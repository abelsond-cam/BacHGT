r"""Link manually-downloaded paper PDFs to their study accession.

Paywalled describing papers (listed in ``find_papers/missing_papers_report.tsv`` with
``has_paper=True``) are downloaded by hand into a publisher-named PDF in a downloads folder. This
script matches each PDF to its accession — primarily by the **DOI text-mined from the PDF's first
pages**, then by normalised filename/URL tokens, then by an explicit override map — and copies it to
``data/find_papers/manual_download/<accession>.pdf`` so
:func:`engine.local_papers.resolve_local_fulltext` can feed it to grading.

A single PDF may serve several accessions (same paper describes >1 project, e.g. ``cix270`` →
PRJEB6891 + PRJNA351909) — it is copied to each. Idempotent; re-run safely.

Run once::

    uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/link_local_papers.py \\
        --downloads "~/Downloads/Agentic Metadata Downloads"
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.fulltext import _DOI_RE

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
WORKLIST = DATA_DIR / "find_papers" / "missing_papers_report.tsv"
MANUAL_DIR = DATA_DIR / "find_papers" / "manual_download"

#: Publisher filename stem (lower) → accession(s), for PDFs whose worklist row has no DOI/URL that
#: matches the file (e.g. a JAC DOI not recorded in the sheet). Seeded from the verified audit.
OVERRIDES: dict[str, list[str]] = {
    "dkaa431": ["PRJEB22890"],
}


def _norm(s: str) -> str:
    """Lowercase, alphanumeric-only — a publisher-agnostic key for DOIs/PIIs/filenames."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _accession_keys(row: pd.Series) -> set[str]:
    """Normalised identifier keys for an accession (DOI full + suffix, URL last segment, pmid)."""
    keys: set[str] = set()
    doi = str(row.get("doi", "")).strip()
    if doi:
        keys.add(_norm(doi))
        keys.add(_norm(doi.split("/")[-1]))
    url = str(row.get("best_url", "")).strip().rstrip("/")
    if url:
        keys.add(_norm(url.split("/")[-1]))
    for col in ("pmid", "pmcid"):
        v = str(row.get(col, "")).strip()
        if v and v.lower() != "nan":
            keys.add(_norm(v))
    return {k for k in keys if len(k) >= 5}  # drop tiny/ambiguous keys


def _pdf_dois(path: Path, *, pages: int = 1) -> set[str]:
    """Text-mine DOIs from the first ``pages`` of a PDF (normalised).

    Page 1 only by default: later pages carry *cited* DOIs that cross-match other papers.
    """
    import pdfplumber

    found: set[str] = set()
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:pages]:
                txt = page.extract_text() or ""
                # Mine raw text AND whitespace-stripped text: PDFs break DOIs across lines
                # ("10.1128/aac\n.01622-19"), so the despaced pass rejoins the full DOI.
                for src in (txt, re.sub(r"\s+", "", txt)):
                    for m in _DOI_RE.findall(src):
                        found.add(_norm(m.rstrip(").")))
    except Exception as exc:  # noqa: BLE001 — an unreadable PDF just yields no DOI
        print(f"  [warn] could not read {path.name}: {type(exc).__name__}", file=sys.stderr)
    return found


def _match(pdf: Path, acc_keys: dict[str, set[str]]) -> list[str]:
    """Return the accession(s) a PDF belongs to (DOI text-mine → filename token → override)."""
    stem = _norm(pdf.stem)
    if stem in OVERRIDES:
        return OVERRIDES[stem]
    for raw_stem, accs in OVERRIDES.items():  # also honour override on substring of the stem
        if raw_stem in stem:
            return accs

    # 1) Filename/URL token containment — authoritative for publisher-named files (cix270, dkx135,
    #    s41564-…, journal.pgph.…, PIIS…). Done first: it never picks up cited DOIs.
    hits = {acc for acc, keys in acc_keys.items() if any(k in stem or stem in k for k in keys)}
    if hits:
        return sorted(hits)

    # 2) DOI text-mined from page 1 — for generic names (file.pdf, main.pdf, descriptive titles).
    #    Match only when the accession's DOI is a substring of the PDF's mined DOI (the PDF carries
    #    the full/longer string); the reverse direction lets truncated DOIs cross-match every paper.
    pdf_keys = _pdf_dois(pdf)
    hits = {acc for acc, keys in acc_keys.items()
            if any(any(pk == k or k in pk for k in keys) for pk in pdf_keys)}
    return sorted(hits)


def main() -> None:
    """Match downloaded PDFs to accessions and copy them into the manual_download/ tree."""
    p = argparse.ArgumentParser(description="Link manual paper PDFs → data/find_papers/manual_download/.")
    p.add_argument("--downloads", required=True, help="Folder of manually-downloaded publisher PDFs.")
    p.add_argument("--worklist", default=str(WORKLIST), help="missing_papers_report.tsv (has_paper rows).")
    p.add_argument("--out-dir", default=str(MANUAL_DIR), help="Destination for <accession>.pdf.")
    p.add_argument("--dry-run", action="store_true", help="Report matches without copying.")
    args = p.parse_args()

    dl = Path(args.downloads).expanduser()
    out = Path(args.out_dir)
    if not dl.is_dir():
        sys.exit(f"downloads folder not found: {dl}")
    rep = pd.read_csv(args.worklist, sep="\t", dtype=str).fillna("")
    have_paper = rep[rep["has_paper"].str.lower().isin({"true", "1", "yes"})]
    acc_keys = {r["study_accession"]: _accession_keys(r) for _, r in have_paper.iterrows()}

    pdfs = sorted(q for q in dl.glob("*.pdf"))
    print(f"{len(pdfs)} PDFs in {dl.name}; {len(acc_keys)} accessions need a paper.\n", file=sys.stderr)

    resolved: dict[str, Path] = {}
    unmatched_pdfs: list[str] = []
    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        accs = _match(pdf, acc_keys)
        if not accs:
            unmatched_pdfs.append(pdf.name)
            continue
        for acc in accs:
            resolved[acc] = pdf
            dest = out / f"{acc}.pdf"
            print(f"  {pdf.name}  ->  {acc}.pdf", file=sys.stderr)
            if not args.dry_run:
                shutil.copy2(pdf, dest)

    missing = sorted(set(acc_keys) - set(resolved))
    print(f"\nResolved {len(resolved)}/{len(acc_keys)} accessions.", file=sys.stderr)
    if missing:
        print(f"STILL MISSING ({len(missing)}): {', '.join(missing)}", file=sys.stderr)
    if unmatched_pdfs:
        print(f"Unmatched PDFs ({len(unmatched_pdfs)}): {', '.join(unmatched_pdfs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
