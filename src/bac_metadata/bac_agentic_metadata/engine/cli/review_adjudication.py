r"""Curator CLI — walk the residual agent-vs-manual disagreements the adjudicator did not rule for the agent.

The queue is built by ``evaluation.build_adjudication_review_queue`` (find + grade rows the Opus adjudicator
sided against the agent on, or couldn't decide). This is the attended half: the curator confirms who is right.

* ``--interactive`` walks the *pending* rows. For a GRADE row: Enter keeps the manual/sheet value (agent scored
  wrong), ``a`` accepts the agent's value, or type a third value; ``s`` skips. For a FIND row: Enter keeps the
  curated paper, ``a`` accepts the agent's pick; ``s`` skips.
* On completion (``--apply``, or ``--interactive`` which applies as it finishes) the confirmed calls are written
  where the re-summariser reads them: GRADE corrections that overturn the sheet append to the existing
  ``diagnostics/gt_corrections.tsv`` overlay (``corrected_value`` = the curator's value); FIND calls rewrite the
  matching ``adj_verdict`` in ``run_progress/<tag>/find/find_adjudication_report.tsv`` (``found_correct`` /
  ``curated_correct``). Re-running ``summarise_agent_vs_manual`` then reflects the curator's sign-off.

Resume-safe: a row with a ``david_verdict`` is preserved and not re-walked.

    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.review_adjudication --interactive \
        --data-dir .../applications/klebsiella/data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths


def _resolved(row: pd.Series) -> bool:
    """A queue row is resolved once the curator has recorded a verdict."""
    return bool(str(row.get("david_verdict", "")).strip())


def _walk(frame: pd.DataFrame, out: Path) -> None:
    """Walk pending rows at the prompt; record david_verdict / david_value; write the frame back."""
    pending = frame[~frame.apply(_resolved, axis=1)]
    if not len(pending):
        print("No pending disagreements — all reviewed.", file=sys.stderr)
        return
    print(f"\n{len(pending)} disagreement(s) — Enter keeps MANUAL, 'a' = AGENT, or type a value, 's' skips, "
          "Ctrl-C stops.\n")
    for pos, (idx, r) in enumerate(pending.iterrows(), start=1):
        print("=" * 92)
        print(f"[{pos}/{len(pending)}] {r['tag']} · {r['source']} · {r['study_accession']} · {r['field']} "
              f"· adjudicator={r['adj_verdict']}")
        print(f"  agent : {r['agent_value']}")
        print(f"  manual: {r['manual_value']}")
        if str(r.get("adj_correct_value", "")).strip():
            print(f"  adjudicator value: {r['adj_correct_value']}")
        print(f"  reasoning: {str(r['adj_reasoning'])[:300]}")
        if str(r.get("adj_quote", "")).strip():
            print(f"  quote: {str(r['adj_quote'])[:300]}")
        prompt = ("  right? [Enter=manual, a=agent, s=skip]: " if r["source"] == "find"
                  else "  correct value [Enter=manual, a=agent, <value>=other, s=skip]: ")
        try:
            ans = input(prompt).strip()
        except EOFError:
            print("\n(no interactive input — stopping)", file=sys.stderr)
            break
        low = ans.lower()
        if low == "s":
            frame.at[idx, "david_verdict"] = "skip"
        elif low == "a":
            frame.at[idx, "david_verdict"] = "agent"
            frame.at[idx, "david_value"] = r["agent_value"]
        elif ans == "":
            frame.at[idx, "david_verdict"] = "manual"
            frame.at[idx, "david_value"] = r["manual_value"]
        else:  # a typed value (grade rows only, meaningfully)
            frame.at[idx, "david_verdict"] = "other"
            frame.at[idx, "david_value"] = ans
    frame.to_csv(out, sep="\t", index=False)
    done = int(frame.apply(_resolved, axis=1).sum())
    print(f"\nWrote {out.name}: {done}/{len(frame)} reviewed.", file=sys.stderr)


def apply_reviews(frame: pd.DataFrame, data_dir: Path, gt_path: Path) -> dict[str, int]:
    """Push resolved calls to where the re-summariser reads them.

    GRADE rows whose curator value overturns the sheet (verdict agent/other) → append to ``gt_corrections.tsv``.
    FIND rows → rewrite the matching ``adj_verdict`` (agent→found_correct, manual→curated_correct). Returns a
    small counts dict. Idempotent for gt_corrections (dedupe on study_accession+attribute).
    """
    counts = {"gt_corrections_added": 0, "find_verdicts_updated": 0}
    # ── grade → gt_corrections overlay ──────────────────────────────────────────────────────────────────
    grade = frame[(frame["source"] == "grade") & frame["david_verdict"].isin(["agent", "other"])]
    if len(grade):
        gt = (pd.read_csv(gt_path, sep="\t", dtype=str).fillna("") if gt_path.exists()
              else pd.DataFrame(columns=["study_accession", "attribute", "corrected_value", "source"]))
        add = pd.DataFrame({
            "study_accession": grade["study_accession"], "attribute": grade["field"],
            "corrected_value": grade["david_value"], "source": "david_adjudication_review",
        })
        merged = (pd.concat([gt, add], ignore_index=True)
                  .drop_duplicates(["study_accession", "attribute"], keep="last"))
        gt_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(gt_path, sep="\t", index=False)
        counts["gt_corrections_added"] = len(add)
    # ── find → rewrite adj_verdict in each tag's find_adjudication_report ────────────────────────────────
    find = frame[(frame["source"] == "find") & frame["david_verdict"].isin(["agent", "manual"])]
    for tag, sub in find.groupby("tag"):
        rep = RunPaths(data_dir, tag).find_dir / "find_adjudication_report.tsv"
        if not rep.exists():
            continue
        df = pd.read_csv(rep, sep="\t", dtype=str).fillna("")
        want = {r["study_accession"]: ("found_correct" if r["david_verdict"] == "agent" else "curated_correct")
                for _, r in sub.iterrows()}
        mask = df["study_accession"].isin(want)
        df.loc[mask, "adj_verdict"] = df.loc[mask, "study_accession"].map(want)
        df.to_csv(rep, sep="\t", index=False)
        counts["find_verdicts_updated"] += int(mask.sum())
    return counts


def main() -> None:
    """Walk the residual-disagreement queue and push the curator's calls into the re-summariser inputs."""
    p = argparse.ArgumentParser(description="Walk + apply the agent-vs-manual residual-disagreement queue.")
    p.add_argument("--data-dir", required=True, help="Application data tree root.")
    p.add_argument("--queue", default=None, help="Queue TSV (default <data-dir>/diagnostics/adjudication_review_queue.tsv).")
    p.add_argument("--gt-corrections", default=None, help="GT overlay TSV (default <data-dir>/diagnostics/gt_corrections.tsv).")
    p.add_argument("--interactive", action="store_true", help="Walk the pending queue (then apply).")
    p.add_argument("--apply", action="store_true", help="Apply an already-walked queue without re-walking.")
    args = p.parse_args()
    if args.interactive == args.apply:
        sys.exit("Choose exactly one mode: --interactive OR --apply.")

    data = Path(args.data_dir)
    queue = Path(args.queue) if args.queue else data / "diagnostics" / "adjudication_review_queue.tsv"
    gt = Path(args.gt_corrections) if args.gt_corrections else data / "diagnostics" / "gt_corrections.tsv"
    if not queue.exists():
        sys.exit(f"No queue at {queue} — build it with evaluation.build_adjudication_review_queue first.")

    frame = pd.read_csv(queue, sep="\t", dtype=str).fillna("")
    if args.interactive:
        _walk(frame, queue)
        frame = pd.read_csv(queue, sep="\t", dtype=str).fillna("")  # reload the persisted verdicts
    counts = apply_reviews(frame, data, gt)
    print(f"[review] applied — gt_corrections +{counts['gt_corrections_added']}, "
          f"find verdicts updated {counts['find_verdicts_updated']}. "
          "Re-run summarise_agent_vs_manual for train+test to refresh the accuracy.", file=sys.stderr)


if __name__ == "__main__":
    main()
