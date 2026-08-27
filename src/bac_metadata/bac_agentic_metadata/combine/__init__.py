"""Combine the agentic Klebsiella curation into the canonical metadata table (v1 → rebuild → v2).

Architecture A (David, 2026-07-22): inject the agent fills at the v1 stage and run the idempotent
``pp/rebuild_v2.sh`` cascade, as a **separate, reviewable** step — not an in-place v2 mutation. See
``MERGE_TO_V2_RUNBOOK.md`` and ``PROJECT_STATE.md`` Layer B.
"""
