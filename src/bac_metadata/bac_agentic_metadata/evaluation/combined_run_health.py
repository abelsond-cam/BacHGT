r"""Cross-tag run-health roll-up with an explicit acceptance policy → ONE "genuinely clear" verdict.

Per-tag ``run_health`` is deliberately conservative: it reports every un-FILLED cell as ``ACTIONABLE`` or
``BLOCKED`` and says *"supplement & rerun"* — it has **no notion of a gap that is genuinely unrecoverable**, so
it can never declare a cohort clear. Confirming "there is really nothing left to do" therefore used to require
hand-rolled Python across the per-tag ``report.tsv`` grids (done 2026-07-15). This tool makes that repeatable.

It (a) **unions** the per-tag ``run_progress/<tag>/run_health/report.tsv`` grids and (b) applies a transparent
**acceptance policy** — reclassifying the outstanding buckets a curator has already dispositioned as genuinely
unrecoverable (``ACCEPTED``) versus the ones a curator can still act on (``ACTIONABLE``). It then emits one
verdict: **GENUINELY CLEAR** vs **K truly-actionable cell(s) remain (listed)**.

The policy is the whole point, so it lives in one visible constant (:data:`ACCEPT_POLICY`). It encodes the
dispositions confirmed for *Klebsiella*: an escalation still awaiting a curator answer is the only genuinely
actionable bucket; a requested supplement not in the folder is *unavailable* (all fetchable tables were
fetched), an unanchored table has *no ENA-mappable key*, and a wide-mix big-decision has *no single whole-field
value*. Any **unrecognised** recoverability on an outstanding cell is treated as ACTIONABLE (fail-loud), so a
new failure mode surfaces rather than being silently accepted.

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.combined_run_health \
        --tags train,test,tail100,tail50_99,tail25_49,tail10_24
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

#: recoverability (on an ACTIONABLE/BLOCKED cell) → (disposition, human reason). ``ACCEPTED`` = genuinely
#: unrecoverable, counts toward "clear"; ``ACTIONABLE`` = a curator can still resolve it. Unrecognised keys
#: fall through to ACTIONABLE (fail-loud) so a new failure mode is never silently swept into "clear".
ACCEPT_POLICY: dict[str, tuple[str, str]] = {
    "answer_escalation": ("ACTIONABLE", "whole-field escalation still awaiting a curator answer"),
    "fetch_supp_table": ("ACCEPTED", "requested supplement not in folder — unavailable (all fetchable fetched)"),
    "needs_linkage": ("ACCEPTED", "table has no ENA-mappable key (unanchored) or no per-isolate table exists"),
    "escalate_big_decision": ("ACCEPTED", "wide-mix — no single whole-field value applies"),
}

#: resolution_states that are already closed (not outstanding). FILLED = resolved; EXHAUSTED = logged-exhausted.
_CLOSED = ("FILLED", "EXHAUSTED")


def classify(row: pd.Series) -> tuple[str, str]:
    """Map one run-health cell to a disposition and reason.

    Returns one of ``FILLED`` / ``EXHAUSTED`` / ``ACCEPTED`` / ``ACTIONABLE`` and a short reason.
    """
    state = str(row.get("resolution_state", "")).strip()
    if state in _CLOSED:
        return state, "already closed"
    rec = str(row.get("recoverability", "")).strip()
    disp, reason = ACCEPT_POLICY.get(rec, ("ACTIONABLE", f"unrecognised recoverability '{rec}' — review"))
    return disp, reason


def combine(data_dir: Path, tags: list[str]) -> tuple[pd.DataFrame, dict[str, int]]:
    """Union the per-tag run-health grids, classify every cell, return (annotated frame, verdict counts)."""
    frames = []
    for tag in tags:
        tsv = RunPaths(data_dir, tag).run_health_tsv
        if not tsv.exists():
            print(f"[warn] no run_health for tag '{tag}' at {tsv} — skipped", file=sys.stderr)
            continue
        df = pd.read_csv(tsv, sep="\t", dtype=str).fillna("")
        df["tag"] = tag
        frames.append(df)
    if not frames:
        return pd.DataFrame(), {}
    allcells = pd.concat(frames, ignore_index=True)
    disp = allcells.apply(classify, axis=1, result_type="expand")
    allcells["disposition"], allcells["disposition_reason"] = disp[0], disp[1]
    counts = allcells["disposition"].value_counts().to_dict()
    return allcells, counts


def _render_md(allcells: pd.DataFrame, counts: dict[str, int], tags: list[str]) -> str:
    """Render the combined verdict + per-tag roll-up + the truly-actionable list."""
    actionable = allcells[allcells["disposition"] == "ACTIONABLE"]
    clear = len(actionable) == 0
    verdict = "✅ **GENUINELY CLEAR**" if clear else f"⚠️ **{len(actionable)} truly-actionable cell(s) remain**"
    total = len(allcells)
    L = [
        f"# Combined run-health — {len(tags)} tag(s) — {verdict}",
        "",
        "Cross-tag roll-up of `run_progress/<tag>/run_health/report.tsv` with the acceptance policy in "
        "`evaluation/combined_run_health.py` applied. **ACCEPTED** = genuinely unrecoverable (counts as clear); "
        "**ACTIONABLE** = a curator can still resolve it. Unrecognised recoverability → ACTIONABLE (fail-loud).",
        "",
        f"**{total} (study×field) cells** — "
        + " · ".join(f"{k} {counts.get(k, 0)}" for k in ("FILLED", "EXHAUSTED", "ACCEPTED", "ACTIONABLE")),
        "",
        "## Per-tag roll-up",
        "",
        "| tag | FILLED | EXHAUSTED | ACCEPTED | ACTIONABLE |",
        "|---|---|---|---|---|",
    ]
    for tag in tags:
        sub = allcells[allcells["tag"] == tag]
        if not len(sub):
            continue
        c = sub["disposition"].value_counts()
        L.append(f"| {tag} | {c.get('FILLED', 0)} | {c.get('EXHAUSTED', 0)} | {c.get('ACCEPTED', 0)} "
                 f"| {c.get('ACTIONABLE', 0)} |")
    L += ["", "## Accepted-as-unrecoverable — breakdown", "", "| reason | cells |", "|---|---|"]
    acc = allcells[allcells["disposition"] == "ACCEPTED"]
    for reason, n in acc["disposition_reason"].value_counts().items():
        L.append(f"| {reason} | {n} |")
    L += ["", "## Truly-actionable cells", ""]
    if clear:
        L.append("_None — every outstanding cell is an accepted, genuinely-unrecoverable gap._")
    else:
        L += ["| tag | study | field | recoverability | reason |", "|---|---|---|---|---|"]
        for _, r in actionable.iterrows():
            L.append(f"| {r['tag']} | {r.get('study_accession', '')} | {r.get('field', '')} "
                     f"| {r.get('recoverability', '')} | {r['disposition_reason']} |")
    return "\n".join(L) + "\n"


def main() -> None:
    """Union the tags' run-health grids, apply the acceptance policy, write the combined verdict."""
    p = argparse.ArgumentParser(description="Cross-tag run-health roll-up with acceptance policy (any application).")
    p.add_argument("--app", default="klebsiella", help="Application under applications/ (default klebsiella).")
    p.add_argument("--data-dir", default=None, help="Override data dir (default applications/<app>/data).")
    p.add_argument("--tags", required=True, help="Comma-separated run tags to union.")
    p.add_argument("--out", default=None, help="Output stem (default <data-dir>/combined_run_health).")
    p.add_argument("--strict", action="store_true", help="Exit 1 when not genuinely clear (for CI).")
    args = p.parse_args()

    here = Path(__file__).resolve().parent.parent  # bac_agentic_metadata/
    data_dir = Path(args.data_dir) if args.data_dir else here / "applications" / args.app / "data"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    allcells, counts = combine(data_dir, tags)
    if not len(allcells):
        sys.exit("No run-health grids found for any tag.")

    md = _render_md(allcells, counts, tags)
    stem = Path(args.out) if args.out else data_dir / "combined_run_health"
    stem.parent.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".md").write_text(md)
    allcells.to_csv(stem.with_suffix(".tsv"), sep="\t", index=False)

    n_act = int(counts.get("ACTIONABLE", 0))
    verdict = "GENUINELY CLEAR" if n_act == 0 else f"{n_act} TRULY-ACTIONABLE cell(s) remain"
    print(f"[combined run-health] {len(tags)} tags · {len(allcells)} cells · "
          f"ACCEPTED {counts.get('ACCEPTED', 0)} · {verdict} → {stem.with_suffix('.md')}", file=sys.stderr)
    raise SystemExit(1 if (args.strict and n_act) else 0)


if __name__ == "__main__":
    main()
