#!/usr/bin/env python3
"""norway_cohort_audit.py
-------------------------
Audit where the Norway *K. pneumoniae* "568 complete genomes" actually
live in public repositories, and how they map onto our curated metadata.

Background
──────────
The Norway KPSC paper (PMC12160537) claims **568 complete genomes** drawn
from **two overarching ENA projects**:

  * ``PRJEB48268`` — **NORKAB**: a reads-only project. 1,110 K. pneumoniae
    samples; 498 are flagged ``is_complete_norway_genome=True`` in our
    metadata (keyed by the SAMEA BioSample in the ``Sample`` column).
  * ``PRJEB74192`` — the **KLEB-GAP umbrella** assembly project, itself an
    aggregate of 10 component sub-projects.

Repeated searches have failed to find complete-genome *assemblies* for the
498 NORKAB samples because the authors deposited **reads only** (Illumina
+ Nanopore). NCBI's Pathogen Detection pipeline rebuilt ~80% of them as
short-read SKESA "Contig" drafts (under PRJNA514245); ~5% have author
Trycycler hybrid drafts — but **none reach "Complete Genome" level** in
either ENA or NCBI. The only RefSeq-mirrored complete genomes findable
across the whole umbrella are 70 GCFs from 4 sub-projects, and those are
already ``is_refseq=True`` in our metadata (matched via
``secondary_sample_accession``) — just not flagged as Norway.

This script reproduces and re-runs that audit so the finding is a
runnable artefact rather than buried chat history. See the report it
prints (``--mode all``) for the headline table.

Data sources
────────────
  * **ENA Portal API** ``/portal/api/filereport``
        ``result=read_run``  — unique samples + scientific_name per project
        ``result=assembly``  — ENA-side assemblies + assembly_level
  * **NCBI Datasets v2** ``/genome/bioproject/{PRJ}/dataset_report``
        paginated; gives GCA + paired GCF + assembly_level + BioSample
  * **NCBI Datasets v2** ``/genome/biosample/{SAMEA}/dataset_report``
        per-NORKAB-sample assembly characterisation (level / method)

Set ``NCBI_API_KEY`` to raise the NCBI rate limit from 3 to 10 req/s.

Modes
─────
    uv run python src/bac_panaroo/pp/download_data/norway_cohort_audit.py
        [--mode projects|prjeb74192|norkab|all]   # default: all
        [--metadata PATH]                          # default: curated slimmed TSV
        [--out-dir PATH]                           # default: <metadata dir>/processed
        [--norkab-limit N]                         # cap NORKAB BioSample probes (debug)

Outputs (written to ``--out-dir``)
  norway_component_project_breakdown.tsv   one row per component project
  norway_prjeb74192_assemblies.tsv         every PRJEB74192 GCA + GCF + level
  norway_norkab_assembly_characterisation.tsv  per-NORKAB-sample assembly rows
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

# ─── PATHS ────────────────────────────────────────────────────────────────────

# Local OneDrive mirror of the curated metadata (same path the rest of
# download_data/ uses). On HPC point --metadata at the rds copy.
DATA_DIR = (
    "/Users/davidabelson/Library/CloudStorage/"
    "OneDrive-UniversityofCambridge/"
    "Aaron Weimann's files - project_k/data/final/metadata/"
)
DEFAULT_METADATA = Path(DATA_DIR) / "metadata_final_curated_slimmed.tsv"

# ─── COHORT DEFINITION ────────────────────────────────────────────────────────

# The umbrella assembly project named in the paper.
UMBRELLA_PROJECT = "PRJEB74192"

# Its 10 component sub-projects, as listed on the ENA browser page for
# PRJEB74192. PRJEB48268 (NORKAB) is itself one of them.
COMPONENT_PROJECTS = [
    "PRJEB43870",
    "PRJEB48268",  # NORKAB — reads-only, the 498 is_complete_norway_genome rows
    "PRJEB57159",
    "PRJEB57169",
    "PRJNA591480",
    "PRJNA922900",
    "PRJNA835677",
    "PRJEB42350",
    "PRJEB27256",
    "PRJEB40149",
]

NORKAB_PROJECT = "PRJEB48268"
NORWAY_FLAG_COL = "is_complete_norway_genome"
SAMPLE_COL = "Sample"
SECONDARY_COL = "secondary_sample_accession"

# ─── API ENDPOINTS ────────────────────────────────────────────────────────────

ENA_FILEREPORT = "https://www.ebi.ac.uk/ena/portal/api/filereport"
NCBI_BIOPROJECT = "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/bioproject/{}/dataset_report"
NCBI_BIOSAMPLE = "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/biosample/{}/dataset_report"

DEFAULT_TIMEOUT = 90
NCBI_PAGE_SIZE = 1000
SLEEP_WITHOUT_KEY = 0.35  # ≤ 3 req/s
SLEEP_WITH_KEY = 0.11  # ≤ 10 req/s


def ncbi_headers() -> tuple[dict[str, str], float]:
    """Return NCBI request headers (with API key if set) and the matching
    per-request sleep that respects NCBI's rate limit."""
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return {"api-key": key}, SLEEP_WITH_KEY
    return {}, SLEEP_WITHOUT_KEY


# ─── ENA ──────────────────────────────────────────────────────────────────────


def ena_filereport(accession: str, result: str, fields: str, limit: int = 50000) -> pd.DataFrame:
    """Query the ENA Portal ``filereport`` endpoint for one accession.

    Returns an empty DataFrame on any error or "no rows" response (ENA
    answers an unknown/empty query with a body that starts with
    ``Accession``)."""
    try:
        r = requests.get(
            ENA_FILEREPORT,
            params={"accession": accession, "result": result, "fields": fields,
                    "format": "tsv", "limit": limit},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"  WARN ENA {result} {accession}: {exc}", file=sys.stderr, flush=True)
        return pd.DataFrame()
    if r.status_code != 200 or not r.text:
        return pd.DataFrame()
    first_line = r.text.split("\n", 1)[0]
    if first_line.startswith("Accession") and "not valid" in first_line:
        return pd.DataFrame()
    try:
        return pd.read_csv(io.StringIO(r.text), sep="\t", low_memory=False)
    except (pd.errors.ParserError, ValueError):
        return pd.DataFrame()


# ─── NCBI DATASETS ────────────────────────────────────────────────────────────


def ncbi_bioproject_records(project: str, headers: dict[str, str], sleep_s: float) -> list[dict]:
    """Page through every NCBI Datasets assembly report for a BioProject.

    NCBI returns each GCA and its paired RefSeq GCF as separate report
    dicts; callers should de-dupe to GCA primaries themselves."""
    url = NCBI_BIOPROJECT.format(project)
    records: list[dict] = []
    params: dict[str, object] = {"page_size": NCBI_PAGE_SIZE}
    for _ in range(200):  # hard page ceiling — guards against a stuck token
        try:
            r = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            print(f"  WARN NCBI {project}: {exc}", file=sys.stderr, flush=True)
            break
        if r.status_code != 200:
            print(f"  WARN NCBI {project}: HTTP {r.status_code}", file=sys.stderr, flush=True)
            break
        data = r.json()
        records.extend(data.get("reports", []))
        token = data.get("next_page_token")
        if not token:
            break
        params = {"page_size": NCBI_PAGE_SIZE, "page_token": token}
        time.sleep(sleep_s)
    return records


def ncbi_biosample_records(samea: str, headers: dict[str, str]) -> list[dict]:
    """Fetch NCBI Datasets assembly reports for one BioSample (≤20 rows)."""
    try:
        r = requests.get(
            NCBI_BIOSAMPLE.format(samea),
            params={"page_size": 20},
            headers=headers,
            timeout=30,
        )
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    return r.json().get("reports", [])


def _gca_primaries(records: list[dict]) -> pd.DataFrame:
    """Collapse raw NCBI reports to one row per GCA primary, carrying the
    paired GCF, BioSample, assembly level and method."""
    rows = []
    for rec in records:
        acc = rec.get("accession", "")
        if not acc.startswith("GCA_"):
            continue
        ai = rec.get("assembly_info", {}) or {}
        rows.append(
            {
                "gca": acc,
                "gcf": rec.get("paired_accession", ""),
                "biosample": (ai.get("biosample", {}) or {}).get("accession", ""),
                "level": ai.get("assembly_level", ""),
                "method": ai.get("assembly_method", ""),
                "submitter": ai.get("submitter", ""),
            }
        )
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset="gca") if len(df) else df


# ─── MODE: per-component-project breakdown ────────────────────────────────────


def audit_component_projects(headers: dict[str, str], sleep_s: float) -> pd.DataFrame:
    """For each component project, count ENA samples / Klebsiella reads and
    NCBI samples-with-GCF / complete-genome GCFs. This is the table in the
    headline report."""
    rows = []
    for pj in COMPONENT_PROJECTS:
        print(f"[{pj}] querying ENA + NCBI ...", flush=True)
        runs = ena_filereport(pj, "read_run", "sample_accession,scientific_name", limit=20000)
        if len(runs) and "sample_accession" in runs.columns:
            runs = runs.drop_duplicates(subset="sample_accession")
            n_samples = len(runs)
            n_klebs = int(
                runs["scientific_name"].astype(str).str.contains("Klebsiella", na=False).sum()
            )
        else:
            n_samples = n_klebs = 0

        recs = ncbi_bioproject_records(pj, headers, sleep_s)
        gca = _gca_primaries(recs)
        if len(gca):
            has_gcf = gca["gcf"].astype(str).str.startswith("GCF_")
            n_with_gcf = int(has_gcf.sum())
            n_complete_gcf = int((has_gcf & (gca["level"] == "Complete Genome")).sum())
        else:
            n_with_gcf = n_complete_gcf = 0

        rows.append(
            {
                "project": pj,
                "is_norkab": pj == NORKAB_PROJECT,
                "n_samples_ENA": n_samples,
                "n_klebsiella_ENA": n_klebs,
                "n_GCA_NCBI": len(gca),
                "n_samples_with_GCF_NCBI": n_with_gcf,
                "n_complete_GCF_NCBI": n_complete_gcf,
            }
        )
        time.sleep(sleep_s)

    df = pd.DataFrame(rows)
    total = {
        "project": "TOTAL",
        "is_norkab": False,
        "n_samples_ENA": df["n_samples_ENA"].sum(),
        "n_klebsiella_ENA": df["n_klebsiella_ENA"].sum(),
        "n_GCA_NCBI": df["n_GCA_NCBI"].sum(),
        "n_samples_with_GCF_NCBI": df["n_samples_with_GCF_NCBI"].sum(),
        "n_complete_GCF_NCBI": df["n_complete_GCF_NCBI"].sum(),
    }
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ─── MODE: PRJEB74192 umbrella vs our metadata ────────────────────────────────


def audit_prjeb74192(metadata: pd.DataFrame, headers: dict[str, str], sleep_s: float) -> pd.DataFrame:
    """Pull every PRJEB74192 GCA, then cross-check the Complete-Genome GCFs
    against ``secondary_sample_accession`` in our metadata and report how
    many are flagged is_refseq vs is_complete_norway_genome."""
    recs = ncbi_bioproject_records(UMBRELLA_PROJECT, headers, sleep_s)
    gca = _gca_primaries(recs)
    print(f"\nPRJEB74192 GCAs: {len(gca)}", flush=True)
    if len(gca):
        print(f"  level breakdown: {gca['level'].value_counts().to_dict()}", flush=True)

    our_gcf = set()
    if SECONDARY_COL in metadata.columns:
        sec = metadata[SECONDARY_COL].dropna().astype(str)
        our_gcf = set(sec[sec.str.startswith("GCF_")])

    for level, sub in gca.groupby("level"):
        gcfs = {g for g in sub["gcf"] if str(g).startswith("GCF_")}
        in_meta = gcfs & our_gcf
        print(
            f"\n  '{level}' assemblies: {len(sub)} "
            f"(paired GCFs in metadata.{SECONDARY_COL}: {len(in_meta)}/{len(gcfs)})",
            flush=True,
        )

    complete = gca[gca["level"] == "Complete Genome"]
    samn_set = {s for s in complete["biosample"] if s}
    in_meta = metadata[
        metadata[SAMPLE_COL].astype(str).isin(samn_set)
        | (metadata.get(SECONDARY_COL, pd.Series(dtype=str)).astype(str).isin(samn_set))
    ]
    print(f"\nPRJEB74192 Complete-Genome BioSamples in our metadata: {len(in_meta)}", flush=True)
    if len(in_meta) and "is_refseq" in in_meta.columns:
        print(f"  is_refseq: {in_meta['is_refseq'].value_counts().to_dict()}", flush=True)
    if len(in_meta) and NORWAY_FLAG_COL in in_meta.columns:
        print(f"  {NORWAY_FLAG_COL}: {in_meta[NORWAY_FLAG_COL].value_counts().to_dict()}", flush=True)

    return gca


# ─── MODE: NORKAB 498 — what assemblies actually exist? ───────────────────────


def audit_norkab(metadata: pd.DataFrame, headers: dict[str, str], limit: int | None) -> pd.DataFrame:
    """For every ``is_complete_norway_genome=True`` BioSample, ask NCBI
    Datasets what assemblies exist and at what level. Confirms the cohort
    is Contig/SKESA drafts with no Complete-Genome assembly anywhere."""
    if NORWAY_FLAG_COL not in metadata.columns:
        print(f"  metadata has no '{NORWAY_FLAG_COL}' column — skipping NORKAB mode", flush=True)
        return pd.DataFrame()
    sameas = (
        metadata.loc[metadata[NORWAY_FLAG_COL] == True, SAMPLE_COL]  # noqa: E712
        .astype(str)
        .tolist()
    )
    if limit:
        sameas = sameas[:limit]
    print(f"\nProbing NCBI Datasets for {len(sameas)} NORKAB BioSamples ...", flush=True)

    rows = []
    n_with = 0
    for i, samea in enumerate(sameas, start=1):
        recs = ncbi_biosample_records(samea, headers)
        if recs:
            n_with += 1
        for rec in recs:
            ai = rec.get("assembly_info", {}) or {}
            stats = rec.get("assembly_stats", {}) or {}
            rows.append(
                {
                    "sample": samea,
                    "accession": rec.get("accession", ""),
                    "paired_gcf": rec.get("paired_accession", ""),
                    "level": ai.get("assembly_level", ""),
                    "submitter": ai.get("submitter", ""),
                    "method": ai.get("assembly_method", ""),
                    "n_contigs": stats.get("number_of_contigs", ""),
                    "contig_n50": stats.get("contig_n50", ""),
                }
            )
        if i % 100 == 0:
            print(f"  ... {i}/{len(sameas)} probed; records so far: {len(rows)}", flush=True)
        time.sleep(0.1)

    df = pd.DataFrame(rows)
    print(f"\n=== NORKAB assembly characterisation ({len(sameas)} samples) ===", flush=True)
    print(f"Samples with ≥1 assembly: {n_with}/{len(sameas)}", flush=True)
    if len(df):
        gca = df[df["accession"].astype(str).str.startswith("GCA_")].drop_duplicates("accession")
        print(f"Unique GCA assemblies: {len(gca)}", flush=True)
        print(f"Assembly levels: {gca['level'].value_counts().to_dict()}", flush=True)
        print(
            f"Has paired GCF: {int(gca['paired_gcf'].astype(str).str.startswith('GCF_').sum())}",
            flush=True,
        )
        n_complete = int((gca["level"] == "Complete Genome").sum())
        print(f"** Complete-Genome assemblies: {n_complete} **", flush=True)
        print(
            f"Top assembly methods: "
            f"{dict(Counter(gca['method'].astype(str)).most_common(5))}",
            flush=True,
        )
    return df


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Parse args and run the requested audit mode(s), writing TSVs to
    ``--out-dir`` and printing the headline summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--mode",
        choices=["projects", "prjeb74192", "norkab", "all"],
        default="all",
    )
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--norkab-limit",
        type=int,
        default=None,
        help="cap NORKAB BioSample probes (for a quick smoke-test)",
    )
    args = parser.parse_args(argv)

    out_dir = args.out_dir or args.metadata.parent / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    headers, sleep_s = ncbi_headers()
    print(
        f"NCBI auth: {'NCBI_API_KEY set (10 req/s)' if headers else 'anon (3 req/s)'}",
        flush=True,
    )

    metadata = pd.read_csv(args.metadata, sep="\t", low_memory=False)
    print(f"Loaded metadata: {args.metadata}  rows={len(metadata)}", flush=True)
    if NORWAY_FLAG_COL in metadata.columns:
        n_flag = int((metadata[NORWAY_FLAG_COL] == True).sum())  # noqa: E712
        print(f"  {NORWAY_FLAG_COL}=True rows: {n_flag}", flush=True)

    if args.mode in ("projects", "all"):
        breakdown = audit_component_projects(headers, sleep_s)
        path = out_dir / "norway_component_project_breakdown.tsv"
        breakdown.to_csv(path, sep="\t", index=False)
        print(f"\n=== Component-project breakdown → {path} ===", flush=True)
        print(breakdown.to_string(index=False), flush=True)

    if args.mode in ("prjeb74192", "all"):
        gca = audit_prjeb74192(metadata, headers, sleep_s)
        path = out_dir / "norway_prjeb74192_assemblies.tsv"
        gca.to_csv(path, sep="\t", index=False)
        print(f"\nWrote {path}  rows={len(gca)}", flush=True)

    if args.mode in ("norkab", "all"):
        norkab = audit_norkab(metadata, headers, args.norkab_limit)
        path = out_dir / "norway_norkab_assembly_characterisation.tsv"
        norkab.to_csv(path, sep="\t", index=False)
        print(f"\nWrote {path}  rows={len(norkab)}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
