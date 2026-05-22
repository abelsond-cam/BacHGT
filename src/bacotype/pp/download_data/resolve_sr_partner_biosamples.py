#!/usr/bin/env python3
"""Resolve the Cohort-B SR run accessions to INSDC BioSamples.

resolve_sr_partner_biosamples.py
--------------------------------
``is_refseq=True`` rows in the curated metadata carry a paired short-read run in
``related_sr_accession`` (an ENA *run* ID: SRR/ERR/DRR). ATB and BakRep both key
on INSDC **BioSample** (``SAM*``), so before anything can be downloaded each SR
run must be resolved to its BioSample.

Two resolution routes, cheapest first:

1. **Internal join** — a metadata row whose ``run_accession`` equals the SR run
   already tells us its ``Sample`` (a BioSample). Free, offline.
2. **ENA Portal API** — for runs not in the metadata, batch-query
   ``read_run`` for ``run_accession -> sample_accession`` (the ENA
   ``sample_accession`` field is the INSDC BioSample).

Output ``related_sr/sr_partner_resolution.tsv`` with one row per refseq SR
partner: ``lr_sample, lr_secondary_accession, sr_run, sr_biosample,
resolved_via, unresolved``.

Usage
─────
    uv run python -m bacotype.pp.download_data.resolve_sr_partner_biosamples
        [--metadata PATH] [--out-dir PATH] [--batch 50] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ─── PATHS ────────────────────────────────────────────────────────────────────

DEFAULT_METADATA = Path(
    "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/"
    "Aaron Weimann's files - project_k/data/final/metadata/"
    "metadata_final_curated_all_samples_and_columns.tsv"
)
LOCAL_RAW = Path(
    "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/"
    "local_data/klebsiella/raw"
)
DEFAULT_OUT_DIR = LOCAL_RAW / "related_sr"
RESOLUTION_NAME = "sr_partner_resolution.tsv"

ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api/search"
DEFAULT_TIMEOUT = 120
DEFAULT_RETRIES = 4

_ABSENT = {"", "nan", "none", "na", "<na>", "null"}


def _clean(val: object) -> str:
    """Return a trimmed string, or '' for pandas/empty sentinels."""
    s = str(val).strip()
    return "" if s.lower() in _ABSENT else s


def read_refseq_sr_rows(meta: pd.DataFrame) -> pd.DataFrame:
    """Return one row per ``is_refseq`` sample that has a ``related_sr_accession``.

    Columns: ``lr_sample``, ``lr_secondary_accession`` (GCF for refseq),
    ``sr_run``.
    """
    is_ref = meta["is_refseq"].astype(str).str.strip().str.lower().isin({"true", "1", "1.0"})
    sub = meta.loc[is_ref, ["Sample", "secondary_sample_accession", "related_sr_accession"]].copy()
    sub["sr_run"] = sub["related_sr_accession"].map(_clean)
    sub = sub[sub["sr_run"] != ""]
    out = pd.DataFrame(
        {
            "lr_sample": sub["Sample"].map(_clean),
            "lr_secondary_accession": sub["secondary_sample_accession"].map(_clean),
            "sr_run": sub["sr_run"],
        }
    )
    return out.drop_duplicates(subset=["sr_run"]).reset_index(drop=True)


def internal_join(rows: pd.DataFrame, meta: pd.DataFrame) -> dict[str, str]:
    """Map ``sr_run -> BioSample`` using metadata rows keyed by ``run_accession``.

    A metadata row whose ``run_accession`` is the SR run already records its
    ``Sample`` (a BioSample), so no network call is needed for those.
    """
    run_to_sample: dict[str, str] = {}
    if "run_accession" not in meta.columns:
        return run_to_sample
    m = meta[["run_accession", "Sample"]].copy()
    m["run_accession"] = m["run_accession"].map(_clean)
    m["Sample"] = m["Sample"].map(_clean)
    m = m[(m["run_accession"] != "") & (m["Sample"] != "")]
    lut = dict(zip(m["run_accession"], m["Sample"]))
    wanted = set(rows["sr_run"])
    for run in wanted:
        bs = lut.get(run)
        if bs and bs.startswith("SAM"):
            run_to_sample[run] = bs
    return run_to_sample


def _ena_session() -> requests.Session:
    """Return a session with a descriptive User-Agent."""
    s = requests.Session()
    s.headers.update({"User-Agent": "bacotype-resolve-sr-partners/1.0"})
    return s


def ena_resolve(runs: list[str], batch: int, session: requests.Session) -> dict[str, str]:
    """Resolve ``run_accession -> sample_accession`` via the ENA Portal API.

    Queries the ``read_run`` result in OR-batches; the ENA ``sample_accession``
    field is the INSDC BioSample. Unresolved runs are simply absent from the
    returned mapping.
    """
    resolved: dict[str, str] = {}
    for i in range(0, len(runs), batch):
        chunk = runs[i : i + batch]
        query = " OR ".join(f'run_accession="{r}"' for r in chunk)
        params = {
            "result": "read_run",
            "query": query,
            "fields": "run_accession,sample_accession",
            "format": "tsv",
            "limit": 0,
        }
        for attempt in range(DEFAULT_RETRIES):
            try:
                resp = session.get(ENA_PORTAL, params=params, timeout=DEFAULT_TIMEOUT)
            except requests.RequestException as exc:
                print(f"  WARN ENA batch {i // batch} attempt {attempt + 1}: {exc}", file=sys.stderr, flush=True)
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                for line in lines[1:]:  # skip header
                    parts = line.split("\t")
                    if len(parts) < 2:
                        continue
                    run, sample = parts[0].strip(), parts[1].strip()
                    if run and sample.startswith("SAM"):
                        resolved[run] = sample
                break
            if resp.status_code in (429, 500, 502, 503, 504):
                print(
                    f"  WARN ENA batch {i // batch} status={resp.status_code}; retrying",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(2 * (attempt + 1))
                continue
            print(
                f"  WARN ENA batch {i // batch} status={resp.status_code} body={resp.text[:160]!r}",
                file=sys.stderr,
                flush=True,
            )
            break
        done = min(i + batch, len(runs))
        if done % (batch * 10) == 0 or done == len(runs):
            print(f"  ... ENA resolved {len(resolved)}/{done} queried", flush=True)
    return resolved


def main(argv: list[str] | None = None) -> int:
    """Resolve every refseq SR run to a BioSample; write the resolution TSV."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--batch", type=int, default=50, help="ENA OR-query batch size")
    parser.add_argument("--limit", type=int, default=None, help="cap SR runs (smoke-test)")
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading metadata: {args.metadata}", flush=True)
    meta = pd.read_csv(
        args.metadata,
        sep="\t",
        low_memory=False,
        usecols=["Sample", "is_refseq", "secondary_sample_accession", "related_sr_accession", "run_accession"],
    )
    print(f"  {len(meta)} metadata rows", flush=True)

    rows = read_refseq_sr_rows(meta)
    if args.limit:
        rows = rows.head(args.limit).copy()
    print(f"Refseq samples with a related_sr_accession: {len(rows)}", flush=True)

    internal = internal_join(rows, meta)
    print(f"Resolved via internal metadata join: {len(internal)}", flush=True)

    need_ena = sorted(set(rows["sr_run"]) - set(internal))
    ena: dict[str, str] = {}
    if need_ena:
        print(f"Querying ENA for remaining {len(need_ena)} runs ...", flush=True)
        ena = ena_resolve(need_ena, args.batch, _ena_session())
        print(f"Resolved via ENA Portal API: {len(ena)}", flush=True)

    def _resolve(run: str) -> tuple[str, str]:
        if run in internal:
            return internal[run], "internal_join"
        if run in ena:
            return ena[run], "ena_portal"
        return "", "unresolved"

    resolved_pairs = rows["sr_run"].map(_resolve)
    rows["sr_biosample"] = [p[0] for p in resolved_pairs]
    rows["resolved_via"] = [p[1] for p in resolved_pairs]
    rows["unresolved"] = rows["sr_biosample"] == ""

    out_path = args.out_dir / RESOLUTION_NAME
    rows.to_csv(out_path, sep="\t", index=False)

    n_unres = int(rows["unresolved"].sum())
    print("\n=== resolution summary ===", flush=True)
    print(f"SR partners total      : {len(rows)}", flush=True)
    print(f"  internal_join        : {int((rows['resolved_via'] == 'internal_join').sum())}", flush=True)
    print(f"  ena_portal           : {int((rows['resolved_via'] == 'ena_portal').sum())}", flush=True)
    print(f"  unresolved           : {n_unres}", flush=True)
    if n_unres:
        print(f"  unresolved runs (head): {rows.loc[rows['unresolved'], 'sr_run'].head(20).tolist()}", flush=True)
    print(f"\nResolution → {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
