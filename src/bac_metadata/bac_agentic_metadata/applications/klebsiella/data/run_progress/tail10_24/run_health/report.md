# Run-health report (tail10_24 / tail10_24)

## ⚠️ **4 ACTIONABLE + 50 BLOCKED outstanding — supplement & rerun**

856 (study × field) cells over 214 studies — **FILLED 671 · ACTIONABLE 4 · BLOCKED 50 · EXHAUSTED 131**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 159/214 studies have a resolvable paper (54 none-found) |
| Manual papers picked up & used | 17 study(ies) filled from a hand-added PDF (PRJDB10735, PRJEB15325, PRJEB18733, PRJEB27344, PRJEB27707, PRJEB42167, PRJEB42426, PRJNA1047501…) |
| Meaningless values dropped (preclean) | **149** cells blanked pre-fill (host 10, isolation_source 139) so the agent can recover a real value |
| Per-sample added from supplementary tables | 10 study(ies), **227** fills from a per-isolate table (25 tables read) |
| Meaning of words improved (overwrites) | **28** ENA cells replaced by a better table value (collection_date 2, isolation_source 26) — examples below |
| Escalation fired (close calls + big papers) | 0 decision(s) / 0 studies — close-call 0, big-decision 0, residual 0, sticky 0 |
| Extra manual tables requested | ⛔ **1** table(s) requested — PRJEB15325 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2019' → '2020-08-01 00:00:00'
- `collection_date`: '2019' → '2020-08-01 00:00:00'
- `isolation_source`: 'clinical sample' → 'catheter'
- `isolation_source`: 'clinical sample' → 'rectal'

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

### Fetch supplementary tables (1)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB15325 | collection_date,country,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Metabolic diversity of the emerging pathogenic lineages of K](https://doi.org/10.1111/1462-2920.13689) | `manual_download_supp/PRJEB15325.xlsx` |

## No paper could be found — validated, won't be recovered
34 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB4867, PRJEB1730, PRJEB24612, PRJEB25682, PRJEB29106, PRJEB3226, PRJEB38650, PRJEB7657, PRJNA1026663, PRJNA1057737, PRJNA356346, PRJNA437215, PRJNA438157, PRJNA451051, PRJNA508510, PRJNA523429, PRJNA523433, PRJNA523709, PRJNA590288, PRJNA635420, PRJNA640134, PRJNA647793, PRJNA685215, PRJNA701285, PRJNA701733, PRJNA719104, PRJNA720499, PRJNA739639, PRJNA776891, PRJNA823356, PRJNA833742, PRJNA835887, PRJNA857878, PRJNA949542

## Tables present but unjoinable (Phase-2 linkage target)
28 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB12817, PRJEB20357, PRJEB22139, PRJEB31347, PRJEB35018, PRJEB45397, PRJEB52158, PRJEB58695, PRJEB70314, PRJEB70897, PRJNA1000742, PRJNA1016138, PRJNA1031934, PRJNA1136145, PRJNA279496, PRJNA396729, PRJNA670748, PRJNA729628, PRJNA741866, PRJNA799444, PRJNA865026, PRJNA906139, PRJNA947477, PRJNA952961, PRJNA956822, PRJNA984017, PRJNA986550, PRJNA994484

## Escalation status
- queue generated: 0 rows; answered: 0; applied fills: 0.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 92
- no_supp: 37
- abstained_other: 3
- field_not_in_table: 3


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (17 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/tail10_24/escalation/decisions_needed.tsv`: **0 generated · 0 answered · 0 PENDING** (0 fills applied).

✅ No tight-grading escalations were raised.

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 0 answered decision(s) → 0 applied (study×field), 0 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 50 ⊇ HEAD 50 rows; 0 committed decisions dropped.
- **INV3 fill** — 0 escalation fill(s) → 0 non-blank in filled_metadata_tail10_24. 0 lost to a blank final cell.
