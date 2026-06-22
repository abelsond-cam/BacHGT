"""Resolve a manually-downloaded local PDF to text — the fallback for paywalled papers.

Many describing papers are paywalled, so :func:`engine.fulltext.fetch_fulltext` returns them
flagged ``needs_manual_download``. The curator downloads those PDFs by hand and the application's
``link_local_papers.py`` renames each to ``<study_accession>.pdf`` in a canonical directory
(``data/find_papers/manual_download/``). This loader extracts their text so grading can use them
exactly like an openly fetched full text — closing the completeness gap the paywall opened.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .fulltext import _MIN_PDF_CHARS, FullText, _pdf_to_text


def resolve_local_fulltext(accession: str, local_dir: str | Path | None) -> FullText | None:
    """Return :class:`FullText` from a local ``<accession>.pdf``, or ``None`` if absent/unreadable.

    Parameters
    ----------
    accession
        Study accession; the PDF must be named ``<accession>.pdf`` in ``local_dir``.
    local_dir
        Directory of manually-downloaded PDFs (``data/find_papers/manual_download/``). ``None`` or
        a missing directory yields ``None`` (the loader is an optional fallback).

    Returns
    -------
    FullText | None
        ``FullText(source="local_pdf", is_full_text=True)`` when a readable PDF with substantial
        text is found; ``None`` when there is no PDF for the accession or it yielded no usable text
        (scanned/garbled), so the caller keeps whatever it already had.
    """
    if not local_dir:
        return None
    pdf = Path(local_dir) / f"{accession}.pdf"
    if not pdf.exists():
        return None
    text = _pdf_to_text(pdf.read_bytes())
    if len(text) < _MIN_PDF_CHARS:
        # The PDF is *present* (a curator put it there deliberately) but yielded no usable text — almost
        # always a transient pdfplumber failure, not a genuinely empty paper. Never drop it silently:
        # shout so the run is visibly grading WITHOUT a paper we have, and a refire is known to be needed.
        print(f"  [WARN] manual PDF {pdf.name} is present but extraction yielded {len(text)} chars "
              f"(< {_MIN_PDF_CHARS}) — grading WITHOUT it; re-run grading to retry (likely transient).",
              file=sys.stderr)
        return None
    return FullText(text, "local_pdf", True, False, pdf.name, "", {"local_path": str(pdf)})
