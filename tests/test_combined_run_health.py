"""Unit tests for the cross-tag run-health roll-up (``evaluation.combined_run_health``).

The tool's value is its acceptance policy: outstanding cells a curator has already dispositioned as genuinely
unrecoverable must count as *clear*, while a still-answerable escalation — or any **unrecognised** recoverability
(a new failure mode) — must stay ACTIONABLE and fail the ``--strict`` gate. Each classification path is checked
in isolation, plus an end-to-end ``combine`` over a tiny on-disk pair of tags built through ``RunPaths``.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.evaluation import combined_run_health as crh


def _cell(state, rec=""):
    return pd.Series({"resolution_state": state, "recoverability": rec})


# ── classify() — the acceptance policy ────────────────────────────────────────────────────────────────
def test_closed_states_passthrough():
    assert crh.classify(_cell("FILLED"))[0] == "FILLED"
    assert crh.classify(_cell("EXHAUSTED"))[0] == "EXHAUSTED"


def test_accepted_buckets():
    for rec in ("fetch_supp_table", "needs_linkage", "escalate_big_decision", "fetch_paper"):
        assert crh.classify(_cell("ACTIONABLE", rec))[0] == "ACCEPTED", rec
    assert crh.classify(_cell("BLOCKED", "needs_linkage"))[0] == "ACCEPTED"


def test_pending_escalation_is_actionable():
    assert crh.classify(_cell("ACTIONABLE", "answer_escalation"))[0] == "ACTIONABLE"


def test_unrecognised_recoverability_fails_loud():
    disp, reason = crh.classify(_cell("ACTIONABLE", "some_new_mode"))
    assert disp == "ACTIONABLE" and "unrecognised" in reason


# ── combine() — end-to-end over a tiny on-disk pair of tags ───────────────────────────────────────────
def _write_grid(data, tag, rows):
    tsv = RunPaths(data, tag).run_health_tsv
    tsv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(tsv, sep="\t", index=False)


def test_combine_clear_when_only_accepted_and_closed(tmp_path):
    data = tmp_path / "data"
    _write_grid(data, "train", [
        {"study_accession": "A", "field": "host", "resolution_state": "FILLED", "recoverability": "whole_field"},
        {"study_accession": "B", "field": "country", "resolution_state": "ACTIONABLE", "recoverability": "fetch_supp_table"},
    ])
    _write_grid(data, "test", [
        {"study_accession": "C", "field": "host", "resolution_state": "BLOCKED", "recoverability": "needs_linkage"},
    ])
    allcells, counts = crh.combine(data, ["train", "test"])
    assert counts.get("ACTIONABLE", 0) == 0 and counts["ACCEPTED"] == 2 and counts["FILLED"] == 1


def test_combine_flags_pending_escalation_and_unknown(tmp_path):
    data = tmp_path / "data"
    _write_grid(data, "train", [
        {"study_accession": "A", "field": "host", "resolution_state": "ACTIONABLE", "recoverability": "answer_escalation"},
        {"study_accession": "D", "field": "host", "resolution_state": "ACTIONABLE", "recoverability": "brand_new_bucket"},
    ])
    allcells, counts = crh.combine(data, ["train"])
    assert counts["ACTIONABLE"] == 2
    acts = allcells[allcells["disposition"] == "ACTIONABLE"]["study_accession"].tolist()
    assert set(acts) == {"A", "D"}


def test_combine_skips_missing_tag(tmp_path):
    data = tmp_path / "data"
    _write_grid(data, "train", [
        {"study_accession": "A", "field": "host", "resolution_state": "FILLED", "recoverability": "whole_field"}])
    allcells, counts = crh.combine(data, ["train", "absent_tag"])
    assert len(allcells) == 1 and counts["FILLED"] == 1
