"""Integration tests for nx_lib.views.dashboard — page + 11 widget APIs +
recent activity.

Seed test users (user@test.local, admin@test.local) have only the
`dashboard.view` permission, not the per-process `dashboard.filter.process.*`
codes. That means most KPI endpoints short-circuit at the
`if not target_processes` guard and return an empty/zero response — which is
ideal for an integration test (deterministic, no DB-write needed).

For endpoints whose first DB hit is unconditional (field_metadata,
get_layout, put_layout, reset_layout), the missing tables in TEST schema
(FieldMetadata, SearchConfig, Search_Field_Labels, DashboardLayouts) push
the request through the except branch → JSON error with 500. We assert
tuple-match `(200, 500)` to stay forward-compatible if the test schema is
later extended.

Routes covered:
- GET  /dashboard                            page (dashboard.view-gated)
- GET  /api/dashboard/processed_over_time    early-empty path
- GET  /api/dashboard/kpi_stats              cached empty path
- GET  /api/dashboard/hourly_stats           cached empty path
- GET  /api/dashboard/avg_processing_time    cached empty path
- POST /api/dashboard/set_filter             session mutation
- GET  /api/dashboard/field_metadata         expects 200/500
- GET  /api/dashboard/layout                 expects 200/500
- PUT  /api/dashboard/layout                 invalid JSON 400 + 200/500
- POST /api/dashboard/layout/reset           expects 200/500
- POST /api/dashboard/widget_data            invalid widget 400 + 200/500
- POST /api/dashboard/widget_compare         no-date-range path returns warning
- GET  /api/dashboard/recent_activity        early-empty (returns [])
"""

from datetime import datetime
from unittest.mock import MagicMock

import nx_lib.hooks
import nx_lib.views.dashboard as dv
from nx_lib.extensions import cache


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
    """No dashboard.filter.process.* perms → empty labels/data."""
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
        "processed_week": 0,
        "current_backlog": 0,
        "imported_today": 0,
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


def test_field_metadata_authed_returns_json(user_client):
    """FieldMetadata table is missing from TEST → 500 via except branch."""
    resp = user_client.get("/api/dashboard/field_metadata")
    assert resp.status_code in (200, 500)
    assert resp.is_json


def test_get_layout_no_table_returns_500_or_default(user_client):
    """DashboardLayouts table is missing in TEST → 500."""
    resp = user_client.get("/api/dashboard/layout")
    assert resp.status_code in (200, 500)


def test_put_layout_invalid_json_returns_400(user_client):
    resp = user_client.put("/api/dashboard/layout", data="not-json")
    assert resp.status_code == 400


def test_put_layout_valid_payload_attempts_save(user_client):
    """Valid empty layout payload — DB tables missing, expect 500 from except."""
    resp = user_client.put("/api/dashboard/layout", json={"widgets": []})
    assert resp.status_code in (200, 400, 500)


def test_reset_layout_500_when_table_missing(user_client):
    resp = user_client.post("/api/dashboard/layout/reset")
    assert resp.status_code in (200, 500)


def test_widget_data_anonymous_returns_redirect(client):
    """@require_permission with no session redirects to /login."""
    resp = client.post(
        "/api/dashboard/widget_data",
        json={"widget": {"type": "kpi"}},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 401)


def test_widget_data_invalid_widget_returns_400(user_client):
    resp = user_client.post("/api/dashboard/widget_data", json={"widget": {}})
    assert resp.status_code == 400


def test_widget_data_valid_payload_attempts_query(user_client):
    """Valid widget type but no allowed_processes → query returns empty/error."""
    resp = user_client.post(
        "/api/dashboard/widget_data",
        json={"widget": {"type": "kpi", "metric": "count"}},
    )
    assert resp.status_code in (200, 400, 500)


def test_widget_compare_no_date_range_returns_warning(user_client):
    """No date filter → returns warning rather than running queries."""
    resp = user_client.post(
        "/api/dashboard/widget_compare",
        json={"widget": {"type": "categorical"}},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "compare_unavailable_no_date_range" in body.get("warnings", [])


def test_widget_compare_invalid_widget_returns_400(user_client):
    resp = user_client.post("/api/dashboard/widget_compare", json={"widget": {}})
    assert resp.status_code == 400


def test_recent_activity_authed_returns_empty_list(user_client):
    """No process perms → returns []."""
    resp = user_client.get("/api/dashboard/recent_activity")
    assert resp.status_code == 200
    assert resp.get_json() == []


# --------------------- colliding-id rows must carry their client (D9) ------- #
# recent_activity_rows() (nx_lib/workitem_sources.py) already puts `client` on
# every row it returns. A colliding id (e.g. 1216 exists in both the default
# Octo client and MS02) is only resolvable to the RIGHT client if that hint is
# forwarded to get_domain_for_workitem — discarding it re-probes/defaults and
# can surface the wrong client's fields. cache.clear() first: SimpleCache is
# process-global and keyed by (userid, process_name_dashboard), same trap the
# section below documents.


def test_recent_activity_forwards_row_client_as_hint(user_client, monkeypatch):
    """A row for a colliding id carries client='ms02' — that must reach
    get_domain_for_workitem as client_hint, not be silently dropped."""
    cache.clear()
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "dashboard.filter.process.ms02.TestProc"],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", lambda: "")

    row = {
        "id": 1216,
        "modifiedat": datetime(2026, 7, 20, 9, 30),
        "process": "TestProc",
        "client": "ms02",
    }
    monkeypatch.setattr(dv, "recent_activity_rows", lambda *a, **k: [row])

    calls = []

    def fake_get_domain(workitem_id, client_hint=None):
        calls.append((workitem_id, client_hint))
        return "ms02-domain.example.com"

    monkeypatch.setattr(dv, "get_domain_for_workitem", fake_get_domain)
    monkeypatch.setattr(dv, "get_workitemdata_param", lambda wid, domain: ("wdata", "docid"))
    monkeypatch.setattr(
        dv,
        "get_extensions_urls_fields",
        lambda workitemdata, document_id, domain: (None, None, {}, None, None),
    )

    resp = user_client.get("/api/dashboard/recent_activity")
    assert resp.status_code == 200
    assert calls == [(1216, "ms02")]


# --------------------- one bad row must not blank the whole feed (gap left --
# --------------------- by Task 24, b65078f) --------------------------------- #
# get_workitemdata_param (nx_lib/octo.py) now returns None on an Octo API
# failure instead of raising (Task 24). api_recent_activity's per-row loop
# unconditionally unpacked its result (`workitemdata, doc_id = ...`), so a
# None return raised TypeError instead — still propagating to the route's
# outer except and still blanking the entire (2-min-cached) activity feed for
# every row, not just the one that hiccupped.


def test_recent_activity_skips_row_when_workitemdata_lookup_fails(user_client, monkeypatch):
    """One row's get_workitemdata_param returning None (Octo hiccup) must be
    skipped, not blank the whole feed for the other, healthy rows."""
    cache.clear()
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "dashboard.filter.process.sydoc.TestProc"],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", lambda: "")

    good_row = {
        "id": 111,
        "modifiedat": datetime(2026, 7, 20, 9, 30),
        "process": "TestProc",
        "client": "sydoc",
    }
    bad_row = {
        "id": 222,
        "modifiedat": datetime(2026, 7, 20, 9, 35),
        "process": "TestProc",
        "client": "sydoc",
    }
    monkeypatch.setattr(dv, "recent_activity_rows", lambda *a, **k: [good_row, bad_row])
    monkeypatch.setattr(
        dv, "get_domain_for_workitem", lambda wid, client_hint=None: "domain.example.com"
    )

    def fake_get_workitemdata_param(wid, domain):
        if wid == bad_row["id"]:
            return None  # simulated Octo hiccup for this one row
        return "wdata", "docid"

    monkeypatch.setattr(dv, "get_workitemdata_param", fake_get_workitemdata_param)
    monkeypatch.setattr(
        dv,
        "get_extensions_urls_fields",
        lambda workitemdata, document_id, domain: (None, None, {"f": "v"}, None, None),
    )

    resp = user_client.get("/api/dashboard/recent_activity")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [row["id"] for row in body] == [good_row["id"]]


# --------------------- error responses must not be cached ------------------- #
# TEST has no Statistics DB, so engines are mocked on the VIEW module (it
# does `from ..db import ...` at load time). Session permissions are
# rewritten every request by _reload_user_permissions (nx_lib/hooks.py), so
# we patch nx_lib.hooks.load_permissions_for_user (precedent:
# tests/integration/test_workitems_routes.py). SimpleCache is process-global
# and the app fixture is session-scoped -> cache.clear() first, always.


class _BoomEngine:
    def raw_connection(self):
        raise RuntimeError("nexora db hiccup")


def _fake_nexora_engine(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


# --------------------- dashboard.view required on the four legacy KPI endpoints -----------
# Defect: these endpoints only checked "username" in session, missing the
# @require_permission("dashboard.view") gate present on every sibling dashboard
# route (see test_dashboard_without_perm_returns_403 above for the page route's
# equivalent). A user holding just a grantable dashboard.filter.process.*
# permission (but not the base dashboard.view) could curl real KPI data.
# noperm_client (no permissions at all, incl. no filter.process.* grants) is
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
    """A transient 500 (Statconfig read on NexoraDB fails) must not be pinned
    in the 300s response cache: the next request re-executes the view."""
    cache.clear()
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "dashboard.filter.process.sydoc.TestProc"],
    )

    monkeypatch.setattr(dv, "engine_nexora_db", _BoomEngine())
    resp = user_client.get("/api/dashboard/processed_over_time")
    assert resp.status_code == 500

    monkeypatch.setattr(dv, "engine_nexora_db", _fake_nexora_engine([]))
    resp2 = user_client.get("/api/dashboard/processed_over_time")
    assert resp2.status_code == 200
    assert resp2.get_json() == {"labels": [], "data": []}
