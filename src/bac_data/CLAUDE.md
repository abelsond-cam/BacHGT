# CLAUDE.md — bac_data

The `bac_data` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for the
monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

`bac_data` acquires and stages the genome data the rest of BacHGT analyses:
it discovers assemblies and sequencing runs in public repositories (ENA Portal
API, NCBI Datasets v2), audits and integrates cohorts, downloads genomes/GFFs,
and maintains data-presence columns on the curated metadata TSV.

## Layout

Flat package — every module is a standalone `uv run python -m bac_data.<name>`
CLI (no `pp/tl/pl` split). `norway_cohort_audit.py` is also a shared helper
module: `norway_tables1_integrate.py`, `related_lr_complete_assembly_audit.py`,
and `download_related_lr_complete_genomes.py` import its NCBI helpers
(`ncbi_headers`, `ncbi_biosample_records`, `_gca_primaries`).

## Modules by stage

**Discovery & audit** — `find_sample_assemblies.py` (ENA assemblies for
BioSamples), `gca_to_gcf_lookup.py` (pair GCA↔GCF + assembly metadata),
`norway_cohort_audit.py` (locate the Norway KPSC completes in public repos),
`related_lr_complete_assembly_audit.py` (Complete-Genome GCAs for related-LR
samples), `find_related_run_accessions.py` (long-read + RefSeq SR runs),
`resolve_sr_partner_biosamples.py` (RefSeq SR runs → INSDC BioSamples).

**Integration & cleanup** — `norway_tables1_integrate.py` (Norway paper Table
S1 → metadata), `fix_related_lr_accession.py`, `clean_find_long_reads_appended.py`.

**Download & staging** — `download_related_lr_complete_genomes.py` (GCA/GCF
genome+GFF via NCBI Datasets), `download_bakrep_gbff_files.py`,
`stage_sr_for_related_lr.py` (symlink SR originals into staging).

**Metadata flags** — `add_bakta_gbff_downloaded_flag.py` (`bakta_gbff_downloaded`
column from file presence), `update_biosample_accessions.py` (RefSeq/NCTC
assembly accessions → BioSample accessions).

Two of these run on Slurm: `src/bac_data/slurm_scripts/norway_tables1_integrate.sh` and
`src/bac_data/slurm_scripts/related_lr_complete_assembly_audit.sh`.
