"""Resolve a manually-downloaded local supplementary file to ``SuppTable``s (per-sample analogue of local_papers).

Per-sample backfill (:mod:`engine.sample_extractor`) fills ``isolation_source`` / ``host`` /
``collection_date`` per sample from a paper's per-isolate supplementary table, which
:mod:`engine.supplementary` fetches from Europe PMC **open-access only**. When that table is paywalled,
not mirrored in EPMC, or the paper has no PMCID, the curator downloads it by hand and the application
names it ``<study_accession>.<ext>`` in a canonical directory
(``data/sample_lv_attributes/manual_download_supp/``). This loader parses those files with the **same
parser** the open-access path uses (``engine.supplementary._parse_member``), so the extractor consumes
them identically — closing the per-sample gap the paywall opened, and re-checked on every rerun.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from .supplementary import SuppTable, _parse_member

#: Extensions the manual-supplementary loader will try (the same table-bearing types the OA path parses).
SUPP_EXTS = (".xlsx", ".xls", ".csv", ".tsv", ".txt", ".docx", ".pdf")

#: A single directory, or an ordered list of them (earlier = higher precedence). Two live locations:
#: the **committed** ``applications/<app>/manual_supp_tables/`` (version-controlled, can't be silently
#: lost — the failure that dropped PRJEB28400's table) and the **legacy** gitignored
#: ``data/sample_lv_attributes/manual_download_supp/``.
SuppDirs = str | Path | Iterable[str | Path] | None


def find_local_supp_files(accession: str, dirs: SuppDirs) -> list[Path]:
    """Existing ``<accession>.<ext>`` file(s) for a study, taking the **first** directory that has any.

    Directory precedence means a committed table shadows a legacy one for the same accession (rather than
    both being parsed), so the version-controlled copy is authoritative.

    Parameters
    ----------
    accession
        Study accession; files are named ``<accession>.<ext>`` (``ext`` in :data:`SUPP_EXTS`).
    dirs
        A single directory or an ordered iterable of them (earlier = higher precedence).

    Returns
    -------
    list[pathlib.Path]
        The matching files from the first directory that contains any (empty list if none / no dirs).
    """
    if not dirs:
        return []
    seq: list = [dirs] if isinstance(dirs, (str, Path)) else [d for d in dirs if d]
    for d in seq:
        base = Path(d)
        found = [base / f"{accession}{ext}" for ext in SUPP_EXTS if (base / f"{accession}{ext}").exists()]
        if found:
            return found
    return []


def resolve_local_supp_tables(accession: str, local_dir: SuppDirs) -> list[SuppTable] | None:
    """Return ``SuppTable``s parsed from a local ``<accession>.<ext>``, or ``None`` if no file exists.

    Parameters
    ----------
    accession
        Study accession; the file must be named ``<accession>.<ext>`` (``ext`` in :data:`SUPP_EXTS`).
    local_dir
        One directory, or an ordered list of them (see :data:`SuppDirs` — committed folder first, legacy
        second). ``None`` / missing directories → ``None``.

    Returns
    -------
    list[SuppTable] | None
        Parsed tables when a file is present; ``None`` when there is no file for the accession (caller
        keeps its open-access behaviour). A file that **exists but parses to zero tables** emits a loud
        ``[WARN]`` and returns ``[]`` (never silently dropped), so a present-but-unreadable manual
        supplementary stays visible to the per-sample outcome record and the run-health report.
    """
    found = find_local_supp_files(accession, local_dir)
    if not found:
        return None
    tables: list[SuppTable] = []
    for path in found:
        tables.extend(_parse_member(accession, path.name, path.read_bytes()))
    if not tables:
        print(f"  [WARN] manual supplementary {[p.name for p in found]} present for {accession} but parsed "
              "to 0 tables — per-sample grading WITHOUT it; check the file format.", file=sys.stderr)
    return tables
