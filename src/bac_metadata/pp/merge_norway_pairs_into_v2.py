#!/usr/bin/env python3
"""Second-pass merge: pair Norway SR rows with their LR-extras (G.1-followup).

build_metadata_v2's audit-matched flow uses ``related_lr_accession`` ↔
``related_lr_run_accession`` to pair an SR row with the LRA assembly that
covers it. For 1,639 Klebsiella pneumoniae samples that worked fine.

It missed the **Norway complete-genome pairs**: the Norway-integration
step appended ~579 extra LR-only rows to v1 (one per resolved GCA/GCF,
``is_refseq=True``, ``Sample=GCA…``, ``run_accession=ONT_acc``), but
**never wrote** ``related_lr_accession=ONT_acc`` onto the original SR
rows (because the column it tried to write — ``related_sr_run_accession``
— didn't exist in v1 at the time). So G.1 saw two unrelated rows per
Norway sample:

  SR row (Sample=SAMEA…, is_refseq=False, run_accession=Illumina_acc)
  LR-extra (Sample=GCA…,  is_refseq=True,  run_accession=ONT_acc, lra=T)

This module joins them via the **Norway integration TSV's BioSample**
and does the same overlay the audit-matched flow does:

  - Flip the SR row's Sample → GCA (the LR-extra's Sample).
  - Save the original SR Sample → sr_biosample.
  - Copy lra_gca / lra_gcf / lra_assembly_file / lra_gff_file from the
    LR-extra onto the SR row.
  - Copy lra_final_set + lr_run_accession (= LR-extra's run_accession,
    the ONT) + lr_instrument_platform = OXFORD_NANOPORE onto the SR row.
  - Set kleborate_needs_recall + isescan_needs_recall = True (the LRA
    needs fresh calls; SR-derived values on the SR row are stale).
  - Delete the LR-extra row.

After this pass the Norway samples look exactly like the audit-matched
samples: one row per BioSample, Sample = GCA/GCF, SR + LR run accessions
in their respective columns.

Run BEFORE G.2 cascade (so the cascade sees the merged row, not the two
unmerged rows).

Usage::

    uv run python -m bac_metadata.pp.merge_norway_pairs_into_v2 --dry-run
    uv run python -m bac_metadata.pp.merge_norway_pairs_into_v2
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
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_INTEG       = DATA_ROOT / "david/processed/norway_tables1_integration.tsv"

_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")


def _bare(acc: object) -> str:
    if acc is None or pd.isna(acc):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1) if m else ""


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


# ─── CORE ─────────────────────────────────────────────────────────────────────

def merge_norway_pairs(v2: pd.DataFrame, integ: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """For each Norway LR-extra in v2 with an SR partner, merge + drop the LR-extra.

    Returns ``(updated_v2, stats)``.
    """
    stats: dict = {"v2_rows_in": len(v2), "integration_rows": len(integ)}
    v2 = v2.reset_index(drop=True).copy()

    # Build the biosample lookup keyed by either GCA or GCF (versioned-stripped).
    integ = integ.copy()
    integ["gca_bare"] = integ["resolved_gca"].map(_bare)
    integ["gcf_bare"] = integ["resolved_refseq_gcf"].map(_bare)

    bs_by_acc: dict[str, dict] = {}
    for r in integ.itertuples(index=False):
        d = {
            "biosample":    getattr(r, "biosample", "") or "",
            "illumina_acc": getattr(r, "illumina_acc", "") or "",
            "ont_acc":      getattr(r, "ont_acc", "") or "",
        }
        for key in (getattr(r, "gca_bare", ""), getattr(r, "gcf_bare", "")):
            if key:
                bs_by_acc[key] = d
    stats["integration_keys"] = len(bs_by_acc)

    # Build SR-side lookup: Sample (a BioSample) → row index in v2.
    sample_to_idx: dict[str, int] = (
        v2[["Sample"]]
        .reset_index()
        .assign(sample_str=lambda d: d["Sample"].astype(str))
        .drop_duplicates("sample_str", keep="first")
        .set_index("sample_str")["index"]
        .to_dict()
    )

    # Identify Norway LR-extras: is_complete_norway_genome=True AND
    # Sample.startswith("GCA_"/"GCF_").
    sample_str = v2["Sample"].astype(str)
    nor = _coerce_bool(v2["is_complete_norway_genome"])
    lra_extra_mask = nor & sample_str.str.startswith(("GCA_", "GCF_"))
    lra_extras = v2.index[lra_extra_mask].tolist()
    stats["norway_lra_extras_detected"] = len(lra_extras)

    # Columns to copy from the LR-extra onto the SR partner row.
    lra_cols_to_copy = [
        "lra_gca", "lra_gcf", "lra_assembly_file", "lra_gff_file",
        "lra_final_set",
        # lr_instrument_model — keep if LR-extra had one (usually NaN).
        "lr_instrument_model",
    ]
    lra_cols_to_copy = [c for c in lra_cols_to_copy if c in v2.columns]

    extras_to_drop: list[int] = []
    n_paired = 0
    n_unpaired_orphan = 0
    n_already_keyed_by_gca = 0
    n_partner_already_lra = 0
    n_unmatched_in_integration = 0

    for ex_idx in lra_extras:
        ex_sample = str(v2.at[ex_idx, "Sample"])
        bare = _bare(ex_sample)
        looked = bs_by_acc.get(bare)
        if not looked:
            n_unmatched_in_integration += 1
            continue
        biosample = looked["biosample"]
        ont_acc = looked["ont_acc"]
        # Find an SR partner in v2 keyed by biosample.
        sr_idx = sample_to_idx.get(biosample) if biosample else None
        if sr_idx is None:
            # No SR row in v2 for this biosample — keep the LR-extra as-is
            # (it'll just look like a pure-LR row in v2).
            n_unpaired_orphan += 1
            continue
        if sr_idx == ex_idx:
            # The "SR partner" lookup found the LR-extra itself (biosample == Sample),
            # i.e. the LR-extra was keyed by biosample not GCA. Skip merge.
            n_already_keyed_by_gca += 1
            continue
        sr_lra_flag = v2.at[sr_idx, "lra_final_set"] if "lra_final_set" in v2.columns else None
        if str(sr_lra_flag).lower() in {"true", "1", "yes"}:
            # SR partner is already LRA-bearing — shouldn't happen, but defensively skip.
            n_partner_already_lra += 1
            continue

        # MERGE. Same shape as the audit-matched flow in build_metadata_v2.
        # Save original SR Sample into sr_biosample (if not already set).
        orig_sr_sample = str(v2.at[sr_idx, "Sample"])
        current_sb = v2.at[sr_idx, "sr_biosample"]
        if pd.isna(current_sb) or str(current_sb) in ("", "nan"):
            v2.at[sr_idx, "sr_biosample"] = orig_sr_sample
        # Flip Sample → LR-extra's GCA/GCF.
        v2.at[sr_idx, "Sample"] = ex_sample
        # Copy lra_* columns.
        for col in lra_cols_to_copy:
            val = v2.at[ex_idx, col] if col in v2.columns else pd.NA
            if pd.notna(val) and str(val) != "":
                v2.at[sr_idx, col] = val
        # LR-run accession: prefer the LR-extra's run_accession (it's the ONT
        # accession that was written by the original augment step). Fall back to
        # the integration's ont_acc if the LR-extra row's run_accession is empty.
        ex_run = str(v2.at[ex_idx, "run_accession"]) if pd.notna(v2.at[ex_idx, "run_accession"]) else ""
        if ex_run.lower() == "nan":
            ex_run = ""
        lr_acc = ex_run or ont_acc
        if lr_acc:
            v2.at[sr_idx, "lr_run_accession"] = lr_acc
            v2.at[sr_idx, "lr_instrument_platform"] = "OXFORD_NANOPORE"
        # The SR partner now needs fresh Kleborate + ISEScan against the LRA.
        v2.at[sr_idx, "kleborate_needs_recall"] = True
        v2.at[sr_idx, "isescan_needs_recall"] = True
        # Drop the LR-extra row.
        extras_to_drop.append(ex_idx)
        n_paired += 1

    stats.update({
        "norway_pairs_merged":          n_paired,
        "lr_extras_dropped":            len(extras_to_drop),
        "lr_extras_unpaired_kept":      n_unpaired_orphan,
        "lr_extras_already_keyed_by_gca": n_already_keyed_by_gca,
        "lr_extras_partner_already_lra":  n_partner_already_lra,
        "lr_extras_unmatched_in_integ":   n_unmatched_in_integration,
    })

    if extras_to_drop:
        v2 = v2.drop(index=extras_to_drop).reset_index(drop=True)

    stats["v2_rows_out"] = len(v2)
    return v2, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — apply the merge + write."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2",       type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--norway-integration", type=Path, default=DEFAULT_INTEG)
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    print(f"metadata_v2         : {args.metadata_v2}")
    print(f"norway integration  : {args.norway_integration}")

    v2 = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    integ = pd.read_csv(args.norway_integration, sep="\t", low_memory=False)
    print(f"\nv2 rows             : {len(v2):,}")
    print(f"integration rows    : {len(integ):,}")

    updated, stats = merge_norway_pairs(v2, integ)

    print("\n=== Norway-pair merge stats ===")
    for k, v in stats.items():
        print(f"  {k:40s}: {v:,}")
    print(f"  net row delta                            : {stats['v2_rows_out'] - stats['v2_rows_in']:+,}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    print(f"\nbacked up existing → {bak.name}")
    updated.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"wrote {args.metadata_v2}  rows={len(updated):,}  cols={len(updated.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
