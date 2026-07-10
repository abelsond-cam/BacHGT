r"""Consolidated run-health report — the closure signal of the curation loop (engine, app-agnostic).

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

The engine takes the application's ``data_dir`` (the task-aligned data tree) and ``fields`` (the backfill
field set); a thin application shim supplies them. Reads (tag-suffixed, all under ``data_dir``):
fold_splits/project_splits.tsv, find_papers/found_papers_<tag>.tsv,
study_lv_attributes/grading/study_grades_<tag>.jsonl, find_papers/missing_papers_report.tsv,
study_lv_attributes/whole_study_backfill/backfill_gate_report_<tag>.tsv + backfill_applied_<tag>.tsv,
sample_lv_attributes/per_sample/per_sample_outcomes_<tag>.tsv + per_sample_applied_<tag>.tsv,
study_lv_attributes/escalation/decisions_needed_<tag>.tsv + escalation_applied_<tag>.tsv,
scorecard/backfill_completeness_<tag>_report.tsv, sample_lv_attributes/persample_supplement_worklist_<tag>.tsv,
and the manual_download/ + manual_download_supp/ dirs. Writes scorecard/run_health_<tag>_report.{md,tsv}.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from .local_papers import resolve_local_fulltext
from .local_supplements import find_local_supp_files

#: A study at/above this fraction of the whole cohort's taxon samples is a "big decision" — its whole-field
#: call must always be escalated (mirrors run_escalations.BIG_DECISION_FRAC); run-health flags any that slip.
BIG_DECISION_FRAC = 0.01


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
    if gate_status != "residual_per_sample":
        return ("ACTIONABLE", "needs_grade") if not has_grade else ("FILLED", "not_gated")
    if remaining <= 0:
        return "FILLED", "per_sample_or_escalation"
    if escalation_pending:
        return "ACTIONABLE", "answer_escalation"
    if paper_fetchable:
        return "ACTIONABLE", "fetch_paper"
    if table_recoverable:
        return "ACTIONABLE", "fetch_supp_table"
    if exhausted_reason == "needs_linkage":
        # A table with the data exists but can't be joined to our accessions. Not curator-actionable
        # (fetching it again won't help) but NOT gold-standard either — it's an open engine item
        # (Phase-2 linkage). BLOCKED keeps it OFF the ALL-CLEAR verdict until linkage recovers it OR the
        # curator explicitly accepts it as unrecoverable (accepted_unrecoverable file).
        return "BLOCKED", "needs_linkage"
    return "EXHAUSTED", exhausted_reason


def build_run_health(
    data_dir: Path,
    fields: Sequence[str],
    *,
    fold: str,
    tag: str,
    big_decision_frac: float = BIG_DECISION_FRAC,
) -> tuple[pd.DataFrame, str]:
    """Aggregate every stage artifact into the per-(study × field) health grid + convergence verdict.

    Parameters
    ----------
    data_dir
        The application's task-aligned data tree (holds fold_splits/, find_papers/, study_lv_attributes/, …).
    fields
        The backfill field set to grid over (e.g. country/collection_date/isolation_source/host).
    fold
        Fold(s) for the study universe (e.g. ``"test"`` or ``"train,val"``); also stamped into the table.
    tag
        Artifact tag suffix selecting the per-stage files.
    big_decision_frac
        Cohort-fraction threshold above which a declined whole-field call MUST be escalated.

    Returns
    -------
    tuple[pandas.DataFrame, str]
        The per-(study × field) grid and the one-line verdict string. Side effect: writes
        ``scorecard/run_health_<tag>_report.{md,tsv}`` under ``data_dir``.
    """
    splits = data_dir / "fold_splits" / "project_splits.tsv"
    sizing_path = data_dir / "ena_assessment" / "ena_sizing.tsv"
    find = data_dir / "find_papers"
    grade = data_dir / "study_lv_attributes" / "grading"
    wsb = data_dir / "study_lv_attributes" / "whole_study_backfill"
    esc = data_dir / "study_lv_attributes" / "escalation"
    ps = data_dir / "sample_lv_attributes" / "per_sample"
    score = data_dir / "scorecard"
    manual_pdf = find / "manual_download"
    manual_supp = data_dir / "sample_lv_attributes" / "manual_download_supp"   # tracked in git (see its README)

    folds = {x.strip() for x in fold.split(",") if x.strip()}

    # Fold study universe — the authoritative left side of every join.
    split = _read_tsv(splits)
    studies = sorted(split[split["fold"].isin(folds)]["study_accession"]) if len(split) else []
    if not studies:
        # Size-band / tail runs use a synthetic fold=tag that is absent from the main project_splits
        # (it lives only in the batch-local splits). Fall back to the tag's own graded-study universe so
        # run-health never evaluates an empty set and emits a hollow "ALL CLEAR" (the tail-band gap that
        # let <100-sample studies skip the manual-download loop unnoticed).
        graded = _read_tsv(grade / f"study_grades_{tag}.tsv")
        if len(graded) and "study_accession" in graded.columns:
            studies = sorted(set(graded["study_accession"].astype(str)))

    # Big-decision studies (>= big_decision_frac of the WHOLE cohort): their whole-field declines MUST be
    # escalated — if one isn't in the queue, run-health flags it ACTIONABLE rather than letting it go
    # EXHAUSTED (the silent-under-pickup that sank PRJEB27342 country/date). Cohort-wide, run-independent.
    sizing = _read_tsv(sizing_path)
    big_studies: set[str] = set()
    if len(sizing) and "ena_taxon_samples" in sizing.columns:
        n = pd.to_numeric(sizing["ena_taxon_samples"], errors="coerce").fillna(0)
        cohort_total = float(n.sum())
        if cohort_total:
            big_studies = set(sizing.loc[(n / cohort_total) >= big_decision_frac, "study_accession"].astype(str))

    # Inputs (each guarded — absent artifact ⇒ empty ⇒ flagged in the stage checklist).
    found = _read_tsv(find / f"found_papers_{tag}.tsv").set_index("study_accession") \
        if len(_read_tsv(find / f"found_papers_{tag}.tsv")) else pd.DataFrame()
    grades = {}
    gpath = grade / f"study_grades_{tag}.jsonl"
    if gpath.exists():
        for line in gpath.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                grades[r["study_accession"]] = r
    gate = _read_tsv(wsb / f"backfill_gate_report_{tag}.tsv")
    gate_of = {(r["study_accession"], r["field"]): r for _, r in gate.iterrows()} if len(gate) else {}
    outcomes = _read_tsv(ps / f"per_sample_outcomes_{tag}.tsv")
    outcome_of = outcomes.set_index("study_accession") if len(outcomes) else pd.DataFrame()
    n_wf = _count_by_study_field(wsb / f"backfill_applied_{tag}.tsv")
    n_ps = _count_by_study_field(ps / f"per_sample_applied_{tag}.tsv")
    n_esc = _count_by_study_field(esc / f"escalation_applied_{tag}.tsv")
    decisions = _read_tsv(esc / f"decisions_needed_{tag}.tsv")
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
    esc_applied = len(_read_tsv(esc / f"escalation_applied_{tag}.tsv"))
    worklist = _read_tsv(ps.parent / f"persample_supplement_worklist_{tag}.tsv")  # written to sample_lv_attributes/
    work_of = worklist.set_index("study_accession") if len(worklist) else pd.DataFrame()
    # Curator override: (study_accession, field[, reason]) the curator has manually verified as
    # unrecoverable (no paper findable, paper holds no usable per-isolate table, …) → forced EXHAUSTED,
    # so the loop can reach ALL CLEAR once the human has checked the genuinely-dead-end gaps.
    accepted = _read_tsv(esc / f"accepted_unrecoverable_{tag}.tsv")
    accepted_unrec = {(r["study_accession"], r["field"]) for _, r in accepted.iterrows()} if len(accepted) else set()

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
        doi = str(_get(found, acc, "chosen_doi")).strip()
        pmid = str(_get(found, acc, "chosen_pmid")).strip()
        title = str(_get(found, acc, "chosen_title")).strip()
        # A REAL paper needs a resolvable scholarly identifier — an ENA-browser link is NOT a paper.
        has_real_paper = bool(pmcid or doi or pmid) or is_full_text
        paper_url = (f"https://doi.org/{doi}" if doi else
                     f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/" if pmcid else
                     f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "")
        manual_pdf_present = (manual_pdf / f"{acc}.pdf").exists()
        manual_pdf_readable = manual_pdf_present and resolve_local_fulltext(acc, str(manual_pdf)) is not None
        paper_resolved = is_full_text or manual_pdf_readable
        supp_present = bool(find_local_supp_files(acc, manual_supp))
        om_method = str(_get(outcome_of, acc, "method"))
        om_note = str(_get(outcome_of, acc, "note"))
        probe_opinion = str(_get(work_of, acc, "has_per_sample_table"))

        # Paper fetchable = a REAL paper exists but we still have no usable full text/manual PDF.
        paper_fetchable = has_real_paper and not manual_pdf_readable and not is_full_text
        for field in fields:
            gr = gate_of.get((acc, field), {})
            gate_status = str(gr.get("status", "")) or ("NO_GRADE" if not has_grade else "not_gated")
            n_blank = int(float(gr.get("n_blank", 0) or 0))
            nwf, nps, nesc = n_wf.get((acc, field), 0), n_ps.get((acc, field), 0), n_esc.get((acc, field), 0)
            remaining = max(0, n_blank - nps - nesc)
            zreason = _zero_reason(om_method, om_note, has_pmcid=bool(pmcid), has_grade=has_grade,
                                   gate_status=gate_status)
            accepted_cell = (acc, field) in accepted_unrec
            # A per-isolate table is curator-FETCHABLE when the paper references one (probe yes/likely) and
            # none is wired yet. Two entry points: (i) EPMC lacks the supp ZIP ('no_supp') — a manual
            # publisher download could get it; (ii) the study has NO PMCID so the OA path never ran
            # ('NO_PMCID') but a resolved paper / curator-provided table can still supply it. Case (ii) is
            # bug #4 — it was short-circuited to EXHAUSTED/NO_PMCID (PRJEB28400/PRJDB5929), hiding a
            # recoverable table. 'unanchored'/'manifest_only' tables are ALREADY fetched but can't be JOINED
            # → the Phase-2 linkage problem, not a curator fetch (fetching again wouldn't help).
            table_recoverable = (
                (not supp_present) and probe_opinion in ("yes", "likely")
                and (zreason == "no_supp" or (zreason == "NO_PMCID" and paper_resolved))
            )
            if not has_real_paper and not is_full_text:
                exhausted_reason = "no_paper_findable"
            elif zreason in ("unanchored", "manifest_only"):
                exhausted_reason = "needs_linkage"
            elif probe_opinion == "no":
                exhausted_reason = "paper_has_no_table"
            else:
                exhausted_reason = zreason
            escalation_pending = (acc, field) in esc_pending and not accepted_cell
            state, recover = _resolution(
                gate_status=gate_status, remaining=remaining, has_grade=has_grade,
                escalation_pending=escalation_pending, paper_fetchable=paper_fetchable,
                table_recoverable=table_recoverable, exhausted_reason=exhausted_reason)
            # No-silent-failures audit (big decisions): a study >= big_decision_frac of the cohort whose
            # grader DECLINED a whole-field value, with a real residual, that did NOT reach the escalation
            # queue and wasn't curator-accepted, is ACTIONABLE — never silently EXHAUSTED. This is the
            # defense-in-depth that catches a missed escalation even if detect failed to queue it.
            gbf = (g.get("backfill", {}) or {}).get(field, {}) or {}
            whole_field_declined = has_grade and not bool(gbf.get("applies_whole_project")) \
                and not str(gbf.get("proposed_value") or "").strip()
            if (acc in big_studies and whole_field_declined and remaining > 0 and nesc == 0
                    and (acc, field) not in esc_in_queue and not accepted_cell):
                state, recover = "ACTIONABLE", "escalate_big_decision"
            if accepted_cell and state != "FILLED":  # curator acceptance never clobbers real data — FILLED wins
                state, recover = "EXHAUSTED", "curator_accepted"
            esc_status = ("applied" if nesc > 0 else "pending" if escalation_pending
                          else "generated" if (acc, field) in esc_in_queue else "none") \
                if esc_in_queue else "not_generated"
            rows.append({
                "study_accession": acc, "field": field, "fold": fold,
                "none_found": none_found, "chosen_pmcid": pmcid, "fulltext_source": fulltext_source,
                "is_full_text": is_full_text, "paper_resolved": paper_resolved, "paper_url": paper_url,
                "paper_title": title[:60], "manual_pdf_present": manual_pdf_present,
                "manual_pdf_readable": manual_pdf_readable, "supp_present": supp_present,
                "gate_status": gate_status, "n_blank": n_blank,
                "per_sample_method": om_method,
                "zero_reason": zreason if state in ("ACTIONABLE", "EXHAUSTED") else "",
                "n_whole_field": nwf, "n_per_sample": nps, "n_escalation": nesc, "remaining_est": remaining,
                "escalation_status": esc_status,
                "resolution_state": state, "recoverability": recover,
            })

    res = pd.DataFrame(rows)
    score.mkdir(parents=True, exist_ok=True)
    res.to_csv(score / f"run_health_{tag}_report.tsv", sep="\t", index=False)
    _write_md(res, studies, score, tag, fold, esc_generated, esc_answered, esc_applied, len(esc_pending))
    actionable = int((res["resolution_state"] == "ACTIONABLE").sum()) if len(res) else 0
    blocked = int((res["resolution_state"] == "BLOCKED").sum()) if len(res) else 0
    if not studies:
        # A health check over zero studies is NOT clear — the study universe failed to resolve (e.g. a
        # synthetic-fold tag missing from project_splits AND from grades). Fail loud so a hollow
        # "ALL CLEAR" can never again mask an un-run curator loop.
        base = (f"⛔ NO STUDIES EVALUATED (tag='{tag}', fold='{fold}') — study universe empty; run-health "
                "cannot certify. Check the tag's study_grades_<tag>.tsv / project_splits.")
    else:
        base = ("ALL CLEAR — curated to gold standard" if actionable + blocked == 0
                else f"{actionable} ACTIONABLE + {blocked} BLOCKED(needs-linkage) outstanding")
    # Curator sign-off (the two human steps) folded into the returned verdict so a partially-curated run is
    # loud on the console too — not only in the report's end banner. Mirrors the banner's logic exactly.
    need_paper_n = res[res["recoverability"] == "fetch_paper"]["study_accession"].nunique() if len(res) else 0
    unreadable_n = (res[res["manual_pdf_present"].apply(bool) & ~res["manual_pdf_readable"].apply(bool)]
                    ["study_accession"].nunique()) if len(res) else 0
    curator_ok = need_paper_n == 0 and unreadable_n == 0 and len(esc_pending) == 0
    sign = ("✅ curator sign-off complete" if curator_ok
            else f"⛔ CURATOR ACTION: {need_paper_n} paper(s) to add + {len(esc_pending)} escalation(s) to answer")
    verdict = f"{base}  |  {sign}"
    return res, verdict


def _write_md(res: pd.DataFrame, studies: list, score: Path, tag: str, fold: str, esc_generated: int,
              esc_answered: int, esc_applied: int, esc_pending: int) -> None:
    """Render the verdict banner + the shrinking actionable worklist + the concern sections."""
    n = len(res)
    filled = int((res["resolution_state"] == "FILLED").sum()) if n else 0
    actionable = int((res["resolution_state"] == "ACTIONABLE").sum()) if n else 0
    blocked = int((res["resolution_state"] == "BLOCKED").sum()) if n else 0
    exhausted = int((res["resolution_state"] == "EXHAUSTED").sum()) if n else 0
    if not len(studies):
        verdict = "⛔ **NO STUDIES EVALUATED — study universe empty; run-health cannot certify**"
    elif actionable + blocked == 0:
        verdict = "✅ **ALL CLEAR — curated to gold standard**"
    else:
        verdict = f"⚠️ **{actionable} ACTIONABLE + {blocked} BLOCKED outstanding — supplement & rerun**"
    md = [f"# Run-health report ({fold} / {tag})\n", f"## {verdict}\n",
          f"{n} (study × field) cells over {len(studies)} studies — "
          f"**FILLED {filled} · ACTIONABLE {actionable} · BLOCKED {blocked} · EXHAUSTED {exhausted}**. "
          "ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a "
          "logged reason / curator acceptance), and at least one study evaluated.\n"]

    act = res[res["resolution_state"] == "ACTIONABLE"] if n else res
    md.append("## Actionable worklist — do these, then rerun\n")
    if not len(act):
        md.append("Nothing outstanding — every cell FILLED or EXHAUSTED. ✅\n")
    else:
        # fetch_paper / fetch_supp_table: per study, the paper (title + link) + which fields are short +
        # what per-sample we already have, so the curator can judge each before chasing it.
        for kind, label, save in [("fetch_paper", "Fetch papers", False),
                                  ("fetch_supp_table", "Fetch supplementary tables", True)]:
            sub = act[act["recoverability"] == kind]
            if not len(sub):
                continue
            md.append(f"### {label} ({sub['study_accession'].nunique()})\n")
            md.append("| study | fields short | already have (per-sample) | paper |"
                      + (" save as |" if save else ""))
            md.append("|---|---|---|---|" + ("---|" if save else ""))
            for a, gs in sub.groupby("study_accession"):
                flds = ",".join(sorted(set(gs["field"])))
                srow = res[res["study_accession"] == a]
                have = ",".join(f"{f}:{int(srow[srow['field'] == f]['n_per_sample'].iloc[0])}"
                                for f in ("isolation_source", "host", "collection_date")
                                if len(srow[srow["field"] == f]))
                title, url = gs.iloc[0].get("paper_title", ""), gs.iloc[0].get("paper_url", "")
                paper = f"[{title}]({url})" if url else (title or "(no link)")
                md.append(f"| {a} | {flds} | {have} | {paper} |" + (f" `manual_download_supp/{a}.xlsx` |" if save else ""))
            md.append("")
        for kind, label in [("answer_escalation", "Answer escalations"),
                            ("escalate_big_decision", "Escalate big-decision whole-field calls (>1% of cohort) — not in queue"),
                            ("needs_grade", "Re-grade (no grade yet)")]:
            sub = act[act["recoverability"] == kind]
            if not len(sub):
                continue
            md.append(f"### {label} ({sub['study_accession'].nunique()})\n")
            for a, gs in sub.groupby("study_accession"):
                md.append(f"- {a} ({','.join(sorted(set(gs['field'])))})")
            md.append("")

    # Validated dead-ends — surfaced so the curator can confirm them (no further action will recover them).
    nopaper = sorted(set(res[res["recoverability"] == "no_paper_findable"]["study_accession"])) if n else []
    if nopaper:
        md.append("## No paper could be found — validated, won't be recovered\n"
                  f"{len(nopaper)} studies have no resolvable paper (finder exhausted; EBI record only). "
                  f"Marked EXHAUSTED: {', '.join(nopaper)}\n")
    linkage = sorted(set(res[res["recoverability"] == "needs_linkage"]["study_accession"])) if n else []
    if linkage:
        md.append("## Tables present but unjoinable (Phase-2 linkage target)\n"
                  f"{len(linkage)} studies have a supplementary table with the fields but no joinable "
                  f"accession key (anchoring): {', '.join(linkage)}\n")

    md.append(f"## Escalation status\n- queue generated: {esc_generated} rows; answered: {esc_answered}; "
              f"applied fills: {esc_applied}.\n")

    if n:
        md.append("## Zero-reason breakdown (per-sample residual)\n")
        zr = res[res["zero_reason"] != ""]["zero_reason"].value_counts()
        md.append("\n".join(f"- {k}: {v}" for k, v in zr.items()) or "- none")
        md.append("")

    comp = _read_tsv(score / f"backfill_completeness_{tag}_report.tsv")
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

    # ── LOUD curator sign-off — the two human-in-the-loop steps, stated unmissably at the very end ──
    # David's requirement: a run is NOT trustworthy until (1) manual papers are downloaded & added and
    # (2) every tight-grading escalation is answered. Both numbers come straight from the artifacts, so a
    # partially-curated run can NEVER read as done — even when the per-cell grid is otherwise satisfied.
    need_paper = sorted(set(res[res["recoverability"] == "fetch_paper"]["study_accession"])) if n else []
    added = sorted(set(res[res["manual_pdf_readable"].apply(bool)]["study_accession"])) if n else []
    present_unreadable = sorted(set(
        res[res["manual_pdf_present"].apply(bool) & ~res["manual_pdf_readable"].apply(bool)]["study_accession"])
    ) if n else []
    papers_ok = not need_paper and not present_unreadable
    esc_ok = esc_pending == 0
    paper_mark = "✅ COMPLETE" if papers_ok else "⛔ INCOMPLETE"
    esc_mark = "✅ COMPLETE" if esc_ok else "⛔ INCOMPLETE"
    overall = ("✅ CURATOR SIGN-OFF COMPLETE — both human steps done" if (papers_ok and esc_ok)
               else f"⛔ CURATOR ACTION OUTSTANDING — {len(need_paper)} paper(s) to add, "
                    f"{esc_pending} escalation(s) to answer")

    md.append("\n---\n")
    md.append("# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔\n")
    md.append("> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy "
              "figures above UNDERSTATE the pipeline — supplement the data and rerun.**\n")

    md.append(f"## 1. Manual papers downloaded & added — {paper_mark}\n")
    if need_paper:
        md.append(f"⛔ **{len(need_paper)} stud{'y' if len(need_paper) == 1 else 'ies'} have a real paper but "
                  "NO usable full text** — download each to `find_papers/manual_download/<acc>.pdf`, then rerun:\n")
        md.append("| study | paper |")
        md.append("|---|---|")
        for a in need_paper:
            r0 = res[res["study_accession"] == a].iloc[0]
            t, u = str(r0.get("paper_title", "")), str(r0.get("paper_url", ""))
            md.append(f"| {a} | {f'[{t}]({u})' if u else (t or '(no link)')} |")
        md.append("")
    else:
        md.append("✅ No outstanding downloads — every findable paper has full text "
                  f"({len(added)} via a manually-added PDF).\n")
    if present_unreadable:
        md.append(f"⚠️ **{len(present_unreadable)} manually-added PDF(s) could NOT be parsed** "
                  f"(present but unreadable — re-export/replace): {', '.join(present_unreadable)}\n")

    md.append(f"## 2. Escalations answered (tight grading questions) — {esc_mark}\n")
    md.append(f"Queue `study_lv_attributes/escalation/decisions_needed_{tag}.tsv`: "
              f"**{esc_generated} generated · {esc_answered} answered · {esc_pending} PENDING** "
              f"({esc_applied} fills applied).\n")
    if esc_pending:
        md.append(f"⛔ **{esc_pending} tight-grading decision(s) are UNANSWERED.** Fill the `answer` column "
                  "(a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.\n")
    elif esc_generated:
        md.append(f"✅ All {esc_generated} escalation(s) resolved (answered or explicitly rejected).\n")
    else:
        md.append("✅ No tight-grading escalations were raised.\n")

    md.append(f"# → {overall}\n")

    (score / f"run_health_{tag}_report.md").write_text("\n".join(md) + "\n")
