# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 415 | 0 | 0 | — |
| collection_date | 204 | 0 | 0 | — |
| isolation_source | 256 | 8 | 0 | 0.00 |
| host | 790 | 51 | 44 | 0.86 |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
