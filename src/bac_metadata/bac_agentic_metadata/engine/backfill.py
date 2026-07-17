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
Per-sample extraction (per-sample, from the paper's tables) is a later stage.
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


#: Precedence rank for merging overlapping per-(sample, field) fills (lower wins). Per-sample is the
#: accurate per-isolate source; the two study-wide sources only ever filled blanks (parsimony guard),
#: so the only replacement of a real value comes from per-sample. Used by the enriched-table merge.
PRECEDENCE_DEFAULT: dict[str, int] = {
    "per_sample": 0, "per_sample_two_hop": 0, "curator_escalation": 1, "whole_field": 2,
}


def apply_precedence_merge(
    frames: list[pd.DataFrame],
    *,
    rank: dict[str, int] | None = None,
    key: tuple[str, ...] = ("sample_accession", "field"),
    value_col: str = "applied_value",
    method_col: str = "method",
) -> pd.DataFrame:
    """Resolve overlapping long-format fills to one winning row per ``key`` by source precedence.

    Each input frame is a long-format set of applied fills carrying the ``key`` columns, a
    ``value_col`` and a ``method_col`` naming the source. Placeholder/blank values are dropped, the
    remaining rows are ranked by ``rank[method]`` (lower wins; an unknown method ranks last), and the
    single highest-precedence non-blank fill per ``key`` is kept. Ties break deterministically on
    ``(_rank, method, value)`` so the result is reproducible. All other columns are preserved.

    Parameters
    ----------
    frames
        Long-format fill tables (e.g. per-sample, escalation, whole-field applied changes).
    rank
        ``method -> rank`` map (lower wins); defaults to :data:`PRECEDENCE_DEFAULT`.
    key
        Columns identifying a cell (default ``(sample_accession, field)``).
    value_col, method_col
        Column names holding the applied value and its source method.

    Returns
    -------
    pandas.DataFrame
        One winning row per ``key`` (plus a ``_rank`` column), or empty if no non-blank fills.
    """
    rank = dict(PRECEDENCE_DEFAULT if rank is None else rank)
    last = max(rank.values(), default=0) + 1
    parts: list[pd.DataFrame] = []
    for df in frames:
        if df is None or len(df) == 0:
            continue
        sub = df.copy()
        sub[value_col] = strip_placeholders(sub[value_col])
        sub = sub[sub[value_col].notna()]
        if len(sub) == 0:
            continue
        sub["_rank"] = sub[method_col].map(rank).fillna(last).astype(int)
        parts.append(sub)
    if not parts:
        return pd.DataFrame()
    merged = pd.concat(parts, ignore_index=True)
    merged = merged.sort_values([*key, "_rank", method_col, value_col])
    return merged.drop_duplicates(list(key), keep="first").reset_index(drop=True)


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


def per_sample_guards(
    per_sample: pd.DataFrame | None,
    *,
    fields: tuple[str, ...] = FIELDS,
    group_col: str = "study_accession",
    sample_col: str = "sample_accession",
    value_col: str = "applied_value",
    field_col: str = "field",
) -> tuple[dict[str, set[str]], set[tuple[str, str]]]:
    """Derive the two parsimony guards from per-sample fills: filled cells, and heterogeneous study×fields.

    Per-sample extraction is the ACCURATE, per-isolate source and runs FIRST; whole-field is the coarse
    study-wide fallback that may only fill the *remaining* genuine gaps and must never contradict the table.
    This returns:

    * ``filled`` — ``{field: {sample_accession, …}}`` the per-sample step already filled, so whole-field
      never **overwrites** a per-isolate value (e.g. it can't reassign a Ghana isolate to Italy).
    * ``heterogeneous`` — ``{(study, field), …}`` where per-sample extracted **>=2 distinct values**, proving
      the field is genuinely mixed across the study; a single whole-project value is then unjustified and the
      whole-field fill is **blocked** for that ``(study, field)`` (the residual goes to escalation, not a guess).

    Returns empty guards when ``per_sample`` is None/empty (whole-field then behaves as a pure ENA-blank fill).
    """
    filled: dict[str, set[str]] = {f: set() for f in fields}
    heterogeneous: set[tuple[str, str]] = set()
    if per_sample is None or not len(per_sample):
        return filled, heterogeneous
    if not {group_col, sample_col, field_col} <= set(per_sample.columns):
        return filled, heterogeneous
    ps = per_sample.copy()
    val = ps[value_col] if value_col in ps.columns else pd.Series("", index=ps.index)
    ps = ps.assign(_val=strip_placeholders(val))
    real = ps[ps["_val"].notna()]
    for f, g in real.groupby(field_col):
        if f in filled:
            filled[f] = set(g[sample_col].astype(str))
    distinct = real.groupby([group_col, field_col])["_val"].nunique()
    for (acc, f), nuniq in distinct.items():
        if int(nuniq) >= 2:
            heterogeneous.add((str(acc), str(f)))
    return filled, heterogeneous


def apply_whole_field(
    df: pd.DataFrame,
    proposals: dict[str, dict[str, dict]],
    needs: pd.DataFrame,
    *,
    fields: tuple[str, ...] = FIELDS,
    group_col: str = "study_accession",
    sample_col: str = "sample_accession",
    per_sample: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Fill genuinely-blank per-sample cells of gated fields with the whole-field proposal.

    A cell is filled only when ALL hold: (a) the study's field is gated (``needs``), (b) the grader
    proposed ``applies_whole_project`` with a non-empty value for it, (c) the sample's current
    (placeholder-stripped) value is blank, AND — when ``per_sample`` fills are supplied (the accurate
    per-isolate source, which runs FIRST) — (d) the per-sample step did not already fill that cell and the
    ``(study, field)`` is not per-sample-heterogeneous (see :func:`per_sample_guards`). Present values and
    per-isolate values are **never** overwritten; a single study-wide value is **never** forced onto a
    genuinely-mixed field. Vectorised per field.

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
    per_sample
        The per-sample fills (``per_sample_applied``) — the parsimony guard. When None, whole-field is a pure
        ENA-blank fill (backward-compatible).

    Returns
    -------
    pandas.DataFrame
        Long table of fills, columns :data:`_APPLIED_COLUMNS` (one row per filled cell).
    """
    ps_filled, ps_heterogeneous = per_sample_guards(
        per_sample, fields=fields, group_col=group_col, sample_col=sample_col
    )
    frames: list[pd.DataFrame] = []
    for f in fields:
        if f not in df.columns:
            continue
        gated = needs[f] if f in needs.columns else pd.Series(False, index=needs.index)
        gated_studies = {s for s in gated.index[gated.fillna(False).astype(bool)] if (s, f) not in ps_heterogeneous}
        val_map = {acc: (p.get(f) or {}).get("value", "") for acc, p in proposals.items()}
        wp_map = {acc: bool((p.get(f) or {}).get("whole_project")) for acc, p in proposals.items()}
        ev_map = {acc: (p.get(f) or {}).get("evidence", "") for acc, p in proposals.items()}

        sub = df[[group_col, sample_col, f]].copy()
        sub["_val"] = sub[group_col].map(val_map).fillna("").astype(str).str.strip()
        sub["_wp"] = sub[group_col].map(wp_map).fillna(False).astype(bool)
        sub["_ev"] = sub[group_col].map(ev_map).fillna("")
        sub["_stripped"] = strip_placeholders(sub[f])
        mask = sub[group_col].isin(gated_studies) & sub["_wp"] & (sub["_val"] != "") & sub["_stripped"].isna()
        if ps_filled.get(f):  # never overwrite a per-isolate value the per-sample step already placed
            mask &= ~sub[sample_col].astype(str).isin(ps_filled[f])
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


def _cmp_key(series: pd.Series, field: str | None = None) -> pd.Series:
    """Case-insensitive, whitespace-collapsed comparison key; field-aware where granularity differs.

    ``collection_date`` is compared at **year** granularity: a whole-study fill resolves the year
    (e.g. ``2008``) while the gold carries a full curated date (``2008/06/30`` parsed, ``2008.0`` raw),
    so a plain string match would spuriously score every year-level fill wrong. All other fields use the
    raw case/whitespace-folded key — correctness against the raw *or* parsed gold column (see
    :func:`value_correctness`) then absorbs vocabulary differences like ``Homo sapiens`` vs ``human``.
    """
    s = series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.lower()
    if field == "collection_date":
        s = s.str.extract(r"(\d{4})", expand=False)  # first 4-digit run = the year, on both sides
    return s


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
        ``{field: gold_column | [gold_columns]}`` — one or more candidate gold columns per field
        (default: identity). A fill counts as having gold if *any* candidate carries a value, and as
        correct if it matches *any* candidate's key — so passing both the raw and the curated
        ``_parsed`` column lets ``Homo sapiens`` match the raw host and ``human`` match the parsed one
        without the validator needing its own categorisation table.

    Returns
    -------
    pandas.DataFrame
        One row per field: ``filled``, ``has_gold``, ``correct``, ``accuracy``, plus the same triple
        split by whether the fill landed on a **blank** ENA cell (a positive fill) or **overwrote** a
        real ENA value (``{n_blank_fill,correct_blank_fill,acc_blank_fill}`` /
        ``{n_overwrite,correct_overwrite,acc_overwrite}``). The split uses the applied row's
        ``ena_value``: comparing an overwrite against a gold that *is* the raw ENA value the overwrite
        deliberately replaced scores it wrong by construction, so the two must be read separately (a
        pooled ``accuracy`` conflates near-perfect blank-fills with those gated overwrites).
    """
    gold_cols = gold_cols or {f: [f] for f in fields}
    gidx = gold.drop_duplicates(sample_col).set_index(sample_col)

    def _acc(correct: pd.Series, has_gold: pd.Series) -> dict:
        """Per-cell (correct, has_gold) booleans → {has_gold, correct, accuracy} counts."""
        n = int(has_gold.sum())
        c = int((correct & has_gold).sum())
        return {"has_gold": n, "correct": c, "accuracy": float(c / n) if n else float("nan")}

    rows = []
    for f in fields:
        sub = applied[applied["field"] == f]
        cands = gold_cols.get(f, [f])
        cands = [cands] if isinstance(cands, str) else list(cands)
        cands = [c for c in cands if c in gold.columns]
        base = {"field": f, "filled": int(len(sub)), "has_gold": 0, "correct": 0, "accuracy": float("nan"),
                "n_blank_fill": 0, "has_gold_blank": 0, "correct_blank_fill": 0, "acc_blank_fill": float("nan"),
                "n_overwrite": 0, "has_gold_overwrite": 0, "correct_overwrite": 0, "acc_overwrite": float("nan")}
        if not cands or len(sub) == 0:
            rows.append(base)
            continue
        akey = _cmp_key(sub["applied_value"], f)
        has_gold = pd.Series(False, index=sub.index)
        correct = pd.Series(False, index=sub.index)
        for c in cands:  # a cell is correct if the fill matches the raw OR the parsed gold value
            gmapped = sub[sample_col].map(strip_placeholders(gidx[c]))
            present = gmapped.notna()
            has_gold = has_gold | present
            correct = correct | (present & (akey == _cmp_key(gmapped, f))).fillna(False).astype(bool)
        # blank-fill vs overwrite: the ena_value the fill landed on (blank ⇒ positive fill; else overwrite)
        is_over = (strip_placeholders(sub["ena_value"]).notna() if "ena_value" in sub.columns
                   else pd.Series(False, index=sub.index))
        blank, over = _acc(correct[~is_over], has_gold[~is_over]), _acc(correct[is_over], has_gold[is_over])
        rows.append({**base, **_acc(correct, has_gold),
                     "n_blank_fill": int((~is_over).sum()), "has_gold_blank": blank["has_gold"],
                     "correct_blank_fill": blank["correct"], "acc_blank_fill": blank["accuracy"],
                     "n_overwrite": int(is_over.sum()), "has_gold_overwrite": over["has_gold"],
                     "correct_overwrite": over["correct"], "acc_overwrite": over["accuracy"]})
    return pd.DataFrame(rows)
