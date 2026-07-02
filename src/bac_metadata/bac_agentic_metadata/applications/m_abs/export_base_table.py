"""Export the *M. abscessus* per-sample base table once, as the full-width flat CSV the engine ingests.

The engine driver (``engine/run_full_metadata_agent.py``) is application-agnostic: it reads a single
**pre-built per-sample table** keyed by ``study_accession`` + ``sample_accession`` where every per-sample
field the spec names is a real column, plus the anchoring columns the per-sample extractor joins on. The
Klebsiella source is the collation pipeline (see ``klebsiella/export_base_table.py``); the M.abs source is
the ATB release spreadsheet (``ATB_metadata_Mabs_2025_release.xlsx``, an ENA export with curator columns
bolted on), so this builder's whole job is to **coalesce the spreadsheet's ENA-native + curator variants
into the canonical field names the spec declares** and keep the anchoring/aux columns.

Canonical per-sample fields (from ``attributes.yaml`` ``per_sample_completeness.fields``) and their sources
in the xlsx:

* ``country``          ← ``Country`` (curator), else ENA ``country``.
* ``collection_date``  ← ``Sample_date`` (curator, most specific), else ``collection_year``.
* ``isolation_source`` ← ENA ``isolation_source``.
* ``host``             ← ENA ``host``, else ``host_scientific_name``.
* ``cf_status``        ← curator ``cf_status`` (raw ``CF`` / ``Non-CF`` / ``?`` / ``Animal`` /
  ``Environmental`` — NOT normalised here; the spec normalises downstream).
* ``smoking_status``   ← no column exists → an empty column (100 % paper-derived).

AST is **not** a base column at all (the spreadsheet carries no MIC/AST) — it is extracted per-isolate from
papers by :mod:`engine.sample_extractor`, so it never appears here.

Values are copied RAW (only whitespace-trimmed; placeholders are left for the engine's ``strip_placeholders``
to handle, so completeness is measured on identical rules to Klebsiella). The anchoring columns
(``secondary_sample_accession`` / ``accession`` / ``sample_alias`` / ``sample_title``) already exist in the
ENA export under their canonical names, so the driver's full-width anchor guard passes unchanged.

Examples
--------
unset VIRTUAL_ENV
uv run python .../applications/m_abs/export_base_table.py                 # -> data/inputs/base_table.csv
uv run python .../applications/m_abs/export_base_table.py --output /tmp/mabs_base.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DEFAULT_XLSX = APP_DIR / "ATB_metadata_Mabs_2025_release.xlsx"
DEFAULT_OUTPUT = APP_DIR / "data" / "inputs" / "base_table.csv"

#: Canonical per-sample field -> ordered candidate source columns in the xlsx (first non-blank wins).
#: An empty list means no structured source exists (the field is entirely paper-derived).
FIELD_SOURCES: dict[str, list[str]] = {
    "country": ["Country", "country"],
    "collection_date": ["Sample_date", "collection_year"],
    "isolation_source": ["isolation_source"],
    "host": ["host", "host_scientific_name"],
    "cf_status": ["cf_status"],
    "smoking_status": [],  # no column in the release — paper-only
}

#: Key + anchoring + auxiliary columns carried through verbatim. The full per-sample IDENTIFIER set (every
#: column below except instrument_platform / scientific_name) is what the extractor anchors supplementary
#: tables on — deposited accessions, ENA aliases, strain/isolate names, and Sanger lane IDs. This set is
#: declared to the engine via ``sample_identifier_columns`` in attributes.yaml (see the critical note there
#: and in PROGRESS_REPORT.md — reviewing the input for ALL per-sample identifiers is the first onboarding
#: step for a new species). The four anchoring columns (secondary_sample_accession / accession /
#: sample_alias / sample_title) also satisfy the driver's full-width guard.
KEEP_COLUMNS: tuple[str, ...] = (
    "study_accession", "sample_accession",
    "secondary_sample_accession", "accession", "experiment_accession",
    "run_accession", "sample_alias", "run_alias", "experiment_alias", "sample_title",
    "strain", "isolate", "library_name", "lane", "lane_sanitised",
    "instrument_platform", "scientific_name",
)


def _coalesce(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """First non-blank (whitespace-trimmed) value across ``candidates`` present in ``df``, else ``""``."""
    out = pd.Series("", index=df.index, dtype="object")
    for col in candidates:
        if col not in df.columns:
            continue
        val = df[col].fillna("").astype(str).str.strip()
        out = out.mask((out == "") & (val != ""), val)
    return out


def export_base_table(output: Path, *, xlsx: Path = DEFAULT_XLSX) -> pd.DataFrame:
    """Build the full-width M.abs per-sample base table from the ATB xlsx and write it as CSV."""
    df = pd.read_excel(xlsx, sheet_name=0, dtype=str)
    if "study_accession" not in df.columns or "sample_accession" not in df.columns:
        sys.exit(f"xlsx needs study_accession + sample_accession; got {list(df.columns)[:12]}")

    out = pd.DataFrame(index=df.index)
    for col in KEEP_COLUMNS:
        out[col] = df[col].fillna("").astype(str).str.strip() if col in df.columns else ""
    for field, sources in FIELD_SOURCES.items():
        out[field] = _coalesce(df, sources) if sources else ""

    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    return out


def main() -> None:
    """Parse arguments and export the full-width M.abs base table."""
    p = argparse.ArgumentParser(description="Export the M. abscessus full-width per-sample base table as CSV.")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path (default data/inputs/base_table.csv).")
    p.add_argument("--xlsx", default=str(DEFAULT_XLSX), help="ATB M.abs release spreadsheet (default the committed copy).")
    args = p.parse_args()

    base = export_base_table(Path(args.output), xlsx=Path(args.xlsx))
    n_studies = base["study_accession"].nunique()
    filled = {f: int((base[f].astype(str).str.strip() != "").sum()) for f in FIELD_SOURCES}
    print(f"Wrote {args.output}: {len(base)} samples across {n_studies} studies ({base.columns.size} columns)",
          file=sys.stderr)
    print(f"Structured field fills: {filled}", file=sys.stderr)


if __name__ == "__main__":
    main()
