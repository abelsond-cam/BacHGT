# Per-sample supplementary worklist — which studies need a manual supp-table fetch

10 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJEB2779 | 5370 | cf_status,collection_date,country,host,isolation_source | no_supp | likely | isolation_source | Table S1 | pdf / PMC5142603 | `PRJEB2779.xlsx` |
| FETCH_SUPP | PRJNA1165220 | 364 | cf_status,isolation_source | no_supp | likely | isolation_source,host,collection_date | Supplementary Table 2 | pdf / PMC12128065 | `PRJNA1165220.xlsx` |
| FETCH_SUPP | PRJNA941035 | 64 | cf_status | no_supp | likely | isolation_source,host,collection_date | Tables E1–E6 (online supplement) | pdf / PMC12091025 | `PRJNA941035.xlsx` |
| OA_INVESTIGATE | PRJEB44160 | 366 | cf_status,collection_date,isolation_source | no_supp | likely | isolation_source,host,collection_date | Table S1; Supplemental file 1 (spectrum. | europepmc_fulltext / PMC9431180 | `PRJEB44160.xlsx` |
| OA_INVESTIGATE | PRJNA1036625 | 219 | cf_status | no_supp | likely | isolation_source,host,collection_date | Supplementary Table S3, Supplementary Ta | europepmc_fulltext / PMC11841644 | `PRJNA1036625.xlsx` |
| OA_INVESTIGATE | PRJEB14002 | 162 | collection_date | unanchored | likely | host,collection_date | Supplementary appendix | europepmc_fulltext / PMC3664974 | `PRJEB14002.xlsx` |
| OA_PARTIAL | PRJDB10333 | 296 | cf_status,collection_date | direct | yes | isolation_source | Supplementary Table S1 | europepmc_fulltext / PMC7910664 | `PRJDB10333.xlsx` |
| NO_PAPER | PRJNA989271 | 153 | cf_status | NO_PMCID | no_text |  |  | none | `PRJNA989271.xlsx` |
| SKIP | PRJNA401515 | 118 | cf_status | unanchored | no |  |  | europepmc_fulltext / PMC5786738 | `PRJNA401515.xlsx` |
| SKIP | PRJNA420644 | 85 | cf_status | no_supp | no |  |  | pdf / PMC6325232 | `PRJNA420644.xlsx` |
