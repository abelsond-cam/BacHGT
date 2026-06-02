#!/bin/bash
#SBATCH --job-name=pangenomerge
#SBATCH --output=/home/dca36/workspace/pangenome_merge/logs/merge_%j.out
#SBATCH --error=/home/dca36/workspace/pangenome_merge/logs/merge_%j.err
#SBATCH --partition=icelake-himem
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=4:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#
# pangenomerge_merge.sh
# ---------------------
# Merge N Panaroo output graphs into a single pangenome graph using pangenomerge
# (https://github.com/qtoussaint/pangenome_merge). Adapted from the user's prior
# ~/workspace/pangenome_merge/pangenome_merge_run.sh.
#
# The pangenomerge micromamba env on HPC carries only the runtime deps; the
# pangenomerge package is imported from the source checkout at PANGENOME_MERGE_ROOT
# via PYTHONPATH (no pip install needed). The runner lives in the monorepo at
# src/bac_panaroo/pangenomerge/pangenomerge-runner.py — it's a tiny
# `from pangenomerge.__main__ import main; main()` wrapper. PANGENOME_MERGE_ROOT
# should track upstream `dev` (see src/bac_panaroo/pangenomerge/README.md).
#
# Usage:
#   sbatch src/bac_panaroo/slurm_scripts/pangenomerge_merge.sh \
#     --component-graphs /path/to/component_graphs.tsv \
#     --outdir /path/to/merge_out \
#     [--threads 16] [--extra-args '...']
#
# Env overrides (defaults below):
#   PANGENOME_MERGE_ROOT   default: /home/dca36/workspace/pangenome_merge
#   MONOREPO_ROOT          default: /home/dca36/workspace/BacHGT
#   THREADS                default: SLURM_CPUS_PER_TASK (16)
#   EXTRA_ARGS             default: ''   (forwarded to the pangenomerge CLI)

set -euo pipefail

: "${PANGENOME_MERGE_ROOT:=/home/dca36/workspace/pangenome_merge}"
: "${MONOREPO_ROOT:=/home/dca36/workspace/BacHGT}"
: "${COMPONENT_GRAPHS_TSV:=}"
: "${OUTDIR:=}"
: "${THREADS:=${SLURM_CPUS_PER_TASK:-16}}"
: "${EXTRA_ARGS:=}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --component-graphs)
      COMPONENT_GRAPHS_TSV="$2"
      shift 2
      ;;
    --outdir)
      OUTDIR="$2"
      shift 2
      ;;
    --threads)
      THREADS="$2"
      shift 2
      ;;
    --extra-args)
      EXTRA_ARGS="$2"
      shift 2
      ;;
    *)
      echo "Warning: ignoring unknown argument $1" >&2
      shift
      ;;
  esac
done

if [[ -z "$COMPONENT_GRAPHS_TSV" ]]; then
  echo "ERROR: --component-graphs <path.tsv> is required (one Panaroo output dir per line)" >&2
  exit 1
fi
if [[ -z "$OUTDIR" ]]; then
  echo "ERROR: --outdir <path> is required (merge output directory)" >&2
  exit 1
fi
if [[ ! -f "$COMPONENT_GRAPHS_TSV" ]]; then
  echo "ERROR: component graphs TSV not found: $COMPONENT_GRAPHS_TSV" >&2
  exit 1
fi

RUNNER="${MONOREPO_ROOT}/src/bac_panaroo/pangenomerge/pangenomerge-runner.py"
if [[ ! -f "$RUNNER" ]]; then
  echo "ERROR: monorepo runner not found: $RUNNER" >&2
  exit 1
fi

mkdir -p "$OUTDIR"
mkdir -p "$PANGENOME_MERGE_ROOT/logs"

export PYTHONUNBUFFERED=1
echo "========================================================================"
echo "pangenomerge merge"
echo "  COMPONENT_GRAPHS_TSV=${COMPONENT_GRAPHS_TSV}"
echo "  OUTDIR=${OUTDIR}"
echo "  THREADS=${THREADS}"
echo "  PANGENOME_MERGE_ROOT=${PANGENOME_MERGE_ROOT}"
echo "  RUNNER=${RUNNER}"
echo "Job ID: ${SLURM_JOB_ID:-local}    Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "CPUs (Slurm): ${SLURM_CPUS_PER_TASK:-n/a}"
echo "========================================================================"
echo ""

if command -v micromamba &>/dev/null; then
  eval "$(micromamba shell hook --shell bash)"
  micromamba activate pangenomerge
else
  echo "ERROR: micromamba not found on PATH" >&2
  exit 1
fi

cd "$PANGENOME_MERGE_ROOT"
export PYTHONPATH=".:pangenomerge"

if [[ -n "${SLURM_TMPDIR:-}" ]]; then
  export TMPDIR="${SLURM_TMPDIR}/pangenomerge_${SLURM_JOB_ID:-$$}"
  mkdir -p "$TMPDIR"
fi

set -x
python3 "$RUNNER" \
  --component-graphs "$COMPONENT_GRAPHS_TSV" \
  --outdir "$OUTDIR" \
  --threads "$THREADS" \
  ${EXTRA_ARGS}
set +x

echo ""
echo "========================================================================"
echo "Merge complete: ${OUTDIR}"
echo "  -> next: sbatch src/bac_panaroo/slurm_scripts/pangenomerge_postprocess.sh \$(basename ${OUTDIR})"
echo "========================================================================"
