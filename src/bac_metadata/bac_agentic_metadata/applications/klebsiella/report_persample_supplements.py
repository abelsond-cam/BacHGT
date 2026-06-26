r"""Per-sample supplementary worklist: which studies need a manual supplementary-table fetch.

Per-sample backfill fills ``isolation_source`` / ``host`` / ``collection_date`` PER sample from a
paper's per-isolate supplementary table — but :mod:`engine.supplementary` only fetches those tables
from Europe PMC **open-access**. Paywalled studies (we hold only the main-text PDF) therefore get no
per-sample fills, which is the dominant isolation-source completeness gap.

This builds the manual-fetch worklist for that step. For every study with a per-sample backlog (gate
report ``status == residual_per_sample``) it:

1. resolves the paper text we already hold (open-access full text, or a ``manual_download/<acc>.pdf``),
2. asks the LLM (:func:`engine.supplement_probe.probe_supplement`) whether that paper actually carries a
   per-isolate table and which fields it covers — so the curator skips studies that hold no per-sample
   data (many don't), and
3. classifies each study into an action: **FETCH_SUPP** (paywalled, has a table → download its
   supplementary file by hand), **OA_INVESTIGATE** (open-access + has a table but per-sample extracted
   nothing → a fetch/parse bug to chase), **SKIP** (no per-isolate table), **NO_PAPER** (no text yet).

Downloaded supplementary files go to ``data/sample_lv_attributes/manual_download_supp/<acc>.<ext>`` for
the local-supplementary loader to pick up. Writes ``data/sample_lv_attributes/persample_supplement_worklist.{md,tsv}``.

Examples
--------
unset VIRTUAL_ENV
uv run python .../report_persample_supplements.py --fold test --tag test --min-gap 50
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import supplement_probe
from bac_metadata.bac_agentic_metadata.engine.fulltext import fetch_fulltext
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, UsageLimitError, make_llm
from bac_metadata.bac_agentic_metadata.engine.local_papers import resolve_local_fulltext

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
GATE = DATA_DIR / "study_lv_attributes" / "whole_study_backfill"
GRADE = DATA_DIR / "study_lv_attributes" / "grading"
PS = DATA_DIR / "sample_lv_attributes" / "per_sample"
FIND = DATA_DIR / "find_papers"
OUT_DIR = DATA_DIR / "sample_lv_attributes"
SUPP_DIR = OUT_DIR / "manual_download_supp"
FIELDS = ("isolation_source", "host", "collection_date")


def _load_grading_helpers():
    """Import ``run_study_grading`` by path to reuse its link map + cache/dir constants (DRY)."""
    spec = importlib.util.spec_from_file_location("_rsg", APP_DIR / "run_study_grading.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _resolve_text(acc: str, link: str, rsg) -> tuple[str, str]:
    """Return (text, source) for a study — open-access full text, else a manual_download PDF."""
    ft = fetch_fulltext(link, cache_dir=rsg.FULLTEXT_CACHE) if link else None
    if ft is not None and ft.is_full_text:
        return ft.text, ft.source
    local = resolve_local_fulltext(acc, str(rsg.MANUAL_PAPERS_DIR))
    if local is not None:
        return local.text, local.source
    return ((ft.text if ft else ""), (ft.source if ft else "none"))


def _action(opinion: dict, *, paywalled: bool, ps_fills: int, has_text: bool) -> str:
    """Classify a study into a curator action from the probe + paper/extraction state."""
    if not has_text:
        return "NO_PAPER"
    verdict = opinion.get("has_per_sample_table", "unclear")
    if verdict in ("yes", "likely"):
        if paywalled:
            return "FETCH_SUPP"
        return "OA_INVESTIGATE" if ps_fills == 0 else "OA_PARTIAL"
    if verdict == "no":
        return "SKIP"
    return "REVIEW"


def _mech_reason(method: str, note: str) -> str:
    """The mechanical (engine) reason a study yielded 0 per-sample fills, read from its outcome row."""
    if method in ("NO_PMCID", "NOT_IN_FOLD", "NOT_REACHED", "direct", "two_hop"):
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


def main() -> None:
    """Build the per-sample supplementary worklist with the LLM per-sample-table opinion."""
    p = argparse.ArgumentParser(description="Per-sample supplementary-table worklist (Klebsiella).")
    p.add_argument("--tag", default="test", help="Artifact tag (gate/grades/per-sample suffix).")
    p.add_argument("--min-gap", type=int, default=50, help="Skip studies whose per-sample backlog is <= this.")
    p.add_argument("--backend", default="subscription", help="LLM backend (subscription | api).")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Model for the opinion.")
    args = p.parse_args()

    rsg = _load_grading_helpers()
    links = rsg._accession_to_paper_link()

    gate = pd.read_csv(GATE / f"backfill_gate_report_{args.tag}.tsv", sep="\t", dtype=str).fillna("")
    gate["n_blank"] = pd.to_numeric(gate["n_blank"], errors="coerce").fillna(0).astype(int)
    resid = gate[(gate["field"].isin(FIELDS)) & (gate["status"] == "residual_per_sample") & (gate["n_blank"] > 0)]
    # Per study: total per-sample backlog + the fields that are short.
    backlog = resid.groupby("study_accession").agg(
        gap=("n_blank", "sum"), fields=("field", lambda s: ",".join(sorted(set(s))))).reset_index()
    backlog = backlog[backlog["gap"] > args.min_gap].sort_values("gap", ascending=False)

    grades = {r["study_accession"]: r for _, r in
              pd.read_json(GRADE / f"study_grades_{args.tag}.jsonl", lines=True).iterrows()} \
        if (GRADE / f"study_grades_{args.tag}.jsonl").exists() else {}
    ps_path = PS / f"per_sample_applied_{args.tag}.tsv"
    ps = pd.read_csv(ps_path, sep="\t", dtype=str).fillna("") if ps_path.exists() else pd.DataFrame()
    ps_fills = (ps[ps["applied_value"] != ""].groupby("study_accession").size().to_dict()
                if len(ps) else {})
    fp_path = FIND / f"found_papers_{args.tag}.tsv"
    fp = pd.read_csv(fp_path, sep="\t", dtype=str).fillna("").set_index("study_accession") \
        if fp_path.exists() else pd.DataFrame()
    # The per-sample outcomes carry the MECHANICAL reason each study yielded 0 (no_supp/unanchored/…),
    # shown alongside the LLM opinion so the curator sees both "engine couldn't anchor" and "model thinks
    # the paper does/doesn't hold per-sample data".
    out_path = PS / f"per_sample_outcomes_{args.tag}.tsv"
    outcomes = pd.read_csv(out_path, sep="\t", dtype=str).fillna("").set_index("study_accession") \
        if out_path.exists() else pd.DataFrame()
    _supp_exts = (".xlsx", ".xls", ".csv", ".tsv", ".docx", ".pdf")

    llm = make_llm(args.backend, model=args.model, cache_dir=rsg.LLM_CACHE)
    rows = []
    for i, (_, b) in enumerate(backlog.iterrows(), 1):
        acc, gap = b["study_accession"], int(b["gap"])
        g = grades.get(acc, {})
        ft_source = str(g.get("fulltext_source", "")) or "none"
        paywalled = ft_source in ("local_pdf", "pdf", "none", "abstract")
        text, src = _resolve_text(acc, links.get(acc, ""), rsg)
        has_text = len(text) >= 500
        print(f"[probe {i}/{len(backlog)}] {acc} (gap={gap}, src={src}, text={len(text)})", file=sys.stderr)
        try:
            opinion = supplement_probe.probe_supplement(text, llm, model=args.model) if has_text else {}
        except UsageLimitError:
            print(f"[usage limit] stopped at {acc}; rerun to resume (cache fills the rest).", file=sys.stderr)
            break
        pmcid = str(fp.loc[acc, "chosen_pmcid"]) if acc in getattr(fp, "index", []) else ""
        doi = str(fp.loc[acc, "chosen_doi"]) if acc in getattr(fp, "index", []) else ""
        # Mechanical reason from the per-sample outcome row + re-check whether a manual supp file is
        # already on disk (added between runs → drops out of the chase list as SUPP_PRESENT).
        om = outcomes.loc[acc] if (len(outcomes) and acc in outcomes.index) else None
        mech = _mech_reason(om["method"], om["note"]) if om is not None else ""
        supp_present = any((SUPP_DIR / f"{acc}{e}").exists() for e in _supp_exts)
        action = "SUPP_PRESENT" if supp_present else \
            _action(opinion, paywalled=paywalled, ps_fills=ps_fills.get(acc, 0), has_text=has_text)
        rows.append({
            "study_accession": acc, "gap_samples": gap, "gap_fields": b["fields"],
            "fulltext_source": ft_source, "paywalled": paywalled, "per_sample_fills": ps_fills.get(acc, 0),
            "mech_reason": mech, "supp_present": supp_present,
            "has_per_sample_table": opinion.get("has_per_sample_table", "" if has_text else "no_text"),
            "table_fields": ",".join(opinion.get("fields_present", [])),
            "accession_keyed": opinion.get("accession_keyed", ""),
            "table_reference": opinion.get("table_reference", ""),
            "action": action, "evidence_quote": opinion.get("evidence_quote", ""),
            "pmcid": pmcid, "doi": doi, "save_as": f"{acc}.xlsx",
        })

    res = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_DIR / f"persample_supplement_worklist_{args.tag}.tsv", sep="\t", index=False)

    order = {"FETCH_SUPP": 0, "OA_INVESTIGATE": 1, "OA_PARTIAL": 2, "REVIEW": 3, "NO_PAPER": 4,
             "SKIP": 5, "SUPP_PRESENT": 6}
    res = res.sort_values(["action", "gap_samples"], key=lambda c: c.map(order) if c.name == "action" else -c,
                          ascending=[True, True]) if len(res) else res
    md = ["# Per-sample supplementary worklist — which studies need a manual supp-table fetch\n",
          f"{len(res)} studies with a per-sample backlog > {args.min_gap}. The LLM read the paper we hold "
          "and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the "
          "engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the "
          f"FETCH_SUPP rows as `<acc>.xlsx` into `{SUPP_DIR.name}/`.**\n",
          "- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.",
          "- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.",
          "- **SKIP** — paper has no per-isolate table (no per-sample data to recover).",
          "- **NO_PAPER** — no full text yet (resolve the paper first).",
          "- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.\n",
          "| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        paper = r["fulltext_source"] + (f" / {r['pmcid']}" if r["pmcid"] else "")
        md.append(f"| {r['action']} | {r['study_accession']} | {r['gap_samples']} | {r['gap_fields']} | "
                  f"{r.get('mech_reason', '')} | {r['has_per_sample_table']} | {r['table_fields']} | "
                  f"{r['table_reference'][:40]} | {paper} | `{r['save_as']}` |")
    (OUT_DIR / f"persample_supplement_worklist_{args.tag}.md").write_text("\n".join(md) + "\n")
    print(f"\nWrote persample_supplement_worklist_{args.tag}.{{md,tsv}} ({len(res)} studies)", file=sys.stderr)
    if len(res):
        print(res["action"].value_counts().to_string(), file=sys.stderr)


if __name__ == "__main__":
    main()
