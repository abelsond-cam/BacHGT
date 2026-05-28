#!/usr/bin/env python3
"""Build the unified LRA discovery TSV — one row per biological assembly.

build_lra_discovery.py
----------------------
Replaces the lost ad-hoc ``related_lr_all_gca.tsv`` with a comprehensive
``lra_discovery.tsv`` keyed on **biological assembly** (not accession), with
sibling ``GCA`` / ``GCF`` columns. One row per assembly. ``GCF`` is the CheckM2
scoring target whenever it exists (RefSeq is the curated version); the GCA
column carries the GenBank pairing.

Single source of truth for the CheckM2 cohort: ``prep_checkm2_inputs.py``
reads it, ``annotate_checkm2.py`` writes results back to it, the
``lra_quality_cutoffs.ipynb`` notebook joins on it, and ``build_lra_set.py``
filters it.

Three input sources merged on biological assembly identity:

  1. ``related_lr_complete_assembly_audit.tsv`` (LR audit) — 2,571 GCAs of
     which 1,665 carry a paired GCF.
  2. ``norway_tables1_integration.tsv`` (Norway Table S1) — 534 resolved
     GCAs of which 270 carry a paired GCF.
  3. Curated metadata rows with ``is_refseq=True`` — 3,911 rows; ``Sample``
     holds either a GCF (most) or a stale GCA (~280 mis-flagged).

Two rows refer to the same assembly when their (version-stripped) ``GCA``s
match OR their ``GCF``s match. Merging ORs the per-source provenance flags
so a row found in multiple sources keeps the full lineage.

Schema (output ``lra_discovery.tsv``)::

    # identity
    GCA, GCF, accession_bare_primary, Sample, related_lr_run_accession

    # provenance
    source_audit, source_norway, source_refseq_metadata,
    is_norway, is_refseq, stale_refseq

    # NCBI metadata (when available)
    level

    # scoring
    scoring_accession, expected_fasta_path, fasta_on_disk, download_needed

CheckM2 result columns (``completeness``, ``contamination``, …) are appended
later by ``annotate_checkm2.py``; this module does not touch them.

Usage::

    uv run python -m bac_data.lr_data.build_lra_discovery
    uv run python -m bac_data.lr_data.build_lra_discovery --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_AUDIT_TSV  = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lr_discovery/related_lr_complete_assembly_audit.tsv"
DEFAULT_NORWAY_TSV = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lr_discovery/norway_tables1_integration.tsv"
DEFAULT_METADATA   = DATA_ROOT / "david/final/metadata_final_curated_all_samples_and_columns.tsv"
DEFAULT_LR_ASM_DIR = DATA_ROOT / "david/raw/related_lr/assemblies"
DEFAULT_PROJECT_K  = DATA_ROOT                # for resolving metadata.assembly_file
DEFAULT_OUT_TSV    = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lr_discovery/lra_discovery.tsv"

# Sample column → bare GCA/GCF accession. Same regex as prep_checkm2_inputs.
_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")

PROVENANCE_COLS = ["source_audit", "source_norway", "source_refseq_metadata"]
FLAG_COLS       = ["is_norway", "is_refseq"]

# Final output column order — deterministic, easy to eyeball.
OUTPUT_COLS = [
    "GCA", "GCF", "accession_bare_primary", "Sample", "related_lr_run_accession",
    "source_audit", "source_norway", "source_refseq_metadata",
    "is_norway", "is_refseq", "stale_refseq",
    "level",
    "scoring_accession", "expected_fasta_path", "fasta_on_disk", "download_needed",
]


# ─── PER-SOURCE LOADERS ───────────────────────────────────────────────────────

def _bare(acc: object) -> str:
    """Return the version-stripped bare accession, or ``''`` if no match."""
    if acc is None or (isinstance(acc, float) and np.isnan(acc)):
        return ""
    s = str(acc).strip()
    if not s:
        return ""
    return s.split(".", 1)[0]


def load_audit(audit_tsv: Path) -> pd.DataFrame:
    """One row per audited LR sample. Drops rows without a GCA (no assembly found)."""
    df = pd.read_csv(audit_tsv, sep="\t", low_memory=False, dtype=str).fillna("")
    df = df[df["gca"].str.startswith("GCA_")].copy()
    out = pd.DataFrame({
        "GCA":   df["gca"],
        "GCF":   df["gcf"].where(df["gcf"].str.startswith("GCF_"), ""),
        "Sample": df["Sample"],
        "related_lr_run_accession": df["related_lr_accession"],
        "level":  df["level"],
        "seb_path": "",
        "source_audit": True,
        "source_norway": False,
        "source_refseq_metadata": False,
        "is_norway": False,
        "is_refseq": False,
    })
    return out


def load_norway(norway_tsv: Path) -> pd.DataFrame:
    """One row per Norway Table S1 strain that resolved to a GenBank GCA."""
    df = pd.read_csv(norway_tsv, sep="\t", low_memory=False, dtype=str).fillna("")
    df = df[df["resolved_gca"].str.startswith("GCA_")].copy()
    out = pd.DataFrame({
        "GCA":   df["resolved_gca"],
        "GCF":   df["resolved_refseq_gcf"].where(df["resolved_refseq_gcf"].str.startswith("GCF_"), ""),
        # The Norway integration adds rows to metadata keyed on biosample; carry
        # the Norway BioSample as Sample so the join back is unambiguous.
        "Sample": df["biosample"],
        # ont_acc = the actual ONT DRR/SRR run accession.
        # ont_in_run_accession is the *boolean* indicator of whether that accession
        # is present in our metadata's run_accession column — not the accession itself.
        "related_lr_run_accession": df["ont_acc"],
        "level":  df["assembly_level"],
        "seb_path": "",
        "source_audit": False,
        "source_norway": True,
        "source_refseq_metadata": False,
        "is_norway": True,
        "is_refseq": False,
    })
    return out


def load_refseq_metadata(metadata_tsv: Path) -> pd.DataFrame:
    """One row per ``is_refseq=True`` metadata sample. Sample column holds GCF (mostly) or GCA.

    If the metadata carries an ``assembly_file`` column (populated by
    ``bac_metadata.pp.add_paths_gff_fna_to_metadata`` — relative to project_k),
    pass it through as ``seb_path`` so ``derive_scoring`` can prefer the
    existing seb/ FASTA over re-downloading.
    """
    head = pd.read_csv(metadata_tsv, sep="\t", nrows=0).columns.tolist()
    cols = ["Sample", "is_refseq"]
    if "assembly_file" in head:
        cols.append("assembly_file")
    df = pd.read_csv(metadata_tsv, sep="\t", low_memory=False, usecols=cols, dtype=str).fillna("")
    rs = df[df["is_refseq"].str.lower().isin({"true", "1", "yes"})].copy()
    rs["acc"] = rs["Sample"].astype(str).str.extract(_ACC_RE, expand=False).fillna("")
    rs = rs[rs["acc"] != ""].copy()
    is_gcf = rs["acc"].str.startswith("GCF_")
    out = pd.DataFrame({
        "GCA":   np.where(is_gcf, "", rs["acc"]),
        "GCF":   np.where(is_gcf, rs["acc"], ""),
        "Sample": rs["Sample"],
        "related_lr_run_accession": "",
        "level":  "",
        "seb_path": rs["assembly_file"] if "assembly_file" in rs.columns else "",
        "source_audit": False,
        "source_norway": False,
        "source_refseq_metadata": True,
        "is_norway": False,
        "is_refseq": True,
    })
    return out


# ─── MERGE LOGIC ──────────────────────────────────────────────────────────────

def _aggregate(rows: pd.DataFrame) -> pd.Series:
    """Collapse rows sharing one biological assembly into a single record."""
    def first_nonempty(series: pd.Series) -> str:
        for v in series:
            s = str(v) if v is not None else ""
            if s and s.lower() != "nan":
                return s
        return ""
    return pd.Series({
        "GCA":   first_nonempty(rows["GCA"]),
        "GCF":   first_nonempty(rows["GCF"]),
        "Sample": first_nonempty(rows["Sample"]),
        "related_lr_run_accession": first_nonempty(rows["related_lr_run_accession"]),
        "level":  first_nonempty(rows["level"]),
        "seb_path": first_nonempty(rows["seb_path"]),
        "source_audit":          bool(rows["source_audit"].any()),
        "source_norway":         bool(rows["source_norway"].any()),
        "source_refseq_metadata": bool(rows["source_refseq_metadata"].any()),
        "is_norway":  bool(rows["is_norway"].any()),
        "is_refseq":  bool(rows["is_refseq"].any()),
    })


def _merge_on_key(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    """Merge rows sharing a non-empty bare value in ``key_col``."""
    bare = df[key_col].map(_bare)
    grouped_mask = bare != ""
    if not grouped_mask.any():
        return df.reset_index(drop=True)
    grouped = (
        df[grouped_mask]
        .assign(_key=bare[grouped_mask])
        .groupby("_key", sort=False, group_keys=False)
        .apply(_aggregate, include_groups=False)
        .reset_index(drop=True)
    )
    untouched = df[~grouped_mask].reset_index(drop=True)
    return pd.concat([grouped, untouched], ignore_index=True)


def merge_assemblies(audit: pd.DataFrame, norway: pd.DataFrame, refseq: pd.DataFrame) -> pd.DataFrame:
    """Union the three sources, merging rows that share a GCA or GCF accession."""
    combined = pd.concat([audit, norway, refseq], ignore_index=True)
    # Two passes: first merge on GCF (RefSeq is the curated identity), then on GCA.
    # Both passes use _bare so any version mismatch between sources still merges.
    combined = _merge_on_key(combined, "GCF")
    combined = _merge_on_key(combined, "GCA")
    return combined


# ─── DERIVED COLUMNS ──────────────────────────────────────────────────────────

def derive_scoring(df: pd.DataFrame, lr_asm_dir: Path, project_k: Path) -> pd.DataFrame:
    """Add ``scoring_accession``, ``expected_fasta_path``, ``fasta_on_disk``, ``download_needed``.

    Per-row resolution:
      1. Prefer the GCF (RefSeq is the curated version) — try seb path first,
         then ``lr_asm_dir/<GCF>.fna.gz``.
      2. If the GCF FASTA isn't reachable on disk anywhere (typically because
         RefSeq suppressed it), fall back to the paired GCA's FASTA. The
         ``scoring_accession`` flips to the GCA accession in that case.
      3. If neither has a FASTA on disk, ``scoring_accession`` is left at the
         preferred (GCF if present, else GCA) and ``download_needed=True``.

    This means a re-run after downloading the fallback GCA automatically
    picks it up — no manual TSV edits needed for suppressed-GCF rows.
    """
    df = df.copy()

    def _try_path(acc: str, seb_rel: str) -> str:
        """Return the on-disk path for ``acc`` (seb first, then LR pool), or ''."""
        if not acc:
            return ""
        if seb_rel:
            seb_full = str(project_k / seb_rel)
            if Path(seb_full).is_file() and Path(seb_full).stat().st_size > 0:
                return seb_full
        lr_full = str(lr_asm_dir / f"{acc}.fna.gz")
        if Path(lr_full).is_file() and Path(lr_full).stat().st_size > 0:
            return lr_full
        return ""

    def _resolve(row: pd.Series) -> tuple[str, str, str]:
        gca, gcf, seb = row["GCA"], row["GCF"], row.get("seb_path", "")
        # GCF preferred when present on disk anywhere.
        if gcf:
            on_disk = _try_path(gcf, seb)
            if on_disk:
                return gcf, on_disk, on_disk
        # GCF missing on disk — fall back to GCA if it has a FASTA.
        if gca:
            on_disk = _try_path(gca, seb if not gcf else "")
            if on_disk:
                return gca, on_disk, on_disk
        # Neither on disk: set scoring to preferred (GCF if present, else GCA)
        # and expected_fasta_path under the LR pool, so the downloader queues it.
        preferred = gcf or gca
        expected = str(lr_asm_dir / f"{preferred}.fna.gz") if preferred else ""
        return preferred, expected, ""

    resolved = df.apply(_resolve, axis=1, result_type="expand")
    df["scoring_accession"]   = resolved[0]
    df["expected_fasta_path"] = resolved[1]
    df["fasta_on_disk"]       = resolved[2]
    df["download_needed"]     = df["fasta_on_disk"] == ""
    return df


def derive_identity_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``accession_bare_primary`` (dedup key) and ``stale_refseq`` flag."""
    df = df.copy()
    df["accession_bare_primary"] = np.where(
        df["GCF"] != "", df["GCF"].map(_bare), df["GCA"].map(_bare),
    )
    df["stale_refseq"] = df["is_refseq"] & (df["GCF"] == "")
    return df


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _print_counts(audit: pd.DataFrame, norway: pd.DataFrame, refseq: pd.DataFrame, out: pd.DataFrame) -> None:
    """Print the verification block the plan calls out."""
    print()
    print(f"audit_in  : {len(audit):>5}  GCA  /  {(audit['GCF'] != '').sum():>5}  paired-GCF")
    print(f"norway_in : {len(norway):>5}  GCA  /  {(norway['GCF'] != '').sum():>5}  paired-GCF")
    print(
        f"refseq_in : {len(refseq):>5}  rows / "
        f"{(refseq['GCF'] != '').sum():>5}  GCF / "
        f"{(refseq['GCA'] != '').sum():>5}  GCA-only (stale candidates)"
    )
    print()
    print(f"merged_unique_assemblies : {len(out):>5}")
    print(f"  with_GCF (preferred for CheckM2)             : {(out['GCF'] != '').sum():>5}")
    print(f"  with_GCA_only (no paired RefSeq)             : {((out['GCF'] == '') & (out['GCA'] != '')).sum():>5}")
    print(f"  paired (both GCA AND GCF)                    : {((out['GCF'] != '') & (out['GCA'] != '')).sum():>5}")
    print(f"  GCF-only (no paired GenBank GCA)             : {((out['GCF'] != '') & (out['GCA'] == '')).sum():>5}")
    print(f"  stale_refseq (is_refseq=True but GCF blank)  : {int(out['stale_refseq'].sum()):>5}")
    print(f"  download_needed                              : {int(out['download_needed'].sum()):>5}")
    print()

    print("source provenance (per-source totals — multi-source rows counted in each):")
    audit_n  = int(out["source_audit"].sum())
    norway_n = int(out["source_norway"].sum())
    refseq_n = int(out["source_refseq_metadata"].sum())
    naive    = audit_n + norway_n + refseq_n
    print(f"  source_audit             : {audit_n:>5}")
    print(f"  source_norway            : {norway_n:>5}")
    print(f"  source_refseq_metadata   : {refseq_n:>5}")
    print(f"  naive sum                : {naive:>5}")
    print(f"  merged unique rows       : {len(out):>5}")
    print(f"  dedups removed           : {naive - len(out):>5}")
    print()

    # Membership cross-tab — the 7-way Venn over {audit, norway, refseq}.
    # Single-counted (each row in exactly one bucket); columns sum to the
    # merged total and the math (with multi-source rows pair-/triple-counted)
    # explains where the dedups land.
    print("provenance cross-tab (each row counted once):")
    flags = out[["source_audit", "source_norway", "source_refseq_metadata"]].astype(bool)
    labels = flags.apply(
        lambda r: "+".join(t for t, v in zip(("audit", "norway", "refseq"), r, strict=True) if v) or "(none)",
        axis=1,
    )
    vc = labels.value_counts()
    # Ordering: solo sources first, then pairs, then triples — easier to eyeball.
    order = [
        "audit", "norway", "refseq",
        "audit+norway", "audit+refseq", "norway+refseq",
        "audit+norway+refseq", "(none)",
    ]
    for k in order:
        if k in vc.index:
            print(f"  {k:<24} : {int(vc[k]):>5}")
    print()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — read 3 sources, union, write ``lra_discovery.tsv``."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit-tsv",  type=Path, default=DEFAULT_AUDIT_TSV)
    ap.add_argument("--norway-tsv", type=Path, default=DEFAULT_NORWAY_TSV)
    ap.add_argument("--metadata",   type=Path, default=DEFAULT_METADATA)
    ap.add_argument("--lr-asm-dir", type=Path, default=DEFAULT_LR_ASM_DIR,
                    help="Canonical pool for downloaded GCA + GCF FASTAs.")
    ap.add_argument("--project-k",  type=Path, default=DEFAULT_PROJECT_K,
                    help="Root for resolving metadata.assembly_file (relative paths).")
    ap.add_argument("--out-tsv",    type=Path, default=DEFAULT_OUT_TSV)
    ap.add_argument("--dry-run",   action="store_true",
                    help="Print counts but don't write the output TSV.")
    args = ap.parse_args(argv)

    print(f"audit_tsv  : {args.audit_tsv}")
    print(f"norway_tsv : {args.norway_tsv}")
    print(f"metadata   : {args.metadata}")
    print(f"lr_asm_dir : {args.lr_asm_dir}")
    print(f"out_tsv    : {args.out_tsv}")

    audit  = load_audit(args.audit_tsv)
    norway = load_norway(args.norway_tsv)
    refseq = load_refseq_metadata(args.metadata)

    merged = merge_assemblies(audit, norway, refseq)
    merged = derive_identity_cols(merged)
    merged = derive_scoring(merged, args.lr_asm_dir, args.project_k)
    merged = merged.sort_values("accession_bare_primary").reset_index(drop=True)
    merged = merged[OUTPUT_COLS]

    _print_counts(audit, norway, refseq, merged)

    if args.dry_run:
        print("--dry-run set; not writing output.")
        return 0

    if args.out_tsv.exists():
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = args.out_tsv.with_suffix(f".bak.{ts}.tsv")
        args.out_tsv.rename(backup)
        print(f"backed up existing → {backup.name}")
    args.out_tsv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.out_tsv, sep="\t", index=False)
    print(f"wrote {args.out_tsv}  rows={len(merged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
