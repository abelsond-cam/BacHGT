"""Unit tests for ``_genome_records_for_row`` (dual SR+LRA genome expansion).

Each curated metadata row may carry a short-read assembly (``gff_file`` /
``assembly_file``) and/or a long-read assembly (``lra_gff_file`` /
``lra_assembly_file``). ``_genome_records_for_row`` turns one row into up to two
genome records, labelling the short-read genome by ``sample_accession`` and the
long-read genome by ``Sample``, and emitting a record only when both of its
files exist on disk.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bac_panaroo.pp.panaroo_run_strain import _genome_records_for_row


def _touch(path: Path) -> str:
    """Create an empty file at *path* and return its name (a base_dir-relative path)."""
    path.write_text("x")
    return path.name


def test_sr_only_row(tmp_path: Path) -> None:
    """SR files present, no LRA: one 'sr' record labelled by sample_accession."""
    gff = _touch(tmp_path / "SAMEA1.gff")
    fna = _touch(tmp_path / "SAMEA1.fna")
    row = pd.Series(
        {
            "Sample": "SAMEA1",  # SR-only: Sample == sample_accession
            "sample_accession": "SAMEA1",
            "gff_file": gff,
            "assembly_file": fna,
            "lra_gff_file": pd.NA,
            "lra_assembly_file": pd.NA,
        }
    )

    records = _genome_records_for_row(tmp_path, row)

    assert len(records) == 1
    (rec,) = records
    assert rec["assembly_type"] == "sr"
    assert rec["panaroo_label"] == "SAMEA1"
    assert rec["Sample"] == "SAMEA1"
    assert rec["gff_abs"] == (tmp_path / "SAMEA1.gff").resolve()
    assert rec["assembly_abs"] == (tmp_path / "SAMEA1.fna").resolve()


def test_lra_only_row(tmp_path: Path) -> None:
    """LRA files present, no SR: one 'lra' record labelled by Sample."""
    lra_gff = _touch(tmp_path / "GCF_9.1.gff")
    lra_fna = _touch(tmp_path / "GCF_9.1.fna")
    row = pd.Series(
        {
            "Sample": "GCF_9.1",
            "sample_accession": pd.NA,
            "gff_file": pd.NA,
            "assembly_file": pd.NA,
            "lra_gff_file": lra_gff,
            "lra_assembly_file": lra_fna,
        }
    )

    records = _genome_records_for_row(tmp_path, row)

    assert len(records) == 1
    (rec,) = records
    assert rec["assembly_type"] == "lra"
    assert rec["panaroo_label"] == "GCF_9.1"
    assert rec["Sample"] == "GCF_9.1"


def test_paired_row_yields_two_records(tmp_path: Path) -> None:
    """Both assemblies present: SR labelled by sample_accession, LRA by Sample."""
    sr_gff = _touch(tmp_path / "SAMEA2.gff")
    sr_fna = _touch(tmp_path / "SAMEA2.fna")
    lra_gff = _touch(tmp_path / "GCF_10.1.gff")
    lra_fna = _touch(tmp_path / "GCF_10.1.fna")
    row = pd.Series(
        {
            "Sample": "GCF_10.1",  # paired: Sample is the LRA accession
            "sample_accession": "SAMEA2",  # the SR SAM accession
            "gff_file": sr_gff,
            "assembly_file": sr_fna,
            "lra_gff_file": lra_gff,
            "lra_assembly_file": lra_fna,
        }
    )

    records = _genome_records_for_row(tmp_path, row)

    assert len(records) == 2
    by_type = {r["assembly_type"]: r for r in records}
    assert by_type["sr"]["panaroo_label"] == "SAMEA2"
    assert by_type["lra"]["panaroo_label"] == "GCF_10.1"
    # Both records carry the same metadata Sample for downstream flag lookup.
    assert by_type["sr"]["Sample"] == "GCF_10.1"
    assert by_type["lra"]["Sample"] == "GCF_10.1"


def test_skips_assembly_when_a_file_is_absent(tmp_path: Path) -> None:
    """A genome is dropped if either of its two files is missing on disk."""
    # SR: gff exists but assembly does NOT -> no SR record.
    sr_gff = _touch(tmp_path / "SAMEA3.gff")
    # LRA: both files exist -> one LRA record survives.
    lra_gff = _touch(tmp_path / "GCF_11.1.gff")
    lra_fna = _touch(tmp_path / "GCF_11.1.fna")
    row = pd.Series(
        {
            "Sample": "GCF_11.1",
            "sample_accession": "SAMEA3",
            "gff_file": sr_gff,
            "assembly_file": "SAMEA3_missing.fna",  # never created
            "lra_gff_file": lra_gff,
            "lra_assembly_file": lra_fna,
        }
    )

    records = _genome_records_for_row(tmp_path, row)

    assert len(records) == 1
    assert records[0]["assembly_type"] == "lra"


def test_lra_absolute_path_not_double_prefixed(tmp_path: Path) -> None:
    """v2 stores ``lra_*`` columns as absolute paths; base_dir must not be prepended.

    Regression: the original ``base / str(rel).lstrip("/")`` double-prefixed
    absolute LRA paths into ``base/home/dca36/...``, so no LRA record ever
    survived disk-existence checks.
    """
    # SR files live under tmp_path (relative-path convention).
    sr_gff = _touch(tmp_path / "SAMEA77.gff")
    sr_fna = _touch(tmp_path / "SAMEA77.fna")
    # LRA files live ELSEWHERE — at an absolute path outside tmp_path.
    elsewhere = tmp_path.parent / "lra_root"
    elsewhere.mkdir(exist_ok=True)
    lra_gff = elsewhere / "GCF_99.1.gff"
    lra_fna = elsewhere / "GCF_99.1.fna"
    lra_gff.write_text("x")
    lra_fna.write_text("x")

    row = pd.Series(
        {
            "Sample": "GCF_99.1",
            "sample_accession": "SAMEA77",
            "gff_file": sr_gff,
            "assembly_file": sr_fna,
            "lra_gff_file": str(lra_gff),
            "lra_assembly_file": str(lra_fna),
        }
    )

    records = _genome_records_for_row(tmp_path, row)

    assert len(records) == 2
    by_type = {r["assembly_type"]: r for r in records}
    assert by_type["lra"]["gff_abs"] == lra_gff.resolve()
    assert by_type["lra"]["assembly_abs"] == lra_fna.resolve()


def test_skips_sr_when_sample_accession_empty(tmp_path: Path) -> None:
    """SR files exist but sample_accession is empty: no SR record (cannot label)."""
    sr_gff = _touch(tmp_path / "x.gff")
    sr_fna = _touch(tmp_path / "x.fna")
    row = pd.Series(
        {
            "Sample": "GCF_12.1",
            "sample_accession": "",
            "gff_file": sr_gff,
            "assembly_file": sr_fna,
            "lra_gff_file": pd.NA,
            "lra_assembly_file": pd.NA,
        }
    )

    records = _genome_records_for_row(tmp_path, row)

    assert records == []
