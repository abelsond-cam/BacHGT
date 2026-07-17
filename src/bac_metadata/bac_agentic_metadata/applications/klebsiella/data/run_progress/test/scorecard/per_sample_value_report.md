# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy | blank-fill acc (n) | overwrite acc (n) |
|---|---|---|---|---|---|---|
| country | 147 | 146 | 146 | 1.00 | 1.00 (n=146) | — (n=0) |
| collection_date | 3653 | 3581 | 3363 | 0.94 | 0.94 (n=3492) | 1.00 (n=89) |
| isolation_source | 5303 | 4699 | 4499 | 0.96 | 1.00 (n=3783) | 0.80 (n=916) |
| host | 4717 | 4516 | 4358 | 0.97 | 0.97 (n=4516) | — (n=0) |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
- **blank-fill acc** = accuracy on fills of a blank ENA cell (a positive fill — the real value-add). **overwrite acc** = accuracy on fills that replaced a real ENA value; these are scored against a gold that *is* the raw ENA the fill deliberately replaced, so they read low by construction and need spot-review, not equality. `n` = with-gold count in each split.
