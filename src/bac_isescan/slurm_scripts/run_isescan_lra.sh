#!/usr/bin/env bash
# Slurm array job: run ISEScan over the LRA cohort (Phase G.2).
#
# Prereqs (one-time):
#   1. uv run python -m bac_isescan.run_isescan_lra prepare
#      → writes <RDS>/david/processed/isescan_lra/isescan_inputs.tsv (~5,521 rows)
#   2. The pixi env at src/bac_isescan/ already pins isescan >= 1.7.2.
#      (cd src/bac_isescan && pixi install) once if not yet installed on HPC.
#
# Submit (5,521 / 30 = ~184 chunks → array indices 0..183):
#   sbatch --array=0-183 src/bac_isescan/slurm_scripts/run_isescan_lra.sh
#
# Each task processes 30 LRAs sequentially at ~10 min/genome (4 threads each)
# → ~5 h per chunk. Resumable: per-sample .isescan.done sentinels skip
# completed genomes.
#
# After the array finishes, collate locally:
#   uv run python -m bac_isescan.run_isescan_lra collate

#SBATCH --job-name=isescan_lra
#SBATCH --partition=icelake-himem
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/isescan_lra/slurm_logs/%x_%A_%a.out
#SBATCH --error=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/isescan_lra/slurm_logs/%x_%A_%a.err

set -euo pipefail

REPO_DIR=${REPO_DIR:-$HOME/workspace/BacHGT}
PIXI_DIR="$REPO_DIR/src/bac_isescan"     # isescan lives in this env
RDS=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
OUT_DIR="$RDS/david/processed/isescan_lra"
INPUTS="$OUT_DIR/isescan_inputs.tsv"
CHUNK_SIZE=30

mkdir -p "$OUT_DIR/slurm_logs"

CHUNK_IDX="${SLURM_ARRAY_TASK_ID:-0}"

echo "[$(date -Is)] host=$(hostname)  job=${SLURM_JOB_ID:-local}  chunk=${CHUNK_IDX}  cpus=${SLURM_CPUS_PER_TASK:-?}"

if [[ ! -f "$INPUTS" ]]; then
    echo "FATAL: $INPUTS not found — run 'uv run python -m bac_isescan.run_isescan_lra prepare' first" >&2
    exit 2
fi

# Worker /tmp is tiny on icelake nodes. ISEScan writes intermediate HMMER /
# BLAST files to TMPDIR; redirect to personal RDS (1 TB) for safety.
JOB="${SLURM_JOB_ID:-local}_${SLURM_ARRAY_TASK_ID:-0}"
export TMPDIR="$HOME/rds/hpc-work/isescan_tmp/$JOB"
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT

cd "$PIXI_DIR"
# bac_isescan is the pixi env's own package, but the module is in the
# monorepo's src/ — expose the parent to PYTHONPATH.
export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
pixi run python -m bac_isescan.run_isescan_lra worker \
    --inputs "$INPUTS" \
    --chunk-idx "$CHUNK_IDX" \
    --chunk-size "$CHUNK_SIZE" \
    --out-dir "$OUT_DIR" \
    --threads "${SLURM_CPUS_PER_TASK:-4}"

echo "[$(date -Is)] DONE chunk $CHUNK_IDX"
