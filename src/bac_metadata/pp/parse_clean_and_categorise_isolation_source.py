#!/usr/bin/env python3
"""
Standalone script to identify uncategorized isolation_source values.

This script loads metadata, runs parse_isolation_source and categorise_isolation_source functions,
then shows the top 50 uncategorized values for iterative improvement.

Usage:
    uv run python Klebsiella/pp/parse_clean_and_categorise_isolation_source.py [--input FILE] [--top N]
"""

import argparse
import sys
from pathlib import Path
import pandas as pd

# Import functions from metadata_curation
from bac_metadata.pp.metadata_curation import (
    parse_isolation_source, 
    categorise_isolation_source
)


def find_uncategorized_values(df):
    """
    Find values in isolation_source_parsed that don't match any category.
    
    A value is considered "uncategorized" if:
    - isolation_source_parsed is not null
    - isolation_source_category == isolation_source_parsed (meaning no categorization rule matched)
    - EXCEPT when the value is already a valid category name (like "blood")
    - EXCEPT when the value is a known placeholder/unhelpful category
    """
    if 'isolation_source_parsed' not in df.columns or 'isolation_source_category' not in df.columns:
        return pd.Series(dtype=int)
    
    # Define valid category names that should not be flagged as uncategorized
    valid_categories = {
        'blood',
        'urine, urinary catheter',
        'upper airway',
        'lower respiratory, endotracheal',
        'faeces & rectal swabs',
        'invasive gut & organs',
        'invasive body fluid (pericardial, synovial, CSF)',
        'body fluid (ascites / peritoneal / pleural)',
        'wound & pus, abscess, surgical drain, body tissue, bone, biopsy',
        'surface swabs (skin, groin, vaginal, genital, eye, ear)',
        'clinical environment or surface',
        'wastewater & water',
        'birds (other)',
        'animals (other)',
        'grazing livestock',
        'poultry livestock',
        'domestic dogs and cats',
        'food',
        'vegetable, plant or soil',
        'insect',
        'lab, hospital or facility (unhelpful)'
    }
    
    # Known placeholder/unhelpful categories that are intentionally vague
    known_placeholders = {
        'patient (unhelpful)',
        'other (not specified)',
        'swab (not specified)',
        'aspirate (not specified)',
        'catheter (not specified)',
        'clinical isolate (unhelpful)',
        'insect'  # generic insect category
    }
    
    # Combine both sets
    exclude_from_uncategorized = valid_categories | known_placeholders
    
    # Find rows where categorization didn't change the value
    # AND the value is not in the exclude list
    mask = (df['isolation_source_parsed'].notna() & 
            (df['isolation_source_parsed'] == df['isolation_source_category']) &
            (~df['isolation_source_parsed'].isin(exclude_from_uncategorized)))
    
    uncategorized = df.loc[mask, 'isolation_source_parsed'].value_counts()
    return uncategorized


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Identify uncategorized isolation_source values',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Show top 50 uncategorized values
    uv run python Klebsiella/pp/parse_clean_and_categorise_isolation_source.py
    
    # Show top 100
    uv run python Klebsiella/pp/parse_clean_and_categorise_isolation_source.py --top 100
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        default="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/metadata/intermediate_collated_metadata_wo_qc_or_kleborate.tsv",
        help='Path to metadata TSV file'
    )
    
    parser.add_argument(
        '--top',
        type=int,
        default=50,
        help='Number of top uncategorized values to show (default: 50)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading metadata from: {input_path.name}")
    df = pd.read_csv(input_path, sep="\t", low_memory=False)
    print(f"Total rows: {len(df):,}\n")
    
    if 'isolation_source' not in df.columns:
        print("Error: 'isolation_source' column not found in metadata", file=sys.stderr)
        sys.exit(1)
    
    # Run parsing and categorization (suppress verbose output)
    print("Running isolation_source parsing and categorization...")
    df = parse_isolation_source(df, verbose=False)
    
    # Find uncategorized values
    uncategorized = find_uncategorized_values(df)
    
    if len(uncategorized) == 0:
        print("\nAll values were successfully categorized!")
        return
    
    print(f"\nFound {len(uncategorized):,} unique uncategorized values")
    print(f"Total uncategorized samples: {uncategorized.sum():,}")
    print(f"\nTop {min(args.top, len(uncategorized))} uncategorized values:\n")
    print("=" * 80)
    
    # Display top N uncategorized values, one per line
    for value, count in uncategorized.head(args.top).items():
        print(f"{value}: {count:,}")
    
    if len(uncategorized) > args.top:
        remaining = len(uncategorized) - args.top
        remaining_count = uncategorized.iloc[args.top:].sum()
        print(f"\n... and {remaining:,} more values ({remaining_count:,} samples)")
    
    print("=" * 80)


if __name__ == "__main__":
    main()
