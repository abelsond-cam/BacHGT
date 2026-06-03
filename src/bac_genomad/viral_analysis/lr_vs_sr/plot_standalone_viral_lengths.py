#!/usr/bin/env python3
"""Plot per-cohort standalone-viral contig length distributions (LRA vs paired SR).

Reads ``standalone_viral_lengths.tsv`` (produced by an ad-hoc length-dump pass
over ``genomad_virus_summary_long.tsv`` + ``contig_lengths_paired.tsv``; see
``compare_lra_to_sr``'s ``_classify_virus_coords`` for the classification
rules) and writes a 4-panel PNG — one panel per cohort, LRA + paired SR
overlaid — to ``standalone_viral_lengths.png`` beside the input.

Log-spaced bins from 200 bp to 200 kb; vertical reference lines at the size-bin
cuts used by ``compare_lra_to_sr`` (20 kb, 80 kb) plus an extra line at 2 kb to
flag the SR-noise floor seen in the data.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bac_genomad.genomad_constants import DEFAULT_COMPARE_OUT_DIR

COHORTS = ["reference_genome", "is_complete", "is_hybrid", "lra_final_list"]
COHORT_TITLES = {
    "reference_genome": "reference_genome",
    "is_complete": "is_complete",
    "is_hybrid": "is_hybrid",
    "lra_final_list": "lra_final_list (all paired)",
}
SIDE_COLORS = {
    "lra_all": "#2ca02c",  # green — every LRA sample in the cohort (paired + unpaired)
    "lra": "#1f77b4",      # blue  — paired LRA only
    "sr": "#d62728",       # red   — paired SR partners
}
SIDE_LABELS = {
    "lra_all": "LRA-all",
    "lra": "LRA-paired",
    "sr": "SR-paired",
}
SIZE_BIN_CUTS_KB = (2, 20, 80)


def main() -> int:
    """CLI entry — read the lengths TSV, write the 4-panel histogram PNG."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_COMPARE_OUT_DIR / "standalone_viral_lengths.tsv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_COMPARE_OUT_DIR / "standalone_viral_lengths.png",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.input, sep="\t", dtype={"Sample": str, "contig": str, "length": int})
    print(f"loaded {len(df):,} rows from {args.input}")

    bins = np.logspace(np.log10(200), np.log10(2e5), 60)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=False)
    axes = axes.flatten()

    for ax, cohort in zip(axes, COHORTS, strict=False):
        # Draw LRA-all underneath (broadest distribution), then paired LRA and SR
        # on top — both as stepfilled with the same alpha so peak alignment
        # vs. lra_all is readable at a glance.
        for side in ("lra_all", "lra", "sr"):
            sub = df[(df["cohort"] == cohort) & (df["side"] == side)]
            if sub.empty:
                continue
            colour = SIDE_COLORS[side]
            ax.hist(
                sub["length"],
                bins=bins,
                histtype="stepfilled",
                alpha=0.40,
                color=colour,
                edgecolor=colour,
                linewidth=1.2,
                label=f"{SIDE_LABELS[side]}  (n={len(sub):,})",
            )
        for cut in SIZE_BIN_CUTS_KB:
            ax.axvline(cut * 1000, color="grey", linestyle="--", linewidth=0.7, alpha=0.5)
        ax.set_xscale("log")
        ax.set_title(COHORT_TITLES[cohort])
        ax.set_xlabel("standalone viral contig length (bp, log)")
        ax.set_ylabel("contigs")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, which="both", alpha=0.2)
        for kb in SIZE_BIN_CUTS_KB:
            ax.text(
                kb * 1000, ax.get_ylim()[1] * 0.98, f"{kb} kb",
                ha="center", va="top", fontsize=8, color="grey",
            )

    fig.suptitle(
        "Standalone viral contig length — LRA-all vs paired LRA vs paired SR, by cohort\n"
        "(geNomad whole-contig topology calls; dashed lines at 2/20/80 kb)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=150)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
