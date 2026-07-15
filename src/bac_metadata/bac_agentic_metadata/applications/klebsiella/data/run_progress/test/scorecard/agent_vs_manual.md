# Agent vs manual curation — agreement, then adjudicated accuracy of each (test)

The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. Agreements are assumed jointly correct.

| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 36 | 31 (0.86) | 2 | 2 | 1 | 0 | — | 0.94 | 0.94 | +0.00 |
| amr_study | 39 | 32 (0.82) | 4 | 1 | 1 | 1 | 0.69 | 0.97 | 0.89 | +0.08 |
| study_setting | 42 | 38 (0.90) | 4 | 0 | 0 | 0 | 0.81 | 1.00 | 0.90 | +0.10 |
| TOTAL | 117 | 101 (0.86) | 10 | 3 | 2 | 1 | — | 0.97 | 0.91 | +0.06 |

- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement (can read low when one label dominates — the prevalence effect — even at high p₀).
- **agent right** = adjudicated manual-curation errors the agent corrects; **manual right** = agent errors. When they disagree the agent is right far more often.
