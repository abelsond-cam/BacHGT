"""Paths, defaults, and sizing knobs for the geNomad LRA+SR run."""

from __future__ import annotations

from pathlib import Path

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_OUT_DIR     = DATA_ROOT / "david/processed/genomad"
DEFAULT_INPUTS_TSV  = DEFAULT_OUT_DIR / "inputs" / "genomad_inputs.tsv"
DEFAULT_DB_DIR      = DEFAULT_OUT_DIR / "db" / "genomad_db"

# Long-format outputs of `bac_genomad.run_genomad collate` — consumed by
# downstream comparators (e.g. compare_lra_to_sr).
DEFAULT_PLASMID_LONG_TSV = DEFAULT_OUT_DIR / "genomad_plasmid_summary_long.tsv"
DEFAULT_VIRUS_LONG_TSV   = DEFAULT_OUT_DIR / "genomad_virus_summary_long.tsv"

# All downstream viral analyses (peak characterisation, LR-vs-SR comparison,
# per-SL/CG penetrance, future phage/prophage work) live under one root:
#   <DATA_ROOT>/david/processed/genomad/viral_analysis/
DEFAULT_VIRAL_ANALYSIS_DIR  = DEFAULT_OUT_DIR / "viral_analysis"
DEFAULT_VIRAL_LR_VS_SR_DIR  = DEFAULT_VIRAL_ANALYSIS_DIR / "lr_vs_sr"
DEFAULT_VIRAL_PENETRANCE_DIR = DEFAULT_VIRAL_ANALYSIS_DIR / "viral_penetrance"

# ─── SIZING ───────────────────────────────────────────────────────────────────

# ~5 min/sample at 8 threads → 100 samples ≈ 8.3 h per chunk; fits a 16 h
# walltime with slack for outliers. 900 array tasks for ~90 k jobs sits under
# CSD3's typical 1024 MaxArraySize.
DEFAULT_CHUNK_SIZE = 100
DEFAULT_THREADS    = 8

# Suffix appended to the LRA Sample id when a paired SR assembly is also run,
# so the SR row doesn't collide with the LRA row in `per_sample/`.
SR_PAIRED_SUFFIX = "__sr"
