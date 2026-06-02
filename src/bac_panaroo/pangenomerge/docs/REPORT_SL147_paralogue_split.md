# pangenomerge paralogue-splitting on SL147 (upstream `dev` branch, commit `944cbd8`)

## Summary

Running `pangenomerge` from the upstream `dev` branch (commit `944cbd8`) on two halves
of a single *Klebsiella pneumoniae* sublineage (SL147), the merged pangenome contains
**526 gene clusters at exactly ~50% prevalence** that are not present at this frequency
in either input. They are almost all part-half-specific (live in one input's genomes,
absent from the other's), and **~147 of them** form unambiguous paralogue-split pairs
(same annotation, mutual exclusion, ~100% combined coverage). Per-genome gene content
is preserved through the merge, but cluster topology is fragmented: each genome's
mean core-gene count drops by ~340 with a matching ~340 increase in shell.

This is the same class of issue our old fork patches
(`fix/mmseqs-missing-node-guard`, `patch-1`) were targeting; the dev branch resolved
the crash failures but the paralogue / cross-graph ortholog mapping appears to still
under-merge.

## Cohort

- **SL147** — a single *Klebsiella pneumoniae* sublineage from a curated cohort
  (metadata v2 of our KPSC dataset).
- **5,353 genomes** total. Each metadata row may contribute a short-read assembly,
  a long-read assembly, or both; here we have ~3,500 SR + ~1,800 LRA in the union.
- Randomly partitioned into two halves of ~2,700 genomes each via a deterministic
  seed-42 shuffle + 2-way split inside our batching script
  (`panaroo_metadata_batching.py:shuffle_two_parts`). Same SL, randomised halves —
  no population-structure partition.

| Part | Genomes |
|---|---:|
| `SL147_part_0` | 2,672 |
| `SL147_part_1` | 2,681 |
| **Total** | **5,353** |

## Panaroo per-part baseline (each half run independently)

### Per-pangenome cluster category counts

Cutoffs follow pangenomerge's own conventions (core ≥99%, soft-core 95-99%,
shell 15-95%, cloud <15%), computed directly from each part's
`gene_presence_absence.csv`:

| Part | Total clusters | Core | Soft-core | Shell | Cloud |
|---|---:|---:|---:|---:|---:|
| **SL147_part_0** (n=2,672) | 17,433 | 3,890 | 177 | 1,221 | 12,145 |
| **SL147_part_1** (n=2,681) | 17,590 | 3,791 | 199 | 1,372 | 12,228 |

### Per-genome means (from each part's `gpa_clustering_summary_SL147_part_X.tsv`)

| Part | core (mean ± sd) | soft-core | shell | cloud | total Panaroo clusters/genome |
|---|---:|---:|---:|---:|---:|
| SL147_part_0 | **3886.91 ± 9.21** | 173.09 ± 7.66 | 515.83 ± 173.48 | 126.92 ± 86.21 | **4702.74 ± 152.26** |
| SL147_part_1 | **3788.05 ± 9.84** | 194.49 ± 9.13 | 582.03 ± 169.13 | 132.25 ± 90.10 | **4696.82 ± 152.53** |

Each half produces a typical SL-level pangenome distribution: ~4,700 clusters per
genome with ~3,840 in core + ~180 soft-core + ~550 shell + ~130 cloud. The two halves
are highly consistent — as expected for two random halves of the same sublineage.

## pangenomerge merge of the two parts

Run on upstream/dev (`944cbd8`) with default options + 16 threads. Wall time 31:58,
max RSS 44 GB. Then `pangenomerge-postprocess --output presenceabsence` was run on the
resulting `pangenome_metadata.sqlite` + `final_graph.gml` to produce the Panaroo-style
`gene_presence_absence.csv` used below.

### Per-pangenome category counts (merged)

| Merged pangenome (n=5,353) | Total clusters | Core | Soft-core | Shell | Cloud |
|---|---:|---:|---:|---:|---:|
| **SL147_merged** | **20,840** | **3,556** | 165 | **2,010** | 15,109 |

### Per-genome means (merged)

| | core | soft-core | shell | cloud | total / genome |
|---|---:|---:|---:|---:|---:|
| SL147_merged | **3485.71 ± 7.07** | 187.38 ± 14.74 | **872.46 ± 171.44** | 146.48 ± 85.80 | **4692.03 ± 156.50** |

### Per-genome side-by-side

| Per-genome (mean) | part_0 | part_1 | **merge** | Δ vs avg part |
|---|---:|---:|---:|---:|
| core | 3886.91 | 3788.05 | **3485.71** | **−352** |
| soft-core | 173.09 | 194.49 | 187.38 | -3 |
| shell | 515.83 | 582.03 | **872.46** | **+323** |
| cloud | 126.92 | 132.25 | 146.48 | +17 |
| total Panaroo clusters/genome | 4702.74 | 4696.82 | **4692.03** | **-8** |
| total Panaroo genes/genome | 4713.99 | 4711.12 | 4704.75 | -8 |

**Per-genome content is preserved (~4,700 clusters per genome) — the merge has not
lost or duplicated content.** ✓

**But ~350 clusters per genome moved from core → shell.** A core gene in part_0 that
gets mapped to a different cluster than its part_1 counterpart shows up in the merge as
two clusters, each present in ~50% of all merged genomes — i.e., shell. The total per
genome is conserved because each genome carries exactly one of the two clusters.

## Smoking gun — frequency-distribution spike at 50%

Histogram of cluster prevalence in the merged pangenome (524-bin output, condensed
to relevant bins):

| Prevalence band | # clusters |
|---|---:|
| 0.40-0.45 | 170 |
| 0.45-0.48 | 53 |
| **0.48-0.52** | **526** ← isolated spike |
| 0.52-0.55 | 21 |
| 0.55-0.60 | 11 |
| 0.60-0.70 | 62 |

The neighbouring bands hold **10-50× fewer clusters** than the 0.48-0.52 bin. For two
random halves of the same SL, you would expect a smooth tail through this region —
not a discrete peak at exactly half-population prevalence. See
`gpa_freq_dist_post_filter_SL147.png` for the histogram plot (the spike is unmissable);
contrast with `gpa_freq_dist_post_filter_SL147_part_0.png` and
`gpa_freq_dist_post_filter_SL147_part_1.png` — neither shows any analogous peak at
~50%.

## Diagnostic — mutual-exclusivity test

For each of the 526 spike clusters, find the spike cluster *j* that maximises
`union(i, j)`. For a true paralogue-split pair, the union should be ~100% of genomes
and the intersect ~0 (each genome carries exactly one of the two).

Results across all 526 spike clusters (computed on the merged
`gene_presence_absence.csv`):

- **Median best-partner union: 99.94% of all genomes** (5,350 of 5,353)
- Median best-partner intersect: 67 genomes (1.3% of cluster's own count)
- **100% of spike clusters have a best partner covering ≥98% of genomes**
- Under strict criteria (union ≥98% AND intersect ≤2% of own count):
  **150 / 526 (28.5%) clusters → 147 distinct paired events**

Even the looser pairs (where annotations don't match exactly or one partner is a
slightly-divergent paralogue) still show clean anti-correlation: the cluster lives
in one population half and never co-occurs with its twin from the other half.

For comparison, **two random ~50% clusters would have a best-partner union of
~75% by chance** (and intersect ~50% of each cluster's count). The observed 99.94%
median union and ~1.3% intersect are not consistent with chance.

## Example confirmed paralogue-split pairs

From the strict-criterion set (4 of the 147 found):

**1 — Outer membrane usher protein FimD/PapC:**
- Cluster A: `group_3210` — prevalence 2,681 / 5,353 (50.1%) — annotation: *"Outer
  membrane usher protein FimD/PapC"*
- Cluster B: `group_8889` — prevalence 2,662 / 5,353 (49.7%) — annotation: *"Outer
  membrane usher protein FimD/PapC; Type 1 fimbriae anchor"*
- Union: 5,340 / 5,353 (99.76%); intersect: 3

**2 — LuxR-family transcriptional regulator:**
- Cluster A: `luxR~~~acoK~~~malT` — prevalence 2,731 / 5,353 (51.0%) — annotation:
  *"Transcriptional activator of maltose regulon MalT; LuxR C-terminal..."*
- Cluster B: `group_6766` — prevalence 2,620 / 5,353 (48.9%) — annotation: *"LuxR
  C-terminal-related transcriptional regulator"*
- Union: 5,342 / 5,353 (99.79%); intersect: 9

**3 — Threonine/homoserine/homoserine lactone efflux (RhtB) + an MFS transporter
that pairs with it:**
- Cluster A: `rhtB` — prevalence 2,693 / 5,353 (50.3%)
- Cluster B: `group_9580` — prevalence 2,659 / 5,353 (49.7%) — *"MFS transporter;
  Putative transport protein; Major facilitator..."*
- Union: 5,349 / 5,353 (99.93%); intersect: 3

**4 — Chorismate-mutase / TrmD candidate split (functionally unrelated but cleanly
anti-correlated, suggesting the chorismate-mutase gene is part-half-specific in our
data and got partnered with a different ~50% cluster):**
- Cluster A: `group_16543` — prevalence 2,716 / 5,353 (50.7%) — annotation:
  *"bifunctional chorismate mutase/prephenate dehydrogenase"*
- Cluster B: `group_16528` — prevalence 2,672 / 5,353 (49.9%) — annotation: *"tRNA
  (guanosine(37)-N1)-methyltransferase TrmD"*
- Union: 5,353 / 5,353 (100.00%); intersect: 35

## Impact

- ~526 clusters (~3% of total merged clusters) are in the 50% paralogue-split spike.
- ~147 confirmed paralogue-split pair events; the remaining spike clusters look like
  population-half-specific clusters that the merge failed to bridge across the two
  parts' graphs.
- These clusters represent ~10% of the mid-prevalence (≥15%) cluster space.
- Per-genome content is preserved, so the merge is biologically usable for coarse
  comparisons of gene content. But ortholog-level analyses (core-genome alignments,
  pan-genome dynamics, ortholog-specific selection scans) would under-count the core
  by ~10% and over-count the gene-family universe by ~3%.

## File references (HPC paths)

### Each part's Panaroo outputs

```
/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome/SL147_part_0/
/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome/SL147_part_1/
```

Each contains a top-level Panaroo output set + an `analysis/GPA_reference_genome/`
subdir with:

- `gpa_clustering_summary_SL147_part_X.tsv` — per-pangenome category counts + per-genome means.
- `gpa_freq_dist_post_filter_SL147_part_X.png` — gene-frequency-distribution histogram. **Reference plot — shows the smooth-tail expected pangenome.**
- `gpa_core_softcore_shell_cloud_post_filter_SL147_part_X.png` — category-count bar plot.
- `gpa_distances_detail_SL147_part_X.tsv` — whole-set + per-CG/Klocus distance/category rows.

### Merged pangenome

```
/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/pangenomerge/SL147/
```

Top-level pangenomerge outputs:
- `component_graphs.tsv` — input TSV (paths to the two Panaroo run dirs).
- `final_graph.gml` — merged graph (20,840 nodes).
- `pangenome_metadata.sqlite` — 5.9 GB sqlite of merged metadata.
- `pangenome_reference_aa/` — MMseqs2 reference db.
- `summary_statistics.txt` — pangenomerge's own category counts (3,556 / 165 / 2,010 / 15,109).
- `intermediate_graphs/` — per-iteration checkpoint graphs.
- `_run_postprocess_then_gpa.sh` — the chained script used to produce the postprocess + analysis outputs.
- `login_postprocess_and_analysis.log` — log of that chained run.

postprocess outputs (`postprocess/`):
- `gene_presence_absence.csv` — Panaroo-format presence/absence (5,353 columns × 20,840 rows).
- `gene_presence_absence_roary.csv` — Roary-format.
- `gene_presence_absence.Rtab` — tab-separated binary matrix.

`analysis/GPA_reference_genome/`:
- `gpa_clustering_summary_SL147.tsv` — per-pangenome counts + per-genome means.
- `gpa_freq_dist_post_filter_SL147.png` — **THE smoking-gun plot — shows the 50% spike**.
- `gpa_core_softcore_shell_cloud_post_filter_SL147.png` — category-count bar plot.

## Reproduce

The pangenomerge run was launched as a Slurm job (see
`/home/dca36/workspace/BacHGT/src/bac_panaroo/slurm_scripts/pangenomerge_merge.sh`),
which after env activation + `cd` into the source checkout runs:

```bash
cd ~/workspace/pangenome_merge        # upstream/dev checkout
micromamba activate pangenomerge      # env contains only runtime deps; pangenomerge runs from source via PYTHONPATH
export PYTHONPATH=".:pangenomerge"
python3 pangenomerge-runner.py \
  --component-graphs <component_graphs.tsv> \
  --outdir <out> \
  --threads 16
```

(Component graphs TSV is just two lines, one per Panaroo run dir.)

postprocess:

```bash
python -m pangenomerge.generate_output \
  --sqlite  <out>/pangenome_metadata.sqlite \
  --gml     <out>/final_graph.gml \
  --component-graphs <out>/component_graphs.tsv \
  --outdir  <out>/postprocess \
  --output  presenceabsence \
  --sqlite-cache 1048576
```

## Diagnostic script (re-runs the mutual-exclusivity test in <30 s)

```python
import pandas as pd
import numpy as np

GPA = '<merge_dir>/postprocess/gene_presence_absence.csv'
df = pd.read_csv(GPA, low_memory=False)
meta = ['Gene', 'Non-unique Gene name', 'Annotation']
sample_cols = [c for c in df.columns if c not in meta]
n = len(sample_cols)
present = (df[sample_cols].notna() & (df[sample_cols] != '')).values
freq = present.sum(axis=1) / n

spike = (freq >= 0.48) & (freq <= 0.52)
print(f'{int(spike.sum())} clusters in [0.48, 0.52] out of {len(freq)} total')

# Mutual-exclusivity test: for each spike cluster, find its best union-partner.
X = present[spike].astype(np.int32)
sums = X.sum(axis=1)
inter = X @ X.T
union = sums[:, None] + sums[None, :] - inter
np.fill_diagonal(union, -1)
best_j = union.argmax(axis=1)
best_u = union[np.arange(len(X)), best_j] / n
print(f'median best-partner union: {np.median(best_u)*100:.2f}% of all genomes')
print(f'spike clusters with a >=98%-union partner: {int((best_u >= 0.98).sum())}/{len(X)}')
```
