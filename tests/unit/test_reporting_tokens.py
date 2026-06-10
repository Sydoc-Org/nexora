"""Unit tests for nx_lib.reporting.tokens — relative-date token resolution."""

import datetime

import pytest

from nx_lib.reporting.tokens import (
    RELATIVE_DATE_TOKENS,
    date_fields_from_catalog,
    resolve_definition_tokens,
    resolve_token,
    validate_token_value,
)

# A Wednesday. ISO week = Mon 2026-06-08 .. Sun 2026-06-14.
TODAY = datetime.date(2026, 6, 10)


def _d(s):
    return datetime.date.fromisoformat(s)


@pytest.mark.parametrize(
    ("token", "start", "end"),
    [
        ("today", "2026-06-10", "2026-06-10"),
        ("yesterday", "2026-06-09", "2026-06-09"),
        ("this_week", "2026-06-08", "2026-06-14"),
        ("last_week", "2026-06-01", "2026-06-07"),
        ("this_month", "2026-06-01", "2026-06-30"),
        ("last_month", "2026-05-01", "2026-05-31"),
        ("this_year", "2026-01-01", "2026-12-31"),
        ("last_year", "2025-01-01", "2025-12-31"),
        # 1st of month-2 .. last day of current month (wizard preset semantics)
        ("last_3_months", "2026-04-01", "2026-06-30"),
    ],
)
def test_fixed_token_resolution(token, start, end):
    assert resolve_token({"token": token}, TODAY) == (_d(start), _d(end))


def test_last_n_days_is_a_rolling_inclusive_window():
    assert resolve_token({"token": "last_n_days", "n": 1}, TODAY) == (TODAY, TODAY)
    assert resolve_token({"token": "last_n_days", "n": 30}, TODAY) == (
        _d("2026-05-12"),
        TODAY,
    )


def test_month_edges_resolve_correctly():
    # Jan: last_month crosses the year boundary.
    assert resolve_token({"token": "last_month"}, _d("2026-01-15")) == (
        _d("2025-12-01"),
        _d("2025-12-31"),
    )
    # March in a leap year: last_month is a 29-day February.
    assert resolve_token({"token": "last_month"}, _d("2028-03-31")) == (
        _d("2028-02-01"),
        _d("2028-02-29"),
    )
    # Week range never depends on DATEFIRST: Monday anchor from a Sunday.
    assert resolve_token({"token": "this_week"}, _d("2026-06-14")) == (
        _d("2026-06-08"),
        _d("2026-06-14"),
    )
    # last_week from a Monday: t - 7 days = prior Monday, ISO week anchors correctly.
    assert resolve_token({"token": "last_week"}, _d("2026-06-08")) == (
        _d("2026-06-01"),
        _d("2026-06-07"),
    )


def test_validate_token_value_matrix():
    assert validate_token_value({"token": "last_month"}) is None
    assert validate_token_value({"token": "last_n_days", "n": 30}) is None
    assert "unknown" in validate_token_value({"token": "last_fortnight"})
    assert validate_token_value("last_month") is not None  # not an object
    assert validate_token_value({"token": "last_n_days"}) is not None  # n missing
    assert validate_token_value({"token": "last_n_days", "n": 0}) is not None
    assert validate_token_value({"token": "last_n_days", "n": 367}) is not None
    assert validate_token_value({"token": "last_n_days", "n": "30"}) is not None
    assert validate_token_value({"token": "last_n_days", "n": True}) is not None
    assert validate_token_value({"token": "last_month", "n": 3}) is not None  # stray n
    assert validate_token_value({"token": "last_month", "x": 1}) is not None  # stray key


def test_unknown_token_error_lists_vocabulary():
    msg = validate_token_value({"token": "nope"})
    assert "last_month" in msg and "last_n_days" in msg


def test_resolve_definition_tokens_expands_to_half_open_pair():
    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "last_month"}},
            {"field": "doctype", "op": "eq", "value": "Invoice"},
        ]
    }
    out = resolve_definition_tokens(rd, TODAY)
    assert out is not rd  # copy when tokens present
    assert out["filters"] == [
        {"field": "import_date", "op": "gte", "value": "2026-05-01"},
        {"field": "import_date", "op": "lt", "value": "2026-06-01"},  # end + 1 day
        {"field": "doctype", "op": "eq", "value": "Invoice"},
    ]
    # The input definition is untouched (the stored JSON keeps its token).
    assert rd["filters"][0]["value"] == {"token": "last_month"}


def test_resolve_definition_tokens_is_identity_without_tokens():
    rd = {"filters": [{"field": "doctype", "op": "eq", "value": "Invoice"}]}
    assert resolve_definition_tokens(rd, TODAY) is rd
    rd_no_filters = {"columns": []}
    assert resolve_definition_tokens(rd_no_filters, TODAY) is rd_no_filters


def test_resolve_definition_tokens_raises_on_bad_token():
    rd = {"filters": [{"field": "d", "op": "between", "value": {"token": "nope"}}]}
    with pytest.raises(ValueError):
        resolve_definition_tokens(rd, TODAY)


def test_date_fields_from_catalog():
    catalog = [
        {"field": "import_date", "type": "string", "grainable": True},  # docprocessing
        {"field": "created", "type": "date"},  # table source
        {"field": "modified", "type": "DATETIME"},  # case-insensitive
        {"field": "doctype", "type": "string"},
    ]
    assert date_fields_from_catalog(catalog) == {"import_date", "created", "modified"}
    assert date_fields_from_catalog(None) == set()


def test_registry_is_the_documented_vocabulary():
    assert set(RELATIVE_DATE_TOKENS) == {
        "today",
        "yesterday",
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "this_year",
        "last_year",
        "last_3_months",
        "last_n_days",
    }
