#!/usr/bin/env python3
"""Lollipop/connected-dot plot for granularity level comparisons.

Shows improvement in shared genes at each granularity level (e → d → c → b → a)
per strain on a connected-dot lollipop chart.

Connecting-line color indicates row type:
  gray    — KP epidemic clonal group (kp_epidemic)
  purple  — KP rare-lineage batch (kp_rare)
  crimson — Non-KP Klebsiella species (kp_species)

Sublineage labels are spread vertically to avoid overlap.
Labels in red indicate CGs where the CG-level RefSeq gain over sublineage-level
exceeds `highlight_cg_gain_pct` (default 2 %).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import matplotlib.pyplot as plt
import pandas as pd


_LINE_COLORS = {
    "kp_epidemic": "gray",
    "kp_rare": "#9467bd",    # purple
    "kp_species": "#dc143c",  # crimson
}

_DOT_COLORS = {
    "e": "#7f7f7f",   # gray      — global mgh78578 mean
    "d": "#d62728",   # red       — per-run mgh78578
    "c": "#ff7f0e",   # orange    — sublineage RefSeq
    "b": "#1f77b4",   # steelblue — CG RefSeq
    "a": "#2ca02c",   # green     — per-sample RefSeq
}


def _spread_labels(ys: list[float], min_gap: float) -> list[float]:
    """Spread y-positions to avoid overlap while preserving relative order.

    Iteratively pushes adjacent (in sorted order) labels apart by equal
    amounts until no pair is closer than `min_gap`.
    """
    n = len(ys)
    if n <= 1:
        return list(ys)
    order = sorted(range(n), key=lambda i: ys[i])
    result = [ys[i] for i in order]
    for _ in range(500):
        moved = False
        for i in range(n - 1):
            gap = result[i + 1] - result[i]
            if gap < min_gap:
                push = (min_gap - gap) / 2
                result[i] -= push
                result[i + 1] += push
                moved = True
        if not moved:
            break
    final = [0.0] * n
    for rank, orig_idx in enumerate(order):
        final[orig_idx] = result[rank]
    return final


def plot_granularity_lollipop(
    df: pd.DataFrame | str,
    out_dir: str,
    *,
    top_n: int | None = None,
    sort_by: str = "shared_genes_d",
    highlight_cg_gain_pct: float = 2.0,
) -> list[str]:
    """
    Generate lollipop plot of granularity level improvement per strain.

    Parameters
    ----------
    df
        DataFrame with granularity data, or path to granularity_table.tsv.
    out_dir
        Output directory for PNG, PDF, and log.
    top_n
        If set, keep only the top_n strains with highest gain_b_to_a.
    sort_by
        Column to sort strains by (default "shared_genes_d").
    highlight_cg_gain_pct
        Strains with pct_gain_c_to_b above this threshold get red labels
        (default 2.0 %).

    Returns
    -------
    list of output file paths (PNG, PDF, log)
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

    fig, ax = plt.subplots(figsize=(16, 9))

    for row in df.itertuples():
        levels = ["e", "d", "c", "b", "a"]
        values = [
            row.shared_genes_e, row.shared_genes_d,
            row.shared_genes_c, row.shared_genes_b, row.shared_genes_a,
        ]
        fallback = [False, False, row.fallback_c, row.fallback_b, False]

        row_type = getattr(row, "row_type", "kp_epidemic") or "kp_epidemic"
        line_color = _LINE_COLORS.get(row_type, "gray")

        ax.plot(levels, values, "-", color=line_color, alpha=0.5, linewidth=1.5, zorder=1)

        for level, value, is_fallback in zip(levels, values, fallback):
            facecolor = _DOT_COLORS[level] if not is_fallback else "white"
            ax.scatter(
                level, value, s=100, marker="o",
                facecolor=facecolor, edgecolor=_DOT_COLORS[level],
                linewidth=1 if is_fallback else 1.5, zorder=2,
            )

    # --- Spread Sublineage labels to avoid overlap ---
    ann_fontsize = 5
    _annots: list[tuple[float, str, str]] = []  # (y_original, label, color)
    for row in df.itertuples():
        label = str(getattr(row, "Sublineage", "") or "")
        if not label:
            continue
        pct = getattr(row, "pct_gain_c_to_b", None)
        is_highlight = (
            pct is not None
            and not pd.isna(pct)
            and float(pct) > highlight_cg_gain_pct
        )
        _annots.append((float(row.shared_genes_a), label, "red" if is_highlight else "black"))

    if _annots:
        y_orig = [a[0] for a in _annots]
        # Estimate min gap: fontsize in data-coordinate units
        y_lim = ax.get_ylim()
        y_span = y_lim[1] - y_lim[0]
        fig_h_in = fig.get_size_inches()[1]
        units_per_pt = y_span / (fig_h_in * 72 * 0.82)  # 82% of height is axis
        min_gap = ann_fontsize * units_per_pt * 1.4

        y_adj = _spread_labels(y_orig, min_gap)
        for (y_o, lbl, col), y_a in zip(_annots, y_adj):
            if abs(y_a - y_o) > min_gap * 0.15:
                ax.plot([4.05, 4.10], [y_o, y_a], lw=0.4, color="gray", alpha=0.4, zorder=0)
            ax.text(4.12, y_a, lbl, fontsize=ann_fontsize, va="center", color=col)

    ax.set_ylabel("Shared genes with reference genome", fontsize=11, fontweight="bold")
    ax.set_xticks(range(5))
    ax.set_xticklabels(
        ["e: Global mgh78578", "d: Run mgh78578",
         "c: Sublineage RefSeq", "b: CG RefSeq", "a: Per-sample RefSeq"],
        fontsize=10,
    )
    ax.grid(True, axis="y", alpha=0.3, linestyle="--")

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
        Line2D([0], [0], color="w", label=f"Red label: c→b gain > {highlight_cg_gain_pct:.0f}%"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    n_rows = len(df)
    n_epidemic = (df["row_type"] == "kp_epidemic").sum() if "row_type" in df.columns else n_rows
    n_rare = (df["row_type"] == "kp_rare").sum() if "row_type" in df.columns else 0
    n_species = (df["row_type"] == "kp_species").sum() if "row_type" in df.columns else 0
    title_parts = [f"{n_rows} strains"]
    if n_epidemic:
        title_parts.append(f"{n_epidemic} KP epidemic")
    if n_rare:
        title_parts.append(f"{n_rare} rare-lineage")
    if n_species:
        title_parts.append(f"{n_species} non-KP species")
    fig.suptitle(
        f"GPA Reference Granularity Analysis ({', '.join(title_parts)})",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, "granularity_lollipop.png")
    pdf_path = os.path.join(out_dir, "granularity_lollipop.pdf")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    # --- Write gain log ---
    log_path = os.path.join(out_dir, "granularity_notes.log")
    _write_gain_log(df, log_path, highlight_cg_gain_pct)

    return [png_path, pdf_path, log_path]


def _write_gain_log(df: pd.DataFrame, log_path: str, threshold: float) -> None:
    """Write c→b gain statistics to a plain-text log file."""
    gain_col = "pct_gain_c_to_b"
    abs_col = "gain_c_to_b"
    has_gain = gain_col in df.columns and abs_col in df.columns

    lines = [
        "GPA Reference Granularity — CG-level gain highlights",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Threshold: pct_gain_c_to_b > {threshold:.1f}%",
        f"Total rows: {len(df)}",
        "",
    ]

    if has_gain:
        hi = df[df[gain_col] > threshold].copy()
        lo = df[df[gain_col] <= threshold].copy()

        lines.append(
            f"=== Highlighted CGs: sublineage→CG RefSeq gain > {threshold:.1f}% "
            f"(n={len(hi)}) ==="
        )
        if hi.empty:
            lines.append("  (none)")
        else:
            col_w = max(len(str(s)) for s in hi.get("strain", hi.index)) + 2
            sl_w = max(len(str(s)) for s in hi.get("Sublineage", hi.index)) + 2
            header = (f"  {'strain':<{col_w}} {'Sublineage':<{sl_w}} {'row_type':<15}"
                      f"  {'pct_gain_c_to_b':>16}  {'gain_c_to_b':>12}")
            lines.append(header)
            lines.append("  " + "-" * (len(header) - 2))
            for _, r in hi.sort_values(gain_col, ascending=False).iterrows():
                lines.append(
                    f"  {str(r.get('strain','')):<{col_w}} "
                    f"{str(r.get('Sublineage','')):<{sl_w}} "
                    f"{str(r.get('row_type','')):<15}  "
                    f"{r[gain_col]:>15.2f}%  "
                    f"{r[abs_col]:>12.1f}"
                )

        lines += [
            "",
            "=== Summary statistics (c→b gain) ===",
        ]
        if not hi.empty:
            lines.append(
                f"  Highlighted  (n={len(hi):2d}):  "
                f"mean={hi[gain_col].mean():.2f}%  "
                f"median={hi[gain_col].median():.2f}%  "
                f"range=[{hi[gain_col].min():.2f}%, {hi[gain_col].max():.2f}%]"
            )
        if not lo.empty:
            lines.append(
                f"  Other        (n={len(lo):2d}):  "
                f"mean={lo[gain_col].mean():.2f}%  "
                f"median={lo[gain_col].median():.2f}%  "
                f"range=[{lo[gain_col].min():.2f}%, {lo[gain_col].max():.2f}%]"
            )
        # Per row_type breakdown
        if "row_type" in df.columns:
            lines.append("")
            lines.append("  Per row_type (all rows):")
            for rt, grp in df.groupby("row_type"):
                v = grp[gain_col].dropna()
                if not v.empty:
                    lines.append(
                        f"    {rt:<20}  n={len(grp):3d}  "
                        f"mean={v.mean():.2f}%  "
                        f"median={v.median():.2f}%"
                    )
    else:
        lines.append("(pct_gain_c_to_b column not found — gain stats unavailable)")

    with open(log_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate lollipop plot from granularity_table.tsv"
    )
    parser.add_argument("--input", required=True, help="Path to granularity_table.tsv")
    parser.add_argument("--out-dir", required=True, help="Output directory for PNG/PDF/log")
    parser.add_argument("--top-n", type=int, default=None,
                        help="Keep only top_n strains by gain_b_to_a")
    parser.add_argument("--sort-by", default="shared_genes_d",
                        help="Column to sort by (default: shared_genes_d)")
    parser.add_argument("--highlight-cg-gain-pct", type=float, default=2.0,
                        help="Highlight CGs with c→b gain above this %% (default 2.0)")

    args = parser.parse_args(argv)

    print(f"Loading: {args.input}")
    try:
        output_files = plot_granularity_lollipop(
            args.input, args.out_dir,
            top_n=args.top_n,
            sort_by=args.sort_by,
            highlight_cg_gain_pct=args.highlight_cg_gain_pct,
        )
        print(f"Saved: {output_files}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
