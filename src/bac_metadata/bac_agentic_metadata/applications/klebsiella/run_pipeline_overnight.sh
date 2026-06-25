#!/bin/bash
# Retry-across-usage-windows wrapper for run_pipeline.sh — drives ONE full pipeline pass for a fold
# to completion across Claude subscription windows. The live stages (find / grade / per-sample /
# escalation-detect) hard-stop on the usage limit; each retry RESUMES from the disk cache (cached
# LLM calls return instantly), so a pass converges over hours/days. run_pipeline.sh exits 0 once all
# live stages finish a window-bounded pass — actionable gaps (papers to fetch, escalations to answer)
# are surfaced by the run-health / worklist reports, NOT failures, so this wrapper succeeding means
# "a full pass completed; now read the worklists and re-supply curator inputs, then run another pass".
#
# Usage (detached, survives the terminal; keep the LID OPEN — clamshell sleep ignores caffeinate):
#   caffeinate -dimsu nohup bash run_pipeline_overnight.sh "train,val" train >/dev/null 2>&1 & disown
#   caffeinate -dimsu nohup bash run_pipeline_overnight.sh "test"      test  >/dev/null 2>&1 & disown
#
# After a pass: read data/scorecard/run_health_<tag>_report.md (verdict + actionable worklist),
# download any paywalled papers it lists + link_local_papers.py, drop manual supp tables into
# manual_download_supp/, fill the regenerated decisions_needed_<tag>.tsv answer column (re-supply
# from ~/.bachgt_rerun_stash/), then re-run this wrapper for the next convergence pass.
set -uo pipefail
FOLD="${1:-train,val}"
TAG="${2:-train}"
APP=/Users/davidabelson/developer/BacHGT/src/bac_metadata/bac_agentic_metadata/applications/klebsiella
LOG="$APP/data/logs/pipeline_${TAG}.log"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP="${SLEEP:-1800}"   # 30 min between retries — lets a depleted usage window recover before resuming
mkdir -p "$APP/data/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Per-tag single-instance guard (macOS-safe; no flock). A second launch for the SAME tag is a no-op,
# so a forgotten cancel-before-resume can't spawn a colliding run; DIFFERENT tags (train vs test)
# coexist fine since they write disjoint outputs. Stale PID (dead process) is reclaimed.
PIDFILE="$APP/data/logs/.overnight_${TAG}.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  echo "===== [$(ts)] overnight runner for tag='$TAG' already running (pid $(cat "$PIDFILE")); exiting =====" >> "$LOG"
  exit 0
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

echo "===== [$(ts)] overnight runner START fold='$FOLD' tag='$TAG' (max $MAX_ATTEMPTS attempts, ${SLEEP}s backoff) =====" >> "$LOG"
for i in $(seq 1 "$MAX_ATTEMPTS"); do
  echo "===== [$(ts)] attempt $i/$MAX_ATTEMPTS =====" >> "$LOG"
  if bash "$APP/run_pipeline.sh" "$FOLD" "$TAG" >> "$LOG" 2>&1; then
    echo "===== [$(ts)] PIPELINE PASS COMPLETED on attempt $i — read run_health_${TAG}_report.md =====" >> "$LOG"
    exit 0
  fi
  echo "===== [$(ts)] attempt $i failed (usage limit or transient); sleeping ${SLEEP}s =====" >> "$LOG"
  sleep "$SLEEP"
done
echo "===== [$(ts)] gave up after $MAX_ATTEMPTS attempts — resume by re-running this wrapper =====" >> "$LOG"
exit 1
