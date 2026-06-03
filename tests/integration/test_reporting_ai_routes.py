"""Integration tests for POST /api/reporting/ai/ask (perm gating + happy path)."""

from unittest.mock import patch

from nx_lib.reporting.ai import AiResult

# The @require_permission decorator calls has_permission from nx_lib.security;
# inline calls inside api_ai_ask use the imported name in nx_lib.views.reporting.
# Both must be patched together when we want to bypass the permission checks.
_PERM_PATCHES = (
    "nx_lib.security.has_permission",
    "nx_lib.views.reporting.has_permission",
)


def _result(sql="SELECT TOP (5) Id FROM dbo.Foo", valid=True):
    return AiResult(
        sql=sql,
        explanation="five ids",
        valid=valid,
        gate_verdict="valid" if valid else "invalid",
        model="m",
        provider="anthropic",
        tokens_in=10,
        tokens_out=5,
    )


def test_ai_ask_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_ask_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config", return_value={"provider": "none", "api_key": None}
        ),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_ask_happy_path_returns_sql_and_audits(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sql"].startswith("SELECT TOP (5)")
    assert data["valid"] is True
    assert "rows" not in data  # schema-only egress; never returns data
    ask.assert_called_once()
    audit.assert_called_once()


def test_ai_ask_rejects_empty_question(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "   "})
    assert resp.status_code == 400


def test_ai_ask_502_on_provider_error(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", side_effect=RuntimeError("boom")),
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 502
    audit.assert_called_once()
    # error path audits with status="error" (the second-to-last positional arg)
    assert "error" in audit.call_args.args
    assert audit.call_args.args[-2] == "error"


def test_ai_ask_429_when_daily_limit_reached(user_client):
    # When the per-user daily cap is hit, the route blocks BEFORE calling the
    # provider (no token cost), records the throttle, and never reaches ai_ask.
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting._ai_asks_today", return_value=5),
        patch("nx_lib.views.reporting.ai_ask") as ask,
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 429
    ask.assert_not_called()  # never calls the provider -> no token cost
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "blocked"  # status="blocked"


def test_ai_ask_allows_when_under_daily_limit(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting._ai_asks_today", return_value=4),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    ask.assert_called_once()


def test_ai_ask_unlimited_when_limit_zero(user_client):
    # limit 0 disables the cap: the usage count is never queried.
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_asks_today") as count,
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    ask.assert_called_once()
    count.assert_not_called()  # cap disabled -> no usage query
