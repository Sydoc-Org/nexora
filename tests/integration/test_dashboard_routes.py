"""Integration tests for nx_lib.views.dashboard — page + KPI APIs + recent
activity.

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
- GET  /api/dashboard/recent_activity        early-empty (returns [])
"""

from datetime import datetime

import pytest

import nx_lib.hooks
import nx_lib.views.dashboard as dv
import nx_lib.views.workitems as wv
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
# can surface the wrong client's fields. The autouse _clear_response_cache
# fixture wipes the (userid, process_name_dashboard)-keyed entries first --
# SimpleCache is process-global, same trap the section below documents.


def test_recent_activity_forwards_row_client_as_hint(user_client, monkeypatch):
    """A row for a colliding id carries client='ms02' — that must reach
    get_domain_for_workitem as client_hint, not be silently dropped."""
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "process.ms02.TestProc.view"],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", dict)

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
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "process.sydoc.TestProc.view"],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", dict)

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


# --------------------- sensitive doc-fields must not leak (Task 16) --------- #
# The activity feed read raw Octo `fields` straight through with no strip,
# unlike every other surface that shows doc-fields (workitems.filter.
# documentfields.sensitive). Caller without the perm must not see a
# sensitive-configured field's value.


def test_recent_activity_strips_sensitive_fields_without_perm(user_client, monkeypatch):
    """Caller WITHOUT workitems.filter.docfields.sensitive.view: a sensitive-
    configured field must be absent from the row's fields, not leaked."""
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "process.sydoc.TestProc.view"],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", dict)
    monkeypatch.setattr(wv, "get_sensitive_field_tokens", lambda: {"pid"})

    row = {
        "id": 444,
        "modifiedat": datetime(2026, 7, 20, 9, 30),
        "process": "TestProc",
        "client": "sydoc",
    }
    monkeypatch.setattr(dv, "recent_activity_rows", lambda *a, **k: [row])
    monkeypatch.setattr(
        dv, "get_domain_for_workitem", lambda wid, client_hint=None: "domain.example.com"
    )
    monkeypatch.setattr(dv, "get_workitemdata_param", lambda wid, domain: ("wdata", "docid"))
    monkeypatch.setattr(
        dv,
        "get_extensions_urls_fields",
        lambda workitemdata, document_id, domain: (
            None,
            None,
            {"PID": "12345", "Notes": "hello"},
            None,
            None,
        ),
    )

    resp = user_client.get("/api/dashboard/recent_activity")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["fields"] == {"Notes": "hello"}


# --------------------- every row must carry its client (Task 16) ------------ #
# Rows carried no `client` key in the JSON response, so a colliding-id
# click-through (see D9 tests above, which cover the server-side hint
# forwarding) could not disambiguate on the front end either.


def test_recent_activity_rows_include_client_key(user_client, monkeypatch):
    """Every emitted row carries its source client, not just internally for
    the domain-hint lookup -- the front-end deep link needs it too."""
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "process.ms02.TestProc.view"],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", dict)

    row = {
        "id": 1216,
        "modifiedat": datetime(2026, 7, 20, 9, 30),
        "process": "TestProc",
        "client": "ms02",
    }
    monkeypatch.setattr(dv, "recent_activity_rows", lambda *a, **k: [row])
    monkeypatch.setattr(
        dv, "get_domain_for_workitem", lambda wid, client_hint=None: "ms02-domain.example.com"
    )
    monkeypatch.setattr(dv, "get_workitemdata_param", lambda wid, domain: ("wdata", "docid"))
    monkeypatch.setattr(
        dv,
        "get_extensions_urls_fields",
        lambda workitemdata, document_id, domain: (None, None, {}, None, None),
    )

    resp = user_client.get("/api/dashboard/recent_activity")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["client"] == "ms02"


# --------------------- phase-review fix: cross-product pair derivation ------ #
# api_recent_activity() built two separately-uniqued proc/client lists from
# target_processes -- the SAME cross-product bug Task 14 (cc167e1) fixed for
# the workitems list, but independently, since this call site feeds
# recent_activity_rows()/backlog_count(), not list_workitems(). A caller
# granted only (A, P1) and (B, P2) must never let (A, P2)/(B, P1) reach the
# source layer.


def test_recent_activity_route_derives_granted_pairs_not_cross_product(user_client, monkeypatch):
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: [
            "dashboard.view",
            "process.A.P1.view",
            "process.B.P2.view",
        ],
    )
    monkeypatch.setattr(dv, "get_activity_instances_to_ignore", dict)

    calls = []

    def _fake_recent_activity_rows(pairs, activity_ignore_map, top=3):
        calls.append(pairs)
        return []

    monkeypatch.setattr(dv, "recent_activity_rows", _fake_recent_activity_rows)

    resp = user_client.get("/api/dashboard/recent_activity")
    assert resp.status_code == 200
    assert len(calls) == 1
    built_pairs = calls[0]
    assert sorted(built_pairs) == [("A", "P1"), ("B", "P2")]
    assert ("A", "P2") not in built_pairs
    assert ("B", "P1") not in built_pairs


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
