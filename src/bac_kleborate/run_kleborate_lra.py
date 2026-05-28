#!/usr/bin/env python3
"""Run Kleborate v3 over the LRA cohort (Phase G.2).

Three subcommands, designed for a Slurm-array launch pattern:

  prepare — read ``metadata_v2``, filter to ``lra_final_list=True``, write
            ``lra_inputs.tsv`` (one row per LRA: ``Sample``, ``fasta_path``).
            Pure-local, ~5 s.

  worker  — run Kleborate on one chunk of ``lra_inputs.tsv``. Reads rows
            ``[chunk_idx * chunk_size : (chunk_idx + 1) * chunk_size]``,
            decompresses each ``.fna.gz`` to scratch, calls
            ``kleborate -p kpsc -a <fastas...> -o <chunk_out>``.
            Resumable: a per-chunk ``.done`` sentinel skips completed chunks.

  collate — walk every chunk's output dir and concatenate by Kleborate
            module name (e.g. ``klebsiella_pneumo_complex_output.txt``).
            Writes ``<out>/kleborate_<module>.tsv`` for each module.

Designed to run in the ``bac_isescan/pixi.toml`` env (already pins
``kleborate >= 3.1``). Slurm wrapper at
``slurm_scripts/run_kleborate_lra.sh``.

Usage::

    # 1. Build the input list (local, once):
    uv run python -m bac_kleborate.run_kleborate_lra prepare

    # 2. Submit the Slurm array (5,521 / 100 = 56 chunks):
    sbatch --array=0-55 src/bac_kleborate/slurm_scripts/run_kleborate_lra.sh

    # 3. Concatenate results once the array finishes:
    uv run python -m bac_kleborate.run_kleborate_lra collate
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
DEFAULT_OUT_DIR     = DATA_ROOT / "david/processed/kleborate_lra"
DEFAULT_INPUTS_TSV  = DEFAULT_OUT_DIR / "lra_inputs.tsv"
DEFAULT_CHUNK_SIZE  = 100
KLEBORATE_PRESET    = "kpsc"

_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")


# ─── PREPARE ──────────────────────────────────────────────────────────────────

def _bare(acc: object) -> str:
    """Return the bare (un-versioned) GCF/GCA accession, or ''."""
    if acc is None or pd.isna(acc):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1).split(".", 1)[0] if m else ""


def cmd_prepare(args: argparse.Namespace) -> int:
    """Build lra_inputs.tsv from metadata_v2."""
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
    """Decompress a gzipped FASTA to ``dest``."""
    if gz.suffix != ".gz":
        # Not gzipped — just symlink to avoid copying.
        dest.symlink_to(gz.resolve())
        return
    with gzip.open(gz, "rb") as fh, open(dest, "wb") as out:
        shutil.copyfileobj(fh, out)


def cmd_worker(args: argparse.Namespace) -> int:
    """Run Kleborate on one chunk."""
    chunk_out = args.out_dir / "chunks" / f"chunk_{args.chunk_idx:05d}"
    done_sentinel = chunk_out / ".kleborate.done"
    if done_sentinel.exists() and not args.force:
        print(f"chunk {args.chunk_idx}: already done (sentinel {done_sentinel}); skipping.")
        return 0

    inputs = pd.read_csv(args.inputs, sep="\t", low_memory=False)
    start = args.chunk_idx * args.chunk_size
    end = start + args.chunk_size
    batch = inputs.iloc[start:end].copy()
    if batch.empty:
        print(f"chunk {args.chunk_idx}: empty (start={start}, end={end}, n_inputs={len(inputs)})")
        return 0
    print(f"chunk {args.chunk_idx}: processing rows [{start}, {end}) → {len(batch)} genomes")

    chunk_out.mkdir(parents=True, exist_ok=True)
    # Decompress to scratch.
    with tempfile.TemporaryDirectory(prefix="kleb_lra_") as td:
        scratch = Path(td)
        fastas: list[str] = []
        for sample, fasta_path in batch[["Sample", "fasta_path"]].itertuples(index=False):
            gz = Path(fasta_path)
            if not gz.is_file():
                print(f"  WARN missing FASTA for {sample}: {gz}", file=sys.stderr)
                continue
            # Kleborate uses the input filename (minus extension) as the genome ID,
            # so write the decompressed file as <Sample>.fasta for clean joins later.
            dest = scratch / f"{_bare(sample) or sample}.fasta"
            _gunzip(gz, dest)
            fastas.append(str(dest))

        if not fastas:
            print(f"chunk {args.chunk_idx}: no FASTAs to process", file=sys.stderr)
            return 1

        cmd = ["kleborate", "-a", *fastas, "-o", str(chunk_out), "-p", KLEBORATE_PRESET]
        print(f"  running kleborate over {len(fastas)} genomes …", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  kleborate FAILED rc={r.returncode}", file=sys.stderr)
            print(r.stderr[-2000:], file=sys.stderr)
            return r.returncode

    done_sentinel.write_text(f"ok\nn_genomes={len(fastas)}\n")
    print(f"chunk {args.chunk_idx}: done.")
    return 0


# ─── COLLATE ──────────────────────────────────────────────────────────────────

def cmd_collate(args: argparse.Namespace) -> int:
    """Concatenate per-chunk Kleborate output by module name."""
    chunks_dir = args.out_dir / "chunks"
    if not chunks_dir.exists():
        print(f"no chunks dir at {chunks_dir}", file=sys.stderr)
        return 1

    chunks = sorted(chunks_dir.glob("chunk_*"))
    print(f"found {len(chunks)} chunk dirs under {chunks_dir}")
    by_module: dict[str, list[pd.DataFrame]] = {}
    n_done = 0
    n_failed = 0
    for c in chunks:
        if not (c / ".kleborate.done").exists():
            n_failed += 1
            print(f"  {c.name}: NO .kleborate.done sentinel — skipping in collate", file=sys.stderr)
            continue
        for txt in sorted(c.glob("*.txt")):
            try:
                df = pd.read_csv(txt, sep="\t", low_memory=False)
            except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
                print(f"  {c.name}/{txt.name}: read failed ({exc})", file=sys.stderr)
                continue
            by_module.setdefault(txt.name, []).append(df)
        n_done += 1

    if not by_module:
        print("no output to collate", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    for module_name, frames in by_module.items():
        concat = pd.concat(frames, ignore_index=True)
        # Kleborate writes "strain" as the genome ID; that's our Sample (bare GCF/GCA).
        if "strain" in concat.columns:
            concat = concat.rename(columns={"strain": "Sample"})
        out_path = args.out_dir / f"kleborate_{module_name[:-4] if module_name.endswith('.txt') else module_name}.tsv"
        concat.to_csv(out_path, sep="\t", index=False)
        summary_rows.append({"module": module_name, "rows": len(concat), "out": str(out_path)})

    print(f"\ncollated {n_done}/{len(chunks)} chunks ({n_failed} missing/failed)")
    print(pd.DataFrame(summary_rows).to_string(index=False))
    return 0 if n_failed == 0 else 1


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI dispatcher for ``prepare`` / ``worker`` / ``collate``."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="Build lra_inputs.tsv from metadata_v2.")
    p.add_argument("--metadata-v2", type=Path, default=DEFAULT_METADATA_V2)
    p.add_argument("--inputs",      type=Path, default=DEFAULT_INPUTS_TSV)
    p.add_argument("--out-dir",     type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--chunk-size",  type=int,  default=DEFAULT_CHUNK_SIZE)
    p.set_defaults(func=cmd_prepare)

    w = sub.add_parser("worker", help="Run Kleborate on one chunk (Slurm array task).")
    w.add_argument("--inputs",      type=Path, default=DEFAULT_INPUTS_TSV)
    w.add_argument("--chunk-idx",   type=int,  required=True)
    w.add_argument("--chunk-size",  type=int,  default=DEFAULT_CHUNK_SIZE)
    w.add_argument("--out-dir",     type=Path, default=DEFAULT_OUT_DIR)
    w.add_argument("--force", action="store_true", help="Re-run chunk even if sentinel exists.")
    w.set_defaults(func=cmd_worker)

    c = sub.add_parser("collate", help="Concatenate per-chunk Kleborate output.")
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    c.set_defaults(func=cmd_collate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
