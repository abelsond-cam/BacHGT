"""Smoke tests for the Bakta ``convert`` loaded from the panaroo fork.

Exercises the file-path loader in ``bac_panaroo.run_panaroo.panaroo_run_strain`` with
synthetic Bakta-shaped fixtures: confirms that single-``#`` banner lines
in the GFF body and pre-``>`` comment lines in the FASTA section are both
stripped, and that a valid combined GFF+FASTA is produced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bac_panaroo.run_panaroo.panaroo_run_strain import convert


# 252 nt = 84 × "AAA" (Lys, no stop codons). Long enough for two 99 nt CDSs.
CONTIG_SEQ = "AAA" * 84
CONTIG_ID = "contig_1"


def _gff_body(include_fasta: bool, fasta_preamble: str = "") -> str:
    body = (
        "##gff-version 3\n"
        "# Bakta v1.9.2 — synthetic test banner\n"
        "# Database: db v5.1 (synthetic)\n"
        f"##sequence-region {CONTIG_ID} 1 {len(CONTIG_SEQ)}\n"
        f"{CONTIG_ID}\tBakta\tCDS\t1\t99\t.\t+\t0\tID=cds_001;product=hypothetical\n"
        f"{CONTIG_ID}\tBakta\tCDS\t110\t208\t.\t+\t0\tID=cds_002;product=hypothetical\n"
    )
    if include_fasta:
        body += "##FASTA\n"
        if fasta_preamble:
            body += fasta_preamble
        body += f">{CONTIG_ID}\n{CONTIG_SEQ}\n"
    return body


def _assert_valid_combined_gff(out_path: Path) -> None:
    text = out_path.read_text()
    assert "##FASTA" in text, "output is missing ##FASTA separator"
    head, fasta = text.split("##FASTA", 1)
    assert "\tCDS\t" in head, "no CDS lines in output GFF section"
    assert f">{CONTIG_ID}" in fasta, "expected contig header missing from FASTA section"
    # At least one feature ID we wrote should survive
    assert "cds_001" in head or "cds_002" in head


def test_convert_separate_fasta(tmp_path: Path) -> None:
    """GFF body without embedded FASTA + separate assembly FASTA file."""
    gff_path = tmp_path / "sample.gff"
    fasta_path = tmp_path / "sample.fna"
    out_path = tmp_path / "combined.gff"

    gff_path.write_text(_gff_body(include_fasta=False))
    fasta_path.write_text(f">{CONTIG_ID}\n{CONTIG_SEQ}\n")

    convert(str(gff_path), str(out_path), str(fasta_path), is_ignore_overlapping=True)

    _assert_valid_combined_gff(out_path)


def test_convert_embedded_fasta_with_preamble(tmp_path: Path) -> None:
    """GFF body with embedded FASTA preceded by a ``# `` comment line.

    Confirms ``strip_fasta_preamble`` skips past the comment so SeqIO.parse
    sees a clean FASTA block.
    """
    gff_path = tmp_path / "sample.gff"
    out_path = tmp_path / "combined.gff"

    preamble = "# synthetic Bakta-style comment before first record\n"
    gff_path.write_text(_gff_body(include_fasta=True, fasta_preamble=preamble))

    # fastafile=None tells convert() to use the embedded FASTA section.
    convert(str(gff_path), str(out_path), None, is_ignore_overlapping=True)

    _assert_valid_combined_gff(out_path)


def test_convert_function_loaded_from_fork() -> None:
    """The wired ``convert`` should resolve to the sibling panaroo fork
    checkout, not to anything inlined inside BacHGT."""
    import inspect

    src = inspect.getsourcefile(convert)
    assert src is not None
    src_path = Path(src).resolve()
    expected = (
        Path(__file__).resolve().parents[1].parent
        / "panaroo"
        / "scripts"
        / "convert_bakta_to_prokka_gff.py"
    ).resolve()
    assert src_path == expected, f"convert came from {src_path}, expected {expected}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
