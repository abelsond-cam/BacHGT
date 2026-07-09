# Run-health report (tail25_49 / tail25_49)

## ⚠️ **22 ACTIONABLE + 24 BLOCKED outstanding — supplement & rerun**

592 (study × field) cells over 148 studies — **FILLED 486 · ACTIONABLE 22 · BLOCKED 24 · EXHAUSTED 60**. ALL CLEAR requires ACTIONABLE and BLOCKED both 0 (every cell FILLED, or EXHAUSTED with a logged reason / curator acceptance), and at least one study evaluated.

## Actionable worklist — do these, then rerun

### Fetch papers (8)

| study | fields short | already have (per-sample) | paper |
|---|---|---|---|
| PRJDB17160 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Multidrug-resistant Klebsiella pneumoniae clinical isolates ](https://doi.org/10.1016/j.jgar.2024.04.008) |
| PRJEB19808 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Expansion of KPC-producing Klebsiella pneumoniae with variou](https://doi.org/10.1016/j.ijantimicag.2017.10.011) |
| PRJEB60743 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Genotypic characterisation of carbapenemase-producing organi](https://doi.org/10.1016/j.jgar.2023.06.002) |
| PRJNA390933 | isolation_source | isolation_source:0,host:0,collection_date:0 | [Characterization of OXA-48-like carbapenemase producers in C](https://doi.org/10.1093/jac/dkx462) |
| PRJNA552385 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Coevolution of host-plasmid pairs facilitates the emergence ](https://doi.org/10.1038/s41559-020-1170-1) |
| PRJNA631924 | host | isolation_source:0,host:0,collection_date:0 | [The evolutionary trade-offs in phage-resistant Klebsiella pn](https://doi.org/10.1111/1462-2920.15476) |
| PRJNA728968 | collection_date | isolation_source:0,host:0,collection_date:0 | [Toward accurate diagnosis and surveillance of bacterial infe](https://doi.org/10.1093/bib/bbac004) |
| PRJNA814816 | isolation_source | isolation_source:0,host:0,collection_date:0 | [PCR-based ORF typing of Klebsiella pneumoniae for rapid iden](https://doi.org/10.1111/jam.15701) |

### Fetch supplementary tables (5)

| study | fields short | already have (per-sample) | paper | save as |
|---|---|---|---|---|
| PRJEB14854 | collection_date,host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Whole-genome sequencing to investigate the prevalence and tr](https://doi.org/10.1099/mgen.0.001654) | `manual_download_supp/PRJEB14854.xlsx` |
| PRJEB56212 | collection_date,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic Characterization of Multidrug-Resistant Extended Spe](https://doi.org/10.3390/microorganisms11020525) | `manual_download_supp/PRJEB56212.xlsx` |
| PRJEB6688 | collection_date,country,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic definition of hypervirulent and multidrug-resistant ](https://doi.org/10.3201/eid2011.140206) | `manual_download_supp/PRJEB6688.xlsx` |
| PRJNA1092272 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Genomic epidemiology and longitudinal sampling of ward waste](https://doi.org/10.1093/jacamr/dlae140) | `manual_download_supp/PRJNA1092272.xlsx` |
| PRJNA984451 | host,isolation_source | isolation_source:0,host:0,collection_date:0 | [Analysis of the stepwise acquisition of &lt;i&gt;bla&lt;/i&g](https://doi.org/10.1093/jacamr/dlad106) | `manual_download_supp/PRJNA984451.xlsx` |

## No paper could be found — validated, won't be recovered
14 studies have no resolvable paper (finder exhausted; EBI record only). Marked EXHAUSTED: PRJDB5317, PRJEB36919, PRJEB5132, PRJEB73547, PRJNA1092662, PRJNA278293, PRJNA292902, PRJNA527021, PRJNA563817, PRJNA739636, PRJNA744889, PRJNA842739, PRJNA857525, PRJNA986308

## Tables present but unjoinable (Phase-2 linkage target)
12 studies have a supplementary table with the fields but no joinable accession key (anchoring): PRJEB14100, PRJEB25080, PRJEB27508, PRJEB32657, PRJEB43550, PRJEB47075, PRJEB50270, PRJEB60478, PRJNA1000963, PRJNA1071125, PRJNA552297, PRJNA868296

## Escalation status
- queue generated: 0 rows; answered: 0; applied fills: 0.

## Zero-reason breakdown (per-sample residual)

- NO_PMCID: 41
- no_supp: 34
- field_not_in_table: 5
- value_check_failed: 2


---

# ⛔⛔ CURATOR SIGN-OFF — REQUIRED BEFORE THIS RUN IS TRUSTED ⛔⛔

> Two steps only a human can do. **While either is INCOMPLETE the completeness/accuracy figures above UNDERSTATE the pipeline — supplement the data and rerun.**

## 1. Manual papers downloaded & added — ⛔ INCOMPLETE

⛔ **8 studies have a real paper but NO usable full text** — download each to `find_papers/manual_download/<acc>.pdf`, then rerun:

| study | paper |
|---|---|
| PRJDB17160 | [Multidrug-resistant Klebsiella pneumoniae clinical isolates ](https://doi.org/10.1016/j.jgar.2024.04.008) |
| PRJEB19808 | [Expansion of KPC-producing Klebsiella pneumoniae with variou](https://doi.org/10.1016/j.ijantimicag.2017.10.011) |
| PRJEB60743 | [Genotypic characterisation of carbapenemase-producing organi](https://doi.org/10.1016/j.jgar.2023.06.002) |
| PRJNA390933 | [Characterization of OXA-48-like carbapenemase producers in C](https://doi.org/10.1093/jac/dkx462) |
| PRJNA552385 | [Coevolution of host-plasmid pairs facilitates the emergence ](https://doi.org/10.1038/s41559-020-1170-1) |
| PRJNA631924 | [The evolutionary trade-offs in phage-resistant Klebsiella pn](https://doi.org/10.1111/1462-2920.15476) |
| PRJNA728968 | [Toward accurate diagnosis and surveillance of bacterial infe](https://doi.org/10.1093/bib/bbac004) |
| PRJNA814816 | [PCR-based ORF typing of Klebsiella pneumoniae for rapid iden](https://doi.org/10.1111/jam.15701) |

## 2. Escalations answered (tight grading questions) — ✅ COMPLETE

Queue `study_lv_attributes/escalation/decisions_needed_tail25_49.tsv`: **0 generated · 0 answered · 0 PENDING** (0 fills applied).

✅ No tight-grading escalations were raised.

# → ⛔ CURATOR ACTION OUTSTANDING — 8 paper(s) to add, 0 escalation(s) to answer

