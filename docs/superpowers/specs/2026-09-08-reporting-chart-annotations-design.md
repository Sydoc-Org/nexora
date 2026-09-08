# Reporting chart annotations — design

**Date:** 2026-09-08 · **Status:** approved design, plan pending · **Branch:** `feat/284-reporting-chart-annotations` · **Issue:** #284

## Goal

Let the owner of a **saved** report pin a short dated note on its time axis —
"new client onboarded", "mailroom outage" — so the chart explains its own bumps.
Each annotation shows as a marker on the Simple-tab chart and in a compact list
under it. This is roadmap item 1 (Insight track) of the 2026-09-07 reporting
brainstorm, the follow-on to contribution analysis ("Why did it move?").

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Scope | **Per report** — a row references `dbo.Reports(ReportID)`. Not an org-wide event timeline. |
| Surfaces | **Simple tab only** in this pass. Advanced and dashboard cards each own their own Chart.js instance and follow later. |
| Who may write | **Report owner only** — reuse `_is_report_owner(report_id, userid)` from `reports.py`. No new permission code. Anyone who can open the report sees the markers. |
| Add interaction | **Click a bucket** on the chart → inline popover (bucket shown read-only, one text field) → save. |
| Date granularity | **Snap to the chart's bucket key** — the raw SQL grain key the chart already carries in `labels` (`2026-09-01` for a month bucket), never the prettified label and never a free date. |
| Unsaved reports | No annotations. The popover explains "Save the report to add annotations" and offers nothing else. |
| Chart library | No new dependency. The marker is a **second Chart.js dataset** drawn on the existing instance. |

Out of scope, deliberately: Advanced tab, dashboard cards, org-wide annotations,
rich text, editing an annotation in place (delete + re-add covers it), showing
annotations that fall outside the currently charted window, exports, schedules
and the AI assistant reading annotations. Each is one added piece later; none
changes this data model.

## 1. Data model

Migration `sql/_migrations/NexoraDB/0123_report_annotations.sql` (number claimed
in #284), `GO`-separated, guarded by `IF OBJECT_ID(...) IS NULL`:

```sql
CREATE TABLE dbo.ReportAnnotations (
    AnnotationID  INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ReportID      INT           NOT NULL
        CONSTRAINT FK_ReportAnnotations_Reports
        REFERENCES dbo.Reports(ReportID) ON DELETE CASCADE,
    BucketKey     NVARCHAR(64)  NOT NULL,   -- raw chart label, e.g. '2026-09-01'
    Text          NVARCHAR(500) NOT NULL,
    CreatedBy     INT           NOT NULL
        CONSTRAINT FK_ReportAnnotations_Users REFERENCES dbo.Users(userID),
    CreatedAt     DATETIME2(0)  NOT NULL CONSTRAINT DF_ReportAnnotations_CreatedAt DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_ReportAnnotations_Report ON dbo.ReportAnnotations (ReportID, BucketKey);
```

No permission insert: the feature is gated by ownership, not a code. Deleting a
report cascades its annotations. `BucketKey` is stored verbatim from the chart's
`labels[]`; for category axes (no grain) it is the category value.

## 2. API

New module `nx_lib/views/reporting/annotations.py`, registered in
`nx_lib/views/reporting/__init__.py` next to `schedules` (import, re-export,
`register_routes` fan-out). Same shape as `schedules.py`:

| Verb / path | Who | Behaviour |
|---|---|---|
| `GET /api/reporting/reports/<id>/annotations` | anyone who can load the report — a new `_can_view_report(report_id, userid)` in `reports.py`, lifted from the `WHERE` clause `api_reports_get` already uses (owner, `Visibility = 'shared'`, or a `ReportShares` row) | `{ok, data:[{id, bucket, text, author, created_at}]}` ordered by `BucketKey`. |
| `POST /api/reporting/reports/<id>/annotations` | owner | body `{bucket, text}`; 400 if `text` is blank after strip or > 500 chars, or `bucket` is blank or > 64 chars; returns the created row. |
| `DELETE /api/reporting/reports/<id>/annotations/<aid>` | owner | 404 if the annotation is not on that report; `{ok:true}`. |

Every route: 404 on an unknown report, 403 for non-owners on writes, JSON only,
`@limiter.limit("60 per minute")` on POST/DELETE like schedules. No PUT — see
"out of scope". The server does **not** verify that `bucket` is currently one of
the report's buckets; that would mean re-running the report for every save.
`# ponytail: format-only validation; add a bucket check if orphan rows appear`.
An annotation whose bucket is not in the charted window is simply not drawn.

## 3. Front end

All in the Simple tab, behind `RS.state.current.reportId`.

**Load.** `reporting_simple_chart.js` gains `RS.annotations = {list:[], load(reportId)}`.
After a run finishes and the chart mounts, if `RS.state.current.reportId` is set,
`GET …/annotations` fills `list` and the chart re-draws the marker dataset.
Switching or clearing the report empties the list.

**Draw.** One extra dataset on the existing chart: type `line`, `showLine:false`,
point style `triangle` sized ~9 px, plotted at `y = 0` of the primary axis for
each `labels[]` index whose value matches an annotation `bucket`; other indices
`null`. Its tooltip callback shows the annotation text(s) for that bucket. The
dataset is tagged `_nxAnnotations:true` so legend and export code skip it. No
`chartjs-plugin-annotation`.

**Add.** The chart's existing `onClick` (drill-through) gains a modifier check:
a plain click keeps drilling; **Alt+click** (or the "Add annotation" button in the
list header, which then asks for the bucket via the same popover with a
`<select>` of `labels[]`) opens a small popover anchored to the click point:
bucket (read-only, pretty label), `<input maxlength=500>`, Save / Cancel. Save
POSTs, pushes the row into `list`, re-draws, closes. Non-owners and unsaved
reports get no button and no popover; Alt+click falls through to drill.

**List.** A `<ul id="rsAnnotations">` under the chart, hidden when empty: pretty
bucket · text · author, and a delete `×` for the owner (DELETE, splice, re-draw).
Rendered with `NX.esc`; strings for the popover and list live in the shim
`templates/js/_reporting_simple_js.html` and are read off `window`.

Files: `static/js/reporting_simple_chart.js`, `static/js/reporting_simple.js`
(hook load/clear into the report lifecycle), `templates/reporting.html` (the
list + popover markup), `templates/js/_reporting_simple_js.html` (strings),
`static/css/reporting.css`.

## 4. Errors

- Save fails → `NX.toast` the server message, popover stays open.
- Delete fails → toast, row stays.
- 403/404 on load → treat as no annotations, no toast (a shared-then-unshared
  report should not shout).

## 5. Testing

- **Integration** `tests/integration/test_reporting_annotations_api.py`: owner
  create → list → delete; non-owner 403 on POST/DELETE, 200 on GET when shared;
  blank / over-long text 400; delete of another report's annotation 404; report
  delete cascades.
- **Unit** none beyond the route tests — there is no pure helper worth one.
- **e2e** `tests/e2e/test_reporting_annotations.py`: load a saved report, Alt+click
  a bucket, save, marker + list row appear; delete, both gone; unsaved report
  shows no add affordance.
- Translations + help-sync tests as usual.

## 6. Docs & i18n

`docs/howto/reporting.md` (new "Chart annotations" section), `docs/howto/reporting-guide.md`
+ `templates/_reporting_help.html` (one tip each, same commit), `CHANGELOG.md`
under `[Unreleased]` / Added, msgids for the popover and list, `docs/howto/db-migrations.md`
untouched (nothing new there). No env key, no deploy exclude.
