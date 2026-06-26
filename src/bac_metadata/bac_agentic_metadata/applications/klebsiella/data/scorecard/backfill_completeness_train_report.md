# Per-sample backfill completeness vs metadata_v2 (train, val)

Samples: **34288**. Completeness = fraction with a real value (placeholder-stripped both sides; gold = curated `*_parsed`). Cumulative: **baseline** (ENA as deposited) → **+whole-field** (step-a) → **+per-sample** (step-b, = **agent**) → **v2** (manual target). **gap-closed** = (agent−baseline)/(v2−baseline); **residual_gap** = v2−agent (what manual still has and we don't).

| field | baseline | +whole-field | +per-sample | +escalation (agent) | v2 (gold) | gain wf | gain ps | gain esc | residual gap | gap-closed |
|---|---|---|---|---|---|---|---|---|---|---|
| country | 0.62 | 0.74 | 0.86 | **0.93** | 0.88 | +0.12 | +0.11 | +0.08 | 0.00 | 1.20 |
| collection_date | 0.55 | 0.60 | 0.76 | **0.87** | 0.75 | +0.05 | +0.16 | +0.11 | 0.00 | 1.61 |
| isolation_source | 0.45 | 0.51 | 0.65 | **0.73** | 0.67 | +0.06 | +0.14 | +0.08 | 0.00 | 1.27 |
| host | 0.44 | 0.82 | 0.82 | **0.87** | 0.79 | +0.38 | +0.00 | +0.05 | 0.00 | 1.24 |

- **gain wf / ps / esc** isolate the whole-field, per-sample, and curator-escalation contributions; **residual gap** is the per-field completeness manual curation still has over us — the target of the gap diagnosis.
