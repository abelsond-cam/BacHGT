"""
Standalone test script to verify Google Sheets and Drive API access using OAuth.

This script will:
1. Authenticate with your Google account
2. Create a test spreadsheet
3. Add some test data
4. Print the URL so you can verify it worked

Usage:
    uv run Klebsiella/pp/test_google_auth.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Path to credentials file
CREDENTIALS_FILE = Path("/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k/data/raw/google/client_secret_766063885615-5r4chm0o2635kqjc2fe18coak2a70ugc.apps.googleusercontent.com.json")

# Token file will be saved in the same directory as this script
TOKEN_FILE = Path(__file__).parent / "token.json"

# Target folder ID for the test
DRIVE_FOLDER_ID = "1mdiSVEniLb07NDbyHnH_pYL4DgPvIAHq"


def authenticate_google():
    """Authenticate with Google and return credentials."""
    creds = None
    
    # Check if we have a saved token
    if TOKEN_FILE.exists():
        print(f"Found existing token at: {TOKEN_FILE}")
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If there are no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: Credentials file not found: {CREDENTIALS_FILE}")
                sys.exit(1)
            
            print("Starting OAuth authentication flow...")
            print("A browser window will open for authentication.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for next run
        TOKEN_FILE.write_text(creds.to_json())
        print(f"✓ Credentials saved to {TOKEN_FILE}")
    else:
        print("✓ Using existing valid credentials")
    
    return creds


def test_google_apis():
    """Test Google Sheets and Drive API access."""
    print("=" * 70)
    print("Testing Google Sheets & Drive API Access")
    print("=" * 70)
    
    # Step 1: Authenticate
    print("\n[Step 1] Authenticating...")
    try:
        creds = authenticate_google()
        print("✓ Authentication successful!")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return False
    
    # Step 2: Build services
    print("\n[Step 2] Building API services...")
    try:
        sheets_service = build("sheets", "v4", credentials=creds)
        drive_service = build("drive", "v3", credentials=creds)
        print("✓ API services built successfully!")
    except Exception as e:
        print(f"✗ Failed to build API services: {e}")
        return False
    
    # Step 3: Create a test spreadsheet
    print("\n[Step 3] Creating test spreadsheet...")
    try:
        spreadsheet_body = {
            "properties": {"title": "TEST - Klebsiella API Access Test"},
            "sheets": [{"properties": {"title": "Test Sheet"}}]
        }
        
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body).execute()
        spreadsheet_id = spreadsheet["spreadsheetId"]
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        print(f"✓ Created test spreadsheet!")
        print(f"  URL: {spreadsheet_url}")
    except Exception as e:
        print(f"✗ Failed to create spreadsheet: {e}")
        return False
    
    # Step 4: Add some test data
    print("\n[Step 4] Adding test data...")
    try:
        values = [
            ["Column A", "Column B", "Column C"],
            ["Test 1", "Test 2", "Test 3"],
            ["Data 1", "Data 2", "Data 3"],
        ]
        body = {"values": values}
        
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Test Sheet!A1",
            valueInputOption="RAW",
            body=body,
        ).execute()
        print("✓ Test data added successfully!")
    except Exception as e:
        print(f"✗ Failed to add test data: {e}")
        return False
    
    # Step 5: Move to target folder
    print("\n[Step 5] Moving to target Google Drive folder...")
    try:
        file = drive_service.files().get(fileId=spreadsheet_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents", []))
        
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=DRIVE_FOLDER_ID,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()
        print(f"✓ Moved to target folder: {DRIVE_FOLDER_ID}")
    except Exception as e:
        print(f"✗ Failed to move to folder: {e}")
        print("  (The spreadsheet was still created, just not in the target folder)")
    
    # Success!
    print("\n" + "=" * 70)
    print("✓✓✓ ALL TESTS PASSED! ✓✓✓")
    print("=" * 70)
    print(f"\nTest spreadsheet created successfully:")
    print(f"  {spreadsheet_url}")
    print("\nYou can now run the full export script:")
    print("  uv run Klebsiella/pp/excel_to_gsheet.py")
    print("=" * 70)
    
    return True


if __name__ == "__main__":
    success = test_google_apis()
    sys.exit(0 if success else 1)
