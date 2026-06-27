r"""Per-sample supplementary worklist (Klebsiella shim over ``engine.persample_supplement_worklist``).

Thin application wrapper: wires the Klebsiella ``data/`` tree, the curated link map, and the full-text /
manual-PDF / LLM caches (reused from ``run_study_grading``), then delegates to
:func:`engine.persample_supplement_worklist.build_persample_supplement_worklist`. See that module for what
the worklist judges and the curator actions it emits.

Examples
--------
unset VIRTUAL_ENV
uv run python .../report_persample_supplements.py --tag test --min-gap 50
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bac_metadata.bac_agentic_metadata.applications.klebsiella import run_study_grading as rsg
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL
from bac_metadata.bac_agentic_metadata.engine.persample_supplement_worklist import (
    build_persample_supplement_worklist,
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"


def main() -> None:
    """Build the per-sample supplementary worklist with the LLM per-sample-table opinion."""
    p = argparse.ArgumentParser(description="Per-sample supplementary-table worklist (Klebsiella).")
    p.add_argument("--tag", default="test", help="Artifact tag (gate/grades/per-sample suffix).")
    p.add_argument("--min-gap", type=int, default=50, help="Skip studies whose per-sample backlog is <= this.")
    p.add_argument("--backend", default="subscription", help="LLM backend (subscription | api).")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Model for the opinion.")
    args = p.parse_args()

    build_persample_supplement_worklist(
        DATA_DIR,
        paper_links=rsg._accession_to_paper_link(),
        fulltext_cache=rsg.FULLTEXT_CACHE,
        manual_papers_dir=rsg.MANUAL_PAPERS_DIR,
        llm_cache=rsg.LLM_CACHE,
        tag=args.tag,
        min_gap=args.min_gap,
        backend=args.backend,
        model=args.model,
    )


if __name__ == "__main__":
    main()
