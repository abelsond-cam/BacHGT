"""Find the paper that DESCRIBES a project accession (the foundation of Stage 2).

Finding is a **deterministic retrieval problem**: candidates come only from API queries
(:mod:`europepmc` + :mod:`ncbi` + ENA-description id-mining), and the LLM merely **picks among
real candidates** — it never emits an identifier of its own. The pick is then **grounded**: we
fetch the chosen paper and confirm the accession actually appears in it; an unverified, low-
confidence pick **abstains** (``none_found``) rather than risk poisoning all downstream grading.

Channels (union, deduped by id, in rough precision order):
1. ENA ``study_description`` DOI/PMID mining — submitters often state the paper id outright.
2. NCBI BioProject → PubMed links (authoritative when populated; often empty in practice).
3. Europe PMC accession text-mining — the workhorse (keyed on the accession AND its ENA/SRA
   secondary study accessions, since describing papers often cite the ERP/SRP, not the PRJ).
4. Europe PMC title search — corroboration / fallback.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import europepmc, ncbi
from .europepmc import Candidate
from .fulltext import fetch_fulltext
from .llm import LLMClient
from .spec import AttributeSpec

SCHEMA_NAME = "paper_choice"
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_PMID_RE = re.compile(r"\bPMID:?\s*(\d{6,9})\b", re.IGNORECASE)
_PMCID_RE = re.compile(r"\bPMC\d{5,9}\b", re.IGNORECASE)
_ABSTRACT_CHARS = 600
_MAX_CANDIDATES = 25


# --------------------------------------------------------------------------------------------- #
# Candidate gathering (deterministic retrieval).
# --------------------------------------------------------------------------------------------- #
def mine_ids_from_text(text: str, *, cache_dir=None) -> list[Candidate]:
    """Mine explicit DOIs/PMIDs/PMCIDs from free text (e.g. an ENA description) → candidates."""
    if not text:
        return []
    pmids = _PMID_RE.findall(text)
    cands: list[Candidate] = []
    if pmids:
        cands += europepmc.candidates_by_pmids(pmids, cache_dir=cache_dir)
    for doi in dict.fromkeys(m.rstrip(").,") for m in _DOI_RE.findall(text)):
        hit = europepmc.search_by_title(doi, cache_dir=cache_dir)  # title-query also matches a DOI string
        cands += [Candidate(**{**asdict(c), "found_via": "ena_description"}) for c in hit[:1]]
    for c in cands:
        c.found_via = "ena_description"
    return cands


def _cand_key(c: Candidate) -> str:
    """Stable dedup/agreement key for a candidate (doi → pmcid → pmid → title prefix)."""
    return (
        (c.doi and f"doi:{c.doi.lower()}")
        or (c.pmcid and c.pmcid.upper())
        or (c.pmid and f"pmid:{c.pmid}")
        or c.title.lower()[:80]
    )


def _prefer_published(deduped: dict[str, Candidate], channels: dict[str, set[str]], *, cache_dir) -> None:
    """Swap every preprint candidate for its published version in place (always favour published).

    For each preprint we resolve the peer-reviewed article (bioRxiv/medRxiv ``published`` DOI, else a
    title-matched Europe PMC sibling); when found, the preprint is dropped, its channel provenance is
    carried over to the published id, and ``published_version`` is recorded as a contributing channel.
    Preprints with no discoverable publication are left untouched.
    """
    for key in list(deduped):
        c = deduped[key]
        if not europepmc.is_preprint(c):
            continue
        pub = europepmc.published_version_of(c, cache_dir=cache_dir)
        if pub is None:
            continue
        pub_key = _cand_key(pub)
        provenance = channels.pop(key, set())
        del deduped[key]
        channels.setdefault(pub_key, set()).update(provenance)
        channels[pub_key].add("published_version")
        deduped.setdefault(pub_key, pub)


def gather_candidates(
    accession: str,
    ena_title: str,
    ena_description: str,
    *,
    aliases: list[str] | None = None,
    cache_dir=None,
) -> tuple[list[Candidate], dict[str, set[str]]]:
    """Union the retrieval channels; dedup by id; return (candidates, id→channels map).

    ``aliases`` is the accession plus its ENA/SRA secondary study accessions (ERP/SRP); Europe PMC
    accession text-mining is run on every one, since describing papers often cite the secondary
    accession rather than the BioProject (e.g. ``PRJNA767944`` is cited only as ``SRP340092``). Hits
    surfaced via a secondary are tagged ``europepmc_secondary``. The channel map records every source
    that surfaced each id, for cross-source agreement. Preprints are then promoted to their published
    versions (:func:`_prefer_published`) so the LLM never has to choose a preprint when the
    peer-reviewed article exists.
    """
    search_accessions = aliases or [accession]
    raw: list[Candidate] = []
    raw += mine_ids_from_text(f"{ena_description}\n{ena_title}", cache_dir=cache_dir)
    raw += europepmc.candidates_by_pmids(ncbi.bioproject_pmids(accession, cache_dir=cache_dir), cache_dir=cache_dir)
    for acc in search_accessions:
        hits = europepmc.search_by_accession(acc, cache_dir=cache_dir)
        if acc != accession:
            for h in hits:
                h.found_via = "europepmc_secondary"
        raw += hits
    if ena_title:
        raw += europepmc.search_by_title(ena_title, cache_dir=cache_dir)

    deduped: dict[str, Candidate] = {}
    channels: dict[str, set[str]] = {}
    for c in raw:
        key = _cand_key(c)
        if key not in deduped:
            deduped[key] = c
        channels.setdefault(key, set()).add(c.found_via)
    _prefer_published(deduped, channels, cache_dir=cache_dir)
    # Attach the merged channel set to each kept candidate for display.
    for key, c in deduped.items():
        c.found_via = ",".join(sorted(channels[key]))
    return list(deduped.values()), channels


def merge_web_candidates(
    candidates: list[Candidate],
    channels: dict[str, set[str]] | None,
    web_cands: list[Candidate],
    *,
    cache_dir=None,
) -> tuple[list[Candidate], dict[str, set[str]]]:
    """Fold web-search candidates into an existing candidate set (dedup by id; re-prefer published).

    Used by the runner's web-search fallback: the deterministic channels abstained, so the open-web
    hits (tagged ``web_search``) are added, deduped against what we already have, any preprint promoted
    to its published version, and the merged list handed back for a fresh grounded pick.
    """
    deduped = {_cand_key(c): c for c in candidates}
    merged_channels: dict[str, set[str]] = {k: set(v) for k, v in (channels or {}).items()}
    for c in web_cands:
        key = _cand_key(c)
        if key not in deduped:
            deduped[key] = c
        merged_channels.setdefault(key, set()).add("web_search")
    _prefer_published(deduped, merged_channels, cache_dir=cache_dir)
    for key, c in deduped.items():
        c.found_via = ",".join(sorted(merged_channels[key]))
    return list(deduped.values()), merged_channels


# --------------------------------------------------------------------------------------------- #
# LLM pick (confined to retrieved candidates).
# --------------------------------------------------------------------------------------------- #
def build_choice_schema(n_candidates: int) -> dict:
    """Forced-tool-use schema: pick an index into the candidate list (or abstain)."""
    return {
        "type": "object",
        "properties": {
            "none_found": {"type": "boolean"},
            "chosen_index": {"type": ["integer", "null"], "minimum": 0, "maximum": max(n_candidates - 1, 0)},
            "find_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "coverage_estimate": {"type": ["integer", "null"]},
            "flags": {
                "type": "object",
                "properties": {
                    "shared_accession": {"type": "boolean"},
                    "umbrella": {"type": "boolean"},
                    "data_reuse_only": {"type": "boolean"},
                },
                "required": ["shared_accession", "umbrella", "data_reuse_only"],
                "additionalProperties": False,
            },
            "reasoning": {"type": "string"},
        },
        "required": ["none_found", "chosen_index", "find_confidence", "coverage_estimate", "flags", "reasoning"],
        "additionalProperties": False,
    }


def _render_candidates(candidates: list[Candidate]) -> str:
    """Render the candidate list for the prompt (index + ids + year + title + short abstract)."""
    lines = []
    for i, c in enumerate(candidates):
        ids = f"pmid={c.pmid} pmcid={c.pmcid} doi={c.doi}"
        lines.append(
            f"[{i}] ({c.found_via}; {c.year}; cites={c.cited_by}; OA={c.is_open_access}) {ids}\n"
            f"    title: {c.title}\n"
            f"    abstract: {c.abstract[:_ABSTRACT_CHARS]}"
        )
    return "\n".join(lines) if lines else "(no candidates retrieved)"


@dataclass
class FindResult:
    """The finder's output for one accession."""

    study_accession: str
    none_found: bool
    chosen_title: str | None
    chosen_pmid: str | None
    chosen_pmcid: str | None
    chosen_doi: str | None
    chosen_found_via: str | None
    find_confidence: str
    coverage_estimate: int | None
    coverage_fraction: float | None
    verified: bool | None
    sources_agreeing: int
    n_candidates: int
    flags: dict
    reasoning: str
    model: str
    raw: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        """Flatten to one TSV row."""
        return {
            "study_accession": self.study_accession,
            "none_found": self.none_found,
            "chosen_pmid": self.chosen_pmid,
            "chosen_pmcid": self.chosen_pmcid,
            "chosen_doi": self.chosen_doi,
            "chosen_found_via": self.chosen_found_via,
            "find_confidence": self.find_confidence,
            "verified": self.verified,
            "sources_agreeing": self.sources_agreeing,
            "coverage_estimate": self.coverage_estimate,
            "coverage_fraction": self.coverage_fraction,
            "shared_accession": self.flags.get("shared_accession"),
            "umbrella": self.flags.get("umbrella"),
            "data_reuse_only": self.flags.get("data_reuse_only"),
            "n_candidates": self.n_candidates,
            "chosen_title": self.chosen_title,
        }


def verify_pick(
    candidate: Candidate, accession: str, *, aliases: list[str] | None = None, cache_dir=None
) -> bool | None:
    """Confirm the accession (or any of its ERP/SRP aliases) appears in the chosen paper's text.

    Returns True if any alias is found, False if the text was retrieved but lacks them all, or
    ``None`` if no full text was available to check (inconclusive — only an abstract or nothing).
    Checking the aliases matters: a describing paper often cites the ENA/SRA secondary accession
    (ERP/SRP) rather than the BioProject, so a PRJ-only check spuriously fails to verify.
    """
    ref = candidate.pmcid or (candidate.doi and candidate.doi) or (candidate.pmid and candidate.pmid)
    if not ref:
        return None
    ft = fetch_fulltext(str(ref), cache_dir=cache_dir)
    if not ft.is_full_text or not ft.text:
        return None
    text_up = ft.text.upper()
    return any(a.upper() in text_up for a in (aliases or [accession]))


def find_paper(
    spec: AttributeSpec,
    llm: LLMClient,
    *,
    accession: str,
    ena_title: str,
    ena_description: str,
    sizing_row: dict | None,
    candidates: list[Candidate],
    channels: dict[str, set[str]] | None = None,
    aliases: list[str] | None = None,
    model: str | None = None,
    fulltext_cache=None,
) -> FindResult:
    """Pick the describing paper from retrieved candidates, then ground-verify the pick.

    The LLM selects an index into ``candidates`` (or abstains); it cannot invent an identifier.
    The pick is verified by confirming the accession appears in the paper text; an unverified
    low-confidence pick is downgraded to ``none_found``.
    """
    sizing_row = sizing_row or {}
    taxon_n = sizing_row.get("ena_taxon_samples")
    candidates = candidates[:_MAX_CANDIDATES]
    schema = build_choice_schema(len(candidates))

    system = (
        "You identify which candidate paper DESCRIBES a given bacterial-genomics PROJECT ACCESSION "
        "(the primary study that generated/deposited these genomes) — NOT papers that merely reuse "
        "or cite the data. You may ONLY choose from the numbered candidates provided; never invent "
        "a paper or identifier. Choose the one whose scope matches the project: the taxon, the "
        "approximate sample count, and the study description. Prefer the original describing study "
        "(usually the earliest among several that match); but when a preprint and its peer-reviewed "
        "published version both appear, choose the PUBLISHED version. If no candidate plausibly describes this "
        "project, set none_found=true and chosen_index=null. Use find_confidence honestly: 'high' "
        "only when a candidate clearly describes this exact cohort. Set coverage_estimate to the "
        "number of taxon-of-interest samples the chosen paper describes (null if unclear). flags: "
        "shared_accession (the accession is cited by several distinct studies), umbrella (the "
        "accession aggregates many substudies), data_reuse_only (candidates only reuse the data, "
        "none is the describing study)."
    )
    sizing_bits = []
    if taxon_n not in (None, ""):
        sizing_bits.append(f"ena_taxon_samples={taxon_n}")
    if sizing_row.get("umbrella_suspected") not in (None, ""):
        sizing_bits.append(f"umbrella_suspected={sizing_row.get('umbrella_suspected')}")
    user = (
        f"PROJECT ACCESSION: {accession}\n"
        f"ENA study title: {ena_title or '(none)'}\n"
        f"ENA study description: {(ena_description or '(none)')[:1200]}\n"
        f"ENA sizing: {', '.join(sizing_bits) or '(none)'}\n\n"
        f"CANDIDATES:\n{_render_candidates(candidates)}\n\n"
        "Pick the describing paper (or abstain) and return the structured object."
    )

    out = llm.complete_structured(
        system=system, user=user, json_schema=schema,
        schema_name=SCHEMA_NAME, schema_description="Pick the describing paper for an accession.",
        model=model,
    )

    idx = out.get("chosen_index")
    none_found = bool(out.get("none_found")) or idx is None or not candidates
    chosen = None if none_found else candidates[idx]
    confidence = out.get("find_confidence", "low")

    verified: bool | None = None
    sources_agreeing = 0
    if chosen is not None:
        verified = verify_pick(chosen, accession, aliases=aliases, cache_dir=fulltext_cache)
        if channels:
            sources_agreeing = len(channels.get(_cand_key(chosen), set()))
        # `verified` is a trust SIGNAL, not a gate: describing papers often cite the accession only
        # in supplements, which the fetched full-text misses (observed for Genome Medicine/BMC), so
        # verified=False alone must NOT disqualify a pick (it would drop correct matches). Abstain
        # only on a low-confidence pick that is neither grounded-verified nor multi-source
        # corroborated — the weakest tier, where a wrong pick would otherwise poison grading.
        if chosen is not None and confidence == "low" and verified is not True and sources_agreeing < 2:
            none_found, chosen = True, None

    coverage = out.get("coverage_estimate")
    cov_frac = None
    if coverage is not None and taxon_n:
        try:
            cov_frac = round(int(coverage) / int(taxon_n), 4)
        except (ValueError, ZeroDivisionError):
            cov_frac = None

    return FindResult(
        study_accession=accession,
        none_found=none_found,
        chosen_title=chosen.title if chosen else None,
        chosen_pmid=chosen.pmid if chosen else None,
        chosen_pmcid=chosen.pmcid if chosen else None,
        chosen_doi=chosen.doi if chosen else None,
        chosen_found_via=chosen.found_via if chosen else None,
        find_confidence=confidence,
        coverage_estimate=coverage,
        coverage_fraction=cov_frac,
        verified=verified,
        sources_agreeing=sources_agreeing,
        n_candidates=len(candidates),
        flags=out.get("flags", {}),
        reasoning=out.get("reasoning", ""),
        model=model or getattr(llm, "model", ""),
        raw=out,
    )


FIND_ADJ_SCHEMA_NAME = "find_adjudication"
_FIND_VERDICTS = ["found_correct", "curated_correct", "both_describe", "neither"]
_ADJ_TEXT_CHARS = 60_000  # per-paper truncation for the two-paper adjudication prompt


def adjudicate_find(
    llm: LLMClient,
    *,
    accession: str,
    ena_title: str,
    ena_description: str,
    sizing_row: dict | None,
    found_label: str,
    found_text: str,
    curated_label: str,
    curated_text: str,
    model: str | None = None,
) -> dict:
    """Adjudicate a finder mismatch: are the two the same paper, and which describes the project.

    Used by the validator when the found paper ≠ the curated ``paper_link``. The curated link is
    NOT assumed correct (it may be wrong, paywalled, or one of several). Returns a dict with
    ``same_paper`` (the two links are the same work — incl. a preprint vs its published version, or
    two URLs for one article), ``same_paper_reason``, ``verdict`` (found_correct / curated_correct /
    both_describe / neither), a verbatim ``justification_quote``, ``reasoning``, and any ``rule_gap``.

    ``same_paper`` is the key signal the validator wants: a "mismatch" that is merely the same paper
    under a different link/DOI is not a finding error — only a genuinely different (or wrong) paper is.
    """
    sizing_row = sizing_row or {}
    schema = {
        "type": "object",
        "properties": {
            "same_paper": {"type": "boolean"},
            "same_paper_reason": {"type": "string"},
            "verdict": {"type": "string", "enum": _FIND_VERDICTS},
            "justification_quote": {"type": "string"},
            "reasoning": {"type": "string"},
            "rule_gap": {"type": "string"},
        },
        "required": ["same_paper", "same_paper_reason", "verdict", "justification_quote", "reasoning", "rule_gap"],
        "additionalProperties": False,
    }
    system = (
        "You are an adversarial adjudicator comparing two paper references for one bacterial-genomics "
        "project. Do TWO things. (1) same_paper: decide whether PAPER A and PAPER B are the SAME work "
        "— identical article, or a preprint and its peer-reviewed publication, or two URLs/DOIs/IDs "
        "for one article (compare titles, authors, cohort, sample counts, findings — not just the "
        "link). A different DOI does NOT mean a different paper. Give same_paper_reason briefly. "
        "(2) verdict: which paper actually DESCRIBES this project (the primary study that "
        "generated/deposited its genomes) vs one that merely reuses/cites the data — found_correct, "
        "curated_correct, both_describe (incl. when same_paper), or neither. Judge ONLY from the "
        "provided text + ENA metadata; neither paper is assumed correct (the hand-curated one may be "
        "wrong or one of several). Quote verbatim from whichever paper decides it. If the deciding "
        "evidence is missing, use verdict=neither. rule_gap: note any systematic finder weakness this "
        "case reveals (else empty)."
    )
    taxon_n = sizing_row.get("ena_taxon_samples")
    user = (
        f"PROJECT ACCESSION: {accession}\n"
        f"ENA title: {ena_title or '(none)'}\nENA description: {(ena_description or '(none)')[:800]}\n"
        f"ENA taxon samples: {taxon_n}\n\n"
        f"PAPER A — {found_label}\n{(found_text or '(no text)')[:_ADJ_TEXT_CHARS]}\n\n"
        f"PAPER B — {curated_label}\n{(curated_text or '(no text)')[:_ADJ_TEXT_CHARS]}\n\n"
        "Are A and B the same paper, and which one describes THIS project? Return the structured object."
    )
    return llm.complete_structured(
        system=system, user=user, json_schema=schema,
        schema_name=FIND_ADJ_SCHEMA_NAME, schema_description="Adjudicate which paper describes the project.",
        model=model,
    )


def write_results(results: list[FindResult], jsonl_path, tsv_path) -> None:
    """Write finder results to JSONL (full) + a flat TSV (one row per accession)."""
    import json

    import pandas as pd

    jsonl_path, tsv_path = Path(jsonl_path), Path(tsv_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    pd.DataFrame([r.to_row() for r in results]).to_csv(tsv_path, sep="\t", index=False)
