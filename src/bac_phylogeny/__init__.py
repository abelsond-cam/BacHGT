"""Variant-call (SNP) population structure vs Clonal Group, paired against Panaroo GPA.

This subpackage builds the **variant-call** side of a structure comparison: per-sample
snippy SNP/indel calls are reduced to a binary samples × loci presence matrix, embedded
with the same scanpy Jaccard-UMAP-Leiden machinery the ``bac_panaroo`` GPA pipeline uses,
and the resulting clustering is compared head-to-head against the gene-content (HGT) GPA
clustering. The question: does **Clonal Group** fall out of variant-call structure as
cleanly as it does out of HGT / gene-content (Panaroo GPA) structure?

Pipeline (one module per stage):

- ``resolve_snippy_paths`` — map each metadata ``Sample`` to its snippy raw VCF.
- ``extract_sample_loci`` — per-sample bcftools re-filter → idempotent ``<Sample>.loci.tsv.gz`` cache.
- ``build_variant_matrix`` — reduce the cache to a frequency-filtered sparse CSR presence matrix.
- ``gpa_run_groups`` — derive the comparison groups (and their sample sets) from the existing
  SL-level Panaroo GPA runs.
- ``sublineage_variant_umap`` — per group: build the within-group variant matrix and run the
  GPA-matched scanpy neighbors/UMAP/Leiden; persist coords + labels.
- ``compare_variant_vs_gpa`` — join the variant and GPA runs and quantify Clonal-Group
  recovery (ARI / AMI / kNN label-purity) per modality.

The variant-matrix and UMAP logic is copy-adapted from BacPredict
(``bac_pyseer/kleb_iso_source``); the clustering helpers are imported from ``bac_panaroo``
so the two modalities stay method-matched. See ``HANDOVER.md`` and ``CLAUDE.md``.
"""
