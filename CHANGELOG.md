# Changelog

All notable changes to nexora are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work toward 2.5.63 (version bumped from 2.5.60; now single-sourced in `nx_lib/version.py`).

### Added
- Reporting: alert-only schedules — a schedule can carry a threshold condition
  (total >, ≥, <, ≤) and only mails when it trips; schedules can now be
  enabled/disabled from the modal (migration 0022).
- Reporting: truncated results now say so — both tabs show "Showing the first
  N rows" whenever the server row limit was hit.
- Reporting Simple: CSV export option beside Export (chart embedding stays
  Excel-only).
- Reporting Simple wizard: "This week" and "This quarter" time presets; the
  Back button steps back through the wizard instead of exiting and discarding
  picks.
- Reporting: "Show query" on Simple and Advanced results — reveals the executed SQL (pretty-printed server-side via sqlglot, syntax-highlighted, collapsed by default) and bind parameters; Copy copies the raw executed statement.
- Reporting: in-flight loading indicators — Simple and Advanced report runs show a pulsing status (the Advanced Run button locks while running), and all three Advanced Ask-AI surfaces show a thinking indicator with rotating status lines.
- Reporting Simple wizard: up to three breakdowns (at most one date); two-breakdown results chart as multi-series with a stacked-bar option.
- Reporting: XLSX exports gain a title block and embed the on-screen chart; Simple gets a chart-PNG download button.
- Reporting: scheduled report mails embed a server-rendered chart (matplotlib) inline and in the attached XLSX.
- **Reporting Simple wizard: chart-type switcher.** Bar/line/pie/doughnut toolbar
  in the result chart card; the chosen type persists in the saved definition and
  is restored on library open.
- **Reporting Simple wizard: "Adjust in wizard" for saved reports.** Any
  wizard-shaped definition — including saved library reports and simple AI-built
  results — can re-enter the wizard with all choices pre-selected (definition
  reverse-mapping; no schema change).
- **Reporting Simple results: chart-absence explanations.** When no chart can be
  drawn, the result now explains why (single total, too many date points, chart
  library unavailable). Category breakdowns >50 rows chart the top 50 with a note.
- **Reporting Simple: exit buttons.** Explicit ✕ buttons on both the wizard header
  and the result bar exit straight to the library.
- **`db-migrate.py --env STAGING`.** The migration runner now accepts `STAGING`
  alongside `INT`/`PROD` (applies without a confirm prompt, like INT) — used to
  bring the prod-copy staging DB up to date for feature testing.
- **Reporting Simple/Advanced tabs.** `/reporting` is now split into a **Simple**
  tab (the new default) and an **Advanced** tab (the full builder, unchanged).
  Simple is a presentation layer for report *viewers*: a **library** of reports
  grouped into *Library* (org-shared, `Visibility='shared'`), *My reports*, and
  *Shared with me* (sql-kind reports are hidden — they stay usable in Advanced);
  a **guided wizard** (measure from the metrics registry → break down by
  date-with-grain / category / nothing → time-range presets emitting a `between`
  filter on the raw date) assembling a standard v1 definition; and an optional
  **ask-AI** bar (Surface A) rendering valid drafts straight to cards. Results
  show as a grand-total **number card** (a zero-column clone run, so the total
  is correct for every aggregation) plus a **chart card** (Simple owns a private
  Chart.js instance) with a show-table toggle; Save always creates a new row;
  *Open in Advanced* pre-fills the builder (passing `id:null` for non-owned
  reports so Advanced's Save defaults to create-a-copy). Deep link
  `/reporting?tab=advanced`; the last-used tab is remembered per browser
  (`localStorage`). de/fr/it translated.
- **Reporting zero-dimension metric definitions (grand totals).** A definition
  with a non-empty `metrics` list may now have **zero columns** — both the
  docprocessing and the generic `table` query builders emit a global aggregate
  `SELECT AGG(...)` with no GROUP BY (count-only metric sets project a constant
  per union subquery). Powers Simple's number card; Advanced and the AI
  surfaces inherit it.
- **Reporting AI Surface-A metrics + grain grounding.** The "Build a report"
  catalog now marks **grainable** date fields and lists each source's canonical
  **metrics** (code, label, aggregation), the system prompt documents the
  `metrics`/`grain` contract (incl. zero-column grand totals), and the
  validation gate passes `metric_codes`/`grainable_fields` exactly like the run
  path — AI drafts using metrics or grains now validate instead of bouncing.
- **Reporting process-scope picker (clients / processes).** The builder's left
  panel gained a **Processes** multi-select dropdown (below **Source**,
  docprocessing only) listing the caller's allowed `<client>.<process>` grants
  grouped by client — tick a whole client or individual processes to narrow a
  report's row scope (default: all). The selection serialises into the
  definition's `scope` (fully-ticked clients → `scope.clients`, partial →
  `scope.processes`) and is saved/restored with the report. `_effective_scope`
  now **honors `scope.clients`** (previously a dead field): it narrows the
  caller's allowed set to *(client ∈ clients) ∪ (process ∈ processes)*, with the
  `reporting.scope.process.*` grant still the security boundary. Hidden for
  `table` sources (Generali / Octo), which carry no processes. The left-panel
  **field list now scopes to the selected process(es)** (mirroring the workitems
  field picker): a docprocessing field shows only when at least one selected
  process exposes it (union; each catalog field already carries its `processes`
  list, so this is client-side), and narrowing the scope **prunes any
  already-added column / filter / sort** whose field falls out of scope so a run
  can't break. de/fr/it translated.
- **Reporting date dimension (docprocessing).** Import & export dates are now
  first-class report fields (`import_date` / `export_date`), synthesized from
  `Statconfig` (CONVERT-vs-CAST aware, mirroring the dashboard). Date columns
  take an optional **grain** (`day/week/month/quarter/year`, default month) that
  the query builder resolves in both the row and aggregate/GROUP BY paths;
  filters on a date field always use the raw date. Enables date-range filtering
  and "documents per day/week/month" reporting. Security boundary unchanged
  (date expressions come only from `Statconfig`). de/fr/it translated.
- **Reporting workitem dimension + distinct workitem count (docprocessing).**
  A synthetic **`workitem_id`** field, mapped per process by the new
  `StatConfig.WorkitemColumn` (migration `0020`; underlying names vary —
  `WorkItem` / `WorkitemID` / `WID`). The query builder CASTs every mapping to
  `nvarchar(100)` so the cross-process UNION never mixes native column types;
  unmapped processes project NULL (and can be added later by setting
  `WorkitemColumn`, no code change). Ships with the registered metric
  **`workitem_count`** (`COUNT(DISTINCT workitem_id)`) — "how many workitems"
  where `doc_count` counts rows — which appears automatically in the Simple
  wizard's measures and the AI grounding. de/fr/it translated.
- **Generali PDQM mapping seed.** Added the `PDQMMapping` row
  `Adressverifikation` / `QSTAT 27` via migration
  `sql/_migrations/GeneraliDB/0002_insert_pdqmmapping_adressverifikation_qstat27.sql`
  (idempotent `IF NOT EXISTS` guard).
- **Reporting semantic layer (Slice 1 — canonical metrics).** Canonical
  **metrics** (named, blessed server-side aggregations) so the builder and the AI
  assistant produce the same numbers. A DB-backed registry
  (`dbo.ReportingMetrics`, migration `0017`) is curated at a new admin page
  `GET /reporting/metrics` with a CRUD API
  (`GET/POST/PUT/DELETE /api/reporting/admin/metrics[/<id>]`), both gated by the
  new permission `reporting.semantic.admin` (admins seeded). A report
  definition's optional `metrics` list switches the run into **aggregate mode**:
  the selected `columns` become the `GROUP BY` and each metric adds an
  `AGG(col) AS [code]` column, resolved server-side via the new pure
  `nx_lib/reporting/semantic.py` (`resolve_metrics` + `build_aggregate_sql`) and
  validated against the source's enabled metrics (`MetricResolveError` → HTTP
  400). Both query builders gained an aggregate branch reusing their existing
  whitelist + parameterized-value boundary (`table_query.py` direct; `query.py`
  wraps the docprocessing UNION). The builder gained a **Metrics well** (selected
  metrics turn the Columns into the grouping), a builder-facing
  `GET /api/reporting/metrics` (accessible metrics grouped by source), and the
  metric catalog is injected into the AI schema (`ai_schema.serialize_metrics_catalog`)
  so Surfaces A/C can reference metrics by code. Empty/absent `metrics` keeps the
  row-projection path unchanged. de/fr/it translated. (Per-metric locked
  `FilterJson` is stored but not yet applied — reserved for a later slice.)
- **Workitems table / line-item source highlighting.** The read-only "Show
  sources" overlay now extends from scalar index fields to **table / line-item
  extractions**. `api_get_media_info` opt-in-fetches table data
  (`get_extensions_urls_fields(..., with_tables=True)`, only on the viewer path
  so the scalar-only callers pay nothing) and returns a new `table_sources`
  array, parsed from the Octopus `Tables[].Rows[].Cells[]` structure by the pure
  helper `nx_lib/table_locations.py` (same `IndexField.Location` rect shape,
  reusing `field_locations.py`'s rect/confidence/page-offset helpers). The field
  panel grows a compact **line-item grid** below the scalar fields whose located
  cells are click-to-locate; on the page each cell renders a **dashed** highlight
  box (distinct from the solid scalar-field boxes, confidence colour preserved)
  in both the lightbox and thumbnails, under the same single "Show sources"
  toggle. Reuses `workitems.details.view.images` + `.fields` (**no new
  permission, no migration**); `table_sources` is permission-suppressed
  identically to `field_sources`. Extracted document content is HTML-escaped
  before rendering (the same hardening was applied to the pre-existing scalar
  rows). See `docs/superpowers/specs/2026-06-09-workitem-table-highlighting-design.md`.
- **Two new workitems source-highlight permissions** (migration `0018`,
  seeded to admin profiles). `workitems.details.view.confidence` gates the
  extraction **confidence %** (the per-field/cell chips + the confidence colour
  on the boxes); `workitems.details.view.source_location` gates seeing **where**
  each value was found on the page (the highlight boxes + click-to-locate; only
  effective together with `workitems.details.view.images`, since boxes draw over
  the page image). `api_get_media_info` strips `confidence` / `locations` from
  `field_sources` + `table_sources` per permission and returns a
  `source_location_visible` flag so the viewer hides the "no source location"
  badge when the perm is absent (a permission state, not missing data). Both
  appear in the admin access-control grant UI automatically (it reads
  `dbo.Permission`).
- **Reporting AI — humanized process ids in catalog grounding.** The AI catalog
  now shows each process id with a derived human label in parentheses
  (e.g. `privera.03_Invoice_New ("privera Invoice New")`), and the prompts
  instruct the model to match natural-language process names against both the raw
  id and this label. Process matching is now case-insensitive and includes all
  matches rather than guessing one.
- **Reporting Simple tab — AI transparency line.** After an Ask-AI request returns a
  valid definition, the result view now shows a one-line summary below the report
  title: the AI's own explanation plus the filters and processes it chose. Wrong
  guesses (bad date range, wrong process) are immediately visible instead of
  silently rendering an empty table. Rendered via `textContent` (XSS-safe).
  de/fr/it translated.
- **`.claudeignore` + enforcing PreToolUse hook.** A repo-root `.claudeignore`
  lists which paths AI coding tools should skip (secrets, Python bytecode,
  virtualenvs/vendored deps, build artifacts, tool/index caches, `uv.lock`,
  compiled message catalogs, and `var/` runtime data). Because current Claude
  Code does not natively read `.claudeignore`, a stdlib PreToolUse hook
  (`.claude/hooks/claudeignore_guard.py`, wired in
  `.claude/settings.local.json` for `Read|Grep|Glob`) parses it and denies any
  matching read/search (gitignore syntax incl. `!` negation). The generated
  `sql/` per-object dumps and `messages.pot` are intentionally left readable
  (documented but not enforced) so schema/i18n search still works.
  `.claudeignore` is added to the `deploy.yml` `/XF` exclude list (dev-only
  file); `.claude/` is already excluded via `/XD`.
- **Reporting AI assistant (Phase 3 — agentic loop + deterministic stats, spine):**
  a Tier-2 **agentic tool-loop** (`nx_lib/reporting/ai.py: ask_agentic`) that drives
  *model → tool → model* with self-repair and a hard turn cap, over a provider-neutral
  tool layer (`nx_lib/reporting/ai_tools.py`) wrapping the existing rails, plus a
  pure-stdlib **deterministic statistics engine** (`nx_lib/reporting/stats.py`:
  describe / group_by / percentiles / value_counts / correlation / top_n — no
  pandas/scipy). New route `POST /api/reporting/ai/agent` (Surface C) is a
  self-repairing **drafter** gated by `reporting.ai.use`: it binds only data-free
  tools to the model (`build_definition` always, `validate_sql` with
  `reporting.ai.sql`), stays **schema-only** (no result rows reach the model), audits
  `Surface='agent'`, honours `AI_DAILY_LIMIT`, and returns a validated definition/SQL
  for one-click Open-in-builder / Insert-SQL.
  See `docs/superpowers/plans/2026-06-03-reporting-ai-phase3.md`.
- **Reporting AI assistant (Phase 3e — explain the data).** New opt-in permission
  `reporting.ai.explain_data` (migration `0015`; admins seeded) lets the agentic loop
  bind the data-returning tools `run_sql` and `compute_stats` so the model can run
  validated read-only SELECTs and **narrate the actual result numbers** (exact
  aggregates via the deterministic stats engine). This is a deliberate **data-egress**
  grant — result rows reach the model — so it is gated separately from
  `reporting.ai.use` / `reporting.ai.sql` and is only effective together with
  `reporting.sql.run`. Without it the agent stays **schema-only** (no result rows ever
  reach the model), the default posture. Audited `Surface='agent'` with an
  `explainData` flag; the route also returns `explainData` so the UI can surface that
  the answer is grounded in fetched data.
- **Workitems — source highlighting.** A "Show sources" toggle on the document viewer
  overlays where each extracted index-field value was found on the page (read-only).
  Coordinates come from the Octopus document service (`IndexField.Location`), captured
  in `nx_lib/field_locations.py` and returned by `api_get_media_info` as `field_sources`;
  the browser normalizes the pixel rects against each page image's
  `naturalWidth`/`naturalHeight` and draws boxes in the lightbox and on thumbnails
  (thumbnails switch to `object-contain` so boxes map correctly). Field values with a
  location are click-to-locate (jump + pulse); values without one show a "no source
  location" badge. Reuses `workitems.details.view.images` + `.fields` — no new
  permission, no migration. CSS isolated in `static/css/source-highlight.css`.
- **Workitems — source-highlight confidence visualization.** When the Octopus
  document service reports a per-field extraction `Confidence`, `field_sources`
  now carries an optional normalized `confidence` (0–1; `nx_lib/field_locations.py`
  handles 0–1 and 0–100 scales, clamps, drops negatives), and the "Show sources"
  overlay colours each box + adds a per-field confidence chip — green ≥ 90 %,
  amber ≥ 70 %, red < 70 % — while fields without a reported confidence keep the
  neutral "located" orange. Read-only over existing data; no new permission.
- **Reporting AI assistant (Phase 2 — Build a report):** a "Build a report" sub-mode
  in the Ask-AI panel turns a natural-language question into a v1 report definition
  that auto-fills the builder wells (whitelist-safe; row-scoping preserved; **no SQL
  permission required** — only `reporting.ai.use`). Route `POST /api/reporting/ai/build`
  self-validates the draft through `validate_report_definition` with one self-repair
  retry, and audits to `dbo.ReportingAiAudit` (`Surface='definition'`). An optional AI
  "Make a chart" suggestion (`chartHint`) one-clicks into the existing chart view. No new
  permission or migration.
- **Reporting AI assistant — per-user/day cost cap.** New optional `AI_DAILY_LIMIT`
  env var caps how many AI asks a user can make per UTC day. When the cap is hit,
  `POST /api/reporting/ai/ask` returns **429** *before* any provider call (so a
  throttled ask costs no tokens) and records the throttle in `dbo.ReportingAiAudit`
  with `Status='blocked'`. `0` (the default) leaves the assistant unlimited. The
  existing 10/min `flask_limiter` cap is unchanged.
- **Reporting RO-login provisioning script.** `scripts/provision-reporting-ro-logins.sql`
  — an idempotent, SQLCMD-parameterised one-shot that creates the two
  `db_datareader`-only SQL logins (`DB_REPORTING_RO_*`, `DB_REPORTING_OCTO_RO_*`) the
  SQL sandbox, scheduled reports, and the AI assistant's live schema grounding need.
  Re-running with a changed password **rotates** it (`ALTER LOGIN` on the existing
  login), so the server always matches the env files; run it on each SQL server the
  env points at (INT/PROD `DB_SERVER_PRD` may differ).
- **Reporting AI assistant (Phase 1):** an "Ask AI" mode that turns a natural-language
  question into read-only T-SQL placed in the SQL editor (no auto-run). Server-side,
  provider-agnostic (`AI_PROVIDER` = `anthropic` | `azure` | `none`); schema-only egress
  (the model never receives result rows); every interaction self-validated through the
  sqlglot gate and audited to `dbo.ReportingAiAudit`. New perms `reporting.ai.use` /
  `reporting.ai.sql`; route `POST /api/reporting/ai/ask`. Disabled until a provider key
  is configured.
- Reporting — **motion / micro-interactions.** Added a purely additive animation
  layer (`templates/js/_reporting_anim_js.html`) built on **Motion**
  ([motion.dev](https://motion.dev), pinned `motion@12.40.0` from jsdelivr with
  Subresource Integrity): a staggered three-column entrance, result rows that
  stream in after **Run**, chart/pivot views that fade in on switch, spring-in
  modals (SQL ack / Share / Schedule), and hover/press feedback on buttons and
  toggles. It observes the existing DOM only — no reporting logic changed — and
  fully respects `prefers-reduced-motion` (and degrades to a static, fully
  functional page if the CDN script is blocked).
- Reporting — **scheduled & emailed reports.** A saved report can be run on a
  recurring schedule (daily / weekly / monthly at a UTC time) and emailed as
  xlsx or csv to recipients. New `dbo.ReportSchedules` table (migration `0012`),
  owner-only schedule endpoints, and a **Schedule** dialog; gated by the new
  grantable `reporting.schedule` permission (admins seeded). Delivery is done by
  `ops/run_scheduled_reports.py` (driven by Windows Task Scheduler), which runs
  each due report **as its owner** via a session-independent runner
  (`nx_lib/reporting/runner.py`) and sends it through Microsoft Graph
  (`nx_lib/mail.py`). See `docs/howto/reporting.md`.
- Reporting — **Generali & Workitems curated sources.** Two ready-to-use curated
  sources registered through the new `table` provider (migration `0011`):
  **Generali — PDQM Report** (`dbo.PDQMReport`, engine `generali`) and
  **Workitems (Octopus)** (`dbo.t_Documents`, engine `octopus`), each gated by
  its own grantable permission (`reporting.source.generali.pdqm`,
  `reporting.source.workitems`; admins seeded). The exposed columns came from the
  live INT schema and are admin-tunable via `/reporting/sources`.
- Reporting — **DB-backed source registry + admin page.** The source list is no
  longer purely code-defined: `dbo.ReportingSources` rows (migration `0010`)
  augment or override the built-in sources — relabel, enable/disable, reorder,
  re-permission, or register new ones — managed at **`/reporting/sources`** (new
  `reporting.admin.sources` permission, admins seeded). Curated sources bind to a
  **provider**: `docprocessing` (the built-in Statconfig source) or a new generic
  **`table`** provider (`nx_lib/reporting/table_query.py`) that runs a safe,
  whitelist-built parameterized `SELECT` over any registered object/engine
  (Nexora / Statistics / Generali / Octopus) — so new curated sources can be
  registered from the UI with no code.
- Reporting — **cross-user sharing & a shared report library.** Saved reports
  are no longer owner-only. Each report has a **Visibility** (`private`, or
  `shared` = visible read-only to everyone who can use Reporting) plus optional
  explicit **per-user grants** that can be read-only or read-write. The
  Saved-reports dropdown groups **My reports** and **Shared with me** (tagging
  the owner), a per-report **Share** dialog manages visibility and people, and
  an in-place **Save** respects edit rights (recipients without edit rights fork
  a copy via Save as). Migration `0009` adds `dbo.Reports.Visibility` and a
  `dbo.ReportShares` table; new endpoints under
  `/api/reporting/reports/<id>/shares` (owner-only management).
- Reporting — **builder polish + richer export.**
  - **Save vs Save as:** with a report loaded, **Save** now overwrites it in
    place (PUT); the new **Save as** button always forks a fresh copy. Previously
    every Save created a new report.
  - **CSV export:** an Excel/CSV format selector next to **Export**; CSV is
    UTF-8 (BOM-prefixed for Excel) with the same formula-injection guard as the
    xlsx path.
  - **Export what you see:** Export is view-aware — the **Chart** view exports a
    PNG image, the **Pivot** view exports the computed matrix (xlsx/csv via the
    new `/api/reporting/export/grid` endpoint, gated by `reporting.export`), and
    the **Grid** view exports the raw rows as before.
  - **Nested pivot column headers:** multi-field Columns now render a proper
    multi-level `<thead>` (grouped/`colspan`-ed per dimension level) instead of a
    single composite line; rows/columns are sorted for stable, grouped output.
- Reporting — **chart & pivot result views.** A Grid / Chart / Pivot toggle
  appears after a run and re-visualizes the current result set (curated *or*
  SQL) in place: Chart.js bar/line/pie/doughnut charts, and a vanilla
  drag-and-drop multi-dimension **pivot/matrix** (drag fields into
  Rows/Columns/Values, per-measure aggregation sum/avg/count/min/max, with row
  and grand totals).
- Reporting — **saved-report load UI.** A "Saved reports" dropdown on the
  builder toolbar with Load / Rename / Delete (the list/get/update/delete
  endpoints already existed); Load restores a curated definition into the
  builder or a SQL definition into the SQL editor.
- Reporting — **Octopus as a 2nd live-SQL target.** The SQL sandbox can target
  the Octopus runtime DB alongside Statistics, gated by the new grantable
  `reporting.sql.target.octopus` permission (migration `0008`, admins seeded)
  and its own dedicated `db_datareader`-only login
  (`DB_REPORTING_OCTO_RO_USER` / `DB_REPORTING_OCTO_RO_PWD`; until set the
  Octopus target degrades to 503).
- Reporting: live read-only **SQL sandbox** (Statistics) — run a single SELECT,
  export to Excel, and save SQL reports. Gated by the new grantable
  `reporting.sql.run` permission plus a one-time acknowledgment, hardened by an
  sqlglot AST gate, a dedicated `db_datareader`-only login, a 50k row cap,
  statement timeout, and per-run audit (`ReportingSqlAudit`).
- **Reporting page** (`/reporting`): internal self-service report builder (PowerBI replacement, phase 1). Curated **Document Processing** source, table visualization with field picker, filters, combine clients/processes, custom column headers, save/load reports, and Excel export. New `reporting.*` permissions; new `Reports` table; new `openpyxl` dependency.
- **`nx --doctor`** preflight health check (`nx_lib/cli_doctor.py`): verifies the Python interpreter, installed packages vs `requirements.txt`, `.env` / `env/<ENV>.env` keys, writable `var/` dirs and translation compile state, all four SQL Server engines + the ODBC driver, pending schema migrations, schema drift vs INT, on-PATH tooling, git hooks, port 8000, and the external services (Microsoft Graph / Octopus / Bexio). `--fast` skips drift + external calls; `--fix` runs safe auto-repairs. Exit code 0 on no failures, 1 otherwise — usable as a preflight gate.
- **`nx -md` / `--maindir`** to cd into the repo (handled by the `$PROFILE` wrapper function), plus a matching `doctor` command in the interactive REPL.
- **`docs/howto/nx.md`** — full nx CLI reference (one-shot flags, interactive REPL, `doctor`).
- **`docs/howto/db-migrations.md`** — detailed database-migration how-to: the two-script model (`db-migrate.py` / `sync-from-db.py`), authoring workflow, `db-migrate.py` flag reference, the `dbo.SchemaMigrations` ledger, recipes, and troubleshooting.
- App logger output captured to `var/logs/system/app.log`.
- **Automated test suite build-out.** pytest unit coverage across the app factory, Flask extensions, request-lifecycle hooks, logging, DB helpers (URL builder + `ping_db` / `ping_dbs_parallel`), security/permissions, i18n locale fallback, maintenance banner/lockout, `PrefixMiddleware`, notifications, the Octopus client, process helpers, and the nx CLI (REPL + doctor). Route-level tests covering every view module (auth, core, dashboard, profile, admin, workitems, invoices, notifications, chat). Playwright E2E browser tests across login / 2FA, dashboard, workitems, invoices, chat, profile, admin, and misc pages, with a cross-browser login smoke. pytest-cov wired in with per-module ratcheting coverage thresholds; test layout, fixtures, and run commands documented under `docs/`.
- Reporting date filters support relative-date tokens (`{"token": "last_month"}`, incl. `last_n_days`) that resolve at run time, so saved and scheduled reports never go stale. The Simple wizard presets and a new Advanced preset dropdown emit tokens; the AI drafts them for relative questions; results show the concrete resolved range.
- **Reporting Simple tab: conversational AI refine** — after an AI-built result renders, a **Refine** bar appears below the explanation. Type a follow-up question (e.g. "break it down by month instead") and click **Refine** to iterate without starting over; the AI receives the original question and definition as context (`priorQuestion` / `priorDefinition`) so it applies targeted changes rather than rebuilding from scratch (`rsRefineBar`).
- **Reporting Simple tab: thinking indicator** — while the AI is working, the result area shows the current step in plain language ("Asking the AI…" → "Drafting your report…" → "Checking the result…") so users know progress without a spinner.
- **Reporting Simple tab: editable filter/process chips** — AI-built results display every filter the AI chose and which processes are in scope as interactive chips below the explanation. Click a chip to edit the value inline; click × to remove a filter; click the process chip to open a checklist and narrow scope. Each change re-runs the report immediately without an AI call.
- Reporting Simple: every result is now tweakable — the AI refine bar and the editable filter/process chips show on wizard-built and library-opened reports too (refine works without a prior AI question), and wizard-built results get an **"Adjust in wizard"** button that re-opens the walkthrough with the previous choices pre-selected.
- Reporting: `this_quarter` / `last_quarter` relative-date tokens — in the AI prompts, the Simple wizard ("Last quarter" preset), the Advanced filter presets, and the chip editor.
- Git → Confluence docs sync: `scripts/confluence-publish.py` publishes `docs/howto/*`, `docs/design/*`, `README.md`, `CONTRIBUTING.md` and `CHANGELOG.md` to the Confluence space as a read-only mirror (md2conf engine, `git-managed` labels, orphan archiving); triggered by `.github/workflows/confluence-docs.yml` on push to `main`. Runbook: `docs/howto/confluence-sync.md`.

### Fixed
- Reporting AI: prompts now require a date `grain` for per-month/week/quarter/year questions (drafts no longer bucket by raw day while claiming "monthly").
- Reporting AI: "how many distinct X per Y" no longer groups by the counted field (prompt rule + a gate guard that drops the shadowing column).
- Reporting AI agent: the grounding and the `run_sql` error now name the valid SQL targets, so the agent can self-repair instead of dying at the turn cap.
- Reporting AI: sources without registered metrics are marked "cannot aggregate" in the grounding; failure messages surface the gate error instead of the model's explanation.
- Reporting Simple: two-breakdown results now chart correctly — the pre-pivot >50-row guard was firing on the (dim1 × dim2) cross-product (e.g. 12 months × 8 sources = 96 raw rows) and wrongly reporting "too many data points", even though the pivot collapses to far fewer x-axis points. The guard is now scoped to single-dimension charts; two-dim charts use the existing post-pivot x-axis cap and 12-series cap (matching the server renderer).

- **Scheduled reports now support metric definitions.** The scheduled-report
  runner (`nx_lib/reporting/runner.py`) validated saved definitions **without
  the source's metric codes** and never resolved `metrics` into the aggregate
  query — any scheduled report carrying a metric (e.g. one saved from the
  Simple wizard) failed with *unknown metric* since semantic Slice 1. The
  runner now mirrors the interactive run path for both providers
  (docprocessing + `table`): it passes `metric_codes` to validation, resolves
  the metrics, builds the aggregate query, and appends the metric columns to
  the exported sheet.
- **Reporting AI — table-source drafts no longer bounce on labels/missing fields.**
  Small models (e.g. gpt-4o-mini) reliably emitted *near-valid* report definitions
  for curated **table** sources — using a column's human **label** ("Date") where
  the schema wants its **key** (`ForDate`), or omitting `schemaVersion`/`title` — so
  Surface A ("Build a report") and the Surface C agent's `build_definition` tool
  rejected them and the agent often looped to `max_turns` without an artifact. A new
  whitelist-safe repair (`schema.coerce_definition`, run inside the shared
  `_validate_definition_for_user` gate) now resolves a label back to its catalog key
  (columns, filters, sort, chart axes), backfills the column header with the label,
  and fills `schemaVersion`/`visualization`/a synthesized `title`/a default-or-clamped
  `rowLimit` — only ever swapping a label that maps to exactly one field, and a no-op
  for already-valid drafts. The human builder path (`/run`) is untouched.
- **Workitems "Show sources" — boxes mispositioned in the lightbox.** The
  full-page overlay measured the modal image with `getBoundingClientRect()`,
  which returns the *visual* (post-`transform`) rectangle. Because the overlay
  rendered on the image's `load` event — fired while the lightbox `zoom`
  animation (`scale(0.5) → 1`) was still mid-flight — the boxes were pinned to a
  shrunken, centre-pulled frame and never re-measured once the zoom settled, so
  they appeared stranded in blank space and "jumped" to a different place when
  the toggle was flipped off/on. The overlay (`#srcHlLayer`) is now
  `position:absolute` inside `#imageModal` and sized from the image's
  transform-independent **layout box** (`offsetLeft/Top/Width/Height`), so boxes
  map to the displayed page on first open and stay put across hide/show. Lightbox
  boxes also get a subtle white halo + drop shadow so they read clearly on white
  paper and over dark text/logos (confidence colour unchanged).
- **Workitems "Show sources" — boxes shown out of register on lightbox open.**
  A residual of the fix above: with the image cached, the overlay rendered on the
  very next frame after open, *during* the `.modal-content` open-zoom animation
  (`scale(0.5) → 1`). Because `#srcHlLayer` is a **sibling** of the image it does
  not inherit that transform, so the boxes — drawn at the page's final layout
  coordinates — floated off the still-scaling page ("already visible when you open
  it, locations wrong") and only snapped into place on a manual hide/show that
  happened to re-render against the settled image. The overlay's first render now
  waits until the page is geometrically settled — the image bitmap is decoded
  **and** every running animation on it has `finished` — via a new
  `drawOverlayWhenStable()` (reopen / prev-next, with no animation running, render
  immediately). A `ResizeObserver` on the modal image re-renders the boxes on any
  later box-size change (values-panel reflow, late decode, viewport resize),
  keeping them locked to the page without a manual toggle.
- **Reporting AI (Build a report) — polish.** Four follow-ups to Phase 2:
  (1) the curated-source catalog shown to the model now lists each field as
  `key "Human Label":type`, and the prompt instructs the model to emit the exact
  key (the label only aids field selection / column headers) — so docprocessing
  "Build a report" no longer drafts label-named fields the validator rejects;
  (2) the Build-mode definition summary in `_reporting_ai_js.html` (`"source"`,
  `"columns"`, `"filter(s)"`, `"sorted"`, fallback title, and the error strings)
  is now translated (de/fr/it) instead of hard-coded English;
  (3) a provider **misconfiguration** on `POST /api/reporting/ai/{ask,build}` now
  leaves an audit trace (`dbo.ReportingAiAudit` `Status='misconfig'`) instead of a
  silent 503 — `misconfig` is excluded from the `AI_DAILY_LIMIT` count so a broken
  provider never burns a user's daily quota;
  (4) the `_audit_ai` log line reports the actual `surface` instead of a hard-coded
  `reporting.ai.ask` (the DB `Surface` column was already correct).
- **Reporting — 500 on SQL/curated results containing binary or time cells.**
  `/api/reporting/sql/run` and `/api/reporting/run` returned raw pyodbc values to
  `jsonify`; Flask's default JSON encoder cannot serialize `bytes`/`bytearray`/
  `memoryview` (varbinary, `rowversion`/`timestamp`, image) or `datetime.time`,
  so any query selecting such a column 500'd with "Object of type … is not JSON
  serializable". Result cells are now coerced to JSON-safe values at the response
  boundary (binary → `0x…` hex, time → ISO string), preserving the types Flask
  already handles (date/datetime/Decimal/UUID).
- **i18n — app-wide Python messages now translated.** `babel.cfg` extracted
  Python strings only from root-level `*.py` (`[python: *.py]`), so every
  `_()`/`gettext()` route/flash message under `nx_lib/**` fell back to English
  for de/fr/it. Extraction is now recursive over `nx_lib/**.py`; the ~150
  newly-surfaced messages (auth, admin, dashboard, workitems, invoices,
  notifications, profile, reporting, …) are translated to de/fr/it. The
  `test_translations.py` gate enforces full coverage going forward.
- **Reporting — `status` synthetic field removed from catalog:** `fetch_docprocessing_catalog` was injecting `status` as always-available alongside `processname`, but `SearchConfig` has no `col_status` column and the query builder cannot synthesize it. Selecting or filtering on `status` produced all-NULL columns or a `QueryBuildError`. Now only `processname` (fully supported by the builder) is injected; `status` will be offered once a real column backs it.
- **Reporting — empty-cols guard in `_load_field_col_maps`:** added early-return when `SearchConfig` exposes no `col_*` columns, preventing malformed SQL being emitted.
- **Reporting — flatpickr wired for date filter inputs:** `templates/reporting.html` loaded the flatpickr CSS/JS but `_reporting_js.html` never used it. Date/datetime-typed filter fields now initialize a flatpickr calendar picker; the field dropdown re-renders the row (resetting the value input) when changed so the picker activates immediately.
- **2FA:** accept adjacent TOTP windows on verify, tolerating small client/server clock skew.
- **generali-import:** store the full CSV filename in the import log.
- **pre-commit:** exclude `sql/` from the `mixed-line-ending` hook (it already excluded `end-of-file-fixer` / `trailing-whitespace`). The auto-generated dumps are CRLF from mssql-scripter and LF-normalized by `.gitattributes`, so the fixer perpetually re-flagged them on Windows, blocking commits of any regenerated dump.
- **db-migrate — non-ASCII corruption via sqlcmd codepage.** `scripts/db-migrate.py` ran migrations through `sqlcmd -i <file>` without a UTF-8 input codepage, so sqlcmd read UTF-8 migration files in the host OEM/ANSI codepage and silently corrupted any non-ASCII text on INSERT (German/French strings, dashes, …). This is how migration `0011` stored the mojibake source label "Generali â€" PDQM Report". The runner now passes `-f 65001` (UTF-8 in/out) and decodes captured output as UTF-8; migration `0016_fix_generali_pdqm_label_encoding.sql` repairs the already-stored label (codepage-safe via `NCHAR(0x2014)`).
- **Reporting AI (agent, explain-data) — run_sql against builder-only sources.** Curated `table`-provider sources (e.g. Generali PDQM, which lives on GeneraliDB) are not reachable by `run_sql` (it only targets the statistics/octopus RO engines), but the explain-data agent bound `run_sql` unconditionally and drafted `SELECT … FROM <source>` against a run_sql target, looping on an unrecoverable 208 "invalid object name". The agent route is now **source-aware**: the client sends the active builder source and `POST /api/reporting/ai/agent` binds the data tools (`run_sql`/`compute_stats`) **only when that source is run_sql-able**, so a builder-only source confines the model to `build_definition` (and `explainData` is reported `false`). The schema grounding (`nx_lib/reporting/ai_schema.py`) also labels such sources **builder-only — answer with `build_definition`, NOT queryable with `run_sql`**, and the explain suffix spells out that `run_sql` only hits the named SQL targets.
- **Footer — stale hard-coded version.** `templates/_nexora_version.html` hard-coded `nexora 2.5.60`, a third copy of the version that silently drifted from `pyproject.toml`. The version is now single-sourced in `nx_lib/version.py`, injected app-wide via a `nexora_version` context processor, and consumed by both the footer and the dev CLI; `tests/unit/test_version.py` enforces it stays in sync with `pyproject.toml`.

- **Reporting AI — correct dates for "last month", "this year", etc.** The AI
  definition drafter (Surface A) and the agentic loop (Surface C) had no concept of
  the current date; gpt-4o-mini fell back to training-data dates and turned "last
  month" into a range from 2023. Both surfaces now receive today's date in their
  prompts and grounding and are instructed to resolve all relative time expressions
  against it.
- **Reporting AI — "different docsources" returned duplicate rows.** A columns-only
  definition (no `metrics`) compiles to a plain projection with no GROUP BY, so
  asking for the distinct values of a field produced one row per document, not one
  per value. The prompts now teach both surfaces the correct pattern: put the target
  field in `columns` and add a count metric, which makes the columns GROUP BY
  dimensions so each value appears once.
### Changed
- **Reporting Simple wizard: curated breakdown dimensions.** For the Document
  Processing source, business dimensions (Document Source, Document Type,
  Forwarding, Owner no., Property No., Registered, Tenancy no.) are listed first;
  technical noise (process name, Bank PK, creditor no., barcode, document date,
  workitem id) is hidden. Other sources are unaffected.
- **Reporting Simple wizard: prominent process-scope control.** "Limit to specific
  processes" is now a bordered card-row with a live selection badge.
- **Reporting Simple: Back navigation.** Back on a wizard-shaped result returns to
  the wizard adjustment instead of the library.
- **Reporting Advanced: Save as / Rename use an in-page dialog.** The browser's
  `window.prompt` is replaced by a `.reporting-modal` name dialog — now drivable
  by automated tests.
- Reporting: `workitem_count` metric disabled (migration `0021`) — verified on PROD that the Statistics tables hold one row per workitem, so it always equaled `doc_count`. `workitem_id` remains available as a column/filter; re-enable the metric row if a multi-row-per-workitem source ever appears.
- **Admin pages migrated to nexora-ui design system.** All 7 admin pages
  (Overview, Organizations, Sessions, System Logs, Maintenance Banners, User
  Detail, Access Control) and their JS partials now use the app-wide `--nx-*`
  tokens and `.nx-*` component classes (same system as Workitems, Dashboard,
  Invoices, Chat, Generali). `admin-tokens.css` replaced by `admin.css` (admin-
  specific components only — `sev-pill`, `ml-toggle`, `health-card`,
  `permission-row` hover — all on `--nx-*` tokens). Dark-mode fixes applied to
  the permission drawer, user-detail confirm-delete modal, and access-control
  modals (`bg-white` → `var(--nx-card)`). Tab chrome (`perm-tabs`,
  `acl-tabs`) replaced by `nx-tabs`/`nx-tab` from `nexora-ui.css`.
- **Generali import scripts: `.env` instead of `env.json`, split into `remote/` +
  `local/`.** `scripts/generali-import/` now loads secrets from a `.env` file via a
  `load_from_dot_env` helper (process env vars, `$env:*`) instead of
  `Get-Content env.json | ConvertFrom-Json`. The two scripts were duplicated into
  `remote/` (the unattended copies the Task Scheduler runs on prdimpexp01,
  `isLocal` → `$false`) and `local/` (hand-run backup copies, `isLocal` → `$true`
  for confirmation prompts + progress) — identical otherwise: same
  `\\prdimpexp01\d$\sydoc\scripts\generali` paths, same `.env`, same SQL servers and
  mailbox. Replaces the fragile `(Get-Location).Path -like "*bes*"` local-detection.
  Added `.env.example` + a `README.md`; `env.json` removed. See
  `scripts/generali-import/README.md`.
- **Reporting page UI redesign.** The reporting builder, which had only received
  a token re-colour (the `nexora-ui` harmonization left layout/structure alone),
  was restructured for clarity. The toolbar is regrouped: the mode switch
  (Table / SQL / Ask AI) and the result-view + AI sub-mode switches are now proper
  **segmented controls** (they previously shrank and wrapped into a broken vertical
  stack); the report title reads as an editable document title; saved-report links
  are grouped; and the action cluster pins right with a single gradient-primary
  **Run** (Save / Save as / Export are now secondary, instead of every button
  looking primary). The empty results area gained a branded `.nx-empty` empty state,
  the metric/filter/sort wells became a divided stack with dashed "+ Add" ghost
  buttons, the field list shows an add affordance on hover, and the data table
  adopted the calm GitHub-style header/divider treatment. **Fixed** a pre-existing
  layout bug where SQL and Ask-AI modes (which hide both sidebars) collapsed the
  results column into the grid's narrow 260px first track — those modes now span
  full width via a `.reporting-main--single` class toggled by the mode switch.
  Pure CSS + structural grouping; every `id` / `data-testid` / JS hook preserved.
  Also corrected the SQL-target display label "Live SQL — Octopus" →
  "Live SQL — Octo" (`nx_lib/reporting/sources.py`; the `sql_octopus` id and
  `reporting.sql.target.octopus` permission are unchanged). de/fr/it translated.
- **Workitems "Show sources" is now a full-page split review.** Opening the
  source view (clicking a page or a value's locate action) shows the whole
  document page with its highlight boxes on the **left** and the extracted
  values on the **right** — the full scalar field list (label + value +
  confidence chip + "no source location" badge) plus the line-item grid, all
  click-to-locate (clicking a value navigates the page, pulses its box in
  place, and switches the boxes on — toggle flips to "Hide sources").
  Replaces the centred image-only lightbox. The values markup is shared
  with the inline Document Details panel via one builder so they never drift,
  and the right panel hides itself for documents with no extracted values
  (plain media viewing stays full-width). New string `Extracted values`
  (de/fr/it).
- **App-wide UI redesign — the `nexora-ui` design system.** A shared
  `static/css/nexora-ui.css` (global `--nx-*` design tokens + `.nx-*` components:
  cards, buttons, inputs, filter bars, tables, GitHub-style status labels, KPI
  stat cards, empty states, dark mode) plus a `templates/_ui.html` Jinja macro
  library, loaded globally from `_header.html`. The business pages (Workitems,
  Dashboard, Invoices, Chat) and all eight Generali pages (dashboard, documents,
  reporting, additional-services, base-services, project-management, pdqm,
  import-status) were migrated off ad-hoc Tailwind utilities onto the system —
  GitHub-structured (one indigo accent, hairline keylines, calm dense tables,
  tabular-mono identifiers) with a restrained indigo→violet brand-gradient
  signature (page-title icon chips, primary CTAs, the active-nav rail, count
  pills, own-message chat bubbles, empty-state orbs). Admin/Profile already used
  the precursor token system and were aligned (gradient primary button + nav
  rail). Behaviour, routes, ids,
  `data-testid`s and form fields are unchanged — presentational only. Fixed a
  pre-existing duplicate nested `<main>` on Workitems along the way.
- **UI redesign — pre-login (auth) pages brought onto `nexora-ui`.** The auth
  pages (login, forgot/reset password, 2FA setup + verify) load a shared new
  `static/css/auth.css` that maps their common Tailwind structure onto the brand —
  indigo→violet gradient buttons, a gradient top-accent card, nx radius/shadow, a
  soft brand wash and accent focus rings — plus `nexora-ui.css` for the tokens. The
  403/404/500 error pages already carried a distinct brand-aligned "cosmic" design
  and were left as-is.
- **UI redesign — public landing (hero) page + 2FA brand consistency.** The public
  `hero.html` landing page was reworked into a premium light "Trust & Authority"
  enterprise hero (per the ui-ux-pro design guide): a token-based (`--nx-*`) light
  fold with a restrained indigo→violet aurora accent and a faint hairline grid, an
  eyebrow status pill, a single primary CTA, a trust-signal row, and a crisp product-window
  mock of the document-status card. Because the whole page is token-based it follows
  the app's `html.dark` preference automatically — light by default, dark as a user
  preference. `static/css/hero.css` was rewritten onto the `--nx-*` tokens; the
  page was trimmed to hero → process journey → feature cards → CTA (the "Getting
  Started" steps and the FAQ accordion were removed), and the remaining sections,
  the closing CTA and the `_small_footer` all flow on a single continuous light
  wash — no per-section colour bands, the footer blends in with a hairline top
  rule — so the page reads smooth instead of as stacked blocks. Avoids a full-bleed
  purple wash (an explicit anti-pattern). The two 2FA pages (`init_2FA`,
  `verify_2fa`), which were still on residual
  `blue-600` buttons/badges, were brought onto the brand gradient (gradient buttons,
  gradient shield chip, `rounded-xl shadow-2xl` cards, accent focus rings); the
  shared `_small_footer` link-hover moved from blue to the brand accent. The login
  and forgot/reset/init-reset pages already matched and were left unchanged.
  Presentational only — all JS hooks (preloader logo-flight, process animation, FAQ
  accordion), routes, ids and `data-testid`s unchanged.
- **UI redesign — Reporting page brought onto `nexora-ui`.** The Reporting builder
  now consumes the global `--nx-*` tokens via a harmonization layer appended to
  `static/css/reporting.css`: panels, toolbar, buttons, mode/view toggles, inputs,
  tables, pivot shelf, modals and the AI panel share the indigo→violet brand
  signature, hairline keylines and dark-mode awareness (primary CTAs + active
  toggles use the brand gradient). Layout, ids and `data-testid`s are unchanged.
- **Reporting page — branded page header to match the other pages.** Following the
  colour harmonization above, the Reporting builder and the source-registry admin
  page (`/reporting/sources`) now open with the same `nx-page-head` block every
  other page carries — the indigo→violet gradient icon chip, page title and
  subtitle — and use the `nx-app` body shell. The "Sources" admin link moved from
  the builder toolbar into the page-header actions (restyled as an `nx-btn`,
  `data-testid` unchanged); "Back to Reporting" likewise sits in the registry
  page's header. Builder layout, ids and the remaining `data-testid`s are
  unchanged; one new translated string (de/fr/it) for the subtitle.
- **Templates — CDN assets pinned + Subresource Integrity.** Every
  jsdelivr/cdnjs `<script>`/`<link>` across all templates (Chart.js, flatpickr,
  xlsx, `@tailwindcss/browser`, `@tailwindplus/elements`, Font Awesome,
  highlight.js) is pinned to an explicit version and carries
  `integrity="sha384-…" crossorigin="anonymous"`, so a tampered or silently
  updated CDN asset will not load. Versions were pinned to the bytes already
  being served (no behavioural change). Google Fonts CSS is intentionally left
  without SRI — its stylesheet is user-agent-dependent and has no stable hash.
- Route listing (`nx --routes`) moved out of embedded PowerShell into Python (`nx_lib/cli.py::print_routes`) as the single source of truth shared by the one-shot flag and the REPL `routes` command.
- `CLAUDE.md` Databases section: corrected the stale git-hook install step (the non-existent `scripts/install-git-hooks.ps1` → `pre-commit install --install-hooks` / `bootstrap.ps1`) and the pre-commit hook reference (`scripts/git-hooks/pre-commit` → the `sql-migrate-int` / `sql-sync-check` hooks in `.pre-commit-config.yaml`).
- **`dbo.SearchConfig`:** backfilled `col_targetsystemfilename` for the `elektromaterial`/`privera` process rows via migration `0003_update_col_targetsystemfilename_data_searchconfig.sql`.

### Fixed
- **Generali add-modals no longer show an empty red strip.** The Tailwind v4
  browser CDN emits utilities inside `@layer utilities`, so the unlayered
  `.nx-flash { display:flex }` rule always beat the `hidden` utility and kept
  the (empty) modal error banner visible on the PDQM, base-services,
  project-management and reporting add/edit modals. `nexora-ui.css` now
  re-asserts `.nx-flash.hidden { display:none }` (same pattern as the earlier
  `pl-10` fix), and the four affected error banners were normalised to the
  icon + `<span id="…ErrorText">` markup additionalservices already used (the
  paired JS partials write the message into the span and keep toggling
  `hidden` on the banner).
- **Scheduled reports now support metric definitions.** The scheduled-report
  runner (`nx_lib/reporting/runner.py`) validated saved definitions **without
  the source's metric codes** and never resolved `metrics` into the aggregate
  query — any scheduled report carrying a metric (e.g. one saved from the
  Simple wizard) failed with *unknown metric* since semantic Slice 1. The
  runner now mirrors the interactive run path for both providers
  (docprocessing + `table`): it passes `metric_codes` to validation, resolves
  the metrics, builds the aggregate query, and appends the metric columns to
  the exported sheet.
- **Reporting AI — table-source drafts no longer bounce on labels/missing fields.**
  Small models (e.g. gpt-4o-mini) reliably emitted *near-valid* report definitions
  for curated **table** sources — using a column's human **label** ("Date") where
  the schema wants its **key** (`ForDate`), or omitting `schemaVersion`/`title` — so
  Surface A ("Build a report") and the Surface C agent's `build_definition` tool
  rejected them and the agent often looped to `max_turns` without an artifact. A new
  whitelist-safe repair (`schema.coerce_definition`, run inside the shared
  `_validate_definition_for_user` gate) now resolves a label back to its catalog key
  (columns, filters, sort, chart axes), backfills the column header with the label,
  and fills `schemaVersion`/`visualization`/a synthesized `title`/a default-or-clamped
  `rowLimit` — only ever swapping a label that maps to exactly one field, and a no-op
  for already-valid drafts. The human builder path (`/run`) is untouched.
- **Workitems "Show sources" — boxes mispositioned in the lightbox.** The
  full-page overlay measured the modal image with `getBoundingClientRect()`,
  which returns the *visual* (post-`transform`) rectangle. Because the overlay
  rendered on the image's `load` event — fired while the lightbox `zoom`
  animation (`scale(0.5) → 1`) was still mid-flight — the boxes were pinned to a
  shrunken, centre-pulled frame and never re-measured once the zoom settled, so
  they appeared stranded in blank space and "jumped" to a different place when
  the toggle was flipped off/on. The overlay (`#srcHlLayer`) is now
  `position:absolute` inside `#imageModal` and sized from the image's
  transform-independent **layout box** (`offsetLeft/Top/Width/Height`), so boxes
  map to the displayed page on first open and stay put across hide/show. Lightbox
  boxes also get a subtle white halo + drop shadow so they read clearly on white
  paper and over dark text/logos (confidence colour unchanged).
- **Workitems "Show sources" — boxes shown out of register on lightbox open.**
  A residual of the fix above: with the image cached, the overlay rendered on the
  very next frame after open, *during* the `.modal-content` open-zoom animation
  (`scale(0.5) → 1`). Because `#srcHlLayer` is a **sibling** of the image it does
  not inherit that transform, so the boxes — drawn at the page's final layout
  coordinates — floated off the still-scaling page ("already visible when you open
  it, locations wrong") and only snapped into place on a manual hide/show that
  happened to re-render against the settled image. The overlay's first render now
  waits until the page is geometrically settled — the image bitmap is decoded
  **and** every running animation on it has `finished` — via a new
  `drawOverlayWhenStable()` (reopen / prev-next, with no animation running, render
  immediately). A `ResizeObserver` on the modal image re-renders the boxes on any
  later box-size change (values-panel reflow, late decode, viewport resize),
  keeping them locked to the page without a manual toggle.
- **Reporting AI (Build a report) — polish.** Four follow-ups to Phase 2:
  (1) the curated-source catalog shown to the model now lists each field as
  `key "Human Label":type`, and the prompt instructs the model to emit the exact
  key (the label only aids field selection / column headers) — so docprocessing
  "Build a report" no longer drafts label-named fields the validator rejects;
  (2) the Build-mode definition summary in `_reporting_ai_js.html` (`"source"`,
  `"columns"`, `"filter(s)"`, `"sorted"`, fallback title, and the error strings)
  is now translated (de/fr/it) instead of hard-coded English;
  (3) a provider **misconfiguration** on `POST /api/reporting/ai/{ask,build}` now
  leaves an audit trace (`dbo.ReportingAiAudit` `Status='misconfig'`) instead of a
  silent 503 — `misconfig` is excluded from the `AI_DAILY_LIMIT` count so a broken
  provider never burns a user's daily quota;
  (4) the `_audit_ai` log line reports the actual `surface` instead of a hard-coded
  `reporting.ai.ask` (the DB `Surface` column was already correct).
- **Reporting — 500 on SQL/curated results containing binary or time cells.**
  `/api/reporting/sql/run` and `/api/reporting/run` returned raw pyodbc values to
  `jsonify`; Flask's default JSON encoder cannot serialize `bytes`/`bytearray`/
  `memoryview` (varbinary, `rowversion`/`timestamp`, image) or `datetime.time`,
  so any query selecting such a column 500'd with "Object of type … is not JSON
  serializable". Result cells are now coerced to JSON-safe values at the response
  boundary (binary → `0x…` hex, time → ISO string), preserving the types Flask
  already handles (date/datetime/Decimal/UUID).
- **i18n — app-wide Python messages now translated.** `babel.cfg` extracted
  Python strings only from root-level `*.py` (`[python: *.py]`), so every
  `_()`/`gettext()` route/flash message under `nx_lib/**` fell back to English
  for de/fr/it. Extraction is now recursive over `nx_lib/**.py`; the ~150
  newly-surfaced messages (auth, admin, dashboard, workitems, invoices,
  notifications, profile, reporting, …) are translated to de/fr/it. The
  `test_translations.py` gate enforces full coverage going forward.
- **Reporting — `status` synthetic field removed from catalog:** `fetch_docprocessing_catalog` was injecting `status` as always-available alongside `processname`, but `SearchConfig` has no `col_status` column and the query builder cannot synthesize it. Selecting or filtering on `status` produced all-NULL columns or a `QueryBuildError`. Now only `processname` (fully supported by the builder) is injected; `status` will be offered once a real column backs it.
- **Reporting — empty-cols guard in `_load_field_col_maps`:** added early-return when `SearchConfig` exposes no `col_*` columns, preventing malformed SQL being emitted.
- **Reporting — flatpickr wired for date filter inputs:** `templates/reporting.html` loaded the flatpickr CSS/JS but `_reporting_js.html` never used it. Date/datetime-typed filter fields now initialize a flatpickr calendar picker; the field dropdown re-renders the row (resetting the value input) when changed so the picker activates immediately.
- **2FA:** accept adjacent TOTP windows on verify, tolerating small client/server clock skew.
- **generali-import:** store the full CSV filename in the import log.
- **pre-commit:** exclude `sql/` from the `mixed-line-ending` hook (it already excluded `end-of-file-fixer` / `trailing-whitespace`). The auto-generated dumps are CRLF from mssql-scripter and LF-normalized by `.gitattributes`, so the fixer perpetually re-flagged them on Windows, blocking commits of any regenerated dump.
- **db-migrate — non-ASCII corruption via sqlcmd codepage.** `scripts/db-migrate.py` ran migrations through `sqlcmd -i <file>` without a UTF-8 input codepage, so sqlcmd read UTF-8 migration files in the host OEM/ANSI codepage and silently corrupted any non-ASCII text on INSERT (German/French strings, dashes, …). This is how migration `0011` stored the mojibake source label "Generali â€" PDQM Report". The runner now passes `-f 65001` (UTF-8 in/out) and decodes captured output as UTF-8; migration `0016_fix_generali_pdqm_label_encoding.sql` repairs the already-stored label (codepage-safe via `NCHAR(0x2014)`).
- **Reporting AI (agent, explain-data) — run_sql against builder-only sources.** Curated `table`-provider sources (e.g. Generali PDQM, which lives on GeneraliDB) are not reachable by `run_sql` (it only targets the statistics/octopus RO engines), but the explain-data agent bound `run_sql` unconditionally and drafted `SELECT … FROM <source>` against a run_sql target, looping on an unrecoverable 208 "invalid object name". The agent route is now **source-aware**: the client sends the active builder source and `POST /api/reporting/ai/agent` binds the data tools (`run_sql`/`compute_stats`) **only when that source is run_sql-able**, so a builder-only source confines the model to `build_definition` (and `explainData` is reported `false`). The schema grounding (`nx_lib/reporting/ai_schema.py`) also labels such sources **builder-only — answer with `build_definition`, NOT queryable with `run_sql`**, and the explain suffix spells out that `run_sql` only hits the named SQL targets.
- **Footer — stale hard-coded version.** `templates/_nexora_version.html` hard-coded `nexora 2.5.60`, a third copy of the version that silently drifted from `pyproject.toml`. The version is now single-sourced in `nx_lib/version.py`, injected app-wide via a `nexora_version` context processor, and consumed by both the footer and the dev CLI; `tests/unit/test_version.py` enforces it stays in sync with `pyproject.toml`.
- **Reporting AI — correct dates for "last month", "this year", etc.** The AI
  definition drafter (Surface A) and the agentic loop (Surface C) had no concept of
  the current date; gpt-4o-mini fell back to training-data dates and turned "last
  month" into a range from 2023. Both surfaces now receive today's date in their
  prompts and grounding and are instructed to resolve all relative time expressions
  against it.
- **Reporting AI — "different docsources" returned duplicate rows.** A columns-only
  definition (no `metrics`) compiles to a plain projection with no GROUP BY, so
  asking for the distinct values of a field produced one row per document, not one
  per value. The prompts now teach both surfaces the correct pattern: put the target
  field in `columns` and add a count metric, which makes the columns GROUP BY
  dimensions so each value appears once.
### Removed
- **`dbo.SearchConfig`:** dropped 12 unused columns (`col_scanbatchnr`, `col_pid`, `col_personalfileid`, `col_employmentfileid`, `col_doctypeidtargetsystem`, `col_doctypeidsydoc`, `col_registeridtargetsystem`, `col_masterdataseparatorsheettype`, `col_masterdatabirthday`, `col_masterdatafirstname`, `col_masterdatalastname`, `col_masterdataseparatorsheetid`) via migration `0002_remove_unused_columns_searchconfig.sql`.

## [2.5.61] - 2026-05-28

Dev-environment upgrade (10-PR bundle). No behavioural code changes — only structure, tooling, and naming. See `docs/superpowers/specs/2026-05-26-dev-env-upgrade-design.md` for the design and `docs/superpowers/plans/2026-05-27-dev-env-upgrade.md` for the step-by-step plan.

### Added
- `bootstrap.ps1` one-shot dev-environment setup. Idempotent and re-runnable: detects Python, installs uv if missing, runs `uv sync --extra dev`, installs Playwright chromium, seeds `env/<E>.env` from templates (never overwrites existing), installs pre-commit hooks (pre-commit / commit-msg / pre-push), ensures `var/` subdirs exist, prints a checklist of remaining manual steps. Quick start collapses to `git clone … && .\bootstrap.ps1`.
- `LICENSE` (proprietary Sydoc notice).
- `CHANGELOG.md` (this file, Keep-a-Changelog format).
- `CONTRIBUTING.md` — naming, branch, and commit conventions, plus the manual-fallback setup steps for when `bootstrap.ps1` doesn't fit.
- `.editorconfig` for cross-editor consistency.
- `.python-version` pinning Python 3.13.9.
- Modern Python toolchain: uv (deps), ruff (lint + format), mypy (types), pre-commit framework (`.pre-commit-config.yaml`), gitlint commit-msg lint (`.gitlint`). All wired into CI as blocking steps.
- `env/` directory: `INT.env` / `PROD.env` / `STAGING.env` / `TEST.env` (gitignored) plus committed sanitised `env/*.env.example` templates.
- `var/` directory consolidating all runtime data: `uploads/`, `session/`, `logs/`, `screenshots/`, `backups/`, `test-results/`. Only `.gitkeep` markers tracked. Resolved via `nx_lib.config.PATHS`.
- `bin/` directory for dev CLI scripts. Currently holds `bin/nx.ps1`.

### Changed
- `nx.ps1` moved to `bin/nx.ps1` (history preserved via `git mv`). `nx_lib.cli.NX_PS1` updated; the dir is excluded from the prod robocopy mirror.
- All non-root `*.env` files moved under `env/` (`env/INT.env`, `env/PROD.env`, `env/STAGING.env`, `env/TEST.env`). `nx_lib/config.py` now loads from `env/{ENVIRONMENT}.env` with a one-release fallback to the legacy root location (emits a `DeprecationWarning` naming both paths). The root `.env` env-selector stays put. `.gitignore`: `*.env` still ignores secrets everywhere, with a `!env/*.env.example` exception to commit the templates. `.github/workflows/deploy.yml` copies `env/PROD.env` (legacy fallback included) and `env/TEST.env` into the workspace `env/`. `scripts/test_db_reset.py` reads `env/TEST.env`. **PROD pre-flight on SYAPP01:** move `D:\sydoc\nexora\{INT,PROD}.env` into `D:\sydoc\nexora\env\` before the 2.5.61 bundle merges; the deploy and the runtime loader both fall back with a warning if you don't.
- Runtime data consolidated under `var/`: `uploads/`, `session/`, `logs/`, `screenshots/`, `backups/`, `test-results/` all moved out of the repo root. All Python writers now resolve their location through `nx_lib.config.PATHS` (e.g. `PATHS.logs`, `PATHS.uploads`), which auto-creates each dir at import time. The ops cleanup scripts (`ops/cleanup/csvLogs_toDB.ps1`, `ops/cleanup/cleanup_expired_sessionFiles.ps1`), pytest output paths (`--junitxml`, `--html`), and the GitHub Actions `test-results` artifact path are all updated. `static/uploads/` (Flask-served public chat assets) stays in place — only private runtime data moves. **PROD follow-up on SYAPP01:** move `D:\sydoc\nexora\{uploads,session,logs,screenshots,backups}\*` into `D:\sydoc\nexora\var\...` so the cron scripts pick up the new path on the next run.
- `scripts/db-migrate.py` `find_sqlcmd()` now falls back to common install dirs (`C:\Program Files\SqlCmd`, the ODBC 17/18 Tools `Binn` dirs) when `shutil.which` can't see `sqlcmd` on the runner's PATH. `deploy.yml` also prepends `C:\Program Files\SqlCmd` to `$env:PATH` in the PROD-migration step. Defensive against the post-install-PATH-isn't-yet-inherited pattern that wedged the 2.5.60 deploy.
- `README.md` quick-start collapses to `.\bootstrap.ps1`; setup details live in `CONTRIBUTING.md` (with manual fallback steps for when bootstrap doesn't fit).
- Dependency management migrated to uv with committed `uv.lock`. `requirements.txt` and `requirements-dev.txt` are now generated artifacts (kept for the IIS/wfastcgi deploy path).
- Git hooks now managed via the pre-commit framework (`.pre-commit-config.yaml`). Custom hook scripts under `scripts/git-hooks/` are wrapped as `repo: local` entries to preserve behaviour.
- Conventional Commits enforced via gitlint commit-msg hook (`.gitlint`).
- Python identifiers renamed to snake_case per PEP 8 / ruff rule set N. Notable: `pageVisability` → `page_visibility` (also fixes the long-standing typo); the four DB engine globals (`engineOctoDB`/`engineNexoraDB`/`engineStatisticsDB`/`engineGeneraliDB`) → `engine_octo_db`/`engine_nexora_db`/`engine_statistics_db`/`engine_generali_db`; `getDBUrl` → `get_db_url`; `get_activityinstancesToIgnore` → `get_activity_instances_to_ignore`; the four Generali route handlers (`generali_additionalServices` etc.) → snake_case with the camelCase **endpoint names preserved** via `endpoint=` on `add_url_rule`, so existing `url_for()` callers and templates continue to resolve unchanged. Same endpoint-preservation pattern for `init_2FA` → `init_2fa`.
- Ruff lint and format-check in `.github/workflows/deploy.yml` are now blocking (formerly advisory with `continue-on-error: true`).
- Jinja template files renamed to snake_case. All 30 camelCase templates (page templates, JS partials, error base, logo, version footer) renamed in lockstep with their includes / `render_template` callers. Highlights: `templates/admin/{accessControl,adminOverview,userDetail,archive/userManagement}.html` → snake_case; `templates/nexoraLogo/_nexoraLogo.html` → `templates/nexora_logo/_nexora_logo.html` (folder + file); `templates/handlers/_errorBase.html` → `_error_base.html`; all `templates/js/_<page>JS.html` and `templates/js/admin/_<page>JS.html` partials → `_<page>_js.html`; `templates/js/_generali-dashboardJS.html` also normalised hyphen → underscore. `messages.pot` and the three locale `.po` files re-extracted so source-path references match. Template-side identifiers (`pageV` kwargs, `active_page` strings) and the camelCase static CSS assets are intentionally out of scope.

### Removed
- Empty placeholder folders: `cleanup/`, `export-help/`, `generali-import/`, `news/`.
- Deprecated `environment_transfer_queries.tmp.sql` (superseded by `sql/_migrations/`).
- `scripts/install-git-hooks.ps1` — the PR 4 deprecation shim. Use `.venv\Scripts\pre-commit.exe install ...` directly (which the shim was already calling on your behalf).

## [2.5.60] - 2026-05-28
- Repository restructure (PRs #84, #85): `ops/` (prod-scheduled) vs `scripts/` (dev/manual), SQL migrations workflow, branch-name guard.
