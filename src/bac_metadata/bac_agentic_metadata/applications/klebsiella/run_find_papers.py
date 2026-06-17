"""Stage 2B runner (Klebsiella) — find the describing paper for each project accession.

For each accession in the chosen fold(s) this: fetches the ENA study title + description, gathers
candidate papers from the four retrieval channels (ENA-description mining, NCBI BioProject links,
Europe PMC accession text-mining + title search), has the LLM pick the describing paper (confined
to retrieved candidates — no invented ids), grounds the pick by confirming the accession appears
in the paper, and abstains when unverified + low-confidence. Writes ``data/found_papers.{jsonl,tsv}``.

The curated ``paper_link`` is NOT used here — that is the held-out ground truth for
``validate_find_papers.py``. Processed biggest-first; all network + LLM responses are cached.

Examples
--------
unset VIRTUAL_ENV
uv run python .../run_find_papers.py --accessions PRJDB10842,PRJEB10018,PRJNA339843 --output-prefix found_papers_dryrun
uv run python .../run_find_papers.py --fold train,val
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import paper_finder
from bac_metadata.bac_agentic_metadata.engine.ena_sizing import study_aliases, study_title_and_description
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, UsageLimitError, make_llm
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPEC_PATH = APP_DIR / "attributes.yaml"
SIZING_PATH = DATA_DIR / "stage1_sizing.tsv"
ENA_CACHE = DATA_DIR / "ena_cache"
FIND_CACHE = DATA_DIR / "find_cache"            # Europe PMC + NCBI search JSON
FULLTEXT_CACHE = DATA_DIR / "fulltext_cache"    # grounded-verify paper fetches
LLM_CACHE = DATA_DIR / "llm_cache"


def _select_accessions(args: argparse.Namespace) -> pd.DataFrame:
    """Return Stage-1 sizing rows to process (by --accessions or --fold), biggest-first."""
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


def main() -> None:
    """Parse arguments and run Stage 2B paper-finding."""
    parser = argparse.ArgumentParser(description="Stage 2B — find describing papers (Klebsiella).")
    parser.add_argument("--fold", default="train,val", help="Comma-separated folds (default train,val; test sealed).")
    parser.add_argument("--accessions", default=None, help="Comma-separated accessions (overrides --fold).")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N (biggest-first).")
    parser.add_argument(
        "--backend", choices=["subscription", "api"], default=os.environ.get("BAC_LLM_BACKEND", "subscription"),
        help="LLM backend (default subscription, zero API spend).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model id (default {DEFAULT_MODEL}).")
    parser.add_argument("--cache-dir", type=Path, default=LLM_CACHE, help="LLM response cache dir.")
    parser.add_argument("--output-prefix", default="found_papers", help="Output basename under data/.")
    args = parser.parse_args()

    spec = AttributeSpec.from_yaml(SPEC_PATH)
    sel = _select_accessions(args)
    print(f"Finding papers for {len(sel)} accessions with {args.model} (backend={args.backend})", file=sys.stderr)

    llm = make_llm(args.backend, model=args.model, cache_dir=args.cache_dir)
    for d in (FIND_CACHE, FULLTEXT_CACHE, ENA_CACHE):
        d.mkdir(parents=True, exist_ok=True)

    results: list[paper_finder.FindResult] = []
    skipped: list[str] = []
    limited = False
    for i, (_, row) in enumerate(sel.iterrows(), start=1):
        acc = row["study_accession"]
        taxon_n = int(row["ena_taxon_samples"]) if pd.notna(row["ena_taxon_samples"]) else None
        print(f"[find {i}/{len(sel)}] {acc} (taxon={taxon_n})", file=sys.stderr)

        # Whole per-accession pipeline (ENA fetch → candidate gathering → LLM pick) is wrapped so a
        # single bad accession (e.g. an upstream API returning malformed JSON) is skipped, never
        # fatal to the batch — except a usage-limit, which stops cleanly and writes partial results.
        try:
            study = study_title_and_description(acc, cache_dir=ENA_CACHE)
            aliases = study_aliases(acc, cache_dir=ENA_CACHE)
            candidates, channels = paper_finder.gather_candidates(
                acc, study["study_title"], study["study_description"], aliases=aliases, cache_dir=FIND_CACHE
            )
            sizing_row = {"ena_taxon_samples": taxon_n, "umbrella_suspected": row.get("umbrella_suspected")}
            result = paper_finder.find_paper(
                spec, llm,
                accession=acc, ena_title=study["study_title"], ena_description=study["study_description"],
                sizing_row=sizing_row, candidates=candidates, channels=channels, aliases=aliases,
                model=args.model, fulltext_cache=FULLTEXT_CACHE,
            )
        except UsageLimitError as exc:
            print(f"\n[usage limit] {exc}\nFound {len(results)}/{len(sel)} before the window was exhausted. "
                  "Rerun the same command to resume — cached results return instantly.", file=sys.stderr)
            limited = True
            break
        except Exception as exc:  # noqa: BLE001 — per-accession isolation; one failure must not kill the batch
            print(f"  [skip {acc}] {type(exc).__name__}: {exc}", file=sys.stderr)
            skipped.append(acc)
            continue
        results.append(result)

    jsonl = DATA_DIR / f"{args.output_prefix}.jsonl"
    tsv = DATA_DIR / f"{args.output_prefix}.tsv"
    paper_finder.write_results(results, jsonl, tsv)
    status = "partial (usage limit)" if limited else "complete"
    print(f"Wrote {jsonl} and {tsv} ({len(results)} rows, {status})", file=sys.stderr)
    if skipped:
        print(f"Skipped {len(skipped)} (errors): {skipped} — rerun to retry (cache fills the rest).", file=sys.stderr)


if __name__ == "__main__":
    main()
