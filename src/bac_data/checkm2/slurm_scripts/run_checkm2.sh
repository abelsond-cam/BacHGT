#!/usr/bin/env bash
# Run CheckM2 against the LRA cohort (LR-GCAs + is_refseq, ~6,200 assemblies).
#
# Prereqs (one-time, see src/bac_data/checkm2/README.md):
#   1. pixi install at src/bac_data/checkm2/
#   2. CheckM2 DB downloaded to /home/dca36/rds/.../david/raw/CheckM2/Zenodo_db
#   3. python -m bac_data.checkm2.prep_checkm2_inputs (symlinks all FASTAs into one dir)
#
# Submit with:
#   sbatch src/bac_data/checkm2/slurm_scripts/run_checkm2.sh

#SBATCH --job-name=checkm2_lra
#SBATCH --partition=icelake-himem
#SBATCH --account=FLOTO-SL3-CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

set -euo pipefail

REPO_DIR=${REPO_DIR:-$HOME/workspace/BacHGT}
PIXI_DIR="$REPO_DIR/src/bac_data/checkm2"
RDS=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
INPUT_DIR="$RDS/david/processed/checkm2_lra/links"
OUTPUT_DIR="$RDS/david/processed/checkm2_lra/checkm2_out"
DB_PATH="$RDS/david/raw/CheckM2/Zenodo_db"

echo "[$(date -Is)] host=$(hostname)  cpus=${SLURM_CPUS_PER_TASK:-?}"
echo "[$(date -Is)] inputs:  $INPUT_DIR"
echo "[$(date -Is)] outputs: $OUTPUT_DIR"
echo "[$(date -Is)] DB:      $DB_PATH"

if [[ ! -d "$INPUT_DIR" ]]; then
    echo "FATAL: $INPUT_DIR not found — run prep_checkm2_inputs first" >&2
    exit 2
fi
N_LINKS=$(ls "$INPUT_DIR" | wc -l)
echo "[$(date -Is)] $N_LINKS symlinks queued"

mkdir -p "$OUTPUT_DIR"

# Tell CheckM2 where the DB lives (checkm2 reads CHECKM2DB if --database_path is omitted).
export CHECKM2DB="$DB_PATH"

cd "$PIXI_DIR"
pixi run checkm2 predict \
    --threads "${SLURM_CPUS_PER_TASK:-8}" \
    --input "$INPUT_DIR" \
    -x fna.gz \
    --output-directory "$OUTPUT_DIR" \
    --database_path "$DB_PATH" \
    --force        # overwrite previous run; CheckM2 is fast enough

# Hoist the headline TSV to a stable name beside it.
cp -f "$OUTPUT_DIR/quality_report.tsv" "$RDS/david/processed/checkm2_lra/quality_report.tsv"
echo "[$(date -Is)] DONE → $RDS/david/processed/checkm2_lra/quality_report.tsv"
