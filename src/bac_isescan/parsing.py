"""ISEScan IS-family parsing primitives.

Single source of truth for discovering IS-family columns (``IS_<family>``) on a
``metadata_v2``-style frame and converting them to per-sample copy counts / 0-1
presence. Lifted out of ``bac_complete_genomes.compare_lra_to_sra`` so the
existing analysis driver and any future consumers (linear baselines, hotspot
analyses) share one implementation.

The selection rule (``startswith("IS_")``) matches IS-family copy columns
emitted by upstream ISEScan annotation while excluding the lower-case
``is_<flag>`` booleans (``is_complete``, ``is_reference_genome``, …) and the
``sr_IS_*`` SR-shadow shadow columns.
"""

from __future__ import annotations

import pandas as pd


def is_family_columns(columns) -> list[str]:
    """Return ``IS_<family>`` copy-count column names from an iterable of columns (sorted)."""
    return sorted(c for c in columns if str(c).startswith("IS_"))


def is_family_copies(meta_df: pd.DataFrame) -> pd.DataFrame:
    """Per-sample integer copy-count DataFrame for every IS family found in ``meta_df``.

    Non-numeric cells are coerced to NaN and filled with 0 — i.e. "missing" is
    treated as "no copies", matching the convention used by the paired-LR/SR
    comparison driver.
    """
    cols = is_family_columns(meta_df.columns)
    out = {c: pd.to_numeric(meta_df[c], errors="coerce").fillna(0) for c in cols}
    return pd.DataFrame(out, index=meta_df.index)


def is_family_presence(meta_df: pd.DataFrame) -> pd.DataFrame:
    """Per-sample 0/1 DataFrame for every IS family found in ``meta_df``.

    Presence = ``copies > 0`` after the :func:`is_family_copies` coercion.
    """
    return (is_family_copies(meta_df) > 0).astype(float)
