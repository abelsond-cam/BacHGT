# Per-sample supplementary worklist — which studies need a manual supp-table fetch

21 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJEB44852 | 58 | collection_date,isolation_source | NO_PMCID | likely | isolation_source | Table 2 | pdf | `PRJEB44852.xlsx` |
| OA_INVESTIGATE | PRJEB60478 | 123 | collection_date,country,isolation_source | unanchored | likely | isolation_source | Supplementary Table A | europepmc_fulltext / PMC8060595 | `PRJEB60478.xlsx` |
| OA_INVESTIGATE | PRJEB14100 | 100 | collection_date,country,host,isolation_source | unanchored | yes | isolation_source,host,collection_date | Supplementary Table 2 | europepmc_fulltext / PMC10234813 | `PRJEB14100.xlsx` |
| OA_INVESTIGATE | PRJEB14854 | 93 | collection_date,host,isolation_source | no_supp | yes | isolation_source,host,collection_date | Supplementary Table S1 | europepmc_fulltext / PMC13148723 | `PRJEB14854.xlsx` |
| OA_INVESTIGATE | PRJNA1092272 | 84 | host,isolation_source | no_supp | likely | isolation_source,host,collection_date | Supplementary dataset 2 | europepmc_fulltext / PMC11369815 | `PRJNA1092272.xlsx` |
| OA_INVESTIGATE | PRJEB6688 | 76 | country,isolation_source | no_supp | yes | isolation_source,collection_date | Table S1 (http://bigsdb.web.pasteur.fr/k | europepmc_fulltext / PMC4214299 | `PRJEB6688.xlsx` |
| OA_INVESTIGATE | PRJEB56212 | 72 | collection_date,isolation_source | no_supp | likely | isolation_source | Table 3 | europepmc_fulltext / PMC9960421 | `PRJEB56212.xlsx` |
| OA_INVESTIGATE | PRJEB32657 | 54 | host,isolation_source | unanchored | yes | isolation_source,host,collection_date | Source Data file (Zenodo: 10.5281/zenodo | europepmc_fulltext / PMC12612273 | `PRJEB32657.xlsx` |
| NO_PAPER | PRJEB36919 | 164 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB36919.xlsx` |
| NO_PAPER | PRJEB5132 | 128 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB5132.xlsx` |
| NO_PAPER | PRJNA1092662 | 88 | collection_date,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA1092662.xlsx` |
| NO_PAPER | PRJNA292902 | 78 | collection_date,country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA292902.xlsx` |
| NO_PAPER | PRJEB73547 | 62 | host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB73547.xlsx` |
| SKIP | PRJEB50270 | 192 | collection_date,country,host,isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC9007738 | `PRJEB50270.xlsx` |
| SKIP | PRJNA552297 | 180 | collection_date,country,host,isolation_source | manifest_only | no |  | Table S9 | europepmc_fulltext / PMC6867876 | `PRJNA552297.xlsx` |
| SKIP | PRJEB9147 | 100 | collection_date,country,host,isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC4896371 | `PRJEB9147.xlsx` |
| SKIP | PRJNA922161 | 92 | host,isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC9862994 | `PRJNA922161.xlsx` |
| SKIP | PRJNA1000963 | 80 | collection_date,isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC8084501 | `PRJNA1000963.xlsx` |
| SKIP | PRJNA552385 | 60 | host,isolation_source | no_supp | no |  |  | local_pdf / PMC8049106 | `PRJNA552385.xlsx` |
| SKIP | PRJNA508406 | 58 | collection_date,isolation_source | no_supp | no |  | Supplementary Table S1 | europepmc_fulltext / PMC8072773 | `PRJNA508406.xlsx` |
| SKIP | PRJNA292904 | 54 | collection_date,isolation_source | no_supp | no |  |  | pdf / PMC5442553 | `PRJNA292904.xlsx` |
