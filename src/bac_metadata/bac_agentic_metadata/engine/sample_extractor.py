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

#: Minimum distinct ENA accessions a column must contain to be a usable join key.
MIN_ACCESSION_HITS = 3

#: Most accession-bearing tables to send to the LLM per study (cost cap; ranked by overlap).
MAX_TABLES_TO_MAP = 6

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
    """System framing for the column-mapping task."""
    return (
        "You map the columns of a scientific paper's supplementary metadata table to four per-sample "
        "fields: country, collection_date, isolation_source, host. You are shown a preview with "
        "0-indexed column labels [0], [1], .... Return the 0-based column index for each field, or null "
        "if that field is not present as its own column. Also return header_rows (how many leading rows "
        "are header, usually 1).\n"
        "Rules: pick the column holding the RAW per-sample value. For isolation_source choose the most "
        "SPECIFIC specimen column (e.g. the actual sample type like 'rectal swab', 'blood', 'sputum'), "
        "NOT a derived/grouped category column. Do not invent columns; if unsure for a field, return "
        "null for it. The accession/sample-ID column is handled separately — you do not need to map it."
    )


def _user_prompt(study_accession: str, table: SuppTable, preview: str) -> str:
    """Per-study user prompt: the table identity + the preview grid."""
    return (
        f"STUDY: {study_accession}\nSUPPLEMENTARY FILE: {table.filename}"
        f"{' (sheet ' + table.sheet + ')' if table.sheet else ''}\n\n"
        f"TABLE PREVIEW (column labels are 0-based indices):\n{preview}\n\n"
        "Map each of country / collection_date / isolation_source / host to a column index or null."
    )


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

    two_hop = [t.filename for t in tables if has_field_headers(t) and t not in [j[1] for j in joinable]]
    if not joinable:
        note = "no joinable table" + (f"; field-bearing tables need two-hop join: {two_hop}" if two_hop else "")
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
        note = ("joinable tables are accession-manifest only (no field columns)"
                + (f"; fields may be in a strain-keyed table → two-hop: {two_hop}" if two_hop else ""))
        return StudyExtraction(study_accession, pmcid, table.filename, [], 0, cols,
                               mapping.get("confidence", "low"), note)

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
    return StudyExtraction(study_accession, pmcid, table.filename, fills, len(mapped_samples), cols,
                           mapping.get("confidence", "low"),
                           f"mapped {len(mapped_samples)} samples, {len(fills)} cell-fills")


def confidence_tally(extractions: list[StudyExtraction]) -> dict[str, int]:
    """Count extraction confidences across studies (small reporting helper)."""
    return dict(Counter(e.confidence for e in extractions))
