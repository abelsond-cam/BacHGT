# Agent vs manual curation — agreement, then adjudicated accuracy of each (train+val)

The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. Agreements are assumed jointly correct.

| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 95 | 71 (0.75) | 16 | 6 | 2 | 0 | — | 0.94 | 0.83 | +0.11 |
| amr_study | 85 | 68 (0.80) | 15 | 1 | 0 | 1 | 0.63 | 0.99 | 0.82 | +0.17 |
| study_setting | 94 | 87 (0.93) | 6 | 0 | 0 | 1 | 0.73 | 1.00 | 0.94 | +0.06 |
| TOTAL | 274 | 226 (0.82) | 37 | 7 | 2 | 2 | — | 0.97 | 0.86 | +0.11 |

- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement (can read low when one label dominates — the prevalence effect — even at high p₀).
- **agent right** = adjudicated manual-curation errors the agent corrects; **manual right** = agent errors. When they disagree the agent is right far more often.
