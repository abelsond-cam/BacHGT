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
# Submit (88,810 / 100 = 889 chunks → array indices 0..888 — adjust to the
# actual chunk count printed by `prepare`):
#   sbatch --array=0-888 src/bac_genomad/slurm_scripts/run_genomad.sh
#
# Each task processes 100 assemblies sequentially at ~5 min/genome (8 threads
# each) → ~8 h per chunk. Resumable: per-sample .genomad.done sentinels skip
# completed genomes. --cleanup deletes geNomad intermediates on success.
#
# After the array finishes, collate on the login node:
#   pixi run python -m bac_genomad.run_genomad collate
#
# Smoke test via a 1-task array against a trimmed inputs TSV (DB + pixi cache
# stay pinned to the real root; only OUT_DIR/INPUTS/CHUNK_SIZE are overridden):
#   sbatch --job-name=genomad_smoke --array=0 --time=00:30:00 \
#     --export=ALL,GENOMAD_OUT_DIR=$G/smoke,GENOMAD_INPUTS=$G/inputs/genomad_inputs.smoke.tsv,GENOMAD_CHUNK_SIZE=3 \
#     src/bac_genomad/slurm_scripts/run_genomad.sh
#   (where G=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad)

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
GENOMAD_ROOT="$RDS/david/processed/genomad"   # fixed: DB + pixi env/cache live here

# Overridable for smoke runs via sbatch --export (defaults = the real run):
OUT_DIR="${GENOMAD_OUT_DIR:-$GENOMAD_ROOT}"
INPUTS="${GENOMAD_INPUTS:-$OUT_DIR/inputs/genomad_inputs.tsv}"
DB_DIR="${GENOMAD_DB_DIR:-$GENOMAD_ROOT/db/genomad_db}"
CHUNK_SIZE="${GENOMAD_CHUNK_SIZE:-100}"

# The geNomad pixi env pulls in TensorFlow (~4–5 GB), too big for the /home
# quota — env + package cache are detached onto project_k. The env location is
# pinned in src/bac_genomad/.pixi/config.toml (detached-environments); pin the
# cache here too so a `pixi run` revalidation never falls back to /home.
export PIXI_CACHE_DIR="$GENOMAD_ROOT/pixi_cache"

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
