#!/usr/bin/env bash
# Parallel per-sample ISEScan family + cluster counts (KpSC only). Outputs one wide CSV.
# Run: sbatch src/bac_isescan/slurm_scripts/isescan_n_per_sample.sh
# Progress: squeue -u "$USER"; cancel: scancel <jobid>

#SBATCH --job-name=isescan_n_sample
#SBATCH --output=isescan_n_per_sample_%j.out
#SBATCH --error=isescan_n_per_sample_%j.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --time=06:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU

set -euo pipefail

cd /home/dca36/workspace/BacHGT

export PYTHONUNBUFFERED=1

WORKERS="${SLURM_CPUS_PER_TASK:-32}"

echo "========================================================================"
echo "ISEScan per-sample family + cluster extraction"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Node: ${SLURMD_NODENAME}"
echo "Workers (--workers): ${WORKERS}"
echo "========================================================================"

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Starting bac_isescan.isescan_family_copy_per_sample"

uv run python -m bac_isescan.isescan_family_copy_per_sample \
  --workers "${WORKERS}" \
  --imap-chunksize 10000

echo ""
echo "========================================================================"
echo "Done."
echo "========================================================================"
