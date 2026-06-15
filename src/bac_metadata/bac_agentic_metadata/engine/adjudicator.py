"""Adjudicate grader-vs-ground-truth disagreements (a critique / second-opinion agent).

When the grader's value for a study-level attribute disagrees with the curated sheet, this runs an
**adversarial adjudicator**: it re-reads the paper against the rubric definition and decides which
label is correct, quoting **verbatim** from the paper, and flags any **rule gap** — wording in the
rubric that is ambiguous or missing a case and likely caused the disagreement. The gold standard
has known imperfections, so the adjudicator is explicitly allowed to rule the *sheet* wrong.

First pass uses the same LLM backend as the grader (optionally a stronger model, e.g. Opus, since
it runs only on the handful of disagreements); the :class:`~...engine.llm.LLMClient` seam means a
distinct/opposing backend can be swapped in later. Output is structured (forced where the backend
supports it; schema-validated otherwise) → a per-disagreement record with the verbatim
justification, plus aggregated rule-gap lessons for tightening ``attributes.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grader import DEFAULT_MAX_CHARS, _study_level_attributes
from .llm import LLMClient
from .spec import AttributeSpec

SCHEMA_NAME = "disagreement_adjudication"
VERDICTS = ["model_correct", "sheet_correct", "both_defensible", "undetermined"]


def _attribute_block(spec: AttributeSpec, attribute: str) -> dict:
    """Return the rubric block for one study-level attribute (values + definition)."""
    return _study_level_attributes(spec).get(attribute, {})


def build_adjudication_schema(attr_values: list) -> dict:
    """Build the forced-tool-use / validation schema for one adjudication."""
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": VERDICTS},
            "correct_value": {"type": ["string", "null"], "enum": [*attr_values, None]},
            "justification_quote": {"type": "string"},
            "reasoning": {"type": "string"},
            "rule_gap": {"type": "string"},
        },
        "required": ["verdict", "correct_value", "justification_quote", "reasoning", "rule_gap"],
        "additionalProperties": False,
    }


@dataclass
class Adjudication:
    """One adjudicated disagreement."""

    study_accession: str
    attribute: str
    model_value: str | None
    sheet_value: str | None
    sheet_value_raw: str
    verdict: str
    correct_value: str | None
    justification_quote: str
    reasoning: str
    rule_gap: str
    model: str

    def to_row(self) -> dict:
        """Flatten for a TSV row."""
        return {
            "study_accession": self.study_accession,
            "attribute": self.attribute,
            "model_value": self.model_value,
            "sheet_value": self.sheet_value,
            "verdict": self.verdict,
            "correct_value": self.correct_value,
            "rule_gap": self.rule_gap,
        }


def adjudicate(
    spec: AttributeSpec,
    llm: LLMClient,
    *,
    accession: str,
    attribute: str,
    paper_text: str,
    model_value: str | None,
    model_quote: str,
    sheet_value_norm: str | None,
    sheet_value_raw: str,
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Adjudication:
    """Adjudicate one grader-vs-sheet disagreement and return an :class:`Adjudication`.

    Parameters
    ----------
    spec
        Application spec (supplies the rubric definition + grading basis).
    llm
        Any :class:`LLMClient` (the adjudicator backend; may differ from the grader's).
    accession
        Project accession.
    attribute
        Study-level attribute in dispute (e.g. ``"amr_study"``, ``"study_setting"``).
    paper_text
        The paper text the grader saw (truncated to ``max_chars``).
    model_value, model_quote
        The grader's value and the evidence quote it gave.
    sheet_value_norm, sheet_value_raw
        The curated sheet's normalised value and its raw text.
    model
        Per-call model override (e.g. escalate to Opus for the critique).
    max_chars
        Paper-text truncation ceiling.

    Returns
    -------
    Adjudication
        The verdict, the corrected value, a verbatim justification, and any rule gap.
    """
    block = _attribute_block(spec, attribute)
    values = block.get("values", [])
    definition = (block.get("definition", "") or "").strip()
    grading_basis = (
        spec.raw.get("attributes", {}).get("study_level", {}).get("grading_basis", "") or ""
    ).strip()
    schema = build_adjudication_schema(list(values))

    system = (
        "You are an adversarial ADJUDICATOR giving a rigorous second opinion. For one project "
        "accession, an automated grader and a hand-curated spreadsheet DISAGREE on a single "
        "study-level attribute. Decide which is correct STRICTLY per the rubric and the paper — "
        "judge ONLY from the paper text provided, not outside knowledge. The curated sheet is NOT "
        "assumed correct; it has known errors, so ruling the sheet wrong is expected when the paper "
        "supports it.\n\n"
        "Return: verdict (model_correct / sheet_correct / both_defensible / undetermined); "
        "correct_value (the rubric value you judge correct, or null if undetermined); "
        "justification_quote (a SHORT VERBATIM quote from the paper that decides it — empty only if "
        "undetermined); reasoning (one or two sentences tying the quote to the rubric); rule_gap "
        "(if the rubric wording is ambiguous or missing the case that caused this disagreement, "
        "describe precisely what to clarify in the definition — else empty string).\n\n"
        f"=== RUBRIC for `{attribute}` ===\n"
        f"Allowed values: {values}\n"
        f"Definition:\n{definition}\n\n"
        f"Grading basis (gradeable/partial/not_gradeable):\n{grading_basis}"
    )

    text = paper_text or "(no paper text available)"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[...truncated...]"
    user = (
        f"PROJECT ACCESSION: {accession}\n"
        f"ATTRIBUTE IN DISPUTE: {attribute}\n\n"
        f"GRADER's value: {model_value!r}\n"
        f"GRADER's evidence quote: {model_quote!r}\n\n"
        f"CURATED SHEET's value (normalised): {sheet_value_norm!r}\n"
        f"CURATED SHEET's raw text: {sheet_value_raw!r}\n\n"
        f"--- PAPER TEXT START ---\n{text}\n--- PAPER TEXT END ---\n\n"
        "Adjudicate which value is correct and return the structured object."
    )

    out = llm.complete_structured(
        system=system,
        user=user,
        json_schema=schema,
        schema_name=SCHEMA_NAME,
        schema_description="Adjudication of one grader-vs-sheet disagreement.",
        model=model,
    )
    return Adjudication(
        study_accession=accession,
        attribute=attribute,
        model_value=model_value,
        sheet_value=sheet_value_norm,
        sheet_value_raw=sheet_value_raw,
        verdict=out.get("verdict", "undetermined"),
        correct_value=out.get("correct_value"),
        justification_quote=out.get("justification_quote", ""),
        reasoning=out.get("reasoning", ""),
        rule_gap=out.get("rule_gap", ""),
        model=model or getattr(llm, "model", ""),
    )
