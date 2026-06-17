#!/usr/bin/env bash
# Stage 4: per-group variant UMAP + Leiden (one array task per qualifying SL group).
# Each task rebuilds the within-group variant matrix from the shared cache and runs the
# GPA-matched scanpy neighbors(jaccard)/umap/leiden, persisting coords + labels + plots.
# Run: sbatch src/bac_phylogeny/slurm_scripts/sublineage_variant_umap_array.sh
# Size --array to cover the rows in groups/groups.tsv (~30-42 SL groups; tasks past the end exit 0).

#SBATCH --job-name=phylo_variant_umap
#SBATCH --output=phylo_variant_umap_%A_%a.out
#SBATCH --error=phylo_variant_umap_%A_%a.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --array=0-49

set -euo pipefail
cd /home/dca36/workspace/BacHGT
export PYTHONUNBUFFERED=1

# --- paths ------------------------------------------------------------------
DATA="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david"
SHARED="${DATA}/processed/pyseer_iso_source"          # shared per-sample cache
CACHE_DIR="${SHARED}/locus_cache"
WORK="${DATA}/processed/phylogeny_variant_structure"
GROUPS_TSV="${WORK}/groups/groups.tsv"
GROUP_SAMPLES_TSV="${WORK}/groups/group_samples.tsv"
METADATA="${DATA}/final/metadata_v2_all_samples_and_columns.tsv"
OUT_DIR="${WORK}/variant_umap"
WORKERS="${SLURM_CPUS_PER_TASK:-8}"
# ---------------------------------------------------------------------------

# Pick this task's group = row (SLURM_ARRAY_TASK_ID + 1) of groups.tsv, skipping the header.
ROW=$(( SLURM_ARRAY_TASK_ID + 2 ))
GROUP=$(awk -F'\t' -v r="${ROW}" 'NR==r{print $1}' "${GROUPS_TSV}")
if [ -z "${GROUP}" ]; then echo "task ${SLURM_ARRAY_TASK_ID}: no group at row ${ROW}; exiting"; exit 0; fi

echo "task ${SLURM_ARRAY_TASK_ID}: group=${GROUP}"

uv run python src/bac_phylogeny/sublineage_variant_umap.py \
    --group "${GROUP}" \
    --group-samples-tsv "${GROUP_SAMPLES_TSV}" \
    --cache-dir "${CACHE_DIR}" \
    --metadata "${METADATA}" \
    --out-dir "${OUT_DIR}" \
    --min-freq 0.001 \
    --n-jobs "${WORKERS}"
