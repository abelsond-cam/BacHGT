#!/usr/bin/env python3
"""Per-CG virulence-BSC penetrance: complete genomes vs short-read MAGs (all CGs >= n).

Generalises the per-CG penetrance pass in ``compare_lra_to_sra`` (which
only writes tables for the top-N epidemic CGs + pooled rare + all_samples) to
every clonal group with at least ``--min-complete`` ``is_refseq=True`` genomes.
For each qualifying CG and each Kleborate virulence biosynthetic cluster
(Yersiniabactin, Colibactin, Aerobactin, Salmochelin, RmpADC, rmpA2) it records
the detection rate in the complete-genome and short-read subsets, plus the
two sample counts.

Output: long-format TSV (one row per (CG, BSC)) and, unless ``--no-plot``, a
scatter PNG of complete-vs-SR penetrance produced by
:mod:`bac_complete_genomes.per_clonal_group.cg_virulence_penetrance_scatter`.
"""

from __future__ import annotations

import argparse
from math import sqrt
from pathlib import Path

import pandas as pd

from bac_complete_genomes.compare_lra_to_sra import (
    DEFAULT_METADATA,
    DEFAULT_OUTPUT_DIR,
    KLEBORATE_VIRULENCE_LOCI,
    kleborate_column_to_presence,
)


def bsc_presence_features(meta: pd.DataFrame) -> dict[str, pd.Series]:
    """Return ``{bsc_name: 0/1 presence Series}`` for each Kleborate virulence locus.

    Mirrors the BSC-naming rule in ``build_feature_data``: ``{Lineage}_bsc`` when a
    lineage column exists (ybt/clb/iuc/iro/rmp), otherwise ``{locus}_bsc`` on the
    sole allele (rmpA2).
    """
    out: dict[str, pd.Series] = {}
    for locus, info in KLEBORATE_VIRULENCE_LOCI.items():
        lineage = info.get("lineage")
        if lineage and lineage in meta.columns:
            out[f"{lineage}_bsc"] = kleborate_column_to_presence(meta[lineage])
            continue
        allele = info["alleles"][0]
        if allele in meta.columns:
            out[f"{locus}_bsc"] = kleborate_column_to_presence(meta[allele])
    return out


def wilson_ci(count: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval (default 95%) for a binomial proportion ``count / n``.

    Returns ``(nan, nan)`` if ``n == 0``. Bounds are clipped to ``[0, 1]``.
    """
    if n == 0:
        return float("nan"), float("nan")
    p = count / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def per_cg_bsc_penetrance(
    meta: pd.DataFrame,
    bsc_features: dict[str, pd.Series],
    *,
    cg_col: str = "Clonal group",
    is_refseq_col: str = "is_refseq",
    min_complete: int = 10,
) -> pd.DataFrame:
    """Long-format penetrance table for every CG with ``n_complete >= min_complete``.

    Columns: ``clonal_group, bsc, n_complete, n_sr, complete_count, sr_count,
    complete_penetrance, sr_penetrance, complete_ci_low, complete_ci_high,
    sr_ci_low, sr_ci_high``. CIs are Wilson 95%. SR fields are NaN when the CG
    has no short-read samples.
    """
    df = meta.dropna(subset=[cg_col]).copy()
    df["_cg_str"] = df[cg_col].astype(str)
    is_refseq = df[is_refseq_col].astype(bool)

    rows: list[dict] = []
    for cg, sub in df.groupby("_cg_str", sort=False):
        sub_refseq = is_refseq.loc[sub.index]
        n_complete = int(sub_refseq.sum())
        if n_complete < min_complete:
            continue
        n_sr = int(len(sub) - n_complete)
        for bsc, series in bsc_features.items():
            vals = series.loc[sub.index]
            c_count = int(vals[sub_refseq].sum()) if n_complete > 0 else 0
            s_count = int(vals[~sub_refseq].sum()) if n_sr > 0 else 0
            c_mean = c_count / n_complete if n_complete > 0 else float("nan")
            s_mean = s_count / n_sr if n_sr > 0 else float("nan")
            c_lo, c_hi = wilson_ci(c_count, n_complete)
            s_lo, s_hi = wilson_ci(s_count, n_sr)
            rows.append(
                {
                    "clonal_group": cg,
                    "bsc": bsc,
                    "n_complete": n_complete,
                    "n_sr": n_sr,
                    "complete_count": c_count,
                    "sr_count": s_count,
                    "complete_penetrance": c_mean,
                    "sr_penetrance": s_mean,
                    "complete_ci_low": c_lo,
                    "complete_ci_high": c_hi,
                    "sr_ci_low": s_lo,
                    "sr_ci_high": s_hi,
                }
            )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["n_complete", "clonal_group", "bsc"], ascending=[False, True, True], kind="mergesort")
        out = out.reset_index(drop=True)
    return out


def main() -> None:
    """CLI entry point: compute the per-CG BSC penetrance table and (optionally) plot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "penetrance_all_cgs",
        help="Output directory for TSV + plot.",
    )
    parser.add_argument(
        "--min-complete",
        type=int,
        default=20,
        help="Minimum is_refseq=True genomes per CG (default: 20).",
    )
    parser.add_argument("--no-plot", action="store_true", help="Skip the scatter plot.")
    parser.add_argument(
        "--low-region-cutoff",
        type=float,
        default=0.25,
        help="Penetrance below which a point is subject to the CI filter (default: 0.25).",
    )
    parser.add_argument(
        "--max-ci-excess",
        type=float,
        default=0.10,
        help="In the low region, drop points whose Wilson 95%% upper CI extends more than "
        "this far above the point estimate (default: 0.10). Set to 1.0 to disable.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading metadata from {args.metadata}")
    meta = pd.read_csv(args.metadata, sep="\t", low_memory=False)
    required = {"Sample", "Clonal group", "is_refseq"}
    missing = required - set(meta.columns)
    if missing:
        raise KeyError(f"Metadata missing required columns: {sorted(missing)}")
    print(f"Loaded {len(meta)} samples")

    bsc_features = bsc_presence_features(meta)
    print(f"Built {len(bsc_features)} BSC features: {list(bsc_features)}")

    df = per_cg_bsc_penetrance(meta, bsc_features, min_complete=args.min_complete)
    n_cgs = df["clonal_group"].nunique() if not df.empty else 0
    print(f"CGs with n_complete >= {args.min_complete}: {n_cgs} ({len(df)} (CG, BSC) rows)")

    stem = f"cg_virulence_penetrance_min{args.min_complete}"
    tsv_path = args.output_dir / f"{stem}.tsv"
    df.to_csv(tsv_path, sep="\t", index=False)
    print(f"Wrote {tsv_path}")

    if args.no_plot or df.empty:
        return

    from bac_complete_genomes.per_clonal_group.cg_virulence_penetrance_scatter import plot_cg_virulence_penetrance

    png_path = args.output_dir / f"{stem}.png"
    plot_cg_virulence_penetrance(
        df,
        save_path=png_path,
        min_complete=args.min_complete,
        low_region_cutoff=args.low_region_cutoff,
        max_ci_excess=args.max_ci_excess,
    )
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
