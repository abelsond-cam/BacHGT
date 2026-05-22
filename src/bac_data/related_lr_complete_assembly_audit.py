#!/usr/bin/env python3
"""Audit remaining related-long-read samples for Complete-Genome GCAs.

related_lr_complete_assembly_audit.py
-----------------------------------------
Audit which of the *remaining* related-long-read samples already have a
**Complete Genome** assembly deposited in GenBank (a GCA), so we can
download those instead of re-assembling them from raw long reads.

Background
──────────
The curated metadata links many short-read samples to an associated
long-read run via ``related_lr_run_accession`` (older snapshots name the
column ``related_lr_accession`` — this script accepts either). The Norway
"complete genomes" cohort has already been resolved and integrated
(``norway_tables1_integrate``). That still leaves ~3,000 non-Norway,
non-RefSeq samples carrying a long-read run accession. Some of those
long-read isolates have a closed assembly in GenBank already — often
deposited under a *different* BioProject than the read submission, which
is exactly the case ENA's ``result=assembly`` query misses (see
``norway_cohort_audit.py``). So this audit goes the robust route: probe
**NCBI Datasets v2 per BioSample** and report the best assembly level.

Discovery method
────────────────
For non-RefSeq samples the ``Sample`` column *is* the BioSample SAMEA
(``find_sample_assemblies.py`` queries ``sample_accession="<Sample>"``;
``norway_cohort_audit.audit_norkab`` passes ``Sample`` straight to the
NCBI biosample endpoint). We reuse, rather than reimplement, the proven
helpers from ``norway_cohort_audit``:

  * ``ncbi_headers``           — API-key / rate-limit handling
  * ``ncbi_biosample_records`` — NCBI Datasets v2 per-BioSample probe
  * ``_gca_primaries``         — collapse reports to one row per GCA

Set ``NCBI_API_KEY`` to raise the NCBI rate limit from 3 to 10 req/s.

Modes / usage
─────────────
    uv run python src/bac_data/related_lr_complete_assembly_audit.py
        [--metadata PATH]      # default: project_k/david/final full TSV
        [--out-dir PATH]       # default: <DATA_ROOT>/processed
        [--limit N]            # cap BioSample probes (smoke-test)
        [--include-side-csv]   # also probe related_lr_run_accessions.csv

Outputs (written to ``--out-dir``)
  related_lr_complete_assembly_audit.tsv   every probed sample + best GCA
  related_lr_complete_genomes.tsv          Complete-Genome rows only
                                           (the actionable download list)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from bac_data.norway_cohort_audit import (
    _gca_primaries,
    ncbi_biosample_records,
    ncbi_headers,
)

# ─── PATHS ────────────────────────────────────────────────────────────────────

# Same project_k layout the rest of download_data/ uses. On HPC this is
# the real path; locally point --metadata at the Weimann mirror.
DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david")
DEFAULT_METADATA = DATA_ROOT / "final" / "metadata_final_curated_all_samples_and_columns.tsv"
DEFAULT_OUT_DIR = DATA_ROOT / "processed"
SIDE_CSV_NAME = "related_lr_run_accessions.csv"

# ─── COLUMNS ──────────────────────────────────────────────────────────────────

SAMPLE_COL = "Sample"
NORWAY_FLAG_COL = "is_complete_norway_genome"
REFSEQ_FLAG_COL = "is_refseq"
# The column was renamed related_lr_accession → related_lr_run_accession;
# live metadata may carry either. Prefer the newer name when both exist.
LR_COL_CANDIDATES = ("related_lr_run_accession", "related_lr_accession")

# NCBI Datasets assembly_level vocabulary, worst → best.
LEVEL_RANK = {
    "Contig": 0,
    "Scaffold": 1,
    "Chromosome": 2,
    "Complete Genome": 3,
}
COMPLETE = "Complete Genome"


def _truthy(s: pd.Series) -> pd.Series:
    """Coerce a metadata flag column (True/"True"/1/NaN) to clean bool."""
    return s.astype(str).str.strip().str.lower().isin({"true", "1", "1.0"})


def resolve_lr_column(meta: pd.DataFrame) -> str:
    """Return whichever long-read-accession column this snapshot carries."""
    for col in LR_COL_CANDIDATES:
        if col in meta.columns:
            return col
    raise SystemExit(f"metadata has none of {LR_COL_CANDIDATES} — cannot define the LR subset")


def load_subset(metadata_path: Path) -> tuple[pd.DataFrame, str]:
    """Return the audit subset, one row per ``Sample``.

    Keeps rows with a long-read accession populated that are *not* a
    Norway-complete (already integrated) and *not* RefSeq (those already
    have a complete genome).
    """
    print(f"Loading metadata: {metadata_path}", flush=True)
    meta = pd.read_csv(metadata_path, sep="\t", low_memory=False)
    lr_col = resolve_lr_column(meta)
    md = meta.drop_duplicates(subset=[SAMPLE_COL], keep="first").reset_index(drop=True)

    has_lr = md[lr_col].notna() & (md[lr_col].astype(str).str.strip() != "")
    is_norway = _truthy(md[NORWAY_FLAG_COL]) if NORWAY_FLAG_COL in md.columns else pd.Series(False, index=md.index)
    is_refseq = _truthy(md[REFSEQ_FLAG_COL]) if REFSEQ_FLAG_COL in md.columns else pd.Series(False, index=md.index)
    keep = md[has_lr & ~is_norway & ~is_refseq].copy()
    print(
        f"LR column: '{lr_col}'  |  has_lr={int(has_lr.sum())}  "
        f"norway_complete excluded={int(is_norway.sum())}  "
        f"refseq excluded={int(is_refseq.sum())}  →  audit subset={len(keep)}",
        flush=True,
    )
    return keep[[SAMPLE_COL, lr_col]].rename(columns={lr_col: "related_lr_accession"}), lr_col


def load_side_csv_samples(out_dir_metadata_dir: Path) -> pd.DataFrame:
    """Fold in side-CSV ATB BioSamples (written next to the metadata)."""
    path = out_dir_metadata_dir / SIDE_CSV_NAME
    if not path.exists():
        print(f"  --include-side-csv set but {path} not found — skipping", flush=True)
        return pd.DataFrame(columns=[SAMPLE_COL, "related_lr_accession"])
    side = pd.read_csv(path)
    out = side.rename(columns={"sample_accession": SAMPLE_COL, "run_accession": "related_lr_accession"})[
        [SAMPLE_COL, "related_lr_accession"]
    ]
    out = out.dropna(subset=[SAMPLE_COL]).drop_duplicates(subset=[SAMPLE_COL])
    print(f"  side CSV BioSamples added: {len(out)} (from {path})", flush=True)
    return out


def _best_gca(records: list[dict]) -> dict | None:
    """Pick the highest-assembly-level GCA for one BioSample.

    Reuses ``_gca_primaries`` for the GCA/GCF/level/method/submitter
    collapse, then re-attaches contig stats from the raw report whose
    accession matches the chosen GCA.
    """
    gca = _gca_primaries(records)
    if not len(gca):
        return None
    gca = gca.copy()
    gca["rank"] = gca["level"].map(lambda v: LEVEL_RANK.get(str(v), -1))
    best = gca.sort_values("rank", ascending=False).iloc[0].to_dict()

    stats: dict = {}
    for rec in records:
        if rec.get("accession", "") == best["gca"]:
            stats = rec.get("assembly_stats", {}) or {}
            break
    best["n_contigs"] = stats.get("number_of_contigs", "")
    best["contig_n50"] = stats.get("contig_n50", "")
    best["n_gca_for_biosample"] = int(len(gca))
    return best


def probe(
    subset: pd.DataFrame,
    headers: dict[str, str],
    sleep_s: float,
    limit: int | None,
    shuffle: bool = False,
) -> pd.DataFrame:
    """Probe NCBI Datasets for every BioSample in ``subset``.

    Returns one row per sample with its best GCA (blank where none). With
    ``shuffle`` the subset is permuted (fixed seed) before ``limit`` is
    applied, so a capped smoke-test samples across the metadata rather
    than just its DDBJ-heavy head.
    """
    if shuffle:
        subset = subset.sample(frac=1.0, random_state=0).reset_index(drop=True)
    samples = subset[SAMPLE_COL].astype(str).tolist()
    lr_by_sample = dict(
        zip(
            subset[SAMPLE_COL].astype(str),
            subset["related_lr_accession"].astype(str),
            strict=False,
        )
    )
    if limit:
        samples = samples[:limit]
        print(
            f"Limiting to {limit} BioSamples ({'shuffled' if shuffle else 'head'}; smoke-test).",
            flush=True,
        )
    print(f"\nProbing NCBI Datasets for {len(samples)} BioSamples ...", flush=True)

    rows = []
    n_with_gca = 0
    for i, samea in enumerate(samples, start=1):
        best = _best_gca(ncbi_biosample_records(samea, headers))
        row = {
            "Sample": samea,
            "related_lr_accession": lr_by_sample.get(samea, ""),
            "gca": "",
            "gcf": "",
            "level": "",
            "method": "",
            "submitter": "",
            "n_contigs": "",
            "contig_n50": "",
            "n_gca_for_biosample": 0,
        }
        if best is not None:
            n_with_gca += 1
            row.update(
                {
                    "gca": best["gca"],
                    "gcf": best["gcf"],
                    "level": best["level"],
                    "method": best["method"],
                    "submitter": best["submitter"],
                    "n_contigs": best["n_contigs"],
                    "contig_n50": best["contig_n50"],
                    "n_gca_for_biosample": best["n_gca_for_biosample"],
                }
            )
        rows.append(row)
        if i % 100 == 0:
            print(f"  ... {i}/{len(samples)} probed; with GCA so far: {n_with_gca}", flush=True)
        time.sleep(sleep_s)

    df = pd.DataFrame(rows)
    print(f"\nBioSamples with ≥1 GCA: {n_with_gca}/{len(samples)}", flush=True)
    return df


def print_summary(df: pd.DataFrame) -> None:
    """Print the headline table (same style as ``audit_norkab``)."""
    has_gca = df["gca"].astype(str).str.startswith("GCA_")
    has_gcf = df["gcf"].astype(str).str.startswith("GCF_")
    is_complete = df["level"] == COMPLETE

    print("\n=== related-LR complete-assembly audit ===", flush=True)
    print(f"Samples probed:               {len(df)}", flush=True)
    print(f"  with a GCA assembly:        {int(has_gca.sum())}", flush=True)
    print(f"  with a paired RefSeq GCF:   {int(has_gcf.sum())}", flush=True)
    print(f"** Complete-Genome assemblies: {int(is_complete.sum())} **", flush=True)
    if has_gca.any():
        print(
            f"  assembly-level breakdown: {df.loc[has_gca, 'level'].value_counts().to_dict()}",
            flush=True,
        )
    if is_complete.any():
        cg = df[is_complete]
        print(
            f"  Complete-Genome with paired GCF: {int(cg['gcf'].astype(str).str.startswith('GCF_').sum())}/{len(cg)}",
            flush=True,
        )
        print(
            f"  top Complete-Genome submitters: {cg['submitter'].astype(str).value_counts().head(5).to_dict()}",
            flush=True,
        )
        print(
            f"  top Complete-Genome methods:    {cg['method'].astype(str).value_counts().head(5).to_dict()}",
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    """Parse args, probe NCBI per BioSample, write TSVs, print summary.

    Writes the full audit TSV plus the Complete-Genome download list.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="cap BioSample probes (smoke-test)")
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="permute the subset (fixed seed) before --limit so a smoke-test "
        "samples across the metadata, not just its DDBJ-heavy head",
    )
    parser.add_argument(
        "--include-side-csv",
        action="store_true",
        help=f"also probe BioSamples in <metadata dir>/{SIDE_CSV_NAME}",
    )
    args = parser.parse_args(argv)

    out_dir = args.out_dir or DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    headers, sleep_s = ncbi_headers()
    print(
        f"NCBI auth: {'NCBI_API_KEY set (10 req/s)' if headers else 'anon (3 req/s)'}",
        flush=True,
    )

    subset, _ = load_subset(args.metadata)
    if args.include_side_csv:
        side = load_side_csv_samples(args.metadata.parent)
        subset = (
            pd.concat([subset, side], ignore_index=True)
            .drop_duplicates(subset=[SAMPLE_COL], keep="first")
            .reset_index(drop=True)
        )
        print(f"Combined audit subset (metadata + side CSV): {len(subset)}", flush=True)

    df = probe(subset, headers, sleep_s, args.limit, shuffle=args.shuffle)

    audit_path = out_dir / "related_lr_complete_assembly_audit.tsv"
    df.to_csv(audit_path, sep="\t", index=False)
    print(f"\nWrote {audit_path}  rows={len(df)}", flush=True)

    cg = df[df["level"] == COMPLETE].copy()
    cg_cols = [
        "gca",
        "Sample",
        "related_lr_accession",
        "gcf",
        "level",
        "method",
        "submitter",
        "n_contigs",
        "contig_n50",
    ]
    cg_path = out_dir / "related_lr_complete_genomes.tsv"
    cg[cg_cols].to_csv(cg_path, sep="\t", index=False)
    print(f"Wrote {cg_path}  rows={len(cg)}  (Complete-Genome download list)", flush=True)

    print_summary(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
