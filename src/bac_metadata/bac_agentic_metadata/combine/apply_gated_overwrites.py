r"""Step (iii) of the two-step v2 combine — apply the David-approved per-sample overwrites.

Blank-fill (B2) never replaces an existing value. This step applies the subset of ``v2_overwrite_candidates.tsv``
(B1) that David signs off — the per-sample vague→specific / date-refinement overwrites — over the existing
canonical value, keyed on ``sample_accession``. Each write sets a ``<field>_agent_overwrote`` provenance flag,
and the overwritten rows are re-normalised with v1's own parse/categorise (shared with B2) so the derived
``*_parsed``/``*_category``/``region``/``year_parsed`` columns follow.

**Gated:** run only on the rows David approved (a filtered copy of the B1 artefact). Only the four clinical
fields are accepted; a row for any other field is a hard error (never-overwrite protection lives upstream, this
is a second guard). Rows whose ``sample_accession`` is not in the canonical table are reported, not applied.

    uv run python -m bac_metadata.bac_agentic_metadata.combine.apply_gated_overwrites \
        --canonical <injected_v1_or_v2.tsv> --approved <approved_overwrites.tsv> --out <out.tsv>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.combine.inject_agentic_into_v1 import (
    CLINICAL_FIELDS,
    load_table,
    reparse_rows,
)

#: Columns an approved-overwrites table must carry (a filtered copy of ``v2_overwrite_candidates.tsv``).
REQUIRED_APPROVED_COLS = ("sample_accession", "field", "applied_value")


def apply_gated_overwrites(canonical: pd.DataFrame, approved: pd.DataFrame, *,
                           reparse: bool = True) -> tuple[pd.DataFrame, dict]:
    """Apply approved per-sample overwrites over existing canonical values; re-parse the changed rows.

    Parameters
    ----------
    canonical
        The table to write into (the injected v1, or the rebuilt v2 on CSD3). Keyed on ``sample_accession``.
    approved
        David's approved subset — needs :data:`REQUIRED_APPROVED_COLS`. One ``(sample_accession, field)`` per
        row (deduplicated, last wins, with a warning).
    reparse
        Re-derive the normalised columns for the overwritten rows (True in production; False to unit-test the
        write in isolation).

    Returns
    -------
    tuple
        ``(out, stats)`` — the written frame and a per-field application report.
    """
    missing = [c for c in REQUIRED_APPROVED_COLS if c not in approved.columns]
    if missing:
        sys.exit(f"approved table missing columns: {missing}")
    if "sample_accession" not in canonical.columns:
        sys.exit("canonical table lacks sample_accession — cannot apply overwrites")
    bad = sorted(set(approved["field"]) - set(CLINICAL_FIELDS))
    if bad:
        sys.exit(f"approved rows reference non-clinical fields (refusing to overwrite): {bad}")

    approved = approved.drop_duplicates(["sample_accession", "field"], keep="last")
    out = canonical.copy()
    for f in CLINICAL_FIELDS:
        flag = f"{f}_agent_overwrote"
        if flag not in out.columns:
            out[flag] = False
    canon_samples = set(out["sample_accession"])
    overwrite_mask = pd.Series(False, index=out.index)
    stats: dict = {"requested": int(len(approved)), "rows_written": 0, "unmatched_samples": 0, "per_field": {}}
    for f, grp in approved.groupby("field"):
        vmap = dict(zip(grp["sample_accession"], grp["applied_value"], strict=False))
        sel = out["sample_accession"].isin(vmap.keys())
        out.loc[sel, f] = out.loc[sel, "sample_accession"].map(vmap).to_numpy()
        out.loc[sel, f"{f}_agent_overwrote"] = True
        overwrite_mask |= sel
        unmatched = len(set(vmap) - canon_samples)
        stats["unmatched_samples"] += unmatched
        stats["rows_written"] += int(sel.sum())
        stats["per_field"][f] = {"approved": int(len(grp)), "rows_written": int(sel.sum()),
                                 "unmatched_samples": unmatched}
    if reparse:
        out, n = reparse_rows(out, overwrite_mask)
        stats["rows_reparsed"] = n
    return out, stats


def _report(stats: dict) -> str:
    """One-line-per-field summary of the application."""
    lines = [f"[overwrites] requested={stats['requested']} rows_written={stats['rows_written']} "
             f"unmatched_samples={stats['unmatched_samples']} reparsed={stats.get('rows_reparsed', 0)}"]
    for f, s in stats["per_field"].items():
        lines.append(f"    {f}: approved={s['approved']} rows_written={s['rows_written']} "
                     f"unmatched={s['unmatched_samples']}")
    return "\n".join(lines)


def main() -> None:
    """Apply the approved per-sample overwrites onto a canonical table (gated on David's B1 review)."""
    p = argparse.ArgumentParser(description="Apply David-approved per-sample overwrites (combine step iii).")
    p.add_argument("--canonical", required=True, help="the table to write into (injected v1, or rebuilt v2)")
    p.add_argument("--approved", required=True, help="approved subset of v2_overwrite_candidates.tsv")
    p.add_argument("--out", required=True, help="where to write the result")
    p.add_argument("--no-reparse", action="store_true", help="skip the re-parse (write raw values only)")
    args = p.parse_args()
    canonical = load_table(Path(args.canonical))
    approved = load_table(Path(args.approved))
    out, stats = apply_gated_overwrites(canonical, approved, reparse=not args.no_reparse)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.fillna("").to_csv(args.out, sep="\t", index=False)
    print(_report(stats), file=sys.stderr)
    print(f"[overwrites] wrote {args.out} ({len(out):,} rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
