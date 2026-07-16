r"""Build the human-review queue of agent-vs-manual disagreements the adjudicator did not rule for the agent.

So the curator can sign off on the residual paper-finding + grading calls.

The adjudicator (``validate_find_papers --adjudicate`` / ``validate_study_grading --adjudicate``) auto-rules every
agent-vs-sheet disagreement. Most it rules *for* the agent (``found_correct`` / ``model_correct``); this tool
surfaces only the rest — where the adjudicator sided with the manual sheet, called both defensible, or couldn't
decide — as one walkable queue. The curator walks it with ``engine.cli.review_adjudication --interactive``, whose
confirmed grade corrections feed the existing ``gt_corrections.tsv`` overlay (and re-summarising then reflects
the human calls).

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.build_adjudication_review_queue \
        --tags train,test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

#: find verdicts that mean the AGENT's pick was accepted → not escalated. Everything else (curated_correct,
#: both_describe, neither) is a residual the curator should see. An ``adj_same_paper`` hit is a link/DOI variant,
#: never a real disagreement.
_FIND_AGENT_OK = {"found_correct"}
#: grade verdicts that mean the agent's value stood → not escalated. sheet_correct / both_defensible /
#: undetermined are residuals.
_GRADE_AGENT_OK = {"model_correct"}

_QUEUE_COLS = [
    "tag", "source", "study_accession", "field", "agent_value", "manual_value",
    "adj_verdict", "adj_correct_value", "adj_quote", "adj_reasoning", "rule_gap",
    "david_verdict", "david_value", "david_note",
]


def _find_rows(df: pd.DataFrame, tag: str) -> list[dict]:
    """Residual paper-finding disagreements — agent pick not accepted (and not a mere link variant)."""
    out = []
    for _, r in df.iterrows():
        if str(r.get("adj_same_paper", "")).strip().lower() == "true":
            continue
        if str(r.get("adj_verdict", "")).strip() in _FIND_AGENT_OK:
            continue
        out.append({
            "tag": tag, "source": "find", "study_accession": r.get("study_accession", ""), "field": "paper",
            "agent_value": r.get("chosen_title", ""), "manual_value": r.get("paper_title", ""),
            "adj_verdict": r.get("adj_verdict", ""), "adj_correct_value": "",
            "adj_quote": r.get("adj_justification_quote", ""), "adj_reasoning": r.get("adj_reasoning", ""),
            "rule_gap": r.get("adj_rule_gap", ""),
            "david_verdict": "", "david_value": "", "david_note": "",
        })
    return out


def _grade_rows(df: pd.DataFrame, tag: str) -> list[dict]:
    """Residual grading disagreements — agent value not accepted."""
    out = []
    for _, r in df.iterrows():
        if str(r.get("verdict", "")).strip() in _GRADE_AGENT_OK:
            continue
        out.append({
            "tag": tag, "source": "grade", "study_accession": r.get("study_accession", ""),
            "field": r.get("attribute", ""), "agent_value": r.get("model_value", ""),
            "manual_value": r.get("sheet_value", ""), "adj_verdict": r.get("verdict", ""),
            "adj_correct_value": r.get("correct_value", ""), "adj_quote": r.get("justification_quote", ""),
            "adj_reasoning": r.get("reasoning", ""), "rule_gap": r.get("rule_gap", ""),
            "david_verdict": "", "david_value": "", "david_note": "",
        })
    return out


def build_queue(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Union the per-tag find + grade adjudication reports into the residual-disagreement queue."""
    rows: list[dict] = []
    for tag in tags:
        rp = RunPaths(data_dir, tag)
        find = rp.find_dir / "find_adjudication_report.tsv"
        grade = rp.grade_dir / "grading_adjudication_report.tsv"
        if find.exists():
            rows += _find_rows(pd.read_csv(find, sep="\t", dtype=str).fillna(""), tag)
        else:
            print(f"[warn] no find adjudication for '{tag}' at {find}", file=sys.stderr)
        if grade.exists():
            rows += _grade_rows(pd.read_csv(grade, sep="\t", dtype=str).fillna(""), tag)
        else:
            print(f"[warn] no grading adjudication for '{tag}' at {grade}", file=sys.stderr)
    return pd.DataFrame(rows, columns=_QUEUE_COLS)


def _render_md(q: pd.DataFrame) -> str:
    L = [
        "# Adjudication review queue — residual agent-vs-manual disagreements",
        "",
        "Only rows the Opus adjudicator did NOT rule for the agent (it sided with the manual sheet, called both "
        "defensible, or was undetermined). Walk with `engine.cli.review_adjudication --interactive`.",
        "",
        f"**{len(q)} rows** — "
        + " · ".join(f"{s} {int((q['source'] == s).sum())}" for s in ("find", "grade")),
        "",
        "| tag | source | study | field | agent | manual | verdict | adjudicator says |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in q.iterrows():
        L.append(f"| {r['tag']} | {r['source']} | {r['study_accession']} | {r['field']} "
                 f"| {str(r['agent_value'])[:32]} | {str(r['manual_value'])[:32]} | {r['adj_verdict']} "
                 f"| {str(r['adj_correct_value'] or r['adj_reasoning'])[:48]} |")
    return "\n".join(L) + "\n"


def main() -> None:
    """Build the residual-disagreement review queue TSV+MD from the per-tag adjudication reports."""
    p = argparse.ArgumentParser(description="Build the agent-vs-manual residual-disagreement review queue.")
    p.add_argument("--app", default="klebsiella", help="Application under applications/ (default klebsiella).")
    p.add_argument("--data-dir", default=None, help="Override data dir (default applications/<app>/data).")
    p.add_argument("--tags", default="train,test", help="Folds with find/grade gold (default train,test).")
    p.add_argument("--out", default=None, help="Output stem (default <data-dir>/diagnostics/adjudication_review_queue).")
    args = p.parse_args()

    here = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else here / "applications" / args.app / "data"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    q = build_queue(data_dir, tags)
    stem = Path(args.out) if args.out else data_dir / "diagnostics" / "adjudication_review_queue"
    stem.parent.mkdir(parents=True, exist_ok=True)
    q.to_csv(stem.with_suffix(".tsv"), sep="\t", index=False)
    stem.with_suffix(".md").write_text(_render_md(q))
    print(f"[review-queue] {len(q)} residual disagreement(s) "
          f"(find {int((q['source'] == 'find').sum())}, grade {int((q['source'] == 'grade').sum())}) "
          f"→ {stem.with_suffix('.tsv')}", file=sys.stderr)


if __name__ == "__main__":
    main()
