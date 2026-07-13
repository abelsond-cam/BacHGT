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
