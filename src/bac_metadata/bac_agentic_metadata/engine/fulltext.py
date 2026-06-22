"""Resolve a paper reference to text for grading — Europe PMC first, then abstract, then PDF.

Given a curated reference (a URL, PMID, PMCID, or DOI from the Klebsiella ``paper_link`` column),
:func:`fetch_fulltext` returns a :class:`FullText` with the best text we can obtain and how it was
sourced, following a strict preference order:

1. **Europe PMC open-access full text** — if the article is in Europe PMC (``inEPMC=Y``) with a
   PMCID, fetch its JATS ``fullTextXML`` and flatten to text (body minus the reference list).
2. **Abstract** — else the Europe PMC abstract plus title (enough for many study-level judgements).
3. **PDF** — else, if the reference (or a Europe PMC open-access link) points at a PDF, download
   and extract text with ``pdfplumber``.
4. **needs_manual_download** — else flag the accession; the full text is paywalled / unreachable.

Identifiers are text-mined from the reference (``PMC…`` / a PubMed id / a DOI, incl. medRxiv/
bioRxiv ``10.1101/…``). Raw responses (search JSON, full-text XML, PDFs) are cached on disk so
reruns are deterministic and offline. Europe PMC XML is parsed with the stdlib ``xml.etree`` —
no bs4/lxml dependency.
"""

from __future__ import annotations

import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import http_utils

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"

_PMCID_RE = re.compile(r"PMC\d+", re.IGNORECASE)
_PMID_URL_RE = re.compile(r"pubmed[^0-9]*?(\d+)", re.IGNORECASE)
_BARE_INT_RE = re.compile(r"^\d+$")
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
#: JATS sections dropped from extracted body text (low grading value, high token cost).
_DROP_TAGS = frozenset({"ref-list", "back", "fn-group", "table-wrap-foot"})


@dataclass
class FullText:
    """Text obtained for one paper reference plus how it was sourced.

    Parameters
    ----------
    text
        The extracted text (full text, or abstract+title, or PDF text; empty if none).
    source
        One of ``"europepmc_fulltext"``, ``"abstract"``, ``"pdf"``, ``"none"``.
    is_full_text
        True only when ``source == "europepmc_fulltext"`` or a PDF yielded substantial text.
    needs_manual_download
        True when a paper was identified but its full text could not be reached (paywalled).
    identifier
        The resolved identifier used (e.g. ``"PMC123"``, ``"DOI:10.x/y"``, or the raw URL).
    title
        Article title when known.
    """

    text: str
    source: str
    is_full_text: bool
    needs_manual_download: bool
    identifier: str
    title: str = ""
    meta: dict = field(default_factory=dict)


def _resolve_identifier(ref: str) -> tuple[str, str]:
    """Classify a reference string into ``(kind, value)``.

    kind is one of ``pmcid`` / ``pmid`` / ``doi`` / ``url``.
    """
    s = ref.strip()
    m = _PMCID_RE.search(s)
    if m:
        return "pmcid", m.group(0).upper()
    m = _PMID_URL_RE.search(s)
    if m:
        return "pmid", m.group(1)
    if _BARE_INT_RE.match(s):
        return "pmid", s
    m = _DOI_RE.search(s)
    if m:
        return "doi", m.group(0).rstrip(").")
    return "url", s


def _search_query(kind: str, value: str) -> str | None:
    """Build a Europe PMC ``query`` for an identifier, or ``None`` for a bare URL."""
    if kind == "pmcid":
        return f"PMCID:{value}"
    if kind == "pmid":
        return f"EXT_ID:{value} AND SRC:MED"
    if kind == "doi":
        return f'DOI:"{value}"'
    return None


def _europepmc_search(query: str, cache_dir: Path | None) -> dict | None:
    """Return the first Europe PMC core record for a query (cached), or ``None``."""
    cache_path = None
    if cache_dir is not None:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", query)[:120]
        cache_path = cache_dir / f"search_{slug}.json"
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            results = data.get("resultList", {}).get("result", [])
            return results[0] if results else None

    resp = http_utils.get(
        f"{EUROPEPMC}/search",
        params={"query": query, "format": "json", "resultType": "core", "pageSize": 1},
    )
    if resp is None:
        return None
    data = resp.json()
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False))
    results = data.get("resultList", {}).get("result", [])
    return results[0] if results else None


def _xml_to_text(xml_text: str) -> str:
    """Flatten a Europe PMC JATS ``fullTextXML`` to plain text (body, minus reference lists)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    body = root.find(".//body")
    target = body if body is not None else root
    # Drop low-value subtrees in place before flattening.
    for tag in _DROP_TAGS:
        for parent in target.iter():
            for child in list(parent):
                if child.tag.split("}")[-1] == tag:
                    parent.remove(child)
    parts = [t.strip() for t in target.itertext() if t and t.strip()]
    return "\n".join(parts)


def _fetch_fulltext_xml(pmcid: str, cache_dir: Path | None) -> str | None:
    """Fetch + cache the JATS full-text XML for a PMCID; return the raw XML or ``None``."""
    cache_path = None
    if cache_dir is not None:
        cache_path = cache_dir / f"{pmcid}.xml"
        if cache_path.exists():
            return cache_path.read_text()
    resp = http_utils.get(f"{EUROPEPMC}/{pmcid}/fullTextXML")
    if resp is None or not resp.text.strip():
        return None
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(resp.text)
    return resp.text


def _pdf_url_for(ref: str, record: dict | None) -> str | None:
    """Find a PDF URL: a direct ``.pdf`` reference, an OA link, or a medRxiv/bioRxiv ``.full.pdf``."""
    s = ref.strip()
    if s.lower().endswith(".pdf"):
        return s
    if record:
        for grp in record.get("fullTextUrlList", {}).get("fullTextUrl", []):
            if grp.get("documentStyle") == "pdf" and grp.get("availability") in {"Open access", "Free"}:
                return grp.get("url")
    if re.search(r"(medrxiv|biorxiv)\.org", s, re.IGNORECASE) and "/10.1101/" in s:
        base = s.rstrip("/")
        return base + ".pdf" if base.endswith(".full") else base + ".full.pdf"
    return None


def _pdf_to_text(data: bytes, *, attempts: int = 3) -> str:
    """Extract text from PDF bytes with ``pdfplumber``; retry transient failures, then give up.

    pdfplumber can fail *transiently* under memory/CPU pressure when many large PDFs are parsed
    back-to-back (e.g. a grading run over a dozen paywalled-paper PDFs). A swallowed failure silently
    drops that paper from grading, and the cached no-full-text grade then persists across refires — so
    we retry a few times and, on persistent failure, log loudly rather than returning ``""`` in
    silence. Returns ``""`` only after all attempts fail.
    """
    import pdfplumber

    for attempt in range(1, attempts + 1):
        try:
            out = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        out.append(t)
            return "\n".join(out)
        except Exception as exc:  # noqa: BLE001 — retry transient parse failures, then give up loudly
            if attempt == attempts:
                print(f"  [warn] pdfplumber failed to parse {len(data)} bytes after {attempts} "
                      f"attempts: {type(exc).__name__}: {exc}", file=sys.stderr)
                return ""
    return ""


def _fetch_pdf_text(url: str, cache_dir: Path | None) -> str:
    """Download + cache a PDF and extract its text (empty string if unreachable/unparseable)."""
    cache_path = None
    if cache_dir is not None:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", url)[:120]
        cache_path = cache_dir / f"pdf_{slug}.pdf"
        if cache_path.exists():
            return _pdf_to_text(cache_path.read_bytes())
    resp = http_utils.get(url, headers={"Accept": "application/pdf"})
    if resp is None or not resp.content:
        return ""
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(resp.content)
    return _pdf_to_text(resp.content)


#: Below this character count a PDF extraction is treated as failed (scanned/garbled).
_MIN_PDF_CHARS = 500


def fetch_fulltext(ref: str, *, cache_dir: str | Path | None = None) -> FullText:
    """Resolve a paper reference to the best available text (full text → abstract → PDF → flag).

    Parameters
    ----------
    ref
        A reference string: a URL, PMID, PMCID, or DOI (the curated ``paper_link`` value).
    cache_dir
        Directory for caching raw responses (search JSON, XML, PDFs). If ``None``, nothing is
        cached.

    Returns
    -------
    FullText
        The text and provenance. ``needs_manual_download`` is True only when a paper was
        identified but no openly accessible text could be retrieved.
    """
    cdir = Path(cache_dir) if cache_dir is not None else None
    kind, value = _resolve_identifier(ref)
    query = _search_query(kind, value)
    record = _europepmc_search(query, cdir) if query else None

    title = (record or {}).get("title", "")
    pmcid = (record or {}).get("pmcid") or (value if kind == "pmcid" else None)
    in_epmc = (record or {}).get("inEPMC") == "Y"
    abstract = (record or {}).get("abstractText", "")

    # 1) Europe PMC open-access full text.
    if pmcid and in_epmc:
        xml_text = _fetch_fulltext_xml(pmcid, cdir)
        if xml_text:
            body = _xml_to_text(xml_text)
            if body:
                text = f"{title}\n\n{body}" if title else body
                return FullText(text, "europepmc_fulltext", True, False, pmcid, title)

    # 3a) PDF (before abstract only if we have no abstract; abstract preferred when present is a
    #     judgement call — but a full PDF beats an abstract, so try PDF when there's no EPMC body).
    pdf_url = _pdf_url_for(ref, record)
    if pdf_url:
        pdf_text = _fetch_pdf_text(pdf_url, cdir)
        if len(pdf_text) >= _MIN_PDF_CHARS:
            text = f"{title}\n\n{pdf_text}" if title else pdf_text
            return FullText(text, "pdf", True, False, pmcid or value, title)

    # 2) Abstract fallback.
    if abstract:
        text = f"{title}\n\n{abstract}" if title else abstract
        return FullText(text, "abstract", False, False, value, title)

    # 4) Nothing reachable.
    found_paper = record is not None or kind in {"pmcid", "pmid", "doi"}
    return FullText("", "none", False, needs_manual_download=found_paper, identifier=value, title=title)
