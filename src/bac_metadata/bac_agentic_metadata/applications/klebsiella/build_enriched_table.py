"""Build the intermediate **enriched collated table** for a Klebsiella fold (deterministic, no LLM).

This replicates step 1 of the curation pipeline (``pp.metadata_collation`` — the per-project
``ready_to_merge`` substitution) but with the **agent's found values** as the merge source instead of
David's manual ``ready_to_merge`` files. It does **not** touch the ``ENA_projects`` tree (so it never
clashes with the manual files for the curated studies); it writes a standalone full-width per-sample
table that is a drop-in for ``qc_add_metadata`` (step 2) and the substrate for the downstream steps.

For each of the four clinical fields (``country``, ``collection_date``, ``isolation_source``, ``host``)
the agent value **replaces** the ENA-deposited value with precedence

    per-sample  >  curator-escalation  >  whole-field  >  ENA-as-deposited

— the per-sample table (accurate, per-isolate) wins; the two study-wide sources only ever filled blanks
(by the backfill parsimony guard), so the only replacements of a *real* ENA value come from per-sample.
Every change is recorded in a long-format provenance sidecar, so nothing is silently overwritten.

It also adds **two new study-level columns** — ``study_setting`` and ``amr_study`` — broadcasting the
agent's per-study graded value to every sample in the study (blank where ``not_gradeable``). These match
the metadata_v2 column names; the manual pipeline fills them per-study from the study_level sheet.

Inputs (per fold ``<TAG>`` = ``test`` | ``train``):
  * the full-width collated base table — ``pp.metadata_collation.load_collated_metadata`` run **offline**
    (``google_sheet_id=None`` + the committed ``study_level`` CSV), restricted to the fold's studies;
  * the three applied-fill tables ``{per_sample,escalation,backfill}_applied_<TAG>.tsv``
    (long format: ``study_accession, sample_accession, field, ena_value, applied_value, method, evidence``).

Outputs (under ``data/sample_lv_attributes/enriched/``):
  * ``enriched_collated_<TAG>.tsv``   — full-width base table, the four fields substituted;
  * ``enriched_provenance_<TAG>.tsv`` — long: ``study_accession, sample_accession, field, ena_value,
    enriched_value, source`` (one row per filled/changed cell);
  * ``enriched_summary_<TAG>.md``     — per-field completeness (base vs enriched) + source/override counts.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
INPUTS_DIR = DATA_DIR / "inputs"
GRADING_DIR = DATA_DIR / "study_lv_attributes" / "grading"
WSB_DIR = DATA_DIR / "study_lv_attributes" / "whole_study_backfill"
ESC_DIR = DATA_DIR / "study_lv_attributes" / "escalation"
PS_DIR = DATA_DIR / "sample_lv_attributes" / "per_sample"
OUT_DIR = DATA_DIR / "sample_lv_attributes" / "enriched"

FIELDS = list(backfill.FIELDS)
#: Study-level grades broadcast to every sample in the study, as new columns (col name -> grade __value).
#: Matches the metadata_v2 column names (``amr_study``, ``study_setting``), which the manual pipeline
#: fills per-study from the study_level sheet; here they carry the AGENT's graded value.
STUDY_GRADES = {"study_setting": "study_setting__value", "amr_study": "amr_study__value"}
DEFAULT_STUDY_CSV = INPUTS_DIR / "study_level_metadata_all_combined_v1.0_20260105.csv"


def _fold_studies(folds: set[str]) -> set[str]:
    """Return the set of ``study_accession`` assigned to the requested folds."""
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)
    return set(split[split["fold"].isin(folds)]["study_accession"])


def _load_full_base(study_csv: str | None, studies: set[str]) -> pd.DataFrame:
    """Return the full-width collated base table (all ENA columns) for the given studies.

    Runs ``pp.metadata_collation.load_collated_metadata`` **offline** — ``google_sheet_id=None`` makes
    ``removed_studies`` an empty set and the local ``study_level`` CSV supplies the reviewed flag without
    a Google read. The collation already coalesces duplicate ``sample_accession`` to one row.
    """
    from bac_metadata.pp import metadata_collation as mcoll

    kwargs: dict[str, str] = {}
    if study_csv:
        kwargs["study_metadata_file"] = study_csv
    # The collation is verbose; keep its debug chatter off the report stream (stdout) by sending it to stderr.
    with contextlib.redirect_stdout(sys.stderr):
        base = mcoll.load_collated_metadata(google_sheet_id=None, **kwargs)
    base = base.drop_duplicates("sample_accession")
    return base[base["study_accession"].isin(studies)].copy()


def _load_fills(paths: dict[str, str]) -> pd.DataFrame:
    """Concatenate the applied-fill tables and resolve to one winning fill per (sample, field).

    Each input row carries a ``method`` (``per_sample``/``per_sample_two_hop``/``curator_escalation``/
    ``whole_field``); we strip placeholder applied-values, rank by source precedence, and keep the
    single highest-precedence non-blank fill per (sample_accession, field).
    """
    frames = []
    for label, path in paths.items():
        if not path or not Path(path).exists():
            print(f"  [fills] {label}: absent ({path}) — skipped", file=sys.stderr)
            continue
        df = pd.read_csv(path, sep="\t", dtype=str)
        need = {"sample_accession", "field", "applied_value", "method", "study_accession"}
        if not need <= set(df.columns):
            sys.exit(f"{path} missing columns: {sorted(need - set(df.columns))}")
        frames.append(df[["study_accession", "sample_accession", "field", "ena_value", "applied_value", "method"]].copy())
    if not frames:
        return pd.DataFrame(columns=["study_accession", "sample_accession", "field", "ena_value",
                                     "applied_value", "method", "_rank"])
    # The precedence pick (per-sample > escalation > whole-field) lives in the engine.
    return backfill.apply_precedence_merge(frames, rank=backfill.PRECEDENCE_DEFAULT)


def _load_grades(path: str, studies: set[str]) -> pd.DataFrame:
    """Return per-study graded values for the broadcast study-level columns (placeholder-stripped)."""
    if not path or not Path(path).exists():
        print(f"  [grades] absent ({path}) — study-level columns will be blank", file=sys.stderr)
        return pd.DataFrame(columns=["study_accession", *STUDY_GRADES])
    g = pd.read_csv(path, sep="\t", dtype=str)
    g = g[g["study_accession"].isin(studies)].drop_duplicates("study_accession")
    out = pd.DataFrame({"study_accession": g["study_accession"]})
    for col, src in STUDY_GRADES.items():
        out[col] = backfill.strip_placeholders(g[src]) if src in g.columns else pd.NA
    return out.reset_index(drop=True)


def main() -> None:
    """Substitute the agent's found values into the fold's collated base table and write the outputs."""
    p = argparse.ArgumentParser(description="Build the intermediate enriched collated table for a fold.")
    p.add_argument("--fold", required=True, help="Comma-separated folds for the roster, e.g. 'test' or 'train,val'.")
    p.add_argument("--tag", required=True, help="Applied-file suffix, e.g. 'test' or 'train'.")
    p.add_argument("--study-csv", default=str(DEFAULT_STUDY_CSV),
                   help="Local study_level CSV to drive collation offline (avoids the Google read).")
    p.add_argument("--per-sample", default=None, help="Per-sample applied TSV (default: per_sample_applied_<TAG>.tsv).")
    p.add_argument("--escalation", default=None, help="Escalation applied TSV (default: escalation_applied_<TAG>.tsv).")
    p.add_argument("--backfill", default=None, help="Whole-field applied TSV (default: backfill_applied_<TAG>.tsv).")
    p.add_argument("--grades", default=None, help="Study grading TSV (default: study_grades_<TAG>.tsv).")
    p.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory.")
    args = p.parse_args()

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    tag = args.tag
    ps = args.per_sample or str(PS_DIR / f"per_sample_applied_{tag}.tsv")
    esc = args.escalation or str(ESC_DIR / f"escalation_applied_{tag}.tsv")
    wf = args.backfill or str(WSB_DIR / f"backfill_applied_{tag}.tsv")
    grades_path = args.grades or str(GRADING_DIR / f"study_grades_{tag}.tsv")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    studies = _fold_studies(folds)
    print(f"Fold {sorted(folds)} (tag={tag}): {len(studies)} studies", file=sys.stderr)
    base = _load_full_base(args.study_csv, studies)
    print(f"Collated base (full width): {len(base)} samples, {len(base.columns)} columns", file=sys.stderr)

    fills = _load_fills({"per_sample": ps, "escalation": esc, "whole_field": wf})
    grades = _load_grades(grades_path, studies)

    # Long-format provenance + the wide substitution, built field by field.
    prov_rows: list[pd.DataFrame] = []
    summary: list[dict[str, object]] = []
    enriched = base.copy()
    base_idx_value = {f: backfill.strip_placeholders(base.set_index("sample_accession")[f]) if f in base.columns
                      else pd.Series(dtype="string") for f in FIELDS}

    for f in FIELDS:
        ff = fills[fills["field"] == f]
        val_map = dict(zip(ff["sample_accession"], ff["applied_value"], strict=False))
        src_map = dict(zip(ff["sample_accession"], ff["method"], strict=False))
        base_real = base_idx_value[f]  # placeholder-stripped, indexed by sample_accession

        samp = enriched["sample_accession"]
        fill_val = samp.map(val_map)                      # agent value where we have one
        base_val = samp.map(base_real)                    # real ENA value (NA if blank/placeholder)
        # Final enriched value: agent fill wins, else keep the (real) ENA value.
        final_val = fill_val.where(fill_val.notna(), base_val)
        enriched[f] = final_val

        # Provenance: every cell that ended up with an agent fill (record what it replaced, if anything).
        has_fill = fill_val.notna()
        prov = pd.DataFrame({
            "study_accession": enriched["study_accession"][has_fill].to_numpy(),
            "sample_accession": samp[has_fill].to_numpy(),
            "field": f,
            "ena_value": base_val[has_fill].to_numpy(),                # NA = filled a blank; value = override
            "enriched_value": fill_val[has_fill].to_numpy(),
            "source": samp[has_fill].map(src_map).to_numpy(),
        })
        prov_rows.append(prov)

        # Per-field completeness + accounting.
        n = len(enriched)
        base_present = base_val.notna()
        enriched_present = final_val.notna()
        overrides = int((has_fill & base_present).sum())       # agent replaced a real ENA value
        new_fills = int((has_fill & ~base_present).sum())      # agent filled a blank
        by_src = prov["source"].value_counts().to_dict()
        summary.append({
            "field": f,
            "n_samples": n,
            "base_complete": round(float(base_present.mean()), 4),
            "enriched_complete": round(float(enriched_present.mean()), 4),
            "agent_fills": int(has_fill.sum()),
            "new_fills": new_fills,
            "overrides": overrides,
            "per_sample": int(by_src.get("per_sample", 0) + by_src.get("per_sample_two_hop", 0)),
            "curator_escalation": int(by_src.get("curator_escalation", 0)),
            "whole_field": int(by_src.get("whole_field", 0)),
        })

    # Study-level grades broadcast to every sample in the study (new columns; uniform within a study,
    # so accounted at study level rather than as per-cell provenance rows).
    grade_map = grades.set_index("study_accession") if not grades.empty else pd.DataFrame()
    grade_summary: list[dict[str, object]] = []
    for col in STUDY_GRADES:
        gser = grade_map[col] if col in grade_map.columns else pd.Series(dtype="string")
        enriched[col] = enriched["study_accession"].map(gser)
        filled = enriched[col].notna()
        graded_studies = int(grade_map[col].notna().sum()) if col in grade_map.columns else 0
        grade_summary.append({
            "field": col, "graded_studies": graded_studies, "samples_filled": int(filled.sum()),
            "values": dict(enriched.loc[filled, col].value_counts()),
        })

    provenance = pd.concat(prov_rows, ignore_index=True) if prov_rows else pd.DataFrame()
    res = pd.DataFrame(summary)

    enriched_path = out_dir / f"enriched_collated_{tag}.tsv"
    prov_path = out_dir / f"enriched_provenance_{tag}.tsv"
    md_path = out_dir / f"enriched_summary_{tag}.md"
    enriched.to_csv(enriched_path, sep="\t", index=False)
    provenance.to_csv(prov_path, sep="\t", index=False)

    md = [f"# Enriched collated table — fold {', '.join(sorted(folds))} (tag `{tag}`)\n",
          f"Studies: **{len(studies)}**; samples: **{len(enriched)}**. The four clinical fields in the "
          "full-width collated base table have been substituted with the agent's found values "
          "(precedence **per-sample > curator-escalation > whole-field > ENA**). `new_fills` filled a blank "
          "ENA cell; `overrides` replaced a real ENA value (only per-sample does this). Completeness is "
          "placeholder-stripped.\n",
          "| field | base | enriched | agent fills | new | overrides | per-sample | escalation | whole-field |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        md.append(f"| {r['field']} | {r['base_complete']:.3f} | **{r['enriched_complete']:.3f}** | "
                  f"{r['agent_fills']} | {r['new_fills']} | {r['overrides']} | {r['per_sample']} | "
                  f"{r['curator_escalation']} | {r['whole_field']} |")
    md += ["\n## Study-level grades (broadcast to every sample in the study)\n",
           "Two **new** columns (`study_setting`, `amr_study`) carry the agent's per-study graded value, "
           "filled for every sample in the study (blank where `not_gradeable`). These match the metadata_v2 "
           "column names; the manual pipeline fills them per-study from the study_level sheet.\n",
           "| column | graded studies | samples filled | value distribution |",
           "|---|---|---|---|"]
    for gs in grade_summary:
        dist = ", ".join(f"{k} {v}" for k, v in gs["values"].items()) or "—"
        md.append(f"| {gs['field']} | {gs['graded_studies']} | {gs['samples_filled']} | {dist} |")
    md.append("\nOutputs: full-width `enriched_collated_<TAG>.tsv` (drop-in for `qc_add_metadata`), "
              "long-format `enriched_provenance_<TAG>.tsv` (every changed clinical-field cell), this summary.\n")
    md_path.write_text("\n".join(md))

    print(res.to_string(index=False), file=sys.stderr)
    print(f"\nWrote:\n  {enriched_path}\n  {prov_path}\n  {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
