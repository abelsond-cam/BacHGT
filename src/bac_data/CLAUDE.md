# CLAUDE.md — bac_data

The `bac_data` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for the
monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

`bac_data` acquires and stages the genome data the rest of BacHGT analyses:
it discovers assemblies and sequencing runs in public repositories (ENA Portal
API, NCBI Datasets v2), audits and integrates cohorts, downloads genomes/GFFs,
and maintains data-presence columns on the curated metadata TSV.

## Layout

Flat package (no `pp/tl/pl` split). Every module is a standalone
`uv run python -m bac_data.<name>` CLI; no second environment for the modules
that live at this top level. Two cohesive sub-packages branch off:

- [`lr_data/`](lr_data/) — long-read sub-pipeline (Norway integration,
  `related_lr_*` audit/download chain, LRA selector, `metadata_v2`). See
  [`lr_data/CLAUDE.md`](lr_data/CLAUDE.md).
- [`checkm2/`](checkm2/) — dedicated `pixi` env + Slurm wrapper for
  CheckM2-scoring any assembly cohort uniformly (currently called by the
  LRA cohort; cohort-agnostic by design). See
  [`checkm2/README.md`](checkm2/README.md).

The downstream **genome-annotation** step (batch-running Kleborate + ISEScan
over the staged genome sets) lives in `bac_isescan` — see
`src/bac_isescan/CLAUDE.md`.

## Modules at this top level

Generic / non-LR data acquisition that stays out of `lr_data/`:

| Module | Purpose |
|---|---|
| `update_biosample_accessions.py` | Map assembly accessions (RefSeq/NCTC) → INSDC BioSample accessions on the curated metadata. |
| `add_bakta_gbff_downloaded_flag.py` | Sets the `bakta_gbff_downloaded` column from file presence. |
| `download_bakrep_gbff_files.py` | Pulls per-sample Bakta `.gbff` annotations from BakRep. |

Slurm + helper scripts at [`slurm_scripts/`](slurm_scripts/):

- `download_bakrep.sh`, `collect_bakrep_samples.py` — BakRep bulk download + collect.
- `download_ncbi_datasets.sh`, `collect_ncbi_datasets_samples.py` — NCBI Datasets bulk download + collect.

`sr_for_existing_refseq_review.csv` is a one-off review artefact (kept for
reference; not pipeline input).

## Long-read sub-pipeline → [`lr_data/`](lr_data/)

Everything related to discovering, auditing, downloading and qualifying
long-read assemblies (LR-GCAs + is_refseq RefSeq genomes) that form the LRA
("long-read assembly") cohort moved into [`lr_data/`](lr_data/) in May 2026.
That includes the Norway KPSC integration, the `related_lr_*` audit/download
chain, CheckM2-on-HPC, and the upcoming LRA-selector / `metadata_v2` builders.
See [`lr_data/CLAUDE.md`](lr_data/CLAUDE.md) for module-by-module detail.
