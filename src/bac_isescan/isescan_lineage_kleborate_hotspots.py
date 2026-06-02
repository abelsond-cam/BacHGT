"""Per-lineage ISEScan flanking-context → Kleborate label hotspot pivot.

Sibling to :mod:`bac_isescan.isescan_lineage_panaroo_hotspots`. Same IS-flank
events; different recurrence unit. Each output row is a
``(Kleborate label, IS family)`` pair, where ``label`` is either:

- a Kleborate virulence gene — already at gene level (e.g. ``ybt:ybtP``,
  ``iuc:iucA``, ``rmp:rmpA2``), or
- an AMR drug class — Kleborate's taxonomy from ``Kleborate_classes.csv``
  (e.g. ``Bla``, ``AGly``, ``Flq``, ``Tet``).

Mechanism: load the shared per-lineage prep (per-IS DataFrame + flank-event
long form + Panaroo annotation), then left-join the per-cluster Kleborate
annotation TSV produced by
:mod:`bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap`, explode each flank
event by its cluster's labels, and group by ``(label, label_type, is_family)``.
``n_panaroo_clusters`` reports how many distinct Panaroo clusters under each
label are flanked by that IS family.

Allele-level AMR (``amr_hits`` in the Panaroo annotation TSV — NDM-1, NDM-2,
…, KPC-2, …) is intentionally not pivoted — too granular for the hotspot
view; the Panaroo table preserves allele detail.

Descriptive only — no per-pair enrichment test. The Panaroo pivot is the
home for hotspot detection; this pivot just answers "what IS families flank
each Kleborate label, in how many genomes, how often partial".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_isescan._lineage_hotspot_common import _log, prepare_lineage

# Label-type tags emitted as the second column of the output.
_LABEL_TYPE_VIRULENCE = "virulence"
_LABEL_TYPE_AMR_CLASS = "amr_class"


def _explode_labels(kleb: pd.DataFrame) -> pd.DataFrame:
    """Explode cluster annotations into long form ``(cluster, label, label_type)``.

    Reads ``virulence_hits`` and ``amr_classes`` columns (``;``-joined strings),
    drops empties, emits one row per label. ``amr_hits`` (allele-level) is
    intentionally not pivoted.
    """
    rows: list[dict[str, str]] = []
    for _, r in kleb.iterrows():
        cluster = r["cluster"]
        for lbl in str(r.get("virulence_hits") or "").split(";"):
            lbl = lbl.strip()
            if lbl:
                rows.append({"cluster": cluster, "label": lbl, "label_type": _LABEL_TYPE_VIRULENCE})
        for lbl in str(r.get("amr_classes") or "").split(";"):
            lbl = lbl.strip()
            if lbl:
                rows.append({"cluster": cluster, "label": lbl, "label_type": _LABEL_TYPE_AMR_CLASS})
    return pd.DataFrame(rows)


def run(
    is_gene_context: Path,
    panaroo_root: Path,
    lineage: str,
    out_dir: Path,
    include_ref_bucket: bool,
) -> None:
    """Execute the per-(Kleborate label, IS family) hotspot pivot."""
    df, long, _ann, n_clusters, samples, run_dir = prepare_lineage(
        panaroo_root, lineage, is_gene_context, include_ref_bucket
    )
    del df  # unused for the pivot; kept by prepare_lineage for symmetry

    kleb_tsv = run_dir / f"{lineage}_panaroo_nodes_annotate_kleborate.tsv"
    if not kleb_tsv.exists():
        sys.exit(
            f"no {kleb_tsv.name} under {run_dir} — run "
            "bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap first"
        )
    kleb = pd.read_csv(kleb_tsv, sep="\t", dtype=str).fillna("")
    labels = _explode_labels(kleb)
    if labels.empty:
        sys.exit("no Kleborate labels in the annotation TSV — nothing to pivot")
    _log(f"exploded {len(kleb):,} cluster rows → {len(labels):,} (cluster, label) rows")

    # Join labels onto the flank-event long form: each event whose cluster
    # carries a label gets one row per label.
    long_lab = long.merge(labels, on="cluster", how="inner")
    _log(f"flank events with a Kleborate label: {len(long_lab):,}")

    keys = ["label", "label_type", "is_family"]
    grp = long_lab.groupby(keys)
    hot = pd.DataFrame(
        {
            "n_genomes_flanked": grp["sample"].nunique(),
            "n_is_events": grp.size(),
            "n_panaroo_clusters": grp["cluster"].nunique(),
            "n_as_upstream": long_lab[long_lab["side"].eq("upstream")].groupby(keys).size(),
            "n_as_downstream": long_lab[long_lab["side"].eq("downstream")].groupby(keys).size(),
            "n_partial_events": grp["is_partial"].sum(),
            "n_genomes_partial": long_lab[long_lab["is_partial"]].groupby(keys)["sample"].nunique(),
        }
    ).fillna({"n_as_upstream": 0, "n_as_downstream": 0, "n_partial_events": 0, "n_genomes_partial": 0})
    hot["frac_partial"] = hot["n_partial_events"] / hot["n_is_events"]
    hot = hot.reset_index()

    # Order: label's total IS events (desc), then IS family by n within label.
    hot["label_n_is_events"] = hot.groupby("label")["n_is_events"].transform("sum")
    for c in (
        "n_genomes_flanked", "n_is_events", "n_panaroo_clusters",
        "n_as_upstream", "n_as_downstream",
        "n_partial_events", "n_genomes_partial",
        "label_n_is_events",
    ):
        hot[c] = hot[c].astype("int64")
    hot = hot.sort_values(
        ["label_n_is_events", "label", "n_is_events"], ascending=[False, True, False]
    ).reset_index(drop=True)
    cols = [
        "label",
        "label_type",
        "is_family",
        "label_n_is_events",
        "n_panaroo_clusters",
        "n_genomes_flanked",
        "n_is_events",
        "n_as_upstream",
        "n_as_downstream",
        "n_partial_events",
        "n_genomes_partial",
        "frac_partial",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    hotspots = out_dir / f"{lineage}_is_flank_kleborate_hotspots.tsv"
    with open(hotspots, "w") as fh:
        fh.write(
            f"# lineage={lineage} genomes={len(samples)} clusters_N={n_clusters} "
            f"unit=(kleborate_label,is_family); descriptive (no enrichment test "
            f"— see isescan_lineage_panaroo_hotspots for that)\n"
        )
        hot[cols].to_csv(fh, sep="\t", index=False)
    _log(
        f"wrote {hotspots.name} ({len(hot):,} label-family pairs, "
        f"{hot['label'].nunique():,} distinct labels) — DONE"
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
    ap.add_argument("--include-ref-bucket", action="store_true")
    args = ap.parse_args()
    run(args.is_gene_context, args.panaroo_root, args.lineage, args.out_dir, args.include_ref_bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
