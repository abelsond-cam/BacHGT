# M. abscessus application — project plan

**Status: PAUSED.** Parked until the Klebsiella application is *finished* — the engine must be proven sound
(and Klebsiella wrapped up) before a second application is built on it. The reproduction gate that originally
blocked this is now cleared (see [`../../PROGRESS_REPORT.md`](../../PROGRESS_REPORT.md) §9); resume only after
the Klebsiella finishing plan (§10) completes — David: too complex to run both while still fixing/testing.

Progress so far:
- **M2 (input pre-scan) — DONE + committed** (`e6b2e62`): `scan_input_availability.py` + `data/diagnostics/
  input_availability.{tsv,md}`. Findings: 7,217 records / 133 studies; country/date/iso/host ~65–77% present;
  cf_status 21% (1,547 human CF/non-CF, answered_by_data for only 4/133 studies); smoking + AST 0% (paper-only).
- **M3 (attributes.yaml) — DRAFT written (parses), UNCOMMITTED, awaiting David's final review** of the drug
  list / CF wording / `reports_AST` scope. 93 effective per-sample fields (6 core/phenotype + 43 drugs ×
  {mic, resistance} + `ast_other`); `reports_AST` the sole study-level attribute; taxon `[abscessus]`.

---

## Context

The **second application site of the same engine: *Mycobacterium abscessus*** (~7,200 sequences / 133 ENA
project accessions, from `ATB_metadata_Mabs_2025_release.xlsx`). The engine is the product; M.abs is a new
application — so most work is a new `attributes.yaml` + a new input source, with one **regression-safe engine
generalisation** (hardcoded-4-fields → spec-driven) that benefits both apps. Start from a **copy of the rich
Klebsiella `attributes.yaml`** (much carries over), not the thin m_abs scaffold.

**What changes for M.abs (David):** (1) DROP study-level grading of `study_setting` + `amr_study`
(+ dependents) — irrelevant (all drug-resistant, all hospital); (2) ADD one study-level boolean `reports_AST`
(does the study report AST) to prioritise per-sample AST mining; (3) per-sample fields = the 4 core (country,
collection_date, isolation_source, host) PLUS `cf_status`, `smoking_status`, and an **AST panel**;
(4) isolation_source/host are low-priority (nearly all respiratory/human) but collected anyway; (5) the
whole-study fallback ("all CF" / "all non-CF") rides the existing `whole_project_value` backfill.

**Key discoveries from exploration:**
- The engine is **already spec-driven for grading** (`grader._study_level_attributes` reads any
  `attributes.study_level.*` with a `values:` key). Dropping setting/amr_study and adding `reports_AST` is
  essentially free. The work is generalising `backfill` / `sample_extractor` / `escalation`, which
  **hardcode the 4 fields**.
- **`engine/sources.py::GenericXlsxSource`** already exists, purpose-built for this xlsx.
- The xlsx **already has `cf_status`** (1,693/7,217 rows) but NOT binary — values
  `CF / Non-CF / ? / Animal / Environmental`. `disease`/`host_phenotype`/`Notes` are EMPTY; the real
  CF-signal columns are `cf_status`, `host_status` ("Cystic fibrosis"…), `sample_description`.
- **No smoking and no antibiotic/MIC/AST column** in the 203 — smoking + AST are **100% paper-derived**.
- The xlsx `scientific_name` is **`Mycobacteroides abscessus`** (genus reclassified) — the spec's
  `["Mycobacterium abscessus"]` would silently size everything to 0. **Latent bug → match on `[abscessus]`.**

## Confirmed decisions (David, 2026-06-25/26)

1. **AST = fixed but EXTENSIVE canonical panel.** Keep it WIDE ("the more data the better") — the **compact
   list sub-schema** (M1) decouples the number of drug output columns from the column-map schema size, so
   extra drugs are ~free. Each drug → `ast_<drug>_mic` (verbatim MIC string) + `ast_<drug>_resistance`
   (categorical S/I/R **as stated** — never interpret, no breakpoints; curation is a later job). `ast_other`
   free-text for off-panel agents. **Inducible-macrolide (day-14) reads DEFERRED** to a later run. Panel ~43
   drugs across macrolides / aminoglycosides / carbapenems / cephalosporins / β-lactam-combos / tetracyclines
   / fluoroquinolones / oxazolidinones / other antimycobacterials (see the drafted `attributes.yaml` for the
   list; David finalises canonical names + synonyms).
2. **CF (per-sample `cf_status`)** = `CF` / `non_CF` / `unknown`. CF = cystic-fibrosis host; non_CF = any
   non-CF condition; `unknown` = not stated OR non-human (Animal/Environmental → coded by the `host` field,
   NOT forced into the CF binary — no `non_human` value needed). `host_disease` and `smoking_status` are
   **PER-SAMPLE** fields (not study-level grades), each with the whole-study fallback.
3. **Smoking (per-sample `smoking_status`)** = aspirational: smoker (any pack-years/quit-date) / non_smoker
   (explicit never) / unknown.
4. **Validation = no-gold.** Completeness before/after backfill + run-health + a free proxy CF accuracy +
   the **manual-verification scorecard** (see M5). Defer supervised value-accuracy until a hand-graded seed.
5. **First run scope** = the biggest ~20 studies (biggest-first) to get data flowing before scaling to 133.

## Phase M0 — Engine/application boundary cleanup (regression-safe) **[do first]**

Make the `engine/` vs `applications/klebsiella/` split honest (a boundary audit classified every module):
- **Promote three generic aggregators from `klebsiella/` to `engine/`** (keep a **thin Klebsiella wrapper**
  wiring app paths + the `paper_link` lookup, so kleb output is unchanged):
  - `report_run_health.py` → `engine/run_health_report.py` (study×field grid + resolution + ALL-CLEAR verdict).
  - `report_missing_papers.py` → `engine/missing_papers.py` (inject the `paper_link` lookup).
  - `report_persample_supplements.py` → `engine/persample_supplement_worklist.py` (probe + action classify).
- **Generalise `engine/completeness.py:45`** — the hard `from bac_metadata.pp import metadata_curation`
  (kleb `parse_*` normalisers) becomes an **injected** `normalisers` map, **no-op when none** (M.abs passes
  none; kleb runner injects). Removes the one true engine→kleb-curation coupling.
- **`engine/sources.py`** — `KlebCollationSource` stays kleb-specific; generalise `GenericXlsxSource._clinical`
  to accept the clinical/keep set so M.abs carries `cf_status` + AST through. Drop the kleb line in
  `engine/fulltext.py:3` docstring.
- Leave the thin `run_*` runners, gold/sheet-bound `validate_*`/`summarise`/`freeze_study_setting`/
  `make_kleb_splits`, and `diagnostics/` as Klebsiella-specific.

**GATE:** shared with M1 — byte-identical Klebsiella re-run (relocation must not change behaviour).

## Phase M1 — Engine generalisation (spec-driven fields), regression-safe **[GATE]**

Make `backfill` / `sample_extractor` / `escalation` read their field set + per-field guidance from the
**spec** instead of module constants, **constants kept as verbatim fallback** so Klebsiella runs
byte-identical. New per-field YAML keys (1:1 with current hardcoded structures): `value_guide` →
`sample_extractor.FIELD_VALUE_GUIDE`; `column_aliases` → prompt alias bullets; `escalation_terms` →
`escalation._FIELD_TERMS`; `triage_hint` → `escalation._TRIAGE_GUIDANCE`; `compare: year|exact` →
`backfill._cmp_key`.
- `engine/spec.py` — add `backfill_field_names()` + `field_guidance(key, default_map)` over `spec.raw`,
  falling back to legacy constants.
- `engine/backfill.py` — callers pass `spec.backfill_field_names()`; `_cmp_key` takes `compare_modes`
  defaulting to `{"collection_date":"year"}`.
- `engine/sample_extractor.py` — generate `column_map_schema()` properties + prompt bullets by looping the
  spec field list + guidance; swap the `FIELDS` constant for the passed list. **AST**: do NOT emit ~80 fixed
  `ast_*_column` schema properties — keep the ~6 core/CF/smoking fields fixed and map AST via a **compact
  list sub-schema** (`ast_columns: [{drug, mic_column, resistance_column}]`, drug normalised to a canonical
  name or `other`); a deterministic step expands to `ast_<drug>_*`.
- `engine/escalation.py` — add `field_terms`/`triage_guidance` params sourced from spec; constants become
  defaults.
- `engine/grader.py` — generalise the hardcoded amr sentence at grader.py:222 to render from each attribute's
  `applies_when` (so dropping amr_study leaves nothing dangling; kleb unchanged).
- `engine/completeness.py` — `normalise_table` no-ops when no normaliser-backed field is requested.
- Klebsiella `attributes.yaml` — add the new per-field keys with values **copied verbatim** from constants.

**GATE:** cache-warm `evaluation/run_folds.sh "train,val" train curated` before/after M0+M1 → `study_grades_train.tsv`,
`backfill_applied_train.tsv`, `per_sample_applied_train.tsv`, `decisions_needed_train.tsv` **byte-identical**.

## Phase M2 — Input pre-scan diagnostic — **DONE** (`e6b2e62`)

`scan_input_availability.py` (engine-free pandas) → per-study × field structured availability. (See status.)

## Phase M3 — `attributes.yaml` — **DRAFT done, uncommitted**

Drafted from David's answers (`reports_AST` only study-level; per-sample cf_status/smoking + AST panel;
taxon `[abscessus]`; verbatim-no-interpret AST; inducible deferred). Awaiting David's final review +
sign-off before commit. **Do not invent grading criteria** (CLAUDE.md rule).

## Phase M4 — m_abs ingestion + thin runners

> **Superseded by the one-driver consolidation (2026-07-01):** the engine now runs every stage in-process
> via `engine/run_full_metadata_agent.py`, and kleb's thin `run_*` / `run_pipeline.sh` scripts are retired
> (curator tools moved to `engine/cli/`). m_abs should add a thin `run_m_abs.sh` over that driver (like
> `run_klebsiella.sh`) + `GenericXlsxSource`, **not** copy the retired per-stage scripts. Re-scope this
> section in Step 3 (parameterise `sample_extractor`); the phase content below is kept as historical intent.

The engine does the heavy lifting (after M0+M1); m_abs gets **thin runner copies** (sources differ —
`GenericXlsxSource` vs `KlebCollationSource`, no paper-link snapshot, no gold). New under `applications/m_abs/`:
`run_ena_assessment.py` (sizes via `ena_sizing.study_record_counts`, taxon fix makes counts non-zero);
`make_mabs_splits.py` (**single `fold=all`** — no ground truth, biggest-first; first run = top ~20);
`run_find_papers.py`, `run_study_grading.py` (reuse engine, spec=m_abs); `run_backfill.py`,
`run_per_sample_extract.py`, `run_escalations.py` (pass `spec.backfill_field_names()` + `GenericXlsxSource`;
per-sample runner reads `reports_AST__value` to **prioritise** AST tables); `run_pipeline.sh` (copy of kleb's
minus the gold-required Stage 9; keep Stages 1–8 + run-health + the no-gold scorecard).

## Phase M5 — No-gold validation

- `validate_completeness_nogold.py` — completeness before → +whole-field → +per-sample per field, without the
  gold/`--truth` columns. Headline: did backfill raise cf_status/AST/smoking completeness.
- **run-health** (gold-free) — convergence verdict + worklist.
- **Proxy CF accuracy** — LLM study-level CF call vs the structured `cf_status` majority on the pre-filled rows.
- **Manual-verification scorecard (David, primary M.abs review artifact).** Paper-finding is trusted, so
  M.abs review is by manual spot-check of found papers. Emit a concise per-study table: `study_accession`,
  **paper hyperlink**, **EBI study hyperlink**, `table_found` (T/F), `samples_linked` (T/F), `cf_info_added`
  (+ AST-info-added). David manually verifies CF / AST against the papers after the run.
- Defer `validate_backfill_values.py` (supervised value-accuracy) until a hand-graded seed exists.

## Risks of Klebsiella regression (and mitigations)

- **R0 prompt/regex drift** — 4-field schema/prompt/regex reconstructed from YAML; one-char diff changes
  output. *Mitigation:* copy constants verbatim; gate on the byte-identical re-run; Python constants as fallback.
- **R1 taxon miss** — fixed via `scientific_name_match: ["abscessus"]`.
- **R2 grader.py:222 amr rule** — render from `applies_when`; confirm kleb prompt unchanged via byte-diff.
- **R3 `_cmp_key` compare-mode** — default `{"collection_date":"year"}`; covered by the diff.
- **R4 `GenericXlsxSource._clinical` widening** — independent of `KlebCollationSource._clinical`; re-run kleb.
