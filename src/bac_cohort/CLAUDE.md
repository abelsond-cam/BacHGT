# CLAUDE.md — bac_cohort

The `bac_cohort` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for
the monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

`bac_cohort` compares the **complete-genome cohort** against the **short-read
(MAG) cohort**, per clonal group, across feature classes — Kleborate virulence
loci, chromosomal MLST, acquired AMR, and ISEScan IS families — to find
features enriched or depleted by assembly cohort.

## Layout

Flat package — each module is a standalone CLI.

| Module | Purpose |
|---|---|
| `cg_feature_cohort_analysis.py` | Per-CG complete-vs-short-read feature comparison; p-value-sorted count/penetrance tables |
| `cg_feature_heatmaps.py` | Heatmaps of complete-vs-short-read enrichment from those count tables |
| `cg_virulence_penetrance_all.py` | Per-CG virulence-BSC penetrance (all CGs over a threshold); long-format TSV + scatter |
| `cg_virulence_penetrance_scatter.py` | Scatter plot for `cg_virulence_penetrance_all.py` (the plotting helper) |

`cg_virulence_penetrance_all.py` imports `cg_feature_cohort_analysis` and
`cg_virulence_penetrance_scatter` (both in this package).

## Cross-package dependency

`cg_feature_cohort_analysis.py` imports the clonal-group selection helper
`bac_panaroo.tl.define_epidemic_cgs` (kept in `bac_panaroo`; shared with
`bac_isescan`). Works because the monorepo shares one uv environment.
