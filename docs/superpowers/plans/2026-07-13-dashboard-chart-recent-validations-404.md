# Dashboard PROD Bugs: Recent-Validations 404 + Non-PDBS Chart Blank — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. This plan was merged from two independent drafts and adversarially red-teamed on 2026-07-13; findings are folded in — trust the anchors, never line numbers.

**Goal:** Fix two PROD dashboard bugs in one pass: (1) clicking a **Recent Validations** card lands on an IIS 404 because the card's onclick uses a root-relative `/workitems?search=<id>` URL that escapes the `/nexora` PROD prefix — and the identical defect class exists latently in the error pages, the four reporting `api()` helpers, the reporting AI/export fetches, and the prepared-documents partial, all swept in this plan so the new lint guard ships allowlist-free; (2) the **Documents Processed over time** chart (and, by shared code, the KPI cards / hourly chart / avg-processing-time card) renders empty for every non-PDBS process because a failure in the default StatisticsDB (T-SQL) leg 500s the whole endpoint before the healthy MS02/Postgres leg runs, and the 500 gets pinned in the response cache. Bug 1's root cause is confirmed; Bug 2's exact PROD failure is diagnosed first (read-only), with every plausible outcome mapped to a pre-written task or owner action.

**Bug 1 — Confirmed root cause (do not re-investigate):**
- PROD serves the app under a URL prefix: `nx_lib/__init__.py` ends `create_app` with `if cfg.IS_PROD:` → `app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix="/nexora")` (`nx_lib/middleware.py`; it sets `SCRIPT_NAME`, so server-side `url_for()` is prefix-correct — only hand-built client-side URLs break).
- `templates/js/_dashboard_js.html`, inside `updateActivityFeed()`, renders each card with `onclick="window.location.href='/workitems?search=${act.id}'">` — root-relative, escapes the prefix, lands on the IIS ROOT site (`C:\inetpub\wwwroot`, handler StaticFile) → the exact 404.0 the user saw.
- The correct idiom is already defined on line 4 of the same file: `const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";` and used by every fetch in it. `templates/js/_chat_js.html` renders the identical target URL correctly: `` const url = `${API_PREFIX}workitems?search=${id}`; ``.
- Full-templates sweep of the defect class (verified 2026-07-13): `templates/handlers/_error_base.html` has two `href="/"` home links; the four reporting partials with `api()` helpers make 33 `api('/api/reporting/...')` calls that pass root-relative literals straight to `fetch`; `_reporting_ai_js.html` has 3 bare `fetch("/api/reporting/ai/...")` calls and `_reporting_simple_js.html` 1 bare `fetch('/api/reporting/export', ...)`; `templates/js/_prepared_documents_js.html` line 3 reads `const API_PREFIX = window.API_PREFIX || "/";` — and `window.API_PREFIX` is assigned NOWHERE in the repo, so that page's fetches are prefix-broken on PROD too. All reporting partials are IIFE-wrapped (`(function () {`), so per-file `API_PREFIX` consts cannot collide.
- **Why tests passed:** `tests/conftest.py` sets `ENVIRONMENT=TEST`, so `PrefixMiddleware` is never wired in any test or dev run; `tests/e2e/test_dashboard.py` is deliberately chrome-only and never clicks an activity card. Only a source lint can guard this.

**Bug 2 — Confirmed failure GEOMETRY (code-side), unconfirmed PROD trigger:**
- `nx_lib/views/dashboard.py` `dashboard_processed_over_time` runs the default T-SQL leg (`engine_statistics_db`, one `UNION ALL` built verbatim from `dbo.Statconfig` row values as `FROM [{DB_STATISTICS}].{row.TableName}` + raw `additionalCondition`) BEFORE the MS02 leg, inside a single `try/except` that returns `jsonify({"error": str(e)}), 500` — so any default-leg exception kills the whole endpoint including the healthy MS02 numbers. Selecting the PDBS process yields zero default rows → `if sub_queries:` skips StatisticsDB entirely → only the resilient MS02 leg runs → works. That is exactly the "only PDBS works" symptom.
- The MS02 leg is ALREADY isolated: `_ms02_stat_rows` swallows-and-logs (`current_app.logger.error(f"ms02 dashboard stats query failed: {e}")` → `return []`). The default leg lacks the mirror.
- Siblings `dashboard_kpi_stats`, `dashboard_hourly_stats`, `dashboard_avg_processing_time` share the identical single-try shape, so if the default leg is failing on PROD, the KPI cards (incl. the backlog number, which never even touches StatisticsDB), hourly chart and avg card are blanked too — the real blast radius is all four endpoints.
- All four are `@cache.cached` (300/60/120/300 s, key = userid + process filter) with **no `response_filter`** — a transient 500 is pinned in SimpleCache for the full TTL per user+filter.
- The front-end (`updateProcessedOverTimeChart` in `_dashboard_js.html`) never checks `response.ok` — a 500 body yields `data.labels`/`data.data` undefined → silent blank chart, console-only error.
- What is NOT known: WHICH failure is live on PROD (connectivity, bad Statconfig data, SQL-construction, empty upstream tables, or pinned transient errors). Task 3 discriminates with authorized read-only PROD access; Tasks 4–6 are unconditional resilience fixes that ship regardless of the diagnosis outcome.
- Migration `0032` (PROD data change from PR #115) is ruled out code-side: `dbo.ActivityInstancesToIgnore` is consumed only by `get_activity_instances_to_ignore()` → `api_recent_activity`/backlog, never by any Statconfig-driven chart SQL. Residual: a PROD `Statconfig.additionalCondition` value could reference anything — Task 3 reads the rows.
- User answer: NOT SURE whether this worked on PROD before the 2026-07-13 deploy — regression vs longstanding is undetermined; the plan assumes neither.

**Architecture:** Bug 1 is a template-fix sweep using each file's `API_PREFIX` idiom (plus `url_for('index')` on the error pages), guarded permanently by a new template-lint unit test — the only guard that can work, since the prefix is never wired outside PROD. Bug 2 gets (a) a bounded read-only PROD diagnosis with an explicit A–E decision tree, (b) a `_default_stat_rows` helper mirroring `_ms02_stat_rows` so one dead leg can never blank the other, applied to all four legacy endpoints, (c) `response_filter` on the four cache decorators so errors are never pinned (proven end-to-end by one integration test), (d) a `response.ok` guard in the chart updater (console-only — no new user-facing string, no i18n cycle), and (e) a conditional corrective data migration / conditional SQL-construction fix, selected by the diagnosis.

**Tech stack:** Python 3.13 / Flask, pyodbc raw cursors + SQLAlchemy engines (`nx_lib/db.py`), Flask-Caching SimpleCache, Jinja2 JS partials, pytest (unit tests mock engines — TEST has NO Statistics DB), SQL Server migrations under `sql/_migrations/NexoraDB/`.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.64`. Commit per task. **Do NOT push and do NOT open a PR** — the owner reviews and pushes (pre-push runs the full two-tier suite incl. Playwright e2e).
- **CONCURRENT WORK ON THIS BRANCH (important):** the docfield-permission-gating plan is being executed on the SAME branch in parallel — commits `a32c7c7` (`feat(db): ... (0035)`) and `9b54052` (`feat(workitems): ...`) landed on 2026-07-13, and the working tree may contain that effort's uncommitted files (e.g. `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py`). Consequences:
  - At execution start, run `git status` and `git log --oneline -5`. If unrelated modified files exist, **leave them alone** — `git add` ONLY the explicit paths named in each task's commit step; never `git add -A`, `git add .`, or `git add -u`.
  - If another agent session is actively editing this working tree right now, stop and ask the owner before proceeding.
  - **Re-list `sql/_migrations/NexoraDB/` before writing any migration** — the next free number was `0036` on the evening of 2026-07-13 (`0035_docfield_sensitive_and_validation_user.sql` is taken), but the concurrent effort may consume more numbers.
  - `CHANGELOG.md` and `CLAUDE.md` are also merge-conflict surface with that effort — Task 9 anchors on section headings and appends at the end of the subsection instead of on specific neighboring bullets.
- **TDD is the house rule:** failing test first, watch it fail, implement, watch it pass. Use `superpowers:test-driven-development`.
- **Anchor on snippets, never line numbers** — quote-match the exact code shown in each task; line numbers drift.
- **PROD access is READ-ONLY and bounded (Task 3 only):** reading `\\SYAPP01\D$\sydoc\nexora\var\logs\system\app.log` over SMB and read-only SELECTs against PROD NexoraDB/StatisticsDB (creds parsed from the gitignored `env/PROD.env` on this dev box — the env-var names are `DB_SERVER_PRD`, `DB_UID`, `DB_PWD`, `DB_NEXORA`, `DB_STATISTICS`, verified in `nx_lib/config.py`). NO writes, NO restarts, NO config changes on PROD, and never print/echo credential values.
- **TEST env has NO Statistics DB** (docstring of `tests/e2e/test_dashboard.py`: Statconfig/t_WorkItems tables absent) — the default T-SQL leg cannot be integration-tested against a real DB. New Bug-2 tests are unit tests that monkeypatch the module-level engine bindings **on the view module** (`nx_lib.views.dashboard.engine_nexora_db` / `engine_statistics_db` — the module does `from ..db import ...` at load time, so patching `nx_lib.db` would miss). Route bodies are exercised via `app.test_request_context(...)` + the flask-caching **`.uncached`** attribute on decorated views (bypasses the cache entirely; verified present in the pinned flask-caching 2.3.1, and the four legacy views are module-level with no other decorator). One integration test (Task 6) goes through the real request cycle to prove error responses are not cached — it must call `cache.clear()` first because SimpleCache is process-global and the `app` fixture is session-scoped.
- **Session permissions are rewritten every request** in integration tests: the `before_request` hook `_reload_user_permissions` (`nx_lib/hooks.py`) overwrites `session["permissions"]` via `load_permissions_for_user`. To give a test client `dashboard.filter.process.*` codes, monkeypatch `nx_lib.hooks.load_permissions_for_user` (established precedent: `tests/integration/test_workitems_routes.py`).
- **Jinja template cache:** the dev server caches templates for the process lifetime — restart it (`nx -u`) after editing any template before browser verification. Screenshots go to `var/screenshots/`, never the repo root; if this is a remote session, SendUserFile them unprompted.
- **Migrations: CONDITIONAL.** Only Task 7 creates one, and only if Task 3 lands on branch B (bad PROD Statconfig data). Next free number was **0036** on 2026-07-13 evening — **re-list the directory at execution time** (see concurrent-work note above). Migrations must be idempotent (the pre-commit hook auto-applies them to INT, where the data may already be correct). `*.sql` is pinned to LF by `.gitattributes` — write migration files with the Write tool, not shell heredocs. Data-only migrations don't change the per-object dumps, so `sql-sync-check` stays clean. `SQL_SYNC_SKIP=1 git commit ...` only for INT-unreachable flakes, never `--no-verify`.
- **i18n: NONE.** No task adds a user-facing string (the front-end guard is console-only by design — see Decision 8), so no pybabel cycle. If you deviate and add one, `tests/unit/test_translations.py` hard-fails until you run the full `/nx-i18n` cycle.
- **gitlint:** conventional-commit title ≤72 chars, body required, body lines ≤100 chars.
- **ruff runs at commit** (pre-commit hook; rules E/F/W/I/N/UP/B/SIM/RUF). Leftover unused variables after the Task-5 prunes will fail F841. If the hook's isort autofix reorders a new import block, accept the autofix, `git add` the fixed file, and re-run the commit.
- **Test commands:** `.venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py -q`. The `.venv` is test-only; the dev server runs global Python — irrelevant here (no new runtime deps).
- **No new permission codes, no `page_visibility()` change, no `deploy.yml` exclude change** (all touched runtime paths must deploy; new test files live under `tests/`, already `/XD`-excluded).

---

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| 1 | Bug 1 onclick fix uses the file's own `API_PREFIX` (`'${API_PREFIX}workitems?search=${act.id}'`) | Idiom already defined on line 4 of the same file; `_chat_js.html` renders the identical URL this way. Do NOT "improve" the `includes("nexora")` heuristic in one file only — it's proven across ~20 partials (the hostname `nexora.sydoc.ch` matches too) |
| 2 | Error-page home links become `href="{{ url_for('index') }}"` | Server-rendered; `url_for` respects `SCRIPT_NAME` (the middleware sets it), correct in every environment; the `/` route is registered as endpoint `index` in `nx_lib/views/core.py` |
| 3 | Fix ALL root-relative template URLs now (reporting `api()` helpers ×4, 4 bare fetches, 2 error-page hrefs, prepared-docs fallback), not only the dashboard card | Identical defect class the user just reported, latent-broken on PROD (reporting + prepared-docs pages); lets the lint guard ship allowlist-free; in unprefixed envs `API_PREFIX` is `"/"`, so `API_PREFIX + url.slice(1) === url` — provably zero behavioral change for the whole test suite |
| 4 | Reporting fix goes INSIDE the 4 `api()` helpers (normalize once: `if (url.startsWith('/')) url = API_PREFIX + url.slice(1);`) — the 33 `api('/api/reporting/...')` call sites stay untouched | Minimal churn; each partial is IIFE-wrapped so per-file `API_PREFIX` consts cannot collide |
| 5 | Regression guard = template-lint unit test only (`tests/unit/test_template_url_prefix.py`); NO PrefixMiddleware-wrapped render test, NO new e2e | `PrefixMiddleware` is only wired when `ENVIRONMENT=PROD`, so no test environment can reproduce the 404; the offending URLs live verbatim in template source, so a source lint is the honest, permanent guard |
| 6 | Per-leg isolation via new `_default_stat_rows(sql)` mirroring `_ms02_stat_rows`, applied to **all four** legacy endpoints; no generalized shared helper, no `degraded` response key, no UI banner | The symmetry precedent is already in the file; one dead leg must never blank the other; blast radius is all four endpoints. A degraded-state banner needs an i18n cycle — deferred (Follow-ups) to keep this bugfix-sized |
| 7 | Keep one `UNION ALL` per leg — no per-Statconfig-row isolation | A broken row is a data bug (fixed by migration under branch B); per-row querying multiplies round-trips for no diagnostic gain (the leg logs the full error) |
| 8 | `response_filter=_cacheable_response` on the four cache decorators; the front-end gets a `response.ok` guard in `updateProcessedOverTimeChart` only, console-only | Without the filter a transient 500 is pinned for the TTL per user+filter; the guard keeps the previous chart instead of rendering an undefined-data chart; zero new strings → no i18n cycle |
| 9 | Migration `0036` is written ONLY under diagnosis branch B, guarded on the WRONG value (0031 pattern) so re-apply/INT is a no-op | Pre-commit auto-applies to INT; migrations are the delivery vehicle for PROD data (PROD is read-only for the executor). Number re-verified at execution time — concurrent work consumed 0035 |
| 10 | Diagnosis uses a self-contained pyodbc probe script (parses `env/PROD.env` directly, no `nx_lib` imports, no `ENVIRONMENT` var), time-boxed with an explicit A–E decision tree | `nx_lib` is not installed in the `.venv` and the scratchpad is outside the repo, so an nx_lib-importing script crashes with ModuleNotFoundError; the pyodbc connection string mirrors `nx_lib/db.py get_db_url` (`DRIVER={SQL Server};SERVER=<server>,1433;...`) so it faithfully discriminates connectivity. Every outcome maps to a pre-written task or owner action; if unclassifiable in ~30 min, stop and hand the raw evidence to the owner |

---

## Task 1 — Bug 1: prefix-safe card + error-page links + lint guard v1

**Files:** Create `tests/unit/test_template_url_prefix.py`; Modify `templates/js/_dashboard_js.html`, `templates/handlers/_error_base.html`.

- [ ] **Write the failing lint test.** Create `tests/unit/test_template_url_prefix.py` (new file):

```python
"""Template lint: no root-relative URLs hand-built in templates.

On PROD nexora is served under the /nexora URL prefix — nx_lib/__init__.py
wires PrefixMiddleware(app.wsgi_app, prefix="/nexora") when ENVIRONMENT=PROD.
Server-side url_for() is prefix-aware (the middleware sets SCRIPT_NAME), but a
hand-written root-relative URL in a template escapes the prefix and lands on
the IIS ROOT site (C:\\inetpub\\wwwroot) -> 404.0 StaticFile. The Recent
Validations card shipped exactly that (2026-07-13). No test environment wires
the prefix, so this source lint is the only possible regression guard.

Allowed idioms (never matched below):
- server-rendered: {{ url_for(...) }}  (SCRIPT_NAME-aware)
- client-side:     const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";
                   then `${API_PREFIX}workitems?...` or API_PREFIX + url.slice(1)
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"

BAD_PATTERNS = [
    # JS navigation with a root-relative literal (any quote style);
    # '${API_PREFIX}...', a.url and "{{ url_for(...) }}" values don't match.
    # (?!/) exempts protocol-relative //.
    re.compile(r"location\.href\s*=\s*['\"`]/(?!/)"),
    # literal href/src/action attributes with a root-relative value
    re.compile(r"""\b(?:href|src|action)=["']/(?!/)"""),
]


def _offenders():
    found = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        text = tpl.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rx in BAD_PATTERNS:
                if rx.search(line):
                    found.append(f"{tpl.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    return found


def test_no_root_relative_urls_in_templates():
    offenders = _offenders()
    assert offenders == [], (
        "Root-relative URL(s) escape the /nexora prefix on PROD and 404 on the "
        "IIS root site. Use API_PREFIX (JS partials) or url_for() (Jinja):\n"
        + "\n".join(offenders)
    )
```

- [ ] **Run it — expect FAIL** listing exactly two files: `Run: .venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py -q` → AssertionError naming `templates\js\_dashboard_js.html` (the onclick line matches BOTH patterns — `location.href='/` and `href='/`) and `templates\handlers\_error_base.html` (two `href="/"` hits). If anything ELSE is listed, a new offender landed since 2026-07-13 — fix it the same way, don't allowlist.
- [ ] **Fix the card onclick.** In `templates/js/_dashboard_js.html`, inside `updateActivityFeed()`, change (verbatim anchor):

```
                        onclick="window.location.href='/workitems?search=${act.id}'">
```

to:

```
                        onclick="window.location.href='${API_PREFIX}workitems?search=${act.id}'">
```

(The card markup is a JS template literal, so `${API_PREFIX}` interpolates the file's own line-4 const. `API_PREFIX` ends with `/`, so this yields `/workitems?...` in dev and `/nexora/workitems?...` on PROD — same shape as `_chat_js.html`'s `` const url = `${API_PREFIX}workitems?search=${id}`; ``.)
- [ ] **Fix the error-page home links.** In `templates/handlers/_error_base.html`, change both anchors:

```
            <a href="/" class="brand-mark" data-testid="error-{{ error_code }}-brand-home">
```

→ `<a href="{{ url_for('index') }}" class="brand-mark" data-testid="error-{{ error_code }}-brand-home">`, and

```
                    <a href="/" class="btn-cosmic btn-cosmic-primary" data-testid="error-{{ error_code }}-home">
```

→ `<a href="{{ url_for('index') }}" class="btn-cosmic btn-cosmic-primary" data-testid="error-{{ error_code }}-home">`.
- [ ] **Run green:** `.venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py tests/integration/test_dashboard_routes.py -q` → all pass. Also run whatever error-handler integration tests exist to prove the template still renders: `.venv\Scripts\python -m pytest tests/integration -k "403 or 404 or 500 or error" -q` (zero failures expected).
- [ ] **Commit** (explicit paths only — the tree may hold unrelated concurrent work):

```bash
git add tests/unit/test_template_url_prefix.py templates/js/_dashboard_js.html templates/handlers/_error_base.html
git commit -m "fix(dashboard): route Recent Validations card through API_PREFIX

The activity-feed card onclick used a root-relative /workitems?search=<id>
URL. On PROD the app lives under the /nexora prefix (PrefixMiddleware,
wired only when ENVIRONMENT=PROD), so the click escaped the app and hit
the IIS ROOT site -> 404.0 StaticFile (C:\inetpub\wwwroot\workitems).
Dev/tests run unprefixed, which is why every test passed. Also fixes the
error pages' two home links (href=\"/\" -> url_for('index')). New
template-lint unit test permanently blocks root-relative navigation URLs."
```

## Task 2 — Sweep the remaining prefix escapes (reporting, prepared docs) + lint v2

**Files:** Modify `tests/unit/test_template_url_prefix.py`, `templates/js/_reporting_js.html`, `templates/js/_reporting_simple_js.html`, `templates/js/_reporting_sources_js.html`, `templates/js/_reporting_metrics_js.html`, `templates/js/_reporting_ai_js.html`, `templates/js/_prepared_documents_js.html`.

Verified violation inventory (2026-07-13): 33× `api('/api/reporting/...')` across `_reporting_js.html` (21) / `_reporting_simple_js.html` (8) / `_reporting_metrics_js.html` (2) / `_reporting_sources_js.html` (2); 3× `fetch("/api/reporting/ai/...` in `_reporting_ai_js.html`; 1× `fetch('/api/reporting/export', {` in `_reporting_simple_js.html`; and `const API_PREFIX = window.API_PREFIX || "/";` in `_prepared_documents_js.html` (`window.API_PREFIX` is assigned nowhere, so that page's fetches fall back to bare `/` — prefix-broken on PROD).

- [ ] **Extend the lint (failing first):** in `tests/unit/test_template_url_prefix.py`, append two patterns to `BAD_PATTERNS`:

```python
    # Direct fetch of a root-relative literal.
    re.compile(r"""\bfetch\(\s*['\"`]/(?!/)"""),
    # A bare-"/" API_PREFIX fallback silently breaks under the PROD prefix.
    re.compile(r"""window\.API_PREFIX\s*\|\|\s*["']/["']"""),
]
```

- [ ] **Run — expect FAIL** listing exactly 5 offender lines: `_reporting_ai_js.html` ×3, `_reporting_simple_js.html` ×1 (the export fetch), `_prepared_documents_js.html` ×1 (the fallback). The 33 `api('...')` call sites are deliberately NOT matched — they are made safe inside the helpers in the next step, so the literal call sites become safe.
- [ ] **Fix the four `api()` helpers.** In each of `_reporting_js.html`, `_reporting_sources_js.html`, `_reporting_metrics_js.html`: directly under the file's `const csrf = document.querySelector('meta[name="csrf-token"]').content;` line add

```js
  const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";
```

and change the helper opening (anchor, identical in all three):

```js
  async function api(url, opts) {
    opts = opts || {};
```

to:

```js
  async function api(url, opts) {
    if (url.startsWith('/')) url = API_PREFIX + url.slice(1);
    opts = opts || {};
```

In `_reporting_simple_js.html` (var-style file): under `var csrf = document.querySelector('meta[name="csrf-token"]').content;` add `var API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";`, apply the same `if (url.startsWith('/')) ...` first line to its `async function api(url, opts) {` / `opts = opts || {};` helper, and change the export fetch anchor `res = await fetch('/api/reporting/export', {` to `res = await fetch(API_PREFIX + 'api/reporting/export', {`.
- [ ] **Fix `_reporting_ai_js.html`:** directly under its `"use strict";` line add `var API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";`, then change the three fetch anchors `fetch("/api/reporting/ai/build", {` / `fetch("/api/reporting/ai/ask", {` / `fetch("/api/reporting/ai/agent", {` to `fetch(API_PREFIX + "api/reporting/ai/build", {` (etc.).
- [ ] **Fix `templates/js/_prepared_documents_js.html`:** replace its anchor `const API_PREFIX = window.API_PREFIX || "/";` with the standard heuristic `const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";`.
- [ ] **Run green:** `.venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py -q` → 1 passed. In unprefixed dev `API_PREFIX` is `"/"`, so `API_PREFIX + url.slice(1) === url` — zero behavioral change for the entire test suite; the reporting e2e tier stays owner-run at pre-push.
- [ ] **Browser smoke (dev):** restart the dev server (`nx -u -b --loginas:ben.streich` — templates are process-lifetime cached), open Reporting → run any saved simple report — no console 404s. Screenshot to `var/screenshots/dashboard-404-chart-00-reporting-smoke.png`; if remote, SendUserFile it.
- [ ] **Commit:**

```bash
git add tests/unit/test_template_url_prefix.py templates/js/_reporting_js.html templates/js/_reporting_simple_js.html templates/js/_reporting_sources_js.html templates/js/_reporting_metrics_js.html templates/js/_reporting_ai_js.html templates/js/_prepared_documents_js.html
git commit -m "fix(templates): sweep remaining root-relative URLs behind the prefix

Same defect class as the Recent Validations 404: root-relative URLs
escape the /nexora PROD prefix. Fixed: the four reporting api() helpers
now normalize '/...' through API_PREFIX (33 call sites unchanged), the
three AI fetches and the export fetch, and the prepared-documents
API_PREFIX fallback (window.API_PREFIX is never assigned, so it fell
back to bare '/'). Lint extended to fetch() literals and the bare-'/'
fallback pattern; ships allowlist-free. In unprefixed environments
API_PREFIX is '/', so behavior is provably identical there."
```

## Task 3 — Bug 2: bounded read-only PROD diagnosis (decision tree A–E)

**Files:** none in the repo except recording the result (script lives in your scratchpad). READ-ONLY on PROD. Time-box: ~30 minutes; if the evidence doesn't classify into A–E, stop and hand the raw output to the owner.

- [ ] **Read the PROD error lines** (SMB, read-only, tail-bounded):

```powershell
Get-Content '\\SYAPP01\D$\sydoc\nexora\var\logs\system\app.log' -Tail 5000 |
  Select-String 'Failed to fetch processed_over_time report:|Failed to fetch kpi_stats report:|Failed to fetch hourly_stats:|Failed to fetch avg_processing_time:|ms02 dashboard stats query failed:' |
  Select-Object -Last 60
```

Record the exact exception texts and their timestamps (recent vs old matters for branch E). If nothing matches in the tail, widen with a full-file `Select-String` on the same path.
- [ ] **Write the probe script** to `<your scratchpad>\diag_statconfig.py` (NEVER inside the repo; it reads `env/PROD.env` but prints no secrets — only the server hostname, DB names, Statconfig values and probe results). It is fully self-contained: it does NOT import `nx_lib` (which is not installed in the `.venv`), and its connection string mirrors `nx_lib/db.py get_db_url` (`DRIVER={SQL Server};SERVER=<server>,1433;...`) so a connectivity failure here faithfully reproduces the app's:

```python
"""READ-ONLY dashboard-stats diagnosis (Bug 2). SELECT-only; prints no secrets.
Usage:  C:\\dev\\nexora\\.venv\\Scripts\\python.exe diag_statconfig.py PROD
        (run with INT too, for comparison)
"""

import sys
from pathlib import Path

import pyodbc

ENV = sys.argv[1] if len(sys.argv) > 1 else "PROD"
env = {}
for line in (Path(r"C:\dev\nexora\env") / f"{ENV}.env").read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

SERVER = env["DB_SERVER_PRD"]
DBS = env["DB_STATISTICS"]


def connect(db):
    return pyodbc.connect(
        f"DRIVER={{SQL Server}};SERVER={SERVER},1433;DATABASE={db};"
        f"UID={env['DB_UID']};PWD={env['DB_PWD']};",
        timeout=5,
    )


print(f"[{ENV}] server={SERVER} nexora={env['DB_NEXORA']} stats={DBS}")

# 0) connectivity probe (branch A discriminator)
try:
    with connect(DBS) as c:
        c.cursor().execute("SELECT 1").fetchone()
    print("StatisticsDB connect: OK")
except Exception as e:
    print(f"StatisticsDB connect: FAIL {type(e).__name__}: {str(e)[:300]}")

# 1) all Statconfig rows (branch B evidence; also shows additionalCondition values)
with connect(env["DB_NEXORA"]) as c:
    rows = c.cursor().execute(
        "SELECT ProcessName, TableName, ExportColumn, ImportColumn, "
        "additionalCondition, ClientCode FROM dbo.Statconfig"
    ).fetchall()
for r in rows:
    print("CFG", tuple(r))

# 2) run the EXACT per-row sub-query dashboard_processed_over_time builds
for r in rows:
    if (r.ClientCode or "default") == "ms02":
        continue
    convert = "convert" in str(r.ExportColumn).lower()
    date_col = f"CAST({r.ExportColumn} AS DATE)" if not convert else r.ExportColumn
    condition = f" {r.additionalCondition}" if r.additionalCondition else ""
    sql = (
        f"SELECT {date_col} as d, COUNT(*) as c FROM [{DBS}].{r.TableName} "
        f"WHERE {r.ExportColumn} >= DATEADD(day, -14, GETDATE()) {condition} "
        f"GROUP BY {date_col}"
    )
    try:
        with connect(DBS) as c:
            out = c.cursor().execute(sql).fetchall()
        total = sum(x[1] for x in out)
        print(f"OK   {r.ProcessName}: {len(out)} day-buckets, {total} rows in 14d window")
        with connect(DBS) as c:
            mx = c.cursor().execute(f"SELECT MAX({r.ExportColumn}) FROM [{DBS}].{r.TableName}").fetchone()
        print(f"     MAX({r.ExportColumn}) = {mx[0]}")
    except Exception as e:
        print(f"FAIL {r.ProcessName}: {type(e).__name__}: {str(e)[:300]}")
        print(f"     SQL: {sql}")
```

- [ ] **Run it against PROD, then against INT for comparison:** `C:\dev\nexora\.venv\Scripts\python.exe <scratchpad>\diag_statconfig.py PROD` and `... INT`. (The `.venv` has pyodbc. The INT comparison tells you regression-vs-longstanding and whether a branch-B migration would need to touch INT too.) Also eyeball each `additionalCondition` value: does it start with `AND`/`OR`? Does any value reference post-0032 state?
- [ ] **Classify with this decision tree** (multiple branches can hold at once — apply per row; record verdict + key evidence lines):

| Evidence | Branch | Action |
|---|---|---|
| Step-0 connect FAILs and/or app.log shows login/connect/timeout errors (e.g. `Login failed`, `Unable to connect`, `Communication link failure`) — note: if the dev-box probe succeeds but app.log shows connection errors, the break is SYAPP01-side | **A — StatisticsDB connectivity/creds** | Owner action O2 (infra/creds on SYAPP01; executor cannot touch PROD config). Tasks 4–6 still ship: PDBS + backlog keep rendering while StatisticsDB is down |
| Step-2 FAILs with `Invalid object name` / `Invalid column name` on specific rows, i.e. a **stored Statconfig value** points at a dead object, OR a bad/bare `additionalCondition` value breaks the SQL (`Incorrect syntax near ...` where the stored value violates the `AND <predicate>` contract), OR rows are missing for known default processes | **B — stale/wrong PROD Statconfig data** | Task 7: corrective idempotent migration `0036`, values copied from the FAIL lines |
| Step-2 FAILs with a syntax error caused by the ROUTE'S string-building against a **legitimate** stored value (e.g. a TableName that needs bracketing: space, reserved word) | **C — SQL-construction bug** | Task 8: reproduce-first code fix + unit test |
| All step-2 probes OK but `0 rows in 14d window` everywhere and `MAX(ExportColumn)` is stale (days/weeks old) | **D — upstream ingest dead** (StatisticsDB no longer being fed) | Owner action O3 (ops: `ops/cleanup/csvLogs_toDB.ps1` ingest / Octo-side export jobs — outside this repo). Chart legitimately shows zeros; Tasks 4–6 still ship |
| Step-2 probes OK **with** recent rows, and the app.log errors are old/sporadic | **E — transient outage whose 500s were pinned by the cache** | Task 6 (`response_filter`) is the fix; Tasks 4–5 remove the 500s at the source. Verify post-deploy (owner action O1) |

- [ ] **Record the result:** append a `## Diagnosis result (2026-07-13)` section to THIS plan file (`docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md`) — the secret-free app.log error line(s), the Statconfig row table, each probe verdict, and the chosen branch(es). Commit:

```bash
git add docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md
git commit -m "docs(plan): record PROD dashboard-stats diagnosis result

Read-only diagnosis per plan Task 3: app.log error lines, PROD Statconfig
rows, per-row chart-subquery probe results, and the selected decision
branch. No PROD state was modified."
```

## Task 4 — `_default_stat_rows` helper + isolate `dashboard_processed_over_time`

**Files:** Modify `nx_lib/views/dashboard.py`, `tests/unit/test_dashboard_stats.py`.

- [ ] **Write the failing tests.** In `tests/unit/test_dashboard_stats.py`, extend the import block at the top of the file (it currently has `import types` and `from nx_lib.views.dashboard import _ms02_source, _split_stat_configs`) to:

```python
import types
from datetime import date
from unittest.mock import MagicMock

from flask import session

import nx_lib.views.dashboard as dv
from nx_lib.views.dashboard import _ms02_source, _split_stat_configs
```

(If the pre-commit ruff hook reorders these, accept its autofix.) Then append this new section at the end of the file:

```python
# ------------------- per-leg isolation (default T-SQL leg) ------------------- #
# The existing _row helper deliberately lacks additionalCondition; the route
# reads it, so config-row fakes for route-level tests need their own shape.


def _cfg_row(client, name, table, exp, imp, cond=None):
    return types.SimpleNamespace(
        ClientCode=client,
        ProcessName=name,
        TableName=table,
        ExportColumn=exp,
        ImportColumn=imp,
        additionalCondition=cond,
    )


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


_PERMS = [
    "dashboard.filter.process.sydoc.Alpha",
    "dashboard.filter.process.sydoc.05_PDBS",
]

_CONFIGS = [
    _cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate"),
    _cfg_row("ms02", "sydoc.05_PDBS", 'public."DossierStatistik"', "DatumInTempExport", "ImportDate"),
]


def test_default_stat_rows_returns_rows(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(1,)]))
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == [(1,)]


def test_default_stat_rows_swallows_and_logs_errors(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == []


def test_processed_over_time_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    today = date.today()
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(today, 7)])

    with app.test_request_context("/api/dashboard/processed_over_time"):
        session["username"] = "u"
        session["userid"] = 990001
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_processed_over_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    body = resp.get_json()
    assert max(body["data"]) == 7  # the healthy MS02 leg still renders


def test_processed_over_time_default_leg_survives_dead_ms02(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    today = date.today()
    monkeypatch.setattr(
        dv,
        "engine_statistics_db",
        _engine_returning([types.SimpleNamespace(d=today, total_count=5)]),
    )
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [])  # PG leg's existing degrade contract

    with app.test_request_context("/api/dashboard/processed_over_time"):
        session["username"] = "u"
        session["userid"] = 990002
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_processed_over_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert max(resp.get_json()["data"]) == 5
```

- [ ] **Run — expect FAIL:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py -q` → the two helper tests fail with `AttributeError: module 'nx_lib.views.dashboard' has no attribute '_default_stat_rows'`; `test_processed_over_time_serves_ms02_when_statistics_db_dead` fails with `assert 500 == 200` (today the dead default leg 500s the whole endpoint — the bug in miniature).
- [ ] **Implement the helper.** In `nx_lib/views/dashboard.py`, directly below the whole `_ms02_stat_rows` function (its closing lines are `current_app.logger.error(f"ms02 dashboard stats query failed: {e}")` / `return []`) and above the `DASHBOARD_LAYOUT_SCHEMA_VERSION = 1` constant, add:

```python
def _default_stat_rows(sql):
    """Run a read-only query on the default StatisticsDB engine; return rows,
    or [] if the server is unreachable or the query errors (e.g. a stale
    Statconfig row pointing at a dropped table). Mirror of _ms02_stat_rows for
    the T-SQL leg: a default-leg failure must never blank the MS02 numbers —
    log and yield no rows so each leg degrades independently."""
    try:
        conn = engine_statistics_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"default dashboard stats query failed: {e}")
        return []
```

- [ ] **Refactor `dashboard_processed_over_time`.** Two edits inside the function:
  1. After the Statconfig read (anchor: `configs = cursor.fetchall()` followed by `cursor.close()` and `conn.close()`), add `conn = None` on the next line — without it, the route's `finally: if conn: conn.close()` would re-close the already-closed NexoraDB connection once the stats block below stops reassigning `conn`.
  2. Replace the inline StatisticsDB block —

```python
            conn = engine_statistics_db.raw_connection()
            cursor = conn.cursor()
            cursor.execute(full_query)
            for row in cursor.fetchall():
                counts[row.d] = counts.get(row.d, 0) + row.total_count
            cursor.close()
            conn.close()
            conn = None
```

with:

```python
            for row in _default_stat_rows(full_query):
                counts[row.d] = counts.get(row.d, 0) + row.total_count
```

- [ ] **Run green:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py -q` → all pass (the integration file's early-empty paths are untouched).
- [ ] **Commit** (paste the Task 3 verdict line into the body where indicated):

```bash
git add nx_lib/views/dashboard.py tests/unit/test_dashboard_stats.py
git commit -m "fix(dashboard): isolate default T-SQL leg in processed_over_time

A default-leg failure (dead Statconfig table, StatisticsDB outage, bad
condition SQL) 500'd the whole endpoint before the healthy MS02 leg ran,
blanking the over-time chart for every non-PDBS process on PROD while
PDBS (zero default rows -> leg skipped) kept working. New
_default_stat_rows mirrors _ms02_stat_rows: log + degrade to zero rows.
PROD diagnosis 2026-07-13: <one-line branch verdict + key error text>."
```

## Task 5 — Same isolation for the three sibling endpoints

**Files:** Modify `nx_lib/views/dashboard.py`, `tests/unit/test_dashboard_stats.py`.

- [ ] **Write the failing tests** (append to the Task-4 section of `tests/unit/test_dashboard_stats.py`):

```python
def test_kpi_stats_serves_ms02_and_backlog_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    monkeypatch.setattr(dv, "total_backlog_count", lambda procs, clients: 3)

    with app.test_request_context("/api/dashboard/kpi_stats"):
        session["username"] = "u"
        session["userid"] = 990003
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_kpi_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert resp.get_json() == {"processed_today": 5, "imported_today": 2, "current_backlog": 3}


def test_hourly_stats_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(9, 4)])

    with app.test_request_context("/api/dashboard/hourly_stats"):
        session["username"] = "u"
        session["userid"] = 990004
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_hourly_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    body = resp.get_json()
    assert body["data"][9] == 4
    assert sum(body["data"]) == 4


def test_avg_processing_time_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(120.0,)])

    with app.test_request_context("/api/dashboard/avg_processing_time"):
        session["username"] = "u"
        session["userid"] = 990005
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_avg_processing_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert resp.get_json()["avg_display"] == "2min"
```

- [ ] **Run — expect FAIL:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py -q` → the three new tests fail with `assert 500 == 200`.
- [ ] **Refactor `dashboard_kpi_stats`:** replace its inline stats block —

```python
                conn_stat = engine_statistics_db.raw_connection()
                cursor_stat = conn_stat.cursor()
                cursor_stat.execute(full_stat_query)
                row = cursor_stat.fetchone()
                if row:
                    processed_today += row[0] or 0
                    imported_today += row[1] or 0
```

with:

```python
                srows = _default_stat_rows(full_stat_query)
                if srows:
                    processed_today += srows[0][0] or 0
                    imported_today += srows[0][1] or 0
```

then delete the now-dead `conn_stat = None` / `cursor_stat = None` declarations (anchor: the four-line block `conn_nex = None` / `conn_stat = None` / `cursor_nex = None` / `cursor_stat = None` — keep the `conn_nex`/`cursor_nex` lines) and remove the `if cursor_stat:` / `if conn_stat:` close pairs from its `finally:` block (keep the `cursor_nex`/`conn_nex` pairs). Leftover unused declarations fail ruff F841 at commit.
- [ ] **Refactor `dashboard_hourly_stats`:** replace —

```python
            conn_stat = engine_statistics_db.raw_connection()
            cursor_stat = conn_stat.cursor()
            cursor_stat.execute(full_query)
            for row in cursor_stat.fetchall():
                hourly[row.h] = hourly.get(row.h, 0) + row.total
```

with:

```python
            for row in _default_stat_rows(full_query):
                hourly[row.h] = hourly.get(row.h, 0) + row.total
```

and prune its `conn_stat`/`cursor_stat` declarations + `finally:` lines the same way.
- [ ] **Refactor `dashboard_avg_processing_time`:** replace —

```python
            conn_stat = engine_statistics_db.raw_connection()
            cursor_stat = conn_stat.cursor()
            cursor_stat.execute(full_query)
            row = cursor_stat.fetchone()
            if row and row[0] is not None:
                avg_values.append(row[0])
```

with:

```python
            srows = _default_stat_rows(full_query)
            if srows and srows[0][0] is not None:
                avg_values.append(srows[0][0])
```

and prune its `conn_stat`/`cursor_stat` declarations + `finally:` lines the same way.
- [ ] **Run green:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py -q` → all pass.
- [ ] **Commit:**

```bash
git add nx_lib/views/dashboard.py tests/unit/test_dashboard_stats.py
git commit -m "fix(dashboard): per-leg isolation for kpi/hourly/avg endpoints

Same single-try asymmetry as processed_over_time: a StatisticsDB failure
500'd each endpoint wholesale, zeroing the KPI cards (incl. the backlog
number, which never touches StatisticsDB), the hourly chart and the avg
card for every non-PDBS scope. All three now route their default T-SQL
leg through _default_stat_rows and degrade per leg."
```

## Task 6 — Never cache error responses + front-end non-OK guard

**Files:** Modify `nx_lib/views/dashboard.py`, `templates/js/_dashboard_js.html`, `tests/unit/test_dashboard_stats.py`, `tests/integration/test_dashboard_routes.py`.

- [ ] **Write the failing unit test** (append to `tests/unit/test_dashboard_stats.py`):

```python
def test_cacheable_response_rejects_error_statuses():
    ok_resp = types.SimpleNamespace(status_code=200)
    assert dv._cacheable_response(ok_resp)
    assert dv._cacheable_response((ok_resp, 200))
    assert not dv._cacheable_response(("body", 500))
    assert not dv._cacheable_response(("body", 401))
```

- [ ] **Write the failing integration test.** `tests/integration/test_dashboard_routes.py` currently has NO imports (docstring, then fixture-only tests). Add this import block directly after the module docstring — at the TOP of the file, never mid-file (ruff E402/I run at commit; accept the hook's autofix if it reorders):

```python
from unittest.mock import MagicMock

from nx_lib.extensions import cache
import nx_lib.hooks
import nx_lib.views.dashboard as dv
```

Then append at the end of the file:

```python
# --------------------- error responses must not be cached ------------------- #
# TEST has no Statistics DB, so engines are mocked on the VIEW module (it
# does `from ..db import ...` at load time). Session permissions are
# rewritten every request by _reload_user_permissions (nx_lib/hooks.py), so
# we patch nx_lib.hooks.load_permissions_for_user (precedent:
# tests/integration/test_workitems_routes.py). SimpleCache is process-global
# and the app fixture is session-scoped -> cache.clear() first, always.


class _BoomEngine:
    def raw_connection(self):
        raise RuntimeError("nexora db hiccup")


def _fake_nexora_engine(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


def test_processed_over_time_error_response_is_not_cached(user_client, monkeypatch):
    """A transient 500 (Statconfig read on NexoraDB fails) must not be pinned
    in the 300s response cache: the next request re-executes the view."""
    cache.clear()
    monkeypatch.setattr(
        nx_lib.hooks,
        "load_permissions_for_user",
        lambda uid: ["dashboard.view", "dashboard.filter.process.sydoc.TestProc"],
    )

    monkeypatch.setattr(dv, "engine_nexora_db", _BoomEngine())
    resp = user_client.get("/api/dashboard/processed_over_time")
    assert resp.status_code == 500

    monkeypatch.setattr(dv, "engine_nexora_db", _fake_nexora_engine([]))
    resp2 = user_client.get("/api/dashboard/processed_over_time")
    assert resp2.status_code == 200
    assert resp2.get_json() == {"labels": [], "data": []}
```

- [ ] **Run — expect FAIL:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py::test_cacheable_response_rejects_error_statuses tests/integration/test_dashboard_routes.py::test_processed_over_time_error_response_is_not_cached -q` → the unit test fails with `AttributeError: ... has no attribute '_cacheable_response'`; the integration test fails on the second request (`assert 500 == 200` on `resp2` — the cached 500 is served).
- [ ] **Implement.** In `nx_lib/views/dashboard.py`, directly below `make_cache_key` (anchor: `return f"{request.path}_{session.get('userid')}_{session.get('process_name_dashboard', 'all')}"`), add:

```python
def _cacheable_response(rv):
    """response_filter for @cache.cached on the four legacy KPI endpoints:
    never pin an error response — a transient 500 would otherwise be served
    for the full TTL per user+filter, stretching outages and confusing
    diagnosis."""
    status = rv[1] if isinstance(rv, tuple) and len(rv) == 2 else getattr(rv, "status_code", 200)
    return status < 400
```

- [ ] **Wire it into the four decorators** (ONLY these four — leave `dash_fieldmeta` and `recent_activity` alone):
  - `@cache.cached(timeout=300, key_prefix=make_cache_key)` (on `dashboard_processed_over_time`) → `@cache.cached(timeout=300, key_prefix=make_cache_key, response_filter=_cacheable_response)`
  - the `timeout=60` decorator with `key_prefix=lambda: f"kpi_stats_{...}"` on `dashboard_kpi_stats` — add `response_filter=_cacheable_response,` after the `key_prefix` line
  - the `timeout=120` / `key_prefix=lambda: f"hourly_stats_{...}"` decorator on `dashboard_hourly_stats` — same addition
  - the `timeout=300` / `key_prefix=lambda: f"avg_proc_time_{...}"` decorator on `dashboard_avg_processing_time` — same addition
- [ ] **Front-end guard.** In `templates/js/_dashboard_js.html`, inside `updateProcessedOverTimeChart()` (unique anchor: `const url = buildApiUrl('api/dashboard/processed_over_time');`), between the fetch block's closing `}});` and `const data = await response.json();`, insert:

```js
            if (!response.ok) {
                console.error("processed_over_time HTTP", response.status);
                return;
            }
```

(Keeps the previously rendered chart instead of feeding `undefined` labels/data into Chart.js; console-only on purpose — no new user-facing string, no i18n cycle.)
- [ ] **Run green:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py tests/unit/test_template_url_prefix.py -q` → all pass (the lint test confirms the template edit introduced no root-relative URL).
- [ ] **Commit:**

```bash
git add nx_lib/views/dashboard.py templates/js/_dashboard_js.html tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py
git commit -m "fix(dashboard): stop caching error responses; guard chart fetch

Flask-Caching pinned whatever the four legacy KPI views returned --
including (jsonify error, 500) tuples -- for 60-300s per user+filter,
so one transient failure blanked the dashboard for minutes. New
_cacheable_response response_filter skips caching any status >= 400
(proven end-to-end by a new integration test). The over-time chart
updater now bails on non-OK responses instead of rendering a Chart.js
dataset from an error payload."
```

## Task 7 — CONDITIONAL (diagnosis branch B only): corrective Statconfig migration

**Files:** Create `sql/_migrations/NexoraDB/0036_fix_statconfig_default_rows.sql`. **Skip this task entirely unless Task 3 produced branch-B evidence** (a `FAIL <ProcessName>: ... Invalid object name/Invalid column name/Incorrect syntax ...` line traced to a stored value, or a missing row). Every angle-bracket token below is copied 1:1 from a Task 3 `CFG`/`FAIL` output line — they are diagnosis parameters, not blanks to invent.

- [ ] **Re-list `sql/_migrations/NexoraDB/`** — `0036` was the next free number on 2026-07-13 evening, but the concurrent docfield effort may have consumed it; use the actual next free number and adjust the filename/commit accordingly.
- [ ] Create `sql/_migrations/NexoraDB/0036_fix_statconfig_default_rows.sql` **with the Write tool** (LF endings — `*.sql` is pinned in `.gitattributes`), following the `0031_fix_ms02_statconfig_dossierstatistik.sql` pattern — each statement keyed on the WRONG value so re-apply (and INT, if INT's data is already correct per the Task 3 INT run) is a no-op:

```sql
-- 0036_fix_statconfig_default_rows.sql
-- The dashboard's default (StatisticsDB/T-SQL) leg failed on PROD because
-- <one sentence: the exact defect Task 3 proved, e.g. "the sydoc.Xyz row's
-- TableName points at dbo.OldTable, dropped upstream">. Diagnosed 2026-07-13
-- (plan 2026-07-13-dashboard-chart-recent-validations-404.md, Task 3).
-- Data only (no DDL -> per-object dumps unchanged). Idempotent: each UPDATE
-- is keyed on the WRONG value (0031 pattern), so re-running -- or running on
-- an environment whose data is already correct -- is a no-op.

UPDATE dbo.Statconfig
SET TableName    = '<correct TableName from Task 3 evidence>',
    ExportColumn = '<correct ExportColumn from Task 3 evidence>'
WHERE ProcessName = '<affected ProcessName>'
  AND TableName   = '<current broken TableName>';
GO
```

Repeat the guarded `UPDATE` block once per broken row. If a row is broken because its `additionalCondition` violates the `AND <predicate>` contract or references dead state, `SET additionalCondition = '<corrected condition>'` (or `NULL`) with the same wrong-value `WHERE`. For a missing row, use the `0025` insert-if-missing idiom (`IF NOT EXISTS (SELECT 1 FROM dbo.Statconfig WHERE ProcessName = '...') INSERT INTO dbo.Statconfig (ProcessName, TableName, ExportColumn, additionalCondition, ImportColumn, WorkitemColumn, ClientCode) VALUES (...);`). Never use unguarded blanket UPDATEs.
- [ ] After commit (the pre-commit hook auto-applies the migration to INT — the guards make it a no-op there if INT is already correct), re-run the Task 3 probe script's step-2 loop against **INT**: every default row prints `OK`.
- [ ] **Commit:**

```bash
git add sql/_migrations/NexoraDB/0036_fix_statconfig_default_rows.sql
git commit -m "fix(db): repair stale Statconfig default rows (0036)

<ProcessName(s)> pointed at <broken value(s)>, so the dashboard's default
T-SQL leg raised on every request and (pre-isolation) 500'd all four KPI
endpoints for non-PDBS scopes on PROD. Guarded on the wrong value per the
0031 pattern -> no-op wherever the data is already correct. Reaches PROD
via the next deploy (migrations run before app-pool stop)."
```

## Task 8 — CONDITIONAL (diagnosis branch C only): SQL-builder fix (reproduce-first)

**Files:** Modify `nx_lib/views/dashboard.py`, `tests/unit/test_dashboard_stats.py`. **Skip unless Task 3 proved the route's string-building breaks a legitimate stored value.** Rule: no fix without a failing string-level unit test that reproduces the exact SQL the route builds from the offending row (construct the row with `_cfg_row(...)` values copied from the diagnosis).

The most likely defect shape — an unbracketed `TableName` (space/reserved word) — has a pre-written fix; if the actual defect differs, follow the same TDD shape with the real cause.

- [ ] **Failing test first** (append to `tests/unit/test_dashboard_stats.py`):

```python
def test_bracket_tsql_name_quotes_each_part():
    assert dv._bracket_tsql_name("dbo.My Table") == "[dbo].[My Table]"
    assert dv._bracket_tsql_name("dbo.tblAlpha") == "[dbo].[tblAlpha]"
    assert dv._bracket_tsql_name("[dbo].[Already]") == "[dbo].[Already]"
```

Run: `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py::test_bracket_tsql_name_quotes_each_part -q` → `AttributeError`.
- [ ] **Implement** in `nx_lib/views/dashboard.py`, next to `_default_stat_rows`:

```python
def _bracket_tsql_name(name):
    """Bracket a possibly schema-qualified T-SQL object name coming from
    dbo.Statconfig (e.g. 'dbo.My Table' -> '[dbo].[My Table]'). Parts that
    are already bracketed pass through unchanged."""
    out = []
    for p in str(name).split("."):
        if p.startswith("[") and p.endswith("]"):
            out.append(p)
        else:
            out.append("[" + p.replace("]", "]]") + "]")
    return ".".join(out)
```

- [ ] Apply at all four build sites: change every `FROM [{DB_STATISTICS}].{row.TableName}` occurrence (one each in `dashboard_processed_over_time`, `dashboard_kpi_stats`, `dashboard_hourly_stats`, `dashboard_avg_processing_time`) to `FROM [{DB_STATISTICS}].{_bracket_tsql_name(row.TableName)}`. Do NOT touch the widget engine (`build_widget_query` and its `_build_*_sql` helpers — dormant) or MS02 paths.
- [ ] **Run green:** `.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py -q`.
- [ ] **Commit:** test + fix together, `fix(dashboard): <specific cause from diagnosis>` with a body quoting the PROD error text.

## Task 9 — Changelog + stale-doc fix

**Files:** Modify `CHANGELOG.md`, `CLAUDE.md`. Both files are merge-conflict surface with the concurrent docfield effort — anchor on the section headings, append at the END of the subsection, and re-read the current file state before editing.

- [ ] In `CHANGELOG.md`, under `## [Unreleased]` → the `### Fixed` heading, append at the end of that subsection (after whatever bullets are there at execution time):

```markdown
- Dashboard: clicking a Recent Validations card on PROD landed on the IIS root site's 404
  page — the card's onclick built a root-relative `/workitems?search=<id>` URL that escaped
  the `/nexora` prefix. Fixed via the page's `API_PREFIX` idiom; the error pages' two "home"
  links now use `url_for('index')`. The same sweep fixed latent prefix escapes in the four
  reporting `api()` helpers, the reporting AI/export fetches, and the prepared-documents
  partial (`window.API_PREFIX` was never assigned). A new template-lint test
  (`tests/unit/test_template_url_prefix.py`) permanently forbids root-relative URLs in
  templates.
- Dashboard: a failing StatisticsDB (T-SQL) leg 500'd all four legacy KPI/chart endpoints —
  including the healthy MS02/Postgres numbers and the backlog count — which blanked the
  "Documents Processed over time" chart (and KPI cards) for every non-PDBS process on PROD
  while PDBS kept working. The default leg is now isolated like the MS02 leg already was
  (`_default_stat_rows`): each leg logs and degrades to zero rows. Error responses are no
  longer pinned in the per-user response cache, and the chart updater skips non-OK payloads.
```

(If Task 7 and/or 8 ran, extend the second bullet with one clause naming the corrective migration / the TableName bracketing respectively.)
- [ ] In `CLAUDE.md` (repo root), replace the stale Architectural-conventions bullet —

```markdown
- **Prefix middleware:** `PrefixMiddleware` exists for deploying under a URL prefix; it's defined but only wired up when needed.
```

with:

```markdown
- **Prefix middleware / PROD URL prefix:** PROD serves the app under `/nexora` — `nx_lib/__init__.py` wires `PrefixMiddleware(app.wsgi_app, prefix="/nexora")` whenever `ENVIRONMENT=PROD`. Server-side `url_for()` is prefix-correct (the middleware sets `SCRIPT_NAME`), but hand-built URLs in JS partials must use the `API_PREFIX` idiom (`const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";`); root-relative literals escape the prefix and 404 on the IIS root site. Dev/INT/tests run unprefixed. Enforced by `tests/unit/test_template_url_prefix.py` (note: it does not match `api('/api/...')` call sites — a new partial's `api()` helper must normalize through `API_PREFIX` itself).
```

- [ ] **Commit:**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -m "docs: changelog for dashboard fixes + correct PrefixMiddleware note

CLAUDE.md claimed PrefixMiddleware is 'only wired up when needed' -- it is
unconditionally active on PROD with prefix /nexora, which is plausibly why
a root-relative link shipped unnoticed. The bullet now states the PROD
prefix reality and the API_PREFIX convention the lint test enforces."
```

## Task 10 — Live verification on INT (browser, self-driven)

No commit; evidence only. INT has a real Statistics DB, so the default leg renders real data here.

- [ ] Restart the dev server fresh (clears both the Jinja template cache and the SimpleCache): `nx -u -b --loginas:ben.streich`.
- [ ] Dashboard: with the process filter on **All Processes** and then on a non-PDBS process, the "Documents Processed over time" chart renders a line (INT data); the KPI cards show numbers; browser console shows no `processed_over_time HTTP` errors.
- [ ] Click a **Recent Validations** card → lands on `/workitems?search=<id>` and the workitems list filters to that ID. (Prefix behavior itself is untestable outside PROD — the lint test carries that guarantee; this validates the interpolation didn't break navigation.)
- [ ] Force a 404 (navigate to `/definitely-not-a-route`) → the 404 page renders and both home links navigate back to the app.
- [ ] Open Reporting → run a saved simple report; open Prepared Documents if reachable with the login user — no console 404s.
- [ ] Screenshots to `var/screenshots/dashboard-404-chart-01-chart.png`, `...-02-card-click.png`, `...-03-error-page.png`; if the session is remote, SendUserFile them unprompted.
- [ ] Full local gate: `.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q` → green. If concurrent-work test failures unrelated to these files appear, report them but don't chase them. (The owner runs the e2e tier via pre-push; if you run it yourself, `python scripts/test_db_reset.py` first.)

---

## Owner actions (not for the executor)

1. **O1 — PROD delivery + spot check:** review, push, PR, merge → deploy applies any pending migration before app-pool stop and mirrors the code. Afterwards, on PROD: click a Recent Validations card (should land on `/nexora/workitems?search=<id>`), check the over-time chart + KPI cards for a non-PDBS process, and load the Reporting + Prepared Documents pages watching the console for 404s. Mind the (now error-free) response cache: up to ~5 min per user+filter, per IIS worker. For an immediate PROD data fix under branch B: `python scripts/db-migrate.py --env PROD` (idempotent).
2. **O2 — only if Task 3 landed on branch A:** repair StatisticsDB connectivity/credentials for the app on SYAPP01 — the relevant `env/PROD.env` values on the server are `DB_SERVER_PRD` / `DB_UID` / `DB_PWD` / `DB_STATISTICS` (plus firewall / SQL login server-side). The executor cannot and must not touch PROD config; until fixed, the shipped isolation keeps PDBS + backlog rendering.
3. **O3 — only if Task 3 landed on branch D:** the Statistics DB stopped being fed — chase the upstream ingest (`ops/cleanup/csvLogs_toDB.ps1` scheduled task and/or the Octo-side export). Outside this repo.
4. **Push + PR** for `feature/2.5.64` (full pre-push gate; remote sessions stop at commit). The PR carries everything on the branch at push time — this work, the earlier CI-speedup/retry-net commits, and the concurrent docfield-permission-gating work. The parked-broken Confluence sync workflow will fail on merge — expected, harmless.

## Follow-ups deliberately NOT in this plan

- A user-visible degraded-state banner for the dashboard (workitems `degradedSources` precedent) plus `response.ok` guards for `updateKpiStats`/`updateHourlyChart` — needs a `degraded` key in the four JSON responses and an i18n cycle; do together as one small feature.
- An `additionalCondition` normalizer (`_stat_condition`: auto-prefix `AND` for bare predicates) — under branch B the migration fixes the stored value instead; add the normalizer only if diagnosis shows the contract keeps being violated by hand-edits.
- Server-rendering `window.API_PREFIX = "{{ request.script_root }}/"` once in a base template and migrating the ~20 heuristic copies — nice-to-have consolidation, too much churn mid-bugfix; the lint keeps new code honest.
- `dashboard_kpi_stats`'s early-return includes a `processed_week` key the success path never returns (cosmetic; the front-end doesn't read it).
- `api_recent_activity` caches an error-empty `[]` for 120 s (it returns 200 on failure) — cosmetic, self-heals.
- Widget engine (`build_widget_query` / `dashboard_widget_data`) is StatisticsDB-only and dormant (templates never call it); if it ever goes live it needs the same per-leg thinking.

## Gotchas & notes

- **Concurrent work:** never `git add -A`/`.`/`-u`; only the explicit paths per task. Re-check `git status`, `git log`, and the migrations directory at execution start — this plan's snapshot is from 2026-07-13 evening.
- **SimpleCache is per-process**: INT dev-server restarts clear it; on PROD each IIS worker has its own. When verifying any fix live, restart or wait out the TTL before declaring victory.
- **`.uncached`**: flask-caching 2.3.1 sets `decorated_function.uncached` to the raw view — the route-level unit tests rely on it to bypass caching (the four legacy views are module-level with no other decorator). If a future flask-caching drops it, call the decorated view inside the request context with a unique `session['userid']` per test (the cache key is path/user/filter-scoped).
- The existing `_row` helper in `tests/unit/test_dashboard_stats.py` deliberately lacks `additionalCondition`; route-level tests MUST use the new `_cfg_row` or the route raises `AttributeError` on `row.additionalCondition`.
- `_default_stat_rows` returns fully-materialized pyodbc rows (`fetchall()` before `conn.close()`), same contract as `_ms02_stat_rows`; attribute access (`row.d`, `row.total_count`, `row.h`, `row.total`) keeps working after close.
- The `includes("nexora")` API_PREFIX heuristic matches the HOSTNAME `nexora.sydoc.ch` as well as the path — fragile-looking but proven across ~20 partials; do NOT "improve" it in one file only. It would also match a URL that merely contains "nexora" in a query param — accepted, consistent with the existing idiom.
- **The lint intentionally does NOT match `api('/api/reporting/...')` call sites** — those are made safe inside the four `api()` helpers (Decision 4). A brand-new partial with its own un-normalized `api()` helper would slip past; the CLAUDE.md convention note (Task 9) is the guard for that.
- In `dashboard_processed_over_time` do not skip the `conn = None` line after the Statconfig read (Task 4 step 1) — without it the route's `finally: if conn: conn.close()` re-closes the NexoraDB connection after the refactor removes the later reassignment.
- The code queries `FROM Statconfig` while the committed dump is `sql/NexoraDB/Tables/dbo.StatConfig.sql` (capital C) — the CI collation makes that fine; don't "fix" the casing anywhere.
- Never hand-edit files under `sql/NexoraDB/…`; a data-only corrective migration leaves the dumps unchanged, so `sql-sync-check` must stay clean without any dump diff.
- `Get-Content`/`Select-String` on the SMB app.log path are read-only and non-locking; don't open the PROD log with tools that take write locks.
- Restart the dev server after ANY template edit before browser checks — Jinja templates are cached for the process lifetime.
- The pre-push gate runs the full two-tier suite incl. Playwright e2e; if e2e fails oddly, reset stale TEST state with `python scripts/test_db_reset.py` first (owner runs the push).
- **PROD diagnosis discipline:** the Task 3 probes are the entire authorized surface — read-only SMB log read + read-only SELECTs. No writes, no restarts, no config edits, no secret values in output, commits, or the plan appendix.
- **Bug 2 may be multi-cause** (e.g. one stale Statconfig row AND transient connectivity): the decision table is per-row/per-evidence — branch B for the bad rows can coexist with owner action O2. The unconditional Tasks 4–6 make every combination non-catastrophic.
