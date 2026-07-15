# Filled metadata table — test (tag `test`)

Studies: **46**; samples: **31604**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.665 | **0.959** | 9292 | 9292 | 0 | 147 | 6187 | 2958 |
| collection_date | 0.644 | **0.935** | 9330 | 9224 | 106 | 3652 | 4825 | 853 |
| isolation_source | 0.595 | **0.747** | 5718 | 4783 | 935 | 5286 | 363 | 69 |
| host | 0.531 | **0.837** | 9693 | 9693 | 0 | 4701 | 913 | 4079 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| study_setting | 44 | 30507 | hospital 22020, mixed 6658, community 1829 |
| amr_study | 43 | 23241 | surveillance 10223, amr 9940, mixed 3078 |
