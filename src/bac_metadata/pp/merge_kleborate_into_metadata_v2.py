#!/usr/bin/env python3
"""Merge Kleborate-on-LRA output into metadata_v2 + run the KPSC cascade (G.2).

Reads:
  - ``metadata_v2_all_samples_and_columns.tsv``
  - Every ``<kleborate_lra_out>/kleborate_*_complex_output.tsv`` typing
    module from ``run_kleborate_lra collate``. Kleborate v3 splits its
    output by detected complex — we have one file for KpSC genomes
    (``klebsiella_pneumo_complex_output.txt``), one for KoSC contamination
    (``klebsiella_oxytoca_complex_output.txt``), and possibly others. All
    typing tables share the species column so we just concatenate them.
    ``*_hAMRonization_output.tsv`` (AMR-hit tables) are *not* read here.

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

# Glob (relative to --kleborate-out) for the collated typing-table files,
# one per Kleborate-detected complex. Excludes hAMRonization (AMR hit) tables.
DEFAULT_TYPING_GLOB = "kleborate_*_complex_output.tsv"

# Kleborate v3 column naming: namespaced "<scheme>__<module>__<field>".
KLEB_SPECIES_COL = "enterobacterales__species__species"
KLEB_STRAIN_COL  = "Sample"  # collate renames Kleborate's "strain" → "Sample"

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

# Accept either versioned (GCA_X.Y) or bare (GCA_X) accessions — Kleborate's
# output uses the file stem, which is bare, while metadata_v2.Sample is
# versioned. Both _bare() through to the same key.
_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")


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
    if KLEB_STRAIN_COL not in kleb.columns:
        raise KeyError(f"Kleborate output missing '{KLEB_STRAIN_COL}' column "
                       "(collate renames Kleborate's 'strain' column).")
    if KLEB_SPECIES_COL not in kleb.columns:
        raise KeyError(f"Kleborate output missing '{KLEB_SPECIES_COL}' column.")

    kleb = kleb.copy()
    kleb["_bare"] = kleb[KLEB_STRAIN_COL].map(_bare)
    kleb = kleb.drop_duplicates("_bare")
    species_map = kleb.set_index("_bare")[KLEB_SPECIES_COL].to_dict()

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
                    help="Dir containing the collated Kleborate typing TSVs.")
    ap.add_argument("--typing-glob",  type=str,  default=DEFAULT_TYPING_GLOB,
                    help="Glob (relative to --kleborate-out) for typing-table TSVs.")
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    typing_paths = sorted(args.kleborate_out.glob(args.typing_glob))
    print(f"metadata_v2  : {args.metadata_v2}")
    print(f"kleborate    : {args.kleborate_out} / {args.typing_glob}")
    print(f"  matched files: {len(typing_paths)}")
    for p in typing_paths:
        print(f"    {p.name}")
    if not typing_paths:
        print(f"FATAL: no Kleborate typing TSVs matching '{args.typing_glob}' under {args.kleborate_out}",
              file=sys.stderr)
        return 2

    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    kleb_frames = []
    for p in typing_paths:
        df = pd.read_csv(p, sep="\t", low_memory=False)
        df["_source_file"] = p.name
        kleb_frames.append(df)
    kleb = pd.concat(kleb_frames, ignore_index=True, sort=False)
    print(f"\nmetadata_v2 rows  : {len(meta):,}")
    print(f"kleborate rows    : {len(kleb):,}  (concatenated from {len(typing_paths)} complex files)")

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
