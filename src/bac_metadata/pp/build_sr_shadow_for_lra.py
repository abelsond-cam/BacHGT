#!/usr/bin/env python3
"""Build sr_shadow_for_lra.tsv: freeze SR-side QC + Kleborate for paired rows (G.3).

Reads:
  - ``metadata_final_curated_all_samples_and_columns.tsv`` (v1 — has the
    SR-side QC + Kleborate values before the v2 build flipped Sample +
    overwrote Kleborate on audit-matched rows).
  - ``metadata_v2_all_samples_and_columns.tsv`` (v2 — has the lra_final_set
    flag, sr_biosample on every paired row, and the lra_gca / lra_gcf
    pointer to the LRA that replaced the SR row).

Emits ``sr_shadow_for_lra.tsv`` — one row per paired SR+LR sample
(~2,967 rows). Each row carries the SR-side state at the moment v2 was
built, so the paired LRA-vs-SR comparison in G.4 can compute deltas
without losing the SR-Kleborate baseline.

Run this **before** the G.2 Kleborate cascade overwrites
``metadata_v2.species`` / ``is_kpsc`` on every ``lra_final_set=True``
row. After the cascade fires, the SR-derived Kleborate calls are gone
from v2 and would have to be recovered from v1 — which is exactly what
this shadow table preserves.

Usage::

    uv run python -m bac_metadata.pp.build_sr_shadow_for_lra --dry-run
    uv run python -m bac_metadata.pp.build_sr_shadow_for_lra
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V1 = DATA_ROOT / "david/final/metadata_final_curated_all_samples_and_columns.tsv"
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_OUT_PATH    = DATA_ROOT / "david/final/sr_shadow_for_lra.tsv"

# ─── COLUMN POLICY ────────────────────────────────────────────────────────────

# Identity/QC columns to copy directly from v1 (prefixed with sr_ in output).
QC_COLUMNS = [
    "run_accession",
    "assembly_file",
    "gff_file",
    "contig_count",
    "N50",
    "largest_contig",
    "total_size",
    "ambiguous_bases",
    "QC_warnings",
]

# Kleborate-derived typing/species columns (prefixed with sr_ in output).
SPECIES_COLUMNS = [
    "species",
    "species_match",
    "scientific_name",
    "tax_id",
    "sub_species",
    "is_kpsc",
    "Species",  # legacy duplicate
]

# Acquired-AMR + virulence columns (the BSC structure) are pattern-matched
# rather than enumerated to stay robust to Kleborate version changes.
AMR_PATTERN_SUFFIXES = ("_acquired", "_chr", "_mutations")
# Locus/BSC columns recognised by their stable names from Kleborate's
# klebsiella_pneumo_complex output. Captures presence + per-gene presence
# (ybt*, clb*, iuc*, iro*, rmp*, etc.) without false positives on
# non-Kleborate columns.
VIRULENCE_PREFIXES = (
    "ybt", "Yersiniabactin", "spurious_ybt",
    "clb", "Colibactin", "spurious_clb",
    "iuc", "Aerobactin", "spurious_iuc",
    "iro", "Salmochelin", "spurious_iro",
    "rmp", "RmpADC", "rmpA2", "spurious_rmp",
    "wzi", "K_locus", "K_type", "O_locus", "O_type",
)


def _amr_columns(v1_cols: list[str]) -> list[str]:
    """Return all v1 columns ending in known AMR-class suffixes."""
    return [c for c in v1_cols if c.endswith(AMR_PATTERN_SUFFIXES)]


def _virulence_columns(v1_cols: list[str]) -> list[str]:
    """Return v1 columns matching the Kleborate virulence-locus prefixes."""
    return [c for c in v1_cols if c.startswith(VIRULENCE_PREFIXES)]


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


# ─── BUILD ────────────────────────────────────────────────────────────────────

def build_sr_shadow(v1: pd.DataFrame, v2: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Snapshot SR-side state for every paired SR+LR row in v2.

    Returns ``(shadow_df, stats)``.
    """
    stats: dict = {"v1_rows": len(v1), "v2_rows": len(v2)}

    lra = _coerce_bool(v2["lra_final_set"])
    biosample = v2.get("sr_biosample", pd.Series([pd.NA] * len(v2)))
    paired_mask = lra & biosample.notna() & (biosample.astype(str) != "") & (biosample.astype(str).str.lower() != "nan")
    paired = v2.loc[paired_mask].copy()
    stats["paired_rows_in_v2"] = len(paired)

    # Lookup v1 rows by Sample == sr_biosample. v1's Sample for SR rows is the
    # BioSample (SAMEA/SAMN/SAMD); for is_refseq rows it's a GCF/GCA. We want
    # the SR partner row in both cases — its Sample IS the v2.sr_biosample.
    v1_indexed = v1.set_index(v1["Sample"].astype(str), drop=False)
    looked_up_idx = paired["sr_biosample"].astype(str).map(
        lambda b: b if b in v1_indexed.index else None
    )
    stats["paired_with_v1_match"]    = int(looked_up_idx.notna().sum())
    stats["paired_without_v1_match"] = int(looked_up_idx.isna().sum())

    # Build the shadow rows. For rows without a v1 match, the SR-side cols
    # stay NaN — surfaced in the stats but not gated, since some audit-matched
    # samples may have v1 entries that don't actually have curated metadata.
    v1_cols = list(v1.columns)
    amr_cols = _amr_columns(v1_cols)
    vir_cols = _virulence_columns(v1_cols)
    snapshot_cols = QC_COLUMNS + SPECIES_COLUMNS + amr_cols + vir_cols
    snapshot_cols = [c for c in snapshot_cols if c in v1.columns]
    snapshot_cols = list(dict.fromkeys(snapshot_cols))  # dedupe, preserve order
    stats["sr_columns_snapshotted"] = len(snapshot_cols)
    stats["snapshot_split"] = {
        "qc":        len([c for c in QC_COLUMNS if c in snapshot_cols]),
        "species":   len([c for c in SPECIES_COLUMNS if c in snapshot_cols]),
        "amr":       len([c for c in amr_cols if c in snapshot_cols]),
        "virulence": len([c for c in vir_cols if c in snapshot_cols]),
    }

    # Initialise the output frame with the identity / pointer columns.
    out = pd.DataFrame({
        "sr_biosample":          paired["sr_biosample"].astype(str).values,
        "replaced_by_v2_sample": paired["Sample"].values,
        "replaced_by_lra_gca":   paired.get("lra_gca", pd.Series([pd.NA] * len(paired))).values,
        "replaced_by_lra_gcf":   paired.get("lra_gcf", pd.Series([pd.NA] * len(paired))).values,
    })

    # Pull each snapshot column off v1 via the looked-up indices.
    for col in snapshot_cols:
        sr_col = f"sr_{col}"
        values = pd.Series(pd.NA, index=range(len(paired)))
        matched = looked_up_idx.notna().to_numpy()
        if matched.any():
            biosamples = looked_up_idx.dropna().astype(str)
            values_matched = v1_indexed.loc[biosamples.values, col].values
            values.loc[matched] = values_matched
        out[sr_col] = values.values

    return out, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — build + write the SR-shadow TSV."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v1", type=Path, default=DEFAULT_METADATA_V1)
    ap.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--out",         type=Path, default=DEFAULT_OUT_PATH)
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    print(f"metadata_v1 : {args.metadata_v1}")
    print(f"metadata_v2 : {args.metadata_v2}")
    print(f"out         : {args.out}")

    v1 = pd.read_csv(args.metadata_v1, sep="\t", low_memory=False)
    v2 = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    print(f"\nv1 rows: {len(v1):,}")
    print(f"v2 rows: {len(v2):,}")

    shadow, stats = build_sr_shadow(v1, v2)

    print("\n=== SR-shadow stats ===")
    for k, v in stats.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk:12s}: {vv}")
        else:
            print(f"  {k:30s}: {v}")
    print(f"\nshadow rows: {len(shadow):,}")
    print(f"shadow cols: {len(shadow.columns)}")
    print("first 5 column heads:", shadow.columns.tolist()[:5])
    print("last  5 column heads:", shadow.columns.tolist()[-5:])

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = args.out.with_suffix(f".bak.{ts}.tsv")
        args.out.rename(bak)
        print(f"\nbacked up existing → {bak.name}")
    shadow.to_csv(args.out, sep="\t", index=False)
    print(f"wrote {args.out}  rows={len(shadow):,}  cols={len(shadow.columns)}")

    # Sanity gate: every paired row must have an sr_biosample (key).
    failed = False
    if shadow["sr_biosample"].isna().any() or (shadow["sr_biosample"] == "").any():
        print("\nERROR: some shadow rows have empty sr_biosample (key).", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
