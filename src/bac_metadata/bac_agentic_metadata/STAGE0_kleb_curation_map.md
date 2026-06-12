# Stage 0 — How the manual Klebsiella curation worked

The reusable agentic-metadata engine **generalises the manual Klebsiella curation**. This
document maps how that curation actually worked, so the engine can replicate it and we can
say precisely which manual steps become deterministic code vs LLM/agent judgement. It is
the reference for [`PIPELINE_PLAN.md`](PIPELINE_PLAN.md).

Sources read while writing this: the curation Google Sheet
(`study_level_metadata_all_combined`, ID `1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk`),
[`../METADATA_v2_README.md`](../METADATA_v2_README.md), and the curation engine modules
under [`../pp/`](../pp/).

## 1. The unit of work: the project accession

The fundamental unit is the **ENA project accession** (`study_accession`, e.g.
`PRJEB10018`) — the natural grouping of the input metadata. The manual workflow was:

1. **Group** the ~90,000 ATB/RefSeq Klebsiella samples by `study_accession`.
2. **Rank by size** and work **biggest-first**. Studies with **>130 samples** were taken
   on for manual curation — these account for ~75% of the assembly set. Smaller studies
   were left uncurated (still an open tail). The threshold lives in code as
   `filter_study_size = 131` in [`../pp/metadata_collation.py`](../pp/metadata_collation.py):
   unreviewed studies above it are dropped from the cohort; reviewed studies (any size)
   are kept.
3. **Find the best paper** describing each accession's cohort. One paper can describe
   several accessions (e.g. `PRJNA339843` + `PRJNA433394` are one ARGONAUT-IV study;
   `neonatal_klebsiella` spans four accessions). The paper is *found per accession*, not
   the entry point.
4. **Grade the paper** to assign cohort-level attributes back to the accession (§4).

## 2. The curation record: one Google Sheet, two tabs

- **`study_level`** — the human-facing curation sheet, **keyed by `study_accessions`**
  (plural; one row may list several comma/slash/`and`-separated accessions). It is laid
  out paper-title-first purely because that reads naturally for a human curator — it does
  **not** make the paper the unit.

  **Column trust map (important):**
  | Columns | Status |
  |---|---|
  | A–K (`paper_title`, `paper_short_title`, `paper_link`, `Curator`, `kleb_assemblies_in_paper`, `isolates_in_study`, `study_accessions`, `amr_study`/`sample_selection`, `study_setting`, `death_metadata`, `cohort_age`/`newborn_cohort`) | **Usable as ground truth** — but imperfect (paper-title typos, improvable values). |
  | `ATB_*_prop`, `*_added` (`location_added`, `date_added`, …) | **NOT ground truth** — these were David's *work-tracking* of his own progress. |
  | Free-text notes (`Outstanding issues…`, `metadata to check`, `Free-text comments`, …) | Curator notes; useful colour, not gradeable labels. |

- **`parsed_per_project`** — the **output of the collation/curation scripts**, and the
  *more reliable* record of what was actually improved per project (use this, not the
  `ATB_*_prop`/`*_added` columns, to judge completeness/backfill). Read at build time via
  the repo's own Sheets API auth (the claude.ai Drive MCP only renders the primary tab).

> **Schema drift to know about.** The frozen snapshot committed for the split
> (`applications/klebsiella/data/study_level_metadata_all_combined_v1.0_20260105.csv`,
> 2026-01-05) uses the *older* column names `sample_selection` / `newborn_cohort` /
> `ATB_location_prop`; the current live sheet uses `amr_study` / `study_setting` /
> `cohort_age`. The split only needs `study_accessions` + `isolates_in_study` +
> `paper_short_title`, which are stable across both. Re-freeze a current snapshot before
> the validation stages so attribute ground truth matches the live sheet.

## 3. How study-level metadata is keyed and ingested (code)

- Google Sheets API read: `_read_google_sheet()` in
  [`../pp/metadata_curation.py`](../pp/metadata_curation.py) (tab-name aware; OAuth2 via
  `client_secret_*.json` + cached `token.json`).
- Reviewed-study list + exclusions: `load_study_accessions()` and `load_removed_studies()`
  in [`../pp/metadata_collation.py`](../pp/metadata_collation.py); a `metadata_reviewed`
  boolean is set per `study_accession`.
- Study-level labels merged onto samples: `merge_amr_study_from_study_metadata()` and
  `merge_study_setting_from_study_metadata()` (keyed by `study_accession`).

Pipeline order (see [`../CLAUDE.md`](../CLAUDE.md)):
`metadata_collation.py` → `qc_add_metadata.py` → `metadata_curation.py`.

## 4. The two kinds of judgement the engine must reproduce

**(a) Study-level judgements read from the paper** — attributes often *absent from the
structured data entirely*:
- `study_setting` — hospital / community / mixed.
- `amr_study` (a.k.a. `sample_selection`) — amr / mixed / surveillance; experimental-
  evolution studies were *excluded*.
- *(wanted, not yet collected)* `amr_target` (3rd-gen cephalosporin / carbapenem / other),
  `amr_method` (PCR gene-presence vs AST result), `cohort_age` (newborn/young-child vs
  adult — for the invasion-gene comparison).

**(b) Per-sample completeness & backfill** — for `country`, `collection_date`,
`isolation_source`, `host`: measure how complete the ATB structured data is, and where
low, recover the value from the paper. The deterministic normalisation of these four
fields is already implemented as parse/categorise pairs in
[`../pp/metadata_curation.py`](../pp/metadata_curation.py):
`parse_host`/`categorise_host`, `parse_isolation_source`/`categorise_isolation_source`,
`parse_country`/`categorise_region`, `parse_collection_date`.

## 5. Manual step → deterministic workflow vs LLM/agent judgement

| Manual step | Becomes |
|---|---|
| Group samples by `study_accession`, rank by size, apply >130 threshold | **Deterministic** (`filter_study_size`) |
| Pull project-level metadata from ENA/EBI | **Deterministic** (API fetch) |
| Measure per-field completeness (country/date/source/host) | **Deterministic** (validated vs `parsed_per_project`) |
| Normalise/categorise host, isolation source, country, date | **Deterministic** (existing parse/categorise pairs) |
| Find the best paper for an accession | **LLM/agent + search** |
| Grade study_setting / amr_study / amr_target / amr_method / cohort_age from the paper | **LLM/agent judgement** |
| Backfill a low-completeness field from the paper | **LLM/agent judgement** (deterministic re-normalisation after) |
| Decide a cohort is "mixed" / not labellable at accession level | **LLM/agent judgement**, flagged for raw per-sample download |

## 6. What is frozen for validation

- The **split**: `applications/klebsiella/data/kleb_project_splits.tsv` (accession unit,
  paper-grouped folds, 50/20/30, seeded). Iterate on train+val; **test stays sealed**.
- The **ground-truth instance**: `study_level` columns A–K + `parsed_per_project`.
  Ground truth exists only for the *already-curated* attributes (`study_setting`,
  `amr_study`, partial `cohort_age`, and the completeness/backfill fields). The wanted new
  attributes (`amr_target`, `amr_method`, finished `cohort_age`) have **no Kleb ground
  truth yet** — the engine generates them and David spot-checks on train/val.
