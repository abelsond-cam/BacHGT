# Run-health report (tail50_99 / tail50_99)

## ⚠️ **22 ACTIONABLE + 11 BLOCKED outstanding — supplement & rerun**

380 (study × field) cells over 95 studies — **FILLED 324 · ACTIONABLE 22 · BLOCKED 11 · EXHAUSTED 23**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Actionable worklist — do these, then rerun

### Fetch papers (7)

| study | fields short | already have (per-sample) | paper |
|---|---|---|---|
| PRJDB8311 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Comparison between IMP carbapenemase-producing Enterobacteri](https://doi.org/10.1093/jac/dkz501) |
| PRJEB43945 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Pan-pathogen deep sequencing of nosocomial bacterial pathoge](https://doi.org/10.1016/S2666-5247(24)00113-7) |
| PRJEB50277 | isolation_source | isolation_source:0,host:0,collection_date:0 | [The first nationwide surveillance of carbapenem-resistant En](https://doi.org/10.1016/j.ijid.2022.04.034) |
| PRJEB59403 | host | isolation_source:0,host:0,collection_date:0 | [Carbapenemase-producing Gram-negative bacteria in hospital w](https://doi.org/10.1016/j.scitotenv.2023.164179) |
| PRJNA1061342 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Expansion and transmission dynamics of high risk carbapenem-](https://doi.org/10.1016/j.drup.2024.101083) |
| PRJNA342893 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Clinical and Molecular Epidemiology of Carbapenem-Resistant ](https://doi.org/10.1093/cid/cix113) |
| PRJNA643814 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Prolonged outbreak of New Delhi metallo-beta-lactamase-produ](https://doi.org/10.2807/1560-7917.ES.2020.25.7.2000080) |

### Fetch supplementary tables (7)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB2655 | collection_date,country,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [A genomic portrait of the emergence, evolution, and global s](https://doi.org/10.1101/gr.147710.112) | `manual_download_supp/PRJEB2655.xlsx` |
| PRJEB42526 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [One Health Genomic Study of Human and Animal <i>Klebsiella p](https://doi.org/10.3390/antibiotics11010042) | `manual_download_supp/PRJEB42526.xlsx` |
| PRJEB66360 | host | isolation_source:0,host:0,collection_date:0 | [Heteroresistance to colistin in wild-type &lt;i&gt;Klebsiell](https://doi.org/10.1128/spectrum.02238-23) | `manual_download_supp/PRJEB66360.xlsx` |
| PRJNA237670 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Molecular dissection of the evolution of carbapenem-resistan](https://doi.org/10.1073/pnas.1321364111) | `manual_download_supp/PRJNA237670.xlsx` |
| PRJNA605147 | host | isolation_source:0,host:0,collection_date:0 | [Niche and local geography shape the pangenome of wastewater-](https://doi.org/10.1126/sciadv.abe3868) | `manual_download_supp/PRJNA605147.xlsx` |
| PRJNA701073 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Oral fosfomycin activity against Klebsiella pneumoniae in a ](https://doi.org/10.1093/jac/dkac045) | `manual_download_supp/PRJNA701073.xlsx` |
| PRJNA918858 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Heteroresistance to Colistin in Clinical Isolates of <i>Kleb](https://doi.org/10.3390/antibiotics12071111) | `manual_download_supp/PRJNA918858.xlsx` |

## No paper could be found — validated, won't be recovered
8 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB4948, PRJEB26075, PRJEB28115, PRJEB45369, PRJEB50346, PRJEB5495, PRJNA1026096, PRJNA329105

## Tables present but unjoinable (Phase-2 linkage target)
7 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB78367, PRJEB7967, PRJEB8265, PRJNA1050414, PRJNA231221, PRJNA259658, PRJNA970254

## Escalation status
- queue generated: 4 rows; answered: 4; applied fills: 299.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 20
- no_supp: 20
- field_not_in_table: 5


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ⛔ INCOMPLETE

⛔ **7 studies have a real paper but NO usable full text** — download each to `find_papers/manual_download/<acc>.pdf`, then rerun:

| study | paper |
|---|---|
| PRJDB8311 | [Comparison between IMP carbapenemase-producing Enterobacteri](https://doi.org/10.1093/jac/dkz501) |
| PRJEB43945 | [Pan-pathogen deep sequencing of nosocomial bacterial pathoge](https://doi.org/10.1016/S2666-5247(24)00113-7) |
| PRJEB50277 | [The first nationwide surveillance of carbapenem-resistant En](https://doi.org/10.1016/j.ijid.2022.04.034) |
| PRJEB59403 | [Carbapenemase-producing Gram-negative bacteria in hospital w](https://doi.org/10.1016/j.scitotenv.2023.164179) |
| PRJNA1061342 | [Expansion and transmission dynamics of high risk carbapenem-](https://doi.org/10.1016/j.drup.2024.101083) |
| PRJNA342893 | [Clinical and Molecular Epidemiology of Carbapenem-Resistant ](https://doi.org/10.1093/cid/cix113) |
| PRJNA643814 | [Prolonged outbreak of New Delhi metallo-beta-lactamase-produ](https://doi.org/10.2807/1560-7917.ES.2020.25.7.2000080) |

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_tail50_99.tsv`: **4 generated · 4 answered · 0 PENDING** (299 fills applied).

✅ All 4 escalation(s) resolved (answered or explicitly rejected).

# → ⛔ CURATOR ACTION OUTSTANDING — 7 paper(s) to add, 0 escalation(s) to answer

