"""The v2 overwrite-candidate classifier — the split that drives the reviewable step-(ii) artefact.

The report's usefulness rides on ``classify`` routing each overwrite correctly: same-year date refinements (the
sanctioned low-risk exception) apart from the rare year-changing / unparseable ones; genuine categorical
changes apart from case/whitespace-only no-ops; and the honest ``shortened`` neutral flag (a de-dup / extract,
NOT a claimed regression).
"""
from __future__ import annotations

from bac_metadata.bac_agentic_metadata.evaluation.report_v2_overwrites import classify


def test_date_same_year_refinement_is_the_sanctioned_exception() -> None:
    """A year-preserving granularity gain is a refinement with no review flag."""
    assert classify("collection_date", "2019", "2019-11-28 00:00:00") == ("date_same_year_refinement", "")


def test_date_year_change_and_unparsed_are_flagged() -> None:
    """Changing the year breaks the same-year rule; an unreadable year is surfaced too."""
    assert classify("collection_date", "2019", "2020-08-01 00:00:00") == ("date_year_changed", "year_changed")
    # '1800/2014' ENA junk vs a supp value → the readable years differ → year_changed
    assert classify("collection_date", "1800/2014", "2007") == ("date_year_changed", "year_changed")
    # '2108' is a copied typo — not matched by (19|20)\d\d, so no year is read → unparsed, surfaced for review
    assert classify("collection_date", "2018", "2108-10-18") == ("date_unparsed", "date_unparsed")
    # a two-digit year on the new side is not matched by (19|20)\d\d → unparsed, surfaced for review
    assert classify("collection_date", "2019", "28/02/19") == ("date_unparsed", "date_unparsed")


def test_categorical_specialise_vs_no_change_vs_shortened() -> None:
    """Vague→specific is a routine change; case/space-only is inert; a shorter substring is flagged neutrally."""
    assert classify("isolation_source", "Human body sites or biosamples", "BLOOD") == ("categorical_change", "")
    assert classify("country", "Switzerland", "Myanmar") == ("categorical_change", "")  # concrete→concrete, no flag
    assert classify("isolation_source", "blood", "  Blood ") == ("no_change", "no_change")  # inert
    assert classify("isolation_source", "Blood_Blood", "Blood") == ("categorical_change", "shortened")
    assert classify("isolation_source", "ST1_Stool_Organism_2", "Stool") == ("categorical_change", "shortened")


def test_categorical_new_is_null_is_flagged() -> None:
    """Replacing a real value with a placeholder-null must be caught (it should never happen)."""
    assert classify("host", "Homo sapiens", "unknown") == ("categorical_change", "new_is_null")
