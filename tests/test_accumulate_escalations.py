"""Regression tests for the curated-escalations master merge (``accumulate.accumulate_escalations``).

The master ``curated_escalations.tsv`` is the precious, non-regenerable curator store. Rebuilding it purely
from the per-band ``decisions_needed_<tag>.tsv`` files (the old behaviour) silently DELETED any committed
answer whose band file had since been regenerated without it — the exact silent-loss step-bug this project
targets. These tests lock the safe behaviour: the existing master is always preserved, a fresh answer updates
it, a fresh skip never overrides a committed answer, and regenerable auto-skips are never promoted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.accumulate import accumulate_escalations


def _write_decisions(data_dir: Path, tag: str, rows: list[dict]) -> None:
    p = data_dir / "study_lv_attributes" / "escalation"
    p.mkdir(parents=True, exist_ok=True)
    cols = ["study_accession", "field", "resolution", "suggested_value", "answer", "answer_note"]
    pd.DataFrame(rows).reindex(columns=cols).fillna("").to_csv(p / f"decisions_needed_{tag}.tsv",
                                                               sep="\t", index=False)


def _write_master(out_dir: Path, rows: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_dir / "curated_escalations.tsv", sep="\t", index=False)


def test_master_is_preserved_updated_and_never_polluted_by_autoskip(tmp_path):
    data = tmp_path / "data"
    out = data / "curated"

    # existing master: a committed answer whose band file no longer lists it (D), a committed curator skip (E),
    # a value that a fresh walk will update (F), and an answer a fresh skip must NOT override (G).
    _write_master(out, [
        {"study_accession": "D", "field": "host", "answer": "poultry", "answer_note": "", "tag": "test"},
        {"study_accession": "E", "field": "country", "answer": "",
         "answer_note": "curator skip: no single whole-field value", "tag": "test"},
        {"study_accession": "F", "field": "host", "answer": "human", "answer_note": "", "tag": "test"},
        {"study_accession": "G", "field": "isolation_source", "answer": "blood", "answer_note": "", "tag": "train"},
    ])
    # fresh train decisions: a new answer (A), a regenerable auto-skip (B — must NOT be promoted), an
    # unresolved blank (C — not promoted), an update to F, and a skip on G (must not beat G's committed answer).
    _write_decisions(data, "train", [
        {"study_accession": "A", "field": "isolation_source", "resolution": "uniform_propose",
         "answer": "blood", "answer_note": ""},
        {"study_accession": "B", "field": "host", "resolution": "wide_mix_skip",
         "answer": "", "answer_note": "auto-skip: wide mix — no single whole-study value"},
        {"study_accession": "C", "field": "country", "resolution": "wide_mix_skip",
         "answer": "", "answer_note": ""},
        {"study_accession": "F", "field": "host", "resolution": "uniform_propose",
         "answer": "Dog", "answer_note": ""},
        {"study_accession": "G", "field": "isolation_source", "resolution": "wide_mix_skip",
         "answer": "", "answer_note": "curator skip: genuinely wide"},
    ])

    res = accumulate_escalations(data, ["train"], out)
    m = {(r.study_accession, r.field): (r.answer, r.answer_note) for r in res.itertuples()}

    assert m[("D", "host")][0] == "poultry"            # preserved — band file no longer lists it
    assert m[("E", "country")][1].startswith("curator skip")  # committed curator skip preserved
    assert m[("A", "isolation_source")][0] == "blood"  # new answer folded in
    assert m[("F", "host")][0] == "Dog"                # fresh walk updates the committed value
    assert m[("G", "isolation_source")][0] == "blood"  # a fresh skip does NOT override a committed answer
    assert ("B", "host") not in m                       # auto-skip is regenerable → never promoted
    assert ("C", "country") not in m                    # unresolved blank → not promoted


def test_first_build_has_no_master_to_preserve(tmp_path):
    data = tmp_path / "data"
    out = data / "curated"
    _write_decisions(data, "train", [
        {"study_accession": "A", "field": "host", "resolution": "uniform_propose",
         "answer": "human", "answer_note": ""},
    ])
    res = accumulate_escalations(data, ["train"], out)  # no pre-existing master
    assert list(res["study_accession"]) == ["A"]
