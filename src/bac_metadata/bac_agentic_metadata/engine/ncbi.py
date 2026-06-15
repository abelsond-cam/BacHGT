"""NCBI E-utilities — link a BioProject accession to its publication PMIDs.

The BioProject record's *Publications* are submitter-curated, making this the most authoritative
accession→paper channel for ``PRJNA`` accessions (and it resolves ``PRJEB``/``PRJDB`` too, since
BioProject is shared across INSDC). Two calls:

1. ``esearch`` ``db=bioproject&term=<accession>`` → BioProject UID(s).
2. ``elink`` ``dbfrom=bioproject&db=pubmed&id=<uid>`` → linked PMIDs.

The PMIDs are hydrated into candidates elsewhere (``europepmc.candidates_by_pmids``). Responses are
cached on disk; requests go through the shared :mod:`http_utils` client with a polite delay. An
``NCBI_API_KEY`` (env) lifts the rate limit from 3 to 10 req/s; ``BAC_NCBI_EMAIL`` (env) sets the
courtesy contact. Returns ``[]`` gracefully when an accession has no BioProject record or links.
"""

from __future__ import annotations

import json
import os
import time

from . import http_utils

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TOOL = "bac_agentic_metadata"
#: Polite inter-request delay (s): NCBI allows 3 req/s without a key, 10 with one.
_DELAY_NO_KEY = 0.34
_DELAY_KEY = 0.11


def _common_params(api_key: str | None) -> dict:
    """Shared E-utilities params (tool/email courtesy + optional api_key)."""
    params = {"tool": _TOOL, "retmode": "json"}
    email = os.environ.get("BAC_NCBI_EMAIL")
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def bioproject_pmids(accession: str, *, cache_dir=None, api_key: str | None = None) -> list[str]:
    """Return PMIDs linked to a BioProject accession via esearch→elink (cached), or ``[]``.

    Parameters
    ----------
    accession
        Project accession (e.g. ``"PRJNA339843"``).
    cache_dir
        If given, the combined result is cached at ``<cache_dir>/ncbi_<accession>.json``.
    api_key
        NCBI API key; falls back to the ``NCBI_API_KEY`` env var.

    Returns
    -------
    list[str]
        Linked PubMed IDs (possibly empty).
    """
    api_key = api_key or os.environ.get("NCBI_API_KEY")
    delay = _DELAY_KEY if api_key else _DELAY_NO_KEY

    cache_path = None
    if cache_dir is not None:
        cache_path = cache_dir / f"ncbi_{accession}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text())

    base = _common_params(api_key)
    # 1) Resolve the BioProject UID(s).
    esearch = http_utils.get(f"{EUTILS}/esearch.fcgi", params={**base, "db": "bioproject", "term": accession})
    time.sleep(delay)
    uids: list[str] = []
    if esearch is not None:
        try:
            uids = esearch.json().get("esearchresult", {}).get("idlist", []) or []
        except json.JSONDecodeError:
            uids = []

    pmids: list[str] = []
    # 2) Link each UID to PubMed.
    for uid in uids:
        elink = http_utils.get(
            f"{EUTILS}/elink.fcgi",
            params={**base, "dbfrom": "bioproject", "db": "pubmed", "id": uid},
        )
        time.sleep(delay)
        if elink is None:
            continue
        try:
            linksets = elink.json().get("linksets", [])
        except json.JSONDecodeError:
            continue
        for ls in linksets:
            for db in ls.get("linksetdbs", []):
                if db.get("dbto") == "pubmed":
                    pmids.extend(str(x) for x in db.get("links", []))

    pmids = list(dict.fromkeys(pmids))  # dedup, preserve order
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(pmids))
    return pmids
