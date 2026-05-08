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

## HPC connection

- Host: `login.hpc.cam.ac.uk` (CSD3, user `dca36`).
- An 8-hour SSH ControlMaster multiplex is configured in `~/.ssh/config`, so any `ssh login.hpc.cam.ac.uk "<cmd>"` reuses the existing socket — no fresh login per call. If a command hangs, the master may have expired; opening any interactive `ssh login.hpc.cam.ac.uk` reseeds it.
- Code lives at `/home/dca36/workspace/Bacotype` (sibling projects under `/home/dca36/workspace/`). Data lives under `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david` (the `DATA_ROOT` baked into `pp/panaroo_run_strain.py`).
- The Panaroo fork (https://github.com/abelsond-cam/panaroo) lives at `/home/dca36/workspace/panaroo` as a sibling of `Bacotype`; `pp/panaroo_run_strain.py` loads `convert_bakta_to_prokka_gff.py` from it via file-path import (see `Convert_Bakta_to_Prokka.MD`).
- Sync local changes with `rsync -av --exclude .venv --exclude .git src/ login.hpc.cam.ac.uk:/home/dca36/workspace/Bacotype/src/` (or target individual files).

## Package layout

The package follows a [scanpy](https://scanpy.readthedocs.io)-style module convention:

| Module | Purpose |
|--------|---------|
| `src/bacotype/pp/` | Preprocessing: resolve assembly/GFF paths, QC feature counts, build metadata TSV, prepare Panaroo inputs |
| `src/bacotype/tl/` | Tools/analysis: Jaccard distances, reference-genome scoring, clustering metrics, pangenome stats; `gpa_reference_granularity.py` for granularity analysis |
| `src/bacotype/pl/` | Plotting: GPA matrix figures, epidemic vs mixed visualisations, `granularity_lollipop.py` for reference-level improvement plots |
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

Every batch TSV produced by `pp/panaroo_metadata_batching.py` carries a curated **reference bucket** (default: mgh78578 + Norway-completes + HS11286), loaded from `<DATA_ROOT>/final/reference_bucket.tsv` (built by `pp/build_reference_bucket.py`). This is what makes level `e` meaningful in Task 3e: every Panaroo run sees the same fixed pool of references, so we can ask "for this species, which single ref gives the best mean shared-genes across all the species's samples?". If the bucket TSV is missing, the script falls back to `is_mgh78578` alone (matches pre-bucket behaviour). Bucket members carry an `is_reference_bucket=True` column in every output batch TSV.

### Task 3 — Analyse GPA & distances

#### Distance analysis (per-run Jaccard computations)

Three entrypoints, narrowest to broadest:
- **3a** `tl/gpa_distances_single_group.py` — one sample set; usually called by 3b, not directly
- **3b** `tl/gpa_distances_single_run.py` — whole set + stratified subsets for one Panaroo run → detail TSV per run
- **3c** `tl/gpa_distances_batch_runs.py` — walks all Panaroo run directories in parallel → compiled summary TSV

Key tunables (set at top of `.sh` or passed as CLI flags): `MIN_GROUP_SIZE` (default 250), `REFERENCE_TOP_N` (default 10), `GPA_FILTER_CUTOFF`, `CORE_SHELL_CUTOFF`, `SHELL_CLOUD_CUTOFF`, `WORKERS`.

#### Post-distance analysis

- **3d** `tl/gpa_distances_combined.py` — load + concatenate all per-run detail TSVs into one combined table; optionally run epidemic-vs-mixed comparison per metric
- **3e** `tl/gpa_reference_granularity.py` — compute reference-genome assignment granularity improvement across 6 plotted levels (`f` → `e` → `d` → `c` → `b` → `a`) per strain; generates run inventory markdown, `granularity_table.tsv`, and a suite of lollipop plots (via `pl/granularity_lollipop.py`).
  - **Self-contained**: walks Panaroo run dirs directly (`tl/panaroo_groups.find_panaroo_runs`), splits each run hierarchically by `Sublineage` → `Clonal group` → `K_locus` (`tl/panaroo_groups.hierarchical_split`), and computes every level from the run's `gene_presence_absence.Rtab` via a single BLAS SGEMM (`X_refseq @ X_query.T`). No dependence on the heavy `gpa_distances_batch_runs.sh` job. For KP sublineage runs the SL split is degenerate (one major SL, no `other_SL`) so kp_epidemic / kp_epidemic_sl rows are the same as if no SL split happened; for `kp_rare` and `kp_species` runs the SL split is what makes level d (and c / b) meaningful.
  - **Levels** (mean shared genes between query samples and chosen RefSeq):
    - `f` — best mgh78578 vs run's KP samples ("Ref mgh78578")
    - `e` — single best reference from the reference bucket, **chosen per query species via cross-run aggregation** ("Best RefSeq in Subspecies"). For each species the granularity script computes the n_query-weighted mean of each bucket reference's shared-gene count across all that species's Panaroo runs, then picks the ref with the highest mean → `best_e_ref[species]`. That single ref's per-row mean becomes `shared_genes_e`. The picks are persisted to `best_e_ref_per_species.tsv`. Falls back to level `f` with `fallback_e=True` only when no bucket ref is reachable for a species (defensive; should not fire in practice).
    - `d` — best single RefSeq across all RefSeqs in the Panaroo run ("Best RefSeq in SL")
    - `c` — best single RefSeq scoped to one CG ("Best RefSeq in CG"). For SL/run summary rows this is the n_samples-weighted mean across **all** CG-level subgroups in the run including the `other` bucket — so the SL row is not biased toward big CGs.
    - `b` — best single RefSeq scoped to one CG/K-locus subgroup ("Best RefSeq in CG / K-locus"). Per-CG rows take a weighted mean across their own K-locus subgroups (incl. `other`); SL/run rows take a weighted mean across each CG's `b` value plus the run-level `other` bucket.
    - `a` — per-sample max-shared-genes RefSeq ("Best RefSeq Per-Sample")
  - **Row types** (`row_type` column): `kp_epidemic` (per major CG in a KP sublineage run, `n ≥ min_group_size`), `kp_epidemic_sl` (one per KP sublineage run, weighted mean over all CG-level subgroups incl. `other`), `kp_rare` (one per `kp_rare_sublineage_batch_*` run, same SL-style aggregation), `kp_species` (one per `species_*` run, same).
  - **Modes**: `inventory` (run metadata summary; still uses combined detail TSVs from batch_runs), `granularity` (full level analysis; standalone), `both` (default).
  - `--min-group-size` (default 50) is now the **only** CG-size knob — both for the kp_epidemic CG cutoff and for the recursive K-locus split inside each major CG. The previous `--min-samples-per-cg` flag is gone.
  - **Outputs** (under `<DATA_ROOT>/processed/pangenome_analysis/granularity/`):
    - `granularity_table.tsv` (columns `shared_genes_f/_e/_d/_c/_b/_a`, `fallback_e/_c/_b`, gains `gain_f_to_e/_e_to_d/_d_to_c/_c_to_b/_b_to_a` + pcts), `granularity_summary.tsv`, `run_inventory.md`, `granularity_notes.log`
    - `plots_png/` and `plots_pdf/` subfolders containing the SL-level lollipop (base + 4 highlight variants: species / epidemic SL / epidemic SL with d→c gain > 20 genes / rare batches) plus 5 `granularity_gain_histogram_*` files (one per consecutive transition).
  - Submit via `sbatch slurm_scripts/gpa_reference_granularity.sh` — fast enough to run on the login node directly (`MIN_GROUP_SIZE` knob at the top of the script).

## Code style

- Line length: 120 characters
- Docstrings: NumPy convention (enforced by ruff `pydocstyle`)
- Ruff linting rules: B, BLE, C4, D, E, F, I, RUF100, TID, UP, W (see `pyproject.toml` for ignores)
- Python 3.10–3.14 supported