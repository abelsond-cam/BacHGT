# CLAUDE.md — m_abs application

The *M. abscessus* **application site** of the agentic-metadata engine — the first non-KPSC cohort
(whole-cohort run tag `mabs_all`; see [`../../PROGRESS_REPORT.md`](../../PROGRESS_REPORT.md) for
current study/sample counts and status). The engine, architecture, attribute-spec model and staged
build live one level up; **read those first**:

- [`../../CLAUDE.md`](../../CLAUDE.md) — engine orientation.
- [`../../PROGRESS_REPORT.md`](../../PROGRESS_REPORT.md) — the single living doc: engine, pipeline,
  attribute-spec model, the Klebsiella application this generalises, results, and forward plan. **State
  of record lives here** — not in this file.

Wider guidance: [`../../../CLAUDE.md`](../../../CLAUDE.md) (bac_metadata),
[`../../../../../CLAUDE.md`](../../../../../CLAUDE.md) (monorepo), `~/.claude/CLAUDE.md` (global).
Tracked as item 1 in [`../../../../../ToDo.md`](../../../../../ToDo.md).

## Plan & state

The current work is the **m_abs redo** — bringing m_abs to the finished state Klebsiella reached
(improved rubric, clean re-grade, escalation walk, collaborator-table integration, summary + Artifact),
run phase-by-phase against a checkpoint cadence (CP‑1 rubric · CP‑2 run · CP‑3 manual work · CP‑4 wrap).
**Status of record: [`../../PROGRESS_REPORT.md`](../../PROGRESS_REPORT.md) + [`ToDo.md`](../../../../../ToDo.md)** —
this file does not carry live state. [`PROJECT_PLAN.md`](PROJECT_PLAN.md) is the *earlier* (Jul 2026) build
plan, superseded by the redo plan; kept only as dated history.

Everything m_abs is **local** (no CSD3). Grading definitions are David's — draft, then he signs off.

## This application

- **Source data:** `ATB_metadata_Mabs_2025_release.xlsx` (the ENA/ATB metadata for the cohort).
- **Collaborator table (M4):** `all_isol2single_isol2cimr2clnc.xlsx` — a lane-keyed clinical table
  (cf_status, location/year, subspecies, a 7-drug AST panel, phenotype, FEV1/outcome, BAPS/treegubbins)
  integrated in the M4 combine (blank-fill + adjudicated overwrites + all other columns attached lane-keyed).
- **Rubric:** [`attributes.yaml`](attributes.yaml) — the M.abs attribute spec (David edits directly). It
  reuses the shared engine + grade scale; the species-specific slots are the **CF phenotype (`cf_status`)**
  and the **AST** work. Curation targets the five per-sample completeness fields
  (country, collection_date, isolation_source, host, **cf_status**).
- **Ground truth:** none curated for M.abs — validation rides on the held-out Klebsiella gold; David
  hand-checks a seed set before trusting M.abs grading.

## Rubric decisions of record (in `attributes.yaml`)

- **cf_status is the headline phenotype** — `never_overwrite: [cf_status]` (blank-fills only; a recorded
  CF/non-CF value is never changed). Its whole-project rule is the stricter one (95% of samples with a
  *known* status + non-CF-by-absence + immune-status guard), NOT the generic categorical rule.
- **AST = scope, don't extract (David, 2026-08-28).** Detection grades `reports_AST` / `per_sample_AST`
  are FINALISED; the **7-drug backbone** (`ast_panel.ast_backbone_drugs`:
  cefoxitin, amikacin, tigecycline, clarithromycin, linezolid, imipenem, tobramycin) is the reference set
  for all AST work. **Per-drug PAPER extraction is DEFERRED** — the full panel is parked under
  `ast_panel.drugs_deferred`, so the engine reads no `drugs:` key and does not mine per-isolate AST this
  round (rename it back to `drugs:` to re-enable). The in-hand collaborator-table AST still lands via M4.
- **Six Klebsiella rubric-prose refinements ported (2026-08-28):** whole_project_rule, study_level
  sizing_first + grading_basis, the study_type "routine lab culturing is NOT experimental_evolution" guard,
  the country funding/affiliation guard, and the isolation_source be-SPECIFIC / lab-is-not-a-source prose.
- **m_abs-specific policy (unchanged):** the `gates` block + grade ladder `[10k,50k,250k]`; the m_abs
  `escalation` triage (pulmonary vs extrapulmonary, human vs environmental, CF axis — NOT Klebsiella's
  blood/carriage priors); **strict 2-yr / never-escalate** dates (`collection_date {24,24,2010}`);
  `auto_skip_wide_mix: false`; host-not-species/host-not-lab; `sample_identifier_columns` (incl.
  strain / lane / library_name — needed for per-isolate table anchoring).

## Running

Use the thin driver wrapper (injects the m_abs app paths — don't call the engine driver directly):

```bash
bash applications/m_abs/run_m_abs.sh <driver args>   # e.g. --min-study-size 1 --tag mabs_all --web-fallback
```

Editing any graded prose in `attributes.yaml` busts the content-addressed grade cache → a **full re-grade**
(intended). Re-run a already-accumulated band **without** `--carry-forward`. Curator loop is the shared
engine CLI (`engine.cli.attach_papers` → `escalate --interactive|--apply` → `run_health`); the exact redo
command sequence + who-runs-what is in the redo plan.

> **Do not invent grading criteria.** Grading definitions are David's — draft changes as a reviewable diff
> and get sign-off before running (a rubric edit forces a re-grade of the whole cohort).
