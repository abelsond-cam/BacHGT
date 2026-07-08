# Klebsiella agentic curation — final whole-cohort completeness

**Size-≥10 study tail complete** (2026-07-08). All bands graded, escalated, and accumulated into the
master: `train, test, tail100, tail50_99, tail25_49, tail10_24`.

## Whole-cohort agent completeness (all 96,291 base samples)

Agent fills (base ENA → agent), from the accumulation fill summary:

| field | base (raw ENA) | agent | gap closed |
|---|---:|---:|---:|
| host | 0.487 | **0.808** | +0.321 |
| country | 0.663 | **0.893** | +0.230 |
| collection_date | 0.623 | **0.837** | +0.214 |
| isolation_source | 0.510 | **0.668** | +0.158 |

## Raw → manual gold → agent (cohort = 87,293 samples in metadata_v2 ∩ master)

Comparison against the manual **metadata_v2** gold (2026-05-17 snapshot; `*_parsed` columns):

| field | raw ENA | metadata_v2 (manual) | agent | agent adds where gold blank |
|---|---:|---:|---:|---:|
| host | 57.8% | 79.9% | **82.4%** | +8,437 |
| country | 70.8% | 91.4% | 90.2% | +3,937 |
| collection_date | 68.4% | 82.2% | **84.8%** | +7,001 |
| isolation_source | 53.7% | 69.0% | 69.0% (=) | +6,494 |

## Interpretation

- The agentic pipeline **reaches parity with, or exceeds, the manual curation** it was benchmarked
  against: agent > gold on host (+2.5pt) and collection_date (+2.6pt), equal on isolation_source, and
  within ~1.2pt on country.
- In **every** field the agent fills thousands of cells that are **blank in the manual gold** —
  **~26,000 cells total** (host 8,437 · collection_date 7,001 · isolation_source 6,494 · country 3,937).
  These feed the merged `metadata_curated_master_merged.tsv` (human > agent > ENA, 90,903 rows).
- country is the one field where the manual gold is marginally more complete overall — worth a targeted
  look at the ~country cells gold has but the agent left blank.

## Provenance / reproduce (pure pandas, no LLM)

```bash
K=src/bac_metadata/bac_agentic_metadata/applications/klebsiella
GOLD=".../project_k/data/final/metadata/metadata_final_curated_all_samples_and_columns.tsv"
uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.accumulate \
  --data-dir "$K/data" --table "$K/data/inputs/base_table.csv" --spec "$K/attributes.yaml" \
  --tags train,test,tail100,tail50_99,tail25_49,tail10_24 --canonical "$GOLD"
```

Gold path (local mirror, when HPC/CSD3 is down) is recorded in the agent memory note
`local-gold-project-k-mirror`. The large `metadata_curated_master*.tsv` are gitignored; this report and
the per-band artifacts are versioned.
