# Filled metadata table — mabs_all (tag `mabs_all`)

Studies: **93**; samples: **348**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.819 | **0.859** | 14 | 14 | 0 | 0 | 0 | 14 |
| collection_date | 0.684 | **0.695** | 4 | 4 | 0 | 0 | 0 | 4 |
| isolation_source | 0.454 | **0.468** | 5 | 5 | 0 | 0 | 0 | 5 |
| host | 0.632 | **0.767** | 47 | 47 | 0 | 0 | 0 | 47 |
| cf_status | 0.049 | **0.262** | 74 | 74 | 0 | 0 | 0 | 74 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| reports_AST | 37 | 114 | False 57, True 57 |
| per_sample_AST | 13 | 46 | possible 30, retrievable 16 |
| study_type | 93 | 348 | observational 283, experimental_evolution 54, other 11 |
| study_type_excluded | 93 | 348 | False 294, True 54 |
