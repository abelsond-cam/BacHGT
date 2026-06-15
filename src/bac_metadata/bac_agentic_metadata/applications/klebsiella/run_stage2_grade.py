"""Stage 2A runner (Klebsiella) — grade the *known* curated papers against the rubric.

For each project accession in the chosen fold(s) this:

1. looks up the curated ``paper_link`` from the frozen study-level snapshot,
2. resolves it to text via Europe PMC / abstract / PDF (``engine.fulltext``),
3. fetches the EBI study title + description (``engine.ena_sizing``),
4. grades it against ``attributes.yaml`` with the LLM (``engine.grader``),

and writes ``data/stage2_grades.{jsonl,tsv}``. Accessions are processed **biggest-first**
(by Stage-1 ``ena_taxon_samples``). All network + LLM responses are cached on disk, so reruns
are deterministic and offline.

Grading-first (2A) deliberately uses the curated paper link as ground-truth input so we measure
the *grading* step in isolation; independent paper-finding is Stage 2B.

Examples
--------
unset VIRTUAL_ENV
# Dry run on three contrasting accessions:
uv run python .../run_stage2_grade.py --accessions PRJEB10018,PRJEB58216,PRJDB10842 \
    --output-prefix stage2_grades_dryrun
# Full train+val pass:
uv run python .../run_stage2_grade.py --fold train,val
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import grader
from bac_metadata.bac_agentic_metadata.engine.ena_sizing import study_title_and_description
from bac_metadata.bac_agentic_metadata.engine.fulltext import FullText, fetch_fulltext
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, UsageLimitError, make_llm
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPEC_PATH = APP_DIR / "attributes.yaml"
SIZING_PATH = DATA_DIR / "stage1_sizing.tsv"
VALIDATION_PATH = DATA_DIR / "stage1_validation_report.tsv"
SNAPSHOT_PATH = DATA_DIR / "study_level_metadata_all_combined_v1.0_20260105.csv"
ENA_CACHE = DATA_DIR / "ena_cache"
FULLTEXT_CACHE = DATA_DIR / "fulltext_cache"
LLM_CACHE = DATA_DIR / "llm_cache"

_URL_RE = re.compile(r"https?://\S+")


def _accession_to_paper_link() -> dict[str, str]:
    """Map each study accession to its first curated ``paper_link`` from the frozen snapshot.

    ``study_accessions`` may list several comma-separated accessions per row, and ``paper_link``
    may hold several URLs; we take the first URL and attach it to each accession on the row.
    """
    df = pd.read_csv(SNAPSHOT_PATH, dtype=str).fillna("")
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        link = row.get("paper_link", "").strip()
        m = _URL_RE.search(link)
        first = m.group(0).rstrip(").,") if m else link
        if not first:
            continue
        for acc in re.split(r"[,\s]+", row.get("study_accessions", "")):
            acc = acc.strip()
            if acc and acc not in mapping:
                mapping[acc] = first
    return mapping


def _select_accessions(args: argparse.Namespace) -> pd.DataFrame:
    """Return the Stage-1 sizing rows to grade (by --accessions or --fold), biggest-first."""
    sizing = pd.read_csv(SIZING_PATH, sep="\t")
    if args.accessions:
        wanted = [a.strip() for a in args.accessions.split(",") if a.strip()]
        sel = sizing[sizing["study_accession"].isin(wanted)].copy()
    else:
        folds = {f.strip() for f in args.fold.split(",") if f.strip()}
        sel = sizing[sizing["fold"].isin(folds)].copy()
    sel["ena_taxon_samples"] = pd.to_numeric(sel["ena_taxon_samples"], errors="coerce").fillna(0)
    sel = sel.sort_values("ena_taxon_samples", ascending=False)
    if args.limit is not None:
        sel = sel.head(args.limit)
    return sel


def _classification_lookup() -> dict[str, dict]:
    """Optional per-accession classification/coverage from the Stage-1 validation report."""
    if not VALIDATION_PATH.exists():
        return {}
    vdf = pd.read_csv(VALIDATION_PATH, sep="\t", dtype=str)
    key = "study_accession" if "study_accession" in vdf.columns else vdf.columns[0]
    out: dict[str, dict] = {}
    for _, r in vdf.iterrows():
        out[r[key]] = {k: r[k] for k in ("classification", "coverage") if k in vdf.columns}
    return out


def main() -> None:
    """Parse arguments and run Stage 2A grading."""
    parser = argparse.ArgumentParser(description="Stage 2A — grade curated papers (Klebsiella).")
    parser.add_argument("--fold", default="train,val", help="Comma-separated folds (default train,val).")
    parser.add_argument("--accessions", default=None, help="Comma-separated accessions (overrides --fold).")
    parser.add_argument("--limit", type=int, default=None, help="Grade only the first N (biggest-first).")
    parser.add_argument(
        "--backend",
        choices=["subscription", "api"],
        default=os.environ.get("BAC_LLM_BACKEND", "subscription"),
        help="LLM backend: 'subscription' (claude -p, zero API spend; default) or 'api' (paid key).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model id (default {DEFAULT_MODEL}).")
    parser.add_argument("--cache-dir", type=Path, default=LLM_CACHE, help="LLM response cache dir.")
    parser.add_argument("--output-prefix", default="stage2_grades", help="Output basename under data/.")
    parser.add_argument("--max-chars", type=int, default=grader.DEFAULT_MAX_CHARS, help="Paper-text truncation.")
    args = parser.parse_args()

    spec = AttributeSpec.from_yaml(SPEC_PATH)
    paper_links = _accession_to_paper_link()
    classifications = _classification_lookup()
    sel = _select_accessions(args)
    print(f"Grading {len(sel)} accessions with {args.model} (backend={args.backend})", file=sys.stderr)

    llm = make_llm(args.backend, model=args.model, cache_dir=args.cache_dir)
    FULLTEXT_CACHE.mkdir(parents=True, exist_ok=True)

    results: list[grader.GradeResult] = []
    limited = False
    for i, (_, row) in enumerate(sel.iterrows(), start=1):
        acc = row["study_accession"]
        link = paper_links.get(acc, "")
        taxon_n = int(row["ena_taxon_samples"]) if pd.notna(row["ena_taxon_samples"]) else None
        print(f"[grade {i}/{len(sel)}] {acc} (taxon={taxon_n}) <- {link[:70] or '(no paper link)'}", file=sys.stderr)

        ft = fetch_fulltext(link, cache_dir=FULLTEXT_CACHE) if link else FullText("", "none", False, False, "")
        study = study_title_and_description(acc, cache_dir=ENA_CACHE)
        sizing_row = {
            "ena_taxon_samples": taxon_n,
            "ena_total_samples": row.get("ena_total_samples"),
            "ena_total_runs": row.get("ena_total_runs"),
            "by_scientific_name": row.get("by_scientific_name"),
            **classifications.get(acc, {}),
        }
        try:
            result = grader.grade_accession(
                spec,
                llm,
                accession=acc,
                fulltext=ft,
                ena_title=study["study_title"],
                ena_description=study["study_description"],
                ena_taxon_samples=taxon_n,
                sizing_row=sizing_row,
                model=args.model,
                max_chars=args.max_chars,
            )
        except UsageLimitError as exc:
            # Stop cleanly: keep what we have (cached), report how to resume. No work lost.
            print(f"\n[usage limit] {exc}", file=sys.stderr)
            print(f"Graded {len(results)}/{len(sel)} before the window was exhausted. "
                  "Rerun the same command later to resume — cached grades return instantly.", file=sys.stderr)
            limited = True
            break
        results.append(result)

    jsonl = DATA_DIR / f"{args.output_prefix}.jsonl"
    tsv = DATA_DIR / f"{args.output_prefix}.tsv"
    grader.write_results(results, jsonl, tsv)
    status = "partial (usage limit)" if limited else "complete"
    print(f"Wrote {jsonl} and {tsv} ({len(results)} rows, {status})", file=sys.stderr)


if __name__ == "__main__":
    main()
