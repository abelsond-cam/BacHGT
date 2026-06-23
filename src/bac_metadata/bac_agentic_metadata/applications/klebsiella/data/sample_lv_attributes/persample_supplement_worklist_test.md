# Per-sample supplementary worklist — which studies need a manual supp-table fetch

22 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJEB27342 | 10826 | host,isolation_source | two_hop | yes | isolation_source,host,collection_date | Supplementary Table 2; Supplementary Tab | local_pdf / PMC9712112 | `PRJEB27342.xlsx` |
| FETCH_SUPP | PRJEB29738 | 1724 | collection_date,isolation_source | unanchored | likely | isolation_source,host,collection_date | Supplementary Tables 1–4; Microreact pro | local_pdf / PMC8634409 | `PRJEB29738.xlsx` |
| FETCH_SUPP | PRJNA757551 | 754 | collection_date,isolation_source | unanchored | yes | isolation_source | Supplementary Data 1 | local_pdf / PMC9160272 | `PRJNA757551.xlsx` |
| FETCH_SUPP | PRJEB32655 | 576 | collection_date,isolation_source | no_supp | yes | isolation_source,host,collection_date | Supplementary data to manuscript; R pack | local_pdf / PMC10327512 | `PRJEB32655.xlsx` |
| FETCH_SUPP | PRJEB38540 | 253 | host | no_supp | yes | isolation_source,host | Supplementary Table S1 | local_pdf / PMC8283727 | `PRJEB38540.xlsx` |
| FETCH_SUPP | PRJEB1272 | 97 | collection_date,isolation_source | no_supp | likely | isolation_source,collection_date | Supplementary Table S1 | pdf / PMC4790626 | `PRJEB1272.xlsx` |
| FETCH_SUPP | PRJNA543274 | 94 | isolation_source | direct | yes | isolation_source | Additional file 2: Table S1 | local_pdf / PMC8438989 | `PRJNA543274.xlsx` |
| OA_INVESTIGATE | PRJEB29739 | 1574 | collection_date,isolation_source | NO_PMCID | likely | isolation_source,collection_date | Supplementary Table 3 | europepmc_fulltext | `PRJEB29739.xlsx` |
| OA_INVESTIGATE | PRJEB43870 | 203 | host | no_supp | likely | host,collection_date | Supplementary Table 1 | europepmc_fulltext / PMC8453068 | `PRJEB43870.xlsx` |
| OA_INVESTIGATE | PRJNA252957 | 167 | isolation_source | unanchored | yes | isolation_source,collection_date | S1 Table, S2 Table | europepmc_fulltext / PMC4510304 | `PRJNA252957.xlsx` |
| OA_PARTIAL | PRJEB1271 | 342 | collection_date,host,isolation_source | direct | yes | isolation_source,collection_date | Additional file 2: Table S1 and Table S4 | europepmc_fulltext / PMC6717969 | `PRJEB1271.xlsx` |
| OA_PARTIAL | PRJEB34643 | 279 | host,isolation_source | direct | yes | isolation_source,collection_date | Table S6 | europepmc_fulltext / PMC8865463 | `PRJEB34643.xlsx` |
| OA_PARTIAL | PRJEB37711 | 142 | isolation_source | direct | yes | isolation_source | S1 Table | europepmc_fulltext / PMC8836320 | `PRJEB37711.xlsx` |
| OA_PARTIAL | PRJNA922900 | 111 | host | direct | likely | host,collection_date | Supplementary Table 1 | europepmc_fulltext / PMC10232788 | `PRJNA922900.xlsx` |
| OA_PARTIAL | PRJNA839691 | 98 | host | direct | yes | isolation_source,host,collection_date | Data Set S1 (XLSX); Data Set S3 (XLSX) | europepmc_fulltext / PMC9764986 | `PRJNA839691.xlsx` |
| REVIEW | PRJNA529744 | 205 | isolation_source | unanchored | unclear |  |  | europepmc_fulltext / PMC6711911 | `PRJNA529744.xlsx` |
| NO_PAPER | PRJEB21081 | 2739 | collection_date,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB21081.xlsx` |
| NO_PAPER | PRJEB53835 | 726 | collection_date,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB53835.xlsx` |
| NO_PAPER | PRJEB19226 | 184 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB19226.xlsx` |
| SKIP | PRJEB29424 | 1706 | host,isolation_source | NO_PMCID | no |  |  | local_pdf | `PRJEB29424.xlsx` |
| SKIP | PRJNA825705 | 155 | collection_date | unanchored | no |  |  | europepmc_fulltext / PMC9393496 | `PRJNA825705.xlsx` |
| SKIP | PRJEB1963 | 69 | collection_date | no_supp | no |  |  | europepmc_fulltext / PMC3772739 | `PRJEB1963.xlsx` |
