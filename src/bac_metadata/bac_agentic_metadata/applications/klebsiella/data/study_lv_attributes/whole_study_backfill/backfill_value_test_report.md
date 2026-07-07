# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 3879 | 3289 | 3289 | 1.00 |
| collection_date | 853 | 548 | 498 | 0.91 |
| isolation_source | 69 | 69 | 0 | 0.00 |
| host | 4682 | 3820 | 1702 | 0.45 |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
