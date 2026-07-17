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

APP_DIR = Path(__file__).resolve().parents[1] / "applications" / "klebsiella"  # gold-bearing app tree (see evaluation/__init__.py)
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
    parser.add_argument("--applied", default=str(DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_applied.tsv"), help="Per-sample fills.")
    parser.add_argument("--truth", required=True, help="metadata_v2 per-sample gold TSV (local path).")
    parser.add_argument("--gold-suffix", default=None,
                        help="Legacy: compare only against the single gold column <field><suffix> "
                             "(e.g. '_parsed', or '' for raw). Default: match against BOTH raw and _parsed.")
    parser.add_argument("--report-prefix", default="backfill_value", help="Report basename.")
    parser.add_argument("--out-dir", default=str(DATA_DIR / "study_lv_attributes" / "whole_study_backfill"),
                        help="Directory for the value report (per-method: whole_study_backfill/ or per_sample/).")
    args = parser.parse_args()

    applied = pd.read_csv(args.applied, sep="\t", dtype=str)
    # Default: score each fill against BOTH the raw and curated `_parsed` gold column, counting it
    # correct if it matches EITHER (so raw `Homo sapiens` and parsed `human` both pass without a
    # categorisation table here); `collection_date` is matched at year granularity (see _cmp_key).
    if args.gold_suffix is None:
        gold_cols = {f: [f, f"{f}_parsed"] for f in backfill.FIELDS}
    else:
        gold_cols = {f: [f"{f}{args.gold_suffix}"] for f in backfill.FIELDS}
    all_cols = sorted({c for cols in gold_cols.values() for c in cols})
    gold = _read_gold(args.truth, "sample_accession", all_cols)
    print(f"Applied fills: {len(applied)}; gold rows: {len(gold)}", file=sys.stderr)

    res = backfill.value_correctness(applied, gold, sample_col="sample_accession", gold_cols=gold_cols)

    basis = "raw + curated `_parsed`" if args.gold_suffix is None else f"`{args.gold_suffix or '(raw)'}`"
    md = ["# Backfill value-correctness vs metadata_v2\n"]
    md.append(f"Gold = `{Path(args.truth).name}`, matched against {basis} per field (placeholder-stripped "
              "both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A "
              "fill is correct if it matches the raw or the parsed gold value.\n")
    def _a(x: float) -> str:
        return f"{x:.2f}" if pd.notna(x) else "—"

    md.append("| field | cells filled | with gold | correct | value-accuracy | blank-fill acc (n) | "
              "overwrite acc (n) |")
    md.append("|---|---|---|---|---|---|---|")
    for _, r in res.iterrows():
        md.append(
            f"| {r['field']} | {int(r['filled'])} | {int(r['has_gold'])} | {int(r['correct'])} | "
            f"{_a(r['accuracy'])} | {_a(r['acc_blank_fill'])} (n={int(r['has_gold_blank'])}) | "
            f"{_a(r['acc_overwrite'])} (n={int(r['has_gold_overwrite'])}) |")
    md.append("\n- **cells filled** = fills proposed; **with gold** = of those, how many have a value in "
              "metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).")
    md.append("- **blank-fill acc** = accuracy on fills of a blank ENA cell (a positive fill — the real "
              "value-add). **overwrite acc** = accuracy on fills that replaced a real ENA value; these are "
              "scored against a gold that *is* the raw ENA the fill deliberately replaced, so they read low by "
              "construction and need spot-review, not equality. `n` = with-gold count in each split.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md = out_dir / f"{args.report_prefix}_report.md"
    out_md.write_text("\n".join(md) + "\n")
    res.to_csv(out_dir / f"{args.report_prefix}_report.tsv", sep="\t", index=False)
    print(f"Wrote {out_md} + .tsv", file=sys.stderr)
    print(res.to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
