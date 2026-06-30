r"""Accumulate per-batch agent fills into one growing curated metadata table (engine, app-agnostic).

The agent curates the cohort in **batches** — the gated folds (train/val, test), then the size-banded
uncurated tails. Each batch persists its fills as long applied-tables
(``{per_sample,backfill,escalation}_applied_<tag>.tsv``), its curator escalation answers
(``decisions_needed_<tag>.tsv``), and its study grades (``study_grades_<tag>.tsv``). On their own these are
**siloed per batch**. This module UNIONS them across every batch into cumulative stores and rebuilds one
master curated table over the FULL base — so curation is **built up, never recomputed-and-discarded**:

============================  ====================================================================
``curated_fills.tsv``         every batch's winning per-(sample, field) fill (precedence-merged,
                              with the originating ``tag``) — the canonical fills store
``curated_escalations.tsv``   every batch's RESOLVED curator escalation answer, keyed (study, field)
                              — so a future batch never re-asks an answered decision
``curated_grades.tsv``        every batch's study grades (deduped by study) — for the broadcast
                              study-level columns of the master table
``metadata_curated_master.tsv``  the FULL base table with all curated fills substituted — the
                              growing deliverable (coverage rises as more studies are curated)
============================  ====================================================================

It also provides the **feed-forward overlay** (:func:`overlay_master_on_base` — pre-populate a new batch's
base with the master so the agent only works still-blank cells) and the **canonical merge**
(:func:`merge_into_canonical` — overlay the master onto the human-curated metadata table, human winning, to
produce the next iteration of metadata for downstream analyses).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from . import backfill

#: The three long applied-fill tables each batch writes, keyed by the method-source they carry.
_APPLIED_FILES: dict[str, tuple[str, ...]] = {
    "per_sample": ("sample_lv_attributes", "per_sample", "per_sample_applied_{tag}.tsv"),
    "whole_field": ("study_lv_attributes", "whole_study_backfill", "backfill_applied_{tag}.tsv"),
    "escalation": ("study_lv_attributes", "escalation", "escalation_applied_{tag}.tsv"),
}

#: Resolved-escalation note markers (mirrors run_health / run_escalations): a skip/reject is a DECISION.
_RESOLVED_NOTE_MARKERS = ("reject", "skip", "undeterm", "leave uncoded", "no value")


def _applied_path(data_dir: Path, source: str, tag: str) -> Path:
    """Return the path to one batch's applied-fill table for the given method source."""
    *parts, name = _APPLIED_FILES[source]
    return data_dir.joinpath(*parts, name.format(tag=tag))


def accumulate_fills(data_dir: Path, tags: Sequence[str], out_dir: Path) -> pd.DataFrame:
    """Union every batch's applied fills into one precedence-merged store with batch provenance.

    For each ``tag`` the three applied tables (per-sample, whole-field, escalation) are read and tagged with
    their batch; all are precedence-merged to one winning row per (sample_accession, field) via
    :func:`backfill.apply_precedence_merge` (per-sample > curator-escalation > whole-field). A sample belongs
    to one batch, so cross-batch conflicts do not arise; the merge resolves within-batch method overlap.

    Parameters
    ----------
    data_dir
        The application's task-aligned data tree.
    tags
        Batch tags to union (e.g. ``["train", "test", "tail100"]``).
    out_dir
        Directory to write ``curated_fills.tsv`` into (created if absent).

    Returns
    -------
    pandas.DataFrame
        One winning fill per (sample_accession, field), with its originating ``tag``.
    """
    frames: list[pd.DataFrame] = []
    for tag in tags:
        for source in _APPLIED_FILES:
            path = _applied_path(data_dir, source, tag)
            if not path.exists():
                print(f"  [fills] {tag}/{source}: absent ({path.name}) — skipped", file=sys.stderr)
                continue
            df = pd.read_csv(path, sep="\t", dtype=str)
            need = {"study_accession", "sample_accession", "field", "applied_value", "method"}
            missing = need - set(df.columns)
            if missing:
                sys.exit(f"{path} missing columns: {sorted(missing)}")
            keep = df[["study_accession", "sample_accession", "field", "applied_value", "method"]].copy()
            keep["ena_value"] = df["ena_value"] if "ena_value" in df.columns else pd.NA
            keep["tag"] = tag
            frames.append(keep)
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["study_accession", "sample_accession", "field", "ena_value", "applied_value", "method", "tag"]
    merged = (backfill.apply_precedence_merge(frames) if frames
              else pd.DataFrame(columns=[*cols, "_rank"]))
    merged = merged.drop(columns=[c for c in ("_rank",) if c in merged.columns])
    merged = merged.reindex(columns=cols)
    out_path = out_dir / "curated_fills.tsv"
    merged.to_csv(out_path, sep="\t", index=False)
    by_field = merged["field"].value_counts().to_dict() if len(merged) else {}
    print(f"Wrote {out_path}: {len(merged)} curated cells "
          f"({', '.join(f'{k} {v}' for k, v in by_field.items()) or 'none'})", file=sys.stderr)
    return merged


def accumulate_escalations(data_dir: Path, tags: Sequence[str], out_dir: Path) -> pd.DataFrame:
    """Union every batch's RESOLVED curator escalation answers into one store, keyed (study, field).

    A decision is resolved when it carries an answer OR a reject/skip note (a deliberate "no single value").
    The store lets a future ``escalate_detect`` skip a (study, field) the curator has already decided — the
    answer is never re-asked, and a regenerated queue cannot lose it.

    Parameters
    ----------
    data_dir, tags, out_dir
        As for :func:`accumulate_fills`; reads ``study_lv_attributes/escalation/decisions_needed_<tag>.tsv``.

    Returns
    -------
    pandas.DataFrame
        Resolved decisions keyed (study_accession, field), with ``answer``, ``answer_note`` and ``tag``;
        on a conflict (same study+field decided in two batches) the answered one wins, else the first.
    """
    frames: list[pd.DataFrame] = []
    for tag in tags:
        path = data_dir / "study_lv_attributes" / "escalation" / f"decisions_needed_{tag}.tsv"
        if not path.exists():
            continue
        df = pd.read_csv(path, sep="\t", dtype=str).fillna("")
        if not {"study_accession", "field"} <= set(df.columns):
            continue
        df["answer"] = df.get("answer", "")
        df["answer_note"] = df.get("answer_note", "")
        answered = df["answer"].astype(str).str.strip() != ""
        skipped = df["answer_note"].astype(str).str.lower().apply(
            lambda n: any(w in n for w in _RESOLVED_NOTE_MARKERS))
        resolved = df[answered | skipped].copy()
        resolved["tag"] = tag
        resolved["_answered"] = answered[answered | skipped].astype(int).to_numpy()
        frames.append(resolved[["study_accession", "field", "answer", "answer_note", "tag", "_answered"]])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "curated_escalations.tsv"
    if not frames:
        empty = pd.DataFrame(columns=["study_accession", "field", "answer", "answer_note", "tag"])
        empty.to_csv(out_path, sep="\t", index=False)
        print(f"Wrote {out_path}: 0 resolved decisions", file=sys.stderr)
        return empty
    alld = pd.concat(frames, ignore_index=True)
    # Prefer an answered decision over a bare skip when the same (study, field) appears in two batches.
    alld = (alld.sort_values(["study_accession", "field", "_answered"], ascending=[True, True, False])
            .drop_duplicates(["study_accession", "field"], keep="first").drop(columns="_answered"))
    alld.to_csv(out_path, sep="\t", index=False)
    n_ans = int((alld["answer"].astype(str).str.strip() != "").sum())
    print(f"Wrote {out_path}: {len(alld)} resolved decisions ({n_ans} answered, {len(alld) - n_ans} skip)",
          file=sys.stderr)
    return alld


def accumulate_grades(data_dir: Path, tags: Sequence[str], out_dir: Path) -> Path:
    """Union every batch's study grades (deduped by study) into ``curated_grades.tsv`` for the master fill."""
    frames: list[pd.DataFrame] = []
    for tag in tags:
        path = data_dir / "study_lv_attributes" / "grading" / f"study_grades_{tag}.tsv"
        if path.exists():
            frames.append(pd.read_csv(path, sep="\t", dtype=str))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "curated_grades.tsv"
    if frames:
        allg = pd.concat(frames, ignore_index=True).drop_duplicates("study_accession", keep="first")
    else:
        allg = pd.DataFrame(columns=["study_accession"])
    allg.to_csv(out_path, sep="\t", index=False)
    print(f"Wrote {out_path}: {len(allg)} graded studies", file=sys.stderr)
    return out_path


def build_master_table(
    *,
    base: pd.DataFrame,
    curated_fills_path: Path,
    curated_grades_path: Path,
    fields: Sequence[str],
    study_grade_columns: Mapping[str, str],
    out_path: Path,
) -> pd.DataFrame:
    """Fill the FULL base table with the accumulated curated fills — the master deliverable.

    A thin wrapper over :func:`stages.fill_metadata_table` that feeds it the *whole* base (every sample) and
    the single accumulated fills store, so one wide table carries all curation done so far. Uncurated samples
    keep their ENA values; curated cells take the agent value (precedence per-sample > escalation >
    whole-field > ENA).

    Returns
    -------
    pandas.DataFrame
        The master curated table (also written to ``out_path`` as ``metadata_curated_master.tsv`` plus its
        provenance/summary sidecars, via the underlying fill stage).
    """
    from . import stages

    return stages.fill_metadata_table(
        base=base,
        fields=fields,
        fill_paths={"curated": curated_fills_path},
        grades_path=curated_grades_path,
        study_grade_columns=study_grade_columns,
        out_path=out_path,
        tag="curated_master",
        fold_label="curated master (all batches)",
    )


def overlay_master_on_base(base: pd.DataFrame, master_fills: pd.DataFrame,
                           fields: Sequence[str]) -> pd.DataFrame:
    """Feed-forward: pre-populate a new batch's base with prior curation so blanks-only are re-worked.

    Left-joins the accumulated ``master_fills`` (long: sample_accession/field/applied_value) onto ``base``,
    writing a curated value ONLY where the base cell is blank. The agent's completeness gate then sees those
    cells as filled and does not re-curate them — so re-processing a curated study is avoided at scale. Real
    ENA values are never overwritten (the agent still owns per-sample overrides within its own batch).

    Returns
    -------
    pandas.DataFrame
        A copy of ``base`` with prior-curated values slotted into previously-blank cells.
    """
    out = base.copy()
    for f in fields:
        if f not in out.columns:
            continue
        vals = master_fills[master_fills["field"] == f]
        val_map = dict(zip(vals["sample_accession"], vals["applied_value"], strict=False))
        cur = backfill.strip_placeholders(out[f])
        blank = cur.isna()
        overlay = out["sample_accession"].map(val_map)
        out.loc[blank, f] = out.loc[blank, f].where(overlay[blank].isna(), overlay[blank])
    return out


def merge_into_canonical(master: pd.DataFrame, canonical: pd.DataFrame, fields: Sequence[str], *,
                         out_path: Path, gold_suffix: str = "_parsed") -> pd.DataFrame:
    """Overlay the master curation onto the human-curated metadata table — human ALWAYS wins.

    Produces "the next iteration of metadata": the canonical table with agent fills slotted into cells the
    human has NOT curated (blank human value), keyed on ``sample_accession``. Human curation is never
    overwritten — precedence is **human-curated > agent > ENA**. A ``<field>_agent_filled`` flag column marks
    each cell the agent contributed, for auditability.

    Parameters
    ----------
    master
        The master curated table (output of :func:`build_master_table`).
    canonical
        The human-curated metadata table (e.g. ``metadata_final_curated_all_samples_and_columns.tsv``).
    fields
        The clinical fields to overlay.
    out_path
        Where to write the merged table.
    gold_suffix
        Suffix of the human-curated parsed column per field (default ``_parsed``); falls back to the bare
        field name when the suffixed column is absent.

    Returns
    -------
    pandas.DataFrame
        The merged canonical table (also written to ``out_path``).
    """
    merged = canonical.copy()
    if "sample_accession" not in merged.columns:
        sys.exit("canonical table lacks sample_accession — cannot merge")
    m_idx = master.drop_duplicates("sample_accession").set_index("sample_accession")
    for f in fields:
        human_col = f if f in merged.columns else None
        parsed = f"{f}{gold_suffix}"
        human_ref = parsed if parsed in merged.columns else human_col
        if human_ref is None or f not in m_idx.columns:
            print(f"  [canonical] {f}: no column to merge onto — skipped", file=sys.stderr)
            continue
        human_val = backfill.strip_placeholders(merged[human_ref])
        agent_val = merged["sample_accession"].map(backfill.strip_placeholders(m_idx[f]))
        target = human_col or f
        take_agent = human_val.isna() & agent_val.notna()
        if target not in merged.columns:
            merged[target] = human_val
        merged.loc[take_agent, target] = agent_val[take_agent]
        merged[f"{f}_agent_filled"] = take_agent
        print(f"  [canonical] {f}: {int(take_agent.sum())} agent fills into human-blank cells", file=sys.stderr)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, sep="\t", index=False)
    print(f"Wrote {out_path}: {len(merged)} rows (human-curated > agent > ENA)", file=sys.stderr)
    return merged
