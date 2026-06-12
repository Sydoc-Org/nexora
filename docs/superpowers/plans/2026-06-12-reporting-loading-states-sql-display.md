# Reporting: Loading States & Formatted Collapsible SQL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every wait on the reporting page gets visible feedback — Simple and Advanced report runs (including chart renders) and all three Advanced Ask-AI surfaces show the existing pulsing-dots indicator while in flight — and the Show-query panel displays the executed SQL pretty-printed and syntax-highlighted instead of a raw one-line dump. The panel stays collapsed by default and user-expandable (it already is today — this plan pins that with an explicit e2e assertion).

**Architecture:** Loading states reuse the proven Simple-tab AI component (`.reporting-ai-loading` dots, reduced-motion-aware, e2e-latch-tested): a new always-present `#rsRunLoading` block covers Simple runs, a self-cleaning dots block injected into `#rpResults` (view forced to grid, Run button locked) covers Advanced runs, and a new `#rpAiLoading` block with rotating status lines covers all three Advanced AI surfaces. SQL formatting is server-side via sqlglot (already a direct dependency parsing `dialect="tsql"` in `nx_lib/reporting/sandbox.py`): a pure helper pretty-prints the executed SQL into a **new** `sqlPretty` response field — the raw `sql` field is untouched, so Copy and every existing consumer keep their contract. A tiny shared ES5 partial (`window.ReportingSqlFormat`) escape-then-highlights the displayed SQL into the existing `<pre>` elements on both tabs plus the AI Write-SQL draft.

**Tech Stack:** Flask, sqlglot 30.8.0 (existing pinned dep, zero new dependencies), Jinja2 + vanilla ES5 IIFE partials, Flask-Babel, pytest + Playwright.

---

## Context an engineer needs (read first)

- **Branch:** work executes on a worktree branch off `feature/2.5.63` (HEAD `9e8236c` at planning time — the rich-export work, including the Show-query panels, is already merged in). Conventional-commit subjects (imperative, ≤72 chars, no trailing period) **with a non-empty body** — gitlint's `body-is-missing` rule is active, so every commit below uses two `-m` flags. **Remote-session policy: stop at `git commit` — never push, never open a PR.** The owner pushes after review (the pre-push hook runs the FULL suite incl. Playwright e2e at that point).
- **SEQUENCING vs drill-through — do not skip:** the pending drill-through plan (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`) has executed only its Task 1; its Tasks 2–8 edit the same frontend files this plan rewrites (`_reporting_simple_js.html` `runCurrent`/`renderChart`/`renderTable`, `_reporting_js.html` `run`/`renderResults`, `reporting.html`, `_reporting_simple.html`, `reporting.css`). **Execute THIS plan first, drill-through second** — this plan is smaller, and the drill drawer can reuse the loading pattern this plan lands. Whoever executes drill-through afterwards must re-verify its quoted anchors against the post-merge tree (especially around `run()`, `runCurrent()` and `renderResults()`), never blind-paste. Do not run the two plans in parallel.
- **Anchor on quoted code snippets, never line numbers.** Every anchor below is a function name plus a verbatim snippet, verified against this worktree at planning time.
- **Migrations needed: NO.** Highest NexoraDB migration is `0021`; nothing here touches the DB.
- **New permissions: NO.** The Show-query button stays gated only by the `/run` response echoing a `sql` key (visible to anyone who can run reports — rich-export decision); SQL-sandbox runs never echo it; loading indicators are unconditional UI.
- **No new dependencies, no CDN scripts.** sqlglot 30.8.0 is already pinned in `requirements.txt`. The highlighter is ~60 lines of hand-rolled ES5 — vendoring or CDN-adding highlight.js would break the no-vendored-JS + pinned-CDN-with-SRI conventions for no gain.
- **The SQL panel is ALREADY collapsed by default** on both tabs (`#rsSqlView` / `#rpSqlView` carry `hidden`, are re-hidden on every run, and toggle via the `rsShowSql`/`rpShowSql` link buttons swapping the *Show query*/*Hide query* labels). Requirement (3) is satisfied structurally; this plan keeps those semantics unchanged and pins them with an explicit hidden-before-click e2e assertion (Task 4). The Simple AI ask/refine already has a full loading treatment (`#rsAiLoading`, pinned by `test_ai_ask_shows_loading_then_result`) — do not rebuild it.
- **Jinja template cache:** nexora caches templates for the process lifetime. Restart the dev server (`nx -u`, or `nx -u -b --loginas:<user>` for Playwright) after every template edit **before manual browser checks**. The pytest e2e fixture spawns its own fresh server per session, so test runs never need a restart.
- **E2E constraints:** the TEST env has **no Statistics DB** — e2e seeds `table`-provider sources over `dbo.Users` (engine `nexora`) via in-page `page.evaluate` POSTs to `/api/reporting/admin/sources` + `/api/reporting/admin/metrics` with DELETE cleanup in `finally` (exemplar: `tests/e2e/test_reporting_simple.py::test_show_query_reveals_sql`). Run `python scripts/test_db_reset.py` before e2e sessions (stale `ReportingSqlAck` rows fail order-dependent tests) and kill stale port-8765 servers: `Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | % { Stop-Process -Id $_.OwningProcess -Force }`.
- **Transient-state e2e idiom:** localhost responses are fast — never `expect(spinner).to_be_visible()`. Install a `MutationObserver` latch before the trigger click and assert the latch flag plus the hidden end-state (existing exemplar: `test_ai_ask_shows_loading_then_result`); use route-stub delays for AI requests.
- **Pre-commit:** ruff + ruff-format run on commit; if ruff-format reformats, the first attempt fails — `git add -u` and commit again. The INT SchemaMigrations CRLF drift makes the `sql-migrate-int` hook fail on Windows even with zero SQL changes — prefix every commit with `$env:SQL_SYNC_SKIP = "1"` (the documented escape hatch; **never** `--no-verify`).
- **i18n:** every new user-visible string goes through the pybabel cycle (Task 8) or `tests/unit/test_translations.py` fails the suite. This plan adds exactly **two** new msgids; the AI rotating lines reuse already-translated msgids (`Asking the AI…`, `Drafting your report…`, `Checking the result…` — all present in `messages.pot`). Until Task 8 runs, `test_translations.py` fails — expected mid-plan, and fine because nothing is pushed before then.
- **Verified facts** (checked against this working tree): `api_run` in `nx_lib/views/reporting.py` echoes `"sql": sql` + `"params": [_json_safe(p) for p in params]`; all reporting imports in that file are **relative** (`from ..reporting.…`); the Motion observer in `templates/js/_reporting_anim_js.html` only animates `TABLE` / `.reporting-empty` / `.reporting-error` children of `#rpResults`, so an injected loading `div` is animation-inert; `sqlglot.transpile(sql, read="tsql", write="tsql", pretty=True)` returns a list of pretty statements, preserves pyodbc `?` placeholders, normalizes tokens (`TOP (5000)` → `TOP 5000`, `) t` → `) AS t`), and raises `ParseError` on garbage (verified empirically against the pinned 30.8.0); `setView('grid')` is what un-hides `#rpResults` (it is hidden whenever `state.view !== 'grid'`); the Advanced `api()` helper **throws** on non-OK responses (unlike Simple's, which returns `{ok:false}`); `ai_enabled` is on in TEST (the existing Simple AI e2e passes there); the SQL-sandbox run returns 503 in TEST (no Statistics DB — pinned by the `test_reporting_sql.py` docstring); the `flaky_e2e` marker is registered in `pyproject.toml` and wired to pytest-rerunfailures in `tests/e2e/conftest.py`.
- **Housekeeping:** the stray unstaged deletion of `env/CONFLUENCE.env.example` in `git status` belongs to the `feat/confluence-docs-sync` worktree — do **not** commit or restore it here.

### Decisions locked in

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Loading visual | Existing pulsing-dots component (`.reporting-ai-loading` + `.reporting-ai-dots`) for ALL new indicators | CSS already exists incl. `prefers-reduced-motion` guard; one loading language per page; `fa-spinner` has zero precedent in the reporting templates; zero new animation CSS |
| 2 | Simple run indicator placement | Static `#rsRunLoading` sibling of `#rsAiLoading`, **outside** the `{% if ai_enabled %}` guard; static label, no rotating lines | Runs must show feedback even when AI is off; runs are seconds, not tens of seconds |
| 3 | Separate chart-render spinner | No — one indicator spans the whole `runCurrent()` (two sequential POSTs + synchronous Chart.js mount) | Chart mounts synchronously once rows arrive; per-request spinners would flicker; also avoids the `:has(#rsChartCard[hidden])` grid-collapse trap |
| 4 | Advanced run indicator | Dots block injected into `#rpResults`, **view forced to grid** + `#rpViewToggle` hidden, `#rpRun` disabled while in flight | `renderResults`/`showError` wholesale-replace `innerHTML`, so it self-cleans; `#rpResults` is hidden unless `state.view === 'grid'`, so forcing grid keeps the indicator visible when re-running from Chart/Pivot |
| 5 | Advanced double-click protection | Disabled Run button only — no `runSeq` token on Advanced | `rpRun` is the sole run trigger on Advanced, so disabling it fully prevents parallel requests; Simple keeps its existing `runSeq` (many triggers) |
| 6 | SQL-sandbox busy start | Busy starts **inside** the `ackThen` callback, never on the Run click | The acknowledgment modal can sit open indefinitely |
| 7 | Advanced AI loading | One shared `#rpAiLoading` dots block + rotating status lines for all three surfaces; the agent surface swaps in a long-wait line | Component, CSS and 3 of 4 msgids already exist translated; agent runs are the longest waits |
| 8 | SQL formatter | Server-side `sqlglot.transpile(read="tsql", write="tsql", pretty=True)` in new pure helper `nx_lib/reporting/sqlformat.py`, echoed as a **new** `sqlPretty` key; raw `sql` unchanged | sqlglot is already a dep parsing this exact dialect; sqlglot normalizes tokens, so the pretty string is display-only and the raw key keeps the Copy/export contract bit-exact |
| 9 | Multi-statement SQL | Join **all** transpiled statements with `;\n` | Never silently drop statements 2..n in a display field (hypothetical today, free correctness win) |
| 10 | Syntax highlighting | Hand-rolled ~60-line escape-as-you-emit ES5 tokenizer (`window.ReportingSqlFormat`) in a shared partial | No CDN/vendored lib (CSP/SRI + no-vendored-JS conventions); text content preserved so the existing `to_contain_text("SELECT")` e2e keeps passing |
| 11 | Copy buttons | Keep copying the **raw** `sql` + params comment | The panel header says "Query sent to the database" — what you copy is byte-exact what executed |
| 12 | Collapse semantics | Unchanged (button flips `hidden`, panel re-collapses on every run); pinned with a hidden-before-click e2e assert | Requirement already met; a `<details>` conversion is churn with no user benefit |
| 13 | AI-drafted SQL (`#rpAiSql`) | Client-side highlight only, no server pretty-print | The model already emits multi-line SQL; `api_ai_ask`'s contract stays untouched |
| 14 | Frontend fallback | Panels render `sqlPretty \|\| sql` | Graceful degradation if formatting ever fails server-side |

### Owner actions

**None.** No env vars, no migrations, no SQL logins, no scheduled tasks, no deploy-workflow changes (`templates/` and `static/` already ship; `docs/` is already excluded). Standing owner debt (push + PR for `feature/2.5.63`, PROD migrations, RO logins) is tracked elsewhere and unchanged by this plan.

---

# PHASE 1 — Server-side SQL pretty-printing (backend, independent)

### Task 1: `format_sql` helper — pure, best-effort, zero new deps

**Files:**
- Create: `nx_lib/reporting/sqlformat.py`
- Test: `tests/unit/test_reporting_sqlformat.py` (new)

- [ ] **Step 1: Write the failing tests.** Create `tests/unit/test_reporting_sqlformat.py`:

```python
"""Unit tests for the display-only T-SQL pretty-printer (sqlformat).

format_sql() feeds the Show-query panels' sqlPretty field. It must be
best-effort: anything sqlglot can't parse comes back unchanged, because a
formatting failure must never break a run response.
"""

import pytest

from nx_lib.reporting.sqlformat import format_sql

# Shape produced by build_table_query: one line, UNION ALL subqueries,
# pyodbc ? placeholders.
REAL_BUILDER_SQL = (
    "SELECT TOP (5000) [doctype] AS [doctype], COUNT(*) AS [cnt] "
    "FROM (SELECT [DocType] AS [doctype] FROM [dbo].[StatA] "
    "WHERE [ExportDate] >= ? AND [ExportDate] < ? "
    "UNION ALL SELECT [DocType] AS [doctype] FROM [dbo].[StatB] "
    "WHERE [ExportDate] >= ? AND [ExportDate] < ?) t "
    "GROUP BY [doctype] ORDER BY [cnt] DESC"
)


def test_single_line_builder_sql_becomes_multiline():
    out = format_sql(REAL_BUILDER_SQL)
    assert out != REAL_BUILDER_SQL
    assert "\n" in out
    lines = [ln.strip() for ln in out.splitlines()]
    assert any(ln.startswith("SELECT") for ln in lines)
    assert any(ln.startswith("GROUP BY") for ln in lines)


def test_placeholders_survive():
    # pyodbc binds positionally — losing or reordering a ? would lie to the user.
    out = format_sql(REAL_BUILDER_SQL)
    assert out.count("?") == REAL_BUILDER_SQL.count("?")


def test_semantic_text_survives():
    # sqlglot re-generates from the AST (e.g. TOP (n) -> TOP n) — that's fine,
    # but tables, the set op, and the aggregate must still be present.
    out = format_sql(REAL_BUILDER_SQL)
    for token in ("UNION ALL", "[dbo].[StatA]", "[dbo].[StatB]", "COUNT(*)"):
        assert token in out


def test_multiple_statements_are_all_kept():
    # Display-only field must never silently drop statements 2..n.
    out = format_sql("SELECT 1 AS a; SELECT 2 AS b")
    assert out.count("SELECT") == 2


@pytest.mark.parametrize("passthrough", ["THIS IS NOT ((( SQL", "", "   "])
def test_unparseable_or_blank_returns_input_unchanged(passthrough):
    assert format_sql(passthrough) == passthrough


def test_none_is_passed_through():
    assert format_sql(None) is None
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python -m pytest tests/unit/test_reporting_sqlformat.py -v
```
Expected: collection error — `ModuleNotFoundError: No module named 'nx_lib.reporting.sqlformat'`.

- [ ] **Step 3: Implement.** Create `nx_lib/reporting/sqlformat.py`:

```python
"""Display-only T-SQL pretty-printer for the reporting Show-query panels.

format_sql() is best-effort: any parse problem returns the input unchanged.
The executed SQL is never altered — api_run echoes the pretty string in a
separate response field (sqlPretty) and keeps the raw `sql` authoritative
(the Copy button and every other consumer read the raw field). sqlglot
re-renders from its AST and normalizes tokens (verified: ``TOP (5000)``
becomes ``TOP 5000``), so the pretty string is for DISPLAY ONLY.
"""

import sqlglot


def format_sql(sql):
    """Pretty-print a T-SQL string for display.

    Preserves pyodbc ``?`` placeholders and keeps every statement when the
    input contains more than one. Falls back to the input on any sqlglot
    error — an unformattable string must never break a run response.
    """
    if not isinstance(sql, str) or not sql.strip():
        return sql
    try:
        statements = sqlglot.transpile(sql, read="tsql", write="tsql", pretty=True)
    except Exception:
        return sql
    pretty = ";\n".join(s for s in statements if s)
    return pretty or sql
```

  (Repo ruff config selects `E,F,W,I,N,UP,B,SIM,RUF` — no BLE rule, so the deliberate broad `except Exception` with fallback is lint-clean.)

- [ ] **Step 4: Run green**

```powershell
python -m pytest tests/unit/test_reporting_sqlformat.py -v
```
Expected: 8 passed (6 functions, one parametrized ×3).

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/reporting/sqlformat.py tests/unit/test_reporting_sqlformat.py
git commit -m "feat(reporting): add sqlglot-based T-SQL pretty-printer helper" -m "Pure display-only formatter for the Show-query panels. Best-effort: falls back to the input on any parse error; preserves pyodbc ? placeholders and joins multi-statement input. Zero new dependencies (sqlglot already pinned)."
```

---

### Task 2: `/api/reporting/run` echoes `sqlPretty`

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_run` payload + import)
- Test: `tests/integration/test_reporting_routes.py`

- [ ] **Step 1: Write the failing test.** In `tests/integration/test_reporting_routes.py`, directly below the existing `test_run_response_includes_sql_and_params` (which pins the raw `sql`/`params` echo — leave it untouched), append:

```python
def test_run_response_includes_pretty_sql(admin_client):
    """/run also echoes a display-formatted copy (sqlPretty) of the SQL.

    The raw `sql` stays byte-exact (Copy and exports read it); sqlPretty is
    cosmetic and must be multi-line with placeholders preserved.
    """
    fake_cols = [{"field": "n", "header": "N"}]
    fake_sql = (
        "SELECT TOP (100) [a] AS [a], COUNT(*) AS [n] FROM "
        "(SELECT [A] AS [a] FROM [dbo].[T] WHERE [D] >= ? AND [D] < ?) t "
        "GROUP BY [a] ORDER BY [n] DESC"
    )
    fake_params = ["2026-01-01", "2026-02-01"]
    fake_rows = [["x", 1]]
    with (
        patch(
            "nx_lib.views.reporting._prepare_run",
            return_value=(fake_cols, fake_sql, fake_params, None),
        ),
        patch("nx_lib.views.reporting._execute", return_value=fake_rows),
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.views.reporting._resolved_dates_meta", return_value=None),
    ):
        resp = admin_client.post("/api/reporting/run", json={"source": "x"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sql"] == fake_sql            # raw untouched
    assert "sqlPretty" in body
    assert "\n" in body["sqlPretty"]          # actually formatted
    assert body["sqlPretty"].count("?") == 2  # placeholders preserved
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/integration/test_reporting_routes.py -k "pretty_sql" -v
```
Expected: FAIL — AssertionError on `'sqlPretty' in body`.

- [ ] **Step 3: Implement.** In `nx_lib/views/reporting.py`:

  (a) All reporting imports in this file are **relative**. In the `..reporting.*` import block, insert the new import between the `sources` and `table_query` blocks (alphabetical: `sources` < `sqlformat` < `table_query`) — the block currently reads:

```python
from ..reporting.sources import (
```
  …
```python
from ..reporting.table_query import (
```

  insert between them:

```python
from ..reporting.sqlformat import format_sql
```

  (b) In `api_run`, the payload dict currently contains:

```python
        "sql": sql,
        "params": [_json_safe(p) for p in params],
```

  replace with:

```python
        "sql": sql,
        "sqlPretty": format_sql(sql),
        "params": [_json_safe(p) for p in params],
```

  (Note: `"sql": sql,` also appears in the AI-agent response near the bottom of the file — edit the **api_run** occurrence, the one followed by the `"params"` line shown above.)

- [ ] **Step 4: Run the file green (both sql-echo tests + neighbours)**

```powershell
python -m pytest tests/integration/test_reporting_routes.py -v
```
Expected: all PASS (including the pre-existing `test_run_response_includes_sql_and_params` — the raw `sql` is untouched).

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/views/reporting.py tests/integration/test_reporting_routes.py
git commit -m "feat(reporting): echo display-formatted SQL (sqlPretty) from /run" -m "New additive response field next to the raw sql echo. Raw sql stays byte-exact for the Copy button and exports; sqlPretty is best-effort via format_sql()."
```

---

# PHASE 2 — Client-side highlighter + Show-query display upgrade

### Task 3: `ReportingSqlFormat` shared partial + token CSS

**Files:**
- Create: `templates/js/_reporting_sqlformat_js.html`
- Modify: `templates/reporting.html` (include the partial)
- Modify: `static/css/reporting.css` (token colors, appended)
- Test: `tests/e2e/test_reporting_simple.py` (pure-function tests via `page.evaluate`)

- [ ] **Step 1: Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_sqlformat_escapes_and_highlights(nexora_server, page):
    """ReportingSqlFormat.toHtml escapes every emitted piece (no raw HTML can
    reach innerHTML) and wraps tokens in classed spans."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    html = page.evaluate(
        "() => ReportingSqlFormat.toHtml(\"SELECT [a] FROM t WHERE x = '<script>' -- note\")"
    )
    assert "<script>" not in html                       # escaped, not injected
    assert "&lt;script&gt;" in html
    assert '<span class="sql-kw">SELECT</span>' in html
    assert '<span class="sql-ident">[a]</span>' in html
    assert '<span class="sql-comment">-- note</span>' in html
    assert '<span class="sql-string">' in html


def test_sqlformat_marks_placeholders_and_numbers(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    html = page.evaluate(
        "() => ReportingSqlFormat.toHtml('SELECT TOP 100 * FROM t WHERE a >= ? AND b < ?')"
    )
    assert html.count('<span class="sql-param">?</span>') == 2
    assert '<span class="sql-number">100</span>' in html
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -k "sqlformat" -v
```
Expected: FAIL — `ReportingSqlFormat is not defined` (evaluate error).

- [ ] **Step 3: Create `templates/js/_reporting_sqlformat_js.html`:**

```html
<script>
/* Shared SQL display helper: escape + token-highlight a T-SQL string into a
   <pre>. Display-only — the raw string stays authoritative for the Copy
   buttons. Used by the Simple and Advanced Show-query panels and the AI
   Write-SQL draft. Exposed on window so page.evaluate e2e tests reach it. */
window.ReportingSqlFormat = (function () {
  'use strict';
  var KEYWORDS = {};
  ('SELECT FROM WHERE GROUP BY ORDER HAVING UNION ALL JOIN INNER LEFT RIGHT ' +
   'FULL OUTER CROSS APPLY ON AS AND OR NOT NULL IS IN EXISTS LIKE BETWEEN ' +
   'CASE WHEN THEN ELSE END TOP DISTINCT COUNT SUM AVG MIN MAX CAST CONVERT ' +
   'COALESCE OVER PARTITION WITH OFFSET FETCH NEXT ROWS ONLY ASC DESC ' +
   'DATEADD DATEDIFF GETDATE IIF')
    .split(' ').forEach(function (k) { KEYWORDS[k] = 1; });

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* Tokenize the RAW sql and escape each piece as it is emitted, so no
     unescaped input ever reaches innerHTML. Alternatives, in order:
     comment | 'string' ('' escapes) | [bracketed ident] | number | ? | word */
  function toHtml(sql) {
    sql = String(sql == null ? '' : sql);
    var re = /(--[^\n]*)|('(?:[^']|'')*')|(\[[^\]]*\])|((?:\d+\.\d+|\d+)(?!\w))|(\?)|([A-Za-z_][A-Za-z0-9_]*)/g;
    var out = '', last = 0, m;
    while ((m = re.exec(sql)) !== null) {
      out += esc(sql.slice(last, m.index));
      if (m[1]) out += '<span class="sql-comment">' + esc(m[1]) + '</span>';
      else if (m[2]) out += '<span class="sql-string">' + esc(m[2]) + '</span>';
      else if (m[3]) out += '<span class="sql-ident">' + esc(m[3]) + '</span>';
      else if (m[4]) out += '<span class="sql-number">' + esc(m[4]) + '</span>';
      else if (m[5]) out += '<span class="sql-param">' + esc(m[5]) + '</span>';
      else out += KEYWORDS[m[6].toUpperCase()]
        ? '<span class="sql-kw">' + esc(m[6]) + '</span>'
        : esc(m[6]);
      last = re.lastIndex;
    }
    out += esc(sql.slice(last));
    return out;
  }

  function render(preEl, sql) {
    if (!preEl) return;
    preEl.innerHTML = toHtml(sql);
  }

  return { toHtml: toHtml, render: render };
})();
</script>
```

- [ ] **Step 4: Include the partial.** In `templates/reporting.html`, find:

```jinja
    {% include '_reporting_simple.html' %}
```

  and add the new include on the line **before** it (the Simple pane's IIFE is included inside `_reporting_simple.html`, so the helper must already exist):

```jinja
    {% include 'js/_reporting_sqlformat_js.html' %}
    {% include '_reporting_simple.html' %}
```

- [ ] **Step 5: Token CSS.** Append at the end of `static/css/reporting.css` (GitHub-light palette matching the existing pre backgrounds; `#rsSqlText`/`#rpSqlText` are `<pre>` elements inside `.reporting-sqlview`, the AI draft pre carries `.reporting-ai-sql`):

```css
/* SQL token highlighting (Show-query panels + AI SQL draft) */
.reporting-sqlview pre .sql-kw, .reporting-ai-sql .sql-kw { color: #cf222e; font-weight: 600; }
.reporting-sqlview pre .sql-string, .reporting-ai-sql .sql-string { color: #0a3069; }
.reporting-sqlview pre .sql-number, .reporting-ai-sql .sql-number { color: #0550ae; }
.reporting-sqlview pre .sql-ident, .reporting-ai-sql .sql-ident { color: #953800; }
.reporting-sqlview pre .sql-param, .reporting-ai-sql .sql-param { color: #8250df; font-weight: 600; }
.reporting-sqlview pre .sql-comment, .reporting-ai-sql .sql-comment { color: #6e7781; font-style: italic; }
```

- [ ] **Step 6: Run green** (the e2e fixture spawns its own fresh server — no manual restart needed)

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "sqlformat" -v
```
Expected: 2 passed.

- [ ] **Step 7: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/js/_reporting_sqlformat_js.html templates/reporting.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): client-side SQL token highlighter partial" -m "window.ReportingSqlFormat: escape-as-you-emit tokenizer (keywords, strings, bracketed idents, numbers, ? placeholders, comments) into classed spans. No CDN library — CSP/SRI and no-vendored-JS conventions hold."
```

---

### Task 4: Wire pretty + highlighted SQL into all three display surfaces

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`runCurrent`, `rsShowSql` listener)
- Modify: `templates/js/_reporting_js.html` (`renderResults`, `rpShowSql` listener)
- Modify: `templates/js/_reporting_ai_js.html` (`askSql` result display)
- Test: `tests/e2e/test_reporting_simple.py` (extend `test_show_query_reveals_sql`)

- [ ] **Step 1: Extend the existing e2e test (failing first).** In `tests/e2e/test_reporting_simple.py::test_show_query_reveals_sql`, replace the assertion block:

```python
        show = page.get_by_test_id("rs-show-sql")
        expect(show).to_be_visible()
        show.click()
        expect(page.get_by_test_id("rs-sql-view")).to_be_visible()
        expect(page.locator("#rsSqlText")).to_contain_text("SELECT")
```

  with:

```python
        show = page.get_by_test_id("rs-show-sql")
        expect(show).to_be_visible()
        # Collapsed by default: the panel is hidden until the user expands it.
        sql_view = page.get_by_test_id("rs-sql-view")
        expect(sql_view).to_be_hidden()
        show.click()
        expect(sql_view).to_be_visible()
        expect(page.locator("#rsSqlText")).to_contain_text("SELECT")
        # Pretty-printed (multi-line) and token-highlighted.
        assert "\n" in page.locator("#rsSqlText").inner_text()
        assert page.locator("#rsSqlText span.sql-kw").count() > 0
        # Second click re-collapses.
        show.click()
        expect(sql_view).to_be_hidden()
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "show_query_reveals" -v
```
Expected: FAIL on `assert "\n" in ...` (SQL is still the raw single-line dump).

- [ ] **Step 3: Simple pane.** In `templates/js/_reporting_simple_js.html`:

  (a) in `runCurrent`, find:

```js
    state.current.sql = res.data.sql || null;
    state.current.params = res.data.params || [];
```

  and replace with:

```js
    state.current.sql = res.data.sql || null;
    state.current.sqlPretty = res.data.sqlPretty || null;
    state.current.params = res.data.params || [];
```

  (b) in the `rsShowSql` click listener, find:

```js
    if (!view.hidden) {
      el('rsSqlText').textContent = cur.sql;
```

  and replace with:

```js
    if (!view.hidden) {
      ReportingSqlFormat.render(el('rsSqlText'), cur.sqlPretty || cur.sql);
```

  Leave the `rsSqlParams` line and the `rsSqlCopy` listener (raw `cur.sql`) untouched.

- [ ] **Step 4: Advanced pane.** In `templates/js/_reporting_js.html`:

  (a) in `renderResults`, find:

```js
    state._lastSql = data.sql || null;
    state._lastParams = data.params || [];
```

  and replace with:

```js
    state._lastSql = data.sql || null;
    state._lastSqlPretty = data.sqlPretty || null;
    state._lastParams = data.params || [];
```

  (b) in the `rpShowSql` listener, find:

```js
      if (!view.hidden) {
        document.getElementById('rpSqlText').textContent = state._lastSql;
```

  and replace with:

```js
      if (!view.hidden) {
        ReportingSqlFormat.render(document.getElementById('rpSqlText'),
          state._lastSqlPretty || state._lastSql);
```

  Leave `rpSqlViewCopy` (raw `state._lastSql`) untouched.

- [ ] **Step 5: AI Write-SQL draft.** In `templates/js/_reporting_ai_js.html`, inside `askSql`, find:

```js
      lastSql = res.data.sql || "";
      sqlEl.textContent = lastSql;
```

  and replace with:

```js
      lastSql = res.data.sql || "";
      ReportingSqlFormat.render(sqlEl, lastSql);
```

  (`lastSql` stays raw — the Insert-into-editor and Copy buttons keep using it. Task 7 later rewrites `askSql` wholesale; its replacement code already includes this line in its new form.)

- [ ] **Step 6: Run green**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "show_query_reveals or sqlformat" -v
```
Expected: 3 passed.

- [ ] **Step 7: Browser sanity pass** — restart the dev server first (Jinja caches templates for the process lifetime): `nx -u -b --loginas:<admin user>`, Simple tab → run a wizard report → Show query → confirm multi-line colored SQL, params line intact, Copy still yields the raw single-line statement. Screenshot to `var/screenshots/reporting_sqlview_pretty.png`. (Remote session: send via SendUserFile.)

- [ ] **Step 8: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/js/_reporting_simple_js.html templates/js/_reporting_js.html templates/js/_reporting_ai_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): pretty + highlighted SQL in Show-query panels" -m "Both tabs render sqlPretty (fallback raw) through ReportingSqlFormat; the AI Write-SQL draft is highlighted client-side. Copy buttons keep copying the raw executed SQL. Panel stays collapsed by default (now pinned by e2e)."
```

---

# PHASE 3 — Loading states

### Task 5: Simple tab — in-flight indicator for report runs

**Files:**
- Modify: `templates/_reporting_simple.html` (new `#rsRunLoading` block)
- Modify: `templates/js/_reporting_simple_js.html` (`runCurrent`, `showAiLoading`, `showResultError`)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py` (seeding copied from `test_show_query_reveals_sql`, distinct codes; latch idiom from `test_ai_ask_shows_loading_then_result`):

```python
def test_run_shows_loading_then_result(nexora_server, page):
    """The pulsing run indicator appears while /api/reporting/run is in flight
    and is hidden once the result cards render. Localhost runs are fast, so
    visibility is latched with a MutationObserver (same idiom as the AI test)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_runload', kind: 'curated', label: 'Run Load Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 19});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_runload_count', sourceId: 'wiz_runload', label: 'Run load count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.evaluate("""() => {
            window.__runLoadingWasSeen = false;
            const el = document.getElementById('rsRunLoading');
            if (!el) return;
            if (!el.hidden) { window.__runLoadingWasSeen = true; return; }
            const obs = new MutationObserver(() => {
                if (!el.hidden) {
                    window.__runLoadingWasSeen = true;
                    obs.disconnect();
                }
            });
            obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
        }""")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Run load count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        # rs-show-sql appears only after the MAIN run response is processed,
        # which is strictly after the indicator is hidden.
        expect(page.get_by_test_id("rs-show-sql")).to_be_visible()
        expect(page.get_by_test_id("rs-run-loading")).to_be_hidden()
        expect(page.get_by_test_id("rs-stat-card")).to_be_visible()
        assert page.evaluate("() => window.__runLoadingWasSeen"), \
            "rsRunLoading never became visible during the report run"
        page.screenshot(path="var/screenshots/reporting_simple_run_loading.png")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "run_shows_loading" -v
```
Expected: FAIL — `rsRunLoading never became visible` (element doesn't exist yet, latch stays False).

- [ ] **Step 3: Markup.** In `templates/_reporting_simple.html`, the AI block ends with:

```html
    </div>
    {% endif %}
    <p id="rsMsg" class="reporting-ai-explain" hidden data-testid="rs-msg"></p>
```

  Insert the run indicator between the `{% endif %}` and the `rsMsg` line (it must live **outside** the `{% if ai_enabled %}` guard so runs get feedback even without AI):

```html
    </div>
    {% endif %}
    <div id="rsRunLoading" class="reporting-ai-loading" hidden data-testid="rs-run-loading">
      <span class="reporting-ai-dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span role="status">{{ _("Running your report…") }}</span>
    </div>
    <p id="rsMsg" class="reporting-ai-explain" hidden data-testid="rs-msg"></p>
```

  (Reuses the existing `.reporting-ai-loading` / `.reporting-ai-dots` CSS — including its `prefers-reduced-motion` guard — so zero new CSS.)

- [ ] **Step 4: Show/hide wiring.** In `templates/js/_reporting_simple_js.html`:

  (a) In `runCurrent`, find the card-hiding block that ends just before `var def = cur.def;` (NOT the similar block in `showAiLoading`):

```js
    el('rsSaveName').hidden = true;
    el('rsStatCard').hidden = true;
    el('rsChartCard').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;

    var def = cur.def;
```

  and replace with:

```js
    el('rsSaveName').hidden = true;
    el('rsStatCard').hidden = true;
    el('rsChartCard').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
    el('rsRunLoading').hidden = false;

    var def = cur.def;
```

  (b) Still in `runCurrent`, find the **main-run** response handling (the second `seq !== runSeq` guard — the one followed by the `!res.ok` check; the first guard after the grand-total run uses `var t = ...` and stays untouched):

```js
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) });
    if (seq !== runSeq) return;
    if (!res.ok) { showResultError(friendlyRunError(res.status, res.data)); return; }
```

  and replace with:

```js
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) });
    if (seq !== runSeq) return;
    // Hide only after the staleness guard: a slow stale response must never
    // hide the indicator a newer run just showed.
    el('rsRunLoading').hidden = true;
    if (!res.ok) { showResultError(friendlyRunError(res.status, res.data)); return; }
```

  (The indicator deliberately stays visible across the grand-total POST that precedes this one — one indicator spans the whole run, no flicker. The chart mount that follows is synchronous, so hiding here covers "chart render" too.)

  (c) In `showResultError`, find:

```js
  function showResultError(msg) {
    hideAiLoading();
```

  and replace with:

```js
  function showResultError(msg) {
    hideAiLoading();
    el('rsRunLoading').hidden = true;
```

  (d) In `showAiLoading`, find its card-hiding block (the one followed by `var lines = ...`):

```js
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
    var lines = [I18N.aiThinking, I18N.aiDrafting, I18N.aiChecking];
```

  and replace with:

```js
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
    el('rsRunLoading').hidden = true;
    var lines = [I18N.aiThinking, I18N.aiDrafting, I18N.aiChecking];
```

  (So a stale run's indicator can never sit under the AI dots; conversely the AI flow chains into `runCurrent()` on success, which then shows the run indicator — continuous feedback from ask to rendered result.)

- [ ] **Step 5: Run green (new test + the pre-existing AI loading test guards the `showAiLoading` edit)**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "run_shows_loading or ai_ask_shows_loading" -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): in-flight indicator for Simple report runs" -m "New always-present rsRunLoading dots block (outside the ai_enabled guard) shown for the whole runCurrent window (both sequential /run POSTs plus the synchronous chart mount). Hidden only behind the runSeq staleness guard and in showResultError/showAiLoading."
```

---

### Task 6: Advanced tab — in-flight indicator + Run lock

**Files:**
- Modify: `templates/js/_reporting_js.html` (`run`, `runSql`, new helpers, I18N const)
- Test: `tests/e2e/test_reporting_sql.py`

- [ ] **Step 1: Write the failing e2e test.** Append to `tests/e2e/test_reporting_sql.py` (this file's `_login` already navigates to `?tab=advanced`; the file convention marks tests `flaky_e2e`):

```python
@pytest.mark.flaky_e2e
def test_sql_run_shows_loading_indicator(nexora_server, page):
    """Run injects the pulsing indicator into the results area while the query
    is in flight; the response (a 503 error here — no Statistics DB in TEST)
    replaces it, and Run is re-enabled. The injected node is latched via the
    MutationObserver addedNodes records, immune to fast replacement."""
    _login(page, nexora_server)
    # Pre-acknowledge via API so Run fires the fetch immediately (no modal in
    # the way), then reload so the page bootstraps with acknowledged=true.
    page.evaluate("""() => fetch('/api/reporting/sql/ack', {
        method: 'POST',
        headers: {'Content-Type': 'application/json',
                  'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
        body: '{}'
    })""")
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.locator('[data-testid="reporting-mode-sql"]').click()
    editor = page.locator('[data-testid="reporting-sql-editor"]')
    expect(editor).to_be_visible()
    editor.fill("SELECT 1 AS one")
    page.evaluate("""() => {
        window.__runLoadingWasSeen = false;
        const wrap = document.getElementById('rpResults');
        const obs = new MutationObserver((muts) => {
            for (const m of muts) {
                for (const n of m.addedNodes) {
                    if (n.nodeType === 1 && n.getAttribute &&
                        n.getAttribute('data-testid') === 'reporting-run-loading') {
                        window.__runLoadingWasSeen = true;
                        obs.disconnect();
                        return;
                    }
                }
            }
        });
        obs.observe(wrap, { childList: true });
    }""")
    run_btn = page.locator('[data-testid="reporting-run"]')
    run_btn.click()
    # 503 from the unconfigured sandbox -> error paragraph replaces the loader.
    expect(page.locator("#rpResults .reporting-error")).to_be_visible()
    expect(run_btn).to_be_enabled()
    assert page.evaluate("() => window.__runLoadingWasSeen"), \
        "the run-loading node was never injected into rpResults"
    page.screenshot(path="var/screenshots/reporting_advanced_run_loading.png")
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/e2e/test_reporting_sql.py -k "loading_indicator" -v
```
Expected: FAIL — latch stays False (no loading node is injected yet).

- [ ] **Step 3: Implement.** In `templates/js/_reporting_js.html`:

  (a) Find the I18N consts:

```js
  var I18N_SHOW_QUERY = {{ _("Show query")|tojson }};
```

  and add above it:

```js
  var I18N_RUNNING = {{ _("Running your report…")|tojson }};
```

  (Same msgid as the Simple markup string — one translation covers both panes.)

  (b) Add the helpers directly after the existing `showError` function, which reads:

```js
  function showError(msg) {
    var wrap = document.getElementById('rpResults');
    wrap.innerHTML = '';
    var p = document.createElement('p');
    p.className = 'reporting-error';
    p.textContent = msg;
    wrap.appendChild(p);
  }
```

  add below it:

```js
  // In-flight indicator for report runs. Lives inside #rpResults so the
  // renderResults/showError innerHTML swap self-cleans it. The view is forced
  // to grid because #rpResults is hidden whenever state.view !== 'grid' —
  // without this, a re-run from Chart/Pivot would show nothing. Run is
  // disabled so a double-click can't fire two parallel requests (rpRun is the
  // only run trigger on this tab). DOM-built so the translated label needs no
  // escaping. The Motion observer ignores non-TABLE/.reporting-empty/
  // .reporting-error nodes, so this block is animation-inert.
  function showRunLoading() {
    document.getElementById('rpRun').disabled = true;
    document.getElementById('rpViewToggle').hidden = true;
    setView('grid');
    var wrap = document.getElementById('rpResults');
    wrap.innerHTML = '';
    var box = document.createElement('div');
    box.className = 'reporting-ai-loading';
    box.setAttribute('data-testid', 'reporting-run-loading');
    var dots = document.createElement('span');
    dots.className = 'reporting-ai-dots';
    dots.setAttribute('aria-hidden', 'true');
    dots.innerHTML = '<i></i><i></i><i></i>';
    var label = document.createElement('span');
    label.setAttribute('role', 'status');
    label.textContent = I18N_RUNNING;
    box.appendChild(dots);
    box.appendChild(label);
    wrap.appendChild(box);
  }
  function endRunLoading() {
    document.getElementById('rpRun').disabled = false;
  }
```

  (c) Replace `run()` — find:

```js
  function run() {
    return api('/api/reporting/run', { method: 'POST', body: JSON.stringify(buildDefinition()) })
      .then(function (res) { return res.json(); })
      .then(function (data) { renderResults(data); })
      .catch(function (e) {
        var wrap = document.getElementById('rpResults');
        wrap.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'reporting-error';
        p.textContent = e.message;
        wrap.appendChild(p);
      });
  }
```

  and replace with (the inline error builder was a verbatim duplicate of `showError` — fold it in):

```js
  function run() {
    showRunLoading();
    return api('/api/reporting/run', { method: 'POST', body: JSON.stringify(buildDefinition()) })
      .then(function (res) { return res.json(); })
      .then(function (data) { endRunLoading(); renderResults(data); })
      .catch(function (e) { endRunLoading(); showError(e.message); });
  }
```

  (d) Replace `runSql()` — find:

```js
  function runSql() {
    ackThen(function () {
      api('/api/reporting/sql/run', { method: 'POST', body: JSON.stringify(sqlBody()) })
        .then(function (res) { return res.json(); })
        .then(function (data) { renderResults(data); })
        .catch(function (e) { showError(e.message); });
    });
  }
```

  and replace with (busy starts only AFTER the user accepts the ack modal):

```js
  function runSql() {
    ackThen(function () {
      showRunLoading();
      api('/api/reporting/sql/run', { method: 'POST', body: JSON.stringify(sqlBody()) })
        .then(function (res) { return res.json(); })
        .then(function (data) { endRunLoading(); renderResults(data); })
        .catch(function (e) { endRunLoading(); showError(e.message); });
    });
  }
```

- [ ] **Step 4: Run green (new test + the existing sandbox smoke proves the ack modal still appears before any busy state)**

```powershell
python -m pytest tests/e2e/test_reporting_sql.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/js/_reporting_js.html tests/e2e/test_reporting_sql.py
git commit -m "feat(reporting): in-flight indicator and Run lock on Advanced runs" -m "showRunLoading injects the dots block into rpResults (self-cleaned by the renderResults/showError innerHTML swap), forces grid view so the indicator is visible when re-running from Chart/Pivot, and disables rpRun until the response lands. SQL-sandbox busy starts only after the ack modal is accepted. run()'s duplicate inline error builder folded into showError."
```

---

### Task 7: Advanced AI panel — loading indicator for all three surfaces

**Files:**
- Modify: `templates/reporting.html` (`#rpAiLoading` block inside `rpAiPanel`)
- Modify: `templates/js/_reporting_ai_js.html` (helpers + full rewrites of `askBuild`/`askSql`/`askAgent`)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py` (reuses the file's `_stub_ai_build` helper, which routes `**/api/reporting/ai/build` — the same endpoint the Advanced Build surface calls; the AI panel's default surface is `build`; `ai_enabled` is on in TEST):

```python
def test_advanced_ai_ask_shows_loading(nexora_server, page):
    """The Advanced AI panel shows the pulsing indicator while a request is in
    flight and hides it when the draft arrives (today it only disables Ask)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-mode-ai").click()
    page.evaluate("""() => {
        window.__aiPanelLoadingWasSeen = false;
        const el = document.getElementById('rpAiLoading');
        if (!el) return;
        if (!el.hidden) { window.__aiPanelLoadingWasSeen = true; return; }
        const obs = new MutationObserver(() => {
            if (!el.hidden) {
                window.__aiPanelLoadingWasSeen = true;
                obs.disconnect();
            }
        });
        obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
    }""")
    _stub_ai_build(page, delay_s=0.8)
    page.get_by_test_id("reporting-ai-prompt").fill("docs by process")
    page.get_by_test_id("reporting-ai-ask").click()
    expect(page.get_by_test_id("reporting-ai-def-result")).to_be_visible()
    expect(page.get_by_test_id("reporting-ai-loading")).to_be_hidden()
    assert page.evaluate("() => window.__aiPanelLoadingWasSeen"), \
        "rpAiLoading never became visible during the AI request"
    page.screenshot(path="var/screenshots/reporting_advanced_ai_loading.png")
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "advanced_ai_ask" -v
```
Expected: FAIL — latch stays False (`rpAiLoading` doesn't exist).

- [ ] **Step 3: Markup.** In `templates/reporting.html`, inside `rpAiPanel`, find:

```html
        <div id="rpAiResult" class="reporting-ai-result" hidden data-testid="reporting-ai-result">
```

  and insert the loading block on the lines **before** it (after the three hint `<p>`s):

```html
        <div id="rpAiLoading" class="reporting-ai-loading" hidden data-testid="reporting-ai-loading">
          <span class="reporting-ai-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span id="rpAiLoadingText" role="status"></span>
        </div>
        <div id="rpAiResult" class="reporting-ai-result" hidden data-testid="reporting-ai-result">
```

- [ ] **Step 4: Helpers.** In `templates/js/_reporting_ai_js.html`, find the agent state declarations:

```js
  var lastAgentDef = null;
  var lastAgentSql = "";
```

  and add below them:

```js
  // In-flight indicator shared by all three surfaces. Rotating lines mirror
  // the Simple pane's component; the agent surface gets a "takes a minute"
  // line since agent runs are the longest waits. tojson handles quoting.
  var aiLoadingEl = document.getElementById("rpAiLoading");
  var aiLoadingTextEl = document.getElementById("rpAiLoadingText");
  var aiLoadingTimer = null;
  var AI_LINES = [
    {{ _("Asking the AI…")|tojson }},
    {{ _("Drafting your report…")|tojson }},
    {{ _("Checking the result…")|tojson }}
  ];
  var AGENT_LINES = [
    {{ _("Asking the AI…")|tojson }},
    {{ _("The agent is working step by step — this can take a minute…")|tojson }},
    {{ _("Checking the result…")|tojson }}
  ];

  function showAiLoading(lines) {
    if (!aiLoadingEl) return;
    var i = 0;
    aiLoadingTextEl.textContent = lines[0];
    aiLoadingEl.hidden = false;
    if (aiLoadingTimer) clearInterval(aiLoadingTimer);
    aiLoadingTimer = setInterval(function () {
      i = (i + 1) % lines.length;
      aiLoadingTextEl.textContent = lines[i];
    }, 3000);
  }
  function hideAiLoading() {
    if (aiLoadingTimer) { clearInterval(aiLoadingTimer); aiLoadingTimer = null; }
    if (aiLoadingEl) aiLoadingEl.hidden = true;
  }
```

  (The three `AI_LINES` msgids already exist translated — they are the Simple pane's rotating lines. Only the agent line is new.)

- [ ] **Step 5: Rewrite the three ask functions.** The `}).then(function (res) { askBtn.disabled = false; if (!res.ok) {` openers and the catch bodies are **not unique across the three functions**, so replace each function wholesale (verified verbatim against the worktree; the only additions are the three `showAiLoading`/`hideAiLoading` calls per function — and `askSql` carries the `ReportingSqlFormat.render` line Task 4 introduced).

  `askBuild` — full replacement:

```js
  function askBuild(question) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    showAiLoading(AI_LINES);
    fetch("/api/reporting/ai/build", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ question: question })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      hideAiLoading();
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || '{{ _("Error") }}';
        errorEl.hidden = false; defResult.hidden = true; return;
      }
      lastDef = res.data.definition;
      defSummary.textContent = lastDef ? summarize(lastDef) : (res.data.explanation || "");
      defInvalid.hidden = res.data.valid !== false;
      openBuilderBtn.disabled = !lastDef || res.data.valid === false;
      defResult.hidden = false;
      if (makeChartBtn) makeChartBtn.hidden = !(lastDef && lastDef.chartHint && res.data.valid !== false);
    }).catch(function () {
      askBtn.disabled = false;
      hideAiLoading();
      errorEl.textContent = '{{ _("Network error") }}'; errorEl.hidden = false;
    });
  }
```

  `askSql` — full replacement:

```js
  function askSql(question) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    showAiLoading(AI_LINES);
    fetch("/api/reporting/ai/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ question: question })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      hideAiLoading();
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || '{{ _("Error") }}';
        errorEl.hidden = false;
        resultEl.hidden = true;
        return;
      }
      lastSql = res.data.sql || "";
      ReportingSqlFormat.render(sqlEl, lastSql);
      explainEl.textContent = res.data.explanation || "";
      invalidEl.hidden = res.data.valid !== false;
      resultEl.hidden = false;
    }).catch(function () {
      askBtn.disabled = false;
      hideAiLoading();
      errorEl.textContent = '{{ _("Network error") }}';
      errorEl.hidden = false;
    });
  }
```

  `askAgent` — full replacement (uses `AGENT_LINES`):

```js
  function askAgent(question) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    showAiLoading(AGENT_LINES);
    fetch("/api/reporting/ai/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({
        question: agentContext() + question,
        // Active source lets the server gate run_sql to sources it can reach.
        source: (document.getElementById("rpSource") || {}).value || null
      })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      hideAiLoading();
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || '{{ _("Error") }}';
        errorEl.hidden = false; agentResult.hidden = true; return;
      }
      var d = res.data;
      agentThread.push({ q: question, a: d.answer || "" });
      renderAgentThread();
      renderAgentTrace(d.toolTrace, d.turns);
      lastAgentDef = d.definition || null;
      lastAgentSql = d.sql || "";
      if (agentOpenBuilderBtn) agentOpenBuilderBtn.hidden = !lastAgentDef;
      if (agentInsertSqlBtn) agentInsertSqlBtn.hidden = !(lastAgentSql && sqlEditor);
      if (agentInvalid)
        agentInvalid.hidden = !!(d.answer && (lastAgentDef || lastAgentSql));
      agentResult.hidden = false;
      promptEl.value = "";
      askBtn.textContent = '{{ _("Ask follow-up") }}';
    }).catch(function () {
      askBtn.disabled = false;
      hideAiLoading();
      errorEl.textContent = '{{ _("Network error") }}'; errorEl.hidden = false;
    });
  }
```

- [ ] **Step 6: Run green**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "advanced_ai_ask" -v
```
Expected: PASS.

- [ ] **Step 7: Browser sanity pass on INT** — restart first (`nx -u -b --loginas:<admin user>`), Advanced → Ask AI → each surface (Build / Write SQL / Agent): dots + rotating line while waiting, gone on result, Ask re-enabled. Screenshot mid-flight if catchable (agent runs are slow enough) to `var/screenshots/reporting_ai_loading.png`. (Remote session: send via SendUserFile.)

- [ ] **Step 8: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/reporting.html templates/js/_reporting_ai_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): loading indicator for Advanced AI surfaces" -m "rpAiLoading dots + rotating status lines for build/sql/agent asks (previously only the Ask button was disabled). Agent surface gets a 'can take a minute' line. Reuses the Simple pane's CSS component and translated line msgids."
```

---

# PHASE 4 — i18n, docs, full verification

### Task 8: i18n cycle (two new msgids)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

New msgids introduced by this plan (everything else reuses existing translations — `Asking the AI…`, `Drafting your report…`, `Checking the result…`, `Show query`, `Hide query`, `Copy`, `Copied`, `Parameters` all already exist):

1. `Running your report…` (Simple markup, Task 5; Advanced JS, Task 6)
2. `The agent is working step by step — this can take a minute…` (Task 7)

- [ ] **Step 1: Extract + update**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```
Expected: `messages.pot` gains exactly the two msgids above; the reused AI lines are untouched.

- [ ] **Step 2: Translate both msgids** in `translations/{de,fr,it}/LC_MESSAGES/messages.po` (also sweep `git diff translations` for any `#, fuzzy` markers pybabel introduced near similar strings — resolve and remove the fuzzy flag):

| msgid | de | fr | it |
|---|---|---|---|
| Running your report… | Ihr Bericht wird ausgeführt… | Exécution de votre rapport… | Esecuzione del report in corso… |
| The agent is working step by step — this can take a minute… | Der Agent arbeitet Schritt für Schritt — das kann eine Minute dauern… | L'agent travaille étape par étape — cela peut prendre une minute… | L'agente lavora passo dopo passo — può richiedere un minuto… |

- [ ] **Step 3: Compile + verify**

```powershell
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: all PASS (pot in sync, de/fr/it complete and non-fuzzy).

- [ ] **Step 4: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add messages.pot translations
git commit -m "chore(i18n): translate reporting loading-state strings (de/fr/it)" -m "Two new msgids: the run indicator label and the agent-surface waiting line. AI rotating lines reuse existing translated msgids."
```

---

### Task 9: Docs, changelog, full verification

**Files:**
- Modify: `docs/howto/reporting.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the Show-query sentence.** In `docs/howto/reporting.md`, find (verbatim — the continuation line is indented 4 spaces):

```markdown
A **Show query** toggle reveals the executed SQL and bind
    parameters (visible to anyone who can run reports, with a Copy button).
```

  and replace with (same 4-space continuation indent):

```markdown
A **Show query** toggle (collapsed by default,
    re-collapsed on every run) reveals the executed SQL — pretty-printed server-side
    (sqlglot) and syntax-highlighted — plus its bind parameters (visible to anyone who
    can run reports; the Copy button copies the raw executed statement). While a report
    runs, both tabs show a pulsing in-flight indicator (the Advanced **Run** button locks
    until the response lands), and the Advanced Ask-AI surfaces show the same indicator
    with rotating status lines.
```

- [ ] **Step 2: Changelog.** In `CHANGELOG.md` under `## [Unreleased]` → `### Added`, the existing entry:

```markdown
- Reporting: "Show query" on Simple and Advanced results — reveals the executed SQL and bind parameters, with copy.
```

  becomes (2.5.63 is unshipped — refinements of an unreleased feature fold into its Added entry rather than a Changed section):

```markdown
- Reporting: "Show query" on Simple and Advanced results — reveals the executed SQL (pretty-printed server-side via sqlglot, syntax-highlighted, collapsed by default) and bind parameters; Copy copies the raw executed statement.
- Reporting: in-flight loading indicators — Simple and Advanced report runs show a pulsing status (the Advanced Run button locks while running), and all three Advanced Ask-AI surfaces show a thinking indicator with rotating status lines.
```

- [ ] **Step 3: Full test suite**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/unit tests/integration -q
python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting.py tests/e2e/test_reporting_sql.py -v
```
Expected: all PASS (including the new unit/integration files and the five new/extended e2e tests). If the e2e server fixture fails to bind, kill stale port-8765 listeners first: `Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | % { Stop-Process -Id $_.OwningProcess -Force }`.

- [ ] **Step 4: Browser pass + screenshots (remote session: send each via SendUserFile as you go).** Restart the dev server (`nx -u -b --loginas:<admin user>`), then walk: Simple wizard run → dots → result cards; Show query → collapsed → expand → colored multi-line SQL → re-collapse; Advanced curated run (incl. a re-run from Chart view — the indicator must appear) → dots in results pane + Run locked; Advanced SQL-sandbox run (ack once) → dots → result/error; Ask AI on each surface → dots + rotating line. The e2e run also produced review artifacts to send:
  - `var/screenshots/reporting_simple_run_loading.png`
  - `var/screenshots/reporting_advanced_run_loading.png`
  - `var/screenshots/reporting_advanced_ai_loading.png`
  - `var/screenshots/reporting_sqlview_pretty.png` (from Task 4 Step 7)

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add docs/howto/reporting.md CHANGELOG.md
git commit -m "docs(reporting): loading states and formatted SQL display" -m "Show-query doc updated for pretty-printed/highlighted SQL, raw-copy semantics and the in-flight indicators; changelog entries under [Unreleased] Added."
```

- [ ] **Step 6: STOP at commit.** Do not push, do not open a PR (remote-session policy — the owner reviews locally; the pre-push hook runs the full suite then). Leave the worktree branch ready for the owner to merge into `feature/2.5.63`; note in the handoff that the drill-through plan (Tasks 2–8) executes next and must re-verify its quoted anchors against this plan's edits to `runCurrent`, `run()`/`renderResults`, `askBuild`/`askSql`/`askAgent`, and the result-area markup.

---

## Gotchas & notes

- **Jinja template cache:** every edit to `templates/**` needs a dev-server restart **before manual browser checks**. The pytest e2e fixture spawns its own fresh server per session, so test runs are unaffected.
- **`SQL_SYNC_SKIP=1` on every commit:** the INT SchemaMigrations CRLF-checksum drift fails the `sql-migrate-int` pre-commit hook on Windows even for SQL-free commits. Never `--no-verify`.
- **ruff-format / hook double-commit dance:** if the first `git commit` fails because a hook rewrote a file (ruff-format, or `mixed-line-ending` after `pybabel extract` writes CRLF), `git add -u` and run the identical commit command again.
- **sqlglot normalizes tokens** (`TOP (5000)` → `TOP 5000`, `) t` → `) AS t`): never assert byte-equality between `sql` and `sqlPretty`, and never feed `sqlPretty` to anything that executes or copies "the executed SQL".
- **The highlighter must escape as it emits** (tokenize raw → escape each piece). Escaping first then tokenizing breaks the string-literal regex (`'` becomes `&#39;`); highlighting unescaped HTML is XSS (filter values can carry user-derived text).
- **Two identical card-hiding blocks** exist in `_reporting_simple_js.html` (one in `showAiLoading`, one in `runCurrent`). Anchor on the *following* line (`var lines = ...` vs `var def = cur.def;`) to disambiguate — the snippets in Task 5 include them.
- **Two `if (seq !== runSeq) return;` guards** exist in `runCurrent` (after the grand-total run and after the main run). The hide-loading line goes after the **second** one; a stale slow response must never hide a newer run's indicator — that is why the hide sits after the guard and why `showResultError` (every error path's funnel) also hides it.
- **Don't gate `#rsRunLoading` inside `{% if ai_enabled %}`** — run loading must work with AI off; `rsAiLoading` is gated, the new element deliberately is not.
- **Advanced view state:** `#rpResults` is hidden unless `state.view === 'grid'` — `showRunLoading()` must keep its `setView('grid')` + `rpViewToggle` hide, or the indicator is invisible on every re-run from Chart/Pivot. On the error path the toggle stays hidden (no data views to toggle — consistent with `showError` leaving no grid either).
- **Motion animation layer:** the `#rpResults` MutationObserver animates only `TABLE` / `.reporting-empty` / `.reporting-error` nodes — the injected loading `div` is intentionally none of those.
- **The three ask functions share non-unique snippets** (`askBtn.disabled = false;` × 6, identical then/catch openers in `askBuild`/`askAgent`) — that is why Task 7 replaces them wholesale instead of patching lines.
- **Task ordering dependency:** Task 7's `askSql` rewrite includes the `ReportingSqlFormat.render(sqlEl, lastSql)` line that Task 4 introduced — execute the tasks in order, or reconcile manually.
- **`ackThen` ordering:** the SQL-sandbox busy state must start inside the ack callback, or the Run button locks while the modal waits for the user.
- **Transient-state e2e:** localhost responses are too fast for `expect(...).to_be_visible()` on a spinner — always use the MutationObserver latch idiom (attribute filter for `hidden` flips, `addedNodes` scan for injected nodes) plus route-stub delays for AI, as `test_ai_ask_shows_loading_then_result` does.
- **Drill-through plan collision:** after this plan lands, `run()`, `runCurrent()`, `renderResults()` and the ask functions no longer match the drill-through plan's quoted anchors verbatim — its executor must re-locate anchors, not blind-paste.
- **Stray `D env/CONFLUENCE.env.example`** in `git status` belongs to another worktree's feature — never stage, commit, or restore it here.
- **Remote session:** stop at `git commit`; screenshots of UI changes go to `var/screenshots/` and are sent via SendUserFile without being asked.
