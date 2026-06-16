# PIPELINE_PLAN — the agentic-metadata engine

The living plan for the **reusable, species-agnostic agentic metadata-curation engine**.
The engine is the product; *Klebsiella* and *M. abscessus* are **application sites**. This
doc is the framework; [`STAGE0_kleb_curation_map.md`](STAGE0_kleb_curation_map.md) is the
reference for the manual Klebsiella curation it generalises.

## 1. What the engine does

For one **project accession** (`study_accession`) — the unit of work — the engine:

1. Pulls the accession's structured ENA/ATB metadata, computes per-field completeness, and
   reads the EBI project record counts (total records + taxon-of-interest by
   `scientific name`) to size the project.
2. Finds the best paper describing the cohort — the one covering the largest part of the
   project (a paper may serve several accessions; the project counts tell us whether a
   candidate paper covers the whole project or only a subsample).
3. Grades the paper into a **configured attribute set** (the application's spec).
4. Emits, per attribute, a value + grade (`gradeable` / `partial` / `not_gradeable`) + an
   evidence pointer; the `paper_coverage_for_taxon` metric (what fraction of the
   project's taxon-of-interest records the chosen paper describes); plus cohort flags
   (`cohort_mixed`, `needs_manual_download`).

Accessions are processed **biggest-first**, mirroring the manual workflow. The
**taxon of interest is application config** (`taxon_of_interest` in
`attributes.yaml`): projects can be broad (e.g. all *Enterobacteriaceae*), so sizing,
coverage and completeness are all computed over records matching it, not the whole project.

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

The curated Klebsiella accessions are split **train 78 / val 31 / test 47** by accession,
folds assigned at paper-group level to prevent paper leakage
(`applications/klebsiella/data/kleb_project_splits.tsv`, seeded, reproducible). **All
rubric/prompt tuning happens on train+val; the test fold stays sealed** until a single
final measured-agreement run.

## 6. Staged build (Stages 1–4 follow this Stage 0)

- **Stage 0 (this round) — DONE here.** Engine skeleton, this plan, the Stage 0 map, the
  attribute-spec scaffolds, and the seeded split.
- **Stage 1 — Deterministic ingestion & completeness (no LLM).** Group by accession; pull
  ENA/EBI project metadata; read project record counts (total + taxon-of-interest by
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

## 6b. Current status & results (as of 2026-06-16)

Stages 1–2 are **built and validated on train+val** (test fold sealed). Full per-module detail +
how-to-run is in [`STAGE2.md`](STAGE2.md); this is the summary + measured results.

**Stage 1 — deterministic sizing/completeness (no LLM): done.** Per accession: ENA total + taxon
sample/run counts, `umbrella_suspected`, fold → `data/stage1_sizing.tsv`. The stable test bed.

**Stage 2A — grading (LLM): done.** The grader renders the rubric *straight from
`attributes.yaml`* (each attribute `definition` + shared `grading_basis` + a `sizing_first`
sanity-check that says trust ENA counts over the sheet and reconcile vs the article) into both a
forced-tool JSON schema and the prompt. Two interchangeable backends behind `engine.llm.LLMClient`:
**`subscription`** (default — `claude -p`, **zero API spend**, fresh single-turn context per call,
schema embedded + validated + one retry) and **`api`** (paid, forced tool use). A **backend-
independent disk cache** makes reruns byte-identical/free. Per accession it emits each study-level
attribute `{value, grade, evidence_quote}`, `paper_coverage_for_taxon`, method-(a) backfill
proposals, and `needs_manual_download`.
*Results (n train+val):* primary checks **amr_study 0.94** (was 0.78) and **study_setting 0.98**
(was 0.90), after folding adjudicator rule-gaps into the rubric and applying David-verified GT
corrections. `cohort_age` is **not scored** (no reliable GT). Gains are partly mechanical (truth
corrected to match verified findings); the pre-correction raw figures were 0.78 / 0.90.

**Adjudication — opposing Opus critic: done.** For every grader-vs-sheet disagreement,
`engine.adjudicator.adjudicate` re-reads the paper and returns a verdict {model_correct,
sheet_correct, both_defensible, undetermined} + **verbatim quote** + `rule_gap`. The sheet is *not*
assumed correct. First full pass: **28 disagreements → 20 model_correct (sheet wrong), 3
sheet_correct, 5 undetermined**. The verified sheet errors became a **GT-correction overlay**
(`data/gt_corrections.tsv`, 19 rows, applied at scoring time; snapshot stays immutable); a re-grade
under the improved rubric left **7** disagreements.

**Stage 2B — paper finding (LLM-picks-among-retrieved, never invents): done.** Deterministic
retrieval (ENA-description id-mining → NCBI BioProject elink → Europe PMC accession text-mining →
EPMC title) unions candidates; the LLM only picks an index; the pick is **grounded** (accession must
appear in the paper) with abstain-over-guess. Matching to the curated `paper_link` is by paper
**identity** (union of all curated rows + EPMC cross-id `{pmid,pmcid,doi}` canonicalization + a
`same_paper` adjudicator verdict), and the finder **always prefers the published version** over a
preprint (`europepmc.published_version_of`).
*Results (102 train+val with a curated link):* **find-accuracy 0.62 → 0.75 adjudicated**; of 19
mismatches the Opus critic ruled 12 the curated link wrong (finder right) + 1 same_paper + 2
both_describe, leaving 5 genuine finder errors. Channels: `europepmc_accession` workhorse, NCBI 3
sole wins, preprint→published 2 wins; grounded-verify 61/109.

**Sample-level backfill (method-a) — measured.** The grader proposes whole-project values for
`country` / `collection_date` / `isolation_source` / `host`; `validate_backfill.py` scores
*targeting/recall* against the live `parsed_per_project` tab (per-field pre/post completeness — value
correctness needs per-sample `metadata_v2`, deferred). **country 0.78 / host 0.83 recall** (method-a
strong); **collection_date 0.17 / isolation_source 0.14** (44 residual accession-fields → the
deferred **method-(b)** per-sample-table path).

### Forward plan (do in order)

1. **Apply** method-(a) `country`/`host` backfill (the covered cases) to the table — first write-back.
2. **Value-correctness**: bring in per-sample `metadata_v2` to verify proposed raw values (not just
   targeting).
3. **Method-(b)**: per-sample-table extraction for the ~44 `collection_date` / `isolation_source`
   gaps (needs sample-accession↔paper-table mapping; the `partial` path).

Deferred follow-ups: 2 rubric over-steers (`PRJEB58136` mixed→surveillance; `PRJNA604975`
mixed→hospital — BSI "all blood cultures→hospital" default vs community-facility nuance) + a wording
tweak; 2 new GT candidates (`PRJNA789565`→surveillance, `PRJEB30134`→mixed); `PRJEB28400` sample
counts → ENA-deposit (1950) + audit other screened-subset studies; a re-grade *with* `sizing_first`
(it postdates the last re-grade); multi-organism-umbrella taxon-aware finder rule. **Test fold stays
sealed** until a single final run.

## 7. Definition of done

Pipeline runs end-to-end on a real cohort by swapping the application directory; every LLM
step has **measured agreement** against held-out ground truth; the rubric lives in a
versioned `attributes.yaml`; the system is species-agnostic.
