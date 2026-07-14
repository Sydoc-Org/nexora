"""Unit tests for nx_lib/api_auth.py -- Bearer API-key auth for /api/v1.

The engine is mocked on the module (precedent:
tests/unit/test_prepared_documents.py -- CI/TEST has no guaranteed rows);
the route-level tests hit the real NEXORA_TEST ApiKeys table instead, see
tests/integration/test_api_external_routes.py. The decorator is exercised
by calling a wrapped probe view inside test_request_context.
"""

import hashlib
import types
from unittest.mock import MagicMock

from flask import g, jsonify

import nx_lib.api_auth as aa
from nx_lib.api_auth import hash_api_key, require_api_key


@require_api_key
def _probe():
    return jsonify(
        {
            "client": g.api_client["client_code"],
            "processes": g.api_client["processes"],
            "key_id": g.api_client["key_id"],
        }
    )


def _key_row(raw="sesame", client="acme", processes="p.a,p.b", kid=7):
    # Shape of the SELECT in _match_key: ID, KeyHash, ClientCode, ProcessList.
    # No Enabled attribute -- disabled rows are filtered out in SQL.
    return types.SimpleNamespace(
        ID=kid,
        KeyHash=hash_api_key(raw),
        ClientCode=client,
        ProcessList=processes,
    )


def _engine_returning(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


def _dead_engine(msg="NexoraDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


# ------------------------------- helpers ------------------------------- #


def test_hash_api_key_is_sha256_hex():
    assert hash_api_key("abc") == hashlib.sha256(b"abc").hexdigest()
    assert len(hash_api_key("anything")) == 64


def test_parse_process_list_trims_and_drops_blanks():
    assert aa._parse_process_list(" a.b , ,c.d ,") == ["a.b", "c.d"]
    assert aa._parse_process_list("") == []
    assert aa._parse_process_list(None) == []


# ------------------------------ decorator ------------------------------ #


def test_missing_header_returns_401(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status, headers = _probe()
    assert status == 401
    assert headers["WWW-Authenticate"] == "Bearer"
    assert "Authorization" in body.get_json()["error"]


def test_non_bearer_scheme_returns_401(app):
    with app.test_request_context("/api/v1/stats/today", headers={"Authorization": "Basic Zm9v"}):
        body, status, headers = _probe()
    assert status == 401


def test_empty_bearer_token_returns_401(app):
    with app.test_request_context("/api/v1/stats/today", headers={"Authorization": "Bearer   "}):
        body, status, headers = _probe()
    assert status == 401


def test_unknown_key_returns_401(app, monkeypatch):
    monkeypatch.setattr(aa, "engine_nexora_db", _engine_returning([_key_row(raw="other")]))
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        body, status, headers = _probe()
    assert status == 401
    assert body.get_json() == {"error": "Invalid API key"}


def test_disabled_keys_are_filtered_in_sql_and_get_the_same_401(app, monkeypatch):
    # Uniform 401: the lookup scans WHERE Enabled = 1, so a disabled key is
    # simply absent from the candidate rows -- indistinguishable from a
    # never-issued key (no existence oracle for leaked/revoked keys).
    eng = _engine_returning([])
    monkeypatch.setattr(aa, "engine_nexora_db", eng)
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        body, status, headers = _probe()
    assert status == 401
    assert body.get_json() == {"error": "Invalid API key"}
    executed_sql = eng.raw_connection.return_value.cursor.return_value.execute.call_args[0][0]
    assert "Enabled = 1" in executed_sql


def test_db_error_fails_closed_with_503(app, monkeypatch):
    # Deliberate deviation from the dashboard helpers' fail-open pattern:
    # auth must fail CLOSED -- a NexoraDB blip yields 503, never a free pass
    # and never a misleading 401 ("key revoked").
    monkeypatch.setattr(aa, "engine_nexora_db", _dead_engine())
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        body, status = _probe()
    assert status == 503
    assert body.get_json() == {"error": "Auth backend unavailable"}


def test_good_key_sets_g_and_calls_view(app, monkeypatch):
    monkeypatch.setattr(aa, "engine_nexora_db", _engine_returning([_key_row()]))
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        resp = _probe()
    assert resp.status_code == 200
    assert resp.get_json() == {"client": "acme", "processes": ["p.a", "p.b"], "key_id": 7}


def test_key_matching_uses_constant_time_compare(app, monkeypatch):
    calls = []
    real = aa.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(aa.hmac, "compare_digest", spy)
    monkeypatch.setattr(aa, "engine_nexora_db", _engine_returning([_key_row()]))
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        _probe()
    assert calls, "hmac.compare_digest was not used for key matching"


def test_touch_last_used_swallows_db_errors(app, monkeypatch):
    # LastUsedAt is best-effort bookkeeping: a write failure must not fail an
    # otherwise-authenticated request.
    monkeypatch.setattr(aa, "engine_nexora_db", _dead_engine())
    with app.app_context():
        aa._touch_last_used(1)  # must not raise
