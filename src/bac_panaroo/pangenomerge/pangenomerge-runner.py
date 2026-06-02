#!/usr/bin/env python
"""Convenience wrapper for running pangenomerge directly from its source tree.

Context: on HPC the ``pangenomerge`` micromamba env contains **only runtime deps**
(mmseqs2, biopython, networkx, …). The pangenomerge package itself is imported
from the source checkout at ``~/workspace/pangenome_merge`` via ``PYTHONPATH``
set by the sbatch wrappers in ``src/bac_panaroo/slurm_scripts/``. This runner is
the canonical entry-point those wrappers invoke (no ``pip install`` step is
needed). Copy of ``~/workspace/pangenome_merge/pangenomerge-runner.py`` (preserved
in the monorepo so the upstream-dev branch reset doesn't drop it).
"""

from pangenomerge.__main__ import main

if __name__ == "__main__":
    main()
