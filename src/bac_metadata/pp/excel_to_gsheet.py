"""
Export all sheets from the klebsiella_qc.xlsx Excel file to a new Google Sheets document.

This script reads all sheets from the large QC Excel file and creates a new
Google Sheets document with the same structure, making it easier to work with
the data in a collaborative cloud environment.

Usage (from repo root):
    uv run Klebsiella/pp/excel_to_gsheet.py

Requirements:
    - Google Cloud project with Sheets API and Drive API enabled
    - OAuth credentials file (client_secret*.json)
    - First run will open a browser for authentication
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

try:
    from bac_metadata.pp.metadata_collation import QC_EXCEL_FILE
except Exception as exc:
    print("ERROR: Could not import QC_EXCEL_FILE from metadata_collation.")
    print(f"Import error: {type(exc).__name__}: {exc}")
    sys.exit(1)

# Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Target Google Drive folder ID (from the provided URL)
DRIVE_FOLDER_ID = "1mdiSVEniLb07NDbyHnH_pYL4DgPvIAHq"

# Path to credentials file
CREDENTIALS_FILE = Path("/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/raw/google/client_secret_766063885615-5r4chm0o2635kqjc2fe18coak2a70ugc.apps.googleusercontent.com.json")

# Token file will be saved in the same directory as this script
TOKEN_FILE = Path(__file__).parent / "token.json"


def authenticate_google() -> Any:
    """
    Authenticate with Google and return credentials.
    
    On first run, this will open a browser window for OAuth authentication.
    Subsequent runs will use the saved token.json file.
    """
    creds = None
    
    # Check if we have a saved token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If there are no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: Credentials file not found: {CREDENTIALS_FILE}")
                print("\nPlease ensure you have downloaded the OAuth credentials from Google Cloud Console")
                print("and updated the CREDENTIALS_FILE path in this script.")
                sys.exit(1)
            
            print("Starting OAuth authentication flow...")
            print("A browser window will open for authentication.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for next run
        TOKEN_FILE.write_text(creds.to_json())
        print(f"Credentials saved to {TOKEN_FILE}")
    
    return creds


def load_excel_sheets(excel_path: str) -> dict[str, pd.DataFrame]:
    """Load all sheets from the Excel file into a dictionary of DataFrames."""
    print(f"\nLoading Excel file: {excel_path}")
    
    try:
        # Get all sheet names first
        excel_file = pd.ExcelFile(excel_path)
        sheet_names = excel_file.sheet_names
        print(f"Found {len(sheet_names)} sheets: {', '.join(sheet_names)}")
        
        # Load each sheet
        sheets_data = {}
        for sheet_name in sheet_names:
            print(f"  Loading sheet: {sheet_name}")
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            sheets_data[sheet_name] = df
            print(f"    Rows: {len(df)}, Columns: {len(df.columns)}")
        
        return sheets_data
    
    except FileNotFoundError:
        print(f"ERROR: Excel file not found: {excel_path}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to read Excel file: {type(exc).__name__}: {exc}")
        sys.exit(1)


def create_google_sheet(
    creds: Any,
    title: str,
    folder_id: str,
    sheets_data: dict[str, pd.DataFrame],
) -> str:
    """
    Create a new Google Sheets document with multiple sheets and upload data.
    
    Returns the URL of the created Google Sheet.
    """
    print(f"\nCreating Google Sheets document: '{title}'")
    
    # Build the Sheets API service
    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    
    # Create a new spreadsheet
    spreadsheet_body = {
        "properties": {"title": title},
        "sheets": [],
    }
    
    # Add a sheet for each DataFrame (first sheet will be created by default)
    sheet_names = list(sheets_data.keys())
    for i, sheet_name in enumerate(sheet_names):
        spreadsheet_body["sheets"].append({
            "properties": {
                "sheetId": i,
                "title": sheet_name,
            }
        })
    
    spreadsheet = (
        sheets_service.spreadsheets()
        .create(body=spreadsheet_body)
        .execute()
    )
    
    spreadsheet_id = spreadsheet["spreadsheetId"]
    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    print(f"Created spreadsheet: {spreadsheet_url}")
    
    # Move the spreadsheet to the specified folder
    print(f"Moving to folder: {folder_id}")
    file = drive_service.files().get(fileId=spreadsheet_id, fields="parents").execute()
    previous_parents = ",".join(file.get("parents", []))
    
    drive_service.files().update(
        fileId=spreadsheet_id,
        addParents=folder_id,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()
    print("Moved to target folder successfully")
    
    # Resize and upload data to each sheet
    print("\nResizing and uploading data to sheets...")
    for i, (sheet_name, df) in enumerate(sheets_data.items()):
        print(f"  Processing sheet: {sheet_name}")
        # Resize the sheet to fit the data (with some buffer)
        resize_sheet(sheets_service, spreadsheet_id, i, sheet_name, df)
        # Upload the data
        upload_dataframe_to_sheet(sheets_service, spreadsheet_id, sheet_name, df)
    
    print("\n" + "=" * 70)
    print("✓ SUCCESS! All sheets exported to Google Sheets")
    print("=" * 70)
    print(f"\nGoogle Sheets URL: {spreadsheet_url}")
    print(f"Total sheets: {len(sheets_data)}")
    print("=" * 70)
    
    return spreadsheet_url


def resize_sheet(
    sheets_service: Any,
    spreadsheet_id: str,
    sheet_id: int,
    sheet_name: str,
    df: pd.DataFrame,
) -> None:
    """
    Resize a sheet to accommodate the data.
    
    Google Sheets are created with default dimensions (typically 1000 rows x 26 columns).
    This function resizes the sheet to fit the data with a small buffer.
    """
    # Calculate required dimensions (data + header + buffer)
    required_rows = len(df) + 1 + 100  # data + header + 100 row buffer
    required_cols = len(df.columns) + 5  # columns + 5 column buffer
    
    print(f"    Resizing to {required_rows} rows x {required_cols} columns")
    
    request = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "rowCount": required_rows,
                            "columnCount": required_cols,
                        }
                    },
                    "fields": "gridProperties(rowCount,columnCount)"
                }
            }
        ]
    }
    
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=request
    ).execute()


def upload_dataframe_to_sheet(
    sheets_service: Any,
    spreadsheet_id: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> None:
    """
    Upload a pandas DataFrame to a specific sheet in the Google Sheets document.
    
    Uploads data in batches to avoid timeout and size limit issues with large datasets.
    """
    
    # Convert DataFrame to list of lists (including header)
    # Replace NaN with empty string for Google Sheets
    df_clean = df.fillna("")
    
    # Convert all datetime columns to strings to avoid JSON serialization issues
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            df_clean[col] = df_clean[col].astype(str)
    
    # Prepare the data with headers
    headers = [df_clean.columns.tolist()]
    data_rows = df_clean.values.tolist()
    
    # Convert any remaining non-serializable objects to strings
    headers = [[str(cell) if not isinstance(cell, (str, int, float, bool, type(None))) else cell 
                for cell in row] for row in headers]
    data_rows = [[str(cell) if not isinstance(cell, (str, int, float, bool, type(None))) else cell 
                  for cell in row] for row in data_rows]
    
    # Upload in batches to avoid timeouts (5000 rows at a time)
    BATCH_SIZE = 5000
    total_rows = len(data_rows)
    
    # First, upload headers
    body = {"values": headers}
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()
    
    # Then upload data in batches
    if total_rows == 0:
        print(f"    Uploaded 0 rows (headers only), {len(df.columns)} columns")
        return
    
    num_batches = (total_rows + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division
    
    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_rows)
        batch_data = data_rows[start_idx:end_idx]
        
        # Calculate the starting row in Google Sheets (row 2 is first data row, row 1 is headers)
        start_row = start_idx + 2
        
        body = {"values": batch_data}
        
        try:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A{start_row}",
                valueInputOption="RAW",
                body=body,
            ).execute()
            
            if num_batches > 1:
                print(f"      Batch {batch_idx + 1}/{num_batches}: rows {start_idx + 1}-{end_idx}")
        except Exception as e:
            print(f"      ERROR in batch {batch_idx + 1}: {e}")
            print(f"      Retrying batch {batch_idx + 1}...")
            # Retry once
            try:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A{start_row}",
                    valueInputOption="RAW",
                    body=body,
                ).execute()
                print(f"      ✓ Retry successful for batch {batch_idx + 1}")
            except Exception as retry_e:
                print(f"      ✗ Retry failed for batch {batch_idx + 1}: {retry_e}")
                raise
    
    print(f"    ✓ Uploaded {total_rows} rows, {len(df.columns)} columns")


def main() -> None:
    """Main execution function."""
    print("=" * 70)
    print("Excel to Google Sheets Export Tool")
    print("=" * 70)
    
    # Step 1: Authenticate with Google
    print("\n[Step 1] Authenticating with Google...")
    creds = authenticate_google()
    print("✓ Authentication successful")
    
    # Step 2: Load Excel file
    print("\n[Step 2] Loading Excel file...")
    sheets_data = load_excel_sheets(QC_EXCEL_FILE)
    print(f"✓ Loaded {len(sheets_data)} sheets successfully")
    
    # Step 3: Create Google Sheets document and upload data
    print("\n[Step 3] Creating Google Sheets document...")
    title = "klebsiella_qc"  # Name of the new Google Sheets document
    spreadsheet_url = create_google_sheet(creds, title, DRIVE_FOLDER_ID, sheets_data)
    
    print("\n✓ Export completed successfully!")


if __name__ == "__main__":
    main()
