"""Unit tests for nx_lib.views.generali.documents.resolve_date_window.

The Generali dashboard used to answer a missing date bound with a 400, which
the page rendered as nothing at all: every KPI blank, no chart, no explanation.
That 400 was itself an improvement — before it, `.replace` on ``None`` raised
and the request 500'd — but refusing the request was never the useful answer
when there is an obvious window to show.

These pin the filling-in, not the formatting. The rule that matters is that a
bound the caller *did* supply is never second-guessed: an explicit range has to
keep meaning exactly what it says, or a report someone reconciles against a
spreadsheet quietly stops matching it.
"""

from datetime import datetime, timedelta

from nx_lib.views.generali.documents import DEFAULT_RANGE_DAYS, resolve_date_window

NOW = datetime(2026, 9, 14, 13, 5, 9)


def test_no_dates_gives_the_default_window_ending_now():
    start, end = resolve_date_window(None, None, now=NOW)
    assert end == "2026-09-14 13:05:09"
    assert start == "2026-08-15 00:00:00"
    assert (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days == (
        DEFAULT_RANGE_DAYS
    )


def test_missing_end_runs_to_the_current_clock_not_end_of_day():
    """A day still in progress must not be padded out to 23:59:59.

    Asking for hours that have not happened yet reports them as a quiet
    stretch rather than as a day still filling up.
    """
    _start, end = resolve_date_window("2026-01-01 00:00:00", None, now=NOW)
    assert end == "2026-09-14 13:05:09"


def test_missing_start_counts_back_from_the_supplied_end():
    """Not from today — the caller named the end, so it anchors the window."""
    start, end = resolve_date_window(None, "2026-01-31 23:59:59", now=NOW)
    assert end == "2026-01-31 23:59:59"
    assert start == "2026-01-01 00:00:00"


def test_defaulted_start_begins_at_midnight_so_the_first_day_is_whole():
    start, _end = resolve_date_window(None, None, now=NOW)
    assert start.endswith(" 00:00:00")


def test_supplied_bounds_are_passed_through_untouched():
    start, end = resolve_date_window("2026-03-01 08:30:00", "2026-03-05 17:45:00", now=NOW)
    assert (start, end) == ("2026-03-01 08:30:00", "2026-03-05 17:45:00")


def test_the_t_separator_is_still_normalised():
    """The page sends ISO-with-T; the driver wants a space."""
    start, end = resolve_date_window("2026-01-01T00:00:00", "2026-01-31T23:59:59", now=NOW)
    assert (start, end) == ("2026-01-01 00:00:00", "2026-01-31 23:59:59")


def test_blank_and_whitespace_bounds_count_as_missing():
    """Clearing the field yields "", not an absent param."""
    assert resolve_date_window("", "   ", now=NOW) == resolve_date_window(None, None, now=NOW)


def test_an_unparsable_end_is_not_swallowed():
    """It still reaches the driver, and the start falls back to *now*.

    Quietly replacing a malformed bound with a plausible window would hide a
    caller bug behind a chart that looks fine.
    """
    start, end = resolve_date_window(None, "not-a-date", now=NOW)
    assert end == "not-a-date"
    assert start == (NOW - timedelta(days=DEFAULT_RANGE_DAYS)).strftime("%Y-%m-%d 00:00:00")


def test_window_matches_the_span_the_page_opens_with():
    """`setDefaultDates` in the JS partial uses the same span.

    If these drift, clearing a date field returns a different range than the
    one the dashboard loaded with, and nothing on screen says so.
    """
    partial = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "templates"
        / "js"
        / "_generali_dashboard_js.html"
    ).read_text(encoding="utf-8")
    assert f"start.setDate(end.getDate() - {DEFAULT_RANGE_DAYS});" in partial
