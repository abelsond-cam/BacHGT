#!/usr/bin/env python3
"""Download the related-LR Complete-Genome GCAs (+ paired RefSeq GCFs).

download_related_lr_complete_genomes.py
---------------------------------------
Consumes ``related_lr_complete_genomes.tsv`` (the actionable list emitted
by ``related_lr_complete_assembly_audit.py``) and downloads, for every
row, the GenBank **GCA** genome+GFF and — when one exists — the paired
RefSeq **GCF** genome+GFF.

No ``datasets`` CLI dependency: this uses the NCBI Datasets **v2 REST
download endpoint** directly (pure ``requests``, like the rest of
``download_data/``), so it runs anywhere, including a laptop::

    https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/<ACC>/download
        ?include_annotation_type=GENOME_FASTA&include_annotation_type=GENOME_GFF

Each accession's zip is streamed to a temp file, the genomic FASTA is
re-gzipped to ``<out>/assemblies/<ACC>.fna.gz`` and the GFF (when the
submitter provided one) to ``<out>/gff/<ACC>.gff`` — the same layout
``norway_tables1_integrate`` writes. Already-present accessions are
skipped, so the run is resumable.

Set ``NCBI_API_KEY`` to raise the NCBI rate limit from 3 to 10 req/s.

Usage
─────
    uv run python src/bac_data/download_related_lr_complete_genomes.py
        [--cg-tsv PATH]    # default: <out-dir>/related_lr_complete_genomes.tsv
        [--out-dir PATH]   # default: <DATA_ROOT>/raw/related_lr
        [--which both]     # both | gca | gcf
        [--workers N]      # default 6
        [--limit N]        # cap accessions (smoke-test)

Outputs
  <out-dir>/assemblies/<ACC>.fna.gz   genomic FASTA (gzipped)
  <out-dir>/gff/<ACC>.gff             genomic GFF (only if submitter gave one)
  <out-dir>/download_related_lr_complete_genomes_manifest.tsv
"""

from __future__ import annotations

import argparse
import gzip
import io
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from bac_data.lr_data.norway_cohort_audit import ncbi_headers

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david")
DEFAULT_OUT_DIR = DATA_ROOT / "raw" / "related_lr"
CG_TSV_NAME = "related_lr_complete_genomes.tsv"

NCBI_DOWNLOAD = "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{}/download"
DEFAULT_TIMEOUT = 300
DEFAULT_RETRIES = 4


class RateLimiter:
    """Minimum-interval gate keeping pooled workers under the NCBI budget.

    One ``wait()`` == one outbound request; thread-safe.
    """

    def __init__(self, min_interval: float) -> None:
        self._min = min_interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        """Block until the next request is allowed."""
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next - now
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._next = max(now, self._next) + self._min


def _accessions(cg: pd.DataFrame, which: str) -> list[tuple[str, str, str]]:
    """Return (accession, kind, Sample) for every accession to fetch."""
    out: list[tuple[str, str, str]] = []
    for _, r in cg.iterrows():
        sample = str(r["Sample"])
        if which in ("both", "gca"):
            gca = str(r["gca"])
            if gca.startswith("GCA_"):
                out.append((gca, "gca", sample))
        if which in ("both", "gcf"):
            gcf = str(r["gcf"])
            if gcf.startswith("GCF_"):
                out.append((gcf, "gcf", sample))
    return out


def _fetch_zip(acc: str, headers: dict[str, str], limiter: RateLimiter) -> bytes | None:
    """Stream one accession's genome+GFF zip; return its bytes or None."""
    url = NCBI_DOWNLOAD.format(acc)
    params = {
        "include_annotation_type": ["GENOME_FASTA", "GENOME_GFF"],
    }
    for attempt in range(DEFAULT_RETRIES):
        limiter.wait()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT, stream=True)
        except requests.RequestException as exc:
            print(f"  WARN {acc} attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            buf = io.BytesIO()
            for chunk in r.iter_content(chunk_size=1 << 20):
                buf.write(chunk)
            return buf.getvalue()
        if r.status_code in (429, 500, 502, 503, 504):
            print(
                f"  WARN {acc} attempt={attempt + 1} status={r.status_code}; retrying",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(2 * (attempt + 1))
            continue
        print(
            f"  WARN {acc} status={r.status_code} body={r.text[:160]!r}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(2 * (attempt + 1))
    return None


def _extract(acc: str, zbytes: bytes, asm_dir: Path, gff_dir: Path) -> tuple[bool, bool]:
    """Pull the genomic FASTA + GFF out of the dataset zip.

    Returns ``(genome_ok, gff_ok)``. GFF is absent when the submitter
    deposited no annotation — that is expected, not an error.
    """
    genome_ok = gff_ok = False
    try:
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
    except zipfile.BadZipFile:
        return False, False
    for name in zf.namelist():
        if "/data/" not in name:
            continue
        if name.endswith(".fna"):
            with zf.open(name) as fh, gzip.open(asm_dir / f"{acc}.fna.gz", "wb") as out:
                out.writelines(fh)
            genome_ok = True
        elif name.endswith(".gff") or name.endswith(".gff3"):
            with zf.open(name) as fh, open(gff_dir / f"{acc}.gff", "wb") as out:
                out.writelines(fh)
            gff_ok = True
    return genome_ok, gff_ok


def _one(
    job: tuple[str, str, str],
    headers: dict[str, str],
    limiter: RateLimiter,
    asm_dir: Path,
    gff_dir: Path,
) -> dict:
    """Download + extract one accession; skip if its FASTA already exists."""
    acc, kind, sample = job
    fna = asm_dir / f"{acc}.fna.gz"
    if fna.exists() and fna.stat().st_size > 0:
        return {
            "accession": acc,
            "kind": kind,
            "Sample": sample,
            "status": "skipped_exists",
            "genome": True,
            "gff": (gff_dir / f"{acc}.gff").exists(),
        }
    zb = _fetch_zip(acc, headers, limiter)
    if zb is None:
        return {
            "accession": acc,
            "kind": kind,
            "Sample": sample,
            "status": "fetch_failed",
            "genome": False,
            "gff": False,
        }
    genome_ok, gff_ok = _extract(acc, zb, asm_dir, gff_dir)
    return {
        "accession": acc,
        "kind": kind,
        "Sample": sample,
        "status": "ok" if genome_ok else "no_genome_in_zip",
        "genome": genome_ok,
        "gff": gff_ok,
    }


def main(argv: list[str] | None = None) -> int:
    """Download every GCA (+ paired GCF) genome+GFF; write manifest+summary.

    Drives the pooled download from the Complete-Genome list and reports
    genomes/GFFs ok plus any failures.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cg-tsv", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--which", choices=["both", "gca", "gcf"], default="both")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None, help="cap accessions (smoke-test)")
    args = parser.parse_args(argv)

    cg_tsv = args.cg_tsv or args.out_dir / CG_TSV_NAME
    asm_dir = args.out_dir / "assemblies"
    gff_dir = args.out_dir / "gff"
    asm_dir.mkdir(parents=True, exist_ok=True)
    gff_dir.mkdir(parents=True, exist_ok=True)

    headers, sleep_s = ncbi_headers()
    print(
        f"NCBI auth: {'NCBI_API_KEY set (10 req/s)' if headers else 'anon (3 req/s)'}",
        flush=True,
    )
    cg = pd.read_csv(cg_tsv, sep="\t")
    jobs = _accessions(cg, args.which)
    if args.limit:
        jobs = jobs[: args.limit]
    n_gca = sum(1 for _, k, _ in jobs if k == "gca")
    n_gcf = sum(1 for _, k, _ in jobs if k == "gcf")
    print(
        f"Loaded {cg_tsv}  rows={len(cg)}  →  {len(jobs)} downloads (GCA={n_gca}, GCF={n_gcf}, which={args.which})",
        flush=True,
    )

    limiter = RateLimiter(sleep_s)
    results: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, j, headers, limiter, asm_dir, gff_dir) for j in jobs]
        for fut in as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 100 == 0:
                ok = sum(1 for r in results if r["genome"])
                print(f"  ... {done}/{len(jobs)} done; genomes ok: {ok}", flush=True)

    res = pd.DataFrame(results)
    manifest = args.out_dir / "download_related_lr_complete_genomes_manifest.tsv"
    res.to_csv(manifest, sep="\t", index=False)

    genome_ok = int(res["genome"].sum())
    gff_ok = int(res["gff"].sum())
    failed = res[~res["genome"]]
    print("\n=== download summary ===", flush=True)
    print(f"Accessions attempted : {len(res)}", flush=True)
    print(f"  genomes ok         : {genome_ok}", flush=True)
    print(f"  GFFs ok            : {gff_ok}", flush=True)
    print(f"  skipped (existing) : {int((res['status'] == 'skipped_exists').sum())}", flush=True)
    print(f"  no genome / failed : {len(failed)}", flush=True)
    if len(failed):
        print(
            f"  failed accessions  : {failed['accession'].head(20).tolist()}{' ...' if len(failed) > 20 else ''}",
            flush=True,
        )
    print(f"\nManifest → {manifest}", flush=True)
    print(f"Genomes  → {asm_dir}", flush=True)
    print(f"GFFs     → {gff_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
