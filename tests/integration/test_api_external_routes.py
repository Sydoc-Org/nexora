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
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

import nx_lib.views.api_external as ax
import nx_lib.views.dashboard as dv
from nx_lib.clients import CLIENTS as CLIENTS_REGISTRY
from nx_lib.db import engine_nexora_db
from nx_lib.mapping_config import ProcessSource

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
    return ProcessSource(
        client=client_code,
        process=name,
        table=table,
        alias=None,
        join_condition=None,
        time_filter=None,
        suggestion_time_filter=None,
        export_column=exp,
        import_column=imp,
        workitem_column=None,
        extra_condition=None,
        id_column_type=None,
    )


def _stub_sources(monkeypatch, configs):
    """Replace mapping_config.registry()/sources_for() on the dashboard view
    module so _statconfig_sources returns `configs` -- the direct successor
    to monkeypatching dv.engine_nexora_db with a fake cursor around the
    legacy Statconfig SELECT (#98)."""
    monkeypatch.setattr(dv.mapping_config, "registry", lambda: object())
    monkeypatch.setattr(
        dv.mapping_config, "sources_for", lambda client, processes=None: list(configs)
    )


def _stub_sources_dead(monkeypatch, msg="NexoraDB down"):
    def _boom():
        raise RuntimeError(msg)

    monkeypatch.setattr(dv.mapping_config, "registry", _boom)


def test_statistics_db_outage_returns_500_not_zeros(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    cfg = _cfg_row("default", "sydoc.TestProc", "dbo.tblTest", "ExportDate", "ImportDate")
    _stub_sources(monkeypatch, [cfg])
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
    _stub_sources(monkeypatch, [cfg])
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["imported_today"] == 0
        assert body["exported_today"] == 0
    finally:
        _delete_key(key_hash)


# ------------------- resolve_import_datetimes (real legs) ------------------ #


def _import_cfg_row(client_code, name, table, wid_col, imp_col):
    return ProcessSource(
        client=client_code,
        process=name,
        table=table,
        alias=None,
        join_condition=None,
        time_filter=None,
        suggestion_time_filter=None,
        export_column=None,
        import_column=imp_col,
        workitem_column=wid_col,
        extra_condition=None,
        id_column_type=None,
    )


def test_resolve_import_datetimes_maps_ids_and_skips_unmapped(monkeypatch, auth_app_ctx):
    cfgs = [
        _import_cfg_row("default", "sydoc.TestProc", "dbo.tblTest", "WorkitemID", "ImportDate"),
        # No WorkitemColumn -> this process can't answer and must be skipped.
        _import_cfg_row("default", "sydoc.Other", "dbo.tblOther", None, "ImportDate"),
        # MS02 rows never feed the default-leg UNION.
        _import_cfg_row("ms02", "sydoc.MsProc", 'public."DossierStatistik"', "wid", "imp"),
    ]
    _stub_sources(monkeypatch, cfgs)
    monkeypatch.setattr(
        dv, "engine_statistics_db", _engine_returning([("1216", datetime(2026, 8, 1, 8, 0, 0))])
    )
    result = dv.resolve_import_datetimes([1216, 999], ["sydoc.TestProc", "sydoc.Other"])
    assert result == {"1216": datetime(2026, 8, 1, 8, 0, 0)}


def test_resolve_import_datetimes_empty_inputs_short_circuit(monkeypatch, auth_app_ctx):
    _stub_sources_dead(monkeypatch, "must not be reached")
    assert dv.resolve_import_datetimes([], ["sydoc.TestProc"]) == {}
    assert dv.resolve_import_datetimes([1], []) == {}


def test_resolve_import_datetimes_chunks_under_param_limit(monkeypatch, auth_app_ctx):
    # 3 legs x 1000 ids naively = 3000 params > SQL Server's 2100 cap; the
    # helper must partition ids so len(legs) * chunk <= 2000 per statement.
    cfgs = [
        _import_cfg_row("default", f"sydoc.P{i}", f"dbo.tbl{i}", "WorkitemID", "ImportDate")
        for i in range(3)
    ]
    _stub_sources(monkeypatch, cfgs)
    calls = []

    def _fake_rows(sql, params=None, *, strict=False):
        calls.append(len(params))
        return [(params[0], datetime(2026, 8, 1, 8, 0, 0))]

    monkeypatch.setattr(dv, "_default_stat_rows", _fake_rows)
    result = dv.resolve_import_datetimes(list(range(1000)), ["sydoc.P0"])
    assert len(calls) >= 2
    assert all(n <= 2000 for n in calls)
    assert result["0"] == datetime(2026, 8, 1, 8, 0, 0)


def test_resolve_import_datetimes_strict_raises_on_outage(monkeypatch, auth_app_ctx):
    cfg = _import_cfg_row("default", "sydoc.TestProc", "dbo.tblTest", "WorkitemID", "ImportDate")
    _stub_sources(monkeypatch, [cfg])
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine("Statistics DB down"))
    with pytest.raises(RuntimeError):
        dv.resolve_import_datetimes([1216], ["sydoc.TestProc"], strict=True)
    # non-strict degrades to "no data" like the KPI legs
    assert dv.resolve_import_datetimes([1216], ["sydoc.TestProc"]) == {}


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


#  ------------------------- /api/v1/avg_processing_time ------------- #

AVG_URL = "/api/v1/avg_processing_time"


def test_avg_no_auth_header_returns_401_json(client):
    resp = client.get(AVG_URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_avg_good_key_returns_scoped_avg_and_stamps_last_used(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_avg(target_processes, *, strict=False):
        seen["processes"] = target_processes
        seen["strict"] = strict
        return 252.0  # 4.2 minutes

    monkeypatch.setattr(ax, "compute_avg_processing_time", _fake_avg)
    try:
        resp = client.get(AVG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {
            "avg_minutes": 4.2,
            "avg_display": "4min",
        }
        assert seen["processes"] == ["sydoc.TestProc", "sydoc.Other"]
        # Same strict contract as stats/today -- an outage must raise, not
        # silently report "no data today".
        assert seen["strict"] is True
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_avg_no_matching_rows_returns_null(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")

    monkeypatch.setattr(ax, "compute_avg_processing_time", lambda procs, *, strict=False: None)
    try:
        resp = client.get(AVG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {
            "avg_minutes": None,
            "avg_display": "—",
        }
    finally:
        _delete_key(key_hash)


def test_avg_empty_process_scope_returns_null_without_compute(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(target_processes, *, strict=False):
        raise AssertionError("compute_avg_processing_time must not run for an empty scope")

    monkeypatch.setattr(ax, "compute_avg_processing_time", _must_not_be_called)
    try:
        resp = client.get(AVG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["avg_minutes"] is None
        assert body["avg_display"] == "—"
        assert "processes" not in body
    finally:
        _delete_key(key_hash)


def test_avg_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _boom(target_processes, *, strict=False):
        raise RuntimeError("StatisticsDB exploded")

    monkeypatch.setattr(ax, "compute_avg_processing_time", _boom)
    try:
        resp = client.get(AVG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Stats backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_avg_post_method_not_allowed(client):
    resp = client.post(AVG_URL)
    assert resp.status_code == 405


# ---------------------------- /api/v1/workitems ---------------------------- #

WORKITEMS_URL = "/api/v1/workitems"
WORKITEM_DETAIL_URL = "/api/v1/workitems/1216"


def _patch_field_whitelist(monkeypatch, columns=("invoicenr",), sensitive=(), scoped=None):
    """Doc-field whitelist without a NexoraDB round-trip. scoped defaults to
    columns (every valid column mapped for the key's scope); pass a subset to
    exercise the mapped-for-no-target-process 400."""
    monkeypatch.setattr(ax, "get_valid_search_columns", lambda: list(columns))
    monkeypatch.setattr(ax, "get_sensitive_field_keys", lambda: set(sensitive))
    scoped_set = set(columns if scoped is None else scoped)
    monkeypatch.setattr(ax, "get_search_columns_for_processes", lambda processes: scoped_set)


def test_workitems_no_auth_header_returns_401_json(client):
    resp = client.get(WORKITEMS_URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_workitems_bad_params_return_400_without_backend(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("_get_workitems_data must not run for an invalid request")

    monkeypatch.setattr(ax, "_get_workitems_data", _must_not_be_called)
    _patch_field_whitelist(monkeypatch)
    bad = [
        {"status": "Nope"},
        {"stage": "Nope"},
        {"start_date": "not-a-date"},
        {"end_date": "31.12.2026"},
        {"process": "other.NotGranted"},
        {"field": "invoicenr"},  # field without value
        {"field": "", "value": "x"},  # empty field key (no value-first search)
        {"field": "invoicenr", "value": "x", "op": "regex"},
        {"field": "invoicenr", "value": "x", "comb": "xor"},
        {"page": "0"},
        {"page": "abc"},
        {"per_page": "41"},
    ]
    try:
        for qs in bad:
            resp = client.get(
                WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"}, query_string=qs
            )
            assert resp.status_code == 400, qs
            assert "error" in resp.get_json(), qs
    finally:
        _delete_key(key_hash)


def test_workitems_unknown_and_sensitive_field_answer_identically(client, monkeypatch):
    # A sensitive field key must 400 exactly like an unknown one -- no
    # sensitivity-existence oracle on the external surface.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    _patch_field_whitelist(monkeypatch, columns=("invoicenr", "pid"), sensitive=("pid",))
    try:
        for field in ("nosuchfield", "pid"):
            resp = client.get(
                WORKITEMS_URL,
                headers={"Authorization": f"Bearer {raw}"},
                query_string={"field": field, "value": "x"},
            )
            assert resp.status_code == 400
            assert resp.get_json() == {"error": f"Unknown field '{field}'"}
    finally:
        _delete_key(key_hash)


def test_workitems_empty_process_scope_returns_empty_page(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(*a, **kw):
        raise AssertionError("_get_workitems_data must not run for an empty scope")

    monkeypatch.setattr(ax, "_get_workitems_data", _must_not_be_called)
    # TEST has no Search_Field_Labels table; the sensitive lookup would fail
    # closed (500) before the empty-scope short-circuit -- not this test's
    # subject, so give it a resolvable (empty) sensitive set.
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {
            "count": 0,
            "page": 1,
            "per_page": 40,
            "total_pages": 0,
            "workitems": [],
        }
    finally:
        _delete_key(key_hash)


def test_workitems_good_key_scopes_remaps_and_serializes(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_data(args, export_all=False, scope=None):
        seen["args"] = args
        seen["scope"] = scope
        return {
            "workitems": [
                {
                    "modifiedat": datetime(2026, 8, 9, 14, 30, 0),
                    "workitemid": 1216,
                    "status": "Done",
                    "current_stage": "Delivery",
                    "client": "default",
                },
                {
                    # Colliding id from the OTHER client: must NOT get the
                    # default row's import_datetime stamped onto it.
                    "modifiedat": datetime(2026, 8, 9, 15, 0, 0),
                    "workitemid": 1216,
                    "status": "Ready",
                    "current_stage": "Import",
                    "client": "ms02",
                },
            ],
            "pagination": {"currentPage": 1, "totalPages": 1, "totalItems": 2, "perPage": 40},
            "degradedSources": [],
        }

    def _fake_import_map(ids, processes, *, strict=False):
        seen["import_ids"] = ids
        seen["import_processes"] = processes
        seen["import_strict"] = strict
        return {"1216": datetime(2026, 8, 1, 8, 0, 0)}

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    monkeypatch.setattr(ax, "resolve_import_datetimes", _fake_import_map)
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string=[
                ("status", "Done"),
                ("stage", "Delivery"),
                ("start_date", "2026-08-01"),
                ("end_date", "2026-08-10"),
                ("process", "sydoc.TestProc"),
                ("field", "invoicenr"),
                ("value", "INV-2026-1"),
                ("op", "eq"),
            ],
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 2
        assert body["page"] == 1
        assert body["per_page"] == 40
        assert body["total_pages"] == 1
        # No client/source code in the response rows (owner decision
        # 2026-08-17) -- the internal row's client only steers the
        # import_datetime stamping.
        assert body["workitems"] == [
            {
                "id": 1216,
                "status": "Done",
                "stage": "Delivery",
                "modified_at": "2026-08-09 14:30:00",
                "import_datetime": "2026-08-01 08:00:00",
            },
            {
                "id": 1216,
                "status": "Ready",
                "stage": "Import",
                "modified_at": "2026-08-09 15:00:00",
                "import_datetime": None,
            },
        ]
        # External -> internal arg remap
        args = seen["args"]
        assert args.get("status") == "Done"
        assert args.get("stage") == "Delivery"
        assert args.get("startDate") == "2026-08-01"
        assert args.get("endDate") == "2026-08-10"
        assert args.get("prcfW") == "sydoc.TestProc"
        assert args.getlist("docfield") == ["invoicenr"]
        assert args.getlist("docvalue") == ["INV-2026-1"]
        assert args.getlist("docop") == ["eq"]
        assert args.getlist("doccomb") == ["and"]
        # Session-less scope from the key's ProcessList
        scope = seen["scope"]
        assert scope["allowed"] == {"sydoc.TestProc", "sydoc.Other"}
        assert scope["can_docfields"] is True
        assert scope["can_deleted"] is False
        assert scope["persist_selection"] is False
        assert scope["stamp_register"] is False
        # Import-datetime enrichment: default-client ids only, strict
        assert seen["import_ids"] == [1216]
        assert seen["import_strict"] is True
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_workitems_degraded_source_returns_500(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _fake_data(args, export_all=False, scope=None):
        return {
            "workitems": [],
            "pagination": {"currentPage": 1, "totalPages": 0, "totalItems": 0, "perPage": 40},
            "degradedSources": ["ms02"],
        }

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_workitems_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _boom(args, export_all=False, scope=None):
        raise RuntimeError("sources exploded")

    monkeypatch.setattr(ax, "_get_workitems_data", _boom)
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_workitems_post_method_not_allowed(client):
    resp = client.post(WORKITEMS_URL)
    assert resp.status_code == 405


def test_workitems_sensitive_lookup_failure_fails_closed_500(client, monkeypatch):
    # SECURITY PIN: the sensitive-field list is the ONLY gate on this surface
    # (no per-key sensitive grant) -- an unresolved list must 500, never mean
    # "nothing is sensitive" (the in-app fail-open does not apply here).
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    monkeypatch.setattr(ax, "get_sensitive_field_keys", lambda: None)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("_get_workitems_data must not run when sensitive lookup failed")

    monkeypatch.setattr(ax, "_get_workitems_data", _must_not_be_called)
    try:
        resp = client.get(WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_workitems_docfield_pair_cap_returns_400(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    _patch_field_whitelist(monkeypatch)
    qs = []
    for i in range(11):
        qs.append(("field", "invoicenr"))
        qs.append(("value", f"x{i}"))
    try:
        resp = client.get(
            WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"}, query_string=qs
        )
        assert resp.status_code == 400
        assert "at most 10 field/value pairs" in resp.get_json()["error"]
    finally:
        _delete_key(key_hash)


def test_workitems_real_data_path_and_docfield_fail_closed(client, monkeypatch):
    # Drives the REAL _get_workitems_data (no seam monkeypatch) with the
    # scope built from the key -- pins the stringly-typed scope-dict seam --
    # and pins the documented fail-closed contract: an active doc-field pair
    # that cannot be resolved (no mapping_config mapping here, #98 phase 3)
    # must force an EMPTY allow-set, never an unconstrained query.
    import nx_lib.mapping_config as mc
    import nx_lib.views.workitems as wi

    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    seen = {}

    def _fake_fetch(filt, offset, limit):
        seen["filt"] = filt
        return [], 0, []

    monkeypatch.setattr(wi, "fetch_merged_page", _fake_fetch)
    monkeypatch.setattr(wi, "get_activity_instances_to_ignore", lambda: "")
    monkeypatch.setattr(wi, "get_valid_search_columns", lambda: ["invoicenr"])
    # No mapping_config rows for the field -> the resolution blocks' upfront
    # mappings_for/sources_for reads (#98 phase 3) come back empty, same as
    # the old "no SearchConfig rows" simulation.
    monkeypatch.setattr(mc, "mappings_for", lambda client, processes, field_keys=None: [])
    monkeypatch.setattr(mc, "sources_for", lambda client, processes=None: [])
    _patch_field_whitelist(monkeypatch)  # view-level whitelist (ax namespace)
    monkeypatch.setattr(ax, "resolve_import_datetimes", lambda ids, procs, *, strict=False: {})
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"status": "Done", "field": "invoicenr", "value": "INV-1", "op": "eq"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 0
        filt = seen["filt"]
        assert filt.client_process_pairs == [("sydoc", "TestProc")]
        assert filt.status_code == 5  # Done, via scope can_status
        assert filt.docfield_ids == set()  # fail-closed, NOT None/unconstrained
    finally:
        _delete_key(key_hash)


def test_api_scope_covers_every_session_scope_key(auth_app_ctx):
    # The scope contract is a stringly-typed dict -- if _session_scope grows a
    # key the API twin doesn't set, _get_workitems_data KeyErrors only on the
    # API path (a CI-invisible 500). Pin the key sets to each other.
    import nx_lib.views.workitems as wi

    with auth_app_ctx.test_request_context("/"):
        from flask import session

        session["permissions"] = []
        session_keys = set(wi._session_scope())
    api_keys = set(ax._api_workitems_scope(["sydoc.TestProc"], set()))
    assert api_keys == session_keys


# ------------------------- /api/v1/workitems/<id> -------------------------- #


def test_workitem_detail_no_auth_header_returns_401_json(client):
    # The auth sweep skips parameterized rules ('<' in rule) -- this pins the
    # detail route's @require_api_key explicitly.
    resp = client.get(WORKITEM_DETAIL_URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_workitem_detail_client_param_is_ignored(client, monkeypatch):
    # ?client= no longer exists on this surface (owner decision 2026-08-17):
    # any value is ignored like other unknown params, never a 400.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    monkeypatch.setattr(ax, "process_pair_for_workitem", lambda wid, client_hint=None: None)
    try:
        resp = client.get(
            WORKITEM_DETAIL_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"client": "nope"},
        )
        assert resp.status_code == 404
        assert resp.get_json() == {"workitem_id": 1216, "detail": None}
    finally:
        _delete_key(key_hash)


def test_workitem_detail_empty_scope_returns_404_null(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(*a, **kw):
        raise AssertionError("source resolution must not run for an empty scope")

    monkeypatch.setattr(ax, "process_pair_for_workitem", _must_not_be_called)
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 404
        assert resp.get_json() == {"workitem_id": 1216, "detail": None}
    finally:
        _delete_key(key_hash)


def test_workitem_detail_unresolvable_and_out_of_scope_answer_identically(client, monkeypatch):
    # Unknown id and not-entitled id must be indistinguishable (uniform 404,
    # no existence oracle) -- deliberate deviation from the UI's 403.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    try:
        for pair in (None, ("sydoc", "NotGranted")):
            monkeypatch.setattr(
                ax, "process_pair_for_workitem", lambda wid, client_hint=None, _p=pair: _p
            )
            resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
            assert resp.status_code == 404
            assert resp.get_json() == {"workitem_id": 1216, "detail": None}
    finally:
        _delete_key(key_hash)


def test_workitem_detail_good_key_returns_stripped_fields_and_tables(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    seen = {}
    payload = {
        "workitem_id": 1216,
        "media_count": 3,
        "fields": {"InvoiceNumber": "INV-2026-1", "Person ID": "756.1234"},
        "field_sources": [
            {"key": "InvoiceNumber", "label": "Invoice Number", "value": "INV-2026-1"},
            {"key": "Person ID", "label": "Person ID", "value": "756.1234"},
        ],
        "table_sources": [
            {
                "title": "LineItems",
                "columns": ["Amount", "PID"],
                "rows": [
                    [
                        {"col": "Amount", "value": "10.00", "confidence": 0.93, "locations": []},
                        {"col": "PID", "value": "756.1234"},
                    ]
                ],
            }
        ],
    }

    def _fake_pair(wid, client_hint=None):
        seen["hint"] = client_hint
        return ("Sydoc", "testproc")

    monkeypatch.setattr(ax, "process_pair_for_workitem", _fake_pair)
    monkeypatch.setattr(ax, "get_domain_for_workitem", lambda wid, client_hint=None: "octo.test")
    monkeypatch.setattr(ax, "_load_media_info", lambda wid, domain: payload)
    monkeypatch.setattr(ax, "get_sensitive_field_tokens", lambda: {"personid", "pid"})
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        # Entitlement compares case-insensitively; the source is resolved
        # from the key's scope (registered sources tried in order), never
        # from a caller-supplied param, and never echoed back.
        assert seen["hint"] in CLIENTS_REGISTRY
        assert resp.get_json() == {
            "workitem_id": 1216,
            "detail": {
                "fields": {"InvoiceNumber": "INV-2026-1"},
                "tables": [
                    {
                        "title": "LineItems",
                        "columns": ["Amount"],
                        "rows": [[{"column": "Amount", "value": "10.00"}]],
                    }
                ],
            },
        }
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_workitem_detail_unloadable_document_returns_404_null(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    monkeypatch.setattr(
        ax, "process_pair_for_workitem", lambda wid, client_hint=None: ("sydoc", "TestProc")
    )
    monkeypatch.setattr(ax, "get_domain_for_workitem", lambda wid, client_hint=None: "octo.test")
    monkeypatch.setattr(ax, "_load_media_info", lambda wid, domain: None)
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 404
        assert resp.get_json() == {"workitem_id": 1216, "detail": None}
    finally:
        _delete_key(key_hash)


def test_workitem_detail_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")

    def _boom(wid, client_hint=None):
        raise RuntimeError("NexoraDB exploded")

    monkeypatch.setattr(ax, "process_pair_for_workitem", _boom)
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_workitem_detail_post_method_not_allowed(client):
    resp = client.post(WORKITEM_DETAIL_URL)
    assert resp.status_code == 405


def test_workitem_detail_sensitive_lookup_failure_fails_closed_500(client, monkeypatch):
    # SECURITY PIN (mirror of the query endpoint's): a failed sensitive-token
    # lookup must never serve unstripped fields/tables.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    monkeypatch.setattr(
        ax, "process_pair_for_workitem", lambda wid, client_hint=None: ("sydoc", "TestProc")
    )
    monkeypatch.setattr(ax, "get_domain_for_workitem", lambda wid, client_hint=None: "octo.test")
    monkeypatch.setattr(
        ax,
        "_load_media_info",
        lambda wid, domain: {
            "workitem_id": wid,
            "media_count": 0,
            "fields": {"Secret": "x"},
            "field_sources": [],
            "table_sources": [],
        },
    )
    monkeypatch.setattr(ax, "get_sensitive_field_tokens", lambda: None)
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


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
TEST_AVG_URL = "/api/test/v1/avg_processing_time"


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


def test_test_avg_no_auth_header_returns_401_json(client):
    resp = client.get(TEST_AVG_URL)
    assert resp.status_code == 401
    assert resp.is_json


def test_test_avg_good_key_returns_random_data_in_real_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    try:
        resp = client.get(TEST_AVG_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert isinstance(body["avg_minutes"], float)
        assert isinstance(body["avg_display"], str)
        assert "processes" not in body
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


TEST_WORKITEMS_URL = "/api/test/v1/workitems"
TEST_WORKITEM_DETAIL_URL = "/api/test/v1/workitems/1216"


def test_test_workitems_no_auth_header_returns_401_json(client):
    resp = client.get(TEST_WORKITEMS_URL)
    assert resp.status_code == 401
    assert resp.is_json


def test_test_workitems_validates_params_like_the_real_endpoint(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        resp = client.get(
            TEST_WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"status": "Nope"},
        )
        assert resp.status_code == 400
        # ...but accepts ANY field name: the sandbox skips the DB-backed
        # doc-field whitelist to stay zero-backend-query.
        resp = client.get(
            TEST_WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"field": "anything", "value": "x"},
        )
        assert resp.status_code == 200
    finally:
        _delete_key(key_hash)


def test_test_workitems_good_key_returns_random_data_in_real_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        resp = client.get(
            TEST_WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"per_page": "100", "page": "2"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert set(body) == {"count", "page", "per_page", "total_pages", "workitems"}
        assert body["page"] == 2
        assert body["per_page"] == 100
        assert body["count"] == len(body["workitems"])
        for row in body["workitems"]:
            assert set(row) == {
                "id",
                "status",
                "stage",
                "modified_at",
                "import_datetime",
            }
            datetime.strptime(row["modified_at"], "%Y-%m-%d %H:%M:%S")
            datetime.strptime(row["import_datetime"], "%Y-%m-%d %H:%M:%S")
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_test_workitem_detail_no_auth_header_returns_401_json(client):
    resp = client.get(TEST_WORKITEM_DETAIL_URL)
    assert resp.status_code == 401
    assert resp.is_json


def test_test_workitem_detail_good_key_returns_fake_document_in_real_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        resp = client.get(TEST_WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert set(body) == {"workitem_id", "detail"}
        assert body["workitem_id"] == 1216
        assert body["detail"]["fields"]
        table = body["detail"]["tables"][0]
        assert set(table) == {"title", "columns", "rows"}
        for row in table["rows"]:
            for cell in row:
                assert set(cell) == {"column", "value"}
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_unknown_api_test_v1_path_returns_json_404(client):
    resp = client.get("/api/test/v1/definitely/not/a/route")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json() == {"error": "Not found"}


# --------------------- /api/v1/undelivered (issue #196) --------------------- #
# Auth-required coverage comes for free from test_every_api_v1_route_requires_auth.

UNDELIVERED_URL = "/api/v1/undelivered"
TEST_UNDELIVERED_URL = "/api/test/v1/undelivered"


def test_undelivered_good_key_returns_scoped_count(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_compute(target_processes, days, *, strict=False):
        seen["processes"] = target_processes
        seen["days"] = days
        seen["strict"] = strict
        return 42

    monkeypatch.setattr(ax, "compute_undelivered_count", _fake_compute)
    try:
        resp = client.get(f"{UNDELIVERED_URL}?days=7", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        # Like /backlog, the response deliberately omits the process list --
        # scoping happens at key issuance, not in the payload.
        assert resp.get_json() == {
            "date": date.today().isoformat(),
            "days": 7,
            "undelivered": 42,
        }
        assert seen["processes"] == ["sydoc.TestProc", "sydoc.Other"]
        assert seen["days"] == 7
        assert seen["strict"] is True
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_undelivered_days_10_is_accepted(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    monkeypatch.setattr(ax, "compute_undelivered_count", lambda p, d, *, strict=False: 3)
    try:
        resp = client.get(f"{UNDELIVERED_URL}?days=10", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json()["days"] == 10
    finally:
        _delete_key(key_hash)


def test_undelivered_missing_or_invalid_days_returns_400(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("compute_undelivered_count must not run for invalid days")

    monkeypatch.setattr(ax, "compute_undelivered_count", _must_not_be_called)
    try:
        # Only the literal strings "7" and "10" pass -- no int coercion.
        for qs in ("", "?days=9", "?days=07", "?days=7.0", "?days=abc"):
            resp = client.get(UNDELIVERED_URL + qs, headers={"Authorization": f"Bearer {raw}"})
            assert resp.status_code == 400, f"days qs {qs!r} was not rejected"
            assert resp.get_json() == {"error": "days must be 7 or 10"}
    finally:
        _delete_key(key_hash)


def test_undelivered_empty_process_scope_returns_zero_without_compute(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(*a, **kw):
        raise AssertionError("compute_undelivered_count must not run for an empty scope")

    monkeypatch.setattr(ax, "compute_undelivered_count", _must_not_be_called)
    try:
        resp = client.get(f"{UNDELIVERED_URL}?days=7", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["undelivered"] == 0
        assert "processes" not in body
    finally:
        _delete_key(key_hash)


def test_undelivered_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _boom(target_processes, days, *, strict=False):
        raise RuntimeError("StatisticsDB exploded")

    monkeypatch.setattr(ax, "compute_undelivered_count", _boom)
    try:
        resp = client.get(f"{UNDELIVERED_URL}?days=7", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Stats backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_test_undelivered_good_key_returns_random_data_in_real_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    try:
        resp = client.get(
            f"{TEST_UNDELIVERED_URL}?days=10", headers={"Authorization": f"Bearer {raw}"}
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["date"] == date.today().isoformat()
        assert body["days"] == 10
        assert isinstance(body["undelivered"], int)
        assert "processes" not in body
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_undelivered_compute_runs_real_sql_leg(client, monkeypatch):
    # Exercise compute_undelivered_count FOR REAL (only engines faked): the
    # T-SQL leg must window on the import column, require a NULL export
    # column, and skip ProcessSources rows without an import_column.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    cfg_ok = _cfg_row("default", "sydoc.TestProc", "dbo.tblTest", "ExportDate", "ImportDate")
    cfg_no_import = _cfg_row("default", "sydoc.TestProc", "dbo.tblOther", "ExportDate", None)
    stats_engine = _engine_returning([(5,)])
    _stub_sources(monkeypatch, [cfg_ok, cfg_no_import])
    monkeypatch.setattr(dv, "engine_statistics_db", stats_engine)
    try:
        resp = client.get(f"{UNDELIVERED_URL}?days=7", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json()["undelivered"] == 5
        sql = stats_engine.raw_connection().cursor().execute.call_args[0][0]
        assert "DATEADD(day, -7, GETDATE())" in sql
        assert "ExportDate IS NULL" in sql
        assert "tblOther" not in sql  # no ImportColumn -> skipped
    finally:
        _delete_key(key_hash)


def test_test_undelivered_validates_days_like_the_real_endpoint(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        resp = client.get(TEST_UNDELIVERED_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "days must be 7 or 10"}
    finally:
        _delete_key(key_hash)


# ------------------------ /api/v1/workitems/fields ------------------------- #

FIELDS_URL = "/api/v1/workitems/fields"
TEST_FIELDS_URL = "/api/test/v1/workitems/fields"


def test_workitems_fields_lists_keys_minus_sensitive(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    _patch_field_whitelist(monkeypatch, columns=("invoicenr", "pid", "doctype"), sensitive=("pid",))
    try:
        resp = client.get(FIELDS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {"fields": ["doctype", "invoicenr"]}
    finally:
        _delete_key(key_hash)


def test_workitems_fields_fails_closed_on_lookup_errors(client, monkeypatch):
    # BOTH lookup failures answer 500: sensitive-list None AND the None error
    # fallback of get_search_columns_for_processes -- never a partial list.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        _patch_field_whitelist(monkeypatch, columns=("invoicenr",))
        monkeypatch.setattr(ax, "get_sensitive_field_keys", lambda: None)
        resp = client.get(FIELDS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
        _patch_field_whitelist(monkeypatch, columns=("invoicenr",))
        monkeypatch.setattr(ax, "get_search_columns_for_processes", lambda processes: None)
        resp = client.get(FIELDS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_workitems_fields_empty_scope_mapping_returns_empty_list(client, monkeypatch):
    # No SearchConfig mapping for any of the key's processes is a truthful
    # empty list (200), NOT an error -- distinct from the None failure above.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    _patch_field_whitelist(monkeypatch, scoped=())
    try:
        resp = client.get(FIELDS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {"fields": []}
    finally:
        _delete_key(key_hash)


def test_workitems_field_unmapped_for_scope_returns_400(client, monkeypatch):
    # A globally valid column that is mapped for NONE of the key's processes
    # must 400 (it would otherwise silently resolve to count=0), with a
    # message distinct from the unknown/sensitive "Unknown field".
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    _patch_field_whitelist(monkeypatch, columns=("invoicenr", "doctype"), scoped=("invoicenr",))

    def _must_not_be_called(*a, **kw):
        raise AssertionError("_get_workitems_data must not run for an unmapped field")

    monkeypatch.setattr(ax, "_get_workitems_data", _must_not_be_called)
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"field": "doctype", "value": "Invoice"},
        )
        assert resp.status_code == 400
        assert resp.get_json() == {
            "error": "Field 'doctype' is not available for your process scope"
        }
        # the mapped field on the same key still parses fine (hits the seam
        # mock's 500 only if it got past validation -- so patch a benign body)
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"field": "invoicenr", "value": "x", "op": "eq"},
        )
        assert resp.status_code == 500  # _must_not_be_called raised -> 500 path
    finally:
        _delete_key(key_hash)


def test_get_search_columns_for_processes_maps_and_fails_closed(monkeypatch, auth_app_ctx):
    # Delegates to mapping_config.field_keys_for_processes (#98): keys come
    # back bare lowercase (the col_ prefix was retired in task 6); empty
    # scope short-circuits without a registry lookup; a registry load
    # failure (None) propagates so the external API keeps failing closed.
    import nx_lib.mapping_config as mc
    import nx_lib.views.workitems as wi

    monkeypatch.setattr(mc, "field_keys_for_processes", lambda processes: {"invoicenr", "doctype"})
    assert wi.get_search_columns_for_processes(["p.a", "p.b"]) == {
        "invoicenr",
        "doctype",
    }
    assert wi.get_search_columns_for_processes([]) == set()
    monkeypatch.setattr(mc, "field_keys_for_processes", lambda processes: None)
    assert wi.get_search_columns_for_processes(["p.a"]) is None


def test_test_workitems_fields_static_shape_no_backend(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("sandbox must not query SearchConfig")

    monkeypatch.setattr(ax, "get_valid_search_columns", _must_not_be_called)
    monkeypatch.setattr(ax, "get_sensitive_field_keys", _must_not_be_called)
    try:
        resp = client.get(TEST_FIELDS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["fields"] and all(f == f.lower() for f in body["fields"])
    finally:
        _delete_key(key_hash)


# ----------------------- hardening pass (2026-08-17) ----------------------- #
# The endpoints are client-facing contract surface; these pin the corners the
# feature tests above don't: the detail endpoint's multi-source resolution
# loop, validation boundaries, parameter defaults, and response-shape locks.


def _fake_page(rows=None):
    return {
        "workitems": rows or [],
        "pagination": {"currentPage": 1, "totalPages": 0, "totalItems": 0, "perPage": 40},
        "degradedSources": [],
    }


def test_workitem_detail_resolves_via_second_source_when_first_out_of_scope(client, monkeypatch):
    # The scope-resolution loop must not stop at the first source that KNOWS
    # the id -- only at the first whose (client, process) pair the key covers.
    # Pins the colliding-id case: default owns the id under an ungranted
    # process, ms02 owns it under the granted one.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="pdbs.MS02Proc")
    seen = {"pair_hints": [], "domain_hint": None}
    pairs_by_hint = {"default": ("sydoc", "NotGranted"), "ms02": ("pdbs", "MS02Proc")}

    def _fake_pair(wid, client_hint=None):
        seen["pair_hints"].append(client_hint)
        return pairs_by_hint.get(client_hint)

    def _fake_domain(wid, client_hint=None):
        seen["domain_hint"] = client_hint
        return "octo.ms02"

    monkeypatch.setattr(ax, "CLIENTS", {"default": object(), "ms02": object()})
    monkeypatch.setattr(ax, "process_pair_for_workitem", _fake_pair)
    monkeypatch.setattr(ax, "get_domain_for_workitem", _fake_domain)
    monkeypatch.setattr(
        ax,
        "_load_media_info",
        lambda wid, domain: {"fields": {"A": "1"}, "field_sources": [], "table_sources": []},
    )
    monkeypatch.setattr(ax, "get_sensitive_field_tokens", lambda: set())
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert seen["pair_hints"] == ["default", "ms02"]  # tried in registration order
        assert seen["domain_hint"] == "ms02"  # media loaded from the WINNING source
        assert resp.get_json() == {
            "workitem_id": 1216,
            "detail": {"fields": {"A": "1"}, "tables": []},
        }
    finally:
        _delete_key(key_hash)


def test_workitem_detail_prefers_default_source_on_full_collision(client, monkeypatch):
    # A key covering BOTH sources of a colliding id gets the default-source
    # document deterministically (registration order) -- documented edge.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, pdbs.MS02Proc")
    seen = {"domain_hint": None}
    pairs_by_hint = {"default": ("sydoc", "TestProc"), "ms02": ("pdbs", "MS02Proc")}

    def _fake_domain(wid, client_hint=None):
        seen["domain_hint"] = client_hint
        return "octo.default"

    monkeypatch.setattr(ax, "CLIENTS", {"default": object(), "ms02": object()})
    monkeypatch.setattr(
        ax, "process_pair_for_workitem", lambda wid, client_hint=None: pairs_by_hint[client_hint]
    )
    monkeypatch.setattr(ax, "get_domain_for_workitem", _fake_domain)
    monkeypatch.setattr(
        ax,
        "_load_media_info",
        lambda wid, domain: {"fields": {}, "field_sources": [], "table_sources": []},
    )
    monkeypatch.setattr(ax, "get_sensitive_field_tokens", lambda: set())
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert seen["domain_hint"] == "default"
    finally:
        _delete_key(key_hash)


def test_workitem_detail_dotless_process_scope_returns_404(client, monkeypatch):
    # A ProcessList entry without a '.' can never form a (client, process)
    # pair -- the key must resolve nothing rather than error.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="NoDotProcess")
    monkeypatch.setattr(
        ax, "process_pair_for_workitem", lambda wid, client_hint=None: ("sydoc", "TestProc")
    )
    try:
        resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 404
        assert resp.get_json() == {"workitem_id": 1216, "detail": None}
    finally:
        _delete_key(key_hash)


def test_workitem_detail_strips_all_sensitive_table_and_absent_tables(client, monkeypatch):
    # _api_tables corners: a payload without table_sources answers tables=[],
    # and a table whose every column is sensitive keeps its title but loses
    # all columns and cell values.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc")
    monkeypatch.setattr(
        ax, "process_pair_for_workitem", lambda wid, client_hint=None: ("sydoc", "TestProc")
    )
    monkeypatch.setattr(ax, "get_domain_for_workitem", lambda wid, client_hint=None: "octo.test")
    monkeypatch.setattr(ax, "get_sensitive_field_tokens", lambda: {"pid"})
    payloads = [
        {"fields": {"A": "1"}, "field_sources": []},  # no table_sources key at all
        {
            "fields": {"A": "1"},
            "field_sources": [],
            "table_sources": [
                {
                    "title": "Persons",
                    "columns": ["PID"],
                    "rows": [[{"col": "PID", "value": "756.1"}]],
                }
            ],
        },
    ]
    expected_tables = [[], [{"title": "Persons", "columns": [], "rows": [[]]}]]
    try:
        for payload, tables in zip(payloads, expected_tables, strict=True):
            monkeypatch.setattr(ax, "_load_media_info", lambda wid, domain, _p=payload: _p)
            resp = client.get(WORKITEM_DETAIL_URL, headers={"Authorization": f"Bearer {raw}"})
            assert resp.status_code == 200
            assert resp.get_json()["detail"]["tables"] == tables
    finally:
        _delete_key(key_hash)


def test_workitems_more_validation_corners_return_400(client, monkeypatch):
    # Additions to the bad-params matrix: value without field, surplus
    # op/comb entries, page/per_page corner values.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("_get_workitems_data must not run for an invalid request")

    monkeypatch.setattr(ax, "_get_workitems_data", _must_not_be_called)
    _patch_field_whitelist(monkeypatch)
    bad = [
        [("value", "x")],  # value without field
        [("field", "invoicenr"), ("value", "x"), ("op", "eq"), ("op", "eq")],  # surplus op
        [("field", "invoicenr"), ("value", "x"), ("comb", "and"), ("comb", "or")],  # surplus comb
        [("page", "-1")],
        [("page", "1.5")],
        [("per_page", "0")],
        [("per_page", "9999")],
        [("field", "invoicenr"), ("value", "   ")],  # whitespace-only value
    ]
    try:
        for qs in bad:
            resp = client.get(
                WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"}, query_string=qs
            )
            assert resp.status_code == 400, qs
            assert "error" in resp.get_json(), qs
    finally:
        _delete_key(key_hash)


def test_workitems_ten_pairs_is_accepted_and_eleven_is_not(client, monkeypatch):
    # Boundary lock on WORKITEM_API_MAX_DOCFIELD_PAIRS.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    monkeypatch.setattr(ax, "_get_workitems_data", lambda args, scope=None: _fake_page())
    monkeypatch.setattr(ax, "resolve_import_datetimes", lambda ids, procs, *, strict=False: {})
    _patch_field_whitelist(monkeypatch)
    try:
        for n, expected in ((10, 200), (11, 400)):
            qs = []
            for i in range(n):
                qs += [("field", "invoicenr"), ("value", f"v{i}")]
            resp = client.get(
                WORKITEMS_URL, headers={"Authorization": f"Bearer {raw}"}, query_string=qs
            )
            assert resp.status_code == expected, n
    finally:
        _delete_key(key_hash)


def test_workitems_field_key_case_insensitive_and_value_case_preserved(client, monkeypatch):
    # Field keys normalize to lowercase; the VALUE must pass through
    # untouched (lowercasing it would break exact-match searches).
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    seen = {}

    def _fake_data(args, scope=None):
        seen["args"] = args
        return _fake_page()

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    monkeypatch.setattr(ax, "resolve_import_datetimes", lambda ids, procs, *, strict=False: {})
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string=[("field", "INVOICENR"), ("value", "  Inv-2026-X  ")],
        )
        assert resp.status_code == 200
        assert seen["args"].getlist("docfield") == ["invoicenr"]
        assert seen["args"].getlist("docvalue") == ["Inv-2026-X"]  # trimmed, case kept
    finally:
        _delete_key(key_hash)


def test_workitems_omitted_op_and_comb_default_to_contains_and(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    seen = {}

    def _fake_data(args, scope=None):
        seen["args"] = args
        return _fake_page()

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    monkeypatch.setattr(ax, "resolve_import_datetimes", lambda ids, procs, *, strict=False: {})
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string=[
                ("field", "invoicenr"),
                ("value", "a"),
                ("field", "invoicenr"),
                ("value", "b"),
            ],
        )
        assert resp.status_code == 200
        assert seen["args"].getlist("docop") == ["contains", "contains"]
        assert seen["args"].getlist("doccomb") == ["and", "and"]
    finally:
        _delete_key(key_hash)


def test_workitems_workitem_id_maps_to_search_and_all_per_page_values_accepted(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    seen = {}

    def _fake_data(args, scope=None):
        seen["args"] = args
        return _fake_page()

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    monkeypatch.setattr(ax, "resolve_import_datetimes", lambda ids, procs, *, strict=False: {})
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"workitem_id": " 4711 "},
        )
        assert resp.status_code == 200
        assert seen["args"].get("search") == "4711"
        for pp in ax.WORKITEM_API_PER_PAGE:
            resp = client.get(
                WORKITEMS_URL,
                headers={"Authorization": f"Bearer {raw}"},
                query_string={"per_page": pp},
            )
            assert resp.status_code == 200, pp
    finally:
        _delete_key(key_hash)


def test_workitems_process_list_tolerates_whitespace(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_data(args, scope=None):
        seen["args"] = args
        return _fake_page()

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    monkeypatch.setattr(ax, "resolve_import_datetimes", lambda ids, procs, *, strict=False: {})
    _patch_field_whitelist(monkeypatch)
    try:
        resp = client.get(
            WORKITEMS_URL,
            headers={"Authorization": f"Bearer {raw}"},
            query_string={"process": " sydoc.TestProc , sydoc.Other "},
        )
        assert resp.status_code == 200
        assert seen["args"].get("prcfW") == "sydoc.TestProc,sydoc.Other"
    finally:
        _delete_key(key_hash)


def test_workitems_fields_sorted_and_stamps_last_used(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    _patch_field_whitelist(monkeypatch, columns=("zeta", "alpha", "mid"), sensitive=("mid",))
    try:
        resp = client.get(FIELDS_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {"fields": ["alpha", "zeta"]}  # sorted, sensitive dropped
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


# --------------------------- /api/v1/stages -------------------------------- #
# Auth-required coverage comes for free from test_every_api_v1_route_requires_auth.

STAGES_URL = "/api/v1/stages"
TEST_STAGES_URL = "/api/test/v1/stages"


def test_workitems_stages_counts_all_four_stages(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = []

    def _fake_data(args, export_all=False, scope=None):
        seen.append((args.get("stage"), scope))
        totals = {"Import": 3, "Extraction": 1, "Validation": 0, "Delivery": 7}
        return {
            "workitems": [],
            "pagination": {
                "currentPage": 1,
                "totalPages": 1,
                "totalItems": totals[args.get("stage")],
                "perPage": 40,
            },
            "degradedSources": [],
        }

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    try:
        resp = client.get(STAGES_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["stages"] == {"Import": 3, "Extraction": 1, "Validation": 0, "Delivery": 7}
        assert "datetime" in body
        # One stage-filtered query per stage, session-less scope from the key.
        assert [s for s, _ in seen] == list(ax.WORKITEM_STAGES)
        assert all(sc["allowed"] == {"sydoc.TestProc", "sydoc.Other"} for _, sc in seen)
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_workitems_stages_empty_scope_returns_zeros_without_backend(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(*a, **kw):
        raise AssertionError("_get_workitems_data must not run for an empty scope")

    monkeypatch.setattr(ax, "_get_workitems_data", _must_not_be_called)
    try:
        resp = client.get(STAGES_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json()["stages"] == {
            "Import": 0,
            "Extraction": 0,
            "Validation": 0,
            "Delivery": 0,
        }
    finally:
        _delete_key(key_hash)


def test_workitems_stages_degraded_source_returns_500(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _fake_data(args, export_all=False, scope=None):
        return {
            "workitems": [],
            "pagination": {"currentPage": 1, "totalPages": 0, "totalItems": 0, "perPage": 40},
            "degradedSources": ["ms02"],
        }

    monkeypatch.setattr(ax, "_get_workitems_data", _fake_data)
    try:
        resp = client.get(STAGES_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Workitems backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_test_workitems_stages_returns_random_counts_in_shape(client):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)
    try:
        resp = client.get(TEST_STAGES_URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert set(body["stages"]) == {"Import", "Extraction", "Validation", "Delivery"}
        assert all(isinstance(v, int) and v >= 0 for v in body["stages"].values())
        assert "datetime" in body
    finally:
        _delete_key(key_hash)
