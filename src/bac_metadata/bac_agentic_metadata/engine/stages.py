"""The pipeline stages, as one importable function each — the whole pipeline lives here.

Every stage is application-agnostic: it takes the spec, the per-study selection, the input/output
paths, the cache dirs, and the LLM client as explicit arguments. Nothing here knows about Klebsiella —
the field list and per-field guidance come from the spec (``engine.spec``), and the data paths come from
the caller (the unified driver, fed by an application's wrapper script).

The heavy per-study logic already lives in the sibling engine modules (``paper_finder``, ``grader``,
``backfill``, ``sample_extractor``, ``escalation`` …); these functions are the orchestration layer that
loops over the selected studies, calls those modules, records an outcome for every study (never a silent
drop), and writes the stage's output table. They replace the former per-application ``run_*.py`` /
``report_*.py`` scripts, which were thin wrappers around exactly this logic.

The driver (``engine.run_full_metadata_agent``) calls these in order:
    ena_assessment → find_papers → grade → per_sample → backfill → missing_papers →
    persample_supplement → escalate_detect → escalate_apply → fill_metadata_table → run_health
plus ``attach_downloaded_papers`` in the curator loop (match hand-downloaded PDFs to their study).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import paper_finder, websearch
from bac_metadata.bac_agentic_metadata.engine.ena_sizing import study_aliases, study_title_and_description
from bac_metadata.bac_agentic_metadata.engine.llm import UsageLimitError
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec


@dataclass(frozen=True)
class StageCaches:
    """The on-disk cache directories a stage may use (all regenerable). Paths supplied by the caller."""

    llm: Path
    ena: Path
    find: Path
    fulltext: Path
    per_sample_supp: Path

    def ensure(self) -> None:
        """Create every cache dir if missing."""
        for d in (self.llm, self.ena, self.find, self.fulltext, self.per_sample_supp):
            d.mkdir(parents=True, exist_ok=True)


def select_sizing_rows(sizing_path: str | Path, *, accessions: Sequence[str] | None,
                       folds: Sequence[str] | None) -> pd.DataFrame:
    """Return the sizing rows to process — by explicit accessions or by fold — biggest-first.

    One selection helper for every stage that reads the sizing table, so find/grade/escalation can
    never disagree on which studies (or what order) they process. ``accessions`` overrides ``folds``.
    """
    sizing = pd.read_csv(sizing_path, sep="\t")
    if accessions:
        wanted = {a.strip() for a in accessions if a.strip()}
        sel = sizing[sizing["study_accession"].isin(wanted)].copy()
    else:
        keep = {f.strip() for f in (folds or []) if f.strip()}
        sel = sizing[sizing["fold"].isin(keep)].copy()
    sel["ena_taxon_samples"] = pd.to_numeric(sel["ena_taxon_samples"], errors="coerce").fillna(0)
    return sel.sort_values("ena_taxon_samples", ascending=False)


def find_papers(
    *,
    spec: AttributeSpec,
    sizing_path: str | Path,
    accessions: Sequence[str] | None = None,
    folds: Sequence[str] | None = None,
    out_jsonl: Path,
    out_tsv: Path,
    llm,
    model: str,
    caches: StageCaches,
    web_fallback: bool = False,
    limit: int | None = None,
) -> list[paper_finder.FindResult]:
    """Find the describing paper for each selected study and write ``found_papers.{jsonl,tsv}``.

    For each accession (biggest-first): fetch the ENA title/description, gather candidate papers from the
    retrieval channels, let the LLM pick the describing paper (confined to retrieved candidates), ground
    the pick by confirming the accession appears, and abstain when unverified + low-confidence. On
    abstention, ``web_fallback`` searches the open web (paid) and re-picks on the subscription. A single
    bad accession is skipped, never fatal; a usage limit stops cleanly with partial results saved.
    """
    caches.ensure()
    sel = select_sizing_rows(sizing_path, accessions=accessions, folds=folds)
    if limit is not None:
        sel = sel.head(limit)
    print(f"Finding papers for {len(sel)} accessions with {model}", file=sys.stderr)

    results: list[paper_finder.FindResult] = []
    skipped: list[str] = []
    limited = False
    for i, (_, row) in enumerate(sel.iterrows(), start=1):
        acc = row["study_accession"]
        taxon_n = int(row["ena_taxon_samples"]) if pd.notna(row["ena_taxon_samples"]) else None
        print(f"[find {i}/{len(sel)}] {acc} (taxon={taxon_n})", file=sys.stderr)
        try:
            study = study_title_and_description(acc, cache_dir=caches.ena)
            aliases = study_aliases(acc, cache_dir=caches.ena)
            candidates, channels = paper_finder.gather_candidates(
                acc, study["study_title"], study["study_description"], aliases=aliases, cache_dir=caches.find
            )
            sizing_row = {"ena_taxon_samples": taxon_n, "umbrella_suspected": row.get("umbrella_suspected")}
            result = paper_finder.find_paper(
                spec, llm, accession=acc, ena_title=study["study_title"],
                ena_description=study["study_description"], sizing_row=sizing_row,
                candidates=candidates, channels=channels, aliases=aliases,
                model=model, fulltext_cache=caches.fulltext,
            )
            if result.none_found and web_fallback:
                web = websearch.web_search_candidates(
                    acc, study["study_title"], study["study_description"],
                    aliases=aliases, cache_dir=caches.find, model=model,
                )
                if web:
                    merged, merged_channels = paper_finder.merge_web_candidates(
                        candidates, channels, web, cache_dir=caches.find
                    )
                    result = paper_finder.find_paper(
                        spec, llm, accession=acc, ena_title=study["study_title"],
                        ena_description=study["study_description"], sizing_row=sizing_row,
                        candidates=merged, channels=merged_channels, aliases=aliases,
                        model=model, fulltext_cache=caches.fulltext,
                    )
        except UsageLimitError as exc:
            print(f"\n[usage limit] {exc}\nFound {len(results)}/{len(sel)} before the window was "
                  "exhausted. Rerun the same command to resume — cached results return instantly.",
                  file=sys.stderr)
            limited = True
            break
        except Exception as exc:  # noqa: BLE001 — per-accession isolation; one failure must not kill the batch
            print(f"  [skip {acc}] {type(exc).__name__}: {exc}", file=sys.stderr)
            skipped.append(acc)
            continue
        results.append(result)

    paper_finder.write_results(results, out_jsonl, out_tsv)
    status = "partial (usage limit)" if limited else "complete"
    print(f"Wrote {out_jsonl} and {out_tsv} ({len(results)} rows, {status})", file=sys.stderr)
    if skipped:
        print(f"Skipped {len(skipped)} (errors): {skipped} — rerun to retry (cache fills the rest).",
              file=sys.stderr)
    return results


def finder_paper_links(found_path: str | Path) -> dict[str, str]:
    """Map each accession to the paper the *finder* picked (the production / tail grading standard).

    Prefers the PMCID (Europe PMC full text resolves fastest), then DOI, then PMID — all of which
    ``engine.fulltext.fetch_fulltext`` text-mines from a bare identifier.
    """
    f = pd.read_csv(found_path, sep="\t", dtype=str).fillna("")
    links: dict[str, str] = {}
    for _, r in f.iterrows():
        acc = str(r.get("study_accession", "")).strip()
        ref = (r.get("chosen_pmcid", "").strip() or r.get("chosen_doi", "").strip()
               or r.get("chosen_pmid", "").strip())
        if acc and ref:
            links[acc] = ref
    return links


def grade(
    *,
    spec: AttributeSpec,
    sizing_path: str | Path,
    accessions: Sequence[str] | None = None,
    folds: Sequence[str] | None = None,
    paper_links: Mapping[str, str],
    classifications: Mapping[str, dict] | None,
    manual_papers_dir: str | Path,
    out_jsonl: Path,
    out_tsv: Path,
    llm,
    model: str,
    caches: StageCaches,
    max_chars: int | None = None,
    limit: int | None = None,
) -> list:
    """Grade each selected study's paper against the rubric; write ``study_grades.{jsonl,tsv}``.

    ``paper_links`` maps accession → paper reference; the caller chooses its source (the finder's pick
    for production, or the curated snapshot for the in-isolation diagnostic / reproduction check). Paper
    text is resolved the same way for every stage via :func:`resolve_fulltext_for_accession` (open full
    text, else a manually-downloaded ``<acc>.pdf``). One bad/slow paper is skipped; a usage limit stops
    cleanly. A loud audit flags any study whose ``manual_download`` PDF grading did not actually use.
    """
    from bac_metadata.bac_agentic_metadata.engine import grader

    caches.ensure()
    classifications = classifications or {}
    sel = select_sizing_rows(sizing_path, accessions=accessions, folds=folds)
    if limit is not None:
        sel = sel.head(limit)
    print(f"Grading {len(sel)} accessions with {model}", file=sys.stderr)
    max_chars = grader.DEFAULT_MAX_CHARS if max_chars is None else max_chars

    results: list = []
    skipped: list[str] = []
    limited = False
    for i, (_, row) in enumerate(sel.iterrows(), start=1):
        acc = row["study_accession"]
        link = paper_links.get(acc, "")
        taxon_n = int(row["ena_taxon_samples"]) if pd.notna(row["ena_taxon_samples"]) else None
        print(f"[grade {i}/{len(sel)}] {acc} (taxon={taxon_n}) <- {link[:70] or '(no paper link)'}",
              file=sys.stderr)
        ft = resolve_fulltext_for_accession(acc, link, manual_papers_dir, fulltext_cache=caches.fulltext)
        if ft.source == "local_pdf":
            print(f"  [local pdf] grading {acc} from manual download ({len(ft.text)} chars)", file=sys.stderr)
        study = study_title_and_description(acc, cache_dir=caches.ena)
        sizing_row = {
            "ena_taxon_samples": taxon_n, "ena_total_samples": row.get("ena_total_samples"),
            "ena_total_runs": row.get("ena_total_runs"), "by_scientific_name": row.get("by_scientific_name"),
            **classifications.get(acc, {}),
        }
        try:
            result = grader.grade_accession(
                spec, llm, accession=acc, fulltext=ft, ena_title=study["study_title"],
                ena_description=study["study_description"], ena_taxon_samples=taxon_n,
                sizing_row=sizing_row, model=model, max_chars=max_chars,
            )
        except UsageLimitError as exc:
            print(f"\n[usage limit] {exc}\nGraded {len(results)}/{len(sel)} before the window was "
                  "exhausted. Rerun to resume — cached grades return instantly.", file=sys.stderr)
            limited = True
            break
        except (RuntimeError, ValueError) as exc:
            print(f"  [skip {acc}] {exc}", file=sys.stderr)
            skipped.append(acc)
            continue
        results.append(result)

    grader.write_results(results, out_jsonl, out_tsv)
    status = "partial (usage limit)" if limited else "complete"
    print(f"Wrote {out_jsonl} and {out_tsv} ({len(results)} rows, {status})", file=sys.stderr)

    mdir = Path(manual_papers_dir)
    pdf_not_used = sorted(r.study_accession for r in results
                          if (mdir / f"{r.study_accession}.pdf").exists() and r.fulltext_source != "local_pdf")
    if pdf_not_used:
        print(f"[WARN] {len(pdf_not_used)} stud(ies) have a manual_download PDF that grading did NOT use "
              f"(fulltext_source != local_pdf): {pdf_not_used} — re-run grading to retry.", file=sys.stderr)
    if skipped:
        print(f"Skipped {len(skipped)} (errors/timeouts): {skipped} — rerun to retry.", file=sys.stderr)
    return results


def resolve_fulltext_for_accession(acc: str, link: str, manual_papers_dir: str | Path, *, fulltext_cache: Path):
    """Resolve a study's paper text the SAME way for every stage: open full text, else a manual PDF.

    Single source of truth so grading and the escalation triage can never diverge on what evidence a
    study was judged on. Tries Europe PMC / abstract / OA PDF, and — when that is not full text — falls
    back to a manually-downloaded ``<acc>.pdf``. Returns an empty ``FullText`` when neither resolves.
    """
    from bac_metadata.bac_agentic_metadata.engine.fulltext import FullText, fetch_fulltext
    from bac_metadata.bac_agentic_metadata.engine.local_papers import resolve_local_fulltext

    ft = fetch_fulltext(link, cache_dir=fulltext_cache) if link else FullText("", "none", False, False, "")
    if not ft.is_full_text:
        local = resolve_local_fulltext(acc, str(manual_papers_dir))
        if local is not None:
            ft = local
    return ft


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


def per_sample(
    *,
    base: pd.DataFrame,
    found_path: str | Path,
    fields: Sequence[str],
    accessions: Sequence[str] | None,
    out_path: Path,
    manual_supp_dir: str | Path,
    llm,
    model: str,
    caches: StageCaches,
    threshold: float = 0.75,
) -> pd.DataFrame:
    """Per-sample extraction from supplementary tables — the accurate per-isolate source, runs FIRST.

    Over every ENA-incomplete (gated) study with a paper (grade-independent gate), fetch + parse the
    paper's supplementary tables, let the extractor map columns→fields, and deterministically join rows
    to ENA ``sample_accession``. Emits per-sample fills (``method="per_sample"``) and one outcome row per
    target (direct / two_hop / abstained / NO_PMCID / NOT_IN_FOLD / NOT_REACHED) so a study is never
    silently dropped. ``base`` is the per-sample table already restricted to the selection.
    """
    from collections import Counter

    from bac_metadata.bac_agentic_metadata.engine import backfill
    from bac_metadata.bac_agentic_metadata.engine import local_supplements as lsupp
    from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
    from bac_metadata.bac_agentic_metadata.engine import supplementary as supp

    caches.ensure()
    sets: dict[str, set[str]] = {}
    maps: dict[str, dict[str, str]] = {}
    for acc, g in base.groupby("study_accession"):
        maps[acc] = sx.build_accession_to_sample(g)
        sets[acc] = set(maps[acc])

    found = pd.read_csv(found_path, sep="\t", dtype=str).fillna("")
    pmcid_of = {r["study_accession"]: r.get("chosen_pmcid", "").strip() for _, r in found.iterrows()}

    needs = backfill.gate_fields(backfill.field_completeness(base, fields=tuple(fields)), threshold=threshold)
    any_gated = needs.any(axis=1)
    gated = set(any_gated.index[any_gated])
    if accessions:
        targets = [(a.strip(), pmcid_of.get(a.strip(), "")) for a in accessions if a.strip()]
    else:
        targets = [(a, pmcid_of.get(a, "")) for a in sorted(gated)]
    print(f"Per-sample over {len(targets)} gated studies (of {len(gated)} gated; threshold {threshold}) "
          f"with {model}", file=sys.stderr)

    fills: list[dict] = []
    extractions = []
    outcome_rows: list[dict] = []

    def _synthetic(a: str, pm: str, method: str, note: str) -> dict:
        return {"study_accession": a, "pmcid": pm, "table": None, "method": method,
                "n_samples": 0, "n_fills": 0, "confidence": "none", "note": note}

    for i, (acc, pmcid) in enumerate(targets, 1):
        if acc not in sets:
            outcome_rows.append(_synthetic(acc, pmcid, "NOT_IN_FOLD",
                                           "study not in the per-sample selection accession sets"))
            print(f"[{i}/{len(targets)}] {acc} — NOT_IN_FOLD; skip", file=sys.stderr)
            continue
        if not pmcid:
            outcome_rows.append(_synthetic(acc, "", "NO_PMCID",
                "no PMCID — cannot fetch OA supplementary; see missing-papers / manual_download_supp"))
            print(f"[{i}/{len(targets)}] {acc} — NO_PMCID (cannot fetch OA supp)", file=sys.stderr)
            continue
        tables = supp.parse_tables(pmcid, cache_dir=caches.per_sample_supp)
        local = lsupp.resolve_local_supp_tables(acc, manual_supp_dir)
        if local:
            tables = (tables or []) + local
        try:
            ex = sx.extract_study(acc, pmcid, tables, sets[acc], maps[acc], llm, model=model)
        except UsageLimitError as e:
            print(f"[{i}/{len(targets)}] {acc} — usage limit; stopping (cache holds the rest): {e}",
                  file=sys.stderr)
            for racc, rpmcid in targets[i - 1:]:
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
        print(f"[{i}/{len(targets)}] {acc} ({pmcid}) — {ex.note} [conf={ex.confidence}] cols={ex.columns}",
              file=sys.stderr)

    out = pd.DataFrame(fills, columns=["study_accession", "sample_accession", "field", "ena_value",
                                       "applied_value", "method", "evidence"])
    out.to_csv(out_path, sep="\t", index=False)
    outcomes = pd.DataFrame(outcome_rows, columns=["study_accession", "pmcid", "table", "method",
                                                   "n_samples", "n_fills", "confidence", "note"])
    outcomes_path = Path(out_path).with_name(Path(out_path).name.replace("per_sample_applied", "per_sample_outcomes"))
    outcomes.to_csv(outcomes_path, sep="\t", index=False)

    print(f"\nWrote {out_path}: {len(out)} per-sample fills across "
          f"{out['study_accession'].nunique() if len(out) else 0} studies; + {outcomes_path.name}",
          file=sys.stderr)
    if len(outcomes):
        zero = outcomes[outcomes["n_fills"] == 0]
        reasons = Counter(_zero_bucket(r["method"], r["note"]) for _, r in zero.iterrows())
        print(f"\n[per-sample audit] {len(zero)}/{len(outcomes)} target studies produced 0 per-sample fills "
              f"({', '.join(f'{k}={v}' for k, v in sorted(reasons.items())) or 'none'})", file=sys.stderr)
    print(f"confidence: {sx.confidence_tally(extractions)}", file=sys.stderr)
    return out


def backfill_whole_field(
    *,
    base: pd.DataFrame,
    grades_path: str | Path,
    per_sample_path: str | Path | None,
    fields: Sequence[str],
    out_path: Path,
    threshold: float = 0.75,
) -> pd.DataFrame:
    """Whole-field fills for the gaps per-sample LEFT, with the parsimony guard; writes the gate report.

    Gates each field where ENA is already ≥ ``threshold`` complete, fills genuinely-blank cells of the
    rest with the grader's whole-field proposal — never overwriting a per-isolate value, never
    whole-filling a per-sample-heterogeneous field. ``base`` is the per-sample table restricted to the
    selection. Writes the per-sample changes table + a covered/residual gate report.
    """
    from bac_metadata.bac_agentic_metadata.engine import backfill

    fields = tuple(fields)
    g = pd.read_csv(grades_path, sep="\t", dtype=str).fillna("")
    proposals: dict[str, dict[str, dict]] = {}
    for _, r in g.iterrows():
        proposals[r["study_accession"]] = {
            f: {"value": r.get(f"backfill_{f}__value", ""),
                "whole_project": str(r.get(f"backfill_{f}__whole_project", "")).strip().lower() == "true",
                "evidence": ""}
            for f in fields
        }

    completeness = backfill.field_completeness(base, fields=fields)
    needs = backfill.gate_fields(completeness, threshold=threshold)
    per_sample_df = None
    if per_sample_path and Path(per_sample_path).exists():
        per_sample_df = pd.read_csv(per_sample_path, sep="\t", dtype=str)
        ps_filled, ps_het = backfill.per_sample_guards(per_sample_df)
        print(f"Per-sample guard: {sum(len(v) for v in ps_filled.values())} cells already filled; "
              f"{len(ps_het)} (study×field) blocked as per-sample-heterogeneous", file=sys.stderr)
    applied = backfill.apply_whole_field(base, proposals, needs, per_sample=per_sample_df)
    applied.to_csv(out_path, sep="\t", index=False)

    covered = {(f, s) for f, s in zip(applied["field"], applied["study_accession"], strict=False)}
    if per_sample_df is not None and {"field", "study_accession"} <= set(per_sample_df.columns):
        covered |= {(f, s) for f, s in zip(per_sample_df["field"], per_sample_df["study_accession"], strict=False)}
    filled_counts = applied.groupby(["field", "study_accession"]).size().to_dict()
    rows = []
    for f in fields:
        for acc, gated in needs[f].items():
            if not bool(gated):
                continue
            frac = completeness.loc[acc, f]
            n = int(completeness.loc[acc, "n_records"])
            rows.append({
                "field": f, "study_accession": acc, "n_records": n,
                "completeness": round(float(frac), 3) if pd.notna(frac) else "",
                "n_blank": int(round(n * (1 - (frac if pd.notna(frac) else 0.0)))),
                "status": "covered" if (f, acc) in covered else "residual_per_sample",
                "n_filled": int(filled_counts.get((f, acc), 0)),
            })
    gate = pd.DataFrame(rows)
    gate_path = Path(out_path).with_name(Path(out_path).name.replace("applied", "gate_report"))
    gate.sort_values(["field", "status", "study_accession"]).to_csv(gate_path, sep="\t", index=False)
    print(f"Wrote {out_path} ({len(applied)} per-sample fills) and {gate_path.name}", file=sys.stderr)
    return applied
