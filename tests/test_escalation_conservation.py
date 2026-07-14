"""Unit tests for the escalation-conservation gate (``evaluation.verify_escalation_conservation``).

The gate is the end-to-end catch for the recurring silent-drop pattern: a curator decision that vanishes at
any link of answer → apply → master → final. These tests lock each invariant's PASS and its loud-FAIL:
INV1 (an answered decision with no applied fill), INV3 (an escalation fill that ends blank in the final
table), and the honest funnel. INV2 (master ⊇ git HEAD) is exercised against a throwaway git repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.evaluation import verify_escalation_conservation as vc


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)


def _dirs(tmp_path: Path):
    data = tmp_path / "data"
    return data, data / "study_lv_attributes" / "escalation", data / "sample_lv_attributes" / "enriched"


def test_inv1_apply_pass_and_fail(tmp_path):
    _data, esc, _enr = _dirs(tmp_path)
    # A answered → applied (pass side); B answered → NOT applied (fail side); C skip → not required to apply.
    _write(esc / "decisions_needed_train.tsv", [
        {"study_accession": "A", "field": "country", "answer": "USA", "answer_note": ""},
        {"study_accession": "B", "field": "host", "answer": "human", "answer_note": ""},
        {"study_accession": "C", "field": "isolation_source", "answer": "", "answer_note": "curator skip: wide mix"},
    ])
    _write(esc / "escalation_applied_train.tsv", [
        {"study_accession": "A", "sample_accession": "s1", "field": "country",
         "ena_value": "", "applied_value": "USA", "method": "curator_escalation"},
    ])
    fails: list[str] = []
    stats = vc.check_inv1_apply(esc, "train", fails)
    assert stats["answered"] == 2                       # A + B (skip C not counted)
    assert stats["applied_pairs"] == 1                  # only A applied
    assert len(fails) == 1 and "1 answered decision(s) never applied" in fails[0]


def test_inv3_fill_detects_blank_final_cell(tmp_path):
    _data, esc, enr = _dirs(tmp_path)
    _write(esc / "escalation_applied_train.tsv", [
        {"study_accession": "A", "sample_accession": "s1", "field": "country",
         "ena_value": "", "applied_value": "USA", "method": "curator_escalation"},
        {"study_accession": "A", "sample_accession": "s2", "field": "country",
         "ena_value": "", "applied_value": "USA", "method": "curator_escalation"},
    ])
    # s1 reached final; s2 is blank in final → a silent loss the gate must catch.
    _write(enr / "filled_metadata_train.tsv", [
        {"sample_accession": "s1", "country": "USA"},
        {"sample_accession": "s2", "country": ""},
    ])
    fails: list[str] = []
    stats = vc.check_inv3_fill(esc, enr, "train", fails)
    assert stats["traced"] == 2 and stats["in_final"] == 1
    assert len(fails) == 1 and "blank/absent in final" in fails[0]


def test_inv3_fill_passes_when_all_reach_final(tmp_path):
    _data, esc, enr = _dirs(tmp_path)
    _write(esc / "escalation_applied_train.tsv", [
        {"study_accession": "A", "sample_accession": "s1", "field": "host",
         "ena_value": "", "applied_value": "human", "method": "curator_escalation"},
    ])
    # A higher-precedence per-sample value CHANGED the cell — not blank, so not a loss.
    _write(enr / "filled_metadata_train.tsv", [{"sample_accession": "s1", "host": "Homo sapiens"}])
    fails: list[str] = []
    stats = vc.check_inv3_fill(esc, enr, "train", fails)
    assert not fails and stats["in_final"] == 1


def test_inv2_master_preserve_catches_dropped_row(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    master = repo / "curated" / "curated_escalations.tsv"
    _write(master, [
        {"study_accession": "A", "field": "country", "answer": "USA", "answer_note": "", "tag": "train"},
        {"study_accession": "B", "field": "host", "answer": "human", "answer_note": "", "tag": "train"},
    ])
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)

    # Now the disk master DROPS B — the exact silent-loss the gate exists to catch.
    _write(master, [{"study_accession": "A", "field": "country", "answer": "USA", "answer_note": "", "tag": "train"}])
    fails: list[str] = []
    stats = vc.check_inv2_master(master, fails)
    assert stats["head_rows"] == 2 and stats["disk_rows"] == 1 and stats["dropped"] == 1
    assert len(fails) == 1 and "missing from disk master" in fails[0]

    # Preserving B (and adding C) passes.
    _write(master, [
        {"study_accession": "A", "field": "country", "answer": "USA", "answer_note": "", "tag": "train"},
        {"study_accession": "B", "field": "host", "answer": "human", "answer_note": "", "tag": "train"},
        {"study_accession": "C", "field": "country", "answer": "UK", "answer_note": "", "tag": "test"},
    ])
    fails2: list[str] = []
    stats2 = vc.check_inv2_master(master, fails2)
    assert not fails2 and stats2["dropped"] == 0 and stats2["disk_rows"] == 3


def test_amend_run_health_is_idempotent(tmp_path):
    score = tmp_path / "scorecard"
    score.mkdir()
    md = score / "run_health_train_report.md"
    md.write_text("# Run-health report\n\nbody\n")
    inv1 = {"answered": 3, "applied_pairs": 3, "n_fills": 120}
    inv3 = {"traced": 120, "in_final": 120}
    inv2 = {"disk_rows": 51, "head_rows": 50, "dropped": 0}
    vc._amend_run_health(score, "train", inv1, inv3, inv2)
    once = md.read_text()
    assert once.count(vc._CONSERVATION_MARKER) == 1 and "VERIFIED" in once
    vc._amend_run_health(score, "train", inv1, inv3, inv2)
    twice = md.read_text()
    assert twice.count(vc._CONSERVATION_MARKER) == 1   # replaced, not appended
