"""bac_genomad: geNomad plasmid/provirus calls across the KpSC assembly set.

Flat subpackage that runs `geNomad <https://portal.nersc.gov/genomad/>`_ over
every long-read (LRA) and short-read (SR) Klebsiella assembly listed in
``metadata_v2``. Three-phase prepare → worker (Slurm array) → collate pattern
mirroring :mod:`bac_isescan.run_isescan_lra`; runs in a dedicated bioconda
pixi env (``src/bac_genomad/pixi.toml``).
"""
