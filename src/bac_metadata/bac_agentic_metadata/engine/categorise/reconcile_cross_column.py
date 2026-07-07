r"""Phase D — cross-column reconcile + value canonicalisation (pure rules, no LLM).

Two operations, both driven by the application ``attributes.yaml`` ``categorisation`` block, so they are
instant, deterministic and byte-stable on re-run:

* **``normalise_field``** — collapse a column's raw values onto a canonical set via a literal map
  (``cf_status``: ``Non-CF`` -> ``non-CF``; junk tokens -> blank).
* **``apply_cross_column``** — a value in one column implies a value in another. Each rule is
  ``{source_pattern | source_category, target_field, target_value, mode}``:
    - ``source_pattern`` matches (regex, from string start) against the RAW ``<field>`` column — e.g.
      host strain codes ``^CF\d`` -> ``cf_status = CF``.
    - ``source_category`` matches (exact membership) against the categorised ``<field>_category`` column
      — e.g. ``isolation_source_category in [water_environment]`` -> ``host_category = environment``.
  ``mode: fill`` writes the target only where it is BLANK and **escalates** a conflict (target already
  holds a different value) rather than overwriting it — the human-in-the-loop hybrid David chose.
  ``mode: set`` overwrites unconditionally (a correction, e.g. relabelling a mis-categorised host).

Nothing is silently changed: every reassignment lands in the returned audit frame, and every skipped
conflict in the escalation frame.
"""

from __future__ import annotations

import pandas as pd


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Return column ``name`` as a blank-filled string Series (creating an all-blank one if absent)."""
    if name in df.columns:
        return df[name].fillna("").astype(str)
    return pd.Series("", index=df.index, dtype="object")


def normalise_field(df: pd.DataFrame, field: str, mapping: dict[str, str]) -> tuple[pd.DataFrame, list[dict]]:
    """Canonicalise ``df[field]`` values via a literal ``{from: to}`` map.

    Parameters
    ----------
    df
        The table (modified on a copy).
    field
        Column to canonicalise; a no-op if absent.
    mapping
        ``{raw_value: canonical_value}`` — an empty ``to`` blanks the cell.

    Returns
    -------
    tuple[pandas.DataFrame, list[dict]]
        The updated table and a per-mapping change log ``{field, from, to, count}`` (only entries that
        actually matched rows).
    """
    out = df.copy()
    if field not in out.columns or not mapping:
        return out, []
    col = _col(out, field)
    changes: list[dict] = []
    for src, dst in mapping.items():
        hit = col == src
        n = int(hit.sum())
        if n:
            out.loc[hit, field] = dst
            changes.append({"field": field, "from": src, "to": dst, "count": n})
    return out, changes


def apply_cross_column(
    df: pd.DataFrame, field: str, rules: list[dict]
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """Apply the ``cross_column`` rules declared under one ``field`` to the table.

    Parameters
    ----------
    df
        The table (modified on a copy).
    field
        The ``categorisation.fields`` key the rules live under — resolves the source column:
        ``source_pattern`` reads raw ``<field>``; ``source_category`` reads ``<field>_category``.
        An explicit ``source_field`` in a rule overrides this.
    rules
        List of ``{source_pattern|source_category, target_field, target_value, mode}`` (``mode`` in
        ``{fill, set}``, default ``fill``).

    Returns
    -------
    tuple[pandas.DataFrame, list[dict], list[dict]]
        The updated table; an audit (one row per matched source value:
        ``{source_field, source_value, count, target_field, target_value, action}``); and an escalation
        list (``fill`` conflicts: ``{source_field, source_value, count, target_field, existing_value,
        proposed_value}``).
    """
    out = df.copy()
    audit: list[dict] = []
    escalations: list[dict] = []

    for rule in rules or []:
        target_field = rule["target_field"]
        target_value = rule["target_value"]
        mode = rule.get("mode", "fill")

        if "source_category" in rule:
            source_field = rule.get("source_field", f"{field}_category")
            src = _col(out, source_field)
            matched = src.isin([str(v) for v in rule["source_category"]])
        else:
            source_field = rule.get("source_field", field)
            src = _col(out, source_field)
            matched = src.str.match(rule["source_pattern"], na=False)

        if not matched.any():
            continue

        tgt = _col(out, target_field)
        if mode == "set":
            changed = matched & (tgt != target_value)
            out.loc[matched, target_field] = target_value
            for val, grp in src[changed].groupby(src[changed]):
                audit.append({
                    "source_field": source_field, "source_value": val, "count": int(len(grp)),
                    "target_field": target_field, "target_value": target_value, "action": "set",
                })
        else:  # fill: only blank targets; conflicting non-blank targets are escalated, never overwritten
            blank = tgt == ""
            fill_idx = matched & blank
            conflict_idx = matched & ~blank & (tgt != target_value)
            out.loc[fill_idx, target_field] = target_value
            for val, grp in src[fill_idx].groupby(src[fill_idx]):
                audit.append({
                    "source_field": source_field, "source_value": val, "count": int(len(grp)),
                    "target_field": target_field, "target_value": target_value, "action": "fill",
                })
            for val, grp in src[conflict_idx].groupby(src[conflict_idx]):
                existing = tgt[grp.index].value_counts().index[0]
                escalations.append({
                    "source_field": source_field, "source_value": val, "count": int(len(grp)),
                    "target_field": target_field, "existing_value": existing, "proposed_value": target_value,
                })
    return out, audit, escalations


def reconcile(df: pd.DataFrame, categorisation: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run every field's ``cross_column`` rules and ``normalise`` map from the spec's categorisation block.

    Parameters
    ----------
    df
        The applied/categorised per-sample table.
    categorisation
        ``spec.categorisation`` — ``{field: {cross_column: [...], normalise: {...}, ...}}``.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.DataFrame, pandas.DataFrame]
        The reconciled table, the reassignment audit (cross-column reassignments + normalise changes),
        and the escalation frame (fill conflicts to review).
    """
    out = df.copy()
    audit: list[dict] = []
    escalations: list[dict] = []

    # 1) cross-column rules (order: process every field's rules once, in declaration order).
    for field, cfg in categorisation.items():
        out, a, e = apply_cross_column(out, field, cfg.get("cross_column") or [])
        audit.extend(a)
        escalations.extend(e)

    # 2) value canonicalisation (after cross-column so a decode isn't clobbered by a later rename).
    for field, cfg in categorisation.items():
        out, changes = normalise_field(out, field, cfg.get("normalise") or {})
        for c in changes:
            audit.append({
                "source_field": field, "source_value": c["from"], "count": c["count"],
                "target_field": field, "target_value": c["to"], "action": "normalise",
            })

    audit_df = pd.DataFrame(
        audit,
        columns=["source_field", "source_value", "count", "target_field", "target_value", "action"],
    )
    esc_df = pd.DataFrame(
        escalations,
        columns=["source_field", "source_value", "count", "target_field", "existing_value", "proposed_value"],
    )
    return out, audit_df, esc_df
