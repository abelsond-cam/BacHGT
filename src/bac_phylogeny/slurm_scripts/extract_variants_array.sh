#!/usr/bin/env bash
# Stage 2: per-sample snippy re-filter -> shared <Sample>.loci.tsv.gz cache (job array).
# The cache is per-sample and idempotent (--skip-existing): it is the SAME shared cache the
# blood/faeces cohort already populated (~20.8k samples), so this only extracts the SL-run
# samples not yet cached. Re-running fills gaps; widen --array if a chunk runs long.
# Run: sbatch src/bac_phylogeny/slurm_scripts/extract_variants_array.sh
# Pre-req (once): cd src/bac_phylogeny && pixi install     # provides bcftools

#SBATCH --job-name=phylo_extract
#SBATCH --output=phylo_extract_%A_%a.out
#SBATCH --error=phylo_extract_%A_%a.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=08:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --array=0-99

set -euo pipefail
cd /home/dca36/workspace/BacHGT
export PYTHONUNBUFFERED=1

# --- paths ------------------------------------------------------------------
DATA="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david"
SHARED="${DATA}/processed/pyseer_iso_source"          # shared, cohort-agnostic
REF="${SHARED}/ref/ref.fa"
CACHE_DIR="${SHARED}/locus_cache"                     # shared per-sample cache (extract-once)
WORK="${DATA}/processed/phylogeny_variant_structure"
RESOLUTION_TSV="${WORK}/snippy_resolution.tsv"
BCFTOOLS="${PWD}/src/bac_phylogeny/.pixi/envs/default/bin/bcftools"
# ---------------------------------------------------------------------------

# Chunk the resolution TSV across the array (mirror BacPredict's extract array).
TOTAL=$(($(wc -l < "${RESOLUTION_TSV}") - 1))
NTASKS=${SLURM_ARRAY_TASK_COUNT:-100}
CHUNK=$(( TOTAL / NTASKS + 1 ))
START=$(( SLURM_ARRAY_TASK_ID * CHUNK ))
END=$(( (SLURM_ARRAY_TASK_ID + 1) * CHUNK ))
if [ "${END}" -gt "${TOTAL}" ]; then END=${TOTAL}; fi
if [ "${START}" -ge "${TOTAL}" ]; then echo "task ${SLURM_ARRAY_TASK_ID}: nothing to do"; exit 0; fi

echo "task ${SLURM_ARRAY_TASK_ID}: rows [${START}:${END}) of ${TOTAL}; cache=${CACHE_DIR}"

uv run python src/bac_phylogeny/extract_sample_loci.py \
    --resolution-tsv "${RESOLUTION_TSV}" \
    --ref "${REF}" \
    --cache-dir "${CACHE_DIR}" \
    --start-idx "${START}" \
    --end-idx "${END}" \
    --min-qual 100 --min-dp 3 \
    --bcftools "${BCFTOOLS}" \
    --skip-existing
