# Run-health report (mabs_all / mabs_all)

## ⚠️ **6 ACTIONABLE + 31 BLOCKED outstanding — supplement & rerun**

465 (study × field) cells over 93 studies — **FILLED 180 · ACTIONABLE 6 · BLOCKED 31 · EXHAUSTED 248**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Pipeline self-audit — every silent-fail-prone step, explicitly accounted

Each row is a step that has, at some point, failed *silently*; here it is accounted for with counts from this run's own artifacts (so it holds on any run, including unlabelled / no-gold). A green summary above is not enough — these are the checks that a paper, table, drop, or decision was not quietly lost.

| step | result |
|---|---|
| Papers found | 42/93 studies have a resolvable paper (50 none-found) |
| Manual papers picked up & used | 0 study(ies) filled from a hand-added PDF |
| Meaningless values dropped (preclean) | **24** cells blanked pre-fill (isolation_source 24) so the agent can recover a real value |
| Per-sample added from supplementary tables | 0 study(ies), **0** fills from a per-isolate table (0 tables read) |
| Meaning of words improved (overwrites) | 0 — no deposited ENA value was overwritten (fidelity guard kept every one) |
| Escalation fired (close calls + big papers) | 0 decision(s) / 0 studies — close-call 0, big-decision 0, residual 0, sticky 0 |
| Extra manual tables requested | **none required** ✅ |

## Escalation-conservation chain — the five links a curator answer travels

Every past silent-drop bug hid at a *different* link. This report **counts** each link from the run's artifacts; it does **not** prove an individual answer survived apply→master→final. **Run `verify_escalation_conservation.py` to CONFIRM links 3–5 (apply · master-preserve · fill) — it hard-fails on any lost answer and stamps its verdict back into this report.**

| # | link | artifact | count |
|---|---|---|---|
| 1 | detect | decisions_needed | 0 decision(s) queued |
| 2 | answer | answer / answer_note | 0 answered · 0 skip (0 auto) |
| 3 | apply | escalation_applied | 2131 per-sample fill(s) |
| 4 | accumulate | curated_escalations (master) | 4 rows · 2 answered |
| 5 | fill | filled_metadata_provenance | 0 cell(s) reached final via curator_escalation |

> ⚠️ Counts are *necessary, not sufficient*. A non-zero row at each link does not prove the SAME answers flowed through — only the conservation gate traces them individually.

## Actionable worklist — do these, then rerun

### Fetch papers (3)

| study | fields short | already have (per-sample) | paper |
|---|---|---|---|
| PRJEB38893 | cf_status,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Mutations in Genes Encoding 23S rRNA and FadD32 May be Assoc](https://doi.org/10.1089/mdr.2022.0068) |
| PRJNA1236821 | collection_date | isolation_source:0,host:0,collection_date:0 | [Phylogenomic and Clinical Perspectives of an East Asia-Speci](https://doi.org/10.1016/j.chest.2026.04.011) |
| PRJNA840944 | cf_status,isolation_source | isolation_source:0,host:0,collection_date:0 | [Biotin-dependent cell envelope remodelling is required for M](https://doi.org/10.1038/s41564-022-01307-5) |

## No paper could be found — validated, won't be recovered
50 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB2099, PRJDB2362, PRJEB19845, PRJEB33804, PRJEB64488, PRJEB85433, PRJNA1019825, PRJNA1040155, PRJNA1136428, PRJNA1169681, PRJNA1215975, PRJNA1215977, PRJNA1238535, PRJNA191785, PRJNA191787, PRJNA191788, PRJNA191789, PRJNA203565, PRJNA203566, PRJNA203567, PRJNA203569, PRJNA203570, PRJNA203571, PRJNA203572, PRJNA297030, PRJNA401495, PRJNA65139, PRJNA65143, PRJNA65145, PRJNA65147, PRJNA65149, PRJNA65153, PRJNA65155, PRJNA65157, PRJNA65161, PRJNA65169, PRJNA65187, PRJNA65193, PRJNA65197, PRJNA65203, PRJNA65205, PRJNA65207, PRJNA65209, PRJNA65213, PRJNA656566, PRJNA698640, PRJNA698643, PRJNA734948, PRJNA867543, PRJNA996741

## Tables present but unjoinable (Phase-2 linkage target)
11 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB50291, PRJEB74244, PRJNA231221, PRJNA323571, PRJNA347845, PRJNA65137, PRJNA65151, PRJNA65191, PRJNA65199, PRJNA823663, PRJNA865308

## Escalation status
- queue generated: 0 rows; answered: 0; applied fills: 2131.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 198
- no_supp: 56


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ⛔ INCOMPLETE

⛔ **3 studies have a real paper but NO usable full text** — download each to `find_papers/manual_download/<acc>.pdf`, then rerun:

| study | paper |
|---|---|
| PRJEB38893 | [Mutations in Genes Encoding 23S rRNA and FadD32 May be Assoc](https://doi.org/10.1089/mdr.2022.0068) |
| PRJNA1236821 | [Phylogenomic and Clinical Perspectives of an East Asia-Speci](https://doi.org/10.1016/j.chest.2026.04.011) |
| PRJNA840944 | [Biotin-dependent cell envelope remodelling is required for M](https://doi.org/10.1038/s41564-022-01307-5) |

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `run_progress/mabs_all/escalation/decisions_needed.tsv`: **0 generated · 0 answered · 0 PENDING** (2131 fills applied).

✅ No tight-grading escalations were raised.

# → ⛔ CURATOR ACTION OUTSTANDING — 3 paper(s) to add, 0 escalation(s) to answer

---

<!-- ESCALATION-CONSERVATION -->
## ✅ Escalation conservation VERIFIED — links 3–5 confirmed

`verify_escalation_conservation.py` traced every curator decision through apply → master → final and found none lost:

- **INV1 apply** — 0 answered decision(s) → 0 applied (study×field), 0 per-sample fills. 0 unapplied.
- **INV2 master-preserve** — curated_escalations disk 28 ⊇ HEAD 4 rows; 0 committed decisions dropped.
- **INV3 fill** — 0 escalation fill(s) → 0 non-blank in filled_metadata_mabs_all. 0 lost to a blank final cell.
