"""CLI — rebuild the cumulative curated stores + master table from completed batches.

Run after a batch finishes (or any time) to fold every batch's fills/escalations/grades into one growing
master curated table; pass ``--canonical`` to also emit the human>agent>ENA merge (the next iteration of
metadata). Example::

    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.accumulate \
      --data-dir <app>/data --table base_table.csv --spec <app>/attributes.yaml \
      --tags train,test --canonical <gold>.tsv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import accumulate, stages
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec


def main() -> None:
    """Parse arguments and rebuild the accumulation stores + master table."""
    p = argparse.ArgumentParser(description="Accumulate per-batch agent fills into the master curated table.")
    p.add_argument("--data-dir", required=True, help="Application data tree (holds the per-batch artifacts).")
    p.add_argument("--table", required=True, help="Full-width base table (the concat table) to fill.")
    p.add_argument("--spec", required=True, help="attributes.yaml — supplies fields + study-level columns.")
    p.add_argument("--tags", required=True, help="Comma-separated batch tags to union (e.g. train,test,tail100).")
    p.add_argument("--canonical", default=None,
                   help="Optional human-curated metadata TSV to overlay the master onto (human always wins).")
    p.add_argument("--out-dir", default=None, help="Output dir (default <data-dir>/curated).")
    p.add_argument("--gold-suffix", default="_parsed", help="Parsed-column suffix in the canonical table.")
    args = p.parse_args()

    spec = AttributeSpec.from_yaml(args.spec)
    base = pd.read_csv(args.table, dtype=str, low_memory=False, keep_default_na=False)
    accumulate.run_accumulation(
        data_dir=Path(args.data_dir),
        base=base,
        tags=[t.strip() for t in args.tags.split(",") if t.strip()],
        fields=list(spec.completeness_fields),
        study_grade_columns=stages.study_grade_columns(spec),
        out_dir=Path(args.out_dir) if args.out_dir else None,
        canonical_path=args.canonical,
        gold_suffix=args.gold_suffix,
    )


if __name__ == "__main__":
    main()
