"""Unified entry point — run the whole agentic-metadata pipeline IN-PROCESS against one provided table.

A thin, application-agnostic orchestrator over the engine stages (``engine.stages``). It ingests a single
pre-built **full-width** per-sample table (the flat CSV/xlsx an application exports once), selects which
studies to process — by **curated split** *or* by **study-size band** — and calls the stage functions
in-process (no subprocess shell-out) in their proven order:

    find papers → study grading → per-sample extract (FIRST) → whole-field backfill
        → missing-papers worklist → per-sample-supplement worklist
        → escalation detect → escalation apply → fill metadata table → run-health

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

The driver contains **no** per-application stage logic. Everything application-specific arrives as data:
the rubric (``--spec``), the per-sample table (``--table``), the data tree (``--data-dir``), the curated
snapshot (``--snapshot``). A new application supplies those four and reuses this driver unchanged.

Examples
--------
unset VIRTUAL_ENV
export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
# Byte-identical regression gate (reproduces run_pipeline.sh "train,val" train):
uv run python .../engine/run_full_metadata_agent.py \
    --spec .../klebsiella/attributes.yaml --table .../klebsiella/data/inputs/base_table.csv \
    --data-dir .../klebsiella/data --splits .../klebsiella/data/fold_splits/project_splits.tsv \
    --sizing .../klebsiella/data/ena_assessment/ena_sizing.tsv \
    --snapshot .../klebsiella/data/inputs/study_level_metadata_all_combined_v1.0_20260105.csv \
    --fold train,val --tag train --paper-source curated
# The full uncurated >100-sample tail:
uv run python .../engine/run_full_metadata_agent.py \
    --spec .../klebsiella/attributes.yaml --table .../klebsiella/data/inputs/base_table.csv \
    --data-dir .../klebsiella/data --min-study-size 100 --tag tail100 --web-fallback
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
from bac_metadata.bac_agentic_metadata.engine import stages
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, make_llm
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

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


def _classification_lookup(report_path: Path) -> dict[str, dict]:
    """Optional per-accession classification/coverage from an ENA assessment report (absent → empty).

    Generic: reads whatever ``classification`` / ``coverage`` columns the report holds, keyed by
    ``study_accession``. The uncurated tail has no assessment report, so this is simply empty there.
    """
    if not report_path or not report_path.exists():
        return {}
    vdf = pd.read_csv(report_path, sep="\t", dtype=str)
    key = "study_accession" if "study_accession" in vdf.columns else vdf.columns[0]
    cols = [c for c in ("classification", "coverage") if c in vdf.columns]
    return {r[key]: {c: r[c] for c in cols} for _, r in vdf.iterrows()}


def main() -> None:
    """Parse arguments, select studies, and orchestrate the full pipeline in-process over the table."""
    p = argparse.ArgumentParser(description="Unified agentic-metadata pipeline (in-process) over one table.")
    p.add_argument("--spec", required=True, help="Application attributes.yaml (the rubric).")
    p.add_argument("--table", required=True, help="Pre-built FULL-WIDTH per-sample base table (CSV/TSV).")
    p.add_argument("--data-dir", required=True, help="Application data tree root (holds find_papers/, cache/, …).")
    p.add_argument("--tag", required=True, help="Run tag — names the synthetic fold and all output artifacts.")
    p.add_argument("--snapshot", default=None,
                   help="Curated study-level snapshot CSV (source of paper_link for --paper-source curated).")
    p.add_argument("--paper-source", choices=["finder", "curated"], default="finder",
                   help="Grade off the finder's pick (default, production standard) or the curated snapshot link.")
    p.add_argument("--classifications", default=None,
                   help="ENA assessment report TSV for per-study classification/coverage "
                        "(default <data-dir>/ena_assessment/ena_assessment_report.tsv; absent → none).")
    p.add_argument("--manual-curation", default=None,
                   help="Manual-curation TSV. Recorded for the evaluation layer (run_folds.sh runs the "
                        "agreement comparison when present); the driver itself does not score.")
    # Selection — exactly one of the two modes.
    p.add_argument("--splits", default=None, help="Curated split TSV (with --fold: process curated fold(s)).")
    p.add_argument("--fold", default=None, help="Comma-separated curated fold(s) to process (splits mode).")
    p.add_argument("--sizing", default=None,
                   help="Curated ena_sizing TSV (splits mode; default <data-dir>/ena_assessment/ena_sizing.tsv).")
    p.add_argument("--min-study-size", type=int, default=None, help="Tail mode: min distinct-sample count (inclusive).")
    p.add_argument("--max-study-size", type=int, default=None, help="Tail mode: max distinct-sample count (inclusive).")
    p.add_argument("--exclude-splits", default=None,
                   help="Curated split to exclude in tail mode (default <data-dir>/fold_splits/project_splits.tsv).")
    p.add_argument("--limit", type=int, default=None, help="Process only the first N selected studies (biggest-first).")
    p.add_argument("--scratch", default=None, help="Scratch dir for the batch-local sizing/split (default under data/cache).")
    p.add_argument("--web-fallback", action="store_true", help="Enable the finder's paid web-search fallback.")
    p.add_argument("--backend", choices=["subscription", "api"], default="subscription", help="LLM backend.")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model id (default {DEFAULT_MODEL}).")
    p.add_argument("--grade-workers", type=int, default=1,
                   help="Concurrent grading workers (default 1 = sequential, light on a shared Claude Pro "
                        "window). Raise it (e.g. 4-8) for a faster run when you are not using the account for "
                        "other work; the grades output is identical regardless of the worker count.")
    p.add_argument("--find-workers", type=int, default=None,
                   help="Concurrent paper-finding workers (default: match --grade-workers). find is the slow "
                        "sequential leg (one LLM paper-pick per study); this fans it across a thread pool the "
                        "same way grading is. Output is identical regardless of the worker count.")
    p.add_argument("--grade-skip-existing", action="store_true",
                   help="Keep studies already present in study_grades_<tag>.jsonl exactly as graded and grade "
                        "only the rest (usage-saving resume after a ladder/rubric tweak you don't want to "
                        "re-spend on). Without it, a re-run regrades all (cheap via cache when unchanged).")
    p.add_argument("--threshold", type=float, default=None,
                   help="ENA non-null fraction at/above which a field is complete. Overrides the spec's "
                        "gates.completeness_threshold; when omitted the spec value is used.")
    p.add_argument("--skip-find", action="store_true",
                   help="Skip the paper-finding stage and reuse the existing found_papers_<tag>.tsv (which must "
                        "already exist). Intended for --paper-source curated, where grading uses the curated "
                        "snapshot's links and the finder output is only a downstream input, not regenerated.")
    p.add_argument("--skip-escalation", action="store_true", help="Skip the escalation detect/apply stages.")
    p.add_argument("--skip-per-sample", action="store_true",
                   help="Skip the per-sample supplementary-table extraction (the expensive LLM per-isolate "
                        "stage) + its worklist; emit empty per-sample artifacts. Grade + whole-field backfill "
                        "+ fill still run — a cheap 'study_type + whole-field only' pass (e.g. the sub-10 tail).")
    p.add_argument("--skip-run-health", action="store_true", help="Skip the run-health report.")
    p.add_argument("--carry-forward", action="store_true",
                   help="Build-it-up mode: overlay prior curation (data-dir/curated/) onto the base so the "
                        "agent only works still-blank cells, and never re-ask an escalation decided earlier.")
    args = p.parse_args()

    size_mode = args.min_study_size is not None or args.max_study_size is not None
    splits_mode = args.fold is not None
    if size_mode == splits_mode:
        sys.exit("Choose exactly one selection mode: --min-study-size/--max-study-size OR --splits + --fold.")
    if args.paper_source == "curated" and not args.snapshot:
        sys.exit("--paper-source curated needs --snapshot (the curated study-level CSV with paper_link).")

    data = Path(args.data_dir).resolve()
    # RunPaths is the single path authority — every per-tranche artifact lives under
    # data/run_progress/<tag>/<stage>/ (auditable per tranche); shared curator/input dirs stay at data root.
    rp = RunPaths(data, args.tag).ensure()
    find_dir = rp.find_dir
    manual_papers_dir = rp.manual_papers_dir
    # The single, version-controlled home for curator-provided per-isolate tables (see its README). Tracked in
    # git precisely so a hand-provided table can never be silently lost — the failure that dropped PRJEB28400's
    # table in the OneDrive→developer migration. Auto-read every run; no separate wiring step. (Shared, root-level.)
    manual_supp_dir = rp.manual_supp_dir
    manual_papers_dir.mkdir(parents=True, exist_ok=True)
    manual_supp_dir.mkdir(parents=True, exist_ok=True)

    caches = stages.StageCaches(
        llm=data / "cache" / "llm", ena=data / "cache" / "ena", find=data / "cache" / "find",
        fulltext=data / "cache" / "fulltext", per_sample_supp=data / "cache" / "per_sample_supp",
    )
    caches.ensure()

    spec = AttributeSpec.from_yaml(args.spec)
    fields = list(spec.completeness_fields)
    # Application pipeline gates come from the spec's `gates` section (the yaml is the constants file); a CLI
    # --threshold, if given, overrides only the completeness gate for an ad-hoc run.
    completeness_threshold = args.threshold if args.threshold is not None else spec.completeness_threshold
    # Controlled-vocabulary summaries grounding the per-sample rescue cascade (Tier 2, no paper). Built from
    # the approved categorise yamls; absent files (a new application, or country/date which have none) are
    # simply omitted — the rescue then leans on the built-in per-field value guide.
    category_vocab = sx.load_category_vocabs(data / "study_lv_attributes" / "categorisation", fields)
    # Optional AST panel (M. abscessus): the extractor mines per-isolate susceptibility into ast_<drug>_*
    # long-format fills. Absent for Klebsiella (spec has no ast_panel) -> None -> extractor unchanged.
    ast_panel = spec.raw.get("attributes", {}).get("per_sample_completeness", {}).get("ast_panel") or {}
    ast_drugs = list(ast_panel.get("drugs", [])) or None
    tag = args.tag

    sizes = _study_sizes(Path(args.table))
    if size_mode:
        exclude_path = Path(args.exclude_splits) if args.exclude_splits else data / "fold_splits" / "project_splits.tsv"
        selected = _select_size_band(
            sizes, lo=args.min_study_size or 0, hi=args.max_study_size,
            exclude=_curated_studies(exclude_path), limit=args.limit,
        )
        if not selected:
            sys.exit("No uncurated studies match the size band — nothing to do.")
        sel_dir = Path(args.scratch) if args.scratch else rp.selection_dir
        sel_dir.mkdir(parents=True, exist_ok=True)
        sizing_path = _write_batch_sizing(selected, sizes, tag, sel_dir / "ena_sizing.tsv")
        _write_batch_splits(selected, sizes, tag, sel_dir / "project_splits.tsv")
        fold = tag
        classifications: dict[str, dict] = {}
        total = int(sum(sizes.get(s, 0) for s in selected))
        print(f"=== driver: tail mode tag='{tag}' — {len(selected)} uncurated studies / {total} samples "
              f"(size band [{args.min_study_size or 0}, {args.max_study_size or '∞'}], biggest "
              f"{selected[0]}={int(sizes.get(selected[0], 0))}) ===", file=sys.stderr)
    else:
        splits_path = Path(args.splits).resolve() if args.splits else data / "fold_splits" / "project_splits.tsv"
        sizing_path = Path(args.sizing) if args.sizing else data / "ena_assessment" / "ena_sizing.tsv"
        fold = args.fold
        sel = pd.read_csv(splits_path, sep="\t", dtype=str)
        selected = list(sel[sel["fold"].isin(set(fold.split(",")))]["study_accession"])
        report = Path(args.classifications) if args.classifications else data / "ena_assessment" / "ena_assessment_report.tsv"
        classifications = _classification_lookup(report)
        print(f"=== driver: splits mode fold='{fold}' tag='{tag}' — {len(selected)} curated studies "
              f"(paper-source={args.paper_source}) ===", file=sys.stderr)

    folds = [f.strip() for f in fold.split(",") if f.strip()]
    found_jsonl = rp.found_papers_jsonl
    found_tsv = rp.found_papers_tsv
    grades_jsonl = rp.study_grades_jsonl
    grades_tsv = rp.study_grades_tsv
    per_sample_tsv = rp.per_sample_applied
    backfill_tsv = rp.backfill_applied
    gate_report_tsv = rp.backfill_gate_report
    decisions_tsv = rp.decisions_needed
    escalation_applied_tsv = rp.escalation_applied
    filled_tsv = rp.filled_metadata

    # The full-width base table, restricted to the selection — the substrate every per-sample stage reads.
    # keep_default_na=False preserves literal placeholder strings (e.g. ENA's "NA") exactly as the
    # in-memory collation base holds them, so apply_whole_field records the original value byte-for-byte.
    base_full = pd.read_csv(args.table, dtype=str, low_memory=False, keep_default_na=False)
    if "study_accession" not in base_full.columns or "sample_accession" not in base_full.columns:
        sys.exit(f"--table needs study_accession + sample_accession; got {list(base_full.columns)[:12]}")
    # Guard against a stale/slim base table silently crippling per-sample extraction (2026-07-01). The
    # per-sample anchorer (sample_extractor.build_accession_to_sample) matches supplementary-table rows to
    # samples by the strain names carried in these ENA columns; a base missing them can only anchor by
    # sample_accession and silently under-extracts strain-keyed studies. Fail loud, don't limp along.
    # (Step 3 / M. abscessus: make the required anchor columns spec-driven — its xlsx base names differ.)
    anchor_cols = ("secondary_sample_accession", "accession", "sample_alias", "sample_title")
    missing_anchor = [c for c in anchor_cols if c not in base_full.columns]
    if missing_anchor:
        sys.exit(
            f"Base table {args.table} is missing per-sample anchoring column(s) {missing_anchor} — it looks "
            "like a stale/slim export. Per-sample extraction anchors supplementary tables on these (strain "
            "names live in sample_alias/sample_title). Re-export the full-width base:\n"
            "  uv run python .../applications/<app>/export_base_table.py --output <the --table path>"
        )
    base = base_full[base_full["study_accession"].isin(set(selected))].copy()
    print(f"Base (selection): {len(base)} samples across {base['study_accession'].nunique()} studies "
          f"({len(base.columns)} columns)", file=sys.stderr)

    # Pre-clean: wipe field-specific null tokens (attributes.yaml `categorisation.*.null_tokens`) to
    # blank IN-MEMORY, so the fill agent gets a chance to recover them. Base on disk stays verbatim.
    from bac_metadata.bac_agentic_metadata.engine.categorise.preclean import preclean_base
    base, precleaned = preclean_base(base, spec)
    if precleaned:
        summary = {f: sum(vals.values()) for f, vals in precleaned.items()}
        print(f"[preclean] blanked field-specific null tokens/patterns: {summary}", file=sys.stderr)
        for f, vals in precleaned.items():
            top = sorted(vals.items(), key=lambda kv: -kv[1])[:8]
            print(f"[preclean]   {f}: " + ", ".join(f"{v!r}×{c}" for v, c in top)
                  + (f" (+{len(vals) - 8} more)" if len(vals) > 8 else ""), file=sys.stderr)
    # Persist the drop summary so run-health can self-audit "meaningless data dropped" on ANY run (incl.
    # unlabelled / no-gold): field × dropped-value × cell-count. Always written (empty header if nothing
    # dropped) so "ran, dropped 0" is distinguishable from "step never ran".
    preclean_path = rp.preclean_summary
    preclean_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"field": f, "dropped_value": v, "n_cells": c}
         for f, vals in (precleaned or {}).items()
         for v, c in sorted(vals.items(), key=lambda kv: -kv[1])],
        columns=["field", "dropped_value", "n_cells"],
    ).to_csv(preclean_path, sep="\t", index=False)

    # Whole-cohort taxon counts for the big-decision leverage gate (>=1% of the WHOLE cohort, never the
    # batch). Computed over the FULL base (all studies) via the spec's taxon match — the batch-local sizing
    # would otherwise make every >~1%-of-batch study look "big". None if the base lacks scientific_name.
    cohort_taxon_samples = cohort_taxon_total = None
    taxon_match = spec.raw.get("taxon_of_interest", {}).get("scientific_name_match", [])
    if taxon_match and "scientific_name" in base_full.columns:
        is_taxon = base_full["scientific_name"].str.contains("|".join(taxon_match), case=False, na=False, regex=True)
        counts = base_full[is_taxon].groupby("study_accession").size()
        cohort_taxon_samples, cohort_taxon_total = counts.to_dict(), int(counts.sum())
        print(f"Big-decision gate: whole-cohort taxon total {cohort_taxon_total} "
              f"(>=1% = {cohort_taxon_total // 100} taxon samples)", file=sys.stderr)

    if args.carry_forward:  # feed-forward: pre-fill blanks from prior curation so curated cells aren't re-worked
        cf = Path(args.data_dir) / "curated" / "curated_fills.tsv"
        if cf.exists():
            from bac_metadata.bac_agentic_metadata.engine.accumulate import overlay_master_on_base
            prior = pd.read_csv(cf, sep="\t", dtype=str, keep_default_na=False)
            base = overlay_master_on_base(base, prior, fields)
            print(f"[carry-forward] overlaid prior curation from {cf.name} onto base blanks", file=sys.stderr)
        else:
            print(f"[carry-forward] no {cf} yet — first batch, nothing to overlay", file=sys.stderr)

    llm = make_llm(args.backend, model=args.model, cache_dir=caches.llm)

    # ── Stage 1 — find papers ─────────────────────────────────────────────────────────────────────
    if args.skip_find:
        if not Path(found_tsv).exists():
            sys.exit(f"--skip-find given but {found_tsv} does not exist — run find first (or drop --skip-find).")
        print(f"\n### [find] SKIPPED (--skip-find) — reusing {Path(found_tsv).name}", file=sys.stderr)
    else:
        print(f"\n### [find] {len(selected)} studies", file=sys.stderr)
        stages.find_papers(
            spec=spec, sizing_path=sizing_path, folds=folds, out_jsonl=found_jsonl, out_tsv=found_tsv,
            llm=llm, model=args.model, caches=caches, web_fallback=args.web_fallback, limit=args.limit,
            workers=(args.find_workers if args.find_workers is not None else args.grade_workers),
        )

    # ── Stage 2 — study grading (paper source per --paper-source) ─────────────────────────────────
    paper_links = (stages.finder_paper_links(found_tsv) if args.paper_source == "finder"
                   else stages.curated_paper_links(args.snapshot))
    print("\n### [grade]", file=sys.stderr)
    stages.grade(
        spec=spec, sizing_path=sizing_path, folds=folds, paper_links=paper_links,
        classifications=classifications, manual_papers_dir=manual_papers_dir,
        out_jsonl=grades_jsonl, out_tsv=grades_tsv, llm=llm, model=args.model, caches=caches,
        context_tiers=spec.grade_context_tiers, workers=args.grade_workers,
        skip_existing=args.grade_skip_existing, limit=args.limit,
    )

    # ── Stage 3 — per-sample extraction FIRST (the accurate per-isolate source) ────────────────────
    print("\n### [per-sample]", file=sys.stderr)
    if args.skip_per_sample:
        # Emit empty per-sample artifacts (correct headers) so backfill/fill/run-health read them cleanly;
        # whole-field backfill + fill still run. The one-place headers mirror stages.per_sample's writes.
        print("[per-sample] SKIPPED (--skip-per-sample) — writing empty artifacts", file=sys.stderr)
        outcomes_tsv = per_sample_tsv.with_name(per_sample_tsv.name.replace("per_sample_applied", "per_sample_outcomes"))
        pd.DataFrame(columns=["study_accession", "sample_accession", "field", "ena_value",
                              "applied_value", "method", "evidence"]).to_csv(per_sample_tsv, sep="\t", index=False)
        pd.DataFrame(columns=["study_accession", "pmcid", "table", "method",
                              "n_samples", "n_fills", "confidence", "note"]).to_csv(outcomes_tsv, sep="\t", index=False)
    else:
        stages.per_sample(
            base=base, found_path=found_tsv, fields=fields, accessions=None, out_path=per_sample_tsv,
            manual_supp_dir=manual_supp_dir, llm=llm, model=args.model, caches=caches, threshold=completeness_threshold,
            ast_drugs=ast_drugs, id_columns=list(spec.sample_identifier_columns) or None,
            manual_papers_dir=manual_papers_dir, category_vocab=category_vocab, paper_links=paper_links,
        )

    # ── Stage 4 — whole-field backfill (coarse fallback for what per-sample left) ──────────────────
    print("\n### [backfill]", file=sys.stderr)
    stages.backfill_whole_field(
        base=base, grades_path=grades_tsv, per_sample_path=per_sample_tsv, fields=fields,
        out_path=backfill_tsv, threshold=completeness_threshold,
    )

    # ── Stage 5 — missing-papers worklist (the manual-fetch loop; best-effort) ─────────────────────
    try:
        stages.missing_papers(
            grades_jsonl=grades_jsonl, found_path=found_tsv, gap_report_path=gate_report_tsv,
            sizing_path=Path(sizing_path), manual_papers_dir=manual_papers_dir, out_dir=find_dir,
            paper_links=paper_links, report_prefix=RunPaths.MISSING_PAPERS_PREFIX,
        )
    except Exception as exc:  # noqa: BLE001 — a worklist failure must not kill the run
        print(f"WARN: missing-papers worklist failed (non-blocking): {type(exc).__name__}: {exc}", file=sys.stderr)

    # ── Stage 6 — per-sample supplementary worklist (the manual-table curator queue; best-effort) ──
    if not args.skip_per_sample:
        try:
            stages.persample_supplement(
                data_dir=data, paper_links=paper_links, caches=caches, manual_papers_dir=manual_papers_dir,
                fields=fields, tag=tag, backend=args.backend, model=args.model,
            )
        except Exception as exc:  # noqa: BLE001 — non-blocking worklist
            print(f"WARN: per-sample supplement worklist failed (non-blocking): {type(exc).__name__}: {exc}", file=sys.stderr)

    # ── Stage 7 — escalation detect → apply (best-effort; the curator-tier near-miss queue) ────────
    if not args.skip_escalation:
        try:
            # ALWAYS consult the version-controlled escalations master (not just under --carry-forward): its
            # answers are the precious, non-regenerable curator input, re-applied to any still-gated study so
            # a committed decision is never silently dropped when its detection trigger stops firing.
            esc_master = Path(args.data_dir) / "curated" / "curated_escalations.tsv"
            stages.escalate_detect(
                spec=spec, base=base, keep=selected, grades_jsonl=grades_jsonl,
                per_sample_path=per_sample_tsv, sizing_path=sizing_path, paper_links=paper_links,
                classifications=classifications, manual_papers_dir=manual_papers_dir, fields=fields,
                out_path=decisions_tsv, llm=llm, model=args.model, caches=caches,
                escalations_master_path=esc_master,
                threshold=spec.escalation_residual_floor, frac=completeness_threshold,
                big_decision_frac=spec.escalation_big_decision_frac,
                auto_skip_wide=spec.auto_skip_wide_mix,
                cohort_taxon_samples=cohort_taxon_samples, cohort_taxon_total=cohort_taxon_total,
            )
            stages.escalate_apply(base=base, keep=selected, queue_path=decisions_tsv,
                                  out_path=escalation_applied_tsv)
        except Exception as exc:  # noqa: BLE001 — escalation is best-effort
            print(f"WARN: escalation failed (non-blocking): {type(exc).__name__}: {exc}", file=sys.stderr)

    # ── Stage 8 — fill the metadata table (PRODUCTION output) ──────────────────────────────────────
    # One fill code path (stages.fill_for_tag) shared with `escalate --apply` and `cli.fill`, so a curator
    # answer can never be applied without the final table being rebuilt to fold it in.
    print("\n### [fill-metadata-table]", file=sys.stderr)
    stages.fill_for_tag(data_dir=data, spec=spec, base=base, fields=fields, tag=tag, fold_label=fold)

    # ── Stage 9 — run-health report (the convergence / closure artifact; best-effort) ──────────────
    if not args.skip_run_health:
        try:
            stages.run_health(data_dir=data, fields=fields, fold=fold, tag=tag, spec=spec)
        except Exception as exc:  # noqa: BLE001 — run-health never blocks
            print(f"WARN: run-health report failed (non-blocking): {type(exc).__name__}: {exc}", file=sys.stderr)

    # ── Stage 10 — escalation-conservation gate (always-on, loud WARN, never blocks) ───────────────
    # Content-based: every applied escalation value must appear non-blank in the final table. Because it is
    # rebuilt every pass (stage 8) this is normally green — but it stays as the loud backstop that makes any
    # future stale-final regression impossible to miss. On PASS it stamps the VERIFIED block into run-health.
    try:
        from bac_metadata.bac_agentic_metadata.engine import escalation_conservation as ec
        cons_fails = ec.verify_tags(data, [tag], amend=True, include_master=True)
        if cons_fails:
            print(f"\n⛔⛔ WARN: escalation-conservation gate FAILED for tag={tag} "
                  f"({len(cons_fails)} issue(s)) — a curator answer did not reach the final table:",
                  file=sys.stderr)
            for f in cons_fails:
                print(f"   ⛔ {f}", file=sys.stderr)
            print("   The final table may be stale. Re-run fill (cli.fill) / accumulate, then "
                  "verify_escalation_conservation.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — the gate is a backstop, never blocks the run
        print(f"WARN: escalation-conservation gate errored (non-blocking): {type(exc).__name__}: {exc}",
              file=sys.stderr)

    print(f"\n=== DRIVER COMPLETE (tag={tag}) ===", file=sys.stderr)
    print(f"found:      {found_tsv}", file=sys.stderr)
    print(f"grades:     {grades_tsv}", file=sys.stderr)
    print(f"per-sample: {per_sample_tsv}", file=sys.stderr)
    print(f"backfill:   {backfill_tsv}", file=sys.stderr)
    print(f"filled:     {filled_tsv}", file=sys.stderr)
    if args.manual_curation:
        print(f"manual-curation supplied ({args.manual_curation}); run evaluation/run_folds.sh to score "
              "agent-vs-manual agreement.", file=sys.stderr)


if __name__ == "__main__":
    main()
