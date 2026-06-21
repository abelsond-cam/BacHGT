"""Application-agnostic engine primitives.

ENA assessment (deterministic, no LLM): project sizing from ENA (:mod:`ena_sizing`), per-sample
completeness across the base / post-merge / normalised states (:mod:`sources`,
:mod:`completeness`), and per-accession assembly (:mod:`ingest`). The attribute rubric is
loaded from an application ``attributes.yaml`` by :mod:`spec`.
"""
