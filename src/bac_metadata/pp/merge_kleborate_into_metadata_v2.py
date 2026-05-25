#!/usr/bin/env python3
"""Merge Kleborate-on-LRA output into metadata_v2 + run the KPSC cascade (G.2).

Reads:
  - ``metadata_v2_all_samples_and_columns.tsv``
  - ``<kleborate_lra_out>/kleborate_klebsiella_pneumo_complex_output.tsv``
    (the main per-genome typing module from ``run_kleborate_lra collate``)

For each ``lra_final_set=True`` row, the cascade:

  1. **species + scientific_name** — overwrite with the Kleborate call
     (LRA-derived; more accurate than the SR-derived values currently on
     audit-matched rows, and the only source for the 117 ingested orphans).
  2. **is_kpsc** — recompute as ``species`` ∈ KPSC species set
     (K. pneumoniae, K. variicola, K. quasipneumoniae *.subsp.*, K. africana,
     K. tropica). Catches both 5 + 6 subspecies form.
  3. **kpsc_final_list** — ``True`` iff this row is in
     ``lra_final_set AND is_kpsc``. Only fills rows where the existing
     value is NaN (the 117 ingested orphans) to avoid clobbering the
     curated whitelist on existing rows.
  4. **kleborate_needs_recall** — cleared (False) on rows that got a
     fresh Kleborate call.

Always backs up the existing metadata_v2 with a UTC-stamped ``.bak.*.tsv``
before overwriting.

Usage::

    uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2 --dry-run
    uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS + CONSTANTS ────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_KLEBORATE_OUT = DATA_ROOT / "david/processed/kleborate_lra"

# Default name of Kleborate v3's main per-genome typing module after collation.
# (The actual filename written by `kleborate -p kpsc` is
# `klebsiella_pneumo_complex_output.txt`, prefixed with `kleborate_` by collate.)
DEFAULT_TYPING_FILE = "kleborate_klebsiella_pneumo_complex_output.tsv"

# The species names Kleborate v3 emits for the KPSC. Match by prefix so we catch
# all subspecies variants without hard-coding the exact subspecies suffix:
#   "Klebsiella pneumoniae"
#   "Klebsiella variicola subsp. variicola"
#   "Klebsiella quasipneumoniae subsp. quasipneumoniae"
#   "Klebsiella quasipneumoniae subsp. similipneumoniae"
#   "Klebsiella africana"
#   "Klebsiella tropica"           (formerly K. variicola subsp. tropica)
KPSC_SPECIES_PREFIXES: tuple[str, ...] = (
    "Klebsiella pneumoniae",
    "Klebsiella variicola",
    "Klebsiella quasipneumoniae",
    "Klebsiella africana",
    "Klebsiella tropica",
)

_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")


def _bare(acc: object) -> str:
    if acc is None or pd.isna(acc):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1).split(".", 1)[0] if m else ""


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _is_kpsc(species: pd.Series) -> pd.Series:
    """True iff species starts with one of the KPSC genus-species prefixes."""
    s = species.astype(str)
    mask = pd.Series(False, index=species.index)
    for prefix in KPSC_SPECIES_PREFIXES:
        mask = mask | s.str.startswith(prefix)
    return mask


# ─── MAIN MERGE ───────────────────────────────────────────────────────────────

def apply_cascade(meta: pd.DataFrame, kleb: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply species → is_kpsc → kpsc_final_list cascade on lra_final_set rows.

    Returns ``(updated_meta, stats)``.
    """
    stats: dict = {}
    meta = meta.copy()

    # Kleborate's collated output keys on Sample (bare GCF/GCA). Each LRA in v2
    # has Sample = scoring_accession (versioned). Join via bare accession.
    if "Sample" not in kleb.columns:
        raise KeyError("Kleborate output missing 'Sample' column "
                       "(run collate which renames Kleborate's 'strain' column).")
    if "species" not in kleb.columns:
        raise KeyError("Kleborate output missing 'species' column.")

    kleb = kleb.copy()
    kleb["_bare"] = kleb["Sample"].map(_bare)
    kleb = kleb.drop_duplicates("_bare")
    species_map = kleb.set_index("_bare")["species"].to_dict()

    lra_mask = _coerce_bool(meta["lra_final_set"])
    stats["lra_final_set_rows"] = int(lra_mask.sum())

    # Find which v2 LRA rows have a Kleborate call.
    meta_bare = meta.loc[lra_mask, "Sample"].map(_bare)
    has_call = meta_bare.map(lambda b: b in species_map)
    stats["lra_rows_matched_to_kleborate"] = int(has_call.sum())
    stats["lra_rows_missing_kleborate"]    = int((~has_call).sum())

    # Apply species (only to matched rows; preserve NaN/existing otherwise).
    new_species = meta_bare.map(species_map)
    for col in ("species", "scientific_name"):
        if col not in meta.columns:
            meta[col] = pd.NA
    fill_idx = new_species.dropna().index
    meta.loc[fill_idx, "species"] = new_species.loc[fill_idx].values
    meta.loc[fill_idx, "scientific_name"] = new_species.loc[fill_idx].values

    # Recompute is_kpsc on every lra_final_set row whose species is now non-null.
    if "is_kpsc" not in meta.columns:
        meta["is_kpsc"] = pd.NA
    new_is_kpsc = _is_kpsc(meta.loc[fill_idx, "species"])
    meta.loc[fill_idx, "is_kpsc"] = new_is_kpsc.values
    stats["lra_rows_is_kpsc_true"]  = int(new_is_kpsc.sum())
    stats["lra_rows_is_kpsc_false"] = int(len(new_is_kpsc) - new_is_kpsc.sum())

    # Recompute kpsc_final_list only where currently NaN (the 117 ingested
    # orphans). Existing values are the curated whitelist — leave them alone.
    if "kpsc_final_list" not in meta.columns:
        meta["kpsc_final_list"] = pd.NA
    kpsc_nan_mask = meta["kpsc_final_list"].isna()
    nan_lra_indices = meta.index[lra_mask & kpsc_nan_mask & has_call.reindex(meta.index, fill_value=False)]
    stats["kpsc_final_list_filled_on_nan_rows"] = int(len(nan_lra_indices))
    if len(nan_lra_indices):
        meta.loc[nan_lra_indices, "kpsc_final_list"] = (
            _coerce_bool(meta.loc[nan_lra_indices, "lra_final_set"])
            & _coerce_bool(meta.loc[nan_lra_indices, "is_kpsc"])
        )
        n_true_filled = int(_coerce_bool(meta.loc[nan_lra_indices, "kpsc_final_list"]).sum())
        stats["kpsc_final_list_filled_True"]  = n_true_filled
        stats["kpsc_final_list_filled_False"] = int(len(nan_lra_indices) - n_true_filled)

    # Clear kleborate_needs_recall on rows that got a fresh call.
    if "kleborate_needs_recall" in meta.columns:
        meta.loc[fill_idx, "kleborate_needs_recall"] = False

    return meta, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — apply cascade + write."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2",  type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--kleborate-out", type=Path, default=DEFAULT_KLEBORATE_OUT,
                    help="Dir containing the collated Kleborate typing TSV.")
    ap.add_argument("--typing-file",  type=str,  default=DEFAULT_TYPING_FILE,
                    help="Name of the Kleborate typing-module TSV inside --kleborate-out.")
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    typing_path = args.kleborate_out / args.typing_file
    print(f"metadata_v2  : {args.metadata_v2}")
    print(f"kleborate    : {typing_path}")

    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    kleb = pd.read_csv(typing_path, sep="\t", low_memory=False)
    print(f"\nmetadata_v2 rows  : {len(meta):,}")
    print(f"kleborate rows    : {len(kleb):,}")

    updated, stats = apply_cascade(meta, kleb)

    print("\n=== Cascade stats ===")
    for k, v in stats.items():
        print(f"  {k:40s}: {v:,}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0 if stats.get("lra_rows_missing_kleborate", 0) == 0 else 1

    # Backup + overwrite in place.
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    print(f"\nbacked up existing → {bak.name}")
    updated.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"wrote {args.metadata_v2}  rows={len(updated):,}  cols={len(updated.columns)}")

    # Gate: every lra_final_set=True row must now have non-null species + is_kpsc.
    failed = False
    if stats.get("lra_rows_missing_kleborate", 0) > 0:
        print(f"\nWARNING: {stats['lra_rows_missing_kleborate']} LRA rows missing Kleborate calls "
              f"— re-submit the Slurm array for the failed chunks.", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
