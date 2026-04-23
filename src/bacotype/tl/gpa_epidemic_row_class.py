"""Structural row labels for epidemic vs mixed (GPA distances detail tables).

The column ``epidemic_vs_mixed_row_class`` is metric-agnostic: species,
``group_level``, group labels, counts, and sample thresholds only.
``is_epidemic_gpa_clonal_target`` is a convenience boolean (true when the
class is ``epidemic_group``). Per-metric mean/sd checks live in
:mod:`bacotype.pl.epidemic_vs_mixed`.
"""

from __future__ import annotations

from enum import StrEnum

import pandas as pd

__all__ = [
    "EPIDEMIC_ROW_CLASS_COL",
    "IS_EPIDEMIC_GPA_CLONAL_TARGET_COL",
    "EpidemicRowClass",
    "DEFAULT_SPECIES_FILTER",
    "DEFAULT_TARGET_GROUP_LEVEL",
    "DEFAULT_TARGET_MIN_SAMPLES",
    "DEFAULT_OTHER_LABEL",
    "structural_epidemic_row_class",
    "add_epidemic_row_class_column",
    "get_epidemic_row_class_series",
]

EPIDEMIC_ROW_CLASS_COL = "epidemic_vs_mixed_row_class"
# True iff ``epidemic_vs_mixed_row_class == epidemic_group`` (same structural rules).
IS_EPIDEMIC_GPA_CLONAL_TARGET_COL = "is_epidemic_gpa_clonal_target"

DEFAULT_SPECIES_FILTER = "Klebsiella pneumoniae"
DEFAULT_TARGET_GROUP_LEVEL = "clonal_group"
DEFAULT_TARGET_MIN_SAMPLES = 250
DEFAULT_OTHER_LABEL = "other"


class EpidemicRowClass(StrEnum):
    """Structural classification for epidemic vs mixed analysis."""

    epidemic_group = "epidemic_group"
    non_epidemic_comparator = "non_epidemic_comparator"
    na = "na"


def structural_epidemic_row_class(
    df: pd.DataFrame,
    *,
    species_col: str = "species",
    group_level_col: str = "group_level",
    group_label_col: str = "group_label",
    group_count_col: str = "n_unique_clonal_groups",
    weight_col: str = "n_samples",
    species_filter: str = DEFAULT_SPECIES_FILTER,
    target_group_level: str = DEFAULT_TARGET_GROUP_LEVEL,
    target_min_samples: int = DEFAULT_TARGET_MIN_SAMPLES,
    other_label: str = DEFAULT_OTHER_LABEL,
) -> pd.Series:
    """Return per-row structural class (same length and index as ``df``)."""
    required = [
        species_col,
        group_level_col,
        group_label_col,
        group_count_col,
        weight_col,
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"structural_epidemic_row_class: df missing columns: {missing}"
        )

    sp = df[species_col].astype(str) == str(species_filter)
    level = df[group_level_col].astype(str) == str(target_group_level)
    gl = df[group_label_col].astype(str)
    not_other = gl != str(other_label)
    is_other = gl == str(other_label)
    w = df[weight_col]
    gc = df[group_count_col]
    w_ok = w >= int(target_min_samples)
    one_group = gc == 1

    is_epidemic = sp & level & not_other & one_group & w_ok
    is_comparator = sp & level & is_other

    out = pd.Series(EpidemicRowClass.na, index=df.index, dtype=object)
    out.loc[is_comparator] = EpidemicRowClass.non_epidemic_comparator
    out.loc[is_epidemic] = EpidemicRowClass.epidemic_group
    return out


def get_epidemic_row_class_series(
    df: pd.DataFrame,
    *,
    prefer_column: bool = True,
    species_col: str = "species",
    group_level_col: str = "group_level",
    group_label_col: str = "group_label",
    group_count_col: str = "n_unique_clonal_groups",
    weight_col: str = "n_samples",
    species_filter: str = DEFAULT_SPECIES_FILTER,
    target_group_level: str = DEFAULT_TARGET_GROUP_LEVEL,
    target_min_samples: int = DEFAULT_TARGET_MIN_SAMPLES,
    other_label: str = DEFAULT_OTHER_LABEL,
) -> pd.Series:
    """Read ``EPIDEMIC_ROW_CLASS_COL`` from ``df`` if present, else compute."""
    if prefer_column and EPIDEMIC_ROW_CLASS_COL in df.columns:
        return df[EPIDEMIC_ROW_CLASS_COL].astype(str)
    return structural_epidemic_row_class(
        df,
        species_col=species_col,
        group_level_col=group_level_col,
        group_label_col=group_label_col,
        group_count_col=group_count_col,
        weight_col=weight_col,
        species_filter=species_filter,
        target_group_level=target_group_level,
        target_min_samples=target_min_samples,
        other_label=other_label,
    )


def add_epidemic_row_class_column(
    df: pd.DataFrame,
    *,
    overwrite: bool = True,
    species_col: str = "species",
    group_level_col: str = "group_level",
    group_label_col: str = "group_label",
    group_count_col: str = "n_unique_clonal_groups",
    weight_col: str = "n_samples",
    species_filter: str = DEFAULT_SPECIES_FILTER,
    target_group_level: str = DEFAULT_TARGET_GROUP_LEVEL,
    target_min_samples: int = DEFAULT_TARGET_MIN_SAMPLES,
    other_label: str = DEFAULT_OTHER_LABEL,
) -> pd.DataFrame:
    """Add or replace structural class and boolean target columns (copy of ``df``)."""
    if not overwrite:
        out = df.copy()
        has_cls = EPIDEMIC_ROW_CLASS_COL in out.columns
        has_bool = IS_EPIDEMIC_GPA_CLONAL_TARGET_COL in out.columns
        if has_cls and has_bool:
            return out
        if has_cls and not has_bool:
            c = out[EPIDEMIC_ROW_CLASS_COL].astype(str)
            out[IS_EPIDEMIC_GPA_CLONAL_TARGET_COL] = c == str(
                EpidemicRowClass.epidemic_group
            )
            return out
    s = structural_epidemic_row_class(
        df,
        species_col=species_col,
        group_level_col=group_level_col,
        group_label_col=group_label_col,
        group_count_col=group_count_col,
        weight_col=weight_col,
        species_filter=species_filter,
        target_group_level=target_group_level,
        target_min_samples=target_min_samples,
        other_label=other_label,
    )
    out = df.copy()
    cls_str = s.astype(str)
    out[EPIDEMIC_ROW_CLASS_COL] = cls_str
    out[IS_EPIDEMIC_GPA_CLONAL_TARGET_COL] = (
        cls_str == str(EpidemicRowClass.epidemic_group)
    )
    return out
