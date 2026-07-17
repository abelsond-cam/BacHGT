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

## 4. Per-sample completeness — base → filled

### Cohort (master)

| field | base | filled | Δ pp |
|---|---|---|---|
| country | 0.663 | 0.901 | +23.8 |
| collection_date | 0.623 | 0.848 | +22.5 |
| isolation_source | 0.510 | 0.696 | +18.6 |
| host | 0.487 | 0.847 | +36.0 |

### Per tranche (filled completeness)

| field | train | test | tail100 | tail50_99 | tail25_49 | tail10_24 | sub10 |
|---|---|---|---|---|---|---|---|
| country | 0.934 | 0.959 | 0.922 | 0.957 | 0.927 | 0.900 | 0.775 |
| collection_date | 0.857 | 0.935 | 0.846 | 0.868 | 0.886 | 0.812 | 0.767 |
| isolation_source | 0.764 | 0.747 | 0.493 | 0.756 | 0.661 | 0.634 | 0.712 |
| host | 0.924 | 0.837 | 0.886 | 0.949 | 0.864 | 0.813 | 0.756 |

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

### 5b. Per-field value accuracy vs the v2 gold (per-sample fills)

| field | train | test | tail100 | tail50_99 | tail25_49 | tail10_24 | sub10 |
|---|---|---|---|---|---|---|---|
| country | 1.000 (n=3686) | 1.000 (n=146) | — | 1.000 (n=67) | 0.000 (n=13) | — | — |
| collection_date | 0.986 (n=7447) | 0.939 (n=3581) | 0.990 (n=97) | 1.000 (n=128) | 1.000 (n=96) | — | — |
| isolation_source | 0.846 (n=6206) | 0.957 (n=4699) | 0.988 (n=86) | 0.333 (n=201) | 0.360 (n=50) | 0.095 (n=21) | — |
| host | 0.934 (n=1926) | 0.965 (n=4516) | — | 0.794 (n=102) | 0.723 (n=65) | 1.000 (n=13) | — |

_'—' = the tranche's samples are not in the manual v2 gold (nothing to score against)._

