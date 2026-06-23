r"""Consolidated run-health report — the closure signal of the curation loop (Klebsiella).

A read-only aggregator (the final pipeline stage). It **recomputes nothing**: it left-joins every existing
per-stage artifact onto the full fold study list and emits, for each **(fold study × field)**, an explicit
resolution state — so a study that was skipped, a fetch that failed, or a table that could not be
read/joined is **never a silent 0**. It then drives the human-in-the-loop convergence:

    run → the report lists the ACTIONABLE gaps (papers to fetch, supp tables to fetch, escalations to
    answer) → the curator supplements the data (manual_download/, manual_download_supp/, escalation queue)
    → rerun integrates the additions → the report re-checks …

until the verdict is **ALL CLEAR — curated to gold standard**: every (study × field) is FILLED or EXHAUSTED
(no recoverable source) with **zero ACTIONABLE** items. The report ALWAYS exits 0 — the verdict is the
loop's stop condition, not a process gate.

Reads (tag-suffixed): fold_splits/project_splits.tsv, find_papers/found_papers_<tag>.tsv,
study_lv_attributes/grading/study_grades_<tag>.jsonl, find_papers/missing_papers_report.tsv,
study_lv_attributes/whole_study_backfill/backfill_gate_report_<tag>.tsv + backfill_applied_<tag>.tsv,
sample_lv_attributes/per_sample/per_sample_outcomes_<tag>.tsv + per_sample_applied_<tag>.tsv,
study_lv_attributes/escalation/decisions_needed_<tag>.tsv + escalation_applied_<tag>.tsv,
scorecard/backfill_completeness_<tag>_report.tsv, sample_lv_attributes/persample_supplement_worklist_<tag>.tsv,
and the manual_download/ + manual_download_supp/ dirs. Writes scorecard/run_health_<tag>_report.{md,tsv}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.backfill import FIELDS
from bac_metadata.bac_agentic_metadata.engine.local_papers import resolve_local_fulltext

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPLITS = DATA_DIR / "fold_splits" / "project_splits.tsv"
FIND = DATA_DIR / "find_papers"
GRADE = DATA_DIR / "study_lv_attributes" / "grading"
WSB = DATA_DIR / "study_lv_attributes" / "whole_study_backfill"
ESC = DATA_DIR / "study_lv_attributes" / "escalation"
PS = DATA_DIR / "sample_lv_attributes" / "per_sample"
SCORE = DATA_DIR / "scorecard"
MANUAL_PDF = FIND / "manual_download"
MANUAL_SUPP = DATA_DIR / "sample_lv_attributes" / "manual_download_supp"
SUPP_EXTS = (".xlsx", ".xls", ".csv", ".tsv", ".docx", ".pdf")


def _read_tsv(path: Path) -> pd.DataFrame:
    """Read a TSV as strings, or an empty frame if absent/empty (a missing artifact is itself a finding)."""
    try:
        return pd.read_csv(path, sep="\t", dtype=str).fillna("")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _count_by_study_field(path: Path) -> dict[tuple[str, str], int]:
    """Count non-blank fills per (study_accession, field) in a long applied-fills TSV."""
    df = _read_tsv(path)
    if not len(df) or "field" not in df.columns or "applied_value" not in df.columns:
        return {}
    df = df[df["applied_value"] != ""]
    return df.groupby(["study_accession", "field"]).size().to_dict()


def _zero_reason(method: str, note: str, *, has_pmcid: bool, has_grade: bool, gate_status: str) -> str:
    """Categorise WHY a residual (study × field) yielded 0 per-sample fills — never a silent blank."""
    if not has_grade:
        return "NO_GRADE"
    if method == "NOT_IN_FOLD":
        return "NOT_IN_FOLD"
    if method == "NO_PMCID" or (not has_pmcid and method in ("", "NO_PMCID")):
        return "NO_PMCID"
    n = (note or "").lower()
    if "unanchored" in n:
        return "unanchored"
    if "manifest" in n:
        return "manifest_only"
    if "value check" in n:
        return "value_check_failed"
    if "no joinable table" in n:
        return "no_supp"
    if method in ("direct", "two_hop"):
        return "field_not_in_table"
    return "abstained_other"


def _resolution(*, gate_status: str, remaining: int, has_grade: bool, escalation_pending: bool,
                paper_fetchable: bool, table_recoverable: bool, exhausted_reason: str) -> tuple[str, str]:
    """Return (resolution_state, recoverability) for one (study × field). ACTIONABLE drives the loop."""
    if gate_status == "covered":
        return "FILLED", "whole_field"
    if gate_status != "residual_method_b":
        return ("ACTIONABLE", "needs_grade") if not has_grade else ("FILLED", "not_gated")
    if remaining <= 0:
        return "FILLED", "per_sample_or_escalation"
    if escalation_pending:
        return "ACTIONABLE", "answer_escalation"
    if paper_fetchable:
        return "ACTIONABLE", "fetch_paper"
    if table_recoverable:
        return "ACTIONABLE", "fetch_supp_table"
    return "EXHAUSTED", exhausted_reason


def main() -> None:
    """Aggregate every stage artifact into the per-(study × field) health grid + convergence verdict."""
    p = argparse.ArgumentParser(description="Consolidated run-health / convergence report (Klebsiella).")
    p.add_argument("--fold", default="test", help="Fold(s) for the study universe (e.g. 'test' or 'train,val').")
    p.add_argument("--tag", default="test", help="Artifact tag suffix.")
    args = p.parse_args()
    tag, folds = args.tag, {x.strip() for x in args.fold.split(",") if x.strip()}

    # Fold study universe — the authoritative left side of every join.
    split = _read_tsv(SPLITS)
    studies = sorted(split[split["fold"].isin(folds)]["study_accession"]) if len(split) else []

    # Inputs (each guarded — absent artifact ⇒ empty ⇒ flagged in the stage checklist).
    found = _read_tsv(FIND / f"found_papers_{tag}.tsv").set_index("study_accession") \
        if len(_read_tsv(FIND / f"found_papers_{tag}.tsv")) else pd.DataFrame()
    grades = {}
    gpath = GRADE / f"study_grades_{tag}.jsonl"
    if gpath.exists():
        for line in gpath.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                grades[r["study_accession"]] = r
    missing = _read_tsv(FIND / "missing_papers_report.tsv")
    missing_idx = missing.set_index("study_accession") if len(missing) else pd.DataFrame()
    gate = _read_tsv(WSB / f"backfill_gate_report_{tag}.tsv")
    gate_of = {(r["study_accession"], r["field"]): r for _, r in gate.iterrows()} if len(gate) else {}
    outcomes = _read_tsv(PS / f"per_sample_outcomes_{tag}.tsv")
    outcome_of = outcomes.set_index("study_accession") if len(outcomes) else pd.DataFrame()
    n_wf = _count_by_study_field(WSB / f"backfill_applied_{tag}.tsv")
    n_ps = _count_by_study_field(PS / f"per_sample_applied_{tag}.tsv")
    n_esc = _count_by_study_field(ESC / f"escalation_applied_{tag}.tsv")
    decisions = _read_tsv(ESC / f"decisions_needed_{tag}.tsv")
    # A decision is RESOLVED when answered (accepted) OR explicitly rejected (a reject marker in
    # answer_note) — otherwise the curator's "leave it" looks identical to "not yet decided" and the loop
    # could never reach ALL CLEAR. Pending = blank answer AND no reject marker.
    def _rejected(note: str) -> bool:
        return any(w in str(note).lower() for w in ("reject", "skip", "undeterm", "leave uncoded", "no value"))
    esc_pending = {(r["study_accession"], r["field"]) for _, r in decisions.iterrows()
                   if str(r.get("answer", "")).strip() == "" and not _rejected(r.get("answer_note", ""))} \
        if len(decisions) else set()
    esc_in_queue = {(r["study_accession"], r["field"]) for _, r in decisions.iterrows()} if len(decisions) else set()
    esc_generated = len(decisions)
    esc_answered = sum(1 for _, r in decisions.iterrows() if str(r.get("answer", "")).strip()) if len(decisions) else 0
    esc_applied = len(_read_tsv(ESC / f"escalation_applied_{tag}.tsv"))
    worklist = _read_tsv(PS / f"persample_supplement_worklist_{tag}.tsv")
    work_of = worklist.set_index("study_accession") if len(worklist) else pd.DataFrame()

    def _get(df, acc, col, default=""):
        return df.loc[acc, col] if (len(df) and acc in df.index and col in df.columns) else default

    rows = []
    for acc in studies:
        g = grades.get(acc, {})
        has_grade = acc in grades
        fulltext_source = str(g.get("fulltext_source", "")) or ("" if has_grade else "NO_GRADE")
        is_full_text = bool(g.get("is_full_text", False))
        none_found = str(_get(found, acc, "none_found")).lower() in ("true", "1", "yes")
        pmcid = str(_get(found, acc, "chosen_pmcid")).strip()
        has_paper = str(_get(missing_idx, acc, "has_paper")).lower() in ("true", "1", "yes")
        # missing_papers only lists no-full-text studies; a graded full-text study is paper-resolved.
        paper_resolved = is_full_text or (acc not in missing_idx.index if len(missing_idx) else is_full_text)
        manual_pdf_present = (MANUAL_PDF / f"{acc}.pdf").exists()
        manual_pdf_readable = manual_pdf_present and resolve_local_fulltext(acc, str(MANUAL_PDF)) is not None
        supp_present = any((MANUAL_SUPP / f"{acc}{e}").exists() for e in SUPP_EXTS)
        om_method = str(_get(outcome_of, acc, "method"))
        om_note = str(_get(outcome_of, acc, "note"))
        probe_opinion = str(_get(work_of, acc, "has_per_sample_table"))

        # paper fetchable = a paywalled study that still has no usable manual PDF.
        paper_fetchable = (has_paper and not manual_pdf_readable and not is_full_text)
        for field in FIELDS:
            gr = gate_of.get((acc, field), {})
            gate_status = str(gr.get("status", "")) or ("NO_GRADE" if not has_grade else "not_gated")
            n_blank = int(float(gr.get("n_blank", 0) or 0))
            nwf, nps, nesc = n_wf.get((acc, field), 0), n_ps.get((acc, field), 0), n_esc.get((acc, field), 0)
            remaining = max(0, n_blank - nps - nesc)
            zreason = _zero_reason(om_method, om_note, has_pmcid=bool(pmcid), has_grade=has_grade,
                                   gate_status=gate_status)
            table_recoverable = (not supp_present) and (
                zreason in ("unanchored", "manifest_only") or probe_opinion in ("yes", "likely"))
            exhausted_reason = ("NO_PAPER" if (none_found or not has_paper) and not is_full_text
                                else "probe_no" if probe_opinion == "no" else zreason)
            escalation_pending = (acc, field) in esc_pending
            state, recover = _resolution(
                gate_status=gate_status, remaining=remaining, has_grade=has_grade,
                escalation_pending=escalation_pending, paper_fetchable=paper_fetchable,
                table_recoverable=table_recoverable, exhausted_reason=exhausted_reason)
            esc_status = ("applied" if nesc > 0 else "pending" if escalation_pending
                          else "generated" if (acc, field) in esc_in_queue else "none") \
                if esc_in_queue else "not_generated"
            rows.append({
                "study_accession": acc, "field": field, "fold": args.fold,
                "none_found": none_found, "chosen_pmcid": pmcid, "fulltext_source": fulltext_source,
                "is_full_text": is_full_text, "paper_resolved": paper_resolved,
                "manual_pdf_present": manual_pdf_present, "manual_pdf_readable": manual_pdf_readable,
                "supp_present": supp_present,
                "gate_status": gate_status, "n_blank": n_blank,
                "per_sample_method": om_method, "zero_reason": zreason if remaining > 0 else "",
                "n_whole_field": nwf, "n_per_sample": nps, "n_escalation": nesc, "remaining_est": remaining,
                "escalation_status": esc_status,
                "resolution_state": state, "recoverability": recover,
            })

    res = pd.DataFrame(rows)
    SCORE.mkdir(parents=True, exist_ok=True)
    res.to_csv(SCORE / f"run_health_{tag}_report.tsv", sep="\t", index=False)
    _write_md(res, studies, tag, args.fold, esc_generated, esc_answered, esc_applied,
              missing_idx, work_of, gate)
    actionable = int((res["resolution_state"] == "ACTIONABLE").sum()) if len(res) else 0
    verdict = "ALL CLEAR — curated to gold standard" if actionable == 0 else f"{actionable} ACTIONABLE items outstanding"
    print(f"Wrote run_health_{tag}_report.{{md,tsv}} — VERDICT: {verdict}", file=sys.stderr)
    if len(res):
        print(res["resolution_state"].value_counts().to_string(), file=sys.stderr)
    raise SystemExit(0)  # always exit 0 — loud, never blocks


def _write_md(res: pd.DataFrame, studies: list, tag: str, fold: str, esc_generated: int,
              esc_answered: int, esc_applied: int, missing_idx, work_of, gate) -> None:
    """Render the verdict banner + the shrinking actionable worklist + the concern sections."""
    n = len(res)
    filled = int((res["resolution_state"] == "FILLED").sum()) if n else 0
    actionable = int((res["resolution_state"] == "ACTIONABLE").sum()) if n else 0
    exhausted = int((res["resolution_state"] == "EXHAUSTED").sum()) if n else 0
    verdict = "✅ **ALL CLEAR — curated to gold standard**" if actionable == 0 \
        else f"⚠️ **{actionable} ACTIONABLE items outstanding — supplement & rerun**"
    md = [f"# Run-health report ({fold} / {tag})\n", f"## {verdict}\n",
          f"{n} (study × field) cells over {len(studies)} fold studies — "
          f"**FILLED {filled} · ACTIONABLE {actionable} · EXHAUSTED {exhausted}**. "
          "The loop closes when ACTIONABLE reaches 0 (every cell FILLED or EXHAUSTED).\n"]

    act = res[res["resolution_state"] == "ACTIONABLE"] if n else res
    md.append("## Actionable worklist — do these, then rerun\n")
    if not len(act):
        md.append("Nothing outstanding. ✅\n")
    else:
        for kind, label in [("fetch_paper", "Fetch papers"), ("fetch_supp_table", "Fetch supplementary tables"),
                            ("answer_escalation", "Answer escalations"), ("needs_grade", "Re-grade (no grade yet)")]:
            sub = act[act["recoverability"] == kind]
            accs = sorted(set(sub["study_accession"]))
            if not accs:
                continue
            md.append(f"### {label} ({len(accs)})\n")
            if kind == "fetch_paper":
                md.append("| study | best URL | gap |")
                md.append("|---|---|---|")
                for a in accs:
                    url = missing_idx.loc[a, "best_url"] if (len(missing_idx) and a in missing_idx.index) else ""
                    gap = missing_idx.loc[a, "gap_samples"] if (len(missing_idx) and a in missing_idx.index
                                                               and "gap_samples" in missing_idx.columns) else ""
                    md.append(f"| {a} | {url} | {gap} |")
            elif kind == "fetch_supp_table":
                md.append("| study | save as | table ref |")
                md.append("|---|---|---|")
                for a in accs:
                    ref = work_of.loc[a, "table_reference"] if (len(work_of) and a in work_of.index
                                                               and "table_reference" in work_of.columns) else ""
                    md.append(f"| {a} | `manual_download_supp/{a}.xlsx` | {str(ref)[:50]} |")
            else:
                fields_by = sub.groupby("study_accession")["field"].apply(lambda s: ",".join(sorted(set(s))))
                for a in accs:
                    md.append(f"- {a} ({fields_by.get(a, '')})")
            md.append("")

    md.append(f"## Escalation status\n- queue generated: {esc_generated} rows; answered: {esc_answered}; "
              f"applied fills: {esc_applied}.\n")

    if n:
        md.append("## Zero-reason breakdown (per-sample residual)\n")
        zr = res[res["zero_reason"] != ""]["zero_reason"].value_counts()
        md.append("\n".join(f"- {k}: {v}" for k, v in zr.items()) or "- none")
        md.append("")

    comp = _read_tsv(SCORE / f"backfill_completeness_{tag}_report.tsv")
    if len(comp):
        md.append("\n## Per-field completeness roll-up (verbatim from completeness report)\n")
        md.append("| field | agent | v2 | gain_wf | gain_ps | gain_esc | residual | flag |")
        md.append("|---|---|---|---|---|---|---|---|")
        for _, r in comp.iterrows():
            gwf, gps, gesc = r.get("gain_whole_field", ""), r.get("gain_per_sample", ""), r.get("gain_escalation", "")
            resid = float(r.get("residual_gap", 0) or 0)
            zeros = [m for m, v in [("wf", gwf), ("ps", gps), ("esc", gesc)] if str(v) in ("0.0", "0", "-0.0")]
            flag = f"⚠ {'+'.join(zeros)}=0 w/ gap" if zeros and resid > 0 else ""
            md.append(f"| {r['field']} | {r.get('agent', '')} | {r.get('v2', '')} | {gwf} | {gps} | {gesc} | "
                      f"{r.get('residual_gap', '')} | {flag} |")
        md.append("")

    (SCORE / f"run_health_{tag}_report.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
