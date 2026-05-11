"""Scatter: per-CG virulence-BSC penetrance in complete genomes vs short-read MAGs.

Inputs the long-format table produced by
``bacotype.tl.complete_genome_analysis.cg_virulence_penetrance_all`` (one row
per (CG, BSC)). Each point is one (CG, BSC). Color encodes the BSC; per-point
alpha encodes ``n_complete`` -- pale at the inclusion threshold (default 10),
opaque once the estimate is reliable (n >= 30).
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
ALPHA_N_LO = 10  # pale at this n_complete
ALPHA_N_HI = 30  # opaque at and above this n_complete


def _alpha_from_n(n) -> np.ndarray:
    """Linear ramp from (n=10, alpha=0.2) to (n=30, alpha=1.0); clipped outside."""
    n_arr = np.asarray(n, dtype=float)
    frac = (n_arr - ALPHA_N_LO) / (ALPHA_N_HI - ALPHA_N_LO)
    return np.clip(ALPHA_MIN + frac * (ALPHA_MAX - ALPHA_MIN), ALPHA_MIN, ALPHA_MAX)


def plot_cg_virulence_penetrance(
    df: pd.DataFrame,
    *,
    save_path: str | Path | None = None,
    min_complete: int = 10,
    figsize: tuple[float, float] = (8.0, 7.5),
) -> tuple[plt.Figure, plt.Axes]:
    """Scatter of complete-genome vs short-read penetrance, one point per (CG, BSC).

    Parameters
    ----------
    df
        Long-format table with columns ``clonal_group, bsc, n_complete, n_sr,
        complete_penetrance, sr_penetrance``.
    save_path
        If given, save PNG to this path (parents created as needed).
    min_complete
        Used only for the x-axis label / title.
    figsize
        Figure size in inches.
    """
    needed = {"clonal_group", "bsc", "n_complete", "n_sr", "complete_penetrance", "sr_penetrance"}
    missing = needed - set(df.columns)
    if missing:
        raise KeyError(f"df missing columns: {sorted(missing)}")

    plot_df = df.dropna(subset=["complete_penetrance", "sr_penetrance"]).copy()

    fig, ax = plt.subplots(figsize=figsize)
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color="grey", alpha=0.6, zorder=1, label=None)

    for bsc, sub in plot_df.groupby("bsc"):
        color = BSC_COLORS.get(bsc, "black")
        ax.scatter(
            sub["complete_penetrance"].to_numpy(dtype=float),
            sub["sr_penetrance"].to_numpy(dtype=float),
            c=color,
            alpha=_alpha_from_n(sub["n_complete"].to_numpy()),
            s=42,
            edgecolors="none",
            zorder=3,
        )

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(f"Penetrance in complete genomes  (n_complete >= {min_complete})")
    ax.set_ylabel("Penetrance in short-read MAGs")
    n_cgs = plot_df["clonal_group"].nunique()
    ax.set_title(f"Per-CG virulence-BSC penetrance: complete vs short-read  ({n_cgs} CGs)")

    bsc_handles = [
        Line2D([0], [0], marker="o", linestyle="", color=color, markersize=8, label=name.replace("_bsc", ""))
        for name, color in BSC_COLORS.items()
        if name in set(plot_df["bsc"])
    ]
    alpha_labels = [
        (ALPHA_N_LO, f"n={ALPHA_N_LO}  (threshold)"),
        (20, "n=20"),
        (ALPHA_N_HI, f"n>={ALPHA_N_HI}  (reliable)"),
    ]
    alpha_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            color="black",
            markersize=8,
            alpha=float(_alpha_from_n(np.array([n]))[0]),
            label=label,
        )
        for n, label in alpha_labels
    ]

    leg_bsc = ax.legend(handles=bsc_handles, title="Virulence BSC", loc="upper left", frameon=True)
    ax.add_artist(leg_bsc)
    ax.legend(handles=alpha_handles, title="n complete genomes", loc="lower right", frameon=True)

    fig.tight_layout()
    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig, ax
