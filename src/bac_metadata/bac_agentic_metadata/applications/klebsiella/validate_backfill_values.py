"""Value-correctness of the whole-field backfill vs the ``metadata_v2`` gold standard (Klebsiella).

The runner (``run_backfill.py``) proposes per-sample fills; here we ask whether those values are
actually RIGHT, not just well-targeted. We compare each fill to the reviewed gold value for the same
sample in ``metadata_v2`` (collation + curation + Klebsiella hand-curation).

Per David's comparison-alignment note: ``metadata_v2`` was produced by the parse/curate step, which
already removed the meaningless text-"NA" the raw input carries (~1% of cells). So we compare our
**standalone-placeholder-stripped** raw fill against ``metadata_v2``'s **curated value** — by default
the ``*_parsed`` column (curated, text-NA removed; spelling-normalised but NOT categorised). Both sides
are placeholder-stripped and compared case-insensitively. Use ``--gold-suffix ''`` to compare against
the raw ``metadata_v2`` columns instead.

Writes ``data/<report-prefix>_report.{md,tsv}`` (default ``backfill_value_report``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"


def _read_gold(truth_path: str, sample_col: str, gold_cols: list[str]) -> pd.DataFrame:
    """Read only the sample key + needed gold columns from the (large) metadata_v2 table."""
    header = pd.read_csv(truth_path, sep="\t", nrows=0).columns.tolist()
    key = sample_col if sample_col in header else ("Sample" if "Sample" in header else None)
    if key is None:
        sys.exit(f"metadata_v2 has no '{sample_col}' or 'Sample' column; header starts {header[:10]}")
    usecols = [key] + [c for c in gold_cols if c in header]
    gold = pd.read_csv(truth_path, sep="\t", dtype=str, usecols=usecols, low_memory=False)
    return gold.rename(columns={key: "sample_accession"})


def main() -> None:
    """Parse arguments and write the value-correctness report (per-field coverage + accuracy)."""
    parser = argparse.ArgumentParser(description="Backfill value-correctness vs metadata_v2 (Klebsiella).")
    parser.add_argument("--applied", default=str(DATA_DIR / "backfill_applied.tsv"), help="Per-sample fills.")
    parser.add_argument("--truth", required=True, help="metadata_v2 per-sample gold TSV (local path).")
    parser.add_argument("--gold-suffix", default="_parsed",
                        help="Gold column suffix per field (default '_parsed' = curated; '' for raw).")
    parser.add_argument("--report-prefix", default="backfill_value", help="Report basename under data/.")
    args = parser.parse_args()

    applied = pd.read_csv(args.applied, sep="\t", dtype=str)
    gold_cols = {f: f"{f}{args.gold_suffix}" for f in backfill.FIELDS}
    gold = _read_gold(args.truth, "sample_accession", list(gold_cols.values()))
    print(f"Applied fills: {len(applied)}; gold rows: {len(gold)}", file=sys.stderr)

    res = backfill.value_correctness(applied, gold, sample_col="sample_accession", gold_cols=gold_cols)

    md = ["# Backfill value-correctness vs metadata_v2 (train+val whole-field fills)\n"]
    md.append(f"Gold = `{Path(args.truth).name}`, column suffix `{args.gold_suffix or '(raw)'}` "
              "(curated value, placeholder-stripped both sides, raw — no categorisation).\n")
    md.append("| field | cells filled | with gold | correct | value-accuracy |")
    md.append("|---|---|---|---|---|")
    for _, r in res.iterrows():
        acc = f"{r['accuracy']:.2f}" if pd.notna(r["accuracy"]) else "—"
        md.append(f"| {r['field']} | {int(r['filled'])} | {int(r['has_gold'])} | {int(r['correct'])} | {acc} |")
    md.append("\n- **cells filled** = per-sample whole-field fills proposed; **with gold** = of those, how "
              "many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match.")
    md.append("- `collection_date` accuracy is expected low here: a single whole-project midpoint rarely "
              "equals each sample's true date — those mostly belong to the per-sample (method-b) step.")

    out_md = DATA_DIR / f"{args.report_prefix}_report.md"
    out_md.write_text("\n".join(md) + "\n")
    res.to_csv(DATA_DIR / f"{args.report_prefix}_report.tsv", sep="\t", index=False)
    print(f"Wrote {out_md.name} + .tsv", file=sys.stderr)
    print(res.to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
