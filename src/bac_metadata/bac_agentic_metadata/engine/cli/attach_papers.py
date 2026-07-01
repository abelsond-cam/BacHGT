r"""Curator CLI — match hand-downloaded paper PDFs to their study accession and stage them for grading.

Species-agnostic wrapper over :func:`engine.stages.attach_downloaded_papers`. Paywalled describing papers
(listed in ``find_papers/missing_papers_report.tsv`` with ``has_paper=True``) are downloaded by hand into a
publisher-named PDF; this matches each to its accession (filename/URL token → DOI text-mined from page 1 →
an optional overrides map) and copies it to ``<data-dir>/find_papers/manual_download/<accession>.pdf`` so
grading picks it up on the next pass. A single PDF may serve several accessions (one paper, >1 project).
Idempotent. Replaces the former per-application ``link_local_papers.py``.

    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.attach_papers \\
        --downloads "~/Downloads/Agentic Metadata Downloads" \\
        --data-dir .../applications/klebsiella/data
    (optional: --overrides overrides.json, a {filename_stem: [accession, ...]} map for PDFs no matcher resolves)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bac_metadata.bac_agentic_metadata.engine.stages import attach_downloaded_papers


def main() -> None:
    """Match downloaded PDFs to accessions and copy them into the manual_download/ tree."""
    p = argparse.ArgumentParser(description="Attach hand-downloaded paper PDFs to their study (any application).")
    p.add_argument("--downloads", required=True, help="Folder of manually-downloaded publisher PDFs.")
    p.add_argument("--data-dir", required=True, help="Application data tree root (holds find_papers/).")
    p.add_argument("--worklist", default=None,
                   help="missing_papers_report.tsv (default <data-dir>/find_papers/missing_papers_report.tsv).")
    p.add_argument("--out-dir", default=None,
                   help="Destination for <accession>.pdf (default <data-dir>/find_papers/manual_download).")
    p.add_argument("--overrides", default=None,
                   help="Optional JSON map {filename_stem: [accession, ...]} for PDFs no matcher resolves.")
    p.add_argument("--dry-run", action="store_true", help="Report matches without copying.")
    args = p.parse_args()

    data = Path(args.data_dir)
    worklist = Path(args.worklist) if args.worklist else data / "find_papers" / "missing_papers_report.tsv"
    out_dir = Path(args.out_dir) if args.out_dir else data / "find_papers" / "manual_download"
    overrides = json.loads(Path(args.overrides).read_text()) if args.overrides else {}
    attach_downloaded_papers(downloads_dir=args.downloads, worklist_path=worklist, out_dir=out_dir,
                             overrides=overrides, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
