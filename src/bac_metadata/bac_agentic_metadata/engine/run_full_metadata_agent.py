"""Unified entry point — run the whole agentic-metadata pipeline against one provided table.

A thin, application-agnostic orchestrator over the proven stage scripts. It ingests a single pre-built
per-sample table (the flat CSV/xlsx an application exports once), selects which studies to process — by
**curated split** *or* by **study-size band** — and runs the production stages in their proven order:

    find papers → study grading → per-sample extract (FIRST) → whole-field backfill
                 → escalation detect → run-health      (escalation + run-health best-effort)

Two selection modes (mutually exclusive):

* ``--splits SPLITS --fold F`` — process the curated fold(s); the stages read the curated sizing/split.
  This is the equivalence path (reproduces ``run_pipeline.sh``); pair with ``--paper-source curated``
  for the byte-identical regression gate.
* ``--min-study-size N [--max-study-size M]`` — process the **uncurated tail**: every study whose
  per-sample row count in ``--table`` falls in the band and is **not** in any curated fold. Study size
  is the distinct-sample row count in the table (no ENA API on the selection path). The driver writes a
  **batch-local** sizing + split pair (synthetic fold = ``--tag``) to a scratch dir and points the stages
  at them — the curated ``project_splits.tsv`` is **never** mutated.

Grading defaults to ``--paper-source finder`` (grade the paper the finder picked — the production
standard, so the numbers carry finder error); ``curated`` grades off the snapshot ``paper_link``.

The driver contains **no** per-application stage logic — it sequences the application's ``run_*`` stage
scripts (``--stage-dir``), so a new application supplies its own table + stage dir and reuses this driver.

Examples
--------
unset VIRTUAL_ENV
export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
# Smoke one uncurated study end-to-end:
uv run python .../engine/run_full_metadata_agent.py --table .../data/inputs/base_table.csv \
    --min-study-size 100 --max-study-size 110 --limit 1 --tag tail_smoke --web-fallback
# The full uncurated >100-sample tail:
uv run python .../engine/run_full_metadata_agent.py --table .../data/inputs/base_table.csv \
    --min-study-size 100 --tag tail100 --web-fallback
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

#: Synthetic non-study collections in the base table — never selected for the tail.
SYNTHETIC_STUDIES = {"Refseq_collection", "NCTC_collection"}

#: Full ena_sizing schema the find/grading stages read; the driver fills it with row-count proxies.
SIZING_COLUMNS = [
    "study_accession", "paper_short_title", "n_isolates", "fold", "seed", "ena_total_samples",
    "ena_total_runs", "ena_taxon_samples", "n_child_studies", "umbrella_suspected", "by_scientific_name",
    "fetch_status",
]
#: project_splits schema (study_accession -> fold) the backfill/per-sample/escalation stages read.
SPLIT_COLUMNS = ["study_accession", "paper_short_title", "n_isolates", "fold", "seed"]


def _study_sizes(table_path: Path) -> pd.Series:
    """Per-study distinct-sample count from the provided base table (the study-size proxy)."""
    df = pd.read_csv(table_path, dtype=str, low_memory=False)
    if "study_accession" not in df.columns:
        sys.exit(f"--table needs a study_accession column; got {list(df.columns)[:12]}")
    key = "sample_accession" if "sample_accession" in df.columns else None
    if key:
        df = df.drop_duplicates([key])
    return df.groupby("study_accession").size().sort_values(ascending=False)


def _curated_studies(splits_path: Path) -> set[str]:
    """Study accessions already in a curated fold (excluded from the uncurated tail)."""
    if not splits_path.exists():
        return set()
    return set(pd.read_csv(splits_path, sep="\t", dtype=str)["study_accession"])


def _select_size_band(sizes: pd.Series, *, lo: int, hi: int | None, exclude: set[str], limit: int | None) -> list[str]:
    """Uncurated studies whose size is in ``[lo, hi]`` and not already curated, biggest-first."""
    band = sizes[(sizes >= lo) & (sizes <= (hi if hi is not None else sizes.max()))]
    keep = [s for s in band.index if s not in exclude and s not in SYNTHETIC_STUDIES]
    if limit is not None:
        keep = keep[:limit]
    return keep


def _write_batch_sizing(studies: list[str], sizes: pd.Series, tag: str, out: Path) -> Path:
    """Write a batch-local ena_sizing TSV (row-count proxies, synthetic fold=tag) for the find/grade stages."""
    rows = []
    for acc in studies:
        n = int(sizes.get(acc, 0))
        rows.append({
            "study_accession": acc, "paper_short_title": "", "n_isolates": n, "fold": tag, "seed": "",
            "ena_total_samples": n, "ena_total_runs": "", "ena_taxon_samples": n, "n_child_studies": "",
            "umbrella_suspected": "", "by_scientific_name": "", "fetch_status": "proxy_rowcount",
        })
    df = pd.DataFrame(rows, columns=SIZING_COLUMNS)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, sep="\t", index=False)
    return out


def _write_batch_splits(studies: list[str], sizes: pd.Series, tag: str, out: Path) -> Path:
    """Write a batch-local project_splits TSV (synthetic fold=tag) for the backfill/per-sample/escalation stages."""
    rows = [{"study_accession": acc, "paper_short_title": "", "n_isolates": int(sizes.get(acc, 0)),
             "fold": tag, "seed": ""} for acc in studies]
    df = pd.DataFrame(rows, columns=SPLIT_COLUMNS)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, sep="\t", index=False)
    return out


def _run(label: str, argv: list[str], *, required: bool) -> bool:
    """Run one stage as a subprocess; return success. A ``required`` failure aborts the driver."""
    print(f"\n### [{label}] {' '.join(str(a) for a in argv)}", file=sys.stderr, flush=True)
    proc = subprocess.run([sys.executable, *[str(a) for a in argv]], check=False)
    if proc.returncode != 0:
        msg = f"STAGE FAILED ({label}): exit {proc.returncode}"
        if required:
            sys.exit(msg)
        print(f"WARN: {msg} (non-blocking)", file=sys.stderr)
        return False
    return True


def main() -> None:
    """Parse arguments, select studies, and orchestrate the full pipeline over the provided table."""
    p = argparse.ArgumentParser(description="Unified agentic-metadata pipeline over one provided table.")
    p.add_argument("--table", required=True, help="Pre-built per-sample base table (CSV/TSV/xlsx).")
    p.add_argument("--stage-dir", default=str(Path(__file__).resolve().parents[1] / "applications" / "klebsiella"),
                   help="Directory holding the application's run_* stage scripts (default the Klebsiella app).")
    p.add_argument("--tag", required=True, help="Run tag — names the synthetic fold and all output artifacts.")
    p.add_argument("--paper-source", choices=["finder", "curated"], default="finder",
                   help="Grade off the finder's pick (default, production standard) or the curated snapshot link.")
    # Selection — exactly one of the two modes.
    p.add_argument("--splits", default=None, help="Curated split TSV (with --fold: process curated fold(s)).")
    p.add_argument("--fold", default=None, help="Comma-separated curated fold(s) to process (splits mode).")
    p.add_argument("--min-study-size", type=int, default=None, help="Tail mode: min distinct-sample count (inclusive).")
    p.add_argument("--max-study-size", type=int, default=None, help="Tail mode: max distinct-sample count (inclusive).")
    p.add_argument("--exclude-splits", default=None,
                   help="Curated split to exclude in tail mode (default <stage-dir>/data/fold_splits/project_splits.tsv).")
    p.add_argument("--limit", type=int, default=None, help="Process only the first N selected studies (biggest-first).")
    p.add_argument("--scratch", default=None, help="Scratch dir for the batch-local sizing/split (default under data/cache).")
    p.add_argument("--web-fallback", action="store_true", help="Enable the finder's paid web-search fallback.")
    p.add_argument("--backend", choices=["subscription", "api"], default="subscription", help="LLM backend.")
    p.add_argument("--model", default=None, help="LLM model id (default: each stage's default).")
    p.add_argument("--skip-escalation", action="store_true", help="Skip the escalation-detect stage.")
    p.add_argument("--skip-run-health", action="store_true", help="Skip the run-health report.")
    args = p.parse_args()

    size_mode = args.min_study_size is not None or args.max_study_size is not None
    splits_mode = args.fold is not None
    if size_mode == splits_mode:
        sys.exit("Choose exactly one selection mode: --min-study-size/--max-study-size OR --splits + --fold.")

    stage = Path(args.stage_dir).resolve()
    data = stage / "data"
    find_dir = data / "find_papers"
    grade_dir = data / "study_lv_attributes" / "grading"
    wsb_dir = data / "study_lv_attributes" / "whole_study_backfill"
    esc_dir = data / "study_lv_attributes" / "escalation"
    ps_dir = data / "sample_lv_attributes" / "per_sample"
    for d in (find_dir, grade_dir, wsb_dir, esc_dir, ps_dir):
        d.mkdir(parents=True, exist_ok=True)
    model_args = ["--model", args.model] if args.model else []

    sizes = _study_sizes(Path(args.table))
    if size_mode:
        exclude_path = Path(args.exclude_splits) if args.exclude_splits else data / "fold_splits" / "project_splits.tsv"
        selected = _select_size_band(
            sizes, lo=args.min_study_size or 0, hi=args.max_study_size,
            exclude=_curated_studies(exclude_path), limit=args.limit,
        )
        if not selected:
            sys.exit("No uncurated studies match the size band — nothing to do.")
        scratch = Path(args.scratch) if args.scratch else data / "cache" / f"driver_{args.tag}"
        sizing_path = _write_batch_sizing(selected, sizes, args.tag, scratch / f"ena_sizing_{args.tag}.tsv")
        splits_path = _write_batch_splits(selected, sizes, args.tag, scratch / f"project_splits_{args.tag}.tsv")
        fold = args.tag
        total = int(sum(sizes.get(s, 0) for s in selected))
        print(f"=== driver: tail mode tag='{args.tag}' — {len(selected)} uncurated studies / {total} samples "
              f"(size band [{args.min_study_size or 0}, {args.max_study_size or '∞'}], biggest "
              f"{selected[0]}={int(sizes.get(selected[0], 0))}) ===", file=sys.stderr)
    else:
        splits_path = Path(args.splits).resolve() if args.splits else data / "fold_splits" / "project_splits.tsv"
        sizing_path = data / "ena_assessment" / "ena_sizing.tsv"  # curated sizing (stage default)
        fold = args.fold
        sel = pd.read_csv(splits_path, sep="\t", dtype=str)
        selected = list(sel[sel["fold"].isin(set(fold.split(",")))]["study_accession"])
        print(f"=== driver: splits mode fold='{fold}' tag='{args.tag}' — {len(selected)} curated studies "
              f"(paper-source={args.paper_source}) ===", file=sys.stderr)

    tag = args.tag
    found_tsv = find_dir / f"found_papers_{tag}.tsv"
    grades_tsv = grade_dir / f"study_grades_{tag}.tsv"
    grades_jsonl = grade_dir / f"study_grades_{tag}.jsonl"
    per_sample_tsv = ps_dir / f"per_sample_applied_{tag}.tsv"
    backfill_tsv = wsb_dir / f"backfill_applied_{tag}.tsv"
    common = ["--backend", args.backend, *model_args]

    # ── Stage 1 — find papers ───────────────────────────────────────────────────────────────────
    find_argv = [stage / "run_find_papers.py", "--fold", fold, "--sizing", sizing_path,
                 "--output-prefix", f"found_papers_{tag}", *common]
    if args.web_fallback:
        find_argv.append("--web-fallback")
    _run("find", find_argv, required=True)

    # ── Stage 2 — study grading (paper source per --paper-source) ────────────────────────────────
    _run("grade", [stage / "run_study_grading.py", "--fold", fold, "--sizing", sizing_path,
                   "--paper-source", args.paper_source, "--found", found_tsv,
                   "--output-prefix", f"study_grades_{tag}", *common], required=True)

    # ── Stage 3 — per-sample extraction FIRST (the accurate per-isolate source) ───────────────────
    _run("per-sample", [stage / "run_per_sample_extract.py", "--fold", fold, "--splits", splits_path,
                        "--found", found_tsv, "--output", per_sample_tsv, *common], required=True)

    # ── Stage 4 — whole-field backfill (coarse fallback for what per-sample left) ─────────────────
    _run("backfill", [stage / "run_backfill.py", "--fold", fold, "--splits", splits_path,
                      "--grades", grades_tsv, "--per-sample", per_sample_tsv,
                      "--output", backfill_tsv], required=True)

    # ── Stage 5 — escalation detect (best-effort; the curator-tier near-miss queue) ───────────────
    if not args.skip_escalation:
        _run("escalation", [stage / "run_escalations.py", "--fold", fold, "--accessions", ",".join(selected),
                            "--grades", grades_jsonl, "--per-sample", per_sample_tsv,
                            "--output", esc_dir / f"decisions_needed_{tag}.tsv", *common], required=False)

    # ── Stage 6 — run-health report (the convergence / closure artifact; best-effort) ─────────────
    if not args.skip_run_health:
        _run("run-health", [stage / "report_run_health.py", "--fold", fold, "--tag", tag], required=False)

    print(f"\n=== DRIVER COMPLETE (tag={tag}) ===", file=sys.stderr)
    print(f"found:      {found_tsv}", file=sys.stderr)
    print(f"grades:     {grades_tsv}", file=sys.stderr)
    print(f"per-sample: {per_sample_tsv}", file=sys.stderr)
    print(f"backfill:   {backfill_tsv}", file=sys.stderr)


if __name__ == "__main__":
    main()
