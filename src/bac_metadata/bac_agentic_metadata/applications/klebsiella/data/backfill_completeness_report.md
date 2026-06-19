# Per-sample backfill completeness vs metadata_v2 (train, val)

Samples: **34288**. Completeness = fraction with a real value (placeholder-stripped both sides; gold = curated `*_parsed`). **baseline** = ENA as deposited; **agent** = baseline + our backfill (whole-field + method-b); **v2** = the manual-curation target; **gap-closed** = (agent−baseline)/(v2−baseline).

| field | baseline | agent | v2 (gold) | agent gain | gap-closed |
|---|---|---|---|---|---|
| country | 0.62 | **0.87** | 0.88 | +0.25 | 0.95 |
| collection_date | 0.55 | **0.71** | 0.75 | +0.16 | 0.80 |
| isolation_source | 0.45 | **0.59** | 0.67 | +0.15 | 0.67 |
| host | 0.44 | **0.87** | 0.79 | +0.42 | 1.23 |

- **agent ≥ v2** means our backfill completed at least as much as the manual curation; **gap-closed > 1.0** means we filled more than manual did over baseline.
