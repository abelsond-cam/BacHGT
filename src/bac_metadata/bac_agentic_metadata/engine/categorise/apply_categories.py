"""Apply an approved category scheme — map each DISTINCT value to ``{parsed, category}``, join to rows.

Phase C. Operating on distinct values (not rows) keeps this cheap, cacheable and deterministic: the
same distinct value is mapped once (via the ``temperature=0`` disk cache) and joined back to every row
that holds it. Writes ``<field>_parsed`` (a cleaned canonical form of the value) and
``<field>_category`` (one of the approved category names, or ``NA``). Nothing is silently dropped —
values the model fits poorly are flagged (``poor_fit``) as candidates for a new category / re-induction.
"""

from __future__ import annotations

import pandas as pd

from .value_frequencies import value_frequencies

SCHEMA_NAME = "map_values_to_categories"


def _map_schema(category_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "parsed": {"type": "string"},
                        "category": {"type": "string", "enum": category_names},
                        "poor_fit": {"type": "boolean"},
                        "na_reason": {"type": "string"},
                    },
                    "required": ["value", "parsed", "category"],
                },
            }
        },
        "required": ["mappings"],
    }


_SYSTEM = """\
You assign metadata values to a fixed category scheme for a bacterial-genomics dataset. You are given
the field name, the approved categories (each with name + definition + what it INCLUDES + what it
EXCLUDES), and a batch of distinct raw values. Code each value strictly by the includes/excludes
rules. For EACH value return:
- `parsed`: a cleaned, canonical form of the value (fix casing/abbreviations/typos; keep the meaning),
- `category`: EXACTLY ONE of the approved category names. Use `NA` for values that carry no usable
  information for this field — codes, IDs, lab/culture artefacts, uninterpretable strings, and any
  value that belongs to a DIFFERENT field (e.g. a place name in an isolation-source column).
- `poor_fit`: true if the value is informative but does not fit any category well (a candidate for a
  new category) — still pick the closest category, but flag it.
- `na_reason`: REQUIRED when category is `NA` — one short phrase: `uninformative`, `laboratory`, or
  `belongs_to:<field>` (e.g. `belongs_to:country`) for a value that is really another field's data.
Return one mapping per input value, echoing `value` verbatim.
"""


def _scheme_block(categories: list[dict]) -> str:
    lines = []
    for c in categories:
        lines.append(f"- {c['name']}: {c.get('definition', '')}")
        if c.get("includes"):
            lines.append(f"    includes: {c['includes']}")
        if c.get("excludes"):
            lines.append(f"    excludes: {c['excludes']}")
    return "\n".join(lines)


def map_values(
    field: str,
    values: list[str],
    categories: list[dict],
    *,
    llm,
    batch_size: int = 60,
    model: str | None = None,
) -> dict[str, dict]:
    """Map each distinct ``value`` to ``{parsed, category, poor_fit}`` via batched, cached LLM calls.

    Values are sorted then chunked into ``batch_size`` batches so each call's payload is stable → the
    ``temperature=0`` disk cache makes reruns byte-identical.
    """
    names = [c["name"] for c in categories]
    if "NA" not in names:
        names = names + ["NA"]
    schema = _map_schema(names)
    scheme = _scheme_block(categories)
    ordered = sorted(values)
    out: dict[str, dict] = {}
    for i in range(0, len(ordered), batch_size):
        batch = ordered[i : i + batch_size]
        user = (
            f"FIELD: {field}\n\n=== APPROVED CATEGORIES ===\n{scheme}\n\n"
            f"=== VALUES TO MAP ({len(batch)}) ===\n" + "\n".join(batch)
        )
        res = llm.complete_structured(
            system=_SYSTEM,
            user=user,
            json_schema=schema,
            schema_name=SCHEMA_NAME,
            schema_description=f"Map distinct `{field}` values to the approved category scheme.",
            model=model,
        )
        for m in res.get("mappings", []):
            v = m.get("value")
            if v is not None:
                out[v] = {
                    "parsed": m.get("parsed", v),
                    "category": m.get("category", "NA"),
                    "poor_fit": bool(m.get("poor_fit", False)),
                    "na_reason": m.get("na_reason", ""),
                }
    return out


def apply_categories(
    base: pd.DataFrame,
    field: str,
    categories: list[dict],
    *,
    llm,
    null_tokens: tuple[str, ...] = (),
    null_patterns: tuple[str, ...] = (),
    batch_size: int = 60,
    model: str | None = None,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Add ``<field>_parsed`` + ``<field>_category`` to ``base`` and return an assessment.

    Parameters
    ----------
    base
        Per-sample table containing ``field``.
    field, categories
        The field and its approved category scheme (list of ``{name, definition, ...}``).
    llm
        An :class:`~engine.llm.LLMClient`.
    null_tokens, null_patterns
        Field-specific nulls (from the spec) dropped in addition to ``PLACEHOLDER_NULLS`` — whole-cell
        tokens and case-insensitive regex patterns (e.g. laboratory variants).
    batch_size, model
        Passed to :func:`map_values`.

    Returns
    -------
    tuple[pandas.DataFrame, dict, pandas.DataFrame]
        (1) the base with ``<field>_parsed`` + ``<field>_category`` added; (2) an assessment dict
        ``{n_distinct, n_samples, by_category, n_uncategorised, poor_fit_values}``; (3) the full
        **reassignment audit** — one row per distinct value: ``value, count, parsed, category,
        poor_fit, na_reason`` (sorted by count) — so every reassignment is inspectable.
    """
    freqs = value_frequencies(base[field], null_tokens=null_tokens, null_patterns=null_patterns)
    lookup = map_values(field, list(freqs.index), categories, llm=llm, batch_size=batch_size, model=model)

    out = base.copy()
    parsed_col, cat_col = f"{field}_parsed", f"{field}_category"

    def _lookup(cell: str, which: str):
        m = lookup.get(cell)
        return m[which] if m else pd.NA

    raw = out[field]
    out[parsed_col] = raw.map(lambda c: _lookup(c, "parsed"))
    out[cat_col] = raw.map(lambda c: _lookup(c, "category"))

    # Full reassignment audit — every distinct informative value and where it landed.
    audit = pd.DataFrame(
        [
            {
                "value": v,
                "count": int(freqs[v]),
                "parsed": lookup.get(v, {}).get("parsed", ""),
                "category": lookup.get(v, {}).get("category", ""),
                "poor_fit": lookup.get(v, {}).get("poor_fit", False),
                "na_reason": lookup.get(v, {}).get("na_reason", ""),
            }
            for v in freqs.index
        ]
    ).sort_values("count", ascending=False, ignore_index=True)

    by_cat = out[cat_col].value_counts(dropna=True).to_dict()
    poor = sorted(v for v, m in lookup.items() if m.get("poor_fit"))
    assessment = {
        "field": field,
        "n_distinct": int(len(freqs)),
        "n_samples": int(freqs.sum()),
        "by_category": {str(k): int(v) for k, v in by_cat.items()},
        "n_uncategorised": int(by_cat.get("NA", 0)),
        "poor_fit_values": poor,
    }
    return out, assessment, audit
