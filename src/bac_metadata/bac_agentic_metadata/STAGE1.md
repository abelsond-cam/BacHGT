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

## Validation semantics

`ena_taxon_samples` is the project's *Klebsiella* size — the denominator for the later
`paper_coverage_for_taxon`. `isolates_in_study` (trusted sheet column) is what the curation
covered. So `coverage = isolates_in_study / ena_taxon_samples`: ≈1 means a whole-project paper,
≪1 means a subsample. A holding that *exceeds* the project taxon count is a genuine anomaly
(accession drift, data under other accessions, or zero portal-visible reads) and is listed for
manual review.

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
# Full (also computes completeness from the local collated ATB data):
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_stage1.py --mode full \
  --metadata-file1 <local TSV1> --metadata-file2 <local TSV2> --metadata-file3 <local TSV3> \
  --qc-excel <local QC.xlsx> --ena-project-dir <local ready_to_merge dir>
# Validate:
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/validate_stage1.py
```

## Full-split sizing summary (156 accessions / 146 curation rows)

From `stage1_validation_report.md` (read_run-based sizing):

- **median coverage 1.00**; **75%** of rows are whole-project (coverage ≥ 0.9), **7%** are
  subsamples (< 0.5).
- **1 umbrella** flagged: `PRJEB74192` (One Health Norway, 9 child studies) — see
  [`applications/klebsiella/known_cases.md`](applications/klebsiella/known_cases.md).
- **37 anomalies** (holding > ENA project taxon count): a mix of (a) tiny ±1–2-sample rounding
  from samples lacking `scientific_name`, and (b) genuine cases needing review — large excesses
  (`icu_hannoi` 3153 vs 745; `uganda_and_malawi_amr` 6508 vs 1603) and zero-portal-record
  accessions (`PRJNA565795`/`melb_superbugs`, `China colonisation`). Listed in the report for
  manual attention rather than silently dropped.
- True subsamples (distinct from umbrellas) show up as low coverage, e.g. `cdc_surveillance`
  (curated 322 of 12,456 project Klebsiella).
