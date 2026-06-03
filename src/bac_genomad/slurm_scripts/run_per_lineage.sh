#!/bin/bash
#SBATCH --job-name=viral_penetrance_per_lineage
#SBATCH --partition=icelake-himem
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/slurm_logs/per_lineage_%j.log

# Per-Sublineage / per-Clonal-group viral-bracket penetrance across the KpSC
# universe. Runs the BacHGT shared uv env (NOT the bac_genomad pixi env) so
# matplotlib + pandas + scipy are available.
#
# Usage:
#   sbatch src/bac_genomad/slurm_scripts/run_per_lineage.sh

set -euo pipefail

REPO_DIR="/home/dca36/workspace/BacHGT"
cd "$REPO_DIR"

echo "[$(date -Is)] start per_lineage on $(hostname) (cpus=${SLURM_CPUS_PER_TASK:-1})"
time uv run python -m bac_genomad.viral_analysis.viral_penetrance.per_lineage
echo "[$(date -Is)] done per_lineage"
