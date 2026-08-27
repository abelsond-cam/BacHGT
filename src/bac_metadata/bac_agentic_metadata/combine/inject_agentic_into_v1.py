r"""Step (i) of the two-step v2 combine — inject the agent's blank-fills into v1, re-normalise, flag evolutionary.

Architecture A (David, 2026-07-22): the agent fills go in at the **v1** stage so the idempotent
``pp/rebuild_v2.sh`` cascade re-derives every v2-only column downstream. ``build_metadata_v2`` does NOT re-parse
the bulk v1 rows (``v2 = meta.copy()``) — it copies v1's ``*_parsed``/``*_category``/``region``/``year_parsed``
columns through — so those derived columns must already be consistent at the v1 level. This tool produces that
consistent, injected v1 as a **separate, reviewable** artefact (not an in-place mutation):

1. **Blank-fill** the four clinical fields onto a copy of v1 via the engine's ``merge_into_canonical`` — human
   ``_parsed`` > agent > ENA, so a curated value is never touched; each fill is flagged ``<field>_agent_filled``.
2. **Re-normalise** the agent-filled rows with v1's OWN ``pp/metadata_curation`` parse/categorise functions
   (David's "v2's hardcoded parse/categorise"), in v1's ``main`` order (host→country→region→iso→reconcile→date).
   Blast radius = the filled rows only; every untouched row keeps v1's derived columns byte-identical.
3. **Evolutionary lab samples** (78 studies / 1,489 samples, ``study_type_excluded=True`` in the master): add
   ``evolutionary_lab_sample=True``, set ``kpsc_final_list=False``, and split SR-only vs LRA-bearing (via
   ``related_lr_accession``) — the LRA-bearing ones are what the additive Kleborate gate re-admits on CSD3, so
   B3's post-Kleborate delist must catch them (the quality flags is_complete/is_hybrid/is_reference_genome are
   CSD3-only, cleared there).

**Local (v1 mirror) test only — the real inject runs on CSD3.** Point at the mirror with
``BACHGT_PROJECT_K_ROOT``. Writes the injected v1 + a numbers report.

    BACHGT_PROJECT_K_ROOT="…/project_k" \
      uv run python -m bac_metadata.bac_agentic_metadata.combine.inject_agentic_into_v1 --out /tmp/v1_injected.tsv
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import accumulate, backfill

#: The four per-sample clinical fields blank-filled + re-normalised.
CLINICAL_FIELDS = ("country", "collection_date", "isolation_source", "host")
#: Candidate derived columns to refresh per field. The re-parse splices back only those the TARGET table
#: actually carries, so this adapts to both canonical shapes: v1 has ``year_parsed`` (rebuild_v2 later renames
#: it to ``collection_year``); v2 already carries ``collection_year`` and drops ``year_parsed``. Listing both
#: lets one code path serve architecture A (inject at v1) and B (inject directly onto v2).
DERIVED_COLUMNS = {
    "country": ["country_parsed", "region"],
    "collection_date": ["collection_date_parsed", "year_parsed", "collection_year"],
    "isolation_source": ["isolation_source_parsed", "isolation_source_category"],
    "host": ["host_parsed", "host_category"],
}
ALL_DERIVED = [c for cols in DERIVED_COLUMNS.values() for c in cols]
V1_RELPATH = Path("data") / "final" / "metadata" / "metadata_final_curated_all_samples_and_columns.tsv"


def resolve_v1_path(explicit: str | None) -> Path:
    """Resolve the v1 canonical table: an explicit path, else ``$BACHGT_PROJECT_K_ROOT/<V1_RELPATH>``."""
    if explicit:
        p = Path(explicit)
    else:
        root = os.environ.get("BACHGT_PROJECT_K_ROOT")
        if not root:
            sys.exit("set BACHGT_PROJECT_K_ROOT (v1 lives under data/final/metadata/) or pass --v1")
        p = Path(root) / V1_RELPATH
    if not p.exists():
        sys.exit(f"v1 table not found: {p}")
    return p


def load_table(path: Path, usecols=None) -> pd.DataFrame:
    """Read a curated TSV as strings, preserving ENA's literal ``NA`` (``keep_default_na=False``)."""
    return pd.read_csv(path, sep="\t", dtype=str, low_memory=False, keep_default_na=False, usecols=usecols)


def blank_fill(v1: pd.DataFrame, master: pd.DataFrame, tmp_dir: Path) -> pd.DataFrame:
    """Overlay the agent master onto v1 (human ``_parsed`` > agent > ENA) via the engine's canonical merge.

    Reuses ``accumulate.merge_into_canonical`` (the single source of truth for the precedence + the
    ``<field>_agent_filled`` flags). That function writes as a side effect, so it is pointed at a throwaway file
    which is removed — the injected table is written once, at the end, by :func:`build_injection`.
    """
    tmp = tmp_dir / "_blankfill_scratch.tsv"
    merged = accumulate.merge_into_canonical(master, v1, CLINICAL_FIELDS, out_path=tmp, gold_suffix="_parsed")
    tmp.unlink(missing_ok=True)
    return merged


def _filled_mask(merged: pd.DataFrame) -> pd.Series:
    """Boolean row mask: any of the four ``<field>_agent_filled`` flags is True (handles bool or str dtype)."""
    flags = [f"{f}_agent_filled" for f in CLINICAL_FIELDS if f"{f}_agent_filled" in merged.columns]
    if not flags:
        return pd.Series(False, index=merged.index)
    cols = [merged[c].astype(str).str.lower().eq("true") for c in flags]
    return pd.concat(cols, axis=1).any(axis=1)


def reparse_rows(df: pd.DataFrame, mask: pd.Series) -> tuple[pd.DataFrame, int]:
    """Re-derive the normalised columns for the ``mask`` rows only, using v1's own parse/categorise pipeline.

    The parse/categorise functions are row-independent regex/lookup, so running them on the masked subframe
    reproduces exactly what the full pipeline would give those rows, while leaving every other row's derived
    columns byte-identical. Order = ``metadata_curation.main`` (host→country→region→iso→reconcile→date), the
    pipeline that produced v1's derived columns. Only columns v1 already carries (:data:`ALL_DERIVED`) are
    spliced back. Shared by the blank-fill (B2) and the gated-overwrite apply (B3) — both change a bare value.
    """
    from bac_metadata.pp.metadata_curation import (
        categorise_region,
        parse_collection_date,
        parse_country,
        parse_host,
        parse_isolation_source,
        reconcile_host_and_isolation_source,
    )
    idx = df.index[mask]
    if not len(idx):
        return df, 0
    sub = df.loc[idx].reset_index(drop=True).copy()
    with contextlib.redirect_stdout(io.StringIO()):  # the parsers are chatty even at verbose=False
        sub = parse_host(sub, verbose=False)  # NOTE: also rewrites bare country/iso/dev_stage on host hints
        sub = parse_country(sub, verbose=False)
        sub = categorise_region(sub, verbose=False)
        sub = parse_isolation_source(sub, verbose=False)  # runs categorise_isolation_source internally
        sub = reconcile_host_and_isolation_source(sub, verbose=False)  # host←iso NA-fill inference
        sub = parse_collection_date(sub, verbose=False)  # collection_date_parsed + year_parsed (+ collection_year)
    for col in ALL_DERIVED:
        if col in sub.columns and col in df.columns:  # splice only columns the TARGET table carries (v1 vs v2)
            df.loc[idx, col] = sub[col].to_numpy()
    return df, int(len(idx))


def reparse_filled_rows(merged: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Re-derive the normalised columns for exactly the agent-filled rows (B2 blank-fill blast radius)."""
    return reparse_rows(merged, _filled_mask(merged))


def handle_evolutionary(merged: pd.DataFrame, master: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Flag the experimental-evolution lab samples, de-list them from the KPSC cohort, split SR-only vs LRA.

    Adds ``evolutionary_lab_sample`` (``True``/``False``), sets ``kpsc_final_list=False`` for those rows, and
    reports the SR-only vs LRA-bearing split (``related_lr_accession`` non-blank ⇒ LRA-bearing ⇒ B3's
    post-Kleborate delist on CSD3 must clamp it too). ``is_kpsc`` is a **taxonomic** call (a lab-evolved
    K. pneumoniae is still KPSC) and is deliberately NOT flipped — only cohort membership is.
    """
    evo_samples = set(master.loc[master["study_type_excluded"].astype(str).str.lower().eq("true"),
                                 "sample_accession"]) - {""}
    evo_mask = merged["sample_accession"].isin(evo_samples)
    merged["evolutionary_lab_sample"] = evo_mask.map({True: "True", False: "False"})
    if "kpsc_final_list" in merged.columns:
        merged.loc[evo_mask, "kpsc_final_list"] = "False"
    # LRA-bearing = the row has a linked long-read assembly (which the Kleborate cascade could re-admit).
    # v1 records this in `related_lr_accession`; v2 has no such column but its LRA rows key on a GCA_/GCF_
    # `Sample` (merge_kleborate…:354). Use whichever the target carries.
    if "related_lr_accession" in merged.columns:
        lra_bearing = evo_mask & backfill.strip_placeholders(merged["related_lr_accession"]).notna()
    elif "Sample" in merged.columns:
        lra_bearing = evo_mask & merged["Sample"].astype(str).str.startswith(("GCA_", "GCF_"))
    else:
        lra_bearing = pd.Series(False, index=merged.index)
    stats = {
        "master_evo_samples": len(evo_samples),
        "rows_flagged": int(evo_mask.sum()),
        "lra_bearing_rows": int((evo_mask & lra_bearing).sum()),
        "sr_only_rows": int((evo_mask & ~lra_bearing).sum()),
    }
    return merged, stats


def _nonblank_frac(series: pd.Series) -> float:
    """Placeholder-stripped non-blank fraction of a column (the completeness measure used across the engine)."""
    return float(backfill.strip_placeholders(series).notna().mean())


def numbers_report(v1_orig: pd.DataFrame, merged: pd.DataFrame, evo: dict, n_reparsed: int) -> str:
    """Assemble the step-(i) numbers report: blank-fills per field, re-parse blast radius, evolutionary split."""
    L = ["# Combine step (i) — inject agentic blank-fills into the canonical table (numbers report)", "",
         "_Blank-fill + re-parse of the filled rows + evolutionary handling. Architecture A injects onto v1 (then "
         "`rebuild_v2.sh`); architecture B injects directly onto the current v2._",
         "", f"**Row count:** canonical {len(v1_orig):,} → injected {len(merged):,} "
         f"({'✅ preserved' if len(v1_orig) == len(merged) else '❌ CHANGED'}).", "",
         "## Blank-fills per field (human `_parsed` > agent > ENA)", "",
         "| field | agent fills | into truly-blank bare | replaced unparsed raw ENA | base non-blank % → injected % |",
         "|---|--:|--:|--:|--:|"]
    v1_bare = {f: backfill.strip_placeholders(v1_orig[f]) for f in CLINICAL_FIELDS}
    for f in CLINICAL_FIELDS:
        flag = f"{f}_agent_filled"
        filled = merged[flag].astype(str).str.lower().eq("true") if flag in merged.columns \
            else pd.Series(False, index=merged.index)
        pre_blank = v1_bare[f].isna()
        into_blank = int((filled & pre_blank).sum())
        replaced = int((filled & ~pre_blank).sum())
        L.append(f"| {f} | {int(filled.sum())} | {into_blank} | {replaced} | "
                 f"{_nonblank_frac(v1_orig[f]) * 100:.1f} → {_nonblank_frac(merged[f]) * 100:.1f} |")
    L += ["", "_`replaced unparsed raw ENA` = the bare cell held a raw ENA value that never parsed "
          "(`_parsed` blank), so the agent value wins per human > agent > ENA — still not a curated overwrite._",
          "", "## Re-normalisation (v2's hardcoded parse/categorise; `main` order)", "",
          f"- Rows re-parsed: **{n_reparsed:,}** (exactly the agent-filled rows — every other row keeps the "
          "canonical table's derived columns byte-identical).",
          f"- Derived columns refreshed: {', '.join(c for c in ALL_DERIVED if c in merged.columns)}.",
          "- The year column follows the target: v1 carries `year_parsed`; v2 carries `collection_year`.",
          "", "## Experimental-evolution lab samples (Step 2b)", "",
          "| quantity | n |", "|---|--:|",
          f"| master evolutionary samples (`study_type_excluded=True`) | {evo['master_evo_samples']:,} |",
          f"| rows flagged `evolutionary_lab_sample=True` (+ `kpsc_final_list=False`) | {evo['rows_flagged']:,} |",
          f"| ├ SR-only (de-list sticks) | {evo['sr_only_rows']:,} |",
          f"| └ LRA-bearing (a full rebuild's Kleborate cascade would re-admit → delist re-clamps) | {evo['lra_bearing_rows']:,} |",
          "", "_The assembly-quality flags (`is_complete`/`is_hybrid`/`is_reference_genome`/`is_variant_called`) "
          "are cleared by `delist_evolutionary` (present on v2; absent on v1 where they are re-derived)._", ""]
    return "\n".join(L) + "\n"


def build_injection(v1: pd.DataFrame, master: pd.DataFrame, out_path: Path) -> tuple[pd.DataFrame, str]:
    """Run the three steps (blank-fill → re-parse → evolutionary), write the injected v1, return (frame, report)."""
    v1_orig = v1.copy()
    merged = blank_fill(v1, master, out_path.parent)
    merged, n_reparsed = reparse_filled_rows(merged)
    merged, evo = handle_evolutionary(merged, master)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.fillna("").to_csv(out_path, sep="\t", index=False)
    report = numbers_report(v1_orig, merged, evo, n_reparsed)
    return merged, report


def main() -> None:
    """Inject the agentic blank-fills into v1 (local test against the mirror), write the table + numbers report."""
    p = argparse.ArgumentParser(description="Inject agentic blank-fills into v1 + re-parse + flag evolutionary.")
    p.add_argument("--app", default="klebsiella")
    p.add_argument("--data-dir", default=None, help="agentic data dir (default applications/<app>/data)")
    p.add_argument("--v1", default=None,
                   help="canonical table to inject onto — v1 (default $BACHGT_PROJECT_K_ROOT/data/final/…) for "
                        "architecture A, or the current v2 for architecture B (the tool adapts the derived-column "
                        "splice + the LRA split to whichever the table carries)")
    p.add_argument("--out", required=True, help="where to write the injected v1 table")
    args = p.parse_args()
    here = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else here / "applications" / args.app / "data"
    v1_path = resolve_v1_path(args.v1)
    print(f"[inject] v1={v1_path}", file=sys.stderr)
    v1 = load_table(v1_path)
    master = load_table(data_dir / "curated" / "metadata_curated_master.tsv")
    out = Path(args.out)
    _, report = build_injection(v1, master, out)
    report_path = out.with_name(out.stem + "_numbers.md")
    report_path.write_text(report)
    print(f"[inject] wrote {out} + {report_path}", file=sys.stderr)
    print(report, file=sys.stderr)


if __name__ == "__main__":
    main()
