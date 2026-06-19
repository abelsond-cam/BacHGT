"""Fetch + parse a paper's Europe PMC supplementary tables (open-access only) for method-b backfill.

Method-b completes the genuinely per-sample fields (``collection_date`` / ``isolation_source`` and the
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
import zipfile
from dataclasses import dataclass

import pandas as pd
import requests

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
TABLE_SUFFIXES = (".xlsx", ".xls", ".csv", ".tsv")

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


def fetch_supplementary_zip(pmcid: str, *, cache_dir) -> bytes | None:
    """Download (and cache) the Europe PMC supplementary-files ZIP for an OA article.

    Parameters
    ----------
    pmcid
        Europe PMC PMCID (with or without the ``PMC`` prefix).
    cache_dir
        Directory for the cached ``<PMCID>.zip`` (and a ``<PMCID>.none`` marker when no OA ZIP exists).

    Returns
    -------
    bytes | None
        The ZIP bytes, or ``None`` when the article has no open-access supplementary ZIP.
    """
    pmcid = normalise_pmcid(pmcid)
    zip_path = cache_dir / f"{pmcid}.zip"
    none_path = cache_dir / f"{pmcid}.none"
    if zip_path.exists():
        return zip_path.read_bytes()
    if none_path.exists():
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(f"{EUROPEPMC}/{pmcid}/supplementaryFiles", timeout=120)
    except requests.RequestException:
        return None
    if resp.status_code == 200 and resp.content[:2] == b"PK":
        zip_path.write_bytes(resp.content)
        return resp.content
    none_path.write_text(str(resp.status_code))
    return None


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
        low = name.lower()
        if not low.endswith(TABLE_SUFFIXES):
            continue
        try:
            data = zf.read(name)
        except (KeyError, zipfile.BadZipFile):
            continue
        if low.endswith((".csv", ".tsv")):
            sep = "\t" if low.endswith(".tsv") else ","
            try:
                df = pd.read_csv(io.BytesIO(data), sep=sep, dtype=str, header=None, on_bad_lines="skip")
                out.append(SuppTable(pmcid, name, None, df))
            except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                continue
        else:
            engine = "xlrd" if low.endswith(".xls") else "openpyxl"
            try:
                sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None, engine=engine)
            except Exception:  # noqa: BLE001 - supplementary spreadsheets are arbitrarily malformed
                continue
            for sheet_name, df in sheets.items():
                out.append(SuppTable(pmcid, name, str(sheet_name), df))
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
