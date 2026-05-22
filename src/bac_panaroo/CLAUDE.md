# CLAUDE.md — bac_panaroo

The `bac_panaroo` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for
the monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

`bac_panaroo` uses [Panaroo](https://github.com/gtonkinhill/panaroo) to define
"bacotypes" by analysing gene presence/absence (GPA) in bacterial sublineages,
clonal groups, and clusters of the *Klebsiella pneumoniae* species complex.
Three task areas: preprocess metadata → run Panaroo on HPC → analyse GPA
distances to reference genomes.

## Package layout

scanpy-style modules under `src/bac_panaroo/`:

| Module | Purpose |
|---|---|
| `pp/` | Preprocessing — build the reference bucket and Panaroo-sized input batches |
| `tl/` | Tools/analysis — Jaccard distances, ref-genome scoring, clustering, pangenome stats |
| `pl/` | Plotting — GPA matrices, epidemic-vs-mixed, granularity lollipops |

## Panaroo fork dependency

`pp/panaroo_run_strain.py` loads the Bakta→Prokka `convert` function from the
`panaroo` fork's `scripts/convert_bakta_to_prokka_gff.py` **by file path** — the
fork must be checked out as a sibling of the BacHGT repo (`~/developer/panaroo`
locally, `~/workspace/panaroo` on HPC). See `_load_convert_from_panaroo_fork()`.

## Three-task workflow

### Task 1 — Preprocessing

Metadata preprocessing — scanning assembly/GFF dirs, resolving per-sample paths,
GFF-feature QC, PopPUNK clusters, slimming the curated TSV — is handled by the
`bac_metadata` subpackage (see `src/bac_metadata/CLAUDE.md`); its curated
metadata TSV is the single source of truth for everything below. What remains in
`bac_panaroo/pp/` is Panaroo-input prep: `build_reference_bucket.py` and
`panaroo_metadata_batching.py` (see Task 2).

### Task 2 — Run Panaroo

Three modes sharing `pp/panaroo_run_strain.py`:

- **2a** single CG: `sbatch slurm_scripts/panaroo_run_strain.sh --clonal-group CG11`
- **2b** whole dataset as a Slurm array: `pp/panaroo_metadata_batching.py` →
  `panaroo_run_strain_metadata_array.sh`
- **2c** arbitrary sample list: same script with `--sample-metadata-file`

Each batch TSV carries a curated **reference bucket** (mgh78578 + Norway-completes
+ HS11286 by default, from `<DATA_ROOT>/final/reference_bucket.tsv`) so every run
sees a fixed reference pool — that is what makes level `e` meaningful in Task 3e.
`--n 10` caps sample count for smoke-tests.

### Task 3 — Analyse GPA & distances

- **3a–c** distance analysis (Jaccard) — `tl/gpa_distances_single_group.py` →
  `..._single_run.py` → `..._batch_runs.py` (narrowest → broadest). Tunables at the
  top of the `.sh`: `MIN_GROUP_SIZE`, `REFERENCE_TOP_N`, `GPA_FILTER_CUTOFF`,
  `CORE_SHELL_CUTOFF`, `SHELL_CLOUD_CUTOFF`, `WORKERS`.
- **3d** combine — `tl/gpa_distances_combined.py` concatenates per-run detail TSVs;
  optional epidemic-vs-mixed comparison.
- **3e** granularity — `tl/gpa_reference_granularity.py` (+ `pl/granularity_lollipop.py`)
  measures ref-assignment improvement across six levels (`f` → `e` → `d` → `c` →
  `b` → `a`) per strain. Self-contained: walks Panaroo run dirs, hierarchically
  splits `Sublineage` → `Clonal group` → `K_locus`, computes levels via a single
  BLAS SGEMM. Level definitions, row types, and output schema:
  [`docs/panaroo_run_inventory.md`](docs/panaroo_run_inventory.md). Submit via
  `sbatch slurm_scripts/gpa_reference_granularity.sh` (fast enough for the login node).
