"""Tests for the AST-availability **scoping** report (``evaluation.ast_availability_report``).

The report is a go/no-go input for a possible per-drug extraction round, so the two guarantees that must hold
are: (a) it is spec-gated and app-agnostic — the backbone drug list comes from the spec, and an application
without an ``ast_panel`` (Klebsiella) is a clean no-op; and (b) it reads the two signals faithfully — the
nested ``study_level`` detection grades (booleans lowercased for comparison) and a whole-word drug scan of the
SAME cached full text the grader read, with the grade ``evidence_quote`` as an explicit fallback when no full
text was resolved. It must never imply a per-drug value was extracted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec
from bac_metadata.bac_agentic_metadata.evaluation import ast_availability_report as ast

_APPS = Path(__file__).resolve().parents[1] / "src/bac_metadata/bac_agentic_metadata/applications"


def _spec(app: str) -> AttributeSpec:
    return AttributeSpec.from_yaml(_APPS / app / "attributes.yaml")


def _write_fixture(dd: Path) -> None:
    """Three graded studies: S1 (reports/possible, full text), S2 (no AST, no paper), S3 (reports/retrievable)."""
    g = dd / "run_progress" / "t1" / "grade"
    f = dd / "run_progress" / "t1" / "find"
    ft = dd / "cache" / "fulltext"
    for d in (g, f, ft):
        d.mkdir(parents=True, exist_ok=True)
    grades = [
        {"study_accession": "S1", "study_level": {
            "reports_AST": {"value": True, "grade": "gradeable", "evidence_quote": "MICs to tigecycline"},
            "per_sample_AST": {"value": "possible", "grade": "gradeable", "evidence_quote": ""}}},
        {"study_accession": "S2", "study_level": {
            "reports_AST": {"value": False, "grade": "gradeable", "evidence_quote": ""},
            "per_sample_AST": {"value": "none", "grade": "gradeable", "evidence_quote": ""}}},
        {"study_accession": "S3", "study_level": {
            "reports_AST": {"value": True, "grade": "gradeable", "evidence_quote": ""},
            "per_sample_AST": {"value": "retrievable", "grade": "gradeable", "evidence_quote": ""}}},
    ]
    (g / "study_grades.jsonl").write_text("\n".join(json.dumps(x) for x in grades) + "\n")
    (f / "found_papers.tsv").write_text(
        "study_accession\tchosen_pmid\tchosen_pmcid\tchosen_doi\tchosen_title\n"
        "S1\t111\tPMC1\t10.1/x\tPaper one\n"
        "S2\t\t\t10.2/y\tPaper two\n"
        "S3\t333\tPMC3\t10.3/z\tPaper three\n")
    (ft / "PMC1.xml").write_text(
        "<article><body><sec><p>We tested MICs to clarithromycin and amikacin for all isolates.</p></sec></body></article>")
    (ft / "PMC3.xml").write_text(
        "<article><body><sec><p>Susceptibility to linezolid and imipenem was measured per isolate.</p></sec></body></article>")


# --------------------------------------------------------------------------------------------------------- #
# spec gating — backbone drugs are spec-driven; no ast_panel → empty → the tool no-ops
# --------------------------------------------------------------------------------------------------------- #
def test_backbone_drugs_from_spec():
    assert ast.backbone_drugs(_spec("m_abs")) == [
        "cefoxitin", "amikacin", "tigecycline", "clarithromycin", "linezolid", "imipenem", "tobramycin"]
    assert ast.backbone_drugs(_spec("klebsiella")) == []   # no ast_panel → clean no-op


# --------------------------------------------------------------------------------------------------------- #
# build_records — detection grades + full-text/evidence drug scan, with explicit scan-coverage
# --------------------------------------------------------------------------------------------------------- #
def test_build_records_reads_grades_and_scans_fulltext(tmp_path):
    dd = tmp_path / "data"
    _write_fixture(dd)
    drugs = ast.backbone_drugs(_spec("m_abs"))
    df = ast.build_records(dd, ["t1"], drugs).set_index("study_accession")
    assert len(df) == 3
    # booleans lowercased for stable comparison
    assert df.loc["S1", "reports_AST"] == "true" and df.loc["S2", "reports_AST"] == "false"
    assert df.loc["S1", "per_sample_AST"] == "possible" and df.loc["S3", "per_sample_AST"] == "retrievable"
    # full-text scan picks up drugs present in the cached XML, in panel order
    assert df.loc["S1", "backbone_fulltext"] == "amikacin; clarithromycin"
    assert df.loc["S3", "backbone_fulltext"] == "linezolid; imipenem"
    # a drug named only in the evidence quote is captured there, NOT claimed as a full-text hit
    assert "tigecycline" in df.loc["S1", "backbone_evidence_quote"]
    assert "tigecycline" not in df.loc["S1", "backbone_fulltext"]
    # scan coverage is explicit: full text vs none (S2 has no PMCID and no quote)
    assert df.loc["S1", "text_source"] == "fulltext:PMC1"
    assert df.loc["S2", "text_source"] == "none"


def test_build_report_writes_md_and_orders_worklist(tmp_path):
    dd = tmp_path / "data"
    _write_fixture(dd)
    out = dd / "ast_availability_report.md"
    ast.build_report(dd, ["t1"], _spec("m_abs"), out)
    md = out.read_text()
    tsv = out.with_suffix(".tsv").read_text()
    assert out.exists() and out.with_suffix(".tsv").exists()
    # §1 detection count uses the lowercased boolean correctly (2 studies report AST)
    assert "studies with reports_AST = true: **2**" in md
    # §3 worklist ranks retrievable (S3) above possible (S1); S2 (no AST) is excluded
    assert md.index("| S3 |") < md.index("| S1 |")
    assert "| S2 |" not in md.split("## 3.")[1].split("## 4.")[0]
    # the disclaimer that no per-drug value is extracted is always present
    assert "No per-drug MIC" in md and "does not extract values" in md
    assert "S1\tt1\ttrue" in tsv


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
