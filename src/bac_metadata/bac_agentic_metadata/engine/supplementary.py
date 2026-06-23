"""Fetch + parse a paper's Europe PMC supplementary tables (open-access only) for per-sample backfill.

Per-sample completes the genuinely per-sample fields (``collection_date`` / ``isolation_source`` and the
residual ``country`` / ``host``) by reading the describing paper's **supplementary tables**. This module
is the deterministic data layer:

1. :func:`fetch_supplementary_zip` — download the Europe PMC ``supplementaryFiles`` ZIP for a PMCID
   (open-access only; cached on disk). Paywalled / no-OA papers return ``None`` → the study is a
   ``needs_manual`` residual.
2. :func:`parse_tables` — read each spreadsheet/CSV member (``.xlsx/.xls/.csv/.tsv``; every sheet of a
   workbook) into a raw, header-less :class:`SuppTable` (``dtype=str``, ``header=None``) so even messy
   multi-row-header tables are captured cell-for-cell.
3. :func:`accession_overlap` — the **join gate**: how many of a study's ENA accessions
   (``sample``/``run``/``secondary``/``biosample``) appear as cells in a table. A table that joins is one
   the per-sample extraction agent can ground against; a table with no joinable key is unusable.

No LLM here. Column→field and row→sample mapping (and the carriage-vs-invasive faithfulness rule for
``isolation_source``) belong to the extraction agent that consumes these tables.
"""

from __future__ import annotations

import io
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
#: Native-spreadsheet members parsed directly into DataFrames.
TABLE_SUFFIXES = (".xlsx", ".xls", ".csv", ".tsv")
#: Document members whose embedded tables we extract (DOCX via XML, PDF via pdfplumber) — no new deps.
DOC_SUFFIXES = (".docx", ".pdf")
#: WordprocessingML namespace for DOCX table parsing.
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: ENA/INSDC accession shapes that let a supplementary-table row join to an ENA sample. Sample
#: (SAM[END]…), secondary sample (ERS/SRS/DRS), run (ERR/SRR/DRR), study (PRJ…/ERP/SRP/DRP),
#: assembly (GCA/GCF). Matched case-insensitively against every table cell.
ACCESSION_RE = re.compile(
    r"\b(SAM[END][A-Z]?\d+|[ESD]RS\d+|[ESD]RR\d+|PRJ[EDN][A-Z]\d+|[ESD]RP\d+|GC[AF]_\d+)\b",
    re.IGNORECASE,
)


@dataclass
class SuppTable:
    """One parsed supplementary table (a single sheet of a workbook, or a CSV/TSV file)."""

    pmcid: str
    filename: str
    sheet: str | None
    df: pd.DataFrame


def normalise_pmcid(pmcid: str) -> str:
    """Return ``pmcid`` with the ``PMC`` prefix (Europe PMC wants e.g. ``PMC1234567``)."""
    p = str(pmcid).strip()
    return p if p.upper().startswith("PMC") else f"PMC{p}"


def fetch_supplementary_zip(pmcid: str, *, cache_dir, attempts: int = 4) -> bytes | None:
    """Download (and cache) the Europe PMC supplementary-files ZIP for an OA article.

    Parameters
    ----------
    pmcid
        Europe PMC PMCID (with or without the ``PMC`` prefix).
    cache_dir
        Directory for the cached ``<PMCID>.zip`` (and a ``<PMCID>.none`` marker when no OA ZIP exists).
    attempts
        Max attempts before giving up on transient failures (5xx / 429 / connection errors), which are
        retried with backoff and never cached — only a definitive 404 / 200-non-ZIP is cached ``.none``.

    Returns
    -------
    bytes | None
        The ZIP bytes, or ``None`` when the article has no open-access supplementary ZIP (or a
        transient failure persisted, in which case nothing is cached and the next run retries).
    """
    pmcid = normalise_pmcid(pmcid)
    zip_path = cache_dir / f"{pmcid}.zip"
    none_path = cache_dir / f"{pmcid}.none"
    if zip_path.exists():
        return zip_path.read_bytes()
    if none_path.exists():
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Cache a ``.none`` marker ONLY on a definitive negative (404, or a 200 that is not a ZIP).
    # Transient failures (connection errors, 5xx, 429) are RETRIED and left uncached — a single 503
    # cached as permanent ``.none`` would silently drop this study's per-sample table from every later
    # run (exactly what poisoned the test fold), so transients must never become a permanent miss.
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(f"{EUROPEPMC}/{pmcid}/supplementaryFiles", timeout=120)
        except requests.RequestException as exc:
            last = type(exc).__name__
        else:
            if resp.status_code == 200 and resp.content[:2] == b"PK":
                zip_path.write_bytes(resp.content)
                return resp.content
            if resp.status_code in (404, 200):  # definitive: no OA supplementary ZIP for this article
                none_path.write_text(str(resp.status_code))
                return None
            last = str(resp.status_code)  # 5xx / 429 — transient
        if attempt < attempts:
            time.sleep(min(2 * attempt, 8))
    print(f"  [warn] EPMC supplementary fetch for {pmcid} failed transiently ({last}) after {attempts} "
          "attempts; not caching — will retry next run.", file=sys.stderr)
    return None


def _docx_tables(data: bytes) -> list[pd.DataFrame]:
    """Extract every table embedded in a ``.docx`` as a header-less DataFrame (stdlib only).

    A ``.docx`` is a ZIP whose ``word/document.xml`` holds ``<w:tbl>`` elements; each ``<w:tr>`` is a
    row and ``<w:tc>`` a cell (text in the descendant ``<w:t>`` runs). No external dependency.
    """
    import xml.etree.ElementTree as ET

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as dz:
            xml = dz.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[pd.DataFrame] = []
    for tbl in root.iter(f"{_W_NS}tbl"):
        rows = []
        for tr in tbl.findall(f"{_W_NS}tr"):
            cells = ["".join(t.text or "" for t in tc.iter(f"{_W_NS}t")).strip()
                     for tc in tr.findall(f"{_W_NS}tc")]
            if cells:
                rows.append(cells)
        if rows:
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            out.append(pd.DataFrame(rows, dtype=str))
    return out


def _pdf_tables(data: bytes) -> list[pd.DataFrame]:
    """Extract tables from PDF bytes with ``pdfplumber`` (already a dependency); [] on failure."""
    import pdfplumber

    out: list[pd.DataFrame] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                for tbl in page.extract_tables() or []:
                    rows = [["" if c is None else str(c).replace("\n", " ").strip() for c in row]
                            for row in tbl if row]
                    if rows:
                        width = max(len(r) for r in rows)
                        rows = [r + [""] * (width - len(r)) for r in rows]
                        out.append(pd.DataFrame(rows, dtype=str))
    except Exception:  # noqa: BLE001 - any PDF parse failure → no tables from this file
        return out
    return out


def parse_tables(pmcid: str, *, cache_dir) -> list[SuppTable]:
    """Parse every spreadsheet/CSV member of the article's supplementary ZIP into :class:`SuppTable`.

    Tables are read raw (``header=None``, ``dtype=str``) so multi-row headers and merged cells survive
    for downstream inspection. Unreadable members are skipped.

    Parameters
    ----------
    pmcid
        Europe PMC PMCID.
    cache_dir
        Cache directory (see :func:`fetch_supplementary_zip`).

    Returns
    -------
    list[SuppTable]
        One entry per sheet/CSV; empty if there is no OA ZIP or no table members.
    """
    raw = fetch_supplementary_zip(pmcid, cache_dir=cache_dir)
    if raw is None:
        return []
    pmcid = normalise_pmcid(pmcid)
    out: list[SuppTable] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return []
    for name in zf.namelist():
        if not name.lower().endswith(TABLE_SUFFIXES + DOC_SUFFIXES):
            continue
        try:
            data = zf.read(name)
        except (KeyError, zipfile.BadZipFile):
            continue
        out.extend(_parse_member(pmcid, name, data))
    return out


def _parse_member(tag: str, name: str, data: bytes) -> list[SuppTable]:
    """Parse one table-bearing file's bytes (csv/tsv/xlsx/xls/docx/pdf) into :class:`SuppTable`s."""
    low = name.lower()
    out: list[SuppTable] = []
    if low.endswith((".csv", ".tsv")):
        sep = "\t" if low.endswith(".tsv") else ","
        try:
            df = pd.read_csv(io.BytesIO(data), sep=sep, dtype=str, header=None, on_bad_lines="skip")
            out.append(SuppTable(tag, name, None, df))
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
            return out
    elif low.endswith((".xlsx", ".xls")):
        engine = "xlrd" if low.endswith(".xls") else "openpyxl"
        try:
            sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None, engine=engine)
        except Exception:  # noqa: BLE001 - supplementary spreadsheets are arbitrarily malformed
            return out
        out.extend(SuppTable(tag, name, str(sheet_name), df) for sheet_name, df in sheets.items())
    elif low.endswith((".docx", ".pdf")):
        extractor = _docx_tables if low.endswith(".docx") else _pdf_tables
        out.extend(SuppTable(tag, name, f"table{idx + 1}", df) for idx, df in enumerate(extractor(data)))
    return out


def parse_local_tables(dir_path, *, exclude_substr: str = "ready_to_merge") -> list[SuppTable]:
    """Parse the table files in a LOCAL folder (diagnostic only — e.g. a curator's ENA_projects folder).

    Reuses the same per-format parsers as :func:`parse_tables`. Files whose name contains
    ``exclude_substr`` are skipped (so a curator's ``*ready_to_merge*`` OUTPUT is never mistaken for an
    input source table). This is a **diagnostic harness**, not a production source: such files do not
    exist for unseen data.
    """
    d = Path(dir_path)
    if not d.is_dir():
        return []
    out: list[SuppTable] = []
    for f in sorted(d.iterdir()):
        low = f.name.lower()
        if not low.endswith(TABLE_SUFFIXES + DOC_SUFFIXES) or (exclude_substr and exclude_substr in low):
            continue
        try:
            data = f.read_bytes()
        except OSError:
            continue
        out.extend(_parse_member(f.name, f.name, data))
    return out


def accession_overlap(table: SuppTable, accession_set: set[str]) -> set[str]:
    """Return the study's ENA accessions that appear as cells anywhere in ``table``.

    The intersection is the join key: rows of a table with a non-empty overlap can be mapped to ENA
    samples; a table with an empty overlap carries no accession the extractor can ground against.

    Parameters
    ----------
    table
        A parsed :class:`SuppTable`.
    accession_set
        Upper-cased ENA accessions for the study (sample/secondary/run/study/assembly).

    Returns
    -------
    set[str]
        The subset of ``accession_set`` found in the table.
    """
    found: set[str] = set()
    for val in table.df.to_numpy().ravel():
        if not isinstance(val, str):
            continue
        for m in ACCESSION_RE.findall(val):
            up = m.upper()
            if up in accession_set:
                found.add(up)
    return found
