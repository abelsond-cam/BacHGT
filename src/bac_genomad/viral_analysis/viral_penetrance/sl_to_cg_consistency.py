#!/usr/bin/env python3
"""Within-Sublineage Clonal-group consistency check for Sgld_v / Wbr_v carriage.

For every epidemic Sublineage (n ≥ ``--min-sl``, default 250) and every
constituent Clonal group with at least ``--min-cg`` (default 50) KpSC
samples, computes the bracket carriage rate with Wilson 95 % CI and
compares it to the parent-SL rate. Pairs nicely with
``viral_penetrance.per_lineage`` whose per-SL summary plot can mask big
intra-SL CG-level variation (e.g. SL17 spans CG16 at 21 % Sgld_v vs CG17 at
2 %).

Outputs:

- ``viral_penetrance_by_SL_then_CG.tsv`` — one row per (SL, CG) above
  thresholds, with CG rate + Wilson CI + parent SL rate + delta.
- ``viral_penetrance_by_SL_then_CG.png`` — 2-panel grouped bar plot
  (top Sgld_v, bottom Wbr_v). X = epidemic SLs, ordered by parent-SL
  Sgld_v rate descending. Each SL gets its own hue (tab20/tab20b); each
  CG within the SL is a darker→lighter shade of that hue (darkest =
  largest CG). Wider gap between SL groups. Wilson 95 % CI error bars.
  Two-tier x-axis: CG number under each bar, SL centred under the group.
"""

from __future__ import annotations

import argparse
from math import sqrt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgb

from bac_genomad.genomad_constants import DEFAULT_METADATA_V2, DEFAULT_VIRAL_PENETRANCE_DIR

CARRIAGE_BRACKETS = ("Sgld_v", "Wbr_v")
BRACKET_FULL_NAMES = {"Sgld_v": "Sugargold virus", "Wbr_v": "Weber virus"}
META_USECOLS = ("Sample", "Sublineage", "Clonal group", "is_kpsc")
TRUE_TOKENS = frozenset({"true", "1", "yes"})


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(TRUE_TOKENS)


def _wilson_ci(count: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95 % CI for a binomial proportion. (nan, nan) when n == 0."""
    if n == 0:
        return float("nan"), float("nan")
    p = count / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _build_table(
    carriage: pd.DataFrame, meta: pd.DataFrame, min_sl: int, min_cg: int
) -> pd.DataFrame:
    """Per-(SL, CG) carriage rates + parent-SL rates + Wilson CIs."""
    kpsc = meta[_truthy(meta["is_kpsc"])][["Sample", "Sublineage", "Clonal group"]]
    print(f"  KpSC samples: {len(kpsc):,} of {len(meta):,}")
    joined = carriage.merge(kpsc, on="Sample", how="inner").dropna(subset=["Sublineage", "Clonal group"])
    joined["Sublineage"] = joined["Sublineage"].astype(str)
    joined["Clonal group"] = joined["Clonal group"].astype(str)
    print(f"  joined+non-null SL+CG rows: {len(joined):,}")

    # Per-SL aggregate (every SL — used as parent rate)
    sl_size = joined.groupby("Sublineage").size().rename("n_sl")
    sl_rates: dict[str, dict[str, float]] = {}
    for b in CARRIAGE_BRACKETS:
        sl_rates[b] = joined.groupby("Sublineage")[f"carries_{b}"].mean().rename(f"pct_{b}_sl") * 100
    epidemic_sls = sl_size[sl_size >= min_sl].sort_values(ascending=False).index.tolist()
    print(f"  epidemic SLs (n ≥ {min_sl}): {len(epidemic_sls)}")

    rows: list[dict] = []
    for sl in epidemic_sls:
        sl_sub = joined[joined["Sublineage"] == sl]
        n_sl_total = int(len(sl_sub))
        sl_sgld = float(sl_sub["carries_Sgld_v"].mean()) * 100
        sl_wbr = float(sl_sub["carries_Wbr_v"].mean()) * 100
        cg_sizes = sl_sub.groupby("Clonal group").size().sort_values(ascending=False)
        for cg, n_cg in cg_sizes.items():
            if n_cg < min_cg:
                continue
            cg_sub = sl_sub[sl_sub["Clonal group"] == cg]
            row: dict = {
                "Sublineage": sl, "Clonal group": cg,
                "n_cg": int(n_cg), "n_sl_total": n_sl_total,
                "pct_Sgld_v_sl": sl_sgld, "pct_Wbr_v_sl": sl_wbr,
            }
            for b in CARRIAGE_BRACKETS:
                k = int(cg_sub[f"carries_{b}"].sum())
                rate = k / int(n_cg)
                lo, hi = _wilson_ci(k, int(n_cg))
                row[f"n_{b}_carriers"] = k
                row[f"pct_{b}_cg"] = 100.0 * rate
                row[f"pct_{b}_cg_ci_lo"] = 100.0 * lo
                row[f"pct_{b}_cg_ci_hi"] = 100.0 * hi
                row[f"delta_{b}_vs_sl"] = (100.0 * rate) - row[f"pct_{b}_sl"]
            rows.append(row)
    return pd.DataFrame(rows)


INTER_SL_PAD = 1.5  # gap between SL groups, in bar-width units
# Per-SL hue palette: tab20 then tab20b (40 distinct colours). Cycled if we
# ever exceed 40 epidemic SLs.
_SL_PALETTE = list(plt.get_cmap("tab20").colors) + list(plt.get_cmap("tab20b").colors)


def _sl_colours(sl_order: list[str]) -> dict[str, tuple[float, float, float]]:
    """Stable per-SL hue from the tab20 + tab20b palette."""
    return {sl: _SL_PALETTE[i % len(_SL_PALETTE)] for i, sl in enumerate(sl_order)}


def _shade_ramp(base_color: tuple[float, float, float], n: int) -> list[tuple[float, float, float]]:
    """Return ``n`` shades of ``base_color`` from darkest (pure base) → lightest.

    Lighter shades are linear blends with white (``alpha`` from 1.0 → 0.35).
    ``n == 1`` returns the base colour unchanged so single-CG SLs aren't faded.
    """
    if n <= 0:
        return []
    if n == 1:
        return [base_color]
    base = np.array(to_rgb(base_color))
    white = np.ones(3)
    alphas = np.linspace(1.0, 0.35, n)
    return [tuple(a * base + (1.0 - a) * white) for a in alphas]


def _layout(df: pd.DataFrame, sl_order: list[str]) -> tuple[pd.DataFrame, list[float], list[tuple[float, str]], list[tuple[float, float, float]]]:
    """Compute bar layout + per-bar shade ramp for grouped CG bars.

    Within each SL, qualifying CGs are sorted by ``n_cg`` desc and laid out
    1 bar-width apart; SL groups are separated by ``INTER_SL_PAD`` bar-widths.
    The CG bars within an SL are shaded from the SL's hue (darkest = largest
    CG) to a faded blend with white (lightest = smallest CG).

    Returns ``(layout_rows, bar_x, slot_centres, bar_colours)`` — all four
    keyed in walk order (same row index in each list).
    """
    sl_hue = _sl_colours(sl_order)
    layout_chunks: list[pd.DataFrame] = []
    bar_x: list[float] = []
    bar_colours: list[tuple[float, float, float]] = []
    slot_centres: list[tuple[float, str]] = []
    cursor = 0.0
    for sl in sl_order:
        sub = df[df["Sublineage"] == sl].sort_values("n_cg", ascending=False)
        n = len(sub)
        if n == 0:
            continue
        xs = [cursor + i for i in range(n)]
        slot_centres.append((cursor + (n - 1) / 2.0, sl))
        bar_x.extend(xs)
        bar_colours.extend(_shade_ramp(sl_hue[sl], n))
        layout_chunks.append(sub)
        cursor += n + INTER_SL_PAD
    layout_rows = pd.concat(layout_chunks, ignore_index=True)
    return layout_rows, bar_x, slot_centres, bar_colours


def _plot_dispersion(
    df: pd.DataFrame, out_png: Path, min_sl: int, min_cg: int
) -> None:
    """2-panel grouped bar plot per bracket: one bar per CG, grouped within its SL."""
    if df.empty:
        print(f"  (no rows for {out_png.name})")
        return

    # SL ordering: by parent Sgld_v carriage descending (so high-Sgld SLs cluster left).
    sl_order = (
        df.drop_duplicates("Sublineage").set_index("Sublineage")["pct_Sgld_v_sl"]
        .sort_values(ascending=False).index.tolist()
    )
    layout_rows, bar_x, slot_centres, bar_colours = _layout(df, sl_order)
    cg_labels = layout_rows["Clonal group"].astype(str).tolist()
    total_width = (max(bar_x) + 0.5) if bar_x else 1.0

    fig, axes = plt.subplots(
        2, 1, figsize=(max(12, 0.45 * len(bar_x) + 4), 10), sharex=True
    )
    for ax, bracket in zip(axes, CARRIAGE_BRACKETS, strict=False):
        rates = layout_rows[f"pct_{bracket}_cg"].to_numpy()
        ci_lo = layout_rows[f"pct_{bracket}_cg_ci_lo"].to_numpy()
        ci_hi = layout_rows[f"pct_{bracket}_cg_ci_hi"].to_numpy()
        err_lo = np.maximum(rates - ci_lo, 0)
        err_hi = np.maximum(ci_hi - rates, 0)
        ax.bar(
            bar_x, rates, width=0.9,
            color=bar_colours, edgecolor="black", linewidth=0.5, zorder=3,
        )
        ax.errorbar(
            bar_x, rates, yerr=[err_lo, err_hi],
            fmt="none", ecolor="black", capsize=2.5, linewidth=0.9, zorder=4,
        )
        ax.set_ylim(bottom=0)
        ax.set_ylabel(f"{bracket} carriage (%)")
        ax.set_title(
            f"{bracket} ({BRACKET_FULL_NAMES[bracket]}) carriage by Clonal group within each epidemic Sublineage  "
            f"(SL n ≥ {min_sl}; CG n ≥ {min_cg}; Wilson 95 % CI)"
        )
        ax.grid(axis="y", alpha=0.25)

    # Two-tier x-axis: per-bar CG label (top tier, on the axis) + SL name
    # centred under the group (bottom tier, in axes-fraction coords).
    axes[-1].set_xticks(bar_x)
    axes[-1].set_xticklabels(cg_labels, rotation=90, fontsize=7)
    axes[-1].set_xlim(-0.7, total_width)
    for centre, sl in slot_centres:
        axes[-1].text(
            centre, -0.12, sl,
            ha="center", va="top", fontsize=9, fontweight="bold",
            transform=axes[-1].get_xaxis_transform(),
        )
    fig.subplots_adjust(bottom=0.20)

    fig.suptitle(
        "Standalone-viral peak carriage — per-CG within epidemic SL\n"
        "(KpSC universe; SL groups ordered by parent Sgld_v rate descending; "
        "within-group bars sorted by CG sample count descending)",
        fontsize=12,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_png}")


def main() -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--carriage-tsv", type=Path,
        default=DEFAULT_VIRAL_PENETRANCE_DIR / "viral_bracket_carriage_per_sample.tsv",
        help="Per-Sample carriage TSV from viral_penetrance.per_lineage.",
    )
    parser.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_VIRAL_PENETRANCE_DIR)
    parser.add_argument("--min-sl", type=int, default=250,
                        help="Minimum KpSC samples in an SL for it to count as 'epidemic'.")
    parser.add_argument("--min-cg", type=int, default=50,
                        help="Minimum KpSC samples in a CG for it to be plotted within its SL.")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"reading carriage table: {args.carriage_tsv}")
    carriage = pd.read_csv(args.carriage_tsv, sep="\t", dtype={"Sample": str})
    print(f"  {len(carriage):,} rows")

    print(f"reading metadata_v2: {args.metadata_v2}")
    meta = pd.read_csv(args.metadata_v2, sep="\t", dtype=str, usecols=list(META_USECOLS))
    print(f"  {len(meta):,} rows")

    table = _build_table(carriage, meta, args.min_sl, args.min_cg)
    tsv_path = args.out_dir / "viral_penetrance_by_SL_then_CG.tsv"
    table.to_csv(tsv_path, sep="\t", index=False)
    print(f"\nwrote {tsv_path}  rows={len(table):,}")

    # Per-SL summary print (CG-level dispersion)
    if not table.empty:
        spread = table.groupby("Sublineage").agg(
            n_cgs=("Clonal group", "size"),
            n_sl=("n_sl_total", "first"),
            pct_Sgld_min=("pct_Sgld_v_cg", "min"),
            pct_Sgld_max=("pct_Sgld_v_cg", "max"),
            pct_Wbr_min=("pct_Wbr_v_cg", "min"),
            pct_Wbr_max=("pct_Wbr_v_cg", "max"),
        )
        spread["Sgld_spread"] = spread["pct_Sgld_max"] - spread["pct_Sgld_min"]
        spread["Wbr_spread"] = spread["pct_Wbr_max"] - spread["pct_Wbr_min"]
        spread = spread.sort_values("Sgld_spread", ascending=False)
        print("\n=== Intra-SL CG carriage spread (max - min, pp) ===")
        print(f"  {'SL':<8} {'#CGs':>5} {'n_SL':>7}  {'Sgld_spread':>11}  {'Wbr_spread':>11}")
        for sl, r in spread.iterrows():
            print(
                f"  {sl:<8} {int(r['n_cgs']):>5} {int(r['n_sl']):>7,}  "
                f"{r['Sgld_spread']:>10.1f}pp  {r['Wbr_spread']:>10.1f}pp"
            )

    png_path = args.out_dir / "viral_penetrance_by_SL_then_CG.png"
    _plot_dispersion(table, png_path, args.min_sl, args.min_cg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
