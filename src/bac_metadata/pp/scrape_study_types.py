"""
Study Type Scraper - Analyze unreviewed studies to infer metadata characteristics.

This script:
- Loads curated metadata and filters to unreviewed samples
- Groups samples by study_accession
- Infers missing host values from isolation source categories
- Calculates completeness metrics for key metadata columns
- Calculates isolation source category distributions
- Infers study_setting based on isolation source patterns
- Infers amr_study based on AMR-related keywords in titles
- Outputs a per-study summary table

Output: TSV file with one row per study_accession, ordered by sample count.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import numpy as np


# File paths
METADATA_FILE = "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/final/metadata/metadata_final_curated_all_samples_and_columns.tsv"
OUTPUT_DIR = "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/processed/metadata"
OUTPUT_FILE = "study_characteristics_unreviewed.tsv"

# AMR lookup words (from notebook)
AMR_LOOKUP_WORDS = [
    "resist", "antibiotic", "antimicrobial", "carbapenem", "multi-drug", 
    "multidrug", "AMR", "aminoglycoside", "beta-lactam", "cephalosporin", 
    "fluoroquinolone", "macrolide", "penicillin", "tetracycline", "colistin", 
    "CPE", "CRE", "lactam", "KRE", "CRKP"
]

# Isolation source categories of interest
HOSPITAL_CATEGORIES = ["blood", "urine", "respiratory"]
ALL_CATEGORIES = ["blood", "urine", "faeces", "respiratory"]


def load_metadata(file_path: str) -> pd.DataFrame:
    """
    Load metadata from TSV file.
    
    Parameters:
    -----------
    file_path : str
        Path to metadata TSV file
        
    Returns:
    --------
    pd.DataFrame
        Loaded metadata
    """
    print(f"Loading metadata from: {file_path}")
    df = pd.read_csv(file_path, sep="\t", low_memory=False)
    print(f"  Loaded {len(df):,} total samples")
    return df


def filter_unreviewed(df: pd.DataFrame, max_samples: int = 132) -> pd.DataFrame:
    """
    Filter to studies with <= max_samples samples.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Full metadata dataframe
    max_samples : int
        Maximum number of samples per study (default: 132)
        
    Returns:
    --------
    pd.DataFrame
        Samples from studies with <= max_samples
    """
    # Count samples per study
    study_counts = df.groupby('study_accession')['sample_accession'].count()
    
    # Get studies with <= max_samples
    small_studies = study_counts[study_counts <= max_samples].index
    
    # Filter to those studies
    filtered = df[df['study_accession'].isin(small_studies)].copy()
    
    print(f"  Filtered to {len(filtered):,} samples")
    print(f"  from {filtered['study_accession'].nunique()} studies (n <= {max_samples})")
    return filtered


def calculate_completeness(group: pd.DataFrame, column: str) -> float:
    """
    Calculate completeness for a column (filled / total).
    
    Parameters:
    -----------
    group : pd.DataFrame
        Group of samples (e.g., from groupby)
    column : str
        Column name to check
        
    Returns:
    --------
    float
        Completeness ratio (0.0 to 1.0)
    """
    if column not in group.columns:
        return 0.0
    
    total = len(group)
    if total == 0:
        return 0.0
    
    filled = group[column].notna().sum()
    return filled / total


def calculate_category_percentages(group: pd.DataFrame) -> dict:
    """
    Calculate percentage of each isolation source category among filled values.
    
    Parameters:
    -----------
    group : pd.DataFrame
        Group of samples
        
    Returns:
    --------
    dict
        Dictionary with keys: blood_pct, urine_pct, faeces_pct, respiratory_pct
    """
    result = {f"{cat}_pct": 0.0 for cat in ALL_CATEGORIES}
    
    if 'isolation_source_category' not in group.columns:
        return result
    
    # Get filled isolation source categories
    filled = group[group['isolation_source_category'].notna()]['isolation_source_category']
    
    if len(filled) == 0:
        return result
    
    # Count each category (case-insensitive partial match)
    for category in ALL_CATEGORIES:
        count = filled.str.contains(category, case=False, na=False, regex=False).sum()
        result[f"{category}_pct"] = count / len(filled)
    
    return result


def infer_study_setting(group: pd.DataFrame) -> str:
    """
    Infer study_setting based on isolation source categories.
    
    Logic:
    - If >75% of filled isolation_source_category samples are blood/urine/respiratory → 'Hospital'
    - Otherwise → empty string
    
    Parameters:
    -----------
    group : pd.DataFrame
        Group of samples from same study
        
    Returns:
    --------
    str
        'Hospital' or empty string
    """
    if 'isolation_source_category' not in group.columns:
        return pd.NA
    
    # Get filled isolation source categories
    filled = group[group['isolation_source_category'].notna()]['isolation_source_category']
    
    if len(filled) == 0:
        return pd.NA
    
    # Count Hospital-related categories
    hospital_count = 0
    for category in HOSPITAL_CATEGORIES:
        hospital_count += filled.str.contains(category, case=False, na=False, regex=False).sum()
    
    # If >75% are Hospital-related
    if hospital_count / len(filled) > 0.75:
        return 'Hospital'
    
    return pd.NA


def infer_amr_study(group: pd.DataFrame) -> str:
    """
    Infer if study is AMR-related based on lookup words in titles.
    
    Searches both study_title and sample_title for AMR-related keywords.
    
    Parameters:
    -----------
    group : pd.DataFrame
        Group of samples from same study
        
    Returns:
    --------
    str
        'AMR' if any keyword found, otherwise empty string
    """
    # Build regex pattern from lookup words (case-insensitive)
    pattern = '|'.join(re.escape(word) for word in AMR_LOOKUP_WORDS)
    regex = re.compile(pattern, re.IGNORECASE)
    
    # Check study_title
    if 'study_title' in group.columns:
        study_titles = group['study_title'].dropna()
        if len(study_titles) > 0:
            # Check first value (they should all be the same for a study)
            if regex.search(str(study_titles.iloc[0])):
                return 'AMR'
    
    # Check sample_title across all samples in the group
    if 'sample_title' in group.columns:
        sample_titles = group['sample_title'].dropna()
        for title in sample_titles:
            if regex.search(str(title)):
                return 'AMR'
    
    return pd.NA


def infer_host(group: pd.DataFrame, study_setting: str = '') -> tuple[pd.DataFrame, dict]:
    """
    Infer missing host values based on isolation_source_category.
    
    Logic:
    a) Sample level: If host is NA and isolation_source_category contains 
       'blood', 'urine', or 'respiratory' → set host='human'
    b) Hospital + faeces: If study_setting='Hospital' and isolation_source_category 
       contains 'faeces' → set host='human'
    c) Study level: If >75% of filled isolation_source_category are clinical
       (blood/urine/respiratory), set all remaining NA hosts to 'human'
    
    Parameters:
    -----------
    group : pd.DataFrame
        Group of samples from same study
    study_setting : str
        Study setting ('Hospital' or empty string)
        
    Returns:
    --------
    tuple
        - Modified dataframe with inferred host values
        - Statistics dict: {'na_initial': int, 'na_filled_sample': int, 
                           'na_filled_hospital_faeces': int, 'na_filled_study': int}
    """
    # Create a copy to avoid modifying original data
    group = group.copy()
    
    # Initialize statistics
    stats = {
        'na_initial': 0,
        'na_filled_sample': 0,
        'na_filled_hospital_faeces': 0,
        'na_filled_study': 0
    }
    
    # Check if required columns exist
    if 'host' not in group.columns:
        return group, stats
    
    # Count initial NA hosts
    stats['na_initial'] = group['host'].isna().sum()
    
    if stats['na_initial'] == 0:
        return group, stats
    
    # Sample-level inference: If host is NA and isolation_source_category contains clinical terms
    if 'isolation_source_category' in group.columns:
        for category in HOSPITAL_CATEGORIES:
            # Find samples with NA host and this category in isolation_source_category
            mask = (
                group['host'].isna() & 
                group['isolation_source_category'].notna() &
                group['isolation_source_category'].str.contains(category, case=False, na=False, regex=False)
            )
            
            # Fill these with 'human'
            group.loc[mask, 'host'] = 'human'
            stats['na_filled_sample'] += mask.sum()
        
        # Hospital + faeces inference: If study_setting is 'Hospital' and faeces is present
        if pd.notna(study_setting) and study_setting == 'Hospital':
            faeces_mask = (
                group['host'].isna() & 
                group['isolation_source_category'].notna() &
                group['isolation_source_category'].str.contains('faeces', case=False, na=False, regex=False)
            )
            group.loc[faeces_mask, 'host'] = 'human'
            stats['na_filled_hospital_faeces'] += faeces_mask.sum()
        
        # Study-level inference: If >75% of filled isolation_source_category are clinical
        filled_iso = group[group['isolation_source_category'].notna()]['isolation_source_category']
        
        if len(filled_iso) > 0:
            # Count Hospital-related categories
            hospital_count = 0
            for category in HOSPITAL_CATEGORIES:
                hospital_count += filled_iso.str.contains(category, case=False, na=False, regex=False).sum()
            
            # If >75% are Hospital-related, infer remaining NA hosts as 'human'
            if hospital_count / len(filled_iso) > 0.75:
                remaining_na_mask = group['host'].isna()
                group.loc[remaining_na_mask, 'host'] = 'human'
                stats['na_filled_study'] += remaining_na_mask.sum()
    
    return group, stats


def analyze_study(study_accession: str, group: pd.DataFrame) -> dict:
    """
    Analyze a single study and return summary metrics.
    
    Parameters:
    -----------
    study_accession : str
        Study accession ID
    group : pd.DataFrame
        All samples from this study
        
    Returns:
    --------
    dict
        Dictionary with all metrics for this study
    """
    result = {
        'study_accession': study_accession,
        'sample_count': len(group),
    }
    
    # First values for descriptive fields
    for field in ['study_title', 'host', 'isolation_source']:
        if field in group.columns:
            first_value = group[field].dropna()
            result[field] = first_value.iloc[0] if len(first_value) > 0 else ''
        else:
            result[field] = ''
    
    # Completeness metrics
    for column in ['host', 'isolation_source', 'country', 'collection_date']:
        result[f'{column}_completeness'] = calculate_completeness(group, column)
    
    # Category percentages
    category_pcts = calculate_category_percentages(group)
    result.update(category_pcts)
    
    # Inferred values
    result['study_setting'] = infer_study_setting(group)
    result['amr_study'] = infer_amr_study(group)
    
    return result


def main():
    """
    Main execution function.
    """
    print("\n" + "="*80)
    print("STUDY TYPE SCRAPER - ANALYZE UNREVIEWED STUDIES")
    print("="*80)
    
    # Load and filter data
    metadata = load_metadata(METADATA_FILE)
    unreviewed = filter_unreviewed(metadata)
    
    # Group by study_accession
    print("\nAnalyzing studies...")
    print("Inferring missing host values from isolation sources...")
    grouped = unreviewed.groupby('study_accession')
    
    # Initialize host inference statistics
    total_host_stats = {
        'na_initial': 0,
        'na_filled_sample': 0,
        'na_filled_hospital_faeces': 0,
        'na_filled_study': 0
    }
    
    # Analyze each study
    results = []
    modified_groups = {}
    for study_acc, group in grouped:
        # Infer study_setting first (needed for host inference)
        study_setting = infer_study_setting(group)
        
        # Infer host values with study_setting
        group_modified, host_stats = infer_host(group, study_setting)
        modified_groups[study_acc] = group_modified
        
        # Accumulate statistics
        total_host_stats['na_initial'] += host_stats['na_initial']
        total_host_stats['na_filled_sample'] += host_stats['na_filled_sample']
        total_host_stats['na_filled_hospital_faeces'] += host_stats['na_filled_hospital_faeces']
        total_host_stats['na_filled_study'] += host_stats['na_filled_study']
        
        # Analyze study with modified group (after host inference)
        study_result = analyze_study(study_acc, group_modified)
        results.append(study_result)
    
    # Create results dataframe
    results_df = pd.DataFrame(results)
    
    # Sort by sample count (descending)
    results_df = results_df.sort_values('sample_count', ascending=False)
    
    # Calculate sample-level statistics
    samples_with_hospital = results_df[results_df['study_setting'] == 'Hospital']['sample_count'].sum()
    samples_with_amr = results_df[results_df['amr_study'] == 'AMR']['sample_count'].sum()
    
    # Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"Total studies analyzed: {len(results_df)}")
    print(f"Total samples: {results_df['sample_count'].sum():,}")
    
    print("\n" + "-"*80)
    print("STUDY-LEVEL INFERENCES")
    print("-"*80)
    print(f"Studies with inferred study_setting='Hospital': {(results_df['study_setting'] == 'Hospital').sum()}")
    print(f"  → Samples in these studies: {samples_with_hospital:,}")
    print(f"\nStudies with inferred amr_study='AMR': {(results_df['amr_study'] == 'AMR').sum()}")
    print(f"  → Samples in these studies: {samples_with_amr:,}")
    
    print("\n" + "-"*80)
    print("SAMPLE-LEVEL HOST INFERENCE")
    print("-"*80)
    print(f"Samples with NA host initially: {total_host_stats['na_initial']:,}")
    total_filled = (total_host_stats['na_filled_sample'] + 
                    total_host_stats['na_filled_hospital_faeces'] + 
                    total_host_stats['na_filled_study'])
    print(f"Samples with host inferred from isolation source: {total_filled:,}")
    print(f"  - Individual sample matches (blood/urine/respiratory): {total_host_stats['na_filled_sample']:,}")
    print(f"  - Hospital setting + faeces: {total_host_stats['na_filled_hospital_faeces']:,}")
    print(f"  - Study-level bias inference (>75% clinical): {total_host_stats['na_filled_study']:,}")
    
    # Average completeness
    print("\n" + "-"*80)
    print("AVERAGE COMPLETENESS ACROSS STUDIES")
    print("-"*80)
    for col in ['host_completeness', 'isolation_source_completeness', 
                'country_completeness', 'collection_date_completeness']:
        avg = results_df[col].mean()
        print(f"  {col}: {avg:.2%}")
    
    # Save output
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results_df.to_csv(output_path, sep='\t', index=False)
    print(f"\nResults saved to: {output_path}")
    print(f"  {len(results_df)} rows × {len(results_df.columns)} columns")
    
    print("\n" + "="*80)
    print("DONE")
    print("="*80)


if __name__ == "__main__":
    main()
