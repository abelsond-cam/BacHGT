r"""
Build Panaroo input file from metadata, optionally filtered by strain.

When --clonal-group or --sublineage is given, metadata is filtered to that
strain.  When neither is provided, all samples in the metadata file are used.
``kpsc_final_list`` is enforced unless ``--non-kpsc-species`` is passed (the
non-KPSC per-species batches carry their own genomes plus the mgh reference).

Each metadata row may carry **two** assemblies of one isolate: a short-read
pair (``sr_gff_file`` / ``sr_assembly_file``) and a long-read pair (``lr_gff_file`` /
``lr_assembly_file``). Both are emitted as separate Panaroo genomes when their
files exist on disk. The genome's Panaroo label (= GFF stem = output column
header) is the accession matching its files: ``sample_accession`` for the
short-read genome, ``Sample`` for the long-read genome.

GFF files that are gzipped (.gz) are decompressed into the run subdir
(gff_unzipped/) so only the genomes needed are unzipped; assemblies are
likewise decompressed into assembly_unzipped/. For each genome, a single
Prokka-style combined GFF+FASTA file is created via Panaroo's convert logic in
converted_gff/, and ``panaroo_input.txt`` lists those combined GFF paths (one
per line). ``panaroo_genomes.tsv`` records ``panaroo_label`` → ``Sample`` (plus
``assembly_type`` and ``sample_accession``) so downstream can map each Panaroo
column back to its metadata row and flags.
Used by src/bac_panaroo/slurm_scripts/panaroo_run_strain.sh and panaroo_run_strain_split.sh.

With --split 1 or --split 2 (and --clonal-group or --sublineage), writes
``{label}_all_part{N}/`` with ``sample_metadata.tsv``, symlinks combined GFFs
from ``{label}_all/converted_gff/`` when present, then builds ``panaroo_input.txt``
as usual (shuffle seed 42).
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _load_convert_from_panaroo_fork():
    """Load ``convert`` from the sibling ``panaroo`` fork checkout.

    Layout: the ``BacHGT`` repo and the ``panaroo`` fork are sibling
    directories (``~/developer/`` locally, ``~/workspace/`` on HPC). The
    ``convert`` script lives in ``panaroo/scripts/`` (not in panaroo's
    importable package), so it is loaded directly by file path.
    """
    script_path = (
        Path(__file__).resolve().parents[4]
        / "panaroo"
        / "scripts"
        / "convert_bakta_to_prokka_gff.py"
    )
    if not script_path.is_file():
        raise FileNotFoundError(
            f"Expected Bakta convert script at {script_path}. "
            "Clone the panaroo fork (abelsond-cam/panaroo) as a sibling "
            "directory next to the BacHGT repo."
        )
    spec = importlib.util.spec_from_file_location(
        "panaroo_fork_convert_bakta_to_prokka_gff", script_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.convert


convert = _load_convert_from_panaroo_fork()


# BASE_DIR is project_k root — paths in metadata (e.g. seb/..., david/raw/...)
# are stored relative to it. DATA_ROOT is our personal subtree under it.
PROJECT_K_ROOT = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw"
DATA_ROOT = f"{PROJECT_K_ROOT}/david"
METADATA_FILE = Path(f"{DATA_ROOT}/final/metadata_v2_all_samples_and_columns.tsv")
BASE_DIR = Path(PROJECT_K_ROOT)
DEFAULT_OUTDIR = Path(f"{DATA_ROOT}/processed/panaroo_run")
PANAROO_INPUT_FILENAME = "panaroo_input.txt"
SAMPLE_METADATA_PART_FILENAME = "sample_metadata.tsv"
PANAROO_GENOMES_FILENAME = "panaroo_genomes.tsv"
SPLIT_SHUFFLE_SEED = 42

GFF_UNZIPPED_SUBDIR = "gff_unzipped"
ASSEMBLY_UNZIPPED_SUBDIR = "assembly_unzipped"
CONVERTED_GFF_SUBDIR = "converted_gff"

# Per-genome columns carried through the run pipeline. Each metadata row can
# yield up to two genomes (a short-read and a long-read assembly); panaroo_label
# is the GFF stem = Panaroo column header (sample_accession for SR, Sample for LRA).
GENOME_COLS = [
    "panaroo_label",
    "gff_abs",
    "assembly_abs",
    "assembly_type",
    "Sample",
    "sample_accession",
]


def _abs_path(base: Path, rel: str | float | None) -> Path | None:
    """Resolve a metadata path column to an absolute Path on disk.

    v2 metadata is heterogeneous: ``sr_gff_file`` / ``sr_assembly_file`` are stored
    relative to ``base`` (e.g. ``david/raw/...``), while ``lr_gff_file`` /
    ``lr_assembly_file`` are full absolute paths (``/home/dca36/...``). Detect
    the leading ``/`` to choose: absolute paths are used as-is; relative paths
    are joined onto ``base``. Returns None for null / empty / NaN values.
    """
    if pd.isna(rel) or rel is None or (isinstance(rel, str) and not rel.strip()):
        return None
    s = str(rel).strip()
    p = Path(s) if s.startswith("/") else base / s
    return p.resolve()


def _as_bool(series: pd.Series) -> pd.Series:
    """Coerce a (possibly object/float/NaN) flag column to a clean boolean Series."""
    if series.dtype == bool:
        return series
    if series.dtype == object:
        return series.map(
            lambda x: (
                str(x).strip().lower() in ("true", "1", "yes", "t")
                if pd.notna(x) and str(x).strip() != ""
                else False
            )
        )
    return series.fillna(False).astype(bool)


def _both_exist(gff: Path | None, assembly: Path | None) -> bool:
    """True only if both paths are resolved and present on disk."""
    return (
        gff is not None
        and assembly is not None
        and gff.exists()
        and assembly.exists()
    )


def _genome_records_for_row(base_dir: Path, row: pd.Series) -> list[dict]:
    """Expand one metadata row into up to two genome records (short-read + long-read).

    Each metadata row may carry a short-read assembly (``sr_gff_file`` /
    ``sr_assembly_file``) and/or a long-read assembly (``lr_gff_file`` /
    ``lr_assembly_file``); both can coexist for the same isolate. Each is
    emitted as its own genome only when **both** of its GFF and assembly files
    resolve and exist on disk (graceful per-assembly skipping).

    The Panaroo label (GFF stem = output column header) is the accession that
    already matches the assembly's files: ``sample_accession`` for the
    short-read genome, ``Sample`` for the long-read genome.

    Parameters
    ----------
    base_dir
        Root to prepend to the relative path columns.
    row
        One metadata row (``Sample``, ``sample_accession`` and the four file
        columns are read via ``.get`` so missing columns degrade gracefully).

    Returns
    -------
    list of dict
        Up to two records with keys ``panaroo_label``, ``gff_abs``,
        ``assembly_abs``, ``assembly_type`` (``"sr"`` / ``"lra"``), ``Sample``
        and ``sample_accession``.
    """
    records: list[dict] = []
    sample = row.get("Sample")
    sample_accession = row.get("sample_accession")

    sr_gff = _abs_path(base_dir, row.get("sr_gff_file"))
    sr_assembly = _abs_path(base_dir, row.get("sr_assembly_file"))
    if _both_exist(sr_gff, sr_assembly):
        if pd.notna(sample_accession) and str(sample_accession).strip():
            records.append(
                {
                    "panaroo_label": str(sample_accession).strip(),
                    "gff_abs": sr_gff,
                    "assembly_abs": sr_assembly,
                    "assembly_type": "sr",
                    "Sample": sample,
                    "sample_accession": sample_accession,
                }
            )
        else:
            print(
                f"Warning: short-read assembly present for Sample={sample!r} but "
                "sample_accession is empty; cannot label the SR genome — skipping it.",
                file=sys.stderr,
            )

    lra_gff = _abs_path(base_dir, row.get("lr_gff_file"))
    lra_assembly = _abs_path(base_dir, row.get("lr_assembly_file"))
    if _both_exist(lra_gff, lra_assembly):
        records.append(
            {
                "panaroo_label": str(sample).strip(),
                "gff_abs": lra_gff,
                "assembly_abs": lra_assembly,
                "assembly_type": "lra",
                "Sample": sample,
                "sample_accession": sample_accession,
            }
        )
    return records


def _eligible_samples_df(
    metadata_file: Path,
    base_dir: Path,
    strain_type: str | None,
    strain_value: str | None,
    non_kpsc_species: bool = False,
) -> tuple[str, pd.DataFrame]:
    """Resolve eligible genomes for a run as a one-row-per-genome long frame.

    Loads metadata, applies the strain filter and (unless *non_kpsc_species*)
    the ``kpsc_final_list`` filter, then expands each surviving row into up to
    two genome records (short-read + long-read assembly), keeping only genomes
    whose GFF and assembly both exist on disk. Returns ``(group_desc, long_df)``
    where ``long_df`` has the original metadata columns plus ``panaroo_label``,
    ``gff_abs``, ``assembly_abs`` and ``assembly_type``.
    """
    df = pd.read_csv(metadata_file, sep="\t", low_memory=False)

    if strain_type is not None and strain_value is not None:
        if strain_type not in df.columns:
            print(
                f"ERROR: metadata has no column {strain_type!r}. "
                f"Columns include: {list(df.columns)[:30]} …",
                file=sys.stderr,
            )
            sys.exit(1)
        key = str(strain_value).strip()
        col_norm = df[strain_type].astype(str).str.strip().str.upper()
        subset = df[col_norm == key.upper()].copy()
        group_desc = f"{strain_type}: {strain_value}"
    else:
        subset = df.copy()
        group_desc = f"All samples from {metadata_file.name}"

    before_kpsc_filter = len(subset)
    print(f"{group_desc}")
    if non_kpsc_species:
        print("  --non-kpsc-species: NOT applying the kpsc_final_list filter")
    else:
        subset = subset[_as_bool(subset["kpsc_final_list"])]
        after_kpsc_filter = len(subset)
        print("  Applied mandatory filter: kpsc_final_list == True")
        print(f"  Before kpsc_final_list filter: {before_kpsc_filter}")
        print(f"  Removed by kpsc_final_list filter: {before_kpsc_filter - after_kpsc_filter}")
        print(f"  Remaining after kpsc_final_list filter: {after_kpsc_filter}")

    total_in_group = len(subset)
    if total_in_group == 0:
        print(f"No samples found ({group_desc}).")
        if (
            before_kpsc_filter == 0
            and strain_type is not None
            and strain_value is not None
            and strain_type in df.columns
        ):
            col = df[strain_type].dropna().astype(str)
            sample_vals = sorted({s.strip() for s in col.unique()})[:25]
            print(
                f"  Hint: no rows matched {strain_value!r} (after strip + case-insensitive match on "
                f"{strain_type!r}). Example values (up to 25): {sample_vals}"
            )
        elif before_kpsc_filter > 0 and not non_kpsc_species:
            print(
                "  All strain-matched rows were removed by kpsc_final_list == True."
            )
        sys.exit(1)

    # Expand to one row per genome (SR and/or LRA). The helper only returns
    # genomes whose GFF + assembly both exist on disk, so every record here is
    # guaranteed to resolve. Bounded per-batch, so a row loop is fine.
    genome_rows: list[dict] = []
    for _, row in subset.iterrows():
        for rec in _genome_records_for_row(base_dir, row):
            genome_rows.append({**row.to_dict(), **rec})

    if not genome_rows:
        print(
            "No genomes have both a GFF and an assembly present on disk "
            f"({group_desc}). Exiting.",
            file=sys.stderr,
        )
        sys.exit(1)

    eligible = pd.DataFrame(genome_rows)

    # Two genomes cannot share a Panaroo column header; drop dup labels keep-first.
    dup_mask = eligible["panaroo_label"].duplicated(keep="first")
    if dup_mask.any():
        dups = sorted(eligible.loc[dup_mask, "panaroo_label"].astype(str).unique())
        print(
            f"  WARNING: dropped {int(dup_mask.sum())} duplicate panaroo_label(s) "
            f"(keep-first): {dups[:20]}{' …' if len(dups) > 20 else ''}"
        )
        eligible = eligible.loc[~dup_mask].copy()

    n_genomes = len(eligible)
    n_sr = int((eligible["assembly_type"] == "sr").sum())
    n_lra = int((eligible["assembly_type"] == "lra").sum())
    labels = eligible["panaroo_label"].astype(str)
    n_gcf = int(labels.str.startswith("GCF_").sum())
    n_gca = int(labels.str.startswith("GCA_").sum())
    n_other = n_genomes - n_gcf - n_gca
    print(f"  Total in group (samples): {total_in_group}")
    print(f"  Genomes with both GFF + assembly on disk: {n_genomes}")
    print(f"    by assembly_type:  sr={n_sr}  lra={n_lra}")
    print(f"    by accession:      GCF={n_gcf}  GCA={n_gca}  other(SR/SAM)={n_other}")

    return group_desc, eligible


def _shuffle_and_part(eligible_df: pd.DataFrame, part: int) -> pd.DataFrame:
    """Shuffle row order with a fixed seed, then split into two deterministic halves.

    Part 1 = first ceil(n/2) rows, part 2 = remainder (stable across invocations).
    """
    if part not in (1, 2):
        raise ValueError(f"part must be 1 or 2, got {part}")
    n = len(eligible_df)
    if n == 0:
        return eligible_df.copy()
    order = np.arange(n)
    rng = np.random.default_rng(SPLIT_SHUFFLE_SEED)
    rng.shuffle(order)
    shuffled = eligible_df.iloc[order].reset_index(drop=True)
    mid = (n + 1) // 2  # ceil(n/2)
    if part == 1:
        return shuffled.iloc[:mid]
    return shuffled.iloc[mid:]


def _run_subdir_for_split(outdir: Path, run_label: str, part: int) -> Path:
    return outdir / f"{run_label}_part{part}"


def _canonical_run_dir(outdir: Path, run_label: str) -> Path:
    return outdir / run_label


def _write_part_metadata(run_subdir: Path, df_slice: pd.DataFrame) -> Path:
    """Write subset metadata without internal path columns."""
    out = run_subdir / SAMPLE_METADATA_PART_FILENAME
    to_write = df_slice.drop(
        columns=[c for c in ("gff_abs", "assembly_abs") if c in df_slice.columns],
        errors="ignore",
    )
    to_write.to_csv(out, sep="\t", index=False)
    return out


def _symlink_converted_gff_from_canonical(
    run_subdir: Path,
    outdir: Path,
    run_label: str,
    panaroo_labels: pd.Series,
) -> None:
    """Symlink combined GFFs from canonical {run_label}_all/converted_gff when present."""
    canonical_gff = _canonical_run_dir(outdir, run_label) / CONVERTED_GFF_SUBDIR
    part_gff_dir = run_subdir / CONVERTED_GFF_SUBDIR
    part_gff_dir.mkdir(parents=True, exist_ok=True)
    n_link = 0
    for label in panaroo_labels.astype(str):
        src = canonical_gff / f"{label}.gff"
        dst = part_gff_dir / f"{label}.gff"
        if not src.is_file():
            continue
        if dst.exists() or dst.is_symlink():
            continue
        rel = os.path.relpath(src, start=dst.parent)
        dst.symlink_to(rel)
        n_link += 1
    print(
        f"  Symlinked {n_link}/{len(panaroo_labels)} combined GFFs from {canonical_gff}"
    )


def _build_panaroo_input(
    run_subdir: Path,
    rows_both: pd.DataFrame,
) -> tuple[Path, Path]:
    """Create unzipped dirs, convert/reuse combined GFFs, write the run inputs.

    Writes ``panaroo_input.txt`` and ``panaroo_genomes.tsv``. ``rows_both`` must
    have the GENOME_COLS columns (one row per genome). Returns
    (input_path, run_subdir).
    """
    run_subdir.mkdir(parents=True, exist_ok=True)
    gff_unzipped_dir = run_subdir / GFF_UNZIPPED_SUBDIR
    gff_unzipped_dir.mkdir(exist_ok=True)
    assembly_unzipped_dir = run_subdir / ASSEMBLY_UNZIPPED_SUBDIR
    assembly_unzipped_dir.mkdir(exist_ok=True)
    converted_gff_dir = run_subdir / CONVERTED_GFF_SUBDIR
    converted_gff_dir.mkdir(exist_ok=True)
    input_path = run_subdir / PANAROO_INPUT_FILENAME

    n_samples = len(rows_both)
    already_combined_count = 0
    newly_converted_count = 0
    lines_written = 0
    mismatched_rows: list[dict[str, str]] = []
    mismatched_tsv_path = run_subdir / "mismatched_faa_gff.tsv"
    # Genomes that actually land in panaroo_input.txt (cached-reuse or freshly
    # converted) — written to panaroo_genomes.tsv so downstream can map each
    # Panaroo column header (panaroo_label) back to its metadata Sample + flags.
    genomes_written: list[dict] = []

    def _record(row: pd.Series, label: str) -> None:
        genomes_written.append(
            {
                "panaroo_label": label,
                "Sample": row["Sample"],
                "assembly_type": row["assembly_type"],
                "sample_accession": row["sample_accession"],
            }
        )

    with open(input_path, "w") as f:
        for i, (_, row) in enumerate(rows_both.iterrows()):
            label = str(row["panaroo_label"])
            gff_abs = row["gff_abs"]
            assembly_abs = row["assembly_abs"]
            combined_gff = converted_gff_dir / f"{label}.gff"

            if combined_gff.exists():
                is_valid, reason = _is_valid_combined_gff(combined_gff)
                if is_valid:
                    already_combined_count += 1
                    f.write(f"{combined_gff}\n")
                    lines_written += 1
                    _record(row, label)
                    continue
                print(
                    f"Invalid existing combined GFF for genome {label}: "
                    f"{combined_gff} ({reason}). Regenerating."
                )
                try:
                    combined_gff.unlink()
                except OSError as exc:
                    print(
                        f"Warning: failed to delete invalid combined GFF "
                        f"{combined_gff}: {exc}"
                    )

            gff_for_panaroo = _ensure_gff_unzipped(gff_abs, gff_unzipped_dir, i)
            assembly_for_panaroo = _ensure_assembly_unzipped(
                assembly_abs, assembly_unzipped_dir, i
            )
            try:
                convert(
                    str(gff_for_panaroo),
                    str(combined_gff),
                    str(assembly_for_panaroo),
                    is_ignore_overlapping=True,
                )
            except RuntimeError as exc:
                # Known failure mode: GFF CDS seqids don't exist in FASTA,
                # so conversion can't produce a combined GFF+FASTA file.
                if "Mismatch between fasta and GFF!" in str(exc):
                    mismatched_rows.append(
                        {
                            "subdir": str(run_subdir),
                            "panaroo_label": label,
                            "assembly_type": str(row["assembly_type"]),
                            "Sample": str(row["Sample"]),
                            "sr_assembly_file": str(assembly_abs),
                            "sr_gff_file": str(gff_abs),
                        }
                    )
                    print(
                        f"Skipping genome {label} due to FASTA/GFF mismatch.",
                        file=sys.stderr,
                    )
                    # Ensure we don't leave a partial cached combined GFF behind.
                    try:
                        combined_gff.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise
            else:
                newly_converted_count += 1
                f.write(f"{combined_gff}\n")
                lines_written += 1
                _record(row, label)
            finally:
                # Release large staged temp files promptly (even if conversion failed).
                if gff_abs.suffix == ".gz":
                    try:
                        gff_for_panaroo.unlink()
                    except FileNotFoundError:
                        pass
                if assembly_abs.suffix == ".gz":
                    try:
                        assembly_for_panaroo.unlink()
                    except FileNotFoundError:
                        pass

    try:
        shutil.rmtree(gff_unzipped_dir)
    except OSError as e:
        print(f"Warning: failed to remove {gff_unzipped_dir}: {e}")
    try:
        shutil.rmtree(assembly_unzipped_dir)
    except OSError as e:
        print(f"Warning: failed to remove {assembly_unzipped_dir}: {e}")

    print(
        f"Combined files already present in {converted_gff_dir}: "
        f"{already_combined_count}/{n_samples}"
    )
    print(f"Skipped converting {already_combined_count} samples with existing combined files.")
    print(f"Converted {newly_converted_count} new combined files.")
    print(f"Wrote {lines_written} lines to {input_path}")

    if mismatched_rows:
        pd.DataFrame(mismatched_rows).to_csv(
            mismatched_tsv_path, sep="\t", index=False
        )
        print(
            f"FASTA/GFF mismatches skipped: {len(mismatched_rows)}. "
            f"Wrote {mismatched_tsv_path}"
        )
        print("Skipped genomes (FASTA/GFF mismatch):")
        for r in mismatched_rows:
            print(
                f"  {r['panaroo_label']}\t{r['assembly_type']}\t{r['sr_gff_file']}\t{r['sr_assembly_file']}"
            )

    genomes_tsv_path = run_subdir / PANAROO_GENOMES_FILENAME
    pd.DataFrame(
        genomes_written,
        columns=["panaroo_label", "Sample", "assembly_type", "sample_accession"],
    ).to_csv(genomes_tsv_path, sep="\t", index=False)
    n_sr = sum(1 for g in genomes_written if g["assembly_type"] == "sr")
    n_lra = sum(1 for g in genomes_written if g["assembly_type"] == "lra")
    print(f"Wrote {genomes_tsv_path}  (n={len(genomes_written)}: sr={n_sr} lra={n_lra})")
    print(f"Run subdir (for panaroo -o): {run_subdir}")
    return input_path, run_subdir


def _is_valid_combined_gff(path: Path) -> tuple[bool, str]:
    """Lightweight structural validation for cached combined GFF files.

    Requires:
    - file exists and is non-empty
    - contains '##FASTA'
    - FASTA section contains at least one '>' header
    """
    if not path.exists():
        return False, "file does not exist"
    try:
        if path.stat().st_size == 0:
            return False, "file is empty"
        with open(path) as fh:
            content = fh.read()
    except OSError as exc:
        return False, f"unable to read file: {exc}"

    if "##FASTA" not in content:
        return False, "missing ##FASTA section"
    _, fasta_part = content.split("##FASTA", 1)
    has_header = any(ln.lstrip().startswith(">") for ln in fasta_part.splitlines())
    if not has_header:
        return False, "FASTA section has no sequence headers"
    return True, "ok"


def _ensure_gff_unzipped(gff_path: Path, out_dir: Path, index: int) -> Path:
    """Decompress a gzipped GFF into out_dir, or return the path unchanged.

    If gff_path ends with .gz, decompress to out_dir/gff_{index}.gff and return
    that path. Otherwise return gff_path unchanged.
    """
    if gff_path.suffix != ".gz":
        return gff_path
    out_path = out_dir / f"gff_{index}.gff"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    with gzip.open(gff_path, "rt") as f_in, open(out_path, "w") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return out_path


def _ensure_assembly_unzipped(assembly_path: Path, out_dir: Path, index: int) -> Path:
    """Decompress a gzipped assembly into out_dir, or return the path unchanged.

    If assembly_path ends with .gz, decompress to out_dir/assembly_{index}.fna
    and return that path. Otherwise return assembly_path unchanged.
    """
    if assembly_path.suffix != ".gz":
        return assembly_path
    out_path = out_dir / f"assembly_{index}.fna"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    with gzip.open(assembly_path, "rt") as f_in:
        with open(out_path, "w") as f_out:
            for line in f_in:
                f_out.write(line)
    return out_path


def run(
    strain_type: str | None,
    strain_value: str | None,
    n: int,
    outdir: Path,
    metadata_file: Path,
    base_dir: Path,
    run_label: str | None = None,
    split_part: int | None = None,
    non_kpsc_species: bool = False,
) -> tuple[Path, Path]:
    """Build a Panaroo run for a strain (or all samples), expanding to genomes.

    Optionally filters metadata by strain_type == strain_value, expands each row
    into up to two genomes (short-read + long-read), and restricts to genomes
    with both GFF and assembly on disk.

    When strain_type/strain_value are None, all rows are used. When
    *non_kpsc_species* is True the ``kpsc_final_list`` filter is skipped (used
    for the non-KPSC per-species batches, which carry their own genomes + mgh).
    *run_label* drives the output subdir name ({run_label}_all or
    {run_label}_n{n}).  Defaults to strain_value when filtering by strain,
    or the metadata file stem when using all samples.

    When *split_part* is 1 or 2, requires clonal group or sublineage; shuffles
    eligible genomes with fixed seed and writes only that half to
    {run_label}_all_part{p}.

    Returns (input_file_path, run_subdir_path).
    """
    if split_part is not None:
        print("=" * 70)
        print(
            "panaroo_run_strain.py  MODE=TWO_WAY_SPLIT  "
            f"--split {split_part}/2  (shuffle_seed={SPLIT_SHUFFLE_SEED})"
        )
        print(
            "  Strain filter:",
            f"{strain_type!r} = {strain_value!r}",
            "|  metadata:",
            metadata_file,
        )
        print(
            "  Note: --split is added by panaroo_run_strain_split.sh from "
            "SLURM_ARRAY_TASK_ID; you do not pass it on the sbatch command line."
        )
        print("=" * 70)
        if strain_type is None or strain_value is None:
            print("ERROR: --split requires --clonal-group or --sublineage.", file=sys.stderr)
            sys.exit(1)
        group_desc, eligible = _eligible_samples_df(
            metadata_file, base_dir, strain_type, strain_value, non_kpsc_species
        )
        part_df = _shuffle_and_part(eligible, split_part)
        if len(part_df) == 0:
            print(
                f"No genomes in split part {split_part} (empty partition). Exiting.",
                file=sys.stderr,
            )
            sys.exit(1)
        if run_label is None:
            run_label = strain_value
        print(
            f"  - Split part {split_part}: {len(part_df)} genomes "
            f"(shuffle seed {SPLIT_SHUFFLE_SEED}, first half = part 1)"
        )
        run_subdir = _run_subdir_for_split(outdir, run_label, split_part)
        run_subdir.mkdir(parents=True, exist_ok=True)
        meta_path = _write_part_metadata(run_subdir, part_df)
        print(f"  - Wrote {meta_path}")
        _symlink_converted_gff_from_canonical(
            run_subdir, outdir, run_label, part_df["panaroo_label"]
        )
        rows_both = part_df[GENOME_COLS].copy()
        return _build_panaroo_input(run_subdir, rows_both)

    group_desc, eligible = _eligible_samples_df(
        metadata_file, base_dir, strain_type, strain_value, non_kpsc_species
    )
    rows_full = eligible
    if n >= 1:
        # --n caps the number of samples (isolates); keep all genomes of those
        # samples so paired SR + LRA genomes stay together in smoke-tests.
        keep_samples = rows_full["Sample"].drop_duplicates().head(n)
        rows_full = rows_full[rows_full["Sample"].isin(keep_samples)]
        print(
            f"  - Selected first {n} samples ({len(rows_full)} genomes) ({group_desc})"
        )

    n_written = len(rows_full)
    if run_label is None:
        run_label = strain_value if strain_value is not None else metadata_file.stem

    if n == -1:
        print(f"  - Using all {n_written} genomes ({group_desc})")
    run_subdir = outdir / run_label
    rows_both = rows_full[GENOME_COLS].copy()
    return _build_panaroo_input(run_subdir, rows_both)


def main() -> None:
    """CLI entry point: parse args and run."""
    parser = argparse.ArgumentParser(
        description=(
            "Build Panaroo input file from metadata.  Optionally filter by "
            "--clonal-group or --sublineage; if neither is given, all samples "
            "in the metadata file are used."
        ),
    )
    strain_group = parser.add_mutually_exclusive_group(required=False)
    strain_group.add_argument(
        "--clonal-group",
        type=str,
        default=None,
        help="Clonal group to filter by (e.g. CG11); matched with strip + case-insensitive equality on metadata column 'Clonal group'",
    )
    strain_group.add_argument(
        "--sublineage",
        type=str,
        default=None,
        help="Sublineage to filter by (e.g. SL_123); matched with strip + case-insensitive equality on metadata column 'Sublineage'",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=-1,
        help="Max number of samples to include; -1 = all (default: -1)",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=DEFAULT_OUTDIR,
        help=f"Base output directory; run subdir created under it (default: {DEFAULT_OUTDIR})",
    )
    parser.add_argument(
        "--sample-metadata-file",
        type=Path,
        default=METADATA_FILE,
        help="Path to sample metadata TSV (default: project default)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Base directory to prepend to sr_gff_file and sr_assembly_file paths (default: project default)",
    )
    parser.add_argument(
        "--split",
        type=int,
        choices=(1, 2),
        default=None,
        metavar="PART",
        help=(
            "Two-way split: part 1 or 2. For normal use, panaroo_run_strain_split.sh passes "
            "this from SLURM_ARRAY_TASK_ID (you do not type --split on sbatch). "
            "Requires --clonal-group or --sublineage; --n must be -1. Fixed shuffle seed 42."
        ),
    )
    parser.add_argument(
        "--non-kpsc-species",
        action="store_true",
        help=(
            "Disable the otherwise-mandatory kpsc_final_list filter. Use for the "
            "non-KPSC per-species batches, whose TSV already carries that species' "
            "genomes plus the force-added mgh reference."
        ),
    )
    args = parser.parse_args()

    if args.split is not None and args.n != -1:
        parser.error("--split cannot be used unless --n is -1 (all samples in that strain)")

    if args.clonal_group is not None:
        strain_type = "Clonal group"
        strain_value = args.clonal_group
    elif args.sublineage is not None:
        strain_type = "Sublineage"
        strain_value = args.sublineage
    else:
        strain_type = None
        strain_value = None

    if args.split is not None and strain_value is None:
        parser.error("--split requires --clonal-group or --sublineage")

    run(
        strain_type=strain_type,
        strain_value=strain_value,
        n=args.n,
        outdir=args.outdir,
        metadata_file=args.sample_metadata_file,
        base_dir=args.base_dir,
        split_part=args.split,
        non_kpsc_species=args.non_kpsc_species,
    )


if __name__ == "__main__":
    main()
