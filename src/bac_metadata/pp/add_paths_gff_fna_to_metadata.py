"""
Add sr_assembly_file and sr_gff_file columns to metadata TSV.

Reads the three .txt path lists (assemblies, ncbi_gff, klebsiella_gff), parses
Sample from each path with GC normalization, writes TSVs, then loads metadata
and adds sr_assembly_file / sr_gff_file via dict lookup. The .txt lists are
simple one-path-per-line files — produce them with e.g.
``find <ASSEMBLIES_DIR> -name "*.fna.gz" > assemblies_file_list.txt``.

Rows whose ``Sample`` starts with ``GCF_``/``GCA_`` are LR-only — the SR-side
lookup is intentionally skipped on them so LR-tree paths can't leak into the
sr_* columns. Stored paths are made relative to the project_k root via
``bac_metadata.path_resolve.to_relative_v2_path``.

``--mode lra`` fills the long-read columns ``lr_assembly_file`` /
``lr_gff_file`` on a metadata_v2 TSV from the ``related_lr/{assemblies,gff}``
pools (the GFF pool also holds the backfilled is_refseq GFFs), resolving by
accession (the shipped accession first, then GCF, then GCA). It only fills
``lr_assembly_file`` where empty so discovery's seb paths are preserved, and
is re-runnable so newly downloaded GFFs are picked up.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/")

METADATA_F = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_final_curated_slimmed.tsv")
METADATA_V2_F = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv")

RELATED_LR_ASM_DIR = DATA_DIR / "david/raw/related_lr/assemblies"
RELATED_LR_GFF_DIR = DATA_DIR / "david/raw/related_lr/gff"
_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")

ASSEMBLY_LIST_F = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/assemblies_file_list.txt")
NCBI_GFF_LIST_F = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/ncbi_gff.txt")
KLEBSIELLA_GFF_LIST_F = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/klebsiella_gff.txt")

ASSEMBLY_TSV_F = ASSEMBLY_LIST_F.with_suffix(".tsv")
NCBI_GFF_TSV_F = NCBI_GFF_LIST_F.with_suffix(".tsv")
KLEBSIELLA_GFF_TSV_F = KLEBSIELLA_GFF_LIST_F.with_suffix(".tsv")
ISESCAN_LIST_F = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/isescan_csv.txt")
ISESCAN_TSV_F = ISESCAN_LIST_F.with_suffix(".tsv")


def _normalize_sample_for_lookup(s: str) -> str:
    """If Sample starts with GC, return first two underscore-separated parts; else return as-is."""
    if not isinstance(s, str):
        s = str(s)
    if s.startswith("GCA_") or s.startswith("GCF_"):
        return s.split(".", 1)[0]
    if s.startswith("GC"):
        parts = s.split("_")
        return "_".join(parts[:2]) if len(parts) >= 2 else s
    return s


def _gc_normalize_series(s: pd.Series) -> pd.Series:
    """Vectorised GC normalization: if starts with GC, take first two parts."""
    s_str = s.astype(str)
    refseq_mask = s_str.str.startswith("GCA_") | s_str.str.startswith("GCF_")
    refseq_first = s_str.str.split(".", n=1).str[0]
    s_norm = s_str.where(~refseq_mask, refseq_first)

    mask = s_norm.str.startswith("GC")
    parts = s_norm.str.split("_")
    first_two = parts.apply(lambda x: "_".join(x[:2]) if len(x) >= 2 else (x[0] if x else ""))
    return s_norm.where(~mask, first_two)


def _parse_assemblies(path_series: pd.Series) -> pd.Series:
    """
    Sample = basename with common FASTA+compression suffixes removed.

    Assemblies are now stored as flat .fa.gz / .fna.gz (always two extensions),
    so we strip these composite suffixes first; if that doesn't match, fall
    back to stripping only the last extension.
    """
    basename = path_series.str.rsplit("/", n=1).str[-1]
    sample = basename.str.replace(".fa.gz", "", regex=False).str.replace(".fna.gz", "", regex=False)
    # Return all extensions, but normalise by GC starting names while doing so
    return _gc_normalize_series(sample)


def _parse_klebsiella_gff(path_series: pd.Series) -> pd.Series:
    """Sample = basename with .bakta.gff3.gz removed."""
    basename = path_series.str.rsplit("/", n=1).str[-1]
    sample = basename.str.removesuffix(".bakta.gff3.gz")
    # Return all extensions, but normalise by GC starting names while doing so
    return _gc_normalize_series(sample)


def _parse_ncbi_gff(path_series: pd.Series) -> pd.Series:
    """Sample = basename, everything before first .gff."""
    basename = path_series.str.rsplit("/", n=1).str[-1]
    sample = basename.str.split(".gff").str[0]
    # Return all extensions, but normalise by GC starting names while doing so
    return _gc_normalize_series(sample)


def _parse_isescan_csv(path_series: pd.Series) -> pd.Series:
    """Sample = basename with assembly+csv suffix removed."""
    basename = path_series.str.rsplit("/", n=1).str[-1]
    sample = basename.str.replace(r"_[0-9]+\.fa\.csv$", "", regex=True)
    return _gc_normalize_series(sample)


def _load_and_parse_txt(
    path: Path,
    parse_fn,
    label: str,
    out_tsv: Path,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load .txt (one path per line), parse Sample, report lines/duplicates, write TSV, return (df, sample->path dict)."""
    if not path.exists():
        raise FileNotFoundError(f"{label} list file not found: {path}")
    df = pd.read_csv(path, header=None, names=["path"])
    df["path"] = df["path"].astype(str).str.strip()
    df = df[df["path"].str.len() > 0]
    n_lines = len(df)
    if n_lines == 0:
        raise ValueError(f"{label} list file is empty: {path}")
    df["Sample"] = parse_fn(df["path"])
    before = len(df)
    df = df.drop_duplicates(subset=["Sample"], keep="first")  # type: ignore[arg-type]
    n_unique = len(df)
    n_dropped = before - n_unique
    print(f"\n{label}:")
    print(f"  Lines read: {n_lines}")
    print(f"  Duplicates dropped: {n_dropped}")
    print(f"  Unique Samples: {n_unique}")
    out_df = df[["Sample", "path"]].copy()
    out_df.to_csv(out_tsv, sep="\t", index=False)
    print(f"  Wrote {out_tsv}")
    d: dict[str, str] = out_df.set_index("Sample")["path"].astype(str).to_dict()
    return (pd.DataFrame(out_df), d)


def _summarise_matches(total_files: int, used_count: int, label: str) -> None:
    """Print summary of how many files in the list were matched to at least one sample."""
    if total_files == 0:
        all_matched_str = "N/A (directory empty)"
    else:
        all_matched_str = str(used_count == total_files)
    print(
        f"{label}: total_files={total_files}, matched_at_least_once={used_count}, all_files_matched={all_matched_str}"
    )


def _apply_path_column(
    df: pd.DataFrame,
    *,
    sample_key_col: str,
    out_col: str,
    lookup_dict: dict[str, str],
) -> tuple[pd.DataFrame, int, int]:
    """Set ``out_col`` from ``sample_key_col`` lookup; return (df, n_found, n_used_files)."""
    df[out_col] = df[sample_key_col].map(lookup_dict)  # type: ignore[arg-type]
    n_found = int(df[out_col].notna().sum())
    n_used_files = int(df[out_col].dropna().nunique())
    return df, n_found, n_used_files


def run(metadata_path: Path | None = None) -> None:
    """Default mode: add sr_assembly_file / sr_gff_file columns to metadata.

    Writes directly to the canonical v2 column names (sr_*). Rows whose
    ``Sample`` starts with ``GCF_``/``GCA_`` are LR-only assemblies — the
    SR-side lookup is intentionally skipped on them (their bare-GC sample
    key would otherwise hit LR-tree entries in the assembly/GFF lists and
    leak LR paths into sr_* columns). Stored paths are made relative to the
    project_k root, matching what ``--mode lra`` does for lr_* columns.
    """
    meta_path = Path(metadata_path) if metadata_path is not None else METADATA_F

    print(f"Metadata file: {meta_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {meta_path}")
    print("  File exists: Yes")

    print("\nParsing path lists and writing TSVs...")
    _, assembly_dict = _load_and_parse_txt(
        ASSEMBLY_LIST_F,
        _parse_assemblies,
        "Assemblies",
        ASSEMBLY_TSV_F,
    )
    _, ncbi_dict = _load_and_parse_txt(
        NCBI_GFF_LIST_F,
        _parse_ncbi_gff,
        "NCBI GFF",
        NCBI_GFF_TSV_F,
    )
    _, kleb_dict = _load_and_parse_txt(
        KLEBSIELLA_GFF_LIST_F,
        _parse_klebsiella_gff,
        "Klebsiella GFF",
        KLEBSIELLA_GFF_TSV_F,
    )

    print("\n" + "=" * 80)
    print("Loading metadata...")
    df = pd.read_csv(meta_path, sep="\t", low_memory=False)
    print(f"Loaded {len(df)} samples from metadata\n")

    df["sample_key"] = df["Sample"].apply(_normalize_sample_for_lookup)
    total_samples = len(df)
    is_gc_sample = df["Sample"].astype(str).str.startswith(("GCF_", "GCA_"))
    sr_eligible = ~is_gc_sample
    n_gc_skipped = int(is_gc_sample.sum())

    df["sr_assembly_file"] = pd.NA
    df.loc[sr_eligible, "sr_assembly_file"] = (
        df.loc[sr_eligible, "sample_key"].map(assembly_dict)
    )
    n_assembly_found     = int(df["sr_assembly_file"].notna().sum())
    n_assembly_not_found = total_samples - n_assembly_found - n_gc_skipped
    used_assembly        = int(df["sr_assembly_file"].dropna().nunique())

    print("Assembly files (SR side):")
    print(f"  Samples in metadata                : {total_samples}")
    print(f"  GC-prefixed (skipped, LR-only rows): {n_gc_skipped}")
    print(f"  Samples with sr_assembly_file      : {n_assembly_found}")
    print(f"  SR-eligible without sr_assembly_file: {n_assembly_not_found}")
    if "kpsc_final_list" in df.columns:
        kpsc_mask = df["kpsc_final_list"].fillna(False).astype(bool) & sr_eligible
        n_kpsc_no_asm = int(df.loc[kpsc_mask, "sr_assembly_file"].isna().sum())
        print(f"    SR-eligible kpsc_final_list rows without sr_assembly_file: {n_kpsc_no_asm}")
    _summarise_matches(len(assembly_dict), used_assembly, "  Assembly list coverage")

    is_refseq_or_nctc = (
        df["is_refseq"].fillna(False).astype(bool)
        | df["is_nctc"].fillna(False).astype(bool)
    )
    search_ncbi = sr_eligible & is_refseq_or_nctc
    search_kleb = sr_eligible & ~is_refseq_or_nctc
    df["sr_gff_file"] = pd.NA
    df.loc[search_ncbi, "sr_gff_file"] = df.loc[search_ncbi, "sample_key"].map(ncbi_dict)
    df.loc[search_kleb, "sr_gff_file"] = df.loc[search_kleb, "sample_key"].map(kleb_dict)

    n_gff_found     = int(df["sr_gff_file"].notna().sum())
    n_gff_not_found = total_samples - n_gff_found - n_gc_skipped
    used_ncbi = int(df.loc[search_ncbi, "sr_gff_file"].dropna().nunique())
    used_kleb = int(df.loc[search_kleb, "sr_gff_file"].dropna().nunique())

    print("\nGFF files (SR side):")
    print(f"  Samples with sr_gff_file           : {n_gff_found}")
    print(f"  SR-eligible without sr_gff_file    : {n_gff_not_found}")
    _summarise_matches(len(ncbi_dict), used_ncbi, "  ncbi_gff3 list coverage")
    _summarise_matches(len(kleb_dict), used_kleb, "  klebsiella_gff3 list coverage")

    # Path-relative rewrite: mirror the strip applied at the end of --mode lra
    # so v1's path columns end up in the same canonical form as v2's lr_* ones.
    from bac_metadata.path_resolve import to_relative_v2_path
    for col in ("sr_assembly_file", "sr_gff_file"):
        s = df[col].astype(str)
        mask = df[col].notna() & s.str.strip().ne("") & s.str.lower().ne("nan")
        df.loc[mask, col] = df.loc[mask, col].map(to_relative_v2_path)

    df = df.drop(columns=["sample_key"])
    df.to_csv(meta_path, sep="\t", index=False)

    print("\n" + "=" * 80)
    print(f"Writing updated metadata to: {meta_path}")
    print("Done!")


def run_add_single_path_column(
    *,
    metadata_path: Path | None = None,
    path_list: Path,
    output_tsv: Path,
    out_col: str,
    label: str,
    parse_fn,
) -> None:
    """Generic mode: add one path column by Sample lookup from a single path list file."""
    meta_path = Path(metadata_path) if metadata_path is not None else METADATA_F
    print(f"Metadata file: {meta_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {meta_path}")
    print("  File exists: Yes")

    print("\nParsing path list and writing TSV...")
    _, lookup_dict = _load_and_parse_txt(path_list, parse_fn, label, output_tsv)

    print("\n" + "=" * 80)
    print("Loading metadata...")
    df = pd.read_csv(meta_path, sep="\t", low_memory=False)
    print(f"Loaded {len(df)} samples from metadata\n")

    df["sample_key"] = df["Sample"].apply(_normalize_sample_for_lookup)
    total_samples = len(df)
    df, n_found, used_files = _apply_path_column(
        df,
        sample_key_col="sample_key",
        out_col=out_col,
        lookup_dict=lookup_dict,
    )
    n_not_found = total_samples - n_found

    print(f"{label} files:")
    print(f"  Samples in metadata: {total_samples}")
    print(f"  Samples with {out_col}: {n_found}")
    print(f"  Samples without {out_col}: {n_not_found}")
    _summarise_matches(len(lookup_dict), used_files, f"  {label} list coverage")

    df = df.drop(columns=["sample_key"])
    df.to_csv(meta_path, sep="\t", index=False)

    print("\n" + "=" * 80)
    print(f"Writing updated metadata to: {meta_path}")
    print("Done!")


def _bare_versioned(value: object) -> str:
    """Versioned bare accession (GCF_000009885.1) from an accession or path/stem."""
    m = _ACC_RE.search(str(value or ""))
    return m.group(1) if m else ""


def _related_lr_pool(d: Path, suffix: str) -> dict[str, str]:
    """Map versioned accession → path for files named ``<acc><suffix>`` in ``d``."""
    out: dict[str, str] = {}
    if d.is_dir():
        for p in d.iterdir():
            if p.name.endswith(suffix):
                out[p.name[: -len(suffix)]] = str(p)
    return out


def run_lra(
    metadata_path: Path | None = None,
    *,
    asm_dir: Path = RELATED_LR_ASM_DIR,
    gff_dir: Path = RELATED_LR_GFF_DIR,
) -> None:
    """Fill ``lr_gff_file`` (and ``lr_assembly_file`` where empty) on metadata_v2.

    LR genomes live at ``related_lr/{assemblies,gff}/<versioned-acc>.{fna.gz,gff}``.
    For every LRA row (non-empty ``lra_gca``/``lra_gcf``) the GFF/assembly is
    resolved by the shipped accession first (the stem of ``lr_assembly_file``),
    then the GCF (RefSeq), then the GCA — matching the discovery resolver.
    ``lr_assembly_file`` is only filled where empty so discovery's seb-resident
    paths are preserved; ``lr_gff_file`` is always (re)resolved from the pool.
    """
    meta_path = Path(metadata_path) if metadata_path is not None else METADATA_V2_F
    print(f"Metadata file: {meta_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {meta_path}")

    df = pd.read_csv(meta_path, sep="\t", low_memory=False)
    print(f"Loaded {len(df)} rows")
    if "lra_gca" not in df.columns and "lra_gcf" not in df.columns:
        raise SystemExit("No lra_gca/lra_gcf columns — not a metadata_v2 TSV; nothing to do.")
    for col in ("lra_gca", "lra_gcf", "lr_assembly_file", "lr_gff_file"):
        if col not in df.columns:
            df[col] = pd.NA
    # An all-NaN column is float64; scalar string assignment into it raises in
    # future pandas — hold the path columns as object up front.
    df["lr_assembly_file"] = df["lr_assembly_file"].astype("object")
    df["lr_gff_file"] = df["lr_gff_file"].astype("object")

    asm_pool = _related_lr_pool(asm_dir, ".fna.gz")
    gff_pool = _related_lr_pool(gff_dir, ".gff")
    print(f"related_lr pools: assemblies={len(asm_pool)} gff={len(gff_pool)}")

    gcf = df["lra_gcf"].fillna("").astype(str).str.strip()
    gca = df["lra_gca"].fillna("").astype(str).str.strip()
    lra_mask = (gcf != "") | (gca != "")
    n_rows = int(lra_mask.sum())

    gff_filled = asm_filled = 0
    for idx in df.index[lra_mask]:
        cands = [
            c for c in (
                _bare_versioned(df.at[idx, "lr_assembly_file"]),
                gcf.at[idx],
                gca.at[idx],
                _bare_versioned(df.at[idx, "Sample"]),
            ) if c
        ]
        for acc in cands:
            if acc in gff_pool:
                df.at[idx, "lr_gff_file"] = gff_pool[acc]
                gff_filled += 1
                break
        cur = str(df.at[idx, "lr_assembly_file"] or "").strip()
        if cur in ("", "nan"):
            for acc in cands:
                if acc in asm_pool:
                    df.at[idx, "lr_assembly_file"] = asm_pool[acc]
                    asm_filled += 1
                    break

    print(f"LRA rows: {n_rows}")
    print(f"  lr_gff_file filled: {gff_filled} ({n_rows - gff_filled} without a GFF on disk)")
    print(f"  lr_assembly_file filled (empty only): {asm_filled}")

    # ── Path-relative rewrite (2026-06-02): strip the project_k prefix from
    # lr_assembly_file / lr_gff_file (and sr_* if present) so v2's path
    # columns are portable. Consumers prepend their own root via
    # `bac_metadata.path_resolve.resolve_v2_path`.
    from bac_metadata.path_resolve import to_relative_v2_path
    for col in ("lr_assembly_file", "lr_gff_file", "sr_assembly_file", "sr_gff_file"):
        if col in df.columns:
            mask = df[col].notna() & (df[col].astype(str).str.strip().ne("")) & (df[col].astype(str).str.lower().ne("nan"))
            df.loc[mask, col] = df.loc[mask, col].map(to_relative_v2_path)

    df.to_csv(meta_path, sep="\t", index=False)
    print("\n" + "=" * 80)
    print(f"Writing updated metadata to: {meta_path}")
    print("Done!")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point with default and generic single-column modes."""
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "metadata",
        nargs="?",
        default=None,
        help="Optional metadata TSV path (default: curated slimmed metadata).",
    )
    parser.add_argument(
        "--mode",
        choices=["default", "isescan", "lra"],
        default="default",
        help="default: SR assembly+gff. isescan: single-column. "
             "lra: fill lr_assembly_file/lr_gff_file on metadata_v2 from related_lr pools.",
    )
    parser.add_argument(
        "--isescan-list",
        default=str(ISESCAN_LIST_F),
        help="Path to newline-delimited full paths of ISEScan CSV files.",
    )
    args = parser.parse_args(argv)

    metadata_path = Path(args.metadata) if args.metadata else None

    if args.mode == "default":
        run(metadata_path)
        return

    if args.mode == "lra":
        run_lra(metadata_path)
        return

    run_add_single_path_column(
        metadata_path=metadata_path,
        path_list=Path(args.isescan_list),
        output_tsv=Path(args.isescan_list).with_suffix(".tsv"),
        out_col="isescan_file",
        label="ISEScan CSV",
        parse_fn=_parse_isescan_csv,
    )


if __name__ == "__main__":
    main()
