# Curator-gold categorisation: whole-field vs per-sample (train, val)

71 studies with a ready_to_merge file. For each field, the curator's pattern (did they add data over ENA, and is it one value or many) tells us whether their answer was whole-field (our step-a's job) or per-sample (method-b's job).

## isolation_source

| curator bucket | studies | residual gap (samples) |
|---|---|---|
| no_add | 47 | 9 |
| per_sample_multiple | 12 | 2301 |
| whole_field_uniform | 12 | 3379 |

- **whole-field-uniform studies: 12; our step-a actually fired on 3/12** → we MISS 9 whole-field-fillable studies (gap 3379 samples) that are a step-a issue, not method-b.

## collection_date

| curator bucket | studies | residual gap (samples) |
|---|---|---|
| no_add | 52 | 0 |
| per_sample_multiple | 14 | 2883 |
| whole_field_uniform | 5 | 859 |

- **whole-field-uniform studies: 5; our step-a actually fired on 1/5** → we MISS 4 whole-field-fillable studies (gap 859 samples) that are a step-a issue, not method-b.

