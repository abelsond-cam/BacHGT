#!/usr/bin/env python3
"""Parse per-protein GC content from CheckM2's prodigal output.

parse_protein_gc.py
-------------------
CheckM2 v1.x runs prodigal on every input genome and keeps the predicted
protein FASTA at ``checkm2_out/protein_files/<scoring_accession>.fna.faa``.
Each protein header carries ``gc_cont=<float>`` (3 decimal places) — finer
resolution than CheckM2's genome-level ``GC_Content`` column (2 decimals).

This script:

  1. Walks every ``.faa`` file under ``--protein-dir``.
  2. For each protein, parses ``gc_cont`` and the start/end DNA coordinates.
  3. Per genome, computes:
       - ``n_proteins``
       - ``mean_protein_gc``           (simple mean)
       - ``weighted_mean_protein_gc``  (weighted by DNA length per protein)
       - ``median_protein_gc``
       - ``std_protein_gc``
       - ``min_protein_gc`` / ``max_protein_gc``
       - ``total_dna_length``
  4. Writes per-genome aggregates → ``lra_per_gene_gc.tsv``.
  5. Optionally samples ``--sample-per-genome`` proteins per genome → a
     per-protein TSV for downstream histogram plots in
     ``lra_GC_per_gene.ipynb`` (size: ~30 MB at N=100).

Parallelism: ``--workers`` controls the ProcessPool size (one .faa per task).
At 5,557 files × ~5,600 proteins/file ≈ 31M headers, expect <10 min wall on
HPC at workers=8.

Usage::

    uv run python -m bac_data.lr_data.parse_protein_gc                  # defaults
    uv run python -m bac_data.lr_data.parse_protein_gc --workers 8 --sample-per-genome 100
"""

from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_PROTEIN_DIR    = DATA_ROOT / "david/processed/checkm2_lra/checkm2_out/protein_files"
DEFAULT_AGGREGATE_TSV  = DATA_ROOT / "david/processed/lra_per_gene_gc.tsv"
DEFAULT_SAMPLE_TSV     = DATA_ROOT / "david/processed/lra_per_protein_gc_sample.tsv"

# Prodigal .faa header: ">contig_id_gene_num # start # end # strand # ID=…;…;gc_cont=0.552"
_HEADER_RE = re.compile(
    r"^>(?P<gid>\S+)\s+#\s+(?P<start>\d+)\s+#\s+(?P<end>\d+)\s+#\s+(?P<strand>-?\d+).*?gc_cont=(?P<gc>[\d.]+)"
)

# Filename convention: "<scoring_accession>.fna.faa".
_SUFFIX = ".fna.faa"


def _strip_suffix(name: str) -> str:
    if name.endswith(_SUFFIX):
        return name[: -len(_SUFFIX)]
    # Fall back to stripping standard FASTA extensions if the suffix evolves.
    return re.sub(r"\.(faa|fna\.faa|fa\.faa)$", "", name)


def parse_one(path_str: str, sample_per_genome: int) -> tuple[dict, list[dict]]:
    """Parse a single .faa file → (aggregate dict, optional protein-sample rows)."""
    path = Path(path_str)
    sample_rng = np.random.default_rng(seed=hash(path.name) & 0xFFFFFFFF)

    gene_ids: list[str] = []
    lengths: list[int]  = []
    gcs: list[float]    = []

    with open(path) as fh:
        for line in fh:
            if not line.startswith(">"):
                continue
            m = _HEADER_RE.match(line)
            if not m:
                continue
            gene_ids.append(m["gid"])
            lengths.append(int(m["end"]) - int(m["start"]) + 1)
            gcs.append(float(m["gc"]))

    sample: list[dict] = []
    acc = _strip_suffix(path.name)

    if not gcs:
        return {"scoring_accession": acc, "n_proteins": 0}, sample

    lens = np.asarray(lengths, dtype=float)
    arr  = np.asarray(gcs,     dtype=float)
    agg = {
        "scoring_accession":        acc,
        "n_proteins":               int(len(arr)),
        "mean_protein_gc":          float(arr.mean()),
        "weighted_mean_protein_gc": float((arr * lens).sum() / lens.sum()),
        "median_protein_gc":        float(np.median(arr)),
        "std_protein_gc":           float(arr.std(ddof=0)),
        "min_protein_gc":           float(arr.min()),
        "max_protein_gc":           float(arr.max()),
        "total_dna_length":         int(lens.sum()),
    }

    if sample_per_genome > 0 and len(arr) > 0:
        k = min(sample_per_genome, len(arr))
        idx = sample_rng.choice(len(arr), size=k, replace=False)
        for i in idx:
            sample.append({
                "scoring_accession": acc,
                "gene_id":           gene_ids[i],
                "dna_length":        int(lengths[i]),
                "gc_cont":           float(gcs[i]),
            })
    return agg, sample


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — parse protein_files/, write per-genome + sample TSVs."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--protein-dir",       type=Path, default=DEFAULT_PROTEIN_DIR)
    ap.add_argument("--out-aggregate",     type=Path, default=DEFAULT_AGGREGATE_TSV)
    ap.add_argument("--out-sample",        type=Path, default=DEFAULT_SAMPLE_TSV)
    ap.add_argument("--sample-per-genome", type=int, default=100,
                    help="Random proteins per genome to keep for histogram TSV (0 = skip).")
    ap.add_argument("--workers",           type=int, default=8)
    args = ap.parse_args(argv)

    paths = sorted(args.protein_dir.glob("*.faa"))
    print(f"protein_dir : {args.protein_dir}  files={len(paths)}")
    print(f"out_aggregate: {args.out_aggregate}")
    if args.sample_per_genome > 0:
        print(f"out_sample   : {args.out_sample}  (sample={args.sample_per_genome}/genome)")
    print(f"workers      : {args.workers}")

    aggregates: list[dict] = []
    samples:    list[dict] = []

    if not paths:
        print(f"ERROR: no .faa files under {args.protein_dir}", file=sys.stderr)
        return 1

    if args.workers <= 1:
        for p in paths:
            agg, smp = parse_one(str(p), args.sample_per_genome)
            aggregates.append(agg)
            samples.extend(smp)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {
                ex.submit(parse_one, str(p), args.sample_per_genome): p.name
                for p in paths
            }
            for n, fut in enumerate(as_completed(futures), 1):
                agg, smp = fut.result()
                aggregates.append(agg)
                samples.extend(smp)
                if n % 500 == 0 or n == len(paths):
                    print(f"  parsed {n} / {len(paths)} genomes", flush=True)

    agg_df = pd.DataFrame(aggregates).sort_values("scoring_accession").reset_index(drop=True)
    args.out_aggregate.parent.mkdir(parents=True, exist_ok=True)
    agg_df.to_csv(args.out_aggregate, sep="\t", index=False)
    print(f"\nwrote {args.out_aggregate}  rows={len(agg_df)}")
    print(f"  median per-genome n_proteins        : {agg_df['n_proteins'].median():.0f}")
    print(f"  median weighted_mean_protein_gc     : {agg_df['weighted_mean_protein_gc'].median():.4f}")
    print(f"  IQR    weighted_mean_protein_gc     : "
          f"{agg_df['weighted_mean_protein_gc'].quantile(0.25):.4f} – "
          f"{agg_df['weighted_mean_protein_gc'].quantile(0.75):.4f}")

    if args.sample_per_genome > 0 and samples:
        smp_df = pd.DataFrame(samples)
        smp_df.to_csv(args.out_sample, sep="\t", index=False)
        print(f"wrote {args.out_sample}  rows={len(smp_df)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
