# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 4644 | 4319 | 4167 | 0.96 |
| collection_date | 6748 | 5728 | 5533 | 0.97 |
| isolation_source | 6398 | 5915 | 4659 | 0.79 |
| host | 170 | 143 | 32 | 0.22 |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
