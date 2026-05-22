"""Symlink short-read assembly_file/gff_file originals into staging_for_tf.

For every long-read complete genome downloaded under
``raw/related_lr/{assemblies,gff}`` (named by its ``resolved_gca`` stem),
find the matching short-read sample and symlink that sample's
``assembly_file`` / ``gff_file`` original into
``raw/staging_for_tf/{assemblies,gff}`` so the resolved files can be
rsynced for the transformer workflow.

Authoritative map: ``raw/norway_genomes/norway_tables1_integration.tsv``
(produced by ``norway_tables1_integrate.py`` from
``Norway_Complete_Genomes_Fig1.xlsx``). It links each downloaded
``resolved_gca`` -> ``biosample``, and that biosample is the ``Sample``
in the curated slimmed metadata. Rows with ``in_metadata == False`` have
no short-read sample in our metadata and are reported, not symlinked.

Run from ~/workspace/BacHGT:
    uv run python src/bac_panaroo/pp/download_data/stage_sr_for_related_lr.py
"""

from __future__ import annotations

import csv
from pathlib import Path

RDS_BASE = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DAVID = RDS_BASE / "david"
METADATA = DAVID / "final" / "metadata_final_curated_slimmed.tsv"
INTEGRATION = DAVID / "raw" / "norway_genomes" / "norway_tables1_integration.tsv"
RELATED_LR = DAVID / "raw" / "related_lr"
STAGING = DAVID / "raw" / "staging_for_tf"


def load_gca_to_biosample() -> dict[str, str]:
    """resolved_gca stem -> biosample, from the Norway integration TSV."""
    out: dict[str, str] = {}
    with INTEGRATION.open(newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            gca = (row.get("resolved_gca") or "").strip()
            if gca:
                out[gca] = (row.get("biosample") or "").strip()
    return out


def load_sample_files() -> dict[str, tuple[str, str]]:
    """Sample -> (assembly_file, gff_file) from the curated slimmed metadata."""
    out: dict[str, tuple[str, str]] = {}
    with METADATA.open(newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            out[row["Sample"]] = (
                row.get("assembly_file", "") or "",
                row.get("gff_file", "") or "",
            )
    return out


def clear_symlinks(d: Path) -> int:
    """Remove existing symlinks in d (leave real files alone). Returns count."""
    n = 0
    if d.is_dir():
        for p in d.iterdir():
            if p.is_symlink():
                p.unlink()
                n += 1
    return n


def main() -> int:
    gca2bs = load_gca_to_biosample()
    sample2files = load_sample_files()
    print(
        f"Integration rows: {len(gca2bs)} resolved_gca | "
        f"metadata samples: {len(sample2files)}\n"
    )

    report: list[str] = []
    for kind, col_idx in (("assemblies", 0), ("gff", 1)):
        src_dir = RELATED_LR / kind
        dst_dir = STAGING / kind
        dst_dir.mkdir(parents=True, exist_ok=True)
        removed = clear_symlinks(dst_dir)

        n_src = linked = 0
        not_in_integration = no_metadata = no_path = missing_orig = collisions = 0
        seen: dict[str, str] = {}

        for f in sorted(src_dir.iterdir()):
            if not f.is_file():
                continue
            n_src += 1
            suffix = ".fna.gz" if kind == "assemblies" else ".gff"
            stem = f.name[: -len(suffix)] if f.name.endswith(suffix) else f.stem

            bs = gca2bs.get(stem)
            if bs is None:
                not_in_integration += 1
                report.append(f"{kind}\tnot_in_integration\t{f.name}")
                continue
            rec = sample2files.get(bs)
            if rec is None:
                no_metadata += 1
                report.append(f"{kind}\tno_metadata_sample\t{f.name}\t{bs}")
                continue
            rel = rec[col_idx]
            if not rel:
                no_path += 1
                report.append(f"{kind}\tno_{['assembly','gff'][col_idx]}_file\t{f.name}\t{bs}")
                continue
            original = (RDS_BASE / rel).resolve()
            if not original.is_file():
                missing_orig += 1
                report.append(f"{kind}\tmissing_original\t{f.name}\t{bs}\t{original}")
                continue

            link = dst_dir / original.name
            if original.name in seen and seen[original.name] != bs:
                collisions += 1
                report.append(
                    f"{kind}\tname_collision\t{original.name}\t{seen[original.name]}\t{bs}"
                )
                continue
            seen[original.name] = bs
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(original)
            linked += 1

        print(
            f"[{kind}] src={n_src} cleared_old_symlinks={removed} "
            f"symlinked={linked} | not_in_integration={not_in_integration} "
            f"no_metadata_sample={no_metadata} no_path={no_path} "
            f"missing_original={missing_orig} name_collision={collisions}"
        )

    report_path = STAGING / "staging_report.tsv"
    report_path.write_text(
        "kind\tstatus\tdetail...\n" + "\n".join(report) + ("\n" if report else "")
    )
    # The old report from the superseded matching approach is no longer valid.
    old = STAGING / "staging_report_unmatched_missing.tsv"
    if old.exists():
        old.unlink()
    print(f"\nReport: {report_path} ({len(report)} problem rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
