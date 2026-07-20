"""cf_status review register — surface every whole-project cf call AND every big study for human review.

The M. abscessus headline phenotype (CF vs non-CF) carries two review risks that this register makes visible
(David, 2026-07-20):

* **Non-CF-by-absence inferences** — a paper that describes its patient cohort but never mentions CF is graded
  non-CF and APPLIED (blank cells only; a known value is never overwritten). Because that is an inference, every
  one is listed here with the agent's cohort argument so a curator can revert a weak call.
* **Big / explicit studies** — a large study (>= ``big_frac`` of the cohort) drives a lot of the phenotype, and
  we have been burned before (PRJEB2779, 2,143 samples). These are surfaced with their full cf composition and
  how cf was decided, whether or not they carried a whole-project call — so nothing huge slips through unchecked.

Read-only. Reads the tag's grade JSONL + filled table + the base + the curated escalations; writes
``run_progress/<tag>/cf_review_register.md``. Usage: ``python -m ...evaluation.cf_review_register <tag> [<tag> ...]``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.categorise.preclean import preclean_base
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

DATA = "src/bac_metadata/bac_agentic_metadata/applications/m_abs/data"
BIG_FRAC = 0.01  # a study >= 1% of the cohort is a "big decision" — always reviewed (matches the engine gate)


def _canon_cf(v: object) -> str:
    """Canonicalise a filled cf_status cell for composition counts (case/hyphen-insensitive; ? → blank)."""
    s = str(v).strip().lower()
    if s in ("", "?"):
        return "(blank)"
    if s == "cf":
        return "CF"
    if s in ("non-cf", "non_cf", "noncf"):
        return "non-CF"
    return str(v).strip()  # Environmental / Animal / anything else — surfaced verbatim under "other"


def _cf_skip_notes() -> dict[str, str]:
    """Curator cf_status skip/answer notes from the (untracked) escalations master, keyed by study."""
    p = Path(DATA) / "curated" / "curated_escalations.tsv"
    if not p.exists():
        return {}
    e = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
    e = e[e["field"] == "cf_status"]
    out = {}
    for _, r in e.iterrows():
        ans, note = r.get("answer", "").strip(), r.get("answer_note", "").strip()
        out[r["study_accession"]] = f"answer={ans!r}" + (f"; {note}" if note else "")
    return out


def build(tags: list[str]) -> str:
    """Render the cf review register (Section A whole-project calls + Section B big studies) for the tags."""
    spec = AttributeSpec.from_yaml(f"{DATA}/../attributes.yaml")
    base = pd.read_csv(f"{DATA}/inputs/base_table.csv", dtype=str, keep_default_na=False)
    base, _ = preclean_base(base, spec)
    base["_cf"] = backfill.strip_placeholders(base["cf_status"])
    size = base.groupby("study_accession")["sample_accession"].nunique()
    cohort_total = int(base["sample_accession"].nunique())
    blank_by_study = (base.assign(_blank=base["_cf"].isna())
                      .drop_duplicates("sample_accession").groupby("study_accession")["_blank"].sum().to_dict())
    skip_notes = _cf_skip_notes()

    calls, big_rows = [], []
    for tag in tags:
        rp = RunPaths(DATA, tag)
        grades = {}
        if rp.study_grades_jsonl.exists():
            for line in open(rp.study_grades_jsonl):
                r = json.loads(line)
                grades[r.get("study_accession")] = (r.get("backfill", {}) or {}).get("cf_status", {}) or {}
        filled = (pd.read_csv(rp.filled_metadata, sep="\t", dtype=str, keep_default_na=False)
                  if rp.filled_metadata.exists() else pd.DataFrame())
        comp = {}
        if not filled.empty and "cf_status" in filled.columns:
            for acc, g in filled.groupby("study_accession"):
                v = g["cf_status"].map(_canon_cf).value_counts()
                comp[acc] = {k: int(n) for k, n in v.items()}

        for acc, cf in grades.items():
            val = (cf.get("proposed_value") or "").strip()
            if val and cf.get("applies_whole_project"):
                calls.append({"tag": tag, "study": acc, "proposed": val,
                              "filled": int(blank_by_study.get(acc, 0)),
                              "argument": " ".join((cf.get("evidence_quote") or "").split())})

        studies = set(grades) | set(comp)
        for acc in studies:
            n = int(size.get(acc, 0))
            if n < BIG_FRAC * cohort_total:
                continue  # Section B is the big studies only; small whole-project calls live in Section A
            cf = grades.get(acc, {})
            wp = (cf.get("proposed_value") or "").strip()
            if wp and cf.get("applies_whole_project"):
                decision = f"whole-project {wp}"
            elif acc in skip_notes:
                decision = f"curator-skip ({skip_notes[acc]})"
            else:
                decision = "known-only (no whole-project fill)"
            c = comp.get(acc, {})
            other = sum(v for k, v in c.items() if k not in ("CF", "non-CF", "(blank)"))
            big_rows.append({"tag": tag, "study": acc, "n": n,
                             "CF": c.get("CF", 0), "non-CF": c.get("non-CF", 0), "blank": c.get("(blank)", 0),
                             "other": other, "decision": decision,
                             "argument": " ".join((cf.get("evidence_quote") or "").split())})

    df = pd.DataFrame(calls)
    lines = ["# cf_status review register", ""]
    lines += ["## A. Whole-project cf calls (applied to blank cells; known values never overwritten)", "",
              "**non-CF first** — scrutinise the *non-CF-by-absence* inference: the argument must describe the "
              "patient cohort (ages/comorbidities) AND note no CF mention. Flag any weak argument to revert.", "",
              "| tag | study | proposed | blanks filled | argument (agent's basis) |", "|---|---|---|---|---|"]
    if not df.empty:
        df["_ord"] = df["proposed"].str.lower().map(lambda v: 0 if "non" in v else 1)
        for _, r in df.sort_values(["_ord", "filled"], ascending=[True, False]).iterrows():
            lines.append(f"| {r['tag']} | {r['study']} | **{r['proposed']}** | {r['filled']} | "
                         f"{(r['argument'][:280] or '(no quote)')} |")
        n_noncf = int(df["proposed"].str.lower().str.contains("non").sum())
        lines += ["", f"{len(df)} whole-project calls ({n_noncf} non-CF, {len(df) - n_noncf} CF)."]
    else:
        lines += ["", "_(none)_"]

    bdf = pd.DataFrame(big_rows)
    lines += ["", f"## B. Big studies (>= {BIG_FRAC:.0%} of the cohort) — cf composition + decision, ALWAYS reviewed",
              "", "The large studies drive the phenotype and have caused problems before (PRJEB2779). Check each "
              "cf split + how it was decided, regardless of whether it carried a whole-project call.", "",
              "| tag | study | n | CF | non-CF | blank | other | decision | argument |",
              "|---|---|---|---|---|---|---|---|---|"]
    if not bdf.empty:
        for _, r in bdf.sort_values("n", ascending=False).iterrows():
            lines.append(f"| {r['tag']} | {r['study']} | {r['n']} | {r['CF']} | {r['non-CF']} | {r['blank']} | "
                         f"{r['other']} | {r['decision']} | {(r['argument'][:180])} |")
    else:
        lines += ["", "_(none — filled table not present yet)_"]
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI: build the register for the given tag(s); write it beside a single tag's run outputs."""
    tags = sys.argv[1:] or ["mabs_top20"]
    out = build(tags)
    print(out)
    if len(tags) == 1:
        dest = Path(f"{DATA}/run_progress/{tags[0]}/cf_review_register.md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out)
        print(f"[written] {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
