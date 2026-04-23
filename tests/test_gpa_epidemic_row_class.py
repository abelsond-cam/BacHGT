"""Tests for structural epidemic row class and stats/plot alignment."""

from __future__ import annotations

import pandas as pd

from bacotype.pl.epidemic_vs_mixed import (
    _rest_sublineage_join_keys,
    _row_sublineage_join_key,
    epidemic_vs_mixed_strain_stats,
)
from bacotype.tl.gpa_epidemic_row_class import (
    EPIDEMIC_ROW_CLASS_COL,
    IS_EPIDEMIC_GPA_CLONAL_TARGET_COL,
    EpidemicRowClass,
    add_epidemic_row_class_column,
    get_epidemic_row_class_series,
    structural_epidemic_row_class,
)


def test_sublineage_join_key_uses_strain_for_empty_sublineage_on_rest() -> None:
    """Pooled 'other' rows can have empty Sublineage but strain=SL14 (see detail TSV)."""
    rest = pd.DataFrame(
        {
            "Sublineage": [""],
            "strain": ["SL14"],
        }
    )
    assert _rest_sublineage_join_keys(rest).iloc[0] == "SL14"
    target = pd.Series({"Sublineage": "SL14", "strain": "CG14"})
    assert _row_sublineage_join_key(target) == "SL14"


def test_structural_epidemic_row_class_labels() -> None:
    df = pd.DataFrame(
        {
            "strain": ["A", "B", "C", "D"],
            "species": ["Klebsiella pneumoniae"] * 3 + ["Escherichia coli"],
            "group_level": ["clonal_group"] * 4,
            "group_label": ["CG1", "other", "CG2", "CG3"],
            "n_unique_clonal_groups": [1, 16, 2, 1],
            "n_samples": [300, 300, 300, 300],
        }
    )
    s = structural_epidemic_row_class(df)
    assert s.iloc[0] == EpidemicRowClass.epidemic_group
    assert s.iloc[1] == EpidemicRowClass.non_epidemic_comparator
    assert s.iloc[2] == EpidemicRowClass.na
    assert s.iloc[3] == EpidemicRowClass.na


def test_add_epidemic_row_class_column() -> None:
    df = pd.DataFrame(
        {
            "species": ["Klebsiella pneumoniae"],
            "group_level": ["clonal_group"],
            "group_label": ["other"],
            "n_unique_clonal_groups": [2],
            "n_samples": [300],
        }
    )
    out = add_epidemic_row_class_column(df)
    assert EPIDEMIC_ROW_CLASS_COL in out.columns
    assert IS_EPIDEMIC_GPA_CLONAL_TARGET_COL in out.columns
    assert out[EPIDEMIC_ROW_CLASS_COL].iloc[0] == str(
        EpidemicRowClass.non_epidemic_comparator
    )
    assert out[IS_EPIDEMIC_GPA_CLONAL_TARGET_COL].iloc[0] is False


def test_get_epidemic_row_class_series_prefers_column() -> None:
    df = pd.DataFrame(
        {
            "species": ["Klebsiella pneumoniae"],
            "group_level": ["clonal_group"],
            "group_label": ["CG1"],
            "n_unique_clonal_groups": [1],
            "n_samples": [300],
            EPIDEMIC_ROW_CLASS_COL: ["na"],
        }
    )
    s = get_epidemic_row_class_series(df, prefer_column=True)
    assert s.iloc[0] == "na"


def _stats_ready_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strain": ["t1", "rest1", "mix1"],
            "Sublineage": ["SLX", "SLX", "SLY"],
            "species": ["Klebsiella pneumoniae"] * 3,
            "group_level": ["clonal_group"] * 3,
            "group_label": ["CG_T1", "other", "CG_M"],
            "n_unique_clonal_groups": [1, 12, 3],
            "n_samples": [300, 300, 300],
            "mean_genome_size": [100.0, 50.0, 70.0],
            "sd_genome_size": [2.0, 2.0, 2.0],
            "source_tsv": ["/a/x.tsv", "/a/x.tsv", "/a/x.tsv"],
        }
    )


def test_stats_uses_structural_then_metric() -> None:
    df = _stats_ready_df()
    out_df, rest_mean, _ = epidemic_vs_mixed_strain_stats(
        df,
        metric="genome_size",
        show_table=False,
    )
    assert out_df is not None
    assert rest_mean is not None
    assert len(out_df) == 1
    assert out_df["strain"].iloc[0] == "t1"


def test_epidemic_structural_dropped_when_sd_zero_for_metric() -> None:
    df = _stats_ready_df()
    df2 = df.copy()
    df2.loc[df2["strain"] == "t1", "sd_genome_size"] = 0.0
    out_df, _, _ = epidemic_vs_mixed_strain_stats(
        df2,
        metric="genome_size",
        show_table=False,
    )
    assert out_df is None

