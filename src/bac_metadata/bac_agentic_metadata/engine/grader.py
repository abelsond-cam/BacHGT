"""Grade one project accession against the application rubric (the first LLM stage).

The grader renders the rubric **straight from the application's** ``attributes.yaml`` — both the
forced-tool-use JSON schema (value sets, grade scale) and the natural-language prompt (each
attribute's ``definition`` plus the shared ``grading_basis``). The YAML stays the single source
of truth: add or change an attribute there and the grader follows, no code edit.

Per accession it produces, using only the supplied evidence (paper text + EBI study
title/description + ENA assessment sizing):

* ``study_type`` — the filter value (studies in the spec's ``exclude_if`` set are flagged excluded).
* each **study-level attribute** — ``{value, grade, evidence_quote}`` graded against the rubric's
  ``grade_scale`` and ``grading_basis``.
* ``paper_coverage_for_taxon`` — the LLM reports how many taxon-of-interest samples the paper
  describes; the engine divides by the ENA assessment ``ena_taxon_samples`` to get the fraction (the gate
  for whole-project backfill).
* **whole-field whole-project backfill** proposals for the four standard fields (country,
  isolation_source, host, collection_date).
* ``needs_manual_download`` — a paper was found but its full text was not reachable.

Output is a :class:`GradeResult` → JSONL (full, with evidence quotes) + a flat TSV (one row per
accession) for the validator.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import value_validity as vv
from .fulltext import FullText
from .llm import LLMClient
from .spec import AttributeSpec

#: Truncate paper text beyond this many characters (~30k tokens) to bound per-call cost.
DEFAULT_MAX_CHARS = 120_000
SCHEMA_NAME = "study_grade"

#: Generic FALLBACK for the whole-project fill rule rendered to the grader. The application supplies its own
#: policy text at ``attributes.per_sample_completeness.backfill.whole_project_rule`` (Klebsiella does — see its
#: attributes.yaml); the engine only assembles + renders it. Kept generic here so an app that omits it still
#: gets a sane, species-agnostic instruction.
_DEFAULT_WHOLE_PROJECT_RULE = (
    "Propose a single value for ALL samples (applies_whole_project true) when one value covers essentially "
    "the whole project — study-wide-constant, or a predominant value shared by the vast majority of samples "
    "(only genuine blanks are filled; per-sample and existing values are never overwritten). Only under "
    "whole-project coverage (paper coverage > 75%, or an EBI-wide title/description), for the categorical "
    "fields (host, country, isolation_source). When the values are genuinely mixed with no predominant value, "
    "set applies_whole_project false but STILL give your best proposed_value if you have one. For "
    "collection_date, do NOT propose a value: report the EARLIEST and LATEST collection dates (earliest_date, "
    "latest_date, verbatim — a year alone is fine); the engine computes the span deterministically."
)


# --------------------------------------------------------------------------------------------- #
# Rubric introspection — pull the gradeable attributes out of the parsed YAML.
# --------------------------------------------------------------------------------------------- #
def _study_level_attributes(spec: AttributeSpec) -> dict[str, dict]:
    """Return the study-level attributes (dict entries with a ``values`` list), in YAML order."""
    block = spec.raw.get("attributes", {}).get("study_level", {})
    return {k: v for k, v in block.items() if isinstance(v, dict) and "values" in v}


def _study_type_spec(spec: AttributeSpec) -> dict:
    """Return the ``study_filters.study_type`` block."""
    return spec.raw.get("attributes", {}).get("study_filters", {}).get("study_type", {})


def _backfill_fields(spec: AttributeSpec) -> dict[str, dict]:
    """Return the per-field backfill rules (``per_sample_completeness.backfill.fields``)."""
    return (
        spec.raw.get("attributes", {})
        .get("per_sample_completeness", {})
        .get("backfill", {})
        .get("fields", {})
    )


def _grade_scale(spec: AttributeSpec) -> list[str]:
    """Return the grade scale (``[gradeable, partial, not_gradeable]``)."""
    return list(spec.raw.get("grade_scale", ["gradeable", "partial", "not_gradeable"]))


def whole_project_rule(spec: AttributeSpec) -> str:
    """Return the application's whole-project fill rule text (yaml), or the generic engine default."""
    txt = (
        spec.raw.get("attributes", {})
        .get("per_sample_completeness", {})
        .get("backfill", {})
        .get("whole_project_rule", "")
    )
    return (txt or "").strip() or _DEFAULT_WHOLE_PROJECT_RULE


def date_span_policy(spec: AttributeSpec) -> dict:
    """Return the application's collection_date span thresholds (yaml ``escalation.collection_date``).

    Missing keys fall back to the engine defaults in :mod:`value_validity` — the date-span *machinery* is
    generic; only the thresholds (2yr / 5yr / pre-2010) are application policy (David, 2026-07-14).
    """
    cd = (spec.raw.get("escalation", {}) or {}).get("collection_date", {}) or {}
    return {
        "two_year_months": int(cd.get("two_year_months", vv.DATE_SPAN_TWO_YEAR_MONTHS)),
        "five_year_months": int(cd.get("five_year_months", vv.DATE_SPAN_FIVE_YEAR_MONTHS)),
        "old_before_year": int(cd.get("old_before_year", vv.DATE_OLD_BEFORE_YEAR)),
    }


# --------------------------------------------------------------------------------------------- #
# JSON schema for forced tool use, built from the rubric.
# --------------------------------------------------------------------------------------------- #
def build_grade_schema(spec: AttributeSpec) -> dict:
    """Build the forced-tool-use JSON schema from the rubric (enums = the YAML value sets)."""
    grade_scale = _grade_scale(spec)
    study_level = _study_level_attributes(spec)
    study_type = _study_type_spec(spec)
    backfill = _backfill_fields(spec)

    def attr_obj(values: list) -> dict:
        return {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "null"], "enum": [*values, None]},
                "grade": {"type": "string", "enum": grade_scale},
                "evidence_quote": {"type": "string"},
            },
            "required": ["value", "grade", "evidence_quote"],
            "additionalProperties": False,
        }

    study_level_props = {name: attr_obj(a["values"]) for name, a in study_level.items()}
    backfill_props = {}
    for name in backfill:
        props = {
            "proposed_value": {"type": ["string", "null"]},
            "applies_whole_project": {"type": "boolean"},
            "evidence_quote": {"type": "string"},
        }
        required = ["proposed_value", "applies_whole_project", "evidence_quote"]
        if name == "collection_date":
            # The grader reports the two endpoint dates VERBATIM; the engine computes the span + fill
            # deterministically (value_validity.resolve_date_span) rather than trusting LLM calendar-label
            # arithmetic (David, 2026-07-13). proposed_value/applies_whole_project are overwritten post-grade.
            props["earliest_date"] = {"type": ["string", "null"]}
            props["latest_date"] = {"type": ["string", "null"]}
            required += ["earliest_date", "latest_date"]
        backfill_props[name] = {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        }

    return {
        "type": "object",
        "properties": {
            "study_type": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "enum": list(study_type.get("values", []))},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["value", "evidence_quote"],
                "additionalProperties": False,
            },
            "study_level": {
                "type": "object",
                "properties": study_level_props,
                "required": list(study_level_props),
                "additionalProperties": False,
            },
            "paper_coverage": {
                "type": "object",
                "properties": {
                    "paper_records_in_taxon": {"type": ["integer", "null"]},
                    "basis": {"type": "string"},
                },
                "required": ["paper_records_in_taxon", "basis"],
                "additionalProperties": False,
            },
            "backfill": {
                "type": "object",
                "properties": backfill_props,
                "required": list(backfill_props),
                "additionalProperties": False,
            },
            "needs_manual_download": {"type": "boolean"},
            "notes": {"type": "string"},
        },
        "required": ["study_type", "study_level", "paper_coverage", "backfill", "needs_manual_download", "notes"],
        "additionalProperties": False,
    }


# --------------------------------------------------------------------------------------------- #
# Prompt construction — render the rubric definitions verbatim from the YAML.
# --------------------------------------------------------------------------------------------- #
def _render_rubric(spec: AttributeSpec) -> str:
    """Render the gradeable rubric (definitions, grade scale, backfill rules) as prompt text."""
    raw = spec.raw
    toi = raw["taxon_of_interest"]
    grade_scale = _grade_scale(spec)
    study_level_block = raw.get("attributes", {}).get("study_level", {})
    sizing_first = study_level_block.get("sizing_first", "")
    grading_basis = study_level_block.get("grading_basis", "")
    coverage_def = (
        raw.get("attributes", {})
        .get("paper_selection", {})
        .get("paper_coverage_for_taxon", {})
        .get("definition", "")
    )

    lines: list[str] = []
    lines.append(f"TAXON OF INTEREST: {toi['name']} (rank: {toi['rank']}). Count and grade only records of this taxon.")
    if sizing_first:
        lines.append(f"\n{sizing_first}")
    lines.append(f"\nGRADE SCALE: {grade_scale}")
    if grading_basis:
        lines.append(f"\nGRADING BASIS (applies to every study-level attribute):\n{grading_basis}")

    st = _study_type_spec(spec)
    if st:
        lines.append("\n--- STUDY FILTER ---")
        lines.append(f"study_type — values {st.get('values', [])}; excluded if value in {st.get('exclude_if', [])}.")
        lines.append((st.get("definition", "") or "").strip())

    lines.append("\n--- STUDY-LEVEL ATTRIBUTES (one value for the whole project) ---")
    for name, a in _study_level_attributes(spec).items():
        header = f"\n[{name}] values: {a.get('values', [])}"
        if a.get("applies_when"):
            header += f"  (applies_when: {a['applies_when']})"
        lines.append(header)
        lines.append((a.get("definition", "") or "").strip())

    bf = _backfill_fields(spec)
    if bf:
        lines.append("\n--- WHOLE-PROJECT BACKFILL (whole-field) for the standard per-sample fields ---")
        lines.append(whole_project_rule(spec))
        for name, frule in bf.items():
            rule = (frule.get("whole_project_value", "") or "").strip()
            lines.append(f"\n[{name}] {frule.get('meaning', '')}\n{rule}")

    if coverage_def:
        lines.append("\n--- PAPER COVERAGE ---")
        lines.append(
            "Report paper_records_in_taxon = how many taxon-of-interest samples THIS paper describes "
            "(null if it cannot be determined). The engine divides it by the ENA taxon-sample count.\n"
            + coverage_def.strip()
        )
    return "\n".join(lines)


def _build_system_prompt(spec: AttributeSpec) -> str:
    """Assemble the system prompt: role, hard rules, and the rendered rubric."""
    return (
        "You are a careful biomedical curator grading one bacterial-genomics PROJECT ACCESSION "
        "against a FIXED rubric. Judge ONLY from the evidence provided (the paper text and the EBI "
        "study title/description). Do NOT use outside knowledge and do NOT guess.\n\n"
        "Rules:\n"
        "- A study-level value may be graded `gradeable` only when the evidence supports a single "
        "value for the WHOLE project (per the grading basis). If it applies to only part of the "
        "project and cannot be tied to specific samples, use `partial`. If the evidence does not "
        "determine it, use `not_gradeable` and set value null.\n"
        "- For each attribute give a short verbatim evidence_quote from the supplied text "
        "supporting your choice (empty string if not_gradeable).\n"
        "- amr_target and amr_method apply only when amr_study is amr or mixed; otherwise value "
        "null, grade not_gradeable.\n"
        "- Backfill proposals are whole-field whole-project values only; never invent per-sample values.\n"
        "- Set needs_manual_download true only if a paper clearly exists but its full text was not "
        "available to you (you were given only an abstract or nothing).\n\n"
        "=== RUBRIC ===\n" + _render_rubric(spec)
    )


def _build_user_prompt(
    *,
    accession: str,
    fulltext: FullText,
    ena_title: str,
    ena_description: str,
    sizing_row: dict | None,
    max_chars: int,
) -> str:
    """Assemble the per-accession evidence prompt."""
    sizing_row = sizing_row or {}
    sizing_keys = [
        "ena_taxon_samples",
        "ena_total_samples",
        "ena_total_runs",
        "by_scientific_name",
        "classification",
        "coverage",
    ]
    sizing_lines = [f"  {k}: {sizing_row[k]}" for k in sizing_keys if k in sizing_row and sizing_row[k] not in ("", None)]

    paper_text = fulltext.text or "(no paper text available)"
    truncated = ""
    if len(paper_text) > max_chars:
        paper_text = paper_text[:max_chars]
        truncated = f"\n[...truncated to {max_chars} characters...]"

    return (
        f"PROJECT ACCESSION: {accession}\n\n"
        f"EBI STUDY TITLE: {ena_title or '(none)'}\n"
        f"EBI STUDY DESCRIPTION: {ena_description or '(none)'}\n\n"
        f"ENA SIZING (deterministic, ENA assessment):\n" + ("\n".join(sizing_lines) or "  (none)") + "\n\n"
        f"PAPER TEXT SOURCE: {fulltext.source} (full_text={fulltext.is_full_text})\n"
        f"PAPER TITLE: {fulltext.title or '(none)'}\n"
        f"--- PAPER TEXT START ---\n{paper_text}{truncated}\n--- PAPER TEXT END ---\n\n"
        "Grade this accession against the rubric and return the structured object."
    )


# --------------------------------------------------------------------------------------------- #
# Result types.
# --------------------------------------------------------------------------------------------- #
@dataclass
class GradeResult:
    """The graded output for one accession (full record; serialised to JSONL)."""

    study_accession: str
    study_type: str | None
    study_type_excluded: bool
    study_level: dict  # name -> {value, grade, evidence_quote}
    paper_records_in_taxon: int | None
    paper_coverage_for_taxon: float | None
    coverage_basis: str
    backfill: dict  # field -> {proposed_value, applies_whole_project, evidence_quote}
    needs_manual_download: bool
    fulltext_source: str
    is_full_text: bool
    notes: str
    model: str
    raw: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        """Flatten to a single TSV row (study-level value/grade + backfill value/applies columns)."""
        row: dict = {
            "study_accession": self.study_accession,
            "study_type": self.study_type,
            "study_type_excluded": self.study_type_excluded,
            "paper_records_in_taxon": self.paper_records_in_taxon,
            "paper_coverage_for_taxon": self.paper_coverage_for_taxon,
            "needs_manual_download": self.needs_manual_download,
            "fulltext_source": self.fulltext_source,
            "is_full_text": self.is_full_text,
            "model": self.model,
        }
        for name, g in self.study_level.items():
            row[f"{name}__value"] = g.get("value")
            row[f"{name}__grade"] = g.get("grade")
        for fname, b in self.backfill.items():
            row[f"backfill_{fname}__value"] = b.get("proposed_value")
            row[f"backfill_{fname}__whole_project"] = b.get("applies_whole_project")
        return row


def grade_accession(
    spec: AttributeSpec,
    llm: LLMClient,
    *,
    accession: str,
    fulltext: FullText,
    ena_title: str = "",
    ena_description: str = "",
    ena_taxon_samples: int | None = None,
    sizing_row: dict | None = None,
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> GradeResult:
    """Grade one accession against the rubric and return a :class:`GradeResult`.

    Parameters
    ----------
    spec
        The application :class:`AttributeSpec` (its ``attributes.yaml`` is the rubric).
    llm
        Any :class:`~bac_metadata.bac_agentic_metadata.engine.llm.LLMClient`.
    accession
        The project accession being graded.
    fulltext
        The :class:`FullText` resolved for the chosen paper.
    ena_title, ena_description
        EBI study title / description (the second evidence source).
    ena_taxon_samples
        ENA assessment distinct taxon-sample count; denominator for ``paper_coverage_for_taxon``.
    sizing_row
        Optional ENA assessment sizing row (surfaced to the model as context).
    model
        Per-call model override (e.g. escalate to Opus).
    max_chars
        Truncation ceiling for the paper text.

    Returns
    -------
    GradeResult
        The graded record. ``paper_coverage_for_taxon`` is computed here from the model's
        ``paper_records_in_taxon`` and ``ena_taxon_samples``.
    """
    schema = build_grade_schema(spec)
    system = _build_system_prompt(spec)
    user = _build_user_prompt(
        accession=accession,
        fulltext=fulltext,
        ena_title=ena_title,
        ena_description=ena_description,
        sizing_row=sizing_row,
        max_chars=max_chars,
    )
    out = llm.complete_structured(
        system=system,
        user=user,
        json_schema=schema,
        schema_name=SCHEMA_NAME,
        schema_description="Structured rubric grade for one project accession.",
        model=model,
    )

    # collection_date is resolved DETERMINISTICALLY from the grader's earliest/latest endpoints (never LLM span
    # arithmetic): the engine computes the true month span and applies David's 2yr/5yr/pre-2010 rule, overwriting
    # the model's proposed_value/applies_whole_project so whole-field backfill + escalation act on it uniformly.
    cd = (out.get("backfill", {}) or {}).get("collection_date")
    if isinstance(cd, dict):
        dec = vv.resolve_date_span(cd.get("earliest_date"), cd.get("latest_date"), **date_span_policy(spec))
        cd["proposed_value"] = dec["proposed_value"]
        cd["applies_whole_project"] = dec["applies_whole_project"]
        cd["date_decision"] = dec["date_decision"]
        cd["date_span_months"] = dec["span_months"]

    study_type_val = out.get("study_type", {}).get("value")
    exclude_if = set(_study_type_spec(spec).get("exclude_if", []))
    paper_records = out.get("paper_coverage", {}).get("paper_records_in_taxon")
    coverage = None
    if paper_records is not None and ena_taxon_samples and ena_taxon_samples > 0:
        coverage = round(paper_records / ena_taxon_samples, 4)

    return GradeResult(
        study_accession=accession,
        study_type=study_type_val,
        study_type_excluded=study_type_val in exclude_if,
        study_level=out.get("study_level", {}),
        paper_records_in_taxon=paper_records,
        paper_coverage_for_taxon=coverage,
        coverage_basis=out.get("paper_coverage", {}).get("basis", ""),
        backfill=out.get("backfill", {}),
        needs_manual_download=bool(out.get("needs_manual_download", False)),
        fulltext_source=fulltext.source,
        is_full_text=fulltext.is_full_text,
        notes=out.get("notes", ""),
        model=model or getattr(llm, "model", ""),
        raw=out,
    )


def write_results(results: list[GradeResult], jsonl_path: str | Path, tsv_path: str | Path) -> None:
    """Write graded results to JSONL (full) + a flat TSV (one row per accession)."""
    import pandas as pd

    jsonl_path = Path(jsonl_path)
    tsv_path = Path(tsv_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    df = pd.DataFrame([r.to_row() for r in results])
    # Nullable integer so a blank (no-paper) row does not coerce the column to float ("128.0"),
    # keeping reruns byte-identical regardless of which rows are missing a count.
    if "paper_records_in_taxon" in df.columns:
        df["paper_records_in_taxon"] = df["paper_records_in_taxon"].astype("Int64")
    df.to_csv(tsv_path, sep="\t", index=False)
