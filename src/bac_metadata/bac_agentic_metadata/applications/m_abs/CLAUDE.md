# CLAUDE.md — m_abs application

The *M. abscessus* **application site** of the agentic-metadata engine — the first
non-KPSC cohort, ~7,000 sequences. The engine, architecture, attribute-spec model, ground
truth and staged build now live one level up; **read those first**:

- [`../../CLAUDE.md`](../../CLAUDE.md) — engine orientation.
- [`../../PROGRESS_REPORT.md`](../../PROGRESS_REPORT.md) — the single living doc: engine, pipeline,
  architecture + attribute-spec model, the Klebsiella curation this generalises, results, and the forward plan.

Wider guidance: [`../../../CLAUDE.md`](../../../CLAUDE.md) (bac_metadata),
[`../../../../../CLAUDE.md`](../../../../../CLAUDE.md) (monorepo),
`~/.claude/CLAUDE.md` (global). Tracked as item 1 in
[`../../../../../ToDo.md`](../../../../../ToDo.md).

## Plan

The full, current M. abscessus build plan lives in [`PROJECT_PLAN.md`](PROJECT_PLAN.md) (phases M0–M5,
confirmed decisions, the AST panel, risks). **Status: PAUSED** until the Klebsiella application is *finished*
(David: too complex to run both while still fixing/testing) — the reproduction gate that blocked it is now
cleared (see [`../../PROGRESS_REPORT.md`](../../PROGRESS_REPORT.md) §9–10). The Klebsiella finishing plan
(§10) is done, so M.abs is **now active** for a re-run. M2 (input pre-scan) is done; M3 (`attributes.yaml`) is
aligned to the current engine (2026-07-17, commit `423f242`): the six post-2026-07-07 Klebsiella rubric changes
were ported and the key escalation/date/null-token policy decided with David — `gates` block + grade ladder
`[10k,50k,250k]`; `escalation` block with an **m_abs-specific** triage (pulmonary vs extrapulmonary, human vs
environmental, CF axis — NOT Klebsiella's blood/carriage priors); **strict 2-yr / never-escalate** dates
(`collection_date {24,24,2010}`); `auto_skip_wide_mix: false`; expanded isolation_source null_tokens. **Next =
M4 launch**, first-pass scope **~20 largest studies** (rubric change busts the grading cache → fresh grades).

## This application

- **Source data:** `ATB_metadata_Mabs_2025_release.xlsx` (in this folder).
- **Rubric:** [`attributes.yaml`](attributes.yaml) — the M.abs attribute spec. The gates / escalation / date /
  null-token policy is decided (2026-07-17, see Plan above). Still carrying `TODO(david)` drafts: the study-level
  AST definitions (`reports_AST`, `per_sample_AST`) and the `ast_panel` drug list — refine those before trusting
  AST output.
- **Headline target:** `host_disease` = **CF vs non-CF** (the species phenotype slot,
  absent from the structured data), plus aspirational `host_smoking_status`, and the four
  core completeness fields (country, collection_date, isolation_source, host).
- **Ground truth:** none curated yet — David hand-grades a seed set before the LLM grading
  is trusted; until then validation rides on the held-out Klebsiella gold standard.

> **Do not invent grading criteria.** Ask David for the grading definitions and any
> hand-graded M.abs seed set before building Stage 2.
