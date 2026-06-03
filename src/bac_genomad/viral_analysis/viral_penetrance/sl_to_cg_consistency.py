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
- ``viral_penetrance_by_SL_then_CG.png`` — 2-panel dispersion plot
  (top Sgld_v, bottom Wbr_v). X = epidemic SLs, ordered by parent-SL
  Sgld_v rate descending. For each SL: one dot per qualifying CG at
  the SL's x position (small horizontal jitter so dots don't overlay),
  size = CG sample count, vertical line = Wilson 95 % CI, black bar
  across the slot = parent-SL carriage rate.
"""

from __future__ import annotations

import argparse
from math import sqrt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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


def _plot_dispersion(
    df: pd.DataFrame, out_png: Path, min_sl: int, min_cg: int
) -> None:
    """2-panel dispersion plot per bracket: CG dots + Wilson CIs + parent-SL bar."""
    if df.empty:
        print(f"  (no rows for {out_png.name})")
        return

    # SL ordering: by parent Sgld_v carriage descending (so the "high-Sgld" SLs cluster left)
    sl_order = (
        df.drop_duplicates("Sublineage").set_index("Sublineage")["pct_Sgld_v_sl"]
        .sort_values(ascending=False).index.tolist()
    )
    sl_x = {sl: i for i, sl in enumerate(sl_order)}

    fig, axes = plt.subplots(2, 1, figsize=(max(12, 0.5 * len(sl_order) + 4), 11), sharex=True)
    for ax, bracket in zip(axes, CARRIAGE_BRACKETS, strict=False):
        # Parent-SL bars (drawn first so CG dots overlay)
        for sl in sl_order:
            sl_rate = float(df[df["Sublineage"] == sl][f"pct_{bracket}_sl"].iloc[0])
            ax.hlines(sl_rate, sl_x[sl] - 0.40, sl_x[sl] + 0.40,
                      colors="black", linewidth=2.5, zorder=3,
                      label="parent SL rate" if sl == sl_order[0] else None)

        # CG dots with Wilson CI
        for _, row in df.iterrows():
            x = sl_x[row["Sublineage"]]
            # Jitter within the slot based on a stable hash of the CG name so re-runs match
            jitter = (hash(str(row["Clonal group"])) % 1000) / 1000.0 * 0.6 - 0.30
            xj = x + jitter
            yc = row[f"pct_{bracket}_cg"]
            ylo = row[f"pct_{bracket}_cg_ci_lo"]
            yhi = row[f"pct_{bracket}_cg_ci_hi"]
            ax.vlines(xj, ylo, yhi, colors="#444", linewidth=1.0, alpha=0.7, zorder=4)
            ax.scatter(
                [xj], [yc],
                s=max(20.0, 5.0 * np.sqrt(row["n_cg"])),
                color="#1f77b4", edgecolor="black", linewidth=0.5,
                alpha=0.75, zorder=5,
            )

        ax.set_ylim(bottom=-2)
        ax.set_ylabel(f"{bracket} carriage (%)")
        ax.set_title(
            f"{bracket} ({BRACKET_FULL_NAMES[bracket]}) carriage by Clonal group within each epidemic Sublineage  "
            f"(SL n ≥ {min_sl}; CG n ≥ {min_cg})  —  dot size ∝ √n_CG, vertical line = Wilson 95 % CI"
        )
        ax.grid(axis="y", alpha=0.25)
        ax.legend(loc="upper right", fontsize=8)

    axes[-1].set_xticks(np.arange(len(sl_order)))
    axes[-1].set_xticklabels(sl_order, rotation=45, ha="right", fontsize=9)
    axes[-1].set_xlim(-0.7, len(sl_order) - 0.3)

    fig.suptitle(
        "Standalone-viral peak carriage — per-CG within epidemic SL\n"
        "(KpSC universe; SL ordered by parent Sgld_v rate descending)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
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
