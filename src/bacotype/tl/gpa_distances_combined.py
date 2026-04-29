#!/usr/bin/env python3
"""Combined GPA-distances analysis across Panaroo runs.

Discovers every ``gpa_distances_detail_*.tsv`` under

    <data_dir>/<run>/analysis/GPA_reference_genome/

concatenates them into one table, slices to a chosen ``group_level`` (default
``'clonal_group'``), deduplicates by ``strain`` keeping the row with the
largest ``n_samples``, and drives the epidemic-vs-mixed-strain comparison
from :mod:`bacotype.pl.epidemic_vs_mixed` over one or more metrics.

Three modes:

* ``combined`` - concatenate across all runs and analyse the combined
  (sliced + deduped) table; outputs under ``<data_dir>/genome_stats/`` and
  per-metric under ``<data_dir>/genome_stats/<metric>/``.
* ``per-run`` - analyse each run's own detail TSV in isolation; outputs
  under ``<data_dir>/<run>/genome_stats/`` and per-metric in subfolders as above.
* ``both`` - run both of the above.

By default, if ``<data_dir>/genome_stats/gpa_distances_detail.tsv`` already
exists, it is **not** rebuilt from per-run TSVs; the existing file is loaded.
Pass ``--recompile`` to re-concatenate all subfolders and overwrite that table.

By default, every metric with both mean and SD columns in the sliced+deduped
table is analysed (or pass ``--metrics`` to restrict). Outputs are written per
metric under ``<out_dir>/<metric_name>/`` (e.g. ``epidemic_vs_mixed_panaroo_genes_stats.tsv``).
A run summary table ``epidemic_vs_mixed_metric_summary.tsv`` at the top of
``out_dir`` ranks metrics by the count of rows with ``p_bonferroni_m < 0.01``.

Both naming conventions (``mean_<m>/sd_<m>`` and ``<m>_mean/<m>_sd``) are
recognised by :func:`bacotype.pl.epidemic_vs_mixed.resolve_mean_sd_columns`.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from collections.abc import Iterable, Sequence

print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: stdlib modules loaded",
    flush=True,
)

import pandas as pd

print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: pandas loaded",
    flush=True,
)

from bacotype.pl.epidemic_vs_mixed import epidemic_vs_mixed_strain_comparison

print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: bacotype.pl.epidemic_vs_mixed loaded",
    flush=True,
)

from bacotype.tl.gpa_distances_single_group import PANAROO_RUN_ROOT
from bacotype.tl.gpa_epidemic_row_class import (
    EPIDEMIC_ROW_CLASS_COL,
    IS_EPIDEMIC_GPA_CLONAL_TARGET_COL,
    add_epidemic_row_class_column,
)

print(
    f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] import checkpoint: bacotype.tl.gpa_distances_single_group loaded",
    flush=True,
)

DEFAULT_DATA_DIR = PANAROO_RUN_ROOT
# CLI default for metrics: None = use every metric with a valid mean/SD pair.
DEFAULT_GROUP_LEVEL = "clonal_group"
SIGNIFICANCE_THRESHOLD = 0.01
SUMMARY_TSV_NAME = "epidemic_vs_mixed_metric_summary.tsv"
DEFAULT_GROUP_COUNT_COL = "n_unique_clonal_groups"
DETAIL_GLOB = os.path.join(
    "*", "analysis", "GPA_reference_genome", "gpa_distances_detail_*.tsv"
)
COMBINED_SUBDIR = "genome_stats"
COMBINED_TSV_NAME = "gpa_distances_detail.tsv"


def combined_tsv_path(data_dir: str) -> str:
    """Path to the concatenated detail table under ``data_dir``."""
    return os.path.join(data_dir, COMBINED_SUBDIR, COMBINED_TSV_NAME)


def _tslog(message: str) -> None:
    """Print a timestamped progress line."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {message}", flush=True)


def _available_metric_bases(df: pd.DataFrame) -> list[str]:
    """Detect metric bases from both mean/sd naming conventions.

    Included bases must have both mean and sd columns in either:
    - ``mean_<base>`` and ``sd_<base>``
    - ``<base>_mean`` and ``<base>_sd``
    """
    starts = {
        c[len("mean_") :]
        for c in df.columns
        if c.startswith("mean_") and f"sd_{c[len('mean_') :]}" in df.columns
    }
    ends = {
        c[: -len("_mean")]
        for c in df.columns
        if c.endswith("_mean") and f"{c[: -len('_mean')]}_sd" in df.columns
    }
    return sorted(starts | ends)


def _discover_detail_tsvs(data_dir: str) -> list[str]:
    """Return sorted absolute paths of per-run detail TSVs under ``data_dir``."""
    _tslog(f"Discovering detail TSVs under: {data_dir}")
    pattern = os.path.join(data_dir, DETAIL_GLOB)
    paths = sorted(glob.glob(pattern))
    _tslog(f"Detail TSV discovery complete: n={len(paths)}")
    return paths


def load_and_concat_detail_tsvs(
    data_dir: str,
    *,
    write_tsv: bool = True,
    recompile: bool = False,
) -> pd.DataFrame:
    """Concatenate all per-run ``gpa_distances_detail_*.tsv`` under ``data_dir``.

    Adds a ``source_tsv`` column (absolute path) and a ``run_dir`` column
    (leaf directory name of the Panaroo run). Prints the number of TSVs
    found and total rows concatenated. If ``write_tsv`` is True, writes the
    result to ``<data_dir>/genome_stats/gpa_distances_detail.tsv``.

    If that combined TSV **already exists** and ``recompile`` is False, the
    file is read and returned without scanning or merging per-run TSVs.
    Set ``recompile`` to True to force a full re-concatenation and overwrite
    (when ``write_tsv`` is True).
    """
    out_path = combined_tsv_path(data_dir)
    if not recompile and os.path.isfile(out_path):
        _tslog(
            f"Using existing combined TSV (use recompile=True or --recompile to "
            f"rebuild from per-run files): {out_path}"
        )
        combined = pd.read_csv(out_path, sep="\t")
        need_classification = (
            EPIDEMIC_ROW_CLASS_COL not in combined.columns
            or IS_EPIDEMIC_GPA_CLONAL_TARGET_COL not in combined.columns
        )
        if need_classification:
            _tslog(
                "Backfilling epidemic classification columns on existing combined TSV"
            )
            combined = add_epidemic_row_class_column(
                combined,
                target_group_level=DEFAULT_GROUP_LEVEL,
                group_count_col=DEFAULT_GROUP_COUNT_COL,
            )
            if write_tsv:
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                combined.to_csv(out_path, sep="\t", index=False)
                _tslog(f"Wrote updated combined TSV: {out_path}")
        return combined

    paths = _discover_detail_tsvs(data_dir)
    if not paths:
        raise FileNotFoundError(
            f"No detail TSVs found under {data_dir} matching {DETAIL_GLOB!r}."
        )
    _tslog(f"Found {len(paths)} detail TSV files under {data_dir}")

    frames = []
    for i, p in enumerate(paths, start=1):
        _tslog(f"Reading detail TSV {i}/{len(paths)}: {p}")
        df = pd.read_csv(p, sep="\t")
        df["source_tsv"] = p
        rel = os.path.relpath(p, data_dir)
        run_dir = rel.split(os.sep, 1)[0]
        df["run_dir"] = run_dir
        frames.append(df)

    _tslog("Concatenating sub-tables into one combined dataframe")
    combined = pd.concat(frames, axis=0, ignore_index=True)
    _tslog(
        f"Concatenation complete: rows={len(combined)}, cols={combined.shape[1]}"
    )

    _tslog("Adding structural epidemic row class column")
    combined = add_epidemic_row_class_column(
        combined,
        target_group_level=DEFAULT_GROUP_LEVEL,
        group_count_col=DEFAULT_GROUP_COUNT_COL,
    )

    if write_tsv:
        out_dir = os.path.join(data_dir, COMBINED_SUBDIR)
        os.makedirs(out_dir, exist_ok=True)
        _tslog(f"Writing combined TSV: {out_path}")
        combined.to_csv(out_path, sep="\t", index=False)
        _tslog(f"Wrote combined TSV: {out_path}")

    return combined


def slice_and_dedup(
    df: pd.DataFrame,
    *,
    group_level: str = DEFAULT_GROUP_LEVEL,
    weight_col: str = "n_samples",
    strain_col: str = "strain",
    group_level_col: str = "group_level",
    group_label_col: str = "group_label",
    other_label: str = "other",
) -> pd.DataFrame:
    """Filter to ``group_level_col == group_level`` and dedup by ``strain_col``.

    For rows sharing a ``strain``, keep the row with the largest
    ``weight_col`` (first occurrence wins on ties, via stable sort). Rows
    whose ``group_label_col`` equals ``other_label`` are preserved as-is and
    NOT deduplicated: they form the pooled per-run "other" comparator used
    downstream, and there is expected to be one such row per input
    sub-table. Collapsing them by strain would double/undercount the
    comparator pool.
    """
    if group_level_col not in df.columns:
        raise KeyError(
            f"Input df missing group-level column {group_level_col!r}. "
            f"Columns: {list(df.columns)[:20]}..."
        )
    sliced = df[df[group_level_col] == group_level].copy()
    _tslog(
        f"Slice {group_level_col}=={group_level!r}: "
        f"{len(sliced)} rows (from {len(df)})."
    )
    if sliced.empty:
        return sliced

    if strain_col not in sliced.columns:
        raise KeyError(f"Sliced df missing strain column {strain_col!r}.")
    if weight_col not in sliced.columns:
        raise KeyError(f"Sliced df missing weight column {weight_col!r}.")
    if group_label_col not in sliced.columns:
        raise KeyError(
            f"Sliced df missing group-label column {group_label_col!r}."
        )

    is_other = sliced[group_label_col].astype(str) == other_label
    others = sliced[is_other].copy()
    non_other = sliced[~is_other].copy()

    ordered = non_other.sort_values(
        by=[strain_col, weight_col],
        ascending=[True, False],
        kind="mergesort",  # stable: first row wins on ties
    )
    non_other_dedup = ordered.drop_duplicates(subset=[strain_col], keep="first")

    deduped = pd.concat([non_other_dedup, others], axis=0, ignore_index=True)
    _tslog(
        f"Dedup by {strain_col!r} (max {weight_col}) on non-{other_label!r} rows: "
        f"{len(non_other_dedup)} unique strains (from {len(non_other)}); "
        f"preserved {len(others)} {other_label!r} rows."
    )
    return deduped


def run_analysis_for_detail_file(
    detail: str | pd.DataFrame,
    out_dir: str,
    *,
    group_level: str = DEFAULT_GROUP_LEVEL,
    group_count_col: str = DEFAULT_GROUP_COUNT_COL,
    weight_col: str = "n_samples",
    metrics: Sequence[str] | None = None,
    show_plot: bool = True,
    show_table: bool = True,
) -> tuple[dict[str, pd.DataFrame | None], list[str]]:
    """Reusable unit: slice + dedup + per-metric epidemic-vs-mixed comparison.

    ``detail`` can be a path to a single per-run detail TSV or an already-loaded
    DataFrame (e.g. the combined one). Per-metric stats and plots are written
    under ``out_dir/<metric>/``. A summary TSV is written at ``out_dir``.

    If ``metrics`` is ``None`` (default), all bases returned by
    :func:`_available_metric_bases` on the deduped table are analysed.

    Returns
    -------
    results
        Dict mapping metric name to its ``out_df`` (or ``None`` when the
        comparison could not be run).
    saved_outputs
        List of concrete output files that were confirmed to exist on disk.
    """
    if isinstance(detail, str):
        _tslog(f"Starting analysis for TSV input: {detail} -> {out_dir}")
        df = pd.read_csv(detail, sep="\t")
    else:
        _tslog(f"Starting analysis for in-memory df ({len(detail)} rows) -> {out_dir}")
        df = detail

    deduped = slice_and_dedup(
        df,
        group_level=group_level,
        weight_col=weight_col,
    )
    # Diagnostic: distribution of group-count values before/after dedup helps
    # explain why there may be no targets (==1) or many suspect zeros.
    sliced_df = df[df["group_level"] == group_level].copy()
    if group_count_col in sliced_df.columns:
        vc_pre = sliced_df[group_count_col].value_counts(dropna=False).sort_index()
        _tslog(f"{group_count_col} distribution in sliced rows (pre-dedup):")
        for val, cnt in vc_pre.items():
            print(f"  - {group_count_col}={val}: n={int(cnt)}", flush=True)
    else:
        _tslog(f"Column missing in sliced rows: {group_count_col}")

    if deduped.empty:
        _tslog(f"No rows after slice/dedup for out_dir={out_dir}; skipping.")
        return {}, []

    if group_count_col in deduped.columns:
        vc_post = deduped[group_count_col].value_counts(dropna=False).sort_index()
        _tslog(f"{group_count_col} distribution in deduped rows:")
        for val, cnt in vc_post.items():
            print(f"  - {group_count_col}={val}: n={int(cnt)}", flush=True)

        zero_rows = deduped[deduped[group_count_col] == 0]
        if not zero_rows.empty:
            _tslog(
                f"WARNING: deduped rows with {group_count_col}==0: n={len(zero_rows)}"
            )
            preview_cols = [
                c
                for c in ("strain", "directory_leaf", "run_dir", "source_tsv", "n_samples")
                if c in zero_rows.columns
            ]
            if preview_cols:
                _tslog(
                    f"Preview first rows with {group_count_col}==0 "
                    f"(cols={preview_cols}):"
                )
                for row in zero_rows[preview_cols].head(20).to_dict("records"):
                    print(f"  - {row}", flush=True)

    available_metrics = _available_metric_bases(deduped)
    _tslog(
        "Detected metric bases from mean/sd columns: "
        + (", ".join(available_metrics) if available_metrics else "<none>")
    )
    if metrics is None:
        metrics = tuple(available_metrics)
        _tslog(
            f"Using all detected metrics (none requested explicitly): n={len(metrics)}"
        )
    else:
        metrics = tuple(metrics)
        if not metrics:
            _tslog("Empty metrics list requested; skipping per-metric outputs.")
            return {}, []
        _tslog(f"Input metrics requested: {', '.join(metrics)}")

    if not metrics:
        _tslog("No detectable mean/sd metrics; skipping per-metric outputs.")
        return {}, []

    os.makedirs(out_dir, exist_ok=True)
    _tslog(f"Ensured output directory exists: {out_dir}")

    results: dict[str, pd.DataFrame | None] = {}
    saved_outputs: list[str] = []
    for metric in metrics:
        metric_out_dir = os.path.join(out_dir, metric)
        os.makedirs(metric_out_dir, exist_ok=True)
        _tslog(f"Starting metric analysis: {metric!r} -> {metric_out_dir}")
        try:
            out_df, _rest_mean, _rest_var = epidemic_vs_mixed_strain_comparison(
                deduped,
                metric=metric,
                group_count_col=group_count_col,
                weight_col=weight_col,
                show_table=show_table,
                show_plot=show_plot,
                out_dir=metric_out_dir,
            )
            _tslog(f"Finished metric analysis: {metric!r}")
        except KeyError as exc:
            _tslog(f"Skipping metric={metric!r}: {exc}")
            out_df = None
        results[metric] = out_df

        stats_path = os.path.join(
            metric_out_dir, f"epidemic_vs_mixed_{metric}_stats.tsv"
        )
        plot_path = os.path.join(
            metric_out_dir, f"epidemic_vs_mixed_{metric}.png"
        )
        if os.path.isfile(stats_path):
            saved_outputs.append(stats_path)
            _tslog(f"Output saved: {stats_path}")
        else:
            _tslog(f"Output missing: {stats_path}")
        if os.path.isfile(plot_path):
            saved_outputs.append(plot_path)
            _tslog(f"Output saved: {plot_path}")
        else:
            _tslog(f"Output missing: {plot_path}")

    summary_rows: list[dict[str, object]] = []
    for metric, out_df in results.items():
        n_sig = 0
        if out_df is not None and "p_bonferroni_m" in out_df.columns:
            n_sig = int(
                (out_df["p_bonferroni_m"] < SIGNIFICANCE_THRESHOLD).sum()
            )
        summary_rows.append({"metric": metric, "n_significant": n_sig})
    if summary_rows:
        summary_df = (
            pd.DataFrame(summary_rows)
            .sort_values(
                ["n_significant", "metric"],
                ascending=[False, True],
                kind="mergesort",
            )
            .reset_index(drop=True)
        )
        summary_path = os.path.join(out_dir, SUMMARY_TSV_NAME)
        summary_df.to_csv(summary_path, sep="\t", index=False)
        saved_outputs.append(summary_path)
        _tslog(
            f"Metric summary (p_bonferroni_m < {SIGNIFICANCE_THRESHOLD}):"
        )
        print(summary_df.to_string(index=False), flush=True)
        _tslog(f"Wrote summary: {summary_path}")

    if saved_outputs:
        _tslog("Saved outputs for this analysis:")
        for p in saved_outputs:
            print(f"  - {p}", flush=True)
    else:
        _tslog("No per-metric output files were created for this analysis.")

    return results, saved_outputs


def run_combined(
    data_dir: str,
    *,
    group_level: str = DEFAULT_GROUP_LEVEL,
    group_count_col: str = DEFAULT_GROUP_COUNT_COL,
    weight_col: str = "n_samples",
    metrics: Sequence[str] | None = None,
    recompile: bool = False,
) -> None:
    """Load or build the combined detail TSV and analyse the combined set.

    The combined table is only rebuilt from all per-run TSVs when
    ``recompile`` is True or the output file is missing. Otherwise the
    existing ``gpa_distances_detail.tsv`` is read.
    """
    combined_df = load_and_concat_detail_tsvs(
        data_dir, write_tsv=True, recompile=recompile
    )
    out_dir = os.path.join(data_dir, COMBINED_SUBDIR)
    _, saved_outputs = run_analysis_for_detail_file(
        combined_df,
        out_dir,
        group_level=group_level,
        group_count_col=group_count_col,
        weight_col=weight_col,
        metrics=metrics,
    )
    combined_tsv = combined_tsv_path(data_dir)
    _tslog("Combined-mode saved outputs:")
    if os.path.isfile(combined_tsv):
        print(f"  - {combined_tsv}", flush=True)
    else:
        print(f"  - MISSING: {combined_tsv}", flush=True)
    if saved_outputs:
        for p in saved_outputs:
            print(f"  - {p}", flush=True)
    else:
        print("  - No metric output files saved.", flush=True)
    _tslog("=== run_combined: end ===")


def run_per_run(
    data_dir: str,
    *,
    group_level: str = DEFAULT_GROUP_LEVEL,
    group_count_col: str = DEFAULT_GROUP_COUNT_COL,
    weight_col: str = "n_samples",
    metrics: Sequence[str] | None = None,
) -> None:
    """Run the analysis on each panaroo-run detail TSV individually."""
    _tslog("=== run_per_run: start ===")
    paths = _discover_detail_tsvs(data_dir)
    if not paths:
        raise FileNotFoundError(
            f"No detail TSVs found under {data_dir} matching {DETAIL_GLOB!r}."
        )
    _tslog(f"Per-run mode: {len(paths)} detail TSVs discovered.")
    for i, p in enumerate(paths, start=1):
        rel = os.path.relpath(p, data_dir)
        run_dir_name = rel.split(os.sep, 1)[0]
        _tslog(f"Per-run analysis {i}/{len(paths)}: {run_dir_name}")
        out_dir = os.path.join(data_dir, run_dir_name, COMBINED_SUBDIR)
        _, saved_outputs = run_analysis_for_detail_file(
            p,
            out_dir,
            group_level=group_level,
            group_count_col=group_count_col,
            weight_col=weight_col,
            metrics=metrics,
        )
        _tslog(f"Per-run output summary ({run_dir_name}):")
        if saved_outputs:
            for out_path in saved_outputs:
                print(f"  - {out_path}", flush=True)
        else:
            print("  - No metric output files saved.", flush=True)
    _tslog("=== run_per_run: end ===")


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Combined + per-run epidemic-vs-mixed-strain analysis over "
            "gpa_distances_detail_*.tsv files."
        )
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=(
            "Root directory whose immediate children are Panaroo runs; each "
            "run contains analysis/GPA_reference_genome/gpa_distances_detail_*.tsv. "
            f"Default: {DEFAULT_DATA_DIR}"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("combined", "per-run", "both"),
        default="combined",
        help="Analysis mode (default: combined).",
    )
    parser.add_argument(
        "--group-level",
        default=DEFAULT_GROUP_LEVEL,
        help=(
            "Value of 'group_level' column to slice to "
            f"(default: {DEFAULT_GROUP_LEVEL})."
        ),
    )
    parser.add_argument(
        "--group-count-col",
        default=DEFAULT_GROUP_COUNT_COL,
        help=(
            "Column whose value == 1 marks a 'single-strain' row "
            f"(default: {DEFAULT_GROUP_COUNT_COL})."
        ),
    )
    parser.add_argument(
        "--weight-col",
        default="n_samples",
        help="Per-row sample count column (default: n_samples).",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=None,
        metavar="METRIC",
        help=(
            "Metric base names to analyse (e.g. panaroo_genes core_genes). "
            "Omit the flag, or pass no values, to run every metric that has a "
            "valid mean/SD column pair. Both mean_<m>/sd_<m> and <m>_mean/<m>_sd "
            "naming conventions are recognised."
        ),
    )
    parser.add_argument(
        "--recompile",
        action="store_true",
        help=(
            "In combined (or both) mode: re-concatenate all per-run "
            f"``{os.path.basename(DETAIL_GLOB)}`` under --data-dir and overwrite "
            f"``{COMBINED_SUBDIR}/{COMBINED_TSV_NAME}``. "
            "Default: use the existing combined TSV if it is already present."
        ),
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    """Parse CLI args and run combined/per-run analysis workflows."""
    _tslog("gpa_distances_combined.py main() start")
    args = _parse_args(argv)
    metrics_kw: tuple[str, ...] | None
    if args.metrics:
        metrics_kw = tuple(args.metrics)
    else:
        metrics_kw = None
    _tslog(
        "Parsed args: "
        f"mode={args.mode}, data_dir={args.data_dir}, "
        f"group_level={args.group_level}, group_count_col={args.group_count_col}, "
        f"weight_col={args.weight_col}, metrics={metrics_kw}, "
        f"recompile={args.recompile}"
    )

    kwargs = {
        "group_level": args.group_level,
        "group_count_col": args.group_count_col,
        "weight_col": args.weight_col,
        "metrics": metrics_kw,
    }

    if args.mode in ("combined", "both"):
        run_combined(args.data_dir, recompile=args.recompile, **kwargs)
    if args.mode in ("per-run", "both"):
        run_per_run(args.data_dir, **kwargs)
    _tslog("gpa_distances_combined.py main() end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
