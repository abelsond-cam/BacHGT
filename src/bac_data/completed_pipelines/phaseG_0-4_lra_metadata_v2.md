# Completed pipeline record — Phase G.0–G.4 (LRA cohort → metadata_v2 → SR-vs-LRA paired comparison)

Archived 2026-05-28 from the active plan (`~/.claude/plans/in-src-bac-data-we-look-curried-dragonfly.md`)
once G.0–G.4 were done + verified, to keep the active plan focused on G.5–G.8. This
is the durable record of what was built and the final numbers — enough to reconstruct
the comparison sets without the blow-by-blow.

For the upstream Phases A–E (LRA discovery → CheckM2 → accepted-set), see
`src/bac_data/lr_data/CLAUDE.md`. For the data model + flag taxonomy, see the active plan.

---

## The data model these phases produced

- **`Sample` is the assembly key.** Where an accepted LRA exists, `Sample` = its versioned
  GCF/GCA (`scoring_accession`); otherwise `Sample` = the SR BioSample.
- **`lra_final_set` (bool)** — True iff `Sample` is in the accepted-LRA set
  (`lra_final_set.tsv`, 5,521 rows passing the locked 3-criterion CheckM2 rule:
  completeness ≥ 99.0, contamination ≤ 5.0, genome_size ≤ 7.23 Mb).
  *(Renamed to `lra_final_list` in G.6.5 — post-dates this archive.)*
- **`kpsc_final_list` = `lra_final_set ∧ is_kpsc`** on LRA-bearing rows.
- Legacy `is_complete` / `is_refseq` columns dropped from v2 (the GCF prefix encodes RefSeq).

---

## G.0 — `bac_cohort` → `bac_complete_genomes` refactor

`git mv src/bac_cohort src/bac_complete_genomes`; split into `per_clonal_group/`
(cross-section CG analysis) + `paired_lra_vs_sra/` (new paired work);
`cg_feature_cohort_analysis.py` → top-level `compare_lra_to_sra.py` with
`--mode {clonal_group, paired}`. The shared Kleborate/ISEScan parsing primitives
(`KLEBORATE_VIRULENCE_LOCI`, `kleborate_cell_present`, `kleborate_column_to_presence`,
`load_isescan_features`, `count_acquired_tokens`, `safe_numeric_column`) live at the
top level and are imported by both sub-modules. History preserved via `git mv`.

## G.1 — `build_metadata_v2.py`: the metadata merger

`src/bac_metadata/pp/build_metadata_v2.py`. Builds metadata_v2 from v1 + `lra_final_set.tsv`
+ `lra_discovery.tsv` + `related_lr_run_accessions.csv`.

- **Step 0 — pre-cleanup**: dropped **3,078** LR-appended rows from v1 (filter
  `is_refseq==False AND related_sr_accession.notna()`). (Plan estimated 2,576; reality
  was 3,078 — all verified PacBio/ONT runs with populated run_accession.)
- **Step 1 — LRA→metadata match** (priority order): (1) is_refseq accession
  `lra.scoring_accession ↔ metadata.Sample`; (2) audit chain
  `lra.related_lr_run_accession ↔ metadata.related_lr_accession`; (3) orphans → ingested.
- **Step 2 — SR-partner merge**: for each is_refseq row whose `related_sr_accession`
  matches an SR row, copy SR metadata onto the refseq row, drop the SR row.
- **Step 3 — orphan ingestion** (G.1.1): **117** orphan LRAs ingested as new pure-LR rows
  (plan estimated 124; 7 reclaimed by a Priority-2 audit match after the `load_norway`
  `ont_acc` bugfix). Enriched from the Norway Table S1 xlsx via `metadata_curation.py`
  parse/categorise functions (host, isolation_source, country=Norway, region, collection_date).
- Post-build: `Sample` flipped to GCF/GCA on matched rows; `lra_*`/`lr_*` cols populated;
  `sr_biosample` preserves the original SAM*; `kleborate_needs_recall` / `isescan_needs_recall`
  set True (cleared in G.2). `_was_v1_is_refseq` tracking col added to handle the
  Sample-flip in the is_refseq cross-table.

**Result**: v2 ≈ 86,985 rows × 456 cols (down from v1's 90,903 due to LR-appended +
SR-partner + Norway-pair dedup). Ingested orphans initially carried NaN
species/is_kpsc/kpsc_final_list — addressed by the G.2 cascade.

### Key bugfix in this phase
`build_lra_discovery.py` `load_norway()` was mapping `df["ont_in_run_accession"]` (a boolean)
to `related_lr_run_accession` instead of `df["ont_acc"]`. Fixed; discovery TSV rebuilt.

## G.2 — Re-call Kleborate + ISEScan on the LRA cohort + cascades

| Module | Purpose |
|---|---|
| `src/bac_kleborate/run_kleborate_lra.py` + `slurm_scripts/run_kleborate_lra.sh` | `prepare`/`worker`/`collate` Kleborate v3 (`-p kpsc`) over the 5,521 LRAs; Slurm array (icelake-himem, 4 CPU, 56 chunks × 100). Uses the bac_isescan pixi env (kleborate ≥ 3.1). Output cols are **namespaced** (`enterobacterales__species__species`, `klebsiella_pneumo_complex__mlst__gapA`). |
| `src/bac_metadata/pp/merge_kleborate_into_metadata_v2.py` | species → is_kpsc → kpsc_final_list cascade on lra_final_set rows. Discards non-Klebsiella (E. coli) by flipping `lra_final_set=False` (2 discards). Preserves v1 species for the 107 LRAs Kleborate v3 can't type (K. aerogenes / Raoultella). `_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")` accepts bare GCAs. Rule: `kpsc_final_list = is_kpsc` universally on the LRA cohort. |
| `src/bac_isescan/run_isescan_lra.py` + `slurm_scripts/run_isescan_lra.sh` | Mirror of the Kleborate runner. Slurm array (icelake-himem, 4 CPU, ~184 chunks × 30, time bumped 6h→24h). Resumable via per-sample `.isescan.done` sentinels. **Completed: array 29726541 finished all 552 tasks 2026-05-27; 5,519/5,519 sentinels.** |
| `src/bac_metadata/pp/merge_isescan_into_metadata_v2.py` | Adds one `IS_<family>` count column per family to every lra_final_set row; clears `isescan_needs_recall`. |
| `src/bac_metadata/pp/merge_norway_pairs_into_v2.py` | Late-discovered: G.1's audit match missed Norway LR-extras (their SR rows had no `related_lr_accession=ONT`). Re-runs the audit-style overlay keyed on the Norway integration TSV's biosample. **467 pairs merged** (445 from integration TSV + 22 from xlsx `ont_acc` fallback). 4 standalone GCF rows unfixable without NCBI lookup (out of scope). Bugfixes: `itertuples` mangles leading-underscore fieldnames (renamed `_gca_bare`→`gca_bare`); scalar check for sr-partner `lra_final_set`. |
| `src/bac_metadata/pp/rebuild_v2.sh` | Orchestrator: build_metadata_v2 → merge_norway_pairs → merge_kleborate → merge_isescan → import_sr_kleborate → import_sr_isescan → build_sr_shadow_for_lra. Flags `--skip-g1`, `--skip-isescan`, `--skip-sr-import`. |

**Numbers as built**: v2 86,518 rows; LRA cohort 5,519 lra_final_set=True (5,521 − 2 E. coli);
KPSC LRAs 5,263; KoSC 144; non-Kp/Ko-typed 107; LRA cross-table sanity 0 rows with
lra=T & kpsc_final_list≠is_kpsc.

## G.3 — SR-shadow table + seb-tree SR-side import

`src/bac_metadata/pp/build_sr_shadow_for_lra.py` snapshots SR-side QC + Kleborate +
ISEScan for every paired SR+LR row, frozen before the LRA-side overwrote v1. Column
policy: QC_COLUMNS, SPECIES_COLUMNS, MLST_COLUMNS (gapA/infB/mdh/pgi/phoE/rpoB/tonB/ST),
AMR (`*_acquired`/`*_chr`/`*_mutations`), virulence (ybt/clb/iuc/iro/rmp/wzi/K_locus/O_locus
prefixes). Output **2,919 paired rows × 128 cols**.

### The SR-side import (the crux of the G.4 bug-hunt — see below)
SR Kleborate + ISEScan existed in Seb's tree but were never merged into v1 for ~957
priority-3 audit-matched pairs. Two importers built:
- `src/bac_metadata/pp/import_sr_kleborate.py` — concats `<RDS>/seb/kleborate_v3.2.4/<batch>/`
  (25 KpSC + 3 KoSC + 4 E.coli + 4 species batch dirs; `strain` col = BioSample). Auto-flattens
  Kleborate-v3 namespaced columns; `--extra-kpsc` unions our own runs.
  Output `<RDS>/seb/sr_kleborate_v3.2.4.tsv` = **87,378 BioSamples × 149 cols**.
- `src/bac_metadata/pp/import_sr_isescan.py` — parses `<RDS>/seb/ISEScan_results/csv_files/`
  (81,059 CSVs, key `<biosample-or-GCx>_<runid>.fa.csv`) → per-Sample IS-family counts.
  Output `<RDS>/seb/sr_isescan_long.tsv` (3.5M rows) + `<RDS>/seb/sr_isescan_family_counts.tsv`
  (**81,059 samples × 25 families**).

`build_sr_shadow_for_lra.py` was extended (`--sr-kleborate`, `--sr-isescan`) to fill NaN
Kleborate cells from the seb sidecar (70,550 cells filled) + append `sr_IS_<family>` cols.

## G.4 — SR-vs-LRA paired comparison + the 957→127 bug-hunt

`compare_lra_to_sra.py --mode paired` reads metadata_v2 + sr_shadow_for_lra.tsv, joins on
`sr_biosample`, applies McNemar (binary features) + paired t / Wilcoxon (numeric).
Output `<RDS>/david/processed/complete_vs_sr_genomes/lra_vs_sr_comparison.tsv` (36 features).

**The bug-hunt**: the first run was "too clean" — 754 LR-only virulence calls / **0** SR-only
(statistically impossible). Root cause: 957 priority-3 audit-matched pairs had **no SR-Kleborate
in v1** (it lived unmerged in `<RDS>/seb/kleborate_v3.2.4/`). After importing the seb sidecars
(G.3) and re-running:
- Virulence BSC LR-only/SR-only: 754/0 → 195/24 → **123/30** (real two-sided signal).
- MLST LR-only/locus: 957 (single col) → ~190 → **~127** across all 7 housekeeping loci.

The residual 127 = samples that were **`kpsc_final_list=False` in v1** so Seb never staged an
SR assembly (no SR-Kleborate possible). Of the original 189-sample residual: **62** had SR
assemblies in Seb's empty batch-98 dir → Kleborate run on them locally + merged (`--extra-kpsc`);
**127** have no SR assembly anywhere (all KPSC by ENA taxonomy + paired LRA's Kleborate, but
`kpsc_final_list=False` in v1). **Accepted as documented gap.**

The 127 MLST LR-only / 0 SR-only is now coverage-attributable (not biology) — housekeeping
genes don't fail SR detection when Kleborate actually ran.

### G.4.5 — `paired_index.tsv` (built 2026-05-27, commit e46dadd)
`src/bac_metadata/pp/build_paired_features.py`. Join `v2.Sample ↔ lra_final_set.scoring_accession`.
Output `<RDS>/david/processed/complete_vs_sr_genomes/paired_index.tsv` = **2,919 rows × 20 cols**
(identity + per-LRA NCBI assembly_level / CheckM2 QC / provenance / species / kpsc_final_list).
`lra_features.tsv` + `sr_features.tsv` deferred (built post-G.6).

---

## Canonical outputs on RDS (as of this archive)

| File | Rows × cols | What |
|---|---|---|
| `<RDS>/david/final/metadata_v2_all_samples_and_columns.tsv` | 86,518 × 456 | the unified assembly-keyed metadata |
| `<RDS>/david/processed/lra_final_set.tsv` | 5,521 | accepted-LRA set (→ moved+renamed `lra_final_list.tsv` in G.6) |
| `<RDS>/david/final/sr_shadow_for_lra.tsv` | 2,919 × 128 | frozen SR-side snapshot (→ moved in G.6) |
| `<RDS>/seb/sr_kleborate_v3.2.4.tsv` | 87,378 × 149 | SR-Kleborate sidecar (imported from seb tree) |
| `<RDS>/seb/sr_isescan_family_counts.tsv` | 81,059 × 26 | SR-ISEScan per-Sample IS-family counts |
| `<RDS>/david/processed/complete_vs_sr_genomes/paired_index.tsv` | 2,919 × 20 | paired-cohort index |
| `<RDS>/david/processed/complete_vs_sr_genomes/lra_vs_sr_comparison.tsv` | 36 | paired-comparison stats |

## Key modules (all committed)

`build_metadata_v2.py`, `merge_kleborate_into_metadata_v2.py`,
`merge_isescan_into_metadata_v2.py`, `merge_norway_pairs_into_v2.py`,
`build_sr_shadow_for_lra.py`, `import_sr_kleborate.py`, `import_sr_isescan.py`,
`build_paired_features.py`, `rebuild_v2.sh` (all in `src/bac_metadata/pp/`);
`run_kleborate_lra.py` (`src/bac_kleborate/`), `run_isescan_lra.py` (`src/bac_isescan/`);
`compare_lra_to_sra.py` (`src/bac_complete_genomes/`).
