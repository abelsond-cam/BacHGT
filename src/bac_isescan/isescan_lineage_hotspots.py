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
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_T0 = time.monotonic()


def _log(msg: str) -> None:
    """Print a timestamped, flushed progress line (tail-friendly)."""
    print(f"[{time.monotonic() - _T0:7.1f}s] {msg}", flush=True)

try:
    from scipy.stats import poisson

    def _poisson_sf(k: np.ndarray, lam: np.ndarray | float) -> np.ndarray:
        """Upper-tail P(X >= k) for a Poisson(lam) (lam scalar or per-element)."""
        return poisson.sf(k - 1, lam)

except ImportError:  # pragma: no cover - scipy expected in env

    def _poisson_sf(k: np.ndarray, lam: np.ndarray | float) -> np.ndarray:
        """Normal-approx upper tail P(X >= k) fallback when scipy is absent."""
        from math import erfc, sqrt

        z = (k - 0.5 - lam) / np.sqrt(lam)
        return np.array([0.5 * erfc(v / sqrt(2.0)) for v in z])


# Columns from is_gene_context.tsv.gz needed for the flanking analysis.
USE_COLS = [
    "sample", "is_family", "is_len", "is_type", "ncopy", "ov",
    "relationship", "hit_product",
    "upstream_locus_tag", "upstream_distance_bp",
    "downstream_locus_tag", "downstream_distance_bp",
]

# A sample is "reference bucket" if any of these run-TSV flags is True.
REF_BUCKET_FLAGS = ("is_refseq", "is_nctc", "is_mgh78578", "is_complete_norway_genome")

GPA_META_COLS = {"Gene", "Non-unique Gene name", "Annotation"}

SELF_TPASE_RE = r"transposase|insertion sequence|\bIS\d|integrase|recombinase|transpos|tnp"


def _lineage_samples(run_dir: Path, include_ref_bucket: bool) -> list[str]:
    """Return the lineage's sample IDs (gene_presence_absence columns minus ref bucket)."""
    gpa = run_dir / "gene_presence_absence.csv"
    with open(gpa, newline="") as fh:
        header = next(csv.reader(fh))
    samples = [c for c in header if c not in GPA_META_COLS]

    tsv = run_dir / f"{run_dir.name}.tsv"
    if include_ref_bucket or not tsv.exists():
        return samples
    meta = pd.read_csv(tsv, sep="\t", usecols=lambda c: c == "Sample" or c in REF_BUCKET_FLAGS)
    flags = [c for c in REF_BUCKET_FLAGS if c in meta.columns]
    is_ref = np.zeros(len(meta), dtype=bool)
    for c in flags:
        is_ref |= meta[c].astype(str).eq("True").to_numpy()
    ref_samples = set(meta.loc[is_ref, "Sample"].astype(str))
    return [s for s in samples if s not in ref_samples]


def _filter_is_rows(path: Path, lineage_samples: set[str]) -> pd.DataFrame:
    """Vector-filter is_gene_context.tsv.gz to the lineage's samples (chunked)."""
    keep = []
    scanned = kept = 0
    t0 = time.monotonic()
    for i, chunk in enumerate(pd.read_csv(
        path, sep="\t", compression="gzip", usecols=USE_COLS,
        dtype=str, chunksize=500_000,
    ), start=1):
        sub = chunk[chunk["sample"].isin(lineage_samples)]
        keep.append(sub)
        scanned += len(chunk)
        kept += len(sub)
        dt = time.monotonic() - t0
        _log(f"  filter chunk {i}: scanned={scanned:,} kept={kept:,} "
             f"({scanned / dt:,.0f} rows/s)")
    df = pd.concat(keep, ignore_index=True) if keep else pd.DataFrame(columns=USE_COLS)
    for c in ("is_len", "ncopy", "ov", "upstream_distance_bp", "downstream_distance_bp"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _build_index(
    run_dir: Path, lineage_samples: list[str], needed_keys: set[str]
) -> tuple[dict[str, str], dict[str, str], int]:
    """Stream gene_presence_absence.csv once.

    Returns ``(key->cluster, cluster->annotation, n_clusters)`` where ``key`` is
    ``"<sample>|<locus_tag>"`` and only keys in ``needed_keys`` are recorded.
    """
    gpa = run_dir / "gene_presence_absence.csv"
    idx: dict[str, str] = {}
    ann: dict[str, str] = {}
    n_clusters = 0
    sample_set = set(lineage_samples)
    with open(gpa, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        col_of = {name: i for i, name in enumerate(header)}
        gene_i, ann_i = col_of["Gene"], col_of["Annotation"]
        sample_cols = [(s, col_of[s]) for s in lineage_samples if s in col_of]
        for row in reader:
            n_clusters += 1
            cluster = row[gene_i]
            for s, ci in sample_cols:
                cell = row[ci]
                if not cell:
                    continue
                for lt in cell.split(";"):
                    lt = lt.strip()
                    if not lt:
                        continue
                    key = f"{s}|{lt}"
                    if key in needed_keys and key not in idx:
                        idx[key] = cluster
                        ann.setdefault(cluster, row[ann_i])
    _ = sample_set  # documents intent: cells outside lineage cols are never read
    return idx, ann, n_clusters


def _bh_qvalues(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted q-values (vectorised)."""
    n = p.size
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out


def run(
    is_gene_context: Path, panaroo_root: Path, lineage: str, out_dir: Path,
    min_recurrence: int, fdr: float, include_ref_bucket: bool,
) -> None:
    """Execute the flanking-context hotspot analysis for one lineage."""
    run_dir = panaroo_root / lineage
    if not (run_dir / "gene_presence_absence.csv").exists():
        sys.exit(f"no gene_presence_absence.csv under {run_dir}")

    samples = _lineage_samples(run_dir, include_ref_bucket)
    _log(f"lineage={lineage} samples={len(samples)} "
         f"(ref_bucket {'kept' if include_ref_bucket else 'excluded'})")

    _log(f"filtering {is_gene_context.name} (3.5M rows) to lineage samples...")
    df = _filter_is_rows(is_gene_context, set(samples))
    _log(f"IS rows for lineage: {len(df):,}")
    if df.empty:
        sys.exit("no IS rows matched the lineage samples")

    # Composite flank keys (vectorised string ops).
    ku = df["sample"].str.cat(df["upstream_locus_tag"].fillna(""), sep="|")
    kd = df["sample"].str.cat(df["downstream_locus_tag"].fillna(""), sep="|")
    has_u = df["upstream_locus_tag"].notna() & df["upstream_locus_tag"].ne("")
    has_d = df["downstream_locus_tag"].notna() & df["downstream_locus_tag"].ne("")
    needed = set(ku[has_u]) | set(kd[has_d])

    _log(f"building locus_tag->cluster index ({len(needed):,} keys needed)...")
    idx, ann, n_clusters = _build_index(run_dir, samples, needed)
    _log(f"pangenome clusters N={n_clusters}; resolved flank keys={len(idx):,}")

    df["upstream_cluster"] = ku.map(idx).where(has_u)
    df["downstream_cluster"] = kd.map(idx).where(has_d)
    df["self_transposase"] = df["relationship"].eq("within") & df["hit_product"].str.contains(
        SELF_TPASE_RE, case=False, na=False, regex=True
    )
    # ISEScan type='p' marks a partial IS — a degraded remnant ("scar").
    df["is_partial"] = df["is_type"].astype(str).str.strip().str.lower().eq("p")
    igr_len = df["upstream_distance_bp"] + df["is_len"] + df["downstream_distance_bp"]
    intergenic_ok = (
        df["relationship"].eq("intergenic") & has_u & has_d & (igr_len > 0)
    )
    df["igr_len"] = np.where(intergenic_ok, igr_len, np.nan)
    df["igr_occupancy_frac"] = np.where(intergenic_ok, df["is_len"] / igr_len, np.nan)

    _log("vectorised cluster join + per-IS annotation done")
    out_dir.mkdir(parents=True, exist_ok=True)
    annotated = out_dir / f"{lineage}_is_flank_annotated.tsv"
    df.to_csv(annotated, sep="\t", index=False)
    _log(f"wrote {annotated.name} ({len(df):,} rows)")

    # Long form: one row per (IS, resolved flank side). Vectorised concat.
    up = df.loc[df["upstream_cluster"].notna(),
                ["sample", "is_family", "is_partial", "upstream_cluster"]].rename(
        columns={"upstream_cluster": "cluster"})
    up["side"] = "upstream"
    dn = df.loc[df["downstream_cluster"].notna(),
                ["sample", "is_family", "is_partial", "downstream_cluster"]].rename(
        columns={"downstream_cluster": "cluster"})
    dn["side"] = "downstream"
    long = pd.concat([up, dn], ignore_index=True)
    _log(f"aggregating hotspots over {len(long):,} flank events...")

    # Recurrence unit: a (Panaroo cluster, IS family) pair.
    keys = ["cluster", "is_family"]
    grp = long.groupby(keys)
    hot = pd.DataFrame({
        "n_genomes_flanked": grp["sample"].nunique(),
        "n_is_events": grp.size(),
        "n_as_upstream": long[long["side"].eq("upstream")].groupby(keys).size(),
        "n_as_downstream": long[long["side"].eq("downstream")].groupby(keys).size(),
        "n_partial_events": grp["is_partial"].sum(),
        "n_genomes_partial": long[long["is_partial"]].groupby(keys)["sample"].nunique(),
    }).fillna({"n_as_upstream": 0, "n_as_downstream": 0,
               "n_partial_events": 0, "n_genomes_partial": 0})
    hot["frac_partial"] = hot["n_partial_events"] / hot["n_is_events"]
    hot = hot.reset_index()
    hot["annotation"] = hot["cluster"].map(ann)

    # Family-conditioned uniform null: for IS family F the expected genome-
    # recurrence of any cluster depends only on m_{g,F} (genome g's count of
    # family-F IS), each contributing 2 flank events. lambda_F is one scalar
    # per family; enrichment is observed genome-recurrence relative to it.
    base = 1.0 - 1.0 / n_clusters
    fam_counts = df.groupby(["sample", "is_family"]).size()
    lam_by_fam = fam_counts.groupby("is_family").apply(
        lambda c: float(np.sum(1.0 - base ** (2 * c.to_numpy()))))
    lam = hot["is_family"].map(lam_by_fam).to_numpy()
    obs = hot["n_genomes_flanked"].to_numpy()
    hot["expected_genomes"] = lam
    hot["enrichment"] = obs / lam
    hot["p_value"] = _poisson_sf(obs, lam)
    hot["q_value"] = _bh_qvalues(hot["p_value"].to_numpy())
    hot["hotspot"] = (hot["n_genomes_flanked"] >= min_recurrence) & (hot["q_value"] <= fdr)

    # Order: cluster's total IS events (desc), then IS family by n within cluster.
    hot["cluster_n_is_events"] = hot.groupby("cluster")["n_is_events"].transform("sum")
    hot = hot.sort_values(
        ["cluster_n_is_events", "cluster", "n_is_events"],
        ascending=[False, True, False]).reset_index(drop=True)
    cols = ["cluster", "is_family", "annotation", "cluster_n_is_events",
            "n_genomes_flanked", "n_is_events", "n_as_upstream", "n_as_downstream",
            "n_partial_events", "n_genomes_partial", "frac_partial",
            "expected_genomes", "enrichment", "p_value", "q_value", "hotspot"]
    hotspots = out_dir / f"{lineage}_is_flank_hotspots.tsv"
    with open(hotspots, "w") as fh:
        fh.write(f"# lineage={lineage} genomes={len(samples)} clusters_N={n_clusters} "
                 f"unit=(cluster,is_family) lambda_F=[{lam.min():.3f},{lam.max():.3f}]; "
                 f"null=uniform-over-clusters per IS family "
                 f"(ignores cluster length/core-accessory)\n")
        hot[cols].to_csv(fh, sep="\t", index=False)
    _log(f"wrote {hotspots.name} ({len(hot):,} cluster-family pairs, "
         f"{int(hot['hotspot'].sum())} flagged hotspots) — DONE")


def main() -> int:
    """CLI entry point."""
    base = Path(
        "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge"
        "/local_data/klebsiella/processed"
    )
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--is-gene-context", type=Path,
                    default=base / "isescan_analysis/is_gene_context.tsv.gz")
    ap.add_argument("--panaroo-root", type=Path, default=base / "panaroo_min")
    ap.add_argument("--lineage", default="SL39")
    ap.add_argument("--out-dir", type=Path,
                    default=base / "isescan_analysis/lineage_hotspots")
    ap.add_argument("--min-recurrence", type=int, default=3)
    ap.add_argument("--fdr", type=float, default=0.05)
    ap.add_argument("--include-ref-bucket", action="store_true")
    args = ap.parse_args()
    run(args.is_gene_context, args.panaroo_root, args.lineage, args.out_dir,
        args.min_recurrence, args.fdr, args.include_ref_bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
