"""Unit tests for ``tl.aggregate_species_reference``."""

from __future__ import annotations

import pandas as pd

from bac_panaroo.gpa_analysis.aggregate_species_reference import (
    LEVELS_ALL,
    _modal_pick,
    aggregate_species_reference,
)


def test_modal_pick_basic():
    s = pd.Series(["A", "A", "B", "C"])
    assert _modal_pick(s) == ("A", 2)


def test_modal_pick_tie_resolves_lexicographically():
    """A and B both at 2 -> lexicographically smallest ("A") wins."""
    s = pd.Series(["B", "B", "A", "A", "C"])
    assert _modal_pick(s) == ("A", 2)


def test_modal_pick_empty():
    assert _modal_pick(pd.Series([], dtype=object)) == (None, 0)


def test_modal_pick_all_nan():
    assert _modal_pick(pd.Series([None, None])) == (None, 0)


def test_aggregate_species_reference_basic():
    df = pd.DataFrame(
        {
            "Sample": ["S1", "S2", "S3", "S4", "S5"],
            "run": [
                "non_kpsc_species_X",
                "non_kpsc_species_X",
                "non_kpsc_species_X",
                "SL11",
                "SL11",
            ],
            "species": ["Klebsiella X", "Klebsiella X", "Klebsiella X",
                        "Klebsiella pneumoniae", "Klebsiella pneumoniae"],
            "ref_d": ["REF1", "REF1", "REF2", "REFkp", "REFkp"],
            "shared_d": [100, 110, 80, 4500, 4600],
        }
    )
    out = aggregate_species_reference(df)
    by = out.set_index("species")
    assert by.loc["Klebsiella X", "modal_ref_d"] == "REF1"
    assert by.loc["Klebsiella X", "modal_ref_d_count"] == 2
    assert by.loc["Klebsiella X", "n_samples"] == 3
    assert by.loc["Klebsiella X", "n_runs"] == 1
    assert by.loc["Klebsiella X", "median_shared_d"] == 100.0
    assert by.loc["Klebsiella pneumoniae", "modal_ref_d"] == "REFkp"
    assert by.loc["Klebsiella pneumoniae", "n_samples"] == 2
    assert by.loc["Klebsiella pneumoniae", "median_shared_d"] == 4550.0


def test_aggregate_species_reference_non_kpsc_only():
    df = pd.DataFrame(
        {
            "Sample": ["S1", "S2", "S3"],
            "run": ["non_kpsc_species_X", "SL11", "SL11"],
            "species": ["Klebsiella X", "Klebsiella pneumoniae", "Klebsiella pneumoniae"],
            "ref_d": ["R1", "R2", "R2"],
            "shared_d": [10, 20, 30],
        }
    )
    out = aggregate_species_reference(df, non_kpsc_only=True)
    assert len(out) == 1
    assert out["species"].iloc[0] == "Klebsiella X"


def test_aggregate_species_reference_all_levels_ties_resolve_lex():
    df = pd.DataFrame(
        {
            "Sample": ["S1", "S2"],
            "run": ["non_kpsc_species_X", "non_kpsc_species_X"],
            "species": ["Klebsiella X", "Klebsiella X"],
            "ref_f": ["F1", "F1"],
            "shared_f": [50, 60],
            "ref_d": ["D1", "D1"],
            "shared_d": [70, 80],
            "ref_c": ["C2", "C1"],  # tie -> lexicographic C1
            "shared_c": [90, 100],
            "ref_b": ["B2", "B1"],  # tie -> B1
            "shared_b": [110, 120],
            "ref_a": ["A2", "A1"],  # tie -> A1
            "shared_a": [130, 140],
        }
    )
    out = aggregate_species_reference(df, levels=LEVELS_ALL)
    row = out.iloc[0]
    assert row["modal_ref_f"] == "F1"
    assert row["modal_ref_d"] == "D1"
    assert row["modal_ref_c"] == "C1"
    assert row["modal_ref_b"] == "B1"
    assert row["modal_ref_a"] == "A1"


def test_aggregate_species_reference_handles_nan_refs():
    df = pd.DataFrame(
        {
            "Sample": ["S1", "S2"],
            "run": ["non_kpsc_species_X", "non_kpsc_species_X"],
            "species": ["Klebsiella X", "Klebsiella X"],
            "ref_d": [None, None],
            "shared_d": [float("nan"), float("nan")],
        }
    )
    out = aggregate_species_reference(df)
    row = out.iloc[0]
    assert row["modal_ref_d"] is None
    assert row["modal_ref_d_count"] == 0
    assert pd.isna(row["median_shared_d"])
