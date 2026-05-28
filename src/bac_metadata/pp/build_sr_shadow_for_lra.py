#!/usr/bin/env python3
"""Build sr_shadow_for_lra.tsv: freeze SR-side QC + Kleborate for paired rows (G.3).

Reads:
  - ``metadata_final_curated_all_samples_and_columns.tsv`` (v1 — has the
    SR-side QC + Kleborate values before the v2 build flipped Sample +
    overwrote Kleborate on audit-matched rows).
  - ``metadata_v2_all_samples_and_columns.tsv`` (v2 — has the lra_final_list
    flag, sr_biosample on every paired row, and the lra_gca / lra_gcf
    pointer to the LRA that replaced the SR row).

Emits ``sr_shadow_for_lra.tsv`` — one row per paired SR+LR sample
(~2,967 rows). Each row carries the SR-side state at the moment v2 was
built, so the paired LRA-vs-SR comparison in G.4 can compute deltas
without losing the SR-Kleborate baseline.

Run this **before** the G.2 Kleborate cascade overwrites
``metadata_v2.species`` / ``is_kpsc`` on every ``lra_final_list=True``
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
DEFAULT_OUT_PATH    = DATA_ROOT / "david/processed/complete_vs_sr_genomes/sr_shadow_for_lra.tsv"

# Seb-tree SR-side sidecars produced by ``import_sr_kleborate`` /
# ``import_sr_isescan``. These fill the 957 priority-3 audit-matched
# biosamples whose Kleborate / ISEScan results live in seb/ but were
# never merged into v1.
DEFAULT_SR_KLEBORATE = DATA_ROOT / "seb/sr_kleborate_v3.2.4.tsv"
DEFAULT_SR_ISESCAN   = DATA_ROOT / "seb/sr_isescan_family_counts.tsv"

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

# Kleborate KpSC chromosomal MLST 7-locus scheme + ST. Captured for the
# paired SR-vs-LRA MLST comparison (housekeeping genes; failure to detect
# any is an assembly-quality signal).
MLST_COLUMNS = [
    "gapA", "infB", "mdh", "pgi", "phoE", "rpoB", "tonB", "ST",
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

def _fill_from_sidecar(
    merged: pd.DataFrame,
    sidecar: pd.DataFrame,
    key_col: str,
    sidecar_key: str,
    cols: list[str],
) -> tuple[pd.DataFrame, dict]:
    """Fill NaN values in ``cols`` of ``merged`` from a BioSample-keyed sidecar.

    Returns ``(merged, stats)``. ``stats`` reports rows-changed per column
    and a single ``filled_total`` count for the whole sidecar pass.
    """
    stats: dict = {}
    if sidecar.empty:
        stats["sidecar_rows"] = 0
        return merged, stats

    sc = sidecar.drop_duplicates(sidecar_key, keep="first").set_index(sidecar_key)
    # Only fill where the sidecar actually has the column.
    fillable = [c for c in cols if c in sc.columns]
    stats["sidecar_rows"]     = len(sc)
    stats["sidecar_cols_used"] = len(fillable)

    n_filled_total = 0
    keys = merged[key_col].astype(str)
    for c in fillable:
        existing = merged[c]
        # treat empty string + literal 'nan' as missing
        existing_str = existing.astype(str)
        is_missing = existing.isna() | (existing_str == "") | (existing_str.str.lower() == "nan")
        if not is_missing.any():
            continue
        new_vals = keys.map(sc[c])
        # Only fill rows that are both missing in v1 AND present in sidecar.
        to_fill = is_missing & new_vals.notna()
        if to_fill.any():
            merged.loc[to_fill, c] = new_vals[to_fill].values
            n_filled_total += int(to_fill.sum())
    stats["filled_total_cells"] = n_filled_total
    return merged, stats


def build_sr_shadow(
    v1: pd.DataFrame,
    v2: pd.DataFrame,
    sr_kleborate: pd.DataFrame | None = None,
    sr_isescan: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Snapshot SR-side state for every paired SR+LR row in v2.

    Optionally fills missing Kleborate columns from a BioSample-keyed
    seb-tree sidecar, and appends SR-ISEScan family counts as
    ``sr_IS_<family>`` columns.

    Returns ``(shadow_df, stats)``.
    """
    stats: dict = {"v1_rows": len(v1), "v2_rows": len(v2)}

    lra = _coerce_bool(v2["lra_final_list"])
    biosample = v2.get("sr_biosample", pd.Series([pd.NA] * len(v2)))
    biosample_str = biosample.astype(str)
    paired_mask = lra & biosample.notna() & (biosample_str != "") & (biosample_str.str.lower() != "nan")
    paired = v2.loc[paired_mask, [c for c in (
        "Sample", "sr_biosample", "lra_gca", "lra_gcf",
    ) if c in v2.columns]].copy()
    paired = paired.rename(columns={
        "Sample":      "replaced_by_v2_sample",
        "lra_gca":     "replaced_by_lra_gca",
        "lra_gcf":     "replaced_by_lra_gcf",
    })
    paired["sr_biosample"] = paired["sr_biosample"].astype(str)
    stats["paired_rows_in_v2"] = len(paired)

    # Determine the snapshot columns from v1.
    v1_cols = list(v1.columns)
    amr_cols = _amr_columns(v1_cols)
    vir_cols = _virulence_columns(v1_cols)
    snapshot_cols = QC_COLUMNS + SPECIES_COLUMNS + MLST_COLUMNS + amr_cols + vir_cols
    snapshot_cols = [c for c in snapshot_cols if c in v1.columns]
    snapshot_cols = list(dict.fromkeys(snapshot_cols))  # dedupe, preserve order
    stats["sr_columns_snapshotted"] = len(snapshot_cols)
    stats["snapshot_split"] = {
        "qc":        len([c for c in QC_COLUMNS if c in snapshot_cols]),
        "species":   len([c for c in SPECIES_COLUMNS if c in snapshot_cols]),
        "mlst":      len([c for c in MLST_COLUMNS if c in snapshot_cols]),
        "amr":       len([c for c in amr_cols if c in snapshot_cols]),
        "virulence": len([c for c in vir_cols if c in snapshot_cols]),
    }

    # Project v1 to (Sample, snapshot_cols), dedupe (some BioSamples appear in
    # multiple v1 rows: same BioSample, multiple ENA runs — keep the first).
    v1_sr = v1[["Sample"] + snapshot_cols].copy()
    v1_sr["Sample"] = v1_sr["Sample"].astype(str)
    v1_sr = v1_sr.drop_duplicates("Sample", keep="first")

    merged = paired.merge(
        v1_sr, left_on="sr_biosample", right_on="Sample", how="left", suffixes=("", "_v1"),
    ).drop(columns=["Sample"], errors="ignore")

    n_matched = int(merged[snapshot_cols[0]].notna().sum()) if snapshot_cols else 0
    stats["paired_with_v1_match"]    = n_matched
    stats["paired_without_v1_match"] = len(merged) - n_matched

    # Fill missing Kleborate-derived columns (SPECIES + MLST + AMR +
    # virulence) from the seb-tree sidecar. QC columns (contig_count, N50,
    # …) stay v1-sourced — those are SR-assembly QC and weren't re-run.
    if sr_kleborate is not None and not sr_kleborate.empty:
        kleborate_cols_for_fill = [
            c for c in (SPECIES_COLUMNS + MLST_COLUMNS + amr_cols + vir_cols)
            if c in snapshot_cols
        ]
        merged, fill_stats = _fill_from_sidecar(
            merged,
            sr_kleborate,
            key_col="sr_biosample",
            sidecar_key="BioSample",
            cols=kleborate_cols_for_fill,
        )
        stats["sr_kleborate_sidecar"] = fill_stats

    # Rename snapshot columns to sr_<col>.
    rename = {c: f"sr_{c}" for c in snapshot_cols}
    merged = merged.rename(columns=rename)

    # Order: identity columns first, then sr_* in (qc, species, amr, virulence) order.
    identity = ["sr_biosample", "replaced_by_v2_sample", "replaced_by_lra_gca", "replaced_by_lra_gcf"]
    identity = [c for c in identity if c in merged.columns]
    sr_cols  = [f"sr_{c}" for c in snapshot_cols]
    out = merged[identity + sr_cols].copy()

    # Append SR-ISEScan per-Sample family counts as sr_IS_<family> columns.
    if sr_isescan is not None and not sr_isescan.empty:
        ise_key = "Sample" if "Sample" in sr_isescan.columns else sr_isescan.columns[0]
        ise = sr_isescan.drop_duplicates(ise_key, keep="first").set_index(ise_key)
        # Family columns are everything except the key.
        fam_cols = [c for c in ise.columns if c != ise_key]
        renamed = {c: f"sr_IS_{c}" for c in fam_cols}
        sub = ise[fam_cols].rename(columns=renamed)
        out = out.merge(sub, how="left", left_on="sr_biosample", right_index=True)
        # Samples present in v2 but missing from the SR-ISEScan sidecar
        # carry NaN here — meaning "no SR ISEScan run available" (distinct
        # from "ran, found zero hits", which would be a populated row).
        # That distinction matters for the paired comparison: NaN → exclude
        # from the pair; 0 → genuine no-call.
        n_ise_matched = int(out[f"sr_IS_{fam_cols[0]}"].notna().sum()) if fam_cols else 0
        stats["sr_isescan_sidecar"] = {
            "families":         len(fam_cols),
            "paired_with_isescan": n_ise_matched,
            "paired_without_isescan": len(out) - n_ise_matched,
        }
    return out, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — build + write the SR-shadow TSV."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v1", type=Path, default=DEFAULT_METADATA_V1)
    ap.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--sr-kleborate", type=Path, default=DEFAULT_SR_KLEBORATE,
                    help="BioSample-keyed sidecar from import_sr_kleborate; "
                         "pass empty string to disable sidecar fill.")
    ap.add_argument("--sr-isescan",   type=Path, default=DEFAULT_SR_ISESCAN,
                    help="Sample-keyed per-family count sidecar from import_sr_isescan; "
                         "pass empty string to disable sidecar fill.")
    ap.add_argument("--out",         type=Path, default=DEFAULT_OUT_PATH)
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    print(f"metadata_v1  : {args.metadata_v1}")
    print(f"metadata_v2  : {args.metadata_v2}")
    print(f"sr_kleborate : {args.sr_kleborate}")
    print(f"sr_isescan   : {args.sr_isescan}")
    print(f"out          : {args.out}")

    v1 = pd.read_csv(args.metadata_v1, sep="\t", low_memory=False)
    v2 = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    print(f"\nv1 rows: {len(v1):,}")
    print(f"v2 rows: {len(v2):,}")

    sr_kleborate: pd.DataFrame | None = None
    if str(args.sr_kleborate):
        if args.sr_kleborate.exists():
            sr_kleborate = pd.read_csv(args.sr_kleborate, sep="\t", low_memory=False)
            print(f"sr_kleborate sidecar rows: {len(sr_kleborate):,}")
        else:
            print(f"NOTE: {args.sr_kleborate} not found; skipping sidecar fill.", file=sys.stderr)

    sr_isescan: pd.DataFrame | None = None
    if str(args.sr_isescan):
        if args.sr_isescan.exists():
            sr_isescan = pd.read_csv(args.sr_isescan, sep="\t", low_memory=False)
            print(f"sr_isescan sidecar rows: {len(sr_isescan):,}")
        else:
            print(f"NOTE: {args.sr_isescan} not found; skipping sidecar.", file=sys.stderr)

    shadow, stats = build_sr_shadow(v1, v2, sr_kleborate=sr_kleborate, sr_isescan=sr_isescan)

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
