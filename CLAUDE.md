# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project purpose

Bacotype uses [Panaroo](https://github.com/gtonkinhill/panaroo) to define "bacotypes" by analysing gene presence/absence (GPA) in bacterial sublineages, clonal groups, and clusters. Primary organism is the *Klebsiella pneumoniae species complex* (KPSC: K. pneumo (Kp), K. variicola, K. quasipneumoniae, africana, tropica). Three task areas: preprocess metadata → run Panaroo on HPC → analyse GPA distances to reference genomes.

## Project arms & sibling workspaces

Two parallel project arms, both run from `~/workspace/` on the HPC:

- **Klebsiella genomics** — pangenome / GPA / mobile-element analysis of KPSC. Uses this repo + the panaroo fork + Pangenome-merge + Klebsiella_Mobile_Elements.
- **Bacformer-based prediction** — uses [Bacformer](https://github.com/macwiatrak/Bacformer) genome embeddings to predict AMR + isolation source (proxy for virulence); downstream goal is uncovering phenotype-associated genes. Lives in `predict_kleb_by_bacformer`.

Sibling workspaces under `~/workspace/`:

- `Bacotype` (this repo) — pangenome workflow with Panaroo.
- `panaroo` — forked Panaroo (https://github.com/abelsond-cam/panaroo); imported by file path from `pp/panaroo_run_strain.py` (see `Convert_Bakta_to_Prokka.MD`).
- `Pangenome-merge` — forked tool to merge Panaroo runs across batches.
- `Klebsiella_Mobile_Elements` — MGEFinder analysis of mobile genetic elements.
- `predict_kleb_by_bacformer` — Bacformer phenotype prediction.

## Commands

```bash
uv pip install -e .                                                # editable install
uv run python src/bacotype/tl/gpa_distances_single_run.py --help   # always use uv run
hatch test                                                         # full matrix (Python 3.10 + 3.14)
pytest tests/                                                      # quick local run
ruff check src/ && ruff format src/                                # lint + format
hatch run docs:build                                               # docs
```

Production scripts run on Slurm: edit knobs at the top of the relevant `slurm_scripts/*.sh`, then `sbatch`.

## HPC connection

- Host: `login.hpc.cam.ac.uk` (CSD3, user `dca36`). 8-hour SSH ControlMaster configured in `~/.ssh/config`; if a command hangs, reseed by opening an interactive `ssh login.hpc.cam.ac.uk`.
- Code at `/home/dca36/workspace/Bacotype` (siblings under `/home/dca36/workspace/`). Data under `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david` — full storage map (four roots: `project_k`, `personal_rds`, `bacformer_rds`, `cold_storage`) in [`docs/data/hpc_storage_overview.md`](docs/data/hpc_storage_overview.md).
- For code changes prefer `git commit` → `push` → `pull` on HPC over rsync (rsync desyncs the working tree from branch HEAD). Reserve rsync for data files not in git.
- Hard-coded `/home/dca36/rds/...` paths across `slurm_scripts/*.sh` and `src/bacotype/` are deliberately not centralised; their literal paths use the vocabulary in `docs/data/hpc_storage_overview.md`.

## Package layout

scanpy-style modules:

| Module | Purpose |
|--------|---------|
| `src/bacotype/pp/` | Preprocessing — resolve assembly/GFF paths, QC features, build metadata TSV, prep Panaroo inputs |
| `src/bacotype/tl/` | Tools/analysis — Jaccard distances, ref-genome scoring, clustering, pangenome stats |
| `src/bacotype/pl/` | Plotting — GPA matrices, epidemic-vs-mixed, granularity lollipops |

## Three-task workflow

### Task 1 — Preprocessing

Scans assembly/GFF dirs and populates `metadata_final_curated_all_samples_and_columns.tsv` (the single source of truth downstream). Key scripts: `pp/add_paths_gff_fna_to_metadata.py`, `pp/count_gff_features.py`, `pp/merge_gff_feature_counts_into_metadata.py`.

### Task 2 — Run Panaroo

Three modes sharing `pp/panaroo_run_strain.py`:

- **2a** single CG: `sbatch slurm_scripts/panaroo_run_strain.sh --clonal-group CG11`
- **2b** whole dataset as a Slurm array: `pp/panaroo_metadata_batching.py` → `panaroo_run_strain_metadata_array.sh`
- **2c** arbitrary sample list: same script with `--sample-metadata-file`

Each batch TSV carries a curated **reference bucket** (mgh78578 + Norway-completes + HS11286 by default, from `<DATA_ROOT>/final/reference_bucket.tsv`) so every run sees a fixed reference pool — that's what makes level `e` meaningful in Task 3e. `--n 10` caps sample count for smoke-tests.

### Task 3 — Analyse GPA & distances

- **3a–c** distance analysis (Jaccard) — `tl/gpa_distances_single_group.py` → `..._single_run.py` → `..._batch_runs.py` (narrowest → broadest). Tunables at top of `.sh`: `MIN_GROUP_SIZE`, `REFERENCE_TOP_N`, `GPA_FILTER_CUTOFF`, `CORE_SHELL_CUTOFF`, `SHELL_CLOUD_CUTOFF`, `WORKERS`.
- **3d** combine — `tl/gpa_distances_combined.py` concatenates per-run detail TSVs; optional epidemic-vs-mixed comparison.
- **3e** granularity — `tl/gpa_reference_granularity.py` (+ `pl/granularity_lollipop.py`) measures ref-assignment improvement across six levels (`f` → `e` → `d` → `c` → `b` → `a`) per strain. Self-contained: walks Panaroo run dirs, hierarchically splits `Sublineage` → `Clonal group` → `K_locus`, computes levels via a single BLAS SGEMM. **Level definitions, row types, and output schema:** [`docs/data/panaroo_run_inventory.md`](docs/data/panaroo_run_inventory.md). Submit via `sbatch slurm_scripts/gpa_reference_granularity.sh` (fast enough for the login node).

## Code style

- Line length: 120; numpy docstrings (enforced by `ruff pydocstyle`).
- Ruff: B, BLE, C4, D, E, F, I, RUF100, TID, UP, W (see `pyproject.toml` for ignores).
- Python 3.10–3.14 supported.
