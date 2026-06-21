"""Categorise the curator gold (ready_to_merge) into whole-field vs per-sample — Klebsiella, read-only.

David's account of how the curators worked: per project they took the ENA slice missing the 4 fields,
checked the paper, and **either** annotated all samples to one value (whole-field — paper says uniform,
usually faeces/blood or a tight date window) **or** transcribed per-sample values from the paper's table.
The reviewed `*ready_to_merge*` files are that gold, so they tell us — per study — whether the curator's
answer was whole-field (one distinct value) or per-sample (many), and whether they added data over ENA.

That is the correct lens on our completeness gap:

* **whole-field-uniform gold** (curator added & 1 distinct value) → the gold for OUR step-a. Cross-check
  whether `backfill_applied` (whole-field) actually fired for the study. The tiny iso step-a (+0.03)
  predicts we under-fire — this quantifies the whole-field iso we are *missing* (a step-a/grader gap).
* **per-sample-multiple gold** (curator added & ≥2 distinct values) → genuinely per-sample → per-sample's
  job (its fetch/parse reach is then tested separately, only on this bucket).
* **no-add** → curator didn't improve on ENA → not part of the gap.

Reads ready_to_merge via `metadata_collation`; never feeds them to the extractor (they are the answer).
Writes ``data/curator_gold_report.{md,tsv}``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
FIELDS = ("isolation_source", "collection_date")


def _read_ready_to_merge(folds: set[str]) -> pd.DataFrame:
    """Concatenate the curators' ready_to_merge per-sample rows (study/sample + the 4 fields), train+val."""
    from bac_metadata.pp import metadata_collation as mc

    keep = {"study_accession", "sample_accession", "isolation_source", "collection_date", "country", "host"}
    frames = []
    for rec in mc.find_ready_to_merge_files(mc.ENA_PROJECT_DIR, verbose=False):
        try:
            df, _ = mc._read_ready_to_merge_file(rec.file_path)
        except Exception as exc:  # noqa: BLE001 - skip a malformed curator file, keep going
            print(f"  skip {rec.file_path}: {exc}", file=sys.stderr)
            continue
        cols = [c for c in keep if c in df.columns]
        if "study_accession" in cols and "sample_accession" in cols:
            frames.append(df[cols])
    rtm = pd.concat(frames, ignore_index=True).drop_duplicates("sample_accession")
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    keep_studies = set(split[split["fold"].isin(folds)]["study_accession"])
    return rtm[rtm["study_accession"].isin(keep_studies)]


def _base(folds: set[str]) -> pd.DataFrame:
    """Raw ENA per-sample input (the pre-curation completeness to compare ready_to_merge against)."""
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    base = KlebCollationSource(keep_columns=("sample_accession",)).states()["base"]
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    return base[base["study_accession"].isin(keep)].drop_duplicates("sample_accession")


def _step_a_fired(backfill_path: Path) -> dict[str, set[str]]:
    """Map field → set of studies where our whole-field step-a actually filled it."""
    out = {f: set() for f in FIELDS}
    if backfill_path.exists():
        df = pd.read_csv(backfill_path, sep="\t", dtype=str)
        for f, g in df.groupby("field"):
            if f in out:
                out[f] = set(g["study_accession"])
    return out


def main() -> None:
    """Categorise each study's curator gold and attribute the iso/date gap to the right cause."""
    p = argparse.ArgumentParser(description="Categorise curator gold (whole-field vs per-sample) — Klebsiella.")
    p.add_argument("--fold", default="train,val")
    p.add_argument("--backfill", default=str(DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_applied.tsv"))
    p.add_argument("--gap-report", default=str(DATA_DIR / "diagnostics" / "backfill_gap_report.tsv"))
    p.add_argument("--report-prefix", default="curator_gold")
    args = p.parse_args()

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    rtm = _read_ready_to_merge(folds)
    base = _base(folds).set_index("sample_accession")
    step_a = _step_a_fired(Path(args.backfill))
    gap = pd.read_csv(args.gap_report, sep="\t", dtype=str).set_index("study_accession") if Path(args.gap_report).exists() else pd.DataFrame()
    print(f"ready_to_merge samples {sorted(folds)}: {len(rtm)} across {rtm['study_accession'].nunique()} studies", file=sys.stderr)

    rows = []
    for acc, g in rtm.groupby("study_accession"):
        rec = {"study_accession": acc, "n_rtm_samples": len(g)}
        for f in FIELDS:
            cur = backfill.strip_placeholders(g[f]) if f in g.columns else pd.Series(pd.NA, index=g.index, dtype="string")
            inp = backfill.strip_placeholders(base.reindex(g["sample_accession"])[f]) if f in base.columns else \
                pd.Series(pd.NA, index=g.index, dtype="string")
            inp.index = g.index
            n_added = int((cur.notna().to_numpy() & inp.isna().to_numpy()).sum())
            distinct = int(cur.dropna().str.lower().str.strip().nunique())
            if n_added == 0:
                bucket = "no_add"
            elif distinct <= 1:
                bucket = "whole_field_uniform"
            else:
                bucket = "per_sample_multiple"
            gcol = f"{f}_gap"
            rec[f"{f}_bucket"] = bucket
            rec[f"{f}_n_added"] = n_added
            rec[f"{f}_distinct"] = distinct
            rec[f"{f}_step_a_fired"] = acc in step_a[f]
            rec[f"{f}_gap"] = int(gap.loc[acc, gcol]) if (len(gap) and acc in gap.index and gcol in gap.columns) else 0
        rows.append(rec)
    res = pd.DataFrame(rows)
    diag_dir = DATA_DIR / "diagnostics"
    res.to_csv(diag_dir / f"{args.report_prefix}_report.tsv", sep="\t", index=False)

    md = [f"# Curator-gold categorisation: whole-field vs per-sample ({', '.join(sorted(folds))})\n",
          f"{len(res)} studies with a ready_to_merge file. For each field, the curator's pattern (did they "
          "add data over ENA, and is it one value or many) tells us whether their answer was whole-field "
          "(our step-a's job) or per-sample (per-sample's job).\n"]
    for f in FIELDS:
        bc = res.groupby(f"{f}_bucket").agg(studies=("study_accession", "count"), gap=(f"{f}_gap", "sum"))
        wf = res[res[f"{f}_bucket"] == "whole_field_uniform"]
        wf_fired = int(wf[f"{f}_step_a_fired"].sum())
        md.append(f"## {f}\n")
        md.append("| curator bucket | studies | residual gap (samples) |")
        md.append("|---|---|---|")
        for b, r in bc.iterrows():
            md.append(f"| {b} | {int(r['studies'])} | {int(r['gap'])} |")
        md.append(f"\n- **whole-field-uniform studies: {len(wf)}; our step-a actually fired on "
                  f"{wf_fired}/{len(wf)}** → we MISS {len(wf) - wf_fired} whole-field-fillable studies "
                  f"(gap {int(wf[~wf[f'{f}_step_a_fired']][f'{f}_gap'].sum())} samples) that are a step-a "
                  "issue, not per-sample.\n")
    (diag_dir / f"{args.report_prefix}_report.md").write_text("\n".join(md) + "\n")
    print(f"Wrote diagnostics/{args.report_prefix}_report.{{md,tsv}}", file=sys.stderr)
    for f in FIELDS:
        print(f"\n{f} buckets:\n{res.groupby(f'{f}_bucket')[f'{f}_gap'].agg(['count','sum']).to_string()}", file=sys.stderr)


if __name__ == "__main__":
    main()
