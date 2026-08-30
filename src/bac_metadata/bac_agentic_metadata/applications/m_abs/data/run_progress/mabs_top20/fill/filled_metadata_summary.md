# Filled metadata table — mabs_top20 (tag `mabs_top20`)

Studies: **20**; samples: **5340**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.765 | **0.846** | 432 | 432 | 0 | 0 | 0 | 432 |
| collection_date | 0.712 | **0.753** | 285 | 217 | 68 | 285 | 0 | 0 |
| isolation_source | 0.671 | **0.956** | 1523 | 1523 | 0 | 365 | 996 | 162 |
| host | 0.781 | **1.000** | 1167 | 1167 | 0 | 0 | 883 | 284 |
| cf_status | 0.287 | **0.570** | 1509 | 1509 | 0 | 285 | 0 | 1224 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| reports_AST | 19 | 5187 | False 4082, True 1105 |
| per_sample_AST | 7 | 1020 | possible 1020 |
| study_type | 20 | 5340 | observational 5340 |
| study_type_excluded | 20 | 5340 | False 5340 |
