"""Reset and re-apply the kpsc_final_list flag based on samples_final_v2.txt.

Can be run standalone (overwrites the two final TSVs in-place) or called from
metadata_curation.py via apply_kpsc_final_list_flag() on an in-memory dataframe.
"""

import pandas as pd
from pathlib import Path

FINAL_DIR = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final")
SAMPLES_FINAL_PATH = FINAL_DIR / "samples_final_v2.txt"
FULL_METADATA_PATH = FINAL_DIR / "metadata/metadata_final_curated_all_samples_and_columns.tsv"
SLIMMED_METADATA_PATH = FINAL_DIR / "metadata/metadata_final_curated_slimmed.tsv"


def apply_kpsc_final_list_flag(df, samples_path=SAMPLES_FINAL_PATH):
    """Reset kpsc_final_list to False for all rows, then set True for samples in the final list.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'Sample' and 'kpsc_final_list' columns.
    samples_path : Path
        Path to a text/CSV file with a 'Sample' column listing final samples.

    Returns
    -------
    pd.DataFrame
        The same dataframe with kpsc_final_list updated in place.
    """
    samples_df = pd.read_csv(samples_path, header=0, names=["Sample"])
    if "Sample" not in samples_df.columns:
        raise ValueError(
            f"'Sample' column not found in {samples_path}. "
            f"Columns found: {list(samples_df.columns)}"
        )
    sample_set = set(samples_df["Sample"].astype(str).unique())
    print(f"Final list v2 opened, has {len(sample_set)} unique Samples")

    if "Sample" not in df.columns:
        raise ValueError("'Sample' column not found in dataframe")
    if "kpsc_final_list" not in df.columns:
        raise ValueError(
            "'kpsc_final_list' column not found in dataframe — "
            "this column must already exist before slicing by the final list"
        )

    n_true = int(df["kpsc_final_list"].sum())
    n_false = len(df) - n_true
    print(f"kpsc_final_list currently has {n_true} True and {n_false} False")

    print("Setting all kpsc_final_list values to False")
    df["kpsc_final_list"] = False

    df.loc[df["Sample"].astype(str).isin(sample_set), "kpsc_final_list"] = True
    n_matched = int(df["kpsc_final_list"].sum())
    print(f"After matching to final v2, {n_matched} Samples have kpsc_final_list=True")

    matched_samples = set(df.loc[df["kpsc_final_list"], "Sample"].astype(str))
    unmatched = sample_set - matched_samples
    if not unmatched:
        print("SUCCESS: All Samples in samples_final_v2.txt were matched in the dataframe")
    else:
        first_five = sorted(unmatched)[:5]
        print(
            f"WARNING: {len(unmatched)} Samples from samples_final_v2.txt were NOT found "
            f"in the dataframe. First 5: {first_five}"
        )

    return df


def apply_kpsc_final_list_to_both(full_df, slimmed_df, samples_path=SAMPLES_FINAL_PATH):
    """Apply the kpsc_final_list flag to both the full and slimmed dataframes."""
    print("\n--- Applying kpsc_final_list to full metadata ---")
    full_df = apply_kpsc_final_list_flag(full_df, samples_path)
    print("\n--- Applying kpsc_final_list to slimmed metadata ---")
    slimmed_df = apply_kpsc_final_list_flag(slimmed_df, samples_path)
    return full_df, slimmed_df


def run_slice_by_final_list():
    """Standalone runner: read the final TSVs, re-apply kpsc_final_list, overwrite in place."""
    print("=" * 60)
    print("Slicing metadata by final sample list (standalone mode)")
    print("=" * 60)

    print(f"\nProcessing full metadata: {FULL_METADATA_PATH}")
    full_df = pd.read_csv(FULL_METADATA_PATH, sep="\t", low_memory=False)
    full_df = apply_kpsc_final_list_flag(full_df)
    full_df.to_csv(FULL_METADATA_PATH, sep="\t", index=False)
    print(f"Full metadata overwritten: {FULL_METADATA_PATH}")

    print(f"\nProcessing slimmed metadata: {SLIMMED_METADATA_PATH}")
    slimmed_df = pd.read_csv(SLIMMED_METADATA_PATH, sep="\t", low_memory=False)
    slimmed_df = apply_kpsc_final_list_flag(slimmed_df)
    slimmed_df.to_csv(SLIMMED_METADATA_PATH, sep="\t", index=False)
    print(f"Slimmed metadata overwritten: {SLIMMED_METADATA_PATH}")


if __name__ == "__main__":
    run_slice_by_final_list()
