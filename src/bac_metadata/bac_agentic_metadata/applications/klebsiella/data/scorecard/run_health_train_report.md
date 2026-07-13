# Run-health report (train,val / train)

## ⚠️ **53 ACTIONABLE + 0 BLOCKED outstanding — supplement & rerun**

436 (study × field) cells over 109 studies — **FILLED 374 · ACTIONABLE 53 · BLOCKED 0 · EXHAUSTED 9**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (1)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB20799 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | (no link) | `manual_download_supp/PRJEB20799.xlsx` |

### Answer escalations (29)

- PRJDB12075 (isolation_source)
- PRJDB5929 (isolation_source)
- PRJEB12699 (isolation_source)
- PRJEB15226 (collection_date,isolation_source)
- PRJEB1563 (collection_date)
- PRJEB17615 (collection_date,isolation_source)
- PRJEB19322 (collection_date)
- PRJEB21277 (collection_date,isolation_source)
- PRJEB22903 (country,isolation_source)
- PRJEB24082 (collection_date,isolation_source)
- PRJEB28054 (collection_date,country,host,isolation_source)
- PRJEB35685 (collection_date,isolation_source)
- PRJEB36486 (collection_date)
- PRJEB37378 (host,isolation_source)
- PRJEB38289 (host)
- PRJEB39867 (collection_date,isolation_source)
- PRJEB42331 (isolation_source)
- PRJEB42462 (country)
- PRJEB64895 (isolation_source)
- PRJEB74083 (isolation_source)
- PRJNA1087366 (collection_date,country)
- PRJNA325243 (host)
- PRJNA549322 (collection_date,country,isolation_source)
- PRJNA634885 (isolation_source)
- PRJNA765801 (collection_date,isolation_source)
- PRJNA767944 (isolation_source)
- PRJNA804332 (isolation_source)
- PRJNA855907 (isolation_source)
- PRJNA996149 (collection_date,isolation_source)

### Escalate big-decision whole-field calls (>1% of cohort) — not in queue (4)

- PRJEB29740 (collection_date,isolation_source)
- PRJEB39943 (country,isolation_source)
- PRJEB42462 (collection_date)
- PRJNA604975 (collection_date)

## Escalation status
- queue generated: 62 rows; answered: 12; applied fills: 7192.

## Zero-reason breakdown (per-sample residual)

- no_supp: 27
- NO_PMCID: 13
- field_not_in_table: 8
- unanchored: 7
- manifest_only: 4
- abstained_other: 3


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

✅ No outstanding downloads — every findable paper has full text (38 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ⛔ INCOMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_train.tsv`: **62 generated · 12 answered · 50 PENDING** (7192 fills applied).

⛔ **50 tight-grading decision(s) are UNANSWERED.** Fill the `answer` column (a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.

# → ⛔ CURATOR ACTION OUTSTANDING — 0 paper(s) to add, 50 escalation(s) to answer

