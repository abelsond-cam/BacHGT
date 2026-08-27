# PROJECT_STATE.md — BacHGT

**Last verified: 2026-08-27 @ `dev`** · scope: the metadata layers (agentic-metadata engine + Klebsiella
application; metadata_v2), incl. combine-build B1 (`v2_overwrite_candidates` reconciled EXACT to §5c). Every
number below names the artifact it was read from; a number without a path is a quotation, not a fact. Where this
file and any other doc/memory disagree, **this file wins**.

## 0. How to use — who owns which fact
- **This file is the single authority on current state, status, numbers, and next-steps.** Read it first.
- **Sub-project docs hold mechanics + argument, not state.** In particular:
  `src/bac_metadata/bac_agentic_metadata/PROGRESS_REPORT.md` (engine design, HITL, the argument for results) and
  `src/bac_metadata/METADATA_v2_README.md` (v2 schema/row-keying/rebuild). Numbers there are illustrative; the
  numbers **of record** are in §3 here.
- **The reviewable results deliverable** is the frozen
  `…/applications/klebsiella/data/Kp_AGENTIC_METADATA_WRAPUP_REPORT.md` (methods + every headline figure traced
  to its source). This file links to it; it is not duplicated here.
- Update this file **in the same commit** as any work that changes a fact, and re-stamp the header.

## 1. What this project is · deliverables
The **Klebsiella-genomics monorepo**: pangenome / GPA / mobile-element analysis of the *Klebsiella pneumoniae*
species complex, plus a **species-agnostic agentic metadata-curation engine** (now also applied to
*M. abscessus*). One git repo, one shared uv env, seven `src/bac_*` subpackages + the `bac_agentic_metadata`
engine. **Active deliverable stream (this file's focus):** a re-curated Klebsiella metadata table (agent-filled
country/collection_date/isolation_source/host + study-level judgements) to be combined into the canonical
**metadata_v2**, with a publishable per-study table and a methods+results wrap-up.

## 2. Repo map (+ DEAD PATHS)
```
src/bac_metadata/
  bac_agentic_metadata/     ← LAYER A (engine) + applications (Klebsiella, m_abs)
    engine/                   driver, stages, accumulate, gates, cli/
    evaluation/               wrapup_report, completeness_by_split, build_per_study_table, verify_* gates
    applications/klebsiella/  attributes.yaml (rubric) + data/ (run_progress/<tag>/, curated/, inputs/…)
    applications/m_abs/        ← LAYER C (deferred)
  pp/                        ← LAYER B: metadata_v2 curation (metadata_curation.py, build_metadata_v2.py, rebuild_v2.sh)
  METADATA_v2_README.md      v2 authority doc
src/bac_panaroo · bac_ariba · bac_data · bac_isescan · bac_complete_genomes · bac_kleborate  ← LAYERS D–I (stubs)
```

| DEAD / MOVED PATH | Status |
|---|---|
| `…/klebsiella/data/WRAPUP_REPORT.md` | **RENAMED** → `Kp_AGENTIC_METADATA_WRAPUP_REPORT.md` (2026-07-22, `Kp` prefix for a future m_abs one). |
| scratchpad `blast_radius.py` | **RETIRED** → committed `engine/overwrite_radius.py` + `evaluation/verify_overwrite_radius.py`. |
| per-stage `run_*` / `report_*` scripts, `run_pipeline.sh` | **RETIRED** — one driver `engine/run_full_metadata_agent.py`. |
| PIPELINE_PLAN / STAGE0–2 / reproduction-gate docs | **RETIRED** → `PROGRESS_REPORT.md`. |
| `metadata_curated_master_merged.tsv` | the canonical merge onto the **v1** table, NOT v2 (see Layer B caveats). |

## 3. LAYERS

### Layer A — Agentic-metadata engine + Klebsiella application
- **Status:** DONE + accumulated for the whole Klebsiella cohort; wrapped up. Species-agnostic engine (spec-
  driven) with always-on gates. **In tidy-up** (this round): docs/state, per-study table, v2-combine scoping.
- **Numbers of record:**
  - Accumulated master `…/klebsiella/data/curated/metadata_curated_master.tsv` = **96,291 samples** (all base
    rows) / **1,912 studies** (`…/curated/metadata_curated_master_summary.md`); **90,117** match the Klebsiella
    taxon (`PROGRESS_REPORT.md` §what-this-is). 7 tranches accumulated: train, test, tail100, tail50_99,
    tail25_49, tail10_24, sub10.
  - **Study-count reconciliation** (the three figures that looked like drift are three real populations):
    **1,912** study_accessions in the master summary (includes the RefSeq/NCTC *collection* pseudo-studies) ⊃
    **1,911** real ENA studies in `…/data/per_study_accession_table.tsv` (pseudo-studies dropped) ⊇ **~1,909**
    with study-level grades (a couple ungraded).
  - Papers (`Kp_AGENTIC_METADATA_WRAPUP_REPORT.md` §2): **1,914 studies reviewed · 952 papers found · 864
    full-texts read · 90 manual PDFs**. (">1,700" is true of *studies reviewed*, not distinct papers.)
  - Experimental-evolution excluded (§3, master `study_type_excluded==True`): **78 studies / 1,489 samples**.
  - Completeness lift, agent − v2 gold on the 83,780-sample cohort excl. Refseq (§4 / `scorecard/
    final_completeness_raw_agent_gold.tsv`): country **+3.6**, collection_date **+7.9**, isolation_source
    **+6.3**, host **+10.4** pp — agent matches-or-beats v2 on every field.
  - Accuracy vs manual (§5a, adjudicated, gold folds): **train +0.108** (agent 0.974 vs manual 0.866); **test
    +0.028** (agent 0.953 vs manual 0.925) — the earlier "+0.037" was stale, corrected 2026-07-22.
- **In flight:** WS1 docs/PROJECT_STATE (this commit); WS2 per-study table extension; WS3 v2-combine scoping.
- **Next:** curator adjudication sign-off (`diagnostics/adjudication_review_queue.tsv` via
  `review_adjudication`); then it gates the v2 adjudicated-overwrite pass (Layer B).
- **Caveats:** master + summary are **gitignored** (regenerable via `engine.cli.accumulate`); the tracked
  artifacts are the filled_metadata per tag, the wrap-up report, and the per-study table. `--carry-forward` only
  for a band's FIRST run; base_table must stay full-width; editing the rubric re-grades everything.
- **Owns:** the agent-filled per-sample metadata + study-level grades; the completeness/accuracy benchmark.

### Layer B — metadata_v2 (the canonical table) + the agentic→v2 combine
- **Status:** v2 is the authoritative curated table (built by `pp/build_metadata_v2.py` + `rebuild_v2.sh`).
  The agentic→v2 combine is **DESIGNED + prototyped against the v1 table only; NOT yet done against v2**.
- **Numbers of record:**
  - v2 = `metadata_v2_all_samples_and_columns.tsv` — **86,398 rows × 505 cols** (`METADATA_v2_README.md` line 3),
    row key **`Sample`** (LR-assembly accession when a long read exists, else SR BioSample); SR↔LR link via
    **`sr_biosample`**. **HPC-only** path: `…/rds/.../david/final/metadata_v2_all_samples_and_columns.tsv` —
    **not on the local OneDrive mirror** (verified 2026-07-22).
  - Canonical merge already produced = `…/curated/metadata_curated_master_merged.tsv` = **90,903 rows** (human >
    agent > ENA) — but onto the **v1** table (`metadata_final_curated_all_samples_and_columns.tsv`), which lacks
    v2's SR↔LR / typing / AST columns. Agent fills into human-blank cells (PROGRESS_REPORT §4c): country 4,856 /
    date 9,121 / iso 7,218 / host 7,410.
- **In flight:** the **two-step combine build** (David, 2026-08-26: "blank-fill first reviewable pass + numbers"
  → "surface examples + a reviewable artefact" → "apply overwrites after checking with me"). Scoped in
  [`bac_agentic_metadata/MERGE_TO_V2_RUNBOOK.md`](src/bac_metadata/bac_agentic_metadata/MERGE_TO_V2_RUNBOOK.md);
  build phases B1–B4.
  - **B1 DONE (2026-08-27):** `evaluation/report_v2_overwrites.py` → `data/v2_overwrite_candidates.{tsv,md}`
    — the reviewable step-(ii) artefact, built locally from committed repo data. **Reconciles EXACT to §5c:
    3,105 candidates** (iso 2,037 · date 1,014 · host 38 · country 16), of which **3,015 genuinely change** the
    value. Review-critical rows surfaced: all **16 country** overwrites are `Switzerland→{Myanmar,USA,…}` (one
    study PRJNA744003 — concrete→concrete, ENA submitting-lab-country error); **4 date year-changes + 3
    unparseable** flagged; 29 benign `shortened` (`Blood_Blood`→`Blood`); 90 inert `no_change`. `classify()`
    unit-tested (`tests/test_report_v2_overwrites.py`, 4 tests).
  - **B2 DONE (2026-08-27):** `combine/inject_agentic_into_v1.py` — step-(i) blank-fill onto v1 (via engine
    `merge_into_canonical`, human `_parsed` > agent > ENA) + re-normalise the filled rows with v1's own
    `pp/metadata_curation` parse/categorise (v1 `main` order) + evolutionary handling. **Verified on the v1
    mirror:** row count preserved (90,903); blank-fills country 6,835 / date 9,020 / iso 9,863 / host 12,942
    (completeness 87.8→95.3 / 78.9→88.9 / 69.8→76.9 / 77.2→91.2 %); **re-parse blast radius = the 22,433
    filled rows only** (derived cols byte-identical on every other row — checked); **no curated (`_parsed`
    non-blank) bare value overwritten** (checked); evolutionary 1,489 master → **1,055 present in v1** (1,071
    rows, `kpsc_final_list=False`) = 1,045 SR-only + 26 LRA-bearing, **434 absent from v1** (v1 ⊂ master
    cohort; real match happens against v2 on CSD3); `is_kpsc` left alone (taxonomic). 4 unit tests
    (`tests/test_inject_agentic_into_v1.py`). Note: iso/host "replaced unparsed raw ENA" (3,464 / 259) are
    agent beating an un-curated raw ENA bare value — still within human > agent > ENA, surfaced in the report.
  - **B3–B4 pending:** B3 `apply_gated_overwrites` + post-kleborate evolutionary-delist hook (clears the
    CSD3-only quality flags for the LRA-bearing evo rows) · B4 runbook/PROJECT_STATE update for the CSD3
    orchestration.
  Candidate sizing of record: **16 study-level** (await `david_verdict` sign-off) + **3,105 per-sample**
  (iso 2,037 · date 1,014 · host 38 · country 16).
- **Next:** CSD3 is SSH-reachable again (2026-07-22) — the run executes there (v2 lives on CSD3). Gated on the
  adjudication sign-off + the parse/categorise-architecture decision (runbook Decisions; README §16).
- **Caveats / OPEN:** (1) combine policy decided = **blank-fill + adjudicated overwrites**; normalisation =
  **v2's hardcoded `pp/metadata_curation.py` parse/categorise** (decisions of record §6). (2) **Open
  reconciliation:** the RefSeq/NCTC carve-out is **3,513 RefSeq + 97 NCTC samples** in the completeness scorecard,
  vs a "~398 assembly genomes out-of-scope for the merge" figure in PROGRESS_REPORT §merge-readiness — these are
  different quantities (benchmark samples vs orphan-genome subset); the ~398 needs a cited source before it is of
  record. (3) production write into metadata_v2 is gated (§5; README §16 = contact David before any rebuild).
- **Owns:** the canonical table, SR↔LR linkage, all v2-only column groups, and the parse/categorise vocabulary.

### Layer C — M. abscessus agentic application — **DEFERRED (out of scope this round)**
- Whole-cohort `mabs_all` run complete (133 studies / 6,455 samples; cf_status 57.8%); rubric committed
  (`09fd292`). **Remaining (a later round):** the 23-decision escalation walk, accumulate → master, and the
  decision on git-tracking the m_abs data tree. State detail: `PROGRESS_REPORT.md` §9.

### Layers D–I — bac_panaroo · bac_ariba · bac_data · bac_isescan · bac_complete_genomes · bac_kleborate
- **State not yet consolidated here** — see each subpackage's `CLAUDE.md`. Fold into this file as each gets
  active attention.

## 4. Artifact dependency table (Layer A/B)
| Artifact | Produced by | Consumed by | Invalidated when |
|---|---|---|---|
| `inputs/base_table.csv` | `applications/klebsiella/export_base_table.py` | every stage | ENA re-export |
| `run_progress/<tag>/…` (find→grade→per_sample→backfill→escalation→fill) | `engine/run_full_metadata_agent.py` | accumulate, gates, reports | rubric edit (re-grade) |
| `curated/metadata_curated_master.tsv` (+ summary) | `engine.cli.accumulate` | per-study table, completeness, merge | any tranche re-accumulated |
| `Kp_AGENTIC_METADATA_WRAPUP_REPORT.md` | `evaluation/wrapup_report.py` (via `refresh_wrapup_report.sh`) | humans (review) | master or scorecard change |
| `scorecard/final_completeness_raw_agent_gold.tsv` | `evaluation/completeness_by_split.py` (needs v2 gold) | wrap-up §4 | master or gold change |
| `per_study_accession_table.tsv` | `evaluation/build_per_study_table.py` | humans (publishable) | master change |
| `v2_overwrite_candidates.{tsv,md}` | `evaluation/report_v2_overwrites.py` | David (step-iii sign-off), `combine.apply_gated_overwrites` (B3) | per-tranche `per_sample_applied` change |
| injected v1 (step i; local test / CSD3 inject) | `combine/inject_agentic_into_v1.py` (needs v1 + master) | `rebuild_v2.sh` cascade (CSD3) | master change or v1 re-issue |
| `curated/metadata_curated_master_merged.tsv` | `engine/accumulate.py::merge_into_canonical --canonical` | (pending v2 combine) | master or canonical change |
| `metadata_v2_all_samples_and_columns.tsv` | `pp/build_metadata_v2.py` + `rebuild_v2.sh` | downstream analyses | `rebuild_v2.sh` |

## 5. Shared infrastructure & cluster truth
- One shared uv env (`uv sync`; run via `uv run`). LLM backend default = subscription `claude -p` (zero API
  cost); disk cache is content-addressed, so re-runs are free/deterministic.
- **v2 gold / mirror:** the v1 gold `metadata_final_curated_all_samples_and_columns.tsv` (239 MB) **is** on the
  local OneDrive mirror `…/OneDrive-…/Aaron Weimann's files - project_k/data/final/metadata/` (point
  `BACHGT_PROJECT_K_ROOT` there when HPC is down). The **built v2 table is HPC-only** (CSD3
  `…/david/final/`) — so the WS3 v2 combine **cannot run locally** until the v2 table is copied to the mirror or
  the combine is run on CSD3. Per global guidance CSD3 was restored 29 Jul 2026; **confirm access each session.**

## 6. Decisions of record (dated)
- **2026-07-22** — This tidy-up round is **Klebsiella-only** (m_abs deferred). Per-study table stays
  Klebsiella-shaped. v2 combine policy = **blank-fill + adjudicated overwrites**. Re-normalisation of added
  fills = **v2's hardcoded `pp/metadata_curation.py` parse/categorise** (keeps v2 vocab stable). v2 combine
  **architecture = A: inject the agent fills at v1 + run `rebuild_v2.sh` as a separate, reviewable step** (NOT
  in-place — so the merged v2 can be reviewed before it becomes production). Study-level adjudication queue is
  fully reviewed (16 rows: 14 `manual`, 2 `skip`) → no study-level overwrites to apply. Wrap-up report renamed
  `Kp_AGENTIC_METADATA_WRAPUP_REPORT.md` + gained a Methods (§0) section. This `PROJECT_STATE.md` created.
- **2026-07-22 (v2 evolutionary-sample handling)** — the 78 experimental-evolution studies / 1,489 samples get,
  in v2: an `evolutionary_lab_sample=True` flag (records what was done), `kpsc_final_list=False` (removed from
  the cohort; `is_variant_called` follows), and `is_complete`/`is_hybrid`/`is_reference_genome` **checked +
  cleared** (count on CSD3 first, surface before flipping). Rows kept for the record, not deleted. See
  `MERGE_TO_V2_RUNBOOK.md` Step 2b.
- **2026-07-21/22 (m_abs)** — overwrite-radius promoted to an engine always-on gate (`083fe93`); `smoking_status`
  dropped + `host` defined as organism-at-sampling (`09fd292`); cf non-CF-by-absence rule (`a7efc..` series).
- **Earlier** — keep the per-sample fidelity judge (vague→specific overwrites allowed); `never_overwrite`
  protects the headline phenotype; whole-project fill only on the ≥95% majority rule.

## 7. Retired documents index
- `WRAPUP_REPORT.md` → renamed (§2). · PIPELINE_PLAN / STAGE0–2 / reproduction-gate → `PROGRESS_REPORT.md`. ·
  `~/.claude/PROGRAM_PLAN_2026-05-30.md` → superseded. · `ToDo.md` → living tracker; points here for state.
