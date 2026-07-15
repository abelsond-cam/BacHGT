"""Validate paper finding against the curated ``paper_link`` (train+val only).

The finder is fed only the accession; here we score its pick against the held-out curated
``paper_link`` (+ ``paper_title`` for publisher URLs with no extractable id). Per the project rule
we **record disagreements rather than assume the sheet is right**: when the found paper ≠ curated,
an Opus critique agent (``paper_finder.adjudicate_find``) judges which one actually describes the
project — the curated link may be wrong, paywalled, or one of several.

Classification per train+val accession: ``exact_match`` (found id ∈ curated ids), ``title_match``
(curated link unresolvable / different id but titles agree), ``mismatch``, ``not_found`` (finder
abstained), ``no_curated_link``. Reports find-accuracy, a category table, per-channel recall (which
retrieval channel supplied the winner), and the grounded-verify rate.

Writes ``data/find_validation_report.{tsv,md}`` (+ ``data/find_adjudication_report.{md,tsv}`` with
``--adjudicate``).
"""

from __future__ import annotations

import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.fulltext import (
    _europepmc_search,
    _resolve_identifier,
    _search_query,
)

APP_DIR = Path(__file__).resolve().parents[1] / "applications" / "klebsiella"  # gold-bearing app tree (see evaluation/__init__.py)
DATA_DIR = APP_DIR / "data"
SPEC_PATH = APP_DIR / "attributes.yaml"
SNAPSHOT_PATH = DATA_DIR / "inputs" / "study_level_metadata_all_combined_v1.0_20260105.csv"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
ENA_CACHE = DATA_DIR / "cache" / "ena"
FULLTEXT_CACHE = DATA_DIR / "cache" / "fulltext"
LLM_CACHE = DATA_DIR / "cache" / "llm"
ACCESSION_RE = re.compile(r"\bPRJ[A-Z]+\d+\b")
_TITLE_MATCH = 0.82  # SequenceMatcher ratio over normalised titles


def _norm_id(kind: str, value: str) -> str:
    """Canonical id token for matching."""
    if kind == "pmcid":
        return f"pmcid:{value.upper()}"
    if kind == "doi":
        return f"doi:{value.lower()}"
    return f"{kind}:{value}"


def _curated_ids(paper_link: str) -> set[str]:
    """Resolve a curated ``paper_link`` (possibly pipe-separated) to a set of id tokens."""
    out: set[str] = set()
    for part in re.split(r"[|]", paper_link or ""):
        part = part.strip()
        if not part:
            continue
        kind, value = _resolve_identifier(part)
        if kind != "url":  # url == no extractable id
            out.add(_norm_id(kind, value))
    return out


def _epmc_triple(token: str) -> set[str]:
    """Expand one id token (``pmid:`` / ``pmcid:`` / ``doi:``) to its full {pmid,pmcid,doi} set.

    Cross-id canonicalization: one paper carries a PMID, a PMCID and a DOI, but a curated link
    usually exposes only one of them. A single cached Europe PMC lookup recovers the other two so a
    curated PubMed link matches a found DOI (etc.) for the same article.
    """
    if ":" not in token:
        return set()
    kind, value = token.split(":", 1)
    query = _search_query(kind, value)
    rec = _europepmc_search(query, FULLTEXT_CACHE) if query else None
    if not rec:
        return set()
    out: set[str] = set()
    if rec.get("pmid"):
        out.add(f"pmid:{rec['pmid']}")
    if rec.get("pmcid"):
        out.add(f"pmcid:{str(rec['pmcid']).upper()}")
    if rec.get("doi"):
        out.add(f"doi:{str(rec['doi']).lower()}")
    return out


def _expand_via_epmc(tokens: set[str]) -> set[str]:
    """Union the Europe PMC id-triple of every token (the cross-id canonicalization step)."""
    out: set[str] = set()
    for tok in tokens:
        out |= _epmc_triple(tok)
    return out


def _found_ids(row: pd.Series) -> set[str]:
    """Id tokens for the finder's chosen paper."""
    out = set()
    if pd.notna(row.get("chosen_pmid")) and str(row.get("chosen_pmid")) not in ("", "nan"):
        out.add(f"pmid:{row['chosen_pmid']}")
    if pd.notna(row.get("chosen_pmcid")) and str(row.get("chosen_pmcid")) not in ("", "nan"):
        out.add(f"pmcid:{str(row['chosen_pmcid']).upper()}")
    if pd.notna(row.get("chosen_doi")) and str(row.get("chosen_doi")) not in ("", "nan"):
        out.add(f"doi:{str(row['chosen_doi']).lower()}")
    return out


def _norm_title(t: str) -> str:
    """Lowercase, strip non-alphanumerics for fuzzy title comparison."""
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def _title_sim(a: str, b: str) -> float:
    """SequenceMatcher ratio over normalised titles (0 if either is empty)."""
    na, nb = _norm_title(a), _norm_title(b)
    return SequenceMatcher(None, na, nb).ratio() if na and nb else 0.0


def _gt_by_accession() -> dict[str, dict]:
    """Per-accession curated GT, unioned across ALL curated rows for that study.

    A study often has several curated paper rows (different outputs, or the same article under
    different links). We union their id sets and keep every (title, link) so the finder is scored
    against the *whole* curated set, not just whichever row happened to come first.
    """
    snap = pd.read_csv(SNAPSHOT_PATH, dtype=str).fillna("")
    gt: dict[str, dict] = {}
    for _, r in snap.iterrows():
        link = r.get("paper_link", "").strip()
        ids = _curated_ids(link)
        title = (r.get("paper_title", "") or r.get("paper_short_title", "")).strip()
        has_link = bool(link) and link.lower() not in ("na", "n/a", "none", "")
        for acc in ACCESSION_RE.findall(r.get("study_accessions", "")):
            e = gt.setdefault(acc, {"papers": [], "curated_ids": set(), "has_link": False})
            e["papers"].append({"title": title, "link": link, "has_link": has_link})
            e["curated_ids"] |= ids
            e["has_link"] = e["has_link"] or has_link
    return gt


def _classify(row: pd.Series, gt: dict | None) -> str:
    """Classify one found row against the (unioned) curated GT.

    Match in three escalating ways: (1) raw id intersection against the union of all curated ids;
    (2) cross-id canonicalization — expand both sides to full {pmid,pmcid,doi} triples via Europe
    PMC and retry (only when the cheap check misses); (3) soft title match against ANY curated
    title. Anything else is a true mismatch (handed to the adjudicator).
    """
    if gt is None or not gt.get("has_link"):
        return "no_curated_link"
    if str(row.get("none_found")).lower() == "true":
        return "not_found"
    found = _found_ids(row)
    cur = gt["curated_ids"]
    if found & cur:
        return "exact_match"
    if (found | _expand_via_epmc(found)) & (cur | _expand_via_epmc(cur)):
        return "exact_match"
    chosen_title = row.get("chosen_title", "")
    if any(_title_sim(chosen_title, p["title"]) >= _TITLE_MATCH for p in gt["papers"]):
        return "title_match"
    return "mismatch"


def _curated_links(gt: dict) -> list[str]:
    """Every curated link recorded for a study (deduped, link-bearing rows only)."""
    return list(dict.fromkeys(p["link"] for p in gt.get("papers", []) if p["has_link"]))


def _best_curated(chosen_title: str, gt: dict) -> dict:
    """The curated paper (title, link) most title-similar to the found pick — the one to adjudicate."""
    papers = [p for p in gt.get("papers", []) if p["has_link"]] or gt.get("papers", [])
    if not papers:
        return {"title": "", "link": ""}
    return max(papers, key=lambda p: _title_sim(chosen_title, p["title"]))


def _first_id(*vals: object) -> str | None:
    """First value that is a real, non-empty id string (pandas reads blank TSV cells as NaN/"nan")."""
    for v in vals:
        s = str(v).strip()
        if s and s.lower() != "nan":
            return s
    return None


def _adjudicate_mismatches(mismatches: list[dict], model: str, backend: str) -> list[dict]:
    """Run the find-adjudication agent on each mismatch (found vs curated)."""
    from bac_metadata.bac_agentic_metadata.engine import paper_finder
    from bac_metadata.bac_agentic_metadata.engine.ena_sizing import study_title_and_description
    from bac_metadata.bac_agentic_metadata.engine.fulltext import fetch_fulltext
    from bac_metadata.bac_agentic_metadata.engine.llm import make_llm

    llm = make_llm(backend, model=model, cache_dir=LLM_CACHE)
    out = []
    for m in mismatches:
        acc = m["study_accession"]
        study = study_title_and_description(acc, cache_dir=ENA_CACHE)
        found_ref = _first_id(m.get("chosen_pmcid"), m.get("chosen_doi"), m.get("chosen_pmid"))
        found_ft = fetch_fulltext(str(found_ref), cache_dir=FULLTEXT_CACHE) if found_ref else None
        cur_ft = fetch_fulltext(m["paper_link"], cache_dir=FULLTEXT_CACHE) if m.get("paper_link") else None
        print(f"[adjudicate-find] {acc} found={found_ref} vs curated={m['paper_link'][:50]}", file=sys.stderr)
        verdict = paper_finder.adjudicate_find(
            llm, accession=acc, ena_title=study["study_title"], ena_description=study["study_description"],
            sizing_row={"ena_taxon_samples": m.get("ena_taxon_samples")},
            found_label=f"{m.get('chosen_title')} ({found_ref})",
            found_text=(found_ft.text if found_ft else "") or (found_ft.title if found_ft else ""),
            curated_label=f"{m.get('paper_title')} ({m['paper_link']})",
            curated_text=(cur_ft.text if cur_ft else "") or (cur_ft.title if cur_ft else ""),
            model=model,
        )
        out.append({**m, **{f"adj_{k}": v for k, v in verdict.items()}})
    return out


def main() -> None:
    """Parse arguments and write the paper finding find-validation report."""
    parser = argparse.ArgumentParser(description="Validate paper finding (Klebsiella).")
    parser.add_argument("--found", default=str(DATA_DIR / "find_papers" / "found_papers.tsv"), help="found_papers TSV.")
    parser.add_argument("--folds", default="train,val",
                        help="Folds to validate against GT (default train,val keeps the test fold sealed; "
                             "the pipeline passes the run's fold, e.g. 'test', to open it deliberately).")
    parser.add_argument("--adjudicate", action="store_true", help="Adjudicate mismatches with the critique agent.")
    parser.add_argument("--adjudicate-model", default="claude-opus-4-8")
    parser.add_argument("--adjudicate-backend", default="subscription", choices=["subscription", "api"])
    parser.add_argument("--report-prefix", default="find",
                        help="Report basename prefix (default 'find' -> find_validation_report.*; use "
                             "e.g. 'find_opus' to compare finder models without clobbering).")
    args = parser.parse_args()

    found = pd.read_csv(args.found, sep="\t", dtype=str)
    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    sizing = pd.read_csv(DATA_DIR / "ena_assessment" / "ena_sizing.tsv", sep="\t", dtype=str)[["study_accession", "ena_taxon_samples"]]
    df = found.merge(split, on="study_accession", how="left").merge(sizing, on="study_accession", how="left")
    folds = [f.strip() for f in args.folds.split(",") if f.strip()]
    df = df[df["fold"].isin(folds)].copy()
    gt = _gt_by_accession()
    df["category"] = df.apply(lambda r: _classify(r, gt.get(r["study_accession"])), axis=1)
    print(f"Validating {len(df)} {args.folds} found rows", file=sys.stderr)

    cats = df["category"].value_counts().to_dict()
    scored = df[df["category"].isin(["exact_match", "title_match", "mismatch", "not_found"])]
    correct = int((scored["category"].isin(["exact_match", "title_match"])).sum())
    denom = len(scored)
    acc = correct / denom if denom else float("nan")

    md = [f"# paper finding validation — paper-finding vs curated paper_link ({args.folds})\n"]
    md.append(f"Found rows in {args.folds}: **{len(df)}**.\n")
    md.append(f"## Find-accuracy: {acc:.2f}  ({correct}/{denom} matched among accessions with a curated link)\n")
    md.append(f"Category counts: {cats}\n")

    # Per-channel recall (which channel supplied a matched winner).
    matched = df[df["category"].isin(["exact_match", "title_match"])]
    md.append("## Winning channel (matched finds)\n")
    md.append("```\n" + matched["chosen_found_via"].value_counts().to_string() + "\n```")
    # Grounded-verify rate + confidence mix.
    vr = (df["verified"].astype(str).str.lower() == "true").sum()
    md.append(f"\n## Grounded-verify: {vr}/{len(df)} picks had the accession confirmed in the paper text.")
    if "find_confidence" in df.columns:
        md.append(f"Confidence mix: {df['find_confidence'].value_counts().to_dict()}")

    # Mismatch + not_found lists (the actionable part).
    mismatch_rows = []
    md.append("\n## Mismatches (found ≠ any curated paper)\n")
    for _, r in df[df["category"] == "mismatch"].iterrows():
        g = gt.get(r["study_accession"], {})
        links = _curated_links(g)
        best = _best_curated(r.get("chosen_title", "") or "", g)
        md.append(f"- `{r['study_accession']}` found={r.get('chosen_doi') or r.get('chosen_pmcid') or r.get('chosen_pmid')} "
                  f"(via {r.get('chosen_found_via')}, verified={r.get('verified')}) vs {len(links)} curated: {links}")
        mismatch_rows.append({
            "study_accession": r["study_accession"], "chosen_title": r.get("chosen_title"),
            "chosen_pmid": r.get("chosen_pmid"), "chosen_pmcid": r.get("chosen_pmcid"), "chosen_doi": r.get("chosen_doi"),
            "paper_title": best["title"], "paper_link": best["link"],
            "ena_taxon_samples": r.get("ena_taxon_samples"),
        })
    md.append("\n## Abstained (not_found, with a curated link)\n")
    for _, r in df[df["category"] == "not_found"].iterrows():
        g = gt.get(r["study_accession"], {})
        md.append(f"- `{r['study_accession']}` (n_candidates={r.get('n_candidates')}) curated={_curated_links(g)}")

    find_dir = Path(args.found).parent   # write reports beside the found_papers input (run_progress/<tag>/find/)
    (find_dir / f"{args.report_prefix}_validation_report.md").write_text("\n".join(md) + "\n")
    df[["study_accession", "fold", "category", "chosen_found_via", "verified", "find_confidence",
        "chosen_pmid", "chosen_pmcid", "chosen_doi", "coverage_fraction"]].to_csv(
        find_dir / f"{args.report_prefix}_validation_report.tsv", sep="\t", index=False)
    print(f"Wrote {args.report_prefix}_validation_report.{{md,tsv}} (accuracy {acc:.2f})", file=sys.stderr)

    if args.adjudicate:
        print(f"Adjudicating {len(mismatch_rows)} mismatches with {args.adjudicate_model}", file=sys.stderr)
        adjs = _adjudicate_mismatches(mismatch_rows, args.adjudicate_model, args.adjudicate_backend) if mismatch_rows else []
        from collections import Counter

        def _is_same(a: dict) -> bool:
            return str(a.get("adj_same_paper")).lower() == "true"

        # A "mismatch" the adjudicator rules is the SAME paper (different link/DOI, or preprint vs
        # published) is not a finding error — fold it back in for an adjudicated accuracy.
        same = sum(_is_same(a) for a in adjs)
        found_or_both = sum(a.get("adj_verdict") in ("found_correct", "both_describe") for a in adjs if not _is_same(a))
        adj_correct = correct + same + found_or_both
        adj_acc = adj_correct / denom if denom else float("nan")

        amd = ["# paper finding find-adjudication — found vs curated on mismatches\n"]
        amd.append(f"Adjudicated {len(adjs)}. same_paper={same} (link/DOI variants, not errors); "
                   f"verdicts: {dict(Counter(a['adj_verdict'] for a in adjs))}.\n")
        amd.append(f"## Adjudicated find-accuracy: {adj_acc:.2f}  ({adj_correct}/{denom}) — folding in "
                   f"{same} same-paper variants + {found_or_both} where the found paper is the correct "
                   "(or a co-)describing study.\n")
        for a in adjs:
            same_tag = "SAME PAPER" if _is_same(a) else a["adj_verdict"]
            amd.append(f"\n## `{a['study_accession']}` — {same_tag}")
            amd.append(f"- found: {a.get('chosen_title')}  |  curated: {a.get('paper_title')}")
            amd.append(f"- same_paper={a.get('adj_same_paper')} — {a.get('adj_same_paper_reason','')}")
            amd.append(f"- justification: {a.get('adj_justification_quote','')!r}")
            amd.append(f"- reasoning: {a.get('adj_reasoning','')}")
            if str(a.get("adj_rule_gap", "")).strip():
                amd.append(f"- ⚠️ rule_gap: {a['adj_rule_gap']}")
        (find_dir / f"{args.report_prefix}_adjudication_report.md").write_text("\n".join(amd) + "\n")
        # Always emit a headered TSV (even with 0 mismatches) so downstream never sees an empty/missing
        # file and silently scores 0 — a present-but-empty file honestly means "no disagreements".
        adj_cols = ["study_accession", "adj_verdict", "adj_same_paper", "adj_same_paper_reason",
                    "chosen_title", "paper_title", "adj_justification_quote", "adj_reasoning", "adj_rule_gap"]
        (pd.DataFrame(adjs) if adjs else pd.DataFrame(columns=adj_cols)).to_csv(
            find_dir / f"{args.report_prefix}_adjudication_report.tsv", sep="\t", index=False)
        print(f"Wrote {args.report_prefix}_adjudication_report.{{md,tsv}} (adjudicated accuracy {adj_acc:.2f})", file=sys.stderr)


if __name__ == "__main__":
    main()
