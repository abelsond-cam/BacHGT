"""Combine step (iii) — the two gated writes: apply approved overwrites, and the post-Kleborate delist.

These pin the decisions that must never drift: an overwrite writes the approved value + a `_agent_overwrote`
flag and refuses any non-clinical field; the delist is dry-run-safe, clamps cohort + quality flags on
evolutionary rows, and leaves the taxonomic `is_kpsc` alone.
"""
from __future__ import annotations

import pandas as pd
import pytest

from bac_metadata.bac_agentic_metadata.combine.apply_gated_overwrites import apply_gated_overwrites
from bac_metadata.bac_agentic_metadata.combine.delist_evolutionary import delist_evolutionary


def _canonical() -> pd.DataFrame:
    """A tiny canonical frame; s2 appears twice (a duplicated sample_accession, as in v1)."""
    return pd.DataFrame({
        "sample_accession": ["s1", "s2", "s2", "s3"],
        "country":          ["Switzerland", "clinical material", "clinical material", "USA"],
        "isolation_source": ["blood", "clinical material", "clinical material", "urine"],
    })


def test_apply_writes_value_flag_and_is_dup_aware() -> None:
    """Approved overwrite writes applied_value into every matching row + sets the _agent_overwrote flag."""
    approved = pd.DataFrame({"sample_accession": ["s1", "s2"], "field": ["country", "isolation_source"],
                             "applied_value": ["Myanmar", "BLOOD"]})
    out, stats = apply_gated_overwrites(_canonical(), approved, reparse=False)
    assert out.loc[out["sample_accession"] == "s1", "country"].tolist() == ["Myanmar"]
    assert out.loc[out["sample_accession"] == "s2", "isolation_source"].tolist() == ["BLOOD", "BLOOD"]  # both rows
    assert out.loc[out["sample_accession"] == "s1", "country_agent_overwrote"].tolist() == [True]
    assert stats["rows_written"] == 3  # s1 country (1) + s2 iso (2)
    assert stats["per_field"]["isolation_source"]["rows_written"] == 2


def test_apply_reports_unmatched_and_leaves_others_untouched() -> None:
    """A sample not in the canonical table is counted, not applied; unrelated rows are unchanged."""
    approved = pd.DataFrame({"sample_accession": ["s1", "sX"], "field": ["country", "country"],
                             "applied_value": ["Myanmar", "Narnia"]})
    out, stats = apply_gated_overwrites(_canonical(), approved, reparse=False)
    assert stats["unmatched_samples"] == 1
    assert out.loc[out["sample_accession"] == "s3", "country"].tolist() == ["USA"]  # untouched


def test_apply_refuses_non_clinical_field() -> None:
    """A never-clinical field is a hard error (second guard beyond upstream never-overwrite)."""
    approved = pd.DataFrame({"sample_accession": ["s1"], "field": ["cf_status"], "applied_value": ["CF"]})
    with pytest.raises(SystemExit):
        apply_gated_overwrites(_canonical(), approved, reparse=False)


def _evo_v2() -> pd.DataFrame:
    """A v2-shaped frame with the evolutionary flag + cohort/quality flags."""
    return pd.DataFrame({
        "sample_accession":        ["e1", "e2", "n1"],
        "evolutionary_lab_sample": ["True", "True", "False"],
        "kpsc_final_list":         ["True", "True", "True"],
        "lra_final_list":          ["True", "False", "True"],
        "is_variant_called":       ["True", "True", "True"],
        "is_complete":             ["True", "False", "True"],
        "is_hybrid":               ["False", "False", "True"],
        "is_reference_genome":     ["False", "False", "True"],
        "is_kpsc":                 ["True", "True", "True"],
    })


def test_delist_dry_run_counts_without_changing() -> None:
    """Dry-run surfaces the pre-counts and mutates nothing (count-first before flipping)."""
    v2 = _evo_v2()
    out, stats = delist_evolutionary(v2, apply=False)
    assert stats["evo_rows"] == 2
    assert stats["quality_flags"]["is_complete"] == 1  # only e1 among evo rows
    assert out.equals(v2)  # unchanged


def test_delist_apply_clamps_cohort_and_quality_but_not_is_kpsc() -> None:
    """--apply forces cohort + quality flags False on evo rows, leaves non-evo rows and is_kpsc alone."""
    out, _ = delist_evolutionary(_evo_v2(), apply=True)
    evo = out["evolutionary_lab_sample"] == "True"
    for col in ("kpsc_final_list", "lra_final_list", "is_variant_called",
                "is_complete", "is_hybrid", "is_reference_genome"):
        assert (out.loc[evo, col] == "False").all(), col
    assert (out.loc[evo, "is_kpsc"] == "True").all()  # taxonomic — untouched
    assert out.loc[out["sample_accession"] == "n1", "kpsc_final_list"].tolist() == ["True"]  # non-evo untouched


def test_delist_reports_absent_v2_only_columns() -> None:
    """Against a v1-like frame the v2-only flags are absent — reported, not an error."""
    v1_like = pd.DataFrame({"sample_accession": ["e1"], "evolutionary_lab_sample": ["True"],
                            "kpsc_final_list": ["True"]})
    _, stats = delist_evolutionary(v1_like, apply=False)
    assert "is_complete" in stats["absent_columns"]
    assert "is_hybrid" in stats["absent_columns"]
