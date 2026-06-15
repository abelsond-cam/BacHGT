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
from difflib import SequenceMatcher

from . import http_utils

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
#: bioRxiv/medRxiv "details" API — exposes a ``published`` DOI once a preprint is published.
BIORXIV_API = "https://api.biorxiv.org/details"
_PREPRINT_DOI_RE = re.compile(r"^10\.1101/", re.IGNORECASE)
#: Title similarity above which a non-preprint Europe PMC hit is accepted as the published version.
_PUBLISHED_TITLE_SIM = 0.90


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


# --------------------------------------------------------------------------------------------- #
# Preprint → published promotion (always favour the peer-reviewed version).
# --------------------------------------------------------------------------------------------- #
def is_preprint(c: Candidate) -> bool:
    """True if a candidate is a preprint (Europe PMC ``source`` PPR, or a bioRxiv/medRxiv DOI)."""
    return (c.source or "").upper() == "PPR" or bool(c.doi and _PREPRINT_DOI_RE.match(c.doi))


def published_doi_for_preprint(doi: str, *, cache_dir=None) -> str | None:
    """Published DOI for a bioRxiv/medRxiv preprint via the preprint-server API, or ``None``.

    The bioRxiv/medRxiv ``details`` endpoint carries a ``published`` field that becomes the DOI of
    the peer-reviewed article once the preprint is published (``"NA"`` until then). Result cached.
    """
    if not doi:
        return None
    cache_path = None
    if cache_dir is not None:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", doi)[:120]
        cache_path = cache_dir / f"preprint_pub_{slug}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text()).get("published")

    published: str | None = None
    for server in ("biorxiv", "medrxiv"):
        resp = http_utils.get(f"{BIORXIV_API}/{server}/{doi}")
        if resp is None:
            continue
        coll = resp.json().get("collection", [])
        if not coll:
            continue
        cand = (coll[-1].get("published") or "").strip()
        if cand and cand.upper() != "NA":
            published = cand
            break
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"published": published}))
    return published


def _title_sim(a: str, b: str) -> float:
    """Normalised SequenceMatcher ratio over two titles (0 if either is empty)."""
    na = re.sub(r"[^a-z0-9]+", " ", (a or "").lower()).strip()
    nb = re.sub(r"[^a-z0-9]+", " ", (b or "").lower()).strip()
    return SequenceMatcher(None, na, nb).ratio() if na and nb else 0.0


def published_version_of(c: Candidate, *, cache_dir=None) -> Candidate | None:
    """Resolve a preprint candidate to its peer-reviewed published version, or ``None``.

    Two routes: (1) the bioRxiv/medRxiv ``published`` DOI (authoritative), hydrated via Europe PMC;
    (2) a Europe PMC title search for a non-preprint sibling with a near-identical title. Returns a
    :class:`Candidate` tagged ``found_via="published_version"``, or ``None`` if the preprint has no
    discoverable published version.
    """
    if not is_preprint(c):
        return None
    pub_doi = published_doi_for_preprint(c.doi, cache_dir=cache_dir) if c.doi else None
    if pub_doi:
        hits = _search(f'DOI:"{pub_doi}"', cache_dir=cache_dir, page_size=1, found_via="published_version")
        if hits:
            return hits[0]
    if c.title:
        for cand in search_by_title(c.title, cache_dir=cache_dir):
            if not is_preprint(cand) and _title_sim(c.title, cand.title) >= _PUBLISHED_TITLE_SIM:
                cand.found_via = "published_version"
                return cand
    return None
