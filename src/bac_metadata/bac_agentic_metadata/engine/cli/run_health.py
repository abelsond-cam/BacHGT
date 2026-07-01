r"""Curator CLI — the consolidated run-health / convergence report over an application's data tree.

Species-agnostic: takes the data tree + the rubric (for the completeness-field list) and delegates to
:func:`engine.run_health_report.build_run_health`, which holds the convergence logic + the ALL-CLEAR vs
N-actionable verdict. Replaces the former per-application ``report_run_health.py``. The driver runs this as
its final stage; this CLI re-runs it standalone (e.g. after a curator supplies inputs between passes).

    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.run_health \\
        --data-dir .../applications/klebsiella/data \\
        --spec .../applications/klebsiella/attributes.yaml --fold train,val --tag train
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bac_metadata.bac_agentic_metadata.engine.run_health_report import build_run_health
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec


def main() -> None:
    """Aggregate every stage artifact into the per-(study × field) health grid + convergence verdict."""
    p = argparse.ArgumentParser(description="Consolidated run-health / convergence report (any application).")
    p.add_argument("--data-dir", required=True, help="Application data tree root.")
    p.add_argument("--spec", required=True, help="Application attributes.yaml (source of the completeness fields).")
    p.add_argument("--fold", default="test", help="Fold(s) for the study universe (e.g. 'test' or 'train,val').")
    p.add_argument("--tag", default="test", help="Artifact tag suffix.")
    args = p.parse_args()

    fields = tuple(AttributeSpec.from_yaml(args.spec).completeness_fields)
    res, verdict = build_run_health(Path(args.data_dir), fields, fold=args.fold, tag=args.tag)
    print(f"Wrote run_health_{args.tag}_report.{{md,tsv}} — VERDICT: {verdict}", file=sys.stderr)
    if len(res):
        print(res["resolution_state"].value_counts().to_string(), file=sys.stderr)
    raise SystemExit(0)  # always exit 0 — loud, never blocks


if __name__ == "__main__":
    main()
