## 0. Methods & provenance

**What this is.** An LLM-agent re-curation of ENA study metadata for the *Klebsiella pneumoniae* species complex, producing per isolate the four ENA completeness fields (country, collection_date, isolation_source, host) plus study-level judgements (study_type, study_setting, amr_study), accumulated across size-band tranches into one master table. The engine is species-agnostic and data-driven by a rubric (`applications/klebsiella/attributes.yaml`); grading definitions are the curator's, not invented by the model.

**Cohort & row key.** The working base table `data/inputs/base_table.csv` (96,291 samples; 90,117 match the Klebsiella taxon) is keyed `study_accession` + `sample_accession` (one row per SR biosample). Studies are processed biggest-first across seven tranches (train, test, tail100, tail50_99, tail25_49, tail10_24, sub10). RefSeq/NCTC assembly genomes carry no ENA study/paper and are out of scope (a separate path).

**Pipeline (one stage per step; `engine/run_full_metadata_agent.py`).** *find* — discover the describing paper (EuropePMC/NCBI + web fallback + hand-downloaded PDFs); *grade* — an LLM grades each study against the paper on a tiered context budget; *per-sample* — extract per-isolate values from in-paper / supplementary tables, anchored to samples **by value** (never by column name); *backfill* — apply a single whole-project value where a study is uniform (the ≥95%-majority rule); *escalation* — surface tight near-misses for a human decision (wide mixes go to per-sample); *fill* — assemble the production `filled_metadata` table.

**Human-in-the-loop.** Curators attach paywalled PDFs (`attach_papers`), add per-isolate supplementary tables (`local_supplements`), and answer the escalation queue (`escalate --interactive`); committed answers are sticky (re-injected from the versioned `curated_escalations.tsv` master). Study-level find/grade disagreements are adjudicated and signed off (`review_adjudication`).

**Overwrite policy.** Fills only populate BLANK cells, with two sanctioned exceptions: a same-year `collection_date` refinement, and a single-hop vague→specific replacement passed by the fidelity judge. A `never_overwrite` field is never changed. In the canonical merge onto human curation the precedence is **human-curated > agent > ENA**.

**Always-on gates.** Every run is checked by the escalation-conservation gate (no curator answer lost across detect→apply→master→fill), the overwrite-radius gate (no recorded value changed beyond the sanctioned exceptions), and `verify_pipeline_triggers` (every stage fired; no silent zero-fill); `run_health` grades every (study×field) FILLED/ACTIONABLE/BLOCKED/EXHAUSTED.

**How each figure below is derived.**

- **§1 Reconciliation** — Σ per-tranche agent fills (`run_progress/<tag>/fill/filled_metadata_summary.md`) vs the accumulated master (`curated/metadata_curated_master_summary.md`); must match to the cell.
- **§2 Papers** — `run_progress/<tag>/find/found_papers.tsv` (studies reviewed, papers found) + `grade/study_grades.tsv` (`is_full_text`, `fulltext_source==local_pdf`). *Studies reviewed* counts every study whose candidate papers were assessed; *papers found* counts those with a resolved paper.
- **§3 Experimental-evolution** — `study_type_excluded==True` in the master (`curated/metadata_curated_master.tsv`): studies excluded from the analysis cohort.
- **§4 Completeness** — `evaluation/completeness_by_split.py`: presence (placeholder-stripped) of raw ENA (`base_table.csv`) vs agent (master) vs the v2 gold's `*_parsed` columns, on the master∩gold cohort → `scorecard/final_completeness_raw_agent_gold.{md,tsv}`.
- **§5a Accuracy** — `validate_find_papers` / `validate_study_grading` with adjudication → `run_progress/<tag>/scorecard/agent_vs_manual.tsv` (train/test only — the gold folds).
- **§5b/§5c Value correctness** — `evaluation/validate_backfill_values.py`, splitting blank-fills (scored vs the v2 gold) from gated overwrites (scored vs the parsed-ENA they replace → low by construction, surfaced for spot-review).
