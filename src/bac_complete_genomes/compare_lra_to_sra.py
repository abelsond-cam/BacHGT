#!/usr/bin/env python3
"""Per-clonal-group feature comparison: complete genomes (is_refseq) vs short reads.

Joins curated metadata with ISEScan per-sample counts, then for each epidemic CG,
pooled Rare_CGs, and all_samples, outputs p-value-sorted tables comparing cohorts.

Kleborate columns are handled by category:
  - Virulence biosynthetic clusters (ybt/clb/iuc/iro/rmp/rmpA2): reported as
    '{Lineage}_bsc' — the number of alleles detected per sample across the
    whole biosynthetic cluster (BSC). The locus_concordance column reports the
    fraction of samples where all BSC genes are either fully present or fully absent,
    indicating whether the cluster is acquired and lost as a unit. Use
    --full-virulence-output to also report individual alleles, STs, lineage strings,
    and spurious-hit columns.
  - Chromosomal MLST 7-locus alleles (gapA, infB, mdh, pgi, phoE, rpoB, tonB)
    and chromosomal ST: presence/absence. (Mean comparisons of allele IDs are
    biologically meaningless; the IDs are arbitrary labels.)
  - Acquired AMR (*_acquired): semicolon-delimited token counts.
  - ISEScan IS-family columns: numeric per-sample counts.
  - Curated stats (total_size, contig_count, N50, num_resistance_genes): numeric.
    virulence_score and resistance_score are excluded (composite/derived).

For Kleborate typing cells, "absent" means the cell is one of {'-', '0', '',
'NA', 'nan', 'None'}; any other content (allele integer, optionally annotated
with *, ^, ?, -X% truncation; lineage string; comma-separated multi-copy list;
ST integer) counts as present. This mirrors Kleborate's own behaviour: the
cell is populated only when minimap2 finds a hit passing that module's
identity/coverage thresholds, with NA->0 conversion in ST columns.

For binary (presence/absence) features the *_mean columns equal the cohort
detection rate. The pickup_ratio_pct column is 100 * complete_mean /
short_mean rounded to a whole percent: 100 means equal detection, >100 means
better detection in complete genomes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from bac_panaroo.tl.define_epidemic_cgs import (
    RARE_CGS_ROW,
    cg_unique_sample_counts,
    epidemic_labels_from_counts,
    rare_labels_from_counts,
)

DEFAULT_METADATA = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_final_curated_all_samples_and_columns.tsv"
)
DEFAULT_ISESCAN = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/isescan_analysis/"
    "isescan_family_cluster_counts_per_sample.csv"
)
DEFAULT_OUTPUT_DIR = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/complete_vs_sr_genomes")

EXPLICIT_NUMERIC = (
    "total_size",
    "contig_count",
    "N50",
    "num_resistance_genes",
)

# Kleborate summary scores — excluded from analysis (composite/derived, not raw features).
EXCLUDE_NUMERIC: frozenset[str] = frozenset({"virulence_score", "resistance_score"})

# ---------------------------------------------------------------------------
# Kleborate virulence module schema
# Read directly from each module's get_headers() in
# https://github.com/klebgenomics/Kleborate/tree/main/kleborate/modules
# ---------------------------------------------------------------------------
KLEBORATE_VIRULENCE_LOCI: dict[str, dict] = {
    "ybt": {
        "st": "YbST",
        "lineage": "Yersiniabactin",
        "alleles": ["ybtS", "ybtX", "ybtQ", "ybtP", "ybtA", "irp2", "irp1", "ybtU", "ybtT", "ybtE", "fyuA"],
        "spurious": "spurious_ybt_hits",
    },
    "clb": {
        "st": "CbST",
        "lineage": "Colibactin",
        "alleles": [
            "clbA",
            "clbB",
            "clbC",
            "clbD",
            "clbE",
            "clbF",
            "clbG",
            "clbH",
            "clbI",
            "clbL",
            "clbM",
            "clbN",
            "clbO",
            "clbP",
            "clbQ",
        ],
        "spurious": "spurious_clb_hits",
    },
    "iuc": {
        "st": "AbST",
        "lineage": "Aerobactin",
        "alleles": ["iucA", "iucB", "iucC", "iucD", "iutA"],
        "spurious": "spurious_abst_hits",
    },
    "iro": {
        "st": "SmST",
        "lineage": "Salmochelin",
        "alleles": ["iroB", "iroC", "iroD", "iroN"],
        "spurious": "spurious_smst_hits",
    },
    "rmp": {
        "st": "RmST",
        "lineage": "RmpADC",
        "alleles": ["rmpA", "rmpD", "rmpC"],
        "spurious": "spurious_rmst_hits",
    },
    "rmpA2": {
        "st": None,
        "lineage": None,
        "alleles": ["rmpA2"],
        "spurious": None,
    },
}

# Flattened list of every Kleborate virulence column we expect.
KLEBORATE_VIRULENCE_COLS: list[str] = []
for _info in KLEBORATE_VIRULENCE_LOCI.values():
    for _key in ("st", "lineage", "spurious"):
        if _info[_key]:
            KLEBORATE_VIRULENCE_COLS.append(_info[_key])
    KLEBORATE_VIRULENCE_COLS.extend(_info["alleles"])

# Kleborate KpSC chromosomal 7-locus MLST scheme + ST.
# Treated as presence/absence: mean of allele IDs is meaningless biologically,
# but failure to detect a housekeeping gene is a meaningful assembly artefact.
KLEBORATE_CHROMOSOMAL_MLST_COLS: list[str] = [
    "gapA",
    "infB",
    "mdh",
    "pgi",
    "phoE",
    "rpoB",
    "tonB",
]

# Strings that Kleborate uses to indicate "no detection". The multi_mlst
# function converts NA -> 0 in ST columns so 0 is treated as absent.
KLEBORATE_ABSENT_TOKENS: frozenset[str] = frozenset(
    {
        "-",
        "0",
        "0.0",
        "",
        "NA",
        "na",
        "nan",
        "None",
        "none",
    }
)

GAPA_START = "gapA"
VIRULENCE_END = "virulence_score"

OUTPUT_COLS = (
    "feature",
    "p_val_corr",
    "complete_vs_sr_ratio",
    "locus_concordance",
    "complete_genome_mean",
    "short_read_mean",
    "n_complete",
    "n_sr",
    "complete_sd",
    "sr_sd",
    "p_val",
)

PENETRANCE_OUTPUT_COLS = (
    "feature",
    "p_val_corr",
    "penetrance_ratio",
    "complete_penetrance",
    "sr_penetrance",
    "locus_concordance",
    "n_complete",
    "n_sr",
    "p_val",
)


def _fmt_sci_1dp(x: float) -> str:
    """Format p-values compactly, e.g. 3.2e-145."""
    if pd.isna(x):
        return ""
    return f"{float(x):.1e}"


def _round_3sig(x) -> str:
    """Format a float to 3 significant figures; empty string for NaN."""
    if pd.isna(x):
        return ""
    return f"{float(x):.3g}"


def _ratio(complete_mean, short_mean) -> str:
    """complete_mean / short_mean to 3 sig figs. Empty if undefined, 'inf' if short is 0."""
    if pd.isna(complete_mean) or pd.isna(short_mean):
        return ""
    if short_mean == 0:
        if complete_mean == 0:
            return ""
        return "inf"
    return f"{complete_mean / short_mean:.3g}"


def compute_locus_concordance(gene_series: list[pd.Series], index) -> float:
    """Fraction of samples where all locus genes are either all present or all absent.

    1.0 means perfectly concordant (genes always co-occur or co-absent).
    Values <1.0 indicate partial-locus samples (IS mid-cluster disruption,
    fragmented assembly, or genuine partial acquisition).
    """
    mat = pd.concat([s.loc[index] for s in gene_series], axis=1)
    n = len(mat)
    if n == 0:
        return np.nan
    n_genes = len(gene_series)
    row_sums = mat.sum(axis=1)
    n_concordant = ((row_sums == 0) | (row_sums == n_genes)).sum()
    return n_concordant / n


class _Tee:
    """Write stream output to both console and log file."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> int:
        for s in self._streams:
            s.write(data)
            s.flush()
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            s.flush()


# ---------------------------------------------------------------------------
# Kleborate cell parsing helpers
# ---------------------------------------------------------------------------


def kleborate_cell_present(val) -> bool:
    """True if a Kleborate cell records a detection.

    Treats any string outside KLEBORATE_ABSENT_TOKENS as a positive call -
    including imperfect-match annotations (15*, 15^, 15?, 15*-42%) and
    multi-copy comma-separated lists (e.g. 'rmpA_11(ICEKp1),rmpA_2(KpVP-1)').
    Mirrors Kleborate's own logic: it only writes a non-'-' value when
    minimap2 finds a hit above the module's identity/coverage thresholds.
    """
    if pd.isna(val):
        return False
    return str(val).strip() not in KLEBORATE_ABSENT_TOKENS


def kleborate_column_to_presence(series: pd.Series) -> pd.Series:
    """Return float Series of 0/1 indicating Kleborate detection per row."""
    return series.apply(kleborate_cell_present).astype(float)


# ---------------------------------------------------------------------------
# Existing helpers
# ---------------------------------------------------------------------------


def load_isescan_features(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Load ISEScan CSV; keep Sample + IS-family columns (names starting with 'IS')."""
    raw = pd.read_csv(path, low_memory=False)
    if raw.shape[1] < 4:
        raise ValueError(f"ISEScan CSV must have >= 4 columns: {path}")
    if "Sample" not in raw.columns:
        raw = raw.rename(columns={raw.columns[0]: "Sample"})
    candidate_cols = [str(c) for c in raw.columns[3:]]
    feature_cols = [c for c in candidate_cols if c.startswith("IS")]
    print("\n=== ISEScan Features ===")
    print(
        f"Loaded {len(feature_cols)} IS-family columns (from {len(candidate_cols)} candidates) in {path.name}",
    )
    return raw[["Sample"] + feature_cols].copy(), feature_cols


def merge_metadata_isescan(
    meta: pd.DataFrame,
    isesc: pd.DataFrame,
    isesc_feature_cols: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """Left-merge ISEScan on Sample; rename overlapping columns with __isescan suffix."""
    rename_map = {c: f"{c}__isescan" for c in isesc_feature_cols if c in meta.columns}
    if rename_map:
        print(f"Renaming {len(rename_map)} ISEScan columns to avoid conflicts: {list(rename_map.keys())[:5]}...")
    isesc = isesc.rename(columns=rename_map)
    merged_ise_cols = [rename_map.get(c, c) for c in isesc_feature_cols]
    merged = meta.merge(isesc, on="Sample", how="left")
    return merged, merged_ise_cols


def column_range_inclusive(cols: list[str], start: str, end: str) -> list[str]:
    """Return columns from start to end inclusive."""
    if start not in cols or end not in cols:
        return []
    i0, i1 = cols.index(start), cols.index(end)
    if i0 > i1:
        i0, i1 = i1, i0
    return cols[i0 : i1 + 1]


def acquired_column_names(columns: list[str]) -> list[str]:
    """Return column names ending with _acquired."""
    return sorted(c for c in columns if str(c).endswith("_acquired"))


def count_acquired_tokens(series: pd.Series) -> pd.Series:
    """Split by ';', count non-empty tokens."""

    def count_tokens(x):
        if pd.isna(x):
            return 0
        tokens = [t.strip() for t in str(x).split(";") if t.strip()]
        return len(tokens)

    return series.apply(count_tokens)


def safe_numeric_column(series: pd.Series, col_name: str, threshold: float = 0.05) -> pd.Series | None:
    """Convert to numeric; return None and log details if >threshold of non-NaN fail."""
    numeric = pd.to_numeric(series, errors="coerce")
    non_nan_original = series.notna().sum()
    failed_mask = series.notna() & numeric.isna()
    failed_count = failed_mask.sum()

    if non_nan_original > 0 and failed_count / non_nan_original > threshold:
        pct = 100 * failed_count / non_nan_original
        failed_samples = series[failed_mask].head(5).tolist()
        print(f"  SKIPPED '{col_name}': {failed_count}/{non_nan_original} ({pct:.1f}%) failed numeric conversion")
        print(f"    Sample failed values: {failed_samples}")
        return None
    return numeric


def compute_row_stats(feature_name: str, feature_vals: pd.Series, is_refseq: pd.Series) -> dict:
    """Return dict with p_val, means, sds for one feature."""
    complete = feature_vals[is_refseq]
    short = feature_vals[~is_refseq]

    complete_finite = complete.dropna()
    short_finite = short.dropna()

    if len(complete_finite) < 2 or len(short_finite) < 2:
        p_val = np.nan
    else:
        # If both groups have zero variance (e.g. binary feature absent in
        # both cohorts), ttest_ind returns nan with a RuntimeWarning. That's
        # the desired behaviour - the row will sort to the bottom.
        with np.errstate(invalid="ignore"):
            _, p_val = stats.ttest_ind(complete_finite, short_finite, equal_var=True)

    return {
        "feature": feature_name,
        "p_val": p_val,
        "complete_genome_mean": complete.mean(),
        "short_read_mean": short.mean(),
        "n_complete": len(complete_finite),
        "n_sr": len(short_finite),
        "complete_sd": complete.std(ddof=1),
        "sr_sd": short.std(ddof=1),
    }


def build_feature_data(
    merged: pd.DataFrame,
    ise_cols: list[str],
    full_virulence_output: bool = False,
) -> tuple[dict[str, pd.Series], dict[str, list[pd.Series]], list[str]]:
    """Build feature dict, locus_gene_map for concordance, and skipped list.

    Each virulence BSC is reported as '{Lineage}_bsc': presence/absence of the
    lineage column (0/1), so the mean equals the BSC detection rate. locus_gene_map
    maps each BSC feature to its per-allele presence Series so concordance (fraction
    of samples where all BSC alleles are co-present or co-absent) can be computed.

    Processing order:
      1. Explicit numeric scalars
      2. Kleborate virulence module columns -> presence/absence (1/0)
         [only when full_virulence_output=True]
      3. Kleborate virulence BSC features ('{Lineage}_bsc' by default,
         '{locus}_gene_count' when full_virulence_output=True)
      4. Kleborate chromosomal MLST columns -> presence/absence (1/0)
      5. Gene-range fallback (gapA -> virulence_score) -> safe_numeric
      6. *_acquired AMR columns -> token counts
      7. ISEScan IS-family columns -> numeric counts
    """
    features: dict[str, pd.Series] = {}
    locus_gene_map: dict[str, list[pd.Series]] = {}
    skipped: list[str] = []
    all_cols = list(merged.columns)

    print("\n=== Feature Processing ===")

    # 1. Explicit numeric columns
    print("\nExplicit numeric columns:")
    for col in EXPLICIT_NUMERIC:
        if col in merged.columns:
            numeric = pd.to_numeric(merged[col], errors="coerce")
            features[col] = numeric
            print(f"  + {col}: {numeric.notna().sum()} valid values")
        else:
            print(f"  - {col}: NOT FOUND in metadata")
            skipped.append(col)

    # 2. Kleborate virulence module columns -> presence/absence
    # Skipped in default mode; use --full-virulence-output to include individual
    # alleles, STs, lineage strings, and spurious-hit columns.
    if full_virulence_output:
        print(f"\nKleborate virulence columns: {len(KLEBORATE_VIRULENCE_COLS)} expected")
        v_added = v_missing = 0
        for col in KLEBORATE_VIRULENCE_COLS:
            if col in features:
                continue
            if col in merged.columns:
                features[col] = kleborate_column_to_presence(merged[col])
                v_added += 1
            else:
                v_missing += 1
                skipped.append(col)
        print(f"  Added (presence/absence): {v_added}, missing from metadata: {v_missing}")
        if v_added:
            for example in KLEBORATE_VIRULENCE_COLS:
                if example in merged.columns:
                    non_absent = int((features[example] == 1).sum())
                    absent = int((features[example] == 0).sum())
                    print(f"  Example '{example}': {non_absent} present, {absent} absent")
                    break
    else:
        print(
            "\nKleborate virulence columns: collapsed to BSC presence "
            "(use --full-virulence-output for individual alleles, STs, and spurious hits)"
        )

    # 3. Kleborate virulence BSC presence per locus.
    # Default: '{Lineage}_bsc' — presence/absence of the lineage column (0/1),
    #   representing whether the whole BSC was detected. Mean = detection rate.
    # Full mode: '{locus}_gene_count' — sum of allele presence/absence per sample.
    # Loci without a lineage column (rmpA2) use presence of the allele itself.
    # locus_gene_map always holds allele-level series for concordance.
    print("\nKleborate virulence BSC features:")
    for locus, info in KLEBORATE_VIRULENCE_LOCI.items():
        gene_series_list = [kleborate_column_to_presence(merged[g]) for g in info["alleles"] if g in merged.columns]
        if not gene_series_list:
            print(f"  - {locus}: no allele columns found, skipping")
            continue
        lineage = info.get("lineage")
        if full_virulence_output:
            feat_name = f"{locus}_gene_count"
            feat_series = sum(gene_series_list).astype(float)
        elif lineage and lineage in merged.columns:
            feat_name = f"{lineage}_bsc"
            feat_series = kleborate_column_to_presence(merged[lineage])
        else:
            feat_name = f"{locus}_bsc"
            feat_series = (
                gene_series_list[0] if len(gene_series_list) == 1 else (sum(gene_series_list) > 0).astype(float)
            )
        features[feat_name] = feat_series
        locus_gene_map[feat_name] = gene_series_list
        print(f"  + {feat_name}: mean={feat_series.mean():.3f}, n_alleles_for_concordance={len(gene_series_list)}")

    # 4. Kleborate chromosomal MLST -> presence/absence
    print(f"\nKleborate chromosomal MLST columns: {len(KLEBORATE_CHROMOSOMAL_MLST_COLS)} expected")
    m_added = m_missing = 0
    for col in KLEBORATE_CHROMOSOMAL_MLST_COLS:
        if col in features:
            continue
        if col in merged.columns:
            features[col] = kleborate_column_to_presence(merged[col])
            m_added += 1
        else:
            m_missing += 1
    print(f"  Added (presence/absence): {m_added}, missing: {m_missing}")

    # 5. Gene-range fallback
    # Exclude all Kleborate virulence schema columns: they are either already in
    # features (full mode) or intentionally collapsed to gene counts (default mode).
    _virulence_schema_cols: frozenset[str] = frozenset(KLEBORATE_VIRULENCE_COLS)
    gene_range = column_range_inclusive(all_cols, GAPA_START, VIRULENCE_END)
    print(f"\nGene-range fallback ({GAPA_START} to {VIRULENCE_END}): {len(gene_range)} columns")
    fb_added_cols: list[str] = []
    fb_skipped = 0
    for col in gene_range:
        if col in features or col in _virulence_schema_cols or col in EXCLUDE_NUMERIC:
            continue
        numeric = safe_numeric_column(merged[col], col)
        if numeric is not None:
            features[col] = numeric
            fb_added_cols.append(col)
        else:
            skipped.append(col)
            fb_skipped += 1
    print(f"  Added (numeric): {len(fb_added_cols)}, Skipped: {fb_skipped}")
    if fb_added_cols:
        print("  REVIEW: columns added by fallback (not in explicit Kleborate schema):")
        for c in fb_added_cols:
            print(f"    - {c}")

    # 6. *_acquired columns (count semicolon-delimited tokens)
    acquired_cols = acquired_column_names(all_cols)
    print(f"\nAcquired columns (*_acquired): {len(acquired_cols)} columns")
    if acquired_cols:
        example_col = acquired_cols[0]
        example_series = merged[example_col]
        example_counts = count_acquired_tokens(example_series)
        print(f"  Example '{example_col}': token counts range {example_counts.min()}-{example_counts.max()}")
        sample_idx = example_series.notna().idxmax() if example_series.notna().any() else None
        if sample_idx is not None:
            print(f"    Sample value: '{example_series.loc[sample_idx]}' -> {example_counts.loc[sample_idx]} tokens")
    for col in acquired_cols:
        features[col] = count_acquired_tokens(merged[col]).astype(float)
    print(f"  Added all {len(acquired_cols)} acquired columns as token counts")

    # 7. ISEScan columns
    print(f"\nISEScan columns: {len(ise_cols)} columns")
    ise_added = 0
    for col in ise_cols:
        if col in merged.columns:
            numeric = pd.to_numeric(merged[col], errors="coerce")
            display_name = col.replace("__isescan", "") if col.endswith("__isescan") else col
            features[display_name] = numeric
            ise_added += 1
    print(f"  Added: {ise_added}")

    # Summary
    print("\n=== Feature Summary ===")
    print(f"Total features included: {len(features)}")
    print(f"  of which locus gene counts: {len(locus_gene_map)}")
    print(f"Total columns skipped: {len(skipped)}")
    if skipped:
        print(f"  Skipped: {skipped}")

    return features, locus_gene_map, skipped


def build_comparison_table(
    subset: pd.DataFrame,
    features: dict[str, pd.Series],
    locus_gene_map: dict[str, list[pd.Series]],
    is_refseq_col: str = "is_refseq",
) -> pd.DataFrame:
    """Build comparison table for a subset of samples."""
    is_refseq = subset[is_refseq_col].astype(bool)
    rows = []

    for feature_name, full_series in features.items():
        feature_vals = full_series.loc[subset.index]
        row = compute_row_stats(feature_name, feature_vals, is_refseq)
        # Concordance: fraction of samples fully concordant within locus.
        # Only defined for locus gene-count features; NA for everything else.
        if feature_name in locus_gene_map:
            row["locus_concordance"] = compute_locus_concordance(locus_gene_map[feature_name], subset.index)
        else:
            row["locus_concordance"] = np.nan
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df.reindex(columns=list(OUTPUT_COLS))

    # Bonferroni-adjusted p-value (numeric, used for sorting)
    n_tests = int(df["p_val"].notna().sum())
    if n_tests > 0:
        df["p_val_corr"] = (df["p_val"] * n_tests).clip(upper=1.0)
    else:
        df["p_val_corr"] = np.nan

    # Ratio computed from raw means (before any rounding)
    df["complete_vs_sr_ratio"] = [_ratio(c, s) for c, s in zip(df["complete_genome_mean"], df["short_read_mean"], strict=False)]

    # Sort while p_val_corr is still numeric
    df = df.sort_values("p_val_corr", ascending=True, na_position="last")

    # String formatting for display
    df["p_val_corr"] = df["p_val_corr"].map(_fmt_sci_1dp)
    df["p_val"] = df["p_val"].map(_fmt_sci_1dp)
    df["locus_concordance"] = df["locus_concordance"].map(lambda x: _round_3sig(x) if not pd.isna(x) else "")
    for col in ("complete_genome_mean", "short_read_mean", "complete_sd", "sr_sd"):
        df[col] = df[col].map(_round_3sig)

    return df[list(OUTPUT_COLS)]


def compute_penetrance_stats(feature_name: str, feature_vals: pd.Series, is_refseq: pd.Series) -> dict:
    """Return Fisher exact p-value and penetrance (0-1) for each cohort."""
    binary = (feature_vals > 0).astype(float)
    complete = binary[is_refseq].dropna()
    short = binary[~is_refseq].dropna()

    n_complete = len(complete)
    n_sr = len(short)
    c_present = int((complete > 0).sum())
    s_present = int((short > 0).sum())

    if n_complete < 2 or n_sr < 2:
        p_val = np.nan
    else:
        _, p_val = stats.fisher_exact([[c_present, n_complete - c_present], [s_present, n_sr - s_present]])

    return {
        "feature": feature_name,
        "p_val": p_val,
        "complete_penetrance": c_present / n_complete if n_complete > 0 else np.nan,
        "sr_penetrance": s_present / n_sr if n_sr > 0 else np.nan,
        "n_complete": n_complete,
        "n_sr": n_sr,
    }


def build_penetrance_table(
    subset: pd.DataFrame,
    features: dict[str, pd.Series],
    locus_gene_map: dict[str, list[pd.Series]],
    is_refseq_col: str = "is_refseq",
) -> pd.DataFrame:
    """Build penetrance table for a subset of samples using Fisher's exact test."""
    is_refseq = subset[is_refseq_col].astype(bool)
    rows = []

    for feature_name, full_series in features.items():
        feature_vals = full_series.loc[subset.index]
        row = compute_penetrance_stats(feature_name, feature_vals, is_refseq)
        row["locus_concordance"] = (
            compute_locus_concordance(locus_gene_map[feature_name], subset.index)
            if feature_name in locus_gene_map
            else np.nan
        )
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df.reindex(columns=list(PENETRANCE_OUTPUT_COLS))

    n_tests = int(df["p_val"].notna().sum())
    df["p_val_corr"] = (df["p_val"] * n_tests).clip(upper=1.0) if n_tests > 0 else np.nan

    df["penetrance_ratio"] = [_ratio(c, s) for c, s in zip(df["complete_penetrance"], df["sr_penetrance"], strict=False)]

    df = df.sort_values("p_val_corr", ascending=True, na_position="last")

    df["p_val_corr"] = df["p_val_corr"].map(_fmt_sci_1dp)
    df["p_val"] = df["p_val"].map(_fmt_sci_1dp)
    df["locus_concordance"] = df["locus_concordance"].map(lambda x: _round_3sig(x) if not pd.isna(x) else "")
    for col in ("complete_penetrance", "sr_penetrance"):
        df[col] = df[col].map(_round_3sig)

    return df[list(PENETRANCE_OUTPUT_COLS)]


def sluggify(group_name: str) -> str:
    """Convert group name to safe filename."""
    if group_name == RARE_CGS_ROW:
        return "Rare_CGs"
    return str(group_name).replace(" ", "_").replace("/", "_")


def report_project_breakdown(gdf: pd.DataFrame, project_col: str, threshold: float = 0.10) -> None:
    """Print n_projects per stratum and any project >= threshold of stratum samples.

    Helps identify ascertainment bias: if one BioProject contributes >threshold
    of either complete or short-read samples in a CG, the comparison may be
    confounded by single-study effects.
    """
    if project_col not in gdf.columns:
        print(f"  (project breakdown skipped: '{project_col}' not in metadata)")
        return

    is_refseq = gdf["is_refseq"].astype(bool)
    for label, sub in (("complete", gdf[is_refseq]), ("short_read", gdf[~is_refseq])):
        projs = sub[project_col].dropna().astype(str)
        n_total = len(projs)
        n_unique = projs.nunique()
        print(f"  {label}: n_samples_with_project={n_total}, n_projects={n_unique}")
        if n_total == 0:
            continue
        counts = projs.value_counts()
        flagged = counts[counts / n_total >= threshold]
        if len(flagged):
            print(f"    Projects >={int(threshold * 100)}% of {label} samples:")
            for proj, n in flagged.items():
                pct = 100 * n / n_total
                print(f"      {proj}: n={n} ({pct:.1f}%)")


DEFAULT_METADATA_V2 = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv"
)
DEFAULT_SR_SHADOW = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/sr_shadow_for_lra.tsv"
)
DEFAULT_PAIRED_OUT = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/lra_vs_sr_comparison.tsv"
)


def _mcnemar_exact(b: int, c: int) -> float:
    """Exact McNemar p-value via two-sided binomial against H0=0.5.

    b = #(LR positive AND SR negative) = "LR-only" calls.
    c = #(LR negative AND SR positive) = "SR-only" calls.
    Returns NaN if b + c == 0 (no discordance to test).
    """
    n = b + c
    if n == 0:
        return float("nan")
    return float(stats.binomtest(min(b, c), n, 0.5).pvalue)


def _paired_binary_stats(
    lr_present: pd.Series, sr_present: pd.Series, feature: str, category: str,
) -> dict:
    """McNemar 2×2 contingency on a paired binary feature."""
    lr01 = lr_present.astype(int)
    sr01 = sr_present.astype(int)
    a = int(((lr01 == 1) & (sr01 == 1)).sum())  # both positive
    b = int(((lr01 == 1) & (sr01 == 0)).sum())  # LR rescue
    c = int(((lr01 == 0) & (sr01 == 1)).sum())  # SR-only (LR loss)
    d = int(((lr01 == 0) & (sr01 == 0)).sum())  # both negative
    n_pairs = a + b + c + d
    lr_pickup = (b / (b + c)) if (b + c) else float("nan")
    return {
        "feature":          feature,
        "category":         category,
        "stat":             "mcnemar",
        "n_pairs":          n_pairs,
        "both_positive":    a,
        "lr_only":          b,
        "sr_only":          c,
        "both_negative":    d,
        "lr_pickup_rate":   lr_pickup,
        "mcnemar_p":        _mcnemar_exact(b, c),
        "lr_mean":          float(lr01.mean()) if n_pairs else float("nan"),
        "sr_mean":          float(sr01.mean()) if n_pairs else float("nan"),
        "paired_t_p":       float("nan"),
        "wilcoxon_p":       float("nan"),
    }


def _paired_numeric_stats(
    lr_vals: pd.Series, sr_vals: pd.Series, feature: str, category: str,
) -> dict:
    """Paired t-test + Wilcoxon signed-rank on a paired numeric feature."""
    lr = pd.to_numeric(lr_vals, errors="coerce")
    sr = pd.to_numeric(sr_vals, errors="coerce")
    mask = lr.notna() & sr.notna()
    n_pairs = int(mask.sum())
    if n_pairs < 2:
        return {
            "feature": feature, "category": category, "stat": "paired_numeric",
            "n_pairs": n_pairs, "lr_mean": float("nan"), "sr_mean": float("nan"),
            "lr_only": int(((lr.fillna(0) > 0) & ~(sr.fillna(0) > 0)).sum()),
            "sr_only": int((~(lr.fillna(0) > 0) & (sr.fillna(0) > 0)).sum()),
            "both_positive": float("nan"), "both_negative": float("nan"),
            "lr_pickup_rate": float("nan"), "mcnemar_p": float("nan"),
            "paired_t_p": float("nan"), "wilcoxon_p": float("nan"),
        }
    lr_v, sr_v = lr[mask].astype(float), sr[mask].astype(float)
    diff = lr_v - sr_v
    # Paired t-test (handles zero-variance via NaN p).
    if diff.std(ddof=1) == 0 or diff.empty:
        t_p = float("nan")
    else:
        with np.errstate(invalid="ignore"):
            _, t_p = stats.ttest_rel(lr_v, sr_v)
    # Wilcoxon: skip if all diffs are zero.
    if (diff == 0).all():
        w_p = float("nan")
    else:
        try:
            _, w_p = stats.wilcoxon(lr_v, sr_v, zero_method="wilcox")
        except ValueError:
            w_p = float("nan")
    return {
        "feature":         feature,
        "category":        category,
        "stat":            "paired_numeric",
        "n_pairs":         n_pairs,
        "lr_mean":         float(lr_v.mean()),
        "sr_mean":         float(sr_v.mean()),
        "lr_only":         int((diff > 0).sum()),
        "sr_only":         int((diff < 0).sum()),
        "both_positive":   float("nan"),
        "both_negative":   float("nan"),
        "lr_pickup_rate":  float("nan"),
        "mcnemar_p":       float("nan"),
        "paired_t_p":      float(t_p),
        "wilcoxon_p":      float(w_p),
    }


def _paired_features(merged: pd.DataFrame) -> list[dict]:
    """Walk every paired feature and emit one stats dict per feature."""
    rows: list[dict] = []

    # ── Binary Kleborate virulence BSCs (presence of the lineage column) ──
    for code, info in KLEBORATE_VIRULENCE_LOCI.items():
        lineage = info.get("lineage") or ("rmpA2" if code == "rmpA2" else None)
        if not lineage:
            continue
        lr_col, sr_col = lineage, f"sr_{lineage}"
        if lr_col not in merged.columns or sr_col not in merged.columns:
            continue
        lr_present = kleborate_column_to_presence(merged[lr_col])
        sr_present = kleborate_column_to_presence(merged[sr_col])
        rows.append(_paired_binary_stats(lr_present, sr_present, f"{lineage}_bsc", "virulence_bsc"))

    # ── Numeric BSC allele counts (LR vs SR sum of present alleles) ──
    for code, info in KLEBORATE_VIRULENCE_LOCI.items():
        feat = f"{code}_allele_count"
        lr_alleles = [a for a in info["alleles"] if a in merged.columns]
        sr_alleles = [a for a in info["alleles"] if f"sr_{a}" in merged.columns]
        if not lr_alleles or not sr_alleles:
            continue
        lr_count = sum(kleborate_column_to_presence(merged[a]) for a in lr_alleles)
        sr_count = sum(kleborate_column_to_presence(merged[f"sr_{a}"]) for a in sr_alleles)
        rows.append(_paired_numeric_stats(lr_count, sr_count, feat, "virulence_allele_count"))

    # ── Binary MLST locus presence ──
    for locus in KLEBORATE_CHROMOSOMAL_MLST_COLS:
        if locus not in merged.columns or f"sr_{locus}" not in merged.columns:
            continue
        lr_present = kleborate_column_to_presence(merged[locus])
        sr_present = kleborate_column_to_presence(merged[f"sr_{locus}"])
        rows.append(_paired_binary_stats(lr_present, sr_present, locus, "mlst"))

    # ── Acquired-AMR token counts ──
    for col in acquired_column_names(list(merged.columns)):
        sr_col = f"sr_{col}"
        if sr_col not in merged.columns:
            continue
        lr_count = count_acquired_tokens(merged[col])
        sr_count = count_acquired_tokens(merged[sr_col])
        rows.append(_paired_numeric_stats(lr_count, sr_count, col, "amr_acquired"))

    return rows


def _run_paired_mode(args: argparse.Namespace) -> None:
    """Paired SR-vs-LRA comparison driver (Phase G.4).

    Reads ``metadata_v2`` + ``sr_shadow_for_lra.tsv``, joins on
    ``sr_biosample``, and runs McNemar's (binary) + paired t-test /
    Wilcoxon signed-rank (numeric) over the Kleborate + AMR feature set.

    ISEScan is **LR-only** (no SR-side counts in v1), so IS-family features
    are not paired — those go via the cross-section ``--mode clonal_group``.

    Writes ``lra_vs_sr_comparison.tsv`` with one row per feature.
    """
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading metadata_v2: {args.metadata_v2}")
    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    print(f"  rows: {len(meta):,}")
    print(f"Loading SR-shadow:   {args.sr_shadow}")
    shadow = pd.read_csv(args.sr_shadow, sep="\t", low_memory=False)
    print(f"  rows: {len(shadow):,}")

    # Filter to LRA-bearing rows with sr_biosample, then inner-join with shadow.
    lra = meta["lra_final_set"].astype(str).str.lower().isin({"true", "1", "yes"})
    paired_meta = meta[lra & meta["sr_biosample"].notna()].copy()
    paired_meta["sr_biosample"] = paired_meta["sr_biosample"].astype(str)
    shadow["sr_biosample"] = shadow["sr_biosample"].astype(str)

    merged = paired_meta.merge(shadow, on="sr_biosample", how="inner", suffixes=("", "_shadow"))
    print(f"\nPaired rows after merge: {len(merged):,}")
    print(f"  LRA-bearing rows with sr_biosample : {len(paired_meta):,}")
    print(f"  shadow rows                         : {len(shadow):,}")

    rows = _paired_features(merged)
    out = pd.DataFrame(rows)

    # Add BH-corrected q values per stat-test column.
    for p_col, q_col in (("mcnemar_p", "mcnemar_q"), ("paired_t_p", "paired_t_q"), ("wilcoxon_p", "wilcoxon_q")):
        if p_col in out.columns:
            valid = out[p_col].notna()
            ranked = out.loc[valid, p_col].rank(method="average")
            n = int(valid.sum())
            if n:
                out.loc[valid, q_col] = (out.loc[valid, p_col] * n / ranked).clip(upper=1.0)
            else:
                out[q_col] = float("nan")

    out_path = args.output_dir / "lra_vs_sr_comparison.tsv"
    out.to_csv(out_path, sep="\t", index=False)
    print(f"\nwrote {out_path}  rows={len(out)}")

    # Headline summary: per-category LR-rescue rate + total LR-only calls.
    print("\n=== Per-category headline ===")
    if "category" in out.columns and len(out):
        binary = out[out["stat"] == "mcnemar"]
        if not binary.empty:
            print("\n  Binary features (Kleborate presence/absence):")
            for cat, g in binary.groupby("category"):
                total_b = int(g["lr_only"].sum())
                total_c = int(g["sr_only"].sum())
                rate = total_b / (total_b + total_c) if (total_b + total_c) else float("nan")
                sig = int((g["mcnemar_p"] < 0.05).sum())
                print(f"    {cat:25s}  features={len(g):>3}  LR-only={total_b:>5}  "
                      f"SR-only={total_c:>5}  LR-rescue-rate={rate:.3f}  sig@0.05={sig}")
        numeric = out[out["stat"] == "paired_numeric"]
        if not numeric.empty:
            print("\n  Numeric features (paired t / Wilcoxon):")
            for cat, g in numeric.groupby("category"):
                sig_t  = int((g["paired_t_p"]  < 0.05).sum())
                sig_w  = int((g["wilcoxon_p"]  < 0.05).sum())
                print(f"    {cat:25s}  features={len(g):>3}  sig_t@0.05={sig_t}  sig_wilcoxon@0.05={sig_w}")

    # Top 10 LR-rescue features overall (sorted by lr_only count).
    binary_calls = out[out["stat"] == "mcnemar"].sort_values("lr_only", ascending=False).head(10)
    if not binary_calls.empty:
        print("\n  Top 10 LR-rescue binary features (by LR-only count):")
        for _, r in binary_calls.iterrows():
            print(f"    {r['feature']:35s}  LR-only={int(r['lr_only']):>4}  "
                  f"SR-only={int(r['sr_only']):>4}  rate={r['lr_pickup_rate']:.3f}  "
                  f"p={r['mcnemar_p']:.2e}")


def main() -> None:
    """CLI entry point — dispatch to clonal_group (cross-section) or paired (G.4) mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["clonal_group", "paired"],
        default="clonal_group",
        help="clonal_group: cross-section is_refseq vs short-read per CG (default). "
        "paired: same-biosample SR-vs-LRA stats from metadata_v2 + sr_shadow_for_lra.tsv (G.4).",
    )
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--isescan-csv", type=Path, default=DEFAULT_ISESCAN)
    # Paired-mode inputs (Phase G.4).
    parser.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2,
                        help="(paired mode) metadata_v2 TSV with LR-Kleborate values.")
    parser.add_argument("--sr-shadow",   type=Path, default=DEFAULT_SR_SHADOW,
                        help="(paired mode) sr_shadow_for_lra.tsv with SR-Kleborate frozen at v1.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory (clonal_group mode); paired mode writes "
             "lra_vs_sr_comparison.tsv under <RDS>/david/processed/ by default.",
    )
    parser.add_argument(
        "--full-virulence-output",
        action="store_true",
        default=False,
        help="Report all individual alleles, STs, lineage strings, and spurious hits "
        "for each virulence locus. Default: one '{Lineage}_gene_count' row per locus.",
    )
    parser.add_argument("--top-clonal-groups", type=int, default=15)
    parser.add_argument("--rare-cg-n", type=int, default=1000)
    parser.add_argument(
        "--project-col",
        default="study_accession",
        help="Metadata column holding BioProject (or equivalent) accession. "
        "Used to print per-stratum project breakdown for ascertainment-bias review.",
    )
    parser.add_argument(
        "--project-threshold",
        type=float,
        default=0.10,
        help="Print projects accounting for >= this fraction of stratum samples (default 0.10).",
    )
    args = parser.parse_args()

    if args.mode == "paired":
        _run_paired_mode(args)
        return

    output_dir = args.output_dir
    counts_dir = output_dir / "counts"
    penetrance_dir = output_dir / "penetrance"
    output_dir.mkdir(parents=True, exist_ok=True)
    counts_dir.mkdir(exist_ok=True)
    penetrance_dir.mkdir(exist_ok=True)
    log_path = output_dir / "cg_feature_cohort_analysis.log"
    with log_path.open("w", encoding="utf-8") as log_fh:
        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        sys.stdout = _Tee(orig_stdout, log_fh)
        sys.stderr = _Tee(orig_stderr, log_fh)
        try:
            print(f"Logging to: {log_path}")
            # Load metadata
            print(f"Loading metadata from {args.metadata}")
            meta = pd.read_csv(args.metadata, sep="\t", low_memory=False)
            required = {"Sample", "Clonal group", "is_refseq"}
            missing = required - set(meta.columns)
            if missing:
                raise KeyError(f"Metadata missing required columns: {sorted(missing)}")
            print(f"Loaded {len(meta)} samples")

            # Load and merge ISEScan
            isesc, ise_cols = load_isescan_features(args.isescan_csv)
            merged, ise_internal_cols = merge_metadata_isescan(meta, isesc, ise_cols)
            print(f"After merge: {len(merged)} samples")

            # Build feature data
            features, locus_gene_map, skipped = build_feature_data(
                merged, ise_internal_cols, full_virulence_output=args.full_virulence_output
            )

            # Identify CG groups
            whole = merged.dropna(subset=["Clonal group"]).copy()
            cg_totals = cg_unique_sample_counts(whole, sample_col="Sample", cg_col="Clonal group")

            epidemic_labels = epidemic_labels_from_counts(cg_totals, args.top_clonal_groups)
            rare_labels = rare_labels_from_counts(cg_totals, epidemic_labels, args.rare_cg_n)

            print("\n=== CG Groups ===")
            print(f"Top {args.top_clonal_groups} epidemic CGs: {epidemic_labels}")
            print(f"Rare CGs pooled: {len(rare_labels)} groups")

            # Build groups to analyze
            merged["_cg_str"] = merged["Clonal group"].astype(str)
            groups: list[tuple[str, pd.DataFrame]] = []

            # Epidemic CGs (ordered by sample count descending)
            for cg in epidemic_labels:
                mask = merged["_cg_str"] == str(cg)
                groups.append((str(cg), merged.loc[mask]))

            # Rare CGs
            rare_mask = merged["_cg_str"].isin(list(rare_labels))
            groups.append((RARE_CGS_ROW, merged.loc[rare_mask]))

            # All samples
            groups.append(("all_samples", merged))

            # Process each group
            print("\n=== Processing Groups ===")
            for group_name, gdf in groups:
                n_complete = gdf["is_refseq"].sum()
                n_short = len(gdf) - n_complete
                print(f"\n--- {group_name} ---")
                print(f"Samples: {len(gdf)} (complete: {n_complete}, short-read: {n_short})")

                if len(gdf) == 0:
                    print("  Skipping: no samples")
                    continue

                report_project_breakdown(gdf, args.project_col, args.project_threshold)

                fname = f"{sluggify(group_name)}.csv"

                tbl = build_comparison_table(gdf, features, locus_gene_map)
                out_path = counts_dir / fname
                tbl.to_csv(out_path, index=False)
                print(f"Wrote counts:      {out_path} ({len(tbl)} features)")

                pen_tbl = build_penetrance_table(gdf, features, locus_gene_map)
                pen_path = penetrance_dir / fname
                pen_tbl.to_csv(pen_path, index=False)
                print(f"Wrote penetrance:  {pen_path} ({len(pen_tbl)} features)")

            print("\n=== Done ===")
            print(f"Output directory: {output_dir}")
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr


if __name__ == "__main__":
    main()
