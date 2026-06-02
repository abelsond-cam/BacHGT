#!/usr/bin/env python3
"""Lollipop/connected-dot plot for granularity level comparisons.

Shows improvement in shared genes at each granularity level
(f → d → c → b → a) per strain on a connected-dot lollipop chart:

  f: per-run mgh78578
  d: best reference in SL (best ref across the whole run)
  c: best reference in CG
  b: best reference in CG / K-locus
  a: best reference per-sample

Level e (best reference in subspecies via the fixed reference bucket) was
removed with the bucket; recoverable from git, to be revisited after
pangenome_merge. All dots and connecting lines are gray. The histograms below
show the per-row gain at each transition (f→d, d→c, c→b, b→a).

Strain labels are spread vertically to avoid overlap.
Labels and connector lines in the highlight colour indicate CGs where the
CG-level RefSeq gain over SL-level exceeds ``highlight_cg_gain_genes``
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
    "f": "gray",
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


_HIST_BAR_COLOR = "#4682B4"  # steel blue

# (gain_col, plot_title, x_label, file_stem) for each granularity transition
_HISTOGRAM_TRANSITIONS: list[tuple[str, str, str, str]] = [
    (
        "gain_f_to_d",
        "Increase in shared genes using best reference at SL vs mgh78578",
        "Shared-gene gain (genes)",
        "granularity_gain_histogram_f_to_d",
    ),
    (
        "gain_d_to_c",
        "Increase in shared genes using best reference at CG level vs SL",
        "Shared-gene gain (genes)",
        "granularity_gain_histogram_d_to_c",
    ),
    (
        "gain_c_to_b",
        "Increase in shared genes using best reference at CG/K-locus level vs CG",
        "Shared-gene gain (genes)",
        "granularity_gain_histogram_c_to_b",
    ),
    (
        "gain_b_to_a",
        "Increase in shared genes using best reference per-sample vs CG/K-locus",
        "Shared-gene gain (genes)",
        "granularity_gain_histogram_b_to_a",
    ),
]


def _plot_one_gain_histogram(
    df: pd.DataFrame,
    out_dir: str,
    gain_col: str,
    title: str,
    x_label: str,
    file_stem: str,
) -> list[str]:
    """Single-color histogram of one gain column over all granularity rows
    (kp_epidemic / kp_epidemic_sl / kp_rare / kp_species), 5-gene bins.

    No per-bar annotation, no threshold colouring — uniform steel-blue bars.
    """
    if gain_col not in df.columns:
        return []
    vals = df[gain_col].dropna().values
    if len(vals) == 0:
        return []

    max_val = float(vals.max())
    min_val = float(vals.min())
    lo = min(0.0, np.floor(min_val / 5) * 5)
    bins = np.arange(lo, max_val + 6, 5)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(vals, bins=bins, color=_HIST_BAR_COLOR, edgecolor="white", linewidth=0.5)

    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel("Number of strains", fontsize=11)
    ax.set_title(title, fontsize=11)
    ax.yaxis.get_major_locator().set_params(integer=True)
    plt.tight_layout()

    png_dir = os.path.join(out_dir, "plots_png")
    pdf_dir = os.path.join(out_dir, "plots_pdf")
    os.makedirs(png_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)
    png = os.path.join(png_dir, f"{file_stem}.png")
    pdf = os.path.join(pdf_dir, f"{file_stem}.pdf")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return [png, pdf]


def _plot_gain_histograms(df: pd.DataFrame, out_dir: str) -> list[str]:
    """Generate one histogram per granularity transition over all rows.

    Includes every row type (kp_epidemic, kp_epidemic_sl, kp_rare, kp_species)
    — now that the SL split makes c→b.i and b.i→b.ii meaningful for the
    summary rows too.
    """
    if df.empty:
        return []

    out: list[str] = []
    for gain_col, title, x_label, file_stem in _HISTOGRAM_TRANSITIONS:
        out += _plot_one_gain_histogram(df, out_dir, gain_col, title, x_label, file_stem)
    return out


def plot_granularity_lollipop(
    df: pd.DataFrame | str,
    out_dir: str,
    *,
    top_n: int | None = None,
    sort_by: str = "shared_genes_f",
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
        Column to sort strains by (default "shared_genes_f").
    highlight_cg_gain_genes
        If not None, restrict the highlight set to rows with ``gain_d_to_c``
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

    # Keep only rows with all five plotted level values present.
    df = df[
        df[["shared_genes_f", "shared_genes_d",
            "shared_genes_c", "shared_genes_b", "shared_genes_a"]]
        .notna()
        .all(axis=1)
    ].copy()

    if df.empty:
        raise ValueError("No complete rows after filtering for f/d/c/b/a levels")

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
            gain = getattr(row, "gain_d_to_c", None)
            if gain is None or pd.isna(gain) or float(gain) <= highlight_cg_gain_genes:
                return False
        return highlight_row_types is not None or highlight_cg_gain_genes is not None

    fig, ax = plt.subplots(figsize=(16, 9))

    for row in df.itertuples():
        levels = ["f", "d", "c", "b", "a"]
        values = [
            row.shared_genes_f,
            row.shared_genes_d,
            row.shared_genes_c,
            row.shared_genes_b,
            row.shared_genes_a,
        ]
        fallback = [
            False,
            False,
            getattr(row, "fallback_c", False),
            getattr(row, "fallback_b", False),
            False,
        ]

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
                ax.plot([4.05, 4.10], [y_o, y_a], lw=0.4, color=col, alpha=alp * 0.6, zorder=0)
            ax.text(4.12, y_a, lbl, fontsize=ann_fontsize, va="center", color=col, alpha=alp)

    ax.set_ylabel("Shared genes with reference genome", fontsize=11, fontweight="bold")
    ax.set_xticks(range(5))
    ax.set_xticklabels(
        ["f: Ref mgh78578",
         "d: Best reference in SL",
         "c: Best reference in CG",
         "b: Best reference in CG / K-locus",
         "a: Best reference Per-Sample"],
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
        hist_paths = _plot_gain_histograms(df_full, out_dir)
        log_path = os.path.join(out_dir, "granularity_notes.log")
        _write_gain_log(df_full, log_path)
        outputs += hist_paths + [log_path]
    return outputs


def _write_gain_log(df: pd.DataFrame, log_path: str) -> None:
    """Write per-CG gains and a summary of mean+range across all transitions.

    Per-CG table is sorted by ``gain_d_to_c`` descending and reports absolute
    gene gains for d→c, c→b, b→a, plus the total d→a gain. The summary block
    reports mean + range across kp_epidemic CGs for each of the four
    consecutive transitions: mgh→SL, SL→CG, CG→CG/KL, CG/KL→per-sample.
    """
    epi = df[df["row_type"] == "kp_epidemic"].copy() if "row_type" in df.columns else df.copy()

    lines = [
        "GPA Reference Granularity — CG-level gains",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Total epidemic CGs: {len(epi)}",
        "",
    ]

    abs_col = "gain_d_to_c"
    if abs_col not in epi.columns or epi.empty:
        lines.append("(gain_d_to_c column not found or no epidemic CGs — log empty)")
        with open(log_path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        return

    # ---- Per-CG table ----
    epi = epi.sort_values(abs_col, ascending=False).reset_index(drop=True)
    # total_gain_d_to_a: sum of d→c, c→b, b→a (not present as a column).
    total = (
        epi.get("gain_d_to_c", 0)
        + epi.get("gain_c_to_b", 0)
        + epi.get("gain_b_to_a", 0)
    )

    col_w = max(len(str(s)) for s in epi["strain"]) + 2 if "strain" in epi.columns else 8
    sl_w = (
        max(len(str(s)) for s in epi["Sublineage"]) + 2 if "Sublineage" in epi.columns else 6
    )
    header = (
        f"  {'strain':<{col_w}} {'Sublineage':<{sl_w}} {'n_samples':>10}"
        f"  {'gain_d_to_c':>13}  {'gain_c_to_b':>11}"
        f"  {'gain_b_to_a':>11}  {'total_gain_d_to_a':>17}"
    )
    lines += [
        "=== Per-CG gains (sorted by gain_d_to_c descending) ===",
        header,
        "  " + "-" * (len(header) - 2),
    ]
    for i, r in epi.iterrows():
        lines.append(
            f"  {str(r.get('strain','')):<{col_w}} "
            f"{str(r.get('Sublineage','')):<{sl_w}} "
            f"{int(r.get('n_samples', 0)):>10d}  "
            f"{r.get('gain_d_to_c', float('nan')):>13.1f}  "
            f"{r.get('gain_c_to_b', float('nan')):>11.1f}  "
            f"{r.get('gain_b_to_a', float('nan')):>11.1f}  "
            f"{float(total.iloc[i]):>17.1f}"
        )

    # ---- Summary of gains across all kp_epidemic CGs ----
    transitions = [
        ("mgh → SL                 (f → d)", "gain_f_to_d"),
        ("SL → CG                  (d → c)", "gain_d_to_c"),
        ("CG → CG/K-locus          (c → b)", "gain_c_to_b"),
        ("CG/K-locus → Per-Sample  (b → a)", "gain_b_to_a"),
    ]
    lines += ["", f"=== Summary of gains across kp_epidemic CGs (n={len(epi)}) ==="]
    for label, col in transitions:
        if col not in epi.columns:
            continue
        v = epi[col].dropna()
        if v.empty:
            continue
        lines.append(
            f"  {label}:  mean={v.mean():>7.1f}  range=[{v.min():>7.1f}, {v.max():>7.1f}]  genes"
        )

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
    parser.add_argument("--sort-by", default="shared_genes_f",
                        help="Column to sort by (default: shared_genes_f)")
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
