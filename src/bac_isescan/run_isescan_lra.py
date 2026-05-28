#!/usr/bin/env python3
"""Run ISEScan over the LRA cohort (Phase G.2).

Mirror of :mod:`bac_kleborate.run_kleborate_lra` for ISEScan. Three
subcommands designed for a Slurm-array launch pattern:

  prepare — read ``metadata_v2``, filter to ``lra_final_list=True``, write
            ``isescan_inputs.tsv`` (one row per LRA: ``Sample``,
            ``fasta_path``). Pure-local, ~5 s.

  worker  — run ISEScan on one chunk of ``isescan_inputs.tsv``. Reads
            rows ``[chunk_idx * chunk_size : (chunk_idx + 1) * chunk_size]``,
            decompresses each ``.fna.gz`` to scratch, calls
            ``isescan.py --seqfile <fa> --output <per-sample-dir>
            --nthread <N>`` once per genome (sequentially within the
            chunk; chunk-level parallelism comes from the Slurm array).
            Per-genome ``.isescan.done`` sentinels make resumes idempotent.

  collate — walk every per-sample ISEScan output dir and concatenate
            the per-IS rows into one wide TSV plus a per-Sample IS-family
            count summary.

ISEScan is ~10 min/genome and parallelises poorly above ~4 threads. We
run one genome at a time per Slurm task at 4 threads, chunking ~30
genomes per task → 5,519 / 30 ≈ 184 tasks of ~5 h each.

Uses the ``bac_isescan/pixi.toml`` env (kleborate + isescan + pandas).
Slurm wrapper at ``slurm_scripts/run_isescan_lra.sh``.

Usage::

    # 1. Build the input list (login node):
    uv run python -m bac_isescan.run_isescan_lra prepare

    # 2. Submit the Slurm array (5,519 / 30 = ~184 chunks):
    sbatch --array=0-183 src/bac_isescan/slurm_scripts/run_isescan_lra.sh

    # 3. Concatenate results once the array finishes:
    uv run python -m bac_isescan.run_isescan_lra collate
"""

from __future__ import annotations

import argparse
import gzip
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_OUT_DIR     = DATA_ROOT / "david/processed/complete_vs_sr_genomes/isescan_lra"
DEFAULT_INPUTS_TSV  = DEFAULT_OUT_DIR / "isescan_inputs.tsv"
DEFAULT_CHUNK_SIZE  = 30
DEFAULT_THREADS     = 4

_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")


def _bare(acc: object) -> str:
    """Return the bare GCF/GCA accession (no .X version), or ''."""
    if acc is None or pd.isna(acc):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1) if m else ""


# ─── PREPARE ──────────────────────────────────────────────────────────────────

def cmd_prepare(args: argparse.Namespace) -> int:
    """Build isescan_inputs.tsv from metadata_v2."""
    args.out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)

    lra_mask = df["lra_final_list"].astype(str).str.lower().isin({"true", "1", "yes"})
    lra = df.loc[lra_mask, ["Sample", "lra_assembly_file"]].copy()
    n_total = len(lra)
    n_missing = int(lra["lra_assembly_file"].isna().sum())
    lra = lra.dropna(subset=["lra_assembly_file"])
    lra["lra_assembly_file"] = lra["lra_assembly_file"].astype(str)
    n_exists = int(lra["lra_assembly_file"].map(lambda p: Path(p).is_file()).sum())

    print(f"metadata_v2 rows         : {len(df):,}")
    print(f"lra_final_list=True rows  : {n_total:,}")
    print(f"  missing lra_assembly_file (skipped): {n_missing}")
    print(f"  fasta exists on disk            : {n_exists} / {len(lra)}")

    out = lra.rename(columns={"lra_assembly_file": "fasta_path"})
    out.to_csv(args.inputs, sep="\t", index=False)
    print(f"\nwrote {args.inputs}  rows={len(out)}")
    print(f"chunk plan @ chunk_size={args.chunk_size}: "
          f"{(len(out) + args.chunk_size - 1) // args.chunk_size} chunks "
          f"(array indices 0..{(len(out) - 1) // args.chunk_size})")
    return 0 if n_exists == len(out) else 1


# ─── WORKER ───────────────────────────────────────────────────────────────────

def _gunzip(gz: Path, dest: Path) -> None:
    """Decompress a gzipped FASTA to ``dest`` (or symlink if already uncompressed)."""
    if gz.suffix != ".gz":
        dest.symlink_to(gz.resolve())
        return
    with gzip.open(gz, "rb") as fh, open(dest, "wb") as out:
        shutil.copyfileobj(fh, out)


def _isescan_one(sample: str, fasta_path: Path, out_dir: Path, threads: int) -> tuple[str, bool, str]:
    """Run ISEScan on one genome. Returns (sample, ok, message)."""
    sample_bare = _bare(sample) or sample
    dest = out_dir / sample_bare
    done = dest / ".isescan.done"
    if done.exists():
        return (sample, True, "skipped (already done)")
    dest.mkdir(parents=True, exist_ok=True)

    if not fasta_path.is_file():
        return (sample, False, f"missing FASTA: {fasta_path}")

    with tempfile.TemporaryDirectory(prefix="isescan_") as td:
        scratch = Path(td)
        fa = scratch / f"{sample_bare}.fasta"
        _gunzip(fasta_path, fa)
        cmd = ["isescan.py", "--seqfile", str(fa), "--output", str(dest), "--nthread", str(threads)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return (sample, False, f"rc={r.returncode} stderr={r.stderr[-300:]!r}")

    done.write_text("ok\n")
    return (sample, True, "ok")


def cmd_worker(args: argparse.Namespace) -> int:
    """Run ISEScan on one chunk of inputs (Slurm array task)."""
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
        s, ok, msg = _isescan_one(sample, fp, per_sample_root, args.threads)
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

def cmd_collate(args: argparse.Namespace) -> int:
    """Concatenate per-sample ISEScan output into one wide TSV + family counts."""
    per_sample_root = args.out_dir / "per_sample"
    if not per_sample_root.exists():
        print(f"no per_sample dir at {per_sample_root}", file=sys.stderr)
        return 1

    sample_dirs = sorted(p for p in per_sample_root.iterdir() if p.is_dir())
    print(f"found {len(sample_dirs)} per-sample dirs under {per_sample_root}")

    frames = []
    n_done = 0
    n_no_tsv = 0
    for sd in sample_dirs:
        if not (sd / ".isescan.done").exists():
            continue
        n_done += 1
        # ISEScan writes its main per-IS table as <fa>.tsv. Concat anything matching *.tsv.
        tsvs = list(sd.rglob("*.tsv"))
        if not tsvs:
            n_no_tsv += 1
            continue
        for t in tsvs:
            try:
                df = pd.read_csv(t, sep="\t", low_memory=False)
            except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
                print(f"  {sd.name}/{t.name}: read failed ({exc})", file=sys.stderr)
                continue
            df["Sample"] = sd.name
            df["_src_file"] = t.name
            frames.append(df)

    if not frames:
        print("no output to collate", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_is = pd.concat(frames, ignore_index=True, sort=False)
    long_path = args.out_dir / "isescan_lra_long.tsv"
    all_is.to_csv(long_path, sep="\t", index=False)
    print(f"wrote {long_path}  rows={len(all_is):,}  cols={len(all_is.columns)}")
    print(f"  sample dirs done : {n_done}")
    print(f"  sample dirs with no TSV : {n_no_tsv}")

    # Per-Sample IS-family count summary (one row per Sample, columns are families).
    fam_col = None
    for cand in ("family", "Family", "IS_family", "isfamily"):
        if cand in all_is.columns:
            fam_col = cand
            break
    if fam_col is not None:
        counts = (
            all_is.groupby(["Sample", fam_col]).size().rename("count").reset_index()
        )
        wide = counts.pivot(index="Sample", columns=fam_col, values="count").fillna(0).astype(int)
        wide_path = args.out_dir / "isescan_lra_family_counts.tsv"
        wide.to_csv(wide_path, sep="\t")
        print(f"wrote {wide_path}  shape={wide.shape}")
    else:
        print("WARNING: no 'family' column in ISEScan output — family-count summary skipped.",
              file=sys.stderr)
    return 0


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI dispatcher for ``prepare`` / ``worker`` / ``collate``."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="Build isescan_inputs.tsv from metadata_v2.")
    p.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    p.add_argument("--inputs",      type=Path, default=DEFAULT_INPUTS_TSV)
    p.add_argument("--out-dir",     type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--chunk-size",  type=int,  default=DEFAULT_CHUNK_SIZE)
    p.set_defaults(func=cmd_prepare)

    w = sub.add_parser("worker", help="Run ISEScan on one chunk (Slurm array task).")
    w.add_argument("--inputs",      type=Path, default=DEFAULT_INPUTS_TSV)
    w.add_argument("--chunk-idx",   type=int,  required=True)
    w.add_argument("--chunk-size",  type=int,  default=DEFAULT_CHUNK_SIZE)
    w.add_argument("--out-dir",     type=Path, default=DEFAULT_OUT_DIR)
    w.add_argument("--threads",     type=int,  default=DEFAULT_THREADS)
    w.set_defaults(func=cmd_worker)

    c = sub.add_parser("collate", help="Concatenate per-sample ISEScan output.")
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    c.set_defaults(func=cmd_collate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
