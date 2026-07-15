# Reporting UX friction fixes — design

**Date:** 2026-07-15 · **Branch:** `feature/2.5.64` · **Scope:** UX (behavior), not visual redesign
**Origin:** live Playwright audit of `/reporting` (Simple tab + AI surfaces) as `ben.streich` on INT.
Screenshots: `var/screenshots/ux-audit-*.png`.

## Problem

The reporting logic is solid (all old gap-list items shipped), but six friction points make the
everyday Simple-tab path feel untrustworthy:

1. Opening a saved report whose definition no longer validates (e.g. metric `workitem_count`
   disabled by migration `0021`) shows only "This report is outdated — open it in Advanced to fix
   it." The server's precise `detail` ("unknown metric: 'workitem_count'") is discarded by
   `friendlyRunError()` (`templates/js/_reporting_simple_js.html:240`), no action is wired, and
   Save/Export/Show-query stay clickable with nothing loaded.
2. A successful run with 0 rows renders a bare header-only table and a "0" KPI — no explanation,
   no hint to widen the range or drop a filter.
3. "← Back" from an opened report always goes to the wizard, even when the report was opened from
   a library card; the tiny "×" is the actual back-to-library. Two backs, wrong default.
4. Loading a saved report into the wizard leaves the Custom date picker EMPTY while the old range
   is still silently applied on "Show result" — hidden state.
5. Drill-drawer workitem IDs are anchors (`_reporting_drill_js.html:116`) but styled as plain text
   and jump away to `/workitems?search=…` — no in-context detail.
6. A failed agent run shows raw ODBC tuples (`('42000', "[Microsoft][ODBC SQL Server Driver]…`) in
   the step trace, retries identical broken SQL (error 1033: ORDER BY in derived table), ends in
   apologetic prose with no retry affordance, yet still offers Open-in-builder artifacts.

Opportunistic: the header result meta ("2 rows · 1707 ms") persists across tabs/views after the
result is gone.

## Design

### 1. Dead-end 400 → informative + actionable (Simple pane)

- `friendlyRunError(status, data)` returns the server `error` **plus** `detail` when present
  (`"<error> — <detail>"`); the canned "outdated" line remains the fallback for 400s without
  detail.
- The error state renders an inline **Open in Advanced** button (reuses the existing
  open-in-advanced handler with the already-loaded saved definition).
- The result header keeps showing the saved report's title even when the run failed.
- Save, Export, Show query, Adjust in wizard are disabled while no successful result is loaded
  (single `hasResult` guard).

### 2. Zero-row empty state (Simple pane)

- After a successful run with `rows.length === 0`: instead of the bare table, render an empty-state
  message: "No data matched these filters." + hint "Widen the time range or remove a filter."
- Chips stay visible and removable (removing one already reruns). KPI band may still render its
  zeros. No auto-widen actions (YAGNI).

### 3. Back consistency (Simple pane)

- Track the origin of the current result view: `'library' | 'wizard' | 'ask'`.
- "← Back" returns to that origin (library list, wizard with state, or library for ask-AI results).
- "×" (back to library) stays as-is; "Adjust in wizard" remains the explicit wizard entry.

### 4. Wizard reflects loaded state (Simple pane)

- When a definition is loaded into the wizard: a literal `between` date range prefills the Custom
  picker text; a token range (`this_year`, …) selects the matching preset chip instead of Custom.
- Guarantee: what the wizard displays is exactly what "Show result" runs — no hidden carried-over
  range. If the picker is emptied by the user, the range is dropped from the definition.

### 5. Drill drawer → inline workitem detail (shared drawer)

- Workitem-ID cells get link styling (visible affordance).
- Click opens the shared `NexoraWorkitemDetail.render(wid, container, {readOnly: true, perms})`
  panel in a modal layered over the drawer — same pattern as the Prepared Documents preview
  (`templates/js/_prepared_documents_js.html:95`). Requires including
  `_workitem_detail_panel_js.html` + its perms JSON on the reporting page (server-side perm gates
  stay authoritative).
- Plain `href` to `/workitems?search=<id>` kept for middle-click/new-tab; normal click is
  intercepted for the modal.
- Users without `workitems.details.view` perms: no modal, link behaves as today.

### 6. Agent errors teach + retry (AI surfaces)

- **Humanize tool errors**: in the `run_sql` error path (`nx_lib/reporting/ai_tools.py`), strip the
  pyodbc tuple wrapper and driver prefixes before the message reaches the trace/model; map common
  SQL Server errors to a teaching hint appended for the model and the user. First mapping: error
  1033 → "ORDER BY inside a derived table needs TOP or OFFSET — or move ORDER BY to the outer
  SELECT." (Same pattern as the `tsql_limit` gate from `b2f9f39`.)
- **Retry affordance**: a failed agent run (turn-cap or error ending) renders a **Try again**
  button that resends the same question.
- **Prompt line** (`nx_lib/reporting/ai.py` agent prompt): never resubmit SQL identical to a
  previously failed attempt — change the query before retrying.

### Opportunistic

- Reset the header result meta when the result view is left/superseded.

## Non-goals

- No visual redesign (reskin shipped separately). No metric back-compat aliasing for
  `workitem_count` — disabled means disabled; the UX now tells the user why. No auto-fix of broken
  definitions. Pin-to-dashboard stays parked (own plan).

## Testing

- Unit/integration: friendlyRunError detail passthrough (route-level test asserting `detail` in
  400 body already exists — extend front-end e2e), zero-row empty state, wizard prefill from
  literal + token ranges, ODBC humanizer mapping (pure function test), agent retry button wiring.
- e2e (`tests/e2e/test_reporting_simple.py` conventions): library→broken-report shows detail +
  Open-in-Advanced; back-origin behavior; drill modal opens detail panel (stub run endpoint per
  the `_stub_run_ok` idiom to avoid the known race).
- i18n: new strings extracted + translated de/fr/it; `test_translations.py` green.

## Rollout

Single branch `feature/2.5.64`, per-fix commits, changelog under `[Unreleased]`.
