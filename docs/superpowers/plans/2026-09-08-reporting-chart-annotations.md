# Reporting chart annotations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** The owner of a saved report can pin a short dated note on its Simple-tab chart (Alt+click a bucket, or the list's "Add" button); every viewer sees the note as a marker on the chart and in a list under it.

**Architecture:** One new NexoraDB table (`dbo.ReportAnnotations`, migration `0123`), one new route module (`nx_lib/views/reporting/annotations.py`, copied from the `schedules.py` shape, owner-gated by `_is_report_owner`, read-gated by a new `_can_view_report`), and one new JS module (`static/js/reporting_simple_annotations.js`) that loads the rows for the open report, injects a marker dataset into the existing Chart.js instance through `chartConfigFor(..., opts.annotations)`, and owns the popover + list DOM. No new dependency, no new permission code.

**Tech Stack:** Flask + pyodbc raw cursors (house style in `nx_lib/views/reporting/`), SQL Server T-SQL migration via `scripts/db-migrate.py`, vanilla JS (#191 shim pattern, `window.NX`), Chart.js 4.5.1 (CDN, already on the page), pytest (integration against NEXORA_TEST), Playwright e2e (CI-only, run locally with `NEXORA_E2E_PORT`).

**Spec:** `docs/superpowers/specs/2026-09-08-reporting-chart-annotations-design.md` — its Decisions table is authoritative. Issue: #284.

## Global Constraints

- Per-report, **owner-only writes**, **Simple tab only**, bucket-snapped (`BucketKey` = the chart's `labels[i]` string, e.g. `2026-09-01`), no annotations on unsaved reports, no `chartjs-plugin-annotation`.
- `Text` ≤ 500 chars after strip, `BucketKey` ≤ 64 chars; the server does **not** verify the bucket exists (spec §2, `ponytail:` comment).
- Migration number **0123** (claimed in #284). Run `python scripts/db-migrate.py --env INT --dry-run` before creating the file; if 0123 is taken, take the next free number and say so in the commit body.
- Hand-built URLs in JS go through `RS.api` (= `NX.apiSafe`, which prefixes `API_PREFIX`); no inline `onclick=` (CSP on PROD; `tests/unit/test_no_inline_event_handlers.py`).
- Templates are cached for the process lifetime: `bin\nx.ps1 -r` after every template edit before a browser check.
- Never `--no-verify`. If the SQL hooks block on unrelated INT drift, `SQL_SYNC_SKIP=1 git commit ...`.
- **Commit only — no push, no PR this session** (owner instruction 2026-09-08).

---

## Context an engineer needs (read first)

- **Branch / worktree:** `feat/284-reporting-chart-annotations` in worktree `.claude/worktrees/feat-chart-annotations` (cut from `origin/main` @ `aba4df2e`). Execute there. The main checkout `C:\dev\nexora` sits on a peer's branch `refactor/255-admin-nav-tenancy-labels` — never touch it.
- **Worktree has no secrets or venv.** `env/*.env` are gitignored; a deny rule blocks Claude from copying them, so the **owner** runs `cp ../../../env/INT.env ../../../env/TEST.env env/` inside the worktree before Task 1 (never commit them). The venv lives in the main checkout: `$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"` before any `pytest` / `python scripts/...`.
- **In-flight work:** `feat/reporting-contribution-analysis` (20 commits, unpushed) and worktree `plan-report-layouts` both edit `static/js/reporting_simple_chart.js`, `static/css/reporting.css`, `docs/howto/reporting*.md`, `templates/_reporting_help.html` and `CHANGELOG.md`. Keep every edit here **append-only or inside a new function** so whichever lands second re-anchors trivially. `chartConfigFor` is also consumed by the dashboard's whole-report card via `window.ReportingSimple` — the `opts.annotations` parameter must default to "none" so that surface is unchanged.
- **Test DB:** `sql/test/schema.sql` + `sql/test/seed.sql`, reset with `python scripts/test_db_reset.py`. Migrations do **not** run against it — Task 1 mirrors the table into `schema.sql` by hand. Users: `admin@test.local` (TestAdmin, every permission) and `noai@test.local` (also TestAdmin — the second user with `reporting.view`, used as the *non-owner*); `user@test.local` has only `dashboard.view` and 403s on every `/api/reporting/*` route before ownership is even checked.
- **Shared NEXORA_TEST lock:** a peer's pytest run can hold `sp_getapplock` for minutes; runs queue, never kill the holder.
- **Simple-tab chart facts:** `mountChart(def, columns, rows, forecast)` in `reporting_simple_chart.js` builds `RS.state.chartData` (`{labels, rawX, datasets, forecastStart, type}`) then calls `renderChart(type)`, which calls `chartConfigFor(d, type, def, { onDrill: RS.drillFromChart })` and does `RS.state.chart = new Chart(RS.el('rsChartCanvas'), built.config)`. `labels[i]` for a date grain is already the ISO bucket start (`2026-09-01`); forecast buckets are appended at index ≥ `forecastStart`. The legend filter and `onClick` already skip datasets tagged `_band` / `_forecast` — the annotation dataset adds a third tag `_nxAnnotations`.
- **Where the open report lives:** `RS.state.current = { def, name, reportId, owned, canEdit, ... }` — set by `openReport(r)` in `reporting_simple_library.js` (saved report), `openDefinition` (AI, `reportId: null`), the wizard (`reportId: null`), and updated by `persistCurrent(name)` in `reporting_simple.js` after a first save (`cur.reportId = (res.data && res.data.id) || null;`).
- **Script order** (`templates/js/_reporting_simple_js.html`): chart.js loads before `reporting_simple.js`; the new module loads **after** `reporting_simple_chart.js` and reads `RS.el = RS.el || window.NX.el` defensively like the others.
- **Migrations needed: YES** (0123). **i18n needed: YES** (Task 9). **Deploy excludes: none.** **Env keys: none.** **New permission: none.**

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | Table `dbo.ReportAnnotations`, FK cascade from `dbo.Reports`. | Spec §1; deleting a report takes its notes. |
| D2 | Writes gated by `_is_report_owner`, reads by a new `_can_view_report` lifted from `api_reports_get`'s `WHERE`. | Spec decisions; no permission code, no migration row in `dbo.Permission`. |
| D3 | GET/POST/DELETE only — no PUT. | Spec "out of scope": delete + re-add covers edit. |
| D4 | Marker = a second Chart.js dataset (`type:'line'`, `showLine:false`, `pointStyle:'triangle'`) at `y = 0` on the primary axis, tagged `_nxAnnotations`. Skipped on pie/doughnut. | No new dependency; the legend/drill code already has a tag-skip idiom. |
| D5 | New file `static/js/reporting_simple_annotations.js` instead of growing `reporting_simple_chart.js` (660 lines). | Same split pattern as result/library/wizard/chart. |
| D6 | Add = **Alt+click** a chart element **or** the list header's "Add annotation" button (which asks for the bucket via a `<select>` of `labels[0..forecastStart)`). Plain click keeps drilling. | Spec §3; drill-through keeps its primary gesture. |
| D7 | Bucket key stored = `RS.state.chartData.labels[index]` verbatim. | Spec: raw chart label, never the prettified tick. |
| D8 | Non-owner / unsaved report: no "Add" button, Alt+click falls through to drill, list is read-only (no `×`). | Spec §3. |

## Owner actions

- Copy `env/INT.env` and `env/TEST.env` into the worktree (see Context) before Task 1.
- After Task 1's commit, confirm INT shows the table: `python scripts/db-migrate.py --env INT --dry-run` prints nothing pending.
- Push + PR when ready (not this session).

---

# PHASE 1 — Data

### Task 1: Migration 0123 + test-schema mirror

**Files:**
- Create: `sql/_migrations/NexoraDB/0123_report_annotations.sql`
- Modify: `sql/test/schema.sql` (append after the `dbo.ReportSchedules` block)
- Auto-generated on commit (stage it): `sql/NexoraDB/Tables/dbo.ReportAnnotations.sql`

**Interfaces:**
- Produces: table `dbo.ReportAnnotations(AnnotationID, ReportID, BucketKey, Text, CreatedBy, CreatedAt)` in INT and NEXORA_TEST. Every later task reads/writes it.

- [ ] **Step 1: Check the number is free**

Run: `python scripts/db-migrate.py --env INT --dry-run`
Expected: no pending migration named `0123_*`. If `0123` already exists under `sql/_migrations/NexoraDB/`, use the next free number everywhere below.

- [ ] **Step 2: Create `sql/_migrations/NexoraDB/0123_report_annotations.sql`**

```sql
-- 0123_report_annotations.sql
-- Chart annotations (#284): a report owner pins a short dated note on the
-- Simple-tab chart. BucketKey is the chart's own label string for the bucket
-- ('2026-09-01' for a month grain, the category value for a category axis).
-- Owner-gated in code (nx_lib/views/reporting/annotations.py); no permission
-- row. Idempotent.

IF OBJECT_ID(N'dbo.ReportAnnotations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportAnnotations (
        AnnotationID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportAnnotations PRIMARY KEY,
        ReportID     INT NOT NULL,
        BucketKey    NVARCHAR(64) NOT NULL,
        Text         NVARCHAR(500) NOT NULL,
        CreatedBy    INT NOT NULL,
        CreatedAt    DATETIME2(0) NOT NULL CONSTRAINT DF_ReportAnnotations_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ReportAnnotations_Reports FOREIGN KEY (ReportID)
            REFERENCES dbo.Reports(ReportID) ON DELETE CASCADE,
        CONSTRAINT FK_ReportAnnotations_Users FOREIGN KEY (CreatedBy)
            REFERENCES dbo.Users(userID)
    );
    CREATE INDEX IX_ReportAnnotations_Report ON dbo.ReportAnnotations(ReportID, BucketKey);
END;
GO
```

- [ ] **Step 3: Mirror it into `sql/test/schema.sql`**

Find the block ending with `CREATE INDEX IX_ReportSchedules_Due ON dbo.ReportSchedules(Enabled, NextRunAt);` followed by `END;` and `GO`. Directly **after** that `GO`, paste the same `IF OBJECT_ID(N'dbo.ReportAnnotations' ...` block from Step 2 (including its `GO`).

- [ ] **Step 4: Reset the test DB and prove the table exists**

Run:
```powershell
$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"
python scripts/test_db_reset.py
python -c "from nx_lib.db import engine_nexora_db as e; from sqlalchemy import text; print(e.connect().execute(text(\"SELECT OBJECT_ID('dbo.ReportAnnotations','U')\")).scalar())"
```
(`ENVIRONMENT=TEST` must be set in that shell: `$env:ENVIRONMENT = 'TEST'` — restore it afterwards.)
Expected: a non-`None` integer.

- [ ] **Step 5: Commit** (the `sql-migrate-int` hook applies 0123 to INT and `sql-sync-check` regenerates the dump — stage the dump in the same commit; if the hook fails on unrelated drift, re-run with `SQL_SYNC_SKIP=1`)

```powershell
git add sql/_migrations/NexoraDB/0123_report_annotations.sql sql/test/schema.sql
git commit -m "feat(reporting): ReportAnnotations table (migration 0123)" -m "Per-report chart annotations for #284: report id, chart bucket key, text, author. Cascades with the report. Mirrored into sql/test/schema.sql."
git add sql/NexoraDB/Tables/dbo.ReportAnnotations.sql
git commit --amend --no-edit
```

---

# PHASE 2 — API

### Task 2: `_can_view_report` helper

**Files:**
- Modify: `nx_lib/views/reporting/reports.py` (add after `_is_report_owner`)
- Test: `tests/integration/test_reporting_annotations_api.py` (new file — Task 3 extends it)

**Interfaces:**
- Produces: `_can_view_report(report_id: int, userid: int) -> bool` — True when the user owns the report, the report's `Visibility = 'shared'`, or a `dbo.ReportShares` row grants it. Mirrors the `WHERE` clause in `api_reports_get`.

- [ ] **Step 1: Write the failing test**

```python
"""Integration: /api/reporting/reports/<id>/annotations (#284)."""

from nx_lib.views.reporting.reports import _can_view_report


def _create_report(client, name="Annotation Test"):
    resp = client.post(
        "/api/reporting/reports",
        json={
            "name": name,
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": name,
            },
        },
    )
    assert resp.status_code == 200, resp.data
    return resp.get_json()["id"]


def _userid(client):
    with client.session_transaction() as s:
        return s["userid"]


def test_can_view_report_owner_shared_and_granted(admin_client, login):
    rid = _create_report(admin_client)
    try:
        owner = _userid(admin_client)
        assert _can_view_report(rid, owner) is True

        other_client = login(username="noai@test.local")
        other = _userid(other_client)
        assert _can_view_report(rid, other) is False

        admin_client.post(f"/api/reporting/reports/{rid}/shares", json={"visibility": "shared"})
        assert _can_view_report(rid, other) is True
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")
```

Note: `login` and `admin_client` both come from `tests/conftest.py`; calling `login(...)` a second time re-logs the same Flask test client as the other user, so read `owner` **before** switching.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/integration/test_reporting_annotations_api.py -q --no-cov`
Expected: `ImportError: cannot import name '_can_view_report'`.

- [ ] **Step 3: Implement** — in `reports.py`, directly after the function `def _is_report_owner(report_id, userid):` block, add:

```python
def _can_view_report(report_id, userid):
    """True when ``userid`` may open the report: owner, ``Visibility='shared'``,
    or an explicit ``dbo.ReportShares`` grant. Same rule ``api_reports_get``
    applies in its WHERE clause; annotations (#284) read through this."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM dbo.Reports r "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.ReportID = ? "
            "  AND (r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ?)",
            (userid, report_id, userid, userid),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()
```

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_reporting_annotations_api.py -q --no-cov`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add nx_lib/views/reporting/reports.py tests/integration/test_reporting_annotations_api.py
git commit -m "feat(reporting): _can_view_report helper for read-gated report children" -m "Lifts the owner / shared / explicit-share rule out of api_reports_get's WHERE clause so the annotations routes (#284) can reuse it."
```

### Task 3: Annotations routes

**Files:**
- Create: `nx_lib/views/reporting/annotations.py`
- Modify: `nx_lib/views/reporting/__init__.py` (import line, docstring route table, `register_routes` fan-out)
- Test: `tests/integration/test_reporting_annotations_api.py` (extend)

**Interfaces:**
- Consumes: `_is_report_owner`, `_can_view_report` (Task 2), `dbo.ReportAnnotations` (Task 1).
- Produces:
  - `GET /api/reporting/reports/<int:report_id>/annotations` → `200 [{id, bucket, text, author, createdAt}]` ordered by `BucketKey, AnnotationID`; `404` when `_can_view_report` is false.
  - `POST …/annotations` body `{bucket, text}` → `200 {id, ok:true}`; `404` non-owner; `400 {error}` on blank/over-long fields.
  - `DELETE …/annotations/<int:annotation_id>` → `200 {ok:true}`; `404` non-owner or foreign annotation.
  - Endpoint names `reporting_reports_annotations_get|create|delete`.

- [ ] **Step 1: Append the failing tests** to `tests/integration/test_reporting_annotations_api.py`

```python
def test_annotations_without_reporting_perm_403(user_client):
    assert user_client.get("/api/reporting/reports/1/annotations").status_code == 403


def test_annotation_crud_owner(admin_client):
    rid = _create_report(admin_client)
    try:
        assert admin_client.get(f"/api/reporting/reports/{rid}/annotations").get_json() == []
        cr = admin_client.post(
            f"/api/reporting/reports/{rid}/annotations",
            json={"bucket": "2026-09-01", "text": "  Mailroom outage  "},
        )
        assert cr.status_code == 200, cr.data
        aid = cr.get_json()["id"]
        lst = admin_client.get(f"/api/reporting/reports/{rid}/annotations").get_json()
        assert len(lst) == 1
        assert lst[0]["id"] == aid
        assert lst[0]["bucket"] == "2026-09-01"
        assert lst[0]["text"] == "Mailroom outage"
        assert lst[0]["author"]
        assert lst[0]["createdAt"]
        assert (
            admin_client.delete(f"/api/reporting/reports/{rid}/annotations/{aid}").status_code
            == 200
        )
        assert admin_client.get(f"/api/reporting/reports/{rid}/annotations").get_json() == []
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_annotation_validation_400(admin_client):
    rid = _create_report(admin_client)
    try:
        url = f"/api/reporting/reports/{rid}/annotations"
        assert admin_client.post(url, json={"bucket": "2026-09-01", "text": "   "}).status_code == 400
        assert admin_client.post(url, json={"bucket": "", "text": "x"}).status_code == 400
        assert admin_client.post(url, json={"bucket": "2026-09-01", "text": "x" * 501}).status_code == 400
        assert admin_client.post(url, json={"bucket": "b" * 65, "text": "x"}).status_code == 400
        assert admin_client.post(url, json={"bucket": "2026-09-01", "text": "x" * 500}).status_code == 200
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_annotation_non_owner_reads_shared_but_cannot_write(admin_client, login):
    rid = _create_report(admin_client)
    try:
        cr = admin_client.post(
            f"/api/reporting/reports/{rid}/annotations",
            json={"bucket": "2026-09-01", "text": "owner note"},
        )
        aid = cr.get_json()["id"]
        admin_client.post(f"/api/reporting/reports/{rid}/shares", json={"visibility": "shared"})

        other = login(username="noai@test.local")
        assert other.get(f"/api/reporting/reports/{rid}/annotations").status_code == 200
        assert (
            other.post(
                f"/api/reporting/reports/{rid}/annotations",
                json={"bucket": "2026-09-01", "text": "intruder"},
            ).status_code
            == 404
        )
        assert other.delete(f"/api/reporting/reports/{rid}/annotations/{aid}").status_code == 404
    finally:
        admin = login(username="admin@test.local")
        admin.delete(f"/api/reporting/reports/{rid}")


def test_annotation_private_report_hidden_from_non_owner(admin_client, login):
    rid = _create_report(admin_client)
    try:
        other = login(username="noai@test.local")
        assert other.get(f"/api/reporting/reports/{rid}/annotations").status_code == 404
    finally:
        admin = login(username="admin@test.local")
        admin.delete(f"/api/reporting/reports/{rid}")


def test_annotation_delete_foreign_id_404(admin_client):
    rid_a = _create_report(admin_client, "A")
    rid_b = _create_report(admin_client, "B")
    try:
        aid = admin_client.post(
            f"/api/reporting/reports/{rid_a}/annotations",
            json={"bucket": "2026-09-01", "text": "on A"},
        ).get_json()["id"]
        assert (
            admin_client.delete(f"/api/reporting/reports/{rid_b}/annotations/{aid}").status_code
            == 404
        )
        assert len(admin_client.get(f"/api/reporting/reports/{rid_a}/annotations").get_json()) == 1
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid_a}")
        admin_client.delete(f"/api/reporting/reports/{rid_b}")


def test_annotation_cascades_with_report(admin_client):
    from sqlalchemy import text

    from nx_lib.db import engine_nexora_db

    rid = _create_report(admin_client)
    admin_client.post(
        f"/api/reporting/reports/{rid}/annotations",
        json={"bucket": "2026-09-01", "text": "gone with the report"},
    )
    admin_client.delete(f"/api/reporting/reports/{rid}")
    with engine_nexora_db.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM dbo.ReportAnnotations WHERE ReportID = :r"), {"r": rid}
        ).scalar()
    assert n == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/integration/test_reporting_annotations_api.py -q --no-cov`
Expected: the new tests fail with `404` where `200`/`400` is expected (route not registered); `test_annotations_without_reporting_perm_403` may already pass (unknown route under `/api/reporting` still hits the login/permission layer first — fine either way).

- [ ] **Step 3: Create `nx_lib/views/reporting/annotations.py`**

```python
"""Reporting: chart annotations (#284).

``/api/reporting/reports/<id>/annotations[/<aid>]`` -- a report owner pins a
short note on one chart bucket; anyone who can open the report reads them.
Writes are gated by ``reports._is_report_owner``, reads by
``reports._can_view_report``. No permission code of its own (spec D2).
"""

from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import limiter
from ...security import require_permission
from .reports import _can_view_report, _is_report_owner

TEXT_MAX = 500
BUCKET_MAX = 64


def _serialize(r):
    return {
        "id": r.AnnotationID,
        "bucket": r.BucketKey,
        "text": r.Text,
        "author": r.Author,
        "createdAt": str(r.CreatedAt) if r.CreatedAt else None,
    }


def _validate(p):
    """Return (bucket, text) or raise ValueError with a user-facing message.

    ponytail: format-only validation; the server does not re-run the report to
    check the bucket exists. Add that if orphan rows ever show up.
    """
    bucket = str(p.get("bucket") or "").strip()
    text = str(p.get("text") or "").strip()
    if not bucket or len(bucket) > BUCKET_MAX:
        raise ValueError(_("Pick a bucket on the chart."))
    if not text:
        raise ValueError(_("Annotation text is required."))
    if len(text) > TEXT_MAX:
        raise ValueError(_("Annotation text is limited to 500 characters."))
    return bucket, text


@require_permission("reporting.view")
def api_reports_annotations_get(report_id):
    userid = session.get("userid")
    if not _can_view_report(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT a.AnnotationID, a.BucketKey, a.Text, a.CreatedAt, "
            "       u.Fullname AS Author "
            "FROM dbo.ReportAnnotations a "
            "JOIN dbo.Users u ON u.userID = a.CreatedBy "
            "WHERE a.ReportID = ? "
            "ORDER BY a.BucketKey, a.AnnotationID",
            (report_id,),
        )
        return jsonify([_serialize(r) for r in cur.fetchall()])
    except Exception as e:
        current_app.logger.error(f"reporting annotations list error: {e}")
        return jsonify({"error": _("Could not list annotations")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_annotations_create(report_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    try:
        bucket, text = _validate(request.get_json(silent=True) or {})
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportAnnotations (ReportID, BucketKey, Text, CreatedBy) "
            "OUTPUT INSERTED.AnnotationID VALUES (?, ?, ?, ?)",
            (report_id, bucket, text, userid),
        )
        inserted = cur.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        conn.commit()
        return jsonify({"id": inserted[0], "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting annotations create error: {e}")
        return jsonify({"error": _("Could not save annotation")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_annotations_delete(report_id, annotation_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportAnnotations WHERE AnnotationID = ? AND ReportID = ?",
            (annotation_id, report_id),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting annotations delete error: {e}")
        return jsonify({"error": _("Could not delete annotation")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/annotations",
        endpoint="reporting_reports_annotations_get",
        view_func=api_reports_annotations_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/annotations",
        endpoint="reporting_reports_annotations_create",
        view_func=api_reports_annotations_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/annotations/<int:annotation_id>",
        endpoint="reporting_reports_annotations_delete",
        view_func=api_reports_annotations_delete,
        methods=["DELETE"],
    )
```

- [ ] **Step 4: Register the module** in `nx_lib/views/reporting/__init__.py`

1. In the docstring route table, after the line containing `GET/POST/PUT/DELETE /api/reporting/reports/<id>/schedules[/<sid>]  owner: schedules`, add:
   `  GET/POST/DELETE /api/reporting/reports/<id>/annotations[/<aid>]  owner/view: annotations`
2. Change `from . import admin_registry, ai, catalog, export, health, pages, reports, run, schedules` to `from . import admin_registry, ai, annotations, catalog, export, health, pages, reports, run, schedules`.
3. In `register_routes`, directly after the line `    schedules.register_routes(app)`, add `    annotations.register_routes(app)`.

- [ ] **Step 5: Run green**

Run: `pytest tests/integration/test_reporting_annotations_api.py tests/integration/test_reporting_routes.py -q --no-cov`
Expected: all pass (annotations file: 8 passed).

- [ ] **Step 6: Commit**

```powershell
git add nx_lib/views/reporting/annotations.py nx_lib/views/reporting/__init__.py tests/integration/test_reporting_annotations_api.py
git commit -m "feat(reporting): annotations API - list, create, delete per report" -m "Owner-gated writes, view-gated reads, format-only validation (spec D2/D3). Registered beside schedules in the reporting package."
```

---

# PHASE 3 — Front end (Simple tab)

### Task 4: Strings, markup, CSS

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (strings + script tag)
- Modify: `templates/_reporting_simple.html` (list + popover markup)
- Modify: `static/css/reporting.css` (append)

**Interfaces:**
- Produces: `window.NX_I18N_REPORTING_SIMPLE.annotations*` strings; DOM ids `rsAnnotations`, `rsAnnotationsList`, `rsAnnotationAdd`, `rsAnnotationPop`, `rsAnnotationBucket`, `rsAnnotationBucketSelect`, `rsAnnotationText`, `rsAnnotationSave`, `rsAnnotationCancel`; test ids `rs-annotations`, `rs-annotation-add`, `rs-annotation-pop`, `rs-annotation-text`, `rs-annotation-save`, `rs-annotation-row`, `rs-annotation-delete`.

- [ ] **Step 1: Strings** — in `templates/js/_reporting_simple_js.html`, inside the object `window.NX_I18N_REPORTING_SIMPLE = {`, add after the line `forecastLabel: {{ _("Forecast")|tojson }},`:

```jinja
    annotationsTitle: {{ _("Annotations")|tojson }},
    annotationAdd: {{ _("Add annotation")|tojson }},
    annotationHint: {{ _("Alt+click a bar or point to annotate it.")|tojson }},
    annotationSaveFirst: {{ _("Save the report to add annotations.")|tojson }},
    annotationPlaceholder: {{ _("What happened here? (e.g. “mailroom outage”)")|tojson }},
    annotationCouldNotSave: {{ _("Could not save the annotation.")|tojson }},
    annotationCouldNotDelete: {{ _("Could not delete the annotation.")|tojson }},
    annotationDelete: {{ _("Delete annotation")|tojson }},
    annotationMarker: {{ _("Annotation")|tojson }},
```

- [ ] **Step 2: Script tag** — in the same file, find the `<script>` tag that loads `reporting_simple_chart.js` (grep `reporting_simple_chart.js`) and add directly **after** it, same form (`static_v(...)`, `nonce` if the neighbours carry one):

```jinja
<script src="{{ static_v('js/reporting_simple_annotations.js') }}"></script>
```

- [ ] **Step 3: Markup** — in `templates/_reporting_simple.html`, directly after the line `<div class="rs-chart-body"><canvas id="rsChartCanvas"></canvas></div>` add:

```jinja
        {# Chart annotations (#284): owner-only Add + popover, read-only list
           for everyone else. Filled by static/js/reporting_simple_annotations.js. #}
        <div id="rsAnnotations" class="rs-annotations" hidden data-testid="rs-annotations">
          <div class="rs-annotations-head">
            <span class="rs-annotations-title">{{ _("Annotations") }}</span>
            <button type="button" class="reporting-link" id="rsAnnotationAdd" hidden data-testid="rs-annotation-add">{{ _("Add annotation") }}</button>
          </div>
          <ul id="rsAnnotationsList" class="rs-annotations-list"></ul>
        </div>
        <div id="rsAnnotationPop" class="rs-annotation-pop" hidden role="dialog" aria-labelledby="rsAnnotationBucket" data-testid="rs-annotation-pop">
          <div class="rs-annotation-pop-bucket" id="rsAnnotationBucket"></div>
          <select id="rsAnnotationBucketSelect" class="rs-annotation-bucket-select" hidden aria-label="{{ _('Bucket') }}" data-testid="rs-annotation-bucket-select"></select>
          <input type="text" id="rsAnnotationText" maxlength="500" placeholder="{{ _('What happened here? (e.g. “mailroom outage”)') }}" aria-label="{{ _('Annotation text') }}" data-testid="rs-annotation-text">
          <div class="rs-annotation-pop-actions">
            <button type="button" class="reporting-link" id="rsAnnotationCancel" data-testid="rs-annotation-cancel">{{ _("Cancel") }}</button>
            <button type="button" class="reporting-btn" id="rsAnnotationSave" data-testid="rs-annotation-save">{{ _("Save") }}</button>
          </div>
        </div>
```

Confirm `reporting-btn` and `reporting-link` classes exist: `grep -c "\.reporting-btn\b\|\.reporting-link\b" static/css/reporting.css` (both > 0; if `.reporting-btn` is missing, use the class the `rsSave` button carries — `grep -n 'id="rsSave"' templates/_reporting_simple.html`).

- [ ] **Step 4: CSS** — append to `static/css/reporting.css`:

```css
/* Chart annotations (#284) -- list under the Simple chart + add popover. */
.rs-annotations { margin-top: 8px; font-size: 13px; }
.rs-annotations-head { display: flex; align-items: center; gap: 10px; color: var(--nx-text-meta); }
.rs-annotations-title { font-weight: 600; }
.rs-annotations-list { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.rs-annotations-list li { display: flex; align-items: baseline; gap: 8px; }
.rs-annotation-bucket { color: var(--nx-text-meta); white-space: nowrap; }
.rs-annotation-author { color: var(--nx-text-meta); margin-left: auto; white-space: nowrap; }
.rs-annotation-delete { background: none; border: 0; color: var(--nx-text-meta); cursor: pointer; padding: 0 4px; }
.rs-annotation-delete:hover { color: var(--nx-danger, #b91c1c); }
.rs-annotation-pop { position: absolute; z-index: 30; width: min(320px, 90vw); padding: 10px; background: var(--nx-card); border: 1px solid var(--nx-border); border-radius: calc(var(--nx-radius-scale, 1) * 8px); box-shadow: 0 8px 24px rgba(0,0,0,.12); display: flex; flex-direction: column; gap: 8px; }
.rs-annotation-pop-bucket { font-weight: 600; }
.rs-annotation-pop input, .rs-annotation-bucket-select { width: 100%; box-sizing: border-box; }
.rs-annotation-pop-actions { display: flex; justify-content: flex-end; gap: 8px; }
```

The chart card needs a positioning context for the popover: append `#rsChartCard { position: relative; }` too, unless `grep -n "#rsChartCard" static/css/reporting.css` already shows `position: relative`.

- [ ] **Step 5: Restart and eyeball** — `bin\nx.ps1 -r`, open `/reporting`, confirm no console error and no visible change (everything is `hidden`).

- [ ] **Step 6: Commit**

```powershell
git add templates/js/_reporting_simple_js.html templates/_reporting_simple.html static/css/reporting.css
git commit -m "feat(reporting): annotation list and popover markup, strings, styles" -m "Hidden scaffolding for #284; the JS module in the next commit fills it. Script tag for reporting_simple_annotations.js is already wired."
```

(Between this commit and Task 5 the page 404s the new script on load — harmless; do Task 5 immediately.)

### Task 5: `reporting_simple_annotations.js` + chart hook

**Files:**
- Create: `static/js/reporting_simple_annotations.js`
- Modify: `static/js/reporting_simple_chart.js` (`chartConfigFor`: marker dataset, legend filter, `onClick`; `renderChart`: pass annotations)
- Modify: `static/js/reporting_simple_library.js` (`openReport`: load after `RS.state.current` is set)
- Modify: `static/js/reporting_simple.js` (`persistCurrent`: load after a first save; `setView`: nothing)

**Interfaces:**
- Consumes: API from Task 3; DOM/ids from Task 4; `RS.state.current.reportId/owned`, `RS.state.chartData.labels/forecastStart`, `RS.renderChart`, `RS.api`, `RS.el`, `RS.esc`, `RS.I18N`, `window.NX.toast`.
- Produces on `window.ReportingSimple` namespace (`RS`):
  - `RS.annotations.load(reportId)` — fetches, stores `RS.annotations.list`, re-renders chart + list. `load(null)` clears.
  - `RS.annotations.list` — `[{id, bucket, text, author, createdAt}]`.
  - `RS.annotations.byBucket()` — `{bucket: [text, ...]}` for the chart.
  - `RS.annotations.openPopover(index)` — index into `chartData.labels`, or `null` to show the bucket `<select>`.
  - `RS.annotations.renderList()`.
  - `chartConfigFor(d, type, def, opts)` accepts `opts.annotations` = the `byBucket()` map (default none) and `opts.onAnnotate(index)` (Alt+click / marker click handler; default none).

- [ ] **Step 1: Chart hook — marker dataset** in `static/js/reporting_simple_chart.js`, inside `chartConfigFor`. Find the block starting `var partialIdx = (grain0 && !circular) ? d.labels.indexOf(currentBucketStart(grain0)) : -1;` and its `if (partialIdx >= 0) { datasets = datasets.map(...) }`. Directly **after** that `if` block (before the `var config = {` / `config` construction), add:

```js
    // Chart annotations (#284): one marker dataset, a triangle at y=0 on each
    // annotated bucket. Tagged _nxAnnotations so the legend filter and the
    // drill click-handler treat it like _band/_forecast. Never on pie/doughnut.
    var annMap = (opts && opts.annotations) || null;
    if (annMap && !circular) {
      var annData = d.labels.map(function (lbl, i) {
        return (i < (d.forecastStart == null ? d.labels.length : d.forecastStart) && annMap[lbl]) ? 0 : null;
      });
      if (annData.some(function (v) { return v !== null; })) {
        datasets = datasets.concat([{
          _nxAnnotations: true,
          label: RS.I18N.annotationMarker,
          type: 'line',
          showLine: false,
          data: annData,
          pointStyle: 'triangle',
          pointRadius: 7,
          pointHoverRadius: 9,
          pointBackgroundColor: '#f59e0b',
          pointBorderColor: '#b45309',
          pointBorderWidth: 1,
          yAxisID: 'y',
          order: -1
        }]);
      }
    }
```

- [ ] **Step 2: Legend filter + tooltip + click** in the same function's `config`:
  1. In the legend `filter`, change `return !(ds._band || ds._forecast);` to `return !(ds._band || ds._forecast || ds._nxAnnotations);`.
  2. In the tooltip `label` callback, before `var raw = ctx.parsed;` add:
     ```js
                                  if (ctx.dataset._nxAnnotations) {
                                    return ((annMap || {})[ctx.label] || []).join(' · ');
                                  }
     ```
  3. In `onClick`, replace the two lines
     ```js
                   if (dsHit._forecast || dsHit._band) return;
                   if (d.forecastStart != null && d.forecast && els[0].index >= d.forecastStart) return;
     ```
     with
     ```js
                   if (dsHit._forecast || dsHit._band) return;
                   if (d.forecastStart != null && d.forecast && els[0].index >= d.forecastStart) return;
                   var onAnnotate = opts && opts.onAnnotate;
                   if (onAnnotate && (dsHit._nxAnnotations || (evt.native && evt.native.altKey))) {
                     onAnnotate(els[0].index); return;
                   }
                   if (dsHit._nxAnnotations) return;
     ```

- [ ] **Step 3: `renderChart` passes the hooks** — change

```js
    var built = chartConfigFor(d, type, (RS.state.current && RS.state.current.def) || {},
                               { onDrill: RS.drillFromChart });
```
to
```js
    var built = chartConfigFor(d, type, (RS.state.current && RS.state.current.def) || {},
                               { onDrill: RS.drillFromChart,
                                 annotations: RS.annotations ? RS.annotations.byBucket() : null,
                                 onAnnotate: RS.annotations ? RS.annotations.onChartAnnotate : null });
```

`RS.annotations` is defined by the new module, which loads after this file; `renderChart` runs later at user time, so the guard is only for the dashboard's `window.ReportingSimple` consumer.

- [ ] **Step 4: Create `static/js/reporting_simple_annotations.js`**

```js
// Simple tab: chart annotations (#284). Loads the open report's annotations,
// feeds chartConfigFor a bucket->texts map (marker dataset), renders the list
// under the chart and owns the add popover. Owner-only chrome; viewers get
// the markers and a read-only list. Loads AFTER reporting_simple_chart.js.
(function () {
  'use strict';
  var RS = window.ReportingSimple = window.ReportingSimple || {};
  RS.el = RS.el || window.NX.el;
  RS.api = RS.api || window.NX.apiSafe;
  RS.esc = RS.esc || window.NX.esc;

  var A = RS.annotations = { list: [], reportId: null };
  var popIndex = null;   // labels[] index the popover is for, or null (select)

  function canEdit() {
    var cur = RS.state && RS.state.current;
    return !!(cur && cur.reportId && cur.owned);
  }

  function chartBuckets() {
    var cd = RS.state && RS.state.chartData;
    if (!cd || !cd.labels) return [];
    var n = cd.forecastStart == null ? cd.labels.length : cd.forecastStart;
    return cd.labels.slice(0, n);
  }

  A.byBucket = function () {
    var m = {};
    A.list.forEach(function (a) { (m[a.bucket] = m[a.bucket] || []).push(a.text); });
    return m;
  };

  A.load = async function (reportId) {
    A.reportId = reportId || null;
    A.list = [];
    if (reportId) {
      var res = await RS.api('/api/reporting/reports/' + reportId + '/annotations');
      // 403/404 (unshared meanwhile) reads as "no annotations" -- no toast.
      if (res.ok && Array.isArray(res.data)) A.list = res.data;
    }
    A.refresh();
  };

  // Re-draw the chart (marker dataset) and the list from A.list.
  A.refresh = function () {
    if (RS.state.chartData && RS.state.chart) RS.renderChart(RS.state.chartType || RS.state.chartData.type);
    A.renderList();
  };

  A.renderList = function () {
    var box = RS.el('rsAnnotations'), ul = RS.el('rsAnnotationsList');
    var editable = canEdit();
    RS.el('rsAnnotationAdd').hidden = !editable;
    ul.innerHTML = A.list.map(function (a) {
      return '<li data-testid="rs-annotation-row" data-id="' + a.id + '">' +
        '<span class="rs-annotation-bucket">' + RS.esc(a.bucket) + '</span>' +
        '<span class="rs-annotation-text">' + RS.esc(a.text) + '</span>' +
        '<span class="rs-annotation-author">' + RS.esc(a.author || '') + '</span>' +
        (editable ? '<button type="button" class="rs-annotation-delete" data-id="' + a.id +
                    '" title="' + RS.esc(RS.I18N.annotationDelete) + '" aria-label="' +
                    RS.esc(RS.I18N.annotationDelete) + '" data-testid="rs-annotation-delete">×</button>' : '') +
        '</li>';
    }).join('');
    // Hidden unless there is something to show: rows, or the owner's Add button.
    box.hidden = !(A.list.length || (editable && chartBuckets().length));
  };

  // ----- popover -----
  A.openPopover = function (index, anchor) {
    var pop = RS.el('rsAnnotationPop');
    var sel = RS.el('rsAnnotationBucketSelect');
    var buckets = chartBuckets();
    if (!canEdit() || !buckets.length) return;
    popIndex = (index != null && index < buckets.length) ? index : null;
    RS.el('rsAnnotationBucket').textContent = popIndex != null ? buckets[popIndex] : RS.I18N.annotationAdd;
    sel.hidden = popIndex != null;
    if (popIndex == null) {
      sel.innerHTML = buckets.map(function (b) { return '<option value="' + RS.esc(b) + '">' + RS.esc(b) + '</option>'; }).join('');
    }
    RS.el('rsAnnotationText').value = '';
    pop.hidden = false;
    // Anchor near the click inside the chart card (position:relative), else
    // under the list header.
    var card = RS.el('rsChartCard').getBoundingClientRect();
    if (anchor) {
      pop.style.left = Math.max(8, Math.min(anchor.x - card.left, card.width - 330)) + 'px';
      pop.style.top = (anchor.y - card.top + 8) + 'px';
    } else {
      var head = RS.el('rsAnnotations').getBoundingClientRect();
      pop.style.left = '8px';
      pop.style.top = (head.top - card.top + 24) + 'px';
    }
    RS.el('rsAnnotationText').focus();
  };

  A.closePopover = function () { RS.el('rsAnnotationPop').hidden = true; popIndex = null; };

  // Chart click-handler hook (chartConfigFor opts.onAnnotate): Alt+click on a
  // bucket, or a click on an existing marker.
  A.onChartAnnotate = function (index) {
    if (!canEdit()) { RS.drillFromChart(index, 0); return; }
    var c = RS.state.chart, pt = null;
    if (c && c.canvas) {
      var r = c.canvas.getBoundingClientRect();
      var x = c.scales && c.scales.x ? c.scales.x.getPixelForValue(index) : r.width / 2;
      pt = { x: r.left + x, y: r.top + r.height / 2 };
    }
    A.openPopover(index, pt);
  };

  async function save() {
    var buckets = chartBuckets();
    var bucket = popIndex != null ? buckets[popIndex] : RS.el('rsAnnotationBucketSelect').value;
    var text = RS.el('rsAnnotationText').value.trim();
    if (!bucket || !text || !A.reportId) return;
    var res = await RS.api('/api/reporting/reports/' + A.reportId + '/annotations', {
      method: 'POST', body: JSON.stringify({ bucket: bucket, text: text })
    });
    if (!res.ok) {
      window.NX.toast((res.data && res.data.error) || RS.I18N.annotationCouldNotSave, 'error');
      return;
    }
    var cur = RS.state.current || {};
    A.list.push({ id: res.data.id, bucket: bucket, text: text, author: cur.ownerName || '', createdAt: null });
    A.list.sort(function (a, b) { return a.bucket < b.bucket ? -1 : a.bucket > b.bucket ? 1 : a.id - b.id; });
    A.closePopover();
    A.refresh();
  }

  async function remove(id) {
    if (!A.reportId) return;
    var res = await RS.api('/api/reporting/reports/' + A.reportId + '/annotations/' + id, { method: 'DELETE' });
    if (!res.ok) {
      window.NX.toast((res.data && res.data.error) || RS.I18N.annotationCouldNotDelete, 'error');
      return;
    }
    A.list = A.list.filter(function (a) { return String(a.id) !== String(id); });
    A.refresh();
  }

  // ----- wiring -----
  RS.el('rsAnnotationAdd').addEventListener('click', function () { A.openPopover(null, null); });
  RS.el('rsAnnotationSave').addEventListener('click', save);
  RS.el('rsAnnotationCancel').addEventListener('click', A.closePopover);
  RS.el('rsAnnotationText').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); save(); }
    if (e.key === 'Escape') { e.preventDefault(); A.closePopover(); }
  });
  RS.el('rsAnnotationsList').addEventListener('click', function (e) {
    var btn = e.target.closest('.rs-annotation-delete');
    if (btn) remove(btn.dataset.id);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !RS.el('rsAnnotationPop').hidden) A.closePopover();
  });
}());
```

Check `window.NX.toast`'s signature once (`grep -n "function toast" static/js/nx_core.js`) and match its argument order.

- [ ] **Step 5: Load on open / save, clear otherwise**
  1. `static/js/reporting_simple_library.js`, in `openReport(r)`: after the `RS.state.current = { ... origin: 'library' };` statement and **before** `RS.runCurrent();`, add `if (RS.annotations) RS.annotations.load(r.id);`.
     In `openDefinition(def, name)`: after its `RS.state.current = { ... origin: 'ai' };` add `if (RS.annotations) RS.annotations.load(null);`.
  2. `static/js/reporting_simple_wizard.js`: after the line starting `RS.state.current = { def: def, name: def.title, reportId: null,` (finish the statement — it spans lines), add `if (RS.annotations) RS.annotations.load(null);`.
  3. `static/js/reporting_simple.js`, in `persistCurrent(name)`: inside the `if (!update) { ... }` block, after `cur.canEdit = true;`, add `if (RS.annotations) RS.annotations.load(cur.reportId);`.
  4. `static/js/reporting_simple_chart.js`, at the end of `mountChart` just before `return true;`: add `if (RS.annotations) RS.annotations.renderList();` — and in the early-return branch `if (!dims || !rows.length) { RS.el('rsChartCard').hidden = true; return false; }` nothing changes (the list lives inside the card, so it hides with it).

  Because `load` fires before `runCurrent` resolves, the first `renderChart` may run before the fetch returns; `A.load` calls `A.refresh()` afterwards, which re-renders. Both orders end with markers drawn.

- [ ] **Step 6: Lint gates**

Run: `pytest tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py -q --no-cov`
Expected: pass.

- [ ] **Step 7: Browser check** (`bin\nx.ps1 -r`, then `bin\nx.ps1 -u -b --loginas:ben.streich`, INT): open a saved Simple report with a date breakdown → chart shows; Alt+click a bar → popover with the bucket key; type, Save → triangle marker at that bucket and a row in the list; hover the marker → tooltip shows the text; click `×` → both gone; open an unsaved wizard result → no Add button, Alt+click drills. Screenshots to `var/screenshots/284_annotation_popover.png`, `284_annotation_marker.png`.

- [ ] **Step 8: Commit**

```powershell
git add static/js/reporting_simple_annotations.js static/js/reporting_simple_chart.js static/js/reporting_simple_library.js static/js/reporting_simple_wizard.js static/js/reporting_simple.js
git commit -m "feat(reporting): chart annotations - marker dataset, popover, list" -m "Alt+click a bucket (or Add annotation) to pin a note on a saved report's Simple chart; markers ride a tagged Chart.js dataset, the list sits under the chart. Owner-only chrome, read-only for viewers (#284)."
```

### Task 6: e2e

**Files:**
- Create: `tests/e2e/test_reporting_annotations.py`

**Interfaces:**
- Consumes: test ids from Task 4; API stubs (TEST has no Statistics DB, so `/api/reporting/run` and the report endpoints are stubbed exactly like `tests/e2e/test_reporting_simple.py` does).

- [ ] **Step 1: Write the test**

```python
"""e2e: chart annotations on the Simple tab (#284)."""

import json

from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


# Same stub catalog shape tests/e2e/test_reporting_simple.py uses (WIZ_STUB_*):
# the Simple pane fetches sources + measures at page load, and mountChart's
# metric labels come from that catalog.
STUB_SOURCES = [
    {
        "id": "stub_src",
        "label": "Stub source",
        "kind": "curated",
        "processes": [],
        "fields": [
            {"field": "import_date", "label": "Import date", "type": "date",
             "grainable": True, "filterable": True},
        ],
    }
]
STUB_METRICS = {"stub_src": [{"code": "stub_count", "label": "Stub count", "aggregation": "count"}]}


def _definition():
    return {
        "schemaVersion": 1,
        "source": "stub_src",
        "visualization": "chart",
        "chartType": "bar",
        "title": "e2e annotated",
        "columns": [{"field": "import_date", "grain": "month"}],
        "metrics": [{"metric": "stub_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }


def _json(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def _stub_report(page, owned=True):
    """Register BEFORE goto: library list, catalogs and the report detail all
    fetch as soon as the Simple pane mounts. A non-owned report is listed with
    visibility 'shared' so the library files it under rs-group-shared."""
    row = {
        "id": 4242,
        "name": "e2e annotated",
        "ownerName": "Admin",
        "updatedAt": "2026-07-01T00:00:00Z",
        "visibility": "private" if owned else "shared",
        "owned": owned,
        "kind": "chart",
    }
    page.route("**/api/reporting/sources", lambda r: _json(r, STUB_SOURCES))
    page.route("**/api/reporting/measures", lambda r: _json(r, STUB_METRICS))
    page.route("**/api/reporting/reports", lambda r: _json(r, [row]))
    page.route(
        "**/api/reporting/reports/4242",
        lambda r: _json(r, {"name": row["name"], "definition": _definition(), "owned": owned, "canEdit": owned}),
    )
    page.route(
        "**/api/reporting/run",
        lambda r: _json(
            r,
            {
                "columns": [{"field": "import_date", "header": "Import date"},
                            {"field": "stub_count", "header": "Stub count"}],
                "rows": [["2026-06-01", 10], ["2026-07-01", 14], ["2026-08-01", 9]],
                "truncated": False,
                "rowCount": 3,
                "sql": None,
                "params": [],
                "resolvedDates": [],
            },
        ),
    )


def _stub_annotations(page, store):
    def handler(route):
        req = route.request
        if req.method == "GET":
            _json(route, list(store))
        elif req.method == "POST":
            body = req.post_data_json
            store.append({"id": len(store) + 1, "bucket": body["bucket"], "text": body["text"],
                          "author": "Admin", "createdAt": None})
            _json(route, {"id": store[-1]["id"], "ok": True})
        elif req.method == "DELETE":
            aid = int(req.url.rsplit("/", 1)[1])
            store[:] = [a for a in store if a["id"] != aid]
            _json(route, {"ok": True})

    # "**" so ".../annotations/<id>" matches too; registered AFTER _stub_report so
    # Playwright (last-registered wins) never hands these to the detail stub.
    page.route("**/api/reporting/reports/4242/annotations**", handler)


def test_owner_adds_and_deletes_annotation(nexora_server, page):
    _login(page, nexora_server)
    store = []
    _stub_report(page)
    _stub_annotations(page, store)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e annotated").click()
    expect(page.get_by_test_id("rs-chart-card")).to_be_visible()

    add = page.get_by_test_id("rs-annotation-add")
    expect(add).to_be_visible()
    add.click()
    expect(page.get_by_test_id("rs-annotation-pop")).to_be_visible()
    page.get_by_test_id("rs-annotation-bucket-select").select_option("2026-07-01")
    page.get_by_test_id("rs-annotation-text").fill("Mailroom outage")
    page.get_by_test_id("rs-annotation-save").click()

    expect(page.get_by_test_id("rs-annotation-pop")).to_be_hidden()
    row = page.get_by_test_id("rs-annotation-row")
    expect(row).to_have_count(1)
    expect(row).to_contain_text("2026-07-01")
    expect(row).to_contain_text("Mailroom outage")
    assert store and store[0]["bucket"] == "2026-07-01"
    # The marker rides the chart as a tagged dataset.
    n = page.evaluate("window.ReportingSimple.state.chart.data.datasets.filter(d => d._nxAnnotations).length")
    assert n == 1

    page.get_by_test_id("rs-annotation-delete").click()
    expect(page.get_by_test_id("rs-annotation-row")).to_have_count(0)
    assert store == []


def test_viewer_sees_list_but_no_add(nexora_server, page):
    _login(page, nexora_server)
    store = [{"id": 7, "bucket": "2026-06-01", "text": "New client", "author": "Owner", "createdAt": None}]
    _stub_report(page, owned=False)
    _stub_annotations(page, store)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-shared").get_by_text("e2e annotated").click()
    expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
    expect(page.get_by_test_id("rs-annotation-row")).to_have_count(1)
    expect(page.get_by_test_id("rs-annotation-add")).to_be_hidden()
    expect(page.get_by_test_id("rs-annotation-delete")).to_have_count(0)
```

- [ ] **Step 2: Run**

```powershell
$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"
python scripts/test_db_reset.py
$env:NEXORA_E2E_PORT = 5178; pytest tests/e2e/test_reporting_annotations.py -q --no-cov
```
Expected: `2 passed`. If the library files the shared report elsewhere, the three groups are `rs-group-mine` / `rs-group-shared` / `rs-group-direct` (`templates/_reporting_simple.html`).

- [ ] **Step 3: Commit**

```powershell
git add tests/e2e/test_reporting_annotations.py
git commit -m "test(e2e): chart annotations add, delete, viewer read-only" -m "Stubs the report, run and annotations endpoints; asserts the tagged marker dataset on the live Chart.js instance (#284)."
```

---

# PHASE 4 — Docs, changelog, i18n

### Task 7: Docs + tips panel + changelog

**Files:**
- Modify: `docs/howto/reporting.md` (new section before `## Forecast`)
- Modify: `docs/howto/reporting-guide.md` (new `###` under "Reading the result", after "Click a bar to see the documents behind it")
- Modify: `templates/_reporting_help.html` (one `<li>` under "Checking a number")
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Added`)

- [ ] **Step 1: `docs/howto/reporting.md`** — directly before the line `## Forecast`, insert:

```markdown
## Chart annotations (#284)

A report **owner** can pin a short note on one bucket of the Simple-tab chart —
"new client onboarded", "mailroom outage" — so the chart explains its own bumps.
Everyone who can open the report sees the note as an amber triangle at the foot
of that bucket (hover for the text) and in the **Annotations** list under the
chart.

- **Add:** Alt+click a bar/point, or **Add annotation** in the list header (then
  pick the bucket). Plain click still drills through. Unsaved results (wizard,
  Eddard) have no Add — save first.
- **Delete:** the `×` on the row (owner only). There is no in-place edit.
- **Storage:** `dbo.ReportAnnotations` (migration `0123`) — `ReportID`,
  `BucketKey` (the chart's own label string, `2026-09-01` for a month bucket),
  `Text` ≤ 500, `CreatedBy`, `CreatedAt`. Cascades with the report.
- **API:** `GET/POST /api/reporting/reports/<id>/annotations`,
  `DELETE …/annotations/<aid>` — reads gated by `_can_view_report` (owner,
  shared, or explicit share), writes by `_is_report_owner`. No permission code.
- **Render:** `static/js/reporting_simple_annotations.js` feeds
  `chartConfigFor(..., {annotations})` a bucket→texts map; the marker is a second
  Chart.js dataset tagged `_nxAnnotations` (skipped by legend and drill). Only
  the Simple tab draws it — Advanced and dashboard cards don't (yet).
- **Not verified server-side:** the bucket string is stored as sent; a note on a
  bucket outside the charted window is simply not drawn.

```

- [ ] **Step 2: `docs/howto/reporting-guide.md`** — after the "Click a bar to see the documents behind it" section's last bullet (`- On a distinct-count measure, the drawer says so: ...`) and before its `---`, insert:

```markdown

### Pin a note on the chart

If you own the report, **Alt+click** a bar or point (or use **Add annotation**
under the chart) to pin a short note on that period — "mailroom outage", "new
client onboarded". It shows as a small triangle at the foot of that bar and in
the Annotations list below; everyone you share the report with sees it. Delete
with the `×` on the row. A result you haven't saved yet can't be annotated.
```

- [ ] **Step 3: `templates/_reporting_help.html`** — under `<h4>{{ _("Checking a number") }}</h4>`, after the `<li>` that starts `{{ _("Click a chart bar or a table row to open the documents behind that number;`, add:

```jinja
        <li>{{ _("Own the report? Alt+click a bar to pin a note on that period (“mailroom outage”). It shows as a small triangle on the chart and in the Annotations list below for everyone the report is shared with.") }}</li>
```

- [ ] **Step 4: `CHANGELOG.md`** — under `## [Unreleased]`, add a `### Added` section **above** the existing `### Fixed` (or under the existing `### Added` if one exists):

```markdown
### Added

- **Chart annotations.** The owner of a saved report can Alt+click a bar or
  point on the Simple-tab chart (or use *Add annotation* under it) to pin a
  short dated note — "mailroom outage", "new client onboarded". Everyone the
  report is shared with sees it as a marker on the chart and in a list below.
  New `dbo.ReportAnnotations` (migration `0123`) and
  `/api/reporting/reports/<id>/annotations`. Simple tab only for now. #284
```

- [ ] **Step 5: Verify** — `pytest tests/unit/test_reporting_help_sync.py -q --no-cov` passes; `bin\nx.ps1 -r` and open the tips panel to see the new line.

- [ ] **Step 6: Commit**

```powershell
git add docs/howto/reporting.md docs/howto/reporting-guide.md templates/_reporting_help.html CHANGELOG.md
git commit -m "docs(reporting): chart annotations howto, guide, tips, changelog" -m "User guide and in-app tips updated in the same commit (reporting-help-sync). #284"
```

### Task 8: Translations (de/fr/it)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo` if tracked — check `git ls-files translations | grep -c "\.mo$"`)

- [ ] **Step 1: Run the cycle** — invoke the `nx-i18n` skill (`/nx-i18n`), which runs `pybabel extract -F babel.cfg -o messages.pot .`, `pybabel update -i messages.pot -d translations`, fills the new msgids for de/fr/it, then `pybabel compile -d translations`. New msgids to translate (from Tasks 4 and 7): Annotations, Add annotation, Alt+click a bar or point to annotate it., Save the report to add annotations., What happened here? (e.g. “mailroom outage”), Could not save the annotation., Could not delete the annotation., Delete annotation, Annotation, Bucket, Annotation text, Pick a bucket on the chart., Annotation text is required., Annotation text is limited to 500 characters., Could not list annotations, Could not save annotation, Could not delete annotation, and the tips-panel sentence.

- [ ] **Step 2: Verify** — `pytest tests/unit/test_translations.py -q --no-cov` → pass. Diff-sweep the `.po` files for mangled lines (pybabel silently truncates malformed msgstrs): `git diff --stat translations/` shows only additions of the new ids.

- [ ] **Step 3: Commit**

```powershell
git add messages.pot translations/
git commit -m "chore(i18n): chart annotation strings (de/fr/it)" -m "pybabel extract/update/compile for #284; every new msgid translated, none fuzzy."
```

### Task 9: Full fast-tier gate

- [ ] **Step 1:** `python scripts/test_db_reset.py` then `pytest tests/unit tests/integration -q --no-cov -x` — expected all green (the two rate-limiter tests are known order-dependent; re-run alone if they trip).
- [ ] **Step 2:** `$env:NEXORA_E2E_PORT = 5178; pytest tests/e2e/test_reporting_annotations.py tests/e2e/test_reporting_simple.py -q --no-cov` — green.
- [ ] **Step 3:** No commit; if anything fails, fix in the task that owns the file and commit there.

---

## Gotchas & notes

- **`chartConfigFor` is shared** with the dashboard whole-report card through `window.ReportingSimple.chartConfigFor`; it passes no `opts.annotations`, so nothing changes there. Keep the `annMap` default `null`.
- **Alt+click on macOS** is Option+click — Chart.js exposes `evt.native.altKey` for both. Firefox on Windows may eat Alt for the menu bar on *keyup*, not on click — fine.
- **Forecast buckets** are appended to `labels` at index ≥ `forecastStart`; the marker dataset and the popover `<select>` both cut at `forecastStart` so a note can't land on a forecast bucket.
- **Pie/doughnut** get no marker (no x axis); the list still renders.
- **`RS.state.current.owned`** is what gates the chrome — a `canEdit` share (co-editor) does *not* get Add, per spec (owner only).
- **First save of a wizard result:** `persistCurrent` flips `reportId`, so `load(cur.reportId)` runs and the Add button appears without a re-run.
- **Test DB has no `Statistics` engine** — every e2e stubs `/api/reporting/run`; integration tests create `kind:'sql'` reports and never run them.
- **`noai@test.local`** is the only other seeded user with `reporting.view`; it is denied just `reporting.ai.explain_data` via override.
- **In-flight overlap:** `feat/reporting-contribution-analysis` edits `reporting_simple_chart.js`'s `onClick`-adjacent code? No — it touched `reporting_simple_result.js` and the KPI band; the chart `onClick` block is untouched there. `plan/report-layouts` may restructure the chart card; our markup sits *inside* `#rsChartCard` right after the canvas, so re-anchor on `rsChartCanvas` if it moves.
- **sql-sync hook** regenerates `sql/NexoraDB/Tables/dbo.ReportAnnotations.sql` on the first commit after the migration applies — commit it with Task 1 (amend, as written). If the hook reports unrelated drift under `sql/NexoraDB/`, `git restore -- sql/NexoraDB` for everything except the new file and use `SQL_SYNC_SKIP=1`.
- **Deferred (not in this plan):** Advanced tab + dashboard markers; org-wide annotations; editing in place; exports/schedules/Eddard reading annotations; server-side bucket validation.
