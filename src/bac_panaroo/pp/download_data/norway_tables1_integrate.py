#!/usr/bin/env python3
"""Integrate the Norway KPSC paper's Table S1 against our curated metadata.

norway_tables1_integrate.py
------------------------------
Table S1 is the authoritative ``strain ↔ BioSample ↔ GenBank
complete-genome accession ↔ Illumina run ↔ ONT run`` map for the 579
complete genomes. This script cross-checks it against our curated
metadata and resolves the GenBank records to NCBI assemblies.

Why this exists
───────────────
Every prior search (see ``norway_cohort_audit.py``) failed to find the
Norway complete genomes because they were deposited **only as
GenBank/INSDC nucleotide records** (CP-range accessions = chromosome +
plasmids), **never RefSeq-mirrored**, and keyed under an NCBI-side
``SAMN…`` BioSample that differs from the ``SAMEA…`` in our metadata — so
NCBI-Datasets-by-biosample returned nothing. The records are nonetheless
fully retrievable via NCBI **E-utilities** (``efetch`` / ``elink`` /
``esummary``), which is what this script uses.

What it produces
────────────────
A reviewable integration TSV (one row per S1 strain) plus a discrepancy
report. With ``--augment`` it also produces an integrated metadata copy
(or, with ``--write-back``, overwrites ``--metadata`` in place after a
timestamped backup). With ``--download`` it fetches each resolved GCA's
GenBank genome + GFF via the NCBI Datasets CLI.

For every S1 strain it:
  1. expands the ``GenBank accession`` range to its nuccore accessions,
  2. validates them via ``esummary`` (existence / length / title),
  3. resolves the assembly via ``elink`` nuccore→assembly + ``esummary``
     (GCA, paired RefSeq GCF if any, assembly name, NCBI biosample),
  4. cross-checks BioSample + Illumina + ONT accessions against our
     metadata columns, the related-run side CSVs, and (unless
     ``--skip-70-gcf``) the PRJEB74192 Complete-Genome GCF set.

Set ``NCBI_API_KEY`` to lift the E-utilities rate limit from 3 to 10
req/s (the per-strain ``elink``/``esummary`` calls dominate runtime).

Usage
─────
    uv run python src/bac_panaroo/pp/download_data/norway_tables1_integrate.py
        [--table-s1 PATH]      # default: the Norway_Complete_Genomes_Fig1.xlsx
        [--metadata PATH]      # default: curated slimmed TSV
        [--out-dir PATH]       # default: <metadata dir>/processed
        [--limit N]            # cap to first N strains (smoke-test)
        [--skip-70-gcf]        # skip the PRJEB74192 GCF cross-check (slow)
        [--augment]            # also produce an integrated metadata copy
        [--write-back]         # with --augment: overwrite --metadata in place
                               #   (timestamped .bak alongside it first)
        [--download]           # also fetch each resolved GCA's GenBank
                               #   genome + GFF via the NCBI Datasets CLI
        [--assemblies-dir PATH]  # genomes → <dir>/<GCA>.fna.gz
        [--gff-dir PATH]         # annotations → <dir>/<GCA>.gff
        [--datasets-cmd CMD]     # default: "datasets"

Outputs (in ``--out-dir``)
  norway_tables1_integration.tsv     one row per S1 strain (579)
  norway_tables1_discrepancies.tsv   problem rows, with a reason column
"""

from __future__ import annotations

import argparse
import gzip
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# Reuse the Norway audit module's auth + PRJEB74192 helpers.
from bac_panaroo.pp.download_data.norway_cohort_audit import (
    DEFAULT_METADATA,
    UMBRELLA_PROJECT,
    _gca_primaries,
    ncbi_bioproject_records,
    ncbi_headers,
)

# ─── PATHS ────────────────────────────────────────────────────────────────────

# The paper supplement. Note it is an .xlsx (sheet "Table S1"), not a CSV.
TABLE_S1_DEFAULT = Path(
    "/Users/davidabelson/Library/CloudStorage/OneDrive-UniversityofCambridge/Norway_Complete_Genomes_Fig1.xlsx"
)
TABLE_S1_SHEET = "Table S1"

# Related-run side CSVs live next to the curated metadata.
RELATED_SR_CSV = "related_sr_run_accessions.csv"
RELATED_LR_CSV = "related_lr_run_accessions.csv"

# ─── E-UTILITIES ──────────────────────────────────────────────────────────────

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EUTILS_TOOL = "bac_panaroo-norway-tables1"
EUTILS_EMAIL = "abelsond@cam.ac.uk"

DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 3
ESUMMARY_BATCH = 180  # nuccore accessions per esummary call

# E-utilities min interval between requests: ~3 req/s anon, ~10 with key.
INTERVAL_WITHOUT_KEY = 0.35
INTERVAL_WITH_KEY = 0.11


class RateLimiter:
    """Thread-safe global request pacer.

    ``wait()`` blocks until at least ``interval`` seconds have elapsed
    since the previous caller was admitted, so concurrent workers stay
    collectively under NCBI's per-second limit while still overlapping
    network latency.
    """

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        """Block until this caller is allowed to issue its request."""
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next - now)
            self._next = max(now, self._next) + self._interval
        if sleep_for:
            time.sleep(sleep_for)


def eutils_auth() -> tuple[dict[str, str], float]:
    """Return E-utilities query params and the matching min request interval.

    ``api_key`` is added when ``NCBI_API_KEY`` is set, which raises the
    limit from 3 to 10 req/s.
    """
    base = {"tool": EUTILS_TOOL, "email": EUTILS_EMAIL}
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return {**base, "api_key": key}, INTERVAL_WITH_KEY
    return base, INTERVAL_WITHOUT_KEY


def eutils_get(endpoint: str, params: dict, auth: dict[str, str], limiter: RateLimiter) -> requests.Response | None:
    """GET an E-utilities endpoint, rate-limited, with retry on failure.

    Returns the ``Response`` on HTTP 200, else ``None`` after retries.
    """
    url = EUTILS + endpoint
    merged = {**params, **auth}
    for attempt in range(DEFAULT_RETRIES):
        limiter.wait()
        try:
            r = requests.get(url, params=merged, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            print(f"  WARN {endpoint} attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            print(
                f"  WARN {endpoint} attempt={attempt + 1} status={r.status_code}; retrying",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(2 * (attempt + 1))
            continue
        print(
            f"  WARN {endpoint} status={r.status_code} body={r.text[:160]!r}",
            file=sys.stderr,
            flush=True,
        )
        return None
    return None


# ─── GENBANK RANGE EXPANSION ──────────────────────────────────────────────────

_ACC_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def expand_genbank_range(raw: str) -> list[str]:
    """Expand a ``GenBank accession`` cell to its nuccore accessions.

    ``"CP153558-CP153560"`` → ``["CP153558", "CP153559", "CP153560"]``;
    a single accession is returned as a one-element list. The numeric
    width and letter prefix of the left token are preserved. Anything
    unparseable is returned as ``[raw.strip()]`` so it surfaces in the
    discrepancy report rather than vanishing.
    """
    s = str(raw).strip()
    if "-" not in s:
        return [s] if s else []
    left, right = (p.strip() for p in s.split("-", 1))
    m_left = _ACC_RE.match(left)
    m_right = re.match(r"^([A-Za-z]+)?(\d+)$", right)
    if not m_left or not m_right:
        return [s]
    prefix, start_digits = m_left.group(1), m_left.group(2)
    width = len(start_digits)
    start, end = int(start_digits), int(m_right.group(2))
    if end < start or end - start > 999:  # sanity guard
        return [s]
    return [f"{prefix}{str(n).zfill(width)}" for n in range(start, end + 1)]


# ─── NCBI LOOKUPS ─────────────────────────────────────────────────────────────


def esummary_nuccore(accs: list[str], auth: dict[str, str], limiter: RateLimiter) -> dict[str, dict]:
    """Batch-validate nuccore accessions via ``esummary``.

    Returns ``{bare_acc: {slen, title}}`` for every accession NCBI knows
    about (missing ones simply absent). Call once over all accessions.
    """
    out: dict[str, dict] = {}
    for i in range(0, len(accs), ESUMMARY_BATCH):
        batch = accs[i : i + ESUMMARY_BATCH]
        r = eutils_get(
            "esummary.fcgi",
            {"db": "nuccore", "id": ",".join(batch), "retmode": "json"},
            auth,
            limiter,
        )
        if r is None:
            continue
        try:
            result = r.json().get("result", {})
        except ValueError:
            continue
        for uid in result.get("uids", []):
            ent = result.get(uid, {})
            acc = ent.get("caption") or str(ent.get("accessionversion", "")).split(".")[0]
            if acc:
                out[acc] = {"slen": ent.get("slen"), "title": ent.get("title", "")}
    return out


def elink_assembly_uid(first_cp: str, auth: dict[str, str], limiter: RateLimiter) -> str:
    """Return the first assembly UID linked from a nuccore accession.

    elink merges links when given multiple ids, so this is unavoidably
    one call per strain. Returns ``""`` when nothing is linked.
    """
    r = eutils_get(
        "elink.fcgi",
        {"dbfrom": "nuccore", "db": "assembly", "id": first_cp, "retmode": "json"},
        auth,
        limiter,
    )
    if r is None:
        return ""
    try:
        linksets = r.json().get("linksets", [])
    except ValueError:
        return ""
    for ls in linksets:
        for db in ls.get("linksetdbs", []):
            if db.get("linkname") == "nuccore_assembly" and db.get("links"):
                return db["links"][0]
    return ""


def esummary_assembly(uids: list[str], auth: dict[str, str], limiter: RateLimiter) -> dict[str, dict]:
    """Batch-summarise assembly UIDs.

    Returns ``{uid: {resolved_gca, resolved_refseq_gcf, assembly_name,
    ncbi_assembly_biosample, assembly_level}}``.
    """
    out: dict[str, dict] = {}
    uniq = sorted(set(uids))
    for i in range(0, len(uniq), ESUMMARY_BATCH):
        batch = uniq[i : i + ESUMMARY_BATCH]
        r = eutils_get(
            "esummary.fcgi",
            {"db": "assembly", "id": ",".join(batch), "retmode": "json"},
            auth,
            limiter,
        )
        if r is None:
            continue
        try:
            result = r.json().get("result", {})
        except ValueError:
            continue
        for uid in result.get("uids", []):
            ent = result.get(uid, {})
            syn = ent.get("synonym", {}) or {}
            out[uid] = {
                "resolved_gca": syn.get("genbank", "") or ent.get("assemblyaccession", ""),
                "resolved_refseq_gcf": syn.get("refseq", ""),
                "assembly_name": ent.get("assemblyname", ""),
                "ncbi_assembly_biosample": ent.get("biosampleaccn", ""),
                "assembly_level": ent.get("assemblylevel", ""),
            }
    return out


# ─── INPUTS ───────────────────────────────────────────────────────────────────

S1_RENAME = {
    "strain": "strain",
    "BioSample accession": "biosample",
    "GenBank accession": "genbank_raw",
    "Illumina read accession": "illumina_acc",
    "ONT read accession": "ont_acc",
    "Total length (Mbp)": "total_length_mbp",
    "SL": "SL",
    "ST": "ST",
    "Collection year": "collection_year",
    "Host": "host",
    "Source": "source",
}


def load_table_s1(path: Path, limit: int | None) -> pd.DataFrame:
    """Read Table S1, normalise column names, keep the columns we use."""
    df = pd.read_excel(path, sheet_name=TABLE_S1_SHEET)
    df.columns = [str(c).strip() for c in df.columns]
    keep = {k: v for k, v in S1_RENAME.items() if k in df.columns}
    df = df[list(keep)].rename(columns=keep)
    for c in ("strain", "biosample", "genbank_raw", "illumina_acc", "ont_acc"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    if limit:
        df = df.head(limit).copy()
    return df.reset_index(drop=True)


def _col_set(df: pd.DataFrame, col: str) -> set[str]:
    """Set of non-null string values in a column (empty if absent)."""
    if col not in df.columns:
        return set()
    return set(df[col].dropna().astype(str))


def load_metadata_sets(metadata_path: Path) -> dict[str, set[str]]:
    """Load the metadata + side CSVs into the accession sets we match against."""
    m = pd.read_csv(metadata_path, sep="\t", low_memory=False)
    norkab = set(
        m.loc[m.get("is_complete_norway_genome") == True, "Sample"].astype(str)  # noqa: E712
    )
    sets = {
        "sample": _col_set(m, "Sample"),
        "sample_accession": _col_set(m, "sample_accession"),
        "secondary": _col_set(m, "secondary_sample_accession"),
        "run_accession": _col_set(m, "run_accession"),
        "related_sr": _col_set(m, "related_sr_run_accession"),
        "related_lr": _col_set(m, "related_lr_run_accession"),
        "norkab": norkab,
    }
    side_dir = metadata_path.parent
    for name, key in ((RELATED_SR_CSV, "sr_csv"), (RELATED_LR_CSV, "lr_csv")):
        p = side_dir / name
        sets[key] = _col_set(pd.read_csv(p), "run_accession") if p.exists() else set()
    return sets


def get_70_complete_gcf_set(metadata_path: Path) -> set[str]:
    """Return the "70 GCFs" set.

    The PRJEB74192 Complete-Genome paired-GCF accessions that intersect
    our metadata's ``secondary_sample_accession``.
    """
    headers, sleep_s = ncbi_headers()
    recs = ncbi_bioproject_records(UMBRELLA_PROJECT, headers, sleep_s)
    gca = _gca_primaries(recs)
    if not len(gca):
        return set()
    complete = gca[gca["level"] == "Complete Genome"]
    s1_gcfs = {g for g in complete["gcf"] if str(g).startswith("GCF_")}
    m = pd.read_csv(metadata_path, sep="\t", low_memory=False, usecols=["secondary_sample_accession"])
    our = set(m["secondary_sample_accession"].dropna().astype(str))
    return s1_gcfs & our


# ─── BUILD ────────────────────────────────────────────────────────────────────


def build_rows(
    s1: pd.DataFrame,
    sets: dict[str, set[str]],
    gcf70: set[str],
    auth: dict[str, str],
    limiter: RateLimiter,
    workers: int,
) -> pd.DataFrame:
    """Resolve + cross-check every S1 strain in batched phases.

    Phase 1 expands all GenBank ranges and validates every nuccore
    accession in one batched ``esummary`` sweep. Phase 2 runs the
    unavoidable per-strain ``elink`` concurrently (rate-limited). Phase 3
    batch-summarises the linked assembly UIDs. Phase 4 assembles rows.
    The actual GenBank genome + GFF download is a separate phase keyed on
    ``resolved_gca`` (see :func:`download_assemblies`).
    """
    n = len(s1)
    recs = [r._asdict() for r in s1.itertuples(index=False)]
    accs_per = [expand_genbank_range(d.get("genbank_raw", "")) for d in recs]
    first_cps = [a[0] if a else "" for a in accs_per]

    # Phase 1 — one batched nuccore esummary over every accession.
    all_accs = sorted({a for accs in accs_per for a in accs})
    print(f"Phase 1/3: validating {len(all_accs)} nuccore accessions ...", flush=True)
    nuc = esummary_nuccore(all_accs, auth, limiter) if all_accs else {}
    print(f"  {len(nuc)}/{len(all_accs)} nuccore records exist", flush=True)

    # Phase 2 — per-strain elink (concurrent, rate-limited).
    print(f"Phase 2/3: elink nuccore→assembly for {n} strains ({workers} workers) ...", flush=True)
    uids: list[str] = [""] * n
    done = 0

    def _link(idx: int) -> tuple[int, str]:
        return idx, (elink_assembly_uid(first_cps[idx], auth, limiter) if first_cps[idx] else "")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for idx, uid in pool.map(_link, range(n)):
            uids[idx] = uid
            done += 1
            if done % 50 == 0 or done == n:
                print(f"  ... {done}/{n} elinked; {sum(bool(u) for u in uids)} linked", flush=True)

    # Phase 3 — one batched assembly esummary over the linked UIDs.
    linked = [u for u in uids if u]
    print(f"Phase 3/3: summarising {len(set(linked))} unique assembly UIDs ...", flush=True)
    asm_by_uid = esummary_assembly(linked, auth, limiter) if linked else {}

    # Phase 4 — assemble rows + cross-check.
    rows = []
    for d, accs, fcp, uid in zip(recs, accs_per, first_cps, uids, strict=True):
        n_valid = sum(1 for a in accs if a in nuc)
        total_len = sum(int(nuc[a]["slen"]) for a in accs if a in nuc and nuc[a]["slen"])
        titles = "; ".join(nuc[a]["title"] for a in accs if a in nuc)
        asm = asm_by_uid.get(uid, {})

        bs = str(d.get("biosample", ""))
        ill = str(d.get("illumina_acc", ""))
        ont = str(d.get("ont_acc", ""))
        in_meta = bs in sets["sample"] or bs in sets["sample_accession"] or bs in sets["secondary"]
        gcf = str(asm.get("resolved_refseq_gcf", ""))

        rows.append(
            {
                "strain": d.get("strain", ""),
                "biosample": bs,
                "genbank_raw": d.get("genbank_raw", ""),
                "n_nuccore": len(accs),
                "n_nuccore_valid": n_valid,
                "first_cp": fcp,
                "all_cp": ",".join(accs),
                "resolved_gca": asm.get("resolved_gca", ""),
                "resolved_refseq_gcf": gcf,
                "assembly_name": asm.get("assembly_name", ""),
                "ncbi_assembly_biosample": asm.get("ncbi_assembly_biosample", ""),
                "assembly_level": asm.get("assembly_level", ""),
                "nuccore_total_len_bp": total_len,
                "nuccore_titles": titles,
                "illumina_acc": ill,
                "ont_acc": ont,
                "in_metadata": in_meta,
                "is_complete_norway_genome": bs in sets["norkab"],
                "illumina_in_run_accession": ill in sets["run_accession"],
                "illumina_in_related_sr": ill in sets["related_sr"] or ill in sets["sr_csv"],
                "ont_in_related_lr": ont in sets["related_lr"] or ont in sets["lr_csv"],
                "ont_in_run_accession": ont in sets["run_accession"],
                "in_70_complete_gcf": bool(gcf) and gcf in gcf70,
            }
        )
    return pd.DataFrame(rows)


def discrepancy_rows(integ: pd.DataFrame) -> pd.DataFrame:
    """Flatten the problem rows into a long ``reason``-tagged frame."""
    out = []
    for r in integ.itertuples(index=False):
        d = r._asdict()
        reasons = []
        if not d["in_metadata"]:
            reasons.append("biosample_not_in_metadata")
        if d["in_metadata"] and not d["ont_in_related_lr"]:
            reasons.append("ont_not_linked_in_metadata")
        if d["in_metadata"] and not d["illumina_in_run_accession"]:
            reasons.append("illumina_not_linked_in_metadata")
        if d["n_nuccore"] and d["n_nuccore_valid"] < d["n_nuccore"]:
            reasons.append("nuccore_validation_incomplete")
        if not d["resolved_gca"]:
            reasons.append("no_gca_resolved")
        for reason in reasons:
            out.append({"reason": reason, **d})
    cols = [
        "reason",
        "strain",
        "biosample",
        "genbank_raw",
        "first_cp",
        "resolved_gca",
        "in_metadata",
        "is_complete_norway_genome",
        "illumina_acc",
        "ont_acc",
        "n_nuccore",
        "n_nuccore_valid",
    ]
    df = pd.DataFrame(out)
    return df[cols] if len(df) else df


def print_summary(integ: pd.DataFrame, gcf70_used: bool) -> None:
    """Print the headline reconciliation table."""
    n = len(integ)
    in_meta = integ["in_metadata"].sum()
    norkab = integ["is_complete_norway_genome"].sum()
    print("\n=== Norway Table S1 integration summary ===", flush=True)
    print(f"S1 strains processed                         : {n}", flush=True)
    print(f"  with ≥1 nuccore record validated           : {(integ['n_nuccore_valid'] > 0).sum()}", flush=True)
    print(f"  with a resolved GCA assembly               : {(integ['resolved_gca'] != '').sum()}", flush=True)
    print(f"  with a paired RefSeq GCF                    : {(integ['resolved_refseq_gcf'] != '').sum()}", flush=True)
    print(f"S1 BioSample in our metadata                 : {in_meta}", flush=True)
    print(f"  flagged is_complete_norway_genome=True      : {norkab}", flush=True)
    print(f"S1 strains NOT in our metadata               : {n - in_meta}", flush=True)
    print(f"Illumina acc == metadata run_accession       : {integ['illumina_in_run_accession'].sum()}", flush=True)
    print(f"ONT acc      ∈ related_lr (+ side CSV)        : {integ['ont_in_related_lr'].sum()}", flush=True)
    if gcf70_used:
        print(f"Resolved GCF ∈ PRJEB74192 70-complete set     : {integ['in_70_complete_gcf'].sum()}", flush=True)


def _species_from_titles(titles: str) -> str:
    """Pull a binomial species from the nuccore title, else fall back."""
    m = re.match(r"\s*([A-Z][a-z]+ [a-z]+)", str(titles))
    return m.group(1) if m else "Klebsiella pneumoniae"


def augment_metadata(integ: pd.DataFrame, metadata_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Produce a metadata copy with the resolved complete genomes integrated.

    Genomes whose paired RefSeq GCF is already an ``is_refseq`` row get
    ``is_complete_norway_genome=True`` set on that row (no duplicate).
    Every other resolved genome is appended as a new GCA-keyed row with
    ``is_refseq=True`` (provisional) + ``is_complete_norway_genome=True``,
    Illumina run in ``related_sr_run_accession`` and ONT run in
    ``run_accession`` (the existing is_refseq convention). Strains with
    no resolved GCA are skipped. Returns ``(augmented_df, changes_df)``.
    """
    m = pd.read_csv(metadata_path, sep="\t", low_memory=False)

    # Version-insensitive GCF → existing-is_refseq-row-index map.
    refseq_mask = m.get("is_refseq") == True  # noqa: E712
    gcf_to_idx: dict[str, list[int]] = {}
    for col in ("secondary_sample_accession", "Sample"):
        if col not in m.columns:
            continue
        sub = m.loc[refseq_mask, col].dropna().astype(str)
        for idx, val in sub.items():
            if val.startswith("GCF_"):
                gcf_to_idx.setdefault(val.split(".")[0], []).append(idx)

    changes: list[dict] = []
    new_rows: list[dict] = []
    seen_gca: set[str] = set()
    blank = dict.fromkeys(m.columns, pd.NA)

    for r in integ.itertuples(index=False):
        d = r._asdict()
        gca = str(d.get("resolved_gca", "") or "")
        if not gca:
            changes.append({"action": "skipped_no_gca", **_prov(d)})
            continue
        gca_base = gca.split(".")[0]
        if gca_base in seen_gca:
            changes.append({"action": "skipped_duplicate_gca", **_prov(d)})
            continue
        seen_gca.add(gca_base)

        gcf = str(d.get("resolved_refseq_gcf", "") or "")
        gcf_base = gcf.split(".")[0] if gcf.startswith("GCF_") else ""
        existing = gcf_to_idx.get(gcf_base, []) if gcf_base else []

        if existing:
            for idx in existing:
                m.at[idx, "is_complete_norway_genome"] = True
            changes.append(
                {"action": "flagged_existing", "matched_Sample": str(m.at[existing[0], "Sample"]), **_prov(d)}
            )
            continue

        row = dict(blank)
        row["Sample"] = gca
        if "sample_accession" in row:
            row["sample_accession"] = gca
        if "secondary_sample_accession" in row:
            row["secondary_sample_accession"] = gcf or gca
        if "accession" in row:
            row["accession"] = gca
        if "is_refseq" in row:
            row["is_refseq"] = True
        if "is_complete_norway_genome" in row:
            row["is_complete_norway_genome"] = True
        if "related_sr_run_accession" in row:
            row["related_sr_run_accession"] = d.get("illumina_acc", "")
        if "run_accession" in row:
            row["run_accession"] = d.get("ont_acc", "")
        if "scientific_name" in row:
            row["scientific_name"] = _species_from_titles(d.get("nuccore_titles", ""))
        new_rows.append(row)
        changes.append({"action": "added_new_row", "matched_Sample": "", **_prov(d)})

    if new_rows:
        # New rows are intentionally NA in most columns; the all-NA-column
        # dtype FutureWarning is expected and the current behaviour is what
        # we want (those cells serialise to empty on TSV write).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            augmented = pd.concat([m, pd.DataFrame(new_rows, columns=m.columns)], ignore_index=True)
    else:
        augmented = m
    return augmented, pd.DataFrame(changes)


def _prov(d: dict) -> dict:
    """Provenance fields carried into the changes log for one S1 strain."""
    return {
        "strain": d.get("strain", ""),
        "biosample": d.get("biosample", ""),
        "resolved_gca": d.get("resolved_gca", ""),
        "resolved_refseq_gcf": d.get("resolved_refseq_gcf", ""),
        "illumina_acc": d.get("illumina_acc", ""),
        "ont_acc": d.get("ont_acc", ""),
    }


# ─── DATASETS DOWNLOAD ────────────────────────────────────────────────────────


def _datasets_download(cmd_parts: list[str], gca: str, zip_path: Path, retries: int = 3) -> bool:
    """Fetch one GCA's genome + gff3 with the NCBI ``datasets`` CLI.

    Parameters
    ----------
    cmd_parts
        The ``datasets`` invocation split into argv tokens (e.g.
        ``["micromamba", "run", "-n", "ncbi-datasets", "datasets"]``).
    gca
        GenBank assembly accession (versioned, e.g. ``GCA_041863035.1``).
    zip_path
        Destination ``.zip`` path the CLI writes its package to.
    retries
        Number of attempts before giving up.

    Returns
    -------
    bool
        ``True`` if a non-empty zip was produced, else ``False``.
    """
    argv = [
        *cmd_parts,
        "download",
        "genome",
        "accession",
        gca,
        "--include",
        "genome,gff3",
        "--filename",
        str(zip_path),
    ]
    for attempt in range(retries):
        try:
            res = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"  WARN datasets {gca} attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
            time.sleep(2 * (attempt + 1))
            continue
        if res.returncode == 0 and zip_path.exists() and zip_path.stat().st_size > 0:
            return True
        print(
            f"  WARN datasets {gca} attempt={attempt + 1} rc={res.returncode} err={res.stderr[:160]!r}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(2 * (attempt + 1))
    return False


def download_assemblies(
    integ: pd.DataFrame,
    assemblies_dir: Path,
    gff_dir: Path,
    datasets_cmd: str,
) -> None:
    """Download each resolved GCA's GenBank genome + GFF via NCBI Datasets.

    For every unique non-empty ``resolved_gca`` in *integ*, fetch the
    GenBank assembly with the NCBI ``datasets`` CLI. The genome is placed
    gzipped as ``<assemblies_dir>/<GCA>.fna.gz`` and the annotation (only
    present when the GenBank submitter provided one) as
    ``<gff_dir>/<GCA>.gff``. A GCA whose ``<GCA>.fna.gz`` already exists is
    skipped. Prints a confirmation summary including the explicit list of
    GCAs with no GFF — unannotated GenBank assemblies that will need later
    local Bakta annotation (out of scope here).

    Parameters
    ----------
    integ
        Integration frame; only its ``resolved_gca`` column is used.
    assemblies_dir
        Output directory for ``<GCA>.fna.gz`` genomes.
    gff_dir
        Output directory for ``<GCA>.gff`` annotations.
    datasets_cmd
        The ``datasets`` CLI invocation (shell-split), e.g.
        ``"micromamba run -n ncbi-datasets datasets"``.
    """
    assemblies_dir.mkdir(parents=True, exist_ok=True)
    gff_dir.mkdir(parents=True, exist_ok=True)

    col = integ.get("resolved_gca", pd.Series(dtype=str))
    gcas = sorted({s for s in col.dropna().astype(str) if s.strip()})
    cmd_parts = shlex.split(datasets_cmd)
    print(f"\nDatasets download: {len(gcas)} unique GCA assemblies → {assemblies_dir}", flush=True)

    genome_ok = 0
    gff_ok = 0
    gff_missing: list[str] = []

    for i, gca in enumerate(gcas, 1):
        genome_dst = assemblies_dir / f"{gca}.fna.gz"
        gff_dst = gff_dir / f"{gca}.gff"
        if genome_dst.exists() and genome_dst.stat().st_size > 0:
            genome_ok += 1
            if gff_dst.exists() and gff_dst.stat().st_size > 0:
                gff_ok += 1
            else:
                gff_missing.append(gca)
            continue

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            zip_path = tmp / f"{gca}.zip"
            if not _datasets_download(cmd_parts, gca, zip_path):
                print(f"  [{i}/{len(gcas)}] {gca}: download FAILED", flush=True)
                continue
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(tmp)
            except zipfile.BadZipFile:
                print(f"  [{i}/{len(gcas)}] {gca}: bad zip", flush=True)
                continue

            data_root = tmp / "ncbi_dataset" / "data"
            fna = next(data_root.rglob("*.fna"), None) if data_root.exists() else None
            if fna is not None:
                with fna.open("rb") as fsrc, gzip.open(genome_dst, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                genome_ok += 1
            else:
                print(f"  [{i}/{len(gcas)}] {gca}: no genome FASTA in package", flush=True)

            gff = next(data_root.rglob("*.gff"), None) if data_root.exists() else None
            if gff is not None:
                shutil.copy2(gff, gff_dst)
                gff_ok += 1
            else:
                gff_missing.append(gca)
        time.sleep(0.34)

    print("\n=== Datasets download summary ===", flush=True)
    print(f"  GCA assemblies requested  : {len(gcas)}", flush=True)
    print(f"  genomes written (.fna.gz) : {genome_ok}", flush=True)
    print(f"  GFFs written (.gff)       : {gff_ok}", flush=True)
    print(f"  GCAs with NO GFF          : {len(gff_missing)}", flush=True)
    if gff_missing:
        print("  (unannotated GenBank assemblies — need later local Bakta annotation):", flush=True)
        for g in gff_missing:
            print(f"    {g}", flush=True)


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Run the integration end to end.

    Parses args, builds the integration table + discrepancy report,
    writes both TSVs to ``--out-dir``, and prints the summary.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--table-s1", type=Path, default=TABLE_S1_DEFAULT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="cap to first N strains")
    parser.add_argument("--skip-70-gcf", action="store_true")
    parser.add_argument(
        "--download",
        action="store_true",
        help="also fetch each resolved GCA's GenBank genome + GFF via the NCBI Datasets CLI",
    )
    parser.add_argument(
        "--assemblies-dir",
        type=Path,
        default=None,
        help="with --download: output dir for <GCA>.fna.gz genomes (default: <out-dir>/related_lr/assemblies)",
    )
    parser.add_argument(
        "--gff-dir",
        type=Path,
        default=None,
        help="with --download: output dir for <GCA>.gff annotations (default: <out-dir>/related_lr/gff)",
    )
    parser.add_argument(
        "--datasets-cmd",
        type=str,
        default="datasets",
        help='NCBI Datasets CLI invocation (default: "datasets"; e.g. "micromamba run -n ncbi-datasets datasets")',
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="concurrent elink workers; the shared rate limiter still caps "
        "total throughput to NCBI's limit, so this only hides latency "
        "(use 1 to disable threading)",
    )
    parser.add_argument(
        "--augment",
        action="store_true",
        help="also write a metadata copy with the complete genomes integrated",
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="with --augment: overwrite --metadata in place after writing a "
        "timestamped <stem>.bak.<UTC>.tsv next to it (instead of a "
        ".with_norway_complete.tsv review copy)",
    )
    parser.add_argument(
        "--from-integration",
        type=Path,
        default=None,
        help="reuse an existing norway_tables1_integration.tsv and skip all "
        "NCBI calls (only meaningful with --augment)",
    )
    args = parser.parse_args(argv)

    out_dir = args.out_dir or args.metadata.parent / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    assemblies_dir = args.assemblies_dir or out_dir / "related_lr" / "assemblies"
    gff_dir = args.gff_dir or out_dir / "related_lr" / "gff"

    if args.from_integration:
        integ = pd.read_csv(args.from_integration, sep="\t", low_memory=False).fillna("")
        print(f"Loaded integration TSV: {args.from_integration}  rows={len(integ)}", flush=True)
        if args.augment:
            _write_augmented(integ, args.metadata, out_dir, write_back=args.write_back)
        if args.download:
            download_assemblies(integ, assemblies_dir, gff_dir, args.datasets_cmd)
        return 0

    auth, interval = eutils_auth()
    limiter = RateLimiter(interval)
    print(
        f"E-utilities auth: {'NCBI_API_KEY set (10 req/s)' if 'api_key' in auth else 'anon (3 req/s)'}"
        f"  workers={args.workers}",
        flush=True,
    )

    s1 = load_table_s1(args.table_s1, args.limit)
    print(f"Loaded Table S1: {args.table_s1}  strains={len(s1)}", flush=True)

    sets = load_metadata_sets(args.metadata)
    print(
        f"Metadata: {args.metadata}  norkab={len(sets['norkab'])}  run_accession={len(sets['run_accession'])}",
        flush=True,
    )

    gcf70: set[str] = set()
    if not args.skip_70_gcf:
        print("Fetching PRJEB74192 Complete-Genome GCF set ...", flush=True)
        gcf70 = get_70_complete_gcf_set(args.metadata)
        print(f"  70-complete GCF set size: {len(gcf70)}", flush=True)

    integ = build_rows(s1, sets, gcf70, auth, limiter, args.workers)

    integ_path = out_dir / "norway_tables1_integration.tsv"
    integ.to_csv(integ_path, sep="\t", index=False)
    print(f"\nWrote {integ_path}  rows={len(integ)}", flush=True)

    disc = discrepancy_rows(integ)
    disc_path = out_dir / "norway_tables1_discrepancies.tsv"
    disc.to_csv(disc_path, sep="\t", index=False)
    print(f"Wrote {disc_path}  rows={len(disc)}", flush=True)

    print_summary(integ, gcf70_used=not args.skip_70_gcf)

    if args.augment:
        _write_augmented(integ, args.metadata, out_dir, write_back=args.write_back)
    if args.download:
        download_assemblies(integ, assemblies_dir, gff_dir, args.datasets_cmd)
    return 0


def _write_augmented(integ: pd.DataFrame, metadata_path: Path, out_dir: Path, write_back: bool = False) -> None:
    """Run :func:`augment_metadata` and write the result + changes log.

    When *write_back* is true the augmented frame overwrites
    *metadata_path* in place, after copying the original to a timestamped
    ``<stem>.bak.<UTC-YYYYmmddTHHMMSS>.tsv`` alongside it. Otherwise it is
    written to a ``<stem>.with_norway_complete.tsv`` review copy.
    """
    augmented, changes = augment_metadata(integ, metadata_path)
    if write_back:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        bak_path = metadata_path.with_name(f"{metadata_path.stem}.bak.{ts}.tsv")
        shutil.copy2(metadata_path, bak_path)
        print(f"\nBacked up {metadata_path} → {bak_path}", flush=True)
        aug_path = metadata_path
    else:
        aug_path = out_dir.parent / f"{metadata_path.stem}.with_norway_complete.tsv"
    changes_path = out_dir / "norway_complete_changes.csv"
    augmented.to_csv(aug_path, sep="\t", index=False)
    changes.to_csv(changes_path, index=False)
    counts = changes["action"].value_counts().to_dict() if len(changes) else {}
    n_norway_refseq = int(
        ((augmented.get("is_complete_norway_genome") == True) & (augmented.get("is_refseq") == True)).sum()  # noqa: E712
    )
    print(
        f"\nWrote {aug_path}  rows={len(augmented)} (was {len(augmented) - counts.get('added_new_row', 0)})", flush=True
    )
    print(f"Wrote {changes_path}", flush=True)
    print(f"  actions: {counts}", flush=True)
    print(f"  is_complete_norway_genome & is_refseq rows now: {n_norway_refseq}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
