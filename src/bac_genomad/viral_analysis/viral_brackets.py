"""5-bracket size classifier for standalone-viral geNomad calls.

Centres + widths come from a Gaussian peak fit on the standalone-viral
length distribution of the ``is_complete`` LRA-all cohort (see the
companion ``lr_vs_sr/analyze_viral_peaks.py`` for the fitting code and
``lr_vs_sr/standalone_viral_peak_stats_is_complete_lra_all.tsv`` for the
provenance numbers):

- **Upper peak** ("Sgld_v"): μ = 111,018 bp, σ = 2,080 bp
- **Lower peak** ("Wbr_v"): μ = 54,500 bp, σ = 1,160 bp

Both peaks are very tight: σ/μ ≈ 1.9% (upper) and 2.1% (lower); FWHM
4.9 kb and 2.7 kb respectively. We use ±2σ around each centre (95.4 %
of a Gaussian's mass) — tighter than ±FWHM (98.1 %), to keep the bracket
labels clean of shoulder mass that's mixed-origin.

Brackets partition the real line with half-open intervals ``[lo, hi)``.
``lo = None`` means "no lower bound"; ``hi = None`` means "no upper bound".

Outside this module, treat the labels as opaque tags. Downstream consumers
should import :data:`VIRAL_BRACKETS` or call :func:`classify_length` /
:func:`assign_brackets` rather than hard-coding the cut values.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

# ─── Peak provenance (from is_complete LRA-all fit, 2026-06-02 run) ──────────

SGLD_V_CENTRE_BP: Final[int] = 111_018
SGLD_V_SIGMA_BP:  Final[int] =   2_080
WBR_V_CENTRE_BP:  Final[int] =  54_500
WBR_V_SIGMA_BP:   Final[int] =   1_160

# ±2σ cuts. Stored as ints (bp) so the classification is exact.
SGLD_V_LO: Final[int] = SGLD_V_CENTRE_BP - 2 * SGLD_V_SIGMA_BP   # 106_858
SGLD_V_HI: Final[int] = SGLD_V_CENTRE_BP + 2 * SGLD_V_SIGMA_BP   # 115_178
WBR_V_LO:  Final[int] = WBR_V_CENTRE_BP  - 2 * WBR_V_SIGMA_BP    #  52_180
WBR_V_HI:  Final[int] = WBR_V_CENTRE_BP  + 2 * WBR_V_SIGMA_BP    #  56_820

# Ordered, mutually exclusive, exhaustive. ``(label, lo, hi)`` with half-open
# ``[lo, hi)`` semantics. ``None`` = unbounded.
VIRAL_BRACKETS: Final[tuple[tuple[str, int | None, int | None], ...]] = (
    ("above_upper", SGLD_V_HI, None),       # ≥ 115_178
    ("Sgld_v",      SGLD_V_LO, SGLD_V_HI),  # 106_858 – 115_178
    ("between",     WBR_V_HI,  SGLD_V_LO),  #  56_820 – 106_858
    ("Wbr_v",       WBR_V_LO,  WBR_V_HI),   #  52_180 –  56_820
    ("below_lower", None,      WBR_V_LO),   # <  52_180
)

BRACKET_LABELS: Final[tuple[str, ...]] = tuple(label for label, _, _ in VIRAL_BRACKETS)


def classify_length(length_bp: int) -> str:
    """Return the bracket label for a single contig length (bp)."""
    if length_bp >= SGLD_V_HI:
        return "above_upper"
    if length_bp >= SGLD_V_LO:
        return "Sgld_v"
    if length_bp >= WBR_V_HI:
        return "between"
    if length_bp >= WBR_V_LO:
        return "Wbr_v"
    return "below_lower"


def assign_brackets(lengths: pd.Series) -> pd.Series:
    """Vectorised classification of a length column.

    Treats non-numeric / NA entries as missing — the corresponding output
    rows are ``NaN`` rather than a bracket label. Numeric values are
    converted to int before classification.
    """
    lens = pd.to_numeric(lengths, errors="coerce")
    cuts = [-np.inf, WBR_V_LO, WBR_V_HI, SGLD_V_LO, SGLD_V_HI, np.inf]
    labels = ["below_lower", "Wbr_v", "between", "Sgld_v", "above_upper"]
    # ``right=False`` gives ``[lo, hi)`` half-open intervals.
    out = pd.cut(lens, bins=cuts, labels=labels, right=False, ordered=False)
    return out.astype("object").where(lens.notna(), other=pd.NA)
