r"""One-time patch — fold the agentic re-curation's uncategorised category tail into the canonical buckets.

The 2026-08-27 agentic combine introduced some raw paper values (clinical abbreviations, body-site codes, Latin
host names) that `pp/metadata_curation.py`'s categorise rules didn't yet map, so they passed through into the
`region` / `host_category` / `isolation_source_category` columns as small ad-hoc buckets. The rules have since
been extended (`categorise_region`/`categorise_host`/`categorise_isolation_source`), which fixes any FUTURE
rebuild — but the already-promoted v2 needs the landed values corrected in place.

Re-running the categorise functions wholesale is unsafe here: it would recompute the category from the parsed
column alone and so **undo** `reconcile_host_and_isolation_source`'s host←iso inference and its "unhelpful"
clearing. This module instead does a **targeted value remap** — it only rewrites cells whose current category
is one of the exact tail values below, leaving every other cell (and all of reconcile's work) untouched. The
maps mirror the rules added to `metadata_curation.py` on 2026-08-27.

    uv run python -m bac_metadata.bac_agentic_metadata.combine.recategorise_agentic_tail \
        --table <v2.tsv> --out <v2_recategorised.tsv>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_WOUND = "wound & pus, abscess, surgical drain, body tissue, bone, biopsy"
_SKIN = "skin swabs (skin, groin, vaginal, genital, eye, ear)"
_LAB = "lab, hospital or facility (unhelpful)"
_RESP = "lower respiratory, endotracheal"
_BODYFLUID = "body fluid (ascites / peritoneal / pleural)"

#: Exact category-value → canonical bucket, one map per category column. Only these values are rewritten;
#: genuinely ambiguous codes (MB, TASP, SS, BA, CHEST, "case from Ment. Gen. Hosp.") and host-in-iso mis-files
#: (domestic animals / wild animals / poultry livestock / wild birds / bovine / equine) are deliberately LEFT.
TAIL_MAPS: dict[str, dict[str, object]] = {
    "region": {
        "Saint Kitts and Nevis": "Central & S. America",
        "Middle East": "M. East, Central Asia",
    },
    "host_category": {
        "Galleria mellonella": "insect",
        "Caenorhabditis elegans": "insect",
        "hospital sink": "clinical environment or surface",
        "International Space Station": "clinical environment or surface",
        "Necrosyrtes monachus": "wild birds",
        "Larus spp.": "wild birds",
        "Phoca vitulina": "wild animals",
        "Fish": "wild animals",
        "wild carp": "wild animals",
    },
    "isolation_source_category": {
        "UTI": "urine", "URN": "urine",
        "UCATH": "urinary catheter",
        "SPUT": _RESP, "SPUTIN": _RESP, "HAP/VAP": _RESP,
        "CRBSI": "blood", "CRBISI": "blood", "BLUD": "blood", "C LINE": "blood",
        "cIAI": "invasive gut & organs", "CHOLANGITIS": "invasive gut & organs",
        "Cholangitis": "invasive gut & organs", "CHOLANGITIE": "invasive gut & organs",
        "EMPYEMA": _BODYFLUID,
        "SSTI": _WOUND, "WUND": _WOUND, "WS": _WOUND, "Eschar Fragment": _WOUND, "Fragment": _WOUND,
        "SEPTIC ARTHRITI": _WOUND, "RT TRUNK": _WOUND, "THIGH R": _WOUND, "RIGHT THIGH": _WOUND,
        "LT LOWER LIMB": _WOUND,
        "SCROTAL": _SKIN, "Super. swab": _SKIN,
        "Swab Retal": "faeces & rectal swabs", "bovine rumen": "faeces & rectal swabs",
        "Closet Equipment": "clinical environment or surface",
        "International Space Station": "clinical environment or surface",
        "Klebsiella pneumoniae microbiological culture": _LAB, "Biofilm culture": _LAB,
        "Bacterial culture": _LAB, "culture": _LAB, "new culture swab": _LAB, "lab": _LAB,
        "NO SOURCE": "",  # a null placeholder — blank it
    },
}


def recategorise_tail(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply :data:`TAIL_MAPS` to the three category columns; return ``(frame, {column: cells_changed})``."""
    out = df.copy()
    changed: dict[str, int] = {}
    for col, mapping in TAIL_MAPS.items():
        if col not in out.columns:
            continue
        hits = out[col].isin(mapping.keys())
        changed[col] = int(hits.sum())
        out.loc[hits, col] = out.loc[hits, col].map(mapping)
    return out, changed


def main() -> None:
    """Fold the agentic uncategorised category tail into canonical buckets (targeted value remap)."""
    p = argparse.ArgumentParser(description="Remap the agentic category tail into canonical buckets (one-time).")
    p.add_argument("--table", required=True, help="the table to patch (e.g. production v2)")
    p.add_argument("--out", required=True, help="where to write the patched table")
    args = p.parse_args()
    df = pd.read_csv(args.table, sep="\t", dtype=str, low_memory=False, keep_default_na=False)
    out, changed = recategorise_tail(df)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.fillna("").to_csv(args.out, sep="\t", index=False)
    for col, n in changed.items():
        print(f"[recategorise] {col}: {n} cells remapped", file=sys.stderr)
    print(f"[recategorise] wrote {args.out} ({len(out):,} rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
