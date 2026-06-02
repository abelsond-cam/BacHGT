#!/usr/bin/env python3
"""Panaroo run discovery and metadata-based sample-group splitting.

Single source of truth for two pieces of logic that were previously duplicated:

1. ``find_panaroo_runs`` — locate Panaroo output directories (those containing
   ``gene_presence_absence.Rtab``) under a parent directory.
2. ``split_samples`` / ``hierarchical_split`` — partition a sample set by a
   metadata column (e.g. Clonal_group, K_locus), keeping groups with
   ``count >= min_group_size`` as their own slice and pooling everything else
   (small groups + missing values) into a single ``other`` bucket.

Used by ``gpa_distances_single_run.py`` (for stratified distance analysis)
and ``gpa_reference_granularity.py`` (for the level-b.i / b.ii granularity
calculations).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

# Sentinel values that pandas can produce when reading missing metadata cells
# as objects/strings (rather than as a true NaN). Any of these signals "missing".
_MISSING_STRINGS = frozenset({"", "nan", "None", "NaN"})


def find_panaroo_runs(panaroo_run_root: str | Path) -> list[str]:
    """Return names of Panaroo-run subdirectories under ``panaroo_run_root``.

    A subdirectory qualifies iff it contains a ``gene_presence_absence.Rtab``
    file at its top level. Only immediate children of ``panaroo_run_root`` are
    inspected (no recursive descent). The return value is the leaf directory
    names (not full paths), sorted alphabetically.
    """
    root = str(panaroo_run_root)
    leaves: list[str] = []
    for entry in sorted(os.listdir(root)):
        run_dir = os.path.join(root, entry)
        gpa_rtab = os.path.join(run_dir, "gene_presence_absence.Rtab")
        if os.path.isdir(run_dir) and os.path.isfile(gpa_rtab):
            leaves.append(entry)
    return leaves


def split_samples(
    meta_for_samples: pd.DataFrame,
    col: str,
    min_group_size: int,
    other_label: str = "other",
) -> list[tuple[str, list[str]]]:
    """Partition samples by ``col`` value into major groups + a pooled ``other``.

    Groups with ``count >= min_group_size`` keep their own entry, ordered by
    descending size. All other samples (including those with missing/empty
    values, and those with values whose group size is below the threshold)
    are pooled into a single ``(other_label, ids)`` tuple appended last. The
    ``other`` tuple is appended only when non-empty.

    Parameters
    ----------
    meta_for_samples
        DataFrame indexed by sample ID, containing column ``col``.
    col
        Column to split on (e.g. ``"Clonal group"``, ``"K_locus"``).
    min_group_size
        Minimum size for a group to keep its own slice.
    other_label
        Label to use for the pooled bucket (default ``"other"``).

    Returns
    -------
    list of (label, sample_ids) tuples; major groups in descending size,
    ``other`` last (only if non-empty).
    """
    if col not in meta_for_samples.columns:
        return []

    series = meta_for_samples[col]
    series_str = series.astype(str)
    missing_mask = series.isna() | series_str.isin(_MISSING_STRINGS)
    value_counts = series_str[~missing_mask].value_counts()

    major_vals = value_counts[value_counts >= min_group_size].index.tolist()
    minor_set = set(value_counts[value_counts < min_group_size].index.tolist())

    groups: list[tuple[str, list[str]]] = []
    for val in major_vals:
        ids = (
            meta_for_samples.index[(~missing_mask) & (series_str == val)]
            .astype(str)
            .tolist()
        )
        groups.append((str(val), ids))
    other_mask = missing_mask | series_str.isin(minor_set)
    other_ids = meta_for_samples.index[other_mask].astype(str).tolist()
    if other_ids:
        groups.append((other_label, other_ids))
    return groups


def hierarchical_split(
    meta_for_samples: pd.DataFrame,
    sample_ids: list[str] | pd.Index | None,
    levels: list[str],
    min_group_size: int,
    other_label: str = "other",
) -> dict[str, Any]:
    """Recursively split ``sample_ids`` by each metadata column in ``levels``.

    At each level: major groups (size ≥ ``min_group_size``) recurse into the
    next level; the pooled ``other`` bucket does not recurse further. The
    whole-set node carries ``level_col=None``.

    Returns a tree of nodes::

        {
          "label":     "<this group's label>",       # "__whole_set__" at root
          "level_col": "Clonal group" | None,        # column used to split children
          "members":   [sample_id, ...],
          "subgroups": [<child node>, ...],          # [] when no further split
        }
    """
    if sample_ids is None:
        ids: list[str] = meta_for_samples.index.astype(str).tolist()
    else:
        ids = [str(x) for x in sample_ids]

    return _build_node(
        meta_for_samples,
        ids,
        label="__whole_set__",
        levels=levels,
        min_group_size=min_group_size,
        other_label=other_label,
    )


def _build_node(
    meta_for_samples: pd.DataFrame,
    ids: list[str],
    *,
    label: str,
    levels: list[str],
    min_group_size: int,
    other_label: str,
) -> dict[str, Any]:
    """Build one tree node, recursing into major children only."""
    if not levels or not ids:
        return {"label": label, "level_col": None, "members": ids, "subgroups": []}

    next_col = levels[0]
    remaining = levels[1:]
    sub_meta = meta_for_samples.reindex([str(x) for x in ids])
    children = split_samples(sub_meta, next_col, min_group_size, other_label)

    subgroups: list[dict[str, Any]] = []
    for child_label, child_ids in children:
        if child_label == other_label:
            # 'other' is a single non-recursive bucket at every level.
            subgroups.append(
                {
                    "label": child_label,
                    "level_col": None,
                    "members": child_ids,
                    "subgroups": [],
                }
            )
        else:
            subgroups.append(
                _build_node(
                    meta_for_samples,
                    child_ids,
                    label=child_label,
                    levels=remaining,
                    min_group_size=min_group_size,
                    other_label=other_label,
                )
            )

    return {
        "label": label,
        "level_col": next_col,
        "members": ids,
        "subgroups": subgroups,
    }
