#!/bin/bash
#SBATCH --job-name=viral_plot_refresh
#SBATCH --partition=icelake-himem
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/slurm_logs/viral_plot_refresh_%j.log

# Regenerate the four viral-analysis plots after their plot-code refactor.
# Inputs (long TSVs, length cache, carriage TSV) are untouched; just the
# rendering changed.

set -euo pipefail

REPO_DIR="/home/dca36/workspace/BacHGT"
cd "$REPO_DIR"

echo "[$(date -Is)] start viral_plot_refresh on $(hostname)"

echo "[$(date -Is)] === step 1: plot_standalone_viral_lengths (paired LRA + SR only) ==="
time uv run python -m bac_genomad.viral_analysis.lr_vs_sr.plot_standalone_viral_lengths

echo "[$(date -Is)] === step 2: analyze_viral_peaks single (is_complete x lra) ==="
time uv run python -m bac_genomad.viral_analysis.lr_vs_sr.analyze_viral_peaks

echo "[$(date -Is)] === step 3: viral_penetrance.per_lineage ==="
time uv run python -m bac_genomad.viral_analysis.viral_penetrance.per_lineage

echo "[$(date -Is)] === step 4: viral_penetrance.sl_to_cg_consistency ==="
time uv run python -m bac_genomad.viral_analysis.viral_penetrance.sl_to_cg_consistency

echo "[$(date -Is)] done viral_plot_refresh"
