# Phase G — sessions 2 + 3 (G.4.5, G.6, G.6.5, G.6.6, G.7, G.8a-d, G.9 deferred)

Continuation of [`phaseG_0-4_lra_metadata_v2.md`](phaseG_0-4_lra_metadata_v2.md). Records the LRA-cohort / metadata_v2 work completed across two follow-on sessions; remaining work tracked in the active plan / `METADATA_v2_README.md`.

## G.4.5 — Paired feature tables (`build_paired_features.py`)

Wrote three artefacts under `<RDS>/david/processed/complete_vs_sr_genomes/`:
- `paired_index.tsv` — 2,919 rows: `(lra_sample, sr_biosample, lra_gca, lra_gcf, lra_assembly_level, …)`. Identity + paired join key.
- `lra_features.tsv` — 2,919 × 115 columns.
- `sr_features.tsv` — 2,523 × 172 columns (superset; user's call to leave wider).

109 feature cols overlap between the two (incl. all acquired-AMR). Used by `bac_complete_genomes` paired mode + downstream analyses.

## G.6 / G.6.5 / G.7 — RDS reorg + cohort rename + NCBI enrichment

- Renamed `lra_final_set` → **`lra_final_list`** end-to-end.
- Discovery artefacts under `complete_vs_sr_genomes/lr_discovery/`.
- NCBI Datasets API enrichment added the level / library_class fields and derived flags:
  - `is_complete` ← `level == "Complete Genome"`
  - `is_hybrid` ← `library_class == "hybrid"`
  - `is_reference_genome` ← `is_complete ∧ is_hybrid ∧ scoring_accession.startswith("GCF_")`
- All three propagated into metadata_v2 (86,518 × 483). Authoritative derivation in `src/bac_data/lr_data/build_lra_set.py:120-127`.
- `rebuild_v2.sh` solidified as the 8-step cascade orchestrator.

## G.6.6 — Move `*_lra` directories under `complete_vs_sr_genomes/`

On HPC, relocated `checkm2_lra` / `kleborate_lra` / `isescan_lra` from `processed/<name>_lra/` into `processed/complete_vs_sr_genomes/<name>_lra/`. Repointed all 23 dir-path constants across the codebase (commit `a5fc6bd`). Zero residual references to old `processed/<name>_lra/` paths.

## G.8a-d — `compare_lra_to_sra.py --mode paired` (first-pass output)

Iterative landing of the paired comparison tables:
- **G.8** (`7ac7b87`) — `--cohort {lra_final_list, reference_genome, both}` switch; output column reorder (counts first, stats / `n_pairs` to end); binary `amr_presence` row alongside numeric AMR rows; `count_acquired_tokens` now ignores Kleborate `-` no-hit marker. `reference_genome` cohort (748) is a strict subset of `lra_final_list` (2,919).
- **G.8b** (`e56bfb5`) — count rows fill `both_positive` / `both_negative`; consistent category labels (`amr counts`, `amr presence / absence`, `mlst presence / absence`, `virulence presence / absence`, `virulence counts`).
- **G.8c** (`b4a79f1`) — count rows restricted to co-carrier pairs (`LR>0 & SR>0`).
- **G.8d** (up to `72b4d27`) — copy-flow `_paired_numeric_stats` over co-carriers; `_paired_isescan_features` added (24 IS families); two-table split: `lra_vs_sr_{kleborate,isescan}__<cohort>.tsv`.

The paired tables are being **reworked separately** (wide one-row-per-feature redesign) by a different agent. Do not edit `compare_lra_to_sra.py` paired mode in BacHGT G.5-onwards work.

## G.9 — Kleborate typing-block backfill (DEFERRED)

**Diagnosis.** 124 v2 rows are `kpsc_final_list==True` with null `Sublineage` (121 LRA orphan/Norway, 3 SR with v1 LINcode-sheet gaps). All have valid Kleborate species + ST calls; missing only the LIN sub-typing.

**Root cause.** Kleborate v3.2.4 (the pinned version) does **not** emit `Sublineage` / `LINcode` / `Clonal group` / `Phylogroup` — those came from a separate LIN-typing layer (Pasteur BIGSdb) folded into the QC Excel's LINcode sheet by v1's `qc_add_metadata.py`. Verified by inspecting all four collated Kleborate outputs (no `lincoding`/`Sublineage` columns).

**Status.** Re-running Kleborate or wiring the BIGSdb LIN-typing API is **not in scope** ("too fiddly, not important enough" — user 2026-05-29). The 124-row Sublineage gap is documented as a known issue in `METADATA_v2_README.md`'s To Do; revisit only if a downstream analysis needs it.

**Code edits retained** (net improvements, fill-on-empty, no risk to existing values):
- `src/bac_kleborate/run_kleborate_lra.py` — `cmd_prepare` filter widened to `lra_final_list ∪ kleborate_needs_recall`; FASTA source picks `lra_assembly_file` first, then `assembly_file` (SR).
- `src/bac_metadata/pp/merge_kleborate_into_metadata_v2.py` — added a full Kleborate-typing-block overlay (MLST + virulence MLSTs + AMR + Kaptive + wzi + cipro) on every row whose Sample matches a Kleborate output row. `_bare` now falls back to identity for non-`GC[AF]_` samples so SAM* rows can join. Fill-on-empty preserves curated v1 values on rows that already have them.
- `src/bac_metadata/pp/flag_kleborate_recall.py` — new CLI for setting `kleborate_needs_recall=True` on rows matching a gap criterion (default: `kpsc_final_list AND Sublineage null`). Unused while G.9 is deferred but reusable.

---

## Authoritative-source pointers

- Cohort gate (CheckM2 thresholds, scoring_accession): [`src/bac_data/lr_data/build_lra_set.py`](../lr_data/build_lra_set.py).
- LR/SR pairing + orphan ingest + 957 SR-RefSeq merge: [`src/bac_metadata/pp/build_metadata_v2.py`](../../bac_metadata/pp/build_metadata_v2.py).
- 8-step cascade: [`src/bac_metadata/pp/rebuild_v2.sh`](../../bac_metadata/pp/rebuild_v2.sh).
- Paired feature builder: [`src/bac_metadata/pp/build_paired_features.py`](../../bac_metadata/pp/build_paired_features.py).
- LR-Kleborate runner: [`src/bac_kleborate/run_kleborate_lra.py`](../../bac_kleborate/run_kleborate_lra.py).
- LR-ISEScan runner: [`src/bac_isescan/run_isescan_lra.py`](../../bac_isescan/run_isescan_lra.py).
