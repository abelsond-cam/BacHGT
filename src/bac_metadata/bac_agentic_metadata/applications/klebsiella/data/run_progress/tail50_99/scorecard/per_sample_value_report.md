# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy | blank-fill acc (n) | overwrite acc (n) |
|---|---|---|---|---|---|---|
| country | 121 | 67 | 67 | 1.00 | 1.00 (n=67) | — (n=0) |
| collection_date | 253 | 128 | 128 | 1.00 | 1.00 (n=128) | — (n=0) |
| isolation_source | 506 | 201 | 67 | 0.33 | 0.52 (n=128) | 0.00 (n=73) |
| host | 544 | 102 | 81 | 0.79 | 0.79 (n=102) | — (n=0) |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
- **blank-fill acc** = accuracy on fills of a blank ENA cell (a positive fill — the real value-add). **overwrite acc** = accuracy on fills that replaced a real ENA value; these are scored against a gold that *is* the raw ENA the fill deliberately replaced, so they read low by construction and need spot-review, not equality. `n` = with-gold count in each split.
