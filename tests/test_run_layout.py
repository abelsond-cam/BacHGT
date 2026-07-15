"""Unit tests for the run-layout path authority (``engine.run_layout.RunPaths``).

RunPaths is the single source of truth for every per-tranche artifact path — the thing that stops two modules
disagreeing on where a file lives (the root of the recurring silent-drop bugs). These tests lock the two
invariants that matter: every per-tranche output resolves under ``run_progress/<tag>/<stage>/`` (suffix
dropped), and the shared cohort-wide inputs stay at the ``data_dir`` root, owned by no tranche.
"""

from __future__ import annotations

from pathlib import Path

from bac_metadata.bac_agentic_metadata.engine.run_layout import STAGES, RunPaths


def test_per_tranche_artifacts_live_under_run_progress_tag_stage():
    rp = RunPaths("/d", "train")
    root = Path("/d/run_progress/train")
    # one representative artifact per stage — all under run_progress/<tag>/<stage>/, no _train suffix.
    assert rp.found_papers_tsv == root / "find" / "found_papers.tsv"
    assert rp.study_grades_jsonl == root / "grade" / "study_grades.jsonl"
    assert rp.per_sample_applied == root / "per_sample" / "per_sample_applied.tsv"
    assert rp.backfill_applied == root / "backfill" / "backfill_applied.tsv"
    assert rp.decisions_needed == root / "escalation" / "decisions_needed.tsv"
    assert rp.escalation_applied == root / "escalation" / "escalation_applied.tsv"
    assert rp.filled_metadata == root / "fill" / "filled_metadata.tsv"
    assert rp.run_health_md == root / "run_health" / "report.md"
    assert rp.agent_vs_manual_tsv == root / "scorecard" / "agent_vs_manual.tsv"
    # no artifact carries the tag in its filename (the folder does).
    for p in (rp.found_papers_tsv, rp.filled_metadata, rp.run_health_tsv, rp.decisions_needed):
        assert "train" not in p.name


def test_shared_inputs_stay_at_data_root():
    rp = RunPaths("/d", "tail100")
    assert rp.splits == Path("/d/fold_splits/project_splits.tsv")
    assert rp.sizing == Path("/d/ena_assessment/ena_sizing.tsv")
    assert rp.manual_papers_dir == Path("/d/find_papers/manual_download")
    assert rp.manual_supp_dir == Path("/d/sample_lv_attributes/manual_download_supp")
    # the cross-tag master belongs to no single tranche → NOT under run_progress/<tag>/.
    assert rp.escalations_master == Path("/d/curated/curated_escalations.tsv")
    assert "run_progress" not in str(rp.escalations_master)


def test_ensure_creates_every_stage_dir(tmp_path):
    rp = RunPaths(tmp_path, "test").ensure()
    for stage in STAGES:
        assert (rp.root / stage).is_dir()
    # the tag folder isolates tranches from each other.
    assert rp.root == tmp_path / "run_progress" / "test"
