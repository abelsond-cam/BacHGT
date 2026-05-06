#!/usr/bin/env python3
"""GPA reference genome granularity analysis + run inventory.

Quantifies how much shared-gene coverage improves at different levels of
reference-genome assignment granularity:

  Level d (coarsest): mgh78578 distance — single global baseline
  Level c: best RefSeq for whole sublineage
  Level b: best RefSeq for the clonal group
  Level a (finest): per-sample nearest RefSeq (new computation from .Rtab)

Produces: granularity_table.tsv, granularity_summary.tsv, run_inventory.md,
and delegates lollipop plotting to bacotype.pl.granularity_lollipop.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

from bacotype.tl.gpa_distances_cluster_metrics import jaccard_to_shared
from bacotype.tl.gpa_distances_combined import (
    DEFAULT_GROUP_LEVEL,
    load_and_concat_detail_tsvs,
)
from bacotype.tl.gpa_distances_single_group import PANAROO_RUN_ROOT


def _tslog(message: str) -> None:
    """Print timestamped log line."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {message}", flush=True)


def generate_run_inventory(
    combined_df: pd.DataFrame,
    out_path: str,
) -> None:
    """Write run inventory markdown from combined detail TSV."""
    _tslog("Generating run inventory markdown...")

    ws = combined_df[combined_df["group_level"] == "whole_set"].copy()
    cg_rows = combined_df[
        (combined_df["group_level"] == "clonal_group")
        & (combined_df["group_label"] != "other")
    ].copy()

    # Build markdown
    lines = [
        "# Panaroo Run Inventory",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"**Total runs:** {len(ws)}",
        f"**Total samples:** {ws['n_samples'].sum():,}",
        f"**Total RefSeq genomes:** {ws.get('n_refseq_genomes', ws.get('ref_min_mean_jaccard', pd.Series([0]))).sum() if 'n_refseq_genomes' in ws.columns else '?':,}",
        "",
        "## Runs",
        "",
        "| Run | Samples | Sublineages | CGs (≥250) | Classification |",
        "|-----|---------|-------------|-----------|-----------------|",
    ]

    for _, row in ws.iterrows():
        run = row["directory_leaf"]
        samples = int(row["n_samples"])
        sls = int(row.get("n_unique_sublineages", 0))
        # Count CGs with >250 samples for this run
        cgs_major = len(
            cg_rows[cg_rows["directory_leaf"] == run]["group_label"].unique()
        )
        classification = str(row.get("run_classification", "unknown"))

        lines.append(
            f"| {run} | {samples} | {sls} | {cgs_major} | {classification} |"
        )

    markdown = "\n".join(lines)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(markdown)

    _tslog(f"Wrote inventory: {out_path}")


def compute_per_sample_min_jaccard(
    run_dir: str,
    metadata_df: pd.DataFrame,
) -> pd.Series | None:
    """
    Compute per-sample min Jaccard to any is_refseq genome per CG.

    Returns Series {cg_name: shared_genes_level_a}. Fully vectorized: cdist
    gives (n_refseq, n_kpsc) distance matrix; .min(axis=0) gives per-sample min;
    pandas groupby aggregates to CG level.

    Returns None if run not found or failed.
    """
    try:
        rtab_path = os.path.join(run_dir, "gene_presence_absence.Rtab")
        if not os.path.isfile(rtab_path):
            _tslog(f"WARNING: Rtab not found: {rtab_path}")
            return None

        # Load .Rtab: (n_genes, n_samples), index=gene_names, columns=sample_ids
        gpa = pd.read_csv(rtab_path, sep="\t", index_col=0)

        # Align metadata to .Rtab columns; detect sample column
        sample_id_col = None
        for col in ["Sample", "sample_id", "Sample ID", "SampleID", "sampleid"]:
            if col in metadata_df.columns:
                sample_id_col = col
                break
        if not sample_id_col:
            _tslog(f"WARNING: No sample column found in metadata; trying first column")
            sample_id_col = metadata_df.columns[0]

        meta = metadata_df.set_index(sample_id_col).reindex(gpa.columns)
        is_refseq = meta["is_refseq"].fillna(False).astype(bool).values
        is_kpsc = meta["kpsc_final_list"].fillna(False).astype(bool).values

        if not is_refseq.any():
            _tslog(
                f"WARNING: No is_refseq samples in {run_dir} (pipeline guarantees ≥1)"
            )
            return None

        # Binarize and transpose → (n_samples, n_genes)
        X = (gpa.values > 0).astype(np.uint8).T

        kpsc_only = is_kpsc & ~is_refseq
        X_refseq = X[is_refseq]  # (n_refseq, n_genes)
        X_kpsc = X[kpsc_only]  # (n_kpsc,   n_genes)

        if len(X_kpsc) == 0:
            _tslog(f"WARNING: No KPSC non-refseq samples in {run_dir}")
            return None

        # Fully vectorized: cdist → (n_refseq, n_kpsc)
        dist = cdist(X_refseq, X_kpsc, metric="jaccard")
        per_sample_min = dist.min(axis=0)  # (n_kpsc,)

        mean_features = X_kpsc.sum(axis=1).mean()  # scalar

        # Vectorized groupby: mean per-sample min Jaccard per CG
        kpsc_sample_ids = gpa.columns[kpsc_only]
        # Try both underscore and space variants
        cg_col = "Clonal_group" if "Clonal_group" in meta.columns else "Clonal group"
        cg_labels = meta.loc[kpsc_sample_ids, cg_col]
        min_j_series = pd.Series(per_sample_min, index=kpsc_sample_ids)
        cg_mean_min_j = min_j_series.groupby(cg_labels.values).mean()

        # Convert to shared genes
        result = cg_mean_min_j.apply(lambda j: jaccard_to_shared(j, mean_features))
        return result

    except Exception as e:
        _tslog(f"ERROR computing level_a for {run_dir}: {e}")
        return None


def compute_granularity_table(
    combined_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    data_dir: str,
    min_samples_per_cg: int = 100,
    workers: int = 1,
) -> pd.DataFrame:
    """
    Compute granularity levels b, c, d from detail TSV and level a from .Rtab files.

    Returns DataFrame with one row per target CG (n_samples >= min_samples_per_cg,
    single CG, Klebsiella pneumoniae, group_label != "other").
    """
    _tslog("=== Computing granularity table ===")

    # Step 1: Extract levels b, c, d from detail TSV
    _tslog("Step 1: Extracting levels b, c, d from combined detail TSV...")

    # Compute global mgh78578 baseline
    ws_all = combined_df[combined_df["group_level"] == "whole_set"]
    weights = ws_all["n_samples"]
    values = ws_all["global_ref_mean_shared_genes"]
    global_mgh_shared_genes = (weights * values).sum() / weights.sum()
    _tslog(f"Global mgh78578 baseline (level d): {global_mgh_shared_genes:.2f}")

    # Filter target CGs
    target_rows = combined_df[
        (combined_df["group_level"] == "clonal_group")
        & (combined_df["group_label"] != "other")
        & (combined_df["n_unique_clonal_groups"] == 1)
        & (combined_df["n_samples"] >= min_samples_per_cg)
        & (combined_df["species"] == "Klebsiella pneumoniae")
    ].copy()

    _tslog(f"Target CGs: {len(target_rows)}")

    if target_rows.empty:
        _tslog("No target CGs found. Returning empty DataFrame.")
        return pd.DataFrame()

    # Join to whole_set rows for sublineage-level data
    ws_for_cgs = ws_all[
        ws_all["directory_leaf"].isin(target_rows["directory_leaf"].unique())
    ][
        ["directory_leaf", "ref_min_shared_genes", "n_refseq_genomes"]
    ].rename(
        columns={
            "ref_min_shared_genes": "ref_min_shared_genes_sublineage",
            "n_refseq_genomes": "n_refseq_genomes_sublineage",
        }
    )

    result = target_rows.merge(
        ws_for_cgs, on="directory_leaf", how="left"
    ).copy()

    # Compute levels b, c, d
    result["shared_genes_d"] = global_mgh_shared_genes
    result["fallback_c"] = False
    result["fallback_b"] = False

    # Level c: use whole_set ref_min_shared_genes if available
    has_refseq_c = result["n_refseq_genomes_sublineage"] > 0
    result.loc[has_refseq_c, "shared_genes_c"] = result.loc[
        has_refseq_c, "ref_min_shared_genes_sublineage"
    ]
    result.loc[~has_refseq_c, "shared_genes_c"] = global_mgh_shared_genes
    result.loc[~has_refseq_c, "fallback_c"] = True

    # Level b: use CG ref_min_shared_genes if available; else fall back to c
    has_refseq_b = result["n_refseq_genomes"] > 0
    result.loc[has_refseq_b, "shared_genes_b"] = result.loc[
        has_refseq_b, "ref_min_shared_genes"
    ]
    result.loc[~has_refseq_b, "shared_genes_b"] = result.loc[
        ~has_refseq_b, "shared_genes_c"
    ]
    result.loc[~has_refseq_b, "fallback_b"] = True

    # Step 2: Compute level a from .Rtab files
    _tslog("Step 2: Computing level a from .Rtab files...")

    unique_runs = result["directory_leaf"].unique()
    run_dirs = [os.path.join(data_dir, run) for run in unique_runs]

    level_a_results = {}
    if workers > 1:
        _tslog(f"Processing {len(run_dirs)} runs in parallel (workers={workers})...")
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(compute_per_sample_min_jaccard, rd, metadata_df): rd
                for rd in run_dirs
            }
            for future in futures:
                rd = futures[future]
                try:
                    res = future.result(timeout=300)
                    if res is not None:
                        level_a_results[os.path.basename(rd)] = res
                except Exception as e:
                    _tslog(f"ERROR: {e}")
    else:
        for rd in run_dirs:
            res = compute_per_sample_min_jaccard(rd, metadata_df)
            if res is not None:
                level_a_results[os.path.basename(rd)] = res

    _tslog(f"Computed level a for {len(level_a_results)} runs")

    # Lookup level a for each target CG
    result["shared_genes_a"] = np.nan
    for idx, row in result.iterrows():
        run_name = row["directory_leaf"]
        cg_name = row["group_label"]
        if run_name in level_a_results and cg_name in level_a_results[run_name]:
            result.at[idx, "shared_genes_a"] = level_a_results[run_name][cg_name]
        else:
            if run_name not in level_a_results:
                _tslog(
                    f"WARNING: No level_a computed for run {run_name}; "
                    f"CG {cg_name} will have NaN"
                )
            else:
                _tslog(
                    f"WARNING: CG {cg_name} in {run_name} not in level_a results"
                )

    # Step 3: Compute gain columns
    _tslog("Step 3: Computing gain columns...")

    result["gain_d_to_c"] = result["shared_genes_c"] - result["shared_genes_d"]
    result["gain_c_to_b"] = result["shared_genes_b"] - result["shared_genes_c"]
    result["gain_b_to_a"] = result["shared_genes_a"] - result["shared_genes_b"]

    result["pct_gain_d_to_c"] = 100 * result["gain_d_to_c"] / (
        result["shared_genes_d"] + 1e-9
    )
    result["pct_gain_c_to_b"] = 100 * result["gain_c_to_b"] / (
        result["shared_genes_c"] + 1e-9
    )
    result["pct_gain_b_to_a"] = 100 * result["gain_b_to_a"] / (
        result["shared_genes_b"] + 1e-9
    )

    # Select output columns
    output_cols = [
        "strain",
        "Sublineage",
        "directory_leaf",
        "n_samples",
        "n_refseq_genomes",
        "n_refseq_genomes_sublineage",
        "shared_genes_d",
        "shared_genes_c",
        "shared_genes_b",
        "shared_genes_a",
        "fallback_c",
        "fallback_b",
        "gain_d_to_c",
        "gain_c_to_b",
        "gain_b_to_a",
        "pct_gain_d_to_c",
        "pct_gain_c_to_b",
        "pct_gain_b_to_a",
    ]

    result = result[[c for c in output_cols if c in result.columns]]

    _tslog(f"Granularity table: {len(result)} rows")
    return result


def compute_summary_stats(granularity_df: pd.DataFrame) -> dict[str, float]:
    """Compute aggregate summary statistics."""
    stats = {}

    for level in ["d", "c", "b", "a"]:
        col = f"shared_genes_{level}"
        if col in granularity_df.columns:
            valid = granularity_df[col].dropna()
            if not valid.empty:
                stats[f"mean_{level}"] = valid.mean()
                stats[f"median_{level}"] = valid.median()
                stats[f"std_{level}"] = valid.std()
                stats[f"min_{level}"] = valid.min()
                stats[f"max_{level}"] = valid.max()

    # % where b > c
    if "shared_genes_b" in granularity_df.columns:
        pct_b_gt_c = (
            (granularity_df["shared_genes_b"] > granularity_df["shared_genes_c"]).sum()
            / len(granularity_df)
            * 100
        )
        stats["pct_b_gt_c"] = pct_b_gt_c

    # % where a > b
    if "shared_genes_a" in granularity_df.columns:
        valid_a = granularity_df[granularity_df["shared_genes_a"].notna()]
        if not valid_a.empty:
            pct_a_gt_b = (
                (valid_a["shared_genes_a"] > valid_a["shared_genes_b"]).sum()
                / len(valid_a)
                * 100
            )
            stats["pct_a_gt_b"] = pct_a_gt_b

    return stats


def main(argv: Iterable[str] | None = None) -> int:
    """Parse args and run inventory/granularity analysis."""
    parser = argparse.ArgumentParser(
        description="GPA reference genome granularity analysis + run inventory."
    )
    parser.add_argument(
        "--data-dir",
        default=PANAROO_RUN_ROOT,
        help=f"Panaroo run root (default: {PANAROO_RUN_ROOT})",
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="Metadata TSV with sample_id, is_refseq, kpsc_final_list, Clonal_group",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: <data-dir>/../granularity_to_ref)",
    )
    parser.add_argument(
        "--mode",
        choices=("inventory", "granularity", "both"),
        default="both",
        help="Run mode (default: both)",
    )
    parser.add_argument(
        "--min-samples-per-cg",
        type=int,
        default=100,
        help="Min n_samples per target CG (default 100)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel workers for .Rtab processing (default 1)",
    )
    parser.add_argument(
        "--test-n-runs",
        type=int,
        default=None,
        help="Limit to N runs for testing",
    )
    parser.add_argument(
        "--recompile",
        action="store_true",
        help="Force rebuild of combined detail TSV",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.out_dir is None:
        # Default to granularity_to_ref directory (sibling of data_dir)
        args.out_dir = os.path.join(os.path.dirname(args.data_dir), "granularity_to_ref")

    os.makedirs(args.out_dir, exist_ok=True)
    _tslog("=== gpa_reference_granularity.py start ===")
    _tslog(f"Mode: {args.mode}")
    _tslog(f"Data dir: {args.data_dir}")
    _tslog(f"Out dir: {args.out_dir}")

    # Load combined detail TSV
    _tslog("Loading combined detail TSV...")
    combined_df = load_and_concat_detail_tsvs(
        args.data_dir, write_tsv=False, recompile=args.recompile
    )

    if args.test_n_runs:
        combined_df = combined_df[
            combined_df["directory_leaf"].isin(
                combined_df["directory_leaf"].unique()[: args.test_n_runs]
            )
        ]
        _tslog(f"Test mode: limited to {args.test_n_runs} runs")

    # Inventory mode
    if args.mode in ("inventory", "both"):
        inv_path = os.path.join(args.out_dir, "run_inventory.md")
        generate_run_inventory(combined_df, inv_path)

    # Granularity mode
    if args.mode in ("granularity", "both"):
        # Load metadata
        _tslog(f"Loading metadata: {args.metadata}")
        metadata_df = pd.read_csv(args.metadata, sep="\t")

        # Compute granularity table
        granularity_df = compute_granularity_table(
            combined_df,
            metadata_df,
            args.data_dir,
            min_samples_per_cg=args.min_samples_per_cg,
            workers=args.workers,
        )

        if not granularity_df.empty:
            # Write table
            table_path = os.path.join(args.out_dir, "granularity_table.tsv")
            granularity_df.to_csv(table_path, sep="\t", index=False)
            _tslog(f"Wrote granularity table: {table_path}")

            # Compute and write summary
            summary_stats = compute_summary_stats(granularity_df)
            summary_df = pd.DataFrame(
                [
                    {"metric": k, "value": v}
                    for k, v in sorted(summary_stats.items())
                ]
            )
            summary_path = os.path.join(args.out_dir, "granularity_summary.tsv")
            summary_df.to_csv(summary_path, sep="\t", index=False)
            _tslog(f"Wrote summary: {summary_path}")

            # Call lollipop plot
            try:
                from bacotype.pl.granularity_lollipop import plot_granularity_lollipop

                _tslog("Generating lollipop plot...")
                plot_granularity_lollipop(granularity_df, args.out_dir)
            except ImportError:
                _tslog(
                    "WARNING: granularity_lollipop module not found; "
                    "skipping plot generation"
                )
        else:
            _tslog("No target CGs found; skipping granularity outputs")

    _tslog("=== gpa_reference_granularity.py end ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
