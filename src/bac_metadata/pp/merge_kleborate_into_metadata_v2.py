#!/usr/bin/env python3
"""Merge Kleborate-on-LRA output into metadata_v2 + run the KPSC cascade (G.2).

Reads:
  - ``metadata_v2_all_samples_and_columns.tsv``
  - Every ``<kleborate_lra_out>/kleborate_*_complex_output.tsv`` typing
    module from ``run_kleborate_lra collate``. Kleborate v3 splits its
    output by detected complex — we have one file for KpSC genomes
    (``klebsiella_pneumo_complex_output.txt``), one for KoSC contamination
    (``klebsiella_oxytoca_complex_output.txt``), and possibly others. All
    typing tables share the species column so we just concatenate them.
    ``*_hAMRonization_output.tsv`` (AMR-hit tables) are *not* read here.

For each ``lra_final_list=True`` row, the cascade:

  1. **species + scientific_name** — overwrite with the Kleborate call
     (LRA-derived; more accurate than the SR-derived values currently on
     audit-matched rows, and the only source for the 117 ingested orphans).
  2. **is_kpsc** — recompute as ``species`` ∈ KPSC species set
     (K. pneumoniae, K. variicola, K. quasipneumoniae *.subsp.*, K. africana,
     K. tropica). Catches both 5 + 6 subspecies form.
  3. **kpsc_final_list** — additive rule (only ADD, never REMOVE samples).
     - Paired LR rows (sr_biosample populated): ``kpsc_v2 = kpsc_v1 OR (lra_final_list AND is_kpsc)``.
       The v1 SR-side QC pass is preserved even if the LRA fails CheckM2;
       new orphans can also be promoted to True if LRA QC + KPSC pass.
     - Orphan LR rows (sr_biosample empty): ``kpsc_v2 = lra_final_list AND is_kpsc``
       (no v1 SR-side data exists; the LRA QC is the only signal).
     - SR-only rows: unchanged from v1.
  4. **Full typing block overlay** — every Kleborate v3 column whose bare
     name (last ``__``-segment) matches an existing v2 column is overlaid
     onto matched rows where the v2 cell is empty. Covers MLST (``ST`` +
     ``gapA``/``infB``/``mdh``/``pgi``/``phoE``/``rpoB``/``tonB``), virulence
     MLSTs (``YbST``/``CbST``/``AbST``/``SmST``/``RmST`` + locus genes),
     ``rmpA2``, AMR per-class acquired/mutations, resistance/virulence scores,
     Kaptive K/O locus, ``wzi``, cipro prediction. Fill-on-empty preserves
     curated v1 values on already-typed rows. ``Sublineage``/``LINcode``/
     ``Clonal group``/``Phylogroup`` are **not** emitted by Kleborate v3 and
     are left untouched here — they come from a separate LIN-typing layer.
  5. **kleborate_needs_recall** — cleared (False) on rows that got a
     fresh Kleborate call.

Always backs up the existing metadata_v2 with a UTC-stamped ``.bak.*.tsv``
before overwriting.

Usage::

    uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2 --dry-run
    uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import pandas as pd

# ─── PATHS + CONSTANTS ────────────────────────────────────────────────────────

DATA_ROOT = Path("/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw")
DEFAULT_METADATA_V2 = DATA_ROOT / "david/final/metadata_v2_all_samples_and_columns.tsv"
DEFAULT_KLEBORATE_OUT = DATA_ROOT / "david/processed/complete_vs_sr_genomes/kleborate_lra"

# Two globs:
#   - typing tables (KpSC + KoSC) → drive species/is_kpsc cascade.
#   - non-Klebsiella tables (escherichia, salmonella, etc.) → discard from
#     the LRA cohort (set lra_final_list=False).
DEFAULT_TYPING_GLOB  = "kleborate_*_complex_output.tsv"
DEFAULT_DISCARD_GLOB = "kleborate_escherichia_output.tsv"

# Kleborate v3 column naming: namespaced "<scheme>__<module>__<field>".
KLEB_SPECIES_COL = "enterobacterales__species__species"
KLEB_STRAIN_COL  = "Sample"  # collate renames Kleborate's "strain" → "Sample"

# The species names Kleborate v3 emits for the KPSC. Match by prefix so we catch
# all subspecies variants without hard-coding the exact subspecies suffix:
#   "Klebsiella pneumoniae"
#   "Klebsiella variicola subsp. variicola"
#   "Klebsiella quasipneumoniae subsp. quasipneumoniae"
#   "Klebsiella quasipneumoniae subsp. similipneumoniae"
#   "Klebsiella africana"
#   "Klebsiella tropica"           (formerly K. variicola subsp. tropica)
KPSC_SPECIES_PREFIXES: tuple[str, ...] = (
    "Klebsiella pneumoniae",
    "Klebsiella variicola",
    "Klebsiella quasipneumoniae",
    "Klebsiella africana",
    "Klebsiella tropica",
)

# Accept either versioned (GCA_X.Y) or bare (GCA_X) accessions — Kleborate's
# output uses the file stem, which is bare, while metadata_v2.Sample is
# versioned. Both _bare() through to the same key.
_ACC_RE = re.compile(r"(GC[AF]_\d+)(?:\.\d+)?")


def _bare(acc: object) -> str:
    """Return a stable join key.

    For GCF/GCA accessions, strip the ``.<version>`` suffix
    (``GCF_003855335.1`` → ``GCF_003855335``). For non-GCF/GCA accessions
    (e.g. SAM*/ERR*), return the trimmed string as-is so SR-only rows can
    still be joined to their Kleborate output (whose ``strain`` column is
    populated from the input FASTA filename, which the runner names after
    the Sample for non-GCF/GCA inputs).
    """
    if acc is None or pd.isna(acc):
        return ""
    s = str(acc).strip()
    m = _ACC_RE.search(s)
    if m:
        return m.group(1).split(".", 1)[0]
    return s


def _coerce_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _is_kpsc(species: pd.Series) -> pd.Series:
    """True iff species starts with one of the KPSC genus-species prefixes."""
    s = species.astype(str)
    mask = pd.Series(False, index=species.index)
    for prefix in KPSC_SPECIES_PREFIXES:
        mask = mask | s.str.startswith(prefix)
    return mask


# Cells treated as empty for fill-on-empty overlay semantics.
_EMPTY_STRS = {"", "nan", "NaN", "None", "<NA>"}


def _is_empty_cell(val: object) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    return str(val).strip() in _EMPTY_STRS


def _kleb_bare_col(col: str) -> str:
    """Map a Kleborate v3 namespaced column to its bare v1-style name.

    ``klebsiella_pneumo_complex__mlst__ST`` → ``ST``;
    ``klebsiella__ybst__YbST`` → ``YbST``;
    ``general__contig_stats__N50`` → ``N50``.
    """
    return col.rsplit("__", 1)[-1]


def _build_overlay_map(kleb_cols: list[str], v2_cols: set[str]) -> dict[str, str]:
    """Build the Kleborate→v2 column-name overlay map.

    Returns ``{kleb_col: v2_col}`` for every Kleborate column whose bare name
    matches an existing v2 column. Skips columns where the bare name collides
    with another Kleborate column (would be ambiguous).
    """
    bare_to_kleb: dict[str, list[str]] = {}
    for c in kleb_cols:
        bare_to_kleb.setdefault(_kleb_bare_col(c), []).append(c)
    overlay: dict[str, str] = {}
    skipped_collisions: list[str] = []
    for bare, kcols in bare_to_kleb.items():
        if bare not in v2_cols:
            continue
        if len(kcols) > 1:
            skipped_collisions.append(f"{bare} <- {kcols}")
            continue
        overlay[kcols[0]] = bare
    if skipped_collisions:
        print(f"WARN: skipped {len(skipped_collisions)} Kleborate columns due to bare-name "
              f"collisions; first few: {skipped_collisions[:3]}", file=sys.stderr)
    return overlay


# ─── MAIN MERGE ───────────────────────────────────────────────────────────────

def apply_cascade(
    meta: pd.DataFrame,
    kleb: pd.DataFrame,
    discard: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Apply species → is_kpsc → kpsc_final_list cascade on lra_final_list rows.

    If ``discard`` is provided (Kleborate output for non-Klebsiella species,
    e.g. ``escherichia_output.tsv``), the matched rows are removed from the
    LRA cohort: ``lra_final_list=False``, ``kpsc_final_list=False``. Species
    is still set so downstream auditing can see why they were dropped.

    Returns ``(updated_meta, stats)``.
    """
    stats: dict = {}
    meta = meta.copy()

    # Kleborate's collated output keys on Sample (bare GCF/GCA). Each LRA in v2
    # has Sample = scoring_accession (versioned). Join via bare accession.
    if KLEB_STRAIN_COL not in kleb.columns:
        raise KeyError(f"Kleborate output missing '{KLEB_STRAIN_COL}' column "
                       "(collate renames Kleborate's 'strain' column).")
    if KLEB_SPECIES_COL not in kleb.columns:
        raise KeyError(f"Kleborate output missing '{KLEB_SPECIES_COL}' column.")

    kleb = kleb.copy()
    kleb["_bare"] = kleb[KLEB_STRAIN_COL].map(_bare)
    kleb = kleb.drop_duplicates("_bare")
    species_map = kleb.set_index("_bare")[KLEB_SPECIES_COL].to_dict()

    lra_mask = _coerce_bool(meta["lra_final_list"])
    stats["lra_final_list_rows"] = int(lra_mask.sum())

    # Find which v2 LRA rows have a Kleborate call.
    meta_bare = meta.loc[lra_mask, "Sample"].map(_bare)
    has_call = meta_bare.map(lambda b: b in species_map)
    stats["lra_rows_matched_to_kleborate"] = int(has_call.sum())
    stats["lra_rows_missing_kleborate"]    = int((~has_call).sum())

    # Apply species (only to matched rows; preserve NaN/existing otherwise).
    new_species = meta_bare.map(species_map)
    for col in ("species", "scientific_name"):
        if col not in meta.columns:
            meta[col] = pd.NA
    fill_idx = new_species.dropna().index
    meta.loc[fill_idx, "species"] = new_species.loc[fill_idx].values
    meta.loc[fill_idx, "scientific_name"] = new_species.loc[fill_idx].values

    # Recompute is_kpsc on every lra_final_list row whose species is now non-null.
    if "is_kpsc" not in meta.columns:
        meta["is_kpsc"] = pd.NA
    new_is_kpsc = _is_kpsc(meta.loc[fill_idx, "species"])
    meta.loc[fill_idx, "is_kpsc"] = new_is_kpsc.values
    stats["lra_rows_is_kpsc_true"]  = int(new_is_kpsc.sum())
    stats["lra_rows_is_kpsc_false"] = int(len(new_is_kpsc) - new_is_kpsc.sum())

    # Ensure the kpsc_final_list column exists; the authoritative write happens
    # in the kpsc gate below (additive on paired rows, strict on orphan LRAs).
    if "kpsc_final_list" not in meta.columns:
        meta["kpsc_final_list"] = pd.NA

    # ── Overlay the full Kleborate typing block on matched rows ───────────
    # Kleborate v3 emits MLST (ST + 7 alleles), virulence MLSTs (Yb/Cb/Ab/Sm/Rm/rmpA2),
    # AMR per-class acquired/mutations, resistance/virulence scores, Kaptive K/O,
    # wzi, cipro_prediction. Sublineage/LINcode/Clonal group are NOT emitted by
    # Kleborate v3 — they came from a separate LIN-typing layer in v1's QC Excel.
    # Fill-on-empty so curated v1 values on the already-typed rows are preserved.
    # Scope: every v2 row whose Sample matches a row in the Kleborate output
    # (covers both LRA-cohort rows and recall-flagged SR rows that were
    # included in the runner's prepare step).
    overlay_map = _build_overlay_map(list(kleb.columns), set(meta.columns))
    # Drop species-related cols (already handled above; avoid double-write under different semantics).
    overlay_map = {k: v for k, v in overlay_map.items() if v not in {"species", "scientific_name"}}
    stats["typing_block_cols_overlaid"] = len(overlay_map)
    kleb_indexed = kleb.set_index("_bare")
    meta_bare_all = meta["Sample"].map(_bare)
    overlay_mask = meta_bare_all.map(lambda b: bool(b) and b in kleb_indexed.index)
    overlay_idx = meta.index[overlay_mask]
    stats["typing_block_rows_overlaid"] = int(overlay_mask.sum())
    n_cells_filled = 0
    for kleb_col, v2_col in overlay_map.items():
        kleb_vals = meta_bare_all.loc[overlay_idx].map(kleb_indexed[kleb_col])
        v2_vals = meta.loc[overlay_idx, v2_col]
        empty_mask = v2_vals.map(_is_empty_cell)
        target_idx = v2_vals.index[empty_mask]
        if len(target_idx) == 0:
            continue
        new_vals = kleb_vals.loc[target_idx]
        # Only write where the Kleborate value itself is non-empty.
        nonempty = ~new_vals.map(_is_empty_cell)
        target_idx = target_idx[nonempty.values]
        if len(target_idx) == 0:
            continue
        meta.loc[target_idx, v2_col] = new_vals.loc[target_idx].values
        n_cells_filled += int(len(target_idx))
    stats["typing_block_cells_filled"] = n_cells_filled

    # Clear kleborate_needs_recall on rows that got a fresh call (LRA or
    # recall-flagged SR rows whose Sample matched the Kleborate output).
    if "kleborate_needs_recall" in meta.columns:
        meta.loc[fill_idx, "kleborate_needs_recall"] = False
        meta.loc[overlay_idx, "kleborate_needs_recall"] = False

    # ── Discard non-Klebsiella matches from the LRA cohort ────────────────
    n_discarded = 0
    if discard is not None and not discard.empty:
        if KLEB_STRAIN_COL not in discard.columns or KLEB_SPECIES_COL not in discard.columns:
            print("WARNING: discard table missing required columns; skipping discard step.",
                  file=sys.stderr)
        else:
            d = discard.copy()
            d["_bare"] = d[KLEB_STRAIN_COL].map(_bare)
            d = d.drop_duplicates("_bare")
            d_species_map = d.set_index("_bare")[KLEB_SPECIES_COL].to_dict()
            meta_bare_all = meta["Sample"].map(_bare)
            discard_mask = meta_bare_all.map(lambda b: b in d_species_map)
            disc_idx = meta.index[discard_mask]
            for idx in disc_idx:
                sp = d_species_map.get(meta_bare_all.loc[idx])
                if sp:
                    meta.at[idx, "species"] = sp
                    if "scientific_name" in meta.columns:
                        meta.at[idx, "scientific_name"] = sp
                meta.at[idx, "lra_final_list"] = False
                if "is_kpsc" in meta.columns:
                    meta.at[idx, "is_kpsc"] = False
                if "kpsc_final_list" in meta.columns:
                    meta.at[idx, "kpsc_final_list"] = False
                if "kleborate_needs_recall" in meta.columns:
                    meta.at[idx, "kleborate_needs_recall"] = False
            n_discarded = int(len(disc_idx))
    stats["discarded_non_klebsiella"] = n_discarded

    # ── Sanity gate: how many lra_final_list rows still lack a species call? ──
    final_lra = _coerce_bool(meta["lra_final_list"])
    null_species = final_lra & meta["species"].isna()
    stats["lra_rows_null_species_post_cascade"] = int(null_species.sum())
    stats["lra_final_list_count_post_cascade"] = int(final_lra.sum())

    # ── kpsc_final_list integrity gate (updated 2026-06-02) ──────────────
    # Additive rule: the v1 kpsc_final_list was set for short-read samples
    # whose SR assembly already passed QC. v2 should only ADD to kpsc_final_list
    # (via the orphan LRA ingest), never REMOVE — a sample whose LR fails
    # CheckM2 still has valid SR data and should stay in the cohort.
    #
    #   Paired LR rows  (sr_biosample populated):   kpsc_v2 = kpsc_v1 OR (lra_final_list AND is_kpsc)
    #   Orphan LR rows  (sr_biosample empty/NaN):   kpsc_v2 = lra_final_list AND is_kpsc
    #   SR-only rows    (Sample not GCF_/GCA_):     unchanged from v1.
    #
    # is_kpsc must be non-NaN on every accepted (lra_final_list=True) LRA row;
    # a NaN there is a bug (missing species call) and is reported below.
    lra_bearing = meta["Sample"].astype(str).str.startswith(("GCF_", "GCA_"))
    if "sr_biosample" in meta.columns:
        srb = meta["sr_biosample"].astype(str).str.strip().str.lower()
        has_sr_partner = meta["sr_biosample"].notna() & ~srb.isin({"", "nan", "<na>", "none"})
    else:
        has_sr_partner = pd.Series(False, index=meta.index)
    paired_lra = lra_bearing & has_sr_partner
    orphan_lra = lra_bearing & ~has_sr_partner

    raw_kpsc = meta["is_kpsc"]
    is_kpsc_nan = raw_kpsc.isna() | raw_kpsc.astype(str).str.strip().isin(["", "nan", "<NA>", "None"])
    bad = lra_bearing & final_lra & is_kpsc_nan
    stats["kpsc_gate_accepted_lra_rows"]      = int((lra_bearing & final_lra).sum())
    stats["kpsc_gate_is_kpsc_nan_on_accepted"] = int(bad.sum())
    if bad.any():
        print(f"\n⚠  kpsc gate: {int(bad.sum())} accepted LRA rows have NaN is_kpsc "
              "(species call needs chasing):", file=sys.stderr)
        for s in meta.loc[bad, "Sample"].astype(str).tolist()[:30]:
            print(f"     {s}", file=sys.stderr)

    strict_kpsc = final_lra & _coerce_bool(meta["is_kpsc"])  # lra_final_list ∧ is_kpsc
    pre_full = _coerce_bool(meta["kpsc_final_list"])

    # Paired LR rows: additive (v1 OR strict). Never lose a v1 True.
    paired_post = pre_full | strict_kpsc
    meta.loc[paired_lra, "kpsc_final_list"] = paired_post[paired_lra].values
    # Orphan LR rows: strict formula (no v1 SR-side data to preserve).
    meta.loc[orphan_lra, "kpsc_final_list"] = strict_kpsc[orphan_lra].values

    # Stats — categorise the outcome.
    post_full = _coerce_bool(meta["kpsc_final_list"])
    stats["kpsc_paired_lr_rows"]                       = int(paired_lra.sum())
    stats["kpsc_orphan_lr_rows"]                       = int(orphan_lra.sum())
    stats["kpsc_paired_preserved_T_despite_strict_F"]  = int((paired_lra & pre_full & ~strict_kpsc).sum())
    stats["kpsc_paired_added_F_to_T"]                  = int((paired_lra & ~pre_full & strict_kpsc).sum())
    stats["kpsc_orphan_set_T"]                         = int((orphan_lra & strict_kpsc).sum())
    stats["kpsc_orphan_set_F"]                         = int((orphan_lra & ~strict_kpsc).sum())
    stats["kpsc_total_changes_on_lr_rows"]             = int((lra_bearing & (post_full != pre_full)).sum())

    # ── is_variant_called flag ────────────────────────────────────────────
    # True iff the row has SR data that passed v1's KPSC QC (which is the
    # cohort variant-calling was performed against). Definition:
    #   is_variant_called = (NOT orphan LRA) AND (v1's kpsc_final_list was True)
    # Equivalently: True for SR-only rows that were on v1's kpsc_final_list, and
    # for paired rows whose SR side was on v1's kpsc_final_list. False for orphan
    # LRA rows (no SR data exists for variant calling).
    has_sr_data = ~orphan_lra  # SR-only OR paired-LR
    meta["is_variant_called"] = has_sr_data & pre_full
    stats["is_variant_called_total"]    = int(meta["is_variant_called"].sum())
    stats["is_variant_called_paired"]   = int((meta["is_variant_called"] & paired_lra).sum())
    stats["is_variant_called_sr_only"]  = int((meta["is_variant_called"] & ~lra_bearing).sum())

    return meta, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — apply cascade + write."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-v2",  type=Path, default=DEFAULT_METADATA_V2)
    ap.add_argument("--kleborate-out", type=Path, default=DEFAULT_KLEBORATE_OUT,
                    help="Dir containing the collated Kleborate typing TSVs.")
    ap.add_argument("--typing-glob",  type=str,  default=DEFAULT_TYPING_GLOB,
                    help="Glob (relative to --kleborate-out) for typing-table TSVs.")
    ap.add_argument("--discard-glob", type=str,  default=DEFAULT_DISCARD_GLOB,
                    help="Glob for non-Klebsiella outputs whose matched rows "
                         "should be removed from the LRA cohort (lra_final_list=False).")
    ap.add_argument("--dry-run", action="store_true", help="Print stats; don't write.")
    args = ap.parse_args(argv)

    typing_paths  = sorted(args.kleborate_out.glob(args.typing_glob))
    discard_paths = sorted(args.kleborate_out.glob(args.discard_glob))
    print(f"metadata_v2  : {args.metadata_v2}")
    print(f"kleborate    : {args.kleborate_out}")
    print(f"  typing glob  : {args.typing_glob}  → {len(typing_paths)} files")
    for p in typing_paths:
        print(f"    {p.name}")
    print(f"  discard glob : {args.discard_glob}  → {len(discard_paths)} files")
    for p in discard_paths:
        print(f"    {p.name}")
    if not typing_paths:
        print(f"FATAL: no Kleborate typing TSVs matching '{args.typing_glob}' under {args.kleborate_out}",
              file=sys.stderr)
        return 2

    meta = pd.read_csv(args.metadata_v2, sep="\t", low_memory=False)
    kleb_frames = []
    for p in typing_paths:
        df = pd.read_csv(p, sep="\t", low_memory=False)
        df["_source_file"] = p.name
        kleb_frames.append(df)
    kleb = pd.concat(kleb_frames, ignore_index=True, sort=False)
    discard = pd.DataFrame()
    if discard_paths:
        d_frames = [pd.read_csv(p, sep="\t", low_memory=False) for p in discard_paths]
        discard = pd.concat(d_frames, ignore_index=True, sort=False) if d_frames else discard
    print(f"\nmetadata_v2 rows  : {len(meta):,}")
    print(f"kleborate rows    : {len(kleb):,}  (typing tables)")
    print(f"discard rows      : {len(discard):,}  (non-Klebsiella, to be removed from LRA cohort)")

    updated, stats = apply_cascade(meta, kleb, discard=discard)

    print("\n=== Cascade stats ===")
    for k, v in stats.items():
        print(f"  {k:40s}: {v:,}")

    if args.dry_run:
        print("\n--dry-run set; not writing output.")
        return 0 if stats.get("lra_rows_missing_kleborate", 0) == 0 else 1

    # Backup + overwrite in place.
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = args.metadata_v2.with_name(f"{args.metadata_v2.stem}.bak.{ts}.tsv")
    args.metadata_v2.rename(bak)
    print(f"\nbacked up existing → {bak.name}")
    updated.to_csv(args.metadata_v2, sep="\t", index=False)
    print(f"wrote {args.metadata_v2}  rows={len(updated):,}  cols={len(updated.columns)}")

    # Missing-Kleborate is informational, NOT fatal: some accepted LRAs are
    # non-KpSC (E. coli / KoSC / species-only) and legitimately have no KpSC
    # typing row. The genuine-failure signals are an accepted LRA with NO
    # species at all, or a NaN is_kpsc — those indicate a failed Slurm chunk.
    n_missing = stats.get("lra_rows_missing_kleborate", 0)
    if n_missing > 0:
        print(f"\nNOTE: {n_missing} accepted LRA rows have no KpSC Kleborate call "
              "(expected for non-KpSC genomes; not fatal).", file=sys.stderr)
    fatal = (
        stats.get("lra_rows_null_species_post_cascade", 0) > 0
        or stats.get("kpsc_gate_is_kpsc_nan_on_accepted", 0) > 0
    )
    if fatal:
        print("\nERROR: accepted LRA rows with no species / NaN is_kpsc — investigate "
              "(likely a failed Kleborate chunk).", file=sys.stderr)
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
