#!/bin/bash
#SBATCH --job-name=pangenomerge_post
#SBATCH --output=/home/dca36/workspace/pangenome_merge/logs/postprocess/post_%j.out
#SBATCH --error=/home/dca36/workspace/pangenome_merge/logs/postprocess/post_%j.err
#SBATCH --partition=icelake-himem
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=4:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#
# pangenomerge_postprocess.sh
# ---------------------------
# Produce presence/absence outputs from a completed pangenomerge merge by
# calling `python -m pangenomerge.generate_output`. Adapted from the user's
# prior ~/workspace/pangenome_merge/pangenome_merge_generate_postmerge_output.sh.
#
# Activation pattern matches pangenomerge_merge.sh: the `pangenomerge`
# micromamba env carries only runtime deps; the pangenomerge package itself is
# imported from the source checkout via PYTHONPATH (no pip install step).
#
# Usage (positional arg = a name resolved under PANGENOME_MERGE_DATA_BASE,
# or a full path):
#   sbatch src/bac_panaroo/slurm_scripts/pangenomerge_postprocess.sh SL147
#   sbatch src/bac_panaroo/slurm_scripts/pangenomerge_postprocess.sh /path/to/.../pangenomerge/SL147
#
# Expects under the merge dir: pangenome_metadata.sqlite, final_graph.gml,
# component_graphs.tsv. Writes to <merge_dir>/postprocess/.

set -euo pipefail

: "${PANGENOME_MERGE_ROOT:=/home/dca36/workspace/pangenome_merge}"
: "${PANGENOME_MERGE_DATA_BASE:=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/pangenomerge}"
: "${SQLITE_CACHE_KB:=1048576}"

usage() {
  echo "Usage: $0 MERGE_DIR_OR_NAME" >&2
  echo "  full path to a pangenomerge merge dir, or a name appended to:" >&2
  echo "  ${PANGENOME_MERGE_DATA_BASE}/" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

SPEC="$1"
if [[ "$SPEC" == /* ]]; then
  MERGE_DIR="$SPEC"
else
  MERGE_DIR="${PANGENOME_MERGE_DATA_BASE}/${SPEC}"
fi

SQLITE="${MERGE_DIR}/pangenome_metadata.sqlite"
GML="${MERGE_DIR}/final_graph.gml"
COMPONENT_GRAPHS_TSV="${MERGE_DIR}/component_graphs.tsv"
POSTPROCESS_OUTDIR="${MERGE_DIR}/postprocess"

export PYTHONUNBUFFERED=1
echo "========================================================================"
echo "pangenomerge postprocess (presence/absence)"
echo "  MERGE_DIR=${MERGE_DIR}"
echo "  POSTPROCESS_OUTDIR=${POSTPROCESS_OUTDIR}"
echo "  SQLITE_CACHE_KB=${SQLITE_CACHE_KB}"
echo "Job ID: ${SLURM_JOB_ID:-local}    Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "========================================================================"
echo ""

for f in "$SQLITE" "$GML" "$COMPONENT_GRAPHS_TSV"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: required file not found: $f" >&2
    exit 1
  fi
done

mkdir -p "$POSTPROCESS_OUTDIR"
mkdir -p "$PANGENOME_MERGE_ROOT/logs/postprocess"

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
  export TMPDIR="${SLURM_TMPDIR}/pangenomerge_post_${SLURM_JOB_ID:-$$}"
  mkdir -p "$TMPDIR"
fi

set -x
python3 -m pangenomerge.generate_output \
  --sqlite "$SQLITE" \
  --gml "$GML" \
  --component-graphs "$COMPONENT_GRAPHS_TSV" \
  --outdir "$POSTPROCESS_OUTDIR" \
  --output presenceabsence \
  --sqlite-cache "$SQLITE_CACHE_KB"
set +x

echo ""
echo "========================================================================"
echo "Postprocess complete: ${POSTPROCESS_OUTDIR}"
echo "========================================================================"
