"""Assemble the deterministic ENA assessment table, one row per project accession.

Joins ENA sizing (per accession) with the three-state per-field completeness (computed once
over the whole source tables, then looked up per study). No LLM, no paper lookup.
"""

from __future__ import annotations

import pandas as pd

from .completeness import PARSED_COLUMN, completeness_by_study, normalise_table
from .spec import AttributeSpec

#: Completeness states emitted, in column order.
STATES = ("base", "post-merge", "norm")
_STATE_TAG = {"base": "base", "post-merge": "postmerge", "norm": "norm"}


def _completeness_frames(states: dict[str, pd.DataFrame], fields: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Compute per-study completeness for the base, post-merge and normalised states.

    Parameters
    ----------
    states
        Source states (must include ``"base"``; ``"post-merge"`` optional).
    fields
        Clinical fields to score.

    Returns
    -------
    dict[str, pandas.DataFrame]
        State tag -> per-study completeness frame.
    """
    raw_cols = {f: f for f in fields}
    frames: dict[str, pd.DataFrame] = {"base": completeness_by_study(states["base"], raw_cols)}

    post = states.get("post-merge")
    if post is not None:
        frames["post-merge"] = completeness_by_study(post, raw_cols)
        norm_source = normalise_table(post, fields)
    else:
        norm_source = normalise_table(states["base"], fields)
    norm_cols = {f: PARSED_COLUMN[f] for f in fields if f in PARSED_COLUMN}
    frames["norm"] = completeness_by_study(norm_source, norm_cols)
    return frames


def build_ena_assessment_table(
    split_df: pd.DataFrame,
    spec: AttributeSpec,
    states: dict[str, pd.DataFrame],
    sizing_records: dict[str, dict],
) -> pd.DataFrame:
    """Build the per-accession ENA assessment ingestion table.

    Parameters
    ----------
    split_df
        Must contain ``study_accession``; ``fold`` and ``n_isolates`` are carried through if present.
    spec
        The application :class:`AttributeSpec` (drives the completeness fields).
    states
        Per-sample source states from a source's ``.states()``.
    sizing_records
        Mapping ``study_accession -> study_record_counts(...)`` result.

    Returns
    -------
    pandas.DataFrame
        One row per accession: split metadata, ENA sizing, ``n_held``, the three completeness
        states per field, the base->post-merge ``backfill_delta`` per field, and ``fetch_status``.
    """
    fields = spec.completeness_fields
    frames = _completeness_frames(states, fields)
    held = frames["base"]["n_records"]

    rows: list[dict] = []
    for _, srow in split_df.iterrows():
        acc = srow["study_accession"]
        sizing = sizing_records.get(acc, {})
        row: dict[str, object] = {"study_accession": acc}
        if "fold" in split_df.columns:
            row["fold"] = srow["fold"]
        if "n_isolates" in split_df.columns:
            row["n_isolates_split"] = srow["n_isolates"]

        row["ena_total_samples"] = sizing.get("ena_total_samples", pd.NA)
        row["ena_total_runs"] = sizing.get("ena_total_runs", pd.NA)
        row["ena_taxon_samples"] = sizing.get("ena_taxon_samples", pd.NA)
        row["n_child_studies"] = sizing.get("n_child_studies", pd.NA)
        row["umbrella_suspected"] = sizing.get("umbrella_suspected", pd.NA)
        row["n_held"] = int(held[acc]) if acc in held.index else 0

        for f in fields:
            for state in STATES:
                tag = _STATE_TAG[state]
                frame = frames.get(state)
                val = frame.loc[acc, f] if (frame is not None and acc in frame.index and f in frame.columns) else pd.NA
                row[f"completeness_{tag}_{f}"] = val
            base_v = frames["base"].loc[acc, f] if acc in frames["base"].index else pd.NA
            post_frame = frames.get("post-merge")
            post_v = post_frame.loc[acc, f] if (post_frame is not None and acc in post_frame.index) else pd.NA
            row[f"backfill_delta_{f}"] = (
                post_v - base_v if (pd.notna(base_v) and pd.notna(post_v)) else pd.NA
            )

        row["fetch_status"] = sizing.get("fetch_status", "not_fetched")
        rows.append(row)

    return pd.DataFrame(rows)
