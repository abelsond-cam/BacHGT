#!/usr/bin/env python3
"""Bar chart of cohort sizes — LR assemblies vs matched paired-SR partners.

One plot, three cohort groups (`lra_final_list`, `complete_genome`,
`reference_genome`), two bars per group: total LR assemblies in the
cohort, and the subset that has a matched `sr_biosample` partner (the
paired SR shadow). Lets you read the cohort funnel and the paired
fraction directly off the page.
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
    PAIRED_COHORTS,
)

_LR_COLOR = "#1f77b4"
_SR_COLOR = "#ff7f0e"


def _bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _counts(meta: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """Return ``{cohort: (n_lr_total, n_lr_with_sr_partner)}`` for each cohort."""
    lra = _bool(meta["lra_final_list"])
    comp = _bool(meta["is_complete"])
    ref = _bool(meta["is_reference_genome"])
    sr = meta["sr_biosample"].notna()
    masks = {
        "lra_final_list": lra,
        "complete_genome": lra & comp,
        "reference_genome": lra & ref,
    }
    return {name: (int(m.sum()), int((m & sr).sum())) for name, m in masks.items()}


def _plot(counts: dict[str, tuple[int, int]], out_png: Path) -> None:
    cohorts = list(PAIRED_COHORTS)
    lr_vals = [counts[c][0] for c in cohorts]
    sr_vals = [counts[c][1] for c in cohorts]

    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    x = np.arange(len(cohorts))
    width = 0.38

    bars_lr = ax.bar(x - width / 2, lr_vals, width, color=_LR_COLOR,
                     edgecolor="black", linewidth=0.5, label="LR assemblies")
    bars_sr = ax.bar(x + width / 2, sr_vals, width, color=_SR_COLOR,
                     edgecolor="black", linewidth=0.5, label="Matched paired SR")

    for bars in (bars_lr, bars_sr):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h, f"{int(h):,}",
                    ha="center", va="bottom", fontsize=9)

    pct = [100 * sr / lr if lr else float("nan") for lr, sr in zip(lr_vals, sr_vals, strict=False)]
    for i, p in enumerate(pct):
        if not np.isnan(p):
            ax.text(i + width / 2, sr_vals[i] / 2, f"{p:.0f}% paired",
                    ha="center", va="center", fontsize=8, color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(cohorts)
    ax.set_ylabel("n biosamples")
    ax.set_title("Cohort sizes — LR assemblies and matched paired SR shadow")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=True)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.set_ylim(top=max(lr_vals) * 1.20)

    descriptors = {
        "lra_final_list": (
            "All long read assemblies with CheckM2\n"
            "completeness > 99% and contamination < 5%"
        ),
        "complete_genome": (
            "NCBI 'complete': all long read assemblies\n"
            "which also have circular closed contigs"
        ),
        "reference_genome": (
            "Complete assemblies using a hybrid of\n"
            "short and long read technologies"
        ),
    }
    for i, c in enumerate(cohorts):
        ax.text(
            i, 0.97, descriptors[c],
            transform=ax.get_xaxis_transform(),
            ha="center", va="top",
            fontsize=9, fontstyle="italic", color="#333",
        )

    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)
    print(f"wrote {out_png}")


def main() -> None:
    """CLI entry point — write the cohort-size bar chart."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loading metadata_v2: {args.metadata_v2}")
    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    print(f"  rows: {len(meta):,}")
    counts = _counts(meta)
    for c, (lr, sr) in counts.items():
        pct = 100 * sr / lr if lr else float("nan")
        print(f"  {c:<18} LR={lr:>6,}  matched-SR={sr:>6,}  ({pct:.1f}% paired)")
    _plot(counts, args.output_dir / "lra_vs_sr_cohort_sizes.png")


if __name__ == "__main__":
    main()
