"""Agentic categorisation sub-engine — a data-driven replacement for the hardcoded parse/categorise.

Replaces the rule-system in ``pp/metadata_curation.py``, scoped to the two messy fields (``host``,
``isolation_source``). Stages (all config-driven via the ``attributes.yaml`` ``categorisation``
block, one per file):

* :mod:`preclean` — wipe field-specific null tokens to blank *before* the fill stages, so the fill
  agent gets a chance to recover them (Phase A).
* ``value_frequencies`` — distinct (placeholder-stripped) values + counts per field (Phase B).
* ``induce_categories`` — LLM proposes a category scheme → human-approved YAML (Phase B).
* ``apply_categories`` — per-distinct-value ``{parsed, category}`` map, joined to rows (Phase C).
* ``reconcile_cross_column`` — a value in one field implying another field, hybrid apply (Phase D).
"""
