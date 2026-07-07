"""Run the Klebsiella parse/categorise + completeness-assessment engine on the M. abscessus master.

The full ``pp.metadata_curation.main()`` is Klebsiella-specific (kpsc_final_list filtering,
Google-Sheet study merges, MGH78578 / Norway flags, run_accession_used, a Klebsiella slimmed
column set). Here we call only the reusable, species-agnostic pieces the M.abs first pass needs:

  * parse/categorise the four core ENA fields — host, isolation_source, country, collection_date;
  * the ``calculate_*_completeness`` assessors that report whether every parsed value lands in a
    sensible category and how many stay uncategorised ("Not-filled" / "Other").

Two M.abs tweaks vs Klebsiella (per David):
  a) the primary per-sample identifier is ``sample_accession`` (Klebsiella keyed on ``Sample``) —
     we alias it to ``Sample`` so any downstream reference resolves;
  b) cf_status / smoking_status / AST are M.abs-only and are NOT parsed here (no Kleborate rubric).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from bac_metadata.pp import metadata_curation as mc

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MASTER = DATA / "curated" / "metadata_curated_master.tsv"
OUT = DATA / "curated" / "metadata_curated_master_parsed.tsv"
LOG = DATA / "curated" / "metadata_curated_master_parsed.log"


def _assess(df: pd.DataFrame) -> None:
    """Print the category-completeness assessment for the four core fields."""
    print("\n" + "#" * 70)
    print("# CATEGORY-COMPLETENESS ASSESSMENT (usable / other / not-filled)")
    print("#" * 70)

    host_counts, host_bd = mc.calculate_host_completeness(df)
    print(f"\n[host]  {host_bd}")
    print(host_counts.to_string())

    iso_counts, iso_bd, iso_other, iso_other_counts = mc.calculate_isolation_source_completeness(
        df, return_other_info=True
    )
    print(f"\n[isolation_source]  {iso_bd}")
    print(iso_counts.to_string())
    if len(iso_other):
        print(f"  -> {len(iso_other)} 'Other' (off-list) categories:")
        print(iso_other_counts.to_string())

    region_counts, region_bd = mc.calculate_region_completeness(df)
    print(f"\n[country/region]  {region_bd}")
    print(region_counts.to_string())

    date_counts, date_bd = mc.calculate_date_completeness(df)
    print(f"\n[collection_date]  {date_bd}")
    print(date_counts.to_string())


def main() -> None:
    df = pd.read_csv(MASTER, sep="\t", low_memory=False)
    print(f"Loaded master: {len(df)} rows, {df['study_accession'].nunique()} studies")

    # tweak (a): primary identifier — Klebsiella used 'Sample'; M.abs keys on sample_accession
    df["Sample"] = df["sample_accession"]

    df = mc.parse_host(df, verbose=True)
    df = mc.categorise_host(df, verbose=True)

    df = mc.parse_country(df, verbose=True)
    df = mc.categorise_region(df, verbose=True)

    df = mc.parse_isolation_source(df, verbose=True)
    df = mc.categorise_isolation_source(df, verbose=True)
    df = mc.reconcile_host_and_isolation_source(df, verbose=True)

    df = mc.parse_collection_date(df, verbose=True)

    _assess(df)

    df.to_csv(OUT, sep="\t", index=False)
    print(f"\nWrote parsed master -> {OUT}")


if __name__ == "__main__":
    # tee stdout to the log while still showing it
    log_fh = open(LOG, "w")

    class _Tee:
        def write(self, s):
            sys.__stdout__.write(s)
            log_fh.write(s)

        def flush(self):
            sys.__stdout__.flush()
            log_fh.flush()

    sys.stdout = _Tee()
    try:
        main()
    finally:
        sys.stdout = sys.__stdout__
        log_fh.close()
