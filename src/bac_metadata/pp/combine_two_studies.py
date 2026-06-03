"""Combine study metadata by merging TSV accessions into the main CSV.

Steps:
- Read main CSV and supplementary TSV.
- Build Collection Date in the CSV from Year/Month (01/MM/YYYY).
- Add TSV rows whose Accession is not already in Reads accession (Illumina).
- Write combined CSV to a new file, preserving column order.
"""
from pathlib import Path
from typing import Iterable

import pandas as pd


# Input/output locations (hardcoded as requested)
_PROJECT_K = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david")
_ENA_STUDY = _PROJECT_K / "raw/metadata/study_level_metadata/ENA_projects/PRJNA351909_PRJEB6891"
DATA_CSV = _ENA_STUDY / "data.csv"
TSV_SUPPLEMENT = _ENA_STUDY / "cix270_suppl_supplementarytable1.tsv"
OUTPUT_CSV = _ENA_STUDY / "data_combined.csv"


def _find_column(df: pd.DataFrame, target: str) -> str:
    """Return the first column whose normalized name matches target (tolerates BOM)."""
    target_norm = target.lower().strip()

    def normalize(col: str) -> str:
        return col.strip().lstrip("\ufeff").lower()

    matches = [col for col in df.columns if normalize(col) == target_norm]
    if not matches:
        # Fallback: substring match in case headers were mangled
        matches = [col for col in df.columns if target_norm in normalize(col)]
    if not matches:
        raise KeyError(f"Column '{target}' not found in DataFrame columns.")
    return matches[0]


def _build_collection_date(years: Iterable, months: Iterable) -> pd.Series:
    """Construct Collection Date as 01/MM/YYYY, using Year and Month."""
    years_numeric = pd.to_numeric(years, errors="coerce").astype("Int64")
    months_numeric = pd.to_numeric(months, errors="coerce").astype("Int64")

    result = pd.Series(pd.NA, index=pd.RangeIndex(len(years_numeric)), dtype="string")
    valid_mask = (
        months_numeric.between(1, 12, inclusive="both") & years_numeric.notna()
    )
    result.loc[valid_mask] = [
        f"01/{int(month):02d}/{int(year):04d}"
        for month, year in zip(months_numeric[valid_mask], years_numeric[valid_mask])
    ]
    return result


def _read_tsv_with_fallback(path: Path) -> pd.DataFrame:
    """Read TSV, tolerating BOM/encoding issues and bad lines."""
    for enc in ("utf-16", "utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(
                path,
                sep="\t",
                engine="python",
                encoding=enc,
                encoding_errors="replace",
                on_bad_lines="warn",
            )
        except UnicodeDecodeError:
            continue
    # Last resort: try default encoding without specifying
    return pd.read_csv(path, sep="\t", engine="python", on_bad_lines="warn")


def main() -> None:
    # Load inputs
    csv_df = pd.read_csv(
        DATA_CSV,
        sep=",",
        engine="python",
        on_bad_lines="warn",
    )
    tsv_df = _read_tsv_with_fallback(TSV_SUPPLEMENT)

    total_csv_rows = len(csv_df)
    total_tsv_rows = len(tsv_df)

    # Resolve column names (allowing for trailing spaces in headers)
    reads_col = _find_column(csv_df, "Reads accession (Illumina)")
    sample_type_col = _find_column(csv_df, "SampleType")
    year_col = _find_column(csv_df, "Year")
    month_col = _find_column(csv_df, "Month")
    collection_col = "Collection Date"

    tsv_accession_col = _find_column(tsv_df, "Accession")
    tsv_source_col = _find_column(tsv_df, "Source")
    tsv_collection_col = _find_column(tsv_df, "Collection Date")

    # Normalize new-data Collection Date from dd/mm/yy -> dd/mm/yyyy by prefixing 20
    tsv_df[tsv_collection_col] = (
        tsv_df[tsv_collection_col]
        .astype(str)
        .str.replace(r"(\\d{2}/\\d{2}/)(\\d{2})$", r"\\120\\2", regex=True)
    )

    # Build Collection Date for existing CSV rows
    csv_df[collection_col] = _build_collection_date(
        csv_df[year_col], csv_df[month_col]
    )

    # Identify TSV rows with accessions not already present
    existing_accessions = csv_df[reads_col].astype(str).str.strip()
    new_data = tsv_df.copy()
    new_data[tsv_accession_col] = new_data[tsv_accession_col].astype(str).str.strip()
    missing_mask = ~new_data[tsv_accession_col].isin(existing_accessions)
    already_present_count = int((~missing_mask).sum())
    additions = new_data.loc[missing_mask]
    additions_count = len(additions)

    if additions.empty:
        combined_df = csv_df
    else:
        # Prepare rows aligned to CSV columns
        template = {col: pd.NA for col in csv_df.columns}
        new_rows = pd.DataFrame(template, index=additions.index)
        new_rows[reads_col] = additions[tsv_accession_col]
        new_rows[sample_type_col] = additions[tsv_source_col]
        new_rows[collection_col] = additions[tsv_collection_col]

        combined_df = pd.concat([csv_df, new_rows], ignore_index=True)

    combined_df.to_csv(OUTPUT_CSV, index=False)

    print(
        f"Main CSV rows: {total_csv_rows} | TSV rows: {total_tsv_rows} | "
        f"TSV already present: {already_present_count} | Added: {additions_count}"
    )
    print(f"Output written to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()

