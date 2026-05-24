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
an SR sample. Three sources unioned into one row-per-biological-assembly table
(`lra_discovery.tsv`):

- **LR-GCAs from the audit** — every Complete-Genome GCA/GCF NCBI knows for
  our related-LR run accessions (`related_lr_complete_assembly_audit.py`).
- **Norway KPSC Table S1** — 534 strains resolved to GenBank, of which 270
  have a paired RefSeq GCF (`norway_tables1_integrate.py`).
- **is_refseq metadata** — RefSeq assemblies already flagged in the curated
  metadata; mostly GCFs, ~280 stale-GCAs flagged is_refseq=True without ever
  being promoted to RefSeq (the `stale_refseq` column flags these).

Together ≈5,557 unique biological assemblies. CheckM2 scores them uniformly so
the per-assembly QC is comparable, and `build_lra_set.py` (Phase E) emits the
accepted subset.

## Single source of truth: `lra_discovery.tsv`

At `<RDS>/david/processed/lra_discovery.tsv`. One row per biological assembly.
Built by `build_lra_discovery.py` (pure-local merge of the three sources;
re-runnable in <60 s). CheckM2 results join back onto it via
`annotate_checkm2.py`. The Phase C notebook and Phase E selector both consume
this single file. See module docstrings for the schema.

## The pipeline (B.1 → B.8)

```
  1. add_paths_gff_fna_to_metadata.sh           ← bac_metadata; populates assembly_file
                                                 for is_refseq rows (~3,500 GCFs already
                                                 live under seb/assemblies_2/...)
  2. build_lra_discovery                        ← unions 3 sources → lra_discovery.tsv
  3. discovery_to_download_lists                ← splits download_needed rows by tier
  4. download_lra_missing_{gca,gcf}.sh          ← Slurm; convergence-loop downloader
  5. build_lra_discovery (re-run)               ← refreshes fasta_on_disk; pivots
                                                 scoring_accession to paired GCA when a
                                                 GCF turns out to be NCBI-suppressed
  6. prep_checkm2_inputs                        ← symlinks the scoring FASTAs into one dir
  7. run_checkm2.sh                             ← Slurm; CheckM2 on icelake-himem (~1-2 h)
  8. annotate_checkm2                           ← merges quality_report.tsv back
                                                 onto lra_discovery.tsv
```

Modules 2, 3, 5, 6, 8 run on the login node; 1, 4, 7 are Slurm. Steps 2 + 5
are the same module re-invoked; both are <60 s pure-local.

## Modules by stage

**Upstream discovery & audit** (network-bound; ~2 h each via Slurm) —
`related_lr_complete_assembly_audit.py` (Complete-Genome GCAs/GCFs for
related-LR samples), `norway_tables1_integrate.py` (Norway Table S1 →
metadata + downloads).

**Discovery TSV (the unification step)** — `build_lra_discovery.py` (the
single coherent merge; replaces the lost ad-hoc `related_lr_all_gca.tsv`
filter), `discovery_to_download_lists.py` (split `download_needed=True` rows
into per-tier missing-accession TSVs for the downloader).

**Download** — `download_related_lr_complete_genomes.py` (GCA/GCF
genome+GFF via NCBI Datasets v2; batch-level convergence loop).

**CheckM2 (HPC)** — lives in sibling [`../checkm2/`](../checkm2/) (lifted out
of `lr_data/` because the env + Slurm wrapper are cohort-agnostic).
`prep_checkm2_inputs.py` there reads `lra_discovery.tsv` and symlinks one FASTA
per `scoring_accession` into a single working dir;
`slurm_scripts/run_checkm2.sh` submits the batch on icelake-himem.

**Annotate** — `annotate_checkm2.py` joins CheckM2's `quality_report.tsv`
onto `lra_discovery.tsv` by `scoring_accession`; idempotent (drops + rewrites
`checkm2_*` columns on re-run).

**Quality cutoffs (notebook)** —
[`notebooks/lra_quality_cutoffs.ipynb`](notebooks/lra_quality_cutoffs.ipynb)
+ caches at [`notebooks/_data/`](notebooks/_data/). Picks LRA inclusion
thresholds from the RefSeq empirical distribution in `lra_discovery.tsv`.

**Helper modules (legacy / shared)** — `find_sample_assemblies.py`,
`gca_to_gcf_lookup.py` (pair GCA↔GCF + assembly metadata; has a built-in
convergence-retry loop), `norway_cohort_audit.py` (shared NCBI helpers),
`find_related_run_accessions.py`, `resolve_sr_partner_biosamples.py`,
`fix_related_lr_accession.py`, `clean_find_long_reads_appended.py`,
`stage_sr_for_related_lr.py`.

`norway_tables1_integrate.py`, `related_lr_complete_assembly_audit.py`, and
`download_related_lr_complete_genomes.py` all import NCBI helpers
(`ncbi_headers`, `ncbi_biosample_records`, `_gca_primaries`) from
`norway_cohort_audit`.

## Slurm scripts

At [`slurm_scripts/`](slurm_scripts/):

- `norway_tables1_integrate.sh` — Table S1 integration + GenBank download
  (icelake, 32 GB).
- `related_lr_complete_assembly_audit.sh` — Complete-Genome audit
  (icelake, 8 GB; pure-network).
- `download_related_lr_all_gca.sh` — bulk GCA download against the legacy
  `related_lr_all_gca.tsv` (icelake, 4 CPU, 8 GB; convergence loop).
- `download_lra_missing_gca.sh` + `download_lra_missing_gcf.sh` — Phase B.4
  per-tier download against `lra_download_{gca,gcf}_missing.tsv` produced by
  `discovery_to_download_lists.py`.

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
