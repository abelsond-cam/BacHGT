"""Export the Klebsiella per-sample base table once, as the flat CSV the unified driver ingests.

The driver (``engine/run_full_metadata_agent.py``) is application-agnostic: it always reads a single
**pre-built concatenated table** keyed per-sample by ``study_accession`` + ``sample_accession``, exactly
the shape *M. abscessus* already has as an xlsx. For Klebsiella that table comes from the existing
collation (``KlebCollationSource``); this script materialises it once so the driver never re-runs
collation at selection time. Study size is then simply the per-``study_accession`` distinct-sample count.

The exported columns are ``study_accession``, ``sample_accession``, the four clinical fields
(``country``, ``collection_date``, ``isolation_source``, ``host``), and a few auxiliary columns. RAW
ENA values only — no curation, no QC, no ``ready_to_merge`` backfill (this is the ``base`` state).

Examples
--------
unset VIRTUAL_ENV
export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
uv run python .../export_base_table.py                          # -> data/inputs/base_table.csv
uv run python .../export_base_table.py --output /tmp/base.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
STUDY_CSV = DATA_DIR / "inputs" / "study_level_metadata_all_combined_v1.0_20260105.csv"
DEFAULT_OUTPUT = DATA_DIR / "inputs" / "base_table.csv"
#: sample_accession is the per-sample key the driver sizes on (and stages join to); carry it explicitly.
KEEP_COLUMNS = ("sample_accession", "run_accession", "instrument_platform", "scientific_name")


def export_base_table(output: Path, *, study_metadata_file: str | None = None) -> pd.DataFrame:
    """Build the per-sample base table from the collation and write it as CSV; return the frame."""
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    src = KlebCollationSource(keep_columns=KEEP_COLUMNS, study_metadata_file=study_metadata_file)
    base = src.states()["base"]
    if "sample_accession" not in base.columns or "study_accession" not in base.columns:
        sys.exit(f"Base table needs study_accession + sample_accession; got {list(base.columns)[:12]}")
    # One row per isolate: the driver counts rows per study to size each study (the local proxy for
    # ena_taxon_samples), so a duplicated sample_accession must not inflate the count.
    base = base.drop_duplicates("sample_accession").reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(output, index=False)
    return base


def main() -> None:
    """Parse arguments and export the base table."""
    p = argparse.ArgumentParser(description="Export the Klebsiella per-sample base table as a flat CSV.")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path (default data/inputs/base_table.csv).")
    p.add_argument("--study-metadata-file", default=str(STUDY_CSV),
                   help="Local study-level CSV (keeps collation offline; default the committed snapshot).")
    args = p.parse_args()

    base = export_base_table(Path(args.output), study_metadata_file=args.study_metadata_file)
    n_studies = base["study_accession"].nunique()
    print(f"Wrote {args.output}: {len(base)} samples across {n_studies} studies "
          f"({base.columns.size} columns: {list(base.columns)})", file=sys.stderr)


if __name__ == "__main__":
    main()
