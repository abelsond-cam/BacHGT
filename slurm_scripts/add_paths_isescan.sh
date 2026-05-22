#!/usr/bin/env bash
# Build ISEScan CSV list, then add/overwrite isescan_file in metadata using
# the shared Python matcher used by add_paths_gff_fna_to_metadata.py.

set -euo pipefail

BASE=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw
ISESCAN_DIR="${BASE}/seb/ISEScan_results/csv_files"
METADATA_F="${BASE}/david/final/metadata_final_curated_slimmed.tsv"
ISESCAN_LIST_F="${BASE}/david/raw/isescan_csv.txt"

if [[ ! -d "${ISESCAN_DIR}" ]]; then
  echo "ISEScan directory not found: ${ISESCAN_DIR}" >&2
  exit 1
fi

if [[ ! -f "${METADATA_F}" ]]; then
  echo "Metadata file not found: ${METADATA_F}" >&2
  exit 1
fi

echo "Building ISEScan CSV list from ${ISESCAN_DIR}..."
find "${ISESCAN_DIR}" -maxdepth 1 -type f -name "*.csv" -print > "${ISESCAN_LIST_F}"
echo "Wrote $(wc -l < "${ISESCAN_LIST_F}") paths to ${ISESCAN_LIST_F}"

echo
echo "Running add_paths_gff_fna_to_metadata.py in ISEScan mode..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.." && uv run python -m bac_panaroo.pp.add_paths_gff_fna_to_metadata \
  --mode isescan \
  --isescan-list "${ISESCAN_LIST_F}" \
  "${METADATA_F}"

# Keep paths relative (e.g. seb/...) in metadata.
sed -i "s|${BASE}/||g" "${METADATA_F}"
echo "Stripped ${BASE}/ from paths in ${METADATA_F}"

echo "Done."
