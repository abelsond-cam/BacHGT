#!/usr/bin/env python3
"""Lollipop/connected-dot plot for granularity level comparisons.

Shows improvement in shared genes at each granularity level (e → d → c → b → a)
per strain on a connected-dot lollipop chart.

Connecting-line color indicates row type:
  gray    — KP epidemic clonal group (kp_epidemic)
  purple  — KP rare-lineage batch (kp_rare)
  crimson — Non-KP Klebsiella species (kp_species)
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd


_LINE_COLORS = {
    "kp_epidemic": "gray",
    "kp_rare": "#9467bd",    # purple
    "kp_species": "#dc143c",  # crimson
}

_DOT_COLORS = {
    "e": "#7f7f7f",   # gray   — global mgh78578 mean
    "d": "#d62728",   # red    — per-run mgh78578
    "c": "#ff7f0e",   # orange — sublineage RefSeq
    "b": "#1f77b4",   # steelblue — CG RefSeq
    "a": "#2ca02c",   # green  — per-sample RefSeq
}


def plot_granularity_lollipop(
    df: pd.DataFrame | str,
    out_dir: str,
    *,
    top_n: int | None = None,
    sort_by: str = "shared_genes_d",
) -> list[str]:
    """
    Generate lollipop plot of granularity level improvement per strain.

    Parameters
    ----------
    df
        DataFrame with granularity data, or path to granularity_table.tsv.
    out_dir
        Output directory for PNG and PDF.
    top_n
        If set, keep only the top_n strains with highest gain_b_to_a.
    sort_by
        Column to sort strains by (default "shared_genes_d").

    Returns
    -------
    list of output file paths
    """
    if isinstance(df, str):
        df = pd.read_csv(df, sep="\t")

    # Keep only rows with all five level values
    df = df[
        df[["shared_genes_e", "shared_genes_d", "shared_genes_c",
            "shared_genes_b", "shared_genes_a"]]
        .notna()
        .all(axis=1)
    ].copy()

    if df.empty:
        raise ValueError("No complete rows after filtering for all five levels")

    if top_n:
        df = df.nlargest(top_n, "gain_b_to_a")

    df = df.sort_values(sort_by)

    fig, ax = plt.subplots(figsize=(16, 8))

    for row in df.itertuples():
        levels = ["e", "d", "c", "b", "a"]
        values = [
            row.shared_genes_e, row.shared_genes_d,
            row.shared_genes_c, row.shared_genes_b, row.shared_genes_a,
        ]
        fallback = [False, False, row.fallback_c, row.fallback_b, False]

        row_type = getattr(row, "row_type", "kp_epidemic") or "kp_epidemic"
        line_color = _LINE_COLORS.get(row_type, "gray")

        # Connecting line colored by row_type
        ax.plot(levels, values, "-", color=line_color, alpha=0.5, linewidth=1.5, zorder=1)

        # Individual dots colored by level; hollow = fallback
        for level, value, is_fallback in zip(levels, values, fallback):
            facecolor = _DOT_COLORS[level] if not is_fallback else "white"
            ax.scatter(
                level,
                value,
                s=100,
                marker="o",
                facecolor=facecolor,
                edgecolor=_DOT_COLORS[level],
                linewidth=1 if is_fallback else 1.5,
                zorder=2,
            )

        # Right-side annotation: Sublineage label
        label = str(getattr(row, "Sublineage", "") or "")
        if label:
            ax.text(4.05, row.shared_genes_a, label, fontsize=7, va="center", alpha=0.7)

    ax.set_ylabel("Shared genes with reference genome", fontsize=11, fontweight="bold")
    ax.set_xticks(range(5))
    ax.set_xticklabels(
        ["e: Global mgh78578",
         "d: Run mgh78578",
         "c: Sublineage RefSeq",
         "b: CG RefSeq",
         "a: Per-sample RefSeq"],
        fontsize=10,
    )
    ax.grid(True, axis="y", alpha=0.3, linestyle="--")

    # Legend: dot level colors + line row-type colors + fallback symbol
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D([0], [0], marker="o", color="w", label="e: Global mgh78578 mean",
               markerfacecolor=_DOT_COLORS["e"], markeredgecolor=_DOT_COLORS["e"], markersize=8),
        Line2D([0], [0], marker="o", color="w", label="d: Run mgh78578",
               markerfacecolor=_DOT_COLORS["d"], markeredgecolor=_DOT_COLORS["d"], markersize=8),
        Line2D([0], [0], marker="o", color="w", label="c: Sublineage RefSeq",
               markerfacecolor=_DOT_COLORS["c"], markeredgecolor=_DOT_COLORS["c"], markersize=8),
        Line2D([0], [0], marker="o", color="w", label="b: CG RefSeq",
               markerfacecolor=_DOT_COLORS["b"], markeredgecolor=_DOT_COLORS["b"], markersize=8),
        Line2D([0], [0], marker="o", color="w", label="a: Per-sample RefSeq",
               markerfacecolor=_DOT_COLORS["a"], markeredgecolor=_DOT_COLORS["a"], markersize=8),
        Line2D([0], [0], marker="o", color="w", label="○ = fallback level",
               markerfacecolor="white", markeredgecolor="black", markersize=8),
        Line2D([0], [0], color=_LINE_COLORS["kp_epidemic"], alpha=0.7, linewidth=2,
               label="KP epidemic CG"),
        Line2D([0], [0], color=_LINE_COLORS["kp_rare"], alpha=0.7, linewidth=2,
               label="KP rare lineage batch"),
        Line2D([0], [0], color=_LINE_COLORS["kp_species"], alpha=0.7, linewidth=2,
               label="Non-KP species"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    n_rows = len(df)
    n_epidemic = (df.get("row_type", pd.Series()) == "kp_epidemic").sum() if "row_type" in df.columns else n_rows
    n_rare = (df.get("row_type", pd.Series()) == "kp_rare").sum() if "row_type" in df.columns else 0
    n_species = (df.get("row_type", pd.Series()) == "kp_species").sum() if "row_type" in df.columns else 0
    title_parts = [f"{n_rows} strains"]
    if n_epidemic:
        title_parts.append(f"{n_epidemic} KP epidemic")
    if n_rare:
        title_parts.append(f"{n_rare} rare-lineage")
    if n_species:
        title_parts.append(f"{n_species} non-KP species")
    fig.suptitle(
        f"GPA Reference Granularity Analysis ({', '.join(title_parts)})",
        fontsize=12,
        fontweight="bold",
    )
    plt.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, "granularity_lollipop.png")
    pdf_path = os.path.join(out_dir, "granularity_lollipop.pdf")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    return [png_path, pdf_path]


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate lollipop plot from granularity_table.tsv"
    )
    parser.add_argument("--input", required=True, help="Path to granularity_table.tsv")
    parser.add_argument("--out-dir", required=True, help="Output directory for PNG and PDF")
    parser.add_argument("--top-n", type=int, default=None,
                        help="Keep only top_n strains by gain_b_to_a")
    parser.add_argument("--sort-by", default="shared_genes_d",
                        help="Column to sort by (default: shared_genes_d)")

    args = parser.parse_args(argv)

    print(f"Loading: {args.input}")
    try:
        output_files = plot_granularity_lollipop(
            args.input, args.out_dir, top_n=args.top_n, sort_by=args.sort_by
        )
        print(f"Saved: {output_files}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
