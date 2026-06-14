"""
Metadata collation pipeline:
- Load collated ENA metadata (destination data).
- Add metadata_reviewed flag based on study-level metadata file.
- Filter out large unreviewed studies (configurable threshold, default 131 samples).
- Discover per-project ready_to_merge slices.
- Apply row-wise substitutions by sample_accession with strict error reporting.
- Compare completeness of key columns before vs after substitutions.
- Write updated data and diagnostics to processed outputs.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype
from pandas.io.common import dedup_names
import matplotlib.pyplot as plt
import numpy as np

from bac_metadata.pp.metadata_curation import report_ena_column


METADATA_DIR = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/metadata"
ENA_METADATA_FILE1 = f"{METADATA_DIR}/ena_metadata_klebsiella_with_header_filtered.tsv"
ENA_METADATA_FILE2 = f"{METADATA_DIR}/ena_metadata_klebsiella_with_header_filtered_r02_format.20240801.tsv"
ENA_METADATA_FILE3 = f"{METADATA_DIR}/bakrep_klebsiella_genus_extra_ena_metadata.tsv"
ENA_PROJECT_DIR = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/metadata/study_level_metadata/ENA_projects"
OUTPUT_DIR = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/metadata"
# Study metadata can be either a CSV file path or a Google Sheet URL/ID
STUDY_METADATA_GOOGLE_SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"
STUDY_METADATA_SHEET_NAME = "study_level"
STUDY_METADATA_FILE = None  # Set to None to use Google Sheet, or provide CSV file path
QC_EXCEL_FILE = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/klebsiella_qc_NCTC.xlsx"
KLEBNET_METADATA_FILE = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/metadata/study_level_metadata/KlebNET-GSP_Metadata_Repository_Database.csv"

KEY_COLUMNS = ["collection_date", "country", "isolation_source", "host"]
DEBUG_SAMPLE_ACCESSIONS = ["SAMD00112425"]
DEBUG_TRACK_COLUMNS = [
    "sample_accession",
    "run_accession",
    "study_accession",
    "secondary_sample_accession",
    "accession",
]

REQUIRED_COLUMNS = [
    "sample_accession", "run_accession", "submission_accession", "assembly_software",
    "library_selection", "serotype", "environment_feature", "last_updated",
    "submitted_galaxy", "germline", "culture_collection", "submission_tool",
    "sra_bytes", "collected_by", "submitted_ftp", "isolate", "fastq_bytes",
    "instrument_platform", "variety", "temperature", "sra_aspera", "ecotype",
    "submitted_aspera", "sampling_campaign", "tissue_lib", "environmental_sample",
    "sex", "submitted_md5", "checklist", "fastq_galaxy", "specimen_voucher",
    "submitted_bytes", "taxonomic_identity_marker", "country", "sample_description",
    "experiment_title", "sra_galaxy", "fastq_md5", "secondary_study_accession",
    "read_count", "study_title", "bio_material", "host_body_site",
    "assembly_quality", "sample_capture_status", "sample_title", "host_genotype",
    "host_phenotype", "cultivar", "instrument_model", "target_gene",
    "nominal_sdev", "environment_material", "host_tax_id", "sample_material",
    "sra_md5", "cell_type", "fastq_ftp", "broker_name", "sub_strain",
    "base_count", "library_strategy", "serovar", "investigation_type",
    "location", "library_source", "sra_ftp", "library_layout",
    "experimental_factor", "environment_biome", "dev_stage", "binning_software",
    "sample_collection", "nominal_length", "completeness_score", "lon",
    "fastq_aspera", "host_sex", "sample_alias", "mating_type", "sub_species",
    "contamination_score", "run_alias", "depth", "host_growth_conditions",
    "collection_date", "experiment_alias", "host_gravidity", "center_name",
    "identified_by", "cell_line", "sampling_site", "host", "library_name",
    "first_created", "lat", "strain", "experiment_accession", "scientific_name",
    "host_status", "tax_id", "study_accession", "submitted_format",
    "submitted_host_sex", "altitude", "accession", "secondary_sample_accession",
    "sampling_platform", "taxonomic_classification", "protocol_label",
    "elevation", "salinity", "sequencing_method", "first_public", "study_alias",
    "ph", "tissue_type", "isolation_source"
]


class TeeOutput:
    """Class that writes to both file and stdout."""
    def __init__(self, file_path: str):
        self.file = open(file_path, 'w', encoding='utf-8')
        self.stdout = sys.stdout
    
    def write(self, text: str) -> None:
        self.stdout.write(text)
        self.file.write(text)
        self.file.flush()  # Ensure immediate write
    
    def flush(self) -> None:
        self.stdout.flush()
        self.file.flush()
    
    def close(self) -> None:
        if self.file:
            self.file.close()


def _debug_run_accession_status(
    data: pd.DataFrame,
    stage: str,
    label: str = "",
) -> None:
    """Print run_accession completeness summary for the current dataframe."""
    if 'run_accession' not in data.columns:
        print(f"[DEBUG][{stage}] run_accession column missing {label}".rstrip())
        return

    present_mask = data['run_accession'].notna() & (data['run_accession'].astype(str).str.strip() != "")
    present = int(present_mask.sum())
    total = len(data)
    missing = total - present
    suffix = f" ({label})" if label else ""
    print(
        f"[DEBUG][{stage}] run_accession completeness{suffix}: "
        f"present={present}, missing_or_blank={missing}, total={total}"
    )


def _strip_cell_value(x: object) -> object:
    """Strip leading/trailing whitespace and UTF-8 BOM from string cells; leave other types unchanged."""
    if isinstance(x, str):
        return x.replace("\ufeff", "").strip()
    return x


def _strip_whitespace_object_string_columns(data: pd.DataFrame) -> None:
    """In-place: trim BOM/whitespace in every object or pandas string column."""
    for col in data.columns:
        dtype = data[col].dtype
        if is_object_dtype(dtype) or is_string_dtype(dtype):
            data[col] = data[col].map(_strip_cell_value)


def _read_tab_separated_table(path: str) -> pd.DataFrame:
    """Read ENA-style TSV; skipinitialspace absorbs stray spaces after tab delimiters."""
    return pd.read_csv(path, sep="\t", low_memory=False, skipinitialspace=True)


def _debug_specific_samples(
    data: pd.DataFrame,
    stage: str,
    sample_accessions: Sequence[str] = DEBUG_SAMPLE_ACCESSIONS,
    label: str = "",
) -> None:
    """Print row-level debug details for selected sample_accession values."""
    if 'sample_accession' not in data.columns:
        print(f"[DEBUG][{stage}] sample_accession column missing {label}".rstrip())
        return

    suffix = f" ({label})" if label else ""
    for sample_acc in sample_accessions:
        rows = data[data['sample_accession'] == sample_acc]
        if rows.empty:
            print(f"[DEBUG][{stage}] {sample_acc}{suffix}: NOT FOUND")
            continue

        print(f"[DEBUG][{stage}] {sample_acc}{suffix}: found {len(rows)} row(s)")
        cols_to_show = [c for c in DEBUG_TRACK_COLUMNS if c in rows.columns]
        if not cols_to_show:
            print(f"[DEBUG][{stage}]   no tracked columns available")
            continue

        # Convert NaN to explicit marker to make value loss obvious in logs.
        printable = rows[cols_to_show].fillna("<NA>")
        print(printable.to_string(index=False))


def _normalize_loaded_metadata_dataframe(
    data: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    """
    Normalize loaded ENA metadata:
    - strip whitespace from column names (fixes headers like ' run_accession')
    - rename known ENA header typos so downstream code sees canonical names
    - strip BOM / leading / trailing whitespace from all object and string-dtype cells
      so joins and ``isin`` checks match the main table
    """
    normalized = data.copy()

    original_columns = normalized.columns.tolist()
    stripped_names = [str(c).strip() for c in normalized.columns]
    stripped_to_originals: Dict[str, List[str]] = {}
    for original, stripped in zip(original_columns, stripped_names):
        stripped_to_originals.setdefault(stripped, []).append(str(original))

    collisions = {
        stripped: originals
        for stripped, originals in stripped_to_originals.items()
        if len(originals) > 1
    }
    if collisions:
        print(f"[DEBUG][normalize] {label}: header collisions after strip ({len(collisions)}):")
        for stripped, originals in sorted(collisions.items()):
            print(f"  - '{stripped}' <= {originals}")

    # Stripping can make two distinct headers identical; duplicate labels break per-column assigns.
    normalized.columns = dedup_names(stripped_names, is_potential_multiindex=False)
    changed_cols = sum(1 for old, new in zip(original_columns, normalized.columns) if old != new)
    if changed_cols:
        print(f"[DEBUG][normalize] {label}: stripped whitespace in {changed_cols} column name(s)")

    # ENA / export typo sometimes seen in TSVs (missing "s" in accession)
    if (
        "secondary_sample_accesion" in normalized.columns
        and "secondary_sample_accession" not in normalized.columns
    ):
        normalized = normalized.rename(columns={"secondary_sample_accesion": "secondary_sample_accession"})
        print(f"[DEBUG][normalize] {label}: renamed secondary_sample_accesion -> secondary_sample_accession")

    _strip_whitespace_object_string_columns(normalized)

    # Reconcile deduplicated columns like "col.1", "col.2", etc.:
    # - fill missing/blank base values from duplicate column non-blank values
    # - then drop duplicate column
    suffix_duplicate_cols = [
        c for c in normalized.columns
        if isinstance(c, str) and c.rsplit(".", 1)[-1].isdigit() and "." in c
    ]
    for dup_col in suffix_duplicate_cols:
        base_col = dup_col.rsplit(".", 1)[0]
        if base_col not in normalized.columns:
            continue

        base_series = normalized[base_col]
        dup_series = normalized[dup_col]

        base_blank = base_series.isna()
        if is_object_dtype(base_series.dtype) or is_string_dtype(base_series.dtype):
            base_blank = base_blank | (base_series.astype(str).str.strip() == "")

        dup_has_data = dup_series.notna()
        if is_object_dtype(dup_series.dtype) or is_string_dtype(dup_series.dtype):
            dup_has_data = dup_has_data & (dup_series.astype(str).str.strip() != "")

        fill_mask = base_blank & dup_has_data
        filled_count = int(fill_mask.sum())

        if filled_count > 0:
            normalized.loc[fill_mask, base_col] = dup_series[fill_mask]

        print(
            f"[DEBUG][normalize] {label}: reconciled duplicate column '{dup_col}' -> '{base_col}' "
            f"(filled {filled_count} row(s)); dropping '{dup_col}'"
        )
        normalized = normalized.drop(columns=[dup_col])

    return normalized


def _debug_loaded_table(
    data: pd.DataFrame,
    source_label: str,
    required_columns: Sequence[str] | None = None,
) -> None:
    """Detailed diagnostics immediately after a table is loaded from disk/API."""
    print(f"[DEBUG][load] {source_label}: rows={len(data)}, cols={len(data.columns)}")
    preview_cols = data.columns[:12].tolist()
    print(f"[DEBUG][load] {source_label}: first_columns={preview_cols}")

    if required_columns is not None:
        missing = [c for c in required_columns if c not in data.columns]
        print(
            f"[DEBUG][load] {source_label}: required_columns_present="
            f"{len(required_columns) - len(missing)}/{len(required_columns)}"
        )
        if missing:
            print(f"[DEBUG][load] {source_label}: missing_required={missing[:20]}")

    whitespace_cols = [c for c in data.columns if str(c) != str(c).strip()]
    if whitespace_cols:
        print(
            f"[DEBUG][load] {source_label}: columns_with_edge_whitespace="
            f"{len(whitespace_cols)} (examples={whitespace_cols[:10]})"
        )

    for id_col in ("sample_accession", "run_accession", "study_accession", "study_accessions", "Sample accession", "FILE"):
        if id_col in data.columns:
            non_blank = data[id_col].notna() & (data[id_col].astype(str).str.strip() != "")
            print(
                f"[DEBUG][load] {source_label}: {id_col} "
                f"non_blank={int(non_blank.sum())}/{len(data)}"
            )


def _report_ena_bakrep_overlap(
    df_ena: pd.DataFrame,
    df_bakrep: pd.DataFrame,
    sample_col: str = "sample_accession",
) -> None:
    """
    Report overlap between ENA and bakrep for shared samples/columns.

    For each shared column:
    - number of shared samples with ENA non-missing
    - number with bakrep non-missing
    - number where both are non-missing
    - among both non-missing, number of exact conflicts
    """
    print("\n" + "=" * 80)
    print("ENA vs BAKREP OVERLAP REPORT")
    print("=" * 80)

    if sample_col not in df_ena.columns or sample_col not in df_bakrep.columns:
        print(f"Cannot report overlap: '{sample_col}' missing in one of the inputs.")
        print("=" * 80 + "\n")
        return

    ena_idx = df_ena.drop_duplicates(subset=sample_col, keep="first").set_index(sample_col, drop=False)
    bakrep_idx = df_bakrep.drop_duplicates(subset=sample_col, keep="first").set_index(sample_col, drop=False)

    shared_samples = ena_idx.index.intersection(bakrep_idx.index)
    print(f"Shared samples between ENA and bakrep: {len(shared_samples)}")

    shared_columns = sorted(set(df_ena.columns).intersection(set(df_bakrep.columns)))
    # Exclude helper/source columns and identifier from conflict summaries.
    shared_columns = [c for c in shared_columns if c not in {"_source_file"}]
    print(f"Shared columns between ENA and bakrep: {len(shared_columns)}")

    if len(shared_samples) == 0:
        print("No overlapping samples to compare.")
        print("=" * 80 + "\n")
        return

    ena_shared = ena_idx.loc[shared_samples]
    bakrep_shared = bakrep_idx.loc[shared_samples]

    rows: List[Dict[str, object]] = []
    for col in shared_columns:
        ena_has = ena_shared[col].notna() & (ena_shared[col].astype(str).str.strip() != "")
        bak_has = bakrep_shared[col].notna() & (bakrep_shared[col].astype(str).str.strip() != "")
        both_has = ena_has & bak_has

        conflicts = 0
        if both_has.any():
            ena_vals = ena_shared.loc[both_has, col].astype(str).str.strip()
            bak_vals = bakrep_shared.loc[both_has, col].astype(str).str.strip()
            conflicts = int((ena_vals != bak_vals).sum())

        rows.append(
            {
                "column": col,
                "ena_non_missing": int(ena_has.sum()),
                "bakrep_non_missing": int(bak_has.sum()),
                "both_non_missing": int(both_has.sum()),
                "conflicts_when_both_present": conflicts,
            }
        )

    overlap_df = pd.DataFrame(rows)
    overlap_df = overlap_df.sort_values(
        by=["both_non_missing", "conflicts_when_both_present"],
        ascending=[False, False],
    )
    comparable_cols = int((overlap_df["both_non_missing"] > 0).sum())
    conflicting_cols = int((overlap_df["conflicts_when_both_present"] > 0).sum())
    fillable_cols = int(((overlap_df["ena_non_missing"] < len(shared_samples)) & (overlap_df["bakrep_non_missing"] > 0)).sum())
    print(f"Columns comparable on shared samples (both non-missing at least once): {comparable_cols}")
    print(f"Columns with at least one ENA-vs-bakrep conflict: {conflicting_cols}")
    print(f"Columns where bakrep can potentially fill ENA gaps: {fillable_cols}")

    if conflicting_cols > 0:
        print("\nTop conflicting columns (up to 10):")
        print(
            overlap_df[overlap_df["conflicts_when_both_present"] > 0]
            .head(10)
            .to_string(index=False)
        )
    print("=" * 80 + "\n")


@dataclass
class ReadyToMergeFilename:
    """Record of a ready_to_merge filename found in a project folder."""
    project_folder: str
    file_path: str


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
    # Resolve the OAuth client secret OFF OneDrive (OneDrive dehydrates/corrupts files):
    # env BAC_GOOGLE_CLIENT_SECRET -> ~/.config/bac_metadata/client_secret.json -> legacy OneDrive path.
    # Shares the config dir + token with bac_agentic_metadata.engine.gsheet so one login serves both.
    CONFIG_DIR = Path(os.environ.get("BAC_GOOGLE_CONFIG_DIR", Path.home() / ".config" / "bac_metadata"))
    _LEGACY_ONEDRIVE_SECRET = Path(
        "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/"
        "Aaron Weimann's files - project_k/data/raw/google/"
        "client_secret_766063885615-5r4chm0o2635kqjc2fe18coak2a70ugc.apps.googleusercontent.com.json"
    )
    _env_secret = os.environ.get("BAC_GOOGLE_CLIENT_SECRET")
    if _env_secret:
        CREDENTIALS_FILE = Path(_env_secret)
    elif (CONFIG_DIR / "client_secret.json").exists():
        CREDENTIALS_FILE = CONFIG_DIR / "client_secret.json"
    else:
        CREDENTIALS_FILE = _LEGACY_ONEDRIVE_SECRET
    TOKEN_FILE = Path(os.environ.get("BAC_GOOGLE_TOKEN", CONFIG_DIR / "token.json"))
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    
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


def load_study_accessions(
    study_metadata_file: str | None = STUDY_METADATA_FILE,
    google_sheet_id: str | None = STUDY_METADATA_GOOGLE_SHEET_ID,
    sheet_name: str = STUDY_METADATA_SHEET_NAME,
) -> Set[str]:
    """
    Load and parse study accessions from the study-level metadata file.
    
    Can read from either a CSV file or a Google Sheet.
    
    Parameters:
    -----------
    study_metadata_file : str | None
        Path to the study-level metadata CSV file (if None, uses Google Sheet)
    google_sheet_id : str | None
        Google Spreadsheet ID (used if study_metadata_file is None)
    sheet_name : str
        Name of the sheet to read from Google Sheets (default: 'study_level')
    
    Returns:
    --------
    set[str]
        Set of unique study accessions (PRJ... format)
    """
    # Determine source: CSV file or Google Sheet
    if study_metadata_file is not None:
        print(f"Loading study accessions from CSV file: {study_metadata_file}")
        df = pd.read_csv(study_metadata_file, low_memory=False, skipinitialspace=True)
        df = _normalize_loaded_metadata_dataframe(df, "study_accessions_csv")
        _debug_loaded_table(df, "study_accessions_csv", required_columns=["study_accessions"])
    else:
        if google_sheet_id is None:
            raise ValueError("Either study_metadata_file or google_sheet_id must be provided")
        print(f"Loading study accessions from Google Sheet: {google_sheet_id} (sheet: {sheet_name})")
        df = _read_google_sheet(google_sheet_id, sheet_name)
        df = _normalize_loaded_metadata_dataframe(df, f"study_accessions_google_sheet:{sheet_name}")
        _debug_loaded_table(df, f"study_accessions_google_sheet:{sheet_name}", required_columns=["study_accessions"])
    
    if 'study_accessions' not in df.columns:
        source = study_metadata_file if study_metadata_file else f"Google Sheet {google_sheet_id}"
        raise ValueError(f"Column 'study_accessions' not found in {source}")
    
    study_accessions_set = set()
    
    # Parse study_accessions column, handling comma-separated values
    for idx, value in df['study_accessions'].items():
        if pd.notna(value):
            # Split by comma and strip whitespace
            accessions = [acc.strip() for acc in str(value).split(',')]
            for acc in accessions:
                if acc and acc.startswith('PRJ'):  # Filter for PRJ... format
                    study_accessions_set.add(acc)
    
    print(f"Found {len(study_accessions_set)} unique study accessions")
    return study_accessions_set


def report_reviewed_studies_statistics(
    data: pd.DataFrame,
    reviewed_studies: Set[str],
) -> None:
    """
    Report statistics on reviewed studies.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Dataframe with study_accession column
    reviewed_studies : Set[str]
        Set of reviewed study accessions
    """
    if 'study_accession' not in data.columns:
        raise ValueError("Column 'study_accession' not found in data")
    
    # Calculate which studies are reviewed
    reviewed_mask = data['study_accession'].isin(reviewed_studies)
    reviewed_data = data[reviewed_mask]
    
    # Count unique studies and samples in reviewed studies
    reviewed_study_count = reviewed_data['study_accession'].nunique()
    reviewed_sample_count = len(reviewed_data)
    
    print("\n" + "="*80)
    print("REVIEWED STUDIES STATISTICS")
    print("="*80)
    print(f"Number of reviewed studies: {reviewed_study_count}")
    print(f"Total samples in reviewed studies: {reviewed_sample_count}")
    print("="*80 + "\n")


def report_filtered_samples_statistics(filtered_data: pd.DataFrame, filter_study_size: int = 131) -> None:
    """
    Report detailed statistics on filtered samples by study.
    
    Parameters:
    -----------
    filtered_data : pd.DataFrame
        Filtered dataframe containing samples with study_accession column
    filter_study_size : int
        Threshold for categorizing studies by size. Default: 131
    """
    if 'study_accession' not in filtered_data.columns:
        raise ValueError("Column 'study_accession' not found in filtered_data")
    
    if 'metadata_reviewed' not in filtered_data.columns:
        raise ValueError("Column 'metadata_reviewed' not found in filtered_data")
    
    # Calculate samples per study
    study_sample_counts = filtered_data.groupby('study_accession')['sample_accession'].nunique()
    
    total_studies = len(study_sample_counts)
    total_samples = len(filtered_data)
    
    # Count reviewed vs unreviewed studies
    reviewed_studies = filtered_data[filtered_data['metadata_reviewed']]['study_accession'].nunique()
    unreviewed_studies = filtered_data[~filtered_data['metadata_reviewed']]['study_accession'].nunique()
    
    # Calculate statistics
    sample_counts = study_sample_counts.values
    min_samples = sample_counts.min() if len(sample_counts) > 0 else 0
    max_samples = sample_counts.max() if len(sample_counts) > 0 else 0
    
    # Count samples in reviewed vs unreviewed studies
    reviewed_samples = len(filtered_data[filtered_data['metadata_reviewed']])
    unreviewed_samples = len(filtered_data[~filtered_data['metadata_reviewed']])
    
    print("\n" + "="*80)
    print("FILTERED SAMPLES STATISTICS")
    print("="*80)
    print(f"Total studies retained: {total_studies}")
    print(f"  Reviewed studies (metadata_reviewed = True): {reviewed_studies}")
    print(f"  Unreviewed studies (metadata_reviewed = False): {unreviewed_studies}")
    print(f"\nTotal samples retained: {total_samples}")
    print(f"  Total samples in reviewed studies: {reviewed_samples}")
    print(f"  Total samples in unreviewed studies: {unreviewed_samples}")
    print("\nSamples per study:")
    print(f"  Minimum: {min_samples}")
    print(f"  Maximum: {max_samples}")
    
    print("="*80 + "\n")


def load_removed_studies(
    google_sheet_id: str | None = STUDY_METADATA_GOOGLE_SHEET_ID,
    sheet_name: str = "removed_studies",
) -> Set[str]:
    """
    Load list of study accessions to remove from the 'removed_studies' sheet in Google Sheets.
    
    Parameters:
    -----------
    google_sheet_id : str | None
        Google Spreadsheet ID (default: STUDY_METADATA_GOOGLE_SHEET_ID)
    sheet_name : str
        Name of the sheet to read (default: 'removed_studies')
    
    Returns:
    --------
    set[str]
        Set of study accessions to remove
    """
    if google_sheet_id is None:
        print("WARNING: No Google Sheet ID provided, returning empty set for removed studies")
        return set()
    
    try:
        print(f"Loading removed studies from Google Sheet: {google_sheet_id} (sheet: {sheet_name})")
        df = _read_google_sheet(google_sheet_id, sheet_name)
        _debug_loaded_table(df, f"removed_studies_google_sheet:{sheet_name}")
        
        # Get first column (should be 'study_accession')
        if len(df.columns) == 0:
            print("WARNING: 'removed_studies' sheet is empty, no studies will be removed")
            return set()
        
        first_col = df.columns[0]
        removed_studies = set(df[first_col].dropna().astype(str).unique())
        
        # Filter to only PRJ... format
        removed_studies = {s for s in removed_studies if s.startswith('PRJ')}
        
        print(f"Found {len(removed_studies)} study accessions to remove")
        return removed_studies
        
    except Exception as e:
        print(f"WARNING: Could not load removed_studies sheet: {type(e).__name__}: {e}")
        print("  Continuing without removing studies from removed_studies sheet")
        return set()


def load_collated_metadata(
    metadata_file1: str = ENA_METADATA_FILE1,
    metadata_file2: str = ENA_METADATA_FILE2,
    metadata_file3: str = ENA_METADATA_FILE3,
    study_metadata_file: str = STUDY_METADATA_FILE,
    filter_study_size: int = 131,  # Deprecated: kept for backward compatibility, not used
    google_sheet_id: str | None = STUDY_METADATA_GOOGLE_SHEET_ID,
    qc_excel_path: str = QC_EXCEL_FILE,
) -> pd.DataFrame:
    """
    Load and concatenate the three collated metadata TSVs plus Refseq samples from QC Excel.
    Detects and removes duplicates by sample_accession, keeping first occurrence.
    Adds metadata_reviewed flag and filters out studies listed in 'removed_studies' sheet.
    
    Parameters:
    -----------
    metadata_file1 : str
        Path to first ENA metadata TSV file
    metadata_file2 : str
        Path to second ENA metadata TSV file
    metadata_file3 : str
        Path to third ENA metadata TSV file (bakrep_extra_ena_metadata.tsv)
    study_metadata_file : str | None
        Path to study-level metadata CSV file (if None, uses Google Sheet)
    filter_study_size : int
        Deprecated: kept for backward compatibility, not used anymore
    google_sheet_id : str | None
        Google Spreadsheet ID for loading removed_studies sheet (default: STUDY_METADATA_GOOGLE_SHEET_ID)
    qc_excel_path : str
        Path to QC Excel file containing Refseq sheet (default: QC_EXCEL_FILE)
    """
    print(f"Loading collated metadata from:\n  {metadata_file1}\n  {metadata_file2}\n  {metadata_file3}")
    
    # Load all three dataframes
    df1 = _read_tab_separated_table(metadata_file1)
    df2 = _read_tab_separated_table(metadata_file2)
    df3 = _read_tab_separated_table(metadata_file3)
    _debug_loaded_table(df1, f"ENA file1 raw:{os.path.basename(metadata_file1)}", required_columns=REQUIRED_COLUMNS)
    _debug_loaded_table(df2, f"ENA file2 raw:{os.path.basename(metadata_file2)}", required_columns=REQUIRED_COLUMNS)
    _debug_loaded_table(df3, f"ENA file3 raw:{os.path.basename(metadata_file3)}", required_columns=REQUIRED_COLUMNS)
    df1 = _normalize_loaded_metadata_dataframe(df1, "file1")
    df2 = _normalize_loaded_metadata_dataframe(df2, "file2")
    df3 = _normalize_loaded_metadata_dataframe(df3, "file3")
    _debug_loaded_table(df1, f"ENA file1 normalized:{os.path.basename(metadata_file1)}", required_columns=REQUIRED_COLUMNS)
    _debug_loaded_table(df2, f"ENA file2 normalized:{os.path.basename(metadata_file2)}", required_columns=REQUIRED_COLUMNS)
    _debug_loaded_table(df3, f"ENA file3 normalized:{os.path.basename(metadata_file3)}", required_columns=REQUIRED_COLUMNS)
    print("\n[DEBUG] Initial source-file run_accession checks")
    _debug_run_accession_status(df1, "load_collated_metadata", "file1")
    _debug_run_accession_status(df2, "load_collated_metadata", "file2")
    _debug_run_accession_status(df3, "load_collated_metadata", "file3")
    _debug_specific_samples(df1, "load_collated_metadata", label="file1")
    _debug_specific_samples(df2, "load_collated_metadata", label="file2")
    _debug_specific_samples(df3, "load_collated_metadata", label="file3")
    
    # Load Refseq samples from QC Excel as a 4th dataframe
    print(f"\nLoading Refseq samples from QC Excel: {os.path.basename(qc_excel_path)}")
    try:
        refseq_df = pd.read_excel(qc_excel_path, sheet_name='Refseq')
        refseq_df = _normalize_loaded_metadata_dataframe(refseq_df, "QC Excel Refseq raw")
        _debug_loaded_table(refseq_df, "QC Excel Refseq raw")
        # Refseq uses "FILE" as the primary identifier (matches QC data)
        # and "Assembly Accession" as secondary identifier
        if 'FILE' in refseq_df.columns:
            # Create mapping from FILE to Assembly Accession
            file_to_assembly = dict(zip(refseq_df['FILE'].dropna(), refseq_df.get('Assembly Accession', pd.Series(dtype=object))))
            
            # Create minimal dataframe with FILE as sample_accession
            refseq_metadata = pd.DataFrame({
                'sample_accession': refseq_df['FILE'].dropna().unique(),
                'study_accession': 'Refseq_collection'
            })
            
            # Add Assembly Accession as secondary_sample_accession
            refseq_metadata['secondary_sample_accession'] = refseq_metadata['sample_accession'].map(file_to_assembly)
            
            refseq_metadata['_source_file'] = 'Refseq'
            print(f"Refseq samples: {len(refseq_metadata)} rows")
            print("  Metadata extracted: sample_accession (FILE) + secondary_sample_accession (Assembly Accession)")
            
            # Report how many have secondary_sample_accession
            secondary_count = refseq_metadata['secondary_sample_accession'].notna().sum()
            print(f"  secondary_sample_accession populated for {secondary_count}/{len(refseq_metadata)} samples")
        else:
            refseq_metadata = pd.DataFrame()
            print("WARNING: 'FILE' column not found in Refseq sheet")
    except Exception as e:
        print(f"WARNING: Could not load Refseq sheet: {type(e).__name__}: {e}")
        refseq_metadata = pd.DataFrame()
    
    # Load NCTC samples from QC Excel as a 5th dataframe
    print(f"\nLoading NCTC samples from QC Excel: {os.path.basename(qc_excel_path)}")
    try:
        nctc_df = pd.read_excel(qc_excel_path, sheet_name='NCTC')
        nctc_df = _normalize_loaded_metadata_dataframe(nctc_df, "QC Excel NCTC raw")
        _debug_loaded_table(nctc_df, "QC Excel NCTC raw")
        # NCTC uses "strain" for sample identifier
        if 'strain' in nctc_df.columns:
            # Create dataframe with sample_accession from strain column
            nctc_metadata = pd.DataFrame({
                'sample_accession': nctc_df['strain'].dropna().unique()
            })
            nctc_metadata['study_accession'] = 'NCTC_collection'
            
            # Map Year_Cultured to collection_date
            metadata_cols = ['sample_accession']
            if 'Year_Cultured' in nctc_df.columns:
                # Create mapping from strain to Year_Cultured
                year_mapping = dict(zip(nctc_df['strain'], nctc_df['Year_Cultured']))
                nctc_metadata['collection_date'] = nctc_metadata['sample_accession'].map(year_mapping)
                # Convert to string, handling NaN
                nctc_metadata['collection_date'] = nctc_metadata['collection_date'].apply(
                    lambda x: str(int(x)) if pd.notna(x) else pd.NA
                )
                metadata_cols.append('collection_date')
                collection_date_count = nctc_metadata['collection_date'].notna().sum()
            else:
                collection_date_count = 0
            
            nctc_metadata['_source_file'] = 'NCTC'
            print(f"NCTC samples: {len(nctc_metadata)} rows")
            print(f"  Metadata extracted: {', '.join(metadata_cols)}")
            print("  study_accession set to: NCTC_collection")
            if 'Year_Cultured' in nctc_df.columns:
                print(f"  collection_date (years) populated for {collection_date_count}/{len(nctc_metadata)} samples")
                # Show example year if available
                if collection_date_count > 0:
                    first_year = nctc_metadata[nctc_metadata['collection_date'].notna()]['collection_date'].iloc[0]
                    print(f"    Example (first): {first_year}")
        else:
            nctc_metadata = pd.DataFrame()
            print("WARNING: 'strain' column not found in NCTC sheet")
    except Exception as e:
        print(f"WARNING: Could not load NCTC sheet: {type(e).__name__}: {e}")
        nctc_metadata = pd.DataFrame()
    
    # Track source file for each row
    df1['_source_file'] = os.path.basename(metadata_file1)
    df2['_source_file'] = os.path.basename(metadata_file2)
    df3['_source_file'] = os.path.basename(metadata_file3)
    
    # Report per-file statistics
    print("\n" + "="*80)
    print("MERGE STATISTICS")
    print("="*80)
    file1_name = os.path.basename(metadata_file1)
    file2_name = os.path.basename(metadata_file2)
    file3_name = os.path.basename(metadata_file3)
    
    df1_rows = len(df1)
    df1_unique = df1['sample_accession'].nunique() if 'sample_accession' in df1.columns else 0
    df2_rows = len(df2)
    df2_unique = df2['sample_accession'].nunique() if 'sample_accession' in df2.columns else 0
    df3_rows = len(df3)
    df3_unique = df3['sample_accession'].nunique() if 'sample_accession' in df3.columns else 0
    refseq_rows = len(refseq_metadata)
    refseq_unique = refseq_metadata['sample_accession'].nunique() if 'sample_accession' in refseq_metadata.columns else 0
    nctc_rows = len(nctc_metadata)
    nctc_unique = nctc_metadata['sample_accession'].nunique() if 'sample_accession' in nctc_metadata.columns else 0
    
    print(f"File 1 ({file1_name}):")
    print(f"  Rows: {df1_rows}")
    print(f"  Unique samples: {df1_unique}")
    print(f"\nFile 2 ({file2_name}):")
    print(f"  Rows: {df2_rows}")
    print(f"  Unique samples: {df2_unique}")
    print(f"\nFile 3 ({file3_name}):")
    print(f"  Rows: {df3_rows}")
    print(f"  Unique samples: {df3_unique}")
    if refseq_rows > 0:
        print("\nRefseq (from QC Excel):")
        print(f"  Rows: {refseq_rows}")
        print(f"  Unique samples: {refseq_unique}")
    if nctc_rows > 0:
        print("\nNCTC (from QC Excel):")
        print(f"  Rows: {nctc_rows}")
        print(f"  Unique samples: {nctc_unique}")

    # Report overlap specifically between ENA (file1+file2) and bakrep (file3)
    ena_combined = pd.concat([df1, df2], ignore_index=True, sort=False)
    _report_ena_bakrep_overlap(ena_combined, df3)
    
    # Concatenate all dataframes (3 TSVs + Refseq + NCTC)
    dfs_to_concat = [df1, df2, df3]
    if not refseq_metadata.empty:
        dfs_to_concat.append(refseq_metadata)
    if not nctc_metadata.empty:
        dfs_to_concat.append(nctc_metadata)
    
    combined = pd.concat(dfs_to_concat, ignore_index=True)
    _debug_run_accession_status(combined, "load_collated_metadata", "after_concat_before_dedup")
    _debug_specific_samples(combined, "load_collated_metadata", label="after_concat_before_dedup")
    total_rows_after_concat = len(combined)
    total_unique_after_concat = combined['sample_accession'].nunique() if 'sample_accession' in combined.columns else 0
    
    print("\nAfter concatenation:")
    print(f"  Total rows: {total_rows_after_concat}")
    print(f"  Total unique samples: {total_unique_after_concat}")
    
    # Detect duplicates by sample_accession
    if 'sample_accession' in combined.columns:
        duplicate_counts = combined['sample_accession'].value_counts()
        duplicates = duplicate_counts[duplicate_counts > 1]
        
        if not duplicates.empty:
            print("\nDuplicate detection:")
            print(f"  Duplicates found: {len(duplicates)} unique sample_accession(s) with {duplicates.sum()} total rows")
            
            # Track which files each duplicate came from
            duplicate_details: List[Dict[str, str]] = []
            for sample_acc in duplicates.index:
                dup_rows = combined[combined['sample_accession'] == sample_acc]
                source_files = dup_rows['_source_file'].unique().tolist()
                duplicate_details.append({
                    'sample_accession': sample_acc,
                    'occurrences': len(dup_rows),
                    'source_files': ', '.join(sorted(source_files))
                })
            
            # # Show first 20 duplicate samples with details
            # print("  Sample accessions with duplicates (showing first 20):")
            # for detail in duplicate_details[:20]:
            #     print(f"    {detail['sample_accession']}: {detail['occurrences']} occurrences from {detail['source_files']}")
            # if len(duplicate_details) > 20:
            #     print(f"    ... and {len(duplicate_details) - 20} more duplicate sample accessions")
            
            # Coalesce duplicates into a single row per sample_accession.
            # Priority follows concatenation order:
            # file1 (ENA) -> file2 (ENA) -> file3 (bakrep) -> Refseq -> NCTC
            # This preserves ENA values when present and uses later sources
            # (including bakrep) only to fill missing values.
            rows_before_dedup = len(combined)
            cols = combined.columns.tolist()

            def _coalesce_group(group: pd.DataFrame) -> pd.Series:
                out: Dict[str, object] = {}
                for col in cols:
                    if col not in group.columns:
                        # With include_groups=False, groupby key column is not present.
                        if col == "sample_accession":
                            out[col] = group.name
                        else:
                            out[col] = pd.NA
                        continue
                    chosen = pd.NA
                    for val in group[col]:
                        if pd.notna(val):
                            if isinstance(val, str):
                                val = _strip_cell_value(val)
                                if val == "":
                                    continue
                                chosen = val
                                break
                            chosen = val
                            break
                    out[col] = chosen
                return pd.Series(out)

            combined = (
                combined
                .groupby('sample_accession', as_index=False, sort=False)
                .apply(_coalesce_group, include_groups=False)
                .reset_index(drop=True)
            )
            rows_removed = rows_before_dedup - len(combined)
            
            print(f"  Duplicate rows coalesced: {rows_removed}")
            print(f"  Rows remaining after coalescing: {len(combined)}")
            _debug_run_accession_status(combined, "load_collated_metadata", "after_initial_dedup")
            _debug_specific_samples(combined, "load_collated_metadata", label="after_initial_dedup")
        else:
            print("\nDuplicate detection:")
            print("  No duplicates found - all sample_accession values are unique")
    
    # Remove temporary source file column
    combined = combined.drop(columns=['_source_file'])
    
    final_unique = combined['sample_accession'].nunique() if 'sample_accession' in combined.columns else 0
    print("\nFinal merged data:")
    print(f"  Total rows: {len(combined)}")
    print(f"  Total unique samples: {final_unique}")
    print("="*80 + "\n")
    
    print(f"Collated metadata loaded: {combined.shape[0]} rows, {combined.shape[1]} columns")
    
    # Load reviewed study accessions from study-level metadata CSV
    reviewed_studies = load_study_accessions(study_metadata_file)
    print(f"Found {len(reviewed_studies)} reviewed studies in study-level metadata")
    
    # Add metadata_reviewed column
    combined['metadata_reviewed'] = combined['study_accession'].isin(reviewed_studies)
    
    # Report statistics on reviewed studies
    report_reviewed_studies_statistics(combined, reviewed_studies)
    
    # Load list of studies to remove from Google Sheet
    removed_studies_set = load_removed_studies(google_sheet_id, sheet_name="removed_studies")
    
    initial_rows = len(combined)
    initial_studies = combined['study_accession'].nunique()
    
    # Filter: remove studies that are in the removed_studies list
    filter_mask = ~combined['study_accession'].isin(removed_studies_set)
    
    # Identify removed studies for reporting
    removed_mask = ~filter_mask
    if removed_mask.any():
        removed_studies_data = combined[removed_mask]
        removed_study_counts = removed_studies_data.groupby('study_accession')['sample_accession'].nunique().sort_values(ascending=False)
        
        print("\n" + "="*80)
        print("REMOVED STUDIES (from 'removed_studies' sheet in Google Sheet)")
        print("="*80)
        print(f"Number of studies removed: {len(removed_study_counts)}")
        print(f"Total samples removed: {removed_mask.sum()}")
        print("\nRemoved studies (study_accession: sample_count):")
        for study_acc, count in removed_study_counts.items():
            print(f"  {study_acc}: {count} samples")
        print("="*80 + "\n")
    else:
        if len(removed_studies_set) > 0:
            print(f"\nNOTE: {len(removed_studies_set)} studies listed in 'removed_studies' sheet, but none were found in the metadata")
        else:
            print("\nNOTE: No studies to remove (removed_studies sheet is empty or not found)")
    
    # Apply filter
    combined = combined[filter_mask].copy()
    _debug_run_accession_status(combined, "load_collated_metadata", "after_removed_studies_filter")
    _debug_specific_samples(combined, "load_collated_metadata", label="after_removed_studies_filter")
    
    print(f"After filtering: {combined.shape[0]} rows (removed {initial_rows - combined.shape[0]} rows), {combined['study_accession'].nunique()} studies (removed {initial_studies - combined['study_accession'].nunique()} studies)")
    
    # Report detailed statistics (filter_study_size parameter kept for compatibility but not used)
    report_filtered_samples_statistics(combined, filter_study_size)
    
    return combined


def import_refseq_metadata(
    updated_data: pd.DataFrame,
    qc_excel_path: str = QC_EXCEL_FILE,
) -> pd.DataFrame:
    """
    Import enhanced metadata from Refseq sheet into the metadata dataframe.
    
    Maps Refseq columns to metadata columns:
    - "Assembly BioSample Collection date" → "collection_date"
    - "Assembly BioSample Geographic location" → "country"
    - "Assembly BioSample Host" → "host"
    - "Assembly BioSample Host disease" → "host_status"
    - "Assembly BioSample Isolation source" → "isolation_source"
    
    Parameters:
    -----------
    updated_data : pd.DataFrame
        The metadata dataframe with sample_accession column
    qc_excel_path : str
        Path to the QC Excel file (default: QC_EXCEL_FILE)
    
    Returns:
    --------
    pd.DataFrame
        The metadata dataframe with Refseq metadata columns added/updated
    """
    print("\n--- Importing Refseq metadata ---")
    try:
        refseq_df = pd.read_excel(qc_excel_path, sheet_name='Refseq')
        refseq_df = _normalize_loaded_metadata_dataframe(refseq_df, "import_refseq_metadata Refseq raw")
        _debug_loaded_table(refseq_df, "import_refseq_metadata Refseq raw")

        # Refseq uses "FILE" as the primary identifier (matches sample_accession in metadata)
        if 'FILE' in refseq_df.columns:
            # Rename to 'Sample' for consistency with rest of function
            refseq_df = refseq_df.rename(columns={'FILE': 'Sample'})
        else:
            print("  WARNING: 'FILE' column not found in 'Refseq' sheet, skipping Refseq metadata import")
            return updated_data

        # Define column mappings
        column_mappings = {
            "Assembly BioSample Collection date": "collection_date",
            "Assembly BioSample Geographic location": "country",
            "Assembly BioSample Host": "host",
            "Assembly BioSample Host disease": "host_status",
            "Assembly BioSample Isolation source": "isolation_source"
        }

        # Create a subset of Refseq data with only the columns we need
        refseq_metadata = refseq_df[['Sample'] + [col for col in column_mappings.keys() if col in refseq_df.columns]].copy()

        # Rename columns to match metadata column names
        rename_dict = {col: column_mappings[col] for col in column_mappings.keys() if col in refseq_metadata.columns}
        refseq_metadata = refseq_metadata.rename(columns=rename_dict)

        # Track state before updates for logging
        matched_samples = updated_data['sample_accession'].isin(refseq_metadata['Sample'])
        matched_count = matched_samples.sum()
        print(f"  Matched {matched_count} samples from Refseq sheet")
        
        # Ensure study_accession is set to 'Refseq_collection' for matched samples
        # Check which matched samples have study_accession = 'Refseq_collection'
        refseq_study_mask = matched_samples & (updated_data['study_accession'] == 'Refseq_collection')
        refseq_study_count = refseq_study_mask.sum()
        print(f"  study_accession: {refseq_study_count}/{matched_count} samples already set to 'Refseq_collection'")
        if refseq_study_count < matched_count:
            print(f"    Note: {matched_count - refseq_study_count} matched samples have different study_accession values (keeping as-is)")
        
        # Merge with metadata, overwriting existing values
        # Use 'right' join approach: update existing rows where Sample matches sample_accession
        for col in rename_dict.values():
            if col in refseq_metadata.columns:
                # Track values before update
                if col not in updated_data.columns:
                    updated_data[col] = pd.NA
                before_mask = updated_data[col].notna()
                
                # Create a mapping dictionary from Refseq data
                refseq_map = dict(zip(refseq_metadata['Sample'], refseq_metadata[col]))
                
                # Identify which samples have non-NA values in Refseq
                refseq_has_value = refseq_metadata[col].notna()
                refseq_samples_with_value = set(refseq_metadata[refseq_has_value]['Sample'])
                
                # Count how many matched samples have values in Refseq
                matched_with_refseq_value = updated_data['sample_accession'].isin(refseq_samples_with_value)
                refseq_values_count = matched_with_refseq_value.sum()
                
                # Update metadata where sample_accession matches
                updated_data[col] = updated_data['sample_accession'].map(refseq_map).fillna(updated_data[col])
                
                # Track what was newly added (was NA, now has value from Refseq)
                after_mask = updated_data[col].notna()
                newly_added = after_mask & ~before_mask & matched_with_refseq_value
                newly_added_count = newly_added.sum()
                
                # Get first example value from Refseq
                if refseq_values_count > 0:
                    # Find first sample that has a Refseq value
                    first_sample_with_value = refseq_metadata[refseq_has_value]['Sample'].iloc[0]
                    first_value = refseq_metadata[refseq_metadata['Sample'] == first_sample_with_value][col].iloc[0]
                    overwritten_count = refseq_values_count - newly_added_count
                    print(f"  {col}: {refseq_values_count} values added/updated ({newly_added_count} newly added, {overwritten_count} overwritten)")
                    print(f"    Example (first): {first_value}")
                else:
                    print(f"  {col}: No values added (column exists in Refseq but all values are NA)")
        
        # Report which columns were updated
        updated_cols = [col for col in rename_dict.values() if col in refseq_metadata.columns]
        if updated_cols:
            print(f"  Summary: Updated columns: {', '.join(updated_cols)}")
        
    except Exception as e:
        print(f"  WARNING: Could not import Refseq metadata: {type(e).__name__}: {e}")
        print("  Continuing without Refseq metadata import...")
    
    return updated_data


def find_ready_to_merge_files(ena_project_dir: str = ENA_PROJECT_DIR, verbose: bool = False) -> List[ReadyToMergeFilename]:
    """Locate ready_to_merge filenames in each project subfolder; error if a folder has >1."""
    if verbose:
        print(f"Scanning for ready_to_merge filenames in ENA project directory:\n  {ena_project_dir}")
    records: List[ReadyToMergeFilename] = []
    multi_matches: Dict[str, List[str]] = {}

    for entry in os.scandir(ena_project_dir):
        if not entry.is_dir():
            continue
        folder = entry.name
        ready_files = [
            os.path.join(entry.path, f)
            for f in os.listdir(entry.path)
            if "ready_to_merge" in f
        ]
        if len(ready_files) > 1:
            multi_matches[folder] = ready_files
        elif len(ready_files) == 1:
            records.append(ReadyToMergeFilename(project_folder=folder, file_path=ready_files[0]))

    if multi_matches:
        details = "; ".join(f"{folder}: {files}" for folder, files in multi_matches.items())
        raise ValueError(f"Found multiple ready_to_merge files in subfolders: {details}")

    print(f"Found {len(records)} ready_to_merge filenames (one per subfolder).")
    return records


def _read_ready_to_merge_file(path: str, verbose: bool = False) -> Tuple[pd.DataFrame, str]:
    """
    Read data from a ready_to_merge file, trying CSV first, then TSV if needed.
    
    Raises an error if required columns are missing in both formats.
    
    Parameters:
    -----------
    path : str
        Path to the ready_to_merge file
    verbose : bool
        If True, print detailed reading messages. Default: False
    """
    if verbose:
        print(f"  Reading data from ready_to_merge file: {path}")
    
    # Try CSV first (only wrap parsing in try/except; normalization errors must not be swallowed).
    try:
        df_csv = pd.read_csv(path, sep=",", low_memory=False, skipinitialspace=True)
    except Exception as e:
        if verbose:
            print(f"  CSV read failed ({type(e).__name__}), trying TSV...")
        missing_cols_csv = list(REQUIRED_COLUMNS)
        df_csv = None
    else:
        missing_cols_csv = [col for col in REQUIRED_COLUMNS if col not in df_csv.columns]
        if not missing_cols_csv:
            if verbose:
                print(f"  Successfully read as CSV: {df_csv.shape[0]} rows with all required columns")
            df_csv = _normalize_loaded_metadata_dataframe(
                df_csv, f"ready_to_merge_csv:{os.path.basename(path)}"
            )
            return df_csv, "csv"
        if verbose:
            print(f"  CSV format missing {len(missing_cols_csv)} required columns, trying TSV...")
    
    # Try TSV
    try:
        df_tsv = _read_tab_separated_table(path)
    except Exception as e:
        if verbose:
            print(f"  TSV read also failed ({type(e).__name__})")
        missing_cols_tsv = list(REQUIRED_COLUMNS)
    else:
        missing_cols_tsv = [col for col in REQUIRED_COLUMNS if col not in df_tsv.columns]
        if not missing_cols_tsv:
            if verbose:
                print(f"  Successfully read as TSV: {df_tsv.shape[0]} rows with all required columns")
            df_tsv = _normalize_loaded_metadata_dataframe(
                df_tsv, f"ready_to_merge_tsv:{os.path.basename(path)}"
            )
            return df_tsv, "tsv"
        if verbose:
            print(f"  TSV format also missing {len(missing_cols_tsv)} required columns")
    
    # Both failed - report the better attempt
    if len(missing_cols_csv) <= len(missing_cols_tsv):
        missing_cols = missing_cols_csv
        format_type = "CSV"
    else:
        missing_cols = missing_cols_tsv
        format_type = "TSV"
    
    raise ValueError(
        f"CRITICAL ERROR: File is missing required columns in both CSV and TSV formats.\n"
        f"File: {path}\n"
        f"Best attempt ({format_type}) missing {len(missing_cols)} columns: {missing_cols[:10]}"
        + (f"... and {len(missing_cols) - 10} more" if len(missing_cols) > 10 else "")
        + "\n\nPlease fix the source file:\n"
        "  - Add missing columns to the source data\n"
        "  - Or remove the file if not needed"
    )


def apply_ready_to_merge_updates(
    destination_data: pd.DataFrame,
    ready_files: Sequence[ReadyToMergeFilename],
    verbose: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Substitute rows in destination_data using ready_to_merge files.
    Returns: updated_data, deleted_data, substituted_data, critical_unmatched, critical_duplicates.
    
    Note: deleted_data and substituted_data are returned for completeness analysis only (not saved to disk).
    
    Optimized: Reads all files first, concatenates into one dataframe, then does ONE merge operation.
    
    Parameters:
    -----------
    destination_data : pd.DataFrame
        The destination dataframe to update
    ready_files : Sequence[ReadyToMergeFilename]
        Sequence of ready_to_merge file records
    verbose : bool
        If True, print detailed reading messages. Default: False
    """
    print(f"Reading and combining {len(ready_files)} ready_to_merge file(s)...")
    
    # Step 1: Read all files and concatenate, collecting errors
    ready_dfs: List[pd.DataFrame] = []
    problematic_files: List[Dict[str, str]] = []
    read_mode_counts = {"csv": 0, "tsv": 0}
    total_ready_rows = 0
    
    for record in ready_files:
        if verbose:
            print(f"- Reading from project folder '{record.project_folder}'")
        try:
            ready_df, read_mode = _read_ready_to_merge_file(record.file_path, verbose)
            # Track which file each row came from for error reporting
            ready_df['_source_file'] = record.file_path
            ready_dfs.append(ready_df)
            read_mode_counts[read_mode] += 1
            total_ready_rows += len(ready_df)
        except ValueError as e:
            # Collect problematic files instead of failing immediately
            error_msg = str(e)
            problematic_files.append({
                "project_folder": record.project_folder,
                "file_path": record.file_path,
                "error": error_msg
            })
            print("  WARNING: Skipping file due to errors (will report at end)")
    
    # Report all problematic files at once
    if problematic_files:
        print("\n" + "="*80)
        print(f"CRITICAL ERROR: {len(problematic_files)} file(s) have formatting problems:")
        print("="*80)
        for idx, problem in enumerate(problematic_files, start=1):
            print(f"\n{idx}. Project folder: {problem['project_folder']}")
            print(f"   File: {problem['file_path']}")
            print("   Issue: Missing required columns in both CSV and TSV formats")
        print("\n" + "="*80)
        print("Please fix these files:")
        print("  - Add missing columns to the source data")
        print("  - Or remove files if not needed")
        print("="*80 + "\n")
        raise ValueError(f"Cannot proceed: {len(problematic_files)} file(s) have formatting problems. See list above.")

    print("\nready_to_merge read summary:")
    print(f"  Files successfully loaded: {len(ready_dfs)}")
    print(f"  Parsed as CSV: {read_mode_counts['csv']}")
    print(f"  Parsed as TSV fallback: {read_mode_counts['tsv']}")
    print(f"  Total rows across all ready_to_merge files: {total_ready_rows}")
    
    print(f"Concatenating {len(ready_dfs)} dataframes...")
    combined_ready_df = pd.concat(ready_dfs, ignore_index=True)
    print(f"Combined ready_to_merge data: {len(combined_ready_df)} total rows")
    _debug_run_accession_status(combined_ready_df, "apply_ready_to_merge_updates", "combined_ready_df")
    _debug_specific_samples(combined_ready_df, "apply_ready_to_merge_updates", label="combined_ready_df")
    
    # Step 2: Vectorized matching and substitution (O(n log n) instead of O(n*m))
    print(f"Performing vectorized match and substitution for {len(combined_ready_df)} rows...")
    updated = destination_data.copy()
    _debug_run_accession_status(updated, "apply_ready_to_merge_updates", "destination_before_substitution")
    _debug_specific_samples(updated, "apply_ready_to_merge_updates", label="destination_before_substitution")
    
    # Check for unmatched sample_accessions (in ready_df but not in destination - these will be DISCARDED)
    unmatched_mask = ~combined_ready_df['sample_accession'].isin(updated['sample_accession'])
    if unmatched_mask.any():
        unmatched_df = combined_ready_df[unmatched_mask].copy()
        print(f"  WARNING: Found {len(unmatched_df)} sample_accession(s) in ready_to_merge files that don't match any samples in the initial dataset")
        print("  These samples will be DISCARDED (not added to the dataset)")
        
        # Report by project (study_accession)
        if 'study_accession' in unmatched_df.columns:
            project_counts = unmatched_df['study_accession'].value_counts()
            print(f"  Discarded samples by project ({len(project_counts)} projects):")
            for project, count in project_counts.items():
                print(f"    {project}: {count} samples discarded")
        
        # Do not add unmatched samples - discard them
        new_rows_to_add = pd.DataFrame()
    else:
        new_rows_to_add = pd.DataFrame()
    
    # Check for duplicates in destination (sample_accession appears >1 time in destination)
    matched_in_ready = combined_ready_df[~unmatched_mask]['sample_accession'].unique()
    duplicate_counts = updated[updated['sample_accession'].isin(matched_in_ready)]['sample_accession'].value_counts()
    duplicates = duplicate_counts[duplicate_counts > 1]
    
    if not duplicates.empty:
        print(f"  Found {len(duplicates)} sample_accession(s) with duplicate entries in destination data")
        print("  Taking first occurrence for each duplicate and discarding others")
        
        # For each duplicate in destination, keep only the first occurrence
        for sample_acc in duplicates.index:
            # Find all indices with this sample_accession
            dup_indices = updated[updated['sample_accession'] == sample_acc].index
            # Mark all but first for removal
            updated = updated.drop(dup_indices[1:])
        
        print(f"  Removed {(duplicates - 1).sum()} duplicate rows from destination")
    
    # Create masks for rows to keep vs replace
    ready_sample_accessions_to_replace = set(combined_ready_df[~unmatched_mask]['sample_accession'])
    mask_to_replace = updated['sample_accession'].isin(ready_sample_accessions_to_replace)
    mask_to_keep = ~mask_to_replace
    
    print(f"  Rows to keep unchanged: {mask_to_keep.sum()}, Rows to replace: {mask_to_replace.sum()}, New rows to add: {len(new_rows_to_add)}")
    
    # Track deleted and substituted data
    deleted_data = updated[mask_to_replace].copy()
    
    # Clean ready_df for substitution (remove source_file column, filter to matched only)
    combined_ready_df_clean = combined_ready_df[~unmatched_mask].drop(columns=['_source_file']).copy()
    substituted_data = combined_ready_df_clean.copy()
    _debug_run_accession_status(deleted_data, "apply_ready_to_merge_updates", "deleted_data_overwritten_rows")
    _debug_specific_samples(deleted_data, "apply_ready_to_merge_updates", label="deleted_data_overwritten_rows")
    _debug_run_accession_status(substituted_data, "apply_ready_to_merge_updates", "substituted_data_replacement_rows")
    _debug_specific_samples(substituted_data, "apply_ready_to_merge_updates", label="substituted_data_replacement_rows")
    
    # Perform vectorized substitution: keep unchanged rows + add replacement rows + add new rows
    kept_data = updated[mask_to_keep].copy()
    
    # Concatenate all parts, ensuring consistent dtypes
    parts_to_concat = [kept_data, combined_ready_df_clean]
    if not new_rows_to_add.empty:
        parts_to_concat.append(new_rows_to_add)
    
    updated = pd.concat(parts_to_concat, ignore_index=True, sort=False)
    
    print(f"  Substitution complete: {len(updated)} total rows in updated data")
    _debug_run_accession_status(updated, "apply_ready_to_merge_updates", "updated_after_substitution")
    _debug_specific_samples(updated, "apply_ready_to_merge_updates", label="updated_after_substitution")
    
    # Empty error dataframes (no critical errors, handled gracefully)
    critical_unmatched = []
    critical_duplicates = []

    # Report critical errors
    critical_unmatched_df = pd.DataFrame(critical_unmatched)
    critical_duplicates_df = pd.DataFrame(critical_duplicates)
    if not critical_unmatched_df.empty or not critical_duplicates_df.empty:
        print(
            "Critical substitution errors encountered: "
            f"{len(critical_unmatched_df)} unmatched sample_accession(s), "
            f"{len(critical_duplicates_df)} sample_accession(s) with duplicate matches."
        )
        raise RuntimeError(
            "Critical substitution errors encountered "
            f"(unmatched: {len(critical_unmatched_df)}, duplicates: {len(critical_duplicates_df)})."
        )

    print(
        f"Substitution complete. Rows replaced: {len(deleted_data)}, "
        f"new rows substituted: {len(substituted_data)}."
    )

    return updated, deleted_data, substituted_data, critical_unmatched_df, critical_duplicates_df


def compare_curated_columns(
    column_name: str,
    deleted_data: pd.DataFrame,
    substituted_data: pd.DataFrame,
    show_unique_values_before: bool = False,
    show_unique_values_after: bool = False,
) -> Dict[str, float]:
    """
    Call report_ena_column on deleted vs substituted for a column and return completeness metrics.
    
    Parameters:
    -----------
    show_unique_values_before : bool
        If True, show unique values for deleted_data (overwritten rows). Default False.
    show_unique_values_after : bool
        If True, show unique values for substituted_data (replacement rows). Default False.
    """
    # Report completeness of rows that were overwritten
    print(f"\n--- Completeness of data that was OVERWRITTEN (column: {column_name}) ---")
    report_ena_column(deleted_data, column_name, display_n=0)
    
    # Report completeness of new replacement rows
    print(f"\n--- Completeness of NEWLY SUBSTITUTED data (column: {column_name}) ---")
    report_ena_column(substituted_data, column_name, display_n=0)

    before_total = len(deleted_data)
    after_total = len(substituted_data)
    before_present = deleted_data[column_name].notna().sum() if before_total else 0
    after_present = substituted_data[column_name].notna().sum() if after_total else 0

    before_completeness = before_present / before_total if before_total else 0.0
    after_completeness = after_present / after_total if after_total else 0.0
    delta = after_completeness - before_completeness

    print(
        f"\nSUMMARY for '{column_name}':"
        f"\n  Overwritten data completeness: {before_completeness:.3f}"
        f"\n  Substituted data completeness: {after_completeness:.3f}"
        f"\n  Delta (improvement): {delta:+.3f}"
    )

    return {
        "column": column_name,
        "before_completeness": before_completeness,
        "after_completeness": after_completeness,
        "delta": delta,
        "decreased": delta < 0,
    }


def analyze_completeness(
    deleted_data: pd.DataFrame,
    substituted_data: pd.DataFrame,
) -> pd.DataFrame:
    """Analyze completeness for key columns and return a summary dataframe."""
    print("\n" + "="*80)
    print("COMPLETENESS ANALYSIS: Comparing overwritten vs substituted data")
    print("="*80)
    missing_cols = [c for c in KEY_COLUMNS if c not in deleted_data.columns or c not in substituted_data.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns for completeness analysis: {missing_cols}")

    summaries: List[Dict[str, float]] = []
    for col in KEY_COLUMNS:
        # Unique value listings are removed - only show summary statistics
        summaries.append(compare_curated_columns(
            col, deleted_data, substituted_data,
            show_unique_values_before=False,
            show_unique_values_after=False
        ))

    summary_df = pd.DataFrame(summaries)

    # Per-project completeness and decreases
    if "study_accession" not in deleted_data.columns or "study_accession" not in substituted_data.columns:
        raise ValueError("Missing required column 'study_accession' for project-level completeness.")

    project_rows: List[Dict[str, object]] = []
    for project, before_proj in deleted_data.groupby("study_accession"):
        after_proj = substituted_data[substituted_data["study_accession"] == project]
        for col in KEY_COLUMNS:
            before_total = len(before_proj)
            after_total = len(after_proj)
            before_comp = before_proj[col].notna().sum() / before_total if before_total else 0.0
            after_comp = after_proj[col].notna().sum() / after_total if after_total else 0.0
            delta = after_comp - before_comp
            
            # Calculate value summary for original data
            non_na_values = before_proj[col].dropna()
            if len(non_na_values) > 0:
                value_counts = non_na_values.value_counts()
                unique_count = len(value_counts)
                most_common_val = value_counts.index[0]
                most_common_count = value_counts.iloc[0]
                values_before_summary = f"{unique_count} unique (most common: {most_common_val}, n={most_common_count})"
            else:
                values_before_summary = "0 unique (all NA)"
            
            project_rows.append(
                {
                    "study_accession": project,
                    "column": col,
                    "n": before_total,
                    "before_completeness": before_comp,
                    "after_completeness": after_comp,
                    "delta": delta,
                    "decreased": after_comp < before_comp,
                    "values_before_summary": values_before_summary,
                }
            )

    project_summary_df = pd.DataFrame(project_rows)

    # Filter to significant decreases only (delta <= -0.05)
    significant_decreases = project_summary_df[
        (project_summary_df["decreased"]) & (project_summary_df["delta"] <= -0.05)
    ]
    
    if not significant_decreases.empty:
        print("\nProjects (study accession) with decreased completeness (delta <= -0.05):")
        # Format output with proper column widths
        display_cols = ["study_accession", "column", "n", "delta", "values_before_summary"]
        print(significant_decreases[display_cols].to_string(index=False))

    return pd.concat(
        [
            summary_df.assign(scope="overall"),
            project_summary_df.assign(scope="per_project"),
        ],
        ignore_index=True,
    )


def write_outputs(
    updated_data: pd.DataFrame,
    output_dir: str = OUTPUT_DIR,
) -> None:
    """Write intermediate data to TSV file (without QC data)."""
    os.makedirs(output_dir, exist_ok=True)

    updated_path = f"{output_dir}/intermediate_collated_metadata_wo_qc_or_kleborate.tsv"

    updated_data.to_csv(updated_path, sep="\t", index=False)

    print("Output written:")
    print(f"  Intermediate metadata (without QC): {updated_path}")


def plot_completeness_comparison(initial_data, final_data, output_dir):
    """
    Plot completeness comparison pre vs post ready_to_merge updates for 4 key columns.
    Shows sample-level breakdown: reviewed pre-curation, curation added, unreviewed pre-curation.
    
    Note: This compares initial data (before ready_to_merge) vs final data (after ready_to_merge).
    QC operations are not included in this comparison.
    
    Parameters:
    -----------
    initial_data : pd.DataFrame
        Initial combined data with metadata_reviewed flag (before ready_to_merge updates)
    final_data : pd.DataFrame
        Data after ready_to_merge updates (before QC operations)
    output_dir : str
        Directory to save the figure
        
    Returns:
    --------
    dict : Statistics including total studies and total samples
    """
    # Define column mappings: (column_name, display_name)
    columns = [
        ('host', 'Host'),
        ('country', 'Country'),
        ('collection_date', 'Collection Date'),
        ('isolation_source', 'Isolation Source')
    ]
    
    # Validate required columns exist
    if 'metadata_reviewed' not in initial_data.columns:
        print("Warning: 'metadata_reviewed' column not found in initial_data, skipping plot")
        return {}
    
    # Calculate sample counts for each category
    reviewed_pre = []
    curation_added = []
    unreviewed_pre = []
    column_names = []
    
    for col_name, display_name in columns:
        if col_name not in initial_data.columns or col_name not in final_data.columns:
            print(f"Warning: Column '{col_name}' not found, skipping")
            continue
            
        column_names.append(display_name)
        
        # Count unique samples with data in initial (reviewed)
        initial_reviewed_mask = initial_data['metadata_reviewed'] & (initial_data[col_name].notna())
        if 'sample_accession' in initial_data.columns:
            reviewed_pre_count = initial_data[initial_reviewed_mask]['sample_accession'].nunique()
        else:
            reviewed_pre_count = initial_reviewed_mask.sum()
        
        # Count unique samples with data in initial (unreviewed)
        initial_unreviewed_mask = ~initial_data['metadata_reviewed'] & (initial_data[col_name].notna())
        if 'sample_accession' in initial_data.columns:
            unreviewed_pre_count = initial_data[initial_unreviewed_mask]['sample_accession'].nunique()
        else:
            unreviewed_pre_count = initial_unreviewed_mask.sum()
        
        # Count unique samples with data in final
        final_mask = final_data[col_name].notna()
        if 'sample_accession' in final_data.columns:
            final_count = final_data[final_mask]['sample_accession'].nunique()
        else:
            final_count = final_mask.sum()
        
        # Curation added = final - (reviewed_pre + unreviewed_pre)
        curation_added_count = final_count - (reviewed_pre_count + unreviewed_pre_count)
        
        reviewed_pre.append(reviewed_pre_count)
        curation_added.append(curation_added_count)
        unreviewed_pre.append(unreviewed_pre_count)
    
    if len(column_names) == 0:
        print("Warning: No valid columns found for plotting")
        return {}
    
    # Create stacked bar chart
    x = np.arange(len(column_names))
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Bottom: reviewed pre-curation (steelblue)
    ax.bar(x, reviewed_pre, label='Reviewed (pre-curation)', color='steelblue')
    
    # Middle: curation added (dark blue) - stacked on reviewed
    bottom_reviewed = np.array(reviewed_pre)
    ax.bar(x, curation_added, bottom=bottom_reviewed, label='Curation Added', color='darkblue')
    
    # Top: unreviewed pre-curation (skyblue with transparency) - stacked on everything
    bottom_total = bottom_reviewed + np.array(curation_added)
    ax.bar(x, unreviewed_pre, bottom=bottom_total, label='Unreviewed (pre-curation)', color='skyblue', alpha=0.5)
    
    ax.set_ylabel('Number of Samples', fontsize=12)
    ax.set_title('Completeness Comparison: Pre vs Post ready_to_merge Updates', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(column_names)
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for i, (rev_val, added_val, unrev_val) in enumerate(zip(reviewed_pre, curation_added, unreviewed_pre)):
        # Label in middle of reviewed segment (white text)
        if rev_val > 0:
            reviewed_mid = rev_val / 2
            ax.text(i, reviewed_mid, f'reviewed\nn = {int(rev_val):,}',
                   ha='center', va='center', fontsize=9, color='white', fontweight='bold')
        
        # Label in middle of curation added segment (white text)
        if added_val > 0:
            added_mid = bottom_reviewed[i] + added_val / 2
            ax.text(i, added_mid, f'added\nn = {int(added_val):,}',
                   ha='center', va='center', fontsize=9, color='white', fontweight='bold')
        
        # Label in middle of unreviewed segment (white text)
        if unrev_val > 0:
            unreviewed_mid = bottom_total[i] + unrev_val / 2
            ax.text(i, unreviewed_mid, f'unreviewed\nn = {int(unrev_val):,}',
                   ha='center', va='center', fontsize=9, color='white', fontweight='bold')
        
        # Label on top of stack (total in black)
        total = rev_val + added_val + unrev_val
        if total > 0:
            ax.text(i, total, f'{int(total):,}',
                   ha='center', va='bottom', fontsize=9, color='black')
    
    plt.tight_layout()
    
    # Save figure
    output_path = os.path.join(output_dir, 'completeness_comparison.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    # Calculate statistics
    if 'study_accession' in final_data.columns:
        total_studies = final_data['study_accession'].nunique()
        total_samples = final_data['sample_accession'].nunique() if 'sample_accession' in final_data.columns else len(final_data)
    else:
        total_studies = 0
        total_samples = len(final_data)
    
    stats = {
        'total_studies': total_studies,
        'total_samples': total_samples
    }
    
    return stats


def import_klebnet_metadata(
    updated_data: pd.DataFrame,
    klebnet_file: str,
    output_dir: str,
) -> pd.DataFrame:
    """
    Import KlebNET-GSP metadata and update sample metadata for matched samples.
    
    Matches samples by "Sample accession" → sample_accession and updates:
    - Collection year → year
    - Collection year/month/day → collection_date (yyyy/mm/dd)
    - Country + City or region → country (format: "Country : City or region")
    - Host → host
    - Host tissue sampled → isolation_source
    
    Writes detailed project summaries to klebnet_summary.txt file.
    
    Parameters:
    -----------
    updated_data : pd.DataFrame
        The metadata dataframe with sample_accession column
    klebnet_file : str
        Path to the KlebNET-GSP metadata CSV file
    output_dir : str
        Directory to write klebnet_summary.txt file
    
    Returns:
    --------
    pd.DataFrame
        The metadata dataframe with KlebNET metadata updates applied
    """
    print("\n" + "="*80)
    print("IMPORTING KLEBNET-GSP METADATA")
    print("="*80)
    
    try:
        # Load KlebNET metadata (using latin-1 encoding to handle special characters)
        klebnet_df = pd.read_csv(klebnet_file, encoding='latin-1', low_memory=False, skipinitialspace=True)
        klebnet_df = _normalize_loaded_metadata_dataframe(
            klebnet_df, f"klebnet:{os.path.basename(klebnet_file)}"
        )
        _debug_loaded_table(klebnet_df, f"KlebNET raw:{os.path.basename(klebnet_file)}", required_columns=["Sample accession"])
        print(f"Loaded KlebNET metadata: {len(klebnet_df)} rows")
        
        # Validate required columns
        required_cols = ["Sample accession"]
        missing_cols = [col for col in required_cols if col not in klebnet_df.columns]
        if missing_cols:
            print(f"  WARNING: Missing required columns: {missing_cols}")
            print("  Skipping KlebNET metadata import")
            return updated_data
        
        # Rename identifier column for matching
        klebnet_df = klebnet_df.rename(columns={"Sample accession": "sample_accession"})
        
        # Helper function to format date
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
        
        # Helper function to format country
        def format_klebnet_country(row):
            """Combine country and city/region into single string."""
            country = row.get("Country")
            city_or_region = row.get("City or region")
            
            if pd.isna(country):
                # If country doesn't exist, return NA (don't update)
                return pd.NA
            elif not pd.isna(city_or_region):
                # Both exist: combine them
                return f"{country} : {city_or_region}"
            else:
                # Only country exists
                return country
        
        # Process date and country columns
        if "Collection year" in klebnet_df.columns:
            klebnet_df["collection_date"] = klebnet_df.apply(format_klebnet_date, axis=1)
        
        if "Country" in klebnet_df.columns:
            klebnet_df["country"] = klebnet_df.apply(format_klebnet_country, axis=1)
        
        # Create mapping dictionaries for each column
        klebnet_samples = set(klebnet_df["sample_accession"].dropna().unique())
        our_samples = set(updated_data["sample_accession"].dropna().unique())
        matched_samples = klebnet_samples & our_samples
        
        print(f"KlebNET samples: {len(klebnet_samples)}")
        print(f"Samples in our metadata: {len(our_samples)}")
        print(f"Matched samples: {len(matched_samples)}")
        
        if len(matched_samples) == 0:
            print("  No matching samples found - skipping updates")
        else:
            # Create mappings for each column
            column_mappings = {}
            
            # Note: We don't map "Collection year" to "year" as year column doesn't exist in metadata
            # Only collection_date is updated
            
            if "collection_date" in klebnet_df.columns:
                column_mappings["collection_date"] = dict(zip(klebnet_df["sample_accession"], klebnet_df["collection_date"]))
            
            if "country" in klebnet_df.columns:
                column_mappings["country"] = dict(zip(klebnet_df["sample_accession"], klebnet_df["country"]))
            
            if "Host" in klebnet_df.columns:
                column_mappings["host"] = dict(zip(klebnet_df["sample_accession"], klebnet_df["Host"]))
            
            if "Host tissue sampled" in klebnet_df.columns:
                column_mappings["isolation_source"] = dict(zip(klebnet_df["sample_accession"], klebnet_df["Host tissue sampled"]))
            
            # Update metadata columns (overwrite existing values)
            for col_name, mapping_dict in column_mappings.items():
                if col_name in updated_data.columns:
                    # Update only matched samples, and only where mapping has non-NA values
                    mask = updated_data["sample_accession"].isin(matched_samples)
                    mapped_values = updated_data.loc[mask, "sample_accession"].map(mapping_dict)
                    # Only update where mapped value is not NA
                    non_na_mask = mapped_values.notna()
                    updated_data.loc[mask & non_na_mask, col_name] = mapped_values[non_na_mask]
                else:
                    # Column doesn't exist, create it
                    updated_data[col_name] = updated_data["sample_accession"].map(mapping_dict)
            
            print(f"  Updated metadata for {len(matched_samples)} samples")
        
        # Write project summaries to separate file
        summary_path = os.path.join(output_dir, 'klebnet_summary.txt')
        os.makedirs(output_dir, exist_ok=True)
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("KlebNET-GSP Project Summaries\n")
            f.write("="*80 + "\n\n")
            
            if "Project accession" in klebnet_df.columns:
                # Group by project accession
                project_groups = klebnet_df.groupby("Project accession")
                
                for project_acc, group_df in project_groups:
                    n_samples = len(group_df)
                    
                    # Get first non-null values for summary fields
                    def get_first_value(col_name):
                        if col_name in group_df.columns and group_df[col_name].notna().any():
                            return group_df[col_name].dropna().iloc[0]
                        return "N/A"
                    
                    country = get_first_value("Country")
                    host = get_first_value("Host")
                    purpose = get_first_value("Purpose of sampling")
                    population = get_first_value("Study population")
                    title = get_first_value("Study title")
                    
                    f.write(f"Project: {project_acc}\n")
                    f.write(f"  Samples: {n_samples}\n")
                    f.write(f"  Country: {country}\n")
                    f.write(f"  Host: {host}\n")
                    f.write(f"  Purpose: {purpose}\n")
                    f.write(f"  Population: {population}\n")
                    f.write(f"  Title: {title}\n")
                    f.write("-" * 80 + "\n")
            else:
                f.write("WARNING: 'Project accession' column not found - no project summaries available\n")
        
        print("Detailed project summaries saved to: klebnet_summary.txt")
        print("="*80 + "\n")
        
    except FileNotFoundError:
        print(f"  WARNING: KlebNET metadata file not found: {klebnet_file}")
        print("  Continuing without KlebNET metadata import...")
        print("="*80 + "\n")
    except Exception as e:
        print(f"  WARNING: Could not import KlebNET metadata: {type(e).__name__}: {e}")
        print("  Continuing without KlebNET metadata import...")
        print("="*80 + "\n")
    
    return updated_data


def run_metadata_collation(
    metadata_file1: str = ENA_METADATA_FILE1,
    metadata_file2: str = ENA_METADATA_FILE2,
    metadata_file3: str = ENA_METADATA_FILE3,
    ena_project_dir: str = ENA_PROJECT_DIR,
    output_dir: str = OUTPUT_DIR,
    study_metadata_file: str = STUDY_METADATA_FILE,
    filter_study_size: int = 131,
    verbose: bool = False,
) -> None:
    """
    Orchestrate the metadata collation workflow (without QC operations).
    
    This function:
    1. Loads and merges ENA metadata files
    2. Applies ready_to_merge substitutions
    3. Imports KlebNET-GSP metadata
    4. Analyzes completeness of substitutions
    5. Writes intermediate output (without QC data)
    
    QC operations (kleborate join, KPSC flag, QC filtering) are handled
    separately by metadata_add_qc.py.
    
    Parameters:
    -----------
    metadata_file1 : str
        Path to first ENA metadata TSV file
    metadata_file2 : str
        Path to second ENA metadata TSV file
    metadata_file3 : str
        Path to third ENA metadata TSV file (bakrep_extra_ena_metadata.tsv)
    ena_project_dir : str
        Directory containing ready_to_merge files in project subfolders
    output_dir : str
        Directory to write output files
    study_metadata_file : str
        Path to study-level metadata CSV file containing study_accessions column (default: STUDY_METADATA_FILE)
    filter_study_size : int
        Deprecated: kept for backward compatibility, not used anymore.
        Studies are now removed based on the 'removed_studies' sheet in Google Sheets.
        Default: 131
    verbose : bool
        If True, print detailed file reading messages. Default: False
    """
    # Set up logging to both file and console
    log_file_path = os.path.join(output_dir, "collated_metadata.log")
    os.makedirs(output_dir, exist_ok=True)
    original_stdout = sys.stdout
    tee_output = TeeOutput(log_file_path)
    sys.stdout = tee_output
    
    try:
        print("Starting metadata collation workflow...")
        print("Configuration:")
        print(f"  Metadata file 1: {metadata_file1}")
        print(f"  Metadata file 2: {metadata_file2}")
        print(f"  Metadata file 3: {metadata_file3}")
        print(f"  ENA project directory: {ena_project_dir}")
        print(f"  Output directory: {output_dir}")
        print(f"  Study metadata file: {study_metadata_file}")
        print(f"  Google Sheet ID: {STUDY_METADATA_GOOGLE_SHEET_ID}")
        print("  (Studies to remove loaded from 'removed_studies' sheet)\n")
        
        destination_data = load_collated_metadata(
            metadata_file1, metadata_file2, metadata_file3, study_metadata_file, 
            filter_study_size, google_sheet_id=STUDY_METADATA_GOOGLE_SHEET_ID,
            qc_excel_path=QC_EXCEL_FILE
        )
        _debug_run_accession_status(destination_data, "run_metadata_collation", "post_load_collated_metadata")
        _debug_specific_samples(destination_data, "run_metadata_collation", label="post_load_collated_metadata")
        
        # ============================================================================
        # SAVE CHECKPOINT: Combined metadata BEFORE ready_to_merge updates
        # ============================================================================
        # This save happens AFTER:
        #   - Loading and merging 3 ENA metadata TSV files
        #   - Adding Refseq samples (from QC Excel, sample_accession only)
        #   - Adding NCTC samples (from QC Excel, with sample_accession and collection_date)
        #   - Adding metadata_reviewed flag (from study-level metadata)
        #   - Filtering out removed studies (from removed_studies sheet)
        # 
        # This save happens BEFORE:
        #   - ready_to_merge file substitutions
        #   - KlebNET-GSP metadata import
        #   - QC operations (kleborate join, KPSC flags, QC filtering)
        # ============================================================================
        print("\n" + "="*80)
        print("SAVING CHECKPOINT: Combined metadata before collation")
        print("="*80)
        combined_before_collation_path = os.path.join(output_dir, 'combined_metadata_before_collation.tsv')
        destination_data.to_csv(combined_before_collation_path, sep="\t", index=False)
        print(f"File saved: {os.path.basename(combined_before_collation_path)}")
        print(f"Total rows saved: {len(destination_data)}")
        print("="*80 + "\n")
        
        # Import Refseq metadata BEFORE ready_to_merge substitutions
        destination_data = import_refseq_metadata(destination_data, QC_EXCEL_FILE)
        _debug_run_accession_status(destination_data, "run_metadata_collation", "post_import_refseq")
        _debug_specific_samples(destination_data, "run_metadata_collation", label="post_import_refseq")
        
        ready_files = find_ready_to_merge_files(ena_project_dir, verbose)

        updated_data, deleted_data, substituted_data, critical_unmatched, critical_duplicates = apply_ready_to_merge_updates(
            destination_data, ready_files, verbose
        )
        _debug_run_accession_status(updated_data, "run_metadata_collation", "post_ready_to_merge_updates")
        _debug_specific_samples(updated_data, "run_metadata_collation", label="post_ready_to_merge_updates")

        # Import KlebNET-GSP metadata
        updated_data = import_klebnet_metadata(updated_data, KLEBNET_METADATA_FILE, output_dir)
        _debug_run_accession_status(updated_data, "run_metadata_collation", "post_import_klebnet")
        _debug_specific_samples(updated_data, "run_metadata_collation", label="post_import_klebnet")

        # Add is_refseq and is_nctc boolean flags based on study_accession
        # This is done after all substitutions and imports are complete
        updated_data['is_refseq'] = updated_data['study_accession'] == 'Refseq_collection'
        updated_data['is_nctc'] = updated_data['study_accession'] == 'NCTC_collection'

        refseq_count = updated_data['is_refseq'].sum()
        nctc_count = updated_data['is_nctc'].sum()
        print("\nAdded boolean flags:")
        print(f"  is_refseq: {refseq_count} samples")
        print(f"  is_nctc: {nctc_count} samples")

        # Remove duplicate rows before saving (by sample_accession)
        if 'sample_accession' in updated_data.columns:
            rows_before_dedup = len(updated_data)
            samples_before_dedup = updated_data['sample_accession'].nunique()
            
            # Check for duplicates
            duplicate_counts = updated_data['sample_accession'].value_counts()
            duplicates = duplicate_counts[duplicate_counts > 1]
            
            if not duplicates.empty:
                print("\nFinal deduplication:")
                print(f"  Found {len(duplicates)} duplicate sample_accession(s) with {duplicates.sum()} total rows")
                updated_data = updated_data.drop_duplicates(subset='sample_accession', keep='first')
                rows_removed = rows_before_dedup - len(updated_data)
                samples_after_dedup = updated_data['sample_accession'].nunique()
                print(f"  Removed {rows_removed} duplicate rows")
                print(f"  Rows: {rows_before_dedup} → {len(updated_data)}")
                print(f"  Unique samples: {samples_before_dedup} → {samples_after_dedup}")
            else:
                print("\nFinal deduplication: No duplicates found - all sample_accession values are unique")
        _debug_run_accession_status(updated_data, "run_metadata_collation", "before_write_outputs")
        _debug_specific_samples(updated_data, "run_metadata_collation", label="before_write_outputs")

        # Analyze completeness for logging purposes (not saved to file)
        analyze_completeness(deleted_data, substituted_data)
        
        write_outputs(updated_data, output_dir)

        # If we reach here, no critical errors occurred
        if not ready_files:
            print("No ready_to_merge files found; destination data written unchanged.")
        else:
            print("Metadata collation complete.")
    finally:
        # Restore stdout and close log file
        sys.stdout = original_stdout
        tee_output.close()
        print(f"Log file written to: {log_file_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Collate ENA metadata by merging ready_to_merge files into collated metadata'
    )
    
    # All arguments are optional with defaults defined in function signatures
    parser.add_argument(
        '--metadata-file1',
        type=str,
        default=ENA_METADATA_FILE1,
        help=f'Path to first ENA metadata TSV file (default: {ENA_METADATA_FILE1})'
    )
    parser.add_argument(
        '--metadata-file2',
        type=str,
        default=ENA_METADATA_FILE2,
        help=f'Path to second ENA metadata TSV file (default: {ENA_METADATA_FILE2})'
    )
    parser.add_argument(
        '--metadata-file3',
        type=str,
        default=ENA_METADATA_FILE3,
        help=f'Path to third ENA metadata TSV file (default: {ENA_METADATA_FILE3})'
    )
    parser.add_argument(
        '--ena-project-dir',
        type=str,
        default=ENA_PROJECT_DIR,
        help=f'Directory containing ready_to_merge files (default: {ENA_PROJECT_DIR})'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=OUTPUT_DIR,
        help=f'Directory to write output files (default: {OUTPUT_DIR})'
    )
    parser.add_argument(
        '--study-metadata-file',
        type=str,
        default=STUDY_METADATA_FILE,
        help=f'Path to study-level metadata CSV file (default: None, uses Google Sheet {STUDY_METADATA_GOOGLE_SHEET_ID} sheet "{STUDY_METADATA_SHEET_NAME}")'
    )
    parser.add_argument(
        '--filter-study-size',
        type=int,
        default=131,
        help='Maximum study size (unique samples) for unreviewed studies. Studies with metadata_reviewed=False and size > filter_study_size will be removed (default: 131)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed file reading messages (default: False)'
    )
    
    args = parser.parse_args()
    
    run_metadata_collation(
        metadata_file1=args.metadata_file1,
        metadata_file2=args.metadata_file2,
        metadata_file3=args.metadata_file3,
        ena_project_dir=args.ena_project_dir,
        output_dir=args.output_dir,
        study_metadata_file=args.study_metadata_file,
        filter_study_size=args.filter_study_size,
        verbose=args.verbose,
    )

