# Filled metadata table — train,val (tag `train`)

Studies: **104**; samples: **34288**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.620 | **0.934** | 10740 | 10740 | 0 | 3933 | 2172 | 4635 |
| collection_date | 0.551 | **0.857** | 11148 | 10491 | 657 | 8427 | 2471 | 250 |
| isolation_source | 0.444 | **0.764** | 11923 | 10979 | 944 | 6689 | 3598 | 1636 |
| host | 0.444 | **0.924** | 16510 | 16472 | 38 | 2160 | 828 | 13522 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| study_setting | 100 | 33460 | hospital 27188, mixed 3204, community 3068 |
| amr_study | 100 | 33552 | amr 17350, surveillance 9876, mixed 6326 |
