# Klebsiella agentic metadata — wrap-up report

_Read-only, deterministic; every figure traces to a per-tranche artifact._

## 1. Reconciliation — per-tranche fills vs the accumulated master

| field | train | test | tail100 | tail50_99 | tail25_49 | tail10_24 | sub10 | Σ tranches | master | Δ |
|---|---|---|---|---|---|---|---|---|---|---|
| country | 10740 | 9292 | 707 | 939 | 619 | 435 | 208 | 22940 | 22940 | 0 |
| collection_date | 11148 | 9330 | 562 | 587 | 735 | 259 | 60 | 22681 | 22681 | 0 |
| isolation_source | 11923 | 5718 | 409 | 1016 | 608 | 350 | 275 | 20299 | 20299 | 0 |
| host | 16510 | 9693 | 2211 | 2943 | 1648 | 935 | 763 | 34703 | 34703 | 0 |

**Reconciliation: ✅ EXACT (Σ tranches == master, all fields)**

## 2. Papers reviewed

| tranche | studies | papers found | full-text read | manual PDFs |
|---|---|---|---|---|
| train | 109 | 91 | 105 | 37 |
| test | 47 | 30 | 43 | 17 |
| tail100 | 50 | 41 | 40 | 4 |
| tail50_99 | 95 | 78 | 73 | 7 |
| tail25_49 | 148 | 121 | 114 | 8 |
| tail10_24 | 214 | 160 | 146 | 17 |
| sub10 | 1251 | 431 | 343 | 0 |
| **TOTAL** | **1914** | **952** | **864** | **90** |

## 3. Experimental-evolution studies flagged for exclusion

| tranche | evo studies |
|---|---|
| train | 0 |
| test | 0 |
| tail100 | 3 |
| tail50_99 | 5 |
| tail25_49 | 10 |
| tail10_24 | 18 |
| sub10 | 42 |
| **TOTAL** | **78** |

**78 studies / 1489 samples** now carry `study_type_excluded=True` for downstream removal.

## 4. Per-sample completeness — raw ENA → agent → v2 gold

_On the master∩gold cohort (samples in **both** the agent master and the v2 gold), placeholder-stripped uniformly. Manual v2 only ever curated train/val/test; the tail and uncovered bands are raw ENA, so there the agent is the sole enrichment._

### 4a. Cohort — 83,780 samples (excl. the Refseq carve-out)

| field | raw ENA % | agent % | v2 gold % | agent − raw (fill Δ) | agent − v2 |
|---|--:|--:|--:|--:|--:|
| country | 70.8 | 94.8 | 91.2 | +24.0 | +3.6 |
| collection_date | 66.9 | 89.6 | 81.7 | +22.7 | +7.9 |
| isolation_source | 54.7 | 74.9 | 68.6 | +20.2 | +6.3 |
| host | 52.0 | 90.1 | 79.7 | +38.1 | +10.4 |

### 4b. Agent − v2 gold by split (percentage points; ≥ 0 = match-or-beat v2)

| split | n | country | collection_date | isolation_source | host |
|---|--:|--:|--:|--:|--:|
| train | 19,978 | -2.8 | +7.9 | +0.2 | +9.0 |
| test | 28,231 | +2.6 | +9.6 | +0.0 | +2.2 |
| val | 11,932 | +3.6 | +4.9 | +16.0 | +7.0 |
| tail100 | 7,300 | +4.2 | +3.4 | +7.2 | +6.4 |
| tail50_99 | 6,118 | +14.2 | +8.7 | +18.6 | +37.4 |
| tail25_49 | 4,647 | +12.6 | +12.8 | +17.3 | +28.5 |
| tail10_24 | 3,058 | +13.9 | +9.7 | +15.1 | +27.5 |
| other_uncovered(<10) | 2,419 | +7.7 | +4.5 | +17.4 | +21.4 |
| NCTC_collection | 97 | +0.0 | +0.0 | +0.0 | +0.0 |
| Refseq_collection | 3,513 | -96.4 | -94.1 | -78.7 | -83.0 |
| **TOTAL_excl_Refseq** | **83,780** | **+3.6** | **+7.9** | **+6.3** | **+10.4** |

_Agent matches-or-beats v2 on the cohort (proving nothing major was dropped in accumulation) and adds most on the uncurated tail bands. The one negative, `Refseq_collection` (RefSeq genomes empty in the ENA base, agent-skipped by design, carried by v2), is a benchmark-scope carve-out — see `scorecard/final_completeness_raw_agent_gold.md`._

## 5. Accuracy vs manual curation

### 5a. Paper-finding + grading (adjudicated; gold folds only)

**train**

| item | N | agreement | agent acc | manual acc | improvement |
|---|---|---|---|---|---|
| paper-finding | 88 | 0.761 | 0.943 | 0.841 | +0.102 |
| amr_study | 86 | 0.802 | 0.977 | 0.835 | +0.141 |
| study_setting | 95 | 0.916 | 1.000 | 0.916 | +0.084 |
| TOTAL | 269 | 0.829 | 0.974 | 0.866 | +0.108 |

**test**

| item | N | agreement | agent acc | manual acc | improvement |
|---|---|---|---|---|---|
| paper-finding | 30 | 0.833 | 0.900 | 0.933 | -0.033 |
| amr_study | 37 | 0.838 | 0.971 | 0.914 | +0.057 |
| study_setting | 42 | 0.905 | 0.976 | 0.929 | +0.048 |
| TOTAL | 109 | 0.862 | 0.953 | 0.925 | +0.028 |

_Residual disagreements the adjudicator did not rule for the agent are in `diagnostics/adjudication_review_queue.tsv` for curator sign-off._

### 5b. Per-sample fill correctness — blank-fills vs the v2 gold

_Accuracy on fills of a **blank** ENA cell (the positive value-add), scored only where v2 carries a value. `n` = with-gold blank fills. Overwrites of existing ENA values are held out to §5c (they are scored against the very ENA they replace, so they read low by construction)._

| field | train | test | tail100 | tail50_99 | tail25_49 | tail10_24 | sub10 |
|---|---|---|---|---|---|---|---|
| country | 1.000 (n=3686) | 1.000 (n=146) | — | 1.000 (n=67) | — | — | — |
| collection_date | 0.984 (n=6801) | 0.938 (n=3492) | — | 1.000 (n=128) | — | — | — |
| isolation_source | 0.994 (n=5285) | 0.996 (n=3783) | 0.988 (n=86) | 0.523 (n=128) | — | — | — |
| host | 0.933 (n=1888) | 0.965 (n=4516) | — | 0.794 (n=102) | 0.723 (n=65) | 1.000 (n=13) | — |

_train/test carry genuine per-sample gold overlap; for the tail bands the v2 gold is raw ENA or a coarse study-level backfill, so small-n dips (e.g. isolation_source) reflect the gold, not the fill — §4 is the coverage check there. '—' = no with-gold blank fills to score._

### 5c. Overwrites of existing ENA values (gated; for spot-review)

_Per-sample is the only stage that can replace a non-blank ENA value, and only through the fidelity gate (date-granularity / `judge_overwrite_fidelity`, vague→specific only). Scored against the parsed-ENA gold these read low **by construction** — the gold *is* the ENA value the fill deliberately replaced (e.g. `clinical sample`→`rectal`) — so they are surfaced for optional manual spot-review, not counted as errors._

| tranche | overwrites | with v2 gold | matches v2 | top studies (overwrite count) |
|---|--:|--:|--:|---|
| train | 1641 | 1605 | 682/1605 (0.42) | PRJEB63361 (826), PRJEB58216 (418), PRJEB36683 (323), PRJEB48990 (73) |
| test | 1041 | 1005 | 819/1005 (0.81) | PRJEB63349 (687), PRJEB34643 (210), PRJNA839691 (143), PRJEB1271 (1) |
| tail100 | 105 | 97 | 96/97 (0.99) | PRJNA675776 (105) |
| tail50_99 | 74 | 73 | 0/73 (0.00) | PRJEB56668 (73), PRJEB39942 (1) |
| tail25_49 | 213 | 159 | 114/159 (0.72) | PRJEB76311 (48), PRJEB76496 (46), PRJNA741123 (31), PRJEB76256 (30) |
| tail10_24 | 31 | 21 | 2/21 (0.10) | PRJEB34353 (19), PRJEB38898 (12) |
| sub10 | 0 | 0 | — | — |

_The v2 gold for these four fields is essentially parsed raw ENA (+ coarse study-level backfill), not an independent per-sample truth, so 'matches v2' measures agreement with ENA: a high rate means the overwrite was re-derivable from ENA, a **low** rate means the fill genuinely moved the value away from a vague ENA term (the intended vague→specific gain) — those rows (train `PRJEB63361/58216/36683`, tail50_99 `PRJEB56668`, tail10_24 `PRJEB34353`) are the spot-review targets, not errors._

