r"""Curator CLI for the agentic categoriser — ``induce`` | ``apply`` | ``reconcile``.

Species-agnostic: everything is driven by the application ``attributes.yaml`` ``categorisation`` block
and the per-sample base table. ``induce`` proposes a category scheme (Phase B) for review; ``apply``
maps distinct values to ``{parsed, category}`` (Phase C); ``reconcile`` applies cross-column
implications + value canonicalisation and (optionally) country/date normalisation, writing the final
table (Phase D).

Example::

    python -m bac_metadata.bac_agentic_metadata.engine.cli.categorise induce \\
        --spec applications/klebsiella/attributes.yaml \\
        --table applications/klebsiella/data/inputs/base_table.csv \\
        --data-dir applications/klebsiella/data --field host --field isolation_source
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine.categorise import apply_categories as ac
from bac_metadata.bac_agentic_metadata.engine.categorise import induce_categories as ic
from bac_metadata.bac_agentic_metadata.engine.categorise import reconcile_cross_column as rc
from bac_metadata.bac_agentic_metadata.engine.categorise.value_frequencies import value_frequencies
from bac_metadata.bac_agentic_metadata.engine.llm import make_llm
from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec


def _seed_for(field: str) -> list[dict]:
    """Return the existing hardcoded Klebsiella scheme for ``field`` as a non-binding seed (or [])."""
    try:
        from bac_metadata.pp import metadata_curation as mc
    except Exception:  # noqa: BLE001 — seed is optional; induction works from scratch without it
        return []
    names = {
        "host": getattr(mc, "HOST_CATEGORIES_TO_PLOT", []),
        "isolation_source": getattr(mc, "ISOLATION_SOURCE_CATEGORIES_TO_PLOT", []),
    }.get(field, [])
    return [{"name": n, "definition": ""} for n in names]


def _read_base(table: str) -> pd.DataFrame:
    sep = "\t" if str(table).endswith(".tsv") else ","
    return pd.read_csv(table, sep=sep, dtype=str, low_memory=False, keep_default_na=False)


def _make_llm(args: argparse.Namespace):
    """Build the LLM client with the CLI's backend/model/timeout (large category outputs are slow)."""
    return make_llm(args.backend, model=args.model, timeout=args.timeout) if args.model \
        else make_llm(args.backend, timeout=args.timeout)


def _load_categories(cfg: dict, field: str, cat_dir: Path) -> list[dict]:
    """Return the approved category scheme for ``field``.

    Inline yaml ``categories`` win if present; otherwise the reviewed standalone
    ``<field>_categories_approved.yaml`` (the verbose scheme lives in its own reviewable file to keep
    attributes.yaml — which David edits by hand — readable). Returns ``[]`` if neither exists.
    """
    inline = cfg.get("categories") or []
    if inline:
        return inline
    approved = cat_dir / f"{field}_categories_approved.yaml"
    if approved.exists():
        import yaml
        return yaml.safe_load(approved.read_text()).get("categories", []) or []
    return []


def _induce(args: argparse.Namespace) -> None:
    spec = AttributeSpec.from_yaml(args.spec)
    base = _read_base(args.table)
    llm = _make_llm(args)
    out_dir = Path(args.data_dir) / "study_lv_attributes" / "categorisation"

    for field in args.field:
        if field not in base.columns:
            print(f"[skip] {field}: not a column in the base table", file=sys.stderr)
            continue
        cfg = spec.categorisation.get(field, {}) or {}
        null_tokens = tuple(cfg.get("null_tokens", []))
        null_patterns = tuple(cfg.get("null_patterns", []))
        freqs = value_frequencies(base[field], null_tokens=null_tokens, null_patterns=null_patterns)
        seed = [] if args.no_seed else _seed_for(field)
        print(f"[induce] {field}: {len(freqs)} distinct values, {int(freqs.sum())} samples"
              f"{' (seeded)' if seed else ''}", file=sys.stderr)
        proposal = ic.induce_categories(
            field, freqs, llm=llm, seed_categories=seed, max_values=args.max_values, model=args.model,
        )
        out = ic.write_proposal(field, proposal, freqs, out_dir / f"{field}_categories_proposed.yaml")
        cats = proposal.get("categories", [])
        xf = proposal.get("cross_field_notes", [])
        print(f"[induce] {field}: proposed {len(cats)} categories, {len(xf)} cross-field notes -> {out}",
              file=sys.stderr)


def _apply(args: argparse.Namespace) -> None:
    spec = AttributeSpec.from_yaml(args.spec)
    base = _read_base(args.table)
    llm = _make_llm(args)
    out_dir = Path(args.data_dir) / "study_lv_attributes" / "categorisation"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = base
    for field in args.field:
        cfg = spec.categorisation.get(field, {}) or {}
        categories = _load_categories(cfg, field, out_dir)
        if not categories:
            print(f"[skip] {field}: no approved scheme — run `induce`, review, then save the approved "
                  f"scheme as {out_dir / f'{field}_categories_approved.yaml'}", file=sys.stderr)
            continue
        df, assessment, audit = ac.apply_categories(
            df, field, categories, llm=llm,
            null_tokens=tuple(cfg.get("null_tokens", [])),
            null_patterns=tuple(cfg.get("null_patterns", [])),
            batch_size=args.batch_size, model=args.model,
        )
        audit_path = out_dir / f"{field}_reassignment_audit.tsv"
        audit.to_csv(audit_path, sep="\t", index=False)
        # Console audit: category tallies + every NA/poor-fit reassignment (never a silent drop).
        print(f"\n=== [apply] {field}: {assessment['n_distinct']} distinct values, "
              f"{assessment['n_samples']} samples ===", file=sys.stderr)
        for cat, n in sorted(assessment["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"    {cat:32s} {n}", file=sys.stderr)
        na_rows = audit[audit["category"] == "NA"]
        if len(na_rows):
            print(f"  -> {len(na_rows)} distinct values sent to NA (value ×count | reason):", file=sys.stderr)
            for _, r in na_rows.head(40).iterrows():
                print(f"       {r['value']!r} ×{r['count']} | {r['na_reason']}", file=sys.stderr)
        poor = assessment["poor_fit_values"]
        if poor:
            print(f"  -> {len(poor)} poor-fit values flagged (candidates for a new category): "
                  f"{poor[:20]}", file=sys.stderr)
        print(f"  -> full reassignment audit: {audit_path}", file=sys.stderr)

    out_path = Path(args.out) if args.out else (out_dir / f"categorised_{args.tag}.tsv")
    df.to_csv(out_path, sep="\t", index=False)
    print(f"\n[apply] wrote categorised table -> {out_path}", file=sys.stderr)


def _counts(series: pd.Series) -> dict:
    """Value counts with blank cells shown as ``(blank)`` (for before/after console reporting)."""
    return series.fillna("").replace("", "(blank)").value_counts().to_dict()


def _reconcile(args: argparse.Namespace) -> None:
    """Phase D — apply cross-column + normalise rules, optionally normalise country/date, write final."""
    spec = AttributeSpec.from_yaml(args.spec)
    df = _read_base(args.table)
    out_dir = Path(args.data_dir) / "study_lv_attributes" / "categorisation"
    out_dir.mkdir(parents=True, exist_ok=True)

    report_cols = [c for c in ("cf_status", "host_category") if c in df.columns]
    before = {c: _counts(df[c]) for c in report_cols}

    df, audit, escalations = rc.reconcile(df, spec.categorisation)

    # Geo/date: reuse the robust, organism-agnostic parsers from pp.metadata_curation (lazy import keeps
    # the engine decoupled — same optional-import pattern as `_seed_for`). No agentic work here.
    if args.geo_date:
        try:
            from bac_metadata.pp import metadata_curation as mc
        except Exception as exc:  # noqa: BLE001 — geo/date is optional; report and carry on
            print(f"[reconcile] --geo-date requested but pp.metadata_curation unavailable: {exc}", file=sys.stderr)
        else:
            df = mc.parse_country(df, verbose=False)
            df = mc.categorise_region(df, verbose=False)
            df = mc.parse_collection_date(df, verbose=False)

    audit_path = out_dir / "reconcile_audit.tsv"
    esc_path = out_dir / "reconcile_escalations.tsv"
    audit.to_csv(audit_path, sep="\t", index=False)
    escalations.to_csv(esc_path, sep="\t", index=False)

    # Console audit — before/after for reconciled columns, cross-column tally, escalations, geo/date fill.
    print("\n" + "=" * 70, file=sys.stderr)
    print("[reconcile] cross-column + normalise", file=sys.stderr)
    for c in report_cols:
        print(f"\n  {c}: before -> after", file=sys.stderr)
        after = _counts(df[c])
        for k in sorted(set(before[c]) | set(after), key=lambda k: -after.get(k, 0)):
            b, a = before[c].get(k, 0), after.get(k, 0)
            flag = "" if b == a else "   <-- changed"
            print(f"      {str(k):16s} {b:6d} -> {a:6d}{flag}", file=sys.stderr)
    if len(audit):
        print("\n  reassignments (action x count):", file=sys.stderr)
        for act, grp in audit.groupby("action"):
            print(f"      {act:10s} {int(grp['count'].sum()):6d}  ({len(grp)} distinct source values)", file=sys.stderr)
    print(f"\n  escalations (fill conflicts to review): {len(escalations)}", file=sys.stderr)
    for _, r in escalations.head(20).iterrows():
        print(f"      {r['source_value']!r} x{r['count']}: {r['target_field']} "
              f"{r['existing_value']!r} vs proposed {r['proposed_value']!r}", file=sys.stderr)
    if args.geo_date:
        print("\n  geo/date fill (% non-blank):", file=sys.stderr)
        for c in ("country_parsed", "region", "collection_date_parsed", "year_parsed"):
            if c in df.columns:
                nz = (df[c].fillna("").astype(str) != "").sum()
                print(f"      {c:24s} {nz:6d}  {100 * nz / len(df):5.1f}%", file=sys.stderr)
    print(f"\n  -> audit: {audit_path}\n  -> escalations: {esc_path}", file=sys.stderr)

    out_path = Path(args.out) if args.out else (
        Path(args.data_dir) / "curated" / f"metadata_curated_master_final_{args.tag}.tsv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, sep="\t", index=False)
    print(f"\n[reconcile] wrote final table -> {out_path} ({len(df)} rows x {df.shape[1]} cols)", file=sys.stderr)


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Agentic categoriser — induce/apply/reconcile category schemes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("induce", help="Propose a category scheme per field for curator review (Phase B).")
    pi.add_argument("--spec", required=True, help="Application attributes.yaml.")
    pi.add_argument("--table", required=True, help="Full-width per-sample base table (CSV/TSV).")
    pi.add_argument("--data-dir", required=True, help="Application data tree root (proposals written under it).")
    pi.add_argument("--field", action="append", required=True, help="Field(s) to induce (repeatable).")
    pi.add_argument("--backend", default="subscription", help="LLM backend (subscription | api).")
    pi.add_argument("--model", default=None, help="Model override.")
    pi.add_argument("--max-values", type=int, default=400, help="Distinct values shown to the model (tail summarised).")
    pi.add_argument("--no-seed", action="store_true", help="Induce fully from scratch (no existing-scheme seed).")
    pi.add_argument("--timeout", type=int, default=1500, help="Per-call subprocess timeout (s) — large outputs are slow.")
    pi.set_defaults(func=_induce)

    pa = sub.add_parser("apply", help="Map values to the approved scheme -> parsed+category+audit (Phase C).")
    pa.add_argument("--spec", required=True, help="Application attributes.yaml (with approved `categories`).")
    pa.add_argument("--table", required=True, help="Full-width per-sample base/master table (CSV/TSV).")
    pa.add_argument("--data-dir", required=True, help="Application data tree root (audit + output written under it).")
    pa.add_argument("--field", action="append", required=True, help="Field(s) to categorise (repeatable).")
    pa.add_argument("--tag", default="train", help="Run tag for the output filename.")
    pa.add_argument("--out", default=None, help="Explicit categorised-table output path.")
    pa.add_argument("--backend", default="subscription", help="LLM backend (subscription | api).")
    pa.add_argument("--model", default=None, help="Model override.")
    pa.add_argument("--batch-size", type=int, default=60, help="Distinct values per LLM mapping call.")
    pa.add_argument("--timeout", type=int, default=900, help="Per-call subprocess timeout (s).")
    pa.set_defaults(func=_apply)

    pr = sub.add_parser("reconcile", help="Apply cross-column + normalise rules -> final table (Phase D).")
    pr.add_argument("--spec", required=True, help="Application attributes.yaml (with `cross_column`/`normalise`).")
    pr.add_argument("--table", required=True, help="Applied/categorised per-sample table (from `apply`).")
    pr.add_argument("--data-dir", required=True, help="Application data tree root (audit + final written under it).")
    pr.add_argument("--field", action="append", default=[], help="Unused placeholder for symmetry (rules come from the spec).")
    pr.add_argument("--geo-date", action="store_true", help="Also normalise country/region/collection_date via pp.metadata_curation.")
    pr.add_argument("--tag", default="mabs", help="Run tag for the default output filename.")
    pr.add_argument("--out", default=None, help="Explicit final-table output path.")
    pr.set_defaults(func=_reconcile)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
