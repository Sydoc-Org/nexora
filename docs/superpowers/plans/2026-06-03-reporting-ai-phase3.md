# Reporting AI Phase 3 — Agentic tool-loop + deterministic stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Reporting AI assistant from single-shot drafting (Phase 1/2) into a **Tier-2 agentic tool-loop** that inspects the schema, drafts, self-repairs against the existing gates, runs read-only queries, and computes **deterministic statistics** — all over the rails we already own.

**Architecture:** The model is given a small set of **tools** that wrap existing nexora rails (sqlglot gate, RO engines, Surface-A whitelist validator, a new pure-Python stats engine). A provider-agnostic loop (`ask_agentic`) drives: *model → tool calls → execute → feed results back → repeat* until a validated answer or a hard turn cap. Nothing executes outside the existing gates; egress stays schema-only by default (sending result **rows/stats** to the model is deferred to Phase 3e behind a new gated permission + a governance decision). The loop logic is separated from provider tool-calling parsing so both are unit-testable offline via injected seams (`agent_step` / `transport`).

**Tech Stack:** Python 3 stdlib only for stats (`statistics`, `math` — *no pandas/scipy*, to keep the IIS/WSGI deploy light); existing `requests`-based raw-HTTP provider layer in `nx_lib/reporting/ai.py`; sqlglot gate in `sandbox.py`; Flask route + vanilla-JS inline partial for UI; `dbo.ReportingAiAudit` for audit.

---

## Phase map (sub-phases by dependency & governance)

| Sub-phase | Deliverable | New perm/migration? | Offline-testable? | This session |
|---|---|---|---|---|
| **3a** | `compute_stats` deterministic engine (`stats.py`) | no | yes (pure) | ✅ implement |
| **3b** | Tool layer (`ai_tools.py`) wrapping existing rails + stats | no | yes (contracts) | ✅ implement |
| **3c** | Agentic loop driver (`ai.py: ask_agentic` + `_dispatch_tools`) | no | yes (fake seams) | ✅ implement |
| **3d** | Route `POST /api/reporting/ai/agent` + "Ask AI" agentic UI w/ visible tool steps + follow-up | no | route: yes / UI: needs live server | ⏳ route + tests now; UI spec'd, browser-verify follow-up |
| **3e** | `reporting.ai.explain_data` (send rows/stats to model) + glossary RAG | **yes (migration + perm)** | n/a | ⛔ deferred — needs governance decision (design §13-Q2/Q5) |

**Governance decision that gates 3e (surface to owner, do not assume):** design doc §4/§13-Q2 — *is sending result rows or computed stats to the model ever acceptable for narration?* Until decided, Phase 3a–3d keep the **schema-only, no-row-egress** posture: `compute_stats` runs server-side and its results render in the UI deterministically; they are **not** sent back to the model. The "explain these numbers" narration is Phase 3e only.

---

## File structure

- `nx_lib/reporting/stats.py` — **NEW**. Pure-Python deterministic stats over `(columns, rows)` result sets. One responsibility: numbers. No Flask, no DB, no network.
- `nx_lib/reporting/ai_tools.py` — **NEW**. Tool specifications (provider-neutral JSON-schema) + a `ToolRegistry` dispatcher mapping tool-name → callable. Wraps `validate_select`, the Surface-A validator, `compute_stats`, and an injected `run_sql` callable. No provider/HTTP code.
- `nx_lib/reporting/ai.py` — **MODIFY**. Add `_dispatch_tools` (provider-agnostic tool-calling round-trip; Anthropic `tool_use`/`tool_result` + Azure OpenAI `tool_calls`/role:tool) and `ask_agentic` (the loop) + `AiAgenticResult`. Keep `ask`/`ask_definition` unchanged.
- `nx_lib/views/reporting.py` — **MODIFY** (3d). Add `POST /api/reporting/ai/agent` mirroring `api_ai_build`'s gating/audit/limit. Reuse `_run_sql`, `_ai_catalog_text`, `_validate_definition_for_user`, `_audit_ai`.
- `templates/reporting.html`, `templates/js/_reporting_ai_js.html` — **MODIFY** (3d). Agentic sub-mode + visible tool-step trace + follow-up input. i18n all strings.
- Tests: `tests/unit/test_reporting_stats.py` (3a), `tests/unit/test_reporting_ai_tools.py` (3b), `tests/unit/test_reporting_ai_agentic.py` (3c), `tests/integration/test_reporting_ai_routes.py` (extend, 3d).

---

## Phase 3a — Deterministic stats engine

### Task 1: `StatsError` + `describe` op

**Files:**
- Create: `nx_lib/reporting/stats.py`
- Test: `tests/unit/test_reporting_stats.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_stats.py
import math
import pytest
from nx_lib.reporting.stats import compute_stats, StatsError

COLS = ["process", "qty"]
ROWS = [["A", 10], ["A", 20], ["B", 30], ["B", None], ["B", 50]]


def test_describe_numeric_column():
    out = compute_stats(COLS, ROWS, {"op": "describe", "columns": ["qty"]})
    q = out["result"]["qty"]
    assert q["count"] == 4 and q["nulls"] == 1
    assert q["min"] == 10 and q["max"] == 50
    assert q["sum"] == 110 and q["mean"] == 27.5
    assert q["median"] == 25.0
    assert math.isclose(q["stddev"], 17.07825127, rel_tol=1e-6)


def test_describe_text_column():
    out = compute_stats(COLS, ROWS, {"op": "describe", "columns": ["process"]})
    q = out["result"]["process"]
    assert q["count"] == 5 and q["distinct"] == 2
    assert q["top"] == "B"  # most frequent


def test_unknown_column_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "describe", "columns": ["nope"]})


def test_unknown_op_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "bogus"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_stats.py -q`
Expected: FAIL — `ModuleNotFoundError: nx_lib.reporting.stats`.

- [ ] **Step 3: Write minimal implementation**

```python
# nx_lib/reporting/stats.py
"""Deterministic statistics over a (columns, rows) result set.

Pure stdlib (no pandas/scipy) so it adds no runtime dependency to the WSGI app.
The model decides *what* to compute (the spec); this module computes it exactly
and reproducibly. Numbers never depend on the LLM's arithmetic.
"""

import math
import statistics
from collections import Counter

MAX_STATS_ROWS = 100_000  # defensive cap; callers already row-cap upstream


class StatsError(ValueError):
    """Raised when a stats spec is malformed or references unknown columns."""


def _col_index(columns, field):
    names = [c["field"] if isinstance(c, dict) else c for c in columns]
    if field not in names:
        raise StatsError(f"unknown column: {field!r}")
    return names.index(field)


def _column_values(columns, rows, field, *, drop_null=True):
    idx = _col_index(columns, field)
    vals = [r[idx] for r in rows]
    if drop_null:
        vals = [v for v in vals if v is not None]
    return vals


def _as_numbers(values):
    out = []
    for v in values:
        if isinstance(v, bool):  # bool is an int subclass; exclude
            raise StatsError("non-numeric value in numeric stat")
        if isinstance(v, (int, float)):
            out.append(float(v))
        else:
            raise StatsError(f"non-numeric value: {v!r}")
    return out


def _describe_one(columns, rows, field):
    idx = _col_index(columns, field)
    raw = [r[idx] for r in rows]
    non_null = [v for v in raw if v is not None]
    numericish = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null)
    base = {"count": len(non_null), "nulls": len(raw) - len(non_null)}
    if non_null and numericish:
        nums = [float(v) for v in non_null]
        base.update(
            min=min(nums), max=max(nums), sum=sum(nums),
            mean=statistics.fmean(nums),
            median=statistics.median(nums),
            stddev=statistics.pstdev(nums) if len(nums) > 1 else 0.0,
            variance=statistics.pvariance(nums) if len(nums) > 1 else 0.0,
        )
    else:
        counts = Counter(non_null)
        base.update(
            distinct=len(counts),
            top=counts.most_common(1)[0][0] if counts else None,
        )
    return base


def compute_stats(columns, rows, spec):
    """Compute `spec` over the result set. Returns {"op": ..., "result": ...}."""
    if not isinstance(spec, dict):
        raise StatsError("spec must be an object")
    if len(rows) > MAX_STATS_ROWS:
        raise StatsError(f"too many rows for stats: {len(rows)} > {MAX_STATS_ROWS}")
    op = spec.get("op")
    if op == "describe":
        fields = spec.get("columns") or []
        if not fields:
            raise StatsError("describe requires a non-empty 'columns' list")
        return {"op": op, "result": {f: _describe_one(columns, rows, f) for f in fields}}
    raise StatsError(f"unknown stats op: {op!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_stats.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/stats.py tests/unit/test_reporting_stats.py
git commit -m "feat(reporting): deterministic stats engine — describe op (Phase 3a)"
```

### Task 2: `group_by`, `percentiles`, `value_counts`, `correlation`, `top_n`

**Files:**
- Modify: `nx_lib/reporting/stats.py`
- Test: `tests/unit/test_reporting_stats.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_group_by_sum_and_mean():
    out = compute_stats(COLS, ROWS, {
        "op": "group_by", "by": ["process"],
        "agg": {"qty": ["sum", "mean", "count"]},
    })
    rows = {tuple(r["group"]): r["values"] for r in out["result"]}
    assert rows[("A",)]["qty"]["sum"] == 30 and rows[("A",)]["qty"]["mean"] == 15.0
    assert rows[("B",)]["qty"]["sum"] == 80 and rows[("B",)]["qty"]["count"] == 2


def test_percentiles_linear_interpolation():
    cols, rows = ["x"], [[i] for i in range(1, 101)]  # 1..100
    out = compute_stats(cols, rows, {"op": "percentiles", "column": "x", "q": [0.5, 0.9, 0.95]})
    r = out["result"]
    assert r["0.5"] == 50.5
    assert math.isclose(r["0.9"], 90.1, rel_tol=1e-9)


def test_value_counts_top_n():
    out = compute_stats(COLS, ROWS, {"op": "value_counts", "column": "process", "top_n": 1})
    assert out["result"] == [{"value": "B", "count": 3}]


def test_correlation_perfect_positive():
    cols, rows = ["a", "b"], [[1, 2], [2, 4], [3, 6], [4, 8]]
    out = compute_stats(cols, rows, {"op": "correlation", "x": "a", "y": "b"})
    assert math.isclose(out["result"]["r"], 1.0, rel_tol=1e-9)


def test_correlation_zero_variance_raises():
    cols, rows = ["a", "b"], [[1, 5], [1, 6], [1, 7]]
    with pytest.raises(StatsError):
        compute_stats(cols, rows, {"op": "correlation", "x": "a", "y": "b"})


def test_top_n_descending():
    out = compute_stats(COLS, ROWS, {"op": "top_n", "by": "qty", "n": 2})
    assert [r[1] for r in out["result"]] == [50, 30]
```

- [ ] **Step 2: Run to verify failure**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_stats.py -q`
Expected: FAIL — the new ops raise `unknown stats op`.

- [ ] **Step 3: Implement the ops** (add to `compute_stats`, plus helpers)

```python
_AGG_FUNCS = {
    "count": lambda n: len(n),
    "sum": lambda n: sum(n),
    "min": lambda n: min(n) if n else None,
    "max": lambda n: max(n) if n else None,
    "mean": lambda n: statistics.fmean(n) if n else None,
    "median": lambda n: statistics.median(n) if n else None,
    "stddev": lambda n: statistics.pstdev(n) if len(n) > 1 else 0.0,
}


def _percentile(sorted_nums, q):
    if not sorted_nums:
        raise StatsError("percentile of empty column")
    if not 0.0 <= q <= 1.0:
        raise StatsError(f"quantile out of range: {q}")
    if len(sorted_nums) == 1:
        return sorted_nums[0]
    pos = q * (len(sorted_nums) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_nums[lo]
    frac = pos - lo
    return sorted_nums[lo] * (1 - frac) + sorted_nums[hi] * frac


def _group_by(columns, rows, by, agg):
    by_idx = [_col_index(columns, f) for f in by]
    agg_idx = {f: _col_index(columns, f) for f in agg}
    buckets = {}
    for r in rows:
        key = tuple(r[i] for i in by_idx)
        buckets.setdefault(key, []).append(r)
    result = []
    for key in sorted(buckets, key=lambda k: tuple("" if v is None else v for v in k)):
        group_rows = buckets[key]
        values = {}
        for field, funcs in agg.items():
            nums = _as_numbers([gr[agg_idx[field]] for gr in group_rows if gr[agg_idx[field]] is not None])
            values[field] = {fn: _AGG_FUNCS[fn](nums) for fn in funcs if _check_func(fn)}
        result.append({"group": list(key), "values": values})
    return result


def _check_func(fn):
    if fn not in _AGG_FUNCS:
        raise StatsError(f"unknown agg function: {fn!r}")
    return True
```

Then extend `compute_stats` with branches:

```python
    if op == "group_by":
        by = spec.get("by") or []
        agg = spec.get("agg") or {}
        if not by or not agg:
            raise StatsError("group_by requires 'by' and 'agg'")
        return {"op": op, "result": _group_by(columns, rows, by, agg)}
    if op == "percentiles":
        nums = sorted(_as_numbers(_column_values(columns, rows, spec["column"])))
        qs = spec.get("q") or [0.5]
        return {"op": op, "result": {str(q): _percentile(nums, q) for q in qs}}
    if op == "value_counts":
        vals = _column_values(columns, rows, spec["column"])
        counts = Counter(vals).most_common(spec.get("top_n"))
        return {"op": op, "result": [{"value": v, "count": c} for v, c in counts]}
    if op == "correlation":
        xs = _as_numbers(_column_values(columns, rows, spec["x"], drop_null=False))
        ys = _as_numbers(_column_values(columns, rows, spec["y"], drop_null=False))
        if len(xs) != len(ys) or len(xs) < 2:
            raise StatsError("correlation needs two equal-length numeric columns (n>=2)")
        try:
            r = statistics.correlation(xs, ys)
        except statistics.StatisticsError as e:
            raise StatsError(str(e)) from e
        return {"op": op, "result": {"r": r, "n": len(xs)}}
    if op == "top_n":
        idx = _col_index(columns, spec["by"])
        ascending = bool(spec.get("ascending"))
        keyed = [r for r in rows if r[idx] is not None]
        keyed.sort(key=lambda r: r[idx], reverse=not ascending)
        return {"op": op, "result": keyed[: int(spec.get("n", 10))]}
```

> Note: `spec["column"]`/`spec["x"]` KeyError → let it surface as `StatsError` by guarding with `.get` and an explicit raise if missing. Add at the top of each branch: `if not spec.get("column"): raise StatsError("...requires 'column'")`.

- [ ] **Step 4: Run to verify pass**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_stats.py -q`
Expected: PASS (all stats tests).

- [ ] **Step 5: ruff + commit**

```bash
C:/dev/nexora/.venv/Scripts/python.exe -m ruff check nx_lib/reporting/stats.py
git add nx_lib/reporting/stats.py tests/unit/test_reporting_stats.py
git commit -m "feat(reporting): stats engine — group_by/percentiles/value_counts/correlation/top_n (Phase 3a)"
```

---

## Phase 3b — Tool layer

### Task 3: Tool specs + `ToolRegistry` dispatcher

**Files:**
- Create: `nx_lib/reporting/ai_tools.py`
- Test: `tests/unit/test_reporting_ai_tools.py`

Design: each tool returns a **JSON-serialisable envelope** `{"ok": bool, ...}` (never raises across the boundary — errors become `{"ok": False, "error": "..."}` so the loop can feed them back for self-repair). `TOOL_SPECS` is the provider-neutral list (name, description, JSON-schema params). `ToolRegistry` holds bound callables; `validate_sql`/`build_definition`/`compute_stats` are pure; `run_sql` is injected (the route binds `_run_sql`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_ai_tools.py
from nx_lib.reporting.ai_tools import TOOL_SPECS, ToolRegistry


def test_specs_are_provider_neutral():
    names = {t["name"] for t in TOOL_SPECS}
    assert {"validate_sql", "compute_stats", "build_definition"} <= names
    for t in TOOL_SPECS:
        assert t["description"] and t["parameters"]["type"] == "object"


def test_validate_sql_ok_and_error():
    reg = ToolRegistry()
    assert reg.call("validate_sql", {"sql": "SELECT 1"}) == {"ok": True}
    bad = reg.call("validate_sql", {"sql": "DELETE FROM t"})
    assert bad["ok"] is False and "error" in bad


def test_compute_stats_tool_wraps_engine():
    reg = ToolRegistry()
    out = reg.call("compute_stats", {
        "columns": ["x"], "rows": [[1], [2], [3]],
        "spec": {"op": "describe", "columns": ["x"]},
    })
    assert out["ok"] is True and out["result"]["x"]["sum"] == 6


def test_compute_stats_tool_swallows_error():
    reg = ToolRegistry()
    out = reg.call("compute_stats", {"columns": ["x"], "rows": [[1]], "spec": {"op": "bogus"}})
    assert out["ok"] is False and "error" in out


def test_build_definition_uses_injected_validator():
    reg = ToolRegistry(validate_definition=lambda d: (False, "unknown source"))
    out = reg.call("build_definition", {"definition": {"source": "x"}})
    assert out == {"ok": False, "error": "unknown source"}


def test_run_sql_requires_binding():
    reg = ToolRegistry()  # no runner bound
    out = reg.call("run_sql", {"target": "statistics", "sql": "SELECT 1"})
    assert out["ok"] is False and "not available" in out["error"].lower()


def test_run_sql_uses_injected_runner():
    reg = ToolRegistry(run_sql=lambda target, sql: ([{"field": "n", "header": "n"}], [[1]]))
    out = reg.call("run_sql", {"target": "statistics", "sql": "SELECT 1 AS n"})
    assert out["ok"] is True and out["rows"] == [[1]]


def test_unknown_tool_errors():
    reg = ToolRegistry()
    out = reg.call("frobnicate", {})
    assert out["ok"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_ai_tools.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# nx_lib/reporting/ai_tools.py
"""Tool layer for the Reporting AI agentic loop.

Each tool wraps an existing nexora rail and returns a JSON-serialisable envelope.
Tools NEVER raise across the boundary: failures become {"ok": False, "error": ...}
so the loop can feed the error back and let the model self-repair. The model
proposes; these wrappers + the rails they call dispose.
"""

from .sandbox import SqlSandboxError, validate_select
from .stats import StatsError, compute_stats

# Provider-neutral tool catalogue (translated to Anthropic/Azure shapes in ai.py).
TOOL_SPECS = [
    {
        "name": "validate_sql",
        "description": "Check whether a T-SQL string is one read-only SELECT that passes the sandbox gate. Call this before run_sql.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
    {
        "name": "run_sql",
        "description": "Execute a validated read-only SELECT on a read-only target and return capped rows. Targets: 'statistics' or 'octopus'.",
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
        "description": "Validate a v1 report-definition against its source field catalog (whitelist-safe, no SQL). Use for simple builder reports.",
        "parameters": {
            "type": "object",
            "properties": {"definition": {"type": "object"}},
            "required": ["definition"],
        },
    },
    {
        "name": "compute_stats",
        "description": "Compute deterministic statistics over rows you already fetched. ops: describe, group_by, percentiles, value_counts, correlation, top_n.",
        "parameters": {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array"}},
                "spec": {"type": "object"},
            },
            "required": ["columns", "rows", "spec"],
        },
    },
]


class ToolRegistry:
    """Dispatch tool calls to bound implementations. Pure tools are built in;
    run_sql / build_definition are injected by the route (they need request scope).
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
            return {"ok": False, "error": "run_sql is not available (no SQL permission or RO engine unconfigured)"}
        columns, rows = self._run_sql(args.get("target"), args.get("sql"))
        return {"ok": True, "columns": columns, "rows": rows, "rowCount": len(rows)}

    def _tool_build_definition(self, args):
        if self._validate_definition is None:
            return {"ok": False, "error": "build_definition is not available"}
        ok, error = self._validate_definition(args.get("definition"))
        return {"ok": True} if ok else {"ok": False, "error": error}

    def _tool_compute_stats(self, args):
        try:
            result = compute_stats(args.get("columns") or [], args.get("rows") or [], args.get("spec") or {})
            return {"ok": True, **result}
        except StatsError as e:
            return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: Run to verify pass**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_ai_tools.py -q`
Expected: PASS.

- [ ] **Step 5: ruff + commit**

```bash
C:/dev/nexora/.venv/Scripts/python.exe -m ruff check nx_lib/reporting/ai_tools.py
git add nx_lib/reporting/ai_tools.py tests/unit/test_reporting_ai_tools.py
git commit -m "feat(reporting): AI tool layer wrapping gate/run/definition/stats (Phase 3b)"
```

---

## Phase 3c — Agentic loop driver

### Task 4: `ask_agentic` loop over an injected `agent_step`

The loop is separated from provider parsing: it consumes an `agent_step(messages) -> AssistantTurn` callable. Tests inject a scripted `agent_step`; production builds it from `_dispatch_tools` (Task 5).

**Files:**
- Modify: `nx_lib/reporting/ai.py`
- Test: `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_ai_agentic.py
from nx_lib.reporting.ai import AssistantTurn, ask_agentic
from nx_lib.reporting.ai_tools import ToolRegistry


def _script(*turns):
    """Return an agent_step that yields the given turns in order."""
    seq = iter(turns)

    def step(messages):
        return next(seq)

    return step


def test_loop_runs_tool_then_returns_final_answer():
    reg = ToolRegistry()
    step = _script(
        AssistantTurn(text="", tool_calls=[{"id": "1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}], tokens_in=10, tokens_out=5),
        AssistantTurn(text="It is valid.", tool_calls=[], tokens_in=4, tokens_out=3),
    )
    res = ask_agentic("is this ok?", registry=reg, agent_step=step, max_turns=5)
    assert res.answer == "It is valid."
    assert res.turns == 2
    assert res.tool_trace[0]["name"] == "validate_sql" and res.tool_trace[0]["result"]["ok"] is True
    assert res.tokens_in == 14 and res.tokens_out == 8


def test_self_repair_feeds_error_back():
    reg = ToolRegistry()
    step = _script(
        AssistantTurn(text="", tool_calls=[{"id": "1", "name": "validate_sql", "args": {"sql": "DELETE FROM t"}}]),
        AssistantTurn(text="", tool_calls=[{"id": "2", "name": "validate_sql", "args": {"sql": "SELECT 1"}}]),
        AssistantTurn(text="Fixed.", tool_calls=[]),
    )
    res = ask_agentic("q", registry=reg, agent_step=step, max_turns=5)
    assert res.answer == "Fixed."
    assert res.tool_trace[0]["result"]["ok"] is False  # first rejected
    assert res.tool_trace[1]["result"]["ok"] is True


def test_turn_cap_stops_runaway_loop():
    reg = ToolRegistry()
    forever = AssistantTurn(text="", tool_calls=[{"id": "x", "name": "validate_sql", "args": {"sql": "SELECT 1"}}])
    res = ask_agentic("q", registry=reg, agent_step=lambda m: forever, max_turns=3)
    assert res.turns == 3
    assert res.stopped_reason == "max_turns"
```

- [ ] **Step 2: Run to verify failure**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_ai_agentic.py -q`
Expected: FAIL — `AssistantTurn` / `ask_agentic` not defined.

- [ ] **Step 3: Implement (append to `ai.py`)**

```python
DEFAULT_MAX_TURNS = 6


@dataclass
class AssistantTurn:
    text: str = ""
    tool_calls: list | None = None  # [{"id","name","args"}]
    tokens_in: int | None = None
    tokens_out: int | None = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


@dataclass
class AiAgenticResult:
    answer: str
    turns: int
    tool_trace: list  # [{"name","args","result"}]
    stopped_reason: str  # "final" | "max_turns"
    tokens_in: int
    tokens_out: int


def ask_agentic(question, *, registry, agent_step, max_turns=DEFAULT_MAX_TURNS):
    """Drive the model→tool→model loop until a final answer or the turn cap.

    `agent_step(messages) -> AssistantTurn` is the injected provider round-trip
    (scripted in tests). `registry` is a ToolRegistry. Returns AiAgenticResult.
    No network or provider code lives here — that is `_dispatch_tools` / `_make_agent_step`.
    """
    messages = [{"role": "user", "content": question}]
    trace, tin, tout, turns, stopped = [], 0, 0, 0, "max_turns"
    while turns < max_turns:
        turns += 1
        turn = agent_step(messages)
        tin += turn.tokens_in or 0
        tout += turn.tokens_out or 0
        if not turn.tool_calls:
            stopped = "final"
            messages.append({"role": "assistant", "content": turn.text})
            return AiAgenticResult(turn.text, turns, trace, stopped, tin, tout)
        messages.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls})
        results = []
        for call in turn.tool_calls:
            result = registry.call(call["name"], call.get("args"))
            trace.append({"name": call["name"], "args": call.get("args"), "result": result})
            results.append({"tool_call_id": call.get("id"), "name": call["name"], "result": result})
        messages.append({"role": "tool", "content": results})
    return AiAgenticResult("", turns, trace, stopped, tin, tout)
```

- [ ] **Step 4: Run to verify pass**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_ai_agentic.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_agentic.py
git commit -m "feat(reporting): agentic tool-loop driver with self-repair + turn cap (Phase 3c)"
```

### Task 5: `_dispatch_tools` — provider tool-calling round-trip + `_make_agent_step`

Translates the neutral message list + `TOOL_SPECS` into each provider's tool-calling wire format and parses the assistant turn back into an `AssistantTurn`. Tested with a fake `transport` returning provider-shaped JSON (no network).

**Files:**
- Modify: `nx_lib/reporting/ai.py`
- Test: `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing tests** (Azure + Anthropic parsing)

```python
from nx_lib.reporting.ai import _make_agent_step
from nx_lib.reporting.ai_tools import TOOL_SPECS


def test_azure_tool_call_parsed():
    def fake_transport(url, headers, body, timeout):
        return {
            "choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "validate_sql", "arguments": '{"sql": "SELECT 1"}'}}]}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }
    step = _make_agent_step(system="s", tools=TOOL_SPECS, provider="azure", model="m",
                            api_key="k", endpoint="https://e", deployment="d", transport=fake_transport)
    turn = step([{"role": "user", "content": "q"}])
    assert turn.tool_calls[0]["name"] == "validate_sql"
    assert turn.tool_calls[0]["args"] == {"sql": "SELECT 1"}
    assert turn.tokens_in == 11 and turn.tokens_out == 7


def test_azure_final_answer_parsed():
    def fake_transport(url, headers, body, timeout):
        return {"choices": [{"message": {"content": "done"}}], "usage": {}}
    step = _make_agent_step(system="s", tools=TOOL_SPECS, provider="azure", model="m",
                            api_key="k", endpoint="https://e", deployment="d", transport=fake_transport)
    turn = step([{"role": "user", "content": "q"}])
    assert turn.text == "done" and turn.tool_calls == []


def test_anthropic_tool_use_parsed():
    def fake_transport(url, headers, body, timeout):
        return {"content": [
            {"type": "text", "text": "let me check"},
            {"type": "tool_use", "id": "tu1", "name": "validate_sql", "input": {"sql": "SELECT 1"}},
        ], "usage": {"input_tokens": 3, "output_tokens": 9}}
    step = _make_agent_step(system="s", tools=TOOL_SPECS, provider="anthropic", model="m",
                            api_key="k", transport=fake_transport)
    turn = step([{"role": "user", "content": "q"}])
    assert turn.tool_calls[0] == {"id": "tu1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}
```

- [ ] **Step 2: Run to verify failure**

Run: `C:/dev/nexora/.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_ai_agentic.py -q`
Expected: FAIL — `_make_agent_step` undefined.

- [ ] **Step 3: Implement** — `_make_agent_step` builds a closure that, per call, (a) translates the neutral `messages` into provider wire format (with `tool_use`/`tool_result` for Anthropic; `assistant.tool_calls` + role:`tool` for Azure), (b) POSTs via `transport`, (c) parses into `AssistantTurn`. Provide `_to_anthropic_messages` / `_to_azure_messages` translators and `_anthropic_tools(TOOL_SPECS)` / `_azure_tools(TOOL_SPECS)` spec adapters. (Full code authored at implementation time against the two providers' documented shapes; both paths fully covered by the fake-transport tests above — extend with a multi-turn round-trip test that includes a prior `tool` result to prove the translators emit the right wire format.)

- [ ] **Step 4: Run to verify pass.** Expected: PASS.

- [ ] **Step 5: ruff + commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_agentic.py
git commit -m "feat(reporting): provider tool-calling round-trip for agentic loop (Phase 3c)"
```

---

## Phase 3d — Route + UI (route + tests this session; UI browser-verify follow-up)

### Task 6: `POST /api/reporting/ai/agent`

**Files:**
- Modify: `nx_lib/views/reporting.py` (add route after `api_ai_build`, register in the same place)
- Test: `tests/integration/test_reporting_ai_routes.py`

Behaviour, mirroring `api_ai_build`:
- `@require_permission("reporting.ai.use")`, `@limiter.limit(...)` like the others.
- Build a `ToolRegistry`: always bind `compute_stats` (pure) + `build_definition` (→ `_validate_definition_for_user`). Bind `run_sql` **only if** `has_permission("reporting.ai.sql")` — else the model gets the schema-only subset and `run_sql` returns its "not available" envelope. (Row egress to the model stays off; this route returns the final answer + tool trace; rows fetched by `run_sql` are rendered client-side, not sent back to the model — that is Phase 3e.)
- Enforce `_ai_daily_limit()` / `_ai_asks_today()` exactly like `api_ai_build` (429 + `Status='blocked'`).
- `AiError` (provider misconfig) → audit `Status='misconfig'`, 503 (matches `3956a1b`).
- On success audit `Surface='agent'`, `Status='ok'`, store the final answer (or a compact trace summary) in `GeneratedSql`, `GateVerdict` = "valid" if a definition/sql tool ended `ok` else "n/a".
- Response JSON: `{answer, toolTrace, turns, stoppedReason, model, provider}`.

- [ ] **Step 1: failing integration test** — patch `nx_lib.views.reporting.ai_agentic`-equivalent (the route should call `ask_agentic` with a `_make_agent_step` built from config; in tests, monkeypatch `ask_agentic` to return a canned `AiAgenticResult`). Assert: 200 + JSON shape; an `AiError` path audits `misconfig`; over-limit returns 429.

```python
def test_agent_route_returns_answer_and_audits(client, ...):
    # grant reporting.ai.use; monkeypatch reporting.ask_agentic -> canned result
    # POST /api/reporting/ai/agent {"question": "..."} -> 200, json["answer"], json["turns"]
    ...
```

- [ ] **Step 2–5:** run (fail) → implement route → run (pass) → ruff + commit `feat(reporting): POST /api/reporting/ai/agent — agentic loop route (Phase 3d)`.

### Task 7: "Ask AI" agentic UI (browser-verify follow-up)

**Files:** `templates/reporting.html`, `templates/js/_reporting_ai_js.html` (+ `messages.pot`, `translations/*`).

- Add an **Agent** sub-mode (next to Build / Write-SQL) gated like the others. Render the **visible tool-step trace** (each step: tool name + ok/error chip) for trust, the final answer, and a **follow-up input** that re-POSTs with the conversation carried (server stateless: client resends prior Q/A as context, or the route accepts a `history` array — keep egress schema-only).
- i18n every new string (`{{ _() }}`); run the pybabel extract/update/compile cycle; keep `test_translations.py` green.
- **Verification:** restart INT (`bin\nx.ps1 -r`), `/dev/login/ben.streich` → `/reporting` → Ask AI → Agent; screenshot the tool-step trace + a follow-up. (Needs the running server + live Azure provider — do on a session with env; this plan's offline tasks 1–6 do not.)

---

## Phase 3e — DEFERRED (needs governance decision + migration)

Do **not** implement until the owner decides design §13-Q2 (row/stats egress) and §13-Q5 (glossary ownership).

- **`reporting.ai.explain_data`** permission (new migration `sql/_migrations/NexoraDB/00NN_reporting_ai_explain_data.sql`; admins seeded; mirror the `reporting.ai.*` seeding of migrations 0013/0014). Gates sending **result rows / computed stats** back to the model so it can *narrate* ("explain these numbers"). Until granted, the loop's results render deterministically client-side only.
- **Glossary RAG** (Tier 3): `dbo.ReportingAiGlossary` (term → definition) injected into the system prompt by relevance; optional embeddings later. Needs a curation owner.
- Update `docs/design/reporting-ai-assistant.md` §12 to mark Phase 3 status and CHANGELOG.

---

## Acceptance criteria (Phase 3a–3d)

- `compute_stats` computes describe/group_by/percentiles/value_counts/correlation/top_n exactly, pure-stdlib, with unit tests; malformed specs raise `StatsError` (never crash a caller).
- `ToolRegistry` dispatches every tool to an `{"ok": ...}` envelope and never raises across the boundary.
- `ask_agentic` runs the model→tool→model loop, feeds tool errors back for self-repair, and stops at `max_turns`; provider parsing covered for Azure + Anthropic via fake transport.
- `POST /api/reporting/ai/agent` is gated `reporting.ai.use`, binds `run_sql` only with `reporting.ai.sql`, honours `AI_DAILY_LIMIT`, audits `Surface='agent'` (and `misconfig` on `AiError`), and returns `{answer, toolTrace, turns}`.
- No new dependency, permission, table, or migration in 3a–3d. No data egress beyond question + schema metadata. Docs + CHANGELOG updated; `test_translations.py` green.

## Self-review notes

- **Spec coverage:** design §3 Tier-2 loop → Tasks 4–5; §10 `compute_stats` → Tasks 1–2; §6 audit (`Surface='agent'`) → Task 6; §9 visible tool steps + follow-up → Task 7; §4/§13 egress posture → 3e deferral + 3d "schema-only" rule.
- **Type consistency:** `AssistantTurn{text,tool_calls,tokens_in,tokens_out}`, `AiAgenticResult{answer,turns,tool_trace,stopped_reason,tokens_in,tokens_out}`, tool envelope `{"ok":bool,...,"error"?}`, `ToolRegistry(run_sql=, validate_definition=).call(name,args)`, `compute_stats(columns,rows,spec)->{"op","result"}` — used identically across Tasks 1–6.
- **No placeholders** in Tasks 1–4 (full code). Task 5 impl body and Tasks 6–7 are outlined with exact signatures/behaviour; their failing-test-first steps are concrete. Provider wire-format code is authored at implementation time against documented shapes and fully covered by the fake-transport tests.
