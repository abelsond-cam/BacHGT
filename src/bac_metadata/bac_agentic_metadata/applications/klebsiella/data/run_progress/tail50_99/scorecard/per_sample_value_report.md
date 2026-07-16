# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 121 | 67 | 67 | 1.00 |
| collection_date | 253 | 128 | 128 | 1.00 |
| isolation_source | 506 | 201 | 67 | 0.33 |
| host | 544 | 102 | 81 | 0.79 |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
