"""Integration tests for nx_lib.views.dashboard — page + KPI APIs.

Seed test users (user@test.local, admin@test.local) have only the
`dashboard.view` permission, not the per-process `process.<client>.<name>.view`
codes. That means most KPI endpoints short-circuit at the
`if not target_processes` guard and return an empty/zero response — which is
ideal for an integration test (deterministic, no DB-write needed).

Routes covered:
- GET  /dashboard                            page (dashboard.view-gated)
- GET  /api/dashboard/processed_over_time    early-empty path
- GET  /api/dashboard/kpi_stats              cached empty path
- GET  /api/dashboard/hourly_stats           cached empty path
- GET  /api/dashboard/avg_processing_time    cached empty path
- POST /api/dashboard/set_filter             session mutation
"""

import types

import pytest

import nx_lib.hooks
import nx_lib.views.dashboard as dv
import nx_lib.views.tenant as tv
from nx_lib.extensions import cache


@pytest.fixture(autouse=True)
def _clear_response_cache(app):
    """MUST clear inside ``app.app_context()``, never bare ``cache.clear()``:
    outside a context Flask-Caching falls back to whatever app LAST called
    ``cache.init_app()`` -- e.g. test_admin_routes' module-scoped
    ``prod_csp_app`` -- so a bare clear wipes THAT app's backend while requests
    dispatched through this session's ``app`` fixture keep serving earlier
    tests' cached empty responses (and the mocks below never run). Same trap
    documented at test_workitems_routes._clear_view_cache."""
    with app.app_context():
        cache.clear()
    yield


def test_dashboard_anonymous_redirects_to_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_dashboard_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/dashboard")
    assert resp.status_code == 403


def test_dashboard_with_perm_renders(user_client):
    resp = user_client.get("/dashboard")
    assert resp.status_code == 200


def test_dashboard_with_prcfd_query_param(user_client):
    """Unknown process name falls back to 'all'."""
    resp = user_client.get("/dashboard?prcfD=some.fake.process")
    assert resp.status_code == 200
    with user_client.session_transaction() as sess:
        assert sess.get("process_name_dashboard") == "all"


def test_processed_over_time_anonymous_returns_401(client):
    resp = client.get("/api/dashboard/processed_over_time")
    # The decorator @require_permission redirects to /login when no
    # session; with the user gated by perms, the response is 302.
    assert resp.status_code in (302, 401)


def test_processed_over_time_authed_returns_empty(user_client):
    """No process.<client>.<name>.view perms → empty labels/data."""
    resp = user_client.get("/api/dashboard/processed_over_time")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"labels": [], "data": []}


def test_kpi_stats_authed_returns_zeros(user_client):
    """No process perms → all zeros (no DB hit)."""
    resp = user_client.get("/api/dashboard/kpi_stats")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "processed_today": 0,
        "imported_today": 0,
        "current_backlog": 0,
        "prev_imported": 0,
        "prev_processed": 0,
        "prev_backlog": 0,
        "series": {"imported": [], "processed": [], "backlog": []},
    }


def test_hourly_stats_authed_returns_24_zeros(user_client):
    """No process perms → 24 hour buckets of 0."""
    resp = user_client.get("/api/dashboard/hourly_stats")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["labels"]) == 24
    assert body["data"] == [0] * 24


def test_avg_processing_time_authed_returns_empty(user_client):
    resp = user_client.get("/api/dashboard/avg_processing_time")
    assert resp.status_code == 200


def test_set_filter_authed_updates_session(user_client):
    """POST process_name=all sets session.process_name_dashboard."""
    resp = user_client.post(
        "/api/dashboard/set_filter",
        json={"process_name": "all"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["process_name"] == "all"
    with user_client.session_transaction() as sess:
        assert sess.get("process_name_dashboard") == "all"


def test_set_filter_unknown_process_falls_back_to_all(user_client):
    resp = user_client.post(
        "/api/dashboard/set_filter",
        json={"process_name": "unknown.process"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["process_name"] == "all"


# --------------------- error responses must not be cached ------------------- #
# TEST has no Statistics DB, so engines/registry are mocked on the VIEW
# module (it does `from ..db import ...` / `from .. import mapping_config`
# at load time). Session permissions are rewritten every request by
# _reload_user_permissions (nx_lib/hooks.py), so we patch
# nx_lib.hooks.load_permissions_for_user (precedent:
# tests/integration/test_workitems_routes.py). SimpleCache is process-global
# and the app fixture is session-scoped -> _clear_response_cache (autouse)
# wipes it before every test.


# --------------------- dashboard.view required on the four legacy KPI endpoints -----------
# Defect: these endpoints only checked "username" in session, missing the
# @require_permission("dashboard.view") gate present on every sibling dashboard
# route (see test_dashboard_without_perm_returns_403 above for the page route's
# equivalent). A user holding just a grantable process.<client>.<name>.view
# permission (but not the base dashboard.view) could curl real KPI data.
# noperm_client (no permissions at all, incl. no process-scope grants) is
# the strictest case of "missing dashboard.view" and — same as the page route
# — must 403 before any Statconfig/DB work happens, matching this module's own
# "deterministic, no DB-write needed" precedent noted above.


def test_processed_over_time_without_dashboard_view_returns_403(noperm_client):
    resp = noperm_client.get("/api/dashboard/processed_over_time")
    assert resp.status_code == 403


def test_kpi_stats_without_dashboard_view_returns_403(noperm_client):
    resp = noperm_client.get("/api/dashboard/kpi_stats")
    assert resp.status_code == 403


def test_hourly_stats_without_dashboard_view_returns_403(noperm_client):
    resp = noperm_client.get("/api/dashboard/hourly_stats")
    assert resp.status_code == 403


def test_avg_processing_time_without_dashboard_view_returns_403(noperm_client):
    resp = noperm_client.get("/api/dashboard/avg_processing_time")
    assert resp.status_code == 403


def test_processed_over_time_error_response_is_not_cached(user_client, monkeypatch):
    """A transient 500 (mapping_config registry read fails) must not be
    pinned in the 300s response cache: the next request re-executes the
    view."""
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "process.sydoc.TestProc.view"],
    )

    def _boom():
        raise RuntimeError("nexora db hiccup")

    monkeypatch.setattr(dv.mapping_config, "registry", _boom)
    resp = user_client.get("/api/dashboard/processed_over_time")
    assert resp.status_code == 500

    monkeypatch.setattr(dv.mapping_config, "registry", lambda: object())
    monkeypatch.setattr(dv.mapping_config, "sources_for", lambda client, processes=None: [])
    resp2 = user_client.get("/api/dashboard/processed_over_time")
    assert resp2.status_code == 200
    assert resp2.get_json() == {"labels": [], "data": []}


# ------------------------------------------------ tenant-scoped dashboard (0097) --


def _acme(code):
    return types.SimpleNamespace(code=code, display_name="Acme", active=True)


def test_dashboard_unknown_tenant_param_404(user_client, monkeypatch):
    monkeypatch.setattr(tv, "tenant", lambda code: None)
    assert user_client.get("/dashboard?tenant=nope").status_code == 404


def test_dashboard_tenant_param_without_membership_or_grant_403(user_client, monkeypatch):
    monkeypatch.setattr(tv, "tenant", _acme)
    monkeypatch.setattr(tv, "can_view_tenant", lambda code: False)
    assert user_client.get("/dashboard?tenant=acme").status_code == 403


def test_dashboard_tenant_scope_sticks_until_the_global_entry_clears_it(user_client, monkeypatch):
    monkeypatch.setattr(tv, "tenant", _acme)
    monkeypatch.setattr(tv, "can_view_tenant", lambda code: True)
    monkeypatch.setattr("nx_lib.process_helpers.tenant_processes", lambda code: set())
    monkeypatch.setattr(tv, "organization_tenant", lambda org: None)  # staff, no own tenant

    resp = user_client.get("/dashboard?tenant=acme")
    assert resp.status_code == 200
    assert b"Acme Dashboard" in resp.data
    with user_client.session_transaction() as sess:
        assert sess.get("tenant_scope") == "acme"

    # no parameter keeps the scope (a page may rewrite its own URL)
    resp = user_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Acme Dashboard" in resp.data

    # the global sidebar entry sends an explicit empty tenant
    resp = user_client.get("/dashboard?tenant=")
    assert resp.status_code == 200
    assert b"Global Dashboard" in resp.data
    with user_client.session_transaction() as sess:
        assert sess.get("tenant_scope") is None


def test_dashboard_stale_scope_is_dropped_silently(user_client, monkeypatch):
    monkeypatch.setattr(tv, "tenant", lambda code: None)  # remembered tenant vanished
    monkeypatch.setattr(tv, "organization_tenant", lambda org: None)
    with user_client.session_transaction() as sess:
        sess["tenant_scope"] = "gone"
    resp = user_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Global Dashboard" in resp.data
    with user_client.session_transaction() as sess:
        assert sess.get("tenant_scope") is None


def test_dashboard_defaults_to_the_users_own_tenant(user_client, monkeypatch):
    monkeypatch.setattr(tv, "tenant", _acme)
    monkeypatch.setattr(tv, "can_view_tenant", lambda code: True)
    monkeypatch.setattr("nx_lib.process_helpers.tenant_processes", lambda code: set())
    monkeypatch.setattr(tv, "organization_tenant", lambda org: "acme")

    resp = user_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Acme Dashboard" in resp.data
    with user_client.session_transaction() as sess:
        assert sess.get("tenant_scope") == "acme"


def test_backlog_trend_returns_labels_and_capped_series(user_client, monkeypatch):
    """Five processes -> four named series plus one folded "Other"; labels are
    the zero-filled day window, oldest first."""
    from datetime import date, timedelta

    today = date.today()
    names = [f"c.p{i}" for i in range(5)]
    monkeypatch.setattr(dv, "_allowed_processes", lambda: names)
    monkeypatch.setattr(
        dv,
        "_backlog_history",
        lambda tp, days: {
            today - timedelta(days=1): {n: 10 * (i + 1) for i, n in enumerate(names)},
            today: {n: 100 * (i + 1) for i, n in enumerate(names)},
        },
    )

    resp = user_client.get("/api/dashboard/backlog_trend?range=14")
    assert resp.status_code == 200
    body = resp.get_json()

    assert len(body["labels"]) == 14
    assert body["labels"][-1] == today.isoformat()
    assert [s["name"] for s in body["series"]] == ["c.p4", "c.p3", "c.p2", "c.p1", "Other"]
    assert body["series"][0]["values"][-1] == 500
    assert body["series"][-1]["values"][-1] == 100  # the folded remainder
    assert body["total"] == 1500
    assert body["prev_total"] == 150


def test_backlog_trend_collapses_to_one_series_for_a_single_process(user_client, monkeypatch):
    from datetime import date

    today = date.today()
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "_backlog_history", lambda tp, days: {today: {"c.p1": 77}})

    resp = user_client.get("/api/dashboard/backlog_trend")
    body = resp.get_json()
    assert [s["name"] for s in body["series"]] == ["Backlog"]
    assert body["series"][0]["values"][-1] == 77


def test_backlog_trend_empty_when_nothing_is_granted(noperm_client):
    """No grants -> empty payload, not a 500 and not somebody else's numbers."""
    resp = noperm_client.get("/api/dashboard/backlog_trend")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        assert resp.get_json() == {"labels": [], "series": [], "total": 0, "prev_total": 0}


def test_kpi_stats_carries_previous_day_and_seven_point_series(user_client, monkeypatch):
    from datetime import date, timedelta

    today = date.today()
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "compute_today_stats", lambda tp: (595, 60))
    monkeypatch.setattr(dv, "total_backlog_count", lambda pairs: 1247)
    monkeypatch.setattr(
        dv,
        "_kpi_daily_counts",
        lambda tp, days: {
            today - timedelta(days=i): {"imported": 500 + i, "processed": 90 - i}
            for i in range(days - 1, -1, -1)
        },
    )
    monkeypatch.setattr(
        dv,
        "_backlog_history",
        lambda tp, days: {today - timedelta(days=1): {"c.p1": 1199}, today: {"c.p1": 1247}},
    )

    body = user_client.get("/api/dashboard/kpi_stats").get_json()

    assert body["imported_today"] == 595 and body["current_backlog"] == 1247
    assert body["prev_imported"] == 501 and body["prev_processed"] == 89
    assert body["prev_backlog"] == 1199
    assert len(body["series"]["imported"]) == 7
    assert body["series"]["backlog"][-1] == 1247


def test_avg_processing_time_carries_previous_day_and_series(user_client, monkeypatch):
    from datetime import date, timedelta

    today = date.today()
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(
        dv,
        "_avg_processing_by_day",
        lambda tp, days, strict=False: {today: 3600.0, today - timedelta(days=1): 7200.0},
    )

    body = user_client.get("/api/dashboard/avg_processing_time").get_json()

    assert body["avg_display"] == "1.0h"
    assert body["prev_avg_minutes"] == 120.0
    assert len(body["series"]) == 7
    assert body["series"][-1] == 60.0
    assert body["series"][0] is None  # no data that day -> a gap, not a zero


def test_processed_over_time_honours_the_range_parameter(user_client, monkeypatch):
    """?range= widens the zero-filled window; an unlisted value falls back to 14.

    ``_split_stat_configs`` is faked to ([], []) so neither SQL leg runs and the
    response is pure zero-fill -- the label count IS the window under test.
    ``_statconfig_sources`` must stay truthy: an empty config list short-circuits
    to {"labels": [], "data": []} before the window is ever built.
    """
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "_statconfig_sources", lambda tp: [object()])
    monkeypatch.setattr(dv, "_split_stat_configs", lambda configs: ([], []))

    body = user_client.get("/api/dashboard/processed_over_time?range=30").get_json()
    assert len(body["labels"]) == 30

    body = user_client.get("/api/dashboard/processed_over_time?range=7").get_json()
    assert len(body["labels"]) == 14  # not an allowed choice -> default


def test_set_filter_persists_the_range_in_the_session(user_client, monkeypatch):
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "_statconfig_sources", lambda tp: [object()])
    monkeypatch.setattr(dv, "_split_stat_configs", lambda configs: ([], []))

    resp = user_client.post("/api/dashboard/set_filter", json={"process_name": "all", "range": 90})
    assert resp.get_json()["range"] == 90

    # the next request needs no ?range= to stay on 90 days
    body = user_client.get("/api/dashboard/processed_over_time").get_json()
    assert len(body["labels"]) == 90
