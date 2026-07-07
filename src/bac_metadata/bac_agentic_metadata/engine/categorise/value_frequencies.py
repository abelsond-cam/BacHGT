"""Distinct informative values + counts per field — the substrate for category induction + apply.

Category work operates on **distinct values, not rows**: a field like ``isolation_source`` has a few
hundred distinct strings across tens of thousands of samples, so inducing/mapping each distinct value
once (then joining back) is cheap, cacheable and deterministic. This module produces that distinct-
value frequency table, applying the same cleaning the pipeline uses (:func:`backfill.strip_placeholders`
plus the per-field ``null_tokens`` from the spec) so induction only ever sees genuinely-informative
values — never placeholder junk.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.backfill import strip_placeholders


def _norm_key(series: pd.Series) -> pd.Series:
    """Lower-case, strip, collapse whitespace — matches ``preclean``/``strip_placeholders``."""
    return series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.lower()


def null_mask(
    series: pd.Series,
    *,
    null_tokens: tuple[str, ...] = (),
    null_patterns: tuple[str, ...] = (),
) -> pd.Series:
    r"""Boolean mask of cells that are field-specific nulls: whole-cell tokens OR regex patterns.

    ``null_tokens`` match a whole cell (normalised, e.g. ``"others"``); ``null_patterns`` are
    case-insensitive regexes matched anywhere in the cell (e.g. ``r"\\blaborator"`` to catch every
    ``laboratory`` variant — a tautology, never a real host/source). Shared by :func:`value_frequencies`
    and :func:`preclean.preclean_base` so induction, cleaning and apply all agree on what is a null.
    """
    key = _norm_key(series)
    mask = key.isin({str(t).strip().lower() for t in null_tokens}) if null_tokens else pd.Series(
        False, index=series.index
    )
    for pat in null_patterns:
        mask = mask | key.str.contains(pat, case=False, na=False, regex=True)
    return mask


def value_frequencies(
    series: pd.Series, *, null_tokens: tuple[str, ...] = (), null_patterns: tuple[str, ...] = ()
) -> pd.Series:
    """Return distinct informative values and their counts, most-frequent first.

    Parameters
    ----------
    series
        The raw field column.
    null_tokens, null_patterns
        Extra field-specific nulls (from ``spec.categorisation.<field>``) dropped in addition to
        :data:`backfill.PLACEHOLDER_NULLS` — whole-cell tokens and case-insensitive regex patterns
        (e.g. laboratory variants). See :func:`null_mask`.

    Returns
    -------
    pandas.Series
        Index = distinct value (verbatim, first-seen casing), value = count; descending by count.
    """
    clean = strip_placeholders(series)
    if null_tokens or null_patterns:
        clean = clean.mask(null_mask(clean, null_tokens=null_tokens, null_patterns=null_patterns), other=pd.NA)
    return clean.dropna().value_counts()


def render_for_prompt(freqs: pd.Series, *, max_values: int | None = None) -> str:
    r"""Render a frequency Series as a compact ``count \t value`` list for an LLM prompt.

    Parameters
    ----------
    freqs
        Output of :func:`value_frequencies`.
    max_values
        If set, keep only the top-``max_values`` rows and append a ``… (+N more, M samples)`` line so
        the model is told what was truncated (never a silent cap).
    """
    total_distinct = len(freqs)
    shown = freqs if max_values is None else freqs.head(max_values)
    lines = [f"{int(c)}\t{v}" for v, c in shown.items()]
    if max_values is not None and total_distinct > max_values:
        dropped = freqs.iloc[max_values:]
        lines.append(f"... (+{total_distinct - max_values} more distinct values, {int(dropped.sum())} samples)")
    return "\n".join(lines)
