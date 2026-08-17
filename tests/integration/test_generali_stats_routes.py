"""Integration test for the Generali stats endpoint's missing-date handling.

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

No DB fake is wired here: the missing-params check happens before the
endpoint ever touches engine_generali_db, so this is hermetic by
construction.
"""

import nx_lib.hooks as hooks


def _grant_perms(monkeypatch, perms):
    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: list(perms))


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
