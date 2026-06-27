"""Manual-fetch worklist for the papers we could NOT pull full text for (engine, app-agnostic).

The whole-field-decline probe and the gap diagnosis both land on the same recurring constraint: a large
slice of the residual date/source gap is **fetch-limited** — the describing paper is paywalled / not
Europe-PMC-open-access, so the grader only ever saw an abstract (or nothing) and could not propose values
it never read. That barrier is a publisher-access problem, not an engine bug: it is closed by a human with
institutional access downloading the PDFs by hand.

This builds that worklist. For every study whose grading ran on ``is_full_text=False`` it joins the
identifiers needed to fetch the paper manually — the curated ``paper_link`` (injected by the application as
a ``study_accession -> link`` map; ``None`` when the application has no curated links, e.g. M. abscessus),
plus the finder's DOI / PMID / PMCID / title — and weights each by the per-study completeness gap it would
unblock, so the high-yield papers are fetched first. Studies with **no paper at all** are split out.

Download convention: download each paywalled PDF into one folder, then ``link_local_papers.py`` renames
them to ``<study_accession>.pdf`` under the manual-download dir; :func:`engine.local_papers.resolve_local_fulltext`
then feeds them to the next grading pass. Read-only. Writes ``<report_prefix>.{md,tsv}`` under ``out_dir``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from .local_papers import resolve_local_fulltext


def _clean_link(paper_link: str) -> str:
    """Keep a curated link only if it is an actual http(s) URL (drops junk like 'Na')."""
    link = (paper_link or "").strip()
    return link if link.lower().startswith("http") else ""


def _best_url(doi: str, pmid: str, pmcid: str, paper_link: str) -> str:
    """A single click-to-fetch URL: DOI resolver > Europe PMC > PubMed > the curated link."""
    if doi:
        return f"https://doi.org/{doi}"
    if pmcid:
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return _clean_link(paper_link)


def build_missing_papers(
    *,
    grades_path: Path,
    found_path: Path,
    gap_report_path: Path,
    sizing_path: Path,
    manual_dir: Path,
    out_dir: Path,
    report_prefix: str = "missing_papers_report",
    paper_links: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Build the manual-fetch worklist of paywalled / no-full-text papers, gap-weighted.

    Parameters
    ----------
    grades_path
        Grader JSONL carrying the full-text status per study.
    found_path
        Paper-finder output TSV (DOI/PMID/PMCID/title identifiers).
    gap_report_path
        Per-study date/source completeness-gap TSV.
    sizing_path
        ENA assessment sizing TSV (taxon samples per study).
    manual_dir
        Directory of manually-downloaded ``<accession>.pdf`` full texts (the re-check source).
    out_dir
        Where the ``<report_prefix>.{md,tsv}`` worklist is written.
    report_prefix
        Output filename stem.
    paper_links
        Injected ``study_accession -> curated link`` map; ``None`` -> no curated links.

    Returns
    -------
    pandas.DataFrame
        The gap-weighted worklist (also written to disk).
    """
    paper_links = paper_links or {}

    # 1) the studies whose grading had no full text.
    missing: dict[str, str] = {}
    with open(grades_path) as fh:
        for line in fh:
            r = json.loads(line)
            if not r.get("is_full_text"):
                missing[r["study_accession"]] = r.get("fulltext_source", "")
    print(f"{len(missing)} studies graded without full text", file=sys.stderr)

    # 2) finder identifiers (DOI/PMID/PMCID/title, none_found) and the curated paper link.
    found = pd.read_csv(found_path, sep="\t", dtype=str).fillna("").set_index("study_accession") \
        if Path(found_path).exists() else pd.DataFrame()
    gap = pd.read_csv(gap_report_path, sep="\t", dtype=str).set_index("study_accession") \
        if Path(gap_report_path).exists() else pd.DataFrame()
    sizing = pd.read_csv(sizing_path, sep="\t", dtype=str).set_index("study_accession") \
        if Path(sizing_path).exists() else pd.DataFrame()

    def _g(df, acc, col, default=""):
        return df.loc[acc, col] if (len(df) and acc in df.index and col in df.columns) else default

    rows = []
    for acc, ftsrc in missing.items():
        doi, pmid, pmcid = _g(found, acc, "chosen_doi"), _g(found, acc, "chosen_pmid"), _g(found, acc, "chosen_pmcid")
        link = _clean_link(paper_links.get(acc, ""))
        date_gap = int(float(_g(gap, acc, "collection_date_gap", 0) or 0))
        src_gap = int(float(_g(gap, acc, "isolation_source_gap", 0) or 0))
        taxon = int(float(_g(sizing, acc, "ena_taxon_samples", 0) or 0))
        best_url = _best_url(doi, pmid, pmcid, link)
        # Fetchable for a human = ANY resolvable identifier exists (the finder's automated `none_found`
        # abstention does not veto a curated link a person can open).
        rows.append({
            "study_accession": acc, "has_paper": bool(best_url),
            "date_gap": date_gap, "source_gap": src_gap, "gap_samples": date_gap + src_gap,
            "ena_taxon_samples": taxon, "fulltext_status": ftsrc,
            "best_url": best_url,
            "doi": doi, "pmid": pmid, "pmcid": pmcid, "paper_link": link,
            "title": _g(found, acc, "chosen_title"), "save_as": f"{acc}.pdf",
        })
    res = pd.DataFrame(rows).sort_values(["has_paper", "gap_samples", "ena_taxon_samples"],
                                         ascending=[False, False, False])
    out_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(out_dir / f"{report_prefix}.tsv", sep="\t", index=False)
    _write_md(res, out_dir / f"{report_prefix}.md")
    fetchable = res[res["has_paper"]]
    print(f"Wrote {report_prefix}.{{md,tsv}}: {len(fetchable)} fetchable "
          f"({int(fetchable['gap_samples'].sum())} gap samples), {len(res) - len(fetchable)} no-paper",
          file=sys.stderr)

    # Manual-download re-check (concern #1 — never silent on papers). A manual PDF lands AFTER the first
    # run flags a paper missing, so split by what is on disk NOW: newly-present (a readable
    # manual_download/<acc>.pdf exists but grading saw no full text → re-run grading to consume it) vs
    # still-missing (has a fetchable paper but no usable manual PDF yet).
    has_paper_of = dict(zip(res["study_accession"], res["has_paper"], strict=False))
    newly_present = sorted(a for a in missing if resolve_local_fulltext(a, str(manual_dir)) is not None)
    still_missing = sorted(a for a in missing
                           if a not in newly_present and has_paper_of.get(a, False))
    if newly_present:
        print(f"[FLAG] {len(newly_present)} manual PDF(s) now present but grading saw no full text — "
              f"RE-RUN GRADING to consume them: {newly_present}", file=sys.stderr)
    if still_missing:
        print(f"[FLAG] {len(still_missing)} studies STILL missing a paper (fetchable, no usable manual PDF "
              f"yet) — fetch + link_local_papers.py: {still_missing}", file=sys.stderr)
    return res


def _write_md(res: pd.DataFrame, path: Path) -> None:
    """Render the prioritised manual-fetch table + the no-paper tail."""
    fetch = res[res["has_paper"]]
    nopaper = res[~res["has_paper"]]
    md = ["# Missing papers — manual-fetch worklist (paywalled / not Europe-PMC open access)\n",
          f"{len(fetch)} studies whose paper we could not pull full text for and that have a resolvable "
          f"identifier — together unblocking **{int(fetch['gap_samples'].sum())} gapped date/source "
          "samples** (plus the study-level grade). Fetch with Cambridge access, **save each as "
          "`<study_accession>.pdf` in one Google-Drive folder** (sorted high-yield first).\n",
          "| save as | gap (date+src) | taxon n | best URL | DOI / PMID | title |",
          "|---|---|---|---|---|---|"]
    for _, r in fetch.iterrows():
        ident = r["doi"] or (f"PMID:{r['pmid']}" if r["pmid"] else (f"PMCID:{r['pmcid']}" if r["pmcid"] else ""))
        title = (r["title"] or "")[:70]
        md.append(f"| `{r['save_as']}` | {int(r['gap_samples'])} | {int(r['ena_taxon_samples'])} | "
                  f"{r['best_url']} | {ident} | {title} |")
    if len(nopaper):
        md += [f"\n## No paper / unresolvable — skip ({len(nopaper)})\n",
               "Finder found nothing, or the curated link is known wrong/misattributed (see the GT finding). "
               "Not worth manual effort.\n",
               "| study | fulltext_status | curated link |", "|---|---|---|"]
        for _, r in nopaper.iterrows():
            md.append(f"| {r['study_accession']} | {r['fulltext_status']} | {(r['paper_link'] or '')[:60]} |")
    path.write_text("\n".join(md) + "\n")
