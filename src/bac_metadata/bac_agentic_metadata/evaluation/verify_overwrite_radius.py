r"""Overwrite-radius verification (CLI) — a fill must never change a value ENA already recorded.

The overwrite guard promises fills only populate BLANK cells. This is the hard gate that proves it on a run's
production table: per field it compares each sample's known base value to the filled cell and classifies every
difference as a same-year ``collection_date`` refinement (allowed), a fidelity-judge-approved
``gated_overwrite`` of a non-protected field (allowed; surfaced for spot-review), or a ``protected_violation``
— a change to a ``never_overwrite`` field, which must NEVER happen. Only a protected violation fails the gate,
so it is correct for every application (Klebsiella reports its judge-approved isolation_source overwrites and
passes; M. abscessus fails loudly if a recorded cf_status is touched).

The invariant + the classification live in :mod:`engine.overwrite_radius` (so the always-on driver WARN gate
calls the SAME logic without an ``engine`` → ``evaluation`` import cycle). This file is the thin CLI: run it
after a driver pass (or an ``escalate --apply``) and it **exits non-zero on any protected violation**, so it is
the checklist/CI stop. Read-only except for the per-tag ``run_health/overwrite_radius.tsv`` record.

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.verify_overwrite_radius \
        --app m_abs --tags mabs_all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bac_metadata.bac_agentic_metadata.engine import overwrite_radius as orad
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

ENGINE_APPS = Path(__file__).resolve().parents[1] / "applications"


def main() -> None:
    """Run the overwrite-radius gate over ``--tags``; exit 1 on any protected violation (unless ``--no-fail``)."""
    p = argparse.ArgumentParser(description="Overwrite-radius verification (read-only, hard exit code).")
    p.add_argument("--app", default="klebsiella", help="Application under applications/ (default klebsiella).")
    p.add_argument("--data-dir", default=None, help="Override data dir (default applications/<app>/data).")
    p.add_argument("--spec", default=None, help="attributes.yaml (default applications/<app>/attributes.yaml).")
    p.add_argument("--tags", required=True, help="Comma-separated run tags to verify (e.g. mabs_all).")
    p.add_argument("--no-fail", action="store_true", help="Always exit 0 (report only).")
    args = p.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else ENGINE_APPS / args.app / "data"
    spec_path = Path(args.spec) if args.spec else ENGINE_APPS / args.app / "attributes.yaml"
    if not data_dir.exists():
        sys.exit(f"data dir not found: {data_dir}")
    spec = AttributeSpec.from_yaml(str(spec_path))
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    fails = orad.verify_tags(data_dir, spec, tags)
    print(f"\n{'OVERWRITE RADIUS CLEAN — no protected value changed' if not fails else f'{len(fails)} FAILURE(S):'}")
    for f in fails:
        print(f"  ⛔ {f}")
    sys.exit(1 if (fails and not args.no_fail) else 0)


if __name__ == "__main__":
    main()
