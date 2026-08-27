"""The agentic category-tail remap — targeted, and leaves everything else (and ambiguous codes) alone."""
from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.combine.recategorise_agentic_tail import recategorise_tail


def test_remaps_tail_values_only_and_leaves_ambiguous_and_canonical() -> None:
    """Clear tail values fold into buckets; canonical buckets and deliberately-left codes are untouched."""
    df = pd.DataFrame({
        "region": ["Saint Kitts and Nevis", "W. Europe", "Middle East"],
        "host_category": ["Galleria mellonella", "human", "Feed"],  # Feed is deliberately left
        "isolation_source_category": ["UTI", "blood", "TASP"],       # TASP is deliberately left
    })
    out, changed = recategorise_tail(df)
    assert out["region"].tolist() == ["Central & S. America", "W. Europe", "M. East, Central Asia"]
    assert out["host_category"].tolist() == ["insect", "human", "Feed"]
    assert out["isolation_source_category"].tolist() == ["urine", "blood", "TASP"]
    assert changed == {"region": 2, "host_category": 1, "isolation_source_category": 1}


def test_null_placeholder_blanked_and_culture_bucketed() -> None:
    """`NO SOURCE` → blank; the lab-culture family → the 'unhelpful' bucket."""
    df = pd.DataFrame({"isolation_source_category": ["NO SOURCE", "Biofilm culture", "SPUT"]})
    out, _ = recategorise_tail(df)
    assert out["isolation_source_category"].tolist() == [
        "", "lab, hospital or facility (unhelpful)", "lower respiratory, endotracheal"]


def test_missing_columns_are_skipped() -> None:
    """A table lacking a category column is handled without error."""
    out, changed = recategorise_tail(pd.DataFrame({"isolation_source_category": ["UTI"]}))
    assert changed == {"isolation_source_category": 1}
    assert "region" not in changed
