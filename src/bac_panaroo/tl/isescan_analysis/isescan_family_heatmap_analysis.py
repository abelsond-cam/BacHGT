#!/usr/bin/env python3
"""Downstream summaries from ``isescan_family_cluster_counts_per_sample.csv`` (means, SDs, heatmap).

Does not read raw ISEScan CSVs — load the per-sample table produced by
``isescan_family_copy_per_sample.py`` first.

For each cohort (refseq vs short-read builds from ``is_refseq``), computes:
  - Mean and SD (sample SD, ddof=1) of canonical IS-family copy counts across samples
    per top-N clonal groups (by cohort unique-sample count).
  - A ``rare_CGs`` pooled group: samples belonging to the K least-populated clonal groups
    (same cohort, ascending unique-sample counts).

Produces family-level CSVs plus one side-by-side heatmap sharing a colour scale across cohorts.

Cluster-family columns (`cluster_*`) are ignored unless you extend this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import numpy as np
import pandas as pd
import seaborn as sns

from bac_panaroo.tl.define_epidemic_cgs import (
    group_mean_sd_for_columns,
    reorder_cg_rows_by_total_sample_count,
)
from bac_panaroo.tl.isescan_analysis.isescan_constants import CANONICAL_IS_FAMILY_COLUMNS

# Older notebooks imported `parse_bool` from this module — keep re-export.
from bac_panaroo.tl.isescan_analysis.isescan_utils import parse_bool

__all__ = ["parse_bool"]


def _coerce_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(("true", "1", "t", "yes", "y"))


def _shared_vlim(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    stacked = np.concatenate([a.reshape(-1), b.reshape(-1)])
    stacked = stacked[np.isfinite(stacked)]
    if stacked.size == 0:
        return 0.0, 1.0
    return float(np.min(stacked)), float(np.max(stacked))


# Omit from heatmap X-axis only (downstream CSVs still include these if present).
_HEATMAP_EXCLUDE_FAMILIES: frozenset[str] = frozenset({"ISNCY", "raw"})


def plot_side_by_side_heatmap(
    mean_refseq: pd.DataFrame,
    mean_short: pd.DataFrame,
    out_png: Path,
) -> None:
    """Two heatmaps (families on X, groups on Y) with one shared colour scale."""
    out_png.parent.mkdir(parents=True, exist_ok=True)

    cols = [
        c
        for c in mean_refseq.columns
        if c not in _HEATMAP_EXCLUDE_FAMILIES and c in mean_short.columns
    ]
    mean_refseq = mean_refseq.reindex(columns=cols)
    mean_short = mean_short.reindex(columns=cols)

    vmin, vmax = _shared_vlim(mean_refseq.values, mean_short.values)
    if vmin == vmax:
        vmax = vmin + 1e-9

    fig_w = max(15, 0.35 * mean_refseq.shape[1] * 2 + 1.0)
    fig_h = max(7, 0.45 * max(mean_refseq.shape[0], mean_short.shape[0]))
    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.05], wspace=0.28)
    ax_refseq = fig.add_subplot(gs[0, 0])
    ax_short = fig.add_subplot(gs[0, 1])
    cax = fig.add_subplot(gs[0, 2])

    # Seaborn sequential, purple–pink: light (low) → saturated (high); tuned for heatmaps.
    # More vivid but still perceptually uniform: ``cmap="plasma"`` or ``cmap="magma"`` (matplotlib).
    cmap = sns.color_palette("rocket_r", as_cmap=True)
    norm = Normalize(vmin=vmin, vmax=vmax)

    for ax, mat, title in (
        (ax_refseq, mean_refseq, "Complete Genomes"),
        (ax_short, mean_short, "Short Read Genomes"),
    ):
        if mat.empty or mat.shape[1] == 0:
            ax.set_title(title)
            ax.text(0.5, 0.5, "empty matrix", ha="center", va="center", transform=ax.transAxes)
            continue
        sns.heatmap(
            mat.astype(float),
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            ax=ax,
            cbar=False,
            xticklabels=True,
            yticklabels=True,
        )
        ax.set_title(title)
        ax.set_xlabel("IS Family")
        ax.set_ylabel("Clonal Group")

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, cax=cax, label="Mean copy number")

    fig.suptitle("Mean ISE Copies Per Clonal Group", fontsize=14, y=1.02)
    fig.subplots_adjust(top=0.86)
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--per-sample-csv",
        type=Path,
        default=Path(
            "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/isescan_analysis/isescan_family_cluster_counts_per_sample.csv",
        ),
        help="Wide per-sample CSV from ``isescan_family_copy_per_sample.py``",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/isescan_analysis/downstream"),
        help="Directory for CSV summaries + heatmap PNG",
    )
    parser.add_argument("--top-clonal-groups", type=int, default=15)
    parser.add_argument("--rare-cg-n", type=int, default=1000)
    args = parser.parse_args()

    df = pd.read_csv(args.per_sample_csv, low_memory=False)
    if "Sample" not in df.columns or "Clonal group" not in df.columns:
        raise KeyError("Per-sample CSV must contain Sample and Clonal group.")

    fam_cols = [c for c in CANONICAL_IS_FAMILY_COLUMNS if c in df.columns]
    if len(fam_cols) < len(CANONICAL_IS_FAMILY_COLUMNS):
        missing = set(CANONICAL_IS_FAMILY_COLUMNS) - set(fam_cols)
        raise ValueError(f"Per-sample CSV missing canonical family columns: {sorted(missing)}")

    if "is_refseq" not in df.columns:
        raise KeyError("Per-sample CSV must contain is_refseq.")

    df["is_refseq"] = _coerce_bool_series(df["is_refseq"])

    refseq = df[df["is_refseq"]].copy()
    short_read = df[~df["is_refseq"]].copy()

    whole = df.dropna(subset=["Clonal group"]).copy()
    whole["_cg_key"] = whole["Clonal group"].astype(str)
    cg_counts_total = whole.groupby("_cg_key", dropna=False)["Sample"].nunique()

    mean_refseq, sd_refseq = group_mean_sd_for_columns(
        refseq,
        value_cols=fam_cols,
        top_n=args.top_clonal_groups,
        rare_k=args.rare_cg_n,
    )
    mean_sr, sd_sr = group_mean_sd_for_columns(
        short_read,
        value_cols=fam_cols,
        top_n=args.top_clonal_groups,
        rare_k=args.rare_cg_n,
    )

    mean_refseq = reorder_cg_rows_by_total_sample_count(mean_refseq, cg_counts_total)
    sd_refseq = reorder_cg_rows_by_total_sample_count(sd_refseq, cg_counts_total)
    mean_sr = reorder_cg_rows_by_total_sample_count(mean_sr, cg_counts_total)
    sd_sr = reorder_cg_rows_by_total_sample_count(sd_sr, cg_counts_total)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    mean_refseq.to_csv(args.output_dir / "ise_family_mean_refseq.csv")
    sd_refseq.to_csv(args.output_dir / "ise_family_sd_refseq.csv")
    mean_sr.to_csv(args.output_dir / "ise_family_mean_short_read.csv")
    sd_sr.to_csv(args.output_dir / "ise_family_sd_short_read.csv")

    png_out = args.output_dir / "ise_family_refseq_vs_shortread_heatmap.png"
    plot_side_by_side_heatmap(mean_refseq, mean_sr, png_out)

    print(f"Wrote: {args.output_dir / 'ise_family_mean_refseq.csv'}")
    print(f"Wrote: {args.output_dir / 'ise_family_sd_refseq.csv'}")
    print(f"Wrote: {args.output_dir / 'ise_family_mean_short_read.csv'}")
    print(f"Wrote: {args.output_dir / 'ise_family_sd_short_read.csv'}")
    print(f"Wrote: {png_out}")


if __name__ == "__main__":
    main()
