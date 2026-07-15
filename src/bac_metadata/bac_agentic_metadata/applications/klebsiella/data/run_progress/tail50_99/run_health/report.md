# Run-health report (tail50_99 / tail50_99)

## ⚠️ **10 ACTIONABLE + 10 BLOCKED outstanding — supplement & rerun**

380 (study × field) cells over 95 studies — **FILLED 336 · ACTIONABLE 10 · BLOCKED 10 · EXHAUSTED 24**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 78/95 studies have a resolvable paper (17 none-found) |
| Manual papers picked up & used | 7 study(ies) filled from a hand-added PDF (PRJDB8311, PRJEB43945, PRJEB50277, PRJEB59403, PRJNA1061342, PRJNA342893, PRJNA643814) |
| Meaningless values dropped (preclean) | **101** cells blanked pre-fill (isolation_source 101) so the agent can recover a real value |
| Per-sample added from supplementary tables | 13 study(ies), **1424** fills from a per-isolate table (18 tables read) |
| Meaning of words improved (overwrites) | **74** ENA cells replaced by a better table value (collection_date 1, isolation_source 73) — examples below |
| Escalation fired (close calls + big papers) | 38 decision(s) / 26 studies — close-call 4, big-decision 0, residual 33, sticky 1 |
| Extra manual tables requested | ⛔ **5** table(s) requested — PRJEB2655, PRJEB43945, PRJNA1061342, PRJNA237670, PRJNA918858 (see the actionable worklist) |

**Overwrite examples — a supplementary-table value replaced a GENUINE deposited ENA value (surfaced for review). Every overwrite is now VETTED: collection_date only overwrites with a strictly more specific date (deterministic), country/isolation_source/host only when the agentic fidelity judge rules the table a real improvement — on every field, gated or not. A still-suspicious value here (truncation, a lateral date) is a table-parse defect to chase:**

- `collection_date`: '2019-05' → '2019-05-01 00:00:00'
- `isolation_source`: 'Food' → 'Cheese stored day 0'
- `isolation_source`: 'Food' → 'Cheese stored day 4 (8°C)'

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 38 decision(s) queued |
| 2 | answer | answer / answer_note | 4 answered · 34 skip (34 auto) |
| 3 | apply | escalation_applied | 263 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 53 rows · 41 answered |
| 5 | fill | filled_metadata_provenance | 263 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (5)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB2655 | collection_date,country,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [A genomic portrait of the emergence, evolution, and global s](https://doi.org/10.1101/gr.147710.112) | `manual_download_supp/PRJEB2655.xlsx` |
| PRJEB43945 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Pan-pathogen deep sequencing of nosocomial bacterial pathoge](https://doi.org/10.1016/S2666-5247(24)00113-7) | `manual_download_supp/PRJEB43945.xlsx` |
| PRJNA1061342 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Expansion and transmission dynamics of high risk carbapenem-](https://doi.org/10.1016/j.drup.2024.101083) | `manual_download_supp/PRJNA1061342.xlsx` |
| PRJNA237670 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Molecular dissection of the evolution of carbapenem-resistan](https://doi.org/10.1073/pnas.1321364111) | `manual_download_supp/PRJNA237670.xlsx` |
| PRJNA918858 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Heteroresistance to Colistin in Clinical Isolates of <i>Kleb](https://doi.org/10.3390/antibiotics12071111) | `manual_download_supp/PRJNA918858.xlsx` |

## No paper could be found — validated, won't be recovered
8 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB4948, PRJEB26075, PRJEB28115, PRJEB45369, PRJEB50346, PRJEB5495, PRJNA1026096, PRJNA329105

## Tables present but unjoinable (Phase-2 linkage target)
7 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB78367, PRJEB7967, PRJEB8265, PRJNA1050414, PRJNA231221, PRJNA259658, PRJNA970254

## Escalation status
- queue generated: 38 rows; answered: 4; applied fills: 263.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 18
- no_supp: 13
- abstained_other: 2
- field_not_in_table: 1


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (7 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/tail50_99/escalation/decisions_needed.tsv`: **38 generated · 4 answered · 0 PENDING** (263 fills applied).

✅ All 38 escalation(s) resolved (answered or explicitly rejected).

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

