r"""The single source of truth for a run's on-disk paths — per-tranche outputs + shared inputs.

Every per-tranche artifact lives under ``<data_dir>/run_progress/<tag>/<stage>/<name>`` (the ``<tag>`` suffix
is dropped — the folder encodes it), so one tranche's whole trail — find → grade → per_sample → backfill →
escalation → fill → run_health → scorecard — sits in one place and is auditable at a glance. Shared inputs
(the base table, fold splits, cohort sizing, caches, the curator ``manual_download*`` dirs, the approved
categorisation vocab, and the cross-tag ``curated/`` master) stay at the ``data_dir`` root — they belong to no
single tranche.

`RunPaths` is the ONLY place these paths are constructed. Before, each of ~8 modules hand-built
``f"..._{tag}.tsv"`` strings independently, and the recurring silent-drop bugs came from two modules
disagreeing on a path. Routing everything through here removes that whole class of bug: change a filename in
one property and every reader/writer follows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Pipeline-stage subfolders under ``run_progress/<tag>/`` (order = pipeline order; ``ensure`` makes them all).
STAGES = ("find", "grade", "per_sample", "backfill", "escalation", "fill", "run_health", "scorecard", "selection")


@dataclass(frozen=True)
class RunPaths:
    """Resolve every artifact path for one ``(data_dir, tag)`` tranche — the run's path authority.

    Per-tranche outputs are under ``data_dir/run_progress/<tag>/<stage>/``; the shared members are cohort-wide
    inputs at ``data_dir`` that no single tranche owns. Construct once per stage call
    (``rp = RunPaths(data_dir, tag)``) and read the named properties — never rebuild these strings by hand.
    """

    data_dir: Path
    tag: str

    #: build_missing_papers takes (out_dir, report_prefix) and writes ``<prefix>.{md,tsv}``.
    MISSING_PAPERS_PREFIX = "missing_papers_report"

    def __init__(self, data_dir: str | Path, tag: str) -> None:
        # frozen dataclass → set via object.__setattr__; normalise data_dir to a Path once.
        object.__setattr__(self, "data_dir", Path(data_dir))
        object.__setattr__(self, "tag", tag)

    # ── per-tranche root + stage dirs ──────────────────────────────────────────────────────────────
    @property
    def root(self) -> Path:
        """The tranche's home: ``data_dir/run_progress/<tag>``."""
        return self.data_dir / "run_progress" / self.tag

    @property
    def find_dir(self) -> Path:
        """``run_progress/<tag>/find`` — paper-finding stage outputs."""
        return self.root / "find"

    @property
    def grade_dir(self) -> Path:
        """``run_progress/<tag>/grade`` — study-grading stage outputs."""
        return self.root / "grade"

    @property
    def per_sample_dir(self) -> Path:
        """``run_progress/<tag>/per_sample`` — per-sample extraction outputs."""
        return self.root / "per_sample"

    @property
    def backfill_dir(self) -> Path:
        """``run_progress/<tag>/backfill`` — whole-field backfill outputs."""
        return self.root / "backfill"

    @property
    def escalation_dir(self) -> Path:
        """``run_progress/<tag>/escalation`` — curator escalation queue + applied fills."""
        return self.root / "escalation"

    @property
    def fill_dir(self) -> Path:
        """``run_progress/<tag>/fill`` — the final filled metadata table (production output)."""
        return self.root / "fill"

    @property
    def run_health_dir(self) -> Path:
        """``run_progress/<tag>/run_health`` — the convergence/closure report."""
        return self.root / "run_health"

    @property
    def scorecard_dir(self) -> Path:
        """``run_progress/<tag>/scorecard`` — the gold-benchmark comparison (evaluation layer)."""
        return self.root / "scorecard"

    @property
    def selection_dir(self) -> Path:
        """``run_progress/<tag>/selection`` — the synthetic sizing/splits that define a tail size-band tranche."""
        return self.root / "selection"

    def ensure(self) -> RunPaths:
        """Create the tranche root + every stage subfolder; return self (chainable)."""
        for stage in STAGES:
            (self.root / stage).mkdir(parents=True, exist_ok=True)
        return self

    # ── find ───────────────────────────────────────────────────────────────────────────────────────
    @property
    def found_papers_jsonl(self) -> Path:
        """``find/found_papers.jsonl`` — the finder's full per-study records."""
        return self.find_dir / "found_papers.jsonl"

    @property
    def found_papers_tsv(self) -> Path:
        """``find/found_papers.tsv`` — the finder's per-study paper picks."""
        return self.find_dir / "found_papers.tsv"

    @property
    def missing_papers_tsv(self) -> Path:
        """``find/missing_papers_report.tsv`` — the gap-weighted manual-fetch worklist."""
        return self.find_dir / f"{self.MISSING_PAPERS_PREFIX}.tsv"

    @property
    def missing_papers_md(self) -> Path:
        """``find/missing_papers_report.md`` — human-readable manual-fetch worklist."""
        return self.find_dir / f"{self.MISSING_PAPERS_PREFIX}.md"

    @property
    def find_validation_md(self) -> Path:
        """``find/find_validation_report.md`` — finder-vs-gold validation (evaluation layer)."""
        return self.find_dir / "find_validation_report.md"

    @property
    def find_validation_tsv(self) -> Path:
        """``find/find_validation_report.tsv`` — finder-vs-gold validation table."""
        return self.find_dir / "find_validation_report.tsv"

    @property
    def find_adjudication_md(self) -> Path:
        """``find/find_adjudication_report.md`` — finder adjudication notes (evaluation layer)."""
        return self.find_dir / "find_adjudication_report.md"

    @property
    def find_adjudication_tsv(self) -> Path:
        """``find/find_adjudication_report.tsv`` — finder adjudication table."""
        return self.find_dir / "find_adjudication_report.tsv"

    # ── grade ───────────────────────────────────────────────────────────────────────────────────────
    @property
    def study_grades_jsonl(self) -> Path:
        """``grade/study_grades.jsonl`` — the grader's full per-study judgements."""
        return self.grade_dir / "study_grades.jsonl"

    @property
    def study_grades_tsv(self) -> Path:
        """``grade/study_grades.tsv`` — the grader's per-study field verdicts (flat)."""
        return self.grade_dir / "study_grades.tsv"

    @property
    def grading_validation_md(self) -> Path:
        """``grade/grading_validation_report.md`` — grader-vs-gold validation (evaluation layer)."""
        return self.grade_dir / "grading_validation_report.md"

    @property
    def grading_validation_tsv(self) -> Path:
        """``grade/grading_validation_report.tsv`` — grader-vs-gold validation table."""
        return self.grade_dir / "grading_validation_report.tsv"

    @property
    def grading_adjudication_md(self) -> Path:
        """``grade/grading_adjudication_report.md`` — grader adjudication notes (evaluation layer)."""
        return self.grade_dir / "grading_adjudication_report.md"

    @property
    def grading_adjudication_tsv(self) -> Path:
        """``grade/grading_adjudication_report.tsv`` — grader adjudication table."""
        return self.grade_dir / "grading_adjudication_report.tsv"

    # ── per_sample ───────────────────────────────────────────────────────────────────────────────────
    @property
    def per_sample_applied(self) -> Path:
        """``per_sample/per_sample_applied.tsv`` — per-isolate fills extracted from supplementary tables."""
        return self.per_sample_dir / "per_sample_applied.tsv"

    @property
    def per_sample_outcomes(self) -> Path:
        """``per_sample/per_sample_outcomes.tsv`` — per-study extraction outcome (never a silent 0)."""
        return self.per_sample_dir / "per_sample_outcomes.tsv"

    @property
    def per_sample_value_report_md(self) -> Path:
        """``per_sample/per_sample_value_report.md`` — per-sample overwrite/fidelity audit."""
        return self.per_sample_dir / "per_sample_value_report.md"

    @property
    def per_sample_value_report_tsv(self) -> Path:
        """``per_sample/per_sample_value_report.tsv`` — per-sample overwrite/fidelity audit table."""
        return self.per_sample_dir / "per_sample_value_report.tsv"

    @property
    def persample_supplement_worklist_md(self) -> Path:
        """``per_sample/persample_supplement_worklist.md`` — the manual per-isolate-table curator queue."""
        return self.per_sample_dir / "persample_supplement_worklist.md"

    @property
    def persample_supplement_worklist_tsv(self) -> Path:
        """``per_sample/persample_supplement_worklist.tsv`` — the manual-table curator queue (table)."""
        return self.per_sample_dir / "persample_supplement_worklist.tsv"

    @property
    def preclean_summary(self) -> Path:
        """``per_sample/preclean_summary.tsv`` — the field-specific null tokens blanked in-memory."""
        return self.per_sample_dir / "preclean_summary.tsv"

    # ── backfill (whole-field) ───────────────────────────────────────────────────────────────────────
    @property
    def backfill_applied(self) -> Path:
        """``backfill/backfill_applied.tsv`` — whole-field fills the grader vouched (coarse fallback)."""
        return self.backfill_dir / "backfill_applied.tsv"

    @property
    def backfill_gate_report(self) -> Path:
        """``backfill/backfill_gate_report.tsv`` — per-study whole-field gate decisions."""
        return self.backfill_dir / "backfill_gate_report.tsv"

    @property
    def backfill_value_report_md(self) -> Path:
        """``backfill/backfill_value_report.md`` — whole-field value audit."""
        return self.backfill_dir / "backfill_value_report.md"

    @property
    def backfill_value_report_tsv(self) -> Path:
        """``backfill/backfill_value_report.tsv`` — whole-field value audit table."""
        return self.backfill_dir / "backfill_value_report.tsv"

    # ── escalation ───────────────────────────────────────────────────────────────────────────────────
    @property
    def decisions_needed(self) -> Path:
        """``escalation/decisions_needed.tsv`` — the whole-field near-miss queue + curator answers."""
        return self.escalation_dir / "decisions_needed.tsv"

    @property
    def escalation_applied(self) -> Path:
        """``escalation/escalation_applied.tsv`` — answers applied as curator_escalation fills."""
        return self.escalation_dir / "escalation_applied.tsv"

    @property
    def accepted_unrecoverable(self) -> Path:
        """``escalation/accepted_unrecoverable.tsv`` — auditable dead-end gaps a curator retired."""
        return self.escalation_dir / "accepted_unrecoverable.tsv"

    # ── fill (production output) ─────────────────────────────────────────────────────────────────────
    @property
    def filled_metadata(self) -> Path:
        """``fill/filled_metadata.tsv`` — the full-width final table (the pipeline's production output)."""
        return self.fill_dir / "filled_metadata.tsv"

    @property
    def filled_metadata_provenance(self) -> Path:
        """``fill/filled_metadata_provenance.tsv`` — long-format per-cell fill provenance."""
        return self.fill_dir / "filled_metadata_provenance.tsv"

    @property
    def filled_metadata_summary(self) -> Path:
        """``fill/filled_metadata_summary.md`` — per-field completeness + source breakdown."""
        return self.fill_dir / "filled_metadata_summary.md"

    # ── run_health ───────────────────────────────────────────────────────────────────────────────────
    @property
    def run_health_md(self) -> Path:
        """``run_health/report.md`` — the convergence verdict + pipeline self-audit + conservation stamp."""
        return self.run_health_dir / "report.md"

    @property
    def run_health_tsv(self) -> Path:
        """``run_health/report.tsv`` — the per-(study×field) resolution-state grid."""
        return self.run_health_dir / "report.tsv"

    # ── scorecard (gold benchmark; produced by evaluation/run_folds.sh) ──────────────────────────────
    @property
    def agent_vs_manual_md(self) -> Path:
        """``scorecard/agent_vs_manual.md`` — agent-vs-gold agreement summary."""
        return self.scorecard_dir / "agent_vs_manual.md"

    @property
    def agent_vs_manual_tsv(self) -> Path:
        """``scorecard/agent_vs_manual.tsv`` — agent-vs-gold agreement table."""
        return self.scorecard_dir / "agent_vs_manual.tsv"

    @property
    def backfill_completeness_md(self) -> Path:
        """``scorecard/backfill_completeness_report.md`` — per-field completeness (raw→agent→gold)."""
        return self.scorecard_dir / "backfill_completeness_report.md"

    @property
    def backfill_completeness_tsv(self) -> Path:
        """``scorecard/backfill_completeness_report.tsv`` — per-field completeness table."""
        return self.scorecard_dir / "backfill_completeness_report.tsv"

    # ── selection (tail size-band batch) ─────────────────────────────────────────────────────────────
    @property
    def selection_sizing(self) -> Path:
        """``selection/ena_sizing.tsv`` — the synthetic per-batch sizing for a tail tranche."""
        return self.selection_dir / "ena_sizing.tsv"

    @property
    def selection_splits(self) -> Path:
        """``selection/project_splits.tsv`` — the synthetic per-batch fold split for a tail tranche."""
        return self.selection_dir / "project_splits.tsv"

    # ── shared cohort-wide inputs (root-level; owned by no single tranche) ───────────────────────────
    @property
    def splits(self) -> Path:
        """``fold_splits/project_splits.tsv`` (shared) — the curated study→fold assignment."""
        return self.data_dir / "fold_splits" / "project_splits.tsv"

    @property
    def sizing(self) -> Path:
        """``ena_assessment/ena_sizing.tsv`` (shared) — the cohort ENA sizing table."""
        return self.data_dir / "ena_assessment" / "ena_sizing.tsv"

    @property
    def assessment_report(self) -> Path:
        """``ena_assessment/ena_assessment_report.tsv`` (shared) — the cohort classification report."""
        return self.data_dir / "ena_assessment" / "ena_assessment_report.tsv"

    @property
    def manual_papers_dir(self) -> Path:
        """``find_papers/manual_download`` (shared) — hand-downloaded paywalled PDFs."""
        return self.data_dir / "find_papers" / "manual_download"

    @property
    def manual_supp_dir(self) -> Path:
        """``sample_lv_attributes/manual_download_supp`` (shared) — curator per-isolate tables (tracked)."""
        return self.data_dir / "sample_lv_attributes" / "manual_download_supp"

    @property
    def categorisation_dir(self) -> Path:
        """``study_lv_attributes/categorisation`` (shared) — approved category vocab yamls."""
        return self.data_dir / "study_lv_attributes" / "categorisation"

    @property
    def curated_dir(self) -> Path:
        """``curated`` (shared) — the cross-tag accumulation stores + master."""
        return self.data_dir / "curated"

    @property
    def escalations_master(self) -> Path:
        """``curated/curated_escalations.tsv`` (shared) — the sticky cross-tag curator answer store."""
        return self.curated_dir / "curated_escalations.tsv"
