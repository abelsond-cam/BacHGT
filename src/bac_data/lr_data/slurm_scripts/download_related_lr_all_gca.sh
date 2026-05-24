#!/bin/bash
#SBATCH --job-name=download_related_lr_all_gca
#SBATCH --output=download_related_lr_all_gca_%j.out
#SBATCH --error=download_related_lr_all_gca_%j.err
#SBATCH --partition=icelake
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#
# download_related_lr_all_gca.sh
# ------------------------------
# Download every GCA in related_lr_all_gca.tsv (~2,571 LR assemblies) via the
# NCBI Datasets v2 REST endpoint, with the batch-level convergence loop.
#
# Why Slurm (not login-node nohup): CSD3 login nodes kill long-running jobs
# silently (the download was being SIGKILL'd every ~100 files when we tried it
# detached on the login node). Slurm gives the job its own cgroup and time
# budget. Pure-network, so icelake (not himem), 4 CPU, 8 GB.
#
# Resumable: the download script's --max-rounds convergence loop re-queues
# anything still missing on disk, so re-submitting the job is safe (it'll
# skip what's already present).
#
# Prerequisites:
#   - Optional: export NCBI_API_KEY before sbatch to lift the NCBI rate limit
#     from 3 to 10 req/s (the script honours it automatically).
#
# Usage:
#   sbatch src/bac_data/lr_data/slurm_scripts/download_related_lr_all_gca.sh
#
set -euo pipefail

cd /home/dca36/workspace/BacHGT

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Pick up NCBI_API_KEY from interactive shell config. /etc/bashrc on CSD3
# references unset vars (BASHRCSOURCED), so disable -u around the source.
set +u
# shellcheck disable=SC1090
source ~/.bashrc
set -u

# ---------------- User-editable settings ----------------
BASE=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
TSV="${BASE}/david/raw/related_lr/related_lr_all_gca.tsv"
OUT_DIR="${BASE}/david/raw/related_lr"
WORKERS=6
MAX_ROUNDS=5
# -------------------------------------------------------

echo "========================================================================"
echo "related-LR ALL-GCA download (NCBI Datasets v2, convergence loop)"
echo "Job ID: ${SLURM_JOB_ID:-local}   Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "TSV          : ${TSV}"
echo "Out dir      : ${OUT_DIR}"
echo "Workers      : ${WORKERS}"
echo "Max rounds   : ${MAX_ROUNDS}"
echo "NCBI_API_KEY : ${NCBI_API_KEY:+set (10 req/s)}${NCBI_API_KEY:-unset (3 req/s)}"
echo "========================================================================"

if [[ ! -f "${TSV}" ]]; then
  echo "ERROR: TSV not found: ${TSV}" >&2
  exit 1
fi

uv run python -u -m bac_data.lr_data.download_related_lr_complete_genomes \
  --cg-tsv "${TSV}" \
  --out-dir "${OUT_DIR}" \
  --which gca \
  --workers "${WORKERS}" \
  --max-rounds "${MAX_ROUNDS}"

echo
echo "Done. Next: uv run python -m bac_data.checkm2.prep_checkm2_inputs"
