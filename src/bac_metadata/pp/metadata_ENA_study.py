#!/usr/bin/env python3
"""
Harmonized Mapping Code for ENA Study Metadata for Klebsiella Project
This script helps to standardize and map metadata between study data and ENA data
"""

import sys
import os
import pandas as pd
import numpy as np

# Import the translation functions if needed
sys.path.append(os.getcwd())  # Add current directory to path
try:
    from source_translation import translate_source_to_isolation_source, report_translation_stats
except ImportError:
    # Define fallback functions if source_translation.py is not available
    def translate_source_to_isolation_source(study_data):
        """Fallback function when source_translation.py is not available"""
        return study_data
        
    def report_translation_stats(study_data):
        """Fallback function when source_translation.py is not available"""
        print("Source translation module not available. Skipping translation stats.")

def setup_standardized_columns(study_data, source_column='source', date_column='isolate date', 
                              sample_id_column='sample accession', location="Vietnam", location_column=None,
                              skip_source_translation=False, fixed_isolation_source=None):
    """
    Setup standardized columns for any study
    
    Parameters:
    -----------
    study_data : pandas.DataFrame
        The study data to standardize
    source_column : str
        Name of the column containing source information
    date_column : str
        Name of the column containing collection date information
    sample_id_column : str
        Name of the column containing sample accession IDs
    location : str
        Fixed location value to use (study-specific)
    location_column : str, optional
        Name of the column containing location information (overrides fixed location if provided)
    skip_source_translation : bool, optional
        If True, skip the source translation step
    fixed_isolation_source : str, optional
        If provided, use this fixed value for all isolation_source entries
    
    Returns:
    --------
    pandas.DataFrame
        Study data with standardized columns
    """
    study_data = study_data.copy()  # Work on a copy to avoid modifying original
    
    # Create standardized columns
    if sample_id_column in study_data.columns:
        study_data['sample_accession'] = study_data[sample_id_column]
    
    if date_column in study_data.columns:
        study_data['collection_date'] = study_data[date_column]
    
    # Set location - either from a column or fixed value
    if location_column and location_column in study_data.columns:
        study_data['combined_location'] = study_data[location_column]
    else:
        study_data['combined_location'] = location
    
    # Handle isolation source
    if fixed_isolation_source:
        # Use fixed value for all samples
        study_data['isolation_source'] = fixed_isolation_source
    elif not skip_source_translation and 'isolation_source' not in study_data.columns and source_column in study_data.columns:
        # Apply source translation
        study_data = translate_source_to_isolation_source(study_data)
    elif source_column in study_data.columns and skip_source_translation:
        # Use source column directly without translation
        study_data['isolation_source'] = study_data[source_column]
    
    return study_data

def debug_sample_matching(study_data, ena_data, ena_study_id_column, study_accession=None):
    """
    Debug sample matching between study data and ENA data
    
    Parameters:
    -----------
    study_data : pandas.DataFrame
        The study data with sample_accession column
    ena_data : pandas.DataFrame
        The full ENA data
    ena_study_id_column : str
        Name of the column in ENA data containing sample accessions
    study_accession : str, optional
        Study accession to filter ENA data
        
    Returns:
    --------
    dict
        Dictionary with matching statistics and filtered ENA data
    """
    # Check how many study samples exist in ENA data
    study_sample_count = len(study_data)
    ena_full_count = len(ena_data)
    
    print(f"Study data samples: {study_sample_count}")
    print(f"ENA samples total: {ena_full_count}")
    
    # Check if study samples exist in FULL ENA data
    study_sample_ids = set(study_data['sample_accession'].dropna())
    ena_sample_ids = set(ena_data[ena_study_id_column].dropna())
    
    matches_in_full_ena = study_sample_ids.intersection(ena_sample_ids)
    matches_count = len(matches_in_full_ena)
    
    print(f"Study samples found in FULL ENA data: {matches_count}/{study_sample_count}")
    
    # Create study-filtered subset if study_accession is provided
    ena_data_subset = None
    if study_accession:
        ena_data_subset = ena_data[ena_data["study_accession"] == study_accession]
        ena_subset_count = len(ena_data_subset)
        print(f"ENA samples in study subset: {ena_subset_count}")
        
        # Check how many are in the study-filtered subset
        matches_in_subset = study_sample_ids.intersection(set(ena_data_subset[ena_study_id_column].dropna()))
        matches_in_subset_count = len(matches_in_subset)
        print(f"Study samples found in study subset: {matches_in_subset_count}/{study_sample_count}")
        
        if matches_count == 0:
            print("\n❌ ISSUE DETECTED:")
            print("- No study samples found in ENA data at all")
            print("- Samples may not be deposited in ENA yet")
            print(f"- Check ena_study_id_column setting: {ena_study_id_column}")
        
        elif matches_count > 0 and matches_in_subset_count == 0:
            print("\n⚠️  PARTIAL ISSUE DETECTED:")
            print(f"- Found {matches_count} samples in FULL ENA data")
            print(f"- But only {matches_in_subset_count} in study-filtered subset")
            print("- This suggests study filtering is removing valid samples")
            print("- Samples may have 'NA' or different study_accession in ENA")
            
            # Show which samples are found but filtered out
            filtered_out = matches_in_full_ena - matches_in_subset
            if filtered_out:
                print(f"- Samples found but filtered out: {list(filtered_out)[:5]}...")
                
                # Check their study accessions
                for sample in list(filtered_out)[:3]:
                    sample_row = ena_data[ena_data[ena_study_id_column] == sample]
                    if len(sample_row) > 0:
                        study_acc = sample_row['study_accession'].iloc[0]
                        print(f"  - {sample}: study_accession = '{study_acc}'")
        else:
            print("✅ Samples found and study filtering working correctly!")
    else:
        print("No study_accession provided, skipping study-specific filtering")
    
    return {
        "matches_count": matches_count,
        "study_sample_count": study_sample_count,
        "ena_data_subset": ena_data_subset,
        "matches_in_full_ena": matches_in_full_ena
    }

def map_metadata(study_data, ena_data, ena_study_id_column, fields_to_map=None, ena_field_mapping=None):
    """
    Map metadata from study data to ENA data
    
    Parameters:
    -----------
    study_data : pandas.DataFrame
        The study data with standardized columns
    ena_data : pandas.DataFrame
        The ENA data to update
    ena_study_id_column : str
        Name of the column in ENA data containing sample accessions
    fields_to_map : list, optional
        List of fields to map. Default: ['location', 'collection_date', 'isolation_source']
    ena_field_mapping : dict, optional
        Mapping between standard field names and ENA column names
        
    Returns:
    --------
    tuple
        Updated ENA data and metadata update statistics
    """
    if fields_to_map is None:
        fields_to_map = ['location', 'collection_date', 'isolation_source']
    
    # Create a copy of the ENA data to work with
    ena_data_updated = ena_data.copy()
    
    # Initialize metadata tracking
    metadata_updates = {field: {'original_count': 0, 'added_count': 0} for field in fields_to_map}
    
    # Map each field
    for field in fields_to_map:
        # Determine the actual field name in ENA data
        ena_field = field
        if ena_field_mapping and field in ena_field_mapping:
            ena_field = ena_field_mapping[field]
            
        # Determine the field name in study data
        study_field = field
        if field == 'location':
            study_field = 'combined_location'
        
        # Count original non-null values
        original_count = ena_data_updated[ena_field].notna().sum()
        metadata_updates[field]['original_count'] = original_count
        
        # Map values from study data to ENA data where ENA data is missing
        ena_data_updated.loc[ena_data_updated[ena_field].isna(), ena_field] = \
            ena_data_updated.loc[ena_data_updated[ena_field].isna(), ena_study_id_column].map(
                study_data.set_index('sample_accession')[study_field]
            )
        
        # Count new non-null values and calculate difference
        new_count = ena_data_updated[ena_field].notna().sum()
        added_count = new_count - original_count
        metadata_updates[field]['added_count'] = added_count
        
        print(f"{field} (ENA: {ena_field}): {original_count} -> {new_count} (+{added_count})")
    
    return ena_data_updated, metadata_updates

def display_mapping_results(ena_data_original, ena_data_updated, metadata_updates, ena_study_id_column, ena_field_mapping=None):
    """
    Display mapping results and examples of newly added data
    
    Parameters:
    -----------
    ena_data_original : pandas.DataFrame
        Original ENA data before mapping
    ena_data_updated : pandas.DataFrame
        Updated ENA data after mapping
    metadata_updates : dict
        Dictionary with metadata update statistics
    ena_study_id_column : str
        Name of the column in ENA data containing sample accessions
    ena_field_mapping : dict, optional
        Mapping between standard field names and ENA column names
    """
    # Print updated summary of metadata updates
    print("\n" + "="*60)
    print("UPDATED METADATA MAPPING SUMMARY")
    print("="*60)
    for field, counts in metadata_updates.items():
        ena_field = field
        if ena_field_mapping and field in ena_field_mapping:
            ena_field = ena_field_mapping[field]
        print(f"{field} (ENA: {ena_field}): {counts['original_count']} originally present, {counts['added_count']} added")
    
    # Get field names in ENA data
    location_field = 'country' if ena_field_mapping and 'location' in ena_field_mapping else 'location'
    collection_date_field = ena_field_mapping.get('collection_date', 'collection_date') if ena_field_mapping else 'collection_date'
    isolation_source_field = ena_field_mapping.get('isolation_source', 'isolation_source') if ena_field_mapping else 'isolation_source'
    
    print(f"\nENA samples with {location_field}: {ena_data_updated[location_field].notna().sum()}/{len(ena_data_updated)}")
    print(f"ENA samples with {collection_date_field}: {ena_data_updated[collection_date_field].notna().sum()}/{len(ena_data_updated)}")
    print(f"ENA samples with {isolation_source_field}: {ena_data_updated[isolation_source_field].notna().sum()}/{len(ena_data_updated)}")
    
    # Show examples of the newly added data
    print("\n" + "="*60)
    print("EXAMPLES OF NEWLY ADDED DATA")
    print("="*60)
    
    for field in metadata_updates.keys():
        ena_field = field
        if ena_field_mapping and field in ena_field_mapping:
            ena_field = ena_field_mapping[field]
            
        print(f"\n{field.upper()} (ENA: {ena_field}):")
        print("-" * 40)
        
        # Show newly added data
        if metadata_updates[field]['added_count'] > 0:
            print(f"First 5 newly added values:")
            # Find samples that were missing this field originally and now have it
            newly_added = ena_data_updated[
                (ena_data_updated[ena_field].notna()) &
                (ena_data_original[ena_field].isna())  # Compare to original
            ].head(5)
            
            for _, row in newly_added.iterrows():
                print(f"  {row[ena_study_id_column]}: {row[ena_field]}")
        else:
            print("No new data added")

def save_results(ena_data_updated, metadata_updates, matches_count, study_sample_count, 
                output_dir, study_accession, ena_field_mapping=None):
    """
    Save mapping results to files
    
    Parameters:
    -----------
    ena_data_updated : pandas.DataFrame
        Updated ENA data after mapping
    metadata_updates : dict
        Dictionary with metadata update statistics
    matches_count : int
        Number of study samples found in ENA data
    study_sample_count : int
        Total number of study samples
    output_dir : str
        Directory to save output files
    study_accession : str
        Study accession
    ena_field_mapping : dict, optional
        Mapping between standard field names and ENA column names
    """
    # Write the updated data to a file
    output_file = f"{output_dir}/ready_to_merge_with_main_meta_corrected.csv"
    ena_data_updated.to_csv(output_file, index=False)
    print(f"\nUpdated metadata written to: {output_file}")
    
    # Also save a summary file
    summary_file = f"{output_dir}/metadata_update_summary_corrected.txt"
    with open(summary_file, 'w') as f:
        f.write(f"Study: {study_accession}\n")
        f.write(f"ENA data samples: {len(ena_data_updated)}\n")
        f.write(f"Study data samples: {study_sample_count}\n")
        f.write(f"Successfully matched samples: {matches_count}\n\n")
        f.write("Metadata updates:\n")
        for field, counts in metadata_updates.items():
            ena_field = field
            if ena_field_mapping and field in ena_field_mapping:
                ena_field = ena_field_mapping[field]
            f.write(f"{field} (ENA: {ena_field}): {counts['original_count']} -> {counts['original_count'] + counts['added_count']} ({counts['added_count']} added)\n")
    
    print(f"Summary written to: {summary_file}")
    print("\n" + "="*60)
    print("🎉 MAPPING COMPLETE!")
    print("="*60)
