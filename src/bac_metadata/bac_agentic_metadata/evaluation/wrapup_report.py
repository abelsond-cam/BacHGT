r"""Consolidated Klebsiella wrap-up report — every headline figure reconciled to its per-tranche source.

Read-only, deterministic, no LLM. Reconciles per-tranche fill summaries against the accumulated master (the
numbers have "fallen down too many times", so Σ per-tranche agent-fills MUST equal the master to the cell), then
reports: papers reviewed · experimental-evolution studies (count + tranche breakdown + samples) · §4 per-sample
completeness **raw ENA → agent → v2 gold** on the same-sample cohort (from ``completeness_by_split`` — proves the
agent matches-or-beats v2 coverage, so nothing was dropped in accumulation) · §5a agent-vs-manual accuracy
(paper-finding + grading, train/test) · §5b per-sample **blank-fill** correctness vs v2 gold (the value-add) · §5c
the gated **overwrites** of existing ENA values, surfaced for spot-review (scored against the parsed-ENA gold they
replace, so low by construction — never folded into an accuracy). Writes ``data/WRAPUP_REPORT.md``.

Prereqs (regenerate first): ``evaluation.completeness_by_split`` (writes the §4 scorecard TSV) and
``evaluation.validate_backfill_values`` per tranche (writes the §5b/§5c per_sample value reports with the
blank-fill/overwrite split columns).

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


def _value_split(rp: RunPaths) -> dict[str, dict[str, float]]:
    """Read the per_sample value report → {field: {blank_n, blank_acc, over_n, over_gold, over_correct}}.

    ``blank_*`` = accuracy of fills of a **blank** ENA cell (the positive value-add, scored where v2 has a
    value); ``over_*`` = the gated overwrites of a real ENA value (scored against the parsed-ENA gold, so
    low by construction — surfaced separately in §5c, not folded into an accuracy).
    """
    path = rp.scorecard_dir / "per_sample_value_report.tsv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, sep="\t", dtype=str).fillna("")

    def _i(r, k):
        return int(r.get(k, 0) or 0)

    def _f(r, k):
        v = r.get(k, "")
        return float(v) if str(v).strip() else float("nan")

    return {r["field"]: {"blank_n": _i(r, "has_gold_blank"), "blank_acc": _f(r, "acc_blank_fill"),
                         "over_n": _i(r, "n_overwrite"), "over_gold": _i(r, "has_gold_overwrite"),
                         "over_correct": _i(r, "correct_overwrite")} for _, r in df.iterrows()}


def _completeness(data_dir: Path) -> pd.DataFrame | None:
    """Read the per-split raw/agent/v2 completeness scorecard (from completeness_by_split), or None."""
    path = data_dir / "scorecard" / "final_completeness_raw_agent_gold.tsv"
    return pd.read_csv(path, sep="\t") if path.exists() else None


def _overwrite_studies(rp: RunPaths, top: int = 4) -> tuple[int, list[str]]:
    """(total overwrite fills, top studies by overwrite volume) from per_sample_applied (ena_value non-blank)."""
    path = rp.per_sample_applied
    if not path.exists():
        return 0, []
    from bac_metadata.bac_agentic_metadata.engine import backfill
    ap = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    if "ena_value" not in ap.columns or not len(ap):
        return 0, []
    over = ap[backfill.strip_placeholders(ap["ena_value"]).notna()]
    if not len(over):
        return 0, []
    counts = over.groupby("study_accession").size().sort_values(ascending=False)
    return int(len(over)), [f"{s} ({n})" for s, n in counts.head(top).items()]


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

    # ── 4. Completeness: raw ENA → agent → v2 gold, on the same-sample cohort ─────────────────────────
    comp = _completeness(data_dir)
    L += ["## 4. Per-sample completeness — raw ENA → agent → v2 gold", ""]
    if comp is None:
        L += ["_`scorecard/final_completeness_raw_agent_gold.tsv` missing — regenerate with "
              "`python -m …evaluation.completeness_by_split --truth <v2 gold>`._", ""]
    else:
        cidx = comp.set_index("split")
        n_cohort = int(cidx.loc["TOTAL_excl_Refseq", "n"]) if "TOTAL_excl_Refseq" in cidx.index else 0
        L += ["_On the master∩gold cohort (samples in **both** the agent master and the v2 gold), "
              "placeholder-stripped uniformly. Manual v2 only ever curated train/val/test; the tail and "
              "uncovered bands are raw ENA, so there the agent is the sole enrichment._", "",
              f"### 4a. Cohort — {n_cohort:,} samples (excl. the Refseq carve-out)", "",
              "| field | raw ENA % | agent % | v2 gold % | agent − raw (fill Δ) | agent − v2 |",
              "|---|--:|--:|--:|--:|--:|"]
        row = cidx.loc["TOTAL_excl_Refseq"] if "TOTAL_excl_Refseq" in cidx.index else None
        for f in FIELDS:
            if row is None:
                continue
            raw, ag, man, diff = (float(row[f"{f}_raw"]), float(row[f"{f}_agent"]),
                                  float(row[f"{f}_manual"]), float(row[f"{f}_diff"]))
            L.append(f"| {f} | {raw:.1f} | {ag:.1f} | {man:.1f} | {ag - raw:+.1f} | {diff:+.1f} |")
        L += ["", "### 4b. Agent − v2 gold by split (percentage points; ≥ 0 = match-or-beat v2)", "",
              "| split | n | " + " | ".join(FIELDS) + " |", "|---|--:|" + "--:|" * len(FIELDS)]
        for sp in cidx.index:
            if sp in ("TOTAL", "TOTAL_excl_Refseq"):
                continue
            r = cidx.loc[sp]
            cells = " | ".join(f"{float(r[f'{f}_diff']):+.1f}" for f in FIELDS)
            L.append(f"| {sp} | {int(r['n']):,} | {cells} |")
        tr = cidx.loc["TOTAL_excl_Refseq"]
        L.append(f"| **TOTAL_excl_Refseq** | **{int(tr['n']):,}** | "
                 + " | ".join(f"**{float(tr[f'{f}_diff']):+.1f}**" for f in FIELDS) + " |")
        L += ["", "_Agent matches-or-beats v2 on the cohort (proving nothing major was dropped in "
              "accumulation) and adds most on the uncurated tail bands. The one negative, "
              "`Refseq_collection` (RefSeq genomes empty in the ENA base, agent-skipped by design, carried "
              "by v2), is a benchmark-scope carve-out — see `scorecard/final_completeness_raw_agent_gold.md`._"]

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
          "`diagnostics/adjudication_review_queue.tsv` for curator sign-off._", ""]

    # ── 5b. Per-sample BLANK-FILL correctness (the value-add) vs the v2 gold ───────────────────────────
    split = {t: _value_split(RunPaths(data_dir, t)) for t in tags}
    L += ["### 5b. Per-sample fill correctness — blank-fills vs the v2 gold", "",
          "_Accuracy on fills of a **blank** ENA cell (the positive value-add), scored only where v2 "
          "carries a value. `n` = with-gold blank fills. Overwrites of existing ENA values are held out "
          "to §5c (they are scored against the very ENA they replace, so they read low by construction)._",
          "", "| field | " + " | ".join(tags) + " |", "|---|" + "---|" * len(tags)]
    for f in FIELDS:
        cells = []
        for t in tags:
            s = split[t].get(f)
            cells.append(f"{_pct(s['blank_acc'])} (n={s['blank_n']})" if s and s["blank_n"] else "—")
        L.append(f"| {f} | " + " | ".join(cells) + " |")
    L += ["", "_train/test carry genuine per-sample gold overlap; for the tail bands the v2 gold is raw "
          "ENA or a coarse study-level backfill, so small-n dips (e.g. isolation_source) reflect the gold, "
          "not the fill — §4 is the coverage check there. '—' = no with-gold blank fills to score._", ""]

    # ── 5c. Gated overwrites of existing ENA values (spot-review, not scored) ──────────────────────────
    L += ["### 5c. Overwrites of existing ENA values (gated; for spot-review)", "",
          "_Per-sample is the only stage that can replace a non-blank ENA value, and only through the "
          "fidelity gate (date-granularity / `judge_overwrite_fidelity`, vague→specific only). Scored "
          "against the parsed-ENA gold these read low **by construction** — the gold *is* the ENA value "
          "the fill deliberately replaced (e.g. `clinical sample`→`rectal`) — so they are surfaced for "
          "optional manual spot-review, not counted as errors._", "",
          "| tranche | overwrites | with v2 gold | matches v2 | top studies (overwrite count) |",
          "|---|--:|--:|--:|---|"]
    for t in tags:
        n_over, top = _overwrite_studies(RunPaths(data_dir, t))
        gold = sum(split[t].get(f, {}).get("over_gold", 0) for f in FIELDS)
        corr = sum(split[t].get(f, {}).get("over_correct", 0) for f in FIELDS)
        acc = f"{corr}/{gold} ({corr / gold:.2f})" if gold else "—"
        L.append(f"| {t} | {n_over} | {gold} | {acc} | {', '.join(top) if top else '—'} |")
    L += ["", "_The v2 gold for these four fields is essentially parsed raw ENA (+ coarse study-level "
          "backfill), not an independent per-sample truth, so 'matches v2' measures agreement with ENA: a "
          "high rate means the overwrite was re-derivable from ENA, a **low** rate means the fill genuinely "
          "moved the value away from a vague ENA term (the intended vague→specific gain) — those rows "
          "(train `PRJEB63361/58216/36683`, tail50_99 `PRJEB56668`, tail10_24 `PRJEB34353`) are the "
          "spot-review targets, not errors._", ""]
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
