# Combined run-health — 7 tag(s) — ✅ **GENUINELY CLEAR**

Cross-tag roll-up of `run_progress/<tag>/run_health/report.tsv` with the acceptance policy in `evaluation/combined_run_health.py` applied. **ACCEPTED** = genuinely unrecoverable (counts as clear); **ACTIONABLE** = a curator can still resolve it. Unrecognised recoverability → ACTIONABLE (fail-loud).

**7660 (study×field) cells** — FILLED 5622 · EXHAUSTED 1818 · ACCEPTED 220 · ACTIONABLE 0

## Per-tag roll-up

| tag | FILLED | EXHAUSTED | ACCEPTED | ACTIONABLE |
|---|---|---|---|---|
| train | 379 | 27 | 30 | 0 |
| test | 174 | 12 | 2 | 0 |
| tail100 | 164 | 18 | 18 | 0 |
| tail50_99 | 336 | 24 | 20 | 0 |
| tail25_49 | 496 | 60 | 36 | 0 |
| tail10_24 | 671 | 131 | 54 | 0 |
| sub10 | 3402 | 1546 | 60 | 0 |

## Accepted-as-unrecoverable — breakdown

| reason | cells |
|---|---|
| table has no ENA-mappable key (unanchored) or no per-isolate table exists | 108 |
| no describing paper resolved for the study — nothing to extract from | 60 |
| requested supplement not in folder — unavailable (all fetchable fetched) | 46 |
| wide-mix — no single whole-field value applies | 6 |

## Truly-actionable cells

_None — every outstanding cell is an accepted, genuinely-unrecoverable gap._
