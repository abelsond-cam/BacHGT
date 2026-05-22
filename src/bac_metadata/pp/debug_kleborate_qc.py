"""
Small debugging script to inspect discrepancies between the QC Excel
`kleborate`, `bakrep`, and `Refseq` sheets.

Specifically:
- Filter `kleborate` to rows with non-null `contig_count` (samples where
  kleborate has actually been run).
- Compare these Sample IDs to those present in the `bakrep` and `Refseq` sheets.
- Print a short summary and the first 15 Sample IDs that are present in
  filtered `kleborate` but *not* present in (bakrep ∪ Refseq).

Usage (from repo root):
    uv run Klebsiella/pp/debug_kleborate_qc.py
"""

from __future__ import annotations

import sys
from typing import Set

import pandas as pd

try:
    # Reuse the QC_EXCEL_FILE path from the main pipeline
    from bac_metadata.pp.metadata_collation import QC_EXCEL_FILE
except Exception as exc:  # pragma: no cover - defensive fallback
    print("ERROR: Could not import QC_EXCEL_FILE from metadata_collation.")
    print(f"Import error: {type(exc).__name__}: {exc}")
    sys.exit(1)


def _load_sheet(path: str, sheet: str) -> pd.DataFrame:
    """Load a sheet from the QC Excel file with basic error checking."""
    try:
        df = pd.read_excel(path, sheet_name=sheet)
    except FileNotFoundError:
        print(f"ERROR: QC Excel file not found: {path}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to read sheet '{sheet}' from {path}: {type(exc).__name__}: {exc}")
        sys.exit(1)

    if "Sample" not in df.columns:
        print(f"ERROR: Column 'Sample' not found in sheet '{sheet}'. Columns available:")
        print(list(df.columns))
        sys.exit(1)

    return df


def _sample_set(df: pd.DataFrame) -> Set[str]:
    """Return a set of Sample IDs as strings (drop NA)."""
    return set(df["Sample"].dropna().astype(str).unique())


def main() -> None:
    print(f"QC Excel file: {QC_EXCEL_FILE}")

    # Load sheets
    kleborate_df = _load_sheet(QC_EXCEL_FILE, "kleborate")
    bakrep_df = _load_sheet(QC_EXCEL_FILE, "bakrep")
    refseq_df = _load_sheet(QC_EXCEL_FILE, "Refseq")

    # Filter kleborate to rows where contig_count is not null
    if "contig_count" in kleborate_df.columns:
        initial_rows = len(kleborate_df)
        kleborate_df = kleborate_df[kleborate_df["contig_count"].notna()].copy()
        print(
            f"kleborate sheet: {initial_rows} rows total, "
            f"{len(kleborate_df)} rows with non-null contig_count"
        )
    else:
        print("WARNING: 'contig_count' column not found in kleborate sheet - using all rows")

    # Build sample sets (as strings to avoid type-mismatch issues)
    kleborate_samples = _sample_set(kleborate_df)
    bakrep_samples = _sample_set(bakrep_df)
    refseq_samples = _sample_set(refseq_df)
    
    # Create combined set: bakrep ∪ Refseq
    combined_samples = bakrep_samples | refseq_samples

    print(f"Unique samples in filtered kleborate: {len(kleborate_samples)}")
    print(f"Unique samples in bakrep: {len(bakrep_samples)}")
    print(f"Unique samples in Refseq: {len(refseq_samples)}")
    print(f"Unique samples in combined (bakrep ∪ Refseq): {len(combined_samples)}")

    # Samples in kleborate (filtered) but not in (bakrep ∪ Refseq)
    missing_in_combined = sorted(kleborate_samples - combined_samples)

    print(
        f"\nSamples present in filtered kleborate but NOT in (bakrep ∪ Refseq): "
        f"{len(missing_in_combined)}"
    )

    if not missing_in_combined:
        print("No discrepancies found (all filtered kleborate samples are in bakrep or Refseq).")
        return

    # Show first 15 Sample IDs for manual inspection
    print("\nFirst 15 Sample IDs in kleborate (filtered) but NOT in (bakrep ∪ Refseq):")
    for sample_id in missing_in_combined[:15]:
        print(f"  {sample_id}")


if __name__ == "__main__":
    main()

