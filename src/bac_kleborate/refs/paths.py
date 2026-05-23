"""Canonical paths to vendored Kleborate reference data.

Each ``*_INPUTS_DIR`` points at a directory of vendored source FASTAs / TSVs
copied from Kleborate's installed module data. Consumers should always go
through these constants rather than hardcoding relative paths — that way the
data can move without churn across consumers.

Layout under each ``*_INPUTS_DIR``:

- ``kleb_virulence`` — per-locus subdirs (``klebsiella__ybst/`` etc.) each
  with one or more allele FASTAs; mirrors Kleborate's older
  ``klebsiella__<locus>`` module convention.
- ``kleb_amr`` — flat dir holding Kleborate's KpSC AMR module data:
  ``CARD_v<version>.fasta`` plus class / metadata TSVs.
"""

from __future__ import annotations

from pathlib import Path

_REFS_DIR = Path(__file__).resolve().parent

KLEB_VIRULENCE_INPUTS_DIR: Path = _REFS_DIR / "kleb_virulence" / "inputs"
"""Vendored Kleborate virulence allele FASTAs (ybt / clb / iuc / iro / rmp / rmpA2)."""

KLEB_AMR_INPUTS_DIR: Path = _REFS_DIR / "kleb_amr" / "inputs"
"""Vendored Kleborate KpSC AMR module data (CARD FASTA + class TSVs)."""
