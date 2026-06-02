#!/usr/bin/env bash
# Rebuild metadata_v2 + cascade all dependent steps in canonical order.
#
# The rule: any change to v2 means re-running the downstream cascades
# (they're all idempotent — safe to re-run). This script encodes the order
# so you don't have to remember.
#
# Steps:
#   1. build_metadata_v2              fresh from v1 → v2 (DESTRUCTIVE)
#   2. merge_norway_pairs_into_v2     biosample-keyed Norway pair merge
#   3. merge_kleborate_into_v2        species → is_kpsc → kpsc_final_list
#   4. merge_isescan_into_v2          per-genome IS-family counts
#   5. import_sr_kleborate            concat seb/kleborate_v3.2.4 batches → sidecar
#   6. import_sr_isescan              concat seb/ISEScan_results/csv_files → sidecar
#   7. build_sr_shadow_for_lra        SR-side snapshot for paired rows (consumes sidecars)
#   8. add_paths_gff_fna_to_metadata  fill lr_gff_file (+ lr_assembly_file where empty)
#                                     from the related_lr/{assemblies,gff} pools (--mode lra)
#   9. merge_predicted_and_ebi_ast    Bacformer-predicted + EBI-ground-truth AST columns
#                                     (BacPredict workstream — see README §12)
#
# Each merge step backs up v2 with a UTC-stamped .bak.*.tsv before
# overwriting; safe to re-run.
#
# Usage:
#   ./rebuild_v2.sh                  # full rebuild from v1
#   ./rebuild_v2.sh --skip-g1        # keep existing v2; re-run steps 2-8
#   ./rebuild_v2.sh --skip-isescan   # skip step 4 (e.g. when ISEScan array
#                                    # hasn't completed yet)
#   ./rebuild_v2.sh --skip-sr-import # skip steps 5-6 (use existing sidecars)
#   ./rebuild_v2.sh --skip-predicted-ast  # skip step 9 (no BacPredict parquets yet)
#   ./rebuild_v2.sh --skip-g1 --skip-isescan --skip-sr-import
#
# All steps run on the login node (no Slurm). Total runtime: ~2-5 min
# depending on which steps are included.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SKIP_G1=0
SKIP_ISESCAN=0
SKIP_SR_IMPORT=0
SKIP_PREDICTED_AST=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-g1)            SKIP_G1=1;            shift ;;
        --skip-isescan)       SKIP_ISESCAN=1;       shift ;;
        --skip-sr-import)     SKIP_SR_IMPORT=1;     shift ;;
        --skip-predicted-ast) SKIP_PREDICTED_AST=1; shift ;;
        -h|--help)
            head -32 "$0" | sed 's/^# *//'
            exit 0
            ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
    esac
done

step() { echo ""; echo "=================================================================="; echo "$1"; echo "=================================================================="; }

if (( SKIP_G1 == 0 )); then
    step "Step 1/8: build_metadata_v2 (fresh from v1)"
    uv run python -m bac_metadata.pp.build_metadata_v2
fi

step "Step 2/8: merge_norway_pairs_into_v2"
uv run python -m bac_metadata.pp.merge_norway_pairs_into_v2

step "Step 3/8: merge_kleborate_into_metadata_v2"
uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2

if (( SKIP_ISESCAN == 0 )); then
    step "Step 4/8: merge_isescan_into_metadata_v2"
    uv run python -m bac_metadata.pp.merge_isescan_into_metadata_v2
else
    step "Step 4/8: merge_isescan_into_metadata_v2  (SKIPPED via --skip-isescan)"
fi

if (( SKIP_SR_IMPORT == 0 )); then
    step "Step 5/8: import_sr_kleborate  (concat seb/kleborate_v3.2.4/ → sidecar)"
    uv run python -m bac_metadata.pp.import_sr_kleborate

    step "Step 6/8: import_sr_isescan    (collate seb/ISEScan_results/csv_files/ → sidecar)"
    uv run python -m bac_metadata.pp.import_sr_isescan
else
    step "Steps 5-6/8: import_sr_kleborate + import_sr_isescan  (SKIPPED via --skip-sr-import)"
fi

step "Step 7/8: build_sr_shadow_for_lra  (consumes both sidecars)"
uv run python -m bac_metadata.pp.build_sr_shadow_for_lra

step "Step 8/9: add_paths_gff_fna_to_metadata --mode lra  (fill lr_gff_file from related_lr pools)"
uv run python -m bac_metadata.pp.add_paths_gff_fna_to_metadata --mode lra

if (( SKIP_PREDICTED_AST == 0 )); then
    step "Step 9/9: merge_predicted_and_ebi_ast_into_metadata_v2  (BacPredict AMR predictions + EBI truth)"
    uv run python -m bac_metadata.pp.merge_predicted_and_ebi_ast_into_metadata_v2
else
    step "Step 9/9: merge_predicted_and_ebi_ast_into_metadata_v2  (SKIPPED via --skip-predicted-ast)"
fi

step "DONE"
