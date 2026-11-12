#!/usr/bin/env python3
"""Add ``qc_pass`` (+ ``qc_pass_source``) to metadata_v2 — ONE QC verdict for every species.

David, 2026-11-12: *"we just need to have qc_pass matched to biosample_accession and added to the v2 metadata.
The qc pass in the kpsc is effectively final_list. So we might make a single column for qc_pass and add true for
all final_list and all true in this data sheet."*

Rule, in order:

1. ``kpsc_final_list == True``                                       → ``qc_pass = True``  (source ``kpsc_final_list``)
2. the row's ``sample_accession`` is a ``biosample_accession`` of the non-KPSC QC sheet
   (``nonkpsc_oct_2026_contamination_with_qc.tsv``: CheckM2, het-SNP contamination, N50 / contigs / GC / size)
   → that sheet's ``qc_pass``  (source ``nonkpsc_oct_2026``). A biosample on more than one sheet row passes only
   if every row passes.
3. otherwise                                                          → ``qc_pass = False`` (source empty): not
   assessed — e.g. an off-final-list KPSC genome, or a non-KPSC row the sheet does not cover.

⛔ Every column is read and written as TEXT (``dtype=str``, no NA parsing), so the ~500 other columns round-trip
byte for byte: a pandas default read would turn integer columns with gaps into floats (``1`` → ``1.0``) and blank
cells into ``NaN`` in a table other projects read. The previous file is kept as ``<stem>.bak.<UTC>.tsv``.
⛔ Refuses if any sheet biosample matches no metadata row, or more than one — a join that loses or duplicates a
genome is how a QC verdict quietly lands on the wrong sample.

Usage::

    python -m bac_metadata.pp.merge_qc_pass_into_metadata_v2 --dry-run
    python -m bac_metadata.pp.merge_qc_pass_into_metadata_v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

import pandas as pd

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_SHEET = DATA_ROOT / "david/raw/nonkpsc_oct_2026_contamination_with_qc.tsv"
SHEET_SOURCE = "nonkpsc_oct_2026"


def _true(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def qc_pass_columns(v2: pd.DataFrame, sheet: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    """``(qc_pass "True"/"False", qc_pass_source, report)`` aligned to ``v2``'s index."""
    verdict = _true(sheet["qc_pass"]).groupby(sheet["biosample_accession"].astype(str).str.strip()).all()
    acc = v2["sample_accession"].astype(str).str.strip()
    hits = acc[acc.isin(verdict.index)]
    n_rows_per = hits.value_counts()
    unmatched = sorted(set(verdict.index) - set(hits))
    multi = sorted(n_rows_per[n_rows_per > 1].index)
    if unmatched or multi:
        raise SystemExit(f"FATAL: {len(unmatched)} sheet biosamples match no metadata row (e.g. {unmatched[:3]}), "
                         f"{len(multi)} match more than one (e.g. {multi[:3]})")  # fmt: skip
    final = _true(v2["kpsc_final_list"])
    on_sheet = acc.isin(verdict.index)
    sheet_pass = acc.map(verdict).fillna(False).astype(bool)
    qc = final | (on_sheet & sheet_pass)
    source = pd.Series("", index=v2.index)
    source[on_sheet] = SHEET_SOURCE
    source[final] = "kpsc_final_list"  # the KPSC curation wins where both apply
    report = {
        "n_rows": len(v2), "n_kpsc_final_list": int(final.sum()), "n_sheet_biosamples": len(verdict),
        "n_sheet_rows": len(sheet), "n_sheet_pass": int(verdict.sum()), "n_on_sheet_and_final_list": int((final & on_sheet).sum()),
        "n_qc_pass": int(qc.sum()), "n_not_assessed": int((~final & ~on_sheet).sum()),
    }  # fmt: skip
    return qc.map({True: "True", False: "False"}), source, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    v2 = pd.read_csv(args.metadata_v2, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    sheet = pd.read_csv(args.sheet, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    qc, source, report = qc_pass_columns(v2, sheet)
    for k, v in report.items():
        print(f"  {k:28s} {v:,}")
    by = pd.crosstab(v2["species"], qc)
    print(by[by.sum(axis=1) >= 50].to_string())
    if args.dry_run:
        print("dry run — nothing written")
        return 0
    out = v2.drop(columns=[c for c in ("qc_pass", "qc_pass_source") if c in v2.columns])
    pos = out.columns.get_loc("kpsc_final_list") + 1  # beside the KPSC verdict it generalises
    out.insert(pos, "qc_pass", qc)
    out.insert(pos + 1, "qc_pass_source", source)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    out.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"backup → {bak}\nwrote {args.metadata_v2}  rows={len(out):,}  cols={len(out.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
