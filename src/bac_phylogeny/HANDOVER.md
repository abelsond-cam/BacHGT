# Handover — variant-call structure vs Clonal Group (bac_phylogeny side project)

## Task

Adapt BacPredict's `build_presence_and_distances.build_presence_matrix` (sparse) +
`qc_distance_umap` to:

1. Extract the **>0.1%-frequency variant matrix for all KPSC samples** (not just the
   blood/faeces cohort), and **save it sparse-compressed** (it will be huge).
2. For each **Sublineage with >1000 samples and >1 large (>50-sample) Clonal Group**,
   **UMAP the Jaccard structure** (use `metric="jaccard"` on the sparse matrix, or
   subsample-then-dense) and compare **KNN clustering against the Panaroo-GPA UMAPs**.

**Goal:** test whether *Clonal Group* is a biologically meaningful subdivision of
*Klebsiella* under variant-call structure vs HGT / gene-content (Panaroo GPA) structure.

> **Frequency-cap fallback.** Start at **>0.1%** (`--min-freq 0.001`). If that explodes
> the matrix beyond what stays tractable (locus count / sparse-save size / UMAP NN build),
> **fall back to 1%** (`--min-freq 0.01`) and run the analysis on that — the conclusion
> about Clonal-Group structure does not hinge on the rarest variants.

## Reference implementations (BacPredict — import-or-adapt)

All live in **BacPredict** at `~/developer/BacPredict/src/bac_pyseer/kleb_iso_source/`.
You are working in **BacHGT/`bac_phylogeny`** — separate repo, separate uv env — so treat
these as reference implementations to **copy/adapt**, not import across repos. The reusable
logic is pure `numpy`/`scipy`/`pandas`/`umap`, so lifting the functions over is clean.

### 1. Variant matrix — 3-stage pipeline (resolve → extract-per-sample → reduce)

| Stage | Module | SLURM wrapper | What it does |
|---|---|---|---|
| Resolve | `resolve_snippy_paths.py` | `scripts/setup_and_resolve.sh` | Maps each sample → its snippy `snps.raw.vcf.gz` path |
| Extract | `extract_sample_loci.py` | `scripts/extract_variants_array.sh` | bcftools filter (`GT=1/1 && QUAL≥100 && DP≥3`) → per-sample `<Sample>.loci.tsv.gz` cache (extract-once, shared) |
| **Reduce** | **`build_presence_and_distances.py`** | `scripts/build_matrix_and_distances.sh` | The core: samples×loci presence matrix + Jaccard distances + frequency filter |

Key importable functions in `build_presence_and_distances.py`:
- `build_presence_matrix(paths, n_jobs) -> (csr_matrix, locus_keys)` — **already returns a
  sparse CSR** (samples × loci, binary). This is exactly what to save sparsely.
- `jaccard_distance_matrix(x_csr) -> dense ndarray` — vectorised `X·Xᵀ` sparse-matmul
  Jaccard (bit-identical to scipy, no per-pair loop, no densify of the *feature* matrix).
- `parse_positions(keys)`, `_read_locus_keys(path)`, `_present_samples(samples, cache_dir)`.

> **Reuse the per-sample cache — don't re-extract.** Stages 1–2 (resolve + extract) have
> already produced the shared `<Sample>.loci.tsv.gz` cache for the blood/faeces cohort. For
> all-KPSC you only need to (a) extend the cohort sample list to all KPSC samples and run
> *extract* for any not yet cached, then (b) run your adapted *reduce*. The cache is the
> expensive part and is shared across cohorts by design.

### 2. UMAP of Jaccard distances by sublineage

`qc_distance_umap.py` (run via `scripts/run_qc.sh`). Importable:
- `bucket_sublineages(sl_per_sample, top_n) -> (labels, top_cats)` — collapses all but the
  top-N SLs into `"rare SL"`. Directly reusable for the ">1000-sample SLs" cut.
- `run_umap(distances, n_neighbors, seed)` — UMAP with `metric="precomputed"` (see caveat 2).
- `plot_umap_by_sublineage(...)`, `plot_umap_by_phenotype(...)` — tab10 + grey-rare conventions.

Frequency-spectrum QC, if useful: `qc_variant_spectrum.py` — `spectrum_from_rtab`,
`frequency_bands`.

## Three scaling caveats at all-sample (~80k) scale

These pipelines were sized for the **14k** blood/faeces cohort. Two of the reduce's output
steps **do not scale** to 80k and must be changed:

1. **Don't write a dense Rtab.** `run()` densifies via `xf.T.toarray()` to emit the pyseer
   Rtab — at 80k × ~1–2M loci that's catastrophic. You don't need a pyseer Rtab; **save
   `xf` directly with `scipy.sparse.save_npz`** (+ the locus-key array, e.g.
   `np.savez_compressed` of `locus_keys`). Bypass the Rtab/phenotype/manifest block, or
   refactor `run()` to a `--sparse-only` path.

2. **Don't build the dense n×n Jaccard for the all-sample UMAP.** `jaccard_distance_matrix`
   returns a dense `n×n` — 80k² × 8 B ≈ **51 GB** (the docstring flags Tier-2 as
   out-of-scope / needs blocking). Two good routes:
   - **(a)** feed the sparse binary matrix straight to `umap.UMAP(metric="jaccard")` and let
     pynndescent's approximate-NN handle it (scales to 80k, no dense matrix) — switch
     `run_umap` off `metric="precomputed"`; or
   - **(b)** since the plan **subsamples** the large SLs first, compute the dense Jaccard only
     on each subsample (a few k²) — cheap, and `jaccard_distance_matrix` works as-is there.

3. **The `>0.1%` cap is `--min-freq 0.001`** (`min_count = ceil(0.001 · n_samples)`; ~80 at
   80k). The reduce persists `prefilter_locus_spectrum.npz` (POS + per-locus count,
   pre-filter), so you can **re-threshold (e.g. drop to 1%) without recomputing** the matrix.

**Compute sizing lesson:** the 14k reduce peaked **~63 GB / ~90 min**. At ~80k →
**icelake-himem**, be generous (≥256 GB, ≥6 h). The sparse-save change in caveat 1 is what
keeps it tractable.

## For the comparison goal

- **Panaroo-GPA UMAPs** to compare against live in **BacHGT** (`bac_panaroo`) — you know where;
  do not crawl the data trees to find them.
- **Metadata join** (`Sublineage`, and the **Clonal Group** column for the ">1 large CG per
  SL" filter) comes from `metadata_v2_all_samples_and_columns.tsv`. Authoritative description:
  `~/developer/BacHGT/src/bac_metadata/METADATA_v2_README.md`. (For reference, the
  blood/faeces split CSV used by the source pipeline keys `Sample`, `Sublineage`, so the same
  table carries Clonal Group.)
- **Reporting parallel:** the source project's KNN-UMAP QC showed lineages cluster crisply
  while blood/faeces intermix *within* a lineage — i.e. structure is dominated by SL/CG, with
  finer signal inside. The question here is the converse-facing one: does variant-call
  structure resolve Clonal Group as cleanly as (or differently from) HGT/gene-content does?

## Conventions to keep (from the source repo)

- `matplotlib.use("Agg")`, `dpi=150`, `tight_layout`, `savefig(bbox_inches="tight")`.
- Name scripts/outputs **for the action, not a plan step** (e.g.
  `build_variant_matrix_all_kpsc.sh`, not `step1_*.sh`).
- HPC SLURM: triple time estimates, be generous on mem/cpus (never under-call); tool binaries
  (bcftools) go in a **pixi** env, never `module load` (the spack module leaks python-3.9 onto
  PYTHONPATH and breaks uv's numpy).
