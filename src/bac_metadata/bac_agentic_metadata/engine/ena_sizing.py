"""Size an ENA project from the ENA Portal API (deterministic, no LLM).

For a ``study_accession`` we count the project's records and how many match the
``taxon_of_interest`` (by ``scientific_name``). This is the denominator for the later
``paper_coverage_for_taxon`` metric and lets us tell whether a candidate paper covers the
whole project or only a subsample.

We query ``result=read_run`` (not ``result=sample``): ENA reliably links *runs* to a study via
``study_accession`` but frequently does **not** link samples — e.g. ``PRJEB74192`` returns 0
records for ``result=sample`` yet 3,831 read_runs (3,261 distinct samples). We therefore fetch
read_runs carrying ``sample_accession`` + ``scientific_name`` and deduplicate to sample level.
Calibrated: ``PRJNA339843`` = 225 runs (the ENA browser count) / 224 distinct samples / 207
distinct *Klebsiella* samples. Assembly-only BioProjects with no portal-visible reads count as
zero and are flagged downstream.

Query construction + retry/backoff mirror ``pp.find_long_reads``; raw per-accession results
are cached so reruns are deterministic and offline.
"""

from __future__ import annotations

import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api/search"
RETRY_MAX = 3
RETRY_PAUSE = 10  # seconds between retries on rate limit

#: A project with at least this many distinct child studies is flagged as an umbrella accession
#: (one accession aggregating many substudies, e.g. PRJEB74192 "One Health Norway" with 9 child
#: studies). One "best paper" cannot describe an umbrella — the paper-finding stage must split it.
UMBRELLA_MIN_CHILD_STUDIES = 3


def matches_taxon(scientific_name: object, patterns: tuple[str, ...]) -> bool:
    """Return whether an ENA ``scientific_name`` belongs to the taxon of interest.

    Parameters
    ----------
    scientific_name
        Value of the ENA ``scientific_name`` field (may be NaN/empty).
    patterns
        Case-insensitive substrings; a match on any one counts.

    Returns
    -------
    bool
        True if the name matches any pattern.
    """
    if not isinstance(scientific_name, str):
        return False
    name = scientific_name.casefold()
    return any(p.casefold() in name for p in patterns)


def _ena_search(params: dict, *, timeout: int = 120) -> str | None:
    """Run one ENA Portal search with retry/backoff; return the raw response text or None."""
    for attempt in range(RETRY_MAX):
        try:
            resp = requests.get(ENA_PORTAL, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429:
                wait = RETRY_PAUSE * (attempt + 1)
                print(f"    [rate limit] waiting {wait}s ...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"    [HTTP {resp.status_code}] {params.get('query')} — giving up", file=sys.stderr)
                return None
        except requests.RequestException as exc:
            print(f"    [request error] {exc}", file=sys.stderr)
            time.sleep(5)
    print(f"    [failed after {RETRY_MAX} retries] {params.get('query')}", file=sys.stderr)
    return None


_READ_RUN_FIELDS = "run_accession,sample_accession,scientific_name,secondary_study_accession,study_title"


def _fetch_read_run_table(accession: str) -> pd.DataFrame | None:
    """Fetch the ``result=read_run`` table (run/sample/scientific_name + child-study fields)."""
    text = _ena_search(
        {
            "result": "read_run",
            "query": f'study_accession="{accession}"',
            "fields": _READ_RUN_FIELDS,
            "format": "tsv",
            "limit": 0,
        }
    )
    if text is None:
        return None
    if not text.strip():
        return pd.DataFrame(columns=_READ_RUN_FIELDS.split(","))
    return pd.read_csv(StringIO(text), sep="\t", dtype=str)


def study_title_and_description(accession: str, *, cache_dir: str | Path | None = None) -> dict:
    """Return the ENA study title + description for one project (cached).

    The EBI study title/description is one of the two evidence sources the grader uses (the other
    being the paper): for many accessions a whole-project value (e.g. "all hospital", "all from
    England") is stated there directly, which is the strongest support for a study-level grade.

    Parameters
    ----------
    accession
        ENA project accession (e.g. ``"PRJNA339843"``).
    cache_dir
        If given, the raw ``result=study`` TSV is cached at ``<cache_dir>/<accession>.study.tsv``
        and reused, making the result deterministic and offline.

    Returns
    -------
    dict
        Keys ``study_accession``, ``study_title``, ``study_description`` (empty strings when ENA
        has no value), and ``fetch_status`` (``"ok"`` / ``"study_failed"``).
    """
    table: pd.DataFrame | None = None
    cache_path: Path | None = None
    if cache_dir is not None:
        cache_path = Path(cache_dir) / f"{accession}.study.tsv"
        if cache_path.exists():
            table = pd.read_csv(cache_path, sep="\t", dtype=str)

    if table is None:
        text = _ena_search(
            {
                "result": "study",
                "query": f'study_accession="{accession}"',
                "fields": "study_accession,study_title,study_description",
                "format": "tsv",
                "limit": 0,
            }
        )
        if text is None:
            return {
                "study_accession": accession,
                "study_title": "",
                "study_description": "",
                "fetch_status": "study_failed",
            }
        if not text.strip():
            table = pd.DataFrame(columns=["study_accession", "study_title", "study_description"])
        else:
            table = pd.read_csv(StringIO(text), sep="\t", dtype=str)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(cache_path, sep="\t", index=False)

    if table.empty:
        return {
            "study_accession": accession,
            "study_title": "",
            "study_description": "",
            "fetch_status": "ok",
        }
    row = table.iloc[0]
    return {
        "study_accession": accession,
        "study_title": (row.get("study_title") or "") if isinstance(row.get("study_title"), str) else "",
        "study_description": (row.get("study_description") or "")
        if isinstance(row.get("study_description"), str)
        else "",
        "fetch_status": "ok",
    }


def _n_distinct(series: pd.Series) -> int:
    """Count distinct non-empty values in a (possibly absent) string series."""
    if series is None or len(series) == 0:
        return 0
    cleaned = series.fillna("").astype(str).str.strip()
    return int(cleaned[cleaned != ""].nunique())


def study_record_counts(
    accession: str,
    scientific_name_match: tuple[str, ...],
    *,
    cache_dir: str | Path | None = None,
) -> dict:
    """Return ENA record counts for one project, total and within the taxon of interest.

    Counts are derived from the ``read_run`` table and deduplicated to sample level (see the
    module docstring for why samples are not queried directly).

    Parameters
    ----------
    accession
        ENA project accession (e.g. ``"PRJNA339843"``).
    scientific_name_match
        Substrings identifying the taxon of interest (see :func:`matches_taxon`).
    cache_dir
        If given, the raw ``read_run`` TSV is cached at ``<cache_dir>/<accession>.read_run.tsv``
        and reused on subsequent runs, making the result deterministic and offline.

    Returns
    -------
    dict
        Keys: ``study_accession``, ``ena_total_samples`` (distinct samples), ``ena_total_runs``,
        ``ena_taxon_samples`` (distinct taxon samples), ``by_scientific_name`` (distinct-sample
        counts per taxon name), ``n_child_studies`` (distinct ``secondary_study_accession``),
        ``umbrella_suspected`` (>= :data:`UMBRELLA_MIN_CHILD_STUDIES` child studies),
        ``fetch_status`` (``"ok"`` / ``"read_run_failed"``).
    """
    table: pd.DataFrame | None = None
    cache_path: Path | None = None
    if cache_dir is not None:
        cache_path = Path(cache_dir) / f"{accession}.read_run.tsv"
        if cache_path.exists():
            table = pd.read_csv(cache_path, sep="\t", dtype=str)

    if table is None:
        table = _fetch_read_run_table(accession)
        if table is None:
            return {
                "study_accession": accession,
                "ena_total_samples": pd.NA,
                "ena_total_runs": pd.NA,
                "ena_taxon_samples": pd.NA,
                "by_scientific_name": {},
                "n_child_studies": pd.NA,
                "umbrella_suspected": pd.NA,
                "fetch_status": "read_run_failed",
            }
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(cache_path, sep="\t", index=False)

    sample_col = table.get("sample_accession", pd.Series(dtype=str)).fillna("")
    sci_col = table.get("scientific_name", pd.Series(dtype=str))
    taxon_mask = sci_col.apply(lambda v: matches_taxon(v, scientific_name_match))

    total_samples = sample_col[sample_col != ""].nunique()
    taxon_samples = sample_col[(sample_col != "") & taxon_mask].nunique()
    # Distinct sample count per taxon scientific name.
    by_name = (
        table.loc[taxon_mask & (sample_col != "")]
        .groupby("scientific_name")["sample_accession"]
        .nunique()
        .to_dict()
    )

    n_child_studies = _n_distinct(table.get("secondary_study_accession"))
    return {
        "study_accession": accession,
        "ena_total_samples": int(total_samples),
        "ena_total_runs": int(len(table)),
        "ena_taxon_samples": int(taxon_samples),
        "by_scientific_name": {k: int(v) for k, v in by_name.items()},
        "n_child_studies": n_child_studies,
        "umbrella_suspected": bool(n_child_studies >= UMBRELLA_MIN_CHILD_STUDIES),
        "fetch_status": "ok",
    }
