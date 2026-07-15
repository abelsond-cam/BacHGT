r"""Curator CLI — rebuild a tag's final ``filled_metadata_<tag>.tsv`` from the current applied files.

Species-agnostic. The driver rebuilds the final table as its stage 8 on every pass, so the pipeline is always
self-consistent end-to-end. This CLI is the standalone equivalent: after a curator applies answers out-of-band
(``escalate --apply``) or edits any applied file, run this to fold those changes into the production output.
It is the permanent "the final table is one step behind — rebuild it" command, and the thing that makes the
escalation-conservation gate's link-5 invariant satisfiable without a full driver re-run.

It reproduces the driver's fill inputs exactly: selects the tag's FULL study universe (``--fold`` splits or
``--min/max-study-size`` band, the same two modes the driver has), restricts the full-width base to it,
applies the same in-memory preclean (field-specific null tokens blanked so a base null can't survive as the
final value), then calls :func:`engine.stages.fill_for_tag`. A subset selection would silently shrink the
final table, so the universe must match the original run's.

    uv run python -m bac_metadata.bac_agentic_metadata.engine.cli.fill \\
        --data-dir .../applications/klebsiella/data \\
        --spec .../applications/klebsiella/attributes.yaml --tag train --fold train,val \\
        --table .../klebsiella/data/inputs/base_table.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import stages
from bac_metadata.bac_agentic_metadata.engine.categorise.preclean import preclean_base
from bac_metadata.bac_agentic_metadata.engine.run_full_metadata_agent import (
    _curated_studies,
    _select_size_band,
    _study_sizes,
)
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec


def main() -> None:
    """Rebuild ``filled_metadata_<tag>.tsv`` from the tag's current applied files (any application)."""
    p = argparse.ArgumentParser(description="Rebuild a tag's final filled metadata table (any application).")
    p.add_argument("--data-dir", required=True, help="Application data tree root.")
    p.add_argument("--spec", required=True, help="Application attributes.yaml (source of the completeness fields).")
    p.add_argument("--table", required=True, help="Full-width per-sample base table CSV/TSV.")
    p.add_argument("--tag", required=True, help="Run tag — selects the applied files and names filled_metadata_<tag>.tsv.")
    # Selection mode — exactly one, mirroring the driver:
    p.add_argument("--fold", default=None, help="Splits mode: comma-separated fold(s) the tag covers (e.g. 'train,val').")
    p.add_argument("--min-study-size", type=int, default=None, help="Band mode: minimum study size (samples).")
    p.add_argument("--max-study-size", type=int, default=None, help="Band mode: maximum study size (samples).")
    p.add_argument("--splits", default=None,
                   help="(--fold) split TSV (default <data-dir>/fold_splits/project_splits.tsv).")
    p.add_argument("--exclude-splits", default=None,
                   help="(band mode) curated-splits TSV whose studies are excluded (default project_splits.tsv).")
    args = p.parse_args()

    size_mode = args.min_study_size is not None or args.max_study_size is not None
    splits_mode = args.fold is not None
    if size_mode == splits_mode:
        sys.exit("Choose exactly one selection mode: --min-study-size/--max-study-size OR --fold.")

    data = Path(args.data_dir).resolve()
    spec = AttributeSpec.from_yaml(args.spec)
    fields = list(spec.completeness_fields)

    sizes = _study_sizes(Path(args.table))
    if size_mode:
        exclude_path = Path(args.exclude_splits) if args.exclude_splits else data / "fold_splits" / "project_splits.tsv"
        selected = _select_size_band(sizes, lo=args.min_study_size or 0, hi=args.max_study_size,
                                     exclude=_curated_studies(exclude_path), limit=None)
        fold = args.tag
    else:
        splits_path = Path(args.splits).resolve() if args.splits else data / "fold_splits" / "project_splits.tsv"
        sel = pd.read_csv(splits_path, sep="\t", dtype=str)
        selected = list(sel[sel["fold"].isin(set(args.fold.split(",")))]["study_accession"])
        fold = args.fold
    if not selected:
        sys.exit("No studies selected — nothing to fill.")

    base_full = pd.read_csv(args.table, dtype=str, low_memory=False, keep_default_na=False)
    if "study_accession" not in base_full.columns or "sample_accession" not in base_full.columns:
        sys.exit(f"--table needs study_accession + sample_accession; got {list(base_full.columns)[:12]}")
    base = base_full[base_full["study_accession"].isin(set(selected))].copy()
    # Match the driver's in-memory preclean so the rebuilt final table is byte-identical to a driver pass:
    # a base null token blanked in-memory there must be blanked here too, else it would survive as the value.
    base, precleaned = preclean_base(base, spec)
    if precleaned:
        print(f"[preclean] blanked null tokens: {{ {', '.join(f'{f}: {sum(v.values())}' for f, v in precleaned.items())} }}",
              file=sys.stderr)
    print(f"Rebuilding filled_metadata_{args.tag}.tsv over {len(selected)} studies / {len(base)} samples "
          f"(fold_label={fold!r})", file=sys.stderr)
    stages.fill_for_tag(data_dir=data, spec=spec, base=base, fields=fields, tag=args.tag, fold_label=fold)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
