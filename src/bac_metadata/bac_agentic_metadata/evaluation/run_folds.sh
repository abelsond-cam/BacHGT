#!/bin/bash
# Benchmark a curated fold end-to-end: run the engine driver (every curation stage, in-process, via
# run_klebsiella.sh) THEN the evaluation layer that scores agent-vs-manual — find + grading adjudication,
# value fidelity, cumulative completeness, and the agent-vs-manual scorecard. Together these reproduce the
# retired run_pipeline.sh: the driver replaced the curation stages; this adds the gold-comparison stages the
# driver deliberately omits (it curates; it does not score).
#
#   bash evaluation/run_folds.sh "train,val" train curated   # dress rehearsal (curated links — the gate source)
#   bash evaluation/run_folds.sh "test"      test  finder    # sealed test, production paper source
set -uo pipefail
FOLD="${1:-train,val}"
TAG="${2:-train}"
PAPER_SOURCE="${3:-curated}"
REPO=/Users/davidabelson/developer/BacHGT
APP="$REPO/src/bac_metadata/bac_agentic_metadata/applications/klebsiella"
EVAL="$REPO/src/bac_metadata/bac_agentic_metadata/evaluation"
DATA="$APP/data"
if [ -z "${BACHGT_PROJECT_K_ROOT:-}" ]; then
  BACHGT_PROJECT_K_ROOT="/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k"
fi
export BACHGT_PROJECT_K_ROOT
export BACHGT_PROJECT_K_USER="${BACHGT_PROJECT_K_USER:-data}"
GOLD="${BACHGT_GOLD:-$BACHGT_PROJECT_K_ROOT/$BACHGT_PROJECT_K_USER/final/metadata/metadata_final_curated_all_samples_and_columns.tsv}"
cd "$REPO" || exit 1
unset VIRTUAL_ENV

# Per-tranche outputs live under run_progress/<tag>/<stage>/ (the RunPaths layout; the tag encodes the folder,
# so filenames drop the _<tag> suffix). Shared inputs (GOLD, splits) stay at the data root.
RP="$DATA/run_progress/$TAG"
FIND="$RP/find"; GRADE="$RP/grade"; WSB="$RP/backfill"; ESC="$RP/escalation"; PS="$RP/per_sample"; SC="$RP/scorecard"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
run() { echo; echo "### [$(ts)] $*"; uv run python "$@" || { echo "FAILED: $*"; exit 1; }; }

echo "=== run_folds: fold='$FOLD' tag='$TAG' paper-source='$PAPER_SOURCE' ==="

# ── Curation — the whole pipeline in-process (driver) ─────────────────────────────────────────────
echo; echo "### [$(ts)] driver (run_klebsiella.sh) — curation stages"
bash "$APP/run_klebsiella.sh" --fold "$FOLD" --tag "$TAG" --paper-source "$PAPER_SOURCE" \
    || { echo "FAILED: driver"; exit 1; }

# ── Evaluation — the gold-comparison stages the driver omits (find/grading adjudication + scorecard) ──
run "$EVAL/validate_find_papers.py" --found "$FIND/found_papers.tsv" --folds "$FOLD" --adjudicate --report-prefix "find"
run "$EVAL/validate_study_grading.py" --grades "$GRADE/study_grades.tsv" --folds "$FOLD" --adjudicate --report-prefix "grading"
run "$EVAL/validate_backfill_values.py" --applied "$WSB/backfill_applied.tsv" --truth "$GOLD" \
    --report-prefix "backfill_value" --out-dir "$WSB"
run "$EVAL/validate_backfill_values.py" --applied "$PS/per_sample_applied.tsv" --truth "$GOLD" \
    --report-prefix "per_sample_value" --out-dir "$PS"
run "$EVAL/validate_backfill_completeness.py" --fold "$FOLD" --backfill "$WSB/backfill_applied.tsv" \
    --per-sample "$PS/per_sample_applied.tsv" --escalation "$ESC/escalation_applied.tsv" \
    --truth "$GOLD" --report-prefix "backfill_completeness" --out-dir "$SC"
run "$EVAL/summarise_agent_vs_manual.py" --grades "$GRADE/study_grades.tsv" \
    --find-validation "$FIND/find_validation_report.tsv" \
    --find-adjudication "$FIND/find_adjudication_report.tsv" \
    --grading-adjudication "$GRADE/grading_adjudication_report.tsv" --prefix "$TAG" --out-dir "$SC"

echo; echo "=== [$(ts)] RUN_FOLDS COMPLETE ($FOLD / $TAG) ==="
echo "scorecard:  $SC/agent_vs_manual.md  +  $SC/backfill_completeness_report.md"
echo "run-health: $RP/run_health/report.md  (written by the driver)"
