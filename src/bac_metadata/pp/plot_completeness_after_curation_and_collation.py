#!/usr/bin/env python3
"""Reproduce the pre-/post-curation completeness figures for the grant, on metadata_v2.

This drives the original, proven plotting functions that live in ``metadata_curation.py``:

- ``plot_host_category_pre_and_post_curation``        — 3 panels: Human (own narrow axis)
  · Non-human hosts · Not-filled
- ``plot_isolation_source_category_pre_and_post_curation`` — Isolation sources + Not-filled
  (all hosts, and a human-hosts-only variant)
- ``plot_region_distribution_pre_and_post_curation``  — Regions + Not-filled

Each draws **pre-curation vs post-curation** bars per category, using the real
``*_category`` columns produced by the curation parser (NOT naive keyword matching).

- **Pre-curation** (lightblue) = the raw, *pre-collation* ENA metadata TSVs in
  ``raw/metadata`` (the three ENA exports production ingests), run through the same
  ``parse_*``/``categorise_*`` pipeline, aligned 1:1 to the cohort. This is the state before
  the study-by-study merge files / manual review were applied. (Cell values are whitespace-
  stripped exactly as the collation loader does — the r02 export pads every field, which would
  otherwise drop ~16k samples from the join.)
- **Post-curation** (steelblue) = the production ``metadata_v2`` table (curated + study
  reviewed), filtered to the KPSC final-list cohort.

So the gap between the two bars is exactly what curation + study review recovered.

Outputs are written under ``src/bac_metadata/visualisations`` as PNG + SVG + PDF (the SVG/PDF
are true vector graphics for the grant). Run on HPC (the data lives there) from the repo root:

    uv run python src/bac_metadata/pp/plot_completeness_after_curation_and_collation.py
"""

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Curation pipeline + the original pre/post plotting functions (package-qualified —
# metadata_curation imports from bac_metadata.pp.*, so it only resolves as a package module).
from bac_metadata.pp.metadata_curation import (
    categorise_host,
    categorise_isolation_source,
    categorise_region,
    parse_country,
    parse_host,
    parse_isolation_source,
    plot_host_category_pre_and_post_curation,
    plot_isolation_source_category_pre_and_post_curation,
    plot_region_distribution_pre_and_post_curation,
)

# Default HPC paths (this script runs where the data lives).
RAW_METADATA_DIR = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/metadata"
# The raw ENA inputs production collation ingests (metadata_collation.py: ENA_METADATA_FILE1-3).
# File 3 (bakrep extra-ENA) is small but contributes a few thousand cohort samples.
DEFAULT_RAW_FILES = [
    f"{RAW_METADATA_DIR}/ena_metadata_klebsiella_with_header_filtered.tsv",
    f"{RAW_METADATA_DIR}/ena_metadata_klebsiella_with_header_filtered_r02_format.20240801.tsv",
    f"{RAW_METADATA_DIR}/bakrep_klebsiella_genus_extra_ena_metadata.tsv",
]
DEFAULT_POST_FILE = (
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/"
    "metadata_v2_all_samples_and_columns.tsv"
)


def install_vector_savefig():
    """Patch ``plt.savefig`` so every ``*.png`` also writes a vector ``*.svg`` and ``*.pdf``.

    The plotting functions in ``metadata_curation.py`` only save PNG; this lets us get the
    grant-ready vector copies without editing that module.
    """
    orig_savefig = plt.savefig

    def savefig(fname, *args, **kwargs):
        orig_savefig(fname, *args, **kwargs)
        if isinstance(fname, (str, os.PathLike)) and str(fname).lower().endswith(".png"):
            base = str(fname)[:-4]
            vector_kwargs = {k: v for k, v in kwargs.items() if k != "dpi"}
            for ext in ("svg", "pdf"):
                orig_savefig(f"{base}.{ext}", *args, **vector_kwargs)

    plt.savefig = savefig


# Grant-facing wording for the two series (the shared plot functions hardcode
# "Pre-curation"/"Post-curation"; we remap at the matplotlib layer so metadata_curation.py
# is left untouched and its own main() keeps the original labels).
GRANT_LABELS = {"Pre-curation": "Raw ENA", "Post-curation": "Curated + reviewed"}


def install_grant_labels():
    """Patch bar legends + the host suptitle to use grant wording."""
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    orig_bar = Axes.bar

    def bar(self, *args, **kwargs):
        if kwargs.get("label") in GRANT_LABELS:
            kwargs["label"] = GRANT_LABELS[kwargs["label"]]
        return orig_bar(self, *args, **kwargs)

    Axes.bar = bar

    orig_suptitle = Figure.suptitle

    def suptitle(self, t, *args, **kwargs):
        if isinstance(t, str):
            t = t.replace("Pre- and Post-curation", "Raw ENA vs Curated + reviewed")
        return orig_suptitle(self, t, *args, **kwargs)

    Figure.suptitle = suptitle


def _as_bool(series):
    """Coerce a possibly-string flag column to a clean boolean mask."""
    if series.dtype == bool:
        return series.fillna(False)
    return series.isin([True, "True", "TRUE", "true", 1, "1", 1.0])


def load_and_normalize_raw(path):
    """Load a raw ENA TSV the same way ``metadata_collation.py`` does.

    Two normalizations matter, and both mirror the production collation loader:
    - Strip whitespace from **column names** (the r02 export has leading-space headers like
      `` host``), and fix the ``secondary_sample_accesion`` typo.
    - Strip whitespace from **cell values** (``_strip_cell_value`` in collation): EVERY cell in
      the r02 export carries trailing whitespace, so ``"SAMN123 "`` won't join to v2's ``"SAMN123"``
      and ``"human "`` won't parse — without this, ~16k samples silently fall out of the join.
    """
    df = pd.read_csv(path, sep="\t", low_memory=False, skipinitialspace=True)
    df.columns = [str(c).strip() for c in df.columns]
    # Strip the fields the join + parser depend on. (Targeted rather than all-columns: some
    # object columns hold mixed types, and these are the only ones whose padding bites.)
    strip_cols = ["sample_accession", "secondary_sample_accession", "run_accession",
                  "study_accession", "host", "country", "isolation_source", "collection_date"]
    for c in strip_cols:
        if c in df.columns:
            df[c] = df[c].map(lambda x: x.strip() or pd.NA if isinstance(x, str) else x)
    if "secondary_sample_accesion" in df.columns and "secondary_sample_accession" not in df.columns:
        df = df.rename(columns={"secondary_sample_accesion": "secondary_sample_accession"})
    return df


def load_raw_baseline(raw_files, cohort_keys):
    """Build the per-cohort-sample raw ENA baseline.

    Concatenates the raw ENA exports, coalesces run-level rows to one row per
    ``sample_accession`` (first non-null per field, as production does), then left-joins onto the
    cohort keys so the baseline is aligned 1:1 with the post cohort — cohort samples with no raw
    ENA record (orphan long-read assemblies) become all-NA rows, i.e. legitimately "Not-filled".
    """
    frames = []
    for path in raw_files:
        if not os.path.exists(path):
            sys.exit(f"ERROR: raw file not found: {path}")
        f = load_and_normalize_raw(path)
        print(f"  {os.path.basename(path)}: {len(f):,} rows")
        frames.append(f)
    raw = pd.concat(frames, ignore_index=True)
    raw = raw.dropna(subset=["sample_accession"])
    raw_unique = raw.groupby("sample_accession", as_index=False, sort=False).first()
    print(f"  concatenated: {len(raw):,} rows -> {len(raw_unique):,} unique samples (coalesced)")

    pre = cohort_keys.merge(raw_unique, on="sample_accession", how="left")
    covered = pre["host"].notna().sum() if "host" in pre.columns else 0
    has_any_raw = pre.drop(columns=["sample_accession"]).notna().any(axis=1).sum()
    print(f"  cohort rows with a raw ENA record: {has_any_raw:,} / {len(pre):,} "
          f"({len(pre) - has_any_raw:,} have none — long-read-only, NA in the baseline)")
    return pre


def run_curation_parser(df, verbose=False):
    """Run the parse + categorise steps so the raw baseline has ``*_category`` columns."""
    print(f"Running curation parser on {len(df):,} raw samples...")
    df = parse_host(df, verbose=verbose)
    df = categorise_host(df, verbose=verbose)
    df = parse_country(df, verbose=verbose)
    df = categorise_region(df, verbose=verbose)
    df = parse_isolation_source(df, verbose=verbose)
    df = categorise_isolation_source(df, verbose=verbose)
    print("Parser complete.")
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-files", nargs="+", default=DEFAULT_RAW_FILES,
                        help="Raw pre-collation ENA metadata TSV(s) — the 'Pre-curation' baseline")
    parser.add_argument("--post-file", default=DEFAULT_POST_FILE,
                        help="Post-curation metadata_v2 TSV")
    parser.add_argument("--cohort-flag", default="kpsc_final_list",
                        help="Boolean column in the post file to filter the cohort on")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent.parent / "visualisations"),
                        help="Directory for the figures")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    install_vector_savefig()
    install_grant_labels()
    print("=" * 70)
    print("Pre-/post-curation completeness — raw ENA (parsed)  vs  metadata_v2 (reviewed)")
    print("=" * 70)

    # --- Post-curation source: metadata_v2, filtered to the cohort ---
    print(f"\nLoading post-curation v2:\n  {args.post_file}")
    if not os.path.exists(args.post_file):
        sys.exit(f"ERROR: post file not found: {args.post_file}")
    post_df = pd.read_csv(args.post_file, sep="\t", low_memory=False)
    print(f"  {len(post_df):,} rows")
    if args.cohort_flag in post_df.columns:
        post_df = post_df[_as_bool(post_df[args.cohort_flag])].copy()
        print(f"  {len(post_df):,} rows after {args.cohort_flag}=True filter")
    else:
        print(f"  WARNING: cohort flag '{args.cohort_flag}' not found — using all rows")
    if "sample_accession" not in post_df.columns:
        sys.exit("ERROR: 'sample_accession' not in post file")

    # --- Pre-curation source: raw ENA TSVs, normalized + parsed, aligned to the cohort ---
    print("\nLoading raw pre-collation ENA metadata (the 'Pre-curation' baseline):")
    pre_df = load_raw_baseline(args.raw_files, post_df[["sample_accession"]].copy())
    pre_df = run_curation_parser(pre_df, verbose=False)

    # --- Plots (original pre/post functions; vector copies via patched savefig) ---
    print("\nWriting figures (PNG + SVG + PDF) to:", args.output_dir)
    plot_host_category_pre_and_post_curation(post_df, args.output_dir, df_pre_collation=pre_df)
    plot_isolation_source_category_pre_and_post_curation(post_df, args.output_dir, df_pre_collation=pre_df)
    plot_region_distribution_pre_and_post_curation(post_df, args.output_dir, df_pre_collation=pre_df)
    print("\nDone.")


if __name__ == "__main__":
    main()
