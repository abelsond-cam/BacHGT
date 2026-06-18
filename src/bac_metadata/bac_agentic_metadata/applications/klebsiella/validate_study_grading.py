"""Validate Stage 2A grades against the trusted curation columns (train+val only).

Measures the *grading* step in isolation (it was fed the curated paper link). Per the project
rule we compare only against trusted ground truth and **record disagreements rather than assume
the sheet is right** — the gold standard has known imperfections.

**Primary accuracy checks** (the ones with usable ground truth):

* ``amr_study`` ↔ frozen ``sample_selection`` (normalised: AMR / surveillance / mixed).
* ``study_setting`` ↔ the **live** ``study_level`` Google tab (opt-in ``--study-setting-from-sheet``;
  it is absent from the frozen snapshot). Skipped with a note when not requested / unavailable.

``cohort_age`` has **no well-curated ground truth** (free-text ``newborn_cohort``), so it is **not
scored for accuracy** — listed only as a spot-check. Generate-only attributes (``amr_target``,
``amr_method``) and backfill proposals are likewise spot-checks. Coverage + ``needs_manual_download``
get sanity summaries.

With ``--adjudicate``, every primary-check disagreement is sent to a critique agent
(``engine.adjudicator``) that re-reads the paper, rules which label is correct with a **verbatim
quote**, and flags rubric **rule gaps** → ``data/grading_adjudication_report.{md,tsv}``.

Writes ``data/grading_validation_report.{tsv,md}``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPEC_PATH = APP_DIR / "attributes.yaml"
SNAPSHOT_PATH = DATA_DIR / "study_level_metadata_all_combined_v1.0_20260105.csv"
STUDY_SETTING_FROZEN = DATA_DIR / "study_setting_frozen.tsv"
GT_CORRECTIONS = DATA_DIR / "gt_corrections.tsv"  # David-verified overlay on the frozen GT
SPLIT_PATH = DATA_DIR / "kleb_project_splits.tsv"
FULLTEXT_CACHE = DATA_DIR / "fulltext_cache"
LLM_CACHE = DATA_DIR / "llm_cache"
SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"

ACCESSION_RE = re.compile(r"\bPRJ[A-Z]+\d+\b")
_URL_RE = re.compile(r"https?://\S+")
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
    """Map a free-text ``newborn_cohort`` note to {newborn_young_child, adult, mixed} or ``None``.

    Retained only for the (unscored) spot-check listing — ``newborn_cohort`` is not a reliable
    ground truth, so it must not drive an accuracy figure.
    """
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


def _paper_links() -> dict[str, str]:
    """Map each accession to its first curated ``paper_link`` (for re-fetching paper text)."""
    snap = pd.read_csv(SNAPSHOT_PATH, dtype=str).fillna("")
    out: dict[str, str] = {}
    for _, r in snap.iterrows():
        m = _URL_RE.search(r.get("paper_link", ""))
        first = m.group(0).rstrip(").,") if m else ""
        if not first:
            continue
        for acc in ACCESSION_RE.findall(r.get("study_accessions", "")):
            out.setdefault(acc, first)
    return out


def _evidence_by_accession(jsonl_path: Path) -> dict[str, dict]:
    """Load per-accession study-level evidence quotes from the grades JSONL."""
    out: dict[str, dict] = {}
    if not jsonl_path.exists():
        return out
    for line in jsonl_path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["study_accession"]] = r.get("study_level", {})
    return out


def _study_setting_frozen() -> dict[str, str] | None:
    """Read study_setting per accession from the committed frozen sidecar, or ``None`` if absent."""
    if not STUDY_SETTING_FROZEN.exists():
        return None
    df = pd.read_csv(STUDY_SETTING_FROZEN, sep="\t", dtype=str).fillna("")
    return {r["study_accession"]: r["study_setting"].strip().lower() for _, r in df.iterrows() if r["study_setting"]}


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


def _apply_gt_corrections(df: pd.DataFrame, attribute: str, gtcol: str) -> int:
    """Overlay David-verified ground-truth corrections onto ``gtcol`` for one attribute.

    The frozen snapshot is left immutable; ``gt_corrections.tsv`` (study_accession, attribute,
    corrected_value, source) records hand-verified fixes that override the frozen value at scoring
    time. Returns the number of rows corrected (0 if the overlay file is absent).
    """
    if not GT_CORRECTIONS.exists() or gtcol not in df.columns:
        return 0
    ov = pd.read_csv(GT_CORRECTIONS, sep="\t", dtype=str).fillna("")
    fixes = {r["study_accession"]: r["corrected_value"].strip().lower()
             for _, r in ov.iterrows() if r["attribute"] == attribute and r["corrected_value"].strip()}
    if not fixes:
        return 0
    mask = df["study_accession"].isin(fixes)
    df.loc[mask, gtcol] = df.loc[mask, "study_accession"].map(fixes)
    return int(mask.sum())


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


def _disagreements(df: pd.DataFrame, attr: str, gtcol: str, rawcol: str, evidence: dict) -> list[dict]:
    """Rows where the grader and ground truth disagree, with the grader's verbatim evidence quote."""
    pcol = f"{attr}__value"
    if pcol not in df.columns or gtcol not in df.columns:
        return []
    mask = df[pcol].notna() & (df[pcol] != "") & df[gtcol].notna() & (df[gtcol] != "") & (df[pcol] != df[gtcol])
    out = []
    for _, r in df[mask].iterrows():
        acc = r["study_accession"]
        ev = evidence.get(acc, {}).get(attr, {})
        out.append(
            {
                "accession": acc,
                "model": r[pcol],
                "gt": r[gtcol],
                "gt_raw": str(r.get(rawcol, "")) if rawcol else str(r[gtcol]),
                "quote": ev.get("evidence_quote", ""),
            }
        )
    return out


def _md_table(df: pd.DataFrame) -> str:
    """Render a small DataFrame as a markdown code block (no tabulate dependency)."""
    return "```\n" + df.to_string() + "\n```" if not df.empty else "_(no overlapping rows)_"


def _run_adjudication(disagreements: dict[str, list[dict]], model: str, backend: str) -> list:
    """Adjudicate each primary-check disagreement (re-read the paper, verbatim verdict + rule gaps)."""
    from bac_metadata.bac_agentic_metadata.engine import adjudicator
    from bac_metadata.bac_agentic_metadata.engine.fulltext import FullText, fetch_fulltext
    from bac_metadata.bac_agentic_metadata.engine.llm import make_llm
    from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

    spec = AttributeSpec.from_yaml(SPEC_PATH)
    llm = make_llm(backend, model=model, cache_dir=LLM_CACHE)
    links = _paper_links()
    adjudications = []
    for attr, items in disagreements.items():
        for d in items:
            link = links.get(d["accession"], "")
            ft = fetch_fulltext(link, cache_dir=FULLTEXT_CACHE) if link else FullText("", "none", False, False, "")
            print(f"[adjudicate] {attr} {d['accession']} (model={d['model']} vs sheet={d['gt']})", file=sys.stderr)
            adjudications.append(
                adjudicator.adjudicate(
                    spec, llm,
                    accession=d["accession"], attribute=attr, paper_text=ft.text,
                    model_value=d["model"], model_quote=d["quote"],
                    sheet_value_norm=d["gt"], sheet_value_raw=d["gt_raw"], model=model,
                )
            )
    return adjudications


def _write_adjudication_report(adjudications: list, report_prefix: str = "grading") -> None:
    """Write the adjudication report (verbatim verdicts + aggregated rule-gap lessons)."""
    from collections import Counter

    md = ["# Stage 2A adjudication — critique of grader-vs-sheet disagreements\n"]
    verdicts = Counter(a.verdict for a in adjudications)
    md.append(f"Adjudicated **{len(adjudications)}** disagreements. Verdicts: {dict(verdicts)}.\n")
    md.append("(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)\n")

    for a in adjudications:
        md.append(f"\n## `{a.study_accession}` — {a.attribute}\n")
        md.append(f"- grader: **{a.model_value}**  |  sheet: **{a.sheet_value}** (raw: {a.sheet_value_raw[:80]!r})")
        md.append(f"- **verdict: {a.verdict}** → correct_value: **{a.correct_value}** (adjudicator: {a.model})")
        md.append(f"- justification (verbatim): {a.justification_quote!r}")
        md.append(f"- reasoning: {a.reasoning}")
        if a.rule_gap.strip():
            md.append(f"- ⚠️ rule_gap: {a.rule_gap}")

    gaps = [a for a in adjudications if a.rule_gap.strip()]
    md.append("\n## Rule gaps / lessons (candidate rubric tweaks)\n")
    if gaps:
        for a in gaps:
            md.append(f"- [{a.attribute}] (`{a.study_accession}`) {a.rule_gap}")
    else:
        md.append("_No rule gaps flagged._")

    (DATA_DIR / f"{report_prefix}_adjudication_report.md").write_text("\n".join(md) + "\n")
    pd.DataFrame([a.to_row() for a in adjudications]).to_csv(
        DATA_DIR / f"{report_prefix}_adjudication_report.tsv", sep="\t", index=False
    )
    print(f"Wrote {DATA_DIR / f'{report_prefix}_adjudication_report.md'} ({len(adjudications)} adjudications)", file=sys.stderr)


def main() -> None:
    """Parse arguments and write the Stage 2A validation report (+ optional adjudication)."""
    parser = argparse.ArgumentParser(description="Validate Stage 2A grades (Klebsiella).")
    parser.add_argument("--grades", default=str(DATA_DIR / "study_grades.tsv"), help="Stage 2A flat TSV.")
    parser.add_argument("--study-setting-from-sheet", action="store_true", help="Score study_setting via live sheet.")
    parser.add_argument("--adjudicate", action="store_true", help="Run the critique agent on primary disagreements.")
    parser.add_argument("--adjudicate-model", default="claude-opus-4-8", help="Adjudicator model (default Opus).")
    parser.add_argument("--adjudicate-backend", default="subscription", choices=["subscription", "api"])
    parser.add_argument("--report-prefix", default="grading",
                        help="Report basename prefix (default 'grading'; use e.g. 'grading_opus' to "
                             "compare grader models without clobbering).")
    args = parser.parse_args()

    grades = pd.read_csv(args.grades, sep="\t", dtype=str)
    evidence = _evidence_by_accession(Path(args.grades).with_suffix(".jsonl"))
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    gt = _gt_by_accession()

    df = grades.merge(gt, on="study_accession", how="left").merge(split, on="study_accession", how="left")
    df = df[df["fold"].isin(["train", "val"])].copy()
    print(f"Validating {len(df)} train+val graded accessions", file=sys.stderr)

    md: list[str] = ["# Stage 2A validation — grading vs trusted ground truth (train+val)\n"]
    md.append(f"Graded rows in train+val: **{len(df)}**.\n")
    md.append("Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no "
              "reliable ground truth and is **not scored** (spot-check only).\n")

    # --- Apply David-verified GT corrections (overlay on the frozen snapshot) ---
    n_amr_fix = _apply_gt_corrections(df, "amr_study", "gt_amr_study")
    if n_amr_fix:
        md.append(f"_Applied {n_amr_fix} David-verified amr_study GT corrections (gt_corrections.tsv)._\n")

    # --- PRIMARY: amr_study ---
    conf, acc, n = _agreement(df.get("amr_study__value"), df["gt_amr_study"])
    md.append(f"## amr_study  (accuracy {acc:.2f} over n={n}) — PRIMARY\n")
    md.append(_md_table(conf) + "\n")

    # --- PRIMARY: study_setting (frozen sidecar by default; live with --study-setting-from-sheet) ---
    md.append("## study_setting — PRIMARY\n")
    have_setting = False
    ss = _study_setting_from_sheet() if args.study_setting_from_sheet else _study_setting_frozen()
    source = "live sheet" if args.study_setting_from_sheet else "frozen sidecar"
    if ss is not None:
        df["gt_study_setting"] = df["study_accession"].map(ss)
        n_ss_fix = _apply_gt_corrections(df, "study_setting", "gt_study_setting")
        if n_ss_fix:
            md.append(f"_Applied {n_ss_fix} David-verified study_setting GT corrections (gt_corrections.tsv)._\n")
        conf, acc, n = _agreement(df.get("study_setting__value"), df["gt_study_setting"])
        md.append(f"Accuracy {acc:.2f} over n={n} ({source}).\n")
        md.append(_md_table(conf) + "\n")
        have_setting = True
    elif args.study_setting_from_sheet:
        md.append("_Live sheet unavailable — skipped._\n")
    else:
        md.append("_No frozen sidecar — run freeze_study_setting.py (or pass --study-setting-from-sheet)._\n")

    # --- disagreements with verbatim grader quotes (the actionable list) ---
    disagreements: dict[str, list[dict]] = {
        "amr_study": _disagreements(df, "amr_study", "gt_amr_study", "gt_amr_study_raw", evidence),
    }
    if have_setting:
        disagreements["study_setting"] = _disagreements(df, "study_setting", "gt_study_setting", "", evidence)

    md.append("## Disagreements (verbatim; record, do not assume the sheet is right)\n")
    for attr, items in disagreements.items():
        md.append(f"\n### {attr} ({len(items)} disagreements)\n")
        for d in items:
            md.append(f"- `{d['accession']}` grader=**{d['model']}** sheet=**{d['gt']}** "
                      f"(raw: {d['gt_raw'][:60]!r})\n  - grader quote: {d['quote'][:200]!r}")

    # --- cohort_age: spot-check only (NOT scored) ---
    md.append("\n## Spot-check (no clean ground truth — NOT scored)\n")
    md.append("### cohort_age (grader value vs free-text newborn_cohort)\n")
    for _, r in df.iterrows():
        cv = r.get("cohort_age__value")
        if pd.notna(cv) and cv not in ("", "None"):
            md.append(f"- `{r['study_accession']}` grader={cv} (newborn_cohort raw: {str(r.get('gt_cohort_age_raw',''))[:60]!r})")

    md.append("\n### amr_target / amr_method where amr_study in {amr,mixed}\n")
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
        "study_setting__value", "gt_study_setting", "cohort_age__value",
        "amr_target__value", "amr_method__value", "paper_coverage_for_taxon",
        "needs_manual_download", "fulltext_source",
    ]
    out_tsv = DATA_DIR / f"{args.report_prefix}_validation_report.tsv"
    df[[c for c in keep if c in df.columns]].to_csv(out_tsv, sep="\t", index=False)
    out_md = DATA_DIR / f"{args.report_prefix}_validation_report.md"
    out_md.write_text("\n".join(md) + "\n")
    print(f"Wrote {out_tsv} and {out_md}", file=sys.stderr)

    if args.adjudicate:
        total = sum(len(v) for v in disagreements.values())
        print(f"Adjudicating {total} primary disagreements with {args.adjudicate_model}", file=sys.stderr)
        adjudications = _run_adjudication(disagreements, args.adjudicate_model, args.adjudicate_backend)
        _write_adjudication_report(adjudications, args.report_prefix)


if __name__ == "__main__":
    main()
