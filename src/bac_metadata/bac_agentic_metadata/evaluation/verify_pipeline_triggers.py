r"""Per-tag pipeline-trigger gate — hard proof that every stage fired and no manual input was silently dropped.

"Too many times this has fallen down": a stage that quietly did nothing, or a hand-provided PDF / supp table
that was added but never processed, and no loud signal either way. The run-health report is a *soft* self-audit
(exit 0, bare counts); this gate is the **hard** complement — read-only, no LLM, one exit code per ``--tags`` —
so a broken run *fails loud* in CI / the driver loop instead of looking healthy.

It composes the checks that already exist rather than inventing new grading logic, resolving every path through
:class:`~engine.run_layout.RunPaths`. Per tag it asserts:

1. **find fired** — ``found_papers.tsv`` non-empty and its study set equals the graded set (find + grade ran
   over the *same* selection; a shortfall on either side is a silent skip).
2. **grade fired** — ``study_grades.tsv`` non-empty, one row per study; and, for a tail size-band tranche, its
   study set equals the batch-local ``selection/ena_sizing.tsv`` (the selection was fully graded).
3. **per_sample fired, NO silent 0** — every outcome row maps to a study in the selection; a ``direct``/
   ``two_hop`` join that produced ``n_fills==0`` is a FAIL (claimed a table but filled nothing), and any
   zero-fill row with an *empty* note is a FAIL (a 0 with no stated reason). Every honest 0 carries a loud
   :func:`~engine.stages._zero_bucket` reason.
4. **manual papers reconciled** — every ``find_papers/manual_download/<acc>.pdf`` for a study in this selection
   was consumed (``fulltext_source==local_pdf``) or is redundant-vs-OA (INFO); a PDF graded with *no* full text
   is an orphan (FAIL). Reuses ``audit_manual_curation``'s vocabulary.
5. **manual tables reconciled** — every ``manual_download_supp/<acc>.*`` for a study in this selection was
   consumed (``method∈{direct,two_hop}`` / ``table`` set) or carries a loud unanchored/manifest note (WARN);
   present-processed-but-unconsumed with no loud note is an orphan (FAIL).
6. **backfill fired** — when the whole-field gate marks ≥1 study ``covered``, ``backfill_applied.tsv`` is
   non-empty (the covered decision actually produced fills).
7. **fill + conservation** — ``filled_metadata.tsv`` non-empty, no completeness field *shrank* vs the base
   table (per the fill summary), and the escalation-conservation invariants hold for the tag
   (:func:`engine.escalation_conservation.verify_tags`, per-tag, master check off).

Writes ``run_progress/<tag>/run_health/pipeline_triggers.{md,tsv}`` and **exits non-zero** if any tag has a
FAIL. WARN (a loud, expected gap — an unanchored table, an unprocessed study) never fails the gate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import escalation_conservation as vc
from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec
from bac_metadata.bac_agentic_metadata.engine.stages import _zero_bucket
from bac_metadata.bac_agentic_metadata.evaluation.audit_manual_curation import (
    _LINKAGE_MARKERS,
    _LOCAL_SOURCES,
    _OA_SOURCES,
    _TABLE_METHODS,
    _supp_stems,
)

ENGINE_APPS = Path(__file__).resolve().parents[1] / "applications"
#: Backfill-gate status that means the grader vouched a whole-field value (so fills must exist).
_COVERED_STATUS = "covered"
#: Severity → exit weight: only FAIL fails the gate; WARN is loud-but-expected.
_SEVERITIES = ("FAIL", "WARN", "INFO", "OK")


def _f(check: str, severity: str, detail: str, accession: str = "") -> dict:
    """One report row (a finding); ``severity`` ∈ :data:`_SEVERITIES`."""
    return {"check": check, "severity": severity, "accession": accession, "detail": detail}


def _read_tsv(path: Path) -> pd.DataFrame:
    """Read a TSV as strings (blanks preserved); empty frame if absent/empty."""
    try:
        return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _studies(df: pd.DataFrame) -> set[str]:
    """The distinct ``study_accession`` set of a frame (empty if the column is absent)."""
    return set(df["study_accession"]) if "study_accession" in df.columns else set()


# ── pure checks (dataframe/collection in, findings out — unit-testable offline) ───────────────────────────

def check_find(found: pd.DataFrame, grades: pd.DataFrame) -> tuple[list[dict], set[str]]:
    """(1) find fired: ``found_papers`` non-empty and its study set equals the graded set. Returns (findings, U)."""
    universe = _studies(grades)
    found_studies = _studies(found)
    out: list[dict] = []
    if not len(found):
        out.append(_f("find", "FAIL", "found_papers.tsv missing/empty — the finder never produced output"))
        return out, universe
    missing = sorted(universe - found_studies)   # graded but the finder skipped them
    extra = sorted(found_studies - universe)     # found but never graded
    if missing:
        out.append(_f("find", "FAIL", f"{len(missing)} graded study(ies) absent from found_papers "
                                      f"(finder shortfall): {', '.join(missing[:6])}"))
    if extra:
        out.append(_f("find", "FAIL", f"{len(extra)} found study(ies) never graded "
                                      f"(grader shortfall): {', '.join(extra[:6])}"))
    if not missing and not extra:
        out.append(_f("find", "OK", f"{len(found_studies)} studies found == graded"))
    return out, universe


def check_grade(grades: pd.DataFrame, universe: set[str], selection_studies: set[str] | None) -> list[dict]:
    """(2) grade fired: non-empty, one row per study; for a tail band, study set == the batch selection."""
    out: list[dict] = []
    if not len(grades):
        return [_f("grade", "FAIL", "study_grades.tsv missing/empty — the grader never produced output")]
    n_rows, n_studies = len(grades), len(universe)
    if n_rows != n_studies:
        out.append(_f("grade", "FAIL", f"{n_rows} grade rows for {n_studies} distinct studies "
                                       "(duplicate/collided grade rows)"))
    if selection_studies is not None:
        miss = sorted(selection_studies - universe)   # selected but never graded
        if miss:
            out.append(_f("grade", "FAIL", f"{len(miss)} selected study(ies) absent from grades "
                                           f"(selection not fully graded): {', '.join(miss[:6])}"))
        else:
            out.append(_f("grade", "OK", f"{n_studies} studies graded == batch selection"))
    elif n_rows == n_studies:
        out.append(_f("grade", "OK", f"{n_studies} studies graded (1 row each)"))
    return out


def check_per_sample(outcomes: pd.DataFrame, universe: set[str]) -> list[dict]:
    """(3) per_sample fired with NO silent 0 — every 0-fill row has a loud reason; no empty direct/two_hop join."""
    out: list[dict] = []
    if not len(outcomes):
        return [_f("per_sample", "WARN", "per_sample_outcomes.tsv empty — no gated study with a paper in scope?")]
    if outcomes["study_accession"].nunique() != len(outcomes):
        dup = outcomes["study_accession"][outcomes["study_accession"].duplicated()].unique()
        out.append(_f("per_sample", "FAIL", f"duplicate outcome row(s) for: {', '.join(sorted(dup)[:6])}"))
    phantom = sorted(_studies(outcomes) - universe)
    if phantom:
        out.append(_f("per_sample", "FAIL", f"{len(phantom)} outcome study(ies) not in the graded selection: "
                                            f"{', '.join(phantom[:6])}"))
    n_fills = pd.to_numeric(outcomes.get("n_fills"), errors="coerce").fillna(0).astype(int)
    method = outcomes.get("method", pd.Series([""] * len(outcomes))).fillna("")
    note = outcomes.get("note", pd.Series([""] * len(outcomes))).fillna("")
    # A joined table (direct/two_hop) that filled nothing = a silent success.
    empty_join = outcomes[method.isin(_TABLE_METHODS) & (n_fills == 0)]
    for _, r in empty_join.iterrows():
        out.append(_f("per_sample", "FAIL", f"method={r['method']} but n_fills=0 (claimed a table, filled "
                                            "nothing — silent)", r["study_accession"]))
    # A zero-fill outcome with no stated reason = a silent 0.
    silent_zero = outcomes[(n_fills == 0) & (note.str.strip() == "")]
    for _, r in silent_zero.iterrows():
        out.append(_f("per_sample", "FAIL", "n_fills=0 with an empty note (0 with no stated reason)",
                      r["study_accession"]))
    if not empty_join.shape[0] and not silent_zero.shape[0] and not phantom:
        buckets = pd.Series([_zero_bucket(m, n) for m, n in zip(method[n_fills == 0], note[n_fills == 0],
                                                                strict=False)]).value_counts().to_dict()
        filled = int((n_fills > 0).sum())
        out.append(_f("per_sample", "OK", f"{len(outcomes)} outcomes: {filled} with fills; "
                                          f"0-fill reasons {buckets or '{}'} (all loud)"))
    return out


def check_manual_papers(grades: pd.DataFrame, pdf_stems: list[str], universe: set[str]) -> list[dict]:
    """(4) hand-downloaded PDFs consumed — for studies in this selection (Check-1 of audit_manual_curation)."""
    src_by_study: dict[str, set[str]] = {}
    if "study_accession" in grades.columns:
        for _, r in grades.iterrows():
            src_by_study.setdefault(r["study_accession"], set()).add((r.get("fulltext_source") or "").strip())
    out: list[dict] = []
    for acc in sorted(s for s in pdf_stems if s in universe):
        srcs = src_by_study.get(acc, set())
        if srcs & _LOCAL_SOURCES:
            out.append(_f("manual_paper", "OK", "consumed (fulltext_source=local_pdf)", acc))
        elif srcs & _OA_SOURCES:
            out.append(_f("manual_paper", "INFO", f"redundant — OA full text used instead ({sorted(srcs & _OA_SOURCES)})", acc))
        else:
            out.append(_f("manual_paper", "FAIL", f"downloaded PDF but graded without full text "
                                                  f"(fulltext_source={sorted(srcs)})", acc))
    return out


def check_manual_tables(outcomes: pd.DataFrame, supp: dict[str, list[Path]], universe: set[str]) -> list[dict]:
    """(5) hand-provided supp tables consumed — for studies in this selection (Check-2 of audit_manual_curation)."""
    used: set[str] = set()
    seen: set[str] = set()
    notes: dict[str, str] = {}
    for _, r in outcomes.iterrows():
        acc, meth, tbl = r["study_accession"], (r.get("method") or "").strip(), (r.get("table") or "").strip()
        seen.add(acc)
        notes[acc] = (r.get("note") or "").lower()
        if meth in _TABLE_METHODS or tbl:
            used.add(acc)
    out: list[dict] = []
    for acc in sorted(a for a in supp if a in universe):
        if acc in used:
            out.append(_f("manual_table", "OK", "consumed (method=direct/two_hop or table set)", acc))
        elif any(m in notes.get(acc, "") for m in _LINKAGE_MARKERS):
            out.append(_f("manual_table", "WARN", "wired but won't anchor to our accessions — linkage, not a loss", acc))
        elif acc not in seen:
            out.append(_f("manual_table", "WARN", "wired but study not in the per_sample outcomes yet", acc))
        else:
            out.append(_f("manual_table", "FAIL", "supp table present but not consumed — re-run per_sample / check format", acc))
    return out


def check_backfill(gate: pd.DataFrame, applied: pd.DataFrame) -> list[dict]:
    """(6) backfill fired — when the whole-field gate marks ≥1 study ``covered``, applied fills must exist."""
    if not len(gate):
        return [_f("backfill", "WARN", "backfill_gate_report.tsv missing/empty — backfill stage did not report")]
    status = gate.get("status", pd.Series(dtype=str)).fillna("")
    n_covered = int((status == _COVERED_STATUS).sum())
    if n_covered and not len(applied):
        return [_f("backfill", "FAIL", f"{n_covered} study×field covered by the gate but backfill_applied.tsv is empty")]
    if n_covered:
        return [_f("backfill", "OK", f"{n_covered} covered → {len(applied)} whole-field fills applied")]
    return [_f("backfill", "OK", "no whole-field value vouched (nothing to backfill)")]


_SUMMARY_ROW = re.compile(r"^\|\s*([a-z_]+)\s*\|\s*([0-9.]+)\s*\|\s*\**([0-9.]+)\**\s*\|")


def _summary_completeness(summary_md: Path, fields: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    """Parse the fill summary's per-field ``| field | base | filled |`` rows → {field: (base_frac, filled_frac)}."""
    out: dict[str, tuple[float, float]] = {}
    if not summary_md.exists():
        return out
    for line in summary_md.read_text().splitlines():
        m = _SUMMARY_ROW.match(line)
        if m and m.group(1) in fields:
            out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out


def check_fill(filled: pd.DataFrame, completeness: dict[str, tuple[float, float]],
               conservation_fails: list[str]) -> list[dict]:
    """(7) fill + conservation — final table non-empty, no field shrank vs base, conservation invariants hold."""
    out: list[dict] = []
    if not len(filled):
        out.append(_f("fill", "FAIL", "filled_metadata.tsv missing/empty — no final table produced"))
    else:
        shrank = {f: (b, v) for f, (b, v) in completeness.items() if v < b}
        if shrank:
            out.append(_f("fill", "FAIL", "field completeness SHRANK vs base: "
                                          + ", ".join(f"{f} {b:.3f}→{v:.3f}" for f, (b, v) in shrank.items())))
        elif completeness:
            out.append(_f("fill", "OK", f"{len(filled)} rows; no field shrank ("
                                        + ", ".join(f"{f} {b:.3f}→{v:.3f}" for f, (b, v) in completeness.items()) + ")"))
        else:
            out.append(_f("fill", "OK", f"{len(filled)} rows (no summary to compare completeness)"))
    if conservation_fails:
        out.append(_f("conservation", "FAIL", f"{len(conservation_fails)} invariant failure(s): "
                                              + "; ".join(conservation_fails[:4])))
    else:
        out.append(_f("conservation", "OK", "answer → apply → final invariants hold"))
    return out


# ── per-tag orchestration ─────────────────────────────────────────────────────────────────────────────

def verify_tag(data_dir: Path, tag: str, fields: tuple[str, ...]) -> list[dict]:
    """Run all seven checks for one tag; return the flat list of findings (severity-tagged)."""
    rp = RunPaths(data_dir, tag)
    found = _read_tsv(rp.found_papers_tsv)
    grades = _read_tsv(rp.study_grades_tsv)
    outcomes = _read_tsv(rp.per_sample_outcomes)
    gate = _read_tsv(rp.backfill_gate_report)
    applied = _read_tsv(rp.backfill_applied)
    filled = _read_tsv(rp.filled_metadata)
    sel_studies = _studies(_read_tsv(rp.selection_sizing)) if rp.selection_sizing.exists() else None

    findings, universe = check_find(found, grades)
    findings += check_grade(grades, universe, sel_studies)
    findings += check_per_sample(outcomes, universe)
    pdf_stems = [p.stem for p in rp.manual_papers_dir.glob("*.pdf")] if rp.manual_papers_dir.exists() else []
    findings += check_manual_papers(grades, pdf_stems, universe)
    findings += check_manual_tables(outcomes, _supp_stems(rp.manual_supp_dir), universe)
    findings += check_backfill(gate, applied)
    conservation_fails = vc.verify_tags(data_dir, [tag], amend=False, include_master=False, out=lambda *_: None)
    findings += check_fill(filled, _summary_completeness(rp.filled_metadata_summary, fields), conservation_fails)
    return findings


def _render_md(tag: str, findings: list[dict]) -> str:
    """Render a tag's findings to markdown, FAIL first."""
    order = {s: i for i, s in enumerate(_SEVERITIES)}
    rows = sorted(findings, key=lambda r: (order.get(r["severity"], 9), r["check"], r["accession"]))
    counts = {s: sum(1 for r in findings if r["severity"] == s) for s in _SEVERITIES}
    verdict = "FAIL" if counts["FAIL"] else ("WARN" if counts["WARN"] else "PASS")
    lines = [
        f"# Pipeline-trigger gate — tag `{tag}` — **{verdict}**",
        "",
        "Auto-generated by `evaluation/verify_pipeline_triggers.py` (read-only, no LLM). Hard proof that every "
        "stage fired and no hand-provided input was silently dropped. **FAIL** fails the gate; **WARN** is a "
        "loud, expected gap (e.g. an unanchored table).",
        "",
        f"**Summary:** {counts['FAIL']} FAIL · {counts['WARN']} WARN · {counts['INFO']} INFO · {counts['OK']} OK.",
        "",
        "| severity | check | accession | detail |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['severity']} | {r['check']} | {r['accession']} | {r['detail']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Run the gate over ``--tags``, write per-tag ``run_health/pipeline_triggers.{md,tsv}``, exit 1 on any FAIL."""
    p = argparse.ArgumentParser(description="Per-tag pipeline-trigger gate (read-only, hard exit code).")
    p.add_argument("--app", default="klebsiella", help="Application under applications/ (default klebsiella).")
    p.add_argument("--data-dir", default=None, help="Override data dir (default applications/<app>/data).")
    p.add_argument("--spec", default=None, help="attributes.yaml (default applications/<app>/attributes.yaml).")
    p.add_argument("--tags", required=True, help="Comma-separated run tags to verify (e.g. train,test,tail100).")
    p.add_argument("--no-fail", action="store_true", help="Always exit 0 (report only).")
    args = p.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else ENGINE_APPS / args.app / "data"
    spec_path = Path(args.spec) if args.spec else ENGINE_APPS / args.app / "attributes.yaml"
    if not data_dir.exists():
        sys.exit(f"data dir not found: {data_dir}")
    fields = tuple(AttributeSpec.from_yaml(str(spec_path)).completeness_fields)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    total_fail = 0
    for tag in tags:
        findings = verify_tag(data_dir, tag, fields)
        rp = RunPaths(data_dir, tag)
        rp.run_health_dir.mkdir(parents=True, exist_ok=True)
        rp.run_health_dir.joinpath("pipeline_triggers.md").write_text(_render_md(tag, findings))
        pd.DataFrame(findings, columns=["severity", "check", "accession", "detail"]).to_csv(
            rp.run_health_dir / "pipeline_triggers.tsv", sep="\t", index=False)
        n_fail = sum(1 for r in findings if r["severity"] == "FAIL")
        n_warn = sum(1 for r in findings if r["severity"] == "WARN")
        total_fail += n_fail
        verdict = "FAIL" if n_fail else ("WARN" if n_warn else "PASS")
        print(f"[{tag}] {verdict} — {n_fail} FAIL · {n_warn} WARN "
              f"→ run_progress/{tag}/run_health/pipeline_triggers.md", file=sys.stderr)
        for r in sorted((r for r in findings if r["severity"] in ("FAIL", "WARN")),
                        key=lambda r: (r["severity"], r["check"])):
            print(f"    {r['severity']:4s} {r['check']:14s} {r['accession']:14s} {r['detail']}", file=sys.stderr)

    print(f"\nTOTAL: {total_fail} FAIL across {len(tags)} tag(s)", file=sys.stderr)
    sys.exit(1 if (total_fail and not args.no_fail) else 0)


if __name__ == "__main__":
    main()
