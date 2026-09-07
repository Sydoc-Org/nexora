"""Integration tests for the Generali stats endpoint's day coverage (#249).

`api_generali_stats` used to derive the trend x-axis -- and the daily-average
denominator -- from the rows the trend query returned, so days with no rows
simply did not exist. Two consequences, both reproduced below:

  * the average was divided by days-with-data instead of days-in-range, so a
    range missing a third of its days scored a HIGHER daily average than a
    complete one;
  * the chart plotted the surviving days adjacently, drawing 03.07 next to
    15.07 as if they were consecutive and hiding an 11-day outage.

Permissions are patched at nx_lib.hooks.load_permissions_for_user because a
before_request hook reloads them from the DB on every request -- same seam as
tests/integration/test_generali_stats_routes.py.

The engine is faked at the package attribute (nx_lib.views.generali), which is
what the endpoint's local `from . import engine_generali_db` re-resolves.
"""

from datetime import date

import pytest

import nx_lib.hooks as hooks
import nx_lib.views.generali as gv
from nx_lib.extensions import cache


@pytest.fixture(autouse=True)
def _clear_response_cache(app):
    """The stats endpoint is @cache.cached per user+filter (60 s); these tests
    re-wire the data between calls. Same fixture as test_generali_stats_routes."""
    with app.app_context():
        cache.clear()
    yield


def _grant_perms(monkeypatch, perms):
    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: list(perms))


class _FakeStatsCursor:
    """Answers the query shapes api_generali_stats issues, in order.

    Only the KPI aggregate and the daily trend carry data; every other
    breakdown returns no rows, which the endpoint renders as empty chart
    dicts.
    """

    def __init__(self, kpi_row, trend_rows):
        self._kpi_row = kpi_row
        self._trend_rows = trend_rows
        self._result = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if "as TotalDocs" in normalized:
            self._result = [self._kpi_row]
        elif "GROUP BY CAST(DOC_SCANDATUM AS DATE)" in normalized:
            self._result = list(self._trend_rows)
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def raw_connection(self):
        return self._conn


def _wire(monkeypatch, kpi_row, trend_rows):
    cursor = _FakeStatsCursor(kpi_row, trend_rows)
    monkeypatch.setattr(gv, "engine_generali_db", _FakeEngine(_FakeConn(cursor)))


def _get(client, start="2026-07-01", end="2026-07-10"):
    resp = client.get(f"/api/generali/stats?startDate={start}T00:00:00&endDate={end}T23:59:59")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    return body


# 300 docs over a 10-day range, but only two of those days produced rows.
_KPI_ROW = (300, 225, 195, 165)
_TREND_ROWS = [
    (date(2026, 7, 1), "Brief", 100),
    (date(2026, 7, 2), "Brief", 200),
]


def test_average_divides_by_days_in_range_not_days_with_data(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["tenant.generali.view"])
    _wire(monkeypatch, _KPI_ROW, _TREND_ROWS)

    kpis = _get(user_client)["kpis"]

    # 300 / 10 calendar days. The bug divided by the 2 days that had rows
    # and reported 150.0 -- five times too high.
    assert kpis["avg_daily"] == 30.0


def test_coverage_is_reported_alongside_the_average(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["tenant.generali.view"])
    _wire(monkeypatch, _KPI_ROW, _TREND_ROWS)

    kpis = _get(user_client)["kpis"]

    assert kpis["days_in_range"] == 10
    assert kpis["days_with_data"] == 2


def test_trend_axis_keeps_the_empty_days(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["tenant.generali.view"])
    _wire(monkeypatch, _KPI_ROW, _TREND_ROWS)

    trend = _get(user_client)["trend"]

    assert len(trend["labels"]) == 10
    assert trend["labels"][0] == "2026-07-01"
    assert trend["labels"][-1] == "2026-07-10"
    # the gap is present and zero, not absent
    assert "2026-07-05" in trend["labels"]
    assert trend["values"] == [100, 200, 0, 0, 0, 0, 0, 0, 0, 0]


def test_per_kommunikation_series_is_padded_to_the_same_length(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["tenant.generali.view"])
    _wire(monkeypatch, _KPI_ROW, _TREND_ROWS)

    trend = _get(user_client)["trend"]

    # a series shorter than labels would silently misalign in Chart.js
    for series in trend["byKommunikation"].values():
        assert len(series) == len(trend["labels"])
    assert trend["byKommunikation"]["Brief"] == [100, 200, 0, 0, 0, 0, 0, 0, 0, 0]


def test_complete_range_is_unchanged_by_the_fix(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["tenant.generali.view"])
    rows = [(date(2026, 7, d), "Brief", 10) for d in range(1, 11)]
    _wire(monkeypatch, (100, 75, 65, 55), rows)

    body = _get(user_client)

    assert body["kpis"]["avg_daily"] == 10.0
    assert body["kpis"]["days_with_data"] == body["kpis"]["days_in_range"] == 10
    assert body["trend"]["values"] == [10] * 10


def test_rows_outside_the_range_are_dropped_not_fatal(user_client, monkeypatch):
    """Labels no longer come from the rows, so membership is not guaranteed."""
    _grant_perms(monkeypatch, ["tenant.generali.view"])
    rows = [*_TREND_ROWS, (date(2026, 8, 1), "Brief", 999)]
    _wire(monkeypatch, _KPI_ROW, rows)

    body = _get(user_client)

    assert len(body["trend"]["labels"]) == 10
    assert "2026-08-01" not in body["trend"]["labels"]
    assert sum(body["trend"]["values"]) == 300
