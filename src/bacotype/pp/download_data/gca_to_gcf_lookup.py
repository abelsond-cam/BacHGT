#!/usr/bin/env python3
"""gca_to_gcf_lookup.py
-----------------------
Take the per-sample TSV produced by ``find_sample_assemblies.py`` (one
GenBank GCA accession per sample, when one was submitted) and enrich it
with NCBI Datasets metadata — most importantly the **paired RefSeq GCF
accession** (when one exists), the **assembly level**, the **sequencing
technology**, and **assembly status / genome notes**.

Why
───
GCF (RefSeq) accessions are NCBI's curated, re-annotated version of GCA
(GenBank) submissions. RefSeq only mints a GCF for assemblies it has
reviewed — typically excludes short-read-only drafts that fail RefSeq's
quality thresholds. So "has a paired GCF" is a sharper "is this a real
reference-tier assembly?" signal than assembly_level alone.

Method
──────
Query NCBI Datasets v2 REST API:

    https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/<comma-list>/dataset_report

Batched at 100 GCAs per call with ``page_size=200`` so each batch comes
back in a single page (default page size is 20 and silently truncates).

Use ``NCBI_API_KEY`` env var to raise the rate limit from 3 req/sec to
10 req/sec (register at https://www.ncbi.nlm.nih.gov/account/).

Usage
─────
    uv run python src/bacotype/pp/download_data/gca_to_gcf_lookup.py
        [--input PATH]    # default: <DATA_ROOT>/processed/ena_sample_assembly_lookup.tsv
        [--output PATH]   # default: <DATA_ROOT>/processed/ena_sample_assembly_lookup_with_gcf.tsv
        [--batch N]       # default: 100

The output TSV is the input TSV plus these new columns:

  paired_gcf_accession     GCF_*.* if RefSeq curated the assembly, else NaN
  ncbi_assembly_level      NCBI's assembly_level (Contig / Scaffold / Chromosome / Complete Genome)
  ncbi_assembly_status     current / replaced / suppressed
  ncbi_sequencing_tech     submitter-reported sequencing_tech (e.g. "PacBio; Illumina")
  ncbi_assembly_method     submitter-reported assembler (e.g. "Unicycler v. 0.4.8")
  ncbi_refseq_category     "reference genome" / "representative genome" / NaN
  ncbi_genome_notes        e.g. "superseded by newer assembly for species"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david")
DEFAULT_INPUT = DATA_ROOT / "processed" / "ena_sample_assembly_lookup.tsv"
DEFAULT_OUTPUT = DATA_ROOT / "processed" / "ena_sample_assembly_lookup_with_gcf.tsv"

NCBI_DATASETS = "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession"
DEFAULT_BATCH = 100
DEFAULT_PAGE_SIZE = 200
DEFAULT_TIMEOUT = 120
DEFAULT_RETRIES = 3

# Polite rate-limit pauses — NCBI permits 3 req/s without an API key,
# 10 req/s with one. We use one GET per batch, so this caps batch frequency.
SLEEP_WITHOUT_KEY = 0.35  # ≤ 3 req/s
SLEEP_WITH_KEY = 0.11  # ≤ 10 req/s


def headers_with_key() -> tuple[dict[str, str], float]:
    """Return request headers (with NCBI key if NCBI_API_KEY is set) and the
    matching per-request sleep that respects NCBI's rate limit."""
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return {"api-key": key}, SLEEP_WITH_KEY
    return {}, SLEEP_WITHOUT_KEY


def query_ncbi(accessions: list[str], headers: dict[str, str]) -> list[dict]:
    """Fetch NCBI Datasets reports for one batch of GCAs. Returns the list of
    report dicts (empty if all retries fail)."""
    url = f"{NCBI_DATASETS}/{','.join(accessions)}/dataset_report"
    params = {"page_size": DEFAULT_PAGE_SIZE}
    for attempt in range(DEFAULT_RETRIES):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            print(
                f"  WARN attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True
            )
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError as exc:
                print(
                    f"  WARN attempt={attempt + 1}: JSON parse error: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(2 * (attempt + 1))
                continue
            reports = data.get("reports", [])
            # If we asked for N accessions and got fewer, the API may have
            # paginated even with page_size=200 — log it for awareness.
            n_returned = len(reports)
            n_total = data.get("total_count", n_returned)
            if n_total > n_returned:
                print(
                    f"  WARN: NCBI returned {n_returned} of {n_total} reports "
                    f"in batch (page truncation)",
                    file=sys.stderr,
                    flush=True,
                )
            return reports
        # Treat 429 / 5xx as retryable
        if r.status_code in (429, 500, 502, 503, 504):
            print(
                f"  WARN attempt={attempt + 1} status={r.status_code}; retrying",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(2 * (attempt + 1))
            continue
        print(
            f"  WARN attempt={attempt + 1} status={r.status_code} body={r.text[:200]!r}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(2 * (attempt + 1))
    print(
        f"FAIL batch first 3={accessions[:3]} after {DEFAULT_RETRIES} attempts",
        file=sys.stderr,
        flush=True,
    )
    return []


def extract_row(report: dict) -> dict:
    """Pull the fields we care about out of one NCBI report dict."""
    ai = report.get("assembly_info", {}) or {}
    notes = ai.get("genome_notes")
    if isinstance(notes, list):
        notes = "; ".join(str(n) for n in notes)
    return {
        "ncbi_accession": report.get("accession"),
        "paired_gcf_accession": report.get("paired_accession"),
        "ncbi_assembly_level": ai.get("assembly_level"),
        "ncbi_assembly_status": ai.get("assembly_status"),
        "ncbi_sequencing_tech": ai.get("sequencing_tech"),
        "ncbi_assembly_method": ai.get("assembly_method"),
        "ncbi_refseq_category": ai.get("refseq_category"),
        "ncbi_genome_notes": notes,
    }


def normalise_gca(acc: str) -> str:
    """NCBI Datasets accepts versioned (GCA_*.*) and bare (GCA_*) accessions.
    We pass through whatever ENA gave us — they normally lack a version
    suffix — and let NCBI resolve to the latest version."""
    return str(acc).strip()


def lookup_all_gcas(gcas: list[str], batch_size: int) -> pd.DataFrame:
    """Batch-query NCBI for all unique GCA accessions. Returns a DataFrame
    with the columns produced by ``extract_row``."""
    headers, sleep_s = headers_with_key()
    print(
        f"Auth mode: {'NCBI_API_KEY set (10 req/s budget)' if headers else 'anon (3 req/s budget)'}",
        flush=True,
    )

    unique_gcas = sorted({normalise_gca(g) for g in gcas if g and str(g) != "nan"})
    print(f"Unique GCAs to query: {len(unique_gcas)}", flush=True)

    rows: list[dict] = []
    seen_lookup_keys: set[str] = set()
    total_batches = (len(unique_gcas) + batch_size - 1) // batch_size
    for batch_idx, start in enumerate(range(0, len(unique_gcas), batch_size), start=1):
        batch = unique_gcas[start : start + batch_size]
        print(f"Batch {batch_idx}/{total_batches}  size={len(batch)}", flush=True)
        reports = query_ncbi(batch, headers)
        for r in reports:
            row = extract_row(r)
            # Keyed by the accession NCBI returned (versioned). Build a
            # lookup column that strips the version so we can join back to
            # the input TSV (which uses bare GCA_xxx accessions).
            ncbi_acc = row["ncbi_accession"]
            row["lookup_accession"] = (
                str(ncbi_acc).split(".")[0] if ncbi_acc else None
            )
            if row["lookup_accession"] in seen_lookup_keys:
                continue
            seen_lookup_keys.add(row["lookup_accession"])
            rows.append(row)
        time.sleep(sleep_s)

    return pd.DataFrame(rows)


def merge_and_summarise(
    input_tsv: Path, ncbi_df: pd.DataFrame, output_tsv: Path
) -> pd.DataFrame:
    """Merge NCBI fields onto the input TSV (joining on the bare GCA) and
    write the enriched TSV. Returns the merged DataFrame."""
    base = pd.read_csv(input_tsv, sep="\t", low_memory=False)
    base["_lookup_accession"] = (
        base["accession"]
        .astype(str)
        .where(base["accession"].notna(), other=None)
        .map(lambda v: None if v is None or v == "nan" else v.split(".")[0])
    )

    merged = base.merge(
        ncbi_df.rename(columns={"lookup_accession": "_lookup_accession"}),
        on="_lookup_accession",
        how="left",
    ).drop(columns=["_lookup_accession"])

    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_tsv, sep="\t", index=False)
    print(f"\nWrote: {output_tsv}  rows={len(merged)}", flush=True)
    return merged


def print_summary(merged: pd.DataFrame) -> None:
    """Print headline stats: paired-GCF coverage, level + tech breakdowns."""
    has_gca = merged["accession"].notna()
    has_gcf = merged["paired_gcf_accession"].notna()
    in_norway = merged["is_norway_complete"].fillna(False).astype(bool)

    print("\n=== Summary ===\n", flush=True)
    print(f"Samples with a GCA assembly:                {has_gca.sum()}", flush=True)
    print(
        f"  of which paired with a GCF (RefSeq):      {has_gcf.sum()}  "
        f"({100 * has_gcf.sum() / max(has_gca.sum(), 1):.1f}% of GCA-bearing)",
        flush=True,
    )
    print(
        f"  Norway-complete & GCF-paired:             "
        f"{(in_norway & has_gcf).sum()} of {in_norway.sum()}",
        flush=True,
    )

    print("\nGCF-paired by NCBI assembly_level:", flush=True)
    if has_gcf.any():
        print(
            "  "
            + merged.loc[has_gcf, "ncbi_assembly_level"]
            .fillna("(blank)")
            .value_counts()
            .to_string()
            .replace("\n", "\n  "),
            flush=True,
        )

    print("\nGCA-without-GCF by NCBI assembly_level:", flush=True)
    only_gca = has_gca & ~has_gcf
    if only_gca.any():
        print(
            "  "
            + merged.loc[only_gca, "ncbi_assembly_level"]
            .fillna("(blank)")
            .value_counts()
            .to_string()
            .replace("\n", "\n  "),
            flush=True,
        )

    print("\nSequencing tech (top 10) — among GCF-paired:", flush=True)
    if has_gcf.any():
        print(
            "  "
            + merged.loc[has_gcf, "ncbi_sequencing_tech"]
            .fillna("(blank)")
            .value_counts()
            .head(10)
            .to_string()
            .replace("\n", "\n  "),
            flush=True,
        )

    print("\nRefSeq category counts (GCF-paired only):", flush=True)
    if has_gcf.any():
        print(
            "  "
            + merged.loc[has_gcf, "ncbi_refseq_category"]
            .fillna("(none)")
            .value_counts()
            .to_string()
            .replace("\n", "\n  "),
            flush=True,
        )

    print("\nAssembly status (GCF-paired only):", flush=True)
    if has_gcf.any():
        print(
            "  "
            + merged.loc[has_gcf, "ncbi_assembly_status"]
            .fillna("(blank)")
            .value_counts()
            .to_string()
            .replace("\n", "\n  "),
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    """Parse args, fetch NCBI metadata for every GCA in the input TSV,
    merge it on, write the enriched TSV, and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    args = parser.parse_args(argv)

    base = pd.read_csv(args.input, sep="\t", low_memory=False)
    gcas = base["accession"].dropna().astype(str).tolist()
    print(f"Loaded {args.input}  rows={len(base)}  with GCA={len(gcas)}", flush=True)

    ncbi_df = lookup_all_gcas(gcas, args.batch)
    print(f"NCBI returned: {len(ncbi_df)} unique GCA records", flush=True)

    merged = merge_and_summarise(args.input, ncbi_df, args.output)
    print_summary(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
