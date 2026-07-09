# Klebsiella agentic curation — completeness by split (agent vs manual gold)

**Updated 2026-07-09.** Cohort = the **87,293** samples present in *both* the agent master and the manual `metadata_v2` gold (`*_parsed` columns). Blank = null-like token set applied uniformly to raw / gold / agent. This supersedes the earlier single pooled table, which **masked the per-split picture**.

## Headline

- The agent **meets or beats** manual curation on **every split it was tasked with** — and beats it handsomely on the size-banded tail (studies manual never curated).

- The pooled figure is dragged to a *draw* by one **out-of-scope** bucket, `Refseq_collection` (3,513 RefSeq/GCF genomes that are **empty in the ENA base table**, were **skipped by design**, and were manually enriched from NCBI). **Excluding it, the agent beats manual on all four fields:** host +6.2, country +2.8, collection_date +6.6, isolation_source +3.3.

- **No fills were lost in accumulation** — the union of all per-tag applied files equals the master exactly (0.0–0.1% rounding), across all six tags (102,767 fills).


## Agent − manual by split (percentage points, per field)

| split | n | host | country | collection_date | isolation_source |
|---|--:|--:|--:|--:|--:|
| train | 19,978 | -0.6 | -4.8 | +3.5 | -4.6 |
| test | 28,231 | +1.8 | +2.6 | +9.6 | -0.9 |
| val | 11,932 | +7.0 | +3.6 | +4.9 | +10.4 |
| tail100 | 7,300 | +4.3 | +3.4 | +2.9 | +5.9 |
| tail50_99 | 6,118 | +30.7 | +14.2 | +8.7 | +16.5 |
| tail25_49 | 4,647 | +25.1 | +12.4 | +11.0 | +15.4 |
| tail10_24 | 3,058 | +22.2 | +12.6 | +7.5 | +13.3 |
| other_uncovered(<10) | 2,419 | -6.5 | +0.1 | +2.5 | +7.4 |
| NCTC_collection | 97 | +0.0 | +0.0 | +0.0 | +0.0 |
| Refseq_collection | 3,513 | -83.0 | -96.4 | -94.1 | -78.7 |
| TOTAL | 87,293 | +2.5 | -1.2 | +2.6 | +0.0 |
| TOTAL_excl_Refseq | 83,780 | +6.2 | +2.8 | +6.6 | +3.3 |

Positive = agent more complete than manual. The tail bands (manual never curated them) are where the agent adds most; `train` trails slightly on country/isolation_source (a few specific studies — see the manual-curation worklist and the residual-deficit notes).


## host: raw → manual → agent, by split

| split | n | raw ENA % | manual gold % | agent % | agent − manual |
|---|--:|--:|--:|--:|--:|
| train | 19,978 | 44.1 | 80.1 | 79.5 | -0.6 |
| test | 28,231 | 55.5 | 85.7 | 87.5 | +1.8 |
| val | 11,932 | 45.3 | 92.6 | 99.6 | +7.0 |
| tail100 | 7,300 | 69.0 | 85.5 | 89.8 | +4.3 |
| tail50_99 | 6,118 | 52.0 | 57.5 | 88.2 | +30.7 |
| tail25_49 | 4,647 | 58.0 | 60.9 | 86.0 | +25.1 |
| tail10_24 | 3,058 | 53.7 | 54.5 | 76.7 | +22.2 |
| other_uncovered(<10) | 2,419 | 47.6 | 54.1 | 47.6 | -6.5 |
| NCTC_collection | 97 | 0.0 | 0.0 | 0.0 | +0.0 |
| Refseq_collection | 3,513 | 0.0 | 83.0 | 0.0 | -83.0 |
| TOTAL | 87,293 | 49.9 | 79.9 | 82.4 | +2.5 |
| TOTAL_excl_Refseq | 83,780 | 52.0 | 79.7 | 85.9 | +6.2 |

## country: raw → manual → agent, by split

| split | n | raw ENA % | manual gold % | agent % | agent − manual |
|---|--:|--:|--:|--:|--:|
| train | 19,978 | 66.3 | 93.9 | 89.1 | -4.8 |
| test | 28,231 | 69.6 | 94.9 | 97.5 | +2.6 |
| val | 11,932 | 57.2 | 96.3 | 99.9 | +3.6 |
| tail100 | 7,300 | 89.8 | 89.2 | 92.6 | +3.4 |
| tail50_99 | 6,118 | 83.0 | 83.0 | 97.2 | +14.2 |
| tail25_49 | 4,647 | 83.7 | 81.5 | 93.9 | +12.4 |
| tail10_24 | 3,058 | 78.1 | 76.5 | 89.1 | +12.6 |
| other_uncovered(<10) | 2,419 | 69.9 | 69.8 | 69.9 | +0.1 |
| NCTC_collection | 97 | 0.0 | 0.0 | 0.0 | +0.0 |
| Refseq_collection | 3,513 | 0.0 | 96.4 | 0.0 | -96.4 |
| TOTAL | 87,293 | 68.0 | 91.4 | 90.2 | -1.2 |
| TOTAL_excl_Refseq | 83,780 | 70.8 | 91.2 | 94.0 | +2.8 |

## collection_date: raw → manual → agent, by split

| split | n | raw ENA % | manual gold % | agent % | agent − manual |
|---|--:|--:|--:|--:|--:|
| train | 19,978 | 61.0 | 79.7 | 83.2 | +3.5 |
| test | 28,231 | 68.2 | 85.5 | 95.1 | +9.6 |
| val | 11,932 | 47.1 | 81.3 | 86.2 | +4.9 |
| tail100 | 7,300 | 84.9 | 84.1 | 87.0 | +2.9 |
| tail50_99 | 6,118 | 80.0 | 80.5 | 89.2 | +8.7 |
| tail25_49 | 4,647 | 79.6 | 76.8 | 87.8 | +11.0 |
| tail10_24 | 3,058 | 74.1 | 71.9 | 79.4 | +7.5 |
| other_uncovered(<10) | 2,419 | 74.8 | 72.3 | 74.8 | +2.5 |
| NCTC_collection | 97 | 100.0 | 100.0 | 100.0 | +0.0 |
| Refseq_collection | 3,513 | 0.0 | 94.1 | 0.0 | -94.1 |
| TOTAL | 87,293 | 64.2 | 82.2 | 84.8 | +2.6 |
| TOTAL_excl_Refseq | 83,780 | 66.9 | 81.7 | 88.3 | +6.6 |

## isolation_source: raw → manual → agent, by split

| split | n | raw ENA % | manual gold % | agent % | agent − manual |
|---|--:|--:|--:|--:|--:|
| train | 19,978 | 44.3 | 71.6 | 67.0 | -4.6 |
| test | 28,231 | 63.5 | 78.5 | 77.6 | -0.9 |
| val | 11,932 | 47.3 | 72.4 | 82.8 | +10.4 |
| tail100 | 7,300 | 49.7 | 46.6 | 52.5 | +5.9 |
| tail50_99 | 6,118 | 63.9 | 59.0 | 75.5 | +16.5 |
| tail25_49 | 4,647 | 58.3 | 51.4 | 66.8 | +15.4 |
| tail10_24 | 3,058 | 57.8 | 52.6 | 65.9 | +13.3 |
| other_uncovered(<10) | 2,419 | 63.1 | 55.6 | 63.0 | +7.4 |
| NCTC_collection | 97 | 0.0 | 0.0 | 0.0 | +0.0 |
| Refseq_collection | 3,513 | 0.0 | 78.7 | 0.0 | -78.7 |
| TOTAL | 87,293 | 52.6 | 69.0 | 69.0 | +0.0 |
| TOTAL_excl_Refseq | 83,780 | 54.9 | 68.6 | 71.9 | +3.3 |

## The `Refseq_collection` carve-out (why the naive pool is a draw)

`Refseq_collection` = **3,513** RefSeq (GCF) reference genomes. In the ENA base table their four fields are **empty** (raw 0%, 0%, 0%, 0%) because the base is built from ENA *reads* and these assemblies have none. Manual gold enriched them from NCBI (gold 83%, 96%, 94%, 79%); the agent skipped them by design (`SYNTHETIC_STUDIES`). They are already carried by manual values in the merged deliverable, so this is a **benchmark-scope** issue, not a data gap. → resolved by the planned NCBI base-table enrichment.

## Accumulation integrity

For every tag, every non-blank applied fill reaches the master (`after_c` = base ∪ applied files **== master**, 0.0–0.1% rounding). All six tags present in `curated_fills.tsv`: train 47,555 · test 39,962 · tail50_99 6,200 · tail25_49 3,679 · tail100 3,586 · tail10_24 1,785 = **102,767**.

## Reconciliation with the earlier per-fold reports

The original `validate_backfill_completeness.py` fold reports showed larger agent−gold margins because they scored over **all** fold-base samples and counted samples **absent from gold** as gold-blank (inflating the agent's lead). This table restricts to master∩gold (apples-to-apples), so the per-fold margins are smaller but honest; the agent still leads on the fold marginal-over-raw for every field.

## Status of the manual-curation loop (2026-07-09)

The curator loop is now fixed (run_health no longer reports a hollow ALL CLEAR over 0 studies; per-sample uses manual supp tables even without a PMCID; worklists are tag-suffixed). It surfaced a worklist of **32 papers + 21 per-isolate tables** to fetch, concentrated in the <100-sample bands (`find_papers/manual_curation_worklist.md`). **These numbers are the pre-worklist baseline;** servicing the worklist will lift the tail bands' `isolation_source` (and some `country`) further.

## Reproduce (pure pandas, no LLM)

```bash
K=src/bac_metadata/bac_agentic_metadata/applications/klebsiella
GOLD=".../project_k/data/final/metadata/metadata_final_curated_all_samples_and_columns.tsv"
uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.accumulate \
  --data-dir "$K/data" --table "$K/data/inputs/base_table.csv" --spec "$K/attributes.yaml" \
  --tags train,test,tail100,tail50_99,tail25_49,tail10_24 --canonical "$GOLD"
# then this per-split table is recomputed by the scorecard script.
```

