"""Validate Stage 2A grades against the trusted curation columns (train+val only).

Measures the *grading* step in isolation (it was fed the curated paper link). Per the project
rule we compare only against trusted ground truth and **record disagreements rather than assume
the sheet is right** — the gold standard has known imperfections.

Agreement is computed where a clean mapping exists:

* ``amr_study`` ↔ frozen ``sample_selection`` (normalised: AMR / surveillance / mixed).
* ``cohort_age`` ↔ frozen ``newborn_cohort`` (free-text → {newborn_young_child, adult, mixed}).
* ``study_setting`` ↔ the **live** ``study_level`` Google tab (opt-in: ``--study-setting-from-sheet``;
  it is absent from the frozen snapshot). Skipped with a note when not requested / unavailable.

Generate-only attributes (``amr_target``; ``amr_method`` beyond a coarse AST hint) and the
backfill proposals are emitted as **spot-check** lists, not scored — there is no clean ground
truth for them. Coverage and ``needs_manual_download`` get sanity summaries.

Writes ``data/stage2_validation_report.{tsv,md}``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SNAPSHOT_PATH = DATA_DIR / "study_level_metadata_all_combined_v1.0_20260105.csv"
SPLIT_PATH = DATA_DIR / "kleb_project_splits.tsv"
SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"

ACCESSION_RE = re.compile(r"\bPRJ[A-Z]+\d+\b")
YOUNG_TERMS = ("neonate", "newborn", "child", "infant", "paediatr", "pediatr")


def norm_amr_study(value: str) -> str | None:
    """Normalise a ``sample_selection`` value to {amr, surveillance, mixed} or ``None``."""
    s = (value or "").strip().lower()
    if not s:
        return None
    if "plus control" in s:  # AMR-selected cases + non-AMR controls
        return "mixed"
    if s.startswith("amr"):
        return "amr"
    if "surveil" in s:  # surveillance / "Surveilance" typo / "lifestock surveillance"
        return "surveillance"
    return None


def norm_cohort_age(value: str) -> str | None:
    """Map a free-text ``newborn_cohort`` note to {newborn_young_child, adult, mixed} or ``None``."""
    s = (value or "").strip().lower()
    if not s or "not provided" in s or s in {"unclear", "unknown", "na", "n/a"}:
        return None
    has_adult = "adult" in s
    has_young = any(t in s for t in YOUNG_TERMS)
    if has_adult and has_young:
        return "mixed"
    if has_adult:
        return "adult"
    if has_young:
        return "newborn_young_child"
    return None


def _gt_by_accession() -> pd.DataFrame:
    """Per-accession ground truth exploded from the frozen snapshot (normalised columns)."""
    snap = pd.read_csv(SNAPSHOT_PATH, dtype=str).fillna("")
    rows = []
    for _, r in snap.iterrows():
        for acc in ACCESSION_RE.findall(r.get("study_accessions", "")):
            rows.append(
                {
                    "study_accession": acc,
                    "gt_amr_study": norm_amr_study(r.get("sample_selection", "")),
                    "gt_amr_study_raw": r.get("sample_selection", ""),
                    "gt_cohort_age": norm_cohort_age(r.get("newborn_cohort", "")),
                    "gt_cohort_age_raw": r.get("newborn_cohort", ""),
                    "gt_has_ast_raw": r.get("has_AST_data", ""),
                }
            )
    return pd.DataFrame(rows).drop_duplicates("study_accession")


def _study_setting_from_sheet() -> dict[str, str] | None:
    """Read study_setting per accession from the live ``study_level`` tab, or ``None`` on failure."""
    try:
        from bac_metadata.bac_agentic_metadata.engine.gsheet import read_tab

        df = read_tab(SHEET_ID, "study_level")
    except Exception as exc:  # noqa: BLE001 — any auth/network failure → skip this half
        print(f"[study_setting] live sheet unavailable, skipping: {exc}", file=sys.stderr)
        return None
    setting_col = next((c for c in df.columns if "setting" in c.lower()), None)
    acc_col = next((c for c in df.columns if "accession" in c.lower()), None)
    if not setting_col or not acc_col:
        print(f"[study_setting] no setting/accession column in tab (cols={list(df.columns)[:8]}...)", file=sys.stderr)
        return None
    out: dict[str, str] = {}
    for _, r in df.iterrows():
        for acc in ACCESSION_RE.findall(str(r.get(acc_col, ""))):
            v = str(r.get(setting_col, "")).strip().lower()
            if v:
                out[acc] = v
    return out


def _agreement(pred: pd.Series, gt: pd.Series) -> tuple[pd.DataFrame, float, int]:
    """Return (confusion crosstab, accuracy, n) over rows where both pred and gt are present."""
    mask = pred.notna() & (pred != "") & gt.notna() & (gt != "")
    p, g = pred[mask], gt[mask]
    n = int(mask.sum())
    if n == 0:
        return pd.DataFrame(), float("nan"), 0
    acc = float((p.values == g.values).mean())
    conf = pd.crosstab(g, p, rownames=["ground_truth"], colnames=["predicted"])
    return conf, acc, n


def _md_table(df: pd.DataFrame) -> str:
    """Render a small DataFrame as a markdown code block (no tabulate dependency)."""
    return "```\n" + df.to_string() + "\n```" if not df.empty else "_(no overlapping rows)_"


def main() -> None:
    """Parse arguments and write the Stage 2A validation report."""
    parser = argparse.ArgumentParser(description="Validate Stage 2A grades (Klebsiella).")
    parser.add_argument("--grades", default=str(DATA_DIR / "stage2_grades.tsv"), help="Stage 2A flat TSV.")
    parser.add_argument("--study-setting-from-sheet", action="store_true", help="Score study_setting via live sheet.")
    args = parser.parse_args()

    grades = pd.read_csv(args.grades, sep="\t", dtype=str)
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    gt = _gt_by_accession()

    df = grades.merge(gt, on="study_accession", how="left").merge(split, on="study_accession", how="left")
    df = df[df["fold"].isin(["train", "val"])].copy()
    print(f"Validating {len(df)} train+val graded accessions", file=sys.stderr)

    md: list[str] = ["# Stage 2A validation — grading vs trusted ground truth (train+val)\n"]
    md.append(f"Graded rows in train+val: **{len(df)}**.\n")

    # --- amr_study ---
    conf, acc, n = _agreement(df.get("amr_study__value"), df["gt_amr_study"])
    md.append(f"## amr_study  (accuracy {acc:.2f} over n={n})\n")
    md.append(_md_table(conf) + "\n")

    # --- cohort_age ---
    conf, acc, n = _agreement(df.get("cohort_age__value"), df["gt_cohort_age"])
    md.append(f"## cohort_age  (accuracy {acc:.2f} over n={n})\n")
    md.append(_md_table(conf) + "\n")

    # --- study_setting (optional, live sheet) ---
    md.append("## study_setting\n")
    if args.study_setting_from_sheet:
        ss = _study_setting_from_sheet()
        if ss is not None:
            df["gt_study_setting"] = df["study_accession"].map(ss)
            conf, acc, n = _agreement(df.get("study_setting__value"), df["gt_study_setting"])
            md.append(f"Accuracy {acc:.2f} over n={n} (live sheet).\n")
            md.append(_md_table(conf) + "\n")
        else:
            md.append("_Live sheet unavailable — skipped._\n")
    else:
        md.append("_Not requested (pass --study-setting-from-sheet to score against the live tab)._\n")

    # --- disagreements (the actionable list) ---
    md.append("## Disagreements (record, do not assume the sheet is right)\n")
    for attr, gtcol, rawcol in [
        ("amr_study", "gt_amr_study", "gt_amr_study_raw"),
        ("cohort_age", "gt_cohort_age", "gt_cohort_age_raw"),
    ]:
        pcol = f"{attr}__value"
        sub = df[df[pcol].notna() & df[gtcol].notna() & (df[pcol] != df[gtcol])]
        md.append(f"\n### {attr} ({len(sub)} disagreements)\n")
        for _, r in sub.iterrows():
            md.append(f"- `{r['study_accession']}` pred=**{r[pcol]}** gt=**{r[gtcol]}** (raw: {r[rawcol][:70]!r})")

    # --- generate-only spot-checks ---
    md.append("\n## Spot-check (generate-only — no clean ground truth)\n")
    md.append("### amr_target (value/grade) where amr_study in {amr,mixed}\n")
    amrmask = df["amr_study__value"].isin(["amr", "mixed"])
    for _, r in df[amrmask].iterrows():
        md.append(f"- `{r['study_accession']}` amr_target={r.get('amr_target__value')} "
                  f"amr_method={r.get('amr_method__value')} (gt has_AST_data raw: {str(r.get('gt_has_ast_raw',''))[:50]!r})")

    # --- backfill proposals summary ---
    md.append("\n## Whole-project backfill proposals (method a)\n")
    for fld in ["country", "isolation_source", "host", "collection_date"]:
        col = f"backfill_{fld}__whole_project"
        if col in df.columns:
            n_prop = int((df[col].astype(str).str.lower() == "true").sum())
            md.append(f"- **{fld}**: {n_prop}/{len(df)} accessions proposed a whole-project value.")

    # --- coverage + needs_manual sanity ---
    md.append("\n## Coverage & retrieval sanity\n")
    cov = pd.to_numeric(df.get("paper_coverage_for_taxon"), errors="coerce")
    md.append(f"- paper_coverage_for_taxon: median {cov.median():.2f}, "
              f">0.9 in {(cov > 0.9).sum()}/{cov.notna().sum()} with a value.")
    nmd = (df.get("needs_manual_download").astype(str).str.lower() == "true").sum()
    md.append(f"- needs_manual_download: {nmd}/{len(df)} accessions.")
    src = df.get("fulltext_source")
    if src is not None:
        md.append(f"- fulltext source mix: {src.value_counts().to_dict()}")

    # Write TSV (per-accession comparison) + MD.
    keep = [
        "study_accession", "fold", "amr_study__value", "gt_amr_study",
        "cohort_age__value", "gt_cohort_age", "study_setting__value",
        "amr_target__value", "amr_method__value", "paper_coverage_for_taxon",
        "needs_manual_download", "fulltext_source",
    ]
    out_tsv = DATA_DIR / "stage2_validation_report.tsv"
    df[[c for c in keep if c in df.columns]].to_csv(out_tsv, sep="\t", index=False)
    out_md = DATA_DIR / "stage2_validation_report.md"
    out_md.write_text("\n".join(md) + "\n")
    print(f"Wrote {out_tsv} and {out_md}", file=sys.stderr)


if __name__ == "__main__":
    main()
