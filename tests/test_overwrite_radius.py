"""Overwrite-radius classification — protected violation vs gated overwrite vs same-year date refinement.

The gate's correctness for BOTH applications rides on this split: a change to a ``never_overwrite`` field is a
hard failure, a fidelity-judge-approved overwrite of a non-protected field is allowed (reported only), and a
same-year ``collection_date`` refinement is neither.
"""
from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.overwrite_radius import overwrite_radius


def _by_field(rows: list[dict]) -> dict[str, dict]:
    """Index the per-field report rows by field name."""
    return {r["field"]: r for r in rows}


def test_protected_violation_vs_gated_overwrite_vs_refinement() -> None:
    """cf_status change = hard violation; non-protected change = gated overwrite; date prefix = refinement."""
    base = pd.DataFrame({
        "sample_accession": ["s1", "s2", "s3", "s4", "s5"],
        "cf_status":        ["CF", "", "", "", "non-CF"],
        "isolation_source": ["faeces", "", "sputum", "", ""],
        "collection_date":  ["2015", "", "", "", ""],
    })
    filled = pd.DataFrame({
        "sample_accession": ["s1", "s2", "s3", "s4", "s5"],
        "cf_status":        ["non-CF", "CF", "", "", "non-CF"],   # s1 CF->non-CF violation; s2 blank->CF fill (ok)
        "isolation_source": ["blood", "", "sputum", "", ""],       # s1 faeces->blood gated; s3 unchanged
        "collection_date":  ["2015-06", "", "", "", ""],           # s1 2015->2015-06 refinement
    })
    rows = _by_field(overwrite_radius(
        base, filled, ["cf_status", "isolation_source", "collection_date"], ["cf_status"]))

    assert rows["cf_status"]["n_known_base"] == 2                  # s1, s5 (s2/s3/s4 blank)
    assert rows["cf_status"]["protected_violation"] == 1          # s1 CF -> non-CF
    assert rows["cf_status"]["gated_overwrite"] == 0              # protected field: never "gated"

    assert rows["isolation_source"]["protected_violation"] == 0
    assert rows["isolation_source"]["gated_overwrite"] == 1       # s1 faeces -> blood (allowed, reported)

    assert rows["collection_date"]["date_refinement"] == 1        # 2015 -> 2015-06
    assert rows["collection_date"]["protected_violation"] == 0
    assert rows["collection_date"]["gated_overwrite"] == 0


def test_blank_fill_is_never_a_change() -> None:
    """A field blank in the base -> any filled value is a blank-fill, never counted as a change/violation."""
    base = pd.DataFrame({"sample_accession": ["s1", "s2"], "cf_status": ["", ""]})
    filled = pd.DataFrame({"sample_accession": ["s1", "s2"], "cf_status": ["CF", "non-CF"]})
    row = _by_field(overwrite_radius(base, filled, ["cf_status"], ["cf_status"]))["cf_status"]
    assert row["n_known_base"] == 0
    assert row["changed"] == 0
    assert row["protected_violation"] == 0


def test_no_protected_fields_means_overwrites_are_gated_not_failures() -> None:
    """Klebsiella shape (protected=()): a known-value overwrite is gated (reported), never a violation."""
    base = pd.DataFrame({"sample_accession": ["s1"], "isolation_source": ["clinical sample"]})
    filled = pd.DataFrame({"sample_accession": ["s1"], "isolation_source": ["rectal"]})
    row = _by_field(overwrite_radius(base, filled, ["isolation_source"], []))["isolation_source"]
    assert row["gated_overwrite"] == 1
    assert row["protected_violation"] == 0
