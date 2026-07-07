# CLAUDE.md — BacHGT

Guidance for Claude Code in the **BacHGT monorepo**. Global guidance — working
preferences, the wider ecosystem, environment policy, HPC connection + storage
map — is in `~/.claude/CLAUDE.md`. Each `src/bac_*` subpackage has its own
`CLAUDE.md` with subpackage-specific detail.

> **Plans.** The living plan + tracker for this repo is [`ToDo.md`](ToDo.md) — read it for current workstreams and their status. (The earlier `~/.claude/PROGRAM_PLAN_2026-05-30.md` is superseded.)

## What BacHGT is

The Klebsiella-genomics monorepo: pangenome / gene-presence-absence (GPA) /
mobile-element analysis of the *Klebsiella pneumoniae* species complex. One git
repo, one shared uv environment, seven subpackages under `src/`:

| Subpackage | Purpose | Detail |
|---|---|---|
| `bac_panaroo` | Panaroo pangenome analysis — defines "bacotypes" from GPA (the core) | `src/bac_panaroo/CLAUDE.md` |
| `bac_ariba` | ARIBA virulence/AMR profiling from short reads | `src/bac_ariba/CLAUDE.md` |
| `bac_metadata` | ENA metadata curation → the curated metadata TSV | `src/bac_metadata/CLAUDE.md` |
| `bac_data` | Data acquisition — discover, audit, download assemblies/runs | `src/bac_data/CLAUDE.md` |
| `bac_isescan` | ISEScan IS-element analysis — copy number, gene context, hotspots | `src/bac_isescan/CLAUDE.md` |
| `bac_complete_genomes` | Complete-genome vs short-read cohort feature comparison (cross-section per-CG + paired SR-vs-LRA) | `src/bac_complete_genomes/CLAUDE.md` |
| `bac_kleborate` | Vendored Kleborate reference data (virulence + AMR FASTAs) — consumed by `bac_ariba` and `bac_panaroo` | `src/bac_kleborate/CLAUDE.md` |

## Metadata

The authoritative description of **`metadata_v2`** (cohort definition, row keying, column groups, flag definitions, source provenance, rebuild pipeline) lives at
[`src/bac_metadata/METADATA_v2_README.md`](src/bac_metadata/METADATA_v2_README.md). Read it before writing code that consumes the table.

## Sibling repos

Separate checkouts beside BacHGT (`~/developer/` locally, `~/workspace/` on HPC) —
**not** part of this monorepo:

- `panaroo` — fork of [gtonkinhill/panaroo](https://github.com/gtonkinhill/panaroo).
  `bac_panaroo` loads its `scripts/convert_bakta_to_prokka_gff.py` by file path
  (the loader in `src/bac_panaroo/run_panaroo/panaroo_run_strain.py`); the fork must be
  cloned as a sibling of this repo.
- `pangenome_merge` — fork of an external tool that merges Panaroo runs across
  batches. Run standalone; no code coupling to BacHGT.
- `BacMGEfinder` — Snakemake workflow for mobile-element (MGEFinder) analysis.

## Environment

One shared uv environment for the whole monorepo:

```bash
uv sync                                                              # build / refresh the env
uv run python src/bac_panaroo/gpa_analysis/gpa_distances_single_run.py --help  # always use uv run
uv run --group test pytest tests/ src/bac_ariba/tests/               # tests
uvx ruff check src/                                                  # lint (ruff is not a project dep)
```

Subpackages that need non-Python tool binaries keep their own `pixi`/`micromamba`
environment — e.g. `bac_ariba` runs ARIBA from an apptainer container (see
`src/bac_ariba/CLAUDE.md`).

Production scripts run on Slurm: each subpackage keeps its own
`src/bac_*/slurm_scripts/` — edit the knobs at the top of the relevant
`*.sh`, then `sbatch`.

## HPC

**Cluster guidance lives at the `~/.claude` level** — the user says which cluster each session:
- [`~/.claude/CLAUDE.md`](~/.claude/CLAUDE.md) → **"Working on HPC clusters"** — the agnostic rules
  (storage discipline, no-`du`, logs/caches/envs off `$HOME`, code-via-git-not-scp, generous `--time`).
- [`~/.claude/cluster_uohpc.md`](~/.claude/cluster_uohpc.md) (CSD3 — most BacHGT data lives here on
  RDS `project_k`; storage vocabulary in [`~/.claude/hpc_storage_overview.md`](~/.claude/hpc_storage_overview.md))
  · [`~/.claude/cluster_isambard.md`](~/.claude/cluster_isambard.md) (BacHGT is also checked out on
  Isambard `$HOME`).

> **CSD3 (UoHPC) is down since 27 Jun 2026** — its RDS data (most of BacHGT's) is stranded.

Hard-coded `/home/dca36/rds/...` data paths across `src/bac_*/slurm_scripts/*.sh` and `src/bac_*/`
are CSD3/`project_k` paths, deliberately not centralised; resolve them via the UoHPC storage doc.

## Code style

- Line length 120; numpy docstrings (enforced by `ruff pydocstyle`).
- Ruff: B, BLE, C4, D, E, F, I, RUF100, TID, UP, W (see `pyproject.toml` for ignores).
- Python 3.10+.
