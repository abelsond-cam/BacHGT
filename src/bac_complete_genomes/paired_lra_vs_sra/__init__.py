"""bac_complete_genomes.paired_lra_vs_sra: same-biosample SR-vs-LRA paired comparison.

Holds the notebook + supporting code for the Phase G.4 paired-stats analysis:
the same ~2,500-3,000 biosamples appear in both arms (SR-Kleborate frozen in
``sr_shadow_for_lra.tsv``, LR-Kleborate live in ``metadata_v2``), enabling
McNemar's / Wilcoxon signed-rank tests on the same Kleborate / ISEScan
features the cross-section per-CG analysis covers.

The shared parsers (Kleborate schemas, presence/absence logic, ISEScan
loaders) live one level up in ``compare_lra_to_sra.py``.
"""
