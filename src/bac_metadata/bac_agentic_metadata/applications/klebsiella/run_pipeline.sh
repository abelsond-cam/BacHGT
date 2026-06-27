#!/bin/bash
# End-to-end agentic-metadata pipeline for one fold set, writing <TAG>-suffixed artifacts into the
# task-aligned data/ tree (find_papers / study_lv_attributes / sample_lv_attributes / scorecard).
# The SAME command does the train+val dress rehearsal and the sealed test-fold one-shot:
#   bash run_pipeline.sh "train,val" train      # dress rehearsal (cache-warm → fast/cheap)
#   bash run_pipeline.sh "test"      test        # the sealed final run (open the test fold once)
#
# Stages map to David's 9-step model (step refs in the comments). Stage 0 — ENA assessment
# (ena_sizing/ingest) — is fold-agnostic; run once via run_ena_assessment.py. This driver runs the
# fold-specific stages. Execution order follows data dependencies (whole-field gate → per-sample;
# per-sample → escalation), which the step refs annotate where they differ from David's numbering.
set -uo pipefail
FOLD="${1:-train,val}"
TAG="${2:-train}"
REPO=/Users/davidabelson/developer/BacHGT
APP="$REPO/src/bac_metadata/bac_agentic_metadata/applications/klebsiella"
EVAL="$REPO/src/bac_metadata/bac_agentic_metadata/evaluation"   # gold/manual-data validation layer
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

# Task-aligned subtrees.
FIND="$DATA/find_papers"
GRADE="$DATA/study_lv_attributes/grading"
WSB="$DATA/study_lv_attributes/whole_study_backfill"
ESC="$DATA/study_lv_attributes/escalation"
PS="$DATA/sample_lv_attributes/per_sample"
SCORE="$DATA/scorecard"
MANUAL_SUPP="$DATA/sample_lv_attributes/manual_download_supp"
mkdir -p "$FIND/manual_download" "$MANUAL_SUPP" "$GRADE" "$WSB" "$ESC" "$PS" "$SCORE" "$DATA/diagnostics" \
  "$DATA/cache/llm" "$DATA/cache/ena" "$DATA/cache/fulltext" "$DATA/cache/find" "$DATA/cache/per_sample_supp"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
run() { echo; echo "### [$(ts)] $*"; uv run python "$@" || { echo "FAILED: $*"; exit 1; }; }

echo "=== pipeline: fold='$FOLD' tag='$TAG' ==="

# ── Stage 1 — Find papers + resolve full text (David step 1) ────────────────────────────────────
run "$APP/run_find_papers.py" --fold "$FOLD" --web-fallback --output-prefix "found_papers_$TAG"

# ── Stage 2 — Adjudicate papers found (David step 2) ────────────────────────────────────────────
run "$EVAL/validate_find_papers.py" --found "$FIND/found_papers_$TAG.tsv" --folds "$FOLD" --adjudicate --report-prefix "find_$TAG"

# ── Stage 3 — Study grading + adjudication (David step 4) ───────────────────────────────────────
#    Grading falls back to data/find_papers/manual_download/<acc>.pdf for paywalled papers.
run "$APP/run_study_grading.py" --fold "$FOLD" --output-prefix "study_grades_$TAG"
run "$EVAL/validate_study_grading.py" --grades "$GRADE/study_grades_$TAG.tsv" --folds "$FOLD" --adjudicate --report-prefix "grading_$TAG"

# ── Stage 4 — Missing-papers worklist (David step 3, the loop) ──────────────────────────────────
#    Lists studies grading STILL lacks full text for. Human downloads them → link_local_papers.py →
#    manual_download/ → the NEXT run's grading picks them up (re-run after downloading).
run "$APP/report_missing_papers.py" --grades "$GRADE/study_grades_$TAG.jsonl" --found "$FIND/found_papers_$TAG.tsv"

# ── Stage 5 — Per-sample extraction FIRST (David step 5) ────────────────────────────────────────
#    The ACCURATE per-isolate source runs first, over EVERY ENA-incomplete (gated) study with a paper
#    (grade-independent gate). Whole-field is only the coarse fallback for what per-sample leaves.
run "$APP/run_per_sample_extract.py" --fold "$FOLD" --found "$FIND/found_papers_$TAG.tsv" \
    --output "$PS/per_sample_applied_$TAG.tsv"

# ── Stage 6 — Whole-field backfill (David step 6a) ──────────────────────────────────────────────
#    Study-wide fills for the gaps per-sample LEFT, with the parsimony guard (never overwrite a
#    per-isolate value; never whole-fill a per-sample-heterogeneous field). Writes the gate report.
run "$APP/run_backfill.py" --fold "$FOLD" --grades "$GRADE/study_grades_$TAG.tsv" \
    --per-sample "$PS/per_sample_applied_$TAG.tsv" --output "$WSB/backfill_applied_$TAG.tsv"

# ── Stage 6b — Per-sample supplementary worklist (manual_table_download) ─────────────────────────
#    LLM opinion per residual study: does the paper hold a per-isolate table? → FETCH_SUPP / SKIP / …
#    Read-only + LLM-cached; non-blocking (a worklist failure must not kill the run).
echo; echo "### [$(ts)] $APP/report_persample_supplements.py (manual-table worklist)"
uv run python "$APP/report_persample_supplements.py" --tag "$TAG" \
    || echo "WARN: per-sample supplement worklist failed (non-blocking)"

# ── Stage 7 — Escalation detect (David step 6b) ─────────────────────────────────────────────────
#    Tight whole-field near-misses → curator queue (whole-study / tightly-linked / diverse). Runs
#    AFTER per-sample so fields resolved per-sample drop out; the grader auto-skips genuinely-wide mixes.
echo; echo "### [$(ts)] $APP/run_escalations.py (detect)"
uv run python "$APP/run_escalations.py" --fold "$FOLD" --grades "$GRADE/study_grades_$TAG.jsonl" \
    --per-sample "$PS/per_sample_applied_$TAG.tsv" --output "$ESC/decisions_needed_$TAG.tsv" \
    || echo "WARN: escalation detect failed (non-blocking)"

# ── Stage 8 — Apply curator decisions (David step 7) ────────────────────────────────────────────
#    Apply only if the curator has filled the queue's 'answer' column between runs; else skip (non-blocking).
QUEUE="$ESC/decisions_needed_$TAG.tsv"
if [ -f "$QUEUE" ] && awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i=="answer") a=i; next} a && $a!="" {f=1} END{exit !f}' "$QUEUE"; then
    run "$APP/run_escalations.py" --apply --fold "$FOLD" --output "$QUEUE" \
        --applied-output "$ESC/escalation_applied_$TAG.tsv"
else
    echo "### [$(ts)] Stage 8 skip: $QUEUE has no filled answers yet (fill the 'answer' column + re-run to apply)."
fi
# David step 8 (loop): re-run this pipeline after editing attributes.yaml (David's call) to improve rules.

# ── Stage 9 — Outputs / scorecard (David step 9) ────────────────────────────────────────────────
#    Value-fidelity per method, cumulative completeness (incl. escalation), agent-vs-manual agreement.
run "$EVAL/validate_backfill_values.py" --applied "$WSB/backfill_applied_$TAG.tsv" --truth "$GOLD" \
    --report-prefix "backfill_value_$TAG" --out-dir "$WSB"
run "$EVAL/validate_backfill_values.py" --applied "$PS/per_sample_applied_$TAG.tsv" --truth "$GOLD" \
    --report-prefix "per_sample_value_$TAG" --out-dir "$PS"
run "$EVAL/validate_backfill_completeness.py" --fold "$FOLD" --backfill "$WSB/backfill_applied_$TAG.tsv" \
    --per-sample "$PS/per_sample_applied_$TAG.tsv" --escalation "$ESC/escalation_applied_$TAG.tsv" \
    --truth "$GOLD" --report-prefix "backfill_completeness_$TAG"
run "$EVAL/summarise_agent_vs_manual.py" --grades "$GRADE/study_grades_$TAG.tsv" \
    --find-validation "$FIND/find_${TAG}_validation_report.tsv" \
    --find-adjudication "$FIND/find_${TAG}_adjudication_report.tsv" \
    --grading-adjudication "$GRADE/grading_${TAG}_adjudication_report.tsv" --prefix "$TAG"

# ── Stage 10 — Run-health report (the convergence / closure artifact) ────────────────────────────
#    Aggregates every stage into a per-(study×field) grid + ALL-CLEAR vs N-actionable verdict. Loud,
#    never blocks (exit 0) — the single front-door artifact for "is the run healthy / curation done?".
echo; echo "### [$(ts)] $APP/report_run_health.py (run-health / convergence)"
uv run python "$APP/report_run_health.py" --fold "$FOLD" --tag "$TAG" \
    || echo "WARN: run-health report failed (non-blocking)"

echo; echo "=== [$(ts)] PIPELINE COMPLETE ($FOLD / $TAG) ==="
echo "run-health:   $SCORE/run_health_${TAG}_report.md   <- START HERE (verdict + actionable worklist)"
echo "scorecard:    $SCORE/agent_vs_manual_$TAG.md  +  $SCORE/backfill_completeness_${TAG}_report.md"
echo "manual-table: $DATA/sample_lv_attributes/persample_supplement_worklist_${TAG}.md"
echo "escalation:   $QUEUE  (resolve: run_escalations.py --interactive | fill 'answer' col + --apply)"
