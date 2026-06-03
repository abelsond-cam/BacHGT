#!/usr/bin/env python3
"""cache_sr_checkm2.py
----------------------
Read the ``checkM2`` sheet out of Aaron's ``klebsiella_qc_NCTC.xlsx`` QC workbook
on OneDrive and write a slim TSV cache to ``notebooks/_data/sr_checkm2.tsv``.

The QC workbook is 112 MB and reopening it from a notebook is slow; this
extractor runs once and the notebook reads only the TSV from then on.

Usage
─────
    uv run python src/bac_data/lr_data/cache_sr_checkm2.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

QC_XLSX = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/klebsiella_qc_NCTC.xlsx"
)
OUT_TSV = Path(__file__).parent / "notebooks" / "_data" / "sr_checkm2.tsv"
SHEET = "checkM2"

KEEP_COLS = [
    "Sample",
    "Completeness",
    "Contamination",
    "Contig_N50",
    "Total_Contigs",
    "Genome_Size",
]


def main() -> int:
    """Read the checkM2 sheet, slim to the columns we plot, write the TSV."""
    print(f"Reading {SHEET!r} from {QC_XLSX}", flush=True)
    df = pd.read_excel(QC_XLSX, sheet_name=SHEET, usecols=KEEP_COLS)
    print(f"  rows={len(df)}  cols={list(df.columns)}", flush=True)

    OUT_TSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_TSV, sep="\t", index=False)
    print(f"Wrote {OUT_TSV}  rows={len(df)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
