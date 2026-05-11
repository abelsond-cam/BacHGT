"""Scatter: per-CG virulence-BSC penetrance in complete genomes vs short-read MAGs.

Inputs the long-format table produced by
``bacotype.tl.complete_genome_analysis.cg_virulence_penetrance_all`` (one row
per (CG, BSC)). Each point is one (CG, BSC). Color encodes the BSC; per-point
alpha encodes ``n_complete`` -- pale at the inclusion threshold, opaque once
the estimate is reliable (n >= 30). Axes default to symlog so zero-penetrance
points still render while the 0-0.25 region (where most signal lives) gets
the bulk of the canvas.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

__all__ = ["plot_cg_virulence_penetrance"]

# Stable color per BSC so plots are comparable across runs.
BSC_COLORS: dict[str, str] = {
    "Yersiniabactin_bsc": "#1f77b4",
    "Colibactin_bsc": "#ff7f0e",
    "Aerobactin_bsc": "#2ca02c",
    "Salmochelin_bsc": "#d62728",
    "RmpADC_bsc": "#9467bd",
    "rmpA2_bsc": "#8c564b",
}

ALPHA_MIN = 0.2
ALPHA_MAX = 1.0
ALPHA_N_RELIABLE = 30  # n_complete at/above which estimate is treated as reliable -> alpha=1


def _alpha_from_n(n, n_lo: int, n_hi: int = ALPHA_N_RELIABLE) -> np.ndarray:
    """Linear ramp from (n=n_lo, alpha=0.2) to (n=n_hi, alpha=1.0); clipped outside."""
    n_arr = np.asarray(n, dtype=float)
    span = max(n_hi - n_lo, 1)
    frac = (n_arr - n_lo) / span
    return np.clip(ALPHA_MIN + frac * (ALPHA_MAX - ALPHA_MIN), ALPHA_MIN, ALPHA_MAX)


def plot_cg_virulence_penetrance(
    df: pd.DataFrame,
    *,
    save_path: str | Path | None = None,
    min_complete: int = 20,
    log_scale: bool = True,
    linthresh: float = 0.01,
    low_region_cutoff: float = 0.25,
    max_complete_upper_ci: float = 0.01,
    figsize: tuple[float, float] = (8.0, 7.5),
) -> tuple[plt.Figure, plt.Axes]:
    """Scatter of complete-genome vs short-read penetrance, one point per (CG, BSC).

    Parameters
    ----------
    df
        Long-format table with columns ``clonal_group, bsc, n_complete, n_sr,
        complete_penetrance, sr_penetrance`` and (for the CI filter)
        ``complete_ci_high``.
    save_path
        If given, save PNG to this path (parents created as needed).
    min_complete
        Inclusion threshold; also sets the low end of the alpha ramp so points
        at the threshold render pale and reach full opacity at n >= 30.
    log_scale
        If True (default), use ``symlog`` on both axes with ``linthresh`` so the
        zero-penetrance points (very common: most BSCs absent in most CGs) still
        plot at the corner while the low-penetrance region (~0-0.25) is expanded.
    linthresh
        Linear region of the symlog scale around zero. Default 0.01.
    low_region_cutoff
        Penetrance below which a point is considered "in the low region" subject
        to the CI filter. Default 0.25.
    max_complete_upper_ci
        For low-region points, drop those whose Wilson 95% upper CI on
        ``complete_penetrance`` exceeds this value -- they can't be placed
        precisely enough at log scale to interpret. Default 0.01 (= ``linthresh``).
        Set to 1.0 to disable the filter.
    figsize
        Figure size in inches.
    """
    needed = {"clonal_group", "bsc", "n_complete", "n_sr", "complete_penetrance", "sr_penetrance"}
    missing = needed - set(df.columns)
    if missing:
        raise KeyError(f"df missing columns: {sorted(missing)}")

    plot_df = df.dropna(subset=["complete_penetrance", "sr_penetrance"]).copy()
    if "complete_ci_high" in plot_df.columns and max_complete_upper_ci < 1.0:
        n_before = len(plot_df)
        drop_mask = (plot_df["complete_penetrance"] < low_region_cutoff) & (
            plot_df["complete_ci_high"] > max_complete_upper_ci
        )
        n_dropped = int(drop_mask.sum())
        plot_df = plot_df.loc[~drop_mask].copy()
        print(
            f"CI filter: dropped {n_dropped}/{n_before} points "
            f"(complete_penetrance < {low_region_cutoff} AND "
            f"complete_ci_high > {max_complete_upper_ci}); "
            f"kept {len(plot_df)}."
        )
    elif "complete_ci_high" not in plot_df.columns:
        print("CI filter: skipped -- 'complete_ci_high' not in df.")

    n_hi = max(ALPHA_N_RELIABLE, min_complete + 1)

    fig, ax = plt.subplots(figsize=figsize)
    diag = np.linspace(0.0, 1.0, 50)
    ax.plot(diag, diag, linestyle="--", linewidth=1, color="grey", alpha=0.6, zorder=1, label=None)

    for bsc, sub in plot_df.groupby("bsc"):
        color = BSC_COLORS.get(bsc, "black")
        ax.scatter(
            sub["complete_penetrance"].to_numpy(dtype=float),
            sub["sr_penetrance"].to_numpy(dtype=float),
            c=color,
            alpha=_alpha_from_n(sub["n_complete"].to_numpy(), n_lo=min_complete, n_hi=n_hi),
            s=42,
            edgecolors="none",
            zorder=3,
        )

    if log_scale:
        ax.set_xscale("symlog", linthresh=linthresh, linscale=0.5)
        ax.set_yscale("symlog", linthresh=linthresh, linscale=0.5)
        scale_note = f" (symlog, linthresh={linthresh:g})"
        ax.set_xlim(-linthresh / 2, 1.1)
        ax.set_ylim(-linthresh / 2, 1.1)
    else:
        scale_note = ""
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(f"Penetrance in complete genomes{scale_note}  (n_complete >= {min_complete})")
    ax.set_ylabel(f"Penetrance in short-read MAGs{scale_note}")
    n_cgs = plot_df["clonal_group"].nunique()
    ax.set_title(f"Per-CG virulence-BSC penetrance: complete vs short-read  ({n_cgs} CGs)")

    bsc_handles = [
        Line2D([0], [0], marker="o", linestyle="", color=color, markersize=8, label=name.replace("_bsc", ""))
        for name, color in BSC_COLORS.items()
        if name in set(plot_df["bsc"])
    ]
    mid_n = (min_complete + n_hi) // 2 if n_hi > min_complete + 1 else min_complete
    alpha_legend_points = [
        (min_complete, f"n={min_complete}  (threshold)"),
        (mid_n, f"n={mid_n}"),
        (n_hi, f"n>={n_hi}  (reliable)"),
    ]
    seen: set[int] = set()
    alpha_handles = []
    for n, label in alpha_legend_points:
        if n in seen:
            continue
        seen.add(n)
        alpha_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="",
                color="black",
                markersize=8,
                alpha=float(_alpha_from_n(np.array([n]), n_lo=min_complete, n_hi=n_hi)[0]),
                label=label,
            )
        )

    leg_bsc = ax.legend(handles=bsc_handles, title="Virulence BSC", loc="upper left", frameon=True)
    ax.add_artist(leg_bsc)
    ax.legend(handles=alpha_handles, title="n complete genomes", loc="lower right", frameon=True)

    fig.tight_layout()
    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig, ax
