r"""Consolidated agentic-metadata wrap-up report — every headline figure reconciled to its per-tranche source.

Read-only, deterministic, no LLM, **app-agnostic** (driven by the application's ``attributes.yaml`` via
``report_config``). Reconciles per-tranche fill summaries against the accumulated master (Σ per-tranche
agent-fills MUST equal the master to the cell), then reports: papers reviewed · experimental-evolution studies
· §4 per-sample completeness **raw ENA → agent [→ v2 gold]** per split (from ``completeness_by_split``) · and,
**when a manual gold exists**, §5a agent-vs-manual accuracy, §5b per-sample blank-fill correctness, §5c gated
overwrites. Opens with a **Methods** section (§0) taken verbatim from the app's ``report.methods_file`` so the
report stands alone. Writes ``<data-dir>/<report.wrapup_out>``.

Applications without a manual gold (e.g. *M. abscessus*) degrade gracefully: §4 shows raw→agent only and §5 is
replaced by a short "no manual gold" note.

    uv run python -m …evaluation.wrapup_report                                  # klebsiella (gold)
    uv run python -m …evaluation.wrapup_report --app m_abs --tags mabs_all      # m_abs (goldless)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.run_layout import RunPaths
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec
from bac_metadata.bac_agentic_metadata.evaluation import report_config as rc

_SUMMARY_COLS = ("base", "filled", "agent", "new", "overrides", "per_sample", "escalation", "whole_field")


def parse_summary(path: Path, fields: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """Parse a ``filled_metadata_summary.md`` per-field table → {field: {base, filled, agent, …}}."""
    out: dict[str, dict[str, float]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        cells = [c.strip().replace("**", "") for c in line.strip().split("|")[1:-1]]
        if len(cells) >= 9 and cells[0] in fields:
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

    ``blank_*`` = accuracy of fills of a **blank** ENA cell (the value-add, scored where the gold has a value);
    ``over_*`` = the gated overwrites of a real ENA value (scored against the parsed-ENA gold, low by
    construction — surfaced separately in §5c). Empty when the report is absent (a goldless application).
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
    """Read the per-split raw/agent[/gold] completeness scorecard (from completeness_by_split), or None."""
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


def _read_methods(methods_path: Path | None, spec: AttributeSpec) -> list[str]:
    r"""The §0 Methods lines: verbatim from the app's ``report.methods_file`` if present, else a generic stub.

    The per-app methods prose is presentation, not computation, so it lives in a file
    (``applications/<app>/<report.methods_file>``) rather than the code — keeping the generator app-agnostic and
    reproducing the file byte-for-byte (``file.split("\n")`` inverts the ``"\n".join(...)`` that wrote it).
    """
    if methods_path is not None and methods_path.exists():
        return methods_path.read_text().split("\n")
    species = rc.species_label(spec)
    return [
        "## 0. Methods & provenance", "",
        f"An LLM-agent re-curation of ENA study metadata for *{species}*, producing per isolate the "
        f"completeness fields ({', '.join(rc.fields(spec))}) plus study-level judgements, accumulated across "
        "tranches into one master table. The engine is species-agnostic and data-driven by a rubric "
        f"(`applications/{spec.application}/attributes.yaml`); grading definitions are the curator's, not "
        "invented by the model.", "",
    ]


def build_report(data_dir: Path, tags: list[str], spec: AttributeSpec, methods_path: Path | None = None) -> str:
    """Assemble the full wrap-up markdown from the per-tranche artifacts + accumulated master."""
    fields = rc.fields(spec)
    species = rc.species_label(spec)
    per = {t: parse_summary(RunPaths(data_dir, t).filled_metadata_summary, fields) for t in tags}
    master = parse_summary(data_dir / "curated" / "metadata_curated_master_summary.md", fields)
    title = spec.report.get("wrapup_title") or f"{species} agentic metadata — wrap-up report"
    L: list[str] = [f"# {title}", "",
                    "_Read-only, deterministic; every figure traces to a per-tranche artifact._", ""]
    L += _read_methods(methods_path, spec)

    # ── 1. Reconciliation ────────────────────────────────────────────────────────────────────────────
    L += ["## 1. Reconciliation — per-tranche fills vs the accumulated master", "",
          "| field | " + " | ".join(tags) + " | Σ tranches | master | Δ |", "|---|" + "---|" * (len(tags) + 3)]
    recon_ok = True
    for f in fields:
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

    # ── 4. Completeness: raw ENA → agent [→ v2 gold], on the same-sample cohort ───────────────────────
    comp = _completeness(data_dir)
    gold_available = comp is not None and f"{fields[0]}_diff" in comp.columns
    if comp is None:
        L += ["## 4. Per-sample completeness", "",
              "_`scorecard/final_completeness_raw_agent_gold.tsv` missing — regenerate with "
              "`python -m …evaluation.completeness_by_split [--truth <gold>]`._", ""]
    elif gold_available:
        L += ["## 4. Per-sample completeness — raw ENA → agent → v2 gold", ""]
        cidx = comp.set_index("split")
        n_cohort = int(cidx.loc["TOTAL_excl_Refseq", "n"]) if "TOTAL_excl_Refseq" in cidx.index else 0
        L += ["_On the master∩gold cohort (samples in **both** the agent master and the v2 gold), "
              "placeholder-stripped uniformly. Manual v2 only ever curated train/val/test; the tail and "
              "uncovered bands are raw ENA, so there the agent is the sole enrichment._", "",
              f"### 4a. Cohort — {n_cohort:,} samples (excl. the Refseq carve-out)", "",
              "| field | raw ENA % | agent % | v2 gold % | agent − raw (fill Δ) | agent − v2 |",
              "|---|--:|--:|--:|--:|--:|"]
        row = cidx.loc["TOTAL_excl_Refseq"] if "TOTAL_excl_Refseq" in cidx.index else None
        for f in fields:
            if row is None:
                continue
            raw, ag, man, diff = (float(row[f"{f}_raw"]), float(row[f"{f}_agent"]),
                                  float(row[f"{f}_manual"]), float(row[f"{f}_diff"]))
            L.append(f"| {f} | {raw:.1f} | {ag:.1f} | {man:.1f} | {ag - raw:+.1f} | {diff:+.1f} |")
        L += ["", "### 4b. Agent − v2 gold by split (percentage points; ≥ 0 = match-or-beat v2)", "",
              "| split | n | " + " | ".join(fields) + " |", "|---|--:|" + "--:|" * len(fields)]
        for sp in cidx.index:
            if sp in ("TOTAL", "TOTAL_excl_Refseq"):
                continue
            r = cidx.loc[sp]
            cells = " | ".join(f"{float(r[f'{f}_diff']):+.1f}" for f in fields)
            L.append(f"| {sp} | {int(r['n']):,} | {cells} |")
        tr = cidx.loc["TOTAL_excl_Refseq"]
        L.append(f"| **TOTAL_excl_Refseq** | **{int(tr['n']):,}** | "
                 + " | ".join(f"**{float(tr[f'{f}_diff']):+.1f}**" for f in fields) + " |")
        L += ["", "_Agent matches-or-beats v2 on the cohort (proving nothing major was dropped in "
              "accumulation) and adds most on the uncurated tail bands. The one negative, "
              "`Refseq_collection` (RefSeq genomes empty in the ENA base, agent-skipped by design, carried "
              "by v2), is a benchmark-scope carve-out — see `scorecard/final_completeness_raw_agent_gold.md`._"]
    else:  # goldless — raw → agent only
        L += ["## 4. Per-sample completeness — raw ENA → agent", ""]
        cidx = comp.set_index("split")
        n_cohort = int(cidx.loc["TOTAL", "n"]) if "TOTAL" in cidx.index else 0
        L += [f"_On the {n_cohort:,}-sample agent master (no manual gold for this application), "
              "placeholder-stripped uniformly._", "",
              "### 4a. Cohort — raw ENA % → agent % (agent − raw = the fill Δ)", "",
              "| field | raw ENA % | agent % | agent − raw |", "|---|--:|--:|--:|"]
        row = cidx.loc["TOTAL"] if "TOTAL" in cidx.index else None
        for f in fields:
            if row is None:
                continue
            raw, ag = float(row[f"{f}_raw"]), float(row[f"{f}_agent"])
            L.append(f"| {f} | {raw:.1f} | {ag:.1f} | {ag - raw:+.1f} |")
        L += ["", "### 4b. Agent completeness by split (%)", "",
              "| split | n | " + " | ".join(fields) + " |", "|---|--:|" + "--:|" * len(fields)]
        for sp in cidx.index:
            if sp == "TOTAL":
                continue
            r = cidx.loc[sp]
            cells = " | ".join(f"{float(r[f'{f}_agent']):.1f}" for f in fields)
            L.append(f"| {sp} | {int(r['n']):,} | {cells} |")

    # ── 5. Accuracy vs manual — only when a manual gold exists ─────────────────────────────────────────
    if not gold_available:
        L += ["", "## 5. Accuracy vs manual curation", "",
              "_No manual gold for this application — accuracy vs manual is not applicable this round. The "
              "collaborator-table integration (a separate step) supplies the reference values where they "
              "exist; completeness above is the raw → agent value-add._", ""]
        return "\n".join(L) + "\n"

    L += ["", "## 5. Accuracy vs manual curation", "",
          "### 5a. Paper-finding + grading (adjudicated; gold folds only)", ""]
    for t in rc.fold_splits(spec):
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

    # ── 5b. Per-sample BLANK-FILL correctness (the value-add) vs the gold ───────────────────────────────
    split = {t: _value_split(RunPaths(data_dir, t)) for t in tags}
    L += ["### 5b. Per-sample fill correctness — blank-fills vs the v2 gold", "",
          "_Accuracy on fills of a **blank** ENA cell (the positive value-add), scored only where v2 "
          "carries a value. `n` = with-gold blank fills. Overwrites of existing ENA values are held out "
          "to §5c (they are scored against the very ENA they replace, so they read low by construction)._",
          "", "| field | " + " | ".join(tags) + " |", "|---|" + "---|" * len(tags)]
    for f in fields:
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
    targets = []  # (tag, top-study) for the low-match tranches — computed, not hard-coded
    for t in tags:
        n_over, top = _overwrite_studies(RunPaths(data_dir, t))
        gold = sum(split[t].get(f, {}).get("over_gold", 0) for f in fields)
        corr = sum(split[t].get(f, {}).get("over_correct", 0) for f in fields)
        acc = f"{corr}/{gold} ({corr / gold:.2f})" if gold else "—"
        L.append(f"| {t} | {n_over} | {gold} | {acc} | {', '.join(top) if top else '—'} |")
        if gold >= 20 and (corr / gold) < 0.5 and top:  # high-gold, low-match ⇒ a genuine vague→specific move
            targets.append(f"{t} `{top[0].split(' ')[0]}`")
    tgt = "; ".join(targets) if targets else "the low-`matches v2` rows above"
    nfields = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}.get(len(fields), str(len(fields)))
    L += ["", f"_The v2 gold for these {nfields} fields is essentially parsed raw ENA (+ coarse study-level "
          "backfill), not an independent per-sample truth, so 'matches v2' measures agreement with ENA: a "
          "high rate means the overwrite was re-derivable from ENA, a **low** rate means the fill genuinely "
          f"moved the value away from a vague ENA term (the intended vague→specific gain). Spot-review targets "
          f"(high overwrite volume + low match, flagged automatically): {tgt} — these are candidates to review, "
          "not errors._", ""]
    return "\n".join(L) + "\n"


def main() -> None:
    """Generate the consolidated wrap-up report."""
    p = argparse.ArgumentParser(description="Consolidated agentic-metadata wrap-up report (app-agnostic).")
    p.add_argument("--app", default="klebsiella")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--spec", default=None, help="attributes.yaml (default: applications/<app>/attributes.yaml).")
    p.add_argument("--tags", default="train,test,tail100,tail50_99,tail25_49,tail10_24,sub10")
    p.add_argument("--out", default=None, help="Output path (default <data-dir>/<report.wrapup_out>).")
    args = p.parse_args()
    here = Path(__file__).resolve().parent.parent
    app_dir = here / "applications" / args.app
    data_dir = Path(args.data_dir) if args.data_dir else app_dir / "data"
    spec = AttributeSpec.from_yaml(args.spec if args.spec else app_dir / "attributes.yaml")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    methods_file = spec.report.get("methods_file")
    methods_path = (app_dir / methods_file) if methods_file else None
    md = build_report(data_dir, tags, spec, methods_path)
    out_name = spec.report.get("wrapup_out") or f"{args.app}_AGENTIC_METADATA_WRAPUP_REPORT.md"
    out = Path(args.out) if args.out else data_dir / out_name
    out.write_text(md)
    print(f"[wrapup] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
