"""Unit tests for the blank-fill vs overwrite split in ``engine.backfill.value_correctness``.

The wrap-up report's §5b/§5c depend on this split being exact: a fill of a **blank** ENA cell (the
positive value-add) must be scored apart from an **overwrite** of a real ENA value (scored against the
parsed-ENA gold it replaces, so low by construction). The discriminator is the applied row's ``ena_value``.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill


def _row(sample, field, ena, applied):
    return {"study_accession": "PRJX", "sample_accession": sample, "field": field,
            "ena_value": ena, "applied_value": applied, "method": "per_sample", "evidence": ""}


def test_blank_and_overwrite_split_is_exact():
    applied = pd.DataFrame([
        _row("S1", "isolation_source", "", "blood"),          # blank-fill, matches gold → blank correct
        _row("S2", "isolation_source", "", "urine"),          # blank-fill, gold blank → not scored
        _row("S3", "isolation_source", "clinical sample", "rectal"),  # overwrite, gold=ENA → wrong
        _row("S4", "isolation_source", "swab", "swab"),       # overwrite, matches gold → overwrite correct
    ])
    gold = pd.DataFrame({"sample_accession": ["S1", "S2", "S3", "S4"],
                         "isolation_source": ["blood", "", "clinical sample", "swab"]})
    r = backfill.value_correctness(applied, gold, fields=("isolation_source",)).iloc[0]

    assert r["filled"] == 4 and r["has_gold"] == 3           # S2 has no gold
    # blank-fills: S1 (has gold, correct), S2 (no gold) → 1 scoreable, 1 correct
    assert r["n_blank_fill"] == 2 and r["has_gold_blank"] == 1
    assert r["correct_blank_fill"] == 1 and r["acc_blank_fill"] == 1.0
    # overwrites: S3 (wrong — gold is the replaced ENA), S4 (correct) → 2 scoreable, 1 correct
    assert r["n_overwrite"] == 2 and r["has_gold_overwrite"] == 2
    assert r["correct_overwrite"] == 1 and r["acc_overwrite"] == 0.5


def test_missing_ena_value_column_treats_all_as_blank_fills():
    # whole-field backfill_applied has no ena_value column → everything is a positive blank-fill
    applied = pd.DataFrame([{"study_accession": "PRJX", "sample_accession": "S1",
                             "field": "host", "applied_value": "human"}])
    gold = pd.DataFrame({"sample_accession": ["S1"], "host": ["human"]})
    r = backfill.value_correctness(applied, gold, fields=("host",)).iloc[0]
    assert r["n_blank_fill"] == 1 and r["n_overwrite"] == 0
    assert r["acc_blank_fill"] == 1.0
