# PIPELINE_PLAN — the agentic-metadata engine

The living plan for the **reusable, species-agnostic agentic metadata-curation engine**.
The engine is the product; *Klebsiella* and *M. abscessus* are **application sites**. This
doc is the framework; [`STAGE0_kleb_curation_map.md`](STAGE0_kleb_curation_map.md) is the
reference for the manual Klebsiella curation it generalises.

## 1. What the engine does

For one **project accession** (`study_accession`) — the unit of work — the engine:

1. Pulls the accession's structured ENA/ATB metadata, computes per-field completeness, and
   reads the EBI project record counts (total records + species-of-interest by
   `scientific name`) to size the project.
2. Finds the best paper describing the cohort — the one covering the largest part of the
   project (a paper may serve several accessions; the project counts tell us whether a
   candidate paper covers the whole project or only a subsample).
3. Grades the paper into a **configured attribute set** (the application's spec).
4. Emits, per attribute, a value + grade (`gradeable` / `partial` / `not_gradeable`) + an
   evidence pointer, plus cohort flags (`cohort_mixed`, `needs_manual_download`).

Accessions are processed **biggest-first**, mirroring the manual workflow.

## 2. Architecture

```
bac_agentic_metadata/
  engine/                 # application-agnostic: spec loader, completeness, paper-finder,
                          #   extraction agent, graders, eval harness
  applications/
    klebsiella/           # attributes.yaml + frozen ground truth + split + outputs
    m_abs/                # attributes.yaml + ground truth + outputs
```

The engine takes an **attribute spec + a study's inputs** and returns graded attributes.
An application supplies (a) its `attributes.yaml`, (b) its ground-truth instance,
(c) input pointers, (d) outputs. Adding a species = adding an application directory.

## 3. The attribute-spec model (core abstraction)

Each application's `attributes.yaml` is the **single source of truth for the rubric** —
David edits it directly. Attributes fall in three classes:

1. **Study filters** — exclude a study from the cohort (Kleb: experimental-evolution).
2. **Study-level judgements** — cohort attributes read from the paper, often *absent from
   structured data* (Kleb: `study_setting`, `amr_study`, wanted `amr_target` /
   `amr_method` / `cohort_age`; M.abs: `host_disease` = CF vs non-CF, `host_smoking_status`).
3. **Per-sample completeness / backfill** — `country`, `collection_date`,
   `isolation_source`, `host`: measure ATB completeness, backfill from the paper.

The **phenotype axis is a per-species slot**: Kleb's is AMR-selection + setting; M.abs's
is CF status. Each attribute is graded on the `gradeable / partial / not_gradeable` scale.
**Grading definitions (thresholds, edge rules) are David's to supply** — the current
`attributes.yaml` files are name/value scaffolds with definitions marked TBD.

## 4. Ground truth & validation (hybrid)

- The **generalised attribute spec is the rubric**; a **frozen Klebsiella instance is the
  validation target**.
- Validate **only** against `study_level` columns A–K + `parsed_per_project`. **Never**
  against `*_added` or `ATB_*_prop` (work-tracking, not truth). Expect gold-standard
  imperfections (typos, improvable values) — record disagreements rather than assuming the
  sheet is correct.
- Ground truth exists **only for already-curated attributes**. Wanted/new attributes
  (`amr_target`, `amr_method`, finished `cohort_age`, all M.abs attributes) are
  **generated, then human-checked** on train/val — we never claim agreement we can't
  measure.

## 5. Iteration discipline (no overfitting)

The curated Klebsiella accessions are split **train 50 / val 20 / test 30** by accession,
folds assigned at paper-group level to prevent paper leakage
(`applications/klebsiella/data/kleb_project_splits.tsv`, seeded, reproducible). **All
rubric/prompt tuning happens on train+val; the test fold stays sealed** until a single
final measured-agreement run.

## 6. Staged build (Stages 1–4 follow this Stage 0)

- **Stage 0 (this round) — DONE here.** Engine skeleton, this plan, the Stage 0 map, the
  attribute-spec scaffolds, and the seeded split.
- **Stage 1 — Deterministic ingestion & completeness (no LLM).** Group by accession; pull
  ENA/EBI project metadata; read project record counts (total + species-of-interest by
  `scientific name`) to size each project; compute completeness for the core + proxy
  fields; resolve best-column ambiguity. Validate completeness against `parsed_per_project`.
  The stable test bed for everything downstream.
- **Stage 2 — Paper lookup & structured grading (LLM).** Find best paper per accession;
  extract + grade into the fixed `attributes.yaml` schema; set `cohort_mixed` /
  `needs_manual_download`. Validate on the train+val ground-truth accessions only.
- **Stage 3 — Opposing evaluator (model-graded review).** Independent agent reviews Stage 2
  → structured verdict + feedback; code-graded evals where checkable (does the completeness
  math reconcile? do flags match?). Measure agreement vs the curated labels.
- **Stage 4 — MCP integration & human handoff.** Wrap the ENA/EBI fetch behind a minimal
  MCP tool; produce the best-paper-per-accession table, the accessible-vs-manual-download
  queue, and the cohort-mixed → needs-raw-tables list. Run end-to-end on the real cohorts
  (Klebsiella small-study tail + ~7,000 *M. abs*).

## 7. Definition of done

Pipeline runs end-to-end on a real cohort by swapping the application directory; every LLM
step has **measured agreement** against held-out ground truth; the rubric lives in a
versioned `attributes.yaml`; the system is species-agnostic.
