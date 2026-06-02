"""bac_data.lr_data — long-read genome discovery, audit, download, LRA selection.

Subpackage of bac_data. Houses everything related to discovering and qualifying
long-read assemblies (LR-GCAs and is_refseq RefSeq genomes) that form the LRA
("long-read assembly") cohort. The CheckM2 scoring step lives in the sibling
``bac_data.checkm2`` subpackage so the env + Slurm wrapper stay cohort-agnostic.
"""
