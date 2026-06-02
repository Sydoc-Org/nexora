"""Unit tests for nx_lib.reporting.schedule — pure scheduling helpers."""

from datetime import datetime

import pytest

from nx_lib.reporting.schedule import (
    compute_next_run,
    parse_recipients,
    valid_recipients,
    validate_schedule,
)


def test_parse_recipients_splits_on_separators():
    assert parse_recipients("a@x.com, b@y.com; c@z.com\n d@w.com") == [
        "a@x.com",
        "b@y.com",
        "c@z.com",
        "d@w.com",
    ]


def test_valid_recipients():
    assert valid_recipients("a@x.com, b@y.com")
    assert not valid_recipients("")
    assert not valid_recipients("not-an-email")
    assert not valid_recipients("a@x.com, broken")


def test_daily_next_run_today_then_tomorrow():
    base = {"frequency": "daily", "hour": 6, "minute": 30}
    before = datetime(2026, 6, 3, 5, 0)
    nxt = compute_next_run("daily", 6, 30, None, None, before)
    assert nxt == datetime(2026, 6, 3, 6, 30)
    after = datetime(2026, 6, 3, 7, 0)
    nxt2 = compute_next_run("daily", 6, 30, None, None, after)
    assert nxt2 == datetime(2026, 6, 4, 6, 30)
    assert validate_schedule({**base, "recipients": "a@x.com"}) is None


def test_weekly_next_run_lands_on_weekday():
    # 2026-06-03 is a Wednesday (weekday 2). Ask for Monday (0).
    now = datetime(2026, 6, 3, 8, 0)
    nxt = compute_next_run("weekly", 9, 0, 0, None, now)
    assert nxt.weekday() == 0 and nxt > now
    assert (nxt - now).days in (4, 5)  # next Monday


def test_weekly_same_day_before_and_after():
    now = datetime(2026, 6, 3, 8, 0)  # Wednesday
    # Wednesday (2) at 09:00 is later today.
    assert compute_next_run("weekly", 9, 0, 2, None, now) == datetime(2026, 6, 3, 9, 0)
    # Wednesday at 07:00 already passed -> next week.
    assert compute_next_run("weekly", 7, 0, 2, None, now) == datetime(2026, 6, 10, 7, 0)


def test_monthly_this_month_then_next():
    now = datetime(2026, 6, 3, 8, 0)
    assert compute_next_run("monthly", 6, 0, None, 15, now) == datetime(2026, 6, 15, 6, 0)
    after = datetime(2026, 6, 20, 8, 0)
    assert compute_next_run("monthly", 6, 0, None, 15, after) == datetime(2026, 7, 15, 6, 0)


def test_monthly_december_rolls_to_january():
    now = datetime(2026, 12, 20, 8, 0)
    assert compute_next_run("monthly", 6, 0, None, 5, now) == datetime(2027, 1, 5, 6, 0)


def test_unknown_frequency_raises():
    with pytest.raises(ValueError):
        compute_next_run("yearly", 6, 0, None, None, datetime(2026, 6, 3))


def test_validate_schedule_errors():
    assert validate_schedule({"frequency": "daily", "hour": 6, "recipients": "a@x.com"}) is None
    assert validate_schedule({"frequency": "hourly", "hour": 6, "recipients": "a@x.com"})
    assert validate_schedule({"frequency": "daily", "hour": 30, "recipients": "a@x.com"})
    assert validate_schedule({"frequency": "daily", "hour": 6, "recipients": "bad"})
    assert validate_schedule(
        {"frequency": "daily", "hour": 6, "recipients": "a@x.com", "format": "pdf"}
    )
    # weekly needs a weekday, monthly needs a day-of-month
    assert validate_schedule({"frequency": "weekly", "hour": 6, "recipients": "a@x.com"})
    assert (
        validate_schedule({"frequency": "weekly", "hour": 6, "recipients": "a@x.com", "weekday": 0})
        is None
    )
    assert validate_schedule({"frequency": "monthly", "hour": 6, "recipients": "a@x.com"})
    assert (
        validate_schedule(
            {"frequency": "monthly", "hour": 6, "recipients": "a@x.com", "dayOfMonth": 15}
        )
        is None
    )
