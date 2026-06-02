"""Backfill GFF annotations for the LRA staging set.

Every LRA row in ``metadata_v2`` ships an assembly (``lr_assembly_file``), but
many have no GFF on disk: their genome came from the is_refseq metadata (FASTA
already on ``seb/``), so it never passed through
``download_related_lr_complete_genomes`` — and that downloader skips any
accession whose FASTA already exists, so it never fetched their GFF either.

For each LRA row lacking a GFF in ``related_lr/gff`` (matched by bare accession
on ``lra_gcf`` / ``lra_gca`` / the assembly stem), download the annotation-only
zip for its bare accession (``lra_gcf`` preferred — RefSeq is reliably
annotated — else ``lra_gca``) from the NCBI Datasets v2 endpoint and write
``related_lr/gff/<bare_acc>.gff``, which ``stage_lra_extras_for_tf`` then picks
up. GFF-only requests avoid re-pulling the genome FASTAs.

Reuses the rate limiter, API-key headers, download endpoint and retry budget
from ``download_related_lr_complete_genomes``.

Run on HPC from ~/workspace/BacHGT:
    uv run python -m bac_data.lr_data.download_lra_gffs [--workers N] [--limit N]
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from bac_data.lr_data.download_related_lr_complete_genomes import (
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    NCBI_DOWNLOAD,
    RateLimiter,
)
from bac_data.lr_data.norway_cohort_audit import ncbi_headers

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david")
METADATA_V2 = DATA_ROOT / "final" / "metadata_v2_all_samples_and_columns.tsv"
GFF_DIR = DATA_ROOT / "raw" / "related_lr" / "gff"

ASM_SUFFIXES = (".fna.gz", ".fna", ".fasta.gz", ".fasta")
_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")


def _bare(value: str) -> str:
    """Bare versioned accession (GCF_000009885.1) from an accession or stem."""
    m = _ACC_RE.match(str(value or "").strip())
    return m.group(1) if m else ""


def _asm_stem(path: str) -> str:
    """Filename stem of an assembly path, FASTA suffix stripped."""
    n = Path(str(path)).name
    for suffix in ASM_SUFFIXES:
        if n.endswith(suffix):
            return n[: -len(suffix)]
    return Path(n).stem


def needed_accessions(gff_dir: Path) -> list[str]:
    """Bare accessions whose GFF is not yet on disk (prefer GCF for RefSeq)."""
    m = pd.read_csv(METADATA_V2, sep="\t", dtype=str, low_memory=False)
    m = m[m["lr_assembly_file"].fillna("").str.strip() != ""]
    on_disk = (
        {p.name[:-4] for p in gff_dir.iterdir() if p.name.endswith(".gff")}
        if gff_dir.is_dir()
        else set()
    )
    out: dict[str, None] = {}
    for _, r in m.iterrows():
        gcf = _bare(r.get("lra_gcf"))
        gca = _bare(r.get("lra_gca"))
        stem = _bare(_asm_stem(r["lr_assembly_file"]))
        if any(a and a in on_disk for a in (stem, gcf, gca)):
            continue
        target = gcf or gca or stem
        if target:
            out.setdefault(target, None)
    return list(out)


def _fetch_gff_zip(acc: str, headers: dict[str, str], limiter: RateLimiter) -> bytes | None:
    """Stream one accession's annotation-only zip; return its bytes or None."""
    url = NCBI_DOWNLOAD.format(acc)
    params = {"include_annotation_type": ["GENOME_GFF"]}
    for attempt in range(DEFAULT_RETRIES):
        limiter.wait()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT, stream=True)
            if r.status_code == 200:
                # Stream inside the try: a mid-response drop raises
                # ChunkedEncodingError (a RequestException) — retry, don't crash.
                buf = io.BytesIO()
                for chunk in r.iter_content(chunk_size=1 << 20):
                    buf.write(chunk)
                return buf.getvalue()
        except requests.RequestException as exc:
            print(f"  WARN {acc} attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * (attempt + 1))
            continue
        print(f"  WARN {acc} status={r.status_code} body={r.text[:160]!r}", file=sys.stderr, flush=True)
        time.sleep(2 * (attempt + 1))
    return None


def _extract_gff(acc: str, zbytes: bytes, gff_dir: Path) -> bool:
    """Write the genomic GFF out of the dataset zip; return whether one was found."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
    except zipfile.BadZipFile:
        return False
    for name in zf.namelist():
        if "/data/" in name and (name.endswith(".gff") or name.endswith(".gff3")):
            with zf.open(name) as fh, open(gff_dir / f"{acc}.gff", "wb") as out:
                out.writelines(fh)
            return True
    return False


def _one(acc: str, headers: dict[str, str], limiter: RateLimiter, gff_dir: Path) -> dict:
    """Download + extract one accession's GFF; skip if already present."""
    dst = gff_dir / f"{acc}.gff"
    if dst.exists() and dst.stat().st_size > 0:
        return {"accession": acc, "status": "skipped_exists", "gff": True}
    zb = _fetch_gff_zip(acc, headers, limiter)
    if zb is None:
        return {"accession": acc, "status": "fetch_failed", "gff": False}
    ok = _extract_gff(acc, zb, gff_dir)
    return {"accession": acc, "status": "ok" if ok else "no_gff_in_zip", "gff": ok}


def main(argv: list[str] | None = None) -> int:
    """Backfill GFFs for every LRA accession missing one; write manifest+summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gff-dir", type=Path, default=GFF_DIR)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None, help="cap accessions (smoke-test)")
    parser.add_argument(
        "--max-rounds", type=int, default=4,
        help="Convergence loop: re-queue any accession whose GFF isn't on disk after the "
             "round; stop early when all present or a round makes zero progress.",
    )
    args = parser.parse_args(argv)
    args.gff_dir.mkdir(parents=True, exist_ok=True)

    headers, sleep_s = ncbi_headers()
    print(f"NCBI auth: {'NCBI_API_KEY set (10 req/s)' if headers else 'anon (3 req/s)'}", flush=True)
    accs = needed_accessions(args.gff_dir)
    if args.limit:
        accs = accs[: args.limit]
    print(f"accessions needing GFF: {len(accs)}", flush=True)

    limiter = RateLimiter(sleep_s)
    results: list[dict] = []
    pending = list(accs)
    for round_idx in range(1, args.max_rounds + 1):
        pending = [a for a in pending if not (args.gff_dir / f"{a}.gff").exists()]
        if not pending:
            print(f"[round {round_idx}] all GFFs present — done", flush=True)
            break
        print(f"[round {round_idx}/{args.max_rounds}] fetching {len(pending)}", flush=True)
        round_results: list[dict] = []
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_one, a, headers, limiter, args.gff_dir) for a in pending]
            for fut in as_completed(futs):
                round_results.append(fut.result())
                done += 1
                if done % 200 == 0:
                    ok = sum(1 for r in round_results if r["gff"])
                    print(f"  ... {done}/{len(pending)} done; gff ok: {ok}", flush=True)
        results.extend(round_results)
        still = [a for a in pending if not (args.gff_dir / f"{a}.gff").exists()]
        progress = len(pending) - len(still)
        print(f"[round {round_idx}] +{progress} new; {len(still)} still missing", flush=True)
        if progress == 0:
            print(
                f"[round {round_idx}] zero progress — remaining {len(still)} have no GFF at "
                f"NCBI (unannotated GenBank submissions); stopping",
                flush=True,
            )
            break
        pending = still

    res = pd.DataFrame(results)
    manifest = args.gff_dir.parent / "download_lra_gffs_manifest.tsv"
    res.to_csv(manifest, sep="\t", index=False)
    have = sum(1 for a in accs if (args.gff_dir / f"{a}.gff").exists())
    print("\n=== summary ===", flush=True)
    print(f"Accessions requested : {len(accs)}", flush=True)
    print(f"  GFFs on disk now   : {have}", flush=True)
    print(f"  still missing      : {len(accs) - have}", flush=True)
    print(f"\nManifest → {manifest}", flush=True)
    print(f"GFFs     → {args.gff_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
