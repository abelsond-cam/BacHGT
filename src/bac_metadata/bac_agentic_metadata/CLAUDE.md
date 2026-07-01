# CLAUDE.md — bac_agentic_metadata

The **reusable, species-agnostic agentic metadata-curation engine** inside `bac_metadata`.
The engine is the product; *Klebsiella* and *M. abscessus* are **application sites** of it.
Parent guidance: [`../CLAUDE.md`](../CLAUDE.md) (bac_metadata),
[`../../../CLAUDE.md`](../../../CLAUDE.md) (monorepo), `~/.claude/CLAUDE.md` (global).

> **Read first:** [`PROGRESS_REPORT.md`](PROGRESS_REPORT.md) — the collaborator-facing overview: the aim, the
> engine design, the human-in-the-loop steps, the Klebsiella application + its results vs. manual curation,
> where the re-curation stands, and the forward plan. (It supersedes the former PIPELINE_PLAN / STAGE0–2 /
> reproduction-gate docs.) The rubric itself is `applications/klebsiella/attributes.yaml`.
> **Grading definitions are David's — do not invent grading criteria; change them only with David.**
>
> **⚠️ ACTIVE WORK — read [`PROGRESS_REPORT.md` §10 + §12](PROGRESS_REPORT.md) FIRST if resuming.** The
> engine is consolidated to **one in-process driver** (`engine/run_full_metadata_agent.py`, byte-identical
> to the legacy `run_pipeline.sh`), and curation now **accumulates across batches** into a growing master
> (`engine/accumulate.py`). What remains (§12): **retire** the legacy `applications/klebsiella/` stage
> scripts + `run_pipeline.sh` — moving the curator-loop tools to `engine/cli/` first — and add the thin
> `run_klebsiella.sh` entry, then run the uncurated tail. Those legacy scripts still physically exist and
> still run until that step lands.

## Layout

```
bac_agentic_metadata/
  engine/                 # the engine + the whole pipeline:
                          #   run_full_metadata_agent.py (in-process driver), stages.py (one fn/stage),
                          #   accumulate.py + cli/ (build-up across batches), run_health_report.py,
                          #   reference_outputs/ (byte-for-byte gate), + mechanics (grader, paper_finder,
                          #   backfill, sample_extractor, escalation, ena_sizing, fulltext, …)
  evaluation/             # fold + manual-curation validation: make_splits, freeze_study_setting,
                          #   validate_*, summarise_agent_vs_manual
  applications/
    klebsiella/           # the app: attributes.yaml (rubric) + export_base_table.py + data/
                          #   (+ legacy run_*/report_*/run_pipeline.sh — being retired, PROGRESS_REPORT §6)
      diagnostics/        # one-off probes (diagnose_*, assess_*) — not in the pipeline
      data/               # task-aligned tree (folders mirror the pipeline steps):
        inputs/             #   curated study-level snapshot + base_table (gitignored)
        fold_splits/        #   project_splits.tsv
        ena_assessment/     #   ena_sizing / ingest / assessment_report
        find_papers/        #   found_papers*, find_validation/adjudication, missing_papers,
          manual_download/  #     manually-downloaded <accession>.pdf (paywalled-paper fallback)
        study_lv_attributes/  # study-level: grading/ , whole_study_backfill/ , escalation/
        sample_lv_attributes/ # sample-level: per_sample/   (per-sample table extraction)
        curated/            #   accumulation stores + master (curated_escalations.tsv versioned; rest gitignored)
        scorecard/          #   agent_vs_manual + completeness (final measurement)
        diagnostics/        #   curator_gold, gt_corrections, gap/decline reports
        logs/  cache/       #   run logs; regenerable LLM/ENA/fulltext/find/per_sample caches
    m_abs/                # attributes.yaml, ATB_metadata_Mabs_2025_release.xlsx, CLAUDE.md
  PROGRESS_REPORT.md      # collaborator-facing overview (aim, design, results, plan)
```

## Core ideas (one line each)

- **Unit of work = project accession** (`study_accession`); process biggest-first.
- **Attribute spec is the rubric**, one `attributes.yaml` per application, three classes:
  study filters, study-level judgements (read from the paper), per-sample completeness/backfill.
- **Hybrid ground truth**: generalised spec + a *frozen* Klebsiella instance. Validate only
  against `study_level` cols A–K + the `parsed_per_project` tab; never `*_added`/`ATB_*_prop`.
- **Iteration discipline**: tune on train+val; the test fold stays sealed.

## Running the engine

One in-process driver runs every stage — `engine/run_full_metadata_agent.py`, data-driven via
`--spec / --table / --data-dir / --splits / --sizing / --snapshot`. Selection modes: `--fold train,val`
(splits) and `--min-study-size N` (size-band tail). `--carry-forward` builds onto the accumulated master;
`--manual-curation <gold>` turns on the agreement comparison (absent → skipped, e.g. M. abscessus);
`--paper-source finder|curated` + `--web-fallback` control finding. Rebuild the master:
`python -m …engine.cli.accumulate --tags train,test,tail100 [--canonical <gold>]`.

Everything runs on the shared monorepo uv env (`uv run …`). Backends behind `engine.llm.LLMClient`:
**subscription** (`claude -p`, default, zero API cost) and **api** (paid, forced-tool-use JSON). The disk
cache key is backend-independent (`temperature=0`), so a result graded once is reused verbatim and reruns are
free/deterministic; caches + `manual_download/` + the API key are gitignored. Locally, point at the OneDrive
data mirror with `BACHGT_PROJECT_K_ROOT="…/project_k" BACHGT_PROJECT_K_USER=data` (HPC needs no config).
Heavy ENA/EBI lookups and model fan-out belong in SLURM, not the login node.

## Editing the engine or rubric — gotchas

- **Byte-for-byte gate.** `engine/reference_outputs/{study_grades,per_sample_applied,backfill_applied}_train.tsv`
  are the train,val outputs under the final rubric; any behaviour-preserving change must reproduce them
  exactly (sort rows, plain compare) — the driver passes this today. Read the base table with
  `keep_default_na=False` so ENA's literal `"NA"` survives the CSV round-trip.
- **Editing the rubric re-grades everything.** The grader prompt renders each field's `whole_project_value`,
  so editing those texts in `attributes.yaml` busts the grading cache → a full re-grade. (This is why the
  `collection_date` hardening currently lives only in `engine/escalation.py`; reapplying it to the yaml is a
  deliberate, accepted re-grade — PROGRESS_REPORT §5–§6.)
- **Big-decision denominator is whole-cohort.** The ≥1% leverage gate is measured against the whole-cohort
  taxon count (base `scientific_name` match, ~90,117), NOT the batch-local sizing — the driver computes and
  passes it to `escalate_detect`. A batch-local denominator flags every large tail study.

## Re-running the split

```bash
uv run python src/bac_metadata/bac_agentic_metadata/evaluation/make_splits.py
```

Seeded and reproducible; built from the committed CSV snapshot of the (stable) curation sheet.
