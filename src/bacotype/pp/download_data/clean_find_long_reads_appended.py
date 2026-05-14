#!/usr/bin/env python3
"""clean_find_long_reads_appended.py
-------------------------------------
One-off cleanup: drop the metadata rows that ``find_long_reads.py`` appended
to ``metadata_final_curated_all_samples_and_columns.tsv`` /
``metadata_final_curated_slimmed.tsv``.

Context
───────
Before this cleanup the script appended one row per discovered ENA run rather
than merging the run info into existing curated rows. Those appended rows
carry no ``species_match`` (they never ran through Kleborate), have most
curation flags forced ``False``, and confuse every downstream audit (notably
they created the 957 "ghost GCFs" in ``related_lr_accession``).

User-confirmed heuristic — *user mask*:
    row index >= 86472  AND  species_match is null

We additionally compute a *script-prune mask* using the same heuristic that
the original ``find_long_reads.py`` uses to clear prior appended rows on
re-run:
    est_coverage_5_5Mb numeric-and-populated  AND  is_refseq == False

The two masks should match closely. If they diverge by more than 10 rows
the script prints a warning and requires ``--force`` before writing.

Usage
─────
    uv run python src/bacotype/pp/download_data/clean_find_long_reads_appended.py
        [--force]   # only needed if the two masks disagree significantly

Inputs (hard-coded — both local copies in this repo):
    docs/data/metadata_final_curated_all_samples_and_columns.tsv
    docs/data/metadata_final_curated_slimmed.tsv

The user keeps backups elsewhere, so this script overwrites in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
FILES = [
    REPO_ROOT / "docs" / "data" / "metadata_final_curated_all_samples_and_columns.tsv",
    REPO_ROOT / "docs" / "data" / "metadata_final_curated_slimmed.tsv",
]

USER_INDEX_THRESHOLD = 86472
DISAGREEMENT_WARN_THRESHOLD = 10


def build_masks(meta: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (user_mask, script_prune_mask) for the rows to drop."""
    user_mask = pd.Series(False, index=meta.index)
    user_mask.iloc[USER_INDEX_THRESHOLD:] = meta.iloc[USER_INDEX_THRESHOLD:][
        "species_match"
    ].isna()

    script_prune_mask = pd.Series(False, index=meta.index)
    if "est_coverage_5_5Mb" in meta.columns and "is_refseq" in meta.columns:
        cov = pd.to_numeric(meta["est_coverage_5_5Mb"], errors="coerce")
        is_refseq_false = meta["is_refseq"].fillna(False).astype(bool) == False  # noqa: E712
        script_prune_mask = cov.notna() & is_refseq_false

    return user_mask, script_prune_mask


def clean_file(path: Path, force: bool) -> bool:
    """Clean one metadata file in place. Return True if rows were dropped."""
    print(f"\n══ {path.relative_to(REPO_ROOT)} ══", flush=True)
    if not path.exists():
        print(f"  SKIP — file not found", flush=True)
        return False

    meta = pd.read_csv(path, sep="\t", low_memory=False)
    n_before = len(meta)
    print(f"  loaded: {n_before:,} rows × {len(meta.columns)} cols", flush=True)

    if "species_match" not in meta.columns:
        print(
            "  ABORT — 'species_match' column not present; cannot apply user mask",
            file=sys.stderr,
        )
        return False

    user_mask, script_mask = build_masks(meta)
    n_user = int(user_mask.sum())
    n_script = int(script_mask.sum())
    n_intersect = int((user_mask & script_mask).sum())
    n_user_only = int((user_mask & ~script_mask).sum())
    n_script_only = int((~user_mask & script_mask).sum())

    print(
        f"  user_mask (idx ≥ {USER_INDEX_THRESHOLD} & species_match null): {n_user:,}",
        flush=True,
    )
    print(
        f"  script_prune_mask (est_coverage_5_5Mb populated & is_refseq=False): {n_script:,}",
        flush=True,
    )
    print(f"  intersection:                {n_intersect:,}", flush=True)
    print(f"  user_only (will drop):       {n_user_only:,}", flush=True)
    print(f"  script_only (would-be-pruned but kept by user mask): {n_script_only:,}", flush=True)

    diff = abs(n_user - n_script)
    if diff > DISAGREEMENT_WARN_THRESHOLD and not force:
        print(
            f"  WARNING — masks disagree by {diff} rows (> {DISAGREEMENT_WARN_THRESHOLD}). "
            f"Rerun with --force to apply user_mask anyway.",
            file=sys.stderr,
        )
        return False

    cleaned = meta.loc[~user_mask].reset_index(drop=True)
    n_after = len(cleaned)
    cleaned.to_csv(path, sep="\t", index=False)
    print(f"  wrote: {n_after:,} rows (dropped {n_before - n_after:,})", flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI entry — clean both metadata files in place."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Apply the user mask even if it disagrees with the script-prune "
        "mask by more than {} rows.".format(DISAGREEMENT_WARN_THRESHOLD),
    )
    args = parser.parse_args(argv)

    for path in FILES:
        clean_file(path, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
