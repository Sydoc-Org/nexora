# Reporting: Pin to Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `feature/2.5.64` HEAD (`159a2dc`) on 2026-07-15** — trust the anchors, but re-Grep before editing (this plan quotes code, never line numbers). Plan file: `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md`.

**Goal:** A user can pin any saved (non-SQL) report from the Reporting page to their personal Dashboard: the dashboard grows a "Pinned reports" strip that runs each pinned report's saved definition on load and renders a stat card (zero-dimension totals) or a mini chart (dimensioned results), with an unpin `×` on each tile, a click-through that deep-links back to the report in the Simple pane, and a Pin/Unpin toggle in the Simple result header.

**Scope cut discovered during recon:** the original request also named *alert-only schedules* — **that feature already shipped** (migration `0022_report_schedule_alerts.sql`, `ALERT_OPS`/`alert_trips`/`total_definition` in `nx_lib/reporting/schedule.py`, runner support in `ops/run_scheduled_reports.py`, UI fields in `templates/js/_reporting_js.html`, unit + integration + e2e tests). This plan is pin-to-dashboard only.

**Architecture:** Pins are personal rows in a new `dbo.ReportingPins` table (`UserID` + `ReportID`, FK CASCADE to `dbo.Reports` so report deletion auto-unpins) — deliberately **decoupled from the dormant dashboard widget engine** (`nx_lib/views/dashboard.py: dashboard_widget_data`, `validate_dashboard_layout` — backend built by the 2026-04-27 customizable-dashboard plan but frontend-less and its `DashboardLayouts` migration never shipped; resurrecting it is that plan's job, not this one's). Three small endpoints live beside the existing reports CRUD in `nx_lib/views/reporting.py`; the dashboard tile renderer reuses the whole existing reporting read path client-side (`GET /api/reporting/reports/<id>` for the definition, `POST /api/reporting/run` for rows), so pins inherit every access check, scope rule, and metric semantics with zero new query code. Access to a pinned report is re-checked at render time (share revocation ⇒ error tile, not stale data).

**Tech Stack:** SQL Server migration `0040` + `sql/test/schema.sql` mirror, Flask endpoints (pyodbc raw cursors, same style as `api_reports_get`), Chart.js 4 (already on `templates/dashboard.html` via CDN), vanilla-JS Jinja partials (`templates/js/_dashboard_js.html` `API_PREFIX` idiom, `templates/js/_reporting_simple_js.html`), pytest integration + Playwright e2e (network-stub pattern — TEST env has no Statistics DB), Flask-Babel de/fr/it.

---

## Context an engineer needs (read first)

- **Branch:** work directly on `feature/2.5.64` (no worktree was created for this plan). **Commit per task. Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes (the pre-push gate runs the FULL suite incl. Playwright e2e).
- **Two stray untracked files** (`package.json`, `package-lock.json` at repo root) predate this plan — never `git add` them.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python — the `.venv` is test-only.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **TDD is the house rule.** Backend tasks are strict RED→GREEN. Frontend tasks write the failing Playwright e2e first.
- **TEST env has NO Statistics DB** — a pinned docprocessing report can never *run* in e2e. Use the established network-stub helpers (see `tests/e2e/test_reporting_simple.py`: routes are stubbed with `page.route("**/api/reporting/run", …)` **before** `page.goto`).
- **TEST DB shape comes from `sql/test/schema.sql`** (applied by `scripts/test_db_reset.py`), NOT from migrations — Task 1 mirrors the CREATE there in the same commit.
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` (stale NEXORA_TEST state fails order-dependent e2e tests).
- **Jinja template cache is process-lifetime** — restart the dev server before ANY manual browser check.
- **e2e locale is English** — assert English strings.
- **Migrations needed: YES — one migration, target number `0040`** (`sql/_migrations/NexoraDB/` currently tops out at `0039_metric_labels_and_page_count.sql`; re-list at execution time and bump if taken). Idempotent (`IF OBJECT_ID(...) IS NULL` guard). `*.sql` is LF — write with the Write tool, not shell heredocs.
- **The migration is DDL** — the pre-commit `sql-sync-check` regenerates `sql/NexoraDB/Tables/dbo.ReportingPins.sql`; `git add` the regenerated dump into the same commit (never hand-edit it).
- **i18n: ONE late pybabel cycle (Task 6).** New msgids land in Tasks 3 and 5; `tests/unit/test_translations.py` is expected RED in between — use `--deselect tests/unit/test_translations.py` for the fast tier until Task 6.
- **PROD URL prefix:** every hand-built URL in JS partials must go through the `API_PREFIX` idiom. `templates/js/_dashboard_js.html` already opens with `const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";` — reuse it. The Simple pane's `api()` helper already normalizes.
- **No new permission.** Pins are personal; the endpoints are gated by the existing `reporting.view`, the dashboard strip by the page's own `dashboard.view` + a `has_permission('reporting.view')` template guard. `page_visibility()` untouched. **No `deploy.yml` changes** (only `sql/`, `nx_lib/`, `templates/`, `translations/`, `tests/`, `docs/` touched).
- **Visual contract (2026-07-14 flagship polish):** never rename a `.reporting-*` class; preserve every `data-testid`/`id`; `.nx-rise*` animations use fill-mode `backwards`, never `both`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via Bash `git commit -F - <<'EOF' … EOF`. If `ruff-format` rewrites a file the first attempt fails — `git add -u` and recommit. If INT is unreachable: `SQL_SYNC_SKIP=1`, never `--no-verify`.
- **Commit trailer names the EXECUTING model** — the blocks below say `Claude Opus 4.8`; substitute the real executor if different.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Standalone `dbo.ReportingPins` table; the dormant widget engine stays dormant.** | The widget-engine backend (`validate_dashboard_layout`, `dashboard_widget_data`) has no frontend and no `DashboardLayouts` migration — hanging pins on it means shipping half of the 2026-04-27 plan as a side effect. A 4-column table + 3 endpoints is the whole persistence story; if the widget grid ever lands, a pin becomes one `INSERT`-derived widget row (noted in Owner actions). |
| D2 | **Dashboard tiles fetch client-side via the existing `GET /api/reporting/reports/<id>` + `POST /api/reporting/run`.** | Zero new query/security surface: the reports GET enforces owner/shared/visibility, the run endpoint enforces source permissions + process scope. A revoked share degrades to a 404 → error tile with an unpin affordance. |
| D3 | **Only saved, non-SQL reports are pinnable.** `kind == "sql"` inside `DefinitionJSON` is rejected at pin time (dbo.Reports has no Kind column — kind lives in the JSON). | The Simple pane already excludes sql-kind (`state.reports = res.data.filter(function (r) { return r.kind !== 'sql'; })`); `/api/reporting/run` rejects sql-kind for non-SQL users. Unsaved results show a disabled Pin button with a "save first" tooltip. |
| D4 | **Tile rendering: zero-dimension (metrics, no columns) → stat card; otherwise mini Chart.js chart** (line when the first column is a date/grained field, else bar; first metric as the value; cap 25 x-points, first 2 dims only — deeper results still render, extra dims collapse into the first). | Mirrors the Simple pane's own chart heuristics (`isDate = !!firstCol.grain || /date/.test(firstCol.field)`) at tile scale. Chart.js 4 is already loaded on the dashboard. |
| D5 | **Unpin from both sides:** tile `×` on the dashboard, and the same Pin button toggles to "Unpin" in the Simple result header. | One `DELETE /api/reporting/reports/<id>/pin` serves both. |
| D6 | **Deep link `\reporting?report=<id>`** opens the report in the Simple pane (tile click-through). Bootstraps through the existing `window.__rpInitialTab` inline script in `templates/reporting.html`. | The Simple pane already has `openReport(r)`; the boot hook is ~6 lines. |
| D7 | **FK `ON DELETE CASCADE` from ReportingPins to Reports.** | `api_reports_delete` runs a bare `DELETE FROM Reports …` — without CASCADE every report deletion would orphan pins (and the FK would actually block the delete). |
| D8 | **Pin order = `PinnedAt` ascending; no drag-reorder in v1.** | YAGNI — unpin/repin re-orders; a SortOrder column can come with the widget grid. |

---

## Owner actions (not for the executor)

1. **Review + push `feature/2.5.64`** (this session is commit-only). The deploy workflow auto-applies migration `0040` to PROD.
2. **Widget-grid future:** when the 2026-04-27 customizable-dashboard frontend is ever built, migrate pins into layout widgets (one-shot script: `ReportingPins` → `report`-type widget rows) and drop the strip.
3. **Advanced-tab pin button** was deliberately left out (Simple result header + dashboard only). Say the word if you want it mirrored.
4. **Drag-reorder of pinned tiles** — declined for v1 (D8).

---

# PHASE 1 — Persistence + API

### Task 1: Migration 0040 — dbo.ReportingPins (+ TEST mirror)

**Files:**
- Create: `sql/_migrations/NexoraDB/0040_create_reporting_pins.sql`
- Modify: `sql/test/schema.sql` (append CREATE near the existing `CREATE TABLE dbo.ReportShares (`)
- Auto-regenerated by the pre-commit hook: `sql/NexoraDB/Tables/dbo.ReportingPins.sql` (`git add` it, never edit)

**Interfaces:**
- Produces: table `dbo.ReportingPins(PinID int identity PK, UserID int NOT NULL, ReportID int NOT NULL FK→dbo.Reports ON DELETE CASCADE, PinnedAt datetime2 default SYSUTCDATETIME(), UNIQUE(UserID, ReportID))`. Task 2's endpoints and every test rely on exactly these names.

- [ ] **Step 1 — Write the migration** (Write tool, LF):

```sql
-- 0040: personal pin-to-dashboard rows for saved reports.
-- A pin is (user, report); report deletion cascades the pin away.
IF OBJECT_ID('dbo.ReportingPins', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingPins (
        PinID     INT IDENTITY(1,1) NOT NULL,
        UserID    INT NOT NULL,
        ReportID  INT NOT NULL,
        PinnedAt  DATETIME2 NOT NULL CONSTRAINT DF_ReportingPins_PinnedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_ReportingPins PRIMARY KEY CLUSTERED (PinID),
        CONSTRAINT UQ_ReportingPins_UserReport UNIQUE (UserID, ReportID),
        CONSTRAINT FK_ReportingPins_Reports FOREIGN KEY (ReportID)
            REFERENCES dbo.Reports (ReportID) ON DELETE CASCADE
    );
    CREATE NONCLUSTERED INDEX IX_ReportingPins_User ON dbo.ReportingPins (UserID);
END
GO
```

- [ ] **Step 2 — Mirror into `sql/test/schema.sql`.** Find the block starting `CREATE TABLE dbo.ReportShares (` and append after that table (same `IF OBJECT_ID` guard style used throughout the file) the identical CREATE from Step 1.

- [ ] **Step 3 — Reset the TEST DB and prove the table exists:**

Run: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`
Expected: completes without error (schema.sql applies cleanly).

- [ ] **Step 4 — Commit** (the pre-commit hook applies 0040 to INT and regenerates the per-object dump — `git add` it when the hook stages complain):

```bash
git add sql/_migrations/NexoraDB/0040_create_reporting_pins.sql sql/test/schema.sql sql/NexoraDB/Tables/dbo.ReportingPins.sql
git commit -F - <<'EOF'
feat(reporting): migration 0040 - ReportingPins table

Personal pin-to-dashboard rows: (UserID, ReportID) unique, PinnedAt,
FK to dbo.Reports with ON DELETE CASCADE so report deletion auto-unpins.
Mirrored into sql/test/schema.sql for the TEST database.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

### Task 2: Pins API — list / pin / unpin

**Files:**
- Modify: `nx_lib/views/reporting.py` (three view functions + three `app.add_url_rule` lines)
- Test: `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Produces: `GET /api/reporting/pins` → `[{"reportId": int, "name": str, "pinnedAt": iso}]` (only pins whose report still exists AND is still accessible to the caller); `POST /api/reporting/reports/<id>/pin` → `{"pinned": true}` (idempotent; 404 unknown/inaccessible report, 400 sql-kind); `DELETE /api/reporting/reports/<id>/pin` → `{"pinned": false}` (idempotent). All `@require_permission("reporting.view")`.
- Consumes: Task 1's table.

- [ ] **Step 1 — Write the failing integration tests.** Append to `tests/integration/test_reporting_routes.py`, following the file's existing fixture conventions (look at the existing reports-CRUD tests in the same file for the `user_client` fixture and how a report row is created via `POST /api/reporting/reports`):

```python
# ---------------------------------------------------------------- pins

def _create_report(client, name="Pin me", kind=None):
    definition = {
        "schemaVersion": 1, "visualization": "table", "source": "docprocessing",
        "title": name, "columns": [{"field": "processname"}],
        "filters": [], "sort": [], "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }
    if kind:
        definition["kind"] = kind
    resp = client.post(
        "/api/reporting/reports", json={"name": name, "definition": definition}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["id"]


def test_pin_unpin_roundtrip(user_client):
    rid = _create_report(user_client)
    assert user_client.get("/api/reporting/pins").get_json() == []
    resp = user_client.post(f"/api/reporting/reports/{rid}/pin")
    assert resp.status_code == 200 and resp.get_json()["pinned"] is True
    # idempotent re-pin
    assert user_client.post(f"/api/reporting/reports/{rid}/pin").status_code == 200
    pins = user_client.get("/api/reporting/pins").get_json()
    assert len(pins) == 1 and pins[0]["reportId"] == rid and pins[0]["name"] == "Pin me"
    resp = user_client.delete(f"/api/reporting/reports/{rid}/pin")
    assert resp.status_code == 200 and resp.get_json()["pinned"] is False
    assert user_client.get("/api/reporting/pins").get_json() == []


def test_pin_unknown_report_404(user_client):
    assert user_client.post("/api/reporting/reports/999999/pin").status_code == 404


def test_pin_sql_kind_rejected(user_client):
    rid = _create_report(user_client, name="SQL report", kind="sql")
    resp = user_client.post(f"/api/reporting/reports/{rid}/pin")
    assert resp.status_code == 400


def test_deleting_report_cascades_pin(user_client):
    rid = _create_report(user_client, name="Doomed")
    user_client.post(f"/api/reporting/reports/{rid}/pin")
    assert user_client.delete(f"/api/reporting/reports/{rid}").status_code == 200
    assert user_client.get("/api/reporting/pins").get_json() == []
```

> If `_create_report`-style helpers already exist in the file, reuse them instead of adding a duplicate — adjust names accordingly.

- [ ] **Step 2 — Run, expect RED** (`404` on the pins routes):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -k "pin" -q`
Expected: FAIL (404s / missing routes).

- [ ] **Step 3 — Implement the three endpoints.** In `nx_lib/views/reporting.py`, directly after `api_reports_delete` (anchor: the function containing `"DELETE FROM Reports WHERE ReportID = ? AND OwnerUserID = ?"`), add:

```python
@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_pins_list():
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        # Same access predicate as api_reports_get: owner, org-shared, or
        # explicitly shared. A pin whose report lost accessibility is hidden
        # (not deleted - regaining the share brings it back).
        cur.execute(
            "SELECT p.ReportID, r.Name, p.PinnedAt "
            "FROM dbo.ReportingPins p "
            "JOIN dbo.Reports r ON r.ReportID = p.ReportID "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE p.UserID = ? "
            "  AND (r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ?) "
            "ORDER BY p.PinnedAt ASC",
            (userid, userid, userid, userid),
        )
        return jsonify(
            [
                {"reportId": row.ReportID, "name": row.Name, "pinnedAt": row.PinnedAt.isoformat()}
                for row in cur.fetchall()
            ]
        )
    except Exception as e:
        current_app.logger.error(f"/api/reporting/pins list error: {e}")
        return jsonify({"error": _("Could not load pins")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_pins_create(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.DefinitionJSON FROM dbo.Reports r "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.ReportID = ? "
            "  AND (r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ?)",
            (userid, report_id, userid, userid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": _("Not found")}), 404
        try:
            definition = json.loads(row.DefinitionJSON)
        except (TypeError, ValueError):
            definition = {}
        if definition.get("kind") == "sql":
            return jsonify({"error": _("SQL reports cannot be pinned")}), 400
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM dbo.ReportingPins WHERE UserID = ? AND ReportID = ?) "
            "INSERT INTO dbo.ReportingPins (UserID, ReportID) VALUES (?, ?)",
            (userid, report_id, userid, report_id),
        )
        conn.commit()
        return jsonify({"pinned": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/pins create error: {e}")
        return jsonify({"error": _("Could not pin the report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_pins_delete(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportingPins WHERE UserID = ? AND ReportID = ?",
            (userid, report_id),
        )
        conn.commit()
        return jsonify({"pinned": False})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/pins delete error: {e}")
        return jsonify({"error": _("Could not unpin the report")}), 500
    finally:
        conn.close()
```

Then register the routes: find the existing registration block containing `"/api/reporting/reports/<int:report_id>",` and add beside it (matching the file's `app.add_url_rule` style, endpoint names `api_pins_list` / `api_pins_create` / `api_pins_delete`, methods `GET` / `POST` / `DELETE`):

```python
app.add_url_rule("/api/reporting/pins", endpoint="api_pins_list", view_func=api_pins_list)
app.add_url_rule(
    "/api/reporting/reports/<int:report_id>/pin",
    endpoint="api_pins_create",
    view_func=api_pins_create,
    methods=["POST"],
)
app.add_url_rule(
    "/api/reporting/reports/<int:report_id>/pin",
    endpoint="api_pins_delete",
    view_func=api_pins_delete,
    methods=["DELETE"],
)
```

> `test_create_app.py` may assert the full endpoint list — if `pytest tests/unit/test_create_app.py` goes RED on a count/name assertion, add the three new endpoint names there (that test exists to force this conscious step).

- [ ] **Step 4 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -k "pin" tests/unit/test_create_app.py -q`
Expected: PASS.

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_routes.py tests/unit/test_create_app.py
git commit -F - <<'EOF'
feat(reporting): pins API - list, pin, unpin saved reports

GET /api/reporting/pins plus POST/DELETE /api/reporting/reports/<id>/pin,
gated by reporting.view. Pinning re-checks the same access predicate as
the reports GET; sql-kind definitions are rejected; both mutations are
idempotent. Listing hides pins whose report is no longer accessible.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — Reporting-page UI

### Task 3: Pin/Unpin toggle in the Simple result header

**Files:**
- Modify: `templates/_reporting_simple.html` (one button in the result header)
- Modify: `templates/js/_reporting_simple_js.html` (button state + click handler)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Consumes: Task 2's endpoints.
- Produces: `#rsPin` button (`data-testid="rs-pin"`), visible only when the current result is a saved report (`state.current.reportId` set); label toggles Pin ↔ Unpin.

- [ ] **Step 1 — Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py`, reusing the file's login + stub helpers (Grep `def _login` and the `page.route` stubs used by the library tests in the same file — copy their source/metrics/reports stub payloads verbatim so the library shows one saved report):

```python
def test_pin_button_toggles_on_saved_report(nexora_server, page):
    # Reuse the module's existing catalog/library stubs; additionally stub
    # the pins endpoints (in-memory pin set).
    pinned = {"state": False}

    def pins_list(route):
        route.fulfill(json=[{"reportId": 1, "name": "Lib report", "pinnedAt": "2026-07-15T00:00:00"}] if pinned["state"] else [])

    def pin_post(route):
        pinned["state"] = route.request.method == "POST"
        route.fulfill(json={"pinned": pinned["state"]})

    page.route("**/api/reporting/pins", pins_list)
    page.route("**/api/reporting/reports/1/pin", pin_post)
    # ... existing library/report/run stubs from neighbouring tests, then:
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Library cards all carry data-testid="rs-card" — pick by text.
    page.get_by_test_id("rs-card").filter(has_text="Lib report").click()
    pin = page.get_by_test_id("rs-pin")
    expect(pin).to_be_visible()
    expect(pin).to_have_text("Pin to dashboard")
    pin.click()
    expect(pin).to_have_text("Unpin from dashboard")
    pin.click()
    expect(pin).to_have_text("Pin to dashboard")
```

> The stub payload shapes for sources/metrics/reports MUST be copied from the neighbouring library tests in the same file at execution time — do not invent them; the test above marks the spot with a comment.

- [ ] **Step 2 — Run, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "pin_button" -q`
Expected: FAIL (`rs-pin` not found).

- [ ] **Step 3 — Add the button.** In `templates/_reporting_simple.html`, inside the result-header button group (anchor: the line `<button id="rsSave" class="reporting-btn nx-btn nx-btn--secondary" data-testid="rs-save">{{ _("Save") }}</button>`), add directly after `rsSave`:

```html
<button id="rsPin" class="reporting-btn nx-btn nx-btn--secondary" data-testid="rs-pin" hidden>{{ _("Pin to dashboard") }}</button>
```

- [ ] **Step 4 — Wire the JS.** In `templates/js/_reporting_simple_js.html`:

(a) near the other I18N keys (anchor: `opIn: {{ _("is one of")|tojson }},`) add:

```js
    pinLabel: {{ _("Pin to dashboard")|tojson }},
    unpinLabel: {{ _("Unpin from dashboard")|tojson }},
```

(b) a state refresh helper + wiring. Anchor: the line `el('rsResultTitle').textContent = cur.name || cur.def.title || '';` (inside the run-result rendering) — after the title assignment add `refreshPinButton();`. Define nearby:

```js
  var pinnedIds = null;   // Set of pinned reportIds, lazy-loaded once per page
  async function refreshPinButton() {
    var btn = el('rsPin');
    if (!btn) return;
    var rid = state.current && state.current.reportId;
    if (!rid) { btn.hidden = true; return; }
    if (pinnedIds === null) {
      var res = await api('/api/reporting/pins');
      pinnedIds = new Set((res.ok && Array.isArray(res.data) ? res.data : []).map(function (p) { return p.reportId; }));
    }
    btn.textContent = pinnedIds.has(rid) ? I18N.unpinLabel : I18N.pinLabel;
    btn.hidden = false;
  }
  el('rsPin').addEventListener('click', async function () {
    var rid = state.current && state.current.reportId;
    if (!rid) return;
    var isPinned = pinnedIds && pinnedIds.has(rid);
    var res = await api('/api/reporting/reports/' + rid + '/pin', { method: isPinned ? 'DELETE' : 'POST' });
    if (!res.ok) return;
    if (isPinned) pinnedIds.delete(rid); else pinnedIds.add(rid);
    refreshPinButton();
  });
```

> Match the file's actual `api()` helper signature (Grep `function api(` in the partial) — if it takes `(path, opts)` with `method` in opts as shown in neighbouring calls, the above is right; adjust otherwise. Also call `refreshPinButton()` from `showResultError` paths where the header resets? No — `showResultError` hides the result view's cards; add `el('rsPin').hidden = true;` beside the other `el('rs…').hidden = true;` lines in `showResultError` so a failed run never shows a stale Pin.

- [ ] **Step 5 — Run, expect GREEN** (restart dev server first if you eyeball manually — template cache):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "pin_button" -q`
Expected: PASS.

- [ ] **Step 6 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): pin/unpin toggle in the Simple result header

Saved (non-SQL) reports get a Pin-to-dashboard button next to Save;
label toggles with the pin state (lazy-loaded once per page). Hidden
for unsaved results and on result errors.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

### Task 4: Deep link `\reporting?report=<id>`

**Files:**
- Modify: `templates/reporting.html` (extend the inline boot script)
- Modify: `templates/js/_reporting_simple_js.html` (consume the boot value)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Produces: visiting `/reporting?report=<id>` lands on the Simple tab with that report opened (via the existing `openReport`). Dashboard tiles (Task 5) link here.

- [ ] **Step 1 — Write the failing e2e test** (same stub set as Task 3's test — library + report + run stubs):

```python
def test_report_query_param_opens_report(nexora_server, page):
    # ... same stubs as the library tests ...
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?report=1")
    expect(page.get_by_test_id("rs-result-title")).to_have_text("Lib report")
```

- [ ] **Step 2 — Run, expect RED.**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "query_param_opens" -q`
Expected: FAIL (library view shown, no result title).

- [ ] **Step 3 — Boot plumbing.** In `templates/reporting.html`, the inline boot script parses the URL inline (anchor: `var tab = new URLSearchParams(window.location.search).get('tab')`). Extend the same `try` block, right after `window.__rpInitialTab = tab === 'advanced' ? 'advanced' : 'simple';`:

```js
        var rp = new URLSearchParams(window.location.search).get('report');
        window.__rpInitialReportId = rp && /^\d+$/.test(rp) ? parseInt(rp, 10) : null;
        if (window.__rpInitialReportId) window.__rpInitialTab = 'simple';
```

(And in the `catch` fallback line, leave `window.__rpInitialReportId` unset — the Simple partial guards with a truthiness check.)

In `templates/js/_reporting_simple_js.html`, at the end of the partial's init sequence (anchor: Grep the existing initial `loadLibrary()` call site), add:

```js
  if (window.__rpInitialReportId) {
    openReport({ id: window.__rpInitialReportId });
  }
```

> `openReport(r)` only reads `r.id` (anchor: `var res = await api('/api/reporting/reports/' + r.id);`) — passing `{id}` is sufficient.

- [ ] **Step 4 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "query_param_opens" -q`
Expected: PASS.

- [ ] **Step 5 — Commit:**

```bash
git add templates/reporting.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): deep link /reporting?report=<id> opens the report

The reporting boot script parses ?report= and the Simple pane opens it
via the existing openReport path. Used by dashboard pinned-tile links.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — Dashboard strip

### Task 5: "Pinned reports" section on the dashboard

**Files:**
- Modify: `templates/dashboard.html` (section markup)
- Modify: `templates/js/_dashboard_js.html` (tile renderer)
- Modify: `static/css/dashboard.css` (tile styles, append-only)
- Test: `tests/e2e/test_dashboard.py` (append)

**Interfaces:**
- Consumes: Tasks 2 + 4. `GET /api/reporting/pins`, `GET /api/reporting/reports/<id>`, `POST /api/reporting/run`, `DELETE /api/reporting/reports/<id>/pin`, `/reporting?report=<id>`.
- Produces: `#pinnedReports` section — one `.nx-card` tile per pin (`data-testid="pinned-tile-<reportId>"`): title row (name + open link + unpin `×`), body = stat value or `<canvas>` mini chart; error tile on any fetch failure. Whole section hidden when the user has no `reporting.view` or zero pins.

- [ ] **Step 1 — Write the failing e2e test.** Append to `tests/e2e/test_dashboard.py` (reuse its `_login`; stub every reporting call — the TEST env cannot run docprocessing):

```python
def test_pinned_report_tile_renders_and_unpins(nexora_server, page):
    page.route("**/api/reporting/pins", lambda r: r.fulfill(json=[
        {"reportId": 7, "name": "Docs per month", "pinnedAt": "2026-07-15T00:00:00"}
    ]))
    page.route("**/api/reporting/reports/7", lambda r: r.fulfill(json={
        "id": 7, "name": "Docs per month", "visibility": "private", "owned": True, "canEdit": True,
        "definition": {"schemaVersion": 1, "visualization": "table", "source": "docprocessing",
                        "title": "Docs per month",
                        "columns": [{"field": "export_date", "grain": "month"}],
                        "metrics": [{"metric": "doc_count"}],
                        "filters": [], "sort": [], "scope": {"clients": [], "processes": []},
                        "rowLimit": 5000},
    }))
    page.route("**/api/reporting/run", lambda r: r.fulfill(json={
        "columns": [{"field": "export_date"}, {"field": "doc_count"}],
        "rows": [["2026-01-01", 3], ["2026-02-01", 5]],
        "rowCount": 2, "truncated": False, "resolvedDates": [],
    }))
    unpinned = {"hit": False}
    def unpin(route):
        unpinned["hit"] = True
        route.fulfill(json={"pinned": False})
    page.route("**/api/reporting/reports/7/pin", unpin)
    # TestUser holds dashboard.view ONLY — the pinned section is Jinja-gated on
    # reporting.view, so this test must run as the admin seed user.
    _login(page, nexora_server, "admin@test.local")
    page.goto(f"{nexora_server}/dashboard")
    tile = page.get_by_test_id("pinned-tile-7")
    expect(tile).to_be_visible()
    expect(tile).to_contain_text("Docs per month")
    tile.get_by_test_id("pinned-unpin-7").click()
    expect(tile).to_be_hidden()
    assert unpinned["hit"]
```

- [ ] **Step 2 — Run, expect RED.**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_dashboard.py -k "pinned_report_tile" -q`
Expected: FAIL (`pinned-tile-7` not found).

- [ ] **Step 3 — Section markup.** In `templates/dashboard.html`, after the KPI grid (anchor: the closing `</div>` of the block that starts `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">`) and before the two-column grid (anchor: `<div class="grid grid-cols-1 lg:grid-cols-3 gap-8">`), insert:

```html
    {% if has_permission('reporting.view') %}
    <section id="pinnedReports" class="mb-8" hidden data-testid="pinned-reports">
      <h3 class="nx-section" style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
        <i class="fa-solid fa-thumbtack" style="color:var(--nx-accent)"></i>
        {{ _("Pinned reports") }}
      </h3>
      <div id="pinnedReportsGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
    </section>
    {% endif %}
```

> Confirm `has_permission` is exposed to Jinja by Grepping an existing template usage (`has_permission(` in `templates/`); if templates gate differently (e.g. a `page_v` map), copy that idiom instead.

- [ ] **Step 4 — Tile renderer.** In `templates/js/_dashboard_js.html` (inside the existing IIFE, near `updateProcessedOverTimeChart`), add — reusing the file's `API_PREFIX` const and `csrfToken` pattern (Grep `X-CSRFToken` in the file for the exact header idiom):

```js
    // ----- Pinned reports strip -----
    async function loadPinnedReports() {
        const section = document.getElementById('pinnedReports');
        if (!section) return;                       // no reporting.view
        const grid = document.getElementById('pinnedReportsGrid');
        let pins = [];
        try {
            const res = await fetch(`${API_PREFIX}api/reporting/pins`);
            if (res.ok) pins = await res.json();
        } catch (e) { /* leave section hidden on network failure */ }
        if (!pins.length) { section.hidden = true; return; }
        section.hidden = false;
        grid.innerHTML = '';
        pins.forEach(p => renderPinTile(grid, p));
    }

    function pinTileShell(grid, p) {
        const tile = document.createElement('div');
        tile.className = 'nx-card nx-card--pad pinned-tile';
        tile.setAttribute('data-testid', `pinned-tile-${p.reportId}`);
        tile.innerHTML =
            `<div class="pinned-tile__head">` +
            `<a class="pinned-tile__title" href="${API_PREFIX}reporting?report=${p.reportId}">${escapeHtml(p.name)}</a>` +
            `<button class="pinned-tile__unpin" data-testid="pinned-unpin-${p.reportId}" title="{{ _('Unpin') }}">&times;</button>` +
            `</div><div class="pinned-tile__body"></div>`;
        tile.querySelector('.pinned-tile__unpin').addEventListener('click', async () => {
            await fetch(`${API_PREFIX}api/reporting/reports/${p.reportId}/pin`,
                { method: 'DELETE', headers: { 'X-CSRFToken': csrfToken } });
            tile.hidden = true;
        });
        grid.appendChild(tile);
        return tile.querySelector('.pinned-tile__body');
    }

    async function renderPinTile(grid, p) {
        const body = pinTileShell(grid, p);
        try {
            const repRes = await fetch(`${API_PREFIX}api/reporting/reports/${p.reportId}`);
            if (!repRes.ok) throw new Error('report');
            const rep = await repRes.json();
            const runRes = await fetch(`${API_PREFIX}api/reporting/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify(rep.definition),
            });
            if (!runRes.ok) throw new Error('run');
            const data = await runRes.json();
            drawPinResult(body, rep.definition, data.columns || [], data.rows || []);
        } catch (e) {
            body.innerHTML = `<p class="pinned-tile__error">{{ _("Could not load this report.") }}</p>`;
        }
    }

    function drawPinResult(body, def, columns, rows) {
        const dims = (def.columns || []).length;
        const metrics = def.metrics || [];
        if (!rows.length) {
            body.innerHTML = `<p class="pinned-tile__error">{{ _("No data.") }}</p>`;
            return;
        }
        if (!dims && metrics.length) {              // zero-dimension grand total
            body.innerHTML = `<p class="pinned-tile__stat">${Number(rows[0][0]).toLocaleString()}</p>`;
            return;
        }
        const metricIdx = columns.length - metrics.length;
        const shown = rows.slice(0, 25);
        const firstCol = def.columns[0] || {};
        const isDate = !!firstCol.grain || /date/.test(firstCol.field || '');
        const labels = shown.map(r => String(r[0] == null ? '' : r[0]).slice(0, isDate ? 10 : 30));
        const values = shown.map(r => Number(r[metricIdx >= 0 ? metricIdx : 1]) || 0);
        const canvas = document.createElement('canvas');
        body.appendChild(canvas);
        new Chart(canvas.getContext('2d'), {
            type: isDate ? 'line' : 'bar',
            data: { labels, datasets: [{ data: values, borderColor: '#4f46e5',
                backgroundColor: isDate ? 'rgba(79,70,229,.15)' : '#4f46e5',
                fill: isDate, tension: .25 }] },
            options: { responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } } },
        });
    }
```

Call `loadPinnedReports();` from the partial's existing DOM-ready/boot sequence (anchor: the block that calls `updateProcessedOverTimeChart();` and `updateHourlyChart();` on load — add the call beside them). If the file has no `escapeHtml` helper (Grep it), add the standard 4-line entity-escape helper next to the new functions.

- [ ] **Step 5 — Tile CSS.** Append to `static/css/dashboard.css`:

```css
/* Pinned-reports strip (reporting pin-to-dashboard) */
.pinned-tile__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.pinned-tile__title { font-weight: 600; color: var(--nx-text, inherit); text-decoration: none; }
.pinned-tile__title:hover { color: var(--nx-accent); }
.pinned-tile__unpin { border: none; background: none; font-size: 18px; line-height: 1; cursor: pointer; color: var(--nx-muted, #94a3b8); }
.pinned-tile__unpin:hover { color: var(--nx-danger, #dc2626); }
.pinned-tile__body { height: 180px; position: relative; }
.pinned-tile__stat { font-size: 40px; font-weight: 700; margin: 24px 0; }
.pinned-tile__error { color: var(--nx-muted, #94a3b8); font-style: italic; }
```

- [ ] **Step 6 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_dashboard.py -k "pinned_report_tile" -q`
Expected: PASS.

- [ ] **Step 7 — Commit:**

```bash
git add templates/dashboard.html templates/js/_dashboard_js.html static/css/dashboard.css tests/e2e/test_dashboard.py
git commit -F - <<'EOF'
feat(dashboard): pinned-reports strip rendering saved report tiles

Each pin fetches its saved definition and runs it through the existing
/api/reporting/run, rendering a stat card (zero-dim totals) or a mini
Chart.js chart (line for date grains, bar otherwise, 25-point cap).
Tiles link to /reporting?report=<id> and carry an unpin control; access
loss or run failure degrades to an error tile. Section hidden without
reporting.view or with zero pins.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

### Task 6: i18n cycle, changelog, docs, full verify

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`

- [ ] **Step 1 — Babel cycle** (from repo root — relative paths keep the location comments stable):

```powershell
.\.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.\.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

Translate every new msgid in de/fr/it (non-fuzzy): "Pin to dashboard", "Unpin from dashboard", "Pinned reports", "Unpin", "Could not load this report.", "No data.", "Could not load pins", "Could not pin the report", "Could not unpin the report", "SQL reports cannot be pinned". Then:

```powershell
.\.venv\Scripts\pybabel.exe compile -d translations
```

- [ ] **Step 2 — Changelog.** Under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- Reporting: pin-to-dashboard — saved (non-SQL) reports can be pinned from the
  Simple result header; the dashboard grows a per-user "Pinned reports" strip
  that runs each pinned definition on load (stat card or mini chart), links
  back to the report (`/reporting?report=<id>`), and unpins from either side
  (migration `0040`).
```

- [ ] **Step 3 — Docs.** In `docs/howto/reporting.md`, add a short `### Pin to dashboard` subsection near the sharing/schedules sections: what can be pinned (saved non-SQL reports the caller can access), where pins live (`dbo.ReportingPins`, personal, cascade on report delete), the three endpoints, and that access is re-checked on every dashboard render.

- [ ] **Step 4 — Full verify:**

```powershell
.\.venv\Scripts\python scripts\test_db_reset.py
.\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q
.\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_dashboard.py -q
```

Expected: all green (incl. `test_translations.py`).

- [ ] **Step 5 — Live browser pass.** Restart the server (`nx -r`), log in via `/dev/login/ben.streich`, save a report in Simple, pin it, open `/dashboard`, confirm the tile renders real data, unpin from the tile, re-pin from reporting, screenshot to `var/screenshots/`.

- [ ] **Step 6 — Commit:**

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md
git commit -F - <<'EOF'
docs(reporting): pin-to-dashboard changelog, howto and i18n cycle

Changelog entry under Unreleased/Added, a Pin-to-dashboard subsection in
docs/howto/reporting.md, and the pybabel extract/update/translate/compile
cycle for the new UI strings (de/fr/it, non-fuzzy).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- **`\api\reporting\run` CSRF:** the dashboard partial's existing POSTs send `X-CSRFToken` (anchor: `headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken}` in `_dashboard_js.html`) — the pin tile run POST must too, or CSRFProtect 400s.
- **Simple pane's `api()` helper** already handles the prefix + CSRF — do not hand-build URLs there.
- **`state.current.reportId`** is set by `openReport` (`state.current = { def: …, reportId: r.id, … }`) and is `undefined` for wizard/AI results until saved — exactly the visibility condition for the Pin button. After `rsSave` creates a report it sets the id (Grep `reportId` in the save handler at execution time; if save does NOT store the new id, set it there so the Pin button appears right after saving).
- **Zero-fill interaction:** the dashboard tile renders raw run rows (no zero-fill) — acceptable at tile scale; the Simple pane's `zeroFillDateBuckets` applies when the user clicks through.
- **Rate limits:** `GET /api/reporting/pins` is called once per dashboard load and once per reporting page load; tile fetches hit the existing reports/run limits (`60 per minute`) — a user with >20 pins could throttle; tile errors degrade gracefully. Ponytail ceiling, noted — no batching endpoint until real users hit it.
- **`dbo.Reports` has no Kind column** — sql-kind detection parses `DefinitionJSON` (D3). Same trick the reports list endpoint uses (Grep `s["kind"] == "sql"` in `nx_lib/views/reporting.py`).
- **`test_create_app.py`** pins the endpoint registry — expect to touch it in Task 2.
- **The dormant widget engine** (`DASHBOARD_WIDGET_TYPES = {"kpi", "timeseries", "categorical"}`) is intentionally untouched — do NOT add a `report` type there; that's the customizable-dashboard plan's surface.
