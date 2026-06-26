"""Validate whole-field whole-project backfill for the four sample-level fields (train+val).

The grader proposes a single whole-project value for ``country`` / ``collection_date`` /
``isolation_source`` / ``host`` when the paper supports one (whole-field). Here we measure how well
those proposals target the real gaps, using the live ``parsed_per_project`` Google-Sheet tab as
ground truth: it records, per accession and field, the non-null fraction BEFORE curation
(``<field>_pre``) and AFTER (``<field>_completeness``).

That tab holds completeness *fractions*, not the backfilled *values*, so we cannot check a proposed
value's correctness here (that needs the per-sample ``metadata_v2`` table — deferred with per-sample).
What we CAN measure is **targeting / recall**: where ENA left a field largely blank (low ``_pre``),
did whole-field propose a whole-project value, and does that align with where curation actually lifted
completeness? Fillable accessions with no whole-project proposal are the per-sample per-sample
backlog (deferred).

Writes ``data/backfill_validation_report.{md,tsv}``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.gsheet import read_tab

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"
FIELDS = ["country", "collection_date", "isolation_source", "host"]
PRE_THRESHOLD = 0.90  # ENA non-null below this => a real backfill opportunity (>=10% blank)
IMPROVE_THRESHOLD = 0.05  # curation lifted completeness by >5 percentage points


def _to_float(s: pd.Series) -> pd.Series:
    """Coerce a string column (possibly blank / percent) to float in [0, 1]."""
    v = pd.to_numeric(s.astype(str).str.replace("%", "", regex=False).str.strip(), errors="coerce")
    return v.where(v <= 1.0, v / 100.0)  # tolerate values entered as 0-100


def _proposals() -> pd.DataFrame:
    """Per-accession whole-field proposal flags + values from the grades TSV (train+val)."""
    g = pd.read_csv(DATA_DIR / "study_lv_attributes" / "grading" / "study_grades.tsv", sep="\t", dtype=str).fillna("")
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    g = g.merge(split, on="study_accession", how="left")
    g = g[g["fold"].isin(["train", "val"])]
    out = {"study_accession": g["study_accession"]}
    for f in FIELDS:
        vcol, wcol = f"backfill_{f}__value", f"backfill_{f}__whole_project"
        out[f"{f}__value"] = g.get(vcol, "")
        out[f"{f}__proposed"] = (g.get(vcol, pd.Series([""] * len(g))).astype(str).str.strip() != "") & (
            g.get(wcol, pd.Series([""] * len(g))).astype(str).str.lower() == "true"
        )
    return pd.DataFrame(out)


def _parsed_per_project() -> pd.DataFrame:
    """Per-accession pre/post completeness for the four fields from the live tab."""
    df = read_tab(SHEET_ID, "parsed_per_project")
    keep = {"study_accession": df["study_accession"]}
    for f in FIELDS:
        keep[f"{f}__pre"] = _to_float(df.get(f"{f}_pre", pd.Series([""] * len(df))))
        keep[f"{f}__post"] = _to_float(df.get(f"{f}_completeness", pd.Series([""] * len(df))))
    return pd.DataFrame(keep)


def main() -> None:
    """Join proposals with parsed_per_project completeness and write the targeting report."""
    parser = argparse.ArgumentParser(description="Validate whole-field backfill targeting (Klebsiella).")
    parser.add_argument("--pre-threshold", type=float, default=PRE_THRESHOLD)
    args = parser.parse_args()

    prop = _proposals()
    gt = _parsed_per_project()
    df = prop.merge(gt, on="study_accession", how="inner")
    print(f"Joined {len(df)} train+val accessions with parsed_per_project", file=sys.stderr)

    md = ["# attribute extraction — whole-field backfill targeting vs parsed_per_project (train+val)\n"]
    md.append(f"Accessions with both a grade and a parsed_per_project row: **{len(df)}**.\n")
    md.append("`needs` = ENA non-null `<field>_pre` < threshold (a real gap). `covered` = whole-field "
              "proposed a whole-project value. `improved` = curation lifted completeness by "
              f">{IMPROVE_THRESHOLD:.0%}. Threshold = {args.pre_threshold:.0%}.\n")
    md.append("| field | needs backfill | covered by whole-field | residual (per-sample) | redundant | "
              "recall vs curation |")
    md.append("|---|---|---|---|---|---|")

    rows = []
    for f in FIELDS:
        pre, post, proposed = df[f"{f}__pre"], df[f"{f}__post"], df[f"{f}__proposed"]
        has_gt = pre.notna()
        need = has_gt & (pre < args.pre_threshold)
        improved = has_gt & ((post - pre) > IMPROVE_THRESHOLD)
        covered = int((need & proposed).sum())
        residual = int((need & ~proposed).sum())
        redundant = int((~need & proposed & has_gt).sum())
        # recall: of accessions curation actually improved, how many did whole-field also flag?
        recall = float((improved & proposed).sum() / improved.sum()) if improved.sum() else float("nan")
        md.append(f"| {f} | {int(need.sum())} | {covered} | {residual} | {redundant} | "
                  f"{recall:.2f} (n={int(improved.sum())}) |")
        for _, r in df[need].iterrows():
            rows.append({
                "field": f, "study_accession": r["study_accession"],
                "pre": round(r[f"{f}__pre"], 3) if pd.notna(r[f"{f}__pre"]) else "",
                "post": round(r[f"{f}__post"], 3) if pd.notna(r[f"{f}__post"]) else "",
                "method_a_proposed": bool(r[f"{f}__proposed"]),
                "proposed_value": r[f"{f}__value"],
                "status": "covered" if r[f"{f}__proposed"] else "residual_per_sample",
            })

    md.append("\n## Reading it\n")
    md.append("- **covered**: whole-field supplies a whole-project value for a field ENA left blank — "
              "ready to apply (value correctness still to be checked vs metadata_v2).")
    md.append("- **residual (per-sample)**: a real gap with no single whole-project value — the deferred "
              "per-sample-table backlog.")
    md.append("- **recall vs curation**: where curation demonstrably filled the field, did whole-field "
              "also flag it? Low recall ⇒ much of the win needs per-sample.")

    (DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_validation_report.md").write_text("\n".join(md) + "\n")
    pd.DataFrame(rows).sort_values(["field", "study_accession"]).to_csv(
        DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_validation_report.tsv", sep="\t", index=False)
    print("Wrote backfill_validation_report.{md,tsv}", file=sys.stderr)


if __name__ == "__main__":
    main()
