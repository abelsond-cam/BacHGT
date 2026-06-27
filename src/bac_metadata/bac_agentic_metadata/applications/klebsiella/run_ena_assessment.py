"""ENA assessment runner for the Klebsiella application — deterministic ingestion & completeness.

Two modes:

* ``--mode sizing-only`` (local-friendly) — fetch ENA project record counts (total +
  taxon-of-interest) for every accession in the split and write ``data/stage1_sizing.tsv``.
  Needs only the ENA Portal; used for the calibration check against ``isolates_in_study``.
* ``--mode full`` (HPC) — also build the base/post-merge completeness tables via the existing
  collation pipeline and write the full ``data/stage1_ingest.tsv``.

Run with ``uv run`` (after ``unset VIRTUAL_ENV``). The ENA cache makes reruns deterministic.

Examples
--------
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_ena_assessment.py --mode sizing-only
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_ena_assessment.py --mode full
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.ena_sizing import study_record_counts
from bac_metadata.bac_agentic_metadata.engine.ingest import build_ena_assessment_table
from bac_metadata.bac_agentic_metadata.engine.sources import KlebCollationSource
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SPEC_PATH = APP_DIR / "attributes.yaml"
SPLIT_PATH = DATA_DIR / "fold_splits" / "project_splits.tsv"
DEFAULT_CACHE = DATA_DIR / "cache" / "ena"


def _fetch_sizing(accessions: list[str], match: tuple[str, ...], cache_dir: Path) -> dict[str, dict]:
    """Fetch ENA sizing for each accession (cached), printing progress to stderr."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict] = {}
    for i, acc in enumerate(accessions, start=1):
        print(f"[sizing {i}/{len(accessions)}] {acc}", file=sys.stderr)
        records[acc] = study_record_counts(acc, match, cache_dir=cache_dir)
    return records


def main() -> None:
    """Parse arguments and run the requested ENA assessment mode."""
    parser = argparse.ArgumentParser(description="ENA assessment ingestion & completeness (Klebsiella).")
    parser.add_argument("--mode", choices=["sizing-only", "full"], default="full")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N accessions.")
    parser.add_argument("--output", type=Path, default=None, help="Override the output TSV path.")
    parser.add_argument("--metadata-file1", default=None, help="Local override for base ATB ENA TSV 1 (full mode).")
    parser.add_argument("--metadata-file2", default=None, help="Local override for base ATB ENA TSV 2 (full mode).")
    parser.add_argument("--metadata-file3", default=None, help="Local override for base ATB ENA TSV 3 (full mode).")
    parser.add_argument("--qc-excel", default=None, help="Local override for the QC Excel (RefSeq sheet).")
    parser.add_argument("--ena-project-dir", default=None, help="Local override for the ready_to_merge project dir.")
    parser.add_argument(
        "--study-metadata-file",
        default=str(DATA_DIR / "inputs" / "study_level_metadata_all_combined_v1.0_20260105.csv"),
        help="Local study_level CSV for the reviewed flag (keeps collation offline; default: frozen snapshot).",
    )
    args = parser.parse_args()

    spec = AttributeSpec.from_yaml(SPEC_PATH)
    match = spec.taxon_of_interest.scientific_name_match

    split = pd.read_csv(SPLIT_PATH, sep="\t")
    if args.limit is not None:
        split = split.head(args.limit)
    accessions = split["study_accession"].tolist()
    print(f"Loaded {len(accessions)} accessions from {SPLIT_PATH.name}", file=sys.stderr)

    sizing = _fetch_sizing(accessions, match, args.cache_dir)

    if args.mode == "sizing-only":
        out = args.output or DATA_DIR / "ena_assessment" / "ena_sizing.tsv"
        table = split.copy()
        table["ena_total_samples"] = [sizing[a]["ena_total_samples"] for a in accessions]
        table["ena_total_runs"] = [sizing[a]["ena_total_runs"] for a in accessions]
        table["ena_taxon_samples"] = [sizing[a]["ena_taxon_samples"] for a in accessions]
        table["n_child_studies"] = [sizing[a]["n_child_studies"] for a in accessions]
        table["umbrella_suspected"] = [sizing[a]["umbrella_suspected"] for a in accessions]
        table["by_scientific_name"] = [json.dumps(sizing[a]["by_scientific_name"]) for a in accessions]
        table["fetch_status"] = [sizing[a]["fetch_status"] for a in accessions]
        table.to_csv(out, sep="\t", index=False)
        print(f"Wrote {out} ({len(table)} rows)", file=sys.stderr)
        return

    print("Building base + post-merge completeness tables (collation pipeline)...", file=sys.stderr)
    states = KlebCollationSource(
        metadata_file1=args.metadata_file1,
        metadata_file2=args.metadata_file2,
        metadata_file3=args.metadata_file3,
        qc_excel_path=args.qc_excel,
        ena_project_dir=args.ena_project_dir,
        study_metadata_file=args.study_metadata_file,
    ).states()
    # Inject the Klebsiella value-parsers the engine's normalise step is now agnostic to (the engine
    # no-ops without them). names[0] is the field's parse_* (the parser that adds the `*_parsed` column).
    from bac_metadata.pp import metadata_curation as mc
    normalisers = {
        field: functools.partial(getattr(mc, names[0]), verbose=False)
        for field, names in spec.deterministic_normaliser.items()
        if names
    }
    table = build_ena_assessment_table(split, spec, states, sizing, normalisers=normalisers)
    out = args.output or DATA_DIR / "ena_assessment" / "ena_ingest.tsv"
    table.to_csv(out, sep="\t", index=False)
    print(f"Wrote {out} ({len(table)} rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
