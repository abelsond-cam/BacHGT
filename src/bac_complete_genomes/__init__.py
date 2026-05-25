"""bac_complete_genomes: complete-genome vs short-read cohort comparison for BacHGT.

Two comparison modes share the same Kleborate / ISEScan parsing logic:

- :mod:`bac_complete_genomes.per_clonal_group` — cross-section: complete-genome
  cohort (``lra_final_set=True``) vs short-read cohort, **different samples in
  each arm**, per clonal group. Reports p-value-sorted enrichment / penetrance
  tables and the BSC heatmaps.

- :mod:`bac_complete_genomes.paired_lra_vs_sra` — paired: same ~2,500-3,000
  biosamples in both arms (SR-Kleborate frozen in ``sr_shadow_for_lra.tsv``,
  LR-Kleborate in ``metadata_v2``). McNemar's + Wilcoxon for the upgraded
  per-feature stats. Headline: LR-pickup rate per Kleborate call.

The shared library functions (Kleborate virulence schema, presence/absence
parsers, ISEScan loaders, acquired-token counter) live in
:mod:`bac_complete_genomes.compare_lra_to_sra`. Both comparison modes are
exposed via that module's ``--mode {clonal_group, paired}`` CLI flag.
"""
