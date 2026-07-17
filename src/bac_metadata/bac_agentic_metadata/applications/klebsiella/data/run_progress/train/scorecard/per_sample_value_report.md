# Backfill value-correctness vs metadata_v2

Gold = `metadata_final_curated_all_samples_and_columns.tsv`, matched against raw + curated `_parsed` per field (placeholder-stripped both sides; case/whitespace-folded; `collection_date` compared at **year** granularity). A fill is correct if it matches the raw or the parsed gold value.

| field | cells filled | with gold | correct | value-accuracy | blank-fill acc (n) | overwrite acc (n) |
|---|---|---|---|---|---|---|
| country | 3933 | 3686 | 3686 | 1.00 | 1.00 (n=3686) | — (n=0) |
| collection_date | 8429 | 7447 | 7340 | 0.99 | 0.98 (n=6801) | 1.00 (n=646) |
| isolation_source | 6705 | 6206 | 5253 | 0.85 | 0.99 (n=5285) | 0.00 (n=921) |
| host | 2161 | 1926 | 1799 | 0.93 | 0.93 (n=1888) | 0.97 (n=38) |

- **cells filled** = fills proposed; **with gold** = of those, how many have a value in metadata_v2 to check; **value-accuracy** = fraction of those that match (raw or parsed).
- **blank-fill acc** = accuracy on fills of a blank ENA cell (a positive fill — the real value-add). **overwrite acc** = accuracy on fills that replaced a real ENA value; these are scored against a gold that *is* the raw ENA the fill deliberately replaced, so they read low by construction and need spot-review, not equality. `n` = with-gold count in each split.
