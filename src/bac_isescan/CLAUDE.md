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
| `_lineage_hotspot_common.py` | Shared per-lineage prep (filter IS rows, map to Panaroo clusters, build long flank-event form, family-conditioned null) — imported by both hotspot modules |
| `isescan_lineage_panaroo_hotspots.py` | Per-lineage hotspots grouped by **(Panaroo cluster, IS family)** — recurrence test against the family-conditioned uniform-over-clusters null + Kleborate left-join |
| `isescan_lineage_kleborate_hotspots.py` | Pivot of the same flank events onto **(Kleborate label, IS family)** — virulence genes + AMR drug classes (descriptive; no enrichment test) |

## Cross-package dependency

`isescan_family_heatmap_analysis.py` imports the clonal-group selection helper
`bac_panaroo.tl.define_epidemic_cgs` (kept in `bac_panaroo`; shared with
`bac_cohort`). Works because the monorepo shares one uv environment.

`isescan_family_copy_per_sample.py` runs on Slurm via
`src/bac_isescan/slurm_scripts/isescan_n_per_sample.sh`.
