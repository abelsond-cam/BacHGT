# Per-level completeness accounting — test fold (31,604 samples)

How much each backfill **level** contributes per field, across three pipeline states:

- **baseline** — the frozen `0dfc660` ALL-CLEAR run (whole-field-first, no parsimony guard, escalation blind on PDFs).
- **broken rerun** — the clean STASH-and-rerun that exposed the gate (grade non-determinism + the 5 holes).
- **fixed re-gate** — after the per-sample-first reorder + escalate-big-decisions fixes (`5fc7ee4`) + human escalation.

Levels: **WF** = study-level whole-field fill · **PS** = per-sample table extraction · **ESC** = curator escalation.
Values are completeness *gains* (fraction of the 31,604 samples); the **agent** column is the cumulative total
(baseline-ENA + WF + PS + ESC). Counts ≈ gain × 31,604.

## country  (ENA baseline 0.665)

| state | WF | PS | ESC | **agent** | vs v2 (0.848) |
|---|---|---|---|---|---|
| baseline      | **0.292** | 0.000 | 0.000 | 0.957 | +0.109 |
| broken rerun  | 0.123 | 0.000 | 0.000 | **0.788** | **−0.060 (below v2)** |
| fixed re-gate | 0.123 | 0.000 | **0.171** | **0.959** | +0.111 |

*Story:* baseline filled country almost entirely by **silent whole-field "Italy"** (0.292 ≈ 9,200 samples) — but
that included ~568 mislabelled Ghana isolates (PRJEB27342 is Italy 85% / Ghana 13%). When the grade flipped to
abstain (broken rerun) nothing caught the 5,413-sample loss → 0.788. The fix routes the same high-leverage call
through **human escalation** (0.171 ≈ 5,400 samples, David-confirmed Italy for the SpARK subcohort) → 0.959,
now *correct-by-decision* rather than silent.

## collection_date  (ENA baseline 0.644)

| state | WF | PS | ESC | **agent** | vs v2 (0.764) |
|---|---|---|---|---|---|
| baseline      | **0.198** | 0.000 | 0.066 | 0.908 | +0.144 |
| broken rerun  | 0.027 | 0.102 | 0.066 | 0.838 | +0.074 |
| fixed re-gate | 0.027 | **0.105** | **0.160** | **0.936** | +0.172 |

*Story:* baseline **`gain_per_sample = 0.0`** — whole-field date (a single study-wide year) **pre-empted** per-sample
extraction (HOLE 5, the ordering inversion). The reorder runs per-sample FIRST, so date now comes from accurate
**per-sample per-isolate dates (0.105)** + **escalation midpoints (0.160)**, not a coarse study-wide guess.

## isolation_source  (ENA baseline 0.602)

| state | WF | PS | ESC | **agent** | vs v2 (0.702) |
|---|---|---|---|---|---|
| baseline      | 0.002 | 0.125 | 0.027 | 0.756 | +0.054 |
| broken rerun  | 0.002 | 0.125 | 0.000 | 0.729 | +0.027 |
| fixed re-gate | 0.002 | **0.127** | 0.012 | 0.742 | +0.040 |

*Story:* always per-sample-dominated (specimen type is genuinely per-isolate); stable across states.

## host  (ENA baseline 0.531)

| state | WF | PS | ESC | **agent** | vs v2 (0.766) |
|---|---|---|---|---|---|
| baseline      | 0.182 | 0.086 | 0.035 | 0.835 | +0.069 |
| broken rerun  | 0.148 | 0.121 | 0.035 | 0.836 | +0.070 |
| fixed re-gate | 0.148 | 0.121 | 0.035 | 0.836 | +0.070 |

*Story:* host reproduced throughout (per-sample compensated for whole-field variance) — which is why the broken
rerun's host looked fine while country silently collapsed.

## Headline

The collapse was **entirely the WF level on country + date**, and the cure was to **move the leverage off silent
whole-field onto per-sample (accurate) + human escalation (high-stakes)**. The fixed re-gate beats v2 on all four
fields (residual_gap 0.0) with the gains sourced where they belong: country from human-confirmed escalation, date
from per-sample + escalation, iso/host from per-sample.
