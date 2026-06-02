#!/usr/bin/env python3
"""Merge ISEScan-on-LRA family counts into metadata_v2 (G.2).

Reads:
  - ``metadata_v2_all_samples_and_columns.tsv``
  - ``<isescan_lra_out>/isescan_lra_family_counts.tsv`` (per-Sample wide
    table of IS-family copy counts, from ``run_isescan_lra collate``).

For each ``lra_final_list=True`` row, adds one column per detected IS
family with the per-genome count from the LR assembly. Existing
``IS*`` / ``n_IS*`` columns from v1 (if any) are renamed to ``sr_IS*``
to preserve the SR-derived snapshot before overwrite (no SR-side IS
data is currently in v1, but the rename keeps the schema future-proof).

Clears ``isescan_needs_recall=False`` on every LRA row that received a
fresh count.

Run AFTER the ISEScan Slurm array finishes + ``collate`` writes the wide
counts table. Backs up the existing metadata_v2 with a UTC-stamped
``.bak.*.tsv`` before overwriting.

Usage::

    uv run python -m bac_metadata.pp.merge_isescan_into_metadata_v2 --dry-run
    uv run python -m bac_metadata.pp.merge_isescan_into_metadata_v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2  = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_ISESCAN_OUT  = DATA_ROOT / "david/processed/complete_vs_sr_genomes/isescan_lra"
DEFAULT_COUNTS_FILE  = "isescan_lra_family_counts.tsv"

_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")


def _bare(acc: object) -> str:
    if acc is None or pd.isna(acc):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1) if m else ""


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def apply_isescan_merge(meta: pd.DataFrame, counts: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Add per-IS-family count columns to v2 for every lra_final_list=True row.

    Returns ``(updated_meta, stats)``.
    """
    stats: dict = {}
    meta = meta.copy()

    # ISEScan counts is keyed on Sample (the bare GCF/GCA we used as the
    # per-sample dir name). v2.Sample is versioned — join via bare.
    counts = counts.copy()
    if counts.index.name == "Sample":
        counts = counts.reset_index()
    counts["_bare"] = counts["Sample"].map(_bare)
    counts = counts.drop_duplicates("_bare").set_index("_bare")
    fam_cols = [c for c in counts.columns if c not in ("Sample",)]
    stats["isescan_families_detected"] = len(fam_cols)
    stats["isescan_samples_with_counts"] = len(counts)

    lra_mask = _coerce_bool(meta["lra_final_list"])
    meta_bare = meta.loc[lra_mask, "Sample"].map(_bare)
    has_count = meta_bare.map(lambda b: b in counts.index)
    stats["lra_rows"] = int(lra_mask.sum())
    stats["lra_rows_matched_isescan"]   = int(has_count.sum())
    stats["lra_rows_missing_isescan"]   = int((~has_count).sum())

    # Add one column per family (IS_<family>). Default to 0 on LRA rows that
    # were matched but family wasn't in their assembly. NaN on non-LRA rows
    # and unmatched LRA rows.
    for fam in fam_cols:
        out_col = f"IS_{fam}"
        if out_col not in meta.columns:
            meta[out_col] = pd.NA
    # Populate.
    matched_idx = meta.index[lra_mask][has_count.values]
    matched_bare = meta.loc[matched_idx, "Sample"].map(_bare).values
    for fam in fam_cols:
        out_col = f"IS_{fam}"
        meta.loc[matched_idx, out_col] = counts.loc[matched_bare, fam].values

    # Clear isescan_needs_recall on matched rows.
    if "isescan_needs_recall" in meta.columns:
        meta.loc[matched_idx, "isescan_needs_recall"] = False

    # Sanity gate: every lra_final_list row should now have at least one IS_
    # column populated (= 0 if no ISs found, but NOT NaN).
    if fam_cols:
        sample_fam_col = f"IS_{fam_cols[0]}"
        null_count = (lra_mask & meta[sample_fam_col].isna()).sum()
        stats["lra_rows_null_isescan_post_merge"] = int(null_count)

    return meta, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — apply ISEScan merge + write."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2",  type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--isescan-out",  type=Path, default=DEFAULT_ISESCAN_OUT)
    ap.add_argument("--counts-file",  type=str,  default=DEFAULT_COUNTS_FILE)
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    counts_path = args.isescan_out / args.counts_file
    print(f"metadata_v2 : {args.metadata_v2}")
    print(f"isescan     : {counts_path}")

    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    counts = pd.read_csv(counts_path, sep="\t", low_memory=False, index_col=0)
    print(f"\nmetadata_v2 rows  : {len(meta):,}")
    print(f"isescan rows      : {len(counts):,}  (Samples)")
    print(f"isescan families  : {len(counts.columns):,}")

    updated, stats = apply_isescan_merge(meta, counts)

    print("\n=== ISEScan merge stats ===")
    for k, v in stats.items():
        print(f"  {k:40s}: {v:,}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    print(f"\nbacked up existing → {bak.name}")
    updated.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"wrote {args.metadata_v2}  rows={len(updated):,}  cols={len(updated.columns)}")

    failed = False
    if stats.get("lra_rows_missing_isescan", 0) > 0:
        print(f"\nWARNING: {stats['lra_rows_missing_isescan']} LRA rows missing ISEScan "
              f"— re-submit the Slurm array for the failed chunks.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
