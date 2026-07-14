"""Regression tests for the agentic-metadata silent-failure fixes (2026-07-10/11).

These lock the DETERMINISTic building blocks of the fixes that removed the silent-failure modes plaguing
the curation loop, so the behaviour survives refactors and can be re-verified after a compaction without a
live LLM run. The LLM-dependent behaviours (grader ~95% whole-project rule, overwrite-fidelity judgement,
the concrete PRJEB29738 / PRJNA633565 outcomes) are asserted separately against committed run outputs by
``evaluation/regression_edge_cases.py`` — this file covers the logic that must hold regardless of the model.

Fixes covered:
* ``_is_blank`` — the shared blank definition used by the blank-only / residual logic.
* ``_post_per_sample_gap`` — the deterministic post-per-sample residual driving escalation candidacy.
* escalation candidacy — a field the grader did NOT whole-project-fill (pure decline OR "limbo" proposed
  value) and still materially incomplete is escalated; the grader's proposed value becomes the suggestion.
* ``_reinject_resolved_still_gated`` — a committed curator answer is re-applied while its field is still
  gated, even when it no longer freshly detects (the ~3.7k-cell escalation loss).
* ``null_mask`` — ``clinical`` / ``surveillance`` are blanked pre-fill so the table supplies a real specimen.
* ``pmcid_for_link`` — a PMC URL / bare PMCID resolves offline (the curated-link fallback that stopped
  NO_PMCID silent drops).
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import escalation
from bac_metadata.bac_agentic_metadata.engine.categorise.value_frequencies import null_mask
from bac_metadata.bac_agentic_metadata.engine.europepmc import pmcid_for_link
from bac_metadata.bac_agentic_metadata.engine.stages import (
    ESCALATION_QUEUE_COLUMNS,
    _is_blank,
    _post_per_sample_gap,
    _reinject_resolved_still_gated,
)

FIELDS = ("country", "collection_date", "isolation_source", "host")


def test_is_blank_placeholders_but_not_real_or_null_token():
    for v in ["", "NA", " n/a ", "Unknown", None, "Not Collected", "unspecified"]:
        assert _is_blank(v), v
    # real values, and null-TOKENS (clinical) which are handled by preclean, NOT _is_blank
    for v in ["blood", "0", "clinical", "surveillance", "Philippines"]:
        assert not _is_blank(v), v


def test_null_mask_blanks_clinical_and_surveillance():
    s = pd.Series(["clinical", "Clinical", "Surveillance", "surveillance", "blood",
                   "perirectal surveillance swab", ""])
    tokens = ("0", "unclear", "others", "clinical", "surveillance")
    m = null_mask(s, null_tokens=tokens)
    # whole-cell, case-insensitive: only the bare tokens match; a phrase CONTAINING surveillance does not
    assert list(m) == [True, True, True, True, False, False, False]


def test_post_per_sample_gap_subtracts_only_blank_fills(tmp_path):
    raw = pd.DataFrame({
        "study_accession": ["S"] * 4,
        "sample_accession": ["s1", "s2", "s3", "s4"],
        "country": ["", "", "UK", ""],          # 3 genuinely blank
        "host": ["human", "human", "human", "human"],  # 0 blank
    })
    ps = pd.DataFrame({
        "study_accession": ["S", "S"],
        "sample_accession": ["s1", "s3"],
        "field": ["country", "country"],
        "ena_value": ["", "UK"],                 # s1 was blank (counts), s3 was NOT (an overwrite, ignored)
        "applied_value": ["France", "France"],
    })
    p = tmp_path / "ps.tsv"
    ps.to_csv(p, sep="\t", index=False)
    gap = _post_per_sample_gap(str(p), raw, ("country", "host"))
    assert gap[("S", "country")] == 2   # 3 raw blanks - 1 blank-cell fill = 2 residual
    assert gap[("S", "host")] == 0


def _run_detect(grades, raw, monkeypatch, *, post_gap, n_records, resolution="uniform_propose"):
    """Run detect with the LLM triage stubbed (advisory only) and a minimal evidence object.

    The stub returns an escalating ``resolution`` by default so a limbo field's grader-proposed value flows
    through as the suggestion (fix #1: a suggestion is offered only when the triage escalates).
    """
    monkeypatch.setattr(escalation, "classify_escalation_candidate",
                        lambda *a, **k: {"resolution": resolution, "representative_value": "",
                                         "cluster_theme": "", "evidence_quote": ""})
    ev = type("Ev", (), {"fulltext": type("F", (), {"text": "", "source": "x"})(),
                         "ena_title": "", "ena_description": "", "sizing_row": {}})()
    return escalation.detect_whole_field_escalations(
        grades, raw, spec=None, llm=None, evidence_fn=lambda a: ev,
        fields=("country", "host"), threshold=50, frac=0.75,
        post_gap=post_gap, n_records=n_records)


def test_escalation_escalates_declined_and_limbo_but_not_whole_filled(monkeypatch):
    raw = pd.DataFrame({"study_accession": ["S"] * 100,
                        "sample_accession": [f"s{i}" for i in range(100)],
                        "country": [""] * 100, "host": [""] * 100})
    grades = [{"study_accession": "S", "fulltext_source": "x", "backfill": {
        # limbo: grader proposed a value but would not vouch for it whole-project
        "country": {"applies_whole_project": False, "proposed_value": "Philippines", "evidence_quote": "q"},
        # already whole-project-filled -> NOT an escalation candidate (whole-field backfill handles it)
        "host": {"applies_whole_project": True, "proposed_value": "human", "evidence_quote": "q"},
    }}]
    items = _run_detect(grades, raw, monkeypatch,
                        post_gap={("S", "country"): 100, ("S", "host"): 100}, n_records={"S": 100})
    by = {it.field: it for it in items}
    assert "country" in by, "limbo field must escalate, not be silently dropped"
    assert "host" not in by, "a whole-project-filled field must NOT escalate"
    assert by["country"].suggested_value == "Philippines", "grader's proposed value is the suggestion"


def test_escalation_skips_field_already_complete_after_per_sample(monkeypatch):
    raw = pd.DataFrame({"study_accession": ["S"] * 100,
                        "sample_accession": [f"s{i}" for i in range(100)],
                        "country": [""] * 100, "host": [""] * 100})
    grades = [{"study_accession": "S", "fulltext_source": "x", "backfill": {
        "country": {"applies_whole_project": False, "proposed_value": "", "evidence_quote": ""},
        "host": {"applies_whole_project": False, "proposed_value": "", "evidence_quote": ""},
    }}]
    # per-sample resolved country to >75% (residual 10/100) but left host wide open (residual 90/100)
    items = _run_detect(grades, raw, monkeypatch,
                        post_gap={("S", "country"): 10, ("S", "host"): 90}, n_records={"S": 100})
    fields = {it.field for it in items}
    assert "country" not in fields, "a field per-sample lifted above the completeness gate must not escalate"
    assert "host" in fields
    # gap_samples reflects the RESIDUAL (what escalation would fill), not the raw gap
    assert next(it for it in items if it.field == "host").gap_samples == 90


def test_reinject_resolved_answer_while_still_gated(tmp_path):
    empty = pd.DataFrame(columns=ESCALATION_QUEUE_COLUMNS)  # nothing freshly detected
    master = tmp_path / "curated_escalations.tsv"
    pd.DataFrame({"study_accession": ["S"], "field": ["country"],
                  "answer": ["Philippines"], "answer_note": [""]}).to_csv(master, sep="\t", index=False)

    out = _reinject_resolved_still_gated(empty, sources=[master], keep={"S"},
                                         post_gap={("S", "country"): 700}, n_records={"S": 862}, threshold=50)
    assert len(out) == 1
    assert out.iloc[0]["answer"] == "Philippines"
    assert out.iloc[0]["escalate_trigger"] == "reinjected_committed_decision"

    # NOT re-injected once per-sample has filled the whole field (no residual)
    out2 = _reinject_resolved_still_gated(empty, sources=[master], keep={"S"},
                                          post_gap={("S", "country"): 0}, n_records={"S": 862}, threshold=50)
    assert len(out2) == 0

    # NOT re-injected for a study outside this selection (no cross-tag leakage)
    out3 = _reinject_resolved_still_gated(empty, sources=[master], keep={"OTHER"},
                                          post_gap={("S", "country"): 700}, n_records={"S": 862}, threshold=50)
    assert len(out3) == 0


def _fake_evidence():
    """A minimal StudyEvidence-shaped object for detect (no paper text, no LLM)."""
    return type("Ev", (), {"fulltext": type("F", (), {"text": "", "source": "x"})(),
                           "ena_title": "", "ena_description": "", "sizing_row": {}})()


def test_region_cluster_decision_pure():
    csa = "Central & S. America"
    # multi-country, one region, NO dominant (<95%) -> fires with region only (country suggestion blank)
    d = escalation.region_cluster_decision({"Guatemala": 50, "Honduras": 30, "Nicaragua": 20},
                                           {"Guatemala": csa, "Honduras": csa, "Nicaragua": csa})
    assert d and d["region"] == csa and d["dominant"] == ""
    # one country >=95% -> dominant adopted
    d = escalation.region_cluster_decision({"Kenya": 96, "Uganda": 4}, {"Kenya": "Africa", "Uganda": "Africa"})
    assert d and d["dominant"] == "Kenya"
    # two different regions -> not a cluster
    assert escalation.region_cluster_decision({"UK": 5, "Malawi": 5},
                                              {"UK": "W. Europe", "Malawi": "Africa"}) is None
    # a single country is not a region-cluster question
    assert escalation.region_cluster_decision({"France": 10}, {"France": "W. Europe"}) is None
    # one shared label that is NOT a known region (passthrough of an unrecognised country) -> not a cluster
    assert escalation.region_cluster_decision({"X": 5, "Y": 5}, {"X": "Narnia", "Y": "Narnia"}) is None


def test_country_region_cluster_escalates_deterministically(monkeypatch):
    monkeypatch.setattr(escalation, "_country_region_map",
                        lambda cs: dict.fromkeys(cs, "Central & S. America"))
    monkeypatch.setattr(escalation, "classify_escalation_candidate",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM when region clusters")))
    raw = pd.DataFrame({"study_accession": ["S"] * 100, "sample_accession": [f"s{i}" for i in range(100)],
                        "country": ["Guatemala"] * 50 + ["Honduras"] * 30 + ["Nicaragua"] * 20})
    grades = [{"study_accession": "S", "fulltext_source": "x", "backfill": {
        "country": {"applies_whole_project": False, "proposed_value": "", "evidence_quote": ""}}}]
    items = escalation.detect_whole_field_escalations(
        grades, raw, spec=None, llm=None, evidence_fn=lambda a: _fake_evidence(),
        fields=("country",), threshold=50, frac=0.75,
        post_gap={("S", "country"): 60}, n_records={"S": 100})
    it = items[0]
    assert it.suggested_value == "" and it.region_hint == "Central & S. America"
    assert it.resolution == "tight_cluster_escalate"


def test_collection_date_escalation_is_deterministic_no_llm(monkeypatch):
    monkeypatch.setattr(escalation, "classify_escalation_candidate",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM for collection_date")))
    raw = pd.DataFrame({"study_accession": ["S"] * 100, "sample_accession": [f"s{i}" for i in range(100)],
                        "collection_date": [""] * 100})
    # a pre-2010 2-5yr span carries the midpoint as the suggestion; a recent one escalates blank
    grades = [{"study_accession": "S", "fulltext_source": "x", "backfill": {
        "collection_date": {"applies_whole_project": False, "proposed_value": "2005-07-02", "evidence_quote": "q",
                            "date_decision": "escalate_midpoint", "date_span_months": 54,
                            "earliest_date": "2003", "latest_date": "2007"}}}]
    it = escalation.detect_whole_field_escalations(
        grades, raw, spec=None, llm=None, evidence_fn=lambda a: _fake_evidence(),
        fields=("collection_date",), threshold=50, frac=0.75,
        post_gap={("S", "collection_date"): 100}, n_records={"S": 100})[0]
    assert it.suggested_value == "2005-07-02" and it.resolution == "uniform_propose"

    grades[0]["backfill"]["collection_date"].update(
        {"proposed_value": "", "date_decision": "escalate_blank", "earliest_date": "2015", "latest_date": "2019"})
    it = escalation.detect_whole_field_escalations(
        grades, raw, spec=None, llm=None, evidence_fn=lambda a: _fake_evidence(),
        fields=("collection_date",), threshold=50, frac=0.75,
        post_gap={("S", "collection_date"): 100}, n_records={"S": 100})[0]
    assert it.suggested_value == "" and it.resolution == "wide_mix_skip"


def test_pmcid_for_link_resolves_pmc_offline():
    assert pmcid_for_link("https://pmc.ncbi.nlm.nih.gov/articles/PMC7244338/") == "PMC7244338"
    assert pmcid_for_link("PMC10232788") == "PMC10232788"
    assert pmcid_for_link("") is None
    # a link with no PMCID / DOI / PMID resolves to None without any network call
    assert pmcid_for_link("https://pathogen.watch/collection/klebnet;") is None
