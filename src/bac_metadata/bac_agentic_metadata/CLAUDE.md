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
> **⚠️ ACTIVE WORK — read [`PROGRESS_REPORT.md` §5](PROGRESS_REPORT.md) if resuming.** The engine is
> consolidated to **one in-process driver** (`engine/run_full_metadata_agent.py`), fronted by thin wrappers —
> `applications/klebsiella/run_klebsiella.sh` (curation) and `evaluation/run_folds.sh` (curation + the
> gold-comparison scorecard) — with the curator tools in `engine/cli/` (`escalate`, `run_health`,
> `attach_papers`, `accumulate`). The legacy per-stage `run_*` / `report_*` scripts + `run_pipeline.sh` are
> **retired**; curation **accumulates across batches** into a growing master (`engine/accumulate.py`). The
> benchmarked folds + the whole >100-sample tail are **done and accumulated**. What remains (§5): the
> `collection_date` downstream wording (gating — apply *before* the at-scale runs so they grade under the
> hardened rule); the **M. abscessus** first exploratory pass (10 biggest studies → refine
> `m_abs/attributes.yaml`); a **publishable Klebsiella per-study table** + **collaborator plots**
> (raw→manual→agent completeness/accuracy); and the rest of the cohort at scale (the [50,99] band overnight,
> then <50).

## Layout

```
bac_agentic_metadata/
  engine/                 # the engine + the whole pipeline:
                          #   run_full_metadata_agent.py (in-process driver), stages.py (one fn/stage),
                          #   accumulate.py + cli/ (curator CLIs escalate/run_health/attach_papers + accumulate), run_health_report.py,
                          #   reference_outputs/ (byte-for-byte gate), + mechanics (grader, paper_finder,
                          #   backfill, sample_extractor, escalation, ena_sizing, fulltext, …)
  evaluation/             # fold + manual-curation validation + run_folds.sh (driver + scorecard benchmark):
                          #   make_splits, freeze_study_setting, validate_*, summarise_agent_vs_manual
  applications/
    klebsiella/           # the app: attributes.yaml (rubric), export_base_table.py,
                          #   run_klebsiella.sh (canonical driver wrapper), data/
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

For Klebsiella use the thin wrappers that inject the app paths — don't call the driver directly:
`applications/klebsiella/run_klebsiella.sh <driver args>` (curation; the production/tail entry) and
`evaluation/run_folds.sh <fold> <tag> <paper-source>` (driver **+** the gold-comparison scorecard — the
train/val/test benchmark; the byte-for-byte gate is `run_folds.sh train,val train curated`). Long runs are
interactive — on a usage-limit stop, re-run the same command and the disk cache resumes instantly. Curator
loop: `engine.cli.attach_papers` (hand-downloaded PDFs → `manual_download/`), `engine.cli.escalate
--interactive|--apply`, `engine.cli.run_health`.

Everything runs on the shared monorepo uv env (`uv run …`). Backends behind `engine.llm.LLMClient`:
**subscription** (`claude -p`, default, zero API cost) and **api** (paid, forced-tool-use JSON). The disk
cache key is backend-independent (`temperature=0`), so a result graded once is reused verbatim and reruns are
free/deterministic; caches + `manual_download/` + the API key are gitignored. Locally, point at the OneDrive
data mirror with `BACHGT_PROJECT_K_ROOT="…/project_k" BACHGT_PROJECT_K_USER=data` (HPC needs no config).
Under that root (ask-don't-dig): raw ENA TSVs at `data/raw/metadata/`; the manual gold `metadata_v2` at
`data/final/metadata/metadata_final_curated_all_samples_and_columns.tsv` — its `*_parsed` columns are what
scoring compares against, and `run_folds.sh`'s `GOLD` / `accumulate --canonical` default to it. Heavy ENA/EBI
lookups and model fan-out belong in SLURM, not the login node.

## Run-health closes the curator loop

`engine.cli.run_health` grades every (study × field) as **FILLED / ACTIONABLE / BLOCKED / EXHAUSTED** and
emits **"ALL CLEAR — curated to gold standard"** only when ACTIONABLE *and* BLOCKED are both 0 (it always
exits 0 — the verdict is the signal, never a hard block). ACTIONABLE drives an iterate-until-clear loop: fetch
a paper (`manual_download/<acc>.pdf`, via `attach_papers`), add a per-sample supplementary table
(`manual_download_supp/<acc>.{xlsx,csv,docx}`, parsed by `local_supplements.py` and consumed by the per-sample
stage), or answer an escalation (`escalate`). A genuinely dead-end gap is retired only by an explicit,
auditable `study_lv_attributes/escalation/accepted_unrecoverable_<tag>.tsv` — never by code assuming it.

**David's requirement — test the manual-supp-table workflow explicitly; never trust a silent 0.** Whenever it
is exercised, assert all three outcomes visibly: added+joinable → **FILLED** (manual filename shown in the
per_sample outcome `table`); added+unparseable → loud `[WARN]`, stays **ACTIONABLE**; added+parses-but-
unanchored → outcome note `…unanchored…`, run-health **BLOCKED `needs_linkage`**.

## Editing the engine or rubric — gotchas

- **Byte-for-byte gate.** `engine/reference_outputs/{study_grades,per_sample_applied,backfill_applied}_train.tsv`
  are the train,val outputs under the final rubric; any behaviour-preserving change must reproduce them
  exactly (sort rows, plain compare) — the driver passes this today. Read the base table with
  `keep_default_na=False` so ENA's literal `"NA"` survives the CSV round-trip.
- **The base table must be full-width (per-sample anchoring columns).** `base_table.csv` (from
  `export_base_table.py`) must carry `sample_alias` / `sample_title` / `secondary_sample_accession` /
  `accession` — per-sample extraction anchors supplementary-table rows to samples **by value** using the
  strain names in them. A stale/slim export silently under-extracts strain-keyed studies: it cost the
  **train-fold gate** its strain-keyed fills (the 12,937-line divergence, since fixed & verified green). It did
  **not** affect the >100 tail — the tail re-run on the full-width base confirmed zero recovery; the tail's
  "field-bearing but unanchored" studies fail for genuine reasons (PDF-only tables, strain IDs absent from
  ENA, manifest-only two-table joins). The driver now **fails loud** at startup if the anchor cols are
  missing; re-export with `export_base_table.py` to fix.
- **Editing the rubric re-grades everything.** The grader prompt renders each field's `whole_project_value`,
  so editing those texts in `attributes.yaml` busts the grading cache → a full re-grade. (This is why the
  `collection_date` hardening currently lives only in `engine/escalation.py`; reapplying it to the yaml is a
  deliberate, accepted re-grade — PROGRESS_REPORT §5.)
- **Big-decision denominator is whole-cohort.** The ≥1% leverage gate is measured against the whole-cohort
  taxon count (base `scientific_name` match, ~90,117), NOT the batch-local sizing — the driver computes and
  passes it to `escalate_detect`. A batch-local denominator flags every large tail study.

## Re-running the split

```bash
uv run python src/bac_metadata/bac_agentic_metadata/evaluation/make_splits.py
```

Seeded and reproducible; built from the committed CSV snapshot of the (stable) curation sheet.
