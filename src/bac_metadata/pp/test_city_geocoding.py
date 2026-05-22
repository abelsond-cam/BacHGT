"""
Test script for city geocoding from location coordinates.
Tests the first 100 location values and compares with country field.
"""

import pandas as pd
import sys
from pathlib import Path

# Import the function we're testing
from bac_metadata.pp.metadata_curation import parse_city_from_location_coordinates

# Path to metadata file
metadata_dir = Path("/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/processed/metadata")
metadata_file = metadata_dir / "qc_final_with_metadata.tsv"

print(f"Loading metadata from: {metadata_file}")
print("=" * 80)

# Load the metadata
try:
    df = pd.read_csv(metadata_file, sep="\t", low_memory=False)
    print(f"Loaded {len(df)} total rows\n")
except FileNotFoundError:
    print(f"Error: Metadata file not found at {metadata_file}")
    print("Please check the path or specify a different file.")
    sys.exit(1)

# Filter to rows with location data
if 'location' not in df.columns:
    print("Error: 'location' column not found in metadata")
    sys.exit(1)

df_with_location = df[df['location'].notna()].copy()
print(f"Found {len(df_with_location)} rows with location data\n")

# Take first 100 rows with location data
test_df = df_with_location.head(100).copy()
print(f"Testing first {len(test_df)} rows with location data")
print("=" * 80)

# Test geocoding
print("\nGeocoding coordinates...")
test_df['geocoded_city'] = test_df['location'].apply(parse_city_from_location_coordinates)

# Count successes
successful = test_df['geocoded_city'].notna().sum()
failed = test_df['geocoded_city'].isna().sum()

print(f"\nResults:")
print(f"  Successfully geocoded: {successful} / {len(test_df)} ({100*successful/len(test_df):.1f}%)")
print(f"  Failed to geocode: {failed} / {len(test_df)} ({100*failed/len(test_df):.1f}%)")

# Show examples of successful geocoding
if successful > 0:
    print("\n" + "=" * 80)
    print("Examples of successful geocoding:")
    print("=" * 80)
    
    success_df = test_df[test_df['geocoded_city'].notna()].head(20)
    
    # Select columns to display
    display_cols = ['sample_accession', 'country', 'location', 'geocoded_city']
    display_cols = [col for col in display_cols if col in success_df.columns]
    
    # Display in a readable format
    for idx, row in success_df.iterrows():
        print(f"\nSample: {row.get('sample_accession', 'N/A')}")
        print(f"  Country:       {row.get('country', 'N/A')}")
        print(f"  Location:      {row.get('location', 'N/A')}")
        print(f"  Geocoded City: {row.get('geocoded_city', 'N/A')}")

# Show examples of failed geocoding (likely free text)
if failed > 0:
    print("\n" + "=" * 80)
    print("Examples of failed geocoding (likely free text or invalid format):")
    print("=" * 80)
    
    failed_df = test_df[test_df['geocoded_city'].isna()].head(10)
    
    for idx, row in failed_df.iterrows():
        print(f"\nSample: {row.get('sample_accession', 'N/A')}")
        print(f"  Country:  {row.get('country', 'N/A')}")
        print(f"  Location: {row.get('location', 'N/A')}")

# Save results to CSV for manual review
output_file = Path("test_city_geocoding_results.tsv")
output_cols = ['sample_accession', 'country', 'location', 'geocoded_city']
output_cols = [col for col in output_cols if col in test_df.columns]
test_df[output_cols].to_csv(output_file, sep='\t', index=False)

print("\n" + "=" * 80)
print(f"Full results saved to: {output_file}")
print("You can review this file to verify the geocoding makes sense.")
print("=" * 80)
