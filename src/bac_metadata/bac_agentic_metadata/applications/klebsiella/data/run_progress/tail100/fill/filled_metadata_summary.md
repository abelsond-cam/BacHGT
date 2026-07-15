# Filled metadata table — tail100 (tag `tail100`)

Studies: **50**; samples: **8627**. The per-sample clinical fields in the full-width base table have been substituted with the agent's found values (precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is placeholder-stripped.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.840 | **0.922** | 707 | 707 | 0 | 59 | 0 | 648 |
| collection_date | 0.793 | **0.846** | 562 | 457 | 105 | 153 | 0 | 409 |
| isolation_source | 0.445 | **0.493** | 409 | 409 | 0 | 303 | 0 | 106 |
| host | 0.630 | **0.886** | 2211 | 2211 | 0 | 48 | 184 | 1979 |

## Study-level grades (broadcast to every sample in the study)

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| study_setting | 44 | 7420 | hospital 5904, mixed 1206, community 310 |
| amr_study | 41 | 7100 | amr 4642, surveillance 2358, mixed 100 |
