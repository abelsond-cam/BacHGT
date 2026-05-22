"""Epidemic-vs-mixed-strain comparison plots and stats.

Generalised port of the ``sublineage_vs_rare_lineage_*`` functions from
``docs/notebooks/pangenome/intra_genome_clonalgroup.ipynb`` (and the matching
sublineage notebook). The statistical logic is identical; the two
notebook-specific assumptions (``n_unique_sublineages`` as the group-count
column and ``samples_in_strain`` as the per-row weight) are parameterised so
the same functions can be used for clonal-group-level, sublineage-level, or
arbitrary other partitions.

Input is a per-strain/per-group summary table (one row per ``strain``). For
each row we expect a mean and SD of the chosen metric plus a per-row sample
count used both for the variance-of-the-mean and the comparator weighting.

Two naming conventions for the ``(mean, sd)`` columns are recognised, so the
same caller can target either metadata numerics (``<metric>_mean`` /
``<metric>_sd`` -- e.g. ``total_size_mean``) or genome-composition metrics
(``mean_<metric>`` / ``sd_<metric>`` -- e.g. ``mean_genome_size``).
"""

from __future__ import annotations

import os
import time
from math import erfc, sqrt

print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: epidemic_vs_mixed stdlib loaded",
    flush=True,
)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: epidemic_vs_mixed matplotlib loaded",
    flush=True,
)
print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: epidemic_vs_mixed numpy loaded",
    flush=True,
)
print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: epidemic_vs_mixed pandas loaded",
    flush=True,
)

from bac_panaroo.tl.gpa_epidemic_row_class import (
    EpidemicRowClass,
    get_epidemic_row_class_series,
)

__all__ = [
    "resolve_mean_sd_columns",
    "epidemic_vs_mixed_strain_stats",
    "epidemic_vs_mixed_strain_plot",
    "epidemic_vs_mixed_strain_comparison",
]


def resolve_mean_sd_columns(df: pd.DataFrame, metric: str) -> tuple[str, str]:
    """Resolve the (mean, sd) column names for ``metric`` in ``df``.

    Tries ``mean_<metric>`` / ``sd_<metric>`` first (genome-composition
    convention), then ``<metric>_mean`` / ``<metric>_sd`` (metadata-numeric
    convention). Raises ``KeyError`` if neither pair is present.
    """
    candidates = (
        (f"mean_{metric}", f"sd_{metric}"),
        (f"{metric}_mean", f"{metric}_sd"),
    )
    for mean_col, sd_col in candidates:
        if mean_col in df.columns and sd_col in df.columns:
            return mean_col, sd_col
    cols_list = ", ".join(f"({m!r}, {s!r})" for m, s in candidates)
    raise KeyError(f"Could not resolve mean/sd columns for metric={metric!r}. Tried: {cols_list}.")


_mean_sd_columns = resolve_mean_sd_columns  # backward-compatible alias


def epidemic_vs_mixed_strain_stats(
    df: pd.DataFrame,
    *,
    metric: str = "genome_size",
    group_count_col: str = "n_unique_clonal_groups",
    weight_col: str = "n_samples",
    show_table: bool = True,
    species_filter: str = "Klebsiella pneumoniae",
    target_group_level: str = "clonal_group",
    target_min_samples: int = 250,
    other_label: str = "other",
) -> tuple[pd.DataFrame | None, float | None, float | None]:
    """Epidemic-clonal-group test vs pooled per-run ``other`` comparator.

    Structural class (species, group level, labels, counts) comes from
    :mod:`bac_panaroo.tl.gpa_epidemic_row_class` (column
    ``epidemic_vs_mixed_row_class`` or recomputed from ``species_filter`` and
    related args). This function does not apply a separate species filter:
    it keeps rows labelled ``epidemic_group`` or ``non_epidemic_comparator``,
    then drops rows with invalid metric inputs (``weight_col <= 1``,
    ``sd_col <= 0``, missing mean/sd, etc.).

    Targets are metric-eligible rows whose structural class is
    ``epidemic_group``.

    The global ``rest`` comparator is the pooled set of rows with
    ``group_label == other_label``; one such row per input sub-table is
    expected (validated via ``source_tsv`` when available). For each
    target a within-sublineage comparator is additionally computed from
    the subset of ``other`` rows sharing the target's ``Sublineage``
    value.

    Returns
    -------
    out_df
        DataFrame with one row per target containing both the global-rest
        and within-sublineage statistics. ``None`` if no targets or no
        global-rest rows remain after filtering.
    rest_mean
        Weighted global comparator mean.
    rest_var
        Variance of the weighted global comparator mean.

    Notes
    -----
    Rows with ``weight_col <= 1`` or ``sd_col <= 0`` are dropped before the
    test (variance of the mean is undefined / zero).
    """
    mean_col, sd_col = resolve_mean_sd_columns(df, metric)

    required_cols = [
        "strain",
        "Sublineage",
        "species",
        "group_level",
        "group_label",
        group_count_col,
        mean_col,
        sd_col,
        weight_col,
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"df missing columns: {missing}")

    n_in = len(df)
    structural = get_epidemic_row_class_series(
        df,
        prefer_column=True,
        species_filter=species_filter,
        target_group_level=target_group_level,
        target_min_samples=target_min_samples,
        other_label=other_label,
        group_count_col=group_count_col,
        weight_col=weight_col,
    )
    c_ep = EpidemicRowClass.epidemic_group
    c_comp = EpidemicRowClass.non_epidemic_comparator
    cand_mask = structural.astype(str).isin((str(c_ep), str(c_comp)))
    n_cand = int(cand_mask.sum())
    print(f"Structural rows ({c_ep!r} + {c_comp!r}): {n_cand} (from {n_in}).")

    cand_df = df[cand_mask].copy()
    work_df = cand_df.dropna(subset=[mean_col, sd_col, weight_col, group_count_col]).copy()
    work_df = work_df[(work_df[weight_col] > 1) & (work_df[sd_col] > 0)].copy()
    work_df["var_mean"] = (work_df[sd_col] ** 2) / work_df[weight_col]

    struct_on_work = structural.reindex(work_df.index).astype(str)
    rest = work_df[struct_on_work == str(c_comp)].copy()
    if "source_tsv" in rest.columns:
        counts = rest["source_tsv"].value_counts()
        bad = counts[counts != 1]
        if not bad.empty:
            bad_preview = ", ".join(f"{src!r}:n={int(n)}" for src, n in bad.head(5).items())
            raise ValueError(
                f"Expected exactly one {other_label!r} row per sub-table; "
                f"found {len(bad)} source_tsv(s) violating this. "
                f"First offenders: {bad_preview}"
            )

    targets = work_df[struct_on_work == str(c_ep)].copy()

    print(f"Metric-eligible targets (structural {c_ep!r} after weight/sd checks): {len(targets)} rows.")
    print(f"Global comparator {other_label!r} rows: {len(rest)}.")

    if targets.empty:
        print("No target rows after epidemic filters.")
        return None, None, None
    if rest.empty:
        print(f"No global comparator rows (group_label == {other_label!r}).")
        return None, None, None

    rest_weights = rest[weight_col].to_numpy(dtype=float)
    rest_alpha = rest_weights / rest_weights.sum()
    rest_mean = float(np.sum(rest_alpha * rest[mean_col].to_numpy(dtype=float)))
    rest_var = float(np.sum((rest_alpha**2) * rest["var_mean"].to_numpy(dtype=float)))

    target_mean_key = f"target_mean_{metric}"
    rest_mean_key = f"rest_mean_{metric}"
    rest_sl_mean_key = f"rest_SL_mean_{metric}"

    out = []
    z_crit = 1.96
    for _, row in targets.iterrows():
        target_mean = float(row[mean_col])
        target_var = float(row["var_mean"])
        diff = target_mean - rest_mean
        se_diff = float(np.sqrt(target_var + rest_var))

        if se_diff <= 0 or np.isnan(se_diff):
            z_stat = np.nan
            p_raw = np.nan
            ci_low = np.nan
            ci_high = np.nan
        else:
            z_stat = diff / se_diff
            p_raw = erfc(abs(z_stat) / sqrt(2.0))
            ci_low = diff - z_crit * se_diff
            ci_high = diff + z_crit * se_diff

        target_sl = str(row["Sublineage"])
        sl_rest = rest[rest["Sublineage"].astype(str) == target_sl]
        n_other = int(len(sl_rest))
        sl_w_sum = float(sl_rest[weight_col].to_numpy(dtype=float).sum()) if n_other > 0 else 0.0
        if n_other > 0 and sl_w_sum > 0:
            sl_w = sl_rest[weight_col].to_numpy(dtype=float)
            sl_alpha = sl_w / sl_w.sum()
            rest_sl_mean = float(np.sum(sl_alpha * sl_rest[mean_col].to_numpy(dtype=float)))
            rest_sl_var = float(np.sum((sl_alpha**2) * sl_rest["var_mean"].to_numpy(dtype=float)))
            diff_sl = target_mean - rest_sl_mean
            se_diff_sl = float(np.sqrt(target_var + rest_sl_var))
            if se_diff_sl <= 0 or np.isnan(se_diff_sl):
                z_stat_sl = np.nan
                p_raw_sl = np.nan
                ci_low_sl = np.nan
                ci_high_sl = np.nan
            else:
                z_stat_sl = diff_sl / se_diff_sl
                p_raw_sl = erfc(abs(z_stat_sl) / sqrt(2.0))
                ci_low_sl = diff_sl - z_crit * se_diff_sl
                ci_high_sl = diff_sl + z_crit * se_diff_sl
        else:
            rest_sl_mean = np.nan
            diff_sl = np.nan
            se_diff_sl = np.nan
            z_stat_sl = np.nan
            p_raw_sl = np.nan
            ci_low_sl = np.nan
            ci_high_sl = np.nan

        out.append(
            {
                "strain": row["strain"],
                "Sublineage": target_sl,
                group_count_col: int(row[group_count_col]),
                weight_col: int(row[weight_col]),
                target_mean_key: target_mean,
                rest_mean_key: rest_mean,
                "estimate_target_minus_rest": diff,
                "se_target_mean": float(np.sqrt(target_var)),
                "se_diff": se_diff,
                "z_stat": z_stat,
                "p_raw": p_raw,
                "ci_low": ci_low,
                "ci_high": ci_high,
                rest_sl_mean_key: rest_sl_mean,
                "n_other": n_other,
                "estimate_target_minus_rest_SL": diff_sl,
                "se_diff_SL": se_diff_sl,
                "z_stat_SL": z_stat_sl,
                "p_raw_SL": p_raw_sl,
                "ci_low_SL": ci_low_sl,
                "ci_high_SL": ci_high_sl,
            }
        )

    out_df = pd.DataFrame(out)
    m_tests = len(out_df)
    out_df["p_bonferroni_m"] = np.minimum(out_df["p_raw"] * m_tests, 1.0)
    out_df["p_bonferroni_m_SL"] = np.minimum(out_df["p_raw_SL"] * m_tests, 1.0)

    col_order = [
        "strain",
        "Sublineage",
        group_count_col,
        weight_col,
        target_mean_key,
        rest_mean_key,
        "estimate_target_minus_rest",
        "se_target_mean",
        "se_diff",
        "z_stat",
        "p_raw",
        "p_bonferroni_m",
        "ci_low",
        "ci_high",
        rest_sl_mean_key,
        "n_other",
        "estimate_target_minus_rest_SL",
        "se_diff_SL",
        "z_stat_SL",
        "p_raw_SL",
        "p_bonferroni_m_SL",
        "ci_low_SL",
        "ci_high_SL",
    ]
    out_df = out_df[col_order]
    out_df = out_df.sort_values("estimate_target_minus_rest", ascending=False).reset_index(drop=True)

    print(f"Number of tests (m): {m_tests}")
    print(f"Global comparator weighted mean ({mean_col}): {rest_mean:.2f}")

    if show_table:
        try:
            from IPython.display import display  # type: ignore

            display(out_df)
        except ImportError:
            print(out_df.to_string(index=False))

    return out_df, rest_mean, rest_var


def epidemic_vs_mixed_strain_plot(
    df: pd.DataFrame,
    out_df: pd.DataFrame,
    rest_mean: float,
    *,
    metric: str = "genome_size",
    group_count_col: str = "n_unique_clonal_groups",
    weight_col: str = "n_samples",
    ylabel: str = "Number of genes",
    title: str | None = None,
    ylim: tuple[float, float] | None = None,
    save_path: str | None = None,
    single_label: str = "Epidemic targets (as in stats table)",
    mixed_label: str = "Non-target rows",
    mean_samples_group_label: str = "Clonal group",
    target_group_level: str = "clonal_group",
    other_label: str = "other",
    target_min_samples: int = 250,
    species_filter: str = "Klebsiella pneumoniae",
) -> tuple[plt.Figure, plt.Axes]:
    """Bar chart of ``mean_<metric>`` per row with CI error bars.

    Bar colours use structural class from ``epidemic_vs_mixed_row_class`` (or
    :func:`bac_panaroo.tl.gpa_epidemic_row_class.get_epidemic_row_class_series`):
    light blue = ``epidemic_group``; all other classes are light red. The stats
    table can omit rows that fail per-metric weight/sd checks. If
    ``group_level`` / ``group_label`` are missing, falls back to
    ``group_count_col == 1`` vs ``> 1`` (legacy).

    - CI error bars come from ``out_df`` (absolute scale = ``rest_mean + ci_*``).
    - Twin y-axis scatter of ``weight_col / group_count_col`` (mean samples per
      group; axis label uses ``mean_samples_group_label``).
    - Horizontal dashed lines: mean ``mean_<metric>`` over epidemic target rows
      (blue) and the weighted global ``other`` mean ``rest_mean``.

    Rows are ordered in two blocks: epidemic (blue) then non-epidemic (red),
    each block sorted by decreasing ``weight_col / group_count_col`` (mean
    samples per sub-group). The primary y-axis uses data limits plus 25% of
    the span as padding, unless ``ylim`` is set explicitly.
    """
    mean_col, _ = resolve_mean_sd_columns(df, metric)
    target_mean_col = f"target_mean_{metric}"

    required_df_cols = ["strain", group_count_col, weight_col, mean_col]
    missing_df = [c for c in required_df_cols if c not in df.columns]
    if missing_df:
        raise KeyError(f"df missing columns: {missing_df}")

    required_out = ["strain", target_mean_col, "ci_low", "ci_high"]
    missing_out = [c for c in required_out if c not in out_df.columns]
    if missing_out:
        raise KeyError(f"out_df missing columns: {missing_out}")

    mean_samples_ylabel = f"Mean samples per {mean_samples_group_label}"

    plot_df = df.copy().reset_index(drop=True)

    c_ep = EpidemicRowClass.epidemic_group
    if {
        "species",
        "group_level",
        "group_label",
        group_count_col,
        weight_col,
    }.issubset(plot_df.columns):
        structural = get_epidemic_row_class_series(
            plot_df,
            prefer_column=True,
            species_filter=species_filter,
            target_group_level=target_group_level,
            target_min_samples=target_min_samples,
            other_label=other_label,
            group_count_col=group_count_col,
            weight_col=weight_col,
        )
        is_epidemic = structural.astype(str) == str(c_ep)
    elif "group_level" in plot_df.columns and "group_label" in plot_df.columns:
        is_epidemic = (
            (plot_df["group_level"].astype(str) == target_group_level)
            & (plot_df["group_label"].astype(str) != str(other_label))
            & (plot_df[group_count_col] == 1)
            & (plot_df[weight_col] >= target_min_samples)
        )
    else:
        is_epidemic = plot_df[group_count_col] == 1

    gc = plot_df[group_count_col].to_numpy(dtype=float)
    safe_c = np.where(gc > 0, gc, np.nan)
    w = plot_df[weight_col].to_numpy(dtype=float)
    sort_ratio = w / safe_c
    _sort = pd.Series(sort_ratio, index=plot_df.index)
    plot_work = plot_df.assign(_sort_ratio=_sort)
    epart = plot_work[is_epidemic].sort_values("_sort_ratio", ascending=False, kind="mergesort")
    npart = plot_work[~is_epidemic].sort_values("_sort_ratio", ascending=False, kind="mergesort")
    plot_df = pd.concat([epart, npart], axis=0, ignore_index=True)
    plot_df = plot_df.drop(columns=["_sort_ratio"], errors="ignore")
    n_ep = len(epart)
    n_non = len(npart)
    if n_ep == 0:
        is_epidemic = np.zeros(len(plot_df), dtype=bool)
    elif n_non == 0:
        is_epidemic = np.ones(len(plot_df), dtype=bool)
    else:
        is_epidemic = np.concatenate([np.ones(n_ep, dtype=bool), np.zeros(n_non, dtype=bool)])

    if n_ep:
        epidemic_mean = float(plot_df.iloc[:n_ep][mean_col].mean())
    else:
        epidemic_mean = None

    lower_err = np.full(len(plot_df), np.nan, dtype=float)
    upper_err = np.full(len(plot_df), np.nan, dtype=float)
    ci_lookup = out_df.set_index("strain")[[target_mean_col, "ci_low", "ci_high"]]

    for i in range(len(plot_df)):
        row = plot_df.iloc[i]
        strain = row["strain"]
        yv = float(row[mean_col])
        if strain in ci_lookup.index:
            ci_low_abs = float(rest_mean) + float(ci_lookup.loc[strain, "ci_low"])
            ci_high_abs = float(rest_mean) + float(ci_lookup.loc[strain, "ci_high"])
            lower_err[i] = max(0.0, yv - ci_low_abs)
            upper_err[i] = max(0.0, ci_high_abs - yv)

    fig, ax = plt.subplots(figsize=(12, 6))

    bar_colors = np.where(is_epidemic, "lightblue", "#f4a3a3")
    plot_df.plot(
        kind="bar",
        x="strain",
        y=mean_col,
        legend=False,
        color=bar_colors.tolist(),
        alpha=0.7,
        ax=ax,
    )

    x = np.arange(len(plot_df), dtype=float)
    y = plot_df[mean_col].to_numpy(dtype=float)
    ci_yerr = np.vstack([lower_err, upper_err])
    ax.errorbar(
        x=x,
        y=y,
        yerr=ci_yerr,
        fmt="none",
        ecolor="grey",
        elinewidth=1,
        capsize=2,
        capthick=1,
        zorder=3,
    )

    ax2 = ax.twinx()
    group_counts = plot_df[group_count_col].to_numpy(dtype=float)
    safe_counts = np.where(group_counts > 0, group_counts, np.nan)
    sample_counts = plot_df[weight_col].to_numpy(dtype=float) / safe_counts
    ax2.scatter(
        x,
        sample_counts,
        color="black",
        s=9,
        alpha=0.5,
        label=mean_samples_ylabel,
        zorder=4,
    )
    ax2.set_ylabel(mean_samples_ylabel)

    n_epidemic = int(n_ep)
    if 0 < n_epidemic < len(plot_df):
        ax.axvline(
            x=n_epidemic - 0.5,
            color="darkred",
            linewidth=1,
            alpha=0.2,
            label="Divides epidemic (blue) from other rows (red)",
        )
    if epidemic_mean is not None:
        ax.axhline(
            y=float(epidemic_mean),
            color="darkblue",
            linestyle=":",
            linewidth=2,
            alpha=0.8,
            label=f"Mean {mean_col} across epidemic target rows (blue bars)",
        )
    if rest_mean is not None:
        ax.axhline(
            y=float(rest_mean),
            color="darkred",
            linestyle="--",
            linewidth=2,
            alpha=0.6,
            label=f"Weighted mean {mean_col} across mixed groups",
        )

    ax.set_ylabel(ylabel)
    if title is None:
        title = f"Epidemic vs mixed: {mean_col} (group_count_col={group_count_col})"
    ax.set_title(title)
    if ylim is not None:
        ax.set_ylim(*ylim)
    else:
        y_arr = plot_df[mean_col].to_numpy(dtype=float)
        y_lo = y_arr - np.nan_to_num(lower_err, nan=0.0)
        y_hi = y_arr + np.nan_to_num(upper_err, nan=0.0)
        lo = float(np.nanmin(np.concatenate([y_lo, y_arr])))
        hi = float(np.nanmax(np.concatenate([y_hi, y_arr])))
        if epidemic_mean is not None:
            lo = min(lo, float(epidemic_mean))
            hi = max(hi, float(epidemic_mean))
        if rest_mean is not None:
            lo = min(lo, float(rest_mean))
            hi = max(hi, float(rest_mean))
        span = hi - lo
        if not np.isfinite(span) or span <= 0:
            pad = max(0.01 * (abs(lo) if lo else 1.0), 1.0)
        else:
            pad = 0.25 * span
        ax.set_ylim(lo - pad, hi + pad)

    line_handles, line_labels = ax.get_legend_handles_labels()
    line_handles = [h for h, lbl in zip(line_handles, line_labels) if lbl != mean_col]
    ax2_handles, _ = ax2.get_legend_handles_labels()
    bar_handles = [
        Patch(facecolor="lightblue", alpha=0.7, label=single_label),
        Patch(facecolor="#f4a3a3", alpha=0.7, label=mixed_label),
    ]
    ax.legend(
        handles=bar_handles + line_handles + ax2_handles,
        loc="upper right",
        frameon=True,
    )

    fig.tight_layout()

    if save_path is not None:
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    return fig, ax


def epidemic_vs_mixed_strain_comparison(
    df: pd.DataFrame,
    *,
    metric: str = "genome_size",
    group_count_col: str = "n_unique_clonal_groups",
    weight_col: str = "n_samples",
    show_table: bool = True,
    show_plot: bool = True,
    out_dir: str | None = None,
    ylabel: str = "Number of genes",
    title: str | None = None,
    ylim: tuple[float, float] | None = None,
    mean_samples_group_label: str = "Clonal group",
    species_filter: str = "Klebsiella pneumoniae",
    target_group_level: str = "clonal_group",
    target_min_samples: int = 250,
    other_label: str = "other",
) -> tuple[pd.DataFrame | None, float | None, float | None]:
    """Convenience wrapper: run stats + plot, and optionally write to disk.

    If ``out_dir`` is provided, writes:

    - ``<out_dir>/epidemic_vs_mixed_<metric>_stats.tsv`` (the ``out_df``).
    - ``<out_dir>/epidemic_vs_mixed_<metric>.png`` (the plot).

    The plot includes only rows with ``species == species_filter`` so the
    figure does not show other species; the full ``df`` is still used for
    stats (structural labels already encode species).
    """
    out_df, rest_mean, rest_var = epidemic_vs_mixed_strain_stats(
        df,
        metric=metric,
        group_count_col=group_count_col,
        weight_col=weight_col,
        show_table=show_table,
        species_filter=species_filter,
        target_group_level=target_group_level,
        target_min_samples=target_min_samples,
        other_label=other_label,
    )
    if out_df is None:
        return out_df, rest_mean, rest_var

    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        stats_path = os.path.join(out_dir, f"epidemic_vs_mixed_{metric}_stats.tsv")
        out_df.to_csv(stats_path, sep="\t", index=False)
        print(f"wrote {stats_path}")

    if show_plot:
        save_path = os.path.join(out_dir, f"epidemic_vs_mixed_{metric}.png") if out_dir is not None else None
        plot_df = df[df["species"].astype(str) == str(species_filter)].copy() if "species" in df.columns else df
        fig, _ = epidemic_vs_mixed_strain_plot(
            plot_df,
            out_df,
            rest_mean,
            metric=metric,
            group_count_col=group_count_col,
            weight_col=weight_col,
            ylabel=ylabel,
            title=title,
            ylim=ylim,
            save_path=save_path,
            mean_samples_group_label=mean_samples_group_label,
            target_group_level=target_group_level,
            other_label=other_label,
            target_min_samples=target_min_samples,
            species_filter=species_filter,
        )
        if save_path is not None:
            print(f"wrote {save_path}")
        else:
            # Not saving -> leave figure open for the caller to handle.
            _ = fig

    return out_df, rest_mean, rest_var
