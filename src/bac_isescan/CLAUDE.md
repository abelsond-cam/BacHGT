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

Flat package — each module is a standalone CLI. Most run in the monorepo's
shared `uv` env; `annotate_kleborate_isescan.py` is the exception — it needs
bioconda tools (Kleborate + ISEScan binaries), so it runs in this
subpackage's own pixi env (`src/bac_isescan/pixi.toml`); see **Genome
annotation (bioconda pixi env)** below.

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
| `annotate_kleborate_isescan.py` | Batch-run Kleborate + ISEScan over staged genome sets (`sr`/`gca`/`gcf`) for the SR-vs-complete discrepancy analysis; **bioconda pixi env**, see below |
| `run_isescan_lra.py` | **Phase G.2 ISEScan runner over the LRA cohort** (`metadata_v2.lra_final_list=True`). `prepare`/`worker`/`collate` subcommands, Slurm array, resumable per-sample sentinels. Uses the same pixi env as `annotate_kleborate_isescan.py` |

## Genome annotation (bioconda pixi env)

`annotate_kleborate_isescan.py` is the upstream batch annotator that produces
the ISEScan / Kleborate result trees the rest of this subpackage consumes. It
runs over the locally-staged related-LR genome sets that `bac_data` downloads
(`sr_originals/`, `assemblies/GCA_*`, `assemblies/GCF_*`) and emits:

- `kleborate/<group>__<module>.txt` — Kleborate per-module tables (KpSC
  typing: species, ST, virulence loci, K/O loci, AMR), concatenated per set.
- `isescan/<group>/<key>/...` — per-genome ISEScan result trees.
- `isescan/<group>_isescan.tsv` — concatenated IS calls, sample-tagged.
- `annotation_manifest.tsv` — per-(group, key, tool) status.

Resumable: per-key sentinel files skip already-completed work.

Because Kleborate + ISEScan need bioconda binaries (plus their blast / hmmer
deps), this module is the only one in `bac_isescan` that doesn't run in the
shared uv env. It uses a local pixi env at `src/bac_isescan/pixi.toml`:

```bash
cd src/bac_isescan
pixi install                                 # first run only
pixi run annotate --help
pixi run annotate --groups sr --limit 3      # smoke-test
pixi run annotate --groups sr,gca,gcf --tools kleborate,isescan
```

The pixi env pins `osx-64` for Apple Silicon (runs under Rosetta 2) and
`linux-64` for HPC reproducibility. Upstream of the analysis modules in this
subpackage — its outputs feed the per-sample IS-family counter
(`isescan_family_copy_per_sample.py`), the gene-context mapper
(`isescan_gene_context.py`), and downstream the lineage hotspots.

## Cross-package dependency

`isescan_family_heatmap_analysis.py` imports the clonal-group selection helper
`bac_panaroo.gpa_analysis.define_epidemic_cgs` (kept in `bac_panaroo`; shared with
`bac_complete_genomes`). Works because the monorepo shares one uv environment.

The two lineage-hotspot modules + `_lineage_hotspot_common.py` left-join
Kleborate annotations from `bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap`'s
output (`<panaroo_run>/<lineage>_panaroo_nodes_annotate_kleborate.tsv`), which
in turn consumes the vendored references in `bac_kleborate`.

`isescan_family_copy_per_sample.py` runs on Slurm via
`src/bac_isescan/slurm_scripts/isescan_n_per_sample.sh`.

## Week of 2026-05-30 — assigned workstream (D)

Anchor: program plan `~/.claude/PROGRAM_PLAN_2026-05-30.md` — Workstream D.
Branch: `task-pangenome-IS-distance`.

Goal: quantify how much of the accessory genome is explained by IS
proximity / contig-edge effects. This is the **reverse** of the existing
IS → Panaroo hotspot mapping (`isescan_lineage_panaroo_hotspots.py`):
instead of "which clusters are recurrently flanked by IS", we want "per
Panaroo cluster, what's the distribution of distance-to-nearest-IS and
distance-to-nearest-contig-end across its carriers?"

- **D1 — per-node IS-proximity table.** New script:
  `pangenome_node_is_proximity.py`. For each Panaroo cluster in a lineage,
  loop over carrier genomes; from `is_gene_context.tsv.gz`, look up nearest
  upstream/downstream IS distance (`upstream_distance_bp`,
  `downstream_distance_bp`); from the per-genome GFF, look up distance to
  nearest contig end. Aggregate per cluster: median + IQR of min-IS-
  distance, median + IQR of contig-end distance, fraction within 2 kb /
  5 kb of IS, `is_core` (carrier fraction ≥ 0.95). Output:
  `<panaroo_run>/per_cluster_is_and_contig_proximity.tsv`. Reuse
  `_lineage_hotspot_common.py`'s `_build_index()` (sample|locus_tag →
  cluster) and `_filter_is_rows()` — both are exactly the lookups needed.
  **Contig-length lookup is new** — confirm contig length is available in
  the GFF or pull from the assembly FASTA (cache per genome).
- **D2 — accessory-genome explanation report.** New script:
  `accessory_is_explanation.py`. Split clusters into core (carrier fraction
  ≥ 0.95) vs accessory. For accessory, report: fraction within 2 kb of an
  IS in ≥ 50% of carriers; fraction within 10 kb of a contig end. Compare
  to core baselines. Deliverable:
  `docs/accessory_is_explanation_<lineage>.md` with the headline
  percentages + two plots (distance-to-IS histogram and distance-to-
  contig-end histogram, core vs accessory overlay).

Feeds back into **A5 (BacPredict iso-source explainability)**: top
importance genes that ALSO sit close to IS / contig edges are more likely
to be assembly-artefact signals than biological signals — useful filter
when interpreting the per-gene importance ranks.
