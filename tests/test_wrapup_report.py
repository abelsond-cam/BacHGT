"""Unit tests for the wrap-up report's summary parser (``evaluation.wrapup_report.parse_summary``).

The reconciliation (Σ per-tranche agent-fills == master) is only trustworthy if the markdown summary table is
parsed exactly — bold ``**filled**`` stripped, the 8 numeric columns mapped in order, non-field rows ignored.
"""

from __future__ import annotations

from bac_metadata.bac_agentic_metadata.evaluation import wrapup_report as w

_SUMMARY = """# Filled metadata table — train (tag `train`)

Studies: **109**; samples: **6756**.

| field | base | filled | agent fills | new | overrides | per-sample | escalation | whole-field |
|---|---|---|---|---|---|---|---|---|
| country | 0.620 | **0.934** | 10740 | 9000 | 1740 | 4296 | 2000 | 4444 |
| host | 0.487 | **0.924** | 16510 | 16000 | 510 | 7779 | 700 | 8031 |

## Study-level grades

| column | graded studies | samples filled | value distribution |
|---|---|---|---|
| study_setting | 100 | 6000 | hospital 5000, mixed 1000 |
"""


def test_parse_summary_maps_fields_and_strips_bold(tmp_path):
    p = tmp_path / "filled_metadata_summary.md"
    p.write_text(_SUMMARY)
    got = w.parse_summary(p)
    assert set(got) == {"country", "host"}                      # the study-level rows are ignored
    assert got["country"]["base"] == 0.620 and got["country"]["filled"] == 0.934  # bold stripped
    assert got["country"]["agent"] == 10740 and got["host"]["agent"] == 16510
    assert got["host"]["per_sample"] == 7779 and got["host"]["whole_field"] == 8031


def test_parse_summary_missing_file_is_empty(tmp_path):
    assert w.parse_summary(tmp_path / "nope.md") == {}


def test_reconciliation_sum_matches(tmp_path):
    # two tranches whose agent-fills sum to a master total → the report's Δ must be 0
    a = tmp_path / "a.md"; a.write_text(_SUMMARY.replace("10740", "100").replace("16510", "200"))
    got = w.parse_summary(a)
    assert got["country"]["agent"] == 100 and got["host"]["agent"] == 200
