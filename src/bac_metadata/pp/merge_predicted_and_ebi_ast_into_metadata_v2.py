#!/usr/bin/env python3
"""Merge Bacformer-predicted AST + EBI ground-truth AST into metadata_v2.

For each panel drug, adds three columns to v2:

* ``predicted_<drug>_AST``       — ``"R"`` / ``"S"`` / ``NaN`` (Bacformer call at
  the drug's Youden-J operating threshold, chosen on validation; NaN for any
  sample outside ``kpsc_final_list`` or missing an embedding).
* ``predicted_<drug>_AST_prob``  — float in ``[0, 1]`` (raw positive-class
  probability from the fine-tuned head).
* ``EBI_<drug>_AST``             — ``"R"`` / ``"S"`` / ``NaN`` (curated truth from
  EBI / publication metadata, translated from the 1/0/NaN binary encoding).

Inputs:
  * ``metadata_v2_all_samples_and_columns.tsv`` (v2; ``Sample`` column).
  * BacPredict's ``processed/train_kleb_ast/predictions_for_metadata/<drug>.parquet``
    (output of ``src/kleb_ast/scripts/predict_amr_panel_on_slurm.sh``;
    columns: ``Sample``, ``predicted_<drug>_AST_prob``, ``predicted_<drug>_AST``).
  * BacPredict's ``processed/train_kleb_ast/binary_ast.csv`` (EBI source —
    1/0/NaN per drug, keyed by ``phenotype-BioSample_ID`` which is renamed to
    ``Sample`` here before the join).

A drug missing its parquet (Stage C didn't produce a checkpoint, or the
prediction array task failed) is logged and skipped — the merge is idempotent
and can be re-run after the missing drug is fixed.

Backs up the existing v2 TSV with a UTC-stamped ``.bak.<UTC>.tsv`` before
overwriting.

Usage::

    uv run python -m bac_metadata.pp.merge_predicted_and_ebi_ast_into_metadata_v2 --dry-run
    uv run python -m bac_metadata.pp.merge_predicted_and_ebi_ast_into_metadata_v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─── PATHS + CONSTANTS ────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_PREDICTIONS_DIR = DATA_ROOT / "david/processed/train_kleb_ast/predictions_for_metadata"
DEFAULT_EBI_BINARY_CSV = DATA_ROOT / "david/processed/train_kleb_ast/binary_ast.csv"

# Panel order matches BacPredict's eval / predict SLURM scripts.
DRUG_PANEL: tuple[str, ...] = (
    "gentamicin", "ceftazidime", "meropenem", "ciprofloxacin",
    "trimethoprim-sulfamethoxazole", "amikacin", "ceftriaxone",
    "piperacillin-tazobactam", "cefoxitin", "aztreonam", "cefazolin",
    "tobramycin", "cefepime", "imipenem", "levofloxacin", "cefotaxime",
    "cefuroxime", "ampicillin-sulbactam", "ertapenem", "tetracycline",
    "azithromycin", "colistin",
)

# EBI source uses BioSample as its sample key; map to v2's "Sample" before join.
EBI_SAMPLE_COL = "phenotype-BioSample_ID"


# ─── HELPERS ──────────────────────────────────────────────────────────────────


def _binary_to_rs(value: object) -> object:
    """Translate ``1``/``0``/NaN binary AST to ``"R"``/``"S"``/NaN."""
    if value is None:
        return np.nan
    try:
        if pd.isna(value):
            return np.nan
    except (TypeError, ValueError):
        pass
    try:
        return "R" if int(value) == 1 else "S"
    except (TypeError, ValueError):
        return np.nan


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ─── MAIN MERGE ───────────────────────────────────────────────────────────────


def merge_predictions(
    meta: pd.DataFrame,
    predictions_dir: Path,
    panel: tuple[str, ...],
) -> tuple[pd.DataFrame, dict]:
    """Left-join each ``<drug>.parquet`` onto ``meta`` keyed by ``Sample``.

    Drops any pre-existing ``predicted_<drug>_*`` columns first so the merge is
    idempotent (re-running this script doesn't pile up ``_x``/``_y`` suffixes).
    """
    stats: dict[str, list[str]] = {"drugs_added": [], "drugs_missing": []}
    for drug in panel:
        parquet_path = predictions_dir / f"{drug}.parquet"
        if not parquet_path.exists():
            stats["drugs_missing"].append(drug)
            continue
        pred = pd.read_parquet(parquet_path)
        expected = {"Sample", f"predicted_{drug}_AST_prob", f"predicted_{drug}_AST"}
        missing_cols = expected - set(pred.columns)
        if missing_cols:
            print(f"WARN: {parquet_path} missing columns {sorted(missing_cols)}; skipping {drug}", file=sys.stderr)
            stats["drugs_missing"].append(drug)
            continue
        pred["Sample"] = pred["Sample"].astype(str)
        drop = [c for c in (f"predicted_{drug}_AST_prob", f"predicted_{drug}_AST") if c in meta.columns]
        if drop:
            meta = meta.drop(columns=drop)
        meta = meta.merge(
            pred[["Sample", f"predicted_{drug}_AST_prob", f"predicted_{drug}_AST"]],
            on="Sample",
            how="left",
        )
        stats["drugs_added"].append(drug)
    return meta, stats


def merge_ebi(
    meta: pd.DataFrame,
    ebi_csv: Path,
    panel: tuple[str, ...],
) -> tuple[pd.DataFrame, dict]:
    """Translate ``binary_ast.csv`` 1/0/NaN to R/S strings and left-join onto ``meta``."""
    if not ebi_csv.exists():
        raise SystemExit(f"EBI binary AST CSV not found: {ebi_csv}")
    ebi = pd.read_csv(ebi_csv)
    if EBI_SAMPLE_COL not in ebi.columns:
        raise SystemExit(f"EBI CSV missing expected sample column: {EBI_SAMPLE_COL!r}")
    ebi = ebi.rename(columns={EBI_SAMPLE_COL: "Sample"})
    ebi["Sample"] = ebi["Sample"].astype(str)

    stats: dict[str, list[str]] = {"drugs_added": [], "drugs_missing": []}
    for drug in panel:
        if drug not in ebi.columns:
            stats["drugs_missing"].append(drug)
            continue
        col = f"EBI_{drug}_AST"
        per_drug = ebi[["Sample", drug]].copy()
        per_drug[col] = per_drug[drug].apply(_binary_to_rs)
        per_drug = per_drug[["Sample", col]]
        if col in meta.columns:
            meta = meta.drop(columns=[col])
        meta = meta.merge(per_drug, on="Sample", how="left")
        stats["drugs_added"].append(drug)
    return meta, stats


def main() -> None:  # noqa: D401
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metadata-tsv", type=Path, default=DEFAULT_METADATA_V2)
    p.add_argument("--predictions-dir", type=Path, default=DEFAULT_PREDICTIONS_DIR)
    p.add_argument("--ebi-binary-ast-csv", type=Path, default=DEFAULT_EBI_BINARY_CSV)
    p.add_argument("--out-tsv", type=Path, default=None, help="Output path. Default: overwrite the input TSV.")
    p.add_argument("--dry-run", action="store_true", help="Skip the on-disk write; print stats only.")
    args = p.parse_args()

    out_tsv = args.out_tsv or args.metadata_tsv

    print(f"Reading metadata_v2: {args.metadata_tsv}")
    meta = pd.read_csv(args.metadata_tsv, sep="\t", low_memory=False, dtype={"Sample": str})
    print(f"  rows: {len(meta):,}  cols (before): {len(meta.columns):,}")

    print(f"Merging predictions from {args.predictions_dir}/")
    meta, pred_stats = merge_predictions(meta, args.predictions_dir, DRUG_PANEL)
    print(f"  added {len(pred_stats['drugs_added'])} drug(s); missing: {pred_stats['drugs_missing'] or 'none'}")

    print(f"Merging EBI ground truth from {args.ebi_binary_ast_csv}")
    meta, ebi_stats = merge_ebi(meta, args.ebi_binary_ast_csv, DRUG_PANEL)
    print(f"  added {len(ebi_stats['drugs_added'])} drug(s); missing: {ebi_stats['drugs_missing'] or 'none'}")

    print(f"  cols (after):  {len(meta.columns):,}")

    if args.dry_run:
        print("Dry-run: skipping write.")
        return

    if out_tsv.exists():
        backup = out_tsv.with_suffix(f".bak.{_utc_stamp()}.tsv")
        out_tsv.rename(backup)
        print(f"Backed up existing TSV → {backup}")

    print(f"Writing {out_tsv}")
    meta.to_csv(out_tsv, sep="\t", index=False)
    print(f"DONE  shape: {meta.shape}")


if __name__ == "__main__":
    main()
