"""Per-sample backfill of the four clinical fields (country / collection_date / isolation_source / host).

These fields are **genuinely per-sample** and ENA frequently leaves them blank. This module implements
the **completeness-gated, whole-field** pass (steps 1-2 of the plan):

1. **gate** — skip a study's field when ENA already fills it >= ``threshold`` (default 0.75): the
   depositors populated it, so there is no value in backfilling.
2. **whole-field fill** — for gated fields, fill the genuinely-blank per-sample cells with a single
   study-wide value the grader proposed (``applies_whole_project``); never overwrite a present value.

It is **raw-value only**: the ``pp.metadata_curation`` parse/categorise rule-system is downstream and
deliberately NOT used here (it has known-suspect rules and is a separate later workstream). The one
normalisation is a **standalone placeholder->NA strip** (:func:`strip_placeholders`) so completeness is
honest — ENA fields carry "Not available"/"not specified"/etc. text that looks populated but is empty.
Per-sample extraction (method-b, from the paper's tables) is a later stage.
"""

from __future__ import annotations

import pandas as pd

#: The four per-sample clinical fields this module backfills.
FIELDS: tuple[str, ...] = ("country", "collection_date", "isolation_source", "host")

#: Lower-cased, whitespace-collapsed text that LOOKS like a value but means "missing" in ENA fields.
#: Generalises the date-only ``pp.date_utils.step0_clean`` rule to all four fields. Standalone on
#: purpose — independent of the parse/categorise rule-system, which is out of scope here.
PLACEHOLDER_NULLS: frozenset[str] = frozenset(
    {
        "", "-", "--", ".", "na", "n/a", "nan", "none", "null", "unknown", "unspecified",
        "missing", "not collected", "notcollected", "not provided", "notprovided",
        "not applicable", "notapplicable", "not available", "notavailable",
        "not determined", "notdetermined", "not recorded", "not known", "no data", "undetermined",
    }
)


def strip_placeholders(series: pd.Series) -> pd.Series:
    """Return ``series`` with placeholder-null text (and blanks) set to NA, for honest completeness.

    A cell whose lower-cased, whitespace-collapsed value is in :data:`PLACEHOLDER_NULLS` is treated as
    missing. Genuine raw values are otherwise returned untouched (no spelling normalisation, no
    categorisation).

    Parameters
    ----------
    series
        Any column (string/object); coerced to the pandas ``string`` dtype for comparison.

    Returns
    -------
    pandas.Series
        ``series`` (as ``string`` dtype) with placeholders/blanks replaced by ``pd.NA``.
    """
    norm = series.astype("string").str.strip()
    key = norm.str.replace(r"\s+", " ", regex=True).str.lower()
    return norm.mask(norm.isna() | key.isin(PLACEHOLDER_NULLS), other=pd.NA)


def field_completeness(
    df: pd.DataFrame, fields: tuple[str, ...] = FIELDS, *, group_col: str = "study_accession"
) -> pd.DataFrame:
    """Per-study non-null fraction of each field, computed on **placeholder-stripped** values.

    Parameters
    ----------
    df
        Per-sample table with ``group_col`` plus the field columns.
    fields
        Fields to score (default :data:`FIELDS`); a missing column scores as all-blank.
    group_col
        Study key to group by (default ``"study_accession"``).

    Returns
    -------
    pandas.DataFrame
        Indexed by ``group_col`` with ``n_records`` plus one fraction column per field.
    """
    stripped = pd.DataFrame({group_col: df[group_col].astype("string")})
    for f in fields:
        stripped[f] = strip_placeholders(df[f]) if f in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    grouped = stripped.groupby(group_col, dropna=True)
    out = pd.DataFrame({"n_records": grouped.size()})
    for f in fields:
        out[f] = grouped[f].apply(lambda s: float(s.notna().mean()) if len(s) else float("nan"))
    return out


def gate_fields(
    completeness: pd.DataFrame, fields: tuple[str, ...] = FIELDS, *, threshold: float = 0.75
) -> pd.DataFrame:
    """Boolean "needs backfill" per study x field: True iff completeness < ``threshold``.

    A study with no records for a field (NaN completeness) counts as needing backfill.

    Parameters
    ----------
    completeness
        Output of :func:`field_completeness` (indexed by study).
    fields
        Fields to gate (default :data:`FIELDS`).
    threshold
        ENA non-null fraction at/above which a field is considered already complete (default 0.75).

    Returns
    -------
    pandas.DataFrame
        Same index as ``completeness`` with one boolean column per field.
    """
    needs = pd.DataFrame(index=completeness.index)
    for f in fields:
        col = completeness[f] if f in completeness.columns else pd.Series(float("nan"), index=completeness.index)
        needs[f] = col.fillna(0.0) < threshold
    return needs


_APPLIED_COLUMNS = ["study_accession", "sample_accession", "field", "ena_value", "applied_value", "method", "evidence"]


def apply_whole_field(
    df: pd.DataFrame,
    proposals: dict[str, dict[str, dict]],
    needs: pd.DataFrame,
    *,
    fields: tuple[str, ...] = FIELDS,
    group_col: str = "study_accession",
    sample_col: str = "sample_accession",
) -> pd.DataFrame:
    """Fill genuinely-blank per-sample cells of gated fields with the whole-field proposal.

    A cell is filled only when ALL hold: (a) the study's field is gated (``needs``), (b) the grader
    proposed ``applies_whole_project`` with a non-empty value for it, and (c) the sample's current
    (placeholder-stripped) value is blank. Present values are **never** overwritten. Vectorised per
    field.

    Parameters
    ----------
    df
        Raw per-sample table (``group_col``, ``sample_col``, the field columns).
    proposals
        ``{study_accession: {field: {"value": str, "whole_project": bool, "evidence": str}}}``.
    needs
        Output of :func:`gate_fields` (boolean per study x field).
    fields, group_col, sample_col
        Field list and key column names.

    Returns
    -------
    pandas.DataFrame
        Long table of fills, columns :data:`_APPLIED_COLUMNS` (one row per filled cell).
    """
    frames: list[pd.DataFrame] = []
    for f in fields:
        if f not in df.columns:
            continue
        gated = needs[f] if f in needs.columns else pd.Series(False, index=needs.index)
        gated_studies = set(gated.index[gated.fillna(False).astype(bool)])
        val_map = {acc: (p.get(f) or {}).get("value", "") for acc, p in proposals.items()}
        wp_map = {acc: bool((p.get(f) or {}).get("whole_project")) for acc, p in proposals.items()}
        ev_map = {acc: (p.get(f) or {}).get("evidence", "") for acc, p in proposals.items()}

        sub = df[[group_col, sample_col, f]].copy()
        sub["_val"] = sub[group_col].map(val_map).fillna("").astype(str).str.strip()
        sub["_wp"] = sub[group_col].map(wp_map).fillna(False).astype(bool)
        sub["_ev"] = sub[group_col].map(ev_map).fillna("")
        sub["_stripped"] = strip_placeholders(sub[f])
        mask = sub[group_col].isin(gated_studies) & sub["_wp"] & (sub["_val"] != "") & sub["_stripped"].isna()
        hit = sub[mask]
        if len(hit):
            frames.append(
                pd.DataFrame(
                    {
                        "study_accession": hit[group_col].to_numpy(),
                        "sample_accession": hit[sample_col].to_numpy(),
                        "field": f,
                        "ena_value": hit[f].to_numpy(),
                        "applied_value": hit["_val"].to_numpy(),
                        "method": "whole_field",
                        "evidence": hit["_ev"].to_numpy(),
                    }
                )
            )
    if frames:
        return pd.concat(frames, ignore_index=True)[_APPLIED_COLUMNS]
    return pd.DataFrame(columns=_APPLIED_COLUMNS)


def _cmp_key(series: pd.Series) -> pd.Series:
    """Case-insensitive, whitespace-collapsed key for raw-value equality (no categorisation)."""
    return series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.lower()


def value_correctness(
    applied: pd.DataFrame,
    gold: pd.DataFrame,
    *,
    fields: tuple[str, ...] = FIELDS,
    sample_col: str = "sample_accession",
    gold_cols: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Score applied fills against a per-sample gold table (raw values, placeholder-stripped).

    For each field, joins ``applied`` to ``gold`` on ``sample_col`` and compares the filled value to
    the gold value (both placeholder-stripped, case-insensitive). Reports, per field, how many cells
    were filled, how many have a gold value to check against, and the value-accuracy on those.

    Parameters
    ----------
    applied
        Output of :func:`apply_whole_field`.
    gold
        Per-sample gold table (e.g. ``metadata_v2``) with ``sample_col`` + the gold value columns.
    fields
        Fields to score.
    sample_col
        Per-sample join key present in both ``applied`` and ``gold``.
    gold_cols
        ``{field: gold_column}`` (default: identity — same names as ``fields``).

    Returns
    -------
    pandas.DataFrame
        One row per field: ``filled``, ``has_gold``, ``correct``, ``accuracy``.
    """
    gold_cols = gold_cols or {f: f for f in fields}
    rows = []
    for f in fields:
        sub = applied[applied["field"] == f]
        gcol = gold_cols.get(f, f)
        if gcol not in gold.columns or len(sub) == 0:
            rows.append({"field": f, "filled": len(sub), "has_gold": 0, "correct": 0, "accuracy": float("nan")})
            continue
        gvals = strip_placeholders(gold.drop_duplicates(sample_col).set_index(sample_col)[gcol])
        merged = sub.assign(gold=sub[sample_col].map(gvals))
        has_gold = merged["gold"].notna()
        correct = has_gold & (_cmp_key(merged["applied_value"]) == _cmp_key(merged["gold"]))
        n_gold = int(has_gold.sum())
        rows.append(
            {
                "field": f,
                "filled": int(len(sub)),
                "has_gold": n_gold,
                "correct": int(correct.sum()),
                "accuracy": float(correct.sum() / n_gold) if n_gold else float("nan"),
            }
        )
    return pd.DataFrame(rows)
