#!/usr/bin/env python3
"""
Standalone script to generate completeness comparison plot.

This script compares metadata completeness across three stages:
1. Simple parsing (minimal extraction)
2. Full curation pipeline
3. Studies reviewed + curated
showing only "Usable" categories for 4 key metadata fields.
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Import curation pipeline functions
from metadata_curation import (
    parse_host,
    parse_country,
    parse_isolation_source,
    parse_collection_date,
    categorise_host,
    categorise_region,
    categorise_isolation_source,
    calculate_host_completeness,
    calculate_region_completeness,
    calculate_isolation_source_completeness,
    calculate_date_completeness,
)

# Import date parsing utilities
from date_utils import step0_clean, parse_with_pandas_and_dateutil


def calculate_simple_parsed_completeness(df):
    """
    Calculate completeness using only simple parsing methods.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Input dataframe with raw metadata
        
    Returns:
    --------
    dict : Dictionary with usable counts for each category
    """
    completeness = {}
    
    # Host: Count 'human' or 'sapiens' in host column
    if 'host' in df.columns:
        host_mask = df['host'].astype(str).str.lower().str.contains(
            'human|sapiens', case=False, na=False, regex=True
        )
        completeness['Host'] = {'usable': host_mask.sum()}
    else:
        completeness['Host'] = {'usable': 0}
    
    # Country: Count all filled values
    if 'country' in df.columns:
        country_filled = df['country'].notna().sum()
        completeness['Country'] = {'usable': country_filled}
    else:
        completeness['Country'] = {'usable': 0}
    
    # Collection Date: Apply step0_clean and parse_with_pandas_and_dateutil
    if 'collection_date' in df.columns:
        df_temp = df.copy()
        df_temp['collection_date_parsed'] = pd.NA
        df_temp['year_parsed'] = pd.NA
        step0_clean(df_temp)
        parse_with_pandas_and_dateutil(df_temp, "Simple parsing (pandas + dateutil)")
        date_parsed = df_temp['collection_date_parsed'].notna().sum()
        completeness['Collection Date'] = {'usable': date_parsed}
    else:
        completeness['Collection Date'] = {'usable': 0}
    
    # Isolation Source: Look for specific keywords
    if 'isolation_source' in df.columns:
        iso_keywords = ['blood', 'faeces', 'stool', 'rectal', 'urine', 'sputum']
        pattern = '|'.join(iso_keywords)
        iso_mask = df['isolation_source'].astype(str).str.lower().str.contains(
            pattern, case=False, na=False, regex=True
        )
        completeness['Isolation Source'] = {'usable': iso_mask.sum()}
    else:
        completeness['Isolation Source'] = {'usable': 0}
    
    return completeness


def run_curation_pipeline(df, verbose=False):
    """
    Run the complete curation pipeline on a dataframe.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Input dataframe with metadata
    verbose : bool, default=False
        Whether to print verbose output
        
    Returns:
    --------
    pd.DataFrame : Curated dataframe
    """
    print(f"Running curation pipeline on {len(df)} samples...")
    
    # Parse and categorise host
    df = parse_host(df, verbose=verbose)
    df = categorise_host(df, verbose=verbose)
    
    # Parse and categorise country/region
    df = parse_country(df, verbose=verbose)
    df = categorise_region(df, verbose=verbose)
    
    # Parse and categorise isolation source
    df = parse_isolation_source(df, verbose=verbose)
    df = categorise_isolation_source(df, verbose=verbose)
    
    # Parse collection date
    df = parse_collection_date(df, verbose=verbose)
    
    print("Curation pipeline complete.")
    return df


def calculate_all_completeness(df, top_n=6):
    """
    Calculate completeness for all 4 metadata categories.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Curated dataframe
    top_n : int, default=6
        Number of top categories for host/isolation_source
        
    Returns:
    --------
    dict : Dictionary with completeness breakdown for each category
    """
    completeness = {}
    
    # Host
    _, host_breakdown = calculate_host_completeness(df, top_n=top_n)
    completeness['Host'] = host_breakdown
    
    # Country/Region
    _, region_breakdown = calculate_region_completeness(df)
    completeness['Country'] = region_breakdown
    
    # Collection Date
    _, date_breakdown = calculate_date_completeness(df)
    completeness['Collection Date'] = date_breakdown
    
    # Isolation Source
    _, iso_breakdown = calculate_isolation_source_completeness(df, top_n=top_n)
    completeness['Isolation Source'] = iso_breakdown
    
    return completeness


def plot_completeness_comparison(parsed_completeness, curated_completeness, 
                                 post_completeness, output_path):
    """
    Generate grouped bar chart comparing usable completeness across three stages.
    
    Parameters:
    -----------
    parsed_completeness : dict
        Completeness breakdown for simple parsed data
    curated_completeness : dict
        Completeness breakdown for fully curated data
    post_completeness : dict
        Completeness breakdown for studies reviewed + curated data
    output_path : str
        Path to save the output figure
    """
    # Define categories and colors
    categories = ['Host', 'Country', 'Collection Date', 'Isolation Source']
    
    # Colors: light blue, steel blue, dark blue
    colors = ['lightblue', 'steelblue', 'darkblue']
    
    # Extract usable data for each category
    parsed_usable = [parsed_completeness[cat]['usable'] for cat in categories]
    curated_usable = [curated_completeness[cat]['usable'] for cat in categories]
    post_usable = [post_completeness[cat]['usable'] for cat in categories]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 8))
    
    x = np.arange(len(categories))
    width = 0.25
    
    # Three bars per category
    bars_parsed = ax.bar(x - width, parsed_usable, width, 
                         label='Parsed metadata', color=colors[0])
    bars_curated = ax.bar(x, curated_usable, width,
                          label='Curated metadata', color=colors[1])
    bars_post = ax.bar(x + width, post_usable, width,
                       label='Studies reviewed + curated', color=colors[2])
    
    # Add value labels on each bar
    def add_bar_labels(bars_list, values, color='black'):
        """Add value labels on top of each bar."""
        for bar, val in zip(bars_list, values):
            if val > 0:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height/2,
                       f'{int(val):,}',
                       ha='center', va='center', fontsize=9, 
                       color='white' if val > 1000 else 'black', 
                       fontweight='bold')
    
    # Add labels for all three stages
    add_bar_labels(bars_parsed, parsed_usable)
    add_bar_labels(bars_curated, curated_usable)
    add_bar_labels(bars_post, post_usable)
    
    # Formatting
    ax.set_ylabel('Number of Usable Samples', fontsize=12)
    ax.set_title('Metadata Completeness Across Processing Stages', 
                 fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Plot saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate completeness comparison plot for metadata curation'
    )
    parser.add_argument('--pre-curation-file', type=str,
        default='combined_metadata_before_collation.tsv',
        help='Pre-curation metadata filename (default: combined_metadata_before_collation.tsv)')
    parser.add_argument('--post-curation-file', type=str,
        default='metadata_final_curated.tsv',
        help='Post-curation metadata filename (default: metadata_final_curated.tsv)')
    parser.add_argument('--metadata-dir', type=str,
        default="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/processed/metadata",
        help='Directory containing metadata files')
    parser.add_argument('--output-dir', type=str,
        default="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/visualisations/metadata_curation/",
        help='Directory for saving plot')
    parser.add_argument('--top-n', type=int, default=6,
        help='Number of top categories for host/isolation_source (default: 6)')
    
    args = parser.parse_args()
    
    # Build full paths
    pre_curation_path = os.path.join(args.metadata_dir, args.pre_curation_file)
    post_curation_path = os.path.join(args.metadata_dir, args.post_curation_file)
    output_path = os.path.join(args.output_dir, 'completeness_comparison_curated.png')
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    print("=" * 60)
    print("Metadata Completeness Comparison")
    print("=" * 60)
    
    # Load post-curation data first to get sample set
    print(f"\nLoading post-curation data from:\n  {post_curation_path}")
    if not os.path.exists(post_curation_path):
        print(f"ERROR: Post-curation file not found: {post_curation_path}")
        sys.exit(1)
    
    post_df = pd.read_csv(post_curation_path, sep="\t", low_memory=False)
    print(f"Loaded {len(post_df)} samples")
    
    # Get sample_accession set from post-curation data
    if 'sample_accession' not in post_df.columns:
        print("ERROR: 'sample_accession' column not found in post-curation data")
        sys.exit(1)
    
    post_sample_set = set(post_df['sample_accession'].dropna())
    print(f"Post-curation contains {len(post_sample_set)} unique sample_accessions")
    
    # Load pre-curation data
    print(f"\nLoading pre-curation data from:\n  {pre_curation_path}")
    if not os.path.exists(pre_curation_path):
        print(f"ERROR: Pre-curation file not found: {pre_curation_path}")
        sys.exit(1)
    
    pre_df = pd.read_csv(pre_curation_path, sep="\t", low_memory=False)
    print(f"Loaded {len(pre_df)} samples")
    
    # Filter pre-curation data to match post-curation sample set
    if 'sample_accession' not in pre_df.columns:
        print("ERROR: 'sample_accession' column not found in pre-curation data")
        sys.exit(1)
    
    pre_df_filtered = pre_df[pre_df['sample_accession'].isin(post_sample_set)].copy()
    print(f"Filtered pre-curation data to {len(pre_df_filtered)} samples (matching post-curation)")
    
    # Calculate simple parsed completeness
    print("\n" + "-" * 60)
    print("Calculating simple parsed completeness...")
    print("-" * 60)
    parsed_completeness = calculate_simple_parsed_completeness(pre_df_filtered)
    
    # Run curation pipeline on filtered pre-curation data
    print("\n" + "-" * 60)
    print("Processing pre-curation data with full curation pipeline...")
    print("-" * 60)
    pre_df_curated = run_curation_pipeline(pre_df_filtered, verbose=False)
    
    # Calculate curated completeness
    print("\nCalculating curated completeness...")
    curated_completeness = calculate_all_completeness(pre_df_curated, top_n=args.top_n)
    
    # Calculate post-curation completeness
    print("\nCalculating post-curation completeness...")
    post_completeness = calculate_all_completeness(post_df, top_n=args.top_n)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Completeness Summary")
    print("=" * 60)
    
    for category in ['Host', 'Country', 'Collection Date', 'Isolation Source']:
        print(f"\n{category}:")
        parsed = parsed_completeness[category]
        curated = curated_completeness[category]
        post = post_completeness[category]
        
        print(f"  Parsed metadata:              Usable={parsed['usable']:,}")
        print(f"  Curated metadata:             Usable={curated['usable']:,}")
        print(f"  Studies reviewed + curated:   Usable={post['usable']:,}")
        
        # Calculate percentages and changes
        total_samples = len(pre_df_filtered)
        parsed_pct = (parsed['usable'] / total_samples) * 100
        curated_pct = (curated['usable'] / total_samples) * 100
        
        post_total = post['usable'] + post.get('other', 0) + post.get('not_filled', 0)
        post_pct = (post['usable'] / post_total) * 100 if post_total > 0 else 0
        
        parsed_to_curated = curated_pct - parsed_pct
        curated_to_post = post_pct - curated_pct
        parsed_to_post = post_pct - parsed_pct
        
        print(f"  Usable %: {parsed_pct:.1f}% → {curated_pct:.1f}% → {post_pct:.1f}%")
        print(f"  Change: Parsed→Curated: {parsed_to_curated:+.1f}%, Curated→Post: {curated_to_post:+.1f}%, Parsed→Post: {parsed_to_post:+.1f}%")
    
    # Generate plot
    print("\n" + "-" * 60)
    print("Generating comparison plot...")
    print("-" * 60)
    plot_completeness_comparison(parsed_completeness, curated_completeness, 
                                 post_completeness, output_path)
    
    print("\n" + "=" * 60)
    print("Complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
