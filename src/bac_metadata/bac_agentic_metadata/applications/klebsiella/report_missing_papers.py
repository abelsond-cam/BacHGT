"""Manual-fetch worklist for papers lacking full text (Klebsiella shim over ``engine.missing_papers``).

Thin application wrapper: wires the Klebsiella ``data/`` paths and injects the curated
``study_accession -> paper_link`` map (``run_study_grading._accession_to_paper_link``), then delegates to
:func:`engine.missing_papers.build_missing_papers`. See that module for the worklist's purpose + columns.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bac_metadata.bac_agentic_metadata.applications.klebsiella import run_study_grading as rsg
from bac_metadata.bac_agentic_metadata.engine.missing_papers import build_missing_papers

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
MANUAL_DIR = DATA_DIR / "find_papers" / "manual_download"


def main() -> None:
    """Build the manual-fetch worklist of paywalled / no-full-text papers, gap-weighted."""
    p = argparse.ArgumentParser(description="Worklist of papers needing manual download (Klebsiella).")
    p.add_argument("--grades", default=str(DATA_DIR / "study_lv_attributes" / "grading" / "study_grades.jsonl"), help="Grader JSONL (fulltext status).")
    p.add_argument("--found", default=str(DATA_DIR / "find_papers" / "found_papers.tsv"), help="paper finding finder output (identifiers).")
    p.add_argument("--gap-report", default=str(DATA_DIR / "diagnostics" / "backfill_gap_report.tsv"), help="Per-study date/source gap.")
    p.add_argument("--sizing", default=str(DATA_DIR / "ena_assessment" / "ena_sizing.tsv"), help="ENA assessment sizing (taxon samples).")
    p.add_argument("--report-prefix", default="missing_papers_report")
    args = p.parse_args()

    build_missing_papers(
        grades_path=Path(args.grades),
        found_path=Path(args.found),
        gap_report_path=Path(args.gap_report),
        sizing_path=Path(args.sizing),
        manual_dir=MANUAL_DIR,
        out_dir=DATA_DIR / "find_papers",
        report_prefix=args.report_prefix,
        paper_links=rsg._accession_to_paper_link(),
    )


if __name__ == "__main__":
    main()
