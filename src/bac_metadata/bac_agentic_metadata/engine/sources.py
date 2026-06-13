"""Per-sample metadata sources, keyed by ``study_accession``.

A source loads the *existing* ATB metadata for an application and returns one or more named
states (e.g. ``base`` and ``post-merge``). It does **not** remake the metadata — the kleb
source reuses ``pp.metadata_collation`` so the engine measures exactly the tables David already
built, and surfaces the auxiliary columns (run accessions, instrument platform) too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: The four curated clinical fields plus useful auxiliary columns to carry through.
DEFAULT_AUX_COLUMNS = ("run_accession", "instrument_platform", "scientific_name")


@dataclass
class KlebCollationSource:
    """Klebsiella per-sample source built from the existing collation pipeline.

    Wraps ``pp.metadata_collation`` to return two states keyed by ``study_accession``:
    ``base`` (the raw ATB ENA metadata, pre-backfill) and ``post-merge`` (after the per-project
    ``ready_to_merge`` patches are applied). Path arguments default to the module constants in
    ``pp.metadata_collation``; override them to point at local copies of the collated data.

    Parameters
    ----------
    metadata_file1, metadata_file2, metadata_file3
        The three base ATB ENA metadata TSVs (``None`` -> the ``metadata_collation`` default).
    qc_excel_path
        QC Excel providing the RefSeq sheet (``None`` -> default).
    ena_project_dir
        Directory of per-project ``ready_to_merge`` slices (``None`` -> default).
    keep_columns
        Columns to retain in addition to ``study_accession`` and the four clinical fields.
    """

    metadata_file1: str | None = None
    metadata_file2: str | None = None
    metadata_file3: str | None = None
    qc_excel_path: str | None = None
    ena_project_dir: str | None = None
    study_metadata_file: str | None = None  # local study_level CSV -> avoids the Google read
    keep_columns: tuple[str, ...] = DEFAULT_AUX_COLUMNS
    _clinical: tuple[str, ...] = field(
        default=("country", "collection_date", "isolation_source", "host"), init=False, repr=False
    )

    def states(self) -> dict[str, pd.DataFrame]:
        """Return ``{"base": df, "post-merge": df}`` keyed per-sample by ``study_accession``.

        Returns
        -------
        dict[str, pandas.DataFrame]
            The two completeness states.
        """
        from bac_metadata.pp import metadata_collation as mcoll

        load_kwargs = {
            k: v
            for k, v in {
                "metadata_file1": self.metadata_file1,
                "metadata_file2": self.metadata_file2,
                "metadata_file3": self.metadata_file3,
                "qc_excel_path": self.qc_excel_path,
                "study_metadata_file": self.study_metadata_file,
            }.items()
            if v is not None
        }
        # google_sheet_id=None keeps collation offline: the reviewed flag (unused by completeness)
        # comes from study_metadata_file if given, and removed_studies resolves to an empty set.
        base = mcoll.load_collated_metadata(google_sheet_id=None, **load_kwargs)

        project_dir = self.ena_project_dir or mcoll.ENA_PROJECT_DIR
        ready_files = mcoll.find_ready_to_merge_files(project_dir, verbose=False)
        post_merge, *_ = mcoll.apply_ready_to_merge_updates(base, ready_files, verbose=False)

        wanted = ["study_accession", *self._clinical, *self.keep_columns]
        return {
            "base": _select(base, wanted),
            "post-merge": _select(post_merge, wanted),
        }


@dataclass
class GenericXlsxSource:
    """Single-state per-sample source backed by a flat spreadsheet (e.g. the M.abs release).

    Parameters
    ----------
    path
        Path to the ``.xlsx`` file.
    sheet
        Sheet name (defaults to the first sheet).
    study_col
        Column holding the project accession (renamed to ``study_accession``).
    keep_columns
        Auxiliary columns to retain alongside the clinical fields.
    """

    path: str
    sheet: str | int = 0
    study_col: str = "study_accession"
    keep_columns: tuple[str, ...] = DEFAULT_AUX_COLUMNS
    _clinical: tuple[str, ...] = field(
        default=("country", "collection_date", "isolation_source", "host"), init=False, repr=False
    )

    def states(self) -> dict[str, pd.DataFrame]:
        """Return ``{"base": df}`` keyed per-sample by ``study_accession``."""
        df = pd.read_excel(self.path, sheet_name=self.sheet, dtype=str)
        if self.study_col != "study_accession":
            df = df.rename(columns={self.study_col: "study_accession"})
        wanted = ["study_accession", *self._clinical, *self.keep_columns]
        return {"base": _select(df, wanted)}


def _select(df: pd.DataFrame, wanted: list[str]) -> pd.DataFrame:
    """Return ``df`` reduced to the wanted columns that exist, de-duplicated, order preserved."""
    seen: set[str] = set()
    cols = [c for c in wanted if c in df.columns and not (c in seen or seen.add(c))]
    return df.loc[:, cols].copy()
