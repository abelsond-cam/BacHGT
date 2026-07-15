# Per-sample supplementary worklist — which studies need a manual supp-table fetch

15 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJEB29424 | 1706 | host,isolation_source | NO_PMCID | likely | isolation_source,host | appendix 2 | local_pdf | `PRJEB29424.xlsx` |
| FETCH_SUPP | PRJEB32655 | 576 | collection_date,isolation_source | NO_PMCID | likely | isolation_source,host,collection_date | Supplementary data / blantyreESBL R pack | local_pdf | `PRJEB32655.xlsx` |
| FETCH_SUPP | PRJNA757551 | 377 | collection_date | direct | yes | isolation_source | Supplementary Data 1 | local_pdf / PMC9160272 | `PRJNA757551.xlsx` |
| FETCH_SUPP | PRJEB38540 | 253 | host | no_supp | yes | isolation_source,host | Supplementary Table S1 | local_pdf / PMC8283727 | `PRJEB38540.xlsx` |
| FETCH_SUPP | PRJEB1272 | 97 | collection_date,isolation_source | no_supp | yes | isolation_source,collection_date | Supplementary Table S1 | pdf / PMC4790626 | `PRJEB1272.xlsx` |
| FETCH_SUPP | PRJNA543274 | 94 | isolation_source | abstained_other | yes | isolation_source | Additional file 2: Table S1 | local_pdf / PMC8438989 | `PRJNA543274.xlsx` |
| OA_INVESTIGATE | PRJNA252957 | 167 | isolation_source | abstained_other | yes | isolation_source,collection_date | S1 Table; S2 Table | europepmc_fulltext / PMC4510304 | `PRJNA252957.xlsx` |
| NO_PAPER | PRJEB21081 | 1826 | collection_date,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB21081.xlsx` |
| NO_PAPER | PRJEB53835 | 726 | country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB53835.xlsx` |
| NO_PAPER | PRJEB19226 | 184 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB19226.xlsx` |
| SKIP | PRJNA529744 | 205 | isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC6711911 | `PRJNA529744.xlsx` |
| SKIP | PRJNA825705 | 155 | collection_date | manifest_only | no |  |  | europepmc_fulltext / PMC9393496 | `PRJNA825705.xlsx` |
| SKIP | PRJEB1963 | 69 | collection_date | no_supp | no |  |  | europepmc_fulltext / PMC3772739 | `PRJEB1963.xlsx` |
| SUPP_PRESENT | PRJEB27342 | 5413 | country | direct | yes | isolation_source,host,collection_date | Supplementary Table 2; Supplementary Tab | local_pdf / PMC9712112 | `PRJEB27342.xlsx` |
| SUPP_PRESENT | PRJEB1271 | 59 | country | direct | yes | isolation_source,collection_date | Additional file 2: Table S1, Table S4 | europepmc_fulltext / PMC6717969 | `PRJEB1271.xlsx` |
