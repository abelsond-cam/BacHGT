#!/usr/bin/env python3
"""Read all KpSC ISEScan CSVs and write one wide table per sample (families + clusters)."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import pandas as pd
from tqdm import tqdm

from bac_panaroo.tl.isescan_analysis.isescan_constants import (
    CANONICAL_IS_FAMILY_COLUMNS,
    META_COLUMNS,
    cluster_csv_column,
)
from bac_panaroo.tl.isescan_analysis.isescan_utils import is_missing_value, parse_bool


def resolve_family_column(df: pd.DataFrame) -> str:
    lower = {c.lower(): c for c in df.columns}
    if "family" in lower:
        return lower["family"]
    raise ValueError(f"No 'family' column; columns: {list(df.columns)}")


def resolve_cluster_column(df: pd.DataFrame) -> str | None:
    """Prefer common ISEScan/aux column names; optional if absent."""
    lower = {c.lower(): c for c in df.columns}
    for key in ("cluster", "subtype", "oris", "cluster_id", "is_cluster"):
        if key in lower:
            return lower[key]
    for c in sorted(df.columns, key=str.lower):
        lc = c.lower()
        if "cluster" in lc and lc not in ("clustersize",):
            return c
    return None


def load_isescan_family_and_clusters(
    path: Path,
) -> tuple[dict[str, int], dict[str, int]]:
    df = pd.read_csv(path)
    fam_col = resolve_family_column(df)
    canon = set(CANONICAL_IS_FAMILY_COLUMNS)
    fam_s = df[fam_col].astype(str)
    fam_s = fam_s[fam_s.isin(canon)]
    fam_vc = fam_s.value_counts()

    families: dict[str, int] = {f: int(fam_vc.get(f, 0)) for f in CANONICAL_IS_FAMILY_COLUMNS}

    clus_col = resolve_cluster_column(df)
    clusters: dict[str, int] = {}
    if clus_col is not None:
        cl = df[clus_col].astype(str)
        cl = cl[cl.str.len() > 0]
        cl = cl[cl.ne("nan")]
        vc_c = cl.value_counts()
        for k, v in vc_c.items():
            clusters[str(k)] = int(v)

    return families, clusters


def _worker_task(task: tuple[str, object, bool, str, str]) -> tuple[dict[str, Any] | None, str]:
    sample, cg, is_refseq, rel_s, base_dir_str = task
    base_dir = Path(base_dir_str)

    rel: object = rel_s if rel_s else ""
    if is_missing_value(rel):
        return None, "missing"

    full = base_dir / str(rel).strip()
    if not full.is_file():
        return None, "notfound"

    try:
        fam_counts, cluster_counts = load_isescan_family_and_clusters(full)
    except (
        OSError,
        ValueError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        KeyError,
    ):
        return None, "read_error"

    row: dict[str, Any] = {
        "Sample": sample,
        "Clonal group": cg,
        "is_refseq": bool(is_refseq),
    }
    row.update(fam_counts)
    for ck, cv in cluster_counts.items():
        row[cluster_csv_column(ck)] = int(cv)

    return row, "ok"


def _tasks_from_meta(meta_rows: pd.DataFrame, base_dir: Path) -> list[tuple[str, object, bool, str, str]]:
    tasks: list[tuple[str, object, bool, str, str]] = []
    bds = str(base_dir)
    for sample, cg, iref, rel in zip(
        meta_rows["Sample"],
        meta_rows["Clonal group"],
        meta_rows["is_refseq"],
        meta_rows["isescan_file"],
        strict=True,
    ):
        rel_s = "" if is_missing_value(rel) else str(rel).strip()
        tasks.append((str(sample), cg, bool(iref), rel_s, bds))
    return tasks


def _finalize_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(META_COLUMNS) + list(CANONICAL_IS_FAMILY_COLUMNS))

    cluster_keys = sorted(
        {k for r in rows for k in r if k.startswith("cluster_")},
        key=str.lower,
    )

    cols = list(META_COLUMNS) + list(CANONICAL_IS_FAMILY_COLUMNS) + cluster_keys

    df = pd.DataFrame(rows)
    df = df.reindex(columns=cols)

    numeric = list(CANONICAL_IS_FAMILY_COLUMNS) + cluster_keys
    for c in numeric:
        if c in df.columns:
            df[c] = df[c].fillna(0).astype(int)

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path(
            "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_final_curated_slimmed.tsv",
        ),
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw"),
        help="Prefix for relative ``isescan_file`` paths",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/isescan_analysis/isescan_family_cluster_counts_per_sample.csv",
        ),
        help="Output CSV path (wide per-sample table)",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional JSON path for counts (ok / skip reasons)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(32, (os.cpu_count() or 4)),
    )
    parser.add_argument(
        "--imap-chunksize",
        type=int,
        default=10_000,
    )
    parser.add_argument("--threads", action="store_true", help="Use ThreadPoolExecutor instead of ProcessPoolExecutor")
    args = parser.parse_args()

    meta = pd.read_csv(args.metadata, sep="\t", low_memory=False)

    required = ("kpsc_final_list", "is_refseq", "isescan_file", "Clonal group", "Sample")
    for col in required:
        if col not in meta.columns:
            raise KeyError(f"metadata must contain column '{col}'")

    kpsc = meta.loc[parse_bool(cast(pd.Series, meta["kpsc_final_list"]))].copy()
    kpsc["is_refseq"] = parse_bool(cast(pd.Series, kpsc["is_refseq"]))

    tasks = _tasks_from_meta(kpsc, args.base_dir)
    skip_reasons: dict[str, int] = {}
    rows_ok: list[dict[str, Any]] = []

    def _acc(reason: str) -> None:
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    print(f"KpSC samples in metadata: {len(kpsc)} rows")
    print(f"ISEScan CSV tasks: {len(tasks)}")

    if args.workers <= 1:
        for t in tqdm(tasks, desc="ISEScan CSVs", unit="file"):
            row, reason = _worker_task(t)
            if row is not None:
                rows_ok.append(row)
            else:
                _acc(reason)
    else:
        Executor = ThreadPoolExecutor if args.threads else ProcessPoolExecutor
        with Executor(max_workers=args.workers) as ex:
            it = ex.map(
                _worker_task,
                tasks,
                chunksize=max(1, args.imap_chunksize),
            )
            for row, reason in tqdm(it, total=len(tasks), desc="ISEScan CSVs", unit="file"):
                if row is not None:
                    rows_ok.append(row)
                else:
                    _acc(reason)

    out_df = _finalize_table(rows_ok)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)
    summary = {
        "kpsc_metadata_rows": len(kpsc),
        "tasks": len(tasks),
        "rows_written": len(rows_ok),
        "skipped_total": sum(skip_reasons.values()),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "columns_n": len(out_df.columns),
    }
    print(json.dumps(summary, indent=2))

    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Wrote summary JSON: {args.summary_json}")

    print(f"Wrote per-sample table: {args.output}")


if __name__ == "__main__":
    main()