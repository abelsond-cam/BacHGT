#!/usr/bin/env python3
"""Annotate ``lra_discovery.tsv`` with CheckM2 quality metrics.

annotate_checkm2.py
-------------------
Phase B.7. Reads CheckM2's ``quality_report.tsv`` and appends its per-genome
metrics to the unified discovery TSV by joining on ``scoring_accession`` ↔
CheckM2's ``Name`` (the symlink stem, which is the bare scoring accession).

CheckM2 columns kept (renamed to lower-snake-case with a ``checkm2_`` prefix
to avoid collisions with any existing discovery columns)::

    checkm2_completeness, checkm2_contamination,
    checkm2_completeness_model_used, checkm2_translation_table_used,
    checkm2_coding_density, checkm2_contig_n50, checkm2_average_gene_length,
    checkm2_genome_size, checkm2_gc_content, checkm2_total_coding_sequences,
    checkm2_additional_notes

Idempotent: existing ``checkm2_*`` columns on the discovery TSV are dropped
and rewritten so re-runs replace stale values without duplicating columns.

Usage::

    uv run python -m bac_data.lr_data.annotate_checkm2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import pandas as pd

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_DISCOVERY  = DATA_ROOT / "david/processed/lra_discovery.tsv"
DEFAULT_CHECKM2_TSV = DATA_ROOT / "david/processed/checkm2_lra/quality_report.tsv"

# Columns CheckM2 v1.x writes. Kept in this order; "Name" is the join key.
CHECKM2_COLS = [
    "Name",
    "Completeness", "Contamination",
    "Completeness_Model_Used", "Translation_Table_Used",
    "Coding_Density", "Contig_N50", "Average_Gene_Length",
    "Genome_Size", "GC_Content", "Total_Coding_Sequences",
    "Additional_Notes",
]


def load_checkm2(path: Path) -> pd.DataFrame:
    """Load + normalise CheckM2's quality_report.tsv (lower-snake + prefix).

    CheckM2 strips ``.gz`` from input file names but keeps ``.fna`` / ``.fa`` /
    ``.fasta``, so ``Name`` looks like ``GCA_013733775.1.fna``. Strip those
    extensions so the join key matches ``scoring_accession`` (the bare
    accession used by ``build_lra_discovery``).
    """
    df = pd.read_csv(path, sep="\t", low_memory=False)
    keep = [c for c in CHECKM2_COLS if c in df.columns]
    df = df[keep].rename(columns={"Name": "scoring_accession"})
    df["scoring_accession"] = (
        df["scoring_accession"].astype(str)
        .str.replace(r"\.(fna|fa|fasta)(\.gz)?$", "", regex=True)
    )
    rename_map = {c: f"checkm2_{c.lower()}" for c in df.columns if c != "scoring_accession"}
    return df.rename(columns=rename_map)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — merge CheckM2 metrics into ``lra_discovery.tsv``."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discovery-tsv", type=Path, default=DEFAULT_DISCOVERY)
    ap.add_argument("--checkm2-tsv",   type=Path, default=DEFAULT_CHECKM2_TSV)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print join stats but don't write back.")
    args = ap.parse_args(argv)

    print(f"discovery_tsv : {args.discovery_tsv}")
    print(f"checkm2_tsv   : {args.checkm2_tsv}")

    disc = pd.read_csv(args.discovery_tsv, sep="\t", low_memory=False, dtype=str).fillna("")
    cm2  = load_checkm2(args.checkm2_tsv)
    print(f"\ndiscovery rows : {len(disc)}")
    print(f"checkm2 rows   : {len(cm2)}")

    # Drop any previous checkm2_* columns so re-runs cleanly replace them.
    stale = [c for c in disc.columns if c.startswith("checkm2_")]
    if stale:
        print(f"dropping {len(stale)} stale checkm2_* columns: {stale}")
        disc = disc.drop(columns=stale)

    merged = disc.merge(cm2, how="left", on="scoring_accession", validate="many_to_one")
    matched = merged["checkm2_completeness"].notna().sum() if "checkm2_completeness" in merged.columns else 0
    print(f"\nrows with checkm2_completeness : {matched} / {len(merged)} "
          f"({100 * matched / max(len(merged), 1):.1f}%)")

    # Spot-check: any CheckM2 rows that didn't match any discovery row?
    orphan = set(cm2["scoring_accession"]) - set(disc["scoring_accession"])
    if orphan:
        print(f"WARN: {len(orphan)} CheckM2 results have no matching discovery row "
              f"(first 5: {sorted(orphan)[:5]})")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = args.discovery_tsv.with_suffix(f".bak.{ts}.tsv")
    args.discovery_tsv.rename(backup)
    print(f"\nbacked up existing → {backup.name}")
    merged.to_csv(args.discovery_tsv, sep="\t", index=False)
    print(f"wrote {args.discovery_tsv}  rows={len(merged)}  cols={len(merged.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
