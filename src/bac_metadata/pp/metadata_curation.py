"""
Metadata curation: parse and categorise ENA-style fields on the QC-joined metadata table.

Run order (end-to-end)
----------------------
1. **Prerequisites** (separate scripts; must be run before this module's CLI):
   - ``metadata_collation.py`` — merge ENA TSVs, Refseq/NCTC stubs, study review flags,
     ``ready_to_merge`` substitutions, KlebNET import; writes e.g.
     ``intermediate_collated_metadata_wo_qc_or_kleborate.tsv``.
   - ``qc_add_metadata.py`` — build unified QC (bakrep, kleborate, LINcode, flags), left-join
     metadata onto QC, report unmatched rows, fill sparse metadata from bakrep; writes
     ``qc_final_with_metadata.tsv`` (default input for curation below).

2. **This script (``main()`` / CLI)** — loads ``qc_final_with_metadata.tsv`` (or equivalent):
   - Parse/clean **host**, **country**, **region**, **city**, **isolation_source**,
     **collection_date**; reconcile host vs isolation_source.
   - Merge study-level **amr_study** and **study_setting** from Google Sheet + characteristics TSV.
   - Optionally re-run the same parsing on **pre-collation** snapshot for before/after plots.
   - Filter out rows where ``kpsc_final_list`` is False and ``is_kpsc`` is True.
   - **report_curation_summary** — project-level issue table + parsing/ distribution plots.
   - **apply_kpsc_final_list_flag** — refresh final-list flag from the authoritative sample list.
   - Add boolean flags ``is_mgh78578``, ``is_complete_norway_genome``, ``have_transcriptome``;
     write full TSV, slim TSV, and captured log.

Key helpers
-----------
- ``parse_collection_date``: end-to-end date cleaning with targeted fixes and a final manual
  hand-fix step for stubborn patterns.
- Numerous ``parse_*`` / ``categorise_*`` / ``reconcile_*`` functions used by ``main()``.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from bac_metadata.pp.slice_by_final_list import apply_kpsc_final_list_flag


try:
    from IPython.display import display
except ImportError:
    # If not in IPython environment, use print instead
    def display(obj):
      print("Not in IPython environment, using print instead")
      print(obj)


# Google Sheets configuration for study metadata
STUDY_METADATA_GOOGLE_SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"
STUDY_METADATA_SHEET_NAME = "study_level"

# TSV file with study characteristics
STUDY_CHARACTERISTICS_TSV_PATH = "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/processed/metadata/study_characteristics_unreviewed.tsv"

# Norway complete genomes: BioSample accessions match ``Sample`` in the QC-joined metadata table
COMPLETE_NORWAY_GENOMES_CSV_PATH = (
    "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files "
    "- project_k/data/raw/metadata/complete_norway_genomes.csv"
)
COMPLETE_NORWAY_GENOMES_BIOSAMPLE_COL = "BioSample accession"

MGH78578_SAMPLE_ID = "GCF_000016305.1_ASM1630v1_genomic"

TRANSCRIPTOME_SAMPLE_IDS = frozenset({
    "GCF_000016305.1_ASM1630v1_genomic",
    "GCF_000742755.1_ASM74275v1_genomic",
    "GCF_000315385.1_ASM31538v1_genomic",
    "GCF_024397815.1_ASM2439781v1_genomic",
    "GCF_019927625.1_ASM1992762v1_genomic",
    "GCA_900451625.1_32512_C01_genomic",
    "GCF_002813595.1_ASM281359v1_genomic",
})

MANUAL_RUNS_TO_ADD = ("/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files "
    "- project_k/data/raw/metadata/manual_runs_to_add.csv")
USED_RUN_ACCESSION_TSV_PATH = (
    "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files "
    "- project_k/data/final/metadata/metadata_final_curated_used_accession.tsv"
)

# Fixed categories for isolation source plots (sorted by count dynamically in each dataset)
ISOLATION_SOURCE_CATEGORIES_TO_PLOT = [
    "urine",
    "faeces & rectal swabs",
    "blood",
    "lower respiratory, endotracheal",
    "wound & pus, abscess, surgical drain, body tissue, bone, biopsy",
    "wastewater & water",
    "invasive gut & organs",
    "body fluid (ascites / peritoneal / pleural)",
    "urinary catheter",
    "upper airway",
    "clinical environment or surface",
]

# Fixed categories for host plots (sorted by count dynamically in each dataset)
HOST_CATEGORIES_TO_PLOT = [
    "human",
    "wastewater & water",
    "grazing livestock & horses",
    "domestic animals",
    "clinical environment or surface",
    "meat products",
    "wild animals",
    "insect",
    "wild birds",
]


def _authenticate_google():
    """Authenticate with Google and return credentials."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    # Use same scopes as other scripts to match existing token
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    CREDENTIALS_FILE = Path("/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/raw/google/client_secret_766063885615-5r4chm0o2635kqjc2fe18coak2a70ugc.apps.googleusercontent.com.json")
    TOKEN_FILE = Path(__file__).parent / "token.json"
    
    creds = None
    
    # Check if we have a saved token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If there are no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"Credentials file not found: {CREDENTIALS_FILE}")
            
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for next run
        TOKEN_FILE.write_text(creds.to_json())
    
    return creds


def _read_google_sheet(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    """
    Read a sheet from a Google Spreadsheet.
    
    Parameters:
    -----------
    spreadsheet_id : str
        Google Spreadsheet ID (from the URL)
    sheet_name : str
        Name of the sheet to read
    
    Returns:
    --------
    pd.DataFrame
        Dataframe containing the sheet data
    """
    from googleapiclient.discovery import build
    
    creds = _authenticate_google()
    service = build("sheets", "v4", credentials=creds)
    
    # Read the sheet
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:ZZ"  # Read all columns
    ).execute()
    
    values = result.get("values", [])
    
    if not values:
        raise ValueError(f"No data found in sheet '{sheet_name}'")
    
    # First row is headers
    headers = values[0]
    
    # Create dataframe
    data = []
    for row in values[1:]:
        # Pad row to match header length
        padded_row = row + [""] * (len(headers) - len(row))
        data.append(padded_row[:len(headers)])
    
    df = pd.DataFrame(data, columns=headers)
    
    return df
      

def report_ena_column(ena_data_subset, column_name, display_n=None, verbose=True):
    """
    Report on a specific column in the ENA data subset.
    
    Parameters:
    -----------
    ena_data_subset : pd.DataFrame
        The ENA data subset to analyze
    column_name : str
        Name of the column to report on
    display_n : int, default=5
        Number of unique values to display
    verbose : bool, default=True
        If True, print report. If False, suppress output.
        
    Returns:
    --------
    dict : Dictionary with 'present', 'missing', 'unique_values', 'value_counts' keys
        - 'present': number of non-null values
        - 'missing': number of null values
        - 'unique_values': list of unique values
        - 'value_counts': dictionary mapping each unique value to its count
    """
    if column_name not in ena_data_subset.columns:
        if verbose:
            print(f"Warning: Column '{column_name}' not found in data")
        return {'present': 0, 'missing': len(ena_data_subset), 'unique_values': [], 'value_counts': {}}
    
    n_present = ena_data_subset[column_name].notna().sum()
    n_missing = ena_data_subset[column_name].isna().sum()
    value_counts = ena_data_subset[column_name].value_counts(dropna=True)
    unique_vals = value_counts.index.tolist()
    
    # If display_n is None, show all values
    if display_n is None:
        display_n = len(unique_vals)
    
    if verbose:
        print(f"\nColumn: {column_name}")
        print(f"  Present: {n_present}")
        print(f"  Missing: {n_missing}")
        print(f"  Unique values ({len(unique_vals)} total):")
        for val in unique_vals[:display_n]:
            count = value_counts[val]
            print(f"    - {val}: {count}")
        if len(unique_vals) > display_n:
            print(f"    ... and {len(unique_vals) - display_n} more")
    
    # Return a dataframe with the value counts
    value_counts_df = value_counts.to_frame()
    value_counts_df.columns = ['count']
    value_counts_df['unique_value'] = value_counts_df.index
    return value_counts_df


def search_and_replace(df, source_col, target_col, rules, default_passthrough=True, match_case=False, match_whole_word=False, descriptor="Processing", verbose=True):
    """
    Generic search-and-replace helper for parsing or categorising data.
    
    Applies a series of search-and-replace rules to process a column. Each rule is processed
    sequentially, with later rules seeing the results of earlier rules.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame containing the data to process
    source_col : str
        Name of the column to search in (used for initial values and reporting)
    target_col : str
        Name of the column to write processed values to (can be same as source_col)
    rules : list of dict
        List of rules, each dict with keys:
          - 'search': regex pattern or exact string to search for
          - 'replace': replacement value to use when pattern matches
    default_passthrough : bool, default True
        If True, values that don't match any rule pass through unchanged.
        If False, values that don't match any rule are set to pd.NA.
    match_case : bool, default False
        If True, search is case-sensitive. If False, case-insensitive.
    match_whole_word : bool, default False
        If True, match whole words only using word boundaries (\\b).
    descriptor : str, default "Processing"
        Descriptor for print statements (e.g., "Parsing", "Categorising")
    verbose : bool, default=True
        If True, print summary. If False, suppress output.
    
    Returns:
    --------
    tuple of (pd.DataFrame, dict)
        - Modified DataFrame with processed values in target_col
        - Dictionary with per-replacement-value counts
    
    Notes:
    ------
    - Rules are applied sequentially; later rules see the results of earlier rules
    - Reports per-rule breakdown of source values matched and totals converted
    """
    from collections import defaultdict

    if source_col not in df.columns:
        print(f"Warning: source column '{source_col}' not found.")
        return df, {}

    df = df.copy()
    base = df[source_col]
    base_str = base.astype(str)
    df[target_col] = base if default_passthrough else pd.NA

    total_converted = 0
    per_value_counts = {}
    # Track, for each replacement value, which original/source terms contributed and by how many rows
    per_value_source_counts = defaultdict(lambda: defaultdict(int))

    for rule in rules:
        # Recreate the base string array with target col - incl. the latest changes after we have substituted in the previous rules
        base_str = df[target_col].astype(str)

        pattern = rule["search"]
        value = rule["replace"]

        # Apply word boundary if match_whole_word is True
        if match_whole_word:
            # Wrap pattern in group to ensure word boundaries apply to each alternative in pipe-separated patterns
            pattern = rf"\b(?:{pattern})\b"
        
        # Use match_case parameter to control case sensitivity
        mask = base_str.str.contains(pattern, case=match_case, na=False, regex=True)
        # Note: str.extract is useful if you want to get the actual matched groups,
        # but here we just want a boolean mask for matching rows.
        # So we should keep str.contains unless you need the groups elsewhere.

        # Avoid double-counting rows already set to the target value
        # Handle None values (which will become pd.NA)
        if value is not None:
            mask = mask & (df[target_col] != value)
        else:
            # For None values, only match non-NA values
            mask = mask & df[target_col].notna()

        if not mask.any():
            #print(f"Rule -> '{value}' pattern '{pattern}': no matches") # Don't print this
            continue

        subgroup = base_str[mask]
        counts_by_source = subgroup.value_counts()
        rule_total = counts_by_source.sum()

        # Apply replacements (None becomes pd.NA)
        if value is None:
            df.loc[mask, target_col] = pd.NA
            value_label = "NA (removed)"
        else:
            df.loc[mask, target_col] = value
            value_label = value
            
        per_value_counts[value_label] = per_value_counts.get(value_label, 0) + rule_total
        total_converted += rule_total

        # Accumulate which original/source terms contributed to this replacement value
        for src_val, cnt in counts_by_source.items():
            per_value_source_counts[value_label][src_val] += cnt

    # Compact summary grouped by replacement value
    if verbose and per_value_counts:
        print(f"\n{descriptor} summary (per replacement value):")
        # Sort replacement values by total converted (descending) for readability
        for val, total_for_val in sorted(per_value_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"{val} - {total_for_val} records after {descriptor.lower()}, from:")
            # Sort contributing source terms by count (descending)
            source_counts = per_value_source_counts.get(val, {})
            for src_val, cnt in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  '{src_val}' - {cnt}")

    if verbose:
        print(f"\nTotal converted across rules: {total_converted}")

    return df, per_value_counts


def search_report_and_replace_with_na(df, source_col, target_col, patterns_to_replace, verbose=True):
    """
    Search for patterns in a column, report detailed information about matches (studies and samples),
    and replace all matches with pd.NA (missing values).
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame to process
    source_col : str
        Column name to search in
    target_col : str
        Column name to replace in (can be same as source_col)
    patterns_to_replace : list of str
        List of string patterns to search for (case-insensitive regex)
    verbose : bool, default=True
        If True, print replacement info. If False, suppress output.
    
    Returns:
    --------
    pd.DataFrame
        Modified dataframe with matches replaced by pd.NA
    """
    if source_col not in df.columns:
        print(f"Warning: source column '{source_col}' not found in dataframe")
        return df
    
    if target_col not in df.columns:
        print(f"Warning: target column '{target_col}' not found in dataframe")
        return df
    
    df = df.copy()
    
    # Convert column to string for regex matching
    source_str = df[source_col].astype(str)
    
    # For each pattern in patterns_to_replace
    for pattern in patterns_to_replace:
        # Use case-insensitive regex matching
        mask = source_str.str.contains(pattern, case=False, na=False, regex=True)
        
        if not mask.any():
            continue
        
        n_samples = mask.sum()
        n_studies = df[mask]['study_accession'].nunique() if 'study_accession' in df.columns else None
        if verbose:
            if n_studies is not None:
                print(f"Pattern '{pattern}': {n_samples} samples across {n_studies} studies replaced with pd.NA (missing)")
            else:
                print(f"Pattern '{pattern}': {n_samples} samples replaced with pd.NA (missing)")
        
        # Replace all matches with pd.NA in target_col
        df.loc[mask, target_col] = pd.NA
    
    return df


def write_list_of_unique_values(unique_vals, filename):
    """
    Write a list of unique values to a file. If the file already exists, it will be overwritten.
    
    Parameters:
    -----------
    unique_vals : list
        List of unique values to write
    filename : str
        Name of the file to write to
    """
    import os
      # Check if the file exists
    if os.path.exists(filename):
        print("Filename already exists, it will be overwritten")
        os.remove(filename)
    else:    # If the file does not exist, create it      
        print(f"File {filename} does not exist, it will be created")
        os.makedirs(os.path.dirname(filename), exist_ok=True)

    # Write the list of unique values to the file
    with open(filename, "w") as f:
        for val in unique_vals:
            f.write(f"{val}\n")
    print(f"List of unique values written to {filename}")


def parse_collection_date(df, verbose=True):
    """
    Clean, parse, and normalize collection_date into collection_date_parsed and year_parsed.
    Steps: cleaning → pandas/dateutil parse → targeted pattern fixes → manual hand-fix for top
    stubborn values → final reporting. Behavior matches prior parse workflow; only names changed.
    """
    if 'collection_date' not in df.columns:
        if verbose:
            print("Warning: 'collection_date' column not found in dataframe")
        return df

    df = df.copy()

    initial_missing = df['collection_date'].isna().sum()
    initial_filled = df['collection_date'].notna().sum()
    total_rows = len(df)

    if verbose:
        print("\n" + "="*60)
        print("Date Parsing Report")
        print("="*60 + "\n")
        print("\nInitial state of 'collection_date' column:")
        print(f"  Total rows: {total_rows}")
        print(f"  Filled values: {initial_filled}")
        print(f"  Missing values: {initial_missing}")

        print("\n" + "-"*60)
        print("Step 0: Pre-processing and Cleaning")
        print("-"*60)
    from bac_metadata.pp.date_utils import step0_clean
    step0_clean(df)

    df['collection_date_parsed'] = pd.NA
    df['year_parsed'] = pd.NA
    
    from bac_metadata.pp.date_utils import parse_with_pandas_and_dateutil
    parse_with_pandas_and_dateutil(df, "Parsing after Step 0 (pandas + dateutil)")

    if verbose:
        print("\n" + "-"*60)
        print("Step 2: Targeted fixes for known patterns")
        print("-"*60)
    from bac_metadata.pp.date_utils import apply_targeted_fixes
    apply_targeted_fixes(df)

    if verbose:
        print("\n" + "-"*60)
        print("Final Results")
        print("-"*60)

    final_parsed_filled = df['collection_date_parsed'].notna().sum()
    final_parsed_missing = df['collection_date_parsed'].isna().sum()
    final_year_filled = df['year_parsed'].notna().sum()
    final_year_missing = df['year_parsed'].isna().sum()
    # 2026-06-02: emit collection_year alongside year_parsed for v2 / downstream
    # consistency. Future-proof: when v1 is next regenerated, downstream code can
    # use collection_year directly; until then, build_metadata_v2's RENAMED_COLUMNS
    # still maps year_parsed → collection_year on existing v1 TSVs.
    df['collection_year'] = df['year_parsed']
    unparsable_mask = df['collection_date'].notna() & (df['collection_date_parsed'].isna() | df['year_parsed'].isna())
    unparsable_df = df.loc[unparsable_mask, ['collection_date', 'collection_date_parsed', 'year_parsed']]

    if verbose:
        print("\n'collection_date_parsed' column:")
        print(f"  Filled values: {final_parsed_filled}")
        print(f"  Missing values: {final_parsed_missing}")

        print("\n'year_parsed' column:")
        print(f"  Filled values: {final_year_filled}")
        print(f"  Missing values: {final_year_missing}")

    if not unparsable_df.empty:
        if verbose:
            top_unparsable = unparsable_df['collection_date'].value_counts().head(10)
            print("\nTop 10 unparsable collection_date values (after final parsing):")
            for val, count in top_unparsable.items():
                print(f"  '{val}': {count}")

        manual_map = {
            "2015-17": ("2016/06/30", 2016),
            "1800/2020": ("2021-12-03", 2021),
            "2015-01-01/2015-08-31": ("2015/01/01", 2015),
            # Any sample with collection_date == 1800-01-01, set to NaN
            "1800-01-01": (pd.NA, pd.NA),
        }
        from bac_metadata.pp.date_utils import apply_manual_hand_fixes
        df = apply_manual_hand_fixes(df, unparsable_df, manual_map)
    else:
        if verbose:
            print("\nNo unparsable collection_date values remain after final parsing.")

    if verbose:
        print("\n" + "="*60 + "\n")

    return df


def categorise_region(df, verbose=True):
    """
    Categorise region values into a normalized region column based on country_parsed.
    """
    source_col = "country_parsed" if "country_parsed" in df.columns else "country"
    if source_col not in df.columns:
        if verbose:
            print("Warning: source country column not found in dataframe")
        return df
    if source_col == "country":
        if verbose:
            print("categorise_region requires country_parsed; running country parsing first.")
        df = parse_country(df, verbose=verbose)
        source_col = "country_parsed"

    df = df.copy()
    if verbose:
        print("\n" + "=" * 60)
        print("Region Categorisation Report")
        print("=" * 60 + "\n")

    df["region"] = df[source_col]
    
    # Ensure any string "nan" values in source are converted to pd.NA before processing
    # This handles edge cases where np.nan might have been converted to string "nan"
    mask_nan_string_source = df[source_col].astype(str).str.lower() == "nan"
    if mask_nan_string_source.any():
        df.loc[mask_nan_string_source, source_col] = pd.NA
        df.loc[mask_nan_string_source, "region"] = pd.NA

    rules = [
        # Expect exact, case-sensitive country names after country parsing
        {# USA, and Canada are in N. America
            "search": r"USA|United States of America|Canada", 
            "replace": "N. America"
        }, 
        {# Central & S. America
            "search": (
                r"Brazil|Argentina|Chile|Peru|Colombia|Uruguay|Paraguay|Bolivia|Ecuador|Venezuela|"
                r"Guyana|Suriname|French Guiana|Mexico|Guatemala|Belize|Honduras|El Salvador|Guadeloupe|(?:Central America)|" # One of Nick Thompsons studies just has 'Central America' as descriptor in EBI
                r"Nicaragua|Costa Rica|Panama|Bahamas|Cuba|Haiti|Dominican Republic|Puerto Rico|Curacao|"
                r"Jamaica|Trinidad|Tobago|Barbados|Guadeloupe|Martinique"
            ),
            "replace": "Central & S. America",
        },
        {# W. Europe and Israel
            "search": (
                r"United Kingdom|Denmark|Sweden|Finland|Norway|Malta|Ireland|France|Germany|"
                r"Netherlands|Belgium|Luxembourg|Switzerland|Austria|Spain|Portugal|Italy|Greece|Cyprus|Iceland|Greenland|"
                r"Andorra|Monaco|Liechtenstein|San Marino|Vatican|Israel"
            ),
            "replace": "W. Europe",
        },
        {# E. Europe & Russia
            "search": (
                r"Poland|Czech Republic|Slovakia|Hungary|Romania|Bulgaria|Ukraine|Belarus|Moldova|Russia|"
                r"Lithuania|Latvia|Estonia|Serbia|Croatia|Bosnia and Herzegovina|Slovenia|Slovak|"
                r"North Macedonia|Albania|Kosovo|Montenegro|Georgia|Armenia|Azerbaijan|Czechia|Macedonia"
            ),
            "replace": "E. Europe",
        },
        {# Africa
            "search": (
                r"Egypt|Nigeria|Burkina Faso|South Africa|Kenya|Uganda|Tanzania|Ghana|Ethiopia|Malawi|"
                r"Cameroon|Morocco|Algeria|Tunisia|Senegal|Ivory Coast|Côte d'Ivoire|"
                r"Cote d'Ivoire|Madagascar|Botswana|Namibia|Zambia|Zimbabwe|Mozambique|Sudan|"
                r"South Sudan|Rwanda|Burundi|Mali|Niger|Chad|Angola|Congo|Democratic Republic of the Congo|"
                r"Gabon|Mauritania|Libya|Sierra Leone|Liberia|Benin|Togo|Eritrea|Djibouti|Somalia|"
                r"Central African Republic|Cape Verde|Gambia|Seychelles|Mauritius|Reunion|Réunion"
            ),
            "replace": "Africa",
        },
        {# Western and Central Asia
            "search": (
                r"Saudi Arabia|West Bank|United Arab Emirates|Oman|Qatar|Bahrain|Kuwait|Yemen|UAE|"
                r"Jordan|Palestine|Lebanon|Syria|Iraq|Iran|Türkiye|Afghanistan|"
                r"India|Pakistan|Bangladesh|Sri Lanka|Nepal|Bhutan|Maldives|Kazakhstan|"
                r"Turkmenistan|Uzbekistan|Tajikistan|Kyrgyzstan"
            ),
            "replace": "M. East, Central Asia",
        },
        {# East and Southeast Asia
            "search": (
                r"Thailand|Vietnam|Viet Nam|Laos|Cambodia|Myanmar|Burma|Malaysia|Singapore|Japan|South Korea|Korea|Taiwan|"
                r"Indonesia|Philippines|Brunei|Timor-Leste|Papua New Guinea|Fiji|Samoa|Tonga|Solomon Islands|Vanuatu|"
                r"China|Mongolia|Hong Kong|Macau"
            ),
            "replace": "E. Asia",
        },
        {# Australia and New Zealand
            "search": (
                r"Australia|New Zealand|Guam"
            ),
            "replace": "Oceania",
        },
    ]

    df, _ = search_and_replace(
        df,
        source_col=source_col,
        target_col="region",
        rules=rules,
        default_passthrough=True,
        match_case=True,
        match_whole_word=True,
        descriptor="Categorising",
        verbose=verbose,
    )

    # Ensure any string "nan" values are converted to pd.NA
    # This handles edge cases where np.nan might have been converted to string "nan"
    mask_nan_string = df["region"].astype(str).str.lower() == "nan"
    df.loc[mask_nan_string, "region"] = pd.NA

    if verbose:
        print("\ncategorised region column:")
        report_ena_column(df, "region", 40, verbose=verbose)

        print("\n" + "=" * 60 + "\n")
    return df


def parse_country(df, verbose=True):
    """
    Parse country values into a normalized country_parsed column using search/replace rules.
    """
    if 'country' not in df.columns:
        if verbose:
            print("Warning: 'country' column not found in dataframe")
        return df

    df = df.copy()
    if verbose:
        print("\n" + "=" * 60)
        print("Country Parsing Report")
        print("=" * 60 + "\n")

    df['country_parsed'] = df['country']

    rules = [
        {"search": "usa|united states", "replace": "USA"},
        {"search": "canada", "replace": "Canada"},
        {"search": "australia", "replace": "Australia"},
        {"search": "guam", "replace": "USA"},
        {"search": "new zealand", "replace": "New Zealand"},
        {"search": "china", "replace": "China"},
        {"search": "japan", "replace": "Japan"},
        {"search": "india", "replace": "India"},
        {"search": "france", "replace": "France"},
        {"search": "germany", "replace": "Germany"},
        {"search": "portugal", "replace": "Portugal"},
        {"search": "ireland", "replace": "Ireland"},
        {"search": "spain", "replace": "Spain"},
        {"search": "italy", "replace": "Italy"},
        {"search": "netherlands", "replace": "Netherlands"},
        {"search": "bergium", "replace": "Belgium"},
        {"search": "switzerland", "replace": "Switzerland"},
        {"search": "austria", "replace": "Austria"},
        {"search": "greece", "replace": "Greece"},
        {"search": "sweden", "replace": "Sweden"},
        {"search": "norway", "replace": "Norway"},
        {"search": "berlgium", "replace": "Belgium"}, # Typo in metadata
        {"search": "belgium", "replace": "Belgium"}, # Typo in metadata
        {"search": "finland", "replace": "Finland"}, # Typo in metadata
        {"search": "denmark", "replace": "Denmark"}, # Typo in metadata
        {"search": "russia", "replace": "Russia"}, # Typo in metadata
        {"search": "poland", "replace": "Poland"}, # Typo in metadata
        {"search": "czech republic", "replace": "Czech Republic"}, # Typo in metadata
        {"search": "slovakia", "replace": "Slovakia"}, # Typo in metadata
        {"search": "hungary", "replace": "Hungary"}, # Typo in metadata
        {"search": "romania", "replace": "Romania"}, # Typo in metadata
        {"search": "bulgaria", "replace": "Bulgaria"}, # Typo in metadata
        {"search": "ukraine", "replace": "Ukraine"}, # Typo in metadata
        {"search": "belarus", "replace": "Belarus"}, # Typo in metadata
        {"search": "moldova", "replace": "Moldova"}, # Typo in metadata
        {"search": "macedonia", "replace": "Macedonia"}, # Typo in metadata
        {"search": "albania", "replace": "Albania"}, # Typo in metadata
        {"search": "czechia", "replace": "Czechia"}, # Typo in metadata
        {"search": "macedonia", "replace": "Macedonia"}, # Typo in metadata
        {"search": "moldova", "replace": "Moldova"}, # Typo in metadata
        {"search": "macedonia", "replace": "Macedonia"}, # Typo in metadata
        {"search": "ukraine", "replace": "Ukraine"}, # Typo in metadata
        {"search": "denmark", "replace": "Denmark"},
        {"search": "finland", "replace": "Finland"},
        {"search": "brazil", "replace": "Brazil"},
        {"search": "argentina|argentinia", "replace": "Argentina"},
        {"search": "curacao", "replace": "Curacao"},
        {"search": "mexico:", "replace": "Mexico"},  # Used mexico: to avoid picking up USA: New Mexico
        {"search": "chile", "replace": "Chile"}, 
        {"search": "colombia", "replace": "Colombia"},  
        {"search": "guatemala", "replace": "Guatemala"},  
        {"search": "honduras", "replace": "Honduras"},  
        {"search": "nicaragua", "replace": "Nicaragua"}, 
        {"search": "costa rica", "replace": "Costa Rica"},  
        {"search": "panama", "replace": "Panama"},  
        {"search": "bahamas", "replace": "Bahamas"},  
        {"search": "cuba", "replace": "Cuba"},  
        {"search": "haiti", "replace": "Haiti"},  
        {"search": "dominican republic", "replace": "Dominican Republic"},  
        {"search": "puerto rico", "replace": "Puerto Rico"},  
        {"search": "jamaica", "replace": "Jamaica"},  
        {"search": "trinidad", "replace": "Trinidad"},  
        {"search": "tobago", "replace": "Tobago"},  
        {"search": "barbados", "replace": "Barbados"},  
        {"search": "martinique", "replace": "Martinique"},  
        {"search": "curacao", "replace": "Curacao"},  
        {"search": "guadeloupe", "replace": "Guadeloupe"},
        {"search": "peru", "replace": "Peru"},
        {"search": "ecuador", "replace": "Ecuador"},
        {"search": "turkey|TÃ¼rkiye|rkiye", "replace": "Türkiye"}, 
        {"search": "ghana", "replace": "Ghana"},
        {"search": "kenya", "replace": "Kenya"},
        {"search": "ethiopia", "replace": "Ethiopia"},
        {"search": "tanzania", "replace": "Tanzania"},
        {"search": "madagascar", "replace": "Madagascar"},
        {"search": "sudan", "replace": "Sudan"},
        {"search": "uganda", "replace": "Uganda"},
        {"search": "zambia", "replace": "Zambia"},
        {"search": "zimbabwe", "replace": "Zimbabwe"},
        {"search": "malawi", "replace": "Malawi"},
        {"search": "mozambique", "replace": "Mozambique"},
        {"search": "rwanda", "replace": "Rwanda"},
        {"search": "burundi", "replace": "Burundi"},
        {"search": "gambia", "replace": "Gambia"},
        {"search": "malaysia", "replace": "Malaysia"},
        {"search": "singapore", "replace": "Singapore"},
        {"search": "cambodia|cambodge", "replace": "Cambodia"},
        {"search": "indonesia", "replace": "Indonesia"},
        {"search": "philippines", "replace": "Philippines"},
        {"search": "brunei", "replace": "Brunei"},
        {"search": "timor-leste", "replace": "Timor-Leste"},
        {"search": "maldives", "replace": "Maldives"},
        {"search": "laos", "replace": "Laos"},
        {"search": "taiwan", "replace": "Taiwan"},
        {"search": "hong kong", "replace": "Hong Kong"},
        {"search": "korea", "replace": "South Korea"},  # There are no north korean samples, so this is safe
        {"search": "myanmar", "replace": "Myanmar"},  # There are no north korean samples, so this is safe
        {"search": "macau", "replace": "Macau"},
        {"search": "maldives", "replace": "Maldives"},
        {"search": "sri lanka", "replace": "Sri Lanka"},
        {"search": "Viet", "replace": "Vietnam"},  # Will match viet nam, vietnam
        {"search": "bangladesh", "replace": "Bangladesh"},
        {"search": "nepal", "replace": "Nepal"},
        {"search": "bhutan", "replace": "Bhutan"},
        {"search": "KSA", "replace": "Saudi Arabia"},
        {"search": "Saudi Arabia", "replace": "Saudi Arabia"},
        {"search": "pakistan", "replace": "Pakistan"},
        {"search": "afghanistan", "replace": "Afghanistan"},
        {"search": "united arab emirates", "replace": "United Arab Emirates"},
        {"search": "iran", "replace": "Iran"},
        {"search": "iraq", "replace": "Iraq"},
        {"search": "qatar", "replace": "Qatar"},
        {"search": "syria", "replace": "Syria"},
        {"search": "lebanon", "replace": "Lebanon"},
        {"search": "jordan", "replace": "Jordan"},
        {"search": "palestine", "replace": "Palestine"},
        {"search": "gaza", "replace": "Palestine"},
        {"search": "west bank", "replace": "Palestine"},
        {"search": "israel", "replace": "Israel"},
        {"search": "egypt", "replace": "Egypt"},
        {"search": "nigeria", "replace": "Nigeria"},
        {"search": "kenya", "replace": "Kenya"},
        {"search": "tanzania", "replace": "Tanzania"},
        {"search": "uganda", "replace": "Uganda"},
        {"search": "zambia", "replace": "Zambia"},
        {"search": "zimbabwe", "replace": "Zimbabwe"},
        {"search": "malawi", "replace": "Malawi"},
        {"search": "mozambique", "replace": "Mozambique"},
        {"search": "rwanda", "replace": "Rwanda"},
        {"search": "burundi", "replace": "Burundi"},
        {"search": "malaysia", "replace": "Malaysia"},
        {"search": "singapore", "replace": "Singapore"},
        {"search": "indonesia", "replace": "Indonesia"},
        {"search": "philippines", "replace": "Philippines"},
        {"search": "thailand", "replace": "Thailand"},
        {"search": "brunei", "replace": "Brunei"},
        {"search": "timor-leste", "replace": "Timor-Leste"},
        {"search": "maldives", "replace": "Maldives"},
        {"search": "sri lanka", "replace": "Sri Lanka"},
        {"search": "bangladesh", "replace": "Bangladesh"},
        {"search": "nepal", "replace": "Nepal"},
        {"search": "bhutan", "replace": "Bhutan"},
        {"search": "pakistan", "replace": "Pakistan"},
        {"search": "afghanistan", "replace": "Afghanistan"},
        {"search": "iran", "replace": "Iran"},
        {"search": "iraq", "replace": "Iraq"},
        {"search": "syria", "replace": "Syria"},
        {"search": "lebanon", "replace": "Lebanon"},
        {"search": "jordan", "replace": "Jordan"},
        {"search": "argentina", "replace": "Argentina"},
        {"search": "uruguay", "replace": "Uruguay"},
        {"search": "south africa", "replace": "South Africa"},
        {"search": "missing|not collected", "replace": pd.NA},
        {"search": r"\bunknown\b", "replace": pd.NA},  # exact 'unknown', won't match 'USA: unknown'
        {"search": r"\bUnknown\b", "replace": pd.NA},  # exact 'unknown', won't match 'USA: unknown'
        {"search": r"^\s*-\s*$", "replace": pd.NA},  # match single '-' (with possible whitespace)
        {"search": r"\bnot\b", "replace": pd.NA},  # exact 'not' as a separate word, catches e.g. 'Not provided', 'Not specified' etc.
        {"search": r"\buk\b", "replace": "United Kingdom"},  # exact 'uk', won't match 'ukraine'
        {"search": "united kingdom|england|scotland|wales|northern ireland|britain", "replace": "United Kingdom"},

    ]

    df, _ = search_and_replace(
        df,
        source_col="country_parsed",
        target_col="country_parsed",
        rules=rules,
        default_passthrough=True,
        descriptor="Parsing",
        verbose=verbose,
    )

    if verbose:
        print("\nparsed country column:")
        report_ena_column(df, "country_parsed", 40, verbose=verbose)

        print("\n" + "=" * 60 + "\n")
    return df


def parse_city_from_location_coordinates(location_str):
    """
    Parse location coordinates and convert to city name using reverse geocoding.
    
    Expected format: "35.01988 N 135.7778 E" (latitude N/S longitude E/W)
    Skips free text entries that don't match the coordinate pattern.
    
    Parameters:
    -----------
    location_str : str
        Location string with format "lat N/S lon E/W"
        
    Returns:
    --------
    str or None
        City name if successfully geocoded, None otherwise
    """
    if pd.isna(location_str) or not isinstance(location_str, str):
        return None
    
    try:
        # Parse the coordinate string
        # Format: "35.01988 N 135.7778 E"
        parts = location_str.strip().split()
        
        # Must have at least 4 parts: lat, N/S, lon, E/W
        if len(parts) < 4:
            return None
        
        # Validate that parts[0] and parts[2] are numbers
        try:
            lat_value = float(parts[0])
            lon_value = float(parts[2])
        except ValueError:
            # Not valid numbers, skip this entry (likely free text)
            return None
        
        # Validate that parts[1] and parts[3] are directional indicators
        lat_dir = parts[1].upper()
        lon_dir = parts[3].upper()
        
        if lat_dir not in ['N', 'S'] or lon_dir not in ['E', 'W']:
            # Not valid directions, skip this entry
            return None
        
        # Convert to signed decimal degrees
        # North is positive, South is negative
        # East is positive, West is negative
        if lat_dir == 'S':
            lat_value = -lat_value
        if lon_dir == 'W':
            lon_value = -lon_value
        
        # Use reverse_geocoder to get location
        import reverse_geocoder as rg
        result = rg.search((lat_value, lon_value), mode=1)
        
        if result and len(result) > 0:
            # Return city name
            return result[0].get('name')
        
        return None
        
    except Exception as e:
        # Silently fail for individual coordinates
        print(f"Error geocoding coordinates: {e}")
        return None


def parse_city(df, output_dir=None, verbose=True):
    """
    Parse city-level geographic information from country, location, and centre fields.
    
    Extraction strategy:
    a) Extract city from 'country' field (pattern: "country: city")
    b) Extract coordinates from 'location' field (when city is empty)
    c) Extract from 'center_name' or 'centre' field (when both above are empty)
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame containing the metadata
    output_dir : str, optional
        Directory to save the city_metadata.tsv review file
    verbose : bool, default True
        If True, print detailed parsing report
        
    Returns:
    --------
    pd.DataFrame
        DataFrame with added columns: city, city_location, city_center
    """
    df = df.copy()
    
    if verbose:
        print("\n" + "=" * 60)
        print("City Parsing Report")
        print("=" * 60 + "\n")
    
    # Initialize new columns
    df['city'] = None
    df['city_location'] = None
    df['city_center'] = None
    
    # Step a) Extract from 'country' field (pattern: country: city)
    city_from_country = 0
    if 'country' in df.columns:
        # Find entries with ':' in country field
        has_colon = df['country'].notna() & df['country'].str.contains(':', na=False)
        if has_colon.any():
            # Extract everything after ':' and strip whitespace
            df.loc[has_colon, 'city'] = df.loc[has_colon, 'country'].str.split(':', n=1).str[1].str.strip()
            city_from_country = df['city'].notna().sum()
        
        if verbose:
            print("Step a) Extracting from 'country' field (pattern: country: city):")
            print(f"  Found {city_from_country} cities from 'country' field")
    else:
        if verbose:
            print("Step a) Extracting from 'country' field:")
            print("  Warning: 'country' column not found in dataframe")
    
    # Step b) Extract from 'location' field (when city is empty)
    # Store raw coordinates in city_location and try to geocode to city name
    total_location = 0
    added_city_location = 0
    geocoded_cities = 0
    if 'location' in df.columns:
        total_location = df['location'].notna().sum()
        # Only process location where city is empty
        need_location = df['city'].isna() & df['location'].notna()
        
        if need_location.any():
            # Store raw coordinates in city_location
            df.loc[need_location, 'city_location'] = df.loc[need_location, 'location']
            added_city_location = need_location.sum()
            
            # Try to geocode coordinates to city names
            if verbose:
                print("\nStep b) Extracting coordinates from 'location' field:")
                print(f"  Total rows with 'location' data: {total_location}")
                print(f"  Stored {added_city_location} coordinates in 'city_location' (where city is empty)")
                print("  Geocoding coordinates to city names...")
            
            # Geocode each location to get city name
            for idx in df[need_location].index:
                location_str = df.loc[idx, 'location']
                city_name = parse_city_from_location_coordinates(location_str)
                if city_name:
                    df.loc[idx, 'city'] = city_name
                    geocoded_cities += 1
            
            if verbose:
                print(f"  Successfully geocoded {geocoded_cities} coordinates to city names")
        else:
            if verbose:
                print("\nStep b) Extracting coordinates from 'location' field:")
                print(f"  Total rows with 'location' data: {total_location}")
                print("  No new coordinates to process (city already filled)")
    else:
        if verbose:
            print("\nStep b) Extracting from 'location' field:")
            print("  Warning: 'location' column not found in dataframe")
    
    # Step c) Report on 'center_name' or 'centre' field availability
    # Note: center data is too unreliable (many overseas institutes), so we include it in
    # the review file but do NOT automatically populate city_center - must be done manually
    total_center = 0
    center_with_country = 0
    # Check which column exists: center_name or centre
    center_col = None
    if 'center_name' in df.columns:
        center_col = 'center_name'
    elif 'centre' in df.columns:
        center_col = 'centre'
    
    if center_col:
        total_center = df[center_col].notna().sum()
        # Count how many rows have both center and country data
        if 'country' in df.columns:
            center_with_country = (df[center_col].notna() & df['country'].notna()).sum()
        
        if verbose:
            print(f"\nStep c) '{center_col}' field availability:")
            print(f"  Total rows with '{center_col}' data: {total_center}")
            if 'country' in df.columns:
                print(f"  Rows with both '{center_col}' and 'country': {center_with_country}")
            print("  Note: center data included in review file but NOT auto-populated to 'city_center'")
            print("        (too unreliable - many overseas institutes; requires manual curation)")
    else:
        if verbose:
            print("\nStep c) 'center' field availability:")
            print("  Warning: neither 'center_name' nor 'centre' column found in dataframe")
    
    # Summary statistics
    if verbose:
        city_filled = df['city'].notna().sum()
        city_location_filled = df['city_location'].notna().sum()
        city_center_filled = df['city_center'].notna().sum()
        total_with_city_data = (df['city'].notna() | df['city_location'].notna() | df['city_center'].notna()).sum()
        total_rows = len(df)
        
        print("\nSummary:")
        print(f"  city: {city_filled} filled")
        print(f"  city_location: {city_location_filled} filled")
        print(f"  city_center: {city_center_filled} filled")
        print(f"  Total with some city data: {total_with_city_data} / {total_rows} ({100*total_with_city_data/total_rows:.1f}%)")
    
    # Save review file if output_dir is provided
    if output_dir:
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        # Determine which center column to use
        center_col = 'center_name' if 'center_name' in df.columns else ('centre' if 'centre' in df.columns else None)
        
        # Select columns for the review file
        review_columns = ['sample_accession', 'study_accession', 'country', 'location']
        if center_col:
            review_columns.append(center_col)
        review_columns.extend(['city', 'city_location', 'city_center'])
        
        # Filter to only columns that exist
        existing_review_columns = [col for col in review_columns if col in df.columns]
        
        review_file_path = os.path.join(output_dir, 'city_metadata.tsv')
        df[existing_review_columns].to_csv(review_file_path, sep='\t', index=False)
        
        if verbose:
            print("\nCity metadata review file saved to:")
            print(f"  {review_file_path}")
    
    if verbose:
        print("\n" + "=" * 60 + "\n")
    
    return df


def parse_host(df, verbose=True):
    """
    Parse host values into a normalized host_parsed column.
    - Sets host_parsed to 'Homo sapiens' when host is Homo sapiens or contains human/sapiens/patient (case-insensitive).
    - Otherwise copies the original host value.
    - Reports counts per rule and the parsed column distribution (top 40 values).
    """
    if 'host' not in df.columns:
        if verbose:
            print("Warning: 'host' column not found in dataframe")
        return df

    df = df.copy()
    if verbose:
        print("\n" + "=" * 60)
        print("Host Parsing Report")
        print("=" * 60 + "\n")

    # Make host_parsed the same as host to start with
    df['host_parsed'] = df['host']

    # Replace unspecified, missing, not collected, none, and unknown with pd.NA
    replace_with_none_rules = ["unspecified", "missing", "not collected", "none", "unknown", "not provided", "not aplicable", "not applicable", "None", "not host-associated"]
    df = search_report_and_replace_with_na(df, "host_parsed", "host_parsed", replace_with_none_rules, verbose=verbose)

    # Apply these rules only where 'host' is not na
    mask_ireland = df['host'].notna() & df['host'].str.contains('Ireland', na=False)
    df.loc[mask_ireland, 'country'] = 'Ireland'
    df.loc[mask_ireland, 'host_parsed'] = pd.NA

    mask_uk = df['host'].notna() & df['host'].str.contains('UK', na=False)
    df.loc[mask_uk, 'country'] = 'UK'
    df.loc[mask_uk, 'host_parsed'] = pd.NA

    mask_lisbon = df['host'].notna() & df['host'].str.contains('Lisbon', na=False)
    df.loc[mask_lisbon, 'country'] = 'Portugal: Lisbon'
    df.loc[mask_lisbon, 'host_parsed'] = pd.NA

    mask_liver_abscess = df['host'].notna() & df['host'].str.contains('Liver abscess', na=False)
    df.loc[mask_liver_abscess, 'isolation_source'] = 'Liver abscess'
    df.loc[mask_liver_abscess, 'host'] = "human"
    df.loc[mask_liver_abscess, 'host_parsed'] = "human"
    df.loc[mask_liver_abscess, 'host_category'] = "human"

    mask_blood = df['host'].notna() & df['host'].str.contains('blood', na=False)
    df.loc[mask_blood, 'isolation_source'] = 'blood'
    df.loc[mask_blood, 'host'] = "human"
    df.loc[mask_blood, 'host_parsed'] = "human"
    df.loc[mask_blood, 'host_category'] = "human"

    mask_intestinal = df['host'].notna() & df['host'].str.contains('intestinal', na=False)
    df.loc[mask_intestinal, 'isolation_source'] = 'intestinal'
    df.loc[mask_intestinal, 'host'] = "human"
    df.loc[mask_intestinal, 'host_parsed'] = "human"
    df.loc[mask_intestinal, 'host_category'] = "human"

    mask_sputum = df['host'].notna() & df['host'].str.contains('Sputum', na=False)
    df.loc[mask_sputum, 'isolation_source'] = 'Sputum'
    df.loc[mask_sputum, 'host'] = "human"
    df.loc[mask_sputum, 'host_parsed'] = "human"
    df.loc[mask_sputum, 'host_category'] = "human"
            
    # In all these cases, source should be human and isolation source should be reset
    mask_children = df['host'].notna() & df['host'].str.contains('Children', na=False)
    df.loc[mask_children, 'host'] = "human"
    df.loc[mask_children, 'host_parsed'] = "human"
    df.loc[mask_children, 'host_category'] = "human"
    df.loc[mask_children, 'dev_stage'] = "child"

    # Rules for collating host results that are not none
    rules = [
        {"search": r"sapien", "replace": "human"},
        {"search": r"human", "replace": "human"},
        {"search": r"homo", "replace": "human"},
        {"search": r"male", "replace": "human"},  # This is clearly referring to a human, not a male animal
        {"search": r"female", "replace": "human"},  # This is clearly referring to a human, not a female animal
        {"search": r"patient", "replace": "human"},
        {"search": r"environment", "replace": "environment"}, # will need to check if this maeans clinical envrionment
        {"search": r"surface", "replace": "surface"}, # this is an assumption that they are all clinical environments, but ideally we would check each
        {"search": r"env", "replace": "environment"}, # I have checked, nothing else has 'env' in the name (ctrl f)
        {"search": r"wastewater", "replace": "waste aqua"}, # Temporary to separate from water
        {"search": r"water", "replace": "water"},
        {"search": r"river", "replace": "water"},
        {"search": r"sewage", "replace": "sewage"},
        {"search": r"bos", "replace": "cow"},
        {"search": r"taurus", "replace": "cow"},
        {"search": r"bovine", "replace": "cow"},
        {"search": r"cattle", "replace": "cow"},
        {"search": r"livestock", "replace": "livestock"},
        {"search": r"live stock", "replace": "livestock"},
        {"search": r"sheep", "replace": "sheep"},
        {"search": r"canis", "replace": "dog"},  
        {"search": r"canine", "replace": "dog"},
        {"search": r"dog", "replace": "dog"},
        {"search": r"felis", "replace": "cats"},
        {"search": r"\bcat\b", "replace": "cats"},  # exact 'cat' → 'cats' (plural), won't match 'catheter'
        {"search": r"gallus", "replace": "chicken"},
        {"search": r"chicken", "replace": "chicken"},
        {"search": r"Meleagris gallopavo", "replace": "turkey"},
        {"search": r"broiler", "replace": "chicken"},   # A broiler is a chicken that is raised for meat production.
        {"search": r"turkey", "replace": "turkey"},   # The Norway study includes many turkeys raised for meat production.
        {"search": r"musculus", "replace": "mouse"}, #mouse
        {"search": r"mouse", "replace": "mouse"}, #mouse
        {"search": r"\bpig\b", "replace": "pig"},  # Exact match 'pig'
        {"search": r"scrofa", "replace": "pig"},
        {"search": r"swine", "replace": "pig"},
        {"search": r"Porcine", "replace": "pig"},
        {"search": r"goat", "replace": "goat"},
        {"search": r"Capra hircus", "replace": "goat"},
        {"search": r"Capra aegagrus", "replace": "goat"},
        {"search": r"Ovis aries", "replace": "sheep"},
        {"search": r"rabbit", "replace": "rabbit"},
        {"search": r"caballus", "replace": "horse"},
        {"search": r"horse", "replace": "horse"},
        {"search": r"equine", "replace": "horse"},
        {"search": r"deer", "replace": "deer"}, # any type
        {"search": r"elk", "replace": "deer"}, # any type
        {"search": r"moose", "replace": "deer"}, # any type
        {"search": r"bear", "replace": "bear"}, # any type
        {"search": r"Pteropus poliocephalus", "replace": "fruit bat"},
        {"search": r"monkey", "replace": "monkey"},
        {"search": r"primate", "replace": "primate"},
        {"search": r"animal", "replace": "animal"},
        {"search": r"Phocarctos hookeri", "replace": "seal"},
        {"search": r"Larus michahellis", "replace": "seabird"},
        {"search": r"avian", "replace": None},  # Too generic, redundant with host
        {"search": r"equus", "replace": "horse"},
        # Anser cygnoides, Aratinga solstitialis, Bombyx mori, Capra aegagrus hicus, Chroicocephalus ridibundus, Dasycercus crisicauda, Hoplobatrachus rugulosus, Malurus Cyaneus, Manorina melanocephala, Megadyptes antipodes, Morus alba, Pteropus poliocephalus, Sorghum bicolor, Sus scrofa domesticus, Tilapia zillii, Melomys burtoni
        {"search": r"Anser cygnoides", "replace": "bird"},
        {"search": r"Aratinga solstitialis", "replace": "bird"},
        {"search": r"Bombyx mori", "replace": "insect"},
        {"search": r"Capra aegagrus hicus", "replace": "goat"},
        {"search": r"Chroicocephalus ridibundus", "replace": "bird"},
        {"search": r"Dasycercus crisicauda", "replace": "animal"},
        {"search": r"Hoplobatrachus rugulosus", "replace": "animal"},
        {"search": r"Malurus Cyaneus", "replace": "bird"},
        {"search": r"Manorina melanocephala", "replace": "bird"},
        {"search": r"Megadyptes antipodes", "replace": "bird"},
        {"search": r"Morus alba", "replace": "tree"},
        {"search": r"Pteropus poliocephalus", "replace": "fruit bat"},
        {"search": r"Sorghum bicolor", "replace": "plant"},
        {"search": r"Sus scrofa domesticus", "replace": "pig"},
        {"search": r"Tilapia zillii", "replace": "fish"},
        {"search": r"Melomys burtoni", "replace": "rodent"},
        {"search": r"Notaden nichollsi", "replace": "toad"},
        {"search": r"donkey", "replace": "donkey"},
        {"search": r"lizard", "replace": "lizard"},
        {"search": r"turtle", "replace": "turtle"},
        {"search": r"hare", "replace": "rabbit"},
        {"search": r"duck", "replace": "duck"},
        {"search": r"pigeon", "replace": "pigeon"},
        {"search": r"rodent", "replace": "rodent"},
        {"search": r"elephant", "replace": "elephant"},
        {"search": r"kangaroo", "replace": "kangaroo"},
        {"search": r"peafowl", "replace": "peafowl"},
        {"search": r"guinea", "replace": "guinea fowl"},
        {"search": r"finch", "replace": "finch"}, # Any type
        {"search": r"crow", "replace": "crow"},
        {"search": r"canary", "replace": "canary"},
        {"search": r"insect", "replace": "insect"},
        {"search": r"Anopheles darlingi", "replace": "mosquito"},
        {"search": r"Lepidoptera", "replace": "butterfly"},
        {"search": r"snail", "replace": "snail"},
        {"search": r"cricket", "replace": "cricket"},
        {"search": r"Musca domestica", "replace": "fly"},
        {"search": r"fly", "replace": "fly"},
        {"search": r"worm", "replace": "worm"},
        {"search": r"wasp", "replace": "wasp"},
        {"search": r"Blattodea", "replace": "cockroach"},
        {"search": r"bee", "replace": "bee"},
        {"search": r"Mytilus edulis", "replace": "mussel"},
        {"search": r"lactuca", "replace": "lettuce"},           # Lettuce
        {"search": r"salad", "replace": "salad"},           # Lettuce
        {"search": r"daucus", "replace": "carrot"},            # Carrot
        {"search": r"brassica", "replace": "brassica"},          # Brassica rapa / oleracea
        {"search": r"ipomoea", "replace": "sweet potato"},           # Sweet potato
        {"search": r"allium", "replace": "onion"},     
        {"search": r"Banana", "replace": "banana"},       # Onion/scallion
        {"search": r"beta", "replace": "beet"},  
        {"search": r"faba bean", "replace": "bean"},              # Beet (Beta vulgaris)
        {"search": r"capsicum", "replace": "pepper"},          # Pepper/chili
        {"search": r"petroselinum", "replace": "parsley"},      # Parsley
        {"search": r"cucumis", "replace": "cucumber"},           # Cucumber
        {"search": r"solanum", "replace": "eggplant"},           # Eggplant / tomato (Solanum spp.)
        {"search": r"xanthosoma", "replace": "tannia"},        # Tannia/taro
        {"search": r"raphanus", "replace": "radish"},          # Radish
        {"search": r"dioscorea", "replace": "dioscorea"},   
        {"search": r"zingiber", "replace": "ginger"},          # Ginger
        {"search": r"helianthus", "replace": "helianthus"}, 
        {"search": r"soil", "replace": "soil"}, 
        {"search": r"bird", "replace": "bird"},
        {"search": r"clinical", "replace": "clinical (not specified)"},
        {"search": r"surface", "replace": "surface"},
        {"search": r"fecal", "replace": "fecal (not specified)"},
        # Additional reptiles and amphibians
        {"search": r"Gopherus berlandieri", "replace": "turtle"},
        {"search": r"Varanus", "replace": "lizard"},  # Monitor lizards
        {"search": r"Ctenotus", "replace": "lizard"},  # Skinks
        {"search": r"Diplodactylus", "replace": "lizard"},  # Geckos
        {"search": r"Egernia", "replace": "lizard"},  # Skinks
        {"search": r"Pseudemoia", "replace": "lizard"},  # Skinks
        {"search": r"Elseya", "replace": "turtle"},
        {"search": r"Aquarana catesbeiana", "replace": "toad"},  # American bullfrog
        {"search": r"Litoria", "replace": "toad"},  # Tree frogs
        {"search": r"Uperoleia", "replace": "toad"},  # Toadlets
        # Additional birds
        {"search": r"Dromaius", "replace": "bird"},  # Emu
        {"search": r"Passer domesticus", "replace": "bird"},  # House sparrow
        {"search": r"Eclectus", "replace": "bird"},  # Parrots
        {"search": r"Stercorarius", "replace": "seabird"},  # Skuas
        {"search": r"Numididae", "replace": "bird"},  # Guinea fowl family
        # Additional mammals (marsupials and rodents)
        {"search": r"Trichosurus", "replace": "animal"},  # Possums
        {"search": r"Lagorchestes", "replace": "animal"},  # Wallabies
        {"search": r"Notomys", "replace": "rodent"},  # Hopping mice
        {"search": r"Pseudomys", "replace": "rodent"},  # Native mice
        {"search": r"Dasycercus", "replace": "animal"},  # Mulgara
        {"search": r"Dasyurus", "replace": "animal"},  # Quolls
        {"search": r"Parantechinus", "replace": "animal"},  # Dunnarts
        {"search": r"Pogonomys", "replace": "rodent"},  # Tree mice
        {"search": r"Tachyglossus", "replace": "animal"},  # Echidna
        {"search": r"Phoca largha", "replace": "seal"},
        # Additional insects
        {"search": r"Anopheline", "replace": "mosquito"},  # Anopheles mosquitoes
        {"search": r"Spodoptera", "replace": "insect"},  # Armyworm moths
        {"search": r"Frieseomelitta", "replace": "bee"},  # Stingless bees
        {"search": r"Melipona", "replace": "bee"},  # Stingless bees
        {"search": r"Drosophila", "replace": "fly"},  # Fruit flies
        {"search": r"Araneae", "replace": "spider"},
        {"search": r"Anastrepha", "replace": "fly"},  # Fruit flies
        {"search": r"Ceratitis", "replace": "fly"},  # Fruit flies
        {"search": r"Atta cephalotes", "replace": "insect"},  # Leafcutter ants
        # Fish and aquatic animals
        {"search": r"Leipotheropon", "replace": "fish"},
        {"search": r"Salmo salar", "replace": "fish"},  # Salmon
        {"search": r"Misgurnus", "replace": "fish"},  # Loaches
        {"search": r"Chlamydogobius", "replace": "fish"},  # Desert gobies
        {"search": r"Crassostrea", "replace": "mussel"},  # Oysters
        {"search": r"Pecten maximus", "replace": "mussel"},  # Scallops
        {"search": r"Tegillarcagranosa", "replace": "mussel"},  # Clams
        {"search": r"Tilapia", "replace": "fish"},
        {"search": r"catfish", "replace": "fish"},
        {"search": r"Leiocassis", "replace": "fish"},
        # Additional plants
        {"search": r"Zea mays", "replace": "plant"},  # Corn/maize
        {"search": r"Maize", "replace": "plant"},
        {"search": r"Cenchrus", "replace": "plant"},  # Grasses
        {"search": r"Citrus sinensis", "replace": "plant"},  # Orange
        {"search": r"Philodendron", "replace": "plant"},
        {"search": r"Musa", "replace": "banana"},
        # Other organisms that should be excluded or categorized
        {"search": r"bacteria", "replace": pd.NA},
        {"search": r"Fungi", "replace": pd.NA},
        {"search": r"wild chukar", "replace": "bird"},
        {"search": r"wild rat", "replace": "rodent"},
        {"search": r"gull", "replace": "seabird"},
        {"search": r"panda", "replace": "animal"},
        # Values that are isolation sources, not hosts
        {"search": r"blood", "replace": pd.NA},
        {"search": r"intestinal", "replace": pd.NA},
        {"search": r"Sputum", "replace": pd.NA},
        {"search": r"Liver abscess", "replace": pd.NA},
        {"search": r"Children", "replace": "human"},
        {"search": r"NIST Mixed Microbial RM", "replace": pd.NA},   
        {"search": r"Grown in Blood agar culture medium", "replace": pd.NA},
        {"search": r"Laboratory Derived", "replace": pd.NA}
    ]

    df, counts = search_and_replace(
        df,
        source_col="host_parsed",
        target_col="host_parsed",
        rules=rules,
        default_passthrough=True,
        descriptor="Parsing",
        verbose=verbose,
    )

    if verbose:
        print("\nparsed host column:")
        report_ena_column(df, "host_parsed", 40, verbose=verbose)

        print("\n" + "=" * 60 + "\n")
    
    # Automatically create host_category from host_parsed
    df = categorise_host(df, verbose=verbose)
    
    return df


def categorise_host(df, verbose=True):
    """
    Categorise host_category values into a normalized host_category column based on host_parsed.
    Maps host_parsed values to broad categories: human, livestock, companion animals, 
    wild animals, wild birds, insect, vegetable/plant/soil, clinical environment, wastewater & water.
    """
    source_col = "host_parsed" if "host_parsed" in df.columns else "host"
    if source_col not in df.columns:
        if verbose:
            print("Warning: source host column not found in dataframe")
        return df
    if source_col == "host":
        if verbose:
            print("categorise_host requires host_parsed; running host parsing first.")
        df = parse_host(df, verbose=verbose)
        source_col = "host_parsed"

    df = df.copy()
    if verbose:
        print("\n" + "=" * 60)
        print("Host Category Categorisation Report")
        print("=" * 60 + "\n")

    df["host_category"] = df[source_col]

    rules = [
        {"search": "human", "replace": "human"},
        {"search": "environment|surface|Padding|Medical Instrument", "replace": "clinical environment or surface"},
        {"search": "waste aqua|wastewater|sewage|water", "replace": "wastewater & water"},
        {"search": "pigeon|finch|crow|canary|bird|gull", "replace": "wild birds"},
        {"search": "cow|sheep|pig|goat|livestock|Cow|horse", "replace": "grazing livestock & horses"},
        {"search": "chicken|broiler|poultry|turkey|duck|guinea fowl|peafowl|quail|Poultry", "replace": "poultry livestock"},
        {"search": "dog|cats|rabbit|mouse|rodent", "replace": "domestic animals"},
        {"search": "animal|primate|elephant|kangaroo|hare|deer|bear|lizard|turtle|monkey|donkey|Sea mammal|seal|seabird|toad|fruit bat|mussel|giant panda|wild rat|Reptiles", "replace": "wild animals"},
        {"search": "insect|cricket|fly|worm|wasp|bee|spider|snail|cockroach|butterfly|mosquito", "replace": "insect"},
        {"search": "banana|salad|lettuce|carrot|brassica|sweet potato|onion|beet|bean|pepper|parsley|cucumber|eggplant|tannia|radish|dioscorea|ginger|helianthus|soil|banana|tree|plant|Plantain|Mulberry", "replace": "vegetable, plant or soil"},
        {"search": "meat|food|egg|fish|milk|Milk|dairy", "replace": "meat products"},
        {"search": "not available|Not available|Laboratory Derived|Laboratory|Lab|laboratory|Biofilm|biofilm|germ", "replace": pd.NA},
    ]

    df, _ = search_and_replace(
        df,
        source_col=source_col,
        target_col="host_category",
        rules=rules,
        default_passthrough=True,
        match_case=True,
        match_whole_word=True,
        descriptor="Categorising",
        verbose=verbose,
    )

    if verbose:
        print("\nhost_category column:")
        report_ena_column(df, "host_category", 40, verbose=verbose)

        print("\n" + "=" * 60 + "\n")
    return df


def parse_isolation_source(df, verbose=True):
    """
    Parse isolation_source values into a normalized isolation_source_parsed column using search/replace rules.
    """
    if 'isolation_source' not in df.columns:
        if verbose:
            print("Warning: 'isolation_source' column not found in dataframe")
        return df

    df = df.copy()
    if verbose:
        print("\n" + "=" * 60)
        print("Isolation Source Parsing Report")
        print("=" * 60 + "\n")

    df['isolation_source_parsed'] = df['isolation_source']
    
    # Before collating, report on and replace invalid isolation sources
    patterns_to_replace = ["0", "missing", "not known", "not collected", "not available", "unclear", "others"]
    df = search_report_and_replace_with_na(
        df,
        source_col="isolation_source_parsed",
        target_col="isolation_source_parsed",
        patterns_to_replace=patterns_to_replace,
        verbose=verbose
    )

    rules = [
        # FIRST: Catch unhelpful clinical/hospital/facility labels before ANY other rules
        # These describe WHERE the sample was collected (hospital/lab) but not WHAT was sampled
        # Use (?i) for case-insensitive matching since match_case=True in function call
        {"search": r"(?i)clinical sample", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)clinical material", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)clinical isolate", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)clinical specimen", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)clinical speciment", "replace": "hospital or facility (unhelpful)"},  # misspelling
        {"search": r"(?i)clinical source", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)laboratory isolate", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)laboratory-generated", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)lab isolate", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)intensive care unit", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)\bICU\b", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)\bNICU\b", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)acute care hospital", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)intermediate-care facility", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)long-term care facility", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)hospital universitario", "replace": "hospital or facility (unhelpful)"},
        {"search": r"(?i)hospital univeristario", "replace": "hospital or facility (unhelpful)"},  # common misspelling
        {"search": r"(?i)facility [a-z]", "replace": "hospital or facility (unhelpful)"},  # Facility A, B, C, etc.
        {"search": r"(?i)faciility [a-z]", "replace": "hospital or facility (unhelpful)"},  # misspelling
        {"search": r"(?i)^isolate$", "replace": "hospital or facility (unhelpful)"},  # Just "Isolate" alone
        {"search": r"(?i)bacterial isolate", "replace": "hospital or facility (unhelpful)"},  # "Bacterial isolate specimen"
        {"search": r"(?i)^clinical$", "replace": "hospital or facility (unhelpful)"},  # Just "clinical" alone
        {"search": r"(?i)^hospital$", "replace": "hospital or facility (unhelpful)"},  # Just "hospital" alone (but not "hospital floor", etc.)
        {"search": r"(?i)^other sterile site$", "replace": "hospital or facility (unhelpful)"},  # Unhelpful descriptor
        {"search": r"(?i)^sterile fluid$", "replace": "hospital or facility (unhelpful)"},  # Just "sterile fluid" is unhelpful
        {"search": r"(?i)LB Medium", "replace": "hospital or facility (unhelpful)"},  # Lab medium, not actual source
        {"search": r"(?i)^sterile site$", "replace": "hospital or facility (unhelpful)"},  # Just "sterile site" is unhelpful
        {"search": r"(?i)^sterile$", "replace": "hospital or facility (unhelpful)"},  # Just "sterile" alone is unhelpful
        {"search": r"chilli", "replace": "plant"}, # to avoid alternative pickup
        {"search": r"soy sprout", "replace": "plant"},
        {"search": r"Ear canal secretions", "replace": "skin"},
        
        # This regex uses a positive lookahead (?=.*catheter) and (?=.*urin).
        # It will match any string that contains both the substring "catheter" and the substring "urin" (in any order and anywhere in the string).
        # For example, it matches: "urinary catheter tip", "catheter, urine", "sample from urin catheter".
        {"search": r"(?=.*catheter)(?=.*urin)", "replace": "UCS"},  # Using a code for urinary catheter - this is a temporary solution to avoid double counting

        {"search": r"blood", "replace": "blood"},  # Will include bloodstream etc
        {"search": r"bacteraemia", "replace": "blood"},  # Will include bloodstream etc
        {"search": r"bacteremia", "replace": "blood"},  # Will include bloodstream etc
        {"search": r"\bIV\b", "replace": "blood"},  # Must match whole word (case insensitive)
        {"search": r"CVC", "replace": "blood"},  # cvc
        {"search": r"intravenous", "replace": "blood"},  # IV access
        {"search": r"subclav", "replace": "blood"},  # subclavian vein catheter 
        {"search": r"hickman", "replace": "blood"},  # hickman catheter 
        {"search": r"cvp", "replace": "blood"},  # central venous pressure catheter
        {"search": r"permacath", "replace": "blood"},  # central venous pressure catheter
        {"search": r"Cath.V.O.S", "replace": "blood"},  # central venous pressure catheter
        {"search": r"picc", "replace": "blood"},  # peripherally inserted central catheter
        {"search": r"port", "replace": "blood"},  # port access
        {"search": r"venous", "replace": "blood"},  # Will include central venous
        {"search": r"disseminated", "replace": "disseminated infection"},  # Will include bloodstream etc
        {"search": r"BAL", "replace": "bronchoscopy"},
        {"search": r"bronch", "replace": "bronchoscopy"},
        {"search": r"bronquial", "replace": "bronchoscopy"},
        {"search": r"trachea", "replace": "tracheal/endotracheal"}, # Will include tracheal aspirate, trachea, tracheostomy etc
        {"search": r"traqueal", "replace": "tracheal/endotracheal"}, # Foreign language mispelling of tracheal
        {"search": r"endotracheal", "replace": "tracheal/endotracheal"},
        {"search": r"Endotrachial", "replace": "tracheal/endotracheal"},
        {"search": r"ET tip", "replace": "respiratory"}, # to avoid later confusion, be specific
        {"search": r"\bETT\b", "replace": "tracheal/endotracheal"},
        {"search": r"resp", "replace": "respiratory"}, # presume from lower
        {"search": r"sputum", "replace": "respiratory"},
        {"search": r"pharingeal", "replace": "respiratory"}, # mispelling of pharynx
        {"search": r"sputm", "replace": "respiratory"}, # mispelling of sputum
        {"search": r"lung", "replace": "respiratory"},
        {"search": r"airways", "replace": "respiratory"},
        {"search": r"sinus", "replace": "upper airway"},
        {"search": r"axillary swab", "replace": "skin swab"},
        {"search": r"laryngeal", "replace": "upper airway"},
        {"search": r"laryn", "replace": "upper airway"}, # Will catch laryngitis, laryngitis, laryngitis, larynx etc
        {"search": r"nasal", "replace": "upper airway"}, # Will include nasal swab, nasal etc 
        {"search": r"naso", "replace": "upper airway"}, # Will include nasal swab, nasal etc 
        {"search": r"phary", "replace": "upper airway"}, # Phyarynx, pharyngeal, pharyngitis, pharyngitis, pharynx etc
        {"search": r"lary", "replace": "upper airway"}, # Larynx, laryngitis, laryngitis, larynx etc
        {"search": r"throat", "replace": "upper airway"},
        {"search": r"tonsil", "replace": "upper airway"},  # Upper airway is more specific
        {"search": r"caecal", "replace": "caecum"},
        {"search": r"cecal", "replace": "caecum"},
        {"search": r"cecum", "replace": "caecum"},
        {"search": r"\bcanal\b", "replace": "wastewater & water"},  # Canal is a water channel, not rectum
        {"search": r"rectum", "replace": "rectal swab"},
        {"search": r"perianal", "replace": "upper perianal"}, 
        {"search": r"rectal", "replace": "rectal swab"},
        {"search": r"anus  ", "replace": "rectal swab"},
        {"search": r"stool", "replace": "faeces"},
        {"search": r"faeces", "replace": "faeces"},
        {"search": r"feces", "replace": "faeces"},
        {"search": r"faecal", "replace": "faeces"},
        {"search": r"fecal", "replace": "faeces"},
        {"search": r"screen", "replace": "rectal swab"},
        {"search": r"anal", "replace": "rectal swab"},
        {"search": r"surveil", "replace": "rectal swab"},  #Suveillance, surveillance, surveillance swab...
        {"search": r"carriage", "replace": "rectal swab"},  #Usually meaning patient was carrying it in their rectum
        {"search": r"wastewater", "replace": "wastewater & water"},
        {"search": r"HPB", "replace": "bilary"},
        {"search": r"gall", "replace": "bilary"},  # Gallbladder, gall stone, gall bladder, gallstone
        {"search": r"intestinal", "replace": "intestinal tract"},
        {"search": r"intestine", "replace": "intestinal tract"},
        {"search": r"internal_organs", "replace": "intestinal tract"},
        {"search": r"urine", "replace": "urine"},  
        {"search": r"urinary", "replace": "urine"}, # Will include 'urinary catheter
        {"search": r"wound", "replace": "wound"},  # Includes surgical wounds and superficial / trauma wounds, but will also catch ' wound at foot', 'wound at ...'
        {"search": r"abscess", "replace": "abscess"},
        {"search": r"abcess", "replace": "abscess"}, # mispelling
        {"search": r"inguinal", "replace": "inguinal"},  # Inguinal hernia 
        {"search": r"vagina", "replace": "vaginal"},  # Vaginal swab, vagina swab... all picked u
        {"search": r"skin", "replace": "skin"},  # skin swab.. all picked u
        {"search": r"burn", "replace": "skin burn"},  # skin swab.. all picked u
        {"search": r"tissue", "replace": "body tissue"},  # This will include all sorts of soft tissue samples
        {"search": r"bone", "replace": "bone"}, 
        {"search": r"ulcer", "replace": "ulcer"},  # make it case insensitive
        {"search": r"exudate", "replace": "exudate"},  # make it case insensitive
        {"search": r"ascitic", "replace": "ascitic, peritoneal, and pleural"}, 
        {"search": r"peritoneal", "replace": "ascitic, peritoneal"},
        {"search": r"Abdominal fluid", "replace": "ascitic, peritoneal, and pleural"},
        {"search": r"ascites", "replace": "ascitic, peritoneal, and pleural"},
        {"search": r"ascitic fluid", "replace": "ascitic, peritoneal, and pleural"},
        {"search": r"surgical", "replace": "surgical"},  # surgical site
        {"search": r"pleural", "replace": "ascitic, peritoneal, and pleural"},  # empyema
        {"search": r"CSF", "replace": "cerebrospinal"},  # Cerebrospinal fluid
        {"search": r"cerebrospinal", "replace": "cerebrospinal"},  # Cerebrospinal fluid
        {"search": r"cerebral", "replace": "cerebrospinal"},  # Cerebrospinal fluid
        {"search": r"spinal", "replace": "cerebrospinal"},  # Cerebrospinal fluid
        {"search": r"BIOPS", "replace": "biopsy"},  # Biopsy mispelled in one
        {"search": r"biopsy", "replace": "biopsy"},  # Any tissue biopsy
        {"search": r"surface", "replace": "surface (not specified)"},  # Unclear if this is clinical surface
        {"search": r"Patient or hospital wastewater site", "replace": None},
        {"search": r"Patients (Stored isolate from hospital lab)", "replace":None},
        {"search": r"\benv\b", "replace": "clinical environment"},  # environment, environmental, env swab...
        {"search": r"environmental", "replace": "clinical environment"},  # environment, environmental, env swab...
        {"search": r"envirom", "replace": "clinical environment"},  # mispelling
        {"search": r"sterile", "replace": "clinical environment"},  # environment, environmental, env swab...
        {"search": r"door", "replace": "clinical environment"},
        {"search": r"room", "replace": "clinical environment"},
        {"search": r"bedding", "replace": "clinical environment"},
        {"search": r"towel", "replace": "clinical environment"},
        {"search": r"floor", "replace": "clinical environment"},
        {"search": r"sink", "replace": "clinical environment"},
        {"search": r"WWTP", "replace": "wastewater & water"},
        {"search": r"effluent", "replace": "wastewater & water"},
        {"search": r"water", "replace": "wastewater & water"},  # This is a bit broad as it may not all be wastewater and we may want to split this out into wastewater and other water sources.
        {"search": r"stream sediment", "replace": "wastewater & water"},
        {"search": r"pond", "replace": "wastewater & water"},  # This is a bit broad as it may not all be wastewater and we may want to split this out into wastewater and other water sources.
        {"search": r"river", "replace": "wastewater & water"},  # This is a bit broad as it may not all be wastewater and we may want to split this out into wastewater and other water sources. 
        {"search": r"sewage", "replace": "sewage"},
        # Note: "animal" and "food" are too generic - handled in categorization function
        {"search": r"cloacal", "replace": "chicken anus"},
        {"search": r"meat", "replace": "meat"},
        {"search": r"butcher", "replace": "meat"},  # incl butcher table swab
        {"search": r"pig", "replace": "pig"},
        {"search": r"prawn", "replace": "prawn"},
        {"search": r"goat", "replace": "goat"},
        {"search": r"sheep", "replace": "sheep"},
        {"search": r"cow", "replace": "cow"},
        {"search": r"beef", "replace": "beef"},
        {"search": r"breast", "replace": "wound"},  # breast milk put with breast abscess/wound
        {"search": r"mastitis", "replace": "wound"},  # Presuming dairy milk not human milk. Ideally we would check study
        {"search": r"dairy", "replace": "dairy milk"}, # Includes dairy milk and dairy
        {"search": r"milk", "replace": "milk"}, # Includes dairy milk and dairy as well as Milk
        {"search": r"turkey", "replace": "turkey"},
        {"search": r"pork", "replace": "pork"}, # Includes dairy milk and dairy
        {"search": r"egg", "replace": "egg"},
        {"search": r"chicken", "replace": "chicken"},
        {"search": r"duck", "replace": "duck"},
        {"search": r"poultry", "replace": "chicken"},
        {"search": r"\bcalf\b", "replace": "calf"},
        {"search": r"\bsow\b", "replace": "sow"},
        {"search": r"(?i)cattle", "replace": "cow"},
        {"search": r"dog", "replace": "dog"},
        {"search": r"canine", "replace": "dog"},
        {"search": r"\bcat\b", "replace": "cats"},  # Whole word to prevent all catheters being cats
        {"search": r"(?i)fly", "replace": "fly"},
        {"search": r"(?i)wasp", "replace": "wasp"},
        {"search": r"(?i)worm", "replace": "worm"},
        {"search": r"(?i)bug", "replace": "insect"},  # Generic bug term
        {"search": r"(?i)forficula auricularia", "replace": "earwig"},  # Earwig species
        {"search": r"(?i)chalinolobus picatus", "replace": "bat"},  # Bat species
        {"search": r"(?i)lampropholis delicata", "replace": "lizard"},  # Skink species
        {"search": r"(?i)barn environment", "replace": "livestock environment"},
        {"search": r"(?i)liquid culture", "replace": "lab culture"},
        {"search": r"cheese", "replace": "cheese"},
        {"search": r"salad", "replace": "plant"},
        {"search": r"leafy greens", "replace": "plant"},
        {"search": r"plant", "replace": "plant"},
        {"search": r"(?i)rhizoplane", "replace": "rhizoplane"},  # Plant root surface
        {"search": r"(?i)rhizosphere", "replace": "rhizosphere"},  # Plant root zone
        {"search": r"(?i)endophytes", "replace": "endophyte"},  # Plant-associated microbes
        {"search": r"(?i)epiphytes", "replace": "epiphyte"},  # Plant surface microbes
        {"search": r"\bcrop\b", "replace": "invasive gut & organs"},  # Bird crop (digestive organ)
        {"search": r"soil", "replace": "soil"},
        {"search": r"^swab$", "replace": "swab (not specified)"},  # Only match standalone "swab" with nothing else
        {"search": r"aspirate", "replace": "aspirate (not specified)"},  # Non-specific aspirate
        {"search": r"pus", "replace": "pus (not specified)"},  # Non-specific secretion
        {"search": r"Swab insertion site", "replace": "skin"},  # skin swab
        {"search": r"drain", "replace": "drain"}, # Combine all other drains
        {"search": r"dranage fluid", "replace": "drain"}, # Mispelling
        {"search": r"patient", "replace": None}, # Combine all other patients - this is unlikely helpful
        {"search": r"human", "replace": None}, # Combine all other humans - this is unlikely helpful
        {"search": r"people", "replace": None}, # Combine all other humans - this is unlikely helpful
        {"search": r"body", "replace": None}, # Combine all other humans - this is unlikely helpful
        {"search": r"sapien", "replace": None}, # Combine all other sapien - this is unlikely helpful
        {"search": r"clinical", "replace": "hospital or facility (unhelpful)"}, # Catch-all for any remaining "clinical" 
        {"search": r"screening", "replace": "rectal swab"}, # Combine all other screenings - because studies are for klebsiella, screening refers to rectal swabs
        {"search": r"facility", "replace": "hospital or facility (unhelpful)"},  # Catch-all for "facility"
        {"search": r"hospital", "replace": "hospital or facility (unhelpful)"},  # Catch-all for "hospital"
        {"search": r"\bCentre\b", "replace": "hospital or facility (unhelpful)"},  # Catch-all for whole word "Centre"
        {"search": r"NICU", "replace": "hospital or facility (unhelpful)"},
        {"search": r"clinic", "replace": "hospital or facility (unhelpful)"},
        {"search": r"ward", "replace": "hospital or facility (unhelpful)"},
        {"search": r"laboratory", "replace": "hospital or facility (unhelpful)"},
        {"search": r"cockroach", "replace": "insect"},
        {"search": r"insect", "replace": "insect"},
        {"search": r"housefly", "replace": "insect"},
        {"search": r"mosquito", "replace": "insect"},
        {"search": r"biliar", "replace": "bilary"},  # biliar secretion, biliar aspirate
        {"search": r"gastrostom", "replace": "gut"},  # gastrostomy, gastrostomy secretion
        {"search": r"jejunostomy", "replace": "gut"},  # jejunostomy
        {"search": r"cabbage", "replace": "plant"},
        {"search": r"okra", "replace": "plant"},
        {"search": r"garam masala", "replace": "plant"},  # hot spice mixture
        {"search": r"spice", "replace": "plant"},
        {"search": r"groin", "replace": "groin swab"},
        {"search": r"periurethral", "replace": "periurethral swab"},
        {"search": r"umbilical", "replace": "umbilical swab"},
        {"search": r"nares", "replace": "upper airway"},  # nasal
        {"search": r"oral cavity", "replace": "upper airway"},
        {"search": r"mouth", "replace": "upper airway"},
        {"search": r"tongue", "replace": "upper airway"},
        {"search": r"pericardial", "replace": "pericardial fluid"},
        {"search": r"peritoneal fluid", "replace": "ascitic, peritoneal, and pleural"},
        {"search": r"peritoneum", "replace": "ascitic, peritoneal, and pleural"},
        {"search": r"puncture", "replace": "aspirate (not specified)"},  # puncture fluids
        {"search": r"secretion", "replace": "aspirate (not specified)"},  # non-specific secretion
        {"search": r"physical", "replace": "patient (unhelpful)"},  # unclear what this means
        {"search": r"lavage", "replace": "bronchoscopy"},  # lavage fluid
        {"search": r"dung", "replace": "faeces"},
        {"search": r"fece", "replace": "faeces"},  # misspelling
        {"search": r"sludge", "replace": "sewage"},
        {"search": r"root nodule", "replace": "plant"},
        {"search": r"litter", "replace": "faeces & rectal swabs"},  # Animal bedding/litter containing faeces
        {"search": r"brain", "replace": "cerebrospinal"},  # brain tissue/aspirate
        {"search": r"CNS", "replace": "cerebrospinal"},  # central nervous system
        {"search": r"synovial", "replace": "synovial fluid"},  # joint fluid
        {"search": r"joint", "replace": "synovial fluid"},
        {"search": r"fistula", "replace": "fistula"},  # body cavity connection
        {"search": r"lesion", "replace": "wound"},  # skin lesion
        {"search": r"decubitus", "replace": "wound"},  # pressure sore
        {"search": r"eye", "replace": "eye swab"},
        {"search": r"ear", "replace": "ear swab"},
        {"search": r"anus swab", "replace": "rectal swab"},
        {"search": r"anus", "replace": "rectal swab"},
        {"search": r"nose swab", "replace": "upper airway"},
        {"search": r"nose", "replace": "upper airway"},
        {"search": r"conjunctival", "replace": "eye swab"},
        {"search": r"surgical", "replace": "wound"},  # surgical site/wound
        {"search": r"sacrum", "replace": "wound"},  # sacral pressure ulcer
        {"search": r"decubitus", "replace": "wound"},  # pressure sore
        {"search": r"leg", "replace": "wound"},  # leg wound/ulcer
        {"search": r"hip", "replace": "wound"},  # hip wound
        {"search": r"line tip", "replace": "blood"}, # most line tips sent for culture are blood

        {"search": r"central line", "replace": "blood"},  # central venous line
        {"search": r"percutaneous", "replace": "aspirate (not specified)"},
        {"search": r"drainage fluid", "replace": "drain (other)"},
        {"search": r"dranage", "replace": "drain (other)"},  # misspelling of drainage
        {"search": r"superficial swab", "replace": "swab (not specified)"},
        {"search": r"sputm", "replace": "respiratory"},  # misspelling of sputum
        {"search": r"flypaper", "replace": "insect"},
        {"search": r"sweet potato", "replace": "plant"},
        {"search": r"beet", "replace": "plant"},
        {"search": r"root", "replace": "plant"},
        {"search": r"sediment", "replace": "wastewater & water"},
        {"search": r"urea", "replace": "urine"},
        {"search": r"care taker", "replace": "patient (unhelpful)"},
        {"search": r"foot", "replace": "wound"},  # foot wound/ulcer (diabetic foot etc)
        {"search": r"suction tip", "replace": "aspirate (not specified)"},
        {"search": r"gastric juice", "replace": "gut"},
        {"search": r"gastric", "replace": "gut"},
        {"search": r"plueral", "replace": "ascitic, peritoneal, and pleural"},  # misspelling of pleural
        {"search": r"faringeal", "replace": "upper airway"},  # misspelling of pharyngeal
        {"search": r"cervix", "replace": "vaginal"},
        {"search": r"sprout", "replace": "plant"},
        {"search": r"bed sheet", "replace": "clinical environment"},
        {"search": r"farm", "replace": "clinical environment"},  # or could be animal environment
        {"search": r"secreta", "replace": "aspirate (not specified)"},  # secretion
        {"search": r"pericardium", "replace": "pericardial fluid"},
        {"search": r"home of pet owner", "replace": "clinical environment"},
        {"search": r"perineum", "replace": "groin swab"},
        {"search": r"vagil", "replace": "vaginal"},  # misspelling
        {"search": r"muscle", "replace": "body tissue"},
        {"search": r"manure", "replace": "faeces"},
        {"search": r"physiatry", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"department", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"built", "replace": "clinical environment"},  # built environment
        {"search": r"wild bird", "replace": "bird"},
        {"search": r"grower feed", "replace": "food"},  # animal feed
        {"search": r"alar crease", "replace": "upper airway"},  # nasal area
        {"search": r"duodenoscope", "replace": "gut"},
        {"search": r"duedonoscope", "replace": "gut"},  # misspelling of duodenoscope
        {"search": r"reproductive tract", "replace": "genital swab"},
        {"search": r"fungus garden", "replace": "soil"},  # ant fungus gardens
        {"search": r"trakea", "replace": "tracheal/endotracheal"},  # misspelling of trachea
        {"search": r"trach swab", "replace": "tracheal/endotracheal"},
        {"search": r"peritone", "replace": "ascitic, peritoneal, and pleural"},  # peritoneal
        {"search": r"nephros", "replace": "kidney"},  # kidney
        {"search": r"bedsore", "replace": "wound"},  # pressure sore
        {"search": r"incision", "replace": "wound"},  # surgical incision
        {"search": r"shoe", "replace": "clinical environment"},
        {"search": r"microbial", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"diversion fluid", "replace": "drain (other)"},
        {"search": r"celery", "replace": "plant"},
        {"search": r"feedlot", "replace": "clinical environment"},  # animal environment
        {"search": r"amniotic fluid", "replace": "body fluid"},
        {"search": r"bodily fluid", "replace": "body fluid"},
        {"search": r"fluid", "replace": "body fluid"},  # catch remaining generic fluid references
        {"search": r"avian", "replace": None},  # Too generic, redundant with host
        {"search": r"suckler", "replace": "cow"},  # cattle
        {"search": r"horse", "replace": "horse"},
        {"search": r"tomato", "replace": "plant"},
        {"search": r"banana", "replace": "plant"},
        {"search": r"marjoram", "replace": "plant"},
        {"search": r"health care worker", "replace": "clinical environment"},
        {"search": r"telephone", "replace": "clinical environment"},
        {"search": r"monitor", "replace": "clinical environment"},
        {"search": r"ventilator", "replace": "clinical environment"},
        {"search": r"pooled swab", "replace": "swab (not specified)"},
        {"search": r"experimental", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"hydrothorax", "replace": "ascitic, peritoneal, and pleural"},  # pleural effusion
        {"search": r"malleolus", "replace": "wound"},  # ankle wound
        {"search": r"outer", "replace": "wound"},  # outer wound
        {"search": r"soli", "replace": "soil"},  # misspelling
        {"search": r"tracheostomic", "replace": "tracheal/endotracheal"},
        {"search": r"right pcn", "replace": "kidney"},  # percutaneous nephrostomy
        {"search": r"pcn", "replace": "kidney"},
        {"search": r"buttock", "replace": "wound"},
        {"search": r"gluteal", "replace": "wound"},
        {"search": r"scrotum", "replace": "genital swab"},
        {"search": r"knee", "replace": "wound"},
        {"search": r"scalp", "replace": "wound"},
        {"search": r"jaw", "replace": "wound"},
        {"search": r"arm", "replace": "wound"},
        {"search": r"back", "replace": "wound"},
        {"search": r"elbow", "replace": "wound"},
        {"search": r"coccyx", "replace": "wound"},
        {"search": r"spinous process", "replace": "wound"},  # spine area
        {"search": r"hematoma", "replace": "wound"},
        {"search": r"cyst", "replace": "wound"},
        {"search": r"graft site", "replace": "wound"},
        {"search": r"pilonidal", "replace": "wound"},  # pilonidal cyst
        {"search": r"chest tube", "replace": "drain (other)"},
        {"search": r"j-tube", "replace": "gut"},  # jejunostomy tube
        {"search": r"tracheostomy site", "replace": "tracheal/endotracheal"},
        {"search": r"urethral swab", "replace": "urine"},
        {"search": r"platelet bag", "replace": "blood"},
        {"search": r"wheel chair", "replace": "clinical environment"},
        {"search": r"walker", "replace": "clinical environment"},
        {"search": r"bed", "replace": "clinical environment"},
        {"search": r"kitchen sponge", "replace": "clinical environment"},
        {"search": r"hand swab", "replace": "skin"},
        {"search": r"swab sample", "replace": "swab (not specified)"},
        {"search": r"kiwi", "replace": "plant"},
        {"search": r"gulab jamun", "replace": "plant"},  # Indian sweet
        {"search": r"lb medium", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"experiment", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"enterobacteriaceae", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"vermicompost", "replace": "soil"},
        {"search": r"peat", "replace": "soil"},
        {"search": r"foetus", "replace": "body tissue"},
        {"search": r"fetus", "replace": "body tissue"},
        {"search": r"mare metritis", "replace": "horse"},  # mare is female horse
        {"search": r"stallion sperm", "replace": "horse"},  # stallion is male horse
        {"search": r"hill myna", "replace": "bird"},  # bird
        {"search": r"musca domestica", "replace": "insect"},  # housefly
        {"search": r"toe", "replace": "wound"},
        {"search": r"ankle", "replace": "wound"},
        {"search": r"labia", "replace": "vaginal"},
        {"search": r"spine", "replace": "wound"},
        {"search": r"tibia", "replace": "wound"},  # leg bone
        {"search": r"medulla", "replace": "bone"},  # bone marrow
        {"search": r"bubo", "replace": "wound"},  # swollen lymph node
        {"search": r"absces", "replace": "abscess"},  # misspelling
        {"search": r"ascities", "replace": "ascitic, peritoneal, and pleural"},  # misspelling of ascites
        {"search": r"asidic", "replace": "ascitic, peritoneal, and pleural"},  # misspelling
        {"search": r"oral swab", "replace": "upper airway"},
        {"search": r"sputamentum", "replace": "respiratory"},  # sputum
        {"search": r"pulmonary infection", "replace": "respiratory"},
        {"search": r"brocheal", "replace": "bronchoscopy"},  # misspelling
        {"search": r"airway specimen", "replace": "respiratory"},
        {"search": r"cornea", "replace": "eye swab"},
        {"search": r"ileostomy", "replace": "gut"},
        {"search": r"gizzard", "replace": "chicken"},  # chicken organ
        {"search": r"mink", "replace": "mink"},
        {"search": r"white-lipped deer", "replace": "deer"},
        {"search": r"black-collared starling", "replace": "bird"},
        {"search": r"call light", "replace": "clinical environment"},
        {"search": r"arterial line", "replace": "blood"},
        {"search": r"art line", "replace": "blood"},
        {"search": r"p-trap", "replace": "wastewater & water"},  # plumbing trap
        {"search": r"detergent", "replace": "clinical environment"},
        {"search": r"wash", "replace": "clinical environment"},
        {"search": r"mine", "replace": "clinical environment"},  # mining environment
        {"search": r"purulent-necrotic detritus", "replace": "wound"},
        {"search": r"discharge from", "replace": "wound"},
        {"search": r"excreted bodily substance", "replace": "body fluid"},
        {"search": r"punctate", "replace": "wound"},  # puncture
        {"search": r"conjugation assay", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"atcc standard strain", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"type strain", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"university", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"faculty", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"panda", "replace": "panda"},
        {"search": r"lake", "replace": "wastewater & water"},
        {"search": r"pavement", "replace": "clinical environment"},
        {"search": r"street", "replace": "clinical environment"},
        {"search": r"crude oil", "replace": "clinical environment"},
        {"search": r"paper tray", "replace": "clinical environment"},
        {"search": r"cage", "replace": "clinical environment"},
        {"search": r"rotten tea", "replace": "plant"},
        {"search": r"malanga", "replace": "plant"},  # root vegetable
        {"search": r"yam", "replace": "plant"},
        {"search": r"radish", "replace": "plant"},
        {"search": r"ginger", "replace": "plant"},
        {"search": r"graft", "replace": "wound"},
        {"search": r"pelvic", "replace": "wound"},
        {"search": r"intra-operative", "replace": "wound"},
        {"search": r"surgery swab", "replace": "wound"},
        {"search": r"donor site", "replace": "wound"},
        {"search": r"endotrachael", "replace": "tracheal/endotracheal"},  # misspelling
        {"search": r"urostomy", "replace": "urine"},
        {"search": r"urethra", "replace": "urine"},
        {"search": r"urethral_swab", "replace": "urine"},
        {"search": r"uterus", "replace": "vaginal"},
        {"search": r"uterine", "replace": "vaginal"},
        {"search": r"fourchette", "replace": "vaginal"},  # posterior part of vaginal opening
        {"search": r"umbilicus", "replace": "umbilical swab"},
        {"search": r"duct", "replace": "drain (other)"},
        {"search": r"plaque", "replace": "upper airway"},  # dental plaque
        {"search": r"air sac", "replace": "respiratory"},  # bird respiratory
        {"search": r"teat", "replace": "cattle"},  # udder of cow
        {"search": r"fat", "replace": "body tissue"},
        {"search": r"excreta", "replace": "faeces"},
        {"search": r"trach asp", "replace": "tracheal/endotracheal"},
        {"search": r"mediastinum", "replace": "body tissue"},  # chest cavity
        {"search": r"mediastinal", "replace": "body tissue"},
        {"search": r"ascending colon", "replace": "gut"},
        {"search": r"descending colon", "replace": "gut"},
        {"search": r"colon lumen", "replace": "gut"},
        {"search": r"colon mucosa", "replace": "gut"},
        {"search": r"addominal", "replace": "abdominal"},  # misspelling
        {"search": r"abdomi", "replace": "abdominal"},
        {"search": r"dreinage", "replace": "drain (other)"},  # misspelling of drainage
        {"search": r"subcutaneous flap", "replace": "wound"},
        {"search": r"sacral", "replace": "wound"},
        {"search": r"ingle", "replace": "groin swab"},  # inguinal
        {"search": r"amputated limb", "replace": "wound"},
        {"search": r"vulvar", "replace": "vaginal"},
        {"search": r"vulval", "replace": "vaginal"},
        {"search": r"tracheostomy_swab", "replace": "tracheal/endotracheal"},
        {"search": r"intraoperative_swab", "replace": "wound"},
        {"search": r"thoracic effusion", "replace": "ascitic, peritoneal, and pleural"},  # pleural effusion
        {"search": r"thoracic cavity", "replace": "body tissue"},
        {"search": r"illeosto", "replace": "gut"},  # ileostomy misspelling
        {"search": r"heel", "replace": "wound"},
        {"search": r"prothesis", "replace": "wound"},  # prosthesis misspelling
        {"search": r"prosthesis", "replace": "wound"},
        {"search": r"hick brown lumen", "replace": "blood"},  # hickman catheter
        {"search": r"kitchen", "replace": "clinical environment"},
        {"search": r"swab c/s", "replace": "swab (not specified)"},
        {"search": r"lab-derived", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"atcc", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"\btip\b", "replace": "blood"},  # Catch all other tip, likely blood culture (whole word match)
        {"search": r"catheter", "replace": "UCS"},  # Catch all other catheters, before cat rule can match

        # More scientific organism names - convert to common English names
        {"search": r"heteromyias albispecularis", "replace": "bird"},  # bird
        {"search": r"rhinoplocephalus nigrescens", "replace": "snake"},  # snake
        {"search": r"vespadelus darlingtoni", "replace": "bat"},  # bat
        {"search": r"lampropholis guichenoti", "replace": "lizard"},  # lizard
        {"search": r"haemoculture", "replace": "blood"},  # blood culture
        {"search": r"bllod", "replace": "blood"},  # misspelling
        {"search": r"decayed fruit", "replace": "plant"},
        {"search": r"jerusalem artichoke", "replace": "plant"},
        {"search": r"madhuca insignis", "replace": "plant"},  # tree
        {"search": r"garcinia xanthochymus", "replace": "plant"},  # tree
        {"search": r"salacia chinensis", "replace": "plant"},  # tree
        {"search": r"desmodium pulchellum", "replace": "plant"},  # plant
        {"search": r"leaf", "replace": "plant"},
        {"search": r"trolley handle", "replace": "clinical environment"},
        {"search": r"swab ileum conduit", "replace": "gut"},
        {"search": r"thoracic_effusion", "replace": "ascitic, peritoneal, and pleural"},
        {"search": r"seal", "replace": "seal"},
        # More scientific organism names - convert to common English names
        {"search": r"grallina cyanoleuca", "replace": "bird"},  # magpie-lark
        {"search": r"vanellus miles", "replace": "bird"},  # masked lapwing
        {"search": r"tachyglossus aculeatus", "replace": "echidna"},  # echidna
        {"search": r"dasycercus cristicauda", "replace": "quoll"},  # mulgara/eastern quoll
        {"search": r"sericornis citreogularis", "replace": "bird"},  # yellow-throated scrubwren
        {"search": r"gymnorhina tibicen", "replace": "bird"},  # australian magpie
        {"search": r"otorrhea", "replace": "ear swab"},  # ear discharge
        {"search": r"cot", "replace": "clinical environment"},
        {"search": r"bird", "replace": "bird"},
        {"search": r"^MHH\d+$", "replace": None},  # Match MHH followed by digits
        {"search": r"^MHS\d+$", "replace": None},  # Match MHS followed by digits
        {"search": r"^MBS\d+$", "replace": None},  # Match MBS followed by digits
        {"search": r"buccal swab", "replace": "upper airway"},  # cheek/mouth swab
        {"search": r"boerewors", "replace": "food"},  # South African sausage
        {"search": r"folyes tip", "replace": "urinary catheter"},  # Foley catheter
        {"search": r"foley", "replace": "urinary catheter"},
        {"search": r"big tank", "replace": None},  # lab equipment
        {"search": r"kp-s1", "replace": None},  # lab strain
        {"search": r"omvs", "replace": None},  # outer membrane vesicles - lab
        {"search": r"black creek park", "replace": None},  # location
        {"search": r"china: anhui", "replace": None},  # location
        {"search": r"p/u c\.tip", "replace": "urinary catheter"},
        {"search": r"^\?.*\?.*$", "replace": None},  # corrupted text with question marks
        {"search": r"brazil", "replace": None},  # just location name
        {"search": r"swab \(site:\)", "replace": "swab (not specified)"},
        {"search": r"stoma", "replace": "gut"},  # stoma swab (gastrostomy/colostomy opening)
        {"search": r"sacral swab", "replace": "wound"},  # sacral area wound
        {"search": r"spleen", "replace": "abdominal"},
        {"search": r"pancreatic", "replace": "abdominal"},
        {"search": r"perihepatic", "replace": "abdominal"},
        {"search": r"neck", "replace": "wound"},  # neck wound/abscess
        {"search": r"placenta", "replace": "body tissue"},
        {"search": r"vegetable", "replace": "plant"},
        {"search": r"parsley", "replace": "plant"},
        {"search": r"pepper", "replace": "plant"},
        {"search": r"cucumber", "replace": "plant"},
        {"search": r"burfi", "replace": "plant"},  # Indian sweet/confection
        {"search": r"swine", "replace": "pig"},
        {"search": r"laying hen", "replace": "chicken"},
        {"search": r"chevon", "replace": "goat"},  # goat meat
        {"search": r"papaya", "replace": "plant"},
        {"search": r"g-tube", "replace": "gut"},  # gastric tube
        {"search": r"neonatal", "replace": "patient (unhelpful)"},
        {"search": r"traumatic discharge", "replace": "wound"},
        {"search": r"donor organ", "replace": "body tissue"},
        {"search": r"retail market", "replace": None},
        {"search": r"pasture", "replace": 'faeces & rectal swabs'},
        {"search": r"cattle", "replace": None},
        # Scientific organism names (animals) - convert to common English names
        {"search": r"manis javanica", "replace": "pangolin"},  # pangolin
        {"search": r"rattus rattus", "replace": "rat"},  # rat
        {"search": r"antechinus stuartii", "replace": "marsupial mouse"},  # marsupial mouse
        {"search": r"dasyurus viverrinus", "replace": "quoll"},  # eastern quoll
        {"search": r"eopsaltria australis", "replace": "bird"},  # yellow robin
        {"search": r"trichosurus arhemensis", "replace": "possum"},  # possum
        {"search": r"vespadelus baverstocki", "replace": "bat"},  # bat
        {"search": r"sturnus nigricollis", "replace": "bird"},  # black-collared starling
        # Insect orders
        {"search": r"coleptera", "replace": "insect"},  # beetles
        {"search": r"coleoptera", "replace": "insect"},
        {"search": r"orthoptera", "replace": "insect"},  # grasshoppers/crickets
        {"search": r"lepidoptera", "replace": "insect"},  # butterflies/moths
        {"search": r"isopoda", "replace": "insect"},  # woodlice/crustaceans
        {"search": r"gene knockout", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"clot", "replace": "blood"},
        {"search": r"hvs", "replace": "vaginal"},  # high vaginal swab
        {"search": r"vagina", "replace": "vaginal"},  # Already had vaginal rule but ensure vagina caught
        {"search": r"cervic", "replace": "vaginal"},  # cervical, cervix
        {"search": r"penis", "replace": "genital swab"},
        {"search": r"genital", "replace": "genital swab"},
        {"search": r"inguinal", "replace": "groin swab"},  # inguinal is groin area
        {"search": r"kidney", "replace": "kidney"},
        {"search": r"pancreas", "replace": "abdominal"},
        {"search": r"liver", "replace": "liver"},  # can keep as liver for now
        {"search": r"gut", "replace": "gut"},
        {"search": r"bile", "replace": "biliary"},
        {"search": r"abdomen", "replace": "abdominal"}, 
        {"search": r"abdominal", "replace": "abdominal"},
        {"search": r"Cive", "replace": "plant"},  # chive mispelling? 
        {"search": r"Carot", "replace": "plant"}, # carrot
        {"search": r"shower", "replace": "clinical environment"},
        {"search": r"lettuce", "replace": "plant"},
        {"search": r"turnip", "replace": "plant"},
        {"search": r"carrot", "replace": "plant"},
        {"search": r"carcass", "replace": "food"},  # animal carcass/meat
        {"search": r"mollusc", "replace": "mollusc"},  # animal
        {"search": r"bivalve", "replace": "mollusc"},  # bivalves are molluscs
        {"search": r"expectorate", "replace": "respiratory"},  # expectorated sputum
        {"search": r"combined swab", "replace": "swab (not specified)"},
        {"search": r"medical device", "replace": "clinical environment"},
        {"search": r"lab strain", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"isolate", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"passage", "replace": "lab, hospital or facility (unhelpful)"},  # lab passage
        {"search": r"intensive care", "replace": "lab, hospital or facility (unhelpful)"},
        {"search": r"no data", "replace": "other (not specified)"},
        {"search": r"liquor", "replace": "other (not specified)"},  # unclear context
        {"search": r"not applicable", "replace": "other (not specified)"},
        {"search": r"not assigned", "replace": "other (not specified)"},
        {"search": r"not provided", "replace": "other (not specified)"},
        {"search": r"unknown", "replace": "other (not specified)"},
        {"search": r"^-$", "replace": "other (not specified)"},  # just a dash
        {"search": r"other", "replace": "other (not specified)"},
        {"search": r"no site specified", "replace": "other (not specified)"},
        {"search": r"undefined", "replace": "other (not specified)"},
        {"search": r"not detemined", "replace": "other (not specified)"},
        {"search": r"not determined", "replace": "other (not specified)"},
        {"search": r"collection", "replace": "other (not specified)"},
        {"search": r"no source specified", "replace": "other (not specified)"},
        {"search": r"biological sample", "replace": "other (not specified)"},
        {"search": r"restricted access", "replace": "other (not specified)"},
        {"search": r"unspecified", "replace": "other (not specified)"},
        {"search": r"\bNorth\b", "replace": "other (not specified)"},
        {"search": r"n\.d\.", "replace": "other (not specified)"},  # not determined
    ]

    df, _ = search_and_replace(
        df,
        source_col="isolation_source_parsed",
        target_col="isolation_source_parsed",
        rules=rules,
        match_case=False,
        default_passthrough=True,
        descriptor="Parsing",
        verbose=verbose,
    )

    # Step 3: Case-sensitive whole-word matching rules for abbreviations
    case_sensitive_whole_word_rules = [
        {"search": "UCS", "replace": "urinary catheter"}, # Renaming UCS to urinary catheter
        {"search": "UC", "replace": "urinary catheter"}, # Renaming UCS to urinary catheter
        {"search": "ETA", "replace": "respiratory"},
        {"search": "ET", "replace": "respiratory"},
        {"search": "ETT", "replace": "respiratory"},
        {"search": "SP", "replace": "respiratory"},
        {"search": "ST", "replace": "faeces"},
        {"search": "BS", "replace": "blood"},
        {"search": "BC", "replace": "blood"},
        {"search": "PS", "replace": "wound"},  # Patient swab, match whole word and case
        {"search": "WND", "replace": "wound"},  # Patient swab, match whole word and case
        {"search": "UR", "replace": "urine"},
        {"search": "BL", "replace": "blood"},
        {"search": "pus", "replace": "wound"},
        {"search": "GIT", "replace": "gut"},
        {"search": "env", "replace": "clinical environment"},  # Studies that use 'env' are invariably clinical environments, but ideally we would check each
        {"search": "PEG", "replace": "gut"},  # Peg tube
        {"search": "TRACH", "replace": "tracheal/endotracheal"},
        {"search": "Trach", "replace": "tracheal/endotracheal"},
        {"search": "SPU", "replace": "respiratory"},  # sputum
        {"search": "Sptum", "replace": "respiratory"},  # misspelling of sputum
        {"search": "SB", "replace": "blood"},
        {"search": "DTA", "replace": "tracheal/endotracheal"},
        {"search": "PA", "replace": "aspirate (not specified)"},
        {"search": "HIP", "replace": "wound"},
        {"search": "MSU", "replace": "urine"},  # mid-stream urine
        {"search": "ABSC", "replace": "abscess"},
        {"search": "CLI", "replace": "hospital or facility (unhelpful)"},  # Clinical isolate abbreviation - unhelpful
        {"search": "CLIN", "replace": "hospital or facility (unhelpful)"},  # Clinical abbreviation - unhelpful
        {"search": "INC", "replace": "hospital or facility (unhelpful)"},
        {"search": "Abd", "replace": "abdominal"},
        {"search": "Fld", "replace": "body fluid"},
        {"search": "LD", "replace": "drain (other)"},  # likely drain
        {"search": "SNS", "replace": "upper airway"},  # sinus
        {"search": "SCP", "replace": "aspirate (not specified)"},
        {"search": "BLC", "replace": "blood"},
        {"search": "PTC", "replace": "percutaneous drain"},
        # Lab-specific codes - set to None (will become NA in pandas)
        {"search": "ENRH", "replace": None},
        {"search": "MRV", "replace": None},
        {"search": "TTH", "replace": None},
        {"search": "ETS", "replace": None},
        {"search": "HWARE", "replace": None},
        {"search": "ka", "replace": None},
        {"search": "SITE", "replace": None},
        {"search": "KPN7", "replace": None},
        {"search": "ABD", "replace": "abdominal"},
        {"search": "WDSB", "replace": "wound"},
        {"search": "BUTTOCK", "replace": "wound"},
        {"search": "ACA", "replace": "body tissue"},  # anterior cerebral artery
        {"search": "TIP", "replace": "blood"}, # Most catheter tips sent for culture are blood
        {"search": "Skn", "replace": "skin"},
        {"search": "Thio", "replace": None},  # thioglycolate broth (lab medium)
        {"search": "CVC", "replace": "blood"},  # central venous catheter
        {"search": "SUR", "replace": "wound"},  # surgical
        {"search": "CM1", "replace": None},  # lab code
        {"search": "SCM1", "replace": None},  # lab code
        {"search": "SCM2", "replace": None},  # lab code
        {"search": "SCM3", "replace": None},  # lab code
        {"search": "SCM4", "replace": None},  # lab code
        {"search": "ORGAN", "replace": "body tissue"},
        {"search": "ORG", "replace": None},  # organism/lab code
        {"search": "EXUD", "replace": "exudate"},
        {"search": "BRONW", "replace": "bronchoscopy"},
        {"search": "TISSU", "replace": "body tissue"},
        # Lab codes (MHH, MHS, MBS series) - match with numbers
        {"search": r"MHH\d+", "replace": None}, 
        {"search": r"MHS\d+", "replace": None},
        {"search": r"MBS\d+", "replace": None},
        {"search": "UVC", "replace": "urinary catheter"},  # urinary vesicle (bladder) catheter
        {"search": "CL-BLD", "replace": "blood"},  # central line blood
    ]

    df, _ = search_and_replace(
        df,
        source_col="isolation_source_parsed",
        target_col="isolation_source_parsed",
        rules=case_sensitive_whole_word_rules,
        default_passthrough=True,
        match_case=True,
        match_whole_word=True,
        descriptor="Parsing",
        verbose=verbose,
    )

    if verbose:
        print("\nparsed isolation source column:")
        report_ena_column(df, "isolation_source_parsed", 40, verbose=verbose)

        print("\n" + "=" * 60 + "\n")
    
    # Clean up city/location names in isolation_source
    # If isolation_source appears to be a location and country has a value,
    # set isolation_source_parsed to NA (location info is already in country)
    if 'country' in df.columns or 'country_parsed' in df.columns:
        country_col = 'country_parsed' if 'country_parsed' in df.columns else 'country'
        
        # Known city/location names to clean up
        location_names = [
            'Zhejiang', 'Shanghai', 'Beijing', 'Guangzhou', 'Shenzhen', 'Hangzhou',
            'Lisbon', 'Porto', 'Madrid', 'Barcelona', 'Paris', 'London', 'Berlin',
            'Rome', 'Athens', 'Vienna', 'Prague', 'Budapest', 'Warsaw', 'Stockholm',
            'Copenhagen', 'Amsterdam', 'Brussels', 'Dublin', 'Helsinki', 'Oslo',
            'Moscow', 'St Petersburg', 'Kiev', 'Istanbul', 'Cairo', 'Lagos',
            'Nairobi', 'Johannesburg', 'Cape Town', 'Delhi', 'Mumbai', 'Bangalore',
            'Kolkata', 'Chennai', 'Hyderabad', 'Tokyo', 'Seoul', 'Bangkok', 'Singapore',
            'Manila', 'Jakarta', 'Sydney', 'Melbourne', 'Auckland', 'Wellington',
            'New York', 'Los Angeles', 'Chicago', 'Houston', 'Toronto', 'Montreal',
            'Vancouver', 'Mexico City', 'Sao Paulo', 'Rio de Janeiro', 'Buenos Aires',
            'Santiago', 'Lima', 'Bogota', 'Caracas', 'Havana', 'Anhui', 'Jiangsu',
            'Shandong', 'Henan', 'Sichuan', 'Hubei', 'Hunan', 'Fujian', 'Guangdong'
        ]
        
        for location in location_names:
            location_mask = (df['isolation_source_parsed'].notna() & 
                           (df['isolation_source_parsed'] == location))
            country_has_value = df[country_col].notna()
            
            cleanup_mask = location_mask & country_has_value
            cleanup_count = cleanup_mask.sum()
            
            if cleanup_count > 0:
                df.loc[cleanup_mask, 'isolation_source_parsed'] = pd.NA
                if verbose:
                    print(f"Cleaned up {cleanup_count:,} '{location}' entries in isolation_source (set to NA, location in country column)")
    
    # Automatically create isolation_source_category
    df = categorise_isolation_source(df, verbose=verbose)
    
    return df


def categorise_isolation_source(df, verbose=True):
    """
    Map isolation_source_parsed values to broad categories.
    Maps to categories: blood, urine, respiratory, faeces & gut, wound, body_fluid,
    clinical_environment, wastewater & water, animal_product, plant_product.
    """
    source_col = "isolation_source_parsed" if "isolation_source_parsed" in df.columns else "isolation_source"
    if source_col not in df.columns:
        if verbose:
            print("Warning: source isolation_source column not found in dataframe")
        return df
    if source_col == "isolation_source":
        if verbose:
            print("categorise_isolation_source requires isolation_source_parsed; running isolation source parsing first.")
        df = parse_isolation_source(df, verbose=verbose)
        source_col = "isolation_source_parsed"

    df = df.copy()
    if verbose:
        print("\n" + "=" * 60)
        print("Isolation Source Category Categorisation Report")
        print("=" * 60 + "\n")

    df["isolation_source_category"] = df[source_col]

    rules = [
        { # Blood
            "search": "blood|disseminated infection", 
            "replace": "blood"
        },
        { # Urine (include all variations)
            "search": "urine", 
            "replace": "urine"
        },
        { # Urinary catheter (include all variations)
            "search": "urinary catheter", 
            "replace": "urinary catheter"
        },
        { # Upper Respiratory
            "search": "upper airway",
            "replace": "upper airway",
        },
        { # Lower Respiratory & Endotracheal
            "search": "bronchoscopy|tracheal/endotracheal|respiratory",
            "replace": "lower respiratory, endotracheal",
        },
        { # Faeces & Rectal
            "search": "gut|caecum|rectal|faeces|perianal", 
            "replace": "faeces & rectal swabs"
        },
        { # Bilary & Intestinal Tract & Abdominal & Liver & Kidney
            "search": "bilary|biliary|intestinal tract|abdominal|liver|kidney",
            "replace": "invasive gut & organs",
        },
        { # Invasive body fluids (deep cavities)
            "search": "pericardial fluid|synovial fluid|cerebrospinal",
            "replace": "invasive body fluid (pericardial, synovial, CSF)",
        },
        { # Body fluid (ascites/peritoneal/pleural)
            "search": "body fluid|abdominal fluid|ascitic|peritoneal|pleural|drain",
            "replace": "body fluid (ascites / peritoneal / pleural)",
        },
        { # Wound & deep tissue & drains
            "search": "wound|abscess|body tissue|bone|biopsy|ulcer|exudate|fistula|drain|percutaneous drain|aspirate",
            "replace": "wound & pus, abscess, surgical drain, body tissue, bone, biopsy",
        },
        { # Surface swabs (skin surface, groin, vaginal, eye, ear, genital) - NOT wounds
            "search": "skin|skin burn|groin swab|vaginal|periurethral swab|umbilical swab|eye swab|ear swab|genital swab|axilla",
            "replace": "skin swabs (skin, groin, vaginal, genital, eye, ear)",
        },
        { # Unhelpful - matches the exact parsed token from parsing step
            # Since parsing already converts all unhelpful terms to this exact token,
            # we only need to match this one token here (not individual words)
            # The '\\' in the string is an escape character for the parentheses.
            # In regular expressions, '(' and ')' are special characters (used for grouping).
            # To literally match the character '(', it must be escaped as '\(' in the regex.
            # In a Python string, a backslash itself must be escaped, so one writes '\\('.
            # Thus, 'hospital or facility \\(unhelpful\\)' matches the literal text:
            # "hospital or facility (unhelpful)"
            "search": "hospital or facility \\(unhelpful\\)", 
            "replace": "lab, hospital or facility (unhelpful)"},
        { # Clinical environment or surface
            # Matches parsed environmental tokens (not standalone "hospital"/"facility" which are parsed as unhelpful)
            "search": "surface|environment|Environment|sink|door|room|floor|bedding|towel",
            "replace": "clinical environment or surface",
        },
        { # Wastewater
            "search": "wastewater|water|sewage", 
            "replace": "wastewater & water"
        },
        { # Birds (non-poultry) - matching host category
            "search": "bird|avian|pigeon|finch|crow|canary|gull|starling|myna|robin|magpie|scrubwren|lapwing",
            "replace": "wild birds",
        },
        { # Animals (other) - matching host category
            "search": "animal|primate|elephant|kangaroo|rabbit|mouse|rodent|deer|bear|lizard|turtle|hare|monkey|donkey|seal|seabird|toad|fruit bat|mussel|giant panda|wild rat|reptiles|snake|bat|echidna|quoll|possum|pangolin|rat|marsupial mouse|mink|panda|mollusc|seal|prawn",
            "replace": "wild animals",
        },
        { # Grazing livestock - matching host category
            "search": "cow|sheep|pig|goat|livestock|horse|suckler|calf|sow",
            "replace": "grazing livestock & horses",
        },
        { # Poultry livestock - matching host category
            "search": "chicken|broiler|poultry|turkey|duck|guinea fowl|peafowl|quail|chicks",
            "replace": "poultry livestock",
        },
        { # Domestic animals - matching host category
            # Use "cats" (plural) to avoid matching "catheter"
            "search": "dog|cats|canine",
            "replace": "domestic animals",
        },
        { # Food (processed animal products, meat, dairy, eggs, seafood)
            "search": "meat|beef|pork|dairy milk|milk|egg|food|Food|boerewors|carcass|grower feed|Animal feed|seafood|Mus musculus|Animal-Calf|Food-waste compost|cheese",
            "replace": "meat products",
        },
        { # Vegetable, plant or soil - matching host category
            "search": "plant|soil|salad|banana|lettuce|carrot|brassica|sweet potato|onion|beet|bean|pepper|parsley|cucumber|eggplant|tannia|radish|dioscorea|ginger|helianthus|tree|plantain|mulberry|vegetable|celery|tomato|marjoram|papaya|burfi|chilli|kiwi|gulab jamun|vermicompost|peat|rotten tea|malanga|yam|jerusalem artichoke|madhuca insignis|garcinia xanthochymus|salacia chinensis|desmodium pulchellum|leaf|decayed fruit|rhizoplane|rhizosphere|endophyte|epiphyte",
            "replace": "vegetable, plant or soil",
        },
        { # Insect
            "search": "insect|fly|wasp|worm|earwig",
            "replace": "insect"
        },
        { # Livestock/farm environment
            "search": "livestock environment",
            "replace": "clinical environment or surface",
        },
        { # Lab culture - unhelpful
            "search": "lab culture",
            "replace": "lab, hospital or facility (unhelpful)",
        },
    ]

    df, _ = search_and_replace(
        df,
        source_col=source_col,
        target_col="isolation_source_category",
        rules=rules,
        default_passthrough=True,
        match_case=True,
        match_whole_word=True,
        descriptor="Categorising",
        verbose=verbose,
    )

    if verbose:
        print("\nisolation_source_category column:")
        report_ena_column(df, "isolation_source_category", 40, verbose=verbose)

        print("\n" + "=" * 60 + "\n")
    
    return df


def normalize_missing_values(df, columns, verbose=True):
    """
    Normalize all types of missing values (pd.NA, np.nan, None) to pd.NA.
    
    This ensures consistent handling of missing values throughout the pipeline
    and prevents duplicate "Missing/NA" entries in value_counts().
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame to normalize
    columns : list
        List of column names to normalize
    verbose : bool, default=True
        If True, print information about normalization
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with normalized missing values
    """
    df = df.copy()
    
    for col in columns:
        if col not in df.columns:
            continue
        
        # Count different types of missing before normalization
        original_na_count = df[col].isna().sum()
        
        # Replace all missing-like values with pd.NA
        # This catches pd.NA, np.nan, None, and potentially string "nan"
        mask = df[col].isna() | (df[col].astype(str).str.lower() == 'nan')
        df.loc[mask, col] = pd.NA
        
        if verbose:
            final_na_count = df[col].isna().sum()
            if original_na_count != final_na_count:
                print(f"Normalized {col}: {original_na_count} -> {final_na_count} missing values")
    
    return df


def reconcile_host_and_isolation_source(df, verbose=True):
    """
    Reconcile inconsistencies between host and isolation_source columns.
    
    This function:
    1. Removes 'patient (unhelpful)' isolation_source_category when host is human
    2. Sets host to 'human' when isolation_source indicates human clinical samples (blood, urine, respiratory)
       but host is missing
    3. Infers host_category from isolation_source_category ONLY when host_category is NA
       - Uses highly specific isolation sources that are >99% associated with a particular host type
       - Does NOT modify existing host_category values (only fills in missing ones)
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with host and isolation_source columns
    verbose : bool, default=True
        If True, print cleanup information
        
    Returns:
    --------
    pd.DataFrame
        Modified dataframe with reconciled host and isolation_source
    """
    if 'isolation_source_category' not in df.columns:
        if verbose:
            print("Warning: 'isolation_source_category' column not found")
        return df
    
    df = df.copy()
    
    if verbose:
        print("\n" + "=" * 60)
        print("Reconciling Host and Isolation Source")
        print("=" * 60 + "\n")
    
    # 1. Clean up "patient (unhelpful)" when host is human - set to NA
    patient_unhelpful_mask = (df['isolation_source_category'] == 'patient (unhelpful)') | (df['isolation_source_category'] == 'swab (not specified)')
    patient_unhelpful_count = patient_unhelpful_mask.sum()
    
    if patient_unhelpful_count > 0:
        df.loc[patient_unhelpful_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Cleaned up {patient_unhelpful_count:,} 'patient (unhelpful)' entries (set isolation_source_category to NA)")
    
    # 1b. Clean up unhelpful hospital/facility labels - these don't tell us the anatomical source
    # They only indicate the sample came from a hospital/lab setting, which we capture in study_setting instead
    # Catch both the parsed token and the categorized version (use exact matches, not substring)
    hospital_unhelpful_mask = (
        (df['isolation_source_category'] == 'lab, hospital or facility (unhelpful)') |
        (df['isolation_source_category'] == 'hospital or facility (unhelpful)')
    )
    hospital_unhelpful_count = hospital_unhelpful_mask.sum()

    # Debug: print unique values if no matches found but we expect some
    if hospital_unhelpful_count == 0 and verbose:
        # Check what values actually exist
        unique_vals = df['isolation_source_category'].value_counts().head(20)
        unhelpful_vals = [v for v in unique_vals.index if pd.notna(v) and ('unhelpful' in str(v).lower() or 'hospital' in str(v).lower())]
        if unhelpful_vals:
            print(f"DEBUG: No hospital/facility unhelpful matches found, but found these similar values: {unhelpful_vals[:5]}")
    
    if hospital_unhelpful_count > 0:
        # Set study_setting to "Hospital" to preserve location information
        if 'study_setting' in df.columns:
            df.loc[hospital_unhelpful_mask, 'study_setting'] = 'Hospital'
        # Clear the unhelpful isolation_source_category
        df.loc[hospital_unhelpful_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Cleaned up {hospital_unhelpful_count:,} unhelpful hospital/facility entries (set study_setting to 'Hospital' and isolation_source_category to NA)")

    # 2. Set host to 'human' when isolation_source indicates human clinical samples but host is missing
    # Check for blood, urine, or respiratory isolation sources
    human_source_mask = (
        df['isolation_source_category'].notna() & 
        (df['isolation_source_category'].str.contains('blood|urine|respiratory|airway', case=False, na=False))
    )
    
    # Check for missing host values: both pd.NA and string "Missing" (case-insensitive, with whitespace)
    host_is_na = df['host'].isna()
    host_is_missing_string = (
        df['host'].notna() & 
        df['host'].astype(str).str.strip().str.lower().isin(['missing', ''])
    )
    host_missing_mask = host_is_na | host_is_missing_string
    
    set_human_mask = human_source_mask & host_missing_mask
    set_human_count = set_human_mask.sum()
    
    if set_human_count > 0:
        df.loc[set_human_mask, 'host'] = 'human'
        df.loc[set_human_mask, 'host_parsed'] = 'human'
        df.loc[set_human_mask, 'host_category'] = 'human'
        if verbose:
            print(f"Set host to 'human' for {set_human_count:,} samples with clinical isolation sources (blood/urine/respiratory) but missing host")
            if host_is_missing_string.sum() > 0:
                print(f"  Note: {host_is_missing_string.sum():,} of these had string 'Missing' instead of pd.NA")
    
    # 3. Infer host_category from isolation_source_category when host_category is NA
    # Check for NA host_category
    host_cat_is_na = df['host_category'].isna()
    
    # 3a. Wastewater & water
    wastewater_mask = (
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'wastewater & water')
    )
    wastewater_count = wastewater_mask.sum()
    if wastewater_count > 0:
        df.loc[wastewater_mask, 'host_category'] = 'wastewater & water'
        if verbose:
            print(f"Set host_category to 'wastewater & water' for {wastewater_count:,} samples based on isolation_source_category")
    
    # 3b. Clinical environment or surface
    clinical_env_mask = (
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'clinical environment or surface')
    )
    clinical_env_count = clinical_env_mask.sum()
    if clinical_env_count > 0:
        df.loc[clinical_env_mask, 'host_category'] = 'clinical environment or surface'
        if verbose:
            print(f"Set host_category to 'clinical environment or surface' for {clinical_env_count:,} samples based on isolation_source_category")
    
    # 3c. Human clinical sources (blood, patient, lower respiratory/endotracheal, urine, wound, body fluid, invasive gut)
    # NOTE: These are highly specific to humans (>99% human)
    human_clinical_mask = (
        host_cat_is_na & # Use this as avoid overriding existing host_category values
        df['isolation_source_category'].notna() &
        df['isolation_source_category'].str.contains(
            'blood|patient|lower respiratory, endotracheal|urine|wound|body fluid|invasive gut|urinary catheter|skin swabs',
            case=False, na=False
        )
    )
    human_clinical_count = human_clinical_mask.sum()
    if human_clinical_count > 0:
        df.loc[human_clinical_mask, 'host_category'] = 'human'
        if verbose:
            print(f"Set host_category to 'human' for {human_clinical_count:,} samples based on highly human-specific isolation_source_category")
    
    # 3d. Vegetable, plant or soil
    vegetable_mask = (
        df['isolation_source_category'].notna() &
        df['isolation_source_category'].str.contains('soil', case=False, na=False)
    )
    vegetable_count = vegetable_mask.sum()
    if vegetable_count > 0:
        df.loc[vegetable_mask, 'host_category'] = 'vegetable, plant or soil'
        if verbose:
            print(f"Set host_category to 'vegetable, plant or soil' for {vegetable_count:,} samples based on isolation_source_category")
    
    # 3e. meat products (case-insensitive to catch "meat products" and "meat products")
    food_mask = (
        df['isolation_source_category'].notna() &
        df['isolation_source_category'].str.lower().str.contains('meat products|seafood', case=False, na=False)
    )
    food_count = food_mask.sum()
    if food_count > 0:
        df.loc[food_mask, 'host_category'] = 'meat products'
        if verbose:
            print(f"Set host_category to 'meat products' for {food_count:,} samples based on isolation_source_category")
    
    # 3f. Poultry livestock
    poultry_mask = (
        host_cat_is_na &
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'poultry livestock')
    )
    poultry_count = poultry_mask.sum()
    if poultry_count > 0:
        df.loc[poultry_mask, 'host_category'] = 'poultry livestock'
        if verbose:
            print(f"Set host_category to 'poultry livestock' for {poultry_count:,} samples based on isolation_source_category")
    
    # 3g. Domestic animals
    dogs_cats_mask = (
        host_cat_is_na &
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'domestic animals')
    )
    dogs_cats_count = dogs_cats_mask.sum()
    if dogs_cats_count > 0:
        df.loc[dogs_cats_mask, 'host_category'] = 'domestic animals'
        if verbose:
            print(f"Set host_category to 'domestic animals' for {dogs_cats_count:,} samples based on isolation_source_category")
    
    # 3h. Animals (other)
    animals_mask = (
        host_cat_is_na &
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'wild animals')
    )
    animals_count = animals_mask.sum()
    if animals_count > 0:
        df.loc[animals_mask, 'host_category'] = 'wild animals'
        if verbose:
            print(f"Set host_category to 'wild animals' for {animals_count:,} samples based on isolation_source_category")
    
    # 3i. Grazing livestock (when it appears in isolation_source_category)
    grazing_mask = (
        host_cat_is_na &
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'grazing livestock & horses')
    )
    grazing_count = grazing_mask.sum()
    if grazing_count > 0:
        df.loc[grazing_mask, 'host_category'] = 'grazing livestock & horses'
        if verbose:
            print(f"Set host_category to 'grazing livestock & horses' for {grazing_count:,} samples based on isolation_source_category")
    
    # 3j. Birds (other)
    birds_mask = (
        host_cat_is_na &
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'wild birds')
    )
    birds_count = birds_mask.sum()
    if birds_count > 0:
        df.loc[birds_mask, 'host_category'] = 'wild birds'
        if verbose:
            print(f"Set host_category to 'wild birds' for {birds_count:,} samples based on isolation_source_category")
    
    # 3k. Insect
    insect_mask = (
        host_cat_is_na &
        df['isolation_source_category'].notna() &
        (df['isolation_source_category'] == 'insect')
    )
    insect_count = insect_mask.sum()
    if insect_count > 0:
        df.loc[insect_mask, 'host_category'] = 'insect'
        if verbose:
            print(f"Set host_category to 'insect' for {insect_count:,} samples based on isolation_source_category")
    
    # 4. Fix specific cases: shellfish hosts with "patient (unhelpful)" should be recategorized
    # Species like Mytilus edulis, Crassostrea gigas, Pecten maximus are shellfish, not patients
    shellfish_species = ['mytilus', 'crassostrea', 'pecten', 'oyster', 'mussel', 'scallop', 'clam']
    shellfish_mask = (
        df['host'].notna() &
        df['host'].str.lower().str.contains('|'.join(shellfish_species), case=False, na=False) &
        (df['isolation_source_category'] == 'patient (unhelpful)')
    )
    shellfish_count = shellfish_mask.sum()
    if shellfish_count > 0:
        # Reclassify as wild animals instead of patient
        df.loc[shellfish_mask, 'isolation_source_category'] = 'wild animals'
        if verbose:
            print(f"Fixed {shellfish_count:,} shellfish samples: changed isolation_source_category from 'patient (unhelpful)' to 'wild animals'")
    
    # 5. Fix specific cases: insect hosts with "patient (unhelpful)" should be recategorized
    # Insects like fly, snail, worm, spider with "body" isolation_source are not patients
    insect_mask = (
        df['host_category'] == 'insect') & (df['isolation_source_category'] == 'patient (unhelpful)'
    )
    insect_count = insect_mask.sum()
    if insect_count > 0:
        # Reclassify as insect instead of patient
        df.loc[insect_mask, 'isolation_source_category'] = 'insect'
        if verbose:
            print(f"Fixed {insect_count:,} insect samples: changed isolation_source_category from 'patient (unhelpful)' to 'insect'")
    
    
    # 7. Fix clinical environment misclassifications
    # Sometimes "environment" or "environmental" host is used incorrectly for meat products, animals, or human samples

    # Other (not specified) as category - just make NA
    other_not_specified_mask = (
        (df['isolation_source_category'] == 'other (not specified)')
    )
    other_not_specified_count = other_not_specified_mask.sum()
    if other_not_specified_count > 0:
        df.loc[other_not_specified_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Fixed {other_not_specified_count:,} samples: changed isolation_source_category from 'other (not specified)' to NA")

    # 7a. Clinical environment + meat products isolation → should be meat products host
    env_food_mask = (
        (df['host_category'] == 'clinical environment or surface') &
        (df['isolation_source_category'] == 'meat products')
    )
    env_food_count = env_food_mask.sum()
    if env_food_count > 0:
        df.loc[env_food_mask, 'host_category'] = 'meat products'
        if verbose:
            print(f"Fixed {env_food_count:,} samples: changed host_category from 'clinical environment or surface' to 'meat products' based on meat products isolation source")
    
    # 7b. Clinical environment + poultry isolation → should be poultry host
    env_poultry_mask = (
        (df['host_category'] == 'clinical environment or surface') &
        (df['isolation_source_category'] == 'poultry livestock')
    )
    env_poultry_count = env_poultry_mask.sum()
    if env_poultry_count > 0:
        df.loc[env_poultry_mask, 'host_category'] = 'poultry livestock'
        if verbose:
            print(f"Fixed {env_poultry_count:,} samples: changed host_category from 'clinical environment or surface' to 'poultry livestock'")
    
    # 7c. Clinical environment + wastewater & water → should be wastewater host
    # Hospital wastewater should be categorized as wastewater, not clinical environment
    # Study setting will track that it's from a hospital
    env_wastewater_mask = (
        (df['host_category'] == 'clinical environment or surface') &
        (df['isolation_source_category'] == 'wastewater & water')
    )
    env_wastewater_count = env_wastewater_mask.sum()
    if env_wastewater_count > 0:
        df.loc[env_wastewater_mask, 'host_category'] = 'wastewater & water'
        df.loc[env_wastewater_mask, 'study_setting'] = 'Hospital'
        if verbose:
            print(f"Fixed {env_wastewater_count:,} samples: changed host_category from 'clinical environment or surface' to 'wastewater & water'")
    
    # 7d. Clinical environment + faeces & rectal swabs → likely human (rectal swabs are from humans)
    # Check original isolation_source to see if it contains "rectal swab"
    env_faeces_mask = (
        (df['host_category'] == 'clinical environment or surface') &
        (df['isolation_source_category'] == 'faeces & rectal swabs') &
        df['isolation_source'].notna() &
        df['isolation_source'].str.contains('rectal swab', case=False, na=False)
    )
    env_faeces_count = env_faeces_mask.sum()
    if env_faeces_count > 0:
        df.loc[env_faeces_mask, 'host_category'] = 'human'
        if verbose:
            print(f"Fixed {env_faeces_count:,} samples: changed host_category from 'clinical environment or surface' to 'human' for rectal swabs")
    
    # 7e. Human + clinical environment or surface isolation → should be clinical environment host
    # If isolation source is from hospital surfaces/environment, the host should be clinical environment, not human
    human_clinical_env_mask = (
        (df['host_category'] == 'human') &
        df['isolation_source_category'].notna() &
        df['isolation_source_category'].str.contains('clinical environment', case=False, na=False)
    )
    human_clinical_env_count = human_clinical_env_mask.sum()
    if human_clinical_env_count > 0:
        df.loc[human_clinical_env_mask, 'host_category'] = 'clinical environment or surface'
        df.loc[human_clinical_env_mask, 'study_setting'] = 'Hospital'
        if verbose:
            print(f"Fixed {human_clinical_env_count:,} samples: changed host_category from 'human' to 'clinical environment or surface' based on clinical environment isolation source")
    
    # 7f. Human + wastewater isolation → should be wastewater host
    # If isolation source is wastewater, the host should be wastewater, not human
    human_wastewater_mask = (
        (df['host_category'] == 'human') &
        df['isolation_source_category'].notna() &
        df['isolation_source_category'].str.contains('wastewater', case=False, na=False)
    )
    human_wastewater_count = human_wastewater_mask.sum()
    if human_wastewater_count > 0:
        df.loc[human_wastewater_mask, 'host_category'] = 'wastewater & water'
        if verbose:
            print(f"Fixed {human_wastewater_count:,} samples: changed host_category from 'human' to 'wastewater & water' based on wastewater isolation source")
    
    # 8. Force alignment of isolation_source_category for specific host categories
    # For these hosts, the isolation source should always match the host
    categories_to_align = ["clinical environment or surface", "insect", "meat products", "vegetable, plant or soil", "wastewater & water"]
    # 8a. Clinical environment or surface, insect, meat products, vegetable, plant or soil, wastewater & water: align isolation_source_category with host_category
    for cat in categories_to_align:
        mask = (df['host_category'] == cat)
        n = (mask & (df['isolation_source_category'] != cat)).sum()
        if n > 0:
            df.loc[mask, 'isolation_source_category'] = cat
            if verbose:
                print(f"Fixed {n:,} {cat!r} samples: aligned isolation_source_category with host_category")

    # Vice versa: if isolation_source_category is one of these, host_category must match
    for cat in categories_to_align:
        iso_mask = (df['isolation_source_category'] == cat)
        n = (iso_mask & (df['host_category'] != cat)).sum()
        if n > 0:
            df.loc[iso_mask, 'host_category'] = cat
            if verbose:
                print(f"Fixed {n:,} {cat!r} samples: aligned host_category with isolation_source_category")


    # 8c. Clear redundant isolation_source_category when it duplicates host_category
    # For animal host categories, if isolation_source_category is the same, set to NA
    # 
    # BIOLOGICAL RATIONALE:
    # When a sample comes from an animal host (e.g., chicken), and the isolation_source
    # just describes the same animal (e.g., "poultry livestock"), the isolation_source_category
    # is redundant and uninformative. The host_category is sufficient to capture this information.
    # 
    # In contrast, if isolation_source provides additional specific anatomical/clinical detail
    # (e.g., "faeces", "blood", "respiratory"), that should be preserved in isolation_source_category
    # because it adds meaningful information beyond just knowing the host species.
    # 
    # This rule applies to animal-type hosts but NOT to environmental hosts like 
    # "wastewater & water" or "vegetable, plant or soil", which are handled separately
    # to ensure host and isolation source always match.
    redundant_iso_source_category = [
        'poultry livestock',
        'grazing livestock & horses',
        'domestic animals',
        'wild birds',
        'wild animals',
    ]
    
    clear_count = 0
    for category in redundant_iso_source_category:
        mask = (df['host_category'] == category) & (df['isolation_source_category'] == category)
        count = mask.sum()
        if count > 0:
            df.loc[mask, 'isolation_source_category'] = pd.NA
            clear_count += count
    
    if verbose and clear_count > 0:
        print(f"Cleared {clear_count:,} redundant isolation_source_category values that duplicated host_category")
    
    # 8d. Clear "clinical environment or surface" for animal hosts
    # Clinical environment should only be hospital/clinic bugs, not animal samples
    # Exception: insects in hospitals ARE valid (literally bugs in clinical environments)
    animal_clinical_hosts = [
        'grazing livestock & horses',
        'domestic animals',
        'wild animals',
        'poultry livestock',
        'fish',
        'wild birds',
    ]
    
    animal_clinical_count = 0
    for host_cat in animal_clinical_hosts:
        mask = (df['host_category'] == host_cat) & (df['isolation_source_category'] == 'clinical environment or surface')
        count = mask.sum()
        if count > 0:
            df.loc[mask, 'isolation_source_category'] = pd.NA
            animal_clinical_count += count
    
    if verbose and animal_clinical_count > 0:
        print(f"Cleared {animal_clinical_count:,} 'clinical environment or surface' values for animal hosts (keeping insects)")
    
    # 8e. Fix specific host-isolation mismatches (set isolation_source_category to NA)
    # Small number of edge cases where isolation_source_category doesn't match host_category
    
    # wild animals with grazing livestock & horses isolation
    animals_grazing_mask = (
        (df['host_category'] == 'wild animals') &
        (df['isolation_source_category'] == 'grazing livestock & horses')
    )
    animals_grazing_count = animals_grazing_mask.sum()
    if animals_grazing_count > 0:
        df.loc[animals_grazing_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Cleared {animals_grazing_count} 'grazing livestock & horses' isolation_source_category for 'wild animals' hosts (set to NA)")
    
    # wild birds with poultry livestock isolation
    birds_poultry_mask = (
        (df['host_category'] == 'wild birds') &
        (df['isolation_source_category'] == 'poultry livestock')
    )
    birds_poultry_count = birds_poultry_mask.sum()
    if birds_poultry_count > 0:
        df.loc[birds_poultry_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Cleared {birds_poultry_count} 'poultry livestock' isolation_source_category for 'wild birds' hosts (set to NA)")
    
    # grazing livestock & horses with wild animals isolation
    grazing_animals_mask = (
        (df['host_category'] == 'grazing livestock & horses') &
        (df['isolation_source_category'] == 'wild animals')
    )
    grazing_animals_count = grazing_animals_mask.sum()
    if grazing_animals_count > 0:
        df.loc[grazing_animals_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Cleared {grazing_animals_count} 'wild animals' isolation_source_category for 'grazing livestock & horses' hosts (set to NA)")
    
    # human with domestic animals isolation
    human_dogs_cats_mask = (
        (df['host_category'] == 'human') &
        (df['isolation_source_category'] == 'domestic animals')
    )
    human_dogs_cats_count = human_dogs_cats_mask.sum()
    if human_dogs_cats_count > 0:
        df.loc[human_dogs_cats_mask, 'isolation_source_category'] = pd.NA
        if verbose:
            print(f"Cleared {human_dogs_cats_count} 'domestic animals' isolation_source_category for 'human' hosts (set to NA)")
    
    # 9. Normalize missing values to ensure consistent handling
    # This prevents duplicate "Missing/NA" entries in downstream analysis
    df = normalize_missing_values(df, ['host_category', 'isolation_source_category'], verbose=False)
    
    if verbose:
        print("\n" + "=" * 60 + "\n")
    
    return df


def retrieve_unhelpful_isolation_source_annotations(df):
    """
    Retrieve all unhelpful isolation_source_parsed annotations.
    Includes values containing "(unhelpful)", "(other)", or "(not specified)" patterns,
    plus hardcoded problematic values that don't follow the pattern.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with isolation_source_parsed column
        
    Returns:
    --------
    list
        List of unhelpful annotation values
    """
    unhelpful_patterns = ["(unhelpful)", "(other)", "(not specified)"]
    unhelpful_values = set()
    
    # Dynamically find values containing the patterns
    if 'isolation_source_parsed' in df.columns:
        unique_values = df['isolation_source_parsed'].dropna().unique()
        for val in unique_values:
            val_str = str(val)
            if any(pattern in val_str for pattern in unhelpful_patterns):
                unhelpful_values.add(val_str)
    
    return sorted(list(unhelpful_values))


def retrieve_unhelpful_host_annotations(df):
    """
    Retrieve all unhelpful host_parsed annotations.
    Includes values containing "(unhelpful)", "(other)", or "(not specified)" patterns,
    plus hardcoded problematic values that don't follow the pattern.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with host_parsed column
        
    Returns:
    --------
    list
        List of unhelpful annotation values
    """
    unhelpful_patterns = ["(unhelpful)", "(other)", "(not specified)"]
    unhelpful_values = set()
    
    # Dynamically find values containing the patterns
    if 'host_parsed' in df.columns:
        unique_values = df['host_parsed'].dropna().unique()
        for val in unique_values:
            val_str = str(val)
            if any(pattern in val_str for pattern in unhelpful_patterns):
                unhelpful_values.add(val_str)
    
    return sorted(list(unhelpful_values))


def calculate_column_completeness(df, columns):
    """
    Calculate completeness (non-null / total) for specified columns.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame to analyze
    columns : list of str
        List of column names to check
        
    Returns:
    --------
    dict
        Dictionary mapping column name -> completeness ratio (float between 0 and 1)
    """
    completeness = {}
    total_rows = len(df)
    
    for col in columns:
        if col not in df.columns:
            completeness[col] = 0.0
        else:
            n_filled = df[col].notna().sum()
            completeness[col] = n_filled / total_rows if total_rows > 0 else 0.0
    
    return completeness


def identify_unhelpful_annotations(df):
    """
    Identify rows with unhelpful annotations in parsed columns.
    Adds a boolean column 'has_unhelpful_annotations' to the dataframe.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame to analyze
        
    Returns:
    --------
    pd.DataFrame
        DataFrame with added 'has_unhelpful_annotations' column
    """
    df = df.copy()
    
    # Retrieve unhelpful values dynamically
    unhelpful_isolation_source = retrieve_unhelpful_isolation_source_annotations(df)
    unhelpful_host = retrieve_unhelpful_host_annotations(df)
    
    # Initialize the flag column
    df['has_unhelpful_annotations'] = False
    
    # Check isolation_source_parsed
    if 'isolation_source_parsed' in df.columns:
        mask = df['isolation_source_parsed'].isin(unhelpful_isolation_source)
        df.loc[mask, 'has_unhelpful_annotations'] = True
    
    # Check host_parsed
    if 'host_parsed' in df.columns:
        mask = df['host_parsed'].isin(unhelpful_host)
        df.loc[mask, 'has_unhelpful_annotations'] = True
    
    return df


def get_study_metadata_value(study_metadata_df, study_accession, column_name):
    """
    Get a value from study metadata by matching study_accession.
    
    Parameters:
    -----------
    study_metadata_df : pd.DataFrame
        DataFrame containing study metadata with 'study_accessions' column
    study_accession : str
        Study accession to match (e.g., 'PRJEB12345')
    column_name : str
        Name of the column to extract from study_metadata_df
        
    Returns:
    --------
    value or None
        The value from column_name for the matching row, or None if no match found.
        Returns None if the value is NaN (distinguish from no match using has_study_metadata_match).
    """
    if study_metadata_df is None:
        return None
    
    # Validate required columns exist
    if 'study_accessions' not in study_metadata_df.columns:
        return None
    
    if column_name not in study_metadata_df.columns:
        return None
    
    # Find rows where study_accessions contains the study_accession
    matches = study_metadata_df[study_metadata_df['study_accessions'].astype(str).str.contains(str(study_accession), na=False, regex=False)]
    
    if matches.empty:
        return None
    
    # Take the first match's value
    value = matches.iloc[0][column_name]
    
    # Handle NaN values by returning None
    if pd.isna(value):
        return None
    
    return value


def has_study_metadata_match(study_metadata_df, study_accession):
    """
    Check if a study_accession has a match in study_metadata_df.
    
    Parameters:
    -----------
    study_metadata_df : pd.DataFrame
        DataFrame containing study metadata with 'study_accessions' column
    study_accession : str
        Study accession to match (e.g., 'PRJEB12345')
        
    Returns:
    --------
    bool
        True if study_accession is found in study_accessions column, False otherwise
    """
    if study_metadata_df is None:
        return False
    
    if 'study_accessions' not in study_metadata_df.columns:
        return False
    
    # Find rows where study_accessions contains the study_accession
    matches = study_metadata_df[study_metadata_df['study_accessions'].astype(str).str.contains(str(study_accession), na=False, regex=False)]
    
    return not matches.empty


def merge_amr_study_from_study_metadata(df, google_sheet_id=None, sheet_name=None, tsv_file_path=None):
    """
    Merge amr_study column from study metadata into curated metadata dataframe.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Curated metadata dataframe with 'study_accession' column
    google_sheet_id : str, optional
        Google Spreadsheet ID (defaults to STUDY_METADATA_GOOGLE_SHEET_ID constant)
    sheet_name : str, optional
        Name of the sheet to read (defaults to STUDY_METADATA_SHEET_NAME constant)
    tsv_file_path : str, optional
        Path to TSV file with study characteristics (defaults to STUDY_CHARACTERISTICS_TSV_PATH constant)
        
    Returns:
    --------
    pd.DataFrame
        Modified dataframe with 'amr_study' column added. Unmatched study_accessions
        will have amr_study set to NaN.
        
    Raises:
    -------
    ValueError
        If Google Sheet cannot be loaded or required columns are missing
    """
    if 'study_accession' not in df.columns:
        raise ValueError("Dataframe must contain 'study_accession' column")
    
    # Use defaults if not provided
    if google_sheet_id is None:
        google_sheet_id = STUDY_METADATA_GOOGLE_SHEET_ID
    if sheet_name is None:
        sheet_name = STUDY_METADATA_SHEET_NAME
    if tsv_file_path is None:
        tsv_file_path = STUDY_CHARACTERISTICS_TSV_PATH
    
    # Load study metadata from Google Sheet
    try:
        study_metadata_df = _read_google_sheet(google_sheet_id, sheet_name)
    except Exception as e:
        raise ValueError(f"Could not load study metadata from Google Sheet '{google_sheet_id}' (sheet: {sheet_name}): {e}")
    
    # Validate required columns exist
    if 'study_accessions' not in study_metadata_df.columns:
        raise ValueError(f"Column 'study_accessions' not found in Google Sheet '{google_sheet_id}' (sheet: {sheet_name})")
    
    if 'amr_study' not in study_metadata_df.columns:
        raise ValueError(f"Column 'amr_study' not found in Google Sheet '{google_sheet_id}' (sheet: {sheet_name})")
    
    # Create mapping dictionary for all unique study_accessions
    unique_study_accessions = df['study_accession'].unique()
    mapping = {}
    unmatched_studies = []
    nan_count = 0
    
    for study_acc in unique_study_accessions:
        # Check if study_accession has a match in study_metadata
        if not has_study_metadata_match(study_metadata_df, study_acc):
            # No match found - set to NaN
            unmatched_studies.append(study_acc)
            mapping[study_acc] = pd.NA
        else:
            # Match found - get the value (may be NaN)
            amr_study_value = get_study_metadata_value(study_metadata_df, study_acc, 'amr_study')
            if amr_study_value is None:
                # Match exists but value is NaN - set to pd.NA in mapping
                mapping[study_acc] = pd.NA
                nan_count += 1
            else:
                mapping[study_acc] = amr_study_value
    
    # Try to fill remaining NaN values from TSV file
    if tsv_file_path:
        import os
        if os.path.exists(tsv_file_path):
            tsv_df = pd.read_csv(tsv_file_path, sep="\t")
            if 'study_accession' in tsv_df.columns and 'amr_study' in tsv_df.columns:
                tsv_filled_count = 0
                for study_acc in unique_study_accessions:
                    if pd.isna(mapping.get(study_acc)):
                        # Look up in TSV and fill if exists
                        tsv_matches = tsv_df[tsv_df['study_accession'] == study_acc]
                        if not tsv_matches.empty:
                            tsv_value = tsv_matches['amr_study'].iloc[0]
                            # Check if value is not NaN and not empty string
                            if pd.notna(tsv_value) and str(tsv_value).strip() != '':
                                mapping[study_acc] = tsv_value
                                tsv_filled_count += 1
                if tsv_filled_count > 0:
                    print(f"  Note: Filled {tsv_filled_count} additional study_accession(s) from TSV file")
        else:
            print(f"\n{'='*60}")
            print(f"WARNING: TSV file not found: {tsv_file_path}")
            print(f"{'='*60}\n")
    
    # Report unmatched studies (set to NaN instead of raising error)
    if unmatched_studies:
        print(f"  Note: {len(unmatched_studies)} study_accession(s) not found in study metadata (amr_study set to NaN): "
              f"{', '.join(unmatched_studies[:10])}"
              + (f" ... and {len(unmatched_studies) - 10} more" if len(unmatched_studies) > 10 else ""))
    
    # Merge mapping into dataframe
    df = df.copy()
    df['amr_study'] = df['study_accession'].map(mapping)
    
    # Report if any matched values were NaN
    if nan_count > 0:
        print(f"  Note: {nan_count} study_accession(s) had NaN amr_study values in study metadata (set to missing)")
    
    # Report statistics
    print("\nMerged 'amr_study' from study metadata:")
    print(f"  Matched {len(mapping)} unique study_accession(s)")
    print("  Distribution of amr_study values:")
    amr_study_counts = df['amr_study'].value_counts(dropna=False)
    for value, count in amr_study_counts.items():
        if pd.isna(value):
            print(f"    <missing>: {count} samples")
        else:
            print(f"    {value}: {count} samples")
    
    return df


def merge_study_setting_from_study_metadata(df, google_sheet_id=None, sheet_name=None, tsv_file_path=None):
    """
    Merge study_setting column from study metadata into curated metadata dataframe.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Curated metadata dataframe with 'study_accession' column
    google_sheet_id : str, optional
        Google Spreadsheet ID (defaults to STUDY_METADATA_GOOGLE_SHEET_ID constant)
    sheet_name : str, optional
        Name of the sheet to read (defaults to STUDY_METADATA_SHEET_NAME constant)
    tsv_file_path : str, optional
        Path to TSV file with study characteristics (defaults to STUDY_CHARACTERISTICS_TSV_PATH constant)
        
    Returns:
    --------
    pd.DataFrame
        Modified dataframe with 'study_setting' column added. Unmatched study_accessions
        will have study_setting set to NaN.
        
    Raises:
    -------
    ValueError
        If Google Sheet cannot be loaded or required columns are missing
    """
    if 'study_accession' not in df.columns:
        raise ValueError("Dataframe must contain 'study_accession' column")
    
    # Use defaults if not provided
    if google_sheet_id is None:
        google_sheet_id = STUDY_METADATA_GOOGLE_SHEET_ID
    if sheet_name is None:
        sheet_name = STUDY_METADATA_SHEET_NAME
    if tsv_file_path is None:
        tsv_file_path = STUDY_CHARACTERISTICS_TSV_PATH
    
    # Load study metadata from Google Sheet
    try:
        study_metadata_df = _read_google_sheet(google_sheet_id, sheet_name)
    except Exception as e:
        raise ValueError(f"Could not load study metadata from Google Sheet '{google_sheet_id}' (sheet: {sheet_name}): {e}")
    
    # Validate required columns exist
    if 'study_accessions' not in study_metadata_df.columns:
        raise ValueError(f"Column 'study_accessions' not found in Google Sheet '{google_sheet_id}' (sheet: {sheet_name})")
    
    if 'study_setting' not in study_metadata_df.columns:
        raise ValueError(f"Column 'study_setting' not found in Google Sheet '{google_sheet_id}' (sheet: {sheet_name})")
    
    # Create mapping dictionary for all unique study_accessions
    unique_study_accessions = df['study_accession'].unique()
    mapping = {}
    unmatched_studies = []
    nan_count = 0
    
    for study_acc in unique_study_accessions:
        # Check if study_accession has a match in study_metadata
        if not has_study_metadata_match(study_metadata_df, study_acc):
            # No match found - set to NaN
            unmatched_studies.append(study_acc)
            mapping[study_acc] = pd.NA
        else:
            # Match found - get the value (may be NaN)
            study_setting_value = get_study_metadata_value(study_metadata_df, study_acc, 'study_setting')
            if study_setting_value is None:
                # Match exists but value is NaN - set to pd.NA in mapping
                mapping[study_acc] = pd.NA
                nan_count += 1
            else:
                mapping[study_acc] = study_setting_value
    
    # Try to fill remaining NaN values from TSV file
    if tsv_file_path:
        import os
        if os.path.exists(tsv_file_path):
            tsv_df = pd.read_csv(tsv_file_path, sep="\t")
            if 'study_accession' in tsv_df.columns and 'study_setting' in tsv_df.columns:
                tsv_filled_count = 0
                for study_acc in unique_study_accessions:
                    if pd.isna(mapping.get(study_acc)):
                        # Look up in TSV and fill if exists
                        tsv_matches = tsv_df[tsv_df['study_accession'] == study_acc]
                        if not tsv_matches.empty:
                            tsv_value = tsv_matches['study_setting'].iloc[0]
                            # Check if value is not NaN and not empty string
                            if pd.notna(tsv_value) and str(tsv_value).strip() != '':
                                mapping[study_acc] = tsv_value
                                tsv_filled_count += 1
                if tsv_filled_count > 0:
                    print(f"  Note: Filled {tsv_filled_count} additional study_accession(s) from TSV file")
        else:
            print(f"\n{'='*60}")
            print(f"WARNING: TSV file not found: {tsv_file_path}")
            print(f"{'='*60}\n")
    
    # Report unmatched studies (set to NaN instead of raising error)
    if unmatched_studies:
        print(f"  Note: {len(unmatched_studies)} study_accession(s) not found in study metadata (study_setting set to NaN): "
              f"{', '.join(unmatched_studies[:10])}"
              + (f" ... and {len(unmatched_studies) - 10} more" if len(unmatched_studies) > 10 else ""))
    
    # Merge mapping into dataframe
    df = df.copy()
    df['study_setting'] = df['study_accession'].map(mapping)
    
    # Report if any matched values were NaN
    if nan_count > 0:
        print(f"  Note: {nan_count} study_accession(s) had NaN study_setting values in study metadata (set to missing)")
    
    # Report statistics
    print("\nMerged 'study_setting' from study metadata:")
    print(f"  Matched {len(mapping)} unique study_accession(s)")
    print("  Distribution of study_setting values:")
    study_setting_counts = df['study_setting'].value_counts(dropna=False)
    for value, count in study_setting_counts.items():
        if pd.isna(value):
            print(f"    <missing>: {count} samples")
        else:
            print(f"    {value}: {count} samples")
    
    return df


def generate_project_summary_table(df, google_sheet_id=None, sheet_name=None, pre_collation_df=None):
    """
    Generate a summary table by study_accession with completeness metrics and unhelpful annotation counts.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns
    google_sheet_id : str, optional
        Google Spreadsheet ID (defaults to STUDY_METADATA_GOOGLE_SHEET_ID constant)
    sheet_name : str, optional
        Name of the sheet to read (defaults to STUDY_METADATA_SHEET_NAME constant)
    pre_collation_df : pd.DataFrame, optional
        Pre-collation dataframe with parsed columns for comparison
        
    Returns:
    --------
    pd.DataFrame
        Summary table with one row per study_accession
    """
    if 'study_accession' not in df.columns:
        print("Warning: 'study_accession' column not found in dataframe")
        return pd.DataFrame()
    
    # Define columns to check for completeness
    completeness_columns = {
        'host_category': 'host_completeness',
        'region': 'country_completeness',
        'collection_date_parsed': 'collection_date_completeness',
        'isolation_source_category': 'isolation_source_completeness'
    }

    # Group by study_accession
    grouped = df.groupby('study_accession')
    
    # Use defaults if not provided
    if google_sheet_id is None:
        google_sheet_id = STUDY_METADATA_GOOGLE_SHEET_ID
    if sheet_name is None:
        sheet_name = STUDY_METADATA_SHEET_NAME
    
    # Load study metadata from Google Sheet to get curator information
    study_metadata_df = None
    try:
        study_metadata_df = _read_google_sheet(google_sheet_id, sheet_name)
    except Exception as e:
        print(f"Warning: Could not load study metadata from Google Sheet: {e}")
    
    # Calculate pre-collation completeness data directly from dataframe
    pivot_data = None
    if pre_collation_df is not None and 'study_accession' in pre_collation_df.columns:
        # Calculate completeness for each study in pre-collation data
        # Map parsed column names to pre-collation column names
        pre_collation_columns = {
            'host_category': 'host_pre',
            'region': 'country_pre',
            'collection_date_parsed': 'collection_date_pre',
            'isolation_source_category': 'isolation_source_pre'
        }
        
        # Build pivot data manually by calculating completeness per study
        pivot_data_dict = {}
        for study_acc in pre_collation_df['study_accession'].unique():
            study_df = pre_collation_df[pre_collation_df['study_accession'] == study_acc]
            if 'sample_accession' in study_df.columns:
                total_samples = study_df['sample_accession'].nunique()
            else:
                total_samples = len(study_df)
            
            if total_samples > 0:
                completeness_values = {}
                for col, pre_col_name in pre_collation_columns.items():
                    if col in study_df.columns:
                        if 'sample_accession' in study_df.columns:
                            n_filled = study_df[study_df[col].notna()]['sample_accession'].nunique()
                        else:
                            n_filled = study_df[col].notna().sum()
                        completeness_values[pre_col_name] = n_filled / total_samples
                    else:
                        completeness_values[pre_col_name] = None
                
                pivot_data_dict[study_acc] = completeness_values
        
        # Convert to DataFrame
        if pivot_data_dict:
            pivot_data = pd.DataFrame.from_dict(pivot_data_dict, orient='index')
    
    summary_data = []
    
    for study_acc, group_df in grouped:
        # Count unique samples (matching the filtering logic in metadata_collation)
        
        total_samples_per_study = group_df['sample_accession'].nunique()
        # Calculate completeness metrics
        row_data = {'study_accession': study_acc, 'total_samples': total_samples_per_study}
        
        # Get curator from study metadata using helper function
        curator = get_study_metadata_value(study_metadata_df, study_acc, 'Curator')
        row_data['curator'] = curator
        
        for col, metric_name in completeness_columns.items():
            # Count unique samples (matching the filtering logic in metadata_collation)
            n_filled = group_df[group_df[col].notna()]['sample_accession'].nunique()
            completeness_ratio = n_filled / total_samples_per_study # By definition, total_samples_per_study is always greater than 0
            row_data[metric_name] = round(completeness_ratio, 2)
        
        # end loop over completeness columns

        # Retrieve unhelpful values dynamically
        unhelpful_isolation_source = retrieve_unhelpful_isolation_source_annotations(group_df)
        unhelpful_host = retrieve_unhelpful_host_annotations(group_df)
        
        # Collect unhelpful isolation source annotations (only if count >= 10)
        isolation_source_annotations = []
        if 'isolation_source_parsed' in group_df.columns and 'isolation_source' in group_df.columns:
            for unhelpful_val in unhelpful_isolation_source:
                # Count rows with this unhelpful value
                count = (group_df['isolation_source_parsed'] == unhelpful_val).sum()
                
                # Only proceed if count >= 10
                if count >= 10:
                    # Filter to rows with this unhelpful value
                    masked_df = group_df[group_df['isolation_source_parsed'] == unhelpful_val]
                    
                    # Get unique values and their counts from original isolation_source column
                    value_counts = masked_df['isolation_source'].value_counts()
                    
                    # Format as "val1 (count1), val2 (count2), ..."
                    formatted_values = ", ".join([f"{val} ({count})" for val, count in value_counts.items()])
                    
                    # Prepend the unhelpful value name for context
                    isolation_source_annotations.append(f"{formatted_values}")
        
        # Collect unhelpful host annotations (only if count >= 10)
        host_annotations = []
        if 'host_parsed' in group_df.columns and 'host' in group_df.columns:
            for unhelpful_val in unhelpful_host:
                # Count rows with this unhelpful value
                count = (group_df['host_parsed'] == unhelpful_val).sum()
                
                # Only proceed if count >= 10
                if count >= 10:
                    # Filter to rows with this unhelpful value
                    masked_df = group_df[group_df['host_parsed'] == unhelpful_val]
                    
                    # Get unique values and their counts from original host column
                    value_counts = masked_df['host'].value_counts()
                    
                    # Format as "val1 (count1), val2 (count2), ..."
                    formatted_values = ", ".join([f"{val} ({count})" for val, count in value_counts.items()])
                    
                    # Prepend the unhelpful value name for context
                    host_annotations.append(f"{formatted_values}")
        
        # Add consolidated columns (empty string if no annotations >= 10)
        row_data['unhelpful isolation source annotation'] = " | ".join(isolation_source_annotations) if isolation_source_annotations else ""
        row_data['unhelpful host annotation'] = " | ".join(host_annotations) if host_annotations else ""
        
        # Calculate review_required: 
        # - True if ANY metric has final < 0.8 AND (delta < 0.05 OR no pre-curation data available)
        review_required = False
        
        # Get pre-collation values if available
        pre_values = None
        if pivot_data is not None and study_acc in pivot_data.index:
            pre_values = pivot_data.loc[study_acc]
        
        if pre_values is not None:
            # Check each of the 4 metrics when pre-curation data is available
            metric_pairs = [
                ('host_completeness', 'host_pre'),
                ('country_completeness', 'country_pre'),
                ('collection_date_completeness', 'collection_date_pre'),
                ('isolation_source_completeness', 'isolation_source_pre')
            ]
            
            for final_col, pre_col in metric_pairs:
                if final_col in row_data and pre_col in pre_values:
                    final_val = row_data[final_col]
                    pre_val = pre_values[pre_col]
                    
                    if not pd.isna(pre_val) and not pd.isna(final_val):
                        delta = final_val - pre_val
                        if final_val < 0.8 and delta < 0.05:
                            review_required = True
                            break
        else:
            # No pre-curation data available - check if any metric is inadequate
            completeness_metrics = ['host_completeness', 'country_completeness', 
                                   'collection_date_completeness', 'isolation_source_completeness']
            
            for metric in completeness_metrics:
                if metric in row_data:
                    final_val = row_data[metric]
                    if not pd.isna(final_val) and final_val < 0.8:
                        review_required = True
                        break
        
        row_data['review_required'] = review_required
        
        # Add pre-collation completeness values
        if pre_values is not None:
            for pre_col in ['host_pre', 'country_pre', 'collection_date_pre', 'isolation_source_pre']:
                if pre_col in pre_values and not pd.isna(pre_values[pre_col]):
                    row_data[pre_col] = round(pre_values[pre_col], 2)
                else:
                    row_data[pre_col] = None
        else:
            # No pre-collation data for this study
            for pre_col in ['host_pre', 'country_pre', 'collection_date_pre', 'isolation_source_pre']:
                row_data[pre_col] = None
        
        summary_data.append(row_data)
    
    summary_df = pd.DataFrame(summary_data)
    
    # Reorder columns: study_accession, total_samples, curator, review_required, completeness metrics, pre-collation metrics, then unhelpful annotations
    base_cols = [
        'study_accession', 
        'total_samples', 
        'curator',
        'review_required',
        'host_completeness', 
        'country_completeness', 
        'collection_date_completeness', 
        'isolation_source_completeness',
        'host_pre',
        'country_pre', 
        'collection_date_pre',
        'isolation_source_pre',
        'unhelpful host annotation', 
        'unhelpful isolation source annotation'
    ]
    other_cols = [c for c in summary_df.columns if c not in base_cols]
    summary_df = summary_df[base_cols + sorted(other_cols)]
    # Order rows by total_samples descending
    summary_df = summary_df.sort_values(by='total_samples', ascending=False)
    
    return summary_df


def _normalize_amr_study(df):
    """
    Helper function to normalize amr_study values.
    Collapses "AMR with controls" and "AMR plus control" into "AMR",
    and combines "Pending" with "Missing".
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'amr_study' column
    
    Returns:
    --------
    pd.Series
        Series with normalized amr_study values
    """
    if 'amr_study' not in df.columns:
        return pd.Series('Missing', index=df.index)
    
    # Create a copy to avoid modifying original
    normalized = df['amr_study'].copy()
    
    # Replace NaN/None with 'Missing' first
    normalized = normalized.fillna('Missing')
    
    # Convert to string for case-insensitive operations
    normalized_str = normalized.astype(str)
    
    # Collapse "AMR with controls" and "AMR plus control" variations into "AMR"
    # Use case-insensitive regex matching for any variant containing "amr" and "control"
    mask_amr_controls = normalized_str.str.contains(r'amr.*(?:plus|with).*control', case=False, na=False, regex=True)
    normalized.loc[mask_amr_controls] = 'AMR'
    
    # Also handle exact string matches (case-insensitive) as a fallback
    # Convert to lowercase for comparison, then map back
    normalized_lower = normalized_str.str.lower()
    amr_variants = ['amr with controls', 'amr plus control', 'amr with control', 'amr plus controls']
    for variant in amr_variants:
        mask = normalized_lower == variant
        normalized.loc[mask] = 'AMR'
    
    # Combine "Pending" with "Missing" (case-insensitive)
    mask_pending = normalized_str.str.lower() == 'pending'
    normalized.loc[mask_pending] = 'Missing'
    
    return normalized


def plot_region_distribution_by_amr_study(df, output_dir):
    """
    Plot region distribution as stacked bars by amr_study.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns including 'region' and 'amr_study'
    output_dir : str
        Directory to save the figure
    """
    import os
    
    if 'region' not in df.columns:
        return
    
    # Prepare amr_study using normalization helper
    df_plot = df.copy()
    df_plot['amr_study_grouped'] = _normalize_amr_study(df_plot)
    
    # Filter to rows with valid region
    df_plot = df_plot[df_plot['region'].notna()].copy()
    
    if len(df_plot) == 0:
        return
    
    # Create crosstab for stacked bars
    crosstab = pd.crosstab(df_plot['region'], df_plot['amr_study_grouped'])
    
    # Sort by total (sum across columns) descending
    crosstab['_total'] = crosstab.sum(axis=1)
    crosstab = crosstab.sort_values('_total', ascending=False)
    crosstab = crosstab.drop('_total', axis=1)
    
    if len(crosstab) == 0:
        return
    
    # Create stacked bar chart
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Define custom colors matching isolation source: Surveillance (steelblue), AMR (dark red), Missing (grey)
    color_map = {
        'Surveillance': 'steelblue',
        'AMR': 'darkred',
        'Missing': 'grey'
    }
    colors = [color_map.get(col, 'steelblue') for col in crosstab.columns]
    
    # Plot stacked bars with custom colors
    crosstab.plot(kind='bar', stacked=True, ax=ax, width=0.8, color=colors)
    
    ax.set_xticks(range(len(crosstab)))
    ax.set_xticklabels(crosstab.index, rotation=45, ha='right')
    ax.set_ylabel('Number of Samples', fontsize=12)
    ax.set_title('Region Distribution by AMR Study Type', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    ax.legend(title='AMR Study Type', bbox_to_anchor=(1.05, 1), loc='upper left')
    
    # Add value labels on top of bars (total)
    for i, (idx, row) in enumerate(crosstab.iterrows()):
        total = row.sum()
        if total > 0:
            ax.text(i, total, f'{int(total):,}',
                   ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'region_distribution_by_amr_study.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def calculate_region_completeness(df):
    """
    Calculate region completeness with breakdown of usable, other, and not-filled counts.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'region' and 'country' columns
        
    Returns:
    --------
    tuple : (pd.Series, dict)
        - Series with category counts (regions, 'Other', 'Not-filled')
        - Dict with breakdown: {'usable': int, 'other': int, 'not_filled': int}
    """
    if 'region' not in df.columns or 'country' not in df.columns:
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': 0}
    
    # Count samples per region (only for rows with valid region)
    region_counts = df[df['region'].notna()]['region'].value_counts()
    
    # Get all major regions that exist in the data (sort by count descending)
    major_regions = region_counts.index.tolist()
    
    if len(major_regions) == 0:
        not_filled_count = df['country'].isna().sum()
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': int(not_filled_count)}
    
    # Create series with major regions
    region_data = region_counts.copy()
    
    # Calculate "Other" = rows where country is filled but region is not in major regions
    country_filled_mask = df['country'].notna()
    region_not_in_major_mask = ~df['region'].isin(major_regions)
    other_count = (country_filled_mask & region_not_in_major_mask).sum()
    
    # Calculate "Not-filled" = rows where country is not filled
    not_filled_count = df['country'].isna().sum()
    
    # Calculate usable count (all regions in major_regions)
    usable_count = region_data.sum()
    
    # Append "Other" and "Not-filled" to the series
    if other_count > 0:
        region_data['Other'] = other_count
    if not_filled_count > 0:
        region_data['Not-filled'] = not_filled_count
    
    if len(region_data) == 0:
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': 0}
    
    # Sort by count descending (excluding Other and Not-filled for sorting, then append them)
    main_regions_data = region_data[region_data.index.isin(major_regions)].sort_values(ascending=False)
    other_unfilled = region_data[~region_data.index.isin(major_regions)]
    region_data_final = pd.concat([main_regions_data, other_unfilled])
    
    breakdown = {
        'usable': int(usable_count),
        'other': int(other_count),
        'not_filled': int(not_filled_count)
    }
    
    return region_data_final, breakdown


def calculate_isolation_source_completeness(df, return_other_info=False):
    """
    Calculate isolation source completeness with breakdown of usable and not-filled counts.
    Uses fixed category list from ISOLATION_SOURCE_CATEGORIES_TO_PLOT.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'isolation_source_category' column
    return_other_info : bool, default=False
        If True, returns additional info about categories not in fixed list
        
    Returns:
    --------
    If return_other_info is False:
        tuple : (pd.Series, dict)
            - Series with category counts (fixed categories, 'Not-filled')
            - Dict with breakdown: {'usable': int, 'other': int, 'not_filled': int}
    If return_other_info is True:
        tuple : (pd.Series, dict, list, pd.Series)
            - Series with category counts
            - Dict with breakdown
            - List of 'Other' category names (not in fixed list)
            - Series with counts for 'Other' categories
    """
    if 'isolation_source_category' not in df.columns:
        if return_other_info:
            return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': 0}, [], pd.Series(dtype=int)
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': 0}
    
    # Get all category counts
    iso_counts_all = df['isolation_source_category'].value_counts()
    iso_counts_all = iso_counts_all[iso_counts_all.index.notna()]
    
    # Filter to only categories in the fixed list
    fixed_categories = [cat for cat in ISOLATION_SOURCE_CATEGORIES_TO_PLOT if cat in iso_counts_all.index]
    
    if len(fixed_categories) == 0:
        not_filled_count = df['isolation_source_category'].isna().sum()
        if return_other_info:
            return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': int(not_filled_count)}, [], pd.Series(dtype=int)
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': int(not_filled_count)}
    
    # Get counts for fixed categories, sorted by count descending
    fixed_counts = iso_counts_all[fixed_categories].sort_values(ascending=False)
    
    # Calculate "Other" = categories not in fixed list (for return_other_info)
    other_categories = [cat for cat in iso_counts_all.index if cat not in ISOLATION_SOURCE_CATEGORIES_TO_PLOT]
    if len(other_categories) > 0:
        other_count = iso_counts_all[other_categories].sum()
        other_counts = iso_counts_all[other_categories].sort_values(ascending=False)
    else:
        other_count = 0
        other_counts = pd.Series(dtype=int)
    
    # Calculate "Not-filled" = count of rows where isolation_source_category is NA
    not_filled_count = df['isolation_source_category'].isna().sum()
    
    # Calculate usable count (fixed categories only)
    usable_count = fixed_counts.sum()
    
    # Create final series with fixed categories and Not-filled
    category_data = fixed_counts.copy()
    if not_filled_count > 0:
        category_data['Not-filled'] = not_filled_count
    
    breakdown = {
        'usable': int(usable_count),
        'other': int(other_count),
        'not_filled': int(not_filled_count)
    }
    
    if return_other_info:
        return category_data, breakdown, other_categories, other_counts
    return category_data, breakdown


def calculate_host_completeness(df):
    """
    Calculate host completeness with breakdown of usable and not-filled counts.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'host_category' column
        
    Returns:
    --------
    tuple : (pd.Series, dict)
        - Series with category counts (all categories, 'Not-filled')
        - Dict with breakdown: {'usable': int, 'other': int, 'not_filled': int}
    """
    if 'host_category' not in df.columns:
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': 0}
    
    # Keep obviously unhelpful annotations, but allow categories containing "(other)"
    unhelpful_patterns = ["(unhelpful)", "(not specified)"]
    host_counts_all = df['host_category'].value_counts()
    host_counts_all = host_counts_all[host_counts_all.index.notna()]
    
    if len(host_counts_all) > 0:
        mask = pd.Series([True] * len(host_counts_all), index=host_counts_all.index)
        for pattern in unhelpful_patterns:
            mask = mask & ~host_counts_all.index.astype(str).str.contains(pattern, na=False, regex=False)
        # Use all valid (non-unhelpful) categories, sorted by count (descending)
        valid_counts = host_counts_all[mask].sort_values(ascending=False)
    else:
        valid_counts = pd.Series(dtype=int)
    
    if len(valid_counts) == 0:
        not_filled_count = df['host_category'].isna().sum()
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': int(not_filled_count)}
    
    # Calculate "Not-filled" = count of rows where host_category is NA
    not_filled_count = df['host_category'].isna().sum()
    
    # Calculate usable count (all valid categories)
    usable_count = valid_counts.sum()
    
    # Create final series with all categories and Not-filled
    category_data = valid_counts.copy()
    if not_filled_count > 0:
        category_data['Not-filled'] = not_filled_count
    
    breakdown = {
        'usable': int(usable_count),
        # 'other' is kept for backward compatibility but is always zero
        'other': 0,
        'not_filled': int(not_filled_count)
    }
    
    return category_data, breakdown


def calculate_date_completeness(df):
    """
    Calculate date completeness with breakdown of usable and not-filled counts.
    Note: Date parsing does not have an "Other" category.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'year_parsed' column
        
    Returns:
    --------
    tuple : (pd.Series, dict)
        - Series with category counts (time periods, 'Not-filled')
        - Dict with breakdown: {'usable': int, 'other': int, 'not_filled': int}
    """
    if 'year_parsed' not in df.columns:
        return pd.Series(dtype=int), {'usable': 0, 'other': 0, 'not_filled': len(df)}
    
    # Filter to valid years
    valid_years = df['year_parsed'].dropna()
    
    # Define bins and labels
    labels = ['Pre-2000', '2000-2005', '2005-2010', '2010-2015', '2015-2020', '2020-2025']
    
    # Create bins manually to handle edge cases
    valid_years_series = pd.Series(valid_years)
    binned_list = []
    
    for year in valid_years_series:
        if year < 2000:
            binned_list.append('Pre-2000')
        elif 2000 <= year < 2005:
            binned_list.append('2000-2005')
        elif 2005 <= year < 2010:
            binned_list.append('2005-2010')
        elif 2010 <= year < 2015:
            binned_list.append('2010-2015')
        elif 2015 <= year < 2020:
            binned_list.append('2015-2020')
        elif 2020 <= year < 2025:
            binned_list.append('2020-2025')
        else:
            binned_list.append('2025+')
    
    binned = pd.Series(binned_list, index=valid_years_series.index)
    
    # Count values in each bin
    counts = binned.value_counts()
    # Filter out 2025+ category completely
    counts = counts[counts.index != '2025+']
    # Reindex to ensure all labels are present in correct order
    counts = counts.reindex([label for label in labels if label in counts.index], fill_value=0)
    # Reorder to match desired order
    counts_ordered = pd.Series(index=labels, dtype=int)
    for label in labels:
        if label in counts.index:
            counts_ordered[label] = counts[label]
        else:
            counts_ordered[label] = 0
    
    # Calculate "Not-filled" = count of rows where year_parsed is NA
    not_filled_count = df['year_parsed'].isna().sum()
    
    # Calculate usable count (all time periods)
    usable_count = counts_ordered.sum()
    
    # Create final series with time periods and Not-filled
    date_data = counts_ordered.copy()
    if not_filled_count > 0:
        date_data['Not-filled'] = not_filled_count
    
    breakdown = {
        'usable': int(usable_count),
        'other': 0,  # Date parsing doesn't have "Other" category
        'not_filled': int(not_filled_count)
    }
    
    return date_data, breakdown


def plot_region_distribution_pre_and_post_curation(df, output_dir, df_pre_collation=None):
    """
    Plot region distribution with "Other" and "Not-filled" bars.
    Creates two side-by-side plots: left plot shows regions and 'Other',
    right plot shows 'Not-filled' only. All bars are simple steelblue (no stacking).
    If df_pre_collation is provided, plots side-by-side bars for pre/post comparison.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns including 'region' and 'country' (collated data)
    output_dir : str
        Directory to save the figure
    df_pre_collation : pd.DataFrame, optional
        Pre-collation DataFrame for side-by-side comparison. If None, plots single dataframe.
    """
    import os
    import numpy as np
    
    if 'region' not in df.columns or 'country' not in df.columns:
        return
    
    # Calculate for collated dataframe
    region_data_collated, _ = calculate_region_completeness(df.copy())
    
    if len(region_data_collated) == 0:
        return

    region_data_pre, _ = calculate_region_completeness(df_pre_collation.copy())
    
    # Separate into main categories (regions + Other) and Not-filled
    main_categories = []
    not_filled_categories = []
    
    # Get all categories from both dataframes
    all_cats_set = set(region_data_collated.index) | set(region_data_pre.index)
    
    for cat in all_cats_set:
        if cat == 'Not-filled':
            not_filled_categories.append(cat)
        else:
            main_categories.append(cat)
    
    # Sort main categories: regions by count (descending), then Other at end
    other_cat = None
    if 'Other' in main_categories:
        other_cat = 'Other'
        main_categories.remove('Other')
    main_categories = sorted(main_categories, key=lambda x: region_data_collated.get(x, 0), reverse=True)
    if other_cat is not None:
        main_categories.append(other_cat)
    
    # Create aligned data series with zeros for missing categories
    collated_main = [region_data_collated.get(cat, 0) for cat in main_categories]
    pre_main = [region_data_pre.get(cat, 0) for cat in main_categories]
    collated_not_filled = [region_data_collated.get(cat, 0) for cat in not_filled_categories]
    pre_not_filled = [region_data_pre.get(cat, 0) for cat in not_filled_categories]
    
    # Create two subplots: regions + Other on left (wide), Not-filled on right (narrow)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), gridspec_kw={'width_ratios': [8, 1]})
    
    # ax1 (left): regions + Other
    if len(main_categories) > 0:
        x_main = np.arange(len(main_categories))
        width = 0.45
        
        bars1_main = ax1.bar(x_main - width/2, pre_main, width, label='Pre-curation', color='lightblue')
        bars2_main = ax1.bar(x_main + width/2, collated_main, width, label='Post-curation', color='steelblue')
        
        ax1.set_xticks(x_main)
        ax1.set_xticklabels(main_categories, rotation=45, ha='right', fontsize=11)
        ax1.set_ylabel('Number of Samples', fontsize=12)
        ax1.set_title('Region Distribution', fontsize=14, fontweight='bold')
        ax1.legend(fontsize=11)
        ax1.grid(axis='y', alpha=0.3)
        
        # Add value labels on top of bars
        for bars in [bars1_main, bars2_main]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax1.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9)
    
    # ax2 (right): Not-filled only
    if len(not_filled_categories) > 0:
        x_not_filled = np.arange(len(not_filled_categories))
        width = 0.175
        
        bars1_not_filled = ax2.bar(x_not_filled - width/2, pre_not_filled, width, label='Pre-curation', color='lightblue')
        bars2_not_filled = ax2.bar(x_not_filled + width/2, collated_not_filled, width, label='Post-curation', color='steelblue')
        
        ax2.set_xticks(x_not_filled)
        ax2.set_xticklabels(not_filled_categories, rotation=45, ha='right', fontsize=11)
        # No y-axis label (only first subplot has label)
        ax2.set_title('Region not filled', fontsize=14, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)
        
        # Add value labels on top of bars
        for bars in [bars1_not_filled, bars2_not_filled]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax2.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'region_distribution_pre_and_post_curation.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def plot_isolation_source_category_pre_and_post_curation(df, output_dir, df_pre_collation=None):
    """
    Plot isolation source category distribution with "Not-filled" bars.
    Uses fixed categories from ISOLATION_SOURCE_CATEGORIES_TO_PLOT.
    Creates two side-by-side plots: left plot shows isolation sources,
    right plot shows 'Not-filled' category only. Uses linear scale with independent y-axes.
    If df_pre_collation is provided, plots side-by-side bars for pre/post comparison.
    Plots full df first, then human-only (host_category == "human") with a separate filename if host_category exists.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns including 'isolation_source_category' (collated data)
    output_dir : str
        Directory to save the figure
    df_pre_collation : pd.DataFrame, optional
        Pre-collation DataFrame for side-by-side comparison. If None, plots single dataframe.
    """

    def _do_plot(plot_df, output_path, pre_collation=None, plot_title=None):
        """Internal: plot isolation source category for given dataframe and save to output_path."""
        import numpy as np

        if 'isolation_source_category' not in plot_df.columns:
            return
        category_data_collated, _ = calculate_isolation_source_completeness(
            plot_df.copy(), return_other_info=False
        )
        if len(category_data_collated) == 0:
            return

        category_data_pre, _ = calculate_isolation_source_completeness(
            pre_collation.copy(), return_other_info=False
        )
        # Define categories for target layout: main categories on left, Not-filled on right
        main_categories = []
        not_filled_categories = []
        all_cats_set = set(category_data_collated.index) | set(category_data_pre.index)
        for cat in all_cats_set:
            if cat == 'Not-filled':
                not_filled_categories.append(cat)
            else:
                main_categories.append(cat)
        # Filter to only categories with count > 0 in post-curation (collated) data
        main_categories = [cat for cat in main_categories if category_data_collated.get(cat, 0) > 0]
        # Sort main categories by count (already sorted by calculate_isolation_source_completeness)
        main_categories = sorted(
            main_categories, key=lambda x: category_data_collated.get(x, 0), reverse=True
        )
        # Get data for both panels
        collated_main = [category_data_collated.get(cat, 0) for cat in main_categories]
        pre_main = [category_data_pre.get(cat, 0) for cat in main_categories]
        collated_not_filled = [category_data_collated.get(cat, 0) for cat in not_filled_categories]
        pre_not_filled = [category_data_pre.get(cat, 0) for cat in not_filled_categories]
        # Create figure with main panel on left (wide) and Not-filled on right (narrow)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), gridspec_kw={'width_ratios': [11, 1]})
        if plot_title is not None:
            fig.suptitle(plot_title, fontsize=16, fontweight='bold')
        # ax1 (left): main isolation sources
        if len(main_categories) > 0:
            x_main = np.arange(len(main_categories))
            width = 0.45
            bars1_main = ax1.bar(x_main - width / 2, pre_main, width, label='Pre-curation', color='lightblue')
            bars2_main = ax1.bar(x_main + width / 2, collated_main, width, label='Post-curation', color='steelblue')
            truncated_labels = [' '.join(str(lbl).split()[:3]) for lbl in main_categories]
            ax1.set_xticks(x_main)
            ax1.set_xticklabels(truncated_labels, rotation=45, ha='right', fontsize=11)
            ax1.set_ylabel('Number of Samples', fontsize=12)
            ax1.set_title('Isolation Sources', fontsize=14, fontweight='bold')
            ax1.legend(fontsize=11)
            ax1.grid(axis='y', alpha=0.3)
            for bars in [bars1_main, bars2_main]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax1.text(
                            bar.get_x() + bar.get_width() / 2.0, height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9
                        )
        # ax2 (right): Not-filled only
        if len(not_filled_categories) > 0:
            x_not_filled = np.arange(len(not_filled_categories))
            width = 0.175
            bars1_not_filled = ax2.bar(x_not_filled - width / 2, pre_not_filled, width, label='Pre-curation', color='lightblue')
            bars2_not_filled = ax2.bar(x_not_filled + width / 2, collated_not_filled, width, label='Post-curation', color='steelblue')
            ax2.set_xticks(x_not_filled)
            ax2.set_xticklabels(not_filled_categories, rotation=45, ha='right', fontsize=11)
            # No y-axis label (only first subplot has label)
            ax2.set_title('Not filled', fontsize=14, fontweight='bold')
            ax2.grid(axis='y', alpha=0.3)
            for bars in [bars1_not_filled, bars2_not_filled]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax2.text(
                            bar.get_x() + bar.get_width() / 2.0, height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9
                        )
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  Saved: {output_path}")

    import os

    if 'isolation_source_category' not in df.columns:
        return
    category_data_collated, _, other_categories_list, other_counts_series = calculate_isolation_source_completeness(
        df.copy(), return_other_info=True
    )
    if len(other_categories_list) > 0:
        print("\n'Other' categories in isolation_source_category (not in fixed list):")
        print(f"  Total unique 'Other' categories: {len(other_categories_list)}")
        print("  Top 40 'Other' categories (by count):")
        top_40_other = other_counts_series.head(40)
        for cat, count in top_40_other.items():
            print(f"    - {cat}: {count}")
        if len(other_categories_list) > 40:
            print(f"    ... and {len(other_categories_list) - 40} more categories")
    if len(category_data_collated) == 0:
        return

    output_path_full = os.path.join(output_dir, 'isolation_source_category_pre_and_post_curation_all_hosts.png')
    _do_plot(df, output_path_full, df_pre_collation, plot_title="Isolation Sources in All Hosts")

    if 'host_category' in df.columns:
        df_human = df[df['host_category'] == 'human']
        pre_human = None
        if df_pre_collation is not None and 'host_category' in df_pre_collation.columns:
            # Create a copy of pre_collation and update host_category from post-curation data
            df_pre_collation_copy = df_pre_collation.copy()
            # Join host_category from post-curation human samples
            human_host_map = df_human[['sample_accession', 'host_category']].copy()
            # Merge to update host_category in pre-curation data
            df_pre_collation_copy = df_pre_collation_copy.drop(columns=['host_category'], errors='ignore')
            df_pre_collation_copy = df_pre_collation_copy.merge(
                human_host_map, on='sample_accession', how='left', suffixes=('', '_post')
            )
            # Now filter to human hosts in the updated pre-curation data
            pre_human = df_pre_collation_copy[df_pre_collation_copy['host_category'] == 'human']
        output_path_human = os.path.join(
            output_dir, 'isolation_source_category_pre_and_post_curation_human_hosts.png'
        )
        _do_plot(df_human, output_path_human, pre_human, plot_title="Isolation Sources in Human Hosts")


def plot_isolation_source_category_with_parsing_stacked(df, output_dir, annotate_min_count=250):
    """
    Plot isolation source category distribution showing how original isolation_source
    values were parsed into categories. Each bar is stacked by original isolation_source
    values (all steelblue with white division lines). Uses fixed categories from
    ISOLATION_SOURCE_CATEGORIES_TO_PLOT.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns including 'isolation_source_category' and 'isolation_source'
    output_dir : str
        Directory to save the figure
    annotate_min_count : int, default=250
        Minimum count threshold for annotating segment labels
    """
    import os
    
    if 'isolation_source_category' not in df.columns:
        return
    
    if 'isolation_source' not in df.columns:
        return
    
    df_plot = df.copy()
    
    # Filter to only fixed categories that exist in the data (excluding NA values)
    existing_categories = df_plot['isolation_source_category'].dropna().unique()
    fixed_categories = [cat for cat in ISOLATION_SOURCE_CATEGORIES_TO_PLOT 
                       if cat in existing_categories]
    
    if len(fixed_categories) == 0:
        return
    
    # Filter to fixed categories
    df_plot = df_plot[df_plot['isolation_source_category'].isin(fixed_categories)].copy()
    df_plot = df_plot[df_plot['isolation_source_category'].notna()].copy()
    df_plot = df_plot[df_plot['isolation_source'].notna()].copy()
    
    if len(df_plot) == 0:
        return
    
    # Group by category and original isolation_source to create stacked data
    # Make grouping case-insensitive by converting isolation_source to lowercase
    df_plot_grouping = df_plot.copy()
    df_plot_grouping['isolation_source_lower'] = df_plot_grouping['isolation_source'].str.lower()
    
    # Group by lowercase version and sum counts (case-insensitive grouping)
    grouped = df_plot_grouping.groupby(['isolation_source_category', 'isolation_source_lower']).size().reset_index(name='count')
    
    # Rename back to isolation_source for consistency (now lowercase)
    grouped = grouped.rename(columns={'isolation_source_lower': 'isolation_source'})
    
    # Create pivot table: rows=categories, columns=original_sources (lowercase), values=counts
    pivot_data = grouped.pivot(index='isolation_source_category', columns='isolation_source', values='count').fillna(0)
    
    # Sort categories by total samples (descending)
    pivot_data['_total'] = pivot_data.sum(axis=1)
    pivot_data = pivot_data.sort_values('_total', ascending=False)
    pivot_data = pivot_data.drop('_total', axis=1)
    
    # Sort columns by total contribution (descending) to put most common sources first
    column_totals = pivot_data.sum().sort_values(ascending=False)
    pivot_data = pivot_data[column_totals.index]
    
    # Truncate category labels to first two words for readability
    truncated_labels = []
    for label in pivot_data.index:
        words = str(label).split()[:3]
        truncated_labels.append(' '.join(words))
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Plot stacked bars - all steelblue with black edges
    x_positions = range(len(pivot_data))
    bottom = np.zeros(len(pivot_data))
    
    # Plot each original source as a segment and add labels for segments > annotate_min_count
    for col in pivot_data.columns:
        values = pivot_data[col].values
        ax.bar(x_positions, values, bottom=bottom, 
               color='steelblue', edgecolor='black', linewidth=0.5, width=0.8)
        
        # Add labels for segments with count > annotate_min_count
        for i, (val, bot) in enumerate(zip(values, bottom)):
            if val > annotate_min_count:
                # Position label in the middle of the segment
                # Show the original isolation_source value (col) instead of count
                # Limit to first three words and add quotes
                label_y = bot + val / 2
                words = str(col).split()[:3]
                label_text = f'"{ " ".join(words) }"'
                ax.text(i, label_y, label_text,
                       ha='center', va='center', fontsize=8, color='white', style='italic')
        
        bottom += values
    
    ax.set_xticks(x_positions)
    ax.set_xticklabels(truncated_labels, rotation=45, ha='right')
    ax.set_ylabel('Number of Samples', fontsize=12)
    ax.set_title('Isolation Source Category Parsing Detail', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    ax.set_ylim(0, 13999)

    # Add value labels on top of bars (sample count, then number of names)
    for i, (idx, row) in enumerate(pivot_data.iterrows()):
        n_categories = (row > 0).sum()
        total = row.sum()
        if n_categories > 0:
            label = f"{int(total)}\n{n_categories} names"
            ax.text(i, total, label, ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'isolation_source_category_parsing.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_host_category_parsing(df, output_dir, annotate_min_count=250):
    """
    Plot host category distribution showing how original host values were parsed into categories.
    Creates two subplots: left shows all categories except 'human', right shows 'human' with
    independent y-axis. Each bar is stacked by original host values.
    Annotations appear for segments with count > 75 (non-human categories) or > 2000 (human).
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'host_category' and 'host' columns
    output_dir : str
        Directory to save the figure
    annotate_min_count : int, default=250
        Minimum count threshold for annotating segment labels (deprecated - not used)
    """
    import os
    
    if 'host_category' not in df.columns:
        return
    
    if 'host' not in df.columns:
        return
    
    df_plot = df.copy()
    
    # Filter to only fixed categories that exist in the data (excluding NA values)
    existing_categories = df_plot['host_category'].dropna().unique()
    fixed_categories = [cat for cat in HOST_CATEGORIES_TO_PLOT 
                       if cat in existing_categories]
    
    if len(fixed_categories) == 0:
        return
    
    # Separate human from other categories
    human_categories = [cat for cat in fixed_categories if cat == 'human']
    other_categories = [cat for cat in fixed_categories if cat != 'human']
    
    # Filter to fixed categories
    df_plot = df_plot[df_plot['host_category'].isin(fixed_categories)].copy()
    df_plot = df_plot[df_plot['host_category'].notna()].copy()
    df_plot = df_plot[df_plot['host'].notna()].copy()
    
    if len(df_plot) == 0:
        return
    
    # Group by category and original host to create stacked data
    # Make grouping case-insensitive by converting host to lowercase
    df_plot_grouping = df_plot.copy()
    df_plot_grouping['host_lower'] = df_plot_grouping['host'].str.lower()
    
    # Group by lowercase version and sum counts (case-insensitive grouping)
    grouped = df_plot_grouping.groupby(['host_category', 'host_lower']).size().reset_index(name='count')
    
    # Rename back to host for consistency (now lowercase)
    grouped = grouped.rename(columns={'host_lower': 'host'})
    
    # Create pivot table: rows=categories, columns=original_hosts (lowercase), values=counts
    pivot_data = grouped.pivot(index='host_category', columns='host', values='count').fillna(0)
    
    # Separate data for two subplots
    pivot_other = pivot_data.loc[[cat for cat in other_categories if cat in pivot_data.index]]
    pivot_human = pivot_data.loc[[cat for cat in human_categories if cat in pivot_data.index]]
    
    # Sort categories by total samples (descending)
    if len(pivot_other) > 0:
        pivot_other['_total'] = pivot_other.sum(axis=1)
        pivot_other = pivot_other.sort_values('_total', ascending=False)
        pivot_other = pivot_other.drop('_total', axis=1)
        # Sort columns by total contribution
        column_totals_other = pivot_other.sum().sort_values(ascending=False)
        pivot_other = pivot_other[column_totals_other.index]
    
    if len(pivot_human) > 0:
        pivot_human['_total'] = pivot_human.sum(axis=1)
        pivot_human = pivot_human.sort_values('_total', ascending=False)
        pivot_human = pivot_human.drop('_total', axis=1)
        # Sort columns by total contribution
        column_totals_human = pivot_human.sum().sort_values(ascending=False)
        pivot_human = pivot_human[column_totals_human.index]
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), gridspec_kw={'width_ratios': [10, 1]})
    fig.suptitle('Host Category Parsing Detail', fontsize=16, fontweight='bold')
    
    # Left subplot: all categories except human
    if len(pivot_other) > 0:
        truncated_labels_other = []
        for label in pivot_other.index:
            words = str(label).split()[:3]
            truncated_labels_other.append(' '.join(words))
        
        x_positions_other = range(len(pivot_other))
        bottom_other = np.zeros(len(pivot_other))
        
        for col in pivot_other.columns:
            values = pivot_other[col].values
            ax1.bar(x_positions_other, values, bottom=bottom_other, 
                   color='steelblue', edgecolor='black', linewidth=0.5, width=0.8)
            
            # Add labels for segments with count > 75 (for non-human categories)
            for i, (val, bot) in enumerate(zip(values, bottom_other)):
                if val > 75:
                    label_y = bot + val / 2
                    words = str(col).split()[:3]
                    label_text = f'"{ " ".join(words) }"'
                    ax1.text(i, label_y, label_text,
                           ha='center', va='center', fontsize=8, color='white', style='italic')
            
            bottom_other += values
        
        ax1.set_xticks(x_positions_other)
        ax1.set_xticklabels(truncated_labels_other, rotation=45, ha='right')
        ax1.set_ylabel('Number of Samples', fontsize=12)
        ax1.set_title('Host Categories (excluding human)', fontsize=14, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)
        
        # Add value labels on top of bars
        for i, (idx, row) in enumerate(pivot_other.iterrows()):
            n_categories = (row > 0).sum()
            total = row.sum()
            if n_categories > 0:
                label = f"{int(total)}\n{n_categories} names"
                ax1.text(i, total, label, ha='center', va='bottom', fontsize=9)
    
    # Right subplot: human only (independent y-axis)
    if len(pivot_human) > 0:
        truncated_labels_human = []
        for label in pivot_human.index:
            words = str(label).split()[:3]
            truncated_labels_human.append(' '.join(words))
        
        x_positions_human = range(len(pivot_human))
        bottom_human = np.zeros(len(pivot_human))
        
        for col in pivot_human.columns:
            values = pivot_human[col].values
            ax2.bar(x_positions_human, values, bottom=bottom_human, 
                   color='steelblue', edgecolor='black', linewidth=0.5, width=0.8)
            
            # Add labels for segments with count > 2000 (for human category)
            for i, (val, bot) in enumerate(zip(values, bottom_human)):
                if val > 2000:
                    label_y = bot + val / 2
                    words = str(col).split()[:3]
                    label_text = f'"{ " ".join(words) }"'
                    ax2.text(i, label_y, label_text,
                           ha='center', va='center', fontsize=8, color='white', style='italic')
            
            bottom_human += values
        
        ax2.set_xticks(x_positions_human)
        ax2.set_xticklabels(truncated_labels_human, rotation=45, ha='right')
        ax2.set_title('Human', fontsize=14, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)
        
        # Add value labels on top of bars
        for i, (idx, row) in enumerate(pivot_human.iterrows()):
            n_categories = (row > 0).sum()
            total = row.sum()
            if n_categories > 0:
                label = f"{int(total)}\n{n_categories} names"
                ax2.text(i, total, label, ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'host_category_parsing.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_host_category_pre_and_post_curation(df, output_dir, df_pre_collation=None):
    """
    Plot host category distribution with "Not-filled" bars.
    Creates three side-by-side plots: left plot shows 'human' only (narrow),
    middle plot shows all other host categories (wide), right plot shows 'Not-filled' only (narrow).
    Human and Not-filled panels share the same y-axis scale for direct comparison.
    If df_pre_collation is provided, plots side-by-side bars for pre/post comparison.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns including 'host_category' (collated data)
    output_dir : str
        Directory to save the figure
    df_pre_collation : pd.DataFrame, optional
        Pre-collation DataFrame for side-by-side comparison. If None, plots single dataframe.
    """
    import os
    import numpy as np
    
    if 'host_category' not in df.columns:
        return
    
    # Calculate for collated dataframe (all categories)
    category_data_collated, _ = calculate_host_completeness(df.copy())
    
    if len(category_data_collated) == 0:
        return
    

    category_data_pre, _ = calculate_host_completeness(df_pre_collation.copy())
    
    # Separate categories into three groups: human, others, Not-filled
    human_cats = []
    other_cats = []
    not_filled_cats = []
    
    # Collect all categories from both dataframes
    all_cats_set = set(category_data_collated.index) | set(category_data_pre.index)
    
    for cat in all_cats_set:
        if cat == 'human':
            human_cats.append(cat)
        elif cat == 'Not-filled':
            not_filled_cats.append(cat)
        else:
            other_cats.append(cat)
    
    # Filter to only categories with count > 0 in post-curation (collated) data
    human_cats = [cat for cat in human_cats if category_data_collated.get(cat, 0) > 0]
    other_cats = [cat for cat in other_cats if category_data_collated.get(cat, 0) > 0]
    
    # Sort other categories by collated values (descending)
    other_cats = sorted(other_cats, key=lambda x: category_data_collated.get(x, 0), reverse=True)
    
    # Create aligned data series with zeros for missing categories
    collated_human = [category_data_collated.get(cat, 0) for cat in human_cats]
    pre_human = [category_data_pre.get(cat, 0) for cat in human_cats]
    collated_other = [category_data_collated.get(cat, 0) for cat in other_cats]
    pre_other = [category_data_pre.get(cat, 0) for cat in other_cats]
    collated_not_filled = [category_data_collated.get(cat, 0) for cat in not_filled_cats]
    pre_not_filled = [category_data_pre.get(cat, 0) for cat in not_filled_cats]
    
    # Create three subplots side by side with 1:12:1 width ratio
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 8), gridspec_kw={'width_ratios': [1, 11, 1]})
    
    # Add overall title
    fig.suptitle('Hosts, Pre- and Post-curation', fontsize=16, fontweight='bold')
    
    # ax1 (left): human only (narrow)
    if len(human_cats) > 0:
        x_human = np.arange(len(human_cats))
        width = 0.35
        
        bars1_human = ax1.bar(x_human - width/2, pre_human, width, label='Pre-curation', color='lightblue')
        bars2_human = ax1.bar(x_human + width/2, collated_human, width, label='Post-curation', color='steelblue')
        
        ax1.set_xticks(x_human)
        ax1.set_xticklabels(human_cats, rotation=45, ha='right', fontsize=11)
        ax1.set_ylabel('Number of Samples', fontsize=12)
        ax1.set_title('Human', fontsize=14, fontweight='bold')
        # No legend for human subplot
        ax1.grid(axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bars in [bars1_human, bars2_human]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax1.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9)
    
    # ax2 (middle): other host categories (wide)
    if len(other_cats) > 0:
        x_other = np.arange(len(other_cats))
        width = 0.45
        
        bars1_other = ax2.bar(x_other - width/2, pre_other, width, label='Pre-curation', color='lightblue')
        bars2_other = ax2.bar(x_other + width/2, collated_other, width, label='Post-curation', color='steelblue')
        
        ax2.set_xticks(x_other)
        ax2.set_xticklabels(other_cats, rotation=45, ha='right', fontsize=11)
        # No y-axis label (only first subplot has label)
        ax2.set_title('Non-Human Hosts', fontsize=14, fontweight='bold')
        ax2.legend(fontsize=11)
        ax2.grid(axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bars in [bars1_other, bars2_other]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax2.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9)
    
    # ax3 (right): Not-filled only (narrow)
    if len(not_filled_cats) > 0:
        x_not_filled = np.arange(len(not_filled_cats))
        width = 0.35
        
        bars1_not_filled = ax3.bar(x_not_filled - width/2, pre_not_filled, width, label='Pre-curation', color='lightblue')
        bars2_not_filled = ax3.bar(x_not_filled + width/2, collated_not_filled, width, label='Post-curation', color='steelblue')
        
        ax3.set_xticks(x_not_filled)
        ax3.set_xticklabels(not_filled_cats, rotation=45, ha='right', fontsize=11)
        # No y-axis labels (shares scale with human panel)
        ax3.set_title('Not-filled', fontsize=14, fontweight='bold')
        ax3.grid(axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bars in [bars1_not_filled, bars2_not_filled]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax3.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height):,}',
                            ha='center', va='bottom', fontsize=9)
    
    # Set shared y-axis scale for human (ax1) and Not-filled (ax3)
    if len(human_cats) > 0 or len(not_filled_cats) > 0:
        ymax_human = ax1.get_ylim()[1] if len(human_cats) > 0 else 0
        ymax_not_filled = ax3.get_ylim()[1] if len(not_filled_cats) > 0 else 0
        ymax_shared = max(ymax_human, ymax_not_filled)
        if len(human_cats) > 0:
            ax1.set_ylim(0, ymax_shared)
        if len(not_filled_cats) > 0:
            ax3.set_ylim(0, ymax_shared)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'host_category_pre_and_post_curation.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def plot_parsing_statistics(df, output_dir):
    """
    Plot parsing statistics for region, isolation source, and host.
    Creates separate figures showing distribution of parsed values with stacked bars.
    Uses fixed category lists from module-level constants.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns
    output_dir : str
        Directory to save the figures
        
    Returns:
    --------
    dict : Unique value counts by field and parsing stage
    """
    # Call individual plotting functions
    plot_region_distribution_by_amr_study(df, output_dir)
    plot_isolation_source_category_with_parsing_stacked(df, output_dir)
    plot_host_category_parsing(df, output_dir)
    
    # Collect statistics (same as before for backward compatibility)
    stats = {}
    
    # Region stats
    if 'region' in df.columns:
        stats['region'] = {
            'country': df['country'].nunique() if 'country' in df.columns else 0,
            'country_parsed': df['country_parsed'].nunique() if 'country_parsed' in df.columns else 0,
            'region': df['region'].nunique() if 'region' in df.columns else 0
        }
    else:
        stats['region'] = {
            'country': df['country'].nunique() if 'country' in df.columns else 0,
            'country_parsed': df['country_parsed'].nunique() if 'country_parsed' in df.columns else 0,
            'region': 0
        }
    
    # Isolation source stats
    if 'isolation_source_category' in df.columns:
        stats['isolation_source'] = {
            'isolation_source': df['isolation_source'].nunique() if 'isolation_source' in df.columns else 0,
            'isolation_source_parsed': df['isolation_source_parsed'].nunique() if 'isolation_source_parsed' in df.columns else 0,
            'isolation_source_category': df['isolation_source_category'].nunique() if 'isolation_source_category' in df.columns else 0
        }
    else:
        stats['isolation_source'] = {
            'isolation_source': df['isolation_source'].nunique() if 'isolation_source' in df.columns else 0,
            'isolation_source_parsed': df['isolation_source_parsed'].nunique() if 'isolation_source_parsed' in df.columns else 0,
            'isolation_source_category': 0
        }
    
    # Host stats
    if 'host_category' in df.columns:
        stats['host'] = {
            'host': df['host'].nunique() if 'host' in df.columns else 0,
            'host_parsed': df['host_parsed'].nunique() if 'host_parsed' in df.columns else 0,
            'host_category': df['host_category'].nunique() if 'host_category' in df.columns else 0
        }
    else:
        stats['host'] = {
            'host': df['host'].nunique() if 'host' in df.columns else 0,
            'host_parsed': df['host_parsed'].nunique() if 'host_parsed' in df.columns else 0,
            'host_category': 0
        }
    
    return stats


def plot_country_map(df, output_dir):
    """
    Plot world map showing sample distribution by country.
    Countries are filled with green color, with intensity based on sample count.
    Darkest green is for countries with 3000+ samples.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with country_parsed and region columns
    output_dir : str
        Directory to save the figure
    """
    import os
    import plotly.express as px

    print("\n[plot_country_map] Starting country map generation")
    if 'country_parsed' not in df.columns:
        print("Warning: 'country_parsed' column not found, skipping country map")
        return
    
    if 'region' not in df.columns:
        print("Warning: 'region' column not found, skipping country map")
        return
    
    # Filter to rows with valid country_parsed values
    df_valid = df[df['country_parsed'].notna()].copy()
    
    print(f"[plot_country_map] Found {len(df_valid)} rows with valid country_parsed values")
    
    if len(df_valid) == 0:
        print("Warning: No valid country data found, skipping country map")
        return
    
    # Count samples per country and get region for each country
    # Each country should only appear once with its region, so we take the first region value per country
    if 'sample_accession' in df_valid.columns:
        # Count unique samples per country
        country_data = df_valid.groupby('country_parsed').agg({
            'region': 'first',
            'sample_accession': 'nunique'
        }).reset_index()
        country_data = country_data.rename(columns={'sample_accession': 'count'})
    else:
        # Count rows per country
        country_counts = df_valid.groupby('country_parsed').size().reset_index(name='count')
        country_regions = df_valid.groupby('country_parsed')['region'].first().reset_index()
        country_data = country_counts.merge(country_regions, on='country_parsed', how='left')
    
    # Keep original count for hover display
    country_data['display_count'] = country_data['count']
    
    # Filter out rows with missing region
    country_data = country_data[country_data['region'].notna()]
    
    if len(country_data) == 0:
        print("Warning: No valid country data with regions found, skipping country map")
        return
    
    # Convert country names to ISO-3 codes (requires pycountry package)
    import pycountry
    
    country_to_iso3 = {}
    unrecognized_countries = []
    
    # Process regular countries - get ISO-3 codes for plotly's built-in country centroids
    for country_name in country_data['country_parsed'].unique():
        # Try to find the country by name
        try:
            country = pycountry.countries.search_fuzzy(country_name)[0]
            country_to_iso3[country_name] = country.alpha_3
        except (LookupError, IndexError):
            # Try common alternative names
            name_mappings = {
                'USA': 'USA',
                'United States of America': 'USA',
                'United Kingdom': 'GBR',
                'United Arab Emirates': 'ARE',
                'South Korea': 'KOR',
                'Vietnam': 'VNM',
                'Czech Republic': 'CZE',
                'Czechia': 'CZE',
            }
            if country_name in name_mappings:
                country_to_iso3[country_name] = name_mappings[country_name]
            else:
                unrecognized_countries.append(country_name)
    
    # Add ISO-3 codes to countries dataframe
    country_data = country_data.copy()
    country_data['iso3'] = country_data['country_parsed'].map(country_to_iso3)
    
    # Filter out countries without ISO-3 codes
    country_data_with_iso = country_data[country_data['iso3'].notna()].copy()
    
    if len(unrecognized_countries) > 0:
        print(f"Warning: Could not find ISO-3 codes for {len(unrecognized_countries)} countries: {', '.join(unrecognized_countries[:5])}")
        if len(unrecognized_countries) > 5:
            print(f"  ... and {len(unrecognized_countries) - 5} more")
    
    if len(country_data_with_iso) == 0:
        print("Warning: No countries could be mapped, skipping country map")
        return
    
    # Try to create the map
    try:
        import plotly.graph_objects as go
        
        fig = go.Figure()
        
        # Add choropleth map with discrete color bins
        if len(country_data_with_iso) > 0:
            # Define discrete color bins
            bins = [
                (1, 25, '1-25', '#d4eac7'),
                (26, 100, '26-100', '#a9d890'),
                (101, 250, '101-250', '#5eb24e'),
                (251, 1000, '251-1000', '#2d8a2f'),
                (1001, 2500, '1001-2500', '#145214'),
                (2501, 999999, '>2500', '#0a3d0a')
            ]
            
            # Assign each country to a bin and color
            def get_bin_info(count):
                for min_val, max_val, label, color in bins:
                    if min_val <= count <= max_val:
                        return label, color
                return bins[-1][2], bins[-1][3]  # Default to last bin
            
            country_data_with_iso['bin_label'] = country_data_with_iso['display_count'].apply(lambda x: get_bin_info(x)[0])
            country_data_with_iso['bin_color'] = country_data_with_iso['display_count'].apply(lambda x: get_bin_info(x)[1])
            
            # Create a separate trace for each bin to get discrete legend entries
            for min_val, max_val, label, color in bins:
                bin_data = country_data_with_iso[
                    (country_data_with_iso['display_count'] >= min_val) & 
                    (country_data_with_iso['display_count'] <= max_val)
                ]
                
                if len(bin_data) > 0:
                    fig.add_trace(go.Choropleth(
                        locations=bin_data['iso3'],
                        locationmode='ISO-3',
                        z=[1] * len(bin_data),  # Dummy values - we use marker color instead
                        text=bin_data['country_parsed'],
                        customdata=bin_data[['display_count', 'region']],
                        hovertemplate='<b>%{text}</b><br>Count: %{customdata[0]:,}<br>Region: %{customdata[1]}<extra></extra>',
                        marker=dict(line=dict(width=0)),
                        colorscale=[[0, color], [1, color]],  # Solid color
                        showscale=False,
                        name=label,
                        legendgroup=label,
                        showlegend=True
                    ))
        
        # Calculate region totals and representative positions for annotations
        # We'll use the geographic center (mean lat/lon) of countries in each region
        region_annotations = []
        
        # Calculate region totals using original uncapped data from df_valid
        if 'sample_accession' in df_valid.columns:
            region_totals = df_valid.groupby('region')['sample_accession'].nunique().to_dict()
        else:
            region_totals = df_valid.groupby('region').size().to_dict()
        
        # First, we need to get lat/lon for the countries (use a simple approximation based on ISO codes)
        # For simplicity, we'll calculate the centroid of all countries in each region
        for region in country_data_with_iso['region'].unique():
            total_samples = region_totals.get(region, 0)
            
            # Simple region position mapping (approximate geographic centers)
            region_positions = {
                'N. America': (38, -140),
                'Central & S. America': (-15, -95),
                'W. Europe': (45, -23),
                'E. Europe': (51, 32),
                'Africa': (-5, 1),
                'M. East, Central Asia': (1, 73), # Needs to be on three lines, /n between M.East and Central Asia
                'E. Asia': (24, 131),
                'Oceania': (-28, 168),
            }
            
            if region in region_positions:
                lat, lon = region_positions[region]
                
                # Format region name with line breaks for long names
                region_display = region
                if region == 'Central & S. America':
                    region_display = 'Central &<br>S. America'
                elif region == 'M. East, Central Asia':
                    region_display = 'M. East,<br>Central Asia'
                
                region_annotations.append(
                    dict(
                        lon=lon,
                        lat=lat,
                        text=f"{region_display}<br>n={total_samples:,}",
                        showarrow=False,
                        font=dict(size=10, color='black', family='Arial Black'),
                        bgcolor='rgba(255, 255, 255, 0.7)',
                        borderpad=4
                    )
                )
        
        fig.update_layout(
            title='Sample Distribution by Country',
            geo=dict(
                showframe=False,
                showcoastlines=False,
                projection_type='robinson',
                landcolor='lightgray',
                oceancolor='lightblue',
                lataxis=dict(range=[-55, 70]),  # Exclude Antarctica and focus on inhabited areas
            ),
            height=600
        )
        
        # Add region labels as a separate geographic trace
        if region_annotations:
            fig.add_trace(go.Scattergeo(
                lat=[a['lat'] for a in region_annotations],
                lon=[a['lon'] for a in region_annotations],
                text=[a['text'] for a in region_annotations],
                mode='text',
                textfont=dict(size=11, color='black', family='Arial Black'),
                hoverinfo='skip',
                showlegend=False
            ))
        
        # Update layout for better appearance with horizontal legend below
        fig.update_layout(
            height=700,  # Increased to accommodate legend below
            geo=dict(
                showframe=False,
                showcoastlines=False,
                projection_type='robinson',
                lataxis=dict(range=[-55, 70])  # Exclude Antarctica
            ),
            legend=dict(
                orientation='h',
                yanchor='top',
                y=-0.05,
                xanchor='center',
                x=0.5,
                title=dict(text='Genomes per Country', font=dict(size=12)),
                font=dict(size=10)
            )
        )
        
        # Save as HTML
        output_path_html = os.path.join(output_dir, 'country_distribution_map.html')
        fig.write_html(output_path_html)
        
        # Save as PNG (static image)
        output_path_png = os.path.join(output_dir, 'country_distribution_map.png')
        try:
            fig.write_image(output_path_png, width=1200, height=600, scale=2)
            print(f"[plot_country_map] Country map created with {len(country_data_with_iso)} countries (ISO-3 mapped)")
        except Exception as e:
            print(f"Warning: Could not save PNG version of map: {e}")
            print("  (This may require 'kaleido' package: pip install kaleido)")
        
        # Try to identify countries that plotly might not recognize
        # We can't directly detect this, but we can warn if the map seems incomplete
        # by checking if all countries are plotted (this is approximate)
        print(f"Country map created with {len(country_data)} countries")
        
    except Exception as e:
        print(f"Warning: Error creating country map: {e}")
        # Try to identify problematic country names by attempting individual checks
        unrecognized = []
        for country in country_data['country_parsed'].unique():
            try:
                # Try a simple test plot with just this country
                test_df = pd.DataFrame({'country': [country], 'count': [1]})
                test_fig = px.scatter_geo(test_df, locations='country', locationmode='country names')
                test_fig.data = []  # Clear data to avoid issues
            except Exception:
                unrecognized.append(country)
        
        if unrecognized:
            print(f"Warning: The following countries may not be recognized by plotly: {', '.join(unrecognized[:10])}")
            if len(unrecognized) > 10:
                print(f"... and {len(unrecognized) - 10} more")


def plot_date_distribution(df, output_dir):
    """
    Plot histogram of collection dates by year groups.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with year_parsed column
    output_dir : str
        Directory to save the figure
    """
    import os
    
    if 'year_parsed' not in df.columns:
        print("Warning: 'year_parsed' column not found, skipping date distribution plot")
        return
    
    # Filter to valid years
    valid_years = df['year_parsed'].dropna()
    
    if len(valid_years) == 0:
        print("Warning: No valid years found, skipping date distribution plot")
        return
    
    # Define bins and labels
    labels = ['Pre-2000', '2000-2005', '2005-2010', '2010-2015', '2015-2020', '2020-2025']
    
    # Create bins manually to handle edge cases
    valid_years_series = pd.Series(valid_years)
    binned_list = []
    
    for year in valid_years_series:
        if year < 2000:
            binned_list.append('Pre-2000')
        elif 2000 <= year < 2005:
            binned_list.append('2000-2005')
        elif 2005 <= year < 2010:
            binned_list.append('2005-2010')
        elif 2010 <= year < 2015:
            binned_list.append('2010-2015')
        elif 2015 <= year < 2020:
            binned_list.append('2015-2020')
        elif 2020 <= year < 2025:
            binned_list.append('2020-2025')
        else:
            binned_list.append('2025+')
    
    binned = pd.Series(binned_list, index=valid_years_series.index)
    
    # Count values in each bin
    counts = binned.value_counts()
    # Filter out 2025+ category completely
    counts = counts[counts.index != '2025+']
    # Reindex to ensure all labels are present in correct order
    counts = counts.reindex([label for label in labels if label in counts.index], fill_value=0)
    # Reorder to match desired order
    counts_ordered = pd.Series(index=labels, dtype=int)
    for label in labels:
        if label in counts.index:
            counts_ordered[label] = counts[label]
        else:
            counts_ordered[label] = 0
    
    # Create histogram
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(range(len(counts_ordered)), counts_ordered.values, color='steelblue')
    ax.set_xticks(range(len(counts_ordered)))
    ax.set_xticklabels(counts_ordered.index, rotation=45, ha='right')
    ax.set_ylabel('Number of Samples', fontsize=12)
    ax.set_title('Collection Date Distribution by Year Groups', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        if height > 0:  # Only label non-zero bars
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(height):,}',
                   ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    # Save figure
    output_path = os.path.join(output_dir, 'date_distribution.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()


def plot_date_distribution_pre_and_post_curation(df, output_dir, df_pre_collation=None):
    """
    Plot histogram of collection dates by year groups with "Other" and "Not-filled" bars.
    All bars are simple steelblue (no stacking). If df_pre_collation is provided, plots side-by-side bars.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with year_parsed column (collated data)
    output_dir : str
        Directory to save the figure
    df_pre_collation : pd.DataFrame, optional
        Pre-collation DataFrame for side-by-side comparison. If None, plots single dataframe.
    """
    import os
    import numpy as np
    
    if 'year_parsed' not in df.columns:
        if df_pre_collation is None or 'year_parsed' not in df_pre_collation.columns:
            print("Warning: 'year_parsed' column not found, skipping date distribution plot")
            return
    
    # Calculate for collated dataframe
    date_data_collated, _ = calculate_date_completeness(df.copy())
    
    # If pre-collation dataframe is provided, calculate for it and plot side-by-side
    if df_pre_collation is not None and 'year_parsed' in df_pre_collation.columns:
        date_data_pre, _ = calculate_date_completeness(df_pre_collation.copy())
        
        # Fixed ordering: Pre-2000, 2000-2005, 2005-2010, 2010-2015, 2015-2020, 2020-2025
        time_periods = ['Pre-2000', '2000-2005', '2005-2010', '2010-2015', '2015-2020', '2020-2025']
        # Keep only time periods that exist in either dataframe (not including Not-filled)
        time_periods_only = [cat for cat in time_periods if cat in date_data_collated.index or cat in date_data_pre.index]
        # Check if Not-filled exists in either dataframe
        not_filled_only = []
        if 'Not-filled' in date_data_collated.index or 'Not-filled' in date_data_pre.index:
            not_filled_only = ['Not-filled']
        
        # Create aligned data series with zeros for missing categories
        collated_periods = [date_data_collated.get(cat, 0) for cat in time_periods_only]
        pre_periods = [date_data_pre.get(cat, 0) for cat in time_periods_only]
        collated_not_filled = [date_data_collated.get(cat, 0) for cat in not_filled_only]
        pre_not_filled = [date_data_pre.get(cat, 0) for cat in not_filled_only]
        
        # Create two subplots: time periods on left (wide), Not-filled on right (narrow)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6), gridspec_kw={'width_ratios': [8, 1]})
        
        # ax1 (left): Time periods only
        if len(time_periods_only) > 0:
            x_periods = np.arange(len(time_periods_only))
            width = 0.45
            
            bars1_periods = ax1.bar(x_periods - width/2, pre_periods, width, label='Pre-curation', color='lightblue')
            bars2_periods = ax1.bar(x_periods + width/2, collated_periods, width, label='Post-curation', color='steelblue')
            
            ax1.set_xticks(x_periods)
            ax1.set_xticklabels(time_periods_only, rotation=45, ha='right', fontsize=11)
            ax1.set_ylabel('Number of Samples', fontsize=12)
            ax1.set_title('Collection Date Distribution by Year Groups', fontsize=14, fontweight='bold')
            ax1.legend(fontsize=11)
            ax1.grid(axis='y', alpha=0.3)
            
            # Add value labels on top of bars
            for bars in [bars1_periods, bars2_periods]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax1.text(bar.get_x() + bar.get_width()/2., height,
                               f'{int(height):,}',
                               ha='center', va='bottom', fontsize=9)
        
        # ax2 (right): Not-filled only
        if len(not_filled_only) > 0:
            x_not_filled = np.arange(len(not_filled_only))
            width = 0.175
            
            bars1_not_filled = ax2.bar(x_not_filled - width/2, pre_not_filled, width, label='Pre-curation', color='lightblue')
            bars2_not_filled = ax2.bar(x_not_filled + width/2, collated_not_filled, width, label='Post-curation', color='steelblue')
            
            ax2.set_xticks(x_not_filled)
            ax2.set_xticklabels(not_filled_only, rotation=45, ha='right', fontsize=11)
            # No y-axis label (only first subplot has label)
            ax2.set_title('Date not filled', fontsize=14, fontweight='bold')
            ax2.grid(axis='y', alpha=0.3)
            
            # Add value labels on top of bars
            for bars in [bars1_not_filled, bars2_not_filled]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax2.text(bar.get_x() + bar.get_width()/2., height,
                               f'{int(height):,}',
                               ha='center', va='bottom', fontsize=9)
    else:
        # Single dataframe plotting
        if len(date_data_collated) == 0:
            return
        
        # Split into time periods and Not-filled
        time_periods_only = [cat for cat in date_data_collated.index if cat != 'Not-filled']
        not_filled_only = []
        if 'Not-filled' in date_data_collated.index:
            not_filled_only = ['Not-filled']
        
        # Get values
        periods_values = [date_data_collated[cat] for cat in time_periods_only]
        not_filled_values = [date_data_collated[cat] for cat in not_filled_only]
        
        # Create two subplots: time periods on left (wide), Not-filled on right (narrow)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={'width_ratios': [6, 1]})
        
        # ax1 (left): Time periods only
        if len(time_periods_only) > 0:
            ax1.bar(range(len(time_periods_only)), periods_values, color='steelblue')
            ax1.set_xticks(range(len(time_periods_only)))
            ax1.set_xticklabels(time_periods_only, rotation=45, ha='right')
            ax1.set_ylabel('Number of Samples', fontsize=12)
            ax1.set_title('Collection Date Distribution by Year Groups', fontsize=14, fontweight='bold')
            ax1.grid(axis='y', alpha=0.3)
            
            # Add value labels on bars
            for i, (cat, val) in enumerate(zip(time_periods_only, periods_values)):
                if val > 0:
                    ax1.text(i, val, f'{int(val):,}',
                           ha='center', va='bottom', fontsize=9)
        
        # ax2 (right): Not-filled only
        if len(not_filled_only) > 0:
            ax2.bar(range(len(not_filled_only)), not_filled_values, color='steelblue', width=0.4)
            ax2.set_xticks(range(len(not_filled_only)))
            ax2.set_xticklabels(not_filled_only, rotation=45, ha='right')
            # No y-axis label (only first subplot has label)
            ax2.set_title('Date not filled', fontsize=14, fontweight='bold')
            ax2.grid(axis='y', alpha=0.3)
            
            # Add value labels on bars
            for i, (cat, val) in enumerate(zip(not_filled_only, not_filled_values)):
                if val > 0:
                    ax2.text(i, val, f'{int(val):,}',
                           ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    # Save figure
    output_path = os.path.join(output_dir, 'date_distribution_pre_and_post_curation.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def report_curation_summary(df, output_file, google_sheet_id=None, sheet_name=None, pre_collation_df=None, plots_output_dir=None):
    """
    Generate and print a comprehensive curation quality report.
    Uses fixed category lists from module-level constants.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with parsed columns
    output_file : str
        Path to output TSV file for project summary table
    google_sheet_id : str, optional
        Google Spreadsheet ID (defaults to STUDY_METADATA_GOOGLE_SHEET_ID constant)
    sheet_name : str, optional
        Name of the sheet to read (defaults to STUDY_METADATA_SHEET_NAME constant)
    pre_collation_df : pd.DataFrame, optional
        Pre-collation dataframe for comparison
    plots_output_dir : str, optional
        Path to directory for saving plots. If None, uses same directory as output_file
    """
    print("\n" + "=" * 60)
    print("Metadata Parsing Quality Report")
    print("=" * 60 + "\n")
    
    # 1. Calculate completeness
    columns_to_check = ['host_parsed', 'country_parsed', 'collection_date_parsed', 'isolation_source_parsed']
    completeness = calculate_column_completeness(df, columns_to_check)
    
    print("Completeness Summary:")
    for col, comp_ratio in completeness.items():
        status = "✓" if comp_ratio >= 0.8 else "⚠ (below 0.8 threshold)"
        print(f"  {col}: {comp_ratio:.3f} {status}")
    
    print("\n" + "-" * 60)
    print("Unhelpful Annotations Found:")
    print("-" * 60)
    
    # 2. Identify unhelpful annotations
    df = identify_unhelpful_annotations(df)
    
    # 3. Report on each unhelpful category
    # Retrieve unhelpful values dynamically
    unhelpful_isolation_source = retrieve_unhelpful_isolation_source_annotations(df)
    unhelpful_host = retrieve_unhelpful_host_annotations(df)
    
    # Report isolation_source_parsed unhelpful values
    if 'isolation_source_parsed' in df.columns:
        for unhelpful_val in unhelpful_isolation_source:
            mask = df['isolation_source_parsed'] == unhelpful_val
            if mask.any():
                n_samples = mask.sum()
                affected_studies = df[mask]['study_accession'].unique()
                n_studies = len(affected_studies)
                
                print(f"\n  isolation_source_parsed - \"{unhelpful_val}\":")
                print(f"    Total samples: {n_samples:,}")
                print(f"    Unique projects: {n_studies}")
                # print("    Breakdown by study_accession:")
                
                # # Get total unique samples per study for context (matching metadata_collation filtering)
                # if 'sample_accession' in df.columns:
                #     study_totals = df.groupby('study_accession')['sample_accession'].nunique()
                #     study_counts = df[mask].groupby('study_accession')['sample_accession'].nunique()
                # else:
                #     # Fallback to row count if sample_accession column doesn't exist
                #     study_totals = df.groupby('study_accession').size()
                #     study_counts = df[mask].groupby('study_accession').size()
                
                # for study_acc in sorted(affected_studies):
                #     n_affected = study_counts[study_acc]
                #     n_total = study_totals[study_acc]
                #     print(f"      - {study_acc}: {n_affected} samples of {n_total} total samples in study")
    
    # Report host_parsed unhelpful values
    if 'host_parsed' in df.columns:
        for unhelpful_val in unhelpful_host:
            mask = df['host_parsed'] == unhelpful_val
            if mask.any():
                n_samples = mask.sum()
                affected_studies = df[mask]['study_accession'].unique()
                n_studies = len(affected_studies)
                
                print(f"\n  host_parsed - \"{unhelpful_val}\":")
                print(f"    Total samples: {n_samples:,}")
                print(f"    Unique projects: {n_studies}")
                print("    Breakdown by study_accession:")
                
                # Get total unique samples per study for context (matching metadata_collation filtering)
                if 'sample_accession' in df.columns:
                    study_totals = df.groupby('study_accession')['sample_accession'].nunique()
                    study_counts = df[mask].groupby('study_accession')['sample_accession'].nunique()
                else:
                    # Fallback to row count if sample_accession column doesn't exist
                    study_totals = df.groupby('study_accession').size()
                    study_counts = df[mask].groupby('study_accession').size()
                
                for study_acc in sorted(affected_studies):
                    n_affected = study_counts[study_acc]
                    n_total = study_totals[study_acc]
                    print(f"      - {study_acc}: {n_affected} samples of {n_total} total samples in study")
    
    # 4. Generate and save project summary table
    print("\n" + "-" * 60)
    print("Project Summary Table:")
    print("-" * 60)
    
    summary_table = generate_project_summary_table(df, google_sheet_id, sheet_name, pre_collation_df)
    
    if not summary_table.empty:
        print(f"\nSummary table with {len(summary_table)} projects:")
        display(summary_table)
        
        # Save to file
        summary_table.to_csv(output_file, sep="\t", index=False)
        print(f"\nProject summary table saved to: {output_file}")
    else:
        print("Warning: Could not generate summary table (missing required columns)")
    
    # 5. Generate visualizations
    print("\n" + "-" * 60)
    print("Generating Visualization Reports:")
    print("-" * 60)
    
    import os
    # Separate output directories for data and plots
    data_output_dir = os.path.dirname(output_file)
    if plots_output_dir is None:
        plots_output_dir = data_output_dir
    
    # Create plots output directory if it doesn't exist
    os.makedirs(plots_output_dir, exist_ok=True)
    
    # 1. Parsing statistics  
    parsing_stats = plot_parsing_statistics(df, plots_output_dir)
    
    # 2. Date distribution
    plot_date_distribution(df, plots_output_dir)
    
    # 3. Country distribution map 
    print("\nDEBUG: About to call plot_country_map")
    print(f"DEBUG: df columns include country_parsed: {'country_parsed' in df.columns}")
    print(f"DEBUG: df columns include region: {'region' in df.columns}")
    plot_country_map(df, plots_output_dir)
    print("DEBUG: plot_country_map returned")
    
    # 4. New plots with "Other" and "Not-filled" bars (only if pre_collation_df is provided)
    if pre_collation_df is not None:
        print("\nGenerating plots with 'Other' and 'Not-filled' bars (side-by-side comparison):")
        plot_region_distribution_pre_and_post_curation(df, plots_output_dir, df_pre_collation=pre_collation_df)
        plot_isolation_source_category_pre_and_post_curation(df, plots_output_dir, df_pre_collation=pre_collation_df)
        plot_host_category_pre_and_post_curation(df, plots_output_dir, df_pre_collation=pre_collation_df)
        plot_date_distribution_pre_and_post_curation(df, plots_output_dir, df_pre_collation=pre_collation_df)
    else:
        print("\nSkipping plots with 'Other' and 'Not-filled' bars (no pre-collation data provided)")
    
    print("\nVisualization files saved to:")
    print(f"  - {os.path.join(plots_output_dir, 'region_distribution.png')}")
    print(f"  - {os.path.join(plots_output_dir, 'isolation_source_category_parsing.png')}")
    print(f"  - {os.path.join(plots_output_dir, 'host_category_parsing.png')}")
    print(f"  - {os.path.join(plots_output_dir, 'host_category.png')}")
    print(f"  - {os.path.join(plots_output_dir, 'date_distribution.png')}")
    print(f"  - {os.path.join(plots_output_dir, 'country_distribution_map.html')}")
    print(f"  - {os.path.join(plots_output_dir, 'country_distribution_map.png')}")
    if pre_collation_df is not None:
        print("\nPlots with 'Other' and 'Not-filled' bars saved to:")
        print(f"  - {os.path.join(plots_output_dir, 'region_distribution_pre_and_post_curation.png')}")
        print(f"  - {os.path.join(plots_output_dir, 'isolation_source_category_pre_and_post_curation_all_hosts.png')}")
        print(f"  - {os.path.join(plots_output_dir, 'isolation_source_category_pre_and_post_curation_human_hosts.png')}")
        print(f"  - {os.path.join(plots_output_dir, 'host_category_pre_and_post_curation.png')}")
        print(f"  - {os.path.join(plots_output_dir, 'date_distribution_pre_and_post_curation.png')}")
    
    # Append text reports to log (will be captured by log_capture in main())
    print("\n" + "=" * 60)
    print("CURATION STATISTICS SUMMARY")
    print("=" * 60)
    print("\nUnique Values by Parsing Stage:")
    for field, counts in parsing_stats.items():
        print(f"  {field}:")
        for stage, count in counts.items():
            print(f"    {stage}: {count}")
    
    print("\n" + "=" * 60 + "\n")
    
    return df


def _load_complete_norway_biosample_ids(csv_path: str) -> set:
    """Read complete_norway_genomes.csv (first row title, second row header). Returns unique BioSample IDs."""
    df = pd.read_csv(csv_path, skiprows=1, low_memory=False)
    col = COMPLETE_NORWAY_GENOMES_BIOSAMPLE_COL
    if col not in df.columns:
        return set()
    ser = df[col].dropna().astype(str).str.strip()
    ser = ser[ser != ""]
    return set(ser.unique())


def manual_runs_to_add(df: pd.DataFrame, csv_path: str = MANUAL_RUNS_TO_ADD) -> pd.DataFrame:
    """Fill missing run_accession values from a manual Sample->run_accession table."""
    required_columns = {"Sample", "run_accession"}
    if "Sample" not in df.columns:
        print("WARNING: manual_runs_to_add skipped (main table missing 'Sample' column).")
        return df

    if "run_accession" not in df.columns:
        df["run_accession"] = pd.NA
        print("manual_runs_to_add: created missing 'run_accession' column in main table.")

    try:
        manual_df = pd.read_csv(csv_path, sep="\t", low_memory=False)
    except Exception as e:
        print(f"WARNING: manual_runs_to_add could not read file ({type(e).__name__}: {e})")
        return df

    missing_required = required_columns - set(manual_df.columns)
    if missing_required:
        print(f"WARNING: manual_runs_to_add skipped (missing columns in file: {sorted(missing_required)})")
        return df

    manual_df = manual_df[list(required_columns)].copy()
    manual_df["Sample"] = manual_df["Sample"].astype(str).str.strip()
    manual_df["run_accession"] = manual_df["run_accession"].astype(str).str.strip()
    manual_df = manual_df[(manual_df["Sample"] != "") & (manual_df["run_accession"] != "")]
    manual_map = manual_df.drop_duplicates(subset=["Sample"]).set_index("Sample")["run_accession"]

    sample_series = df["Sample"].astype(str).str.strip()
    missing_mask = df["run_accession"].isna() | (df["run_accession"].astype(str).str.strip() == "")
    fill_values = sample_series.map(manual_map)
    fill_mask = missing_mask & fill_values.notna()

    n_filled = int(fill_mask.sum())
    if n_filled > 0:
        df.loc[fill_mask, "run_accession"] = fill_values[fill_mask].values
        print(f"manual_runs_to_add: filled {n_filled} missing run_accession values from manual table.")
    else:
        print("manual_runs_to_add: no missing run_accession values were filled.")

    return df


def merge_run_accession_used(df: pd.DataFrame, tsv_path: str = USED_RUN_ACCESSION_TSV_PATH) -> pd.DataFrame:
    """Join run_accession_used from a sample_accession keyed table."""
    required_columns = {"sample_accession", "run_accession_used"}
    if "sample_accession" not in df.columns:
        print("WARNING: merge_run_accession_used skipped (main table missing 'sample_accession' column).")
        return df

    if "run_accession_used" not in df.columns:
        df["run_accession_used"] = pd.NA
        print("merge_run_accession_used: created missing 'run_accession_used' column in main table.")

    try:
        used_df = pd.read_csv(tsv_path, sep="\t", low_memory=False)
    except Exception as e:
        print(f"WARNING: merge_run_accession_used could not read file ({type(e).__name__}: {e})")
        return df

    missing_required = required_columns - set(used_df.columns)
    if missing_required:
        print(f"WARNING: merge_run_accession_used skipped (missing columns in file: {sorted(missing_required)})")
        return df

    used_df = used_df[list(required_columns)].copy()
    used_df["sample_accession"] = used_df["sample_accession"].astype(str).str.strip()
    used_df["run_accession_used"] = used_df["run_accession_used"].astype(str).str.strip()
    used_df = used_df[used_df["sample_accession"] != ""]

    used_map = (
        used_df.drop_duplicates(subset=["sample_accession"])
        .set_index("sample_accession")["run_accession_used"]
    )

    sample_accession_series = df["sample_accession"].astype(str).str.strip()
    joined_values = sample_accession_series.map(used_map)
    n_joined = int(joined_values.notna().sum())
    df["run_accession_used"] = joined_values

    print(f"merge_run_accession_used: joined run_accession_used for {n_joined} rows from sample_accession mapping.")
    return df


def main(
    metadata_file: str,
    output_file: str,
    output_file_slimmed: str,
    output_log: str,
    google_sheet_id: str = None,
    sheet_name: str = None,
    tsv_file_path: str = None,
    pre_collation_file: str = None,
    plots_output_dir: str = None,
):
    """
    Load collated metadata TSV file, report completeness, and parse metadata fields.
    Uses fixed category lists from module-level constants.
    
    Parameters:
    -----------
    google_sheet_id : str, optional
        Google Spreadsheet ID for study metadata (defaults to STUDY_METADATA_GOOGLE_SHEET_ID constant)
    sheet_name : str, optional
        Name of the sheet to read (defaults to STUDY_METADATA_SHEET_NAME constant)
    tsv_file_path : str, optional
        Path to TSV file with study characteristics (defaults to STUDY_CHARACTERISTICS_TSV_PATH constant)
    plots_output_dir : str, optional
        Path to directory for saving plots. If None, uses same directory as output_file
    """
    import sys
    from io import StringIO
    
    # Capture stdout to log file
    log_capture = StringIO()
    sys.stdout = log_capture  # Redirect print statements
    
    print(f"Loading metadata from:\n  {metadata_file}")
    pre_parsing_metadata = pd.read_csv(metadata_file, sep="\t", low_memory=False)
    print(f"Total rows loaded: {len(pre_parsing_metadata)}")
    pre_parsing_metadata = manual_runs_to_add(pre_parsing_metadata)

    # Use full dataset for parsing
    filtered_metadata = pre_parsing_metadata.copy()

    print("\n" + "=" * 60)
    print("Running host parsing...")
    print("=" * 60)
    filtered_metadata = parse_host(filtered_metadata, verbose=True)

    print("\n" + "=" * 60)
    print("Running country parsing...")
    print("=" * 60)
    filtered_metadata = parse_country(filtered_metadata, verbose=True)
    # Always run region categorisation after country parsing so regional categories
    # are available whenever countries have been parsed.
    print("\n" + "=" * 60)
    print("Running region categorisation...")
    print("=" * 60)
    filtered_metadata = categorise_region(filtered_metadata, verbose=True)

    print("\n" + "=" * 60)
    print("Running city parsing...")
    print("=" * 60)
    # Calculate processed directory path for saving city review file
    import os
    processed_dir = os.path.dirname(output_file).replace('/final/metadata', '/processed/metadata')
    filtered_metadata = parse_city(filtered_metadata, output_dir=processed_dir, verbose=True)

    print("\n" + "=" * 60)
    print("Running isolation source parsing...")
    print("=" * 60)
    filtered_metadata = parse_isolation_source(filtered_metadata, verbose=True)

    print("\n" + "=" * 60)
    print("Reconciling host and isolation_source...")
    print("=" * 60)
    filtered_metadata = reconcile_host_and_isolation_source(filtered_metadata, verbose=True)

    print("\n" + "=" * 60)
    print("Running collection_date parsing...")
    print("=" * 60)
    filtered_metadata = parse_collection_date(filtered_metadata, verbose=True)

    # Merge amr_study from study metadata
    print("\n" + "=" * 60)
    print("Merging amr_study from study metadata...")
    print("=" * 60)
    filtered_metadata = merge_amr_study_from_study_metadata(filtered_metadata, google_sheet_id, sheet_name, tsv_file_path)

    # Merge study_setting from study metadata
    print("\n" + "=" * 60)
    print("Merging study_setting from study metadata...")
    print("=" * 60)
    filtered_metadata = merge_study_setting_from_study_metadata(filtered_metadata, google_sheet_id, sheet_name, tsv_file_path)

    # Process pre-collation data if pre_collation_file is provided
    pre_collation_df = None
    if pre_collation_file:
        print("\n" + "=" * 60)
        print("Processing pre-collation data (silent mode)...")
        print("=" * 60)
        import os
        if os.path.exists(pre_collation_file):
            pre_collation_raw = pd.read_csv(pre_collation_file, sep="\t", low_memory=False)
            pre_collation_df = pre_collation_raw.copy()
            
            # Run same parsing pipeline with verbose=False
            pre_collation_df = parse_host(pre_collation_df, verbose=False)
            pre_collation_df = parse_country(pre_collation_df, verbose=False)
            pre_collation_df = categorise_region(pre_collation_df, verbose=False)
            pre_collation_df = parse_city(pre_collation_df, output_dir=None, verbose=False)
            pre_collation_df = parse_isolation_source(pre_collation_df, verbose=False)
            pre_collation_df = parse_collection_date(pre_collation_df, verbose=False)
            
            pre_collation_df = merge_amr_study_from_study_metadata(pre_collation_df, google_sheet_id, sheet_name, tsv_file_path)
            pre_collation_df = merge_study_setting_from_study_metadata(pre_collation_df, google_sheet_id, sheet_name, tsv_file_path)
            
            print("Pre-collation data processed successfully.")
        else:
            print(f"Warning: Pre-collation file not found: {pre_collation_file}")

    # Apply row filtering to remove samples where kpsc_final_list=False AND is_kpsc=True
    import os
    rows_before = len(filtered_metadata)
    filtered_metadata = filtered_metadata[
        ~(~filtered_metadata['kpsc_final_list'] & filtered_metadata['is_kpsc'])
    ]
    rows_after = len(filtered_metadata)
    rows_removed = rows_before - rows_after
    print(f"\nRow filtering: Removed {rows_removed} samples where kpsc_final_list=False AND is_kpsc=True")
    print(f"Rows before filtering: {rows_before}")
    print(f"Rows after filtering: {rows_after}")
    
    # Generate parsing quality report
    # Construct report output file path in processed directory (not final directory)
    output_basename = os.path.basename(output_file)
    report_basename = output_basename.replace('.tsv', '_issues_by_project.tsv')
    # Get processed directory by replacing /final/ with /processed/ in output_file path
    processed_dir = os.path.dirname(output_file).replace('/final/metadata', '/processed/metadata')
    report_output_file = os.path.join(processed_dir, report_basename)
    filtered_metadata = report_curation_summary(filtered_metadata, report_output_file, google_sheet_id, sheet_name, pre_collation_df=pre_collation_df, plots_output_dir=plots_output_dir)
    
    # Create final output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Apply kpsc_final flag from the final sample list
    print("\n" + "=" * 60)
    print("Applying kpsc_final_list from final sample list...")
    print("=" * 60)
    filtered_metadata = apply_kpsc_final_list_flag(filtered_metadata)

    print("\n" + "=" * 60)
    print("Sample flags: is_mgh78578, is_complete_norway_genome, have_transcriptome")
    print("=" * 60)
    sample_series = filtered_metadata["Sample"].astype(str)
    filtered_metadata["is_mgh78578"] = sample_series == MGH78578_SAMPLE_ID
    filtered_metadata["have_transcriptome"] = sample_series.isin(TRANSCRIPTOME_SAMPLE_IDS)

    if not os.path.isfile(COMPLETE_NORWAY_GENOMES_CSV_PATH):
        print(f"  WARNING: complete_norway_genomes file missing: {COMPLETE_NORWAY_GENOMES_CSV_PATH}")
        print("  is_complete_norway_genome set False for all rows.")
        norway_biosamples = set()
    else:
        try:
            norway_biosamples = _load_complete_norway_biosample_ids(COMPLETE_NORWAY_GENOMES_CSV_PATH)
        except Exception as e:
            print(f"  WARNING: could not read complete_norway_genomes.csv ({type(e).__name__}: {e})")
            norway_biosamples = set()
        if not norway_biosamples and os.path.isfile(COMPLETE_NORWAY_GENOMES_CSV_PATH):
            print("  WARNING: No BioSample accessions loaded (check column name or file contents).")

    meta_samples = set(sample_series.unique())
    meta_samples.discard("nan")

    n_csv_unique = len(norway_biosamples)
    matched_accessions = norway_biosamples & meta_samples
    n_matched_accessions = len(matched_accessions)
    n_unmatched_csv = len(norway_biosamples - meta_samples)

    filtered_metadata["is_complete_norway_genome"] = sample_series.isin(norway_biosamples)
    n_rows_flagged = int(filtered_metadata["is_complete_norway_genome"].sum())

    print(f"  complete_norway_genomes.csv: {n_csv_unique} unique BioSample accessions")
    print(f"  Rows in metadata with is_complete_norway_genome=True: {n_rows_flagged}")
    print(f"  BioSample accessions from CSV also present as Sample in metadata: {n_matched_accessions}")
    print(f"  BioSample accessions from CSV NOT found as Sample in metadata: {n_unmatched_csv}")

    print("\n" + "=" * 60)
    print("Merging run_accession_used from curated used-accession table...")
    print("=" * 60)
    filtered_metadata = merge_run_accession_used(filtered_metadata)

    # Write full curated metadata to final directory
    filtered_metadata.to_csv(output_file, sep="\t", index=False)
    print(f"\nFull curated metadata written to: {output_file}")
    
    # Create slimmed version with selected columns
    slimmed_columns = [
        # Group 1 - Kleborate/QC columns
        'Sample', 'is_kpsc', 'kpsc_final_list', 'is_kpsc_final', 'is_refseq', 'is_nctc',
        'is_mgh78578', 'is_complete_norway_genome', 'have_transcriptome',
        'species', 'species_match', 
        'Clonal group', 'LINcode', 'Phylogroup', 'Sublineage', 'scgST',
        'contig_count', 'N50', 'largest_contig', 'total_size', 'ambiguous_bases', 'QC_warnings', 
        'ST', 
        'wzi', 'K_locus', 'K_type', 'K_locus_confidence', 'K_locus_problems', 'K_locus_identity', 'K_Missing_expected_genes',
        'O_locus', 'O_type', 'O_locus_confidence', 'O_locus_problems', 'O_locus_identity', 'O_Missing_expected_genes',
        # Group 3 - ENA metadata columns
        'sample_accession', 'secondary_sample_accesion', 'accession', 'study_accession', 'run_accession', 'run_accession_used', 'Biosample'
        'country', 'country_parsed', 'region', 
        'isolation_source', 'isolation_source_parsed', 'isolation_source_category',
        'host', 'host_parsed', 'host_category',
        'collection_date', 'collection_date_parsed', 'year_parsed',
        'dev_stage', 'scientific_name', 'center_name', 'amr_study', 'study_setting'
    ]
    
    # Filter to only columns that exist in the dataframe
    existing_columns = [col for col in slimmed_columns if col in filtered_metadata.columns]
    missing_columns = [col for col in slimmed_columns if col not in filtered_metadata.columns]
    
    if missing_columns:
        print(f"\nWarning: {len(missing_columns)} columns not found in data: {missing_columns[:10]}{'...' if len(missing_columns) > 10 else ''}")
    
    print(f"Slimmed version will contain {len(existing_columns)} columns (out of {len(slimmed_columns)} requested)")
    
    filtered_metadata[existing_columns].to_csv(output_file_slimmed, sep="\t", index=False)
    print(f"Slimmed metadata written to: {output_file_slimmed}")    
    # Write log to processed directory
    with open(output_log, 'w') as f:
        f.write(log_capture.getvalue())
    print(f"\nLog written to: {output_log}")
    
    return


if __name__ == '__main__':
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description='Process ENA metadata: report completeness and optionally parse metadata fields'
    )
    parser.add_argument('--metadata-dir', type=str,
        default="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/processed/metadata",
        help='Directory containing metadata files')
    parser.add_argument('--metadata-file', type=str,
        default="qc_final_with_metadata.tsv",
        help='Input metadata filename (default: collated_metadata.tsv)')
    parser.add_argument('--output-file', type=str,
        default="metadata_final_curated_all_samples_and_columns.tsv",
        help='Output metadata filename (default: parsed_metadata.tsv)')
    parser.add_argument('--output-file-slimmed', type=str,
        default="metadata_final_curated_slimmed.tsv",
        help='Output slimmed metadata filename with selected columns (default: metadata_final_curated_slimmed.tsv)')
    parser.add_argument('--output-log', type=str,
        default="parsed_metadata.log",
        help='Output log filename (default: parsed_metadata.log)')
    parser.add_argument('--google-sheet-id', type=str,
        default=STUDY_METADATA_GOOGLE_SHEET_ID,
        help=f'Google Spreadsheet ID for study metadata (default: {STUDY_METADATA_GOOGLE_SHEET_ID})')
    parser.add_argument('--sheet-name', type=str,
        default=STUDY_METADATA_SHEET_NAME,
        help=f'Name of the sheet to read (default: {STUDY_METADATA_SHEET_NAME})')
    parser.add_argument('--study-characteristics-tsv', type=str,
        default=STUDY_CHARACTERISTICS_TSV_PATH,
        help=f'TSV file with study characteristics (default: {STUDY_CHARACTERISTICS_TSV_PATH})')
    parser.add_argument('--pre-collation-file', type=str,
        default="combined_metadata_before_collation.tsv",
        help='Pre-collation metadata filename (default: combined_metadata_before_collation.tsv)')
    parser.add_argument('--plots-output-dir', type=str,
        default="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/visualisations/metadata_curation/",
        help='Directory for saving plots (default: Aaron Weimann\'s files - project_k/data/visualisations/metadata_curation/)')

    args = parser.parse_args()

    # Build full paths
    # Main curated files go to final/metadata directory
    final_metadata_dir = args.metadata_dir.replace('/processed/metadata', '/final/metadata')
    metadata_file_path = os.path.join(args.metadata_dir, args.metadata_file)
    output_file_path = os.path.join(final_metadata_dir, args.output_file)
    output_file_slimmed_path = os.path.join(final_metadata_dir, args.output_file_slimmed)
    # Report and log stay in processed/metadata directory
    output_log_path = os.path.join(args.metadata_dir, args.output_log)
    pre_collation_file_path = os.path.join(args.metadata_dir, args.pre_collation_file)

    main(
        metadata_file=metadata_file_path,
        output_file=output_file_path,
        output_file_slimmed=output_file_slimmed_path,
        output_log=output_log_path,
        google_sheet_id=args.google_sheet_id,
        sheet_name=args.sheet_name,
        tsv_file_path=args.study_characteristics_tsv,
        pre_collation_file=pre_collation_file_path,
        plots_output_dir=args.plots_output_dir,
    )

# uv run python Klebsiella/pp/metadata_curation.py 




########################## REPORTING FUNCTIONS, MOSTLY HISTORICAL AND NO USED IN SCRIPT ##########################

def report_ena_data_completeness(ena_data_subset, filter_n=100, display_n=5, report_columns=False, verbose=True):
    """
    Summarize completeness of key ENA metadata columns, optionally with per-column detail.
    """

    #Basic information about the ENA data
    columns_to_check = [
          "host",     
          "country",
          "collection_date",
          "isolation_source",
          "dev_stage"]
    
    # Number of samples in the ENA data file (pre-filter)
    n_samples_pre = len(ena_data_subset)
    n_study_accessions_pre = len(ena_data_subset['study_accession'].unique())
    
    if verbose:
        print(f"The total number of samples in the ENA data file is {n_samples_pre}")
        print(f"The total number of study accessions in the ENA data file is {n_study_accessions_pre}")
    
    # Apply filtering if filter_n is not None
    if filter_n is not None:
        # Count unique samples per study accession
        study_sample_counts = ena_data_subset.groupby('study_accession')['sample_accession'].nunique()
        # Keep only studies with > filter_n unique samples
        studies_to_keep = study_sample_counts[study_sample_counts > filter_n].index
        ena_data_subset = ena_data_subset[ena_data_subset['study_accession'].isin(studies_to_keep)].copy()
        
        n_samples_post = len(ena_data_subset)
        n_study_accessions_post = len(ena_data_subset['study_accession'].unique())
        
        if verbose:
            print(f"\nAfter filtering (keeping studies with > {filter_n} unique samples):")
            print(f"  Number of samples: {n_samples_post}")
            print(f"  Number of study accessions: {n_study_accessions_post}")
    else:
        if verbose:
            print("\nNo filtering applied (filter_n=None)")
    
    # Print first 3 study accessions
    if verbose:
        print(f"\nThe first 3 study accessions in the ENA data file are: {ena_data_subset['study_accession'].unique()[:3]}")
    
    # STEP 2.5: Create a view of just the columns we're interested in
    df_to_check = ena_data_subset[columns_to_check]
    
    # STEP 2.6: Build completeness summary dataframe
    completeness_data = []
    for column in columns_to_check:
        if column in df_to_check.columns:
            n_filled = df_to_check[column].notna().sum()
            n_missing = df_to_check[column].isna().sum()
            unique_vals = df_to_check[column].dropna().unique()
            completeness_data.append({
                'column': column,
                'n_filled': n_filled,
                'n_missing': n_missing,
                'unique_values': len(unique_vals)
            })
        else:
            completeness_data.append({
                'column': column,
                'n_filled': 0,
                'n_missing': len(df_to_check),
                'unique_values': 0
            })

            # If report columns is True, then call report_ena_column for this column
            if report_columns and verbose:
                report_ena_column(ena_data_subset, column, display_n=display_n, verbose=verbose)
    
    completeness_summary = pd.DataFrame(completeness_data)
    
    if verbose:
        print("\nColumns completeness summary:")
        display(completeness_summary)
    
        # Report on each column with detailed information
        print("\nDetailed column reports:")
        if report_columns:
            for column in columns_to_check:
                report_ena_column(ena_data_subset, column, display_n=display_n, verbose=verbose)
        else:
            print("Columns not reported")

    return df_to_check, completeness_summary