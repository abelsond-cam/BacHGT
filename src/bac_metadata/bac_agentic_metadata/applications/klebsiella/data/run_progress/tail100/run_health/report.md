# Run-health report (tail100 / tail100)

## ⚠️ **5 ACTIONABLE + 13 BLOCKED outstanding — supplement & rerun**

200 (study × field) cells over 50 studies — **FILLED 164 · ACTIONABLE 5 · BLOCKED 13 · EXHAUSTED 18**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 40/50 studies have a resolvable paper (9 none-found) |
| Manual papers picked up & used | 4 study(ies) filled from a hand-added PDF (PRJEB20234, PRJEB36370, PRJNA797179, PRJNA878595) |
| Meaningless values dropped (preclean) | **93** cells blanked pre-fill (isolation_source 93) so the agent can recover a real value |
| Per-sample added from supplementary tables | 4 study(ies), **563** fills from a per-isolate table (6 tables read) |
| Meaning of words improved (overwrites) | **105** ENA cells replaced by a better table value (collection_date 105) — examples below |
| Escalation fired (close calls + big papers) | 39 decision(s) / 22 studies — close-call 4, big-decision 1, residual 34, sticky 0 |
| Extra manual tables requested | ⛔ **3** table(s) requested — PRJEB20809, PRJEB36370, PRJNA646855 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2010' → '10/08/2010'
- `collection_date`: '2011' → '27/01/2011'

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 39 decision(s) queued |
| 2 | answer | answer / answer_note | 1 answered · 38 skip (36 auto) |
| 3 | apply | escalation_applied | 184 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 50 rows · 38 answered |
| 5 | fill | filled_metadata_provenance | 184 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (3)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB20809 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-genome sequencing to investigate the prevalence and tr](https://doi.org/10.1099/mgen.0.001654) | `manual_download_supp/PRJEB20809.xlsx` |
| PRJEB36370 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Investigation of possible clonal transmission of carbapenema](https://doi.org/10.1016/j.ijantimicag.2020.105931) | `manual_download_supp/PRJEB36370.xlsx` |
| PRJNA646855 | host | isolation_source:0,host:0,collection_date:0 | [Transmission of Klebsiella strains and plasmids within and b](https://doi.org/10.1111/1462-2920.16047) | `manual_download_supp/PRJNA646855.xlsx` |

## No paper could be found — validated, won't be recovered
6 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB11378, PRJEB12888, PRJEB21132, PRJEB40861, PRJEB8667, PRJNA353728

## Tables present but unjoinable (Phase-2 linkage target)
8 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB39567, PRJEB54810, PRJEB55414, PRJEB8666, PRJNA1076808, PRJNA411762, PRJNA611540, PRJNA857533

## Escalation status
- queue generated: 39 rows; answered: 1; applied fills: 184.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 14
- no_supp: 8
- field_not_in_table: 1


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (4 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/tail100/escalation/decisions_needed.tsv`: **39 generated · 1 answered · 0 PENDING** (184 fills applied).

✅ All 39 escalation(s) resolved (answered or explicitly rejected).

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 1 answered decision(s) → 1 applied (study×field), 184 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 50 ⊇ HEAD 50 rows; 0 committed decisions dropped.
- **INV3 fill** — 184 escalation fill(s) → 184 non-blank in filled_metadata_tail100. 0 lost to a blank final cell.
