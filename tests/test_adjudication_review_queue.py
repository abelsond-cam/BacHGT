"""Unit tests for the residual-disagreement review-queue builder (``evaluation.build_adjudication_review_queue``).

The queue must keep ONLY the rows the adjudicator did not rule for the agent — find `found_correct` and grade
`model_correct` (and find link-variant `adj_same_paper` hits) are agent-accepted and must be dropped; everything
else (curated_correct / sheet_correct / both_describe / undetermined / neither) is a residual for the curator.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.evaluation import build_adjudication_review_queue as q


def _find(rows):
    cols = ["study_accession", "chosen_title", "paper_title", "adj_same_paper", "adj_verdict",
            "adj_justification_quote", "adj_reasoning", "adj_rule_gap"]
    return pd.DataFrame(rows, columns=cols).fillna("")


def _grade(rows):
    cols = ["study_accession", "attribute", "model_value", "sheet_value", "verdict",
            "correct_value", "justification_quote", "reasoning", "rule_gap"]
    return pd.DataFrame(rows, columns=cols).fillna("")


def test_find_drops_agent_accepted_and_link_variants():
    df = _find([
        {"study_accession": "A", "adj_verdict": "found_correct"},      # agent right → drop
        {"study_accession": "B", "adj_verdict": "curated_correct"},    # manual right → keep
        {"study_accession": "C", "adj_verdict": "both_describe"},      # keep
        {"study_accession": "D", "adj_verdict": "curated_correct", "adj_same_paper": "True"},  # link variant → drop
    ])
    rows = q._find_rows(df, "train")
    assert {r["study_accession"] for r in rows} == {"B", "C"}
    assert all(r["source"] == "find" and r["field"] == "paper" for r in rows)


def test_grade_drops_model_correct_keeps_the_rest():
    df = _grade([
        {"study_accession": "A", "attribute": "amr_study", "model_value": "amr", "verdict": "model_correct"},
        {"study_accession": "B", "attribute": "amr_study", "model_value": "mixed", "sheet_value": "amr",
         "verdict": "sheet_correct", "correct_value": "amr"},
        {"study_accession": "C", "attribute": "study_setting", "verdict": "undetermined"},
    ])
    rows = q._grade_rows(df, "test")
    assert {r["study_accession"] for r in rows} == {"B", "C"}
    b = next(r for r in rows if r["study_accession"] == "B")
    assert b["field"] == "amr_study" and b["adj_correct_value"] == "amr" and b["david_verdict"] == ""


def test_build_queue_unions_tags(tmp_path):
    from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
    data = tmp_path / "data"
    for tag in ("train", "test"):
        rp = RunPaths(data, tag)
        rp.find_dir.mkdir(parents=True, exist_ok=True)
        rp.grade_dir.mkdir(parents=True, exist_ok=True)
        _find([{"study_accession": f"{tag}F", "adj_verdict": "curated_correct"}]).to_csv(
            rp.find_dir / "find_adjudication_report.tsv", sep="\t", index=False)
        _grade([{"study_accession": f"{tag}G", "attribute": "amr_study", "verdict": "sheet_correct"}]).to_csv(
            rp.grade_dir / "grading_adjudication_report.tsv", sep="\t", index=False)
    out = q.build_queue(data, ["train", "test"])
    assert len(out) == 4 and set(out["source"]) == {"find", "grade"}
    assert list(out.columns) == q._QUEUE_COLS
