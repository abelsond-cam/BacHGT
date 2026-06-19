r"""Method-b: per-sample field extraction from a paper's supplementary table (grounded, abstaining).

The residual ``collection_date`` / ``isolation_source`` (and a few ``country`` / ``host``) gaps are
**genuinely per-sample** — they vary row to row, so a whole-field value cannot fill them. Method-b reads
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
from dataclasses import dataclass

import pandas as pd

from .supplementary import ACCESSION_RE, SuppTable

#: The four per-sample fields method-b extracts (same set as ``engine.backfill``).
FIELDS: tuple[str, ...] = ("country", "collection_date", "isolation_source", "host")

SCHEMA_NAME = "map_supplementary_columns"
VERIFY_SCHEMA_NAME = "verify_field_values"

#: One-line description of what each field's values should look like (used by the value check).
FIELD_VALUE_GUIDE = {
    "country": "real country / place names (NOT site codes, sample IDs, or abbreviations)",
    "collection_date": "years or calendar dates",
    "isolation_source": "clinical/environmental specimen or sample types (blood, urine, sputum, swab, water…)",
    "host": "host organisms (human/Homo sapiens, an animal, or a species name)",
}

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


def column_map_schema() -> dict:
    """JSON schema for the field→column-index mapping the model returns (null = field absent)."""
    col = {"type": ["integer", "null"]}
    return {
        "type": "object",
        "properties": {
            "header_rows": {"type": "integer", "description": "Number of leading rows that are header (often 1)."},
            "country_column": col,
            "collection_date_column": col,
            "isolation_source_column": col,
            "host_column": col,
            "confidence": {"enum": ["high", "medium", "low"]},
            "notes": {"type": "string"},
        },
        "required": ["header_rows", "country_column", "collection_date_column",
                     "isolation_source_column", "host_column", "confidence"],
    }


@dataclass
class StudyExtraction:
    """Outcome of method-b for one study: the per-sample fills plus provenance/diagnostics."""

    study_accession: str
    pmcid: str
    table: str | None
    fills: list[dict]  # rows shaped like engine.backfill._APPLIED_COLUMNS, method="per_sample"
    n_samples_mapped: int
    columns: dict
    confidence: str
    note: str


def build_accession_to_sample(study_df: pd.DataFrame, *, sample_col: str = "sample_accession") -> dict[str, str]:
    """Map every ENA accession kind (sample/secondary/run/assembly) → the canonical ``sample_accession``.

    Supplementary tables key on whichever accession the authors deposited (often the run or the
    secondary-sample accession), so we resolve any of them back to the sample.

    Parameters
    ----------
    study_df
        The study's rows from the raw ENA table.
    sample_col
        Canonical per-sample key column.

    Returns
    -------
    dict[str, str]
        Upper-cased accession → ``sample_accession``.
    """
    other = [c for c in ("secondary_sample_accession", "run_accession", "accession") if c in study_df.columns]
    out: dict[str, str] = {}
    for _, r in study_df.iterrows():
        sample = str(r.get(sample_col, "")).strip()
        if not sample:
            continue
        out[sample.upper()] = sample
        for c in other:
            v = str(r.get(c, "")).strip()
            if v and v.lower() not in ("nan", ""):
                out[v.upper()] = sample
    return out


def pick_accession_column(table: SuppTable, accession_set: set[str]) -> tuple[int, int]:
    """Return ``(column_index, n_distinct_hits)`` for the column best matching the study's accessions."""
    best_col, best_hits = -1, 0
    for j in range(table.df.shape[1]):
        found: set[str] = set()
        for val in table.df.iloc[:, j].to_numpy().ravel():
            if isinstance(val, str):
                for m in ACCESSION_RE.findall(val):
                    if m.upper() in accession_set:
                        found.add(m.upper())
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


def _system_prompt() -> str:
    """System framing for the column-mapping task — match by MEANING, with explicit field aliases."""
    return (
        "You map the columns of a scientific paper's supplementary metadata table to four per-sample "
        "fields. Tables rarely use our exact field names, so match by MEANING — use both the header "
        "wording AND the example values in the preview. Common aliases:\n"
        "- country: 'location', 'geographic origin/location', 'region', 'country of origin', 'origin', "
        "'place', 'nation', 'geography' — or a column whose values are country/place names.\n"
        "- collection_date: 'date', 'year', 'collection year', 'sampling/isolation date', 'date "
        "collected', 'date of collection' — or a column of years/dates.\n"
        "- isolation_source: 'source', 'specimen', 'sample type', 'specimen type', 'isolate source', "
        "'material', 'body site', 'anatomical site' — the clinical/environmental sample the isolate came "
        "from.\n"
        "- host: 'host species', 'host organism', 'organism', 'source host', 'host type' — or a "
        "human/animal host designation.\n"
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


def _user_prompt(study_accession: str, table: SuppTable, preview: str) -> str:
    """Per-study user prompt: the table identity + the preview grid."""
    return (
        f"STUDY: {study_accession}\nSUPPLEMENTARY FILE: {table.filename}"
        f"{' (sheet ' + table.sheet + ')' if table.sheet else ''}\n\n"
        f"TABLE PREVIEW (column labels are 0-based indices):\n{preview}\n\n"
        "Map each of country / collection_date / isolation_source / host to a column index or null."
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
                     *, model: str | None) -> StudyExtraction | None:
    """Chain manifest (accession→ID) to a strain-keyed field table (ID→fields). ``None`` if no bridge."""
    # hop 1: build strain/patient-ID → sample_accession from the manifest.
    best: StudyExtraction | None = None
    for ft in field_tables[:MAX_TABLES_TO_MAP]:
        mapping = llm.complete_structured(
            system=_system_prompt(), user=_user_prompt(study_accession, ft, render_preview(ft.df)),
            json_schema=column_map_schema(), schema_name=SCHEMA_NAME,
            schema_description="Map supplementary-table columns to per-sample metadata fields.", model=model,
        )
        cols = {f: mapping.get(f"{f}_column") for f in FIELDS}
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
            am = ACCESSION_RE.search(_cell(manifest.df, i, acc_col))
            bid = _cell(manifest.df, i, m_key).lower()
            if am and bid:
                sample = acc_to_sample.get(am.group(0).upper())
                if sample:
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


def extract_study(
    study_accession: str,
    pmcid: str,
    tables: list[SuppTable],
    accession_set: set[str],
    acc_to_sample: dict[str, str],
    llm,
    *,
    model: str | None = None,
) -> StudyExtraction:
    """Run method-b for one study: pick the joinable table, map columns (LLM), extract per-sample rows.

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
            system=_system_prompt(),
            user=_user_prompt(study_accession, t, render_preview(t.df)),
            json_schema=column_map_schema(),
            schema_name=SCHEMA_NAME,
            schema_description="Map supplementary-table columns to per-sample metadata fields.",
            model=model,
        )
        nfields = sum(mapping.get(f"{f}_column") is not None for f in FIELDS)
        if nfields > best_nfields:
            best_map, best_table, best_acc_col, best_nfields = mapping, t, col, nfields
        if nfields == len(FIELDS):
            break
    mapping, table, acc_col = best_map, best_table, best_acc_col
    cols = {f: mapping.get(f"{f}_column") for f in FIELDS}
    header_rows = max(0, int(mapping.get("header_rows", 1)))
    if best_nfields == 0:
        # The joinable tables are accession manifests with no field columns. If a strain-keyed field
        # table exists, chain through it (two-hop) using `table` as the manifest.
        if two_hop_tables:
            th = _two_hop_extract(study_accession, pmcid, table, acc_col, header_rows,
                                  two_hop_tables, acc_to_sample, llm, model=model)
            if th is not None:
                return th
        note = ("joinable tables are accession-manifest only (no field columns)"
                + (f"; no bridge to field tables {two_hop_names}" if two_hop_names else ""))
        return StudyExtraction(study_accession, pmcid, table.filename, [], 0, cols,
                               mapping.get("confidence", "low"), note)

    # 2b) value-plausibility check (general, all fields) when the mapping is not high-confidence.
    confidence = mapping.get("confidence", "low")
    rejected: set[str] = set()
    if confidence != "high":
        cols, rejected = verify_field_values(table, cols, header_rows, llm, model=model)
        if not any(c is not None for c in cols.values()):
            return StudyExtraction(study_accession, pmcid, table.filename, [], 0, cols, confidence,
                                   f"all mapped fields failed the value check: {sorted(rejected)}")

    # 3) deterministic row-by-row join + verbatim extraction.
    fills: list[dict] = []
    mapped_samples: set[str] = set()
    for i in range(header_rows, len(table.df)):
        raw_acc = _cell(table.df, i, acc_col)
        m = ACCESSION_RE.search(raw_acc)
        if not m:
            continue
        sample = acc_to_sample.get(m.group(0).upper())
        if sample is None:
            continue
        mapped_samples.add(sample)
        for f, col in cols.items():
            val = _cell(table.df, i, col)
            if val:
                fills.append({
                    "study_accession": study_accession, "sample_accession": sample, "field": f,
                    "ena_value": "", "applied_value": val, "method": "per_sample",
                    "evidence": f"{table.filename}:{m.group(0)}",
                })
    note = f"mapped {len(mapped_samples)} samples, {len(fills)} cell-fills"
    if rejected:
        note += f"; value-check rejected {sorted(rejected)}"
    return StudyExtraction(study_accession, pmcid, table.filename, fills, len(mapped_samples), cols,
                           confidence, note)


def confidence_tally(extractions: list[StudyExtraction]) -> dict[str, int]:
    """Count extraction confidences across studies (small reporting helper)."""
    return dict(Counter(e.confidence for e in extractions))
