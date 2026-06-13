"""Validate the Stage 1 output against the trusted curation-sheet columns.

Two reconciliations (see ``PIPELINE_PLAN.md`` — validate only against the trusted columns,
record disagreements rather than assuming the sheet is right):

* **Sizing** — per-accession ENA taxon counts vs the trusted A–K ``isolates_in_study`` /
  ``kleb_assemblies_in_paper``. Because one curation row can list several accessions, the
  comparison is made per *row* (summing the engine's per-accession counts across the row's
  accessions).
* **Completeness** — the engine's post-merge / normalised completeness vs the live
  ``parsed_per_project`` tab. Schema-tolerant: it locates the project key + any per-field
  completeness-like columns and reports overlaps; if credentials are absent it skips this half
  with a clear message rather than failing.

Writes ``data/stage1_validation_report.tsv`` and a short ``.md`` summary.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
FROZEN_STUDY_LEVEL = DATA_DIR / "study_level_metadata_all_combined_v1.0_20260105.csv"
SHEET_ID = "1wfMvlxyPW7zEQ9xD4OfxZWBFenALcEJlo_Fs8YQHnvk"
ACCESSION_RE = re.compile(r"\bPRJ[A-Z]+\d+\b")
CLINICAL = ("country", "collection_date", "isolation_source", "host")


def _explode_accessions(study_level: pd.DataFrame) -> pd.DataFrame:
    """Map each PRJ accession to its curation row (paper, isolates_in_study, kleb count)."""
    rows = []
    for idx, r in study_level.iterrows():
        accs = ACCESSION_RE.findall(str(r.get("study_accessions", "")))
        for acc in accs:
            rows.append(
                {
                    "study_accession": acc,
                    "row_id": idx,
                    "paper_short_title": r.get("paper_short_title", ""),
                    "isolates_in_study": pd.to_numeric(r.get("isolates_in_study"), errors="coerce"),
                    "kleb_assemblies_in_paper": pd.to_numeric(r.get("kleb_assemblies_in_paper"), errors="coerce"),
                    "n_accessions_in_row": len(accs),
                }
            )
    return pd.DataFrame(rows)


def _sizing_reconcile(stage1: pd.DataFrame, study_level: pd.DataFrame) -> pd.DataFrame:
    """Join engine sizing to the trusted columns and compute per-row agreement."""
    mapping = _explode_accessions(study_level)
    # Keep only the engine columns the reconcile needs, so split-carried columns
    # (paper_short_title, ...) don't collide with the mapping's columns on merge.
    needed = ["study_accession", "ena_taxon_samples", *(["n_held"] if "n_held" in stage1.columns else [])]
    merged = stage1[needed].merge(mapping, on="study_accession", how="left")

    agg = {
        "paper_short_title": ("paper_short_title", "first"),
        "isolates_in_study": ("isolates_in_study", "first"),
        "kleb_assemblies_in_paper": ("kleb_assemblies_in_paper", "first"),
        "n_accessions": ("study_accession", "nunique"),
        "ena_taxon_samples_sum": ("ena_taxon_samples", lambda s: pd.to_numeric(s, errors="coerce").sum()),
    }
    if "n_held" in merged.columns:
        agg["n_held_sum"] = ("n_held", lambda s: pd.to_numeric(s, errors="coerce").sum())
    per_row = merged.groupby("row_id").agg(**agg).reset_index()
    # ena_taxon_samples = the project's taxon-of-interest size (denominator); isolates_in_study =
    # what the curation/paper covered. Their ratio is coverage, not an error. A holding that
    # exceeds the project taxon count is a genuine anomaly worth eyeballing (e.g. RefSeq genomes
    # under other accessions, or samples whose scientific_name is unset in ENA).
    per_row["coverage"] = per_row["isolates_in_study"] / per_row["ena_taxon_samples_sum"]
    per_row["holding_exceeds_project"] = per_row["isolates_in_study"] > per_row["ena_taxon_samples_sum"]
    return per_row


def _find_parsed_per_project() -> pd.DataFrame | None:
    """Read the live ``parsed_per_project`` tab, or return None if credentials are unavailable."""
    try:
        from bac_metadata.bac_agentic_metadata.engine.gsheet import read_tab

        return read_tab(SHEET_ID, "parsed_per_project")
    except Exception as exc:  # noqa: BLE001 - any auth/IO failure should degrade gracefully
        print(f"[completeness] skipping parsed_per_project reconcile: {exc}", file=sys.stderr)
        return None


def _completeness_reconcile(stage1: pd.DataFrame, ppp: pd.DataFrame) -> pd.DataFrame:
    """Best-effort overlap of engine completeness with parsed_per_project per-field columns."""
    key = next((c for c in ppp.columns if "accession" in c.lower() or c.lower() in {"project", "study"}), None)
    if key is None:
        print("[completeness] no project key column found in parsed_per_project", file=sys.stderr)
        return pd.DataFrame()
    ppp = ppp.rename(columns={key: "study_accession"})

    field_cols: dict[str, str] = {}
    for field in CLINICAL:
        match = next((c for c in ppp.columns if field.split("_")[0] in c.lower()), None)
        if match:
            field_cols[field] = match

    keep = ["study_accession", *field_cols.values()]
    merged = stage1.merge(ppp[keep], on="study_accession", how="left", suffixes=("", "_ppp"))
    for field, col in field_cols.items():
        merged[f"ppp_{field}"] = pd.to_numeric(merged[col], errors="coerce")
        eng = pd.to_numeric(merged.get(f"completeness_norm_{field}"), errors="coerce")
        merged[f"completeness_diff_{field}"] = eng - merged[f"ppp_{field}"]
    return merged


def _umbrella_section(stage1: pd.DataFrame) -> list[str]:
    """Markdown lines listing umbrella-suspected accessions (one accession, many substudies)."""
    if "umbrella_suspected" not in stage1.columns:
        return []
    flag = stage1["umbrella_suspected"].astype(str).str.lower().isin({"true", "1"})
    umb = stage1[flag]
    if umb.empty:
        return ["## Umbrella accessions", "_none flagged._", ""]
    cols = [c for c in ["study_accession", "paper_short_title", "n_child_studies", "ena_taxon_samples"] if c in umb.columns]
    return [
        "## Umbrella accessions (one accession aggregating many substudies)",
        "Flagged via distinct child studies; one 'best paper' cannot describe these. "
        "`PRJEB74192` (One Health Norway) is the canonical training case.",
        "```",
        umb[cols].to_string(index=False),
        "```",
        "",
    ]


def _write_markdown(out_md: Path, per_row: pd.DataFrame, comp: pd.DataFrame, stage1: pd.DataFrame) -> None:
    """Write a short human-readable agreement summary."""
    lines = ["# Stage 1 validation summary", "", *_umbrella_section(stage1)]
    cov = per_row["coverage"].dropna()
    if len(cov):
        anomalies = per_row[per_row["holding_exceeds_project"].fillna(False)]
        lines += [
            "## Sizing (curation holding vs ENA project taxon count, per curation row)",
            "`ena_taxon_samples` is the project's Klebsiella size (paper-coverage denominator); "
            "`isolates_in_study` is what the curation covered. `coverage = isolates / ena_taxon`.",
            f"- rows compared: {len(cov)}",
            f"- median coverage: {cov.median():.2f}",
            f"- whole-project (coverage >= 0.9): {(cov >= 0.9).mean():.0%}; "
            f"subsample (< 0.5): {(cov < 0.5).mean():.0%}",
            f"- anomalies (holding > project taxon count): {len(anomalies)}",
            "",
            "### Lowest coverage (most subsampled)",
            "```",
            per_row.reindex(cov.sort_values().index)
            .head(10)[["paper_short_title", "isolates_in_study", "ena_taxon_samples_sum", "coverage"]]
            .to_string(index=False),
            "```",
            "",
        ]
        if len(anomalies):
            lines += [
                "### Anomalies — holding exceeds ENA project taxon count",
                "```",
                anomalies[["paper_short_title", "isolates_in_study", "ena_taxon_samples_sum"]].to_string(index=False),
                "```",
                "",
            ]
    if not comp.empty:
        lines += ["## Completeness (engine norm vs parsed_per_project)", ""]
        for field in CLINICAL:
            diff = comp.get(f"completeness_diff_{field}")
            if diff is not None and diff.notna().any():
                d = diff.dropna()
                lines.append(f"- {field}: n={len(d)}, median diff={d.median():+.3f}, mean |diff|={d.abs().mean():.3f}")
    else:
        lines += ["## Completeness", "_parsed_per_project not read (no credentials) — sizing only._"]
    out_md.write_text("\n".join(lines) + "\n")


def main() -> None:
    """Parse arguments, run both reconciliations, and write the report."""
    parser = argparse.ArgumentParser(description="Validate Stage 1 output vs the curation sheet.")
    parser.add_argument("--ingest", type=Path, default=DATA_DIR / "stage1_ingest.tsv")
    parser.add_argument("--out-tsv", type=Path, default=DATA_DIR / "stage1_validation_report.tsv")
    parser.add_argument("--out-md", type=Path, default=DATA_DIR / "stage1_validation_report.md")
    parser.add_argument(
        "--no-completeness", action="store_true", help="Skip the parsed_per_project completeness reconcile."
    )
    args = parser.parse_args()

    stage1 = pd.read_csv(args.ingest, sep="\t")
    study_level = pd.read_csv(FROZEN_STUDY_LEVEL)

    per_row = _sizing_reconcile(stage1, study_level)
    comp = pd.DataFrame()
    if not args.no_completeness:
        ppp = _find_parsed_per_project()
        if ppp is not None:
            comp = _completeness_reconcile(stage1, ppp)

    per_row.to_csv(args.out_tsv, sep="\t", index=False)
    _write_markdown(args.out_md, per_row, comp, stage1)
    print(f"Wrote {args.out_tsv} and {args.out_md}", file=sys.stderr)


if __name__ == "__main__":
    main()
