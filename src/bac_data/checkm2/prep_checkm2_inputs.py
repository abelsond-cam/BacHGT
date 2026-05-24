#!/usr/bin/env python3
"""Build the CheckM2 symlink manifest from ``lra_discovery.tsv``.

prep_checkm2_inputs.py
----------------------
Reads the unified ``lra_discovery.tsv`` (built by
``bac_data.lr_data.build_lra_discovery``), which already records one row per
biological assembly, the chosen ``scoring_accession`` (GCF preferred over GCA),
and the resolved ``fasta_on_disk`` path. This script just stages the symlinks
CheckM2 will scan in one working directory.

Cohort-agnostic by design: any caller who can produce a TSV with the columns
``scoring_accession``, ``fasta_on_disk``, ``GCA``, ``GCF`` can drive CheckM2
through this step.

Inputs (HPC defaults; flags override):
  --discovery-tsv   <RDS>/david/processed/lra_discovery.tsv

Outputs (default: <RDS>/david/processed/checkm2_lra/):
  manifest.tsv        one row per CheckM2 scoring target
  missing_fastas.tsv  rows whose FASTA isn't on disk (review + re-download)
  links/              symlinks named <scoring_accession>.fna.gz → source_path

Idempotent: re-run to refresh symlinks after new genomes appear on disk.
Returns nonzero if any scoring target's FASTA is missing — fix and rerun.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Defaults match the HPC layout. --override flags handle local dev.
DEFAULT_DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_DISCOVERY = DEFAULT_DATA_ROOT / "david/processed/lra_discovery.tsv"
DEFAULT_OUT_DIR   = DEFAULT_DATA_ROOT / "david/processed/checkm2_lra"


def load_discovery(path: Path) -> pd.DataFrame:
    """Load ``lra_discovery.tsv`` as strings; coerce bool-text where needed."""
    df = pd.read_csv(path, sep="\t", low_memory=False, dtype=str).fillna("")
    # The bool columns we care about read back as "True" / "False" strings.
    for col in ("download_needed",):
        if col in df.columns:
            df[col] = df[col].str.lower().isin({"true", "1", "yes"})
    return df


def symlink_targets(discovery: pd.DataFrame, links_dir: Path) -> pd.DataFrame:
    """Populate ``links_dir`` with one symlink per scoring target. Returns manifest."""
    links_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, row in discovery.iterrows():
        acc = row["scoring_accession"]
        src = row.get("fasta_on_disk", "")
        if not acc:
            continue
        link = links_dir / f"{acc}.fna.gz"
        exists = bool(src) and Path(src).is_file()
        if exists:
            # Refresh symlink — handle stale targets from prior runs.
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(src)
        rows.append({
            "scoring_accession": acc,
            "GCA": row.get("GCA", ""),
            "GCF": row.get("GCF", ""),
            "Sample": row.get("Sample", ""),
            "is_refseq": row.get("is_refseq", ""),
            "is_norway": row.get("is_norway", ""),
            "stale_refseq": row.get("stale_refseq", ""),
            "source_path": src,
            "link_path": str(link),
            "exists": exists,
        })
    return pd.DataFrame(rows)


def main() -> int:
    """CLI entry point — stage CheckM2 symlinks from ``lra_discovery.tsv``."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discovery-tsv", type=Path, default=DEFAULT_DISCOVERY)
    ap.add_argument("--out-dir",       type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    print(f"Discovery TSV: {args.discovery_tsv}", flush=True)
    print(f"Out dir:       {args.out_dir}", flush=True)

    disc = load_discovery(args.discovery_tsv)
    print(f"\nDiscovery rows: {len(disc)}", flush=True)

    links_dir = args.out_dir / "links"
    manifest = symlink_targets(disc, links_dir)

    missing = manifest[~manifest["exists"].astype(bool)]
    n_ok = int(manifest["exists"].astype(bool).sum())
    print(f"Symlinked:           {n_ok}", flush=True)
    print(f"Missing source FASTA: {len(missing)}", flush=True)
    if len(missing):
        print("\nFirst 10 missing rows:")
        print(missing[["scoring_accession", "GCA", "GCF", "Sample", "source_path"]].head(10).to_string(index=False))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_tsv = args.out_dir / "manifest.tsv"
    missing_tsv  = args.out_dir / "missing_fastas.tsv"
    manifest.to_csv(manifest_tsv, sep="\t", index=False)
    missing.to_csv(missing_tsv, sep="\t", index=False)
    print(f"\nManifest → {manifest_tsv}", flush=True)
    print(f"Missing  → {missing_tsv}  (review + re-download via build_lra_discovery + the download wrappers)", flush=True)
    print(f"Links    → {links_dir}/<scoring_accession>.fna.gz  (n={n_ok})", flush=True)
    return 0 if len(missing) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
