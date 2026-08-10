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
import types
from datetime import date
from unittest.mock import MagicMock

import nx_lib.views.api_external as ax
import nx_lib.views.dashboard as dv
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


def test_every_api_v1_route_requires_auth(client):
    """Security #193: the /api/v1 surface is exempt from session/CSRF and its
    auth is applied per-view via @require_api_key -- so a future route added
    without the decorator would ship fully unauthenticated. Enforce that EVERY
    /api/v1 (and /api/test/v1) route rejects an unauthenticated caller with a
    401, so that regression fails CI instead of shipping."""
    app = client.application
    api_rules = [
        r
        for r in app.url_map.iter_rules()
        if (r.rule.startswith("/api/v1/") or r.rule.startswith("/api/test/v1/"))
        and "<" not in r.rule
    ]
    assert api_rules, "expected at least one /api/v1 route to exist"
    for r in api_rules:
        method = "GET" if "GET" in r.methods else next(iter(r.methods - {"HEAD", "OPTIONS"}))
        resp = client.open(r.rule, method=method)
        assert resp.status_code == 401, (
            f"{method} {r.rule} did not require auth (got {resp.status_code}); "
            f"a new /api/v1 route may be missing @require_api_key"
        )


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

    def _fake_compute(target_processes, *, strict=False):
        seen["processes"] = target_processes
        seen["strict"] = strict
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
        # Task 58: the external API must always request the strict contract
        # so a Statistics-DB outage raises instead of degrading to zeros.
        assert seen["strict"] is True
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

    def _boom(target_processes, *, strict=False):
        raise RuntimeError("StatisticsDB exploded")

    monkeypatch.setattr(ax, "compute_today_stats", _boom)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Stats backend unavailable"}
    finally:
        _delete_key(key_hash)


# ------------- Task 58: Statistics-DB outage vs a genuinely quiet day ------- #
# The two tests above (`test_stats_backend_error_returns_500_json` /
# `test_good_key_returns_scoped_stats_and_stamps_last_used`) monkeypatch
# compute_today_stats itself, which only proves the view's try/except wiring.
# These exercise compute_today_stats FOR REAL (only its DB engines faked) to
# prove the underlying stat-row legs actually distinguish "outage" from
# "healthy query, no rows today" -- the bug this task fixes was that both
# looked identical ([] from the leg) and always produced 200 zeros.


def _engine_returning(rows):
    """Fake engine: raw_connection().cursor().fetchall() -> rows."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


def _dead_engine(msg="StatisticsDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


def _cfg_row(client_code, name, table, exp, imp):
    return types.SimpleNamespace(
        ClientCode=client_code,
        ProcessName=name,
        TableName=table,
        ExportColumn=exp,
        ImportColumn=imp,
        additionalCondition=None,
    )


def test_statistics_db_outage_returns_500_not_zeros(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    cfg = _cfg_row("default", "sydoc.TestProc", "dbo.tblTest", "ExportDate", "ImportDate")
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([cfg]))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine("Statistics DB down"))
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Stats backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_genuinely_quiet_day_still_returns_200_zeros(client, monkeypatch):
    # Healthy engine, zero matching rows today: SUM(...) with no GROUP BY
    # still returns exactly one row of NULLs -- must NOT be treated as an
    # outage. Proves the fix isn't just "always 500 now".
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    cfg = _cfg_row("default", "sydoc.TestProc", "dbo.tblTest", "ExportDate", "ImportDate")
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([cfg]))
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["imported_today"] == 0
        assert body["exported_today"] == 0
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


# --------------------------- JSON error handlers --------------------------- #


# ------------------------------- /api/v1/backlog --------------------------- #

BACKLOG_URL = "/api/v1/backlog"


def test_backlog_no_auth_header_returns_401_json(client):
    resp = client.get(BACKLOG_URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_backlog_good_key_returns_scoped_count_and_stamps_last_used(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_total(pairs):
        seen["pairs"] = pairs
        return 154

    monkeypatch.setattr(ax, "total_backlog_count", _fake_total)
    try:
        resp = client.get(BACKLOG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["current_backlog"] == 154
        assert "datetime" in body
        assert "processes" not in body
        assert seen["pairs"] == [("sydoc", "Other"), ("sydoc", "TestProc")]
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_backlog_empty_process_scope_returns_zero_without_compute(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(pairs):
        raise AssertionError("total_backlog_count must not run for an empty scope")

    monkeypatch.setattr(ax, "total_backlog_count", _must_not_be_called)
    try:
        resp = client.get(BACKLOG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json()["current_backlog"] == 0
    finally:
        _delete_key(key_hash)


def test_backlog_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _boom(pairs):
        raise RuntimeError("backlog source exploded")

    monkeypatch.setattr(ax, "total_backlog_count", _boom)
    try:
        resp = client.get(BACKLOG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Backlog backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_backlog_post_method_not_allowed(client):
    resp = client.post(BACKLOG_URL)
    assert resp.status_code == 405


def test_unknown_api_v1_path_returns_json_404(client):
    resp = client.get("/api/v1/definitely/not/a/route")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json() == {"error": "Not found"}


def test_non_api_404_still_renders_html(client):
    resp = client.get("/definitely-not-a-page")
    assert resp.status_code == 404
    assert "text/html" in resp.content_type


# ------------------------- /api/test/v1 sandbox twins ---------------------- #
# No compute_today_stats/total_backlog_count monkeypatching needed: these
# routes never touch a data backend, only real auth against dbo.ApiKeys.

TEST_STATS_URL = "/api/test/v1/stats/today"
TEST_BACKLOG_URL = "/api/test/v1/backlog"


def test_test_stats_no_auth_header_returns_401_json(client):
    resp = client.get(TEST_STATS_URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_test_stats_good_key_returns_random_data_in_real_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    try:
        resp = client.get(TEST_STATS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["date"] == date.today().isoformat()
        assert isinstance(body["imported_today"], int)
        assert isinstance(body["exported_today"], int)
        assert 0 <= body["exported_today"] <= body["imported_today"]
        assert body["processes"] == ["sydoc.TestProc", "sydoc.Other"]
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_test_backlog_no_auth_header_returns_401_json(client):
    resp = client.get(TEST_BACKLOG_URL)
    assert resp.status_code == 401
    assert resp.is_json


def test_test_backlog_good_key_returns_random_data_in_real_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        resp = client.get(TEST_BACKLOG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "datetime" in body
        assert isinstance(body["current_backlog"], int)
        assert "processes" not in body
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_test_stats_post_method_not_allowed(client):
    resp = client.post(TEST_STATS_URL)
    assert resp.status_code == 405


def test_unknown_api_test_v1_path_returns_json_404(client):
    resp = client.get("/api/test/v1/definitely/not/a/route")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json() == {"error": "Not found"}
