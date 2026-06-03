"""Boundary tests for `bac_genomad.viral_analysis.viral_brackets`.

Half-open semantics: ``[lo, hi)``. A length equal to the lower edge is IN
the bracket, equal to the upper edge it is NOT.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bac_genomad.viral_analysis.viral_brackets import (
    SGLD_V_HI,
    SGLD_V_LO,
    WBR_V_HI,
    WBR_V_LO,
    assign_brackets,
    classify_length,
)


def test_constants_are_consistent_with_2sigma_rule() -> None:
    # Sanity: ±2σ widths come out to the canonical values.
    assert SGLD_V_LO == 106_858
    assert SGLD_V_HI == 115_178
    assert WBR_V_LO == 52_180
    assert WBR_V_HI == 56_820


def test_classify_length_strictly_inside_each_bracket() -> None:
    assert classify_length(200_000) == "above_upper"
    assert classify_length(111_018) == "Sgld_v"      # exact upper-peak centre
    assert classify_length(75_000) == "between"
    assert classify_length(54_500) == "Wbr_v"        # exact lower-peak centre
    assert classify_length(10_000) == "below_lower"


def test_classify_length_at_every_cut_boundary() -> None:
    # Lower edge IS in the upper bracket (half-open intervals).
    assert classify_length(WBR_V_LO) == "Wbr_v"           # 52_180 → Wbr_v, not below_lower
    assert classify_length(WBR_V_LO - 1) == "below_lower"

    # Upper edge of Wbr_v is exclusive — that point is "between".
    assert classify_length(WBR_V_HI) == "between"         # 56_820 → between, not Wbr_v
    assert classify_length(WBR_V_HI - 1) == "Wbr_v"

    # Sgld_v lower edge inclusive.
    assert classify_length(SGLD_V_LO) == "Sgld_v"         # 106_858
    assert classify_length(SGLD_V_LO - 1) == "between"

    # Sgld_v upper edge exclusive — beyond it is "above_upper".
    assert classify_length(SGLD_V_HI) == "above_upper"    # 115_178
    assert classify_length(SGLD_V_HI - 1) == "Sgld_v"


def test_assign_brackets_matches_classify_length_elementwise() -> None:
    samples = [
        0, 1_000, WBR_V_LO - 1, WBR_V_LO, 54_500, WBR_V_HI - 1, WBR_V_HI,
        75_000, SGLD_V_LO - 1, SGLD_V_LO, 111_018, SGLD_V_HI - 1, SGLD_V_HI, 200_000,
    ]
    series = pd.Series(samples, dtype=int)
    got = assign_brackets(series)
    expected = [classify_length(x) for x in samples]
    assert got.tolist() == expected


def test_assign_brackets_handles_missing_and_non_numeric() -> None:
    series = pd.Series([54_500, None, np.nan, "garbage", 200_000])
    got = assign_brackets(series)
    assert got.iloc[0] == "Wbr_v"
    assert pd.isna(got.iloc[1])
    assert pd.isna(got.iloc[2])
    assert pd.isna(got.iloc[3])
    assert got.iloc[4] == "above_upper"
