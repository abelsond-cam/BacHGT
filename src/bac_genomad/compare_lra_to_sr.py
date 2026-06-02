#!/usr/bin/env python3
"""Paired LRA-vs-SR comparison of geNomad plasmid + virus calls.

Two subcommands:

  aggregate — collapse the per-contig long TSVs into a per-Sample count table:
              ``Sample | source | n_plasmid_contigs | n_virus_provirus |
              n_virus_whole_contig | n_virus_total``. The universe is taken
              from ``genomad_inputs.tsv`` so the ~94 zero-call Samples in the
              2026-06-02 run (sentinel present, header-only summary TSVs)
              appear as 0/0/0/0 rather than dropping out.

  compare   — for each of four nested LRA cohorts (reference_genome ⊂ is_hybrid
              and is_complete ⊂ lra_final_list), join the per-sample counts
              against the paired SR partner (keyed ``<Sample>__sr`` in the
              geNomad outputs) and write one wide TSV + one summary TSV per
              cohort. Adds ``n_full_prophage`` — proviruses bounded by host
              sequence on BOTH sides (``coord_start > 1 AND coord_end <
              host_contig_length``) — distinguishing complete integrations
              from proviruses truncated by a contig edge. Host-contig lengths
              are computed once from the paired FASTAs and cached as
              ``contig_lengths_paired.tsv`` beside the outputs.

Cohort filters are read straight from ``paired_index.tsv`` (every paired_index
row is already in ``lra_final_list``, so ``lra_final_list`` is just the full
paired index — no extra filter needed). Reuses the True/False-string parse
idiom from ``bac_complete_genomes/compare_lra_to_sra.py``.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from bac_genomad.genomad_constants import (
    DEFAULT_COMPARE_OUT_DIR,
    DEFAULT_INPUTS_TSV,
    DEFAULT_PAIRED_INDEX,
    DEFAULT_PLASMID_LONG_TSV,
    DEFAULT_VIRUS_LONG_TSV,
    SR_PAIRED_SUFFIX,
)

# Cohort filters applied to paired_index. The value is the column name to test
# True on (or None for "no filter — use the full paired_index").
COHORTS: list[tuple[str, str | None]] = [
    ("reference_genome", "lra_is_reference_genome"),
    ("is_hybrid", "lra_is_hybrid"),
    ("is_complete", "lra_is_complete"),
    ("lra_final_list", None),
]

TRUE_TOKENS = frozenset({"true", "1", "yes"})

METRIC_COLS = (
    "n_plasmid_contigs",
    "n_virus_provirus",
    "n_virus_whole_contig",
    "n_virus_total",
)


# ─── shared helpers ───────────────────────────────────────────────────────────


def _truthy(series: pd.Series) -> pd.Series:
    """Parse a column of mixed True/False/bool/str values into a bool mask."""
    return series.astype(str).str.lower().isin(TRUE_TOKENS)


def _read_inputs_universe(inputs_tsv: Path) -> pd.DataFrame:
    """Read ``genomad_inputs.tsv`` (Sample, fasta_path, source) — the run universe."""
    if not inputs_tsv.exists():
        sys.exit(f"missing inputs TSV: {inputs_tsv}")
    df = pd.read_csv(inputs_tsv, sep="\t", dtype=str)
    needed = {"Sample", "fasta_path", "source"}
    missing = needed - set(df.columns)
    if missing:
        sys.exit(f"{inputs_tsv} missing columns: {sorted(missing)}")
    return df


# ─── AGGREGATE ────────────────────────────────────────────────────────────────


def cmd_aggregate(args: argparse.Namespace) -> int:
    """Build the per-Sample count table from the two long TSVs."""
    inputs = _read_inputs_universe(args.inputs)
    samples = inputs["Sample"].astype(str)
    print(f"universe: {len(samples):,} Samples from {args.inputs}")

    print(f"reading {args.plasmid_long} ...")
    plasmid = pd.read_csv(args.plasmid_long, sep="\t", usecols=["Sample"], dtype=str)
    n_plasmid = plasmid.groupby("Sample").size().rename("n_plasmid_contigs")
    print(f"  {len(plasmid):,} plasmid rows over {n_plasmid.size:,} Samples")

    print(f"reading {args.virus_long} ...")
    virus = pd.read_csv(args.virus_long, sep="\t", usecols=["Sample", "topology"], dtype=str)
    is_provirus = virus["topology"].fillna("") == "Provirus"
    n_pv = virus.loc[is_provirus].groupby("Sample").size().rename("n_virus_provirus")
    n_wc = virus.loc[~is_provirus].groupby("Sample").size().rename("n_virus_whole_contig")
    print(
        f"  {len(virus):,} virus rows over {virus['Sample'].nunique():,} Samples"
        f" (provirus={int(is_provirus.sum()):,}, whole-contig={int((~is_provirus).sum()):,})"
    )

    counts = pd.DataFrame(index=samples).join([n_plasmid, n_pv, n_wc]).fillna(0).astype(int)
    counts["n_virus_total"] = counts["n_virus_provirus"] + counts["n_virus_whole_contig"]
    out = (
        inputs[["Sample", "source"]]
        .merge(counts.reset_index(), on="Sample", how="left")
        .reindex(columns=["Sample", "source", *METRIC_COLS])
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "per_sample_counts.tsv"
    out.to_csv(out_path, sep="\t", index=False)
    print(f"\nwrote {out_path}  rows={len(out):,}")
    print("  zero-call (all 4 metrics == 0):", int((out[list(METRIC_COLS)].sum(axis=1) == 0).sum()))
    for src, sub in out.groupby("source"):
        print(f"  source={src:<10} n={len(sub):>6,}  mean_n_plasmid={sub['n_plasmid_contigs'].mean():.2f}")
    return 0


# ─── CONTIG LENGTHS (sidecar for `compare`) ───────────────────────────────────


def _fasta_contig_lengths(path: Path) -> list[tuple[str, int]]:
    """Stream a (maybe-gzipped) FASTA and return ``[(contig_id, length), ...]``.

    ``contig_id`` is the token immediately after ``>`` (whitespace-split — the
    same convention geNomad uses when it writes ``seq_name``).
    """
    opener = gzip.open if path.suffix == ".gz" else open
    rows: list[tuple[str, int]] = []
    current_id: str | None = None
    current_len = 0
    with opener(path, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                if current_id is not None:
                    rows.append((current_id, current_len))
                current_id = line[1:].split(None, 1)[0]
                current_len = 0
            else:
                current_len += len(line.strip())
    if current_id is not None:
        rows.append((current_id, current_len))
    return rows


def _build_contig_lengths(
    inputs: pd.DataFrame, paired_samples: set[str], out_path: Path, workers: int
) -> pd.DataFrame:
    """Read FASTAs for every paired Sample (LRA + ``__sr``) into a long TSV. Cached on disk."""
    if out_path.exists():
        print(f"loading cached {out_path}")
        return pd.read_csv(out_path, sep="\t", dtype={"Sample": str, "contig": str, "length": int})

    todo = inputs[inputs["Sample"].isin(paired_samples)][["Sample", "fasta_path"]].copy()
    todo["fasta_path"] = todo["fasta_path"].map(Path)
    missing = todo[~todo["fasta_path"].map(Path.is_file)]
    if not missing.empty:
        print(f"  WARNING: {len(missing)} FASTAs missing on disk (skipped):", file=sys.stderr)
        for _, r in missing.head(5).iterrows():
            print(f"    {r.Sample}\t{r.fasta_path}", file=sys.stderr)
        todo = todo[todo["fasta_path"].map(Path.is_file)]
    print(f"reading {len(todo):,} paired FASTAs with {workers} workers ...")

    def _one(item: tuple[str, Path]) -> list[tuple[str, str, int]]:
        sample, fp = item
        try:
            return [(sample, cid, ln) for cid, ln in _fasta_contig_lengths(fp)]
        except (OSError, EOFError) as exc:
            print(f"  {sample}: {fp.name} read failed ({exc})", file=sys.stderr)
            return []

    rows: list[tuple[str, str, int]] = []
    items = list(todo.itertuples(index=False, name=None))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for chunk in pool.map(_one, items):
            rows.extend(chunk)

    df = pd.DataFrame(rows, columns=["Sample", "contig", "length"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, sep="\t", index=False)
    print(
        f"wrote {out_path}  contig_rows={len(df):,}  samples={df['Sample'].nunique():,}"
    )
    return df


# ─── COMPARE ──────────────────────────────────────────────────────────────────


def _select_cohort(paired: pd.DataFrame, column: str | None) -> pd.DataFrame:
    """Return rows of ``paired`` selected by the cohort column (or all if None)."""
    if column is None:
        return paired
    if column not in paired.columns:
        sys.exit(f"paired_index missing cohort column: {column}")
    return paired[_truthy(paired[column])].copy()


def _full_prophage_counts(
    virus: pd.DataFrame, lengths: pd.DataFrame, cohort_samples: set[str]
) -> pd.Series:
    """Per-Sample count of proviruses bounded by host sequence on both sides.

    A "full prophage" here = ``topology == "Provirus"`` AND ``coord_start > 1``
    AND ``coord_end < host_contig_length``. The host contig id is parsed from
    ``seq_name`` (geNomad writes ``<host_contig>|provirus_<start>_<end>``);
    coordinates from the ``coordinates`` column (``"<start>-<end>"``).
    """
    sub = virus[
        (virus["Sample"].isin(cohort_samples)) & (virus["topology"].fillna("") == "Provirus")
    ].copy()
    if sub.empty:
        return pd.Series(dtype=int, name="n_full_prophage")

    sub["host_contig"] = sub["seq_name"].astype(str).str.rsplit("|provirus_", n=1).str[0]
    coords = sub["coordinates"].astype(str).str.split("-", n=1, expand=True)
    sub["coord_start"] = pd.to_numeric(coords[0], errors="coerce")
    sub["coord_end"] = pd.to_numeric(coords[1], errors="coerce")

    merged = sub.merge(
        lengths.rename(columns={"contig": "host_contig", "length": "host_contig_length"}),
        on=["Sample", "host_contig"],
        how="left",
    )
    missing = merged["host_contig_length"].isna().sum()
    if missing:
        print(
            f"  WARNING: {missing:,} provirus rows in cohort had no contig-length lookup"
            f" (likely host_contig parse mismatch); they are excluded.",
            file=sys.stderr,
        )

    full = (
        (merged["coord_start"] > 1)
        & (merged["coord_end"] < merged["host_contig_length"])
        & merged["host_contig_length"].notna()
    )
    return merged.loc[full].groupby("Sample").size().rename("n_full_prophage")


def _pair_metrics(
    counts: pd.DataFrame, full_proph: pd.Series, samples: pd.Series
) -> pd.DataFrame:
    """Look up the 5 per-Sample metrics for one arm of the pairing."""
    df = pd.DataFrame({"Sample": samples.values})
    df = df.merge(counts, on="Sample", how="left")
    df = df.merge(full_proph.rename("n_full_prophage").reset_index(), on="Sample", how="left")
    for col in (*METRIC_COLS, "n_full_prophage"):
        df[col] = df[col].fillna(0).astype(int)
    return df


PAIRED_COL_ORDER = [
    "lra_sample",
    "sr_biosample",
]
# Display order for paired metrics: plasmid → provirus → full prophage → whole
# contig → virus total. Full-prophage is sandwiched next to provirus so it
# reads as a refinement of the provirus count.
_METRIC_DISPLAY_ORDER = (
    "n_plasmid_contigs",
    "n_virus_provirus",
    "n_full_prophage",
    "n_virus_whole_contig",
    "n_virus_total",
)
for _m in _METRIC_DISPLAY_ORDER:
    PAIRED_COL_ORDER += [f"lra_{_m}", f"sr_{_m}", f"delta_{_m}"]


def _summary_row(paired_df: pd.DataFrame, cohort: str) -> dict:
    """Mean/median/q1/q3 per metric (×3 sides) + n_pairs."""
    out: dict = {"cohort": cohort, "n_pairs": len(paired_df)}
    for m in _METRIC_DISPLAY_ORDER:
        for side in ("lra", "sr", "delta"):
            col = f"{side}_{m}"
            s = paired_df[col]
            out[f"{col}__mean"] = float(s.mean()) if len(s) else float("nan")
            out[f"{col}__median"] = float(s.median()) if len(s) else float("nan")
            out[f"{col}__q1"] = float(s.quantile(0.25)) if len(s) else float("nan")
            out[f"{col}__q3"] = float(s.quantile(0.75)) if len(s) else float("nan")
    return out


def _print_cohort_summary(paired_df: pd.DataFrame, cohort: str) -> None:
    """Print headline LRA vs SR per-metric means + median delta for a cohort."""
    print(f"\n  cohort summary  ({cohort}, n_pairs={len(paired_df):,})")
    print(f"    {'metric':<24} {'lra_mean':>10} {'sr_mean':>10} {'delta_mean':>12} {'delta_median':>14}")
    for m in _METRIC_DISPLAY_ORDER:
        lra = paired_df[f"lra_{m}"].mean()
        sr = paired_df[f"sr_{m}"].mean()
        d_mean = paired_df[f"delta_{m}"].mean()
        d_med = paired_df[f"delta_{m}"].median()
        print(f"    {m:<24} {lra:>10.3f} {sr:>10.3f} {d_mean:>12.3f} {d_med:>14.3f}")


def cmd_compare(args: argparse.Namespace) -> int:
    """Build paired LRA-vs-SR tables + summaries for each cohort."""
    if not args.per_sample_counts.exists():
        sys.exit(
            f"missing {args.per_sample_counts} — run `aggregate` first."
        )

    counts = pd.read_csv(args.per_sample_counts, sep="\t", dtype={"Sample": str})
    print(f"per_sample_counts: {len(counts):,} rows  ({args.per_sample_counts})")

    paired = pd.read_csv(args.paired_index, sep="\t", dtype=str)
    print(f"paired_index:      {len(paired):,} rows  ({args.paired_index})")
    sample_col = "lra_sample" if "lra_sample" in paired.columns else "Sample"
    if sample_col not in paired.columns:
        sys.exit(f"{args.paired_index} missing 'lra_sample' / 'Sample' column")

    lra_samples = paired[sample_col].astype(str)
    sr_samples = lra_samples + SR_PAIRED_SUFFIX
    paired_universe = set(lra_samples) | set(sr_samples)

    inputs = _read_inputs_universe(args.inputs)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    lengths = _build_contig_lengths(
        inputs,
        paired_universe,
        args.out_dir / "contig_lengths_paired.tsv",
        workers=args.workers,
    )

    print(f"reading {args.virus_long} ...")
    virus = pd.read_csv(
        args.virus_long,
        sep="\t",
        usecols=["Sample", "seq_name", "coordinates", "topology"],
        dtype={"Sample": str, "seq_name": str, "coordinates": str, "topology": str},
    )

    summary_rows: list[dict] = []
    for cohort_name, cohort_col in COHORTS:
        print(f"\n=== cohort: {cohort_name} ===")
        cohort_paired = _select_cohort(paired, cohort_col)
        print(f"  {len(cohort_paired):,} pairs after filter ({cohort_col or 'all paired_index rows'})")
        if cohort_paired.empty:
            continue
        cohort_lra = cohort_paired[sample_col].astype(str)
        cohort_sr = cohort_lra + SR_PAIRED_SUFFIX
        cohort_universe = set(cohort_lra) | set(cohort_sr)

        full_proph = _full_prophage_counts(virus, lengths, cohort_universe)

        lra_df = _pair_metrics(counts, full_proph, cohort_lra)
        sr_df = _pair_metrics(counts, full_proph, cohort_sr)

        out = pd.DataFrame({"lra_sample": cohort_lra.values, "sr_biosample": cohort_sr.values})
        for m in _METRIC_DISPLAY_ORDER:
            out[f"lra_{m}"] = lra_df[m].values
            out[f"sr_{m}"] = sr_df[m].values
            out[f"delta_{m}"] = out[f"lra_{m}"] - out[f"sr_{m}"]
        out = out.reindex(columns=PAIRED_COL_ORDER)

        paired_path = args.out_dir / f"paired__{cohort_name}.tsv"
        out.to_csv(paired_path, sep="\t", index=False)
        print(f"  wrote {paired_path}  rows={len(out):,}")

        summary = _summary_row(out, cohort_name)
        summary_path = args.out_dir / f"summary__{cohort_name}.tsv"
        pd.DataFrame([summary]).to_csv(summary_path, sep="\t", index=False)
        print(f"  wrote {summary_path}")
        summary_rows.append(summary)

        _print_cohort_summary(out, cohort_name)

    if summary_rows:
        combined_path = args.out_dir / "summary__all_cohorts.tsv"
        pd.DataFrame(summary_rows).to_csv(combined_path, sep="\t", index=False)
        print(f"\nwrote {combined_path}")
    return 0


# ─── CLI ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    pagg = sub.add_parser("aggregate", help="build per_sample_counts.tsv")
    pagg.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS_TSV)
    pagg.add_argument("--plasmid-long", type=Path, default=DEFAULT_PLASMID_LONG_TSV)
    pagg.add_argument("--virus-long", type=Path, default=DEFAULT_VIRUS_LONG_TSV)
    pagg.add_argument("--out-dir", type=Path, default=DEFAULT_COMPARE_OUT_DIR)
    pagg.set_defaults(func=cmd_aggregate)

    pcmp = sub.add_parser("compare", help="paired LRA-vs-SR tables per cohort")
    pcmp.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS_TSV)
    pcmp.add_argument("--virus-long", type=Path, default=DEFAULT_VIRUS_LONG_TSV)
    pcmp.add_argument("--paired-index", type=Path, default=DEFAULT_PAIRED_INDEX)
    pcmp.add_argument("--out-dir", type=Path, default=DEFAULT_COMPARE_OUT_DIR)
    pcmp.add_argument(
        "--per-sample-counts",
        type=Path,
        default=DEFAULT_COMPARE_OUT_DIR / "per_sample_counts.tsv",
        help="output of `aggregate`; default sits beside the cohort TSVs.",
    )
    pcmp.add_argument("--workers", type=int, default=16, help="threads for FASTA scanning.")
    pcmp.set_defaults(func=cmd_compare)

    return parser


def main() -> int:
    """CLI entry — dispatch to aggregate or compare."""
    args = _build_parser().parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
