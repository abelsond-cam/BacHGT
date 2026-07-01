#!/bin/bash
# Thin Klebsiella wrapper over the unified engine driver (engine/run_full_metadata_agent.py).
# Injects the four application inputs (spec / table / data-dir / snapshot) plus the curated split & sizing,
# sets the local OneDrive data-mirror env, and forwards ALL remaining args to the driver — so every driver
# flag works unchanged: selection (--fold/--tag OR --min-study-size/--tag), --paper-source, --carry-forward,
# --web-fallback, --backend, --limit, --skip-escalation, … The driver runs every curation stage in-process.
# Replaces the retired run_pipeline.sh. (The gold-comparison scorecard layer is evaluation/run_folds.sh.)
#
#   bash run_klebsiella.sh --fold train,val --tag train --paper-source curated       # a curated fold
#   bash run_klebsiella.sh --min-study-size 100 --tag tail100 --web-fallback --carry-forward   # the tail
set -uo pipefail
REPO=/Users/davidabelson/developer/BacHGT
APP="$REPO/src/bac_metadata/bac_agentic_metadata/applications/klebsiella"
DRIVER="$REPO/src/bac_metadata/bac_agentic_metadata/engine/run_full_metadata_agent.py"
DATA="$APP/data"
# Local OneDrive mirror of the raw ENA + curated gold (override via env on another machine).
# (plain assignment, not ${:-default}, because the default path contains an apostrophe)
if [ -z "${BACHGT_PROJECT_K_ROOT:-}" ]; then
  BACHGT_PROJECT_K_ROOT="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k"
fi
export BACHGT_PROJECT_K_ROOT
export BACHGT_PROJECT_K_USER="${BACHGT_PROJECT_K_USER:-data}"
cd "$REPO" || exit 1
unset VIRTUAL_ENV

exec uv run python "$DRIVER" \
  --spec "$APP/attributes.yaml" \
  --table "$DATA/inputs/base_table.csv" \
  --data-dir "$DATA" \
  --splits "$DATA/fold_splits/project_splits.tsv" \
  --sizing "$DATA/ena_assessment/ena_sizing.tsv" \
  --snapshot "$DATA/inputs/study_level_metadata_all_combined_v1.0_20260105.csv" \
  "$@"
