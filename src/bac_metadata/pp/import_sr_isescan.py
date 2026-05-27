#!/usr/bin/env python3
"""Import SR-side ISEScan results into a sidecar per-Sample family-count TSV.

Background
----------
SR ISEScan was run by Seb against the short-read assemblies and the
per-genome CSVs live under
``<RDS>/seb/ISEScan_results/csv_files/<key>_<runid>.fa.csv`` (81,059
files). They were never aggregated into a per-sample IS-family count
table or merged into ``metadata_v1``. That left the paired SR-vs-LRA
comparison (G.4) treating every SR sample's IS counts as NaN — which is
why the first-pass result claimed zero SR-side IS calls.

This module fixes that by walking every CSV, counting IS calls by
family, and emitting one wide TSV that mirrors
``<RDS>/david/processed/isescan_lra/isescan_lra_family_counts.tsv``
(same shape — one row per Sample, one column per IS family) so the
G.3 SR-shadow builder can consume both tables symmetrically.

Filename convention
-------------------
``<key>_<runid>.fa.csv`` where ``<key>`` is either a BioSample
(SAMN/SAMD/SAME accession) or an assembly accession (GCA_xxxxx / GCF_xxxxx)
and ``<runid>`` is a stable ISEScan-run identifier (typically ``21508953``).
We extract the key as ``Sample``; the run-ID suffix is ignored.

Usage
-----
::

    uv run python -m bac_metadata.pp.import_sr_isescan --dry-run
    uv run python -m bac_metadata.pp.import_sr_isescan
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_CSV_DIR  = DATA_ROOT / "seb/ISEScan_results/csv_files"
DEFAULT_OUT_DIR  = DATA_ROOT / "seb"
DEFAULT_LONG_OUT = DEFAULT_OUT_DIR / "sr_isescan_long.tsv"
DEFAULT_WIDE_OUT = DEFAULT_OUT_DIR / "sr_isescan_family_counts.tsv"

# Recover the Sample key from a filename like ``SAMN02141993_21508953.fa.csv``
# or ``GCF_900451185_21508953.fa.csv``. The key is everything up to the final
# ``_<runid>.fa.csv`` segment, so GCF/GCA stems with embedded underscores are
# handled correctly.
_KEY_RE = re.compile(r"^(?P<key>.+?)_(?P<runid>\d+)\.fa\.csv$")


def _sample_from_filename(fn: str) -> str | None:
    m = _KEY_RE.match(fn)
    if m is None:
        return None
    return m.group("key")


def collate_isescan_csvs(csv_dir: Path, limit: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Walk every per-genome ISEScan CSV; emit long + wide tables."""
    stats: dict = {"csv_dir": str(csv_dir)}

    files = sorted(csv_dir.iterdir())
    stats["files_total"] = len(files)
    if limit is not None:
        files = files[:limit]
        stats["files_processed_limit"] = limit

    long_frames: list[pd.DataFrame] = []
    n_ok = 0
    n_empty = 0
    n_bad_name = 0
    n_read_err = 0
    skipped_names: list[str] = []

    for f in files:
        sample = _sample_from_filename(f.name)
        if sample is None:
            n_bad_name += 1
            if len(skipped_names) < 10:
                skipped_names.append(f.name)
            continue
        try:
            df = pd.read_csv(f, low_memory=False)
        except pd.errors.EmptyDataError:
            n_empty += 1
            continue
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            print(f"  {f.name}: read failed ({exc})", file=sys.stderr)
            n_read_err += 1
            continue
        if df.empty:
            n_empty += 1
            continue
        df["Sample"] = sample
        long_frames.append(df)
        n_ok += 1

    stats["files_ok"]        = n_ok
    stats["files_empty"]     = n_empty
    stats["files_bad_name"]  = n_bad_name
    stats["files_read_err"]  = n_read_err
    if skipped_names:
        stats["skipped_examples"] = skipped_names

    if not long_frames:
        return pd.DataFrame(), pd.DataFrame(), stats

    long_df = pd.concat(long_frames, ignore_index=True, sort=False)
    stats["long_rows"] = len(long_df)
    stats["long_cols"] = len(long_df.columns)

    # The SR CSVs share the ISEScan column schema — `family` (lowercase) is
    # the canonical IS-family field. The LRA-side runner falls back to a few
    # alternate spellings; mirror that to stay robust.
    fam_col = None
    for cand in ("family", "Family", "IS_family", "isfamily"):
        if cand in long_df.columns:
            fam_col = cand
            break
    if fam_col is None:
        print(f"WARN: no family column in long table; cols={long_df.columns.tolist()[:8]}", file=sys.stderr)
        return long_df, pd.DataFrame(), stats

    counts = long_df.groupby(["Sample", fam_col]).size().rename("count").reset_index()
    wide = counts.pivot(index="Sample", columns=fam_col, values="count").fillna(0).astype(int)
    wide = wide.reset_index()
    stats["wide_samples"]  = len(wide)
    stats["wide_families"] = len(wide.columns) - 1
    return long_df, wide, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry: collate SR ISEScan CSVs into per-Sample family-count TSV."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir",   type=Path, default=DEFAULT_CSV_DIR)
    ap.add_argument("--long-out",  type=Path, default=DEFAULT_LONG_OUT)
    ap.add_argument("--wide-out",  type=Path, default=DEFAULT_WIDE_OUT)
    ap.add_argument("--limit",     type=int,  default=None,
                    help="Limit number of CSVs (smoke-test).")
    ap.add_argument("--dry-run",   action="store_true", help="Print stats; don't write outputs.")
    args = ap.parse_args(argv)

    print(f"csv_dir  : {args.csv_dir}")
    print(f"long_out : {args.long_out}")
    print(f"wide_out : {args.wide_out}")
    if args.limit:
        print(f"limit    : {args.limit}")

    long_df, wide, stats = collate_isescan_csvs(args.csv_dir, limit=args.limit)

    print("\n=== SR-ISEScan collate stats ===")
    for k, v in stats.items():
        print(f"  {k:30s}: {v}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    if not long_df.empty:
        args.long_out.parent.mkdir(parents=True, exist_ok=True)
        long_df.to_csv(args.long_out, sep="\t", index=False)
        print(f"\nwrote {args.long_out}  rows={len(long_df):,}  cols={len(long_df.columns)}")
    if not wide.empty:
        wide.to_csv(args.wide_out, sep="\t", index=False)
        print(f"wrote {args.wide_out}  shape={wide.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
