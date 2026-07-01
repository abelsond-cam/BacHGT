# PROGRESS REPORT — bac_agentic_metadata

**The single living doc for the engine** — what it is, how it runs, the architecture + ground-truth
discipline, the measured results, and the forward plan. (Supersedes the former `PIPELINE_PLAN.md`,
`STAGE0_kleb_curation_map.md`, `STAGE1.md`, `STAGE2.md`, and `REPRODUCTION_GATE_INVESTIGATION.md`, all now
folded in here and deleted.) Authoritative metadata_v2 description: [`../METADATA_v2_README.md`](../METADATA_v2_README.md).

_Last updated 2026-06-30. Scope: the Klebsiella validation site. The 47-accession test fold is re-gated; the
uncurated **>100-sample tail has run** (§12); and a **consolidation into one engine + one entry point is IN
PROGRESS — see §12 (read it first if you are resuming this work).**_

---

## 1. What the engine is + status

A **reusable, species-agnostic agentic metadata-curation engine.** The engine is the product; *Klebsiella*
and *M. abscessus* are **application sites**. The unit of work is the **project accession**
(`study_accession`), processed biggest-first. For each accession it finds the describing paper, grades it
into a configured **attribute spec** (`attributes.yaml`), and backfills the four per-sample clinical fields
(`country`, `collection_date`, `isolation_source`, `host`) from the paper — measuring everything against a
frozen Klebsiella gold standard (`metadata_v2`).

**Status (2026-06-26): the test fold beats `metadata_v2` on all four fields, through a pipeline whose
human-in-the-loop reproduction has been proven.** A clean STASH-and-rerun reproduction test (§9) exposed a
real collapse, which was root-caused to five structural holes and fixed; the corrected pipeline re-gates the
sealed test fold to **agent ≥ v2 on all four fields, residual gap 0.0**:

| field | ENA baseline | **agent (corrected pipeline)** | v2 (manual) |
|---|---|---|---|
| country | 0.665 | **0.959** | 0.848 |
| collection_date | 0.644 | **0.936** | 0.764 |
| isolation_source | 0.602 | **0.742** | 0.702 |
| host | 0.531 | **0.836** | 0.766 |

Grading quality is likewise above manual: on the sealed test fold, adjudicated **agent accuracy 0.96 vs
manual 0.90** (paper-finding tie 0.92; `amr_study` 0.97 vs 0.86; `study_setting` 1.00 vs 0.93). Two LLM
backends sit behind `engine.llm.LLMClient` — **`subscription`** (`claude -p`, zero API spend, default) and
**`api`** (paid) — with a backend-independent disk cache that makes reruns deterministic and free.

---

## 2. The pipeline — `run_pipeline.sh "<FOLD>" "<TAG>"`

The same command runs the train+val dress rehearsal (`"train,val" train`) and the sealed test one-shot
(`"test" test`), writing `<TAG>`-suffixed artifacts into the task-aligned `data/` tree. **Per-sample runs
BEFORE whole-field** (the accurate per-isolate source first; the coarse study-wide fallback only on what it
leaves — see §9 HOLE 5). Stage 0 (ENA assessment) is a fold-agnostic prereq run once.

0. **ENA assessment** (`run_ena_assessment.py`, no LLM) — per-accession sizing from ENA `read_run` (deduped
   to sample level — see §7), umbrella detection, three-state completeness.
1. **Find papers + resolve full text** (`run_find_papers.py`) — 3-tier finder (deterministic retrieval →
   secondary-accession ERP/SRP → web-search fallback); the LLM only picks among retrieved candidates
   (grounded; abstains when unsure). Full text via Europe PMC → abstract → PDF, with a manual-download
   `<accession>.pdf` fallback for paywalled papers (`engine/local_papers.py`).
2. **Adjudicate papers found** (`validate_find_papers.py --adjudicate`) — opposing Opus rules finder-vs-curated mismatches.
3. **Study grading + adjudication** (`run_study_grading.py` + `validate_study_grading.py --adjudicate`) —
   grade the paper into the `attributes.yaml` schema; Opus adjudicates grader-vs-sheet disagreements.
   Grading consumes the manual PDFs from stage 1 (`resolve_fulltext_for_accession`, the shared resolver).
4. **Missing-papers worklist** (`report_missing_papers.py`) — the loop point: studies still lacking full
   text → human downloads → `link_local_papers.py` → `manual_download/` → next run's grading picks them up.
5. **Per-sample extraction — FIRST** (`run_per_sample_extract.py`) — per-isolate values from supplementary
   tables (xlsx/csv/DOCX/PDF, direct + two-hop, value-verified), over **every ENA-incomplete (gated) study**
   with a paper (grade-independent gate). The accurate source gets first crack at every field.
6. **Whole-field backfill — guarded** (`run_backfill.py --per-sample …`) — study-wide fills for the gaps
   per-sample LEFT, with the **parsimony guard**: never overwrites a per-isolate value, never whole-fills a
   `(study,field)` per-sample proved heterogeneous (≥2 distinct values). Writes the gate report (covered if
   per-sample OR whole-field resolved it; else `residual_per_sample`).
   - **6b. Per-sample supplement worklist** (`report_persample_supplements.py`) — per residual study, does
     the paper hold a per-isolate table? → manual-table fetch worklist (non-blocking).
7. **Escalation detect** (`run_escalations.py`) — whole-field declines worth a human decision → curator
   queue. **Always escalates BIG decisions** (any study ≥1% of the whole cohort's taxon samples) regardless
   of the tight/wide triage, plus the tight-cluster near-misses; the triage reads the same paper grading did.
8. **Apply curator decisions** (`run_escalations.py --apply`) — fold the filled queue in as
   `curator_escalation` whole-field fills (non-blocking; skipped if unfilled). A queue `s`-skip records the decision.
9. **Outputs / scorecard** — value-fidelity (`validate_backfill_values.py`), cumulative completeness incl.
   escalation (`validate_backfill_completeness.py`), agent-vs-manual (`summarise_agent_vs_manual.py`).
10. **Run-health** (`report_run_health.py`) — the convergence/closure artifact: every (study×field) →
    FILLED / ACTIONABLE / BLOCKED / EXHAUSTED, verdict **ALL CLEAR** only when ACTIONABLE+BLOCKED are 0.
    Flags an un-escalated big-decision decline ACTIONABLE (never silently EXHAUSTED). Always exits 0 (loud, non-blocking).

`data/` is a task-aligned tree: `inputs/` · `fold_splits/` · `ena_assessment/` · `find_papers/`
(+`manual_download/`) · `study_lv_attributes/{grading,whole_study_backfill,escalation}/` ·
`sample_lv_attributes/per_sample/` · `scorecard/` · `diagnostics/` · `logs/` · `cache/` (gitignored).

---

## 3. Architecture & the attribute-spec model

```
bac_agentic_metadata/
  engine/                 # application-agnostic: spec, ena_sizing, paper_finder, grader, adjudicator,
                          #   fulltext, local_papers, backfill, sample_extractor, supplementary, escalation, …
  applications/
    klebsiella/           # attributes.yaml + frozen ground truth + split + run_*/validate_* + run_pipeline.sh
    m_abs/                # attributes.yaml + ATB xlsx (PARKED behind Klebsiella — see m_abs/PROJECT_PLAN.md)
```

Each application's **`attributes.yaml` is the single source of truth for the rubric** (David edits it
directly). Attributes fall in three classes:
1. **Study filters** — exclude a study from the cohort (Kleb: experimental-evolution).
2. **Study-level judgements** — cohort attributes read from the paper, often absent from structured data
   (Kleb: `study_setting`, `amr_study`; M.abs: `reports_AST`, with CF status + AST as per-sample fields).
3. **Per-sample completeness / backfill** — the four clinical fields: measure structured completeness,
   backfill from the paper. The **phenotype axis is a per-species slot** (Kleb = AMR-selection + setting;
   M.abs = CF status). Grading scale: `gradeable / partial / not_gradeable`. **Grading definitions are
   David's to supply** — do not invent grading criteria.

The grader renders the rubric **straight from `attributes.yaml`** (enums = the YAML value sets; prompt =
each attribute's `definition`), so adding/removing an attribute is a YAML edit, not a code change.

---

## 4. Ground truth & validation discipline

- The generalised attribute spec is the rubric; a **frozen Klebsiella instance is the validation target**
  (`metadata_v2` + the `study_level` Google sheet, snapshot
  `applications/klebsiella/data/inputs/study_level_metadata_all_combined_v1.0_20260105.csv`).
- **Column trust map:** `study_level` cols A–K (`paper_link`, `amr_study`, `study_setting`, `cohort_age`, …)
  are usable-but-imperfect ground truth; `parsed_per_project` is the more reliable per-project completeness
  record. **Never** validate against `*_added` / `ATB_*_prop` (David's work-tracking, not truth).
- The sheet is **curation, not ground truth** — an agent-vs-sheet number is *agreement*, and disagreements
  are ruled by an opposing **Opus adjudicator** (verbatim quotes). A recurring finding: ~20% of curated
  `paper_link`s are wrong/misattributed, which the engine surfaces rather than trusts.
- **Iteration discipline:** accessions split **train 78 / val 31 / test 47** at paper-group level (no paper
  leakage; seeded, reproducible). All tuning on train+val; the test fold stays sealed for one final run.

---

## 5. The manual curation it generalises (Klebsiella)

The engine replicates David's manual workflow: group ~90k samples by `study_accession`, rank by size, take
on studies **>130 samples** for curation (~75% of assemblies; threshold `filter_study_size=131` in
`pp/metadata_collation.py`). For each: read the EBI project record counts (total + *Klebsiella* by
`scientific name`) to know whether a paper covers the whole project or a subsample; find the best paper
(the one covering the largest part — one paper may serve several accessions); grade it for the study-level
attributes; backfill the four clinical fields. Manual→automated mapping: grouping/sizing/completeness/
normalisation are **deterministic**; paper-finding, grading, and field backfill are **LLM/agent judgement**
(grounded, abstaining, adjudicated). The deterministic parse/categorise pairs for the four fields already
exist in `pp/metadata_curation.py` (`parse_host`/`categorise_host`, etc.) and stay a downstream step.

---

## 6. Backends, caching, secrets

- **`subscription` (default, `ClaudeCliClient`)** — drives `claude -p` headless on the Claude Max plan, zero
  API spend. Schema embedded in the prompt + validated with one retry. On usage-window exhaustion the runner
  catches `UsageLimitError`, writes partials, and resumes from cache on rerun.
- **`api` (opt-in, `AnthropicClient`)** — paid Messages API with forced tool use (server-validated JSON).
  Key off-OneDrive: `ANTHROPIC_API_KEY` → `BAC_ANTHROPIC_KEY_FILE` → `~/.config/bac_metadata/anthropic_api_key`.
- The disk cache key is **backend-independent** (hash of model + system + user + schema + name), so a result
  graded once on either backend is reused verbatim by the other; `temperature=0`. Caches
  (`data/cache/{llm,ena,fulltext,find,per_sample_supp}`) + `manual_download/` + the API key are gitignored.
- **Local data paths** resolve via `path_resolve.project_k_user_dir()` from `BACHGT_PROJECT_K_ROOT` +
  `BACHGT_PROJECT_K_USER` (HPC needs no config; locally point at the OneDrive mirror with
  `BACHGT_PROJECT_K_ROOT="…/project_k" BACHGT_PROJECT_K_USER=data`).

---

## 7. ENA sizing calibration (technical note)

Query **`result=read_run`** and deduplicate to sample level, **not** `result=sample`: ENA reliably links
*runs* to a study but frequently not *samples* (e.g. `PRJEB74192` returns 0 samples but 3,831 runs / 3,261
distinct samples = the curated holding). So `ena_total_runs` matches the browser count and
`ena_total_samples`/`ena_taxon_samples` are distinct-sample counts from read_run. `ena_taxon_samples`
(scientific_name match) is a **lower bound** (under-counts for broad *Enterobacteriaceae* projects);
`ena_total_samples` the upper bound. Classification per accession: `whole_project` / `subsample` /
`shared_accession` / `umbrella` (≥3 child studies) / `ena_underlabels_klebsiella` (curation more complete,
not an error) / review-queue. Assembly-only BioProjects with no portal reads surface as anomalies, not silently dropped.

---

## 8. Measured results

### Grading — agent vs manual curation (adjudicated)

| fold | N judged | agreement | **agent acc** | manual acc | Δ |
|---|---|---|---|---|---|
| train+val | 274 | 0.84 | **0.97** | 0.88 | **+0.10** |
| **test (sealed)** | 114 | 0.85 | **0.96** | 0.90 | **+0.06** |

Adjudicated agent accuracy **0.96 out-of-sample** ≈ 0.97 train — beats manual everywhere. By attribute on
test: `amr_study` 0.97 vs 0.86, `study_setting` 1.00 vs 0.93, paper-finding 0.92 = 0.92. **Model-robust:**
re-running finder+grader with Opus-4.8 as the agent lands within noise (find adj. 0.86 vs 0.87, `amr_study`
0.97 vs 0.94) — two independent models converge, so it is not a Sonnet artifact. **Decision: Sonnet 4.6 is
the default agent; Opus 4.8 the independent adjudicator.** Scorecards: `scorecard/agent_vs_manual_*.{md,tsv}`.

### Completeness vs metadata_v2 — corrected pipeline

**Test fold (sealed, re-gated 2026-06-26):** agent ≥ v2 on all four, residual 0.0 (§1 table). Per-level
accounting (where each gain comes from) is in `data/scorecard/per_level_accounting_test.md`: country's gain
is now **human escalation 0.171** (not silent whole-field that mislabelled ~568 Ghana isolates as Italy);
date is **per-sample 0.105 + escalation 0.160**; iso/host per-sample-dominated. Run-health: 0 ACTIONABLE,
172 FILLED, 15 EXHAUSTED, 1 BLOCKED (PRJEB29738 iso — aggregate-only supplement, no per-isolate table).

**Train+val (re-gated 2026-06-26 under the corrected pipeline)** — agent ≥ v2 on all four, residual 0.0
(34,288 samples): country **0.933** (v2 0.882), collection_date **0.867** (v2 0.747), isolation_source
**0.729** (v2 0.669), host **0.870** (v2 0.789); 10,770 escalation fills from David's 27 decisions. Both
folds now reproduce above v2 through the same per-sample-first + guarded-whole-field + big-decision-escalation
pipeline. Run-health (dress rehearsal, not required ALL CLEAR like the sealed test) shows the normal
convergence worklist: 19 ACTIONABLE (18 fetch-supp-table for the iterate-to-clear loop + 1 big-decision audit
flag PRJNA604975) + 7 BLOCKED (needs_linkage — the unlinkable-table-adjudicator territory).

### Backfill value-correctness (where filled, is it right)

Whole-field is ~0.99–1.0 where it is the right model (country, host); per-sample gives the per-isolate
granularity whole-field cannot (`collection_date` 0.999 year-level, `isolation_source` 0.957 fidelity with
carriage-vs-invasive granularity preserved, `country` 0.999, `host` 1.0 semantic). RAW values only;
parse/categorise stays downstream. Reports: `*/backfill_value_*` and `*/per_sample_value_*`.

### Finding — 3-tier finder

Raw 0.70 → **adjudicated 0.87** (train+val); precision-when-committed ~0.94; abstentions 24→7 (6 findable
only with the curated link as a hint, 1 genuinely paper-less). Matching is by paper **identity** not URL
(union of curated rows + EPMC cross-id canonicalisation + `same_paper` adjudicator + prefer-published).
Web-search fallback recovered ~11 of the tail (e.g. PRJEB6574 → Holt 2015 PNAS).

---

## 9. The reproduction test — what it found + the five fixes (2026-06-26)

The clean STASH-and-rerun (stash the 54 manual PDFs / supp tables / escalation answers; archive+purge the
cache; rerun fresh; re-supply from the stash) is the thorough test of the *whole human-in-the-loop pipeline*.
It **exposed a real collapse**: on the test rerun, country/date whole-field completeness fell below v2,
localised (by token-free cache replay) to **ONE study — PRJEB27342 (SpARK, 17% of the fold)**. A
non-deterministic grade flip (identical prompt → `Italy/whole-project` one run, abstain the next) was the
*trigger*; it exposed five structural holes (all now fixed, commits `5fc7ee4` → `36ec359`):

1. **Escalation triage ran BLIND on paywalled-PDF studies** — `run_escalations` lacked the manual-PDF
   fallback grading uses → mis-triaged as wide_mix_skip. *Fix:* shared `resolve_fulltext_for_accession`.
2. **Uncertainty silently skipped, not escalated.** *Fix + David's rule:* **always escalate BIG decisions**
   (study ≥1% of the whole cohort's taxon samples), regardless of the tight/wide triage — a deterministic,
   LLM-free leverage gate, with the paper + grade + reasoning shown to the human.
3. **`per_sample_covered` suppressed a big study's residual gap.** *Fix:* big-decision studies bypass it.
4. **Run-health read the 5,413-sample drop as clear.** *Fix:* it now flags an un-escalated big-decision
   decline ACTIONABLE, never silently EXHAUSTED.
5. **Pipeline ORDERING was inverted** — whole-field ran first and *pre-empted* per-sample; a coarse
   study-wide "Italy" could sit on cells a per-isolate table resolves differently. *Fix:* **per-sample FIRST
   + parsimony guard** (`engine.backfill.per_sample_guards`): whole-field never overwrites a per-isolate
   value and never whole-fills a heterogeneous field.

A key correctness finding: the baseline's higher country (0.957) was **partly wrong** — PRJEB27342 is
Italy 85% / **Ghana 13%** (a Pattern-C aggregate), so "Italy for all" mislabelled ~568 isolates. The honest
resolution is the **human escalation** (now fires, David confirmed Italy for the SpARK subcohort), not a
silent whole-fill. The original failure — a large silent under-pickup reading ALL CLEAR — is now structurally
impossible. _Forensic assets retained:_ stash at `~/.bachgt_rerun_stash/`, baseline-replay cache at
`data/cache.basereplay/`, scratch at `~/bachgt_gate_investigation/`.

### Queued enhancements

1. **Auto-adjudicate unlinkable tables.** When per-sample anchoring fails, classify WHY: **aggregate_only**
   (no per-isolate rows / ID column, e.g. PRJEB29738) → auto-discard `EXHAUSTED: aggregate_only` with the
   agent's logged reason; **per_isolate_unlinked** (rows are per-isolate but no column matched) → stay BLOCKED
   (a real linkage target). Clears genuine dead-ends without manual curator accepts; carries over to M.abs AST.
2. **Pathogenwatch as a per-sample source — INVESTIGATED 2026-06-26, NOT USEFUL (dropped).** Tested whether
   the per-isolate epi metadata for a study could be pulled from its Pathogenwatch collection (David's idea
   for PRJEB29740, the NIHR-GHRU India 1072-isolate collection). Findings: public collections ARE reachable
   programmatically with **no token** — `GET /api/collections/details?uuid=<full-url-slug>` and
   `GET /api/collections/genomes?uuid=<slug>&page=N` (paginated) both return JSON. BUT the collection holds
   **only genomic analysis** (AMR phenotypes, Kleborate, Kaptive, MLST, cgMLST, LIN codes, assembly stats) —
   its `downloads`/`analyses` are all typing jobs, every isolate has `location:null`, and there is **no
   country/date/source metadata schema**. Pathogenwatch is a genomics-surveillance platform, not an
   epi-metadata one (the paper's "data on Pathogenwatch" = the genomes/typing, not the epi fields, which are
   in the paper supp / ENA where we already mine them). We also already run Kleborate ourselves. So there is
   nothing here for completeness backfill. (David's API token saved off-repo at
   `~/.config/bac_metadata/pathogenwatch_api_key`, chmod 600, in case the typing data is ever wanted; not
   needed for public reads.)
3. **Escalation suggestion quality** — `representative_value` must be a single parseable canonical value
   (a country, not a region like "Central America" or a concatenation like "Uganda; Malawi"); when a study
   genuinely spans several, suggest the dominant one or leave blank for the human, never an unparseable string.

---

## 10. Forward plan — finishing Klebsiella (the bac_metadata to-do)

Do all of this **before** resuming M. abscessus (too complex to run both while still fixing/testing).

- [ ] **0. Train+val re-gate** — finish the corrected-pipeline run: David walks the train/val escalation
      queue → apply → completeness → run-health. Updates §8.
- [ ] **1. Summarise the improvement vs v2** — completeness AND value-accuracy, for **both** train/val and
      test, in one clean summary.
- [x] **2. Build the intermediate enriched table** — DONE. `build_enriched_table.py` replicates step 1
      (`pp.metadata_collation` ready_to_merge substitution) with the **agent's found values** as the merge
      source: it substitutes the four clinical fields in the full-width collated base table, precedence
      **per-sample > curator-escalation > whole-field > ENA**, and writes a standalone full-width table
      (drop-in for `qc_add_metadata`) + a long-format provenance sidecar + a summary, both folds
      (`data/sample_lv_attributes/enriched/`). It never touches `ENA_projects`, so it can't clash with the
      manual ready_to_merge files for the curated studies. Enriched completeness reproduces §1/§8 (test
      country 0.959/date 0.935/iso 0.739/host 0.834; train 0.933/0.866/0.729/0.870). The only cells where
      precedence overwrites a real ENA value are **per-sample** overrides, and they agree with gold **more**
      than the ENA value they replace (country +43, date +154, iso +508; host a tie — raw-vs-category
      artifact resolved at Step 5), so the "never overwrite existing data" rule (which targeted coarse
      whole-study fills) is respected. It also adds **two new study-level columns** — `study_setting` and
      `amr_study` (matching metadata_v2) — broadcasting the agent's per-study graded value to every sample
      in the study (blank where `not_gradeable`), as the manual pipeline does from the study_level sheet.
      Large `enriched_collated_*.tsv` are gitignored (regenerable); provenance + summary are tracked.
- [ ] **3. Run on the uncurated tail** — the full pipeline on **all studies >10 samples NOT in
      train/val/test**. Genuine production: find-papers + grading run **live** (not cached for new
      accessions) → real `claude -p` spend, likely multi-day; size the batch before launching.
- [ ] **4. Final curated set** — assemble + report the finalised results on the added data.
- [ ] **5. Categorisation** — run the parse/categorise (the hand step) over the enriched data.
- [ ] **6. Plots** — `pp/plot_completeness_after_curation_and_collation.py` (runs on HPC where the raw data
      lives) to show the completeness improvement.
- [ ] **Loose ends:** accept PRJEB29738 iso (aggregate-only) → ALL CLEAR; build the unlinkable-table
      adjudicator (§9). _Done: escalation-suggestion parseability (`122aa40`). Investigated + dropped:
      Pathogenwatch (§9 — genomics-only, no epi metadata)._ Then **M. abscessus** (parked).

---

## 11. Where things live

- **Engine:** `engine/{ena_sizing,europepmc,ncbi,paper_finder,grader,adjudicator,llm,fulltext,websearch,
  local_papers,local_supplements,backfill,sample_extractor,supplementary,escalation,whole_field_audit,sources,spec}.py`.
- **Klebsiella runners:** `applications/klebsiella/{run_ena_assessment,run_find_papers,run_study_grading,
  report_missing_papers,run_per_sample_extract,run_backfill,report_persample_supplements,run_escalations,
  validate_*,summarise_agent_vs_manual,report_run_health,link_local_papers,run_pipeline.sh}`; rubric
  `attributes.yaml` (**David edits**; coverage gate 0.75).
- **Key outputs** (`data/`, `<TAG>`=train|test): `ena_assessment/ena_sizing.tsv`; `find_papers/{found_papers,
  find_*_validation/adjudication,missing_papers}…`; `study_lv_attributes/grading/study_grades_<TAG>.{jsonl,tsv}`;
  `study_lv_attributes/whole_study_backfill/{backfill_applied,backfill_gate_report,backfill_value}_<TAG>…`;
  `sample_lv_attributes/per_sample/{per_sample_applied,per_sample_outcomes,per_sample_value}_<TAG>…`;
  `study_lv_attributes/escalation/{decisions_needed,escalation_applied,accepted_unrecoverable}_<TAG>.tsv`;
  `scorecard/{agent_vs_manual,backfill_completeness,run_health,per_level_accounting}_<TAG>…`.
- **Diagnostics (read-only, not in the pipeline):** `applications/klebsiella/diagnostics/*`.

---

## 12. Consolidation into ONE engine + ONE entry point (IN PROGRESS — 2026-06-30)

**Why.** The pipeline logic already lives in `engine/`, but the stage runners still sit in
`applications/klebsiella/` and the driver ran them by **subprocess** — not really one pipeline, and the app
folder is full of generic code. A 3-agent read-only audit (2026-06-30) confirmed **no duplicate/divergent
copies** (folds and tail ran the same scripts) but the layering is wrong. Decisions locked with David:
**(a)** promote the stage orchestration into `engine/` as importable functions; the driver calls them
**in-process**; **(b)** make the engine **attribute-agnostic** (fields come from `attributes.yaml`, not
hardcoded); **(c)** the Klebsiella app shrinks to four things + a thin shell wrapper; **(d)** every
behaviour-changing step is checked **byte-for-byte** against a captured reference. Full approved plan:
`~/.claude/plans/entering-plan-mode-for-cozy-snowglobe.md` (this §12 is the living summary; no separate
plan doc).

### The split — engine vs Klebsiella (NO acronym/number labels; name things for what they do)

- **engine/** = the whole pipeline + the spec reader + mechanics (grade scale, fill precedence
  `per-sample > curator > whole-field > ENA`, the ENA-complete gate `0.75`, the big-decision `1%`).
- **Klebsiella application = only:** `attributes.yaml` (the rubric + each per-sample field's input/output
  column), `run_klebsiella.sh` (NEW thin wrapper — the human entry point, holds the data-in/out paths),
  `export_base_table.py` (the ONE genuinely Kleb-specific piece — collates the ENA TSVs into the base
  table), and `data/`. Everything else moves to the engine.
- The reference David curated is **manual curation, not gold/truth** (the agent corrects real errors in
  it). The driver flag is therefore **`--manual-curation`** (NOT `--gold`); supplying it runs the
  agreement comparison, absent → skipped (e.g. M. abscessus).

### `run_klebsiella.sh` (target) — the only Kleb entry, passes every path to the generic engine

```bash
uv run python .../engine/run_full_metadata_agent.py \
  --spec     .../klebsiella/attributes.yaml \
  --table    .../klebsiella/data/inputs/base_table.csv \      # FULL-WIDTH (all ENA cols) — see remaining work
  --data-dir .../klebsiella/data \
  --splits   .../klebsiella/data/fold_splits/project_splits.tsv \
  --sizing   .../klebsiella/data/ena_assessment/ena_sizing.tsv \
  --snapshot .../klebsiella/data/inputs/study_level_metadata_all_combined_v1.0_20260105.csv \
  --manual-curation "$MANUAL" "$@"   # mode: --fold train,val | --min-study-size 101 --tag tail100; +--paper-source finder|curated, --web-fallback
```

### What moves into `engine/stages.py` (one function per stage; driver calls in-process)

`find_papers`, `grade`, `per_sample`, `backfill_whole_field`, `escalate_detect`/`escalate_apply`,
`ena_assessment`, `missing_papers`, `persample_supplement`, `run_health`,
**`fill_metadata_table`** (← `build_enriched_table.py`; writes `filled_metadata_<tag>.tsv` — PRODUCTION
output, **not** evaluation; merge already `engine.backfill.apply_precedence_merge`),
**`attach_downloaded_papers`** (← `link_local_papers.py`; match hand-downloaded PDFs → accession, generic).

### KEY FINDING (de-risks the rest): the engine is already mostly attribute-agnostic

- `grader.py` reads **everything** from the spec (`spec.raw` study_level / study_filters /
  per_sample_completeness.backfill.fields) — no hardcoded field list. `study_grades` is already spec-driven.
- `backfill.py` functions already take `fields=...` (the constant `FIELDS` is only the default) — `field_completeness`/`gate_fields`/`apply_whole_field`. `backfill_applied` is already parameterised.
- `spec.completeness_fields` already returns the 4 fields **read from the yaml**.
- The ONLY gated module still hardcoding the 4 fields is **`sample_extractor.py`** (`FIELDS` + `FIELD_VALUE_GUIDE` in the per-sample column-map prompt). For Klebsiella the defaults reproduce current behaviour (byte-identical), so its parameterisation **only matters to enable M. abscessus** — do it, but it is not on the Kleb byte-identity path.
- Non-gated field constants (`escalation._FIELD_TERMS`, `completeness.PARSED_COLUMN`,
  `persample_supplement_worklist.DEFAULT_FIELDS`, `sources` clinical) don't affect the 3 checked outputs;
  parameterise with the constant as default for M. abscessus.

### Safety net — the exact-match check (the discipline for every step)

`engine/reference_outputs/{study_grades,per_sample_applied,backfill_applied}_train.tsv` are sorted copies
of the **current** train,val outputs under the **final rubric** (captured by `run_pipeline.sh "train,val"
train` on 2026-06-30, committed `1d8da89`). Every consolidation step must reproduce these **byte-for-byte**
(sort rows, then plain file compare). Grading is now **cached under the final rubric**, so the check is
**fast** (cache hit = prompt unchanged = pass; a cache miss itself signals a prompt drift). Stop & fix on
any diff.

### DONE & committed
- `80032fd` — unified driver (`engine/run_full_metadata_agent.py`, size-band + splits selection, writes
  batch-local sizing/splits to scratch, `project_splits.tsv` read-only) + stage pass-through hooks
  (`--sizing` / `--paper-source finder` / `--splits` on the app run_*.py) + `export_base_table.py` +
  **rubric hardening** (below) + tail100 curator artifacts.
- `1d8da89` — `engine/stages.py` (find_papers, grade, per_sample, backfill_whole_field + helpers
  `select_sizing_rows`, `resolve_fulltext_for_accession`, `curated_paper_links`, `finder_paper_links`,
  `StageCaches`) + `engine/reference_outputs/`.
- `7c8884b` — **the one-engine driver, byte-identical to `run_pipeline.sh`** (steps 1–3 + the verification
  half of 4): `stages.py` finished (escalate_detect/apply, fill_metadata_table, attach_downloaded_papers,
  + missing_papers/persample_supplement/run_health wrappers); `run_full_metadata_agent.py` rewritten to
  call `stages.py` **in-process** (data-driven `--spec`/`--table`/`--data-dir`/`--snapshot`, spec-driven
  `study_grade_columns` + classification lookup, ends with `fill_metadata_table`); `export_base_table.py`
  → **FULL-WIDTH** (96,291×119, sizing unchanged, 0 dup samples). **Byte-for-byte gate PASSES**: driver
  `--fold train,val --paper-source curated` reproduces all three `reference_outputs/` exactly
  (study_grades 110, per_sample_applied 17961, backfill_applied 22456). Key fix: read base with
  `keep_default_na=False` so ENA's literal `"NA"` survives the CSV round-trip (the only diff the gate caught).

### DONE & committed — session 2026-06-30 → 07-01 (continued)
- `3c7296b` — §12 doc (byte-identity milestone).
- `b581a2e` — **run-health LOUD curator sign-off**: `run_health_report.py` ends with an unmissable block +
  console verdict stating whether the two human steps are COMPLETE — (1) manual papers downloaded & added,
  (2) tight-grading escalations answered — each ✅/⛔ straight from the artifacts (also flags a manual PDF
  present-but-unparseable). A partially-curated run can never read as done.
- `6b5c1a8` — interactive escalation resume-safety: `run_escalations.py --interactive` walks only PENDING
  rows (never re-prompts a resolved one, so a partial queue resumes without clobbering prior answers).
- `f7836d3` → refined by `0c2f425` — **collection_date rule hardened** (David): ≤2yr midpoint;
  2–5yr escalate **only if the span midpoint is pre-2010**, else blank & NOT escalated; >5yr blank. Lives in
  **`escalation.py` `_TRIAGE_GUIDANCE`** only (the trigger). The `attributes.yaml` grader text was reverted
  to its exact pre-hardening form (a YAML comment records the rule) because the grader prompt renders
  `whole_project_value` — editing it busts the grading cache and would force a needless re-grade. Grader FILL
  behaviour was never changing (≤2yr midpoint, >2yr blank). Folds are NOT re-gated; forward-only.
- `fa8f9bb` — **train/val curator sign-off complete** (data): escalation queue 34 = 19 answered + 15
  skipped-wide + 0 pending (8,977 fills); run-health banner ✅ on both steps.
- `7cae487` + `047409e` — **accumulation engine** (§ below).
- `0c2f425` — **escalation gate correct for at-scale batches**: grading-cache-safe date rule (above) +
  **whole-cohort big-decision denominator** (below).

### Measured results — regression from the COMBINED base table (David's ask; DONE)
Scored the in-process driver's outputs *from the single full-width combined base table* (never done before):
- **Grading (train/val)** — agent accuracy **0.974**, improvement **+0.114** vs manual, N=274 (= §8's 0.97 /
  +0.10). `amr_study` 0.988, `study_setting` 1.000.
- **Value-accuracy** — whole-field country **0.99**, host **1.00** (= §8).
- **Completeness (train/val, after full curator sign-off)** — agent ≥ v2 on all four, residual 0.00:
  country **0.92**, collection_date **0.87**, isolation_source **0.71**, host **0.89** (host now *exceeds*
  §8's 0.87; country/iso within ~0.02 — the deliberate rubric hardening substituting more-correct/blank
  values for §8's pre-hardening fills, not a regression). 8,977 escalation fills from 19 curator decisions.
- **TEST slot-in (no re-grade)** — confirmed via the accumulation master (the cheap check David wanted):
  master's test rows reproduce **§8 test** exactly — country **0.959** / date **0.935** / iso **0.739** /
  host **0.834** (§8: 0.959 / 0.936 / 0.742 / 0.836; Δ≤0.003). The driver's escalation stage is also
  byte-faithful (`escalate_detect` == `run_escalations.py` detect, identical 34-row queue).

### Accumulation — build curation UP across batches (`engine/accumulate.py` + `engine/cli/accumulate.py`)
Each batch's fills were siloed per-tag and every run restarted from raw ENA. Now unioned into cumulative
stores + one master over the FULL base (rebuild: `python -m …engine.cli.accumulate --tags train,test,tail100
[--canonical <gold>]`). Large outputs gitignored (`curated/.gitignore`); only `curated_escalations.tsv`
(precious human answers) is versioned. Driver **`--carry-forward`** (build-it-up mode) overlays prior
curation onto the base (only blanks re-worked) + carries resolved escalations forward (never re-asked).
Current master (tags train,test,tail100):
- `metadata_curated_master.tsv` — 96,291 × 121 (base + fills + study_setting/amr_study).
- `curated_fills.tsv` — **92,656** cells (host 26,721 / date 24,527 / country 23,230 / iso 18,178).
- `curated_grades.tsv` — 203 studies; `curated_escalations.tsv` — 55 resolved (31 answered, 24 skip).
- `metadata_curated_master_merged.tsv` — canonical merge (**human > agent > ENA**): agent fills only
  human-blank cells (country 4,856 / date 9,073 / iso 7,218 / host 7,410); human curation never overwritten.

### tail100 re-run via the new driver (2026-07-01) — cached, `--carry-forward`
`--min-study-size 101 --paper-source finder --web-fallback`. Grading = **all cache hits** (only escalation
re-justify wrote cache). Two escalation-gate bugs found + fixed (`0c2f425`):
- **Big-decision denominator** was the batch-local cohort (8,327 → 1% = 83) → every >100-sample study
  "big" → **39 spurious escalations**. Now the driver computes whole-cohort taxon counts from the full base
  (`scientific_name` match, total **90,117** → 1% = **901**) and passes them; escalate_detect uses them for
  the ≥1% gate (gap threshold stays batch-local). tail100 **39 → 3** (1 big_decision PRJNA788733 + 2
  uniform_propose; **no spurious collection_date** — the hardened date rule now visibly works). Splits mode
  unchanged (falls back to the sizing file).
- Accumulated into the master (above). Its 3 escalations are unanswered (uncurated tail) — the sign-off
  banner flags them; run-health cell grid is otherwise ALL CLEAR.

### REMAINING (the close-out, in order)
1. **DONE** — regression from combined base (train/val + test slot-in) + accumulation framework + tail100.
2. **Retire + wrap (NEXT).** The driver's in-process stages fully cover the batch pipeline; delete the 11 app
   scripts (`run_*.py` ×5, `report_*.py` ×3, `build_enriched_table.py`, `link_local_papers.py`,
   `make_tail_batch.py`) and `run_pipeline.sh`. **Preserve the curator-loop tools** — they must move to
   `engine/cli/` before deletion: **escalate** (`--interactive` queue walk + `--apply`, from
   `run_escalations.py`), **run_health** (standalone re-check), **attach_papers** (from `link_local_papers.py`).
   Add thin **`run_klebsiella.sh`** (batch entry, holds data paths → the driver) + **`evaluation/run_folds.sh`**
   (driver + `validate_*` when `--manual-curation` present). Update the overnight `.sh` (they call
   `run_pipeline.sh`). Place full-width `base_table.csv` at `data/inputs/` (gitignored). Keep
   `export_base_table.py` + `run_ena_assessment.py`. `engine/cli/accumulate.py` already exists.
3. **Parameterise `sample_extractor`** (+ non-gated constants) → **M. abscessus** (`run_m_abs.sh`).
4. **The REST of the cohort** — smaller (<100-sample) uncurated studies at scale via the driver
   (`--carry-forward` onto the master, biggest-first); curator answers the now-minimal escalation queues.
