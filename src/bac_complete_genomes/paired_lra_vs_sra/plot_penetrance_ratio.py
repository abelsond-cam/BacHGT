#!/usr/bin/env python3
"""Horizontal bar chart of paired LR/SR pickup ratio per feature.

Reads the wide TSVs written by ``compare_lra_to_sra --mode paired``:

    lra_vs_sr_kleborate__<cohort>.tsv
    lra_vs_sr_isescan__<cohort>.tsv

For each row computes the 95% CI on the paired pickup ratio using the
delta-method log-ratio variance for matched binary data (Nam 1995):

    Var(log R) = (b + c) / [(a + b) (a + c)]

with the 2×2 cells recovered from the wide schema:

    b + c = n_lr * (1 - penetrance_concordance)
    a + b = n_lr * lr_pickup
    a + c = n_lr * sr_pickup

The bars are sorted by ratio descending; a dashed line at x=1 marks
equivalence. Writes one PNG per feature class.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bac_complete_genomes.compare_lra_to_sra import DEFAULT_OUTPUT_DIR

_VIRULENCE_COLOR = "#1f77b4"
_MLST_COLOR = "#7f7f7f"
_AMR_COLOR = "#d62728"
_ISESCAN_COLOR = "#2ca02c"


def _classify(feature: str) -> str:
    if feature.endswith(" bsc"):
        return "virulence"
    if feature.endswith(" chromosomal"):
        return "mlst"
    if feature.endswith("_acquired"):
        return "amr"
    return "isescan"


def _color_for(feature_class: str) -> str:
    return {
        "virulence": _VIRULENCE_COLOR,
        "mlst": _MLST_COLOR,
        "amr": _AMR_COLOR,
        "isescan": _ISESCAN_COLOR,
    }[feature_class]


def _paired_log_ratio_ci(df: pd.DataFrame, z: float = 1.96) -> pd.DataFrame:
    """Add ``ratio``, ``ci_lo``, ``ci_hi`` (95% delta-method paired CI on log R)."""
    out = df.copy()
    n = out["n_lr"].astype(float)
    p_lr = out["lr_pickup"].astype(float)
    p_sr = out["sr_pickup"].astype(float)
    conc = out["penetrance_concordance"].astype(float)

    # SE(log R) = sqrt( (1 - concordance) / (n * p_lr * p_sr) )
    with np.errstate(divide="ignore", invalid="ignore"):
        var_log = (1.0 - conc) / (n * p_lr * p_sr)
        se_log = np.sqrt(var_log)

    ratio = out["lr_sr_pickup_ratio"].astype(float)
    out["ratio"] = ratio
    out["ci_lo"] = ratio * np.exp(-z * se_log)
    out["ci_hi"] = ratio * np.exp(+z * se_log)
    return out


def _plot_one(df: pd.DataFrame, out_png: Path, title: str) -> None:
    """Render a single horizontal bar+CI plot, sorted by ratio descending."""
    df = _paired_log_ratio_ci(df).sort_values("ratio", ascending=True).reset_index(drop=True)

    n = len(df)
    fig_h = max(3.5, 0.32 * n + 1.5)
    fig, ax = plt.subplots(figsize=(8.5, fig_h))

    y = np.arange(n)
    ratio = df["ratio"].to_numpy()
    lo = df["ci_lo"].to_numpy()
    hi = df["ci_hi"].to_numpy()
    err_lo = np.clip(ratio - lo, 0, None)
    err_hi = np.clip(hi - ratio, 0, None)

    classes = df["feature"].map(_classify)
    colors = [_color_for(c) for c in classes]

    ax.barh(y, ratio, color=colors, edgecolor="black", linewidth=0.4, alpha=0.85, height=0.7)
    ax.errorbar(
        ratio,
        y,
        xerr=[err_lo, err_hi],
        fmt="none",
        ecolor="black",
        elinewidth=0.8,
        capsize=2.5,
    )

    ax.axvline(1.0, linestyle="--", color="black", linewidth=0.9, alpha=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(df["feature"].tolist(), fontsize=8)
    ax.set_xlabel("LR / SR pickup ratio (95% CI)")
    ax.set_title(title)

    x_max = float(np.nanmax(hi)) if np.isfinite(hi).any() else float(np.nanmax(ratio))
    ax.set_xlim(0.9, max(2.0, x_max * 1.05))
    ax.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.5)

    # Legend only for the classes present.
    present = sorted(set(classes))
    if len(present) > 1:
        handles = [plt.Rectangle((0, 0), 1, 1, color=_color_for(c), alpha=0.85) for c in present]
        ax.legend(handles, present, loc="lower right", fontsize=8, frameon=True)

    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)
    print(f"wrote {out_png}")


def main() -> None:
    """CLI entry point — write the two PNGs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cohort", default="reference_genome")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    klebo_tsv = args.input_dir / f"lra_vs_sr_kleborate__{args.cohort}.tsv"
    isescan_tsv = args.input_dir / f"lra_vs_sr_isescan__{args.cohort}.tsv"

    klebo = pd.read_csv(klebo_tsv, sep="\t")
    isescan = pd.read_csv(isescan_tsv, sep="\t")

    _plot_one(
        klebo,
        args.output_dir / "lra_vs_sr_prevalence_kleborate_ratio.png",
        f"LR vs SR pickup ratio — Kleborate ({args.cohort})",
    )
    _plot_one(
        isescan,
        args.output_dir / "lra_vs_sr_prevalence_isescan_ratio.png",
        f"LR vs SR pickup ratio — ISEScan ({args.cohort})",
    )


if __name__ == "__main__":
    main()
