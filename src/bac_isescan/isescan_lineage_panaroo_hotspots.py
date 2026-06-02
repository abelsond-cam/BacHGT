"""Per-lineage ISEScan flanking-context → Panaroo cluster hotspot analysis.

For one Panaroo run (lineage, e.g. ``SL39``), restrict ``is_gene_context.tsv.gz``
to that run's genomes, map each IS element's upstream/downstream host gene
(``locus_tag``) to its synteny-aware Panaroo cluster via the run's
``gene_presence_absence.csv``, and test which clusters are flanked by IS far
more often than a uniform-IS null predicts.

Flanking-only by design: the hit gene is mostly the IS's own transposase
(~59% of ``within`` rows), so it is carried through (plus a cheap
``self_transposase`` flag) but not analysed. The recurrence unit is a
``(Panaroo cluster, IS family)`` pair, unordered: each IS contributes a hit to
``cluster(upstream)`` and to ``cluster(downstream)`` independently; recurrence
is the number of distinct lineage genomes with >=1 IS of that family flanked
by that cluster.

The null is uniform over clusters and conditioned on IS family: ``lambda_F``
is driven by each genome's count of family-F IS only, so reported
``enrichment`` is observed genome-recurrence relative to what that family's IS
load predicts (ignores cluster length and core/accessory status).

Each IS carries an ``is_partial`` flag (ISEScan ``type='p'`` — a degraded IS
remnant, i.e. a "scar" of a former full-length element). Partial IS rows are
kept in the annotated TSV and summarised per cluster in the hotspot table as
``n_partial_events``, ``n_genomes_partial`` and ``frac_partial``.

Reading the side counts: ``n_as_upstream`` / ``n_as_downstream`` are by
**contig coordinate**, not biology. Draft assemblers (SPAdes/Unicycler/…) do
not preserve a canonical contig orientation, so a single fixed IS adjacent to
a gene appears as ``upstream`` in some genomes and ``downstream`` in others.
A pair with ``n_as_upstream + n_as_downstream ≈ n_is_events ≈
n_genomes_flanked`` is one ancestral adjacency seen from two orientations;
the side split is noise. Strong one-sided uniformity is the informative
signal; mixed two-sided counts conflate orientation flips, Panaroo paralog
collapse and tandem-IS arrangements — don't treat them as event counts.

If a sibling ``{lineage}_panaroo_nodes_annotate_kleborate.tsv`` (written by
``bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap``) sits in the Panaroo run
folder, its ``virulence_hits`` / ``amr_hits`` / ``amr_classes`` columns are
left-joined onto the hotspot table. Missing file → empty columns.

See :mod:`bac_isescan.isescan_lineage_kleborate_hotspots` for the sibling
view that pivots the same flank events onto Kleborate labels (virulence
genes + AMR drug classes) instead.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_isescan._lineage_hotspot_common import (
    _bh_qvalues,
    _log,
    _poisson_sf,
    family_conditioned_lambda,
    prepare_lineage,
)


def run(
    is_gene_context: Path,
    panaroo_root: Path,
    lineage: str,
    out_dir: Path,
    min_recurrence: int,
    fdr: float,
    include_ref_bucket: bool,
) -> None:
    """Execute the per-(Panaroo cluster, IS family) hotspot analysis."""
    df, long, ann, n_clusters, samples, run_dir = prepare_lineage(
        panaroo_root, lineage, is_gene_context, include_ref_bucket
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    annotated = out_dir / f"{lineage}_is_flank_annotated.tsv"
    df.to_csv(annotated, sep="\t", index=False)
    _log(f"wrote {annotated.name} ({len(df):,} rows)")

    # Recurrence unit: a (Panaroo cluster, IS family) pair.
    keys = ["cluster", "is_family"]
    grp = long.groupby(keys)
    hot = pd.DataFrame(
        {
            "n_genomes_flanked": grp["sample"].nunique(),
            "n_is_events": grp.size(),
            "n_as_upstream": long[long["side"].eq("upstream")].groupby(keys).size(),
            "n_as_downstream": long[long["side"].eq("downstream")].groupby(keys).size(),
            "n_partial_events": grp["is_partial"].sum(),
            "n_genomes_partial": long[long["is_partial"]].groupby(keys)["sample"].nunique(),
        }
    ).fillna({"n_as_upstream": 0, "n_as_downstream": 0, "n_partial_events": 0, "n_genomes_partial": 0})
    hot["frac_partial"] = hot["n_partial_events"] / hot["n_is_events"]
    hot = hot.reset_index()
    hot["annotation"] = hot["cluster"].map(ann)

    # Left-join Kleborate virulence + AMR labels from the Panaroo run folder
    # (written by bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap). Missing file
    # → empty columns, with a log line so the omission is visible.
    kleb_tsv = run_dir / f"{lineage}_panaroo_nodes_annotate_kleborate.tsv"
    if kleb_tsv.exists():
        kleb = pd.read_csv(kleb_tsv, sep="\t", dtype=str).fillna("")
        hot = hot.merge(kleb, on="cluster", how="left")
        for c in ("virulence_hits", "amr_hits", "amr_classes"):
            hot[c] = hot[c].fillna("")
        n_lab = int((hot[["virulence_hits", "amr_hits"]].ne("").any(axis=1)).sum())
        _log(f"joined {kleb_tsv.name}: {n_lab:,} of {len(hot):,} pair-rows have a virulence/AMR label")
    else:
        for c in ("virulence_hits", "amr_hits", "amr_classes"):
            hot[c] = ""
        _log(f"NOTE: {kleb_tsv.name} not found — virulence/amr columns will be empty")

    # Family-conditioned uniform null; lambda_F is one scalar per family.
    lam_by_fam = family_conditioned_lambda(df, n_clusters)
    lam = hot["is_family"].map(lam_by_fam).to_numpy()
    obs = hot["n_genomes_flanked"].to_numpy()
    hot["expected_genomes"] = lam
    hot["enrichment"] = obs / lam
    hot["p_value"] = _poisson_sf(obs, lam)
    hot["q_value"] = _bh_qvalues(hot["p_value"].to_numpy())
    hot["hotspot"] = (hot["n_genomes_flanked"] >= min_recurrence) & (hot["q_value"] <= fdr)

    # Order: cluster's total IS events (desc), then IS family by n within cluster.
    hot["cluster_n_is_events"] = hot.groupby("cluster")["n_is_events"].transform("sum")
    # Counts are float after fillna(); cast to int64 for clean output.
    for c in (
        "n_genomes_flanked", "n_is_events",
        "n_as_upstream", "n_as_downstream",
        "n_partial_events", "n_genomes_partial",
        "cluster_n_is_events",
    ):
        hot[c] = hot[c].astype("int64")
    hot = hot.sort_values(
        ["cluster_n_is_events", "cluster", "n_is_events"], ascending=[False, True, False]
    ).reset_index(drop=True)
    cols = [
        "cluster",
        "is_family",
        "annotation",
        "virulence_hits",
        "amr_hits",
        "amr_classes",
        "cluster_n_is_events",
        "n_genomes_flanked",
        "n_is_events",
        "n_as_upstream",
        "n_as_downstream",
        "n_partial_events",
        "n_genomes_partial",
        "frac_partial",
        "expected_genomes",
        "enrichment",
        "p_value",
        "q_value",
        "hotspot",
    ]
    hotspots = out_dir / f"{lineage}_is_flank_panaroo_hotspots.tsv"
    with open(hotspots, "w") as fh:
        fh.write(
            f"# lineage={lineage} genomes={len(samples)} clusters_N={n_clusters} "
            f"unit=(panaroo_cluster,is_family) lambda_F=[{lam.min():.3f},{lam.max():.3f}]; "
            f"null=uniform-over-clusters per IS family "
            f"(ignores cluster length/core-accessory)\n"
        )
        hot[cols].to_csv(fh, sep="\t", index=False)
    _log(
        f"wrote {hotspots.name} ({len(hot):,} cluster-family pairs, "
        f"{int(hot['hotspot'].sum())} flagged hotspots) — DONE"
    )


def main() -> int:
    """CLI entry point."""
    base = Path(
        "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/local_data/klebsiella/processed"
    )
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--is-gene-context", type=Path, default=base / "isescan_analysis/is_gene_context.tsv.gz")
    ap.add_argument("--panaroo-root", type=Path, default=base / "panaroo_min")
    ap.add_argument("--lineage", default="SL39")
    ap.add_argument("--out-dir", type=Path, default=base / "isescan_analysis/lineage_hotspots")
    ap.add_argument("--min-recurrence", type=int, default=3)
    ap.add_argument("--fdr", type=float, default=0.05)
    ap.add_argument("--include-ref-bucket", action="store_true")
    args = ap.parse_args()
    run(
        args.is_gene_context,
        args.panaroo_root,
        args.lineage,
        args.out_dir,
        args.min_recurrence,
        args.fdr,
        args.include_ref_bucket,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
