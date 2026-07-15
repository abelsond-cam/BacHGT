r"""Per-sample supplementary worklist: which studies need a manual supplementary-table fetch (engine).

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

The application injects the curated link map + the cache/manual-PDF dirs; new fields like ``cf_status``
have no per-sample table convention and the application simply doesn't run this stage. Downloaded
supplementary files go to ``<data_dir>/sample_lv_attributes/manual_download_supp/<acc>.<ext>``. Writes
``<data_dir>/sample_lv_attributes/persample_supplement_worklist_<tag>.{md,tsv}``.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from . import supplement_probe
from .fulltext import fetch_fulltext
from .llm import DEFAULT_MODEL, UsageLimitError, make_llm
from .local_papers import resolve_local_fulltext

DEFAULT_FIELDS = ("isolation_source", "host", "collection_date")


def _resolve_text(acc: str, link: str, *, fulltext_cache: Path, manual_papers_dir: Path) -> tuple[str, str]:
    """Return (text, source) for a study — open-access full text, else a manual_download PDF."""
    ft = fetch_fulltext(link, cache_dir=fulltext_cache) if link else None
    if ft is not None and ft.is_full_text:
        return ft.text, ft.source
    local = resolve_local_fulltext(acc, str(manual_papers_dir))
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


def build_persample_supplement_worklist(
    data_dir: Path,
    *,
    paper_links: Mapping[str, str],
    fulltext_cache: Path,
    manual_papers_dir: Path,
    llm_cache: Path,
    tag: str = "test",
    min_gap: int = 50,
    backend: str = "subscription",
    model: str = DEFAULT_MODEL,
    fields: Sequence[str] = DEFAULT_FIELDS,
) -> pd.DataFrame:
    """Build the per-sample supplementary worklist with the LLM per-sample-table opinion.

    Parameters
    ----------
    data_dir
        The application's task-aligned data tree.
    paper_links
        Injected ``study_accession -> curated link`` map.
    fulltext_cache, manual_papers_dir, llm_cache
        The application's full-text cache, manual-PDF dir, and LLM response cache.
    tag
        Artifact tag (gate/grades/per-sample suffix).
    min_gap
        Skip studies whose per-sample backlog is <= this.
    backend, model
        LLM backend + model for the per-sample-table opinion.
    fields
        Per-sample fields whose residual backlog drives the worklist.

    Returns
    -------
    pandas.DataFrame
        The worklist (also written to disk).
    """
    from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

    rp = RunPaths(data_dir, tag)
    supp_dir = rp.manual_supp_dir
    fields = tuple(fields)

    gate = pd.read_csv(rp.backfill_gate_report, sep="\t", dtype=str).fillna("")
    gate["n_blank"] = pd.to_numeric(gate["n_blank"], errors="coerce").fillna(0).astype(int)
    resid = gate[(gate["field"].isin(fields)) & (gate["status"] == "residual_per_sample") & (gate["n_blank"] > 0)]
    # Per study: total per-sample backlog + the fields that are short.
    backlog = resid.groupby("study_accession").agg(
        gap=("n_blank", "sum"), fields=("field", lambda s: ",".join(sorted(set(s))))).reset_index()
    backlog = backlog[backlog["gap"] > min_gap].sort_values("gap", ascending=False)

    grades = {r["study_accession"]: r for _, r in
              pd.read_json(rp.study_grades_jsonl, lines=True).iterrows()} \
        if rp.study_grades_jsonl.exists() else {}
    ps_path = rp.per_sample_applied
    ps = pd.read_csv(ps_path, sep="\t", dtype=str).fillna("") if ps_path.exists() else pd.DataFrame()
    ps_fills = (ps[ps["applied_value"] != ""].groupby("study_accession").size().to_dict()
                if len(ps) else {})
    fp_path = rp.found_papers_tsv
    fp = pd.read_csv(fp_path, sep="\t", dtype=str).fillna("").set_index("study_accession") \
        if fp_path.exists() else pd.DataFrame()
    # The per-sample outcomes carry the MECHANICAL reason each study yielded 0 (no_supp/unanchored/…),
    # shown alongside the LLM opinion so the curator sees both "engine couldn't anchor" and "model thinks
    # the paper does/doesn't hold per-sample data".
    out_path = rp.per_sample_outcomes
    outcomes = pd.read_csv(out_path, sep="\t", dtype=str).fillna("").set_index("study_accession") \
        if out_path.exists() else pd.DataFrame()
    _supp_exts = (".xlsx", ".xls", ".csv", ".tsv", ".docx", ".pdf")

    llm = make_llm(backend, model=model, cache_dir=llm_cache)
    rows = []
    for i, (_, b) in enumerate(backlog.iterrows(), 1):
        acc, gap = b["study_accession"], int(b["gap"])
        g = grades.get(acc, {})
        ft_source = str(g.get("fulltext_source", "")) or "none"
        paywalled = ft_source in ("local_pdf", "pdf", "none", "abstract")
        text, src = _resolve_text(acc, paper_links.get(acc, ""), fulltext_cache=fulltext_cache,
                                  manual_papers_dir=manual_papers_dir)
        has_text = len(text) >= 500
        print(f"[probe {i}/{len(backlog)}] {acc} (gap={gap}, src={src}, text={len(text)})", file=sys.stderr)
        try:
            opinion = supplement_probe.probe_supplement(text, llm, model=model) if has_text else {}
        except UsageLimitError:
            print(f"[usage limit] stopped at {acc}; rerun to resume (cache fills the rest).", file=sys.stderr)
            break
        pmcid = str(fp.loc[acc, "chosen_pmcid"]) if acc in getattr(fp, "index", []) else ""
        doi = str(fp.loc[acc, "chosen_doi"]) if acc in getattr(fp, "index", []) else ""
        # Mechanical reason from the per-sample outcome row + re-check whether a manual supp file is
        # already on disk (added between runs → drops out of the chase list as SUPP_PRESENT).
        om = outcomes.loc[acc] if (len(outcomes) and acc in outcomes.index) else None
        mech = _mech_reason(om["method"], om["note"]) if om is not None else ""
        supp_present = any((supp_dir / f"{acc}{e}").exists() for e in _supp_exts)
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
    rp.per_sample_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(rp.persample_supplement_worklist_tsv, sep="\t", index=False)

    order = {"FETCH_SUPP": 0, "OA_INVESTIGATE": 1, "OA_PARTIAL": 2, "REVIEW": 3, "NO_PAPER": 4,
             "SKIP": 5, "SUPP_PRESENT": 6}
    res = res.sort_values(["action", "gap_samples"], key=lambda c: c.map(order) if c.name == "action" else -c,
                          ascending=[True, True]) if len(res) else res
    md = ["# Per-sample supplementary worklist — which studies need a manual supp-table fetch\n",
          f"{len(res)} studies with a per-sample backlog > {min_gap}. The LLM read the paper we hold "
          "and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the "
          "engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the "
          f"FETCH_SUPP rows as `<acc>.xlsx` into `{supp_dir.name}/`.**\n",
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
    rp.persample_supplement_worklist_md.write_text("\n".join(md) + "\n")
    print(f"\nWrote run_progress/{tag}/per_sample/persample_supplement_worklist.{{md,tsv}} "
          f"({len(res)} studies)", file=sys.stderr)
    if len(res):
        print(res["action"].value_counts().to_string(), file=sys.stderr)
    return res
