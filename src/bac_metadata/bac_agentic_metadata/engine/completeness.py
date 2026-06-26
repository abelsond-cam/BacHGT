"""Per-field, per-study completeness across the base / post-merge / normalised states.

"Completeness" is the fraction of a study's records that carry a non-empty value for a field.
We measure it three ways (see ``PROGRESS_REPORT.md``):

* **base** — raw value on the base ATB metadata (the pre-backfill baseline);
* **post-merge** — after the per-project ``ready_to_merge`` patches (the *manual* backfill);
* **norm** — after the reusable ``pp.metadata_curation`` parse/categorise pairs, which null out
  placeholders ("unknown", "not collected") so a placeholder no longer counts as present.

The base -> post-merge delta is exactly the manual backfill the engine must later reproduce.
The parse/categorise callables are run once over a whole table (not per accession) to match how
the production pipeline runs and to keep their verbose logging to a single pass.
"""

from __future__ import annotations

import pandas as pd

#: field -> the ``*_parsed`` column its normaliser produces.
PARSED_COLUMN = {
    "country": "country_parsed",
    "collection_date": "collection_date_parsed",
    "isolation_source": "isolation_source_parsed",
    "host": "host_parsed",
}


def normalise_table(df: pd.DataFrame, fields: tuple[str, ...]) -> pd.DataFrame:
    """Add ``*_parsed`` columns for ``fields`` using the reusable curation parsers.

    Parameters
    ----------
    df
        Per-sample table carrying the raw field columns.
    fields
        Subset of ``country``/``collection_date``/``isolation_source``/``host`` to normalise.

    Returns
    -------
    pandas.DataFrame
        A copy of ``df`` with the relevant ``*_parsed`` columns added.
    """
    # Imported lazily: pulls in the heavy curation module only when normalisation is requested.
    from bac_metadata.pp import metadata_curation as mc

    out = df.copy()
    if "country" in fields:
        out = mc.parse_country(out, verbose=False)
    if "host" in fields:
        out = mc.parse_host(out, verbose=False)
    if "isolation_source" in fields:
        out = mc.parse_isolation_source(out, verbose=False)
    if "collection_date" in fields:
        out = mc.parse_collection_date(out, verbose=False)
    return out


def _nonnull_fraction(series: pd.Series) -> float:
    """Fraction of entries that are non-null and not an empty/whitespace string."""
    if len(series) == 0:
        return float("nan")
    filled = series.notna() & (series.astype(str).str.strip() != "") & (series.astype(str).str.strip().str.lower() != "nan")
    return float(filled.mean())


def completeness_by_study(
    df: pd.DataFrame,
    columns: dict[str, str],
    *,
    group_col: str = "study_accession",
) -> pd.DataFrame:
    """Compute the non-null fraction of each column, grouped by study accession.

    Parameters
    ----------
    df
        Per-sample table with ``group_col`` plus the columns to score.
    columns
        Mapping ``out_name -> source_column``; missing source columns score as all-empty.
    group_col
        Column to group by (default ``"study_accession"``).

    Returns
    -------
    pandas.DataFrame
        Indexed by ``group_col`` with one ``out_name`` column per entry plus ``n_records``.
    """
    grouped = df.groupby(group_col, dropna=True)
    result = pd.DataFrame({"n_records": grouped.size()})
    for out_name, source_col in columns.items():
        if source_col in df.columns:
            result[out_name] = grouped[source_col].apply(_nonnull_fraction)
        else:
            result[out_name] = float("nan")
    return result
