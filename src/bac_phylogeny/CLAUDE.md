# CLAUDE.md — bac_phylogeny

The `bac_phylogeny` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for the
monorepo and `~/.claude/CLAUDE.md` for global guidance.

> **Read first:** [`HANDOVER.md`](HANDOVER.md) — the task brief and the BacPredict reference
> implementations this package copy-adapts.

## Purpose

Build the **variant-call (SNP) structure** side of a population-structure comparison and pit
it against the **HGT / gene-content (Panaroo GPA)** structure that `bac_panaroo` already
produces. The scientific question: is **Clonal Group** a biologically meaningful subdivision
of a *Klebsiella* Sublineage — does it fall out of variant-call structure as cleanly as it
does out of gene content?

The comparison is run **per existing SL-level GPA run** (the unit is the Panaroo run dir,
including the random `SL147_part_0` / `_part_1` splits). The variant analysis uses the **exact
same sample set** as each GPA run, so the two embeddings are directly comparable.

## Data layout (HPC)

The Panaroo GPA runs and their layout are documented in
[`../bac_panaroo/docs/panaroo_run_inventory.md`](../bac_panaroo/docs/panaroo_run_inventory.md)
— read it first. Concretely (all under `project_k/david` = `…/rds-floto-bacterial-4k08a2yyQLw/david`):

| What | Path |
|---|---|
| Panaroo GPA runs (input) | `processed/panaroo_with_reference_genome/` — `SL*` (per-Sublineage, incl. `_part_N`), plus `kp_rare_*` + `species_*` (not used here). Each run has `gene_presence_absence.csv`, `panaroo_genomes.tsv`, `analysis/GPA_reference_genome/`. |
| Shared reference (reused) | `processed/pyseer_iso_source/ref/ref.fa` (NC_009648, faidx'd) |
| Shared per-sample locus cache (reused, extract-once) | `processed/pyseer_iso_source/locus_cache/` (`<Sample>.loci.tsv.gz`) |
| **This subproject's outputs** | `processed/phylogeny_variant_structure/` — `groups/`, `snippy_resolution.tsv`, `variant_umap/`, `comparison/` |
| Metadata | `final/metadata_v2_all_samples_and_columns.tsv` (`Sample`, `Clonal group`, `Sublineage`, `kpsc_final_list`) |

The reference + per-sample locus cache are **shared and cohort-agnostic** (built once, grown
incrementally): the SLURM scripts reuse them so only SL-run samples not already cached are
re-extracted. Only the resolution TSV, group tables, variant matrices, UMAPs, and comparison
outputs are written under this subproject's `phylogeny_variant_structure/` tree.

## Layout

| Module | Purpose |
|---|---|
| `resolve_snippy_paths.py` | Map each metadata `Sample` → its snippy raw VCF (one filesystem pass; `--all-kpsc` or `--sample-csv`). Copy-adapted from BacPredict. |
| `extract_sample_loci.py` | Per-sample bcftools re-filter (`GT=1/1 && QUAL≥100 && DP≥3` → norm → snps,indels) → idempotent `<Sample>.loci.tsv.gz` cache. Copy-adapted. |
| `build_variant_matrix.py` | Reduce the cache to a frequency-filtered binary sparse CSR (`--sparse-only`: saves `.npz`, never densifies). Copy-adapted from BacPredict's `build_presence_and_distances.py`. |
| `gpa_run_groups.py` | Enumerate the SL-level GPA run dirs + read each `panaroo_genomes.tsv` → group→samples + CG-composition annotations. |
| `sublineage_variant_umap.py` | Per group: rebuild the within-group variant matrix from the cache and run the GPA-matched scanpy `neighbors(metric="jaccard")` → `umap` → `leiden(0.3)` → merge; persist coords + labels + plots. |
| `compare_variant_vs_gpa.py` | Join the variant and GPA per-sample labels; compute ARI / AMI / kNN-purity of Clonal Group per modality; emit the paired recovery TSV + side-by-side plots. |
| `slurm_scripts/` | HPC wrappers: `setup_and_resolve.sh`, `extract_variants_array.sh`, `sublineage_variant_umap_array.sh`. |

## Method-matching to `bac_panaroo`

To keep the variant and GPA clusterings comparable, `sublineage_variant_umap.py` **imports**
(same monorepo, same uv env) the GPA clustering helpers rather than re-implementing them:

```python
from bac_panaroo.gpa_analysis.gpa_distances_single_group import _compute_k, _merge_small_clusters
```

It mirrors the GPA path exactly: `sc.pp.neighbors(n_neighbors=_compute_k(n), metric="jaccard",
use_rep="X")` (with the same dense-sklearn fallback) → `sc.tl.umap` →
`sc.tl.leiden(resolution=0.3)` → `_merge_small_clusters(..., max(10, int(0.01*n)))`.

The GPA side persists its per-sample UMAP coords + Leiden labels via a `--persist-embedding`
flag added to `bac_panaroo/gpa_analysis/gpa_distances_single_group.py` (off by default).

## Within-group vs global loci

`build_variant_matrix.py` can build the full all-KPSC matrix (deferred — expensive himem
reduce), but the **per-group** analysis rebuilds its matrix from the shared per-sample cache
with a **within-group** frequency filter. This is deliberate: a 50-sample Clonal Group is
<0.1 % of a large Sublineage, so a global frequency cap would drop exactly the CG-defining
variants the comparison tests. Slicing a global matrix would lose them; rebuilding per group
preserves them and is cheap (each group is a few-k samples).

## Running (HPC, staged)

```bash
cd src/bac_phylogeny && pixi install          # once — provides bcftools + samtools
sbatch src/bac_phylogeny/slurm_scripts/setup_and_resolve.sh          # groups + resolve (subset-first)
sbatch src/bac_phylogeny/slurm_scripts/extract_variants_array.sh     # fill the shared cache (skip-existing)
# (one-time) persist the GPA side for the SL runs:
#   uv run python src/bac_panaroo/gpa_analysis/gpa_distances_single_group.py \
#       --directory-leaf SL101 --persist-embedding true --skip-jaccard true
sbatch src/bac_phylogeny/slurm_scripts/sublineage_variant_umap_array.sh   # per-group variant UMAP+Leiden
uv run python src/bac_phylogeny/compare_variant_vs_gpa.py \
    --groups-tsv  <WORK>/groups/groups.tsv \
    --variant-dir <WORK>/variant_umap \
    --out-dir     <WORK>/comparison
```

`<WORK>` = `processed/phylogeny_variant_structure` (see the table above). Edit the knobs at the
top of `slurm_scripts/*.sh`, then `sbatch`. **bcftools comes from a
pixi env, never `module load`** (the spack module leaks python-3.9 onto PYTHONPATH and breaks
uv's numpy). Triple time estimates; be generous on mem/cpus. Code at
`/home/dca36/workspace/BacHGT`; data under `project_k/david` (see `~/.claude/hpc_storage_overview.md`).

## Code style

Line length 120; numpy docstrings; ruff (B, BLE, C4, D, E, F, I, RUF100, TID, UP, W). Plots:
`matplotlib.use("Agg")`, dpi=150, `tight_layout`, `savefig(bbox_inches="tight")`. Name scripts
and outputs for the **action**, not a plan step.
