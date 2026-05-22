#!/usr/bin/env python3
"""find_sample_assemblies.py
-----------------------------
For every sample with ``related_lr_accession`` populated or
``is_complete_norway_genome=True``, query the ENA Portal API for any
submitted assembly (GCA_*) and analysis (ERZ_*) record linked to the
sample's BioSample accession. Writes a per-sample TSV and prints a summary
by study and assembly level.

Rationale
─────────
The "Norway-complete" bucket members in ``reference_bucket.tsv`` are
actually short-read Illumina drafts (median 110 contigs, N50 ≈ 290 kb), not
closed-circle complete genomes. The original publications submitted both
the reads (recorded in our metadata under ``related_lr_accession`` for the
ONT runs and ``related_sr_accession`` for the Illumina runs) and, for some
samples, an assembly to ENA / NCBI. The assembly-bioproject lookup in our
metadata-build pipeline missed those because the assemblies are under a
*different* bioproject (e.g. PRJNA514245) from the read submission
(PRJEB48268 / PRJEB27256 / PRJEB42350).

This script bypasses that by going directly sample → assembly via the ENA
portal: for each BioSample (SAMEA*), it asks ENA for any ``result=assembly``
or ``result=analysis`` record linked to that sample. The output identifies
which samples have a submitted assembly already (and at what level —
``contig`` / ``scaffold`` / ``chromosome`` / ``complete``) so the user can
decide which to download vs. re-assemble from raw long reads.

Usage
─────
    uv run python src/bac_panaroo/pp/download_data/find_sample_assemblies.py
        [--metadata PATH] [--output PATH] [--batch N] [--limit N]

Defaults assume the standard project_k metadata path.
"""

from __future__ import annotations

import argparse
import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david")
METADATA_FILE = DATA_ROOT / "final" / "metadata_final_curated_all_samples_and_columns.tsv"
DEFAULT_OUTPUT = DATA_ROOT / "processed" / "ena_sample_assembly_lookup.tsv"

ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api/search"
DEFAULT_BATCH = 60  # SAMEAs per OR-query — under typical URL/query length limits
DEFAULT_TIMEOUT = 120
DEFAULT_RETRIES = 3

ASSEMBLY_FIELDS = (
    "accession,sample_accession,study_accession,assembly_level,assembly_type,"
    "genome_representation,assembly_quality,assembly_software,base_count,coverage,"
    "scientific_name,last_updated"
)
ANALYSIS_FIELDS = (
    "analysis_accession,sample_accession,study_accession,analysis_type,description,"
    "submitted_format,last_updated"
)

LEVEL_RANK = {
    "contig": 0,
    "scaffold": 1,
    "chromosome": 2,
    "complete genome": 3,
    "complete": 3,
}


def query_ena(result: str, fields: str, sample_ids: list[str]) -> pd.DataFrame:
    """Query ENA Portal for one batch of SAMEAs against ``result=...``.

    ``sample_ids`` are OR'd together as ``sample_accession="SAMEAxxx"`` predicates.
    Returns a DataFrame (empty if no rows or all retries fail).
    """
    quoted = [f'sample_accession="{sid}"' for sid in sample_ids]
    query = " OR ".join(quoted)
    params = {
        "result": result,
        "format": "tsv",
        "fields": fields,
        "query": query,
        "limit": 10000,
    }
    for attempt in range(DEFAULT_RETRIES):
        try:
            r = requests.get(ENA_PORTAL, params=params, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            print(
                f"  WARN result={result} attempt={attempt + 1}: {exc}",
                file=sys.stderr,
            )
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            text = r.text.strip()
            if not text:
                return pd.DataFrame()
            return pd.read_csv(StringIO(text), sep="\t")
        print(
            f"  WARN result={result} attempt={attempt + 1} "
            f"status={r.status_code} body={r.text[:200]!r}",
            file=sys.stderr,
        )
        time.sleep(2 * (attempt + 1))
    print(
        f"FAIL result={result} batch first 3={sample_ids[:3]} after "
        f"{DEFAULT_RETRIES} attempts",
        file=sys.stderr,
    )
    return pd.DataFrame()


def load_subset(metadata_path: Path) -> pd.DataFrame:
    """Load curated metadata and return rows with related_lr_accession or
    is_complete_norway_genome flagged (one row per unique Sample)."""
    print(f"Loading metadata: {metadata_path}", flush=True)
    meta = pd.read_csv(metadata_path, sep="\t", low_memory=False)
    md = meta.drop_duplicates(subset=["Sample"], keep="first").reset_index(drop=True)
    lr_mask = md["related_lr_accession"].notna()
    nor_mask = md["is_complete_norway_genome"].fillna(False).astype(bool)
    keep = md[lr_mask | nor_mask].copy()
    keep["has_lr_accession"] = keep["related_lr_accession"].notna()
    keep["is_norway_complete"] = keep["is_complete_norway_genome"].fillna(False).astype(bool)
    print(
        f"Subset rows: lr_populated={lr_mask.sum()}  "
        f"is_norway_complete={nor_mask.sum()}  union={len(keep)}",
        flush=True,
    )
    return keep


def pick_best_assembly(asm: pd.DataFrame) -> pd.DataFrame:
    """Per sample_accession, keep the highest-assembly_level row (contig <
    scaffold < chromosome < complete). Unknown/blank levels rank last."""
    if asm.empty:
        return pd.DataFrame(columns=["sample_accession"])
    asm = asm.copy()
    asm["level_rank"] = asm["assembly_level"].map(
        lambda v: LEVEL_RANK.get(str(v).lower(), -1)
    )
    asm = asm.sort_values(["sample_accession", "level_rank"], ascending=[True, False])
    return asm.drop_duplicates(subset=["sample_accession"], keep="first")


def pick_first_seqasm_analysis(anl: pd.DataFrame) -> pd.DataFrame:
    """Per sample_accession, keep the first SEQUENCE_ASSEMBLY analysis row."""
    if anl.empty:
        return pd.DataFrame(columns=["sample_accession"])
    seqasm = anl[anl["analysis_type"].astype(str).str.lower() == "sequence_assembly"]
    return seqasm.drop_duplicates(subset=["sample_accession"], keep="first")


def fetch_all(sample_ids: list[str], batch_size: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch ENA assembly + analysis records for ``sample_ids`` in batches."""
    asm_rows: list[pd.DataFrame] = []
    anl_rows: list[pd.DataFrame] = []
    total_batches = (len(sample_ids) + batch_size - 1) // batch_size
    for batch_idx, start in enumerate(range(0, len(sample_ids), batch_size), start=1):
        batch = sample_ids[start : start + batch_size]
        print(
            f"Batch {batch_idx}/{total_batches}  size={len(batch)}",
            flush=True,
        )
        df_a = query_ena("assembly", ASSEMBLY_FIELDS, batch)
        df_n = query_ena("analysis", ANALYSIS_FIELDS, batch)
        if not df_a.empty:
            asm_rows.append(df_a)
        if not df_n.empty:
            anl_rows.append(df_n)
    asm = pd.concat(asm_rows, ignore_index=True) if asm_rows else pd.DataFrame()
    anl = pd.concat(anl_rows, ignore_index=True) if anl_rows else pd.DataFrame()
    print(
        f"Total: assembly rows={len(asm)}  analysis rows={len(anl)}",
        flush=True,
    )
    return asm, anl


def merge_results(
    keep: pd.DataFrame, asm_best: pd.DataFrame, anl_first: pd.DataFrame
) -> pd.DataFrame:
    """Left-merge ENA results onto the metadata subset, one row per Sample."""
    base = keep[
        [
            "Sample",
            "study_accession",
            "is_norway_complete",
            "has_lr_accession",
            "related_lr_accession",
            "related_sr_accession",
            "species",
            "kpsc_final_list",
            "is_refseq",
        ]
    ].rename(columns={"study_accession": "study_in_metadata"})
    base = base.merge(
        asm_best.rename(columns={"sample_accession": "Sample"}),
        on="Sample",
        how="left",
    )
    base = base.merge(
        anl_first[
            ["sample_accession", "analysis_accession", "analysis_type", "submitted_format"]
        ].rename(
            columns={
                "sample_accession": "Sample",
                "analysis_accession": "analysis_erz",
                "analysis_type": "analysis_type",
                "submitted_format": "analysis_format",
            }
        ),
        on="Sample",
        how="left",
    )
    return base


def print_summary(merged: pd.DataFrame) -> None:
    """Print per-cohort + per-study breakdown to stdout."""
    has_asm = merged["accession"].notna()
    has_anl = merged["analysis_erz"].notna()

    print("=== Summary ===\n", flush=True)
    print(f"Total samples queried: {len(merged)}", flush=True)
    print(f"  with submitted assembly (GCA_*):  {has_asm.sum()}", flush=True)
    print(f"  with analysis (ERZ_*):            {has_anl.sum()}", flush=True)
    print(f"  with either:                      {(has_asm | has_anl).sum()}\n", flush=True)

    if has_asm.any():
        print("assembly_level breakdown (across samples with an assembly):", flush=True)
        print(
            "  "
            + merged.loc[has_asm, "assembly_level"]
            .fillna("(blank)")
            .value_counts()
            .to_string()
            .replace("\n", "\n  "),
            flush=True,
        )
        print()

    nc = merged[merged["is_norway_complete"]]
    print(f"Norway-complete subset (n={len(nc)}):", flush=True)
    print(f"  has_assembly: {nc['accession'].notna().sum()} / {len(nc)}", flush=True)
    if nc["accession"].notna().any():
        print(
            "  assembly_level breakdown:\n    "
            + nc.loc[nc["accession"].notna(), "assembly_level"]
            .fillna("(blank)")
            .value_counts()
            .to_string()
            .replace("\n", "\n    "),
            flush=True,
        )
    print()

    print("By study_in_metadata (top 15 by has_assembly count):", flush=True)
    by_study = merged.groupby("study_in_metadata").agg(
        n=("Sample", "size"),
        with_assembly=("accession", lambda s: s.notna().sum()),
    )
    by_study["pct"] = (100 * by_study["with_assembly"] / by_study["n"]).round(1)
    print(
        by_study.sort_values("with_assembly", ascending=False).head(15).to_string(),
        flush=True,
    )
    print()

    print("Where the assemblies live (assembly-record study_accession, top 10):", flush=True)
    if has_asm.any():
        print(
            merged.loc[has_asm, "study_accession"]
            .fillna("(blank)")
            .value_counts()
            .head(10)
            .to_string(),
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    """Parse args, run the ENA lookup pipeline, write TSV + summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--metadata", type=Path, default=METADATA_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N samples (for testing).",
    )
    args = parser.parse_args(argv)

    keep = load_subset(args.metadata)
    sample_ids = keep["Sample"].astype(str).tolist()
    if args.limit:
        sample_ids = sample_ids[: args.limit]
        print(f"Limiting to first {args.limit} samples for testing.", flush=True)

    asm, anl = fetch_all(sample_ids, args.batch)
    asm_best = pick_best_assembly(asm)
    anl_first = pick_first_seqasm_analysis(anl)

    merged = merge_results(
        keep[keep["Sample"].astype(str).isin(sample_ids)], asm_best, anl_first
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, sep="\t", index=False)
    print(f"\nWrote: {args.output}  rows={len(merged)}\n", flush=True)

    print_summary(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
