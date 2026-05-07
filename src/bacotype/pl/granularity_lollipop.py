#!/usr/bin/env python3
"""Lollipop/connected-dot plot for granularity level comparisons.

Shows improvement in shared genes at each granularity level (e → d → c → b → a)
per strain on a connected-dot lollipop chart.

Connecting-line color indicates row type:
  gray     — KP epidemic clonal group (kp_epidemic)
  dark blue — KP rare-lineage batch (kp_rare)
  purple   — Non-KP Klebsiella species (kp_species)

Node colors by level (light-to-dark continuum):
  e: gray (global mgh78578 mean)
  d: light yellow-orange (per-run mgh78578)
  c: medium orange (sublineage RefSeq)
  b: dark orange (CG RefSeq)
  a: very dark orange (per-sample RefSeq)

Strain labels are spread vertically to avoid overlap.
Labels and connector lines in light blue indicate CGs where the CG-level
RefSeq gain over sublineage-level exceeds `highlight_cg_gain_genes`
(default 20 genes).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


_LINE_COLORS = {
    "kp_epidemic":    "gray",
    "kp_rare":        "gray",
    "kp_species":     "gray",
    "kp_epidemic_sl": "gray",
}

_DOT_COLORS = {
    "e": "gray",
    "d": "gray",
    "c": "gray",
    "b": "gray",
    "a": "gray",
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


def _plot_gain_histogram(
    df: pd.DataFrame,
    out_dir: str,
    threshold: float,
) -> list[str]:
    """Histogram of gain_c_to_b (absolute shared genes) for epidemic CGs (5-gene bins).

    Bars above `threshold` genes are coloured red. Rare-lineage batches and
    non-KP species are excluded because level_b = level_c by construction
    for those rows (whole-run mode has no per-CG reference).
    """
    gain_col = "gain_c_to_b"

    n_rare = int((df.get("row_type", pd.Series()) == "kp_rare").sum())
    n_species = int((df.get("row_type", pd.Series()) == "kp_species").sum())

    if "row_type" in df.columns:
        epi = df[df["row_type"] == "kp_epidemic"].copy()
    else:
        epi = df.copy()

    vals = epi[gain_col].dropna().values if gain_col in epi.columns else np.array([])
    if len(vals) == 0:
        return []

    max_val = float(vals.max())
    bins = np.arange(0.0, max_val + 6, 5)

    fig, ax = plt.subplots(figsize=(10, 5))
    n_arr, bin_edges, patches = ax.hist(
        vals, bins=bins, color="#9ecae1", edgecolor="white", linewidth=0.5,
    )

    highlight_color = "#66B2FF"  # light blue
    for patch, left in zip(patches, bin_edges[:-1]):
        if left >= threshold - 1e-9:
            patch.set_facecolor(highlight_color)

    ax.axvline(
        threshold, color="black", linestyle="--", linewidth=1.2, alpha=0.8,
        label=f"Threshold: {threshold:.0f} genes",
    )

    # Annotate highlighted CGs by name
    if "strain" in epi.columns and gain_col in epi.columns:
        for _, row in epi[epi[gain_col] > threshold].iterrows():
            gain = float(row[gain_col])
            strain = str(row["strain"])
            bin_idx = int(np.searchsorted(bin_edges, gain, side="right") - 1)
            bin_idx = max(0, min(bin_idx, len(n_arr) - 1))
            bar_h = int(n_arr[bin_idx])
            bin_centre = bin_edges[bin_idx] + 2.5
            ax.annotate(
                strain,
                xy=(bin_centre, bar_h),
                xytext=(bin_centre, bar_h + 0.35),
                ha="center", fontsize=8, color=highlight_color,
                arrowprops=dict(arrowstyle="-", color=highlight_color, lw=0.6),
            )

    ax.set_xlabel(
        "Sublineage RefSeq → CG RefSeq shared-gene gain  (absolute genes)",
        fontsize=11,
    )
    ax.set_ylabel("Number of epidemic CGs", fontsize=11)
    ax.set_title(
        f"Distribution of c→b gain  (KP epidemic CGs, n={len(epi)})\n"
        f"kp_rare (n={n_rare}) and kp_species (n={n_species}) excluded: "
        "level_b = level_c by construction for whole-run rows",
        fontsize=10,
    )
    ax.legend(fontsize=9)
    ax.yaxis.get_major_locator().set_params(integer=True)
    plt.tight_layout()

    png_dir = os.path.join(out_dir, "plots_png")
    pdf_dir = os.path.join(out_dir, "plots_pdf")
    os.makedirs(png_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)
    png = os.path.join(png_dir, "granularity_gain_histogram.png")
    pdf = os.path.join(pdf_dir, "granularity_gain_histogram.pdf")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return [png, pdf]


def plot_granularity_lollipop(
    df: pd.DataFrame | str,
    out_dir: str,
    *,
    top_n: int | None = None,
    sort_by: str = "shared_genes_d",
    highlight_cg_gain_genes: float | None = 20.0,
    filename_stem: str = "granularity_lollipop_sl",
    highlight_color: str | None = None,
    row_type_filter: list[str] | None = None,
    highlight_row_types: list[str] | None = None,
    make_histogram: bool = True,
) -> list[str]:
    """
    Generate lollipop plot of granularity level improvement per strain.

    Output PNGs go to ``<out_dir>/plots_png/`` and PDFs to ``<out_dir>/plots_pdf/``.

    Parameters
    ----------
    df
        DataFrame with granularity data, or path to granularity_table.tsv.
    out_dir
        Parent output directory; ``plots_png/`` and ``plots_pdf/`` subfolders
        are created within it for the figure files. The histogram and log
        (when generated) go to the same subfolders / out_dir respectively.
    top_n
        If set, keep only the top_n strains with highest gain_b_to_a.
    sort_by
        Column to sort strains by (default "shared_genes_d").
    highlight_cg_gain_genes
        If not None, restrict the highlight set to rows with ``gain_c_to_b``
        above this many genes (default 20). Pass None to disable the gain
        criterion (highlight purely by ``highlight_row_types``).
    filename_stem
        Base name for output files without extension.
    highlight_color
        If set, draw highlighted rows in this color and dim the rest.
        If None, all rows render in their base row_type color.
    row_type_filter
        If set, keep only rows whose ``row_type`` value is in this list.
    highlight_row_types
        If set, restrict the highlight set to rows whose ``row_type`` value
        is in this list. Combined (AND) with ``highlight_cg_gain_genes``.
    make_histogram
        If True (default), also write the c→b gain histogram and notes log.

    Returns
    -------
    list of output file paths (lollipop PNG/PDF, optional histogram PNG/PDF, log)
    """
    if isinstance(df, str):
        df = pd.read_csv(df, sep="\t")

    df_full = df  # keep unfiltered reference for the histogram (which always uses kp_epidemic rows)

    if row_type_filter is not None and "row_type" in df.columns:
        df = df[df["row_type"].isin(row_type_filter)].copy()

    # Keep only rows with the four plotted level values (e is intentionally omitted)
    df = df[
        df[["shared_genes_d", "shared_genes_c",
            "shared_genes_b", "shared_genes_a"]]
        .notna()
        .all(axis=1)
    ].copy()

    if df.empty:
        raise ValueError("No complete rows after filtering for d/c/b/a levels")

    if top_n:
        df = df.nlargest(top_n, "gain_b_to_a")

    df = df.sort_values(sort_by)

    in_highlight_mode = highlight_color is not None
    dim_alpha = 0.3
    high_alpha = 0.95
    base_alpha = 0.5

    def _is_highlight_row(row) -> bool:
        if highlight_row_types is not None:
            rt = getattr(row, "row_type", "") or ""
            if rt not in highlight_row_types:
                return False
        if highlight_cg_gain_genes is not None:
            gain = getattr(row, "gain_c_to_b", None)
            if gain is None or pd.isna(gain) or float(gain) <= highlight_cg_gain_genes:
                return False
        return highlight_row_types is not None or highlight_cg_gain_genes is not None

    fig, ax = plt.subplots(figsize=(16, 9))

    for row in df.itertuples():
        levels = ["d", "c", "b", "a"]
        values = [
            row.shared_genes_d,
            row.shared_genes_c, row.shared_genes_b, row.shared_genes_a,
        ]
        fallback = [False, row.fallback_c, row.fallback_b, False]

        row_type = getattr(row, "row_type", "kp_epidemic") or "kp_epidemic"
        is_highlight = _is_highlight_row(row)
        base_color = _LINE_COLORS.get(row_type, "gray")
        if in_highlight_mode and is_highlight:
            line_color, line_alpha = highlight_color, high_alpha
        elif in_highlight_mode:
            line_color, line_alpha = base_color, dim_alpha
        else:
            line_color, line_alpha = base_color, base_alpha

        ax.plot(levels, values, "-", color=line_color, alpha=line_alpha, linewidth=1.5, zorder=1)

        for level, value, is_fallback in zip(levels, values, fallback):
            facecolor = _DOT_COLORS[level] if not is_fallback else "white"
            ax.scatter(
                level, value, s=100, marker="o",
                facecolor=facecolor, edgecolor=_DOT_COLORS[level],
                linewidth=1 if is_fallback else 1.5, zorder=2, alpha=line_alpha,
            )

    # --- Spread strain labels to avoid overlap ---
    ann_fontsize = 5
    _annots: list[tuple[float, str, str, float]] = []  # (y_original, label, color, alpha)
    for row in df.itertuples():
        label = str(getattr(row, "strain", "") or "")
        if not label:
            continue
        is_highlight = _is_highlight_row(row)
        row_type = getattr(row, "row_type", "kp_epidemic") or "kp_epidemic"
        base_color = _LINE_COLORS.get(row_type, "gray")
        if in_highlight_mode and is_highlight:
            label_color, label_alpha = highlight_color, high_alpha
        elif in_highlight_mode:
            label_color, label_alpha = base_color, dim_alpha
        else:
            label_color, label_alpha = base_color, 1.0
        _annots.append((float(row.shared_genes_a), label, label_color, label_alpha))

    if _annots:
        y_orig = [a[0] for a in _annots]
        y_lim = ax.get_ylim()
        y_span = y_lim[1] - y_lim[0]
        fig_h_in = fig.get_size_inches()[1]
        units_per_pt = y_span / (fig_h_in * 72 * 0.82)
        min_gap = ann_fontsize * units_per_pt * 1.4

        y_adj = _spread_labels(y_orig, min_gap)
        for (y_o, lbl, col, alp), y_a in zip(_annots, y_adj):
            if abs(y_a - y_o) > min_gap * 0.15:
                ax.plot([3.05, 3.10], [y_o, y_a], lw=0.4, color=col, alpha=alp * 0.6, zorder=0)
            ax.text(3.12, y_a, lbl, fontsize=ann_fontsize, va="center", color=col, alpha=alp)

    ax.set_ylabel("Shared genes with reference genome", fontsize=11, fontweight="bold")
    ax.set_xticks(range(4))
    ax.set_xticklabels(
        ["d: Ref mgh78578",
         "c: Best RefSeq in SL / Subspecies Batch",
         "b: Best RefSeq in CG",
         "a: Best RefSeq Per-Sample"],
        fontsize=10,
    )
    ax.grid(True, axis="y", alpha=0.3, linestyle="--")

    n_rows = len(df)
    n_epidemic = (df["row_type"] == "kp_epidemic").sum() if "row_type" in df.columns else n_rows
    n_epidemic_sl = (df["row_type"] == "kp_epidemic_sl").sum() if "row_type" in df.columns else 0
    n_rare = (df["row_type"] == "kp_rare").sum() if "row_type" in df.columns else 0
    n_species = (df["row_type"] == "kp_species").sum() if "row_type" in df.columns else 0
    title_parts = [f"{n_rows} strains"]
    if n_epidemic:
        title_parts.append(f"{n_epidemic} KP epidemic CG")
    if n_epidemic_sl:
        title_parts.append(f"{n_epidemic_sl} KP epidemic SL")
    if n_rare:
        title_parts.append(f"{n_rare} rare-lineage")
    if n_species:
        title_parts.append(f"{n_species} non-KP species")
    fig.suptitle(
        f"Shared Genes Using Different Reference Genome Granularity ({', '.join(title_parts)})",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()

    png_dir = os.path.join(out_dir, "plots_png")
    pdf_dir = os.path.join(out_dir, "plots_pdf")
    os.makedirs(png_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    png_path = os.path.join(png_dir, f"{filename_stem}.png")
    pdf_path = os.path.join(pdf_dir, f"{filename_stem}.pdf")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    outputs = [png_path, pdf_path]
    if make_histogram:
        gain_threshold = highlight_cg_gain_genes if highlight_cg_gain_genes is not None else 20.0
        hist_paths = _plot_gain_histogram(df_full, out_dir, gain_threshold)
        log_path = os.path.join(out_dir, "granularity_notes.log")
        _write_gain_log(df_full, log_path, gain_threshold)
        outputs += hist_paths + [log_path]
    return outputs


def _write_gain_log(df: pd.DataFrame, log_path: str, threshold: float) -> None:
    """Write c→b gain statistics to a plain-text log file."""
    abs_col = "gain_c_to_b"
    pct_col = "pct_gain_c_to_b"
    has_abs = abs_col in df.columns
    has_pct = pct_col in df.columns

    lines = [
        "GPA Reference Granularity — CG-level gain highlights",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Threshold: gain_c_to_b > {threshold:.0f} genes",
        f"Total rows: {len(df)}",
        "",
    ]

    if has_abs:
        hi = df[df[abs_col] > threshold].copy()
        lo = df[df[abs_col] <= threshold].copy()

        lines.append(
            f"=== Highlighted CGs: sublineage→CG RefSeq gain > {threshold:.0f} genes "
            f"(n={len(hi)}) ==="
        )
        if hi.empty:
            lines.append("  (none)")
        else:
            col_w = max(len(str(s)) for s in hi.get("strain", hi.index)) + 2
            sl_w = max(len(str(s)) for s in hi.get("Sublineage", hi.index)) + 2
            header = (f"  {'strain':<{col_w}} {'Sublineage':<{sl_w}} {'row_type':<15}"
                      f"  {'gain_c_to_b':>12}  {'pct_gain_c_to_b':>16}")
            lines.append(header)
            lines.append("  " + "-" * (len(header) - 2))
            for _, r in hi.sort_values(abs_col, ascending=False).iterrows():
                pct_str = f"{r[pct_col]:>15.2f}%" if has_pct else "        N/A"
                lines.append(
                    f"  {str(r.get('strain','')):<{col_w}} "
                    f"{str(r.get('Sublineage','')):<{sl_w}} "
                    f"{str(r.get('row_type','')):<15}  "
                    f"{r[abs_col]:>12.1f}  "
                    f"{pct_str}"
                )

        lines += [
            "",
            "=== Summary statistics (c→b gain, absolute genes) ===",
        ]
        if not hi.empty:
            lines.append(
                f"  Highlighted  (n={len(hi):2d}):  "
                f"mean={hi[abs_col].mean():.1f}  "
                f"median={hi[abs_col].median():.1f}  "
                f"range=[{hi[abs_col].min():.1f}, {hi[abs_col].max():.1f}] genes"
            )
        if not lo.empty:
            lines.append(
                f"  Other        (n={len(lo):2d}):  "
                f"mean={lo[abs_col].mean():.1f}  "
                f"median={lo[abs_col].median():.1f}  "
                f"range=[{lo[abs_col].min():.1f}, {lo[abs_col].max():.1f}] genes"
            )
        if "row_type" in df.columns:
            lines.append("")
            lines.append("  Per row_type (all rows):")
            for rt, grp in df.groupby("row_type"):
                v = grp[abs_col].dropna()
                if not v.empty:
                    lines.append(
                        f"    {rt:<20}  n={len(grp):3d}  "
                        f"mean={v.mean():.1f}  "
                        f"median={v.median():.1f} genes"
                    )
    else:
        lines.append("(gain_c_to_b column not found — gain stats unavailable)")

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
    parser.add_argument("--highlight-cg-gain-genes", default="20",
                        help="Threshold for c→b gain to qualify as 'highlighted'; pass 'none' to disable (default 20)")
    parser.add_argument("--filename-stem", default="granularity_lollipop_sl",
                        help="Base name for output files without extension")
    parser.add_argument("--highlight-color", default=None,
                        help="Color for highlighted rows (e.g., '#003d82' for dark blue); None disables highlighting")
    parser.add_argument("--row-type-filter", default=None,
                        help="Comma-separated row_type values to keep (e.g., 'kp_epidemic_sl,kp_rare,kp_species')")
    parser.add_argument("--highlight-row-types", default=None,
                        help="Comma-separated row_type values to highlight (combined with gain threshold)")
    parser.add_argument("--no-histogram", action="store_true",
                        help="Skip the c→b gain histogram and notes log")

    args = parser.parse_args(argv)
    row_type_filter = (
        [s.strip() for s in args.row_type_filter.split(",") if s.strip()]
        if args.row_type_filter else None
    )
    highlight_row_types = (
        [s.strip() for s in args.highlight_row_types.split(",") if s.strip()]
        if args.highlight_row_types else None
    )
    gain_arg = str(args.highlight_cg_gain_genes).strip().lower()
    highlight_cg_gain_genes = None if gain_arg in ("none", "") else float(gain_arg)

    print(f"Loading: {args.input}")
    try:
        output_files = plot_granularity_lollipop(
            args.input, args.out_dir,
            top_n=args.top_n,
            sort_by=args.sort_by,
            highlight_cg_gain_genes=highlight_cg_gain_genes,
            filename_stem=args.filename_stem,
            highlight_color=args.highlight_color,
            row_type_filter=row_type_filter,
            highlight_row_types=highlight_row_types,
            make_histogram=not args.no_histogram,
        )
        print(f"Saved: {output_files}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
