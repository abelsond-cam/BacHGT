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

## Two comparison modes — one wide schema

Both modes share the same wide per-feature schema and the same row-building
math (see `WIDE_OUTPUT_COLUMN_ORDER` in `compare_lra_to_sra.py`): per-arm
**per-genome sensitivity** (`n_positive_in_arm / n_total_in_arm`) + LR/SR
sensitivity ratio, gene-count totals + copies-per-carrier, and
`n_lr` / `n_sr`. No p-values, no q-values, no `category`. The only column
that differs is `penetrance_concordance` — populated in paired (from the
2×2 contingency, `(a+d)/n`), blank in clonal_group (different samples in
each arm). The sensitivity / concordance split keeps the two ideas
distinct: sensitivity is the per-arm detection rate (what we'd report as a
classifier's recall on the universe of genomes); concordance is pair-level
agreement (which is dominated by the both-absent cell `d` for rare
features and so reads ~0.9 even when sensitivity ratios are far from 1).

### Paired (paired mode) — `paired_lra_vs_sra/`

**Same biosamples in both arms** — SR-Kleborate + SR-ISEScan frozen in
`<RDS>/david/processed/complete_vs_sr_genomes/sr_shadow_for_lra.tsv`
(Phase G.3 output), LR-Kleborate + LR-ISEScan live in `metadata_v2`
(Phase G.1+G.2 output). Joined on `sr_biosample`. `n_lr == n_sr` by
construction; `penetrance_concordance = (a+d)/n_pairs` from the 2×2.

| Module | Purpose |
|---|---|
| `compare_lra_to_sra.py` (top level; `--mode paired`) | Paired driver. Writes `lra_vs_sr_kleborate__<cohort>.tsv` (virulence → joint `Complete chromosomal ST` → AMR) and `lra_vs_sr_isescan__<cohort>.tsv` (alphabetical) per cohort. Cohorts are nested: `lra_final_list` ⊃ `complete_genome` (`is_complete`) ⊃ `reference_genome` (`is_reference_genome`). |
| `paired_lra_vs_sra/notebooks/lra_vs_sr_comparison.ipynb` | The G.4 analysis notebook — per-category bar charts + the headline LR-pickup figure built from the wide rows. |

### Cross-section (clonal_group mode) — `per_clonal_group/`

**Different samples in each arm, grouped per clonal group.** No shadow join;
metadata_v2 only. Within each CG, the LR arm is the rows in the chosen cohort
(`--cohort lra_final_list` by default, or `reference_genome` for the strict
subset) and the SR arm is everything else. Same feature columns on both arm
subsets — `n_lr ≠ n_sr` in general. One combined wide TSV per CG with
`≥ --min-per-arm` rows in BOTH arms (default 10).

| Module | Purpose |
|---|---|
| `compare_lra_to_sra.py` (top level; `--mode clonal_group`) | Cross-section driver. Writes `<output_dir>/per_clonal_group/<CG>.tsv` (virulence → joint `Complete chromosomal ST` → AMR → ISEScan). |
| `per_clonal_group/cg_virulence_penetrance_all.py` | Per-CG virulence-BSC penetrance for every CG above a threshold; long-format TSV + scatter. |
| `per_clonal_group/cg_virulence_penetrance_scatter.py` | Plot helper consumed by the all-CG penetrance driver. |

## Shared parsers

`compare_lra_to_sra.py` at the top level exports the Kleborate / ISEScan
parsing primitives both modes consume — Kleborate virulence schema
(`KLEBORATE_VIRULENCE_LOCI`), presence/absence detector
(`kleborate_cell_present`, `kleborate_column_to_presence`), ISEScan loader
(`load_isescan_features`, `merge_metadata_isescan`), acquired-AMR token
counter (`count_acquired_tokens`), numeric coercion guard
(`safe_numeric_column`). Both sub-modules import these via
`from bac_complete_genomes.compare_lra_to_sra import …`.

## Running

```bash
# Paired SR-vs-LRA (one cohort) — writes 2 TSVs per cohort:
uv run python -m bac_complete_genomes.compare_lra_to_sra --mode paired --cohort both

# Cross-section per-CG (default) — writes one TSV per qualifying CG:
uv run python -m bac_complete_genomes.compare_lra_to_sra --mode clonal_group --cohort lra_final_list

# Per-CG virulence-BSC penetrance for every CG over a threshold:
uv run python -m bac_complete_genomes.per_clonal_group.cg_virulence_penetrance_all
```

## Week of 2026-05-30 — assigned workstream item (C2 plot extension)

Anchor: program plan `~/.claude/PROGRAM_PLAN_2026-05-30.md` — Workstream C,
part C2. Branch: `task-ariba-rescue` (shared with bac_ariba).

Extend **`paired_lra_vs_sra/plot_penetrance_ratio.py`** with a third bar
per category: **SR-baseline / SR+ARIBA / LR-truth**. Today the plot shows
per-feature `lr_sr_sensitivity_ratio` with 95% delta-method CIs as a
horizontal bar; the extension adds the ARIBA-rescued SR rate alongside,
so the visual question is "does ARIBA close the gap?" for both Kleborate
virulence loci and acquired AMR.

Inputs:
- Existing `lra_vs_sr_kleborate__<cohort>.tsv` (LR + SR penetrance per
  category, current schema).
- New per-category SR+ARIBA penetrance from
  `<RDS>/processed/mag_rescue/<db>/lra_paired/<cohort>/` (output of
  Workstream C2 in `bac_ariba`).

Schema change: add `sr_plus_ariba_per_genome_sensitivity` (+ its 95% CI
via the same delta-method math as `lr_sr_sensitivity_ratio` so the
comparison is fair) to the wide-row schema. `compare_lra_to_sra.py`'s
wide-row builder may need to learn the new column for downstream
consumers — minimal change; per-arm sensitivity math is unchanged.
