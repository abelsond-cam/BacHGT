# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy |
|---|---|---|---|---|
| country | 1122 | 1111 | 1094 | 0.98 |
| collection_date | 4727 | 4637 | 4627 | 1.00 |
| isolation_source | 5605 | 5076 | 4686 | 0.92 |
| host | 3883 | 3674 | 3584 | 0.98 |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
