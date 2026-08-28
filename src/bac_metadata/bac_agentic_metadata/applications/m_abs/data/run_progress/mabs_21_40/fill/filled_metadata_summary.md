# Filled metadata table — mabs_21_40 (tag `mabs_21_40`)

Studies: **20**; samples: **767**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.780 | **0.877** | 75 | 75 | 0 | 0 | 0 | 75 |
| collection_date | 0.639 | **0.643** | 3 | 3 | 0 | 3 | 0 | 0 |
| isolation_source | 0.383 | **0.591** | 159 | 159 | 0 | 4 | 0 | 155 |
| host | 0.662 | **0.836** | 133 | 133 | 0 | 0 | 0 | 133 |
| cf_status | 0.000 | **0.390** | 299 | 299 | 0 | 19 | 0 | 280 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| reports_AST | 16 | 591 | True 342, False 249 |
| per_sample_AST | 7 | 221 | possible 159, retrievable 62 |
| study_type | 20 | 767 | observational 675, experimental_evolution 92 |
| study_type_excluded | 20 | 767 | False 675, True 92 |
