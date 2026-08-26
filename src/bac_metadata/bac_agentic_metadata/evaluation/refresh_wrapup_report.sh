#!/bin/bash
# Regenerate the Klebsiella wrap-up report end-to-end from the committed run artifacts.
#
# Read-only w.r.t. the pipeline (no curation re-run, no LLM) — it recomputes the three report
# inputs from the existing per-tranche artifacts + the v2 gold, so every figure in
# data/Kp_AGENTIC_METADATA_WRAPUP_REPORT.md is reproducible from one command:
#   1. completeness_by_split      → scorecard/final_completeness_raw_agent_gold.{md,tsv}   (§4)
#   2. validate_backfill_values   → run_progress/<tag>/scorecard/per_sample_value_report.* (§5b/§5c;
#      carries the blank-fill vs gated-overwrite split)
#   3. wrapup_report              → data/Kp_AGENTIC_METADATA_WRAPUP_REPORT.md
#
# Requires the v2 gold (metadata_v2). Override GOLD to point at a local copy when HPC is down.
#
#   bash src/bac_metadata/bac_agentic_metadata/evaluation/refresh_wrapup_report.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

: "${BACHGT_PROJECT_K_ROOT:?set BACHGT_PROJECT_K_ROOT (project_k data root)}"
: "${BACHGT_PROJECT_K_USER:=data}"
GOLD="${BACHGT_GOLD:-$BACHGT_PROJECT_K_ROOT/$BACHGT_PROJECT_K_USER/final/metadata/metadata_final_curated_all_samples_and_columns.tsv}"
[ -f "$GOLD" ] || { echo "gold not found: $GOLD" >&2; exit 1; }

M=bac_metadata.bac_agentic_metadata.evaluation
RP=src/bac_metadata/bac_agentic_metadata/applications/klebsiella/data/run_progress
TAGS="train test tail100 tail50_99 tail25_49 tail10_24 sub10"

echo "### 1/3 completeness_by_split (§4) ###"
uv run python -m $M.completeness_by_split --truth "$GOLD"

echo "### 2/3 per-tranche value reports (§5b/§5c) ###"
for tag in $TAGS; do
  uv run python -m $M.validate_backfill_values \
    --applied "$RP/$tag/per_sample/per_sample_applied.tsv" --truth "$GOLD" \
    --report-prefix per_sample_value --out-dir "$RP/$tag/scorecard" 2>/dev/null \
    && echo "  $tag ✓" || echo "  $tag — no per_sample_applied (skipped)"
done

echo "### 3/3 wrapup_report ###"
uv run python -m $M.wrapup_report
echo "=== Kp_AGENTIC_METADATA_WRAPUP_REPORT.md refreshed ==="
