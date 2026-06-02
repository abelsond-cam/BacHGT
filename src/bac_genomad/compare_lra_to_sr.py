#!/usr/bin/env python3
"""Paired LRA-vs-SR comparison of geNomad plasmid + virus calls.

Two subcommands:

  aggregate — collapse the per-contig long TSVs into a per-Sample count table:
              ``Sample | source | n_plasmid_contigs | n_virus_total``. The
              universe is taken from ``genomad_inputs.tsv`` so the ~94 zero-call
              Samples in the 2026-06-02 run (sentinel present, header-only
              summary TSVs) appear as 0/0 rather than dropping out. Virus
              **sub-classification** is not done here — it depends on host
              contig lengths and so only happens in `compare`, where we
              already have lengths cached for the paired cohort.

  compare   — for each of four nested LRA cohorts (reference_genome ⊂ is_hybrid
              and is_complete ⊂ lra_final_list), join the per-Sample plasmid +
              virus totals against the paired SR partner (keyed
              ``<Sample>__sr`` in the geNomad outputs) and add
              **coordinate-based** virus sub-counts computed against host
              contig lengths:

                - ``n_full_prophage`` — provirus call bounded by host
                  sequence on BOTH sides: ``coord_start > 1 AND coord_end <
                  host_contig_length``. Headline metric: complete
                  integrations where both attachment sites are visible.
                - ``n_virus_spans_whole_contig`` — virus call reaches both
                  ends of its contig. Split into two sub-types:
                    * ``n_virus_standalone_contig`` — geNomad's whole-contig
                      topology rows (``topology != "Provirus"``). Real
                      extrachromosomal virus: lytic phage caught mid-
                      assembly, excised prophages, phage-plasmids, virion
                      DNA. Further binned by contig length into
                      ``standalone_small`` (<20 kb, likely SR fragmentation
                      noise), ``standalone_phage`` (20–80 kb, typical phage
                      genome — the real signal), ``standalone_large``
                      (≥80 kb, jumbo phages or multi-element contigs).
                    * ``n_virus_provirus_spans_all`` — provirus rows with
                      coords spanning the entire contig. Usually an SR
                      fragmentation artefact: the "host" contig is itself
                      entirely viral because the assembler broke at the
                      integration boundary.
                - ``n_virus_edge_truncated`` — provirus call that touches
                  exactly one end of the host contig (start == 1 XOR end ==
                  length). Likely a real prophage truncated by an assembly
                  contig break, not a complete excision.

              Identities: ``standalone = small + phage + large``;
              ``spans_whole = standalone + provirus_spans_all``;
              ``virus_total = spans_whole + full_prophage + edge_truncated``.

              Host-contig lengths are computed once from the paired FASTAs
              (~5.8 k files via threaded gunzip + ``>`` scan) and cached as
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

# Metrics carried in `per_sample_counts.tsv` (the aggregate output). Virus
# sub-classification (spans_whole / full_prophage / edge_truncated) lives in
# `compare` only — it needs contig lengths and only the paired cohort has them.
AGGREGATE_METRICS = ("n_plasmid_contigs", "n_virus_total")

# Coordinate-based virus sub-classes, computed in `compare`. Identities held by
# the classification:
#   n_virus_spans_whole_contig = n_virus_standalone_contig + n_virus_provirus_spans_all
#   n_virus_standalone_contig  = n_virus_standalone_small + ..._phage + ..._large
#   n_virus_total              = n_virus_spans_whole_contig + n_full_prophage + n_virus_edge_truncated
VIRUS_COORD_CLASSES = (
    "n_virus_spans_whole_contig",     # parent of the next 5
    "n_virus_standalone_contig",      # topology != Provirus (real extrachromosomal virus)
    "n_virus_standalone_small",       # standalone, contig < 20 kb (likely fragments / noise)
    "n_virus_standalone_phage",       # standalone, 20 kb ≤ contig < 80 kb (typical phage)
    "n_virus_standalone_large",       # standalone, contig ≥ 80 kb (jumbo / multi-element)
    "n_virus_provirus_spans_all",     # topology == Provirus but coords span the whole contig
    "n_full_prophage",
    "n_virus_edge_truncated",
)

STANDALONE_SMALL_MAX = 20_000   # < 20 kb: fragmentation / non-phage viral debris
STANDALONE_PHAGE_MAX = 80_000   # 20-80 kb: canonical phage-genome range

# Display order in the paired output.
PAIRED_METRIC_ORDER = (
    "n_plasmid_contigs",
    "n_virus_total",
    "n_full_prophage",
    "n_virus_spans_whole_contig",
    "n_virus_standalone_contig",
    "n_virus_standalone_small",
    "n_virus_standalone_phage",
    "n_virus_standalone_large",
    "n_virus_provirus_spans_all",
    "n_virus_edge_truncated",
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
    """Build the per-Sample plasmid + virus-total count table."""
    inputs = _read_inputs_universe(args.inputs)
    samples = inputs["Sample"].astype(str)
    print(f"universe: {len(samples):,} Samples from {args.inputs}")

    print(f"reading {args.plasmid_long} ...")
    plasmid = pd.read_csv(args.plasmid_long, sep="\t", usecols=["Sample"], dtype=str)
    n_plasmid = plasmid.groupby("Sample").size().rename("n_plasmid_contigs")
    print(f"  {len(plasmid):,} plasmid rows over {n_plasmid.size:,} Samples")

    print(f"reading {args.virus_long} ...")
    virus = pd.read_csv(args.virus_long, sep="\t", usecols=["Sample"], dtype=str)
    n_virus = virus.groupby("Sample").size().rename("n_virus_total")
    print(f"  {len(virus):,} virus rows over {n_virus.size:,} Samples")

    counts = pd.DataFrame(index=samples).join([n_plasmid, n_virus]).fillna(0).astype(int)
    out = (
        inputs[["Sample", "source"]]
        .merge(counts.reset_index(), on="Sample", how="left")
        .reindex(columns=["Sample", "source", *AGGREGATE_METRICS])
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "per_sample_counts.tsv"
    out.to_csv(out_path, sep="\t", index=False)
    print(f"\nwrote {out_path}  rows={len(out):,}")
    print(
        "  zero-call (both metrics == 0):",
        int((out[list(AGGREGATE_METRICS)].sum(axis=1) == 0).sum()),
    )
    for src, sub in out.groupby("source"):
        print(
            f"  source={src:<10} n={len(sub):>6,}"
            f"  mean_n_plasmid={sub['n_plasmid_contigs'].mean():.2f}"
            f"  mean_n_virus={sub['n_virus_total'].mean():.2f}"
        )
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


# ─── COORDINATE-BASED VIRUS CLASSIFICATION ────────────────────────────────────


def _classify_virus_coords(
    virus: pd.DataFrame, lengths: pd.DataFrame, paired_samples: set[str]
) -> pd.DataFrame:
    """Per-Sample coord-based virus sub-counts for the paired universe.

    Rules:

    - **Whole-contig topology rows** (``topology != "Provirus"``) — geNomad
      called the entire contig viral on its own terms. Count as
      ``n_virus_standalone_contig`` and further binned by host-contig length
      into ``small`` (<20 kb), ``phage`` (20-80 kb), ``large`` (≥80 kb).
      The standalone class is biologically the "real extrachromosomal virus"
      bucket: lytic phage caught in assembly, excised prophages,
      phage-plasmids, virion DNA.
    - **Provirus rows** (``topology == "Provirus"``) — parse ``coord_start``
      / ``coord_end`` from ``coordinates`` and ``host_contig`` from
      ``seq_name`` (``<host_contig>|provirus_<start>_<end>``); look up
      ``host_contig_length``. Then:
        * ``start <= 1 AND end >= length`` → ``n_virus_provirus_spans_all``
          (the "host" contig is itself entirely viral — usually a SR
          fragmentation artefact)
        * ``start > 1 AND end < length`` → ``n_full_prophage``
        * touches exactly one end → ``n_virus_edge_truncated``

    Rows where the contig-length lookup fails (parse mismatch / contig
    missing) are reported as warnings; they appear in ``n_virus_total`` but
    not in any of the sub-classes.
    """
    sub = virus[virus["Sample"].isin(paired_samples)].copy()
    if sub.empty:
        return pd.DataFrame(columns=["Sample", *VIRUS_COORD_CLASSES])

    is_provirus = sub["topology"].fillna("") == "Provirus"

    # ── whole-contig topology rows → standalone, binned by contig length ──
    wc = sub.loc[~is_provirus, ["Sample", "seq_name"]].copy()
    wc["contig"] = wc["seq_name"].astype(str)
    wc = wc.merge(lengths, on=["Sample", "contig"], how="left")
    wc_missing = int(wc["length"].isna().sum())
    if wc_missing:
        print(
            f"  WARNING: {wc_missing:,} whole-contig viral rows had no contig-length lookup;"
            " they appear in n_virus_total but not in the standalone size bins.",
            file=sys.stderr,
        )
    wc_len = pd.to_numeric(wc["length"], errors="coerce")
    has_wc_len = wc_len.notna()
    small_mask = has_wc_len & (wc_len < STANDALONE_SMALL_MAX)
    phage_mask = has_wc_len & (wc_len >= STANDALONE_SMALL_MAX) & (wc_len < STANDALONE_PHAGE_MAX)
    large_mask = has_wc_len & (wc_len >= STANDALONE_PHAGE_MAX)

    standalone_small = wc.loc[small_mask].groupby("Sample").size().rename("n_virus_standalone_small")
    standalone_phage = wc.loc[phage_mask].groupby("Sample").size().rename("n_virus_standalone_phage")
    standalone_large = wc.loc[large_mask].groupby("Sample").size().rename("n_virus_standalone_large")
    standalone_total = (
        wc.loc[has_wc_len].groupby("Sample").size().rename("n_virus_standalone_contig")
    )

    # ── provirus rows → coord-based sub-classes ──
    pv = sub.loc[is_provirus].copy()
    pv["host_contig"] = pv["seq_name"].astype(str).str.rsplit("|provirus_", n=1).str[0]
    coords = pv["coordinates"].astype(str).str.split("-", n=1, expand=True)
    pv["coord_start"] = pd.to_numeric(coords[0], errors="coerce")
    pv["coord_end"] = pd.to_numeric(coords[1], errors="coerce")
    pv = pv.merge(
        lengths.rename(columns={"contig": "host_contig", "length": "host_contig_length"}),
        on=["Sample", "host_contig"],
        how="left",
    )

    has_pv_len = pv["host_contig_length"].notna() & pv["coord_start"].notna() & pv["coord_end"].notna()
    pv_missing = int((~has_pv_len).sum())
    if pv_missing:
        print(
            f"  WARNING: {pv_missing:,} provirus rows had no contig-length lookup"
            " (host_contig parse mismatch); they appear in n_virus_total but not in"
            " the provirus sub-classes.",
            file=sys.stderr,
        )

    pv = pv[has_pv_len]
    pv_spans = (pv["coord_start"] <= 1) & (pv["coord_end"] >= pv["host_contig_length"])
    pv_full = (pv["coord_start"] > 1) & (pv["coord_end"] < pv["host_contig_length"])
    pv_edge = ~pv_spans & ~pv_full

    provirus_spans_all = pv.loc[pv_spans].groupby("Sample").size().rename("n_virus_provirus_spans_all")
    full = pv.loc[pv_full].groupby("Sample").size().rename("n_full_prophage")
    edge = pv.loc[pv_edge].groupby("Sample").size().rename("n_virus_edge_truncated")

    classified = pd.concat(
        [standalone_total, standalone_small, standalone_phage, standalone_large,
         provirus_spans_all, full, edge],
        axis=1,
    ).fillna(0).astype(int)
    classified["n_virus_spans_whole_contig"] = (
        classified["n_virus_standalone_contig"] + classified["n_virus_provirus_spans_all"]
    )
    return classified.reset_index().reindex(columns=["Sample", *VIRUS_COORD_CLASSES])


# ─── COMPARE ──────────────────────────────────────────────────────────────────


def _select_cohort(paired: pd.DataFrame, column: str | None) -> pd.DataFrame:
    """Return rows of ``paired`` selected by the cohort column (or all if None)."""
    if column is None:
        return paired
    if column not in paired.columns:
        sys.exit(f"paired_index missing cohort column: {column}")
    return paired[_truthy(paired[column])].copy()


def _arm_metrics(
    aggregate_counts: pd.DataFrame,
    coord_classes: pd.DataFrame,
    samples: pd.Series,
) -> pd.DataFrame:
    """Look up the 5 paired-metric columns for one arm (LRA or SR)."""
    df = pd.DataFrame({"Sample": samples.values})
    df = df.merge(aggregate_counts, on="Sample", how="left")
    df = df.merge(coord_classes, on="Sample", how="left")
    for col in (*AGGREGATE_METRICS, *VIRUS_COORD_CLASSES):
        df[col] = df[col].fillna(0).astype(int)
    return df


def _paired_columns() -> list[str]:
    """Build the final paired-output column order."""
    cols = ["lra_sample", "sr_biosample"]
    for m in PAIRED_METRIC_ORDER:
        cols += [f"lra_{m}", f"sr_{m}", f"delta_{m}"]
    return cols


def _summary_row(paired_df: pd.DataFrame, cohort: str) -> dict:
    """Mean/median/q1/q3 per metric (×3 sides) + n_pairs."""
    out: dict = {"cohort": cohort, "n_pairs": len(paired_df)}
    for m in PAIRED_METRIC_ORDER:
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
    print(
        f"    {'metric':<30} {'lra_mean':>10} {'sr_mean':>10}"
        f" {'delta_mean':>12} {'delta_median':>14}"
    )
    for m in PAIRED_METRIC_ORDER:
        lra = paired_df[f"lra_{m}"].mean()
        sr = paired_df[f"sr_{m}"].mean()
        d_mean = paired_df[f"delta_{m}"].mean()
        d_med = paired_df[f"delta_{m}"].median()
        print(f"    {m:<30} {lra:>10.3f} {sr:>10.3f} {d_mean:>12.3f} {d_med:>14.3f}")


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

    lra_samples_all = paired[sample_col].astype(str)
    sr_samples_all = lra_samples_all + SR_PAIRED_SUFFIX
    paired_universe = set(lra_samples_all) | set(sr_samples_all)

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

    print("classifying virus calls by coordinates ...")
    coord_classes = _classify_virus_coords(virus, lengths, paired_universe)
    print(
        f"  classified {len(coord_classes):,} Samples with at least one virus call"
        f" ({int(coord_classes['n_virus_spans_whole_contig'].sum()):,} spans-whole"
        f" [{int(coord_classes['n_virus_standalone_small'].sum()):,} standalone<20kb,"
        f" {int(coord_classes['n_virus_standalone_phage'].sum()):,} standalone-phage,"
        f" {int(coord_classes['n_virus_standalone_large'].sum()):,} standalone≥80kb,"
        f" {int(coord_classes['n_virus_provirus_spans_all'].sum()):,} provirus-spans-all],"
        f" {int(coord_classes['n_full_prophage'].sum()):,} full prophage,"
        f" {int(coord_classes['n_virus_edge_truncated'].sum()):,} edge-truncated)"
    )

    summary_rows: list[dict] = []
    for cohort_name, cohort_col in COHORTS:
        print(f"\n=== cohort: {cohort_name} ===")
        cohort_paired = _select_cohort(paired, cohort_col)
        print(
            f"  {len(cohort_paired):,} pairs after filter"
            f" ({cohort_col or 'all paired_index rows'})"
        )
        if cohort_paired.empty:
            continue
        cohort_lra = cohort_paired[sample_col].astype(str)
        cohort_sr = cohort_lra + SR_PAIRED_SUFFIX

        lra_arm = _arm_metrics(counts, coord_classes, cohort_lra)
        sr_arm = _arm_metrics(counts, coord_classes, cohort_sr)

        out = pd.DataFrame({"lra_sample": cohort_lra.values, "sr_biosample": cohort_sr.values})
        for m in PAIRED_METRIC_ORDER:
            out[f"lra_{m}"] = lra_arm[m].values
            out[f"sr_{m}"] = sr_arm[m].values
            out[f"delta_{m}"] = out[f"lra_{m}"] - out[f"sr_{m}"]
        out = out.reindex(columns=_paired_columns())

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
