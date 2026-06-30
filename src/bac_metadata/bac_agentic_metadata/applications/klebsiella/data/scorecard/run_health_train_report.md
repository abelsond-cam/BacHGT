# Run-health report (train,val / train)

## ⚠️ **21 ACTIONABLE + 6 BLOCKED outstanding — supplement & rerun**

436 (study × field) cells over 109 fold studies — **FILLED 374 · ACTIONABLE 21 · BLOCKED 6 · EXHAUSTED 35**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance).

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (12)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJDB12075 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic epidemiology and temperature dependency of hypermuco](https://doi.org/10.1099/mgen.0.000827) | `manual_download_supp/PRJDB12075.xlsx` |
| PRJDB5929 | isolation_source | isolation_source:0,host:0,collection_date:0 | [A Nationwide Plasmidome Surveillance in Thailand Reveals a L](https://doi.org/10.1128/jcm.01080-22) | `manual_download_supp/PRJDB5929.xlsx` |
| PRJEB15226 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-Genome Multilocus Sequence Typing of Extended-Spectrum](https://doi.org/10.1128/jcm.01648-16) | `manual_download_supp/PRJEB15226.xlsx` |
| PRJEB17615 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Integrating whole-genome sequencing within the National Anti](https://doi.org/10.1038/s41467-020-16322-5) | `manual_download_supp/PRJEB17615.xlsx` |
| PRJEB21277 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB21277.xlsx` |
| PRJEB24082 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24082.xlsx` |
| PRJEB24085 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24085.xlsx` |
| PRJEB37378 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Drivers of Resistance in Uganda and Malawi (DRUM): a protoco](https://doi.org/10.12688/wellcomeopenres.17581.2) | `manual_download_supp/PRJEB37378.xlsx` |
| PRJEB39867 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Surveillance and Genomic Analysis of Third-Generation Cephal](https://doi.org/10.3390/antibiotics11101286) | `manual_download_supp/PRJEB39867.xlsx` |
| PRJEB6891 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Gastrointestinal Carriage Is a Major Reservoir of Klebsiella](https://doi.org/10.1093/cid/cix270) | `manual_download_supp/PRJEB6891.xlsx` |
| PRJNA855907 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Characterization of Extensively Drug-Resistant (XDR) Carbape](https://doi.org/10.1128/spectrum.00975-22) | `manual_download_supp/PRJNA855907.xlsx` |
| PRJNA996149 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [<i>In vitro</i> activity of cefiderocol, a siderophore cepha](https://doi.org/10.1128/aac.00735-23) | `manual_download_supp/PRJNA996149.xlsx` |

### Escalate big-decision whole-field calls (>1% of cohort) — not in queue (1)

- PRJNA604975 (collection_date)

## No paper could be found — validated, won't be recovered
3 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJEB12699, PRJEB22903, PRJEB28054

## Tables present but unjoinable (Phase-2 linkage target)
6 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB1563, PRJEB36486, PRJEB38289, PRJNA1087366, PRJNA767944, PRJNA804332

## Escalation status
- queue generated: 34 rows; answered: 19; applied fills: 8977.

## Zero-reason breakdown (per-sample residual)

- no_supp: 35
- NO_PMCID: 15
- field_not_in_table: 4
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

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_train.tsv`: **34 generated · 19 answered · 0 PENDING** (8977 fills applied).

✅ All 34 escalation(s) resolved (answered or explicitly rejected).

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

