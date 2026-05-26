# Customizable Per-User Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-27-customizable-dashboard-design.md`

**Goal:** Replace the fixed dashboard with a per-user customizable dashboard: drag-resize 12-column grid, three widget types (KPI / time-series / categorical) configurable on metric, dimension, filters, chart type, with a dashboard-wide filter bar, View⇄Edit toggle, drill-down on click, and per-widget compare mode.

**Architecture:** One JSON blob per user in a new `DashboardLayouts` table; one new `FieldMetadata` table for field type/aggregation hints; six new endpoints in `app.py` (layout GET/PUT/reset, widget_data, widget_compare, field_metadata) backed by a single `build_widget_query` builder that translates a widget spec to parameterized SQL. Frontend is a rewrite of `templates/dashboard.html` + `templates/js/_dashboardJS.html` + `static/css/dashboard.css` using Gridstack.js (CDN) for the grid and Chart.js (already loaded) for rendering.

**Tech Stack:** Flask + Jinja2 + Tailwind (CDN) + vanilla JS. Chart.js (already loaded). Gridstack.js v11 (new, jsdelivr CDN — CSP is currently disabled in `app.py:98-134` so no whitelist edit needed). SQL Server via pyodbc / SQLAlchemy engines. Manual verification per task (no test framework — matches the existing project convention).

**Conventions:**
- Repo root: `C:\Users\bes\OneDrive - TCG Informatik AG\Dokumente\nexora`
- Branch: `2.5.53` (current)
- Commit style: short imperative, no trailing period — matches existing log
- **Commits are the user's responsibility.** Each task ends with a "Hand off for review" step that runs `git status` + `git diff --stat` and stops. Do **not** run `git commit` or `git push`. The user reviews and commits themselves.
- Do not touch the unstaged `.gitignore`, `app.py` and `sql/accessManagement/tables/ActiveSessions_asCreate.sql` changes — those belong to a separate in-flight task.
- Run the dev server with `set ENVIRONMENT=INT && python app.py` (Windows). Hit `http://127.0.0.1:8000/dashboard` to verify.
- **No DOM injection from string concatenation.** All JS in this plan uses `document.createElement` + `appendChild` + `textContent`, or clones from `<template>` elements. User-controlled strings are set via `textContent` (never via string-built HTML). Where a static fragment is genuinely safe (no interpolation), use a `<template>` element rather than building HTML in code.

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `sql/config/tables/DashboardLayouts_asCreate.sql` | DDL for the per-user layout JSON table |
| `sql/config/tables/FieldMetadata_asCreate.sql` | DDL for the field-type metadata table |
| `sql/other/FieldMetadata_seed.sql` | Initial seed of known fields (numeric / categorical / date) |
| `static/css/dashboard.css` | Replaces existing dashboard styles; styles for grid, widget chrome, filter bar, drawer, modal |

### Modified files

| Path | Why |
|---|---|
| `app.py` | New: starter-layout helper, JSON validator, `build_widget_query`, six routes (layout GET/PUT/reset, widget_data, widget_compare, field_metadata). Old endpoints kept for now — sunset in a follow-up PR per spec §10. |
| `templates/dashboard.html` | Full rewrite: filter bar + grid container + add-widget FAB + settings drawer + add-widget modal + several `<template>` blocks for repeatable markup. Adds Gridstack CSS/JS from CDN. |
| `templates/js/_dashboardJS.html` | Full rewrite: layout load/save, Gridstack init, edit-mode toggle, three widget renderers, settings drawer, add-widget modal, drill-down, auto-refresh. |
| `messages.pot` + `translations/*/LC_MESSAGES/messages.po`/`.mo` | Regenerated in T24 to pick up new strings. |

### Out of scope for this plan (deferred)

- Deletion of the legacy endpoints (`/api/dashboard/kpi_stats`, `/processed_over_time`, `/hourly_stats`, `/avg_processing_time`, `/recent_activity`, `/set_filter`). They stay live during rollout per spec §10. Removed in a follow-up PR ~1 week after deploy.
- Tables / Top-N / heatmap widgets, multiple dashboards, share, PNG/PDF export, mobile-specific layout, annotations.

---

## Task 1: DDL — `DashboardLayouts` table

**Files:**
- Create: `sql/config/tables/DashboardLayouts_asCreate.sql`

- [ ] **Step 1: Create the file** with this content:

```sql
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[DashboardLayouts](
    [UserID]        [int]           NOT NULL,
    [LayoutJSON]    [nvarchar](max) NOT NULL,
    [SchemaVersion] [int]           NOT NULL CONSTRAINT [DF_DashboardLayouts_SchemaVersion] DEFAULT (1),
    [UpdatedAt]     [datetime2](7)  NOT NULL CONSTRAINT [DF_DashboardLayouts_UpdatedAt] DEFAULT (sysutcdatetime()),
 CONSTRAINT [PK_DashboardLayouts] PRIMARY KEY CLUSTERED
(
    [UserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[DashboardLayouts] WITH CHECK ADD CONSTRAINT [FK_DashboardLayouts_Users] FOREIGN KEY([UserID])
REFERENCES [dbo].[Users] ([userID])
GO
ALTER TABLE [dbo].[DashboardLayouts] CHECK CONSTRAINT [FK_DashboardLayouts_Users]
GO
```

- [ ] **Step 2: Apply manually to INT NexoraDB.** Reference DDL per `CLAUDE.md` is not auto-applied. Open SSMS / Azure Data Studio against the INT NexoraDB and run the file. Confirm `SELECT * FROM DashboardLayouts` returns no rows but no error.

- [ ] **Step 3: Hand off for review.**

```
git status
git diff --stat
```

Stop. Wait for user to commit or instruct otherwise.

---

## Task 2: DDL — `FieldMetadata` table + seed

**Files:**
- Create: `sql/config/tables/FieldMetadata_asCreate.sql`
- Create: `sql/other/FieldMetadata_seed.sql`

- [ ] **Step 1: Create `FieldMetadata_asCreate.sql`:**

```sql
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[FieldMetadata](
    [FieldKey]   [varchar](100) NOT NULL,
    [DataType]   [varchar](20)  NOT NULL,    -- 'numeric' | 'categorical' | 'date' | 'text'
    [Aggregable] [bit]          NOT NULL CONSTRAINT [DF_FieldMetadata_Aggregable] DEFAULT (0),
    [Sortable]   [bit]          NOT NULL CONSTRAINT [DF_FieldMetadata_Sortable] DEFAULT (1),
 CONSTRAINT [PK_FieldMetadata] PRIMARY KEY CLUSTERED
(
    [FieldKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[FieldMetadata] WITH CHECK ADD CONSTRAINT [CK_FieldMetadata_DataType]
    CHECK (DataType IN ('numeric','categorical','date','text'))
GO
```

- [ ] **Step 2: Create `FieldMetadata_seed.sql`** with rows that mirror every `col_*` in `SearchConfig` plus the synthetic `processname` and `status`:

```sql
SET NOCOUNT ON;

MERGE INTO [dbo].[FieldMetadata] AS target
USING (VALUES
    ('grossamount',   'numeric',     1, 1),
    ('netamount',     'numeric',     1, 1),
    ('vatamount',     'numeric',     1, 1),
    ('docdate',       'date',        0, 1),
    ('doctype',       'categorical', 0, 1),
    ('docbarcode',    'categorical', 0, 1),
    ('crdno',         'categorical', 0, 1),
    ('crdname',       'categorical', 0, 1),
    ('bankpk',        'categorical', 0, 1),
    ('doccurrency',   'categorical', 0, 1),
    ('invoicenr',     'categorical', 0, 1),
    ('istec',         'categorical', 0, 1),
    ('esrreference',  'categorical', 0, 1),
    ('ordernumber',   'categorical', 0, 1),
    ('client',        'categorical', 0, 1),
    ('docsource',     'categorical', 0, 1),
    ('ownernr',       'categorical', 0, 1),
    ('tenancynr',     'categorical', 0, 1),
    ('registered',    'categorical', 0, 1),
    ('branch',        'categorical', 0, 1),
    ('forwarding',    'categorical', 0, 1),
    ('department',    'categorical', 0, 1),
    ('postcode',      'categorical', 0, 1),
    ('recipient',     'categorical', 0, 1),
    ('confidentiality','categorical',0, 1),
    ('propertynr',    'categorical', 0, 1),
    ('separatorsheet','categorical', 0, 1),
    ('docid',         'categorical', 0, 1),
    ('archiveboxno',  'categorical', 0, 1),
    -- synthetic dimensions (always available regardless of SearchConfig contents):
    ('processname',   'categorical', 0, 1),
    ('status',        'categorical', 0, 1)
) AS src (FieldKey, DataType, Aggregable, Sortable)
ON (target.FieldKey = src.FieldKey)
WHEN MATCHED THEN UPDATE SET DataType = src.DataType, Aggregable = src.Aggregable, Sortable = src.Sortable
WHEN NOT MATCHED THEN INSERT (FieldKey, DataType, Aggregable, Sortable) VALUES (src.FieldKey, src.DataType, src.Aggregable, src.Sortable);
```

- [ ] **Step 3: Apply manually to INT NexoraDB.** Run `FieldMetadata_asCreate.sql` first, then `FieldMetadata_seed.sql`. Confirm `SELECT COUNT(*) FROM FieldMetadata` returns ≥ 31.

- [ ] **Step 4: Hand off for review.**

```
git status
git diff --stat
```

Stop.

---

## Task 3: Backend — starter-layout helper + JSON validator

**Files:**
- Modify: `app.py` (add a new section just before line 2889 — the `# ---- dashboard end ----` marker)

- [ ] **Step 1: Confirm imports.** `datetime`, `timedelta`, `json` are already imported in `app.py` (search to confirm). The `_` translator (Babel) is already used by surrounding routes.

- [ ] **Step 2: Add the helpers** just above line 2889 (after `dashboard_set_filter` and before `# ----- dashboard end -----`):

```python
# ---------------------------- dashboard helpers ----------------------------- #

DASHBOARD_LAYOUT_SCHEMA_VERSION = 1
DASHBOARD_DATE_PRESETS = {'today', 'yesterday', 'last_7d', 'last_30d', 'this_month', 'custom'}
DASHBOARD_WIDGET_TYPES = {'kpi', 'timeseries', 'categorical'}
DASHBOARD_TIMESERIES_BUCKETS = {'hour', 'day', 'week', 'month'}
DASHBOARD_CHART_TYPES = {
    'timeseries': {'line', 'area', 'bar'},
    'categorical': {'bar', 'hbar', 'pie', 'doughnut'},
}
DASHBOARD_METRIC_KINDS = {'count', 'sum', 'avg', 'min', 'max', 'proc_time_avg'}


def dashboard_default_layout():
    """Hard-coded starter layout used when a user has no saved row.
    Mirrors the legacy fixed dashboard so first-time users get continuity."""
    today = datetime.now().date()
    fourteen_days_ago = today - timedelta(days=13)
    return {
        "schemaVersion": DASHBOARD_LAYOUT_SCHEMA_VERSION,
        "globalFilters": {
            "process": "all",
            "datePreset": "today",
            "dateFrom": None,
            "dateTo": None,
            "docFilters": [],
        },
        "grid": [
            {
                "id": "wid_starter_imported",
                "x": 0, "y": 0, "w": 3, "h": 2,
                "type": "kpi",
                "title": _("Imported today"),
                "config": {"metric": {"kind": "count"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": None,
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_processed",
                "x": 3, "y": 0, "w": 3, "h": 2,
                "type": "kpi",
                "title": _("Processed today"),
                "config": {"metric": {"kind": "count"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": {"status": "Done"},
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_backlog",
                "x": 6, "y": 0, "w": 3, "h": 2,
                "type": "kpi",
                "title": _("Current backlog"),
                "config": {"metric": {"kind": "count"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": {"status": "Ready", "datePreset": None},
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_avgtime",
                "x": 9, "y": 0, "w": 3, "h": 2,
                "type": "kpi",
                "title": _("Avg processing time"),
                "config": {"metric": {"kind": "proc_time_avg"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": None,
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_overtime",
                "x": 0, "y": 2, "w": 8, "h": 4,
                "type": "timeseries",
                "title": _("Documents Processed Over Time"),
                "config": {
                    "chartType": "line",
                    "bucket": "day",
                    "metric": {"kind": "count"},
                    "groupBy": None,
                },
                "ignoreGlobalFilters": False,
                "filterOverrides": {
                    "datePreset": "custom",
                    "dateFrom": fourteen_days_ago.isoformat(),
                    "dateTo": today.isoformat(),
                },
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_topdoctypes",
                "x": 8, "y": 2, "w": 4, "h": 4,
                "type": "categorical",
                "title": _("Top doctypes today"),
                "config": {
                    "chartType": "bar",
                    "dimension": "doctype",
                    "metric": {"kind": "count"},
                    "topN": 5,
                    "sort": "desc",
                },
                "ignoreGlobalFilters": False,
                "filterOverrides": None,
                "compare": {"enabled": False, "shift": "previous_period"},
            },
        ],
    }


class DashboardLayoutError(ValueError):
    """Raised by validate_dashboard_layout when the JSON shape is bad."""
    pass


def validate_dashboard_layout(layout, allowed_processes, valid_field_keys, aggregable_field_keys):
    """Validate a layout dict against the v1 schema.

    Raises DashboardLayoutError on any problem; returns nothing on success.

    `allowed_processes` is the set of ProcessName values the user can see.
    `valid_field_keys` is the set of categorical/numeric/date FieldMetadata keys
    plus the synthetic 'processname' and 'status'.
    `aggregable_field_keys` is the subset where Aggregable=1.
    """
    if not isinstance(layout, dict):
        raise DashboardLayoutError("layout must be an object")
    if layout.get("schemaVersion") != DASHBOARD_LAYOUT_SCHEMA_VERSION:
        raise DashboardLayoutError(f"schemaVersion must be {DASHBOARD_LAYOUT_SCHEMA_VERSION}")

    gf = layout.get("globalFilters") or {}
    if not isinstance(gf, dict):
        raise DashboardLayoutError("globalFilters must be an object")
    process = gf.get("process", "all")
    if process != "all" and process not in allowed_processes:
        raise DashboardLayoutError(f"globalFilters.process '{process}' not allowed")
    if gf.get("datePreset") not in DASHBOARD_DATE_PRESETS:
        raise DashboardLayoutError("globalFilters.datePreset invalid")
    for f in gf.get("docFilters") or []:
        if not isinstance(f, dict) or 'field' not in f or 'value' not in f:
            raise DashboardLayoutError("docFilters items must be {field, value}")
        if f['field'] not in valid_field_keys:
            raise DashboardLayoutError(f"docFilter field '{f['field']}' unknown")

    grid = layout.get("grid")
    if not isinstance(grid, list):
        raise DashboardLayoutError("grid must be a list")

    seen_ids = set()
    for w in grid:
        wid = w.get("id")
        if not wid or wid in seen_ids:
            raise DashboardLayoutError(f"widget id missing or duplicate: {wid!r}")
        seen_ids.add(wid)
        if w.get("type") not in DASHBOARD_WIDGET_TYPES:
            raise DashboardLayoutError(f"widget {wid}: unknown type {w.get('type')!r}")
        for k in ("x", "y", "w", "h"):
            v = w.get(k)
            if not isinstance(v, int) or v < 0 or v > 12:
                raise DashboardLayoutError(f"widget {wid}: {k} must be int in [0,12]")

        cfg = w.get("config") or {}
        if w["type"] == "kpi":
            metric = cfg.get("metric") or {}
            kind = metric.get("kind")
            if kind not in DASHBOARD_METRIC_KINDS:
                raise DashboardLayoutError(f"widget {wid}: metric.kind invalid")
            if kind in {"sum", "avg", "min", "max"}:
                if metric.get("field") not in aggregable_field_keys:
                    raise DashboardLayoutError(f"widget {wid}: metric.field must be an aggregable numeric field")
        elif w["type"] == "timeseries":
            if cfg.get("chartType") not in DASHBOARD_CHART_TYPES["timeseries"]:
                raise DashboardLayoutError(f"widget {wid}: chartType invalid")
            if cfg.get("bucket") not in DASHBOARD_TIMESERIES_BUCKETS:
                raise DashboardLayoutError(f"widget {wid}: bucket invalid")
            metric = cfg.get("metric") or {}
            if metric.get("kind") not in DASHBOARD_METRIC_KINDS:
                raise DashboardLayoutError(f"widget {wid}: metric.kind invalid")
            if metric.get("kind") in {"sum", "avg", "min", "max"} and metric.get("field") not in aggregable_field_keys:
                raise DashboardLayoutError(f"widget {wid}: metric.field must be aggregable")
            if cfg.get("groupBy") is not None and cfg["groupBy"] not in valid_field_keys:
                raise DashboardLayoutError(f"widget {wid}: groupBy field unknown")
        elif w["type"] == "categorical":
            if cfg.get("chartType") not in DASHBOARD_CHART_TYPES["categorical"]:
                raise DashboardLayoutError(f"widget {wid}: chartType invalid")
            if cfg.get("dimension") not in valid_field_keys:
                raise DashboardLayoutError(f"widget {wid}: dimension unknown")
            metric = cfg.get("metric") or {}
            if metric.get("kind") not in DASHBOARD_METRIC_KINDS:
                raise DashboardLayoutError(f"widget {wid}: metric.kind invalid")
            if metric.get("kind") in {"sum", "avg", "min", "max"} and metric.get("field") not in aggregable_field_keys:
                raise DashboardLayoutError(f"widget {wid}: metric.field must be aggregable")
            topn = cfg.get("topN", 10)
            if topn != "all" and (not isinstance(topn, int) or topn < 1 or topn > 100):
                raise DashboardLayoutError(f"widget {wid}: topN invalid")
            if cfg.get("sort") not in {"desc", "asc", "alpha"}:
                raise DashboardLayoutError(f"widget {wid}: sort invalid")

        compare = w.get("compare") or {}
        if compare.get("enabled") and compare.get("shift") != "previous_period":
            raise DashboardLayoutError(f"widget {wid}: compare.shift only 'previous_period' supported in v1")
```

- [ ] **Step 3: Smoke-test the helper.** From the repo root with the venv active and `ENVIRONMENT=INT` set, run `python -c "import app; print(app.dashboard_default_layout()['grid'][0])"`. Confirm it prints the imported-today widget dict.

- [ ] **Step 4: Hand off for review.**

```
git status
git diff --stat
```

Stop.

---

## Task 4: Backend — `GET /api/dashboard/field_metadata`

**Files:**
- Modify: `app.py` (add route below the helpers from Task 3, still before `# ----- dashboard end -----`)

- [ ] **Step 1: Add the route:**

```python
@app.route("/api/dashboard/field_metadata")
@require_permission('dashboard.view')
@cache.cached(timeout=3600, key_prefix=lambda: f"dash_fieldmeta_{session.get('userid')}_{str(get_locale())}")
def dashboard_field_metadata():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    perms = session.get('permissions', [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted({
        (p.split('.')[-2] + '.' + p.split('.')[-1])
        for p in perms if p.startswith(prefix)
    })

    current_lang = str(get_locale())
    lang_col = {'de': 'GermanLabel', 'fr': 'FrenchLabel', 'it': 'ItalianLabel'}.get(current_lang, 'EnglishLabel')

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cur = conn.cursor()

        cur.execute("SELECT FieldKey, DataType, Aggregable, Sortable FROM FieldMetadata")
        meta_rows = cur.fetchall()
        meta_by_key = {r.FieldKey: {
            "field": r.FieldKey,
            "type": r.DataType,
            "aggregable": bool(r.Aggregable),
            "sortable": bool(r.Sortable),
        } for r in meta_rows}

        cur.execute("SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels")
        for r in cur.fetchall():
            if r.FieldKey in meta_by_key:
                meta_by_key[r.FieldKey]["label"] = getattr(r, lang_col) or r.EnglishLabel

        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith('col_')]
        select_cols = ", ".join(cols)
        cur.execute(f"SELECT ProcessName, {select_cols} FROM SearchConfig")
        availability = {}
        for row in cur.fetchall():
            if row.ProcessName not in allowed_processes:
                continue
            for i, col in enumerate(cols):
                if row[i + 1]:
                    fk = col[len('col_'):]
                    availability.setdefault(fk, []).append(row.ProcessName)

        for fk in ('processname', 'status'):
            availability[fk] = allowed_processes[:]

        out = []
        for fk, meta in meta_by_key.items():
            if fk not in availability:
                continue
            entry = dict(meta)
            entry.setdefault("label", fk.replace('_', ' ').title())
            entry["processes"] = sorted(availability[fk])
            out.append(entry)

        out.sort(key=lambda e: e["label"])
        return jsonify(out)

    except Exception as e:
        app.logger.error(f"/api/dashboard/field_metadata error: {e}")
        return jsonify({"error": _("Could not fetch field metadata")}), 500
    finally:
        if conn:
            conn.close()
```

- [ ] **Step 2: Run the dev server.** `set ENVIRONMENT=INT && python app.py`. Log in.

- [ ] **Step 3: Verify in the browser DevTools console:**

```js
fetch('/api/dashboard/field_metadata', {credentials:'include'}).then(r => r.json()).then(console.log)
```

Expected: an array with at least one `{field:'doctype', type:'categorical', aggregable:false, label:'Document type', processes:[...]}` and one `{field:'grossamount', type:'numeric', aggregable:true, ...}`. Stop the server.

- [ ] **Step 4: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 5: Backend — `GET /api/dashboard/layout`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the route** below `dashboard_field_metadata`:

```python
@app.route("/api/dashboard/layout")
@require_permission('dashboard.view')
def dashboard_get_layout():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get('userid')
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT LayoutJSON FROM DashboardLayouts WHERE UserID = ?", (userid,))
        row = cur.fetchone()
        if row:
            return jsonify(json.loads(row.LayoutJSON))
        return jsonify(dashboard_default_layout())
    except Exception as e:
        app.logger.error(f"/api/dashboard/layout GET error: {e}")
        return jsonify({"error": _("Could not load layout")}), 500
    finally:
        if conn:
            conn.close()
```

- [ ] **Step 2: Verify** in DevTools:

```js
fetch('/api/dashboard/layout', {credentials:'include'}).then(r => r.json()).then(console.log)
```

Expected: the starter layout dict with 6 widgets.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 6: Backend — `PUT /api/dashboard/layout` (validate + upsert)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the route** below `dashboard_get_layout`:

```python
@app.route("/api/dashboard/layout", methods=["PUT"])
@require_permission('dashboard.view')
def dashboard_put_layout():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get('userid')
    perms = session.get('permissions', [])
    prefix = "dashboard.filter.process."
    allowed_processes = {
        (p.split('.')[-2] + '.' + p.split('.')[-1])
        for p in perms if p.startswith(prefix)
    }

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT FieldKey, Aggregable FROM FieldMetadata")
        rows = cur.fetchall()
        valid_fields = {r.FieldKey for r in rows}
        aggregable_fields = {r.FieldKey for r in rows if r.Aggregable}

        try:
            validate_dashboard_layout(payload, allowed_processes, valid_fields, aggregable_fields)
        except DashboardLayoutError as e:
            return jsonify({"error": str(e)}), 400

        layout_str = json.dumps(payload, ensure_ascii=False)

        cur.execute("""
            MERGE DashboardLayouts AS t
            USING (SELECT ? AS UserID, ? AS LayoutJSON) AS s
            ON t.UserID = s.UserID
            WHEN MATCHED THEN UPDATE SET LayoutJSON = s.LayoutJSON, UpdatedAt = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT (UserID, LayoutJSON) VALUES (s.UserID, s.LayoutJSON);
        """, (userid, layout_str))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        app.logger.error(f"/api/dashboard/layout PUT error: {e}")
        return jsonify({"error": _("Could not save layout")}), 500
    finally:
        if conn:
            conn.close()
```

- [ ] **Step 2: Verify save round-trip.** With the dashboard page open (you can use the existing `/dashboard` route since the new HTML isn't deployed yet — the CSRF token is present in the page meta):

```js
const csrf = (document.cookie.match(/_csrf_token=([^;]+)/)?.[1])
           || document.querySelector('meta[name=csrf-token]')?.content
           || window.csrfToken;
const cur = await fetch('/api/dashboard/layout', {credentials:'include'}).then(r => r.json());
cur.grid[0].title = 'Renamed';
const r = await fetch('/api/dashboard/layout', {method:'PUT', credentials:'include', headers:{'Content-Type':'application/json','X-CSRFToken': csrf}, body: JSON.stringify(cur)});
console.log(await r.json());  // {ok:true}
```

- [ ] **Step 3: Verify validation rejection.** Send an invalid payload:

```js
await fetch('/api/dashboard/layout', {method:'PUT', credentials:'include', headers:{'Content-Type':'application/json','X-CSRFToken': csrf}, body: JSON.stringify({schemaVersion:1, globalFilters:{process:'all',datePreset:'today',docFilters:[]}, grid:[{id:'x',x:0,y:0,w:5,h:2,type:'kpi',config:{metric:{kind:'BAD'}}}]})}).then(r => r.json())
```

Expected: `{error: "widget x: metric.kind invalid"}` with HTTP 400.

- [ ] **Step 4: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 7: Backend — `POST /api/dashboard/layout/reset`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the route** below `dashboard_put_layout`:

```python
@app.route("/api/dashboard/layout/reset", methods=["POST"])
@require_permission('dashboard.view')
def dashboard_reset_layout():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get('userid')
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM DashboardLayouts WHERE UserID = ?", (userid,))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        app.logger.error(f"/api/dashboard/layout/reset error: {e}")
        return jsonify({"error": _("Could not reset layout")}), 500
    finally:
        if conn:
            conn.close()
```

- [ ] **Step 2: Verify** in DevTools:

```js
await fetch('/api/dashboard/layout/reset', {method:'POST', credentials:'include', headers:{'X-CSRFToken': csrf}}).then(r => r.json())
```

Expected: `{ok:true}`. A subsequent GET `/api/dashboard/layout` returns the starter layout.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 8: Backend — `build_widget_query` (helpers + KPI metrics)

**Files:**
- Modify: `app.py`

The query builder is the largest and riskiest piece. Build it in two tasks: helpers + KPI builder first (Task 8), then time-series + categorical aggregations (Task 9). Both share the same `build_widget_query(widget, global_filters, allowed_processes)` entry point — this task implements the entry point with KPI-only support; Task 9 extends it.

- [ ] **Step 1: Add helpers** below `dashboard_reset_layout`:

```python
from datetime import date

def _resolve_date_range(date_preset, date_from=None, date_to=None):
    """Returns (start_date, end_date) as datetime.date or (None, None) if no date filter applies.
    None means 'do not filter by date' (used by point-in-time KPIs like backlog)."""
    if date_preset is None:
        return (None, None)
    today = datetime.now().date()
    if date_preset == 'today':
        return (today, today)
    if date_preset == 'yesterday':
        y = today - timedelta(days=1)
        return (y, y)
    if date_preset == 'last_7d':
        return (today - timedelta(days=6), today)
    if date_preset == 'last_30d':
        return (today - timedelta(days=29), today)
    if date_preset == 'this_month':
        return (today.replace(day=1), today)
    if date_preset == 'custom':
        s = date.fromisoformat(date_from) if date_from else None
        e = date.fromisoformat(date_to) if date_to else None
        return (s, e)
    return (None, None)


def _effective_filters(widget, global_filters):
    if widget.get('ignoreGlobalFilters'):
        base = {}
    else:
        base = dict(global_filters or {})
    overrides = widget.get('filterOverrides') or {}
    base.update(overrides)
    return base


def _process_scope(filters, allowed_processes):
    proc = filters.get('process', 'all') if isinstance(filters, dict) else 'all'
    if proc == 'all':
        return list(allowed_processes)
    return [proc] if proc in allowed_processes else []


_search_config_cache = {}  # ProcessName -> {field_key: actual_col_name}


def _resolve_aggregation_column(process_name, field_key):
    """Look up SearchConfig.col_<field> (which stores the *actual* data column name) for this process.
    Returns None if the process or field isn't mapped."""
    if process_name in _search_config_cache:
        return _search_config_cache[process_name].get(field_key)
    conn = engineNexoraDB.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith('col_')]
        select_cols = ', '.join(cols)
        cur.execute(f"SELECT {select_cols} FROM SearchConfig WHERE ProcessName = ?", (process_name,))
        row = cur.fetchone()
        if not row:
            _search_config_cache[process_name] = {}
            return None
        mapping = {}
        for i, col in enumerate(cols):
            val = row[i]
            if val:
                mapping[col[len('col_'):]] = val
        _search_config_cache[process_name] = mapping
        return mapping.get(field_key)
    finally:
        conn.close()
```

- [ ] **Step 2: Add the KPI builder:**

```python
def _build_kpi_sql(widget, filters, configs, mobscan_set):
    metric = widget['config']['metric']
    kind = metric['kind']
    field = metric.get('field')
    start_date, end_date = _resolve_date_range(filters.get('datePreset'), filters.get('dateFrom'), filters.get('dateTo'))
    status = filters.get('status')

    def build_for(cfgs):
        if not cfgs:
            return '', []
        sub_qs = []
        params = []
        for row in cfgs:
            tbl = row.TableName
            export_col = row.ExportColumn
            import_col = row.ImportColumn
            cond = f" {row.additionalCondition}" if row.additionalCondition else ""

            if kind == 'count':
                expr = "COUNT(*)"
            elif kind == 'proc_time_avg':
                expr = f"AVG(CAST(DATEDIFF(SECOND, {import_col}, {export_col}) AS BIGINT))"
            elif kind in ('sum', 'avg', 'min', 'max'):
                col_actual = _resolve_aggregation_column(row.ProcessName, field)
                if not col_actual:
                    continue
                expr = f"{kind.upper()}(CAST({col_actual} AS DECIMAL(18,4)))"
            else:
                continue

            where = []
            if start_date is not None and status != 'Ready':
                where.append(f"CAST({export_col} AS DATE) >= ?")
                params.append(start_date)
            if end_date is not None and status != 'Ready':
                where.append(f"CAST({export_col} AS DATE) <= ?")
                params.append(end_date)
            for f in (filters.get('docFilters') or []):
                col = _resolve_aggregation_column(row.ProcessName, f['field'])
                if not col:
                    continue
                where.append(f"{col} = ?")
                params.append(f['value'])
            where_sql = (" WHERE " + " AND ".join(where) + cond) if where else (" WHERE 1=1" + cond)
            sub_qs.append(f"SELECT {expr} AS v FROM [{DB_STATISTICS}].{tbl}{where_sql}")
        if not sub_qs:
            return '', []
        outer_agg = {'count': 'SUM', 'sum': 'SUM', 'avg': 'AVG', 'min': 'MIN', 'max': 'MAX', 'proc_time_avg': 'AVG'}[kind]
        full = f"SELECT {outer_agg}(v) FROM ({' UNION ALL '.join(sub_qs)}) t"
        return full, params

    regular_cfgs = [c for c in configs if c.ProcessName not in mobscan_set]
    mobscan_cfgs = [c for c in configs if c.ProcessName in mobscan_set]
    return (*build_for(regular_cfgs), *build_for(mobscan_cfgs))
```

- [ ] **Step 3: Add the public entry point:**

```python
def build_widget_query(widget, global_filters, allowed_processes):
    """Translate (widget, filters) -> a list of (engine, sql, params) tuples.
    Caller runs each tuple, merges results per widget.type, returns labels/series/value.

    KPI implementation lives here. Time-series and categorical handled in T9."""
    filters = _effective_filters(widget, global_filters)
    target_processes = _process_scope(filters, allowed_processes)
    if not target_processes:
        return []

    conn = engineNexoraDB.raw_connection()
    try:
        cur = conn.cursor()
        placeholders = ','.join(['?'] * len(target_processes))
        cur.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition "
            f"FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes,
        )
        configs = cur.fetchall()
    finally:
        conn.close()
    if not configs:
        return []

    mobscan_set = set(get_mobscan_clients())

    if widget['type'] == 'kpi':
        reg_sql, reg_params, mob_sql, mob_params = _build_kpi_sql(widget, filters, configs, mobscan_set)
        out = []
        if reg_sql:
            out.append((engineStatisticsDB, reg_sql, reg_params))
        if mob_sql:
            out.append((engineStatisticsDBMobscan, mob_sql, mob_params))
        return out

    # timeseries / categorical added in T9
    raise NotImplementedError(f"widget type {widget['type']} not yet implemented")
```

- [ ] **Step 4: Smoke-test in a Python REPL** with the venv active and `ENVIRONMENT=INT`:

```python
import app
w = app.dashboard_default_layout()['grid'][0]   # imported-today KPI
queries = app.build_widget_query(w, app.dashboard_default_layout()['globalFilters'], allowed_processes=['<a real ProcessName>'])
print(queries)
```

Expected: a list with one or two `(engine, sql, params)` tuples; the SQL contains `COUNT(*)` and `CAST(... AS DATE)`.

- [ ] **Step 5: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 9: Backend — `build_widget_query` (time-series + categorical)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the time-bucket and metric expression helpers below `_build_kpi_sql`:**

```python
def _bucket_expr(col, bucket):
    if bucket == 'hour':
        return f"DATEADD(hour, DATEPART(hour, {col}), CAST(CAST({col} AS DATE) AS DATETIME2))"
    if bucket == 'day':
        return f"CAST({col} AS DATE)"
    if bucket == 'week':
        return f"DATEADD(day, 1 - DATEPART(weekday, {col}), CAST({col} AS DATE))"
    if bucket == 'month':
        return f"DATEFROMPARTS(YEAR({col}), MONTH({col}), 1)"
    raise ValueError(f"unknown bucket {bucket!r}")


def _metric_expr(metric, process_name):
    """Return a SQL fragment for the metric expression. Returns None if the field isn't exposed
    by this process — caller skips the subquery."""
    kind = metric['kind']
    if kind == 'count':
        return "COUNT(*)"
    if kind == 'proc_time_avg':
        return None  # caller injects DATEDIFF directly because it needs both cols
    field = metric.get('field')
    col = _resolve_aggregation_column(process_name, field) if field else None
    if not col:
        return None
    return f"{kind.upper()}(CAST({col} AS DECIMAL(18,4)))"


def _doc_filter_clauses(filters, process_name, params_out):
    clauses = []
    for f in (filters.get('docFilters') or []):
        col = _resolve_aggregation_column(process_name, f['field'])
        if not col:
            continue
        clauses.append(f"{col} = ?")
        params_out.append(f['value'])
    return clauses
```

- [ ] **Step 2: Add the time-series builder:**

```python
def _build_timeseries_sql(widget, filters, configs, mobscan_set):
    cfg = widget['config']
    bucket = cfg['bucket']
    metric = cfg['metric']
    start_date, end_date = _resolve_date_range(filters.get('datePreset'), filters.get('dateFrom'), filters.get('dateTo'))

    def build_for(cfgs):
        if not cfgs:
            return '', []
        sub_qs = []
        params = []
        for row in cfgs:
            tbl = row.TableName
            export_col = row.ExportColumn
            import_col = row.ImportColumn
            cond = f" {row.additionalCondition}" if row.additionalCondition else ""
            bucket_sql = _bucket_expr(export_col, bucket)
            if metric['kind'] == 'proc_time_avg':
                metric_sql = f"AVG(CAST(DATEDIFF(SECOND, {import_col}, {export_col}) AS BIGINT))"
            else:
                metric_sql = _metric_expr(metric, row.ProcessName)
                if metric_sql is None:
                    continue
            where = []
            if start_date is not None:
                where.append(f"CAST({export_col} AS DATE) >= ?"); params.append(start_date)
            if end_date is not None:
                where.append(f"CAST({export_col} AS DATE) <= ?"); params.append(end_date)
            where += _doc_filter_clauses(filters, row.ProcessName, params)
            where_sql = (" WHERE " + " AND ".join(where) + cond) if where else (" WHERE 1=1" + cond)
            sub_qs.append(
                f"SELECT {bucket_sql} AS bucket, {metric_sql} AS v "
                f"FROM [{DB_STATISTICS}].{tbl}{where_sql} GROUP BY {bucket_sql}"
            )
        if not sub_qs:
            return '', []
        outer_agg = {'count': 'SUM', 'sum': 'SUM', 'avg': 'AVG', 'min': 'MIN', 'max': 'MAX', 'proc_time_avg': 'AVG'}[metric['kind']]
        full = (
            f"SELECT bucket, {outer_agg}(v) AS v "
            f"FROM ({' UNION ALL '.join(sub_qs)}) t "
            f"GROUP BY bucket ORDER BY bucket"
        )
        return full, params

    regular_cfgs = [c for c in configs if c.ProcessName not in mobscan_set]
    mobscan_cfgs = [c for c in configs if c.ProcessName in mobscan_set]
    return (*build_for(regular_cfgs), *build_for(mobscan_cfgs))
```

- [ ] **Step 3: Add the categorical builder:**

```python
def _build_categorical_sql(widget, filters, configs, mobscan_set):
    cfg = widget['config']
    dim = cfg['dimension']
    metric = cfg['metric']
    top_n = cfg.get('topN', 10)
    sort = cfg.get('sort', 'desc')
    start_date, end_date = _resolve_date_range(filters.get('datePreset'), filters.get('dateFrom'), filters.get('dateTo'))

    def build_for(cfgs):
        if not cfgs:
            return '', []
        sub_qs = []
        params = []
        for row in cfgs:
            tbl = row.TableName
            export_col = row.ExportColumn
            cond = f" {row.additionalCondition}" if row.additionalCondition else ""

            if dim == 'processname':
                # constant string per subquery (parameterized via separate placeholder)
                dim_sql = "?"
                params.append(row.ProcessName)
            elif dim == 'status':
                # status lives on Octopus runtime, not the stats DB — skip in v1
                continue
            else:
                dim_col = _resolve_aggregation_column(row.ProcessName, dim)
                if not dim_col:
                    continue
                dim_sql = dim_col

            if metric['kind'] == 'proc_time_avg':
                metric_sql = f"AVG(CAST(DATEDIFF(SECOND, {row.ImportColumn}, {export_col}) AS BIGINT))"
            else:
                metric_sql = _metric_expr(metric, row.ProcessName)
                if metric_sql is None:
                    continue

            where = []
            if start_date is not None:
                where.append(f"CAST({export_col} AS DATE) >= ?"); params.append(start_date)
            if end_date is not None:
                where.append(f"CAST({export_col} AS DATE) <= ?"); params.append(end_date)
            where += _doc_filter_clauses(filters, row.ProcessName, params)
            where_sql = (" WHERE " + " AND ".join(where) + cond) if where else (" WHERE 1=1" + cond)

            group_by = dim_sql if dim_sql != "?" else "1"  # GROUP BY 1 when grouping a constant
            sub_qs.append(
                f"SELECT {dim_sql} AS dim, {metric_sql} AS v "
                f"FROM [{DB_STATISTICS}].{tbl}{where_sql} GROUP BY {group_by}"
            )
        if not sub_qs:
            return '', []
        outer_agg = {'count': 'SUM', 'sum': 'SUM', 'avg': 'AVG', 'min': 'MIN', 'max': 'MAX', 'proc_time_avg': 'AVG'}[metric['kind']]
        order_sql = {'desc': 'v DESC', 'asc': 'v ASC', 'alpha': 'dim ASC'}[sort]
        top_sql = "" if top_n == 'all' else f"TOP {int(top_n)} "
        full = (
            f"SELECT {top_sql}dim, {outer_agg}(v) AS v "
            f"FROM ({' UNION ALL '.join(sub_qs)}) t "
            f"GROUP BY dim ORDER BY {order_sql}"
        )
        return full, params

    regular_cfgs = [c for c in configs if c.ProcessName not in mobscan_set]
    mobscan_cfgs = [c for c in configs if c.ProcessName in mobscan_set]
    return (*build_for(regular_cfgs), *build_for(mobscan_cfgs))
```

- [ ] **Step 4: Wire them into `build_widget_query`.** Replace the `raise NotImplementedError` line with:

```python
    builder = {
        'kpi': _build_kpi_sql,
        'timeseries': _build_timeseries_sql,
        'categorical': _build_categorical_sql,
    }[widget['type']]
    reg_sql, reg_params, mob_sql, mob_params = builder(widget, filters, configs, mobscan_set)
    out = []
    if reg_sql:
        out.append((engineStatisticsDB, reg_sql, reg_params))
    if mob_sql:
        out.append((engineStatisticsDBMobscan, mob_sql, mob_params))
    return out
```

- [ ] **Step 5: Smoke-test** with the timeseries (index 4) and categorical (index 5) starter widgets. Confirm SQL strings contain `GROUP BY` for time-series and `TOP 5` for categorical.

- [ ] **Step 6: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 10: Backend — `_run_widget_queries` helper + `POST /api/dashboard/widget_data`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the merge helper** below `build_widget_query`:

```python
def _run_widget_queries(widget, queries, label_override=None):
    """Run pre-built (engine, sql, params) tuples and merge into a result dict.
    Returns {value, unit?} for KPI, {labels, series} for chart widgets.
    label_override sets the series label (used by widget_compare to mark previous-period)."""
    series_label = label_override or widget.get('title', '')

    if not queries:
        if widget['type'] == 'kpi':
            return {"value": 0, "unit": "seconds" if widget['config']['metric']['kind'] == 'proc_time_avg' else None,
                    "warnings": ["no_data_in_scope"]}
        return {"labels": [], "series": [{"label": series_label, "data": []}], "warnings": ["no_data_in_scope"]}

    if widget['type'] == 'kpi':
        kind = widget['config']['metric']['kind']
        total_value = 0.0
        avg_values = []
        min_value = None
        max_value = None
        for engine, sql, params in queries:
            conn = engine.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute(sql, params)
                row = cur.fetchone()
                v = row[0] if row else None
                if v is None:
                    continue
                v = float(v)
                if kind in ('count', 'sum'):
                    total_value += v
                elif kind in ('avg', 'proc_time_avg'):
                    avg_values.append(v)
                elif kind == 'min':
                    min_value = v if min_value is None else min(min_value, v)
                elif kind == 'max':
                    max_value = v if max_value is None else max(max_value, v)
            finally:
                conn.close()
        if kind in ('count', 'sum'):
            value = total_value
        elif kind in ('avg', 'proc_time_avg'):
            value = (sum(avg_values) / len(avg_values)) if avg_values else 0
        elif kind == 'min':
            value = min_value if min_value is not None else 0
        elif kind == 'max':
            value = max_value if max_value is not None else 0
        else:
            value = 0
        return {"value": value, "unit": "seconds" if kind == 'proc_time_avg' else None}

    if widget['type'] == 'timeseries':
        merged = {}
        for engine, sql, params in queries:
            conn = engine.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute(sql, params)
                for r in cur.fetchall():
                    bucket = r[0]
                    v = float(r[1]) if r[1] is not None else 0.0
                    merged[bucket] = merged.get(bucket, 0.0) + v
            finally:
                conn.close()
        labels = sorted(merged.keys())
        return {
            "labels": [str(b) for b in labels],
            "series": [{"label": series_label, "data": [merged[b] for b in labels]}],
        }

    # categorical
    merged = {}
    for engine, sql, params in queries:
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            for r in cur.fetchall():
                dim = r[0]
                v = float(r[1]) if r[1] is not None else 0.0
                merged[dim] = merged.get(dim, 0.0) + v
        finally:
            conn.close()
    sort = widget['config'].get('sort', 'desc')
    top_n = widget['config'].get('topN', 10)
    items = list(merged.items())
    if sort == 'desc':
        items.sort(key=lambda kv: kv[1], reverse=True)
    elif sort == 'asc':
        items.sort(key=lambda kv: kv[1])
    else:
        items.sort(key=lambda kv: str(kv[0]))
    if top_n != 'all':
        items = items[:int(top_n)]
    return {
        "labels": [str(k) for k, _v in items],
        "series": [{"label": series_label, "data": [v for _k, v in items]}],
    }
```

- [ ] **Step 2: Add the route** below the helper:

```python
def _hash_widget_request(userid, widget, global_filters, allowed_processes):
    import hashlib
    key_obj = {
        'u': userid,
        'w': widget,
        'gf': global_filters,
        'ap': sorted(allowed_processes),
    }
    return hashlib.sha256(json.dumps(key_obj, sort_keys=True, default=str).encode()).hexdigest()


@app.route("/api/dashboard/widget_data", methods=["POST"])
@require_permission('dashboard.view')
@limiter.limit("120 per minute")
def dashboard_widget_data():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get('userid')
    perms = session.get('permissions', [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted({
        (p.split('.')[-2] + '.' + p.split('.')[-1])
        for p in perms if p.startswith(prefix)
    })

    payload = request.get_json(silent=True) or {}
    widget = payload.get('widget')
    global_filters = payload.get('globalFilters') or {}
    if not isinstance(widget, dict) or widget.get('type') not in DASHBOARD_WIDGET_TYPES:
        return jsonify({"error": _("Invalid widget")}), 400

    cache_ttl = 60 if widget['type'] == 'kpi' else 300
    cache_key = f"dash_widget_{_hash_widget_request(userid, widget, global_filters, allowed_processes)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        queries = build_widget_query(widget, global_filters, allowed_processes)
    except DashboardLayoutError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error(f"widget_data build error: {e}")
        return jsonify({"error": _("Could not build query")}), 500

    try:
        result = _run_widget_queries(widget, queries)
    except Exception as e:
        app.logger.error(f"widget_data run error: {e}")
        return jsonify({"error": _("Could not run query")}), 500

    cache.set(cache_key, result, timeout=cache_ttl)
    return jsonify(result)
```

- [ ] **Step 3: Verify** by hitting the endpoint from DevTools with the starter "Imported today" widget. Expected: `{value: <number>, unit: null}` matching today's count from the legacy KPI endpoint.

```js
const csrf = document.querySelector('meta[name=csrf-token]')?.content || (document.cookie.match(/_csrf_token=([^;]+)/)?.[1]);
const layout = await fetch('/api/dashboard/layout').then(r => r.json());
const w = layout.grid[0];
const r = await fetch('/api/dashboard/widget_data', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json','X-CSRFToken': csrf}, body: JSON.stringify({widget: w, globalFilters: layout.globalFilters})});
console.log(await r.json());
```

- [ ] **Step 4: Verify** the time-series widget (index 4):

```js
const ts = layout.grid[4];
fetch('/api/dashboard/widget_data', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json','X-CSRFToken': csrf}, body: JSON.stringify({widget: ts, globalFilters: layout.globalFilters})}).then(r => r.json()).then(console.log)
```

Expected: `{labels: ['2026-04-14', ..., '2026-04-27'], series: [{label, data: [...]}]}`.

- [ ] **Step 5: Verify** the categorical widget (index 5):

```js
const cat = layout.grid[5];
fetch('/api/dashboard/widget_data', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json','X-CSRFToken': csrf}, body: JSON.stringify({widget: cat, globalFilters: layout.globalFilters})}).then(r => r.json()).then(console.log)
```

Expected: `{labels: ['Invoice', ...], series: [{data: [...]}]}` with at most 5 items.

- [ ] **Step 6: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 11: Backend — `POST /api/dashboard/widget_compare`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the route** below `dashboard_widget_data`:

```python
@app.route("/api/dashboard/widget_compare", methods=["POST"])
@require_permission('dashboard.view')
@limiter.limit("60 per minute")
def dashboard_widget_compare():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    payload = request.get_json(silent=True) or {}
    widget = payload.get('widget')
    global_filters = payload.get('globalFilters') or {}
    if not isinstance(widget, dict) or widget.get('type') not in DASHBOARD_WIDGET_TYPES:
        return jsonify({"error": _("Invalid widget")}), 400

    filters = _effective_filters(widget, global_filters)
    s, e = _resolve_date_range(filters.get('datePreset'), filters.get('dateFrom'), filters.get('dateTo'))
    if s is None or e is None:
        return jsonify({"labels": [], "series": [], "warnings": ["compare_unavailable_no_date_range"]})
    span_days = (e - s).days + 1
    new_e = s - timedelta(days=1)
    new_s = new_e - timedelta(days=span_days - 1)

    shifted_widget = json.loads(json.dumps(widget))  # deep copy
    shifted_widget['filterOverrides'] = dict(shifted_widget.get('filterOverrides') or {})
    shifted_widget['filterOverrides']['datePreset'] = 'custom'
    shifted_widget['filterOverrides']['dateFrom'] = new_s.isoformat()
    shifted_widget['filterOverrides']['dateTo'] = new_e.isoformat()

    perms = session.get('permissions', [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted({
        (p.split('.')[-2] + '.' + p.split('.')[-1])
        for p in perms if p.startswith(prefix)
    })
    try:
        queries = build_widget_query(shifted_widget, global_filters, allowed_processes)
        result = _run_widget_queries(shifted_widget, queries, label_override=_("Previous period"))
    except Exception as ex:
        app.logger.error(f"widget_compare error: {ex}")
        return jsonify({"error": _("Could not build comparison")}), 500
    return jsonify(result)
```

- [ ] **Step 2: Verify compare** in DevTools with the timeseries starter widget marked as compare-enabled:

```js
const ts = {...layout.grid[4], compare:{enabled:true, shift:'previous_period'}};
fetch('/api/dashboard/widget_compare', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json','X-CSRFToken': csrf}, body: JSON.stringify({widget: ts, globalFilters: layout.globalFilters})}).then(r => r.json()).then(console.log)
```

Expected: `{labels: [<14 dates from the prior 14-day period>], series: [{label:'Previous period', data:[...]}]}`.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 12: Frontend — Rewrite `dashboard.html` shell + new CSS

**Files:**
- Modify: `templates/dashboard.html` (full rewrite)
- Create: `static/css/dashboard.css` (replace existing — keep the path)
- Modify: `templates/js/_dashboardJS.html` (placeholder stub, real implementation in T13–T23)

- [ ] **Step 1: Replace `templates/dashboard.html`** with this skeleton. Note the `<template>` blocks at the bottom — they hold the repeatable markup so JS never has to build HTML strings.

```html
<!DOCTYPE html>
<html lang="{{ get_locale }}">

<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ _("Dashboard - nexora") }}</title>
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/gridstack@11.1.2/dist/gridstack.min.css">
  <script src="https://cdn.jsdelivr.net/npm/gridstack@11.1.2/dist/gridstack-all.js"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
  <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
  <link rel="stylesheet" href="{{ url_for('static',filename='css/dashboard.css') }}">
  <link rel="icon" type="image/x-icon" href="{{ url_for('static',filename='images/favicon.ico') }}">
  <meta name="csrf-token" content="{{ csrf_token() }}">
</head>

<body class="bg-gray-50 text-gray-800">
  {% set active_page = 'dashboard' %} {% include '_header.html' %}

  <main class="container mx-auto p-6">
    <div class="mb-6 flex justify-between items-end">
      <div>
        <h2 class="text-3xl font-bold text-gray-900 mb-1">
          {{ _("Welcome back") }}, {{ fullname }}! 👋
        </h2>
        <p class="text-gray-500 font-medium">
          {{ _("Drag, resize, and configure widgets to make this dashboard your own.") }}
        </p>
      </div>
    </div>

    <div id="dashFilterBar" class="bg-white p-4 rounded-2xl shadow-sm border border-gray-100 mb-6 flex flex-wrap items-center gap-4">
      <div class="flex items-center gap-3">
        <label for="globalProcess" class="text-xs font-bold text-gray-400 uppercase tracking-widest">{{ _("Process") }}</label>
        <select id="globalProcess" class="bg-gray-50 border-gray-200 text-gray-900 text-sm rounded-xl block p-2.5">
          <option value="all">{{ _("All Processes") }}</option>
          {% for proc in allowed_processes %}
          <option value="{{ proc }}">{{ proc }}</option>
          {% endfor %}
        </select>
      </div>
      <div id="datePresetChips" class="flex items-center gap-1 flex-wrap"></div>
      <div id="globalDocFiltersContainer" class="flex items-center gap-2 flex-wrap"></div>
      <button type="button" id="addGlobalDocFilterBtn" class="text-sm text-indigo-600 hover:text-indigo-800">
        <i class="fas fa-plus-circle mr-1"></i>{{ _("Add filter") }}
      </button>
      <div class="ml-auto flex items-center gap-2">
        <span id="lastUpdatedHint" class="text-xs text-gray-400"></span>
        <button type="button" id="refreshNowBtn" title="{{ _('Refresh now') }}" class="px-2 py-1.5 text-gray-500 hover:text-gray-800">
          <i class="fas fa-rotate"></i>
        </button>
        <button type="button" id="resetLayoutBtn" class="px-3 py-2 bg-white text-gray-600 border border-gray-200 rounded-xl text-sm font-semibold hover:bg-gray-50">
          <i class="fas fa-rotate-left mr-1"></i>{{ _("Reset") }}
        </button>
        <button type="button" id="editToggleBtn" class="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold shadow-sm hover:bg-indigo-700">
          <i class="fas fa-pencil mr-1"></i><span id="editToggleLabel">{{ _("Edit") }}</span>
        </button>
      </div>
    </div>

    <div class="grid-stack" id="dashboardGrid"></div>

    <button type="button" id="addWidgetFab" class="hidden fixed bottom-6 right-6 z-40 px-5 py-3 bg-indigo-600 text-white rounded-full shadow-2xl text-sm font-semibold hover:bg-indigo-700">
      <i class="fas fa-plus mr-2"></i>{{ _("Add widget") }}
    </button>
  </main>

  <div id="widgetDrawer" class="hidden fixed inset-y-0 right-0 z-50 w-[480px] bg-white shadow-2xl border-l border-gray-100 flex flex-col"></div>
  <div id="widgetDrawerBackdrop" class="hidden fixed inset-0 z-40 bg-black/30"></div>

  <div id="addWidgetModal" class="hidden fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl">
      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 class="text-lg font-bold">{{ _("Add a widget") }}</h3>
        <button type="button" id="addWidgetClose" class="text-gray-400 hover:text-gray-700"><i class="fas fa-times"></i></button>
      </div>
      <div class="p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <button type="button" data-type="kpi"         class="text-left p-4 border border-gray-200 rounded-xl hover:border-indigo-400 hover:shadow-sm">
          <div class="text-3xl mb-2"><i class="fas fa-bullseye text-indigo-500"></i></div>
          <div class="font-bold text-gray-900 mb-1">{{ _("KPI card") }}</div>
          <div class="text-xs text-gray-500">{{ _("Single big metric for an at-a-glance summary.") }}</div>
        </button>
        <button type="button" data-type="timeseries"  class="text-left p-4 border border-gray-200 rounded-xl hover:border-indigo-400 hover:shadow-sm">
          <div class="text-3xl mb-2"><i class="fas fa-chart-line text-sky-500"></i></div>
          <div class="font-bold text-gray-900 mb-1">{{ _("Time-series chart") }}</div>
          <div class="text-xs text-gray-500">{{ _("Trend over time as line, area, or bar.") }}</div>
        </button>
        <button type="button" data-type="categorical" class="text-left p-4 border border-gray-200 rounded-xl hover:border-indigo-400 hover:shadow-sm">
          <div class="text-3xl mb-2"><i class="fas fa-chart-pie text-green-500"></i></div>
          <div class="font-bold text-gray-900 mb-1">{{ _("Categorical chart") }}</div>
          <div class="text-xs text-gray-500">{{ _("Bar or pie split by a dimension (doctype, currency, ...).") }}</div>
        </button>
      </div>
    </div>
  </div>

  <!-- Templates: cloned by JS via cloneNode(true). No string concatenation in JS. -->
  <template id="widgetShellTemplate">
    <div class="widget-shell">
      <div class="widget-header">
        <div class="widget-drag-handle"><i class="fas fa-grip-vertical"></i></div>
        <h3 class="widget-title"></h3>
        <div class="widget-actions">
          <button type="button" class="widget-settings-btn" title="{{ _('Settings') }}"><i class="fas fa-cog"></i></button>
          <button type="button" class="widget-remove-btn" title="{{ _('Remove') }}"><i class="fas fa-times"></i></button>
        </div>
      </div>
      <div class="widget-body"></div>
    </div>
  </template>

  <template id="kpiBodyTemplate">
    <div class="kpi-clickable cursor-pointer h-full flex flex-col" role="link" tabindex="0">
      <div class="kpi-value"></div>
      <div class="kpi-sub"></div>
    </div>
  </template>

  <template id="chartBodyTemplate">
    <div class="h-full"><canvas></canvas></div>
  </template>

  <template id="drawerFrameTemplate">
    <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
      <h3 class="text-base font-bold drawer-heading"></h3>
      <button type="button" class="drawer-close text-gray-400 hover:text-gray-700"><i class="fas fa-times"></i></button>
    </div>
    <div class="drawer-tabs">
      <div class="drawer-tab" data-tab="data" aria-selected="true">{{ _("Data") }}</div>
      <div class="drawer-tab" data-tab="filters">{{ _("Filters") }}</div>
      <div class="drawer-tab" data-tab="display">{{ _("Display") }}</div>
    </div>
    <div class="drawer-body"></div>
    <div class="drawer-footer">
      <button type="button" class="drawer-cancel px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg text-sm">{{ _("Cancel") }}</button>
      <button type="button" class="drawer-apply px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold">{{ _("Apply") }}</button>
    </div>
  </template>

  <!-- One field row per "label + control" pair the drawer needs. JS clones, fills, appends. -->
  <template id="fieldRowSelectTemplate">
    <div class="field-row">
      <label></label>
      <select></select>
    </div>
  </template>
  <template id="fieldRowInputTemplate">
    <div class="field-row">
      <label></label>
      <input type="text">
    </div>
  </template>
  <template id="fieldRowCheckboxTemplate">
    <div class="field-row">
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox">
        <span></span>
      </label>
    </div>
  </template>
  <template id="docFilterRowTemplate">
    <div class="flex items-center gap-2 mb-2 doc-filter-row">
      <select class="doc-field flex-1 px-2 py-1 border border-gray-200 rounded"></select>
      <input class="doc-value flex-1 px-2 py-1 border border-gray-200 rounded">
      <button type="button" class="doc-remove text-red-500 px-2"><i class="fas fa-times"></i></button>
    </div>
  </template>
  <template id="presetChipTemplate">
    <span class="preset-chip"></span>
  </template>

  {% include '_small_footer.html' %}
  {% include 'js/_dashboardJS.html' %}
</body>

</html>
```

- [ ] **Step 2: Replace `static/css/dashboard.css`:**

```css
/* Gridstack overrides */
.grid-stack { background: transparent; }
.grid-stack-item-content { display: flex; flex-direction: column; padding: 0; overflow: hidden; }

/* Widget shell */
.widget-shell {
  display: flex; flex-direction: column;
  background: #fff; border: 1px solid #f3f4f6; border-radius: 16px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  height: 100%; overflow: hidden;
}
.widget-header {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid #f3f4f6;
}
.widget-drag-handle { color: #d1d5db; cursor: grab; visibility: hidden; }
.widget-shell:hover .widget-drag-handle { color: #9ca3af; }
.widget-title { flex: 1; font-size: 14px; font-weight: 700; color: #1f2937; margin: 0; }
.widget-actions { display: flex; gap: 6px; visibility: hidden; }
.widget-actions button {
  width: 28px; height: 28px; border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  color: #6b7280; background: transparent; border: none; cursor: pointer;
}
.widget-actions button:hover { background: #f3f4f6; color: #1f2937; }
.widget-body { flex: 1; padding: 14px 16px; min-height: 0; }

.grid-stack[data-edit="true"] .widget-drag-handle,
.grid-stack[data-edit="true"] .widget-actions { visibility: visible; }
.grid-stack[data-edit="true"] .widget-shell {
  border-color: #c7d2fe; border-style: dashed;
  background-image: linear-gradient(#fafafe,#fff);
}

.kpi-value { font-size: 32px; font-weight: 800; color: #111827; line-height: 1.1; margin-top: auto; }
.kpi-sub { font-size: 11px; color: #9ca3af; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }
.kpi-delta-positive { color: #16a34a; margin-left: 8px; }
.kpi-delta-negative { color: #ef4444; margin-left: 8px; }

.preset-chip { padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; cursor: pointer; background: #f3f4f6; color: #4b5563; border: 1px solid transparent; }
.preset-chip[aria-selected="true"] { background: #4f46e5; color: #fff; }

#widgetDrawer .drawer-tabs { display: flex; border-bottom: 1px solid #f3f4f6; }
#widgetDrawer .drawer-tab { flex: 1; padding: 12px; text-align: center; font-size: 13px; font-weight: 600; color: #6b7280; cursor: pointer; }
#widgetDrawer .drawer-tab[aria-selected="true"] { color: #4f46e5; border-bottom: 2px solid #4f46e5; }
#widgetDrawer .drawer-body { flex: 1; overflow-y: auto; padding: 20px 24px; }
#widgetDrawer .drawer-footer { padding: 16px 24px; border-top: 1px solid #f3f4f6; display: flex; gap: 8px; justify-content: flex-end; }

.field-row { margin-bottom: 18px; }
.field-row > label { display: block; font-size: 11px; font-weight: 700; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.field-row select, .field-row input[type="text"] { width: 100%; padding: 8px 12px; border: 1px solid #e5e7eb; border-radius: 10px; font-size: 13px; }
```

- [ ] **Step 3: Replace `templates/js/_dashboardJS.html`** with a temporary stub:

```html
<script>
  document.addEventListener('DOMContentLoaded', () => {
    console.log('dashboard scaffold ready');
  });
</script>
```

- [ ] **Step 4: Verify** — `python app.py`, open `/dashboard`. Expected: header, welcome message, filter bar shell with the existing process dropdown filled, "Edit" button, empty grid area. Console shows "dashboard scaffold ready". No JS errors.

- [ ] **Step 5: Hand off for review.**

```
git status
git diff --stat
```

Stop.

---

## Task 13: Frontend — DOM helpers + layout load + Gridstack init + save-on-change

**Files:**
- Modify: `templates/js/_dashboardJS.html`

This task introduces a small `el(tag, attrs, ...children)` helper that the rest of the frontend uses for all DOM construction. No string-concatenation HTML anywhere.

- [ ] **Step 1: Replace the stub** with the foundation script:

```html
<script>
(() => {
  const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";
  const csrfToken = document.querySelector('meta[name=csrf-token]')?.content || '';

  // ---------- DOM helper ----------
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'text') node.textContent = v;
      else if (v === true) node.setAttribute(k, '');
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return node;
  }
  function tpl(id) {
    return document.getElementById(id).content.firstElementChild.cloneNode(true);
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // ---------- API ----------
  function api(path, opts = {}) {
    return fetch(`${API_PREFIX}${path}`, {
      credentials: 'include',
      ...opts,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken, ...(opts.headers || {}) },
    });
  }

  // ---------- State ----------
  let layout = null;
  let grid = null;
  let editMode = false;
  let refreshTimer = null;
  let fieldMeta = [];
  const chartInstances = new Map();
  let drawerWidgetId = null;
  let drawerDraft = null;

  // ---------- Layout ----------
  async function loadLayout() {
    const res = await api('api/dashboard/layout');
    layout = await res.json();
  }
  async function saveLayout() {
    if (grid) {
      const positions = grid.save(false);
      layout.grid = layout.grid.map(w => {
        const node = positions.find(n => n.id === w.id);
        return node ? { ...w, x: node.x, y: node.y, w: node.w, h: node.h } : w;
      });
    }
    await api('api/dashboard/layout', { method: 'PUT', body: JSON.stringify(layout) });
  }

  // ---------- Grid render ----------
  function renderGrid() {
    const root = document.getElementById('dashboardGrid');
    clear(root);
    layout.grid.forEach(w => {
      const item = el('div', {
        class: 'grid-stack-item',
        'gs-id': w.id, 'gs-x': w.x, 'gs-y': w.y, 'gs-w': w.w, 'gs-h': w.h,
      }, el('div', { class: 'grid-stack-item-content' }));
      root.appendChild(item);
      mountWidget(item.firstElementChild, w);
    });
    if (grid) grid.destroy(false);
    grid = GridStack.init({
      column: 12, cellHeight: 70, margin: 8,
      staticGrid: !editMode,
      handle: '.widget-drag-handle',
      acceptWidgets: false,
    }, root);
    grid.on('change', () => saveLayout().catch(console.error));
  }

  function mountWidget(container, widget) {
    const shell = tpl('widgetShellTemplate');
    shell.dataset.widgetId = widget.id;
    shell.querySelector('.widget-title').textContent = widget.title || '';
    shell.querySelector('.widget-settings-btn').addEventListener('click', () => openSettings(widget.id));
    shell.querySelector('.widget-remove-btn').addEventListener('click', () => removeWidget(widget.id));
    container.appendChild(shell);
    renderWidgetBody(widget, shell.querySelector('.widget-body'));
  }

  function renderWidgetBody(widget, body) {
    clear(body);
    body.appendChild(el('div', { class: 'text-xs text-gray-400', text: widget.type + ' (T14-T16)' }));
  }

  function removeWidget(id) {
    if (!confirm('{{ _("Remove this widget?") }}')) return;
    layout.grid = layout.grid.filter(w => w.id !== id);
    renderGrid();
    saveLayout();
  }

  function openSettings(id) { console.log('open settings for', id); /* T17 */ }

  // ---------- Edit mode ----------
  function setEditMode(on) {
    editMode = !!on;
    document.getElementById('dashboardGrid').setAttribute('data-edit', editMode ? 'true' : 'false');
    grid?.setStatic(!editMode);
    document.getElementById('addWidgetFab').classList.toggle('hidden', !editMode);
    const btn = document.getElementById('editToggleBtn');
    const lbl = document.getElementById('editToggleLabel');
    btn.querySelector('i').className = editMode ? 'fas fa-check mr-1' : 'fas fa-pencil mr-1';
    lbl.textContent = editMode ? '{{ _("Done") }}' : '{{ _("Edit") }}';
  }

  // ---------- Boot ----------
  document.addEventListener('DOMContentLoaded', async () => {
    await loadLayout();
    renderGrid();
    document.getElementById('editToggleBtn').addEventListener('click', () => setEditMode(!editMode));
    document.getElementById('resetLayoutBtn').addEventListener('click', async () => {
      if (!confirm('{{ _("Reset layout to defaults?") }}')) return;
      await api('api/dashboard/layout/reset', { method: 'POST' });
      await loadLayout();
      renderGrid();
    });
  });

  // ---------- Expose for later tasks ----------
  window.__dash = { el, tpl, clear, api, getState: () => ({ layout, grid, editMode, fieldMeta, chartInstances }),
                    setState: (k, v) => { if (k === 'layout') layout = v; if (k === 'fieldMeta') fieldMeta = v;
                                          if (k === 'drawerWidgetId') drawerWidgetId = v; if (k === 'drawerDraft') drawerDraft = v; },
                    setEditMode, openSettings, renderGrid, renderWidgetBody, saveLayout, removeWidget };
})();
</script>
```

(The `window.__dash` namespace lets later tasks add features without rewriting this script. Each later task adds methods or replaces specific functions on `window.__dash`.)

- [ ] **Step 2: Verify** in browser:
  1. `/dashboard` shows 6 placeholder widget shells in a 12-col grid laid out per the starter coords.
  2. Click "Edit" → handles + cogs + remove buttons appear; widgets become draggable. Drag one, drop elsewhere.
  3. Refresh — the new position persisted.
  4. Click "Done" — chrome disappears.
  5. Click "Reset" — layout returns to starter.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 14: Frontend — KPI widget renderer

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append a script block** at the end of the file (below the IIFE) that extends `window.__dash`:

```html
<script>
(() => {
  const D = window.__dash;
  if (!D) throw new Error('dashboard core not loaded');

  function fetchWidgetData(widget) {
    const { layout } = D.getState();
    return D.api('api/dashboard/widget_data', {
      method: 'POST',
      body: JSON.stringify({ widget, globalFilters: layout.globalFilters }),
    }).then(r => r.json());
  }

  function formatKpiValue(value, unit) {
    if (unit === 'seconds') {
      const s = Math.max(0, Math.round(value));
      if (s >= 3600) return (s / 3600).toFixed(1) + ' h';
      if (s >= 60)   return Math.round(s / 60) + ' min';
      return s + ' s';
    }
    if (Number.isInteger(value)) return value.toLocaleString();
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 });
  }

  async function renderKpi(widget, body) {
    D.clear(body);
    body.appendChild(D.el('div', { class: 'animate-pulse h-8 w-24 bg-gray-100 rounded' }));
    let data;
    try { data = await fetchWidgetData(widget); }
    catch (e) {
      D.clear(body);
      body.appendChild(D.el('div', { class: 'text-xs text-red-500', text: '{{ _("Could not load") }}' }));
      return;
    }
    const node = D.tpl('kpiBodyTemplate');
    node.querySelector('.kpi-value').textContent = formatKpiValue(data.value, data.unit);
    node.querySelector('.kpi-sub').textContent = widget.title || '';
    node.addEventListener('click', () => {
      if (D.getState().editMode) return;
      const url = D.buildDrilldownUrl ? D.buildDrilldownUrl(widget) : null;
      if (url) window.location.href = url;
    });
    D.clear(body);
    body.appendChild(node);
  }

  // Replace the placeholder body renderer
  const original = D.renderWidgetBody;
  D.renderWidgetBody = function(widget, body) {
    if (widget.type === 'kpi') return renderKpi(widget, body);
    return original(widget, body);
  };
  D.fetchWidgetData = fetchWidgetData;
  D.formatKpiValue = formatKpiValue;
  D.renderKpi = renderKpi;
})();
</script>
```

- [ ] **Step 2: Verify** — open `/dashboard`. The four KPI tiles show real numbers matching the legacy `/api/dashboard/kpi_stats` response.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 15: Frontend — Time-series chart renderer

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append another script block:**

```html
<script>
(() => {
  const D = window.__dash;
  const PALETTE = ['#4F46E5', '#0EA5E9', '#22C55E', '#F59E0B', '#EF4444', '#A855F7', '#14B8A6', '#EC4899'];

  async function renderTimeseries(widget, body) {
    D.clear(body);
    const node = D.tpl('chartBodyTemplate');
    body.appendChild(node);
    const ctx = node.querySelector('canvas').getContext('2d');
    let data;
    try { data = await D.fetchWidgetData(widget); }
    catch (e) {
      D.clear(body);
      body.appendChild(D.el('div', { class: 'text-xs text-red-500', text: '{{ _("Could not load") }}' }));
      return;
    }
    const fill = widget.config.chartType === 'area';
    const chartType = fill ? 'line' : widget.config.chartType;
    const datasets = data.series.map((s, i) => ({
      label: s.label,
      data: s.data,
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: fill ? 'rgba(79,70,229,0.15)' : PALETTE[i % PALETTE.length],
      fill,
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 5,
    }));
    const { chartInstances } = D.getState();
    if (chartInstances.has(widget.id)) chartInstances.get(widget.id).destroy();
    chartInstances.set(widget.id, new Chart(ctx, {
      type: chartType,
      data: { labels: data.labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: data.series.length > 1 } },
        scales: {
          y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
          x: { grid: { display: false } },
        },
        onClick: (evt, elements) => D.onChartClick && D.onChartClick(widget, evt, elements),
      },
    }));

    if (widget.compare?.enabled) {
      const cmp = await D.api('api/dashboard/widget_compare', {
        method: 'POST',
        body: JSON.stringify({ widget, globalFilters: D.getState().layout.globalFilters }),
      }).then(r => r.json()).catch(() => null);
      if (cmp?.series?.[0] && chartInstances.has(widget.id)) {
        const chart = chartInstances.get(widget.id);
        chart.data.datasets.push({
          label: cmp.series[0].label,
          data: cmp.series[0].data,
          borderColor: '#9CA3AF',
          borderDash: [4, 4],
          backgroundColor: 'transparent',
          fill: false,
          tension: 0.3,
          borderWidth: 1.5,
          pointRadius: 0,
        });
        chart.options.plugins.legend.display = true;
        chart.update();
      }
    }
  }

  const original = D.renderWidgetBody;
  D.renderWidgetBody = function(widget, body) {
    if (widget.type === 'timeseries') return renderTimeseries(widget, body);
    return original(widget, body);
  };
  D.renderTimeseries = renderTimeseries;
  D.PALETTE = PALETTE;
})();
</script>
```

- [ ] **Step 2: Verify** — "Documents Processed Over Time" widget shows the 14-day line chart matching the legacy chart.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 16: Frontend — Categorical chart renderer

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append another script block:**

```html
<script>
(() => {
  const D = window.__dash;

  async function renderCategorical(widget, body) {
    D.clear(body);
    const node = D.tpl('chartBodyTemplate');
    body.appendChild(node);
    const ctx = node.querySelector('canvas').getContext('2d');
    let data;
    try { data = await D.fetchWidgetData(widget); }
    catch (e) {
      D.clear(body);
      body.appendChild(D.el('div', { class: 'text-xs text-red-500', text: '{{ _("Could not load") }}' }));
      return;
    }
    const ct = widget.config.chartType;
    const isHorizontalBar = ct === 'hbar';
    const chartType = (ct === 'pie' || ct === 'doughnut') ? ct : 'bar';
    const datasets = [{
      label: data.series[0]?.label || '',
      data: data.series[0]?.data || [],
      backgroundColor: D.PALETTE,
      borderWidth: 0,
    }];
    const { chartInstances } = D.getState();
    if (chartInstances.has(widget.id)) chartInstances.get(widget.id).destroy();
    chartInstances.set(widget.id, new Chart(ctx, {
      type: chartType,
      data: { labels: data.labels, datasets },
      options: {
        indexAxis: isHorizontalBar ? 'y' : 'x',
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: chartType === 'pie' || chartType === 'doughnut', position: 'right' } },
        scales: (chartType === 'pie' || chartType === 'doughnut') ? {} : {
          y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
          x: { grid: { display: false } },
        },
        onClick: (evt, elements) => D.onChartClick && D.onChartClick(widget, evt, elements),
      },
    }));
  }

  const original = D.renderWidgetBody;
  D.renderWidgetBody = function(widget, body) {
    if (widget.type === 'categorical') return renderCategorical(widget, body);
    return original(widget, body);
  };
  D.renderCategorical = renderCategorical;
})();
</script>
```

- [ ] **Step 2: Verify** — "Top doctypes today" widget renders a bar chart with the top 5 doctypes for today.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 17: Frontend — Settings drawer skeleton + Data tab

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Add field-metadata loader and drawer skeleton:**

```html
<script>
(() => {
  const D = window.__dash;
  const _ = D.el;

  async function loadFieldMeta() {
    const meta = await D.api('api/dashboard/field_metadata').then(r => r.json());
    D.setState('fieldMeta', meta);
  }
  D.loadFieldMeta = loadFieldMeta;

  function fillSelect(sel, options, currentValue) {
    D.clear(sel);
    options.forEach(o => {
      const opt = document.createElement('option');
      opt.value = o.value;
      opt.textContent = o.label;
      if (String(currentValue) === String(o.value)) opt.selected = true;
      sel.appendChild(opt);
    });
  }
  D.fillSelect = fillSelect;

  function makeRowSelect(labelText, options, currentValue, onChange, attrs = {}) {
    const row = D.tpl('fieldRowSelectTemplate');
    row.querySelector('label').textContent = labelText;
    const sel = row.querySelector('select');
    Object.entries(attrs).forEach(([k, v]) => sel.setAttribute(k, v));
    fillSelect(sel, options, currentValue);
    sel.addEventListener('change', () => onChange(sel.value));
    return row;
  }
  function makeRowInput(labelText, currentValue, onChange) {
    const row = D.tpl('fieldRowInputTemplate');
    row.querySelector('label').textContent = labelText;
    const inp = row.querySelector('input');
    inp.value = currentValue ?? '';
    inp.addEventListener('input', () => onChange(inp.value));
    return row;
  }
  function makeRowCheckbox(labelText, currentChecked, onChange) {
    const row = D.tpl('fieldRowCheckboxTemplate');
    row.querySelector('span').textContent = labelText;
    const cb = row.querySelector('input');
    cb.checked = !!currentChecked;
    cb.addEventListener('change', () => onChange(cb.checked));
    return row;
  }
  D.makeRowSelect = makeRowSelect;
  D.makeRowInput = makeRowInput;
  D.makeRowCheckbox = makeRowCheckbox;

  const METRIC_LABELS = { count: '{{ _("Count") }}', sum: '{{ _("Sum") }}', avg: '{{ _("Average") }}',
                          min: '{{ _("Min") }}', max: '{{ _("Max") }}', proc_time_avg: '{{ _("Avg processing time") }}' };

  function renderDataTab(w) {
    const body = document.querySelector('#widgetDrawer .drawer-body');
    D.clear(body);
    const meta = D.getState().fieldMeta;
    const numeric = meta.filter(f => f.aggregable);
    const categorical = meta.filter(f => f.type === 'categorical');

    body.appendChild(makeRowInput('{{ _("Title") }}', w.title, v => { w.title = v; }));

    function metricRows(allowedKinds) {
      const metricRow = makeRowSelect('{{ _("Metric") }}',
        allowedKinds.map(k => ({ value: k, label: METRIC_LABELS[k] })),
        w.config.metric.kind,
        v => {
          w.config.metric.kind = v;
          fieldRow.style.display = ['sum','avg','min','max'].includes(v) ? '' : 'none';
        });
      const fieldRow = makeRowSelect('{{ _("Field") }}',
        numeric.map(f => ({ value: f.field, label: f.label })),
        w.config.metric.field,
        v => { w.config.metric.field = v; });
      if (!['sum','avg','min','max'].includes(w.config.metric.kind)) fieldRow.style.display = 'none';
      body.appendChild(metricRow);
      body.appendChild(fieldRow);
    }

    if (w.type === 'kpi') {
      metricRows(['count','sum','avg','min','max','proc_time_avg']);
    } else if (w.type === 'timeseries') {
      body.appendChild(makeRowSelect('{{ _("Chart type") }}',
        ['line','area','bar'].map(t => ({ value: t, label: t })), w.config.chartType, v => { w.config.chartType = v; }));
      body.appendChild(makeRowSelect('{{ _("Time bucket") }}',
        ['hour','day','week','month'].map(b => ({ value: b, label: b })), w.config.bucket, v => { w.config.bucket = v; }));
      metricRows(['count','sum','avg','min','max','proc_time_avg']);
      body.appendChild(makeRowSelect('{{ _("Group by (optional)") }}',
        [{ value: '', label: '{{ _("None") }}' }, ...categorical.map(f => ({ value: f.field, label: f.label }))],
        w.config.groupBy || '', v => { w.config.groupBy = v || null; }));
    } else { // categorical
      body.appendChild(makeRowSelect('{{ _("Chart type") }}',
        ['bar','hbar','pie','doughnut'].map(t => ({ value: t, label: t })), w.config.chartType, v => { w.config.chartType = v; }));
      body.appendChild(makeRowSelect('{{ _("Dimension") }}',
        categorical.map(f => ({ value: f.field, label: f.label })), w.config.dimension, v => { w.config.dimension = v; }));
      metricRows(['count','sum','avg','min','max']);
      body.appendChild(makeRowSelect('{{ _("Top N") }}',
        [5,10,25,'all'].map(n => ({ value: String(n), label: String(n) })),
        String(w.config.topN), v => { w.config.topN = v === 'all' ? 'all' : parseInt(v,10); }));
      body.appendChild(makeRowSelect('{{ _("Sort") }}',
        ['desc','asc','alpha'].map(s => ({ value: s, label: s })), w.config.sort, v => { w.config.sort = v; }));
    }
  }

  function renderFiltersTab(w) {
    const body = document.querySelector('#widgetDrawer .drawer-body');
    D.clear(body);
    body.appendChild(_('p', { class: 'text-sm text-gray-400', text: '{{ _("Filters tab implemented in T18") }}' }));
  }

  function renderDisplayTab(w) {
    const body = document.querySelector('#widgetDrawer .drawer-body');
    D.clear(body);
    body.appendChild(_('p', { class: 'text-sm text-gray-400', text: '{{ _("Display tab implemented in T19") }}' }));
  }

  function switchDrawerTab(name) {
    document.querySelectorAll('#widgetDrawer .drawer-tab').forEach(t => t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false'));
    if (name === 'data') renderDataTab(D.getState().drawerDraft || drawerDraft);
    else if (name === 'filters') renderFiltersTab(D.getState().drawerDraft || drawerDraft);
    else renderDisplayTab(D.getState().drawerDraft || drawerDraft);
  }

  let drawerDraft = null;
  let drawerWidgetId = null;

  function openSettings(id) {
    const { layout } = D.getState();
    const w = layout.grid.find(g => g.id === id);
    if (!w) return;
    drawerWidgetId = id;
    drawerDraft = JSON.parse(JSON.stringify(w));
    D.setState('drawerWidgetId', id);
    D.setState('drawerDraft', drawerDraft);

    const drawer = document.getElementById('widgetDrawer');
    D.clear(drawer);
    const frame = D.tpl('drawerFrameTemplate');
    frame.querySelector('.drawer-heading').textContent = '{{ _("Edit widget") }}';
    drawer.appendChild(frame);
    drawer.classList.remove('hidden');
    document.getElementById('widgetDrawerBackdrop').classList.remove('hidden');

    drawer.querySelector('.drawer-close').addEventListener('click', () => closeDrawer(false));
    drawer.querySelector('.drawer-cancel').addEventListener('click', () => closeDrawer(false));
    drawer.querySelector('.drawer-apply').addEventListener('click', () => closeDrawer(true));
    drawer.querySelectorAll('.drawer-tab').forEach(t => t.addEventListener('click', () => switchDrawerTab(t.dataset.tab)));
    switchDrawerTab('data');
  }
  function closeDrawer(save) {
    if (save) {
      const { layout } = D.getState();
      Object.assign(layout.grid.find(g => g.id === drawerWidgetId), drawerDraft);
      D.saveLayout().then(() => D.renderGrid());
    }
    drawerWidgetId = null;
    drawerDraft = null;
    D.setState('drawerWidgetId', null);
    D.setState('drawerDraft', null);
    document.getElementById('widgetDrawer').classList.add('hidden');
    document.getElementById('widgetDrawerBackdrop').classList.add('hidden');
  }
  D.openSettings = openSettings;
  D.closeDrawer = closeDrawer;
  D.switchDrawerTab = switchDrawerTab;

  // Wire field-meta load before any widget render that needs the picker
  document.addEventListener('DOMContentLoaded', loadFieldMeta);
})();
</script>
```

- [ ] **Step 2: Verify** — enter Edit mode, click cog on KPI tile. Drawer opens, Data tab shows title + metric dropdown. Change metric → click Apply → widget re-renders with the new value.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 18: Frontend — Filters tab in settings drawer

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Replace the placeholder `renderFiltersTab` from T17.** Add a new script block at the end:

```html
<script>
(() => {
  const D = window.__dash;
  const ALLOWED_PROCESSES = JSON.parse('{{ allowed_processes|tojson }}');

  function renderFiltersTab(w) {
    const body = document.querySelector('#widgetDrawer .drawer-body');
    D.clear(body);

    body.appendChild(D.makeRowCheckbox('{{ _("Use dashboard filters") }}', !w.ignoreGlobalFilters, checked => {
      w.ignoreGlobalFilters = !checked;
      ovrSection.style.display = checked ? 'none' : '';
    }));

    const ovrSection = D.el('div', {});
    body.appendChild(ovrSection);
    if (w.ignoreGlobalFilters) ovrSection.style.display = 'none';

    const overrides = w.filterOverrides || {};
    const ensureOverrides = () => { w.filterOverrides = w.filterOverrides || {}; return w.filterOverrides; };

    const procOptions = [{ value: '', label: '{{ _("All Processes") }}' }, ...ALLOWED_PROCESSES.map(p => ({ value: p, label: p }))];
    ovrSection.appendChild(D.makeRowSelect('{{ _("Process") }}', procOptions, overrides.process || '',
      v => { ensureOverrides().process = v || 'all'; }));

    const presetOptions = ['today','yesterday','last_7d','last_30d','this_month','custom'].map(p => ({ value: p, label: p }));
    ovrSection.appendChild(D.makeRowSelect('{{ _("Date") }}', presetOptions, overrides.datePreset || 'today',
      v => { ensureOverrides().datePreset = v; customSection.style.display = v === 'custom' ? '' : 'none'; }));

    const customSection = D.el('div', { class: 'field-row' });
    customSection.appendChild(D.el('label', { text: '{{ _("Custom range") }}' }));
    const fromInp = D.el('input', { type: 'text', placeholder: 'yyyy-mm-dd', style: 'margin-bottom:6px' });
    fromInp.value = overrides.dateFrom || '';
    fromInp.addEventListener('change', () => { ensureOverrides().dateFrom = fromInp.value; });
    const toInp = D.el('input', { type: 'text', placeholder: 'yyyy-mm-dd' });
    toInp.value = overrides.dateTo || '';
    toInp.addEventListener('change', () => { ensureOverrides().dateTo = toInp.value; });
    customSection.appendChild(fromInp);
    customSection.appendChild(toInp);
    if (overrides.datePreset !== 'custom') customSection.style.display = 'none';
    ovrSection.appendChild(customSection);

    // Doc filter rows
    const docRow = D.el('div', { class: 'field-row' },
      D.el('label', { text: '{{ _("Doc filters") }}' }),
      D.el('div', { class: 'doc-rows' }),
      D.el('button', { type: 'button', class: 'text-sm text-indigo-600 mt-2',
        onclick: () => { const ovr = ensureOverrides(); ovr.docFilters = ovr.docFilters || []; ovr.docFilters.push({ field: D.getState().fieldMeta.find(f => f.type === 'categorical')?.field || 'doctype', value: '' }); renderDocRows(); }
      },
        D.el('i', { class: 'fas fa-plus mr-1' }),
        '{{ _("Add filter") }}'
      ),
    );
    ovrSection.appendChild(docRow);
    const rowsContainer = docRow.querySelector('.doc-rows');

    function renderDocRows() {
      D.clear(rowsContainer);
      const cats = D.getState().fieldMeta.filter(f => f.type === 'categorical');
      const rows = (w.filterOverrides?.docFilters) || [];
      rows.forEach((r, i) => {
        const row = D.tpl('docFilterRowTemplate');
        const sel = row.querySelector('.doc-field');
        D.fillSelect(sel, cats.map(c => ({ value: c.field, label: c.label })), r.field);
        sel.addEventListener('change', () => { ensureOverrides().docFilters[i].field = sel.value; });
        const inp = row.querySelector('.doc-value');
        inp.value = r.value || '';
        inp.addEventListener('change', () => { ensureOverrides().docFilters[i].value = inp.value; });
        row.querySelector('.doc-remove').addEventListener('click', () => {
          ensureOverrides().docFilters.splice(i, 1);
          renderDocRows();
        });
        rowsContainer.appendChild(row);
      });
    }
    renderDocRows();
  }

  // Replace the T17 placeholder
  const originalSwitch = D.switchDrawerTab;
  D.switchDrawerTab = function(name) {
    if (name === 'filters') {
      document.querySelectorAll('#widgetDrawer .drawer-tab').forEach(t => t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false'));
      renderFiltersTab(D.getState().drawerDraft);
      return;
    }
    return originalSwitch(name);
  };
})();
</script>
```

- [ ] **Step 2: Verify** — open settings on the "Imported today" KPI, switch to Filters tab, uncheck "Use dashboard filters", set a doc filter `doctype = Invoice`, Apply. KPI value updates accordingly.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 19: Frontend — Display tab + compare wiring

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append a new script block:**

```html
<script>
(() => {
  const D = window.__dash;

  function renderDisplayTab(w) {
    const body = document.querySelector('#widgetDrawer .drawer-body');
    D.clear(body);
    body.appendChild(D.makeRowCheckbox(
      '{{ _("Compare to previous period") }}',
      w.compare?.enabled || false,
      checked => {
        w.compare = w.compare || { shift: 'previous_period' };
        w.compare.enabled = checked;
        w.compare.shift = 'previous_period';
      }
    ));
    body.appendChild(D.el('p', { class: 'text-xs text-gray-400 mt-1', text: '{{ _("Overlays the previous period’s data for comparison.") }}' }));
  }

  const originalSwitch = D.switchDrawerTab;
  D.switchDrawerTab = function(name) {
    if (name === 'display') {
      document.querySelectorAll('#widgetDrawer .drawer-tab').forEach(t => t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false'));
      renderDisplayTab(D.getState().drawerDraft);
      return;
    }
    return originalSwitch(name);
  };

  // Extend renderKpi to fetch compare and append a +/- delta sub-line.
  const originalRenderKpi = D.renderKpi;
  D.renderKpi = async function(widget, body) {
    await originalRenderKpi(widget, body);
    if (!widget.compare?.enabled) return;
    const cmp = await D.api('api/dashboard/widget_compare', {
      method: 'POST', body: JSON.stringify({ widget, globalFilters: D.getState().layout.globalFilters }),
    }).then(r => r.json()).catch(() => null);
    if (!cmp || typeof cmp.value !== 'number') return;
    const sub = body.querySelector('.kpi-sub');
    if (!sub) return;
    const data = await D.fetchWidgetData(widget);
    const delta = data.value - cmp.value;
    const pct = cmp.value ? Math.round((delta / cmp.value) * 100) : 0;
    const span = D.el('span', { class: delta >= 0 ? 'kpi-delta-positive' : 'kpi-delta-negative',
      text: `${delta >= 0 ? '+' : ''}${pct}% ${'{{ _("vs prev") }}'}`,
    });
    sub.appendChild(span);
  };

  // Override renderWidgetBody to wire the compare branch in renderKpi
  const originalBody = D.renderWidgetBody;
  D.renderWidgetBody = function(widget, body) {
    if (widget.type === 'kpi') return D.renderKpi(widget, body);
    return originalBody(widget, body);
  };
})();
</script>
```

(Time-series compare overlay is already wired in T15 — this task only adds the Display tab and the KPI sub-line. Categorical pie/doughnut have no compare overlay; bar/hbar fall through to the default Chart.js dataset model — extending that is left for phase 2 since it complicates the legend/coloring.)

- [ ] **Step 2: Verify** — enable compare on the time-series widget. A grey dashed line for the previous 14 days appears with legend. Enable compare on a KPI; sub-text gains "+12% vs prev" or similar.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 20: Frontend — Add widget modal + new-widget defaults

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append:**

```html
<script>
(() => {
  const D = window.__dash;

  function newWidgetDefaults(type) {
    const id = 'wid_' + Math.random().toString(36).slice(2, 10);
    const base = { id, x: 0, y: 99, w: 4, h: 3,
      ignoreGlobalFilters: false, filterOverrides: null,
      compare: { enabled: false, shift: 'previous_period' } };
    if (type === 'kpi')        return { ...base, w: 3, h: 2, type, title: '{{ _("New KPI") }}',         config: { metric: { kind: 'count' } } };
    if (type === 'timeseries') return { ...base,           type, title: '{{ _("New time-series") }}',  config: { chartType: 'line', bucket: 'day', metric: { kind: 'count' }, groupBy: null } };
    return                              { ...base,           type, title: '{{ _("New chart") }}',        config: { chartType: 'bar', dimension: 'doctype', metric: { kind: 'count' }, topN: 10, sort: 'desc' } };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const fab = document.getElementById('addWidgetFab');
    const modal = document.getElementById('addWidgetModal');
    fab.addEventListener('click', () => modal.classList.remove('hidden'));
    document.getElementById('addWidgetClose').addEventListener('click', () => modal.classList.add('hidden'));
    modal.querySelectorAll('button[data-type]').forEach(b => b.addEventListener('click', async () => {
      const w = newWidgetDefaults(b.dataset.type);
      const { layout } = D.getState();
      layout.grid.push(w);
      modal.classList.add('hidden');
      D.renderGrid();
      await D.saveLayout();
      D.openSettings(w.id);
    }));
  });
})();
</script>
```

- [ ] **Step 2: Verify** — in Edit mode, click the FAB, pick "Categorical chart". A new bar widget appears at the bottom; the settings drawer auto-opens.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 21: Frontend — Time-range presets + global filter wiring

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append:**

```html
<script>
(() => {
  const D = window.__dash;
  const PRESETS = [
    { id: 'today',       label: '{{ _("Today") }}' },
    { id: 'yesterday',   label: '{{ _("Yesterday") }}' },
    { id: 'last_7d',     label: '{{ _("Last 7 days") }}' },
    { id: 'last_30d',    label: '{{ _("Last 30 days") }}' },
    { id: 'this_month',  label: '{{ _("This month") }}' },
    { id: 'custom',      label: '{{ _("Custom") }}' },
  ];

  function renderPresetChips() {
    const root = document.getElementById('datePresetChips');
    D.clear(root);
    const { layout } = D.getState();
    PRESETS.forEach(p => {
      const chip = D.tpl('presetChipTemplate');
      chip.dataset.preset = p.id;
      chip.textContent = p.label;
      chip.setAttribute('aria-selected', layout.globalFilters.datePreset === p.id ? 'true' : 'false');
      chip.addEventListener('click', async () => {
        layout.globalFilters.datePreset = p.id;
        if (p.id !== 'custom') {
          layout.globalFilters.dateFrom = null;
          layout.globalFilters.dateTo = null;
        }
        await D.saveLayout();
        renderPresetChips();
        refreshAllWidgets();
      });
      root.appendChild(chip);
    });
  }

  function refreshAllWidgets() {
    const { layout } = D.getState();
    document.querySelectorAll('.grid-stack-item').forEach(it => {
      const id = it.getAttribute('gs-id');
      const w = layout.grid.find(g => g.id === id);
      if (!w) return;
      D.renderWidgetBody(w, it.querySelector('.widget-body'));
    });
  }
  D.refreshAllWidgets = refreshAllWidgets;
  D.renderPresetChips = renderPresetChips;

  document.addEventListener('DOMContentLoaded', () => {
    renderPresetChips();
    const procSel = document.getElementById('globalProcess');
    const { layout } = D.getState();
    procSel.value = layout.globalFilters.process || 'all';
    procSel.addEventListener('change', async () => {
      layout.globalFilters.process = procSel.value;
      await D.saveLayout();
      refreshAllWidgets();
    });
    document.getElementById('refreshNowBtn').addEventListener('click', refreshAllWidgets);
  });
})();
</script>
```

- [ ] **Step 2: Verify** — click "Last 7 days" → all widgets that don't override the global filter update. Selected chip is styled.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 22: Frontend — Drill-down on click

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append:**

```html
<script>
(() => {
  const D = window.__dash;
  const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";

  function effectiveFilters(widget) {
    const { layout } = D.getState();
    const base = widget.ignoreGlobalFilters ? {} : { ...layout.globalFilters };
    return Object.assign(base, widget.filterOverrides || {});
  }

  function resolvePreset(preset) {
    const today = new Date(); today.setHours(0,0,0,0);
    const fmt = d => d.toISOString().slice(0, 10);
    if (preset === 'today') return [fmt(today), fmt(today)];
    if (preset === 'yesterday') { const y = new Date(today); y.setDate(y.getDate() - 1); return [fmt(y), fmt(y)]; }
    if (preset === 'last_7d')   { const s = new Date(today); s.setDate(s.getDate() - 6);  return [fmt(s), fmt(today)]; }
    if (preset === 'last_30d')  { const s = new Date(today); s.setDate(s.getDate() - 29); return [fmt(s), fmt(today)]; }
    if (preset === 'this_month'){ const s = new Date(today.getFullYear(), today.getMonth(), 1); return [fmt(s), fmt(today)]; }
    return [null, null];
  }

  function buildDrilldownUrl(widget, extra = {}) {
    const f = effectiveFilters(widget);
    const qs = new URLSearchParams();
    qs.set('prcfW', f.process || 'all');
    if (f.dateFrom && f.dateTo) {
      qs.set('startDate', f.dateFrom); qs.set('endDate', f.dateTo);
    } else if (f.datePreset && f.datePreset !== 'custom' && f.datePreset !== null) {
      const [s, e] = resolvePreset(f.datePreset);
      if (s && e) { qs.set('startDate', s); qs.set('endDate', e); }
    }
    for (const df of (f.docFilters || [])) {
      qs.append('docfield', df.field);
      qs.append('docvalue', df.value);
    }
    if (extra.docfield)  { qs.append('docfield', extra.docfield); qs.append('docvalue', extra.docvalue); }
    if (extra.startDate) qs.set('startDate', extra.startDate);
    if (extra.endDate)   qs.set('endDate', extra.endDate);
    if (f.status)        qs.set('status', f.status);
    return `${API_PREFIX}workitems_overview?${qs.toString()}`;
  }
  D.buildDrilldownUrl = buildDrilldownUrl;

  D.onChartClick = function(widget, evt, elements) {
    if (!elements?.length) return;
    const el = elements[0];
    const { chartInstances } = D.getState();
    const label = (chartInstances.get(widget.id)?.data?.labels || [])[el.index];
    let extra = {};
    if (widget.type === 'timeseries') {
      extra = { startDate: label, endDate: label };
    } else if (widget.type === 'categorical') {
      extra = { docfield: widget.config.dimension, docvalue: label };
    }
    window.location.href = buildDrilldownUrl(widget, extra);
  };
})();
</script>
```

- [ ] **Step 2: Verify** — click a bar in "Top doctypes today" → lands on `/workitems_overview?prcfW=...&startDate=...&docfield=doctype&docvalue=Invoice`. Click a KPI → goes to workitems with the same date scope.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 23: Frontend — Auto-refresh

**Files:**
- Modify: `templates/js/_dashboardJS.html`

- [ ] **Step 1: Append:**

```html
<script>
(() => {
  const D = window.__dash;
  let timer = null;

  function start() {
    if (timer) clearInterval(timer);
    timer = setInterval(() => {
      if (document.hidden) return;
      if (D.getState().drawerWidgetId) return;
      D.refreshAllWidgets();
      const hint = document.getElementById('lastUpdatedHint');
      if (hint) hint.textContent = '{{ _("Updated") }} ' + new Date().toLocaleTimeString();
    }, 30_000);
  }
  document.addEventListener('DOMContentLoaded', start);
})();
</script>
```

- [ ] **Step 2: Verify** — observe a KPI counter update at most every 30 seconds. Open the drawer; timer pauses.

- [ ] **Step 3: Hand off for review.**

```
git diff --stat
```

Stop.

---

## Task 24: Translation pass

**Files:**
- Modify: `messages.pot`, `translations/de/LC_MESSAGES/messages.po`, `translations/fr/LC_MESSAGES/messages.po`, `translations/it/LC_MESSAGES/messages.po`, and the matching `.mo` outputs.

- [ ] **Step 1: Activate the venv** and run from the repo root:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2: Open each `translations/<lang>/LC_MESSAGES/messages.po`** and translate the new strings introduced by the dashboard. New strings include:

- `Drag, resize, and configure widgets to make this dashboard your own.`
- `Add filter`, `Add widget`, `Add a widget`, `Refresh now`
- `Edit`, `Done`, `Reset`, `Apply`, `Cancel`, `Settings`, `Remove`
- `Remove this widget?`, `Reset layout to defaults?`
- `Updated`, `Could not load`
- `Edit widget`, `Data`, `Filters`, `Display`
- `Title`, `Metric`, `Field`, `Chart type`, `Time bucket`, `Group by (optional)`, `Dimension`, `Top N`, `Sort`, `None`
- `Use dashboard filters`, `Date`, `Custom range`, `Doc filters`
- `Compare to previous period`, `Overlays the previous period’s data for comparison.`, `vs prev`
- `KPI card`, `Single big metric for an at-a-glance summary.`, `Time-series chart`, `Trend over time as line, area, or bar.`, `Categorical chart`, `Bar or pie split by a dimension (doctype, currency, ...).`
- `New KPI`, `New time-series`, `New chart`
- `Today`, `Yesterday`, `Last 7 days`, `Last 30 days`, `This month`, `Custom`
- `Imported today`, `Processed today`, `Current backlog`, `Avg processing time`, `Documents Processed Over Time`, `Top doctypes today`
- `Count`, `Sum`, `Average`, `Min`, `Max`
- `Previous period`

- [ ] **Step 3: Compile.**

```bash
pybabel compile -d translations
```

- [ ] **Step 4: Verify** — switch UI language to German; confirm the dashboard chrome translates.

- [ ] **Step 5: Hand off for review.**

```
git diff --stat translations/ messages.pot
```

Stop.

---

## Task 25: Acceptance test against spec §12

**Files:**
- None (verification only)

- [ ] **Step 1: Walk the acceptance criteria from `2026-04-27-customizable-dashboard-design.md` §12.** Tick each as it passes:

  1. A user with `dashboard.view` opens `/dashboard` and sees widgets render with data within 2s on a warm cache.
  2. Dragging and resizing widgets persists across page reload.
  3. Adding a new widget, configuring it, and applying renders a chart with correct data without a full page reload.
  4. Toggling between View and Edit hides/shows the chrome correctly; charts don't re-fetch on the toggle.
  5. Compare mode renders a second series for the previous period.
  6. Clicking a chart segment / KPI card navigates to a workitems overview page with the right filters in the URL.
  7. "Reset to default" returns the user to the starter layout.
  8. A user with a saved layout that references a process they no longer have permission for sees the rest of the dashboard render fine (no 500, no full-page break).
  9. All `widget_data` queries are parameterized; manual SQL injection attempts in field/dimension names get a 400.

- [ ] **Step 2: For criterion 8**, simulate by editing the user's `LayoutJSON` directly in the DB to reference a non-existent process, reload, confirm the rest of the widgets render and the offending widget shows a "no data in scope" placeholder.

- [ ] **Step 3: For criterion 9**, send a hand-crafted PUT to `/api/dashboard/layout` with `dimension: "doctype; DROP TABLE Users--"`. Expected: HTTP 400 with `widget X: dimension unknown`.

- [ ] **Step 4: Hand off with a summary**:

```
git status
git log --oneline main..HEAD
```

Surface the diff and the acceptance-test results to the user. Stop.

---

## Self-review notes (writing-plans)

- **Spec coverage:** Every section of the spec maps to a task — schema (T1, T2), starter layout + validator (T3), field metadata endpoint (T4), CRUD (T5–T7), query builder (T8–T9), data + compare endpoints (T10–T11), frontend scaffold (T12), grid + edit mode (T13), three renderers (T14–T16), drawer tabs (T17–T19), add modal (T20), presets (T21), drill-down (T22), refresh (T23), translations (T24), acceptance (T25).
- **Sunset of legacy endpoints** is explicitly out of scope per spec §10 — flagged in the file-structure table.
- **Type consistency:** `_run_widget_queries` is defined in T10 step 1 and referenced from T11 step 1; the executor must complete T10 before T11 runs end-to-end. The `window.__dash` namespace introduced in T13 is the contract every later frontend task extends. Method names that surface across tasks: `D.fetchWidgetData`, `D.renderKpi`, `D.renderWidgetBody`, `D.renderGrid`, `D.saveLayout`, `D.openSettings`, `D.switchDrawerTab`, `D.refreshAllWidgets`, `D.buildDrilldownUrl`, `D.onChartClick`, `D.getState`, `D.setState`, `D.makeRowSelect`, `D.makeRowInput`, `D.makeRowCheckbox`, `D.fillSelect`.
- **Placeholder scan:** every code step contains the actual code; verification steps reference exact endpoints and expected JSON shapes; no `// TODO` markers in the plan.
- **Open question from spec §11** about `proc_time_avg` denominator is resolved in T8/T9 by using `DATEDIFF(SECOND, ImportColumn, ExportColumn)`, matching the existing `avg_processing_time` legacy endpoint convention.
- **DOM safety:** all dynamic content is built with `el()`/`tpl()`/`textContent`; the only places HTML appears verbatim are inside `<template>` blocks in `dashboard.html`, where the markup is fully under our control with no interpolation.
