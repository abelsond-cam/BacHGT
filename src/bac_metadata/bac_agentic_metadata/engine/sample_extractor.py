r"""Per-sample: per-sample field extraction from a paper's supplementary table (grounded, abstaining).

The residual ``collection_date`` / ``isolation_source`` (and a few ``country`` / ``host``) gaps are
**genuinely per-sample** — they vary row to row, so a whole-field value cannot fill them. Per-sample reads
them from the describing paper's open-access supplementary table (fetched + parsed by
:mod:`engine.supplementary`).

Design — mirror the finder ("the model picks an index; code does the rest"), so grounding and value
extraction never hallucinate:

* **deterministic** chooses the accession column (the column whose cells match the most of the study's
  ENA accessions) and does the row-by-row join + verbatim value copy;
* the **LLM** does only the small fuzzy step — map the four fields to column indices from a
  header+sample-rows preview, and say how many leading rows are header. One small structured call per
  study.

Values are copied **verbatim** (raw, faithful — the carriage-vs-invasive distinction is preserved by not
re-labelling; categorisation stays a downstream step). A table with no joinable accession column, or a
field the model maps to no column, simply yields no fill for that field — **abstain over guess**.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from .supplementary import ACCESSION_RE, SuppTable

#: The four core per-sample fields (the Klebsiella set). The spec-driven ``fields`` argument threaded
#: through this module DEFAULTS to these, so the Klebsiella path is byte-identical: an application (e.g.
#: M. abscessus) passing extra fields only ever APPENDS to the schema/prompt (see :func:`_system_prompt`).
FIELDS: tuple[str, ...] = ("country", "collection_date", "isolation_source", "host")

SCHEMA_NAME = "map_supplementary_columns"
VERIFY_SCHEMA_NAME = "verify_field_values"
RESCUE_SCHEMA_NAME = "rescue_unresolved_columns"
DECODE_SCHEMA_NAME = "decode_coded_column"

#: One-line description of what each field's values should look like (used by the value check). Extra,
#: non-core fields are additive — they are only consulted when an application maps them, so the four core
#: entries and the Klebsiella prompts are unchanged.
FIELD_VALUE_GUIDE = {
    "country": "real country / place names (NOT site codes, sample IDs, or abbreviations)",
    "collection_date": "years or calendar dates",
    "isolation_source": "clinical/environmental specimen or sample types (blood, urine, sputum, swab, water…)",
    "host": "host organisms (human/Homo sapiens, an animal, or a species name)",
    "cf_status": "cystic-fibrosis status of the host (CF, non-CF / bronchiectasis / another condition)",
    "smoking_status": "host smoking status (smoker, former smoker, never-smoker / non-smoker)",
}

#: The per-field alias bullet the column-mapping system prompt lists under "Common aliases". Held as a
#: map (not inline prose) so extra fields append cleanly; the four core bullets are byte-for-byte the
#: former hardcoded text, so the Klebsiella prompt is unchanged.
_FIELD_ALIAS_BULLETS: dict[str, str] = {
    "country": ("- country: 'location', 'geographic origin/location', 'region', 'country of origin', "
                "'origin', 'place', 'nation', 'geography' — or a column whose values are country/place "
                "names.\n"),
    "collection_date": ("- collection_date: 'date', 'year', 'collection year', 'sampling/isolation date', "
                        "'date collected', 'date of collection' — or a column of years/dates.\n"),
    "isolation_source": ("- isolation_source: 'source', 'specimen', 'sample type', 'specimen type', "
                         "'isolate source', 'material', 'body site', 'anatomical site' — the clinical/"
                         "environmental sample the isolate came from.\n"),
    "host": ("- host: 'host species', 'host organism', 'organism', 'source host', 'host type' — or a "
             "human/animal host designation.\n"),
    "cf_status": ("- cf_status: 'CF', 'CF status', 'cystic fibrosis', 'CF/non-CF', 'underlying disease', "
                  "'diagnosis', 'patient group', 'comorbidity', 'cohort' — whether the host has cystic "
                  "fibrosis vs another condition.\n"),
    "smoking_status": ("- smoking_status: 'smoking', 'smoker', 'smoking status', 'tobacco', 'pack-years', "
                       "'smoking history' — the host's smoking status.\n"),
}

#: Cardinal-number words so the prompt reads naturally ("four"/"six per-sample fields"); the count word
#: for the four core fields is "four", preserving the former literal text exactly.
_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
              9: "nine", 10: "ten"}

#: Minimum distinct ENA accessions a column must contain to be a usable join key.
MIN_ACCESSION_HITS = 3

#: Most accession-bearing tables to send to the LLM per study (cost cap; ranked by overlap).
MAX_TABLES_TO_MAP = 6

#: Minimum shared strain/patient IDs for a two-hop bridge between a manifest and a field table.
MIN_BRIDGE_OVERLAP = 5

#: Header keywords that hint a table carries the per-sample clinical fields (for two-hop detection).
FIELD_HEADER_RE = re.compile(
    r"countr|location|origin|geo|date|year|collect|isolat|source|specimen|sample.?type|"
    r"\bsite\b|body.?site|host|species|sex|age|patient",
    re.IGNORECASE,
)


def _norm_drug(name: str, panel: tuple[str, ...] | list[str]) -> str | None:
    """Match a reported antibiotic name to a canonical panel drug, or ``None`` if off-panel.

    Normalises punctuation/whitespace (``co-trimoxazole`` / ``trimethoprim/sulfamethoxazole`` →
    ``trimethoprim_sulfamethoxazole`` style) and matches against the spec's canonical drug list. Off-panel
    drugs return ``None`` — the caller records those verbatim in ``ast_other`` rather than dropping them.
    """
    key = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if not key:
        return None
    canon = {re.sub(r"[^a-z0-9]+", "_", d.lower()).strip("_"): d for d in panel}
    return canon.get(key)


def column_map_schema(fields: tuple[str, ...] = FIELDS, *, ast_drugs: tuple[str, ...] | list[str] | None = None) -> dict:
    """JSON schema for the field→column-index mapping the model returns (null = field absent).

    ``fields`` defaults to the four core fields, giving the exact former schema (the disk-cache key hashes
    schema *content*, order-independent, so Klebsiella keys are unchanged). Extra fields add
    ``<field>_column`` properties; when ``ast_drugs`` is given an ``ast_columns`` list captures the AST
    panel as (drug, mic_column, resistance_column) triples — a compact sub-schema that keeps the panel's
    ~40 drugs from ballooning into ~80 fixed properties.
    """
    col = {"type": ["integer", "null"]}
    properties: dict = {
        "header_rows": {"type": "integer", "description": "Number of leading rows that are header (often 1)."},
    }
    for f in fields:
        properties[f"{f}_column"] = col
    properties["confidence"] = {"enum": ["high", "medium", "low"]}
    properties["notes"] = {"type": "string"}
    if ast_drugs:
        properties["ast_columns"] = {
            "type": "array",
            "description": ("One entry per antibiotic whose per-isolate susceptibility this table reports "
                            "(empty list if none). drug = the antibiotic name as printed; mic_column = the "
                            "0-based column of its MIC value; resistance_column = the 0-based column of its "
                            "S/I/R call. Give whichever column(s) exist, null for the other."),
            "items": {
                "type": "object",
                "properties": {
                    "drug": {"type": "string"},
                    "mic_column": col,
                    "resistance_column": col,
                },
                "required": ["drug", "mic_column", "resistance_column"],
            },
        }
    required = ["header_rows", *[f"{f}_column" for f in fields], "confidence"]
    return {"type": "object", "properties": properties, "required": required}


@dataclass
class StudyExtraction:
    """Outcome of per-sample for one study: the per-sample fills plus provenance/diagnostics."""

    study_accession: str
    pmcid: str
    table: str | None
    fills: list[dict]  # rows shaped like engine.backfill._APPLIED_COLUMNS, method="per_sample"
    n_samples_mapped: int
    columns: dict
    confidence: str
    note: str


#: Identifier columns a supplementary table might key on. Beyond the deposited accessions, authors very
#: often key on a strain/isolate NAME that ENA carries in ``sample_alias`` / ``sample_title`` (e.g.
#: ``SPARK_775``, ``Brazil-2008a``, ``7SUS``). We map all of them so the key column is found by VALUE.
_ID_COLUMNS = ("secondary_sample_accession", "run_accession", "accession", "sample_alias", "sample_title")
_MIN_ID_LEN = 4  # drop 1–3 char ids (collision-prone) from the strain map


def _norm_id(v: object) -> str:
    """Normalised identifier key (lowercase, alphanumeric only) for VALUE-based, name-agnostic matching."""
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def build_accession_to_sample(study_df: pd.DataFrame, *, sample_col: str = "sample_accession",
                              id_columns: tuple[str, ...] = _ID_COLUMNS) -> dict[str, str]:
    """Map every per-sample identifier the authors might key a table on → canonical ``sample_accession``.

    Supplementary tables key on whatever id the authors used — a deposited accession (sample / secondary /
    run / assembly) OR a strain/isolate name carried in ENA ``sample_alias`` / ``sample_title`` / ``strain``
    / sequencing ``lane``. We map ALL of the given ``id_columns`` (:func:`_norm_id`-normalised) so the
    table's key column is found by **value** — which cells match a known id — never by column NAME
    (``Isolate`` / ``SPARK_ID`` / ``Strain`` / … are unbounded). First-write wins on a collision; ids
    shorter than :data:`_MIN_ID_LEN` are skipped.

    ``id_columns`` defaults to the four core Klebsiella identifier columns (:data:`_ID_COLUMNS`), so the
    Klebsiella path is unchanged. Other applications pass their full per-sample identifier set from the spec
    (``per_sample_completeness.sample_identifier_columns``) — see the critical note in that yaml: reviewing
    the input table for ALL per-sample identifiers is the first step when onboarding a new species.

    Parameters
    ----------
    study_df
        The study's rows from the raw ENA table.
    sample_col
        Canonical per-sample key column.
    id_columns
        Base columns whose values may key a supplementary table (in addition to ``sample_accession``,
        which is always mapped). Only those present in ``study_df`` are used.

    Returns
    -------
    dict[str, str]
        ``_norm_id(identifier)`` → ``sample_accession``.
    """
    extra = [c for c in id_columns if c in study_df.columns]
    out: dict[str, str] = {}
    for _, r in study_df.iterrows():
        sample = str(r.get(sample_col, "")).strip()
        if not sample:
            continue
        out.setdefault(_norm_id(sample), sample)
        for c in extra:
            k = _norm_id(r.get(c, ""))
            if len(k) >= _MIN_ID_LEN:
                out.setdefault(k, sample)
    return out


def pick_accession_column(table: SuppTable, id_keys: set[str]) -> tuple[int, int]:
    """Return ``(column_index, n_distinct_hits)`` for the column whose VALUES best match known sample ids.

    Name-agnostic: each cell is normalised (:func:`_norm_id`) and tested for membership in ``id_keys`` (the
    study's full identifier set — accessions + strain aliases from :func:`build_accession_to_sample`).
    Accessions embedded in longer text are also matched via :data:`ACCESSION_RE`. The column with the most
    distinct id matches is the key column, whatever its header is called.
    """
    best_col, best_hits = -1, 0
    for j in range(table.df.shape[1]):
        found: set[str] = set()
        for val in table.df.iloc[:, j].to_numpy().ravel():
            if not isinstance(val, str):
                continue
            k = _norm_id(val)
            if k in id_keys:                       # whole-cell id (strain name or accession)
                found.add(k)
            for m in ACCESSION_RE.findall(val):    # accession embedded in text
                if _norm_id(m) in id_keys:
                    found.add(_norm_id(m))
        if len(found) > best_hits:
            best_col, best_hits = j, len(found)
    return best_col, best_hits


def render_preview(df: pd.DataFrame, *, max_rows: int = 20, max_cell: int = 40) -> str:
    """Render a header+sample-rows preview with explicit ``[idx]`` column labels for the model."""
    lines = []
    head = " | ".join(f"[{j}]" for j in range(df.shape[1]))
    lines.append(head)
    for i in range(min(max_rows, len(df))):
        cells = []
        for j in range(df.shape[1]):
            v = df.iat[i, j]
            s = "" if (v is None or (isinstance(v, float))) else str(v)
            s = s.replace("\n", " ").strip()
            cells.append(s[:max_cell])
        lines.append(" | ".join(cells))
    if len(df) > max_rows:
        lines.append(f"... ({len(df)} rows total)")
    return "\n".join(lines)


def _system_prompt(fields: tuple[str, ...] = FIELDS, *, ast_drugs: tuple[str, ...] | list[str] | None = None) -> str:
    """System framing for the column-mapping task — match by MEANING, with explicit field aliases.

    With the four core ``fields`` and no ``ast_drugs`` this reproduces the former prompt byte-for-byte
    (so the Klebsiella disk-cache keys are unchanged). Extra fields append their alias bullet; an AST
    panel appends a trailing paragraph naming the canonical drugs — Klebsiella appends neither.
    """
    n_word = _NUM_WORDS.get(len(fields), str(len(fields)))
    aliases = "".join(_FIELD_ALIAS_BULLETS.get(f, f"- {f}: match by meaning.\n") for f in fields)
    prompt = (
        f"You map the columns of a scientific paper's supplementary metadata table to {n_word} per-sample "
        "fields. Tables rarely use our exact field names, so match by MEANING — use both the header "
        "wording AND the example values in the preview. Common aliases:\n"
        + aliases +
        "You are shown a preview with 0-indexed column labels [0], [1], .... Return the 0-based column "
        "index for each field, or null if that field genuinely has no column. Also return header_rows "
        "(how many leading rows are header, usually 1).\n"
        "Rules: pick the column holding the RAW per-sample value. For isolation_source choose the most "
        "SPECIFIC specimen column (e.g. the actual sample type like 'rectal swab', 'blood', 'sputum'), "
        "NOT a derived/grouped category column. Map a field only to a column whose VALUES are genuine "
        "values of that field (real place names for country, years/dates for collection_date, specimen "
        "types for isolation_source, host organisms for host) — not opaque site/sample codes or IDs even "
        "if a header sounds right. Do not invent columns; when unsure, prefer null. The accession/"
        "sample-ID column is handled separately — you do not need to map it."
    )
    if ast_drugs:
        drug_list = ", ".join(ast_drugs)
        prompt += (
            "\n\nANTIBIOTIC SUSCEPTIBILITY (AST): many isolate tables also report per-drug susceptibility. "
            "For EACH antibiotic column, add an ast_columns entry with the drug name as printed plus the "
            "0-based column index of its MIC value (mic_column) and/or its S/I/R call (resistance_column), "
            "null for whichever is absent. Record values VERBATIM — do not interpret MICs or apply "
            "breakpoints; that is a separate downstream job. Canonical drug names: "
            + drug_list + ". Use the closest canonical name; keep an off-panel drug's printed name as-is."
        )
    return prompt


def _user_prompt(study_accession: str, table: SuppTable, preview: str, fields: tuple[str, ...] = FIELDS,
                 *, ast_drugs: tuple[str, ...] | list[str] | None = None) -> str:
    """Per-study user prompt: the table identity + the preview grid."""
    tail = "; also list any antibiotic-susceptibility (AST) columns in ast_columns" if ast_drugs else ""
    return (
        f"STUDY: {study_accession}\nSUPPLEMENTARY FILE: {table.filename}"
        f"{' (sheet ' + table.sheet + ')' if table.sheet else ''}\n\n"
        f"TABLE PREVIEW (column labels are 0-based indices):\n{preview}\n\n"
        f"Map each of {' / '.join(fields)} to a column index or null{tail}."
    )


def _distinct_values(df: pd.DataFrame, col: int, header_rows: int, *, n: int = 12) -> list[str]:
    """Up to ``n`` distinct non-empty sample values from a column (for the value-plausibility check)."""
    seen: list[str] = []
    for i in range(header_rows, len(df)):
        v = _cell(df, i, col)
        if v and v not in seen:
            seen.append(v)
            if len(seen) >= n:
                break
    return seen


def verify_field_values(table: SuppTable, cols: dict[str, int | None], header_rows: int, llm,
                        *, model: str | None = None) -> tuple[dict[str, int | None], set[str]]:
    """Drop any field whose mapped column's VALUES are not plausible members of that field.

    A general sanity check (all fields, not a per-field hack): show the model a sample of each mapped
    column's actual values and ask whether they genuinely belong to the field. Called only when the
    mapping is not high-confidence. Returns the filtered column map + the set of rejected fields.
    """
    mapped = {f: c for f, c in cols.items() if c is not None}
    if not mapped:
        return cols, set()
    samples = {f: _distinct_values(table.df, c, header_rows) for f, c in mapped.items()}
    guide = "\n".join(f"- {f}: should be {FIELD_VALUE_GUIDE[f]}" for f in mapped)
    listing = "\n".join(f"{f} (mapped column values): {samples[f]}" for f in mapped)
    system = ("You verify whether table columns were mapped to the right metadata field by inspecting "
              "their actual values. For each field return true only if the listed values are genuine RAW "
              "values OF that field; return false for opaque codes, sample/strain IDs, or values that "
              "belong to a different field.\n" + guide)
    schema = {"type": "object", "properties": {f: {"type": "boolean"} for f in mapped},
              "required": list(mapped)}
    verdict = llm.complete_structured(
        system=system, user=f"Sampled values per mapped field:\n{listing}\n\nIs each field's column correct?",
        json_schema=schema, schema_name=VERIFY_SCHEMA_NAME,
        schema_description="Confirm each mapped column's values belong to its field.", model=model,
    )
    rejected = {f for f in mapped if verdict.get(f) is False}
    kept = {f: (None if f in rejected else c) for f, c in cols.items()}
    return kept, rejected


OVERWRITE_SCHEMA_NAME = "overwrite_fidelity"


def judge_overwrite_fidelity(field: str, ena_table_pairs, llm, *, model: str | None = None) -> tuple[bool, str]:
    """Whether a curator table's values SUBSTANTIALLY improve fidelity over the ENA values of ``field``.

    For a study ENA already reports complete (opened only because it carries a curator table), a table
    value that DIFFERS from ENA is applied only when it is a substantial improvement — ENA vague / coarse
    / wrong and the table specific and accurate (e.g. a vague clinical context → a real specimen such as
    blood, urine, sputum, a perirectal surveillance swab) — never a cosmetic or lateral change (a synonym,
    casing, or merely ADDING sub-locality like ``India`` → ``India: Kolkata``). One judgment per
    ``(study, field)``; otherwise the table defers to ENA (the blank-only default). David, 2026-07-11.

    Parameters
    ----------
    field
        The metadata field being judged (``isolation_source`` / ``host`` / ``country`` / ``collection_date``).
    ena_table_pairs
        Iterable of ``(ena_value, table_value)`` for the samples the table would overwrite.
    llm, model
        The structured-output client and optional model override.

    Returns
    -------
    tuple[bool, str]
        ``(improves, reason)`` — ``improves`` gates the overwrite; ``reason`` is a short rationale for audit.
    """
    pairs = sorted({(str(e).strip(), str(t).strip()) for e, t in ena_table_pairs if str(t).strip()})[:15]
    if not pairs:
        return False, "no differing values"
    listing = "\n".join(f"- ENA {e!r}  ->  table {t!r}" for e, t in pairs)
    system = (
        f"You decide whether a curator-provided per-isolate table should OVERWRITE the ENA value of the "
        f"`{field}` field, which ENA already populated. Say improves=true ONLY when the table value "
        "SUBSTANTIALLY improves fidelity — ENA is vague / coarse / uninformative or wrong and the table is "
        "specific and accurate (e.g. a vague clinical or surveillance context -> a real specimen such as "
        "blood, urine, sputum, or a perirectal surveillance swab). Say improves=false for cosmetic or "
        "lateral changes that add no real information: synonyms or casing (Homo sapiens vs Human), or "
        "merely adding sub-locality (India -> India: Kolkata), or any change that LOSES specificity. When "
        "in doubt, keep ENA (false)."
    )
    schema = {"type": "object",
              "properties": {"improves": {"type": "boolean"}, "reason": {"type": "string"}},
              "required": ["improves"]}
    out = llm.complete_structured(
        system=system,
        user=f"Field: {field}\nProposed overwrites (ENA -> table):\n{listing}\n\n"
             "Does the table SUBSTANTIALLY improve fidelity for this field?",
        json_schema=schema, schema_name=OVERWRITE_SCHEMA_NAME,
        schema_description="Whether the table value substantially improves fidelity over ENA.", model=model,
    )
    return bool(out.get("improves")), str(out.get("reason", ""))[:200]


def has_field_headers(table: SuppTable, *, scan_rows: int = 3) -> bool:
    """True if the table's first rows contain field-like header keywords (a two-hop candidate)."""
    for i in range(min(scan_rows, len(table.df))):
        for v in table.df.iloc[i].to_numpy().ravel():
            if isinstance(v, str) and FIELD_HEADER_RE.search(v):
                return True
    return False


def _cell(df: pd.DataFrame, row: int, col: int | None) -> str:
    """Return the trimmed string cell at ``(row, col)`` or '' (None/out-of-range/NaN-safe)."""
    if col is None or col < 0 or col >= df.shape[1]:
        return ""
    v = df.iat[row, col]
    if v is None or isinstance(v, float):
        return ""
    return str(v).strip()


def _col_values(df: pd.DataFrame, col: int, header_rows: int) -> set[str]:
    """Lower-cased non-empty cell values of one column below the header (a candidate join key)."""
    return {v.lower() for i in range(header_rows, len(df)) if (v := _cell(df, i, col))}


def find_bridge(manifest: pd.DataFrame, acc_col: int, m_header: int,
                field_df: pd.DataFrame, f_header: int) -> tuple[int | None, int | None, int]:
    """Find the shared strain/patient-ID column linking a manifest to a field table.

    Returns the (manifest_col, field_col, overlap) pair whose cell values overlap most — the bridge for
    the two-hop join (the accession column is excluded as a manifest key). ``(None, None, 0)`` if none.
    """
    m_sets = {j: _col_values(manifest, j, m_header) for j in range(manifest.shape[1]) if j != acc_col}
    f_sets = {k: _col_values(field_df, k, f_header) for k in range(field_df.shape[1])}
    best: tuple[int | None, int | None, int] = (None, None, 0)
    for j, ms in m_sets.items():
        if len(ms) < MIN_BRIDGE_OVERLAP:
            continue
        for k, fs in f_sets.items():
            ov = len(ms & fs)
            if ov > best[2]:
                best = (j, k, ov)
    return best


def _two_hop_extract(study_accession: str, pmcid: str, manifest: SuppTable, acc_col: int, m_header: int,
                     field_tables: list[SuppTable], acc_to_sample: dict[str, str], llm,
                     *, model: str | None, fields: tuple[str, ...] = FIELDS) -> StudyExtraction | None:
    """Chain manifest (accession→ID) to a strain-keyed field table (ID→fields). ``None`` if no bridge."""
    # hop 1: build strain/patient-ID → sample_accession from the manifest.
    best: StudyExtraction | None = None
    for ft in field_tables[:MAX_TABLES_TO_MAP]:
        mapping = llm.complete_structured(
            system=_system_prompt(fields), user=_user_prompt(study_accession, ft, render_preview(ft.df), fields),
            json_schema=column_map_schema(fields), schema_name=SCHEMA_NAME,
            schema_description="Map supplementary-table columns to per-sample metadata fields.", model=model,
        )
        cols = {f: mapping.get(f"{f}_column") for f in fields}
        if not any(c is not None for c in cols.values()):
            continue
        f_header = max(0, int(mapping.get("header_rows", 1)))
        if mapping.get("confidence", "low") != "high":  # general value-plausibility check
            cols, _rej = verify_field_values(ft, cols, f_header, llm, model=model)
            if not any(c is not None for c in cols.values()):
                continue
        m_key, f_key, ov = find_bridge(manifest.df, acc_col, m_header, ft.df, f_header)
        if m_key is None or ov < MIN_BRIDGE_OVERLAP:
            continue
        id_to_sample: dict[str, str] = {}
        for i in range(m_header, len(manifest.df)):
            raw = _cell(manifest.df, i, acc_col)
            bid = _cell(manifest.df, i, m_key).lower()
            sample = acc_to_sample.get(_norm_id(raw))
            if sample is None:
                am = ACCESSION_RE.search(raw)
                sample = acc_to_sample.get(_norm_id(am.group(0))) if am else None
            if sample and bid:
                id_to_sample.setdefault(bid, sample)
        # hop 2: walk the field table, bridge each row's ID to a sample, copy field cells verbatim.
        fills: list[dict] = []
        mapped: set[str] = set()
        for i in range(f_header, len(ft.df)):
            sample = id_to_sample.get(_cell(ft.df, i, f_key).lower())
            if sample is None:
                continue
            mapped.add(sample)
            for f, col in cols.items():
                val = _cell(ft.df, i, col)
                if val:
                    fills.append({
                        "study_accession": study_accession, "sample_accession": sample, "field": f,
                        "ena_value": "", "applied_value": val, "method": "per_sample_two_hop",
                        "evidence": f"{ft.filename}+{manifest.filename} via {ov} shared IDs",
                    })
        if fills and (best is None or len(fills) > len(best.fills)):
            best = StudyExtraction(study_accession, pmcid, f"{ft.filename}+{manifest.filename}", fills,
                                   len(mapped), cols, mapping.get("confidence", "low"),
                                   f"two-hop: {len(mapped)} samples via {ov} shared IDs, {len(fills)} cell-fills")
    return best


def load_category_vocabs(categorisation_dir: str | Path, fields: tuple[str, ...] | list[str]) -> dict[str, str]:
    """Compact per-field controlled vocabulary from the approved category yamls (for the no-paper rescue).

    Reads ``<field>_categories_approved.yaml`` (as produced by the categorise sub-engine) and summarises
    each as ``name (e.g. ex1, ex2); …`` so the Tier-2 rescue can recognise a renamed/coded column by
    whether its values are consistent with our vocabulary. Fields without an approved yaml (e.g.
    ``country`` / ``collection_date``) are simply omitted — the rescue falls back to :data:`FIELD_VALUE_GUIDE`.

    Parameters
    ----------
    categorisation_dir
        Directory holding ``<field>_categories_approved.yaml`` files.
    fields
        Fields to load vocabularies for.

    Returns
    -------
    dict[str, str]
        ``field -> compact vocabulary summary`` (only fields with a readable approved yaml).
    """
    out: dict[str, str] = {}
    d = Path(categorisation_dir)
    for f in fields:
        p = d / f"{f}_categories_approved.yaml"
        if not p.exists():
            continue
        try:
            spec = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError:
            continue
        parts = []
        for c in spec.get("categories", []) or []:
            name = str(c.get("name", "")).strip()
            if not name:
                continue
            ex = [str(x) for x in (c.get("examples") or [])][:4]
            parts.append(f"{name} (e.g. {', '.join(ex)})" if ex else name)
        if parts:
            out[f] = "; ".join(parts)
    return out


def _columns_digest(table: SuppTable, header_rows: int, *, exclude_col: int, max_vals: int = 10) -> str:
    """Header + distinct example values for every column except the join key — the rescue's evidence grid."""
    lines = []
    for j in range(table.df.shape[1]):
        if j == exclude_col:
            continue
        header = " ".join(_cell(table.df, r, j) for r in range(max(1, header_rows))).strip()
        vals = _distinct_values(table.df, j, header_rows, n=max_vals)
        lines.append(f"[{j}] header='{header[:60]}' values={vals}")
    return "\n".join(lines)


def _rescue_schema(fields: list[str]) -> dict:
    """Schema for the Tier-2 rescue: per unresolved field a column + needs_paper flag + a code→value list."""
    item = {"type": "object", "properties": {"code": {"type": "string"}, "value": {"type": "string"}},
            "required": ["code", "value"]}
    per = {"type": "object", "properties": {
               "column": {"type": ["integer", "null"]},
               "needs_paper": {"type": "boolean"},
               "codebook": {"type": "array", "items": item}},
           "required": ["column", "needs_paper", "codebook"]}
    return {"type": "object", "properties": dict.fromkeys(fields, per), "required": list(fields)}


def rescue_unresolved(study_accession: str, table: SuppTable, unresolved: list[str], header_rows: int, *,
                      acc_col: int, category_vocab: dict[str, str] | None, llm,
                      model: str | None = None) -> dict[str, dict]:
    """Tier-2 (no paper): re-map + light-decode fields the first pass missed, grounded in our vocabulary.

    For each unresolved field, inspect ALL columns (headers + example values) plus the field's controlled
    vocabulary and return: the column that actually holds it (or ``None``); a ``codebook`` of code→raw-value
    pairs decodable WITHOUT the paper (``clinical→human``, ``env→environmental``, or empty when values are
    already plain → copy verbatim); and ``needs_paper`` when the column is clearly the field but its values
    are OPAQUE codes (``PS``/``UR``/``ST``) only the paper's legend can decode (→ Tier 3).

    Returns ``{field: {"column": int|None, "needs_paper": bool, "codebook": {code: value}}}``.
    """
    vocab = category_vocab or {}
    guide = "\n".join(
        f"- {f}: controlled vocabulary — {vocab[f]}" if f in vocab
        else f"- {f}: should be {FIELD_VALUE_GUIDE.get(f, f)}" for f in unresolved)
    digest = _columns_digest(table, header_rows, exclude_col=acc_col)
    system = (
        "You RESCUE per-sample metadata fields that a first-pass column mapping missed. For EACH field, use "
        "the columns' headers + example values and the field's controlled vocabulary to decide:\n"
        "- column: the 0-based index of the column that actually holds this field, or null if none does.\n"
        "- codebook: code→raw-value pairs you can decode from the VOCABULARY or obvious meaning WITHOUT the "
        "paper (e.g. 'clinical'->'human', 'env'->'environmental'; leave empty when the values are already "
        "plain field values, so the caller copies them verbatim). Keep decoded values RAW and SPECIFIC (the "
        "exact specimen/host term, never a grouped category) — faithfulness is required.\n"
        "- needs_paper: true ONLY when the column is clearly this field but its values are OPAQUE codes/"
        "abbreviations (e.g. 'PS','UR','ST') you cannot decode without the paper's legend.\n"
        "Never map a field to the sample/accession id column. Prefer column=null over a wrong guess.\n"
        + guide)
    user = (f"STUDY: {study_accession}\nCOLUMNS (index, header, example values):\n{digest}\n\n"
            f"Rescue these fields: {', '.join(unresolved)}.")
    out = llm.complete_structured(system=system, user=user, json_schema=_rescue_schema(list(unresolved)),
                                  schema_name=RESCUE_SCHEMA_NAME,
                                  schema_description="Re-map + light-decode unresolved per-sample fields.",
                                  model=model)
    res: dict[str, dict] = {}
    for f in unresolved:
        r = out.get(f) or {}
        col = r.get("column")
        cb = {str(e.get("code", "")).strip(): str(e.get("value", "")).strip()
              for e in (r.get("codebook") or []) if str(e.get("code", "")).strip() and str(e.get("value", "")).strip()}
        res[f] = {"column": col if isinstance(col, int) else None,
                  "needs_paper": bool(r.get("needs_paper")), "codebook": cb}
    return res


def _decode_schema() -> dict:
    """Schema for the Tier-3 paper decode: a code→value list (value nullable = 'could not decode')."""
    item = {"type": "object",
            "properties": {"code": {"type": "string"}, "value": {"type": ["string", "null"]}},
            "required": ["code", "value"]}
    return {"type": "object", "properties": {"codebook": {"type": "array", "items": item}}, "required": ["codebook"]}


def decode_codes_from_paper(study_accession: str, field: str, header: str, codes: list[str], paper_text: str, llm,
                            *, model: str | None = None, max_chars: int = 60000) -> dict[str, str]:
    """Tier-3 (paper): decode a strong-alias column's OPAQUE codes to raw values using the paper's legend.

    Read only as a last resort (the first-pass mapping and the no-paper vocab rescue could not decode the
    values). Returns ``{code: raw_value}`` for codes the paper explains; a code left unexplained is dropped
    (abstain over guess). Decoded values are the SPECIFIC raw specimen/host term (never a grouped category),
    so the carriage-vs-invasive distinction survives and categorisation stays downstream.
    """
    excerpt = paper_text[:max_chars]
    system = (
        f"A supplementary-table column (header '{header}') holds the per-sample {field}, but its values are "
        "abbreviations/codes. Using the paper text, decode EACH listed code to the RAW, SPECIFIC "
        f"{FIELD_VALUE_GUIDE.get(field, field)} it denotes (the exact term, e.g. 'sputum', 'urine', 'rectal "
        "swab' — never a grouped category). Return value=null for any code the paper does not clearly "
        "define; do NOT guess.")
    user = (f"STUDY: {study_accession}\nCODES TO DECODE: {list(codes)}\n\n"
            f"PAPER TEXT (may be truncated):\n{excerpt}")
    out = llm.complete_structured(system=system, user=user, json_schema=_decode_schema(),
                                  schema_name=DECODE_SCHEMA_NAME,
                                  schema_description=f"Decode {field} codes using the paper legend.", model=model)
    cb: dict[str, str] = {}
    for e in out.get("codebook") or []:
        code = str(e.get("code", "")).strip()
        val = e.get("value")
        if code and val is not None and str(val).strip():
            cb[code] = str(val).strip()
    return cb


def _decode_lookup(codebook: dict[str, str], raw: str) -> str:
    """Case/space-insensitive codebook lookup for a coded cell ('' when the code has no decode)."""
    if not raw:
        return ""
    key = raw.strip()
    if key in codebook:
        return codebook[key]
    return {k.strip().lower(): v for k, v in codebook.items()}.get(key.lower(), "")


def extract_study(
    study_accession: str,
    pmcid: str,
    tables: list[SuppTable],
    accession_set: set[str],
    acc_to_sample: dict[str, str],
    llm,
    *,
    model: str | None = None,
    fields: tuple[str, ...] = FIELDS,
    ast_drugs: tuple[str, ...] | list[str] | None = None,
    category_vocab: dict[str, str] | None = None,
    get_fulltext: Callable[[], str | None] | None = None,
) -> StudyExtraction:
    """Run per-sample for one study: pick the joinable table, map columns (LLM), extract per-sample rows.

    The mapping is a 3-tier cascade that reads the paper only as a last resort (to save usage): (1) the
    first-pass column mapping (:func:`_system_prompt`) + value-plausibility check; (2) for any field left
    UNRESOLVED (unmapped or value-check-rejected), a vocabulary-grounded rescue (:func:`rescue_unresolved`,
    NO paper) that re-maps renamed columns and light-decodes values consistent with our controlled
    vocabulary (``location``→country, ``clinical``→human); (3) only for a strong-alias column whose values
    are opaque codes, a minimal paper decode (:func:`decode_codes_from_paper`). A study whose first pass
    resolves every field skips tiers 2–3 entirely.

    Parameters
    ----------
    study_accession, pmcid
        Study + its OA article PMCID.
    tables
        Parsed supplementary tables (:func:`engine.supplementary.parse_tables`).
    accession_set
        Upper-cased ENA accessions for the study (the grounding set).
    acc_to_sample
        Map any ENA accession → canonical ``sample_accession`` (:func:`build_accession_to_sample`).
    llm
        An :class:`engine.llm.LLMClient`.
    model
        Optional per-call model override.
    fields
        Per-sample fields to map (default the four core fields → byte-identical Klebsiella behaviour).
    ast_drugs
        Canonical antibiotic panel; when given, the extractor also maps AST columns and emits per-drug
        ``ast_<drug>_mic`` / ``ast_<drug>_resistance`` fills (off-panel drugs go to ``ast_other``).
    category_vocab
        ``field -> controlled-vocabulary summary`` (from :func:`load_category_vocabs`) grounding the Tier-2
        rescue. ``None`` disables vocab grounding (rescue then leans on :data:`FIELD_VALUE_GUIDE`).
    get_fulltext
        Zero-arg callable returning the study's paper text (or ``None``) — invoked lazily ONLY when a
        Tier-3 decode is needed. ``None`` disables Tier 3 (opaque-coded columns then stay unresolved).

    Returns
    -------
    StudyExtraction
        The per-sample fills (``method="per_sample"``) and diagnostics; empty ``fills`` = abstained.
    """
    # 1) rank the accession-bearing tables by overlap (a manifest can outrank the metadata table,
    #    so we map several, not just the top one).
    joinable = []
    for t in tables:
        col, hits = pick_accession_column(t, accession_set)
        if hits >= MIN_ACCESSION_HITS:
            joinable.append((hits, t, col))
    joinable.sort(key=lambda x: -x[0])

    join_tables = [j[1] for j in joinable]
    two_hop_tables = [t for t in tables if has_field_headers(t) and t not in join_tables]
    two_hop_names = [t.filename for t in two_hop_tables]
    if not joinable:
        # No accession-bearing table at all → nothing to ground on (two-hop needs a manifest for hop 1).
        note = "no joinable table" + (f"; field-bearing tables present but unanchored: {two_hop_names}" if two_hop_names else "")
        return StudyExtraction(study_accession, pmcid, None, [], 0, {}, "none", note)

    # 2) LLM maps fields→columns on each accession-bearing table (capped); keep the richest mapping.
    best_map: dict | None = None
    best_table: SuppTable | None = None
    best_acc_col = -1
    best_nfields = -1
    for _hits, t, col in joinable[:MAX_TABLES_TO_MAP]:
        mapping = llm.complete_structured(
            system=_system_prompt(fields, ast_drugs=ast_drugs),
            user=_user_prompt(study_accession, t, render_preview(t.df), fields, ast_drugs=ast_drugs),
            json_schema=column_map_schema(fields, ast_drugs=ast_drugs),
            schema_name=SCHEMA_NAME,
            schema_description="Map supplementary-table columns to per-sample metadata fields.",
            model=model,
        )
        nfields = sum(mapping.get(f"{f}_column") is not None for f in fields)
        if nfields > best_nfields:
            best_map, best_table, best_acc_col, best_nfields = mapping, t, col, nfields
        if nfields == len(fields):
            break
    mapping, table, acc_col = best_map, best_table, best_acc_col
    cols = {f: mapping.get(f"{f}_column") for f in fields}
    header_rows = max(0, int(mapping.get("header_rows", 1)))
    # AST triples on the chosen table (empty unless the spec enabled a panel). A table carrying only AST
    # (no core fields) must NOT fall through to the manifest branch, so it is part of the has-content test.
    ast_map = (mapping.get("ast_columns") or []) if ast_drugs else []
    if best_nfields == 0 and not ast_map:
        # The joinable tables are accession manifests with no field columns. If a strain-keyed field
        # table exists, chain through it (two-hop) using `table` as the manifest.
        if two_hop_tables:
            th = _two_hop_extract(study_accession, pmcid, table, acc_col, header_rows,
                                  two_hop_tables, acc_to_sample, llm, model=model, fields=fields)
            if th is not None:
                return th
        note = ("joinable tables are accession-manifest only (no field columns)"
                + (f"; no bridge to field tables {two_hop_names}" if two_hop_names else ""))
        return StudyExtraction(study_accession, pmcid, table.filename, [], 0, cols,
                               mapping.get("confidence", "low"), note)

    # 2b) value-plausibility check (general, all fields) when the mapping is not high-confidence.
    confidence = mapping.get("confidence", "low")
    orig_cols = dict(cols)            # mapping BEFORE the value check — tells 'unmapped' apart from 'rejected'
    rejected: set[str] = set()
    if confidence != "high":
        cols, rejected = verify_field_values(table, cols, header_rows, llm, model=model)

    # 2c) rescue cascade (ADDITIVE; fires only for UNRESOLVED fields — never mapped by pass 1, OR dropped by
    #     the value check). Tier 2 re-maps + light-decodes from our controlled vocabulary (NO paper); Tier 3
    #     reads a minimal paper excerpt ONLY for a strong-alias column whose values are opaque codes. A study
    #     whose first pass resolved every field skips this entirely (behaviour/cache unchanged).
    decoded: dict[str, tuple[int, dict]] = {}   # field -> (column, codebook), applied during the join
    rescued: list[str] = []
    unresolved = {f for f in fields if orig_cols.get(f) is None} | rejected
    if unresolved and (category_vocab or get_fulltext is not None):
        rescue = rescue_unresolved(study_accession, table, sorted(unresolved), header_rows,
                                   acc_col=acc_col, category_vocab=category_vocab, llm=llm, model=model)
        paper_text: str | None = None
        for f in sorted(unresolved):
            r = rescue.get(f) or {}
            col = r.get("column")
            if not isinstance(col, int) or col == acc_col or col < 0 or col >= table.df.shape[1]:
                continue
            cb = r.get("codebook") or {}
            if r.get("needs_paper") and get_fulltext is not None:   # Tier 3 — decode opaque codes from paper
                if paper_text is None:
                    paper_text = get_fulltext() or ""
                if paper_text:
                    header = " ".join(_cell(table.df, rr, col) for rr in range(max(1, header_rows))).strip()
                    codes = _distinct_values(table.df, col, header_rows, n=40)
                    cb = decode_codes_from_paper(study_accession, f, header, codes, paper_text, llm, model=model)
            if cb:                          # decode path (Tier-2 vocab decode or Tier-3 paper decode)
                decoded[f] = (col, cb)
                rescued.append(f"{f}={'paper' if r.get('needs_paper') else 'vocab'}")
            elif not r.get("needs_paper"):  # verbatim rescue: values already plain, copy as-is
                cols[f] = col
                rescued.append(f"{f}=verbatim")

    if not any(c is not None for c in cols.values()) and not decoded and not ast_map:
        note = (f"no per-sample fields resolved; value-check rejected {sorted(rejected)}"
                if rejected else "no per-sample field columns found")
        return StudyExtraction(study_accession, pmcid, table.filename, [], 0, cols, confidence, note)

    # 3) deterministic row-by-row join + verbatim/decoded extraction (core/extra fields, then the AST panel).
    fills: list[dict] = []
    mapped_samples: set[str] = set()
    for i in range(header_rows, len(table.df)):
        raw_acc = _cell(table.df, i, acc_col)
        sample = acc_to_sample.get(_norm_id(raw_acc))  # value-based: whole-cell id (strain name or accession)
        key = raw_acc.strip()
        if sample is None:                              # fall back to an accession embedded in the cell text
            m = ACCESSION_RE.search(raw_acc)
            if m:
                sample, key = acc_to_sample.get(_norm_id(m.group(0))), m.group(0)
        if sample is None:
            continue
        mapped_samples.add(sample)
        for f, col in cols.items():                    # values are copied verbatim; validity + overwrite
            val = _cell(table.df, i, col)              # betterness are enforced downstream by stages.py's
            if val:                                    # overwrite gate (engine.value_validity), where the
                fills.append({                         # true ENA value is known.
                    "study_accession": study_accession, "sample_accession": sample, "field": f,
                    "ena_value": "", "applied_value": val, "method": "per_sample",
                    "evidence": f"{table.filename}:{key}",
                })
        for f, (col, cb) in decoded.items():           # decoded/rescued fields: map the cell's code -> value
            val = _decode_lookup(cb, _cell(table.df, i, col))
            if val:
                fills.append({
                    "study_accession": study_accession, "sample_accession": sample, "field": f,
                    "ena_value": "", "applied_value": val, "method": "per_sample",
                    "evidence": f"{table.filename}:{key} (rescued {_cell(table.df, i, col)!r})",
                })
        fills.extend(_ast_fills_for_row(study_accession, sample, table, i, ast_map, ast_drugs, key))
    n_ast = sum(1 for x in fills if x["field"].startswith("ast_"))
    note = f"mapped {len(mapped_samples)} samples, {len(fills)} cell-fills"
    if n_ast:
        note += f" ({n_ast} AST)"
    if rescued:
        note += f"; rescued {rescued}"
    if rejected:
        note += f"; value-check rejected {sorted(rejected)}"
    return StudyExtraction(study_accession, pmcid, table.filename, fills, len(mapped_samples), cols,
                           confidence, note)


def _ast_fills_for_row(study_accession: str, sample: str, table: SuppTable, row: int,
                       ast_map: list[dict], ast_drugs: tuple[str, ...] | list[str] | None, key: str) -> list[dict]:
    """Emit verbatim per-drug AST fills for one joined row (``[]`` when no panel / no values).

    Each ``ast_columns`` entry names a drug plus its MIC and/or S-I-R column. Values are copied AS-IS
    (no breakpoint interpretation). Panel drugs land in ``ast_<drug>_mic`` / ``ast_<drug>_resistance``;
    an off-panel drug's value is preserved verbatim in ``ast_other`` as ``drug=value``.
    """
    if not ast_map or not ast_drugs:
        return []
    out: list[dict] = []
    for entry in ast_map:
        drug_raw = str(entry.get("drug", "")).strip()
        if not drug_raw:
            continue
        mic = _cell(table.df, row, entry.get("mic_column"))
        res = _cell(table.df, row, entry.get("resistance_column"))
        if not mic and not res:
            continue
        canon = _norm_drug(drug_raw, ast_drugs)

        def _add(field: str, value: str) -> None:
            out.append({
                "study_accession": study_accession, "sample_accession": sample, "field": field,
                "ena_value": "", "applied_value": value, "method": "per_sample",
                "evidence": f"{table.filename}:{key}",
            })

        if canon:
            if mic:
                _add(f"ast_{canon}_mic", mic)
            if res:
                _add(f"ast_{canon}_resistance", res)
        else:  # off-panel drug — keep the reading verbatim so nothing is silently dropped
            _add("ast_other", f"{drug_raw}={mic or res}")
    return out


def confidence_tally(extractions: list[StudyExtraction]) -> dict[str, int]:
    """Count extraction confidences across studies (small reporting helper)."""
    return dict(Counter(e.confidence for e in extractions))
