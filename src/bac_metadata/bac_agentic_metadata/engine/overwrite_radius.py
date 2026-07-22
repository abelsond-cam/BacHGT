r"""Overwrite-radius verification — the engine core proving a fill never changes a value ENA already recorded.

The overwrite guard promises fills only populate BLANK cells: whole-field backfill, per-sample extraction, and
curator escalations may ADD a value where ENA was blank, but a value already recorded is preserved —
ABSOLUTELY for the application's ``never_overwrite`` fields (the widest-axis phenotype, e.g. cf_status), and
otherwise only via the single-hop fidelity judge (a vague ENA value sharpened to a specific one) or a same-year
``collection_date`` refinement. This read-only gate proves that on a run's production table.

Per field it takes each sample's placeholder-stripped known base value, compares it to the filled cell, and
classifies every difference:

    * ``date_refinement``     — ``collection_date`` sharpened WITHIN the same year (base is a strict prefix). Allowed.
    * ``gated_overwrite``     — a non-refinement change to a NON-protected field: a fidelity-judge-approved
                                vague→specific replacement. Allowed; surfaced for optional spot-review, NOT a failure.
    * ``protected_violation`` — a change to a ``never_overwrite`` field. This must NEVER happen → the hard failure.

Only ``protected_violation`` fails the gate, so it is correct for every application: Klebsiella (no protected
fields; ~900 legitimate judge-approved ``isolation_source`` overwrites) passes with those reported, while
M. abscessus (``cf_status`` protected) fails loudly the instant a recorded CF/non-CF value is touched.

The pure check + the :func:`verify_tags` orchestrator live in ``engine`` (not ``evaluation``) so BOTH the
always-on driver WARN gate and the standalone CLI (:mod:`evaluation.verify_overwrite_radius`) call the SAME
logic without an ``engine`` → ``evaluation`` import cycle. Read-only (writes only the per-tag
``run_health/overwrite_radius.tsv`` record).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill as bf
from bac_metadata.bac_agentic_metadata.engine.categorise.preclean import preclean_base
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

_REPORT_COLUMNS = [
    "field", "protected", "n_known_base", "changed", "date_refinement", "gated_overwrite", "protected_violation",
]


def _known_base_per_sample(base: pd.DataFrame, field: str) -> pd.Series:
    """First non-blank (placeholder-stripped) base value per sample, across all its run-rows."""
    v = bf.strip_placeholders(base[field])
    tmp = pd.DataFrame({"sample_accession": base["sample_accession"].to_numpy(), "_v": v.to_numpy()})
    return tmp.dropna(subset=["_v"]).drop_duplicates("sample_accession").set_index("sample_accession")["_v"]


def _is_date_refinement(base_val: str, fill_val: str) -> bool:
    """A same-year date refinement: the base is a strict prefix (year -> year-month -> full) of the fill."""
    return bool(fill_val) and bool(base_val) and fill_val.startswith(base_val) and fill_val != base_val


def overwrite_radius(
    base: pd.DataFrame, filled: pd.DataFrame, fields: Sequence[str], protected: Sequence[str]
) -> list[dict]:
    """Per field, classify every change the filled table made to a KNOWN base value (see module docstring).

    Parameters
    ----------
    base
        The raw per-run base table, already precleaned (:func:`preclean_base`) so null tokens (e.g. cf_status
        ``?``) are not mistaken for known values.
    filled
        The tag's per-sample production table (``filled_metadata``), keyed by ``sample_accession``.
    fields
        The application's completeness fields.
    protected
        The ``never_overwrite`` fields whose recorded value must never change (any change is the hard failure).

    Returns
    -------
    list of dict
        One row per field with the :data:`_REPORT_COLUMNS` counts (``field, note`` when a field is absent from
        either table), each carrying an ``examples`` list of up to five ``sample: base -> fill`` changes.
    """
    protected = set(protected)
    filled_idx = filled.drop_duplicates("sample_accession").set_index("sample_accession")
    rows: list[dict] = []
    for f in fields:
        is_protected = f in protected
        if f not in filled.columns or f not in base.columns:
            rows.append({"field": f, "protected": is_protected, "note": "field absent",
                         "protected_violation": 0, "gated_overwrite": 0, "examples": []})
            continue
        kb = _known_base_per_sample(base, f)
        fv = bf.strip_placeholders(filled_idx[f]).reindex(kb.index)          # aligned fill (blank -> NaN)
        pair = pd.DataFrame({"b": kb, "f": fv}).dropna(subset=["f"])         # only where the fill is non-blank
        diff = pair[pair["f"] != pair["b"]]                                  # fill differs from the known base
        if f == "collection_date" and len(diff):
            refine_mask = diff.apply(lambda r: _is_date_refinement(r["b"], r["f"]), axis=1)
        else:
            refine_mask = pd.Series(False, index=diff.index)
        overwrites = diff[~refine_mask]                                      # non-refinement changes to a known value
        rows.append({
            "field": f, "protected": is_protected, "n_known_base": int(len(kb)), "changed": int(len(diff)),
            "date_refinement": int(refine_mask.sum()),
            "gated_overwrite": 0 if is_protected else int(len(overwrites)),
            "protected_violation": int(len(overwrites)) if is_protected else 0,
            "examples": [f"{sa}: {r.b!r} -> {r.f!r}" for sa, r in overwrites.head(5).iterrows()],
        })
    return rows


def verify_tag(data_dir: Path, spec: AttributeSpec, tag: str, fails: list[str],
               out: Callable[[str], None] = print) -> dict:
    """Run the overwrite-radius check for one tag: print the table, write the tsv, append any protected failure."""
    rp = RunPaths(data_dir, tag)
    base = pd.read_csv(data_dir / "inputs" / "base_table.csv", dtype=str, keep_default_na=False)
    base, _ = preclean_base(base, spec)
    filled = pd.read_csv(rp.filled_metadata, sep="\t", dtype=str, keep_default_na=False)
    rows = overwrite_radius(base, filled, list(spec.completeness_fields), spec.overwrite_protected_fields)

    table = pd.DataFrame([{k: v for k, v in r.items() if k != "examples"} for r in rows]).reindex(
        columns=[*_REPORT_COLUMNS, "note"]).dropna(axis=1, how="all")
    violations = int(sum(r.get("protected_violation", 0) for r in rows))
    gated = int(sum(r.get("gated_overwrite", 0) for r in rows))
    rp.run_health_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(rp.run_health_dir / "overwrite_radius.tsv", sep="\t", index=False)

    out(f"  {'PASS' if not violations else 'FAIL'}  [{tag}] overwrite-radius — {violations} protected "
        f"violation(s), {gated} gated overwrite(s) reported (allowed), "
        f"base rows {len(base)} → filled {len(filled)}")
    out("    " + table.to_string(index=False).replace("\n", "\n    "))
    for r in rows:
        if r.get("protected_violation") and r.get("examples"):
            out(f"    ⛔ [{r['field']}] protected value CHANGED (never allowed): {'; '.join(r['examples'])}")
    if violations:
        fails.append(f"[{tag}] overwrite-radius: {violations} change(s) to a never_overwrite value")
    return {"protected_violation": violations, "gated_overwrite": gated}


def verify_tags(data_dir: str | Path, spec: AttributeSpec, tags: Sequence[str],
                *, out: Callable[[str], None] = print) -> list[str]:
    """Run the overwrite-radius gate for ``tags``; return the failure strings (protected violations; empty = clean).

    The ONE orchestrator both callers share: the standalone CLI (:mod:`evaluation.verify_overwrite_radius`,
    exits non-zero on a non-empty return) and the always-on driver WARN gate (loud, but exit 0). A gated
    overwrite of a non-protected field is reported, never a failure — only a change to a ``never_overwrite``
    field fails.
    """
    data = Path(data_dir)
    fails: list[str] = []
    out("Overwrite-radius gate — a fill must never change a value ENA already recorded\n")
    for tag in (t.strip() for t in tags if t.strip()):
        verify_tag(data, spec, tag, fails, out)
    return fails
