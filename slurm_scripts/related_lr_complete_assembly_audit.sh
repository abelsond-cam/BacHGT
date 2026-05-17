#!/bin/bash
#SBATCH --job-name=related_lr_complete_audit
#SBATCH --output=related_lr_complete_audit_%j.out
#SBATCH --error=related_lr_complete_audit_%j.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=02:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --mem=8G
#
# related_lr_complete_assembly_audit.sh
# -------------------------------------
# Audit which of the remaining related-long-read samples (non-Norway,
# non-RefSeq, with a related_lr_*accession) already have a Complete-Genome
# GCA in GenBank — so we can download those instead of re-assembling from
# raw long reads.
#
# This is a pure network/API job (NCBI Datasets per BioSample). It is
# light enough to run on the login node directly, exactly like
# norway_cohort_audit.py:
#
#   uv run python -m bacotype.pp.download_data.related_lr_complete_assembly_audit
#
# The Slurm wrapper just gives it a guaranteed NCBI_API_KEY-rate budget
# and a clean log. ~3,000 probes ≈ a few minutes with a key.
#
# Prerequisites:
#   - Optional: export NCBI_API_KEY before sbatch to lift the NCBI rate
#     limit from 3 to 10 req/s (the script honours it automatically).
#
# Usage:
#   sbatch slurm_scripts/related_lr_complete_assembly_audit.sh
#   bash   slurm_scripts/related_lr_complete_assembly_audit.sh
#
set -euo pipefail

cd /home/dca36/workspace/Bacotype

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# ---------------- User-editable settings ----------------
BASE=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
METADATA="${BASE}/david/final/metadata_final_curated_all_samples_and_columns.tsv"
OUT_DIR="${BASE}/david/processed"
# -------------------------------------------------------

echo "========================================================================"
echo "related-LR Complete-Genome assembly audit"
echo "Job ID: ${SLURM_JOB_ID:-local}   Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "Metadata : ${METADATA}"
echo "Out dir  : ${OUT_DIR}"
echo "NCBI_API_KEY : ${NCBI_API_KEY:+set (10 req/s)}${NCBI_API_KEY:-unset (3 req/s)}"
echo "========================================================================"

if [[ ! -f "${METADATA}" ]]; then
  echo "ERROR: metadata not found: ${METADATA}" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

uv run python -u -m bacotype.pp.download_data.related_lr_complete_assembly_audit \
  --metadata "${METADATA}" \
  --out-dir "${OUT_DIR}"

echo
echo "Done. Review ${OUT_DIR}/related_lr_complete_genomes.tsv — that is the"
echo "actionable Complete-Genome download list for the follow-up step."
