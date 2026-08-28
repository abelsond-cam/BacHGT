# Per-sample supplementary worklist — which studies need a manual supp-table fetch

11 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| OA_INVESTIGATE | PRJNA718117 | 77 | cf_status,host | unanchored | yes | isolation_source | Table 1 (main text) | europepmc_fulltext / PMC10499228 | `PRJNA718117.xlsx` |
| OA_INVESTIGATE | PRJNA315990 | 65 | cf_status,isolation_source | no_supp | yes | collection_date | Table 1 | europepmc_fulltext / PMC5034138 | `PRJNA315990.xlsx` |
| OA_INVESTIGATE | PRJEB6776 | 54 | collection_date,isolation_source | no_supp | yes | collection_date | Table 2 | europepmc_fulltext / PMC4357290 | `PRJEB6776.xlsx` |
| OA_INVESTIGATE | PRJEB61124 | 52 | cf_status | no_supp | yes | host,collection_date | Table 1 (main text) | europepmc_fulltext / PMC10979023 | `PRJEB61124.xlsx` |
| OA_INVESTIGATE | PRJDB13427 | 51 | collection_date | no_supp | yes | isolation_source,collection_date | Table S1 | europepmc_fulltext / PMC10433864 | `PRJDB13427.xlsx` |
| OA_PARTIAL | PRJNA523365 | 76 | isolation_source | direct | yes | host,collection_date | Supplementary Table 2 | europepmc_fulltext / PMC8390669 | `PRJNA523365.xlsx` |
| NO_PAPER | PRJEB36331 | 300 | cf_status,collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB36331.xlsx` |
| NO_PAPER | PRJNA353361 | 116 | cf_status,collection_date,country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA353361.xlsx` |
| SKIP | PRJNA1080355 | 94 | cf_status,host,isolation_source | NO_PMCID | no |  |  | local_pdf | `PRJNA1080355.xlsx` |
| SKIP | PRJNA1211657 | 84 | cf_status,isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC4982176 | `PRJNA1211657.xlsx` |
| SKIP | PRJDB15290 | 66 | cf_status,isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC11099050 | `PRJDB15290.xlsx` |
