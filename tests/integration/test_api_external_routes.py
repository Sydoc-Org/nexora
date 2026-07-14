"""Integration tests for the external machine-to-machine API v1
(nx_lib/views/api_external.py + nx_lib/api_auth.py).

dbo.ApiKeys EXISTS in the TEST schema (mirror added alongside migration
0038), so the auth paths run for real against NEXORA_TEST. The db_conn
fixture's rolled-back transaction is INVISIBLE to the app's separate
raw_connection()s, so key rows are committed directly and deleted in a
finally. The 200 path monkeypatches only compute_today_stats -- TEST has
no Statconfig table and no Statistics DB (precedent:
tests/integration/test_dashboard_routes.py).

No login fixtures: this API never touches the session.
"""

import hashlib
import secrets
from datetime import date

import nx_lib.views.api_external as ax
from nx_lib.db import engine_nexora_db

URL = "/api/v1/stats/today"


def _insert_key(raw_key, client_code="testclient", processes="sydoc.TestProc", enabled=1):
    """Commit an ApiKeys row the app can see; returns the KeyHash for cleanup."""
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ApiKeys (KeyHash, ClientCode, Label, ProcessList, Enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            [key_hash, client_code, "pytest temp key", processes, enabled],
        )
        conn.commit()
    finally:
        conn.close()
    return key_hash


def _delete_key(key_hash):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ApiKeys WHERE KeyHash = ?", [key_hash])
        conn.commit()
    finally:
        conn.close()


def _last_used(key_hash):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LastUsedAt FROM dbo.ApiKeys WHERE KeyHash = ?", [key_hash])
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_no_auth_header_returns_401_json(client):
    resp = client.get(URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_non_bearer_scheme_returns_401_json(client):
    resp = client.get(URL, headers={"Authorization": "Basic Zm9vOmJhcg=="})
    assert resp.status_code == 401
    assert resp.is_json


def test_unknown_key_returns_401_json(client):
    resp = client.get(URL, headers={"Authorization": f"Bearer {secrets.token_urlsafe(32)}"})
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Invalid API key"}


def test_disabled_key_gets_the_same_401(client):
    # Uniform 401 (no existence oracle): revoked == never issued.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, enabled=0)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 401
        assert resp.get_json() == {"error": "Invalid API key"}
    finally:
        _delete_key(key_hash)


def test_post_method_not_allowed(client):
    # GET-only v1 (D1). 405 here because the suite runs WTF_CSRF_ENABLED=False;
    # in PROD the CSRF before_request guard may answer 400 first -- either way
    # a mutating verb is refused before the view runs.
    resp = client.post(URL)
    assert resp.status_code == 405


def test_good_key_returns_scoped_stats_and_stamps_last_used(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_compute(target_processes):
        seen["processes"] = target_processes
        return (12, 8)  # (imported_today, processed_today)

    monkeypatch.setattr(ax, "compute_today_stats", _fake_compute)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {
            "date": date.today().isoformat(),
            "imported_today": 12,
            "exported_today": 8,
            "processes": ["sydoc.TestProc", "sydoc.Other"],
        }
        # Scope comes from the ApiKeys row, whitespace-tolerant.
        assert seen["processes"] == ["sydoc.TestProc", "sydoc.Other"]
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_empty_process_scope_returns_zeros_without_compute(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(target_processes):
        raise AssertionError("compute_today_stats must not run for an empty scope")

    monkeypatch.setattr(ax, "compute_today_stats", _must_not_be_called)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["imported_today"] == 0
        assert body["exported_today"] == 0
        assert body["processes"] == []
    finally:
        _delete_key(key_hash)


def test_stats_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _boom(target_processes):
        raise RuntimeError("StatisticsDB exploded")

    monkeypatch.setattr(ax, "compute_today_stats", _boom)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Stats backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_rate_limit_429_for_unauthenticated_requests(client):
    # SECURITY PIN for the decorator order (@limiter.limit OUTERMOST, D11):
    # the 60/min limit must throttle unauthenticated requests too -- they are
    # the brute-force surface, and each costs a full dbo.ApiKeys scan. With
    # auth outermost, decorated limits (enforced inside the limit wrapper in
    # flask-limiter 3.12) would never run on 401 paths and this test could
    # never pass. The autouse _reset_rate_limiter fixture ran before this
    # test, so the 61st request in-test must 429. Requires an active limiter:
    # do NOT run the suite with NEXORA_DISABLE_RATELIMIT=1 (only the e2e
    # conftest sets it, in its own subprocess). The no-header 401 path never
    # touches the DB, so this stays fast.
    for _ in range(60):
        assert client.get(URL).status_code == 401
    assert client.get(URL).status_code == 429
