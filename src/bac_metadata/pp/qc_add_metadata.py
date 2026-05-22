"""
Metadata QC integration pipeline:
- Build unified QC data (kleborate + bakrep + flags)
- Join metadata to QC data (QC-centric left join)
- Report metadata samples not in QC (STEP 10a)
- Report QC samples not in metadata (STEP 10b)
- Fill empty metadata columns from bakrep
- Write final QC dataset with metadata
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# Import helper functions from metadata_collation
from bac_metadata.pp.metadata_collation import (
    STUDY_METADATA_GOOGLE_SHEET_ID,
    OUTPUT_DIR,
    QC_EXCEL_FILE,
    TeeOutput,
    load_removed_studies,
)


def build_qc_data(
    qc_excel_path: str = QC_EXCEL_FILE,
) -> tuple[pd.DataFrame, list[str], dict]:
    """
    Build unified QC data dataframe from bakrep, Refseq, NCTC, kleborate, and FINAL_LIST sheets.
    
    This function:
    1. Loads and combines bakrep + Refseq + NCTC base data
    2. Merges kleborate data from multiple sources with validation
    3. Loads and joins LINcode (Step 5b, before genus/species filtering)
    4. Filters by genus = 'Klebsiella' with safety checks
    5. Calculates flags: is_kpsc, is_refseq, is_nctc (ONLY place in codebase)
    6. Adds kpsc_final_list flag with sense check
    7. Reorders columns: Sample → Flags → Kleborate → LINcode → Bakrep
    8. Filters out samples from removed studies (from Google Sheet)
    9. Calculates flow_metrics for reporting (after all filtering complete)
    
    When kleborate-only samples exist (Step 4 orphans), writes kleborate_not_in_bakrep.tsv
    to OUTPUT_DIR. When LINcode samples are not in QC, writes lincode_not_in_qc.tsv (enriched
    from kleborate_to_join only).
    
    Parameters:
    -----------
    qc_excel_path : str
        Path to the QC Excel file (default: QC_EXCEL_FILE)
    
    Returns:
    --------
    tuple[pd.DataFrame, list[str], dict]
        - QC dataframe with all columns and flags (in optimized column order)
        - List of kleborate column names (for joining to metadata)
        - Flow metrics dictionary tracking sample counts through pipeline
    """
    # Initialize flow metrics tracking dictionary
    flow_metrics = {
        'inputs': {},      # Bakrep, Refseq, NCTC counts
        'removed': {},     # Removed studies breakdown
        'filtered': {},    # Genus filtering
        'klebsiella': {},  # KPSC vs non-KPSC split
        'qc': {},          # QC filtering (KPSC not in final set)
        'final': {},       # Final set counts
        'downstream': {}   # Downstream analyses
    }
    
    print("\n" + "="*80)
    print("STEP 2: LOADING BASE QC DATA (BAKREP, REFSEQ, NCTC)")
    print("="*80)
    
    # Step 2a: Load bakrep sheet - base dataset with all columns
    print("\n--- Step 2a: Loading bakrep sheet ---")
    bakrep_df = pd.read_excel(qc_excel_path, sheet_name='bakrep')
    
    if 'Sample' not in bakrep_df.columns:
        raise ValueError("Column 'Sample' not found in 'bakrep' sheet")
    
    print(f"Loaded bakrep sheet: {len(bakrep_df)} rows, {len(bakrep_df.columns)} columns")
    
    # Get bakrep column names (exclude Sample)
    bakrep_cols = [col for col in bakrep_df.columns if col != 'Sample']
    print(f"Bakrep has {len(bakrep_cols)} bakrep columns (excluding Sample)")
    
    # Step 2b: Load Refseq identifiers ONLY
    print("\n--- Step 2b: Loading Refseq identifiers ONLY ---")
    refseq_raw = pd.read_excel(qc_excel_path, sheet_name='Refseq')
    
    # Refseq uses "FILE" instead of "Sample"
    if 'FILE' not in refseq_raw.columns:
        raise ValueError("Column 'FILE' not found in 'Refseq' sheet")
    
    print(f"Loaded Refseq sheet: {len(refseq_raw)} rows")
    
    # Create slim Refseq dataframe with only Sample + bakrep columns
    refseq_samples = refseq_raw['FILE'].dropna().unique().tolist()
    refseq_slim = pd.DataFrame({'Sample': refseq_samples})
    
    # Add all bakrep columns with appropriate defaults
    for col in bakrep_cols:
        if col == 'gtdbtk.classification.species':
            refseq_slim[col] = 'Refseq_kpsc'
        elif col == 'gtdbtk.classification.genus':
            refseq_slim[col] = 'Klebsiella'
        elif col == 'metadata.studies.accession':
            refseq_slim[col] = 'Refseq_collection'
        else:
            refseq_slim[col] = pd.NA
    
    # Ensure same column order as bakrep
    refseq_slim = refseq_slim[['Sample'] + bakrep_cols].copy()
    print(f"Created slim Refseq dataframe: {len(refseq_slim)} rows, {len(refseq_slim.columns)} columns")
    
    # Step 2c: Load NCTC identifiers ONLY
    print("\n--- Step 2c: Loading NCTC identifiers ONLY ---")
    nctc_raw = None
    nctc_slim = None
    try:
        nctc_raw = pd.read_excel(qc_excel_path, sheet_name='NCTC')
        if 'strain' not in nctc_raw.columns:
            print("  WARNING: Column 'strain' not found in 'NCTC' sheet, skipping NCTC data")
            nctc_raw = None
        else:
            print(f"Loaded NCTC sheet: {len(nctc_raw)} rows")
            
            # Create slim NCTC dataframe with only Sample + bakrep columns
            nctc_samples = nctc_raw['strain'].dropna().unique().tolist()
            nctc_slim = pd.DataFrame({'Sample': nctc_samples})
            
            # Add all bakrep columns with appropriate defaults
            for col in bakrep_cols:
                if col == 'gtdbtk.classification.species':
                    nctc_slim[col] = 'NCTC_kpsc'
                elif col == 'gtdbtk.classification.genus':
                    nctc_slim[col] = 'Klebsiella'
                elif col == 'metadata.studies.accession':
                    nctc_slim[col] = 'NCTC_collection'
                else:
                    nctc_slim[col] = pd.NA
            
            # Ensure same column order as bakrep
            nctc_slim = nctc_slim[['Sample'] + bakrep_cols].copy()
            print(f"Created slim NCTC dataframe: {len(nctc_slim)} rows, {len(nctc_slim.columns)} columns")
    except Exception as e:
        print(f"  WARNING: Could not load NCTC sheet: {type(e).__name__}: {e}")
        print("  Continuing without NCTC data")
        nctc_raw = None
        nctc_slim = None
    
    # Step 2d: Check for duplicate Sample IDs and handle them
    print("\n--- Step 2d: Checking for duplicate Sample IDs ---")
    bakrep_samples = set(bakrep_df['Sample'].dropna().unique())
    refseq_samples = set(refseq_slim['Sample'].dropna().unique())
    nctc_samples = set(nctc_slim['Sample'].dropna().unique()) if nctc_slim is not None else set()
    
    duplicates_br = bakrep_samples & refseq_samples
    duplicates_bn = bakrep_samples & nctc_samples
    duplicates_rn = refseq_samples & nctc_samples
    
    if duplicates_br:
        print(f"  WARNING: {len(duplicates_br)} Sample IDs found in both bakrep and Refseq")
        print("  Preferring bakrep data for these samples")
        refseq_slim = refseq_slim[~refseq_slim['Sample'].isin(duplicates_br)].copy()
    
    if duplicates_bn:
        print(f"  WARNING: {len(duplicates_bn)} Sample IDs found in both bakrep and NCTC")
        print("  Preferring bakrep data for these samples")
        nctc_slim = nctc_slim[~nctc_slim['Sample'].isin(duplicates_bn)].copy()
    
    if duplicates_rn:
        print(f"  WARNING: {len(duplicates_rn)} Sample IDs found in both Refseq and NCTC")
        print("  Preferring Refseq data for these samples")
        nctc_slim = nctc_slim[~nctc_slim['Sample'].isin(duplicates_rn)].copy()
    
    # Step 2e: Concatenate bakrep + Refseq + NCTC
    print("\n--- Step 2e: Concatenating base QC data ---")
    dataframes_to_combine = [bakrep_df, refseq_slim]
    if nctc_slim is not None:
        dataframes_to_combine.append(nctc_slim)
    
    base_qc_data = pd.concat(dataframes_to_combine, ignore_index=True)
    print(f"Combined base QC data: {len(base_qc_data)} rows, {len(base_qc_data.columns)} columns")
    print(f"  Expected: Sample + {len(bakrep_cols)} bakrep columns = {1 + len(bakrep_cols)} total columns")
    
    print("\n" + "="*80)
    print("STEP 3: LOADING AND STANDARDIZING KLEBORATE")
    print("="*80)
    
    print("\n--- Step 3a: Loading and standardizing kleborate sheet ---")
    kleborate_raw = pd.read_excel(qc_excel_path, sheet_name='kleborate')
    
    if 'Sample' not in kleborate_raw.columns:
        raise ValueError("Column 'Sample' not found in 'kleborate' sheet")
    
    # kleborate sheet structure: Sample (index 0) | FINAL (index 1, discard) | kleborate columns (index 2+)
    # Drop column index 1 (FINAL), keep Sample + kleborate columns
    kleborate_std = kleborate_raw.drop(columns=kleborate_raw.columns[1])
    print(f"Loaded kleborate sheet: {len(kleborate_raw)} rows, {len(kleborate_raw.columns)} columns")
    print(f"After dropping FINAL column: {len(kleborate_std)} rows, {len(kleborate_std.columns)} columns")
    print("  Expected: Sample + ~116 kleborate columns")
    
    # Step 3b: Load NCTC kleborate data and standardize
    print("\n--- Step 3b: Loading and standardizing NCTC kleborate data ---")
    nctc_kleborate_std = None
    if nctc_raw is not None:
        # NCTC sheet structure: strain (index 0) | 3 metadata cols (index 1-3) | kleborate columns (index 4+)
        # Rename column 0 to Sample, drop columns 1-3, keep kleborate columns
        nctc_kleborate_std = nctc_raw.copy()
        nctc_kleborate_std.columns = ['Sample'] + list(nctc_raw.columns[1:])
        nctc_kleborate_std = nctc_kleborate_std.drop(columns=nctc_kleborate_std.columns[1:4])
        print(f"Standardized NCTC kleborate data: {len(nctc_kleborate_std)} rows, {len(nctc_kleborate_std.columns)} columns")
        
        # Verify column names match kleborate sheet
        kleborate_cols = set(kleborate_std.columns) - {'Sample'}
        nctc_kleborate_cols = set(nctc_kleborate_std.columns) - {'Sample'}
        if kleborate_cols != nctc_kleborate_cols:
            print("  WARNING: NCTC kleborate columns don't match kleborate sheet exactly")
            print(f"  Kleborate has {len(kleborate_cols)} columns, NCTC has {len(nctc_kleborate_cols)} columns")
            missing_in_nctc = kleborate_cols - nctc_kleborate_cols
            extra_in_nctc = nctc_kleborate_cols - kleborate_cols
            if missing_in_nctc:
                print(f"  Missing in NCTC (first 5): {sorted(list(missing_in_nctc))[:5]}")
            if extra_in_nctc:
                print(f"  Extra in NCTC (first 5): {sorted(list(extra_in_nctc))[:5]}")
        else:
            print(f"  ✓ NCTC kleborate columns match kleborate sheet ({len(kleborate_cols)} columns)")
    
    # Step 3c: Load kleborate_david sheet and standardize
    print("\n--- Step 3c: Loading and standardizing kleborate_david sheet ---")
    kleborate_david_std = None
    try:
        kleborate_david_raw = pd.read_excel(qc_excel_path, sheet_name='kleborate_david')
        if len(kleborate_david_raw.columns) < 2:
            print("  WARNING: kleborate_david sheet has fewer than 2 columns, skipping")
            kleborate_david_std = None
        else:
            # kleborate_david sheet structure: Sample (index 0) | one other col (index 1, discard) | kleborate columns (index 2+)
            # Rename column 0 to Sample, drop column 1, keep kleborate columns
            kleborate_david_std = kleborate_david_raw.copy()
            kleborate_david_std.columns = ['Sample'] + list(kleborate_david_raw.columns[1:])
            kleborate_david_std = kleborate_david_std.drop(columns=kleborate_david_std.columns[1])
            print(f"Standardized kleborate_david data: {len(kleborate_david_std)} rows, {len(kleborate_david_std.columns)} columns")
            
            # Verify column names match kleborate sheet
            david_kleborate_cols = set(kleborate_david_std.columns) - {'Sample'}
            if kleborate_cols != david_kleborate_cols:
                print("  WARNING: kleborate_david columns don't match kleborate sheet exactly")
                print(f"  Kleborate has {len(kleborate_cols)} columns, david has {len(david_kleborate_cols)} columns")
            else:
                print(f"  ✓ kleborate_david columns match kleborate sheet ({len(kleborate_cols)} columns)")
    except Exception as e:
        print(f"  WARNING: Could not load 'kleborate_david' sheet: {type(e).__name__}: {e}")
        kleborate_david_std = None
    
    # Step 3d: Concatenate all kleborate sheets
    print("\n--- Step 3d: Concatenating all kleborate sheets ---")
    kleborate_dfs_to_concat = [kleborate_std]
    if kleborate_david_std is not None:
        kleborate_dfs_to_concat.append(kleborate_david_std)
    if nctc_kleborate_std is not None:
        kleborate_dfs_to_concat.append(nctc_kleborate_std)
    
    kleborate_to_join = pd.concat(kleborate_dfs_to_concat, ignore_index=True)
    print(f"Concatenated kleborate data: {len(kleborate_to_join)} rows before deduplication")
    
    # Remove duplicates keeping first (priority: kleborate > kleborate_david > NCTC)
    before_dedup = len(kleborate_to_join)
    kleborate_to_join = kleborate_to_join.drop_duplicates(subset=['Sample'], keep='first')
    after_dedup = len(kleborate_to_join)
    print(f"After deduplication: {after_dedup} rows (removed {before_dedup - after_dedup} duplicates)")
    print(f"Final kleborate_to_join: {len(kleborate_to_join)} rows, {len(kleborate_to_join.columns)} columns")
    
    # Track kleborate column names (preserve original order, do NOT sort)
    kleborate_columns_list = [col for col in kleborate_to_join.columns if col != 'Sample']
    print(f"Kleborate columns to join: {len(kleborate_columns_list)}")
    
    print("\n" + "="*80)
    print("STEP 4: VALIDATING FOR ORPHANED SAMPLES")
    print("="*80)
    base_qc_samples = set(base_qc_data['Sample'].dropna().unique())
    kleborate_samples = set(kleborate_to_join['Sample'].dropna().unique())
    orphaned_samples = kleborate_samples - base_qc_samples
    
    if len(orphaned_samples) > 0:
        print("\n" + "!"*80)
        print("!!! ERROR: ORPHANED SAMPLES FOUND IN KLEBORATE DATA !!!")
        print("!"*80)
        print(f"\nFound {len(orphaned_samples)} samples in kleborate data that are NOT in base QC data (bakrep+Refseq+NCTC):")
        
        print("\nSample examples (first 10):")
        for sample_id in sorted(list(orphaned_samples))[:10]:
            print(f"  - {sample_id}")
        if len(orphaned_samples) > 10:
            print(f"  ... and {len(orphaned_samples) - 10} more")
        
        # DETAILED ANALYSIS: Check if any orphaned samples are from kleborate_david
        if kleborate_david_std is not None:
            david_samples = set(kleborate_david_std['Sample'].dropna().unique())
            orphaned_david = orphaned_samples & david_samples
            if len(orphaned_david) > 0:
                print(f"\n--- DETAILED ANALYSIS: {len(orphaned_david)} orphaned samples from kleborate_david ---")
                orphaned_david_df = kleborate_david_std[kleborate_david_std['Sample'].isin(orphaned_david)].copy()
                orphaned_david_unique = orphaned_david_df.drop_duplicates(subset=['Sample'], keep='first')
                analysis_total_samples = len(orphaned_david_unique)
                
                print(f"  Number of unique orphaned Sample IDs for analysis: {analysis_total_samples}")
                
                if 'species' in orphaned_david_unique.columns and 'species_match' in orphaned_david_unique.columns:
                    non_kleb_mask = ~orphaned_david_unique['species'].fillna('').astype(str).str.lower().str.contains('klebsiella')
                    weak_match_mask = orphaned_david_unique['species_match'].fillna('').astype(str).str.lower() != 'strong'
                    combined_mask = non_kleb_mask | weak_match_mask
                    combined_count = combined_mask.sum()
                    print(f"  Combined analysis (non-Klebsiella OR weak match) (on {analysis_total_samples} unique samples):")
                    print(f"    - Unique samples matching criteria: {combined_count} ({combined_count / analysis_total_samples * 100:.1f}%)")
                    print(f"    - Unique samples NOT matching criteria: {analysis_total_samples - combined_count}")
                    
                    if combined_count < analysis_total_samples:
                        print(f"    - WARNING: {analysis_total_samples - combined_count} unique orphaned samples are Klebsiella with strong match!")
                        unexpected_df = orphaned_david_unique[~combined_mask]
                        print("    - First 5 unexpected orphaned samples:")
                        for idx, row in unexpected_df.head(5).iterrows():
                            species = row.get('species', 'N/A')
                            match = row.get('species_match', 'N/A')
                            print(f"      - {row['Sample']} (species: {species}, match: {match})")
        
        # Save kleborate-only samples to TSV
        orphaned_df = kleborate_to_join[kleborate_to_join['Sample'].isin(orphaned_samples)].copy()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, 'kleborate_not_in_bakrep.tsv')
        orphaned_df.to_csv(output_path, sep='\t', index=False)
        print(f"\n  Saved {len(orphaned_df)} kleborate-only samples (not in bakrep/Refseq/NCTC) to: {output_path}")
    else:
        print("  ✓ No orphaned samples found - all kleborate samples are in base QC data")
    
    print("\n" + "="*80)
    print("STEP 5: MERGING KLEBORATE TO BASE QC DATA")
    print("="*80)
    
    # Single left join
    qc_data = base_qc_data.merge(
        kleborate_to_join,
        on='Sample',
        how='left'
    )
    
    print(f"Merged QC data: {len(qc_data)} rows, {len(qc_data.columns)} columns")
    print(f"  Base QC columns: {len(base_qc_data.columns)}")
    print(f"  Added kleborate columns: {len(kleborate_columns_list)}")
    
    # ============================================================================
    # STEP 5b: LOAD AND JOIN LINcode DATA
    # ============================================================================
    
    print("\n" + "="*80)
    print("STEP 5b: LOADING LINcode DATA")
    print("="*80)
    
    try:
        lincode_raw = pd.read_excel(qc_excel_path, sheet_name='LINcode')
        
        if 'Sample' not in lincode_raw.columns:
            raise ValueError("Column 'Sample' not found in 'LINcode' sheet")
        
        print(f"Loaded LINcode sheet: {len(lincode_raw)} rows, {len(lincode_raw.columns)} columns")
        
        # Drop 'name' column if it exists
        if 'name' in lincode_raw.columns:
            lincode_raw = lincode_raw.drop(columns=['name'])
            print("  Dropped 'name' column from LINcode data")
        else:
            print("  WARNING: 'name' column not found in LINcode sheet (expected but not required)")
        
        # Check for duplicates and keep first
        before_dedup = len(lincode_raw)
        lincode_raw = lincode_raw.drop_duplicates(subset=['Sample'], keep='first')
        after_dedup = len(lincode_raw)
        
        if before_dedup > after_dedup:
            print(f"  WARNING: Found {before_dedup - after_dedup} duplicate Sample IDs in LINcode - kept first occurrence")
        
        # Build lincode_columns_list (all columns except Sample)
        lincode_columns_list = [col for col in lincode_raw.columns if col != 'Sample']
        print(f"  LINcode columns to join: {len(lincode_columns_list)}")
        
        # Compute join diagnostics
        print("\n--- Join Coverage Analysis (QC vs LINcode) ---")
        qc_samples = set(qc_data['Sample'].dropna().unique())
        lincode_samples = set(lincode_raw['Sample'].dropna().unique())
        
        qc_count = len(qc_samples)
        lincode_count = len(lincode_samples)
        matched_samples = qc_samples & lincode_samples
        qc_not_in_lincode = qc_samples - lincode_samples
        lincode_not_in_qc = lincode_samples - qc_samples
        
        print(f"  QC samples (before genus/species filtering): {qc_count}")
        print(f"  LINcode samples: {lincode_count}")
        print(f"  QC samples found in LINcode: {len(matched_samples)} ({len(matched_samples) / qc_count * 100:.1f}%)")
        print(f"  QC samples NOT in LINcode: {len(qc_not_in_lincode)} ({len(qc_not_in_lincode) / qc_count * 100:.1f}%)")
        print(f"  LINcode samples NOT in QC: {len(lincode_not_in_qc)} ({len(lincode_not_in_qc) / lincode_count * 100:.1f}%)")
        
        if len(matched_samples) == qc_count:
            print("  ✓ All QC samples found in LINcode!")
        else:
            print(f"\n  WARNING: {len(qc_not_in_lincode)} QC samples missing from LINcode")
            if len(qc_not_in_lincode) > 0:
                print("  First 5 QC samples not in LINcode:")
                for sample in sorted(list(qc_not_in_lincode))[:5]:
                    print(f"    - {sample}")
                if len(qc_not_in_lincode) > 5:
                    print(f"    ... and {len(qc_not_in_lincode) - 5} more")
        
        if len(lincode_not_in_qc) > 0:
            print(f"\n  Note: {len(lincode_not_in_qc)} LINcode samples not in QC (will be ignored in left join)")
            
            # Get DataFrame rows for samples not in QC
            lincode_not_in_qc_df = lincode_raw[lincode_raw['Sample'].isin(lincode_not_in_qc)].copy()
            
            # Enrich from kleborate_to_join only (in memory; no Excel, no bakrep)
            kleborate_cols = ['Sample']
            if 'species' in kleborate_to_join.columns:
                kleborate_cols.append('species')
            if 'species_match' in kleborate_to_join.columns:
                kleborate_cols.append('species_match')
            kleborate_subset = kleborate_to_join[kleborate_cols].drop_duplicates(subset=['Sample'], keep='first').copy()
            rename_map = {}
            if 'species' in kleborate_subset.columns:
                rename_map['species'] = 'kleborate_species'
            if 'species_match' in kleborate_subset.columns:
                rename_map['species_match'] = 'kleborate_species_match'
            if rename_map:
                kleborate_subset = kleborate_subset.rename(columns=rename_map)
            lincode_not_in_qc_df = lincode_not_in_qc_df.merge(kleborate_subset, on='Sample', how='left')
            
            # Analyze the combined dataframe
            print(f"\n  Analysis of {len(lincode_not_in_qc_df)} LINcode samples not in QC:")
            
            if 'LINcode' in lincode_not_in_qc_df.columns:
                unique_lincodes = lincode_not_in_qc_df['LINcode'].dropna().nunique()
                print(f"    Unique LINcode values: {unique_lincodes}")
            
            if 'Phylogroup' in lincode_not_in_qc_df.columns:
                unique_phylogroups = lincode_not_in_qc_df['Phylogroup'].dropna().nunique()
                print(f"    Unique Phylogroup values: {unique_phylogroups}")
            
            if 'Sublineage' in lincode_not_in_qc_df.columns:
                unique_sublineages = lincode_not_in_qc_df['Sublineage'].dropna().nunique()
                print(f"    Unique Sublineage values: {unique_sublineages}")
            
            print("\n  Checking if lincode_not_in_qc samples are Klebsiella (kleborate only):")
            if 'kleborate_species' in lincode_not_in_qc_df.columns:
                kleborate_found = lincode_not_in_qc_df['kleborate_species'].notna().sum()
                print(f"    Kleborate: {kleborate_found} samples found")
                if 'kleborate_species_match' in lincode_not_in_qc_df.columns:
                    kleb_strong_mask = (
                        lincode_not_in_qc_df['kleborate_species'].fillna('').astype(str).str.lower().str.contains('klebsiella') &
                        (lincode_not_in_qc_df['kleborate_species_match'].fillna('').astype(str).str.lower() == 'strong')
                    )
                    kleb_strong_count = kleb_strong_mask.sum()
                    print(f"      - Klebsiella with strong match: {kleb_strong_count} samples")
                else:
                    print("      - (species_match column not available)")
            
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, 'lincode_not_in_qc.tsv')
            lincode_not_in_qc_df.to_csv(output_path, sep='\t', index=False)
            print(f"\n  Saved {len(lincode_not_in_qc_df)} LINcode samples (with kleborate data) to: {output_path}")
        
        # Perform left join
        print("\n--- Joining LINcode to QC data ---")
        before_cols = len(qc_data.columns)
        qc_data = qc_data.merge(lincode_raw, on='Sample', how='left', suffixes=('', '_lincode_dup'))
        after_cols = len(qc_data.columns)
        
        dup_cols = [col for col in qc_data.columns if col.endswith('_lincode_dup')]
        if dup_cols:
            print(f"  WARNING: {len(dup_cols)} duplicate columns detected from LINcode merge: {dup_cols[:5]}")
            print("  Dropping duplicate columns...")
            qc_data = qc_data.drop(columns=dup_cols)
            after_cols = len(qc_data.columns)
        
        print(f"  Merged QC data: {len(qc_data)} rows (unchanged)")
        print(f"  Added {after_cols - before_cols} LINcode columns")
        print(f"  Total columns: {after_cols}")
        
        lincode_columns_list = [col for col in lincode_columns_list if col in qc_data.columns]
        
    except Exception as e:
        print(f"  WARNING: Could not load 'LINcode' sheet: {type(e).__name__}: {e}")
        print("  Continuing without LINcode data")
        lincode_columns_list = []
    
    print("="*80 + "\n")
    
    print("\n" + "="*80)
    print("STEP 6a: FILTERING BY GENUS KLEBSIELLA")
    print("="*80)
    
    if 'gtdbtk.classification.genus' not in qc_data.columns:
        raise ValueError("Column 'gtdbtk.classification.genus' not found in QC data")
    
    # Identify samples to be filtered
    filtered_mask = qc_data['gtdbtk.classification.genus'] != 'Klebsiella'
    filtered_samples = qc_data[filtered_mask].copy()
    
    # SAFETY CHECK - Refseq/NCTC should NEVER be filtered
    if 'gtdbtk.classification.species' in filtered_samples.columns:
        refseq_filtered = (filtered_samples['gtdbtk.classification.species'] == 'Refseq_kpsc').sum()
        nctc_filtered = (filtered_samples['gtdbtk.classification.species'] == 'NCTC_kpsc').sum()
        
        if refseq_filtered > 0 or nctc_filtered > 0:
            print("\n" + "!"*80)
            print("!!! ERROR: REFSEQ/NCTC SAMPLES WOULD BE FILTERED BY GENUS CHECK !!!")
            print("!"*80)
            print(f"\nFound {refseq_filtered} Refseq samples and {nctc_filtered} NCTC samples that would be filtered (genus != 'Klebsiella')")
            print("\nThis should NEVER happen because we explicitly set genus='Klebsiella' for Refseq/NCTC.")
            
            if refseq_filtered > 0:
                refseq_filtered_ids = filtered_samples[filtered_samples['gtdbtk.classification.species'] == 'Refseq_kpsc']['Sample'].tolist()
                print(f"\nRefseq samples to be filtered: {refseq_filtered_ids}")
            
            if nctc_filtered > 0:
                nctc_filtered_ids = filtered_samples[filtered_samples['gtdbtk.classification.species'] == 'NCTC_kpsc']['Sample'].tolist()
                print(f"\nNCTC samples to be filtered: {nctc_filtered_ids}")
            
            print("\nACTION REQUIRED: Check the annotation logic in steps 1b and 1c.")
            print("!"*80 + "\n")
            raise ValueError("CRITICAL BUG: Refseq/NCTC samples would be filtered by genus check")
    
    # Apply filter
    before_count = len(qc_data)
    qc_data = qc_data[~filtered_mask].copy()
    after_count = len(qc_data)
    filtered_count = before_count - after_count
    
    print(f"Filtered {filtered_count} samples (not genus Klebsiella)")
    print(f"Remaining: {after_count} Klebsiella samples")
    
    if filtered_count > 0 and 'gtdbtk.classification.species' in filtered_samples.columns:
        print("\nBreakdown of filtered samples by species/genus:")
        species_counts = filtered_samples['gtdbtk.classification.species'].value_counts()
        for species, count in species_counts.head(10).items():
            print(f"  - {species}: {count} samples")
        if len(species_counts) > 10:
            print(f"  ... and {len(species_counts) - 10} more species")
    
    print("\n" + "="*80)
    print("STEP 6b: FILTERING BY KLEBORATE SPECIES CALL")
    print("="*80)
    
    if 'species' not in qc_data.columns:
        print("WARNING: Column 'species' not found in QC data - skipping Kleborate species filter")
        species_filtered_count = 0
    else:
        # Identify samples to be filtered (species does NOT contain 'klebsiella')
        species_filtered_mask = ~qc_data['species'].fillna('').astype(str).str.lower().str.contains('klebsiella')
        species_filtered_samples = qc_data[species_filtered_mask].copy()
        
        # Apply filter
        before_species_count = len(qc_data)
        qc_data = qc_data[~species_filtered_mask].copy()
        after_species_count = len(qc_data)
        species_filtered_count = before_species_count - after_species_count
        
        print("Kleborate species analysis:")
        print(f"  Klebsiella samples (by Kleborate species call): {after_species_count}")
        print(f"  Non-Klebsiella samples (filtered): {species_filtered_count}")
        print(f"Remaining: {after_species_count} Klebsiella samples")
        
        # Show breakdown of species being removed
        if species_filtered_count > 0:
            species_counts = species_filtered_samples['species'].value_counts()
            n_unique_species = len(species_counts)
            print(f"\nBreakdown of {species_filtered_count} filtered samples:")
            print(f"  Unique species being removed: {n_unique_species}")
            print("\n  Top species (up to 10):")
            for species, count in species_counts.head(10).items():
                print(f"    - {species}: {count} samples")
            if n_unique_species > 10:
                print(f"    ... and {n_unique_species - 10} more species")
    
    # Update cumulative filtered count
    filtered_count = filtered_count + species_filtered_count
    after_count = len(qc_data)
    
    print(f"\nTotal filtered (genus + species): {filtered_count}")
    print(f"Remaining after all Step 6 filters: {after_count}")
    
    print("\n" + "="*80)
    print("STEP 6c: UPDATING FLOW METRICS")
    print("="*80)
    
    # Track filtered (non-Klebsiella) samples for Sankey
    flow_metrics['filtered']['non_klebsiella'] = filtered_count
    
    # Calculate input sources based on Klebsiella dataset (after genus filtering, before removed studies)
    if 'gtdbtk.classification.species' in qc_data.columns:
        refseq_klebsiella = (qc_data['gtdbtk.classification.species'] == 'Refseq_kpsc').sum()
        nctc_klebsiella = (qc_data['gtdbtk.classification.species'] == 'NCTC_kpsc').sum()
        bakrep_klebsiella = len(qc_data) - refseq_klebsiella - nctc_klebsiella
        
        flow_metrics['inputs']['bakrep'] = bakrep_klebsiella
        flow_metrics['inputs']['refseq'] = refseq_klebsiella
        flow_metrics['inputs']['nctc'] = nctc_klebsiella
        flow_metrics['inputs']['total'] = len(qc_data)
        
        print("Input sources (Klebsiella only, after all Step 6 filtering):")
        print(f"  Bakrep: {bakrep_klebsiella:,}")
        print(f"  Refseq: {refseq_klebsiella:,}")
        print(f"  NCTC: {nctc_klebsiella:,}")
        print(f"  Total: {len(qc_data):,}")
    
    # Note: klebsiella_total will be calculated after removed studies filtering
    
    print("\n" + "="*80)
    print("STEP 7: CALCULATING IS_KPSC BOOLEAN")
    print("="*80)
    
    def _is_kpsc_inline(species_name):
        """Determine if species is KPSC. Used ONLY in build_qc_data()."""
        if pd.isna(species_name):
            return False
        species_str = str(species_name)
        # Refseq and NCTC synthetic markers
        if species_str in ['Refseq_kpsc', 'NCTC_kpsc']:
            return True
        species_lower = species_str.lower()
        # Must contain "klebsiella" AND at least one KPSC indicator
        if "klebsiella" not in species_lower:
            return False
        kpsc_indicators = ['pneumoniae', 'quasi', 'variicola', 'africana', 'tropica']
        return any(indicator in species_lower for indicator in kpsc_indicators)
    
    if 'gtdbtk.classification.species' not in qc_data.columns:
        raise ValueError("Column 'gtdbtk.classification.species' not found in QC data")
    
    qc_data['is_kpsc'] = qc_data['gtdbtk.classification.species'].apply(_is_kpsc_inline)
    
    kpsc_count = qc_data['is_kpsc'].sum()
    non_kpsc_count = (~qc_data['is_kpsc']).sum()
    print(f"Calculated is_kpsc flag: {kpsc_count} KPSC samples, {non_kpsc_count} non-KPSC samples")
    
    # Add is_refseq and is_nctc flags
    qc_data['is_refseq'] = qc_data['gtdbtk.classification.species'] == 'Refseq_kpsc'
    qc_data['is_nctc'] = qc_data['gtdbtk.classification.species'] == 'NCTC_kpsc'
    
    refseq_count = qc_data['is_refseq'].sum()
    nctc_count = qc_data['is_nctc'].sum()
    print(f"Calculated is_refseq flag: {refseq_count} Refseq samples")
    print(f"Calculated is_nctc flag: {nctc_count} NCTC samples")
    
    print("\n" + "="*80)
    print("STEP 8: ADDING FINAL_LIST FLAG")
    print("="*80)
    
    try:
        final_list_df = pd.read_excel(qc_excel_path, sheet_name='FINAL_LIST')
        
        if 'Sample' not in final_list_df.columns:
            print("  WARNING: Column 'Sample' not found in 'FINAL_LIST' sheet, skipping FINAL_LIST flag")
            qc_data['kpsc_final_list'] = False
        elif 'kept' not in final_list_df.columns:
            print("  WARNING: Column 'kept' not found in 'FINAL_LIST' sheet, skipping FINAL_LIST flag")
            qc_data['kpsc_final_list'] = False
        else:
            # Convert kept column to boolean if needed
            kept_series = final_list_df['kept']
            if kept_series.dtype == 'object':
                kept_series = kept_series.astype(str).str.lower().isin(['true', '1', 'yes'])
            kept_mask = kept_series.fillna(False).astype(bool)
            
            # Create boolean: kpsc_final_list = TRUE if sample is in FINAL_LIST AND kept=TRUE
            final_list_kept_samples = set(final_list_df[kept_mask]['Sample'].dropna().unique())
            qc_data['kpsc_final_list'] = qc_data['Sample'].isin(final_list_kept_samples)
            
            final_list_count = qc_data['kpsc_final_list'].sum()
            print(f"Added kpsc_final_list flag: {final_list_count} samples with kept=TRUE")
            
            # SENSE CHECK - All kpsc_final_list=TRUE samples should be KPSC
            final_list_samples = qc_data[qc_data['kpsc_final_list']]
            non_kpsc_in_final_list = (~final_list_samples['is_kpsc']).sum()
            
            if non_kpsc_in_final_list > 0:
                print("\n" + "="*80)
                print("WARNING: Non-KPSC samples found in FINAL_LIST with kept=TRUE")
                print("="*80)
                print(f"\nFound {non_kpsc_in_final_list} samples in FINAL_LIST (kept=TRUE) that are NOT KPSC (is_kpsc=FALSE)")
                print("\nThis is unexpected - FINAL_LIST kept=TRUE should primarily contain KPSC samples.")
                
                non_kpsc_samples = final_list_samples[~final_list_samples['is_kpsc']]
                print("\nFirst 5 sample IDs:")
                for idx, row in non_kpsc_samples.head(5).iterrows():
                    species = row.get('gtdbtk.classification.species', 'N/A')
                    print(f"  - {row['Sample']} (species: {species})")
                
                print("\nNote: This is a warning only. These samples will still have kpsc_final_list=TRUE.")
                print("Please review if this is expected.")
                print("="*80)
    except Exception as e:
        print(f"  WARNING: Could not load FINAL_LIST sheet: {type(e).__name__}: {e}")
        print("  Setting kpsc_final_list=False for all samples")
        qc_data['kpsc_final_list'] = False
    
    # Summary after Step 8 (before removed studies filtering)
    print("\n" + "="*80)
    print("INTERMEDIATE SUMMARY (STEPS 2-8)")
    print("="*80)
    print(f"Total samples: {len(qc_data)}")
    print(f"Total columns: {len(qc_data.columns)}")
    print(f"KPSC samples (is_kpsc=TRUE): {qc_data['is_kpsc'].sum()}")
    print(f"Refseq samples (is_refseq=TRUE): {qc_data['is_refseq'].sum()}")
    print(f"NCTC samples (is_nctc=TRUE): {qc_data['is_nctc'].sum()}")
    print(f"kpsc_final_list=TRUE: {qc_data['kpsc_final_list'].sum()}")
    print(f"Kleborate columns: {len(kleborate_columns_list)}")
    
    print("="*80 + "\n")
    
    # Step 9: Filter out samples from removed studies (moved from Step 2f)
    print("\n" + "="*80)
    print("STEP 9: FILTERING REMOVED STUDIES")
    print("="*80)
    print("\n--- Step 9: Filtering out samples from removed studies ---")
    removed_studies_set = load_removed_studies(google_sheet_id=STUDY_METADATA_GOOGLE_SHEET_ID)
    
    if len(removed_studies_set) > 0:
        # Check if metadata.studies.accession column exists
        if 'metadata.studies.accession' not in qc_data.columns:
            print("  WARNING: Column 'metadata.studies.accession' not found in QC data")
            print("  Cannot filter by removed studies - skipping this step")
            flow_metrics['removed']['count'] = 0
            flow_metrics['removed']['after_pruning'] = len(qc_data)
        else:
            # Identify samples to be removed (those with study_accession in removed_studies_set)
            before_count = len(qc_data)
            removal_mask = qc_data['metadata.studies.accession'].isin(removed_studies_set)
            samples_to_remove = qc_data[removal_mask].copy()
            
            if len(samples_to_remove) > 0:
                # Show breakdown by study
                removed_study_counts = samples_to_remove.groupby('metadata.studies.accession')['Sample'].nunique().sort_values(ascending=False)
                
                print(f"  Found {len(samples_to_remove)} samples from {len(removed_study_counts)} removed studies:")
                print("\n  Samples by study:")
                for study, count in removed_study_counts.head(10).items():
                    print(f"    - {study}: {count} samples")
                if len(removed_study_counts) > 10:
                    print(f"    ... and {len(removed_study_counts) - 10} more studies")
                
                # Apply filter
                qc_data = qc_data[~removal_mask].copy()
                after_count = len(qc_data)
                
                print(f"\n  Removed {before_count - after_count} samples from removed studies")
                print(f"  Remaining: {after_count} samples")
                
                # Track removed studies count
                flow_metrics['removed']['count'] = before_count - after_count
                flow_metrics['removed']['after_pruning'] = after_count
            else:
                print(f"  No samples found from the {len(removed_studies_set)} removed studies")
                flow_metrics['removed']['count'] = 0
                flow_metrics['removed']['after_pruning'] = before_count
    else:
        print("  No removed studies to filter (removed_studies sheet is empty or not found)")
        flow_metrics['removed']['count'] = 0
        flow_metrics['removed']['after_pruning'] = len(qc_data)
    
    print("="*80 + "\n")
    
    # ============================================================================
    # CALCULATE FLOW_METRICS (after removed studies filtering)
    # ============================================================================
    
    print("\n" + "="*80)
    print("CALCULATING FLOW METRICS FOR REPORTING")
    print("="*80)
    
    # Track removed studies (already calculated above)
    # flow_metrics['removed']['count'] and ['after_pruning'] already set
    
    # Track final Klebsiella total (after genus + removed studies filtering)
    flow_metrics['filtered']['klebsiella_total'] = len(qc_data)
    
    # Track KPSC vs non-KPSC split (after removed studies filtering)
    kpsc_count = qc_data['is_kpsc'].sum()
    non_kpsc_count = (~qc_data['is_kpsc']).sum()
    flow_metrics['klebsiella']['kpsc'] = kpsc_count
    flow_metrics['klebsiella']['non_kpsc'] = non_kpsc_count
    print(f"KPSC split: {kpsc_count:,} KPSC, {non_kpsc_count:,} non-KPSC")
    
    # Track QC filtering (KPSC samples: passed QC vs failed QC)
    kpsc_samples = qc_data[qc_data['is_kpsc']]
    if 'kpsc_final_list' in qc_data.columns:
        kpsc_passed_qc = (kpsc_samples['kpsc_final_list']).sum()
        kpsc_failed_qc = len(kpsc_samples) - kpsc_passed_qc
        flow_metrics['qc']['kpsc_passed'] = kpsc_passed_qc
        flow_metrics['qc']['kpsc_failed'] = kpsc_failed_qc
        flow_metrics['final']['kpsc_final_set'] = kpsc_passed_qc
        print(f"QC filtering: {kpsc_passed_qc:,} passed, {kpsc_failed_qc:,} failed")
    else:
        flow_metrics['qc']['kpsc_passed'] = 0
        flow_metrics['qc']['kpsc_failed'] = len(kpsc_samples)
        flow_metrics['final']['kpsc_final_set'] = 0
    
    # Track downstream analyses (all use same kpsc_final_list samples)
    flow_metrics['downstream']['panaroo'] = flow_metrics['final']['kpsc_final_set']
    flow_metrics['downstream']['st_k_loci'] = flow_metrics['final']['kpsc_final_set']
    flow_metrics['downstream']['plasmid_hgt'] = flow_metrics['final']['kpsc_final_set']
    flow_metrics['downstream']['amr_isolation'] = flow_metrics['final']['kpsc_final_set']
    
    # Summary of all metrics:
    # - Input sources already tracked at Step 6 (flow_metrics['inputs'])
    # - Non-Klebsiella count already tracked at Step 6 (flow_metrics['filtered']['non_klebsiella'])
    # - Removed studies tracked above (flow_metrics['removed'])
    # - All other metrics tracked in this section
    
    print("="*80 + "\n")
    
    # ============================================================================
    # FINAL COLUMN REORDERING: Sample → Flags → Kleborate → LINcode → Bakrep
    # ============================================================================
    
    print("\n--- Reordering columns for better readability ---")
    flag_columns = ['is_kpsc', 'kpsc_final_list', 'is_refseq', 'is_nctc']
    
    # Use bakrep_cols to preserve original bakrep column order
    # Only include bakrep columns that actually exist in qc_data
    bakrep_columns_final = [col for col in bakrep_cols if col in qc_data.columns]
    
    # Build final column order: Sample → Flags → Kleborate → LINcode → Bakrep
    # Only include columns that actually exist in qc_data and avoid duplicates
    column_order = ['Sample'] + flag_columns + kleborate_columns_list + lincode_columns_list + bakrep_columns_final
    
    # Remove any duplicates from column_order
    seen = set()
    column_order_unique = []
    for col in column_order:
        if col not in seen:
            seen.add(col)
            column_order_unique.append(col)
    
    if len(column_order) != len(column_order_unique):
        print(f"  WARNING: Removed {len(column_order) - len(column_order_unique)} duplicate columns from column order")
    
    column_order = column_order_unique
    
    # Reorder
    qc_data = qc_data[column_order].copy()
    
    if len(lincode_columns_list) > 0:
        print(f"Column order: Sample (1) + Flags ({len(flag_columns)}) + Kleborate ({len(kleborate_columns_list)}) + LINcode ({len(lincode_columns_list)}) + Bakrep ({len(bakrep_columns_final)})")
    else:
        print(f"Column order: Sample (1) + Flags ({len(flag_columns)}) + Kleborate ({len(kleborate_columns_list)}) + Bakrep ({len(bakrep_columns_final)})")
    print(f"  Flag columns: {', '.join(flag_columns)}")
    print(f"  Total columns: {len(column_order)}")
    
    print("="*80 + "\n")
    
    return qc_data, kleborate_columns_list, flow_metrics


def join_qc_data(
    metadata: pd.DataFrame,
    qc_excel_path: str = QC_EXCEL_FILE,
) -> tuple[pd.DataFrame, dict]:
    """
    Join metadata to QC data using left join (QC-centric).
    
    Returns QC data with metadata columns added where available.
    All QC samples are retained; metadata samples not in QC are excluded.
    
    Parameters:
    -----------
    metadata : pd.DataFrame
        The metadata dataframe with sample_accession column
    qc_excel_path : str
        Path to the QC Excel file (default: QC_EXCEL_FILE)
    
    Returns:
    --------
    tuple[pd.DataFrame, dict]
        - QC data with metadata columns added (left join preserves all QC samples)
        - Flow metrics dictionary tracking sample counts through pipeline
    """
    # Validate input data
    if 'sample_accession' not in metadata.columns:
        raise ValueError("Column 'sample_accession' not found in metadata")
    
    metadata_row_count = len(metadata)
    metadata_sample_count = metadata['sample_accession'].nunique()
    
    # Build unified QC data (Steps 2-8 executed within build_qc_data)
    qc_data, kleborate_columns_list, flow_metrics = build_qc_data(qc_excel_path)
    qc_row_count = len(qc_data)
    qc_sample_count = qc_data['Sample'].nunique()
    
    # Now perform Step 9: Join metadata to QC
    print("\n" + "="*80)
    print("STEP 9: JOINING METADATA TO QC DATA")
    print("="*80)
    print(f"Metadata: {metadata_row_count} rows, {metadata_sample_count} unique samples")
    print(f"QC data: {qc_row_count} rows, {qc_sample_count} unique samples")
    print(f"  (includes {len(kleborate_columns_list)} kleborate columns, is_kpsc and kpsc_final_list flags)")
    
    # Perform QC-centric left join (keep all QC samples, add metadata where available)
    print("\nPerforming left join: QC data (left) + metadata (right)...")
    combined_data = qc_data.merge(
        metadata,
        left_on='Sample',
        right_on='sample_accession',
        how='left',
        suffixes=('', '_metadata')
    )
    
    # Keep both Sample and sample_accession columns
    print(f"Combined data: {len(combined_data)} rows, {len(combined_data.columns)} columns")
    
    # Fill sample_accession from Sample for unmatched QC samples
    combined_data['sample_accession'] = combined_data['Sample'].fillna(combined_data['sample_accession'])

    # Report join statistics
    # Samples with metadata are those where sample_accession is not null
    matched_mask = combined_data['sample_accession'].notna()
    matched_count = matched_mask.sum()
    unmatched_count = qc_row_count - matched_count
    
    print("\nJoin results:")
    print(f"  QC samples matched to metadata: {matched_count} ({matched_count / qc_row_count * 100:.1f}%)")
    print(f"  QC samples NOT matched to metadata: {unmatched_count} ({unmatched_count / qc_row_count * 100:.1f}%)")
    
    if 'is_kpsc' in combined_data.columns:
        kpsc_count = combined_data['is_kpsc'].sum()
        print(f"  KPSC samples (is_kpsc=TRUE): {kpsc_count}")
    
    if 'is_refseq' in combined_data.columns:
        refseq_count = combined_data['is_refseq'].sum()
        print(f"  Refseq samples (is_refseq=TRUE): {refseq_count}")
    
    if 'is_nctc' in combined_data.columns:
        nctc_count = combined_data['is_nctc'].sum()
        print(f"  NCTC samples (is_nctc=TRUE): {nctc_count}")
    
    if 'kpsc_final_list' in combined_data.columns:
        final_list_count = combined_data['kpsc_final_list'].sum()
        print(f"  kpsc_final_list=TRUE: {final_list_count}")
    
    # Step 9 summary
    print("\n--- Step 9 Summary ---")
    print(f"Final data: {len(combined_data)} rows (all from QC)")
    print(f"Unique samples: {combined_data['Sample'].nunique()}")
    print("="*80 + "\n")
    
    return combined_data, flow_metrics


def report_unmatched_metadata_samples(
    metadata: pd.DataFrame,
    qc_samples: set,
    output_dir: str,
) -> None:
    """
    STEP 10a: Identify and save metadata samples that are NOT in QC data.
    
    These are samples that were in our metadata collation but were excluded
    because they are not present in the QC dataset (typically not Klebsiella).
    
    Parameters:
    -----------
    metadata : pd.DataFrame
        The metadata dataframe with sample_accession column
    qc_samples : set
        Set of QC sample IDs
    output_dir : str
        Directory to write the unmatched samples file
    
    Returns:
    --------
    None
        Saves file to {output_dir}/metadata_samples_not_in_qc.tsv
    """
    print("\n" + "="*80)
    print("STEP 10a: REPORTING UNMATCHED METADATA SAMPLES (in metadata but NOT in QC)")
    print("="*80)
    
    # Validate columns
    if 'sample_accession' not in metadata.columns:
        print("ERROR: Column 'sample_accession' not found in metadata")
        return
    
    # Identify unmatched samples
    metadata_samples = set(metadata['sample_accession'].dropna().unique())
    unmatched_samples = metadata_samples - qc_samples
    
    print(f"Metadata samples: {len(metadata_samples)}")
    print(f"QC samples: {len(qc_samples)}")
    print(f"Unmatched (in metadata but NOT in QC): {len(unmatched_samples)}")
    
    if len(unmatched_samples) == 0:
        print("  No unmatched samples - all metadata samples are in QC")
        print("="*80 + "\n")
        return
    
    # Extract unmatched sample data
    unmatched_df = metadata[metadata['sample_accession'].isin(unmatched_samples)].copy()
    
    # Select columns to save (use only those that exist)
    columns_to_save = ['sample_accession', 'study_accession', 'scientific_name', 
                       'country', 'host', 'isolation_source', 'collection_date']
    available_columns = [col for col in columns_to_save if col in unmatched_df.columns]
    
    if 'sample_accession' not in available_columns:
        print("ERROR: Cannot save unmatched samples - sample_accession column missing")
        return
    
    unmatched_to_save = unmatched_df[available_columns].copy()
    
    # Save to file
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'metadata_samples_not_in_qc.tsv')
    unmatched_to_save.to_csv(output_path, sep='\t', index=False)
    
    print(f"\nSaved {len(unmatched_to_save)} unmatched samples to: {output_path}")
    print(f"  Columns saved: {', '.join(available_columns)}")
    
    # Print summary statistics by scientific_name if available
    if 'scientific_name' in unmatched_df.columns:
        print("\n--- Breakdown by scientific_name ---")
        scientific_name_counts = unmatched_df['scientific_name'].value_counts()
        print(f"Unique scientific names: {len(scientific_name_counts)}")
        print("\nTop 10 scientific names:")
        for name, count in scientific_name_counts.head(10).items():
            pct = (count / len(unmatched_df) * 100) if len(unmatched_df) > 0 else 0
            print(f"  - {name}: {count} samples ({pct:.1f}%)")
        if len(scientific_name_counts) > 10:
            print(f"  ... and {len(scientific_name_counts) - 10} more")
    
    print("\n" + "-"*80 + "\n Seb has checked ~1500 of these.  Kleborate classifies none of them as Klebsiella.")  
    print("Presumably Bakrep doesn't either, which is why they are not in the QC data!")
    print("="*80 + "\n")


def report_unmatched_qc_samples(
    combined_data: pd.DataFrame,
    output_dir: str,
) -> None:
    """
    STEP 10b: Identify and save QC samples that are NOT in metadata.
    
    These are samples that are in the QC dataset but were not matched to our
    metadata collation. They are kept in the final dataset but don't receive
    metadata enrichment. Critically, they may be missing study_accession.
    
    Parameters:
    -----------
    combined_data : pd.DataFrame
        The combined dataframe from QC left join with metadata (before STEP 11)
    output_dir : str
        Directory to write the unmatched samples file
    
    Returns:
    --------
    None
        Saves file to {output_dir}/qc_samples_not_in_metadata.tsv
    """
    print("\n" + "="*80)
    print("STEP 10b: REPORTING UNMATCHED QC SAMPLES (in QC but NOT in metadata)")
    print("="*80)
    
    # Detect QC samples not in metadata by checking if study_accession is NA
    # (study_accession is a metadata column that should be populated if matched)
    # NOTE: Must run BEFORE STEP 11 which fills study_accession from bakrep
    
    if 'study_accession' not in combined_data.columns:
        print("WARNING: Column 'study_accession' not found in combined_data")
        print("Cannot identify unmatched QC samples")
        print("="*80 + "\n")
        return
    
    # Identify unmatched QC samples (those with NA study_accession from metadata)
    unmatched_mask = combined_data['study_accession'].isna()
    unmatched_qc = combined_data[unmatched_mask].copy()
    
    total_qc_samples = len(combined_data)
    unmatched_count = len(unmatched_qc)
    matched_count = total_qc_samples - unmatched_count
    
    print(f"Total QC samples: {total_qc_samples}")
    print(f"QC samples matched to metadata: {matched_count} ({matched_count / total_qc_samples * 100:.1f}%)")
    print(f"QC samples NOT matched to metadata: {unmatched_count} ({unmatched_count / total_qc_samples * 100:.1f}%)")
    
    if unmatched_count == 0:
        print("  ✓ All QC samples are matched to metadata")
        print("="*80 + "\n")
        return
    
    # Analyze unmatched samples
    print(f"\n--- Analysis of {unmatched_count} unmatched QC samples ---")
    
    # Check if they have metadata.studies.accession from bakrep
    if 'metadata.studies.accession' in unmatched_qc.columns:
        has_bakrep_study = unmatched_qc['metadata.studies.accession'].notna().sum()
        missing_both = unmatched_count - has_bakrep_study
        print(f"  Samples with metadata.studies.accession (from bakrep): {has_bakrep_study} ({has_bakrep_study / unmatched_count * 100:.1f}%)")
        print(f"  Samples missing BOTH study_accession AND metadata.studies.accession: {missing_both} ({missing_both / unmatched_count * 100:.1f}%)")
        
        if missing_both > 0:
            print(f"\n  WARNING: {missing_both} samples will have NO study_accession after STEP 11")
    else:
        print("  WARNING: Column 'metadata.studies.accession' not found - cannot check bakrep data")
    
    # Breakdown by is_refseq and is_nctc flags
    if 'is_refseq' in unmatched_qc.columns and 'is_nctc' in unmatched_qc.columns:
        refseq_count = unmatched_qc['is_refseq'].sum()
        nctc_count = unmatched_qc['is_nctc'].sum()
        other_count = unmatched_count - refseq_count - nctc_count
        
        print("\n  Breakdown by source:")
        print(f"    Refseq samples: {refseq_count} ({refseq_count / unmatched_count * 100:.1f}%)")
        print(f"    NCTC samples: {nctc_count} ({nctc_count / unmatched_count * 100:.1f}%)")
        print(f"    Other samples: {other_count} ({other_count / unmatched_count * 100:.1f}%)")
        
        # Refseq and NCTC should have synthetic study_accession values from bakrep
        if refseq_count > 0 or nctc_count > 0:
            print("\n  Note: Refseq/NCTC samples should have synthetic study_accession values")
            print("        from metadata.studies.accession (will be filled in STEP 11)")
    
    # Breakdown by KPSC status
    if 'is_kpsc' in unmatched_qc.columns:
        kpsc_count = unmatched_qc['is_kpsc'].sum()
        non_kpsc_count = unmatched_count - kpsc_count
        print("\n  Breakdown by KPSC status:")
        print(f"    KPSC samples: {kpsc_count} ({kpsc_count / unmatched_count * 100:.1f}%)")
        print(f"    Non-KPSC samples: {non_kpsc_count} ({non_kpsc_count / unmatched_count * 100:.1f}%)")
    
    # Select columns to save (use only those that exist)
    columns_to_save = ['Sample', 'study_accession', 'metadata.studies.accession', 
                       'is_refseq', 'is_nctc', 'is_kpsc', 'gtdbtk.classification.species',
                       'gtdbtk.classification.genus']
    available_columns = [col for col in columns_to_save if col in unmatched_qc.columns]
    
    if 'Sample' not in available_columns:
        print("ERROR: Cannot save unmatched QC samples - Sample column missing")
        print("="*80 + "\n")
        return
    
    unmatched_to_save = unmatched_qc[available_columns].copy()
    
    # Save to file
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'qc_samples_not_in_metadata.tsv')
    unmatched_to_save.to_csv(output_path, sep='\t', index=False)
    
    print(f"\nSaved {len(unmatched_to_save)} unmatched QC samples to: {output_path}")
    print(f"  Columns saved: {', '.join(available_columns)}")
    
    # Show first few examples
    print("\n  First 10 examples:")
    for idx, row in unmatched_to_save.head(10).iterrows():
        sample = row.get('Sample', 'N/A')
        species = row.get('gtdbtk.classification.species', 'N/A')
        bakrep_study = row.get('metadata.studies.accession', 'N/A')
        is_refseq = row.get('is_refseq', False)
        is_nctc = row.get('is_nctc', False)
        source = 'Refseq' if is_refseq else ('NCTC' if is_nctc else 'Other')
        print(f"    {sample} | {source} | species: {species} | bakrep_study: {bakrep_study}")
    
    if len(unmatched_to_save) > 10:
        print(f"    ... and {len(unmatched_to_save) - 10} more (see file)")
    
    print("="*80 + "\n")


def add_bakrep_metadata(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fill empty metadata columns from bakrep columns using array-based operations.
    
    Only updates cells that are NA/empty - preserves existing metadata values.
    All data is already in one table from the join.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Combined dataframe with both bakrep columns and metadata columns
    
    Returns:
    --------
    pd.DataFrame
        Dataframe with metadata columns filled from bakrep where metadata was empty
    """
    print("\n" + "="*80)
    print("STEP 11: FILLING METADATA FROM BAKREP")
    print("="*80)
    
    # Define mapping from bakrep columns to metadata columns - for data to be added if metadata is empty
    bakrep_to_metadata_mapping = {
        'metadata.sample.collection_date': 'collection_date',
        'metadata.sample.country': 'country',
        'metadata.sample.host.host': 'host',
        'metadata.sample.isolation_source': 'isolation_source',
        'metadata.studies.accession': 'study_accession'
    }
    
    data = data.copy()
    total_cells_updated = 0
    
    for bakrep_col, metadata_col in bakrep_to_metadata_mapping.items():
        # Check if both columns exist
        if bakrep_col not in data.columns:
            print(f"  WARNING: Bakrep column '{bakrep_col}' not found - skipping")
            continue
        
        if metadata_col not in data.columns:
            print(f"  WARNING: Metadata column '{metadata_col}' not found - skipping")
            continue
        
        # Count cells before filling
        before_count = data[metadata_col].notna().sum()
        
        # Fill NA values in metadata column from bakrep column using array-based operation
        data[metadata_col] = data[metadata_col].fillna(data[bakrep_col])
        
        # Count cells after filling
        after_count = data[metadata_col].notna().sum()
        cells_updated = after_count - before_count
        total_cells_updated += cells_updated
        
        if cells_updated > 0:
            print(f"  {metadata_col}: {before_count} -> {after_count} (+{cells_updated} cells filled from bakrep)")
        else:
            print(f"  {metadata_col}: {before_count} (no cells filled)")
    
    print(f"\nTotal cells updated: {total_cells_updated}")
    print("="*80 + "\n")
    
    return data


def generate_enhanced_qc_summary(
    flow_metrics: dict,
    combined_data: pd.DataFrame,
    output_dir: str,
) -> None:
    """
    Generate enhanced QC summary with detailed flow breakdown suitable for Sankey diagram.
    
    Parameters:
    -----------
    flow_metrics : dict
        Dictionary with sample counts at each pipeline stage
    combined_data : pd.DataFrame
        Final combined dataframe with QC and metadata
    output_dir : str
        Directory to write the summary file
    """
    qc_summary_path = os.path.join(output_dir, 'qc_summary.txt')
    
    with open(qc_summary_path, 'w', encoding='utf-8') as f:
        f.write("SAMPLE FLOW THROUGH PIPELINE\n")
        f.write("="*80 + "\n\n")
        
        # INPUT SOURCES
        f.write("INPUT SOURCES:\n")
        bakrep_count = flow_metrics['inputs'].get('bakrep', 0)
        refseq_count = flow_metrics['inputs'].get('refseq', 0)
        nctc_count = flow_metrics['inputs'].get('nctc', 0)
        total_input = flow_metrics['inputs'].get('total', 0)
        
        f.write(f"  Bakrep:         {bakrep_count:,} samples\n")
        f.write(f"  Refseq:         {refseq_count:,} samples\n")
        f.write(f"  NCTC:           {nctc_count:,} samples\n")
        f.write("  " + "-"*50 + "\n")
        f.write(f"  Total input:    {total_input:,} samples\n\n")
        
        # PRUNING - REMOVED STUDIES
        f.write("PRUNING - REMOVED STUDIES:\n")
        removed_count = flow_metrics['removed'].get('count', 0)
        after_pruning = flow_metrics['removed'].get('after_pruning', 0)
        
        f.write(f"  Lab evolution and metagenomic assemblies removed: {removed_count:,} samples\n")
        f.write("  " + "-"*50 + "\n")
        f.write(f"  Remaining:      {after_pruning:,} samples\n\n")
        
        # SPECIES CLASSIFICATION
        f.write("SPECIES CLASSIFICATION (from Kleborate):\n")
        kpsc_count = flow_metrics['klebsiella'].get('kpsc', 0)
        non_kpsc_count = flow_metrics['klebsiella'].get('non_kpsc', 0)
        total_klebsiella = flow_metrics['filtered'].get('klebsiella_total', 0)
        
        f.write(f"  KPSC (is_kpsc=TRUE):     {kpsc_count:,} samples\n")
        f.write(f"  Non-KPSC Klebsiella:     {non_kpsc_count:,} samples\n")
        f.write("  " + "-"*50 + "\n")
        f.write(f"  Total Klebsiella:        {total_klebsiella:,} samples\n\n")
        
        # QUALITY CONTROL (KPSC only)
        f.write("QUALITY CONTROL (KPSC only):\n")
        kpsc_passed = flow_metrics['qc'].get('kpsc_passed', 0)
        kpsc_failed = flow_metrics['qc'].get('kpsc_failed', 0)
        final_kpsc = flow_metrics['final'].get('kpsc_final_set', 0)
        
        f.write(f"  KPSC passed QC (kpsc_final_list=TRUE):    {kpsc_passed:,} samples\n")
        f.write(f"  KPSC failed QC (excluded from final):     {kpsc_failed:,} samples\n")
        f.write("  " + "-"*50 + "\n")
        f.write(f"  Final KPSC set:                           {final_kpsc:,} samples\n\n")
        
        # DOWNSTREAM ANALYSES
        f.write("DOWNSTREAM ANALYSES (kpsc_final_list=TRUE samples):\n")
        f.write("  → Panaroo pangenome analysis\n")
        f.write("  → ST and K-loci analysis\n")
        f.write("  → Plasmid analysis / HGT insertions\n")
        f.write("  → AMR and isolation source prediction\n")
        f.write(f"  (All analyses: {final_kpsc:,} samples, undergoing)\n\n")
        
        # ADDITIONAL SUMMARY INFO
        f.write("="*80 + "\n")
        f.write("ADDITIONAL SUMMARY\n")
        f.write("="*80 + "\n\n")
        f.write(f"Total samples in final dataset: {len(combined_data):,}\n")
        f.write(f"Unique samples: {combined_data['Sample'].nunique():,}\n")
        
        if 'sample_accession' in combined_data.columns:
            matched = combined_data['sample_accession'].notna().sum()
            matched_pct = (matched / len(combined_data) * 100) if len(combined_data) > 0 else 0
            f.write(f"Samples matched to metadata: {matched:,} ({matched_pct:.1f}%)\n")
        
        f.write(f"Total columns: {len(combined_data.columns)}\n")
    
    print(f"Enhanced QC summary written to: {qc_summary_path}")


def generate_sankey_diagram(
    flow_metrics: dict,
    output_dir: str,
) -> None:
    """
    Generate Sankey diagram showing sample flow through pipeline.
    
    Parameters:
    -----------
    flow_metrics : dict
        Dictionary with sample counts at each pipeline stage
    output_dir : str
        Directory to write the Sankey diagram files
    """
    import plotly.graph_objects as go
    
    # Extract values from flow_metrics
    bakrep_count = flow_metrics['inputs'].get('bakrep', 0)
    refseq_count = flow_metrics['inputs'].get('refseq', 0)
    nctc_count = flow_metrics['inputs'].get('nctc', 0)
    total_input = flow_metrics['inputs'].get('total', 0)
    removed_count = flow_metrics['removed'].get('count', 0)
    non_kpsc_count = flow_metrics['klebsiella'].get('non_kpsc', 0)
    kpsc_failed = flow_metrics['qc'].get('kpsc_failed', 0)
    final_kpsc = flow_metrics['final'].get('kpsc_final_set', 0)
    
    # Define node labels with counts (n = ...)
    node_labels = [
        f'Klebsiella assemblies<br>in Bakrep<br>n = {bakrep_count:,}',                                    # 0
        f'Reference assemblies, n = {refseq_count:,}',                                 # 1
        f'Historical UK Collection, n = {nctc_count:,}',                # 2
        f'All Klebsiella<br>Assemblies<br>n = {total_input:,}',                                      # 3
        f'Evolutionary Studies<br>n = {removed_count:,}',            # 4
        f'Other Klebsiella species<br>n = {non_kpsc_count:,}',                                                        # 5
        f'Failed QC<br>n = {kpsc_failed:,}',                                                          # 6
        f'Klebsiella Pneumoniae Species Complex (Kpsc)<br>For Downstream Analyses<br>n = {final_kpsc:,})'  # 7
    ]
    
    # Define links: source node, target node, value
    links = []
    
    # Input sources → All Klebsiella Assemblies
    if bakrep_count > 0:
        links.append({'source': 0, 'target': 3, 'value': bakrep_count})
    if refseq_count > 0:
        links.append({'source': 1, 'target': 3, 'value': refseq_count})
    if nctc_count > 0:
        links.append({'source': 2, 'target': 3, 'value': nctc_count})
    
    # All Klebsiella Assemblies → Outputs (removed, non-KPSC, failed QC, final set)
    if removed_count > 0:
        links.append({'source': 3, 'target': 4, 'value': removed_count})
    if non_kpsc_count > 0:
        links.append({'source': 3, 'target': 5, 'value': non_kpsc_count})
    if kpsc_failed > 0:
        links.append({'source': 3, 'target': 6, 'value': kpsc_failed})
    if final_kpsc > 0:
        links.append({'source': 3, 'target': 7, 'value': final_kpsc})
    
    # Define node positions (x, y coordinates)
    # x: 0 = left, 1 = right
    # y: 0 = top, 1 = bottom
    # Position "Failed QC" and "Removed Studies" closer to middle node (not fully aligned with outputs)
    node_x = [
        0.0,   # 0: Bakrep (left)
        0.0,   # 1: Refseq (left)
        0.0,   # 2: NCTC (left)
        0.5,   # 3: All Klebsiella Assemblies (middle)
        0.8,  # 4: Removed Studies (closer to middle, not fully right)
        1.0,   # 5: Non-KPSC (right)
        0.8,  # 6: Failed QC (closer to middle, not fully right)
        1.0    # 7: Final KPSC Set (right)
    ]
    node_y = [
        0.2,   # 0: Bakrep
        0.5,   # 1: Refseq
        0.8,   # 2: NCTC
        0.6,   # 3: All Klebsiella Assemblies (center)
        0.01,   # 4: Removed Studies (top)
        0.2,   # 5: Non-KPSC (top-right)
        0.1,   # 6: Failed QC (bottom)
        0.7    # 7: Final KPSC Set (bottom-right)
    ]
    
    # Create Sankey diagram
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=20,
            thickness=25,
            line=dict(color="black", width=0.5),
            label=node_labels,
            x=node_x,
            y=node_y,
            color=[
                '#8B0000',  # Bakrep - Maroon
                '#800000',  # Refseq - Dark maroon
                '#DC143C',  # NCTC - Red
                '#800080',  # All Klebsiella Assemblies - Purple
                '#000000',  # Removed Studies - Black
                '#4682B4',  # Non-KPSC - Steel blue
                '#4D4D4D',  # Failed QC - Dark grey
                '#00008B'   # Final KPSC Set - Dark blue
            ]
        ),
        link=dict(
            source=[link['source'] for link in links],
            target=[link['target'] for link in links],
            value=[link['value'] for link in links]
        ),
        textfont=dict(color='black', size=11)
    )])
    
    fig.update_layout(
        title={
            'text': "Evolution and Pathoadaption Klebsiella - Study Pipeline",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'color': 'black'}
        },
        font=dict(size=11, color='black'),
        height=800,
        width=1400,
        paper_bgcolor='#FAFAFA',  # Pale grey background
        plot_bgcolor='#FAFAFA'    # Pale grey background
    )
    
    # Save as HTML
    html_path = os.path.join(output_dir, 'qc_flow_sankey.html')
    fig.write_html(html_path)
    print(f"Sankey diagram (HTML) saved to: {html_path}")
    
    # Try to save as PNG (requires kaleido)
    try:
        png_path = os.path.join(output_dir, 'qc_flow_sankey.png')
        fig.write_image(png_path, width=1400, height=800)
        print(f"Sankey diagram (PNG) saved to: {png_path}")
    except Exception as e:
        print(f"Note: Could not save PNG image: {e}")
        print("  (This is optional - HTML version is available)")


def run_metadata_qc_integration(
    input_file: str = None,
    qc_excel_path: str = QC_EXCEL_FILE,
    output_dir: str = OUTPUT_DIR,
    output_file: str = "qc_final_with_metadata.tsv",
) -> None:
    """
    Orchestrate the QC integration workflow.
    
    This function performs the following steps:
    1. Loads intermediate metadata (with Refseq and NCTC data already imported)
    2-8. Builds unified QC data (kleborate + bakrep + flags) - via build_qc_data()
    9. Joins metadata to QC data (QC-centric left join)
    10a. Reports metadata samples not in QC (removed from final dataset)
    10b. Reports QC samples not in metadata (kept but no metadata enrichment)
    11. Fills empty metadata columns from bakrep
    12. Validates and summarizes
    13. Writes final QC dataset with metadata
    
    Parameters:
    -----------
    input_file : str
        Path to intermediate metadata file (intermediate_collated_metadata_wo_qc_or_kleborate.tsv)
        If None, uses default path in output_dir
    qc_excel_path : str
        Path to the QC Excel file (default: QC_EXCEL_FILE)
    output_dir : str
        Directory to write output files (default: OUTPUT_DIR)
    output_file : str
        Filename for final output file (default: 'qc_final_with_metadata.tsv'). 
        Will be written to output_dir.
    """
    # Set up logging to both file and console
    log_file_path = os.path.join(output_dir, "metadata_qc_integration.log")
    os.makedirs(output_dir, exist_ok=True)
    original_stdout = sys.stdout
    tee_output = TeeOutput(log_file_path)
    sys.stdout = tee_output
    
    try:
        print("Starting QC integration workflow...")
        print("Configuration:")
        if input_file is None:
            input_file = os.path.join(output_dir, 'intermediate_collated_metadata_wo_qc_or_kleborate.tsv')
        print(f"  Input file: {input_file}")
        print(f"  QC Excel file: {qc_excel_path}")
        print(f"  Output directory: {output_dir}")
        print(f"  Google Sheet ID: {STUDY_METADATA_GOOGLE_SHEET_ID}")
        print("  (Studies to remove loaded from 'removed_studies' sheet)\n")
        
        # Step 1: Load intermediate metadata
        print("\n" + "="*80)
        print("STEP 1: LOADING INTERMEDIATE METADATA")
        print("="*80)
        try:
            metadata = pd.read_csv(input_file, sep='\t', low_memory=False)
            print(f"Loaded {len(metadata)} rows from {os.path.basename(input_file)}")
            print(f"Unique samples: {metadata['sample_accession'].nunique()}")
        except FileNotFoundError:
            print(f"ERROR: Input file not found: {input_file}")
            print("Please run metadata_collation.py first to generate the intermediate file.")
            raise
        except Exception as e:
            print(f"ERROR reading input file: {type(e).__name__}: {e}")
            raise
        
        # Steps 2-9: Build QC data and join metadata (calls build_qc_data internally)
        combined_data, flow_metrics = join_qc_data(metadata, qc_excel_path)
        
        # Step 10a: Report unmatched metadata samples (in metadata but NOT in QC)
        # Extract QC samples from combined_data (no need to rebuild QC data)
        qc_samples = set(combined_data['Sample'].dropna().unique())
        report_unmatched_metadata_samples(metadata, qc_samples, output_dir)
        
        # Step 10b: Report unmatched QC samples (in QC but NOT in metadata)
        # NOTE: Must run BEFORE STEP 11 which fills study_accession from bakrep
        report_unmatched_qc_samples(combined_data, output_dir)
        
        # Step 11: Fill empty metadata columns from bakrep
        print("\n" + "="*80)
        print("STEP 11: FILLING METADATA FROM BAKREP")
        print("="*80)
        combined_data = add_bakrep_metadata(combined_data)
        
        # Step 12: Validate and summarize
        print("\n" + "="*80)
        print("STEP 12: VALIDATION AND SUMMARY")
        print("="*80)
        print(f"Final data: {len(combined_data)} rows")
        print(f"Unique samples (Sample): {combined_data['Sample'].nunique()}")
        if 'sample_accession' in combined_data.columns:
            matched_samples = combined_data['sample_accession'].notna().sum()
            print(f"Samples matched to metadata: {matched_samples} ({matched_samples / len(combined_data) * 100:.1f}%)")
        print(f"Total columns: {len(combined_data.columns)}")
        
        if 'is_kpsc' in combined_data.columns:
            kpsc_count = combined_data['is_kpsc'].sum()
            print(f"KPSC samples (is_kpsc=TRUE): {kpsc_count} ({kpsc_count / len(combined_data) * 100:.1f}%)")
        
        if 'is_refseq' in combined_data.columns:
            refseq_count = combined_data['is_refseq'].sum()
            print(f"Refseq samples (is_refseq=TRUE): {refseq_count} ({refseq_count / len(combined_data) * 100:.1f}%)")
        
        if 'is_nctc' in combined_data.columns:
            nctc_count = combined_data['is_nctc'].sum()
            print(f"NCTC samples (is_nctc=TRUE): {nctc_count} ({nctc_count / len(combined_data) * 100:.1f}%)")
        
        if 'kpsc_final_list' in combined_data.columns:
            final_list_count = combined_data['kpsc_final_list'].sum()
            print(f"kpsc_final_list=TRUE: {final_list_count} ({final_list_count / len(combined_data) * 100:.1f}%)")
        
        # Step 13: Write final outputs
        print("\n" + "="*80)
        print("STEP 13: WRITING FINAL OUTPUTS")
        print("="*80)
        
        final_metadata_path = os.path.join(output_dir, output_file)
        combined_data.to_csv(final_metadata_path, sep='\t', index=False)
        print(f"Final QC data with metadata written to: {final_metadata_path}")
        print(f"  Rows: {len(combined_data)}")
        print(f"  Unique samples: {combined_data['Sample'].nunique()}")
        print(f"  Columns: {len(combined_data.columns)}")
        
        # Generate enhanced QC summary and Sankey diagram
        print("\n" + "="*80)
        print("GENERATING ENHANCED SUMMARY AND VISUALIZATIONS")
        print("="*80)
        generate_enhanced_qc_summary(flow_metrics, combined_data, output_dir)
        generate_sankey_diagram(flow_metrics, output_dir)
        
        # Save flow_metrics to JSON file for standalone plotting
        import json
        
        # Convert numpy int64 to Python int for JSON serialization
        def convert_to_serializable(obj):
            """Recursively convert numpy types to Python native types."""
            if isinstance(obj, dict):
                return {key: convert_to_serializable(value) for key, value in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [convert_to_serializable(item) for item in obj]
            elif hasattr(obj, 'item'):  # numpy scalar types
                return obj.item()
            else:
                return obj
        
        flow_metrics_serializable = convert_to_serializable(flow_metrics)
        
        flow_metrics_path = os.path.join(output_dir, 'flow_metrics.json')
        with open(flow_metrics_path, 'w', encoding='utf-8') as f:
            json.dump(flow_metrics_serializable, f, indent=2)
        print(f"Flow metrics saved to: {flow_metrics_path}")
        print("  (Use plot_study_sankey.py to regenerate Sankey diagram without reprocessing)")
        print("="*80 + "\n")
        
        print("QC integration complete.")
    finally:
        # Restore stdout and close log file
        sys.stdout = original_stdout
        tee_output.close()
        print(f"Log file written to: {log_file_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Add QC data to collated metadata (kleborate, FINAL_LIST, KPSC flag, filtering)'
    )
    
    parser.add_argument(
        '--input-file',
        type=str,
        default=None,
        help='Path to intermediate metadata file (intermediate_collated_metadata_wo_qc_or_kleborate.tsv). If not provided, uses default path in output_dir.'
    )
    parser.add_argument(
        '--qc-excel-path',
        type=str,
        default=QC_EXCEL_FILE,
        help=f'Path to QC Excel file (default: {QC_EXCEL_FILE})'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=OUTPUT_DIR,
        help=f'Directory to write output files (default: {OUTPUT_DIR})'
    )
    parser.add_argument(
        '--output-file',
        type=str,
        default="qc_final_with_metadata.tsv",
        help='Path to final output file. If not provided, uses qc_final_with_metadata.tsv in output_dir.'
    )
    
    args = parser.parse_args()
    
    run_metadata_qc_integration(
        input_file=args.input_file,
        qc_excel_path=args.qc_excel_path,
        output_dir=args.output_dir,
        output_file=args.output_file,
    )




