#!/usr/bin/env bash
# Stage 1: build the group work-list from the SL-level Panaroo runs, ensure the shared snippy
# reference is staged, and resolve each group Sample -> raw snippy VCF.
# Writes this subproject's resolution TSV (Sample, source, run_accession, vcf_path) that the
# extract array chunks over.
# Run: sbatch src/bac_phylogeny/slurm_scripts/setup_and_resolve.sh
# Pre-req (once): cd src/bac_phylogeny && pixi install     # provides samtools

#SBATCH --job-name=phylo_setup_resolve
#SBATCH --output=phylo_setup_resolve_%j.out
#SBATCH --error=phylo_setup_resolve_%j.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU

set -euo pipefail
cd /home/dca36/workspace/BacHGT
export PYTHONUNBUFFERED=1

# --- paths ------------------------------------------------------------------
DATA="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david"
PHYLO="/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/klebsiella/phylogeny"   # snippy VCF trees + ref
RUN_ROOT="${DATA}/processed/panaroo_with_reference_genome"                     # the SL-level GPA runs
# Shared, cohort-agnostic variant-extraction assets (reused, extract-once across cohorts):
SHARED="${DATA}/processed/pyseer_iso_source"
REF="${SHARED}/ref/ref.fa"
# This subproject's own outputs:
WORK="${DATA}/processed/phylogeny_variant_structure"
GROUPS_DIR="${WORK}/groups"
UNION_CSV="${GROUPS_DIR}/union_samples.csv"
RESOLUTION_TSV="${WORK}/snippy_resolution.tsv"
SAMTOOLS="${PWD}/src/bac_phylogeny/.pixi/envs/default/bin/samtools"
# ---------------------------------------------------------------------------

mkdir -p "${GROUPS_DIR}" "${SHARED}/ref"

# 0) Group work-list from the SL-level Panaroo runs (^SL selects KP-sublineage runs incl. parts;
#    excludes kp_rare_* and species_* runs). Inclusive: keeps any SL with >=50 samples outside
#    its largest Clonal Group (control SLs included; strict >=2-large-CG split is annotated only).
uv run python src/bac_phylogeny/gpa_run_groups.py \
    --run-root "${RUN_ROOT}" \
    --out-dir "${GROUPS_DIR}"

# 1) Reuse the shared snippy reference (NC_009648 / MGH 78578); stage + faidx only if absent.
if [ ! -s "${REF}" ]; then
    SRC_REF=$(find "${PHYLO}/snippy_ncbi" -maxdepth 2 -name ref.fa 2>/dev/null | head -1)
    echo "Staging reference from: ${SRC_REF}"
    cp "${SRC_REF}" "${REF}"
    "${SAMTOOLS}" faidx "${REF}"
fi
echo "Reference: ${REF}"

# 2) Resolve the union of qualifying-group Samples -> raw snippy VCF.
uv run python src/bac_phylogeny/resolve_snippy_paths.py \
    --sample-csv "${UNION_CSV}" \
    --out-tsv "${RESOLUTION_TSV}"

echo "Done. Resolution TSV: ${RESOLUTION_TSV}"
echo "Rows: $(($(wc -l < "${RESOLUTION_TSV}") - 1))"
