#!/usr/bin/env python3
"""Emit per-tier download TSVs from ``lra_discovery.tsv``.

discovery_to_download_lists.py
------------------------------
Reads ``lra_discovery.tsv`` (built by ``build_lra_discovery.py``), filters to
rows where ``download_needed == True``, and writes two narrow TSVs in the
``Sample, gca, gcf`` schema the existing downloader expects::

    lra_download_gca_missing.tsv  — scoring_accession is a GCA
    lra_download_gcf_missing.tsv  — scoring_accession is a GCF

``download_related_lr_complete_genomes.py`` consumes either with
``--cg-tsv <path> --which gca|gcf``; its convergence loop handles retry until
all FASTAs are present on disk.

Usage::

    uv run python -m bac_data.lr_data.discovery_to_download_lists
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_DISCOVERY = DATA_ROOT / "david/processed/lra_discovery.tsv"
DEFAULT_OUT_DIR   = DATA_ROOT / "david/processed"


def _missing_subset(disc: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Rows where the scoring target is of ``kind`` ('GCA' or 'GCF') AND its FASTA is absent.

    Gate on ``scoring_accession``'s prefix, not on which columns are populated:
    a paired (GCA+GCF) row has both columns set, but the GCF is the scoring target
    — we only want to fetch the GCF for it, not also the GCA.
    """
    assert kind in {"GCA", "GCF"}
    mask = disc["download_needed"].astype(bool) & disc["scoring_accession"].astype(str).str.startswith(kind + "_")
    sub = disc.loc[mask].copy()
    # Downloader expects 'gca' / 'gcf' columns (lowercase) and a 'Sample' column.
    # Blank the non-scoring column so the downloader's _accessions() doesn't queue both.
    sub["gca"] = sub["GCA"].astype(str) if kind == "GCA" else ""
    sub["gcf"] = sub["GCF"].astype(str) if kind == "GCF" else ""
    return sub[["Sample", "gca", "gcf"]]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — split the discovery TSV into per-tier download lists."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discovery-tsv", type=Path, default=DEFAULT_DISCOVERY)
    ap.add_argument("--out-dir",       type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)

    disc = pd.read_csv(args.discovery_tsv, sep="\t", low_memory=False, dtype=str).fillna("")
    disc["download_needed"] = disc["download_needed"].str.lower().isin({"true", "1", "yes"})

    gca_missing = _missing_subset(disc, "GCA")
    gcf_missing = _missing_subset(disc, "GCF")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    gca_out = args.out_dir / "lra_download_gca_missing.tsv"
    gcf_out = args.out_dir / "lra_download_gcf_missing.tsv"
    gca_missing.to_csv(gca_out, sep="\t", index=False)
    gcf_missing.to_csv(gcf_out, sep="\t", index=False)

    print(f"discovery_tsv : {args.discovery_tsv}  rows={len(disc)}")
    print(f"GCA missing   : {len(gca_missing):>5}  →  {gca_out}")
    print(f"GCF missing   : {len(gcf_missing):>5}  →  {gcf_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
