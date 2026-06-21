"""Diagnose WHY the grader declined a whole-field fill where the curator filled one — Klebsiella.

The completeness-gap diagnosis attributed ~45% of the residual date/source gap vs ``metadata_v2`` to
**whole-field-we-failed-to-fire**: studies the curator annotated to one uniform value (so a whole-field
fill was right) where our grader set ``applies_whole_project false``. ``curator_gold_report.tsv`` lists
them — the ``whole_field_uniform`` studies whose step-a did NOT fire (iso: 9, date: 4).

This driver runs David's two-stage probe over exactly those (study, field) pairs (no rubric edit):

1. **Self-justification** (grader's current pitch, Sonnet) — :func:`engine.whole_field_audit.
   justify_whole_field_decline`: re-show the grader its own rubric + the same evidence + its prior
   decision and ask why it declined; the ``blocking_category`` splits the gap into *fetch* vs *rubric*.
2. **Rule-gap adjudication** (adversarial, Opus) — :func:`...adjudicate_whole_field_rule_gap`: anchored
   on the curator's uniform value, rule whether the decline is a fixable ``rule_gap`` (with a drafted
   clause), ``fetch_limited``, ``coverage_gate``, ``correct_decline`` or ``curator_overcollapsed``.
   Skipped (verdict ``fetch_limited``, no Opus call) when the grader simply had no paper text and would
   still not propose — that is a fetch problem, not a rubric one.

Output ``data/whole_field_decline_report.{md,tsv}`` + the aggregated rule-gap themes to bring to David
(``attributes.yaml`` changes are his call). Diagnostic only: writes no rubric, no production data; the
curator value is the adjudication anchor, not an input to any production path.

Run (curator folders need the project_k env, like the other curator-gold scripts):

    unset VIRTUAL_ENV
    export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
    uv run python .../diagnose_whole_field_declines.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.applications.klebsiella import run_study_grading as rsg
from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine import whole_field_audit as wfa
from bac_metadata.bac_agentic_metadata.engine.ena_sizing import study_title_and_description
from bac_metadata.bac_agentic_metadata.engine.fulltext import FullText, fetch_fulltext
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, ESCALATION_MODEL, UsageLimitError, make_llm
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SPEC_PATH = APP_DIR / "attributes.yaml"
SIZING_PATH = DATA_DIR / "ena_assessment" / "ena_sizing.tsv"
LLM_CACHE = DATA_DIR / "cache" / "llm"
FIELDS = ("isolation_source", "collection_date")
_TRUNC = 200


def _target_pairs(curator_gold: Path) -> list[tuple[str, str, int]]:
    """The (study, field, gap_samples) the curator filled whole-field-uniform but our step-a missed."""
    cg = pd.read_csv(curator_gold, sep="\t")
    pairs: list[tuple[str, str, int]] = []
    for f in FIELDS:
        miss = cg[(cg[f"{f}_bucket"] == "whole_field_uniform") & (~cg[f"{f}_step_a_fired"].astype(bool))]
        for _, r in miss.sort_values(f"{f}_gap", ascending=False).iterrows():
            pairs.append((r["study_accession"], f, int(r.get(f"{f}_gap", 0))))
    return pairs


def _curator_values(studies: set[str]) -> dict[tuple[str, str], str]:
    """Modal raw curator value per (study, field) from the ready_to_merge files (the uniform answer)."""
    from bac_metadata.pp import metadata_collation as mc

    frames = []
    for rec in mc.find_ready_to_merge_files(mc.ENA_PROJECT_DIR, verbose=False):
        try:
            df, _ = mc._read_ready_to_merge_file(rec.file_path)
        except Exception as exc:  # noqa: BLE001 - skip a malformed curator file, keep going
            print(f"  skip {rec.file_path}: {exc}", file=sys.stderr)
            continue
        cols = [c for c in ("study_accession", *FIELDS) if c in df.columns]
        if "study_accession" in cols:
            frames.append(df[cols])
    rtm = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["study_accession", *FIELDS])
    rtm = rtm[rtm["study_accession"].isin(studies)]
    out: dict[tuple[str, str], str] = {}
    for acc, g in rtm.groupby("study_accession"):
        for f in FIELDS:
            if f in g.columns:
                vals = backfill.strip_placeholders(g[f]).dropna()
                if len(vals):
                    out[(acc, f)] = vals.astype(str).str.strip().mode().iloc[0]
    return out


def _grades(grades_path: Path) -> dict[str, dict]:
    """Index the grader's full JSONL records by accession (for the prior per-field backfill decision)."""
    out: dict[str, dict] = {}
    with grades_path.open() as fh:
        for line in fh:
            r = json.loads(line)
            out[r["study_accession"]] = r
    return out


def _evidence(acc: str, paper_links: dict[str, str], sizing: pd.DataFrame, classifications: dict):
    """Reconstruct the exact evidence the grader saw: fulltext + EBI title/desc + sizing row."""
    link = paper_links.get(acc, "")
    ft = fetch_fulltext(link, cache_dir=rsg.FULLTEXT_CACHE) if link else FullText("", "none", False, False, "")
    study = study_title_and_description(acc, cache_dir=rsg.ENA_CACHE)
    srow = sizing[sizing["study_accession"] == acc]
    s = srow.iloc[0].to_dict() if len(srow) else {}
    sizing_row = {
        "ena_taxon_samples": s.get("ena_taxon_samples"),
        "ena_total_samples": s.get("ena_total_samples"),
        "ena_total_runs": s.get("ena_total_runs"),
        "by_scientific_name": s.get("by_scientific_name"),
        **classifications.get(acc, {}),
    }
    return ft, study, sizing_row


def main() -> None:
    """Run the whole-field-decline probe over the curator-uniform/step-a-missed pairs and report."""
    p = argparse.ArgumentParser(description="Diagnose whole-field declines for rubric rule gaps (Klebsiella).")
    p.add_argument("--curator-gold", default=str(DATA_DIR / "diagnostics" / "curator_gold_report.tsv"))
    p.add_argument("--grades", default=str(DATA_DIR / "study_lv_attributes" / "grading" / "study_grades.jsonl"))
    p.add_argument("--backend", default="subscription", choices=["subscription", "api"])
    p.add_argument("--justify-model", default=DEFAULT_MODEL, help="Grader self-justification model (Sonnet).")
    p.add_argument("--adjudicate-model", default=ESCALATION_MODEL, help="Rule-gap adjudication model (Opus).")
    p.add_argument("--report-prefix", default="whole_field_decline_report")
    args = p.parse_args()

    spec = AttributeSpec.from_yaml(SPEC_PATH)
    pairs = _target_pairs(Path(args.curator_gold))
    studies = {acc for acc, _, _ in pairs}
    curator_vals = _curator_values(studies)
    grades = _grades(Path(args.grades))
    paper_links = rsg._accession_to_paper_link()
    classifications = rsg._classification_lookup()
    sizing = pd.read_csv(SIZING_PATH, sep="\t", dtype=str)
    llm = make_llm(args.backend, model=args.justify_model, cache_dir=LLM_CACHE)
    print(f"Probing {len(pairs)} whole-field declines across {len(studies)} studies", file=sys.stderr)

    rows = []
    for i, (acc, field, gap) in enumerate(pairs, 1):
        gr = grades.get(acc, {})
        b = gr.get("backfill", {}).get(field, {})
        ft, study, sizing_row = _evidence(acc, paper_links, sizing, classifications)
        try:
            just = wfa.justify_whole_field_decline(
                spec, llm, accession=acc, field=field, fulltext=ft,
                ena_title=study["study_title"], ena_description=study["study_description"],
                sizing_row=sizing_row, prior_proposed=b.get("proposed_value"),
                prior_whole_project=bool(b.get("applies_whole_project", False)),
                prior_quote=b.get("evidence_quote", ""), model=args.justify_model,
            )
        except UsageLimitError as exc:
            print(f"[{i}] usage limit; stopping: {exc}", file=sys.stderr)
            break

        cat = just.get("blocking_category", "other")
        would = bool(just.get("would_propose_now", False))
        # Pure fetch problem (no paper text and still would not propose) → not a rubric question; no Opus.
        if cat == "no_paper_text" and not would:
            verdict, rule_gap, rec_clause, adj_reason = "fetch_limited", "", "", "no paper text was available to the grader"
        else:
            adj = wfa.adjudicate_whole_field_rule_gap(
                spec, llm, accession=acc, field=field, paper_text=ft.text,
                grader_reason=just.get("blocking_reason", ""), grader_blocking_category=cat,
                grader_blocking_clause=just.get("blocking_rubric_clause", ""),
                curator_value=curator_vals.get((acc, field), "(unknown)"), model=args.adjudicate_model,
            )
            verdict = adj.get("verdict", "")
            rule_gap, rec_clause, adj_reason = adj.get("rule_gap", ""), adj.get("recommended_clause", ""), adj.get("reasoning", "")

        rows.append({
            "study_accession": acc, "field": field, "gap_samples": gap,
            "curator_value": curator_vals.get((acc, field), ""),
            "fulltext_source": gr.get("fulltext_source", ""), "is_full_text": gr.get("is_full_text", ""),
            "prior_proposed": b.get("proposed_value"), "prior_whole_project": b.get("applies_whole_project"),
            "would_propose_now": would, "proposed_value": just.get("proposed_value"),
            "blocking_category": cat, "blocking_reason": (just.get("blocking_reason", "") or "")[:_TRUNC],
            "verdict": verdict, "rule_gap": (rule_gap or "")[:_TRUNC],
            "recommended_clause": (rec_clause or "")[:_TRUNC], "adj_reasoning": (adj_reason or "")[:_TRUNC],
        })
        print(f"[{i}/{len(pairs)}] {acc} {field} gap={gap} -> cat={cat} would={would} verdict={verdict}", file=sys.stderr)

    res = pd.DataFrame(rows)
    res.to_csv(DATA_DIR / "diagnostics" / f"{args.report_prefix}.tsv", sep="\t", index=False)
    _write_md(res, DATA_DIR / "diagnostics" / f"{args.report_prefix}.md")
    print(f"\nWrote {args.report_prefix}.{{md,tsv}} ({len(res)} declines)", file=sys.stderr)


def _write_md(res: pd.DataFrame, path: Path) -> None:
    """Render the blocking-category / verdict split + the actionable rule-gap themes."""
    if res.empty:
        path.write_text("# Whole-field declines: no rows.\n")
        return
    total = int(res["gap_samples"].sum())
    md = ["# Whole-field declines: why the grader didn't fire where the curator filled uniform\n",
          f"{len(res)} (study, field) pairs the curator annotated whole-field-uniform but our step-a "
          f"missed — **{total} gap samples**. The grader justified each decline in its current pitch "
          "(Sonnet); an adversarial adjudicator (Opus) then ruled whether it is a fixable rubric "
          "**rule_gap** or a fetch/coverage/correct-decline cause.\n",
          "## by grader blocking_category\n", "| blocking_category | pairs | gap samples |", "|---|---|---|"]
    bc = res.groupby("blocking_category").agg(pairs=("field", "count"), gap=("gap_samples", "sum"))
    for cat, r in bc.sort_values("gap", ascending=False).iterrows():
        md.append(f"| {cat} | {int(r['pairs'])} | {int(r['gap'])} |")
    md += ["\n## by adjudicator verdict\n", "| verdict | pairs | gap samples |", "|---|---|---|"]
    vc = res.groupby("verdict").agg(pairs=("field", "count"), gap=("gap_samples", "sum"))
    for v, r in vc.sort_values("gap", ascending=False).iterrows():
        md.append(f"| {v} | {int(r['pairs'])} | {int(r['gap'])} |")
    gaps = res[res["verdict"] == "rule_gap"]
    md.append(f"\n## actionable rule gaps ({len(gaps)} pairs, {int(gaps['gap_samples'].sum())} gap samples)\n")
    if gaps.empty:
        md.append("_None — the declines are fetch/coverage/correct-decline, not rubric wording._\n")
    else:
        md.append("Bring these to David for an `attributes.yaml` decision (rubric changes are his call):\n")
        for _, r in gaps.sort_values("gap_samples", ascending=False).iterrows():
            md.append(f"- **{r['study_accession']} / {r['field']}** (gap {int(r['gap_samples'])}, curator="
                      f"`{r['curator_value']}`): {r['rule_gap']}")
            if r["recommended_clause"]:
                md.append(f"  - proposed clause: _{r['recommended_clause']}_")
    md.append("\n## per-decline detail\n")
    md.append("| study | field | gap | curator | fulltext | would_now | category | verdict |")
    md.append("|---|---|---|---|---|---|---|---|")
    for _, r in res.iterrows():
        md.append(f"| {r['study_accession']} | {r['field']} | {int(r['gap_samples'])} | {r['curator_value']} | "
                  f"{r['fulltext_source']} | {r['would_propose_now']} | {r['blocking_category']} | {r['verdict']} |")
    path.write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
