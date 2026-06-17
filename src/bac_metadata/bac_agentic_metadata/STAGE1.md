# Stage 1 — deterministic ingestion & completeness (notes + calibration)

The first non-LLM layer of the engine. For each project accession it (1) **sizes** the project
from ENA, and (2) measures per-field **completeness** of the four curated clinical fields across
three states. See [`PIPELINE_PLAN.md`](PIPELINE_PLAN.md) §6 and the approved Stage 1 plan.

Everything runs **locally** (no SLURM). ENA sizing needs only the network; the completeness step
reads the existing ATB collated data (no remaking).

## Modules

- `engine/spec.py` — load an application `attributes.yaml` (`taxon_of_interest`, completeness
  fields, normalisers).
- `engine/ena_sizing.py` — ENA project record counts (see calibration below).
- `engine/sources.py` — per-sample tables keyed by `study_accession`. `KlebCollationSource`
  reuses `pp.metadata_collation` to return **base** (raw ATB) and **post-merge** (after the
  per-project `ready_to_merge` patches) states; path args override the defaults for local data.
- `engine/completeness.py` — non-null fraction per field per study, on base / post-merge /
  normalised (parse/categorise) columns.
- `engine/ingest.py` — assembles the per-accession table (sizing + three-state completeness +
  base→post-merge `backfill_delta`).
- `engine/gsheet.py` — OneDrive-free OAuth reader for the live `study_level` / `parsed_per_project`
  tabs (credential from `BAC_GOOGLE_CLIENT_SECRET`, default `~/.config/bac_metadata/`).
- `applications/klebsiella/run_stage1.py` — `--mode sizing-only` (ENA only) or `--mode full`.
- `applications/klebsiella/validate_stage1.py` — reconcile sizing + completeness vs the sheet.

## ENA sizing — the record unit (calibration)

We query **`result=read_run`** and deduplicate to sample level, **not** `result=sample`.
ENA reliably links *runs* to a study via `study_accession` but frequently does **not** link
samples. Calibration:

| Accession | `result=sample` | `read_run` | distinct samples | distinct *Klebsiella* samples | our holding |
|---|---:|---:|---:|---:|---:|
| `PRJNA339843` (ARGONAUT-IV) | 224 | **225** (= ENA browser count) | 224 | 207 | 225 |
| `PRJEB74192` (One Health Norway) | **0** (broken) | 3,831 | **3,261** | 3,261 | 3,255 |

`PRJEB74192` is the decisive case: the sample query returns nothing while read_run returns 3,831
(3,261 distinct samples) — matching the curated holding. Hence `ena_total_runs` matches the
browser/manual count, and `ena_total_samples` / `ena_taxon_samples` are distinct-sample counts
derived from the read_run table.

**Assembly-only BioProjects** with no portal-visible reads (e.g. `PRJNA565795`) count as zero on
all units; they surface as anomalies in the validation report rather than being silently dropped.

## Validation semantics — prior (sheet) vs found (ENA)

The validation report is a **per-curation-row comparison of the prior finding** (your Google
Sheet: `prior_isolates_in_study`) **against what the engine independently found in ENA**
(`ena_klebsiella_samples`, `ena_total_samples`, `ena_total_runs`, `n_child_studies` — all from
the live `read_run` interrogation, not the sheet). Each row gets a `classification` + a plain
`note` saying how the two relate. This is the check that the engine reproduces the manual
EBI-sizing step.

Two ENA bounds matter: `ena_klebsiella_samples` (scientific_name match) is a **lower bound** — it
**under-counts** Klebsiella for broad *Enterobacteriaceae* projects where submitters didn't set
the species — while `ena_total_samples` is the **upper bound**. Classification uses both:

| class | meaning |
|---|---|
| `whole_project` | curated ≈ ENA Klebsiella → paper covers the whole project |
| `subsample` | curated < ENA Klebsiella → paper covers part of a larger project |
| `shared_accession` | one accession cited by several curated papers (each a slice) |
| `umbrella` | one accession is many substudies (`n_child_studies` ≥ 3) — needs splitting |
| `ena_underlabels_klebsiella` | ENA holds the records but labels fewer as Klebsiella; curation is more complete (**not** an error) |
| `review_prior_exceeds_ena` / `review_no_ena_records` | curated exceeds what ENA holds under the accession — genuine review queue |

## Outputs (`applications/klebsiella/data/`)

- `stage1_sizing.tsv` — sizing-only output (committed).
- `stage1_ingest.tsv` — full per-accession table incl. three-state completeness (full mode).
- `stage1_validation_report.{tsv,md}` — sizing + completeness reconciliation.
- `ena_cache/` — raw per-accession read_run TSVs (gitignored; makes reruns deterministic/offline).

## How to run

```bash
unset VIRTUAL_ENV   # use the project .venv, not a stale system one
# Sizing only (local, ~a few minutes for the 156-accession split):
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_stage1.py --mode sizing-only
# Full (also computes completeness from the collated ATB data). On the HPC this is zero-config;
# locally, point the project_k root + user-dir at the OneDrive mirror via two env vars — the same
# command then resolves all collation inputs identically (no per-file --metadata-* overrides):
BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data \
  uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_stage1.py --mode full
# (per-file --metadata-file1/2/3 --qc-excel --ena-project-dir overrides still exist for ad-hoc paths)
# Validate:
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/validate_stage1.py
```

## Results (sizing + completeness verdicts) — see PROGRESS_REPORT

The 150-row prior-vs-found classification counts and the three-state completeness table (base →
post-merge → normalised, with the base→post-merge backfill delta the later stages must reproduce) are
in [`PROGRESS_REPORT.md`](PROGRESS_REPORT.md) §2. Two method notes: review-queue rows whose
`paper_link` is a Pathogenwatch/KlebNET collection are auto-annotated (count scraped from the
collection, not deposited under the ENA accession — expected, do not chase); completeness sanity must
hold (`base ≤ post-merge`, `norm ≤ post-merge`).

## Data location

The collation inputs are identical on HPC (`<project_k>/david/raw/…`) and the local OneDrive
mirror (`…/project_k/data/raw/…`) — same sizes/mtimes, 98 `ready_to_merge` files both sides. The
only non-uniformity is the path root **and** the per-user segment (`david` on HPC, `data` in the
OneDrive share). Both are now wired through `path_resolve.project_k_user_dir()`: `metadata_collation.py`'s
path constants build on `<BACHGT_PROJECT_K_ROOT>/<BACHGT_PROJECT_K_USER>` (defaults
`/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw` + `david`, so the HPC needs no config). A local
run sets `BACHGT_PROJECT_K_ROOT=…/project_k` and `BACHGT_PROJECT_K_USER=data`; the identical command
then resolves every collation input on either machine.

The Google OAuth `client_secret` is resolved **off OneDrive** too — env `BAC_GOOGLE_CLIENT_SECRET`
→ `~/.config/bac_metadata/client_secret.json` → legacy OneDrive path — by both
`engine/gsheet.py` and `pp/metadata_collation._authenticate_google`, sharing one token at
`~/.config/bac_metadata/token.json`.
