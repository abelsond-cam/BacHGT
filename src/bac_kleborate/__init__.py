"""bac_kleborate: vendored Kleborate reference data for the BacHGT ecosystem.

Pure data subpackage — holds the FASTAs and metadata TSVs vendored from
[Kleborate](https://github.com/klebgenomics/Kleborate)'s module data
(virulence + AMR) so that any consumer can point at one canonical location
without re-deriving the reference. Consumers today:

- :mod:`bac_ariba.pp.build_ariba_ref` — reads the vendored FASTAs and runs
  ``ariba prepareref`` on top to produce a built ARIBA DB.
- :mod:`bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap` — minimap2's
  representative Panaroo-cluster sequences against the same FASTAs.

Path constants live in :mod:`bac_kleborate.refs.paths`.
"""
