# Run-health report (train,val / train)

## ⚠️ **20 ACTIONABLE + 10 BLOCKED outstanding — supplement & rerun**

436 (study × field) cells over 109 studies — **FILLED 379 · ACTIONABLE 20 · BLOCKED 10 · EXHAUSTED 27**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 105/109 studies have a resolvable paper (18 none-found) |
| Manual papers picked up & used | 38 study(ies) filled from a hand-added PDF (PRJEB1563, PRJEB19322, PRJEB20799, PRJEB21277, PRJEB22252, PRJEB22890, PRJEB24082, PRJEB27256…) |
| Meaningless values dropped (preclean) | **44** cells blanked pre-fill (isolation_source 44) so the agent can recover a real value |
| Per-sample added from supplementary tables | 20 study(ies), **21228** fills from a per-isolate table (30 tables read) |
| Meaning of words improved (overwrites) | **1604** ENA cells replaced by a better table value (collection_date 658, host 1, isolation_source 945) — examples below |
| Escalation fired (close calls + big papers) | 65 decision(s) / 39 studies — close-call 18, big-decision 6, residual 38, sticky 4 |
| Extra manual tables requested | ⛔ **8** table(s) requested — PRJEB15226, PRJEB17615, PRJEB20799, PRJEB21277, PRJEB24082, PRJEB39867, PRJNA855907, PRJNA996149 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2019' → '2019-11-28 00:00:00'
- `collection_date`: '2020' → '2020-03-12 00:00:00'
- `host`: 'environmental' → 'environment_soil'
- `isolation_source`: 'Human body sites or biosamples' → 'SCALP'
- `isolation_source`: 'Human body sites or biosamples' → 'BLOOD'

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 65 decision(s) queued |
| 2 | answer | answer / answer_note | 21 answered · 44 skip (43 auto) |
| 3 | apply | escalation_applied | 9152 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 50 rows · 38 answered |
| 5 | fill | filled_metadata_provenance | 9069 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (8)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB15226 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-Genome Multilocus Sequence Typing of Extended-Spectrum](https://doi.org/10.1128/jcm.01648-16) | `manual_download_supp/PRJEB15226.xlsx` |
| PRJEB17615 | collection_date | isolation_source:0,host:0,collection_date:0 | [Integrating whole-genome sequencing within the National Anti](https://doi.org/10.1038/s41467-020-16322-5) | `manual_download_supp/PRJEB17615.xlsx` |
| PRJEB20799 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | (no link) | `manual_download_supp/PRJEB20799.xlsx` |
| PRJEB21277 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | (no link) | `manual_download_supp/PRJEB21277.xlsx` |
| PRJEB24082 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Dissemination of carbapenemase-producing <i>Enterobacterales](https://doi.org/10.1099/mgen.0.000924) | `manual_download_supp/PRJEB24082.xlsx` |
| PRJEB39867 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Surveillance and Genomic Analysis of Third-Generation Cephal](https://doi.org/10.3390/antibiotics11101286) | `manual_download_supp/PRJEB39867.xlsx` |
| PRJNA855907 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Characterization of Extensively Drug-Resistant (XDR) Carbape](https://doi.org/10.1128/spectrum.00975-22) | `manual_download_supp/PRJNA855907.xlsx` |
| PRJNA996149 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [<i>In vitro</i> activity of cefiderocol, a siderophore cepha](https://doi.org/10.1128/aac.00735-23) | `manual_download_supp/PRJNA996149.xlsx` |

### Escalate big-decision whole-field calls (>1% of cohort) — not in queue (4)

- PRJEB29740 (collection_date,isolation_source)
- PRJEB39943 (country,isolation_source)
- PRJEB42462 (collection_date)
- PRJNA604975 (collection_date)

## No paper could be found — validated, won't be recovered
3 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJEB12699, PRJEB22903, PRJEB28054

## Tables present but unjoinable (Phase-2 linkage target)
8 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJDB5929, PRJEB1563, PRJEB37378, PRJEB38289, PRJEB46513, PRJNA1087366, PRJNA767944, PRJNA804332

## Escalation status
- queue generated: 65 rows; answered: 21; applied fills: 9152.

## Zero-reason breakdown (per-sample residual)

- no_supp: 23
- NO_PMCID: 11
- field_not_in_table: 8
- abstained_other: 4
- unanchored: 1


## Per-field completeness roll-up (verbatim from completeness report)

| field | agent | v2 | gain_wf | gain_ps | gain_esc | residual | flag |
|---|---|---|---|---|---|---|---|
| country | 0.9217 | 0.8821 | 0.1352 | 0.1147 | 0.0515 | 0.0 |  |
| collection_date | 0.8585 | 0.7473 | 0.0155 | 0.2266 | 0.0656 | 0.0 |  |
| isolation_source | 0.7459 | 0.6689 | 0.0727 | 0.1679 | 0.0603 | 0.0 |  |
| host | 0.9077 | 0.7891 | 0.3944 | 0.0619 | 0.0076 | 0.0 |  |


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (38 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_train.tsv`: **65 generated · 21 answered · 0 PENDING** (9152 fills applied).

✅ All 65 escalation(s) resolved (answered or explicitly rejected).

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 21 answered decision(s) → 21 applied (study×field), 9152 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 50 ⊇ HEAD 50 rows; 0 committed decisions dropped.
- **INV3 fill** — 9152 escalation fill(s) → 9152 non-blank in filled_metadata_train. 0 lost to a blank final cell.
