#!/usr/bin/env python3
"""Batch Kleborate + ISEScan over the local related-LR genome sets.

Drives Kleborate (KpSC typing — species, ST, virulence, AMR, K/O loci)
and ISEScan (IS-element / mobile-element discovery) across the three
locally-staged genome sets so the short-read drafts can be compared
against their long-read GCA/GCF assemblies for ICE / virulence / AMR
discrepancies.

Runs **inside the pixi env** (provides both tools + their blast/hmmer
deps)::

    pixi run annotate --groups sr,gca,gcf --tools kleborate,isescan
    pixi run annotate --limit 3 --tools kleborate          # smoke-test

Genome sets (under ``--data-dir``, default the local related_lr mirror):
  * ``sr``   sr_originals/**/*.fa.gz      key = file stem (BioSample)
  * ``gca``  assemblies/GCA_*.fna.gz      key = GCA accession
  * ``gcf``  assemblies/GCF_*.fna.gz      key = GCF accession

Both tools need uncompressed FASTA, so each genome is decompressed to a
scratch dir for the run and removed afterwards. The run is **resumable**:
a per-key sentinel / existing output is skipped, so re-invoking after an
interruption only does the remaining work.

Outputs (under ``--out-dir``, default ``<data-dir>/annotations``):
  kleborate/<group>__<module>.txt   per-module Kleborate tables, concatenated per set
  isescan/<group>/<key>/...         per-genome ISEScan result tree
  isescan/<group>_isescan.tsv       concatenated IS calls (key-tagged)
  annotation_manifest.tsv           per-(group,key,tool) status
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

DEFAULT_DATA_DIR = Path(
    "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/local_data/klebsiella/raw/related_lr"
)
GROUP_GLOBS = {
    "sr": ("sr_originals", "*.fa.gz"),
    "gca": ("assemblies", "GCA_*.fna.gz"),
    "gcf": ("assemblies", "GCF_*.fna.gz"),
}
KLEBORATE_PRESET = "kpsc"


def _key(path: Path) -> str:
    """Stable per-genome key: strip .gz then the assembly extension."""
    name = path.name
    for suf in (".fa.gz", ".fna.gz", ".fasta.gz"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return path.stem


def discover(data_dir: Path, group: str) -> list[tuple[str, Path]]:
    """Return sorted ``(key, gz_path)`` for one genome set."""
    sub, pat = GROUP_GLOBS[group]
    base = data_dir / sub
    if not base.exists():
        return []
    return sorted(((_key(p), p) for p in base.rglob(pat)), key=lambda t: t[0])


def _gunzip(gz: Path, dest: Path) -> None:
    """Decompress ``gz`` to ``dest`` (uncompressed FASTA)."""
    with gzip.open(gz, "rb") as fh, open(dest, "wb") as out:
        shutil.copyfileobj(fh, out)


# ─── KLEBORATE ────────────────────────────────────────────────────────────────


def run_kleborate(genomes: list[tuple[str, Path]], out_dir: Path, group: str, chunk: int) -> dict:
    """Run Kleborate over one set in chunks; concat **per module file**.

    Kleborate v3 accepts many ``-a`` assemblies per call (we batch to
    keep process overhead low) and writes several different-schema
    ``*.txt`` modules — e.g. the main per-strain typing table and the
    long hAMRonization AMR-hit table. These must be kept apart, so each
    distinct module filename is concatenated only with itself across
    chunks into ``<out_dir>/kleborate/<group>__<module>.txt``.
    """
    kdir = out_dir / "kleborate"
    kdir.mkdir(parents=True, exist_ok=True)
    done = kdir / f".{group}.kleborate.done"
    if done.exists():
        return {"group": group, "tool": "kleborate", "status": "skipped_exists", "n": len(genomes)}

    by_module: dict[str, list[pd.DataFrame]] = {}
    n_done = 0
    for i in range(0, len(genomes), chunk):
        batch = genomes[i : i + chunk]
        with tempfile.TemporaryDirectory(prefix="kleb_") as td:
            tdp = Path(td)
            fastas = []
            for key, gz in batch:
                fa = tdp / f"{key}.fasta"
                _gunzip(gz, fa)
                fastas.append(str(fa))
            cout = tdp / "out"
            cmd = ["kleborate", "-a", *fastas, "-o", str(cout), "-p", KLEBORATE_PRESET]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(
                    f"  WARN kleborate {group} chunk@{i} rc={r.returncode}: {r.stderr[-300:]}",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            for txt in sorted(cout.glob("*.txt")):
                df = pd.read_csv(txt, sep="\t", low_memory=False)
                df.insert(0, "genome_set", group)
                by_module.setdefault(txt.name, []).append(df)
        n_done += len(batch)
        print(f"  kleborate {group}: {n_done}/{len(genomes)}", flush=True)

    for mod, frames in by_module.items():
        stem = mod[:-4] if mod.endswith(".txt") else mod
        pd.concat(frames, ignore_index=True).to_csv(kdir / f"{group}__{stem}.txt", sep="\t", index=False)
    if by_module:
        done.write_text("ok\n")
    return {
        "group": group,
        "tool": "kleborate",
        "status": "ok" if by_module else "failed",
        "n": len(genomes),
        "modules": ";".join(sorted(by_module)),
    }


# ─── ISESCAN ──────────────────────────────────────────────────────────────────


def _isescan_one(job: tuple[str, str, Path, Path, int]) -> dict:
    """Run ISEScan on a single genome (decompress → isescan → keep tree)."""
    group, key, gz, group_out, threads = job
    dest = group_out / key
    done = dest / ".isescan.done"
    if done.exists():
        return {"group": group, "key": key, "tool": "isescan", "status": "skipped_exists"}
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ise_") as td:
        fa = Path(td) / f"{key}.fa"
        _gunzip(gz, fa)
        cmd = ["isescan.py", "--seqfile", str(fa), "--output", str(dest), "--nthread", str(threads)]
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"group": group, "key": key, "tool": "isescan", "status": "failed", "err": r.stderr[-200:]}
    done.write_text("ok\n")
    return {"group": group, "key": key, "tool": "isescan", "status": "ok"}


def run_isescan(genomes: list[tuple[str, Path]], out_dir: Path, group: str, workers: int, threads: int) -> list[dict]:
    """Run ISEScan per genome (pooled) and concat the per-genome TSVs."""
    group_out = out_dir / "isescan" / group
    group_out.mkdir(parents=True, exist_ok=True)
    jobs = [(group, key, gz, group_out, threads) for key, gz in genomes]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_isescan_one, j) for j in jobs]
        for n, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if n % 50 == 0:
                ok = sum(1 for x in results if x["status"] in ("ok", "skipped_exists"))
                print(f"  isescan {group}: {n}/{len(jobs)} (ok+skip {ok})", flush=True)

    frames = []
    for key, _ in genomes:
        for tsv in (group_out / key).rglob("*.tsv"):
            try:
                df = pd.read_csv(tsv, sep="\t", low_memory=False)
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
                continue
            df.insert(0, "genome_set", group)
            df.insert(1, "genome_key", key)
            frames.append(df)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(out_dir / "isescan" / f"{group}_isescan.tsv", sep="\t", index=False)
    return results


def main(argv: list[str] | None = None) -> int:
    """Parse args, run the requested tools over the requested sets."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--groups", default="sr,gca,gcf")
    p.add_argument("--tools", default="kleborate,isescan")
    p.add_argument("--workers", type=int, default=4, help="parallel ISEScan genomes")
    p.add_argument("--threads", type=int, default=2, help="threads per ISEScan job")
    p.add_argument("--chunk", type=int, default=200, help="genomes per Kleborate call")
    p.add_argument("--limit", type=int, default=None, help="cap genomes/set (smoke-test)")
    args = p.parse_args(argv)

    out_dir = args.out_dir or args.data_dir / "annotations"
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]

    manifest: list[dict] = []
    for group in groups:
        genomes = discover(args.data_dir, group)
        if args.limit:
            genomes = genomes[: args.limit]
        print(f"\n=== {group}: {len(genomes)} genomes ===", flush=True)
        if not genomes:
            continue
        if "kleborate" in tools:
            manifest.append(run_kleborate(genomes, out_dir, group, args.chunk))
        if "isescan" in tools:
            manifest.extend(run_isescan(genomes, out_dir, group, args.workers, args.threads))

    mdf = pd.DataFrame(manifest)
    mpath = out_dir / "annotation_manifest.tsv"
    mdf.to_csv(mpath, sep="\t", index=False)
    print(f"\nManifest → {mpath}", flush=True)
    if len(mdf):
        print(mdf["status"].value_counts().to_dict(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
