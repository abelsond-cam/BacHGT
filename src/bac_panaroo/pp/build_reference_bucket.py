"""Build the reference_bucket.tsv that defines which RefSeqs are attached to every Panaroo batch.

Default bucket sources:
  - is_mgh78578 == True
  - is_complete_norway_genome == True
  - HS11286 (Sample == "GCF_000240185.1")

Output: TSV with header ``Sample`` (one Sample ID per line). Default path on HPC:
``<DATA_ROOT>/final/reference_bucket.tsv``.

Run::

    uv run python src/bac_panaroo/pp/build_reference_bucket.py
    uv run python src/bac_panaroo/pp/build_reference_bucket.py --add-sample GCF_000XXXXXX.1

The bucket file is read by ``panaroo_metadata_batching.py`` at batching time. If
the file is missing, that script falls back to mgh78578 alone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_METADATA = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_final_curated_slimmed.tsv"
)
DEFAULT_OUTPUT = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/reference_bucket.tsv"
)
HS11286_SAMPLE_ID = "GCF_000240185.1_ASM24018v2_genomic"


def _as_bool(series: pd.Series) -> pd.Series:
    """Coerce a possibly-string boolean column to clean bool, NaN→False."""
    if series.dtype == object:
        return series.map(
            lambda x: (
                str(x).strip().lower() in ("true", "1", "yes", "t")
                if pd.notna(x) and str(x).strip() != ""
                else False
            )
        )
    return series.fillna(False).astype(bool)


def build_bucket(
    metadata_path: Path,
    extra_samples: list[str] | None = None,
) -> pd.DataFrame:
    """Read metadata, return DataFrame with one row per bucket Sample (and rich diagnostic columns)."""
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Metadata not found: {metadata_path}")

    meta = pd.read_csv(metadata_path, sep="\t", low_memory=False)
    if "Sample" not in meta.columns:
        raise ValueError(f"'Sample' column not in metadata: {metadata_path}")

    # Optional flags — tolerant of missing columns.
    has_mgh = "is_mgh78578" in meta.columns
    has_norway = "is_complete_norway_genome" in meta.columns
    if not has_mgh:
        raise ValueError("metadata is missing column 'is_mgh78578'")

    mgh_mask = _as_bool(meta["is_mgh78578"])
    norway_mask = (
        _as_bool(meta["is_complete_norway_genome"])
        if has_norway
        else pd.Series(False, index=meta.index)
    )
    hs11286_mask = meta["Sample"].astype(str).eq(HS11286_SAMPLE_ID)

    extras = set(extra_samples or [])
    extra_mask = meta["Sample"].astype(str).isin(extras) if extras else pd.Series(
        False, index=meta.index
    )

    bucket_mask = mgh_mask | norway_mask | hs11286_mask | extra_mask

    # Validation
    n_mgh = int(mgh_mask.sum())
    n_norway = int(norway_mask.sum())
    n_hs = int(hs11286_mask.sum())

    print(f"Metadata rows: {len(meta):,}")
    print(f"  is_mgh78578=True:                 {n_mgh}")
    print(f"  is_complete_norway_genome=True:   {n_norway}")
    print(f"  Sample == {HS11286_SAMPLE_ID!r}:  {n_hs}")
    if extras:
        n_extra_found = int(extra_mask.sum())
        print(f"  --add-sample matches:             {n_extra_found}/{len(extras)}")
        missing_extras = sorted(extras - set(meta.loc[extra_mask, "Sample"].astype(str)))
        if missing_extras:
            print(f"  WARNING: --add-sample IDs not in metadata: {missing_extras}")

    if n_mgh != 1:
        raise ValueError(f"expected exactly 1 is_mgh78578 row, got {n_mgh}")
    if n_norway < 1:
        raise ValueError("no is_complete_norway_genome rows found in metadata")
    if n_hs == 0:
        raise ValueError(
            f"HS11286 ({HS11286_SAMPLE_ID}) not found in metadata. "
            "If the canonical Sample ID differs, pass it via --add-sample and "
            "let me know so we can update HS11286_SAMPLE_ID."
        )

    bucket = meta.loc[bucket_mask].copy()
    # Deduplicate on Sample in case the metadata itself has duplicates.
    bucket = bucket.drop_duplicates(subset=["Sample"], keep="first")

    return bucket


def write_bucket(bucket: pd.DataFrame, output_path: Path) -> None:
    """Write bucket Sample IDs to TSV (single-column, ``Sample`` header)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out = bucket[["Sample"]].copy()
    out.to_csv(output_path, sep="\t", index=False)
    print(f"\nWrote bucket TSV: {output_path}  (n={len(out)})")


def summarise(bucket: pd.DataFrame) -> None:
    """Print per-species and per-source breakdown of the bucket."""
    print(f"\nBucket size: {len(bucket)}")

    # Per-source breakdown (a single sample can satisfy multiple sources)
    print("\nPer-source counts (overlapping):")
    if "is_mgh78578" in bucket.columns:
        print(f"  mgh78578:           {int(_as_bool(bucket['is_mgh78578']).sum())}")
    if "is_complete_norway_genome" in bucket.columns:
        print(
            f"  Norway-completes:   {int(_as_bool(bucket['is_complete_norway_genome']).sum())}"
        )
    print(f"  HS11286:            {int(bucket['Sample'].astype(str).eq(HS11286_SAMPLE_ID).sum())}")

    # Per-species breakdown
    if "species" in bucket.columns:
        print("\nPer-species counts:")
        for species, count in bucket["species"].fillna("(unknown)").value_counts().items():
            print(f"  {species:<60s} {count:>4d}")

    # Per-Sublineage breakdown for KP rows
    if "Sublineage" in bucket.columns and "species" in bucket.columns:
        kp_rows = bucket[bucket["species"] == "Klebsiella pneumoniae"]
        if not kp_rows.empty:
            print("\nKlebsiella pneumoniae bucket members per Sublineage (top 20):")
            sl_counts = kp_rows["Sublineage"].fillna("(none)").value_counts()
            for sl, n in sl_counts.head(20).items():
                print(f"  {sl:<20s} {n:>4d}")
            if len(sl_counts) > 20:
                print(f"  ... ({len(sl_counts) - 20} more SLs)")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(
        description="Build reference_bucket.tsv for Panaroo batching."
    )
    p.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument(
        "--add-sample",
        action="append",
        default=[],
        help="Extra Sample ID to include in the bucket. Repeatable.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the bucket and summary; do not write the TSV.",
    )
    args = p.parse_args(argv)

    try:
        bucket = build_bucket(args.metadata, extra_samples=args.add_sample)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summarise(bucket)

    if args.dry_run:
        print("\n(--dry-run set; not writing TSV)")
        return 0

    write_bucket(bucket, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
