"""Build an ARIBA reference DB from vendored allele FASTAs.

Two DBs are wired today, both sourced from Kleborate:

- ``--kleb-virulence`` — Kleborate's 5+1 virulence cluster modules (ybt, clb,
  iuc, iro, rmp, rmpa2 — rmpA2 grouped under cluster ``rmp`` but kept
  separable as ``rmp:rmpA2`` in the metadata description).
- ``--kleb-amr`` — Kleborate's KpSC AMR module (CARD-derived acquired
  resistance alleles + a Kleborate drug-class TSV); the FASTA is one big
  ``CARD_v*.fasta`` rather than the virulence per-locus FASTAs, so a separate
  metadata builder handles its headers.

Each DB's ``kind`` in ``DB_REGISTRY`` dispatches vendoring + metadata-building
to the appropriate helpers. Future DBs (``--mlst``, …) register a new kind and
helpers if their source layout differs.

Vendored source FASTAs live in the sibling ``bac_kleborate`` subpackage; only
ARIBA's build artefacts (``metadata.tsv``, ``manifest.json``,
``prepareref_out/``) land here under ``src/bac_ariba/refs/<db>/``.

Usage
-----
    pixi run -e refbuild python -m bac_ariba.pp.build_ariba_ref --kleb-virulence
    pixi run -e refbuild python -m bac_ariba.pp.build_ariba_ref --kleb-amr
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import importlib.metadata
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("build_ariba_ref")

# Per-DB spec. ``kind`` dispatches the vendoring + metadata-builder pair:
#  - ``virulence_loci`` — Kleborate's older ``klebsiella__<locus>`` modules, each
#    with per-locus allele FASTAs; vendoring pulls *.fasta + profiles.tsv from
#    each module's data/ dir, metadata.tsv is one row per FASTA header tagged
#    with the cluster label.
#  - ``amr_card`` — Kleborate's newer ``klebsiella_pneumo_complex__amr`` module,
#    a single CARD-derived ``CARD_v*.fasta`` plus class / clustering TSVs;
#    vendoring copies the whole data/ dir wholesale, metadata.tsv is parsed
#    from the CARD-formatted FASTA headers (cluster label = Kleborate drug
#    class, e.g. ``AGly``, ``Bla_Carb``).
DB_REGISTRY: dict[str, dict] = {
    "kleb_virulence": {
        "source_pkg": "kleborate",
        "kind": "virulence_loci",
        "modules": [
            ("klebsiella__ybst", "ybt"),
            ("klebsiella__cbst", "clb"),
            ("klebsiella__abst", "iuc"),
            ("klebsiella__smst", "iro"),
            ("klebsiella__rmst", "rmp"),
            ("klebsiella__rmpa2", "rmp"),
        ],
    },
    "kleb_amr": {
        "source_pkg": "kleborate",
        "kind": "amr_card",
        # Single Kleborate module — data/ dir copied wholesale (CARD FASTA,
        # CARD_AMR_clustered.csv, Kleborate_classes.csv, plus the three
        # mutational FASTAs which ARIBA prepareref ignores).
        "module": "klebsiella_pneumo_complex__amr",
        # Filename inside the module's data/ — the CARD FASTA whose headers
        # drive metadata.tsv. Glob to tolerate version bumps (CARD_v3.2.9 →
        # CARD_v3.x.y).
        "card_fasta_glob": "CARD_v*.fasta",
    },
}

# Paths:
#  - REPO_ROOT — monorepo root, used only for nice ``relative_to`` log lines.
#  - _BAC_ARIBA_ROOT — where ARIBA build artefacts land (refs/<db>/manifest.json,
#    metadata.tsv, prepareref_out/).
#  - _BAC_KLEBORATE_REFS_DIR — where the vendored source FASTAs live; canonical
#    constants are defined in :mod:`bac_kleborate.refs.paths` for uv-side
#    consumers (we recompute here because ``bac_ariba`` runs in its own pixi env
#    and cannot reliably import sibling subpackages).
REPO_ROOT = Path(__file__).resolve().parents[3]
_BAC_ARIBA_ROOT = Path(__file__).resolve().parents[1]
_BAC_KLEBORATE_REFS_DIR = REPO_ROOT / "src" / "bac_kleborate" / "refs"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_pkg_version(pkg) -> str:
    """Return the installed package version.

    Prefers ``importlib.metadata.version()`` (reads the dist-info recorded by
    the package manager — conda/pip), then falls back to ``pkg.__version__``,
    then to a ``version.py`` ``__version__`` global. The metadata path matters
    because some packages (e.g. kleborate) ship a ``version.py`` whose string
    drifts from the actual installed version.
    """
    try:
        return importlib.metadata.version(pkg.__name__)
    except importlib.metadata.PackageNotFoundError:
        pass
    if hasattr(pkg, "__version__"):
        return str(pkg.__version__)
    version_py = Path(pkg.__file__).resolve().parent / "version.py"
    if version_py.exists():
        ns: dict = {}
        exec(version_py.read_text(), ns)
        return str(ns.get("__version__", "unknown"))
    return "unknown"


def _vendor_module(src_data: Path, dest_module: Path) -> dict[str, str]:
    """Copy ``*.fasta`` and ``profiles.tsv`` from src into dest. Return {filename: sha256}."""
    dest_module.mkdir(parents=True, exist_ok=True)
    sums: dict[str, str] = {}
    for src in sorted(src_data.iterdir()):
        if src.suffix == ".fasta" or src.name == "profiles.tsv":
            dest = dest_module / src.name
            shutil.copy2(src, dest)
            sums[src.name] = _sha256(dest)
    return sums


def _read_fasta_headers(fasta: Path) -> list[str]:
    """Return sequence names (no leading ``>``) in FASTA order."""
    names: list[str] = []
    for line in fasta.read_text().splitlines():
        if line.startswith(">"):
            names.append(line[1:].split()[0])
    return names


def _gene_basename(seq_name: str) -> str:
    """Strip Kleborate's allele-number suffix: ``iucA_3`` → ``iucA``."""
    return seq_name.rsplit("_", 1)[0]


def _build_metadata(inputs_root: Path, modules: list[tuple[str, str]]) -> str:
    """Emit the ARIBA prepareref metadata TSV for ``virulence_loci``-kind DBs.

    Six tab-separated columns per row, as expected by
    ``ariba.sequence_metadata.SequenceMetadata``:

        name, gene_or_noncoding, variant_only, variant, variant_id, free_text

    Every row here: gene=1, variant_only=0, variant='.', variant_id='.',
    free_text='<cluster>:<gene>'. Five-column rows are silently rejected by
    ARIBA, leaving sequences orphaned in the FASTA.
    """
    rows: list[str] = []
    for mod, cluster in modules:
        for fasta in sorted((inputs_root / mod).glob("*.fasta")):
            for seq_name in _read_fasta_headers(fasta):
                rows.append("\t".join([seq_name, "1", "0", ".", ".", f"{cluster}:{_gene_basename(seq_name)}"]))
    return "\n".join(rows) + "\n"


def _vendor_amr_data(src_data: Path, dest_inputs: Path) -> dict[str, str]:
    """Copy the whole Kleborate AMR ``data/`` dir into ``dest_inputs``.

    The module ships one CARD FASTA, two metadata TSVs (clustering + class
    table) and three small mutational FASTAs. We carry them all so consumers
    other than ARIBA (e.g. the minimap-based Panaroo-node annotator) can join
    hits through ``CARD_AMR_clustered.csv``. Returns ``{filename: sha256}``.
    """
    dest_inputs.mkdir(parents=True, exist_ok=True)
    sums: dict[str, str] = {}
    for src in sorted(src_data.iterdir()):
        if src.is_file():
            dest = dest_inputs / src.name
            shutil.copy2(src, dest)
            sums[src.name] = _sha256(dest)
    return sums


def _build_amr_metadata(card_fasta: Path) -> str:
    """Emit the ARIBA metadata TSV for the CARD-derived Kleborate AMR DB.

    Kleborate's CARD FASTA headers follow the format
    ``<clusterid>__<gene_family>_<drug_class>__<allele>__<seq_id>`` — e.g.
    ``1__AAC(2')_AGly__aac(2')-Ia__1`` → clusterid=1, gene_family=AAC(2'),
    drug_class=AGly, allele=aac(2')-Ia, seq_id=1. We register each allele as a
    gene presence/absence target (variant_only=0); the ARIBA cluster label is
    the Kleborate drug class (so all aminoglycoside alleles share cluster
    ``AGly``), and ``free_text`` carries ``<class>:<allele>``.

    Drug-class labels are the Kleborate ``class``/``bla_class`` taxonomy from
    ``Kleborate_classes.csv``: ``AGly``, ``Bla``, ``Bla_Carb``, ``Bla_ESBL``,
    ``Bla_ESBL_inhR``, ``Bla_chr``, ``Bla_inhR``, ``Col``, ``Fcyn``, ``Flq``,
    ``Gly``, ``MLS``, ``Phe``, ``Rif``, ``Sul``, ``Tet``, ``Tgc``, ``Tmt``.
    """
    rows: list[str] = []
    skipped = 0
    for line in card_fasta.read_text().splitlines():
        if not line.startswith(">"):
            continue
        header = line[1:].split()[0]
        parts = header.split("__")
        if len(parts) < 3:
            skipped += 1
            continue
        # parts[1] = "<gene_family>_<class>"; drug class is the trailing
        # underscore-delimited token (handles families with embedded
        # parentheses or hyphens, e.g. "AAC(2')_AGly", "23S_rRNA_MLS").
        drug_class = parts[1].rsplit("_", 1)[-1]
        allele = parts[2]
        rows.append("\t".join([header, "1", "0", ".", ".", f"{drug_class}:{allele}"]))
    if skipped:
        logger.warning("AMR metadata: skipped %d FASTA headers with unexpected format", skipped)
    return "\n".join(rows) + "\n"


def _check_apptainer_on_path() -> None:
    if shutil.which("apptainer") is None and shutil.which("singularity") is None:
        logger.error("Neither `apptainer` nor `singularity` on PATH. ariba runs in a container.")
        sys.exit(1)


def build(db_name: str, *, ariba_sif: Path, force: bool = False, threads: int = 1) -> None:
    """Vendor source FASTAs, write metadata + manifest, run ``ariba prepareref``."""
    spec = DB_REGISTRY[db_name]
    # Inputs (vendored source FASTAs) live in the bac_kleborate subpackage;
    # ARIBA build artefacts (metadata/manifest/prepareref_out) live here in
    # bac_ariba. Mirror of bac_kleborate.refs.paths.* constants.
    inputs_root = _BAC_KLEBORATE_REFS_DIR / db_name / "inputs"
    db_root = _BAC_ARIBA_ROOT / "refs" / db_name
    metadata_path = db_root / "metadata.tsv"
    manifest_path = db_root / "manifest.json"
    prepareref_out = db_root / "prepareref_out"
    db_root.mkdir(parents=True, exist_ok=True)

    _check_apptainer_on_path()
    if not ariba_sif.is_file():
        logger.error("apptainer SIF missing: %s", ariba_sif)
        sys.exit(2)

    if prepareref_out.exists() and not force:
        logger.error("%s already exists; pass --force to rebuild", prepareref_out)
        sys.exit(1)
    if force and prepareref_out.exists():
        shutil.rmtree(prepareref_out)

    src_pkg = importlib.import_module(spec["source_pkg"])
    src_pkg_dir = Path(src_pkg.__file__).resolve().parent
    src_pkg_version = _source_pkg_version(src_pkg)
    logger.info("Vendoring %s from %s (%s v%s)", db_name, src_pkg_dir, spec["source_pkg"], src_pkg_version)

    file_sums: dict[str, dict[str, str]] = {}
    fasta_args: list[str] = []
    manifest_extra: dict = {}

    if spec["kind"] == "virulence_loci":
        for mod, _cluster in spec["modules"]:
            src_data = src_pkg_dir / "modules" / mod / "data"
            if not src_data.exists():
                logger.error("source module data missing: %s", src_data)
                sys.exit(1)
            dest = inputs_root / mod
            if dest.exists():
                shutil.rmtree(dest)
            sums = _vendor_module(src_data, dest)
            file_sums[mod] = sums
            logger.info("  %-30s  %d files", mod, len(sums))
        metadata_path.write_text(_build_metadata(inputs_root, spec["modules"]))
        manifest_extra["modules"] = [{"name": m, "cluster": c} for m, c in spec["modules"]]
        for mod, _cluster in spec["modules"]:
            for fasta in sorted((inputs_root / mod).glob("*.fasta")):
                fasta_args.extend(["-f", str(fasta)])

    elif spec["kind"] == "amr_card":
        src_data = src_pkg_dir / "modules" / spec["module"] / "data"
        if not src_data.exists():
            logger.error("source module data missing: %s", src_data)
            sys.exit(1)
        if inputs_root.exists():
            shutil.rmtree(inputs_root)
        sums = _vendor_amr_data(src_data, inputs_root)
        file_sums[spec["module"]] = sums
        logger.info("  %-30s  %d files", spec["module"], len(sums))
        card_fastas = sorted(inputs_root.glob(spec["card_fasta_glob"]))
        if not card_fastas:
            logger.error("no CARD FASTA matching %r under %s", spec["card_fasta_glob"], inputs_root)
            sys.exit(1)
        card_fasta = card_fastas[0]
        metadata_path.write_text(_build_amr_metadata(card_fasta))
        manifest_extra["module"] = spec["module"]
        manifest_extra["card_fasta"] = card_fasta.name
        # Only the CARD FASTA goes into prepareref; mutational FASTAs are
        # variant_only and not registered in metadata.tsv (skipped for now).
        fasta_args.extend(["-f", str(card_fasta)])

    else:
        logger.error("unknown DB kind: %r", spec["kind"])
        sys.exit(1)

    n_seqs = sum(1 for _ in metadata_path.read_text().splitlines())
    logger.info("Wrote %s (%d sequences)", metadata_path.relative_to(REPO_ROOT), n_seqs)

    manifest = {
        "db_name": db_name,
        "kind": spec["kind"],
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_pkg": spec["source_pkg"],
        "source_pkg_version": src_pkg_version,
        "source_pkg_path": str(src_pkg_dir),
        "file_sha256": file_sums,
        **manifest_extra,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    logger.info("Wrote %s", manifest_path.relative_to(REPO_ROOT))
    inner_cmd = [
        "ariba",
        "prepareref",
        *fasta_args,
        "-m",
        str(metadata_path),
        "--threads",
        str(threads),
        str(prepareref_out),
    ]
    cmd = [
        "apptainer", "exec",
        "-B", f"{db_root}:{db_root}",
        "-B", f"{inputs_root}:{inputs_root}",
        str(ariba_sif), *inner_cmd,
    ]
    logger.info("Running ariba prepareref (containerised) → %s", prepareref_out.relative_to(REPO_ROOT))
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        logger.error("ariba prepareref failed (returncode %d)", res.returncode)
        sys.exit(res.returncode)
    logger.info("Build complete: %s", db_root.relative_to(REPO_ROOT))


def main() -> None:
    """CLI entrypoint."""
    ap = argparse.ArgumentParser(description="Build an ARIBA reference DB from vendored allele FASTAs.")
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument(
        "--kleb-virulence",
        action="store_const",
        dest="db",
        const="kleb_virulence",
        help="Build the Kleborate-derived virulence DB (5 loci: ybt/clb/iuc/iro/rmp).",
    )
    sel.add_argument(
        "--kleb-amr",
        action="store_const",
        dest="db",
        const="kleb_amr",
        help="Build the Kleborate-derived AMR DB (CARD acquired-resistance alleles).",
    )
    ap.add_argument("--ariba-sif", type=Path, required=True, help="Path to the ariba apptainer container.")
    ap.add_argument("--force", action="store_true", help="Rebuild even if prepareref_out/ exists.")
    ap.add_argument("--threads", type=int, default=1, help="Threads for cd-hit inside prepareref.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    build(args.db, ariba_sif=args.ariba_sif, force=args.force, threads=args.threads)


if __name__ == "__main__":
    main()
