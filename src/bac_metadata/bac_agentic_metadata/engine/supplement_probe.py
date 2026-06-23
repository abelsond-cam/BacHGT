"""LLM opinion: does a paper actually carry a per-sample (per-isolate) metadata table?

Per-sample backfill (:mod:`engine.sample_extractor`) can only fill ``isolation_source`` / ``host`` /
``collection_date`` per sample when the paper provides a **per-isolate table** — individual
strains/isolates listed with those fields and keyed by an ID we can join to a sequencing accession
(usually a supplementary table). Many papers report only study-level summaries and have no such table,
so manually hunting their supplementary files is wasted effort.

This probe asks the model — grounded strictly in the paper text we already hold (open-access full text
or a manually-downloaded PDF) — whether such a table exists, which fields it covers, and where it is
referenced. It lets the curator chase only the studies that genuinely hold per-sample data, and flags
the *paywalled* ones whose supplementary file we still need to fetch by hand.
"""

from __future__ import annotations

from .llm import LLMClient

SCHEMA_NAME = "per_sample_table_opinion"

#: JSON schema the model must satisfy — a structured, auditable opinion (no free-form prose to parse).
OPINION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "has_per_sample_table": {
            "type": "string",
            "enum": ["yes", "likely", "no", "unclear"],
            "description": "Does the paper provide a per-isolate/per-sample metadata table?",
        },
        "fields_present": {
            "type": "array",
            "items": {"type": "string", "enum": ["isolation_source", "host", "collection_date"]},
            "description": "Which of the target fields that per-isolate table carries (empty if none).",
        },
        "accession_keyed": {
            "type": "string",
            "enum": ["yes", "no", "unclear"],
            "description": "Is each row keyed by a strain/sample/run ID we could join to an accession?",
        },
        "table_reference": {
            "type": "string",
            "description": "Where the table is (e.g. 'Supplementary Table S1', 'Additional file 2'); '' if none.",
        },
        "evidence_quote": {
            "type": "string",
            "description": "Short verbatim sentence from the paper that supports the verdict ('' if none).",
        },
        "reasoning": {"type": "string", "description": "One sentence tying the quote to the verdict."},
    },
    "required": ["has_per_sample_table", "fields_present", "accession_keyed", "table_reference",
                 "evidence_quote", "reasoning"],
}


def _system_prompt() -> str:
    """The grounded, abstaining instruction for the per-sample-table opinion."""
    return (
        "You judge whether a microbial-genomics paper provides PER-SAMPLE (per-isolate) metadata: a "
        "table that lists INDIVIDUAL isolates/strains as rows, each with one or more of isolation "
        "source, host, and collection date, and keyed by a strain / sample / run / BioSample ID that "
        "could be joined to a sequencing accession. This is usually a supplementary table (e.g. "
        "'Table S1', 'Additional file 1', a supplementary .xlsx). It is the data a curator would need "
        "to fill those fields for each genome, so your verdict decides whether fetching the paper's "
        "supplementary file is worthwhile.\n\n"
        "Judge ONLY from the provided paper text — do not assume a table exists because the study has "
        "many isolates. A paper that only reports aggregate counts (e.g. '60% were from blood') or a "
        "summary table by group, with NO per-isolate listing keyed by an ID, is 'no'. Reference to a "
        "per-isolate supplementary table (even if its file is not included in the text) is 'yes' / "
        "'likely'. Return the structured opinion; quote a short verbatim sentence as evidence."
    )


def probe_supplement(
    fulltext: str,
    llm: LLMClient,
    *,
    model: str | None = None,
    max_chars: int = 120_000,
) -> dict:
    """Return the model's structured opinion on whether ``fulltext`` carries a per-sample table.

    Parameters
    ----------
    fulltext
        The paper's full text (open-access or from a manually-downloaded PDF). Truncated to
        ``max_chars`` to bound cost.
    llm
        A configured :class:`~engine.llm.LLMClient` (disk-cached; subscription or API).
    model
        Optional model override.
    max_chars
        Character cap on the paper text sent to the model.

    Returns
    -------
    dict
        Validated against :data:`OPINION_SCHEMA`.
    """
    text = (fulltext or "").strip()[:max_chars]
    user = (
        "Decide whether THIS paper provides a per-isolate metadata table (isolation source / host / "
        "collection date, keyed by a strain/sample/run ID).\n\n=== PAPER TEXT ===\n" + (text or "(no text)")
    )
    return llm.complete_structured(
        system=_system_prompt(),
        user=user,
        json_schema=OPINION_SCHEMA,
        schema_name=SCHEMA_NAME,
        schema_description="Structured opinion on per-sample-table presence in a paper.",
        model=model,
    )
