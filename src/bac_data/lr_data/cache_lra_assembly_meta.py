#!/usr/bin/env python3
"""cache_lra_assembly_meta.py
------------------------------
Fetch per-assembly NCBI Datasets metadata for every ``scoring_accession`` in
``lra_discovery.tsv`` and write a slim TSV cache.

Reuses the batched-with-convergence-loop helpers from
``gca_to_gcf_lookup.py`` — the NCBI Datasets v2 endpoint accepts both GCA and
GCF accessions, so we can feed it the mixed ``scoring_accession`` column
directly.

Requires the ``NCBI_API_KEY`` env var for the 10 req/s rate limit; without
it the lookup is slower but still works.

Usage
─────
    NCBI_API_KEY=... uv run python -m bac_data.lr_data.cache_lra_assembly_meta
    # custom paths:
    uv run python -m bac_data.lr_data.cache_lra_assembly_meta \
        --input <lra_discovery.tsv> --out <lra_ncbi_assembly_meta.tsv>
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from bac_data.lr_data.gca_to_gcf_lookup import DEFAULT_BATCH, lookup_all_gcas

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
LR_DISCOVERY_DIR = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lr_discovery"
DEFAULT_INPUT = LR_DISCOVERY_DIR / "lra_discovery.tsv"
DEFAULT_OUT = LR_DISCOVERY_DIR / "lra_ncbi_assembly_meta.tsv"

KEEP_COLS = [
    "lookup_accession",
    "ncbi_accession",
    "ncbi_assembly_level",
    "ncbi_assembly_status",
    "ncbi_sequencing_tech",
    "ncbi_assembly_method",
    "ncbi_n_contigs",
    "ncbi_contig_n50",
    "ncbi_genome_size",
]


def main(argv: list[str] | None = None) -> int:
    """Read scoring_accession from lra_discovery.tsv, fetch NCBI metadata, write the slim TSV cache."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                    help="lra_discovery.tsv carrying the scoring_accession column.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="output slim NCBI assembly-metadata cache TSV.")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    args = ap.parse_args(argv)

    print(f"Reading {args.input}", flush=True)
    base = pd.read_csv(args.input, sep="\t", low_memory=False)
    accs = base["scoring_accession"].dropna().astype(str).unique().tolist()
    print(f"  unique scoring_accession to query: {len(accs)}", flush=True)

    ncbi_df = lookup_all_gcas(accs, batch_size=args.batch)
    print(f"NCBI returned {len(ncbi_df)} unique records", flush=True)

    keep = [c for c in KEEP_COLS if c in ncbi_df.columns]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ncbi_df[keep].to_csv(args.out, sep="\t", index=False)
    print(f"Wrote {args.out}  rows={len(ncbi_df)}  cols={keep}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
