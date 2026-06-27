# Enriched collated table — fold test (tag `test`)

Studies: **47**; samples: **31604**. The four clinical fields in the full-width collated base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | enriched | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.665 | **0.959** | 11416 | 9292 | 2124 | 2124 | 5413 | 3879 |
| collection_date | 0.644 | **0.935** | 11811 | 9224 | 2587 | 5895 | 5063 | 853 |
| isolation_source | 0.602 | **0.739** | 7102 | 4336 | 2766 | 6670 | 363 | 69 |
| host | 0.531 | **0.834** | 9633 | 9588 | 45 | 3835 | 1116 | 4682 |

Outputs: full-width `enriched_collated_<TAG>.tsv` (drop-in for `qc_add_metadata`), long-format `enriched_provenance_<TAG>.tsv` (every changed cell), this summary.
