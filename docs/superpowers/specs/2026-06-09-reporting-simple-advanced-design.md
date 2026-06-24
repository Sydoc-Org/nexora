# Reporting — Simple / Advanced restructure (Spec 2) — design

- **Date:** 2026-06-09
- **Status:** approved design, pre-plan
- **Predecessor:** `2026-06-09-reporting-date-dimension-design.md` (Spec 1, shipped) — this spec
  consumes the date dimension + grain.
- **Driver:** memory `project_reporting_usability_gaps` gap #4 ("too complicated") — the target
  audience is non-data-science stakeholders, mostly report *viewers*.

## Goal

Restructure `/reporting` into two tabs. **Simple** = a library of ready-made reports + a guided
wizard + an optional ask-AI helper, all rendering results as number/chart cards. **Advanced** =
today's full builder, untouched. Nothing is removed; power features move under Advanced.

## Non-goals (out of scope)

- Grain support on the generic `table` provider (grain stays docprocessing-only).
- A template/featured flag or any `dbo.Reports` schema change — no migration in this spec.
- Multi-card dashboard pages (one report at a time in Simple).
- Share / schedule UI inside Simple (both stay in Advanced; saved wizard reports inherit them).
- The deferred distinct-workitem-ID metric (usability gap #5).

## Locked decisions

| Decision | Choice |
|---|---|
| Landing | Smart + sticky: first visit → Simple; afterwards remember last-used tab per user (`localStorage`) |
| Routing | One route `/reporting`, two client-side panes; deep link `?tab=advanced` |
| Library content | Org-shared reports (`Visibility='shared'`) + direct shares + own reports, grouped; `kind:'sql'` hidden |
| Wizard output | Full round-trip: standard v1 definition; saveable; openable in Advanced pre-filled |
| Simple implementation | Thin parallel partial (new IIFE talking only to existing REST endpoints + `window.Reporting`) |
| Number card | Backend slice: zero-column metric definitions → real grand totals (`SELECT AGG(...)`, no GROUP BY) |
| AI grounding | Backend slice: Surface A learns metrics + grain (catalog + system prompt) |

## 1. Page shell & tabs

- Below the existing `.nx-page-head`, an `.nx-tabs` strip — **first consumer** of the unused
  design-system tab component (`static/css/nexora-ui.css:311-314`; active class `.is-active`,
  *not* the reporting toggles' `.active`). Proper `role="tablist"` semantics with a distinct
  `aria-label` (the page already has a `role="tablist"` mode toggle at `reporting.html:74`).
- Pane wrappers:
  - `#rpPaneSimple` — new include `templates/_reporting_simple.html`.
  - `#rpPaneAdvanced` — wraps the existing `main.reporting-main` **unmoved**. Every element id,
    class, and `data-testid` the builder IIFE and e2e suite use stays in the DOM (hidden is fine;
    `templates/js/_reporting_js.html` has ~50 unguarded `getElementById` bindings and three
    unconditional loads at parse — the markup must always be present wherever the partial is
    included).
  - The three modals (`#rpSqlAck`, `#rpShareModal`, `#rpScheduleModal`) stay global siblings,
    outside both panes.
- Tab resolution order: `?tab=` query param > `localStorage['nx.reporting.tab']` > `'simple'`.
  Switching persists to localStorage and updates the URL via `history.replaceState` — the app's
  established client-side deep-link convention (no `request.args` handling; nothing server-side
  changes in the `reporting()` view).
- Controller exposed as `window.ReportingTabs.show('simple'|'advanced')` so Simple's
  "Open in Advanced" actions can switch programmatically.
- Keyboard: Left/Right/Home/End within the tablist, `aria-selected` kept in sync.
- Entrance animation: Simple containers stay **out** of the `rp-anim` pre-hide layer
  (`reporting.css:444-453`); they use `.nx-rise` instead. The Advanced pane keeps its existing
  anim wiring; verify reveal still works when the pane starts hidden.

## 2. Simple pane — library

```
[ Simple ] [ Advanced ]
+-------------------------------------------------+
| [ + New report ]   [ Ask AI: ____________ Ask ] |
|                                                 |
| Library (shared with everyone)    [search.....] |
| +---------+ +---------+ +---------+             |
| | name    | | name    | | name    |             |
| | by Anna | | by Ben  | | by Tom  |             |
| | 2d ago  | | 5d ago  | | 1w ago  |             |
| +---------+ +---------+ +---------+             |
| My reports                                      |
| +---------+ +---------+                         |
| Shared with me                                  |
| +---------+                                     |
+-------------------------------------------------+
```

- One fetch of `GET /api/reporting/reports` (already returns `owned`, `visibility`, `canEdit`,
  `ownerName`, `kind` per row — no backend change). Client-side grouping:
  - **Library** — `visibility === 'shared'` (org-wide), any owner.
  - **My reports** — `owned === true`.
  - **Shared with me** — the remainder (direct `ReportShares` rows).
  - Rows with `kind === 'sql'` are filtered out of Simple entirely (viewers can't run them;
    `/api/reporting/run` doesn't execute SQL definitions). They remain fully usable in Advanced.
- Cards: name, owner, relative updated-time. Client-side name search box.
- Click → `GET /api/reporting/reports/<id>` → definition → **lazy** run (only on open; respects
  the 120/min run limit) → the shared result view (§4).
- Definitions with `metrics` render as cards; plain table definitions render the grid directly
  (plus Open in Advanced / Export actions). Either way the same result view shell.

## 3. Simple pane — wizard

Progressive disclosure, single column; each answered step reveals the next. Entry: the
"+ New report" card.

1. **Measure** — from `GET /api/reporting/metrics` (`{sourceId: [{code,label,aggregation,
   baseField,format}]}`, already permission-filtered). Grouped by source label when more than one
   source has metrics; picking a measure pins the source. Sources without metrics never appear —
   admins grow the wizard's reach by adding rows at `/reporting/metrics` (semantic registry),
   zero code change.
2. **Break down by** — from the pinned source's field catalog (`GET /api/reporting/sources`):
   - *Over time*: grainable date fields with a grain select (day/week/month/quarter/year, default
     **month** — same string values `query.py` resolves).
   - *By category*: string-typed filterable fields.
   - *None — just the total*: zero-dimension (enabled by backend slice A).
   - Optional collapsed **process picker** (docprocessing only), emitting the same
     `scope: {clients, processes}` serialisation as the Advanced picker (empty = all allowed;
     server clamps to grants).
3. **Time range** — presets: this month, last month, last 3 months, this year, last year, all
   time, custom (flatpickr range; already loaded on the page). Emits a `between` filter on the
   **raw** date field (the Spec-1 contract: filters always use the raw date, never the bucketed
   expression). Date field defaults to `import_date`, switchable to `export_date`. The step is
   skipped when the source exposes no date field.
4. **Result** — see §4. Definition assembled client-side:

```json
{
  "schemaVersion": 1, "source": "docprocessing", "visualization": "table",
  "title": "<auto: measure ± breakdown, user-editable>",
  "columns": [{"field": "import_date", "header": "Import date", "grain": "month"}],
  "metrics": [{"metric": "doc_count"}],
  "filters": [{"field": "import_date", "op": "between", "value": ["...", "..."]}],
  "sort": [{"field": "import_date", "dir": "asc"}],
  "scope": {"clients": [], "processes": []},
  "rowLimit": 5000
}
```

Invariants the wizard honors (validator-enforced): sort fields must be among selected columns;
grain only on grainable fields; metric codes from the source's registry.

## 4. Simple result view (shared by library, wizard, AI helper)

```
<- Back   "Documents per month"     [Save] [Open in Advanced] [Export]
+--------------+  +--------------------------+
| DOCUMENTS    |  |   chart (line for date,  |
|   12 345     |  |   bar for category)      |
+--------------+  +--------------------------+
[ Show table v ]
```

- **Two runs** for metric definitions: a zero-column clone (same metrics/filters/scope,
  `columns: []`) for the grand total, and the breakdown run for chart + table. Both via
  `POST /api/reporting/run`. The total is therefore **correct for every aggregation** —
  avg/count_distinct included — unlike any client-side sum over grouped rows.
- **Number card**: `stat_card()`-style `.nx-stat` markup (`templates/_ui.html:32`); value
  formatted per the metric's `format` hint.
- **Chart card**: Simple's **own** small Chart.js instance on a private canvas — *not*
  `ReportingViz.mountChart` (module-singleton `chartInstance` + hardcoded `rpChartType/X/Y` ids
  make concurrent mounts unsafe). Line for date breakdowns, bar for categories; ≤50 categories
  (same cap convention); destroyed on re-run and tab switch. Chart.js 4.5.1 is already on the
  page (pinned + SRI).
- **Show table** toggle: plain grid below the cards (existing `.reporting-table` styling).
- **Save**: inline name input (no `window.prompt`) → `POST /api/reporting/reports` — always a
  new row. Saved reports land in My reports and inherit share/schedule/Advanced editing for free.
- **Open in Advanced**: `window.Reporting.applyDefinition(def, name, owned && canEdit ? id : null)`
  then `ReportingTabs.show('advanced')`. Passing `id: null` for non-owned reports is
  load-bearing: `applyDefinition` does not reset ownership flags, and CanEdit shares mutate
  shared reports **in place** — Simple must make Advanced's Save default to create-a-copy.
- **Export**: `POST /api/reporting/export` (definition + format), button gated
  `has_permission('reporting.export')`.
- Friendly error states: 403 → "You don't have access to the data behind this report";
  400 (stale definition) → "This report is outdated — open it in Advanced to fix it";
  zero rows → empty state (`empty_state()` macro). A run failure never breaks the pane.

## 5. Simple pane — ask-AI helper

- Rendered `{% if ai_enabled %}` (`reporting.ai.use`), same flag the route already passes.
- One input → `POST /api/reporting/ai/build` (`{question}` → `{definition, explanation, valid,
  error}`; the accepted definition is guaranteed runnable — validated with the same validator as
  `/run`). On `valid:true` → the §4 result view. `chartHint {type,x,y}` respected when its
  fields exist; silently ignored otherwise.
- Check `res.data.valid`, not `res.ok` (the route returns 200 for invalid drafts).
- Degrades: 503 (AI unconfigured) → helper hides after first failure; 429 (daily cap) →
  message; `valid:false` → "try rephrasing" + the explanation text.

## 6. Backend slice A — zero-dimension metric definitions

- `nx_lib/reporting/schema.py`: `validate_report_definition` accepts `columns: []` **iff**
  `metrics` is non-empty (the ≥1-column error stays otherwise).
- `nx_lib/reporting/query.py` (docprocessing): no columns + metrics → `SELECT` of the resolved
  aggregates only, no `GROUP BY`, aggregating over the per-process UNION as today.
- `nx_lib/reporting/table_query.py` (generic provider): same zero-dim branch.
- `nx_lib/views/reporting.py` `_prepare_run`: `out_columns` already degrades to just the metric
  columns; verify, no change expected. `runner.py` passes through unchanged.
- Advanced and the AI surfaces inherit grand-total capability for free.

## 7. Backend slice B — Surface A grounding (metrics + grain)

- `nx_lib/reporting/ai_schema.py` `serialize_sources_catalog`: add per-source metric lines
  (code, label, aggregation) and mark grainable fields with the grain vocabulary.
- `nx_lib/reporting/ai.py` `_SYSTEM_DEF`: document optional `metrics: [{"metric": code}]` and
  per-column `"grain"`, with the rule "when metrics are present, columns become the GROUP BY".
- No validation change needed: `_validate_definition_for_user` already runs the full run
  validator (verify `coerce_definition` tolerates `metrics`/`grain` keys), and the front-end
  `applyDefinition` already round-trips both.
- Also partially addresses usability gap #3 ("AI unreliable" — thin grounding was a traced root
  cause). Audit stays `Surface='definition'`.

## 8. Permissions

No new permission codes. Simple is a presentation layer over `reporting.view`; per-source perms
(`reporting.source.*`) and row scope (`reporting.scope.process.*`) stay server-enforced in
`_prepare_run` exactly as today. Notable consequence (existing semantics, surfaced honestly in
the UI): a shared library report runs against the *viewer's* grants — different users can see
different numbers, or a friendly 403.

## 9. Files touched

| File | Change |
|---|---|
| `templates/reporting.html` | tab strip + two pane wrappers; include the new partials |
| `templates/_reporting_simple.html` | **new** — Simple pane markup |
| `templates/js/_reporting_simple_js.html` | **new** — tab controller + library + wizard + result view + AI helper (self-contained IIFE; talks only to REST + `window.Reporting` + `window.ReportingTabs`) |
| `static/css/reporting.css` | Simple styles, appended **after** the redesign block (order-dependent file) |
| `nx_lib/reporting/schema.py` | zero-dim relaxation |
| `nx_lib/reporting/query.py`, `table_query.py` | global-aggregate branch |
| `nx_lib/reporting/ai_schema.py`, `ai.py` | Surface-A grounding |
| `tests/unit/*`, `tests/integration/*`, `tests/e2e/*` | see §10 |
| `messages.pot`, `translations/*` | pybabel cycle |
| `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md` | docs |

## 10. Testing

- **Unit (pytest):** schema zero-dim acceptance/rejection matrix; both query builders' zero-dim
  SQL; Surface-A catalog serialization includes metrics + grain; draft-with-metrics+grain passes
  `_validate_definition_for_user`.
- **Integration:** `/api/reporting/run` zero-dim round trip (route-level).
- **e2e (Playwright):** existing reporting tests updated to open `/reporting?tab=advanced`
  (one-line navigation change per test, or a shared helper). New: tab default = Simple +
  stickiness via localStorage + `?tab=` override; library grouping (org-shared vs mine vs
  shared-with-me; SQL-kind hidden); wizard happy path where NEXORA_TEST data allows — otherwise
  the route-level integration tests carry the definition-assembly contract.
- Manual browser verify on INT per project convention (`nx -u -b --loginas:…`), screenshots to
  `var/screenshots/`.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Builder IIFE dies if Advanced DOM missing | Advanced markup always rendered, only hidden |
| Chart singleton/id collisions | Simple owns its own Chart instance; never calls `mountChart` |
| Save-overwrites-shared-template | `id: null` on Advanced handoff for non-owned reports |
| e2e tests assert builder testids on load | `?tab=advanced` deep link in tests |
| applyDefinition races `loadSources()` | Advanced handoff is user-initiated (post-load); guard awaits `window.Reporting` presence |
| Ad-hoc shares pollute the library | Accepted (decision); revisit with a template flag only if it hurts in practice |
| AI panel partial mutates page chrome (`.reporting-fields` etc.) | Those elements stay in the Advanced pane unmoved; partial's null-guards hold |
| `rp-anim` pre-hide could blank Simple | Simple containers excluded from the pre-hide selector list |

## 12. Spec-3 candidates (explicitly deferred)

Grain on the `table` provider; template/featured flag (+ curation UI); multi-report dashboard
cards; share/schedule from Simple; wizard support for metric `FilterJson` (reserved column,
unapplied today).
