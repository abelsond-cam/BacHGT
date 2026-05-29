#!/usr/bin/env python3
"""LR-vs-SR feature comparison: one wide row per feature, both modes share a schema.

Two modes, one builder:

- **paired** — joins ``metadata_v2`` with ``sr_shadow_for_lra.tsv`` on
  ``sr_biosample``. LR reads bare columns; SR reads ``sr_``-prefixed columns
  from the shadow. Same biosamples in both arms, so ``n_lr == n_sr`` and the
  2×2 contingency (and ``penetrance_concordance``) is meaningful.
- **clonal_group** — metadata_v2 only. Within each clonal group, the LR arm is
  the rows in the chosen cohort (default ``lra_final_list == True``) and the
  SR arm is the rest. Both arms read the same feature columns; only the row
  subset differs. ``n_lr ≠ n_sr`` typically, so ``penetrance_concordance`` is
  left blank.

Wide schema (one row per feature, both modes), column order:

    feature
    lr_per_genome_sensitivity, sr_per_genome_sensitivity, lr_sr_sensitivity_ratio
    penetrance_concordance               (paired only; blank in clonal_group)
    lr_gene_count, sr_gene_count, lr_sr_gene_count_ratio
    lr_copies_per_carrier, sr_copies_per_carrier, lr_sr_copies_per_carrier_ratio
    n_lr, n_sr

Per-genome sensitivity = ``n_positive_in_arm / n_total_in_arm`` — the per-arm
detection rate, i.e. the fraction of genomes in which the feature was called.
Distinct from ``penetrance_concordance`` (pair-level 2×2 agreement) and from
``lr_gene_count`` (per-feature copy totals). Copy counts are summed
over the arm: ISEScan reads ``IS_<fam>`` directly; acquired-AMR uses
``count_acquired_tokens``; virulence BSCs use Σ allele presence over each
locus's allele set. MLST loci are single-copy → presence-only, so the six
count columns are blank.

Outputs:

- **paired**: two TSVs per cohort,
  ``lra_vs_sr_kleborate__<cohort>.tsv`` (virulence → MLST → AMR) and
  ``lra_vs_sr_isescan__<cohort>.tsv`` (alphabetical).
- **clonal_group**: one combined TSV per qualifying CG at
  ``<output_dir>/per_clonal_group/<CG>.tsv`` (virulence → MLST → AMR → ISEScan).
  Only CGs with ``≥ --min-per-arm`` rows in BOTH arms are written.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_METADATA = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_final_curated_all_samples_and_columns.tsv"
)
DEFAULT_METADATA_V2 = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv"
)
DEFAULT_SR_SHADOW = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/complete_vs_sr_genomes/sr_shadow_for_lra.tsv"
)
DEFAULT_OUTPUT_DIR = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/complete_vs_sr_genomes")

# ---------------------------------------------------------------------------
# Kleborate virulence module schema
# Read directly from each module's get_headers() in
# https://github.com/klebgenomics/Kleborate/tree/main/kleborate/modules
# ---------------------------------------------------------------------------
KLEBORATE_VIRULENCE_LOCI: dict[str, dict] = {
    "ybt": {
        "st": "YbST",
        "lineage": "Yersiniabactin",
        "alleles": ["ybtS", "ybtX", "ybtQ", "ybtP", "ybtA", "irp2", "irp1", "ybtU", "ybtT", "ybtE", "fyuA"],
        "spurious": "spurious_ybt_hits",
    },
    "clb": {
        "st": "CbST",
        "lineage": "Colibactin",
        "alleles": [
            "clbA",
            "clbB",
            "clbC",
            "clbD",
            "clbE",
            "clbF",
            "clbG",
            "clbH",
            "clbI",
            "clbL",
            "clbM",
            "clbN",
            "clbO",
            "clbP",
            "clbQ",
        ],
        "spurious": "spurious_clb_hits",
    },
    "iuc": {
        "st": "AbST",
        "lineage": "Aerobactin",
        "alleles": ["iucA", "iucB", "iucC", "iucD", "iutA"],
        "spurious": "spurious_abst_hits",
    },
    "iro": {
        "st": "SmST",
        "lineage": "Salmochelin",
        "alleles": ["iroB", "iroC", "iroD", "iroN"],
        "spurious": "spurious_smst_hits",
    },
    "rmp": {
        "st": "RmST",
        "lineage": "RmpADC",
        "alleles": ["rmpA", "rmpD", "rmpC"],
        "spurious": "spurious_rmst_hits",
    },
    "rmpA2": {
        "st": None,
        "lineage": None,
        "alleles": ["rmpA2"],
        "spurious": None,
    },
}

# Kleborate KpSC chromosomal 7-locus MLST scheme.
# Treated as presence/absence: allele IDs are arbitrary, but failure to detect
# a housekeeping gene is a meaningful assembly artefact.
KLEBORATE_CHROMOSOMAL_MLST_COLS: list[str] = [
    "gapA",
    "infB",
    "mdh",
    "pgi",
    "phoE",
    "rpoB",
    "tonB",
]

# Strings that Kleborate uses to indicate "no detection". The multi_mlst
# function converts NA -> 0 in ST columns so 0 is treated as absent.
KLEBORATE_ABSENT_TOKENS: frozenset[str] = frozenset(
    {
        "-",
        "0",
        "0.0",
        "",
        "NA",
        "na",
        "nan",
        "None",
        "none",
    }
)

WIDE_OUTPUT_COLUMN_ORDER: list[str] = [
    "feature",
    "lr_per_genome_sensitivity",
    "sr_per_genome_sensitivity",
    "lr_sr_sensitivity_ratio",
    "penetrance_concordance",
    "lr_gene_count",
    "sr_gene_count",
    "lr_sr_gene_count_ratio",
    "lr_copies_per_carrier",
    "sr_copies_per_carrier",
    "lr_sr_copies_per_carrier_ratio",
    "n_lr",
    "n_sr",
]

PAIRED_COHORTS = ("lra_final_list", "complete_genome", "reference_genome")


# ---------------------------------------------------------------------------
# Kleborate cell parsing helpers
# ---------------------------------------------------------------------------


def kleborate_cell_present(val) -> bool:
    """Return True if a Kleborate cell records a detection.

    Treats any string outside ``KLEBORATE_ABSENT_TOKENS`` as a positive call,
    including imperfect-match annotations (``15*``, ``15^``, ``15?``,
    ``15*-42%``) and multi-copy comma-separated lists. Mirrors Kleborate's own
    logic: it only writes a non-``-`` value when minimap2 finds a hit above the
    module's identity/coverage thresholds.
    """
    if pd.isna(val):
        return False
    return str(val).strip() not in KLEBORATE_ABSENT_TOKENS


def kleborate_column_to_presence(series: pd.Series) -> pd.Series:
    """Return a float Series of 0/1 indicating Kleborate detection per row."""
    return series.apply(kleborate_cell_present).astype(float)


# ---------------------------------------------------------------------------
# Acquired-AMR helpers
# ---------------------------------------------------------------------------


def acquired_column_names(columns: list[str]) -> list[str]:
    """Return column names ending in ``_acquired``."""
    return sorted(c for c in columns if str(c).endswith("_acquired"))


def count_acquired_tokens(series: pd.Series) -> pd.Series:
    """Split each cell by ``;`` and count non-empty tokens.

    Kleborate writes ``-`` for a class with no acquired gene; that is a
    no-hit marker, not a gene, so it must not be counted as one token.
    """

    def count_tokens(x):
        if pd.isna(x):
            return 0
        tokens = [t.strip() for t in str(x).split(";") if t.strip() and t.strip() != "-"]
        return len(tokens)

    return series.apply(count_tokens)


# ---------------------------------------------------------------------------
# Filename + cohort helpers
# ---------------------------------------------------------------------------


def sluggify(group_name) -> str:
    """Convert a group name to a safe filename component."""
    return str(group_name).replace(" ", "_").replace("/", "_")


def _select_paired_cohort(meta: pd.DataFrame, cohort: str) -> pd.DataFrame:
    """Return rows for a paired cohort: LRA-bearing with an ``sr_biosample`` partner.

    ``complete_genome`` further restricts to ``is_complete == True`` (assemblies
    deposited as 'complete' — single-chromosome, no gaps); ``reference_genome``
    further restricts to ``is_reference_genome == True`` (RefSeq references, a
    strict subset of ``complete_genome``).
    """
    lra = meta["lra_final_list"].astype(str).str.lower().isin({"true", "1", "yes"})
    sel = lra & meta["sr_biosample"].notna()
    if cohort == "complete_genome":
        comp = meta["is_complete"].astype(str).str.lower().isin({"true", "1", "yes"})
        sel = sel & comp
    elif cohort == "reference_genome":
        refg = meta["is_reference_genome"].astype(str).str.lower().isin({"true", "1", "yes"})
        sel = sel & refg
    out = meta[sel].copy()
    out["sr_biosample"] = out["sr_biosample"].astype(str)
    return out


# ---------------------------------------------------------------------------
# The single shared row builder
# ---------------------------------------------------------------------------


def _wide_feature_row(
    lr_present: pd.Series,
    sr_present: pd.Series,
    lr_copies: pd.Series | None,
    sr_copies: pd.Series | None,
    feature: str,
    *,
    paired: bool,
) -> dict:
    """Build one wide row from per-arm presence (and optional copy) Series.

    ``lr_present`` / ``sr_present`` are 0/1 Series over the LR and SR arms;
    they have the same length only in ``paired`` mode. ``lr_copies`` /
    ``sr_copies`` are optional; when given, the gene-count + copies-per-carrier
    block is populated (AMR / virulence / ISEScan). MLST passes them as
    ``None`` so those six columns stay blank.
    """
    lr_pres = lr_present.astype(int)
    sr_pres = sr_present.astype(int)
    n_lr = int(len(lr_pres))
    n_sr = int(len(sr_pres))
    n_lr_pos = int(lr_pres.sum())
    n_sr_pos = int(sr_pres.sum())

    lr_sens = n_lr_pos / n_lr if n_lr else float("nan")
    sr_sens = n_sr_pos / n_sr if n_sr else float("nan")
    sens_ratio = (lr_sens / sr_sens) if sr_sens else float("nan")

    if paired:
        a = int(((lr_pres == 1) & (sr_pres == 1)).sum())
        d = int(((lr_pres == 0) & (sr_pres == 0)).sum())
        pen_conc = (a + d) / n_lr if n_lr else float("nan")
    else:
        pen_conc = float("nan")

    row: dict = {
        "feature": feature,
        "lr_per_genome_sensitivity": lr_sens,
        "sr_per_genome_sensitivity": sr_sens,
        "lr_sr_sensitivity_ratio": sens_ratio,
        "penetrance_concordance": pen_conc,
        "lr_gene_count": pd.NA,
        "sr_gene_count": pd.NA,
        "lr_sr_gene_count_ratio": float("nan"),
        "lr_copies_per_carrier": float("nan"),
        "sr_copies_per_carrier": float("nan"),
        "lr_sr_copies_per_carrier_ratio": float("nan"),
        "n_lr": n_lr,
        "n_sr": n_sr,
    }

    if lr_copies is not None and sr_copies is not None:
        lr_total = int(round(float(pd.to_numeric(lr_copies, errors="coerce").fillna(0).sum())))
        sr_total = int(round(float(pd.to_numeric(sr_copies, errors="coerce").fillna(0).sum())))
        gc_ratio = (lr_total / sr_total) if sr_total else float("nan")
        lr_cpc = (lr_total / n_lr_pos) if n_lr_pos else float("nan")
        sr_cpc = (sr_total / n_sr_pos) if n_sr_pos else float("nan")
        cpc_ratio = (lr_cpc / sr_cpc) if sr_cpc else float("nan")
        row["lr_gene_count"] = lr_total
        row["sr_gene_count"] = sr_total
        row["lr_sr_gene_count_ratio"] = gc_ratio
        row["lr_copies_per_carrier"] = lr_cpc
        row["sr_copies_per_carrier"] = sr_cpc
        row["lr_sr_copies_per_carrier_ratio"] = cpc_ratio
    return row


# ---------------------------------------------------------------------------
# Feature-class names
# ---------------------------------------------------------------------------


def _virulence_bsc_name(code: str, info: dict) -> str:
    """Wide-schema feature name for a virulence BSC, e.g. ``Yersiniabactin (ybt) bsc``."""
    lineage = info.get("lineage")
    return f"{lineage} ({code}) bsc" if lineage else f"{code} bsc"


def _mlst_name(locus: str) -> str:
    """Wide-schema feature name for an MLST locus, e.g. ``gapA chromosomal``."""
    return f"{locus} chromosomal"


# ---------------------------------------------------------------------------
# Paired feature walkers (same biosamples in both arms)
# ---------------------------------------------------------------------------


def _paired_features(merged: pd.DataFrame) -> list[dict]:
    """Paired wide rows for virulence BSCs → MLST loci → acquired AMR."""
    rows: list[dict] = []

    # Virulence BSCs
    for code, info in KLEBORATE_VIRULENCE_LOCI.items():
        lr_alleles = [a for a in info["alleles"] if a in merged.columns]
        sr_alleles = [a for a in info["alleles"] if f"sr_{a}" in merged.columns]
        if not lr_alleles or not sr_alleles:
            continue
        lr_copies = sum(kleborate_column_to_presence(merged[a]) for a in lr_alleles)
        sr_copies = sum(kleborate_column_to_presence(merged[f"sr_{a}"]) for a in sr_alleles)
        lr_present = (lr_copies > 0).astype(int)
        sr_present = (sr_copies > 0).astype(int)
        rows.append(
            _wide_feature_row(
                lr_present,
                sr_present,
                lr_copies,
                sr_copies,
                _virulence_bsc_name(code, info),
                paired=True,
            )
        )

    # Chromosomal MLST (presence-only)
    for locus in KLEBORATE_CHROMOSOMAL_MLST_COLS:
        if locus not in merged.columns or f"sr_{locus}" not in merged.columns:
            continue
        lr_present = kleborate_column_to_presence(merged[locus])
        sr_present = kleborate_column_to_presence(merged[f"sr_{locus}"])
        rows.append(
            _wide_feature_row(lr_present, sr_present, None, None, _mlst_name(locus), paired=True)
        )

    # Acquired AMR
    for col in acquired_column_names(list(merged.columns)):
        if col.startswith("sr_"):
            continue
        sr_col = f"sr_{col}"
        if sr_col not in merged.columns:
            continue
        lr_copies = count_acquired_tokens(merged[col])
        sr_copies = count_acquired_tokens(merged[sr_col])
        lr_present = (lr_copies > 0).astype(int)
        sr_present = (sr_copies > 0).astype(int)
        rows.append(_wide_feature_row(lr_present, sr_present, lr_copies, sr_copies, col, paired=True))

    return rows


def _paired_isescan_features(merged: pd.DataFrame) -> list[dict]:
    """Paired wide rows for ISEScan IS families (alphabetical).

    LR copies are the ``IS_<family>`` columns on metadata_v2; SR copies are the
    matching ``sr_IS_<family>`` columns frozen in the SR shadow.
    ``startswith("IS_")`` selects family columns while excluding the lower-case
    ``is_*`` boolean flags and the ``sr_IS_*`` shadow columns.
    """
    rows: list[dict] = []
    for col in sorted(c for c in merged.columns if str(c).startswith("IS_")):
        sr_col = f"sr_{col}"
        if sr_col not in merged.columns:
            continue
        lr_copies = pd.to_numeric(merged[col], errors="coerce").fillna(0)
        sr_copies = pd.to_numeric(merged[sr_col], errors="coerce").fillna(0)
        lr_present = (lr_copies > 0).astype(int)
        sr_present = (sr_copies > 0).astype(int)
        rows.append(_wide_feature_row(lr_present, sr_present, lr_copies, sr_copies, col, paired=True))
    return rows


# ---------------------------------------------------------------------------
# Clonal-group feature walker (different samples in each arm; one CG)
# ---------------------------------------------------------------------------


def _clonal_group_features(rows: pd.DataFrame, is_lr_mask: pd.Series) -> list[dict]:
    """Wide rows for one CG: virulence → MLST → AMR → ISEScan, on LR/SR row subsets."""
    lr_df = rows[is_lr_mask]
    sr_df = rows[~is_lr_mask]
    cols = set(rows.columns)
    out: list[dict] = []

    # Virulence BSCs
    for code, info in KLEBORATE_VIRULENCE_LOCI.items():
        alleles = [a for a in info["alleles"] if a in cols]
        if not alleles:
            continue
        lr_copies = sum(kleborate_column_to_presence(lr_df[a]) for a in alleles)
        sr_copies = sum(kleborate_column_to_presence(sr_df[a]) for a in alleles)
        lr_present = (lr_copies > 0).astype(int)
        sr_present = (sr_copies > 0).astype(int)
        out.append(
            _wide_feature_row(
                lr_present,
                sr_present,
                lr_copies,
                sr_copies,
                _virulence_bsc_name(code, info),
                paired=False,
            )
        )

    # Chromosomal MLST (presence-only)
    for locus in KLEBORATE_CHROMOSOMAL_MLST_COLS:
        if locus not in cols:
            continue
        lr_present = kleborate_column_to_presence(lr_df[locus])
        sr_present = kleborate_column_to_presence(sr_df[locus])
        out.append(
            _wide_feature_row(lr_present, sr_present, None, None, _mlst_name(locus), paired=False)
        )

    # Acquired AMR
    for col in acquired_column_names(list(rows.columns)):
        if col.startswith("sr_"):
            continue
        lr_copies = count_acquired_tokens(lr_df[col])
        sr_copies = count_acquired_tokens(sr_df[col])
        lr_present = (lr_copies > 0).astype(int)
        sr_present = (sr_copies > 0).astype(int)
        out.append(_wide_feature_row(lr_present, sr_present, lr_copies, sr_copies, col, paired=False))

    # ISEScan (alphabetical)
    for col in sorted(c for c in rows.columns if str(c).startswith("IS_")):
        lr_copies = pd.to_numeric(lr_df[col], errors="coerce").fillna(0)
        sr_copies = pd.to_numeric(sr_df[col], errors="coerce").fillna(0)
        lr_present = (lr_copies > 0).astype(int)
        sr_present = (sr_copies > 0).astype(int)
        out.append(_wide_feature_row(lr_present, sr_present, lr_copies, sr_copies, col, paired=False))

    return out


# ---------------------------------------------------------------------------
# Output writer + summary
# ---------------------------------------------------------------------------


def _print_paired_summary(out: pd.DataFrame, label: str) -> None:
    """Print n features, count with ``lr_sr_sensitivity_ratio > 1``, top-10 by ratio."""
    n_features = len(out)
    if n_features == 0:
        print(f"  ({label}) no features")
        return
    ratio = out["lr_sr_sensitivity_ratio"]
    n_lr_higher = int((ratio > 1).sum())
    print(f"  ({label}) features={n_features}  lr_sr_sensitivity_ratio>1: {n_lr_higher}")
    top = out.sort_values("lr_sr_sensitivity_ratio", ascending=False, na_position="last").head(10)
    print(f"  Top 10 by lr_sr_sensitivity_ratio ({label}):")
    for _, r in top.iterrows():
        lr_p = "-" if pd.isna(r["lr_per_genome_sensitivity"]) else f"{r['lr_per_genome_sensitivity']:.3f}"
        sr_p = "-" if pd.isna(r["sr_per_genome_sensitivity"]) else f"{r['sr_per_genome_sensitivity']:.3f}"
        rat = "-" if pd.isna(r["lr_sr_sensitivity_ratio"]) else f"{r['lr_sr_sensitivity_ratio']:.3f}"
        print(f"    {str(r['feature']):40s}  lr={lr_p}  sr={sr_p}  ratio={rat}")


def _finalize_and_write(rows: list[dict], out_path: Path, label: str) -> None:
    """Build a wide DataFrame, cast gene-count cols to ``Int64``, write the TSV."""
    if not rows:
        print(f"\n  no features for {label}; skipping {out_path.name}")
        return
    out = pd.DataFrame(rows).reindex(columns=WIDE_OUTPUT_COLUMN_ORDER)
    for col in ("lr_gene_count", "sr_gene_count"):
        out[col] = out[col].astype("Int64")
    out.to_csv(out_path, sep="\t", index=False, na_rep="")
    print(f"\nwrote {out_path}  rows={len(out)}  ({label})")
    _print_paired_summary(out, label)


# ---------------------------------------------------------------------------
# Cohort drivers
# ---------------------------------------------------------------------------


def _run_paired_cohort(meta: pd.DataFrame, shadow: pd.DataFrame, cohort: str, output_dir: Path) -> None:
    """Run + write the paired comparison for a single cohort (two tables)."""
    print(f"\n{'=' * 66}\nPaired cohort: {cohort}\n{'=' * 66}")
    paired_meta = _select_paired_cohort(meta, cohort)
    merged = paired_meta.merge(shadow, on="sr_biosample", how="inner", suffixes=("", "_shadow"))
    print(f"Paired rows after merge: {len(merged):,}")
    print(f"  cohort-selected rows with sr_biosample : {len(paired_meta):,}")

    _finalize_and_write(
        _paired_features(merged),
        output_dir / f"lra_vs_sr_kleborate__{cohort}.tsv",
        f"kleborate / {cohort}",
    )
    _finalize_and_write(
        _paired_isescan_features(merged),
        output_dir / f"lra_vs_sr_isescan__{cohort}.tsv",
        f"isescan / {cohort}",
    )


def _run_clonal_group_cohort(
    meta: pd.DataFrame,
    cohort: str,
    output_dir: Path,
    min_per_arm: int,
) -> None:
    """One combined wide TSV per CG with ≥``min_per_arm`` rows in BOTH arms."""
    if "Clonal group" not in meta.columns:
        raise KeyError("metadata_v2 missing required 'Clonal group' column")

    per_cg_dir = output_dir / "per_clonal_group"
    per_cg_dir.mkdir(parents=True, exist_ok=True)

    lra = meta["lra_final_list"].astype(str).str.lower().isin({"true", "1", "yes"})
    if cohort == "complete_genome":
        comp = meta["is_complete"].astype(str).str.lower().isin({"true", "1", "yes"})
        is_lr = lra & comp
        lr_def = "lra_final_list & is_complete"
    elif cohort == "reference_genome":
        refg = meta["is_reference_genome"].astype(str).str.lower().isin({"true", "1", "yes"})
        is_lr = lra & refg
        lr_def = "lra_final_list & is_reference_genome"
    else:
        is_lr = lra
        lr_def = "lra_final_list"

    print(f"\n{'=' * 66}\nClonal-group cross-section: cohort={cohort}\n{'=' * 66}")
    print(f"LR-arm definition : {lr_def}")
    print(f"  total LR rows   : {int(is_lr.sum()):,}")
    print(f"  total SR rows   : {int((~is_lr).sum()):,}")
    print(f"  min_per_arm     : {min_per_arm}")

    n_written = n_skipped = 0
    for cg_name, gdf in meta.dropna(subset=["Clonal group"]).groupby("Clonal group", sort=False):
        cg_is_lr = is_lr.loc[gdf.index]
        n_lr_arm = int(cg_is_lr.sum())
        n_sr_arm = int((~cg_is_lr).sum())
        if n_lr_arm < min_per_arm or n_sr_arm < min_per_arm:
            n_skipped += 1
            continue
        rows = _clonal_group_features(gdf, cg_is_lr)
        out_path = per_cg_dir / f"{sluggify(cg_name)}.tsv"
        _finalize_and_write(rows, out_path, f"CG={cg_name}  n_lr={n_lr_arm}  n_sr={n_sr_arm}")
        n_written += 1
    print(f"\nWrote {n_written} per-CG tables under {per_cg_dir}")
    print(f"Skipped {n_skipped} CGs with < {min_per_arm} in either arm.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point — dispatch to paired or clonal_group mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["clonal_group", "paired"],
        default="clonal_group",
        help="paired: same-biosample SR-vs-LRA wide table from metadata_v2 + sr_shadow. "
        "clonal_group: per-CG cross-section (all LR assemblies vs all SR assemblies in each CG).",
    )
    parser.add_argument(
        "--metadata-v2",
        type=Path,
        default=DEFAULT_METADATA_V2,
        help="metadata_v2 TSV with LR-Kleborate + LR-ISEScan values.",
    )
    parser.add_argument(
        "--sr-shadow",
        type=Path,
        default=DEFAULT_SR_SHADOW,
        help="(paired mode) sr_shadow_for_lra.tsv with SR-Kleborate + sr_IS_* frozen at v1.",
    )
    parser.add_argument(
        "--cohort",
        choices=["lra_final_list", "complete_genome", "reference_genome", "all"],
        default="lra_final_list",
        help="Which LR cohort to use. Nested subsets: lra_final_list (default) ⊃ "
        "complete_genome (is_complete) ⊃ reference_genome (is_reference_genome). "
        "Use 'all' to emit one set of outputs per cohort.",
    )
    parser.add_argument(
        "--min-per-arm",
        type=int,
        default=10,
        help="(clonal_group mode) minimum rows in BOTH arms for a CG to be written. Default 10.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading metadata_v2: {args.metadata_v2}")
    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    print(f"  rows: {len(meta):,}")

    cohorts = list(PAIRED_COHORTS) if args.cohort == "all" else [args.cohort]

    if args.mode == "paired":
        print(f"Loading SR-shadow:   {args.sr_shadow}")
        shadow = pd.read_csv(args.sr_shadow, sep="\t", low_memory=False)
        print(f"  rows: {len(shadow):,}")
        shadow["sr_biosample"] = shadow["sr_biosample"].astype(str)
        for cohort in cohorts:
            _run_paired_cohort(meta, shadow, cohort, args.output_dir)
    else:
        for cohort in cohorts:
            _run_clonal_group_cohort(meta, cohort, args.output_dir, args.min_per_arm)

    print("\n=== Done ===")
    print(f"Output directory: {args.output_dir}")


if __name__ == "__main__":
    main()
