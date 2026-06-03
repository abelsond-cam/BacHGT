#!/usr/bin/env python3
"""Derive the slimmed curated metadata as a column subset of the full TSV.

slim_metadata.py
----------------
The curated metadata exists in two forms that must stay consistent:

* ``metadata_final_curated_all_samples_and_columns.tsv`` — the canonical
  source of truth (every sample, every column);
* ``metadata_final_curated_slimmed.tsv`` — the *same rows* with most
  columns dropped, so it loads quickly for the analyses that only need a
  handful of fields.

Historically the slimmed↔full relationship was implicit (several scripts
double-wrote both). This module formalises it: the slimmed file is simply
the full file projected onto the columns the **current** slimmed header
already keeps, plus any ``--extra-cols`` (default the two path columns
``sr_assembly_file`` / ``sr_gff_file`` that ``add_paths_gff_fna_to_metadata.py``
adds to the full TSV after augmentation). Columns are emitted in the
full TSV's column order, and the existing slimmed file is backed up to a
timestamped ``<stem>.bak.<UTC-YYYYmmddTHHMMSS>.tsv`` before being
overwritten.

Usage
─────
    uv run python -m bac_metadata.pp.slim_metadata
        --full    PATH   # metadata_final_curated_all_samples_and_columns.tsv
        --slimmed PATH   # metadata_final_curated_slimmed.tsv (read for its
                         #   header, backed up, then overwritten)
        [--extra-cols a,b,c]   # default: sr_assembly_file,sr_gff_file
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_EXTRA_COLS = "sr_assembly_file,sr_gff_file"


def slim_metadata(full_path: Path, slimmed_path: Path, extra_cols: list[str]) -> Path:
    """Project the full TSV onto the slimmed column set and write it back.

    Parameters
    ----------
    full_path
        The canonical full metadata TSV (every sample, every column).
    slimmed_path
        The slimmed TSV. Its current header defines the kept-column set;
        it is backed up and then overwritten with the new slimmed frame.
    extra_cols
        Additional columns to keep if present in the full TSV (e.g.
        ``sr_assembly_file`` / ``sr_gff_file``, which do not exist in the
        current slimmed header because they are created downstream).

    Returns
    -------
    Path
        The timestamped backup path written for the previous slimmed TSV.

    Raises
    ------
    FileNotFoundError
        If *full_path* or *slimmed_path* does not exist.
    ValueError
        If none of the slimmed header's columns are present in the full
        TSV (a sign the two files are unrelated / the wrong paths).
    """
    if not full_path.exists():
        raise FileNotFoundError(f"full metadata not found: {full_path}")
    if not slimmed_path.exists():
        raise FileNotFoundError(f"slimmed metadata not found: {slimmed_path}")

    full = pd.read_csv(full_path, sep="\t", low_memory=False)
    slimmed_header = pd.read_csv(slimmed_path, sep="\t", nrows=0).columns.tolist()

    kept = set(slimmed_header) | set(extra_cols)
    select = [c for c in full.columns if c in kept]
    if not select:
        raise ValueError(f"no slimmed columns found in {full_path.name}; are --full/--slimmed the matching pair?")

    missing = sorted(c for c in slimmed_header if c not in full.columns)
    extra_added = sorted(c for c in extra_cols if c in full.columns)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak_path = slimmed_path.with_name(f"{slimmed_path.stem}.bak.{ts}.tsv")
    shutil.copy2(slimmed_path, bak_path)

    full[select].to_csv(slimmed_path, sep="\t", index=False)

    print(f"Backed up {slimmed_path} → {bak_path}", flush=True)
    print(
        f"Wrote {slimmed_path}  rows={len(full)}  cols={len(select)} (slimmed-header∩full + extra)",
        flush=True,
    )
    if extra_added:
        print(f"  extra cols carried in: {extra_added}", flush=True)
    if missing:
        print(f"  slimmed-header cols absent from full (skipped): {missing}", flush=True)
    return bak_path


def main(argv: list[str] | None = None) -> int:
    """Parse args and run :func:`slim_metadata`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--full", type=Path, required=True, help="canonical full metadata TSV")
    parser.add_argument("--slimmed", type=Path, required=True, help="slimmed TSV (header read, then overwritten)")
    parser.add_argument(
        "--extra-cols",
        type=str,
        default=DEFAULT_EXTRA_COLS,
        help=f'comma-separated extra columns to keep if present (default: "{DEFAULT_EXTRA_COLS}")',
    )
    args = parser.parse_args(argv)
    extra = [c.strip() for c in args.extra_cols.split(",") if c.strip()]
    slim_metadata(args.full, args.slimmed, extra)
    return 0


if __name__ == "__main__":
    sys.exit(main())
