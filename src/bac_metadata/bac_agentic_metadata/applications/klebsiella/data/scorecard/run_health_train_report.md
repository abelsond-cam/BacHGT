# Run-health report (train / train)

## ⚠️ **12 ACTIONABLE + 5 BLOCKED outstanding — supplement & rerun**

312 (study × field) cells over 78 studies — **FILLED 258 · ACTIONABLE 12 · BLOCKED 5 · EXHAUSTED 37**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (4)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB24082 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24082.xlsx` |
| PRJEB24085 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24085.xlsx` |
| PRJEB39867 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Surveillance and Genomic Analysis of Third-Generation Cephal](https://doi.org/10.3390/antibiotics11101286) | `manual_download_supp/PRJEB39867.xlsx` |
| PRJEB6891 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Gastrointestinal Carriage Is a Major Reservoir of Klebsiella](https://doi.org/10.1093/cid/cix270) | `manual_download_supp/PRJEB6891.xlsx` |

### Answer escalations (2)

- PRJEB37378 (host,isolation_source)
- PRJEB42462 (collection_date,country)

## No paper could be found — validated, won't be recovered
3 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJEB12699, PRJEB22903, PRJEB28054

## Tables present but unjoinable (Phase-2 linkage target)
4 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB38289, PRJNA1087366, PRJNA767944, PRJNA804332

## Escalation status
- queue generated: 20 rows; answered: 12; applied fills: 7192.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 23
- no_supp: 23
- field_not_in_table: 2
- value_check_failed: 1


## Per-field completeness roll-up (verbatim from completeness report)

| field | agent | v2 | gain_wf | gain_ps | gain_esc | residual | flag |
|---|---|---|---|---|---|---|---|
| country | 0.9214 | 0.8821 | 0.135 | 0.1145 | 0.0515 | 0.0 |  |
| collection_date | 0.8665 | 0.7473 | 0.0606 | 0.1553 | 0.0998 | 0.0 |  |
| isolation_source | 0.7149 | 0.6689 | 0.0482 | 0.1391 | 0.0826 | 0.0 |  |
| host | 0.8868 | 0.7891 | 0.411 | 0.004 | 0.0279 | 0.0 |  |


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (28 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ⛔ INCOMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_train.tsv`: **20 generated · 12 answered · 8 PENDING** (7192 fills applied).

⛔ **8 tight-grading decision(s) are UNANSWERED.** Fill the `answer` column (a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.

# → ⛔ CURATOR ACTION OUTSTANDING — 0 paper(s) to add, 8 escalation(s) to answer

