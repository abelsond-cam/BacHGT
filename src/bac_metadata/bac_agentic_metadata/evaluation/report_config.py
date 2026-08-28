"""App-agnostic reporting config, derived from an :class:`AttributeSpec`'s non-graded ``report:`` block.

The read-only evaluation/summary tools (``wrapup_report``, ``build_per_study_table``,
``completeness_by_split``) were Klebsiella-hardcoded — a module-level ``FIELDS`` 4-tuple, a fixed pair of
study-level columns, fixed tail size-bands, and Klebsiella prose. This helper drives every app-specific choice
off the spec so the SAME tool serves Klebsiella, *M. abscessus*, and any future application unchanged.

Defaults are chosen so that (a) an application that declares no ``report:`` block still produces a sensible
report (display order = the completeness fields; all graded study-level attributes surfaced; no size bands),
and (b) Klebsiella — which declares a ``report:`` block mirroring its historical constants — reproduces its
previous output byte-for-byte. The block is NOT rendered into the grading prompt, so it never busts the grade
cache (see :attr:`AttributeSpec.report`).
"""

from __future__ import annotations

from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

SizeBand = tuple[str, int, "int | None"]


def fields(spec: AttributeSpec) -> tuple[str, ...]:
    """The per-sample completeness fields, in spec order (drives every per-field table)."""
    return tuple(spec.completeness_fields)


def display_fields(spec: AttributeSpec) -> tuple[str, ...]:
    """Field order for the per-field report sections (``report.display_fields``; else completeness order)."""
    d = spec.report.get("display_fields")
    return tuple(d) if d else tuple(spec.completeness_fields)


def _graded_study_level(spec: AttributeSpec) -> list[str]:
    """Names of the graded study-level attributes (dict entries with a ``values`` list), in YAML order."""
    block = (spec.raw.get("attributes", {}) or {}).get("study_level", {}) or {}
    return [k for k, v in block.items() if isinstance(v, dict) and "values" in v]


def study_level_columns(spec: AttributeSpec) -> list[str]:
    """Study-level attribute names to surface as report columns.

    ``report.study_level_columns`` when declared (Klebsiella → ``[study_setting, amr_study]``; m_abs →
    ``[reports_AST, per_sample_AST]``), else every graded study-level attribute in declaration order.
    """
    cfg = spec.report.get("study_level_columns")
    return list(cfg) if cfg is not None else _graded_study_level(spec)


def species_label(spec: AttributeSpec) -> str:
    """Short species label for titles (``report.species_label``; else the taxon-of-interest name)."""
    return spec.report.get("species_label") or spec.taxon_of_interest.name


def size_bands(spec: AttributeSpec) -> list[SizeBand]:
    """Uncurated-tail size bands ``(label, lo, hi)`` for the completeness split; ``[]`` if none declared.

    ``hi=None`` = open-ended. An application with a single whole-cohort run (m_abs) declares none, so the
    completeness split falls back to the fold map alone.
    """
    raw = spec.report.get("size_bands") or []
    return [(b["label"], int(b["lo"]), (int(b["hi"]) if b.get("hi") is not None else None)) for b in raw]


def fold_splits(spec: AttributeSpec) -> tuple[str, ...]:
    """Curated fold labels, in report order (``report.fold_splits``; else the generic train/test/val)."""
    return tuple(spec.report.get("fold_splits") or ("train", "test", "val"))


def synthetic_collections(spec: AttributeSpec) -> tuple[str, ...]:
    """Synthetic split labels appended (in order) to the split order (``report.synthetic_collections``; else none).

    Klebsiella carries ``[NCTC_collection, Refseq_collection]`` (assembly-only pseudo-studies the agent skips);
    other applications declare none. Kept explicit because the engine's ``SYNTHETIC_STUDIES`` is an unordered
    set, whereas the report needs a stable column order.
    """
    return tuple(spec.report.get("synthetic_collections") or ())
