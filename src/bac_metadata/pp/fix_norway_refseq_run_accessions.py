#!/usr/bin/env python3
"""Fix the schema of Norway-augmented is_refseq rows in metadata_v2 (G.1-followup).

Discovered during G.3 SR-shadow build: the 281 is_refseq rows that
``norway_tables1_integrate.augment_metadata`` appended to v1 have
``run_accession`` populated with the **ONT** (long-read) accession, not
an Illumina (short-read) accession. The augment code intended to put
Illumina in ``related_sr_run_accession``, but that column didn't exist in
v1 at write time, so the Illumina accession was silently dropped.

Net effect in metadata_v2:
- ``run_accession`` = ONT acc (wrongly classified as SR)
- ``lr_run_accession`` = NaN
- ``sr_biosample`` = NaN
- The Illumina accession is missing entirely

This module recovers the Illumina accession from
``norway_tables1_integration.tsv`` (which carries both ``illumina_acc``
and ``ont_acc`` per Norway BioSample) and rewrites the schema in place:

  ``run_accession``       ← ``illumina_acc`` (SR)
  ``lr_run_accession``    ← previous ``run_accession`` (= ONT)
  ``sr_biosample``        ← ``biosample`` from Norway integration
  ``lr_instrument_platform`` ← "OXFORD_NANOPORE"

The 281 rows then become genuine paired SR+LR rows. Backs up the
existing metadata_v2 with a UTC-stamped ``.bak.*.tsv``.

Run BEFORE the G.2 Kleborate cascade overwrites species/is_kpsc on
these rows.

Usage::

    uv run python -m bac_metadata.pp.fix_norway_refseq_run_accessions --dry-run
    uv run python -m bac_metadata.pp.fix_norway_refseq_run_accessions
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2     = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_NORWAY_INTEG    = DATA_ROOT / "david/processed/norway_tables1_integration.tsv"

_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")


def _bare(acc: object) -> str:
    if acc is None or pd.isna(acc):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1) if m else ""


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def fix_norway_rows(v2: pd.DataFrame, integ: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rewrite the schema of Norway is_refseq rows in v2.

    Returns ``(updated_v2, stats)``.
    """
    stats: dict = {"v2_rows": len(v2), "integration_rows": len(integ)}
    v2 = v2.copy()

    # Build a bare-accession → (biosample, illumina_acc, ont_acc) lookup
    # from the integration TSV. Skip rows with no resolved assembly.
    # NB: itertuples() mangles fieldnames starting with "_", so name the
    # derived columns without a leading underscore.
    integ = integ.copy()
    integ["gca_bare"] = integ["resolved_gca"].map(_bare)
    integ["gcf_bare"] = integ["resolved_refseq_gcf"].map(_bare)

    lookup: dict[str, dict] = {}
    for r in integ.itertuples(index=False):
        d = {
            "biosample":    getattr(r, "biosample", "") or "",
            "illumina_acc": getattr(r, "illumina_acc", "") or "",
            "ont_acc":      getattr(r, "ont_acc", "") or "",
        }
        for key in (getattr(r, "gca_bare", ""), getattr(r, "gcf_bare", "")):
            if key:
                lookup[key] = d
    stats["integration_keys"] = len(lookup)

    # Identify candidate v2 rows: is_complete_norway_genome=True is the
    # primary discriminator (set on every Norway-augmented row by the
    # original augment step + carried through G.1).
    if "is_complete_norway_genome" not in v2.columns:
        raise KeyError("metadata_v2 is missing 'is_complete_norway_genome' column.")

    candidates = _coerce_bool(v2["is_complete_norway_genome"])
    stats["candidate_norway_rows"] = int(candidates.sum())

    # For each candidate, look up the integration entry by bare Sample
    # (either GCA or GCF).
    v2_bare = v2.loc[candidates, "Sample"].map(_bare)
    matched_lookups = v2_bare.map(lambda b: lookup.get(b))
    stats["candidate_with_integration_match"] = int(matched_lookups.notna().sum())
    stats["candidate_without_integration_match"] = int(matched_lookups.isna().sum())

    # Ensure target columns exist.
    for col in ("lr_run_accession", "sr_biosample", "lr_instrument_platform"):
        if col not in v2.columns:
            v2[col] = pd.NA

    n_run_was_ont      = 0
    n_run_was_other    = 0
    n_run_was_empty    = 0
    n_illumina_missing = 0
    n_illumina_set     = 0

    for v2_idx, looked in matched_lookups.items():
        if looked is None:
            continue
        current_run = str(v2.at[v2_idx, "run_accession"]) if pd.notna(v2.at[v2_idx, "run_accession"]) else ""
        ont = str(looked.get("ont_acc") or "")
        illumina = str(looked.get("illumina_acc") or "")
        biosample = str(looked.get("biosample") or "")

        # Determine ONT placement: from current run_accession if it matches the
        # integration's ont_acc, else fall back to the integration's ont_acc.
        if current_run and current_run == ont:
            n_run_was_ont += 1
            ont_to_set = current_run
        elif current_run == "" or current_run.lower() == "nan":
            n_run_was_empty += 1
            ont_to_set = ont
        else:
            # run_accession is something else — keep it; only fill lr from ont.
            n_run_was_other += 1
            ont_to_set = ont

        # Apply.
        if ont_to_set:
            v2.at[v2_idx, "lr_run_accession"] = ont_to_set
            v2.at[v2_idx, "lr_instrument_platform"] = "OXFORD_NANOPORE"

        if illumina:
            v2.at[v2_idx, "run_accession"] = illumina
            n_illumina_set += 1
        else:
            # Only clear run_accession if the current value was the ONT
            # (otherwise we keep whatever non-ONT value was there).
            if current_run and current_run == ont:
                v2.at[v2_idx, "run_accession"] = pd.NA
            n_illumina_missing += 1

        if biosample:
            v2.at[v2_idx, "sr_biosample"] = biosample

    stats.update({
        "current_run_was_ont":   n_run_was_ont,
        "current_run_was_empty": n_run_was_empty,
        "current_run_was_other": n_run_was_other,
        "illumina_set":          n_illumina_set,
        "illumina_missing_for_row": n_illumina_missing,
    })

    return v2, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — apply the fix + write."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--norway-integration", type=Path, default=DEFAULT_NORWAY_INTEG)
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    print(f"metadata_v2          : {args.metadata_v2}")
    print(f"norway_integration   : {args.norway_integration}")

    v2 = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    integ = pd.read_csv(args.norway_integration, sep="\t", low_memory=False)
    print(f"\nv2 rows             : {len(v2):,}")
    print(f"integration rows    : {len(integ):,}")

    updated, stats = fix_norway_rows(v2, integ)

    print("\n=== Norway-refseq fix stats ===")
    for k, v in stats.items():
        print(f"  {k:40s}: {v:,}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    print(f"\nbacked up existing → {bak.name}")
    updated.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"wrote {args.metadata_v2}  rows={len(updated):,}  cols={len(updated.columns)}")

    failed = False
    if stats.get("candidate_without_integration_match", 0) > 0:
        print(f"\nWARNING: {stats['candidate_without_integration_match']} Norway candidates had no "
              f"integration lookup — their schema is unchanged.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
