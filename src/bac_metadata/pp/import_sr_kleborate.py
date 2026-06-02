#!/usr/bin/env python3
"""Import SR-side Kleborate v3.2.4 results (the ``seb/`` tree) into a sidecar TSV.

Background
----------
SR Kleborate was run by Seb against the short-read assemblies and the
per-batch aggregate outputs live under
``<RDS>/seb/kleborate_v3.2.4/<batch>/``. They were never merged into
``metadata_final_curated_all_samples_and_columns.tsv`` for the priority-3
audit-matched cohort (~957 paired biosamples), which makes the paired
SR-vs-LRA comparison in G.4 spuriously claim every Kleborate call is a
long-read pickup. This module fixes that by emitting a single
BioSample-keyed sidecar that ``build_sr_shadow_for_lra.py`` can consume.

What it produces
----------------
``<RDS>/seb/sr_kleborate_v3.2.4.tsv`` — one row per BioSample, columns
match Kleborate's ``klebsiella_pneumo_complex_output.txt`` schema (KpSC
typing). Non-KpSC samples from ``klebsiella_oxytoca_complex_output.txt``
and ``escherichia_output.txt`` are merged on top of the KpSC table; the
escherichia / enterobacterales species output only carries a species call
(no MLST / virulence / capsule loci), so those rows have NaN typing.

Layout discovered (2026-05-27)
------------------------------
- 25 batch dirs carry ``klebsiella_pneumo_complex_output.txt`` (KpSC
  typing — 78,957 rows total).
- 3 batch dirs carry ``klebsiella_oxytoca_complex_output.txt`` (KoSC
  typing).
- 4 batch dirs carry ``escherichia_output.txt`` (E. coli — species
  match only).
- 4 batch dirs carry ``enterobacterales__species_output.txt`` (species
  match only, for the rare non-Kp/Ko Klebs).

The ``strain`` column = BioSample directly (SAMD/SAMN/SAME accession);
no upstream mapping required.

Usage
-----
::

    uv run python -m bac_metadata.pp.import_sr_kleborate --dry-run
    uv run python -m bac_metadata.pp.import_sr_kleborate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_SEB_ROOT = DATA_ROOT / "seb/kleborate_v3.2.4"
DEFAULT_OUT_PATH = DATA_ROOT / "seb/sr_kleborate_v3.2.4.tsv"

# ─── INPUTS ───────────────────────────────────────────────────────────────────

KPSC_TYPING_FN  = "klebsiella_pneumo_complex_output.txt"
KOSC_TYPING_FN  = "klebsiella_oxytoca_complex_output.txt"
ECOLI_FN        = "escherichia_output.txt"
SPECIES_FN      = "enterobacterales__species_output.txt"


def _flatten_namespaced(cols: list[str]) -> dict[str, str]:
    """Map Kleborate v3 namespaced columns to flat names.

    Kleborate v3 emits ``<scheme>__<module>__<field>`` (e.g.
    ``enterobacterales__species__species``, ``klebsiella__ybst__ybtS``).
    Seb's batches store the flat ``<field>`` form. Returns a rename dict
    that strips the namespace prefix; columns without ``__`` are left as-is.
    On collision (multiple namespaced cols collapse to the same flat name),
    the LAST occurrence wins — Kleborate's column ordering puts the
    canonical version last in practice.
    """
    rename: dict[str, str] = {}
    for c in cols:
        if "__" not in c:
            continue
        # Take the last segment (after the final '__').
        rename[c] = c.rsplit("__", 1)[-1]
    return rename


def _read_kleborate(path: Path, source_label: str) -> pd.DataFrame:
    """Read one Kleborate batch TSV; rename strain -> BioSample; tag source.

    Auto-detects Kleborate v3 namespaced columns
    (``enterobacterales__species__species`` etc.) and flattens them to the
    seb-batch convention (``species``).
    """
    df = pd.read_csv(path, sep="\t", low_memory=False)
    if "strain" not in df.columns:
        raise ValueError(f"{path}: expected 'strain' column, got {df.columns[:5].tolist()}")
    df = df.rename(columns={"strain": "BioSample"})
    # Flatten namespaced cols if present.
    rename = _flatten_namespaced(list(df.columns))
    if rename:
        df = df.rename(columns=rename)
    df["_seb_batch"] = source_label
    return df


def _concat_typing(seb_root: Path, fn: str) -> pd.DataFrame:
    """Concat all batch TSVs of a given filename into one BioSample-keyed frame."""
    paths = sorted(seb_root.glob(f"*/{fn}"))
    if not paths:
        return pd.DataFrame()
    frames = []
    for p in paths:
        try:
            df = _read_kleborate(p, source_label=p.parent.name)
        except Exception as exc:
            print(f"WARN: {p}: {exc}", file=sys.stderr)
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    return out


def build_sidecar(
    seb_root: Path,
    extra_kpsc_paths: list[Path] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Build the unioned SR-Kleborate sidecar.

    Returns ``(df, stats)``. ``df`` carries one row per BioSample with
    KpSC-typing columns where the SR assembly typed as KpSC, KoSC-typing
    columns where it typed as KoSC, or just a species-only row otherwise.
    Conflicts (same BioSample in multiple files) are resolved by keeping
    the most-informative typing TSV in order: KpSC > KoSC > E. coli >
    enterobacterales-species.

    ``extra_kpsc_paths`` — additional ``klebsiella_pneumo_complex_output.txt``-format
    TSVs (e.g. our own Kleborate runs on SR assemblies that Seb missed) to
    union into the KpSC layer with HIGHEST precedence within that layer.
    Namespaced Kleborate v3 column names are auto-flattened on read.
    """
    stats: dict = {}

    kpsc = _concat_typing(seb_root, KPSC_TYPING_FN)
    # Append extra KpSC sources (our own runs on Seb-missed assemblies).
    if extra_kpsc_paths:
        extras = []
        for p in extra_kpsc_paths:
            try:
                df = _read_kleborate(p, source_label=f"extra:{p.parent.name}")
            except Exception as exc:
                print(f"WARN: {p}: {exc}", file=sys.stderr)
                continue
            extras.append(df)
        if extras:
            extra_df = pd.concat(extras, ignore_index=True, sort=False)
            # Put extras FIRST so dedupe-keep-first prefers them over
            # Seb's seb-batch row for the same BioSample (in case of overlap).
            kpsc = pd.concat([extra_df, kpsc], ignore_index=True, sort=False)
            stats["extra_kpsc_rows"] = len(extra_df)

    kosc = _concat_typing(seb_root, KOSC_TYPING_FN)
    ecoli = _concat_typing(seb_root, ECOLI_FN)
    spec = _concat_typing(seb_root, SPECIES_FN)

    stats["kpsc_raw_rows"]    = len(kpsc)
    stats["kosc_raw_rows"]    = len(kosc)
    stats["ecoli_raw_rows"]   = len(ecoli)
    stats["species_raw_rows"] = len(spec)

    # Dedupe within each layer (keep first occurrence per BioSample).
    def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return df.drop_duplicates("BioSample", keep="first")

    kpsc  = _dedupe(kpsc)
    kosc  = _dedupe(kosc)
    ecoli = _dedupe(ecoli)
    spec  = _dedupe(spec)

    stats["kpsc_unique_biosamples"]    = len(kpsc)
    stats["kosc_unique_biosamples"]    = len(kosc)
    stats["ecoli_unique_biosamples"]   = len(ecoli)
    stats["species_unique_biosamples"] = len(spec)

    # Layer in precedence order. Lower-precedence rows only contribute
    # BioSamples not already present in a higher-precedence layer.
    pieces = []
    seen: set[str] = set()
    for df, label in [(kpsc, "kpsc"), (kosc, "kosc"), (ecoli, "ecoli"), (spec, "species")]:
        if df.empty:
            continue
        mask = ~df["BioSample"].isin(seen)
        added = df.loc[mask].copy()
        added["_typing_source"] = label
        pieces.append(added)
        seen.update(added["BioSample"].tolist())
        stats[f"{label}_after_dedup_against_higher_precedence"] = int(mask.sum())

    out = pd.concat(pieces, ignore_index=True, sort=False) if pieces else pd.DataFrame()
    stats["sidecar_rows"] = len(out)
    stats["sidecar_cols"] = len(out.columns)

    # Move BioSample to the front.
    cols = ["BioSample", "_typing_source", "_seb_batch"] + [
        c for c in out.columns if c not in {"BioSample", "_typing_source", "_seb_batch"}
    ]
    out = out[cols]
    return out, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry: build the SR-Kleborate sidecar TSV."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seb-root", type=Path, default=DEFAULT_SEB_ROOT)
    ap.add_argument("--extra-kpsc", type=Path, nargs="*", default=None,
                    help="Additional KpSC typing TSVs to union (e.g. our own "
                         "Kleborate runs on Seb-missed SR assemblies). "
                         "Namespaced Kleborate v3 columns are auto-flattened.")
    ap.add_argument("--out",      type=Path, default=DEFAULT_OUT_PATH)
    ap.add_argument("--dry-run",  action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    print(f"seb_root : {args.seb_root}")
    if args.extra_kpsc:
        for p in args.extra_kpsc:
            print(f"extra    : {p}")
    print(f"out      : {args.out}")

    sidecar, stats = build_sidecar(args.seb_root, extra_kpsc_paths=args.extra_kpsc)

    print("\n=== SR-Kleborate sidecar stats ===")
    for k, v in stats.items():
        print(f"  {k:48s}: {v}")
    if not sidecar.empty:
        print("\nfirst 5 column heads:", sidecar.columns.tolist()[:5])
        print("last  5 column heads:", sidecar.columns.tolist()[-5:])
        ts = sidecar["_typing_source"].value_counts().to_dict()
        print(f"\ntyping-source split: {ts}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sidecar.to_csv(args.out, sep="\t", index=False)
    print(f"\nwrote {args.out}  rows={len(sidecar):,}  cols={len(sidecar.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
