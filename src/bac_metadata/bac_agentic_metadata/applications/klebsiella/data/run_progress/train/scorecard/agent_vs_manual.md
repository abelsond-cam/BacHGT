# Agent vs manual curation — agreement, then adjudicated accuracy of each (train+val)

The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. Agreements are assumed jointly correct.

| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 93 | 69 (0.74) | 15 | 6 | 3 | 0 | — | 0.94 | 0.84 | +0.10 |
| amr_study | 86 | 69 (0.80) | 15 | 1 | 0 | 1 | 0.63 | 0.99 | 0.82 | +0.16 |
| study_setting | 95 | 87 (0.92) | 8 | 0 | 0 | 0 | 0.70 | 1.00 | 0.92 | +0.08 |
| TOTAL | 274 | 225 (0.82) | 38 | 7 | 3 | 1 | — | 0.97 | 0.86 | +0.11 |

- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement (can read low when one label dominates — the prevalence effect — even at high p₀).
- **agent right** = adjudicated manual-curation errors the agent corrects; **manual right** = agent errors. When they disagree the agent is right far more often.
