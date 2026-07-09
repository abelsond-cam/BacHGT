# Run-health report (tail100 / tail100)

## ⚠️ **7 ACTIONABLE + 11 BLOCKED outstanding — supplement & rerun**

200 (study × field) cells over 50 studies — **FILLED 159 · ACTIONABLE 7 · BLOCKED 11 · EXHAUSTED 23**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Actionable worklist — do these, then rerun

### Fetch supplementary tables (5)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJDB6407 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Plasmid analysis of NDM metallo-β-lactamase-producing Entero](https://doi.org/10.1371/journal.pone.0231119) | `manual_download_supp/PRJDB6407.xlsx` |
| PRJEB20809 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-genome sequencing to investigate the prevalence and tr](https://doi.org/10.1099/mgen.0.001654) | `manual_download_supp/PRJEB20809.xlsx` |
| PRJEB39567 | isolation_source | isolation_source:0,host:0,collection_date:0 | [High frequency body site translocation of nosocomial Pseudom](https://doi.org/10.1038/s41467-025-66088-x) | `manual_download_supp/PRJEB39567.xlsx` |
| PRJNA1076808 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic surveillance of multidrug-resistant organisms based ](https://doi.org/10.1186/s13073-024-01412-6) | `manual_download_supp/PRJNA1076808.xlsx` |
| PRJNA675776 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Comparative phylogenomics of ESBL-, AmpC- and carbapenemase-](https://doi.org/10.1093/jac/dkac041) | `manual_download_supp/PRJNA675776.xlsx` |

## No paper could be found — validated, won't be recovered
6 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB11378, PRJEB12888, PRJEB21132, PRJEB40861, PRJEB8667, PRJNA353728

## Tables present but unjoinable (Phase-2 linkage target)
6 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB54810, PRJEB55414, PRJEB8666, PRJNA411762, PRJNA611540, PRJNA857533

## Escalation status
- queue generated: 3 rows; answered: 1; applied fills: 184.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 16
- no_supp: 11
- field_not_in_table: 3


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ✅ COMPLETE

✅ No outstanding downloads — every findable paper has full text (4 via a manually-added PDF).

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_tail100.tsv`: **3 generated · 1 answered · 0 PENDING** (184 fills applied).

✅ All 3 escalation(s) resolved (answered or explicitly rejected).

# → ✅ CURATOR SIGN-OFF COMPLETE — both human steps done

