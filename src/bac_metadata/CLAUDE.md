# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A metadata curation and processing pipeline for Klebsiella bacterial genomic data. Ingests metadata from the European Nucleotide Archive (ENA), integrates quality control data (Kleborate, bakrep, LINcode), and produces cleaned, categorized metadata TSVs for downstream analysis.

## Package Manager

This project uses **uv**. Run scripts with `uv run <script>` or activate the environment with `uv sync` first.

```bash
uv sync                          # Install dependencies
uv run Klebsiella/pp/<script>.py # Run a script
```

## Pipeline Execution Order

The three main scripts must be run in sequence:

**Step 1 — Collate ENA metadata:**
```bash
uv run Klebsiella/pp/metadata_collation.py \
  --metadata-file1 <ENA_TSV_1> \
  --metadata-file2 <ENA_TSV_2> \
  --metadata-file3 <ENA_TSV_3> \
  --ena-project-dir <DIR_WITH_READY_TO_MERGE_FILES>
```
Output: `intermediate_collated_metadata_wo_qc_or_kleborate.tsv`

**Step 2 — Integrate QC data:**
```bash
uv run Klebsiella/pp/qc_add_metadata.py \
  --input-file <COLLATED_METADATA> \
  --qc-excel-path <QC_EXCEL> \
  --output-dir <OUTPUT_DIR>
```
Output: `qc_final_with_metadata.tsv`

**Step 3 — Curate metadata fields:**
```bash
uv run Klebsiella/pp/metadata_curation.py \
  --metadata-dir <METADATA_DIR> \
  --metadata-file qc_final_with_metadata.tsv \
  --output-file metadata_final_curated_all_samples_and_columns.tsv \
  --output-file-slimmed metadata_final_curated_slimmed.tsv
```
Output: two TSVs + `parsed_metadata.log`

**Optional — Find long-read sequences:**
```bash
uv run Klebsiella/pp/find_long_reads.py [--dry-run] [--limit N]
```
Queries ENA Portal API and NCBI Datasets API for ONT/PacBio runs.

**Optional — Generate analysis plots:**
```bash
uv run Klebsiella/pp/metadata_analysis.py [--metadata-file FILE]
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

### Key Modules (`Klebsiella/pp/`)

- **`metadata_collation.py`** — Merges ENA TSV exports; applies row-level patches from "ready_to_merge" files (one per ENA project)
- **`qc_add_metadata.py`** — Builds unified QC dataframe from multiple Excel sheets; left-joins metadata onto QC rows; applies KPSC final-list filtering
- **`metadata_curation.py`** — Main curation engine (~286KB). Contains all parsing and categorization logic inline. Reads study-level metadata from a Google Sheet
- **`find_long_reads.py`** — Queries ENA Portal API for long-read runs; resolves RefSeq GCF accessions → BioSample IDs via NCBI Datasets API
- **`metadata_analysis.py`** — Generates species/ST/geography/host/isolation-source plots as PNGs and interactive HTML
- **`date_utils.py`** — Date normalization helpers used by `metadata_curation.py`

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
- Token cached at `Klebsiella/pp/token.json` after first run
- Study-level metadata Google Sheet ID: `1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk`
- Run `uv run Klebsiella/pp/test_google_auth.py` to verify auth

**External APIs (no auth required):**
- ENA Portal API: `https://www.ebi.ac.uk/ena/portal/api/search`
- NCBI Datasets API: `https://api.ncbi.nlm.nih.gov/datasets/v1`

## Validation & Debugging

No test framework. Debug/validation scripts in `Klebsiella/pp/`:
- `test_google_auth.py` — Verify Google OAuth
- `test_city_geocoding.py` — Test reverse geocoding
- `debug_kleborate_columns.py`, `debug_kleborate_qc.py`, `debug_klebnet.py` — Validate QC data

Exploratory analysis in `Klebsiella/notebooks/` (11 notebooks, prefixed 00–11).
