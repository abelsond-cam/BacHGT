"""bac_complete_genomes.per_clonal_group: per-CG cross-section comparison of complete-genome vs short-read cohorts.

Drivers for the per-clonal-group complete-vs-MAG comparison (Kleborate virulence,
chromosomal MLST, acquired AMR, ISEScan IS families). Each row of the output
tables corresponds to a feature × CG pair; the means are pooled across
*different samples* within each cohort. For the **paired**-sample SR-vs-LRA
comparison (same biosample sequenced both ways), see the sibling subfolder
``bac_complete_genomes/paired_lra_vs_sra/``.
"""
