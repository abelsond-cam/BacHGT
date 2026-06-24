# Per-sample backfill completeness vs metadata_v2 (test)

Samples: **31604**. Completeness = fraction with a real value (placeholder-stripped both sides; gold = curated `*_parsed`). Cumulative: **baseline** (ENA as deposited) → **+whole-field** (step-a) → **+per-sample** (step-b, = **agent**) → **v2** (manual target). **gap-closed** = (agent−baseline)/(v2−baseline); **residual_gap** = v2−agent (what manual still has and we don't).

| field | baseline | +whole-field | +per-sample | +escalation (agent) | v2 (gold) | gain wf | gain ps | gain esc | residual gap | gap-closed |
|---|---|---|---|---|---|---|---|---|---|---|
| country | 0.67 | 0.96 | 0.96 | **0.96** | 0.85 | +0.29 | +0.00 | +0.00 | 0.00 | 1.60 |
| collection_date | 0.64 | 0.84 | 0.84 | **0.91** | 0.76 | +0.20 | +0.00 | +0.07 | 0.00 | 2.20 |
| isolation_source | 0.60 | 0.60 | 0.73 | **0.76** | 0.70 | +0.00 | +0.13 | +0.03 | 0.00 | 1.55 |
| host | 0.53 | 0.71 | 0.80 | **0.83** | 0.77 | +0.18 | +0.09 | +0.04 | 0.00 | 1.29 |

- **gain wf / ps / esc** isolate the whole-field, per-sample, and curator-escalation contributions; **residual gap** is the per-field completeness manual curation still has over us — the target of the gap diagnosis.
