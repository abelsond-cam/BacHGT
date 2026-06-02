#!/bin/bash
#SBATCH --job-name=gpa_ref_granularity
#SBATCH --output=gpa_ref_granularity_%j.out
#SBATCH --error=gpa_ref_granularity_%j.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=4:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --mem=32G
#
# gpa_reference_granularity.sh
# ---------------------------
# Compute GPA reference genome granularity analysis (how much shared-gene
# coverage improves at each granularity level d → c → b → a) and generate
# run inventory markdown.
#
# Output:
#   <OUTPUT_DIR>/run_inventory.md — run summary
#   <OUTPUT_DIR>/granularity_table.tsv — per-CG granularity metrics
#   <OUTPUT_DIR>/granularity_summary.tsv — aggregate stats
#   <OUTPUT_DIR>/best_reference_per_sample.csv — per-sample best ref +
#       shared-gene count at every level (f/d/c/b/a)
#   <OUTPUT_DIR>/granularity_lollipop.png/pdf — connected-dot plot
#

cd /home/dca36/workspace/BacHGT

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# ---------------- User-editable settings ----------------
DATA_ROOT="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david"
PANAROO_RUN_ROOT="${DATA_ROOT}/processed/panaroo_with_reference_genome"
METADATA_PATH="${DATA_ROOT}/final/metadata_v2_all_samples_and_columns.tsv"
OUTPUT_DIR="${DATA_ROOT}/processed/pangenome_analysis/granularity"
WORKERS=8
MIN_GROUP_SIZE=50           # Min CG / K-locus size to be its own slice (default 50)
MODE="both"                 # inventory | granularity | both
TEST_N_RUNS=""              # e.g. 2 for smoke test; empty for all runs
RECOMPILE=false             # true to rebuild combined detail TSV
STAGE_VENV=false
# -------------------------------------------------------

echo "========================================================================"
echo "GPA Reference Granularity Analysis (gpa_reference_granularity.py)"
echo "IceLake"
echo "--------------------------------"
echo "Stage VENV: ${STAGE_VENV}"
echo "Job ID: ${SLURM_JOB_ID:-local}"
echo "Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "Mode: ${MODE}"
echo "========================================================================"
echo ""

# Pick python: staged local copy (fast) or uv run
PYTHON_CMD=("uv" "run" "python" "-u")
if [[ "${STAGE_VENV}" == "true" ]]; then
  SCRATCH="${SLURM_TMPDIR:-${TMPDIR:-/tmp}}"
  STAGED_VENV="${SCRATCH}/bac_panaroo_venv_${SLURM_JOB_ID:-$$}"
  if [[ ! -L .venv && ! -d .venv ]]; then
    echo "WARNING: .venv not found; falling back to 'uv run'." >&2
  else
    VENV_REAL="$(readlink -f .venv)"
    echo "venv staging: resolved .venv -> ${VENV_REAL}"
    echo "venv staging: rsync -> ${STAGED_VENV}"
    rm -rf "${STAGED_VENV}"
    mkdir -p "${STAGED_VENV}"
    if /usr/bin/time -f "venv staging: rsync elapsed=%es peak_rss=%MkB" \
         rsync -a "${VENV_REAL}/" "${STAGED_VENV}/"; then
      if [[ -x "${STAGED_VENV}/bin/python" ]]; then
        PYTHON_CMD=("${STAGED_VENV}/bin/python" "-u")
        echo "venv staging: using ${STAGED_VENV}/bin/python (shared across ${WORKERS} workers)"
      else
        echo "WARNING: staged venv missing bin/python; falling back to 'uv run'." >&2
      fi
    else
      echo "WARNING: rsync failed; falling back to 'uv run'." >&2
    fi
  fi
else
  echo "venv staging: disabled (STAGE_VENV=false); using 'uv run'."
fi
echo ""

CMD=(
  "${PYTHON_CMD[@]}" src/bac_panaroo/gpa_analysis/gpa_reference_granularity.py
  --data-dir "${PANAROO_RUN_ROOT}"
  --metadata "${METADATA_PATH}"
  --out-dir "${OUTPUT_DIR}"
  --mode "${MODE}"
  --min-group-size "${MIN_GROUP_SIZE}"
  --workers "${WORKERS}"
)

if [[ -n "${TEST_N_RUNS}" ]]; then
  CMD+=(--test-n-runs "${TEST_N_RUNS}")
fi
if [[ "${RECOMPILE}" == "true" ]]; then
  CMD+=(--recompile)
fi

"${CMD[@]}"
RC=$?

if [[ "${STAGE_VENV}" == "true" && -n "${STAGED_VENV:-}" && -d "${STAGED_VENV}" ]]; then
  echo ""
  echo "cleanup: removing staged venv ${STAGED_VENV}"
  rm -rf "${STAGED_VENV}" || echo "cleanup: rm -rf failed (ignored)"
fi

echo ""
echo "========================================================================"
echo "Job complete! (exit=${RC})"
echo "========================================================================"
exit "${RC}"

# Run with: sbatch src/bac_panaroo/slurm_scripts/gpa_reference_granularity.sh
# Check: squeue -u dca36
# Cancel: scancel <jobid>
# Smoke test (2 runs): edit TEST_N_RUNS=2 near the top, then sbatch
