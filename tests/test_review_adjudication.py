"""Unit tests for the adjudication-review apply step (``engine.cli.review_adjudication.apply_reviews``).

A curator call that overturns the sheet (verdict agent/other) must land in ``gt_corrections.tsv`` as the new GT;
a call that agrees with the sheet (verdict manual) must NOT. Find calls must rewrite the matching
``adj_verdict`` (agent→found_correct, manual→curated_correct) so the re-summariser reflects the sign-off.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.cli import review_adjudication as ra
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

_QCOLS = ["tag", "source", "study_accession", "field", "agent_value", "manual_value", "adj_verdict",
          "adj_correct_value", "adj_quote", "adj_reasoning", "rule_gap", "david_verdict", "david_value",
          "david_note"]


def _q(rows):
    return pd.DataFrame([{c: r.get(c, "") for c in _QCOLS} for r in rows], columns=_QCOLS)


def test_grade_overturn_writes_gt_correction(tmp_path):
    gt = tmp_path / "gt.tsv"
    frame = _q([
        {"source": "grade", "study_accession": "A", "field": "amr_study", "agent_value": "amr",
         "manual_value": "mixed", "david_verdict": "agent", "david_value": "amr"},          # overturn → correction
        {"source": "grade", "study_accession": "B", "field": "amr_study", "manual_value": "amr",
         "david_verdict": "manual", "david_value": "amr"},                                   # agrees sheet → none
        {"source": "grade", "study_accession": "C", "field": "study_setting",
         "david_verdict": "other", "david_value": "community"},                              # third value → correction
    ])
    counts = ra.apply_reviews(frame, tmp_path, gt)
    assert counts["gt_corrections_added"] == 2
    out = pd.read_csv(gt, sep="\t", dtype=str).fillna("")
    got = {(r.study_accession, r.attribute): r.corrected_value for r in out.itertuples()}
    assert got == {("A", "amr_study"): "amr", ("C", "study_setting"): "community"}
    assert all(r.source == "david_adjudication_review" for r in out.itertuples())


def test_find_call_rewrites_adj_verdict(tmp_path):
    data = tmp_path / "data"
    rp = RunPaths(data, "test")
    rp.find_dir.mkdir(parents=True, exist_ok=True)
    rep = rp.find_dir / "find_adjudication_report.tsv"
    pd.DataFrame([
        {"study_accession": "P1", "adj_verdict": "curated_correct"},
        {"study_accession": "P2", "adj_verdict": "curated_correct"},
    ]).to_csv(rep, sep="\t", index=False)
    frame = _q([
        {"tag": "test", "source": "find", "study_accession": "P1", "david_verdict": "agent"},   # → found_correct
        {"tag": "test", "source": "find", "study_accession": "P2", "david_verdict": "manual"},   # → curated_correct
    ])
    counts = ra.apply_reviews(frame, data, tmp_path / "gt.tsv")
    assert counts["find_verdicts_updated"] == 2
    got = pd.read_csv(rep, sep="\t", dtype=str).set_index("study_accession")["adj_verdict"].to_dict()
    assert got == {"P1": "found_correct", "P2": "curated_correct"}


def test_skip_does_nothing(tmp_path):
    gt = tmp_path / "gt.tsv"
    frame = _q([{"source": "grade", "study_accession": "A", "field": "amr_study", "david_verdict": "skip"}])
    counts = ra.apply_reviews(frame, tmp_path, gt)
    assert counts["gt_corrections_added"] == 0 and not gt.exists()
