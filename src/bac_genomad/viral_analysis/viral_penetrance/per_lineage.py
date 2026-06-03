#!/usr/bin/env python3
"""Per-Sublineage / per-Clonal-group viral-bracket penetrance across the KpSC universe.

For every standalone whole-contig viral call in
``genomad_virus_summary_long.tsv``, look up which of the five length brackets
(see :mod:`bac_genomad.viral_analysis.viral_brackets`) the contig falls into.
Roll up per Sample into binary carriage flags (``≥ 1`` contig in a bracket).
Then join with ``metadata_v2``, restrict to ``is_kpsc=True`` (the ~79 k sample
universe where Sublineage and Clonal group are biologically meaningful),
group by Sublineage and by Clonal group, and report % carriage of the two
named peaks (``Sgld_v`` and ``Wbr_v``) per group.

Epidemic-size threshold ``--min-samples`` (default 250) — every group at or
above the threshold gets its own bar; all sub-epidemic samples pool into a
single ``other`` bar (carriage rate computed over the pooled samples,
preserving sample weight rather than averaging per-group rates).

Outputs (under :data:`bac_genomad.genomad_constants.DEFAULT_VIRAL_PENETRANCE_DIR`):

- ``viral_bracket_carriage_per_sample.tsv`` — one row per Sample (full
  88 k universe), with bracket counts + binary carriage flags. Useful for
  sanity checks; the SL/CG-aggregated TSVs filter to is_kpsc=True.
- ``viral_penetrance_by_SL.tsv`` — one row per epidemic SL + ``other``.
- ``viral_penetrance_by_CG.tsv`` — one row per epidemic CG + ``other``.
- ``viral_penetrance_by_SL.png`` — 2-panel: top = Sgld_v penetrance,
  bottom = Wbr_v. Bar **height = n_samples**, bar **fill colour = % carriage**
  (viridis 0-100%). Annotated with carriage %.
- ``viral_penetrance_by_CG.png`` — same layout for Clonal group.

Length comes straight from geNomad's ``length`` column in the long TSV —
for whole-contig topology rows (``topology != "Provirus"``), that's the
contig length, so no FASTA scan is needed for the SR-only samples that
aren't in the existing length caches.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

from bac_genomad.genomad_constants import (
    DEFAULT_INPUTS_TSV,
    DEFAULT_METADATA_V2,
    DEFAULT_VIRAL_PENETRANCE_DIR,
    DEFAULT_VIRUS_LONG_TSV,
)
from bac_genomad.viral_analysis.viral_brackets import BRACKET_LABELS, assign_brackets

# Brackets we want carriage flags for — the two named peaks.
CARRIAGE_BRACKETS = ("Sgld_v", "Wbr_v")

# Cohort columns on metadata_v2.
META_USECOLS = ("Sample", "Sublineage", "Clonal group", "is_kpsc")

TRUE_TOKENS = frozenset({"true", "1", "yes"})


def _truthy(series: pd.Series) -> pd.Series:
    """Boolean mask from mixed-case True/False string columns."""
    return series.astype(str).str.lower().isin(TRUE_TOKENS)


# ─── per-Sample carriage table ────────────────────────────────────────────────


def _build_per_sample_carriage(
    inputs_tsv: Path, virus_long_tsv: Path
) -> pd.DataFrame:
    """Per-Sample bracket counts + carriage flags over the full 88 k universe.

    Returns a frame keyed on ``Sample`` with columns:
    ``source``, ``n_<bracket>`` for each of the five brackets, plus
    ``carries_<bracket>`` for the two named-peak carriage flags.
    """
    inputs = pd.read_csv(inputs_tsv, sep="\t", dtype=str, usecols=["Sample", "source"])
    print(f"universe: {len(inputs):,} Samples from {inputs_tsv}")

    print(f"reading {virus_long_tsv} ...")
    virus = pd.read_csv(
        virus_long_tsv, sep="\t",
        usecols=["Sample", "topology", "length"],
        dtype={"Sample": str, "topology": str},
    )
    standalone = virus[virus["topology"].fillna("") != "Provirus"].copy()
    standalone["bracket"] = assign_brackets(standalone["length"])
    standalone = standalone[standalone["bracket"].notna()]
    print(
        f"  {len(virus):,} virus rows → {len(standalone):,} standalone "
        f"(whole-contig) rows with a bracket label"
    )

    bracket_counts = (
        standalone.groupby(["Sample", "bracket"]).size()
        .unstack(fill_value=0)
        .reindex(columns=list(BRACKET_LABELS), fill_value=0)
        .rename(columns={b: f"n_{b}" for b in BRACKET_LABELS})
    )

    carriage = (
        inputs.merge(bracket_counts.reset_index(), on="Sample", how="left")
        .fillna({f"n_{b}": 0 for b in BRACKET_LABELS})
    )
    for b in BRACKET_LABELS:
        carriage[f"n_{b}"] = carriage[f"n_{b}"].astype(int)
    for b in CARRIAGE_BRACKETS:
        carriage[f"carries_{b}"] = carriage[f"n_{b}"] > 0
    return carriage


# ─── per-group penetrance aggregation ────────────────────────────────────────


def _group_penetrance(
    carriage: pd.DataFrame, meta: pd.DataFrame, group_col: str, min_samples: int
) -> pd.DataFrame:
    """% carriage of each named-peak bracket per group, with epidemic + ``other`` split.

    Joins ``carriage`` to ``meta`` on Sample, restricts to ``is_kpsc=True``,
    drops samples with a null group label, then:

    - Groups by ``group_col``; every group with ``n_samples >= min_samples``
      becomes its own row.
    - Pools every sub-epidemic group's samples into a single ``other`` row —
      carriage rate is recomputed over the pooled samples (preserves sample
      weight, does NOT average per-group rates).

    Output is sorted by ``n_samples`` desc with ``other`` pinned last.
    """
    kpsc_mask = _truthy(meta["is_kpsc"])
    kpsc = meta.loc[kpsc_mask, ["Sample", "Sublineage", "Clonal group"]].copy()
    print(f"  KpSC samples: {int(kpsc_mask.sum()):,} of {len(meta):,}")

    joined = carriage.merge(kpsc, on="Sample", how="inner")
    joined = joined.dropna(subset=[group_col])
    joined[group_col] = joined[group_col].astype(str)
    print(f"  joined+group-nonnull rows ({group_col}): {len(joined):,}")

    grouped = joined.groupby(group_col, sort=False)
    sizes = grouped.size().rename("n_samples")

    epidemic_groups = sizes[sizes >= min_samples].sort_values(ascending=False).index.tolist()
    other_mask = ~joined[group_col].isin(epidemic_groups)
    other_pool = joined[other_mask]

    rows: list[dict] = []
    for grp in epidemic_groups:
        sub = joined[joined[group_col] == grp]
        rows.append(_row_for(sub, label=str(grp), is_epidemic=True))
    if not other_pool.empty:
        rows.append(_row_for(other_pool, label="other", is_epidemic=False))

    out = pd.DataFrame(rows)
    return out


def _row_for(sub: pd.DataFrame, label: str, *, is_epidemic: bool) -> dict:
    """One penetrance row for a group (epidemic SL/CG or the pooled ``other``)."""
    n = len(sub)
    return {
        "label": label,
        "n_samples": int(n),
        "is_epidemic": is_epidemic,
        "n_Sgld_v_carriers": int(sub["carries_Sgld_v"].sum()),
        "pct_Sgld_v_carriers": 100.0 * sub["carries_Sgld_v"].mean() if n else float("nan"),
        "n_Wbr_v_carriers": int(sub["carries_Wbr_v"].sum()),
        "pct_Wbr_v_carriers": 100.0 * sub["carries_Wbr_v"].mean() if n else float("nan"),
    }


# ─── plotting ────────────────────────────────────────────────────────────────


def _plot_penetrance(
    df: pd.DataFrame, group_col_name: str, out_png: Path
) -> None:
    """2-panel bar chart: top Sgld_v, bottom Wbr_v.

    Bar height = ``n_samples``; bar fill colour = % carriage on a viridis 0-100
    colormap. ``other`` is drawn last with a distinct edge so it's visually
    separable from the epidemic bars even when small.
    """
    if df.empty:
        print(f"  (no rows for {group_col_name}; skipping {out_png.name})", file=sys.stderr)
        return

    labels = df["label"].tolist()
    heights = df["n_samples"].to_numpy()
    cmap = plt.get_cmap("viridis")
    norm = Normalize(vmin=0, vmax=100)

    fig, axes = plt.subplots(2, 1, figsize=(max(10, 0.5 * len(labels) + 4), 9), sharex=True)
    for ax, bracket in zip(axes, CARRIAGE_BRACKETS, strict=False):
        pct = df[f"pct_{bracket}_carriers"].to_numpy()
        colours = cmap(norm(pct))
        edge_colours = ["black" if lbl == "other" else "none" for lbl in labels]
        bars = ax.bar(
            np.arange(len(labels)), heights,
            color=colours, edgecolor=edge_colours, linewidth=1.0,
        )
        # carriage % annotations
        for bar, pc in zip(bars, pct, strict=False):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.01,
                f"{pc:.0f}%",
                ha="center", va="bottom", fontsize=8,
            )
        ax.set_ylabel("n samples")
        ax.set_title(f"{bracket} carriage by {group_col_name}")
        ax.grid(axis="y", alpha=0.2)

    axes[-1].set_xticks(np.arange(len(labels)))
    axes[-1].set_xticklabels(labels, rotation=45, ha="right", fontsize=9)

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=axes, fraction=0.03, pad=0.02, label="% carriage")
    fig.suptitle(
        f"Standalone-viral peak carriage by {group_col_name} (KpSC; epidemic ≥ "
        f"{int(df.loc[df['is_epidemic']].n_samples.min()) if df['is_epidemic'].any() else 0:,}"
        " samples + 'other' pool)",
        fontsize=11,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_png}")


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main() -> int:
    """CLI entry — build carriage TSV, per-SL/CG TSVs + plots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS_TSV)
    parser.add_argument("--virus-long", type=Path, default=DEFAULT_VIRUS_LONG_TSV)
    parser.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_VIRAL_PENETRANCE_DIR)
    parser.add_argument(
        "--min-samples",
        type=int,
        default=250,
        help="Epidemic threshold: groups with ≥ this many KpSC samples get a "
             "dedicated bar; rest pool into 'other'.",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # ── per-Sample carriage ──
    carriage = _build_per_sample_carriage(args.inputs, args.virus_long)
    carriage_path = args.out_dir / "viral_bracket_carriage_per_sample.tsv"
    carriage.to_csv(carriage_path, sep="\t", index=False)
    print(f"wrote {carriage_path}  rows={len(carriage):,}")
    for b in CARRIAGE_BRACKETS:
        print(
            f"  {b}: {int(carriage[f'carries_{b}'].sum()):,} carriers"
            f" ({100*carriage[f'carries_{b}'].mean():.2f}%)"
        )

    # ── metadata join + per-group aggregation ──
    print(f"\nreading metadata_v2: {args.metadata_v2}")
    meta = pd.read_csv(args.metadata_v2, sep="\t", dtype=str, usecols=list(META_USECOLS))
    print(f"  {len(meta):,} rows")

    # Sanity: non-KpSC carriage report (should be small).
    non_kpsc = meta.loc[~_truthy(meta["is_kpsc"]), ["Sample"]]
    if not non_kpsc.empty:
        non_kpsc_carr = carriage.merge(non_kpsc, on="Sample", how="inner")
        if len(non_kpsc_carr):
            for b in CARRIAGE_BRACKETS:
                n_carr = int(non_kpsc_carr[f"carries_{b}"].sum())
                print(
                    f"  (non-KpSC {b} carriers: {n_carr} of {len(non_kpsc_carr):,}"
                    f" — should be near zero; high count = off-target geNomad calls)"
                )

    for group_col, short, label_name in (
        ("Sublineage", "SL", "Sublineage"),
        ("Clonal group", "CG", "Clonal group"),
    ):
        print(f"\n=== per-{short} penetrance ({group_col}) ===")
        out = _group_penetrance(carriage, meta, group_col, args.min_samples)
        tsv_path = args.out_dir / f"viral_penetrance_by_{short}.tsv"
        out.to_csv(tsv_path, sep="\t", index=False)
        print(f"  wrote {tsv_path}  rows={len(out):,}")
        if not out.empty:
            print(f"  epidemic groups (n_samples ≥ {args.min_samples}): "
                  f"{int(out['is_epidemic'].sum())}")
            for _, r in out.iterrows():
                print(
                    f"    {r['label']:<20} n={int(r['n_samples']):>6,}"
                    f"  Sgld_v={r['pct_Sgld_v_carriers']:>5.1f}%"
                    f"  Wbr_v={r['pct_Wbr_v_carriers']:>5.1f}%"
                )
        png_path = args.out_dir / f"viral_penetrance_by_{short}.png"
        _plot_penetrance(out, label_name, png_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
