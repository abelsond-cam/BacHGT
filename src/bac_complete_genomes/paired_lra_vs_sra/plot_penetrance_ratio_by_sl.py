#!/usr/bin/env python3
"""Per-Sublineage paired LR/SR sensitivity-ratio plot, ``reference_genome`` cohort.

Same picture as ``plot_penetrance_ratio.py`` for the paired ``reference_genome``
cohort, but stratified vertically by Sublineage — one sub-panel per SL with
``> --min-sl`` paired reference genomes (default 5). Feature order is locked
across panels to match the aggregate
``lra_vs_sr_*_ratio__reference_genome.png`` plot, so rows align across SLs for
visual comparison.

Runs the same paired-cohort selection + merge + wide-row builders that the
aggregate driver uses (``compare_lra_to_sra._run_paired_cohort``), then groups
on ``merged["Sublineage"]`` before calling the row builders per group.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bac_complete_genomes.compare_lra_to_sra import (
    DEFAULT_METADATA_V2,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SR_SHADOW,
    _paired_features,
    _paired_isescan_features,
    _select_paired_cohort,
)
from bac_complete_genomes.paired_lra_vs_sra.plot_penetrance_ratio import (
    _classify,
    _color_for,
    _paired_log_ratio_ci,
)

_COHORT = "reference_genome"


def _load_merged(metadata_v2: Path, sr_shadow: Path) -> pd.DataFrame:
    """Load metadata_v2 + sr_shadow and return the paired reference_genome merge."""
    meta = pd.read_csv(metadata_v2, sep="\t", low_memory=False)
    shadow = pd.read_csv(sr_shadow, sep="\t", low_memory=False)
    shadow["sr_biosample"] = shadow["sr_biosample"].astype(str)
    paired_meta = _select_paired_cohort(meta, _COHORT)
    return paired_meta.merge(shadow, on="sr_biosample", how="inner", suffixes=("", "_shadow"))


def _qualifying_sls(merged: pd.DataFrame, min_sl: int) -> pd.Series:
    """Sublineage value-counts (descending) limited to SLs with ``count > min_sl``."""
    if "Sublineage" not in merged.columns:
        raise KeyError("merged frame is missing the 'Sublineage' column")
    counts = merged["Sublineage"].dropna().astype(str).value_counts()
    return counts[counts > min_sl]


def _feature_order(input_dir: Path, kind: str) -> list[str]:
    """Return the feature names from the aggregate TSV, sorted by ratio ascending.

    Matches the y-axis ordering used by
    ``plot_penetrance_ratio._plot_one`` so panel rows align with the parent
    figure.
    """
    tsv = input_dir / f"lra_vs_sr_{kind}__{_COHORT}.tsv"
    df = pd.read_csv(tsv, sep="\t")
    df = df.sort_values("lr_sr_sensitivity_ratio", ascending=True, na_position="last")
    return df["feature"].tolist()


def _wide_for_sl(merged_sl: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Run the shared paired row builder on one SL subset of ``merged``."""
    rows = _paired_features(merged_sl) if kind == "kleborate" else _paired_isescan_features(merged_sl)
    return pd.DataFrame(rows)


def _aligned(df: pd.DataFrame, feature_order: list[str]) -> pd.DataFrame:
    """Reindex wide rows to a fixed feature order; missing features become NaN rows."""
    if df.empty:
        return pd.DataFrame({"feature": feature_order})
    return df.set_index("feature").reindex(feature_order).reset_index()


def _x_max(per_sl: dict[str, pd.DataFrame]) -> float:
    """Global x-axis upper bound — max finite ``ci_hi`` (or ratio) across all SLs."""
    finite: list[float] = []
    for df in per_sl.values():
        ci = _paired_log_ratio_ci(df)
        for col in ("ci_hi", "ratio"):
            vals = ci[col].replace([np.inf, -np.inf], np.nan).dropna()
            finite.extend(vals.tolist())
    return max(2.0, (max(finite) if finite else 2.0) * 1.05)


def _plot_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    *,
    x_max: float,
    show_xlabel: bool,
) -> None:
    """Render one SL panel onto a shared x-axis ``Axes``."""
    df = _paired_log_ratio_ci(df).reset_index(drop=True)
    n = len(df)
    y = np.arange(n)
    ratio = df["ratio"].to_numpy(dtype=float)
    lo = df["ci_lo"].to_numpy(dtype=float)
    hi = df["ci_hi"].to_numpy(dtype=float)

    classes = df["feature"].map(_classify)
    colors = [_color_for(c) for c in classes]

    # NaN ratios (feature absent in this SL, or SR sens = 0) render as no bar.
    finite = np.isfinite(ratio)
    ax.barh(
        y[finite],
        ratio[finite],
        color=[colors[i] for i in np.where(finite)[0]],
        edgecolor="black",
        linewidth=0.4,
        alpha=0.85,
        height=0.7,
    )

    ci_ok = finite & np.isfinite(lo) & np.isfinite(hi)
    if ci_ok.any():
        err_lo = np.clip(ratio[ci_ok] - lo[ci_ok], 0, None)
        err_hi = np.clip(hi[ci_ok] - ratio[ci_ok], 0, None)
        ax.errorbar(
            ratio[ci_ok],
            y[ci_ok],
            xerr=[err_lo, err_hi],
            fmt="none",
            ecolor="black",
            elinewidth=0.8,
            capsize=2.5,
        )

    ax.axvline(1.0, linestyle="--", color="black", linewidth=0.9, alpha=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(df["feature"].tolist(), fontsize=6.5)
    ax.set_title(title, fontsize=9, loc="left")
    ax.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.5)
    if show_xlabel:
        ax.set_xlabel("LR / SR per-genome sensitivity ratio (95% CI)")
    ax.set_xlim(0.9, x_max)


def _render_stacked(
    per_sl: dict[str, pd.DataFrame],
    feature_order: list[str],
    out_png: Path,
    title: str,
) -> None:
    """Render one stacked figure: one panel per SL, sharex, locked feature order."""
    sls = list(per_sl.keys())
    n_sls = len(sls)
    if n_sls == 0:
        print(f"  no qualifying SLs; skipping {out_png.name}")
        return
    n_features = len(feature_order)
    aligned = {sl: _aligned(per_sl[sl], feature_order) for sl in sls}

    x_max = _x_max(aligned)

    panel_h = max(1.8, 0.22 * n_features + 0.5)
    fig_h = panel_h * n_sls + 1.0
    fig, axes = plt.subplots(n_sls, 1, sharex=True, figsize=(9.0, fig_h), squeeze=False)
    axes = axes[:, 0]

    for i, sl in enumerate(sls):
        df = aligned[sl]
        n_pairs = int(df["n_lr"].dropna().max()) if df["n_lr"].notna().any() else 0
        _plot_panel(
            axes[i],
            df,
            title=f"{sl}  (n={n_pairs})",
            x_max=x_max,
            show_xlabel=(i == n_sls - 1),
        )

    fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(out_png, dpi=200)
    plt.close(fig)
    print(f"wrote {out_png}")


def main() -> None:
    """CLI entry point — per-SL stacked plots for the paired reference_genome cohort."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    parser.add_argument("--sr-shadow", type=Path, default=DEFAULT_SR_SHADOW)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where the aggregate lra_vs_sr_*__reference_genome.tsv files live (feature ordering).",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--min-sl",
        type=int,
        default=5,
        help="Keep SLs with count > this many paired reference genomes. Default 5.",
    )
    parser.add_argument(
        "--list-sls",
        action="store_true",
        help="Print qualifying SLs and exit. No PNGs written.",
    )
    parser.add_argument(
        "--write-tsvs",
        action="store_true",
        help="Also write per-SL wide TSVs under <output-dir>/per_sublineage/reference_genome/<SL>/.",
    )
    args = parser.parse_args()

    print(f"Loading metadata_v2: {args.metadata_v2}")
    print(f"Loading SR-shadow:   {args.sr_shadow}")
    merged = _load_merged(args.metadata_v2, args.sr_shadow)
    print(f"Paired reference_genome rows: {len(merged):,}")

    sl_counts = _qualifying_sls(merged, args.min_sl)
    print("\nSublineage\tn_paired_reference")
    for sl, n in sl_counts.items():
        print(f"{sl}\t{int(n)}")
    print(f"n_qualifying SLs (> {args.min_sl} paired reference genomes): {len(sl_counts)}")

    if args.list_sls:
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if len(sl_counts) == 0:
        print("No qualifying SLs; nothing to plot.")
        return

    klebo_order = _feature_order(args.input_dir, "kleborate")
    isescan_order = _feature_order(args.input_dir, "isescan")

    per_sl_klebo: dict[str, pd.DataFrame] = {}
    per_sl_isescan: dict[str, pd.DataFrame] = {}
    for sl in sl_counts.index:
        sub = merged[merged["Sublineage"].astype(str) == sl]
        klebo_df = _wide_for_sl(sub, "kleborate")
        isescan_df = _wide_for_sl(sub, "isescan")
        per_sl_klebo[sl] = klebo_df
        per_sl_isescan[sl] = isescan_df
        if args.write_tsvs:
            sl_dir = args.output_dir / "per_sublineage" / _COHORT / sl.replace("/", "_")
            sl_dir.mkdir(parents=True, exist_ok=True)
            klebo_df.to_csv(sl_dir / "kleborate.tsv", sep="\t", index=False, na_rep="")
            isescan_df.to_csv(sl_dir / "isescan.tsv", sep="\t", index=False, na_rep="")

    _render_stacked(
        per_sl_klebo,
        klebo_order,
        args.output_dir / f"lra_vs_sr_prevalence_kleborate_ratio__{_COHORT}__by_SL.png",
        f"LR vs SR per-genome sensitivity ratio — Kleborate ({_COHORT}, by Sublineage)",
    )
    _render_stacked(
        per_sl_isescan,
        isescan_order,
        args.output_dir / f"lra_vs_sr_prevalence_isescan_ratio__{_COHORT}__by_SL.png",
        f"LR vs SR per-genome sensitivity ratio — ISEScan ({_COHORT}, by Sublineage)",
    )


if __name__ == "__main__":
    main()
