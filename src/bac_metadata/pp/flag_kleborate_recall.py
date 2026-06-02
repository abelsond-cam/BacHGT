#!/usr/bin/env python3
"""Flag rows that need a fresh Kleborate call (sets ``kleborate_needs_recall``).

Identifies metadata_v2 rows that are members of the KPSC cohort
(``kpsc_final_list=True``) but lack a typing call (default criterion:
``Sublineage`` is null/empty). Sets ``kleborate_needs_recall=True`` on those
rows so the dedicated Kleborate runner (``run_kleborate_lra prepare``) picks
them up on the next pass.

This is the entry point for closing a typing gap end-to-end:

  1. ``flag_kleborate_recall`` — mark the gap rows for recall.
  2. ``run_kleborate_lra prepare`` — emits a fresh ``lra_inputs.tsv`` covering
     ``lra_final_list ∪ kleborate_needs_recall`` (LR assembly preferred, SR
     fallback).
  3. ``sbatch run_kleborate_lra.sh`` — sentinels skip already-done genomes;
     only the newly-flagged ones run.
  4. ``run_kleborate_lra collate`` — re-builds the collated typing TSVs.
  5. ``merge_kleborate_into_metadata_v2`` — backfills the full Kleborate
     typing block (MLST, virulence, AMR, Kaptive, wzi) onto matched rows and
     clears ``kleborate_needs_recall``.

Backs up the existing metadata_v2 with a UTC-stamped ``.bak.*.tsv`` before
overwriting.

Usage::

    uv run python -m bac_metadata.pp.flag_kleborate_recall --dry-run
    uv run python -m bac_metadata.pp.flag_kleborate_recall
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import pandas as pd

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"

_EMPTY_STRS = {"", "nan", "NaN", "None", "<NA>"}


def _truthy(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin({"true", "1", "yes"})


def _is_empty(s: pd.Series) -> pd.Series:
    return s.isna() | s.astype(str).str.strip().isin(_EMPTY_STRS)


def find_recall_rows(meta: pd.DataFrame, *, gap_col: str = "Sublineage") -> pd.Series:
    """Return a boolean mask of rows that need a Kleborate recall.

    Default criterion: ``kpsc_final_list=True`` AND ``gap_col`` is null/empty.
    ``gap_col`` defaults to ``Sublineage`` (the column whose absence first
    flagged this issue). Override with ``--gap-col`` for other typing gaps.
    """
    if "kpsc_final_list" not in meta.columns:
        raise KeyError("metadata_v2 missing 'kpsc_final_list' column")
    if gap_col not in meta.columns:
        raise KeyError(f"metadata_v2 missing gap column '{gap_col}'")
    return _truthy(meta["kpsc_final_list"]) & _is_empty(meta[gap_col])


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — flag recall + write."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--gap-col", type=str, default="Sublineage",
                    help="Column whose null/empty value triggers a recall flag (default: Sublineage).")
    ap.add_argument("--dry-run", action="store_true", help="Print counts; don't write.")
    args = ap.parse_args(argv)

    print(f"metadata_v2 : {args.metadata_v2}")
    print(f"gap-col     : {args.gap_col}")

    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    if "kleborate_needs_recall" not in meta.columns:
        meta["kleborate_needs_recall"] = False
    pre_flagged = int(_truthy(meta["kleborate_needs_recall"]).sum())

    recall_mask = find_recall_rows(meta, gap_col=args.gap_col)
    n_to_flag = int(recall_mask.sum())

    # Breakdown by Sample prefix for visibility.
    samp = meta.loc[recall_mask, "Sample"].astype(str)
    prefix_counts = samp.str.extract(r"^(GCF_|GCA_|SAM[NED]|ERS|DRS|[A-Za-z]+)")[0].value_counts(dropna=False).to_dict()

    print(f"\nrows: {len(meta):,}")
    print(f"kpsc_final_list=True rows                       : {int(_truthy(meta['kpsc_final_list']).sum()):,}")
    print(f"  ↳ kpsc & {args.gap_col} null/empty (to flag) : {n_to_flag:,}")
    print(f"      Sample prefix breakdown : {prefix_counts}")
    print(f"kleborate_needs_recall=True before              : {pre_flagged:,}")

    # Set the flag (or re-set on already-flagged rows; safe).
    meta.loc[recall_mask, "kleborate_needs_recall"] = True
    post_flagged = int(_truthy(meta["kleborate_needs_recall"]).sum())
    print(f"kleborate_needs_recall=True after               : {post_flagged:,}  (added {post_flagged - pre_flagged})")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    print(f"\nbacked up existing → {bak.name}")
    meta.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"wrote {args.metadata_v2}  rows={len(meta):,}  cols={len(meta.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
