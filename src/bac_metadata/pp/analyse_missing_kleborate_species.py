#!/usr/bin/env python3
"""
Analyze missing Kleborate species data in metadata_final_curated_slimmed.tsv

This script examines rows that don't have an entry in the 'species' column and reports:
- Total count of rows with missing species
- How many have 'klebsiella' in both gtdbtk.classification.species and scientific_name
- How many have matching gtdbtk.classification.species and scientific_name
- Analysis of discarded samples and their top values
"""

import pandas as pd
import sys
from pathlib import Path


def analyze_missing_species(metadata_file: str, output_file: str = None):
    """
    Analyze rows with missing species data.
    
    Args:
        metadata_file: Path to metadata_final_curated_slimmed.tsv
        output_file: Path to output TSV file for missing species rows (optional)
    """
    print("=" * 80)
    print("Analysis of Missing Kleborate Species Data")
    print("=" * 80)
    print(f"\nReading metadata from: {metadata_file}")
    
    # Read the metadata file
    df = pd.read_csv(metadata_file, sep="\t", low_memory=False)
    total_rows = len(df)
    print(f"Total rows in dataset: {total_rows:,}")
    
    # Find rows with missing species
    missing_species_mask = df['species'].isna() | (df['species'] == '') | (df['species'].str.strip() == '')
    missing_species_df = df[missing_species_mask].copy()
    n_missing = len(missing_species_df)
    
    print("\n" + "-" * 80)
    print("MISSING SPECIES ANALYSIS")
    print("-" * 80)
    print(f"Rows with missing 'species': {n_missing:,} ({n_missing/total_rows*100:.2f}%)")
    
    if n_missing == 0:
        print("\nNo rows with missing species found. Analysis complete.")
        return
    
    # Check for 'klebsiella' in both gtdbtk.classification.species and scientific_name
    print("\n" + "-" * 80)
    print("KLEBSIELLA PRESENCE ANALYSIS")
    print("-" * 80)
    
    # Helper function to check if 'klebsiella' is present (case-insensitive)
    def contains_klebsiella(value):
        if pd.isna(value):
            return False
        return 'klebsiella' in str(value).lower()
    
    # Check gtdbtk.classification.species
    bakta_has_kleb = missing_species_df['gtdbtk.classification.species'].apply(contains_klebsiella)
    n_bakta_kleb = bakta_has_kleb.sum()
    
    # Check scientific_name
    sciname_has_kleb = missing_species_df['scientific_name'].apply(contains_klebsiella)
    n_sciname_kleb = sciname_has_kleb.sum()
    
    # Both contain 'klebsiella'
    both_kleb = bakta_has_kleb & sciname_has_kleb
    n_both_kleb = both_kleb.sum()
    
    print(f"Rows where 'gtdbtk.classification.species' contains 'klebsiella': {n_bakta_kleb:,} ({n_bakta_kleb/n_missing*100:.2f}%)")
    print(f"Rows where 'scientific_name' contains 'klebsiella': {n_sciname_kleb:,} ({n_sciname_kleb/n_missing*100:.2f}%)")
    print(f"Rows where BOTH contain 'klebsiella': {n_both_kleb:,} ({n_both_kleb/n_missing*100:.2f}%)")
    
    # Check how many have matching gtdbtk.classification.species and scientific_name
    print("\n" + "-" * 80)
    print("FIELD MATCHING ANALYSIS")
    print("-" * 80)
    
    # Compare gtdbtk.classification.species and scientific_name
    def fields_match(row):
        bakta = row['gtdbtk.classification.species']
        sciname = row['scientific_name']
        
        # Both must be non-null to match
        if pd.isna(bakta) or pd.isna(sciname):
            return False
        
        # Case-insensitive comparison after stripping whitespace
        return str(bakta).strip().lower() == str(sciname).strip().lower()
    
    matching_fields = missing_species_df.apply(fields_match, axis=1)
    n_matching = matching_fields.sum()
    
    print(f"Rows where 'gtdbtk.classification.species' == 'scientific_name': {n_matching:,} ({n_matching/n_missing*100:.2f}%)")
    
    # Among those with matching fields, how many contain 'klebsiella'?
    matching_with_kleb = matching_fields & both_kleb
    n_matching_with_kleb = matching_with_kleb.sum()
    
    if n_matching > 0:
        print(f"  Of these matching rows, {n_matching_with_kleb:,} ({n_matching_with_kleb/n_matching*100:.2f}%) contain 'klebsiella' in both")
    
    # Analyze top values
    print("\n" + "-" * 80)
    print("TOP VALUES ANALYSIS")
    print("-" * 80)
    
    print("\nTop 10 'gtdbtk.classification.species' values (in missing species rows):")
    bakta_counts = missing_species_df['gtdbtk.classification.species'].value_counts().head(10)
    for value, count in bakta_counts.items():
        percentage = count / n_missing * 100
        print(f"  {value!r}: {count:,} ({percentage:.2f}%)")
    
    print("\nTop 10 'scientific_name' values (in missing species rows):")
    sciname_counts = missing_species_df['scientific_name'].value_counts().head(10)
    for value, count in sciname_counts.items():
        percentage = count / n_missing * 100
        print(f"  {value!r}: {count:,} ({percentage:.2f}%)")
    
    # Analyze "discarded" samples (those with species != missing)
    print("\n" + "-" * 80)
    print("DISCARDED SAMPLES ANALYSIS (rows WITH species)")
    print("-" * 80)
    
    has_species_df = df[~missing_species_mask].copy()
    n_has_species = len(has_species_df)
    
    print(f"Rows with 'species' populated: {n_has_species:,} ({n_has_species/total_rows*100:.2f}%)")
    
    # Check klebsiella presence in discarded samples
    bakta_has_kleb_discarded = has_species_df['gtdbtk.classification.species'].apply(contains_klebsiella)
    n_bakta_kleb_discarded = bakta_has_kleb_discarded.sum()
    
    sciname_has_kleb_discarded = has_species_df['scientific_name'].apply(contains_klebsiella)
    n_sciname_kleb_discarded = sciname_has_kleb_discarded.sum()
    
    both_kleb_discarded = bakta_has_kleb_discarded & sciname_has_kleb_discarded
    n_both_kleb_discarded = both_kleb_discarded.sum()
    
    print(f"\nAmong discarded (WITH species) samples:")
    print(f"  'gtdbtk.classification.species' contains 'klebsiella': {n_bakta_kleb_discarded:,} ({n_bakta_kleb_discarded/n_has_species*100:.2f}%)")
    print(f"  'scientific_name' contains 'klebsiella': {n_sciname_kleb_discarded:,} ({n_sciname_kleb_discarded/n_has_species*100:.2f}%)")
    print(f"  BOTH contain 'klebsiella': {n_both_kleb_discarded:,} ({n_both_kleb_discarded/n_has_species*100:.2f}%)")
    
    print("\nTop 10 'species' values (in rows WITH species):")
    species_counts = has_species_df['species'].value_counts().head(10)
    for value, count in species_counts.items():
        percentage = count / n_has_species * 100
        print(f"  {value!r}: {count:,} ({percentage:.2f}%)")
    
    # Write output file if requested
    if output_file:
        print("\n" + "-" * 80)
        print("WRITING OUTPUT FILE")
        print("-" * 80)
        
        # Select columns to output
        output_columns = ['Sample', 'gtdbtk.classification.species', 'scientific_name']
        
        # Check which columns exist
        existing_output_cols = [col for col in output_columns if col in missing_species_df.columns]
        missing_output_cols = [col for col in output_columns if col not in missing_species_df.columns]
        
        if missing_output_cols:
            print(f"Warning: Some requested columns not found in data: {missing_output_cols}")
        
        if existing_output_cols:
            # Create output directory if it doesn't exist
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to file
            missing_species_df[existing_output_cols].to_csv(output_file, sep="\t", index=False)
            print(f"\nWrote {len(missing_species_df):,} rows to: {output_file}")
            print(f"Columns: {', '.join(existing_output_cols)}")
        else:
            print("Error: None of the requested columns exist in the data")
    
    print("\n" + "=" * 80)
    print("Analysis complete")
    print("=" * 80)


def main():
    """Main entry point."""
    # Default path to metadata file
    default_metadata_path = "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/final/metadata/metadata_final_curated_slimmed.tsv"
    default_output_path = "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/processed/metadata/missing_kleborate_species.tsv"
    
    # Allow command-line override
    if len(sys.argv) > 1:
        metadata_file = sys.argv[1]
    else:
        metadata_file = default_metadata_path
    
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        output_file = default_output_path
    
    # Check if file exists
    if not Path(metadata_file).exists():
        print(f"Error: File not found: {metadata_file}", file=sys.stderr)
        sys.exit(1)
    
    # Run analysis
    analyze_missing_species(metadata_file, output_file)


if __name__ == '__main__':
    main()
