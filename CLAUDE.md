# CLAUDE.md — BacHGT

Guidance for Claude Code in the **BacHGT monorepo**. Global guidance — working
preferences, the wider ecosystem, environment policy, HPC connection + storage
map — is in `~/.claude/CLAUDE.md`. Each `src/bac_*` subpackage has its own
`CLAUDE.md` with subpackage-specific detail.

## What BacHGT is

The Klebsiella-genomics monorepo: pangenome / gene-presence-absence (GPA) /
mobile-element analysis of the *Klebsiella pneumoniae* species complex. One git
repo, one shared uv environment, six subpackages under `src/`:

| Subpackage | Purpose | Detail |
|---|---|---|
| `bac_panaroo` | Panaroo pangenome analysis — defines "bacotypes" from GPA (the core) | `src/bac_panaroo/CLAUDE.md` |
| `bac_ariba` | ARIBA virulence/AMR profiling from short reads | `src/bac_ariba/CLAUDE.md` |
| `bac_metadata` | ENA metadata curation → the curated metadata TSV | `src/bac_metadata/CLAUDE.md` |
| `bac_data` | Data acquisition — discover, audit, download assemblies/runs | `src/bac_data/CLAUDE.md` |
| `bac_isescan` | ISEScan IS-element analysis — copy number, gene context, hotspots | `src/bac_isescan/CLAUDE.md` |
| `bac_cohort` | Complete-genome vs short-read cohort feature comparison | `src/bac_cohort/CLAUDE.md` |

## Sibling repos

Separate checkouts beside BacHGT (`~/developer/` locally, `~/workspace/` on HPC) —
**not** part of this monorepo:

- `panaroo` — fork of [gtonkinhill/panaroo](https://github.com/gtonkinhill/panaroo).
  `bac_panaroo` loads its `scripts/convert_bakta_to_prokka_gff.py` by file path
  (the loader in `src/bac_panaroo/pp/panaroo_run_strain.py`); the fork must be
  cloned as a sibling of this repo.
- `pangenome_merge` — fork of an external tool that merges Panaroo runs across
  batches. Run standalone; no code coupling to BacHGT.
- `BacMGEfinder` — Snakemake workflow for mobile-element (MGEFinder) analysis.

## Environment

One shared uv environment for the whole monorepo:

```bash
uv sync                                                              # build / refresh the env
uv run python src/bac_panaroo/tl/gpa_distances_single_run.py --help  # always use uv run
uv run --group test pytest tests/ src/bac_ariba/tests/               # tests
uvx ruff check src/                                                  # lint (ruff is not a project dep)
```

Subpackages that need non-Python tool binaries keep their own `pixi`/`micromamba`
environment — e.g. `bac_ariba` runs ARIBA from an apptainer container (see
`src/bac_ariba/CLAUDE.md`).

Production scripts run on Slurm: edit the knobs at the top of the relevant
`slurm_scripts/*.sh`, then `sbatch`.

## HPC

See `~/.claude/CLAUDE.md` for the HPC connection and the four storage roots.
Code at `/home/dca36/workspace/BacHGT`. Hard-coded `/home/dca36/rds/...` data
paths across `slurm_scripts/*.sh` and `src/bac_*/` are deliberately not
centralised; their literal paths use the vocabulary in
`~/.claude/hpc_storage_overview.md`.

## Code style

- Line length 120; numpy docstrings (enforced by `ruff pydocstyle`).
- Ruff: B, BLE, C4, D, E, F, I, RUF100, TID, UP, W (see `pyproject.toml` for ignores).
- Python 3.10+.
