#!/usr/bin/env python3
"""Characterise the two main standalone-viral length peaks (~55 kb, ~110 kb).

Reads ``standalone_viral_lengths.tsv`` (the per-Sample × per-contig length
dump from ``compare_lra_to_sr dump_lengths``), restricts to one cohort × side
(default ``is_complete`` × ``lra_all``), splits the data into two length
windows ("lower peak", "upper peak"), and reports for each:

  - window-bounded summary stats: ``n``, ``mean``, ``median``, ``std``, ``IQR``,
    ``p5``/``p95``, modal 2-kb bin
  - a Gaussian peak fit (``A``, ``μ``, ``σ``, FWHM) via ``scipy.optimize.curve_fit``
    on the binned histogram

Also writes a side-by-side zoomed-histogram PNG with the Gaussian fit
overlaid + median + IQR marked.

Defaults assume the user's observed peak ranges (~55 kb and ~110 kb in the
is_complete cohort); the trough between them sits around 75-80 kb, so the
default window split is at 78 kb. Override via CLI for other cohorts /
sides / window cuts.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from bac_genomad.genomad_constants import DEFAULT_VIRAL_LR_VS_SR_DIR

DEFAULT_INPUT = DEFAULT_VIRAL_LR_VS_SR_DIR / "standalone_viral_lengths.tsv"


def _gaussian(x: np.ndarray, amp: float, mu: float, sigma: float) -> np.ndarray:
    """Single-Gaussian peak: ``amp * exp(-(x-mu)^2 / (2*sigma^2))``."""
    return amp * np.exp(-((x - mu) ** 2) / (2.0 * sigma**2))


def _fit_peak(lens_bp: np.ndarray, bin_bp: int) -> dict:
    """Fit a single Gaussian to the binned histogram; None fields on fit failure."""
    if len(lens_bp) < 5:
        return {"amp": None, "mu": None, "sigma": None, "fwhm": None}
    edges = np.arange(lens_bp.min(), lens_bp.max() + bin_bp, bin_bp)
    counts, edges = np.histogram(lens_bp, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2.0
    p0 = [float(counts.max()), float(np.median(lens_bp)), float(np.std(lens_bp))]
    try:
        popt, _ = curve_fit(_gaussian, centers, counts, p0=p0, maxfev=4000)
        amp, mu, sigma = popt
        sigma = abs(sigma)
        return {"amp": float(amp), "mu": float(mu), "sigma": float(sigma), "fwhm": float(2.3548 * sigma)}
    except (RuntimeError, ValueError):
        return {"amp": None, "mu": None, "sigma": None, "fwhm": None}


def _modal_bin(lens_bp: np.ndarray, bin_bp: int) -> int:
    """Return the centre (bp) of the most-populated ``bin_bp``-wide bin."""
    edges = np.arange(lens_bp.min(), lens_bp.max() + bin_bp, bin_bp)
    counts, edges = np.histogram(lens_bp, bins=edges)
    idx = int(np.argmax(counts))
    return int((edges[idx] + edges[idx + 1]) / 2.0)


def _summarise(lens_bp: np.ndarray, bin_bp: int) -> dict:
    """Return distribution summary for a length array (bp)."""
    if len(lens_bp) == 0:
        return dict.fromkeys(
            ("n", "mean", "median", "std", "p25", "p75", "IQR", "p5", "p95", "min", "max", "mode_bin"),
            None,
        )
    p25 = float(np.percentile(lens_bp, 25))
    p75 = float(np.percentile(lens_bp, 75))
    return {
        "n": int(len(lens_bp)),
        "mean": float(np.mean(lens_bp)),
        "median": float(np.median(lens_bp)),
        "std": float(np.std(lens_bp, ddof=1)) if len(lens_bp) > 1 else float("nan"),
        "p25": p25,
        "p75": p75,
        "IQR": p75 - p25,
        "p5": float(np.percentile(lens_bp, 5)),
        "p95": float(np.percentile(lens_bp, 95)),
        "min": int(np.min(lens_bp)),
        "max": int(np.max(lens_bp)),
        "mode_bin": _modal_bin(lens_bp, bin_bp),
    }


def _print_peak_table(rows: list[dict], cohort: str, side: str) -> None:
    print(f"\n=== Peak characterisation: cohort={cohort}, side={side} ===")
    header = f"  {'window':<22} {'n':>5} {'mean':>9} {'median':>9} {'std':>9} {'IQR':>9} {'mode':>8} {'μ':>9} {'σ':>8} {'FWHM':>8}"
    print(header)
    for r in rows:
        gmu = f"{r['gauss_mu']:,.0f}" if r["gauss_mu"] is not None else "-"
        gsig = f"{r['gauss_sigma']:,.0f}" if r["gauss_sigma"] is not None else "-"
        gfwhm = f"{r['gauss_fwhm']:,.0f}" if r["gauss_fwhm"] is not None else "-"
        print(
            f"  {r['window']:<22} {r['n']:>5,} {r['mean']:>9,.0f} {r['median']:>9,.0f}"
            f" {r['std']:>9,.0f} {r['IQR']:>9,.0f} {r['mode_bin']:>8,}"
            f" {gmu:>9} {gsig:>8} {gfwhm:>8}"
        )


def _plot_zoom(
    plots: list[tuple],
    cohort: str,
    side: str,
    bin_bp: int,
    out_png: Path,
) -> None:
    """Two-panel zoomed histogram with Gaussian fit + median/IQR markers."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, (name, lo_bp, hi_bp, lens_bp, stats, fit) in zip(axes, plots, strict=False):
        edges = np.arange(lo_bp, hi_bp + bin_bp, bin_bp) / 1000.0
        ax.hist(
            lens_bp / 1000.0, bins=edges,
            alpha=0.55, color="#1f77b4", edgecolor="#1f77b4",
            label=f"data (n={len(lens_bp):,})",
        )
        if fit["mu"] is not None:
            xfit = np.linspace(lo_bp, hi_bp, 400)
            yfit = _gaussian(xfit, fit["amp"], fit["mu"], fit["sigma"])
            ax.plot(
                xfit / 1000.0, yfit, color="black", linewidth=1.5,
                label=f"Gaussian fit  μ={fit['mu']/1000:.1f} kb,  σ={fit['sigma']/1000:.2f} kb,  FWHM={fit['fwhm']/1000:.2f} kb",
            )
        ax.axvline(stats["median"] / 1000.0, color="red", linestyle="-", linewidth=1.5,
                   label=f"median = {stats['median']/1000:.1f} kb")
        ax.axvline(stats["p25"] / 1000.0, color="red", linestyle="--", linewidth=1, alpha=0.6)
        ax.axvline(stats["p75"] / 1000.0, color="red", linestyle="--", linewidth=1, alpha=0.6,
                   label=f"IQR = {stats['p25']/1000:.1f}-{stats['p75']/1000:.1f} kb")
        ax.set_xlabel("standalone viral contig length (kb)")
        ax.set_ylabel("contigs")
        ax.set_title(f"{name}  window [{lo_bp/1000:.0f} – {hi_bp/1000:.0f}] kb")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.2)
    fig.suptitle(
        f"Standalone viral contig peaks — {cohort} cohort, {side} series"
        f"  ({bin_bp//1000} kb bins, Gaussian peak fit)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    print(f"wrote {out_png}")


def main() -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_VIRAL_LR_VS_SR_DIR)
    parser.add_argument("--cohort", default="is_complete",
                        help="One of: reference_genome, is_complete, is_hybrid, lra_final_list")
    parser.add_argument("--side", default="lra_all",
                        help="One of: lra, lra_all, sr (use lra_all for tightest peaks).")
    parser.add_argument("--lower-window-kb", type=float, nargs=2, default=(35.0, 78.0),
                        metavar=("LO", "HI"),
                        help="Window enclosing the lower peak, in kb (default 35-78).")
    parser.add_argument("--upper-window-kb", type=float, nargs=2, default=(78.0, 160.0),
                        metavar=("LO", "HI"),
                        help="Window enclosing the upper peak, in kb (default 78-160).")
    parser.add_argument("--bin-kb", type=float, default=2.0,
                        help="Histogram bin width in kb (default 2).")
    args = parser.parse_args()

    bin_bp = int(args.bin_kb * 1000)
    df = pd.read_csv(args.input, sep="\t", dtype={"Sample": str, "contig": str, "length": int})
    sub = df[(df["cohort"] == args.cohort) & (df["side"] == args.side) & df["length"].notna()]
    print(f"loaded {len(sub):,} {args.side} contigs in {args.cohort} cohort  ({args.input})")
    if sub.empty:
        return 1

    rows: list[dict] = []
    plots: list[tuple] = []
    for name, lo_kb, hi_kb in [
        ("peak_lower (~55 kb)", *args.lower_window_kb),
        ("peak_upper (~110 kb)", *args.upper_window_kb),
    ]:
        lo_bp = int(lo_kb * 1000)
        hi_bp = int(hi_kb * 1000)
        lens = sub.loc[(sub["length"] >= lo_bp) & (sub["length"] < hi_bp), "length"].to_numpy()
        stats = _summarise(lens, bin_bp)
        fit = _fit_peak(lens, bin_bp)
        row = {"window": name, "lo_bp": lo_bp, "hi_bp": hi_bp, **stats,
               "gauss_amp": fit["amp"], "gauss_mu": fit["mu"],
               "gauss_sigma": fit["sigma"], "gauss_fwhm": fit["fwhm"]}
        rows.append(row)
        plots.append((name, lo_bp, hi_bp, lens, stats, fit))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stats_path = args.out_dir / f"standalone_viral_peak_stats_{args.cohort}_{args.side}.tsv"
    pd.DataFrame(rows).to_csv(stats_path, sep="\t", index=False)
    print(f"wrote {stats_path}")

    _print_peak_table(rows, args.cohort, args.side)

    png_path = args.out_dir / f"standalone_viral_peak_zoom_{args.cohort}_{args.side}.png"
    _plot_zoom(plots, args.cohort, args.side, bin_bp, png_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
