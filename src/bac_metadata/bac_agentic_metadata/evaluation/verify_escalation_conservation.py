r"""Escalation-conservation gate (CLI) — the end-to-end check that no curator decision is silently lost.

The curator-escalation answer travels a five-link chain, and every past silent-drop bug hid at a *different*
link. The run-health report accounts for links 1–2 (detect → decisions queue → answered/skip), but stops
there; it cannot see links 3–5. This is the hard gate over those links — it asserts, per tag and across the
accumulated master, that a decision the curator made survives all the way to the final cell:

    1 detect     → decisions_needed_<tag>.tsv            (run-health covers)
    2 answer      → answer / answer_note in that queue    (run-health covers)
    3 apply       → escalation_applied_<tag>.tsv          INV1
    4 accumulate  → curated_escalations.tsv (master)      INV2  (vs git HEAD)
    5 fill        → filled_metadata_<tag>.tsv (final)     INV3

The invariants themselves live in :mod:`engine.escalation_conservation` (so the driver / ``escalate --apply``
always-on WARN gate calls the SAME logic without an ``engine`` → ``evaluation`` import cycle). This file is the
thin CLI: it runs every invariant, stamps the VERIFIED block into run-health on success, and — unlike the
always-on WARN gate — **exits non-zero on any failure**, so it is the checklist/CI stop.

Read-only except for the stamped ``ESCALATION-CONSERVATION`` block. Run after a driver pass (or an
``escalate --apply`` + accumulate):

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.verify_escalation_conservation \
        --data-dir .../applications/klebsiella/data --tags train,test,tail100,tail50_99,tail25_49,tail10_24
"""

from __future__ import annotations

import argparse
import sys

from bac_metadata.bac_agentic_metadata.engine import escalation_conservation as ec

# Re-exported for the tests + any caller that imported the checks from here historically.
_CONSERVATION_MARKER = ec._CONSERVATION_MARKER
check_inv1_apply = ec.check_inv1_apply
check_inv2_master = ec.check_inv2_master
check_inv3_fill = ec.check_inv3_fill
_amend_run_health = ec._amend_run_health


def main() -> None:
    """Run every conservation invariant per tag (+ the master vs HEAD), amend run-health, exit non-zero on fail."""
    ap = argparse.ArgumentParser(description="Escalation-conservation gate — no curator decision silently lost.")
    ap.add_argument("--data-dir", required=True, help="Application data tree root.")
    ap.add_argument("--tags", required=True, help="Comma-separated run tags (e.g. train,test,tail100).")
    ap.add_argument("--no-amend", action="store_true", help="Do not write the verified block into run-health.")
    args = ap.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    fails = ec.verify_tags(args.data_dir, tags, amend=not args.no_amend, include_master=True)

    print(f"\n{'ALL CONSERVATION INVARIANTS HOLD' if not fails else f'{len(fails)} FAILURE(S):'}")
    for f in fails:
        print(f"  ⛔ {f}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
