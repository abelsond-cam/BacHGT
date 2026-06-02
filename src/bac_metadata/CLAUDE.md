# CLAUDE.md — bac_metadata

The `bac_metadata` subpackage of the BacHGT monorepo, absorbed from the former
standalone metadata-curation repo. Monorepo and global guidance:
`BacHGT/CLAUDE.md` and `~/.claude/CLAUDE.md`. The package is now `bac_metadata`
(was `Klebsiella`) and runs on the shared uv environment. Where the text below
refers to OneDrive-synced paths, that predates the migration — code now lives
under `~/developer` (local) / `~/workspace` (HPC).

> **📖 Read first: [`METADATA_v2_README.md`](METADATA_v2_README.md)** — the
> authoritative description of metadata_v2 (cohort definition, row keying,
> flag definitions, every column group's source, the rebuild pipeline). Anyone
> writing code that consumes the table should start there. This file (the
> CLAUDE.md) covers package-internal layout + how to *re-run* the pipeline.

## Project Overview

A metadata curation and processing pipeline for Klebsiella bacterial genomic data. Ingests metadata from the European Nucleotide Archive (ENA), integrates quality control data (Kleborate, bakrep, LINcode), and produces cleaned, categorized metadata TSVs for downstream analysis.

## Package Manager

This project uses **uv**. Run scripts with `uv run <script>` or activate the environment with `uv sync` first.

```bash
uv sync                          # Install dependencies
uv run python src/bac_metadata/pp/<script>.py # Run a script
```

## Pipeline Execution Order

The three main scripts must be run in sequence:

**Step 1 — Collate ENA metadata:**
```bash
uv run python src/bac_metadata/pp/metadata_collation.py \
  --metadata-file1 <ENA_TSV_1> \
  --metadata-file2 <ENA_TSV_2> \
  --metadata-file3 <ENA_TSV_3> \
  --ena-project-dir <DIR_WITH_READY_TO_MERGE_FILES>
```
Output: `intermediate_collated_metadata_wo_qc_or_kleborate.tsv`

**Step 2 — Integrate QC data:**
```bash
uv run python src/bac_metadata/pp/qc_add_metadata.py \
  --input-file <COLLATED_METADATA> \
  --qc-excel-path <QC_EXCEL> \
  --output-dir <OUTPUT_DIR>
```
Output: `qc_final_with_metadata.tsv`

**Step 3 — Curate metadata fields:**
```bash
uv run python src/bac_metadata/pp/metadata_curation.py \
  --metadata-dir <METADATA_DIR> \
  --metadata-file qc_final_with_metadata.tsv \
  --output-file metadata_final_curated_all_samples_and_columns.tsv \
  --output-file-slimmed metadata_final_curated_slimmed.tsv
```
Output: two TSVs + `parsed_metadata.log`

**Optional — Find long-read sequences:**
```bash
uv run python src/bac_metadata/pp/find_long_reads.py [--dry-run] [--limit N]
```
Queries ENA Portal API and NCBI Datasets API for ONT/PacBio runs.

**Optional — Generate analysis plots:**
```bash
uv run python src/bac_metadata/pp/metadata_analysis.py [--metadata-file FILE]
```

## Architecture

### Data Flow

```
ENA metadata TSVs + ready_to_merge patches
        ↓ metadata_collation.py
intermediate_collated_metadata_wo_qc_or_kleborate.tsv
        ↓ qc_add_metadata.py  ← QC Excel (bakrep/RefSeq/NCTC/Kleborate/LINcode sheets)
qc_final_with_metadata.tsv
        ↓ metadata_curation.py  ← Google Sheet (study-level metadata)
metadata_final_curated_all_samples_and_columns.tsv
metadata_final_curated_slimmed.tsv
```

### Key Modules (`src/bac_metadata/pp/`)

- **`metadata_collation.py`** — Merges ENA TSV exports; applies row-level patches from "ready_to_merge" files (one per ENA project)
- **`qc_add_metadata.py`** — Builds unified QC dataframe from multiple Excel sheets; left-joins metadata onto QC rows; applies KPSC final-list filtering
- **`metadata_curation.py`** — Main curation engine (~286KB). Contains all parsing and categorization logic inline. Reads study-level metadata from a Google Sheet
- **`find_long_reads.py`** — Queries ENA Portal API for long-read runs; resolves RefSeq GCF accessions → BioSample IDs via NCBI Datasets API
- **`metadata_analysis.py`** — Generates species/ST/geography/host/isolation-source plots as PNGs and interactive HTML
- **`date_utils.py`** — Date normalization helpers used by `metadata_curation.py`

Metadata-enrichment modules absorbed from `bac_panaroo` (run after curation, each overwrites the curated TSV in place):

- **`add_paths_gff_fna_to_metadata.py`** — Scans assembly / GFF (and ISEScan) roots and writes resolved per-sample file-path columns into the metadata TSV
- **`count_gff_features.py`** — Counts GFF feature types per sample (annotation QC) into a sidecar TSV
- **`merge_gff_feature_counts_into_metadata.py`** — Merges those `n_*` feature counts into the metadata TSV
- **`add_poppunk_clusters_to_metadata.py`** — Adds the `poppunk_cluster` typing column from a PopPUNK clusters CSV
- **`slim_metadata.py`** — Derives `metadata_final_curated_slimmed.tsv` as a column subset of the full curated TSV

### Parsing & Categorization (in `metadata_curation.py`)

The curation step normalizes four key ENA fields using regex substitution rules and lookup tables:

- `parse_host()` / `categorise_host()` — Maps Latin binomial names → common names → categories (human, livestock, poultry, wild animals, wastewater, etc.)
- `parse_isolation_source()` / `categorise_isolation_source()` — Maps free-text isolation sources → standard categories (blood, urine, faeces, respiratory, wound, water, etc.)
- `parse_country()` / `categorise_region()` — Normalizes country names; maps to WHO/geographic regions
- `parse_collection_date()` — Handles partial dates, ambiguous formats, and non-date placeholders

These functions emit verbose output to support iterative rule refinement when ENA data evolves.

## Configuration & External Dependencies

**Hardcoded paths** — Scripts use absolute paths to OneDrive-synced directories. When paths change (e.g., after repo move), update the `METADATA_DIR`, `OUTPUT_DIR`, and related constants at the top of each script.

**Google Sheets/Drive authentication:**
- OAuth2 flow; credentials file at `~/.../client_secret_*.json`
- Token cached at `src/bac_metadata/pp/token.json` after first run
- Study-level metadata Google Sheet ID: `1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk`
- Run `uv run python src/bac_metadata/pp/test_google_auth.py` to verify auth

**External APIs (no auth required):**
- ENA Portal API: `https://www.ebi.ac.uk/ena/portal/api/search`
- NCBI Datasets API: `https://api.ncbi.nlm.nih.gov/datasets/v1`

## Validation & Debugging

No test framework. Debug/validation scripts in `src/bac_metadata/pp/`:
- `test_google_auth.py` — Verify Google OAuth
- `test_city_geocoding.py` — Test reverse geocoding
- `debug_kleborate_columns.py`, `debug_kleborate_qc.py`, `debug_klebnet.py` — Validate QC data

Exploratory analysis in `src/bac_metadata/notebooks/` (11 notebooks, prefixed 00–11).
