"""Unit tests for nx_lib.reporting.tokens — relative-date token resolution."""

import datetime

import pytest

from nx_lib.reporting.tokens import (
    RELATIVE_DATE_TOKENS,
    date_fields_from_catalog,
    resolve_definition_tokens,
    resolve_token,
    shifted_definition_for_comparison,
    validate_token_value,
    widened_definition_for_forecast,
)

# A Wednesday. ISO week = Mon 2026-06-08 .. Sun 2026-06-14.
TODAY = datetime.date(2026, 6, 10)

# A Thursday in Q3 2026, used for shifted_definition_for_comparison cases.
COMPARISON_TODAY = datetime.date(2026, 7, 23)


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
        ("this_quarter", "2026-04-01", "2026-06-30"),
        ("last_quarter", "2026-01-01", "2026-03-31"),
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


def test_quarter_edges_resolve_correctly():
    # January: last_quarter crosses the year boundary into Q4.
    assert resolve_token({"token": "last_quarter"}, _d("2026-01-15")) == (
        _d("2025-10-01"),
        _d("2025-12-31"),
    )
    # Last day of a quarter still resolves to its own quarter.
    assert resolve_token({"token": "this_quarter"}, _d("2026-03-31")) == (
        _d("2026-01-01"),
        _d("2026-03-31"),
    )
    # First day of a quarter.
    assert resolve_token({"token": "this_quarter"}, _d("2026-10-01")) == (
        _d("2026-10-01"),
        _d("2026-12-31"),
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
        "this_quarter",
        "last_quarter",
    }


def test_resolved_dates_meta_lists_token_filters_only():
    from nx_lib.views import reporting as rv

    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "last_month"}},
            {"field": "import_date", "op": "between", "value": {"token": "last_n_days", "n": 7}},
            {"field": "doctype", "op": "eq", "value": "Invoice"},
        ]
    }
    meta = rv._resolved_dates_meta(rd)
    assert [m["token"] for m in meta] == ["last_month", "last_n_days"]
    assert meta[0]["field"] == "import_date"
    assert meta[1]["n"] == 7
    start, end = resolve_token({"token": "last_month"})
    assert meta[0]["start"] == start.isoformat()
    assert meta[0]["end"] == end.isoformat()
    assert rv._resolved_dates_meta({"filters": []}) == []


def test_shifted_definition_for_comparison_this_month():
    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "this_month"}},
            {"field": "doctype", "op": "eq", "value": "Invoice"},
        ]
    }
    result = shifted_definition_for_comparison(rd, COMPARISON_TODAY)
    assert result is not None
    shifted_rd, prior_start, prior_end = result
    # July 2026 is a 31-day window; the prior window is shifted back by that
    # same length, i.e. [start - 31d, start) — NOT the naive "previous
    # calendar month" (June is only 30 days, so the two diverge by a day).
    assert prior_start == _d("2026-05-31")
    assert prior_end == _d("2026-06-30")
    assert shifted_rd["filters"] == [
        {"field": "doctype", "op": "eq", "value": "Invoice"},
        {"field": "import_date", "op": "gte", "value": "2026-05-31"},
        {"field": "import_date", "op": "lt", "value": "2026-07-01"},
    ]
    # The input definition is untouched (same contract as resolve_definition_tokens).
    assert rd["filters"][0]["value"] == {"token": "this_month"}


def test_shifted_definition_for_comparison_last_n_days():
    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "last_n_days", "n": 7}},
        ]
    }
    result = shifted_definition_for_comparison(rd, COMPARISON_TODAY)
    assert result is not None
    shifted_rd, prior_start, prior_end = result
    # Current window is 2026-07-17..2026-07-23 (7 days); prior window is the
    # 7 days immediately before that.
    assert prior_start == _d("2026-07-10")
    assert prior_end == _d("2026-07-16")
    assert shifted_rd["filters"] == [
        {"field": "import_date", "op": "gte", "value": "2026-07-10"},
        {"field": "import_date", "op": "lt", "value": "2026-07-17"},
    ]


def test_shifted_definition_for_comparison_this_quarter():
    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "this_quarter"}},
        ]
    }
    result = shifted_definition_for_comparison(rd, COMPARISON_TODAY)
    assert result is not None
    shifted_rd, prior_start, prior_end = result
    # Q3 2026 (Jul-Sep) is a 92-day window; the prior window is the full
    # 92-day length ending exactly at the quarter start (2026-07-01).
    assert prior_start == _d("2026-03-31")
    assert prior_end == _d("2026-06-30")
    assert shifted_rd["filters"] == [
        {"field": "import_date", "op": "gte", "value": "2026-03-31"},
        {"field": "import_date", "op": "lt", "value": "2026-07-01"},
    ]


def test_shifted_definition_for_comparison_no_token_filter_is_none():
    rd = {"filters": [{"field": "doctype", "op": "eq", "value": "Invoice"}]}
    assert shifted_definition_for_comparison(rd, COMPARISON_TODAY) is None
    assert shifted_definition_for_comparison({"filters": []}, COMPARISON_TODAY) is None
    assert shifted_definition_for_comparison({}, COMPARISON_TODAY) is None


def test_shifted_definition_for_comparison_two_token_filters_is_none():
    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "this_month"}},
            {"field": "other_date", "op": "between", "value": {"token": "last_week"}},
        ]
    }
    assert shifted_definition_for_comparison(rd, COMPARISON_TODAY) is None


def test_widened_definition_extends_day_grain_window():
    rd = {
        "columns": [{"field": "import_date", "grain": "day"}],
        "metrics": [{"metric": "doc_count"}],
        "filters": [{"field": "import_date", "op": "between", "value": {"token": "this_month"}}],
        "compare": True,
    }
    today = datetime.date(2026, 8, 6)
    out = widened_definition_for_forecast(rd, today=today)
    assert out is not None and "compare" not in out
    f = out["filters"][0]
    assert f["op"] == "between"
    # this_month resolves to [2026-08-01, 2026-08-31]; day lookback = 56 days
    assert f["value"] == ["2026-06-06", "2026-08-31"]
    # original untouched
    assert rd["filters"][0]["value"] == {"token": "this_month"}


def test_widened_definition_requires_single_grained_dim_and_token():
    base = {
        "columns": [{"field": "import_date", "grain": "day"}],
        "filters": [{"field": "import_date", "op": "between", "value": {"token": "this_month"}}],
    }
    no_grain = {**base, "columns": [{"field": "import_date"}]}
    assert widened_definition_for_forecast(no_grain) is None
    literal = {
        **base,
        "filters": [
            {"field": "import_date", "op": "between", "value": ["2026-08-01", "2026-08-31"]}
        ],
    }
    assert widened_definition_for_forecast(literal) is None
    two_dims = {**base, "columns": base["columns"] + [{"field": "process"}]}
    assert widened_definition_for_forecast(two_dims) is None
