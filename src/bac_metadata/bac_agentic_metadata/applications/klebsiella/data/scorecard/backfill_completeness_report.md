# Per-sample backfill completeness vs metadata_v2 (train, val)

Samples: **34288**. Completeness = fraction with a real value (placeholder-stripped both sides; gold = curated `*_parsed`). Cumulative: **baseline** (ENA as deposited) → **+whole-field** (step-a) → **+method-b** (step-b, = **agent**) → **v2** (manual target). **gap-closed** = (agent−baseline)/(v2−baseline); **residual_gap** = v2−agent (what manual still has and we don't).

| field | baseline | +whole-field | +method-b (agent) | v2 (gold) | gain a | gain b | residual gap | gap-closed |
|---|---|---|---|---|---|---|---|---|
| country | 0.62 | 0.78 | **0.87** | 0.88 | +0.16 | +0.09 | 0.01 | 0.95 |
| collection_date | 0.55 | 0.66 | **0.71** | 0.75 | +0.11 | +0.05 | 0.04 | 0.80 |
| isolation_source | 0.45 | 0.47 | **0.59** | 0.67 | +0.03 | +0.12 | 0.07 | 0.67 |
| host | 0.44 | 0.86 | **0.87** | 0.79 | +0.42 | +0.00 | 0.00 | 1.23 |

- **gain a / gain b** isolate the whole-field vs method-b contribution; **residual gap** is the per-field completeness manual curation still has over us — the target of the gap diagnosis.
