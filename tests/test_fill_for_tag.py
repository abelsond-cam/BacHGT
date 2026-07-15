"""Smoke tests for the shared fill primitive (``stages.fill_for_tag``) + its conservation invariant.

``fill_for_tag`` is the ONE fill code path the driver, ``escalate --apply`` and ``cli.fill`` all go through:
rebuild ``filled_metadata_<tag>.tsv`` from the current applied files. These tests lock the two properties the
generalisation depends on — (1) an escalation fill for a study actually lands in the final table, and every
study in the universe survives even if it had no fill (no silent shrink); (2) after the rebuild the
content-based INV3 invariant passes, i.e. ``escalate --apply``'s rebuild-then-gate step leaves the final table
consistent. This is the class of silent-staleness bug the whole workstream targets, tested end to end offline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import escalation_conservation as ec
from bac_metadata.bac_agentic_metadata.engine import stages
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

_MIN_SPEC = """\
application: test_app
species: Test species
taxon_of_interest:
  rank: species
  name: Test species
  scientific_name_match: [Test]
attributes:
  per_sample_completeness:
    fields: [country]
"""


def _spec(tmp_path: Path) -> AttributeSpec:
    p = tmp_path / "attributes.yaml"
    p.write_text(_MIN_SPEC)
    return AttributeSpec.from_yaml(p)


def _seed_applied(data: Path, tag: str) -> None:
    esc = data / "study_lv_attributes" / "escalation"
    esc.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"study_accession": "A", "sample_accession": "s1", "field": "country",
         "ena_value": "", "applied_value": "USA", "method": "curator_escalation"},
        {"study_accession": "A", "sample_accession": "s2", "field": "country",
         "ena_value": "", "applied_value": "USA", "method": "curator_escalation"},
    ]).to_csv(esc / f"escalation_applied_{tag}.tsv", sep="\t", index=False)


def test_fill_for_tag_lands_escalation_and_keeps_full_universe(tmp_path):
    data = tmp_path / "data"
    _seed_applied(data, "train")
    # Base holds the FULL universe: study A (the applied one) + study B (no fill — must survive, stay blank).
    base = pd.DataFrame([
        {"study_accession": "A", "sample_accession": "s1", "country": ""},
        {"study_accession": "A", "sample_accession": "s2", "country": ""},
        {"study_accession": "B", "sample_accession": "s3", "country": ""},
    ])
    filled = stages.fill_for_tag(data_dir=data, spec=_spec(tmp_path), base=base, fields=["country"], tag="train")

    out = data / "sample_lv_attributes" / "enriched" / "filled_metadata_train.tsv"
    assert out.exists()
    fm = pd.read_csv(out, sep="\t", dtype=str, keep_default_na=False).set_index("sample_accession")
    assert fm.at["s1", "country"] == "USA" and fm.at["s2", "country"] == "USA"   # escalation reached final
    assert set(fm.index) == {"s1", "s2", "s3"}                                    # no silent shrink
    assert (fm.at["s3", "country"] or "") == ""                                   # unfilled study stays blank
    assert len(filled) == 3


def test_apply_then_gate_is_consistent(tmp_path):
    """The escalate --apply contract: after fill_for_tag rebuilds the final table, INV3 (content-based) passes."""
    data = tmp_path / "data"
    _seed_applied(data, "train")
    base = pd.DataFrame([
        {"study_accession": "A", "sample_accession": "s1", "country": ""},
        {"study_accession": "A", "sample_accession": "s2", "country": ""},
    ])
    stages.fill_for_tag(data_dir=data, spec=_spec(tmp_path), base=base, fields=["country"], tag="train")
    fails = ec.verify_tags(data, ["train"], amend=False, include_master=False, out=lambda _m: None)
    assert not fails


def test_gate_catches_stale_final_before_rebuild(tmp_path):
    """Without the rebuild (a stale final missing the applied cells), INV3 must loudly fail — the caught bug."""
    data = tmp_path / "data"
    _seed_applied(data, "train")
    enriched = data / "sample_lv_attributes" / "enriched"
    enriched.mkdir(parents=True, exist_ok=True)
    # Stale final: s1 present, s2's escalation cell blank (the exact PRJEB19322-shape silent drop).
    pd.DataFrame([
        {"sample_accession": "s1", "country": "USA"},
        {"sample_accession": "s2", "country": ""},
    ]).to_csv(enriched / "filled_metadata_train.tsv", sep="\t", index=False)
    fails = ec.verify_tags(data, ["train"], amend=False, include_master=False, out=lambda _m: None)
    assert any("INV3" in f for f in fails)
