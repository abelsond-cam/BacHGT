"""Unit tests for the per-tag pipeline-trigger gate (``evaluation.verify_pipeline_triggers``).

The gate is the hard complement to the soft run-health self-audit: it must FAIL loud on the silent-failure
modes that "keep falling down" (a stage that didn't fire; a manual PDF/table added but never processed; a
table join that filled nothing) and PASS-with-WARN on the expected-but-loud gaps (an unanchored table). Each
pure check is exercised in isolation with hand-built frames, plus an end-to-end ``verify_tag`` over a tiny
on-disk tranche built through ``RunPaths`` (the same path authority the engine uses).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.evaluation import verify_pipeline_triggers as vt


def _sev(findings, check):
    """The set of severities emitted for a given check name."""
    return {r["severity"] for r in findings if r["check"] == check}


def _df(rows):
    return pd.DataFrame(rows)


# ── (1) find ─────────────────────────────────────────────────────────────────────────────────────────
def test_find_pass_when_found_equals_graded():
    grades = _df([{"study_accession": "A"}, {"study_accession": "B"}])
    found = _df([{"study_accession": "A"}, {"study_accession": "B"}])
    findings, universe = vt.check_find(found, grades)
    assert universe == {"A", "B"} and _sev(findings, "find") == {"OK"}


def test_find_fails_on_finder_shortfall():
    grades = _df([{"study_accession": "A"}, {"study_accession": "B"}])
    found = _df([{"study_accession": "A"}])          # B graded but never found
    findings, _ = vt.check_find(found, grades)
    assert "FAIL" in _sev(findings, "find")


def test_find_fails_when_empty():
    findings, _ = vt.check_find(pd.DataFrame(), _df([{"study_accession": "A"}]))
    assert "FAIL" in _sev(findings, "find")


# ── (2) grade ────────────────────────────────────────────────────────────────────────────────────────
def test_grade_pass_one_row_each():
    grades = _df([{"study_accession": "A"}, {"study_accession": "B"}])
    assert _sev(vt.check_grade(grades, {"A", "B"}, None), "grade") == {"OK"}


def test_grade_fails_on_selection_shortfall():
    grades = _df([{"study_accession": "A"}])
    # tail band: selection had A and B, but only A was graded
    findings = vt.check_grade(grades, {"A"}, selection_studies={"A", "B"})
    assert "FAIL" in _sev(findings, "grade")


def test_grade_fails_when_empty():
    assert "FAIL" in _sev(vt.check_grade(pd.DataFrame(), set(), None), "grade")


# ── (3) per_sample — the silent-0 core ────────────────────────────────────────────────────────────────
def test_per_sample_pass_all_zero_fills_have_reasons():
    out = _df([
        {"study_accession": "A", "method": "direct", "n_fills": "12", "note": ""},
        {"study_accession": "B", "method": "NO_PMCID", "n_fills": "0", "note": "no PMCID for study"},
        {"study_accession": "C", "method": "abstained", "n_fills": "0", "note": "no joinable table"},
    ])
    assert _sev(vt.check_per_sample(out, {"A", "B", "C"}), "per_sample") == {"OK"}


def test_per_sample_fails_on_empty_join():
    out = _df([{"study_accession": "A", "method": "direct", "n_fills": "0", "note": "parsed a table"}])
    assert "FAIL" in _sev(vt.check_per_sample(out, {"A"}), "per_sample")


def test_per_sample_fails_on_silent_zero_no_note():
    out = _df([{"study_accession": "A", "method": "abstained", "n_fills": "0", "note": ""}])
    assert "FAIL" in _sev(vt.check_per_sample(out, {"A"}), "per_sample")


def test_per_sample_fails_on_phantom_study():
    out = _df([{"study_accession": "Z", "method": "direct", "n_fills": "5", "note": ""}])
    assert "FAIL" in _sev(vt.check_per_sample(out, {"A"}), "per_sample")   # Z not in the graded universe


def test_per_sample_warns_when_empty():
    assert "WARN" in _sev(vt.check_per_sample(pd.DataFrame(), {"A"}), "per_sample")


# ── (4) manual papers ─────────────────────────────────────────────────────────────────────────────────
def test_manual_paper_consumed_is_ok():
    grades = _df([{"study_accession": "A", "fulltext_source": "local_pdf"}])
    assert _sev(vt.check_manual_papers(grades, ["A"], {"A"}), "manual_paper") == {"OK"}


def test_manual_paper_orphan_pdf_fails():
    grades = _df([{"study_accession": "A", "fulltext_source": "none"}])   # PDF downloaded, graded w/o full text
    assert "FAIL" in _sev(vt.check_manual_papers(grades, ["A"], {"A"}), "manual_paper")


def test_manual_paper_out_of_selection_ignored():
    grades = _df([{"study_accession": "A", "fulltext_source": "local_pdf"}])
    # PDF Z belongs to another tag's selection → not this tag's concern
    assert vt.check_manual_papers(grades, ["Z"], {"A"}) == []


# ── (5) manual tables ─────────────────────────────────────────────────────────────────────────────────
def test_manual_table_consumed_is_ok():
    out = _df([{"study_accession": "A", "method": "direct", "table": "A.xlsx", "note": ""}])
    supp = {"A": [Path("A.xlsx")]}
    assert _sev(vt.check_manual_tables(out, supp, {"A"}), "manual_table") == {"OK"}


def test_manual_table_unanchored_is_warn_not_fail():
    out = _df([{"study_accession": "A", "method": "abstained", "table": "", "note": "unanchored — no joinable key"}])
    supp = {"A": [Path("A.csv")]}
    sev = _sev(vt.check_manual_tables(out, supp, {"A"}), "manual_table")
    assert sev == {"WARN"}


def test_manual_table_present_but_unconsumed_fails():
    out = _df([{"study_accession": "A", "method": "abstained", "table": "", "note": "gave up"}])
    supp = {"A": [Path("A.csv")]}
    assert "FAIL" in _sev(vt.check_manual_tables(out, supp, {"A"}), "manual_table")


# ── (6) backfill ──────────────────────────────────────────────────────────────────────────────────────
def test_backfill_covered_but_empty_applied_fails():
    gate = _df([{"study_accession": "A", "field": "host", "status": "covered", "n_filled": "10"}])
    assert "FAIL" in _sev(vt.check_backfill(gate, pd.DataFrame()), "backfill")


def test_backfill_covered_with_applied_ok():
    gate = _df([{"study_accession": "A", "field": "host", "status": "covered", "n_filled": "10"}])
    applied = _df([{"study_accession": "A", "sample_accession": "s1", "field": "host", "applied_value": "human"}])
    assert _sev(vt.check_backfill(gate, applied), "backfill") == {"OK"}


def test_backfill_nothing_vouched_ok():
    gate = _df([{"study_accession": "A", "field": "host", "status": "residual_per_sample", "n_filled": "0"}])
    assert _sev(vt.check_backfill(gate, pd.DataFrame()), "backfill") == {"OK"}


# ── (7) fill + conservation ───────────────────────────────────────────────────────────────────────────
def test_fill_pass_no_shrink_no_conservation_fail():
    filled = _df([{"sample_accession": "s1", "country": "USA"}])
    completeness = {"country": (0.62, 0.93)}
    findings = vt.check_fill(filled, completeness, [])
    assert _sev(findings, "fill") == {"OK"} and _sev(findings, "conservation") == {"OK"}


def test_fill_fails_when_field_shrinks():
    filled = _df([{"sample_accession": "s1", "country": ""}])
    findings = vt.check_fill(filled, {"country": (0.62, 0.40)}, [])   # completeness went DOWN
    assert "FAIL" in _sev(findings, "fill")


def test_fill_flags_conservation_failure():
    filled = _df([{"sample_accession": "s1", "country": "USA"}])
    findings = vt.check_fill(filled, {"country": (0.62, 0.93)}, ["[train] INV1 apply: 1 answered never applied"])
    assert "FAIL" in _sev(findings, "conservation")


def test_fill_fails_when_final_empty():
    assert "FAIL" in _sev(vt.check_fill(pd.DataFrame(), {}, []), "fill")


# ── summary parse ─────────────────────────────────────────────────────────────────────────────────────
def test_summary_completeness_parses_bold_filled(tmp_path):
    md = tmp_path / "filled_metadata_summary.md"
    md.write_text(
        "| field | base | filled | agent fills |\n|---|---|---|---|\n"
        "| country | 0.620 | **0.934** | 10740 |\n"
        "| host | 0.444 | **0.924** | 16510 |\n")
    comp = vt._summary_completeness(md, ("country", "collection_date", "isolation_source", "host"))
    assert comp["country"] == (0.620, 0.934) and comp["host"] == (0.444, 0.924)


# ── end-to-end over a tiny on-disk tranche ────────────────────────────────────────────────────────────
def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)


def test_verify_tag_end_to_end_clean(tmp_path):
    data = tmp_path / "data"
    rp = RunPaths(data, "train")
    _write(rp.found_papers_tsv, [{"study_accession": "A"}, {"study_accession": "B"}])
    _write(rp.study_grades_tsv, [
        {"study_accession": "A", "fulltext_source": "local_pdf"},
        {"study_accession": "B", "fulltext_source": "europepmc_fulltext"}])
    _write(rp.per_sample_outcomes, [
        {"study_accession": "A", "method": "direct", "n_fills": "10", "note": "", "table": "A.csv"},
        {"study_accession": "B", "method": "NO_PMCID", "n_fills": "0", "note": "no PMCID"}])
    _write(rp.backfill_gate_report, [{"study_accession": "A", "field": "host", "status": "covered", "n_filled": "3"}])
    _write(rp.backfill_applied, [{"study_accession": "A", "sample_accession": "s1", "field": "host", "applied_value": "human"}])
    _write(rp.filled_metadata, [{"sample_accession": "s1", "country": "USA"}])
    # a manual PDF for A (consumed via local_pdf) and a manual table for A (consumed via direct)
    rp.manual_papers_dir.mkdir(parents=True, exist_ok=True)
    (rp.manual_papers_dir / "A.pdf").write_bytes(b"%PDF-1.4")
    (rp.manual_supp_dir).mkdir(parents=True, exist_ok=True)
    (rp.manual_supp_dir / "A.csv").write_text("x\n")

    findings = vt.verify_tag(data, "train", ("country",))
    assert not [r for r in findings if r["severity"] == "FAIL"], [r for r in findings if r["severity"] == "FAIL"]


def test_verify_tag_end_to_end_catches_orphan_pdf(tmp_path):
    data = tmp_path / "data"
    rp = RunPaths(data, "train")
    _write(rp.found_papers_tsv, [{"study_accession": "A"}])
    _write(rp.study_grades_tsv, [{"study_accession": "A", "fulltext_source": "none"}])   # graded w/o full text
    _write(rp.per_sample_outcomes, [{"study_accession": "A", "method": "abstained", "n_fills": "0", "note": "no joinable table"}])
    _write(rp.backfill_gate_report, [{"study_accession": "A", "field": "host", "status": "residual_per_sample", "n_filled": "0"}])
    _write(rp.filled_metadata, [{"sample_accession": "s1", "country": "USA"}])
    rp.manual_papers_dir.mkdir(parents=True, exist_ok=True)
    (rp.manual_papers_dir / "A.pdf").write_bytes(b"%PDF-1.4")   # downloaded but never consumed → orphan

    findings = vt.verify_tag(data, "train", ("country",))
    assert "FAIL" in _sev(findings, "manual_paper")
