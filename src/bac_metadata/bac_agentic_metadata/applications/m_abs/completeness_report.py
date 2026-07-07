"""Raw-vs-filled completeness bar chart + cf_status / per_sample_AST summary for the M. abscessus master.

Reads the aggregated curated master (post carry-forward fill) and the raw base table, measures
per-field completeness before and after agentic fills for the five reported fields (host,
isolation_source, country, collection_date, cf_status; smoking excluded), and reports the cf_status
CF/non-CF split and the study-level per_sample_AST tally.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from engine.backfill import strip_placeholders

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MASTER = DATA / "curated" / "metadata_curated_master.tsv"
BASE = DATA / "inputs" / "base_table.csv"  # raw full-width base
GRADES = DATA / "curated" / "curated_grades.tsv"
OUT_PNG = DATA / "diagnostics" / "completeness_raw_vs_filled.png"

FIELDS = ["host", "isolation_source", "country", "collection_date", "cf_status"]


def completeness(series: pd.Series) -> float:
    """Fraction of non-placeholder cells."""
    clean = strip_placeholders(series)
    return float(clean.notna().mean()) * 100.0


def main() -> None:
    master = pd.read_csv(MASTER, sep="\t", dtype=str, keep_default_na=False)
    n = len(master)
    print(f"master: {n} samples, {master['study_accession'].nunique()} studies")

    # raw base: locate whichever base file exists, then restrict to the master's taxon sample set so
    # raw and filled share the same denominator (base carries non-taxon rows the master drops).
    base_path = BASE if BASE.exists() else next(DATA.glob("base_table*.csv"), None)
    raw = pd.read_csv(base_path, dtype=str, keep_default_na=False) if base_path else None
    if raw is not None and "sample_accession" in raw and "sample_accession" in master:
        keys = set(master["sample_accession"])
        raw = raw[raw["sample_accession"].isin(keys)]
    print(f"raw base: {base_path} ({0 if raw is None else len(raw)} taxon-matched rows)")

    rows = []
    for f in FIELDS:
        filled = completeness(master[f]) if f in master else float("nan")
        raw_c = completeness(raw[f]) if raw is not None and f in raw else float("nan")
        rows.append((f, raw_c, filled))
        print(f"  {f:18s} raw={raw_c:5.1f}%  filled={filled:5.1f}%")

    # ---- bar chart ----
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    labels = [r[0] for r in rows]
    raw_vals = [r[1] for r in rows]
    fill_vals = [r[2] for r in rows]
    x = range(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([i - w / 2 for i in x], raw_vals, w, label="raw (ENA)", color="#b0b7c3")
    ax.bar([i + w / 2 for i in x], fill_vals, w, label="filled (agentic)", color="#2f6fb3")
    for i, (rv, fv) in enumerate(zip(raw_vals, fill_vals)):
        ax.text(i - w / 2, rv + 1, f"{rv:.0f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + w / 2, fv + 1, f"{fv:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("completeness (%)")
    ax.set_ylim(0, 105)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_title(f"M. abscessus metadata completeness — raw vs agentic fill (n={n})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    print(f"\nwrote {OUT_PNG}")

    # ---- cf_status split ----
    print("\n=== cf_status (CF vs non-CF) ===")
    cf = strip_placeholders(master["cf_status"]).dropna().astype(str).str.strip().str.lower()
    norm = cf.map(lambda v: "CF" if v in {"1", "cf", "yes", "true"} else ("non-CF" if v in {"0", "non-cf", "no", "false"} else v))
    vc = norm.value_counts()
    total_known = int(vc.sum())
    for k, v in vc.items():
        print(f"  {k:8s} {v:5d}  ({100*v/total_known:.1f}% of known, {100*v/n:.1f}% of all)")
    print(f"  known total: {total_known}/{n} ({100*total_known/n:.1f}%)")

    # ---- per_sample_AST (study level) ----
    print("\n=== per_sample_AST (study-level grade) ===")
    grades = pd.read_csv(GRADES, sep="\t", dtype=str, keep_default_na=False)
    ast = grades["per_sample_AST__value"].str.strip().str.lower().replace("", "blank")
    for k, v in ast.value_counts().items():
        print(f"  {k:12s} {v:4d}")


if __name__ == "__main__":
    main()
