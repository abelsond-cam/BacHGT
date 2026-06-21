"""Human-escalation tier runner (Klebsiella) — ask the curator on *tight* whole-field near-misses.

Runs **after** the main pipeline (method-b included) so the batch/overnight run completes untouched, then
the curator resolves the queue. Three modes:

* **detect** (default) — for every fold study×field the grader declined whole-field: gate by gap
  (>``--threshold`` blank ENA cells), gate by method-b coverage (fields already resolved per-sample drop
  out), then triage tight-cluster-vs-wide-mix; escalate only the tight near-misses
  (:func:`engine.escalation.detect_whole_field_escalations`). Writes ``data/decisions_needed.tsv`` (sorted
  by ``gap_samples`` desc) with empty ``answer`` / ``answer_note`` columns for the curator to fill.
* ``--interactive`` — walk the queue at the prompt, printing the background (cluster theme, grader quote,
  paper excerpt, candidate value, gap); Enter accepts the suggested value, ``s`` skips. Writes the same
  TSV with ``answer`` filled.
* ``--apply`` — read a filled ``decisions_needed.tsv``, drop blank-answer rows, and apply the answers as
  whole-field fills through the **existing** :func:`engine.backfill.apply_whole_field` path. Writes
  ``data/escalation_applied.tsv`` (``method="curator_escalation"`` — auditable and distinct from grader
  ``whole_field``).

The detector is production-safe: it uses no curator gold (the test fold / *M. abscessus* have none), only
the grader's own tight-vs-wide judgement of its decline. The grader auto-skips genuinely-wide mixes
(37 countries; blood+urine+respiratory+wound). Two tight precedents it escalates: PRJNA845975
"blood and/or CSF" (all invasive → ``blood``); PRJEB12699 2000–2006 (a short old span → midpoint date).

Examples
--------
unset VIRTUAL_ENV
export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
uv run python .../run_escalations.py --fold train,val               # detect → decisions_needed.tsv
uv run python .../run_escalations.py --interactive                   # attended resolve
uv run python .../run_escalations.py --apply                         # filled queue → escalation_applied.tsv
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.applications.klebsiella import run_backfill as rbf
from bac_metadata.bac_agentic_metadata.applications.klebsiella import run_study_grading as rsg
from bac_metadata.bac_agentic_metadata.engine import backfill, escalation
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, make_llm
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"

QUEUE_COLUMNS = [
    "study_accession", "field", "gap_samples", "resolution", "cluster_theme",
    "suggested_value", "grader_quote", "paper_excerpt", "fulltext_status",
    "answer", "answer_note",
]


def _fold_studies(folds: set[str]) -> set[str]:
    """Study accessions in the chosen folds (the test fold stays sealed unless asked for)."""
    split = pd.read_csv(rbf.SPLIT_PATH, sep="\t", dtype=str)
    return set(split[split["fold"].isin(folds)]["study_accession"])


def _methodb_covered(methodb_path: str | None, raw: pd.DataFrame, frac: float) -> set[tuple[str, str]]:
    """``(study, field)`` pairs per-sample extraction already resolved — method-b runs first.

    A field counts as resolved when method-b filled at least ``frac`` of its blank ENA cells: if the
    sample-level data is there, the whole-field question is already answered and never escalates.
    """
    if not methodb_path or not Path(methodb_path).exists():
        return set()
    mb = pd.read_csv(methodb_path, sep="\t", dtype=str)
    if not {"study_accession", "field"} <= set(mb.columns) or not len(mb):
        return set()
    fills = mb.groupby(["study_accession", "field"]).size()
    gap = escalation.field_gap(raw, backfill.FIELDS)
    return {(acc, f) for (acc, f), n in fills.items() if gap.get((acc, f), 0) > 0 and n >= frac * gap[(acc, f)]}


def _load_grades(grades_path: Path, keep: set[str]) -> list[dict]:
    """Read the grader JSONL (full records, with the backfill map) for studies in ``keep``."""
    if not grades_path.exists():
        sys.exit(f"Grades JSONL not found: {grades_path} (detect needs the full JSONL, not the flat TSV).")
    records: list[dict] = []
    with grades_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("study_accession") in keep:
                records.append(r)
    return records


def _make_evidence_fn(folds: set[str]):
    """Build ``accession -> StudyEvidence`` reusing the grader's cached fulltext / ENA / sizing lookups."""
    paper_links = rsg._accession_to_paper_link()
    classifications = rsg._classification_lookup()
    sizing = pd.read_csv(rsg.SIZING_PATH, sep="\t", dtype=str).set_index("study_accession")
    rsg.FULLTEXT_CACHE.mkdir(parents=True, exist_ok=True)

    def evidence_for(acc: str) -> escalation.StudyEvidence:
        link = paper_links.get(acc, "")
        ft = rsg.fetch_fulltext(link, cache_dir=rsg.FULLTEXT_CACHE) if link else rsg.FullText("", "none", False, False, "")
        study = rsg.study_title_and_description(acc, cache_dir=rsg.ENA_CACHE)
        srow = sizing.loc[acc].to_dict() if acc in sizing.index else {}
        sizing_row = {
            "ena_taxon_samples": srow.get("ena_taxon_samples"),
            "ena_total_samples": srow.get("ena_total_samples"),
            "ena_total_runs": srow.get("ena_total_runs"),
            "by_scientific_name": srow.get("by_scientific_name"),
            **classifications.get(acc, {}),
        }
        return escalation.StudyEvidence(
            fulltext=ft,
            ena_title=study["study_title"],
            ena_description=study["study_description"],
            sizing_row=sizing_row,
        )

    return evidence_for


def _items_to_frame(items: list[escalation.EscalationItem]) -> pd.DataFrame:
    """Render escalation items to the queue TSV schema (empty answer columns for the curator)."""
    rows = [
        {
            "study_accession": it.study_accession, "field": it.field, "gap_samples": it.gap_samples,
            "resolution": it.resolution, "cluster_theme": it.cluster_theme,
            "suggested_value": it.suggested_value, "grader_quote": it.grader_quote,
            "paper_excerpt": it.paper_excerpt, "fulltext_status": it.fulltext_status,
            "answer": "", "answer_note": "",
        }
        for it in items
    ]
    return pd.DataFrame(rows, columns=QUEUE_COLUMNS)


def _detect(args: argparse.Namespace, folds: set[str], output: Path) -> pd.DataFrame:
    """Run the detector and write the decision queue; return the queue frame."""
    if args.accessions:
        keep = {a.strip() for a in args.accessions.split(",") if a.strip()}
    else:
        keep = _fold_studies(folds)
    grades = _load_grades(Path(args.grades), keep)
    raw = rbf._load_raw_ena(args.input)
    raw = raw[raw["study_accession"].isin(keep)].copy()
    covered = _methodb_covered(args.methodb, raw, args.methodb_frac)
    print(f"Scanning {len(grades)} graded studies / {len(raw)} ENA rows in {sorted(folds)} "
          f"(gap threshold {args.threshold}; {len(covered)} field(s) already resolved by method-b)", file=sys.stderr)

    spec = AttributeSpec.from_yaml(rsg.SPEC_PATH)
    llm = make_llm(args.backend, model=args.model, cache_dir=rsg.LLM_CACHE)
    items = escalation.detect_whole_field_escalations(
        grades, raw, spec, llm, _make_evidence_fn(folds),
        threshold=args.threshold, methodb_covered=covered, model=args.model,
    )
    frame = _items_to_frame(items)
    frame.to_csv(output, sep="\t", index=False)
    print(f"Wrote {output.name}: {len(frame)} escalation(s) "
          f"({int(frame['gap_samples'].sum()) if len(frame) else 0} gap samples)", file=sys.stderr)
    if len(frame):
        print("\nTop escalations (study · field · gap · suggested · theme):", file=sys.stderr)
        for _, r in frame.head(12).iterrows():
            print(f"  {r['study_accession']:<14} {r['field']:<16} {r['gap_samples']:>5}  "
                  f"→ {r['suggested_value'] or '(none)':<12} {r['cluster_theme'][:60]}", file=sys.stderr)
    return frame


def _interactive(frame: pd.DataFrame, output: Path) -> None:
    """Walk the queue at the prompt; Enter accepts the suggestion, 's' skips. Write answers back."""
    if not len(frame):
        print("No escalations to resolve.", file=sys.stderr)
        return
    print(f"\n{len(frame)} decision(s) — Enter accepts the suggested value, 's' skips, Ctrl-C stops.\n")
    for pos, (idx, r) in enumerate(frame.iterrows(), start=1):
        print("=" * 90)
        print(f"[{pos}/{len(frame)}] {r['study_accession']} · {r['field']} · gap {r['gap_samples']} samples "
              f"· {r['resolution']} · fulltext={r['fulltext_status']}")
        print(f"  cluster theme: {r['cluster_theme']}")
        print(f"  grader quote : {r['grader_quote']}")
        print(f"  paper excerpt: {r['paper_excerpt']}")
        print(f"  SUGGESTED    : {r['suggested_value'] or '(none)'}")
        try:
            ans = input("  your value [Enter=suggested, s=skip]: ").strip()
        except EOFError:
            print("\n(no interactive input available — stopping)", file=sys.stderr)
            break
        if ans.lower() == "s":
            continue
        frame.at[idx, "answer"] = ans or r["suggested_value"]
    frame.to_csv(output, sep="\t", index=False)
    filled = int((frame["answer"].astype(str).str.strip() != "").sum())
    print(f"\nWrote {output.name}: {filled}/{len(frame)} answered.", file=sys.stderr)


def _apply(args: argparse.Namespace, folds: set[str], queue_path: Path) -> None:
    """Apply the filled queue as whole-field curator fills through the existing backfill path."""
    if not queue_path.exists():
        sys.exit(f"Queue not found: {queue_path} (run detect/--interactive first, then fill the answer column).")
    queue = pd.read_csv(queue_path, sep="\t", dtype=str).fillna("")
    answered = queue[queue["answer"].astype(str).str.strip() != ""]
    if not len(answered):
        sys.exit(f"No filled answers in {queue_path.name}; nothing to apply.")

    keep = _fold_studies(folds)
    raw = rbf._load_raw_ena(args.input)
    raw = raw[raw["study_accession"].isin(keep)].copy()
    proposals = escalation.answers_to_proposals(answered.to_dict("records"))
    # Gate every answered field as "needs backfill" so the fill is never suppressed by ENA completeness:
    # a curator decision is authoritative regardless of how full ENA already is.
    fields = tuple(sorted({str(f) for f in answered["field"]}))
    studies = raw["study_accession"].unique()
    needs = pd.DataFrame(
        {f: [acc in proposals and f in proposals[acc] for acc in studies] for f in fields},
        index=pd.Index(studies, name="study_accession"),
    )
    applied = backfill.apply_whole_field(raw, proposals, needs, fields=fields)
    applied["method"] = "curator_escalation"
    applied.to_csv(args.applied_output, sep="\t", index=False)
    print(f"Wrote {Path(args.applied_output).name}: {len(applied)} per-sample fills "
          f"from {len(answered)} curator decision(s).", file=sys.stderr)
    if len(applied):
        print(f"\nFills by field:\n{applied['field'].value_counts().to_string()}", file=sys.stderr)


def main() -> None:
    """Parse arguments and dispatch to detect / interactive / apply."""
    p = argparse.ArgumentParser(description="Human-escalation tier for whole-field backfill (Klebsiella).")
    p.add_argument("--fold", default="train,val", help="Comma-separated folds (default train,val; test sealed).")
    p.add_argument("--accessions", default=None, help="Comma-separated accessions to scan (overrides --fold; for smoke tests).")
    p.add_argument("--grades", default=str(DATA_DIR / "study_grades.jsonl"), help="Grader JSONL (full records).")
    p.add_argument("--input", default=None, help="Explicit raw ENA per-sample TSV (else load_collated_metadata).")
    p.add_argument("--output", default=str(DATA_DIR / "decisions_needed.tsv"),
                   help="Queue TSV — written by detect/interactive, read by --apply.")
    p.add_argument("--applied-output", default=str(DATA_DIR / "escalation_applied.tsv"),
                   help="Per-sample changes file written by --apply.")
    p.add_argument("--threshold", type=int, default=50, help="Min blank-cell gap to escalate (default 50).")
    p.add_argument("--methodb", default=str(DATA_DIR / "methodb_applied.tsv"),
                   help="Method-b per-sample fills — fields it resolved are not escalated (method-b runs first).")
    p.add_argument("--methodb-frac", type=float, default=0.5,
                   help="Fraction of a field's gap method-b must fill to count it resolved (default 0.5).")
    p.add_argument("--interactive", action="store_true", help="Resolve the queue at the prompt after detecting.")
    p.add_argument("--apply", action="store_true", help="Apply a filled queue → escalation_applied.tsv.")
    p.add_argument(
        "--backend", choices=["subscription", "api"],
        default=os.environ.get("BAC_LLM_BACKEND", "subscription"),
        help="LLM backend for the justify step (default subscription).",
    )
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model id for the justify step (default {DEFAULT_MODEL}).")
    args = p.parse_args()
    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    output = Path(args.output)

    if args.apply:
        _apply(args, folds, output)
        return

    frame = _detect(args, folds, output)
    if args.interactive:
        _interactive(frame, output)


if __name__ == "__main__":
    main()
