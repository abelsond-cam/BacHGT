#!/usr/bin/env python3
"""
Reconcile host_category and isolation_source_category for consistency checking.

This script loads metadata, runs parsing and categorization for both host and isolation_source,
then displays all unique isolation_source_category values for each host_category.
This helps identify non-sensical combinations (e.g., human host with animal isolation sources).

Usage:
    uv run python Klebsiella/pp/reconcile_host_with_isolation_source.py [--input FILE]
"""

import argparse
import sys
from pathlib import Path
import pandas as pd

# Import functions from metadata_curation
from bac_metadata.pp.metadata_curation import (
    parse_host,
    categorise_host,
    parse_isolation_source,
    categorise_isolation_source,
    reconcile_host_and_isolation_source
)


def analyze_host_isolation_source_combinations(df):
    """
    Analyze combinations of host_category and isolation_source_category.
    
    Returns a dictionary mapping each host_category to a dictionary of
    isolation_source_category counts.
    """
    if 'host_category' not in df.columns or 'isolation_source_category' not in df.columns:
        return {}
    
    # Group by host_category and isolation_source_category
    combinations = {}
    
    # Get all unique host categories (including NA)
    host_categories = df['host_category'].unique()
    
    # Separate NA and non-NA values for sorting
    na_values = [x for x in host_categories if pd.isna(x)]
    non_na_values = [x for x in host_categories if pd.notna(x)]
    
    # Sort non-NA values and put NA at the end
    sorted_categories = sorted(non_na_values) + na_values
    
    for host_cat in sorted_categories:
        # Filter to this host category
        host_mask = df['host_category'] == host_cat if pd.notna(host_cat) else df['host_category'].isna()
        host_df = df[host_mask]
        
        # Get isolation_source_category counts for this host
        isolation_counts = host_df['isolation_source_category'].value_counts(dropna=False)
        
        combinations[host_cat] = {
            'total_samples': len(host_df),
            'isolation_source_counts': isolation_counts.to_dict()
        }
    
    return combinations


def display_combinations(combinations, df):
    """
    Display the host-isolation source combinations in a readable format.
    """
    print("\n" + "=" * 80)
    print("HOST-ISOLATION SOURCE RECONCILIATION REPORT")
    print("=" * 80)
    print(f"\nTotal samples in dataset: {len(df):,}\n")
    
    for host_cat, data in combinations.items():
        total_samples = data['total_samples']
        isolation_counts = data['isolation_source_counts']
        
        # Handle NA host category
        host_display = "Missing/NA" if pd.isna(host_cat) else host_cat
        
        print("\n" + "-" * 80)
        print(f"HOST CATEGORY: {host_display}")
        print(f"Total samples: {total_samples:,} ({100 * total_samples / len(df):.1f}%)")
        print("-" * 80)
        
        if not isolation_counts:
            print("  No isolation sources found")
            continue
        
        # Consolidate all NA types into a single count
        consolidated_counts = {}
        na_total = 0
        
        for iso_cat, count in isolation_counts.items():
            if pd.isna(iso_cat):
                na_total += count
            else:
                consolidated_counts[iso_cat] = count
        
        # Add consolidated NA count if any
        if na_total > 0:
            consolidated_counts["Missing/NA"] = na_total
        
        # Sort consolidated counts by count (descending)
        sorted_iso = sorted(consolidated_counts.items(), key=lambda x: x[1], reverse=True)
        
        print(f"\n  {'Isolation Source Category':<60} {'Count':>10} {'%':>8}")
        print(f"  {'-' * 60} {'-' * 10} {'-' * 8}")
        
        for iso_cat, count in sorted_iso:
            percentage = 100 * count / total_samples
            print(f"  {iso_cat:<60} {count:>10,} {percentage:>7.1f}%")


def examine_nonsensical_combination(df, host_category_value, isolation_source_category_value, max_examples=50):
    """
    Examine original unparsed values for a specific host-isolation source combination.
    
    Useful for diagnosing why certain non-sensical combinations exist.
    
    Supports both exact and partial (substring/contains) matching for convenience:
    - Exact match: "human" matches only "human"
    - Partial match: "clinical" matches "clinical environment or surface"
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with host, host_category, isolation_source, isolation_source_category columns
    host_category_value : str
        The host_category value to filter by (e.g., "insect" or "human")
        Supports partial matching - will try exact match first, then substring match
    isolation_source_category_value : str
        The isolation_source_category value to filter by (e.g., "clinical" matches "clinical environment or surface")
        Supports partial matching - will try exact match first, then substring match
    max_examples : int, default=50
        Maximum number of examples to display
    """
    # Build mask with smart matching (try exact first, fall back to substring/contains)
    # Host category mask
    if (df['host_category'] == host_category_value).any():
        # Exact match found
        host_mask = df['host_category'] == host_category_value
        host_match_type = "exact"
        actual_host_cat = host_category_value
    elif df['host_category'].str.contains(host_category_value, case=False, na=False).any():
        # Substring match found
        host_mask = df['host_category'].str.contains(host_category_value, case=False, na=False)
        host_match_type = "partial"
        # Get actual matching values
        actual_host_cat = df.loc[host_mask, 'host_category'].unique()[0] if host_mask.sum() > 0 else host_category_value
    else:
        # No match
        host_mask = df['host_category'] == host_category_value  # Will be empty
        host_match_type = "none"
        actual_host_cat = host_category_value
    
    # Isolation source category mask
    if (df['isolation_source_category'] == isolation_source_category_value).any():
        # Exact match found
        iso_mask = df['isolation_source_category'] == isolation_source_category_value
        iso_match_type = "exact"
        actual_iso_cat = isolation_source_category_value
    elif df['isolation_source_category'].str.contains(isolation_source_category_value, case=False, na=False).any():
        # Substring match found
        iso_mask = df['isolation_source_category'].str.contains(isolation_source_category_value, case=False, na=False)
        iso_match_type = "partial"
        # Get actual matching values
        actual_iso_cat = ", ".join(df.loc[iso_mask, 'isolation_source_category'].dropna().unique()[:3])
    else:
        # No match
        iso_mask = df['isolation_source_category'] == isolation_source_category_value  # Will be empty
        iso_match_type = "none"
        actual_iso_cat = isolation_source_category_value
    
    # Combine masks
    mask = host_mask & iso_mask
    matching = df[mask]
    
    # Display results
    print("\n" + "=" * 80)
    print(f"EXAMINING COMBINATION")
    print("=" * 80)
    print(f"\nHost Category: '{host_category_value}' ({host_match_type} match)")
    if host_match_type == "partial":
        print(f"  → Matched: '{actual_host_cat}'")
    print(f"\nIsolation Source Category: '{isolation_source_category_value}' ({iso_match_type} match)")
    if iso_match_type == "partial":
        print(f"  → Matched: {actual_iso_cat}")
    print(f"\nTotal matching samples: {len(matching):,}")
    
    if len(matching) == 0:
        print("\nNo matching samples found.")
        return
    
    # Show the full pipeline: isolation_source → isolation_source_parsed → isolation_source_category
    print("\n" + "-" * 120)
    print("ISOLATION SOURCE PIPELINE (showing how original values are parsed and categorized):")
    print("-" * 120)
    print(f"{'Original isolation_source':<40} | {'Parsed → isolation_source_parsed':<40} | {'Categorized → isolation_source_category':<35}")
    print("-" * 120)
    
    # Get unique combinations of the three columns
    pipeline_cols = ['isolation_source', 'isolation_source_parsed', 'isolation_source_category']
    pipeline_combos = matching[pipeline_cols].value_counts(dropna=False).head(max_examples)
    
    for (orig, parsed, cat), count in pipeline_combos.items():
        orig_display = "Missing/NA" if pd.isna(orig) else str(orig)[:39]
        parsed_display = "Missing/NA" if pd.isna(parsed) else str(parsed)[:39]
        cat_display = "Missing/NA" if pd.isna(cat) else str(cat)[:34]
        print(f"{orig_display:<40} | {parsed_display:<40} | {cat_display:<35} ({count:,})")
    
    if len(pipeline_combos) >= max_examples:
        remaining = len(matching[pipeline_cols].value_counts(dropna=False)) - max_examples
        if remaining > 0:
            print(f"\n... and {remaining} more unique combinations")
    
    print("\n" + "=" * 120 + "\n")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Reconcile host_category and isolation_source_category for consistency',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Use default metadata file
    uv run python Klebsiella/pp/reconcile_host_with_isolation_source.py
    
    # Specify custom metadata file
    uv run python Klebsiella/pp/reconcile_host_with_isolation_source.py --input /path/to/metadata.tsv
    
    # Examine a specific non-sensical combination
    uv run python Klebsiella/pp/reconcile_host_with_isolation_source.py --examine "insect" "patient (unhelpful)"
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        default="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/metadata/qc_final_with_metadata.tsv",
        help='Path to metadata TSV file'
    )
    
    parser.add_argument(
        '--examine',
        nargs=2,
        metavar=('HOST_CATEGORY', 'ISOLATION_SOURCE_CATEGORY'),
        help='Examine original values for a specific combination (e.g., --examine "insect" "patient (unhelpful)")'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading metadata from:\n  {input_path.name}")
    df = pd.read_csv(input_path, sep="\t", low_memory=False)
    print(f"Total rows loaded: {len(df):,}")
    
    # Check required columns
    if 'host' not in df.columns:
        print("Error: 'host' column not found in metadata", file=sys.stderr)
        sys.exit(1)
    
    if 'isolation_source' not in df.columns:
        print("Error: 'isolation_source' column not found in metadata", file=sys.stderr)
        sys.exit(1)
    
    # Run parsing and categorization (suppress verbose output)
    print("\n" + "=" * 80)
    print("PROCESSING HOST AND ISOLATION SOURCE")
    print("=" * 80)
    print("\nRunning host parsing and categorization...")
    df = parse_host(df, verbose=False)
    # Note: parse_host already calls categorise_host internally
    
    print("Running isolation_source parsing and categorization...")
    df = parse_isolation_source(df, verbose=False)
    df = categorise_isolation_source(df, verbose=False)
    
    print("\nApplying reconciliation fixes...")
    df = reconcile_host_and_isolation_source(df, verbose=True)
    
    # Check if examination mode is requested
    if args.examine:
        host_cat, iso_cat = args.examine
        examine_nonsensical_combination(df, host_cat, iso_cat)
    else:
        # Analyze combinations
        print("\nAnalyzing host-isolation source combinations...")
        combinations = analyze_host_isolation_source_combinations(df)
        
        # Display results
        display_combinations(combinations, df)
        
        print("\n" + "=" * 80)
        print("Analysis complete!")
        print("=" * 80)
        print("\nReview the combinations above to identify non-sensical pairings.")
        print("For example:")
        print("  - Human hosts should not have animal isolation sources")
        print("  - Animal hosts should not have human clinical sources (blood, urine, etc.)")
        print("  - Environmental hosts should have environmental isolation sources")
        print("\nTo examine a specific combination, use:")
        print("  --examine \"host_category\" \"isolation_source_category\"")
        print("\n")


if __name__ == "__main__":
    main()
