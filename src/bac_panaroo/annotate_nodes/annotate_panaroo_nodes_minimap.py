"""Annotate Panaroo cluster representatives with Kleborate virulence + AMR hits.

For one Panaroo run (lineage, e.g. ``SL39``), take each cluster's
representative DNA sequence from ``pan_genome_reference.fa`` and
``minimap2``-align it against the vendored Kleborate references at
:data:`bac_kleborate.refs.paths.KLEB_VIRULENCE_INPUTS_DIR` and
:data:`bac_kleborate.refs.paths.KLEB_AMR_INPUTS_DIR`. Emit per-cluster
``virulence_hits``, ``amr_hits`` and ``amr_classes`` columns into
``<panaroo_root>/<lineage>/<lineage>_panaroo_nodes_annotate_kleborate.tsv``.

Clusters whose Panaroo run did not produce a ``pan_genome_reference.fa``
representative are **not** silently rescued from per-genome GFF/FNA — they
are counted and listed in ``<lineage>_missing_node_seqs.tsv``. Surfacing the
gap is intentional: missing reps point at an upstream Panaroo-config issue
to fix rather than something to paper over.

By design simple and fast:

- minimap2 ``-cx asm10 --secondary=no`` (assembly-to-assembly, conservative
  chaining; we filter downstream by identity + query coverage).
- Identity defined as ``matches / alignment_length`` from PAF cols 10/11.
- Query coverage as ``(qend - qstart) / qlen`` from PAF cols 2/3/4.
- Per Panaroo cluster, hit sets are deduplicated by ``cluster_label:gene``
  (virulence) or by ``gene`` / ``drug_class`` (AMR); allele-level granularity
  is dropped at the cluster row — drug calls don't need it.

Run via::

    PATH=/home/dca36/.conda/envs/kleborate/bin:$PATH \
        uv run python -m bac_panaroo.annotate_nodes.annotate_panaroo_nodes_minimap \
        --panaroo-root <ROOT> --lineage SL39
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bac_kleborate.refs.paths import KLEB_AMR_INPUTS_DIR, KLEB_VIRULENCE_INPUTS_DIR

logger = logging.getLogger("annotate_panaroo_nodes_minimap")

# Mirrors bac_ariba.pp.build_ariba_ref.DB_REGISTRY["kleb_virulence"]["modules"]
# — kept inline so this module doesn't have to import from the pixi-only
# bac_ariba subpackage. Order doesn't matter; this is only used to label the
# concatenated query FASTA's headers.
_VIRULENCE_MODULES = (
    ("klebsiella__ybst", "ybt"),
    ("klebsiella__cbst", "clb"),
    ("klebsiella__abst", "iuc"),
    ("klebsiella__smst", "iro"),
    ("klebsiella__rmst", "rmp"),
    ("klebsiella__rmpa2", "rmp"),
)

# Kleborate CARD FASTA filename glob inside KLEB_AMR_INPUTS_DIR (versioned).
_CARD_FASTA_GLOB = "CARD_v*.fasta"

# Strip Kleborate's allele-number suffix, e.g. ``iucA_3`` → ``iucA``.
_ALLELE_SUFFIX_RE = re.compile(r"_\d+$")

# Panaroo GPA columns that aren't genome samples.
_GPA_META_COLS = {"Gene", "Non-unique Gene name", "Annotation"}


def _gene_basename(seq_name: str) -> str:
    """Strip a trailing ``_<digits>`` allele suffix."""
    return _ALLELE_SUFFIX_RE.sub("", seq_name)


def _build_virulence_query(out_fasta: Path) -> int:
    """Concatenate vendored virulence allele FASTAs into a single query.

    Rewrites each header from ``>iucA_3`` to ``>iuc:iucA_3`` so the source
    Kleborate cluster label (ybt/clb/iuc/iro/rmp) round-trips into PAF and
    per-cluster hit dedup works without a side table. Returns N sequences.
    """
    n = 0
    with out_fasta.open("w") as out:
        for mod, cluster in _VIRULENCE_MODULES:
            mod_dir = KLEB_VIRULENCE_INPUTS_DIR / mod
            for fasta in sorted(mod_dir.glob("*.fasta")):
                with fasta.open() as fh:
                    for line in fh:
                        if line.startswith(">"):
                            name = line[1:].split()[0]
                            out.write(f">{cluster}:{name}\n")
                            n += 1
                        else:
                            out.write(line)
    return n


def _read_panaroo_clusters(run_dir: Path) -> list[str]:
    """Cluster names from ``gene_presence_absence.csv`` (Gene column)."""
    with (run_dir / "gene_presence_absence.csv").open(newline="") as fh:
        reader = csv.DictReader(fh)
        return [row["Gene"] for row in reader]


def _read_panref_clusters(run_dir: Path) -> set[str]:
    """Cluster names present in ``pan_genome_reference.fa`` (>cluster header)."""
    out: set[str] = set()
    with (run_dir / "pan_genome_reference.fa").open() as fh:
        for line in fh:
            if line.startswith(">"):
                out.add(line[1:].split()[0])
    return out


def _run_minimap2(
    binary: str, target: Path, query: Path, threads: int, out_paf: Path
) -> None:
    """Run ``minimap2 -cx asm10 --secondary=no`` and write PAF to ``out_paf``."""
    cmd = [
        binary, "-cx", "asm10", "--secondary=no",
        "-t", str(threads),
        str(target), str(query),
    ]
    logger.info("minimap2: %s", " ".join(cmd))
    with out_paf.open("w") as fh:
        res = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, check=False)
    if res.returncode != 0:
        sys.stderr.write(res.stderr.decode("utf-8", errors="replace"))
        sys.exit(f"minimap2 failed (rc={res.returncode})")


def _parse_paf_hits(
    paf: Path, min_ident: float, min_cov: float
) -> list[tuple[str, str]]:
    """Read a PAF and return ``(target=cluster, query=hit_name)`` pairs passing thresholds."""
    hits: list[tuple[str, str]] = []
    with paf.open() as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 11:
                continue
            qname = parts[0]
            qlen = int(parts[1])
            qstart, qend = int(parts[2]), int(parts[3])
            tname = parts[5]
            matches = int(parts[9])
            aln_len = int(parts[10])
            if aln_len == 0 or qlen == 0:
                continue
            ident = matches / aln_len
            cov = (qend - qstart) / qlen
            if ident >= min_ident and cov >= min_cov:
                hits.append((tname, qname))
    return hits


def _split_amr_header(header: str) -> tuple[str, str] | None:
    """Parse a Kleborate CARD header into ``(drug_class, allele)``.

    Headers look like ``1__AAC(2')_AGly__aac(2')-Ia__1`` — clusterid, then
    ``<gene_family>_<drug_class>``, then allele, then seq_id. Drug class is
    the trailing underscore-token of field 2.
    """
    parts = header.split("__")
    if len(parts) < 3:
        return None
    drug_class = parts[1].rsplit("_", 1)[-1]
    allele = parts[2]
    return drug_class, allele


def _aggregate_virulence(hits: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Per-cluster set of ``cluster_label:gene`` strings (e.g. ``iuc:iucA``)."""
    out: dict[str, set[str]] = {}
    for cluster, qname in hits:
        # qname format: "<cluster_label>:<allele_name>" (rewritten on concat).
        if ":" not in qname:
            continue
        cluster_label, allele = qname.split(":", 1)
        out.setdefault(cluster, set()).add(f"{cluster_label}:{_gene_basename(allele)}")
    return out


def _aggregate_amr(
    hits: list[tuple[str, str]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Per-cluster sets of (allele, drug_class) from CARD-format hits."""
    alleles: dict[str, set[str]] = {}
    classes: dict[str, set[str]] = {}
    for cluster, qname in hits:
        parsed = _split_amr_header(qname)
        if parsed is None:
            continue
        drug_class, allele = parsed
        alleles.setdefault(cluster, set()).add(allele)
        classes.setdefault(cluster, set()).add(drug_class)
    return alleles, classes


def _semi(values: set[str]) -> str:
    """Sorted, ``;``-joined string for a TSV cell (empty if no values)."""
    return ";".join(sorted(values)) if values else ""


def run(
    panaroo_root: Path,
    lineage: str,
    *,
    min_ident: float,
    min_cov: float,
    threads: int,
    minimap2: str,
) -> None:
    """Execute the annotation for one Panaroo run."""
    run_dir = panaroo_root / lineage
    target = run_dir / "pan_genome_reference.fa"
    gpa = run_dir / "gene_presence_absence.csv"
    if not target.exists() or not gpa.exists():
        sys.exit(f"missing required files under {run_dir}: pan_genome_reference.fa or gene_presence_absence.csv")
    if shutil.which(minimap2) is None and not Path(minimap2).is_file():
        sys.exit(f"minimap2 not found: {minimap2!r}; ensure it's on PATH or pass --minimap2 <bin>")

    out_tsv = run_dir / f"{lineage}_panaroo_nodes_annotate_kleborate.tsv"
    out_missing = run_dir / f"{lineage}_missing_node_seqs.tsv"
    out_log = run_dir / f"{lineage}_panaroo_nodes_annotate_kleborate.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(out_log, mode="w"), logging.StreamHandler()],
    )
    logger.info(
        "panaroo_root=%s lineage=%s min_ident=%.2f min_cov=%.2f threads=%d",
        panaroo_root, lineage, min_ident, min_cov, threads,
    )

    clusters_all = _read_panaroo_clusters(run_dir)
    clusters_with_rep = _read_panref_clusters(run_dir)
    missing = [c for c in clusters_all if c not in clusters_with_rep]
    out_missing.write_text("cluster\n" + "\n".join(missing) + ("\n" if missing else ""))
    logger.info(
        "panaroo clusters: total=%d with_rep=%d missing=%d → %s",
        len(clusters_all), len(clusters_with_rep), len(missing), out_missing.name,
    )

    card_fastas = sorted(KLEB_AMR_INPUTS_DIR.glob(_CARD_FASTA_GLOB))
    if not card_fastas:
        sys.exit(f"no CARD FASTA matching {_CARD_FASTA_GLOB!r} under {KLEB_AMR_INPUTS_DIR}")
    card_fasta = card_fastas[0]

    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="panaroo_minimap_") as tmpdir:
        tmp = Path(tmpdir)
        vir_query = tmp / "kleb_virulence.fa"
        n_vir = _build_virulence_query(vir_query)
        logger.info("built virulence query (%d seqs): %s", n_vir, vir_query)

        vir_paf = tmp / "vir.paf"
        _run_minimap2(minimap2, target, vir_query, threads, vir_paf)
        vir_hits = _parse_paf_hits(vir_paf, min_ident, min_cov)
        logger.info("virulence hits (filtered): %d", len(vir_hits))

        amr_paf = tmp / "amr.paf"
        _run_minimap2(minimap2, target, card_fasta, threads, amr_paf)
        amr_hits = _parse_paf_hits(amr_paf, min_ident, min_cov)
        logger.info("amr hits (filtered): %d", len(amr_hits))

    vir_by_cluster = _aggregate_virulence(vir_hits)
    amr_alleles_by_cluster, amr_classes_by_cluster = _aggregate_amr(amr_hits)

    with out_tsv.open("w") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["cluster", "virulence_hits", "amr_hits", "amr_classes"])
        for cluster in clusters_all:
            w.writerow([
                cluster,
                _semi(vir_by_cluster.get(cluster, set())),
                _semi(amr_alleles_by_cluster.get(cluster, set())),
                _semi(amr_classes_by_cluster.get(cluster, set())),
            ])

    dt = time.monotonic() - t0
    n_annotated = sum(
        1 for c in clusters_all
        if vir_by_cluster.get(c) or amr_alleles_by_cluster.get(c)
    )
    logger.info(
        "wrote %s — %d annotated / %d clusters in %.1fs",
        out_tsv.name, n_annotated, len(clusters_all), dt,
    )


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panaroo-root", type=Path, required=True,
                    help="Directory holding per-lineage Panaroo run subdirs.")
    ap.add_argument("--lineage", required=True,
                    help="Lineage / Panaroo-run subdir name (e.g. SL39).")
    ap.add_argument("--min-ident", type=float, default=0.80,
                    help="Minimum alignment identity (matches/aln_len). Default 0.80.")
    ap.add_argument("--min-cov", type=float, default=0.80,
                    help="Minimum query coverage ((qend-qstart)/qlen). Default 0.80.")
    ap.add_argument("--threads", type=int, default=4,
                    help="minimap2 threads (-t). Default 4.")
    ap.add_argument("--minimap2", default="minimap2",
                    help="minimap2 binary (PATH or explicit). Default 'minimap2'.")
    args = ap.parse_args()
    run(
        args.panaroo_root, args.lineage,
        min_ident=args.min_ident, min_cov=args.min_cov,
        threads=args.threads, minimap2=args.minimap2,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
