# Per-sample-gold gap: fetch vs parse vs non-tabular (train, val)

For the studies the curator did **per-sample** (so method-b's job), we ran the existing extractor on their LOCAL source tables to split the gap. **fetch** = local extraction recovers it (broader fetching would close it; extraction is sound); **parse** = the table has the field but our map/join/value-check failed (fixable); **non_tabular** = no local table carries it (curator used paper text).

Per-sample residual gap analysed = **5184** samples → fetch **2212** (43%), parse **2782** (54%), rest non-tabular.

| verdict | (study,field) | gap samples | recovered (local) |
|---|---|---|---|
| parse | 7 | 2782 | 178 |
| fetch | 8 | 2212 | 2194 |
| non_tabular_no_table | 2 | 190 | 0 |

### by field (gap samples)

| field | fetch | non_tabular_no_table | parse |
|---|---|---|---|
| collection_date | 1977 | 96 | 810 |
| isolation_source | 235 | 94 | 1972 |
