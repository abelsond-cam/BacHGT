#!/usr/bin/env python3
"""Build the CheckM2 input manifest for the LRA cohort.

Collects every assembly we want CheckM2 to score — LR-GCAs from
``related_lr_all_gca.tsv`` plus is_refseq assemblies from the curated metadata
``assembly_file`` column — and symlinks them into a single working directory
so we can call ``checkm2 predict --input <dir>`` once.

Inputs (HPC paths; flags override for local dev):
  --metadata   curated metadata TSV       <RDS>/david/final/metadata_final_curated_all_samples_and_columns.tsv
  --lr-tsv     related_lr_all_gca.tsv     <RDS>/david/raw/related_lr/related_lr_all_gca.tsv
  --lr-dir     LR-GCA assembly dir        <RDS>/david/raw/related_lr/assemblies
  --refseq-roots two seb assembly dirs    <RDS>/seb/assemblies_2/{ncbi_03122025,ncbi_other_15122025}

Outputs (default: <RDS>/david/processed/checkm2_lra/):
  inputs.tsv        sample_id, tier, source_path, link_path, exists
  links/            symlinks named <sample_id>.fna.gz pointing at source_path

Idempotent: re-run to refresh symlinks after new genomes appear on disk.
Missing source files are reported, not skipped silently — fix and rerun.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# Defaults match the HPC layout. --override flags handle local dev.
DEFAULT_DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA  = DEFAULT_DATA_ROOT / "david/final/metadata_final_curated_all_samples_and_columns.tsv"
DEFAULT_LR_TSV    = DEFAULT_DATA_ROOT / "david/raw/related_lr/related_lr_all_gca.tsv"
DEFAULT_LR_DIR    = DEFAULT_DATA_ROOT / "david/raw/related_lr/assemblies"
DEFAULT_SEB_ROOT  = DEFAULT_DATA_ROOT / "seb"
DEFAULT_OUT_DIR   = DEFAULT_DATA_ROOT / "david/processed/checkm2_lra"

# Sample column → bare GCA/GCF accession (for is_refseq rows).
_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")


def collect_lr_inputs(lr_tsv: Path, lr_dir: Path) -> pd.DataFrame:
    """One row per LR-GCA in related_lr_all_gca.tsv → expected on-disk path."""
    df = pd.read_csv(lr_tsv, sep="\t", low_memory=False, usecols=["gca"])
    df = df.drop_duplicates("gca")
    df["sample_id"]   = df["gca"]
    df["tier"]        = "lr_gca"
    df["source_path"] = df["gca"].map(lambda g: str(lr_dir / f"{g}.fna.gz"))
    return df[["sample_id", "tier", "source_path"]]


def collect_refseq_inputs(metadata_tsv: Path, seb_root: Path) -> pd.DataFrame:
    """One row per is_refseq sample → assembly_file expanded to absolute path."""
    df = pd.read_csv(
        metadata_tsv, sep="\t", low_memory=False,
        usecols=["Sample", "is_refseq", "assembly_file"],
    )
    rs = df[df["is_refseq"].fillna(False).astype(bool)].copy()
    rs = rs[rs["assembly_file"].notna()].copy()
    # assembly_file is recorded relative to project_k/ (e.g. "seb/assemblies_2/.../X.fna.gz")
    # → resolve against the seb_root's parent (project_k).
    project_k = seb_root.parent
    rs["source_path"] = rs["assembly_file"].map(lambda f: str(project_k / f))
    # Use the bare GC[AF]_ accession as sample_id (matches NCBI Datasets join key).
    rs["sample_id"] = rs["Sample"].astype(str).str.extract(_ACC_RE, expand=False)
    rs = rs[rs["sample_id"].notna()].copy()
    rs["tier"] = "is_refseq"
    return rs[["sample_id", "tier", "source_path"]]


def symlink_into(manifest: pd.DataFrame, links_dir: Path) -> pd.DataFrame:
    """Populate links_dir with <sample_id>.fna.gz → source_path. Reports `exists`."""
    links_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, row in manifest.iterrows():
        src = Path(row["source_path"])
        link = links_dir / f"{row['sample_id']}.fna.gz"
        exists = src.is_file()
        if exists:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(src)
        rows.append({**row.to_dict(), "link_path": str(link), "exists": exists})
    return pd.DataFrame(rows)


def main() -> int:
    """CLI entry point — build the CheckM2 input manifest + symlinks."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    ap.add_argument("--lr-tsv",   type=Path, default=DEFAULT_LR_TSV)
    ap.add_argument("--lr-dir",   type=Path, default=DEFAULT_LR_DIR)
    ap.add_argument("--seb-root", type=Path, default=DEFAULT_SEB_ROOT,
                    help="Root containing the is_refseq assembly dirs (project_k/seb).")
    ap.add_argument("--out-dir",  type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    print(f"Metadata: {args.metadata}", flush=True)
    print(f"LR TSV:   {args.lr_tsv}", flush=True)
    print(f"LR dir:   {args.lr_dir}", flush=True)
    print(f"seb root: {args.seb_root}", flush=True)
    print(f"Out dir:  {args.out_dir}", flush=True)

    lr     = collect_lr_inputs(args.lr_tsv, args.lr_dir)
    refseq = collect_refseq_inputs(args.metadata, args.seb_root)
    manifest = pd.concat([lr, refseq], ignore_index=True)
    print(f"\nLR-GCA rows:    {len(lr)}")
    print(f"is_refseq rows: {len(refseq)}")
    print(f"Total:          {len(manifest)}")

    links_dir = args.out_dir / "links"
    manifest = symlink_into(manifest, links_dir)

    missing = manifest[~manifest["exists"]]
    print(f"\nSymlinked: {manifest['exists'].sum()}  Missing source: {len(missing)}")
    if len(missing):
        print("First 10 missing rows:")
        print(missing[["sample_id", "tier", "source_path"]].head(10).to_string(index=False))

    inputs_tsv = args.out_dir / "inputs.tsv"
    manifest.to_csv(inputs_tsv, sep="\t", index=False)
    print(f"\nWrote: {inputs_tsv}")
    print(f"Links: {links_dir}/<sample_id>.fna.gz  (n={manifest['exists'].sum()})")
    return 0 if len(missing) == 0 else 1  # nonzero exit when sources are missing


if __name__ == "__main__":
    sys.exit(main())
