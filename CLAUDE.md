# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

Bacotype uses [Panaroo](https://github.com/gtonkinhill/panaroo) to define "bacotypes" by analysing gene presence/absence (GPA) in bacterial sublineages, clonal groups, and clusters. The primary organism is *Klebsiella pneumoniae* subsp. *rhinoscleromatis* (KPSC). The workflow covers three task areas: data preprocessing → running Panaroo on HPC → analysing GPA distances to reference genomes.

## Commands

```bash
# Install (editable)
uv pip install -e .

# Run any script (always use uv run)
uv run python src/bacotype/tl/gpa_distances_single_run.py --help

# Tests
hatch test                          # full matrix (Python 3.10 + 3.14)
pytest tests/                       # quick local run
pytest tests/test_basic.py -v       # single test file

# Lint / format
ruff check src/
ruff format src/

# Docs
hatch run docs:build
hatch run docs:open
```

All production scripts are submitted to a Slurm HPC cluster via `slurm_scripts/*.sh`. Edit the variables at the top of the relevant `.sh` before submitting with `sbatch`.

## Package layout

The package follows a [scanpy](https://scanpy.readthedocs.io)-style module convention:

| Module | Purpose |
|--------|---------|
| `src/bacotype/pp/` | Preprocessing: resolve assembly/GFF paths, QC feature counts, build metadata TSV, prepare Panaroo inputs |
| `src/bacotype/tl/` | Tools/analysis: Jaccard distances, reference-genome scoring, clustering metrics, pangenome stats |
| `src/bacotype/pl/` | Plotting: GPA matrix figures, epidemic vs mixed visualisations |
| `src/bacotype/data_paths.py` | Centralised hard-coded paths to RDS cluster storage — always check this before running on a new machine |

## Three-task workflow

### Task 1 — Preprocessing

Scans assembly/GFF directories and populates `metadata_final_curated_all_samples_and_columns.tsv` (the single source of truth for all later steps).

Key scripts: `pp/add_paths_gff_fna_to_metadata.py`, `pp/count_gff_features.py`, `pp/merge_gff_feature_counts_into_metadata.py`.

### Task 2 — Run Panaroo

Three modes sharing `pp/panaroo_run_strain.py`:
- **2a** single strain / clonal group: `sbatch slurm_scripts/panaroo_run_strain.sh --clonal-group CG11`
- **2b** whole dataset as a Slurm array (per-lineage batches): generate TSVs with `pp/panaroo_metadata_batching.py`, then submit `panaroo_run_strain_metadata_array.sh`
- **2c** arbitrary precomputed sample list: same script with `--sample-metadata-file`

`--n 10` caps sample count for quick smoke-tests.

### Task 3 — Analyse GPA & distances

Three entrypoints, narrowest to broadest:
- **3a** `tl/gpa_distances_single_group.py` — one sample set; usually called by 3b, not directly
- **3b** `tl/gpa_distances_single_run.py` — whole set + stratified subsets for one Panaroo run → detail TSV per run
- **3c** `tl/gpa_distances_batch_runs.py` — walks all Panaroo run directories in parallel → compiled summary TSV

Key tunables (set at top of `.sh` or passed as CLI flags): `MIN_GROUP_SIZE` (default 250), `REFERENCE_TOP_N` (default 10), `GPA_FILTER_CUTOFF`, `CORE_SHELL_CUTOFF`, `SHELL_CLOUD_CUTOFF`, `WORKERS`.

## Code style

- Line length: 120 characters
- Docstrings: NumPy convention (enforced by ruff `pydocstyle`)
- Ruff linting rules: B, BLE, C4, D, E, F, I, RUF100, TID, UP, W (see `pyproject.toml` for ignores)
- Python 3.10–3.14 supported