# Agent vs manual curation — agreement, then adjudicated accuracy of each (train+val)

The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. Agreements are assumed jointly correct.

| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 88 | 67 (0.76) | 14 | 5 | 2 | 0 | — | 0.94 | 0.84 | +0.10 |
| amr_study | 86 | 69 (0.80) | 14 | 2 | 0 | 1 | 0.63 | 0.98 | 0.84 | +0.14 |
| study_setting | 95 | 87 (0.92) | 8 | 0 | 0 | 0 | 0.70 | 1.00 | 0.92 | +0.08 |
| TOTAL | 269 | 223 (0.83) | 36 | 7 | 2 | 1 | — | 0.97 | 0.87 | +0.11 |

- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement (can read low when one label dominates — the prevalence effect — even at high p₀).
- **agent right** = adjudicated manual-curation errors the agent corrects; **manual right** = agent errors. When they disagree the agent is right far more often.
