"""Unit tests for nx_lib.reporting.forecast — pure math, no DB/Flask."""

import datetime

from nx_lib.reporting.forecast import MIN_POINTS, _next_buckets, forecast_series


def _days(n, start="2026-06-01"):
    d0 = datetime.date.fromisoformat(start)
    return [d0 + datetime.timedelta(days=i) for i in range(n)]


def _months(n, start="2025-01-01"):
    d0 = datetime.date.fromisoformat(start)
    out = []
    for i in range(n):
        total = d0.year * 12 + (d0.month - 1) + i
        out.append(datetime.date(total // 12, total % 12 + 1, 1))
    return out


def test_pure_trend_is_recovered():
    # y = 10 + 2x over 8 monthly buckets -> next points continue exactly.
    dates = _months(8)
    values = [10 + 2 * i for i in range(8)]
    future, yhat, lower, upper, method = forecast_series(dates, values, "month", 3)
    assert method == "trend"  # 8 < 2*12: seasonal not attempted for month grain
    assert [round(v, 6) for v in yhat] == [26, 28, 30]
    assert future[0] == datetime.date(2025, 9, 1)
    # zero residuals -> zero-width band
    assert all(round(lo, 6) == round(y, 6) for lo, y in zip(lower, yhat, strict=False))


def test_weekday_seasonality_is_recovered():
    # 4 full weeks of a flat series with a weekend dip; day grain, period 7.
    dates = _days(28)
    values = [(2.0 if d.weekday() >= 5 else 10.0) for d in dates]
    future, yhat, lower, upper, method = forecast_series(dates, values, "day", 7)
    assert method == "trend_seasonal"
    by_wd = dict(zip([d.weekday() for d in future], yhat, strict=False))
    assert by_wd[5] < 5 < by_wd[0]  # Saturday predicted low, Monday high


def test_band_widens_with_horizon():
    dates = _months(12)
    values = [10, 13, 11, 15, 12, 16, 13, 18, 14, 19, 16, 20]  # noisy up-trend
    _, yhat, lower, upper, _ = forecast_series(dates, values, "month", 4)
    w = [u - lo for u, lo in zip(upper, lower, strict=False)]
    assert w[0] > 0 and w[-1] > w[0]


def test_nonnegative_series_clamps_lower_at_zero():
    dates = _months(6)
    values = [5, 4, 3, 2, 1, 0]  # steep down-trend crosses zero
    _, yhat, lower, _, _ = forecast_series(dates, values, "month", 4)
    assert all(lo >= 0 for lo in lower)
    assert all(y >= 0 for y in yhat)


def test_too_little_history_returns_none():
    dates = _months(MIN_POINTS - 1)
    assert forecast_series(dates, [1.0] * len(dates), "month", 3) is None


def test_next_buckets_week_and_quarter():
    assert _next_buckets(datetime.date(2026, 8, 3), "week", 2) == [
        datetime.date(2026, 8, 10),
        datetime.date(2026, 8, 17),
    ]
    assert _next_buckets(datetime.date(2026, 10, 1), "quarter", 2) == [
        datetime.date(2027, 1, 1),
        datetime.date(2027, 4, 1),
    ]
