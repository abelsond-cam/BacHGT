#!/bin/bash
# Regenerate an application's wrap-up report end-to-end from its committed run artifacts.
#
# Read-only w.r.t. the pipeline (no curation re-run, no LLM) — it recomputes the report inputs from the
# existing per-tranche artifacts (+ the manual gold, where one exists), so every figure in the wrap-up is
# reproducible from one command. App-agnostic (driven by applications/<APP>/attributes.yaml):
#   1. completeness_by_split      -> scorecard/final_completeness_raw_agent_gold.{md,tsv}   (§4)
#   2. validate_backfill_values   -> run_progress/<tag>/scorecard/per_sample_value_report.* (§5b/§5c; gold only)
#   3. wrapup_report              -> data/<report.wrapup_out>
#
# Usage:
#   bash .../refresh_wrapup_report.sh                    # klebsiella (needs the v2 gold)
#   APP=m_abs bash .../refresh_wrapup_report.sh          # m_abs (goldless: raw -> agent, §5 omitted)
# Override TAGS / GOLD via env. klebsiella needs the v2 gold (BACHGT_PROJECT_K_ROOT or BACHGT_GOLD); a goldless
# app (m_abs) needs neither.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

APP="${APP:-klebsiella}"
M=bac_metadata.bac_agentic_metadata.evaluation
RP=src/bac_metadata/bac_agentic_metadata/applications/$APP/data/run_progress

if [ "$APP" = "klebsiella" ]; then
  TAGS="${TAGS:-train test tail100 tail50_99 tail25_49 tail10_24 sub10}"
  : "${BACHGT_PROJECT_K_ROOT:?set BACHGT_PROJECT_K_ROOT (project_k data root)}"
  : "${BACHGT_PROJECT_K_USER:=data}"
  GOLD="${BACHGT_GOLD:-$BACHGT_PROJECT_K_ROOT/$BACHGT_PROJECT_K_USER/final/metadata/metadata_final_curated_all_samples_and_columns.tsv}"
  [ -f "$GOLD" ] || { echo "gold not found: $GOLD" >&2; exit 1; }
else
  TAGS="${TAGS:-mabs_all}"
  GOLD="${BACHGT_GOLD:-}"   # goldless app -> raw->agent completeness, §5 omitted
fi

echo "### 1/3 completeness_by_split (§4) — app=$APP ###"
if [ -n "$GOLD" ]; then
  uv run python -m $M.completeness_by_split --app "$APP" --truth "$GOLD"
else
  uv run python -m $M.completeness_by_split --app "$APP"
fi

echo "### 2/3 per-tranche value reports (§5b/§5c) ###"
if [ -n "$GOLD" ]; then
  for tag in $TAGS; do
    uv run python -m $M.validate_backfill_values \
      --applied "$RP/$tag/per_sample/per_sample_applied.tsv" --truth "$GOLD" \
      --report-prefix per_sample_value --out-dir "$RP/$tag/scorecard" 2>/dev/null \
      && echo "  $tag ✓" || echo "  $tag — no per_sample_applied (skipped)"
  done
else
  echo "  (goldless app — value-accuracy reports skipped)"
fi

echo "### 3/3 wrapup_report ###"
uv run python -m $M.wrapup_report --app "$APP" --tags "$(echo "$TAGS" | tr ' ' ',')"
echo "=== $APP wrap-up report refreshed ==="
