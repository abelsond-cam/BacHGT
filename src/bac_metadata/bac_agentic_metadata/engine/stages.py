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
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import paper_finder, websearch
from bac_metadata.bac_agentic_metadata.engine import value_validity as vv
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


def curated_paper_links(snapshot_path: str | Path) -> dict[str, str]:
    """Map each accession to its first curated ``paper_link`` from the application's study-level snapshot.

    The curated-link grading source (the in-isolation diagnostic + the reproduction check). A row may
    list several comma-separated accessions and several URLs; we take the first URL and attach it to each
    accession on the row. App-specific only in *which file* + column — the path is supplied by the caller.
    """
    import re

    url_re = re.compile(r"https?://\S+")
    df = pd.read_csv(snapshot_path, dtype=str).fillna("")
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        link = row.get("paper_link", "").strip()
        m = url_re.search(link)
        first = m.group(0).rstrip(").,") if m else link
        if not first:
            continue
        for acc in re.split(r"[,\s]+", row.get("study_accessions", "")):
            acc = acc.strip()
            if acc and acc not in mapping:
                mapping[acc] = first
    return mapping


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
    context_tiers: Sequence[int] | None = None,
    workers: int = 1,
    skip_existing: bool = False,
    limit: int | None = None,
) -> list:
    """Grade each selected study's paper against the rubric; write ``study_grades.{jsonl,tsv}``.

    ``paper_links`` maps accession → paper reference; the caller chooses its source (the finder's pick
    for production, or the curated snapshot for the in-isolation diagnostic / reproduction check). Paper
    text is resolved the same way for every stage via :func:`resolve_fulltext_for_accession` (open full
    text, else a manually-downloaded ``<acc>.pdf``). One bad/slow paper is skipped; a usage limit stops
    cleanly. A loud audit flags any study whose ``manual_download`` PDF grading did not actually use.

    ``workers`` grades that many accessions concurrently (default 1 = sequential, to stay light on a shared
    Claude Pro window). Concurrency is safe — the subscription backend streams each prompt over stdin and the
    disk cache is per-(study,tier) with atomic writes. The output is written incrementally after every
    completion and always in the stable selection order, so ``study_grades.{jsonl,tsv}`` is byte-identical
    regardless of ``workers`` and inspectable mid-run; a usage limit cancels the pending queue and stops clean.

    ``skip_existing`` keeps any study already present in ``out_jsonl`` exactly as previously graded and grades
    only the rest — a usage-saving resume when a rubric/ladder tweak should NOT re-spend on studies already
    done (their grades are re-used verbatim and merged into the output in stable order).
    """
    from collections import Counter
    from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed

    from bac_metadata.bac_agentic_metadata.engine import grader

    caches.ensure()
    classifications = classifications or {}
    sel = select_sizing_rows(sizing_path, accessions=accessions, folds=folds)
    if limit is not None:
        sel = sel.head(limit)
    max_chars = grader.DEFAULT_MAX_CHARS if max_chars is None else max_chars
    tiers = list(context_tiers) if context_tiers else [max_chars]
    first_tier = min(tiers)
    rows = [(i, row) for i, (_, row) in enumerate(sel.iterrows())]
    total = len(rows)
    print(f"Grading {total} accessions with {model} (workers={workers}, context tiers={tiers})", file=sys.stderr)

    def _grade_one(row):
        acc = row["study_accession"]
        link = paper_links.get(acc, "")
        taxon_n = int(row["ena_taxon_samples"]) if pd.notna(row["ena_taxon_samples"]) else None
        ft = resolve_fulltext_for_accession(acc, link, manual_papers_dir, fulltext_cache=caches.fulltext)
        study = study_title_and_description(acc, cache_dir=caches.ena)
        sizing_row = {
            "ena_taxon_samples": taxon_n, "ena_total_samples": row.get("ena_total_samples"),
            "ena_total_runs": row.get("ena_total_runs"), "by_scientific_name": row.get("by_scientific_name"),
            **classifications.get(acc, {}),
        }
        result = grader.grade_accession(
            spec, llm, accession=acc, fulltext=ft, ena_title=study["study_title"],
            ena_description=study["study_description"], ena_taxon_samples=taxon_n,
            sizing_row=sizing_row, model=model, max_chars=max_chars, context_tiers=context_tiers,
        )
        return result, ft.source

    slots: list = [None] * total
    skipped: list[str] = []
    limited = False
    # Resume: keep already-graded studies verbatim, grade only the rest (a usage-saving restart).
    existing = {r.study_accession: r for r in grader.load_results(out_jsonl)} if skip_existing else {}
    to_grade = []
    for i, row in rows:
        if row["study_accession"] in existing:
            slots[i] = existing[row["study_accession"]]
        else:
            to_grade.append((i, row))
    completed = sum(1 for s in slots if s is not None)
    if existing:
        print(f"[grade] resume: keeping {completed} already-graded studies, grading {len(to_grade)} remaining",
              file=sys.stderr)
        grader.write_results([s for s in slots if s is not None], out_jsonl, out_tsv)  # seed the union
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(_grade_one, row): (i, row["study_accession"]) for i, row in to_grade}
        for fut in as_completed(futures):
            idx, acc = futures[fut]
            try:
                result, ft_source = fut.result()
            except CancelledError:
                continue  # pending task cancelled after a usage limit — nothing graded for it
            except UsageLimitError:
                if not limited:
                    limited = True
                    for f in futures:  # stop cleanly: drop everything not already running
                        f.cancel()
                continue
            except (RuntimeError, ValueError) as exc:
                print(f"  [skip {acc}] {exc}", file=sys.stderr)
                skipped.append(acc)
                continue
            slots[idx] = result
            completed += 1
            tier = result.grade_context_chars
            note = "".join([
                " climbed" if tier > first_tier else "",
                " [local pdf]" if ft_source == "local_pdf" else "",
                " ⚠more-would-help" if result.full_text_would_help else "",
            ])
            print(f"[grade {completed}/{total}] {acc}: resolved at {tier:,} chars{note}", file=sys.stderr)
            grader.write_results([s for s in slots if s is not None], out_jsonl, out_tsv)  # incremental, ordered

    results = [s for s in slots if s is not None]
    grader.write_results(results, out_jsonl, out_tsv)  # final (also covers the graded-nothing case)
    status = "partial (usage limit)" if limited else "complete"
    print(f"Wrote {out_jsonl} and {out_tsv} ({len(results)} rows, {status})", file=sys.stderr)
    if limited:
        print(f"[usage limit] Graded {len(results)}/{total} before the window was exhausted. Rerun to "
              "resume — cached grades return instantly.", file=sys.stderr)

    if results:  # how the escalating-context ladder resolved — the per-call token saving in practice
        tier_hist = Counter(r.grade_context_chars for r in results)
        still = sum(1 for r in results if r.full_text_would_help)
        ladder = " · ".join(f"{c:,}ch×{n}" for c, n in sorted(tier_hist.items()))
        print(f"[grade context] resolved at: {ladder}"
              + (f"  ({still} still flagged full_text_would_help at the top tier)" if still else ""),
              file=sys.stderr)

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


def _is_blank(value) -> bool:
    """True if an ENA cell is genuinely missing — empty, or placeholder-null text (``NA``, ``unknown``, …).

    The scalar counterpart of :func:`engine.backfill.strip_placeholders`, sharing its
    :data:`~engine.backfill.PLACEHOLDER_NULLS` vocabulary so "blank" means the same thing to the
    completeness gate and to the blank-only fill policy.
    """
    import re as _re

    from bac_metadata.bac_agentic_metadata.engine import backfill

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    key = _re.sub(r"\s+", " ", str(value).strip()).lower()
    return key in backfill.PLACEHOLDER_NULLS


def per_sample(
    *,
    base: pd.DataFrame,
    found_path: str | Path,
    fields: Sequence[str],
    accessions: Sequence[str] | None,
    out_path: Path,
    manual_supp_dir: str | Path | Sequence[str | Path],
    llm,
    model: str,
    caches: StageCaches,
    threshold: float = 0.75,
    ast_drugs: Sequence[str] | None = None,
    id_columns: Sequence[str] | None = None,
    manual_papers_dir: str | Path | None = None,
    category_vocab: dict[str, str] | None = None,
    paper_links: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Per-sample extraction from supplementary tables — the accurate per-isolate source, runs FIRST.

    Over every ENA-incomplete (gated) study with a paper (grade-independent gate), fetch + parse the
    paper's supplementary tables, let the extractor map columns→fields, and deterministically join rows
    to ENA ``sample_accession``. Emits per-sample fills (``method="per_sample"``) and one outcome row per
    target (direct / two_hop / abstained / NO_PMCID / NOT_IN_FOLD / NOT_REACHED) so a study is never silently
    dropped. ``base`` is the per-sample table already restricted to the selection.

    Two rules widen the target set beyond the completeness gate, both so a curator's work is never wasted:

    * **A study with a curator-provided local table is always a target** (David, 2026-07-10), even when ENA
      reports it ``>= threshold`` complete — otherwise a table we deliberately hunted down is never opened.
    * ``paper_links`` (the same map the grader uses, honouring ``--paper-source``) is a **fallback** for the
      PMCID when the finder came up empty — resolved via :func:`engine.europepmc.pmcid_for_link`. Without it
      a study whose paper the curated snapshot names is wrongly written off as ``NO_PMCID``.

    **Overwrite gate** (David, 2026-07-13): a per-sample fill always populates a BLANK ENA cell (when the
    table value parses to a real value), but may only OVERWRITE a genuine ENA value when robustly BETTER —
    on every field, gated or not (no free-overwrite bypass). Two layers: (1) parse-validity — a value must
    parse to a real value for its field (rejects table-null tokens like "NF"/"ND" and non-date
    collection_dates), else it is dropped and counted; (2) betterness — collection_date overwrites only with
    a strictly more specific date (year→year-month→full, deterministic via :mod:`engine.value_validity`),
    while country/isolation_source/host defer to :func:`engine.sample_extractor.judge_overwrite_fidelity`.
    """
    from bac_metadata.bac_agentic_metadata.engine import backfill, europepmc
    from bac_metadata.bac_agentic_metadata.engine import local_supplements as lsupp
    from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
    from bac_metadata.bac_agentic_metadata.engine import supplementary as supp

    caches.ensure()
    id_cols = tuple(id_columns) if id_columns else sx._ID_COLUMNS
    sets: dict[str, set[str]] = {}
    maps: dict[str, dict[str, str]] = {}
    for acc, g in base.groupby("study_accession"):
        maps[acc] = sx.build_accession_to_sample(g, id_columns=id_cols)
        sets[acc] = set(maps[acc])
    # The extractor emits fills with a placeholder ena_value=""; look up each sample's ACTUAL base value so
    # the overwrite guard (and the escalation residual) can tell a blank fill from an overwrite of real ENA.
    base_idx = base.drop_duplicates("sample_accession").set_index("sample_accession")

    found = pd.read_csv(found_path, sep="\t", dtype=str).fillna("")
    pmcid_of = {r["study_accession"]: r.get("chosen_pmcid", "").strip() for _, r in found.iterrows()}
    # Best scholarly identifier per study (DOI > PMCID > PMID) for the LAZY Tier-3 fulltext fetch — only
    # ever called when the extractor needs to decode a strong-alias column's opaque codes from the paper.
    link_of = {r["study_accession"]: (str(r.get("chosen_doi", "")).strip() or str(r.get("chosen_pmcid", "")).strip()
                                      or str(r.get("chosen_pmid", "")).strip()) for _, r in found.iterrows()}

    def _fulltext_thunk(a: str):
        """Return a zero-arg getter for study ``a``'s paper text (same resolver as grading; None if none)."""
        def _get() -> str | None:
            ft = resolve_fulltext_for_accession(a, link_of.get(a, ""), str(manual_papers_dir or ""),
                                                fulltext_cache=caches.fulltext)
            return ft.text if (ft and ft.text) else None
        return _get

    needs = backfill.gate_fields(backfill.field_completeness(base, fields=tuple(fields)),
                                 fields=tuple(fields), threshold=threshold)
    any_gated = needs.any(axis=1)
    gated = set(any_gated.index[any_gated])
    # A curator-provided table is always opened; where ENA is already complete the study is BLANK-ONLY.
    table_bearing = {a for a in sets if lsupp.find_local_supp_files(a, manual_supp_dir)}
    blank_only = table_bearing - gated
    if accessions:
        targets = [(a.strip(), pmcid_of.get(a.strip(), "")) for a in accessions if a.strip()]
    else:
        targets = [(a, pmcid_of.get(a, "")) for a in sorted(gated | table_bearing)]
    print(f"Per-sample over {len(targets)} studies ({len(gated)} gated at threshold {threshold}; "
          f"+{len(blank_only)} ungated-with-table, blank-only) with {model}", file=sys.stderr)

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
        # The finder can miss a paper the curated snapshot names; fall back to its link (DOI/PMID/URL).
        if not pmcid and paper_links and paper_links.get(acc):
            pmcid = europepmc.pmcid_for_link(paper_links[acc], cache_dir=caches.find) or ""
            if pmcid:
                print(f"[{i}/{len(targets)}] {acc} — PMCID {pmcid} recovered from the curated paper link",
                      file=sys.stderr)
        # Resolve any curator-provided supplementary table FIRST, so a manually-downloaded table can rescue
        # a paywalled (no-PMCID) study. Only skip when there is NEITHER an OA PMCID NOR a local supp table —
        # the previous `if not pmcid: continue` silently dropped local tables for exactly those studies.
        local = lsupp.resolve_local_supp_tables(acc, manual_supp_dir)
        if not pmcid and not local:
            outcome_rows.append(_synthetic(acc, "", "NO_PMCID",
                "no PMCID and no manual/committed supp table — cannot fetch supplementary; see missing-papers"))
            print(f"[{i}/{len(targets)}] {acc} — NO_PMCID (no OA + no local supp)", file=sys.stderr)
            continue
        tables = supp.parse_tables(pmcid, cache_dir=caches.per_sample_supp) if pmcid else []
        if local:
            tables = (tables or []) + local
            print(f"[{i}/{len(targets)}] {acc} — using {len(local)} local supp table(s)"
                  + ("" if pmcid else " (NO_PMCID; local supp only)"), file=sys.stderr)
        try:
            ex = sx.extract_study(acc, pmcid, tables, sets[acc], maps[acc], llm, model=model,
                                  fields=tuple(fields), ast_drugs=tuple(ast_drugs) if ast_drugs else None,
                                  category_vocab=category_vocab, get_fulltext=_fulltext_thunk(acc))
        except UsageLimitError as e:
            print(f"[{i}/{len(targets)}] {acc} — usage limit; stopping (cache holds the rest): {e}",
                  file=sys.stderr)
            for racc, rpmcid in targets[i - 1:]:
                outcome_rows.append(_synthetic(racc, rpmcid, "NOT_REACHED",
                    "not reached before usage limit; rerun to resume (cache fills the rest)"))
            break
        extractions.append(ex)
        for x in ex.fills:  # backfill the true ENA value (extractor left it "") so the guard can act
            sa, f = x.get("sample_accession"), x.get("field")
            if sa in base_idx.index and f in base_idx.columns:
                x["ena_value"] = str(base_idx.at[sa, f])
        ex_fills, note = ex.fills, ex.note
        # ── OVERWRITE GATE ────────────────────────────────────────────────────────────────────────
        # A table value may only OVERWRITE a genuine ENA value when it is robustly a BETTER value —
        # assessed on the parsed value, on every field (gated OR not; there is no free-overwrite bypass).
        #  Layer 1 (parse-validity): a value must parse to a REAL value for its field to be adopted at all
        #    (blank-fill or overwrite) — rejects table-null tokens ("NF"/"ND"/…) and non-date collection_dates.
        #  Layer 2 (betterness, overwrites only): collection_date is deterministic — adopt only a STRICTLY
        #    more specific date (year→year-month→full); the specimen-tuned judge is wrong for dates. country/
        #    isolation_source/host defer to the agentic judge_overwrite_fidelity (its prompt fits these).
        by_field: dict[str, list] = {}
        for x in ex_fills:
            by_field.setdefault(x.get("field"), []).append(x)
        kept: list[dict] = []
        overwrote: list[str] = []
        kept_ena: list[str] = []
        invalid: Counter = Counter()  # values dropped by Layer 1 (never a silent drop — surfaced in the note)
        for field, xs in by_field.items():
            if field not in fields:  # ast_* / non-core fields: keep verbatim (guard scoped to the metadata fields)
                kept.extend(xs)
                continue
            # Layer 1 — parse-validity for blank-fills (drop e.g. an "NF" that would fill a blank cell)
            for x in (x for x in xs if _is_blank(x.get("ena_value"))):
                if vv.parse_valid(field, x.get("applied_value")):
                    kept.append(x)
                else:
                    invalid[field] += 1
            # Layer 1 — parse-validity for overwrites of a genuine ENA value
            overwrites = []
            for x in (x for x in xs if not _is_blank(x.get("ena_value"))):
                if vv.parse_valid(field, x.get("applied_value")):
                    overwrites.append(x)
                else:
                    invalid[field] += 1
            if not overwrites:
                continue
            # Layer 2 — betterness
            if field == "collection_date":  # deterministic: overwrite only with a STRICTLY more specific date
                better = [x for x in overwrites
                          if vv.parse_date_scalar(x.get("applied_value"))[1] > vv.parse_date_scalar(x.get("ena_value"))[1]]
                kept.extend(better)
                if better:
                    overwrote.append(f"{field}×{len(better)}(more-specific)")
                if len(better) < len(overwrites):
                    kept_ena.append(f"{field}×{len(overwrites) - len(better)}")
            else:  # country / isolation_source / host — the agentic fidelity judge, always
                improves, why = sx.judge_overwrite_fidelity(
                    field, [(x.get("ena_value"), x.get("applied_value")) for x in overwrites], llm, model=model)
                if improves:
                    kept.extend(overwrites)
                    overwrote.append(f"{field}×{len(overwrites)}({why[:32]})")
                else:
                    kept_ena.append(f"{field}×{len(overwrites)}")
        if len(kept) != len(ex_fills):
            note = (f"{note}; overwrite guard: {len(kept)}/{len(ex_fills)} fills kept"
                    + (f"; overwrote {', '.join(overwrote)}" if overwrote else "")
                    + (f"; kept ENA over table on {', '.join(kept_ena)}" if kept_ena else "")
                    + (f"; dropped {sum(invalid.values())} invalid ({dict(invalid)})" if invalid else ""))
        ex_fills = kept
        fills.extend(ex_fills)
        outcome_rows.append({
            "study_accession": ex.study_accession, "pmcid": ex.pmcid, "table": ex.table,
            "method": ("two_hop" if any(f["method"] == "per_sample_two_hop" for f in ex_fills)
                       else "direct" if ex_fills else "abstained"),
            "n_samples": ex.n_samples_mapped, "n_fills": len(ex_fills),
            "confidence": ex.confidence, "note": note,
        })
        print(f"[{i}/{len(targets)}] {acc} ({pmcid}) — {note} [conf={ex.confidence}] cols={ex.columns}",
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
    needs = backfill.gate_fields(completeness, fields=fields, threshold=threshold)
    per_sample_df = None
    if per_sample_path and Path(per_sample_path).exists():
        per_sample_df = pd.read_csv(per_sample_path, sep="\t", dtype=str)
        ps_filled, ps_het = backfill.per_sample_guards(per_sample_df, fields=fields)
        print(f"Per-sample guard: {sum(len(v) for v in ps_filled.values())} cells already filled; "
              f"{len(ps_het)} (study×field) blocked as per-sample-heterogeneous", file=sys.stderr)
    applied = backfill.apply_whole_field(base, proposals, needs, fields=fields, per_sample=per_sample_df)
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


# ── Escalation tier — ask the curator on tight whole-field near-misses (runs after the main pipeline) ──

#: The decision-queue schema written by escalate_detect and read by escalate_apply (empty answer columns
#: for the curator to fill).
ESCALATION_QUEUE_COLUMNS = [
    "study_accession", "field", "gap_samples", "escalate_trigger", "resolution", "cluster_theme",
    "suggested_value", "region_hint", "grader_quote", "paper_excerpt", "fulltext_status", "answer", "answer_note",
]

#: A study at/above this fraction of the WHOLE cohort's taxon samples is a "big decision" — its whole-field
#: call always escalates (David, 2026-06-26), regardless of the tight/wide triage. A leverage-based, LLM-free
#: safety net so a single large study can never silently swing the global completeness metric.
BIG_DECISION_FRAC = 0.01

#: The auto-skip marker written into a wide-mix row's ``answer_note`` when ``auto_skip_wide`` is on. Contains
#: "skip" so both the interactive walk (``_resolved``) and run-health (``_rejected``) treat it as a decided
#: cell (never a lingering ACTIONABLE), while ``escalate_apply`` ignores it (no fill — a wide mix has no value).
AUTO_SKIP_NOTE = "auto-skip: wide mix — no single whole-study value (triage=wide_mix_skip)"


def apply_auto_skip_wide(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Record every still-unresolved ``wide_mix_skip`` row as an auto-skip so it drops out of the curator walk.

    Only touches rows with a blank answer AND a blank note — a real curator answer or a re-injected/prior
    decision is never overwritten. Returns ``(frame, n_auto_skipped)``.
    """
    if not len(frame):
        return frame, 0
    blank_ans = frame["answer"].fillna("").astype(str).str.strip() == ""
    blank_note = frame["answer_note"].fillna("").astype(str).str.strip() == ""
    mask = blank_ans & blank_note & (frame["resolution"].astype(str) == "wide_mix_skip")
    frame = frame.copy()
    frame.loc[mask, "answer_note"] = AUTO_SKIP_NOTE
    return frame, int(mask.sum())


def cohort_study_samples(sizing_path: str | Path) -> tuple[dict[str, int], int]:
    """Return ``({study: taxon_samples}, cohort_total)`` over the WHOLE cohort from the sizing table."""
    sizing = pd.read_csv(sizing_path, sep="\t")
    n = pd.to_numeric(sizing["ena_taxon_samples"], errors="coerce").fillna(0).astype(int)
    samples = dict(zip(sizing["study_accession"].astype(str), n, strict=False))
    return samples, int(n.sum())


def _post_per_sample_gap(per_sample_path: str | Path | None, raw: pd.DataFrame,
                         fields: Sequence[str]) -> dict[tuple[str, str], int]:
    """Blank ENA cells per ``(study, field)`` REMAINING after per-sample fills — the escalation residual.

    Per-sample runs first; the whole-field/escalation tier should only weigh what it left. Starting from
    the raw gap (:func:`engine.escalation.field_gap`), subtract, per ``(study, field)``, the distinct
    samples per-sample filled **from a genuinely-blank ENA cell** (``ena_value`` placeholder-null) — those
    are the cells per-sample newly resolved. A fill that overwrote an existing ENA value never reduces the
    blank count. The result is the deterministic input to the escalation candidacy gate.
    """
    from bac_metadata.bac_agentic_metadata.engine import escalation

    gap = dict(escalation.field_gap(raw, tuple(fields)))
    if not per_sample_path or not Path(per_sample_path).exists():
        return gap
    mb = pd.read_csv(per_sample_path, sep="\t", dtype=str, keep_default_na=False)
    if not {"study_accession", "field", "sample_accession"} <= set(mb.columns) or not len(mb):
        return gap
    if "ena_value" in mb.columns:  # only fills into a blank ENA cell reduce the blank count
        mb = mb[mb["ena_value"].map(_is_blank)]
    filled = mb.groupby(["study_accession", "field"])["sample_accession"].nunique()
    for (acc, f), k in filled.items():
        key = (str(acc), f)
        if key in gap:
            gap[key] = max(0, gap[key] - int(k))
    return gap


def _load_grade_records(grades_jsonl: str | Path, keep: set[str]) -> list[dict]:
    """Read the grader JSONL (full records, with the backfill map) for studies in ``keep``."""
    import json

    p = Path(grades_jsonl)
    if not p.exists():
        sys.exit(f"Grades JSONL not found: {p} (detect needs the full JSONL, not the flat TSV).")
    records: list[dict] = []
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("study_accession") in keep:
                records.append(r)
    return records


def _escalation_evidence_fn(*, paper_links: Mapping[str, str], classifications: Mapping[str, dict],
                            sizing_path: str | Path, manual_papers_dir: str | Path, caches: StageCaches):
    """Build ``accession -> StudyEvidence`` reusing the grader's cached fulltext / ENA / sizing lookups."""
    from bac_metadata.bac_agentic_metadata.engine import escalation

    sizing = pd.read_csv(sizing_path, sep="\t", dtype=str).set_index("study_accession")
    caches.fulltext.mkdir(parents=True, exist_ok=True)

    def evidence_for(acc: str) -> escalation.StudyEvidence:
        # SAME fulltext resolution as grading (incl. the manual-PDF fallback) so the triage is never blind
        # on a paywalled study the grader read from a local PDF.
        ft = resolve_fulltext_for_accession(acc, paper_links.get(acc, ""), manual_papers_dir,
                                             fulltext_cache=caches.fulltext)
        study = study_title_and_description(acc, cache_dir=caches.ena)
        srow = sizing.loc[acc].to_dict() if acc in sizing.index else {}
        sizing_row = {
            "ena_taxon_samples": srow.get("ena_taxon_samples"),
            "ena_total_samples": srow.get("ena_total_samples"),
            "ena_total_runs": srow.get("ena_total_runs"),
            "by_scientific_name": srow.get("by_scientific_name"),
            **classifications.get(acc, {}),
        }
        return escalation.StudyEvidence(fulltext=ft, ena_title=study["study_title"],
                                        ena_description=study["study_description"], sizing_row=sizing_row)

    return evidence_for


def _items_to_queue_frame(items) -> pd.DataFrame:
    """Render escalation items to the queue TSV schema (empty answer columns for the curator)."""
    rows = [{
        "study_accession": it.study_accession, "field": it.field, "gap_samples": it.gap_samples,
        "escalate_trigger": it.escalate_trigger, "resolution": it.resolution, "cluster_theme": it.cluster_theme,
        "suggested_value": it.suggested_value, "region_hint": it.region_hint, "grader_quote": it.grader_quote,
        "paper_excerpt": it.paper_excerpt, "fulltext_status": it.fulltext_status, "answer": "", "answer_note": "",
    } for it in items]
    return pd.DataFrame(rows, columns=ESCALATION_QUEUE_COLUMNS)


def _preserve_prior_answers(frame: pd.DataFrame, output: Path) -> pd.DataFrame:
    """Carry curator-filled answers from an existing queue into the freshly-detected one.

    Detect regenerates the queue on every run; without this it would silently wipe answers the curator
    already gave. Answers are matched by ``(study_accession, field)``: a still-escalated question keeps its
    answer, a question that no longer escalates is dropped (logged loudly), a brand-new question starts empty.
    """
    if not output.exists():
        return frame
    prior = pd.read_csv(output, sep="\t", dtype=str).fillna("")
    if "answer" not in prior.columns:
        return frame
    prior_ans = {(r["study_accession"], r["field"]): (r.get("answer", ""), r.get("answer_note", ""))
                 for _, r in prior.iterrows() if str(r.get("answer", "")).strip()}
    if not prior_ans:
        return frame
    new_keys = {(r["study_accession"], r["field"]) for _, r in frame.iterrows()}
    carried = 0
    for idx, r in frame.iterrows():
        k = (r["study_accession"], r["field"])
        if k in prior_ans:
            frame.at[idx, "answer"], frame.at[idx, "answer_note"] = prior_ans[k]
            carried += 1
    undetected = sorted(k for k in prior_ans if k not in new_keys)
    print(f"  [preserve] carried {carried} prior curator answer(s) into the regenerated queue; "
          f"{len(undetected)} previously-answered question(s) no longer freshly detect"
          + (f" → re-inject handles any still gated: {undetected}" if undetected else ""), file=sys.stderr)
    return frame


def _carry_forward_resolved(frame: pd.DataFrame, store_path: str | Path) -> pd.DataFrame:
    """Carry RESOLVED decisions (answered or reject/skip note) from the cross-batch escalation master.

    So a ``(study, field)`` the curator decided in an EARLIER batch is never re-asked: its answer/note is
    slotted into this batch's freshly-detected queue. Only still-blank rows of THIS queue are touched (the
    same-tag preserve ran first). A no-op when the master store is absent (the first batch).
    """
    store_path = Path(store_path)
    if not store_path.exists() or not len(frame):
        return frame
    store = pd.read_csv(store_path, sep="\t", dtype=str).fillna("")
    if not {"study_accession", "field"} <= set(store.columns):
        return frame
    markers = ("reject", "skip", "undeterm", "leave uncoded", "no value")

    def _resolved(ans: object, note: object) -> bool:
        return bool(str(ans).strip()) or any(w in str(note).lower() for w in markers)

    prior = {(r["study_accession"], r["field"]): (r.get("answer", ""), r.get("answer_note", ""))
             for _, r in store.iterrows() if _resolved(r.get("answer", ""), r.get("answer_note", ""))}
    carried = 0
    for idx, r in frame.iterrows():
        if _resolved(r.get("answer", ""), r.get("answer_note", "")):
            continue  # this batch's own queue already resolved it (preserve ran first)
        k = (r["study_accession"], r["field"])
        if k in prior:
            frame.at[idx, "answer"], frame.at[idx, "answer_note"] = prior[k]
            carried += 1
    if carried:
        print(f"  [carry-forward] {carried} decision(s) carried from the escalation master "
              "(decided in an earlier batch — not re-asked)", file=sys.stderr)
    return frame


def _reinject_resolved_still_gated(
    frame: pd.DataFrame, *, sources: Sequence[str | Path | None], keep: set[str],
    post_gap: Mapping[tuple[str, str], int], n_records: Mapping[str, int], threshold: int,
) -> pd.DataFrame:
    """Re-apply resolved curator decisions still gated after per-sample but no longer freshly detected.

    :func:`_preserve_prior_answers` / :func:`_carry_forward_resolved` only fill rows the fresh (now
    deterministic) detection produced. A decision leaves detection when per-sample lifts its field over the
    completeness gate — but if a residual remains, the curator's committed whole-field value must still fill
    it. This appends such decisions (answered, or skip/reject-noted) as queue rows so :func:`escalate_apply`
    fills the remainder, keyed on the same-tag queue + the version-controlled escalations master (same-tag
    precedence). Without it a decision silently lapses the moment its trigger stops firing — the loss that
    left ~3.7k curator-decided cells blank when the cohort grew past a study's big-decision line.

    Parameters
    ----------
    frame
        The freshly-detected queue (post preserve/carry-forward).
    sources
        Prior answer sources in precedence order (earlier wins) — typically ``[same_tag_queue, master]``.
    keep
        Studies in this selection; a decision for a study outside it is ignored (no cross-tag leakage).
    post_gap, n_records, threshold
        The residual map and per-study denominator; a decision is re-applied only while its field still has
        a blank cell (``post_gap > 0``) — if per-sample filled the whole field there is nothing to re-apply.
    """
    markers = ("reject", "skip", "undeterm", "leave uncoded", "no value")

    def _resolved(ans: object, note: object) -> bool:
        return bool(str(ans).strip()) or any(w in str(note).lower() for w in markers)

    present = {(str(r["study_accession"]), str(r["field"])) for _, r in frame.iterrows()}
    resolved: dict[tuple[str, str], tuple[str, str]] = {}
    for src in sources:
        if not src or not Path(src).exists():
            continue
        d = pd.read_csv(src, sep="\t", dtype=str).fillna("")
        if not {"study_accession", "field"} <= set(d.columns):
            continue
        for _, r in d.iterrows():
            ans, note = r.get("answer", ""), r.get("answer_note", "")
            if _resolved(ans, note):
                resolved.setdefault((str(r["study_accession"]), str(r["field"])), (ans, note))
    rows = []
    for (acc, f), (ans, note) in resolved.items():
        if (acc, f) in present or acc not in keep or int(post_gap.get((acc, f), 0)) <= 0:
            continue
        rows.append({
            "study_accession": acc, "field": f, "gap_samples": int(post_gap[(acc, f)]),
            "escalate_trigger": "reinjected_committed_decision", "resolution": "", "cluster_theme": "",
            "suggested_value": "", "region_hint": "", "grader_quote": "", "paper_excerpt": "", "fulltext_status": "",
            "answer": ans, "answer_note": note,
        })
    if rows:
        add = pd.DataFrame(rows, columns=ESCALATION_QUEUE_COLUMNS)
        frame = pd.concat([frame, add], ignore_index=True) if len(frame) else add
        answered = sum(1 for r in rows if str(r["answer"]).strip())
        print(f"  [re-inject] {len(rows)} committed decision(s) still gated after per-sample but no longer "
              f"freshly detected, re-applied ({answered} with a fill value); "
              f"studies: {sorted({r['study_accession'] for r in rows})}", file=sys.stderr)
    return frame


def escalate_detect(
    *,
    spec: AttributeSpec,
    base: pd.DataFrame,
    keep: Sequence[str],
    grades_jsonl: str | Path,
    per_sample_path: str | Path | None,
    sizing_path: str | Path,
    paper_links: Mapping[str, str],
    classifications: Mapping[str, dict],
    manual_papers_dir: str | Path,
    fields: Sequence[str],
    out_path: Path,
    llm,
    model: str,
    caches: StageCaches,
    threshold: int = 50,
    frac: float = 0.75,
    big_decision_frac: float = BIG_DECISION_FRAC,
    auto_skip_wide: bool = False,
    escalations_master_path: str | Path | None = None,
    cohort_taxon_samples: Mapping[str, int] | None = None,
    cohort_taxon_total: int | None = None,
) -> pd.DataFrame:
    """Detect whole-field near-misses worth a human decision; write the curator decision queue.

    Candidacy is deterministic: a grader-declined field still below ``frac`` complete (and over ``threshold``
    residual samples) **after** per-sample fills is queued — no LLM-triage or cohort-size dependence (see
    :func:`engine.escalation.detect_whole_field_escalations`). ``base`` is the raw per-sample table already
    restricted to the selection. Writes ``decisions_needed_<tag>.tsv`` (sorted by residual ``gap_samples``
    desc). Committed answers are made **sticky**: any resolved decision in the same-tag queue or the
    version-controlled escalations master whose field is still gated is re-applied even when it no longer
    freshly detects (:func:`_reinject_resolved_still_gated`) — so a human decision is never silently dropped.
    """
    from bac_metadata.bac_agentic_metadata.engine import escalation

    caches.ensure()
    fields = tuple(fields)
    keep = set(keep)
    raw = base[base["study_accession"].isin(keep)].copy()
    grades = _load_grade_records(grades_jsonl, keep)
    post_gap = _post_per_sample_gap(per_sample_path, raw, fields)  # residual per-sample left (candidacy input)
    n_records = raw.groupby("study_accession").size().to_dict()
    still_gated = sum(1 for (a, _f), g in post_gap.items() if a in keep and g > threshold)
    # Big-decision leverage = fraction of the WHOLE cohort (audit tag only now). In tail/batch mode
    # sizing_path is batch-local (its total would make every >1%-of-batch study look "big"), so the driver
    # passes the whole-cohort taxon counts explicitly; fall back to the sizing file (splits mode).
    if cohort_taxon_samples is not None and cohort_taxon_total:
        study_samples, cohort_total = dict(cohort_taxon_samples), int(cohort_taxon_total)
    else:
        study_samples, cohort_total = cohort_study_samples(sizing_path)
    big = sorted(a for a in keep if cohort_total and study_samples.get(a, 0) / cohort_total >= big_decision_frac)
    print(f"Scanning {len(grades)} graded studies / {len(raw)} ENA rows "
          f"(residual floor {threshold} samples, completeness gate {frac:.0%}; {still_gated} (study×field) "
          f"still gated after per-sample; cohort total {cohort_total} samples, big-decision "
          f"(>={big_decision_frac:.0%}) studies: {big or 'none'})", file=sys.stderr)

    evidence_fn = _escalation_evidence_fn(
        paper_links=paper_links, classifications=classifications, sizing_path=sizing_path,
        manual_papers_dir=manual_papers_dir, caches=caches,
    )
    items = escalation.detect_whole_field_escalations(
        grades, raw, spec, llm, evidence_fn, fields=fields, threshold=threshold, frac=frac,
        post_gap=post_gap, n_records=n_records, model=model, study_samples=study_samples,
        cohort_total_samples=cohort_total, big_decision_frac=big_decision_frac,
    )
    frame = _items_to_queue_frame(items)
    frame = _preserve_prior_answers(frame, Path(out_path))  # fill freshly-detected rows from the prior queue
    if escalations_master_path:  # cross-batch: never re-ask a decision made in an earlier batch
        frame = _carry_forward_resolved(frame, escalations_master_path)
    # Sticky: re-apply any resolved decision whose field is STILL gated post-per-sample but no longer freshly
    # detects — the data-loss point the old preserve/carry-forward (which only touch detected rows) missed.
    frame = _reinject_resolved_still_gated(
        frame, sources=[Path(out_path), escalations_master_path], keep=keep, post_gap=post_gap,
        n_records=n_records, threshold=threshold,
    )
    if len(frame):  # stable highest-residual-first order (append-independent → byte-reproducible queue)
        frame = frame.sort_values(
            ["gap_samples", "study_accession", "field"],
            key=lambda s: pd.to_numeric(s, errors="coerce") if s.name == "gap_samples" else s,
            ascending=[False, True, True],
        ).reset_index(drop=True)
    n_auto = 0
    if auto_skip_wide:  # once the triage is trusted, record wide mixes as skips so only real decisions surface
        frame, n_auto = apply_auto_skip_wide(frame)
    frame.to_csv(out_path, sep="\t", index=False)
    still_pending = sum(
        1 for _, r in frame.iterrows()
        if str(r.get("answer", "")).strip() == ""
        and not any(w in str(r.get("answer_note", "")).lower()
                    for w in ("reject", "skip", "undeterm", "leave uncoded", "no value"))
    ) if len(frame) else 0
    print(f"Wrote {Path(out_path).name}: {len(frame)} escalation(s) "
          f"({int(frame['gap_samples'].sum()) if len(frame) else 0} gap samples)"
          + (f"; {n_auto} wide-mix auto-skipped, {still_pending} decision(s) remain for review"
             if auto_skip_wide else ""), file=sys.stderr)
    if len(frame):
        print("\nTop escalations (study · field · gap · suggested · theme):", file=sys.stderr)
        for _, r in frame.head(12).iterrows():
            print(f"  {r['study_accession']:<14} {r['field']:<16} {r['gap_samples']:>5}  "
                  f"→ {r['suggested_value'] or '(none)':<12} {r['cluster_theme'][:60]}", file=sys.stderr)
    return frame


def escalate_apply(*, base: pd.DataFrame, keep: Sequence[str], queue_path: str | Path, out_path: Path) -> pd.DataFrame:
    """Apply a curator-filled decision queue as whole-field fills through the existing backfill path.

    Drops blank-answer rows; gates every answered field as "needs backfill" so a curator decision is
    authoritative regardless of how full ENA already is. Writes ``escalation_applied_<tag>.tsv``
    (``method="curator_escalation"`` — auditable and distinct from grader ``whole_field``).
    """
    from bac_metadata.bac_agentic_metadata.engine import backfill, escalation

    queue_path = Path(queue_path)
    if not queue_path.exists():
        print(f"  [escalate-apply] no queue at {queue_path.name}; nothing to apply.", file=sys.stderr)
        return pd.DataFrame()
    queue = pd.read_csv(queue_path, sep="\t", dtype=str).fillna("")
    answered = queue[queue["answer"].astype(str).str.strip() != ""]
    if not len(answered):
        print(f"  [escalate-apply] no filled answers in {queue_path.name}; nothing to apply.", file=sys.stderr)
        return pd.DataFrame()

    keep = set(keep)
    raw = base[base["study_accession"].isin(keep)].copy()
    proposals = escalation.answers_to_proposals(answered.to_dict("records"))
    fields = tuple(sorted({str(f) for f in answered["field"]}))
    studies = raw["study_accession"].unique()
    needs = pd.DataFrame(
        {f: [acc in proposals and f in proposals[acc] for acc in studies] for f in fields},
        index=pd.Index(studies, name="study_accession"),
    )
    applied = backfill.apply_whole_field(raw, proposals, needs, fields=fields)
    applied["method"] = "curator_escalation"
    applied.to_csv(out_path, sep="\t", index=False)
    print(f"Wrote {Path(out_path).name}: {len(applied)} per-sample fills from {len(answered)} curator "
          f"decision(s).", file=sys.stderr)
    return applied


# ── Fill the metadata table — substitute the agent's found values into the full-width base table ───────

def _load_precedence_fills(paths: Mapping[str, str | Path | None]) -> pd.DataFrame:
    """Concatenate the applied-fill tables and resolve to one winning fill per (sample, field).

    Each input row carries a ``method`` (``per_sample``/``per_sample_two_hop``/``curator_escalation``/
    ``whole_field``); strip placeholder applied-values, rank by source precedence, and keep the single
    highest-precedence non-blank fill per (sample_accession, field).
    """
    from bac_metadata.bac_agentic_metadata.engine import backfill

    frames = []
    for label, path in paths.items():
        if not path or not Path(path).exists():
            print(f"  [fills] {label}: absent ({path}) — skipped", file=sys.stderr)
            continue
        df = pd.read_csv(path, sep="\t", dtype=str)
        need = {"sample_accession", "field", "applied_value", "method", "study_accession"}
        if not need <= set(df.columns):
            sys.exit(f"{path} missing columns: {sorted(need - set(df.columns))}")
        frames.append(df[["study_accession", "sample_accession", "field", "ena_value",
                          "applied_value", "method"]].copy())
    if not frames:
        return pd.DataFrame(columns=["study_accession", "sample_accession", "field", "ena_value",
                                     "applied_value", "method", "_rank"])
    return backfill.apply_precedence_merge(frames, rank=backfill.PRECEDENCE_DEFAULT)


def _load_study_grade_columns(grades_path: str | Path | None, studies: set[str],
                              study_grade_columns: Mapping[str, str]) -> pd.DataFrame:
    """Return per-study graded values for the broadcast study-level columns (placeholder-stripped)."""
    from bac_metadata.bac_agentic_metadata.engine import backfill

    cols = list(study_grade_columns)
    if not grades_path or not Path(grades_path).exists():
        print(f"  [grades] absent ({grades_path}) — study-level columns will be blank", file=sys.stderr)
        return pd.DataFrame(columns=["study_accession", *cols])
    g = pd.read_csv(grades_path, sep="\t", dtype=str)
    g = g[g["study_accession"].isin(studies)].drop_duplicates("study_accession")
    out = pd.DataFrame({"study_accession": g["study_accession"]})
    for col, src in study_grade_columns.items():
        out[col] = backfill.strip_placeholders(g[src]) if src in g.columns else pd.NA
    return out.reset_index(drop=True)


def fill_metadata_table(
    *,
    base: pd.DataFrame,
    fields: Sequence[str],
    fill_paths: Mapping[str, str | Path | None],
    grades_path: str | Path | None,
    study_grade_columns: Mapping[str, str],
    out_path: Path,
    tag: str,
    fold_label: str = "",
) -> pd.DataFrame:
    """Substitute the agent's found values into the full-width base table — the PRODUCTION output.

    For each per-sample field the agent value REPLACES the ENA-deposited value with precedence
    ``per-sample > curator-escalation > whole-field > ENA``; the two study-wide sources only ever filled
    blanks (the backfill parsimony guard), so the only replacements of a real ENA value come from
    per-sample. Adds the broadcast study-level columns (``study_grade_columns``). ``base`` is the full-width
    per-sample table already restricted to the selection. Writes ``filled_metadata_<tag>.tsv`` + a
    long-format provenance sidecar + a summary; nothing is silently overwritten.
    """
    from bac_metadata.bac_agentic_metadata.engine import backfill

    fields = list(fields)
    out_path = Path(out_path)
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base.drop_duplicates("sample_accession").copy()
    studies = set(base["study_accession"])
    print(f"Filling metadata table (full width): {len(base)} samples, {len(base.columns)} columns, "
          f"{len(studies)} studies", file=sys.stderr)

    fills = _load_precedence_fills(fill_paths)
    grades = _load_study_grade_columns(grades_path, studies, study_grade_columns)

    prov_rows: list[pd.DataFrame] = []
    summary: list[dict[str, object]] = []
    filled = base.copy()
    base_idx_value = {f: backfill.strip_placeholders(base.set_index("sample_accession")[f])
                      if f in base.columns else pd.Series(dtype="string") for f in fields}

    for f in fields:
        ff = fills[fills["field"] == f]
        val_map = dict(zip(ff["sample_accession"], ff["applied_value"], strict=False))
        src_map = dict(zip(ff["sample_accession"], ff["method"], strict=False))
        base_real = base_idx_value[f]

        samp = filled["sample_accession"]
        fill_val = samp.map(val_map)
        base_val = samp.map(base_real)
        final_val = fill_val.where(fill_val.notna(), base_val)
        filled[f] = final_val

        has_fill = fill_val.notna()
        prov = pd.DataFrame({
            "study_accession": filled["study_accession"][has_fill].to_numpy(),
            "sample_accession": samp[has_fill].to_numpy(),
            "field": f,
            "ena_value": base_val[has_fill].to_numpy(),
            "filled_value": fill_val[has_fill].to_numpy(),
            "source": samp[has_fill].map(src_map).to_numpy(),
        })
        prov_rows.append(prov)

        n = len(filled)
        base_present = base_val.notna()
        filled_present = final_val.notna()
        overrides = int((has_fill & base_present).sum())
        new_fills = int((has_fill & ~base_present).sum())
        by_src = prov["source"].value_counts().to_dict()
        summary.append({
            "field": f, "n_samples": n,
            "base_complete": round(float(base_present.mean()), 4),
            "filled_complete": round(float(filled_present.mean()), 4),
            "agent_fills": int(has_fill.sum()), "new_fills": new_fills, "overrides": overrides,
            "per_sample": int(by_src.get("per_sample", 0) + by_src.get("per_sample_two_hop", 0)),
            "curator_escalation": int(by_src.get("curator_escalation", 0)),
            "whole_field": int(by_src.get("whole_field", 0)),
        })

    grade_map = grades.set_index("study_accession") if not grades.empty else pd.DataFrame()
    grade_summary: list[dict[str, object]] = []
    for col in study_grade_columns:
        gser = grade_map[col] if col in grade_map.columns else pd.Series(dtype="string")
        filled[col] = filled["study_accession"].map(gser)
        present = filled[col].notna()
        graded_studies = int(grade_map[col].notna().sum()) if col in grade_map.columns else 0
        grade_summary.append({"field": col, "graded_studies": graded_studies,
                              "samples_filled": int(present.sum()),
                              "values": dict(filled.loc[present, col].value_counts())})

    provenance = pd.concat(prov_rows, ignore_index=True) if prov_rows else pd.DataFrame()
    res = pd.DataFrame(summary)
    # Provenance + summary sit beside the final table (the folder encodes the tag under the run_progress layout,
    # so they derive from out_path's stem rather than re-appending _<tag>).
    prov_path = out_path.with_name(out_path.stem + "_provenance.tsv")
    md_path = out_path.with_name(out_path.stem + "_summary.md")
    filled.to_csv(out_path, sep="\t", index=False)
    provenance.to_csv(prov_path, sep="\t", index=False)

    md = [f"# Filled metadata table — {fold_label or tag} (tag `{tag}`)\n",
          f"Studies: **{len(studies)}**; samples: **{len(filled)}**. The per-sample clinical fields in the "
          "full-width base table have been substituted with the agent's found values (precedence "
          "**per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank ENA cell; "
          "`overrides` replaced a real ENA value (only per-sample does this). Completeness is "
          "placeholder-stripped.\n",
          "| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        md.append(f"| {r['field']} | {r['base_complete']:.3f} | **{r['filled_complete']:.3f}** | "
                  f"{r['agent_fills']} | {r['new_fills']} | {r['overrides']} | {r['per_sample']} | "
                  f"{r['curator_escalation']} | {r['whole_field']} |")
    if study_grade_columns:
        md += ["\n## Study-level grades (broadcast to every sample in the study)\n",
               "| column | graded studies | samples filled | value distribution |", "|---|---|---|---|"]
        for gs in grade_summary:
            dist = ", ".join(f"{k} {v}" for k, v in gs["values"].items()) or "—"
            md.append(f"| {gs['field']} | {gs['graded_studies']} | {gs['samples_filled']} | {dist} |")
    md_path.write_text("\n".join(md) + "\n")

    print(res.to_string(index=False), file=sys.stderr)
    print(f"\nWrote:\n  {out_path}\n  {prov_path}\n  {md_path}", file=sys.stderr)
    return filled


def study_grade_columns(spec: AttributeSpec) -> dict[str, str]:
    """Study-level grades broadcast to every sample as new columns (col name -> ``<field>__value``).

    Spec-driven, not hardcoded: a study-level attribute is broadcast when it is gradeable for the WHOLE
    project (declares ``ground_truth`` + ``values``) and applies unconditionally (no ``applies_when``,
    no ``note`` caveat). For Klebsiella this resolves to ``study_setting`` + ``amr_study`` — the two
    metadata_v2 study-level columns — reproducing the former ``build_enriched_table`` behaviour.

    Shared home (was ``run_full_metadata_agent._study_grade_columns``) so the driver, ``fill_for_tag``, and
    the standalone ``cli.fill`` all build the broadcast columns identically without importing the driver.
    """
    study_level = spec.raw.get("attributes", {}).get("study_level", {})
    out: dict[str, str] = {}
    for field, body in study_level.items():
        if not isinstance(body, dict):
            continue
        if {"ground_truth", "values"} <= set(body) and "applies_when" not in body and "note" not in body:
            out[field] = f"{field}__value"
    return out


def fill_for_tag(
    *,
    data_dir: str | Path,
    spec: AttributeSpec,
    base: pd.DataFrame,
    fields: Sequence[str],
    tag: str,
    fold_label: str = "",
) -> pd.DataFrame:
    """Rebuild ``filled_metadata_<tag>.tsv`` from the tag's current applied files — the ONE fill code path.

    Derives the standard per-tag artifact paths under ``data_dir`` (exactly the ones the driver writes),
    builds ``study_grade_columns`` from the spec, and delegates to :func:`fill_metadata_table`. The driver's
    fill stage, the standalone ``escalate --apply``, and ``cli.fill`` all go through here, so a curator
    answer can never be applied without the final table being rebuilt to fold it in — the class of
    silent-staleness bug the escalation-conservation gate exists to catch. ``base`` must already be
    restricted to the tag's FULL study universe (a subset would silently shrink the final table).
    """
    from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

    rp = RunPaths(data_dir, tag)
    return fill_metadata_table(
        base=base, fields=fields,
        fill_paths={
            "per_sample": rp.per_sample_applied,
            "escalation": rp.escalation_applied,
            "whole_field": rp.backfill_applied,
        },
        grades_path=rp.study_grades_tsv,
        study_grade_columns=study_grade_columns(spec),
        out_path=rp.filled_metadata,
        tag=tag, fold_label=fold_label,
    )


# ── Curator-loop helpers — worklists + attaching hand-downloaded papers ────────────────────────────────

def missing_papers(*, grades_jsonl: Path, found_path: Path, gap_report_path: Path, sizing_path: Path,
                   manual_papers_dir: Path, out_dir: Path, paper_links: Mapping[str, str],
                   report_prefix: str = "missing_papers_report") -> pd.DataFrame:
    """Build the gap-weighted manual-fetch worklist of paywalled / no-full-text papers."""
    from bac_metadata.bac_agentic_metadata.engine.missing_papers import build_missing_papers

    return build_missing_papers(
        grades_path=grades_jsonl, found_path=found_path, gap_report_path=gap_report_path,
        sizing_path=sizing_path, manual_dir=manual_papers_dir, out_dir=out_dir,
        report_prefix=report_prefix, paper_links=paper_links,
    )


def persample_supplement(*, data_dir: Path, paper_links: Mapping[str, str], caches: StageCaches,
                         manual_papers_dir: Path, fields: Sequence[str], tag: str, min_gap: int = 50,
                         backend: str = "subscription", model: str) -> pd.DataFrame:
    """Build the per-sample supplementary worklist (the manual-table curator queue)."""
    from bac_metadata.bac_agentic_metadata.engine.persample_supplement_worklist import (
        build_persample_supplement_worklist,
    )

    return build_persample_supplement_worklist(
        data_dir, paper_links=paper_links, fulltext_cache=caches.fulltext,
        manual_papers_dir=manual_papers_dir, llm_cache=caches.llm, tag=tag, min_gap=min_gap,
        backend=backend, model=model, fields=tuple(fields),
    )


def run_health(*, data_dir: Path, fields: Sequence[str], fold: str, tag: str,
               spec: AttributeSpec | None = None) -> str:
    """Aggregate every stage artifact into the per-(study × field) health grid + convergence verdict.

    ``spec`` (when supplied) provides the application ``big_decision_frac`` gate so run-health's big-decision
    audit uses the SAME threshold as detection/escalation (the yaml constants file); omitted → engine default.
    """
    from bac_metadata.bac_agentic_metadata.engine.run_health_report import BIG_DECISION_FRAC, build_run_health

    res, verdict = build_run_health(
        data_dir, tuple(fields), fold=fold, tag=tag,
        big_decision_frac=spec.escalation_big_decision_frac if spec is not None else BIG_DECISION_FRAC,
    )
    print(f"Wrote run_progress/{tag}/run_health/report.{{md,tsv}} — VERDICT: {verdict}", file=sys.stderr)
    if len(res):
        print(res["resolution_state"].value_counts().to_string(), file=sys.stderr)
    return verdict


def _norm_id(s: str) -> str:
    """Lowercase, alphanumeric-only — a publisher-agnostic key for DOIs/PIIs/filenames."""
    import re

    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _accession_keys(row: pd.Series) -> set[str]:
    """Normalised identifier keys for an accession (DOI full + suffix, URL last segment, pmid)."""
    keys: set[str] = set()
    doi = str(row.get("doi", "")).strip()
    if doi:
        keys.add(_norm_id(doi))
        keys.add(_norm_id(doi.split("/")[-1]))
    url = str(row.get("best_url", "")).strip().rstrip("/")
    if url:
        keys.add(_norm_id(url.split("/")[-1]))
    for col in ("pmid", "pmcid"):
        v = str(row.get(col, "")).strip()
        if v and v.lower() != "nan":
            keys.add(_norm_id(v))
    return {k for k in keys if len(k) >= 5}


def _pdf_dois(path: Path, *, pages: int = 1) -> set[str]:
    """Text-mine DOIs from the first ``pages`` of a PDF (normalised). Page 1 only avoids cited DOIs."""
    import re

    import pdfplumber

    from bac_metadata.bac_agentic_metadata.engine.fulltext import _DOI_RE

    found: set[str] = set()
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:pages]:
                txt = page.extract_text() or ""
                for src in (txt, re.sub(r"\s+", "", txt)):
                    for m in _DOI_RE.findall(src):
                        found.add(_norm_id(m.rstrip(").")))
    except Exception as exc:  # noqa: BLE001 — an unreadable PDF just yields no DOI
        print(f"  [warn] could not read {path.name}: {type(exc).__name__}", file=sys.stderr)
    return found


def _match_pdf(pdf: Path, acc_keys: dict[str, set[str]], overrides: Mapping[str, list[str]]) -> list[str]:
    """Return the accession(s) a PDF belongs to (override → filename token → DOI text-mine)."""
    stem = _norm_id(pdf.stem)
    if stem in overrides:
        return overrides[stem]
    for raw_stem, accs in overrides.items():
        if raw_stem in stem:
            return accs
    hits = {acc for acc, keys in acc_keys.items() if any(k in stem or stem in k for k in keys)}
    if hits:
        return sorted(hits)
    pdf_keys = _pdf_dois(pdf)
    hits = {acc for acc, keys in acc_keys.items()
            if any(any(pk == k or k in pk for k in keys) for pk in pdf_keys)}
    return sorted(hits)


def attach_downloaded_papers(*, downloads_dir: str | Path, worklist_path: str | Path,
                             out_dir: str | Path, overrides: Mapping[str, list[str]] | None = None,
                             dry_run: bool = False) -> dict[str, Path]:
    """Match hand-downloaded publisher PDFs to their study accession and copy them into ``manual_download/``.

    Matches each PDF primarily by the DOI text-mined from its first page, then by normalised filename/URL
    tokens, then by an explicit ``overrides`` map, and copies it to ``<out_dir>/<accession>.pdf`` so
    grading can pick it up. A PDF may serve several accessions (one paper, >1 project). Idempotent.
    """
    import shutil

    overrides = overrides or {}
    dl = Path(downloads_dir).expanduser()
    out = Path(out_dir)
    if not dl.is_dir():
        sys.exit(f"downloads folder not found: {dl}")
    rep = pd.read_csv(worklist_path, sep="\t", dtype=str).fillna("")
    have_paper = rep[rep["has_paper"].str.lower().isin({"true", "1", "yes"})]
    acc_keys = {r["study_accession"]: _accession_keys(r) for _, r in have_paper.iterrows()}

    pdfs = sorted(q for q in dl.glob("*.pdf"))
    print(f"{len(pdfs)} PDFs in {dl.name}; {len(acc_keys)} accessions need a paper.\n", file=sys.stderr)

    resolved: dict[str, Path] = {}
    unmatched: list[str] = []
    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        accs = _match_pdf(pdf, acc_keys, overrides)
        if not accs:
            unmatched.append(pdf.name)
            continue
        for acc in accs:
            resolved[acc] = pdf
            print(f"  {pdf.name}  ->  {acc}.pdf", file=sys.stderr)
            if not dry_run:
                shutil.copy2(pdf, out / f"{acc}.pdf")

    missing = sorted(set(acc_keys) - set(resolved))
    print(f"\nResolved {len(resolved)}/{len(acc_keys)} accessions.", file=sys.stderr)
    if missing:
        print(f"STILL MISSING ({len(missing)}): {', '.join(missing)}", file=sys.stderr)
    if unmatched:
        print(f"Unmatched PDFs ({len(unmatched)}): {', '.join(unmatched)}", file=sys.stderr)
    return resolved
