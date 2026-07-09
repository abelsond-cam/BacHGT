"""Orphan-audit for the manual-curation loop — nothing hand-provided is silently dropped.

The agentic pipeline has three human-in-the-loop inputs whose *silent* non-integration is exactly the
failure class that let PRJEB28400's per-isolate table go missing. This script is the standing guard.
Read-only, no LLM. It cross-checks, per tag (and reusable across applications):

1. **Papers** — every hand-downloaded ``find_papers/manual_download/<acc>.pdf`` should be *consumed*:
   the study's grade row carries ``fulltext_source == local_pdf``. A study graded from an OA source
   instead (``europepmc_fulltext`` / ``pdf``) makes the local copy merely redundant (**INFO**); a study
   graded with **no** full text (``none`` / ``abstract``) despite a downloaded PDF, or absent from every
   graded tag, is an **orphan** — the PDF was downloaded and never used.
2. **Supplementary tables** — every committed ``manual_supp_tables/<acc>.*`` and legacy
   ``manual_download_supp/<acc>.*`` should be *consumed*: a ``per_sample_outcomes`` row for that study
   with ``method ∈ {direct, two_hop}`` (or a non-empty ``table``). Present-but-unused ⇒ **orphan**.
3. **Recoverable-but-unwired** — a curator-provided ENA per-isolate table sitting at
   ``project_k/.../ENA_projects/<acc>/data.csv`` that is **not** wired into the committed
   ``manual_supp_tables/`` (nor the legacy dir) ⇒ **orphan**; annotated *high-value* when the study is a
   known extraction victim (``NO_PMCID`` / ``abstained`` in ``per_sample_outcomes``).

Writes ``diagnostics/audit_manual_curation.{md,tsv}`` and **exits non-zero** when any orphan is found —
so a baseline run *fails loud* (it should flag PRJEB28400 + PRJDB5929 + the unused project_k tables),
and a post-fix run passing is the loop-closed signal.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.local_supplements import SUPP_EXTS

ENGINE_APPS = Path(__file__).resolve().parents[1] / "applications"
#: Default local mirror of the project_k ENA_projects tree (curator-downloaded per-study tables).
DEFAULT_PK_ROOT = "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Aaron Weimann's files - project_k"
ENA_PROJECTS_REL = "data/raw/metadata/study_level_metadata/ENA_projects"
#: fulltext_source values that mean a local (hand-downloaded) PDF was consumed / an OA full text was used.
_LOCAL_SOURCES = {"local_pdf"}
_OA_SOURCES = {"europepmc_fulltext", "pdf"}
#: per_sample_outcome methods that mean a supplementary table was actually joined.
_TABLE_METHODS = {"direct", "two_hop"}
#: outcome methods that mark a study whose table the agent could NOT fetch itself (a recovery target).
_VICTIM_METHODS = {"NO_PMCID", "abstained"}
_ACC_RE = re.compile(r"PRJ[A-Z]+\d+")
#: tag suffixes to ignore when auto-discovering per-tag artifacts.
_TAG_DENYLIST = {"", "opus", "tail_smoke", "test_basecache", "basecache"}


def _discover_tags(data_dir: Path) -> list[str]:
    """Auto-discover pipeline tags from the per-tag grade/outcome filenames (denylist-filtered)."""
    grading = data_dir / "study_lv_attributes" / "grading"
    persample = data_dir / "sample_lv_attributes" / "per_sample"
    tags: set[str] = set()
    for f in grading.glob("study_grades_*.tsv"):
        tags.add(f.stem[len("study_grades_"):])
    for f in persample.glob("per_sample_outcomes_*.tsv"):
        tags.add(f.stem[len("per_sample_outcomes_"):])
    return sorted(t for t in tags if t not in _TAG_DENYLIST)


def _load_grades(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Concatenate study_grades_<tag>.tsv over ``tags`` (adds a ``tag`` column); empty if none exist."""
    frames = []
    grading = data_dir / "study_lv_attributes" / "grading"
    for t in tags:
        f = grading / f"study_grades_{t}.tsv"
        if f.exists():
            df = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False)
            df["tag"] = t
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["study_accession", "fulltext_source", "tag"])


def _load_outcomes(data_dir: Path, tags: list[str]) -> pd.DataFrame:
    """Concatenate per_sample_outcomes_<tag>.tsv over ``tags`` (adds a ``tag`` column); empty if none."""
    frames = []
    persample = data_dir / "sample_lv_attributes" / "per_sample"
    for t in tags:
        f = persample / f"per_sample_outcomes_{t}.tsv"
        if f.exists():
            df = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False)
            df["tag"] = t
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["study_accession", "table", "method", "tag"])


def _supp_stems(*dirs: Path) -> dict[str, list[Path]]:
    """Map study accession (file stem) → its local supp-table file(s) across the given dirs."""
    out: dict[str, list[Path]] = {}
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPP_EXTS:
                out.setdefault(f.stem, []).append(f)
    return out


def audit(app: str, data_dir: Path, pk_root: Path) -> tuple[list[dict], list[str]]:
    """Run all three orphan checks; return (findings, notes). Each finding is a dict row for the report."""
    tags = _discover_tags(data_dir)
    grades = _load_grades(data_dir, tags)
    outcomes = _load_outcomes(data_dir, tags)
    notes = [f"app={app}  tags={tags or '(none)'}  grade_rows={len(grades)}  outcome_rows={len(outcomes)}"]

    # per-study rollups
    src_by_study: dict[str, set[str]] = {}
    for _, r in grades.iterrows():
        src_by_study.setdefault(r["study_accession"], set()).add((r.get("fulltext_source") or "").strip())
    used_table_studies: set[str] = set()
    victim_studies: set[str] = set()
    for _, r in outcomes.iterrows():
        acc, meth, tbl = r["study_accession"], (r.get("method") or "").strip(), (r.get("table") or "").strip()
        if meth in _TABLE_METHODS or tbl:
            used_table_studies.add(acc)
        if meth in _VICTIM_METHODS:
            victim_studies.add(acc)

    findings: list[dict] = []

    # ---- Check 1: hand-downloaded PDFs consumed? ----
    md_dir = data_dir / "find_papers" / "manual_download"
    for pdf in sorted(md_dir.glob("*.pdf")) if md_dir.exists() else []:
        acc = pdf.stem
        srcs = src_by_study.get(acc)
        if srcs is None:
            sev, detail = "WARN", "downloaded PDF but study not in any graded tag (unprocessed / out of scope)"
        elif srcs & _LOCAL_SOURCES:
            sev, detail = "OK", "consumed (fulltext_source=local_pdf)"
        elif srcs & _OA_SOURCES:
            sev, detail = "INFO", f"redundant — OA full text used instead ({sorted(srcs & _OA_SOURCES)})"
        else:
            sev, detail = "FAIL", f"downloaded PDF but graded without full text (fulltext_source={sorted(srcs)})"
        findings.append({"check": "paper_downloaded", "severity": sev, "accession": acc,
                         "path": str(pdf.relative_to(data_dir.parent)), "detail": detail})

    # ---- Check 2: local supp tables consumed? ----
    supp_dirs = [data_dir.parent / "manual_supp_tables", data_dir / "sample_lv_attributes" / "manual_download_supp"]
    supp = _supp_stems(*supp_dirs)
    for acc, files in sorted(supp.items()):
        rel = ", ".join(str(f.relative_to(data_dir.parent)) for f in files)
        if acc in used_table_studies:
            sev, detail = "OK", "consumed (per_sample_outcomes method=direct/two_hop or table set)"
        else:
            sev, detail = "FAIL", "local supp table present but never used in per_sample_outcomes"
        findings.append({"check": "supp_table", "severity": sev, "accession": acc, "path": rel, "detail": detail})

    # ---- Check 3: recoverable project_k tables wired? ----
    wired_stems = set(supp)  # accession stems already present in a committed/legacy supp dir
    ena_projects = pk_root / ENA_PROJECTS_REL
    if not ena_projects.exists():
        notes.append(f"[skip] project_k ENA_projects not found at {ena_projects} — check 3 skipped (mirror offline)")
    else:
        for d in sorted(p for p in ena_projects.iterdir() if p.is_dir()):
            if not (d / "data.csv").exists():
                continue
            tokens = _ACC_RE.findall(d.name) or [d.name]
            rel = f"ENA_projects/{d.name}/data.csv"  # relative to the project_k mirror (portable, committable)
            if any(tok in wired_stems for tok in tokens):
                findings.append({"check": "projectk_table", "severity": "OK", "accession": d.name,
                                 "path": rel, "detail": f"wired via supp dir ({tokens})"})
                continue
            victim = [tok for tok in tokens if tok in victim_studies]
            tag = " [HIGH-VALUE: extraction victim]" if victim else ""
            findings.append({"check": "projectk_table", "severity": "FAIL", "accession": d.name,
                             "path": rel,
                             "detail": f"data.csv present but not wired into manual_supp_tables/{tag}"})
    return findings, notes


def _render_md(app: str, findings: list[dict], notes: list[str]) -> str:
    """Render findings to markdown, orphans (FAIL) first."""
    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "OK": 3}
    rows = sorted(findings, key=lambda r: (order.get(r["severity"], 9), r["check"], r["accession"]))
    counts = {s: sum(1 for r in findings if r["severity"] == s) for s in ("FAIL", "WARN", "INFO", "OK")}
    lines = [
        f"# Manual-curation orphan audit — {app}",
        "",
        "Auto-generated by `evaluation/audit_manual_curation.py` (read-only). **FAIL** = a hand-provided input "
        "silently dropped, or a recoverable table left unwired — the failure class that lost PRJEB28400's table.",
        "",
        f"**Summary:** {counts['FAIL']} FAIL · {counts['WARN']} WARN · {counts['INFO']} INFO · {counts['OK']} OK.",
        "",
    ]
    for n in notes:
        lines.append(f"- _{n}_")
    lines += ["", "| severity | check | accession | detail | path |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['severity']} | {r['check']} | {r['accession']} | {r['detail']} | `{r['path']}` |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Run the orphan audit, write ``diagnostics/audit_manual_curation.{md,tsv}``, exit 1 if any orphan."""
    p = argparse.ArgumentParser(description="Orphan-audit the manual-curation loop (read-only).")
    p.add_argument("--app", default="klebsiella", help="Application under applications/ (default klebsiella).")
    p.add_argument("--data-dir", default=None, help="Override data dir (default applications/<app>/data).")
    p.add_argument("--project-k-root", default=os.environ.get("BACHGT_PROJECT_K_ROOT", DEFAULT_PK_ROOT),
                   help="project_k mirror root holding ENA_projects/<acc>/data.csv.")
    p.add_argument("--no-fail", action="store_true", help="Always exit 0 (report only; do not fail on orphans).")
    args = p.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else ENGINE_APPS / args.app / "data"
    if not data_dir.exists():
        sys.exit(f"data dir not found: {data_dir}")
    findings, notes = audit(args.app, data_dir, Path(args.project_k_root))

    diagnostics = data_dir / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / "audit_manual_curation.md").write_text(_render_md(args.app, findings, notes))
    pd.DataFrame(findings, columns=["severity", "check", "accession", "detail", "path"]).to_csv(
        diagnostics / "audit_manual_curation.tsv", sep="\t", index=False)

    n_fail = sum(1 for r in findings if r["severity"] == "FAIL")
    for n in notes:
        print(n, file=sys.stderr)
    print(f"Wrote diagnostics/audit_manual_curation.{{md,tsv}} — {n_fail} orphan(s)", file=sys.stderr)
    for r in sorted((r for r in findings if r["severity"] == "FAIL"), key=lambda r: (r["check"], r["accession"])):
        print(f"  FAIL  {r['check']:16s} {r['accession']:28s} {r['detail']}", file=sys.stderr)
    sys.exit(1 if (n_fail and not args.no_fail) else 0)


if __name__ == "__main__":
    main()
