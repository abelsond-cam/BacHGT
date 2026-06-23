# Agent vs manual curation — agreement, then adjudicated accuracy of each (train+val)

The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. Agreements are assumed jointly correct.

| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 37 | 30 (0.81) | 3 | 3 | 1 | 0 | — | 0.92 | 0.92 | +0.00 |
| amr_study | 38 | 32 (0.84) | 3 | 2 | 0 | 1 | 0.73 | 0.95 | 0.92 | +0.03 |
| study_setting | 42 | 38 (0.90) | 3 | 1 | 0 | 0 | 0.80 | 0.98 | 0.93 | +0.05 |
| TOTAL | 117 | 100 (0.85) | 9 | 6 | 1 | 1 | — | 0.95 | 0.92 | +0.03 |

- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement (can read low when one label dominates — the prevalence effect — even at high p₀).
- **agent right** = adjudicated manual-curation errors the agent corrects; **manual right** = agent errors. When they disagree the agent is right far more often.
