"""Per-study date/source completeness-gap diagnosis vs metadata_v2 (Klebsiella, read-only).

The aggregate completeness report shows we trail v2 on `collection_date` / `isolation_source`; this
pins the gap down *per study* and attaches the evidence needed to attribute its cause. For each
train+val study and each of the two hard fields it computes:

* ``v2_has``   — samples whose curated `*_parsed` value is present (placeholder-stripped);
* ``we_have``  — samples we complete (ENA baseline ∪ whole-field ∪ per-sample);
* ``residual_gap`` — samples where **v2 has a value and we don't** (the real shortfall).

Each gap study is joined to its per-sample outcome (`per_sample_outcomes.tsv`: direct/two_hop/abstained + the
abstain reason) and a **curator-folder inventory** (the `ENA_projects/<acc>/` folder: a reviewed
`*ready_to_merge*` file and the curator's source table(s) — with coarse flags for whether the source
table carries a date/source column and an ENA accession). This sets up the fetch-vs-extraction test
(`diagnostics/diagnose_per_sample_local.py`); curator files are a **diagnostic only**, never a production source.

Writes ``data/backfill_gap_report.{md,tsv}``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.supplementary import ACCESSION_RE

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
GAP_FIELDS = ("collection_date", "isolation_source")
_ACC_HEADER_RE = re.compile(r"accession|biosample|\brun\b|\bena\b|sample.?id", re.IGNORECASE)
_DATE_HEADER_RE = re.compile(r"date|year|collect", re.IGNORECASE)
_SOURCE_HEADER_RE = re.compile(r"source|specimen|isolat|sample.?type|\bsite\b|body", re.IGNORECASE)


def _load_base(folds: set[str]) -> pd.DataFrame:
    """Raw per-sample ENA for the folds (one row per sample), via the collation source."""
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    base = KlebCollationSource(keep_columns=("sample_accession",)).states()["base"]
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    return base[base["study_accession"].isin(keep)].drop_duplicates("sample_accession")


def _filled(path: Path) -> dict[str, set[str]]:
    """Map field → set of sample_accessions filled in an applied-changes file."""
    out: dict[str, set[str]] = {f: set() for f in GAP_FIELDS}
    if path.exists():
        df = pd.read_csv(path, sep="\t", dtype=str)
        for f, g in df.groupby("field"):
            if f in out:
                out[f] = set(g["sample_accession"])
    return out


def _read_header(path: Path) -> list[str]:
    """Best-effort column headers of a source table (csv/tsv/xlsx); [] on failure."""
    low = path.name.lower()
    try:
        if low.endswith((".csv", ".tsv")):
            sep = "\t" if low.endswith(".tsv") else ","
            return [str(c) for c in pd.read_csv(path, sep=sep, nrows=0).columns]
        if low.endswith((".xlsx", ".xls")):
            return [str(c) for c in pd.read_excel(path, nrows=0).columns]
    except Exception:  # noqa: BLE001 - curator tables are arbitrarily malformed
        return []
    return []


def _has_accession_value(path: Path) -> bool:
    """True if the first rows of a source table contain ENA accession-shaped cells."""
    low = path.name.lower()
    try:
        if low.endswith((".csv", ".tsv")):
            sep = "\t" if low.endswith(".tsv") else ","
            df = pd.read_csv(path, sep=sep, nrows=40, dtype=str)
        elif low.endswith((".xlsx", ".xls")):
            df = pd.read_excel(path, nrows=40, dtype=str)
        else:
            return False
    except Exception:  # noqa: BLE001
        return False
    return bool(ACCESSION_RE.search(" ".join(df.astype(str).to_numpy().ravel()[:4000])))


def _curator_inventory(ena_project_dir: Path, wanted: set[str]) -> dict[str, dict]:
    """Map each WANTED study accession → its ENA_projects folder inventory (ready_to_merge + source tables)."""
    inv: dict[str, dict] = {}
    if not ena_project_dir.is_dir():
        return inv
    for entry in os.scandir(ena_project_dir):
        if not entry.is_dir():
            continue
        accs = re.findall(r"PRJ[EDN][A-Z]\d+", entry.name)
        if not any(a in wanted for a in accs):
            continue
        files = list(os.scandir(entry.path))
        rtm = [f.name for f in files if "ready_to_merge" in f.name.lower()]
        srcs = [Path(f.path) for f in files
                if f.name.lower().endswith((".csv", ".tsv", ".xlsx", ".xls")) and "ready_to_merge" not in f.name.lower()]
        # Coarse flags from the source tables' headers + an accession value scan.
        headers = [h for s in srcs for h in _read_header(s)]
        rec = {
            "folder": entry.name,
            "has_ready_to_merge": bool(rtm),
            "n_source_tables": len(srcs),
            "source_files": ";".join(s.name for s in srcs),
            "src_has_date_col": any(_DATE_HEADER_RE.search(h) for h in headers),
            "src_has_source_col": any(_SOURCE_HEADER_RE.search(h) for h in headers),
            "src_has_accession": any(_ACC_HEADER_RE.search(h) for h in headers) or any(_has_accession_value(s) for s in srcs),
        }
        for acc in accs:
            inv[acc] = rec
    return inv


def main() -> None:
    """Build the per-study date/source gap table + curator inventory and write the report."""
    p = argparse.ArgumentParser(description="Per-study date/source completeness-gap diagnosis (Klebsiella).")
    p.add_argument("--truth", required=True, help="metadata_v2 per-sample gold TSV (local path).")
    p.add_argument("--gold-suffix", default="_parsed")
    p.add_argument("--fold", default="train,val")
    p.add_argument("--backfill", default=str(DATA_DIR / "study_lv_attributes" / "whole_study_backfill" / "backfill_applied.tsv"))
    p.add_argument("--per-sample", default=str(DATA_DIR / "sample_lv_attributes" / "per_sample" / "per_sample_applied.tsv"))
    p.add_argument("--outcomes", default=str(DATA_DIR / "sample_lv_attributes" / "per_sample" / "per_sample_outcomes.tsv"))
    p.add_argument("--report-prefix", default="backfill_gap")
    args = p.parse_args()

    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    base = _load_base(folds)
    step_a, step_b = _filled(Path(args.backfill)), _filled(Path(args.per_sample))
    gold_cols = {f: f"{f}{args.gold_suffix}" for f in GAP_FIELDS}
    header = pd.read_csv(args.truth, sep="\t", nrows=0).columns.tolist()
    key = "sample_accession" if "sample_accession" in header else "Sample"
    gold = pd.read_csv(args.truth, sep="\t", dtype=str, usecols=[key] + [c for c in gold_cols.values() if c in header],
                       low_memory=False).drop_duplicates(key).set_index(key)

    from bac_metadata.pp import metadata_collation as mcoll

    outcomes = pd.read_csv(args.outcomes, sep="\t", dtype=str).set_index("study_accession") if Path(args.outcomes).exists() else pd.DataFrame()
    print(f"Samples {sorted(folds)}: {len(base)}", file=sys.stderr)

    rows = []
    for acc, g in base.groupby("study_accession"):
        samples = g["sample_accession"]
        rec = {"study_accession": acc, "n_samples": len(g)}
        total_gap = 0
        for f in GAP_FIELDS:
            base_present = backfill.strip_placeholders(g[f]).notna().to_numpy() if f in g.columns else \
                pd.Series(False, index=g.index).to_numpy()
            we = base_present | samples.isin(step_a[f]).to_numpy() | samples.isin(step_b[f]).to_numpy()
            gcol = gold_cols[f]
            v2 = samples.map(backfill.strip_placeholders(gold[gcol])).notna().to_numpy() if gcol in gold.columns else \
                pd.Series(False, index=g.index).to_numpy()
            gap = int((v2 & ~we).sum())
            rec[f"{f}_v2"], rec[f"{f}_we"], rec[f"{f}_gap"] = int(v2.sum()), int(we.sum()), gap
            total_gap += gap
        rec["total_gap"] = total_gap
        oc = outcomes.loc[acc].to_dict() if (len(outcomes) and acc in outcomes.index) else {}
        rec["per_sample"] = oc.get("method", "no_outcome")
        rec["per_sample_note"] = str(oc.get("note", ""))[:80]
        rows.append(rec)

    # Curator-folder inventory only for the gap studies (avoids scanning irrelevant OneDrive folders).
    wanted = {r["study_accession"] for r in rows if r["total_gap"] > 0}
    inventory = _curator_inventory(Path(mcoll.ENA_PROJECT_DIR), wanted)
    print(f"Gap studies: {len(wanted)}; curator folders matched: {len(inventory)}", file=sys.stderr)
    for rec in rows:
        inv = inventory.get(rec["study_accession"], {})
        rec["curator_folder"] = bool(inv)
        rec["src_tables"] = inv.get("n_source_tables", 0)
        rec["src_has_date"] = inv.get("src_has_date_col", False)
        rec["src_has_source"] = inv.get("src_has_source_col", False)
        rec["src_has_accession"] = inv.get("src_has_accession", False)

    res = pd.DataFrame(rows).sort_values("total_gap", ascending=False)
    res.to_csv(DATA_DIR / "diagnostics" / f"{args.report_prefix}_report.tsv", sep="\t", index=False)
    gap = res[res["total_gap"] > 0]
    tot = {f: int(res[f"{f}_gap"].sum()) for f in GAP_FIELDS}

    md = [f"# Per-study date/source completeness gap vs metadata_v2 ({', '.join(sorted(folds))})\n",
          f"Total residual gap (samples v2 has & we don't): **collection_date {tot['collection_date']}**, "
          f"**isolation_source {tot['isolation_source']}**, over {len(gap)} studies with any gap.\n",
          "Top gap studies (residual = v2 has a value and we don't):\n",
          "| study | n | date gap | source gap | per-sample | curator src tables | src date col | src source col | src accession |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in gap.head(25).iterrows():
        md.append(f"| {r['study_accession']} | {r['n_samples']} | {r['collection_date_gap']} | "
                  f"{r['isolation_source_gap']} | {r['methodb']} | {r['src_tables']} | "
                  f"{'Y' if r['src_has_date'] else '·'} | {'Y' if r['src_has_source'] else '·'} | "
                  f"{'Y' if r['src_has_accession'] else '·'} |")
    md.append("\n- **src date/source col** = a curator source table has a date/source-like column; "
              "**src accession** = it carries an ENA accession (directly joinable) vs isolate-keyed only.")
    (DATA_DIR / "diagnostics" / f"{args.report_prefix}_report.md").write_text("\n".join(md) + "\n")
    print(f"Wrote {args.report_prefix}_report.{{md,tsv}}; total gap date={tot['collection_date']} "
          f"source={tot['isolation_source']}", file=sys.stderr)


if __name__ == "__main__":
    main()
