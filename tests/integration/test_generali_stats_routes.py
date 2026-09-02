"""Integration tests for the Generali stats/filter-options endpoints:
missing-date handling, 120s response caching (beautify phase-2c Task 5), and
that error/validation responses are never cached.

Regression for: api_generali_stats (nx_lib/views/generali.py) called
`.replace("T", " ")` directly on `request.args.get("startDate")` /
`("endDate")`. When either query param is absent, `.get()` returns None and
`.replace` raises AttributeError -> unhandled 500, instead of a clean 400.

Session permissions are reloaded from the DB on EVERY request by
nx_lib.hooks._reload_user_permissions (a before_request hook), so the
permission set for the logged-in test user must be patched at the source
(nx_lib.hooks.load_permissions_for_user) rather than via session_transaction,
which would just be clobbered on the next request (same seam used by
tests/integration/test_generali_pdqm_routes.py).

The missing-params check happens before the endpoint ever touches
engine_generali_db, so those tests stay hermetic by construction. The caching
tests below wire a lightweight fake engine (same shape as
test_generali_pdqm_routes._FakeEngine) so a query-count assertion can prove
a second call within the 120s TTL never re-hits the DB -- SimpleCache is
process-global, so the autouse _clear_response_cache fixture (precedent:
tests/integration/test_dashboard_routes.py) wipes it before every test.
"""

import pytest

import nx_lib.hooks as hooks
import nx_lib.views.generali as gv
from nx_lib.extensions import cache


def _grant_perms(monkeypatch, perms):
    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: list(perms))


@pytest.fixture(autouse=True)
def _clear_response_cache(app):
    """MUST clear inside app.app_context() -- see test_dashboard_routes' fixture
    of the same name for why a bare cache.clear() is unsafe."""
    with app.app_context():
        cache.clear()
    yield


def test_stats_missing_both_dates_returns_400(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["generali.dashboard.view"])

    resp = user_client.get("/api/generali/stats")

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"]


def test_stats_missing_end_date_returns_400(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["generali.dashboard.view"])

    resp = user_client.get("/api/generali/stats?startDate=2026-01-01T00:00:00")

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"]


def test_stats_missing_start_date_returns_400(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["generali.dashboard.view"])

    resp = user_client.get("/api/generali/stats?endDate=2026-01-31T00:00:00")

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"]


# ============================ caching ====================================== #


class _CountingCursor:
    """Returns empty result sets for every query shape api_generali_stats /
    api_generali_filter_options issue, while counting cursor.execute calls so
    tests can assert the DB was (or was not) re-hit."""

    def __init__(self, calls):
        self._calls = calls

    def execute(self, sql, params=None):
        self._calls.append((" ".join(sql.split()), list(params or [])))

    def fetchone(self):
        # kpi_row = COUNT(*), NK1_Pass, NK2_Pass, NK1_NK2_Pass
        return (0, 0, 0, 0)

    def fetchall(self):
        return []

    def close(self):
        pass


class _CountingConn:
    def __init__(self, calls):
        self._calls = calls

    def cursor(self):
        return _CountingCursor(self._calls)

    def close(self):
        pass


class _CountingEngine:
    """raw_connection() call count IS the query-count signal used below: one
    request == one raw_connection() (see finally: conn.close() in the view),
    so counting connections is equivalent to counting "did this request hit
    the DB" without needing to track statement-level SQL shape matching."""

    def __init__(self):
        self.connect_count = 0
        self._calls = []

    def raw_connection(self):
        self.connect_count += 1
        return _CountingConn(self._calls)


def test_stats_second_call_within_ttl_does_not_rehit_db(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["generali.dashboard.view"])
    fake_engine = _CountingEngine()
    monkeypatch.setattr(gv, "engine_generali_db", fake_engine)

    url = "/api/generali/stats?startDate=2026-01-01T00:00:00&endDate=2026-01-31T00:00:00"
    resp1 = user_client.get(url)
    assert resp1.status_code == 200
    assert fake_engine.connect_count == 1

    resp2 = user_client.get(url)
    assert resp2.status_code == 200
    assert (
        fake_engine.connect_count == 1
    ), "second call within the 120s TTL must be served from cache"
    assert resp2.get_json() == resp1.get_json()


def test_stats_different_filter_bypasses_cache(user_client, monkeypatch):
    """Per-filter cache key: a different date range must not hit the first
    range's cached entry."""
    _grant_perms(monkeypatch, ["generali.dashboard.view"])
    fake_engine = _CountingEngine()
    monkeypatch.setattr(gv, "engine_generali_db", fake_engine)

    user_client.get("/api/generali/stats?startDate=2026-01-01T00:00:00&endDate=2026-01-31T00:00:00")
    assert fake_engine.connect_count == 1

    user_client.get("/api/generali/stats?startDate=2026-02-01T00:00:00&endDate=2026-02-28T00:00:00")
    assert (
        fake_engine.connect_count == 2
    ), "a different filter must re-hit the DB, not reuse the cache"


def test_stats_error_response_is_not_cached(user_client, monkeypatch):
    """A missing-date 400 must never be pinned in the 120s cache."""
    _grant_perms(monkeypatch, ["generali.dashboard.view"])
    fake_engine = _CountingEngine()
    monkeypatch.setattr(gv, "engine_generali_db", fake_engine)

    resp1 = user_client.get("/api/generali/stats")
    assert resp1.status_code == 400
    assert fake_engine.connect_count == 0  # never reaches the DB for this path

    url = "/api/generali/stats?startDate=2026-01-01T00:00:00&endDate=2026-01-31T00:00:00"
    resp2 = user_client.get(url)
    assert resp2.status_code == 200
    assert fake_engine.connect_count == 1

    resp3 = user_client.get(url)
    assert resp3.status_code == 200
    assert fake_engine.connect_count == 1


def test_filter_options_second_call_within_ttl_does_not_rehit_db(user_client, monkeypatch):
    _grant_perms(monkeypatch, ["generali.documentlist.view"])
    fake_engine = _CountingEngine()
    monkeypatch.setattr(gv, "engine_generali_db", fake_engine)

    resp1 = user_client.get("/api/generali/filter_options")
    assert resp1.status_code == 200
    assert fake_engine.connect_count == 1

    resp2 = user_client.get("/api/generali/filter_options")
    assert resp2.status_code == 200
    assert fake_engine.connect_count == 1
    assert resp2.get_json() == resp1.get_json()
