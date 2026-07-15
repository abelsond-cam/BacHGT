# Per-sample supplementary worklist — which studies need a manual supp-table fetch

22 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJEB36370 | 206 | collection_date,isolation_source | NO_PMCID | yes | collection_date | Table 2 (main text) and Supplementary Ta | local_pdf | `PRJEB36370.xlsx` |
| OA_INVESTIGATE | PRJEB20809 | 222 | collection_date,isolation_source | no_supp | yes | isolation_source,host,collection_date | Supplementary Table S1 | europepmc_fulltext / PMC13148723 | `PRJEB20809.xlsx` |
| OA_INVESTIGATE | PRJEB8666 | 212 | collection_date,country | unanchored | likely | collection_date,isolation_source | online supplemental table 2 (bmjgh-2021- | europepmc_fulltext / PMC8330565 | `PRJEB8666.xlsx` |
| OA_INVESTIGATE | PRJEB55414 | 189 | collection_date,isolation_source | unanchored | yes | isolation_source,collection_date | Table S1 (https://doi.org/10.6084/m9.fig | europepmc_fulltext / PMC10434048 | `PRJEB55414.xlsx` |
| OA_INVESTIGATE | PRJNA611540 | 112 | host | unanchored | likely | isolation_source | Table S5 (Supplemental file 1) | europepmc_fulltext / PMC7688209 | `PRJNA611540.xlsx` |
| OA_INVESTIGATE | PRJNA646855 | 105 | host | no_supp | yes | isolation_source,host,collection_date | Table S1 | europepmc_fulltext | `PRJNA646855.xlsx` |
| OA_INVESTIGATE | PRJNA411762 | 93 | host | unanchored | yes | isolation_source,host,collection_date | Table 1 (main text) | europepmc_fulltext / PMC6535554 | `PRJNA411762.xlsx` |
| OA_PARTIAL | PRJEB50545 | 100 | isolation_source | direct | yes | isolation_source,host,collection_date | S1 Table (XLSX) | europepmc_fulltext / PMC12779062 | `PRJEB50545.xlsx` |
| NO_PAPER | PRJEB12888 | 954 | collection_date,country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB12888.xlsx` |
| NO_PAPER | PRJEB8667 | 552 | collection_date,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB8667.xlsx` |
| NO_PAPER | PRJNA353728 | 441 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA353728.xlsx` |
| NO_PAPER | PRJEB21132 | 390 | collection_date,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB21132.xlsx` |
| NO_PAPER | PRJEB40861 | 218 | host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB40861.xlsx` |
| NO_PAPER | PRJDB11378 | 129 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJDB11378.xlsx` |
| SKIP | PRJNA788733 | 1488 | isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC11925198 | `PRJNA788733.xlsx` |
| SKIP | PRJEB54810 | 660 | collection_date,country,host,isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC9376106 | `PRJEB54810.xlsx` |
| SKIP | PRJEB63210 | 324 | host,isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC11790497 | `PRJEB63210.xlsx` |
| SKIP | PRJNA857533 | 113 | isolation_source | manifest_only | no |  |  | europepmc_fulltext / PMC9813266 | `PRJNA857533.xlsx` |
| SKIP | PRJNA532924 | 106 | isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC8115898 | `PRJNA532924.xlsx` |
| SUPP_PRESENT | PRJEB39567 | 250 | isolation_source | unanchored | likely | isolation_source,collection_date | Supplementary Data 1; Supplementary Data | europepmc_fulltext / PMC12647771 | `PRJEB39567.xlsx` |
| SUPP_PRESENT | PRJDB6407 | 141 | isolation_source | no_supp | yes | isolation_source,collection_date | S1 Table | europepmc_fulltext / PMC8318238 | `PRJDB6407.xlsx` |
| SUPP_PRESENT | PRJNA1076808 | 104 | isolation_source | unanchored | yes | isolation_source,host,collection_date | Additional file 1: Table S1 | europepmc_fulltext / PMC11587635 | `PRJNA1076808.xlsx` |
