# Per-sample supplementary worklist — which studies need a manual supp-table fetch

35 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| FETCH_SUPP | PRJNA237670 | 51 | isolation_source | no_supp | likely | isolation_source,collection_date | Dataset S1 | pdf / PMC3977278 | `PRJNA237670.xlsx` |
| OA_INVESTIGATE | PRJEB42526 | 249 | collection_date,host,isolation_source | no_supp | likely | host,isolation_source | Supplementary File S1 | europepmc_fulltext / PMC8772961 | `PRJEB42526.xlsx` |
| OA_INVESTIGATE | PRJEB7967 | 207 | collection_date,country,isolation_source | unanchored | yes | isolation_source,collection_date | Table S1 | europepmc_fulltext / PMC4513082 | `PRJEB7967.xlsx` |
| OA_INVESTIGATE | PRJEB2655 | 200 | collection_date,country,host,isolation_source | no_supp | yes | isolation_source,collection_date | Supplemental Table S1 | europepmc_fulltext / PMC3613582 | `PRJEB2655.xlsx` |
| OA_INVESTIGATE | PRJEB8265 | 182 | collection_date,isolation_source | unanchored | yes | isolation_source,host,collection_date | Supplementary Data 1 | europepmc_fulltext / PMC11489765 | `PRJEB8265.xlsx` |
| OA_INVESTIGATE | PRJNA918858 | 162 | collection_date,host,isolation_source | no_supp | likely | isolation_source | Table 1 | europepmc_fulltext / PMC10375995 | `PRJNA918858.xlsx` |
| OA_INVESTIGATE | PRJNA701073 | 100 | host,isolation_source | no_supp | likely | isolation_source | Supplementary Table S2 | europepmc_fulltext / PMC9047678 | `PRJNA701073.xlsx` |
| OA_INVESTIGATE | PRJNA231221 | 88 | collection_date,isolation_source | manifest_only | yes | isolation_source,host,collection_date | Supplementary Data 1 | europepmc_fulltext / PMC6658474 | `PRJNA231221.xlsx` |
| OA_INVESTIGATE | PRJNA605147 | 84 | host | no_supp | yes | isolation_source,host,collection_date | table S1 | europepmc_fulltext / PMC8034854 | `PRJNA605147.xlsx` |
| OA_INVESTIGATE | PRJNA1050414 | 72 | isolation_source | unanchored | likely | isolation_source,collection_date | data S1 | europepmc_fulltext / PMC11784837 | `PRJNA1050414.xlsx` |
| OA_INVESTIGATE | PRJNA259658 | 69 | isolation_source | unanchored | yes | isolation_source,collection_date | Data Set S1 | europepmc_fulltext / PMC5156309 | `PRJNA259658.xlsx` |
| OA_INVESTIGATE | PRJEB51676 | 63 | host | unanchored | yes | isolation_source | Supplementary Table 1 | europepmc_fulltext / PMC9218594 | `PRJEB51676.xlsx` |
| OA_INVESTIGATE | PRJEB66360 | 60 | host | no_supp | yes | isolation_source,collection_date | Table 1 | europepmc_fulltext / PMC10714954 | `PRJEB66360.xlsx` |
| OA_PARTIAL | PRJEB39942 | 95 | host | direct | yes | isolation_source,collection_date | Table S1 (Excel file) | europepmc_fulltext / PMC8190614 | `PRJEB39942.xlsx` |
| OA_PARTIAL | PRJEB56668 | 73 | host | direct | yes | isolation_source,collection_date | Supplementary Table S1 | europepmc_fulltext / PMC10326032 | `PRJEB56668.xlsx` |
| OA_PARTIAL | PRJNA903550 | 67 | isolation_source | direct | likely |  | Supplementary Table S1, S2, S3 | europepmc_fulltext / PMC9808315 | `PRJNA903550.xlsx` |
| OA_PARTIAL | PRJEB50837 | 52 | host | direct | yes | isolation_source,host,collection_date | Source Data file | europepmc_fulltext / PMC9744880 | `PRJEB50837.xlsx` |
| OA_PARTIAL | PRJEB51225 | 51 | host | direct | yes | isolation_source,collection_date | Supplementary Table S1 | europepmc_fulltext / PMC10569728 | `PRJEB51225.xlsx` |
| REVIEW | PRJNA488070 | 172 | collection_date,isolation_source | no_supp | unclear | isolation_source,collection_date | Appendix Table 2 | europepmc_fulltext / PMC6433043 | `PRJNA488070.xlsx` |
| REVIEW | PRJEB43945 | 136 | collection_date,isolation_source | NO_PMCID | unclear | isolation_source,collection_date |  | abstract | `PRJEB43945.xlsx` |
| NO_PAPER | PRJEB5495 | 348 | collection_date,country,host,isolation_source | NO_PMCID | no_text |  |  | none | `PRJEB5495.xlsx` |
| NO_PAPER | PRJEB26075 | 130 | collection_date,country | NO_PMCID | no_text |  |  | none | `PRJEB26075.xlsx` |
| NO_PAPER | PRJNA1026096 | 88 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA1026096.xlsx` |
| NO_PAPER | PRJEB45369 | 84 | host | NO_PMCID | no_text |  |  | none | `PRJEB45369.xlsx` |
| NO_PAPER | PRJEB50346 | 70 | collection_date | NO_PMCID | no_text |  |  | none | `PRJEB50346.xlsx` |
| NO_PAPER | PRJDB4948 | 69 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJDB4948.xlsx` |
| NO_PAPER | PRJNA329105 | 57 | isolation_source | NO_PMCID | no_text |  |  | none | `PRJNA329105.xlsx` |
| SKIP | PRJNA415530 | 96 | host,isolation_source | no_supp | no |  |  | pdf / PMC6376851 | `PRJNA415530.xlsx` |
| SKIP | PRJEB50277 | 96 | isolation_source | NO_PMCID | no |  |  | abstract | `PRJEB50277.xlsx` |
| SKIP | PRJEB35890 | 96 | isolation_source | no_supp | no | collection_date |  | europepmc_fulltext / PMC7262493 | `PRJEB35890.xlsx` |
| SKIP | PRJNA342893 | 80 | isolation_source | NO_PMCID | no |  |  | abstract | `PRJNA342893.xlsx` |
| SKIP | PRJNA1061342 | 71 | isolation_source | NO_PMCID | no |  |  | abstract | `PRJNA1061342.xlsx` |
| SKIP | PRJEB78367 | 64 | isolation_source | unanchored | no |  |  | europepmc_fulltext / PMC12753507 | `PRJEB78367.xlsx` |
| SKIP | PRJEB59403 | 59 | host | NO_PMCID | no |  |  | abstract | `PRJEB59403.xlsx` |
| SKIP | PRJNA592157 | 58 | isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC7395672 | `PRJNA592157.xlsx` |
