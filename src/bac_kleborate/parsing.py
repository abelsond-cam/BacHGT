"""Kleborate output-parsing primitives.

Single source of truth for the cell-presence rule, virulence-locus schema, and
acquired-AMR token logic used across the BacHGT ecosystem. Lifted out of
``bac_complete_genomes.compare_lra_to_sra`` so downstream consumers (BacPredict
linear baselines, future annotators, per-task feature builders) can import the
same primitives instead of re-implementing them.

Two layers:

1. **Low-level primitives** — single-column / single-cell helpers:
   :func:`kleborate_cell_present`, :func:`kleborate_column_to_presence`,
   :func:`count_acquired_tokens`, :func:`acquired_column_names`.
2. **High-level feature builders** — whole-metadata-frame helpers that emit a
   per-sample 0/1 DataFrame ready to drop into a feature matrix:
   :func:`virulence_cluster_presence` (6 BSC flags),
   :func:`amr_class_presence` (~15 acquired-class flags).

Schema constants:

- :data:`KLEBORATE_ABSENT_TOKENS` — the ``{-, 0, NA, …}`` set Kleborate emits
  for no-detection.
- :data:`KLEBORATE_VIRULENCE_LOCI` — per-cluster allele list pulled from each
  module's ``get_headers()`` in
  https://github.com/klebgenomics/Kleborate/tree/main/kleborate/modules.
"""

from __future__ import annotations

import logging

import pandas as pd

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

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

# Kleborate virulence module schema.
# Read directly from each module's get_headers() in
# https://github.com/klebgenomics/Kleborate/tree/main/kleborate/modules
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

# Kleborate KpSC chromosomal 7-locus MLST scheme.
# Treated as presence/absence: allele IDs are arbitrary, but failure to detect
# a housekeeping gene is a meaningful assembly artefact.
KLEBORATE_CHROMOSOMAL_MLST_COLS: list[str] = [
    "gapA",
    "infB",
    "mdh",
    "pgi",
    "phoE",
    "rpoB",
    "tonB",
]


# ---------------------------------------------------------------------------
# Low-level cell + column helpers
# ---------------------------------------------------------------------------


def kleborate_cell_present(val) -> bool:
    """Return True if a Kleborate cell records a detection.

    Treats any string outside ``KLEBORATE_ABSENT_TOKENS`` as a positive call,
    including imperfect-match annotations (``15*``, ``15^``, ``15?``,
    ``15*-42%``) and multi-copy comma-separated lists. Mirrors Kleborate's own
    logic: it only writes a non-``-`` value when minimap2 finds a hit above the
    module's identity/coverage thresholds.
    """
    if pd.isna(val):
        return False
    return str(val).strip() not in KLEBORATE_ABSENT_TOKENS


def kleborate_column_to_presence(series: pd.Series) -> pd.Series:
    """Return a float Series of 0/1 indicating Kleborate detection per row."""
    return series.apply(kleborate_cell_present).astype(float)


def acquired_column_names(columns) -> list[str]:
    """Return column names ending in ``_acquired`` (sorted)."""
    return sorted(c for c in columns if str(c).endswith("_acquired"))


def count_acquired_tokens(series: pd.Series) -> pd.Series:
    """Split each cell by ``;`` and count non-empty tokens.

    Kleborate writes ``-`` for a class with no acquired gene; that is a
    no-hit marker, not a gene, so it must not be counted as one token.
    """

    def count_tokens(x):
        if pd.isna(x):
            return 0
        tokens = [t.strip() for t in str(x).split(";") if t.strip() and t.strip() != "-"]
        return len(tokens)

    return series.apply(count_tokens)


# ---------------------------------------------------------------------------
# Feature-name helpers (canonical column names emitted by the builders below)
# ---------------------------------------------------------------------------


def virulence_bsc_name(code: str, info: dict) -> str:
    """Canonical feature name for a virulence BSC, e.g. ``Yersiniabactin (ybt) bsc``.

    Matches the convention used by ``compare_lra_to_sra.py``'s wide schema so
    that downstream analyses (linear baselines, summary notebooks) can quote
    one stable label per cluster.
    """
    lineage = info.get("lineage")
    return f"{lineage} ({code}) bsc" if lineage else f"{code} bsc"


# ---------------------------------------------------------------------------
# High-level feature builders (whole-metadata-frame → per-sample DataFrame)
# ---------------------------------------------------------------------------


def virulence_cluster_presence(meta_df: pd.DataFrame) -> pd.DataFrame:
    """Per-sample 0/1 DataFrame for the 6 Kleborate virulence BSCs.

    For each entry in :data:`KLEBORATE_VIRULENCE_LOCI`, sum allele-column
    presence over the alleles **that exist in ``meta_df``**, then call the
    cluster present iff any allele is present. Clusters whose allele columns
    are all absent from ``meta_df`` are skipped with a warning — the result
    preserves ``meta_df``'s index but only contains columns for clusters that
    could be evaluated.

    Parameters
    ----------
    meta_df
        Any DataFrame indexed by sample (e.g. ``metadata_v2`` rows). Must
        carry Kleborate's per-allele columns (``ybtS``, ``iucA``, ``rmpA``…)
        for the clusters of interest.

    Returns
    -------
    DataFrame
        Shape ``(n_samples, <=6)``. Column names are
        :func:`virulence_bsc_name` of each cluster. Values are 0/1 floats.
    """
    out: dict[str, pd.Series] = {}
    for code, info in KLEBORATE_VIRULENCE_LOCI.items():
        present_alleles = [a for a in info["alleles"] if a in meta_df.columns]
        if not present_alleles:
            logging.warning(
                "virulence_cluster_presence: skipping cluster %r — no allele columns in input "
                "(expected any of %s)", code, info["alleles"],
            )
            continue
        copies = sum(kleborate_column_to_presence(meta_df[a]) for a in present_alleles)
        out[virulence_bsc_name(code, info)] = (copies > 0).astype(float)
    return pd.DataFrame(out, index=meta_df.index)


def amr_class_presence(meta_df: pd.DataFrame) -> pd.DataFrame:
    """Per-sample 0/1 DataFrame for every Kleborate acquired-AMR class.

    Discovers all ``<class>_acquired`` columns via :func:`acquired_column_names`
    and marks each present iff :func:`count_acquired_tokens` returns ≥ 1.

    Parameters
    ----------
    meta_df
        Any DataFrame carrying Kleborate's per-class acquired columns
        (``AGly_acquired``, ``Bla_Carb_acquired``, …).

    Returns
    -------
    DataFrame
        Shape ``(n_samples, n_classes)``. Column names are the source
        ``<class>_acquired`` headers verbatim. Values are 0/1 floats.
    """
    cols = acquired_column_names(meta_df.columns)
    out = {col: (count_acquired_tokens(meta_df[col]) > 0).astype(float) for col in cols}
    return pd.DataFrame(out, index=meta_df.index)
