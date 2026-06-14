"""Path-resolution helper for metadata_v2 file-path columns.

v2's ``sr_assembly_file`` / ``sr_gff_file`` / ``lr_assembly_file`` / ``lr_gff_file``
are stored as **paths relative to the project_k root** so consumers can supply
their own root prefix (local mount vs HPC mount vs container mount). The root
defaults to the HPC RDS location.

This module provides a single function ``resolve_v2_path`` that:

- Returns ``None`` for empty/NaN/missing values.
- Returns the path as-is if it's already absolute (back-compat with v2 TSVs
  produced before the path-relative rewrite — they have absolute paths).
- Prepends the project_k root for relative paths (the new format).

The root can be overridden by environment variable ``BACHGT_PROJECT_K_ROOT``
or passed explicitly as the ``root`` argument.

Usage::

    from bac_metadata.path_resolve import resolve_v2_path

    asm = resolve_v2_path(row["lr_assembly_file"])
    if asm and asm.is_file():
        process(asm)
"""

from __future__ import annotations

import os
from pathlib import Path

# Default project_k root on the HPC. Override via env var or CLI arg in code
# that runs on a local mount or in a container.
DEFAULT_PROJECT_K_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")

# Per-user data subdirectory under the project_k root. On the HPC RDS this is
# ``david``; the local OneDrive mirror of Aaron's share names it ``data`` instead.
# Override via env ``BACHGT_PROJECT_K_USER`` (e.g. ``data`` for a local run).
DEFAULT_PROJECT_K_USER = "david"


def project_k_root(root: str | Path | None = None) -> Path:
    """Return the project_k root: explicit arg → env var → DEFAULT.

    Resolution order:
      1. ``root`` argument (if given).
      2. ``BACHGT_PROJECT_K_ROOT`` environment variable.
      3. ``DEFAULT_PROJECT_K_ROOT`` (the HPC RDS path).
    """
    if root is not None:
        return Path(root)
    env = os.environ.get("BACHGT_PROJECT_K_ROOT")
    if env:
        return Path(env)
    return DEFAULT_PROJECT_K_ROOT


def project_k_user_dir(root: str | Path | None = None, user: str | None = None) -> Path:
    """Return the per-user data dir under project_k (``<root>/<user>``).

    The collation/QC scripts read inputs and write outputs beneath this directory,
    so wiring their path constants through here lets the *same command* run on the
    HPC and on a local mirror by setting environment variables only.

    Resolution:
      * root — see :func:`project_k_root` (``BACHGT_PROJECT_K_ROOT``).
      * user — ``user`` arg → env ``BACHGT_PROJECT_K_USER`` → ``"david"`` (HPC default).

    HPC needs no configuration. A local run sets both ``BACHGT_PROJECT_K_ROOT``
    (the OneDrive ``…/project_k`` dir) and ``BACHGT_PROJECT_K_USER=data``.
    """
    if user is None:
        user = os.environ.get("BACHGT_PROJECT_K_USER", DEFAULT_PROJECT_K_USER)
    return project_k_root(root) / user


def resolve_v2_path(value: object, root: str | Path | None = None) -> Path | None:
    """Resolve a v2 path-column value to an absolute :class:`Path`.

    - ``None`` / NaN-like / empty string → ``None``.
    - Absolute path (starts with ``/``) → returned unchanged (back-compat with
      pre-rewrite v2 TSVs).
    - Relative path → prepended with ``project_k_root(root)``.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s in {"", "nan", "<NA>", "None"}:
        return None
    p = Path(s)
    if p.is_absolute():
        return p
    return project_k_root(root) / p


def to_relative_v2_path(absolute: str | Path, root: str | Path | None = None) -> str:
    """Strip the project_k root from an absolute path for storage in v2.

    Used by ``add_paths_gff_fna_to_metadata.py`` when writing path columns.
    If the absolute path does not live under ``root``, it is returned as-is
    (so paths outside project_k stay absolute and remain openable directly).
    """
    p = Path(str(absolute))
    if not p.is_absolute():
        return str(p)
    base = project_k_root(root)
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)
