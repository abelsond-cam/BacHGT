"""Reduce per-sample locus caches into a frequency-filtered sparse variant presence matrix.

Copy-adapted from BacPredict ``bac_pyseer/kleb_iso_source/build_presence_and_distances.py``.
The pure builders (:func:`build_presence_matrix`, :func:`jaccard_distance_matrix`,
:func:`parse_positions`) are lifted unchanged; the ``run()`` entrypoint is refactored to a
``--sparse-only`` path that **never densifies**.

Each unique ``(POS, REF, ALT)`` against the reference contig is one locus. Given a sample
work-list (a file with a ``Sample`` column — e.g. the resolution TSV) and the shared
per-sample cache produced by :mod:`extract_sample_loci`, this builds a binary samples × loci
CSR matrix, drops loci present in ``< --min-freq`` of samples, and saves it sparse-compressed:

- ``variant_presence.npz``        — the binary CSR (``scipy.sparse.save_npz``)
- ``variant_presence_axes.npz``   — ``locus_keys`` (columns) + ``samples`` (rows)
- ``prefilter_locus_spectrum.npz``— pre-filter ``pos`` + per-locus ``freq`` (re-threshold without rebuild)
- ``build_variant_matrix_manifest.json`` + ``missing_cache_samples.txt``

The three non-scaling steps of the original GWAS reduce — densifying ``xf.T.toarray()`` to a
text Rtab, the dense ``n × n`` Jaccard, and the phenotype/per-source blocks — are **dropped**.
At ~79k samples × millions of loci a dense Rtab or a dense ``n × n`` Jaccard (~51 GB) is
catastrophic; saving ``xf`` sparse is what keeps the reduce tractable.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix, csr_matrix, save_npz

DEFAULT_CONTIG = "NC_009648"


def parse_positions(keys: np.ndarray) -> np.ndarray:
    """Extract the integer ``POS`` from an array of ``pos_ref_alt`` locus keys.

    Parameters
    ----------
    keys
        Array of ``"<POS>_<REF>_<ALT>"`` strings (e.g. ``"948_G_A"``).

    Returns
    -------
    numpy.ndarray
        ``int64`` positions aligned to ``keys``.
    """
    return np.fromiter((int(k.split("_", 1)[0]) for k in keys), dtype=np.int64, count=len(keys))


def _read_locus_keys(path: str) -> np.ndarray:
    """Read one ``<Sample>.loci.tsv.gz`` file, return an array of ``pos_ref_alt`` keys."""
    keys: list[str] = []
    with gzip.open(path, "rt") as fh:
        next(fh, None)  # header POS\tREF\tALT
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                keys.append(f"{parts[0]}_{parts[1]}_{parts[2]}")
    return np.array(keys, dtype=object)


def _present_samples(samples: list[str], cache_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """Split ``samples`` into (present, paths, missing) by cache-file existence.

    Returns ``(present_samples, present_paths, missing_samples)``.
    """
    present, paths, missing = [], [], []
    for s in samples:
        p = cache_dir / f"{s}.loci.tsv.gz"
        if p.exists() and p.stat().st_size > 0:
            present.append(s)
            paths.append(str(p))
        else:
            missing.append(s)
    return present, paths, missing


def build_presence_matrix(paths: list[str], n_jobs: int) -> tuple[csr_matrix, np.ndarray]:
    """Read all per-sample locus files and build a binary samples × locus CSR matrix.

    Parameters
    ----------
    paths
        Per-sample ``<Sample>.loci.tsv.gz`` cache paths, in the desired row order.
    n_jobs
        Worker processes for the parallel read (``-1``/``0``/``None`` = all cores).

    Returns
    -------
    tuple
        ``(X_csr_binary, locus_keys)`` where ``X`` is a ``uint8`` samples × loci CSR and
        ``locus_keys[j]`` is the ``pos_ref_alt`` key of column ``j``.
    """
    workers = os.cpu_count() if n_jobs in (-1, 0, None) else n_jobs
    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            per_sample = list(ex.map(_read_locus_keys, paths, chunksize=16))
    else:
        per_sample = [_read_locus_keys(p) for p in paths]

    counts = np.fromiter((len(k) for k in per_sample), dtype=np.int64, count=len(per_sample))
    all_keys = np.concatenate(per_sample) if per_sample else np.array([], dtype=object)
    rows = np.repeat(np.arange(len(per_sample), dtype=np.int64), counts)
    codes, uniq = pd.factorize(all_keys, sort=False)

    data = np.ones(len(codes), dtype=np.uint8)
    x = coo_matrix((data, (rows, codes)), shape=(len(per_sample), len(uniq))).tocsr()
    x.data[:] = 1  # tocsr summed within-sample duplicates; binarise
    return x, np.asarray(uniq, dtype=object)


def jaccard_distance_matrix(x_csr: csr_matrix) -> np.ndarray:
    """Pairwise Jaccard distance over a binary sparse presence matrix, fully vectorised.

    For binary rows the intersection size is one matrix product,
    ``|a ∩ b| = (X · Xᵀ)_{ab}``, and ``|a ∪ b| = |a| + |b| − |a ∩ b|``, so the entire
    ``n × n`` distance matrix is a single sparse matmul plus broadcast arithmetic — no
    per-pair loop and no densified feature matrix. Matches ``scipy.spatial.distance.jaccard``
    exactly (two all-zero rows have distance 0). **Dense ``n × n`` output — only for small
    (per-group / subsampled) inputs, never the full all-sample matrix.**

    Parameters
    ----------
    x_csr
        Binary samples × loci sparse matrix.

    Returns
    -------
    numpy.ndarray
        Dense ``n × n`` Jaccard distance matrix (``float64``).
    """
    xb = x_csr.astype(bool).astype(np.float64).tocsr()
    inter = np.asarray((xb @ xb.T).todense())
    sizes = np.asarray(xb.sum(axis=1)).ravel()
    union = sizes[:, None] + sizes[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, inter / union, 1.0)
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    return dist


def _read_sample_list(sample_list: Path) -> list[str]:
    """Read the ``Sample`` column from a CSV/TSV work-list (resolution TSV or split CSV)."""
    sep = "\t" if sample_list.suffix.lower() in {".tsv", ".txt"} else ","
    s = pd.read_csv(sample_list, sep=sep, usecols=["Sample"])["Sample"]
    return s.astype(str).drop_duplicates().tolist()


def run(
    *,
    sample_list: Path,
    cache_dir: Path,
    out_dir: Path,
    min_freq: float,
    contig: str,
    n_jobs: int,
    sparse_only: bool = True,
    filter_params: dict[str, float] | None = None,
) -> None:
    """Build and save the sparse frequency-filtered variant presence matrix for a cohort."""
    if not sparse_only:
        raise NotImplementedError(
            "Only the --sparse-only path is implemented in bac_phylogeny; the dense GWAS "
            "Rtab/Jaccard reduce lives in BacPredict and does not scale to all-KPSC."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    requested = _read_sample_list(sample_list)

    present, paths, missing = _present_samples(requested, cache_dir)
    print(f"Work-list samples: {len(requested)}; with cache: {len(present)}; missing: {len(missing)}")
    if not present:
        raise SystemExit("No samples have a cache file — run extract_sample_loci first.")

    x, keys = build_presence_matrix(paths, n_jobs)
    n_loci_pre = x.shape[1]
    min_count = max(1, ceil(min_freq * len(present)))
    freq = np.asarray(x.sum(axis=0)).ravel()
    keep = freq >= min_count
    xf = x[:, keep].tocsr()
    kept_keys = keys[keep]
    print(f"Loci: {n_loci_pre} -> {xf.shape[1]} (>= {min_count} samples = {min_freq:.2%} of {len(present)})")

    # Sparse matrix + its axes (CSR carries no row/col labels).
    save_npz(out_dir / "variant_presence.npz", xf)
    np.savez_compressed(
        out_dir / "variant_presence_axes.npz",
        locus_keys=kept_keys,
        samples=np.array(present, dtype=object),
        contig=np.array(contig, dtype=object),
    )
    # Pre-filter per-locus spectrum (POS + sample count) — lets a later re-threshold (e.g.
    # 0.1% -> 1%) recompute `keep` without rebuilding the matrix. Tiny relative to the matrix.
    np.savez_compressed(
        out_dir / "prefilter_locus_spectrum.npz",
        pos=parse_positions(keys),
        freq=freq.astype(np.int64),
        n_samples=np.int64(len(present)),
        min_count=np.int64(min_count),
    )

    manifest = {
        "sample_list": str(sample_list),
        "reference_contig": contig,
        "n_samples_requested": len(requested),
        "n_samples_with_cache": len(present),
        "n_missing_cache": len(missing),
        "n_loci_prefilter": int(n_loci_pre),
        "n_loci_postfilter": int(xf.shape[1]),
        "min_freq_fraction": min_freq,
        "min_freq_count": int(min_count),
        "filter_params": filter_params or {"min_qual": 100.0, "min_dp": 3, "require_hom": True},
        "outputs": {
            "presence_npz": str(out_dir / "variant_presence.npz"),
            "axes_npz": str(out_dir / "variant_presence_axes.npz"),
            "spectrum_npz": str(out_dir / "prefilter_locus_spectrum.npz"),
        },
    }
    (out_dir / "build_variant_matrix_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "missing_cache_samples.txt").write_text("\n".join(missing) + ("\n" if missing else ""))

    print("\n=== wrote ===")
    for p in (
        out_dir / "variant_presence.npz",
        out_dir / "variant_presence_axes.npz",
        out_dir / "prefilter_locus_spectrum.npz",
        out_dir / "build_variant_matrix_manifest.json",
    ):
        print(f"  {p}")
    print(json.dumps(manifest, indent=2))


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample-list", type=Path, required=True, help="CSV/TSV with a 'Sample' column (e.g. the resolution TSV).")
    parser.add_argument("--cache-dir", type=Path, required=True, help="Shared per-sample locus cache dir.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output dir for the sparse matrix + manifest.")
    parser.add_argument("--min-freq", type=float, default=0.001, help="Drop loci present in < this fraction of samples (default 0.1%%).")
    parser.add_argument("--contig", default=DEFAULT_CONTIG, help="Reference contig name (recorded with the locus keys).")
    parser.add_argument("--n-jobs", type=int, default=-1, help="Cores for the parallel cache read (-1 = all).")
    parser.add_argument("--sparse-only", action="store_true", default=True, help="Save sparse, never densify (the only supported path).")
    args = parser.parse_args(argv)

    run(
        sample_list=args.sample_list,
        cache_dir=args.cache_dir,
        out_dir=args.out_dir,
        min_freq=args.min_freq,
        contig=args.contig,
        n_jobs=args.n_jobs,
        sparse_only=args.sparse_only,
    )


if __name__ == "__main__":
    main()
