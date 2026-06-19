"""Audit *why the grader declined a whole-project (whole-field) backfill* — the step-a rubric probe.

The completeness-gap diagnosis found that ~45% of the residual date/source gap vs ``metadata_v2`` is
**whole-field-we-failed-to-fire**: studies where the manual curator annotated the whole project to one
uniform value (so a whole-field fill was the right model) but our grader set ``applies_whole_project
false`` / ``proposed_value null``. This module turns the grader and the adjudicator inward on those
declines to find **systematic gaps in the rubric** (``attributes.yaml``) — David's "ask the LLM to
justify, in its current pitch, why it decided *not* to, then adjudicate for rule gaps".

Two LLM stages, both reusing the existing seams (no rubric edit):

1. :func:`justify_whole_field_decline` — present the grader **its own current pitch** (the grading
   system prompt rendered from ``attributes.yaml``) plus the *same* evidence it graded on and its prior
   per-field decision, and ask it to explain precisely why it did not propose a single whole-project
   value — and whether, on reflection, one is in fact supported. Returns a ``blocking_category``
   (no_paper_text / coverage / not-uniform / multi-token-or-range / absent / other) so the gap splits
   deterministically into *fetch-limited* vs *genuine rubric* causes.
2. :func:`adjudicate_whole_field_rule_gap` — an adversarial second opinion (typically Opus) that, given
   the grader's stated reason, the paper, the current backfill rule, and the curator's uniform value,
   rules whether the decline is a fixable **rule_gap**, *fetch_limited*, *coverage_gate*, a
   *correct_decline*, or *curator_overcollapsed* — and, when a rule gap, drafts the precise clause to
   add to ``attributes.yaml`` (a recommendation only; the YAML changes with David, never here).

Diagnostic harness: it writes no rubric and no production data; the curator's uniform value is used
only as the adjudication anchor (the curated sheet is gold-but-fallible, exactly as in
:mod:`~bac_metadata.bac_agentic_metadata.engine.adjudicator`).
"""

from __future__ import annotations

from .grader import DEFAULT_MAX_CHARS, _backfill_fields, _build_system_prompt, _build_user_prompt
from .llm import LLMClient
from .spec import AttributeSpec

JUSTIFY_SCHEMA_NAME = "whole_field_decline_justification"
ADJUDICATE_SCHEMA_NAME = "whole_field_rule_gap_adjudication"

#: Why the grader declined — the categories that split the whole-field gap into fetch vs rubric causes.
BLOCKING_CATEGORIES = [
    "no_paper_text",                 # only an abstract / nothing was available → a fetch problem, not a rule gap
    "value_below_coverage_threshold",  # value present + uniform but paper coverage < the whole-project gate
    "value_not_uniform_in_paper",    # the paper describes several sources/dates → not whole-field from the text
    "value_multi_token_or_range",    # one concept but not one token (e.g. "blood and/or CSF"; a year range)
    "value_absent_from_evidence",    # the field simply is not stated in the evidence given
    "other",
]

#: Adjudicator verdicts on a decline — only ``rule_gap`` is an actionable ``attributes.yaml`` change.
ADJUDICATION_VERDICTS = [
    "rule_gap",              # the rubric should have allowed a whole-field call here and does not
    "fetch_limited",         # the grader had no/poor paper text → not a rubric problem
    "coverage_gate",         # paper coverage genuinely < the gate → a gate-threshold question, not wording
    "correct_decline",       # the field genuinely is not whole-field-uniform from the evidence
    "curator_overcollapsed",  # the curator collapsed a genuinely-varying field to one value (sheet wrong)
]


def _justify_schema() -> dict:
    """Schema for the grader's self-justification of one whole-field decline."""
    return {
        "type": "object",
        "properties": {
            "would_propose_now": {"type": "boolean"},
            "proposed_value": {"type": ["string", "null"]},
            "blocking_category": {"type": "string", "enum": BLOCKING_CATEGORIES},
            "blocking_reason": {"type": "string"},
            "blocking_rubric_clause": {"type": "string"},
            "evidence_quote": {"type": "string"},
        },
        "required": [
            "would_propose_now", "proposed_value", "blocking_category",
            "blocking_reason", "blocking_rubric_clause", "evidence_quote",
        ],
        "additionalProperties": False,
    }


def _adjudicate_schema() -> dict:
    """Schema for the adversarial rule-gap adjudication of one decline."""
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ADJUDICATION_VERDICTS},
            "rule_gap": {"type": "string"},
            "recommended_clause": {"type": "string"},
            "reasoning": {"type": "string"},
        },
        "required": ["verdict", "rule_gap", "recommended_clause", "reasoning"],
        "additionalProperties": False,
    }


def _field_rule(spec: AttributeSpec, field: str) -> str:
    """Render the current whole-project backfill rule for one field, verbatim from the rubric."""
    frule = _backfill_fields(spec).get(field, {})
    meaning = frule.get("meaning", "")
    rule = (frule.get("whole_project_value", "") or "").strip()
    return f"[{field}] {meaning}\n{rule}".strip()


def justify_whole_field_decline(
    spec: AttributeSpec,
    llm: LLMClient,
    *,
    accession: str,
    field: str,
    fulltext,
    ena_title: str,
    ena_description: str,
    sizing_row: dict | None,
    prior_proposed: str | None,
    prior_whole_project: bool,
    prior_quote: str,
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Ask the grader, in its current pitch, to justify why it declined a whole-field fill for ``field``.

    The system prompt is the **grader's own** rubric framing (so the reasoning is grounded in the exact
    rules it grades by) and the evidence block is the same one it graded on. We add the grader's prior
    per-field decision and a focused follow-up; nothing reveals the curator's answer (this is the
    grader introspecting, not copying).

    Returns the validated justification dict (see :func:`_justify_schema`).
    """
    system = _build_system_prompt(spec)
    evidence = _build_user_prompt(
        accession=accession,
        fulltext=fulltext,
        ena_title=ena_title,
        ena_description=ena_description,
        sizing_row=sizing_row,
        max_chars=max_chars,
    )
    follow_up = (
        "\n\n=== FOLLOW-UP (this supersedes the grading instruction above) ===\n"
        f"Earlier you graded this accession. For the whole-project backfill of `{field}` you returned "
        f"proposed_value={prior_proposed!r}, applies_whole_project={prior_whole_project!r} "
        f"(evidence quote: {prior_quote!r}).\n\n"
        "The current whole-project backfill rule for this field is:\n"
        f"{_field_rule(spec, field)}\n\n"
        f"Explain PRECISELY why you did not propose a single whole-project value for `{field}`: which "
        "rubric clause or evidence limitation blocked it (quote the blocking clause verbatim into "
        "blocking_rubric_clause, empty string if the block was missing evidence rather than a rule). "
        "Pick the blocking_category that best fits. Then judge afresh whether the evidence DOES support "
        "one value for the whole project: set would_propose_now and, if true, proposed_value (else "
        "null). Use only the evidence above; do not guess. Return the structured object."
    )
    return llm.complete_structured(
        system=system,
        user=evidence + follow_up,
        json_schema=_justify_schema(),
        schema_name=JUSTIFY_SCHEMA_NAME,
        schema_description="Why the grader declined a whole-project backfill for one field.",
        model=model,
    )


def adjudicate_whole_field_rule_gap(
    spec: AttributeSpec,
    llm: LLMClient,
    *,
    accession: str,
    field: str,
    paper_text: str,
    grader_reason: str,
    grader_blocking_category: str,
    grader_blocking_clause: str,
    curator_value: str,
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Adversarially decide whether a whole-field decline is a fixable rule gap, and draft the clause.

    Anchored on the curator's uniform value (gold-but-fallible) and the current rule, the adjudicator
    classifies the decline (see :data:`ADJUDICATION_VERDICTS`) and, only when ``rule_gap``, drafts the
    precise clarification ``attributes.yaml`` would need — a recommendation, never applied here.

    Returns the validated adjudication dict (see :func:`_adjudicate_schema`).
    """
    system = (
        "You are an adversarial ADJUDICATOR auditing an automated metadata grader's RUBRIC. On the "
        "study below, an independent manual curator annotated the WHOLE project to a single uniform "
        f"value for `{field}`, but the grader DECLINED to propose a whole-project value. The curated "
        "sheet is gold-but-fallible (it has known errors), so ruling the curator wrong is allowed.\n\n"
        "Decide the cause of the decline, judging ONLY from the paper text and the grader's stated "
        "reason:\n"
        "- rule_gap: the rubric SHOULD permit a whole-field call here (e.g. it offers no way to map a "
        "two-token clinical source like 'blood and/or CSF' to one value, or to treat an invasive-disease "
        "cohort as uniform) and that wording gap caused the decline. This is the only actionable verdict.\n"
        "- fetch_limited: the grader had no/poor paper text — not a rubric problem.\n"
        "- coverage_gate: the value is uniform but the paper genuinely covers <90% of the project, so "
        "the whole-project gate (a threshold, not wording) blocked it.\n"
        "- correct_decline: the paper genuinely shows the field varies → no single whole-field value.\n"
        "- curator_overcollapsed: the field varies in the paper but the curator forced one value (the "
        "sheet is the one in error).\n\n"
        "When and only when verdict is rule_gap, write rule_gap (what the current rule fails to cover) "
        "and recommended_clause (the precise sentence to ADD to this field's whole_project_value rule). "
        "Otherwise leave both empty. Keep reasoning to one or two sentences.\n\n"
        f"=== CURRENT whole-project backfill rule for `{field}` ===\n{_field_rule(spec, field)}"
    )
    text = paper_text or "(no paper text available)"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[...truncated...]"
    user = (
        f"PROJECT ACCESSION: {accession}\nFIELD: {field}\n\n"
        f"CURATOR's uniform whole-project value: {curator_value!r}\n\n"
        f"GRADER's stated blocking_category: {grader_blocking_category!r}\n"
        f"GRADER's stated reason: {grader_reason!r}\n"
        f"GRADER's quoted blocking clause: {grader_blocking_clause!r}\n\n"
        f"--- PAPER TEXT START ---\n{text}\n--- PAPER TEXT END ---\n\n"
        "Classify the decline and, if a rule gap, draft the clause. Return the structured object."
    )
    return llm.complete_structured(
        system=system,
        user=user,
        json_schema=_adjudicate_schema(),
        schema_name=ADJUDICATE_SCHEMA_NAME,
        schema_description="Adjudication of one whole-field backfill decline for rubric rule gaps.",
        model=model,
    )
