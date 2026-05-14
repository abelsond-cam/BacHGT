#!/usr/bin/env python3
"""clean_find_long_reads_appended.py
-------------------------------------
One-off cleanup: drop the metadata rows that an earlier version of
``find_long_reads.py`` appended to
``metadata_final_curated_all_samples_and_columns.tsv`` /
``metadata_final_curated_slimmed.tsv``.

Context
───────
The legacy ``find_long_reads.py`` appended one row per discovered ENA run
rather than merging the run info into existing curated rows. Those appended
rows carry no ``species_match`` (they never ran through Kleborate), have
most curation flags forced ``False``, and confuse every downstream audit
(notably they created the 957 "ghost GCFs" in ``related_lr_accession``).

We drop the **union** of two heuristics so nothing slips through:

1. **User mask** — row index ≥ 86472 AND ``species_match`` is null.
2. **Script-prune mask** — numeric ``est_coverage_5_5Mb`` populated AND
   ``is_refseq == False``. This is the same heuristic the legacy
   ``find_long_reads.py`` itself used to wipe prior appended rows on re-run.

Both masks should target the same rows on a freshly-polluted file, but the
union catches any straggler the per-index user mask misses (e.g. an
appended row that happens to have a row-index < 86472).

A timestamped log file is written next to the cleaned TSVs so the cleanup
is reproducible / auditable.

Usage
─────
    uv run python src/bacotype/pp/download_data/clean_find_long_reads_appended.py

Inputs (hard-coded — both local copies in this repo):
    docs/data/metadata_final_curated_all_samples_and_columns.tsv
    docs/data/metadata_final_curated_slimmed.tsv

Output:
    docs/data/clean_find_long_reads_appended.log

The user keeps backups elsewhere, so this script overwrites the TSVs in place.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_DATA = REPO_ROOT / "docs" / "data"
FILES = [
    DOCS_DATA / "metadata_final_curated_all_samples_and_columns.tsv",
    DOCS_DATA / "metadata_final_curated_slimmed.tsv",
]
LOG_FILE = DOCS_DATA / "clean_find_long_reads_appended.log"

USER_INDEX_THRESHOLD = 86472


def build_masks(meta: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (user_mask, script_prune_mask) — the two drop heuristics."""
    user_mask = pd.Series(False, index=meta.index)
    if "species_match" in meta.columns and len(meta) > USER_INDEX_THRESHOLD:
        user_mask.iloc[USER_INDEX_THRESHOLD:] = meta.iloc[USER_INDEX_THRESHOLD:][
            "species_match"
        ].isna()

    script_prune_mask = pd.Series(False, index=meta.index)
    if "est_coverage_5_5Mb" in meta.columns and "is_refseq" in meta.columns:
        cov = pd.to_numeric(meta["est_coverage_5_5Mb"], errors="coerce")
        is_refseq_false = meta["is_refseq"].fillna(False).astype(bool) == False  # noqa: E712
        script_prune_mask = cov.notna() & is_refseq_false

    return user_mask, script_prune_mask


def clean_file(path: Path) -> None:
    """Clean one metadata file in place using the union of both masks."""
    print(f"\n══ {path.relative_to(REPO_ROOT)} ══", flush=True)
    if not path.exists():
        print(f"  SKIP — file not found", flush=True)
        return

    meta = pd.read_csv(path, sep="\t", low_memory=False)
    n_before = len(meta)
    print(f"  loaded: {n_before:,} rows × {len(meta.columns)} cols", flush=True)

    user_mask, script_mask = build_masks(meta)
    drop_mask = user_mask | script_mask
    n_user = int(user_mask.sum())
    n_script = int(script_mask.sum())
    n_intersect = int((user_mask & script_mask).sum())
    n_user_only = int((user_mask & ~script_mask).sum())
    n_script_only = int((~user_mask & script_mask).sum())
    n_drop = int(drop_mask.sum())

    print(
        f"  user_mask (idx ≥ {USER_INDEX_THRESHOLD} & species_match null): {n_user:,}",
        flush=True,
    )
    print(
        f"  script_prune_mask (est_coverage_5_5Mb populated & is_refseq=False): {n_script:,}",
        flush=True,
    )
    print(f"  intersection (both masks agree):  {n_intersect:,}", flush=True)
    print(f"  user_only (caught by user mask only):    {n_user_only:,}", flush=True)
    print(f"  script_only (caught by script mask only): {n_script_only:,}", flush=True)
    print(f"  UNION → will drop:                {n_drop:,}", flush=True)

    if n_drop == 0:
        print(f"  no rows to drop — file is already clean", flush=True)
        return

    cleaned = meta.loc[~drop_mask].reset_index(drop=True)
    n_after = len(cleaned)
    cleaned.to_csv(path, sep="\t", index=False)
    print(f"  wrote: {n_after:,} rows (dropped {n_before - n_after:,})", flush=True)


class _Tee:
    """Duplicate writes to terminal + log file."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for s in self.streams:
            s.write(data)
            s.flush()
        return len(data)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


def main(argv: list[str] | None = None) -> int:
    """CLI entry — clean both metadata files in place and tee to log file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.parse_args(argv)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        log_fh = stack.enter_context(LOG_FILE.open("w"))
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = _Tee(original_stdout, log_fh)
        sys.stderr = _Tee(original_stderr, log_fh)
        stack.callback(setattr, sys, "stdout", original_stdout)
        stack.callback(setattr, sys, "stderr", original_stderr)

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        print(f"clean_find_long_reads_appended.py  run at {ts}", flush=True)
        for path in FILES:
            clean_file(path)
        print(f"\nLog: {LOG_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
