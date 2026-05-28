# CLAUDE.md — bac_complete_genomes

The `bac_complete_genomes` subpackage of the BacHGT monorepo. See
`BacHGT/CLAUDE.md` for the monorepo and `~/.claude/CLAUDE.md` for global
guidance.

(Renamed from `bac_cohort` in May 2026 as part of the Phase G metadata_v2
refactor — the new name reflects that the comparison work is anchored on the
complete-genome cohort, and that we now have both a cross-section and a
paired comparison mode.)

## Purpose

Compare the complete-genome cohort (after Phase G: rows with
`lra_final_list=True` in `metadata_v2`; pre-Phase-G: rows with `is_refseq=True`)
against the short-read (MAG) cohort, across feature classes: Kleborate
virulence loci, chromosomal MLST, acquired AMR, and ISEScan IS families.

## Two comparison modes

### Cross-section (clonal_group mode) — `per_clonal_group/`

Different samples in each arm, grouped per clonal group. Reports
p-value-sorted enrichment / penetrance tables and BSC heatmaps for the top-N
epidemic CGs + pooled rare CGs + all_samples.

| Module | Purpose |
|---|---|
| `compare_lra_to_sra.py` (top level; `--mode clonal_group`) | The cross-section driver. Produces counts + penetrance TSVs + log. |
| `per_clonal_group/cg_feature_heatmaps.py` | Heatmaps of complete-vs-short-read enrichment from those count tables. |
| `per_clonal_group/cg_virulence_penetrance_all.py` | Per-CG virulence-BSC penetrance for every CG above a threshold; long-format TSV + scatter. |
| `per_clonal_group/cg_virulence_penetrance_scatter.py` | Plot helper consumed by the all-CG penetrance driver. |

### Paired (paired mode) — `paired_lra_vs_sra/`

**Same biosamples in both arms** — SR-Kleborate frozen in
`<RDS>/david/processed/complete_vs_sr_genomes/sr_shadow_for_lra.tsv` (Phase G.3 output), LR-Kleborate
live in `metadata_v2` (Phase G.1+G.2 output). ~2,500-3,000 paired biosamples,
enabling McNemar's test on binary features + paired t-test / Wilcoxon
signed-rank on numeric features.

| Module | Purpose |
|---|---|
| `compare_lra_to_sra.py` (top level; `--mode paired`) | The paired driver (Phase G.4; placeholder until metadata_v2 ships). |
| `paired_lra_vs_sra/notebooks/lra_vs_sr_comparison.ipynb` | The G.4 analysis notebook — per-category bar charts + the BSC heatmap recoloured by paired LR-vs-SR delta + the headline LR-pickup-rate plot. |

## Shared parsers

`compare_lra_to_sra.py` at the top level exports the Kleborate / ISEScan
parsing primitives both modes consume — Kleborate virulence schema
(`KLEBORATE_VIRULENCE_LOCI`), presence/absence detector
(`kleborate_cell_present`, `kleborate_column_to_presence`), ISEScan loader
(`load_isescan_features`, `merge_metadata_isescan`), acquired-AMR token
counter (`count_acquired_tokens`), numeric coercion guard
(`safe_numeric_column`). Both sub-modules import these via
`from bac_complete_genomes.compare_lra_to_sra import …`.

## Cross-package dependency

`compare_lra_to_sra.py` (clonal_group mode) imports the clonal-group
selection helper `bac_panaroo.tl.define_epidemic_cgs` (kept in `bac_panaroo`;
shared with `bac_isescan`). Works because the monorepo shares one uv
environment.

## Running

```bash
# Cross-section, per-CG (default):
uv run python -m bac_complete_genomes.compare_lra_to_sra --mode clonal_group

# Paired SR-vs-LRA (after Phase G.4):
uv run python -m bac_complete_genomes.compare_lra_to_sra --mode paired

# Per-CG virulence-BSC penetrance for every CG over a threshold:
uv run python -m bac_complete_genomes.per_clonal_group.cg_virulence_penetrance_all

# Heatmaps from count tables:
uv run python -m bac_complete_genomes.per_clonal_group.cg_feature_heatmaps
```
