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
