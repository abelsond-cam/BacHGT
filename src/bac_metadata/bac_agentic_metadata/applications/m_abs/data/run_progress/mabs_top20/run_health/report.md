# Run-health report (mabs_top20 / mabs_top20)

## ⚠️ **15 ACTIONABLE + 0 BLOCKED outstanding — supplement & rerun**

100 (study × field) cells over 20 studies — **FILLED 84 · ACTIONABLE 15 · BLOCKED 0 · EXHAUSTED 1**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 19/20 studies have a resolvable paper (1 none-found) |
| Manual papers picked up & used | 11 study(ies) filled from a hand-added PDF (PRJDB10333, PRJDB10566, PRJEB14002, PRJEB31559, PRJEB39129, PRJEB44160, PRJEB7058, PRJNA1036625…) |
| Meaningless values dropped (preclean) | **175** cells blanked pre-fill (cf_status 143, isolation_source 32) so the agent can recover a real value |
| Per-sample added from supplementary tables | 3 study(ies), **935** fills from a per-isolate table (4 tables read) |
| Meaning of words improved (overwrites) | **68** ENA cells replaced by a better table value (collection_date 68) — examples below |
| Escalation fired (close calls + big papers) | 18 decision(s) / 10 studies — close-call 4, big-decision 17, residual 1, sticky 0 |
| Extra manual tables requested | ⛔ **1** table(s) requested — PRJEB2779 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2019' → '2019-12-23 00:00:00'
- `collection_date`: '2019' → '2019-08-13 00:00:00'

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 18 decision(s) queued |
| 2 | answer | answer / answer_note | 2 answered · 16 skip (0 auto) |
| 3 | apply | escalation_applied | 1781 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 4 rows · 2 answered |
| 5 | fill | filled_metadata_provenance | 1757 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (1)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB2779 | cf_status | isolation_source:0,host:0,collection_date:0 | [Emergence and spread of a human-transmissible multidrug-resi](https://doi.org/10.1126/science.aaf8156) | `manual_download_supp/PRJEB2779.xlsx` |

### Answer escalations (10)

- PRJDB10333 (collection_date)
- PRJEB14002 (collection_date)
- PRJEB2779 (collection_date,country)
- PRJEB44160 (cf_status,collection_date,isolation_source)
- PRJNA1036625 (cf_status)
- PRJNA1165220 (cf_status,isolation_source)
- PRJNA401515 (cf_status)
- PRJNA420644 (cf_status)
- PRJNA941035 (cf_status)
- PRJNA989271 (cf_status)

## Escalation status
- queue generated: 18 rows; answered: 2; applied fills: 1781.

## Zero-reason breakdown (per-sample residual)

- no_supp: 11
- field_not_in_table: 2
- unanchored: 2
- NO_PMCID: 1


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (11 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ⛔ INCOMPLETE

Queue `run_progress/mabs_top20/escalation/decisions_needed.tsv`: **18 generated · 2 answered · 14 PENDING** (1781 fills applied).

⛔ **14 tight-grading decision(s) are UNANSWERED.** Fill the `answer` column (a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.

# → ⛔ CURATOR ACTION OUTSTANDING — 0 paper(s) to add, 14 escalation(s) to answer

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 2 answered decision(s) → 2 applied (study×field), 1781 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 4 rows (no HEAD baseline); 0 committed decisions dropped.
- **INV3 fill** — 1781 escalation fill(s) → 1781 non-blank in filled_metadata_mabs_top20. 0 lost to a blank final cell.
