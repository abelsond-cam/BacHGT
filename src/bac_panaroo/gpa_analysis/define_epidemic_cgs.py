"""Reusable clonal-group (CG) selection: epidemic top-N and rare pooled background.

Used by ISEScan downstream summaries and CG cohort metadata comparisons.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

RARE_CGS_ROW = "Rare CGs"

__all__ = [
    "RARE_CGS_ROW",
    "cg_unique_sample_counts",
    "epidemic_labels_from_counts",
    "rare_labels_from_counts",
    "reorder_cg_rows_by_total_sample_count",
    "group_mean_sd_for_columns",
]


def cg_unique_sample_counts(
    df: pd.DataFrame,
    *,
    sample_col: str = "Sample",
    cg_col: str = "Clonal group",
) -> pd.Series:
    """Return unique ``sample_col`` counts per clonal group (string index keys)."""
    sub = df.dropna(subset=[cg_col]).copy()
    if sub.empty:
        return pd.Series(dtype="int64")
    sub["_cg_key"] = sub[cg_col].astype(str)
    return sub.groupby("_cg_key", dropna=False)[sample_col].nunique()


def epidemic_labels_from_counts(cg_counts: pd.Series, top_n: int) -> list[str]:
    """Labels of the ``top_n`` most sample-rich clonal groups."""
    if cg_counts.empty or top_n <= 0:
        return []
    return list(cg_counts.sort_values(ascending=False).head(top_n).index.astype(str))


def rare_labels_from_counts(
    cg_counts: pd.Series,
    exclude_labels: Sequence[str],
    rare_k: int,
) -> list[str]:
    """Labels of the ``rare_k`` least sample-rich groups among those not in ``exclude_labels``."""
    if cg_counts.empty or rare_k <= 0:
        return []
    ex = [str(x) for x in exclude_labels]
    remaining = cg_counts.drop(labels=ex, errors="ignore")
    if remaining.empty:
        return []
    rare_k_eff = min(rare_k, len(remaining))
    return list(remaining.sort_values(ascending=True).head(rare_k_eff).index.astype(str))


def reorder_cg_rows_by_total_sample_count(
    summary: pd.DataFrame,
    cg_total_unique_samples: pd.Series,
    *,
    rare_row_name: str = RARE_CGS_ROW,
) -> pd.DataFrame:
    """Reindex rows: CG labels by descending global unique-sample count; pooled rare row last."""
    if summary.empty:
        return summary
    idx = [str(i) for i in summary.index]
    rare_here = rare_row_name in idx
    cg_labels = [lab for lab in idx if lab != rare_row_name]
    counts = cg_total_unique_samples.reindex(cg_labels).fillna(0).astype(int)
    cg_sorted = sorted(cg_labels, key=lambda lab: (-int(counts.loc[lab]), lab))
    new_order = cg_sorted + ([rare_row_name] if rare_here else [])
    return summary.reindex(new_order)


def group_mean_sd_for_columns(
    df: pd.DataFrame,
    *,
    value_cols: Sequence[str],
    sample_col: str = "Sample",
    cg_col: str = "Clonal group",
    top_n: int,
    rare_k: int,
    cg_counts: pd.Series | None = None,
    rare_row_name: str = RARE_CGS_ROW,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mean and SD (ddof=1) per selected CG rows + pooled rare row.

    Epidemic vs rare membership uses ``cg_counts`` when provided (e.g. cohort-specific
    counts); otherwise counts are computed from ``df`` alone — matching legacy ISEScan
    behaviour where ``df`` is already filtered to refseq or short-read.
    """
    present_cols = [c for c in value_cols if c in df.columns]
    empty = pd.DataFrame(columns=present_cols)
    sub = df.dropna(subset=[cg_col]).copy()
    if sub.empty:
        return empty.copy(), empty.copy()

    counts = cg_counts if cg_counts is not None else cg_unique_sample_counts(sub, sample_col=sample_col, cg_col=cg_col)
    counts.index = counts.index.astype(str)

    top_labels = epidemic_labels_from_counts(counts, top_n)
    rare_lab_list = rare_labels_from_counts(counts, top_labels, rare_k)

    row_names: list[str] = []
    mean_rows: list[pd.Series] = []
    sd_rows: list[pd.Series] = []

    for lab in top_labels:
        part = sub[sub[cg_col].astype(str) == lab]
        row_names.append(str(lab))
        mean_rows.append(part[list(present_cols)].mean())
        sd_rows.append(part[list(present_cols)].std(ddof=1))

    row_names.append(rare_row_name)
    if not rare_lab_list:
        mean_rows.append(pd.Series(np.nan, index=present_cols))
        sd_rows.append(pd.Series(np.nan, index=present_cols))
    else:
        rare_sub = sub[sub[cg_col].astype(str).isin(rare_lab_list)]
        mean_rows.append(rare_sub[list(present_cols)].mean())
        sd_rows.append(rare_sub[list(present_cols)].std(ddof=1))

    mean_df = pd.DataFrame(mean_rows, index=row_names, columns=present_cols)
    sd_df = pd.DataFrame(sd_rows, index=row_names, columns=present_cols)
    return mean_df, sd_df
