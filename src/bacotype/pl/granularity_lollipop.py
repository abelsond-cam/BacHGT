#!/usr/bin/env python3
"""Lollipop/connected-dot plot for granularity level comparisons.

Shows improvement in shared genes at each granularity level (d → c → b → a)
per strain on a connected-dot lollipop chart.
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd


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
    # Load if path
    if isinstance(df, str):
        df = pd.read_csv(df, sep="\t")

    # Filter to rows with all four level values
    df = df[
        df[["shared_genes_d", "shared_genes_c", "shared_genes_b", "shared_genes_a"]]
        .notna()
        .all(axis=1)
    ].copy()

    if df.empty:
        raise ValueError("No complete rows after filtering for all four levels")

    # Optional: keep top_n by gain_b_to_a
    if top_n:
        df = df.nlargest(top_n, "gain_b_to_a")

    # Sort by specified column
    df = df.sort_values(sort_by)

    # Plot setup
    fig, ax = plt.subplots(figsize=(14, 8))

    strains = df["strain"].values
    x_pos = range(len(strains))

    # Colors per level
    colors = {
        "d": "#d62728",  # red
        "c": "#ff7f0e",  # orange
        "b": "#1f77b4",  # steelblue
        "a": "#2ca02c",  # green
    }

    # For each strain: draw connecting line and dots
    for i, (strain, row) in enumerate(zip(strains, df.itertuples())):
        levels = ["d", "c", "b", "a"]
        values = [
            row.shared_genes_d,
            row.shared_genes_c,
            row.shared_genes_b,
            row.shared_genes_a,
        ]
        fallback = [False, row.fallback_c, row.fallback_b, False]

        # Draw connecting line
        ax.plot(
            levels,
            values,
            "-",
            color="gray",
            alpha=0.4,
            linewidth=1.5,
            zorder=1,
            marker="o",
            markersize=8,
        )

        # Draw dots with colors
        for level, value, is_fallback in zip(levels, values, fallback):
            marker = "o" if not is_fallback else "o"
            facecolor = colors[level] if not is_fallback else "white"
            edgecolor = colors[level]
            linewidth = 1 if is_fallback else 1.5

            ax.scatter(
                level,
                value,
                s=100,
                marker=marker,
                facecolor=facecolor,
                edgecolor=edgecolor,
                linewidth=linewidth,
                zorder=2,
            )

        # Annotate n_samples above level-a dot
        if row.n_samples:
            ax.text(
                3.05,
                row.shared_genes_a,
                f"n={int(row.n_samples)}",
                fontsize=7,
                va="center",
                alpha=0.7,
            )

    # Axes labels and formatting
    ax.set_ylabel("Shared genes with reference genome", fontsize=11, fontweight="bold")
    ax.set_xticks(range(4))
    ax.set_xticklabels(
        [
            "d: mgh78578",
            "c: Sublineage RefSeq",
            "b: CG RefSeq",
            "a: Per-sample RefSeq",
        ],
        fontsize=10,
    )
    ax.grid(True, axis="y", alpha=0.3, linestyle="--")

    # Legend
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="d: mgh78578",
            markerfacecolor=colors["d"],
            markeredgecolor=colors["d"],
            markersize=8,
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="c: Sublineage RefSeq",
            markerfacecolor=colors["c"],
            markeredgecolor=colors["c"],
            markersize=8,
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="b: CG RefSeq",
            markerfacecolor=colors["b"],
            markeredgecolor=colors["b"],
            markersize=8,
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="a: Per-sample RefSeq",
            markerfacecolor=colors["a"],
            markeredgecolor=colors["a"],
            markersize=8,
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="○ = fallback",
            markerfacecolor="white",
            markeredgecolor="black",
            markersize=8,
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    fig.suptitle(
        f"GPA Reference Granularity Analysis ({len(df)} strains)",
        fontsize=12,
        fontweight="bold",
    )
    plt.tight_layout()

    # Save outputs
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
    parser.add_argument(
        "--input",
        required=True,
        help="Path to granularity_table.tsv",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for PNG and PDF",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Keep only top_n strains by gain_b_to_a",
    )
    parser.add_argument(
        "--sort-by",
        default="shared_genes_d",
        help="Column to sort by (default: shared_genes_d)",
    )

    args = parser.parse_args(argv)

    print(f"Loading: {args.input}")
    try:
        output_files = plot_granularity_lollipop(
            args.input,
            args.out_dir,
            top_n=args.top_n,
            sort_by=args.sort_by,
        )
        print(f"✓ Saved: {output_files}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
