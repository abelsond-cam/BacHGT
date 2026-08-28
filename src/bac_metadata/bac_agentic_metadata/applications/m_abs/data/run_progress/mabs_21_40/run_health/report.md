# Run-health report (mabs_21_40 / mabs_21_40)

## ⚠️ **12 ACTIONABLE + 3 BLOCKED outstanding — supplement & rerun**

100 (study × field) cells over 20 studies — **FILLED 69 · ACTIONABLE 12 · BLOCKED 3 · EXHAUSTED 16**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 17/20 studies have a resolvable paper (3 none-found) |
| Manual papers picked up & used | 1 study(ies) filled from a hand-added PDF (PRJNA1080355) |
| Meaningless values dropped (preclean) | **77** cells blanked pre-fill (isolation_source 77) so the agent can recover a real value |
| Per-sample added from supplementary tables | 2 study(ies), **34** fills from a per-isolate table (3 tables read) |
| Meaning of words improved (overwrites) | 0 — no deposited ENA value was overwritten (fidelity guard kept every one) |
| Escalation fired (close calls + big papers) | 10 decision(s) / 4 studies — close-call 0, big-decision 3, residual 7, sticky 0 |
| Extra manual tables requested | ⛔ **2** table(s) requested — PRJEB6776, PRJNA315990 (see the actionable worklist) |

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 10 decision(s) queued |
| 2 | answer | answer / answer_note | 0 answered · 10 skip (0 auto) |
| 3 | apply | escalation_applied | 0 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 4 rows · 2 answered |
| 5 | fill | filled_metadata_provenance | 0 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (2)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB6776 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-genome sequencing and epidemiological analysis do not ](https://doi.org/10.1093/cid/ciu967) | `manual_download_supp/PRJEB6776.xlsx` |
| PRJNA315990 | cf_status,isolation_source | isolation_source:0,host:0,collection_date:0 | [Complete Genome Sequences of 17 Rapidly Growing Nontuberculo](https://doi.org/10.1128/genomea.01009-16) | `manual_download_supp/PRJNA315990.xlsx` |

### Answer escalations (4)

- PRJDB13427 (collection_date)
- PRJEB36331 (cf_status,collection_date,country,host,isolation_source)
- PRJEB61124 (cf_status)
- PRJNA523365 (isolation_source)

## No paper could be found — validated, won't be recovered
1 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJNA353361

## Tables present but unjoinable (Phase-2 linkage target)
2 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJNA1051626, PRJNA718117

## Escalation status
- queue generated: 10 rows; answered: 0; applied fills: 0.

## Zero-reason breakdown (per-sample residual)

- no_supp: 15
- NO_PMCID: 12
- field_not_in_table: 1


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (1 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ⛔ INCOMPLETE

Queue `run_progress/mabs_21_40/escalation/decisions_needed.tsv`: **10 generated · 0 answered · 10 PENDING** (0 fills applied).

⛔ **10 tight-grading decision(s) are UNANSWERED.** Fill the `answer` column (a blank answer = not decided; a reject/skip note counts as resolved) and rerun `--apply`.

# → ⛔ CURATOR ACTION OUTSTANDING — 0 paper(s) to add, 10 escalation(s) to answer

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 0 answered decision(s) → 0 applied (study×field), 0 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 4 rows (no HEAD baseline); 0 committed decisions dropped.
- **INV3 fill** — 0 escalation fill(s) → 0 non-blank in filled_metadata_mabs_21_40. 0 lost to a blank final cell.
