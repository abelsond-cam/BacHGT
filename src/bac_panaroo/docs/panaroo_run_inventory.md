# Panaroo Run Inventory

**Generated:** 2026-05-06  
**Data root:** `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome/`

## Overview

All 60 Panaroo runs with reference genomes are complete. Below is a complete inventory by run type.

| Run Type | Count | Total Samples | Notes |
|----------|-------|---------------|-------|
| KP Sublineage (single) | 36 | ~38,000 | Single lineage runs where `n_samples < 2500`; SL labeled `sublineage-other` |
| KP Sublineage (split) | 9 | ~24,000 | Large lineages split into parts; SL labeled `sublineage-split` (e.g. SL15_part_0, SL15_part_1). SL258 has 5 parts, SL147 has 2 parts. |
| KP Rare Lineage Batches | 11 | ~16,500 | Pooled rare sublineages (each `<250` samples); labeled `rare-lineage`. Batches 0–10 group rare SLs together for processing efficiency. |
| Non-KP Species | 6 | ~7,000 | Other Klebsiella species runs (K. africana, K. quasipneumoniae, K. variicola, etc.) |
| **TOTAL** | **60** | **~79,500** | All runs completed. |

---

## KP Sublineage Runs (single): sublineage-other

Small-to-medium K. pneumoniae sublineages (≤2500 samples), each run as a single folder.

| Run | Samples | CGs (total) | Major CGs (≥250) | Genes | RefSeq | mgh78578 shared |
|-----|---------|-------------|------------------|-------|--------|-----------------|
| SL1 | 320 | 12 | — | 12,137 | 43 | 4,042.39 |
| SL13 | 648 | 12 | CG13 (520) | 12,937 | 6 | 3,988.54 |
| SL107 | 702 | 26 | CG219 (409) | 13,665 | 14 | 3,995.64 |
| SL111 | 601 | 13 | CG111 (497) | 14,993 | 16 | 4,032.52 |
| SL133 | 251 | 11 | — | 11,271 | 11 | 4,014.8 |
| SL152 | 422 | 19 | — | 13,991 | 17 | 4,026.3 |
| SL200 | 291 | 25 | — | 11,342 | 9 | 3,943.22 |
| SL2004 | 380 | 12 | — | 10,430 | 11 | 4,033.88 |
| SL23 | 864 | 2 | CG23 (863) | 11,272 | 159 | 3,938.6 |
| SL25 | 591 | 3 | CG25 (353) | 11,936 | 19 | 4,053.95 |
| SL252 | 393 | 16 | — | 12,813 | 11 | 4,082.99 |
| SL268 | 951 | 55 | CG268 (420) | 18,601 | 31 | 4,050.44 |
| SL29 | 908 | 30 | — | 17,409 | 42 | 4,028.94 |
| SL3010 | 502 | 69 | — | 16,541 | 14 | 4,038.58 |
| SL323 | 395 | 3 | CG323 (321) | 11,199 | 21 | 4,029.14 |
| SL34 | 531 | 98 | — | 17,787 | 25 | 3,992.84 |
| SL35 | 779 | 21 | CG35 (608) | 16,102 | 31 | 4,005.9 |
| SL383 | 295 | 20 | — | 12,464 | 12 | 4,013.67 |
| SL39 | 886 | 3 | CG39 (684) | 12,245 | 19 | 4,042.6 |
| SL405 | 500 | 4 | CG405 (490) | 10,154 | 7 | 4,033.96 |
| SL48 | 567 | 3 | CG14188 (413) | 11,479 | 10 | 4,056.36 |
| SL661 | 408 | 24 | CG661 (290) | 15,301 | 15 | 4,084.21 |
| SL76 | 316 | 37 | — | 14,295 | 19 | 4,091.82 |
| SL86 | 391 | 4 | CG86 (356) | 9,089 | 31 | 3,995.18 |

---

## KP Sublineage Runs (split): sublineage-split

Large K. pneumoniae sublineages split into multiple parts for memory efficiency. Each SL suffix (e.g., `_part_0`) refers to a separate Panaroo run.

| Run | Samples | CGs (total) | Major CGs (≥250) | Genes | RefSeq | mgh78578 shared |
|-----|---------|-------------|------------------|-------|--------|-----------------|
| SL14 | 2,517 | 8 | CG14 (2,236) | 17,284 | 73 | 4,018.29 |
| SL15_part_0 | 1,822 | 9 | CG15 (1,796) | 16,706 | 89 | 3,951.57 |
| SL15_part_1 | 1,823 | 10 | CG15 (1,799) | 16,416 | 74 | 3,976.01 |
| SL17_part_0 | 2,318 | 81 | CG16 (950), CG17 (627) | 22,688 | 52 | 4,022.91 |
| SL17_part_1 | 2,318 | 77 | CG16 (899), CG17 (655), CG20 (342) | 22,882 | 63 | 4,019.81 |
| SL37 | 1,864 | 76 | CG37 (602) | 24,470 | 103 | 4,040.89 |
| SL45 | 1,797 | 34 | CG45 (1,547) | 18,580 | 53 | 4,088.19 |
| SL101 | 1,595 | 2 | CG101 (1,546) | 13,660 | 74 | 3,985.1 |
| SL147_part_0 | 2,546 | 10 | CG147 (2,513) | 17,065 | 93 | 4,055.99 |
| SL147_part_1 | 2,544 | 11 | CG147 (2,506) | 17,268 | 86 | 3,998.08 |
| SL231 | 1,050 | 7 | CG231 (1,029) | 11,847 | 58 | 3,989.11 |
| SL258_part_0 | 3,249 | 14 | CG258 (1,929), CG340 (773), CG11 (650) | 18,047 | 189 | 4,004.99 |
| SL258_part_1 | 3,245 | 17 | CG258 (1,918), CG340 (778), CG11 (698) | 18,224 | 212 | 4,037.3 |
| SL258_part_2 | 3,248 | 15 | CG258 (1,896), CG340 (746), CG11 (677) | 18,024 | 169 | 4,018.05 |
| SL258_part_3 | 3,252 | 13 | CG258 (1,927), CG340 (757), CG11 (658) | 17,466 | 181 | 4,046.56 |
| SL258_part_4 | 3,251 | 13 | CG258 (1,914), CG340 (779), CG11 (683) | 18,086 | 201 | 4,016.32 |
| SL307_part_0 | 2,220 | 3 | CG307 (2,213) | 15,151 | 77 | 4,072.71 |
| SL307_part_1 | 2,212 | 3 | CG307 (2,207) | 14,769 | 84 | 4,012.6 |
| SL395 | 851 | 3 | CG395 (591), CG10190 (300) | 10,920 | 41 | 3,938.29 |

---

## KP Rare Lineage Batches: rare-lineage

Pooled rare K. pneumoniae sublineages (each SL <250 samples). Batches contain multiple small sublineages mixed together for efficient processing. No individual major CGs (clusters are all rare/small).

| Batch | Samples | Sublineages | CGs (total) | Genes | RefSeq | mgh78578 shared |
|-------|---------|-------------|-------------|-------|--------|-----------------|
| kp_rare_sublineage_batch_0 | 1,505 | 7 | 32 | 19,611 | 47 | 4,083.11 |
| kp_rare_sublineage_batch_1 | 1,591 | 11 | 95 | 22,281 | 68 | 4,027.67 |
| kp_rare_sublineage_batch_2 | 1,519 | 14 | 89 | 21,766 | 49 | 4,034.55 |
| kp_rare_sublineage_batch_3 | 1,557 | 20 | 121 | 23,544 | 53 | 4,026.93 |
| kp_rare_sublineage_batch_4 | 1,508 | 26 | 96 | 23,318 | 70 | 4,020.22 |
| kp_rare_sublineage_batch_5 | 1,507 | 37 | 156 | 25,678 | 41 | 4,015.44 |
| kp_rare_sublineage_batch_6 | 1,504 | 55 | 145 | 24,978 | 76 | 4,028.22 |
| kp_rare_sublineage_batch_7 | 1,499 | 87 | 205 | 26,447 | 78 | 4,032.76 |
| kp_rare_sublineage_batch_8 | 1,497 | 161 | 325 | 28,339 | 59 | 3,998.83 |
| kp_rare_sublineage_batch_9 | 1,499 | 404 | 570 | 31,217 | 55 | 3,971.5 |
| kp_rare_sublineage_batch_10 | 829 | 615 | 644 | 28,339 | 30 | 3,972.31 |

---

## Non-KP Species: non-kp-species

Other Klebsiella species runs (not K. pneumoniae). Each run contains all samples of that species with their natural diversity.

| Species | Run Directory | Samples | Sublineages | CGs (total) | Genes | RefSeq | mgh78578 shared |
|---------|---------------|---------|-------------|-------------|-------|--------|-----------------|
| *Klebsiella africana* | species_Klebsiella_africana | 18 | 5 | 5 | 6,369 | 4 | 3,690.12 |
| *K. quasipneumoniae* ssp. *quasipneumoniae* | species_Klebsiella_quasipneumoniae_subsp._quasipneumoniae | 1,081 | 276 | 407 | 28,557 | 66 | 3,434.87 |
| *K. quasipneumoniae* ssp. *similipneumoniae* | species_Klebsiella_quasipneumoniae_subsp._similipneumoniae | 2,497 | 416 | 646 | 35,109 | 116 | 3,463.75 |
| *K. quasivariicola* | species_Klebsiella_quasivariicola | 77 | 14 | 24 | 12,385 | 5 | 3,689.07 |
| *K. variicola* ssp. *tropica* | species_Klebsiella_variicola_subsp._tropica | 15 | 12 | 12 | 8,043 | 3 | 3,721.14 |
| *K. variicola* ssp. *variicola* | species_Klebsiella_variicola_subsp._variicola | 3,050 | 632 | 1,019 | 40,094 | 187 | 3,542.28 |

---

## Directory Notes

- **`batches/`** — Batch metadata TSVs and Slurm array list files. Not modified by Panaroo runs.
- **`genome_stats/`** — Analysis outputs: summary statistics, plots, run inventory, combined detail TSVs.
- **Each run folder** (e.g., `SL101/`, `kp_rare_sublineage_batch_0/`)
  - Contains a copy of the batch metadata TSV
  - Panaroo outputs: `gene_presence_absence.csv`, `gene_presence_absence.Rtab`, `final_graph.gml`, etc.
  - `analysis/GPA_reference_genome/` — Distance analysis outputs (per-run and per-CG detail TSVs, clustering plots, logs)

---

## GPA Reference Granularity Analysis

Produced by `src/bac_panaroo/gpa_analysis/gpa_reference_granularity.py` (delegates plotting to `src/bac_panaroo/gpa_analysis/granularity_lollipop.py`). Quantifies how mean shared-gene count between a query sample and its assigned RefSeq grows as the RefSeq becomes more granular: from a single global anchor (mgh78578), to a per-Panaroo-run RefSeq, to a per-CG RefSeq, to a per-sample RefSeq.

**Output location:** `<DATA_ROOT>/processed/pangenome_analysis/granularity/`

```
granularity_table.tsv           # one row per strain — main analysis output
granularity_summary.tsv         # aggregate stats
granularity_notes.log           # CG-level d→c gain highlights (human-readable)
run_inventory.md                # generated copy of run metadata
plots_png/
  granularity_lollipop_sl.png                              # base SL view, all greyscale
  granularity_lollipop_sl_highlight_species.png            # non-KP species in dark blue
  granularity_lollipop_sl_highlight_epidemic.png           # KP epidemic SLs in dark blue
  granularity_lollipop_sl_highlight_epidemic_high_gain.png # only SLs with d→c > 20 genes
  granularity_lollipop_sl_highlight_rare.png               # rare-lineage batches in dark blue
  granularity_gain_histogram_f_to_d.png                    # mgh → SL
  granularity_gain_histogram_d_to_c.png                    # SL → CG
  granularity_gain_histogram_c_to_b.png                    # CG → CG/K-locus
  granularity_gain_histogram_b_to_a.png                    # CG/K-locus → per-sample
plots_pdf/  (mirror of plots_png/)
```

### Levels (granularity nodes)

The lollipop plots each strain as a connected line across **five** nodes; values are the mean number of genes shared between the run's query genomes and the chosen reference. The reference set is `is_reference_genome ∪ is_mgh78578`; query genomes are all non-reference genomes present in the run.

| Node | Label on plot | Definition | Notes |
|---|---|---|---|
| `f` | **Ref mgh78578** | mgh78578 mean shared genes vs the run's query genomes (per-Panaroo-run baseline) | NaN for runs that don't include mgh78578 |
| `d` | **Best reference in SL** | Per-CG row: run-wide best reference applied to that CG's samples. SL/run summary row: n_samples-weighted mean across all SL-level subgroups in the run (major SLs + `other_SL` bucket) of each SL's `best_shared`. For KP sublineage runs the SL split is degenerate so this collapses to the run-wide best reference. For `kp_rare` and `kp_species` runs the SL split is non-trivial — d reflects per-SL personalisation rather than one ref for the whole heterogeneous run. |
| `c` | **Best reference in CG** | Per-CG row: best reference for that CG's samples. SL/run summary row: weighted mean across **all** CG-level subgroups (CGs within each major SL + each SL's `other_CG` bucket + the run's `other_SL` bucket as a single non-recursive contribution) — eliminates bias toward big children at any level. |
| `b` | **Best reference in CG / K-locus** | Per-CG row: weighted mean across the CG's K-locus subgroups (incl. `other_KL`). SL/run row: weighted mean across all KL-level leaves; nodes that bottom out earlier (no K-locus split) contribute their own `best_shared`. |
| `a` | **Best reference Per-Sample** | Mean over per-sample max shared genes across all references in that run | |

> **Level `e` (Best reference in Subspecies)** — previously a sixth node between `f` and `d`: a single best reference chosen per query species via cross-run aggregation over a fixed reference bucket (mgh + Norway-completes + HS11286). It was **removed** when the reference bucket was scrubbed — without a fixed cross-run reference pool it collapsed toward level `d`. Recoverable from git history; to be revisited after the pangenome_merge experiment.

`level_f ≤ level_d ≤ level_c ≤ level_b ≤ level_a` is monotone by construction (each step either widens the ref pool or narrows the query scope).

### Row types (`row_type` column)

| Value | Source | Description |
|---|---|---|
| `kp_epidemic` | One row per major CG (`n_samples ≥ --min-group-size`) within a KP sublineage Panaroo run. `c` is the CG's own best RefSeq; `b` is its K-locus subgroup mean. |
| `kp_epidemic_sl` | One row per KP sublineage Panaroo run. `c` and `b` are weighted means across **all** top-level CG subgroups in the run, including the `other` bucket of small CGs (so the SL row truly represents the whole sublineage, not just its big CGs). |
| `kp_rare` | One row per `kp_rare_sublineage_batch_*` Panaroo run; same SL-style aggregation as `kp_epidemic_sl`. |
| `kp_species` | One row per `species_*` Panaroo run; same SL-style aggregation. |

The CG-size threshold is now controlled solely by the granularity script's own `--min-group-size` (default 50), and the same threshold is applied uniformly to the SL split, the CG split, and the K-locus split. The script walks Panaroo runs directly via `gene_presence_absence.Rtab` and does its own three-level splitting (`Sublineage` → `Clonal group` → `K_locus`) via `bacotype.tl.panaroo_groups.hierarchical_split` — no dependence on `gpa_distances_batch_runs.sh` having pre-computed per-CG slices.

### Key columns of `granularity_table.tsv`

`strain`, `Sublineage`, `row_type`, `directory_leaf`, `n_parts`, `n_samples`, `n_refseq_genomes`, `shared_genes_f/d/c/b/a`, `fallback_c`, `fallback_b`, `gain_f_to_d`, `gain_d_to_c`, `gain_c_to_b`, `gain_b_to_a`, `pct_gain_*`. (`n_refseq_genomes` counts `is_reference_genome ∪ is_mgh78578` genomes present in the run — the column name is retained for schema stability.)

`fallback_c = True` when no major CG-level subgroup exists in any major SL. `fallback_b = True` when no major K-locus subgroup exists in any major CG. The `c`/`b` flags are typical for the smallest rare-batch and species runs whose SLs and CGs are too small to clear `--min-group-size`.
