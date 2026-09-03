"""Unit tests for nx_lib.views.generali.documents.days_in_range.

The dashboard's daily average and its trend x-axis both run over this list.
Before #249 both were derived from the query result instead, so a range with
missing days was divided by a smaller denominator and scored a *higher*
average than a complete one.
"""

from nx_lib.views.generali.documents import days_in_range


def test_single_day_range_is_one_label():
    assert days_in_range("2026-07-05", "2026-07-05") == ["2026-07-05"]


def test_range_includes_both_bounds():
    assert days_in_range("2026-07-01", "2026-07-04") == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-04",
    ]


def test_full_month_yields_every_calendar_day():
    days = days_in_range("2026-07-01", "2026-07-31")
    assert len(days) == 31
    # the 11-day hole that exposed the bug is present, not skipped
    assert "2026-07-04" in days
    assert "2026-07-14" in days


def test_time_part_is_ignored():
    # the endpoint hands over "2026-07-01 00:00:00" after replacing the T
    assert days_in_range("2026-07-01 00:00:00", "2026-07-03 23:59:59") == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
    ]


def test_range_spanning_a_month_boundary():
    assert days_in_range("2026-06-29", "2026-07-02") == [
        "2026-06-29",
        "2026-06-30",
        "2026-07-01",
        "2026-07-02",
    ]


def test_leap_day_is_included():
    assert "2028-02-29" in days_in_range("2028-02-27", "2028-03-01")


def test_inverted_range_yields_nothing():
    assert days_in_range("2026-07-31", "2026-07-01") == []


def test_unparsable_bounds_yield_nothing():
    # callers fall back to the observed days rather than crashing
    assert days_in_range("not-a-date", "2026-07-01") == []
    assert days_in_range("2026-07-01", "") == []
    assert days_in_range(None, None) == []
