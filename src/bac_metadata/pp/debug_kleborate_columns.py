"""
Debug script to analyze kleborate column extraction from Excel sheets.

This script:
1. Loads and analyzes the kleborate sheet structure
2. Loads and analyzes the NCTC sheet structure
3. Compares column sets between sheets
4. Tests merge logic with proper column extraction
"""

from __future__ import annotations

import pandas as pd
from bac_metadata.pp.metadata_collation import QC_EXCEL_FILE


def analyze_kleborate_sheet(qc_excel_path: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Analyze the kleborate sheet structure.
    
    Expected structure: Sample | FINAL (skip) | kleborate columns (index 2→end)
    
    Returns:
    --------
    tuple[pd.DataFrame, list[str]]
        - The loaded dataframe
        - List of kleborate column names (excluding Sample and FINAL)
    """
    print("\n" + "="*80)
    print("ANALYZING KLEBORATE SHEET")
    print("="*80)
    
    # Load sheet
    df = pd.read_excel(qc_excel_path, sheet_name='kleborate')
    print(f"\nLoaded kleborate sheet: {len(df)} rows, {len(df.columns)} columns")
    
    # Show all column names
    print(f"\nAll columns in kleborate sheet ({len(df.columns)} total):")
    for i, col in enumerate(df.columns):
        print(f"  [{i}] '{col}'")
    
    # Check for required columns
    if 'Sample' not in df.columns:
        raise ValueError("Column 'Sample' not found in 'kleborate' sheet")
    
    # Extract kleborate columns: exclude 'Sample' and 'FINAL'
    all_cols = set(df.columns)
    exclude_cols = {'Sample', 'FINAL'}
    kleborate_cols = sorted(list(all_cols - exclude_cols))
    
    print(f"\nExcluded columns: {exclude_cols}")
    print(f"Kleborate columns extracted: {len(kleborate_cols)}")
    
    # Show first 10 and last 10 kleborate columns
    if len(kleborate_cols) > 0:
        print(f"\nFirst 10 kleborate columns:")
        for col in kleborate_cols[:10]:
            print(f"  - '{col}'")
        if len(kleborate_cols) > 10:
            print(f"  ... and {len(kleborate_cols) - 10} more")
            print(f"\nLast 10 kleborate columns:")
            for col in kleborate_cols[-10:]:
                print(f"  - '{col}'")
    
    # Verify column positions
    print(f"\nColumn position analysis:")
    if 'FINAL' in df.columns:
        final_idx = list(df.columns).index('FINAL')
        print(f"  'FINAL' is at index {final_idx}")
        print(f"  Expected kleborate columns start at index {final_idx + 1}")
        actual_kleb_start = list(df.columns).index(kleborate_cols[0]) if kleborate_cols else None
        if actual_kleb_start is not None:
            print(f"  First kleborate column '{kleborate_cols[0]}' is at index {actual_kleb_start}")
            if actual_kleb_start == final_idx + 1:
                print(f"  ✓ Column positions match expected structure")
            else:
                print(f"  ⚠ WARNING: Column positions don't match expected structure")
    
    return df, kleborate_cols


def analyze_nctc_sheet(qc_excel_path: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Analyze the NCTC sheet structure.
    
    Expected structure: strain (→Sample) | 3 metadata columns | kleborate columns (index 4→end)
    
    Returns:
    --------
    tuple[pd.DataFrame, list[str]]
        - The loaded dataframe (with 'strain' renamed to 'Sample')
        - List of kleborate column names (from index 4 onward)
    """
    print("\n" + "="*80)
    print("ANALYZING NCTC SHEET")
    print("="*80)
    
    # Load sheet
    df = pd.read_excel(qc_excel_path, sheet_name='NCTC')
    print(f"\nLoaded NCTC sheet: {len(df)} rows, {len(df.columns)} columns")
    
    # Show all column names
    print(f"\nAll columns in NCTC sheet ({len(df.columns)} total):")
    for i, col in enumerate(df.columns):
        print(f"  [{i}] '{col}'")
    
    # Check for required columns
    if 'strain' not in df.columns:
        raise ValueError("Column 'strain' not found in 'NCTC' sheet")
    
    # Rename 'strain' to 'Sample'
    df = df.rename(columns={'strain': 'Sample'})
    
    # Extract kleborate columns: from index 4 onward (skip strain + 3 metadata cols)
    # Method 1: By position (index 4 onward)
    nctc_all_cols = list(df.columns)
    nctc_kleborate_cols_by_position = nctc_all_cols[4:]
    
    print(f"\nColumn position analysis:")
    print(f"  Column 0 (Sample/strain): '{nctc_all_cols[0]}'")
    print(f"  Columns 1-3 (metadata): {nctc_all_cols[1:4]}")
    print(f"  Kleborate columns start at index 4: '{nctc_all_cols[4] if len(nctc_all_cols) > 4 else 'N/A'}'")
    print(f"  Total kleborate columns by position: {len(nctc_kleborate_cols_by_position)}")
    
    # Show first 10 and last 10 kleborate columns
    if len(nctc_kleborate_cols_by_position) > 0:
        print(f"\nFirst 10 kleborate columns (by position):")
        for col in nctc_kleborate_cols_by_position[:10]:
            print(f"  - '{col}'")
        if len(nctc_kleborate_cols_by_position) > 10:
            print(f"  ... and {len(nctc_kleborate_cols_by_position) - 10} more")
            print(f"\nLast 10 kleborate columns (by position):")
            for col in nctc_kleborate_cols_by_position[-10:]:
                print(f"  - '{col}'")
    
    return df, nctc_kleborate_cols_by_position


def compare_column_sets(
    kleborate_cols: list[str],
    nctc_kleborate_cols: list[str],
) -> None:
    """
    Compare kleborate columns between the two sheets.
    
    Parameters:
    -----------
    kleborate_cols : list[str]
        Kleborate columns from kleborate sheet
    nctc_kleborate_cols : list[str]
        Kleborate columns from NCTC sheet
    """
    print("\n" + "="*80)
    print("COMPARING COLUMN SETS")
    print("="*80)
    
    kleborate_set = set(kleborate_cols)
    nctc_set = set(nctc_kleborate_cols)
    
    # Columns in both
    common_cols = sorted(list(kleborate_set & nctc_set))
    
    # Columns only in kleborate
    only_kleborate = sorted(list(kleborate_set - nctc_set))
    
    # Columns only in NCTC
    only_nctc = sorted(list(nctc_set - kleborate_set))
    
    print(f"\nSummary:")
    print(f"  Kleborate sheet columns: {len(kleborate_cols)}")
    print(f"  NCTC sheet columns: {len(nctc_kleborate_cols)}")
    print(f"  Common columns: {len(common_cols)}")
    print(f"  Only in kleborate: {len(only_kleborate)}")
    print(f"  Only in NCTC: {len(only_nctc)}")
    
    if len(common_cols) > 0:
        print(f"\nFirst 10 common columns:")
        for col in common_cols[:10]:
            print(f"  - '{col}'")
        if len(common_cols) > 10:
            print(f"  ... and {len(common_cols) - 10} more")
    
    if len(only_kleborate) > 0:
        print(f"\nColumns only in kleborate sheet ({len(only_kleborate)}):")
        for col in only_kleborate[:10]:
            print(f"  - '{col}'")
        if len(only_kleborate) > 10:
            print(f"  ... and {len(only_kleborate) - 10} more")
    
    if len(only_nctc) > 0:
        print(f"\nColumns only in NCTC sheet ({len(only_nctc)}):")
        for col in only_nctc[:10]:
            print(f"  - '{col}'")
        if len(only_nctc) > 10:
            print(f"  ... and {len(only_nctc) - 10} more")
    
    # Check if column names match exactly
    if kleborate_set == nctc_set:
        print(f"\n✓ SUCCESS: All kleborate columns match between sheets!")
    else:
        print(f"\n⚠ WARNING: Column sets don't match exactly")
        if len(common_cols) == len(kleborate_cols) and len(only_nctc) > 0:
            print(f"  NCTC has extra columns that aren't in kleborate sheet")
        elif len(common_cols) == len(nctc_kleborate_cols) and len(only_kleborate) > 0:
            print(f"  Kleborate sheet has extra columns that aren't in NCTC sheet")
        else:
            print(f"  Both sheets have unique columns")


def test_merge_logic(
    kleborate_df: pd.DataFrame,
    kleborate_cols: list[str],
    nctc_df: pd.DataFrame,
    nctc_kleborate_cols: list[str],
) -> None:
    """
    Test the merge logic with proper column extraction.
    
    Parameters:
    -----------
    kleborate_df : pd.DataFrame
        Kleborate sheet dataframe
    kleborate_cols : list[str]
        List of kleborate column names from kleborate sheet
    nctc_df : pd.DataFrame
        NCTC sheet dataframe (with 'Sample' column)
    nctc_kleborate_cols : list[str]
        List of kleborate column names from NCTC sheet
    """
    print("\n" + "="*80)
    print("TESTING MERGE LOGIC")
    print("="*80)
    
    # Get common columns (columns that exist in both sheets)
    common_cols = sorted(list(set(kleborate_cols) & set(nctc_kleborate_cols)))
    
    print(f"\nMerging on common columns: {len(common_cols)} columns")
    
    if len(common_cols) == 0:
        print("  ⚠ WARNING: No common columns found - cannot merge")
        return
    
    # Extract relevant columns from each dataframe
    kleborate_subset = kleborate_df[['Sample'] + common_cols].copy()
    nctc_subset = nctc_df[['Sample'] + common_cols].copy()
    
    print(f"\nKleborate subset: {len(kleborate_subset)} rows, {len(kleborate_subset.columns)} columns")
    print(f"NCTC subset: {len(nctc_subset)} rows, {len(nctc_subset.columns)} columns")
    
    # Get sample counts
    kleborate_samples = set(kleborate_subset['Sample'].dropna().unique())
    nctc_samples = set(nctc_subset['Sample'].dropna().unique())
    common_samples = kleborate_samples & nctc_samples
    
    print(f"\nSample overlap:")
    print(f"  Kleborate samples: {len(kleborate_samples)}")
    print(f"  NCTC samples: {len(nctc_samples)}")
    print(f"  Common samples: {len(common_samples)}")
    
    # Test merge (left join from kleborate perspective)
    merged = kleborate_subset.merge(
        nctc_subset,
        on='Sample',
        how='left',
        suffixes=('', '_nctc')
    )
    
    print(f"\nMerged dataframe: {len(merged)} rows, {len(merged.columns)} columns")
    
    # Check how many values were filled from NCTC
    filled_count = 0
    for col in common_cols:
        nctc_col = f"{col}_nctc"
        if nctc_col in merged.columns:
            # Count how many NaN values in kleborate column were filled by NCTC
            nan_before = merged[col].isna().sum()
            merged[col] = merged[col].fillna(merged[nctc_col])
            nan_after = merged[col].isna().sum()
            filled = nan_before - nan_after
            if filled > 0:
                filled_count += filled
                print(f"  Column '{col}': {filled} NaN values filled from NCTC")
    
    print(f"\nTotal values filled from NCTC: {filled_count}")
    
    # Clean up duplicate columns
    for col in common_cols:
        nctc_col = f"{col}_nctc"
        if nctc_col in merged.columns:
            merged = merged.drop(columns=[nctc_col])
    
    print(f"Final merged dataframe: {len(merged)} rows, {len(merged.columns)} columns")
    print(f"  ✓ Merge test completed successfully")


def main():
    """Main function to run the debug analysis."""
    print("="*80)
    print("DEBUG: KLEBORATE COLUMN EXTRACTION")
    print("="*80)
    print(f"\nQC Excel file: {QC_EXCEL_FILE}")
    
    try:
        # Step 1: Analyze kleborate sheet
        kleborate_df, kleborate_cols = analyze_kleborate_sheet(QC_EXCEL_FILE)
        
        # Step 2: Analyze NCTC sheet
        nctc_df, nctc_kleborate_cols = analyze_nctc_sheet(QC_EXCEL_FILE)
        
        # Step 3: Compare column sets
        compare_column_sets(kleborate_cols, nctc_kleborate_cols)
        
        # Step 4: Test merge logic
        test_merge_logic(kleborate_df, kleborate_cols, nctc_df, nctc_kleborate_cols)
        
        print("\n" + "="*80)
        print("DEBUG ANALYSIS COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
