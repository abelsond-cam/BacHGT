#!/usr/bin/env python3
"""Apply the locked LRA acceptance rule → emit ``lra_final_list.tsv`` + ``lra_rejected.tsv``.

build_lra_set.py
----------------
Phase E. Consumes the fully-annotated ``lra_discovery.tsv`` (Phase B.8 output:
one row per biological assembly with CheckM2 metrics joined on
``scoring_accession``) and materialises the accepted LRA cohort by applying
three locked criteria — matching `lra_quality_cutoffs.ipynb` §8 exactly.

Locked rule (2026-05-25):

    MIN_COMPLETENESS  = 99.0          (hardcoded; isolate high-quality)
    MAX_CONTAMINATION = 5.0           (hardcoded; MIGS / GTDB threshold)
    MAX_GENOME_SIZE   = worst GCF     (data-derived; oversized = contamination)

Outputs (both keyed on ``scoring_accession``)::

    <out-dir>/lra_final_list.tsv             accepted set  (expected: 5,521 rows)
    <out-dir>/lr_discovery/lra_rejected.tsv  rejected set with `reason` column (expected: 36)

Output filename ``lra_final_list.tsv`` is the canonical name (matches the
``lra_final_list`` boolean column on metadata_v2). An older run wrote
``lra_set.tsv``; that file is superseded.

The two TSVs are partitioned, not deduplicated — each row in
``lra_discovery.tsv`` lands in exactly one. The schema is the discovery TSV's
columns plus ``tier``, ``is_complete``, and ``accept_reason``.

Usage::

    uv run python -m bac_data.lr_data.build_lra_set                  # write outputs
    uv run python -m bac_data.lr_data.build_lra_set --dry-run        # print stats only
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_DISCOVERY = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lr_discovery/lra_discovery.tsv"
DEFAULT_OUT_DIR   = DATA_ROOT / "david/processed/complete_vs_sr_genomes"

# ─── LOCKED THRESHOLDS (match `lra_quality_cutoffs.ipynb` §8) ────────────────

MIN_COMPLETENESS  = 99.0   # %   — hardcoded; isolate high-quality
MAX_CONTAMINATION = 5.0    # %   — MIGS / GTDB threshold (Bowers 2017)
# MAX_GENOME_SIZE is data-derived (worst-GCF) — computed at runtime below.

# ─── OUTPUT SCHEMA ────────────────────────────────────────────────────────────

# Columns shared by both lra_final_list.tsv and lra_rejected.tsv. ``accept_reason`` is
# the last column; for the accepted set it is "accept" everywhere.
OUTPUT_COLS = [
    # identity
    "scoring_accession", "tier", "GCA", "GCF", "Sample", "related_lr_run_accession",
    # provenance + NCBI metadata
    "source_audit", "source_norway", "source_refseq_metadata",
    "is_norway", "is_refseq", "stale_refseq",
    "level", "library_class", "is_complete", "is_hybrid", "is_reference_genome",
    "ncbi_sequencing_tech", "ncbi_assembly_method",
    # checkm2 metrics (full set — even the non-gates, for downstream filtering)
    "checkm2_completeness", "checkm2_contamination", "checkm2_genome_size",
    "checkm2_gc_content", "checkm2_contig_n50", "checkm2_total_contigs",
    "checkm2_max_contig_length", "checkm2_total_coding_sequences",
    "checkm2_average_gene_length", "checkm2_coding_density",
    "checkm2_completeness_model_used", "checkm2_translation_table_used",
    "checkm2_additional_notes",
    # paths
    "expected_fasta_path", "fasta_on_disk",
    # verdict
    "accept_reason",
]


# ─── CLASSIFY ─────────────────────────────────────────────────────────────────

def classify(row: pd.Series, max_genome_size: float) -> str:
    """Return ``accept`` or the first failing criterion's name."""
    if pd.isna(row["checkm2_completeness"]):
        return "no_checkm2"
    if row["checkm2_completeness"] < MIN_COMPLETENESS:
        return "completeness"
    if row["checkm2_contamination"] > MAX_CONTAMINATION:
        return "contamination"
    if row["checkm2_genome_size"] > max_genome_size:
        return "genome_size"
    return "accept"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — partition discovery TSV into accepted + rejected sets."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discovery-tsv", type=Path, default=DEFAULT_DISCOVERY)
    ap.add_argument("--out-dir",       type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print stats but don't write the output TSVs.")
    args = ap.parse_args(argv)

    print(f"discovery_tsv : {args.discovery_tsv}")
    print(f"out_dir       : {args.out_dir}")

    df = pd.read_csv(args.discovery_tsv, sep="\t", low_memory=False)
    # Coerce the boolean columns (round-tripped as strings).
    for b in ["source_audit", "source_norway", "source_refseq_metadata",
              "is_refseq", "is_norway", "stale_refseq", "download_needed"]:
        if b in df.columns:
            df[b] = df[b].astype(str).str.lower().isin({"true", "1", "yes"})

    # Derive tier + the NCBI-enrichment flags (all mechanical from level/library_class).
    df["tier"] = np.where(df["scoring_accession"].str.startswith("GCF_"), "GCF", "GCA")
    df["is_complete"] = df["level"].astype(str) == "Complete Genome"
    if "library_class" not in df.columns:
        df["library_class"] = "unknown"
    df["is_hybrid"] = df["library_class"].astype(str) == "hybrid"
    # "from RefSeq" = the scored assembly is a GCF (tier=="GCF"); equals
    # Sample.startswith("GCF_") once propagated to v2 (Sample == scoring_accession there).
    df["is_reference_genome"] = (
        df["is_complete"] & df["is_hybrid"] & df["scoring_accession"].astype(str).str.startswith("GCF_")
    )

    # Data-derived ceiling — worst-GCF genome size (i.e. the largest GCF; for
    # a ceiling criterion the "worst" sits at the upper extreme, not the lower).
    gcf_rows = df[df["tier"] == "GCF"]
    max_genome_size = float(gcf_rows["checkm2_genome_size"].max())
    print("\nLocked thresholds:")
    print(f"  MIN_COMPLETENESS  ≥ {MIN_COMPLETENESS}")
    print(f"  MAX_CONTAMINATION ≤ {MAX_CONTAMINATION}")
    print(f"  MAX_GENOME_SIZE   ≤ {max_genome_size:,.0f} bp  ({max_genome_size/1e6:.2f} Mb; worst-GCF)")

    df["accept_reason"] = df.apply(classify, axis=1, max_genome_size=max_genome_size)
    accepted = df[df["accept_reason"] == "accept"].copy()
    rejected = df[df["accept_reason"] != "accept"].copy()

    # ── Print verification block ────────────────────────────────────────────
    print(f"\nDiscovery rows : {len(df)}")
    print(f"  accepted     : {len(accepted)}")
    print(f"  rejected     : {len(rejected)}")
    print()
    print("=== accept rate by tier ===")
    print(
        df.groupby("tier")["accept_reason"]
          .agg(lambda s: f"{(s == 'accept').sum()} / {len(s)}  ({100 * (s == 'accept').sum() / len(s):.1f}%)")
          .to_string()
    )
    print()
    print("=== rejection reasons × tier ===")
    cross = (
        rejected.groupby(["tier", "accept_reason"]).size().unstack(fill_value=0)
                .reindex(index=["GCF", "GCA"])
                .reindex(columns=["no_checkm2", "completeness", "contamination", "genome_size"], fill_value=0)
    )
    print(cross.to_string())
    print()
    print("=== NCBI-enrichment flags within accepted ===")
    n_acc = len(accepted)
    print(f"  is_complete=True  (NCBI 'Complete Genome')        : {int(accepted['is_complete'].sum())} / {n_acc}")
    print(f"  is_hybrid=True    (library_class=='hybrid')       : {int(accepted['is_hybrid'].sum())} / {n_acc}")
    print(f"  is_reference_genome=True (complete∧hybrid∧GCF)    : {int(accepted['is_reference_genome'].sum())} / {n_acc}")
    print("  library_class breakdown (accepted):")
    for k, v in accepted["library_class"].fillna("unknown").value_counts().items():
        print(f"    {str(k):<12} : {int(v)}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    # Re-order columns deterministically; tolerate missing ones.
    cols = [c for c in OUTPUT_COLS if c in accepted.columns]
    accepted = accepted[cols].sort_values("scoring_accession").reset_index(drop=True)
    rejected = rejected[cols].sort_values(["accept_reason", "scoring_accession"]).reset_index(drop=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_accepted = args.out_dir / "lra_final_list.tsv"
    out_rejected = args.out_dir / "lr_discovery" / "lra_rejected.tsv"
    out_rejected.parent.mkdir(parents=True, exist_ok=True)

    # Back up any existing copies first so the run is non-destructive.
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for p in (out_accepted, out_rejected):
        if p.exists():
            backup = p.with_suffix(f".bak.{ts}.tsv")
            p.rename(backup)
            print(f"backed up existing → {backup.name}")

    accepted.to_csv(out_accepted, sep="\t", index=False)
    rejected.to_csv(out_rejected, sep="\t", index=False)
    print(f"\nwrote {out_accepted}  rows={len(accepted)}  cols={len(accepted.columns)}")
    print(f"wrote {out_rejected}  rows={len(rejected)}  cols={len(rejected.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
