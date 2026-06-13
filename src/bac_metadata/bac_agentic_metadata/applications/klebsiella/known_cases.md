# Known hard cases (Klebsiella) — explicit training/edge cases

Cases worth holding explicitly so the engine (and its evaluators) are tested against them rather
than silently mis-handling them. Surfaced by Stage 1; relevant to the paper-finding/grading
stages that follow.

## Umbrella project accessions (one accession, many substudies)

Some ENA project accessions are **umbrellas** that aggregate many distinct substudies, so a
single "best paper" cannot describe the whole accession — the paper-finding stage must recognise
the umbrella and split it into its child cohorts.

- **`PRJEB74192` — "One Health Norway"** (the canonical training case). 9 distinct child studies
  (`secondary_study_accession`): NORKAB, the Norwegian *K. pneumoniae* study, a GI-carriage
  cohort, poultry, pigs, etc. ~3,261 *Klebsiella* samples; we hold ~all of them (coverage ≈ 1.0),
  but they span unrelated cohorts.

Stage 1 flags these deterministically: `engine/ena_sizing.py` sets `umbrella_suspected` when the
project has `>= UMBRELLA_MIN_CHILD_STUDIES` (3) distinct child studies. See the
`umbrella_suspected` / `n_child_studies` columns in `data/stage1_sizing.tsv` and the umbrella
section of `data/stage1_validation_report.md`.

## ENA sample-vs-read_run linkage

`PRJEB74192` also exposed that ENA's `result=sample&query=study_accession=X` is unreliable: it
returns **0** samples for that study, while `result=read_run` returns 3,831 (3,261 distinct
samples). Stage 1 therefore sizes every project from `read_run` deduplicated to sample level.

## ENA under-labels Klebsiella in broad projects (taxon sizing is a lower bound)

Some accessions are **broad *Enterobacteriaceae* deposits** where submitters left the species
unset or generic, so `scientific_name`-based counting under-reports Klebsiella. The curation
(human + Kleborate) is *more* complete than ENA's `scientific_name`. Examples: `PRJEB32655`
(malawi_ceftriaxone, ENA total 1485 but only 238 labelled Klebsiella; curated 1485),
`PRJEB22252` (baby_biomes_uk, 805 total / 237 labelled). Hence `ena_klebsiella_samples` is a
**lower bound** and `ena_total_samples` an **upper bound**; the validation classifies these as
`ena_underlabels_klebsiella` rather than errors. ~22 rows in the split fall here.

## Assembly-only / zero-portal-record accessions

A few curated accessions return **no** portal-visible reads or samples (e.g. `PRJNA565795`,
`melb_superbugs`) — likely NCBI-only BioProjects or data registered under other accessions. They
appear as "holding exceeds project taxon count" anomalies in the validation report and need
manual attention rather than automated sizing.
