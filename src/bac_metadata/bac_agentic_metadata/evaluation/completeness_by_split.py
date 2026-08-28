"""Per-split completeness scorecard: raw ENA vs agent master vs (optional) manual gold — app-agnostic.

Formalises the previously ad-hoc ``scorecard/final_completeness_raw_agent_gold.md`` so the agent-vs-manual
picture is reproducible from committed helpers. For each split and each per-sample completeness field it reports
the fraction of samples that carry a real value in:

* **raw**    — the ENA base table as deposited (``inputs/base_table.csv``);
* **agent**  — the accumulated agent master (``curated/metadata_curated_master.tsv``);
* **manual** — the curated gold ``*_parsed`` columns (metadata_v2) — **only when a gold is supplied**.

Fields, field display order, the tail size-bands, the fold labels and any synthetic collections are all driven
by the application's ``attributes.yaml`` (its non-graded ``report:`` block, via ``report_config``), so the same
tool serves Klebsiella (four fields, a v2 gold, the Kp tail bands) and *M. abscessus* (five fields incl.
``cf_status``, **no gold** → raw→agent only, no size bands) unchanged. Completeness is measured on
**placeholder-stripped** values on every side (:func:`engine.backfill.strip_placeholders`). The **cohort** is
the intersection of the agent master and the gold (samples in *both*) when a gold is supplied, else the whole
agent master.

Writes ``scorecard/<out-prefix>.{md,tsv}``. Read-only, no LLM.

    uv run python -m …evaluation.completeness_by_split --truth <v2 gold>          # klebsiella (gold)
    uv run python -m …evaluation.completeness_by_split --app m_abs --tags mabs_all # m_abs (goldless)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.run_full_metadata_agent import SYNTHETIC_STUDIES
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec
from bac_metadata.bac_agentic_metadata.evaluation import report_config as rc

SizeBand = tuple[str, int, "int | None"]


def _read_cols(path: Path, wanted: set[str], sep: str) -> pd.DataFrame:
    """Read only ``wanted`` columns from a (possibly huge) delimited table, ENA-``NA``-safe.

    Literal ``"NA"`` is preserved (``keep_default_na=False``) — placeholder stripping is applied later,
    uniformly. Missing columns are simply skipped.
    """
    header = pd.read_csv(path, sep=sep, nrows=0).columns.tolist()
    usecols = [c for c in header if c in wanted]
    return pd.read_csv(path, sep=sep, dtype=str, usecols=usecols, low_memory=False, keep_default_na=False)


def _read_gold(truth_path: Path, parsed_cols: list[str]) -> pd.DataFrame:
    """Read the sample key + the ``*_parsed`` gold columns from metadata_v2 (large TSV)."""
    header = pd.read_csv(truth_path, sep="\t", nrows=0).columns.tolist()
    key = "sample_accession" if "sample_accession" in header else ("Sample" if "Sample" in header else None)
    if key is None:
        sys.exit(f"gold has no sample_accession/Sample column; header starts {header[:8]}")
    usecols = [key] + [c for c in parsed_cols if c in header]
    gold = pd.read_csv(truth_path, sep="\t", dtype=str, usecols=usecols, low_memory=False, keep_default_na=False)
    return gold.rename(columns={key: "sample_accession"})


def _assign_split(study: str, size: int, fold_map: dict[str, str], size_bands: list[SizeBand]) -> str:
    """Map a study to its scorecard split (synthetic → fold → size band, in that precedence)."""
    if study in SYNTHETIC_STUDIES:
        return study
    if study in fold_map:
        return fold_map[study]
    for label, lo, hi in size_bands:
        if size >= lo and (hi is None or size <= hi):
            return label
    return size_bands[-1][0] if size_bands else "uncovered"


def _present(series: pd.Series) -> pd.Series:
    """Boolean 'carries a real value' after placeholder stripping."""
    return backfill.strip_placeholders(series).notna()


def build_scorecard(
    master_path: Path,
    base_path: Path,
    splits_path: Path,
    *,
    fields: tuple[str, ...],
    size_bands: list[SizeBand],
    fold_splits: tuple[str, ...],
    synthetic_collections: tuple[str, ...],
    truth_path: Path | None = None,
) -> pd.DataFrame:
    """Compute the per-split raw/agent[/manual] completeness table.

    Cohort = master∩gold when ``truth_path`` is given, else the whole agent master. Columns: ``split``, ``n``
    and, per field, ``{field}_raw`` / ``{field}_agent`` — plus ``{field}_manual`` / ``{field}_diff`` when a gold
    is supplied (``diff`` = agent − manual pp, from the 1-dp displayed values). ``TOTAL_excl_Refseq`` is emitted
    only when ``Refseq_collection`` is a declared synthetic collection.
    """
    key_cols = {"sample_accession", "study_accession", *fields}
    base = _read_cols(base_path, key_cols, sep=",").drop_duplicates("sample_accession").set_index("sample_accession")
    master = _read_cols(master_path, key_cols, sep="\t").drop_duplicates("sample_accession").set_index("sample_accession")
    gold = None
    gold_fields: list[str] = []
    if truth_path is not None:
        gold = _read_gold(truth_path, [f"{f}_parsed" for f in fields]).drop_duplicates(
            "sample_accession").set_index("sample_accession")
        gold_fields = [f for f in fields if f"{f}_parsed" in gold.columns]

    sizes = base.groupby("study_accession").size()
    fold_map = pd.read_csv(splits_path, sep="\t", dtype=str).set_index("study_accession")["fold"].to_dict()

    cohort = master.index.intersection(gold.index) if gold is not None else master.index
    print(f"cohort ({'master∩gold' if gold is not None else 'master'}) = {len(cohort)}; base={len(base)} "
          f"master={len(master)}" + (f" gold={len(gold)}" if gold is not None else ""), file=sys.stderr)
    base_c, master_c = base.reindex(cohort), master.reindex(cohort)
    gold_c = gold.reindex(cohort) if gold is not None else None

    study = base_c["study_accession"].fillna(master_c["study_accession"])
    size = study.map(sizes).fillna(0).astype(int)
    split = pd.Series([_assign_split(s, z, fold_map, size_bands) for s, z in zip(study, size, strict=True)],
                      index=cohort, name="split")

    frame = pd.DataFrame({"split": split})
    for f in fields:
        frame[f"{f}_raw"] = _present(base_c[f]).to_numpy()
        frame[f"{f}_agent"] = _present(master_c[f]).to_numpy()
        if f in gold_fields:
            frame[f"{f}_manual"] = _present(gold_c[f"{f}_parsed"]).to_numpy()

    def _summarise(sub: pd.DataFrame) -> dict:
        row = {"n": int(len(sub))}
        for f in fields:
            raw = round(100 * float(sub[f"{f}_raw"].mean()), 1)
            agent = round(100 * float(sub[f"{f}_agent"].mean()), 1)
            row[f"{f}_raw"], row[f"{f}_agent"] = raw, agent
            if f in gold_fields:
                manual = round(100 * float(sub[f"{f}_manual"].mean()), 1)
                row[f"{f}_manual"] = manual
                row[f"{f}_diff"] = round(agent - manual, 1)
        return row

    split_order = (*fold_splits, *[b[0] for b in size_bands], *synthetic_collections)
    rows = {}
    for sp in split_order:
        sub = frame[frame["split"] == sp]
        if len(sub):
            rows[sp] = _summarise(sub)
    rows["TOTAL"] = _summarise(frame)
    if "Refseq_collection" in synthetic_collections:
        rows["TOTAL_excl_Refseq"] = _summarise(frame[frame["split"] != "Refseq_collection"])
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.index.name = "split"
    return out.reset_index()


def _fmt_pp(x: float) -> str:
    """Signed percentage-point string (+3.5 / -0.6 / +0.0)."""
    return f"+{x:.1f}" if x >= 0 else f"{x:.1f}"


def _render_md(sc: pd.DataFrame, master_path: Path, truth_path: Path | None, *, spec: AttributeSpec) -> str:
    """Render the scorecard to markdown — full agent-vs-gold layout when a gold is present, else raw→agent."""
    display = rc.display_fields(spec)
    species = rc.species_label(spec)
    gold = truth_path is not None and f"{display[0]}_diff" in sc.columns
    total = sc[sc["split"] == "TOTAL"].iloc[0]
    excl_row = sc[sc["split"] == "TOTAL_excl_Refseq"]
    excl = excl_row.iloc[0] if len(excl_row) else total

    if gold:
        title = spec.report.get("completeness_title") or f"{species} agentic curation — completeness by split (agent vs manual gold)"
        lines = [
            f"# {title}", "",
            f"Auto-generated by `evaluation/completeness_by_split.py`. Cohort = the **{int(total['n']):,}** "
            "samples present in *both* the agent master and the manual gold (`*_parsed`). Blank = the null-like "
            "token set (`engine.backfill.PLACEHOLDER_NULLS`) applied uniformly to raw / gold / agent.",
            "", "## Headline", "",
            "- Excluding the out-of-scope `Refseq_collection`, the agent's completeness minus manual is "
            + ", ".join(f"{f} {_fmt_pp(excl[f'{f}_diff'])}" for f in display) + " percentage points.",
            f"- Pooled over all {int(total['n']):,} samples (incl. Refseq): "
            + ", ".join(f"{f} {_fmt_pp(total[f'{f}_diff'])}" for f in display) + ".",
            "", "## Agent − manual by split (percentage points, per field)", "",
            "| split | n | " + " | ".join(display) + " |", "|---|--:|" + "--:|" * len(display),
        ]
        for _, r in sc.iterrows():
            lines.append(f"| {r['split']} | {int(r['n']):,} | "
                         + " | ".join(_fmt_pp(r[f"{f}_diff"]) for f in display) + " |")
        lines += ["", "Positive = agent more complete than manual. The tail bands (manual never curated them) "
                  "are where the agent adds most; `Refseq_collection` (empty in the ENA base, skipped by design, "
                  "manually enriched from NCBI) drags the naive pool.", ""]
        for f in display:
            lines += [f"## {f}: raw → manual → agent, by split", "",
                      "| split | n | raw ENA % | manual gold % | agent % | agent − manual |",
                      "|---|--:|--:|--:|--:|--:|"]
            for _, r in sc.iterrows():
                lines.append(f"| {r['split']} | {int(r['n']):,} | {r[f'{f}_raw']:.1f} | {r[f'{f}_manual']:.1f} | "
                             f"{r[f'{f}_agent']:.1f} | {_fmt_pp(r[f'{f}_diff'])} |")
            lines.append("")
        refseq = sc[sc["split"] == "Refseq_collection"]
        if len(refseq):
            r = refseq.iloc[0]
            raws = " / ".join(f"{r[f'{f}_raw']:.0f}%" for f in display)
            numword = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}
            nfields = numword.get(len(display), str(len(display)))
            lines += [
                "## The `Refseq_collection` carve-out (why the naive pool is a draw)", "",
                f"`Refseq_collection` = **{int(r['n']):,}** RefSeq (GCF) reference genomes. In the ENA base table "
                f"their {nfields} fields are **empty** (raw {raws}) because the base is built from ENA *reads* and these "
                "assemblies have none. Manual gold enriched them from NCBI; the agent skipped them by design "
                "(`SYNTHETIC_STUDIES`). They are already carried by manual values in the merged deliverable, so "
                "this is a **benchmark-scope** issue, not a data gap → resolved by the planned NCBI base-table "
                "enrichment (see plan Phase 6).", "",
            ]
    else:  # goldless — raw → agent only (no manual column)
        title = spec.report.get("completeness_title_goldless") or f"{species} agentic curation — completeness by split (raw → agent)"
        lines = [
            f"# {title}", "",
            f"Auto-generated by `evaluation/completeness_by_split.py`. No manual gold for this application → "
            f"raw ENA → agent only. Cohort = the **{int(total['n']):,}** samples in the agent master. Blank = the "
            "null-like token set (`engine.backfill.PLACEHOLDER_NULLS`) applied uniformly to raw / agent.",
            "", "## Headline (agent − raw, percentage points)", "",
            "- Pooled over the whole master: "
            + ", ".join(f"{f} {_fmt_pp(round(total[f'{f}_agent'] - total[f'{f}_raw'], 1))}" for f in display) + ".",
            "",
        ]
        for f in display:
            lines += [f"## {f}: raw → agent, by split", "",
                      "| split | n | raw ENA % | agent % | agent − raw |", "|---|--:|--:|--:|--:|"]
            for _, r in sc.iterrows():
                lines.append(f"| {r['split']} | {int(r['n']):,} | {r[f'{f}_raw']:.1f} | {r[f'{f}_agent']:.1f} | "
                             f"{_fmt_pp(round(r[f'{f}_agent'] - r[f'{f}_raw'], 1))} |")
            lines.append("")

    if gold:  # verbatim Klebsiella footer — keeps the Kp completeness report byte-identical on regeneration
        lines += [
            "## Related checks (not computed here)", "",
            "- **Accumulation integrity** — that every applied per-tag fill reaches the master "
            "(`after_c == master`) is proven by `python -m …engine.cli.accumulate … --canonical <gold>`, not "
            "this script.",
            "- **Orphan audit** — downloaded-but-unused papers/tables and recoverable-but-unwired project_k "
            "tables are surfaced by `evaluation/audit_manual_curation.py`.",
            "- **Outstanding manual-curation worklist** — papers/tables still to fetch are listed in "
            "`find_papers/manual_curation_worklist.{md,tsv}`; servicing them lifts the tail bands further.",
            "", "## Reproduce (pure pandas, no LLM)", "", "```bash",
            "uv run python -m bac_metadata.bac_agentic_metadata.evaluation.completeness_by_split \\",
            f"  --master {master_path} \\", f"  --truth '{truth_path}'", "```", "",
        ]
    else:
        lines += [
            "## Related checks (not computed here)", "",
            "- **Accumulation integrity** — that every applied per-tag fill reaches the master is proven by "
            "`python -m …engine.cli.accumulate …`, not this script.",
            "- **Orphan audit** — downloaded-but-unused papers/tables are surfaced by "
            "`evaluation/audit_manual_curation.py`.", "", "## Reproduce (pure pandas, no LLM)", "", "```bash",
            "uv run python -m bac_metadata.bac_agentic_metadata.evaluation.completeness_by_split \\",
            f"  --app {spec.application} \\", f"  --master {master_path}", "```", "",
        ]
    return "\n".join(lines)


def main() -> None:
    """Compute the per-split completeness scorecard and write ``scorecard/<out-prefix>.{md,tsv}``."""
    p = argparse.ArgumentParser(description="Per-split completeness scorecard (raw/agent[/manual]), app-agnostic.")
    p.add_argument("--app", default="klebsiella", help="Application slug (default: klebsiella).")
    p.add_argument("--spec", default=None, help="attributes.yaml (default: applications/<app>/attributes.yaml).")
    p.add_argument("--data-dir", default=None, help="Application data dir (default: applications/<app>/data).")
    p.add_argument("--master", default=None, help="Agent master TSV (default: <data-dir>/curated/metadata_curated_master.tsv).")
    p.add_argument("--base", default=None, help="Raw ENA base table CSV (default: <data-dir>/inputs/base_table.csv).")
    p.add_argument("--splits", default=None, help="project_splits.tsv (default: <data-dir>/fold_splits/project_splits.tsv).")
    p.add_argument("--truth", default=None, help="metadata_v2 gold TSV (optional; omit for a goldless app).")
    p.add_argument("--out-prefix", default="final_completeness_raw_agent_gold", help="Report basename under scorecard/.")
    args = p.parse_args()

    here = Path(__file__).resolve().parent.parent
    app_dir = here / "applications" / args.app
    data_dir = Path(args.data_dir) if args.data_dir else app_dir / "data"
    spec = AttributeSpec.from_yaml(args.spec if args.spec else app_dir / "attributes.yaml")
    master_path = Path(args.master) if args.master else data_dir / "curated" / "metadata_curated_master.tsv"
    base_path = Path(args.base) if args.base else data_dir / "inputs" / "base_table.csv"
    splits_path = Path(args.splits) if args.splits else data_dir / "fold_splits" / "project_splits.tsv"
    truth_path = Path(args.truth) if args.truth else None

    sc = build_scorecard(
        master_path, base_path, splits_path,
        fields=rc.fields(spec), size_bands=rc.size_bands(spec), fold_splits=rc.fold_splits(spec),
        synthetic_collections=rc.synthetic_collections(spec), truth_path=truth_path,
    )

    scorecard_dir = data_dir / "scorecard"
    scorecard_dir.mkdir(parents=True, exist_ok=True)
    (scorecard_dir / f"{args.out_prefix}.md").write_text(_render_md(sc, master_path, truth_path, spec=spec))
    sc.to_csv(scorecard_dir / f"{args.out_prefix}.tsv", sep="\t", index=False)
    print(f"Wrote scorecard/{args.out_prefix}.{{md,tsv}}", file=sys.stderr)
    diff_cols = [f"{f}_diff" for f in rc.display_fields(spec) if f"{f}_diff" in sc.columns]
    cols = ["split", "n", *(diff_cols or [f"{f}_agent" for f in rc.display_fields(spec)])]
    print(sc[cols].to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
