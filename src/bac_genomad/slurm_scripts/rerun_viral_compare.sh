#!/bin/bash
#SBATCH --job-name=viral_compare_metadata_v2
#SBATCH --partition=icelake-himem
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --cpus-per-task=76
#SBATCH --mem=128G
#SBATCH --time=02:00:00
#SBATCH --output=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/slurm_logs/viral_rerun_%j.log

# Re-run the LRA-vs-SR pipeline now that the paired set is derived directly
# from metadata_v2 (drops the corrupted ~3,442 paired-SR rows that previously
# came in via the stale paired_index.tsv).
#
# Sequence:
#   1. compare        — paired__<cohort>.tsv per cohort (cache hot)
#   2. dump_lengths   — standalone_viral_lengths.tsv
#   3. analyze_viral_peaks --multi  — 2x2 LRA-vs-SR zoom PNG
#   4. analyze_viral_peaks (single, is_complete x lra_all) — Gaussian peak refit

set -euo pipefail

REPO_DIR="/home/dca36/workspace/BacHGT"
cd "$REPO_DIR"

echo "[$(date -Is)] start viral_rerun on $(hostname) (cpus=${SLURM_CPUS_PER_TASK:-1})"

# FASTA scanning is I/O-bound on Lustre — oversubscribe threads vs CPUs.
SCAN_WORKERS=128

echo "[$(date -Is)] === step 1: compare ==="
time uv run python -m bac_genomad.viral_analysis.lr_vs_sr.compare_lra_to_sr compare \
    --workers "${SCAN_WORKERS}"

echo "[$(date -Is)] === step 2: dump_lengths ==="
time uv run python -m bac_genomad.viral_analysis.lr_vs_sr.compare_lra_to_sr dump_lengths \
    --workers "${SCAN_WORKERS}"

echo "[$(date -Is)] === step 3: analyze_viral_peaks --multi ==="
time uv run python -m bac_genomad.viral_analysis.lr_vs_sr.analyze_viral_peaks --multi

echo "[$(date -Is)] === step 4: analyze_viral_peaks single (is_complete x lra_all) ==="
time uv run python -m bac_genomad.viral_analysis.lr_vs_sr.analyze_viral_peaks \
    --cohort is_complete --side lra_all

echo "[$(date -Is)] done viral_rerun"
