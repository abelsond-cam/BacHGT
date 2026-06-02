#!/usr/bin/env bash
# Build the single assembly list file and the two GFF list files
# used by add_paths_gff_fna_to_metadata.py.
#
# - assemblies_file_list.txt: all assembly FASTA paths
# - ncbi_gff.txt: all NCBI GFF paths (non-recursive)
# - klebsiella_gff.txt: all Klebsiella GFF paths (non-recursive)

set -euo pipefail

BASE=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw

ASSEMBLIES_OUT="${BASE}/david/raw/assemblies_file_list.txt"
NCBI_GFF_DIR="${BASE}/david/raw/ncbi_gff3"
NCBI_GFF_OUT="${BASE}/david/raw/ncbi_gff.txt"
KLEB_GFF_DIR="${BASE}/david/raw/klebsiella_gff3"
KLEB_GFF_OUT="${BASE}/david/raw/klebsiella_gff.txt"

# Norway complete-genome downloads (norway_tables1_integrate.sh). New rows
# are is_refseq=True → add_paths routes them to the NCBI GFF dict, so the
# related_lr GFFs are appended to the NCBI list.
RELATED_LR_ASM_DIR="${BASE}/david/raw/related_lr/assemblies"
RELATED_LR_GFF_DIR="${BASE}/david/raw/related_lr/gff"

FULL_METADATA="${BASE}/david/final/metadata_final_curated_all_samples_and_columns.tsv"
SLIMMED_METADATA="${BASE}/david/final/metadata_final_curated_slimmed.tsv"

echo "Building assemblies_file_list.txt..."

# 1) assemblies_2: one line per compressed assembly (.gz) file in each
#    immediate subdir (overwrite). All assemblies (ncbi_*, NCTC, missing,
#    klebsiella_*, atb_*, etc.) now live as flat .fa.gz / .fna.gz files
#    directly under these subdirectories, so a simple *.gz match is enough.
: > "${ASSEMBLIES_OUT}"
for d in "${BASE}/seb/assemblies_2"/*; do
  if [[ -d "${d}" ]]; then
    ls "${d}"/*.gz 2>/dev/null >> "${ASSEMBLIES_OUT}" || true
  fi
done

# 2) atb_david/kpsc and non_kpsc: .fa and .fa.gz
ls "${BASE}/seb/assemblies/atb_david/kpsc"/*.fa* 2>/dev/null >> "${ASSEMBLIES_OUT}" || true
ls "${BASE}/seb/assemblies/atb_david/non_kpsc"/*.fa* 2>/dev/null >> "${ASSEMBLIES_OUT}" || true

# 3) ncbi_dataset/data: one subdir per sample, each has a .fna (or .fna.gz)
for d in "${BASE}/seb/assemblies_2/ncbi_03122025/ncbi_kpn/ncbi_dataset/data"/*; do
  if [[ -d "${d}" ]]; then
    ls "${d}"/*.fna* 2>/dev/null >> "${ASSEMBLIES_OUT}" || true
  fi
done

# 4) related_lr/assemblies: flat <GCA>.fna.gz genomes downloaded by
#    norway_tables1_integrate.sh for the Norway complete genomes.
ls "${RELATED_LR_ASM_DIR}"/*.gz 2>/dev/null >> "${ASSEMBLIES_OUT}" || true

echo "Wrote $(wc -l < "${ASSEMBLIES_OUT}") assembly paths to ${ASSEMBLIES_OUT}"

echo
echo "Building ncbi_gff.txt..."
find "${NCBI_GFF_DIR}" -maxdepth 1 -type f -name "*.gff*" -print > "${NCBI_GFF_OUT}"
# Norway complete-genome GFFs (is_refseq → NCBI dict). Appended, not
# overwriting the find above.
if [[ -d "${RELATED_LR_GFF_DIR}" ]]; then
  find "${RELATED_LR_GFF_DIR}" -maxdepth 1 -type f -name "*.gff*" -print >> "${NCBI_GFF_OUT}"
fi
echo "Wrote $(wc -l < "${NCBI_GFF_OUT}") NCBI GFF paths to ${NCBI_GFF_OUT}"

echo
echo "Building klebsiella_gff.txt..."
find "${KLEB_GFF_DIR}" -maxdepth 1 -type f -name "*.gff*" -print > "${KLEB_GFF_OUT}"
echo "Wrote $(wc -l < "${KLEB_GFF_OUT}") Klebsiella GFF paths to ${KLEB_GFF_OUT}"

echo
echo "Running add_paths_gff_fna_to_metadata.py on the FULL TSV (parse path"
echo "lists, write TSVs, add sr_assembly_file/sr_gff_file to the canonical metadata)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/../../.."
uv run python -m bac_metadata.pp.add_paths_gff_fna_to_metadata "${FULL_METADATA}"

# The slimmed TSV is a column subset of the augmented full TSV: derive it
# (kept = current slimmed header ∪ sr_assembly_file,sr_gff_file). Backs the
# previous slimmed up to a timestamped <stem>.bak.<UTC>.tsv first.
echo
echo "Deriving slimmed TSV from full (slim_metadata)..."
uv run python -m bac_metadata.pp.slim_metadata \
  --full "${FULL_METADATA}" \
  --slimmed "${SLIMMED_METADATA}"

# Having saved full paths in the data, strip the base path from BOTH files.
for METADATA_F in "${FULL_METADATA}" "${SLIMMED_METADATA}"; do
  if [[ -f "${METADATA_F}" ]]; then
    sed -i "s|${BASE}/||g" "${METADATA_F}"
    echo "Stripped ${BASE}/ from paths in ${METADATA_F}"
  else
    echo "Metadata file not found: ${METADATA_F}" >&2
  fi
done

echo
echo "Done."

