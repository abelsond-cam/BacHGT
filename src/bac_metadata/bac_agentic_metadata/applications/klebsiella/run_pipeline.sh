#!/bin/bash
# End-to-end agentic-metadata pipeline for one fold set, writing <TAG>-suffixed artifacts so a run
# never clobbers another fold's outputs. The SAME command does the train+val dress rehearsal and the
# sealed test-fold one-shot:
#   bash run_pipeline.sh "train,val" train      # dress rehearsal (cache-warm → fast/cheap)
#   bash run_pipeline.sh "test"      test       # the sealed final run (open the test fold once)
#
# Stage 1 sizing is fold-agnostic (run once already → stage1_sizing.tsv); this driver runs the
# fold-specific stages: grade → find → adjudicate(find+grading) → backfill(whole-field) →
# method-b(per-sample) → value-correctness → agent-vs-manual scorecard.
set -uo pipefail
FOLD="${1:-train,val}"
TAG="${2:-train}"
REPO=/Users/davidabelson/developer/BacHGT
APP="$REPO/src/bac_metadata/bac_agentic_metadata/applications/klebsiella"
DATA="$APP/data"
# Local OneDrive mirror of the raw ENA + the curated gold (override via env on another machine).
# (plain assignment, not ${:-default}, because the default path contains an apostrophe)
if [ -z "${BACHGT_PROJECT_K_ROOT:-}" ]; then
  BACHGT_PROJECT_K_ROOT="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k"
fi
export BACHGT_PROJECT_K_ROOT
export BACHGT_PROJECT_K_USER="${BACHGT_PROJECT_K_USER:-data}"
GOLD="${BACHGT_GOLD:-$BACHGT_PROJECT_K_ROOT/$BACHGT_PROJECT_K_USER/final/metadata/metadata_final_curated_all_samples_and_columns.tsv}"
cd "$REPO" || exit 1
unset VIRTUAL_ENV

ts() { date '+%Y-%m-%d %H:%M:%S'; }
run() { echo; echo "### [$(ts)] $*"; uv run python "$@" || { echo "FAILED: $*"; exit 1; }; }

echo "=== pipeline: fold='$FOLD' tag='$TAG' ==="

# 1. grade the paper into the attributes.yaml schema
run "$APP/run_study_grading.py" --fold "$FOLD" --output-prefix "study_grades_$TAG"
# 2. find the describing paper (3-tier finder incl. web fallback)
run "$APP/run_find_papers.py" --fold "$FOLD" --web-fallback --output-prefix "found_papers_$TAG"
# 3. opposing-Opus adjudication of finder + grader disagreements
run "$APP/validate_find_papers.py" --found "$DATA/found_papers_$TAG.tsv" --adjudicate --report-prefix "find_$TAG"
run "$APP/validate_study_grading.py" --grades "$DATA/study_grades_$TAG.tsv" --adjudicate --report-prefix "grading_$TAG"
# 4. whole-field backfill (gate + study-wide fills)
run "$APP/run_backfill.py" --fold "$FOLD" --grades "$DATA/study_grades_$TAG.tsv" --output "$DATA/backfill_applied_$TAG.tsv"
# 5. method-b per-sample extraction from supplementary tables
run "$APP/run_methodb_extract.py" --fold "$FOLD" --found "$DATA/found_papers_$TAG.tsv" \
    --gate-report "$DATA/backfill_gate_report_$TAG.tsv" --output "$DATA/methodb_applied_$TAG.tsv"
# 6. value-correctness vs the curated gold (whole-field + method-b)
run "$APP/validate_backfill_values.py" --applied "$DATA/backfill_applied_$TAG.tsv" --truth "$GOLD" --report-prefix "backfill_value_$TAG"
run "$APP/validate_backfill_values.py" --applied "$DATA/methodb_applied_$TAG.tsv" --truth "$GOLD" --report-prefix "methodb_value_$TAG"
# 6b. completeness vs the curated gold (baseline ENA / agent / v2, per field)
run "$APP/validate_backfill_completeness.py" --fold "$FOLD" --backfill "$DATA/backfill_applied_$TAG.tsv" \
    --methodb "$DATA/methodb_applied_$TAG.tsv" --truth "$GOLD" --report-prefix "backfill_completeness_$TAG"
# 7. the gold answer: agent-vs-manual agreement + adjudicated accuracy (finding + grading)
run "$APP/summarise_agent_vs_manual.py" --grades "$DATA/study_grades_$TAG.tsv" \
    --find-validation "$DATA/find_${TAG}_validation_report.tsv" \
    --find-adjudication "$DATA/find_${TAG}_adjudication_report.tsv" \
    --grading-adjudication "$DATA/grading_${TAG}_adjudication_report.tsv" --prefix "$TAG"

echo; echo "=== [$(ts)] PIPELINE COMPLETE ($FOLD / $TAG) ==="
echo "scorecard: $DATA/agent_vs_manual_$TAG.md ; backfill: $DATA/{backfill,methodb}_value_${TAG}_report.md"
