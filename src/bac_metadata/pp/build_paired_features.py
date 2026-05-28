#!/usr/bin/env python3
"""Build the paired-cohort feature tables (G.4.5).

Three outputs under ``<RDS>/david/processed/complete_vs_sr_genomes/``:

- ``paired_index.tsv`` — one row per paired SR+LR sample (~2,919). Carries
  the join key (lra_sample + sr_biosample) plus per-LRA NCBI assembly
  metadata (``level`` / ``is_complete``), CheckM2 QC, and v2 species/KPSC
  flags — everything you need to filter the paired cohort before running
  paired stats (e.g. ``level == "Complete Genome"``).
- ``lra_features.tsv`` — paired LRAs only, Kleborate (species + MLST +
  virulence BSCs + AMR + K/O loci) + ISEScan IS-family counts. Keyed by
  ``Sample`` (GCF/GCA versioned).
- ``sr_features.tsv`` — paired SR partners, same column families as
  ``lra_features.tsv`` but sourced from the seb-tree sidecars. Keyed by
  ``BioSample`` (SAM*).

paired_index.tsv is written FIRST and emitted regardless of whether the
feature TSVs build cleanly — so if you only need the paired-cohort index
for cohort filtering, ``--paired-index-only`` skips the feature work.

Design + provenance: see plan §G.4.5 in
``~/.claude/plans/in-src-bac-data-we-look-curried-dragonfly.md``.

Usage::

    # Default — write all three TSVs:
    uv run python -m bac_metadata.pp.build_paired_features

    # Cohort index only (fast; for filtering work):
    uv run python -m bac_metadata.pp.build_paired_features --paired-index-only

    # Dry run (stats only, nothing written):
    uv run python -m bac_metadata.pp.build_paired_features --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2  = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_LRA_FINAL_SET = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lra_final_list.tsv"
DEFAULT_SR_KLEBORATE = DATA_ROOT / "seb/sr_kleborate_v3.2.4.tsv"
DEFAULT_SR_ISESCAN   = DATA_ROOT / "seb/sr_isescan_family_counts.tsv"
DEFAULT_OUT_DIR      = DATA_ROOT / "david/processed/complete_vs_sr_genomes"

# ─── COLUMN POLICY ────────────────────────────────────────────────────────────

# What goes into paired_index.tsv. Identity columns + per-LRA metadata
# sufficient to filter the cohort (NCBI level, CheckM2, provenance flags,
# species/KPSC).
PAIRED_INDEX_LRA_FINAL_SET_COLS = [
    "tier",                       # "GCF" / "GCA"
    "level",                      # NCBI assembly_level: "Complete Genome", "Chromosome", "Scaffold", "Contig", NaN
    "is_complete",                # bool: level == "Complete Genome"
    "is_refseq",                  # bool: source had a RefSeq curation
    "is_norway",                  # bool: from Norway Table S1
    "stale_refseq",               # bool: NCBI suppression-aware
    "checkm2_completeness",
    "checkm2_contamination",
    "checkm2_contig_n50",
    "checkm2_total_contigs",
    "checkm2_genome_size",
    "checkm2_gc_content",
]
PAIRED_INDEX_V2_COLS = [
    "species",                    # post-G.2 LR-Kleborate species
    "scientific_name",            # ENA-derived species
    "is_kpsc",
    "kpsc_final_list",
]

# Mirror the Kleborate column policy already enumerated in build_sr_shadow_for_lra.
# Imported via Python rather than re-defined to keep one source of truth.
try:
    from bac_metadata.pp.build_sr_shadow_for_lra import (
        SPECIES_COLUMNS, MLST_COLUMNS,
        _amr_columns, _virulence_columns,
    )
except ImportError:  # standalone smoke-test fallback
    SPECIES_COLUMNS = [
        "species", "species_match", "scientific_name", "tax_id",
        "sub_species", "is_kpsc",
    ]
    MLST_COLUMNS = ["gapA", "infB", "mdh", "pgi", "phoE", "rpoB", "tonB", "ST"]

    def _amr_columns(cols):
        return [c for c in cols if c.endswith(("_acquired", "_chr", "_mutations"))]

    def _virulence_columns(cols):
        prefixes = ("ybt", "Yersiniabactin", "spurious_ybt", "clb", "Colibactin",
                    "spurious_clb", "iuc", "Aerobactin", "spurious_iuc", "iro",
                    "Salmochelin", "spurious_iro", "rmp", "RmpADC", "rmpA2",
                    "spurious_rmp", "wzi", "K_locus", "K_type", "O_locus", "O_type")
        return [c for c in cols if c.startswith(prefixes)]


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _kleborate_feature_cols(df_cols: list[str]) -> list[str]:
    """Return all Kleborate feature columns present in the given column list."""
    amr = _amr_columns(df_cols)
    vir = _virulence_columns(df_cols)
    base = SPECIES_COLUMNS + MLST_COLUMNS + amr + vir
    return [c for c in dict.fromkeys(base) if c in df_cols]


# ─── BUILD ────────────────────────────────────────────────────────────────────

def build_paired_index(
    v2: pd.DataFrame,
    lra_final_list: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """One row per paired SR+LR sample with per-LRA metadata for cohort filtering.

    Join: ``v2.Sample`` ↔ ``lra_final_list.scoring_accession`` (both
    versioned GCF/GCA accessions).
    """
    stats: dict = {"v2_rows": len(v2), "lra_final_list_rows": len(lra_final_list)}

    # Select paired rows from v2.
    lra_mask = _coerce_bool(v2["lra_final_list"])
    biosample = v2["sr_biosample"].astype(str)
    paired_mask = lra_mask & v2["sr_biosample"].notna() & (biosample != "") & (biosample.str.lower() != "nan")
    paired_v2 = v2.loc[paired_mask].copy()
    stats["paired_rows"] = len(paired_v2)

    # Build the LRA-side join frame from lra_final_list.
    lra_cols = ["scoring_accession"] + [c for c in PAIRED_INDEX_LRA_FINAL_SET_COLS if c in lra_final_list.columns]
    lra_slice = lra_final_list[lra_cols].drop_duplicates("scoring_accession", keep="first").copy()

    # Rename to lra_<col> to keep namespaces clean in the output.
    rename_lra = {c: f"lra_{c}" for c in lra_cols if c != "scoring_accession"}
    lra_slice = lra_slice.rename(columns=rename_lra)
    lra_slice = lra_slice.rename(columns={"level": "lra_assembly_level"} if "level" in rename_lra.values() else {})
    # Above only fires if 'level' became 'lra_level' first; do the canonical rename explicitly:
    if "lra_level" in lra_slice.columns:
        lra_slice = lra_slice.rename(columns={"lra_level": "lra_assembly_level"})

    # Merge.
    merged = paired_v2.merge(
        lra_slice,
        left_on="Sample",
        right_on="scoring_accession",
        how="left",
    )
    n_matched = int(merged["scoring_accession"].notna().sum())
    stats["paired_with_lra_final_list_match"]    = n_matched
    stats["paired_without_lra_final_list_match"] = len(merged) - n_matched

    # Compose the final paired_index columns.
    v2_cols = [c for c in PAIRED_INDEX_V2_COLS if c in merged.columns]
    rename_v2 = {c: f"lra_{c}" if c in {"species", "scientific_name", "is_kpsc"} else c
                 for c in v2_cols}
    merged = merged.rename(columns=rename_v2)

    identity_cols = ["Sample", "sr_biosample", "lra_gca", "lra_gcf"]
    identity_cols = [c for c in identity_cols if c in merged.columns]
    lra_meta_cols = (
        ["lra_assembly_level"]
        + [f"lra_{c}" for c in PAIRED_INDEX_LRA_FINAL_SET_COLS
           if c != "level" and f"lra_{c}" in merged.columns]
        + [v for v in rename_v2.values() if v in merged.columns and v != "lra_assembly_level"]
    )
    # Dedupe while preserving order.
    lra_meta_cols = list(dict.fromkeys(lra_meta_cols))

    out = merged[identity_cols + lra_meta_cols].rename(columns={"Sample": "lra_sample"})

    # Summary stats for the printout — most useful: assembly_level distribution.
    if "lra_assembly_level" in out.columns:
        stats["assembly_level_distribution"] = (
            out["lra_assembly_level"].value_counts(dropna=False).to_dict()
        )
    if "lra_is_complete" in out.columns:
        stats["lra_is_complete_distribution"] = (
            out["lra_is_complete"].astype(str).value_counts(dropna=False).to_dict()
        )
    return out, stats


def build_lra_features(
    v2: pd.DataFrame,
    paired_lra_samples: set[str],
    sr_isescan: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """LRA-side features for paired samples: Kleborate cols + IS_<family> cols.

    Reads Kleborate features from v2 (already merged in by G.2 cascade) and
    ISEScan ``IS_<family>`` counts already on v2 (from
    ``merge_isescan_into_metadata_v2.py``).
    """
    stats: dict = {}
    paired = v2[v2["Sample"].astype(str).isin(paired_lra_samples)].copy()

    feat_cols = _kleborate_feature_cols(list(paired.columns))
    is_cols = [c for c in paired.columns if c.startswith("IS_")]
    stats["lra_kleborate_cols"] = len(feat_cols)
    stats["lra_isescan_cols"]   = len(is_cols)

    out = paired[["Sample"] + feat_cols + is_cols].copy()
    stats["lra_rows"] = len(out)
    stats["lra_cols"] = len(out.columns)
    return out, stats


def build_sr_features(
    sr_kleborate: pd.DataFrame,
    sr_isescan: pd.DataFrame | None,
    paired_biosamples: set[str],
) -> tuple[pd.DataFrame, dict]:
    """SR-side features for paired samples: Kleborate (from sidecar) + IS_<family>.

    Note: no ``sr_`` prefix on columns here — the table identity makes it
    unambiguous. The paired-stats driver adds the prefix on-merge.
    """
    stats: dict = {}
    sk = sr_kleborate[sr_kleborate["BioSample"].astype(str).isin(paired_biosamples)].copy()
    sk = sk.drop_duplicates("BioSample", keep="first")
    stats["sr_kleborate_rows"] = len(sk)

    # Drop import-time metadata cols.
    sk = sk.drop(columns=[c for c in ("_typing_source", "_seb_batch") if c in sk.columns],
                 errors="ignore")

    # Append ISEScan IS_<family> counts.
    if sr_isescan is not None and not sr_isescan.empty:
        ise_key = "Sample" if "Sample" in sr_isescan.columns else sr_isescan.columns[0]
        ise = sr_isescan.drop_duplicates(ise_key, keep="first").copy()
        ise = ise[ise[ise_key].astype(str).isin(paired_biosamples)]
        fam_cols = [c for c in ise.columns if c != ise_key]
        rename = {c: f"IS_{c}" for c in fam_cols}
        ise = ise.rename(columns={ise_key: "BioSample", **rename})
        sk = sk.merge(ise, on="BioSample", how="left")
        stats["sr_isescan_rows_joined"] = int(sk[f"IS_{fam_cols[0]}"].notna().sum()) if fam_cols else 0
        stats["sr_isescan_cols"] = len(fam_cols)

    stats["sr_rows"] = len(sk)
    stats["sr_cols"] = len(sk.columns)
    return sk, stats


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry: build paired_index + lra_features + sr_features."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2",      type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--lra-final-list",   type=Path, default=DEFAULT_LRA_FINAL_SET)
    ap.add_argument("--sr-kleborate",     type=Path, default=DEFAULT_SR_KLEBORATE)
    ap.add_argument("--sr-isescan",       type=Path, default=DEFAULT_SR_ISESCAN)
    ap.add_argument("--out-dir",          type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--paired-index-only", action="store_true",
                    help="Only build paired_index.tsv; skip feature TSVs.")
    ap.add_argument("--dry-run",          action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    print(f"metadata_v2      : {args.metadata_v2}")
    print(f"lra_final_list    : {args.lra_final_list}")
    if not args.paired_index_only:
        print(f"sr_kleborate     : {args.sr_kleborate}")
        print(f"sr_isescan       : {args.sr_isescan}")
    print(f"out_dir          : {args.out_dir}")

    v2  = pd.read_csv(args.metadata_v2,   sep="\t", low_memory=False)
    lra = pd.read_csv(args.lra_final_list, sep="\t", low_memory=False)
    print(f"\nv2 rows: {len(v2):,}    lra_final_list rows: {len(lra):,}")

    # === paired_index.tsv (always built first) ===
    paired_index, idx_stats = build_paired_index(v2, lra)
    print("\n=== paired_index stats ===")
    for k, v in idx_stats.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {str(kk):24s}: {vv}")
        else:
            print(f"  {k:36s}: {v}")
    print(f"\npaired_index shape: {paired_index.shape}")
    print(f"paired_index cols : {paired_index.columns.tolist()}")

    if not args.dry_run:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        out_path = args.out_dir / "paired_index.tsv"
        paired_index.to_csv(out_path, sep="\t", index=False)
        print(f"\nwrote {out_path}  rows={len(paired_index):,}  cols={len(paired_index.columns)}")

    if args.paired_index_only:
        print("\n--paired-index-only set; skipping feature TSVs.")
        return 0

    # === lra_features.tsv ===
    paired_lra_samples = set(paired_index["lra_sample"].astype(str).tolist())
    lra_features, lra_stats = build_lra_features(v2, paired_lra_samples)
    print("\n=== lra_features stats ===")
    for k, v in lra_stats.items():
        print(f"  {k:30s}: {v}")
    if not args.dry_run:
        out_path = args.out_dir / "lra_features.tsv"
        lra_features.to_csv(out_path, sep="\t", index=False)
        print(f"wrote {out_path}  rows={len(lra_features):,}  cols={len(lra_features.columns)}")

    # === sr_features.tsv ===
    paired_biosamples = set(paired_index["sr_biosample"].astype(str).tolist())
    sk = pd.read_csv(args.sr_kleborate, sep="\t", low_memory=False) if args.sr_kleborate.exists() else pd.DataFrame()
    se = pd.read_csv(args.sr_isescan,   sep="\t", low_memory=False) if args.sr_isescan.exists()   else pd.DataFrame()
    print(f"\nsr_kleborate sidecar rows: {len(sk):,}")
    print(f"sr_isescan   sidecar rows: {len(se):,}")
    if sk.empty:
        print("WARN: no SR-Kleborate sidecar; skipping sr_features.tsv", file=sys.stderr)
    else:
        sr_features, sr_stats = build_sr_features(sk, se if not se.empty else None, paired_biosamples)
        print("\n=== sr_features stats ===")
        for k, v in sr_stats.items():
            print(f"  {k:30s}: {v}")
        if not args.dry_run:
            out_path = args.out_dir / "sr_features.tsv"
            sr_features.to_csv(out_path, sep="\t", index=False)
            print(f"wrote {out_path}  rows={len(sr_features):,}  cols={len(sr_features.columns)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
