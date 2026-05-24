#!/bin/bash
#SBATCH --job-name=norway_tables1_integrate
#SBATCH --output=norway_tables1_integrate_%j.out
#SBATCH --error=norway_tables1_integrate_%j.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU
#SBATCH --mem=32G
#
# norway_tables1_integrate.sh
# ---------------------------
# Integrate the Norway KPSC paper's Table S1 into the curated metadata and
# download the resolved GenBank complete genomes + GFFs.
#
# What it does (one full E-utilities run, FULL TSV only):
#   1. Resolves every Table S1 strain to its GenBank GCA assembly via NCBI
#      E-utilities (elink/esummary).
#   2. --augment --write-back: backs up
#      metadata_final_curated_all_samples_and_columns.tsv to a timestamped
#      <stem>.bak.<UTC>.tsv next to it, then overwrites it in place with the
#      383 new GCA rows + 151 flagged is_refseq rows.
#   3. --download: fetches each resolved GCA's GenBank genome + GFF via the
#      NCBI Datasets CLI into david/raw/related_lr/{assemblies,gff}/ as
#      <GCA>.fna.gz / <GCA>.gff, and prints a download confirmation summary
#      (genomes ok / GFFs ok / explicit list of GCAs with no GFF).
#
# The slimmed TSV is NOT touched here — it is regenerated as a column
# subset of the augmented full TSV by add_paths_gff_fna_to_metadata.sh
# (which runs slim_metadata afterwards).
#
# Prerequisites:
#   - Table S1 workbook present at
#     ${BASE}/david/raw/Norway_Complete_Genomes_Fig1.xlsx (rsync'd separately;
#     it is a data file, not in git).
#   - ncbi-datasets micromamba env (provides the `datasets` CLI):
#       micromamba create -n ncbi-datasets -y
#       micromamba install -n ncbi-datasets -c bioconda -c conda-forge ncbi-datasets-cli -y
#   - Optional: export NCBI_API_KEY before sbatch to lift the E-utilities
#     rate limit from 3 to 10 req/s (the script honours it automatically).
#
# Usage:
#   sbatch src/bac_data/lr_data/slurm_scripts/norway_tables1_integrate.sh
#   bash   src/bac_data/lr_data/slurm_scripts/norway_tables1_integrate.sh
#
set -euo pipefail

cd /home/dca36/workspace/BacHGT

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# ---------------- User-editable settings ----------------
BASE=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
TABLE_S1="${BASE}/david/raw/Norway_Complete_Genomes_Fig1.xlsx"
FULL_METADATA="${BASE}/david/final/metadata_final_curated_all_samples_and_columns.tsv"
ASSEMBLIES_DIR="${BASE}/david/raw/related_lr/assemblies"
GFF_DIR="${BASE}/david/raw/related_lr/gff"
DATASETS_CMD="micromamba run -n ncbi-datasets datasets"
WORKERS=4
# -------------------------------------------------------

echo "========================================================================"
echo "Norway Table S1 integration + GenBank genome/GFF download"
echo "Job ID: ${SLURM_JOB_ID:-local}   Node: ${SLURMD_NODENAME:-$(hostname)}"
echo "Table S1     : ${TABLE_S1}"
echo "Full metadata: ${FULL_METADATA}"
echo "Assemblies → : ${ASSEMBLIES_DIR}"
echo "GFFs       → : ${GFF_DIR}"
if [[ -n "${NCBI_API_KEY:-}" ]]; then echo "NCBI_API_KEY : set (10 req/s)"; else echo "NCBI_API_KEY : unset (3 req/s)"; fi
echo "========================================================================"

if [[ ! -f "${TABLE_S1}" ]]; then
  echo "ERROR: Table S1 workbook not found: ${TABLE_S1}" >&2
  echo "       rsync it to the HPC first (it is a data file, not in git)." >&2
  exit 1
fi

mkdir -p "${ASSEMBLIES_DIR}" "${GFF_DIR}"

uv run python -u -m bac_data.lr_data.norway_tables1_integrate \
  --table-s1 "${TABLE_S1}" \
  --metadata "${FULL_METADATA}" \
  --workers "${WORKERS}" \
  --augment --write-back \
  --download \
  --assemblies-dir "${ASSEMBLIES_DIR}" \
  --gff-dir "${GFF_DIR}" \
  --datasets-cmd "${DATASETS_CMD}"

echo
echo "Done. Next: run src/bac_metadata/slurm_scripts/add_paths_gff_fna_to_metadata.sh to add"
echo "assembly_file/gff_file to the full TSV and regenerate the slimmed TSV."
