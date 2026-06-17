"""Quantify how well variant-call vs Panaroo-GPA structure recovers Clonal Group, per group.

For each comparison group with both a persisted variant run (:mod:`sublineage_variant_umap`)
and a persisted GPA run (``gpa_distances_single_group --persist-embedding``), this joins the
two per-sample embeddings on ``Sample`` and scores each modality's recovery of Clonal Group:

- **ARI / AMI** of (Leiden clusters vs Clonal Group) — graph-clustering agreement.
- **kNN label-purity** of Clonal Group on the 2-D UMAP — mean fraction of each sample's
  ``k`` nearest neighbors that share its Clonal Group (the visual companion to the plots).

The GPA embedding is keyed by Panaroo label; it is mapped back to metadata ``Sample`` via the
run's ``panaroo_genomes.tsv`` (a dual SR+LRA isolate is deduped to one ``Sample``, preferring
the ``Sample``-keyed long-read row).

Output: ``variant_vs_gpa_cg_recovery.tsv`` (one row per group, carrying the group-composition
annotations + the strict-vs-control ``group_type`` so the split is a post-hoc filter on the
table) and per-group side-by-side UMAP PNGs (variant | GPA, both colored by Clonal Group).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score
from sklearn.neighbors import NearestNeighbors

from bac_panaroo.gpa_analysis.gpa_distances_single_group import _compute_k
from bac_phylogeny.gpa_run_groups import CG_COL

PANAROO_GENOMES_FILENAME = "panaroo_genomes.tsv"
GPA_ANALYSIS_SUBPATH = "analysis/GPA_reference_genome"
RARE_LABEL = "rare"


def knn_label_purity(coords: np.ndarray, labels: np.ndarray, k: int) -> float:
    """Mean fraction of each point's ``k`` nearest neighbors (in ``coords``) sharing its label.

    Self is excluded. Returns ``nan`` if fewer than ``k + 1`` points.
    """
    n = coords.shape[0]
    if n < k + 1:
        return float("nan")
    nn = NearestNeighbors(n_neighbors=k + 1).fit(coords)
    idx = nn.kneighbors(coords, return_distance=False)[:, 1:]  # drop self
    same = labels[idx] == labels[:, None]
    return float(same.mean())


def _detect_leiden_col(df: pd.DataFrame, prefix: str) -> str:
    cols = [c for c in df.columns if str(c).startswith(prefix)]
    if not cols:
        raise SystemExit(f"No '{prefix}*' column in labels frame (have: {list(df.columns)})")
    return cols[0]


def _load_variant(variant_dir: Path, group: str) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    labels = pd.read_csv(variant_dir / f"{group}_variant_labels.tsv", sep="\t").set_index("Sample")
    labels.index = labels.index.astype(str)
    npz = np.load(variant_dir / f"{group}_variant_umap.npz", allow_pickle=True)
    coords = dict(zip(npz["samples"].astype(str), npz["coords"], strict=True))
    return labels, coords


def _load_gpa(run_dir: Path, group: str, subpath: str) -> tuple[pd.DataFrame, dict[str, np.ndarray]] | None:
    adir = run_dir / subpath
    lab_path = adir / f"gpa_labels_{group}.tsv"
    npz_path = adir / f"gpa_umap_embedding_{group}.npz"
    if not (lab_path.is_file() and npz_path.is_file()):
        return None

    # Map each Panaroo label -> metadata Sample; a dual SR+LRA isolate has two labels for one
    # Sample, so we dedup preferring the Sample-keyed (long-read) row/coordinate.
    g = pd.read_csv(run_dir / PANAROO_GENOMES_FILENAME, sep="\t")
    lab2samp = dict(zip(g["panaroo_label"].astype(str), g["Sample"].astype(str), strict=False))

    labels = pd.read_csv(lab_path, sep="\t")
    labels = labels.rename(columns={labels.columns[0]: "panaroo_label"})  # written with index_label
    labels["panaroo_label"] = labels["panaroo_label"].astype(str)
    labels["Sample"] = labels["panaroo_label"].map(lab2samp)
    labels = labels.dropna(subset=["Sample"])
    labels["_pref"] = (labels["panaroo_label"] == labels["Sample"]).astype(int)
    labels = labels.sort_values("_pref", ascending=False).drop_duplicates(subset=["Sample"], keep="first")

    npz = np.load(npz_path, allow_pickle=True)
    coords: dict[str, np.ndarray] = {}
    for plabel, xy in zip(npz["samples"].astype(str), npz["coords"], strict=True):
        samp = lab2samp.get(plabel)
        if samp is None:
            continue
        if samp not in coords or plabel == samp:  # prefer the Sample-keyed (LRA) coordinate
            coords[samp] = xy
    return labels.set_index("Sample"), coords


def cg_recovery_row(
    group: str,
    variant_labels: pd.DataFrame,
    variant_coords: dict[str, np.ndarray],
    gpa_labels: pd.DataFrame,
    gpa_coords: dict[str, np.ndarray],
) -> dict[str, object]:
    """Compute the paired CG-recovery metrics for one group over its joined samples."""
    v_leiden = _detect_leiden_col(variant_labels, "variant_leiden")
    g_leiden = _detect_leiden_col(gpa_labels, "gpa_leiden")

    shared = [s for s in variant_labels.index if s in gpa_labels.index and s in variant_coords and s in gpa_coords]
    cg = variant_labels.loc[shared, CG_COL].astype("object")
    keep = cg.notna() & (cg.astype(str) != "nan") & (cg.astype(str) != "")
    used = [s for s, k in zip(shared, keep, strict=True) if k]
    n_used = len(used)
    if n_used < 3:
        return {"group": group, "n_joined": len(shared), "n_used": n_used}

    cg_arr = variant_labels.loc[used, CG_COL].astype(str).to_numpy()
    v_lab = variant_labels.loc[used, v_leiden].astype(str).to_numpy()
    g_lab = gpa_labels.loc[used, g_leiden].astype(str).to_numpy()
    v_xy = np.vstack([variant_coords[s] for s in used])
    g_xy = np.vstack([gpa_coords[s] for s in used])
    k = _compute_k(n_used)

    var_ari = adjusted_rand_score(cg_arr, v_lab)
    gpa_ari = adjusted_rand_score(cg_arr, g_lab)
    var_ami = adjusted_mutual_info_score(cg_arr, v_lab)
    gpa_ami = adjusted_mutual_info_score(cg_arr, g_lab)
    var_pur = knn_label_purity(v_xy, cg_arr, k)
    gpa_pur = knn_label_purity(g_xy, cg_arr, k)
    return {
        "group": group,
        "n_joined": len(shared),
        "n_used": n_used,
        "variant_ARI_vs_CG": round(var_ari, 4),
        "gpa_ARI_vs_CG": round(gpa_ari, 4),
        "delta_ARI_gpa_minus_variant": round(gpa_ari - var_ari, 4),
        "variant_AMI_vs_CG": round(var_ami, 4),
        "gpa_AMI_vs_CG": round(gpa_ami, 4),
        "delta_AMI_gpa_minus_variant": round(gpa_ami - var_ami, 4),
        "variant_knn_purity": round(var_pur, 4),
        "gpa_knn_purity": round(gpa_pur, 4),
        "delta_purity_gpa_minus_variant": round(gpa_pur - var_pur, 4),
    }


def _shared_colors(labels_a: np.ndarray, labels_b: np.ndarray, top_n: int) -> dict[str, tuple]:
    """One color map over the top-N Clonal Groups by combined frequency (rest -> grey)."""
    s = pd.Series(np.concatenate([labels_a, labels_b])).astype(str)
    s = s[(s != "nan") & (s != "")]
    top = [str(c) for c in s.value_counts().index[:top_n]]
    cmap = plt.get_cmap("tab10" if len(top) <= 10 else "tab20")
    return {cat: cmap(i % cmap.N) for i, cat in enumerate(top)}


def _panel(ax: plt.Axes, coords: np.ndarray, labels: np.ndarray, colors: dict[str, tuple], title: str) -> None:
    lab = pd.Series(labels).astype(str).to_numpy()
    rare = np.array([c not in colors for c in lab])
    if rare.any():
        ax.scatter(coords[rare, 0], coords[rare, 1], s=4, alpha=0.5, color="0.7", linewidths=0, rasterized=True)
    for cat, col in colors.items():
        m = lab == cat
        if m.any():
            ax.scatter(coords[m, 0], coords[m, 1], s=6, alpha=0.85, color=col, linewidths=0, rasterized=True, label=cat)
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    ax.set_title(title)


def plot_side_by_side(
    group: str,
    variant_coords: dict[str, np.ndarray],
    variant_cg: pd.Series,
    gpa_coords: dict[str, np.ndarray],
    gpa_cg: pd.Series,
    out_path: Path,
    top_n: int = 12,
) -> None:
    """Two panels sharing a Clonal-Group color map: variant UMAP | GPA UMAP."""
    v_s = [s for s in variant_cg.index if s in variant_coords]
    g_s = [s for s in gpa_cg.index if s in gpa_coords]
    v_xy = np.vstack([variant_coords[s] for s in v_s])
    g_xy = np.vstack([gpa_coords[s] for s in g_s])
    v_lab = variant_cg.loc[v_s].astype(str).to_numpy()
    g_lab = gpa_cg.loc[g_s].astype(str).to_numpy()
    colors = _shared_colors(v_lab, g_lab, top_n)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    _panel(axes[0], v_xy, v_lab, colors, f"Variant — {group} (n={len(v_s)})")
    _panel(axes[1], g_xy, g_lab, colors, f"GPA — {group} (n={len(g_s)})")
    handles, labels_ = axes[1].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels_, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8, markerscale=2, title="Clonal Group")
    fig.suptitle(f"Clonal-Group recovery: variant vs GPA — {group}")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}")


def run(
    *,
    groups_tsv: Path,
    variant_dir: Path,
    out_dir: Path,
    gpa_subpath: str,
) -> None:
    """Score every group with both modalities persisted; write the recovery TSV + plots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = pd.read_csv(groups_tsv, sep="\t")
    ann_cols = [c for c in ("group_type", "sublineage", "n_samples", "n_cg_total", "n_large_cgs",
                            "largest_cg_frac", "n_outside_largest_cg") if c in groups.columns]

    rows: list[dict[str, object]] = []
    for _, grow in groups.iterrows():
        group = str(grow["group"])
        run_dir = Path(str(grow["run_dir"]))
        vfiles = (variant_dir / f"{group}_variant_labels.tsv", variant_dir / f"{group}_variant_umap.npz")
        if not all(p.is_file() for p in vfiles):
            print(f"[{group}] skip: variant artifacts missing")
            continue
        gpa = _load_gpa(run_dir, group, gpa_subpath)
        if gpa is None:
            print(f"[{group}] skip: GPA embedding not persisted (run gpa_distances_single_group --persist-embedding)")
            continue
        gpa_labels, gpa_coords = gpa
        variant_labels, variant_coords = _load_variant(variant_dir, group)

        row = cg_recovery_row(group, variant_labels, variant_coords, gpa_labels, gpa_coords)
        row.update({c: grow[c] for c in ann_cols})
        rows.append(row)
        print(f"[{group}] n_used={row.get('n_used')} "
              f"ARI variant={row.get('variant_ARI_vs_CG')} gpa={row.get('gpa_ARI_vs_CG')}")

        plot_side_by_side(
            group, variant_coords, variant_labels[CG_COL], gpa_coords, gpa_labels[CG_COL],
            out_dir / f"{group}_variant_vs_gpa_by_cg.png",
        )

    if not rows:
        raise SystemExit("No groups had both variant and GPA artifacts present.")
    out = pd.DataFrame(rows)
    front = ["group", *ann_cols, "n_joined", "n_used"]
    out = out[[*front, *[c for c in out.columns if c not in front]]]
    out_path = out_dir / "variant_vs_gpa_cg_recovery.tsv"
    out.to_csv(out_path, sep="\t", index=False)
    print(f"\nwrote {out_path}  ({len(out)} groups)")
    if "group_type" in out.columns and "delta_ARI_gpa_minus_variant" in out.columns:
        print("\nmean delta (gpa - variant) by group_type:")
        print(out.groupby("group_type")[[
            c for c in out.columns if c.startswith("delta_")
        ]].mean().round(4).to_string())


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--groups-tsv", type=Path, required=True, help="groups.tsv from gpa_run_groups (has group + run_dir + annotations).")
    p.add_argument("--variant-dir", type=Path, required=True, help="Dir with <group>_variant_{labels.tsv,umap.npz}.")
    p.add_argument("--out-dir", type=Path, required=True, help="Output dir for the recovery TSV + side-by-side plots.")
    p.add_argument("--gpa-subpath", default=GPA_ANALYSIS_SUBPATH, help=f"GPA analysis dir relative to a run dir (default: {GPA_ANALYSIS_SUBPATH}).")
    args = p.parse_args(argv)

    run(groups_tsv=args.groups_tsv, variant_dir=args.variant_dir, out_dir=args.out_dir, gpa_subpath=args.gpa_subpath)


if __name__ == "__main__":
    main()
