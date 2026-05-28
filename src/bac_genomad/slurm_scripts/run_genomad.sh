#!/usr/bin/env bash
# Slurm array job: run geNomad over every Klebsiella assembly (LRA + SR).
#
# Prereqs (one-time, login node):
#   1. cd src/bac_genomad && pixi install
#   2. pixi run genomad download-database \
#        /home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/db
#      → creates .../genomad/db/genomad_db/  (~2 GB)
#   3. pixi run python -m bac_genomad.run_genomad prepare
#      → writes <RDS>/david/processed/genomad/inputs/genomad_inputs.tsv (~90 k rows)
#
# Submit (90 k / 100 = ~900 chunks → array indices 0..899 — adjust to the
# actual chunk count printed by `prepare`):
#   sbatch --array=0-899 src/bac_genomad/slurm_scripts/run_genomad.sh
#
# Each task processes 100 assemblies sequentially at ~5 min/genome (8 threads
# each) → ~8 h per chunk. Resumable: per-sample .genomad.done sentinels skip
# completed genomes. --cleanup deletes geNomad intermediates on success.
#
# After the array finishes, collate on the login node:
#   pixi run python -m bac_genomad.run_genomad collate

#SBATCH --job-name=genomad
#SBATCH --partition=icelake
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=16:00:00
#SBATCH --output=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/slurm_logs/%x_%A_%a.out
#SBATCH --error=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/slurm_logs/%x_%A_%a.err

set -euo pipefail

REPO_DIR=${REPO_DIR:-$HOME/workspace/BacHGT}
PIXI_DIR="$REPO_DIR/src/bac_genomad"     # genomad lives in this env
RDS=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
OUT_DIR="$RDS/david/processed/genomad"
INPUTS="$OUT_DIR/inputs/genomad_inputs.tsv"
DB_DIR="$OUT_DIR/db/genomad_db"
CHUNK_SIZE=100

mkdir -p "$OUT_DIR/slurm_logs"

CHUNK_IDX="${SLURM_ARRAY_TASK_ID:-0}"

echo "[$(date -Is)] host=$(hostname)  job=${SLURM_JOB_ID:-local}  chunk=${CHUNK_IDX}  cpus=${SLURM_CPUS_PER_TASK:-?}"

if [[ ! -f "$INPUTS" ]]; then
    echo "FATAL: $INPUTS not found — run 'pixi run python -m bac_genomad.run_genomad prepare' first" >&2
    exit 2
fi
if [[ ! -d "$DB_DIR" ]]; then
    echo "FATAL: geNomad DB not found at $DB_DIR — run 'pixi run genomad download-database <parent>' first" >&2
    exit 2
fi

# Worker /tmp is tiny on icelake nodes. geNomad's annotate module writes large
# MMseqs2 alignment intermediates to TMPDIR; redirect to personal RDS (1 TB).
JOB="${SLURM_JOB_ID:-local}_${SLURM_ARRAY_TASK_ID:-0}"
export TMPDIR="$HOME/rds/hpc-work/genomad_tmp/$JOB"
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT

cd "$PIXI_DIR"
# bac_genomad is the pixi env's own package, but the module is in the
# monorepo's src/ — expose the parent to PYTHONPATH.
export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
pixi run python -m bac_genomad.run_genomad worker \
    --inputs "$INPUTS" \
    --chunk-idx "$CHUNK_IDX" \
    --chunk-size "$CHUNK_SIZE" \
    --out-dir "$OUT_DIR" \
    --db-dir "$DB_DIR" \
    --threads "${SLURM_CPUS_PER_TASK:-8}"

echo "[$(date -Is)] DONE chunk $CHUNK_IDX"
