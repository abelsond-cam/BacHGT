# Backfill value-correctness vs metadata_v2 (train+val whole-field fills)

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, column suffix `_parsed` (curated value, placeholder-stripped both sides, raw — no categorisation).

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 4292 | 4035 | 4030 | 1.00 |
| collection_date | 5024 | 4179 | 0 | 0.00 |
| isolation_source | 4690 | 4170 | 2425 | 0.58 |
| host | 170 | 143 | 32 | 0.22 |

- **cells filled** = per-sample whole-field fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match.
- `collection_date` accuracy is expected low here: a single whole-project midpoint rarely equals each sample's true date — those mostly belong to the per-sample (per-sample) step.
