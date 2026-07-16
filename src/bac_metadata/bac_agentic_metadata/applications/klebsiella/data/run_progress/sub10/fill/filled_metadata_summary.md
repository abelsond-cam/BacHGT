# Filled metadata table — sub10 (tag `sub10`)

Studies: **1252**; samples: **2724**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.698 | **0.775** | 208 | 208 | 0 | 0 | 0 | 208 |
| collection_date | 0.745 | **0.767** | 60 | 60 | 0 | 0 | 0 | 60 |
| isolation_source | 0.611 | **0.712** | 275 | 275 | 0 | 0 | 0 | 275 |
| host | 0.476 | **0.756** | 763 | 763 | 0 | 0 | 0 | 763 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| study_setting | 723 | 1824 | hospital 1151, community 607, mixed 66 |
| amr_study | 745 | 1899 | amr 1261, surveillance 546, mixed 92 |
| study_type | 1252 | 2724 | observational 2456, experimental_evolution 168, other 100 |
| study_type_excluded | 1252 | 2724 | False 2556, True 168 |
