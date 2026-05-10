"""Split curated sample metadata into Panaroo-sized TSV batches.

Sublineage splits, species batches, and rare Klebsiella pneumoniae packs with
deterministic shuffles. Every batch TSV has the **reference bucket** attached:
a curated TSV (default: ``<DATA_ROOT>/final/reference_bucket.tsv``, produced by
``build_reference_bucket.py``) of Sample IDs to ride along on every Panaroo run
so the same fixed pool of references is available cross-batch. If the bucket
TSV is missing, falls back to ``is_mgh78578`` alone (matches pre-bucket
behaviour). Bucket rows carry ``is_reference_bucket=True`` in the output.

Writes batch TSVs and ``panaroo_batching.log`` under ``<output_dir>/batches/``.

Run: uv run python src/bacotype/pp/panaroo_metadata_batching.py
"""

# ruff: noqa: D102, D103

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO, cast

import numpy as np
import pandas as pd

DEFAULT_METADATA = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_final_curated_slimmed.tsv"
)
DEFAULT_OUTPUT_DIR = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome_v2"
)
DEFAULT_REFERENCE_BUCKET_TSV = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/reference_bucket.tsv"
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


def count_refs(df: pd.DataFrame) -> tuple[int, int]:
    n_g = (
        int(as_bool(cast(pd.Series, df["is_mgh78578"])).sum())
        if "is_mgh78578" in df.columns
        else 0
    )
    n_n = (
        int(as_bool(cast(pd.Series, df["is_complete_norway_genome"])).sum())
        if "is_complete_norway_genome" in df.columns
        else 0
    )
    return n_g, n_n


def write_tsv(
    path: Path,
    df: pd.DataFrame,
    log: RunLog,
    written_counts: Counter[str],
    bucket_ids: set[str],
) -> None:
    _strip_for_csv(df).to_csv(path, sep="\t", index=False)
    n = len(df)
    n_g, n_n = count_refs(df)
    sample_ids = set(df["Sample"].astype(str))
    n_bucket_refs = len(sample_ids & bucket_ids)
    warn = ""
    if n_g != 1:
        warn += f"  WARNING: n_global={n_g} (expected 1)"
    if n_bucket_refs != len(bucket_ids):
        warn += (
            f"  WARNING: reference bucket incomplete "
            f"({n_bucket_refs}/{len(bucket_ids)} present)"
        )
    log.line(f"  WROTE {path}")
    log.line(
        f"    rows={n}  n_bucket_refs={n_bucket_refs}  "
        f"n_global={n_g}  n_norway={n_n}{warn}"
    )
    for sid in df["Sample"].astype(str):
        written_counts[sid] += 1


def _attach_reference_bucket(df: pd.DataFrame, bucket: pd.DataFrame) -> pd.DataFrame:
    """Attach the reference bucket to a batch core.

    Strips only rows whose ``Sample`` ID overlaps with the bucket — non-bucket
    RefSeqs that organically sit in the core (e.g. K. variicola RefSeqs that
    aren't Norway-completes) are preserved and continue to participate in the
    Panaroo pangenome at level d/c/b/a. NO ``drop_duplicates`` anywhere.

    The bucket itself is expected to already carry ``is_reference_bucket=True``
    on every row (stamped once at construction time in ``main``).
    """
    bucket_sample_ids = set(bucket["Sample"].astype(str))
    if "Sample" in df.columns:
        df = df.loc[~df["Sample"].astype(str).isin(bucket_sample_ids)]
    return pd.concat([df, bucket], ignore_index=True)


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
    p.add_argument(
        "--reference-bucket-tsv",
        type=Path,
        default=DEFAULT_REFERENCE_BUCKET_TSV,
        help="TSV listing Sample IDs to attach to every batch as references "
        "(produced by build_reference_bucket.py). Falls back to is_mgh78578 "
        "alone if the file is missing.",
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

        kpsc = metadata.loc[metadata["kpsc_final_list"]].copy()
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
        log.line(f"Global reference Sample: {gid}")

        # Reference bucket — attached to every batch so each Panaroo run sees
        # the same curated set of comparison references. Loaded from a TSV
        # (one Sample ID per line under header "Sample") at args.reference_bucket_tsv.
        # If the file is missing, fall back to is_mgh78578 alone (matches the
        # pre-bucket behaviour). The bucket members carry an is_reference_bucket=True
        # column in every output batch TSV.
        bucket_path = args.reference_bucket_tsv.resolve()
        if bucket_path.is_file():
            bucket_ids_from_tsv = set(
                pd.read_csv(bucket_path, sep="\t")["Sample"].astype(str)
            )
            bucket_refs = kpsc.loc[
                kpsc["Sample"].astype(str).isin(bucket_ids_from_tsv)
            ].copy()
            log.line(
                f"Reference bucket from {bucket_path}: "
                f"n={len(bucket_refs)} of {len(bucket_ids_from_tsv)} listed IDs"
            )
            missing_from_kpsc = bucket_ids_from_tsv - set(
                bucket_refs["Sample"].astype(str)
            )
            if missing_from_kpsc:
                log.line(
                    f"WARNING: {len(missing_from_kpsc)} bucket Sample IDs not "
                    f"found in kpsc_final_list metadata (showing up to 20): "
                    f"{sorted(missing_from_kpsc)[:20]}"
                )
        else:
            log.line(
                f"Reference bucket: {bucket_path} not found; "
                f"falling back to is_mgh78578 only."
            )
            bucket_refs = kpsc.loc[as_bool(kpsc["is_mgh78578"])].copy()

        if gid not in set(bucket_refs["Sample"].astype(str)):
            log.line(f"ERROR: mgh78578 ({gid}) is not in the reference bucket")
            sys.exit(1)
        # Stamp the bucket-membership flag once; every output batch TSV inherits
        # this column on the bucket rows (and missing/False on non-bucket rows).
        bucket_refs["is_reference_bucket"] = True
        bucket_ids = set(bucket_refs["Sample"].astype(str))
        log.line(f"Reference bucket size: {len(bucket_refs)} (incl. mgh {gid})")
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
            # The reference bucket is attached at write time. Bucket members
            # already in sl_df (e.g. an sl_df-resident Norway-complete) are
            # stripped by Sample-ID overlap inside _attach_reference_bucket;
            # other refseqs in sl_df (none expected here, but defensive) stay.
            core = sl_df.copy()

            if sl_norm == sl258_norm:
                log.line(f"  {label}: n={n} -> SL258 path ({args.sl258_parts} parts)")
                parts = shuffle_n_parts(core, args.sl258_parts, args.seed)
                for i, part_core in enumerate(parts):
                    batch = _attach_reference_bucket(part_core, bucket_refs)
                    out_path = batches_dir / f"{label}_part_{i}.tsv"
                    write_tsv(out_path, batch, log, written_counts, bucket_ids)
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
                    batch = _attach_reference_bucket(part_core, bucket_refs)
                    out_path = batches_dir / f"{label}_part_{i}.tsv"
                    write_tsv(out_path, batch, log, written_counts, bucket_ids)
                continue

            if min_sl <= n <= args.split_low:
                log.line(f"  {label}: n={n} -> single file (+ reference bucket)")
                batch = _attach_reference_bucket(sl_df, bucket_refs)
                out_path = batches_dir / f"{label}.tsv"
                write_tsv(out_path, batch, log, written_counts, bucket_ids)
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
            batch = _attach_reference_bucket(grp, bucket_refs)
            base = species_to_basename(species)
            out_path = batches_dir / f"species_{base}.tsv"
            log.line(f"  species batch: {species!r} -> {out_path.name}")
            write_tsv(out_path, batch, log, written_counts, bucket_ids)

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
                    batch_df = _attach_reference_bucket(batch_df, bucket_refs)
                    out_path = batches_dir / f"kp_rare_sublineage_batch_{batch_i}.tsv"
                    log.line(
                        f"  flush batch {batch_i}: {current_count} rows "
                        f"across {len(current_parts)} sublineage keys"
                    )
                    write_tsv(out_path, batch_df, log, written_counts, bucket_ids)
                    batch_i += 1
                    current_parts = []
                    current_count = 0

            if current_parts:
                batch_df = pd.concat(current_parts, ignore_index=True)
                batch_df = _attach_reference_bucket(batch_df, bucket_refs)
                out_path = batches_dir / f"kp_rare_sublineage_batch_{batch_i}.tsv"
                log.line(
                    f"  final batch {batch_i}: {len(batch_df)} rows "
                    f"across {len(current_parts)} sublineage keys"
                )
                write_tsv(out_path, batch_df, log, written_counts, bucket_ids)

        log.line("")
        log.line("--- Coverage check (kpsc_final_list samples vs written) ---")
        all_ids = set(kpsc["Sample"].astype(str))
        # Bucket samples are intentionally written to every batch — exclude them
        # from the missing/dup checks (they're expected to appear N times each).
        non_bucket_ids = all_ids - bucket_ids
        missing_non_bucket = sorted(
            s for s in non_bucket_ids if written_counts[s] == 0
        )
        dup_non_bucket = sorted(
            s for s in non_bucket_ids if written_counts[s] > 1
        )
        if missing_non_bucket:
            log.line(
                f"WARNING: {len(missing_non_bucket)} non-bucket samples never written "
                f"(showing up to 20): {missing_non_bucket[:20]}"
            )
        if dup_non_bucket:
            log.line(
                f"WARNING: {len(dup_non_bucket)} non-bucket samples appear in multiple "
                f"outputs (showing up to 20): {dup_non_bucket[:20]}"
            )
        # Bucket ref appearance: each bucket sample should be in *every* batch.
        ref_counts = sorted(
            (sid, written_counts[sid]) for sid in bucket_ids
        )
        ref_count_set = {c for _, c in ref_counts}
        if len(ref_count_set) != 1:
            log.line(
                f"WARNING: bucket samples appear in inconsistent batch counts: "
                f"{sorted(ref_count_set)}"
            )
        if not missing_non_bucket and not dup_non_bucket and len(ref_count_set) == 1:
            n_batches = next(iter(ref_count_set))
            log.line(
                "Each non-bucket kpsc_final_list sample appears in exactly one "
                f"output file; each of the {len(bucket_ids)} bucket samples "
                f"appears in all {n_batches} output files."
            )
        log.line("")
        log.line(f"Done. Log: {log_path}")
    finally:
        log.close()


if __name__ == "__main__":
    main()
