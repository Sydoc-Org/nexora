# Reporting Flagship UI Polish - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. Multi-agent planning run (explore → dual drafts → adversarial red-team → merge); **every file path, symbol, and quoted snippet below was Grep/Read-verified against the worktree at feature/2.5.64 HEAD (`d2d7205`) on 2026-07-14** — trust the anchors, but re-Grep before editing since line numbers drift (this plan quotes code, never line numbers). Plan file: `docs/superpowers/plans/2026-07-14-reporting-flagship-ui-polish.md`.

**Goal:** The Reporting page becomes the reference page of the app, in four locked workstreams. **WS1** — the Show-query panels display (and Kopieren copies) the runnable SQL with parameter literals inlined; the grey `Parameter: 1 = '…'` footer disappears; execution stays fully parameterized. **WS2** — zero EN/DE language mixing anywhere: every user-facing string flows through the established i18n mechanisms (backend error boundary, JS fallback titles incl. `Untitled report`, filter-chip/op labels, the Beta badge), guarded by a new source lint; de/fr/it ship non-fuzzy. **WS3** — layout/visual/dark-mode polish strictly within the 2.5.63 design-system language (`static/css/reporting.css` + `--nx-*` tokens). **WS4** — smart UX: call-to-action empty states, an AI-unavailable notice instead of a silent vanish, in-page toasts instead of `window.alert`, a designed zero-row state, a real drill-drawer loader, an all-time full-scan hint, copy feedback on the AI SQL draft, app-locale number formatting.

**Architecture:** WS1 mirrors the `sqlPretty` precedent exactly: a new pure function `inline_sql_params()` beside `format_sql()` in `nx_lib/reporting/sqlformat.py` produces a third response field `sqlDisplay` in `api_run` — the raw `sql`, `sqlPretty` and `params` fields (and pyodbc execution, which stays fully parameterized) are untouched. Both tabs' twin panel handlers delegate their content policy to two new helpers on the already-shared, already-e2e-testable `window.ReportingSqlFormat` seam. WS2 translates errors at the **view boundary** (`nx_lib/views/reporting.py`) — a rule-keyed map for `SqlSandboxError` (which grows a machine-readable `token` attribute) and a translated generic + raw `detail` for definition/build errors — so the pure `nx_lib/reporting/*` modules never import Flask and their ~104 English raise-sites stay byte-identical (unit tests pin them). JS-visible strings go through the file-local `|tojson`-injected I18N conventions (babel extracts `[jinja2: **/templates/**.html]`, which covers `templates/js/`). WS3/WS4 are template/CSS/JS-partial edits that preserve every `id`, `.reporting-*` class and `data-testid` (11 e2e files select by them).

**Tech Stack:** Python 3.13 / Flask + Flask-Babel (gettext), Jinja2 JS partials under `templates/js/`, `static/css/reporting.css` on top of `static/css/nexora-ui.css` tokens, pytest unit/integration + Playwright e2e (network-stub pattern — TEST env has no Statistics DB), pybabel de/fr/it cycle.

---

## Context an engineer needs (read first)

- **Where you work:** the worktree `C:\dev\nexora\.claude\worktrees\plan-reporting-flagship-ui-polish` on branch `plan/reporting-flagship-ui-polish`, based on `feature/2.5.64` at `d2d7205`. Merged back into `feature/2.5.64` after execution. **Commit per task. Do NOT `git push` and do NOT open a PR** — the owner reviews, merges and pushes (the pre-push gate runs the FULL suite incl. Playwright e2e).
- **Python for tests:** this worktree has **no `.venv`** (verified). Run every test command from the worktree root with the main clone's interpreter: `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python — the `.venv` is test-only.
- **FIRST-COMMIT BLOCKER (verified):** the `sql-migrate-int` / `sql-sync-check` pre-commit hooks run on every commit and this worktree's `env/` has only `*.env.example`. Before the FIRST commit run `Copy-Item C:\dev\nexora\env\INT.env env\INT.env` and `Copy-Item C:\dev\nexora\env\TEST.env env\TEST.env` (gitignored, safe). Only if INT itself is unreachable, fall back to `$env:SQL_SYNC_SKIP="1"` for that one commit — **never** `--no-verify`.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Every step quotes the exact code to find; re-`Grep` it if it has moved. Several tasks edit the same files — later tasks' anchors sometimes quote code an earlier task *created*; execute in order.
- **TDD is the house rule.** Backend tasks are strict RED→GREEN. Frontend tasks write the failing Playwright test first where the behavior is assertable; CSS-only edits are verified by the untouched e2e suites plus the live browser pass (Task 13).
- **TEST env has NO Statistics DB** — the docprocessing source can never *run* in e2e. Use the established helpers in `tests/e2e/test_reporting_simple.py`: `_stub_catalogs(page)`, `_stub_ai_build(page)`, `_stub_run_ok(page, capture=…)`, and `page.route("**/api/reporting/…")` **registered before `page.goto`** (the Simple pane fetches catalogs at `rp:tabshown` on page load). For real end-to-end runs, seed a `dbo.Users`-backed source via the admin API (see `test_show_query_reveals_sql`). For transient states use the MutationObserver-latch idiom — never `expect(spinner).to_be_visible()` on localhost.
- **e2e locale is English** — JS/Jinja translations render as msgids in tests, so e2e asserts English text.
- **Jinja template cache is process-lifetime.** The e2e harness spawns a fresh server per run (fine), but restart the dev server (`nx -u -b --loginas:<user>`) before ANY manual browser check.
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` (stale NEXORA_TEST state fails order-dependent e2e tests).
- **Migrations needed: NO.** Every string in scope is UI chrome → gettext. DB-driven labels (`dbo.Search_Field_Labels`, source-registry ColumnsJSON, metrics registry) are already localized and untouched. If Task 13 surfaces a wrong/EN-only *catalog* label after all, that is a data-only migration — next free number `0038` (re-list `sql/_migrations/NexoraDB/` first; the pr119 handoff loosely reserves 0038, first taker wins), pattern `0037_reporting_processname_label.sql`. Not expected.
- **Permissions: none new. deploy.yml: no change** (only `templates/`, `static/css/`, `nx_lib/`, `translations/`, `tests/`, `docs/` are touched — all already handled).
- **i18n cycle (Task 10, run ONCE, late):** `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → hand-translate de/fr/it (remove every `#, fuzzy`) → `pybabel compile -d translations` (`.mo` files are COMMITTED; deploy mirrors `translations/`). **`tests/unit/test_translations.py` (7 collected: 1 + 2×3 locales) is expected RED from Task 2 until Task 10** — Task 2 removes the last uses of msgid `"Parameters"` (pot desync), Tasks 3–9 add/remove more. Use `pytest tests --ignore=tests/e2e --deselect tests/unit/test_translations.py` for the fast tier in between if needed; Task 12 proves the whole suite green. Precedent: the 2026-06-12 plan.
- **Which i18n mechanism applies where:** page markup → `{{ _("…") }}`; JS-visible strings → `|tojson` into the file's `I18N` object (Simple/drill) or flat `var I18N_* = {{ _("…")|tojson }};` constants (Advanced/AI) — prefer `|tojson` over inline `'{{ _("…") }}'` (apostrophe-safe, matters for French); data-derived field/measure names → DB labels, NOT gettext.
- **The visual contract (from the executed 2026-06-13 redesign plan):** NEVER rename a `.reporting-*` class; preserve every `data-testid`/`id`/`name`; `.reporting-admin*` rules are shared with `templates/reporting_sources.html` + `templates/reporting_metrics.html` — don't touch; edit `static/css/reporting.css` **in place** (a new stylesheet needs a deploy.yml exclude); `reporting.css` is unlayered, four historical append-wins layers — appended rules win; do not edit `static/css/nexora-ui.css` (app-wide); `.nx-rise*` fill-mode stays `backwards` (stacking-context trap); the light `.sql-*` token colors stay byte-identical (only dark-mode overrides are ADDED).
- **In-flight overlap:** do NOT restructure `templates/js/_reporting_drill_js.html` beyond the surgical edits in Tasks 4/8 — drill-through merged very recently and still owes the owner a live browser pass (Task 13 absorbs a spot-check). A parallel planning worktree (`plan/external-api-v1-today-stats`) may also touch `nx_lib/views/reporting.py`; whichever executes second re-verifies anchors. The dormant 2026-06-12 AI-clarifications plan touches the same JS partials — it is NOT executed and this plan must not assume its chips exist.
- **gitlint:** conventional-commit title, imperative, ≤72 chars, no trailing period; allowed types are exactly `feat,fix,chore,refactor,docs,test,ci,perf,style,build,revert` (verified in `.gitlint` — **`i18n` is NOT a type**, use `chore(i18n): …`); non-empty body wrapped ≤100 chars. Commit with `git commit -F - <<'EOF' … EOF` via the Bash tool. If `ruff-format` rewrites a file the first commit attempt fails — `git add -u` and recommit.
- **Commit trailer names the EXECUTING model.** The blocks below use `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` for the declared Sonnet executor; if a different model executes this plan, substitute its real name — never stamp a model that didn't run the work.
- **Remote-session rules:** screenshots to `var/screenshots/` (never repo root) and `SendUserFile` them proactively as you go; stop at `git commit`.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D-scope (owner) | FULL reporting polish + smart UX: Simple tab, Advanced tab, ask-AI surfaces, results/chart/table, show-query panel, drill-through chrome. | Locked via interactive Q&A. |
| D-design (owner) | Elevate WITHIN the existing design system (2.5.63 language, `reporting.css`, `--nx-*` tokens). No new visual identity. | Locked. |
| D-params (owner) | Displayed SQL inlines the parameter literals; the `Parameter: 1 = …` footer disappears; Kopieren copies the runnable inlined SQL. Execution stays parameterized. | Locked. Supersedes the 2026-06-12 plan's Decision 11 ("Copy … the raw sql + params comment"). |
| D-language (owner) | No mixed languages anywhere; every user-facing string through app i18n; de/fr/it non-fuzzy. | Locked. |
| D1 | **WS1 is server-side inlining**: pure `inline_sql_params(sql, params)` in `sqlformat.py`; `api_run` echoes `sqlDisplay = inline_sql_params(format_sql(sql), params)` as a THIRD sibling field. `sql`, `sqlPretty`, `params` and execution stay byte-identical. | Exactly how `sqlPretty` was added. Pretty-first because `test_placeholders_survive` pins that format_sql preserves every `?`; inlining plain literals afterwards cannot disturb the formatting. One implementation serves display AND copy on both tabs; unit-testable in pure Python. |
| D2 | **Inliner is best-effort with a hard fallback:** returns `None` on placeholder/param count mismatch or an un-literalizable type; the client then renders the pretty placeholder form and Copy falls back to raw SQL + the legacy `-- params:` JSON comment (param info is never lost in the degrade path). `?` inside `'…'` strings, `[brackets]` or `--` comments is never substituted. | A display feature must never lie (positional pyodbc binding) or break a run response. Same tokenization as the client highlighter. |
| D3 | **The params footer dies completely**: markup `<p id="rsSqlParams">`/`<p id="rpSqlParams">`, the JS that fills them, the `.reporting-sqlview-params` CSS rule, and (via Task 10) the `"Parameters"` msgid. | D-params. Verified: zero e2e/integration assertions reference the footer or the copy suffix. |
| D4 | **Content policy hoisted to the shared seam**: `window.ReportingSqlFormat` gains `displayText(res)` + `copyText(res)`; both tabs' handlers call them. | The two handlers are byte-identical twins today; the seam is already `page.evaluate`-tested, so ONE e2e covers BOTH tabs' policy. |
| D5 | **Backend 400s translate at the boundary, raw text moves to `detail`:** definition/build errors → translated generic + `detail`; `SqlSandboxError` → per-rule translated map (new `token` attribute carries the dynamic keyword/construct); export title fallbacks `or "Report"` → `or _("Report")`. The ~104 raise-site strings in `nx_lib/reporting/*` stay English and untouched. | Translating raise-sites would couple pure DB-free modules to Flask and break unit pins. `detail` keeps devtools debuggability without ever rendering — D-language holds. |
| D6 | **Chips show catalog label + symbol/translated op**: `=`, `≠`, `>`, `≥`, `<`, `≤` for comparisons (language-neutral), gettext words for the rest; field key resolves via the existing `fieldMetaFor()`; chips re-render once the sources catalog lands (seq-guarded). The Advanced filter-op `<select>` gets the same labels (option **values** stay raw codes — payload contract). `OP_LABELS` is duplicated per-IIFE with identical msgids (house per-pane duplication, like the palette). | `processname eq acme.inv` is the most visible EN offender. |
| D7 | **`window.alert` → in-page toast** on the Advanced tab (18 sites, all quoted below); `window.confirm()` stays native (needs a blocking answer). | The in-code comment even predicted "menu row 8 sweeps them all later"; a flagship page cannot show unstyled browser chrome. Supersedes Draft A's deferral — the sweep is bounded, tested, and D-scope says FULL polish. |
| D8 | **One late i18n task (10)** with the full de/fr/it table embedded in this plan; suite red on `test_translations.py` in between. | Per-task cycles churn 4 catalog files × 8 tasks for nothing; owner pushes only at the end. |
| D9 | **Lint guard is reporting-scoped with a ≥2-consecutive-words heuristic** over markup text nodes and JS `textContent/innerHTML/.title =` / `\|\| '…'` literals (HTML tags stripped first), plus an ALLOWED map. | Repo-wide or 1-word scans drown in identifiers. Skeleton: `tests/unit/test_template_url_prefix.py`. Single words (CSV, XLSX, Beta) are invisible by design. |
| D10 | **WS3 = surgical CSS/markup edits**: consolidate the thrice-declared `.reporting-main`; 24px gutter incl. the comment above it; Show-query bar divider + database icon + 320px max-height; `html.dark` GitHub-dark SQL token palette (light values byte-identical); `.reporting-sched-alert-hint` → `var(--nx-text-meta)` and `.reporting-truncated-note` → `var(--nx-warning)` (verified: light `#d97706` / dark `#fbbf24` both defined in nexora-ui.css); Beta badge inline style → `.reporting-beta` class + gettext. | Every dark-mode breaker gets a token or an `html.dark` override; token over hardcoded override where the token exists (D-design). |
| D11 | **The wizard's All-time default stays; a hint is added** (`rs-alltime-hint`). | Changing the default changes result semantics — owner call (Owner action 2). |
| D12 | **Pie slice borders stay `#fff`** on both tabs. | The chart PNG export forces a white background; a dark-mode border would dirty every exported image. Deliberate non-fix. |
| D13 | **Filename-only literals `'report'`/`'pivot'`/`'chart'` stay untranslated**; every fallback that can appear ON PAGE (`Report`, `Untitled report`, `SQL report`, `AI report`, drill `Detail rows`, export title) is translated. | D-language governs the page; OS download names are out of scope and single words are lint-invisible anyway. |
| D14 | **`fmtNumber` uses the app locale** via `document.documentElement.lang` (empty attr degrades to browser locale — safe); resolved-date ISO strings stay ISO. | A German UI showing `1,234` is a bug; ISO dates are language-neutral. Locale dates would be a new mini-convention (Owner action 8). |

---

## Owner actions (not for the executor)

1. **Review, merge `plan/reporting-flagship-ui-polish` back into `feature/2.5.64`, and push** (this session is commit-only; your push runs the full pre-push gate).
2. **Wizard default time range:** kept at *All time* (a hint was added, D11). If you want a bounded default (e.g. *This year*), say the word — a two-line change in `renderTimeStep()` plus e2e updates, but it changes what numbers first-time users see.
3. **The "Beta" badge:** now localized and tokenized — but should the flagship reference page still say Beta at all? Removal is a one-line markup edit + i18n prune.
4. **`window.confirm()` dialogs** (delete report / delete schedule) remain native after the alert→toast sweep. A styled modal (like the existing name modal) is a small follow-up if wanted.
5. **The dormant 2026-06-12 AI plain-language-clarifications plan** edits the same JS partials this plan rewrites. Decide whether it is still wanted; whoever executes it must re-Grep every anchor post-polish — or retire it.
6. **Drill-through live pass** (owed since PR 119): Task 13 spot-checks drill in the browser; decide whether that absorbs the dedicated isolated pass or you still schedule it separately.
7. **Error `detail` field:** raw English technical details now travel in a JSON `detail` key visible only in devtools (D5). If Advanced power-users need it on-page (a conscious D-language exception, e.g. behind a "technical details" disclosure), that's your call to green-light as a follow-up.
8. **Locale-formatted dates:** the resolvedDates transparency line still shows raw ISO `2026-07-01 → 2026-08-01` and no locale-date helper exists anywhere in the app — establishing that new mini-convention is a separate decision.

---

# PHASE 1 — WS1 backend: an inlined display/copy SQL field

### Task 1: `inline_sql_params` + `sqlDisplay` in `/api/reporting/run`

**Files:**
- Modify: `nx_lib/reporting/sqlformat.py` (new pure function + stdlib imports)
- Modify: `nx_lib/views/reporting.py` (one import, two lines in `api_run`)
- Test: `tests/unit/test_reporting_sqlformat.py` (append), `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Produces: `inline_sql_params(sql, params) -> str | None` — substitutes each bare `?` with a T-SQL literal (`str` → `'…'` with `''`-doubling, `bool` → `1/0` — checked BEFORE int since bool subclasses int, `int/float/Decimal` → bare, `date/datetime/time` → `'ISO'`, `None` → `NULL`; anything else → the whole call returns `None`). New run-response key `"sqlDisplay"` (string or `null`).
- Consumes: nothing new. `_execute(engine, sql, params)` keeps binding positionally — **never** feed it the inlined string.

- [ ] **Step 1 — Write the failing unit tests.** Append to `tests/unit/test_reporting_sqlformat.py` (the file already imports `pytest` and defines `REAL_BUILDER_SQL` with 4 placeholders; extend the import line `from nx_lib.reporting.sqlformat import format_sql` to also import `inline_sql_params`):

```python
def test_inline_replaces_placeholders_in_order():
    out = inline_sql_params(
        "SELECT * FROM t WHERE d >= ? AND d < ?", ["2026-07-01", "2026-08-01"]
    )
    assert out == "SELECT * FROM t WHERE d >= '2026-07-01' AND d < '2026-08-01'"


def test_inline_handles_scalar_types():
    out = inline_sql_params(
        "SELECT ? AS s, ? AS n, ? AS f, ? AS b1, ? AS b0, ? AS x",
        ["it's", 42, 1.5, True, False, None],
    )
    assert out == "SELECT 'it''s' AS s, 42 AS n, 1.5 AS f, 1 AS b1, 0 AS b0, NULL AS x"


def test_inline_never_touches_question_marks_in_strings_or_comments():
    sql = "SELECT '?' AS q FROM t WHERE a = ? -- really?\n"
    assert inline_sql_params(sql, ["x"]) == "SELECT '?' AS q FROM t WHERE a = 'x' -- really?\n"


def test_inline_question_mark_inside_param_value_is_not_reinterpreted():
    # The emitted literal is output, never re-scanned for placeholders.
    out = inline_sql_params("SELECT * FROM t WHERE a LIKE ? AND b = ?", ["%why?%", "z"])
    assert out == "SELECT * FROM t WHERE a LIKE '%why?%' AND b = 'z'"


def test_inline_count_mismatch_returns_none():
    # Substituting with the wrong arity would LIE about what executed.
    assert inline_sql_params("SELECT ? AS a", []) is None
    assert inline_sql_params("SELECT 1 AS a", ["extra"]) is None


def test_inline_unknown_type_returns_none():
    assert inline_sql_params("SELECT ? AS a", [object()]) is None


def test_inline_no_params_is_passthrough():
    assert inline_sql_params("SELECT 1", []) == "SELECT 1"


def test_inline_composes_with_format_sql():
    # The api_run pipeline: pretty first (placeholders survive — pinned above),
    # then inline. Four ? in REAL_BUILDER_SQL, two UNION subqueries.
    pretty = format_sql(REAL_BUILDER_SQL)
    out = inline_sql_params(pretty, ["2026-07-01", "2026-08-01", "2026-07-01", "2026-08-01"])
    assert out.count("'2026-07-01'") == 2
    assert "?" not in out
```

- [ ] **Step 2 — Run, expect RED** (ImportError):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_sqlformat.py -q`
Expected: collection error — `cannot import name 'inline_sql_params'`

- [ ] **Step 3 — Implement.** In `nx_lib/reporting/sqlformat.py`, replace the import line `import sqlglot` with:

```python
import datetime
import decimal
import re

import sqlglot
```

and append after the `format_sql` function:

```python
# Mirrors the client highlighter's tokenization (_reporting_sqlformat_js.html):
# a ? inside a 'string' (with '' escapes), a [bracketed identifier] or a
# -- comment is never a placeholder.
_INLINE_TOKEN_RE = re.compile(
    r"(--[^\n]*)"
    r"|('(?:[^']|'')*')"
    r"|(\[[^\]]*\])"
    r"|(\?)"
)


def _sql_literal(value):
    """One bound parameter as a T-SQL literal, or None for unknown types."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):  # before int: bool subclasses int
        return "1" if value else "0"
    if isinstance(value, int | float | decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.date | datetime.datetime | datetime.time):
        return "'" + value.isoformat() + "'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def inline_sql_params(sql, params):
    """Return `sql` with each bare pyodbc ``?`` replaced by its literal.

    Display/copy only — execution stays parameterized (api_run keeps sending
    sql+params to pyodbc). Returns None when the placeholder count disagrees
    with len(params) or a parameter has no literal form; callers fall back to
    the placeholder rendering, so this can never lie about what executed.
    """
    if not isinstance(sql, str):
        return None
    out = []
    pos = 0
    i = 0
    for m in _INLINE_TOKEN_RE.finditer(sql):
        out.append(sql[pos : m.start()])
        if m.group(4):
            if i >= len(params):
                return None
            lit = _sql_literal(params[i])
            if lit is None:
                return None
            out.append(lit)
            i += 1
        else:
            out.append(m.group(0))
        pos = m.end()
    out.append(sql[pos:])
    if i != len(params):
        return None
    return "".join(out)
```

- [ ] **Step 4 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_sqlformat.py -q`
Expected: `16 passed` (8 pre-existing collected — 6 defs, one parametrized ×3 — plus 8 new)

- [ ] **Step 5 — Write the failing integration test.** Append to `tests/integration/test_reporting_routes.py`, right after `test_run_response_includes_pretty_sql` (copy its patch stack verbatim — it is the established mock seam):

```python
def test_run_response_includes_inlined_display_sql(admin_client):
    """/run echoes sqlDisplay — the pretty SQL with parameter literals inlined
    (display/copy only; sql+params stay authoritative for execution)."""
    fake_cols = [{"field": "n", "header": "N"}]
    fake_sql = (
        "SELECT TOP (100) [a] AS [a], COUNT(*) AS [n] FROM "
        "(SELECT [A] AS [a] FROM [dbo].[T] WHERE [D] >= ? AND [D] < ?) t "
        "GROUP BY [a] ORDER BY [n] DESC"
    )
    fake_params = ["2026-07-01", "2026-08-01"]
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
    assert body["sql"] == fake_sql          # raw untouched
    assert body["params"] == fake_params    # still echoed
    assert "?" not in body["sqlDisplay"]
    assert "'2026-07-01'" in body["sqlDisplay"]
    assert "'2026-08-01'" in body["sqlDisplay"]
    assert "\n" in body["sqlDisplay"]       # pretty-printed
```

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -k inlined -q`
Expected: `1 failed` (KeyError `sqlDisplay`)

- [ ] **Step 6 — Wire the route.** In `nx_lib/views/reporting.py`:

Find: `from ..reporting.sqlformat import format_sql`
Replace: `from ..reporting.sqlformat import format_sql, inline_sql_params`

In `api_run`, find:

```python
    payload = {
        "columns": [
            {"field": c["field"], "header": c.get("header") or c["field"]} for c in columns
        ],
```

Replace:

```python
    pretty = format_sql(sql)
    payload = {
        "columns": [
            {"field": c["field"], "header": c.get("header") or c["field"]} for c in columns
        ],
```

Then find:

```python
        "sql": sql,
        "sqlPretty": format_sql(sql),
        "params": [_json_safe(p) for p in params],
```

Replace:

```python
        "sql": sql,
        "sqlPretty": pretty,
        "sqlDisplay": inline_sql_params(pretty, params),
        "params": [_json_safe(p) for p in params],
```

- [ ] **Step 7 — Run GREEN + collateral:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py tests/unit/test_reporting_sqlformat.py -q`
Expected: all passed (the two existing sql/params pins stay green)

- [ ] **Step 8 — Commit:**

```bash
git add nx_lib/reporting/sqlformat.py nx_lib/views/reporting.py tests/unit/test_reporting_sqlformat.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): inline bind params into display-only sqlDisplay field

Add pure inline_sql_params() beside format_sql(): substitutes each
bare pyodbc ? with a T-SQL literal (''-doubled strings, bare numerics,
bool as 1/0, ISO dates, NULL) while never touching ? inside string
literals, bracketed identifiers or comments (same tokenization as the
client highlighter). Best-effort: any arity mismatch or unknown type
returns None. /api/reporting/run echoes it as a third sibling field
sqlDisplay = inline(format_sql(sql), params); sql, sqlPretty, params
and the parameterized execution are byte-identical to before.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — WS1 frontend: runnable display + copy, footer dies

### Task 2: Both panels render/copy the inlined SQL via a shared seam

**Files:**
- Modify: `templates/js/_reporting_sqlformat_js.html` (two helpers on the seam)
- Modify: `templates/js/_reporting_simple_js.html` (state capture, show handler, copy handler, I18N key removal)
- Modify: `templates/js/_reporting_js.html` (same four spots)
- Modify: `templates/_reporting_simple.html`, `templates/reporting.html` (footer `<p>` removal)
- Modify: `static/css/reporting.css` (dead rule removal)
- Test: `tests/e2e/test_reporting_simple.py` (two new tests)

**Interfaces:**
- Produces: `window.ReportingSqlFormat.displayText(res)` / `.copyText(res)` where `res = {sql, sqlPretty, sqlDisplay, params}` — the single content policy for both tabs and the e2e seam.
- Consumes: `sqlDisplay` from Task 1 (absent/null → placeholder display + legacy `raw + "\n-- params: " + JSON` copy fallback).
- **`tests/unit/test_translations.py` goes RED here (pot desync from the removed `"Parameters"` msgid) — expected until Task 10.**

- [ ] **Step 1 — Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py` (module-level imports are `json`, `re`, `pytest`, `expect`; `_login` and `_stub_catalogs` exist in the file):

```python
def test_sqlformat_display_and_copy_policy(nexora_server, page):
    """displayText prefers the inlined sqlDisplay; copyText returns runnable
    SQL when inlined and falls back to raw + params comment otherwise. One
    window seam serves BOTH tabs' Show-query panels."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    res = {"sql": "SELECT ?", "sqlPretty": "SELECT\n  ?",
           "sqlDisplay": "SELECT\n  'x'", "params": ["x"]}
    assert page.evaluate("(r) => ReportingSqlFormat.displayText(r)", res) == "SELECT\n  'x'"
    assert page.evaluate("(r) => ReportingSqlFormat.copyText(r)", res) == "SELECT\n  'x'"
    fb = {"sql": "SELECT ?", "sqlPretty": "SELECT\n  ?", "sqlDisplay": None, "params": ["x"]}
    assert page.evaluate("(r) => ReportingSqlFormat.displayText(r)", fb) == "SELECT\n  ?"
    assert page.evaluate("(r) => ReportingSqlFormat.copyText(r)", fb) == 'SELECT ?\n-- params: ["x"]'


def test_show_query_inlines_parameters_and_copies_runnable_sql(nexora_server, page):
    """D-params: the panel shows literals instead of ?, the params footer is
    gone from the DOM, and Copy writes the runnable inlined statement."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    raw = ("SELECT TOP (100) [d] AS [d], COUNT(*) AS [n] FROM [dbo].[T] "
           "WHERE [d] >= ? AND [d] < ? GROUP BY [d]")
    inlined = ("SELECT TOP 100 [d] AS [d], COUNT(*) AS [n] FROM [dbo].[T] "
               "WHERE [d] >= '2026-07-01' AND [d] < '2026-08-01' GROUP BY [d]")

    def _handler(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "columns": [{"field": "d", "header": "D"}, {"field": "n", "header": "N"}],
            "rows": [["2026-07-01", 7]], "truncated": False, "rowCount": 1,
            "sql": raw, "sqlPretty": raw, "sqlDisplay": inlined,
            "params": ["2026-07-01", "2026-08-01"],
        }))

    page.route("**/api/reporting/run", _handler)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    show = page.get_by_test_id("rs-show-sql")
    expect(show).to_be_visible()
    # Capture clipboard writes without clipboard-read permissions.
    page.evaluate(
        "() => { window.__copied = null;"
        " navigator.clipboard.writeText = t => { window.__copied = t; return Promise.resolve(); }; }"
    )
    show.click()
    expect(page.locator("#rsSqlText")).to_contain_text("'2026-07-01'")
    assert page.locator("#rsSqlText span.sql-param").count() == 0  # no bare ? shown
    assert page.locator("#rsSqlParams").count() == 0               # footer element gone
    page.get_by_test_id("rs-sql-copy").click()
    assert page.evaluate("() => window.__copied") == inlined
```

- [ ] **Step 2 — Reset DB, run RED:**

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_sqlformat_display_and_copy_policy" "tests/e2e/test_reporting_simple.py::test_show_query_inlines_parameters_and_copies_runnable_sql" -q
```
Expected: `2 failed` (displayText undefined; footer element still present)

- [ ] **Step 3 — Extend the seam.** In `templates/js/_reporting_sqlformat_js.html`, find:

```js
  return { toHtml: toHtml, render: render };
```

Replace:

```js
  /* Panel/copy content policy — shared by the Simple and Advanced Show-query
     panels and the e2e seam tests. display = inlined literals when the server
     could inline (sqlDisplay), else the pretty placeholder form. copy = the
     runnable inlined statement, else the raw executed SQL plus a -- params:
     JSON comment (legacy fallback for the rare uninlinable case). */
  function displayText(res) {
    if (!res) return '';
    return res.sqlDisplay || res.sqlPretty || res.sql || '';
  }

  function copyText(res) {
    if (!res) return '';
    if (res.sqlDisplay) return res.sqlDisplay;
    return (res.sql || '') + '\n-- params: ' + JSON.stringify(res.params || []);
  }

  return { toHtml: toHtml, render: render, displayText: displayText, copyText: copyText };
```

- [ ] **Step 4 — Simple pane.** In `templates/js/_reporting_simple_js.html`:

(a) Find:
```js
    state.current.sql = res.data.sql || null;
    state.current.sqlPretty = res.data.sqlPretty || null;
    state.current.params = res.data.params || [];
```
Replace:
```js
    state.current.sql = res.data.sql || null;
    state.current.sqlPretty = res.data.sqlPretty || null;
    state.current.sqlDisplay = res.data.sqlDisplay || null;
    state.current.params = res.data.params || [];
```

(b) In the `el('rsShowSql').addEventListener('click', …)` handler, find:
```js
    if (!view.hidden) {
      ReportingSqlFormat.render(el('rsSqlText'), cur.sqlPretty || cur.sql);
      el('rsSqlParams').textContent = (cur.params || []).length
        ? I18N.sqlParamsLabel + ': ' + cur.params.map(function (p, i) {
            return (i + 1) + " = '" + String(p) + "'";
          }).join(', ')
        : '';
    }
```
Replace:
```js
    if (!view.hidden) {
      // sqlDisplay = pretty SQL with the parameter literals inlined
      // server-side (display + copy only; execution stays parameterized).
      ReportingSqlFormat.render(el('rsSqlText'), ReportingSqlFormat.displayText(cur));
    }
```

(c) In the `el('rsSqlCopy').addEventListener('click', …)` handler, find:
```js
    var text = cur.sql + '\n-- params: ' + JSON.stringify(cur.params || []);
```
Replace:
```js
    var text = ReportingSqlFormat.copyText(cur);
```

(d) Delete the I18N line (whole line):
```js
    sqlParamsLabel: {{ _("Parameters")|tojson }},
```

- [ ] **Step 5 — Advanced pane.** In `templates/js/_reporting_js.html`:

(a) Find:
```js
    state._lastSql = data.sql || null;
    state._lastSqlPretty = data.sqlPretty || null;
    state._lastParams = data.params || [];
```
Replace:
```js
    state._lastSql = data.sql || null;
    state._lastSqlPretty = data.sqlPretty || null;
    state._lastSqlDisplay = data.sqlDisplay || null;
    state._lastParams = data.params || [];
```

(b) In the `rpShowSqlBtn.addEventListener('click', …)` handler, find:
```js
      if (!view.hidden) {
        ReportingSqlFormat.render(document.getElementById('rpSqlText'),
          state._lastSqlPretty || state._lastSql);
        document.getElementById('rpSqlParams').textContent = (state._lastParams || []).length
          ? I18N_SQL_PARAMS + ': ' + state._lastParams.map(function (p, i) {
              return (i + 1) + " = '" + String(p) + "'";
            }).join(', ')
          : '';
      }
```
Replace:
```js
      if (!view.hidden) {
        // sqlDisplay = pretty SQL with the parameter literals inlined
        // server-side (display + copy only; execution stays parameterized).
        ReportingSqlFormat.render(document.getElementById('rpSqlText'),
          ReportingSqlFormat.displayText({
            sql: state._lastSql, sqlPretty: state._lastSqlPretty,
            sqlDisplay: state._lastSqlDisplay, params: state._lastParams
          }));
      }
```

(c) In the `rpSqlViewCopyBtn.addEventListener('click', …)` handler, find:
```js
      var text = state._lastSql + '\n-- params: ' + JSON.stringify(state._lastParams || []);
```
Replace:
```js
      var text = ReportingSqlFormat.copyText({
        sql: state._lastSql, sqlDisplay: state._lastSqlDisplay,
        params: state._lastParams
      });
```

(d) Delete the constant line (whole line):
```js
  var I18N_SQL_PARAMS = {{ _("Parameters")|tojson }};
```

- [ ] **Step 6 — Markup + CSS.** Delete these whole lines:
  - `templates/_reporting_simple.html`: `<p id="rsSqlParams" class="reporting-sqlview-params"></p>`
  - `templates/reporting.html`: `<p id="rpSqlParams" class="reporting-sqlview-params"></p>`
  - `static/css/reporting.css`: `.reporting-sqlview-params { font-size: 12px; color: var(--nx-text-meta); margin: 6px 0 0; }`

- [ ] **Step 7 — Run GREEN + the whole Simple e2e file** (proves `test_show_query_reveals_sql`, the sqlformat highlighter tests and everything else survive):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all passed (42 = 40 existing + 2 new)

- [ ] **Step 8 — Commit:**

```bash
git add templates/js/_reporting_sqlformat_js.html templates/js/_reporting_simple_js.html templates/js/_reporting_js.html templates/_reporting_simple.html templates/reporting.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): show-query panels display and copy runnable SQL

Both tabs render sqlDisplay (parameter literals inlined server-side)
in the Show-query panel and the Copy button now writes that runnable
statement; the grey "Parameters: 1 = ..." footer is removed (markup,
JS, CSS). Content policy is hoisted into the shared
window.ReportingSqlFormat seam (displayText/copyText) so one
page.evaluate e2e covers both tabs, with a graceful fallback to the
placeholder form + legacy -- params: comment when the server could
not inline. Supersedes the 2026-06-12 decision to copy raw SQL +
params comment. test_translations goes red on the now-unused
"Parameters" msgid until the Task 10 pybabel cycle prunes it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — WS2 language unification

### Task 3: Backend error boundary — translated errors, raw `detail`

**Files:**
- Modify: `nx_lib/reporting/sandbox.py` (token attribute), `nx_lib/views/reporting.py` (helper + 6 handler edits + export title fallbacks)
- Test: `tests/unit/test_reporting_sandbox.py` (append), `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Produces: `SqlSandboxError(rule, message, token=None)` (backwards-compatible — existing raise-sites and message texts unchanged); `_sandbox_error_message(e)` in the views module; 400 responses shaped `{"error": <translated>, "detail": <raw English>, ...}` with `rule` preserved on sandbox errors.
- Consumes: `MAX_SQL_LEN` from sandbox (new import in views). Raise-site messages in `query.py`/`schema.py`/`sandbox.py`/`table_query.py`/`semantic.py` unchanged (unit tests pin them).

- [ ] **Step 1 — Failing unit test.** Append to `tests/unit/test_reporting_sandbox.py` (the file already imports `pytest`, `SqlSandboxError` and `validate_select`):

```python
def test_sandbox_error_token_carries_dynamic_part():
    # The view boundary translates rule-keyed messages; the dynamic bit
    # (keyword/construct name) must ride on the exception, not be regexed
    # back out of the English message.
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("SELECT 1; DROP TABLE x")
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "DROP"
```

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_sandbox.py -q`
Expected: `1 failed` (AttributeError: token)

- [ ] **Step 2 — Implement in `nx_lib/reporting/sandbox.py`.**

Find:
```python
    def __init__(self, rule, message):
        super().__init__(message)
        self.rule = rule
```
Replace:
```python
    def __init__(self, rule, message, token=None):
        super().__init__(message)
        self.rule = rule
        self.token = token  # dynamic part (keyword/construct) for the i18n boundary
```

Find:
```python
    m = _BLOCKED_RE.search(scan)
    if m:
        raise SqlSandboxError("blocked_keyword", f"disallowed keyword: {m.group(0).strip()}")
```
Replace:
```python
    m = _BLOCKED_RE.search(scan)
    if m:
        kw = m.group(0).strip()
        raise SqlSandboxError("blocked_keyword", f"disallowed keyword: {kw}", token=kw)
```

Find:
```python
    forbidden = next(root.find_all(*_FORBIDDEN_NODES), None)
    if forbidden is not None:
        raise SqlSandboxError("forbidden_node", f"disallowed construct: {type(forbidden).__name__}")
```
Replace:
```python
    forbidden = next(root.find_all(*_FORBIDDEN_NODES), None)
    if forbidden is not None:
        name = type(forbidden).__name__
        raise SqlSandboxError("forbidden_node", f"disallowed construct: {name}", token=name)
```

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_sandbox.py -q` → all passed.

- [ ] **Step 3 — Failing integration tests.** Append to `tests/integration/test_reporting_routes.py`. The SQL-run test MUST patch `_has_acked` — `api_sql_run` checks the ack gate before the `try:` block and returns 409 otherwise (mirrors the house pattern in `test_sql_run_serializes_binary_and_time_cells`):

```python
def test_run_validation_error_is_translated_with_detail(admin_client):
    """A 400 from /run carries a gettext boundary message; the raw builder
    text moves to `detail` (devtools-only, never rendered on the page)."""
    from nx_lib.reporting.schema import ReportDefinitionError

    with (
        patch(
            "nx_lib.views.reporting._prepare_run",
            side_effect=ReportDefinitionError("at least one column is required"),
        ),
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
    ):
        resp = admin_client.post("/api/reporting/run", json={"source": "x"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["detail"] == "at least one column is required"
    assert body["error"] != body["detail"]
    assert "column" not in body["error"]  # raw builder text no longer leaks


def test_sql_run_sandbox_error_is_translated_with_rule_and_detail(admin_client):
    from nx_lib.reporting.sandbox import SqlSandboxError

    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.views.reporting._has_acked", return_value=True),
        patch("nx_lib.views.reporting._authorize_sql_target"),
        patch(
            "nx_lib.views.reporting._run_sql",
            side_effect=SqlSandboxError(
                "not_select", "only SELECT / WITH / set-operations are allowed"
            ),
        ),
    ):
        resp = admin_client.post(
            "/api/reporting/sql/run", json={"target": "statistics", "sql": "SELECT 1"}
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["rule"] == "not_select"
    assert body["detail"] == "only SELECT / WITH / set-operations are allowed"
    assert body["error"] != body["detail"]
```

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -k "translated" -q`
Expected: `2 failed`

- [ ] **Step 4 — Implement the boundary in `nx_lib/views/reporting.py`.**

(a) Find: `from ..reporting.sandbox import SqlSandboxError, validate_select, wrap_with_cap`
Replace: `from ..reporting.sandbox import MAX_SQL_LEN, SqlSandboxError, validate_select, wrap_with_cap`

(b) Insert the helper at module level directly above the unique `def api_sql_run():`'s decorator stack. Anchor the Edit on the two-line pair `@require_permission("reporting.sql.run")` + `@limiter.limit("20 per minute")` (newline-separated; this exact pair appears ONCE — the `@require_permission` line alone decorates two functions) and re-emit both lines below the inserted helper. Do NOT anchor on `@limiter.limit(...)` alone: it is the SECOND decorator, so inserting "directly above" it would land the helper BETWEEN the decorators — `@require_permission` would then decorate the helper and the live-SQL endpoint would silently lose its permission gate:

```python
def _sandbox_error_message(e):
    """Translated user-facing message for a SqlSandboxError, keyed by rule.

    The raw English message stays in the response's `detail` field; dynamic
    bits (keyword / construct name) arrive via e.token. Unknown rules fall
    back to the raw message rather than hiding information.
    """
    token = getattr(e, "token", None) or ""
    messages = {
        "empty": _("SQL is required."),
        "too_long": _("The SQL exceeds {n} characters.").format(n=MAX_SQL_LEN),
        "blocked_keyword": _("Disallowed keyword: {kw}").format(kw=token),
        "parse": _("The SQL could not be parsed."),
        "multi_statement": _("Exactly one statement is allowed."),
        "not_select": _("Only SELECT / WITH / set operations are allowed."),
        "forbidden_node": _("Disallowed construct: {kw}").format(kw=token),
    }
    return messages.get(e.rule, str(e))
```

(c) The definition/build-error passthrough appears **twice, byte-identical at 4-space indent** (in `api_run` and in `api_export`'s non-SQL branch) — replace BOTH (Edit with `replace_all: true`). Find:
```python
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify({"error": str(e)}), 400
```
Replace:
```python
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
```

(d) In `api_sql_run` the sandbox pair sits at **4-space excepts / 8-space returns** (unique at this indent). Find:
```python
    except SqlSandboxError as e:
        return jsonify({"error": str(e), "rule": e.rule}), 400
    except ReportDefinitionError as e:
        return jsonify({"error": str(e)}), 400
```
Replace:
```python
    except SqlSandboxError as e:
        return jsonify({"error": _sandbox_error_message(e), "rule": e.rule, "detail": str(e)}), 400
    except ReportDefinitionError as e:
        return jsonify({"error": _("Invalid SQL request."), "detail": str(e)}), 400
```

(e) In `api_export`'s SQL branch the pair sits at **8-space excepts / 12-space returns** (unique at this indent). Find:
```python
        except SqlSandboxError as e:
            return jsonify({"error": str(e), "rule": e.rule}), 400
        except ReportDefinitionError as e:
            return jsonify({"error": str(e)}), 400
```
Replace:
```python
        except SqlSandboxError as e:
            return jsonify(
                {"error": _sandbox_error_message(e), "rule": e.rule, "detail": str(e)}
            ), 400
        except ReportDefinitionError as e:
            return jsonify({"error": _("Invalid SQL request."), "detail": str(e)}), 400
```

Backstop: `Grep 'jsonify\(\{"error": str\(e\)' nx_lib/views/reporting.py` must now return ZERO hits.

(f) Export title fallbacks (all in request-context views — safe for `_()`): replace **each** occurrence of `rd.get("title") or "Report"` with `rd.get("title") or _("Report")` (two sites, in `api_export`) and `payload.get("title") or "Report"` with `payload.get("title") or _("Report")` (one site, in `api_export_grid`). Leave the lowercase `(title or "report")` filename sanitizer and the inner `title=title or "Report"` default alone (filename-only / unreachable once callers default).

- [ ] **Step 5 — Run GREEN + collateral** (raise-site messages unchanged, so the unit pins hold):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py tests/unit/test_reporting_sandbox.py tests/unit/test_reporting_schema.py tests/unit/test_reporting_query.py -q`
Expected: all passed

- [ ] **Step 6 — Commit:**

```bash
git add nx_lib/reporting/sandbox.py nx_lib/views/reporting.py tests/unit/test_reporting_sandbox.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
fix(reporting): translate API error boundary, keep detail field

400 responses from run/sql-run/export no longer pass raw English
exception text as the user-facing error: definition/build errors get
a translated generic message, sandbox errors a rule-keyed translated
map (SqlSandboxError grows a token attribute carrying the dynamic
keyword/construct so no message parsing is needed), and the export
title fallback is gettext-wrapped. The raw message always survives in
a new `detail` key for debugging. The ~104 raise sites in the pure
nx_lib/reporting modules are untouched, keeping them Flask-free and
their unit pins green. test_translations stays red until the Task 10
pybabel cycle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 4: JS offenders — fallback titles, request errors, chip/op labels, AI copy feedback

**Files:**
- Modify: `templates/js/_reporting_js.html`, `templates/js/_reporting_ai_js.html`, `templates/js/_reporting_drill_js.html`, `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py` (one updated pin + one new test)

**Interfaces:**
- Produces: translated I18N constants for every on-page fallback string (incl. `Untitled report`); `OP_LABELS` maps (symbols for eq/ne/gt/gte/lt/lte, gettext words for the rest) duplicated per-IIFE with identical msgids; chip labels resolve the catalog field label via the existing `fieldMetaFor()` with a seq-guarded post-catalog re-render; the AI-draft Copy button gains the house 1200 ms "Copied" feedback.
- Consumes: nothing new server-side. `friendlyRunError` needs NO change — after Task 3 every backend `error` string is already localized.

- [ ] **Step 1 — Update the e2e pin + write the new failing test.** In `tests/e2e/test_reporting_simple.py`, inside `test_chips_edit_and_remove_rerun_without_ai`, find:
```python
    # STUB_AI_DEFINITION has filters: [{field: "processname", op: "eq", value: "acme.inv"}]
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("processname eq acme.inv")
```
Replace:
```python
    # STUB_AI_DEFINITION has filters: [{field: "processname", op: "eq", value: "acme.inv"}].
    # eq renders as '='; the field key stays raw here because the TEST env's
    # docprocessing catalog is empty (no Statistics DB), so no label resolves.
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("processname = acme.inv")
```
CONTINGENCY (verify against the live TEST run): if the real TEST catalog DOES resolve a label for `processname` (e.g. the 0037-seeded "Process"), the chip renders the label form — pin `"Process = acme.inv"` instead. The new test below is deterministic either way because it stubs the catalog itself.

Then append:
```python
def test_chip_labels_resolve_field_and_op(nexora_server, page):
    """Chips show the catalog field label and a symbol op, not raw codes."""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps([{
                "id": "docprocessing", "label": "Document processing",
                "kind": "curated", "processes": ["acme.inv"],
                "fields": [{"field": "processname", "label": "Process",
                            "type": "string", "grainable": False, "filterable": True}],
            }]),
        ),
    )
    _stub_ai_build(page)
    _stub_run_ok(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    chips = page.get_by_test_id("rs-chips")
    # First paint may show the raw key; the catalog-resolve re-render fixes it.
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("Process = acme.inv")
```
Run: `C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_chips_edit_and_remove_rerun_without_ai" "tests/e2e/test_reporting_simple.py::test_chip_labels_resolve_field_and_op" -q`
Expected: `2 failed`

- [ ] **Step 2 — Advanced pane (`templates/js/_reporting_js.html`).**

(a) Find:
```js
  var I18N_RUNNING = {{ _("Running your report…")|tojson }};
```
Replace:
```js
  var I18N_RUNNING = {{ _("Running your report…")|tojson }};
  var I18N_REQUEST_FAILED = {{ _("The request failed")|tojson }};
  var I18N_REPORT = {{ _("Report")|tojson }};
  var I18N_UNTITLED = {{ _("Untitled report")|tojson }};
  var I18N_SQL_REPORT = {{ _("SQL report")|tojson }};
  var I18N_AI_REPORT = {{ _("AI report")|tojson }};
  // Filter-op labels — mirrored in _reporting_simple_js.html's OP_LABELS with
  // the same msgids, so the two maps can never translate apart.
  var OP_LABELS = {
    eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤',
    between: {{ _("between")|tojson }},
    'in': {{ _("is one of")|tojson }},
    not_in: {{ _("is not one of")|tojson }},
    contains: {{ _("contains")|tojson }},
    starts_with: {{ _("starts with")|tojson }},
    is_null: {{ _("is empty")|tojson }},
    is_not_null: {{ _("is not empty")|tojson }}
  };
```

(b) Find: `      throw new Error(body.error || res.statusText);`
Replace: `      throw new Error(body.error || (I18N_REQUEST_FAILED + ' (HTTP ' + res.status + ')'));`

(c) Find:
```js
    return document.getElementById('rpTitle').value
      || (state.mode === 'sql' ? 'SQL report' : 'Report');
```
Replace:
```js
    return document.getElementById('rpTitle').value
      || (state.mode === 'sql' ? I18N_SQL_REPORT : I18N_REPORT);
```

(d) Find: `      title: document.getElementById('rpTitle').value || 'Untitled report',`
Replace: `      title: document.getElementById('rpTitle').value || I18N_UNTITLED,`

(e) Find: `      title: document.getElementById('rpTitle').value || 'SQL report',`
Replace: `      title: document.getElementById('rpTitle').value || I18N_SQL_REPORT,`

(f) Find: `    var newName = document.getElementById('rpTitle').value || state.currentReportName || 'Report';`
Replace: `    var newName = document.getElementById('rpTitle').value || state.currentReportName || I18N_REPORT;`

(g) Find: `    applyDefinition(def, def.title || 'AI report', null);`
Replace: `    applyDefinition(def, def.title || I18N_AI_REPORT, null);`

(h) In the filters renderer's op `<select>` forEach, find:
```js
        var opt = document.createElement('option');
        opt.value = o;
        opt.textContent = o;
        op.appendChild(opt);
```
Replace:
```js
        var opt = document.createElement('option');
        opt.value = o;                        // payload contract: raw op code
        opt.textContent = OP_LABELS[o] || o;  // label localizes, value doesn't
        op.appendChild(opt);
```

- [ ] **Step 3 — AI panel (`templates/js/_reporting_ai_js.html`).**

(a) Find:
```js
  var AI_LINES = [
```
Replace:
```js
  var I18N_AI_REPORT = {{ _("AI report")|tojson }};
  var I18N_AI_COPIED = {{ _("Copied")|tojson }};
  var AI_LINES = [
```

(b) Replace **both** occurrences of `|| "AI report", null);` with `|| I18N_AI_REPORT, null);` (the `lastDef` and `lastAgentDef` sites).

(c) Copy feedback — the house 1200 ms label swap (`rpAiCopy` is a text button, verified). Find:
```js
  if (copyBtn) copyBtn.addEventListener("click", function () {
    if (navigator.clipboard && lastSql) navigator.clipboard.writeText(lastSql);
  });
```
Replace:
```js
  if (copyBtn) copyBtn.addEventListener("click", function () {
    if (!navigator.clipboard || !lastSql) return;
    navigator.clipboard.writeText(lastSql).then(function () {
      var prev = copyBtn.textContent;
      copyBtn.textContent = I18N_AI_COPIED;
      setTimeout(function () { copyBtn.textContent = prev; }, 1200);
    }).catch(function () { /* clipboard unavailable (non-HTTPS / unfocused) */ });
  });
```

- [ ] **Step 4 — Drill (`templates/js/_reporting_drill_js.html`).** Find:
```js
    nullLabel: {{ _("(empty)")|tojson }},
```
Replace:
```js
    nullLabel: {{ _("(empty)")|tojson }},
    exportName: {{ _("Detail rows")|tojson }},
```
Find: `      title: def.title || 'drill',`
Replace: `      title: def.title || I18N.exportName,`
Find: `    a.download = (current.definition.title || 'drill') + '.' + format;`
Replace: `    a.download = (current.definition.title || I18N.exportName) + '.' + format;`

- [ ] **Step 5 — Simple pane (`templates/js/_reporting_simple_js.html`).**

(a) Find:
```js
    copied: {{ _("Copied")|tojson }}
```
Replace:
```js
    opBetween: {{ _("between")|tojson }},
    opIn: {{ _("is one of")|tojson }},
    opNotIn: {{ _("is not one of")|tojson }},
    opContains: {{ _("contains")|tojson }},
    opStartsWith: {{ _("starts with")|tojson }},
    opIsEmpty: {{ _("is empty")|tojson }},
    opIsNotEmpty: {{ _("is not empty")|tojson }},
    copied: {{ _("Copied")|tojson }}
```

(b) Find:
```js
  function chipValueLabel(v) {
    if (isTokenValue(v)) return tokenLabel(v);
    if (Array.isArray(v)) return v.join(' → ');
    return v === null || v === undefined ? '' : String(v);
  }
```
Replace:
```js
  function chipValueLabel(v) {
    if (isTokenValue(v)) return tokenLabel(v);
    if (Array.isArray(v)) return v.join(' → ');
    return v === null || v === undefined ? '' : String(v);
  }

  // Filter-op labels for chips — mirrored in _reporting_js.html's OP_LABELS
  // with the same msgids, so the two maps can never translate apart.
  var OP_LABELS = {
    eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤',
    between: I18N.opBetween, 'in': I18N.opIn, not_in: I18N.opNotIn,
    contains: I18N.opContains, starts_with: I18N.opStartsWith,
    is_null: I18N.opIsEmpty, is_not_null: I18N.opIsNotEmpty
  };
```

(c) In `renderAiChips()`, find:
```js
    (def.filters || []).forEach(function (f) {
      var label = f.field + ' ' + f.op + ' ' + chipValueLabel(f.value);
```
Replace:
```js
    (def.filters || []).forEach(function (f) {
      var meta = fieldMetaFor(def, f.field);
      var parts = [(meta && meta.label) || f.field, OP_LABELS[f.op] || f.op];
      var vl = chipValueLabel(f.value);
      if (vl) parts.push(vl);        // is_null/is_not_null carry no value
      var label = parts.join(' ');
```

(d) In `runCurrent()`, find (the bare fire-and-forget call directly above `setView('result');` — unique; every other call site is `await loadSourcesCatalog();`):
```js
    loadSourcesCatalog();
    setView('result');
```
Replace:
```js
    loadSourcesCatalog().then(function () {
      // Chip labels resolve field keys against the catalog — re-render once it
      // lands (the first paint may fall back to raw keys on a cold session).
      // The seq guard keeps a stale resolve from repainting a newer result.
      if (seq === runSeq && state.current === cur) renderAiChips(cur);
    });
    setView('result');
```

- [ ] **Step 6 — Run GREEN + whole file:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all passed (43)

- [ ] **Step 7 — Commit:**

```bash
git add templates/js/_reporting_js.html templates/js/_reporting_ai_js.html templates/js/_reporting_drill_js.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): localize JS fallback titles, chips and request errors

Kill the remaining hardcoded English the JS partials showed users:
Report/Untitled report/SQL report/AI report fallback titles (builder,
save-name, AI panels), the browser statusText leak in api() (now a
translated message plus the language-neutral HTTP code), the drill
'drill' title/filename (now "Detail rows"), and the raw
`field op value` filter chips - they now show the catalog field label
plus a symbol (= != > >= < <=) or a translated word op, re-rendering
once the sources catalog resolves. The Advanced filter-op dropdown
gets the same labels; option VALUES stay raw codes (payload
contract). The AI Write-SQL Copy button gains the house 1200ms
"Copied" label-swap feedback. e2e chip pin updated accordingly.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 5: Lint guard — no hardcoded English on reporting surfaces

**Files:**
- Create: `tests/unit/test_reporting_i18n_lint.py`

**Interfaces:** none — a source lint in the style of `tests/unit/test_template_url_prefix.py` (module-level pattern list, `_offenders()` walker, one assert with a fix-it message).

- [ ] **Step 1 — Write the lint** (full file):

```python
"""Reporting i18n lint: no hardcoded English reaches reporting users.

D-language (2026-07 flagship polish): every user-facing string on the
reporting surfaces goes through gettext ({{ _("...") }} in markup, the
|tojson-injected I18N constants in the JS partials) or DB-driven labels.
This lint pins the two regression classes that produced the EN/DE mix:

1. Markup text nodes with >= 2 consecutive alphabetic words outside any
   Jinja expression, in the two reporting page templates.
2. String literals fed to textContent/innerHTML/.title assignments or used
   as `|| '...'` fallbacks in the reporting JS partials (HTML tags are
   stripped first so class-attribute soup can't false-positive).

Single words (CSV, XLSX, Beta, ...) are invisible to this lint by design —
a 1-word heuristic drowns in identifiers. If a flagged literal is genuinely
non-linguistic, add it to ALLOWED with a justification; never weaken the
regexes.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

MARKUP_TEMPLATES = [
    REPO_ROOT / "templates" / "reporting.html",
    REPO_ROOT / "templates" / "_reporting_simple.html",
]
JS_PARTIALS = sorted((REPO_ROOT / "templates" / "js").glob("_reporting*.html"))

WORDS = re.compile(r"[A-Za-z]{2,}[ ]+[A-Za-z]{2,}")
JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}")
TAGS = re.compile(r"<[^>]*>")
TEXT_NODE = re.compile(r">([^<>]+)<")
JS_LITERAL = re.compile(
    r"(?:textContent|innerHTML|\.title)\s*=\s*(['\"])((?:(?!\1).)*)\1"
    r"|\|\|\s*(['\"])((?:(?!\3).)*)\3"
)

ALLOWED = {
    # 'literal': 'why it is fine' — keys must be the POST-STRIP form (the
    # walkers strip HTML tags and whitespace before the lookup). Currently
    # empty: Tasks 2-4 removed every known offender.
}


def _markup_offenders():
    found = []
    for tpl in MARKUP_TEMPLATES:
        text = JINJA.sub("", tpl.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in TEXT_NODE.finditer(line):
                node = m.group(1).strip()
                if node in ALLOWED:
                    continue
                if WORDS.search(node):
                    found.append(f"{tpl.name}:{lineno}: >{node}<")
    return found


def _js_offenders():
    found = []
    for tpl in JS_PARTIALS:
        text = JINJA.sub("", tpl.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(("//", "*", "/*")):
                continue  # comments are developer-facing
            for m in JS_LITERAL.finditer(line):
                lit = TAGS.sub("", m.group(2) or m.group(4) or "").strip()
                if not lit or lit in ALLOWED:
                    continue
                if WORDS.search(lit):
                    found.append(f"{tpl.name}:{lineno}: '{lit}'")
    return found


def test_reporting_markup_has_no_hardcoded_english():
    offenders = _markup_offenders()
    assert offenders == [], (
        "Hardcoded multi-word text in reporting markup — wrap it in "
        '{{ _("...") }} and run the /nx-i18n cycle:\n' + "\n".join(offenders)
    )


def test_reporting_js_partials_have_no_hardcoded_english():
    offenders = _js_offenders()
    assert offenders == [], (
        "Hardcoded multi-word string literal in a reporting JS partial — "
        'inject it via an I18N constant ({{ _("...")|tojson }}) and run '
        "the /nx-i18n cycle:\n" + "\n".join(offenders)
    )
```

- [ ] **Step 2 — Run.** Expected: `2 passed` — Tasks 2–4 removed every known offender, **including `'Untitled report'`** (red-team-verified: without the Task 4 fix this lint flags `_reporting_js.html: 'Untitled report'`). **If it flags anything, treat each hit as a REAL offender first** — fix it with the Task 4 patterns and add the msgid to Task 10's table; only add to `ALLOWED` (with justification) if the literal is provably non-linguistic. Do not weaken the regexes.

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_i18n_lint.py -q`
Expected: `2 passed`

- [ ] **Step 3 — Commit:**

```bash
git add tests/unit/test_reporting_i18n_lint.py
git commit -F - <<'EOF'
test(reporting): lint guard against hardcoded English strings

Source lint (skeleton: test_template_url_prefix.py) over the two
reporting markup templates and every _reporting* JS partial: flags
>=2 consecutive alphabetic words in markup text nodes outside Jinja
expressions, and in string literals assigned to textContent/
innerHTML/.title or used as || fallbacks (HTML tags stripped first).
Reporting-scoped like the url-prefix lint started page-scoped; an
ALLOWED map with mandatory justifications handles non-linguistic
literals. Pins WS2 permanently.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — WS3 visual polish (design-system-true)

### Task 6: reporting.css polish + Beta badge + panel chrome

**Files:**
- Modify: `static/css/reporting.css`, `templates/reporting.html`, `templates/_reporting_simple.html`

**Interfaces:** none — colors move onto `--nx-*` tokens; every `id`/class/`data-testid` preserved; `.reporting-admin*` untouched; `nexora-ui.css` untouched; e2e only asserts `.sql-*` span *classes*, never colors (verified).

- [ ] **Step 1 — Consolidate `.reporting-main` (3 edits).** The selector is declared three times across the file's historical layers (plus once inside a `@media` block, which stays); the merged block carries the values that already win the cascade, so this is a pure readability fix.

Find (top of file):
```css
.reporting-main {
  display: grid;
  grid-template-columns: 260px 1fr 300px;
  gap: 16px;
  padding: 20px;
}
```
Replace:
```css
/* Single source of truth — the harmonization and redesign layers used to
   re-declare gap/padding/font/align below; consolidated 2026-07 with the
   values that already won the cascade. */
.reporting-main {
  display: grid;
  grid-template-columns: 260px 1fr 300px;
  gap: 20px;
  padding: 20px 24px 32px;
  align-items: start;
  font-family: var(--nx-font);
}
```

Delete the whole line: `.reporting-main { font-family: var(--nx-font); }`

Find:
```css
/* Top-align the three columns so the side cards hug their content
   instead of stretching to the tall results card. */
.reporting-main {
  gap: 20px;
  padding: 20px 24px 32px;
  align-items: start;
}
.reporting-fields,
.reporting-wells { align-self: start; }
```
Replace:
```css
/* Top-align the three columns so the side cards hug their content
   instead of stretching to the tall results card. */
.reporting-fields,
.reporting-wells { align-self: start; }
```

- [ ] **Step 2 — Align the header gutter on 24px** (tabs and main already use 24px) — rule AND the comment above it, so the comment doesn't lie. Find:
```css
.reporting-page-head { padding: 20px 20px 0; margin-bottom: 0; }
```
Replace:
```css
.reporting-page-head { padding: 20px 24px 0; margin-bottom: 0; }
```
Then in the comment block directly above that rule, find the fragment `Left padding matches the grid's 20px so the` and replace it with `Left padding matches the grid's 24px so the`.

- [ ] **Step 3 — Show-query panel chrome.** Find:
```css
.reporting-sqlview-bar { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 13px; margin-bottom: 6px; }
```
Replace:
```css
.reporting-sqlview-bar { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 13px; padding-bottom: 8px; border-bottom: 1px solid var(--nx-border); margin-bottom: 10px; }
.reporting-sqlview-bar span i { color: var(--nx-text-meta); margin-inline-end: 6px; font-size: 12px; }
```
Then find (the flagship screenshot shows the query cut off mid-WHERE; the dead footer's vertical space is now free):
```css
.reporting-sqlview pre { font-family: ui-monospace, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; background: var(--nx-sunken); color: var(--nx-text); border: 1px solid var(--nx-border); border-radius: 6px; padding: 10px; max-height: 240px; overflow: auto; margin: 0; }
```
and change `max-height: 240px` to `max-height: 320px` (rest of the rule byte-identical).

- [ ] **Step 4 — Panel bar icons.** In `templates/_reporting_simple.html`, find:
```html
          <span>{{ _("Query sent to the database") }}</span>
```
Replace:
```html
          <span><i class="fas fa-database" aria-hidden="true"></i>{{ _("Query sent to the database") }}</span>
```
Make the identical edit in `templates/reporting.html` (same one-line anchor inside `id="rpSqlView"`).

- [ ] **Step 5 — Dark-mode fixes.** Find:
```css
.reporting-sqlview pre .sql-comment, .reporting-ai-sql .sql-comment { color: #6e7781; font-style: italic; }
```
Replace (append the dark palette after the light block — light values are GitHub-light and stay byte-identical; the dark theme is stamped as `html.dark`, verified in nexora-ui.css):
```css
.reporting-sqlview pre .sql-comment, .reporting-ai-sql .sql-comment { color: #6e7781; font-style: italic; }

/* Dark theme: GitHub-dark syntax palette (the light values above are
   GitHub-light and unreadable on --nx-sunken dark). */
html.dark .reporting-sqlview pre .sql-kw, html.dark .reporting-ai-sql .sql-kw { color: #ff7b72; }
html.dark .reporting-sqlview pre .sql-string, html.dark .reporting-ai-sql .sql-string { color: #a5d6ff; }
html.dark .reporting-sqlview pre .sql-number, html.dark .reporting-ai-sql .sql-number { color: #79c0ff; }
html.dark .reporting-sqlview pre .sql-ident, html.dark .reporting-ai-sql .sql-ident { color: #ffa657; }
html.dark .reporting-sqlview pre .sql-param, html.dark .reporting-ai-sql .sql-param { color: #d2a8ff; }
html.dark .reporting-sqlview pre .sql-comment, html.dark .reporting-ai-sql .sql-comment { color: #8b949e; }
```

Find:
```css
.reporting-sched-alert-hint { margin: 4px 0 8px; font-size: 12px; color: #6b7280; }
```
Replace:
```css
.reporting-sched-alert-hint { margin: 4px 0 8px; font-size: 12px; color: var(--nx-text-meta); }
```

Find (token over hardcoded override — `--nx-warning` is defined in BOTH themes: light `#d97706`, dark `#fbbf24`, verified in nexora-ui.css):
```css
.reporting-truncated-note { margin: 0 0 8px; font-size: 12px; color: #b45309; }
```
Replace:
```css
.reporting-truncated-note { margin: 0 0 8px; font-size: 12px; color: var(--nx-warning); }
```

- [ ] **Step 6 — Beta badge: class instead of inline style, gettext instead of hardcoded.** In `templates/reporting.html`, find:
```html
<span class="nx-label nx-label--indigo nx-label--nodot" style="vertical-align: middle; margin-inline-start: .5rem;">Beta</span>
```
Replace:
```html
<span class="nx-label nx-label--indigo nx-label--nodot reporting-beta">{{ _("Beta") }}</span>
```
And append to `static/css/reporting.css` (end of file):
```css
/* --- Page-head Beta badge (was an inline style on the h1 span) --- */
.reporting-beta { vertical-align: middle; margin-inline-start: .5rem; }
```

- [ ] **Step 7 — Sanity: smoke e2e + lint still green:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting.py tests/unit/test_reporting_i18n_lint.py -q`
Expected: all passed

- [ ] **Step 8 — Commit:**

```bash
git add static/css/reporting.css templates/reporting.html templates/_reporting_simple.html
git commit -F - <<'EOF'
style(reporting): gutters, dark-mode and SQL-panel polish

Consolidate the thrice-declared .reporting-main into one block with
the values that already won the cascade; align the page-head gutter
(rule and comment) on the 24px grid the tabs and main already use;
give the Show-query bar a border divider and a database icon, and
320px of visible query; add a GitHub-dark token palette for the SQL
highlighter (light values byte-identical) plus token fixes for the
schedule hint (--nx-text-meta) and the truncation note
(--nx-warning, dark-safe); move the Beta badge's inline style into a
.reporting-beta class and wrap the label in gettext. No id, class
rename, or data-testid change - the e2e visual contract holds.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — WS4 smart UX

### Task 7: Library call-to-action empty states + AI-unavailable notice

**Files:**
- Modify: `templates/_reporting_simple.html`, `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py` (two new tests)

**Interfaces:**
- Produces: the three library groups get group-specific guidance instead of the shared "Nothing here yet." dead end; a 503 from the AI hides the bar AND explains why via a library-view hint (`rs-ai-gone`), instead of silently eating the typed question. Retires msgid `"Nothing here yet."` (pruned in Task 10).

- [ ] **Step 1 — Failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_library_empty_groups_show_calls_to_action(nexora_server, page):
    """Empty library groups explain the next step instead of a dead end."""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(status=200, content_type="application/json", body="[]"),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-group-mine")).to_contain_text(
        "You haven't saved any reports yet"
    )
    expect(page.get_by_test_id("rs-group-shared")).to_contain_text(
        "No reports have been shared with everyone yet."
    )
    expect(page.get_by_test_id("rs-group-direct")).to_contain_text(
        "No reports have been shared with you yet."
    )


def test_ai_unavailable_shows_notice_not_silent_vanish(nexora_server, page):
    """A 503 from the AI hides the bar AND tells the user why (previously the
    bar just disappeared, eating the typed question without a word)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.route(
        "**/api/reporting/ai/build",
        lambda r: r.fulfill(status=503, content_type="application/json",
                            body='{"error": "AI is not configured"}'),
    )
    page.get_by_test_id("rs-ai-prompt").fill("anything")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-ai-bar")).to_be_hidden()
    notice = page.get_by_test_id("rs-ai-gone")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("AI assistant is unavailable")
```

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_library_empty_groups_show_calls_to_action" "tests/e2e/test_reporting_simple.py::test_ai_unavailable_shows_notice_not_silent_vanish" -q`
Expected: `2 failed`

- [ ] **Step 2 — Markup.** In `templates/_reporting_simple.html`, find:
```html
      <button id="rsAiAsk" class="nx-btn nx-btn--secondary" data-testid="rs-ai-ask">
```
and locate its enclosing `</div>` followed by `{% endif %}` (the AI-bar conditional). Insert the notice line between the `</div>` and the `{% endif %}`:
```html
    <p class="reporting-simple-hint" id="rsAiGone" hidden data-testid="rs-ai-gone">{{ _("The AI assistant is unavailable right now — you can still build reports with “New report”.") }}</p>
```

- [ ] **Step 3 — JS.** In `templates/js/_reporting_simple_js.html`:

(a) Find:
```js
    nothingHere: {{ _("Nothing here yet.")|tojson }},
```
Replace:
```js
    emptyMine: {{ _("You haven't saved any reports yet — click “New report” to build your first one.")|tojson }},
    emptyShared: {{ _("No reports have been shared with everyone yet.")|tojson }},
    emptyDirect: {{ _("No reports have been shared with you yet.")|tojson }},
```

(b) In `renderLibrary()`, find:
```js
    Object.keys(groups).forEach(function (k) {
      if (!groups[k].children.length) {
        groups[k].innerHTML = '<p class="reporting-simple-empty">' + esc(I18N.nothingHere) + '</p>';
      }
    });
```
Replace (the `groups` object keys are `shared`/`mine`/`direct`, verified):
```js
    var groupEmptyText = { mine: I18N.emptyMine, shared: I18N.emptyShared, direct: I18N.emptyDirect };
    Object.keys(groups).forEach(function (k) {
      if (!groups[k].children.length) {
        groups[k].innerHTML = '<p class="reporting-simple-empty">' + esc(groupEmptyText[k]) + '</p>';
      }
    });
```

(c) In `setView()`, find:
```js
    var aiBar = el('rsAiBar');
    if (aiBar && !aiBar.dataset.gone) aiBar.hidden = view !== 'library';
```
Replace:
```js
    var aiBar = el('rsAiBar');
    if (aiBar && !aiBar.dataset.gone) aiBar.hidden = view !== 'library';
    var aiGone = el('rsAiGone');
    if (aiGone && aiBar && aiBar.dataset.gone) aiGone.hidden = view !== 'library';
```

(d) In `askAi()`, find:
```js
    if (res.status === 503) {
      aiBar.hidden = true;
      aiBar.dataset.gone = '1';
      setView('library');
      return;
    }
```
Replace:
```js
    if (res.status === 503) {
      aiBar.hidden = true;
      aiBar.dataset.gone = '1';
      var gone = el('rsAiGone');
      if (gone) gone.hidden = false;
      setView('library');
      return;
    }
```

- [ ] **Step 4 — Run GREEN + neighbors:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_library_empty_groups_show_calls_to_action" "tests/e2e/test_reporting_simple.py::test_ai_unavailable_shows_notice_not_silent_vanish" "tests/e2e/test_reporting_simple.py::test_library_groups_and_hides_sql_kind" -q`
Expected: `3 passed`

- [ ] **Step 5 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): CTA empty states and AI-unavailable notice

The three library groups replace the identical "Nothing here yet."
dead end with group-specific guidance (build your first report /
nothing shared with everyone / nothing shared with you), and an AI
503 no longer silently swallows the typed question: the bar still
hides, but a library-view hint explains the assistant is unavailable
and points at New report. "Nothing here yet." msgid retires in the
Task 10 cycle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 8: Advanced toasts, designed zero-row state, drill loader

**Files:**
- Modify: `templates/js/_reporting_js.html`, `templates/js/_reporting_drill_js.html`, `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py` (two new tests), `tests/e2e/test_reporting_save.py` (two comment updates)

**Interfaces:**
- Produces: an in-page `toast(msg, isError)` helper replacing all 18 `window.alert` sites on the Advanced tab (`window.confirm` stays native); the zero-row result upgrades to the `nx-empty` component (keeping `.reporting-empty` for the Motion observer); the drill drawer shows the page's pulsing-dots loading language instead of a literal `…`.
- Consumes: `.nx-empty`/`.nx-empty__art`/`.nx-empty__title`/`.nx-empty__sub` (nexora-ui, verified), `.reporting-ai-loading` dots (reporting.css, reduced-motion-safe), `I18N.exportName` drill anchor from Task 4.

- [ ] **Step 1 — Failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py`. FALLBACK for the zero-row test: it clicks Run assuming the Advanced pane auto-selected a curated source; if Run bails client-side because TEST has no curated source at that moment, seed one first via the in-page admin-API skeleton of `test_show_query_reveals_sql` (same file, `dbo.Users`-backed source, DELETE cleanup in `finally`) — the established pattern for exactly this.

```python
def test_advanced_no_rows_shows_designed_empty_state(nexora_server, page):
    """A zero-row Advanced run renders the nx-empty pattern, not a bare 'No rows.'"""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"columns": [{"field": "n", "header": "N"}], "rows": [],
                             "rowCount": 0, "truncated": False, "sql": None, "params": []}),
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-run").click()
    empty = page.get_by_test_id("reporting-no-rows")
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No rows matched")


def test_advanced_save_shows_toast_not_alert(nexora_server, page):
    """Saving surfaces an in-page toast; no browser alert dialog fires."""
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}
    page.request.post(f"{nexora_server}/api/reporting/sql/ack", headers=headers, data={})
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.locator('[data-testid="reporting-mode-sql"]').click()
    page.locator('[data-testid="reporting-sql-editor"]').fill("SELECT 1 AS x")
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.type), d.accept()))
    page.locator('[data-testid="reporting-save-as"]').click()
    page.get_by_test_id("reporting-name-input").fill("toast-save-e2e")
    page.get_by_test_id("reporting-name-ok").click()
    try:
        expect(page.get_by_test_id("reporting-toast")).to_be_visible()
        expect(page.get_by_test_id("reporting-toast")).to_contain_text("Saved")
        assert dialogs == []  # window.alert is gone from the save path
    finally:
        reports = page.request.get(f"{nexora_server}/api/reporting/reports").json()
        for r in reports:
            if r.get("name") == "toast-save-e2e":
                page.request.delete(
                    f"{nexora_server}/api/reporting/reports/{r['id']}", headers=headers
                )
```

Run both → expected: `2 failed`.

- [ ] **Step 2 — Toast helper + CSS.** In `templates/js/_reporting_js.html`, find:
```js
  function showError(msg) {
```
Replace:
```js
  // In-page toast — replaces window.alert for non-blocking feedback (browser
  // alerts were the last unstyled chrome on the page). window.confirm() stays
  // native: it needs a blocking answer.
  function toast(msg, isError) {
    var t = document.createElement('div');
    t.className = 'reporting-toast' + (isError ? ' reporting-toast--error' : '');
    t.setAttribute('role', 'status');
    t.setAttribute('data-testid', 'reporting-toast');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('is-gone'); }, 2600);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3000);
  }

  function showError(msg) {
```

Append to `static/css/reporting.css`:
```css
/* --- Toast (Advanced tab: replaces window.alert) --- */
.reporting-toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: var(--nx-card); color: var(--nx-text);
  border: 1px solid var(--nx-border); border-radius: 8px;
  padding: 10px 16px; font-size: 13px; z-index: 100; /* above the drill drawer */
  box-shadow: 0 6px 24px rgba(0, 0, 0, .18);
  transition: opacity .3s ease;
}
.reporting-toast--error { border-color: var(--nx-danger); }
.reporting-toast.is-gone { opacity: 0; }
```

- [ ] **Step 3 — Sweep every `window.alert(` in `templates/js/_reporting_js.html`** (grep first: `grep -n "window.alert(" templates/js/_reporting_js.html` — 18 sites at `d2d7205`). Mechanical rules — success/neutral messages get `toast(...)`, failures get `toast(..., true)`:
  - `window.alert('{{ _("Saved") }}');` (×2) → `toast('{{ _("Saved") }}');`
  - `window.alert('{{ _("Nothing to export.") }}');` (×2, both inside single-line `if (!...)` guards; one also has `return;`) → same text via `toast(...)`
  - `window.alert('{{ _("Save failed") }}: ' + e.message);` (×2), `window.alert('{{ _("Export failed") }}: ' + e.message);` (×2), `window.alert('{{ _("Rename failed") }}: ' + e.message);`, `window.alert('{{ _("Delete failed") }}: ' + e.message);` → same text, `toast(..., true);`
  - every bare `window.alert(e.message);` (×8) → `toast(e.message, true);`
  - Update the now-stale comment: find the two lines
    ```js
  // run. The window.alert matches the file's current idiom (menu row 8 sweeps
  // them all later).
    ```
    and replace them with
    ```js
  // run. Feedback goes through the in-page toast (the 2026-07 polish swept
  // the window.alert idiom away).
    ```
  - Verify: `grep -c "window.alert(" templates/js/_reporting_js.html` → `0`; `grep -c "window.confirm(" templates/js/_reporting_js.html` → unchanged (confirms stay).

- [ ] **Step 4 — Designed zero-row state.** In `renderResults()`, find:
```js
    if (!data.rows.length) {
      var empty = document.createElement('p');
      empty.className = 'reporting-empty';
      empty.textContent = '{{ _("No rows.") }}';
      wrap.appendChild(empty);
      return;
    }
```
Replace (DOM-built like `showRunLoading`; **`.reporting-empty` MUST stay on the wrapper** — the Motion observer in `_reporting_anim_js.html` animates exactly `TABLE`/`.reporting-empty`/`.reporting-error` nodes, and the late reporting.css layer centers `.reporting-empty`):
```js
    if (!data.rows.length) {
      var empty = document.createElement('div');
      empty.className = 'nx-empty reporting-empty';
      empty.setAttribute('data-testid', 'reporting-no-rows');
      var art = document.createElement('div');
      art.className = 'nx-empty__art';
      art.innerHTML = '<i class="fas fa-inbox" aria-hidden="true"></i>';
      var t = document.createElement('p');
      t.className = 'nx-empty__title';
      t.textContent = {{ _("No rows matched")|tojson }};
      var s = document.createElement('p');
      s.className = 'nx-empty__sub';
      s.textContent = {{ _("Widen the time range or remove a filter, then run again.")|tojson }};
      empty.appendChild(art); empty.appendChild(t); empty.appendChild(s);
      wrap.appendChild(empty);
      return;
    }
```
No color re-assert is needed: `.reporting-empty`'s winning text color is the neutral `--nx-text-sec` group (grouped with `.reporting-viz-note`/`.reporting-admin-note`, verified) — only the SEPARATE `.reporting-error` rule uses `--nx-danger` — and `.nx-empty__title`/`__sub` carry their own colors.

- [ ] **Step 5 — Drill loader.** In `templates/js/_reporting_drill_js.html` (Task 4 added `exportName:` after `nullLabel:` — anchor on it):

Find:
```js
    exportName: {{ _("Detail rows")|tojson }},
```
Replace:
```js
    exportName: {{ _("Detail rows")|tojson }},
    loading: {{ _("Loading the rows…")|tojson }},
```
Find:
```js
    el('rdBody').innerHTML = '<p class="reporting-drill-note">…</p>';
```
Replace (the pulsing-dots component is the page's single loading language; `esc()` exists in this file):
```js
    el('rdBody').innerHTML =
      '<div class="reporting-ai-loading"><span class="reporting-ai-dots" aria-hidden="true">' +
      '<i></i><i></i><i></i></span><span role="status">' + esc(I18N.loading) + '</span></div>';
```

- [ ] **Step 6 — Update the two stale dialog comments** in `tests/e2e/test_reporting_save.py`: find `    # The "Saved" alert auto-accepts; Save must issue a PUT (overwrite in place).` → replace with `    # Legacy guard (Saved is a toast now, no dialog fires); Save must issue a PUT.`; find `    # The "Saved" alert fires after the POST completes; accept it automatically.` → replace with `    # Legacy guard (Saved is a toast now, no dialog fires after the POST).` — the `page.on("dialog", …)` lines stay (harmless, and confirm() flows elsewhere still use dialogs).

- [ ] **Step 7 — Run GREEN + neighbors:**

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_save.py -q
```
Expected: all passed (47 in test_reporting_simple.py — 45 after Task 7 plus these 2 — and the save file green)

- [ ] **Step 8 — Commit:**

```bash
git add templates/js/_reporting_js.html templates/js/_reporting_drill_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_save.py
git commit -F - <<'EOF'
feat(reporting): toasts, designed zero-row state, drill loader

Replace every window.alert in the Advanced tab with a token-styled
in-page toast (error variant for failures; confirm() stays native as
it needs a blocking answer), upgrade the bare "No rows." paragraph to
the nx-empty pattern with a next-step subtitle (keeping the
.reporting-empty class the Motion observer and CSS centering key on),
and swap the drill drawer's literal-ellipsis loading state for the
page's pulsing-dots component with a translated status line. e2e
covers the toast (no dialog fires) and the zero-row empty state;
save-test dialog-handler comments updated (they are no-ops now).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 9: All-time full-scan hint + app-locale number formatting

**Files:**
- Modify: `templates/_reporting_simple.html`, `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py` (one new test)

**Interfaces:**
- Produces: wizard step 3 shows a full-scan hint while "All time" (`state.wiz.range === null`) is active; `fmtNumber` follows the app locale. Default behavior unchanged — All time stays the default (D11).

- [ ] **Step 1 — Failing e2e test.** Append (uses the existing `_stub_catalogs` + "Stub count" flow):

```python
def test_wizard_alltime_hint_toggles(nexora_server, page):
    """The default All-time choice warns about full-history scans; picking a
    bounded range hides the hint, coming back shows it again."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-next").click()
    hint = page.get_by_test_id("rs-alltime-hint")
    expect(hint).to_be_visible()  # All time is the default selection
    page.get_by_test_id("rs-time-list").get_by_text("This year", exact=True).click()
    expect(hint).to_be_hidden()
    page.get_by_test_id("rs-time-list").get_by_text("All time", exact=True).click()
    expect(hint).to_be_visible()
```

Run it → expected: `1 failed` (no `rs-alltime-hint` element yet).

- [ ] **Step 2 — Markup.** In `templates/_reporting_simple.html`, find:
```html
      <div id="rsTimeCustom" hidden>
        <input id="rsTimeRange" class="reporting-input" placeholder="{{ _('Pick a date range') }}">
      </div>
```
Replace:
```html
      <div id="rsTimeCustom" hidden>
        <input id="rsTimeRange" class="reporting-input" placeholder="{{ _('Pick a date range') }}">
      </div>
      <p class="reporting-simple-hint" id="rsAllTimeHint" hidden data-testid="rs-alltime-hint">{{ _("“All time” scans the whole history — pick a shorter range for faster results.") }}</p>
```

- [ ] **Step 3 — JS.** In `templates/js/_reporting_simple_js.html`, inside `renderTimeStep()`:

(a) Find:
```js
        } else {
          // Preset = relative-date token: resolved server-side on every run.
          // all_time = no filter.
          state.wiz.range = p[0] === 'all_time' ? null : { token: p[0] };
        }
      }, state.wiz.range === p[0] ||
```
Replace:
```js
        } else {
          // Preset = relative-date token: resolved server-side on every run.
          // all_time = no filter.
          state.wiz.range = p[0] === 'all_time' ? null : { token: p[0] };
        }
        el('rsAllTimeHint').hidden = state.wiz.range !== null;
      }, state.wiz.range === p[0] ||
```

(b) Find:
```js
    // Only default to all-time if no prior choice is being restored.
    if (!state.wiz.range) state.wiz.range = null;
```
Replace:
```js
    // Only default to all-time if no prior choice is being restored.
    if (!state.wiz.range) state.wiz.range = null;
    el('rsAllTimeHint').hidden = state.wiz.range !== null;
```

(c) The no-date-field early return leaves no time choices at all — the hint must not linger from a previous render. Find:
```js
    if (!dateFields.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' + esc(I18N.noDateField) + '</p>';
      el('rsTimeFieldWrap').hidden = true;
      state.wiz.range = null;
      return;
    }
```
Replace:
```js
    if (!dateFields.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' + esc(I18N.noDateField) + '</p>';
      el('rsTimeFieldWrap').hidden = true;
      state.wiz.range = null;
      el('rsAllTimeHint').hidden = true;
      return;
    }
```

(d) App-locale numbers — find:
```js
  function fmtNumber(v) {
    if (v == null) return '–';
    var n = Number(v);
    return isNaN(n) ? String(v) : n.toLocaleString();
  }
```
Replace:
```js
  var APP_LANG = document.documentElement.lang || undefined;
  function fmtNumber(v) {
    if (v == null) return '–';
    var n = Number(v);
    // App locale (html lang attr), not browser locale — a German UI shows
    // 1'234/1.234 shapes consistently regardless of the OS language. An
    // empty lang attr degrades to the browser locale (undefined arg).
    return isNaN(n) ? String(v) : n.toLocaleString(APP_LANG);
  }
```

- [ ] **Step 4 — Run GREEN + whole file:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all passed (48)

- [ ] **Step 5 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): all-time scan hint and app-locale numbers

The wizard's time step shows a hint while the (default) All-time
choice is selected - it scans the whole history, so nudge users
toward a bounded range for faster results; the default itself is
unchanged (owner decision), and the hint hides on the no-date-field
path. fmtNumber passes the html lang attribute into toLocaleString
so stat cards and tables format numbers in the app locale instead of
the browser locale.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 6 — i18n cycle + docs

### Task 10: pybabel cycle — extract, translate de/fr/it non-fuzzy, compile

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` + `.mo` (all COMMITTED; the pre-commit whitespace hooks exclude `translations/`; end-of-file-fixer additionally excludes `messages.pot` but trailing-whitespace does NOT — if it rewrites the pot, `git add -u` and recommit)

**Interfaces:**
- Produces: `tests/unit/test_translations.py` green again (pot in sync, all strings translated non-fuzzy, `.mo` up to date). Prunes the removed msgids `"Parameters"`, `"Nothing here yet."`, `"No rows."` (they become `#~` obsolete entries — leave them, that's the house state).

- [ ] **Step 1 — Extract + update:**

Run:
```
C:\dev\nexora\.venv\Scripts\pybabel extract -F babel.cfg -o messages.pot .
C:\dev\nexora\.venv\Scripts\pybabel update -i messages.pot -d translations
```
Expected: `updating catalog translations\de\LC_MESSAGES\messages.po` (and fr, it)

- [ ] **Step 2 — Translate.** Fill every new msgstr in all three catalogs and **remove every `#, fuzzy` marker** pybabel added. Already-existing translated msgids — pybabel reuses them; do NOT duplicate or overwrite: `Report` (de "Bericht" / fr "Rapport" / it "Rapporto"), `Copied`, and `Untitled report` (de "Unbenannter Bericht" / fr "Rapport sans titre" / it "Rapporto senza titolo" — `templates/reporting.html` extracts it today; it is NOT in the table below). The complete table (typographic quotes/dashes exactly as in the msgids; the German hint quotes „Gesamter Zeitraum“ and „Neuer Bericht“ verbatim because those are the existing de msgstrs of `All time` and `New report`):

| msgid | de | fr | it |
|---|---|---|---|
| This report definition is invalid or outdated. | Diese Berichtsdefinition ist ungültig oder veraltet. | Cette définition de rapport est invalide ou obsolète. | Questa definizione di report non è valida o è obsoleta. |
| Invalid SQL request. | Ungültige SQL-Anfrage. | Requête SQL invalide. | Richiesta SQL non valida. |
| SQL is required. | SQL ist erforderlich. | Le SQL est requis. | L'istruzione SQL è obbligatoria. |
| The SQL exceeds {n} characters. | Das SQL überschreitet {n} Zeichen. | Le SQL dépasse {n} caractères. | L'istruzione SQL supera {n} caratteri. |
| Disallowed keyword: {kw} | Nicht erlaubtes Schlüsselwort: {kw} | Mot-clé non autorisé : {kw} | Parola chiave non consentita: {kw} |
| The SQL could not be parsed. | Das SQL konnte nicht geparst werden. | Le SQL n'a pas pu être analysé. | Impossibile analizzare l'istruzione SQL. |
| Exactly one statement is allowed. | Es ist genau eine Anweisung erlaubt. | Une seule instruction est autorisée. | È consentita una sola istruzione. |
| Only SELECT / WITH / set operations are allowed. | Nur SELECT / WITH / Mengenoperationen sind erlaubt. | Seules les opérations SELECT / WITH / d'ensemble sont autorisées. | Sono consentite solo operazioni SELECT / WITH / di insieme. |
| Disallowed construct: {kw} | Nicht erlaubtes Konstrukt: {kw} | Construction non autorisée : {kw} | Costrutto non consentito: {kw} |
| The request failed | Die Anfrage ist fehlgeschlagen | La requête a échoué | La richiesta non è riuscita |
| SQL report | SQL-Bericht | Rapport SQL | Report SQL |
| AI report | KI-Bericht | Rapport IA | Report IA |
| Detail rows | Detailzeilen | Lignes de détail | Righe di dettaglio |
| between | zwischen | entre | tra |
| is one of | ist eines von | est l'un de | è uno di |
| is not one of | ist keines von | n'est pas l'un de | non è uno di |
| contains | enthält | contient | contiene |
| starts with | beginnt mit | commence par | inizia con |
| is empty | ist leer | est vide | è vuoto |
| is not empty | ist nicht leer | n'est pas vide | non è vuoto |
| Beta | Beta | Bêta | Beta |
| You haven't saved any reports yet — click “New report” to build your first one. | Sie haben noch keine Berichte gespeichert — klicken Sie auf „Neuer Bericht“, um Ihren ersten zu erstellen. | Vous n'avez pas encore enregistré de rapport — cliquez sur « Nouveau rapport » pour créer le premier. | Non hai ancora salvato alcun report — fai clic su “Nuovo report” per creare il primo. |
| No reports have been shared with everyone yet. | Es wurden noch keine Berichte für alle freigegeben. | Aucun rapport n'a encore été partagé avec tout le monde. | Nessun report è ancora stato condiviso con tutti. |
| No reports have been shared with you yet. | Mit Ihnen wurden noch keine Berichte geteilt. | Aucun rapport n'a encore été partagé avec vous. | Nessun report è ancora stato condiviso con te. |
| The AI assistant is unavailable right now — you can still build reports with “New report”. | Der KI-Assistent ist zurzeit nicht verfügbar — Berichte können Sie weiterhin über „Neuer Bericht“ erstellen. | L'assistant IA est indisponible pour le moment — vous pouvez toujours créer des rapports avec « Nouveau rapport ». | L'assistente IA non è al momento disponibile — puoi comunque creare report con “Nuovo report”. |
| No rows matched | Keine passenden Zeilen | Aucune ligne correspondante | Nessuna riga corrispondente |
| Widen the time range or remove a filter, then run again. | Erweitern Sie den Zeitraum oder entfernen Sie einen Filter und führen Sie den Bericht erneut aus. | Élargissez la période ou supprimez un filtre, puis relancez le rapport. | Amplia l'intervallo di tempo o rimuovi un filtro, poi esegui di nuovo il report. |
| Loading the rows… | Zeilen werden geladen… | Chargement des lignes… | Caricamento delle righe… |
| “All time” scans the whole history — pick a shorter range for faster results. | „Gesamter Zeitraum“ durchsucht die komplette Historie — wählen Sie für schnellere Ergebnisse einen kürzeren Zeitraum. | « Toute la période » parcourt tout l'historique — choisissez une période plus courte pour des résultats plus rapides. | “Tutto il periodo” analizza l'intero storico — scegli un intervallo più breve per risultati più rapidi. |

- [ ] **Step 3 — Compile + gate:**

Run:
```
C:\dev\nexora\.venv\Scripts\pybabel compile -d translations
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_translations.py -q
```
Expected: `7 passed` (pot in sync; de/fr/it fully translated non-fuzzy; .mo up to date)

- [ ] **Step 4 — Commit** (type is `chore(i18n)` — `i18n` is NOT a gitlint-permitted commit type):

```bash
git add messages.pot translations
git commit -F - <<'EOF'
chore(i18n): extract, translate and compile reporting polish strings

Full pybabel cycle for the flagship polish: ~30 new msgids (error
boundary, filter-op words, fallback titles, empty-state CTAs, AI
notice, all-time hint, drill loading line, Beta badge) translated
non-fuzzy into de/fr/it and compiled; the retired
Parameters / Nothing here yet. / No rows. msgids drop out of the
catalogs. test_translations is green again after being expectedly
red since Task 2.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 11: Docs + changelog — all four workstreams

**Files:**
- Modify: `docs/howto/reporting.md`, `CHANGELOG.md`

**Interfaces:** none (docs only). CLAUDE.md's "Keeping docs in sync" makes this part of the change, not a follow-up — every workstream gets its changelog entry.

- [ ] **Step 1 — Fix the stale howto passage.** In `docs/howto/reporting.md`, find:

```
A **Show query** toggle (collapsed by default,
    re-collapsed on every run) reveals the executed SQL — pretty-printed server-side
    (sqlglot) and syntax-highlighted — plus its bind parameters (visible to anyone who
    can run reports; the Copy button copies the raw executed statement). While a report
```

Replace:

```
A **Show query** toggle (collapsed by default,
    re-collapsed on every run) reveals the executed SQL — pretty-printed server-side
    (sqlglot), syntax-highlighted, and with the bind-parameter values inlined as
    literals, so the statement reads (and copies) as runnable SQL. Execution itself
    stays fully parameterized; the Copy button copies the inlined statement (visible
    to anyone who can run reports). While a report
```

- [ ] **Step 2 — CHANGELOG.** Under `## [Unreleased]` (all three subsections exist — verified):

To `### Added`:
```
- Reporting: smarter UX — group-specific call-to-action empty states in the Simple
  library, an explanatory notice (instead of silent removal) when the AI assistant
  is unavailable, in-page toasts replacing every `window.alert` on the Advanced tab,
  a designed "No rows matched" empty state, a real loading indicator in the
  drill-through drawer, a full-scan hint while the wizard's "All time" range is
  selected, and copy feedback on the AI SQL draft.
```

To `### Changed`:
```
- Reporting: the Show-query panels (Simple and Advanced) now display the executed
  SQL with parameter values inlined as literals and **Copy** copies that runnable
  statement; the separate "Parameters: 1 = …" footer is gone. Execution is
  unchanged and stays fully parameterized. Visual polish across the page: unified
  24px gutters, dark-mode SQL syntax colors, tokenised hint/warning colors,
  Show-query panel chrome.
```

To `### Fixed`:
```
- Reporting: no more English fragments in localized UIs — reporting API errors are
  translated at the boundary (raw engine text demoted to a debug-only `detail`
  field), filter chips and the Advanced op dropdown show localized operator labels
  and catalog field names instead of raw codes, fallback report titles ("Report",
  "Untitled report", "SQL report", "AI report", drill exports) and the Beta badge
  are localized, and result numbers format with the app locale.
```

- [ ] **Step 3 — Commit:**

```bash
git add docs/howto/reporting.md CHANGELOG.md
git commit -F - <<'EOF'
docs(reporting): document inlined show-query SQL and polish round

Rewrite the howto's Show-query passage (parameters are now inlined
literals and Copy is runnable; execution stays parameterized) and
add the Unreleased changelog entries for all four workstreams of
the flagship polish: display/copy change and visual polish
(Changed), i18n unification (Fixed), and the smart-UX additions
(Added).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 7 — Full gate + live verification

### Task 12: Full local test gate

**Files:** none (verification only).

- [ ] **Step 1 — Non-e2e tiers:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q`
Expected: all passed, 0 failed (includes translations, sqlformat, sandbox, routes, the new i18n lint, url-prefix lint)

- [ ] **Step 2 — e2e tier:**

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e -q
```
Expected: all passed (`test_reporting_simple.py` now has 48 tests; retries come from `tests/e2e/conftest.py` flaky marks)

- [ ] **Step 3 —** `git log --oneline -11` — confirm the eleven commits from Tasks 1–11 are present in order on `plan/reporting-flagship-ui-polish`. Nothing to commit in this task.

### Task 13: Live browser verification + screenshots (absorbs the owed drill spot-check)

**Files:** none (screenshots to `var/screenshots/`, never the repo root).

- [ ] **Step 1 — Restart the dev server with auto-login** (Jinja caches templates for the process lifetime): `nx -u -b --loginas:<the owner's usual admin login — needs reporting.view/export/sql.run/ai.use and docprocessing scope>`.
- [ ] **Step 2 — WS1:** run a Simple wizard report with a bounded time range → **Show query**: the panel shows `'YYYY-MM-DD'` literals, NO `?`, NO grey Parameter footer; **Kopieren** flips to the localized "Copied" label; paste the clipboard into a scratch buffer and eyeball that it is a complete runnable SELECT. Repeat once on the Advanced tab. Screenshots: `var/screenshots/reporting-polish-showquery-light.png` and, after toggling dark theme, `...-dark.png` (SQL token colors must be readable — GitHub-dark palette).
- [ ] **Step 3 — WS2 (German):** switch the profile locale to de → chips read e.g. `Prozess = acme.inv` (no `eq`), the Advanced op dropdown shows `enthält`/`ist leer`, the stat number formats per locale, no English fragment anywhere on either tab. Force a sandbox error in SQL mode (`DELETE FROM x` → Run) → the inline error is German ("Nicht erlaubtes Schlüsselwort: DELETE"). Screenshot: `var/screenshots/reporting-polish-german.png`.
- [ ] **Step 4 — WS4:** empty "My reports" (fresh user or gibberish search) shows the three CTAs; wizard step 3 hint toggles with All time; Advanced zero-row run shows the designed empty state; save a report → toast (no browser alert); click a chart bar → drill drawer shows pulsing dots then rows — **this doubles as the drill-through spot-check owed since PR 119**: check header, null styling, workitem links, CSV export. Screenshots: `var/screenshots/reporting-polish-emptystates.png`, `reporting-polish-drill.png`.
- [ ] **Step 5 — WS3 + dark mode:** head/tabs/content share the 24px gutter; Beta badge visually unchanged; dark mode: truncation note amber, sched hint legible. Screenshots light+dark at 1440px and 375px widths: `reporting-polish-layout-{light,dark}-{1440,375}.png`.
- [ ] **Step 6 — If this is a remote session, SendUserFile every screenshot as you go** (remote frontend rule). Then STOP — the owner reviews, merges into `feature/2.5.64` and pushes.

---

## Gotchas & notes

- **`test_translations.py` is RED from Task 2 through Task 10 — expected.** Don't "fix" it early with ad-hoc `.po` edits; the single Task 10 cycle handles extraction, pruning (`Parameters`, `Nothing here yet.`, `No rows.`) and compilation. Pre-commit does not run pytest, so per-task commits are unaffected; this session never pushes.
- **Never feed the inlined string to execution.** `_execute(engine, sql, params)` keeps positional `?` binding; `sqlDisplay` is display/copy only. The inliner refuses (returns `None`) on any arity/type doubt — the UI then falls back to the pretty placeholder form and the legacy `-- params:` copy comment, so it can never lie about what ran and param info is never lost in the degrade path.
- **sqlglot normalizes tokens** (`TOP (5000)` → `TOP 5000`) — `sqlDisplay` inherits that from `sqlPretty`. Cosmetic, already the panel's documented behavior.
- **`test_sqlformat_marks_placeholders_and_numbers` stays untouched** — `toHtml` still highlights `?` (the fallback path uses it, and the AI Write-SQL draft renders raw drafted SQL through it). Only the *panel content policy* changed, not the highlighter.
- **`sqlPretty` stays in the payload** even though both panels now prefer `sqlDisplay` — one integration test (`test_run_response_includes_pretty_sql`) pins it and it is the client display fallback (`cur.sqlPretty || cur.sql`); no e2e stub carries it. `_stub_run_ok` returns `"sql": None`, so stubbed AI flows keep the Show-query button hidden — unchanged.
- **The `-- params:` copy suffix and the footer had ZERO test coverage** (grep-verified: no e2e mentions `SqlParams` or the comment) — the only test edits WS1 forces are the ones this plan makes explicitly.
- **The definition-error pair appears twice byte-identical** (api_run + api_export non-SQL branch, 4-space) — Task 3 step 4(c) must use `replace_all: true` or the two drift. The sandbox pairs are unique by indentation: 4-space excepts in `api_sql_run`, 8-space excepts in `api_export`'s SQL branch (verified — earlier drafts misstated these levels). The zero-hits grep is the backstop.
- **`_has_acked` gates `api_sql_run` before its `try:`** — any integration test driving `/api/reporting/sql/run` must patch `nx_lib.views.reporting._has_acked` to `True` (house pattern: `test_sql_run_serializes_binary_and_time_cells`) or it 409s and never reaches the patched `_run_sql`.
- **Boundary messages vs. Simple tab:** `friendlyRunError` still maps every 400 to the "outdated — open it in Advanced" hint (unchanged; it can mislabel genuine validation errors, a pre-existing quirk). The Advanced tab is where the new translated boundary messages surface. The raw English lives only in the `detail` JSON key (devtools) — surfacing it on-page is Owner action 7, not a reason to re-English the page.
- **Op labels: values stay raw codes.** Only `<option>.textContent` and chip text localize; definitions, payloads and saved reports are untouched. `'in'` is quoted as an object key defensively.
- **Chip re-render staleness guard:** the `.then` re-render checks `seq === runSeq && state.current === cur`, so a slow catalog fetch can never repaint a newer result's chips. The chip label falls back to the raw field key when the definition's source isn't in the loaded catalog (e.g. the e2e stub) — hence the `processname = acme.inv` pin, with the label-form contingency noted in Task 4 Step 1.
- **The Motion animation layer** (`_reporting_anim_js.html`) animates exactly `TABLE`/`.reporting-empty`/`.reporting-error` nodes — the new zero-row `<div class="nx-empty reporting-empty">` keeps the class on purpose. **No color re-assert is needed**: `.reporting-empty`'s winning color is the neutral `--nx-text-sec` group (grouped with `.reporting-viz-note`/`.reporting-admin-note`); only the SEPARATE `.reporting-error` rule is `--nx-danger` (verified — an earlier draft claimed a grouped danger rule that does not exist).
- **Toast z-index 100** sits above the drill drawer and modals. The toast never uses a `.hidden` class (Tailwind-v4 layer trap) — it removes itself from the DOM. `page.on("dialog", …)` handlers in `test_reporting_save.py` become no-ops after the alert sweep — deliberately kept (confirm() flows elsewhere still dialog), only their comments updated.
- **All-time hint edges:** picking "Custom" without dates keeps `state.wiz.range === null`, so the hint stays visible — honest (an empty custom range runs unfiltered). Picking custom dates hides it on the next chip click, not instantly via the flatpickr callback — accepted micro-staleness to avoid touching the flatpickr wiring. The no-date-field early return hides the hint explicitly (Task 9 step 3c).
- **`.nx-rise` fill-mode stays `backwards`**, `.sql-*` light colors stay GitHub-light (dark overrides are additive `html.dark` rules — that is the verified dark-theme stamp), and no `.reporting-*` class was renamed anywhere — the e2e visual contract from the redesign plan holds. Do not re-order or dedupe other `reporting.css` layers; every edit above targets the LIVE rule (verified against later re-declarations), and the `.reporting-main` consolidation removes the one known editing-a-dead-rule trap.
- **Pie borders stay `#fff` (D12)** — the chart PNG export forces a white background; don't "fix" this in a dark-mode sweep.
- **`fmtNumber`'s en-dash null (`'–'`) is e2e-pinned** — don't touch it while adding the locale argument. `resolvedDates` still shows ISO dates (`d.start + ' → ' + d.end`) — dates are not language mixing; a locale-date convention is Owner action 8.
- **Filename-only literals `'report'`/`'pivot'`/`'chart'`** are deliberately untranslated (D13) — single words are invisible to the lint. The AI `agentContext()` English preamble is model-facing, never rendered — untouched.
- **Lint hits are real offenders first** — the `'Untitled report'` fallback proved the lint's regexes bite (it was missed by both original drafts and IS flagged by the lint); fix new hits with the Task 4 patterns + the Task 10 table, and only then consider `ALLOWED`.
- **Task-order-dependent anchors:** Task 8's drill anchor (`exportName:`) is created by Task 4; Task 4's Simple I18N anchor (`copied:`) sits directly below the line Task 2 deleted (`sqlParamsLabel:`). Execute in order; re-Grep if anything moved.
- **Sequencing vs. siblings:** the parallel `plan/external-api-v1-today-stats` planning run may also touch `nx_lib/views/reporting.py` — whichever branch merges second re-verifies anchors. The dormant 2026-06-12 AI-clarifications plan must be fully re-anchored if ever executed (Owner action 5).
- **If any DB catalog label turns out wrong during Task 13** (German user sees an English *field* name in chips/tables): that's `Search_Field_Labels` data, not gettext — data-only migration, next free number `0038`, `0037_reporting_processname_label.sql` is the template. Not expected (audit found none).
- **Hooks recap:** `ruff`/`ruff-format` may reformat the new Python — `git add -u` and recommit; `gitlint` needs the non-empty body (provided) and one of the permitted types (`chore(i18n)`, never `i18n(…)`); `sql-migrate-int`/`sql-sync-check` need `env/INT.env` copied into the worktree (no migration in this plan, but the hooks still want env to no-op cleanly); `SQL_SYNC_SKIP=1` only for INT-unreachable flakes.
- **Commit trailer:** repo history stamps the model that actually ran the work. The blocks above use `Claude Sonnet 5` for the declared Sonnet executor — substitute the real name if a different model executes. Never copy a planning-model name into an execution commit.
