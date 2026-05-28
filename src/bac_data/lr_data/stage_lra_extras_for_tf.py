"""Symlink long-read assembly (LRA) originals into staging_for_tf/lra.

Second batch for the transformer workflow. The short-read (SR) genomes were
already staged and sent by ``stage_sr_for_related_lr.py`` (into
``raw/staging_for_tf/{assemblies,gff}``). This module stages the **long-read
assemblies themselves** — every ``lra_assembly_file`` in the v2 metadata — into
a separate ``raw/staging_for_tf/lra/{assemblies,gff}`` section so they can be
rsynced as the next batch and deleted afterwards.

``lra_assembly_file`` is an absolute on-disk path (the discovery table's
``fasta_on_disk``), pointing either at a ``seb/...`` RefSeq genome (is_refseq
rows) or at ``.../david/raw/related_lr/assemblies/<acc>.fna.gz`` (downloaded LR
genomes). The reserved ``lra_gff_file`` column is never populated, so GFFs are
sourced from ``related_lr/gff/<acc>.gff`` — present only for the downloaded
subset; seb-resident LRAs have no GFF there and are reported.

Files whose basename already lives in the SR staging section are skipped (they
were sent in the first batch).

Run from ~/workspace/BacHGT:
    uv run python -m bac_data.lr_data.stage_lra_extras_for_tf
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

RDS_BASE = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DAVID = RDS_BASE / "david"
METADATA_V2 = DAVID / "final" / "metadata_v2_all_samples_and_columns.tsv"
RELATED_LR = DAVID / "raw" / "related_lr"
STAGING = DAVID / "raw" / "staging_for_tf"
LRA_STAGING = STAGING / "lra"
SR_ASM_DIR = STAGING / "assemblies"
SR_GFF_DIR = STAGING / "gff"

ASM_SUFFIXES = (".fna.gz", ".fna", ".fasta.gz", ".fasta")


def load_lra_assembly_files() -> list[str]:
    """Unique non-empty ``lra_assembly_file`` paths from the v2 metadata."""
    csv.field_size_limit(sys.maxsize)
    seen: dict[str, None] = {}
    with METADATA_V2.open(newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if "lra_assembly_file" not in (reader.fieldnames or []):
            raise SystemExit(
                f"lra_assembly_file column not found in {METADATA_V2}\n"
                f"columns: {reader.fieldnames}"
            )
        for row in reader:
            path = (row.get("lra_assembly_file") or "").strip()
            if path:
                seen.setdefault(path, None)
    return list(seen)


def existing_sr_basenames() -> set[str]:
    """Basenames already staged in the SR section (first batch, already sent)."""
    names: set[str] = set()
    for d in (SR_ASM_DIR, SR_GFF_DIR):
        if d.is_dir():
            names.update(p.name for p in d.iterdir() if p.is_file() or p.is_symlink())
    return names


def clear_symlinks(d: Path) -> int:
    """Remove existing symlinks in d (leave real files alone). Returns count."""
    n = 0
    if d.is_dir():
        for p in d.iterdir():
            if p.is_symlink():
                p.unlink()
                n += 1
    return n


def assembly_stem(name: str) -> str:
    """Strip a FASTA suffix to get the accession stem (for the GFF lookup)."""
    for suffix in ASM_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def link_into(dst_dir: Path, original: Path) -> None:
    """Symlink ``original`` into ``dst_dir`` under its own basename."""
    link = dst_dir / original.name
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(original)


def main() -> int:
    """CLI entry point."""
    asm_paths = load_lra_assembly_files()
    sr_names = existing_sr_basenames()
    print(
        f"LRA assemblies in v2 metadata: {len(asm_paths)} | "
        f"already in SR staging: {len(sr_names)} basenames\n"
    )

    asm_dst = LRA_STAGING / "assemblies"
    gff_dst = LRA_STAGING / "gff"
    for d in (asm_dst, gff_dst):
        d.mkdir(parents=True, exist_ok=True)
    cleared = clear_symlinks(asm_dst) + clear_symlinks(gff_dst)

    report: list[str] = []
    asm_linked = gff_linked = 0
    missing_asm = already_sr = no_gff_dir = missing_gff = 0
    seen_asm: set[str] = set()

    for path in asm_paths:
        original = Path(path)
        if not original.is_file():
            missing_asm += 1
            report.append(f"assemblies\tmissing_assembly\t{original}")
            continue
        if original.name in sr_names:
            already_sr += 1
            report.append(f"assemblies\talready_in_sr_staging\t{original.name}")
            continue
        if original.name in seen_asm:
            continue
        seen_asm.add(original.name)

        link_into(asm_dst, original)
        asm_linked += 1

        # GFFs are only on disk for the related_lr-downloaded subset.
        if "related_lr/assemblies" in original.as_posix():
            gff = RELATED_LR / "gff" / f"{assembly_stem(original.name)}.gff"
            if gff.is_file():
                link_into(gff_dst, gff)
                gff_linked += 1
            else:
                missing_gff += 1
                report.append(f"gff\tmissing_gff\t{original.name}\t{gff}")
        else:
            no_gff_dir += 1
            report.append(f"gff\tgff_not_in_related_lr\t{original.name}\t{original}")

    report_path = LRA_STAGING / "lra_staging_report.tsv"
    report_path.write_text("kind\tstatus\tdetail...\n" + "\n".join(report) + ("\n" if report else ""))

    print(
        f"cleared_old_symlinks={cleared}\n"
        f"assemblies: symlinked={asm_linked} missing_assembly={missing_asm} "
        f"already_in_sr_staging={already_sr}\n"
        f"gff: symlinked={gff_linked} missing_gff={missing_gff} "
        f"gff_not_in_related_lr={no_gff_dir}\n"
        f"\nReport: {report_path} ({len(report)} problem rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
