# CLAUDE.md — bac_isescan

The `bac_isescan` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for
the monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

`bac_isescan` analyses insertion-sequence (IS) elements — detected by
[ISEScan](https://github.com/xiezhq/ISEScan) — across the *Klebsiella
pneumoniae* species complex: IS-family copy number per genome, per-clonal-group
family profiles, the gene context of each IS, and which Panaroo pangenome
clusters are recurrently flanked by IS ("hotspots").

## Layout

Flat package — each module is a standalone CLI.

| Module | Purpose |
|---|---|
| `isescan_constants.py` | Canonical IS-family / metadata column names; `cluster_csv_column()` |
| `isescan_utils.py` | Shared helpers — `is_missing_value()`, `parse_bool()` |
| `isescan_family_copy_per_sample.py` | ISEScan CSVs → one wide per-sample family+cluster count table |
| `isescan_family_heatmap_analysis.py` | Per-clonal-group mean/SD IS-family heatmaps |
| `isescan_gene_context.py` | Map IS coordinates to per-genome gene context (overlap + flanks) via GFFs |
| `isescan_lineage_hotspots.py` | Per-lineage flanking-context → Panaroo-cluster hotspot enrichment test |

## Cross-package dependency

`isescan_family_heatmap_analysis.py` imports the clonal-group selection helper
`bac_panaroo.tl.define_epidemic_cgs` (kept in `bac_panaroo`; shared with
`bac_cohort`). Works because the monorepo shares one uv environment.

`isescan_family_copy_per_sample.py` runs on Slurm via
`slurm_scripts/isescan_n_per_sample.sh`.
