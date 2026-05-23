#!/usr/bin/env python3
"""Heatmaps of complete-genome vs short-read enrichment from cg_feature_cohort_analysis counts.

Reads per-CG CSV files from the counts/ subdirectory. Each cell shows complete_vs_sr_ratio
only where ratio > 1 AND p_val_corr < 0.05; all other cells are blank. inf ratios are capped
at 100. Row order is shared across all plots, derived from one hierarchical clustering of the
combined feature matrix.

Produces four PNGs in --output-dir (default: same as --counts-dir):
  is_heatmap.png              IS-family insertion sequence enrichment
  acquired_heatmap.png        Acquired AMR gene enrichment
  virulence_mlst_heatmap.png  Virulence BSCs and chromosomal MLST alleles
  combined_heatmap.png        Three panels side-by-side, independent colour scales per panel
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch
import seaborn as sns

INF_CAP: float = 100.0
DEFAULT_P_THRESHOLD: float = 0.05

MLST_ALLELE_COLS: list[str] = ["gapA", "mdh", "infB", "pgi", "phoE", "rpoB", "tonB"]

CMAP = sns.color_palette("rocket_r", as_cmap=True)

DEFAULT_COUNTS_DIR = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/complete_vs_sr_genomes/counts"
)

GROUP_FILE_STEMS: dict[str, str] = {
    "IS Families": "is_heatmap",
    "Acquired AMR": "acquired_heatmap",
    "Virulence BSCs & MLST": "virulence_mlst_heatmap",
}

# Fixed (vmin, vmax) per group; None means data-driven (vmin=1, vmax=data max).
GROUP_VLIM: dict[str, tuple[float, float] | None] = {
    "IS Families": (0.0, 20.0),
    "Acquired AMR": None,
    "Virulence BSCs & MLST": None,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _parse_ratio(series: pd.Series) -> pd.Series:
    """Parse complete_vs_sr_ratio strings: 'inf' → INF_CAP, empty/other → NaN."""
    return pd.to_numeric(series.replace({"inf": str(INF_CAP), "": np.nan}), errors="coerce").clip(upper=INF_CAP)


def load_ratio_matrix(counts_dir: Path, p_threshold: float = DEFAULT_P_THRESHOLD) -> pd.DataFrame:
    """Return (CG × feature) matrix of filtered ratios.

    Cells where ratio <= 1 or p_val_corr >= p_threshold are NaN (rendered blank).
    all_samples.csv is excluded; Rare_CGs.csv is included.
    """
    csv_files = sorted(f for f in counts_dir.glob("*.csv") if f.stem != "all_samples")
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {counts_dir}")

    rows: dict[str, pd.Series] = {}
    for f in csv_files:
        df = pd.read_csv(f)
        ratios = _parse_ratio(df["complete_vs_sr_ratio"])
        pvals = pd.to_numeric(df["p_val_corr"], errors="coerce")
        keep = (ratios > 1) & (pvals < p_threshold)
        masked = ratios.where(keep, other=np.nan)
        masked.index = df["feature"]
        rows[f.stem] = masked

    return pd.DataFrame(rows).T


# ---------------------------------------------------------------------------
# Column groups and row ordering
# ---------------------------------------------------------------------------


def column_groups(all_cols: list[str]) -> dict[str, list[str]]:
    """Return the three feature column groups in display order."""
    is_cols = [c for c in all_cols if c.startswith("IS")]
    acquired_cols = [c for c in all_cols if c.endswith("_acquired")]
    vir_cols = [c for c in all_cols if c.endswith("_bsc")] + [c for c in MLST_ALLELE_COLS if c in all_cols]
    return {
        "IS Families": is_cols,
        "Acquired AMR": acquired_cols,
        "Virulence BSCs & MLST": vir_cols,
    }


def hierarchical_row_order(matrix: pd.DataFrame) -> list[str]:
    """CG row names ordered by Ward hierarchical clustering on the combined matrix."""
    filled = matrix.fillna(1.0)
    if filled.shape[0] < 2:
        return list(filled.index)
    linkage = sch.linkage(filled.values, method="ward", metric="euclidean")
    dendro = sch.dendrogram(linkage, no_plot=True)
    return [filled.index[i] for i in dendro["leaves"]]


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _vmin_vmax(
    mat: pd.DataFrame,
    override: tuple[float, float] | None = None,
) -> tuple[float, float]:
    if override is not None:
        return override
    finite = mat.values[np.isfinite(mat.values) & ~np.isnan(mat.values)]
    vmin = 1.0
    vmax = float(np.nanmax(finite)) if finite.size > 0 else 2.0
    return vmin, max(vmax, vmin + 1.0)


def plot_single_heatmap(
    matrix: pd.DataFrame,
    row_order: list[str],
    cols: list[str],
    title: str,
    out_path: Path,
    vlim: tuple[float, float] | None = None,
) -> None:
    """Write one heatmap PNG for a single column group."""
    mat = matrix.reindex(index=row_order, columns=cols)
    vmin, vmax = _vmin_vmax(mat, override=vlim)

    fig_w = max(8, 0.45 * len(cols) + 2.5)
    fig_h = max(5, 0.42 * len(row_order) + 1.5)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    sns.heatmap(
        mat.astype(float),
        cmap=CMAP,
        vmin=vmin,
        vmax=vmax,
        ax=ax,
        cbar=True,
        cbar_kws={"label": "complete / SR ratio", "shrink": 0.8},
        xticklabels=True,
        yticklabels=True,
        linewidths=0.3,
        linecolor="lightgrey",
    )
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xlabel("")
    ax.set_ylabel("Clonal Group")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    ax.tick_params(axis="y", labelsize=9)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Wrote: {out_path}")


def plot_combined_heatmap(
    matrix: pd.DataFrame,
    row_order: list[str],
    groups: dict[str, list[str]],
    out_path: Path,
) -> None:
    """Three-panel figure: one panel per column group, independent colour scales, shared row order."""
    active = [(name, cols) for name, cols in groups.items() if cols]
    n = len(active)

    # Layout per group: [data, cbar, spacer] — spacer gives visible gap between panels.
    # Last group has no trailing spacer.
    SPACER = 1.2
    col_widths = []
    for i, (_, cols) in enumerate(active):
        col_widths.extend([max(len(cols) * 0.5, 3.0), 0.4])
        if i < n - 1:
            col_widths.append(SPACER)

    n_gs_cols = len(col_widths)
    fig_w = max(20, sum(col_widths) + 1.0)
    fig_h = max(6, 0.42 * len(row_order) + 2.0)
    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = fig.add_gridspec(1, n_gs_cols, width_ratios=col_widths, wspace=0.04)

    gs_idx = 0
    for i, (name, cols) in enumerate(active):
        ax = fig.add_subplot(gs[0, gs_idx])
        cax = fig.add_subplot(gs[0, gs_idx + 1])
        gs_idx += 3 if i < n - 1 else 2  # skip spacer column between panels

        mat = matrix.reindex(index=row_order, columns=cols)
        vmin, vmax = _vmin_vmax(mat, override=GROUP_VLIM.get(name))

        sns.heatmap(
            mat.astype(float),
            cmap=CMAP,
            vmin=vmin,
            vmax=vmax,
            ax=ax,
            cbar=True,
            cbar_ax=cax,
            cbar_kws={"label": "complete / SR ratio"},
            xticklabels=True,
            yticklabels=(i == 0),
            linewidths=0.3,
            linecolor="lightgrey",
        )
        ax.set_title(name, fontsize=11, pad=6)
        ax.set_xlabel("")
        ax.set_ylabel("Clonal Group" if i == 0 else "")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
        if i == 0:
            ax.tick_params(axis="y", labelsize=9)
        else:
            ax.tick_params(axis="y", left=False, labelleft=False)
        cax.tick_params(labelsize=8)

    fig.suptitle(
        "Complete Genome Enrichment vs Short Read  (ratio > 1, p < 0.05)",
        fontsize=13,
        y=1.01,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Wrote: {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for CG feature enrichment heatmaps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts-dir", type=Path, default=DEFAULT_COUNTS_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write PNGs (default: same as --counts-dir)",
    )
    parser.add_argument(
        "--p-threshold",
        type=float,
        default=DEFAULT_P_THRESHOLD,
        help="P-value cutoff for displaying a cell (default: 0.05)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or args.counts_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading counts from: {args.counts_dir}")
    matrix = load_ratio_matrix(args.counts_dir, p_threshold=args.p_threshold)
    print(f"Matrix: {matrix.shape[0]} CGs × {matrix.shape[1]} features")

    groups = column_groups(list(matrix.columns))
    for name, cols in groups.items():
        n_sig = int(matrix[cols].notna().any(axis=0).sum()) if cols else 0
        print(f"  {name}: {len(cols)} columns, {n_sig} with ≥1 significant cell")

    all_group_cols = [c for cols in groups.values() for c in cols]
    missing = [c for c in all_group_cols if c not in matrix.columns]
    if missing:
        print(f"  WARNING: {len(missing)} expected columns not in matrix: {missing}")

    # Cluster on AMR + Virulence/MLST only — IS families can dominate variance
    # and obscure biologically relevant groupings in the other two feature sets.
    clustering_cols = [c for c in groups["Acquired AMR"] + groups["Virulence BSCs & MLST"] if c in matrix.columns]
    print("Computing hierarchical row order (AMR + Virulence/MLST columns)...")
    row_order = hierarchical_row_order(matrix[clustering_cols])
    print(f"  Order: {row_order}")

    for name, cols in groups.items():
        if not cols:
            print(f"Skipping '{name}': no matching columns found")
            continue
        plot_single_heatmap(
            matrix,
            row_order,
            cols,
            name,
            output_dir / f"{GROUP_FILE_STEMS[name]}.png",
            vlim=GROUP_VLIM.get(name),
        )

    plot_combined_heatmap(matrix, row_order, groups, output_dir / "combined_heatmap.png")

    print(f"\nDone. Output directory: {output_dir}")


if __name__ == "__main__":
    main()
