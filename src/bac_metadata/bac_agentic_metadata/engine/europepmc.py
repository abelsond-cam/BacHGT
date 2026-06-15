"""Europe PMC candidate search for the paper-finder (multi-result).

The finder turns a project accession into candidate papers via **deterministic retrieval** — the
LLM only picks among what these queries return, it never invents an identifier. This module wraps
the Europe PMC REST ``/search`` endpoint to return ranked :class:`Candidate` lists:

* :func:`search_by_accession` — free-text query on the accession string; Europe PMC text-mines
  accession numbers, so this returns the papers that cite/deposit the accession (the structured,
  precise analogue of a manual Google search keyed on the accession).
* :func:`search_by_title` — exact-phrase title search (fallback / corroboration via the ENA title).
* :func:`candidates_by_pmids` — hydrate PMIDs (e.g. from NCBI BioProject links) into candidates.

``fulltext._europepmc_search`` resolves a *single* known reference; this returns *many* candidates.
Responses are cached on disk so reruns are deterministic and offline. Same retry/backoff client
as the rest of the engine (:mod:`http_utils`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import http_utils

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


@dataclass
class Candidate:
    """One candidate paper for an accession (from any retrieval channel)."""

    title: str
    pmid: str | None
    pmcid: str | None
    doi: str | None
    year: str
    source: str  # Europe PMC ``source`` (MED, PMC, PPR, …)
    abstract: str
    is_open_access: bool
    cited_by: int
    found_via: str  # which channel surfaced it (europepmc_accession / europepmc_title / ncbi_bioproject / ena_description)

    def ids(self) -> set[str]:
        """Normalised identifier set for matching/dedup (lowercased pmid/pmcid/doi)."""
        out = set()
        if self.pmid:
            out.add(f"pmid:{self.pmid}")
        if self.pmcid:
            out.add(f"pmcid:{self.pmcid.upper()}")
        if self.doi:
            out.add(f"doi:{self.doi.lower()}")
        return out


def _result_to_candidate(r: dict, found_via: str) -> Candidate:
    """Convert a Europe PMC core result object into a :class:`Candidate`."""
    return Candidate(
        title=r.get("title", "") or "",
        pmid=r.get("pmid"),
        pmcid=r.get("pmcid"),
        doi=r.get("doi"),
        year=str(r.get("pubYear", "") or ""),
        source=r.get("source", "") or "",
        abstract=r.get("abstractText", "") or "",
        is_open_access=(r.get("isOpenAccess") == "Y"),
        cited_by=int(r.get("citedByCount", 0) or 0),
        found_via=found_via,
    )


def _search(query: str, *, cache_dir, page_size: int, found_via: str) -> list[Candidate]:
    """Run one Europe PMC ``/search`` (cached) and return candidates."""
    cache_path = None
    if cache_dir is not None:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{found_via}_{query}")[:140]
        cache_path = cache_dir / f"epmc_{slug}.json"
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
        else:
            data = None
    else:
        data = None

    if data is None:
        resp = http_utils.get(
            f"{EUROPEPMC}/search",
            params={"query": query, "format": "json", "resultType": "core", "pageSize": page_size},
        )
        if resp is None:
            return []
        data = resp.json()
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, ensure_ascii=False))

    results = data.get("resultList", {}).get("result", [])
    return [_result_to_candidate(r, found_via) for r in results]


def search_by_accession(accession: str, *, cache_dir=None, page_size: int = 25) -> list[Candidate]:
    """Return candidate papers that text-mine/cite ``accession`` (Europe PMC free-text)."""
    return _search(accession, cache_dir=cache_dir, page_size=page_size, found_via="europepmc_accession")


def search_by_title(title: str, *, cache_dir=None, page_size: int = 10) -> list[Candidate]:
    """Return candidate papers whose title matches ``title`` (exact-phrase TITLE query)."""
    title = (title or "").strip()
    if not title:
        return []
    # Strip quotes that would break the field query; wrap as an exact phrase.
    safe = title.replace('"', " ").strip()
    return _search(f'TITLE:"{safe}"', cache_dir=cache_dir, page_size=page_size, found_via="europepmc_title")


def candidates_by_pmids(pmids: list[str], *, cache_dir=None) -> list[Candidate]:
    """Hydrate PMIDs (e.g. from NCBI BioProject links) into candidates via ``EXT_ID`` lookup."""
    pmids = [p for p in dict.fromkeys(pmids) if p]  # dedup, preserve order
    if not pmids:
        return []
    clause = " OR ".join(f"EXT_ID:{p}" for p in pmids)
    query = f"({clause}) AND SRC:MED"
    return _search(query, cache_dir=cache_dir, page_size=len(pmids), found_via="ncbi_bioproject")
