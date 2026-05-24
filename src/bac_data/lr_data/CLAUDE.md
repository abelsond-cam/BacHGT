# CLAUDE.md — bac_data.lr_data

Long-read assembly (**LRA**) sub-pipeline of `bac_data`. Splits cleanly out of
the top-level package because it's a single coherent flow: discover candidate
long-read assemblies for every short-read sample we have, audit and download
them, score them uniformly with CheckM2, then pick the accepted "LRA" set that
will overlay the SR rows in `metadata_v2`.

See `src/bac_data/CLAUDE.md` for the parent subpackage and
`BacHGT/CLAUDE.md` for the monorepo.

## What an "LRA" is

The **LRA cohort** = every assembly we want to use as the long-read overlay for
an SR sample. Two sources:

- **LR-GCAs** — GenBank long-read assemblies we discover via the
  `related_lr_*` chain (Norway KPSC Table S1 + the rest).
- **is_refseq** — RefSeq assemblies already flagged in the curated metadata.

Together ~6,200 assemblies. CheckM2 scores them uniformly so the per-assembly
QC is comparable, and `build_lra_set.py` (Phase E) emits the accepted subset.

## Modules by stage

**Discovery & audit** — `find_sample_assemblies.py` (ENA assemblies for
BioSamples), `gca_to_gcf_lookup.py` (pair GCA↔GCF + assembly metadata; has a
built-in convergence-retry loop), `norway_cohort_audit.py` (locate the Norway
KPSC completes in public repos; shared helper module),
`related_lr_complete_assembly_audit.py` (Complete-Genome GCAs for related-LR
samples), `find_related_run_accessions.py` (long-read + RefSeq SR runs),
`resolve_sr_partner_biosamples.py` (RefSeq SR runs → INSDC BioSamples).

`norway_tables1_integrate.py`, `related_lr_complete_assembly_audit.py`, and
`download_related_lr_complete_genomes.py` all import NCBI helpers
(`ncbi_headers`, `ncbi_biosample_records`, `_gca_primaries`) from
`norway_cohort_audit`.

**Integration & cleanup** — `norway_tables1_integrate.py` (Norway paper Table
S1 → metadata), `fix_related_lr_accession.py`,
`clean_find_long_reads_appended.py`.

**Download & staging** — `download_related_lr_complete_genomes.py` (GCA/GCF
genome+GFF via NCBI Datasets), `stage_sr_for_related_lr.py` (symlink SR
originals into staging).

**CheckM2 (HPC)** — lives in sibling [`../checkm2/`](../checkm2/) (lifted
out of `lr_data/` because the env + Slurm wrapper are cohort-agnostic). The
LRA cohort is its first caller: `prep_checkm2_inputs.py` there symlinks all
~6,084 FASTAs (LR-GCAs + is_refseq) into one working dir;
`slurm_scripts/run_checkm2.sh` submits the batch on icelake-himem.

**Quality cutoffs (notebook)** —
[`notebooks/lra_quality_cutoffs.ipynb`](notebooks/lra_quality_cutoffs.ipynb)
+ caches at [`notebooks/_data/`](notebooks/_data/). Picks LRA inclusion
thresholds from RefSeq's empirical distribution.

## Slurm scripts

At [`slurm_scripts/`](slurm_scripts/):

- `norway_tables1_integrate.sh` — Table S1 integration + GenBank download
  (icelake, 32 GB).
- `related_lr_complete_assembly_audit.sh` — Complete-Genome audit
  (icelake, 8 GB; pure-network).

The CheckM2 batch lives in the sibling subpackage:
[`../checkm2/slurm_scripts/run_checkm2.sh`](../checkm2/slurm_scripts/run_checkm2.sh)
(icelake-himem, 64 CPU, 64 GB, 4 h).

## Running

```bash
# Top-level invocation pattern for every module here:
uv run python -m bac_data.lr_data.<module>

# On HPC:
sbatch src/bac_data/lr_data/slurm_scripts/<script>.sh
```

The CheckM2 pixi env is separate from the shared uv env — see
[`../checkm2/README.md`](../checkm2/README.md) for the one-time install
(`pixi install` + DB download).
