#!/bin/bash
# Cleanly stop EVERY clean-rerun process for this app: the overnight wrapper(s), the caffeinate that
# wraps them, the in-flight run_pipeline.sh, every stage script (run_*/report_*), AND any PPID-1
# orphans left behind by a prior partial kill (e.g. a stage child whose run_pipeline.sh parent was
# killed first). pgrep/pkill match by command line, so orphans are caught regardless of parent.
#
# SAFE to run repeatedly and SAFE to run before every resume — it does NOT touch the cache or outputs.
# Every completed LLM/network call is on disk, so relaunching run_pipeline_overnight.sh resumes from
# where this stopped. ALWAYS run this before relaunching, to guarantee a single pipeline instance.
set -u
APP=/Users/davidabelson/developer/BacHGT/src/bac_metadata/bac_agentic_metadata/applications/klebsiella
# wrapper (relative basename) | this app's run_pipeline.sh | this app's run_*/report_* stage scripts
PAT="run_pipeline_overnight\.sh|$APP/run_pipeline\.sh|$APP/run_|$APP/report_"
CAF="caffeinate -dimsu nohup bash .*run_pipeline_overnight"

echo "=== matching processes BEFORE ==="; pgrep -fl "$PAT"; pgrep -fl "$CAF"
pkill -TERM -f "$PAT" 2>/dev/null; pkill -TERM -f "$CAF" 2>/dev/null
sleep 4
pkill -KILL -f "$PAT" 2>/dev/null; pkill -KILL -f "$CAF" 2>/dev/null
sleep 1
echo "=== remaining AFTER (should be none) ==="
pgrep -fl "$PAT" || echo "  (clean)"
pgrep -fl "$CAF" || true
