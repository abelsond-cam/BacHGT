"""Split curated sample metadata into Panaroo-sized TSV batches.

Sublineage splits, KPSC per-species batches, and rare Klebsiella pneumoniae
packs with deterministic shuffles, plus one ``non_kpsc_species_<safe>.tsv`` per
non-KPSC species (built from the full metadata, not the KPSC subset). Only the
**mgh78578** reference genome is force-added to every batch (deduped by
``Sample``); the broad ``is_reference_genome`` references are not appended —
they land in their own Sublineage/species batch via the natural grouping, and
the cross-batch reference comparison is handled by a separate all-reference run.

Writes batch TSVs and ``panaroo_batching.log`` under ``<output_dir>/batches/``.

Run: uv run python src/bac_panaroo/run_panaroo/panaroo_metadata_batching.py
"""

# ruff: noqa: D102, D103

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import numpy as np
import pandas as pd

DEFAULT_METADATA = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv"
)
DEFAULT_OUTPUT_DIR = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome"
)
LOG_FILENAME = "panaroo_batching.log"
# Batch TSVs and panaroo_batching.log live under output_dir / BATCHES_SUBDIR.
BATCHES_SUBDIR = "batches"


def as_bool(series: pd.Series) -> pd.Series:
    s = series.copy()
    if s.dtype == object:
        return s.map(
            lambda x: (
                str(x).strip().lower() in ("true", "1", "yes", "t")
                if pd.notna(x) and str(x).strip() != ""
                else False
            )
        )
    return s.fillna(False).astype(bool)


class RunLog:
    """Write the same lines to stdout and a single log file (overwrite each run)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file: TextIO = path.open("w", encoding="utf-8")

    def close(self) -> None:
        self._file.close()

    def line(self, msg: str = "") -> None:
        print(msg)
        self._file.write(msg + "\n")
        self._file.flush()


def _strip_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in df.columns if str(c).startswith("_")], errors="ignore")


def write_tsv(
    path: Path,
    df: pd.DataFrame,
    log: RunLog,
    written_counts: Counter[str],
    mgh_id: str,
) -> None:
    _strip_for_csv(df).to_csv(path, sep="\t", index=False)
    n = len(df)
    n_mgh = int((df["Sample"].astype(str) == mgh_id).sum())
    warn = "" if n_mgh == 1 else f"  WARNING: n_mgh={n_mgh} (expected 1)"
    log.line(f"  WROTE {path}")
    log.line(f"    rows={n}  n_mgh={n_mgh}{warn}")
    for sid in df["Sample"].astype(str):
        written_counts[sid] += 1


def _force_add_mgh(df: pd.DataFrame, mgh_row: pd.DataFrame) -> pd.DataFrame:
    """Force the mgh78578 reference genome into a batch (deduped by ``Sample``).

    mgh is K. pneumoniae and rides along on every batch — KPSC sublineage,
    non-KPSC species, or rare-KP pack — so each Panaroo run measures gene
    content against a fixed reference. The broad ``is_reference_genome`` set is
    NOT appended: those genomes already land in their own grouping batch via the
    natural Sublineage/species split. NO ``drop_duplicates`` beyond the mgh row.
    """
    mgh_ids = set(mgh_row["Sample"].astype(str))
    if "Sample" in df.columns:
        df = df.loc[~df["Sample"].astype(str).isin(mgh_ids)]
    return pd.concat([df, mgh_row], ignore_index=True)


def shuffle_two_parts(core: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match panaroo_run_strain._shuffle_and_part: part0 = first ceil(n/2), part1 = rest."""
    n = len(core)
    if n == 0:
        return core.copy(), core.copy()
    order = np.arange(n)
    rng = np.random.default_rng(seed)
    rng.shuffle(order)
    shuffled = core.iloc[order].reset_index(drop=True)
    mid = (n + 1) // 2
    return shuffled.iloc[:mid].copy(), shuffled.iloc[mid:].copy()


def shuffle_n_parts(core: pd.DataFrame, n_parts: int, seed: int) -> list[pd.DataFrame]:
    n = len(core)
    if n == 0:
        return [core.copy() for _ in range(n_parts)]
    order = np.arange(n)
    rng = np.random.default_rng(seed)
    rng.shuffle(order)
    shuffled = core.iloc[order].reset_index(drop=True)
    idx_groups = np.array_split(np.arange(n), n_parts)
    return [shuffled.iloc[g].copy() for g in idx_groups]


def species_to_basename(species: str) -> str:
    safe = re.sub(r"[^\w\-. ]+", "_", str(species))
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe[:200] if safe else "unknown_species"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Batch metadata TSVs for Panaroo runs.")
    p.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA,
        help="Input metadata TSV",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Project root; batch TSVs and {LOG_FILENAME} are written under <dir>/{BATCHES_SUBDIR}/",
    )
    p.add_argument("--min-sublineage", type=int, default=250)
    p.add_argument(
        "--split-low",
        type=int,
        default=3000,
        help="Sublineages with n strictly between this and --split-high get a 2-way split.",
    )
    p.add_argument("--split-high", type=int, default=7000)
    p.add_argument("--sl258-name", type=str, default="SL258")
    p.add_argument("--sl258-parts", type=int, default=5)
    p.add_argument("--kp-batch-min", type=int, default=1500)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    metadata_path = args.metadata.resolve()
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    batches_dir = out_dir / BATCHES_SUBDIR
    batches_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale batch TSVs / lists from any previous run; batching is fully
    # deterministic and a leftover from an earlier config (e.g. a species batch
    # this config no longer emits) would be silently picked up by the list
    # generator's find(1) glob.
    for stale in [*batches_dir.glob("*.tsv"), *batches_dir.glob("*.list")]:
        stale.unlink()
    log_path = batches_dir / LOG_FILENAME
    log = RunLog(log_path)

    try:
        log.line(f"=== panaroo_metadata_batching {datetime.now(timezone.utc).isoformat()} ===")
        log.line(f"metadata={metadata_path}")
        log.line(f"output_dir={out_dir}  batch_tsv_dir={batches_dir}")
        log.line(
            "args: "
            f"min_sublineage={args.min_sublineage} split_low={args.split_low} "
            f"split_high={args.split_high} sl258_name={args.sl258_name!r} "
            f"sl258_parts={args.sl258_parts} kp_batch_min={args.kp_batch_min} seed={args.seed}"
        )
        log.line("")

        metadata = pd.read_csv(metadata_path, sep="\t", low_memory=False)
        log.line(f"Loaded metadata: {len(metadata)} rows from {metadata_path}")

        kpsc = metadata.loc[as_bool(metadata["kpsc_final_list"])].copy()
        log.line(f"After kpsc_final_list filter: {len(kpsc)} rows")

        if "is_mgh78578" not in kpsc.columns:
            log.line("ERROR: column is_mgh78578 missing")
            sys.exit(1)
        global_rows = kpsc.loc[as_bool(kpsc["is_mgh78578"])]
        if len(global_rows) != 1:
            log.line(f"ERROR: expected exactly one is_mgh78578 row, got {len(global_rows)}")
            sys.exit(1)
        global_row = global_rows.iloc[:1].copy()
        gid = str(global_row["Sample"].iloc[0])
        log.line(f"mgh78578 reference Sample (force-added to every batch): {gid}")
        log.line("")

        has_sl = kpsc["Sublineage"].notna()
        kpsc.loc[has_sl, "_sl_norm"] = (
            kpsc.loc[has_sl, "Sublineage"].astype(str).str.strip().str.upper()
        )
        sub = kpsc[has_sl]
        vc = sub.groupby("_sl_norm", sort=False).size()
        min_sl = args.min_sublineage
        large_sl_norms = set(vc[vc >= min_sl].index)
        sl258_norm = args.sl258_name.strip().upper()

        log.line("--- Phase: large sublineages (split or single file) ---")
        log.line(f"Sublineages with n >= {min_sl}: {len(large_sl_norms)}")
        written_counts: Counter[str] = Counter()

        for sl_norm in sorted(large_sl_norms):
            sl_df = kpsc[has_sl & (kpsc["_sl_norm"] == sl_norm)].copy()
            label = str(sl_df["Sublineage"].iloc[0]).strip()
            n = len(sl_df)
            # mgh is force-added at write time; if it already sits in sl_df it is
            # deduped by Sample-ID inside _force_add_mgh. is_reference_genome
            # genomes already present in sl_df stay and participate naturally.
            core = sl_df.copy()

            if sl_norm == sl258_norm:
                log.line(f"  {label}: n={n} -> SL258 path ({args.sl258_parts} parts)")
                parts = shuffle_n_parts(core, args.sl258_parts, args.seed)
                for i, part_core in enumerate(parts):
                    batch = _force_add_mgh(part_core, global_row)
                    out_path = batches_dir / f"{label}_part_{i}.tsv"
                    write_tsv(out_path, batch, log, written_counts, gid)
                continue

            if n >= args.split_high and sl_norm != sl258_norm:
                log.line(
                    f"ERROR: sublineage {label!r} has n={n} >= {args.split_high} "
                    f"but is not {args.sl258_name!r}. Aborting."
                )
                sys.exit(1)

            if args.split_low < n < args.split_high:
                log.line(f"  {label}: n={n} -> 2-way split (core n={len(core)})")
                p0, p1 = shuffle_two_parts(core, args.seed)
                for i, part_core in enumerate((p0, p1)):
                    batch = _force_add_mgh(part_core, global_row)
                    out_path = batches_dir / f"{label}_part_{i}.tsv"
                    write_tsv(out_path, batch, log, written_counts, gid)
                continue

            if min_sl <= n <= args.split_low:
                log.line(f"  {label}: n={n} -> single file (+ mgh)")
                batch = _force_add_mgh(sl_df, global_row)
                out_path = batches_dir / f"{label}.tsv"
                write_tsv(out_path, batch, log, written_counts, gid)
                continue

            log.line(f"ERROR: uncategorized large sublineage {label!r} n={n}")
            sys.exit(1)

        rem_mask = kpsc["Sublineage"].isna() | ~kpsc["_sl_norm"].isin(large_sl_norms)
        remaining = kpsc.loc[rem_mask].copy()
        log.line("")
        log.line("--- Phase: remaining (small / null Sublineage) ---")
        log.line(f"Remaining rows: {len(remaining)}")

        kp_name = "Klebsiella pneumoniae"
        non_kp = remaining.loc[remaining["species"] != kp_name]
        log.line(f"Non–{kp_name} species groups: {non_kp['species'].nunique()}")

        for species, grp in non_kp.groupby("species", sort=False):
            batch = _force_add_mgh(grp, global_row)
            base = species_to_basename(species)
            out_path = batches_dir / f"species_{base}.tsv"
            log.line(f"  species batch: {species!r} -> {out_path.name}")
            write_tsv(out_path, batch, log, written_counts, gid)

        kp_rem = remaining.loc[remaining["species"] == kp_name].copy()
        log.line("")
        log.line("--- Phase: Klebsiella pneumoniae rare sublineages (greedy) ---")
        log.line(f"KP remaining rows: {len(kp_rem)}")

        if len(kp_rem) > 0:
            kp_rem["_sl_ord"] = kp_rem["Sublineage"].map(
                lambda x: str(x).strip().upper() if pd.notna(x) else ""
            )
            sl_sizes = kp_rem.groupby("_sl_ord", sort=False).size().sort_values(ascending=False)
            ordered_sl = list(sl_sizes.index)
            batch_i = 0
            current_parts: list[pd.DataFrame] = []
            current_count = 0

            for sl_o in ordered_sl:
                sl_part = kp_rem.loc[kp_rem["_sl_ord"] == sl_o]
                current_parts.append(sl_part)
                current_count += len(sl_part)
                if current_count > args.kp_batch_min:
                    batch_df = pd.concat(current_parts, ignore_index=True)
                    batch_df = _force_add_mgh(batch_df, global_row)
                    out_path = batches_dir / f"kp_rare_sublineage_batch_{batch_i}.tsv"
                    log.line(
                        f"  flush batch {batch_i}: {current_count} rows "
                        f"across {len(current_parts)} sublineage keys"
                    )
                    write_tsv(out_path, batch_df, log, written_counts, gid)
                    batch_i += 1
                    current_parts = []
                    current_count = 0

            if current_parts:
                batch_df = pd.concat(current_parts, ignore_index=True)
                batch_df = _force_add_mgh(batch_df, global_row)
                out_path = batches_dir / f"kp_rare_sublineage_batch_{batch_i}.tsv"
                log.line(
                    f"  final batch {batch_i}: {len(batch_df)} rows "
                    f"across {len(current_parts)} sublineage keys"
                )
                write_tsv(out_path, batch_df, log, written_counts, gid)

        # --- Phase: non-KPSC per-species batches (over the FULL metadata) ---
        # These rows are not in the kpsc subset. Each batch carries all of that
        # species' rows plus the force-added mgh reference and is run with
        # --non-kpsc-species; the run script drops genomes lacking files on disk.
        # Distinct prefix (non_kpsc_species_*) so they are not confused with the
        # KPSC non-pneumoniae species_*.tsv batches above.
        log.line("")
        log.line("--- Phase: non-KPSC per-species batches (full metadata) ---")
        if "is_kpsc" not in metadata.columns:
            log.line("WARNING: column is_kpsc missing — skipping non-KPSC species batches")
        else:
            non_kpsc = metadata.loc[~as_bool(metadata["is_kpsc"])].copy()
            has_species = non_kpsc["species"].notna() & (
                non_kpsc["species"].astype(str).str.strip() != ""
            )
            n_no_species = int((~has_species).sum())
            if n_no_species:
                log.line(f"  {n_no_species} non-KPSC rows have no species label — skipped")
            non_kpsc = non_kpsc.loc[has_species]

            # Drop rows whose species is a KPSC species (e.g. K. pneumoniae /
            # K. variicola): is_kpsc=False on a KPSC species marks a QC-rejected
            # assembly, not a separate cohort to rebatch. KPSC species batches
            # already come out of the kpsc subset above. Match on the bare
            # binomial (subsp. stripped) so subspecies are caught too.
            def _bare_species(s: str) -> str:
                return str(s).split(" subsp.")[0].strip()

            kpsc_species_set = {_bare_species(s) for s in kpsc["species"].dropna().astype(str)}
            bare = non_kpsc["species"].astype(str).map(_bare_species)
            is_kpsc_sp = bare.isin(kpsc_species_set)
            n_qc_rejected = int(is_kpsc_sp.sum())
            if n_qc_rejected:
                rejected_species = sorted(non_kpsc.loc[is_kpsc_sp, "species"].astype(str).unique())
                log.line(
                    f"  {n_qc_rejected} non-KPSC rows are KPSC species (QC-rejected assemblies) "
                    f"— skipped: {rejected_species}"
                )
            non_kpsc = non_kpsc.loc[~is_kpsc_sp]

            log.line(
                f"Non-KPSC rows: {len(non_kpsc)} across "
                f"{non_kpsc['species'].nunique()} species"
            )
            for species, grp in non_kpsc.groupby("species", sort=False):
                batch = _force_add_mgh(grp, global_row)
                base = species_to_basename(species)
                out_path = batches_dir / f"non_kpsc_species_{base}.tsv"
                note = ""
                if len(grp) > args.split_high:
                    note = (
                        f"  WARNING: n={len(grp)} > split_high={args.split_high}; "
                        "may exceed Panaroo's practical size (not split)"
                    )
                log.line(
                    f"  non-KPSC species batch: {species!r} n={len(grp)} -> {out_path.name}{note}"
                )
                write_tsv(out_path, batch, log, written_counts, gid)

        log.line("")
        log.line("--- Coverage check (kpsc_final_list samples vs written) ---")
        all_ids = set(kpsc["Sample"].astype(str))
        # mgh is intentionally written to every batch — exclude it from the
        # missing/dup checks (it is expected to appear in all of them).
        non_mgh_ids = all_ids - {gid}
        missing = sorted(s for s in non_mgh_ids if written_counts[s] == 0)
        dup = sorted(s for s in non_mgh_ids if written_counts[s] > 1)
        if missing:
            log.line(
                f"WARNING: {len(missing)} kpsc samples never written "
                f"(showing up to 20): {missing[:20]}"
            )
        if dup:
            log.line(
                f"WARNING: {len(dup)} kpsc samples appear in multiple outputs "
                f"(showing up to 20): {dup[:20]}"
            )
        if not missing and not dup:
            log.line(
                "Each non-mgh kpsc_final_list sample appears in exactly one output "
                f"file; mgh ({gid}) appears in all {written_counts[gid]} output files."
            )
        log.line("")
        log.line(f"Done. Log: {log_path}")
    finally:
        log.close()


if __name__ == "__main__":
    main()
