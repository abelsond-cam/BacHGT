r"""AST-availability **scoping** report — which studies report AST, and for which backbone drugs.

A go/no-go input for a later per-drug extraction round.
Read-only, deterministic, offline, **no LLM**, and **app-agnostic** (spec-driven). It combines two signals
already on disk:

* the **detection grades** ``reports_AST`` / ``per_sample_AST`` (study-level judgements the grader already
  made — does the paper report phenotypic AST, and is a per-isolate AST table retrievable); and
* a **keyword scan of the read paper** for the spec's AST backbone drugs
  (``attributes.per_sample_completeness.ast_panel.ast_backbone_drugs``) — over the SAME cached full text the
  grader saw (``cache/fulltext/<PMCID>.xml`` via :func:`engine.fulltext._xml_to_text`), plus the grades'
  ``evidence_quote`` snippets as a fallback when no full text was resolved.

**Scoping only — it never parses or integrates a per-drug MIC / S-I-R value.** It answers "which papers
report AST for the backbone drugs, and how many", so a per-drug PAPER-extraction round can be decided (or
declined) on evidence. The in-hand collaborator-table AST is a separate, already-decided integration.

The report gates on the spec declaring an ``ast_panel`` with ``ast_backbone_drugs``; an application without one
(e.g. Klebsiella) is a clean no-op. Writes ``<data-dir>/ast_availability_report.{md,tsv}`` (override ``--out``).

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.ast_availability_report \
        --app m_abs --tags mabs_top20,mabs_21_40,mabs_all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.fulltext import _xml_to_text
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec
from bac_metadata.bac_agentic_metadata.evaluation import report_config as rc

#: The spec's AST *detection* study-level grades (present whenever an ``ast_panel`` is declared). Named here
#: rather than hardcoded across the body; an application that grades AST detection under other names adjusts
#: these two constants.
REPORTS_ATTR = "reports_AST"
PER_SAMPLE_ATTR = "per_sample_AST"
#: per_sample_AST values that mark a study worth manual AST follow-up (vs "none"/ungraded).
FOLLOWUP_VALUES = ("retrievable", "possible")


def backbone_drugs(spec: AttributeSpec) -> list[str]:
    """Return the spec's AST backbone drug list (empty if the spec declares no ``ast_panel``)."""
    ap = spec.raw.get("attributes", {}).get("per_sample_completeness", {}).get("ast_panel") or {}
    return [str(d).strip() for d in ap.get("ast_backbone_drugs", []) if str(d).strip()]


def _load_grades(data_dir: Path, tags: list[str]) -> list[dict]:
    """Union each tranche's ``study_grades.jsonl`` into one list of grade records (tag stamped as ``_tag``)."""
    rows: list[dict] = []
    for tag in tags:
        p = RunPaths(data_dir, tag).study_grades_jsonl
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a partially-written trailing line if grading is still in flight
            r["_tag"] = tag
            rows.append(r)
    return rows


def _paper_index(data_dir: Path, tags: list[str]) -> dict[str, dict]:
    """Map ``study_accession`` → {pmcid, link, title} from each tranche's ``found_papers.tsv`` (first wins)."""
    idx: dict[str, dict] = {}
    for tag in tags:
        fp = RunPaths(data_dir, tag).found_papers_tsv
        if not fp.exists():
            continue
        f = pd.read_csv(fp, sep="\t", dtype=str).fillna("")
        for _, r in f.iterrows():
            acc = r["study_accession"]
            if acc in idx:
                continue
            pmcid = r.get("chosen_pmcid", "")
            link = (f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid
                    else f"https://pubmed.ncbi.nlm.nih.gov/{r['chosen_pmid']}/" if r.get("chosen_pmid")
                    else f"https://doi.org/{r['chosen_doi']}" if r.get("chosen_doi") else "")
            idx[acc] = {"pmcid": pmcid, "link": link, "title": r.get("chosen_title", "")}
    return idx


def _study_level(row: dict, attr: str) -> tuple[str, str, str]:
    """Return (value, grade, evidence_quote) for a study-level attribute, blanks if absent/null.

    The value is lowercased for stable comparison/display: the AST detection grades are a JSON boolean
    (``reports_AST`` → ``true``/``false``) or a lowercase enum (``per_sample_AST`` → retrievable/possible/none),
    so ``str(True)`` ("True") must not diverge from the lowercase constants this module compares against.
    """
    d = (row.get("study_level") or {}).get(attr) or {}
    v = d.get("value")
    return ("" if v is None else str(v).lower()), (d.get("grade") or ""), (d.get("evidence_quote") or "")


def _drug_patterns(drugs: list[str]) -> dict[str, re.Pattern]:
    """Whole-word, case-insensitive matcher per drug (full drug name only — abbreviations are not matched)."""
    return {d: re.compile(rf"\b{re.escape(d)}\b", re.IGNORECASE) for d in drugs}


def _scan(text: str, patterns: dict[str, re.Pattern]) -> list[str]:
    """Return the drugs (in panel order) whose name appears in ``text``."""
    return [d for d, pat in patterns.items() if text and pat.search(text)]


def build_records(data_dir: Path, tags: list[str], drugs: list[str]) -> pd.DataFrame:
    """One row per graded study: detection grades + backbone drugs found in full text / evidence quote.

    The full-text scan reads the cached Europe-PMC XML the grader used (``cache/fulltext/<PMCID>.xml``); when
    no PMCID full text was resolved the study is scanned only through its grade ``evidence_quote`` snippets and
    flagged ``text_source == "quote_only"`` (or ``"none"``) so the scan's coverage is explicit, never implied.
    """
    grades = _load_grades(data_dir, tags)
    papers = _paper_index(data_dir, tags)
    ft_cache = data_dir / "cache" / "fulltext"
    patterns = _drug_patterns(drugs)
    seen: set[str] = set()
    records: list[dict] = []
    for row in grades:
        acc = row.get("study_accession", "")
        if not acc or acc in seen:
            continue
        seen.add(acc)
        ra_v, ra_g, ra_q = _study_level(row, REPORTS_ATTR)
        ps_v, ps_g, ps_q = _study_level(row, PER_SAMPLE_ATTR)
        paper = papers.get(acc, {})
        pmcid = paper.get("pmcid", "")
        xmlp = ft_cache / f"{pmcid}.xml" if pmcid else None
        if xmlp is not None and xmlp.exists():
            text, text_source = _xml_to_text(xmlp.read_text()), f"fulltext:{pmcid}"
        else:
            text, text_source = "", ("quote_only" if (ra_q or ps_q) else "none")
        in_ft = _scan(text, patterns)
        in_ev = _scan(" ".join([ra_q, ps_q]), patterns)
        records.append({
            "study_accession": acc, "tag": row.get("_tag", ""),
            "reports_AST": ra_v, "reports_AST_grade": ra_g,
            "per_sample_AST": ps_v, "per_sample_AST_grade": ps_g,
            "n_backbone_fulltext": len(in_ft), "backbone_fulltext": "; ".join(in_ft),
            "backbone_evidence_quote": "; ".join(in_ev), "text_source": text_source,
            "paper": paper.get("link", ""), "paper_title": paper.get("title", ""),
        })
    cols = ["study_accession", "tag", "reports_AST", "reports_AST_grade", "per_sample_AST",
            "per_sample_AST_grade", "n_backbone_fulltext", "backbone_fulltext", "backbone_evidence_quote",
            "text_source", "paper", "paper_title"]
    return pd.DataFrame(records, columns=cols)


def _dist(series: pd.Series) -> str:
    """A compact ``value N, value N`` distribution string (blanks bucketed as ``—``)."""
    vc = series.replace("", "—").value_counts()
    return ", ".join(f"{k} {v}" for k, v in vc.items())


def _render_md(df: pd.DataFrame, drugs: list[str], species: str, tags: list[str]) -> str:
    """Render the scoping report markdown from the per-study records."""
    n = len(df)
    reports_yes = df[df["reports_AST"] == "true"]
    scanned_ft = df[df["text_source"].str.startswith("fulltext:")]
    out: list[str] = []
    out.append(f"# {species} — AST availability (scoping only)")
    out.append("")
    out.append(f"**{n} graded studies** across tags `{', '.join(tags)}`. Detection grades + a keyword scan "
               "of the read paper for the backbone panel. **No per-drug MIC / S-I-R value is parsed or "
               "integrated** — this decides whether a per-drug *paper*-extraction round is worth running.")
    out.append("")
    out.append(f"Backbone panel ({len(drugs)}): {', '.join(drugs)}.")
    out.append("")
    # §1 detection
    out.append("## 1. Detection grades")
    out.append("")
    out.append(f"- **reports_AST** (paper reports phenotypic AST for ≥1 isolate): {_dist(df['reports_AST'])}")
    out.append(f"- **per_sample_AST** (per-isolate AST table obtainable): {_dist(df['per_sample_AST'])}")
    out.append(f"- studies with reports_AST = true: **{len(reports_yes)}**; of those, per_sample_AST "
               f"retrievable/possible: **{len(reports_yes[reports_yes['per_sample_AST'].isin(FOLLOWUP_VALUES)])}**")
    out.append("")
    # §2 backbone drug hits
    out.append("## 2. Backbone-drug mentions in the read papers")
    out.append("")
    out.append("Whole-word, case-insensitive match of the full drug name in the cached full text "
               "(abbreviations are **not** matched — a floor, not a ceiling).")
    out.append("")
    out.append("| drug | studies mentioning | among reports_AST=true | among per_sample follow-up |")
    out.append("|---|---|---|---|")
    for d in drugs:
        hit = df["backbone_fulltext"].str.split("; ").apply(lambda xs, d=d: d in xs)
        n_all = int(hit.sum())
        n_yes = int((hit & (df["reports_AST"] == "true")).sum())
        n_ps = int((hit & df["per_sample_AST"].isin(FOLLOWUP_VALUES)).sum())
        out.append(f"| {d} | {n_all} | {n_yes} | {n_ps} |")
    out.append("")
    # §3 priority worklist
    out.append("## 3. Priority studies for a possible per-drug round")
    out.append("")
    prio = df[(df["reports_AST"] == "true") | df["per_sample_AST"].isin(FOLLOWUP_VALUES)].copy()
    rank = {"retrievable": 0, "possible": 1}
    prio["_r"] = prio["per_sample_AST"].map(rank).fillna(2)
    prio = prio.sort_values(["_r", "n_backbone_fulltext"], ascending=[True, False])
    if prio.empty:
        out.append("_None — no study both reports AST and offers a retrievable/possible per-isolate table._")
    else:
        out.append("| study | reports_AST | per_sample_AST | backbone drugs found | paper |")
        out.append("|---|---|---|---|---|")
        for _, r in prio.iterrows():
            link = f"[link]({r['paper']})" if r["paper"] else "—"
            out.append(f"| {r['study_accession']} | {r['reports_AST'] or '—'} | {r['per_sample_AST'] or '—'} "
                       f"| {r['backbone_fulltext'] or (r['backbone_evidence_quote'] and r['backbone_evidence_quote'] + ' *(quote)*') or '—'} | {link} |")
    out.append("")
    # §4 scan coverage / limitations
    out.append("## 4. Scan coverage & limitations")
    out.append("")
    out.append(f"- full text scanned: **{len(scanned_ft)}/{n}** studies "
               f"(quote-only: {int((df['text_source'] == 'quote_only').sum())}; "
               f"no text: {int((df['text_source'] == 'none').sum())}).")
    out.append("- Full drug-name match only; abbreviations (AMK, CLR, FOX…) and class terms are not counted.")
    out.append("- A mention is not a result: presence of a drug name ≠ a reported MIC/S-I-R for it. This "
               "report scopes availability; it does not extract values.")
    out.append("")
    return "\n".join(out) + "\n"


def build_report(data_dir: Path, tags: list[str], spec: AttributeSpec, out: Path) -> pd.DataFrame:
    """Build the per-study records and write the ``.tsv`` + ``.md`` scoping report; return the records."""
    drugs = backbone_drugs(spec)
    df = build_records(data_dir, tags, drugs)
    out.with_suffix(".tsv").write_text(df.to_csv(sep="\t", index=False))
    out.with_suffix(".md").write_text(_render_md(df, drugs, rc.species_label(spec), tags))
    return df


def main() -> None:
    """CLI: build the AST-availability scoping report for an application's tranches."""
    p = argparse.ArgumentParser(description="AST-availability scoping report (app-agnostic; read-only).")
    p.add_argument("--app", default="klebsiella")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--spec", default=None, help="attributes.yaml (default: applications/<app>/attributes.yaml).")
    p.add_argument("--tags", default="mabs_all", help="Comma-separated run tags to union.")
    p.add_argument("--out", default=None, help="Output path (.md; .tsv sibling). Default <data-dir>/ast_availability_report.md")
    args = p.parse_args()
    here = Path(__file__).resolve().parent.parent
    app_dir = here / "applications" / args.app
    data_dir = Path(args.data_dir) if args.data_dir else app_dir / "data"
    spec = AttributeSpec.from_yaml(args.spec if args.spec else app_dir / "attributes.yaml")
    if not backbone_drugs(spec):
        print(f"[ast-report] {args.app}: spec declares no ast_panel.ast_backbone_drugs — nothing to report.",
              file=sys.stderr)
        return
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    out = Path(args.out) if args.out else data_dir / "ast_availability_report.md"
    df = build_report(data_dir, tags, spec, out)
    print(f"[ast-report] wrote {out.with_suffix('.md')} + .tsv ({len(df)} studies, tags={','.join(tags)})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
