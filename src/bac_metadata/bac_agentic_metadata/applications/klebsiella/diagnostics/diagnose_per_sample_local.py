"""Fetch-vs-extraction diagnostic: run per-sample's extractor on the curators' LOCAL source tables.

The per-study gap (`diagnostics/assess_backfill_gap.py`) shows date/source completeness we lack vs v2, concentrated
on studies where per-sample **abstained** — many of which DO have a curator source table (often accession-
keyed) in their `ENA_projects/<acc>/` folder. This runs the **existing** `engine.sample_extractor.
extract_study` on those LOCAL tables (bypassing the EPMC fetch) to split the gap:

* **fetch** — local extraction recovers the gapped samples ⇒ our extraction logic is fine; we simply
  couldn't fetch the table the curator had (generalisable remedy later = broader fetching);
* **extraction** — the local table has the field but we still don't recover it ⇒ a parse/map/join issue;
* **non-tabular / no local table** — the value isn't in any local table ⇒ curator used paper text.

Diagnostic harness ONLY — curator files are never a production source (they don't exist for unseen data).
The only model calls are the cached column-mapping ones inside `extract_study`. Writes
``data/diagnostics/per_sample_local_diagnosis.{md,tsv}``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
from bac_metadata.bac_agentic_metadata.engine import supplementary as supp
from bac_metadata.bac_agentic_metadata.engine.llm import DEFAULT_MODEL, UsageLimitError, make_llm

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
LLM_CACHE = DATA_DIR / "cache" / "llm"
GAP_FIELDS = ("collection_date", "isolation_source")
AUX = ("sample_accession", "run_accession", "secondary_sample_accession", "accession")


def _base(folds: set[str]):
    """Raw ENA base for the folds (one row per sample)."""
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    base = KlebCollationSource(keep_columns=AUX).states()["base"]
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    return base[base["study_accession"].isin(keep)].drop_duplicates("sample_accession")


def _acc_to_folder(ena_project_dir: Path) -> dict[str, Path]:
    """Map each study accession → its ENA_projects folder (handles compound folder names)."""
    out: dict[str, Path] = {}
    if ena_project_dir.is_dir():
        for entry in ena_project_dir.iterdir():
            if entry.is_dir():
                for acc in re.findall(r"PRJ[EDN][A-Z]\d+", entry.name):
                    out[acc] = entry
    return out


def main() -> None:
    """Run the fetch-vs-extraction diagnostic over the gap studies and write the report."""
    p = argparse.ArgumentParser(description="Per-sample fetch-vs-extraction diagnostic on curator local tables.")
    p.add_argument("--truth", required=True, help="metadata_v2 gold TSV (to define the gapped samples).")
    p.add_argument("--gold-suffix", default="_parsed")
    p.add_argument("--fold", default="train,val")
    p.add_argument("--backfill", default=str(DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_applied.tsv"))
    p.add_argument("--per-sample", default=str(DATA_DIR / "sample_lv_attributes" / "per_sample" / "per_sample_applied.tsv"))
    p.add_argument("--curator-gold", default=str(DATA_DIR / "diagnostics" / "curator_gold_report.tsv"),
                   help="Restrict to the per-sample-gold bucket (curator did per-sample, so per-sample's job).")
    p.add_argument("--backend", default="subscription", choices=["subscription", "api"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--report-prefix", default="per_sample_local_diagnosis")
    args = p.parse_args()

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    base = _base(folds)
    acc_cols = [c for c in AUX if c in base.columns]
    # per-study accession sets + acc→sample maps (for grounding the local extraction)
    sets: dict[str, set[str]] = {}
    maps: dict[str, dict[str, str]] = {}
    for acc, g in base.groupby("study_accession"):
        s: set[str] = set()
        for c in acc_cols:
            s |= set(g[c].dropna().astype(str).str.upper())
        sets[acc] = s
        maps[acc] = sx.build_accession_to_sample(g)

    # what we already complete (baseline ∪ whole-field ∪ per-sample), and what v2 has → the gap sample sets
    def _filled(path):
        out = {f: set() for f in GAP_FIELDS}
        if Path(path).exists():
            df = pd.read_csv(path, sep="\t", dtype=str)
            for f, gg in df.groupby("field"):
                if f in out:
                    out[f] = set(gg["sample_accession"])
        return out

    step_a, step_b = _filled(args.backfill), _filled(args.per_sample)
    header = pd.read_csv(args.truth, sep="\t", nrows=0).columns.tolist()
    key = "sample_accession" if "sample_accession" in header else "Sample"
    gcols = {f: f"{f}{args.gold_suffix}" for f in GAP_FIELDS}
    gold = pd.read_csv(args.truth, sep="\t", dtype=str, usecols=[key] + [c for c in gcols.values() if c in header],
                       low_memory=False).drop_duplicates(key).set_index(key)
    gold_present = {f: set(backfill.strip_placeholders(gold[gcols[f]]).dropna().index) for f in GAP_FIELDS if gcols[f] in gold.columns}

    gap_samples: dict[str, dict[str, set[str]]] = {}
    for acc, g in base.groupby("study_accession"):
        gap_samples[acc] = {}
        for f in GAP_FIELDS:
            base_present = set(g.loc[backfill.strip_placeholders(g[f]).notna(), "sample_accession"]) if f in g.columns else set()
            we = base_present | step_a[f] | step_b[f]
            study_samples = set(g["sample_accession"])
            gap_samples[acc][f] = (study_samples & gold_present.get(f, set())) - we

    from bac_metadata.pp import metadata_collation as mcoll

    acc_folder = _acc_to_folder(Path(mcoll.ENA_PROJECT_DIR))
    gap_studies = sorted([a for a in gap_samples if sum(len(s) for s in gap_samples[a].values()) > 0],
                         key=lambda a: -sum(len(s) for s in gap_samples[a].values()))
    # Restrict to the per-sample-gold bucket (curator did per-sample → this is per-sample's job; the
    # whole-field-uniform studies are a separate step-a issue, not a fetch/parse one).
    if Path(args.curator_gold).exists():
        cg = pd.read_csv(args.curator_gold, sep="\t")
        per_sample = set(cg.loc[(cg.get("isolation_source_bucket") == "per_sample_multiple")
                                | (cg.get("collection_date_bucket") == "per_sample_multiple"), "study_accession"])
        gap_studies = [a for a in gap_studies if a in per_sample]
        print(f"Per-sample-gold bucket: {len(gap_studies)} studies", file=sys.stderr)
    llm = make_llm(args.backend, model=args.model, cache_dir=LLM_CACHE)
    print(f"Gap studies: {len(gap_studies)}; running local extraction on those with a curator folder", file=sys.stderr)

    cg_idx = cg.set_index("study_accession")
    field_re = {"collection_date": re.compile(r"date|year|collect", re.I),
                "isolation_source": re.compile(r"source|specimen|isolat|\bsite\b|body|sample.?type", re.I)}

    def _table_has_field(tables, field) -> bool:
        for t in tables:
            for v in t.df.head(3).to_numpy().ravel():
                if isinstance(v, str) and field_re[field].search(v):
                    return True
        return False

    rows = []
    for i, acc in enumerate(gap_studies, 1):
        folder = acc_folder.get(acc)
        tables = supp.parse_local_tables(folder) if folder else []
        ex = None
        if tables:
            try:
                ex = sx.extract_study(acc, "LOCAL", tables, sets[acc], maps[acc], llm, model=args.model)
            except UsageLimitError as e:
                print(f"[{i}] usage limit; stopping: {e}", file=sys.stderr)
                break
        for field in GAP_FIELDS:  # attribute ONLY the field(s) the curator did per-sample for this study
            if (cg_idx.loc[acc, f"{field}_bucket"] if acc in cg_idx.index else None) != "per_sample_multiple":
                continue
            fgap = gap_samples[acc][field]
            n = len(fgap)
            if n == 0:
                continue
            rec_set = {f["sample_accession"] for f in ex.fills if f["field"] == field} & fgap if ex else set()
            rec_n = len(rec_set)
            if folder is None or not tables:
                verdict = "non_tabular_no_table"
            elif rec_n >= 0.5 * n:
                verdict = "fetch"                                  # local extraction works → we just couldn't fetch it
            elif (ex and ex.columns.get(field) is not None) or _table_has_field(tables, field):
                verdict = "parse"                                  # table has the field but map/join/value-check failed
            else:
                verdict = "non_tabular_text"                       # no table carries the field → curator used paper text
            rows.append({"study_accession": acc, "field": field, "gap": n, "recovered": rec_n,
                         "verdict": verdict, "local_tables": len(tables), "note": (ex.note[:80] if ex else "no table")})
            print(f"[{i}/{len(gap_studies)}] {acc} {field} gap={n} -> {verdict} rec={rec_n}", file=sys.stderr)

    res = pd.DataFrame(rows)
    res.to_csv(DATA_DIR / "diagnostics" / f"{args.report_prefix}.tsv", sep="\t", index=False)
    agg = res.groupby("verdict").agg(rows=("study_accession", "count"),
                                     gap_samples=("gap", "sum"), recovered=("recovered", "sum")).reset_index()
    by_field = res.groupby(["field", "verdict"])["gap"].sum().unstack(fill_value=0)
    total_gap = int(res["gap"].sum())
    fetch_gap = int(res.loc[res["verdict"] == "fetch", "gap"].sum())
    parse_gap = int(res.loc[res["verdict"] == "parse", "gap"].sum())

    md = [f"# Per-sample-gold gap: fetch vs parse vs non-tabular ({', '.join(sorted(folds))})\n",
          "For the studies the curator did **per-sample** (so per-sample's job), we ran the existing extractor "
          "on their LOCAL source tables to split the gap. **fetch** = local extraction recovers it (broader "
          "fetching would close it; extraction is sound); **parse** = the table has the field but our "
          "map/join/value-check failed (fixable); **non_tabular** = no local table carries it (curator used "
          "paper text).\n",
          f"Per-sample residual gap analysed = **{total_gap}** samples → fetch **{fetch_gap}** "
          f"({fetch_gap/total_gap:.0%}), parse **{parse_gap}** ({parse_gap/total_gap:.0%}), rest non-tabular.\n",
          "| verdict | (study,field) | gap samples | recovered (local) |", "|---|---|---|---|"]
    for _, r in agg.sort_values("gap_samples", ascending=False).iterrows():
        md.append(f"| {r['verdict']} | {int(r['rows'])} | {int(r['gap_samples'])} | {int(r['recovered'])} |")
    md.append("\n### by field (gap samples)\n")
    md.append("| field | " + " | ".join(by_field.columns) + " |")
    md.append("|---|" + "---|" * len(by_field.columns))
    for f, r in by_field.iterrows():
        md.append(f"| {f} | " + " | ".join(str(int(x)) for x in r) + " |")
    (DATA_DIR / "diagnostics" / f"{args.report_prefix}.md").write_text("\n".join(md) + "\n")
    print(f"\nWrote {args.report_prefix}.{{md,tsv}}; per-sample gap {total_gap} → fetch {fetch_gap} parse {parse_gap}", file=sys.stderr)


if __name__ == "__main__":
    main()
