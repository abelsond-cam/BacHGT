"""Value-validity + date-granularity helpers for the per-sample OVERWRITE gate (engine, app-agnostic).

The per-sample guard (``stages.py``) may only let a supplementary-table value OVERWRITE a genuine ENA value
when it is *robustly* a better value — assessed on the **parsed** value, not a hand-list of tokens. This
module is the deterministic half of that gate:

* **Layer 1 — parse-validity** (`parse_valid`): a value must parse to a REAL value for its field, else it is
  never adopted (not as an overwrite, not as a blank-fill). A whole-cell table-null token ("NF"/"ND"/"-"/…)
  is rejected for every field; a ``collection_date`` must additionally parse as a date (kills "NF", garbled
  cells, any no-digit string).
* **Layer 2 — date betterness** (`parse_date_scalar` → granularity *rank*): a table date may overwrite an ENA
  date only when it is *strictly more specific* (year → year-month → full date). The specimen-tuned LLM
  fidelity judge is wrong for dates (it reads added precision as a non-improving "sub-locality" change), so
  dates are decided here, deterministically.

Only ``collection_date`` gets a deterministic betterness rule; country / isolation_source / host betterness
stays with the agentic ``sample_extractor.judge_overwrite_fidelity``. The one non-stdlib dependency is the
light, pure ``pp.date_utils`` (re / pandas / dateutil) — no heavy imports, no network.
"""

from __future__ import annotations

import calendar
from datetime import datetime

from dateutil.parser import parse as _dateutil_parse

from bac_metadata.pp.date_utils import normalize_date_str

#: Whole-cell placeholders that name "no value" but are NOT in the engine's ``backfill.PLACEHOLDER_NULLS`` —
#: they turn up in supplementary tables (e.g. "NF" not-found, "ND" not-determined). A cell equal to one of
#: these must never be adopted as a real value; one ("NF") overwrote genuine ENA collection dates (PRJEB36683).
TABLE_NULLS: frozenset[str] = frozenset(
    {"", "-", "--", "---", ".", "?", "na", "n/a", "n.a.", "nd", "n.d.", "n/d", "nf", "n.f.", "none", "null",
     "nan", "unknown", "unk", "ns", "not found", "not determined", "not available", "not collected", "missing"}
)

#: Granularity ranks returned by :func:`parse_date_scalar` — a higher rank is strictly more specific.
DATE_RANK_INVALID = 0
DATE_RANK_YEAR = 1
DATE_RANK_YEAR_MONTH = 2
DATE_RANK_FULL = 3


def is_table_null(value: object) -> bool:
    """Return whether ``value`` is a whole-cell table-null placeholder (case-insensitive)."""
    return str(value).strip().lower() in TABLE_NULLS


def parse_date_scalar(value: object) -> tuple[str | None, int]:
    """Return ``(normalised_string_or_None, granularity_rank)`` for a single collection-date value.

    ``granularity_rank`` is one of :data:`DATE_RANK_INVALID` (not a real date — ``"NF"``, garbled, no digit),
    :data:`DATE_RANK_YEAR` (year only, e.g. ``"2018"``), :data:`DATE_RANK_YEAR_MONTH` (``"2019-10"``) or
    :data:`DATE_RANK_FULL` (a full calendar date, e.g. ``"2003-10-23"`` / ``"26/06/2018"``). A ``None`` first
    element always pairs with rank 0 and means "do not adopt this value".

    Granularity is inferred with the double-default trick: parse the string twice with two different default
    dates; a component (year / month / day) was truly *specified* iff it is identical across both parses (an
    unspecified component is filled from the differing defaults). This is robust to format (ISO, D/M/Y, spelled
    month) without a format catalogue. ``dayfirst=True`` disambiguates D/M/Y vs M/D/Y toward the non-US form
    common in these tables.
    """
    if is_table_null(value):
        return None, DATE_RANK_INVALID
    s = normalize_date_str(value)
    if not s or not any(ch.isdigit() for ch in s):  # a date needs at least one digit
        return None, DATE_RANK_INVALID
    try:
        d1 = _dateutil_parse(s, default=datetime(2000, 1, 1), dayfirst=True)
        d2 = _dateutil_parse(s, default=datetime(2001, 6, 15), dayfirst=True)
    except (ValueError, OverflowError, TypeError):
        return None, DATE_RANK_INVALID
    year_spec = d1.year == d2.year
    month_spec = d1.month == d2.month
    day_spec = d1.day == d2.day
    if not year_spec:  # couldn't even pin the year -> not a usable date
        return None, DATE_RANK_INVALID
    if month_spec and day_spec:
        rank = DATE_RANK_FULL
    elif month_spec:
        rank = DATE_RANK_YEAR_MONTH
    else:
        rank = DATE_RANK_YEAR
    return s, rank


#: collection_date span-policy thresholds (David, 2026-07-13). A span of `DATE_SPAN_TWO_YEAR_MONTHS` or less
#: is whole-field filled with its midpoint; a span up to `DATE_SPAN_FIVE_YEAR_MONTHS` is escalated to a human,
#: and its midpoint is accepted only when the period is BEFORE `DATE_OLD_BEFORE_YEAR` (older genomes are scarce,
#: so an approximate date is worth more; recent imprecise dates are low-value). Wider spans are left blank.
DATE_SPAN_TWO_YEAR_MONTHS = 24
DATE_SPAN_FIVE_YEAR_MONTHS = 60
DATE_OLD_BEFORE_YEAR = 2010
_DAYS_PER_MONTH = 30.44  # mean Gregorian month; span is a coarse month count, boundaries are ± a few days


def period_bounds(value: object) -> tuple[datetime, datetime] | None:
    """Return the ``(start, end)`` datetimes ENCLOSING a possibly-partial collection date, or ``None``.

    A year-only value ``"2016"`` encloses ``2016-01-01 .. 2016-12-31``; a year-month ``"2019-10"`` encloses the
    whole month; a full date encloses itself. This makes a span like "2016–2017" a true ~24-month period (start
    of 2016 → end of 2017) rather than the 12 months a Jan-1/Jan-1 parse would give — the fix for calendar-label
    counting (a 20-month span read as ">2 years", PRJEB36486). Returns ``None`` for a non-date / placeholder.
    """
    norm, rank = parse_date_scalar(value)
    if norm is None:
        return None
    try:
        d = _dateutil_parse(norm, default=datetime(2000, 1, 1), dayfirst=True)
    except (ValueError, OverflowError, TypeError):
        return None
    if rank == DATE_RANK_YEAR:
        return datetime(d.year, 1, 1), datetime(d.year, 12, 31)
    if rank == DATE_RANK_YEAR_MONTH:
        return datetime(d.year, d.month, 1), datetime(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    return d, d


def resolve_date_span(
    earliest: object,
    latest: object,
    *,
    two_year_months: int = DATE_SPAN_TWO_YEAR_MONTHS,
    five_year_months: int = DATE_SPAN_FIVE_YEAR_MONTHS,
    old_before_year: int = DATE_OLD_BEFORE_YEAR,
) -> dict:
    """Deterministically resolve a whole-study ``collection_date`` from the grader's earliest+latest endpoints.

    The grader reports the two endpoint dates verbatim; this function (never the LLM) computes the true month
    span from their enclosing period and applies David's rule (2026-07-13):

    * ``<= two_year_months`` → whole-field fill with the period midpoint (``date_decision="whole_field"``);
    * ``two_year_months < span <= five_year_months`` → escalate to a human, with the midpoint as the suggested
      value ONLY when the midpoint year is before ``old_before_year`` (``"escalate_midpoint"``), else escalate
      with no suggestion (``"escalate_blank"`` — a recent imprecise mid-range date is low-value);
    * ``> five_year_months`` → leave blank (``"blank_wide"``);
    * no parseable dates → ``"no_dates"`` (a pure decline).

    Returns a dict with ``span_months`` (int or None), ``proposed_value`` (midpoint ``"YYYY-MM-DD"`` or ``""``),
    ``applies_whole_project`` (True only for the whole-field case), and ``date_decision``.
    """
    blank = {"span_months": None, "proposed_value": "", "applies_whole_project": False, "date_decision": "no_dates"}
    eb = period_bounds(earliest)
    lb = period_bounds(latest)
    if eb is None and lb is None:
        return blank
    eb = eb or lb
    lb = lb or eb
    start = min(eb[0], lb[0])
    end = max(eb[1], lb[1])
    span_months = int(round((end - start).days / _DAYS_PER_MONTH))
    midpoint = (start + (end - start) / 2).strftime("%Y-%m-%d")
    mid_year = (start + (end - start) / 2).year
    if span_months <= two_year_months:
        return {"span_months": span_months, "proposed_value": midpoint,
                "applies_whole_project": True, "date_decision": "whole_field"}
    if span_months <= five_year_months:
        if mid_year < old_before_year:
            return {"span_months": span_months, "proposed_value": midpoint,
                    "applies_whole_project": False, "date_decision": "escalate_midpoint"}
        return {"span_months": span_months, "proposed_value": "",
                "applies_whole_project": False, "date_decision": "escalate_blank"}
    return {"span_months": span_months, "proposed_value": "",
            "applies_whole_project": False, "date_decision": "blank_wide"}


def parse_valid(field: str, value: object) -> bool:
    """Layer-1 gate: is ``value`` a plausible real value for ``field`` (fit to adopt at all)?

    Rejects a whole-cell table-null token for every field; a ``collection_date`` must additionally parse as a
    date. Free-text fields (country / isolation_source / host) accept any non-null-token value verbatim —
    truncation of a real value ("bronchoalveolar lavage" → "bronchoalveolar lava") is a table-parse concern,
    not a value-validity one, and their *betterness* is judged agentically downstream.
    """
    if is_table_null(value):
        return False
    if field == "collection_date":
        return parse_date_scalar(value)[0] is not None
    return True
