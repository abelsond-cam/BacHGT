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
(`lra_discovery.tsv`); the union is what `build_lra_discovery.py` does in <60 s.

CheckM2 scores them uniformly so the per-assembly QC is comparable, and
`build_lra_set.py` (Phase E) emits the accepted subset.

### Source accounting (numbers from the live `lra_discovery.tsv`, 2026-05-24)

| Source                                     | Rows entering | with GCA | with GCF | paired GCA+GCF | GCA-only | GCF-only |
| ------------------------------------------ | ------------- | -------- | -------- | -------------- | -------- | -------- |
| `related_lr_complete_assembly_audit.tsv`   | 2,571         | 2,571    | 1,665    | 1,665          | 906      |        0 |
| `norway_tables1_integration.tsv`           |   534         |   534    |   270    |   270          | 264      |        0 |
| is_refseq=True curated-metadata rows       | 3,911         |   398    | 3,513    |     0          | 398      |    3,513 |

The is_refseq rows are accession-only (Sample column holds either a GCF or a
GCA, never both) — that's why their "paired" count is 0 here. Pairing happens
in the merge step when an is_refseq GCF matches an audit-paired GCF.

### Cross-source overlap (each row counted exactly once)

Each merged row carries `source_audit` / `source_norway` / `source_refseq_metadata`
booleans (OR'd at merge time). The 7-cell Venn over those three:

| Provenance label       | Rows  | Notes                                                         |
| ---------------------- | ----: | ------------------------------------------------------------- |
| `refseq` alone         | 2,522 | RefSeq curated genomes never re-discovered by the audit       |
| `audit` alone          | 1,639 | Audit-only LR-GCAs (no paired GCF, not in is_refseq metadata) |
| `audit+refseq`         |   862 | Audit-paired GCFs that were already in is_refseq metadata     |
| `norway+refseq`        |   457 | Norway-paired strains where the metadata already had the GCF  |
| `audit+norway+refseq`  |    70 | Triple-overlap; rare                                          |
| `norway` alone         |     7 | Norway resolutions not present in audit or refseq metadata    |
| **Total**              | **5,557** |                                                           |

Per-source totals reconcile to inputs (multi-source rows counted in each):
- source_audit = 1,639 + 862 + 70 = **2,571** ✓
- source_norway = 7 + 457 + 70 = **534** ✓
- source_refseq_metadata = 2,522 + 862 + 457 + 70 = **3,911** ✓

Naive sum (2,571 + 534 + 3,911) = **7,016**.
Merged unique = **5,557**.
Dedups removed = 7,016 − 5,557 = **1,459**, which is exactly:
- 862 (audit+refseq pair-overlaps, each counted twice in the naive sum)
- 457 (norway+refseq pair-overlaps)
- 70 × 2 = 140 (audit+norway+refseq triple-overlaps, counted three times)

= 862 + 457 + 140 = **1,459** ✓

### Final GCA/GCF accounting (per biological assembly)

| Category                             | Rows   |
| ------------------------------------ | -----: |
| with GCF (CheckM2 prefers the GCF)   |  4,365 |
| with GCA-only (no paired RefSeq)     |  1,192 |
| paired (both GCA AND GCF)            |  1,865 |
| GCF-only (no paired GenBank GCA)     |  2,500 |
| **Total unique biological assemblies** | **5,557** |

(`paired` + `GCF-only` = with GCF = 4,365; `paired` + `GCA-only` = with GCA = 3,057.)

### `stale_refseq` — what the flag really means

281 rows have `stale_refseq=True` (is_refseq=True but no GCF on this row).
Breakdown:

| Provenance of stale_refseq row | Count | Reading                                                 |
| ------------------------------ | ----: | ------------------------------------------------------- |
| solely refseq metadata         |    22 | The "real" stale flags — no NCBI corroboration anywhere |
| also in norway (no audit)      |   259 | Norway-resolved GCA-only strains that metadata had already flagged is_refseq |
| also in audit                  |     0 | Audit excludes is_refseq inputs by design, so 0         |

So the bulk of the 281 isn't broken metadata — it's GenBank-only Norway strains
that were tagged is_refseq=True without actually existing in RefSeq. The 22
solely-refseq rows are the genuinely-orphaned flags.

## Single source of truth: `lra_discovery.tsv`

At `<RDS>/david/processed/complete_vs_sr_genomes/lr_discovery/lra_discovery.tsv`. One row per biological assembly.
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
`stage_sr_for_related_lr.py` (stages the SR side into
`staging_for_tf/{assemblies,gff}`), `stage_lra_extras_for_tf.py` (companion that
stages the LR assemblies — every v2 `lra_assembly_file` + its `related_lr` GFF —
into the separate `staging_for_tf/lra/{assemblies,gff}` section for the next
transfer batch).

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
