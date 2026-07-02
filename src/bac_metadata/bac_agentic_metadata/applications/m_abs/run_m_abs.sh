#!/bin/bash
# Thin *M. abscessus* wrapper over the unified engine driver (engine/run_full_metadata_agent.py) — the
# analogue of run_klebsiella.sh. Injects the three application inputs (spec / table / data-dir) and forwards
# ALL remaining args to the driver, so every driver flag works unchanged: selection
# (--min-study-size/--max-study-size + --tag, biggest-first; add --limit N for the top-N), --web-fallback,
# --backend, --carry-forward, --threshold, …
#
# M.abs differs from Klebsiella: NO curated snapshot and NO gold (so no --snapshot, --paper-source stays the
# default `finder`, and there is no gold-comparison scorecard). The rubric adds cf_status / smoking_status
# and an AST panel — the driver reads those from the spec and the per-sample extractor mines them.
#
# First exploratory pass — the 10 biggest studies (biggest-first), get data flowing to refine attributes.yaml:
#   bash run_m_abs.sh --min-study-size 1 --tag explore10 --limit 10 --web-fallback
# Then scale to all 133:
#   bash run_m_abs.sh --min-study-size 1 --tag all --web-fallback --carry-forward
set -uo pipefail
REPO=/Users/davidabelson/developer/BacHGT
APP="$REPO/src/bac_metadata/bac_agentic_metadata/applications/m_abs"
DRIVER="$REPO/src/bac_metadata/bac_agentic_metadata/engine/run_full_metadata_agent.py"
DATA="$APP/data"
cd "$REPO" || exit 1
unset VIRTUAL_ENV

# Build the base table on first run (fast; reads the committed xlsx) if it is missing.
if [ ! -f "$DATA/inputs/base_table.csv" ]; then
  echo "### base_table.csv missing — building from the ATB xlsx"
  uv run python "$APP/export_base_table.py" || { echo "FAILED: export_base_table"; exit 1; }
fi

exec uv run python "$DRIVER" \
  --spec "$APP/attributes.yaml" \
  --table "$DATA/inputs/base_table.csv" \
  --data-dir "$DATA" \
  "$@"
