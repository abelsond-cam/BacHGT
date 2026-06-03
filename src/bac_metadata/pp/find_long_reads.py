#!/usr/bin/env python3
"""
find_long_reads.py
------------------
Reads metadata_final_curated_slimmed.tsv, filters to non-RefSeq samples
(i.e. those WITHOUT a complete genome already), then queries ENA Portal API
in parallel batches to find associated long-read runs (ONT or PacBio).
Then reads atb_release_incr_2_species_calls.tsv, filters to rows whose
scientific_name contains "Klebsiella", and runs the same ENA pipeline.

Usage:
    python find_long_reads.py [--dry-run] [--limit N]

    --dry-run   Print column names and first few rows, then exit.
                Use this first to confirm column names are correct.
    --limit N   Only process first N samples (useful for testing).

Output:
    <metadata_dir>/processed/long_reads/long_read_runs.tsv
    <metadata_dir>/processed/long_reads/long_read_runs_summary.tsv
    <metadata_dir>/processed/long_reads/samples_with_no_long_reads.txt
    <metadata_dir>/processed/long_reads/samples_matched_via_secondary_only.txt
"""

import requests
import pandas as pd
import argparse
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import islice

# ─── CONFIGURE THESE ──────────────────────────────────────────────────────────

DATA_DIR = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/"
METADATA_FILE = DATA_DIR + "metadata_final_curated_slimmed.tsv"
OUTPUT_DIR    = DATA_DIR + "processed/long_reads/"
LONG_READS_OUTPUT_DIR = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/long_reads/"
ATB_RELEASE_FILE = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/atb_release_incr_2_species_calls.tsv"
)

# Column names in the metadata file — adjust if dry-run reveals different names
SAMPLE_ACCESSION_COL = "sample_accession"   # e.g. SAMEA..., SAMN...
IS_REFSEQ_COL        = "is_refseq"          # boolean column (expected filled; used as-is)
ATB_SCI_NAME_COL     = "scientific_name"

# Platforms to retrieve
LONG_READ_PLATFORMS = {"OXFORD_NANOPORE", "PACBIO_SMRT"}

# API settings
ENA_PORTAL  = "https://www.ebi.ac.uk/ena/portal/api/search"
BATCH_SIZE  = 50      # accessions per API request (keep ≤50 to avoid URL length limits)
MAX_WORKERS = 8       # parallel threads — polite for ENA; increase to 16 if needed
RETRY_MAX   = 3
RETRY_PAUSE = 10      # seconds between retries on rate limit

FIELDS = ",".join([
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
])

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
    clauses = [
        f'(sample_accession="{a}" OR secondary_sample_accession="{a}")'
        for a in sample_accs
    ]
    query = " OR ".join(clauses)

    params = {
        "result":  "read_run",
        "query":   query,
        "fields":  FIELDS,
        "format":  "json",
        "limit":   0,   # 0 = return all matches
    }

    for attempt in range(RETRY_MAX):
        try:
            r = requests.get(ENA_PORTAL, params=params, timeout=60)

            if r.status_code == 200:
                if not r.text.strip():
                    return []
                try:
                    return r.json()
                except Exception:
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
    return [
        r for r in runs
        if r.get("instrument_platform", "").upper() in LONG_READ_PLATFORMS
    ]


# ─── BATCHING HELPERS ─────────────────────────────────────────────────────────

def batched(iterable, n):
    """Yield successive n-sized chunks from iterable."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


def extract_unique_accessions(df: pd.DataFrame, column: str) -> list[str]:
    """Return unique non-empty sample accession strings from a dataframe column."""
    accessions = (
        df[column]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
    return [a for a in accessions if a and a.lower() != "nan"]


def run_long_read_pipeline(accessions: list[str], output_dir: Path, dataset_label: str):
    """Run ENA querying, long-read filtering, and write outputs for one accession set."""
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
        future_to_batch = {
            pool.submit(query_ena_batch, batch): batch
            for batch in batches
        }

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
                    f"elapsed: {elapsed/60:.1f}m  eta: {remaining/60:.1f}m",
                    file=sys.stderr,
                )

    elapsed_total = time.time() - t0
    print(f"\n[{dataset_label}] Done in {elapsed_total/60:.1f} minutes", file=sys.stderr)
    print(f"[{dataset_label}] Total long-read runs found: {len(all_long_read_runs):,}", file=sys.stderr)

    if not all_long_read_runs:
        print(f"\n[{dataset_label}] No long reads found for any samples.", file=sys.stderr)
        pd.DataFrame().to_csv(out_tsv, sep="\t", index=False)
        Path(out_no_lr).write_text("\n".join(accessions))
        Path(out_secondary_only).write_text("")
        return

    df = pd.DataFrame(all_long_read_runs)

    for col in ["read_count", "base_count", "fastq_bytes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "base_count" in df.columns:
        df["est_coverage_5_5Mb"] = (df["base_count"] / 5_500_000).round(1)
        df["sufficient_for_hybrid"] = df["base_count"] >= MIN_BASES_FOR_ASSEMBLY

    df.to_csv(out_tsv, sep="\t", index=False)
    print(f"\n[{dataset_label}] Full run table written to:\n    {out_tsv}", file=sys.stderr)

    summary_cols = [
        c for c in [
            "sample_accession", "secondary_sample_accession",
            "instrument_platform", "instrument_model",
            "run_accession", "read_count", "base_count",
            "est_coverage_5_5Mb", "sufficient_for_hybrid",
            "fastq_ftp", "first_public",
        ]
        if c in df.columns
    ]
    summary = df[summary_cols].copy()
    summary.to_csv(out_summary, sep="\t", index=False)
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
    Path(out_no_lr).write_text("\n".join(no_lr) + "\n")
    print(
        f"[{dataset_label}] Samples with NO long reads ({len(no_lr):,}) written to:\n    {out_no_lr}",
        file=sys.stderr,
    )

    if "sample_accession" in df.columns:
        matched_via_secondary_only = sorted(
            a for a in accessions
            if a in samples_with_lr and a not in primary_vals
        )
    else:
        matched_via_secondary_only = []
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
        print(f"\n[{dataset_label}] ── Runs with ≥50x coverage (≥{MIN_BASES_FOR_ASSEMBLY/1e6:.0f} Mb): "
              f"{n_sufficient:,} runs across {n_samples_sufficient:,} queried samples "
              f"(primary ∪ secondary accession match)")

    print(
        f"\n[{dataset_label}] ── Unique queried samples with ≥1 long-read run: {n_queried_with_lr:,} "
        f"(primary ∪ secondary accession match)"
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print metadata columns/sample and exit — use first to check col names")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only query first N samples (for testing)")
    args = parser.parse_args()

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
        print(f"\n── First 3 rows of key columns ───────────────────────────────")
        key_cols = [c for c in [SAMPLE_ACCESSION_COL, IS_REFSEQ_COL] if c in meta.columns]
        missing   = [c for c in [SAMPLE_ACCESSION_COL, IS_REFSEQ_COL] if c not in meta.columns]
        if key_cols:
            print(meta[key_cols].head(3).to_string())
        if missing:
            print(f"\nWARNING: these expected columns were NOT found: {missing}")
            print("  → Update SAMPLE_ACCESSION_COL / IS_REFSEQ_COL at top of script.")
        if IS_REFSEQ_COL in meta.columns:
            print(f"\n── is_refseq value counts ────────────────────────────────────")
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
    accessions = extract_unique_accessions(non_refseq, SAMPLE_ACCESSION_COL)

    if args.limit:
        accessions = accessions[: args.limit]
        print(f"\n  --limit applied: querying first {len(accessions):,} accessions", file=sys.stderr)
    else:
        print(f"\n  Unique sample accessions to query: {len(accessions):,}", file=sys.stderr)

    run_long_read_pipeline(accessions, Path(LONG_READS_OUTPUT_DIR), "metadata_non_refseq")

    # ── ATB increment flow (no is_refseq filter) ──────────────────────────────
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

    run_long_read_pipeline(
        atb_kleb_accessions,
        Path(LONG_READS_OUTPUT_DIR) / "atb_release_incr_2_species_calls",
        "atb_klebsiella",
    )


if __name__ == "__main__":
    main()