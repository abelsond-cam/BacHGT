"""
Debug script to test KlebNET metadata file loading and processing.
"""

import pandas as pd
import os

# File path
KLEBNET_METADATA_FILE = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/metadata/study_level_metadata/KlebNET-GSP_Metadata_Repository_Database.csv"

print("="*80)
print("DEBUG: KLEBNET METADATA FILE")
print("="*80)
print(f"File path: {KLEBNET_METADATA_FILE}")
print(f"File exists: {os.path.exists(KLEBNET_METADATA_FILE)}")

if not os.path.exists(KLEBNET_METADATA_FILE):
    print("ERROR: File not found!")
    exit(1)

# Try different encodings
encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-16']

print("\n--- Testing different encodings ---")
for encoding in encodings:
    try:
        print(f"\nTrying encoding: {encoding}")
        df = pd.read_csv(KLEBNET_METADATA_FILE, encoding=encoding, low_memory=False, nrows=5)
        print(f"  ✓ Success! Loaded {len(df)} rows (first 5)")
        print(f"  Columns: {list(df.columns)[:10]}...")
        break
    except UnicodeDecodeError as e:
        print(f"  ✗ Failed: {e}")
        continue
    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}: {e}")
        continue
else:
    print("\nERROR: Could not load file with any encoding!")
    exit(1)

# Now load full file with working encoding
print(f"\n--- Loading full file with encoding: {encoding} ---")
try:
    klebnet_df = pd.read_csv(KLEBNET_METADATA_FILE, encoding=encoding, low_memory=False)
    print(f"✓ Loaded {len(klebnet_df)} rows, {len(klebnet_df.columns)} columns")
except Exception as e:
    print(f"✗ Error loading full file: {type(e).__name__}: {e}")
    exit(1)

# Check required columns
print("\n--- Checking required columns ---")
required_cols = ["Sample accession"]
missing_cols = [col for col in required_cols if col not in klebnet_df.columns]
if missing_cols:
    print(f"✗ Missing required columns: {missing_cols}")
else:
    print(f"✓ All required columns present")

# Check date columns
print("\n--- Checking date columns ---")
date_cols = ["Collection year", "Collection month", "Collection day"]
for col in date_cols:
    if col in klebnet_df.columns:
        non_null = klebnet_df[col].notna().sum()
        print(f"  {col}: {non_null} non-null values")
    else:
        print(f"  {col}: ✗ NOT FOUND")

# Check other columns
print("\n--- Checking other columns ---")
other_cols = ["Country", "City or region", "Host", "Host tissue sampled", "Project accession"]
for col in other_cols:
    if col in klebnet_df.columns:
        non_null = klebnet_df[col].notna().sum()
        print(f"  {col}: {non_null} non-null values")
    else:
        print(f"  {col}: ✗ NOT FOUND")

# Test date formatting
print("\n--- Testing date formatting ---")
if "Collection year" in klebnet_df.columns:
    def format_klebnet_date(row):
        """Format year/month/day into collection_date string."""
        year = row.get("Collection year")
        month = row.get("Collection month")
        day = row.get("Collection day")
        
        if pd.isna(year):
            return pd.NA
        
        year_str = str(int(year))
        
        # If only year is available, return just the year
        if pd.isna(month):
            return year_str
        
        month_str = str(int(month)).zfill(2)
        
        # If year and month are available but not day, use 01 for day
        if pd.isna(day):
            return f"{year_str}/{month_str}/01"
        
        # All three are available
        day_str = str(int(day)).zfill(2)
        return f"{year_str}/{month_str}/{day_str}"
    
    # Test on first 10 rows
    test_rows = klebnet_df.head(10)
    print("Sample date formatting (first 10 rows):")
    for idx, row in test_rows.iterrows():
        year = row.get("Collection year", "N/A")
        month = row.get("Collection month", "N/A")
        day = row.get("Collection day", "N/A")
        formatted = format_klebnet_date(row)
        print(f"  Row {idx}: year={year}, month={month}, day={day} → {formatted}")

# Test country formatting
print("\n--- Testing country formatting ---")
if "Country" in klebnet_df.columns:
    def format_klebnet_country(row):
        """Combine country and city/region into single string."""
        country = row.get("Country")
        city_or_region = row.get("City or region")
        
        if pd.isna(country):
            return pd.NA
        elif not pd.isna(city_or_region):
            return f"{country} : {city_or_region}"
        else:
            return country
    
    # Test on first 10 rows
    test_rows = klebnet_df.head(10)
    print("Sample country formatting (first 10 rows):")
    for idx, row in test_rows.iterrows():
        country = row.get("Country", "N/A")
        city = row.get("City or region", "N/A")
        formatted = format_klebnet_country(row)
        print(f"  Row {idx}: country={country}, city={city} → {formatted}")

# Check Project accession
print("\n--- Checking Project accession ---")
if "Project accession" in klebnet_df.columns:
    unique_projects = klebnet_df["Project accession"].nunique()
    print(f"  Unique projects: {unique_projects}")
    print(f"  Sample projects:")
    for project in klebnet_df["Project accession"].dropna().unique()[:5]:
        count = (klebnet_df["Project accession"] == project).sum()
        print(f"    {project}: {count} samples")

# Show sample data
print("\n--- Sample data (first 3 rows) ---")
print(klebnet_df.head(3).to_string())

print("\n" + "="*80)
print("DEBUG COMPLETE")
print("="*80)
