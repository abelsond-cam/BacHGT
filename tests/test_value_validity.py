"""Unit tests for the per-sample OVERWRITE gate's deterministic half (``engine.value_validity``).

These lock the parse-validity + date-granularity logic that decides whether a supplementary-table value may
be adopted at all, and (for dates) whether it is *strictly more specific* than the ENA value it would
overwrite — the fix for the silent overwrites the run-health self-audit surfaced (PRJEB36683 'NF' over real
dates; PRJEB30134 garbled/truncated PDF cells). Offline, no LLM.
"""

from __future__ import annotations

from bac_metadata.bac_agentic_metadata.engine.value_validity import (
    DATE_RANK_FULL,
    DATE_RANK_INVALID,
    DATE_RANK_YEAR,
    DATE_RANK_YEAR_MONTH,
    is_table_null,
    parse_date_scalar,
    parse_valid,
    resolve_date_span,
)


def test_is_table_null_matches_placeholders_not_real_values():
    for v in ["NF", "nf", "ND", "n/d", "-", "--", "", " na ", "None", "unknown", "not found"]:
        assert is_table_null(v), v
    for v in ["blood", "2018", "Kenya", "Homo sapiens", "0.5", "bronchoalveolar lavage"]:
        assert not is_table_null(v), v


def test_parse_date_scalar_ranks_by_granularity():
    # invalid: placeholder, garbled, no-digit
    for v in ["NF", "ND", ". similipne2u01m9o-1n0ia-0e1", "clinical", ""]:
        assert parse_date_scalar(v) == (None, DATE_RANK_INVALID), v
    # year-only < year-month < full date (any common format)
    assert parse_date_scalar("2018")[1] == DATE_RANK_YEAR
    assert parse_date_scalar("2019-10")[1] == DATE_RANK_YEAR_MONTH
    assert parse_date_scalar("March 2018")[1] == DATE_RANK_YEAR_MONTH
    for v in ["2003-10-23", "2003-10-23 00:00:00", "26/06/2018"]:
        assert parse_date_scalar(v)[1] == DATE_RANK_FULL, v
    # dayfirst: 26/06 is a real day/month (not month 26)
    assert parse_date_scalar("26/06/2018")[0] is not None


def test_date_betterness_is_strict_specificity():
    # the guard adopts an overwrite iff table_rank > ena_rank
    def better(table, ena):
        return parse_date_scalar(table)[1] > parse_date_scalar(ena)[1]

    assert better("2003-10-23", "2003")        # year -> full date: adopt (real upgrade)
    assert better("26/06/2018", "2018")        # year -> full date (D/M/Y): adopt
    assert not better("2018-04-11", "2018-01-13")   # full -> different full: KEEP ENA (Q1, David 2026-07-13)
    assert not better("2018", "2003-10-23")    # full -> year: KEEP ENA (never coarsen)
    assert not better("NF", "2018-04-11")      # invalid -> rank 0, never beats a real date


def test_resolve_date_span_deterministic_rule():
    # <=2yr -> whole-field fill with the midpoint (David's 2026-07-13 rule; period-enclosing, not label-count)
    d = resolve_date_span("2016", "2017")
    assert d["date_decision"] == "whole_field" and d["applies_whole_project"] is True
    assert d["span_months"] <= 24 and d["proposed_value"][:7] in {"2016-12", "2017-01"}  # true period midpoint
    # the 20-month PRJEB36486 case: a sub-2yr span must NOT read as ">2 years" (the calendar-label bug)
    d = resolve_date_span("2015-06", "2017-01")
    assert d["span_months"] <= 24 and d["date_decision"] == "whole_field"
    # 2-5yr AND pre-2010 -> escalate WITH a midpoint suggestion
    d = resolve_date_span("2003", "2007")
    assert 24 < d["span_months"] <= 60 and d["date_decision"] == "escalate_midpoint"
    assert d["applies_whole_project"] is False and d["proposed_value"].startswith("2005-")
    # 2-5yr but recent -> escalate BLANK (a recent imprecise mid-range date is low-value)
    d = resolve_date_span("2015", "2019")
    assert d["date_decision"] == "escalate_blank" and d["proposed_value"] == ""
    # >5yr -> blank, never filled
    d = resolve_date_span("2000", "2010")
    assert d["span_months"] > 60 and d["date_decision"] == "blank_wide" and d["proposed_value"] == ""
    # no parseable dates -> a pure decline
    d = resolve_date_span(None, None)
    assert d["date_decision"] == "no_dates" and d["span_months"] is None
    # a single date -> a zero-span whole-field fill of that date
    d = resolve_date_span("2018", None)
    assert d["date_decision"] == "whole_field" and d["proposed_value"].startswith("2018-")


def test_full_iso_date_span_not_month_day_swapped():
    # regression (PRJEB36486): "2018-10-02" must read as Oct 2, not Feb 10 — dayfirst must not corrupt ISO dates.
    d = resolve_date_span("2017-02-19", "2018-10-02")
    assert 19 <= d["span_months"] <= 20, d          # true span ~20 months, not the buggy 12
    assert d["date_decision"] == "whole_field"       # still <=2yr -> filled with the (correct) midpoint
    assert d["proposed_value"][:7] in {"2017-12", "2018-01"}, d["proposed_value"]  # midpoint of Feb'17..Oct'18
    # a D/M/Y table date must still be dayfirst (26 is unambiguously the day)
    from bac_metadata.bac_agentic_metadata.engine.value_validity import period_bounds
    assert period_bounds("26/06/2018")[0].month == 6
    # an ISO date whose day <=12 must keep month/day order
    assert period_bounds("2019-03-05")[0].month == 3 and period_bounds("2019-03-05")[0].day == 5


def test_parse_valid_layer1():
    # collection_date must parse as a date; other fields reject only whole-cell table-null tokens
    assert parse_valid("collection_date", "2018")
    assert not parse_valid("collection_date", "NF")
    assert not parse_valid("collection_date", "clinical")     # non-date free text is not a valid date
    assert parse_valid("isolation_source", "blood")
    assert parse_valid("isolation_source", "bronchoalveolar lava")  # truncation is a parse concern, not validity
    assert not parse_valid("isolation_source", "NF")
    assert parse_valid("country", "Kenya")
    assert not parse_valid("host", "ND")
