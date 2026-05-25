#!/usr/bin/env bash
# Slurm array job: run Kleborate v3 over the LRA cohort (Phase G.2).
#
# Prereqs (one-time):
#   1. uv run python -m bac_kleborate.run_kleborate_lra prepare
#      → writes <RDS>/david/processed/kleborate_lra/lra_inputs.tsv (~5,521 rows)
#   2. The pixi env at src/bac_isescan/ already pins kleborate >= 3.1.
#      (cd src/bac_isescan && pixi install) once if not yet installed on HPC.
#
# Submit (5,521 / 100 = 56 chunks → array indices 0..55):
#   sbatch --array=0-55 src/bac_kleborate/slurm_scripts/run_kleborate_lra.sh
#
# Each task processes 100 LRAs at ~30 s/genome → ~50 min per chunk.
# Resumable: chunks that finished (sentinel `.kleborate.done`) are skipped.
#
# After the array finishes, collate locally:
#   uv run python -m bac_kleborate.run_kleborate_lra collate

#SBATCH --job-name=kleborate_lra
#SBATCH --partition=icelake
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:30:00
#SBATCH --output=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/kleborate_lra/slurm_logs/%x_%A_%a.out
#SBATCH --error=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/kleborate_lra/slurm_logs/%x_%A_%a.err

set -euo pipefail

REPO_DIR=${REPO_DIR:-$HOME/workspace/BacHGT}
PIXI_DIR="$REPO_DIR/src/bac_isescan"     # kleborate lives in this env
RDS=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
OUT_DIR="$RDS/david/processed/kleborate_lra"
INPUTS="$OUT_DIR/lra_inputs.tsv"
CHUNK_SIZE=100

mkdir -p "$OUT_DIR/slurm_logs"

CHUNK_IDX="${SLURM_ARRAY_TASK_ID:-0}"

echo "[$(date -Is)] host=$(hostname)  job=${SLURM_JOB_ID:-local}  chunk=${CHUNK_IDX}  cpus=${SLURM_CPUS_PER_TASK:-?}"

if [[ ! -f "$INPUTS" ]]; then
    echo "FATAL: $INPUTS not found — run 'uv run python -m bac_kleborate.run_kleborate_lra prepare' first" >&2
    exit 2
fi

# Worker /tmp is tiny on icelake nodes; Kleborate's BLAST stage stages temp files there.
# Point TMPDIR at personal RDS so we don't run out.
JOB="${SLURM_JOB_ID:-local}_${SLURM_ARRAY_TASK_ID:-0}"
export TMPDIR="$HOME/rds/hpc-work/kleborate_tmp/$JOB"
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT

cd "$PIXI_DIR"
pixi run python -m bac_kleborate.run_kleborate_lra worker \
    --inputs "$INPUTS" \
    --chunk-idx "$CHUNK_IDX" \
    --chunk-size "$CHUNK_SIZE" \
    --out-dir "$OUT_DIR"

echo "[$(date -Is)] DONE chunk $CHUNK_IDX"
