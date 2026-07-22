r"""Overwrite blast-radius gate — a fill must NEVER change a KNOWN base value (only a date refinement).

The engine's overwrite guard (``per_sample_completeness.never_overwrite`` + the single-hop fidelity judge)
promises fills only ever populate BLANK cells: a value already recorded in ENA is preserved, whether the
fill came from whole-field backfill, per-sample extraction, or a curator escalation. This read-only gate
proves that end-to-end on a run's production table. Per field it takes each sample's placeholder-stripped
known base value and checks the filled table did not change it. The ONLY sanctioned difference is a
single-hop ``collection_date`` refinement — a year sharpened to a fuller date WITHIN that same year (the
base value is a strict prefix of the fill) — which the engine deliberately allows.

App-agnostic (Klebsiella + M. abscessus): the fields come from the spec, so it always checks exactly the
application's completeness fields. Exits non-zero when any field shows a REAL (non-refinement) change, so it
gates a run alongside :mod:`verify_pipeline_triggers` / :mod:`verify_escalation_conservation`.

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.verify_overwrite_blast_radius \\
        --app m_abs --tags mabs_all
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.categorise.preclean import preclean_base
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

ENGINE_APPS = Path(__file__).resolve().parents[1] / "applications"


def _known_base_per_sample(base: pd.DataFrame, field: str) -> pd.Series:
    """First non-blank (placeholder-stripped) base value per sample, across all its run-rows."""
    v = backfill.strip_placeholders(base[field])
    tmp = pd.DataFrame({"sample_accession": base["sample_accession"].to_numpy(), "_v": v.to_numpy()})
    return tmp.dropna(subset=["_v"]).drop_duplicates("sample_accession").set_index("sample_accession")["_v"]


def _is_date_refinement(base_val: str, fill_val: str) -> bool:
    """A same-year date refinement: the base is a strict prefix (year -> year-month -> full) of the fill."""
    return bool(fill_val) and bool(base_val) and fill_val.startswith(base_val) and fill_val != base_val


def blast_radius(base: pd.DataFrame, filled: pd.DataFrame, fields: Sequence[str]) -> list[dict]:
    """Per field, count samples whose KNOWN base value the filled table changed (REAL vs date-refinement).

    Parameters
    ----------
    base
        The raw per-run base table, already precleaned (:func:`preclean_base`) so null tokens (e.g. cf_status
        ``?``) are not mistaken for known values.
    filled
        The tag's per-sample production table (``filled_metadata.tsv``), keyed by ``sample_accession``.
    fields
        The application's completeness fields.

    Returns
    -------
    list of dict
        One row per field: ``field, n_known_base, changed, date_refinement, REAL_CHANGE`` (``field, note,
        REAL_CHANGE=0`` when a field is absent from either table), each with an ``examples`` list of up to
        five ``sample: base -> fill`` REAL changes.
    """
    filled_idx = filled.drop_duplicates("sample_accession").set_index("sample_accession")
    rows: list[dict] = []
    for f in fields:
        if f not in filled.columns or f not in base.columns:
            rows.append({"field": f, "note": "field absent", "REAL_CHANGE": 0, "examples": []})
            continue
        kb = _known_base_per_sample(base, f)                                  # sample -> known base value
        fv = backfill.strip_placeholders(filled_idx[f]).reindex(kb.index)     # aligned fill (blank -> NaN)
        pair = pd.DataFrame({"b": kb, "f": fv}).dropna(subset=["f"])          # only where the fill is non-blank
        diff = pair[pair["f"] != pair["b"]]                                   # fill differs from the known base
        if f == "collection_date" and len(diff):
            refine_mask = diff.apply(lambda r: _is_date_refinement(r["b"], r["f"]), axis=1)
        else:
            refine_mask = pd.Series(False, index=diff.index)
        real = diff[~refine_mask]
        rows.append({
            "field": f, "n_known_base": int(len(kb)), "changed": int(len(diff)),
            "date_refinement": int(refine_mask.sum()), "REAL_CHANGE": int(len(real)),
            "examples": [f"{sa}: {r.b!r} -> {r.f!r}" for sa, r in real.head(5).iterrows()],
        })
    return rows


def verify_tag(data_dir: Path, spec: AttributeSpec, tag: str) -> int:
    """Run the gate for one tag: print the table, write ``run_health/overwrite_blast_radius.tsv``, return REAL total."""
    rp = RunPaths(data_dir, tag)
    base = pd.read_csv(data_dir / "inputs" / "base_table.csv", dtype=str, keep_default_na=False)
    base, _ = preclean_base(base, spec)
    filled = pd.read_csv(rp.filled_metadata, sep="\t", dtype=str, keep_default_na=False)
    rows = blast_radius(base, filled, list(spec.completeness_fields))

    table = pd.DataFrame([{k: v for k, v in r.items() if k != "examples"} for r in rows])
    real_total = int(table["REAL_CHANGE"].fillna(0).sum())
    rp.run_health_dir.mkdir(parents=True, exist_ok=True)
    out = rp.run_health_dir / "overwrite_blast_radius.tsv"
    table.to_csv(out, sep="\t", index=False)

    print(f"[{tag}] base rows (per-run): {len(base)}; filled rows (per-sample): {len(filled)}")
    print(table.to_string(index=False))
    for r in rows:
        if r.get("examples"):
            print(f"  [{r['field']}] REAL changes (should be none):")
            for e in r["examples"]:
                print(f"     {e}")
    verdict = "PASS" if real_total == 0 else "FAIL"
    print(f"[{tag}] {verdict} — {real_total} REAL (non-refinement) change(s) to a known base value "
          f"(date refinements allowed) → run_progress/{tag}/run_health/overwrite_blast_radius.tsv")
    return real_total


def main() -> None:
    """Run the blast-radius gate over ``--tags``; exit 1 if any tag has a REAL change (unless ``--no-fail``)."""
    p = argparse.ArgumentParser(description="Overwrite blast-radius gate (read-only, hard exit code).")
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

    total_real = sum(verify_tag(data_dir, spec, tag) for tag in tags)
    print(f"\nTOTAL REAL (non-refinement) changes across {len(tags)} tag(s): {total_real}")
    sys.exit(1 if (total_real and not args.no_fail) else 0)


if __name__ == "__main__":
    main()
