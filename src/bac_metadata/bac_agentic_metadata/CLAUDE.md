# CLAUDE.md — bac_agentic_metadata

The **reusable, species-agnostic agentic metadata-curation engine** inside `bac_metadata`.
The engine is the product; *Klebsiella* and *M. abscessus* are **application sites** of it.
Parent guidance: [`../CLAUDE.md`](../CLAUDE.md) (bac_metadata),
[`../../../CLAUDE.md`](../../../CLAUDE.md) (monorepo), `~/.claude/CLAUDE.md` (global).

> **Read first:** [`PROGRESS_REPORT.md`](PROGRESS_REPORT.md) — the **single living doc**: what the engine
> is, the pipeline, architecture + attribute-spec model, ground-truth discipline, the manual curation it
> generalises, ENA-sizing calibration, all measured results, the reproduction-test findings + fixes, and the
> forward plan. (It supersedes the former PIPELINE_PLAN / STAGE0 / STAGE1 / STAGE2 / reproduction-gate docs.)
> **Before building any grading step, ask David for the grading definitions — do not
> invent grading criteria.** The `attributes.yaml` files are name/value scaffolds with
> definitions marked TBD.

## Layout

```
bac_agentic_metadata/
  engine/                 # application-agnostic engine: ena_sizing, paper_finder, grader, fulltext,
                          #   local_papers, backfill, sample_extractor, escalation, supplementary, …
  applications/
    klebsiella/           # attributes.yaml, run_*/validate_* scripts, run_pipeline.sh (10 stages, per-sample first)
      diagnostics/        # one-off probes (diagnose_*, assess_*) — not in run_pipeline.sh
      data/               # task-aligned tree (folders mirror the pipeline steps):
        inputs/             #   curated study-level snapshot + study_setting_frozen
        fold_splits/        #   project_splits.tsv
        ena_assessment/     #   ena_sizing/ingest/assessment_report   (was "Stage 1")
        find_papers/        #   found_papers*, find_validation/adjudication, missing_papers,
          manual_download/  #     manually-downloaded <accession>.pdf (paywalled-paper fallback)
        study_lv_attributes/  # study-level: grading/ , whole_study_backfill/ , escalation/
        sample_lv_attributes/ # sample-level: per_sample/   (per-sample table extraction)
        scorecard/          #   agent_vs_manual + completeness (final measurement)
        diagnostics/        #   curator_gold, gt_corrections, gap/decline reports
        logs/  cache/       #   run logs; regenerable LLM/ENA/fulltext/find/per_sample caches
    m_abs/                # attributes.yaml, ATB_metadata_Mabs_2025_release.xlsx, CLAUDE.md
  PROGRESS_REPORT.md      # the single living doc
```

## Core ideas (one line each)

- **Unit of work = project accession** (`study_accession`); process biggest-first.
- **Attribute spec is the rubric**, one `attributes.yaml` per application, three classes:
  study filters, study-level judgements (read from the paper), per-sample completeness/backfill.
- **Hybrid ground truth**: generalised spec + a *frozen* Klebsiella instance. Validate only
  against `study_level` cols A–K + the `parsed_per_project` tab; never `*_added`/`ATB_*_prop`.
- **Iteration discipline**: tune on train+val; the test fold stays sealed.

## Re-running the split

```bash
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/make_kleb_splits.py
```

Seeded and reproducible; built from the committed CSV snapshot of the (stable) curation sheet.

## Environment

Shared monorepo uv env (`uv run …`). Heavy ENA/EBI lookups and any model fan-out belong in
SLURM, not the login node (see global CLAUDE.md). Prefer structured JSON/YAML for every
grading step; keep the rubric in the single-source-of-truth `attributes.yaml`.
