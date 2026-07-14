"""Unit tests for the escalating-context grade ladder (``grader.grade_accession`` + ``spec.grade_context_tiers``).

The grader reads the paper in ascending budget tiers (e.g. 10k → 50k → 250k chars), climbing to the next tier
ONLY when it self-reports ``full_text_would_help`` and there is more text to show. This collapses per-call token
cost to the cheapest tier for most studies. These tests lock the climb/stop logic offline (a fake LLM), with no
network and no real model.
"""

from __future__ import annotations

from pathlib import Path

from bac_metadata.bac_agentic_metadata.engine import grader
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

_SPEC = AttributeSpec.from_yaml(
    Path(__file__).resolve().parents[1]
    / "src/bac_metadata/bac_agentic_metadata/applications/klebsiella/attributes.yaml"
)


class _FakeFullText:
    def __init__(self, n_chars: int):
        self.text = "x" * n_chars
        self.source = "test"
        self.is_full_text = True
        self.title = "t"


class _FakeLLM:
    """Returns a queued grade dict per call and records how many calls (tiers) were made."""

    model = "fake"

    def __init__(self, needs_more: list[bool]):
        self._outs = [_grade_out(nm) for nm in needs_more]
        self.calls = 0

    def complete_structured(self, **_kwargs) -> dict:
        out = self._outs[min(self.calls, len(self._outs) - 1)]
        self.calls += 1
        return out


def _grade_out(full_text_would_help: bool) -> dict:
    return {
        "study_type": {"value": "observational", "evidence_quote": ""},
        "study_level": {},
        "paper_coverage": {"paper_records_in_taxon": None, "basis": ""},
        "backfill": {"collection_date": {"proposed_value": None, "applies_whole_project": False,
                                         "evidence_quote": "", "earliest_date": None, "latest_date": None}},
        "needs_manual_download": False,
        "full_text_would_help": full_text_would_help,
        "notes": "",
    }


def _grade(llm, n_chars, tiers=(10, 50, 250)):
    return grader.grade_accession(_SPEC, llm, accession="S", fulltext=_FakeFullText(n_chars),
                                  ena_taxon_samples=100, context_tiers=tiers)


def test_spec_ladder_from_yaml_sorted_ascending():
    assert _SPEC.grade_context_tiers == (10000, 50000, 250000)
    assert _SPEC.max_paper_chars == 250000  # top of the ladder = the escalation-triage single-pass budget


def test_firm_at_first_tier_reads_once():
    llm = _FakeLLM([False])  # firm from the abstract-sized slice
    r = _grade(llm, n_chars=300)
    assert llm.calls == 1
    assert r.grade_context_chars == 10 and r.full_text_would_help is False


def test_climbs_all_tiers_when_never_firm():
    llm = _FakeLLM([True, True, True])  # keeps asking for more; paper longer than the top tier
    r = _grade(llm, n_chars=300)
    assert llm.calls == 3
    assert r.grade_context_chars == 250 and r.full_text_would_help is True


def test_stops_when_a_tier_shows_the_whole_paper():
    llm = _FakeLLM([True, True, True])  # asks for more, but tier 2 (50) already exceeds the 30-char paper
    r = _grade(llm, n_chars=30)
    assert llm.calls == 2 and r.grade_context_chars == 30


def test_short_paper_is_a_single_pass_even_if_flagged():
    llm = _FakeLLM([True])  # first tier already covers the whole 5-char paper — nothing more to show
    r = _grade(llm, n_chars=5)
    assert llm.calls == 1 and r.grade_context_chars == 5


def test_single_tier_fallback_behaves_like_one_pass():
    llm = _FakeLLM([True, True])
    r = grader.grade_accession(_SPEC, llm, accession="S", fulltext=_FakeFullText(9_999),
                               ena_taxon_samples=100, max_chars=120_000)  # no context_tiers -> single pass
    assert llm.calls == 1 and r.grade_context_chars == 9_999


def test_parallel_grade_output_is_order_stable(tmp_path, monkeypatch):
    """workers>1 must produce byte-identical, size-desc-ordered grades — order comes from slots, not completion."""
    import pandas as pd

    from bac_metadata.bac_agentic_metadata.engine import stages

    sizing = tmp_path / "sizing.tsv"
    pd.DataFrame({
        "study_accession": ["S1", "S2", "S3", "S4"],
        "ena_taxon_samples": [400, 300, 200, 100],  # select_sizing_rows sorts size-desc
        "ena_total_samples": [400, 300, 200, 100],
        "ena_total_runs": [0, 0, 0, 0],
        "by_scientific_name": ["", "", "", ""],
        "fold": ["train"] * 4,
    }).to_csv(sizing, sep="\t", index=False)

    monkeypatch.setattr(stages, "resolve_fulltext_for_accession",
                        lambda acc, link, md, *, fulltext_cache: _FakeFullText(300))
    monkeypatch.setattr(stages, "study_title_and_description",
                        lambda acc, *, cache_dir: {"study_title": "", "study_description": ""})

    caches = stages.StageCaches(llm=tmp_path / "llm", ena=tmp_path / "ena", find=tmp_path / "find",
                                fulltext=tmp_path / "ft", per_sample_supp=tmp_path / "pss")

    def run(workers: int, tag: str):
        out_tsv = tmp_path / f"{tag}.tsv"
        stages.grade(spec=_SPEC, sizing_path=sizing, accessions=None, folds=["train"],
                     paper_links={}, classifications={}, manual_papers_dir=tmp_path / "manual",
                     out_jsonl=tmp_path / f"{tag}.jsonl", out_tsv=out_tsv, llm=_FakeLLM([False]),
                     model="fake", caches=caches, context_tiers=(10, 50, 250), workers=workers)
        return pd.read_csv(out_tsv, sep="\t")

    seq = run(1, "seq")
    par = run(4, "par")
    assert list(seq["study_accession"]) == ["S1", "S2", "S3", "S4"]  # stable size-desc order
    pd.testing.assert_frame_equal(seq, par)
