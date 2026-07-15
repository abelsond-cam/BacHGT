# Run-health report (test / test)

## ⚠️ **2 ACTIONABLE + 0 BLOCKED outstanding — supplement & rerun**

188 (study × field) cells over 47 studies — **FILLED 174 · ACTIONABLE 2 · BLOCKED 0 · EXHAUSTED 12**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 43/47 studies have a resolvable paper (17 none-found) |
| Manual papers picked up & used | 17 study(ies) filled from a hand-added PDF (PRJEB27342, PRJEB29424, PRJEB29738, PRJEB32655, PRJEB38540, PRJEB48268, PRJEB63349, PRJNA306133…) |
| Meaningless values dropped (preclean) | **198** cells blanked pre-fill (isolation_source 198) so the agent can recover a real value |
| Per-sample added from supplementary tables | 16 study(ies), **13820** fills from a per-isolate table (21 tables read) |
| Meaning of words improved (overwrites) | **1041** ENA cells replaced by a better table value (collection_date 106, isolation_source 935) — examples below |
| Escalation fired (close calls + big papers) | 36 decision(s) / 19 studies — close-call 9, big-decision 5, residual 16, sticky 7 |
| Extra manual tables requested | ⛔ **1** table(s) requested — PRJEB29424 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '1800/2014' → '2007'
- `collection_date`: '2018' → '2018-12-17 00:00:00'
- `isolation_source`: 'chicken meat' → 'chicken thighs'
- `isolation_source`: 'chicken meat' → 'chicken thighs'

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 36 decision(s) queued |
| 2 | answer | answer / answer_note | 13 answered · 23 skip (15 auto) |
| 3 | apply | escalation_applied | 15900 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 50 rows · 38 answered |
| 5 | fill | filled_metadata_provenance | 12288 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (1)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB29424 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | (no link) | `manual_download_supp/PRJEB29424.xlsx` |

## No paper could be found — validated, won't be recovered
3 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJEB19226, PRJEB21081, PRJEB53835

## Escalation status
- queue generated: 36 rows; answered: 13; applied fills: 15900.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 7
- no_supp: 3
- abstained_other: 2
- unanchored: 1
- field_not_in_table: 1


## Per-field completeness roll-up (verbatim from completeness report)

| field | agent | v2 | gain_wf | gain_ps | gain_esc | residual | flag |
|---|---|---|---|---|---|---|---|
| country | 0.9591 | 0.8477 | 0.1227 | 0.0 | 0.1713 | 0.0 |  |
| collection_date | 0.9359 | 0.7636 | 0.027 | 0.1051 | 0.1602 | 0.0 |  |
| isolation_source | 0.7417 | 0.7016 | 0.0022 | 0.1266 | 0.0115 | 0.0 |  |
| host | 0.8356 | 0.7655 | 0.1481 | 0.1214 | 0.0353 | 0.0 |  |


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (17 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/test/escalation/decisions_needed.tsv`: **36 generated · 13 answered · 0 PENDING** (15900 fills applied).

✅ All 36 escalation(s) resolved (answered or explicitly rejected).

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 13 answered decision(s) → 13 applied (study×field), 15900 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 50 ⊇ HEAD 50 rows; 0 committed decisions dropped.
- **INV3 fill** — 15900 escalation fill(s) → 15900 non-blank in filled_metadata_test. 0 lost to a blank final cell.
