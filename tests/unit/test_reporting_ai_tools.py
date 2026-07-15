"""Unit tests for the Reporting AI tool layer (Phase 3b).

Tools wrap existing rails (sandbox gate, Surface-A validator, stats engine, an
injected run_sql) and return JSON-serialisable envelopes. They must never raise
across the boundary — a failure becomes ``{"ok": False, "error": ...}`` so the
agentic loop can feed it back for self-repair.
"""

from nx_lib.reporting.ai_tools import TOOL_SPECS, ToolRegistry


def test_specs_are_provider_neutral():
    names = {t["name"] for t in TOOL_SPECS}
    assert {"validate_sql", "run_sql", "compute_stats", "build_definition"} <= names
    for t in TOOL_SPECS:
        assert t["description"]
        assert t["parameters"]["type"] == "object"


def test_validate_sql_ok_and_error():
    reg = ToolRegistry()
    assert reg.call("validate_sql", {"sql": "SELECT 1"}) == {"ok": True}
    bad = reg.call("validate_sql", {"sql": "DELETE FROM t"})
    assert bad["ok"] is False and "error" in bad


def test_compute_stats_tool_wraps_engine():
    reg = ToolRegistry()
    out = reg.call(
        "compute_stats",
        {"columns": ["x"], "rows": [[1], [2], [3]], "spec": {"op": "describe", "columns": ["x"]}},
    )
    assert out["ok"] is True and out["result"]["x"]["sum"] == 6


def test_compute_stats_tool_swallows_error():
    reg = ToolRegistry()
    out = reg.call("compute_stats", {"columns": ["x"], "rows": [[1]], "spec": {"op": "bogus"}})
    assert out["ok"] is False and "error" in out


def test_build_definition_uses_injected_validator():
    reg = ToolRegistry(validate_definition=lambda d: (False, "unknown source"))
    out = reg.call("build_definition", {"definition": {"source": "x"}})
    assert out == {"ok": False, "error": "unknown source"}


def test_build_definition_ok():
    reg = ToolRegistry(validate_definition=lambda d: (True, None))
    assert reg.call("build_definition", {"definition": {"source": "ok"}}) == {"ok": True}


def test_run_sql_requires_binding():
    reg = ToolRegistry()  # no runner bound
    out = reg.call("run_sql", {"target": "statistics", "sql": "SELECT 1"})
    assert out["ok"] is False and "not available" in out["error"].lower()


def test_run_sql_uses_injected_runner():
    reg = ToolRegistry(run_sql=lambda target, sql: ([{"field": "n", "header": "n"}], [[1]]))
    out = reg.call("run_sql", {"target": "statistics", "sql": "SELECT 1 AS n"})
    assert out["ok"] is True and out["rows"] == [[1]] and out["rowCount"] == 1


def test_run_sql_swallows_runner_error():
    def boom(target, sql):
        raise RuntimeError("SQL source not configured")

    reg = ToolRegistry(run_sql=boom)
    out = reg.call("run_sql", {"target": "statistics", "sql": "SELECT 1"})
    assert out["ok"] is False and "not configured" in out["error"]


def test_unknown_tool_errors():
    reg = ToolRegistry()
    out = reg.call("frobnicate", {})
    assert out["ok"] is False


def test_run_sql_odbc_error_is_humanized_by_generic_choke_point():
    # Task 6: ToolRegistry.call's generic except (the choke point every tool
    # handler funnels through) must humanize a raw pyodbc/ODBC error the same
    # way sandbox.humanize_sql_error does — no driver noise reaching the model
    # or the tool trace, and a teaching hint for known codes.
    odbc_text = (
        "('42000', '[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
        "The ORDER BY clause is invalid in views, inline functions, derived "
        "tables, subqueries, and common table expressions, unless TOP, OFFSET "
        "or FOR XML is also specified. (1033) (SQLExecDirectW)')"
    )

    def boom(target, sql):
        raise RuntimeError(odbc_text)

    reg = ToolRegistry(run_sql=boom)
    out = reg.call("run_sql", {"target": "statistics", "sql": "SELECT 1"})
    assert out["ok"] is False
    assert "SQLExecDirectW" not in out["error"]
    assert "[Microsoft]" not in out["error"]
    assert "Hint:" in out["error"]
