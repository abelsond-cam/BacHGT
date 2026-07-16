# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 3933 | 3686 | 3686 | 1.00 |
| collection_date | 8429 | 7447 | 7340 | 0.99 |
| isolation_source | 6705 | 6206 | 5253 | 0.85 |
| host | 2161 | 1926 | 1799 | 0.93 |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
