from importlib.metadata import version

from . import annotate_nodes, gpa_analysis, run_panaroo

__all__ = ["annotate_nodes", "gpa_analysis", "run_panaroo"]

__version__ = version("BacHGT")
