"""Derive the comparison groups (and their sample sets) from the existing SL-level GPA runs.

The variant-vs-GPA comparison is run **per existing Panaroo GPA run** — the unit is the run
directory, including the random part-splits (``SL147_part_0`` / ``SL147_part_1``). Each run's
``panaroo_genomes.tsv`` maps every Panaroo genome to its metadata ``Sample``; the variant
analysis then uses that **exact same sample set**, so the two embeddings are comparable.

The KP-sublineage runs are exactly the ``SL*`` dirs under the run root (the ``kp_rare_*``
pooled-rare batches and ``species_*`` / ``non_kpsc_species_*`` runs are not per-Sublineage and
are excluded by the default ``^SL`` name filter). See the data layout in
``src/bac_panaroo/docs/panaroo_run_inventory.md``.

Selection is deliberately **inclusive**: a run is kept if its samples *outside the single
largest Clonal Group* total ``>= --min-outside-largest-cg`` (default 50) — i.e. there is some
sub-SL CG heterogeneity to test. This keeps the natural-control runs (one dominant CG plus a
tail of rare CGs) where clean multi-CG clustering is *not* expected. The stricter "≥2 large
CGs" condition is recorded as ``group_type`` (``multi_cg`` vs ``control_single_cg``) so it can
be applied post-hoc at comparison time, not as a collection gate.

CLI: writes a ``groups`` TSV (one row per qualifying run, with CG-composition annotations),
a long-form ``group_samples`` TSV (group, Sample), and the deduped ``union`` sample-list CSV
(a ``Sample`` column) that feeds resolution + extraction.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

PANAROO_RUN_ROOT_DEFAULT = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome"
)
METADATA_V2_DEFAULT = Path(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv"
)
PANAROO_GENOMES_FILENAME = "panaroo_genomes.tsv"
CG_COL = "Clonal group"
SL_COL = "Sublineage"
LARGE_CG_MIN = 50


def _list_run_dirs(run_root: Path, name_regex: str) -> list[Path]:
    """Immediate child dirs of ``run_root`` whose name matches ``name_regex`` and hold a run.

    One ``scandir`` of the documented run root (not a recursive data-tree crawl): a dir is a
    run if it contains ``panaroo_genomes.tsv``.
    """
    pat = re.compile(name_regex)
    out: list[Path] = []
    with os.scandir(run_root) as it:
        for entry in it:
            if entry.is_dir() and pat.search(entry.name) and os.path.isfile(
                os.path.join(entry.path, PANAROO_GENOMES_FILENAME)
            ):
                out.append(Path(entry.path))
    return sorted(out)


def _group_samples(run_dir: Path) -> list[str]:
    """Unique metadata ``Sample`` set of a Panaroo run (from ``panaroo_genomes.tsv``).

    A dual SR+LRA isolate appears as two Panaroo genomes that share one ``Sample``; deduping
    on ``Sample`` collapses them, matching the single per-``Sample`` snippy variant profile.
    """
    g = pd.read_csv(run_dir / PANAROO_GENOMES_FILENAME, sep="\t")
    if "Sample" not in g.columns:
        return []
    return g["Sample"].astype(str).drop_duplicates().tolist()


def _annotate(samples: list[str], meta: pd.DataFrame, cg_col: str, sl_col: str) -> dict[str, object]:
    """CG/SL composition of a group's KPSC samples (samples without a CG are ignored for CG stats)."""
    sub = meta.reindex(pd.Index(samples, dtype=str))
    sub = sub[sub["_kpsc"]]
    cg = sub[cg_col].dropna().astype(str)
    cg = cg[(cg != "") & (cg.str.lower() != "nan")]
    counts = cg.value_counts()
    n_with_cg = int(counts.sum())
    largest_n = int(counts.iloc[0]) if len(counts) else 0
    largest_cg = str(counts.index[0]) if len(counts) else ""
    n_large = int((counts >= LARGE_CG_MIN).sum())
    n_outside_largest = n_with_cg - largest_n
    sl = sub[sl_col].dropna().astype(str)
    sl = sl[(sl != "") & (sl.str.lower() != "nan")]
    modal_sl = str(sl.value_counts().index[0]) if len(sl) else ""
    return {
        "sublineage": modal_sl,
        "n_samples": int(len(sub)),
        "n_with_cg": n_with_cg,
        "n_cg_total": int(len(counts)),
        "n_large_cgs": n_large,
        "largest_cg": largest_cg,
        "largest_cg_n": largest_n,
        "largest_cg_frac": round(largest_n / n_with_cg, 4) if n_with_cg else 0.0,
        "n_outside_largest_cg": int(n_outside_largest),
        "group_type": "multi_cg" if n_large >= 2 else "control_single_cg",
    }


def list_groups(
    run_root: Path,
    meta: pd.DataFrame,
    *,
    name_regex: str = r"^SL",
    min_outside_largest_cg: int = 50,
    cg_col: str = CG_COL,
    sl_col: str = SL_COL,
) -> dict[str, dict[str, object]]:
    """Return ``{group_name: {"samples": [...], "run_dir": ..., <annotations>}}`` for qualifying runs.

    ``meta`` must be indexed by ``Sample`` and carry a boolean ``_kpsc`` column plus ``cg_col``
    and ``sl_col`` (see :func:`load_metadata`). A run qualifies when its samples outside the
    largest Clonal Group total ``>= min_outside_largest_cg``.
    """
    groups: dict[str, dict[str, object]] = {}
    for run_dir in _list_run_dirs(run_root, name_regex):
        samples = _group_samples(run_dir)
        if not samples:
            continue
        ann = _annotate(samples, meta, cg_col, sl_col)
        if int(ann["n_outside_largest_cg"]) < min_outside_largest_cg:
            continue
        groups[run_dir.name] = {"samples": samples, "run_dir": str(run_dir), **ann}
    return groups


def load_metadata(metadata_path: Path, *, cg_col: str = CG_COL, sl_col: str = SL_COL) -> pd.DataFrame:
    """Load metadata_v2 indexed by ``Sample`` with a boolean ``_kpsc`` column + CG/SL columns."""
    cols = ["Sample", cg_col, sl_col, "kpsc_final_list"]
    meta = pd.read_csv(metadata_path, sep="\t", usecols=cols, low_memory=False)
    meta["Sample"] = meta["Sample"].astype(str)
    meta = meta.drop_duplicates(subset=["Sample"]).set_index("Sample")
    meta["_kpsc"] = meta["kpsc_final_list"].fillna(False).astype(bool)
    return meta


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-root", type=Path, default=PANAROO_RUN_ROOT_DEFAULT, help="Panaroo run root to scan.")
    p.add_argument("--metadata", type=Path, default=METADATA_V2_DEFAULT)
    p.add_argument("--name-regex", default=r"^SL", help="Keep run dirs whose name matches this (default: SL-prefixed).")
    p.add_argument("--min-outside-largest-cg", type=int, default=50, help="Min samples outside the largest CG to keep a run.")
    p.add_argument("--out-dir", type=Path, required=True, help="Output dir for the groups/union/group_samples tables.")
    args = p.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    meta = load_metadata(args.metadata)
    groups = list_groups(
        args.run_root, meta, name_regex=args.name_regex, min_outside_largest_cg=args.min_outside_largest_cg
    )
    if not groups:
        raise SystemExit(f"No qualifying runs under {args.run_root} (regex {args.name_regex!r}).")

    rows = [{"group": g, **{k: v for k, v in d.items() if k != "samples"}} for g, d in groups.items()]
    groups_df = pd.DataFrame(rows).sort_values(["group_type", "n_outside_largest_cg"], ascending=[True, False])
    groups_df.to_csv(args.out_dir / "groups.tsv", sep="\t", index=False)

    long = pd.DataFrame(
        [(g, s) for g, d in groups.items() for s in d["samples"]], columns=["group", "Sample"]
    )
    long.to_csv(args.out_dir / "group_samples.tsv", sep="\t", index=False)
    union = long["Sample"].drop_duplicates().sort_values()
    union.to_frame("Sample").to_csv(args.out_dir / "union_samples.csv", index=False)

    print(f"qualifying runs: {len(groups)}  ({(groups_df['group_type'] == 'multi_cg').sum()} multi_cg, "
          f"{(groups_df['group_type'] == 'control_single_cg').sum()} control_single_cg)")
    print(f"union samples  : {len(union)}")
    print(f"wrote          : {args.out_dir/'groups.tsv'}, group_samples.tsv, union_samples.csv")


if __name__ == "__main__":
    main()
