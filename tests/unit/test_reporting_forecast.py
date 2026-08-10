"""Unit tests for nx_lib.reporting.forecast — pure math, no DB/Flask."""

import datetime

from nx_lib.reporting.forecast import (
    MIN_POINTS,
    _next_buckets,
    compute_forecast,
    forecast_export_rows,
    forecast_series,
)


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


def _definition(horizon="auto"):
    return {
        "source": "backlog_history",
        "columns": [{"field": "SnapshotAt", "grain": "month"}],
        "metrics": [{"metric": "backlog_total"}],
        "forecast": {"enabled": True, "horizon": horizon},
    }


_COLS = [{"field": "SnapshotAt"}, {"field": "backlog_total"}]


def _rows(n=8):
    return [[f"{2025 + (i // 12):04d}-{i % 12 + 1:02d}-01", 10 + 2 * i] for i in range(n)]


def test_compute_forecast_happy_path():
    fc = compute_forecast(_definition(horizon=3), _COLS, _rows())
    assert "unavailable" not in fc
    assert fc["grain"] == "month" and fc["horizon"] == 3
    assert fc["anchor"] == "2025-08-01"
    assert fc["buckets"] == ["2025-09-01", "2025-10-01", "2025-11-01"]
    assert fc["series"][0]["field"] == "backlog_total"
    assert [round(v) for v in fc["series"][0]["values"]] == [26, 28, 30]


def test_compute_forecast_zero_fills_missing_buckets():
    rows = _rows(8)
    del rows[3]  # a month with no snapshot rows at all
    fc = compute_forecast(_definition(horizon=2), _COLS, rows)
    assert "unavailable" not in fc
    # the gap was filled with 0, so the fit saw 8 contiguous buckets
    assert fc["anchor"] == "2025-08-01"


def test_compute_forecast_auto_horizon_scales_with_history():
    fc = compute_forecast(_definition(), _COLS, _rows(16))
    assert fc["horizon"] == 4  # max(3, round(16/4))


def test_compute_forecast_auto_horizon_resolves_from_visible_rows():
    # A widened lookback refit (#178) must change fit quality only — the
    # auto horizon has to track what the user actually sees (`visible_rows`),
    # not the wider series that only exists to improve the fit.
    visible = _rows(16)  # -> horizon max(3, round(16/4)) == 4
    widened = _rows(64)  # would resolve to max(3, round(64/4)) == 16 if unguarded
    fc = compute_forecast(_definition(), _COLS, widened, visible_rows=visible)
    assert fc["horizon"] == 4
    # Sanity: without the visible_rows override, the widened series alone
    # really would have produced a much larger horizon.
    assert compute_forecast(_definition(), _COLS, widened)["horizon"] == 16


def test_compute_forecast_rejects_wrong_shape():
    two_dims = _definition()
    two_dims["columns"].append({"field": "ProcessName"})
    assert compute_forecast(two_dims, _COLS, _rows())["unavailable"] == "shape"
    no_grain = _definition()
    del no_grain["columns"][0]["grain"]
    assert compute_forecast(no_grain, _COLS, _rows())["unavailable"] == "shape"


def test_compute_forecast_insufficient_history():
    assert compute_forecast(_definition(), _COLS, _rows(3))["unavailable"] == "insufficient_history"


def test_forecast_export_rows_marks_predictions():
    fc = compute_forecast(_definition(horizon=2), _COLS, _rows())
    cols2, rows2, start = forecast_export_rows(_COLS, _rows(), fc)
    assert cols2[-1] == {"field": "__forecast", "header": "Forecast"}
    assert start == 8 and len(rows2) == 10
    assert rows2[0][-1] == "" and rows2[-1][-1] == "forecast"
    assert rows2[8][0] == "2025-09-01" and round(rows2[8][1]) == 26
