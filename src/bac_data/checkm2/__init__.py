"""bac_data.checkm2 — uniform CheckM2 scoring of assembly cohorts.

Sibling subpackage of `bac_data.lr_data`. Holds the dedicated `pixi` env
(CheckM2 is bioconda-only — kept out of the shared uv env) plus the input
manifest builder + Slurm wrapper. The first caller is the LRA cohort
(LR-GCAs + is_refseq); future cohorts add a sibling prep script.
"""
