# Per-sample supplementary worklist — which studies need a manual supp-table fetch

15 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| OA_INVESTIGATE | PRJEB70897 | 72 | collection_date,host,isolation_source | unanchored | yes | isolation_source,host,collection_date | Table 1, Table 2 | europepmc_fulltext / PMC10869444 | `PRJEB70897.xlsx` |
| OA_INVESTIGATE | PRJEB52158 | 64 | collection_date,country,host,isolation_source | NO_PMCID | yes | isolation_source,collection_date | Supplementary Tables 3 and 4 | europepmc_fulltext | `PRJEB52158.xlsx` |
| OA_INVESTIGATE | PRJNA984017 | 60 | collection_date,country,host,isolation_source | unanchored | likely |  | Table S2 (Appendix A / Supplementary Dat | europepmc_fulltext / PMC11913740 | `PRJNA984017.xlsx` |
| NO_PAPER | PRJEB24612 | 84 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB24612.xlsx` |
| NO_PAPER | PRJEB1730 | 76 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB1730.xlsx` |
| NO_PAPER | PRJNA635420 | 68 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA635420.xlsx` |
| NO_PAPER | PRJNA356346 | 66 | collection_date,country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA356346.xlsx` |
| NO_PAPER | PRJNA523429 | 56 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA523429.xlsx` |
| NO_PAPER | PRJEB25682 | 54 | collection_date,country,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB25682.xlsx` |
| NO_PAPER | PRJEB3226 | 52 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB3226.xlsx` |
| SKIP | PRJEB17888 | 96 | collection_date,country,host,isolation_source | NO_PMCID | no |  |  | europepmc_fulltext | `PRJEB17888.xlsx` |
| SKIP | PRJEB20357 | 92 | collection_date,country,host,isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC9155631 | `PRJEB20357.xlsx` |
| SKIP | PRJNA986550 | 92 | collection_date,country,host,isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC10597399 | `PRJNA986550.xlsx` |
| SKIP | PRJEB15325 | 84 | collection_date,country,host,isolation_source | NO_PMCID | no |  |  | abstract | `PRJEB15325.xlsx` |
| SKIP | PRJEB42167 | 69 | collection_date,country,host | NO_PMCID | no |  |  | abstract | `PRJEB42167.xlsx` |
