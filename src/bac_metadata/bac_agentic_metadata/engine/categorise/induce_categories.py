"""LLM category induction — propose a broad category scheme for a field from its value list.

Phase B of the agentic categoriser. Two stages, so each ``claude -p`` call stays small (a single
large call that emits detailed includes/excludes for ~12 categories over ~2000 distinct values times
out):

1. :func:`propose_scheme` — one call over the full value list → category **names + one-line
   definitions** (+ cross-field notes). Small output.
2. :func:`detail_category` — one bounded call **per category** → its detailed ``includes`` /
   ``excludes`` (with where-else-values-go) + verbatim ``examples``. Each output is small and is
   cached independently, so re-detailing one category doesn't re-run the rest.

Induction is **from-scratch but seeded**: the prompt shows the existing hardcoded scheme (if any) as
*one example, not binding*. The assembled proposal is written to a YAML for the curator to review/edit;
the approved scheme is pasted into ``attributes.yaml`` under ``categorisation.fields.<field>.categories``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from .value_frequencies import render_for_prompt

NAMES_SCHEMA_NAME = "propose_category_names"
DETAIL_SCHEMA_NAME = "detail_category"

_SHARED_RULES = """\
- Categories must be broad enough to be useful downstream, specific enough to be meaningful. Aim for
  roughly 6-15 categories, not one-per-value.
- ALWAYS include a final category named exactly `NA` for values that carry no usable information for
  this field (codes, IDs, uninterpretable strings).
- `laboratory` / `lab` / `in vitro` / `lab culture` / culture-medium names are a TAUTOLOGY — every
  isolate is grown in a lab, so these say nothing about the true host or source. They belong in `NA`,
  never in a real category.
- A "clinical environment / surface" category (if any) is ONLY for environmental swabs of clinical
  surfaces and equipment (sinks, beds, toilets, ventilators, drains) — NEVER for patient/human
  clinical samples, which are the human host / a named body-site source. Host categories in particular
  must name a SPECIFIC organism or environment, never a generic "clinical"/"patient" bucket.
"""

_NAMES_SYSTEM = f"""\
You are designing a categorisation scheme for a metadata field in a bacterial-genomics dataset.
You will be shown the field name and every distinct informative value with its sample count (one per
line, `count<TAB>value`). Propose a SMALL set of broad, mutually exclusive categories that cover the
values well. For EACH category give only a `name` (short snake/space) and a one-line `definition` —
the detailed inclusion/exclusion rules come in a later step.

{_SHARED_RULES}
- If a value clearly belongs to a DIFFERENT field (e.g. a disease code in a host column, a place name
  like a city/region/province in an isolation-source column), record it in `cross_field_notes` — do
  NOT invent a category for it.
- Prefer the seed scheme's categories where they fit, but add/merge/split/rename freely when the data
  does not fit. The seed is one example, not a constraint.
"""

_DETAIL_SYSTEM = """\
You are writing the precise coding rules for ONE category in a metadata categorisation scheme for a
bacterial-genomics dataset. A downstream agent will code thousands of cells against these rules, so
the in/out boundary must be UNAMBIGUOUS. You are given the field, the target category (name +
definition), the full list of the scheme's category names (so you can say where excluded values go),
and the distinct values in the data. Return:
- `includes`: a DETAILED description of the values that belong in THIS category — the specimen/organism
  types, common synonyms and abbreviations, and boundary cases. Be concrete; cite real values.
- `excludes`: the similar-looking values that do NOT belong here, naming which OTHER category each
  goes to instead (use the provided category names). This is essential for adjacent categories (e.g.
  superficial wound/tissue vs. normally-sterile body fluid vs. deep/invasive organ).
- `examples`: 4-8 example values taken VERBATIM from the provided value list that belong to THIS category.
"""


def _names_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "definition": {"type": "string"}},
                    "required": ["name", "definition"],
                },
            },
            "cross_field_notes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value_pattern": {"type": "string"},
                        "implies_field": {"type": "string"},
                        "implies_value": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["value_pattern", "implies_field", "rationale"],
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["categories"],
    }


def _detail_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "includes": {"type": "string"},
            "excludes": {"type": "string"},
            "examples": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["includes", "excludes", "examples"],
    }


def _seed_block(seed_categories: list[dict] | None) -> str:
    if not seed_categories:
        return ""
    lines = "\n".join(f"- {c['name']}: {c.get('definition', '')}" for c in seed_categories)
    return "\n\n=== SEED SCHEME (one example — reuse/merge/rename/replace as the data demands) ===\n" + lines


def propose_scheme(
    field: str,
    freqs: pd.Series,
    *,
    llm,
    seed_categories: list[dict] | None = None,
    max_values: int | None = 400,
    model: str | None = None,
) -> dict:
    """Stage 1 — propose category names + one-line definitions (+ cross-field notes) for ``field``."""
    value_block = render_for_prompt(freqs, max_values=max_values)
    user = (
        f"FIELD: {field}\n\n=== DISTINCT VALUES (count<TAB>value) ===\n{value_block}"
        f"{_seed_block(seed_categories)}"
    )
    return llm.complete_structured(
        system=_NAMES_SYSTEM,
        user=user,
        json_schema=_names_schema(),
        schema_name=NAMES_SCHEMA_NAME,
        schema_description=f"Proposed category names + definitions for the `{field}` field.",
        model=model,
    )


def detail_category(
    field: str,
    category: dict,
    all_names: list[str],
    freqs: pd.Series,
    *,
    llm,
    max_values: int | None = 400,
    model: str | None = None,
) -> dict:
    """Stage 2 — write detailed ``includes`` / ``excludes`` / ``examples`` for ONE category."""
    value_block = render_for_prompt(freqs, max_values=max_values)
    user = (
        f"FIELD: {field}\n\nTARGET CATEGORY: {category['name']}\n"
        f"DEFINITION: {category.get('definition', '')}\n\n"
        f"ALL CATEGORY NAMES (for 'excludes -> goes to X'): {', '.join(all_names)}\n\n"
        f"=== DISTINCT VALUES (count<TAB>value) ===\n{value_block}"
    )
    return llm.complete_structured(
        system=_DETAIL_SYSTEM,
        user=user,
        json_schema=_detail_schema(),
        schema_name=DETAIL_SCHEMA_NAME,
        schema_description=f"Detailed includes/excludes/examples for `{field}` category `{category['name']}`.",
        model=model,
    )


def induce_categories(
    field: str,
    freqs: pd.Series,
    *,
    llm,
    seed_categories: list[dict] | None = None,
    max_values: int | None = 400,
    model: str | None = None,
) -> dict:
    """Two-stage induction: propose names, then detail each category. Returns the full proposal.

    Parameters
    ----------
    field
        Field name (e.g. ``"host"`` / ``"isolation_source"``).
    freqs
        Distinct informative values + counts, from :func:`value_frequencies.value_frequencies`.
    llm
        An :class:`~engine.llm.LLMClient`.
    seed_categories
        Optional non-binding reference scheme (list of ``{"name", "definition"}``).
    max_values
        Cap on how many distinct values each call sees (the tail is summarised, not dropped).
    model
        Per-call model override.

    Returns
    -------
    dict
        ``{categories: [{name, definition, includes, excludes, examples}], cross_field_notes, notes}``.
    """
    scheme = propose_scheme(
        field, freqs, llm=llm, seed_categories=seed_categories, max_values=max_values, model=model
    )
    names = [c["name"] for c in scheme.get("categories", [])]
    detailed = []
    for cat in scheme.get("categories", []):
        d = detail_category(field, cat, names, freqs, llm=llm, max_values=max_values, model=model)
        detailed.append({
            "name": cat["name"],
            "definition": cat.get("definition", ""),
            "includes": d.get("includes", ""),
            "excludes": d.get("excludes", ""),
            "examples": d.get("examples", []),
        })
    return {
        "categories": detailed,
        "cross_field_notes": scheme.get("cross_field_notes", []),
        "notes": scheme.get("notes", ""),
    }


def write_proposal(field: str, proposal: dict, freqs: pd.Series, out_path: Path) -> Path:
    """Write an induced scheme to a reviewable proposal YAML (category + definition + examples + NA).

    The written shape matches the ``attributes.yaml`` ``categorisation.fields.<field>.categories``
    block, so an approved proposal can be pasted straight in.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "field": field,
        "n_distinct_values": int(len(freqs)),
        "n_samples": int(freqs.sum()),
        "categories": proposal.get("categories", []),
        "cross_column": proposal.get("cross_field_notes", []),
        "notes": proposal.get("notes", ""),
    }
    out_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
    return out_path
