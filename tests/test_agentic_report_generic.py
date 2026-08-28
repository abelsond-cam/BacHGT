"""Generic (app-agnostic) behaviour of the agentic-metadata evaluation/summary tools.

M1 made ``wrapup_report`` / ``build_per_study_table`` / ``completeness_by_split`` spec-driven so the same tool
serves Klebsiella, *M. abscessus*, and any future application. These tests pin the two guarantees that make
that safe:

* the real Klebsiella + m_abs specs resolve to the expected report config (Kp = its historical constants; m_abs
  = five fields incl. ``cf_status``, AST study-level columns, no gold, no size bands); and
* the computation adapts to the spec — ``completeness_by_split`` runs **with and without** a gold and includes
  ``cf_status`` for m_abs; ``build_per_study_table`` surfaces the spec's study-level columns and every field.

The byte-identical Klebsiella regression itself runs against the real committed artifacts (not in this unit
suite, which uses small synthetic fixtures).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bac_metadata.bac_agentic_metadata.engine.spec import AttributeSpec
from bac_metadata.bac_agentic_metadata.evaluation import build_per_study_table as bps
from bac_metadata.bac_agentic_metadata.evaluation import completeness_by_split as cbs
from bac_metadata.bac_agentic_metadata.evaluation import report_config as rc
from bac_metadata.bac_agentic_metadata.evaluation import wrapup_report as wr

_APPS = Path(__file__).resolve().parents[1] / "src/bac_metadata/bac_agentic_metadata/applications"


def _spec(app: str) -> AttributeSpec:
    return AttributeSpec.from_yaml(_APPS / app / "attributes.yaml")


# --------------------------------------------------------------------------------------------------------- #
# report_config — the real specs resolve to the expected app-specific config
# --------------------------------------------------------------------------------------------------------- #
def test_report_config_klebsiella_matches_historical_constants():
    s = _spec("klebsiella")
    assert rc.fields(s) == ("country", "collection_date", "isolation_source", "host")
    assert rc.display_fields(s) == ("host", "country", "collection_date", "isolation_source")
    assert rc.study_level_columns(s) == ["study_setting", "amr_study"]
    assert rc.species_label(s) == "Klebsiella"
    assert [b[0] for b in rc.size_bands(s)] == ["tail100", "tail50_99", "tail25_49", "tail10_24", "other_uncovered(<10)"]
    assert rc.synthetic_collections(s) == ("NCTC_collection", "Refseq_collection")


def test_report_config_m_abs_is_goldless_five_field_cf_status():
    s = _spec("m_abs")
    assert rc.fields(s) == ("country", "collection_date", "isolation_source", "host", "cf_status")
    assert rc.display_fields(s)[0] == "cf_status"  # phenotype leads the display
    assert rc.study_level_columns(s) == ["reports_AST", "per_sample_AST"]
    assert rc.species_label(s) == "M. abscessus"
    assert rc.size_bands(s) == []                  # single whole-cohort run, no tail bands
    assert rc.synthetic_collections(s) == ()       # no RefSeq/NCTC carve-out


def test_study_level_columns_defaults_to_all_graded_when_unset():
    """An app that declares no report.study_level_columns surfaces every graded study-level attribute."""
    s = _spec("klebsiella")
    raw = dict(s.raw)
    raw["report"] = {k: v for k, v in s.report.items() if k != "study_level_columns"}
    s2 = AttributeSpec(application=s.application, species=s.species, taxon_of_interest=s.taxon_of_interest,
                       completeness_fields=s.completeness_fields,
                       deterministic_normaliser=s.deterministic_normaliser,
                       sample_identifier_columns=s.sample_identifier_columns,
                       categorisation=s.categorisation, raw=raw)
    cols = rc.study_level_columns(s2)
    assert cols[:2] == ["study_setting", "amr_study"] and "amr_target" in cols  # all graded, not just the pair


# --------------------------------------------------------------------------------------------------------- #
# synthetic dataset builder for the computation tests
# --------------------------------------------------------------------------------------------------------- #
def _write_dataset(dd: Path, fields: list[str], fold_label: str, *, gold: bool) -> None:
    (dd / "inputs").mkdir(parents=True, exist_ok=True)
    (dd / "curated").mkdir(exist_ok=True)
    (dd / "fold_splits").mkdir(exist_ok=True)
    (dd / "ena_assessment").mkdir(exist_ok=True)
    val = {"country": "France", "collection_date": "2015", "isolation_source": "blood",
           "host": "human", "cf_status": "CF"}
    base_rows, mast_rows, gold_rows = [], [], []
    for i in range(6):
        rid = f"S1_s{i}"
        b = {f: (val[f] if i < 2 else "") for f in fields}      # base: 2/6 filled
        m = {f: (val[f] if i < 5 else "") for f in fields}      # agent: 5/6 filled
        base_rows.append({"study_accession": "S1", "sample_accession": rid, **b})
        mast_rows.append({"study_accession": "S1", "sample_accession": rid, **m})
        gold_rows.append({"sample_accession": rid, **{f"{f}_parsed": val[f] for f in fields}})
    pd.DataFrame(base_rows).to_csv(dd / "inputs" / "base_table.csv", index=False)
    pd.DataFrame(mast_rows).to_csv(dd / "curated" / "metadata_curated_master.tsv", sep="\t", index=False)
    pd.DataFrame([{"study_accession": "S1", "fold": fold_label}]).to_csv(
        dd / "fold_splits" / "project_splits.tsv", sep="\t", index=False)
    if gold:
        pd.DataFrame(gold_rows).to_csv(dd / "gold.tsv", sep="\t", index=False)


def test_completeness_by_split_gold_and_goldless(tmp_path):
    s = _spec("klebsiella")
    fields = list(rc.fields(s))
    dd = tmp_path / "kp"
    _write_dataset(dd, fields, "train", gold=True)
    common = {"fields": rc.fields(s), "size_bands": rc.size_bands(s), "fold_splits": rc.fold_splits(s),
              "synthetic_collections": rc.synthetic_collections(s)}
    gold_sc = cbs.build_scorecard(dd / "curated" / "metadata_curated_master.tsv", dd / "inputs" / "base_table.csv",
                                  dd / "fold_splits" / "project_splits.tsv", truth_path=dd / "gold.tsv", **common)
    # gold path: manual + diff columns present, agent > raw
    assert {"country_manual", "country_diff"} <= set(gold_sc.columns)
    train = gold_sc[gold_sc["split"] == "train"].iloc[0]
    assert train["country_agent"] > train["country_raw"]

    goldless = cbs.build_scorecard(dd / "curated" / "metadata_curated_master.tsv", dd / "inputs" / "base_table.csv",
                                   dd / "fold_splits" / "project_splits.tsv", truth_path=None, **common)
    # goldless path: raw/agent only, never a manual/diff column
    assert not any(c.endswith("_manual") or c.endswith("_diff") for c in goldless.columns)
    assert {"country_raw", "country_agent"} <= set(goldless.columns)


def test_completeness_by_split_m_abs_includes_cf_status_goldless(tmp_path):
    s = _spec("m_abs")
    fields = list(rc.fields(s))
    assert "cf_status" in fields
    dd = tmp_path / "mabs"
    _write_dataset(dd, fields, "mabs_all", gold=False)
    sc = cbs.build_scorecard(dd / "curated" / "metadata_curated_master.tsv", dd / "inputs" / "base_table.csv",
                             dd / "fold_splits" / "project_splits.tsv", truth_path=None,
                             fields=rc.fields(s), size_bands=rc.size_bands(s), fold_splits=rc.fold_splits(s),
                             synthetic_collections=rc.synthetic_collections(s))
    assert "cf_status_agent" in sc.columns and "cf_status_raw" in sc.columns
    assert not any(c.endswith("_manual") for c in sc.columns)      # goldless
    assert "TOTAL_excl_Refseq" not in set(sc["split"])             # no RefSeq carve-out for m_abs
    assert "mabs_all" in set(sc["split"])


# --------------------------------------------------------------------------------------------------------- #
# build_per_study_table — study-level columns + fields come from the spec
# --------------------------------------------------------------------------------------------------------- #
def _write_per_study_dataset(dd: Path, fields: list[str], slc: list[str]) -> None:
    (dd / "inputs").mkdir(parents=True, exist_ok=True)
    (dd / "curated").mkdir(exist_ok=True)
    val = {"country": "France", "collection_date": "2015", "isolation_source": "blood",
           "host": "human", "cf_status": "CF"}
    base_rows, mast_rows = [], []
    for i in range(4):
        rid = f"S1_s{i}"
        base_rows.append({"study_accession": "S1", "sample_accession": rid,
                          **{f: (val[f] if i < 1 else "") for f in fields}})
        mast_rows.append({"study_accession": "S1", "sample_accession": rid,
                          **{f: (val[f] if i < 3 else "") for f in fields}})
    pd.DataFrame(base_rows).to_csv(dd / "inputs" / "base_table.csv", index=False)
    pd.DataFrame(mast_rows).to_csv(dd / "curated" / "metadata_curated_master.tsv", sep="\t", index=False)
    grow = {"study_accession": "S1", "study_type": "observational", "study_type_excluded": "False"}
    for c in slc:
        grow[f"{c}__value"] = "x"
    pd.DataFrame([grow]).to_csv(dd / "curated" / "curated_grades.tsv", sep="\t", index=False)


def test_build_per_study_surfaces_spec_study_level_columns(tmp_path):
    s = _spec("klebsiella")
    dd = tmp_path / "kp"
    _write_per_study_dataset(dd, list(rc.fields(s)), rc.study_level_columns(s))
    t = bps.build_table(dd, tags=["train"], spec=s)
    assert {"study_setting", "amr_study", "study_type", "study_type_excluded"} <= set(t.columns)
    # per-field base/filled/added present for every spec field; agent added data (filled_n > base_n)
    for f in rc.fields(s):
        assert {f"{f}_base_n", f"{f}_filled_n", f"{f}_added"} <= set(t.columns)
    assert int(t.iloc[0]["host_added"]) == 2  # 1 base -> 3 filled


def test_build_per_study_m_abs_has_cf_status_and_ast_columns(tmp_path):
    s = _spec("m_abs")
    dd = tmp_path / "mabs"
    _write_per_study_dataset(dd, list(rc.fields(s)), rc.study_level_columns(s))
    t = bps.build_table(dd, tags=["mabs_all"], spec=s)
    assert {"reports_AST", "per_sample_AST"} <= set(t.columns)     # m_abs study-level judgements
    assert {"cf_status_base_n", "cf_status_filled_n", "cf_status_added"} <= set(t.columns)


# --------------------------------------------------------------------------------------------------------- #
# wrapup_report helpers
# --------------------------------------------------------------------------------------------------------- #
def test_wrapup_methods_file_is_read_verbatim():
    s = _spec("klebsiella")
    mp = _APPS / "klebsiella" / s.report["methods_file"]
    lines = wr._read_methods(mp, s)
    assert lines[0] == "## 0. Methods & provenance"
    assert "\n".join(lines) == mp.read_text()      # verbatim, no mangling


def test_wrapup_methods_stub_when_no_file():
    s = _spec("m_abs")
    lines = wr._read_methods(None, s)               # m_abs declares no methods_file yet
    assert lines[0] == "## 0. Methods & provenance"
    assert any("M. abscessus" in ln for ln in lines)


def test_wrapup_parse_summary_filters_to_fields(tmp_path):
    p = tmp_path / "filled_metadata_summary.md"
    p.write_text(
        "| field | base | filled | agent | new | overrides | per_sample | escalation | whole_field |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| country | 10 | 20 | 10 | 8 | 2 | 5 | 1 | 4 |\n"
        "| not_a_field | 1 | 2 | 1 | 0 | 0 | 0 | 0 | 0 |\n"
    )
    out = wr.parse_summary(p, ("country", "collection_date", "isolation_source", "host"))
    assert set(out) == {"country"} and out["country"]["agent"] == 10.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
