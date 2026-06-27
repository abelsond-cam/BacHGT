"""Consolidated run-health report (Klebsiella shim over ``engine.run_health_report``).

Thin application wrapper: supplies the Klebsiella ``data/`` tree and the four backfill fields, then
delegates the whole aggregation to :func:`engine.run_health_report.build_run_health`. The engine module
holds the convergence logic + verdict; see its docstring for what is read/written and the loop it drives.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bac_metadata.bac_agentic_metadata.engine.backfill import FIELDS
from bac_metadata.bac_agentic_metadata.engine.run_health_report import build_run_health

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"


def main() -> None:
    """Aggregate every stage artifact into the per-(study × field) health grid + convergence verdict."""
    p = argparse.ArgumentParser(description="Consolidated run-health / convergence report (Klebsiella).")
    p.add_argument("--fold", default="test", help="Fold(s) for the study universe (e.g. 'test' or 'train,val').")
    p.add_argument("--tag", default="test", help="Artifact tag suffix.")
    args = p.parse_args()

    res, verdict = build_run_health(DATA_DIR, FIELDS, fold=args.fold, tag=args.tag)
    print(f"Wrote run_health_{args.tag}_report.{{md,tsv}} — VERDICT: {verdict}", file=sys.stderr)
    if len(res):
        print(res["resolution_state"].value_counts().to_string(), file=sys.stderr)
    raise SystemExit(0)  # always exit 0 — loud, never blocks


if __name__ == "__main__":
    main()
