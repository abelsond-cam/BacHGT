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


def _classify(row: pd.Series) -> tuple[str, str]:
    """Classify one curation row against ENA, using both the taxon (lower) and total (upper) bound.

    ``ena_klebsiella_samples`` (scientific_name match) under-counts Klebsiella for broad projects,
    so it is a lower bound; ``ena_total_samples`` is the upper bound. Returns (class, note).
    """
    prior = row["prior_isolates_in_study"]
    taxon = row["ena_klebsiella_samples"]
    total = row["ena_total_samples"]
    cov = row["coverage"]  # prior / taxon
    n_papers = row.get("n_papers_on_this_accession")
    children = row.get("n_child_studies")

    if str(row.get("umbrella_suspected")).lower() in {"true", "1"}:
        return "umbrella", (
            f"umbrella accession ({int(children) if pd.notna(children) else '?'} child studies) — "
            "one paper cannot cover it; split into substudies"
        )
    if pd.isna(prior):
        return "no_curated_count", "sheet has no isolates_in_study for this row — nothing to compare"
    if pd.isna(total) or total == 0:
        return "review_no_ena_records", (
            f"prior curated {int(prior)} but ENA has no records under this accession "
            "(assembly-only / wrong accession) — manual check"
        )
    if prior > total * 1.02:
        return "review_prior_exceeds_ena", (
            f"prior curated {int(prior)} > ENA total {int(total)} under this accession — isolates likely "
            "under other accessions / RefSeq-only / a multi-accession paper; manual check"
        )
    if prior > taxon:  # taxon < prior <= total: ENA holds the records but under-labels Klebsiella
        return "ena_underlabels_klebsiella", (
            f"ENA holds {int(total)} records but labels only {int(taxon)} as Klebsiella by scientific_name; "
            f"the curation's {int(prior)} are present but under-labelled — taxon sizing is a lower bound here"
        )
    if pd.notna(n_papers) and n_papers > 1:
        return "shared_accession", (
            f"accession shared by {int(n_papers)} curated papers; this paper is one slice "
            f"(curated {int(prior)} of {int(taxon)} ENA Klebsiella, coverage {cov:.2f})"
        )
    if pd.notna(cov) and cov >= 0.9:
        return "whole_project", f"engine confirms paper ≈ whole project (curated {int(prior)} ≈ ENA Klebsiella {int(taxon)})"
    return "subsample", (
        f"paper is a subsample of a larger project (curated {int(prior)} of {int(taxon)} "
        f"ENA Klebsiella, coverage {cov:.2f}) — e.g. rolling-surveillance deposit"
    )


def _sizing_reconcile(stage1: pd.DataFrame, study_level: pd.DataFrame) -> pd.DataFrame:
    """Reconcile prior curation (sheet) against what the engine found in ENA, per curation row.

    Emits, per row: the prior finding (``prior_*`` from the sheet), the engine finding (``ena_*``
    from the live ENA interrogation), coverage, ``n_papers_on_this_accession``, and an explicit
    ``classification`` + ``note`` contrasting the two. This is the validation record.
    """
    mapping = _explode_accessions(study_level)
    # How many distinct curation rows cite each accession (an accession shared by >1 paper
    # explains low per-paper coverage).
    papers_per_acc = mapping.groupby("study_accession")["row_id"].nunique().rename("n_papers_on_this_accession")
    mapping = mapping.merge(papers_per_acc, on="study_accession")

    # Keep only the engine columns the reconcile needs, so split-carried columns don't collide.
    eng_cols = ["ena_taxon_samples", "ena_total_runs", "ena_total_samples", "n_child_studies", "umbrella_suspected"]
    needed = ["study_accession", *[c for c in eng_cols if c in stage1.columns]]
    merged = stage1[needed].merge(mapping, on="study_accession", how="left")

    def _sum(col: str):
        return (col, lambda s: pd.to_numeric(s, errors="coerce").sum())

    agg = {
        "paper_short_title": ("paper_short_title", "first"),
        "prior_isolates_in_study": ("isolates_in_study", "first"),
        "prior_kleb_assemblies_in_paper": ("kleb_assemblies_in_paper", "first"),
        "n_accessions": ("study_accession", "nunique"),
        "n_papers_on_this_accession": ("n_papers_on_this_accession", "max"),
        "ena_klebsiella_samples": _sum("ena_taxon_samples"),
        "ena_total_samples": _sum("ena_total_samples"),
        "ena_total_runs": _sum("ena_total_runs"),
        "n_child_studies": ("n_child_studies", lambda s: pd.to_numeric(s, errors="coerce").max()),
        "umbrella_suspected": ("umbrella_suspected", lambda s: s.astype(str).str.lower().isin({"true", "1"}).any()),
    }
    per_row = merged.groupby("row_id").agg(**agg).reset_index()

    per_row["coverage"] = per_row["prior_isolates_in_study"] / per_row["ena_klebsiella_samples"]
    classified = per_row.apply(_classify, axis=1, result_type="expand")
    per_row["classification"] = classified[0]
    per_row["note"] = classified[1]
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


_CLASS_BLURB = {
    "whole_project": "engine confirms the prior paper ≈ the whole ENA project",
    "subsample": "prior paper covers a subsample of a larger ENA project",
    "shared_accession": "one ENA accession is split across several prior papers",
    "umbrella": "one ENA accession is many substudies (needs splitting)",
    "ena_underlabels_klebsiella": "ENA has the records but labels fewer as Klebsiella by scientific_name; "
    "curation more complete (taxon sizing is a lower bound) — not a curation error",
    "review_prior_exceeds_ena": "prior curated MORE than ENA holds under this accession — review",
    "review_no_ena_records": "ENA has no records under the accession — review",
    "no_curated_count": "sheet has no isolates_in_study — nothing to compare",
}


def _write_markdown(out_md: Path, per_row: pd.DataFrame, comp: pd.DataFrame, stage1: pd.DataFrame) -> None:
    """Write the prior-vs-found validation summary."""
    n = len(per_row)
    lines = [
        "# Stage 1 validation summary",
        "",
        "## What this validates",
        f"For each of the **{n} curated rows** we compare the **prior finding** (your Google Sheet "
        "curation: `prior_isolates_in_study`) against **what the engine independently found in ENA** "
        "(`ena_klebsiella_samples`, `ena_total_runs`, `n_child_studies` — all from the live ENA "
        "`read_run` interrogation, not the sheet). `coverage = prior_isolates / ena_klebsiella`. The "
        "`classification` + `note` columns in the TSV say, per row, how the two relate. This is the "
        "check that the engine reproduces the manual EBI-sizing step correctly.",
        "",
        "## Verdict — classification breakdown",
        "```",
        per_row["classification"].value_counts().to_string(),
        "```",
    ]
    for cls, blurb in _CLASS_BLURB.items():
        cnt = int((per_row["classification"] == cls).sum())
        if cnt:
            lines.append(f"- **{cls}** ({cnt}): {blurb}")
    lines.append("")
    lines += _umbrella_section(stage1)

    cov = per_row["coverage"].dropna()
    if len(cov):
        show = ["paper_short_title", "prior_isolates_in_study", "ena_klebsiella_samples", "ena_total_samples", "coverage", "note"]
        lines += [
            "## Lowest coverage (prior paper vs what ENA holds)",
            "```",
            per_row.reindex(cov.sort_values().index).head(10)[show].to_string(index=False),
            "```",
            "",
        ]
        anomalies = per_row[per_row["classification"].isin(["review_prior_exceeds_ena", "review_no_ena_records"])]
        if len(anomalies):
            lines += [
                "## Review queue — prior curated count exceeds / disagrees with ENA",
                "```",
                anomalies[["paper_short_title", "prior_isolates_in_study", "ena_klebsiella_samples", "ena_total_samples", "note"]]
                .to_string(index=False),
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
