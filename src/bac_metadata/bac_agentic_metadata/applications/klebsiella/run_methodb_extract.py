r"""Method-b per-sample extraction runner (Klebsiella) — fill date/source/country/host from supp tables.

For each residual study with a joinable OA supplementary table (see ``methodb_mappability.tsv``), this
fetches + parses the paper's supplementary tables, lets the extraction agent map columns→fields, and
deterministically joins table rows to ENA ``sample_accession``s — emitting per-sample fills
(``method="per_sample"``) in the same long shape as the whole-field backfill. Grounded on the study's
ENA accession set; abstains when nothing maps. RAW values only (no categorisation).

The LLM does one small structured call per study (column mapping); everything else is deterministic and
disk-cached, so reruns are free. Defaults to the ``subscription`` backend (zero API spend).

Examples
--------
unset VIRTUAL_ENV
export BACHGT_PROJECT_K_ROOT="…/Aaron Weimann's files - project_k" BACHGT_PROJECT_K_USER=data
uv run python .../run_methodb_extract.py --accessions PRJEB36486      # smoke-test one study first
uv run python .../run_methodb_extract.py --joinable-only              # all joinable residual studies
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
from bac_metadata.bac_agentic_metadata.engine import supplementary as supp
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, UsageLimitError, make_llm

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SUPP_CACHE = DATA_DIR / "_methodb_supp_cache"
LLM_CACHE = DATA_DIR / "llm_cache"
AUX = ("sample_accession", "run_accession", "secondary_sample_accession", "accession")


def _study_accession_sets(folds: set[str]) -> tuple[dict[str, set[str]], dict[str, dict[str, str]]]:
    """Per-study ENA accession sets + any-accession→sample maps, for the requested folds."""
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    base = KlebCollationSource(keep_columns=AUX).states()["base"]
    split = pd.read_csv(DATA_DIR / "kleb_project_splits.tsv", sep="\t", dtype=str)[["study_accession", "fold"]]
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    base = base[base["study_accession"].isin(keep)]
    acc_cols = [c for c in AUX if c in base.columns]
    sets: dict[str, set[str]] = {}
    maps: dict[str, dict[str, str]] = {}
    for acc, g in base.groupby("study_accession"):
        s: set[str] = set()
        for c in acc_cols:
            s |= set(g[c].dropna().astype(str).str.upper())
        sets[acc] = s
        maps[acc] = sx.build_accession_to_sample(g)
    return sets, maps


def _targets(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Return ``[(study_accession, pmcid)]`` — explicit accessions, all residual studies, or the joinable list."""
    feas = pd.read_csv(DATA_DIR / "methodb_feasibility.tsv", sep="\t", dtype=str)
    pmcid_of = dict(zip(feas["study"], feas["pmcid"], strict=False))
    if args.accessions:
        accs = [a.strip() for a in args.accessions.split(",") if a.strip()]
        return [(a, pmcid_of.get(a, "")) for a in accs]
    if args.all_residual:
        # Every residual study with a PMCID — let the extractor decide (it abstains gracefully). This
        # is the exhaustive sweep now that PDF/DOCX tables + the two-hop join are in.
        gate = pd.read_csv(DATA_DIR / "backfill_gate_report.tsv", sep="\t", dtype=str)
        residual = sorted(set(gate[gate["status"] == "residual_method_b"]["study_accession"]))
        return [(a, pmcid_of.get(a, "")) for a in residual if pmcid_of.get(a, "")]
    mp = pd.read_csv(DATA_DIR / "methodb_mappability.tsv", sep="\t", dtype=str)
    if args.joinable_only:
        mp = mp[mp["joinable"].str.lower() == "true"]
    return list(zip(mp["study"], mp["pmcid"], strict=False))


def main() -> None:
    """Parse args, run method-b extraction over the target studies, write the per-sample fills."""
    p = argparse.ArgumentParser(description="Method-b per-sample extraction from supplementary tables.")
    p.add_argument("--accessions", default=None, help="Comma-separated studies (overrides the joinable list).")
    p.add_argument("--joinable-only", action="store_true", help="Restrict to joinable studies (default if no --accessions).")
    p.add_argument("--all-residual", action="store_true", help="Sweep every residual study (PDF/DOCX-aware; extractor abstains as needed).")
    p.add_argument("--fold", default="train,val", help="Folds for the ENA accession sets (default train,val).")
    p.add_argument("--backend", default="subscription", choices=["subscription", "api"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default=str(DATA_DIR / "methodb_applied.tsv"))
    args = p.parse_args()
    if not args.accessions and not args.all_residual:
        args.joinable_only = True

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    sets, maps = _study_accession_sets(folds)
    targets = _targets(args)
    llm = make_llm(args.backend, model=args.model, cache_dir=LLM_CACHE)
    print(f"Method-b over {len(targets)} studies with {args.model} (backend={args.backend})", file=sys.stderr)

    fills: list[dict] = []
    extractions = []
    for i, (acc, pmcid) in enumerate(targets, 1):
        if acc not in sets:
            print(f"[{i}/{len(targets)}] {acc} — not in folds {sorted(folds)}; skip", file=sys.stderr)
            continue
        tables = supp.parse_tables(pmcid, cache_dir=SUPP_CACHE)
        try:
            ex = sx.extract_study(acc, pmcid, tables, sets[acc], maps[acc], llm, model=args.model)
        except UsageLimitError as e:
            print(f"[{i}/{len(targets)}] {acc} — usage limit hit; stopping (cache holds the rest): {e}", file=sys.stderr)
            break
        extractions.append(ex)
        fills.extend(ex.fills)
        print(f"[{i}/{len(targets)}] {acc} ({pmcid}) — {ex.note} [conf={ex.confidence}] cols={ex.columns}", file=sys.stderr)

    out = pd.DataFrame(fills, columns=["study_accession", "sample_accession", "field", "ena_value",
                                       "applied_value", "method", "evidence"])
    out.to_csv(args.output, sep="\t", index=False)

    # Per-study outcome record (direct / two-hop / abstained + why) — the method-b coverage map.
    outcomes = pd.DataFrame([{
        "study_accession": e.study_accession, "pmcid": e.pmcid, "table": e.table,
        "method": ("two_hop" if any(f["method"] == "per_sample_two_hop" for f in e.fills)
                   else "direct" if e.fills else "abstained"),
        "n_samples": e.n_samples_mapped, "n_fills": len(e.fills),
        "confidence": e.confidence, "note": e.note,
    } for e in extractions])
    outcomes_path = Path(args.output).with_name("methodb_outcomes.tsv")
    outcomes.to_csv(outcomes_path, sep="\t", index=False)

    print(f"\nWrote {args.output}: {len(out)} per-sample fills across "
          f"{out['study_accession'].nunique()} studies; + {outcomes_path.name}", file=sys.stderr)
    if len(out):
        print("fills by field:\n" + out["field"].value_counts().to_string(), file=sys.stderr)
    if len(outcomes):
        print("\nper-study method:\n" + outcomes["method"].value_counts().to_string(), file=sys.stderr)
    print(f"confidence: {sx.confidence_tally(extractions)}", file=sys.stderr)


if __name__ == "__main__":
    main()
