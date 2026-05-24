#!/bin/bash
#SBATCH --job-name=download_lra_missing_gca
#SBATCH --output=download_lra_missing_gca_%j.out
#SBATCH --error=download_lra_missing_gca_%j.err
#SBATCH --partition=icelake
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#
# download_lra_missing_gca.sh
# ---------------------------
# Download every GCA flagged download_needed=True in lra_discovery.tsv. The
# per-tier missing-accession TSV is produced by `discovery_to_download_lists.py`
# (run that first, on the login node — it's a 30 s pandas script).
#
# Uses the same NCBI Datasets v2 + convergence-loop downloader as
# download_related_lr_all_gca.sh; the convergence loop makes resubmission safe.
#
# Prerequisites:
#   1. lra_discovery.tsv exists at ${BASE}/david/processed/
#   2. discovery_to_download_lists.py has been run → emits lra_download_gca_missing.tsv
#   3. Optional: ~/.ncbi_api_key holds the NCBI API key (mode 600).
#
# Usage:
#   sbatch src/bac_data/lr_data/slurm_scripts/download_lra_missing_gca.sh
#
set -euo pipefail

cd /home/dca36/workspace/BacHGT

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Pick up NCBI_API_KEY from a private dot-file outside the repo (mode 600).
if [[ -r ~/.ncbi_api_key ]]; then
  NCBI_API_KEY="$(< ~/.ncbi_api_key)"
  export NCBI_API_KEY
fi

# ---------------- User-editable settings ----------------
BASE=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
TSV="${BASE}/david/processed/lra_download_gca_missing.tsv"
OUT_DIR="${BASE}/david/raw/related_lr"
WORKERS=6
MAX_ROUNDS=5
# -------------------------------------------------------

echo "========================================================================"
echo "LRA missing-GCA download (NCBI Datasets v2, convergence loop)"
echo "Job ID: ${SLURM_JOB_ID:-local}   Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "TSV          : ${TSV}"
echo "Out dir      : ${OUT_DIR}"
echo "Workers      : ${WORKERS}"
echo "Max rounds   : ${MAX_ROUNDS}"
if [[ -n "${NCBI_API_KEY:-}" ]]; then
  echo "NCBI_API_KEY : set (10 req/s)"
else
  echo "NCBI_API_KEY : unset (3 req/s)"
fi
echo "========================================================================"

if [[ ! -f "${TSV}" ]]; then
  echo "ERROR: TSV not found: ${TSV}" >&2
  echo "       Run: uv run python -m bac_data.lr_data.discovery_to_download_lists" >&2
  exit 1
fi

uv run python -u -m bac_data.lr_data.download_related_lr_complete_genomes \
  --cg-tsv "${TSV}" \
  --out-dir "${OUT_DIR}" \
  --which gca \
  --workers "${WORKERS}" \
  --max-rounds "${MAX_ROUNDS}"

echo
echo "Done. Re-run build_lra_discovery to refresh fasta_on_disk, then prep_checkm2_inputs."
