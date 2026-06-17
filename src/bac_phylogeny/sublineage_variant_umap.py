"""Per-group variant UMAP + Leiden, method-matched to the Panaroo-GPA pipeline.

For one comparison group (an SL-level GPA run, e.g. ``SL147_part_0``) this rebuilds a binary
variant presence matrix **from the shared per-sample cache** for that group's exact sample set,
applies a *within-group* frequency filter, and embeds it with the identical scanpy machinery
``bac_panaroo`` uses for GPA — ``sc.pp.neighbors(metric="jaccard")`` → ``sc.tl.umap`` →
``sc.tl.leiden(0.3)`` → small-cluster merge — so the variant and GPA clusterings are directly
comparable.

Why rebuild per group rather than slice a global matrix: a 50-sample Clonal Group is <0.1 % of
a large Sublineage, so a global frequency cap would drop exactly the CG-defining variants this
comparison tests. Rebuilding from the cache for the group's samples (a few thousand at most)
preserves them and is cheap.

Outputs (per group): ``<group>_variant_umap.npz`` (coords + samples), ``<group>_variant_labels.tsv``
(Leiden label + Clonal group + Sublineage, keyed by ``Sample``), and UMAP PNGs colored by
Clonal group and by Leiden cluster.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anndata as ad
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bac_panaroo.gpa_analysis.gpa_distances_single_group import _compute_k, _merge_small_clusters
from bac_phylogeny.build_variant_matrix import _present_samples, build_presence_matrix
from bac_phylogeny.gpa_run_groups import CG_COL, METADATA_V2_DEFAULT, SL_COL

LEIDEN_RESOLUTION = 0.3
LEIDEN_KEY = f"variant_leiden_r{LEIDEN_RESOLUTION}"
RARE_LABEL = "rare"


def build_group_adata(
    samples: list[str],
    meta: pd.DataFrame,
    cache_dir: Path,
    min_freq: float,
    n_jobs: int,
) -> ad.AnnData:
    """Build a within-group-filtered binary variant AnnData for ``samples``.

    The matrix is rebuilt from the per-sample cache (rows = present samples, cols = loci).
    Loci are kept when present in ``>= max(2, ceil(min_freq * n))`` samples and **not** fixed
    across the whole group (dropped if present in all ``n`` samples — group-fixed loci carry no
    within-group structure). ``X`` is a binary ``uint8`` CSR (``obs`` carries the metadata).
    """
    present, paths, missing = _present_samples(samples, cache_dir)
    if missing:
        print(f"  cache missing for {len(missing)}/{len(samples)} samples (excluded)")
    if not present:
        raise SystemExit("No group samples have a cache file — run extract_sample_loci first.")

    x, keys = build_presence_matrix(paths, n_jobs)
    n = len(present)
    from math import ceil

    min_count = max(2, ceil(min_freq * n))
    freq = np.asarray(x.sum(axis=0)).ravel()
    keep = (freq >= min_count) & (freq < n)
    xf = x[:, keep].tocsr()
    print(f"  loci: {x.shape[1]} -> {xf.shape[1]} (>= {min_count} and < {n} of {n} samples)")

    obs = meta.reindex(pd.Index(present, dtype=str))
    obs.index.name = "Sample"
    adata = ad.AnnData(
        X=xf.astype(np.uint8),
        obs=obs,
        var=pd.DataFrame(index=keys[keep].astype(str)),
    )
    return adata


def embed_and_cluster(adata: ad.AnnData, *, resolution: float = LEIDEN_RESOLUTION, key: str = LEIDEN_KEY) -> ad.AnnData:
    """Run the GPA-matched scanpy neighbors/UMAP/Leiden/merge in place; return ``adata``."""
    import scanpy as sc

    sc.settings.verbosity = 0
    n = adata.n_obs
    k = _compute_k(n)
    merge_min_size = max(10, int(0.01 * n))
    print(f"  knn: n={n} k={k}; merge_min_size={merge_min_size}")
    try:
        sc.pp.neighbors(adata, n_neighbors=k, metric="jaccard", use_rep="X")
    except Exception as exc:  # noqa: BLE001 — mirror GPA's dense-sklearn fallback
        print(f"  knn: sparse Jaccard failed ({exc}); retrying dense boolean + sklearn")
        adata.obsm["X_jaccard_dense"] = adata.X.toarray().astype(bool, copy=False)
        sc.pp.neighbors(adata, n_neighbors=k, metric="jaccard", use_rep="X_jaccard_dense", transformer="sklearn")
    sc.tl.umap(adata)
    sc.tl.leiden(adata, resolution=resolution, key_added=key)
    raw = adata.obs[key].value_counts()
    n_small, n_reass, n_remain = _merge_small_clusters(adata, key, merge_min_size)
    print(f"  leiden: {len(raw)} raw clusters; merged {n_small} small (reassigned {n_reass}, {n_remain} remain)")
    return adata


def _bucket_top(labels: np.ndarray, top_n: int) -> tuple[np.ndarray, list[str]]:
    """Collapse all but the ``top_n`` most frequent labels into ``RARE_LABEL`` (NaN -> rare)."""
    s = pd.Series(labels).astype("object")
    s = s.where(s.notna() & (s.astype(str) != "nan") & (s.astype(str) != ""), other=RARE_LABEL)
    counts = s[s != RARE_LABEL].value_counts()
    top = [str(c) for c in counts.index[:top_n]]
    return s.where(s.isin(top), other=RARE_LABEL).to_numpy(), top


def plot_umap_by_category(coords: np.ndarray, labels: np.ndarray, out_path: Path, title: str, top_n: int = 20) -> None:
    """Scatter the embedding colored by the top-N categories (rest collapsed to grey)."""
    bucketed, top = _bucket_top(labels, top_n)
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    rare = bucketed == RARE_LABEL
    if rare.any():
        ax.scatter(coords[rare, 0], coords[rare, 1], s=4, alpha=0.5, color="0.7",
                   linewidths=0, rasterized=True, label=f"{RARE_LABEL} (n={int(rare.sum())})")
    cmap = plt.get_cmap("tab10" if len(top) <= 10 else "tab20")
    for i, cat in enumerate(top):
        m = bucketed == cat
        ax.scatter(coords[m, 0], coords[m, 1], s=6, alpha=0.85, color=cmap(i % cmap.N),
                   linewidths=0, rasterized=True, label=f"{cat} (n={int(m.sum())})")
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    ax.set_title(title)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8, framealpha=0.9, markerscale=2)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}")


def _read_group_samples(group_samples_tsv: Path, group: str) -> list[str]:
    df = pd.read_csv(group_samples_tsv, sep="\t")
    sel = df[df["group"].astype(str) == group]
    if sel.empty:
        raise SystemExit(f"Group {group!r} not found in {group_samples_tsv}")
    return sel["Sample"].astype(str).drop_duplicates().tolist()


def run(
    *,
    group: str,
    group_samples_tsv: Path,
    cache_dir: Path,
    metadata_path: Path,
    out_dir: Path,
    min_freq: float,
    n_jobs: int,
) -> None:
    """Embed + cluster one group's variant matrix and persist coords/labels/plots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = _read_group_samples(group_samples_tsv, group)
    meta = pd.read_csv(metadata_path, sep="\t", usecols=["Sample", CG_COL, SL_COL], low_memory=False)
    meta["Sample"] = meta["Sample"].astype(str)
    meta = meta.drop_duplicates(subset=["Sample"]).set_index("Sample")

    print(f"[{group}] {len(samples)} samples")
    adata = build_group_adata(samples, meta, cache_dir, min_freq, n_jobs)
    adata = embed_and_cluster(adata)

    coords = adata.obsm["X_umap"].astype(np.float32)
    np.savez_compressed(
        out_dir / f"{group}_variant_umap.npz",
        coords=coords,
        samples=np.asarray(adata.obs_names, dtype=object),
    )
    labels = adata.obs[[LEIDEN_KEY, CG_COL, SL_COL]].copy()
    labels.to_csv(out_dir / f"{group}_variant_labels.tsv", sep="\t", index_label="Sample")

    plot_umap_by_category(
        coords, adata.obs[CG_COL].to_numpy(), out_dir / f"{group}_variant_umap_by_clonal_group.png",
        f"Variant UMAP — {group} — Clonal Group",
    )
    plot_umap_by_category(
        coords, adata.obs[LEIDEN_KEY].to_numpy(), out_dir / f"{group}_variant_umap_by_leiden.png",
        f"Variant UMAP — {group} — Leiden r={LEIDEN_RESOLUTION}",
    )
    print(f"[{group}] wrote {group}_variant_umap.npz + _variant_labels.tsv + 2 PNGs")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--group", required=True, help="Group name (a row in --group-samples-tsv).")
    p.add_argument("--group-samples-tsv", type=Path, required=True, help="Long-form (group, Sample) from gpa_run_groups.")
    p.add_argument("--cache-dir", type=Path, required=True, help="Shared per-sample locus cache dir.")
    p.add_argument("--metadata", type=Path, default=METADATA_V2_DEFAULT)
    p.add_argument("--out-dir", type=Path, required=True, help="Output dir for coords/labels/plots.")
    p.add_argument("--min-freq", type=float, default=0.001, help="Within-group min locus frequency (default 0.1%%).")
    p.add_argument("--n-jobs", type=int, default=-1, help="Cores for the parallel cache read (-1 = all).")
    args = p.parse_args(argv)

    run(
        group=args.group,
        group_samples_tsv=args.group_samples_tsv,
        cache_dir=args.cache_dir,
        metadata_path=args.metadata,
        out_dir=args.out_dir,
        min_freq=args.min_freq,
        n_jobs=args.n_jobs,
    )


if __name__ == "__main__":
    main()
