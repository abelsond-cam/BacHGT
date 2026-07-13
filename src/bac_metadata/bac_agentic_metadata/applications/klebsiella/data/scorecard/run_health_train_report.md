# Run-health report (train,val / train)

## ⚠️ **55 ACTIONABLE + 0 BLOCKED outstanding — supplement & rerun**

436 (study × field) cells over 109 studies — **FILLED 372 · ACTIONABLE 55 · BLOCKED 0 · EXHAUSTED 9**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 105/109 studies have a resolvable paper (18 none-found) |
| Manual papers picked up & used | 38 study(ies) filled from a hand-added PDF (PRJEB1563, PRJEB19322, PRJEB20799, PRJEB21277, PRJEB22252, PRJEB22890, PRJEB24082, PRJEB27256…) |
| Meaningless values dropped (preclean) | **44** cells blanked pre-fill (isolation_source 44) so the agent can recover a real value |
| Per-sample added from supplementary tables | 20 study(ies), **21228** fills from a per-isolate table (30 tables read) |
| Meaning of words improved (overwrites) | **1604** ENA cells replaced by a better table value (collection_date 658, host 1, isolation_source 945) — examples below |
| Escalation fired (close calls + big papers) | 63 decision(s) / 38 studies — close-call 15, big-decision 6, residual 39, sticky 4 |
| Extra manual tables requested | ⛔ **1** table(s) requested — PRJEB20799 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2019' → '2019-11-28 00:00:00'
- `collection_date`: '2020' → '2020-03-12 00:00:00'
- `host`: 'environmental' → 'environment_soil'
- `isolation_source`: 'Human body sites or biosamples' → 'SCALP'
- `isolation_source`: 'Human body sites or biosamples' → 'BLOOD'

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (1)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB20799 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | (no link) | `manual_download_supp/PRJEB20799.xlsx` |

### Answer escalations (30)

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
- PRJEB30134 (collection_date,isolation_source)
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
- queue generated: 63 rows; answered: 12; applied fills: 7192.

## Zero-reason breakdown (per-sample residual)

- no_supp: 27
- NO_PMCID: 13
- field_not_in_table: 8
- unanchored: 7
- abstained_other: 5
- manifest_only: 4


## Per-field completeness roll-up (verbatim from completeness report)

| field | agent | v2 | gain_wf | gain_ps | gain_esc | residual | flag |
|---|---|---|---|---|---|---|---|
| country | 0.9217 | 0.8821 | 0.1352 | 0.1147 | 0.0515 | 0.0 |  |
| collection_date | 0.8592 | 0.7473 | 0.0155 | 0.2274 | 0.0656 | 0.0 |  |
| isolation_source | 0.7463 | 0.6689 | 0.0727 | 0.1683 | 0.0603 | 0.0 |  |
| host | 0.9077 | 0.7891 | 0.3944 | 0.0619 | 0.0076 | 0.0 |  |


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (38 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ⛔ INCOMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_train.tsv`: **63 generated · 12 answered · 51 PENDING** (7192 fills applied).

⛔ **51 tight-grading decision(s) are UNANSWERED.** Fill the `answer` column (a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.

# → ⛔ CURATOR ACTION OUTSTANDING — 0 paper(s) to add, 51 escalation(s) to answer

