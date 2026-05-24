"""Repair related_lr_accession using the Norway integration map.

related_lr_accession was unreliable for the Norway complete genomes (it
held stale "ghost GCF" values), so the long-read link could not be
recovered from metadata alone. The authoritative map is
``final/norway_genomes/norway_tables1_integration.tsv``: column
``biosample`` is our ``Sample`` and ``resolved_gca`` is the downloaded
long-read GenBank assembly accession.

For every Sample that equals an integration ``biosample`` with a
non-empty ``resolved_gca``, this script overwrites ``related_lr_accession``
with that ``resolved_gca`` (other rows untouched), in place, in both the
full and slimmed curated metadata. A timestamped ``.bak`` is written
beside each file first.

Run from ~/workspace/BacHGT:
    uv run python src/bac_data/fix_related_lr_accession.py
"""

from __future__ import annotations

import csv
import shutil
from datetime import datetime
from pathlib import Path

FINAL = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final")
INTEGRATION = FINAL / "norway_genomes" / "norway_tables1_integration.tsv"
TARGETS = [
    FINAL / "metadata_final_curated_all_samples_and_columns.tsv",
    FINAL / "metadata_final_curated_slimmed.tsv",
]
COL = "related_lr_accession"


def load_map() -> dict[str, str]:
    """Biosample -> resolved_gca (only rows with a non-empty resolved_gca)."""
    out: dict[str, str] = {}
    with INTEGRATION.open(newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            bs = (row.get("biosample") or "").strip()
            gca = (row.get("resolved_gca") or "").strip()
            if bs and gca:
                out[bs] = gca
    return out


def fix_file(path: Path, bs2gca: dict[str, str], stamp: str) -> None:
    """Repair the ``related_lr_accession`` column of ``path`` in place using ``bs2gca``."""
    lines = path.read_text().splitlines()
    header = lines[0].split("\t")
    s_idx = header.index("Sample")
    c_idx = header.index(COL)
    ncol = len(header)

    changed = unchanged_same = 0
    out = [lines[0]]
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) != ncol:  # do not touch ragged rows
            out.append(ln)
            continue
        gca = bs2gca.get(f[s_idx])
        if gca is not None:
            if f[c_idx] == gca:
                unchanged_same += 1
            else:
                f[c_idx] = gca
                changed += 1
            out.append("\t".join(f))
        else:
            out.append(ln)

    bak = path.with_suffix(path.suffix + f".{stamp}.bak")
    shutil.copy2(path, bak)
    path.write_text("\n".join(out) + "\n")
    print(f"{path.name}: rows={len(lines) - 1} {COL}_set={changed} already_correct={unchanged_same}  backup={bak.name}")


def main() -> int:
    """CLI entry point."""
    bs2gca = load_map()
    print(f"Integration map: {len(bs2gca)} biosample->resolved_gca\n")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    for t in TARGETS:
        fix_file(t, bs2gca, stamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
