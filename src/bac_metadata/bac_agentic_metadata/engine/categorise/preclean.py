r"""Wipe field-specific null tokens/patterns to blank in-memory, before the fill stages run.

``pp/metadata_curation.py`` wipes per-field placeholder text (e.g. ``0`` / ``unclear`` / ``others``
in ``isolation_source``, ``not host-associated`` in ``host``) — and every ``laboratory`` variant, in
both fields — to NaN. But it does so *after* the base table is built, so inside the agentic pipeline
the fill agent sees those cells as real values and never tries to improve them. The engine's global
:data:`backfill.PLACEHOLDER_NULLS` catches the common tokens; this module handles the field-specific
ones declared per application in ``attributes.yaml`` under ``categorisation.fields.<field>``:

* ``null_tokens`` — whole-cell placeholder strings (``0``, ``unclear``, ``others``, …).
* ``null_patterns`` — case-insensitive regexes matched anywhere in the cell (``\\blaborator`` etc.).
  ``laboratory`` is a tautology (every isolate is lab-grown) — never a real host/source, so all its
  variants are blanked pre-grading so the fill agent gets an honest blank to work from.

The clean is **in-memory only** — the base table on disk stays byte-for-byte verbatim. The blanked
values are returned so the caller can audit exactly what was reclassified as missing.
"""

from __future__ import annotations

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.categorise.value_frequencies import null_mask


def preclean_base(base: pd.DataFrame, spec) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Blank field-specific null tokens/patterns so the fill agent can attempt those cells.

    Parameters
    ----------
    base
        The per-sample base table (string columns; blanks are ``""`` under ``keep_default_na=False``).
    spec
        The :class:`~engine.spec.AttributeSpec`; ``spec.categorisation`` supplies per-field
        ``null_tokens`` / ``null_patterns``. Applications with no ``categorisation`` block are a no-op.

    Returns
    -------
    tuple[pandas.DataFrame, dict[str, dict[str, int]]]
        The (possibly copied) base with matched cells set to ``""``, and a per-field audit
        ``{field: {blanked_value: count, ...}}`` of exactly which values were reclassified as missing
        (only fields with a non-zero count appear).
    """
    cat = getattr(spec, "categorisation", None) or {}
    audit: dict[str, dict[str, int]] = {}
    out = base
    for field, cfg in cat.items():
        cfg = cfg or {}
        tokens = tuple(cfg.get("null_tokens") or ())
        patterns = tuple(cfg.get("null_patterns") or ())
        if (not tokens and not patterns) or field not in out.columns:
            continue
        mask = null_mask(out[field], null_tokens=tokens, null_patterns=patterns)
        n = int(mask.sum())
        if n:
            audit[field] = out.loc[mask, field].value_counts().astype(int).to_dict()
            if out is base:
                out = base.copy()
            out.loc[mask, field] = ""
    return out, audit
