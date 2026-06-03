#!/usr/bin/env python3
"""
Standalone script to parse and categorize host data from metadata.

This script loads metadata, runs parse_host and categorise_host functions
with verbose output to help identify issues and iteratively improve the
parsing and categorization rules.

Usage:
    uv run python Klebsiella/pp/parse_and_categorise_host.py [--input FILE] [--show-uncategorized]
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import re

# Import functions from metadata_curation
from bac_metadata.pp.metadata_curation import parse_host, categorise_host, report_ena_column


def detect_latin_names(values):
    """
    Detect potential Latin binomial names in a list of values.
    
    Latin binomial names typically follow the pattern:
    - Two words
    - First word capitalized (genus)
    - Second word lowercase (species)
    - Both are alphabetic (may include hyphens)
    
    Returns list of values that match this pattern.
    """
    latin_pattern = re.compile(r'^[A-Z][a-z]+\s+[a-z]+(?:\s+[a-z]+)?$')
    latin_names = []
    
    for val in values:
        if pd.isna(val):
            continue
        val_str = str(val).strip()
        if latin_pattern.match(val_str):
            latin_names.append(val_str)
    
    return sorted(set(latin_names))


def find_uncategorized_values(df):
    """
    Find values in host_parsed that don't match any category.
    
    A value is considered "uncategorized" if:
    - host_parsed is not null
    - host_category == host_parsed (meaning no categorization rule matched)
    """
    if 'host_parsed' not in df.columns or 'host_category' not in df.columns:
        return []
    
    # Find rows where categorization didn't change the value
    mask = (df['host_parsed'].notna() & 
            (df['host_parsed'] == df['host_category']))
    
    uncategorized = df.loc[mask, 'host_parsed'].value_counts()
    return uncategorized


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Parse and categorize host data from metadata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Use default metadata file
    uv run python Klebsiella/pp/parse_and_categorise_host.py
    
    # Specify custom metadata file
    uv run python Klebsiella/pp/parse_and_categorise_host.py --input /path/to/metadata.tsv
    
    # Show only uncategorized values summary
    uv run python Klebsiella/pp/parse_and_categorise_host.py --show-uncategorized
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        default="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/metadata/intermediate_collated_metadata_wo_qc_or_kleborate.tsv",
        help='Path to metadata TSV file'
    )
    
    parser.add_argument(
        '--show-uncategorized',
        action='store_true',
        help='Show only uncategorized values summary (skip verbose parsing output)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading metadata from:\n  {input_path}")
    df = pd.read_csv(input_path, sep="\t", low_memory=False)
    print(f"Total rows loaded: {len(df):,}")
    
    if 'host' not in df.columns:
        print("Error: 'host' column not found in metadata", file=sys.stderr)
        sys.exit(1)
    
    # Show initial host statistics
    print("\n" + "=" * 60)
    print("Initial Host Column Statistics")
    print("=" * 60)
    print(f"Total hosts present: {df['host'].notna().sum():,}")
    print(f"Total hosts missing: {df['host'].isna().sum():,}")
    print(f"Unique host values: {df['host'].nunique()}")
    
    # Run parsing with verbose output (unless --show-uncategorized is set)
    verbose = not args.show_uncategorized
    
    print("\n" + "=" * 60)
    print("Running Host Parsing and Categorization")
    print("=" * 60)
    
    df = parse_host(df, verbose=verbose)
    
    # Note: parse_host already calls categorise_host internally,
    # so we don't need to call it again
    
    # Summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    
    print(f"\nOriginal 'host' column:")
    print(f"  Unique values: {df['host'].nunique()}")
    
    if 'host_parsed' in df.columns:
        print(f"\nParsed 'host_parsed' column:")
        print(f"  Unique values: {df['host_parsed'].nunique()}")
    
    if 'host_category' in df.columns:
        print(f"\nCategorized 'host_category' column:")
        print(f"  Unique values: {df['host_category'].nunique()}")
    
    # Find and display uncategorized values
    print("\n" + "=" * 60)
    print("UNCATEGORIZED VALUES")
    print("=" * 60)
    print("\nValues in 'host_parsed' that were not categorized:")
    print("(i.e., where host_parsed == host_category)\n")
    
    uncategorized = find_uncategorized_values(df)
    if len(uncategorized) > 0:
        print(f"Found {len(uncategorized)} unique uncategorized values:\n")
        for val, count in uncategorized.items():
            print(f"  {val}: {count:,} samples")
    else:
        print("All values were successfully categorized!")
    
    # Detect Latin names in host_parsed
    print("\n" + "=" * 60)
    print("POTENTIAL LATIN NAMES IN host_parsed")
    print("=" * 60)
    
    if 'host_parsed' in df.columns:
        unique_parsed = df['host_parsed'].dropna().unique()
        latin_names = detect_latin_names(unique_parsed)
        
        if latin_names:
            print(f"\nFound {len(latin_names)} potential Latin binomial names:")
            for name in latin_names:
                count = (df['host_parsed'] == name).sum()
                print(f"  {name}: {count:,} samples")
        else:
            print("\nNo Latin binomial names detected in host_parsed.")
    
    # Detect Latin names in original host column
    print("\n" + "=" * 60)
    print("POTENTIAL LATIN NAMES IN ORIGINAL host")
    print("=" * 60)
    
    unique_host = df['host'].dropna().unique()
    latin_names_original = detect_latin_names(unique_host)
    
    if latin_names_original:
        print(f"\nFound {len(latin_names_original)} potential Latin binomial names in original host column:")
        for name in latin_names_original:
            count = (df['host'] == name).sum()
            print(f"  {name}: {count:,} samples")
    else:
        print("\nNo Latin binomial names detected in original host column.")
    
    print("\n" + "=" * 60)
    print("Analysis complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
