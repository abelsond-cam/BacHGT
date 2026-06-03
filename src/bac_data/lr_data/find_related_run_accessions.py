#!/usr/bin/env python3
"""
find_long_reads.py
------------------
Reads metadata_final_curated_slimmed.tsv, filters to non-RefSeq samples
(i.e. those WITHOUT a complete genome already), then queries ENA Portal API
in parallel batches to find associated long-read runs (ONT or PacBio).
Then reads atb_release_incr_2_species_calls.tsv, filters to rows whose
scientific_name contains "Klebsiella", and runs the same ENA pipeline.

ALSO: for is_refseq=True samples (which have complete RefSeq genomes identified
by GCF accessions), resolves GCF → BioSample via NCBI Datasets API, then
queries ENA for associated short-read (Illumina) runs.

Usage:
    python find_long_reads.py [--dry-run] [--limit N]

    --dry-run   Print column names and first few rows, then exit.
                Use this first to confirm column names are correct.
    --limit N   Only process first N samples (useful for testing).

NCBI API KEY (optional but strongly recommended — raises rate limit 3→10 req/s):
    export NCBI_API_KEY="your_key_here"
    Register at: https://www.ncbi.nlm.nih.gov/account/

Primary outputs:

  1. **Existing metadata rows are updated in place** with the discovered run's
     accession and (for RefSeq rows) NCBI assembly enrichment columns. Row
     count of the metadata is **never changed by this script**.

  2. **Two side-CSV files** are written with the full run-level details. They
     are keyed by `run_accession` and contain one row per discovered run that
     was NOT already captured in the metadata's
     `related_sr_accession` / `related_lr_accession` columns. Both files
     live in the same folder as the curated metadata (``DATA_DIR``) so the
     "one source of truth" property holds.

     - RELATED_SR_CSV → ``<DATA_DIR>/related_sr_accessions.csv``
         Short-read runs found for existing RefSeq long-read genomes
         (section i below).
     - RELATED_LR_CSV → ``<DATA_DIR>/related_lr_accessions.csv``
         Long-read runs found for existing non-RefSeq short-read samples
         (section ii) **and** for ATB-increment BioSamples not in our
         metadata (section iii). The ``source_section`` column
         distinguishes them.

Sections:
  (i)   RefSeq (`is_refseq=True`, `Sample = GCF_*`) → ENA short reads
        - merge: existing row's ``related_sr_accession`` gets the SR run accession
        - side-CSV: full SR run details → RELATED_SR_CSV
  (ii)  Non-RefSeq (`is_refseq=False`) → ENA long reads
        - merge: existing row's ``related_lr_accession`` gets the LR run accession
        - side-CSV: full LR run details → RELATED_LR_CSV
  (iii) ATB increment BioSamples (NOT in our metadata) → ENA long reads
        - no merge target → side-CSV only: full LR run details → RELATED_LR_CSV
          (linked_curated_sample = empty, source_section = "atb_long_read")

Usage:
    python find_long_reads.py [--dry-run] [--limit N]

    --dry-run   Print column names and first few rows, then exit.
    --limit N   Only process first N samples (useful for testing).

NCBI API KEY (optional but strongly recommended — raises rate limit 3→10 req/s):
    export NCBI_API_KEY="your_key_here"
    Register at: https://www.ncbi.nlm.nih.gov/account/

File targets:
  Source location: METADATA_FILES_TO_UPDATE (configured at the top of this script)
                     - data/final/metadata/metadata_final_curated_slimmed.tsv
                     - data/final/metadata/metadata_final_curated_all_samples_and_columns.tsv
  Local copies   : <cwd>/<basename> for each file above
  Log file       : <cwd>/find_long_reads.log  (tee of stderr + stdout)

Columns updated on existing rows
────────────────────────────────
RefSeq rows (is_refseq=True) — keyed via secondary_sample_accession (GCF):
  related_sr_accession            : run accession of best SR run found in ENA
                                    for the BioSample that this GCF maps to
  assembly_sequencing_tech        : NCBI assembly_info.sequencing_tech
  assembly_method                 : NCBI assembly_info.assembly_method
  assembly_bioproject_accession   : NCBI assembly_info.bioproject_accession
  assembly_release_date           : NCBI assembly_info.release_date
  assembly_submitter              : NCBI assembly_info.submitter
  assembly_bioproject_title       : Title of the first BioProject in the lineage

Non-RefSeq rows (is_refseq=False) — keyed via sample_accession (BioSample):
  related_lr_accession            : run accession of best LR run found in ENA
                                    (Oxford Nanopore / PacBio) for this BioSample

These columns are dropped and re-populated on every run, so re-running this script
is the canonical way to refresh the metadata with the latest ENA / NCBI state.

ATB pipeline (atb_release_incr_2_species_calls.tsv) is a separate dataset whose
ATB-only BioSamples are NOT in our curated metadata. Discovered ATB long-read
runs land in RELATED_LR_CSV alongside section-ii rows; the legacy outputs
under ATB_LONG_READS_OUTPUT_DIR (data/final/atb_long_reads/) are still written
for backwards compatibility.

Folders that can be safely deleted (no longer written by this script):
  data/final/long_reads/
  data/final/short_reads_from_refseq/
  data/final/metadata/processed/long_reads/   (legacy CSV location, pre-2026-05)
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import islice
from pathlib import Path

import pandas as pd
import requests


class _TeeStream:
    """Duplicate writes to multiple text streams (e.g. terminal + log file)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:  # noqa: BLE001 — tee fan-out: never let a closed/broken stream kill logging
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:  # noqa: BLE001 — tee fan-out: never let a closed/broken stream kill logging
                pass


# ─── CONFIGURE THESE ──────────────────────────────────────────────────────────

DATA_DIR = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata/"
)
METADATA_FILE = DATA_DIR + "metadata_final_curated_slimmed.tsv"
METADATA_FILE_FULL = DATA_DIR + "metadata_final_curated_all_samples_and_columns.tsv"
# Both files receive the new run-related columns on every run (slimmed first → CG summary)
METADATA_FILES_TO_UPDATE = [METADATA_FILE, METADATA_FILE_FULL]

OUTPUT_DIR = DATA_DIR + "processed/long_reads/"  # legacy — kept only for historical / pre-refactor scripts
# Side-file CSVs of discovered runs (this script no longer appends rows to the
# curated metadata; instead it writes one CSV per role, keyed by run_accession,
# deduped against run accessions already captured in metadata).
# Both CSVs live next to the curated metadata so there's one folder per source-of-truth.
RELATED_SR_CSV = DATA_DIR + "related_sr_accessions.csv"
RELATED_LR_CSV = DATA_DIR + "related_lr_accessions.csv"
LONG_READS_OUTPUT_DIR = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/long_reads/"
)
# ATB outputs live in their own top-level dir so data/final/long_reads/ can be deleted
ATB_LONG_READS_OUTPUT_DIR = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/atb_long_reads/"
)
ATB_RELEASE_FILE = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/atb_release_incr_2_species_calls.tsv"
)
# Log file (saved to current working directory)
LOG_FILE_NAME = "find_long_reads.log"

# Column names in the metadata file — adjust if dry-run reveals different names
SAMPLE_ACCESSION_COL = "sample_accession"  # e.g. SAMEA..., SAMN...
IS_REFSEQ_COL = "is_refseq"  # boolean column (expected filled; used as-is)
ATB_SCI_NAME_COL = "scientific_name"

# Platforms to retrieve
LONG_READ_PLATFORMS = {"OXFORD_NANOPORE", "PACBIO_SMRT"}
SHORT_READ_PLATFORMS = {"ILLUMINA", "BGISEQ"}

# Clonal groups always shown in the post-update CG summary, regardless of rank
PRIORITY_CLONAL_GROUPS = ["CG307", "CG340", "CG39", "CG15"]

# ─── SHORT-READ PIPELINE — NCBI Datasets API (GCF → BioSample resolution) ─────

NCBI_DATASETS_API = "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{}/dataset_report"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")  # set via: export NCBI_API_KEY=...
NCBI_BATCH_SIZE = 50  # well under the 1000 accession limit; keeps URLs short
NCBI_MAX_WORKERS = 4  # safe with or without key on a multi-core Mac
NCBI_RETRY_MAX = 3
NCBI_RETRY_PAUSE = 15  # seconds; NCBI 429 back-off

SHORT_READS_OUTPUT_DIR = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/short_reads_from_refseq/"
)

# Column in the slimmed metadata that holds the clean GCF_X.N accession
GCF_ACCESSION_COL = "secondary_sample_accession"

# API settings
ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api/search"
BATCH_SIZE = 50  # accessions per API request (keep ≤50 to avoid URL length limits)
MAX_WORKERS = 8  # parallel threads — polite for ENA; increase to 16 if needed
RETRY_MAX = 3
RETRY_PAUSE = 10  # seconds between retries on rate limit

FIELDS = ",".join(
    [
        "run_accession",
        "sample_accession",
        "secondary_sample_accession",
        "experiment_accession",
        "study_accession",
        "instrument_platform",
        "instrument_model",
        "library_strategy",
        "library_layout",
        "read_count",
        "base_count",
        "fastq_ftp",
        "fastq_bytes",
        "first_public",
        "scientific_name",
    ]
)

# Minimum bases for a run to be worth attempting hybrid assembly
# ~50x coverage for a 5.5 Mb Klebsiella genome
MIN_BASES_FOR_ASSEMBLY = 275_000_000

# ─── API QUERY ────────────────────────────────────────────────────────────────


def query_ena_batch(sample_accs: list[str]) -> list[dict]:
    """
    Query ENA Portal API for all runs linked to a batch of sample accessions.
    Searches both sample_accession and secondary_sample_accession fields so
    that SAMN (NCBI) accessions are found via their ENA secondary accession.
    """
    clauses = [f'(sample_accession="{a}" OR secondary_sample_accession="{a}")' for a in sample_accs]
    query = " OR ".join(clauses)

    params = {
        "result": "read_run",
        "query": query,
        "fields": FIELDS,
        "format": "json",
        "limit": 0,  # 0 = return all matches
    }

    for attempt in range(RETRY_MAX):
        try:
            r = requests.get(ENA_PORTAL, params=params, timeout=60)

            if r.status_code == 200:
                if not r.text.strip():
                    return []
                try:
                    return r.json()
                except Exception:  # noqa: BLE001 — resilience: empty JSON / malformed response → drop batch
                    return []

            elif r.status_code == 429:
                wait = RETRY_PAUSE * (attempt + 1)
                print(f"    [rate limit] waiting {wait}s ...", file=sys.stderr)
                time.sleep(wait)

            else:
                print(
                    f"    [HTTP {r.status_code}] batch of {len(sample_accs)} — skipping",
                    file=sys.stderr,
                )
                return []

        except requests.RequestException as e:
            print(f"    [request error] {e}", file=sys.stderr)
            time.sleep(5)

    print(f"    [failed after {RETRY_MAX} retries] batch skipped", file=sys.stderr)
    return []


def filter_long_reads(runs: list[dict]) -> list[dict]:
    """Keep only runs from long-read platforms."""
    return [r for r in runs if r.get("instrument_platform", "").upper() in LONG_READ_PLATFORMS]


def filter_short_reads(runs: list[dict]) -> list[dict]:
    """Keep only runs from short-read platforms (Illumina, BGI)."""
    return [r for r in runs if r.get("instrument_platform", "").upper() in SHORT_READ_PLATFORMS]


# ─── NCBI DATASETS API (GCF → BioSample) ──────────────────────────────────────


def query_ncbi_datasets_batch(gcf_accs: list[str]) -> list[dict]:
    """
    Query NCBI Datasets API v2 for BioSample accessions linked to a batch of GCF/GCA
    assembly accessions. Returns list of dicts with keys: gcf, biosample,
    bioproject_accession, release_date, submitter, sequencing_tech, assembly_method,
    bioproject_title.
    """
    accession_str = ",".join(gcf_accs)
    url = NCBI_DATASETS_API.format(accession_str)
    params: dict = {"report_type": "ASSEMBLY", "page_size": NCBI_BATCH_SIZE}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    for attempt in range(NCBI_RETRY_MAX):
        try:
            r = requests.get(url, params=params, timeout=60)

            if r.status_code == 200:
                if not r.text.strip():
                    return []
                try:
                    data = r.json()
                except Exception:  # noqa: BLE001 — resilience: empty JSON / malformed response → drop batch
                    return []
                results = []
                for report in data.get("reports", []):
                    gcf = report.get("current_accession", "")
                    ai = report.get("assembly_info", {})
                    biosample = ai.get("biosample", {}).get("accession", "")
                    bp_title = ""
                    for lineage_entry in ai.get("bioproject_lineage", []):
                        for bp in lineage_entry.get("bioprojects", []):
                            if bp.get("title"):
                                bp_title = bp["title"]
                                break
                        if bp_title:
                            break
                    if gcf and biosample:
                        results.append(
                            {
                                "gcf": gcf,
                                "biosample": biosample,
                                "bioproject_accession": ai.get("bioproject_accession", ""),
                                "release_date": ai.get("release_date", ""),
                                "submitter": ai.get("submitter", ""),
                                "sequencing_tech": ai.get("sequencing_tech", ""),
                                "assembly_method": ai.get("assembly_method", ""),
                                "bioproject_title": bp_title,
                            }
                        )
                # Without an API key NCBI allows 3 req/s; sleep to stay politely under that
                if not NCBI_API_KEY:
                    time.sleep(0.35)
                return results

            elif r.status_code == 429:
                wait = NCBI_RETRY_PAUSE * (attempt + 1)
                print(f"    [NCBI rate limit] waiting {wait}s ...", file=sys.stderr)
                time.sleep(wait)

            else:
                print(
                    f"    [NCBI HTTP {r.status_code}] batch of {len(gcf_accs)} — skipping",
                    file=sys.stderr,
                )
                return []

        except requests.RequestException as e:
            print(f"    [NCBI request error] {e}", file=sys.stderr)
            time.sleep(5)

    print(f"    [NCBI failed after {NCBI_RETRY_MAX} retries] batch skipped", file=sys.stderr)
    return []


def resolve_gcf_to_biosample(
    gcf_accessions: list[str],
) -> tuple[dict[str, str], pd.DataFrame]:
    """
    Resolve a list of GCF/GCA accessions to BioSample accessions via NCBI Datasets API v2.
    Returns (gcf_to_biosample dict, enriched_df with NCBI assembly metadata).
    Prints a detailed report of resolution rates and any failures.
    """
    batches = list(batched(gcf_accessions, NCBI_BATCH_SIZE))
    total_batches = len(batches)
    # Without an API key, cap to 1 worker — the 0.35 s sleep in the batch function
    # keeps us under NCBI's 3 req/s limit; parallelism would immediately breach it.
    actual_workers = NCBI_MAX_WORKERS if NCBI_API_KEY else 1
    key_status = f"API key={'set' if NCBI_API_KEY else 'NOT set — throttling to 1 worker + 0.35s sleep'}"
    print(
        f"\n[resolve_gcf] Resolving {len(gcf_accessions):,} GCF accessions via NCBI Datasets API ({key_status})",
        file=sys.stderr,
    )
    print(
        f"[resolve_gcf] {total_batches} batches × {NCBI_BATCH_SIZE} accessions, "
        f"{actual_workers} workers  (est. {total_batches * 0.35 / 60:.1f} min without key)",
        file=sys.stderr,
    )

    gcf_to_biosample: dict[str, str] = {}
    all_records: list[dict] = []
    completed = 0
    failed_batches = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=actual_workers) as pool:
        future_to_batch = {pool.submit(query_ncbi_datasets_batch, batch): batch for batch in batches}
        for future in as_completed(future_to_batch):
            completed += 1
            batch = future_to_batch[future]
            records = future.result()
            if not records and len(batch) > 0:
                failed_batches += 1
            all_records.extend(records)
            for rec in records:
                gcf_to_biosample[rec["gcf"]] = rec["biosample"]

            if completed % 5 == 0 or completed == total_batches:
                elapsed = time.time() - t0
                rate = completed / elapsed if elapsed > 0 else 1
                remaining = (total_batches - completed) / rate
                print(
                    f"[resolve_gcf] [{completed:4d}/{total_batches}]  "
                    f"resolved: {len(gcf_to_biosample):,}  "
                    f"failed batches: {failed_batches}  "
                    f"elapsed: {elapsed / 60:.1f}m  eta: {remaining / 60:.1f}m",
                    file=sys.stderr,
                )

    elapsed_total = time.time() - t0
    n_resolved = len(gcf_to_biosample)
    n_total = len(gcf_accessions)
    unresolved = [a for a in gcf_accessions if a not in gcf_to_biosample]

    print("\n[resolve_gcf] ── Resolution summary ─────────────────────────────────────────", file=sys.stderr)
    print(f"[resolve_gcf]   Total GCF accessions queried : {n_total:,}", file=sys.stderr)
    print(
        f"[resolve_gcf]   Successfully resolved        : {n_resolved:,}  ({100 * n_resolved / n_total:.1f}%)",
        file=sys.stderr,
    )
    print(f"[resolve_gcf]   Unresolved (suppressed/gone) : {len(unresolved):,}", file=sys.stderr)
    print(f"[resolve_gcf]   Failed batches               : {failed_batches}", file=sys.stderr)
    print(f"[resolve_gcf]   Time                         : {elapsed_total / 60:.1f} minutes", file=sys.stderr)
    if unresolved[:10]:
        print(f"[resolve_gcf]   First unresolved (up to 10)  : {unresolved[:10]}", file=sys.stderr)

    _ncbi_cols = [
        "gcf",
        "biosample",
        "bioproject_accession",
        "release_date",
        "submitter",
        "sequencing_tech",
        "assembly_method",
        "bioproject_title",
    ]
    enriched_df = pd.DataFrame(all_records, columns=_ncbi_cols) if all_records else pd.DataFrame(columns=_ncbi_cols)

    # Per-field non-empty counts — shows how complete the NCBI enrichment is
    if not enriched_df.empty:
        print("[resolve_gcf]   Non-empty values per enriched field:", file=sys.stderr)
        for field in [
            "bioproject_accession",
            "release_date",
            "submitter",
            "sequencing_tech",
            "assembly_method",
            "bioproject_title",
        ]:
            n_filled = int((enriched_df[field].astype(str).str.strip() != "").sum())
            pct = 100 * n_filled / len(enriched_df)
            print(f"[resolve_gcf]     {field:<22}: {n_filled:>5,}  ({pct:5.1f}%)", file=sys.stderr)

    return gcf_to_biosample, enriched_df


# ─── BATCHING HELPERS ─────────────────────────────────────────────────────────


def batched(iterable, n):
    """Yield successive n-sized chunks from iterable."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


def extract_unique_accessions(df: pd.DataFrame, column: str) -> list[str]:
    """Return unique non-empty sample accession strings from a dataframe column."""
    accessions = df[column].dropna().astype(str).str.strip().unique().tolist()
    return [a for a in accessions if a and a.lower() != "nan"]


def run_long_read_pipeline(
    accessions: list[str],
    output_dir: Path,
    dataset_label: str,
    write_outputs: bool = True,
) -> pd.DataFrame:
    """Run ENA querying, long-read filtering, return the runs DataFrame.

    When write_outputs=False, no auxiliary files are written — useful when the
    caller will fold the results into another file (e.g. the metadata TSV).
    """
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
    out_tsv = output_dir / "long_read_runs.tsv"
    out_summary = output_dir / "long_read_runs_summary.tsv"
    out_no_lr = output_dir / "samples_with_no_long_reads.txt"
    out_secondary_only = output_dir / "samples_matched_via_secondary_only.txt"

    batches = list(batched(accessions, BATCH_SIZE))
    total_batches = len(batches)
    print(
        f"\n[{dataset_label}] Querying {len(accessions):,} accessions in {total_batches} batches "
        f"(batch size={BATCH_SIZE}, workers={MAX_WORKERS})",
        file=sys.stderr,
    )
    print(f"[{dataset_label}] Output dir: {output_dir}\n", file=sys.stderr)

    all_long_read_runs: list[dict] = []
    completed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_batch = {pool.submit(query_ena_batch, batch): batch for batch in batches}

        for future in as_completed(future_to_batch):
            completed += 1
            runs = future.result()
            long_reads = filter_long_reads(runs)
            all_long_read_runs.extend(long_reads)

            if completed % 10 == 0 or completed == total_batches:
                elapsed = time.time() - t0
                rate = completed / elapsed
                remaining = (total_batches - completed) / rate if rate > 0 else 0
                print(
                    f"[{dataset_label}] [{completed:4d}/{total_batches}]  "
                    f"long-read runs found so far: {len(all_long_read_runs):,}  "
                    f"elapsed: {elapsed / 60:.1f}m  eta: {remaining / 60:.1f}m",
                    file=sys.stderr,
                )

    elapsed_total = time.time() - t0
    print(f"\n[{dataset_label}] Done in {elapsed_total / 60:.1f} minutes", file=sys.stderr)
    print(f"[{dataset_label}] Total long-read runs found: {len(all_long_read_runs):,}", file=sys.stderr)

    if not all_long_read_runs:
        print(f"\n[{dataset_label}] No long reads found for any samples.", file=sys.stderr)
        if write_outputs:
            pd.DataFrame().to_csv(out_tsv, sep="\t", index=False)
            Path(out_no_lr).write_text("\n".join(accessions))
            Path(out_secondary_only).write_text("")
        return pd.DataFrame()

    df = pd.DataFrame(all_long_read_runs)

    for col in ["read_count", "base_count", "fastq_bytes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "base_count" in df.columns:
        df["est_coverage_5_5Mb"] = (df["base_count"] / 5_500_000).round(1)
        df["sufficient_for_hybrid"] = df["base_count"] >= MIN_BASES_FOR_ASSEMBLY

    if write_outputs:
        df.to_csv(out_tsv, sep="\t", index=False)
        print(f"\n[{dataset_label}] Full run table written to:\n    {out_tsv}", file=sys.stderr)

        summary_cols = [
            c
            for c in [
                "sample_accession",
                "secondary_sample_accession",
                "instrument_platform",
                "instrument_model",
                "run_accession",
                "read_count",
                "base_count",
                "est_coverage_5_5Mb",
                "sufficient_for_hybrid",
                "fastq_ftp",
                "first_public",
            ]
            if c in df.columns
        ]
        df[summary_cols].to_csv(out_summary, sep="\t", index=False)
        print(f"[{dataset_label}] Summary table written to:\n    {out_summary}", file=sys.stderr)

    primary_vals = set()
    secondary_vals_all = []
    if "sample_accession" in df.columns:
        primary_vals = set(df["sample_accession"].dropna().astype(str).str.strip())
    if "secondary_sample_accession" in df.columns:
        secondary_vals_all = df["secondary_sample_accession"].dropna().astype(str).str.strip().tolist()

    ids_from_runs = set(primary_vals) | set(secondary_vals_all)
    samples_with_lr = ids_from_runs
    no_lr = [a for a in accessions if a not in samples_with_lr]
    if write_outputs:
        Path(out_no_lr).write_text("\n".join(no_lr) + "\n")
        print(
            f"[{dataset_label}] Samples with NO long reads ({len(no_lr):,}) written to:\n    {out_no_lr}",
            file=sys.stderr,
        )

    if "sample_accession" in df.columns:
        matched_via_secondary_only = sorted(a for a in accessions if a in samples_with_lr and a not in primary_vals)
    else:
        matched_via_secondary_only = []
    if write_outputs:
        Path(out_secondary_only).write_text("\n".join(matched_via_secondary_only) + "\n")
        print(
            f"[{dataset_label}] Queried accessions matched only via secondary_sample_accession "
            f"({len(matched_via_secondary_only):,}) written to:\n    {out_secondary_only}",
            file=sys.stderr,
        )

    print(f"\n[{dataset_label}] ── Platform breakdown ────────────────────────────────────────────")
    print(df["instrument_platform"].value_counts().to_string())
    print(f"\n[{dataset_label}] ── Instrument model breakdown ────────────────────────────────────")
    print(df["instrument_model"].value_counts().to_string())

    accessions_set = set(accessions)
    n_queried_with_lr = len(accessions_set & samples_with_lr)

    if "sufficient_for_hybrid" in df.columns:
        n_sufficient = df["sufficient_for_hybrid"].sum()
        suff = df[df["sufficient_for_hybrid"]]
        suff_ids = set()
        if "sample_accession" in suff.columns:
            suff_ids |= set(suff["sample_accession"].dropna().astype(str).str.strip())
        if "secondary_sample_accession" in suff.columns:
            suff_ids |= set(suff["secondary_sample_accession"].dropna().astype(str).str.strip())
        n_samples_sufficient = len(accessions_set & suff_ids)
        print(
            f"\n[{dataset_label}] ── Runs with ≥50x coverage (≥{MIN_BASES_FOR_ASSEMBLY / 1e6:.0f} Mb): "
            f"{n_sufficient:,} runs across {n_samples_sufficient:,} queried samples "
            f"(primary ∪ secondary accession match)"
        )

    print(
        f"\n[{dataset_label}] ── Unique queried samples with ≥1 long-read run: {n_queried_with_lr:,} "
        f"(primary ∪ secondary accession match)"
    )

    return df


# ─── SHORT-READ PIPELINE ──────────────────────────────────────────────────────


def run_short_read_pipeline(
    gcf_to_biosample: dict[str, str],
    output_dir: Path,
    dataset_label: str,
    unresolved_gcfs: list[str],
    enriched_ncbi_df: pd.DataFrame | None = None,
    write_outputs: bool = True,
) -> tuple[set[str], pd.DataFrame]:
    """
    Given a GCF→BioSample mapping, query ENA for short-read runs and return them.
    When write_outputs=False, no auxiliary files are written.
    Returns (gcfs_with_sr, short_read_df).
    """
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
    out_tsv = output_dir / "short_read_runs.tsv"
    out_summary = output_dir / "short_read_runs_summary.tsv"
    out_no_sr = output_dir / "samples_with_no_short_reads.txt"
    out_unresolved = output_dir / "gcf_accessions_unresolved.txt"
    out_secondary_only = output_dir / "samples_matched_via_secondary_only.txt"
    out_gcf_biosample = output_dir / "gcf_to_biosample_map.tsv"
    out_gcf_biosample_enr = output_dir / "gcf_to_biosample_enriched.tsv"

    if write_outputs:
        pd.DataFrame(list(gcf_to_biosample.items()), columns=["gcf_accession", "biosample_accession"]).to_csv(
            out_gcf_biosample, sep="\t", index=False
        )
        print(
            f"[{dataset_label}] GCF→BioSample map ({len(gcf_to_biosample):,} entries) written to:\n    {out_gcf_biosample}",
            file=sys.stderr,
        )

        if enriched_ncbi_df is not None and not enriched_ncbi_df.empty:
            enriched_ncbi_df.to_csv(out_gcf_biosample_enr, sep="\t", index=False)
            print(
                f"[{dataset_label}] Enriched GCF metadata ({len(enriched_ncbi_df):,} records) "
                f"written to:\n    {out_gcf_biosample_enr}",
                file=sys.stderr,
            )

        Path(out_unresolved).write_text("\n".join(unresolved_gcfs) + "\n")
        print(
            f"[{dataset_label}] Unresolved GCF accessions ({len(unresolved_gcfs):,}) written to:\n    {out_unresolved}",
            file=sys.stderr,
        )

    biosample_accessions = list(gcf_to_biosample.values())
    biosample_to_gcf = {v: k for k, v in gcf_to_biosample.items()}

    if not biosample_accessions:
        print(f"[{dataset_label}] No BioSample accessions to query — nothing to do.", file=sys.stderr)
        return set(), pd.DataFrame()

    batches = list(batched(biosample_accessions, BATCH_SIZE))
    total_batches = len(batches)
    print(
        f"\n[{dataset_label}] Querying {len(biosample_accessions):,} BioSample accessions "
        f"in {total_batches} batches (batch size={BATCH_SIZE}, workers={MAX_WORKERS})",
        file=sys.stderr,
    )
    print(f"[{dataset_label}] Output dir: {output_dir}\n", file=sys.stderr)

    all_short_read_runs: list[dict] = []
    completed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_batch = {pool.submit(query_ena_batch, batch): batch for batch in batches}
        for future in as_completed(future_to_batch):
            completed += 1
            runs = future.result()
            short_reads = filter_short_reads(runs)
            all_short_read_runs.extend(short_reads)

            if completed % 10 == 0 or completed == total_batches:
                elapsed = time.time() - t0
                rate = completed / elapsed if elapsed > 0 else 1
                remaining = (total_batches - completed) / rate
                print(
                    f"[{dataset_label}] [{completed:4d}/{total_batches}]  "
                    f"short-read runs found so far: {len(all_short_read_runs):,}  "
                    f"elapsed: {elapsed / 60:.1f}m  eta: {remaining / 60:.1f}m",
                    file=sys.stderr,
                )

    elapsed_total = time.time() - t0
    print(f"\n[{dataset_label}] Done in {elapsed_total / 60:.1f} minutes", file=sys.stderr)
    print(f"[{dataset_label}] Total short-read runs found: {len(all_short_read_runs):,}", file=sys.stderr)

    if not all_short_read_runs:
        print(f"\n[{dataset_label}] No short reads found for any samples.", file=sys.stderr)
        if write_outputs:
            pd.DataFrame().to_csv(out_tsv, sep="\t", index=False)
            Path(out_no_sr).write_text("\n".join(biosample_accessions) + "\n")
            Path(out_secondary_only).write_text("")
        return set(), pd.DataFrame()

    df = pd.DataFrame(all_short_read_runs)

    for col in ["read_count", "base_count", "fastq_bytes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Map BioSample back to GCF for easy downstream joining
    if "sample_accession" in df.columns:
        df.insert(
            0,
            "gcf_accession",
            df["sample_accession"]
            .map(biosample_to_gcf)
            .fillna(df.get("secondary_sample_accession", pd.Series(dtype=str)).map(biosample_to_gcf)),
        )

    if write_outputs:
        df.to_csv(out_tsv, sep="\t", index=False)
        print(f"\n[{dataset_label}] Full run table written to:\n    {out_tsv}", file=sys.stderr)

        summary_cols = [
            c
            for c in [
                "gcf_accession",
                "sample_accession",
                "secondary_sample_accession",
                "instrument_platform",
                "instrument_model",
                "run_accession",
                "library_strategy",
                "library_layout",
                "read_count",
                "base_count",
                "fastq_ftp",
                "first_public",
            ]
            if c in df.columns
        ]
        df[summary_cols].to_csv(out_summary, sep="\t", index=False)
        print(f"[{dataset_label}] Summary table written to:\n    {out_summary}", file=sys.stderr)

    # ── Matched / unmatched accounting ────────────────────────────────────────
    primary_vals = set()
    secondary_vals_all: list[str] = []
    if "sample_accession" in df.columns:
        primary_vals = set(df["sample_accession"].dropna().astype(str).str.strip())
    if "secondary_sample_accession" in df.columns:
        secondary_vals_all = df["secondary_sample_accession"].dropna().astype(str).str.strip().tolist()

    ids_from_runs = primary_vals | set(secondary_vals_all)
    samples_with_sr = ids_from_runs

    no_sr = [a for a in biosample_accessions if a not in samples_with_sr]
    matched_via_secondary_only = sorted(
        a for a in biosample_accessions if a in samples_with_sr and a not in primary_vals
    )
    if write_outputs:
        Path(out_no_sr).write_text("\n".join(no_sr) + "\n")
        print(
            f"[{dataset_label}] BioSample accessions with NO short-read runs ({len(no_sr):,}) "
            f"written to:\n    {out_no_sr}",
            file=sys.stderr,
        )
        Path(out_secondary_only).write_text("\n".join(matched_via_secondary_only) + "\n")
        print(
            f"[{dataset_label}] Matched only via secondary_sample_accession "
            f"({len(matched_via_secondary_only):,}) written to:\n    {out_secondary_only}",
            file=sys.stderr,
        )

    # ── Detailed summary ───────────────────────────────────────────────────────
    accessions_set = set(biosample_accessions)
    n_queried_with_sr = len(accessions_set & samples_with_sr)
    n_gcfs_with_sr = len(set(df["gcf_accession"].dropna()) if "gcf_accession" in df.columns else set())

    print(f"\n[{dataset_label}] ── Platform breakdown ──────────────────────────────────────────────")
    print(df["instrument_platform"].value_counts().to_string())
    print(f"\n[{dataset_label}] ── Instrument model breakdown ────────────────────────────────────────")
    print(df["instrument_model"].value_counts().to_string())
    print(f"\n[{dataset_label}] ── Library strategy breakdown ───────────────────────────────────────")
    if "library_strategy" in df.columns:
        print(df["library_strategy"].value_counts().to_string())
    print(f"\n[{dataset_label}] ── Library layout breakdown ─────────────────────────────────────────")
    if "library_layout" in df.columns:
        print(df["library_layout"].value_counts().to_string())

    print(f"\n[{dataset_label}] ── Coverage summary ────────────────────────────────────────────────")
    if "base_count" in df.columns:
        bc = df["base_count"].dropna()
        print(
            f"  base_count — min: {bc.min():,.0f}  median: {bc.median():,.0f}  "
            f"mean: {bc.mean():,.0f}  max: {bc.max():,.0f}"
        )
    if "read_count" in df.columns:
        rc = df["read_count"].dropna()
        print(
            f"  read_count — min: {rc.min():,.0f}  median: {rc.median():,.0f}  "
            f"mean: {rc.mean():,.0f}  max: {rc.max():,.0f}"
        )

    print(f"\n[{dataset_label}] ── Accession match summary ─────────────────────────────────────────")
    print(f"  GCFs queried                        : {len(gcf_to_biosample):,}")
    print(f"  BioSample accessions queried        : {len(biosample_accessions):,}")
    print(
        f"  BioSamples with ≥1 short-read run   : {n_queried_with_sr:,}  "
        f"({100 * n_queried_with_sr / max(len(biosample_accessions), 1):.1f}%)"
    )
    print(f"  Unique GCFs with ≥1 short-read run  : {n_gcfs_with_sr:,}")
    print(f"  BioSamples with NO short-read run   : {len(no_sr):,}")
    print(f"  Matched via secondary acc only      : {len(matched_via_secondary_only):,}")
    print(f"  Total short-read runs in table      : {len(df):,}")

    gcfs_with_sr = set(df["gcf_accession"].dropna()) if "gcf_accession" in df.columns else set()
    return gcfs_with_sr, df


# ─── CROSS-CHECKS: DEDUPLICATION BETWEEN PIPELINES ───────────────────────────


def report_long_read_overlaps_with_refseq(
    long_read_df: pd.DataFrame,
    refseq_meta: pd.DataFrame,
    dataset_label: str,
    output_dir: Path,
    write_outputs: bool = True,
) -> None:
    """
    Cross-check long-read runs against is_refseq=True metadata rows.
    Reports runs whose sample_accession already appears in the RefSeq set,
    meaning we found long reads for a sample that already has a complete genome.
    Writes the overlapping runs to long_reads_already_in_refseq.tsv.
    """
    sep = "─" * max(1, 70 - len(dataset_label) - 4)
    print(f"\n[{dataset_label}] ── Long-read / RefSeq cross-check {sep}")

    if long_read_df.empty:
        print("  No long-read runs to cross-check.")
        return

    lr_primary = (
        set(long_read_df["sample_accession"].dropna().astype(str).str.strip())
        if "sample_accession" in long_read_df.columns
        else set()
    )
    lr_secondary = (
        set(long_read_df["secondary_sample_accession"].dropna().astype(str).str.strip())
        if "secondary_sample_accession" in long_read_df.columns
        else set()
    )
    lr_all = lr_primary | lr_secondary

    rs_primary = set(refseq_meta[SAMPLE_ACCESSION_COL].dropna().astype(str).str.strip())
    rs_gcf = (
        set(refseq_meta[GCF_ACCESSION_COL].dropna().astype(str).str.strip())
        if GCF_ACCESSION_COL in refseq_meta.columns
        else set()
    )
    rs_all = rs_primary | rs_gcf

    overlap_accs = lr_all & rs_all

    print(f"  Long-read run accessions (primary ∪ secondary) : {len(lr_all):,}")
    print(f"  RefSeq metadata accessions (primary ∪ GCF)     : {len(rs_all):,}")
    print(f"  Overlapping accessions                          : {len(overlap_accs):,}")

    if not overlap_accs:
        print("  → No duplicates — long reads are distinct from the is_refseq set.")
        return

    mask = pd.Series(False, index=long_read_df.index)
    if "sample_accession" in long_read_df.columns:
        mask |= long_read_df["sample_accession"].astype(str).isin(overlap_accs)
    if "secondary_sample_accession" in long_read_df.columns:
        mask |= long_read_df["secondary_sample_accession"].astype(str).isin(overlap_accs)
    overlap_df = long_read_df[mask].copy()

    n_runs = len(overlap_df)
    n_samples = overlap_df["sample_accession"].nunique() if "sample_accession" in overlap_df.columns else "?"
    pct = 100 * len(overlap_accs) / max(len(lr_primary), 1)
    print(f"  Long-read runs linked to RefSeq samples         : {n_runs:,} runs / {n_samples:,} BioSamples")
    print(f"  As % of queried BioSamples with long reads      : {pct:.1f}%")
    print("  → These samples already have complete RefSeq genomes.")

    if write_outputs:
        out_path = output_dir / "long_reads_already_in_refseq.tsv"
        overlap_df.to_csv(out_path, sep="\t", index=False)
        print(f"  Overlap table written to:\n    {out_path}")

    if "instrument_platform" in overlap_df.columns:
        print("\n  Platform breakdown of overlapping runs:")
        for line in overlap_df["instrument_platform"].value_counts().to_string().splitlines():
            print(f"    {line}")

    if "sample_accession" in overlap_df.columns:
        top = (
            overlap_df.groupby("sample_accession")
            .agg(
                n_runs=("run_accession", "count"),
                platform=("instrument_platform", lambda x: x.mode().iloc[0] if len(x) else ""),
            )
            .sort_values("n_runs", ascending=False)
            .head(10)
        )
        print("\n  Top overlapping BioSamples (up to 10):")
        print(f"  {'BioSample':<20}  {'runs':>5}  {'platform'}")
        print(f"  {'─' * 20}  {'─' * 5}  {'─' * 20}")
        for bio, row in top.iterrows():
            print(f"  {str(bio):<20}  {row['n_runs']:>5}  {row['platform']}")


def report_short_read_overlaps_with_nonrefseq(
    short_read_df: pd.DataFrame,
    nonrefseq_meta: pd.DataFrame,
    dataset_label: str,
    output_dir: Path,
    write_outputs: bool = True,
) -> None:
    """
    Cross-check short-read runs (found for RefSeq samples) against is_refseq=False metadata.
    Reports runs whose sample_accession already appears in the non-RefSeq metadata set,
    meaning the short reads for that RefSeq assembly are already tracked as a standalone sample.
    Writes the overlapping runs to short_reads_already_in_nonrefseq.tsv.
    """
    sep = "─" * max(1, 70 - len(dataset_label) - 4)
    print(f"\n[{dataset_label}] ── Short-read / non-RefSeq cross-check {sep}")

    if short_read_df.empty:
        print("  No short-read runs to cross-check.")
        return

    sr_primary = (
        set(short_read_df["sample_accession"].dropna().astype(str).str.strip())
        if "sample_accession" in short_read_df.columns
        else set()
    )
    nr_primary = set(nonrefseq_meta[SAMPLE_ACCESSION_COL].dropna().astype(str).str.strip())

    overlap_accs = sr_primary & nr_primary
    pct = 100 * len(overlap_accs) / max(len(sr_primary), 1)

    print(f"  Short-read run BioSamples found                 : {len(sr_primary):,}")
    print(f"  Non-RefSeq metadata BioSamples                  : {len(nr_primary):,}")
    print(f"  Overlapping BioSamples                          : {len(overlap_accs):,}  ({pct:.1f}%)")

    if not overlap_accs:
        print("  → No duplicates — short reads are not already in the non-RefSeq set.")
        return

    mask = (
        short_read_df["sample_accession"].astype(str).isin(overlap_accs)
        if "sample_accession" in short_read_df.columns
        else pd.Series(False, index=short_read_df.index)
    )
    overlap_df = short_read_df[mask].copy()

    n_runs = len(overlap_df)
    n_samples = overlap_df["sample_accession"].nunique() if "sample_accession" in overlap_df.columns else "?"
    print(f"  Short-read runs from already-known samples       : {n_runs:,} runs / {n_samples:,} BioSamples")
    print("  → These RefSeq assembly short reads are already tracked as non-RefSeq samples.")
    print("    They are strong candidates for the related_short_read_accession link column.")

    if write_outputs:
        out_path = output_dir / "short_reads_already_in_nonrefseq.tsv"
        overlap_df.to_csv(out_path, sep="\t", index=False)
        print(f"  Overlap table written to:\n    {out_path}")

    if "instrument_platform" in overlap_df.columns:
        print("\n  Platform breakdown of overlapping runs:")
        for line in overlap_df["instrument_platform"].value_counts().to_string().splitlines():
            print(f"    {line}")

    if all(c in overlap_df.columns for c in ["sample_accession", "run_accession"]):
        top = (
            overlap_df.groupby("sample_accession")
            .agg(
                n_runs=("run_accession", "count"),
                platform=("instrument_platform", lambda x: x.mode().iloc[0] if len(x) else ""),
            )
            .sort_values("n_runs", ascending=False)
            .head(10)
        )
        print("\n  Top overlapping BioSamples (up to 10):")
        print(f"  {'BioSample':<20}  {'runs':>5}  {'platform'}")
        print(f"  {'─' * 20}  {'─' * 5}  {'─' * 20}")
        for bio, row in top.iterrows():
            print(f"  {str(bio):<20}  {row['n_runs']:>5}  {row['platform']}")


# ─── CLONAL GROUP SUMMARY ─────────────────────────────────────────────────────


def print_clonal_group_summary(
    all_kpsc_rows: pd.DataFrame,
    refseq_rows: pd.DataFrame,
    gcf_accessions: list[str],
    gcfs_with_sr: set[str],
    cg_col: str = "Clonal group",
    top_n: int = 15,
) -> None:
    """Print a per-clonal-group summary of RefSeq coverage and short-read availability (top-N)."""
    if cg_col not in all_kpsc_rows.columns:
        print(f"\n  WARNING: '{cg_col}' column not found — skipping clonal group summary")
        return

    # n_total: all KPSC samples in each CG (is_refseq or not) — used for sorting
    cg_totals = all_kpsc_rows[cg_col].value_counts().rename("n_total")

    # n_is_refseq: is_refseq=True KPSC samples in each CG
    cg_refseq = refseq_rows[cg_col].value_counts().rename("n_is_refseq")

    # n_refseq_with_sr: is_refseq=True samples that have ≥1 short-read run
    sr_df = refseq_rows[[SAMPLE_ACCESSION_COL, cg_col]].copy()
    sr_df["gcf"] = sr_df[SAMPLE_ACCESSION_COL].astype(str).str.extract(r"(GC[AF]_\d+\.\d+)")[0]
    sr_df = sr_df.dropna(subset=["gcf"])
    cg_sr = sr_df[sr_df["gcf"].isin(gcfs_with_sr)].groupby(cg_col).size().rename("n_refseq_with_sr")

    summary = pd.concat([cg_totals, cg_refseq, cg_sr], axis=1).fillna(0).astype(int)
    summary.index.name = cg_col
    summary = summary.sort_values("n_total", ascending=False).head(top_n).reset_index()

    print(f"\n── Top {top_n} Clonal groups (kpsc_final_list, sorted by n_total) ──────────────────")
    print(f"  {'Clonal group':<20}  {'n_total':>8}  {'n_is_refseq':>11}  {'n_refseq_with_sr':>16}  {'% SR/refseq':>11}")
    print(f"  {'─' * 20}  {'─' * 8}  {'─' * 11}  {'─' * 16}  {'─' * 11}")
    for _, row in summary.iterrows():
        pct = 100 * row["n_refseq_with_sr"] / row["n_is_refseq"] if row["n_is_refseq"] > 0 else 0
        print(
            f"  {str(row[cg_col]):<20}  {row['n_total']:>8,}  {row['n_is_refseq']:>11,}  "
            f"{row['n_refseq_with_sr']:>16,}  {pct:>10.1f}%"
        )


# ─── METADATA UPDATE ──────────────────────────────────────────────────────────


def _print_cg_run_summary(
    meta: pd.DataFrame,
    priority_cgs: list[str],
    top_n: int = 15,
) -> None:
    """
    Print a clonal-group table using the joined run columns in meta.

    Counts only existing source rows (run_accession.isna()), but joins to the
    new run rows (run_accession.notna()) to determine which sources have
    sufficient_for_hybrid long reads available.

    Columns shown:
      n_total                   — all KPSC samples in the CG (source rows only)
      n_is_refseq               — complete-genome (RefSeq) samples
      n_refseq_with_sr          — RefSeq samples that have ≥1 short-read run found
      n_nonrefseq_with_suff_lr  — non-RefSeq samples whose best LR run is sufficient
                                  for hybrid (≥50× of 5.5 Mb)

    Priority CGs (PRIORITY_CLONAL_GROUPS) are always included even if outside top N.
    """
    cg_col = "Clonal group"
    kpsc_col = "kpsc_final_list"

    if cg_col not in meta.columns:
        print(f"\n  ('{cg_col}' column not found — skipping CG run summary)", file=sys.stderr)
        return

    has_sr = "related_sr_accession" in meta.columns
    has_lr = "related_lr_accession" in meta.columns

    # Discriminator for appended new-run rows: est_coverage_5_5Mb populated AND
    # is_refseq=False (consistent with the prune logic in _apply_run_info).
    is_appended_meta = pd.Series(False, index=meta.index)
    if "est_coverage_5_5Mb" in meta.columns:
        is_appended_meta = pd.to_numeric(meta["est_coverage_5_5Mb"], errors="coerce").notna() & (
            not meta[IS_REFSEQ_COL]
        )

    # Build set of run_accessions for newly-added LONG-read rows that are
    # sufficient_for_hybrid — derived from the FULL meta (not kpsc-filtered),
    # since appended rows have kpsc_final_list=False.
    suff_lr_run_accs: set[str] = set()
    if "run_accession" in meta.columns and "sufficient_for_hybrid" in meta.columns:
        suff_vals = meta["sufficient_for_hybrid"].astype("string").str.lower()
        suff_mask = is_appended_meta & meta["run_accession"].notna() & (suff_vals == "true")
        suff_lr_run_accs = set(meta.loc[suff_mask, "run_accession"].astype(str))

    # Restrict the per-CG aggregation to existing source rows
    if kpsc_col in meta.columns:
        src = meta[(meta[kpsc_col]) & ~is_appended_meta].copy()
    else:
        src = meta[~is_appended_meta].copy()

    def _agg(g):
        is_rs = g[IS_REFSEQ_COL]
        is_nrs = not g[IS_REFSEQ_COL]
        row = {"n_total": len(g), "n_is_refseq": int(is_rs.sum())}
        if has_sr:
            row["n_refseq_with_sr"] = int((is_rs & g["related_sr_accession"].notna()).sum())
        if has_lr:
            link = g["related_lr_accession"].astype(str)
            row["n_nonrefseq_with_suff_lr"] = int((is_nrs & link.isin(suff_lr_run_accs)).sum())
        return pd.Series(row)

    agg = src.groupby(cg_col).apply(_agg, include_groups=False).sort_values("n_total", ascending=False)

    top_idx = list(agg.head(top_n).index)
    extra = [cg for cg in priority_cgs if cg in agg.index and cg not in top_idx]
    display = agg.loc[top_idx + extra].copy()

    cols = ["n_total", "n_is_refseq"]
    if has_sr:
        cols.append("n_refseq_with_sr")
    if has_lr:
        cols.append("n_nonrefseq_with_suff_lr")

    hdrs = {
        "n_total": "n_total",
        "n_is_refseq": "n_refseq",
        "n_refseq_with_sr": "refseq_with_SR",
        "n_nonrefseq_with_suff_lr": "nonRefseq_suffLR",
    }

    w = 22
    sep = "─"
    print(f"\n── Clonal group — long/short read availability (top {top_n} + priority) ──────────────", file=sys.stderr)
    hdr = f"  {'Clonal group':<{w}}" + "".join(f"  {hdrs[c]:>18}" for c in cols)
    if has_sr:
        hdr += f"  {'%SR/refseq':>10}"
    print(hdr, file=sys.stderr)
    print(
        f"  {sep * w}" + "".join(f"  {sep * 18}" for _ in cols) + (f"  {sep * 10}" if has_sr else ""), file=sys.stderr
    )

    in_top_prev = True
    for cg, row in display.iterrows():
        in_top = cg in top_idx
        if not in_top and in_top_prev:
            print(f"  {'·' * w}", file=sys.stderr)
        in_top_prev = in_top

        is_priority = cg in priority_cgs
        marker = " ◀" if is_priority else ""
        line = f"  {str(cg):<{w}}" + "".join(f"  {int(row.get(c, 0)):>18,}" for c in cols)
        if has_sr:
            n_rs = int(row.get("n_is_refseq", 0))
            pct = 100 * int(row.get("n_refseq_with_sr", 0)) / n_rs if n_rs > 0 else 0
            line += f"  {pct:>9.1f}%"
        line += marker
        print(line, file=sys.stderr)


def _filter_library(df: pd.DataFrame, role: str) -> pd.DataFrame:
    """Drop runs that aren't WGS (and for short reads, that aren't PAIRED).

    Short reads: library_strategy='WGS' AND library_layout='PAIRED'
    Long reads:  library_strategy='WGS'  (long-read runs are typically SINGLE layout)
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    if "library_strategy" in out.columns:
        out = out[out["library_strategy"].astype(str).str.upper() == "WGS"]
    if role == "short_read" and "library_layout" in out.columns:
        out = out[out["library_layout"].astype(str).str.upper() == "PAIRED"]
    return out


def _select_best_runs(df: pd.DataFrame, source_key: str) -> pd.DataFrame:
    """Keep one row per source_key — the one with the highest base_count.
    Ties broken by lowest run_accession alphabetical.
    """
    if df is None or df.empty:
        return df
    bc = pd.to_numeric(df.get("base_count"), errors="coerce")
    tmp = df.assign(_bc=bc.fillna(0))
    tmp = tmp.sort_values(["_bc", "run_accession"], ascending=[False, True])
    return tmp.drop_duplicates(subset=source_key, keep="first").drop(columns="_bc")


# Columns of the side-CSV files written by _apply_run_info. ``run_accession``
# is the primary key (the user-requested first column); the rest carry just
# enough run-level detail to cross-reference back to ENA and the curated row.
_SIDE_CSV_COLS = [
    "run_accession",
    "sample_accession",
    "linked_curated_sample",
    "instrument_platform",
    "library_strategy",
    "library_source",
    "library_layout",
    "base_count",
    "read_count",
    "scientific_name",
    "est_coverage_5_5Mb",
    "sufficient_for_hybrid",
    "source_section",
]


def _build_side_dataframe(
    best_runs: pd.DataFrame | None,
    *,
    role: str,
    source_section: str,
    linked_curated_sample: pd.Series | list | str | None,
) -> pd.DataFrame:
    """Build a side-CSV-shaped DataFrame from a ``best_runs`` selection.

    role:                "short_read" or "long_read" — controls sufficient_for_hybrid
    source_section:      one of "sr_for_refseq" / "lr_for_nonrefseq" / "atb_long_read"
    linked_curated_sample:  per-row value (Series or list) or a literal scalar/None.
                            ``None`` (or empty) means there is no matching curated row
                            (the ATB-increment case).
    """
    if best_runs is None or best_runs.empty:
        return pd.DataFrame(columns=_SIDE_CSV_COLS)

    n = len(best_runs)
    base_count = pd.to_numeric(best_runs.get("base_count"), errors="coerce")

    def _col(name: str, default=pd.NA):
        return best_runs[name].values if name in best_runs.columns else [default] * n

    if linked_curated_sample is None:
        linked_vals: list = [pd.NA] * n
    elif isinstance(linked_curated_sample, (pd.Series, list, tuple)):
        linked_vals = list(linked_curated_sample)
    else:
        linked_vals = [linked_curated_sample] * n

    suff = (base_count >= MIN_BASES_FOR_ASSEMBLY).values if role == "long_read" else [pd.NA] * n

    return pd.DataFrame(
        {
            "run_accession": _col("run_accession"),
            "sample_accession": _col("sample_accession"),
            "linked_curated_sample": linked_vals,
            "instrument_platform": _col("instrument_platform"),
            "library_strategy": _col("library_strategy"),
            "library_source": _col("library_source"),
            "library_layout": _col("library_layout"),
            "base_count": base_count.values,
            "read_count": pd.to_numeric(_col("read_count", default=pd.NA), errors="coerce").values
            if "read_count" in best_runs.columns
            else [pd.NA] * n,
            "scientific_name": _col("scientific_name"),
            "est_coverage_5_5Mb": (base_count / 5_500_000).round(1).values,
            "sufficient_for_hybrid": suff,
            "source_section": source_section,
        },
        columns=_SIDE_CSV_COLS,
    )


def _snapshot_existing_run_accs(meta: pd.DataFrame, col: str) -> set[str]:
    """Return the set of run accessions already captured in ``meta[col]``.

    Handles ';'-joined values (legacy format) and single-accession values.
    """
    if col not in meta.columns:
        return set()
    accs: set[str] = set()
    for v in meta[col].dropna().astype(str):
        for piece in v.split(";"):
            piece = piece.strip()
            if piece:
                accs.add(piece)
    return accs


def _write_side_csv(df: pd.DataFrame, path: str, label: str) -> int:
    """Write a side-DataFrame to CSV, creating parent dir if missing.
    Returns the row count written.
    """
    if df is None or df.empty:
        if Path(path).exists():
            Path(path).unlink()
        return 0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return len(df)


def _apply_run_info(
    meta: pd.DataFrame,
    lr_df: pd.DataFrame,
    sr_df: pd.DataFrame,
    enriched_ncbi_df: pd.DataFrame,
    atb_lr_df: pd.DataFrame | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Update existing rows AND write side-CSVs of newly-located runs.

    This script no longer appends rows to the curated metadata. Row count of
    ``meta`` is preserved end-to-end. Discovered runs land in
    ``RELATED_SR_CSV`` / ``RELATED_LR_CSV``, deduped by run_accession against
    runs already captured in the metadata.

    Stages:
      1. Snapshot existing related_sr/lr_accession values for later dedup, then
         clear prior run columns so they can be re-populated from scratch.
      2. Merge NCBI assembly metadata onto existing RefSeq rows.
      3. Best-run selection per source sample, then update existing rows'
         related_sr_accession / related_lr_accession with that single best run.
      4. Build side-DataFrames of all discovered best runs and write them to
         RELATED_SR_CSV / RELATED_LR_CSV (deduped against the snapshot).
      5. Set sufficient_for_hybrid=True / est_coverage_5_5Mb=NaN on existing
         is_refseq=True rows.
    """
    # ── 1. Snapshot prior related_*_accession values + clear legacy columns ─
    _legacy_prefixes = ("related_long_read_", "related_short_read_")
    _current_cols = (
        "related_lr_accession",
        "related_sr_accession",
        "assembly_sequencing_tech",
        "assembly_method",
        "assembly_bioproject_accession",
        "assembly_release_date",
        "assembly_submitter",
        "assembly_bioproject_title",
        "est_coverage_5_5Mb",
        "sufficient_for_hybrid",
    )
    # Capture pre-script run accessions in metadata so we can avoid writing
    # them to the side-CSVs (dedup is by run_accession, NOT sample_accession).
    prior_sr_accs = _snapshot_existing_run_accs(meta, "related_sr_accession")
    prior_lr_accs = _snapshot_existing_run_accs(meta, "related_lr_accession")

    cols_to_drop = [c for c in meta.columns if c.startswith(_legacy_prefixes) or c in _current_cols]
    if cols_to_drop:
        meta = meta.drop(columns=cols_to_drop)
        if verbose:
            print(
                f"  Cleared {len(cols_to_drop)} pre-existing run columns (re-running this script repopulates them)",
                file=sys.stderr,
            )
            print(
                f"  Snapshot of prior run-accessions for dedup: {len(prior_sr_accs):,} SR, {len(prior_lr_accs):,} LR",
                file=sys.stderr,
            )

    n_refseq = int((meta[IS_REFSEQ_COL]).sum())
    n_nonrefseq = int((not meta[IS_REFSEQ_COL]).sum())

    # Initialise the new linking columns so downstream code can always assume they exist
    meta["related_sr_accession"] = pd.NA
    meta["related_lr_accession"] = pd.NA

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION (i): RefSeq long-read genomes → ENA short reads
    # ─────────────────────────────────────────────────────────────────────────
    # NCBI assembly metadata merge (silent — logged in the structured block below)
    n_resolved = 0
    if enriched_ncbi_df is not None and not enriched_ncbi_df.empty and "gcf" in enriched_ncbi_df.columns:
        n_resolved = len(enriched_ncbi_df)
        ncbi_renamed = enriched_ncbi_df.rename(
            columns={
                "gcf": GCF_ACCESSION_COL,
                "bioproject_accession": "assembly_bioproject_accession",
                "release_date": "assembly_release_date",
                "submitter": "assembly_submitter",
                "sequencing_tech": "assembly_sequencing_tech",
                "assembly_method": "assembly_method",
                "bioproject_title": "assembly_bioproject_title",
            }
        ).drop(columns=["biosample"], errors="ignore")
        meta = meta.merge(ncbi_renamed, on=GCF_ACCESSION_COL, how="left")

    # Filter + best-run select for short reads
    sr_total = len(sr_df) if sr_df is not None else 0
    sr_filtered = _filter_library(sr_df, role="short_read") if sr_df is not None else None
    sr_filt_n = len(sr_filtered) if sr_filtered is not None else 0
    sr_best = (
        _select_best_runs(sr_filtered, "gcf_accession") if sr_filtered is not None and not sr_filtered.empty else None
    )
    sr_best_n = len(sr_best) if sr_best is not None else 0

    # Link existing RefSeq rows to their best short-read run
    sr_existing_filled = 0
    if sr_best is not None and not sr_best.empty:
        sr_link = sr_best[["gcf_accession", "run_accession"]].rename(
            columns={"gcf_accession": GCF_ACCESSION_COL, "run_accession": "related_sr_accession_new"}
        )
        meta = meta.merge(sr_link, on=GCF_ACCESSION_COL, how="left")
        meta["related_sr_accession"] = meta["related_sr_accession_new"].fillna(meta["related_sr_accession"])
        meta = meta.drop(columns=["related_sr_accession_new"])
        sr_existing_filled = int(meta["related_sr_accession"].notna().sum())

    # Print structured block (i)
    if verbose:
        print("\n  ┌─ (i) RefSeq long-read genomes → ENA short reads ──────────────────", file=sys.stderr)
        print(f"  │  Existing RefSeq rows in metadata           : {n_refseq:,}", file=sys.stderr)
        print("  │  NCBI Datasets resolved GCFs (BioSample + assembly metadata)", file=sys.stderr)
        print(
            f"  │      Resolved                                  : {n_resolved:,} of {n_refseq:,} ({100 * n_resolved / max(n_refseq, 1):.1f}%)",
            file=sys.stderr,
        )
        for col in [
            "assembly_sequencing_tech",
            "assembly_method",
            "assembly_bioproject_accession",
            "assembly_release_date",
            "assembly_submitter",
            "assembly_bioproject_title",
        ]:
            if col in meta.columns:
                non_empty = meta[col].fillna("").astype(str).str.strip() != ""
                n = int(non_empty.sum())
                pct = 100 * n / max(n_refseq, 1)
                print(f"  │      {col:<32}: {n:>5,} ({pct:.1f}%)", file=sys.stderr)
        print("  │", file=sys.stderr)
        print("  │  Short-read runs found at these BioSamples   (join key: GCF):", file=sys.stderr)
        print(f"  │      Total runs found                          : {sr_total:,}", file=sys.stderr)
        print(
            f"  │      After library filter (WGS+PAIRED)         : {sr_filt_n:,}  ({sr_total - sr_filt_n:,} dropped)",
            file=sys.stderr,
        )
        print(
            f"  │      Best run per BioSample (unique GCFs)      : {sr_best_n:,}  ({sr_filt_n - sr_best_n:,} dropped)",
            file=sys.stderr,
        )
        print(f"  │      → 'related_sr_accession' set on {sr_existing_filled:,} existing RefSeq rows", file=sys.stderr)
        print(f"  │      → {sr_best_n:,} SR runs will be written to RELATED_SR_CSV (subject to dedup)", file=sys.stderr)
        print("  └────────────────────────────────────────────────────────────────────", file=sys.stderr)

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION (ii): Existing ENA short-read samples → ENA long reads
    # ─────────────────────────────────────────────────────────────────────────
    lr_total = len(lr_df) if lr_df is not None else 0
    lr_filtered = _filter_library(lr_df, role="long_read") if lr_df is not None else None
    lr_filt_n = len(lr_filtered) if lr_filtered is not None else 0
    lr_best = (
        _select_best_runs(lr_filtered, SAMPLE_ACCESSION_COL)
        if lr_filtered is not None and not lr_filtered.empty
        else None
    )
    lr_best_n = len(lr_best) if lr_best is not None else 0
    lr_suff = (
        int(lr_best["sufficient_for_hybrid"].fillna(False).astype(bool).sum())
        if lr_best is not None and not lr_best.empty
        else 0
    )

    lr_existing_filled = 0
    if lr_best is not None and not lr_best.empty:
        lr_link = lr_best[[SAMPLE_ACCESSION_COL, "run_accession"]].rename(
            columns={"run_accession": "related_lr_accession_new"}
        )
        meta = meta.merge(lr_link, on=SAMPLE_ACCESSION_COL, how="left")
        meta["related_lr_accession"] = meta["related_lr_accession_new"].fillna(meta["related_lr_accession"])
        meta = meta.drop(columns=["related_lr_accession_new"])
        lr_existing_filled = int(meta["related_lr_accession"].notna().sum())

    if verbose:
        print("\n  ┌─ (ii) Existing ENA short-read samples → ENA long reads ───────────", file=sys.stderr)
        print(f"  │  Existing non-RefSeq rows in metadata       : {n_nonrefseq:,}", file=sys.stderr)
        print("  │", file=sys.stderr)
        print("  │  Long-read runs found at these BioSamples   (join key: BioSample):", file=sys.stderr)
        print(f"  │      Total runs found                          : {lr_total:,}", file=sys.stderr)
        print(
            f"  │      After library filter (WGS)                : {lr_filt_n:,}  ({lr_total - lr_filt_n:,} dropped)",
            file=sys.stderr,
        )
        print(
            f"  │      Best run per BioSample (unique)           : {lr_best_n:,}  ({lr_filt_n - lr_best_n:,} dropped)",
            file=sys.stderr,
        )
        print(
            f"  │      → 'related_lr_accession' set on {lr_existing_filled:,} existing non-RefSeq rows", file=sys.stderr
        )
        print(
            f"  │      → {lr_best_n:,} LR runs will be written to RELATED_LR_CSV ({lr_suff:,} sufficient for hybrid; subject to dedup)",
            file=sys.stderr,
        )
        print("  └────────────────────────────────────────────────────────────────────", file=sys.stderr)

    # ── sufficient_for_hybrid / est_coverage on existing rows ───────────────
    if "sufficient_for_hybrid" not in meta.columns:
        meta["sufficient_for_hybrid"] = pd.NA
    if "est_coverage_5_5Mb" not in meta.columns:
        meta["est_coverage_5_5Mb"] = pd.NA
    refseq_mask = meta[IS_REFSEQ_COL]
    meta.loc[refseq_mask, "sufficient_for_hybrid"] = True
    meta.loc[refseq_mask, "est_coverage_5_5Mb"] = pd.NA

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION (iii): ATB increment dataset → ENA long reads
    # ─────────────────────────────────────────────────────────────────────────
    atb_total = len(atb_lr_df) if atb_lr_df is not None else 0
    atb_filtered = _filter_library(atb_lr_df, role="long_read") if atb_lr_df is not None else None
    atb_filt_n = len(atb_filtered) if atb_filtered is not None else 0
    atb_best = (
        _select_best_runs(atb_filtered, SAMPLE_ACCESSION_COL)
        if atb_filtered is not None and not atb_filtered.empty
        else None
    )
    atb_best_n = len(atb_best) if atb_best is not None else 0
    atb_suff = 0
    if atb_best is not None and not atb_best.empty:
        atb_suff = int(
            (pd.to_numeric(atb_best.get("base_count"), errors="coerce") >= MIN_BASES_FOR_ASSEMBLY).fillna(False).sum()
        )

    if verbose and atb_total > 0:
        print("\n  ┌─ (iii) ATB increment BioSamples → ENA long reads ─────────────────", file=sys.stderr)
        print("  │  ATB BioSamples are NOT in main metadata; runs land in RELATED_LR_CSV", file=sys.stderr)
        print("  │      with source_section='atb_long_read' and linked_curated_sample=NaN.", file=sys.stderr)
        print("  │", file=sys.stderr)
        print("  │  Long-read runs found at these BioSamples:", file=sys.stderr)
        print(f"  │      Total runs found                          : {atb_total:,}", file=sys.stderr)
        print(
            f"  │      After library filter (WGS)                : {atb_filt_n:,}  ({atb_total - atb_filt_n:,} dropped)",
            file=sys.stderr,
        )
        print(
            f"  │      Best run per BioSample (unique)           : {atb_best_n:,}  ({atb_filt_n - atb_best_n:,} dropped)",
            file=sys.stderr,
        )
        print(
            f"  │      → {atb_best_n:,} ATB LR runs will be added to RELATED_LR_CSV ({atb_suff:,} sufficient for hybrid; subject to dedup)",
            file=sys.stderr,
        )
        print("  └────────────────────────────────────────────────────────────────────", file=sys.stderr)

    # ── Build side-CSV DataFrames (replace the old metadata-row append) ─────
    # For each section, build a side-DataFrame keyed by run_accession with a
    # back-link to the curated Sample (or NaN for ATB-only runs). Then dedup
    # against the run accessions already present in the metadata's
    # related_sr_accession / related_lr_accession columns (snapshotted above
    # before they were cleared).

    sr_side_total = lr_side_total_ii = lr_side_total_iii = 0
    sr_side_df = pd.DataFrame(columns=_SIDE_CSV_COLS)
    lr_side_df = pd.DataFrame(columns=_SIDE_CSV_COLS)

    # Section (i) → related_sr_accessions.csv
    if sr_best is not None and not sr_best.empty:
        rf = meta.loc[refseq_mask & meta["Sample"].notna(), [GCF_ACCESSION_COL, "Sample"]]
        gcf_to_sample = dict(zip(rf[GCF_ACCESSION_COL].astype(str), rf["Sample"].astype(str), strict=False))
        sr_linked = sr_best["gcf_accession"].astype(str).map(gcf_to_sample)
        sr_side_df = _build_side_dataframe(
            sr_best,
            role="short_read",
            source_section="sr_for_refseq",
            linked_curated_sample=sr_linked,
        )
        sr_side_total = len(sr_side_df)

    # Section (ii) → related_lr_accessions.csv (non-RefSeq pipeline)
    if lr_best is not None and not lr_best.empty:
        lr_side_ii = _build_side_dataframe(
            lr_best,
            role="long_read",
            source_section="lr_for_nonrefseq",
            linked_curated_sample=lr_best["sample_accession"].astype(str),
        )
        lr_side_total_ii = len(lr_side_ii)
        lr_side_df = lr_side_ii

    # Section (iii) → related_lr_accessions.csv (ATB increment)
    if atb_best is not None and not atb_best.empty:
        atb_side = _build_side_dataframe(
            atb_best,
            role="long_read",
            source_section="atb_long_read",
            linked_curated_sample=None,  # ATB BioSamples not in metadata
        )
        lr_side_total_iii = len(atb_side)
        lr_side_df = pd.concat([lr_side_df, atb_side], ignore_index=True)

    # Dedup by run_accession against the pre-script-state snapshot.
    sr_drop = (
        sr_side_df["run_accession"].astype(str).isin(prior_sr_accs) if sr_side_total else pd.Series([], dtype=bool)
    )
    sr_side_kept = sr_side_df.loc[~sr_drop].reset_index(drop=True) if sr_side_total else sr_side_df
    sr_dedup_dropped = sr_side_total - len(sr_side_kept)

    lr_total = lr_side_total_ii + lr_side_total_iii
    lr_drop = lr_side_df["run_accession"].astype(str).isin(prior_lr_accs) if lr_total else pd.Series([], dtype=bool)
    lr_side_kept = lr_side_df.loc[~lr_drop].reset_index(drop=True) if lr_total else lr_side_df
    lr_dedup_dropped = lr_total - len(lr_side_kept)

    n_sr_written = _write_side_csv(sr_side_kept, RELATED_SR_CSV, "related_sr_accessions.csv")
    n_lr_written = _write_side_csv(lr_side_kept, RELATED_LR_CSV, "related_lr_accessions.csv")

    if verbose:
        print("\n══ Discovered-runs side-files ══════════════════════════════", file=sys.stderr)
        print(
            f"  related_sr_accessions.csv: {sr_side_total:,} runs found, "
            f"{sr_dedup_dropped:,} dropped as already in metadata, "
            f"{n_sr_written:,} written → {RELATED_SR_CSV}",
            file=sys.stderr,
        )
        print(
            f"  related_lr_accessions.csv: {lr_total:,} runs found "
            f"({lr_side_total_ii:,} from non-RefSeq SR pipeline, "
            f"{lr_side_total_iii:,} from ATB increment), "
            f"{lr_dedup_dropped:,} dropped as already in metadata, "
            f"{n_lr_written:,} written → {RELATED_LR_CSV}",
            file=sys.stderr,
        )
        print("═══════════════════════════════════════════════════════════", file=sys.stderr)

    return meta


def update_metadata_with_run_info(
    metadata_files: list[str],
    lr_df: pd.DataFrame,
    sr_df: pd.DataFrame,
    enriched_ncbi_df: pd.DataFrame,
    atb_lr_df: pd.DataFrame | None = None,
) -> None:
    """
    For each metadata file: load → update existing rows → append new run rows →
    save to source location AND a local copy in the current working directory.

    The first file in the list is treated as 'primary' — its merge is logged in detail
    and the clonal-group summary is computed from it.
    """
    print("\n══ Updating metadata files with run info ════════════════════════════", file=sys.stderr)

    primary_meta: pd.DataFrame | None = None

    for i, path in enumerate(metadata_files):
        is_primary = i == 0
        marker = " (primary — drives CG summary)" if is_primary else " (secondary)"
        print(f"\n── File {i + 1}/{len(metadata_files)}{marker}: {os.path.basename(path)}", file=sys.stderr)

        if not Path(path).exists():
            print(f"  WARNING: file not found, skipping: {path}", file=sys.stderr)
            continue

        meta = pd.read_csv(path, sep="\t", low_memory=False)
        print(f"  Loaded: {meta.shape[0]:,} rows × {meta.shape[1]} columns", file=sys.stderr)

        meta = _apply_run_info(meta, lr_df, sr_df, enriched_ncbi_df, atb_lr_df=atb_lr_df, verbose=is_primary)

        meta.to_csv(path, sep="\t", index=False)
        local_path = os.path.join(os.getcwd(), os.path.basename(path))
        saved_local = False
        if os.path.abspath(local_path) != os.path.abspath(path):
            meta.to_csv(local_path, sep="\t", index=False)
            saved_local = True

        print(f"  Source location : {path}", file=sys.stderr)
        if saved_local:
            print(f"  Local copy      : {local_path}", file=sys.stderr)
        print(f"  Final shape     : {meta.shape[0]:,} rows × {meta.shape[1]} columns", file=sys.stderr)

        if is_primary:
            primary_meta = meta

    if primary_meta is not None:
        _print_cg_run_summary(primary_meta, PRIORITY_CLONAL_GROUPS)


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print metadata columns/sample and exit — use first to check col names"
    )
    parser.add_argument("--limit", type=int, default=None, help="Only query first N samples (for testing)")
    parser.add_argument(
        "--sr-only",
        action="store_true",
        help="Skip long-read ENA queries (metadata + ATB); run only the RefSeq→BioSample→short-read pipeline",
    )
    args = parser.parse_args()

    # ── Set up log file (tee stderr+stdout to a log in cwd) ───────────────────
    log_path = os.path.join(os.getcwd(), LOG_FILE_NAME)
    log_file = open(log_path, "w")
    sys.stderr = _TeeStream(sys.stderr, log_file)
    sys.stdout = _TeeStream(sys.stdout, log_file)
    print(f"\nLog file (in current working directory): {log_path}", file=sys.stderr)

    # ── Load metadata ──────────────────────────────────────────────────────────
    print(f"\nLoading metadata from:\n  {METADATA_FILE}", file=sys.stderr)
    if not Path(METADATA_FILE).exists():
        sys.exit(f"ERROR: metadata file not found:\n  {METADATA_FILE}")

    meta = pd.read_csv(METADATA_FILE, sep="\t", low_memory=False)
    print(f"  Loaded {len(meta):,} rows, {len(meta.columns)} columns", file=sys.stderr)

    # ── Dry-run: inspect columns then exit ────────────────────────────────────
    if args.dry_run:
        print("\n── Column names ──────────────────────────────────────────────")
        for i, col in enumerate(meta.columns):
            print(f"  {i:3d}  {col}")
        print("\n── First 3 rows of key columns ───────────────────────────────")
        key_cols = [c for c in [SAMPLE_ACCESSION_COL, IS_REFSEQ_COL] if c in meta.columns]
        missing = [c for c in [SAMPLE_ACCESSION_COL, IS_REFSEQ_COL] if c not in meta.columns]
        if key_cols:
            print(meta[key_cols].head(3).to_string())
        if missing:
            print(f"\nWARNING: these expected columns were NOT found: {missing}")
            print("  → Update SAMPLE_ACCESSION_COL / IS_REFSEQ_COL at top of script.")
        if IS_REFSEQ_COL in meta.columns:
            print("\n── is_refseq value counts ────────────────────────────────────")
            print(meta[IS_REFSEQ_COL].value_counts(dropna=False).to_string())
        sys.exit(0)

    # ── Validate required columns ──────────────────────────────────────────────
    for col in [SAMPLE_ACCESSION_COL, IS_REFSEQ_COL]:
        if col not in meta.columns:
            sys.exit(
                f"ERROR: column '{col}' not found in metadata.\n"
                f"  Run with --dry-run to see available columns, then update the\n"
                f"  SAMPLE_ACCESSION_COL / IS_REFSEQ_COL variables at the top of this script."
            )

    # ── Filter: keep rows where is_refseq is False (samples without a RefSeq-complete genome) ──
    # is_refseq is used as-is (boolean metadata; expect no NA).
    is_refseq_mask = meta[IS_REFSEQ_COL]
    non_refseq = meta[~is_refseq_mask].copy()

    n_complete = int(is_refseq_mask.sum())
    n_query = len(non_refseq)
    print("\n── is_refseq filter ───────────────────────────────────────────────", file=sys.stderr)
    print(
        f"  Rows with is_refseq=True ({n_complete:,}): "
        "these are complete-genome (RefSeq) samples — skipped for long-read lookup.",
        file=sys.stderr,
    )
    print(
        f"  Rows with is_refseq=False ({n_query:,}): querying ENA for long-read runs.",
        file=sys.stderr,
    )

    # ── Extract metadata sample accessions ─────────────────────────────────────
    meta_lr_df: pd.DataFrame = pd.DataFrame()
    if args.sr_only:
        print("\n  --sr-only: skipping long-read ENA queries for metadata_non_refseq.", file=sys.stderr)
    else:
        accessions = extract_unique_accessions(non_refseq, SAMPLE_ACCESSION_COL)

        if args.limit:
            accessions = accessions[: args.limit]
            print(f"\n  --limit applied: querying first {len(accessions):,} accessions", file=sys.stderr)
        else:
            print(f"\n  Unique sample accessions to query: {len(accessions):,}", file=sys.stderr)

        meta_lr_df = run_long_read_pipeline(
            accessions,
            Path(LONG_READS_OUTPUT_DIR),
            "metadata_non_refseq",
            write_outputs=False,
        )

    # ── RefSeq pipeline: find short reads for is_refseq=True samples ──────────
    refseq_rows = meta[is_refseq_mask].copy()
    print(
        f"\n── refseq short-read pipeline ({n_complete:,} is_refseq=True rows) ─────────",
        file=sys.stderr,
    )

    # Apply kpsc_final_list filter
    kpsc_col = "kpsc_final_list"
    if kpsc_col in refseq_rows.columns:
        before = len(refseq_rows)
        refseq_rows = refseq_rows[refseq_rows[kpsc_col]].copy()
        print(f"  kpsc_final_list filter: {before:,} → {len(refseq_rows):,} rows", file=sys.stderr)
    else:
        print(f"  WARNING: '{kpsc_col}' column not found — skipping kpsc filter", file=sys.stderr)

    # Extract GCF accessions — prefer GCF_ACCESSION_COL (clean GCF_X.N), fall back to regex
    if GCF_ACCESSION_COL in refseq_rows.columns:
        gcf_accessions = extract_unique_accessions(refseq_rows, GCF_ACCESSION_COL)
        # Keep only values that look like assembly accessions
        gcf_accessions = [a for a in gcf_accessions if a.startswith(("GCF_", "GCA_"))]
        print(f"  GCF accessions from '{GCF_ACCESSION_COL}': {len(gcf_accessions):,}", file=sys.stderr)
    else:
        print(
            f"  WARNING: '{GCF_ACCESSION_COL}' not found — extracting GCF via regex from '{SAMPLE_ACCESSION_COL}'",
            file=sys.stderr,
        )
        gcf_accessions = (
            refseq_rows[SAMPLE_ACCESSION_COL]
            .dropna()
            .astype(str)
            .str.extract(r"(GC[AF]_\d+\.\d+)")[0]
            .dropna()
            .unique()
            .tolist()
        )
        print(f"  GCF accessions extracted via regex: {len(gcf_accessions):,}", file=sys.stderr)

    if args.limit:
        gcf_accessions = gcf_accessions[: args.limit]
        print(f"  --limit applied: querying first {len(gcf_accessions):,} GCF accessions", file=sys.stderr)

    # Phase 1: GCF → BioSample via NCBI Datasets API (also returns enriched metadata)
    gcf_to_biosample, enriched_ncbi_df = resolve_gcf_to_biosample(gcf_accessions)
    unresolved_gcfs = [a for a in gcf_accessions if a not in gcf_to_biosample]

    # Phase 2: BioSample → ENA short-read runs
    gcfs_with_sr, sr_df = run_short_read_pipeline(
        gcf_to_biosample=gcf_to_biosample,
        output_dir=Path(SHORT_READS_OUTPUT_DIR),
        dataset_label="refseq_short_reads",
        unresolved_gcfs=unresolved_gcfs,
        enriched_ncbi_df=enriched_ncbi_df,
        write_outputs=False,
    )

    # Cross-check 1: long reads found for non-refseq samples vs is_refseq set
    if not meta_lr_df.empty:
        report_long_read_overlaps_with_refseq(
            meta_lr_df,
            refseq_rows,
            "metadata_non_refseq",
            Path(LONG_READS_OUTPUT_DIR),
            write_outputs=False,
        )

    # Cross-check 2: short reads found for RefSeq samples vs non-refseq metadata
    if not sr_df.empty:
        report_short_read_overlaps_with_nonrefseq(
            sr_df,
            non_refseq,
            "refseq_short_reads",
            Path(SHORT_READS_OUTPUT_DIR),
            write_outputs=False,
        )

    # Clonal group breakdown — universe is all KPSC samples (any is_refseq)
    all_kpsc_rows = meta[meta[kpsc_col]].copy() if kpsc_col in meta.columns else meta
    print_clonal_group_summary(all_kpsc_rows, refseq_rows, gcf_accessions, gcfs_with_sr)

    # ── ATB increment flow (no is_refseq filter) ──────────────────────────────
    atb_lr_df: pd.DataFrame = pd.DataFrame()
    if args.sr_only:
        print("\n  --sr-only: skipping long-read ENA queries for ATB Klebsiella set.", file=sys.stderr)
    else:
        print(f"\nLoading ATB increment data from:\n  {ATB_RELEASE_FILE}", file=sys.stderr)
        if not Path(ATB_RELEASE_FILE).exists():
            sys.exit(f"ERROR: ATB release file not found:\n  {ATB_RELEASE_FILE}")

        atb = pd.read_csv(ATB_RELEASE_FILE, sep="\t", low_memory=False)
        for col in [SAMPLE_ACCESSION_COL, ATB_SCI_NAME_COL]:
            if col not in atb.columns:
                sys.exit(f"ERROR: column '{col}' not found in ATB release file: {ATB_RELEASE_FILE}")

        atb_all_accessions = extract_unique_accessions(atb, SAMPLE_ACCESSION_COL)
        print(
            f"  ATB total unique sample_accession values: {len(atb_all_accessions):,}",
            file=sys.stderr,
        )

        atb_kleb = atb[atb[ATB_SCI_NAME_COL].astype(str).str.contains("Klebsiella", case=False, na=False)].copy()
        atb_kleb_accessions = extract_unique_accessions(atb_kleb, SAMPLE_ACCESSION_COL)
        print(
            f"  ATB Klebsiella-filtered unique sample_accession values: {len(atb_kleb_accessions):,}",
            file=sys.stderr,
        )

        if args.limit:
            atb_kleb_accessions = atb_kleb_accessions[: args.limit]
            print(
                f"  --limit applied to ATB Klebsiella set: querying first {len(atb_kleb_accessions):,} accessions",
                file=sys.stderr,
            )

        atb_lr_df = run_long_read_pipeline(
            atb_kleb_accessions,
            Path(ATB_LONG_READS_OUTPUT_DIR),
            "atb_klebsiella",
        )
        if not atb_lr_df.empty:
            report_long_read_overlaps_with_refseq(
                atb_lr_df,
                refseq_rows,
                "atb_klebsiella",
                Path(ATB_LONG_READS_OUTPUT_DIR),
            )

    # ── Write run info back into BOTH metadata files ───────────────────────────
    update_metadata_with_run_info(
        metadata_files=METADATA_FILES_TO_UPDATE,
        lr_df=meta_lr_df,
        sr_df=sr_df,
        enriched_ncbi_df=enriched_ncbi_df,
        atb_lr_df=atb_lr_df,
    )

    # ── Final log path reminder ───────────────────────────────────────────────
    print(f"\nLog file: {log_path}", file=sys.stderr)
    log_file.close()


if __name__ == "__main__":
    main()
