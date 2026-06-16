# Stage 2 — method-(a) backfill targeting vs parsed_per_project (train+val)

Accessions with both a grade and a parsed_per_project row: **97**.

`needs` = ENA non-null `<field>_pre` < threshold (a real gap). `covered` = method-(a) proposed a whole-project value. `improved` = curation lifted completeness by >5%. Threshold = 90%.

| field | needs backfill | covered by method-a | residual (method-b) | redundant | recall vs curation |
|---|---|---|---|---|---|
| country | 18 | 14 | 4 | 29 | 0.78 (n=18) |
| collection_date | 20 | 3 | 17 | 8 | 0.17 (n=18) |
| isolation_source | 31 | 4 | 27 | 6 | 0.14 (n=22) |
| host | 28 | 22 | 6 | 24 | 0.83 (n=24) |

## Reading it

- **covered**: method-(a) supplies a whole-project value for a field ENA left blank — ready to apply (value correctness still to be checked vs metadata_v2).
- **residual (method-b)**: a real gap with no single whole-project value — the deferred per-sample-table backlog.
- **recall vs curation**: where curation demonstrably filled the field, did method-(a) also flag it? Low recall ⇒ much of the win needs method-(b).
