r"""Input pre-scan — what the ATB *M. abscessus* spreadsheet already answers, before any agentic run.

Read-only, no LLM, no ENA calls. For each target curation field it reports, per study and overall, the
fraction of records the **structured input** already fills (after stripping placeholders) — so we know up
front which fields are largely answered by the data (e.g. cf_status, country) versus those that are entirely
paper-derived (smoking, AST). This grounds the rubric and tells us where the agentic run actually adds value.

Per-field structured source columns are the curator-added + ENA-native columns that carry each signal; fields
with no source column (smoking, AST) report 0% and are flagged paper-only. cf_status is reported on its clean
human binary (CF / Non-CF), with the non-human (Animal/Environmental) and unknown (?) tallies shown separately.

Examples
--------
uv run python applications/m_abs/scan_input_availability.py            # writes data/diagnostics/input_availability.{tsv,md}
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DEFAULT_XLSX = APP_DIR / "ATB_metadata_Mabs_2025_release.xlsx"
OUT_DIR = APP_DIR / "data" / "diagnostics"

# Placeholder / non-informative cell values (stripped before counting a cell as "filled").
PLACEHOLDERS = {"", "nan", "na", "n/a", "none", "null", "?", "-", "--", "unknown", "not collected",
                "not provided", "not applicable", "missing", "not available", "not determined"}

# Target curation field -> ordered candidate source columns in the spreadsheet. A field is "structured-
# available" for a row if ANY of its candidate columns holds a non-placeholder value. Fields whose source
# list is empty (smoking_status, ast) are paper-only and report 0% by construction.
SOURCE_COLS: dict[str, list[str]] = {
    "country": ["country", "Country", "Continent"],
    "collection_date": ["collection_year", "Sample_date"],
    "isolation_source": ["isolation_source"],
    "host": ["host", "host_scientific_name"],
    "cf_status": ["cf_status"],          # host_status adds only a few CF hints; reported separately below
    "smoking_status": [],                # no column — paper-only
    "ast": [],                           # no column — paper-only
}

CF_HUMAN_BINARY = {"cf", "non-cf", "noncf", "non cf"}     # the clean human CF signal
CF_NONHUMAN = {"animal", "environmental", "environment"}  # structured but outside the human binary


def _filled(series: pd.Series) -> pd.Series:
    """Boolean mask of rows whose value is a real (non-placeholder) string."""
    s = series.fillna("").astype(str).str.strip()
    return ~s.str.lower().isin(PLACEHOLDERS)


def _verdict(frac: float) -> str:
    """Per-(study, field) availability verdict from the structured non-null fraction."""
    if frac >= 0.80:
        return "answered_by_data"
    if frac >= 0.05:
        return "partial"
    return "needs_paper"


def main() -> None:
    """Scan the spreadsheet and write the per-(study x field) availability report + a roll-up."""
    p = argparse.ArgumentParser(description="Pre-scan the ATB M. abscessus xlsx for structured field availability.")
    p.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    p.add_argument("--study-col", default="study_accession")
    p.add_argument("--out-dir", default=str(OUT_DIR))
    args = p.parse_args()

    df = pd.read_excel(args.xlsx, sheet_name=0, dtype=str)
    n_total = len(df)
    studies = df[args.study_col].fillna("").astype(str)
    n_studies = studies.nunique()

    # Per-row structured-availability mask per field (OR across candidate columns present in the sheet).
    avail = pd.DataFrame(index=df.index)
    for field, cols in SOURCE_COLS.items():
        present = [c for c in cols if c in df.columns]
        if present:
            mask = pd.concat([_filled(df[c]) for c in present], axis=1).any(axis=1)
        else:
            mask = pd.Series(False, index=df.index)
        avail[field] = mask

    # Per-(study x field) long table.
    rows = []
    for acc, idx in df.groupby(studies).groups.items():
        sub = avail.loc[idx]
        n = len(idx)
        for field in SOURCE_COLS:
            frac = float(sub[field].mean())
            rows.append({"study_accession": acc, "field": field, "n_records": n,
                         "structured_nonnull_frac": round(frac, 3), "verdict": _verdict(frac)})
    long = pd.DataFrame(rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv = out_dir / "input_availability.tsv"
    long.to_csv(tsv, sep="\t", index=False)

    # Overall per-field availability + verdict spread.
    overall = (avail.mean().rename("overall_frac").to_frame()
               .assign(overall_pct=lambda d: (100 * d["overall_frac"]).round(0).astype(int)))
    verdict_spread = long.pivot_table(index="field", columns="verdict", values="study_accession",
                                      aggfunc="count", fill_value=0)

    # cf_status detail (human binary vs non-human vs unknown) — the phenotype slot.
    cf = df["cf_status"].fillna("").astype(str).str.strip().str.lower() if "cf_status" in df else pd.Series([], dtype=str)
    cf_binary = int(cf.isin(CF_HUMAN_BINARY).sum())
    cf_nonhuman = int(cf.isin(CF_NONHUMAN).sum())
    cf_unknown = int((cf == "?").sum())

    md = out_dir / "input_availability.md"
    lines = [
        "# M. abscessus input availability (structured pre-scan)", "",
        f"`{Path(args.xlsx).name}` — **{n_total} records / {n_studies} studies**. Structured availability per "
        "target field (fraction already filled by the spreadsheet, after stripping placeholders).", "",
        "## Overall per-field availability", "",
        "| field | structured % | answered_by_data | partial | needs_paper |",
        "|---|---|---|---|---|",
    ]
    for field in SOURCE_COLS:
        vs = verdict_spread.reindex(index=[field]).fillna(0).astype(int)
        a = int(vs.get("answered_by_data", pd.Series([0])).iloc[0]) if "answered_by_data" in vs else 0
        pa = int(vs.get("partial", pd.Series([0])).iloc[0]) if "partial" in vs else 0
        npp = int(vs.get("needs_paper", pd.Series([0])).iloc[0]) if "needs_paper" in vs else 0
        pct = int(overall.loc[field, "overall_pct"]) if field in overall.index else 0
        note = " *(paper-only — no source column)*" if not SOURCE_COLS[field] else ""
        lines.append(f"| {field} | {pct}%{note} | {a} | {pa} | {npp} |")
    lines += [
        "", "## cf_status detail (the phenotype slot)", "",
        f"- human binary (CF / Non-CF): **{cf_binary}** records (CF + non-CF)",
        f"- non-human (Animal / Environmental): {cf_nonhuman}",
        f"- unknown (`?`): {cf_unknown}",
        f"- blank: {n_total - cf_binary - cf_nonhuman - cf_unknown}", "",
        "**Reading:** country / collection_date / isolation_source / host are largely answered by the data; "
        "cf_status is partly pre-filled (the agentic run fills the blanks from papers / whole-study); "
        "**smoking and AST are entirely paper-derived** (0% structured) — that is where the agentic run's "
        "value concentrates.", "",
        f"Per-(study x field) detail: `{tsv.name}`.",
    ]
    md.write_text("\n".join(lines) + "\n")
    print(f"Wrote {tsv}  and  {md}")
    print(f"\nOverall structured availability:\n{overall['overall_pct'].to_string()}")
    print(f"\ncf_status: human-binary={cf_binary}, non-human={cf_nonhuman}, unknown(?)={cf_unknown}")


if __name__ == "__main__":
    main()
