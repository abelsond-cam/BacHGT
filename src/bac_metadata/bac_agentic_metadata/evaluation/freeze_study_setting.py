"""Freeze the live ``study_setting`` labels into a committed sidecar (reproducibility).

``study_setting`` is the one primary-check label missing from the frozen study-level snapshot
(``study_level_metadata_all_combined_v1.0_20260105.csv`` predates it). amr_study / cohort_age were
frozen there; study_setting lives only on the live Google ``study_level`` tab. Reading it live
makes validation non-reproducible and risks post-hoc leakage, so this snapshots it once, keyed by
``study_accession`` (the split key), into ``data/study_setting_frozen.tsv``.

Re-run only to deliberately refresh the freeze (needs the Google OAuth token; see ``engine.gsheet``):

    uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/freeze_study_setting.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.gsheet import read_tab

APP_DIR = Path(__file__).resolve().parents[1] / "applications" / "klebsiella"  # gold-bearing app tree (see evaluation/__init__.py)
DATA_DIR = APP_DIR / "data"
OUT_PATH = DATA_DIR / "inputs" / "study_setting_frozen.tsv"
SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"
ACCESSION_RE = re.compile(r"\bPRJ[A-Z]+\d+\b")


def main() -> None:
    """Read the live ``study_level`` tab and write the per-accession study_setting freeze."""
    df = read_tab(SHEET_ID, "study_level")
    setting_col = next((c for c in df.columns if "setting" in c.lower()), None)
    if setting_col is None:
        raise SystemExit(f"No study_setting column found (cols: {list(df.columns)})")

    rows = []
    for _, r in df.iterrows():
        value = str(r.get(setting_col, "")).strip().lower()
        if not value or value == "nan":
            continue
        for acc in ACCESSION_RE.findall(str(r.get("study_accessions", ""))):
            rows.append({"study_accession": acc, "study_setting": value})

    out = pd.DataFrame(rows).drop_duplicates("study_accession").sort_values("study_accession")
    out.to_csv(OUT_PATH, sep="\t", index=False)
    print(f"Wrote {OUT_PATH} ({len(out)} accessions): {out['study_setting'].value_counts().to_dict()}", file=sys.stderr)


if __name__ == "__main__":
    main()
