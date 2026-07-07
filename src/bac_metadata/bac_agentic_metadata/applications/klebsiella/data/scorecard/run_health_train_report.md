# Run-health report (train,val / train)

## ⚠️ **21 ACTIONABLE + 7 BLOCKED outstanding — supplement & rerun**

436 (study × field) cells over 109 fold studies — **FILLED 368 · ACTIONABLE 21 · BLOCKED 7 · EXHAUSTED 40**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance).

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (9)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJDB12075 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic epidemiology and temperature dependency of hypermuco](https://doi.org/10.1099/mgen.0.000827) | `manual_download_supp/PRJDB12075.xlsx` |
| PRJEB15226 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-Genome Multilocus Sequence Typing of Extended-Spectrum](https://doi.org/10.1128/jcm.01648-16) | `manual_download_supp/PRJEB15226.xlsx` |
| PRJEB17615 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Integrating whole-genome sequencing within the National Anti](https://doi.org/10.1038/s41467-020-16322-5) | `manual_download_supp/PRJEB17615.xlsx` |
| PRJEB24082 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24082.xlsx` |
| PRJEB24085 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24085.xlsx` |
| PRJEB39867 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Surveillance and Genomic Analysis of Third-Generation Cephal](https://doi.org/10.3390/antibiotics11101286) | `manual_download_supp/PRJEB39867.xlsx` |
| PRJEB6891 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Gastrointestinal Carriage Is a Major Reservoir of Klebsiella](https://doi.org/10.1093/cid/cix270) | `manual_download_supp/PRJEB6891.xlsx` |
| PRJNA855907 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Characterization of Extensively Drug-Resistant (XDR) Carbape](https://doi.org/10.1128/spectrum.00975-22) | `manual_download_supp/PRJNA855907.xlsx` |
| PRJNA996149 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [<i>In vitro</i> activity of cefiderocol, a siderophore cepha](https://doi.org/10.1128/aac.00735-23) | `manual_download_supp/PRJNA996149.xlsx` |

### Answer escalations (2)

- PRJEB37378 (host,isolation_source)
- PRJEB42462 (collection_date,country)

### Escalate big-decision whole-field calls (>1% of cohort) — not in queue (1)

- PRJNA604975 (collection_date)

## No paper could be found — validated, won't be recovered
3 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJEB12699, PRJEB22903, PRJEB28054

## Tables present but unjoinable (Phase-2 linkage target)
6 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB1563, PRJEB36486, PRJEB38289, PRJNA1087366, PRJNA767944, PRJNA804332

## Escalation status
- queue generated: 20 rows; answered: 12; applied fills: 7192.

## Zero-reason breakdown (per-sample residual)

- no_supp: 31
- NO_PMCID: 23
- field_not_in_table: 5
- value_check_failed: 1
- unanchored: 1


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

✅ No outstanding downloads — every findable paper has full text (37 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ⛔ INCOMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_train.tsv`: **20 generated · 12 answered · 8 PENDING** (7192 fills applied).

⛔ **8 tight-grading decision(s) are UNANSWERED.** Fill the `answer` column (a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.

# → ⛔ CURATOR ACTION OUTSTANDING — 0 paper(s) to add, 8 escalation(s) to answer

