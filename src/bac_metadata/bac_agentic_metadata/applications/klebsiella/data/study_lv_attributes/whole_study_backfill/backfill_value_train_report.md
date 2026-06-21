# Backfill value-correctness vs metadata_v2 (train+val whole-field fills)

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, column suffix `_parsed` (curated value, placeholder-stripped both sides, raw — no categorisation).

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 5441 | 4472 | 3780 | 0.85 |
| collection_date | 5334 | 4257 | 0 | 0.00 |
| isolation_source | 2571 | 2332 | 631 | 0.27 |
| host | 13522 | 11260 | 0 | 0.00 |

- **cells filled** = per-sample whole-field fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match.
- `collection_date` accuracy is expected low here: a single whole-project midpoint rarely equals each sample's true date — those mostly belong to the per-sample (per-sample) step.
