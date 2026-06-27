# Enriched collated table — fold train, val (tag `train`)

Studies: **109**; samples: **34288**. The four clinical fields in the full-width collated base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | enriched | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.620 | **0.933** | 11449 | 10734 | 715 | 4642 | 2683 | 4124 |
| collection_date | 0.551 | **0.866** | 12223 | 10807 | 1416 | 6723 | 3644 | 1856 |
| isolation_source | 0.445 | **0.729** | 11350 | 9722 | 1628 | 6373 | 2825 | 2152 |
| host | 0.444 | **0.870** | 14656 | 14624 | 32 | 170 | 1618 | 12868 |

Outputs: full-width `enriched_collated_<TAG>.tsv` (drop-in for `qc_add_metadata`), long-format `enriched_provenance_<TAG>.tsv` (every changed cell), this summary.
