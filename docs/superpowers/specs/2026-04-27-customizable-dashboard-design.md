# Customizable Per-User Dashboard — Design

**Status:** Approved (brainstorm)
**Date:** 2026-04-27
**Branch context:** rebuilds `templates/dashboard.html` and the dashboard-related routes in `app.py`

## 1. Goals

Replace today's fixed dashboard (4 KPI cards, 2 charts, activity feed) with a per-user customizable dashboard. Each user can:

- Drag, drop, and resize widgets on a 12-column grid; any widget can go anywhere.
- Add KPI cards, time-series charts, and categorical charts.
- Pick the metric (Y-axis): count, sum/avg/min/max of numeric document fields, or processing time.
- Pick the dimension (X-axis): time bucket (hour/day/week/month) or any categorical field (doctype, doccurrency, ProcessName, status, etc.).
- Apply dashboard-wide filters (process, date preset, doc field=value rows) with per-widget overrides.
- Toggle View ⇄ Edit mode.
- Click a chart segment / KPI card to drill down to the workitems overview pre-filtered to that slice.
- Enable per-widget compare mode (this period vs previous period).

## 2. Non-goals (deferred to a later phase)

- Multiple dashboards / tabs per user.
- Shareable dashboards or cross-user copy.
- Table / Top-N list widget, heatmaps.
- PNG / PDF export.
- Admin-managed organization defaults / templates.
- Mobile-specific layout — automatic stacking on narrow viewports is enough.
- Annotations / notes widget.

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Ownership | Per-user (one dashboard each) | Personal productivity is the dominant use case. |
| Layout system | 12-column drag-resize grid (Gridstack.js) | Matches Datadog/Grafana muscle memory; small MIT dependency; auto-stacks on narrow viewports. |
| Widget palette (v1) | KPI card, time-series chart, categorical chart | Covers the questions today's dashboard answers, plus the user's stated need for chart-type + axis flexibility. |
| Y-axis depth | count, sum/avg/min/max of numeric fields, processing time | Matches all four current KPIs and the user's "much more" ask. |
| Filters | Dashboard-wide filter bar + per-widget overrides | Industry standard; preserves the current "filter by process" flow while allowing power-user dashboards. |
| Defaults on first visit | Existing widgets pre-populated | Smoothest migration; no user starts from blank. |
| Auto-refresh | Match today (KPI 30s, activity 60s) | No reason to change; predictable. |
| Edit mode | Toggle View ⇄ Edit | Prevents accidental drags during touchpad scrolling. |
| Compare mode | Per-widget toggle | Common BI feature; previous-period overlay. |
| Drill-down | On click, link to workitems overview with filters | Single source of truth for raw rows is the workitems page. |
| Time-range presets | Today / Yesterday / Last 7d / Last 30d / This month / Custom | Beats free-typing dates. |
| Storage | One JSON blob per user in `DashboardLayouts` | Schema barely changes when widget options evolve; trivial to copy/share later. |
| Query strategy | Single generic `widget_data` endpoint that takes a widget config + filters | Avoids one endpoint per chart type. |

## 4. Architecture

```
[Browser]                              [Flask: app.py]                       [DBs]
─────────                              ────────────────                      ─────
dashboard.html  ──── GET /dashboard ──>  dashboard()         ───────────────> NexoraDB.DashboardLayouts (JSON)
                                                                              SearchConfig + StatConfig (existing)
                                                                              FieldMetadata (NEW)

Gridstack.js  ─── PUT /api/dashboard/layout (save JSON) ───> save_layout()
                                                                              ┌─> StatisticsDB / Mobscan (data)
Chart.js     ──── POST /api/dashboard/widget_data ─────────> widget_data() ──┤
                                                                              └─> OctoDB (backlog only)

                  POST /api/dashboard/widget_compare ───────> compare data
```

Key idea: the frontend sends a "widget spec" JSON with each data request. The backend has one builder that translates spec → safe parameterized SQL → labels+series. No new endpoint per chart type.

## 5. Data model

### 5.1 New table: `DashboardLayouts` (NexoraDB)

```sql
CREATE TABLE dbo.DashboardLayouts (
    UserID         INT          NOT NULL PRIMARY KEY,
    LayoutJSON     NVARCHAR(MAX) NOT NULL,
    SchemaVersion  INT          NOT NULL DEFAULT 1,
    UpdatedAt      DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_DashboardLayouts_Users FOREIGN KEY (UserID) REFERENCES dbo.Users(userID)
);
```

DDL goes under `sql/config/tables/DashboardLayouts_asCreate.sql`. One row per user. Absent row = user gets the default layout on first visit (lazy-insert on first save).

### 5.2 New table: `FieldMetadata` (NexoraDB)

We need to know which fields are numeric / categorical / date so the chart-builder UI offers the right options and the SQL builder uses the right aggregation.

```sql
CREATE TABLE dbo.FieldMetadata (
    FieldKey   VARCHAR(100) NOT NULL PRIMARY KEY,  -- matches SearchConfig.col_<key> suffix
    DataType   VARCHAR(20)  NOT NULL,              -- 'numeric' | 'categorical' | 'date' | 'text'
    Aggregable BIT          NOT NULL DEFAULT 0,    -- can be SUM/AVG'd
    Sortable   BIT          NOT NULL DEFAULT 1
);
```

DDL goes under `sql/config/tables/FieldMetadata_asCreate.sql` plus a seed insert under `sql/other/FieldMetadata_seed.sql`. Pre-populated rows for known fields:

| FieldKey | DataType | Aggregable |
|---|---|---|
| grossamount | numeric | 1 |
| netamount | numeric | 1 |
| vatamount | numeric | 1 |
| docdate | date | 0 |
| doctype | categorical | 0 |
| doccurrency | categorical | 0 |
| crdname | categorical | 0 |
| branch | categorical | 0 |
| department | categorical | 0 |
| docsource | categorical | 0 |
| (… everything else in `SearchConfig.col_*`) | categorical | 0 |

Cached in-process for 1h via `cache.cached`. New fields added by inserting a row.

### 5.3 LayoutJSON schema (v1)

```jsonc
{
  "schemaVersion": 1,
  "globalFilters": {
    "process": "all",                  // or a specific ProcessName the user has permission for
    "datePreset": "today",             // today | yesterday | last_7d | last_30d | this_month | custom
    "dateFrom": null,                  // used only when datePreset === "custom" (ISO 8601)
    "dateTo":   null,
    "docFilters": [
      { "field": "doctype", "value": "Invoice" }
    ]
  },
  "grid": [
    {
      "id": "wid_<uuid>",              // client-generated, stable across saves
      "x": 0, "y": 0, "w": 3, "h": 2,  // Gridstack coords (12-col)
      "type": "kpi",                   // kpi | timeseries | categorical
      "title": "Imported today",
      "config": { /* see 5.4 */ },
      "ignoreGlobalFilters": false,
      "filterOverrides": null,         // partial overrides when ignoreGlobalFilters=false (object or null)
      "compare": { "enabled": false, "shift": "previous_period" }   // v1 supports only "previous_period"; reserved for future "previous_year" etc.
    }
  ]
}
```

### 5.4 Widget configs by type

**KPI:**
```jsonc
{
  "metric": { "kind": "count" }
  // when kind ∈ {sum, avg, min, max}: include "field": "<numeric field key>"
  // when kind === "proc_time_avg": no field needed
}
```

**Time-series:**
```jsonc
{
  "chartType": "line",                 // line | area | bar
  "bucket": "day",                     // hour | day | week | month
  "metric": { "kind": "count" },
  "groupBy": null                      // optional categorical field for stacked series
}
```

**Categorical:**
```jsonc
{
  "chartType": "bar",                  // bar | hbar | pie | doughnut
  "dimension": "doctype",              // any FieldMetadata.DataType='categorical' field
  "metric": { "kind": "count" },
  "topN": 10,                          // 5 | 10 | 25 | "all"
  "sort": "desc"                       // desc | asc | alpha
}
```

## 6. Backend API

All routes live in `app.py` under the existing dashboard section, guarded by `@require_permission('dashboard.view')` and CSRF.

| Method | Route | Purpose |
|---|---|---|
| GET  | `/api/dashboard/layout` | Returns the user's saved LayoutJSON (or the default layout if no row). |
| PUT  | `/api/dashboard/layout` | Saves the LayoutJSON. Body validated against the schema. Upserts. |
| POST | `/api/dashboard/layout/reset` | Deletes the user's row → next GET returns default. |
| POST | `/api/dashboard/widget_data` | Body: `{ widget, globalFilters }`. Returns `{ labels: [...], series: [{ label, data }] }`. |
| POST | `/api/dashboard/widget_compare` | Same body, returns previous-period series (only called when `widget.compare.enabled`). |
| GET  | `/api/dashboard/field_metadata` | Returns `[{ field, type, aggregable, label, processes: [...] }]` for the user's allowed processes. Cached. |

Existing endpoints (`/api/dashboard/kpi_stats`, `/processed_over_time`, `/hourly_stats`, `/avg_processing_time`, `/recent_activity`, `/set_filter`) stay alive during rollout, get removed once the new dashboard is the only one (see §10).

### 6.1 widget_data builder (the load-bearing piece)

A single `def build_widget_query(widget, global_filters, allowed_processes) -> (sql, params, post_process_fn)` function.

Steps:

1. **Resolve filters:** start from `global_filters` (or `{}` if `widget.ignoreGlobalFilters`); merge `widget.filterOverrides` on top.
2. **Resolve target tables:** for each ProcessName in scope (intersection of `globalFilters.process` and `allowed_processes`), look up `StatConfig.TableName` + `SearchConfig.col_<field>` mappings — same union-by-process pattern the current endpoints use (regular vs Mobscan engines split via `split_processes_by_server`).
3. **Build the SELECT:**
   - X-axis (dimension):
     - time bucket → `CAST(<ExportColumn> AS DATE)` for `day`, `DATEPART(hour, ExportColumn)` for `hour`, `DATEPART(week, ExportColumn)` for `week`, `DATEFROMPARTS(YEAR, MONTH, 1)` for `month`.
     - categorical → `<col_dimension>` joined to the table via SearchConfig mapping.
   - Metric:
     - `count` → `COUNT(*)`
     - `sum` / `avg` / `min` / `max` → `SUM(col_<field>)` etc., field validated against `FieldMetadata.Aggregable=1`.
     - `proc_time_avg` → `AVG(DATEDIFF(MINUTE, <ImportColumn>, <ExportColumn>))`.
4. **WHERE:**
   - Date range from preset (resolved server-side: `today`, `yesterday`, `last_7d`, `last_30d`, `this_month`, `custom` → `dateFrom`/`dateTo`).
   - Process condition.
   - Doc field=value pairs (parameterized; reuse the existing temp-table pattern for large ID sets used in workitems_overview to avoid the 2100-param limit).
5. **ORDER + TOP** (categorical) or chronological order (time-series).
6. **Return parameterized SQL** — every user-supplied value goes through `?` placeholders. Field/dimension/process names are validated against a whitelist from `get_valid_search_columns()` + `FieldMetadata` + the user's `allowed_processes`. Anything not on the whitelist → 400.

Caching key: stable hash of `(userid, widget config canonicalized, global_filters, allowed_processes)` — TTL 60s for KPIs (single number) and 300s for chart series. Use the same `cache` instance as today.

### 6.2 widget_compare

For `widget_compare`, the resolved `dateFrom/dateTo` is shifted backward by the same length and the query is rerun. Returned as `series[1]` with label = "previous period" (i18n). Frontend overlays it as a dashed line / lighter bar.

### 6.3 Validation contract

`PUT /api/dashboard/layout` validates the JSON server-side:
- `schemaVersion` matches.
- `grid[].type` ∈ {kpi, timeseries, categorical}.
- Each widget's `config` matches the per-type shape.
- Field/dimension keys exist in `FieldMetadata`.
- Numeric metrics reference an `Aggregable=1` field.
- Process names in filters are subsets of the user's `dashboard.filter.process.*` permissions.
- Coordinates are non-negative integers; `w` and `h` ≤ 12.

Reject (400) with a message naming the offending widget id on failure. Never silently coerce — bad JSON means bad UX later.

## 7. Frontend

### 7.1 Files

- `templates/dashboard.html` — rewritten. Adds Gridstack CSS+JS from CDN.
- `templates/js/_dashboardJS.html` — rewritten. Hosts the widget renderer, settings drawer, edit-mode logic, drill-down handlers.
- `static/css/dashboard.css` — new styles for the grid container, widget chrome, filter bar, drawer.

### 7.2 Component sketch

```
DashboardPage
├─ Header (existing _header.html)
├─ FilterBar           ← process select, date-preset chips, +Filter row, Refresh indicator, [Edit] button
├─ GridContainer       ← Gridstack instance, renders one WidgetShell per cell
│   └─ WidgetShell     ← chrome: title, drag handle, settings cog, remove X (edit-mode only)
│       └─ WidgetBody  ← KpiCard | TimeseriesChart | CategoricalChart
├─ AddWidgetButton     ← FAB (edit mode only) → opens AddWidgetModal
└─ WidgetSettingsDrawer ← right-side slide-in, dynamic form per type
```

Edit mode toggles a `data-edit="true"` attribute on the grid root; CSS shows handles/cogs/remove buttons. Gridstack's `staticGrid` is flipped on/off accordingly.

### 7.3 WidgetSettingsDrawer

Slides in from the right (~480px wide). Tabs: **Data** / **Filters** / **Display**.

- **KPI — Data tab:** title, metric (count / sum / avg / min / max / proc_time_avg), field picker (only when metric needs it), compare toggle.
- **Time-series — Data tab:** title, chart type, time bucket, metric, group-by.
- **Categorical — Data tab:** title, chart type, dimension, metric, top-N, sort.
- **Filters tab (all types):** "Use dashboard filters" toggle (= `!ignoreGlobalFilters`). When off: process selector + date preset + doc field/value rows (reusing the workitems-overview combobox + autocomplete components).
- **Display tab:** color preset (small palette), legend on/off, decimal places (KPI), value-on-bar (charts).

Local edits buffer in the drawer. **Apply** commits to `LayoutJSON` and re-renders the widget. **Cancel** discards. Drawer closes only on explicit Cancel or Apply (no click-outside dismiss — too easy to lose work).

### 7.4 Drill-down

Each widget type implements `getDrilldownUrl(point)`:

- **KPI** → `/workitems?prcfW=<process>&startDate=<from>&endDate=<to>&<docFilters as querystring>`
- **Time-series** → same as KPI plus `startDate`/`endDate` clamped to the clicked bucket (day, hour, etc.).
- **Categorical** → same plus `docfield=<dimension>&docvalue=<clicked value>`.

Click handler on Chart.js segments + on KPI card → `window.location.href = url`. Drill-down respects per-widget filter overrides (uses the widget's effective filters, not always the global ones).

### 7.5 Refresh cadence

Same as today:
- KPI cards re-fetch every 30s.
- Charts re-fetch every 30s.
- (Activity feed cadence drops out — feed is removed in v1; see §8.)

A subtle "auto-refresh on" indicator in the filter bar with last-updated timestamp. Manual refresh button next to it. Pauses while the settings drawer is open (no surprise re-render of the widget being edited).

### 7.6 Add widget flow

In edit mode, `+ Add widget` opens a modal with three tiles (KPI / Time-series / Categorical), each with a one-sentence description and an example thumbnail. Pick → drawer opens with sensible defaults pre-filled (KPI of "count today", time-series "count by day for 14 days", categorical "count by doctype, top 10"). Apply → widget appears at the bottom of the grid; user drags/resizes from there.

## 8. Defaults & migration

On first GET `/api/dashboard/layout` for a user with no row, the server returns a hard-coded **starter layout** (a Python dict serialized to JSON) that mirrors today's dashboard.

**Starter `globalFilters`:** `process='all'`, `datePreset='today'`, `docFilters=[]`. So all widgets default to today's data unless they override.

| Widget | Type | Coords (x,y,w,h) | Notes |
|---|---|---|---|
| Imported today | kpi | 0,0,3,2 | `metric=count`. No override — uses global `today`. |
| Processed today | kpi | 3,0,3,2 | `metric=count`. `filterOverrides={status:'Done'}`. |
| Current backlog | kpi | 6,0,3,2 | `metric=count`. `filterOverrides={status:'Ready', datePreset:null}` — backlog is point-in-time, not bound to a date range. |
| Avg processing time | kpi | 9,0,3,2 | `metric=proc_time_avg`. No override — uses global `today`. |
| Documents processed over time | timeseries | 0,2,8,4 | `chartType=line`, `bucket=day`, `metric=count`. `filterOverrides={datePreset:'custom', dateFrom:<today-13>, dateTo:<today>}` resolved at default-generation time so users see "last 14 days" exactly. |
| Top doctypes today | categorical | 8,2,4,4 | `chartType=bar`, `dimension=doctype`, `metric=count`, `topN=5`. No override — uses global `today`. |

The 14-day default uses the `custom` preset (rather than introducing a `last_14d` preset) so the supported preset list stays tight: `today | yesterday | last_7d | last_30d | this_month | custom`.

The activity feed ("Recent Validations") is removed in v1 — its information is reachable via drill-down on any chart slice. If users miss it, we add a `recent_activity` widget type in phase 2.

A **Reset to default** action in the dashboard menu calls `POST /api/dashboard/layout/reset` and reloads.

## 9. Permissions & security

- All routes still require `dashboard.view`.
- Process visibility uses the existing `dashboard.filter.process.<process>` permissions; `widget_data` filters out any process the user can't see, even if their saved layout references it (graceful: returns empty data with a `warnings: [...]` field rather than 403, so a stale layout doesn't break the page).
- Dimension/field whitelist for `widget_data` derives from:
  1. `SearchConfig.col_*` columns the user's allowed processes have non-null values for.
  2. `FieldMetadata` rows.
  3. A static allow-list of synthetic dimensions: `ProcessName`, `Status`.
- All SQL parameterized; field/dimension/process names validated by exact match against the whitelist.
- `PUT /api/dashboard/layout` runs full server-side validation (§6.3) — never trust client JSON.
- Rate-limit `widget_data` per-user (e.g. 60 req/min via `flask_limiter`) so a runaway dashboard with 50 widgets and short refresh can't DoS the stats DB.

## 10. Rollout plan

Single PR, since storage is additive and the route swap is atomic:

1. **DDL**: ship `DashboardLayouts` and `FieldMetadata` tables + seed.
2. **Backend**: new endpoints alongside the old ones; `dashboard()` route renders the new template.
3. **Frontend**: rewrite `dashboard.html` + `_dashboardJS.html`.
4. **Sunset old endpoints**: in a follow-up PR after the new dashboard has been live for one week, delete `/api/dashboard/kpi_stats`, `/processed_over_time`, `/hourly_stats`, `/avg_processing_time`, `/recent_activity`, `/set_filter`.

No data migration needed — there's nothing to migrate. Existing users get the starter layout on first visit and can immediately customize.

## 11. Open questions

None at design time. The implementation plan will tighten:

- Exact Gridstack version pin and CDN URL (or vendored copy under `static/vendor/`).
- Final color palette and decimal-places defaults.
- Whether `proc_time_avg` denominator is import→export or any-state→export (pick when wiring; today's `avg_processing_time` endpoint is authoritative).
- Drill-down URL building when `groupBy` is set on a stacked time-series.

## 12. Acceptance criteria

- A user with `dashboard.view` can open `/dashboard`, see widgets render with data within 2s on a warm cache.
- Dragging and resizing widgets persists across page reload.
- Adding a new widget, configuring it, and applying renders a chart with correct data without a full page reload.
- Toggling between View and Edit hides/shows the chrome correctly; charts don't re-fetch on the toggle.
- Compare mode renders a second series for the previous period.
- Clicking a chart segment / KPI card navigates to a workitems overview page with the right filters in the URL.
- "Reset to default" returns the user to the starter layout.
- A user with a saved layout that references a process they no longer have permission for sees the rest of the dashboard render fine (no 500, no full-page break).
- All `widget_data` queries are parameterized; manual SQL injection attempts in field/dimension names get a 400.
