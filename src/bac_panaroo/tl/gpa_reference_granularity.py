#!/usr/bin/env python3
"""GPA reference genome granularity analysis + run inventory.

Quantifies how much shared-gene coverage between query samples and their assigned
reference genome improves as the assignment becomes more granular:

  Level f (coarsest): best mgh78578 vs the run's KP samples ("Ref mgh78578")
  Level e:            best single RefSeq across same-species refs only
                       ("Best RefSeq in Subspecies"; falls back to f when no
                       same-species refs are present in the run)
  Level d:            best single RefSeq across all non-RefSeq samples in the run
  Level c:            best single RefSeq scoped to one CG (or weighted-mean over
                       all CG-level subgroups including 'other' for SL/run rows)
  Level b:            best single RefSeq scoped to one CG/K-locus subgroup
                       (or weighted-mean over all CG/KL subgroups for CG/SL rows)
  Level a (finest):   per-sample max-shared-genes RefSeq

Walks Panaroo run directories directly and computes everything from each run's
``gene_presence_absence.Rtab`` via a single BLAS dot-product per run (X_refseq @
X_query.T). No dependence on per-run detail TSVs from gpa_distances_batch_runs.sh.

Produces: granularity_table.tsv, granularity_summary.tsv,
best_e_ref_per_species.tsv, best_reference_per_sample.csv (one row per
run/query sample with the best reference + shared-gene count at every level),
run_inventory.md (only in 'inventory'/'both' modes — the inventory still reads
the detail TSVs because it reports run-classification metadata they encode),
and delegates lollipop plotting to bac_panaroo.pl.granularity_lollipop.

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

from bac_panaroo.tl.gpa_distances_combined import load_and_concat_detail_tsvs
from bac_panaroo.tl.gpa_distances_single_group import PANAROO_RUN_ROOT
from bac_panaroo.tl.panaroo_groups import find_panaroo_runs, hierarchical_split

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
    bucket_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """Compute level f/d/a + per-node best_shared + bucket matrix for one Panaroo run.

    Level e is **not** computed here (it requires a cross-run species-level
    aggregation). Instead this function returns the bucket-vs-query shared-gene
    matrix and per-bucket-ref per-run mean, which ``compute_granularity_table``
    uses to pick the best bucket ref per species and then fill in level e on
    every node.

    Returns a dict::

        {
            "run_name":            <directory leaf>,
            "n_query":             int,
            "level_f":             float | NaN,
            "level_d":             float,
            "level_a":             float,
            "n_refseq":            int,
            "tree":                <output of hierarchical_split>,
            "node_metrics":        {<path>: {"n", "best_shared", "level_f",
                                              "level_d", "level_a"}},
            "query_species":       str | None,
            "query_ids":           list[str],
            "per_sample_f":        np.ndarray (n_query,),  # mgh per-query, for
                                                            # fallback_e use
            "bucket_shared":       np.ndarray (n_bucket_in_run, n_query),
            "bucket_ref_ids_in_run": list[str],
            "bucket_per_run_means": dict[str, float],
        }

    ``bucket_ids`` is the set of Sample IDs designated as the reference bucket
    (mgh + Norway-completes + HS11286 by default). If None or empty, the
    function still works but level e in the table builder will be effectively
    "best of mgh" (== level f) for every row. Bucket members not present in this
    particular run are silently skipped (they just won't appear in
    ``bucket_per_run_means`` for this run).

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

        # Per-sample best ref shared count + which ref it was (level a,
        # computed once for whole run).
        per_sample_a = shared.max(axis=0)  # (n_query,)
        per_sample_a_idx = shared.argmax(axis=0).astype(np.int64)  # (n_query,)

        # Level d reference: pick the single ref that maximises mean shared
        # over ALL queries; per_sample_d is that ref's shared count for each
        # query sample. Per-node level d is then the mean of per_sample_d
        # restricted to the node's members (same shape as the OLD .Rtab path).
        best_run_ref = int(shared.mean(axis=1).argmax())
        per_sample_d = shared[best_run_ref, :]  # (n_query,)
        level_d_run = float(per_sample_d.mean())

        # Level f: mgh78578 mean shared vs queries (NaN if mgh not present).
        # per_sample_f is mgh's shared count for each query; per-node level f
        # is its mean restricted to the node's members.
        if is_mgh.any():
            X_mgh = X[is_mgh]  # (n_mgh, n_genes); usually n_mgh == 1
            shared_mgh = X_mgh.astype(np.float32) @ X_query.astype(np.float32).T  # (n_mgh, n_query)
            per_sample_f = shared_mgh.mean(axis=0)  # (n_query,)
            level_f_run = float(per_sample_f.mean())
        else:
            per_sample_f = np.full(shared.shape[1], np.nan, dtype=np.float32)
            level_f_run = float("nan")

        # Reference Sample ID used for level f (mgh78578; usually exactly one).
        mgh_ref_ids = list(gpa.columns[is_mgh])
        mgh_ref_id = mgh_ref_ids[0] if mgh_ref_ids else None

        # Map query sample IDs to their column index in shared/per_sample_a
        query_ids = list(gpa.columns[is_query])
        id_to_idx = {sid: i for i, sid in enumerate(query_ids)}

        meta_for_queries = meta_curated.set_index(sample_id_col).reindex(query_ids)

        # Query species: modal species of this run's queries (uniform in practice
        # — KP for sublineage/rare, the named species for species_* runs).
        query_species = (
            meta_for_queries["species"].mode().iloc[0]
            if "species" in meta_for_queries.columns
            and not meta_for_queries["species"].dropna().empty
            else None
        )

        # Bucket-vs-query shared-gene matrix. The bucket is chosen run-externally
        # (default: mgh + all Norway-completes + HS11286, defined by reference_bucket.tsv);
        # here we just slice ``shared`` to whichever bucket members are present
        # in this run's ref set. The per-run mean for each bucket ref is what
        # the table builder later weights across runs of the same species to
        # pick best_e_ref[species].
        ref_sample_ids = list(gpa.columns[is_refseq])
        if bucket_ids:
            bucket_indices = [
                i for i, sid in enumerate(ref_sample_ids) if sid in bucket_ids
            ]
        else:
            bucket_indices = []
        bucket_ref_ids_in_run = [ref_sample_ids[i] for i in bucket_indices]
        if bucket_indices:
            bucket_shared = shared[bucket_indices, :].astype(np.float32, copy=False)
        else:
            bucket_shared = np.zeros((0, shared.shape[1]), dtype=np.float32)
        bucket_per_run_means: dict[str, float] = {
            sid: float(bucket_shared[i].mean())
            for i, sid in enumerate(bucket_ref_ids_in_run)
        }

        # Build hierarchical split of query samples by (Sublineage, Clonal
        # group, K_locus). For KP sublineage runs the SL split is trivial
        # (one major SL, no 'other_SL' bucket) so kp_epidemic / kp_epidemic_sl
        # rows are unchanged. For kp_rare and kp_species runs the SL split
        # adds real resolution: each batch contains many SLs.
        tree = hierarchical_split(
            meta_for_queries,
            sample_ids=query_ids,
            levels=["Sublineage", "Clonal group", "K_locus"],
            min_group_size=min_group_size,
        )

        # Compute metrics for every node in the tree (whole_run + recursive).
        # Level e is filled in later by ``compute_granularity_table`` after the
        # cross-run species-level pick of best_e_ref. ``best_ref_idx`` records
        # WHICH ref (row of ``shared``) maximises the node's mean shared genes;
        # it feeds the per-sample best-reference table.
        node_metrics: dict[tuple[str, ...], dict[str, float]] = {}

        # Per-sample ref index for the CG-level (tree depth 2) and
        # CG/K-locus-level (depth 3) node a sample belongs to. Level c defaults
        # to the run-level best ref (== level d); level b defaults to its
        # level-c ref where the sample's CG carried no K-locus split.
        n_q = shared.shape[1]
        per_sample_c_idx = np.full(n_q, best_run_ref, dtype=np.int64)
        per_sample_b_idx = np.full(n_q, -1, dtype=np.int64)

        def _walk(node: dict, path: tuple[str, ...], depth: int) -> None:
            members = node["members"]
            mask_idx = [id_to_idx[m] for m in members if m in id_to_idx]
            if not mask_idx:
                return
            sub_shared = shared[:, mask_idx]
            mean_per_ref = sub_shared.mean(axis=1)
            best_ref_idx = int(mean_per_ref.argmax())
            node_metrics[path] = {
                "n": len(mask_idx),
                "best_shared": float(mean_per_ref.max()),
                "best_ref_idx": best_ref_idx,
                "level_f": float(np.nanmean(per_sample_f[mask_idx])),
                "level_e": float("nan"),  # filled by compute_granularity_table
                "level_d": float(per_sample_d[mask_idx].mean()),
                "level_a": float(per_sample_a[mask_idx].mean()),
            }
            if depth == 2:
                per_sample_c_idx[mask_idx] = best_ref_idx
            elif depth == 3:
                per_sample_b_idx[mask_idx] = best_ref_idx
            for child in node["subgroups"]:
                _walk(child, path + (child["label"],), depth + 1)

        _walk(tree, (), 0)

        # Samples whose CG carried no K-locus split fall back to the level-c ref.
        _b_missing = per_sample_b_idx < 0
        per_sample_b_idx[_b_missing] = per_sample_c_idx[_b_missing]

        # Resolve per-sample shared-gene counts for the level-c / level-b refs.
        _cols = np.arange(n_q)
        per_sample_c = shared[per_sample_c_idx, _cols]
        per_sample_b = shared[per_sample_b_idx, _cols]

        return {
            "run_name": os.path.basename(run_dir.rstrip("/")),
            "n_query": int(is_query.sum()),
            "level_f": level_f_run,
            "level_d": level_d_run,
            "level_a": float(per_sample_a.mean()),
            "n_refseq": int(is_refseq.sum()),
            "tree": tree,
            "node_metrics": node_metrics,
            "query_species": query_species,
            "query_ids": query_ids,
            "ref_ids": ref_sample_ids,
            "mgh_ref_id": mgh_ref_id,
            "best_run_ref": best_run_ref,
            "per_sample_f": per_sample_f,
            "per_sample_d": per_sample_d,
            "per_sample_a": per_sample_a,
            "per_sample_a_idx": per_sample_a_idx,
            "per_sample_c": per_sample_c,
            "per_sample_c_idx": per_sample_c_idx,
            "per_sample_b": per_sample_b,
            "per_sample_b_idx": per_sample_b_idx,
            "bucket_shared": bucket_shared,
            "bucket_ref_ids_in_run": bucket_ref_ids_in_run,
            "bucket_per_run_means": bucket_per_run_means,
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


def _aggregate_best_shared(
    node: dict,
    node_metrics: dict[tuple[str, ...], dict[str, float]],
    target_depth: int,
    path: tuple[str, ...] = (),
    depth: int = 0,
) -> tuple[float, float]:
    """Walk a hierarchical_split subtree and weighted-average ``best_shared``
    over the subtree's children at ``target_depth`` (relative to ``node``).

    "Other" buckets and any node that has no further subgroups contribute
    their own ``best_shared`` regardless of depth, matching the convention
    that 'other' is a single non-recursive bucket.

    Parameters
    ----------
    node
        Current tree node (output of ``hierarchical_split``).
    node_metrics
        Per-node metric dict keyed by absolute path tuple (the path from the
        whole-run root, not from ``node``).
    target_depth
        Aggregate down to children at this depth below ``node`` (1 = direct
        children, 2 = grandchildren, etc.). Children that bottom out earlier
        (no subgroups) contribute their own ``best_shared``.
    path
        Absolute path of ``node`` from the whole-run root (used to look up
        ``node_metrics``); pass the empty tuple at the root.
    depth
        Recursion depth tracker (do not pass).

    Returns
    -------
    (n_samples, weighted_best_shared) tuple. NaN value if no contributing
    children carry valid metrics.
    """
    if path not in node_metrics:
        return (0.0, float("nan"))
    n_node = float(node_metrics[path]["n"])

    # If we've reached target depth or this node can't recurse further,
    # contribute the node's own best_shared as a leaf.
    if depth >= target_depth or not node.get("subgroups"):
        return (n_node, float(node_metrics[path]["best_shared"]))

    pairs: list[tuple[float, float]] = []
    for child in node["subgroups"]:
        child_path = path + (child["label"],)
        n_child, val_child = _aggregate_best_shared(
            child, node_metrics, target_depth, child_path, depth + 1
        )
        if n_child > 0 and not np.isnan(val_child):
            pairs.append((n_child, val_child))
    return (n_node, _weighted_mean(pairs))


def _build_run_summary_row(
    run: dict,
    row_type: str,
    strain: str,
    sublineage: str,
) -> dict:
    """Construct an SL-style row (kp_epidemic_sl / kp_rare / kp_species).

    The hierarchical split tree has three levels — Sublineage, Clonal group,
    K-locus — so this row's values come from progressively-deeper aggregations:

      * level d  = weighted mean of best_shared across SL-level children
                    (depth 1 from root); 'other_SL' contributes its own
                    best_shared as a single non-recursive bucket
      * level c  = same but at depth 2 (CGs within each SL + each SL's
                    'other_CG' + run's 'other_SL')
      * level b  = depth 3 (CG/K-locus leaves); nodes that bottom out
                    earlier contribute their own best_shared

    This is the bias-fix: rare-batch and species runs no longer treat the
    whole heterogeneous run as one group when computing level d, and SL row
    values aren't biased toward big children at any level.
    """
    nm = run["node_metrics"]
    tree = run["tree"]

    if not tree.get("subgroups"):
        # No splittable structure (run has no Sublineage column or no rows
        # past filters): fall back to whole-run scalars at every level.
        return {
            "strain": strain,
            "Sublineage": sublineage,
            "row_type": row_type,
            "directory_leaf": run["run_name"],
            "n_parts": 1,
            "n_samples": run["n_query"],
            "n_refseq_genomes": run["n_refseq"],
            "shared_genes_f": run["level_f"],
            "shared_genes_e": run["level_e"],
            "shared_genes_d": run["level_d"],
            "shared_genes_c": run["level_d"],
            "shared_genes_b": run["level_d"],
            "shared_genes_a": run["level_a"],
            "fallback_e": run.get("fallback_e", False),
            "fallback_c": True,
            "fallback_b": True,
        }

    _, d_value = _aggregate_best_shared(tree, nm, target_depth=1)
    _, c_value = _aggregate_best_shared(tree, nm, target_depth=2)
    _, b_value = _aggregate_best_shared(tree, nm, target_depth=3)

    # fallback flags: c falls back when no SL has any CG-level children;
    # b falls back when no CG has any KL-level children.
    any_cg_split = any(
        sl.get("subgroups") for sl in tree["subgroups"] if sl["label"] != "other"
    )
    any_kl_split = any(
        cg.get("subgroups")
        for sl in tree["subgroups"]
        if sl["label"] != "other"
        for cg in sl.get("subgroups", [])
        if cg["label"] != "other"
    )

    return {
        "strain": strain,
        "Sublineage": sublineage,
        "row_type": row_type,
        "directory_leaf": run["run_name"],
        "n_parts": 1,
        "n_samples": run["n_query"],
        "n_refseq_genomes": run["n_refseq"],
        "shared_genes_f": run["level_f"],
        "shared_genes_e": run["level_e"],
        "shared_genes_d": d_value if not np.isnan(d_value) else run["level_d"],
        "shared_genes_c": c_value if not np.isnan(c_value) else run["level_d"],
        "shared_genes_b": b_value if not np.isnan(b_value) else run["level_d"],
        "shared_genes_a": run["level_a"],
        "fallback_e": run.get("fallback_e", False),
        "fallback_c": not any_cg_split,
        "fallback_b": not any_kl_split,
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

    # Tree structure: root → SL children → CG children → KL children. For KP
    # sublineage runs there is normally one major SL child (the run's own
    # sublineage). For correctness in split runs and edge cases we walk
    # whichever major SL children exist.
    for sl_node in tree["subgroups"]:
        if sl_node["label"] == "other":
            continue  # 'other_SL' bucket isn't a kp_epidemic source
        sl_label = sl_node["label"]
        for cg_node in sl_node.get("subgroups", []):
            if cg_node["label"] == "other":
                continue  # 'other_CG' within an SL isn't a kp_epidemic row
            path = (sl_label, cg_node["label"])
            if path not in nm:
                continue

            # level b for this CG: weighted mean across its CG/KL grandchildren
            # (incl. 'other_KL'); fall back to the CG's own best_shared if no
            # K-locus split was possible.
            if cg_node.get("subgroups"):
                grandchild_pairs = [
                    (nm[path + (gc["label"],)]["n"], nm[path + (gc["label"],)]["best_shared"])
                    for gc in cg_node["subgroups"]
                    if path + (gc["label"],) in nm
                ]
                b_value = _weighted_mean(grandchild_pairs)
                fallback_b = False
            else:
                b_value = nm[path]["best_shared"]
                fallback_b = True

            # Resolve a per-CG Sublineage label: most common Sublineage among
            # the CG's members (handles split runs where a CG can carry its
            # parent SL). Falls back to the run's sublineage label if missing.
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
                    "shared_genes_f": nm[path]["level_f"],
                    "shared_genes_e": nm[path]["level_e"],
                    "shared_genes_d": nm[path]["level_d"],
                    "shared_genes_c": nm[path]["best_shared"],
                    "shared_genes_b": b_value,
                    "shared_genes_a": nm[path]["level_a"],
                    "fallback_e": run.get("fallback_e", False),
                    "fallback_c": False,
                    "fallback_b": fallback_b,
                }
            )
    return rows


# -----------------------------------------------------------------------------
# Main table builder
# -----------------------------------------------------------------------------
def _resolve_bucket_ids(
    metadata_df: pd.DataFrame,
    bucket_tsv: str | os.PathLike | None,
) -> tuple[set[str], str]:
    """Return (bucket_ids, source_label). Falls back to is_mgh78578 alone."""
    if bucket_tsv is not None and os.path.isfile(str(bucket_tsv)):
        ids = set(
            pd.read_csv(bucket_tsv, sep="\t")["Sample"].astype(str)
        )
        return ids, f"file:{bucket_tsv}"
    if "is_mgh78578" in metadata_df.columns:
        ids = set(
            metadata_df.loc[
                metadata_df["is_mgh78578"].fillna(False).astype(bool), "Sample"
            ].astype(str)
        )
        return ids, "fallback:is_mgh78578"
    return set(), "fallback:none"


def _aggregate_best_e_ref_per_species(
    run_results: dict[str, dict],
) -> tuple[dict[str | None, str | None], list[dict]]:
    """Cross-run species-level aggregation of bucket-ref scores.

    For each ``query_species``, computes the n_query-weighted mean of
    ``bucket_per_run_means[ref]`` over the runs of that species, then picks
    the ref with the highest weighted mean as the species's best e ref.

    Returns (best_e_ref_per_species, audit_rows). ``audit_rows`` is a list of
    {species, best_ref, weighted_mean, n_runs, n_candidate_refs} dicts for
    writing to ``best_e_ref_per_species.tsv``.
    """
    from collections import defaultdict

    runs_by_species: dict[str | None, list[str]] = defaultdict(list)
    for name, run in run_results.items():
        runs_by_species[run.get("query_species")].append(name)

    best_e_ref_for_species: dict[str | None, str | None] = {}
    audit: list[dict] = []
    for species, names in runs_by_species.items():
        candidate_refs: set[str] = set()
        for name in names:
            candidate_refs |= set(run_results[name]["bucket_per_run_means"].keys())
        weighted: dict[str, float] = {}
        for ref in candidate_refs:
            total_w, total_wv = 0.0, 0.0
            for name in names:
                run = run_results[name]
                v = run["bucket_per_run_means"].get(ref, float("nan"))
                if not np.isnan(v):
                    w = float(run["n_query"])
                    total_w += w
                    total_wv += w * v
            if total_w > 0:
                weighted[ref] = total_wv / total_w
        best_ref = max(weighted, key=weighted.get) if weighted else None
        best_e_ref_for_species[species] = best_ref
        audit.append(
            {
                "species": species if species is not None else "(unknown)",
                "best_e_ref": best_ref,
                "weighted_mean_shared_genes": (
                    weighted[best_ref] if best_ref is not None else float("nan")
                ),
                "n_runs": len(names),
                "n_candidate_refs": len(weighted),
            }
        )
        _tslog(
            f"best_e_ref[{species}] = {best_ref}  "
            f"(weighted_mean={weighted.get(best_ref, float('nan')):.2f}; "
            f"runs={len(names)}, candidate_refs={len(weighted)})"
        )
    return best_e_ref_for_species, audit


def _fill_level_e_per_run(
    run: dict,
    best_e_ref_for_species: dict[str | None, str | None],
) -> None:
    """Resolve per-sample-level e for one run, then walk the tree updating
    ``run['node_metrics'][path]['level_e']`` and run-level ``level_e`` /
    ``fallback_e`` / ``best_e_ref`` fields."""
    species = run.get("query_species")
    best_ref = best_e_ref_for_species.get(species)
    bucket_ids = run["bucket_ref_ids_in_run"]
    if best_ref is not None and best_ref in bucket_ids:
        ref_idx = bucket_ids.index(best_ref)
        per_sample_e = run["bucket_shared"][ref_idx, :]
        run["fallback_e"] = False
        run["best_e_ref"] = best_ref
    else:
        per_sample_e = run["per_sample_f"]
        run["fallback_e"] = True
        run["best_e_ref"] = None
    run["level_e"] = float(np.nanmean(per_sample_e))
    run["per_sample_e"] = np.asarray(per_sample_e)

    query_ids = run["query_ids"]
    id_to_idx = {sid: i for i, sid in enumerate(query_ids)}
    nm = run["node_metrics"]

    def _walk(node: dict, path: tuple[str, ...]) -> None:
        if path in nm:
            members = node["members"]
            mask_idx = [id_to_idx[m] for m in members if m in id_to_idx]
            if mask_idx:
                nm[path]["level_e"] = float(np.nanmean(per_sample_e[mask_idx]))
        for child in node.get("subgroups", []):
            _walk(child, path + (child["label"],))

    _walk(run["tree"], ())


def build_reference_assignment_table(run_results: dict[str, dict]) -> pd.DataFrame:
    """Build one row per (run, query sample) of best ref + shared count per level.

    Emits the best reference genome assigned at every granularity level, plus
    the gene count shared with it.

    Levels mirror the granularity table: ``f`` = mgh78578, ``e`` = best
    same-species bucket ref, ``d`` = best single ref over the whole run (the
    "SL-level" reference for kp_sublineage runs), ``c`` = best ref for the
    sample's CG, ``b`` = best ref for the sample's CG/K-locus subgroup,
    ``a`` = per-sample best ref. ``ref_*`` columns hold the reference Sample
    ID; ``shared_*`` columns hold the gene count shared with it.

    A sample can appear in more than one Panaroo run; the ``run`` column
    disambiguates. ``_fill_level_e_per_run`` must have run first (it sets
    ``best_e_ref`` / ``per_sample_e``).
    """

    def _count(v: float | None) -> int | None:
        if v is None:
            return None
        fv = float(v)
        return None if np.isnan(fv) else int(round(fv))

    rows: list[dict] = []
    for name, run in run_results.items():
        ref_ids = run["ref_ids"]
        qids = run["query_ids"]
        species = run.get("query_species")
        mgh_id = run.get("mgh_ref_id")
        best_e = run.get("best_e_ref")
        ref_e_id = best_e if best_e is not None else mgh_id
        ref_d_id = ref_ids[run["best_run_ref"]]
        a_idx = run["per_sample_a_idx"]
        c_idx = run["per_sample_c_idx"]
        b_idx = run["per_sample_b_idx"]
        psf = run["per_sample_f"]
        pse = run.get("per_sample_e")
        psd = run["per_sample_d"]
        psa = run["per_sample_a"]
        psc = run["per_sample_c"]
        psb = run["per_sample_b"]
        for i, sid in enumerate(qids):
            rows.append(
                {
                    "Sample": sid,
                    "run": name,
                    "species": species,
                    "ref_f": mgh_id,
                    "shared_f": _count(psf[i]),
                    "ref_e": ref_e_id,
                    "shared_e": _count(pse[i]) if pse is not None else None,
                    "ref_d": ref_d_id,
                    "shared_d": _count(psd[i]),
                    "ref_c": ref_ids[int(c_idx[i])],
                    "shared_c": _count(psc[i]),
                    "ref_b": ref_ids[int(b_idx[i])],
                    "shared_b": _count(psb[i]),
                    "ref_a": ref_ids[int(a_idx[i])],
                    "shared_a": _count(psa[i]),
                }
            )
    return pd.DataFrame(rows)


def compute_granularity_table(
    panaroo_run_root: str,
    metadata_df: pd.DataFrame,
    min_group_size: int = 50,
    workers: int = 1,
    bucket_tsv: str | os.PathLike | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the granularity table + best_e_ref audit by walking Panaroo runs.

    Returns ``(granularity_df, best_e_ref_summary_df, ref_assignment_df)``. The
    summary df has one row per query species with the bucket reference that
    gave the highest n_query-weighted mean shared-gene count across that
    species's runs ("which single ref should we use for this species?"). The
    ref-assignment df has one row per (run, query sample) with the best
    reference + shared-gene count at every level (see
    ``build_reference_assignment_table``).

    No longer depends on per-run detail TSVs from gpa_distances_batch_runs.sh.
    """
    _tslog("=== Computing granularity table ===")
    runs = find_panaroo_runs(panaroo_run_root)
    _tslog(f"Discovered {len(runs)} Panaroo runs")

    bucket_ids, bucket_source = _resolve_bucket_ids(metadata_df, bucket_tsv)
    _tslog(f"Reference bucket: n={len(bucket_ids)} ({bucket_source})")

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
                    process_panaroo_run, rd, metadata_df, min_group_size, use_kpsc, bucket_ids
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
            res = process_panaroo_run(
                rd, metadata_df, min_group_size, use_kpsc, bucket_ids
            )
            if res is not None:
                run_results[name] = res
    _tslog(f"Processed {len(run_results)} runs successfully")

    if not run_results:
        return (
            pd.DataFrame(),
            pd.DataFrame(
                columns=["species", "best_e_ref", "weighted_mean_shared_genes",
                         "n_runs", "n_candidate_refs"]
            ),
            pd.DataFrame(),
        )

    # Cross-run species-level aggregation: pick best_e_ref per species, then
    # back-fill level_e onto every run's node_metrics.
    _tslog("=== Cross-run aggregation: picking best e ref per species ===")
    best_e_ref_for_species, audit_rows = _aggregate_best_e_ref_per_species(run_results)
    for run in run_results.values():
        _fill_level_e_per_run(run, best_e_ref_for_species)
    best_e_ref_df = pd.DataFrame(audit_rows)
    ref_assignment_df = build_reference_assignment_table(run_results)

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

    # Aggregate split-run parts: kp_epidemic CG rows and kp_epidemic_sl rows can
    # span multiple parts (e.g. SL15_part_0 + SL15_part_1) — collapse to one
    # row per unique (strain, Sublineage, row_type) by n_samples-weighted mean.
    _tslog(f"Pre-aggregation rows: {len(result)}")
    result = _aggregate_split_runs(result)
    _tslog(f"Post-aggregation rows: {len(result)}")

    # Compute gain columns (consecutive-level gains f→e→d→c→b→a)
    result["gain_f_to_e"] = result["shared_genes_e"] - result["shared_genes_f"]
    result["gain_e_to_d"] = result["shared_genes_d"] - result["shared_genes_e"]
    result["gain_d_to_c"] = result["shared_genes_c"] - result["shared_genes_d"]
    result["gain_c_to_b"] = result["shared_genes_b"] - result["shared_genes_c"]
    result["gain_b_to_a"] = result["shared_genes_a"] - result["shared_genes_b"]
    eps = 1e-9
    result["pct_gain_f_to_e"] = 100 * result["gain_f_to_e"] / (result["shared_genes_f"] + eps)
    result["pct_gain_e_to_d"] = 100 * result["gain_e_to_d"] / (result["shared_genes_e"] + eps)
    result["pct_gain_d_to_c"] = 100 * result["gain_d_to_c"] / (result["shared_genes_d"] + eps)
    result["pct_gain_c_to_b"] = (
        100 * result["gain_c_to_b"] / (result["shared_genes_c"] + eps)
    )
    result["pct_gain_b_to_a"] = (
        100 * result["gain_b_to_a"] / (result["shared_genes_b"] + eps)
    )

    output_cols = [
        "strain",
        "Sublineage",
        "row_type",
        "directory_leaf",
        "n_parts",
        "n_samples",
        "n_refseq_genomes",
        "shared_genes_f",
        "shared_genes_e",
        "shared_genes_d",
        "shared_genes_c",
        "shared_genes_b",
        "shared_genes_a",
        "fallback_e",
        "fallback_c",
        "fallback_b",
        "gain_f_to_e",
        "gain_e_to_d",
        "gain_d_to_c",
        "gain_c_to_b",
        "gain_b_to_a",
        "pct_gain_f_to_e",
        "pct_gain_e_to_d",
        "pct_gain_d_to_c",
        "pct_gain_c_to_b",
        "pct_gain_b_to_a",
    ]
    result = result[[c for c in output_cols if c in result.columns]]
    _tslog(f"Granularity table: {len(result)} rows")
    return result, best_e_ref_df, ref_assignment_df


def _aggregate_split_runs(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multiple Panaroo-run parts of the same (strain, Sublineage, row_type)
    into one row by n_samples-weighted mean of all numeric columns."""
    weighted_cols = [
        "shared_genes_f",
        "shared_genes_e",
        "shared_genes_d",
        "shared_genes_c",
        "shared_genes_b",
        "shared_genes_a",
        "n_refseq_genomes",
    ]

    def _agg(grp: pd.DataFrame) -> pd.Series:
        w = grp["n_samples"]
        out: dict = {
            "n_samples": float(w.sum()),
            "n_parts": int(len(grp)),
            "directory_leaf": ";".join(sorted(set(grp["directory_leaf"]))),
            "fallback_e": bool(grp["fallback_e"].any())
            if "fallback_e" in grp.columns else False,
            "fallback_c": bool(grp["fallback_c"].any()),
            "fallback_b": bool(grp["fallback_b"].any()),
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
    for level in ["f", "e", "d", "c", "b", "a"]:
        col = f"shared_genes_{level}"
        if col in granularity_df.columns:
            valid = granularity_df[col].dropna()
            if not valid.empty:
                stats[f"mean_{level}"] = float(valid.mean())
                stats[f"median_{level}"] = float(valid.median())
                stats[f"std_{level}"] = float(valid.std())
                stats[f"min_{level}"] = float(valid.min())
                stats[f"max_{level}"] = float(valid.max())
    if "shared_genes_c" in granularity_df.columns:
        stats["pct_c_gt_d"] = float(
            (granularity_df["shared_genes_c"] > granularity_df["shared_genes_d"]).mean() * 100
        )
    if "shared_genes_b" in granularity_df.columns:
        stats["pct_b_gt_c"] = float(
            (granularity_df["shared_genes_b"] > granularity_df["shared_genes_c"]).mean() * 100
        )
    if "shared_genes_a" in granularity_df.columns:
        valid_a = granularity_df[granularity_df["shared_genes_a"].notna()]
        if not valid_a.empty:
            stats["pct_a_gt_b"] = float(
                (valid_a["shared_genes_a"] > valid_a["shared_genes_b"]).mean() * 100
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
    parser.add_argument(
        "--reference-bucket-tsv",
        default=None,
        help="Path to reference_bucket.tsv (Sample IDs to use as the level-e "
        "comparison pool). Defaults to "
        "<DATA_ROOT>/final/reference_bucket.tsv if present; else falls back "
        "to is_mgh78578 alone.",
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

        # Default bucket TSV: <DATA_ROOT>/final/reference_bucket.tsv (sibling
        # of the metadata file's parent). The user can override with
        # --reference-bucket-tsv. If neither is present, the granularity
        # table-builder falls back to is_mgh78578 alone.
        bucket_tsv = args.reference_bucket_tsv
        if bucket_tsv is None:
            default_bucket = os.path.join(
                os.path.dirname(args.metadata), "reference_bucket.tsv"
            )
            if os.path.isfile(default_bucket):
                bucket_tsv = default_bucket

        # Optional run-count cap for testing
        if args.test_n_runs:
            all_runs = find_panaroo_runs(args.data_dir)[: args.test_n_runs]
            _tslog(f"Test mode: limiting to first {args.test_n_runs} runs: {all_runs}")
            # Build a temporary symlink-free filtered tree by filtering at process time
            # (cheaper: just patch find_panaroo_runs via module attribute)
            import bac_panaroo.tl.gpa_reference_granularity as _self_mod

            _orig = _self_mod.find_panaroo_runs
            _self_mod.find_panaroo_runs = lambda root: all_runs  # type: ignore[assignment]
            try:
                granularity_df, best_e_ref_df, ref_assignment_df = (
                    compute_granularity_table(
                        args.data_dir,
                        metadata_df,
                        min_group_size=args.min_group_size,
                        workers=args.workers,
                        bucket_tsv=bucket_tsv,
                    )
                )
            finally:
                _self_mod.find_panaroo_runs = _orig  # type: ignore[assignment]
        else:
            granularity_df, best_e_ref_df, ref_assignment_df = (
                compute_granularity_table(
                    args.data_dir,
                    metadata_df,
                    min_group_size=args.min_group_size,
                    workers=args.workers,
                    bucket_tsv=bucket_tsv,
                )
            )

        if granularity_df.empty:
            _tslog("No granularity rows produced; skipping outputs")
        else:
            table_path = os.path.join(args.out_dir, "granularity_table.tsv")
            granularity_df.to_csv(table_path, sep="\t", index=False)
            _tslog(f"Wrote granularity table: {table_path}")

            best_e_path = os.path.join(args.out_dir, "best_e_ref_per_species.tsv")
            best_e_ref_df.to_csv(best_e_path, sep="\t", index=False)
            _tslog(f"Wrote best-e-ref audit: {best_e_path}")

            ref_assign_path = os.path.join(
                args.out_dir, "best_reference_per_sample.csv"
            )
            ref_assignment_df.to_csv(ref_assign_path, index=False)
            _tslog(
                f"Wrote per-sample best-reference table "
                f"({len(ref_assignment_df)} rows): {ref_assign_path}"
            )

            summary_stats = compute_summary_stats(granularity_df)
            summary_df = pd.DataFrame(
                [{"metric": k, "value": v} for k, v in sorted(summary_stats.items())]
            )
            summary_path = os.path.join(args.out_dir, "granularity_summary.tsv")
            summary_df.to_csv(summary_path, sep="\t", index=False)
            _tslog(f"Wrote summary: {summary_path}")

            try:
                from bac_panaroo.pl.granularity_lollipop import plot_granularity_lollipop

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
                    "Generating SL lollipop: highlight epidemic SLs with d→c gain > 20..."
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
