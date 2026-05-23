"""Small shared helpers for ISEScan analysis scripts."""

from __future__ import annotations

import pandas as pd


def is_missing_value(rel: object) -> bool:
    """Return True if ``rel`` is missing — None, ``pd.NA``, NaN, or an empty string."""
    if rel is None or rel is pd.NA:
        return True
    if isinstance(rel, bool):
        return False
    try:
        if rel != rel:
            return True
    except TypeError:
        pass
    return str(rel).strip() == ""


def parse_bool(series: pd.Series) -> pd.Series:
    """Coerce typical TSV booleans/strings to boolean."""

    def _one(v: object) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        if isinstance(v, float) and v != v:
            return False
        s = str(v).strip().lower()
        return s in ("true", "1", "t", "yes", "y")

    return series.map(_one).astype(bool)
