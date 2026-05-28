#!/usr/bin/env python3
"""Build metadata_v2: unified assembly-keyed cohort (Phase G.1).

Reads metadata_v1 + ``lra_final_list.tsv`` + ``lra_discovery.tsv`` and emits
``metadata_v2_all_samples_and_columns.tsv`` — the canonical metadata table
where:

- ``Sample`` is the **assembly key**: GCF/GCA where an LRA exists in
  ``lra_final_list.tsv``, SR BioSample where not.
- ``lra_final_list`` (bool) is the headline quality flag. ``is_refseq`` is
  dropped (encoded in ``Sample.startswith("GCF_")``).
- ``is_complete`` / ``is_hybrid`` / ``is_reference_genome`` (bool) are
  NCBI-derived per-row flags (G.7) carried from ``lra_final_list.tsv`` onto
  LRA-bearing rows; False on SR rows. ``assembly_level`` is now collected
  fresh from NCBI (``lra_ncbi_assembly_meta.tsv``), so ``is_complete`` is
  reliable and no longer dropped.
- LRA-derived columns sit alongside SR-derived columns (``lra_gca``,
  ``lra_gcf``, ``lra_assembly_file``, ``lra_gff_file``,
  ``lr_run_accession``, ``lr_instrument_platform``, ``lr_instrument_model``,
  ``sr_biosample``).
- The 957 currently-duplicated SR + is_refseq pairs collapse to one row.
- ``kleborate_needs_recall`` + ``isescan_needs_recall`` flag LRA rows whose
  Kleborate / ISEScan values were called on the SR assembly and need
  re-calling on the LRA (cleared by Phase G.2).

Pipeline order:

  0. **Pre-cleanup** — drop ~2,576 LR-appended duplicate rows that v1
     accumulated when LR data was first wired in (``is_refseq=False`` rows
     whose ``related_sr_accession`` points back at an SR partner). The
     LR-run platform info on those rows is not carried into v2; if needed
     it can be merged from ``related_lr_run_accessions.csv``.
  1. **Match LRAs to metadata rows** — three priority rules (Sample
     accession, related_lr_run_accession, related_lr_accession assembly).
  2. **Overlay LRA columns** on every matched row + flip ``Sample`` to the
     LRA's ``scoring_accession``.
  3. **Merge** the 957 SR + is_refseq pairs (copy SR metadata onto the
     refseq row, drop the SR row).
  4. **Rename + drop** legacy columns (``is_refseq``).
  5. **Ingest orphan LRAs** — LRAs with no metadata row to attach to
     (~124, almost all Norway-sourced) are appended as pure-LR rows,
     enriched from ``Norway_Complete_Genomes_Fig1.xlsx`` (host, source,
     collection_year) and run through ``metadata_curation``'s parse +
     categorise functions. country defaults to "Norway".

The orphan check is now informational: any LRA whose BioSample isn't in
Norway Table S1 is still ingested (with NaN for host/source/date) and
also recorded in ``metadata_v2_orphan_lras.tsv``.

Usage::

    uv run python -m bac_metadata.pp.build_metadata_v2 --dry-run
    uv run python -m bac_metadata.pp.build_metadata_v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─── PATHS ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V1   = DATA_ROOT / "david/final/metadata_final_curated_all_samples_and_columns.tsv"
DEFAULT_DISCOVERY     = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lr_discovery/lra_discovery.tsv"
DEFAULT_FINAL_SET     = DATA_ROOT / "david/processed/complete_vs_sr_genomes/lra_final_list.tsv"
DEFAULT_LR_RUNS_CSV   = DATA_ROOT / "david/final/related_lr_run_accessions.csv"
DEFAULT_TABLE_S1      = DATA_ROOT / "david/raw/Norway_Complete_Genomes_Fig1.xlsx"
DEFAULT_OUT_DIR       = DATA_ROOT / "david/final"

# ─── REGEX ────────────────────────────────────────────────────────────────────

_ACC_RE = re.compile(r"(GC[AF]_\d+\.\d+)")
_RUN_RE = re.compile(r"^(?:SRR|ERR|DRR)\d+$")

# ─── COLUMN POLICY ────────────────────────────────────────────────────────────

# New columns added by metadata_v2. Order matters for the output header.
NEW_LRA_COLUMNS = [
    "lra_final_list",
    "lra_gca",
    "lra_gcf",
    "is_complete",
    "is_hybrid",
    "is_reference_genome",
    "lra_assembly_file",
    "lra_gff_file",
    "lr_run_accession",
    "lr_instrument_platform",
    "lr_instrument_model",
    "sr_biosample",
    "kleborate_needs_recall",
    "isescan_needs_recall",
]

# NCBI-derived per-row flags carried from lra_final_list onto LRA-bearing rows.
LRA_FLAG_COLUMNS = ["is_complete", "is_hybrid", "is_reference_genome"]

# Columns dropped wholesale (replaced by the new schema). is_complete is NO
# LONGER dropped — it is now NCBI-authoritative (G.7) and carried from
# lra_final_list. is_complete_norway_genome is intentionally retained (still
# consumed by merge_norway_pairs_into_v2 + bac_panaroo/bac_isescan; its removal
# is deferred to the G.5 caller sweep).
DROPPED_COLUMNS = ["is_refseq"]

# Existing columns renamed.
RENAMED_COLUMNS = {
    "related_lr_accession": "_legacy_related_lr_accession",
    "related_sr_accession": "sr_run_accession",
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _bare(acc: object) -> str:
    """Return the version-stripped bare accession, or ``''`` if no match."""
    if acc is None or (isinstance(acc, float) and np.isnan(acc)):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1).split(".", 1)[0] if m else ""


def _versioned(acc: object) -> str:
    """Return the versioned accession (e.g. GCF_X.Y), or ``''`` if no match."""
    if acc is None or (isinstance(acc, float) and np.isnan(acc)):
        return ""
    m = _ACC_RE.search(str(acc))
    return m.group(1) if m else ""


def _coerce_bool(series: pd.Series) -> pd.Series:
    """Coerce a string-or-bool series to clean bools (NaN → False)."""
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _looks_like_run_accession(value: str) -> bool:
    """SRR/ERR/DRR run accession pattern."""
    return bool(_RUN_RE.match(str(value)))


# ─── STEP 0: PRE-CLEANUP ──────────────────────────────────────────────────────

def drop_lr_appended_rows(meta: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop the ~2,576 LR-appended duplicate rows from v1.

    When LR data was first wired into metadata_v1, two changes happened:

    1. SR rows got ``related_lr_accession`` populated, pointing at a found
       LR run.
    2. A *second row was appended at the bottom of v1* for each such SR
       row, carrying the LR-run platform info. Both rows share
       ``sample_accession`` (the same BioSample); the appended row has
       ``related_sr_accession`` pointing back at the SR row's
       ``run_accession``.

    These appended rows are pure duplicates by BioSample and we don't need
    the LR-run platform info in v2 — if needed later it can be merged
    from ``related_lr_run_accessions.csv``.

    The filter ``is_refseq == False AND related_sr_accession.notna()``
    isolates them (is_refseq=True rows also have ``related_sr_accession``
    populated, but those are handled later by ``find_sr_refseq_pairs``).

    Returns (cleaned_meta, n_dropped).
    """
    if "related_sr_accession" not in meta.columns or "is_refseq" not in meta.columns:
        return meta.reset_index(drop=True), 0

    is_refseq = _coerce_bool(meta["is_refseq"])
    sr_acc_str = meta["related_sr_accession"].astype(str).fillna("")
    has_sr = (sr_acc_str != "") & (sr_acc_str.str.lower() != "nan")
    drop_mask = (~is_refseq) & has_sr
    n_dropped = int(drop_mask.sum())
    return meta.loc[~drop_mask].reset_index(drop=True), n_dropped


# ─── MATCH LOGIC ──────────────────────────────────────────────────────────────

def match_lras_to_metadata(disc: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """For each discovery row, find its target metadata row index (or NaN if orphan).

    Match priority (each LRA → at most one metadata row):

      1. ``disc.scoring_accession`` (bare) matches an accession parsed from
         ``meta.Sample`` (covers the 3,911 is_refseq rows).
      2. ``disc.related_lr_run_accession`` matches ``meta.related_lr_accession``
         when the metadata value is a run accession (SRR/ERR/DRR).
      3. ``disc.scoring_accession`` (bare) matches the accession parsed from
         ``meta.related_lr_accession`` when the metadata value is itself a
         GCF/GCA assembly accession.

    Returns a DataFrame with columns ``scoring_accession, target_idx, match_via``.
    """
    meta = meta.reset_index(drop=False).rename(columns={"index": "_meta_idx"})

    # Pre-compute lookup dictionaries on the metadata side.
    meta["_sample_bare"] = meta["Sample"].map(_bare)
    sample_to_idx = (
        meta.loc[meta["_sample_bare"] != "", ["_sample_bare", "_meta_idx"]]
        .drop_duplicates("_sample_bare")
        .set_index("_sample_bare")["_meta_idx"]
        .to_dict()
    )

    related_lr_str = meta["related_lr_accession"].astype(str).fillna("").replace("nan", "")
    # Two views of related_lr_accession: run-accession form and assembly-accession form.
    run_form_mask  = related_lr_str.map(_looks_like_run_accession)
    rel_lr_run_to_idx = (
        meta.loc[run_form_mask, ["related_lr_accession", "_meta_idx"]]
        .drop_duplicates("related_lr_accession")
        .set_index("related_lr_accession")["_meta_idx"]
        .to_dict()
    )
    meta["_rel_lr_bare"] = related_lr_str.map(_bare)
    rel_lr_acc_to_idx = (
        meta.loc[(~run_form_mask) & (meta["_rel_lr_bare"] != ""), ["_rel_lr_bare", "_meta_idx"]]
        .drop_duplicates("_rel_lr_bare")
        .set_index("_rel_lr_bare")["_meta_idx"]
        .to_dict()
    )

    results = []
    for _, row in disc.iterrows():
        acc_versioned = str(row["scoring_accession"]).strip()
        acc_bare = _bare(acc_versioned)
        lr_run = str(row.get("related_lr_run_accession", "")).strip()

        # Priority 1: accession ↔ metadata.Sample
        idx = sample_to_idx.get(acc_bare)
        if idx is not None:
            results.append({"scoring_accession": acc_versioned, "target_idx": int(idx), "match_via": "sample_accession"})
            continue

        # Priority 2: run accession ↔ metadata.related_lr_accession (run form)
        if lr_run and lr_run != "nan":
            idx = rel_lr_run_to_idx.get(lr_run)
            if idx is not None:
                results.append({"scoring_accession": acc_versioned, "target_idx": int(idx), "match_via": "related_lr_run_accession"})
                continue

        # Priority 3: accession ↔ metadata.related_lr_accession (assembly form)
        idx = rel_lr_acc_to_idx.get(acc_bare)
        if idx is not None:
            results.append({"scoring_accession": acc_versioned, "target_idx": int(idx), "match_via": "related_lr_accession_assembly"})
            continue

        # Orphan: no metadata match.
        results.append({"scoring_accession": acc_versioned, "target_idx": np.nan, "match_via": "orphan"})

    return pd.DataFrame(results)


def find_sr_refseq_pairs(meta: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame ``(refseq_idx, sr_idx)`` of paired is_refseq + SR rows.

    Pair via ``meta[is_refseq].related_sr_accession ↔ meta[~is_refseq].run_accession``.
    Expected: 957 pairs.
    """
    is_refseq = _coerce_bool(meta["is_refseq"])
    refseq = meta[is_refseq & meta["related_sr_accession"].notna() & (meta["related_sr_accession"] != "")].copy()
    sr_lookup = (
        meta.loc[~is_refseq & meta["run_accession"].notna(), ["run_accession"]]
        .reset_index()
        .drop_duplicates("run_accession")
        .set_index("run_accession")["index"]
        .to_dict()
    )

    pairs = []
    for refseq_idx, row in refseq.iterrows():
        sr_run = str(row["related_sr_accession"]).strip()
        sr_idx = sr_lookup.get(sr_run)
        if sr_idx is not None:
            pairs.append({"refseq_idx": int(refseq_idx), "sr_idx": int(sr_idx), "sr_run": sr_run})
    return pd.DataFrame(pairs)


# ─── ORPHAN-LRA INGESTION (G.1.1) ─────────────────────────────────────────────

def load_norway_table_s1(path: Path) -> pd.DataFrame:
    """Load Norway Table S1 via the shared loader in ``norway_tables1_integrate``.

    Returns the renamed frame with columns ``strain, biosample, host, source,
    collection_year, illumina_acc, ont_acc`` (plus a few others). Empty
    DataFrame if the file can't be read.
    """
    if not path.exists():
        print(f"Norway Table S1 not found at {path} — orphan ingestion will skip enrichment.")
        return pd.DataFrame()
    from bac_data.lr_data.norway_tables1_integrate import load_table_s1
    return load_table_s1(path, limit=None)


def ingest_orphan_lras(
    orphans: pd.DataFrame,
    disc: pd.DataFrame,
    table_s1_df: pd.DataFrame,
    lr_runs: pd.DataFrame,
    v2_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build pure-LR scaffold rows for orphan LRAs (Phase G.1.1).

    Each orphan becomes one new row in v2:
      - ``Sample`` = the LRA's ``scoring_accession`` (GCF/GCA).
      - ``sample_accession`` = the orphan's ``Sample`` from discovery
        (which carries the BioSample for Norway-sourced rows).
      - ``host``, ``isolation_source``, ``collection_date`` (=year) pulled
        from Norway Table S1 by BioSample where available.
      - ``country`` = "Norway" constant (Norway Complete Genomes dataset).
      - Curation parse/categorise functions run in the order documented in
        ``metadata_curation.py``: isolation_source → country → host → date.
      - ``lra_*`` and ``lr_*`` columns populated from discovery + lr_runs.
      - SR-side columns (``run_accession``, ``instrument_platform`` …) NaN.

    Returns ``(scaffold_df, residual_df)``. ``residual_df`` is the subset
    whose BioSample wasn't in Norway Table S1 — still ingested into v2 but
    written to ``metadata_v2_orphan_lras.tsv`` for visibility.
    """
    if orphans.empty:
        return pd.DataFrame(columns=v2_columns), pd.DataFrame()

    # Pull the discovery columns we need onto the orphan list.
    disc_cols = [c for c in (
        "scoring_accession", "GCA", "GCF", "Sample", "fasta_on_disk", "gff_on_disk",
        "related_lr_run_accession", "source_norway",
        "is_complete", "is_hybrid", "is_reference_genome",
    ) if c in disc.columns]
    o = orphans[["scoring_accession"]].drop_duplicates().merge(
        disc[disc_cols], on="scoring_accession", how="left",
    )

    # Optional: merge LR-platform info.
    if lr_runs is not None and not lr_runs.empty:
        keep = ["run_accession"]
        for opt in ("instrument_platform", "instrument_model"):
            if opt in lr_runs.columns:
                keep.append(opt)
        runs_slim = lr_runs[keep].rename(columns={
            "run_accession": "related_lr_run_accession",
            "instrument_platform": "lr_instrument_platform",
            "instrument_model": "lr_instrument_model",
        }).drop_duplicates("related_lr_run_accession")
        o = o.merge(runs_slim, on="related_lr_run_accession", how="left")
    for col in ("lr_instrument_platform", "lr_instrument_model"):
        if col not in o.columns:
            o[col] = pd.NA

    # Join Norway Table S1 by BioSample (orphan.Sample = BioSample for Norway).
    enrich_cols = ["host", "source", "collection_year"]
    if not table_s1_df.empty:
        s1 = table_s1_df.copy()
        if "biosample" in s1.columns:
            s1 = s1.rename(columns={"biosample": "_biosample"})
            keep_in = ["_biosample"] + [c for c in enrich_cols if c in s1.columns]
            s1 = s1[keep_in].drop_duplicates("_biosample")
            o = o.merge(s1, left_on="Sample", right_on="_biosample", how="left").drop(
                columns=["_biosample"], errors="ignore"
            )
    for col in enrich_cols:
        if col not in o.columns:
            o[col] = pd.NA

    # Residual = orphans not enriched by Norway Table S1.
    residual = o[o["host"].isna() & o["source"].isna() & o["collection_year"].isna()].copy()

    # Build the scaffold frame with v2's columns.
    n = len(o)
    scaffold = pd.DataFrame({col: [pd.NA] * n for col in v2_columns})

    scaffold["Sample"] = o["scoring_accession"].to_numpy()
    if "sample_accession" in scaffold.columns:
        scaffold["sample_accession"] = o["Sample"].to_numpy()  # = the BioSample
    if "host" in scaffold.columns:
        scaffold["host"] = o["host"].to_numpy()
    if "isolation_source" in scaffold.columns:
        scaffold["isolation_source"] = o["source"].to_numpy()
    if "country" in scaffold.columns:
        scaffold["country"] = "Norway"
    if "collection_date" in scaffold.columns:
        year_series = o["collection_year"].astype("string").fillna("")
        scaffold["collection_date"] = year_series.where(year_series != "", pd.NA).to_numpy()

    # LRA-side columns.
    if "lra_gca" in scaffold.columns and "GCA" in o.columns:
        scaffold["lra_gca"] = o["GCA"].to_numpy()
    if "lra_gcf" in scaffold.columns and "GCF" in o.columns:
        scaffold["lra_gcf"] = o["GCF"].to_numpy()
    if "lra_assembly_file" in scaffold.columns and "fasta_on_disk" in o.columns:
        scaffold["lra_assembly_file"] = o["fasta_on_disk"].to_numpy()
    if "lra_gff_file" in scaffold.columns and "gff_on_disk" in o.columns:
        scaffold["lra_gff_file"] = o["gff_on_disk"].to_numpy()
    if "lr_run_accession" in scaffold.columns and "related_lr_run_accession" in o.columns:
        scaffold["lr_run_accession"] = o["related_lr_run_accession"].to_numpy()
    if "lr_instrument_platform" in scaffold.columns:
        scaffold["lr_instrument_platform"] = o["lr_instrument_platform"].to_numpy()
    if "lr_instrument_model" in scaffold.columns:
        scaffold["lr_instrument_model"] = o["lr_instrument_model"].to_numpy()
    scaffold["lra_final_list"] = True
    scaffold["kleborate_needs_recall"] = True
    scaffold["isescan_needs_recall"] = True
    # NCBI-derived flags carried from disc (orphans are all in lra_final_list).
    for _f in ("is_complete", "is_hybrid", "is_reference_genome"):
        if _f in o.columns and _f in scaffold.columns:
            scaffold[_f] = o[_f].fillna(False).to_numpy()
    if "_was_v1_is_refseq" in v2_columns:
        scaffold["_was_v1_is_refseq"] = False  # new rows, not from v1

    # Run curation. Order matters: parse_host has documented side-effects on
    # country/isolation_source so it must come *after* those have been parsed
    # + categorised.
    from bac_metadata.pp.metadata_curation import (
        categorise_host,
        categorise_isolation_source,
        categorise_region,
        parse_collection_date,
        parse_country,
        parse_host,
        parse_isolation_source,
    )

    scaffold = parse_isolation_source(scaffold, verbose=False)
    scaffold = categorise_isolation_source(scaffold, verbose=False)
    scaffold = parse_country(scaffold, verbose=False)
    scaffold = categorise_region(scaffold, verbose=False)
    scaffold = parse_host(scaffold, verbose=False)
    scaffold = categorise_host(scaffold, verbose=False)
    scaffold = parse_collection_date(scaffold, verbose=False)

    # Align scaffold columns to v2 (curation may have added new columns —
    # carry them through; v2 will gain them via the concat).
    extra_cols = [c for c in scaffold.columns if c not in v2_columns]
    final_cols = list(v2_columns) + extra_cols
    for col in final_cols:
        if col not in scaffold.columns:
            scaffold[col] = pd.NA
    scaffold = scaffold[final_cols]

    return scaffold, residual


# ─── METADATA_V2 BUILD ────────────────────────────────────────────────────────

def build_metadata_v2(
    meta: pd.DataFrame,
    disc: pd.DataFrame,
    final_set_accs: set[str],
    lr_runs: pd.DataFrame,
    table_s1_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Apply the merge + Sample swap + orphan ingestion. Return (v2, residual_orphans, stats)."""
    stats: dict = {}

    # ── Step 0: pre-cleanup — drop ~3,078 LR-appended duplicate rows.
    meta, n_dropped = drop_lr_appended_rows(meta)
    stats["dropped_lr_appended_rows"] = n_dropped

    v2 = meta.copy()
    # Tracking column for v1↔v2 diagnostics. Survives Step 5 (rename/drop) so
    # the cross-table in _print_v2_diagnostics still works after Sample is
    # flipped to scoring_accession. Dropped just before write.
    if "is_refseq" in v2.columns:
        v2["_was_v1_is_refseq"] = _coerce_bool(v2["is_refseq"])
    else:
        v2["_was_v1_is_refseq"] = False

    # Pre-resolve the LRA-side join columns from the discovery TSV.
    disc = disc.copy()
    # gff_on_disk is a newer discovery column; default it so v2 still builds
    # against an older discovery TSV (lra_gff_file just stays empty there).
    if "gff_on_disk" not in disc.columns:
        disc["gff_on_disk"] = ""
    disc["_scoring_bare"] = disc["scoring_accession"].map(_bare)
    disc["_lra_final_list"] = disc["scoring_accession"].isin(final_set_accs)

    # Pull LR-run platform info from related_lr_run_accessions.csv.
    if lr_runs is not None and not lr_runs.empty:
        keep_cols = ["run_accession"]
        for opt in ("instrument_platform", "instrument_model"):
            if opt in lr_runs.columns:
                keep_cols.append(opt)
        runs_slim = lr_runs[keep_cols].copy()
        runs_slim = runs_slim.rename(columns={
            "run_accession": "related_lr_run_accession",
            "instrument_platform": "lr_instrument_platform",
            "instrument_model": "lr_instrument_model",
        })
        disc = disc.merge(runs_slim, on="related_lr_run_accession", how="left")
    # Guarantee both columns exist (lr_runs CSV often lacks instrument_model).
    for col in ("lr_instrument_platform", "lr_instrument_model"):
        if col not in disc.columns:
            disc[col] = pd.NA

    # ── 1. Match each LRA to a metadata row.
    matches = match_lras_to_metadata(disc, meta)
    stats["match_counts"] = matches["match_via"].value_counts().to_dict()
    orphans = matches[matches["match_via"] == "orphan"].copy()
    if not orphans.empty:
        orphans = orphans.merge(disc[["scoring_accession", "GCA", "GCF", "Sample",
                                       "related_lr_run_accession", "source_audit",
                                       "source_norway", "source_refseq_metadata"]],
                                 on="scoring_accession", how="left")
    stats["n_orphans"] = len(orphans)

    # Drop orphan rows from the match table for the merge pass.
    matched = matches[matches["match_via"] != "orphan"].copy()
    matched["target_idx"] = matched["target_idx"].astype(int)
    # Bring discovery columns onto matched.
    matched = matched.merge(
        disc[[
            "scoring_accession", "GCA", "GCF", "fasta_on_disk", "gff_on_disk",
            "related_lr_run_accession", "_lra_final_list",
            "lr_instrument_platform", "lr_instrument_model",
            *LRA_FLAG_COLUMNS,
        ]],
        on="scoring_accession", how="left",
    )

    # ── 2. Add the new column scaffolding to v2 (defaults).
    for col in NEW_LRA_COLUMNS:
        if col not in v2.columns:
            v2[col] = pd.NA
    v2["lra_final_list"] = False
    v2["kleborate_needs_recall"] = False
    v2["isescan_needs_recall"] = False
    # NCBI-derived flags default False everywhere (incl. SR rows + any legacy v1
    # is_complete values); overlaid True on matched LRA rows below.
    for _f in LRA_FLAG_COLUMNS:
        v2[_f] = False

    # ── 3. Apply LRA overlay on every matched row.
    overlay_cols = {
        "GCA": "lra_gca",
        "GCF": "lra_gcf",
        "fasta_on_disk": "lra_assembly_file",
        "gff_on_disk": "lra_gff_file",
        "related_lr_run_accession": "lr_run_accession",
        "lr_instrument_platform": "lr_instrument_platform",
        "lr_instrument_model": "lr_instrument_model",
        "is_complete": "is_complete",
        "is_hybrid": "is_hybrid",
        "is_reference_genome": "is_reference_genome",
    }
    for _, m in matched.iterrows():
        idx = m["target_idx"]
        # Save the original Sample to sr_biosample (only if Sample is a BioSample form).
        orig_sample = str(v2.at[idx, "Sample"])
        if not orig_sample.startswith(("GCF_", "GCA_")):
            v2.at[idx, "sr_biosample"] = orig_sample
        # Flip Sample to the LRA's scoring accession.
        v2.at[idx, "Sample"] = m["scoring_accession"]
        # Populate the lra/lr columns from the discovery row.
        for src, dst in overlay_cols.items():
            val = m.get(src, "")
            if pd.notna(val) and str(val) != "":
                v2.at[idx, dst] = val
        v2.at[idx, "lra_final_list"] = bool(m["_lra_final_list"])
        v2.at[idx, "kleborate_needs_recall"] = True
        v2.at[idx, "isescan_needs_recall"] = True

    # ── 4. Merge the 957 SR + is_refseq duplicate pairs (drop SR rows).
    pairs = find_sr_refseq_pairs(meta)
    stats["n_sr_refseq_pairs"] = len(pairs)
    # For each pair, copy SR metadata onto the refseq row + mark SR row for removal.
    sr_indices_to_drop = []
    sr_only_cols = [
        "sample_accession", "run_accession", "instrument_platform", "instrument_model",
        "study_accession", "center_name", "host", "country", "isolation_source",
        "collection_date", "scientific_name", "tax_id",
    ]
    sr_only_cols = [c for c in sr_only_cols if c in meta.columns]
    for _, pair in pairs.iterrows():
        ridx, sidx = pair["refseq_idx"], pair["sr_idx"]
        for col in sr_only_cols:
            v_refseq = v2.at[ridx, col]
            v_sr = v2.at[sidx, col]
            # Only copy if the refseq side is empty / NaN.
            if pd.isna(v_refseq) or str(v_refseq) in ("", "nan"):
                v2.at[ridx, col] = v_sr
        # Save the SR BioSample for the join-back in sr_shadow.
        if pd.isna(v2.at[ridx, "sr_biosample"]) or str(v2.at[ridx, "sr_biosample"]) in ("", "nan"):
            v2.at[ridx, "sr_biosample"] = v2.at[sidx, "Sample"]
        sr_indices_to_drop.append(int(sidx))
    if sr_indices_to_drop:
        v2 = v2.drop(index=sr_indices_to_drop)

    # ── 5. Column renames + drops.
    for old, new in RENAMED_COLUMNS.items():
        if old in v2.columns and new not in v2.columns:
            v2 = v2.rename(columns={old: new})
    for col in DROPPED_COLUMNS:
        if col in v2.columns:
            v2 = v2.drop(columns=[col])
    # The legacy related_lr_accession column had heterogeneous content
    # (sometimes a run accession, sometimes an assembly accession). After
    # rename it lives at `_legacy_related_lr_accession`. lr_run_accession is
    # the canonical LR-run column going forward.

    # ── 6. Ingest orphan LRAs as new pure-LR rows (G.1.1).
    # Only ingest orphans that are in lra_final_list (the accepted cohort).
    accepted_orphans = orphans[orphans["scoring_accession"].isin(final_set_accs)].copy() if len(orphans) else orphans
    stats["n_orphans_in_final_set"] = len(accepted_orphans)
    residual = pd.DataFrame()
    if not accepted_orphans.empty and table_s1_df is not None:
        scaffold, residual = ingest_orphan_lras(
            accepted_orphans, disc, table_s1_df, lr_runs, list(v2.columns),
        )
        if not scaffold.empty:
            # Align columns: curation may have added columns; let pd.concat union.
            v2 = pd.concat([v2, scaffold], ignore_index=True, sort=False)
        stats["n_orphans_ingested"] = len(scaffold)
        stats["n_orphans_residual"] = len(residual)
    else:
        stats["n_orphans_ingested"] = 0
        stats["n_orphans_residual"] = 0

    # ── 7. Finalize: validate Sample uniqueness on LRA-bearing rows, sort, etc.
    stats["v2_rows"] = len(v2)
    stats["lra_final_list_count"] = int(_coerce_bool(v2["lra_final_list"]).sum())
    # metadata_v1 already has many duplicate Sample values for SR-only rows (same
    # BioSample, multiple ENA runs). Count them separately from LRA-bearing
    # duplicates: only the LRA case is a logic bug.
    sample_str = v2["Sample"].astype(str)
    is_lra_sample = sample_str.str.startswith(("GCF_", "GCA_"))
    stats["sample_duplicate_count_total"] = int(v2["Sample"].duplicated().sum())
    lra_rows = v2[is_lra_sample]
    stats["sample_duplicate_count_lra"] = int(lra_rows["Sample"].duplicated().sum())
    stats["paired_sr_lra_count"] = int(
        (_coerce_bool(v2["lra_final_list"]) & v2.get("run_accession", pd.Series([pd.NA] * len(v2))).notna()).sum()
    )

    v2 = v2.sort_values("Sample", kind="stable").reset_index(drop=True)
    return v2, residual, stats


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _print_v2_diagnostics(v2: pd.DataFrame, v1_meta: pd.DataFrame) -> None:
    """Verification breakdowns: row categories + v1↔v2 column delta + sample rows.

    Computes the SR-only / LR-only / paired counts, breaks them down by
    ``kpsc_final_list`` if present, cross-tabulates v2's ``lra_final_list``
    against v1's ``is_refseq`` flag (joined by the LR-bearing row's
    sample_accession → v1 row), and shows a few sample rows from each
    category so the headline column changes (old kept, old dropped, new
    added) are easy to eyeball.
    """
    print("\n=== v2 row breakdown ===")
    lra = _coerce_bool(v2["lra_final_list"])
    run_acc_str = v2.get("run_accession", pd.Series([pd.NA] * len(v2))).astype(str).fillna("")
    has_sr_run = (run_acc_str != "") & (run_acc_str.str.lower() != "nan")

    sr_only = int(((~lra) & has_sr_run).sum())
    lr_only = int((lra & ~has_sr_run).sum())
    both    = int((lra & has_sr_run).sum())
    neither = int(((~lra) & ~has_sr_run).sum())

    print(f"  SR only (no LRA)            : {sr_only:>8,}")
    print(f"  LR only (pure-LR, no SR)    : {lr_only:>8,}")
    print(f"  Paired SR+LR                : {both:>8,}")
    print(f"  Neither (no SR run, no LRA) : {neither:>8,}")
    print(f"  TOTAL                       : {len(v2):>8,}")

    if "kpsc_final_list" in v2.columns:
        kpsc = _coerce_bool(v2["kpsc_final_list"])
        print("\n=== Breakdown by kpsc_final_list ===")
        for label, mask in (
            ("SR only (no LRA)        ", (~lra) & has_sr_run),
            ("LR only (pure-LR)       ", lra & ~has_sr_run),
            ("Paired SR+LR            ", lra & has_sr_run),
        ):
            n_kpsc = int((mask & kpsc).sum())
            n_total = int(mask.sum())
            print(f"  {label}: kpsc_final_list True {n_kpsc:>7,} / {n_total:>7,}")
        print(f"  kpsc_final_list True (any)  : {int(kpsc.sum()):>7,} / {len(v2):>7,}")

    if "_was_v1_is_refseq" in v2.columns:
        was_refseq = _coerce_bool(v2["_was_v1_is_refseq"])
        print("\n=== v2.lra_final_list × v1.is_refseq cross-table ===")
        print("                          v1.is_refseq=True    v1.is_refseq=False")
        for lflag, label in ((True, "v2.lra_final_list=True "), (False, "v2.lra_final_list=False")):
            mask = (lra == lflag)
            n_true  = int((mask & was_refseq).sum())
            n_false = int((mask & ~was_refseq).sum())
            print(f"  {label}: {n_true:>14,}   {n_false:>14,}")
        v2_refseq = int(was_refseq.sum())
        print(f"  v1.is_refseq=True rows surviving into v2: {v2_refseq:,}  (v1 had {int(_coerce_bool(v1_meta['is_refseq']).sum()):,})")

    print("\n=== Column delta v1 → v2 ===")
    v1_cols = set(v1_meta.columns)
    # Internal tracking columns (prefixed with _) aren't part of the public schema.
    v2_cols = {c for c in v2.columns if not c.startswith("_")}
    dropped = sorted(v1_cols - v2_cols)
    added   = sorted(v2_cols - v1_cols)
    kept    = sorted(v1_cols & v2_cols)
    print(f"  dropped from v1 ({len(dropped)}): {dropped}")
    print(f"  added in v2     ({len(added)}): {added}")
    print(f"  kept            ({len(kept)} cols; first 20): {kept[:20]} ...")

    # "Neither" rows: no SR run AND not in lra_final_list. Usually is_refseq=True
    # rows whose GCF/GCA wasn't in lra_final_list (CheckM2-rejected, suppressed, etc.).
    neither_mask = (~lra) & ~has_sr_run
    if int(neither_mask.sum()) > 0 and "_was_v1_is_refseq" in v2.columns:
        n_was_refseq = int((neither_mask & _coerce_bool(v2["_was_v1_is_refseq"])).sum())
        print(f"\n  'Neither' breakdown (no SR run, no LRA): {int(neither_mask.sum()):,}")
        print(f"    of which v1 was is_refseq=True (LRA rejected by CheckM2 etc.): {n_was_refseq:,}")
        print(f"    other (no SR run, not is_refseq):                              {int(neither_mask.sum()) - n_was_refseq:,}")

    print("\n=== Sample rows: 3 per category ===")
    show_cols = [c for c in (
        "Sample", "sample_accession", "sr_biosample", "run_accession",
        "lr_run_accession", "lra_final_list", "lra_gca", "lra_gcf",
        "host", "country", "isolation_source", "collection_date",
        "kpsc_final_list",
    ) if c in v2.columns]
    with pd.option_context("display.max_columns", None, "display.width", 200):
        for label, mask in (
            ("SR-only",   (~lra) & has_sr_run),
            ("LR-only",   lra & ~has_sr_run),
            ("Paired SR+LR", lra & has_sr_run),
        ):
            sub = v2.loc[mask, show_cols].head(3)
            if not sub.empty:
                print(f"\n--- {label} ({int(mask.sum()):,} rows total) ---")
                print(sub.to_string(index=False))


def _print_stats(stats: dict) -> None:
    """Print the verification block from the plan."""
    print("\n=== Step 0 pre-cleanup ===")
    print(f"  dropped LR-appended rows : {stats.get('dropped_lr_appended_rows', 0)}  (expected ~2,576)")

    print("\n=== Match counts ===")
    for via, n in (stats.get("match_counts") or {}).items():
        print(f"  {via:<32} {n}")

    print("\n=== Merges + ingestion ===")
    print(f"  n_orphans (unmatched LRAs)     : {stats.get('n_orphans', 0)}")
    print(f"    in lra_final_list              : {stats.get('n_orphans_in_final_set', 0)}  (expected ~124)")
    print(f"    ingested as pure-LR rows      : {stats.get('n_orphans_ingested', 0)}")
    print(f"    residual (no Norway-S1 match) : {stats.get('n_orphans_residual', 0)}  (expected ~0; informational)")
    print(f"  n_sr_refseq_pairs merged       : {stats.get('n_sr_refseq_pairs', 0)}  (expected ~957)")

    print("\n=== Final v2 ===")
    print(f"  v2 rows                   : {stats.get('v2_rows', 0)}  (expected ~87,494)")
    print(f"  lra_final_list=True        : {stats.get('lra_final_list_count', 0)}  (expected 5,521)")
    print(f"  paired SR+LR rows         : {stats.get('paired_sr_lra_count', 0)}  (expected ~5,400; excludes pure-LR orphans)")
    # SR-only-rows can have duplicate Sample (same BioSample, multiple ENA runs) —
    # inherited from metadata_v1, not a logic bug. Only LRA-bearing duplicates matter.
    print(f"  Sample duplicates (all)   : {stats.get('sample_duplicate_count_total', 0)}  (inherited from v1)")
    print(f"  Sample duplicates (LRA)   : {stats.get('sample_duplicate_count_lra', 0)}  (must be 0)")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — build metadata_v2 + write outputs."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v1",  type=Path, default=DEFAULT_METADATA_V1)
    ap.add_argument("--discovery",    type=Path, default=DEFAULT_DISCOVERY)
    ap.add_argument("--final-set",    type=Path, default=DEFAULT_FINAL_SET)
    ap.add_argument("--lr-runs",      type=Path, default=DEFAULT_LR_RUNS_CSV)
    ap.add_argument("--table-s1",     type=Path, default=DEFAULT_TABLE_S1,
                    help="Norway Table S1 xlsx for orphan-LRA enrichment.")
    ap.add_argument("--out-dir",      type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write outputs.")
    args = ap.parse_args(argv)

    print(f"metadata_v1 : {args.metadata_v1}")
    print(f"discovery   : {args.discovery}")
    print(f"final_set   : {args.final_set}")
    print(f"lr_runs     : {args.lr_runs}")
    print(f"table_s1    : {args.table_s1}")
    print(f"out_dir     : {args.out_dir}")

    meta = pd.read_csv(args.metadata_v1, sep="\t", low_memory=False)
    disc = pd.read_csv(args.discovery, sep="\t", low_memory=False)
    final_set = pd.read_csv(args.final_set, sep="\t", low_memory=False)
    final_set_accs = set(final_set["scoring_accession"].astype(str))
    # Carry the NCBI-derived flags (derived once in build_lra_set) onto disc by
    # scoring_accession so the v2 overlay can place them on LRA-bearing rows.
    _present = [c for c in LRA_FLAG_COLUMNS if c in final_set.columns]
    if _present:
        _flags = final_set[["scoring_accession", *_present]].drop_duplicates("scoring_accession")
        disc = disc.merge(_flags, on="scoring_accession", how="left")
    for c in LRA_FLAG_COLUMNS:
        disc[c] = _coerce_bool(disc[c]) if c in disc.columns else False
    lr_runs = pd.read_csv(args.lr_runs, low_memory=False) if args.lr_runs.exists() else pd.DataFrame()
    table_s1_df = load_norway_table_s1(args.table_s1)

    print(f"\nmetadata_v1 rows : {len(meta)}")
    print(f"discovery rows   : {len(disc)}")
    print(f"final-set rows   : {len(final_set)}  (expected 5,521)")
    print(f"lr_runs rows     : {len(lr_runs)}")
    print(f"Norway S1 rows   : {len(table_s1_df)}  (expected ~579)")

    v1_meta_snapshot = meta.copy()  # for v1↔v2 diagnostics (build mutates `meta`)
    v2, residual, stats = build_metadata_v2(meta, disc, final_set_accs, lr_runs, table_s1_df)
    _print_stats(stats)
    _print_v2_diagnostics(v2, v1_meta_snapshot)

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0 if stats["sample_duplicate_count_lra"] == 0 else 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_v2     = args.out_dir / "metadata_v2_all_samples_and_columns.tsv"
    out_orphan = args.out_dir / "metadata_v2_orphan_lras.tsv"

    # Back up any existing copies.
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for p in (out_v2, out_orphan):
        if p.exists():
            backup = p.with_suffix(f".bak.{ts}.tsv")
            p.rename(backup)
            print(f"backed up existing → {backup.name}")

    # Drop internal tracking column before write.
    if "_was_v1_is_refseq" in v2.columns:
        v2 = v2.drop(columns=["_was_v1_is_refseq"])
    v2.to_csv(out_v2, sep="\t", index=False)
    residual.to_csv(out_orphan, sep="\t", index=False)
    print(f"\nwrote {out_v2}  rows={len(v2)}  cols={len(v2.columns)}")
    print(f"wrote {out_orphan}  rows={len(residual)}  (orphans not enriched by Norway S1)")

    # Gate: LRA-bearing-Sample duplicates must be 0. Orphan count is informational.
    failed = False
    if stats["sample_duplicate_count_lra"] > 0:
        print(f"\nERROR: {stats['sample_duplicate_count_lra']} LRA-bearing rows have duplicate Sample values "
              f"(should be 0 — investigate the match logic).", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
