#!/usr/bin/env python3
r"""Run geNomad over the full Klebsiella assembly set (LRA + SR).

Mirror of :mod:`bac_isescan.run_isescan_lra` for geNomad. Three subcommands
designed for a Slurm-array launch pattern:

  prepare — read ``metadata_v2`` and emit ``genomad_inputs.tsv`` with one row
            per FASTA to run. Columns: ``Sample`` | ``fasta_path`` | ``source``.
            Sources: ``lra`` (every row with ``lr_assembly_file`` populated),
            ``sr`` (every row with only ``sr_assembly_file`` — the legacy v1 SR
            column), ``sr_paired`` (rows that have both — the paired SR FASTA
            is emitted under ``<Sample>__sr`` so it doesn't collide with the
            LRA row).

  worker  — run geNomad on one chunk of ``genomad_inputs.tsv``. Reads rows
            ``[chunk_idx * chunk_size : (chunk_idx + 1) * chunk_size]``,
            decompresses each ``.fna.gz`` to scratch, invokes
            ``genomad end-to-end --cleanup --threads N --splits 0 <fa>
            <per-sample-dir> <db_dir>``. Per-sample ``.genomad.done`` sentinels
            make resumes idempotent; ``--cleanup`` deletes intermediate
            module subdirs on success and keeps only ``<bare>_summary/``.

  collate — walk every per-sample geNomad output dir and concatenate the
            ``*_plasmid_summary.tsv`` + ``*_virus_summary.tsv`` keepers into
            two long TSVs keyed by Sample.

geNomad is ~5 min/sample at 8 threads on a typical 5–6 Mb Klebsiella genome
(annotate/MMseqs2 dominates). We run one genome at a time per Slurm task at 8
threads, chunking ~100 genomes per task → ~8 h per chunk. With ~90 k jobs that
is ~900 array tasks at 16 h walltime.

Uses the ``bac_genomad/pixi.toml`` env (bioconda genomad). Slurm wrapper at
``slurm_scripts/run_genomad.sh``.

Usage::

    # 1. One-time geNomad DB download (login node, ~2 GB):
    pixi run genomad download-database \\
        /home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/db

    # 2. Build the input list (login node):
    pixi run python -m bac_genomad.run_genomad prepare

    # 3. Submit the Slurm array (90 k / 100 = ~900 chunks):
    sbatch --array=0-899 src/bac_genomad/slurm_scripts/run_genomad.sh

    # 4. Concatenate results once the array finishes:
    pixi run python -m bac_genomad.run_genomad collate
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from bac_genomad.genomad_constants import (
    DATA_ROOT,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_DB_DIR,
    DEFAULT_INPUTS_TSV,
    DEFAULT_METADATA_V2,
    DEFAULT_OUT_DIR,
    DEFAULT_THREADS,
    SR_PAIRED_SUFFIX,
)

# ─── PREPARE ──────────────────────────────────────────────────────────────────

def _resolve(path: object) -> Path | None:
    """Resolve a metadata path to an existing absolute file, else ``None``.

    metadata_v2 stores ``lr_assembly_file`` as absolute paths but
    ``sr_assembly_file`` (SR) relative to the RDS ``DATA_ROOT``. Relative paths are
    joined onto ``DATA_ROOT``; the result is returned only if it is a real file.
    """
    if path is None or pd.isna(path):
        return None
    p = Path(str(path))
    if not p.is_absolute():
        p = DATA_ROOT / p
    return p if p.is_file() else None


def cmd_prepare(args: argparse.Namespace) -> int:
    """Build genomad_inputs.tsv from metadata_v2 (LRA + SR + paired-SR rows)."""
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.inputs.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    print(f"metadata_v2 rows: {len(df):,}")

    df["_lra_path"] = df["lr_assembly_file"].map(_resolve)
    df["_sr_path"]  = df["sr_assembly_file"].map(_resolve)
    has_lra = df["_lra_path"].notna()
    has_sr  = df["_sr_path"].notna()
    print(f"  rows with lr_assembly_file on disk: {int(has_lra.sum()):,}")
    print(f"  rows with sr_assembly_file (SR) on disk: {int(has_sr.sum()):,}")
    print(f"  rows with BOTH (paired): {int((has_lra & has_sr).sum()):,}")

    rows: list[dict] = []

    for sample, p in df.loc[has_lra, ["Sample", "_lra_path"]].itertuples(index=False):
        rows.append({"Sample": sample, "fasta_path": str(p), "source": "lra"})

    sr_only_mask = has_sr & ~has_lra
    for sample, p in df.loc[sr_only_mask, ["Sample", "_sr_path"]].itertuples(index=False):
        rows.append({"Sample": sample, "fasta_path": str(p), "source": "sr"})

    paired_mask = has_sr & has_lra
    for sample, p in df.loc[paired_mask, ["Sample", "_sr_path"]].itertuples(index=False):
        rows.append({
            "Sample": f"{sample}{SR_PAIRED_SUFFIX}",
            "fasta_path": str(p),
            "source": "sr_paired",
        })

    out = pd.DataFrame(rows, columns=["Sample", "fasta_path", "source"])
    n_dups = int(out["Sample"].duplicated().sum())
    if n_dups:
        print(f"WARNING: {n_dups} duplicate Sample ids in output — investigate.", file=sys.stderr)

    out.to_csv(args.inputs, sep="\t", index=False)
    print(f"\nwrote {args.inputs}")
    print(f"  total rows: {len(out):,}")
    print(out["source"].value_counts().to_string())

    n_chunks = (len(out) + args.chunk_size - 1) // args.chunk_size
    print(f"\nchunk plan @ chunk_size={args.chunk_size}: "
          f"{n_chunks} chunks (array indices 0..{n_chunks - 1})")
    return 0


# ─── WORKER ───────────────────────────────────────────────────────────────────

def _gunzip(gz: Path, dest: Path) -> None:
    """Decompress a gzipped FASTA to ``dest`` (or symlink if already uncompressed)."""
    if gz.suffix != ".gz":
        dest.symlink_to(gz.resolve())
        return
    with gzip.open(gz, "rb") as fh, open(dest, "wb") as out:
        shutil.copyfileobj(fh, out)


def _genomad_one(
    sample: str,
    fasta_path: Path,
    out_root: Path,
    db_dir: Path,
    threads: int,
) -> tuple[str, bool, str]:
    """Run geNomad end-to-end on one assembly. Returns (sample, ok, message)."""
    dest = out_root / sample
    done = dest / ".genomad.done"
    if done.exists():
        return (sample, True, "skipped (already done)")
    dest.mkdir(parents=True, exist_ok=True)

    if not fasta_path.is_file():
        return (sample, False, f"missing FASTA: {fasta_path}")

    with tempfile.TemporaryDirectory(prefix="genomad_") as td:
        scratch = Path(td)
        fa = scratch / f"{sample}.fna"
        _gunzip(fasta_path, fa)
        cmd = [
            "genomad", "end-to-end",
            "--cleanup",
            "--threads", str(threads),
            "--splits", "0",
            str(fa),
            str(dest),
            str(db_dir),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return (sample, False, f"rc={r.returncode} stderr={r.stderr[-300:]!r}")

    done.write_text("ok\n")
    return (sample, True, "ok")


def cmd_worker(args: argparse.Namespace) -> int:
    """Run geNomad on one chunk of inputs (Slurm array task)."""
    if not args.db_dir.is_dir():
        print(f"FATAL: geNomad DB not found at {args.db_dir} — "
              f"run 'pixi run genomad download-database <parent>' first", file=sys.stderr)
        return 2

    inputs = pd.read_csv(args.inputs, sep="\t", low_memory=False)
    start = args.chunk_idx * args.chunk_size
    end   = start + args.chunk_size
    batch = inputs.iloc[start:end].copy()
    if batch.empty:
        print(f"chunk {args.chunk_idx}: empty (start={start}, end={end}, n_inputs={len(inputs)})")
        return 0

    per_sample_root = args.out_dir / "per_sample"
    per_sample_root.mkdir(parents=True, exist_ok=True)
    chunk_log_dir = args.out_dir / "chunk_logs"
    chunk_log_dir.mkdir(parents=True, exist_ok=True)

    print(f"chunk {args.chunk_idx}: processing rows [{start}, {end}) → {len(batch)} genomes")
    n_ok, n_skip, n_fail = 0, 0, 0
    failures: list[str] = []
    for i, row in enumerate(batch.itertuples(index=False), 1):
        sample, fp = row.Sample, Path(row.fasta_path)
        s, ok, msg = _genomad_one(sample, fp, per_sample_root, args.db_dir, args.threads)
        if not ok:
            n_fail += 1
            failures.append(f"{s}\t{msg}")
            print(f"  [{i}/{len(batch)}] {s}  FAIL  {msg}", file=sys.stderr, flush=True)
        elif msg.startswith("skipped"):
            n_skip += 1
        else:
            n_ok += 1
        if i % 5 == 0 or i == len(batch):
            print(f"  [{i}/{len(batch)}] {s}  {msg}", flush=True)

    log_path = chunk_log_dir / f"chunk_{args.chunk_idx:05d}.log"
    with log_path.open("w") as fh:
        fh.write(f"chunk_idx\t{args.chunk_idx}\nstart\t{start}\nend\t{end}\n")
        fh.write(f"n_ok\t{n_ok}\nn_skip\t{n_skip}\nn_fail\t{n_fail}\n")
        if failures:
            fh.write("\nfailures:\n")
            fh.write("\n".join(failures))
    print(f"chunk {args.chunk_idx}: ok={n_ok}, skip={n_skip}, fail={n_fail}  log={log_path}")
    return 0 if n_fail == 0 else 1


# ─── COLLATE ──────────────────────────────────────────────────────────────────

def _read_summary_tsv(path: Path, sample: str) -> pd.DataFrame | None:
    """Read one geNomad summary TSV and tag rows with ``Sample``. None on read failure."""
    try:
        df = pd.read_csv(path, sep="\t", low_memory=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        print(f"  {sample}/{path.name}: read failed ({exc})", file=sys.stderr)
        return None
    df.insert(0, "Sample", sample)
    return df


def _collate_one(sd: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None, str]:
    """Read one sample's plasmid + virus summary TSVs. Returns (plasmid_df, virus_df, status).

    Status is one of: ``ok`` (both read), ``no_sentinel`` (sample not yet done),
    ``no_summary`` (sentinel present but the summary files are missing).
    """
    if not (sd / ".genomad.done").exists():
        return (None, None, "no_sentinel")
    summary_dir = sd / f"{sd.name}_summary"
    plasmid_path = summary_dir / f"{sd.name}_plasmid_summary.tsv"
    virus_path   = summary_dir / f"{sd.name}_virus_summary.tsv"
    pdf = _read_summary_tsv(plasmid_path, sd.name) if plasmid_path.is_file() else None
    vdf = _read_summary_tsv(virus_path,   sd.name) if virus_path.is_file()   else None
    status = "ok" if (pdf is not None or vdf is not None) else "no_summary"
    return (pdf, vdf, status)


def cmd_collate(args: argparse.Namespace) -> int:
    """Concatenate per-sample geNomad plasmid + virus summary TSVs (threaded)."""
    from concurrent.futures import ThreadPoolExecutor

    per_sample_root = args.out_dir / "per_sample"
    if not per_sample_root.exists():
        print(f"no per_sample dir at {per_sample_root}", file=sys.stderr)
        return 1

    sample_dirs = sorted(p for p in per_sample_root.iterdir() if p.is_dir())
    print(f"found {len(sample_dirs)} per-sample dirs under {per_sample_root}")
    if args.limit and args.limit > 0:
        sample_dirs = sample_dirs[: args.limit]
        print(f"  (limited to first {len(sample_dirs)} for inspection)")

    plasmid_frames: list[pd.DataFrame] = []
    virus_frames:   list[pd.DataFrame] = []
    n_done = n_no_sentinel = n_no_summary = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for pdf, vdf, status in pool.map(_collate_one, sample_dirs):
            if status == "no_sentinel":
                n_no_sentinel += 1
                continue
            if status == "no_summary":
                n_no_summary += 1
                continue
            n_done += 1
            if pdf is not None:
                plasmid_frames.append(pdf)
            if vdf is not None:
                virus_frames.append(vdf)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    if plasmid_frames:
        plasmids = pd.concat(plasmid_frames, ignore_index=True, sort=False)
        plasmid_path = args.out_dir / "genomad_plasmid_summary_long.tsv"
        plasmids.to_csv(plasmid_path, sep="\t", index=False)
        print(f"wrote {plasmid_path}  rows={len(plasmids):,}  cols={len(plasmids.columns)}")
    else:
        print("no plasmid summaries found", file=sys.stderr)
        ok = False

    if virus_frames:
        viruses = pd.concat(virus_frames, ignore_index=True, sort=False)
        virus_path = args.out_dir / "genomad_virus_summary_long.tsv"
        viruses.to_csv(virus_path, sep="\t", index=False)
        print(f"wrote {virus_path}  rows={len(viruses):,}  cols={len(viruses.columns)}")
    else:
        print("no virus summaries found", file=sys.stderr)
        ok = False

    print(f"  sample dirs done       : {n_done}")
    print(f"  sample dirs no sentinel: {n_no_sentinel}")
    print(f"  sample dirs no summary : {n_no_summary}")
    return 0 if ok else 1


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI dispatcher for ``prepare`` / ``worker`` / ``collate``."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="Build genomad_inputs.tsv from metadata_v2.")
    p.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    p.add_argument("--inputs",      type=Path, default=DEFAULT_INPUTS_TSV)
    p.add_argument("--out-dir",     type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--chunk-size",  type=int,  default=DEFAULT_CHUNK_SIZE)
    p.set_defaults(func=cmd_prepare)

    w = sub.add_parser("worker", help="Run geNomad on one chunk (Slurm array task).")
    w.add_argument("--inputs",      type=Path, default=DEFAULT_INPUTS_TSV)
    w.add_argument("--chunk-idx",   type=int,  required=True)
    w.add_argument("--chunk-size",  type=int,  default=DEFAULT_CHUNK_SIZE)
    w.add_argument("--out-dir",     type=Path, default=DEFAULT_OUT_DIR)
    w.add_argument("--db-dir",      type=Path, default=DEFAULT_DB_DIR)
    w.add_argument("--threads",     type=int,  default=DEFAULT_THREADS)
    w.set_defaults(func=cmd_worker)

    c = sub.add_parser("collate", help="Concatenate per-sample geNomad summaries.")
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    c.add_argument("--workers", type=int, default=16,
                   help="Thread pool size for parallel summary-TSV reads (default: 16).")
    c.add_argument("--limit",   type=int, default=0,
                   help="If >0, only collate the first N per-sample dirs (subset inspection).")
    c.set_defaults(func=cmd_collate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
