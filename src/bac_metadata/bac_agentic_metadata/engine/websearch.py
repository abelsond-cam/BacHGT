"""Web-search fallback channel for the paper-finder (Anthropic API ``web_search`` server tool).

Fires ONLY on the abstaining tail — when the deterministic channels (ENA mining, NCBI BioProject,
Europe PMC accession/title, secondary accessions) yield no confident pick, because the describing
paper exists but Europe PMC simply doesn't text-mine its accession→paper link (observed for ~12 of
the 20 train+val abstentions).

**Cost split (agreed with David):** the *web search* runs on the **paid API** (the `web_search`
server tool, metered, and only on the tail), while the downstream candidate *pick* stays on the
`claude -p` **subscription** (zero API spend). So this module only RETRIEVES candidate paper
identifiers from the open web; :func:`paper_finder.find_paper` still does the grounded pick.

Anti-hallucination is preserved: the model's web-found candidates are hydrated into real
:class:`Candidate`s (Europe PMC where indexed, else a minimal record from the search hit) and then
pass the same **grounded-verify** (the accession — or an ERP/SRP alias — must appear in the paper
text). Responses are cached on disk so reruns are deterministic, free, and don't re-bill the search.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import europepmc
from .europepmc import Candidate
from .llm import DEFAULT_MODEL, resolve_api_key

#: Anthropic server-side web-search tool (metered ~$10/1k searches; bounded by ``max_uses`` + the tail).
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
_MAX_CANDIDATES = 5


def _extract_json_obj(text: str) -> dict:
    """Parse the last ``{...}`` JSON object from the model's final text (tolerating prose/fences)."""
    s = text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _hydrate(item: dict, *, cache_dir) -> Candidate | None:
    """Turn one web-search hit ``{title,doi,pmid,url,year}`` into a :class:`Candidate`.

    Prefers Europe PMC hydration via a PMID (richer: abstract/pmcid help the pick + grounded-verify);
    otherwise builds a minimal record from the DOI/title (still enough — ``verify_pick`` fetches the
    DOI). Returns ``None`` when there is no usable identifier.
    """
    doi = (str(item.get("doi") or "")).strip() or None
    pmid = (str(item.get("pmid") or "")).strip() or None
    title = (str(item.get("title") or "")).strip()
    if doi and not re.match(r"^10\.\d{4,9}/\S+$", doi):  # drop a malformed/echoed DOI
        doi = None
    if pmid:
        hits = europepmc.candidates_by_pmids([pmid], cache_dir=cache_dir)
        if hits:
            hits[0].found_via = "web_search"
            return hits[0]
    if doi or title:
        return Candidate(
            title=title or (doi or ""), pmid=pmid, pmcid=None, doi=doi,
            year=str(item.get("year") or ""), source="WEB", abstract="",
            is_open_access=False, cited_by=0, found_via="web_search",
        )
    return None


def web_search_candidates(
    accession: str,
    ena_title: str,
    ena_description: str,
    *,
    aliases: list[str] | None = None,
    cache_dir=None,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> list[Candidate]:
    """Search the open web (Anthropic API ``web_search``) for the describing paper → candidates.

    Parameters mirror the deterministic channels. The model is told to find the PRIMARY describing
    paper (not data-reuse), prefer the published version, and return ONLY the candidates it actually
    found (no invented identifiers); the result is cached at ``<cache_dir>/websearch_<accession>.json``
    so reruns neither re-bill nor vary. Returns hydrated :class:`Candidate`s tagged ``web_search``
    (possibly empty); never raises on an API/tool error (returns ``[]`` so the batch continues).
    """
    cache_path = None
    if cache_dir is not None:
        cache_path = Path(cache_dir) / f"websearch_{accession}.json"
        if cache_path.exists():
            items = json.loads(cache_path.read_text()).get("candidates", [])
            return [c for c in (_hydrate(it, cache_dir=cache_dir) for it in items) if c]

    alias_str = ", ".join(aliases or [accession])
    system = (
        "You search the web to surface candidate scientific papers for a given bacterial-genomics "
        "PROJECT ACCESSION, so a downstream step can pick and grounded-verify the primary describing "
        "paper. Use web_search thoroughly: the accession in quotes, each listed secondary accession, and "
        "the project title + organism + any consortium name. Include a paper ONLY if your search "
        "actually connects it to THIS project — it names the accession (or a secondary accession), or it "
        "clearly matches this specific cohort (organism + setting + size/era from the title/description). "
        "Do NOT include unrelated papers and do NOT invent identifiers. Within that bar be inclusive: "
        "list data-reuse and same-group papers too (the downstream step decides which is primary), and "
        "list a published version alongside any preprint. Return ONLY a JSON object "
        '{"candidates": [{"title": ..., "doi": ..., "pmid": ..., "year": ...}]} (up to 5, best first; '
        'null for unknown fields). If nothing genuinely connects, return {"candidates": []}.'
    )
    user = (
        f"PROJECT ACCESSION: {accession} (also cited as: {alias_str})\n"
        f"ENA study title: {ena_title or '(none)'}\n"
        f"ENA study description: {(ena_description or '(none)')[:800]}\n\n"
        "Find the primary describing paper and return the JSON object."
    )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key or resolve_api_key())
        resp = client.messages.create(
            model=model, max_tokens=4096, system=system,
            messages=[{"role": "user", "content": user}], tools=[WEB_SEARCH_TOOL],
        )
    except Exception:  # noqa: BLE001 — web tier is best-effort; never break the batch on an API/tool error
        return []

    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
    parsed = _extract_json_obj(text)
    items = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    items = items[:_MAX_CANDIDATES] if isinstance(items, list) else []
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"candidates": items}, ensure_ascii=False, indent=2))
    return [c for c in (_hydrate(it, cache_dir=cache_dir) for it in items) if c]
