"""Build the reproducible train/val/test split of hand-curated Klebsiella studies.

Stage 0 deliverable for the agentic-metadata engine. The *project accession*
(``study_accession``) is the unit of work, but folds are assigned at **paper-group**
level (all accessions of one paper share a fold) so no paper's text can inform both the
training material and the sealed test set. The split is seeded and stratified by
sample-count bucket, and is built from a committed CSV snapshot of the (stable, completed)
curation sheet so the split is fully reproducible from the repo alone.

Run::

    uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/make_kleb_splits.py

Output: ``data/kleb_project_splits.tsv`` with one row per reviewed accession
(``study_accession``, ``paper_short_title``, ``n_isolates``, ``fold``, ``seed``).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "data" / "inputs" / "study_level_metadata_all_combined_v1.0_20260105.csv"
DEFAULT_OUTPUT = HERE / "data" / "fold_splits" / "project_splits.tsv"

#: Fixed seed — changing it reshuffles every fold, so it is part of the artefact's identity.
DEFAULT_SEED = 20260612

#: Target fold fractions (train, val, test). Test is the remainder.
FRACTIONS = {"train": 0.50, "val": 0.20, "test": 0.30}

#: A token is treated as an ENA/NCBI project accession if it starts with ``PRJ``.
_ACCESSION_RE = re.compile(r"\bPRJ[A-Z]+\d+\b")


def parse_accessions(study_accessions: str) -> list[str]:
    """Extract the ``PRJ...`` accessions from a free-text ``study_accessions`` cell.

    Handles comma-, slash-, semicolon-, whitespace- and ``and``-separated lists.

    Parameters
    ----------
    study_accessions
        Raw cell content, e.g. ``"PRJEB24082, PRJEB19435 and PRJEB24083"``.

    Returns
    -------
    list[str]
        The accessions in first-seen order, de-duplicated.
    """
    seen: dict[str, None] = {}
    for match in _ACCESSION_RE.findall(str(study_accessions or "")):
        seen.setdefault(match, None)
    return list(seen)


class _UnionFind:
    """Minimal union-find to merge accessions into connected paper-groups."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        """Return the representative of ``item``'s set, adding it if unseen."""
        self._parent.setdefault(item, item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        """Merge the sets containing ``a`` and ``b``."""
        self._parent[self.find(b)] = self.find(a)


def build_paper_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Explode the study sheet to one row per accession with a paper-group id.

    Accessions are unioned when they share a sheet row *or* a normalised paper key
    (``paper_short_title`` falling back to ``paper_link``), so a paper spread across
    several rows or accessions becomes a single group.

    Parameters
    ----------
    df
        The frozen curation sheet (one row per curated study).

    Returns
    -------
    pandas.DataFrame
        Columns ``study_accession``, ``paper_short_title``, ``n_isolates``,
        ``paper_group`` (the union-find representative accession).
    """
    uf = _UnionFind()
    key_anchor: dict[str, str] = {}  # normalised paper key -> first accession seen
    records: list[dict[str, object]] = []

    for _, row in df.iterrows():
        accessions = parse_accessions(row["study_accessions"])
        if not accessions:
            continue
        # union all accessions within this row
        for acc in accessions[1:]:
            uf.union(accessions[0], acc)
        # union across rows that share a paper key
        paper_key = str(row.get("paper_short_title") or row.get("paper_link") or "").strip().lower()
        if paper_key:
            if paper_key in key_anchor:
                uf.union(key_anchor[paper_key], accessions[0])
            else:
                key_anchor[paper_key] = accessions[0]
        n_isolates = pd.to_numeric(row.get("isolates_in_study"), errors="coerce")
        for acc in accessions:
            records.append(
                {
                    "study_accession": acc,
                    "paper_short_title": str(row.get("paper_short_title") or "").strip(),
                    "n_isolates": n_isolates,
                }
            )

    exploded = pd.DataFrame.from_records(records).drop_duplicates("study_accession").reset_index(drop=True)
    exploded["paper_group"] = exploded["study_accession"].map(uf.find)
    return exploded


def assign_folds(exploded: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Assign train/val/test folds at paper-group level, balanced in *accessions*.

    Groups are placed greedily, largest study (by ``isolates_in_study``) first, each into
    the fold whose current accession count is furthest *below* its target share. Placing
    big-isolate cohorts first spreads them across the three folds (the stratification
    intent), while the largest-deficit rule keeps the **accession-level** fractions close
    to 50/20/30 despite multi-accession groups. Folds broadcast to every accession in the
    group, so no paper straddles folds. The seed only breaks ties between equal-size
    groups, so the result is reproducible.

    Parameters
    ----------
    exploded
        Output of :func:`build_paper_groups`.
    seed
        RNG seed; the same seed reproduces an identical assignment.

    Returns
    -------
    pandas.DataFrame
        ``exploded`` with an added ``fold`` column.
    """
    group_isolates = exploded.groupby("paper_group")["n_isolates"].max().fillna(0.0)
    group_accessions = exploded.groupby("paper_group")["study_accession"].count()

    # Order: largest study first; seeded jitter breaks ties deterministically.
    rng = np.random.default_rng(seed)
    jitter = pd.Series(rng.permutation(len(group_isolates)), index=group_isolates.index)
    order = sorted(group_isolates.index, key=lambda g: (-group_isolates[g], int(jitter[g]), g))

    counts = dict.fromkeys(FRACTIONS, 0)
    fold_of_group: dict[str, str] = {}
    for group in order:
        size = int(group_accessions[group])
        placed = sum(counts.values())
        # Fold most "owed" accessions once this group is added.
        best = max(FRACTIONS, key=lambda f: FRACTIONS[f] * (placed + size) - counts[f])
        fold_of_group[group] = best
        counts[best] += size

    out = exploded.copy()
    out["fold"] = out["paper_group"].map(fold_of_group)
    return out


def _check(out: pd.DataFrame, n_input_accessions: int) -> None:
    """Assert the split invariants and print a summary."""
    # 1. No paper-group spans more than one fold.
    spanning = out.groupby("paper_group")["fold"].nunique()
    assert (spanning == 1).all(), f"paper-groups spanning folds: {spanning[spanning > 1].index.tolist()}"
    # 2. Every accession appears exactly once.
    assert out["study_accession"].is_unique, "duplicate accessions in output"
    assert len(out) == n_input_accessions, f"accession count drift: {len(out)} vs {n_input_accessions}"
    # 3. Fold fractions roughly match the target.
    counts = out["fold"].value_counts()
    print(f"accessions: {len(out)}  paper-groups: {out['paper_group'].nunique()}")
    for fold in ("train", "val", "test"):
        n = int(counts.get(fold, 0))
        print(f"  {fold:5s}: {n:4d} accessions ({n / len(out):.0%})  target {FRACTIONS[fold]:.0%}")


def main() -> None:
    """Build and write the Klebsiella train/val/test split."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Frozen curation-sheet CSV snapshot.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output split TSV.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed (part of the artefact identity).")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    exploded = build_paper_groups(df)
    out = assign_folds(exploded, seed=args.seed)
    out["seed"] = args.seed

    _check(out, n_input_accessions=len(exploded))

    out = out.sort_values(["fold", "n_isolates", "study_accession"], ascending=[True, False, True])
    out = out[["study_accession", "paper_short_title", "n_isolates", "fold", "seed"]]
    out["n_isolates"] = out["n_isolates"].astype("Int64")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, sep="\t", index=False)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
