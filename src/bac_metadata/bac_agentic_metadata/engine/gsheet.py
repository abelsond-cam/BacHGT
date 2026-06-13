"""OneDrive-free Google Sheets reader for the engine.

Mirrors ``pp.metadata_collation._authenticate_google`` / ``_read_google_sheet`` but resolves the
OAuth ``client_secret`` from an environment variable (default under ``~/.config/bac_metadata/``)
rather than a OneDrive path, and caches the token there too. **Nothing is read from or written
to OneDrive.** Used at build time to read the live ``study_level`` and ``parsed_per_project``
tabs of the curation sheet — which are measurement targets, not the (frozen) train/val/test
partition.

David copies his ``client_secret_*.json`` to the configured path once; first run mints
``token.json`` via a local browser flow, and subsequent runs refresh it silently.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

#: Default config dir (override the credential with ``BAC_GOOGLE_CLIENT_SECRET``).
CONFIG_DIR = Path(os.environ.get("BAC_GOOGLE_CONFIG_DIR", Path.home() / ".config" / "bac_metadata"))


def _credentials_file() -> Path:
    """Resolve the OAuth client-secret path (env override, else the config-dir default)."""
    env = os.environ.get("BAC_GOOGLE_CLIENT_SECRET")
    return Path(env) if env else CONFIG_DIR / "client_secret.json"


def _token_file() -> Path:
    """Resolve the cached OAuth token path."""
    env = os.environ.get("BAC_GOOGLE_TOKEN")
    return Path(env) if env else CONFIG_DIR / "token.json"


def _authenticate():
    """Return valid Google OAuth credentials, minting/refreshing the cached token as needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_file = _token_file()
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            cred_file = _credentials_file()
            if not cred_file.exists():
                raise FileNotFoundError(
                    f"Google client secret not found: {cred_file}. Copy it there (off OneDrive) "
                    "or set BAC_GOOGLE_CLIENT_SECRET."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json())

    return creds


def read_tab(spreadsheet_id: str, tab: str) -> pd.DataFrame:
    """Read one tab of a Google Spreadsheet into a DataFrame (string-typed, header from row 1).

    Parameters
    ----------
    spreadsheet_id
        The spreadsheet ID from its URL.
    tab
        Worksheet/tab name to read.

    Returns
    -------
    pandas.DataFrame
        The tab's values, with the first row used as the header (short rows right-padded).
    """
    from googleapiclient.discovery import build

    creds = _authenticate()
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{tab}!A:ZZ")
        .execute()
    )
    values = result.get("values", [])
    if not values:
        raise ValueError(f"No data found in tab '{tab}'")

    headers = values[0]
    rows = [(row + [""] * (len(headers) - len(row)))[: len(headers)] for row in values[1:]]
    return pd.DataFrame(rows, columns=headers)
