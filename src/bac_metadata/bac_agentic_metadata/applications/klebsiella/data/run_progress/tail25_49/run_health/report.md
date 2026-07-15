# Run-health report (tail25_49 / tail25_49)

## ⚠️ **11 ACTIONABLE + 25 BLOCKED outstanding — supplement & rerun**

592 (study × field) cells over 148 studies — **FILLED 496 · ACTIONABLE 11 · BLOCKED 25 · EXHAUSTED 60**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 121/148 studies have a resolvable paper (27 none-found) |
| Manual papers picked up & used | 8 study(ies) filled from a hand-added PDF (PRJDB17160, PRJEB19808, PRJEB60743, PRJNA390933, PRJNA552385, PRJNA631924, PRJNA728968, PRJNA814816) |
| Meaningless values dropped (preclean) | **104** cells blanked pre-fill (host 46, isolation_source 58) so the agent can recover a real value |
| Per-sample added from supplementary tables | 14 study(ies), **626** fills from a per-isolate table (24 tables read) |
| Meaning of words improved (overwrites) | **213** ENA cells replaced by a better table value (collection_date 142, country 16, isolation_source 55) — examples below |
| Escalation fired (close calls + big papers) | 0 decision(s) / 0 studies — close-call 0, big-decision 0, residual 0, sticky 0 |
| Extra manual tables requested | ⛔ **5** table(s) requested — PRJEB14854, PRJEB44852, PRJEB56212, PRJEB6688, PRJNA1092272 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2019' → '2019-10-15'
- `collection_date`: '2019' → '2019-09-20'
- `country`: 'Switzerland' → 'Australia'
- `country`: 'Switzerland' → 'UAE'
- `isolation_source`: 'sewage' → 'Municipal Wastewater'
- `isolation_source`: 'sewage' → 'Hospital Sewage'

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 0 decision(s) queued |
| 2 | answer | answer / answer_note | 0 answered · 0 skip (0 auto) |
| 3 | apply | escalation_applied | 0 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 50 rows · 38 answered |
| 5 | fill | filled_metadata_provenance | 0 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (5)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB14854 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-genome sequencing to investigate the prevalence and tr](https://doi.org/10.1099/mgen.0.001654) | `manual_download_supp/PRJEB14854.xlsx` |
| PRJEB44852 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Diversity of carbapenem-resistant Klebsiella pneumoniae ST14](https://doi.org/10.1007/s10096-021-04384-2) | `manual_download_supp/PRJEB44852.xlsx` |
| PRJEB56212 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic Characterization of Multidrug-Resistant Extended Spe](https://doi.org/10.3390/microorganisms11020525) | `manual_download_supp/PRJEB56212.xlsx` |
| PRJEB6688 | country,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic definition of hypervirulent and multidrug-resistant ](https://doi.org/10.3201/eid2011.140206) | `manual_download_supp/PRJEB6688.xlsx` |
| PRJNA1092272 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic epidemiology and longitudinal sampling of ward waste](https://doi.org/10.1093/jacamr/dlae140) | `manual_download_supp/PRJNA1092272.xlsx` |

## No paper could be found — validated, won't be recovered
15 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB5317, PRJEB36919, PRJEB5132, PRJEB73547, PRJNA1092662, PRJNA278293, PRJNA292902, PRJNA527021, PRJNA563817, PRJNA739636, PRJNA744889, PRJNA842739, PRJNA857525, PRJNA858823, PRJNA986308

## Tables present but unjoinable (Phase-2 linkage target)
11 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB14100, PRJEB25080, PRJEB27508, PRJEB32657, PRJEB47075, PRJEB50270, PRJEB60478, PRJNA1000963, PRJNA1071125, PRJNA552297, PRJNA868296

## Escalation status
- queue generated: 0 rows; answered: 0; applied fills: 0.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 34
- no_supp: 32
- field_not_in_table: 4
- abstained_other: 1


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (8 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/tail25_49/escalation/decisions_needed.tsv`: **0 generated · 0 answered · 0 PENDING** (0 fills applied).

✅ No tight-grading escalations were raised.

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 0 answered decision(s) → 0 applied (study×field), 0 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 50 ⊇ HEAD 50 rows; 0 committed decisions dropped.
- **INV3 fill** — 0 escalation fill(s) → 0 non-blank in filled_metadata_tail25_49. 0 lost to a blank final cell.
