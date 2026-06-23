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
from pathlib import Path

from .supplementary import SuppTable, _parse_member

#: Extensions the manual-supplementary loader will try (the same table-bearing types the OA path parses).
SUPP_EXTS = (".xlsx", ".xls", ".csv", ".tsv", ".docx", ".pdf")


def resolve_local_supp_tables(accession: str, local_dir: str | Path | None) -> list[SuppTable] | None:
    """Return ``SuppTable``s parsed from a local ``<accession>.<ext>``, or ``None`` if no file exists.

    Parameters
    ----------
    accession
        Study accession; the file must be named ``<accession>.<ext>`` (``ext`` in :data:`SUPP_EXTS`).
    local_dir
        Directory of manually-downloaded supplementary files
        (``data/sample_lv_attributes/manual_download_supp/``). ``None`` or a missing directory → ``None``.

    Returns
    -------
    list[SuppTable] | None
        Parsed tables when a file is present; ``None`` when there is no file for the accession (caller
        keeps its open-access behaviour). A file that **exists but parses to zero tables** emits a loud
        ``[WARN]`` and returns ``[]`` (never silently dropped), so a present-but-unreadable manual
        supplementary stays visible to the per-sample outcome record and the run-health report.
    """
    if not local_dir:
        return None
    d = Path(local_dir)
    found = [d / f"{accession}{ext}" for ext in SUPP_EXTS if (d / f"{accession}{ext}").exists()]
    if not found:
        return None
    tables: list[SuppTable] = []
    for path in found:
        tables.extend(_parse_member(accession, path.name, path.read_bytes()))
    if not tables:
        print(f"  [WARN] manual supplementary {[p.name for p in found]} present for {accession} but parsed "
              "to 0 tables — per-sample grading WITHOUT it; check the file format.", file=sys.stderr)
    return tables
