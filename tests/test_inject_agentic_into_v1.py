"""Combine step (i) — the pure helpers that decide blast radius and the evolutionary de-list.

The heavy re-parse (`reparse_filled_rows`) is exercised by the against-v1-mirror run; these tests pin the two
pure decisions that must never drift: which rows count as agent-filled (the re-parse blast radius) and the
evolutionary handling (flag + `kpsc_final_list=False`, SR-only vs LRA-bearing split, `is_kpsc` left alone).
"""
from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.combine.inject_agentic_into_v1 import _filled_mask, handle_evolutionary


def test_filled_mask_unions_the_field_flags_and_tolerates_str_or_bool() -> None:
    """A row is in the re-parse radius iff ANY <field>_agent_filled is true, whether stored bool or str."""
    df = pd.DataFrame({
        "country_agent_filled": [True, False, False, False],
        "host_agent_filled":    ["False", "True", "false", "False"],  # str dtype (post TSV round-trip)
    })
    assert _filled_mask(df).tolist() == [True, True, False, False]


def test_filled_mask_empty_when_no_flags() -> None:
    """No flag columns → nothing to re-parse (all False), never an error."""
    assert _filled_mask(pd.DataFrame({"x": [1, 2]})).tolist() == [False, False]


def test_handle_evolutionary_flags_delists_and_splits_sr_vs_lra() -> None:
    """Evolutionary samples get flagged + kpsc_final_list=False; SR-only vs LRA-bearing split on related_lr."""
    merged = pd.DataFrame({
        "sample_accession":     ["s1", "s2", "s3", "s4"],
        "kpsc_final_list":      ["True", "True", "True", "False"],
        "is_kpsc":              ["True", "True", "True", "True"],
        "related_lr_accession": ["", "GCA_9", "", ""],   # s2 is LRA-bearing
    })
    master = pd.DataFrame({
        "sample_accession":    ["s1", "s2", "s3", "s4"],
        "study_type_excluded": ["True", "True", "False", "False"],  # s1, s2 evolutionary
    })
    out, stats = handle_evolutionary(merged, master)
    assert out["evolutionary_lab_sample"].tolist() == ["True", "True", "False", "False"]
    assert out["kpsc_final_list"].tolist() == ["False", "False", "True", "False"]  # only evo rows flipped
    assert out["is_kpsc"].tolist() == ["True", "True", "True", "True"]  # taxonomic — never touched
    assert stats == {"master_evo_samples": 2, "rows_flagged": 2, "lra_bearing_rows": 1, "sr_only_rows": 1}


def test_handle_evolutionary_lra_split_falls_back_to_sample_prefix_on_v2() -> None:
    """On a v2-shaped table (no related_lr_accession), LRA-bearing = a GCA_/GCF_ `Sample`."""
    merged = pd.DataFrame({
        "sample_accession": ["s1", "s2", "s3"],
        "Sample":           ["GCA_1", "SAMN9", "GCF_2"],  # s1, s3 are LRA rows; s2 is SR-only
        "kpsc_final_list":  ["True", "True", "True"],
    })
    master = pd.DataFrame({"sample_accession": ["s1", "s2", "s3"],
                           "study_type_excluded": ["True", "True", "True"]})
    _, stats = handle_evolutionary(merged, master)
    assert stats == {"master_evo_samples": 3, "rows_flagged": 3, "lra_bearing_rows": 2, "sr_only_rows": 1}


def test_handle_evolutionary_ignores_blank_sample_accessions() -> None:
    """A blank sample_accession in the master evolutionary set must not match blank rows in the table."""
    merged = pd.DataFrame({
        "sample_accession":     ["", "s2"],
        "kpsc_final_list":      ["True", "True"],
        "related_lr_accession": ["", ""],
    })
    master = pd.DataFrame({"sample_accession": ["", "s2"], "study_type_excluded": ["True", "False"]})
    out, stats = handle_evolutionary(merged, master)
    assert out["evolutionary_lab_sample"].tolist() == ["False", "False"]
    assert stats["rows_flagged"] == 0
