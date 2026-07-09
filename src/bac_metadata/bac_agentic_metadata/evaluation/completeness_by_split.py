"""Per-split completeness scorecard: raw ENA vs agent master vs manual gold (Klebsiella).

Formalises the previously ad-hoc ``scorecard/final_completeness_raw_agent_gold.md`` so the
agent-vs-manual picture is reproducible from committed helpers (no ``.py`` emitted it before). For
each split and each of the four per-sample clinical fields it reports the fraction of samples that
carry a real value in:

* **raw**    — the ENA base table as deposited (``inputs/base_table.csv``);
* **agent**  — the accumulated agent master (``curated/metadata_curated_master.tsv``);
* **manual** — the curated gold ``*_parsed`` columns (metadata_v2).

Completeness is measured on **placeholder-stripped** values on every side (see
:func:`engine.backfill.strip_placeholders`) so ``"not available"`` / ``"missing"`` / … count as
absent. The **cohort** is the intersection of the agent master and the gold table (samples present in
*both*), matching the committed scorecard (87,293 for Klebsiella).

Split membership (precedence): a study in a curated fold → that fold (``train``/``test``/``val``); a
synthetic collection (:data:`SYNTHETIC_STUDIES`) → its own row (``Refseq_collection`` /
``NCTC_collection``); otherwise a **size band** keyed on the study's distinct-sample count in the base
table (``>=100`` → ``tail100``; ``50–99``; ``25–49``; ``10–24``; ``<10`` → ``other_uncovered``). The
size band mirrors the driver's tail selection (:func:`engine.run_full_metadata_agent._study_sizes`), so
unprocessed splits (``other_uncovered`` / synthetic) naturally show ``agent == raw``.

Writes ``scorecard/<out-prefix>.md`` + ``.tsv``. Read-only, no LLM. Re-run unchanged after a pipeline
fix to measure the dial move against a fixed baseline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill
from bac_metadata.bac_agentic_metadata.engine.run_full_metadata_agent import SYNTHETIC_STUDIES

APP_DIR = Path(__file__).resolve().parents[1] / "applications" / "klebsiella"  # gold-bearing app tree
DATA_DIR = APP_DIR / "data"
FIELDS = backfill.FIELDS  # (country, collection_date, isolation_source, host)
#: Report display order for the four fields (matches the committed scorecard's columns).
DISPLAY_FIELDS = ("host", "country", "collection_date", "isolation_source")
#: Uncurated-tail size bands: (label, lo, hi); ``hi=None`` = open-ended. Order = biggest-first.
SIZE_BANDS: tuple[tuple[str, int, int | None], ...] = (
    ("tail100", 100, None), ("tail50_99", 50, 99), ("tail25_49", 25, 49),
    ("tail10_24", 10, 24), ("other_uncovered(<10)", 1, 9),
)
FOLD_SPLITS = ("train", "test", "val")
#: Full split order for the report (folds → size bands → synthetic collections).
SPLIT_ORDER = (*FOLD_SPLITS, *[b[0] for b in SIZE_BANDS], "NCTC_collection", "Refseq_collection")


def _read_cols(path: Path, wanted: set[str], sep: str) -> pd.DataFrame:
    """Read only ``wanted`` columns from a (possibly huge) delimited table, ENA-``NA``-safe.

    Parameters
    ----------
    path
        CSV/TSV path.
    wanted
        Column names to keep (others skipped for memory).
    sep
        Field separator (comma for the base-table CSV, tab for the TSVs).

    Returns
    -------
    pandas.DataFrame
        String-typed frame with the available subset of ``wanted``; literal ``"NA"`` preserved
        (``keep_default_na=False``) — placeholder stripping is applied later, uniformly.
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


def _assign_split(study: str, size: int, fold_map: dict[str, str]) -> str:
    """Map a study to its scorecard split (synthetic → fold → size band, in that precedence)."""
    if study in SYNTHETIC_STUDIES:
        return study
    if study in fold_map:
        return fold_map[study]
    for label, lo, hi in SIZE_BANDS:
        if size >= lo and (hi is None or size <= hi):
            return label
    return "other_uncovered(<10)"


def _present(series: pd.Series) -> pd.Series:
    """Boolean 'carries a real value' after placeholder stripping."""
    return backfill.strip_placeholders(series).notna()


def build_scorecard(master_path: Path, base_path: Path, truth_path: Path, splits_path: Path) -> pd.DataFrame:
    """Compute the per-split raw/agent/manual completeness table over the master∩gold cohort.

    Returns
    -------
    pandas.DataFrame
        One row per split (plus ``TOTAL`` and ``TOTAL_excl_Refseq``), columns ``n`` and, per field,
        ``{field}_raw`` / ``{field}_manual`` / ``{field}_agent`` / ``{field}_diff`` (percentages;
        ``diff`` = agent − manual in percentage points, computed from the displayed 1-dp values).
    """
    key_cols = {"sample_accession", "study_accession", *FIELDS}
    base = _read_cols(base_path, key_cols, sep=",").drop_duplicates("sample_accession").set_index("sample_accession")
    master = _read_cols(master_path, key_cols, sep="\t").drop_duplicates("sample_accession").set_index("sample_accession")
    parsed_cols = [f"{f}_parsed" for f in FIELDS]
    gold = _read_gold(truth_path, parsed_cols).drop_duplicates("sample_accession").set_index("sample_accession")

    # study size = distinct-sample count in the FULL base table (mirrors the driver's tail selection)
    sizes = base.groupby("study_accession").size()
    fold_map = (
        pd.read_csv(splits_path, sep="\t", dtype=str).set_index("study_accession")["fold"].to_dict()
    )

    cohort = master.index.intersection(gold.index)
    print(f"cohort (master∩gold) = {len(cohort)}; base={len(base)} master={len(master)} gold={len(gold)}",
          file=sys.stderr)
    base_c, master_c, gold_c = base.reindex(cohort), master.reindex(cohort), gold.reindex(cohort)

    study = base_c["study_accession"].fillna(master_c["study_accession"])
    size = study.map(sizes).fillna(0).astype(int)
    split = pd.Series([_assign_split(s, z, fold_map) for s, z in zip(study, size, strict=True)],
                      index=cohort, name="split")

    frame = pd.DataFrame({"split": split})
    for f in FIELDS:
        frame[f"{f}_raw"] = _present(base_c[f]).to_numpy()
        frame[f"{f}_agent"] = _present(master_c[f]).to_numpy()
        frame[f"{f}_manual"] = _present(gold_c[f"{f}_parsed"]).to_numpy()

    def _summarise(sub: pd.DataFrame) -> dict:
        row = {"n": int(len(sub))}
        for f in FIELDS:
            raw = round(100 * float(sub[f"{f}_raw"].mean()), 1)
            agent = round(100 * float(sub[f"{f}_agent"].mean()), 1)
            manual = round(100 * float(sub[f"{f}_manual"].mean()), 1)
            row[f"{f}_raw"], row[f"{f}_agent"], row[f"{f}_manual"] = raw, agent, manual
            row[f"{f}_diff"] = round(agent - manual, 1)
        return row

    rows = {}
    for sp in SPLIT_ORDER:
        sub = frame[frame["split"] == sp]
        if len(sub):
            rows[sp] = _summarise(sub)
    rows["TOTAL"] = _summarise(frame)
    rows["TOTAL_excl_Refseq"] = _summarise(frame[frame["split"] != "Refseq_collection"])
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.index.name = "split"
    return out.reset_index()


def _fmt_pp(x: float) -> str:
    """Signed percentage-point string (+3.5 / -0.6 / +0.0)."""
    return f"+{x:.1f}" if x >= 0 else f"{x:.1f}"


def _render_md(sc: pd.DataFrame, master_path: Path, truth_path: Path) -> str:
    """Render the scorecard DataFrame to the committed markdown layout."""
    total = sc[sc["split"] == "TOTAL"].iloc[0]
    excl = sc[sc["split"] == "TOTAL_excl_Refseq"].iloc[0]
    lines = [
        "# Klebsiella agentic curation — completeness by split (agent vs manual gold)",
        "",
        f"Auto-generated by `evaluation/completeness_by_split.py`. Cohort = the **{int(total['n']):,}** samples "
        "present in *both* the agent master and the manual gold (`*_parsed`). Blank = the null-like token set "
        "(`engine.backfill.PLACEHOLDER_NULLS`) applied uniformly to raw / gold / agent.",
        "",
        "## Headline",
        "",
        f"- Excluding the out-of-scope `Refseq_collection`, the agent's completeness minus manual is "
        f"host {_fmt_pp(excl['host_diff'])}, country {_fmt_pp(excl['country_diff'])}, "
        f"collection_date {_fmt_pp(excl['collection_date_diff'])}, "
        f"isolation_source {_fmt_pp(excl['isolation_source_diff'])} percentage points.",
        f"- Pooled over all {int(total['n']):,} samples (incl. Refseq): host {_fmt_pp(total['host_diff'])}, "
        f"country {_fmt_pp(total['country_diff'])}, collection_date {_fmt_pp(total['collection_date_diff'])}, "
        f"isolation_source {_fmt_pp(total['isolation_source_diff'])}.",
        "",
        "## Agent − manual by split (percentage points, per field)",
        "",
        "| split | n | host | country | collection_date | isolation_source |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for _, r in sc.iterrows():
        lines.append(
            f"| {r['split']} | {int(r['n']):,} | {_fmt_pp(r['host_diff'])} | {_fmt_pp(r['country_diff'])} | "
            f"{_fmt_pp(r['collection_date_diff'])} | {_fmt_pp(r['isolation_source_diff'])} |"
        )
    lines += ["", "Positive = agent more complete than manual. The tail bands (manual never curated them) are "
              "where the agent adds most; `Refseq_collection` (empty in the ENA base, skipped by design, manually "
              "enriched from NCBI) drags the naive pool.", ""]

    for f in DISPLAY_FIELDS:
        lines += [f"## {f}: raw → manual → agent, by split", "",
                  "| split | n | raw ENA % | manual gold % | agent % | agent − manual |",
                  "|---|--:|--:|--:|--:|--:|"]
        for _, r in sc.iterrows():
            lines.append(
                f"| {r['split']} | {int(r['n']):,} | {r[f'{f}_raw']:.1f} | {r[f'{f}_manual']:.1f} | "
                f"{r[f'{f}_agent']:.1f} | {_fmt_pp(r[f'{f}_diff'])} |"
            )
        lines.append("")

    refseq = sc[sc["split"] == "Refseq_collection"]
    if len(refseq):
        r = refseq.iloc[0]
        lines += [
            "## The `Refseq_collection` carve-out (why the naive pool is a draw)",
            "",
            f"`Refseq_collection` = **{int(r['n']):,}** RefSeq (GCF) reference genomes. In the ENA base table "
            f"their four fields are **empty** (raw {r['host_raw']:.0f}% / {r['country_raw']:.0f}% / "
            f"{r['collection_date_raw']:.0f}% / {r['isolation_source_raw']:.0f}%) because the base is built from "
            "ENA *reads* and these assemblies have none. Manual gold enriched them from NCBI; the agent skipped "
            "them by design (`SYNTHETIC_STUDIES`). They are already carried by manual values in the merged "
            "deliverable, so this is a **benchmark-scope** issue, not a data gap → resolved by the planned NCBI "
            "base-table enrichment (see plan Phase 6).",
            "",
        ]
    lines += [
        "## Related checks (not computed here)",
        "",
        "- **Accumulation integrity** — that every applied per-tag fill reaches the master "
        "(`after_c == master`) is proven by `python -m …engine.cli.accumulate … --canonical <gold>`, not this "
        "script.",
        "- **Orphan audit** — downloaded-but-unused papers/tables and recoverable-but-unwired project_k tables "
        "are surfaced by `evaluation/audit_manual_curation.py`.",
        "- **Outstanding manual-curation worklist** — papers/tables still to fetch are listed in "
        "`find_papers/manual_curation_worklist.{md,tsv}`; servicing them lifts the tail bands further.",
        "",
        "## Reproduce (pure pandas, no LLM)",
        "",
        "```bash",
        "uv run python -m bac_metadata.bac_agentic_metadata.evaluation.completeness_by_split \\",
        f"  --master {master_path} \\",
        f"  --truth '{truth_path}'",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    """Compute the per-split completeness scorecard and write ``scorecard/<out-prefix>.{md,tsv}``."""
    p = argparse.ArgumentParser(description="Per-split completeness scorecard (raw/agent/manual), Klebsiella.")
    p.add_argument("--data-dir", default=str(DATA_DIR), help="Application data dir (default: klebsiella).")
    p.add_argument("--master", default=None, help="Agent master TSV (default: <data-dir>/curated/metadata_curated_master.tsv).")
    p.add_argument("--base", default=None, help="Raw ENA base table CSV (default: <data-dir>/inputs/base_table.csv).")
    p.add_argument("--splits", default=None, help="project_splits.tsv (default: <data-dir>/fold_splits/project_splits.tsv).")
    p.add_argument("--truth", required=True, help="metadata_v2 gold TSV (local path).")
    p.add_argument("--out-prefix", default="final_completeness_raw_agent_gold", help="Report basename under scorecard/.")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    master_path = Path(args.master) if args.master else data_dir / "curated" / "metadata_curated_master.tsv"
    base_path = Path(args.base) if args.base else data_dir / "inputs" / "base_table.csv"
    splits_path = Path(args.splits) if args.splits else data_dir / "fold_splits" / "project_splits.tsv"
    truth_path = Path(args.truth)

    sc = build_scorecard(master_path, base_path, truth_path, splits_path)

    scorecard_dir = data_dir / "scorecard"
    scorecard_dir.mkdir(parents=True, exist_ok=True)
    (scorecard_dir / f"{args.out_prefix}.md").write_text(_render_md(sc, master_path, truth_path))
    sc.to_csv(scorecard_dir / f"{args.out_prefix}.tsv", sep="\t", index=False)
    print(f"Wrote scorecard/{args.out_prefix}.{{md,tsv}}", file=sys.stderr)
    cols = ["split", "n", *[f"{f}_diff" for f in DISPLAY_FIELDS]]
    print(sc[cols].to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
