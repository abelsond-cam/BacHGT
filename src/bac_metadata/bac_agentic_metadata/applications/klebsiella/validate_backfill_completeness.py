"""Completeness of the per-sample backfill vs the curated gold (metadata_v2) — Klebsiella.

`validate_backfill_values` asks *are the filled values right* (accuracy). This asks the complementary
question: *how much of each per-sample field did we COMPLETE* — the fraction of samples that end up with
a real value after our backfill, against what ENA gave us (baseline) and what the manual curation
achieved in v2 (the target).

Completeness is measured on **placeholder-stripped** values on every side (ENA's "not available" /
"not provided" / "missing" / … text means *absent*; v2's ``*_parsed`` columns already have these
removed), so the chain to v2-style completion is honest for both the manual and the agent case.

Per field (country / collection_date / isolation_source / host) over the fold's samples:

* **baseline** = ENA non-null (stripped);
* **agent**    = baseline OR an agent backfill (whole-field ``backfill_applied`` + per-sample ``per_sample_applied``);
* **v2 (gold)** = curated ``*_parsed`` non-null (stripped);
* **gap-closed** = (agent − baseline) / (v2 − baseline) — how much of the manual-achievable gain we made.

Writes ``data/<report-prefix>_report.{md,tsv}`` (default ``backfill_completeness``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
FIELDS = backfill.FIELDS


def _load_base(input_path: str | None, folds: set[str]) -> pd.DataFrame:
    """Return the raw per-sample ENA table for the requested folds (one row per sample)."""
    if input_path:
        base = pd.read_csv(input_path, sep="\t", dtype=str, low_memory=False)
    else:
        from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

        base = KlebCollationSource(keep_columns=("sample_accession",)).states()["base"]
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    base = base[base["study_accession"].isin(keep)].drop_duplicates("sample_accession")
    return base


def _filled_samples(paths: list[str]) -> dict[str, set[str]]:
    """Union of per-sample fills per field across the applied-changes files that exist."""
    out: dict[str, set[str]] = {f: set() for f in FIELDS}
    for p in paths:
        if not Path(p).exists():
            continue
        df = pd.read_csv(p, sep="\t", dtype=str)
        if {"field", "sample_accession"} <= set(df.columns):
            for f, g in df.groupby("field"):
                if f in out:
                    out[f] |= set(g["sample_accession"])
    return out


def _read_gold(truth_path: str, fields: list[str]) -> pd.DataFrame:
    """Read the sample key + the needed gold columns from the large metadata_v2 table."""
    header = pd.read_csv(truth_path, sep="\t", nrows=0).columns.tolist()
    key = "sample_accession" if "sample_accession" in header else ("Sample" if "Sample" in header else None)
    if key is None:
        sys.exit(f"metadata_v2 has no sample_accession/Sample column; header starts {header[:8]}")
    usecols = [key] + [c for c in fields if c in header]
    gold = pd.read_csv(truth_path, sep="\t", dtype=str, usecols=usecols, low_memory=False)
    return gold.rename(columns={key: "sample_accession"})


def main() -> None:
    """Compute per-field completeness (baseline / agent / v2) over a fold and write the report."""
    p = argparse.ArgumentParser(description="Per-sample backfill completeness vs metadata_v2 (Klebsiella).")
    p.add_argument("--input", default=None, help="Explicit raw ENA per-sample TSV (else load_collated_metadata).")
    p.add_argument("--backfill", default=str(DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_applied.tsv"), help="Whole-field fills.")
    p.add_argument("--per-sample", default=str(DATA_DIR / "sample_lv_attributes" / "per_sample" / "per_sample_applied.tsv"), help="Per-sample fills.")
    p.add_argument("--escalation", default=str(DATA_DIR / "study_lv_attributes" / "escalation" / "escalation_applied.tsv"),
                   help="Curator-escalation whole-field fills (skipped if the file is absent).")
    p.add_argument("--truth", required=True, help="metadata_v2 per-sample gold TSV (local path).")
    p.add_argument("--gold-suffix", default="_parsed", help="Gold column suffix per field (default '_parsed').")
    p.add_argument("--fold", default="train,val", help="Comma-separated folds (default train,val).")
    p.add_argument("--report-prefix", default="backfill_completeness", help="Report basename under data/.")
    args = p.parse_args()

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    base = _load_base(args.input, folds)
    step_a = _filled_samples([args.backfill])    # whole-field
    step_b = _filled_samples([args.per_sample])  # per-sample
    step_c = _filled_samples([args.escalation])  # curator escalation (empty if not yet applied)
    gold_cols = {f: f"{f}{args.gold_suffix}" for f in FIELDS}
    gold = _read_gold(args.truth, list(gold_cols.values())).drop_duplicates("sample_accession").set_index("sample_accession")
    n = len(base)
    print(f"Samples in {sorted(folds)}: {n}; gold rows: {len(gold)}", file=sys.stderr)

    rows = []
    for f in FIELDS:
        base_present = backfill.strip_placeholders(base[f]).notna().to_numpy() if f in base.columns else \
            pd.Series(False, index=base.index).to_numpy()
        after_a = base_present | base["sample_accession"].isin(step_a[f]).to_numpy()   # +whole-field
        after_b = after_a | base["sample_accession"].isin(step_b[f]).to_numpy()        # +per-sample
        after_c = after_b | base["sample_accession"].isin(step_c[f]).to_numpy()        # +escalation (= agent)
        gcol = gold_cols[f]
        if gcol in gold.columns:
            gmap = backfill.strip_placeholders(gold[gcol])
            v2_present = base["sample_accession"].map(gmap).notna().to_numpy()
        else:
            v2_present = pd.Series(False, index=base.index).to_numpy()
        bl, aa, ab, ac, v = base_present.mean(), after_a.mean(), after_b.mean(), after_c.mean(), v2_present.mean()
        gap_closed = (ac - bl) / (v - bl) if v > bl else float("nan")
        rows.append({"field": f, "n_samples": n,
                     "baseline": round(float(bl), 4), "after_whole_field": round(float(aa), 4),
                     "after_per_sample": round(float(ab), 4), "agent": round(float(ac), 4),
                     "v2": round(float(v), 4),
                     "gain_whole_field": round(float(aa - bl), 4), "gain_per_sample": round(float(ab - aa), 4),
                     "gain_escalation": round(float(ac - ab), 4),
                     "residual_gap": round(float(max(0.0, v - ac)), 4),
                     "gap_closed": round(float(gap_closed), 4)})
    res = pd.DataFrame(rows)

    md = [f"# Per-sample backfill completeness vs metadata_v2 ({', '.join(sorted(folds))})\n",
          f"Samples: **{n}**. Completeness = fraction with a real value (placeholder-stripped both sides; "
          "gold = curated `*_parsed`). Cumulative: **baseline** (ENA as deposited) → **+whole-field** "
          "(step-a) → **+per-sample** (step-b, = **agent**) → **v2** (manual target). **gap-closed** = "
          "(agent−baseline)/(v2−baseline); **residual_gap** = v2−agent (what manual still has and we don't).\n",
          "| field | baseline | +whole-field | +per-sample | +escalation (agent) | v2 (gold) | "
          "gain wf | gain ps | gain esc | residual gap | gap-closed |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        gc = f"{r['gap_closed']:.2f}" if pd.notna(r["gap_closed"]) else "—"
        md.append(f"| {r['field']} | {r['baseline']:.2f} | {r['after_whole_field']:.2f} | "
                  f"{r['after_per_sample']:.2f} | **{r['agent']:.2f}** | {r['v2']:.2f} | "
                  f"+{r['gain_whole_field']:.2f} | +{r['gain_per_sample']:.2f} | +{r['gain_escalation']:.2f} | "
                  f"{r['residual_gap']:.2f} | {gc} |")
    md.append("\n- **gain wf / ps / esc** isolate the whole-field, per-sample, and curator-escalation "
              "contributions; **residual gap** is the per-field completeness manual curation still has over "
              "us — the target of the gap diagnosis.")

    scorecard = DATA_DIR / "scorecard"
    (scorecard / f"{args.report_prefix}_report.md").write_text("\n".join(md) + "\n")
    res.to_csv(scorecard / f"{args.report_prefix}_report.tsv", sep="\t", index=False)
    print(f"Wrote scorecard/{args.report_prefix}_report.{{md,tsv}}", file=sys.stderr)
    print(res.to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
