r"""Consolidated Klebsiella wrap-up report — every headline figure reconciled to its per-tranche source.

Read-only, deterministic, no LLM. Reconciles per-tranche fill summaries against the accumulated master (the
numbers have "fallen down too many times", so Σ per-tranche agent-fills MUST equal the master to the cell), then
reports: papers reviewed · experimental-evolution studies (count + tranche breakdown + samples) · the 4 per-sample
variables' base→filled improvement (cohort + per-tranche) · agent-vs-manual accuracy (paper-finding + grading,
train/test) · per-field value accuracy vs the v2 gold (all tranches, where gold covers). Writes
``data/WRAPUP_REPORT.md``.

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.wrapup_report \
        --tags train,test,tail100,tail50_99,tail25_49,tail10_24,sub10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths

FIELDS = ("country", "collection_date", "isolation_source", "host")
_SUMMARY_COLS = ("base", "filled", "agent", "new", "overrides", "per_sample", "escalation", "whole_field")


def parse_summary(path: Path) -> dict[str, dict[str, float]]:
    """Parse a ``filled_metadata_summary.md`` per-field table → {field: {base, filled, agent, …}}."""
    out: dict[str, dict[str, float]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        cells = [c.strip().replace("**", "") for c in line.strip().split("|")[1:-1]]
        if len(cells) >= 9 and cells[0] in FIELDS:
            try:
                vals = [float(c) for c in cells[1:9]]
            except ValueError:
                continue
            out[cells[0]] = dict(zip(_SUMMARY_COLS, vals, strict=True))
    return out


def _papers(rp: RunPaths) -> dict[str, int]:
    """Counts from a tranche's found_papers + study_grades: studies, papers found, full-text read, manual PDFs."""
    d = {"studies": 0, "found": 0, "fulltext": 0, "manual_pdf": 0}
    fp = rp.found_papers_tsv
    if fp.exists():
        f = pd.read_csv(fp, sep="\t", dtype=str).fillna("")
        d["studies"] = len(f)
        d["found"] = int((f["none_found"].str.lower() != "true").sum()) if "none_found" in f else 0
    g = rp.study_grades_tsv
    if g.exists():
        gr = pd.read_csv(g, sep="\t", dtype=str).fillna("")
        if "is_full_text" in gr:
            d["fulltext"] = int((gr["is_full_text"].str.lower() == "true").sum())
        if "fulltext_source" in gr:
            d["manual_pdf"] = int((gr["fulltext_source"] == "local_pdf").sum())
    return d


def _evo(rp: RunPaths) -> tuple[int, int]:
    """(n experimental_evolution studies, n samples in them) for a tranche, from its grades + applied fold size."""
    g = rp.study_grades_tsv
    if not g.exists():
        return 0, 0
    gr = pd.read_csv(g, sep="\t", dtype=str).fillna("")
    if "study_type_excluded" not in gr:
        return 0, 0
    return int((gr["study_type_excluded"].str.lower() == "true").sum()), 0


def _value_accuracy(rp: RunPaths, kind: str) -> dict[str, tuple[int, float]]:
    """Read a value-accuracy report (per_sample/backfill) → {field: (has_gold, accuracy)}; {} if absent/no gold."""
    path = rp.scorecard_dir / f"{kind}_value_report.tsv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    out = {}
    for _, r in df.iterrows():
        hg = int(r.get("has_gold", 0) or 0)
        acc = r.get("accuracy", "")
        out[r["field"]] = (hg, float(acc) if str(acc).strip() else float("nan"))
    return out


def _accuracy(rp: RunPaths) -> pd.DataFrame | None:
    """The agent-vs-manual scorecard for a gold fold (train/test), or None."""
    path = rp.scorecard_dir / "agent_vs_manual.tsv"
    return pd.read_csv(path, sep="\t") if path.exists() else None


def _pct(x: float) -> str:
    return f"{x:.3f}" if x == x else "—"  # NaN → em-dash


def build_report(data_dir: Path, tags: list[str]) -> str:
    """Assemble the full wrap-up markdown from the per-tranche artifacts + accumulated master."""
    per = {t: parse_summary(RunPaths(data_dir, t).filled_metadata_summary) for t in tags}
    master = parse_summary(data_dir / "curated" / "metadata_curated_master_summary.md")
    L: list[str] = ["# Klebsiella agentic metadata — wrap-up report", "",
                    "_Read-only, deterministic; every figure traces to a per-tranche artifact._", ""]

    # ── 1. Reconciliation ────────────────────────────────────────────────────────────────────────────
    L += ["## 1. Reconciliation — per-tranche fills vs the accumulated master", "",
          "| field | " + " | ".join(tags) + " | Σ tranches | master | Δ |", "|---|" + "---|" * (len(tags) + 3)]
    recon_ok = True
    for f in FIELDS:
        sigma = sum(int(per[t].get(f, {}).get("agent", 0)) for t in tags)
        m = int(master.get(f, {}).get("agent", 0))
        recon_ok &= (sigma == m)
        cells = " | ".join(str(int(per[t].get(f, {}).get("agent", 0))) for t in tags)
        L.append(f"| {f} | {cells} | {sigma} | {m} | {m - sigma} |")
    L += ["", f"**Reconciliation: {'✅ EXACT (Σ tranches == master, all fields)' if recon_ok else '❌ MISMATCH — investigate'}**", ""]

    # ── 2. Papers reviewed ───────────────────────────────────────────────────────────────────────────
    L += ["## 2. Papers reviewed", "", "| tranche | studies | papers found | full-text read | manual PDFs |",
          "|---|---|---|---|---|"]
    tot = {"studies": 0, "found": 0, "fulltext": 0, "manual_pdf": 0}
    for t in tags:
        p = _papers(RunPaths(data_dir, t))
        for k in tot:
            tot[k] += p[k]
        L.append(f"| {t} | {p['studies']} | {p['found']} | {p['fulltext']} | {p['manual_pdf']} |")
    L.append(f"| **TOTAL** | **{tot['studies']}** | **{tot['found']}** | **{tot['fulltext']}** | **{tot['manual_pdf']}** |")

    # ── 3. Experimental-evolution studies ────────────────────────────────────────────────────────────
    L += ["", "## 3. Experimental-evolution studies flagged for exclusion", "",
          "| tranche | evo studies |", "|---|---|"]
    evo_total = 0
    for t in tags:
        n, _ = _evo(RunPaths(data_dir, t))
        evo_total += n
        L.append(f"| {t} | {n} |")
    L.append(f"| **TOTAL** | **{evo_total}** |")
    # samples from the master (authoritative)
    mtab = pd.read_csv(data_dir / "curated" / "metadata_curated_master.tsv", sep="\t", dtype=str,
                       low_memory=False, usecols=["study_accession", "study_type_excluded"]).fillna("")
    evo_samples = int((mtab["study_type_excluded"].str.lower() == "true").sum())
    L += ["", f"**{evo_total} studies / {evo_samples} samples** now carry `study_type_excluded=True` for "
          "downstream removal.", ""]

    # ── 4. Four-variable improvement ─────────────────────────────────────────────────────────────────
    L += ["## 4. Per-sample completeness — base → filled", "",
          "### Cohort (master)", "", "| field | base | filled | Δ pp |", "|---|---|---|---|"]
    for f in FIELDS:
        b, fi = master.get(f, {}).get("base", float("nan")), master.get(f, {}).get("filled", float("nan"))
        L.append(f"| {f} | {_pct(b)} | {_pct(fi)} | +{(fi - b) * 100:.1f} |")
    L += ["", "### Per tranche (filled completeness)", "",
          "| field | " + " | ".join(tags) + " |", "|---|" + "---|" * len(tags)]
    for f in FIELDS:
        cells = " | ".join(_pct(per[t].get(f, {}).get("filled", float("nan"))) for t in tags)
        L.append(f"| {f} | {cells} |")

    # ── 5. Accuracy vs manual ────────────────────────────────────────────────────────────────────────
    L += ["", "## 5. Accuracy vs manual curation", "",
          "### 5a. Paper-finding + grading (adjudicated; gold folds only)", ""]
    for t in ("train", "test"):
        if t not in tags:
            continue
        acc = _accuracy(RunPaths(data_dir, t))
        if acc is None:
            continue
        L += [f"**{t}**", "", "| item | N | agreement | agent acc | manual acc | improvement |", "|---|---|---|---|---|---|"]
        for _, r in acc.iterrows():
            L.append(f"| {r['item']} | {int(r['N'])} | {r['agreement']:.3f} | {r['agent_accuracy']:.3f} "
                     f"| {r['manual_accuracy']:.3f} | {r['improvement']:+.3f} |")
        L.append("")
    L += ["_Residual disagreements the adjudicator did not rule for the agent are in "
          "`diagnostics/adjudication_review_queue.tsv` for curator sign-off._", "",
          "### 5b. Per-field value accuracy vs the v2 gold (per-sample fills)", "",
          "| field | " + " | ".join(tags) + " |", "|---|" + "---|" * len(tags)]
    for f in FIELDS:
        cells = []
        for t in tags:
            va = _value_accuracy(RunPaths(data_dir, t), "per_sample").get(f)
            cells.append(f"{_pct(va[1])} (n={va[0]})" if va and va[0] else "—")
        L.append(f"| {f} | " + " | ".join(cells) + " |")
    L += ["", "_'—' = the tranche's samples are not in the manual v2 gold (nothing to score against)._", ""]
    return "\n".join(L) + "\n"


def main() -> None:
    """Generate the consolidated wrap-up report."""
    p = argparse.ArgumentParser(description="Consolidated Klebsiella agentic-metadata wrap-up report.")
    p.add_argument("--app", default="klebsiella")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--tags", default="train,test,tail100,tail50_99,tail25_49,tail10_24,sub10")
    p.add_argument("--out", default=None, help="Output path (default <data-dir>/WRAPUP_REPORT.md).")
    args = p.parse_args()
    here = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else here / "applications" / args.app / "data"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    md = build_report(data_dir, tags)
    out = Path(args.out) if args.out else data_dir / "WRAPUP_REPORT.md"
    out.write_text(md)
    print(f"[wrapup] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
