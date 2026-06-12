# CLAUDE.md — m_abs application

The *M. abscessus* **application site** of the agentic-metadata engine — the first
non-KPSC cohort, ~7,000 sequences. The engine, architecture, attribute-spec model, ground
truth and staged build now live one level up; **read those first**:

- [`../../CLAUDE.md`](../../CLAUDE.md) — engine orientation.
- [`../../PIPELINE_PLAN.md`](../../PIPELINE_PLAN.md) — architecture + staged build (Stages 1–4).
- [`../../STAGE0_kleb_curation_map.md`](../../STAGE0_kleb_curation_map.md) — the Klebsiella
  curation this generalises.

Wider guidance: [`../../../CLAUDE.md`](../../../CLAUDE.md) (bac_metadata),
[`../../../../../CLAUDE.md`](../../../../../CLAUDE.md) (monorepo),
`~/.claude/CLAUDE.md` (global). Tracked as item 1 in
[`../../../../../ToDo.md`](../../../../../ToDo.md).

## This application

- **Source data:** `ATB_metadata_Mabs_2025_release.xlsx` (in this folder).
- **Rubric:** [`attributes.yaml`](attributes.yaml) — the M.abs attribute spec (scaffold;
  grading definitions are David's to supply before Stage 2).
- **Headline target:** `host_disease` = **CF vs non-CF** (the species phenotype slot,
  absent from the structured data), plus aspirational `host_smoking_status`, and the four
  core completeness fields (country, collection_date, isolation_source, host).
- **Ground truth:** none curated yet — David hand-grades a seed set before the LLM grading
  is trusted; until then validation rides on the held-out Klebsiella gold standard.

> **Do not invent grading criteria.** Ask David for the grading definitions and any
> hand-graded M.abs seed set before building Stage 2.
