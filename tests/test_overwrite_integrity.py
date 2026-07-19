"""Overwrite-integrity guards — the two fixes for fills changing a known base value (PROGRESS_REPORT §8).

David's rule: *a fill never changes an existing value*, with one sanctioned exception — a single-hop
per-sample refinement (a more-specific form of the SAME value, e.g. ``2019`` → ``2019-12-23``). Two
mechanisms broke that rule and are pinned here:

1. **Two-hop joins never overwrite** (``stages._apply_overwrite_guard``). A two-hop join (table row →
   intermediate key → ENA sample) is unreliable; it may fill blanks but must NEVER replace a known ENA
   value — the path that turned correct ENA countries (Canada:Toronto) into UK/USA/Australia in PRJNA778024.
2. **Run→sample collapse: known base wins** (``stages.fill_metadata_table`` via ``fill_for_tag``). The base
   is per-RUN but the output is per-SAMPLE; a value known on ANY run of a sample must beat a blank-run fill,
   and a blank-only source (whole-field / escalation) must never override a known value — the path that turned
   known Non-CF isolates into CF in PRJEB2779 (the headline phenotype).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import stages
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

# ── Improvement 1 — the overwrite guard (two-hop never overwrites) ──────────────────────────────────────


class _FakeJudge:
    """Stand-in LLM: records every fidelity judgment it is asked to make and returns a fixed verdict."""

    def __init__(self, improves: bool = True):
        self._improves = improves
        self.calls: list[str] = []

    def complete_structured(self, *, user, **_kw):
        self.calls.append(user)
        return {"improves": self._improves, "reason": "test"}


class _RaisingJudge:
    """Stand-in LLM that fails the test if the fidelity judge is ever invoked."""

    def complete_structured(self, **_kw):
        raise AssertionError("judge_overwrite_fidelity must NOT be called for a two-hop-only overwrite")


def _fill(sample, field, ena, applied, method):
    return {"study_accession": "A", "sample_accession": sample, "field": field,
            "ena_value": ena, "applied_value": applied, "method": method, "evidence": ""}


def test_two_hop_overwrite_dropped_but_single_hop_overwrite_kept():
    """A two-hop overwrite of a known value is dropped (keep ENA); a single-hop overwrite still gates."""
    fills = [
        _fill("s1", "country", "Canada: Toronto", "United Kingdom", "per_sample_two_hop"),  # must DROP
        _fill("s2", "country", "Canada", "France", "per_sample"),                            # judge-eligible
    ]
    judge = _FakeJudge(improves=True)  # even with the judge approving, the two-hop one must not survive
    kept, note = stages._apply_overwrite_guard(fills, ["country"], judge, None)

    kept_vals = {(k["sample_accession"], k["applied_value"]) for k in kept}
    assert ("s1", "United Kingdom") not in kept_vals   # two-hop overwrite blocked
    assert ("s2", "France") in kept_vals               # single-hop overwrite allowed (judge said improves)
    # the judge only ever saw the single-hop pair — a two-hop value never reaches the betterness layer
    assert len(judge.calls) == 1
    assert "France" in judge.calls[0] and "United Kingdom" not in judge.calls[0]
    assert "two-hop" in note


def test_two_hop_blank_fill_is_kept():
    """A two-hop value may still FILL a blank ENA cell — only overwrites of known values are blocked."""
    fills = [_fill("s1", "country", "", "Germany", "per_sample_two_hop")]
    kept, _note = stages._apply_overwrite_guard(fills, ["country"], _FakeJudge(False), None)
    assert [(k["sample_accession"], k["applied_value"]) for k in kept] == [("s1", "Germany")]


def test_two_hop_only_overwrite_never_calls_the_judge():
    """With no single-hop overwrite, the judge is never invoked and the lone two-hop overwrite is dropped."""
    fills = [_fill("s1", "country", "Canada", "United Kingdom", "per_sample_two_hop")]
    kept, note = stages._apply_overwrite_guard(fills, ["country"], _RaisingJudge(), None)
    assert kept == []
    assert "two-hop" in note


def test_single_hop_date_refinement_kept_lateral_change_dropped():
    """collection_date overwrites are deterministic: a strictly more-specific date is kept, a lateral one isn't."""
    fills = [
        _fill("s1", "collection_date", "2019", "2019-12-23", "per_sample"),  # refinement -> keep
        _fill("s2", "collection_date", "2019", "2020", "per_sample"),        # lateral (same granularity) -> drop
    ]
    kept, _note = stages._apply_overwrite_guard(fills, ["collection_date"], _RaisingJudge(), None)
    kept_vals = {(k["sample_accession"], k["applied_value"]) for k in kept}
    assert ("s1", "2019-12-23") in kept_vals
    assert ("s2", "2020") not in kept_vals


# ── Improvement 2 — run→sample collapse (known base wins) ───────────────────────────────────────────────


def _spec(tmp_path: Path, fields: list[str]) -> AttributeSpec:
    p = tmp_path / "attributes.yaml"
    p.write_text(
        "application: test_app\n"
        "species: Test species\n"
        "taxon_of_interest:\n"
        "  rank: species\n"
        "  name: Test species\n"
        "  scientific_name_match: [Test]\n"
        "attributes:\n"
        "  per_sample_completeness:\n"
        f"    fields: [{', '.join(fields)}]\n"
    )
    return AttributeSpec.from_yaml(p)


def _seed(data: Path, tag: str, attr: str, rows: list[dict]) -> None:
    path = getattr(RunPaths(data, tag), attr)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)


def _filled(data: Path, tag: str) -> pd.DataFrame:
    out = RunPaths(data, tag).filled_metadata
    return pd.read_csv(out, sep="\t", dtype=str, keep_default_na=False).set_index("sample_accession")


def test_known_base_on_a_sibling_run_beats_a_blank_run_fill(tmp_path):
    """PRJEB2779 shape: a sample with run-rows [Non-CF, blank] keeps Non-CF despite a whole-field CF fill."""
    data = tmp_path / "data"
    _seed(data, "train", "backfill_applied", [
        {"study_accession": "A", "sample_accession": "s1", "field": "cf_status",
         "ena_value": "", "applied_value": "CF", "method": "whole_field"},
    ])
    base = pd.DataFrame([
        {"study_accession": "A", "sample_accession": "s1", "cf_status": "Non-CF"},  # one run recorded Non-CF
        {"study_accession": "A", "sample_accession": "s1", "cf_status": ""},         # a sibling run is blank
    ])
    stages.fill_for_tag(data_dir=data, spec=_spec(tmp_path, ["cf_status"]),
                        base=base, fields=["cf_status"], tag="train")
    assert _filled(data, "train").at["s1", "cf_status"] == "Non-CF"


def test_blank_only_source_cannot_override_but_per_sample_refines(tmp_path):
    """Whole-field/escalation never override a known value; a single-hop per-sample refinement still applies."""
    data = tmp_path / "data"
    _seed(data, "train", "backfill_applied", [
        {"study_accession": "A", "sample_accession": "s1", "field": "country",
         "ena_value": "", "applied_value": "Canada", "method": "whole_field"},      # must be withheld
    ])
    _seed(data, "train", "per_sample_applied", [
        {"study_accession": "A", "sample_accession": "s2", "field": "collection_date",
         "ena_value": "2019", "applied_value": "2019-12-23", "method": "per_sample"},  # refinement -> applies
    ])
    base = pd.DataFrame([
        {"study_accession": "A", "sample_accession": "s1", "country": "United Kingdom", "collection_date": ""},
        {"study_accession": "A", "sample_accession": "s2", "country": "", "collection_date": "2019"},
    ])
    stages.fill_for_tag(data_dir=data, spec=_spec(tmp_path, ["country", "collection_date"]),
                        base=base, fields=["country", "collection_date"], tag="train")
    fm = _filled(data, "train")
    assert fm.at["s1", "country"] == "United Kingdom"       # whole-field cannot override a known value
    assert fm.at["s2", "collection_date"] == "2019-12-23"   # per-sample refinement applies


def test_blank_fill_still_lands_when_every_run_is_blank(tmp_path):
    """The guard does not break legit blank-fills: an all-blank sample is still filled by whole-field."""
    data = tmp_path / "data"
    _seed(data, "train", "backfill_applied", [
        {"study_accession": "A", "sample_accession": "s1", "field": "cf_status",
         "ena_value": "", "applied_value": "CF", "method": "whole_field"},
    ])
    base = pd.DataFrame([
        {"study_accession": "A", "sample_accession": "s1", "cf_status": ""},
        {"study_accession": "A", "sample_accession": "s1", "cf_status": ""},
    ])
    stages.fill_for_tag(data_dir=data, spec=_spec(tmp_path, ["cf_status"]),
                        base=base, fields=["cf_status"], tag="train")
    assert _filled(data, "train").at["s1", "cf_status"] == "CF"
