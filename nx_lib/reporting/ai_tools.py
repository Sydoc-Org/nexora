"""Tool layer for the Reporting AI agentic loop (Phase 3b).

Each tool wraps an existing nexora rail and returns a JSON-serialisable envelope.
Tools NEVER raise across the boundary: failures become ``{"ok": False, "error": ...}``
so the loop can feed the error back and let the model self-repair. The model
proposes; these wrappers + the rails they call dispose. Pure tools (validate_sql,
compute_stats) are built in; ``run_sql`` and ``build_definition`` are injected by
the route because they need request scope (permissions, RO engines, catalogs).
"""

from .sandbox import SqlSandboxError, validate_select
from .stats import StatsError, compute_stats

# Provider-neutral tool catalogue (translated to Anthropic/Azure shapes in ai.py).
TOOL_SPECS = [
    {
        "name": "validate_sql",
        "description": (
            "Check whether a T-SQL string is one read-only SELECT that passes the "
            "sandbox gate. Always call this before run_sql."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "The T-SQL SELECT to check."}},
            "required": ["sql"],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Execute a validated read-only SELECT on a read-only target and return "
            "capped rows. Targets: 'statistics' or 'octopus'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["statistics", "octopus"]},
                "sql": {"type": "string"},
            },
            "required": ["target", "sql"],
        },
    },
    {
        "name": "build_definition",
        "description": (
            "Validate a v1 report-definition against its source field catalog "
            "(whitelist-safe, no SQL). Use for simple builder reports."
        ),
        "parameters": {
            "type": "object",
            "properties": {"definition": {"type": "object"}},
            "required": ["definition"],
        },
    },
    {
        "name": "compute_stats",
        "description": (
            "Compute deterministic statistics over rows you already fetched. ops: "
            "describe, group_by, percentiles, value_counts, correlation, top_n."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array"}},
                "spec": {"type": "object", "description": "{'op': ..., ...} — see op list."},
            },
            "required": ["columns", "rows", "spec"],
        },
    },
]


class ToolRegistry:
    """Dispatch tool calls to bound implementations.

    ``run_sql`` is a callable ``(target, sql) -> (columns, rows)`` (bound only when
    the caller holds reporting.ai.sql). ``validate_definition`` is a callable
    ``(definition) -> (ok, error)`` (the Surface-A validator). Both default to None,
    in which case their tools report themselves unavailable.
    """

    def __init__(self, *, run_sql=None, validate_definition=None):
        self._run_sql = run_sql
        self._validate_definition = validate_definition

    def call(self, name, args):
        try:
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                return {"ok": False, "error": f"unknown tool: {name}"}
            return handler(args or {})
        except Exception as e:  # never let a tool break the loop
            return {"ok": False, "error": str(e) or e.__class__.__name__}

    def _tool_validate_sql(self, args):
        try:
            validate_select(args.get("sql"))
            return {"ok": True}
        except SqlSandboxError as e:
            return {"ok": False, "error": str(e)}

    def _tool_run_sql(self, args):
        if self._run_sql is None:
            return {
                "ok": False,
                "error": "run_sql is not available (no SQL permission or read-only engine unconfigured)",
            }
        columns, rows = self._run_sql(args.get("target"), args.get("sql"))
        return {"ok": True, "columns": columns, "rows": rows, "rowCount": len(rows)}

    def _tool_build_definition(self, args):
        if self._validate_definition is None:
            return {"ok": False, "error": "build_definition is not available"}
        ok, error = self._validate_definition(args.get("definition"))
        return {"ok": True} if ok else {"ok": False, "error": error}

    def _tool_compute_stats(self, args):
        try:
            result = compute_stats(
                args.get("columns") or [], args.get("rows") or [], args.get("spec") or {}
            )
            return {"ok": True, **result}
        except StatsError as e:
            return {"ok": False, "error": str(e)}
