"""Map ISEScan IS-element coordinates to per-genome gene context.

Run on the HPC login node before shutdown. Emits one gzipped TSV joining each
ISEScan IS element to the gene it overlaps (if any) plus the nearest flanking
genes, using the per-genome annotation GFFs (Bakta for Klebsiella, NCBI for
RefSeq). Offline, join ``hit_locus_tag`` to a Panaroo
``gene_presence_absence.csv`` cell to recover pangenome cluster / annotation /
core-accessory status.
"""

from __future__ import annotations

import argparse
import csv
import glob
import gzip
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

GENE_FEATURES = {"CDS", "tRNA", "rRNA", "tmRNA", "ncRNA"}

OUT_COLUMNS = [
    "sample", "contig", "is_family", "is_cluster", "is_start", "is_end", "is_len",
    "relationship", "n_overlapping", "hit_locus_tag", "hit_gene", "hit_product",
    "upstream_locus_tag", "upstream_product", "upstream_distance_bp",
    "downstream_locus_tag", "downstream_product", "downstream_distance_bp",
]


def _attr(attrs: str, key: str) -> str:
    """Return the value of GFF attribute ``key`` (col 9), or ``""``."""
    needle = key + "="
    for field in attrs.split(";"):
        if field.startswith(needle):
            return field[len(needle):]
    return ""


def _load_lookup(path: str) -> dict[str, str]:
    """Load a ``Sample<TAB>path`` lookup TSV (1 header line) into a dict."""
    out: dict[str, str] = {}
    with open(path) as fh:
        next(fh, None)
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0]:
                out[parts[0]] = parts[1]
    return out


def _parse_gff(gff_path: str) -> dict[str, list[tuple]]:
    """Return ``{contig: [(start, end, strand, locus, gene, product), ...]}`` sorted by start."""
    genes: dict[str, list[tuple]] = {}
    opener = gzip.open if gff_path.endswith(".gz") else open
    with opener(gff_path, "rt") as fh:  # type: ignore[arg-type]
        for line in fh:
            if not line or line[0] == "#":
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 9 or c[2] not in GENE_FEATURES:
                continue
            try:
                start, end = int(c[3]), int(c[4])
            except ValueError:
                continue
            a = c[8]
            locus = _attr(a, "locus_tag") or _attr(a, "ID")
            genes.setdefault(c[0], []).append(
                (start, end, c[6], locus, _attr(a, "gene"), _attr(a, "product"))
            )
    for v in genes.values():
        v.sort()
    return genes


def _context(goc: list[tuple], s: int, e: int):
    """Return (overlaps, upstream_gene, downstream_gene) for IS interval [s, e]."""
    overlaps: list[tuple] = []
    up = None
    down = None
    for g in goc:
        gs, ge = g[0], g[1]
        if ge >= s and gs <= e:
            overlaps.append(g)
        elif ge < s:
            if up is None or ge > up[1]:
                up = g
        elif gs > e:
            if down is None or gs < down[0]:
                down = g
    return overlaps, up, down


def _process(sample: str, is_path: str, gff_path: str):
    """Return (sample, list_of_row_lists, error_str)."""
    try:
        genes = _parse_gff(gff_path)
    except Exception as exc:  # noqa: BLE001
        return sample, None, f"gff_error:{exc}"
    rows: list[list] = []
    try:
        with open(is_path, newline="") as fh:
            for r in csv.DictReader(fh):
                contig = r.get("seqID", "")
                try:
                    s = int(r["start1"])
                    e = int(r.get("end2") or r["end1"])
                except (KeyError, ValueError, TypeError):
                    continue
                ov, up, dn = _context(genes.get(contig, []), s, e)
                if ov:
                    rel = "within"
                    hit_lt, hit_gene, hit_prod = ov[0][3], ov[0][4], ov[0][5]
                else:
                    rel = "intergenic"
                    hit_lt = hit_gene = hit_prod = ""
                rows.append([
                    sample, contig, r.get("family", ""), r.get("cluster", ""),
                    s, e, r.get("isLen", ""), rel, len(ov), hit_lt, hit_gene, hit_prod,
                    up[3] if up else "", up[5] if up else "", (s - up[1]) if up else "",
                    dn[3] if dn else "", dn[5] if dn else "", (dn[0] - e) if dn else "",
                ])
    except Exception as exc:  # noqa: BLE001
        return sample, None, f"is_error:{exc}"
    return sample, rows, ""


def _resolve_gff(sample: str, kleb: dict, ncbi: dict, ncbi_dir: str) -> str | None:
    """Resolve a sample to its GFF path (Bakta first, then NCBI exact, then GCA glob)."""
    if sample in kleb:
        return kleb[sample]
    if sample in ncbi:
        return ncbi[sample]
    if sample.startswith("GCA_"):
        hits = sorted(glob.glob(os.path.join(ncbi_dir, sample + "*.gff.gz")))
        if hits:
            return hits[0]
    return None


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    base = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw"
    ap.add_argument("--isescan-lookup", default=f"{base}/david/raw/isescan_csv.tsv")
    ap.add_argument("--kleb-lookup", default=f"{base}/david/raw/klebsiella_gff.tsv")
    ap.add_argument("--ncbi-lookup", default=f"{base}/david/raw/ncbi_gff.tsv")
    ap.add_argument("--ncbi-dir", default=f"{base}/david/raw/ncbi_gff3")
    ap.add_argument(
        "--out",
        default=f"{base}/david/processed/isescan_analysis/is_gene_context.tsv.gz",
    )
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 8)
    ap.add_argument("--limit", type=int, default=0, help="smoke-test: cap N samples")
    args = ap.parse_args()

    isescan = _load_lookup(args.isescan_lookup)
    kleb = _load_lookup(args.kleb_lookup)
    ncbi = _load_lookup(args.ncbi_lookup)

    tasks: list[tuple[str, str, str]] = []
    unmatched: list[str] = []
    for sample, is_path in isescan.items():
        gff = _resolve_gff(sample, kleb, ncbi, args.ncbi_dir)
        if gff is None:
            unmatched.append(sample)
            continue
        tasks.append((sample, is_path, gff))
    if args.limit:
        tasks = tasks[: args.limit]

    print(
        f"samples={len(isescan)} matched={len(tasks)} unmatched={len(unmatched)} "
        f"workers={args.workers}",
        flush=True,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    log_path = args.out + ".log"

    t0 = time.time()
    done = 0
    failed = 0
    with gzip.open(args.out, "wt", newline="") as out_fh, open(log_path, "w") as log_fh:
        w = csv.writer(out_fh, delimiter="\t")
        w.writerow(OUT_COLUMNS)
        for s in unmatched:
            log_fh.write(f"{s}\tunmatched_no_gff\n")
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_process, *t) for t in tasks]
            for fut in as_completed(futs):
                sample, rows, err = fut.result()
                done += 1
                if err:
                    failed += 1
                    log_fh.write(f"{sample}\t{err}\n")
                elif rows:
                    w.writerows(rows)
                if done % 2000 == 0:
                    print(
                        f"{done}/{len(tasks)} done, {failed} failed, "
                        f"{time.time() - t0:.0f}s",
                        flush=True,
                    )
    print(
        f"DONE matched={len(tasks)} failed={failed} "
        f"elapsed={time.time() - t0:.0f}s -> {args.out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
