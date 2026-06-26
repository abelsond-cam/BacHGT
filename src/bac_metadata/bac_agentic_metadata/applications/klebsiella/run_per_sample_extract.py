r"""Per-sample per-sample extraction runner (Klebsiella) — fill date/source/country/host from supp tables.

For each residual study with a joinable OA supplementary table (see ``per_sample_mappability.tsv``), this
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
uv run python .../run_per_sample_extract.py --accessions PRJEB36486      # smoke-test one study first
uv run python .../run_per_sample_extract.py --joinable-only              # all joinable residual studies
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import local_supplements as lsupp
from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
from bac_metadata.bac_agentic_metadata.engine import supplementary as supp
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, UsageLimitError, make_llm

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SUPP_CACHE = DATA_DIR / "cache" / "per_sample_supp"
LLM_CACHE = DATA_DIR / "cache" / "llm"
MANUAL_SUPP_DIR = DATA_DIR / "sample_lv_attributes" / "manual_download_supp"
AUX = ("sample_accession", "run_accession", "secondary_sample_accession", "accession",
       "sample_alias", "sample_title")


def _zero_bucket(method: str, note: str) -> str:
    """Coarse reason bucket for a per-sample outcome that produced 0 fills (drives the loud audit)."""
    if method in ("NO_PMCID", "NOT_IN_FOLD", "NOT_REACHED"):
        return method
    n = (note or "").lower()
    if "unanchored" in n:
        return "unanchored"
    if "manifest" in n:
        return "manifest_only"
    if "value check" in n:
        return "value_check_failed"
    if "no joinable table" in n:
        return "no_supp"
    return "abstained_other"


def _load_fold_base(folds: set[str]) -> pd.DataFrame:
    """Raw per-sample ENA table for the requested folds (one source of truth for sets + the gate)."""
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    base = KlebCollationSource(keep_columns=AUX).states()["base"]
    split = pd.read_csv(DATA_DIR / "fold_splits" / "project_splits.tsv", sep="\t", dtype=str)[["study_accession", "fold"]]
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    return base[base["study_accession"].isin(keep)]


def _study_accession_sets(base: pd.DataFrame) -> tuple[dict[str, set[str]], dict[str, dict[str, str]]]:
    """Per-study ENA accession sets + any-accession→sample maps."""
    sets: dict[str, set[str]] = {}
    maps: dict[str, dict[str, str]] = {}
    for acc, g in base.groupby("study_accession"):
        maps[acc] = sx.build_accession_to_sample(g)  # normalised id → sample (accessions + strain aliases)
        sets[acc] = set(maps[acc])                   # the id-key set pick_accession_column matches against
    return sets, maps


def _gated_studies(base: pd.DataFrame, threshold: float) -> set[str]:
    """Studies with >=1 field ENA leaves incomplete (< ``threshold``) — the per-sample target universe.

    Per-sample runs FIRST, so its target list is the grade-INDEPENDENT gate (ENA incompleteness), NOT the
    whole-field residual: the accurate per-isolate step gets first crack at every field a study is short on,
    and whole-field later fills only what per-sample leaves.
    """
    from bac_metadata.bac_agentic_metadata.engine import backfill

    needs = backfill.gate_fields(backfill.field_completeness(base), threshold=threshold)
    any_gated = needs.any(axis=1)
    return set(any_gated.index[any_gated])


def _targets(args: argparse.Namespace, gated_studies: set[str], pmcid_of: dict[str, str]) -> list[tuple[str, str]]:
    """Return ``[(study_accession, pmcid)]`` — explicit accessions, else every gated study (with a paper).

    PMCIDs come from the finder output (``--found``); the study universe is the ENA-incompleteness gate
    (:func:`_gated_studies`). The loop records an outcome row for each so a study is never silently dropped;
    the extractor abstains where nothing maps.
    """
    if args.accessions:
        accs = [a.strip() for a in args.accessions.split(",") if a.strip()]
        return [(a, pmcid_of.get(a, "")) for a in accs]
    return [(a, pmcid_of.get(a, "")) for a in sorted(gated_studies)]


def main() -> None:
    """Parse args, run per-sample extraction over the target studies, write the per-sample fills."""
    p = argparse.ArgumentParser(description="Per-sample per-sample extraction from supplementary tables.")
    p.add_argument("--accessions", default=None, help="Comma-separated studies (else every residual study with a paper).")
    p.add_argument("--found", default=str(DATA_DIR / "find_papers" / "found_papers.tsv"), help="Finder output (source of PMCIDs).")
    p.add_argument("--threshold", type=float, default=0.75, help="ENA non-null fraction at/above which a field is complete (gate; default 0.75).")
    p.add_argument("--fold", default="train,val", help="Folds for the ENA accession sets (default train,val).")
    p.add_argument("--backend", default="subscription", choices=["subscription", "api"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default=str(DATA_DIR / "sample_lv_attributes" / "per_sample" / "per_sample_applied.tsv"))
    args = p.parse_args()

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    base = _load_fold_base(folds)
    sets, maps = _study_accession_sets(base)
    found = pd.read_csv(args.found, sep="\t", dtype=str).fillna("")
    pmcid_of = {r["study_accession"]: r.get("chosen_pmcid", "").strip() for _, r in found.iterrows()}
    gated = _gated_studies(base, args.threshold)
    targets = _targets(args, gated, pmcid_of)
    llm = make_llm(args.backend, model=args.model, cache_dir=LLM_CACHE)
    print(f"Per-sample over {len(targets)} gated studies (of {len(gated)} gated; threshold {args.threshold}) "
          f"with {args.model} (backend={args.backend})", file=sys.stderr)

    fills: list[dict] = []
    extractions = []                 # real StudyExtraction objects (drive confidence_tally)
    outcome_rows: list[dict] = []    # ONE ROW PER TARGET — synthetic for skipped/not-reached, never silent

    def _synthetic(a: str, pm: str, method: str, note: str) -> dict:
        return {"study_accession": a, "pmcid": pm, "table": None, "method": method,
                "n_samples": 0, "n_fills": 0, "confidence": "none", "note": note}

    for i, (acc, pmcid) in enumerate(targets, 1):
        if acc not in sets:
            outcome_rows.append(_synthetic(acc, pmcid, "NOT_IN_FOLD",
                                           f"study not in per-sample fold accession sets {sorted(folds)}"))
            print(f"[{i}/{len(targets)}] {acc} — NOT_IN_FOLD; skip", file=sys.stderr)
            continue
        if not pmcid:
            outcome_rows.append(_synthetic(acc, "", "NO_PMCID",
                "no PMCID — cannot fetch OA supplementary; see missing-papers / manual_download_supp"))
            print(f"[{i}/{len(targets)}] {acc} — NO_PMCID (cannot fetch OA supp)", file=sys.stderr)
            continue
        tables = supp.parse_tables(pmcid, cache_dir=SUPP_CACHE)
        local = lsupp.resolve_local_supp_tables(acc, MANUAL_SUPP_DIR)  # manual supp, re-checked every run
        if local:
            tables = (tables or []) + local
        try:
            ex = sx.extract_study(acc, pmcid, tables, sets[acc], maps[acc], llm, model=args.model)
        except UsageLimitError as e:
            print(f"[{i}/{len(targets)}] {acc} — usage limit; stopping (cache holds the rest): {e}", file=sys.stderr)
            for racc, rpmcid in targets[i - 1:]:  # current + remaining never attempted → record, don't drop
                outcome_rows.append(_synthetic(racc, rpmcid, "NOT_REACHED",
                    "not reached before usage limit; rerun to resume (cache fills the rest)"))
            break
        extractions.append(ex)
        fills.extend(ex.fills)
        outcome_rows.append({
            "study_accession": ex.study_accession, "pmcid": ex.pmcid, "table": ex.table,
            "method": ("two_hop" if any(f["method"] == "per_sample_two_hop" for f in ex.fills)
                       else "direct" if ex.fills else "abstained"),
            "n_samples": ex.n_samples_mapped, "n_fills": len(ex.fills),
            "confidence": ex.confidence, "note": ex.note,
        })
        print(f"[{i}/{len(targets)}] {acc} ({pmcid}) — {ex.note} [conf={ex.confidence}] cols={ex.columns}", file=sys.stderr)

    out = pd.DataFrame(fills, columns=["study_accession", "sample_accession", "field", "ena_value",
                                       "applied_value", "method", "evidence"])
    out.to_csv(args.output, sep="\t", index=False)

    # Per-study outcome record (direct / two_hop / abstained / NO_PMCID / NOT_IN_FOLD / NOT_REACHED + why):
    # ONE ROW PER TARGET so a study producing 0 per-sample fills is never silently absent — this is the
    # per-sample coverage map the run-health report aggregates. Tag mirrors --output (…_<tag>.tsv).
    outcomes = pd.DataFrame(outcome_rows, columns=["study_accession", "pmcid", "table", "method",
                                                   "n_samples", "n_fills", "confidence", "note"])
    outcomes_path = Path(args.output).with_name(
        Path(args.output).name.replace("per_sample_applied", "per_sample_outcomes"))
    outcomes.to_csv(outcomes_path, sep="\t", index=False)

    print(f"\nWrote {args.output}: {len(out)} per-sample fills across "
          f"{out['study_accession'].nunique()} studies; + {outcomes_path.name}", file=sys.stderr)
    if len(out):
        print("fills by field:\n" + out["field"].value_counts().to_string(), file=sys.stderr)
    # Loud zero-fill audit — the per-sample analogue of the grading no-fudge audit: never let a study
    # silently yield 0 without saying WHY.
    if len(outcomes):
        zero = outcomes[outcomes["n_fills"] == 0]
        reasons = Counter(_zero_bucket(r["method"], r["note"]) for _, r in zero.iterrows())
        print(f"\n[per-sample audit] {len(zero)}/{len(outcomes)} target studies produced 0 per-sample fills "
              f"({', '.join(f'{k}={v}' for k, v in sorted(reasons.items())) or 'none'})", file=sys.stderr)
        print("per-study method:\n" + outcomes["method"].value_counts().to_string(), file=sys.stderr)
    print(f"confidence: {sx.confidence_tally(extractions)}", file=sys.stderr)


if __name__ == "__main__":
    main()
