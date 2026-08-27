# Agentic metadata re-curation → metadata_v2 — achievements summary

*2026-08-27 · Klebsiella pneumoniae species complex (KPSC) · `bac_agentic_metadata`*

A one-page account of what the agentic metadata re-curation did and what it delivered into the canonical
`metadata_v2` table. State authority: [`PROJECT_STATE.md`](../../../PROJECT_STATE.md) Layer B. Mechanics:
[`PROGRESS_REPORT.md`](PROGRESS_REPORT.md), [`MERGE_TO_V2_RUNBOOK.md`](MERGE_TO_V2_RUNBOOK.md). Reconciled
figures: [`data/Kp_AGENTIC_METADATA_WRAPUP_REPORT.md`](applications/klebsiella/data/Kp_AGENTIC_METADATA_WRAPUP_REPORT.md).

---

## 1. Headline

An LLM-agent pipeline re-curated the four ENA completeness fields (**country, collection_date,
isolation_source, host**) plus study-level judgements across the **entire KPSC cohort**, then combined the
result into production `metadata_v2` — **raising clinical completeness by +5 to +12 percentage points, adding
~30,000 field values, correcting 2,922 values, and removing 1,055 experimental-evolution lab samples from the
analysis cohort — while leaving every one of the 549 pre-existing v2 columns byte-identical.**

The agent **matches or beats the prior manual curation** on every field (validated on sealed gold folds), and
its study-level grading is more accurate than manual (+0.108 train, +0.028 test).

---

## 2. The method

- **Unit of work = ENA project accession**, processed biggest-first across seven size-band tranches
  (train, test, tail100, tail50–99, tail25–49, tail10–24, sub-10).
- **Pipeline** (one in-process driver, `engine/run_full_metadata_agent.py`): *find* the describing paper
  (EuropePMC/NCBI + web fallback + hand-downloaded PDFs) → *grade* each study against the paper → *per-sample*
  extract per-isolate values from in-paper/supplementary tables (anchored to samples **by value**, never by
  column name) → *whole-field backfill* where a study is uniform → *escalate* tight near-misses to a human →
  *fill* the production table.
- **Human-in-the-loop:** curators attach paywalled PDFs, add per-isolate supplementary tables, and answer an
  escalation queue; committed answers are sticky across re-runs.
- **Always-on gates:** escalation-conservation, overwrite-radius, pipeline-trigger, and run-health checks — no
  silent zero-fills, no un-sanctioned overwrites.
- **Overwrite policy:** fills only populate blank cells, with two sanctioned exceptions — a same-year
  `collection_date` refinement and a fidelity-judged vague→specific replacement. Precedence in the merge is
  **human-curated > agent > ENA** (a curated value is never overwritten by a blank-fill).

---

## 3. Scale reviewed

| Quantity | N |
|---|--:|
| ENA project accessions reviewed | **1,914** |
| Describing papers located | **952** |
| Papers read in full text | **864** |
| Paywalled PDFs hand-fetched by curators | **90** |
| Experimental-evolution studies flagged | **78** (1,489 samples) |
| Agent field-values curated into the master (whole cohort) | country 22,940 · date 22,681 · iso 20,299 · host 34,703 |

---

## 4. Accuracy vs manual curation (adjudicated; sealed gold folds)

| Fold | Item | Agent | Manual | Δ |
|---|---|--:|--:|--:|
| train | paper-finding | 0.943 | 0.841 | +0.102 |
| train | study-level grading (all) | 0.974 | 0.866 | **+0.108** |
| test | study-level grading (all) | 0.953 | 0.925 | **+0.028** |

Per-sample completeness on the 83,780-sample cohort (raw ENA → agent → prior manual v2), agent − v2 gold:
**country +3.6, collection_date +7.9, isolation_source +6.3, host +10.4 pp** — the agent matches-or-beats the
manual table on every field, and adds most on the previously-uncurated tail bands.

---

## 5. What landed in production v2 (architecture B, 2026-08-27)

The agent fills + approved overwrites + evolutionary de-list were injected **directly onto the current v2**,
preserving all v2-only columns, rather than a full rebuild (which would have re-derived Kleborate/ISEScan/AST
from the current pools). Verified against the pre-agentic table:

- **86,398 rows preserved**, aligned on `Sample`; **0 columns dropped**, no spurious columns.
- **0 off-target column changes** — every one of the 549 v2-only columns (Kleborate / ISEScan / AST / SR↔LR
  linkage / CheckM2 / Bakta) is **byte-identical**. Only the clinical fields, their derived columns, the cohort
  flags, and 9 new provenance columns changed.
- **Completeness (non-blank %):** country 91.3→96.3 · collection_date 82.0→90.1 · isolation_source 72.6→77.7 ·
  host 80.3→**92.1**.
- **Blank-fills:** country 4,375 · collection_date 6,974 · isolation_source 7,868 · host 10,482.
- **Overwrites:** 2,922 rows written (3,013 David-approved; 91 samples not in v2's cohort). Example —
  `SAMN20064863`: `Switzerland→Australia` (ENA submitting-lab-country error corrected from the paper), with
  `region` re-derived `W. Europe→Oceania`.
- **Experimental-evolution de-list:** 1,055 lab samples removed from the cohort —
  `kpsc_final_list`/`lra_final_list`/`is_variant_called` → False; `is_kpsc` **kept** True (they are genuinely
  KPSC, used for the evolutionary analysis); the 10 that are closed reference genomes **keep** their
  `is_complete`/`is_hybrid`/`is_reference_genome` flags. Non-evolutionary cohort membership byte-identical.

### Cohort-flag impact (whole table, True counts)

| Flag | manual v2 | agentic v2 |
|---|--:|--:|
| **`kpsc_final_list`** (analysis cohort) | 79,153 | **78,190** |
| `is_kpsc` (taxonomic) | 79,153 | 79,153 |
| `is_variant_called` | 76,574 | 75,611 |
| `lra_final_list` | 5,519 | 5,509 |
| `is_complete` / `is_hybrid` / `is_reference_genome` | 4,017 / 2,618 / 1,777 | 4,017 / 2,618 / 1,777 |
| `evolutionary_lab_sample` (new) | — | 1,055 |

---

## 6. Provenance & auditability

Nine new columns record exactly what the agent did to each cell, so the enrichment is fully traceable and
reversible:

- **`<field>_agent_filled`** (×4) — True where the agent filled a blank cell.
- **`<field>_agent_overwrote`** (×4) — True where an approved agent value replaced an existing ENA value.
- **`evolutionary_lab_sample`** — True for the de-listed experimental-evolution lab samples.

The pre-agentic v2 is archived intact at
`…/david/final/archive/metadata_v2_all_samples_and_columns.tsv.20260827T165822.bak`; the reviewed overwrite
candidate list is committed at
[`data/v2_overwrite_candidates.{tsv,md}`](applications/klebsiella/data/v2_overwrite_candidates.tsv); the build
artefact (candidate + numbers + verification script) is retained at `…/david/final/agentic_combine_20260827/`.

---

## 7. Decisions of record (David)

- **Architecture B** — inject onto the current v2 (preserve all v2-only columns), not a full pool-re-deriving
  rebuild.
- **Overwrite candidates approved** in full, including the concrete→concrete country corrections.
- **`is_kpsc` left True** on evolutionary samples; only cohort membership (`kpsc_final_list`) removed.
- **Closed evolutionary genomes keep their quality flags** (10 samples, 4 studies — plausibly ancestral
  clinical isolates).

---

## 8. Follow-ups

- **Category tail — DONE (2026-08-27).** The agent introduced raw paper values the categorise rules didn't map
  (region *Saint Kitts and Nevis*/*Middle East*; host *Galleria*/*C. elegans*/*hospital sink*/…; ~40 iso
  abbreviations *UTI*/*SPUT*/*CRBSI*/*HAP-VAP*/…). Fixed both ways: the `metadata_curation.py` categorise
  rule-lists were extended (future rebuilds), and a targeted `combine/recategorise_agentic_tail.py` remapped the
  already-landed cells (region 88, host 63, iso 403 — only those cells changed). **Small residual left**
  (ambiguous/cross-field, ~110 samples): host *Feed* (1); iso host-in-source mis-files (domestic animals 17,
  wild animals 14, poultry 5, wild birds 2, bovine 3, equine 2) + ambiguous codes (MB 10, TASP 9, SS 4, BA 2,
  CATH 2, CHEST 1, one hospital case); the lab-culture family (94) now sits in `lab, hospital or facility
  (unhelpful)`.
- **`METADATA_v2_README.md`** refreshed to 558 columns with manual→agentic before/after tables (done).
- **M. abscessus** agentic application remains deferred (a later round).
