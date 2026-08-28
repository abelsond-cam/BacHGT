"""Tests for the interactive escalation walk (``engine.cli.escalate._interactive``).

The walk is the point where a human curator's judgement enters the pipeline, so the key guarantee is that
**every keystroke records a DECISION** — never a silent limbo. In particular, pressing Enter on a decision
that has no engine suggestion (``SUGGESTED : (none)``) must record an explicit resolved "none" (mirroring
``s``), not leave the row blank-and-pending. The old behaviour let a whole "accept everything" walk register
nothing, because Enter on a blank suggestion wrote a blank answer with no note. These tests lock the fix:
Enter accepts a real suggestion, Enter-on-none resolves as skip/'none', a typed value wins, and a re-walk
never re-prompts an already-resolved row.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.cli import escalate

_COLS = ["study_accession", "field", "gap_samples", "resolution", "fulltext_status", "cluster_theme",
         "grader_quote", "paper_excerpt", "region_hint", "suggested_value", "answer", "answer_note"]


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).reindex(columns=_COLS).fillna("")


def _feed(monkeypatch, answers: list[str]) -> None:
    """Feed a scripted list of prompt responses to ``input`` (one per pending row)."""
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))


def test_enter_accepts_suggestion_and_enter_on_none_resolves(tmp_path, monkeypatch):
    frame = _frame([
        {"study_accession": "S1", "field": "isolation_source", "suggested_value": "sputum"},  # Enter → accept
        {"study_accession": "S2", "field": "cf_status", "suggested_value": ""},                # Enter → 'none'
        {"study_accession": "S3", "field": "cf_status", "suggested_value": ""},                # type CF
        {"study_accession": "S4", "field": "country", "suggested_value": "France"},            # s → skip
    ])
    out = tmp_path / "decisions_needed.tsv"
    _feed(monkeypatch, ["", "", "CF", "s"])
    escalate._interactive(frame, out)

    got = pd.read_csv(out, sep="\t", dtype=str).fillna("").set_index("study_accession")
    # Enter accepts a real suggestion verbatim
    assert got.loc["S1", "answer"] == "sputum"
    # Enter on a blank suggestion records a RESOLVED 'none' (no value, but a decision — recognised as resolved)
    assert got.loc["S2", "answer"] == ""
    assert "none" in got.loc["S2", "answer_note"].lower() and "skip" in got.loc["S2", "answer_note"].lower()
    assert escalate._resolved(got.loc["S2"]) is True
    # a typed value always wins
    assert got.loc["S3", "answer"] == "CF"
    # 's' is still the explicit skip
    assert got.loc["S4", "answer"] == "" and "skip" in got.loc["S4", "answer_note"].lower()


def test_rewalk_does_not_reprompt_resolved_rows(tmp_path, monkeypatch):
    """The whole point of recording Enter-on-none: a second walk finds nothing pending and re-prompts nobody."""
    frame = _frame([
        {"study_accession": "S1", "field": "cf_status", "suggested_value": ""},
        {"study_accession": "S2", "field": "cf_status", "suggested_value": ""},
    ])
    out = tmp_path / "decisions_needed.tsv"
    _feed(monkeypatch, ["", "non-CF"])          # first walk: S1 accept-none, S2 typed
    escalate._interactive(frame, out)

    # Re-walk with an input that would RAISE if any row were re-prompted (StopIteration on empty feed).
    _feed(monkeypatch, [])
    reloaded = pd.read_csv(out, sep="\t", dtype=str).fillna("")
    escalate._interactive(reloaded, out)        # must not call input() at all → no StopIteration

    got = pd.read_csv(out, sep="\t", dtype=str).fillna("").set_index("study_accession")
    assert escalate._resolved(got.loc["S1"]) and got.loc["S1", "answer"] == ""
    assert got.loc["S2", "answer"] == "non-CF"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
