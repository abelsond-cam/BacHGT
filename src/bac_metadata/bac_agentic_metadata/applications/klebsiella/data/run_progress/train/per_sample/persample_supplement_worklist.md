# Per-sample supplementary worklist — which studies need a manual supp-table fetch

34 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJNA996149 | 638 | collection_date,isolation_source | no_supp | likely | isolation_source,collection_date | Table S1 (AAC00735-23-s0002.xlsx) | pdf / PMC10720542 | `PRJNA996149.xlsx` |
| FETCH_SUPP | PRJNA845975 | 567 | isolation_source | NO_PMCID | likely | isolation_source,host,collection_date | Supplementary Table 1; Supplementary Tab | pdf | `PRJNA845975.xlsx` |
| FETCH_SUPP | PRJNA765801 | 438 | collection_date,isolation_source | abstained_other | likely | isolation_source,host,collection_date | Supplementary Data 1 | local_pdf / PMC12569050 | `PRJNA765801.xlsx` |
| FETCH_SUPP | PRJEB1563 | 396 | collection_date,isolation_source | manifest_only | likely | isolation_source,host,collection_date | Table S1 | local_pdf / PMC5615107 | `PRJEB1563.xlsx` |
| FETCH_SUPP | PRJEB21277 | 388 | collection_date,isolation_source | NO_PMCID | likely | isolation_source | Supplementary Table S1 | local_pdf | `PRJEB21277.xlsx` |
| FETCH_SUPP | PRJEB46513 | 281 | collection_date | manifest_only | yes | isolation_source,collection_date | S2 Table (TSV) | local_pdf / PMC12885268 | `PRJEB46513.xlsx` |
| FETCH_SUPP | PRJEB22890 | 157 | isolation_source | NO_PMCID | likely | isolation_source | Supplementary Table S1 | local_pdf | `PRJEB22890.xlsx` |
| FETCH_SUPP | PRJEB20799 | 92 | host,isolation_source | NO_PMCID | likely | isolation_source,host,collection_date | appendix pp 12–13 | local_pdf | `PRJEB20799.xlsx` |
| OA_INVESTIGATE | PRJEB37378 | 6724 | collection_date,country,host,isolation_source | unanchored | yes | isolation_source,collection_date | S1 Table | europepmc_fulltext | `PRJEB37378.xlsx` |
| OA_INVESTIGATE | PRJEB17615 | 684 | collection_date,isolation_source | no_supp | likely | isolation_source,host,collection_date | Microreact projects (linked in figure de | europepmc_fulltext / PMC7264328 | `PRJEB17615.xlsx` |
| OA_INVESTIGATE | PRJEB15226 | 576 | collection_date,isolation_source | no_supp | yes |  | Table S1 | europepmc_fulltext / PMC5121380 | `PRJEB15226.xlsx` |
| OA_INVESTIGATE | PRJEB39867 | 572 | collection_date,isolation_source | no_supp | likely | isolation_source | Supplementary Table S2 | europepmc_fulltext / PMC9598256 | `PRJEB39867.xlsx` |
| OA_INVESTIGATE | PRJNA1087366 | 405 | collection_date,country,isolation_source | manifest_only | likely | isolation_source | Supplementary Data 2 | europepmc_fulltext / PMC11087563 | `PRJNA1087366.xlsx` |
| OA_INVESTIGATE | PRJEB24082 | 400 | collection_date,isolation_source | no_supp | likely | isolation_source,collection_date | Supplementary Table S1 | europepmc_fulltext / PMC10132065 | `PRJEB24082.xlsx` |
| OA_INVESTIGATE | PRJEB30134 | 338 | collection_date,isolation_source | abstained_other | yes | isolation_source,collection_date | Tables S1 and S2 | europepmc_fulltext / PMC10438816 | `PRJEB30134.xlsx` |
| OA_INVESTIGATE | PRJNA325243 | 241 | host | abstained_other | yes | isolation_source,host,collection_date | Supplemental File 1 (Animal Hosts and Co | europepmc_fulltext / PMC12247286 | `PRJNA325243.xlsx` |
| OA_INVESTIGATE | PRJDB12075 | 184 | isolation_source | no_supp | likely | isolation_source | Table S1 (aem.01712-22-s0001.xlsx), Tabl | europepmc_fulltext / PMC9465067 | `PRJDB12075.xlsx` |
| OA_INVESTIGATE | PRJNA804332 | 138 | isolation_source | unanchored | likely | isolation_source,host,collection_date | Supplementary Table 1 | europepmc_fulltext / PMC9452910 | `PRJNA804332.xlsx` |
| OA_INVESTIGATE | PRJNA855907 | 126 | isolation_source | no_supp | yes | isolation_source,host,collection_date | Table S1 | europepmc_fulltext / PMC9430190 | `PRJNA855907.xlsx` |
| OA_PARTIAL | PRJEB42331 | 80 | isolation_source | direct | likely | isolation_source,collection_date | Table S1, Suppl. File 1 | europepmc_fulltext / PMC8209719 | `PRJEB42331.xlsx` |
| NO_PAPER | PRJEB28054 | 1304 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB28054.xlsx` |
| NO_PAPER | PRJEB22903 | 522 | country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB22903.xlsx` |
| NO_PAPER | PRJEB12699 | 282 | collection_date,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB12699.xlsx` |
| SKIP | PRJEB35685 | 824 | collection_date,isolation_source | NO_PMCID | no |  |  | local_pdf | `PRJEB35685.xlsx` |
| SKIP | PRJEB38289 | 500 | host | unanchored | no |  |  | europepmc_fulltext / PMC7985491 | `PRJEB38289.xlsx` |
| SKIP | PRJNA549322 | 442 | collection_date,country,isolation_source | no_supp | no |  |  | pdf | `PRJNA549322.xlsx` |
| SKIP | PRJEB19322 | 182 | collection_date,isolation_source | no_supp | no |  |  | local_pdf / PMC8743538 | `PRJEB19322.xlsx` |
| SKIP | PRJNA767944 | 173 | isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC9241541 | `PRJNA767944.xlsx` |
| SKIP | PRJNA634885 | 144 | isolation_source | direct | no |  |  | local_pdf / PMC7546619 | `PRJNA634885.xlsx` |
| SKIP | PRJEB64895 | 142 | isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC10668257 | `PRJEB64895.xlsx` |
| SKIP | PRJEB74083 | 106 | isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC11027475 | `PRJEB74083.xlsx` |
| SUPP_PRESENT | PRJEB42462 | 2556 | country,isolation_source | direct | yes | isolation_source,collection_date | Table S3 | pdf | `PRJEB42462.xlsx` |
| SUPP_PRESENT | PRJDB5929 | 631 | isolation_source | unanchored | likely | isolation_source,collection_date | Table S3 | europepmc_fulltext | `PRJDB5929.xlsx` |
| SUPP_PRESENT | PRJEB29143 | 498 | isolation_source | direct | likely | isolation_source,host | Table S1; Table S3 | local_pdf / PMC7527070 | `PRJEB29143.xlsx` |
