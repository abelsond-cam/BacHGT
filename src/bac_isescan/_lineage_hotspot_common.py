"""Shared helpers for the lineage-level IS-flanking hotspot analyses.

Two sibling modules consume this:

- :mod:`bac_isescan.isescan_lineage_panaroo_hotspots` groups flank events by
  ``(Panaroo cluster, IS family)``.
- :mod:`bac_isescan.isescan_lineage_kleborate_hotspots` pivots the same flank
  events onto ``(Kleborate label, IS family)`` — virulence genes and AMR drug
  classes.

The shared bits are the boring-but-expensive prep: filtering the lineage's
samples, streaming the 3.5M-row ``is_gene_context.tsv.gz`` once, mapping
locus_tags to Panaroo clusters via ``gene_presence_absence.csv``, building the
per-IS DataFrame and the long-form flank-event table, and the
family-conditioned uniform-over-clusters null.

Module-private by convention (leading underscore); callers in the same
subpackage import freely.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Columns from is_gene_context.tsv.gz needed for the flanking analysis.
USE_COLS = [
    "sample",
    "is_family",
    "is_len",
    "is_type",
    "ncopy",
    "ov",
    "relationship",
    "hit_product",
    "upstream_locus_tag",
    "upstream_distance_bp",
    "downstream_locus_tag",
    "downstream_distance_bp",
]

# A sample is "reference bucket" if any of these run-TSV flags is True.
REF_BUCKET_FLAGS = ("is_refseq", "is_nctc", "is_mgh78578", "is_complete_norway_genome")

GPA_META_COLS = {"Gene", "Non-unique Gene name", "Annotation"}

SELF_TPASE_RE = r"transposase|insertion sequence|\bIS\d|integrase|recombinase|transpos|tnp"

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


def _bh_qvalues(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted q-values (vectorised)."""
    n = p.size
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out


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
    for i, chunk in enumerate(
        pd.read_csv(
            path,
            sep="\t",
            compression="gzip",
            usecols=USE_COLS,
            dtype=str,
            chunksize=500_000,
        ),
        start=1,
    ):
        sub = chunk[chunk["sample"].isin(lineage_samples)]
        keep.append(sub)
        scanned += len(chunk)
        kept += len(sub)
        dt = time.monotonic() - t0
        _log(f"  filter chunk {i}: scanned={scanned:,} kept={kept:,} ({scanned / dt:,.0f} rows/s)")
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


def prepare_lineage(
    panaroo_root: Path, lineage: str, is_gene_context: Path, include_ref_bucket: bool
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str], int, list[str], Path]:
    """Per-lineage IS-flanking prep shared by both downstream groupings.

    Loads the lineage's samples, filters the gzipped IS-context TSV, maps each
    flank locus_tag to its Panaroo cluster, and emits:

    - ``df`` — one row per IS element, with the per-IS columns from ``USE_COLS``
      plus ``upstream_cluster`` / ``downstream_cluster`` (Panaroo), ``is_partial``,
      ``self_transposase`` and intergenic occupancy stats.
    - ``long`` — one row per resolved flank side (``sample``, ``is_family``,
      ``is_partial``, ``cluster``, ``side``).
    - ``ann`` — ``cluster → annotation`` map.
    - ``n_clusters`` — pangenome cluster count (denominator for null).
    - ``samples`` — lineage sample IDs after the ref-bucket filter.
    - ``run_dir`` — resolved Panaroo run directory (handy for the caller's I/O).
    """
    run_dir = panaroo_root / lineage
    if not (run_dir / "gene_presence_absence.csv").exists():
        sys.exit(f"no gene_presence_absence.csv under {run_dir}")

    samples = _lineage_samples(run_dir, include_ref_bucket)
    _log(f"lineage={lineage} samples={len(samples)} (ref_bucket {'kept' if include_ref_bucket else 'excluded'})")

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
    intergenic_ok = df["relationship"].eq("intergenic") & has_u & has_d & (igr_len > 0)
    df["igr_len"] = np.where(intergenic_ok, igr_len, np.nan)
    df["igr_occupancy_frac"] = np.where(intergenic_ok, df["is_len"] / igr_len, np.nan)
    _log("vectorised cluster join + per-IS annotation done")

    # Long form: one row per (IS, resolved flank side).
    up = df.loc[df["upstream_cluster"].notna(), ["sample", "is_family", "is_partial", "upstream_cluster"]].rename(
        columns={"upstream_cluster": "cluster"}
    )
    up["side"] = "upstream"
    dn = df.loc[df["downstream_cluster"].notna(), ["sample", "is_family", "is_partial", "downstream_cluster"]].rename(
        columns={"downstream_cluster": "cluster"}
    )
    dn["side"] = "downstream"
    long = pd.concat([up, dn], ignore_index=True)
    _log(f"long-form flank events: {len(long):,}")
    return df, long, ann, n_clusters, samples, run_dir


def family_conditioned_lambda(df: pd.DataFrame, n_clusters: int) -> pd.Series:
    """Per-IS-family ``lambda_F`` under the uniform-over-clusters null.

    ``lambda_F`` is the expected genome-recurrence of any single Panaroo
    cluster, conditioned on IS family F: each genome ``g`` contributes
    ``1 - (1 - 1/n_clusters) ** (2 * m_{g,F})`` where ``m_{g,F}`` is its
    count of family-F IS (×2 because each IS contributes upstream +
    downstream flank events). Returned as a ``Series`` indexed by IS family.
    """
    base = 1.0 - 1.0 / n_clusters
    fam_counts = df.groupby(["sample", "is_family"]).size()
    return fam_counts.groupby("is_family").apply(lambda c: float(np.sum(1.0 - base ** (2 * c.to_numpy()))))
