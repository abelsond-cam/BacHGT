"""Linkability report for curator-provided supplementary tables — which ones the engine can anchor.

Curator tables arrive in a mix of formats (.xlsx/.xls/.csv/.tsv/.txt/.docx/.pdf), keyed on whatever
identifier the authors used, with fields named all sorts of things. Two things must hold before a table
can fill anything: it must **parse**, and at least one of its columns must **anchor** — i.e. its values
match this study's ENA sample identifiers (:func:`engine.sample_extractor.pick_accession_column`, which is
name-agnostic and by-value). This script checks both **deterministically (no LLM)** for every table in the
manual-supp folders and reports, per table:

* **parse** — did the format parser yield any table (all sheets/embedded tables counted);
* **anchor** — the best column's distinct id-matches vs the study's ENA ids, and whether it clears the
  join threshold (:data:`engine.sample_extractor.MIN_ACCESSION_HITS`);
* **why-not** — parse-failed / study-not-in-cohort / no-matching-id-column (the "identifier not always
  there" case) — so a table that can't be linked is visible, not silently dropped.

Field-name mapping is a separate LLM step (the per-sample cascade); linkability is the necessary
precondition, tracked here. Writes ``diagnostics/table_linkability.{md,tsv}``. Read-only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import sample_extractor as sx
from bac_metadata.bac_agentic_metadata.engine.local_supplements import SUPP_EXTS
from bac_metadata.bac_agentic_metadata.engine.supplementary import _parse_member

ENGINE_APPS = Path(__file__).resolve().parents[1] / "applications"


def _supp_files(dirs: list[Path]) -> dict[str, list[Path]]:
    """Map study accession (file stem) → ALL its supp file(s) across the dirs (every format is reported).

    A study can carry several tables (e.g. a project_k ``.csv`` that doesn't anchor plus a curator ``.xlsx``
    that does) — the report shows each, so a multi-format study's linkable file is never hidden.
    """
    out: dict[str, list[Path]] = {}
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPP_EXTS:
                out.setdefault(f.stem, []).append(f)
    return out


def linkability(app_dir: Path, base_path: Path) -> pd.DataFrame:
    """Deterministic parse+anchor check for every curator supp table; one row per table file."""
    data_dir = app_dir / "data"
    dirs = [app_dir / "manual_supp_tables", data_dir / "sample_lv_attributes" / "manual_download_supp"]
    files = _supp_files(dirs)

    idcols = list(sx._ID_COLUMNS)
    want = ["study_accession", "sample_accession", *idcols]
    header = pd.read_csv(base_path, nrows=0).columns.tolist()
    usecols = [c for c in want if c in header]
    base = pd.read_csv(base_path, dtype=str, usecols=usecols, low_memory=False, keep_default_na=False)
    id_by_study = {acc: set(sx.build_accession_to_sample(g)) for acc, g in base.groupby("study_accession")}

    rows = []
    for acc, paths in sorted(files.items()):
        for path in paths:
            fmt = path.suffix.lower()
            try:
                tables = _parse_member(acc, path.name, path.read_bytes())
            except Exception as e:  # noqa: BLE001 - arbitrary curator files; a crash is itself a finding
                rows.append({"study": acc, "file": path.name, "format": fmt, "parsed_tables": 0,
                             "n_rows": 0, "anchored": False, "n_matched": 0, "id_column": "",
                             "status": f"PARSE_ERROR: {type(e).__name__}"})
                continue
            if not tables:
                rows.append({"study": acc, "file": path.name, "format": fmt, "parsed_tables": 0, "n_rows": 0,
                             "anchored": False, "n_matched": 0, "id_column": "", "status": "PARSE_EMPTY"})
                continue
            n_rows = max(t.df.shape[0] for t in tables)
            ids = id_by_study.get(acc)
            if ids is None:
                rows.append({"study": acc, "file": path.name, "format": fmt, "parsed_tables": len(tables),
                             "n_rows": n_rows, "anchored": False, "n_matched": 0, "id_column": "",
                             "status": "STUDY_NOT_IN_COHORT"})
                continue
            best_hits, best_col = 0, -1
            for t in tables:
                col, hits = sx.pick_accession_column(t, ids)
                if hits > best_hits:
                    best_hits, best_col = hits, col
            anchored = best_hits >= sx.MIN_ACCESSION_HITS
            status = "LINKED" if anchored else ("NO_ID_MATCH" if best_hits == 0
                                                else f"WEAK_MATCH({best_hits}<{sx.MIN_ACCESSION_HITS})")
            rows.append({"study": acc, "file": path.name, "format": fmt, "parsed_tables": len(tables),
                         "n_rows": n_rows, "anchored": anchored, "n_matched": best_hits,
                         "id_column": best_col if anchored else "", "status": status})
    return pd.DataFrame(rows)


def _render_md(df: pd.DataFrame) -> str:
    """Render the linkability table, LINKED last so the problems are up top."""
    order = {"LINKED": 9}
    d = df.assign(_o=df["status"].map(lambda s: order.get(s, 0))).sort_values(
        ["_o", "n_matched"], ascending=[True, False]).drop(columns="_o")
    n = len(df)
    linked = int(df["anchored"].sum())
    by_status = df["status"].str.replace(r"\(.*\)", "", regex=True).value_counts().to_dict()
    by_fmt = df.groupby("format")["anchored"].agg(["size", "sum"])
    lines = [
        "# Curator supp-table linkability (deterministic — no LLM)",
        "",
        "Auto-generated by `evaluation/table_linkability.py`. A table must **parse** and **anchor** (a "
        "column whose values match this study's ENA sample ids) before the per-sample cascade can map its "
        "fields. Anchoring is by value, name-agnostic. Field-name mapping is the separate LLM step.",
        "",
        f"**{linked}/{n} tables link.** Status counts: {by_status}.",
        "",
        "By format (linked / total):",
        *[f"- `{fmt}`: {int(r['sum'])}/{int(r['size'])}" for fmt, r in by_fmt.iterrows()],
        "",
        "| status | study | file | format | rows | id-matches | id_col |",
        "|---|---|---|---|--:|--:|--:|",
    ]
    for _, r in d.iterrows():
        lines.append(f"| {r['status']} | {r['study']} | `{r['file']}` | {r['format']} | {r['n_rows']} | "
                     f"{r['n_matched']} | {r['id_column']} |")
    lines += ["", "**NO_ID_MATCH** = the table parsed but no column's values match our ENA ids for this "
              "study (the 'identifier not always there' case — the key may be a strain name absent from "
              "ENA, or a two-table manifest join). **STUDY_NOT_IN_COHORT** = the accession isn't in the "
              "base table. **PARSE_EMPTY/ERROR** = the format parser found no table.", ""]
    return "\n".join(lines)


def main() -> None:
    """Build the linkability report and write ``diagnostics/table_linkability.{md,tsv}``."""
    p = argparse.ArgumentParser(description="Deterministic linkability check for curator supp tables.")
    p.add_argument("--app", default="klebsiella", help="Application under applications/ (default klebsiella).")
    p.add_argument("--base", default=None, help="Base table CSV (default applications/<app>/data/inputs/base_table.csv).")
    args = p.parse_args()

    app_dir = ENGINE_APPS / args.app
    base_path = Path(args.base) if args.base else app_dir / "data" / "inputs" / "base_table.csv"
    df = linkability(app_dir, base_path)
    if df.empty:
        sys.exit("no supp tables found")

    diagnostics = app_dir / "data" / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / "table_linkability.md").write_text(_render_md(df))
    df.to_csv(diagnostics / "table_linkability.tsv", sep="\t", index=False)
    linked = int(df["anchored"].sum())
    print(f"Wrote diagnostics/table_linkability.{{md,tsv}} — {linked}/{len(df)} tables link", file=sys.stderr)
    print(df.sort_values("anchored", ascending=False)[
        ["study", "format", "anchored", "n_matched", "status"]].to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
