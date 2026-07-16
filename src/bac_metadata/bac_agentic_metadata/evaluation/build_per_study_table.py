r"""Publication-facing per-study-accession table — one consolidated row per study of what the engine achieved.

Read-only, deterministic. For every curated study: the describing paper link, the number of curated *Klebsiella*
samples, the study-wide grades (``amr_study`` / ``study_setting`` / ``study_type`` + the exclusion flag), and the
**pre- and post-fill completeness of each per-sample field** (base ENA vs the accumulated master, placeholder-
stripped to match the summaries). Joins the same artifacts the wrap-up report reads. Writes
``data/curated/per_study_accession_table.{tsv,md}`` (PROGRESS_REPORT §5 item 3).

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.build_per_study_table
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

FIELDS = ("country", "collection_date", "isolation_source", "host")


def _paper_links(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Union each tranche's found_papers → study_accession, paper (best available id), paper_title."""
    rows = []
    for tag in tags:
        fp = RunPaths(data_dir, tag).found_papers_tsv
        if not fp.exists():
            continue
        f = pd.read_csv(fp, sep="\t", dtype=str).fillna("")
        for _, r in f.iterrows():
            link = (f"https://pmc.ncbi.nlm.nih.gov/articles/{r['chosen_pmcid']}/" if r.get("chosen_pmcid")
                    else f"https://pubmed.ncbi.nlm.nih.gov/{r['chosen_pmid']}/" if r.get("chosen_pmid")
                    else f"https://doi.org/{r['chosen_doi']}" if r.get("chosen_doi") else "")
            rows.append({"study_accession": r["study_accession"], "tag": tag, "paper": link,
                         "paper_title": r.get("chosen_title", "")})
    return pd.DataFrame(rows).drop_duplicates("study_accession") if rows else pd.DataFrame(
        columns=["study_accession", "tag", "paper", "paper_title"])


def _per_study_completeness(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-study fraction non-blank (placeholder-stripped) for each field, over the study's samples."""
    out = pd.DataFrame({"study_accession": sorted(frame["study_accession"].unique())}).set_index("study_accession")
    for f in FIELDS:
        if f in frame.columns:
            present = backfill.strip_placeholders(frame[f]).notna()
            out[f] = present.groupby(frame["study_accession"]).mean()
    return out.reset_index()


def build_table(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Join paper links + grades + n_samples + base→filled per-study completeness into one table."""
    curated = data_dir / "curated"
    keep = ["study_accession", "sample_accession", *FIELDS]
    base = pd.read_csv(data_dir / "inputs" / "base_table.csv", dtype=str, low_memory=False,
                       keep_default_na=False, usecols=lambda c: c in keep).fillna("")
    master = pd.read_csv(curated / "metadata_curated_master.tsv", sep="\t", dtype=str, low_memory=False,
                         usecols=lambda c: c in keep).fillna("")
    n = master.groupby("study_accession").size().rename("n_samples").reset_index()
    base_c = _per_study_completeness(base).rename(columns={f: f"{f}_base" for f in FIELDS})
    fill_c = _per_study_completeness(master).rename(columns={f: f"{f}_filled" for f in FIELDS})
    grades = pd.read_csv(curated / "curated_grades.tsv", sep="\t", dtype=str).fillna("")
    gcols = {"study_accession": "study_accession", "study_type": "study_type",
             "study_type_excluded": "study_type_excluded", "study_setting__value": "study_setting",
             "amr_study__value": "amr_study"}
    g = grades[[c for c in gcols if c in grades.columns]].rename(columns=gcols)

    n = n[n["study_accession"].str.strip() != ""]  # drop blank / collection pseudo-studies handled below
    t = (n.merge(_paper_links(data_dir, tags), on="study_accession", how="left")
         .merge(g, on="study_accession", how="left")
         .merge(base_c, on="study_accession", how="left")
         .merge(fill_c, on="study_accession", how="left")).fillna("")
    # order columns: identity → paper → grades → per-field base/filled pairs
    lead = ["study_accession", "tag", "n_samples", "paper", "paper_title",
            "study_type", "study_type_excluded", "study_setting", "amr_study"]
    pairs = [c for f in FIELDS for c in (f"{f}_base", f"{f}_filled")]
    return t[[c for c in lead if c in t.columns] + [c for c in pairs if c in t.columns]]


def main() -> None:
    """Build the publishable per-study-accession table."""
    p = argparse.ArgumentParser(description="Publishable per-study-accession summary table.")
    p.add_argument("--app", default="klebsiella")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--tags", default="train,test,tail100,tail50_99,tail25_49,tail10_24,sub10")
    args = p.parse_args()
    here = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else here / "applications" / args.app / "data"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    t = build_table(data_dir, tags)
    out = data_dir / "per_study_accession_table.tsv"  # data root (curated/ is gitignored)
    t.to_csv(out, sep="\t", index=False)
    # a small human-readable head for the .md (manual table — no tabulate dependency)
    show = ["study_accession", "tag", "n_samples", "study_type_excluded", "amr_study",
            "country_base", "country_filled", "host_base", "host_filled"]
    show = [c for c in show if c in t.columns]
    md = ["# Per-study-accession table (head)", "",
          f"{len(t)} studies. Full table: `per_study_accession_table.tsv`.", "",
          "| " + " | ".join(show) + " |", "|" + "---|" * len(show)]
    for _, r in t.head(15).iterrows():
        md.append("| " + " | ".join(str(r[c])[:40] for c in show) + " |")
    out.with_suffix(".md").write_text("\n".join(md) + "\n")
    print(f"[per-study] wrote {out} ({len(t)} studies)", file=sys.stderr)


if __name__ == "__main__":
    main()
