r"""Reviewable artefact of the per-sample OVERWRITES that a v2 combine would apply (two-step combine, step ii).

Read-only, deterministic, no LLM. Blank-fills are safe (they only populate empty cells); the per-sample stage
is the **only** one that can replace a *non-blank* ENA value, and only through the fidelity gate
(date-granularity / vague→specific). This tool surfaces every one of those overwrites for David to review
**before** any are applied over a curated v2 value (step iii, ``combine.apply_gated_overwrites``).

It reads each tranche's ``per_sample/per_sample_applied.tsv`` (the only place the ``evidence`` string survives —
it is dropped from ``curated/curated_fills.tsv``), keeps the rows whose ENA value was non-blank (the same
definition as the wrap-up §5c), classifies each, enriches with the study's paper link, and writes
``data/v2_overwrite_candidates.{tsv,md}`` split into:

* **(b) collection_date** — same-year refinements (the sanctioned low-risk exception) vs the rare
  year-changing / unparseable ones (flagged);
* **(a) categorical** — country / host / isolation_source vague→specific, with the concrete→concrete
  replacements flagged.

The candidate counts reconcile to the wrap-up §5c figures (a self-check line in the report). Run locally — no
CSD3 / v2 access needed; the artefact is built entirely from committed repo data.

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.report_v2_overwrites \
        --tags train,test,tail100,tail50_99,tail25_49,tail10_24,sub10
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

#: The four per-sample completeness fields; isolation_source/host/country are the "categorical" group.
FIELDS = ("country", "collection_date", "isolation_source", "host")
CATEGORICAL = ("country", "host", "isolation_source")
#: §5c figures of record (Kp_AGENTIC_METADATA_WRAPUP_REPORT.md / MERGE_TO_V2_RUNBOOK.md) — the reconciliation target.
EXPECTED_5C = {"isolation_source": 2037, "collection_date": 1014, "host": 38, "country": 16}

_YEAR = re.compile(r"(19|20)\d\d")


def _year(text: str) -> str | None:
    """First 4-digit year (19xx/20xx) in ``text``, or None."""
    m = _YEAR.search(str(text))
    return m.group(0) if m else None


def _norm(text: str) -> str:
    """Whitespace-collapsed, case-folded key for equality tests (mirrors the completeness comparison)."""
    return re.sub(r"\s+", " ", str(text).strip()).casefold()


def classify(field: str, ena_value: str, applied_value: str) -> tuple[str, str]:
    """Classify one overwrite → ``(class, review_flag)``.

    ``class`` is the routing bucket used to split the report; ``review_flag`` (``""`` = routine) marks the rows
    that warrant David's eye. The fidelity gate already vetted these at fill time — this only *surfaces* them,
    it does not re-adjudicate.

    Parameters
    ----------
    field
        One of :data:`FIELDS`.
    ena_value
        The pre-existing (non-blank) ENA value the fill replaces.
    applied_value
        The value the agent applied.

    Returns
    -------
    tuple of str
        ``(class, review_flag)``.
    """
    o, n = _norm(ena_value), _norm(applied_value)
    if o == n:
        return "no_change", "no_change"  # ENA text differs only in case/space — nothing really overwritten
    if field == "collection_date":
        oy, ny = _year(ena_value), _year(applied_value)
        if oy and ny and oy == ny:
            return "date_same_year_refinement", ""  # 2019 → 2019-11-28: the sanctioned exception
        if oy and ny and oy != ny:
            return "date_year_changed", "year_changed"  # violates the same-year rule → review
        return "date_unparsed", "date_unparsed"  # a year could not be read on one side → review
    # categorical (country / host / isolation_source)
    if backfill.strip_placeholders(pd.Series([applied_value])).isna().iloc[0]:
        return "categorical_change", "new_is_null"  # replaced a real value with a placeholder → review
    if len(n) < len(o) and n in o:
        return "categorical_change", "shortened"  # new is a shorter substring of old (de-dup / extract-from-token)
    return "categorical_change", ""


def _paper_links(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Union each tranche's ``found_papers`` → ``study_accession`` + best paper link (PMC > PubMed > DOI)."""
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
            rows.append({"study_accession": r["study_accession"], "paper": link})
    return (pd.DataFrame(rows).drop_duplicates("study_accession") if rows
            else pd.DataFrame(columns=["study_accession", "paper"]))


def collect_overwrites(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Read every tranche's per_sample_applied, keep ENA-non-blank rows, classify + enrich → one long table.

    Columns: ``tag, study_accession, sample_accession, field, ena_value, applied_value, changed, class,
    review_flag, evidence, paper``. The row set is the wrap-up §5c overwrite set (ENA value non-blank).
    """
    frames = []
    for t in tags:
        fp = RunPaths(data_dir, t).per_sample_applied
        if not fp.exists():
            continue
        df = pd.read_csv(fp, sep="\t", dtype=str).fillna("")
        if not len(df) or "ena_value" not in df.columns:
            continue
        df = df[backfill.strip_placeholders(df["ena_value"]).notna()].copy()  # §5c definition of an overwrite
        df.insert(0, "tag", t)
        frames.append(df)
    over = (pd.concat(frames, ignore_index=True) if frames
            else pd.DataFrame(columns=["tag", "study_accession", "sample_accession", "field",
                                       "ena_value", "applied_value", "method", "evidence"]))
    cls = over.apply(lambda r: classify(r["field"], r["ena_value"], r["applied_value"]), axis=1)
    over["class"] = [c for c, _ in cls]
    over["review_flag"] = [f for _, f in cls]
    over["changed"] = over["class"] != "no_change"
    over = over.merge(_paper_links(data_dir, tags), on="study_accession", how="left").fillna({"paper": ""})
    cols = ["tag", "study_accession", "sample_accession", "field", "ena_value", "applied_value",
            "changed", "class", "review_flag", "evidence", "paper"]
    return over[[c for c in cols if c in over.columns]]


def _md_table(rows: pd.DataFrame, cols: list[str], cap: int = 0) -> list[str]:
    """Render a DataFrame slice as a GitHub markdown table (values truncated to 60 chars; ``cap`` limits rows)."""
    body = rows.head(cap) if cap else rows
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in body.iterrows():
        out.append("| " + " | ".join(str(r.get(c, ""))[:60].replace("|", "\\|") for c in cols) + " |")
    return out


def build_md(over: pd.DataFrame) -> str:
    """Assemble the reviewable markdown from the classified overwrite table."""
    changed = over[over["changed"]]
    L: list[str] = [
        "# metadata_v2 overwrite candidates — reviewable artefact (combine step ii)", "",
        "_Read-only, deterministic. Blank-fills never overwrite; these are the per-sample stage's "
        "gated replacements of a **non-blank** ENA value — the only overwrites a v2 combine would apply. "
        "Review these before step iii (`combine.apply_gated_overwrites`). Nothing here is applied yet._", "",
    ]

    # ── reconciliation to §5c ──────────────────────────────────────────────────────────────────────────
    L += ["## Reconciliation to wrap-up §5c", "", "| field | candidates | §5c of record | ✓ |", "|---|--:|--:|:-:|"]
    ok = True
    for f in FIELDS:
        n = int((over["field"] == f).sum())
        exp = EXPECTED_5C[f]
        ok &= (n == exp)
        L.append(f"| {f} | {n} | {exp} | {'✅' if n == exp else '❌'} |")
    L.append(f"| **TOTAL** | **{len(over)}** | **{sum(EXPECTED_5C.values())}** | "
             f"**{'✅' if ok else '❌'}** |")
    L += ["", f"**Reconciliation: {'✅ EXACT' if ok else '❌ MISMATCH — investigate'}** "
          f"({len(changed)} of {len(over)} candidates genuinely change the value; the rest differ only in "
          "case/whitespace and are inert).", ""]

    # ── summary by field × class ───────────────────────────────────────────────────────────────────────
    L += ["## Summary by field & class", "", "| field | class | rows | flagged |", "|---|---|--:|--:|"]
    grp = over.groupby(["field", "class"])
    for (f, c), sub in grp:
        L.append(f"| {f} | {c} | {len(sub)} | {int((sub['review_flag'] != '').sum())} |")
    L.append("")

    # ── (b) collection_date ────────────────────────────────────────────────────────────────────────────
    d = over[over["field"] == "collection_date"]
    same = d[d["class"] == "date_same_year_refinement"]
    yc = d[d["class"] == "date_year_changed"]
    du = d[d["class"] == "date_unparsed"]
    L += ["## (b) collection_date — refinements", "",
          f"**{len(same)} same-year refinements** (e.g. `2019` → `2019-11-28`): the sanctioned low-risk "
          "exception — the year is preserved and only granularity is added. Sample:", ""]
    L += _md_table(same, ["study_accession", "sample_accession", "ena_value", "applied_value", "evidence"], cap=8)
    if len(yc):
        L += ["", f"### ⚠ {len(yc)} year-CHANGED (review — violates the same-year rule)", ""]
        L += _md_table(yc, ["study_accession", "sample_accession", "ena_value", "applied_value",
                            "evidence", "paper"])
    if len(du):
        L += ["", f"### ⚠ {len(du)} unparseable year (review)", ""]
        L += _md_table(du, ["study_accession", "sample_accession", "ena_value", "applied_value", "evidence"])
    L.append("")

    # ── (a) categorical ────────────────────────────────────────────────────────────────────────────────
    L += ["## (a) categorical vague→specific — country / host / isolation_source", ""]
    for f in CATEGORICAL:
        sub = over[(over["field"] == f) & over["changed"]]
        if not len(sub):
            L += [f"### {f} — 0 genuine changes", ""]
            continue
        # old→new fan-out: how many distinct NEW values each OLD value maps to (vague→many = healthy)
        fan = (sub.groupby(_norm_series(sub["ena_value"]))["applied_value"]
               .agg(n_rows="size", n_distinct_new=lambda s: s.map(_norm).nunique()))
        one_to_one = fan[fan["n_distinct_new"] == 1]
        L += [f"### {f} — {len(sub)} genuine changes, from {len(fan)} distinct ENA value(s)", "",
              f"_{len(fan[fan['n_distinct_new'] > 1])} ENA value(s) fan out to several specifics "
              f"(the healthy vague→specific pattern); {len(one_to_one)} map one-to-one._", ""]
        if f == "country" or len(sub) <= 40:
            # small enough to show in full — country's 16 concrete→concrete swaps must all be visible
            L += [f"⚠ **All {len(sub)} rows shown** (concrete ENA value replaced — review each):", ""]
            L += _md_table(sub, ["study_accession", "sample_accession", "ena_value", "applied_value",
                                 "evidence", "paper"])
        else:
            top = fan.sort_values("n_rows", ascending=False).head(12).reset_index()
            top.columns = ["ena_value", "n_rows", "n_distinct_new"]
            L += ["Top ENA values overwritten (by volume):", ""]
            L += _md_table(top, ["ena_value", "n_rows", "n_distinct_new"])
            L += ["", "Sample rows:", ""]
            L += _md_table(sub, ["study_accession", "sample_accession", "ena_value", "applied_value",
                                 "evidence"], cap=10)
        L.append("")

    # ── consolidated flags ─────────────────────────────────────────────────────────────────────────────
    flagged = over[over["review_flag"] != ""]
    L += ["## ⚠ Flagged for review (consolidated)", "",
          f"{len(flagged)} row(s) carry a review flag. `no_change` = case/whitespace-only (inert, not "
          "applied); `shortened` = new value is a shorter substring of the ENA one (typically a benign "
          "de-dup like `Blood_Blood`→`Blood` or an extract-from-token like `ST1_Stool_Organism_2`→`Stool`); "
          "`year_changed` / `date_unparsed` = the dates that break the same-year rule. Look before approving.", ""]
    if len(flagged):
        counts = flagged["review_flag"].value_counts()
        L += ["| review_flag | rows |", "|---|--:|"]
        L += [f"| {k} | {v} |" for k, v in counts.items()]
        L += [""]
        non_inert = flagged[flagged["review_flag"] != "no_change"]
        if len(non_inert):
            L += _md_table(non_inert, ["field", "study_accession", "ena_value", "applied_value",
                                       "review_flag", "paper"], cap=60)
            L.append("")

    # ── how to approve ─────────────────────────────────────────────────────────────────────────────────
    L += ["## How to approve (feeds combine step iii)", "",
          "Review `v2_overwrite_candidates.tsv`, keep the rows to apply (a natural default: all "
          "`date_same_year_refinement` + the categorical rows you accept, minus anything flagged you "
          "reject), and pass that subset to `combine.apply_gated_overwrites` (B3). Blank-fills (step i) "
          "need no sign-off — they cannot overwrite.", ""]
    return "\n".join(L) + "\n"


def _norm_series(s: pd.Series) -> pd.Series:
    """Vectorised :func:`_norm` for group keys."""
    return s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()


def main() -> None:
    """Build the reviewable v2 overwrite-candidates artefact (TSV + markdown)."""
    p = argparse.ArgumentParser(description="Reviewable artefact of per-sample overwrites a v2 combine would apply.")
    p.add_argument("--app", default="klebsiella")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--tags", default="train,test,tail100,tail50_99,tail25_49,tail10_24,sub10")
    args = p.parse_args()
    here = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else here / "applications" / args.app / "data"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    over = collect_overwrites(data_dir, tags)
    out = data_dir / "v2_overwrite_candidates.tsv"
    over.to_csv(out, sep="\t", index=False)
    out.with_suffix(".md").write_text(build_md(over))
    print(f"[overwrites] wrote {out} ({len(over)} candidates, "
          f"{int(over['changed'].sum())} genuine changes)", file=sys.stderr)


if __name__ == "__main__":
    main()
