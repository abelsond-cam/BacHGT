"""Aggregate per-sample best-reference picks into a per-species summary.

Reads ``best_reference_per_sample.csv`` (produced by
``gpa_reference_granularity.py`` — one row per (Panaroo run, query sample) with
the best reference + shared-gene count at each granularity level f/d/c/b/a),
groups rows by ``species``, and emits one row per species summarising the
modal best reference + the median shared-gene count at level d (or all levels,
with ``--all-levels``).

This replaces the dropped level-e ``best_e_ref_per_species.tsv`` output (which
relied on the removed fixed reference bucket) with the same intent — a single
best reference per query species — but computed cheaply from the per-sample
picks already in the granularity output. For the non-KPSC species batches the
modal pick is typically the force-added mgh78578 reference, since that's the
only reference present in those runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

LEVELS_DEFAULT: tuple[str, ...] = ("d",)
LEVELS_ALL: tuple[str, ...] = ("f", "d", "c", "b", "a")


def _modal_pick(s: pd.Series) -> tuple[str | None, int]:
    """Return ``(modal value, its count)`` from ``s``; ties resolved lexicographically.

    Empty / all-NaN series returns ``(None, 0)``.
    """
    vc = s.dropna().value_counts()
    if vc.empty:
        return None, 0
    top_count = int(vc.iloc[0])
    top_vals = sorted(vc[vc == top_count].index.astype(str))
    return top_vals[0], top_count


def aggregate_species_reference(
    df: pd.DataFrame,
    levels: tuple[str, ...] = LEVELS_DEFAULT,
    non_kpsc_only: bool = False,
) -> pd.DataFrame:
    """Collapse per-(run, sample) best-ref picks into one row per species.

    Parameters
    ----------
    df
        ``best_reference_per_sample.csv`` loaded as a DataFrame; must have
        ``species``, ``ref_<lvl>`` and ``shared_<lvl>`` columns for each level
        in *levels* (rows missing them are tolerated — modal returns None).
    levels
        Granularity levels to summarise. Default is just ``("d",)`` (best ref
        across the whole run); pass :data:`LEVELS_ALL` for all of f/d/c/b/a.
    non_kpsc_only
        Keep only rows whose ``run`` value starts with ``non_kpsc_species_``
        (the non-KPSC species batches).

    Returns
    -------
    pd.DataFrame
        One row per species, sorted by species. Columns: ``species``,
        ``n_samples``, ``n_runs``, and for each level ``modal_ref_<lvl>``,
        ``modal_ref_<lvl>_count``, ``median_shared_<lvl>``.
    """
    if non_kpsc_only and "run" in df.columns:
        df = df[df["run"].astype(str).str.startswith("non_kpsc_species_")]

    grouped = df.groupby("species", dropna=True, sort=True)
    rows: list[dict] = []
    for species, g in grouped:
        row: dict = {
            "species": species,
            "n_samples": int(len(g)),
            "n_runs": int(g["run"].nunique()) if "run" in g.columns else 0,
        }
        for lvl in levels:
            ref_col = f"ref_{lvl}"
            shared_col = f"shared_{lvl}"
            ref_series = g[ref_col] if ref_col in g.columns else pd.Series(dtype=object)
            shared_series = (
                pd.to_numeric(g[shared_col], errors="coerce")
                if shared_col in g.columns
                else pd.Series(dtype=float)
            )
            modal_ref, modal_count = _modal_pick(ref_series)
            median_shared = (
                float(shared_series.median()) if not shared_series.dropna().empty else float("nan")
            )
            row[f"modal_ref_{lvl}"] = modal_ref
            row[f"modal_ref_{lvl}_count"] = modal_count
            row[f"median_shared_{lvl}"] = median_shared
        rows.append(row)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="best_reference_per_sample.csv produced by gpa_reference_granularity.py",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="output TSV path",
    )
    parser.add_argument(
        "--all-levels",
        action="store_true",
        help="emit modal/median columns for all levels (f, d, c, b, a) "
        "instead of just d (default).",
    )
    parser.add_argument(
        "--non-kpsc-only",
        action="store_true",
        help="keep only rows from non_kpsc_species_* runs.",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 1
    df = pd.read_csv(args.input)
    levels = LEVELS_ALL if args.all_levels else LEVELS_DEFAULT
    out = aggregate_species_reference(df, levels=levels, non_kpsc_only=args.non_kpsc_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, sep="\t", index=False)
    print(f"Wrote {len(out)} species rows -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
