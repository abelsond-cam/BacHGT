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
#   5. build_sr_shadow_for_lra        SR-side snapshot for paired rows
#
# Each merge step backs up v2 with a UTC-stamped .bak.*.tsv before
# overwriting; safe to re-run.
#
# Usage:
#   ./rebuild_v2.sh                  # full rebuild from v1
#   ./rebuild_v2.sh --skip-g1        # keep existing v2; re-run steps 2-5
#   ./rebuild_v2.sh --skip-isescan   # skip step 4 (e.g. when ISEScan array
#                                    # hasn't completed yet)
#   ./rebuild_v2.sh --skip-g1 --skip-isescan
#
# All steps run on the login node (no Slurm). Total runtime: ~2-5 min
# depending on which steps are included.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SKIP_G1=0
SKIP_ISESCAN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-g1)      SKIP_G1=1;      shift ;;
        --skip-isescan) SKIP_ISESCAN=1; shift ;;
        -h|--help)
            head -30 "$0" | sed 's/^# *//'
            exit 0
            ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
    esac
done

step() { echo ""; echo "=================================================================="; echo "$1"; echo "=================================================================="; }

if (( SKIP_G1 == 0 )); then
    step "Step 1/5: build_metadata_v2 (fresh from v1)"
    uv run python -m bac_metadata.pp.build_metadata_v2
fi

step "Step 2/5: merge_norway_pairs_into_v2"
uv run python -m bac_metadata.pp.merge_norway_pairs_into_v2

step "Step 3/5: merge_kleborate_into_metadata_v2"
uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2

if (( SKIP_ISESCAN == 0 )); then
    step "Step 4/5: merge_isescan_into_metadata_v2"
    uv run python -m bac_metadata.pp.merge_isescan_into_metadata_v2
else
    step "Step 4/5: merge_isescan_into_metadata_v2  (SKIPPED via --skip-isescan)"
fi

step "Step 5/5: build_sr_shadow_for_lra"
uv run python -m bac_metadata.pp.build_sr_shadow_for_lra

step "DONE"
