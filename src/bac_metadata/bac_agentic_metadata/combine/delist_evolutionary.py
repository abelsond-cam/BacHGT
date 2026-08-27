r"""Step 2b (CSD3) — re-clamp the experimental-evolution lab samples AFTER the Kleborate cascade.

B2 set ``kpsc_final_list=False`` for the 1,489 evolutionary lab samples at the v1 stage. The Kleborate merge's
**additive** kpsc rule (``merge_kleborate_into_metadata_v2.py`` lines 377–393) can RE-ADMIT the LRA-bearing ones
(``kpsc_v2 = is_kpsc ∧ (kpsc_v1 ∨ lra_final_list)``), undoing that de-list. This step runs after
``rebuild_v2.sh`` and re-clamps every ``evolutionary_lab_sample`` row — mirroring the merge's own non-Klebsiella
discard block (lines 326–332):

* ``kpsc_final_list = False`` · ``lra_final_list = False`` · ``is_variant_called = False`` (out of the cohort);
* **check + clear** the assembly-quality flags ``is_complete`` / ``is_hybrid`` / ``is_reference_genome``
  (``is_reference_genome = is_complete ∧ is_hybrid ∧ GCF_``, so clearing the first two clears it; all three are
  cleared explicitly). **Count-first:** the counts of each flag currently True on evolutionary rows are surfaced
  BEFORE anything is flipped, in case one is a legitimately-closed genome worth keeping (David, runbook 2b).
* ``is_kpsc`` is **left alone** — it is a *taxonomic* call (a lab-evolved K. pneumoniae is still KPSC); only
  cohort membership is removed (runbook Step 2b; consistent with B2). *(The plan text's mention of clamping
  is_kpsc deviates from the runbook — deliberately NOT done here; confirm with David.)*

**CSD3-only** (``is_complete``/``is_hybrid``/``is_reference_genome``/``is_variant_called``/``lra_final_list`` are
v2-only). **Dry-run by default** — pass ``--apply`` to write.

    uv run python -m bac_metadata.bac_agentic_metadata.combine.delist_evolutionary --v2 <rebuilt_v2.tsv>  # dry-run
    uv run python -m bac_metadata.bac_agentic_metadata.combine.delist_evolutionary --v2 <v2.tsv> --apply --out <v2.tsv>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.combine.inject_agentic_into_v1 import load_table

#: Cohort-membership flags forced False on evolutionary rows.
COHORT_FLAGS = ("kpsc_final_list", "lra_final_list", "is_variant_called")
#: Assembly-quality flags cleared on evolutionary rows (counted first).
QUALITY_FLAGS = ("is_complete", "is_hybrid", "is_reference_genome")
EVO_FLAG = "evolutionary_lab_sample"


def _truthy(series: pd.Series) -> pd.Series:
    """Boolean mask for a column stored as bool or as the strings True/1/yes (case-insensitive)."""
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "t"})


def delist_evolutionary(v2: pd.DataFrame, *, apply: bool = False) -> tuple[pd.DataFrame, dict]:
    """Count (and, if ``apply``, clear) the cohort + quality flags on evolutionary rows. ``is_kpsc`` untouched.

    Returns ``(frame, stats)``. With ``apply=False`` the frame is returned unchanged and ``stats`` reports what
    WOULD change (count-first surfacing); with ``apply=True`` the clamps are written.
    """
    if EVO_FLAG not in v2.columns:
        sys.exit(f"{EVO_FLAG} column missing — run combine.inject_agentic_into_v1 (B2) at the v1 stage first")
    out = v2.copy()
    evo = _truthy(out[EVO_FLAG])
    stats: dict = {"evo_rows": int(evo.sum()), "applied": apply, "cohort_flags": {}, "quality_flags": {}}
    for col in COHORT_FLAGS:
        if col in out.columns:
            stats["cohort_flags"][col] = {"true_pre": int((evo & _truthy(out[col])).sum())}
    for col in QUALITY_FLAGS:
        if col in out.columns:
            stats["quality_flags"][col] = int((evo & _truthy(out[col])).sum())
    missing = [c for c in (*COHORT_FLAGS, *QUALITY_FLAGS) if c not in out.columns]
    if missing:
        stats["absent_columns"] = missing  # expected when run against v1 locally (these are v2-only)
    if apply:
        for col in (*COHORT_FLAGS, *QUALITY_FLAGS):
            if col in out.columns:
                out.loc[evo, col] = "False"
        # is_kpsc deliberately NOT touched (taxonomic).
    return out, stats


def _report(stats: dict) -> str:
    """Human-readable count-first summary."""
    verb = "CLEARED" if stats["applied"] else "would clear (dry-run)"
    lines = [f"[delist] evolutionary_lab_sample rows: {stats['evo_rows']:,}  ({verb})"]
    for col, s in stats["cohort_flags"].items():
        lines.append(f"    cohort  {col}: {s['true_pre']} currently True → False")
    for col, n in stats["quality_flags"].items():
        flag = "  ⚠ REVIEW: closed genomes?" if n else ""
        lines.append(f"    quality {col}: {n} currently True → False{flag}")
    if stats.get("absent_columns"):
        lines.append(f"    (absent here, v2-only): {', '.join(stats['absent_columns'])}")
    lines.append("    is_kpsc: left unchanged (taxonomic)")
    return "\n".join(lines)


def main() -> None:
    """Re-clamp evolutionary lab samples after the Kleborate cascade (dry-run unless --apply)."""
    p = argparse.ArgumentParser(description="Post-Kleborate evolutionary-sample delist (combine step 2b).")
    p.add_argument("--v2", required=True, help="the rebuilt v2 table (post rebuild_v2.sh)")
    p.add_argument("--apply", action="store_true", help="write the clamps (default: dry-run, count only)")
    p.add_argument("--out", default=None, help="output path when --apply (default: overwrite --v2)")
    args = p.parse_args()
    v2 = load_table(Path(args.v2))
    out, stats = delist_evolutionary(v2, apply=args.apply)
    print(_report(stats), file=sys.stderr)
    if args.apply:
        dest = Path(args.out) if args.out else Path(args.v2)
        out.fillna("").to_csv(dest, sep="\t", index=False)
        print(f"[delist] wrote {dest} ({len(out):,} rows)", file=sys.stderr)
    else:
        print("[delist] dry-run — pass --apply to write", file=sys.stderr)


if __name__ == "__main__":
    main()
