r"""Curator CLI — the human-escalation tier: resolve the whole-field near-miss queue, then apply it.

Species-agnostic. The pipeline driver (``engine.run_full_metadata_agent``) *detects* escalations on every
pass, writing ``<data-dir>/study_lv_attributes/escalation/decisions_needed_<tag>.tsv`` (empty answer
columns) and re-applying any answers already filled. This CLI is the attended half of that loop:

* ``--interactive`` — walk the *pending* decisions at the prompt (Enter accepts the suggested value, ``s``
  records a curator skip, Ctrl-C stops). Already-resolved rows (answered, or a reject/skip note) are
  preserved untouched, so a partially-answered queue resumes safely. Writes answers back into the queue.
* ``--apply`` — read the filled queue and apply the answers as whole-field fills through the engine backfill
  path (:func:`engine.stages.escalate_apply`), writing ``escalation_applied_<tag>.tsv``
  (``method="curator_escalation"``). The driver also applies on its next pass; this is the standalone shortcut.

Detection lives in the driver (it needs the grader JSONL + the LLM triage); regenerate the queue by
re-running the pipeline. Replaces the former per-application ``run_escalations.py``.

    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.escalate \\
        --interactive --data-dir .../applications/klebsiella/data --tag train
    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.escalate \\
        --apply --data-dir .../applications/klebsiella/data --tag train \\
        --table .../klebsiella/data/inputs/base_table.csv \\
        --splits .../klebsiella/data/fold_splits/project_splits.tsv --fold train,val
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import stages


def _resolved(row: pd.Series) -> bool:
    """A queue row is resolved when it has an answer, or a reject/skip/undetermined curator note."""
    if str(row.get("answer", "")).strip():
        return True
    return any(w in str(row.get("answer_note", "")).lower()
               for w in ("reject", "skip", "undeterm", "leave uncoded", "no value"))


def _interactive(frame: pd.DataFrame, output: Path) -> None:
    """Walk only the *pending* decisions at the prompt; Enter accepts the suggestion, 's' skips.

    Already-resolved rows are preserved untouched and NOT re-walked — re-prompting them would let an Enter
    (= accept suggested) overwrite a prior curator answer with the engine's suggestion (or blank it, where
    there is none). So a partially-answered queue can be resumed safely across runs. Writes the full frame
    (resolved rows + new answers) back to ``output``.
    """
    if not len(frame):
        print("No escalations to resolve.", file=sys.stderr)
        return

    pending = frame[~frame.apply(_resolved, axis=1)]
    n_resolved = len(frame) - len(pending)
    if n_resolved:
        print(f"({n_resolved} already-resolved decision(s) preserved — walking the {len(pending)} pending.)",
              file=sys.stderr)
    if not len(pending):
        print("All escalations already resolved — nothing to walk.", file=sys.stderr)
        return
    print(f"\n{len(pending)} decision(s) — Enter accepts the suggested value, 's' skips, Ctrl-C stops.\n")
    for pos, (idx, r) in enumerate(pending.iterrows(), start=1):
        print("=" * 90)
        print(f"[{pos}/{len(pending)}] {r['study_accession']} · {r['field']} · gap {r['gap_samples']} samples "
              f"· {r['resolution']} · fulltext={r['fulltext_status']}")
        print(f"  cluster theme: {r['cluster_theme']}")
        print(f"  grader quote : {r['grader_quote']}")
        print(f"  paper excerpt: {r['paper_excerpt']}")
        if str(r.get("region_hint", "") or "").strip():
            print(f"  REGION HINT  : {r['region_hint']} (countries cluster to one region; no dominant country — "
                  f"confirm a country or accept the region)")
        print(f"  SUGGESTED    : {r['suggested_value'] or '(none)'}")
        try:
            ans = input("  your value [Enter=suggested, s=skip]: ").strip()
        except EOFError:
            print("\n(no interactive input available — stopping)", file=sys.stderr)
            break
        if ans.lower() == "s":
            # A skip is a DECISION ("no single whole-field value applies"), not "undecided" — record it so
            # run-health treats the cell as resolved (curator-rejected), never a perpetual pending ACTIONABLE.
            frame.at[idx, "answer_note"] = "curator skip: no single whole-field value (genuinely wide / undeterminable)"
            continue
        frame.at[idx, "answer"] = ans or r["suggested_value"]
    frame.to_csv(output, sep="\t", index=False)
    filled = int((frame["answer"].astype(str).str.strip() != "").sum())
    print(f"\nWrote {output.name}: {filled}/{len(frame)} answered.", file=sys.stderr)


def main() -> None:
    """Parse arguments and dispatch to the interactive walk or the apply step."""
    p = argparse.ArgumentParser(description="Human-escalation tier — resolve/apply the whole-field queue (any application).")
    p.add_argument("--data-dir", required=True, help="Application data tree root.")
    p.add_argument("--tag", default="train", help="Run tag — selects decisions_needed_<tag>.tsv / escalation_applied_<tag>.tsv.")
    p.add_argument("--interactive", action="store_true", help="Walk the pending queue at the prompt.")
    p.add_argument("--apply", action="store_true", help="Apply the filled queue → escalation_applied_<tag>.tsv.")
    p.add_argument("--queue", default=None,
                   help="Queue TSV (default <data-dir>/study_lv_attributes/escalation/decisions_needed_<tag>.tsv).")
    p.add_argument("--applied-output", default=None,
                   help="Apply output (default .../escalation/escalation_applied_<tag>.tsv).")
    # --apply needs the base table + fold selection to build the per-sample fills:
    p.add_argument("--table", default=None, help="(--apply) full-width base table CSV/TSV.")
    p.add_argument("--splits", default=None,
                   help="(--apply) fold split TSV (default <data-dir>/fold_splits/project_splits.tsv).")
    p.add_argument("--fold", default=None, help="(--apply) comma-separated fold(s) the tag covers.")
    p.add_argument("--accessions", default=None, help="(--apply) explicit accessions instead of --fold.")
    args = p.parse_args()

    if args.interactive == args.apply:
        sys.exit("Choose exactly one mode: --interactive OR --apply.")

    data = Path(args.data_dir)
    esc_dir = data / "study_lv_attributes" / "escalation"
    queue = Path(args.queue) if args.queue else esc_dir / f"decisions_needed_{args.tag}.tsv"
    if not queue.exists():
        sys.exit(f"No queue at {queue} — run the pipeline (driver) first to detect escalations.")

    if args.interactive:
        frame = pd.read_csv(queue, sep="\t", dtype=str).fillna("")
        _interactive(frame, queue)
        return

    # --apply
    if not args.table:
        sys.exit("--apply needs --table (the full-width base table) to build the per-sample fills.")
    applied_out = (Path(args.applied_output) if args.applied_output
                   else esc_dir / f"escalation_applied_{args.tag}.tsv")
    base = pd.read_csv(args.table, dtype=str, low_memory=False, keep_default_na=False)
    if args.accessions:
        keep = [a.strip() for a in args.accessions.split(",") if a.strip()]
    elif args.fold:
        splits = Path(args.splits) if args.splits else data / "fold_splits" / "project_splits.tsv"
        sel = pd.read_csv(splits, sep="\t", dtype=str)
        folds = {f.strip() for f in args.fold.split(",") if f.strip()}
        keep = list(sel[sel["fold"].isin(folds)]["study_accession"])
    else:
        sys.exit("--apply needs --fold (or --accessions) to select the studies.")
    stages.escalate_apply(base=base, keep=keep, queue_path=queue, out_path=applied_out)


if __name__ == "__main__":
    main()
