"""Per-sample backfill runner (Klebsiella) — steps 1-2: gate (<75%) then whole-field fill.

Reads the **raw, uncurated ENA per-sample table** (what ``metadata_collation.load_collated_metadata``
pulls in — pre-QC, pre-curation, before the ``ready_to_merge`` backfill), gates each field where ENA is
already >= the threshold complete, and fills the genuinely-blank cells of the remaining fields with the
grader's whole-field proposal. Writes a per-sample **changes file** (proposed fills + provenance) and a
**gate report** (which study x field are covered vs residual → the method-b backlog). RAW values only;
the only normalisation is the standalone placeholder->NA strip in ``engine.backfill``.

The gold-standard comparison (value-correctness vs ``metadata_v2``) is a separate step
(``validate_backfill_values.py``); this runner never touches ``metadata_v2``.

Examples
--------
unset VIRTUAL_ENV
uv run python .../run_backfill.py --fold train,val            # raw ENA via load_collated_metadata
uv run python .../run_backfill.py --input raw_ena.tsv --fold train,val
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPLIT_PATH = DATA_DIR / "kleb_project_splits.tsv"
AUX_COLUMNS = ("sample_accession", "run_accession", "instrument_platform", "scientific_name")


def _load_raw_ena(input_path: str | None) -> pd.DataFrame:
    """Return the raw per-sample ENA table — an explicit ``--input`` TSV, else ``load_collated_metadata``."""
    if input_path:
        return pd.read_csv(input_path, sep="\t", dtype=str, low_memory=False)
    from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource

    return KlebCollationSource(keep_columns=AUX_COLUMNS).states()["base"]


def _load_proposals(grades_path: Path) -> dict[str, dict[str, dict]]:
    """Build ``{study: {field: {value, whole_project, evidence}}}`` from the flat grades TSV."""
    g = pd.read_csv(grades_path, sep="\t", dtype=str).fillna("")
    proposals: dict[str, dict[str, dict]] = {}
    for _, r in g.iterrows():
        proposals[r["study_accession"]] = {
            f: {
                "value": r.get(f"backfill_{f}__value", ""),
                "whole_project": str(r.get(f"backfill_{f}__whole_project", "")).strip().lower() == "true",
                "evidence": "",  # evidence_quote lives in study_grades.jsonl, not the flat TSV
            }
            for f in backfill.FIELDS
        }
    return proposals


def main() -> None:
    """Parse arguments, gate by completeness, apply whole-field fills, write changes + gate report."""
    parser = argparse.ArgumentParser(description="Per-sample backfill (Klebsiella) — gate + whole-field fill.")
    parser.add_argument("--input", default=None, help="Explicit raw ENA per-sample TSV (else load_collated_metadata).")
    parser.add_argument("--grades", default=str(DATA_DIR / "study_grades.tsv"), help="Grader output with whole-field proposals.")
    parser.add_argument("--output", default=str(DATA_DIR / "backfill_applied.tsv"), help="Per-sample changes file.")
    parser.add_argument("--fold", default="train,val", help="Comma-separated folds (default train,val; test sealed).")
    parser.add_argument("--threshold", type=float, default=0.75, help="Skip a field already >= this complete in ENA.")
    args = parser.parse_args()

    base = _load_raw_ena(args.input)
    if "sample_accession" not in base.columns or "study_accession" not in base.columns:
        sys.exit(f"Raw ENA table needs sample_accession + study_accession columns; got {list(base.columns)[:12]}")

    split = pd.read_csv(SPLIT_PATH, sep="\t", dtype=str)[["study_accession", "fold"]]
    folds = {x.strip() for x in args.fold.split(",") if x.strip()}
    keep = set(split[split["fold"].isin(folds)]["study_accession"])
    base = base[base["study_accession"].isin(keep)].copy()
    print(f"Raw ENA rows in {sorted(folds)}: {len(base)} across {base['study_accession'].nunique()} studies", file=sys.stderr)

    completeness = backfill.field_completeness(base)
    needs = backfill.gate_fields(completeness, threshold=args.threshold)
    proposals = _load_proposals(Path(args.grades))
    applied = backfill.apply_whole_field(base, proposals, needs)
    applied.to_csv(args.output, sep="\t", index=False)

    # Gate report: every gated study x field, marked covered (a whole-field value was applied) or
    # residual (no whole-field value → the method-b per-sample backlog).
    covered = {(f, s) for f, s in zip(applied["field"], applied["study_accession"], strict=False)}
    filled_counts = applied.groupby(["field", "study_accession"]).size().to_dict()
    rows = []
    for f in backfill.FIELDS:
        for acc, gated in needs[f].items():
            if not bool(gated):
                continue
            frac = completeness.loc[acc, f]
            n = int(completeness.loc[acc, "n_records"])
            rows.append({
                "field": f, "study_accession": acc, "n_records": n,
                "completeness": round(float(frac), 3) if pd.notna(frac) else "",
                "n_blank": int(round(n * (1 - (frac if pd.notna(frac) else 0.0)))),
                "status": "covered" if (f, acc) in covered else "residual_method_b",
                "n_filled": int(filled_counts.get((f, acc), 0)),
            })
    gate = pd.DataFrame(rows)
    gate_path = Path(args.output).with_name("backfill_gate_report.tsv")
    gate.sort_values(["field", "status", "study_accession"]).to_csv(gate_path, sep="\t", index=False)

    print(f"Wrote {args.output} ({len(applied)} per-sample fills) and {gate_path.name}", file=sys.stderr)
    if len(gate):
        summ = gate.groupby(["field", "status"]).size().unstack(fill_value=0)
        print("\nGated study×field (per field) — covered by whole-field vs residual (method-b backlog):", file=sys.stderr)
        print(summ.to_string(), file=sys.stderr)
        print(f"\nTotal per-sample fills by field:\n{applied['field'].value_counts().to_string()}", file=sys.stderr)


if __name__ == "__main__":
    main()
