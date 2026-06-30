"""Export the Klebsiella per-sample base table once, as the full-width flat CSV the engine ingests.

The engine driver (``engine/run_full_metadata_agent.py``) is application-agnostic: it reads a single
**pre-built per-sample table** keyed by ``study_accession`` + ``sample_accession`` and every stage works
off it — per-sample extraction joins on the alias columns, whole-field backfill gates on the four clinical
fields, and the final fill substitutes into the **whole** row. So this table is **full-width**: every
column the collation produces (all the ENA columns, the alias columns ``secondary_sample_accession`` /
``accession`` / ``sample_alias`` / ``sample_title``, the four clinical fields), RAW ENA values only — no
curation, no QC, no ``ready_to_merge`` backfill (the ``base`` state of ``pp.metadata_collation``).

This is the one Klebsiella-specific input builder; *M. abscessus* has no equivalent (its table is its xlsx).

Examples
--------
unset VIRTUAL_ENV
export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
uv run python .../export_base_table.py                          # -> data/inputs/base_table.csv
uv run python .../export_base_table.py --output /tmp/base.csv
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
STUDY_CSV = DATA_DIR / "inputs" / "study_level_metadata_all_combined_v1.0_20260105.csv"
DEFAULT_OUTPUT = DATA_DIR / "inputs" / "base_table.csv"


def export_base_table(output: Path, *, study_metadata_file: str | None = None) -> pd.DataFrame:
    """Build the **full-width** per-sample base table from the collation and write it as CSV.

    Runs ``pp.metadata_collation.load_collated_metadata`` offline (``google_sheet_id=None`` + the local
    study-level CSV), which returns the raw ATB ENA metadata with **all** columns and coalesces duplicate
    ``sample_accession`` to one row. No dedup or column selection here — every stage reads its own columns
    off this one table.
    """
    from bac_metadata.pp import metadata_collation as mcoll

    kwargs: dict[str, str] = {}
    if study_metadata_file:
        kwargs["study_metadata_file"] = study_metadata_file
    # The collation is verbose; keep its debug chatter off stdout so a redirect of this script is clean.
    with contextlib.redirect_stdout(sys.stderr):
        base = mcoll.load_collated_metadata(google_sheet_id=None, **kwargs)
    if "sample_accession" not in base.columns or "study_accession" not in base.columns:
        sys.exit(f"Base table needs study_accession + sample_accession; got {list(base.columns)[:12]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(output, index=False)
    return base


def main() -> None:
    """Parse arguments and export the full-width base table."""
    p = argparse.ArgumentParser(description="Export the Klebsiella full-width per-sample base table as CSV.")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path (default data/inputs/base_table.csv).")
    p.add_argument("--study-metadata-file", default=str(STUDY_CSV),
                   help="Local study-level CSV (keeps collation offline; default the committed snapshot).")
    args = p.parse_args()

    base = export_base_table(Path(args.output), study_metadata_file=args.study_metadata_file)
    n_studies = base["study_accession"].nunique()
    print(f"Wrote {args.output}: {len(base)} samples across {n_studies} studies ({base.columns.size} columns)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
