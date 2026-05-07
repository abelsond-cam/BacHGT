#!/usr/bin/env python3
"""GPA reference genome granularity analysis + run inventory.

Quantifies how much shared-gene coverage between query samples and their assigned
reference genome improves as the assignment becomes more granular:

  Level e (coarsest): global mgh78578 weighted mean across all KP runs (TSV only)
  Level d:            best mgh78578 vs the run's KP samples ("Ref mgh78578")
  Level c:            best single RefSeq across all non-RefSeq samples in the run
  Level b.i:          best single RefSeq scoped to one CG (or weighted-mean over
                       all CG-level subgroups including 'other' for SL/run rows)
  Level b.ii:         best single RefSeq scoped to one CG/K-locus subgroup
                       (or weighted-mean over all CG/KL subgroups for CG/SL rows)
  Level a (finest):   per-sample max-shared-genes RefSeq

Walks Panaroo run directories directly and computes everything from each run's
``gene_presence_absence.Rtab`` via a single BLAS dot-product per run (X_refseq @
X_query.T). No dependence on per-run detail TSVs from gpa_distances_batch_runs.sh.

Produces: granularity_table.tsv, granularity_summary.tsv, run_inventory.md (only
in 'inventory'/'both' modes — the inventory still reads the detail TSVs because
it reports run-classification metadata they encode), and delegates lollipop
plotting to bacotype.pl.granularity_lollipop.

Row types in the output table:
  kp_epidemic    — One per major CG (≥ min_group_size) within a KP sublineage run
  kp_epidemic_sl — One per KP sublineage run; weighted mean over all CG-level
                    subgroups in the run, including the 'other' bucket of small CGs
  kp_rare        — One per kp_rare_sublineage_batch_* run; same SL-style aggregation
  kp_species     — One per species_* run; same SL-style aggregation
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from bacotype.tl.gpa_distances_combined import load_and_concat_detail_tsvs
from bacotype.tl.gpa_distances_single_group import PANAROO_RUN_ROOT
from bacotype.tl.panaroo_groups import find_panaroo_runs, hierarchical_split

# Panaroo-run name patterns used to classify each run's output row type.
_RARE_PREFIX = "kp_rare_sublineage_batch"
_SPECIES_PREFIX = "species_"
_PART_SUFFIX_RE = re.compile(r"_part_\d+$")


def _tslog(message: str) -> None:
    """Print timestamped log line."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {message}", flush=True)


# -----------------------------------------------------------------------------
# Run inventory (still uses combined detail TSVs — independent of granularity)
# -----------------------------------------------------------------------------
def generate_run_inventory(combined_df: pd.DataFrame, out_path: str) -> None:
    """Write run inventory markdown from combined detail TSV."""
    _tslog("Generating run inventory markdown...")

    ws = combined_df[combined_df["group_level"] == "whole_set"].copy()
    cg_rows = combined_df[
        (combined_df["group_level"] == "clonal_group")
        & (combined_df["group_label"] != "other")
    ].copy()

    lines = [
        "# Panaroo Run Inventory",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"**Total runs:** {len(ws)}",
        f"**Total samples:** {ws['n_samples'].sum():,}",
        "",
        "## Runs",
        "",
        "| Run | Samples | Sublineages | Major CGs | Classification |",
        "|-----|---------|-------------|-----------|-----------------|",
    ]
    for _, row in ws.iterrows():
        run = row["directory_leaf"]
        samples = int(row["n_samples"])
        sls = int(row.get("n_unique_sublineages", 0))
        cgs_major = len(cg_rows[cg_rows["directory_leaf"] == run]["group_label"].unique())
        classification = str(row.get("run_classification", "unknown"))
        lines.append(f"| {run} | {samples} | {sls} | {cgs_major} | {classification} |")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    _tslog(f"Wrote inventory: {out_path}")


# -----------------------------------------------------------------------------
# Per-run processing — single BLAS dot-product, returns metrics for every node
# in the hierarchical split tree (whole_run, each CG, each CG/KL).
# -----------------------------------------------------------------------------
def process_panaroo_run(
    run_dir: str,
    metadata_df: pd.DataFrame,
    min_group_size: int,
    use_kpsc_filter: bool,
) -> dict[str, Any] | None:
    """Compute level d/c/a + per-node best_shared for one Panaroo run.

    Returns a dict::

        {
            "run_name":   <directory leaf>,
            "n_query":    int,             # number of query samples
            "level_d":    float | NaN,     # mgh78578 mean shared genes vs queries
            "level_c":    float,           # best ref vs all queries (run-wide)
            "level_a":    float,           # mean of per-sample max shared
            "n_refseq":   int,             # number of RefSeq genomes in the run
            "tree":       <output of hierarchical_split>,
            "node_metrics": {
                node_path_tuple: {
                    "n":           int,
                    "best_shared": float,    # max_ref mean shared(ref, members)
                    "level_a":     float,    # per-sample max mean within members
                },
                ...
            },
        }

    ``node_path_tuple`` is the path of labels from root to the node, e.g. ``()``
    for whole_run, ``("CG16",)`` for a major CG, ``("CG16","KL64")`` for a
    CG/KL leaf, ``("other",)`` for the run-level small-CG bucket.

    Returns None if the run cannot be processed (missing .Rtab, no RefSeqs, etc.).
    """
    try:
        rtab_path = os.path.join(run_dir, "gene_presence_absence.Rtab")
        if not os.path.isfile(rtab_path):
            _tslog(f"WARNING: Rtab not found: {rtab_path}")
            return None

        gpa = pd.read_csv(rtab_path, sep="\t", index_col=0)

        sample_id_col = None
        for col in ["Sample", "sample_id", "Sample ID", "SampleID", "sampleid"]:
            if col in metadata_df.columns:
                sample_id_col = col
                break
        if not sample_id_col:
            sample_id_col = metadata_df.columns[0]

        # Restrict to samples we actually consume (curated or reference). The raw
        # metadata file has duplicate Sample IDs for samples that were excluded
        # from the final curated list; those duplicates are never used here, so
        # drop them before set_index() to avoid pandas' "cannot reindex on an
        # axis with duplicate labels" error.
        flags = pd.DataFrame(
            {
                "kpsc": metadata_df.get("kpsc_final_list", False).fillna(False).astype(bool)
                if "kpsc_final_list" in metadata_df.columns
                else False,
                "ref": metadata_df.get("is_refseq", False).fillna(False).astype(bool)
                if "is_refseq" in metadata_df.columns
                else False,
                "mgh": metadata_df.get("is_mgh78578", False).fillna(False).astype(bool)
                if "is_mgh78578" in metadata_df.columns
                else False,
            }
        )
        keep_mask = flags["kpsc"] | flags["ref"] | flags["mgh"]
        meta_curated = metadata_df.loc[keep_mask]
        meta = meta_curated.set_index(sample_id_col).reindex(gpa.columns)

        is_refseq = meta["is_refseq"].fillna(False).astype(bool).to_numpy()
        is_mgh = (
            meta["is_mgh78578"].fillna(False).astype(bool).to_numpy()
            if "is_mgh78578" in meta.columns
            else np.zeros(len(meta), dtype=bool)
        )
        if use_kpsc_filter:
            is_query = (
                meta["kpsc_final_list"].fillna(False).astype(bool).to_numpy() & ~is_refseq
            )
        else:
            is_query = ~is_refseq

        if not is_refseq.any():
            _tslog(f"WARNING: No RefSeq samples in {run_dir}")
            return None
        if not is_query.any():
            _tslog(f"WARNING: No query samples in {run_dir}")
            return None

        # Binarise: (n_samples, n_genes)
        X = (gpa.values > 0).astype(np.uint8).T
        X_refseq = X[is_refseq]
        X_query = X[is_query]

        # Single BLAS SGEMM call — float32 preserves 0/1 binary values exactly.
        shared = X_refseq.astype(np.float32) @ X_query.astype(np.float32).T  # (n_refseq, n_query)

        # Per-sample best ref shared count (level a, computed once for whole run)
        per_sample_a = shared.max(axis=0)  # (n_query,)

        # Level c reference: pick the single ref that maximises mean shared
        # over ALL queries; per_sample_c is that ref's shared count for each
        # query sample. Per-node level c is then the mean of per_sample_c
        # restricted to the node's members (same shape as the OLD .Rtab path).
        best_run_ref = int(shared.mean(axis=1).argmax())
        per_sample_c = shared[best_run_ref, :]  # (n_query,)
        level_c_run = float(per_sample_c.mean())

        # Level d: mgh78578 mean shared vs queries (NaN if mgh not present).
        # per_sample_d is mgh's shared count for each query; per-node level d
        # is its mean restricted to the node's members.
        if is_mgh.any():
            X_mgh = X[is_mgh]  # (n_mgh, n_genes); usually n_mgh == 1
            shared_mgh = X_mgh.astype(np.float32) @ X_query.astype(np.float32).T  # (n_mgh, n_query)
            per_sample_d = shared_mgh.mean(axis=0)  # (n_query,)
            level_d_run = float(per_sample_d.mean())
        else:
            per_sample_d = np.full(shared.shape[1], np.nan, dtype=np.float32)
            level_d_run = float("nan")

        # Map query sample IDs to their column index in shared/per_sample_a
        query_ids = list(gpa.columns[is_query])
        id_to_idx = {sid: i for i, sid in enumerate(query_ids)}

        # Build hierarchical split of query samples by (Clonal group, K_locus)
        meta_for_queries = meta_curated.set_index(sample_id_col).reindex(query_ids)
        tree = hierarchical_split(
            meta_for_queries,
            sample_ids=query_ids,
            levels=["Clonal group", "K_locus"],
            min_group_size=min_group_size,
        )

        # Compute metrics for every node in the tree (whole_run + recursive).
        # Each node carries:
        #   level_d_node — mean of mgh78578's shared count over node members
        #   level_c_node — mean of run-best-ref's shared count over node members
        #   best_shared  — max over refs of mean shared over node members
        #                  (== "level b" for that node)
        #   level_a_node — mean of per-sample max over node members
        node_metrics: dict[tuple[str, ...], dict[str, float]] = {}

        def _walk(node: dict, path: tuple[str, ...]) -> None:
            members = node["members"]
            mask_idx = [id_to_idx[m] for m in members if m in id_to_idx]
            if not mask_idx:
                return
            sub_shared = shared[:, mask_idx]
            node_metrics[path] = {
                "n": len(mask_idx),
                "best_shared": float(sub_shared.mean(axis=1).max()),
                "level_d": float(np.nanmean(per_sample_d[mask_idx])),
                "level_c": float(per_sample_c[mask_idx].mean()),
                "level_a": float(per_sample_a[mask_idx].mean()),
            }
            for child in node["subgroups"]:
                _walk(child, path + (child["label"],))

        _walk(tree, ())

        return {
            "run_name": os.path.basename(run_dir.rstrip("/")),
            "n_query": int(is_query.sum()),
            "level_d": level_d_run,
            "level_c": level_c_run,
            "level_a": float(per_sample_a.mean()),
            "n_refseq": int(is_refseq.sum()),
            "tree": tree,
            "node_metrics": node_metrics,
        }
    except Exception as e:
        _tslog(f"ERROR processing run {run_dir}: {e}")
        return None


# -----------------------------------------------------------------------------
# Row construction from per-run results
# -----------------------------------------------------------------------------
def _strip_part_suffix(run_name: str) -> str:
    """Strip ``_part_N`` from the end of a Panaroo run name (e.g. SL15_part_0 → SL15)."""
    return _PART_SUFFIX_RE.sub("", run_name)


def _classify_run_name(run_name: str) -> str:
    """Return one of 'kp_rare', 'kp_species', or 'kp_sublineage'."""
    if run_name.startswith(_RARE_PREFIX):
        return "kp_rare"
    if run_name.startswith(_SPECIES_PREFIX):
        return "kp_species"
    return "kp_sublineage"


def _species_label(run_name: str) -> str:
    """Pretty label for a non-KP species run: K. variicola subsp. variicola etc."""
    return (
        run_name.replace("species_Klebsiella_", "K. ")
        .replace("_subsp._", " ssp. ")
        .replace("_", " ")
    )


def _rare_label(run_name: str) -> str:
    """Pretty label for a kp_rare batch run: kp_rare_sublineage_batch_3 → rare_batch_3."""
    return run_name.replace("kp_rare_sublineage_batch_", "rare_batch_")


def _weighted_mean(pairs: list[tuple[float, float]]) -> float:
    """Weighted mean from a list of (weight, value); NaN values are ignored.

    Returns NaN if no valid (weight, value) entries.
    """
    total_w = 0.0
    total_wv = 0.0
    for w, v in pairs:
        if v is None or np.isnan(v) or w <= 0:
            continue
        total_w += w
        total_wv += w * v
    return total_wv / total_w if total_w > 0 else float("nan")


def _build_run_summary_row(
    run: dict,
    row_type: str,
    strain: str,
    sublineage: str,
) -> dict:
    """Construct an SL-style row (kp_epidemic_sl / kp_rare / kp_species).

    SL-style rows aggregate ALL top-level subgroups in the run, including the
    'other' bucket of small CGs. This is the bias-fix the user requested: the
    SL row truly represents the whole run, not just its big CGs.
    """
    nm = run["node_metrics"]
    tree = run["tree"]
    top_subgroups = tree["subgroups"] or [{"label": "__no_split__"}]

    # b.i: weighted mean across top-level subgroups (CGs + 'other') of best_shared
    bi_pairs: list[tuple[float, float]] = []
    bii_pairs: list[tuple[float, float]] = []
    for child in tree["subgroups"]:
        path = (child["label"],)
        if path not in nm:
            continue
        n_child = nm[path]["n"]
        bi_child = nm[path]["best_shared"]
        bi_pairs.append((n_child, bi_child))

        # b.ii for this child: weighted mean across its grandchildren if any,
        # else fall back to its own best_shared (e.g. 'other' bucket).
        if child["subgroups"]:
            grandchild_pairs = [
                (nm[path + (gc["label"],)]["n"], nm[path + (gc["label"],)]["best_shared"])
                for gc in child["subgroups"]
                if path + (gc["label"],) in nm
            ]
            bii_child = _weighted_mean(grandchild_pairs)
        else:
            bii_child = bi_child
        bii_pairs.append((n_child, bii_child))

    # If no top-level split happened (no CG column or all in one bucket), fall
    # back to whole-run level_c for b.i and b.ii.
    if not bi_pairs:
        bi_value = run["level_c"]
        bii_value = run["level_c"]
        fallback_b_i = True
        fallback_b_ii = True
    else:
        bi_value = _weighted_mean(bi_pairs)
        bii_value = _weighted_mean(bii_pairs)
        fallback_b_i = False
        # b.ii falls back to b.i for runs where no second-level split happened
        any_second_level = any(child["subgroups"] for child in tree["subgroups"])
        fallback_b_ii = not any_second_level

    return {
        "strain": strain,
        "Sublineage": sublineage,
        "row_type": row_type,
        "directory_leaf": run["run_name"],
        "n_parts": 1,
        "n_samples": run["n_query"],
        "n_refseq_genomes": run["n_refseq"],
        "shared_genes_d": run["level_d"],
        "shared_genes_c": run["level_c"],
        "shared_genes_b_i": bi_value,
        "shared_genes_b_ii": bii_value,
        "shared_genes_a": run["level_a"],
        "fallback_b_i": fallback_b_i,
        "fallback_b_ii": fallback_b_ii,
    }


def _build_cg_rows(
    run: dict,
    sublineage: str,
    metadata_df: pd.DataFrame,
) -> list[dict]:
    """One kp_epidemic row per major CG within a KP sublineage run."""
    nm = run["node_metrics"]
    tree = run["tree"]
    rows: list[dict] = []

    sample_id_col = None
    for col in ["Sample", "sample_id", "Sample ID", "SampleID", "sampleid"]:
        if col in metadata_df.columns:
            sample_id_col = col
            break
    if sample_id_col is None:
        sample_id_col = metadata_df.columns[0]
    # Same curated-only filter as in process_panaroo_run — avoids the duplicate
    # Sample IDs that exist for non-curated rows in the raw metadata file.
    if "kpsc_final_list" in metadata_df.columns:
        keep = metadata_df["kpsc_final_list"].fillna(False).astype(bool)
        if "is_refseq" in metadata_df.columns:
            keep = keep | metadata_df["is_refseq"].fillna(False).astype(bool)
        if "is_mgh78578" in metadata_df.columns:
            keep = keep | metadata_df["is_mgh78578"].fillna(False).astype(bool)
        meta_idx = metadata_df.loc[keep].set_index(sample_id_col)
    else:
        meta_idx = metadata_df.set_index(sample_id_col)

    for cg_node in tree["subgroups"]:
        if cg_node["label"] == "other":
            continue  # 'other' bucket isn't its own kp_epidemic row
        path = (cg_node["label"],)
        if path not in nm:
            continue

        # b.ii for this CG: weighted mean across its CG/KL grandchildren incl. 'other'
        if cg_node["subgroups"]:
            grandchild_pairs = [
                (nm[path + (gc["label"],)]["n"], nm[path + (gc["label"],)]["best_shared"])
                for gc in cg_node["subgroups"]
                if path + (gc["label"],) in nm
            ]
            bii_value = _weighted_mean(grandchild_pairs)
            fallback_b_ii = False
        else:
            bii_value = nm[path]["best_shared"]
            fallback_b_ii = True

        # Resolve a per-CG Sublineage label: most common Sublineage among the
        # CG's members (handles split runs where a CG can carry its parent SL).
        cg_members = cg_node["members"]
        sub_meta = meta_idx.reindex(cg_members)
        if "Sublineage" in sub_meta.columns:
            sl_vc = sub_meta["Sublineage"].dropna().astype(str).value_counts()
            cg_sublineage = sl_vc.index[0] if len(sl_vc) else sublineage
        else:
            cg_sublineage = sublineage

        rows.append(
            {
                "strain": cg_node["label"],
                "Sublineage": cg_sublineage,
                "row_type": "kp_epidemic",
                "directory_leaf": run["run_name"],
                "n_parts": 1,
                "n_samples": nm[path]["n"],
                "n_refseq_genomes": run["n_refseq"],
                "shared_genes_d": nm[path]["level_d"],
                "shared_genes_c": nm[path]["level_c"],
                "shared_genes_b_i": nm[path]["best_shared"],
                "shared_genes_b_ii": bii_value,
                "shared_genes_a": nm[path]["level_a"],
                "fallback_b_i": False,
                "fallback_b_ii": fallback_b_ii,
            }
        )
    return rows


# -----------------------------------------------------------------------------
# Main table builder
# -----------------------------------------------------------------------------
def compute_granularity_table(
    panaroo_run_root: str,
    metadata_df: pd.DataFrame,
    min_group_size: int = 50,
    workers: int = 1,
) -> pd.DataFrame:
    """Build the full granularity table by walking Panaroo runs directly.

    No longer depends on per-run detail TSVs from gpa_distances_batch_runs.sh.
    """
    _tslog("=== Computing granularity table ===")
    runs = find_panaroo_runs(panaroo_run_root)
    _tslog(f"Discovered {len(runs)} Panaroo runs")

    # Process each run in parallel (or serial if workers=1)
    run_params = [
        (
            os.path.join(panaroo_run_root, r),
            r,
            _classify_run_name(r) != "kp_species",  # use_kpsc_filter — false for species
        )
        for r in runs
    ]
    run_results: dict[str, dict] = {}

    if workers > 1:
        _tslog(f"Processing {len(runs)} runs in parallel (workers={workers})...")
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    process_panaroo_run, rd, metadata_df, min_group_size, use_kpsc
                ): name
                for rd, name, use_kpsc in run_params
            }
            for future in futures:
                name = futures[future]
                try:
                    res = future.result(timeout=600)
                    if res is not None:
                        run_results[name] = res
                except Exception as e:
                    _tslog(f"ERROR for run {name}: {e}")
    else:
        for rd, name, use_kpsc in run_params:
            res = process_panaroo_run(rd, metadata_df, min_group_size, use_kpsc)
            if res is not None:
                run_results[name] = res
    _tslog(f"Processed {len(run_results)} runs successfully")

    if not run_results:
        return pd.DataFrame()

    # Compute global level_e: weighted mean of per-run level_d across ALL runs
    total_n = sum(r["n_query"] for r in run_results.values())
    valid_d = [
        (r["n_query"], r["level_d"]) for r in run_results.values() if not np.isnan(r["level_d"])
    ]
    level_e = (
        sum(n * d for n, d in valid_d) / sum(n for n, _ in valid_d) if valid_d else float("nan")
    )
    _tslog(f"Global mgh78578 baseline (level e): {level_e:.2f}")

    # Build rows from each run
    all_rows: list[dict] = []
    for run_name, run in run_results.items():
        row_class = _classify_run_name(run_name)
        if row_class == "kp_rare":
            label = _rare_label(run_name)
            all_rows.append(_build_run_summary_row(run, "kp_rare", label, label))
        elif row_class == "kp_species":
            label = _species_label(run_name)
            all_rows.append(_build_run_summary_row(run, "kp_species", label, label))
        else:
            sl_label = _strip_part_suffix(run_name)
            # kp_epidemic CG rows
            all_rows.extend(_build_cg_rows(run, sl_label, metadata_df))
            # kp_epidemic_sl row (one per Panaroo run-part — aggregated below)
            all_rows.append(
                _build_run_summary_row(run, "kp_epidemic_sl", sl_label, sl_label)
            )

    result = pd.DataFrame(all_rows)
    result["shared_genes_e"] = level_e

    # Aggregate split-run parts: kp_epidemic CG rows and kp_epidemic_sl rows can
    # span multiple parts (e.g. SL15_part_0 + SL15_part_1) — collapse to one
    # row per unique (strain, Sublineage, row_type) by n_samples-weighted mean.
    _tslog(f"Pre-aggregation rows: {len(result)}")
    result = _aggregate_split_runs(result)
    _tslog(f"Post-aggregation rows: {len(result)}")

    # Compute gain columns
    result["gain_e_to_d"] = result["shared_genes_d"] - result["shared_genes_e"]
    result["gain_d_to_c"] = result["shared_genes_c"] - result["shared_genes_d"]
    result["gain_c_to_b_i"] = result["shared_genes_b_i"] - result["shared_genes_c"]
    result["gain_b_i_to_b_ii"] = result["shared_genes_b_ii"] - result["shared_genes_b_i"]
    result["gain_b_ii_to_a"] = result["shared_genes_a"] - result["shared_genes_b_ii"]
    eps = 1e-9
    result["pct_gain_e_to_d"] = 100 * result["gain_e_to_d"] / (result["shared_genes_e"] + eps)
    result["pct_gain_d_to_c"] = 100 * result["gain_d_to_c"] / (result["shared_genes_d"] + eps)
    result["pct_gain_c_to_b_i"] = 100 * result["gain_c_to_b_i"] / (result["shared_genes_c"] + eps)
    result["pct_gain_b_i_to_b_ii"] = (
        100 * result["gain_b_i_to_b_ii"] / (result["shared_genes_b_i"] + eps)
    )
    result["pct_gain_b_ii_to_a"] = (
        100 * result["gain_b_ii_to_a"] / (result["shared_genes_b_ii"] + eps)
    )

    output_cols = [
        "strain",
        "Sublineage",
        "row_type",
        "directory_leaf",
        "n_parts",
        "n_samples",
        "n_refseq_genomes",
        "shared_genes_e",
        "shared_genes_d",
        "shared_genes_c",
        "shared_genes_b_i",
        "shared_genes_b_ii",
        "shared_genes_a",
        "fallback_b_i",
        "fallback_b_ii",
        "gain_e_to_d",
        "gain_d_to_c",
        "gain_c_to_b_i",
        "gain_b_i_to_b_ii",
        "gain_b_ii_to_a",
        "pct_gain_e_to_d",
        "pct_gain_d_to_c",
        "pct_gain_c_to_b_i",
        "pct_gain_b_i_to_b_ii",
        "pct_gain_b_ii_to_a",
    ]
    result = result[[c for c in output_cols if c in result.columns]]
    _tslog(f"Granularity table: {len(result)} rows")
    return result


def _aggregate_split_runs(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multiple Panaroo-run parts of the same (strain, Sublineage, row_type)
    into one row by n_samples-weighted mean of all numeric columns."""
    weighted_cols = [
        "shared_genes_d",
        "shared_genes_c",
        "shared_genes_b_i",
        "shared_genes_b_ii",
        "shared_genes_a",
        "n_refseq_genomes",
    ]

    def _agg(grp: pd.DataFrame) -> pd.Series:
        w = grp["n_samples"]
        out: dict = {
            "n_samples": float(w.sum()),
            "n_parts": int(len(grp)),
            "directory_leaf": ";".join(sorted(set(grp["directory_leaf"]))),
            "shared_genes_e": grp["shared_genes_e"].iloc[0],
            "fallback_b_i": bool(grp["fallback_b_i"].any()),
            "fallback_b_ii": bool(grp["fallback_b_ii"].any()),
        }
        for col in weighted_cols:
            if col not in grp.columns:
                continue
            valid = grp[col].notna()
            out[col] = (
                (grp.loc[valid, col] * w[valid]).sum() / w[valid].sum()
                if valid.any()
                else float("nan")
            )
        return pd.Series(out)

    return (
        df.groupby(["strain", "Sublineage", "row_type"], sort=False)
        .apply(_agg, include_groups=False)
        .reset_index()
    )


def compute_summary_stats(granularity_df: pd.DataFrame) -> dict[str, float]:
    """Compute aggregate summary statistics."""
    stats: dict[str, float] = {}
    for level in ["e", "d", "c", "b_i", "b_ii", "a"]:
        col = f"shared_genes_{level}"
        if col in granularity_df.columns:
            valid = granularity_df[col].dropna()
            if not valid.empty:
                stats[f"mean_{level}"] = float(valid.mean())
                stats[f"median_{level}"] = float(valid.median())
                stats[f"std_{level}"] = float(valid.std())
                stats[f"min_{level}"] = float(valid.min())
                stats[f"max_{level}"] = float(valid.max())
    if "shared_genes_b_i" in granularity_df.columns:
        stats["pct_b_i_gt_c"] = float(
            (granularity_df["shared_genes_b_i"] > granularity_df["shared_genes_c"]).mean() * 100
        )
    if "shared_genes_b_ii" in granularity_df.columns:
        stats["pct_b_ii_gt_b_i"] = float(
            (granularity_df["shared_genes_b_ii"] > granularity_df["shared_genes_b_i"]).mean() * 100
        )
    if "shared_genes_a" in granularity_df.columns:
        valid_a = granularity_df[granularity_df["shared_genes_a"].notna()]
        if not valid_a.empty:
            stats["pct_a_gt_b_ii"] = float(
                (valid_a["shared_genes_a"] > valid_a["shared_genes_b_ii"]).mean() * 100
            )
    return stats


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main(argv: Iterable[str] | None = None) -> int:
    """Parse args and run inventory/granularity analysis."""
    parser = argparse.ArgumentParser(
        description="GPA reference genome granularity analysis + run inventory."
    )
    parser.add_argument("--data-dir", default=PANAROO_RUN_ROOT)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument(
        "--mode", choices=("inventory", "granularity", "both"), default="both"
    )
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=50,
        help="Minimum CG / K-locus subgroup size to get its own slice (default 50). "
        "Smaller groups are pooled into the 'other' bucket at each level.",
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Parallel workers (default 1)"
    )
    parser.add_argument("--test-n-runs", type=int, default=None)
    parser.add_argument(
        "--recompile",
        action="store_true",
        help="Force rebuild of combined detail TSV (only used by 'inventory' mode)",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.out_dir is None:
        args.out_dir = os.path.join(os.path.dirname(args.data_dir), "granularity")
    os.makedirs(args.out_dir, exist_ok=True)

    _tslog("=== gpa_reference_granularity.py start ===")
    _tslog(f"Mode: {args.mode}")
    _tslog(f"Data dir: {args.data_dir}")
    _tslog(f"Out dir: {args.out_dir}")
    _tslog(f"min_group_size: {args.min_group_size}")

    # Inventory mode: still uses combined detail TSVs (loads them on demand)
    if args.mode in ("inventory", "both"):
        _tslog("Loading combined detail TSV for inventory...")
        try:
            combined_df = load_and_concat_detail_tsvs(
                args.data_dir, write_tsv=False, recompile=args.recompile
            )
            inv_path = os.path.join(args.out_dir, "run_inventory.md")
            generate_run_inventory(combined_df, inv_path)
        except Exception as e:
            _tslog(f"WARNING: inventory generation failed: {e}")

    # Granularity mode: walks Panaroo runs directly via .Rtab; no detail-TSV dep
    if args.mode in ("granularity", "both"):
        _tslog(f"Loading metadata: {args.metadata}")
        metadata_df = pd.read_csv(args.metadata, sep="\t", low_memory=False)

        # Optional run-count cap for testing
        if args.test_n_runs:
            all_runs = find_panaroo_runs(args.data_dir)[: args.test_n_runs]
            _tslog(f"Test mode: limiting to first {args.test_n_runs} runs: {all_runs}")
            # Build a temporary symlink-free filtered tree by filtering at process time
            # (cheaper: just patch find_panaroo_runs via module attribute)
            import bacotype.tl.gpa_reference_granularity as _self_mod

            _orig = _self_mod.find_panaroo_runs
            _self_mod.find_panaroo_runs = lambda root: all_runs  # type: ignore[assignment]
            try:
                granularity_df = compute_granularity_table(
                    args.data_dir,
                    metadata_df,
                    min_group_size=args.min_group_size,
                    workers=args.workers,
                )
            finally:
                _self_mod.find_panaroo_runs = _orig  # type: ignore[assignment]
        else:
            granularity_df = compute_granularity_table(
                args.data_dir,
                metadata_df,
                min_group_size=args.min_group_size,
                workers=args.workers,
            )

        if granularity_df.empty:
            _tslog("No granularity rows produced; skipping outputs")
        else:
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

                sl_filter = ["kp_epidemic_sl", "kp_rare", "kp_species"]
                dark_blue = "#003d82"

                _tslog("Generating Sublineage-level lollipop (base, with histogram)...")
                plot_granularity_lollipop(
                    granularity_df,
                    args.out_dir,
                    filename_stem="granularity_lollipop_sl",
                    row_type_filter=sl_filter,
                )

                _tslog("Generating SL lollipop: highlight non-KP species...")
                plot_granularity_lollipop(
                    granularity_df,
                    args.out_dir,
                    filename_stem="granularity_lollipop_sl_highlight_species",
                    row_type_filter=sl_filter,
                    highlight_color=dark_blue,
                    highlight_row_types=["kp_species"],
                    highlight_cg_gain_genes=None,
                    make_histogram=False,
                )
                _tslog("Generating SL lollipop: highlight epidemic sublineages...")
                plot_granularity_lollipop(
                    granularity_df,
                    args.out_dir,
                    filename_stem="granularity_lollipop_sl_highlight_epidemic",
                    row_type_filter=sl_filter,
                    highlight_color=dark_blue,
                    highlight_row_types=["kp_epidemic_sl"],
                    highlight_cg_gain_genes=None,
                    make_histogram=False,
                )
                _tslog(
                    "Generating SL lollipop: highlight epidemic SLs with c→b.i gain > 20..."
                )
                plot_granularity_lollipop(
                    granularity_df,
                    args.out_dir,
                    filename_stem="granularity_lollipop_sl_highlight_epidemic_high_gain",
                    row_type_filter=sl_filter,
                    highlight_color=dark_blue,
                    highlight_row_types=["kp_epidemic_sl"],
                    highlight_cg_gain_genes=20.0,
                    make_histogram=False,
                )
                _tslog("Generating SL lollipop: highlight rare lineage batches...")
                plot_granularity_lollipop(
                    granularity_df,
                    args.out_dir,
                    filename_stem="granularity_lollipop_sl_highlight_rare",
                    row_type_filter=sl_filter,
                    highlight_color=dark_blue,
                    highlight_row_types=["kp_rare"],
                    highlight_cg_gain_genes=None,
                    make_histogram=False,
                )
            except ImportError:
                _tslog("WARNING: granularity_lollipop not found; skipping plot")

    _tslog("=== gpa_reference_granularity.py end ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
