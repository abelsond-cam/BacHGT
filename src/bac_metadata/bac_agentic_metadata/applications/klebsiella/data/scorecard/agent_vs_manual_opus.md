# Agent vs manual curation — agreement, then adjudicated accuracy of each (train+val)

The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. Agreements are assumed jointly correct.

| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 96 | 71 (0.74) | 16 | 8 | 1 | 0 | — | 0.92 | 0.83 | +0.08 |
| amr_study | 78 | 65 (0.83) | 12 | 1 | 0 | 0 | 0.68 | 0.99 | 0.85 | +0.14 |
| study_setting | 88 | 82 (0.93) | 6 | 0 | 0 | 0 | 0.70 | 1.00 | 0.93 | +0.07 |
| TOTAL | 262 | 218 (0.83) | 34 | 9 | 1 | 0 | — | 0.97 | 0.87 | +0.10 |

- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement (can read low when one label dominates — the prevalence effect — even at high p₀).
- **agent right** = adjudicated manual-curation errors the agent corrects; **manual right** = agent errors. When they disagree the agent is right far more often.
