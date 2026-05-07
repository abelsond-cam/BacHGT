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

Row types in the output table:
  kp_epidemic — KP major clonal groups (≥ min_samples_per_cg, single CG, KP)
  kp_rare     — KP rare-lineage batch runs (kp_rare_sublineage_batch_*)
  kp_species  — Non-KP Klebsiella species runs (species_*)
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


def compute_levels_abc_from_rtab(
    run_dir: str,
    metadata_df: pd.DataFrame,
    target_cgs: list[str] | None = None,
    whole_run: bool = False,
    use_kpsc_filter: bool = True,
) -> dict[str, dict[str, float]] | None:
    """
    Compute levels a, b, c from .Rtab using exact dot-product shared gene counts.

    All three levels use the same computation:
      shared_matrix[i, j] = |genes(ref_i) ∩ genes(sample_j)|  (BLAS SGEMM, float32)

    This guarantees level_c ≤ level_b ≤ level_a for every CG because each step
    gives each sample more degrees of freedom to find a better reference.

    Level c: mean shared genes between CG samples and the ONE BEST REFERENCE
             for the WHOLE RUN (reference chosen by maximising mean over all run samples)
    Level b: mean shared genes between CG samples and the ONE BEST REFERENCE
             for the SPECIFIC CG (reference chosen by maximising mean over CG samples)
    Level a: mean of PER-SAMPLE max shared genes (each sample picks its own best)

    Parameters
    ----------
    run_dir
        Path to Panaroo run folder containing gene_presence_absence.Rtab.
    metadata_df
        Full metadata DataFrame.
    target_cgs
        CG names to compute results for (None = all CGs found in run).
    whole_run
        If True, skip per-CG grouping and return a single whole-run mean
        (used for rare-lineage batches and non-KP species runs).
    use_kpsc_filter
        If True, restrict query samples to kpsc_final_list == True.
        Set False for non-KP species runs where kpsc_final_list may be False.

    Returns
    -------
    dict {cg_name: {"level_a": float, "level_b": float, "level_c": float}}
    or {"__whole_run__": {"level_a": float, "level_c": float}} when whole_run=True,
    or None if the run cannot be processed.
    """
    try:
        rtab_path = os.path.join(run_dir, "gene_presence_absence.Rtab")
        if not os.path.isfile(rtab_path):
            _tslog(f"WARNING: Rtab not found: {rtab_path}")
            return None

        # Load .Rtab: (n_genes, n_samples)
        gpa = pd.read_csv(rtab_path, sep="\t", index_col=0)

        # Detect sample ID column
        sample_id_col = None
        for col in ["Sample", "sample_id", "Sample ID", "SampleID", "sampleid"]:
            if col in metadata_df.columns:
                sample_id_col = col
                break
        if not sample_id_col:
            sample_id_col = metadata_df.columns[0]

        meta = metadata_df.set_index(sample_id_col).reindex(gpa.columns)
        is_refseq = meta["is_refseq"].fillna(False).astype(bool).values

        if use_kpsc_filter:
            is_query = meta["kpsc_final_list"].fillna(False).astype(bool).values & ~is_refseq
        else:
            is_query = ~is_refseq

        if not is_refseq.any():
            _tslog(f"WARNING: No RefSeq samples in {run_dir}")
            return None
        if not is_query.any():
            _tslog(f"WARNING: No query samples in {run_dir}")
            return None

        # Binarize: (n_samples, n_genes)
        X = (gpa.values > 0).astype(np.uint8).T
        X_refseq = X[is_refseq]  # (n_refseq, n_genes)
        X_query = X[is_query]    # (n_query, n_genes)

        # Single BLAS SGEMM call — fully vectorised, no Python loops.
        # float32 preserves 0/1 binary values exactly.
        shared = X_refseq.astype(np.float32) @ X_query.astype(np.float32).T  # (n_refseq, n_query)

        # Level c reference: best single ref maximising mean shared genes over ALL query samples
        best_run_ref = int(shared.mean(axis=1).argmax())
        per_sample_c = shared[best_run_ref, :]  # (n_query,)

        # Level a: per-sample best reference
        per_sample_a = shared.max(axis=0)  # (n_query,)

        if whole_run:
            return {
                "__whole_run__": {
                    "level_a": float(per_sample_a.mean()),
                    "level_c": float(per_sample_c.mean()),
                }
            }

        # Per-CG: levels a, b, c
        query_ids = gpa.columns[is_query]
        cg_col = "Clonal_group" if "Clonal_group" in meta.columns else "Clonal group"
        if cg_col not in meta.columns:
            # No CG column: return whole-run mean for all requested CGs
            whole_a = float(per_sample_a.mean())
            whole_c = float(per_sample_c.mean())
            return {cg: {"level_a": whole_a, "level_b": whole_c, "level_c": whole_c}
                    for cg in (target_cgs or [])}

        cg_labels = meta.loc[query_ids, cg_col].values
        results: dict[str, dict[str, float]] = {}

        for cg_name in (target_cgs if target_cgs is not None else list(pd.unique(cg_labels))):
            cg_mask = cg_labels == cg_name
            if not cg_mask.any():
                continue

            # Level b reference: best single ref maximising mean shared genes over CG samples
            best_cg_ref = int(shared[:, cg_mask].mean(axis=1).argmax())

            results[cg_name] = {
                "level_a": float(per_sample_a[cg_mask].mean()),
                "level_b": float(shared[best_cg_ref, cg_mask].mean()),
                "level_c": float(per_sample_c[cg_mask].mean()),
            }

        return results

    except Exception as e:
        _tslog(f"ERROR computing levels from .Rtab for {run_dir}: {e}")
        return None


def _build_whole_run_rows(
    ws_subset: pd.DataFrame,
    row_type: str,
    label_fn,
    global_mgh_shared_genes: float,
) -> pd.DataFrame:
    """Build per-run analysis rows for rare-batch or species whole-run entries."""
    rows = ws_subset.copy().reset_index(drop=True)
    rows["group_label"] = rows["directory_leaf"].apply(label_fn)
    rows["Sublineage"] = rows["group_label"]
    rows["row_type"] = row_type
    rows["n_refseq_genomes_sublineage"] = rows["n_refseq_genomes"]
    rows["ref_min_shared_genes_sublineage"] = rows["ref_min_shared_genes"]
    rows["shared_genes_e"] = global_mgh_shared_genes        # global weighted mean
    rows["shared_genes_d"] = rows["global_ref_mean_shared_genes"]  # per-run mgh78578
    rows["fallback_c"] = False
    rows["fallback_b"] = True  # no per-CG RefSeq; level b always equals level c

    has_refseq_c = rows["n_refseq_genomes_sublineage"] > 0
    rows.loc[has_refseq_c, "shared_genes_c"] = rows.loc[
        has_refseq_c, "ref_min_shared_genes_sublineage"
    ]
    rows.loc[~has_refseq_c, "shared_genes_c"] = rows.loc[~has_refseq_c, "shared_genes_d"]
    rows.loc[~has_refseq_c, "fallback_c"] = True
    rows["shared_genes_b"] = rows["shared_genes_c"]
    return rows


def compute_granularity_table(
    combined_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    data_dir: str,
    min_samples_per_cg: int = 100,
    workers: int = 1,
) -> pd.DataFrame:
    """
    Compute granularity levels b, c, d from detail TSV and level a from .Rtab files.

    Returns one row per:
      - KP epidemic clonal group (kp_epidemic)
      - KP rare-lineage batch run (kp_rare)
      - Non-KP Klebsiella species run (kp_species)
    """
    _tslog("=== Computing granularity table ===")

    # Step 1: Extract levels b, c, d from detail TSV
    _tslog("Step 1: Extracting levels b, c, d from combined detail TSV...")

    ws_all = combined_df[combined_df["group_level"] == "whole_set"].copy()
    global_mgh_shared_genes = (
        (ws_all["n_samples"] * ws_all["global_ref_mean_shared_genes"]).sum()
        / ws_all["n_samples"].sum()
    )
    _tslog(f"Global mgh78578 baseline (level e): {global_mgh_shared_genes:.2f}")

    # --- 1a. KP epidemic clonal groups ---
    target_rows = combined_df[
        (combined_df["group_level"] == "clonal_group")
        & (combined_df["group_label"] != "other")
        & (combined_df["n_unique_clonal_groups"] == 1)
        & (combined_df["n_samples"] >= min_samples_per_cg)
        & (combined_df["species"] == "Klebsiella pneumoniae")
    ].copy()
    target_rows["row_type"] = "kp_epidemic"
    _tslog(f"Target epidemic CGs: {len(target_rows)}")

    result_epidemic = pd.DataFrame()
    if not target_rows.empty:
        ws_for_cgs = ws_all[
            ws_all["directory_leaf"].isin(target_rows["directory_leaf"].unique())
        ][["directory_leaf", "ref_min_shared_genes", "n_refseq_genomes",
           "global_ref_mean_shared_genes"]].rename(
            columns={
                "ref_min_shared_genes": "ref_min_shared_genes_sublineage",
                "n_refseq_genomes": "n_refseq_genomes_sublineage",
                "global_ref_mean_shared_genes": "shared_genes_d",
            }
        )
        result_epidemic = target_rows.merge(ws_for_cgs, on="directory_leaf", how="left")
        result_epidemic["shared_genes_e"] = global_mgh_shared_genes  # global weighted mean
        result_epidemic["fallback_c"] = False
        result_epidemic["fallback_b"] = False

        has_refseq_c = result_epidemic["n_refseq_genomes_sublineage"] > 0
        result_epidemic.loc[has_refseq_c, "shared_genes_c"] = result_epidemic.loc[
            has_refseq_c, "ref_min_shared_genes_sublineage"
        ]
        result_epidemic.loc[~has_refseq_c, "shared_genes_c"] = result_epidemic.loc[
            ~has_refseq_c, "shared_genes_d"
        ]
        result_epidemic.loc[~has_refseq_c, "fallback_c"] = True

        has_refseq_b = result_epidemic["n_refseq_genomes"] > 0
        result_epidemic.loc[has_refseq_b, "shared_genes_b"] = result_epidemic.loc[
            has_refseq_b, "ref_min_shared_genes"
        ]
        result_epidemic.loc[~has_refseq_b, "shared_genes_b"] = result_epidemic.loc[
            ~has_refseq_b, "shared_genes_c"
        ]
        result_epidemic.loc[~has_refseq_b, "fallback_b"] = True

    # --- 1b. KP rare lineage batch runs ---
    rare_ws = ws_all[ws_all["directory_leaf"].str.startswith("kp_rare_sublineage_batch")]
    result_rare = pd.DataFrame()
    if not rare_ws.empty:
        result_rare = _build_whole_run_rows(
            rare_ws,
            "kp_rare",
            lambda d: d.replace("kp_rare_sublineage_batch_", "rare_batch_"),
            global_mgh_shared_genes,
        )
        _tslog(f"Rare lineage batch runs: {len(result_rare)}")

    # --- 1c. Non-KP Klebsiella species runs ---
    species_ws = ws_all[ws_all["directory_leaf"].str.startswith("species_")]
    result_species = pd.DataFrame()
    if not species_ws.empty:
        def _species_name(d: str) -> str:
            return (
                d.replace("species_Klebsiella_", "K. ")
                .replace("_subsp._", " ssp. ")
                .replace("_", " ")
            )
        result_species = _build_whole_run_rows(
            species_ws, "kp_species", _species_name, global_mgh_shared_genes
        )
        _tslog(f"Non-KP species runs: {len(result_species)}")

    # Concatenate all row types
    frames = [f for f in [result_epidemic, result_rare, result_species] if len(f) > 0]
    if not frames:
        _tslog("No target rows found. Returning empty DataFrame.")
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)

    # Step 2: Compute levels a, b, c from .Rtab files (exact dot product, guarantees monotonicity)
    _tslog("Step 2: Computing levels a/b/c from .Rtab files...")

    # Per-run compute parameters: {run_dir: {target_cgs, whole_run, use_kpsc_filter}}
    run_params: dict[str, dict] = {}
    for run in (result_epidemic["directory_leaf"].unique() if len(result_epidemic) > 0 else []):
        cg_list = result_epidemic[result_epidemic["directory_leaf"] == run]["group_label"].tolist()
        run_params[os.path.join(data_dir, run)] = {
            "target_cgs": cg_list,
            "whole_run": False,
            "use_kpsc_filter": True,
        }
    for run in (result_rare["directory_leaf"].unique() if len(result_rare) > 0 else []):
        run_params[os.path.join(data_dir, run)] = {
            "target_cgs": None,
            "whole_run": True,
            "use_kpsc_filter": True,
        }
    for run in (result_species["directory_leaf"].unique() if len(result_species) > 0 else []):
        # Non-KP species: all non-RefSeq samples (kpsc_final_list may be False)
        run_params[os.path.join(data_dir, run)] = {
            "target_cgs": None,
            "whole_run": True,
            "use_kpsc_filter": False,
        }

    run_dirs = list(run_params.keys())
    level_a_results: dict[str, dict[str, dict[str, float]]] = {}

    if workers > 1:
        _tslog(f"Processing {len(run_dirs)} runs in parallel (workers={workers})...")
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    compute_levels_abc_from_rtab,
                    rd,
                    metadata_df,
                    run_params[rd]["target_cgs"],
                    run_params[rd]["whole_run"],
                    run_params[rd]["use_kpsc_filter"],
                ): rd
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
            res = compute_levels_abc_from_rtab(
                rd,
                metadata_df,
                run_params[rd]["target_cgs"],
                run_params[rd]["whole_run"],
                run_params[rd]["use_kpsc_filter"],
            )
            if res is not None:
                level_a_results[os.path.basename(rd)] = res

    _tslog(f"Computed levels a/b/c from .Rtab for {len(level_a_results)} runs")

    # Populate levels a, b, c from .Rtab results; fall back to detail-TSV values on failure
    result["shared_genes_a"] = np.nan
    for idx, row in result.iterrows():
        run_name = row["directory_leaf"]
        lookup_key = (
            "__whole_run__"
            if row["row_type"] in ("kp_rare", "kp_species")
            else row["group_label"]
        )
        if run_name in level_a_results and lookup_key in level_a_results[run_name]:
            rtab_res = level_a_results[run_name][lookup_key]
            result.at[idx, "shared_genes_a"] = rtab_res["level_a"]
            result.at[idx, "shared_genes_c"] = rtab_res["level_c"]
            result.at[idx, "fallback_c"] = False
            if "level_b" in rtab_res:
                result.at[idx, "shared_genes_b"] = rtab_res["level_b"]
                result.at[idx, "fallback_b"] = False
            else:
                # whole_run mode: no per-CG reference → level_b = level_c
                result.at[idx, "shared_genes_b"] = rtab_res["level_c"]
                # fallback_b stays True (already set by _build_whole_run_rows)
        else:
            if run_name not in level_a_results:
                _tslog(f"WARNING: No .Rtab results for run {run_name}")
            else:
                _tslog(f"WARNING: key '{lookup_key}' not in .Rtab results for {run_name}")

    # Step 3: Compute gain columns
    _tslog("Step 3: Computing gain columns...")
    result["gain_e_to_d"] = result["shared_genes_d"] - result["shared_genes_e"]
    result["gain_d_to_c"] = result["shared_genes_c"] - result["shared_genes_d"]
    result["gain_c_to_b"] = result["shared_genes_b"] - result["shared_genes_c"]
    result["gain_b_to_a"] = result["shared_genes_a"] - result["shared_genes_b"]
    result["pct_gain_e_to_d"] = 100 * result["gain_e_to_d"] / (result["shared_genes_e"] + 1e-9)
    result["pct_gain_d_to_c"] = 100 * result["gain_d_to_c"] / (result["shared_genes_d"] + 1e-9)
    result["pct_gain_c_to_b"] = 100 * result["gain_c_to_b"] / (result["shared_genes_c"] + 1e-9)
    result["pct_gain_b_to_a"] = 100 * result["gain_b_to_a"] / (result["shared_genes_b"] + 1e-9)

    # Step 4: Aggregate split-run parts → one row per unique strain
    # (Only epidemic CGs can span multiple parts; rare/species are always single-run)
    _tslog("Step 4: Aggregating split-run parts...")
    pre_agg_rows = len(result)

    def _agg_cg(grp: pd.DataFrame) -> pd.Series:
        """Collapse multiple run-parts for the same strain into one weighted row."""
        w = grp["n_samples"]
        total = w.sum()
        out: dict = {}
        out["n_samples"] = total
        out["n_parts"] = len(grp)
        out["directory_leaf"] = ";".join(sorted(grp["directory_leaf"].unique()))
        for col in ["n_refseq_genomes", "n_refseq_genomes_sublineage"]:
            if col in grp.columns:
                out[col] = (grp[col] * w).sum() / total
        out["shared_genes_e"] = grp["shared_genes_e"].iloc[0]  # global constant, same in all parts
        for col in ["shared_genes_d", "shared_genes_c", "shared_genes_b", "shared_genes_a"]:
            valid = grp[col].notna()
            out[col] = (
                (grp.loc[valid, col] * w[valid]).sum() / w[valid].sum()
                if valid.any()
                else float("nan")
            )
        out["fallback_c"] = grp["fallback_c"].any()
        out["fallback_b"] = grp["fallback_b"].any()
        out["row_type"] = grp["row_type"].iloc[0]
        return pd.Series(out)

    result = (
        result.groupby(["group_label", "Sublineage"], sort=False)
        .apply(_agg_cg, include_groups=False)
        .reset_index()
        .rename(columns={"group_label": "strain"})
    )

    # Recompute gain columns from aggregated values
    result["gain_e_to_d"] = result["shared_genes_d"] - result["shared_genes_e"]
    result["gain_d_to_c"] = result["shared_genes_c"] - result["shared_genes_d"]
    result["gain_c_to_b"] = result["shared_genes_b"] - result["shared_genes_c"]
    result["gain_b_to_a"] = result["shared_genes_a"] - result["shared_genes_b"]
    result["pct_gain_e_to_d"] = 100 * result["gain_e_to_d"] / (result["shared_genes_e"] + 1e-9)
    result["pct_gain_d_to_c"] = 100 * result["gain_d_to_c"] / (result["shared_genes_d"] + 1e-9)
    result["pct_gain_c_to_b"] = 100 * result["gain_c_to_b"] / (result["shared_genes_c"] + 1e-9)
    result["pct_gain_b_to_a"] = 100 * result["gain_b_to_a"] / (result["shared_genes_b"] + 1e-9)

    _tslog(f"After aggregation: {len(result)} rows (was {pre_agg_rows})")

    # Select output columns
    output_cols = [
        "strain",
        "Sublineage",
        "row_type",
        "directory_leaf",
        "n_parts",
        "n_samples",
        "n_refseq_genomes",
        "n_refseq_genomes_sublineage",
        "shared_genes_e",
        "shared_genes_d",
        "shared_genes_c",
        "shared_genes_b",
        "shared_genes_a",
        "fallback_c",
        "fallback_b",
        "gain_e_to_d",
        "gain_d_to_c",
        "gain_c_to_b",
        "gain_b_to_a",
        "pct_gain_e_to_d",
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

    for level in ["e", "d", "c", "b", "a"]:
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
        help="Min n_samples per target KP epidemic CG (default 100)",
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
        _tslog(f"Loading metadata: {args.metadata}")
        metadata_df = pd.read_csv(args.metadata, sep="\t")

        granularity_df = compute_granularity_table(
            combined_df,
            metadata_df,
            args.data_dir,
            min_samples_per_cg=args.min_samples_per_cg,
            workers=args.workers,
        )

        if not granularity_df.empty:
            table_path = os.path.join(args.out_dir, "granularity_table.tsv")
            granularity_df.to_csv(table_path, sep="\t", index=False)
            _tslog(f"Wrote granularity table: {table_path}")

            summary_stats = compute_summary_stats(granularity_df)
            summary_df = pd.DataFrame(
                [{"metric": k, "value": v} for k, v in sorted(summary_stats.items())]
            )
            summary_path = os.path.join(args.out_dir, "granularity_summary.tsv")
            summary_df.to_csv(summary_path, sep="\t", index=False)
            _tslog(f"Wrote summary: {summary_path}")

            try:
                from bacotype.pl.granularity_lollipop import plot_granularity_lollipop

                _tslog("Generating lollipop plot...")
                plot_granularity_lollipop(granularity_df, args.out_dir)
            except ImportError:
                _tslog("WARNING: granularity_lollipop not found; skipping plot")
        else:
            _tslog("No target rows found; skipping granularity outputs")

    _tslog("=== gpa_reference_granularity.py end ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
