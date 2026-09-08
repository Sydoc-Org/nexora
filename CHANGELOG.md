# Changelog

All notable changes to nexora are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **MediaMarkt scan protocol moves off Excel** — the Sydoc tenant gets a generated
  CRUD page `/t/sydoc/mediamarkt` (migration `0126`) over the new
  `SYDOC_Statistik.dbo.MediaMarkt_Batches` table: one row per scanned batch with
  date, batch number, pieces, type K/D/KA, done, correction batches, corrections,
  corrections received, remarks. The visum is stamped from the login. The 2026
  workbook is back-filled by `nx-sources/mediamarkt/import_protocol.py`. Same
  table is the reporting source **MediaMarkt — Batches** with *Pieces scanned* and
  *Batches* measures (`reporting.source.mediamarkt_batches.use`).
- **Generated CRUD pages learn two roles** — a `person` field is no longer typed:
  it is stamped server-side with the current username on every write. A `flag`
  field renders as a checkbox and stores 0/1.
- **Field quality covers every process of an onboarded customer** — migration
  `0125` relaxes the `0111` gate on `vFieldExtractionQuality` from
  (organization, process) to organization only, so ElektroMaterial's legacy
  `01_Invoice_1` and Privera's `PriveraPostFields` telemetry count again.
  Bucherer and Geberit stay out until they have an organization.
- **Bucherer & Frigemo reporting sources** — migration `0123` registers
  **Bucherer — EasyTax** (`dbo.Bucherer_EasyTax` on the Statistics DB, one row
  per document: measures *Imported documents*, *Exported documents* = rows with
  an export time, *Pages*) and **Frigemo — Documents** (`dbo.Frigemo`, daily
  counters summed: imported/exported documents and pages, deleted, invoices).
  Generic `table` sources, no code; one `reporting.source.<code>.use` permission
  each, held by Enterprise Admin only until granted.
- **Sydoc — Project Hours reporting source** — migration `0124` registers the
  bpsuite Projektbericht feed (`dbo.BPS_ProjectReport` on the Statistics DB,
  loaded by `nx-sources/bps/bps_project_report.py`): customer, project package,
  task, user, date, hours. Measures **Hours**, **Bookings** and **Absence hours**
  (hours on the `Absences` pseudo-customer). `reporting.source.bps_projects.use`.

Work toward the next release.

### Added

- **Live SQL reaches every reporting database, and names them.** The sandbox gained a
  third target — the **Generali** tenant DB (`reporting.sql.target.generali.use`,
  migration `0121`, own `db_datareader` login `DB_REPORTING_GENERALI_RO_*`) — so it
  covers every database the Sources rail shows a card for. The **Target** picker now
  labels the *database* (`SYDOC_Statistik`, `RuntimeDatabase`, `Generali`) instead of
  a registry label like "Live SQL — Octo": `/api/reporting/sources` returns each SQL
  source's configured database as `db` plus a `configured` flag, so the names match
  the rail cards and stay right when INT and PROD name their databases differently.
  A target whose read-only login isn't provisioned renders disabled with a "not set
  up yet" suffix rather than only failing on Run, and the picker opens on the first
  configured one. **NexoraDB is deliberately not a target at any permission level** —
  it holds the bcrypt password hashes and TOTP secrets.
- **Query a table straight from its Structure view.** Expanding a table in a source's
  **Structure** panel shows **Query the first 100 rows** under its column list: it
  drops you into Advanced's SQL mode on the target that reads that database, with
  `SELECT TOP (100) * FROM [schema].[table]` written and already run. Only drawn when
  Live SQL can actually reach that database, so Structure-without-SQL access never
  sees it.

- **Dashboard cards carry the Results tab's chart tools.** In edit mode every
  chart-bearing card has its own toolbar — chart type, download as image,
  Forecast + horizon, Colours & axes — and the tweaks are saved *on the card*
  (`card.viz`), never on the report: one saved report can be a bar chart here and
  a forecast line there. Drag-to-reorder now slides the neighbouring cards into
  place (FLIP transition) instead of snapping them.
- **Whole-report dashboard cards read like the Results tab** — KPI strip above a
  full-width chart, table behind *Show table*, card grows with its content (the
  fixed row height used to clip the fifth KPI tile and the table toggle).

### Fixed

- **Sydoc-tenant users no longer see a Prepared Documents link that always fails.**
  `0094` copied Mobscn's three tenant pages onto the new `sydoc` tenant, but Prepared
  Documents is a hard MS02-only route — every non-MS02 client gets `PermissionDenied`
  regardless of permission grants. Migration `0122` removes the `sydoc` tenant's
  `prepared` `TenantPages` row.
- **A wide result no longer widens the whole builder.** `.reporting-results` had
  `min-width: 0` only inside the collapsed-layout media query, so the middle grid
  track grew to its widest child: one `SELECT *` over a `varbinary(max)` column and
  the toolbar, editor and page all stretched past the window instead of the table
  scrolling inside its own card.
- **An unprovisioned SQL target no longer greys out a healthy database's rail card.**
  The Sources rail keeps one card per distinct database and the first source won the
  slot; the new Generali SQL target sorted first and probed as down (no RO login),
  turning a green card amber. A reachable source now wins the slot.

- **Short dashboard cards can stack beside a tall one.** Cards used to occupy one
  auto-sized grid row each, so a KPI next to a 3-row chart pushed the next KPI
  below the chart. Cards now span real row tracks (`grid-row: span rows`) with
  dense flow, so two 1-row KPIs sit stacked next to the chart.
- **Present mode had no margins.** The full-bleed padding rule out-ranked the
  fullscreen one, so the dashboard sat border-on-border on a wall screen.
- **Forecast on a dashboard card "did nothing".** On a report with more than one
  breakdown the toggle was a dead `disabled` button; it is now dimmed and a click
  explains the one-date-breakdown rule.
- **Ask Eddard about this report.** A button beside the *Eddard insight* card on the
  Results tab opens the chat with the report on screen attached: its definition
  (source, grouping, measures with their registry descriptions, filters) and, for a
  `reporting.ai.explain.use` holder, the same fact sheet the auto-caption uses. "Tell
  me what I am seeing" or "what are Cases" is answered from that context without
  tool calls; the header Eddard button is grounded the same way while a result is
  on screen. `POST /api/reporting/ai/agent` takes the optional `report` object.
- **Conditional measures.** `ReportingMetrics.FilterJson` (there since 0017, never read)
  now turns a measure into `COUNT/SUM(CASE WHEN <cond> THEN … END)`: a JSON list of
  `{field, op, value}` clauses, fields whitelisted against the source catalog, values
  parameterised. Editable as **Condition (JSON)** on `/reporting/metrics`. Migration
  `0120` seeds the three KPIs the Generali pages computed by hand: *Reports filed on
  time*, *Documents without post-check*, *Failed runs*.
- **Generali reporting sources** — migration `0117` registers **Attendance**,
  **Base Services**, **Project Management** and **ISS Reporting** as generic `table`
  sources over the Generali tenant DB (effort hours and KPI filings by category,
  date columns grainable for "over time" breakdowns). One `reporting.source.<code>.use`
  permission each; only Enterprise Admin holds them until granted. No code — the
  column catalog in `ColumnsJSON` is the whole config a custom tenant needs.
  Migration `0118` gives them Simple-wizard measures: **Effort (hours)** and
  **Entries** per effort table, **Reports filed** for ISS (break down by "On time"
  for the share). Sources without a measure are Advanced-only by design.
  Migration `0119` adds the two sources behind the Generali dashboard and import
  status pages: **Documents** over `dbo.v_ReportJobJoinDefinitions` (~870k rows;
  document type, input channel, communication, direction, recipient, language,
  status, post-checks, scan date — measures Documents and Cases) and **CSV
  Imports** over `dbo.CSVImportLog` (import runs, rows inserted/updated). The
  ISS source is relabelled **Reporting**, and the wizard's measure list groups
  every `Tenant — Thing` source under one tenant heading with a sub-label each,
  so Generali reads as one passage: Documents, Attendance, Base Services,
  Project Management, Reporting, CSV Imports. Platform sources sort first.
- **Architecture diagram** — `docs/nexora-architecture.drawio`, four pages: system
  overview, request lifecycle, multi-source workitems, tenancy & permissions. Pointer
  added to `docs/design/architecture-conventions.md`.
- **The Dashboard is a console.** The page loses every card frame: the four
  KPIs are one borderless strip separated by hairlines, each with its
  day-over-day change and a seven-day sparkline; the throughput chart spans
  the full content width with underline tabs (**Over time** / **Today by
  hour** — the separate hourly card is gone); and a new **Backlog** section
  draws a 14/30/90-day trend line per process from the half-hourly
  `dbo.BacklogHistory` snapshots. A 14 d / 30 d / 90 d range control drives
  both charts and sticks for the session. The header carries a live indicator
  with the last refresh time, a countdown to the next one, and a Refresh
  button that forces one now.
- `GET api/dashboard/backlog_trend?range=14|30|90` returns
  `{labels, series:[{name, values, current}], total, prev_total}` — per-process
  backlog history, scoped by the active process filter, capped at four named
  series plus "Other".
- **`scripts/perm-audit.py` + `/nx-perm-audit [PROD|INT]`**: read-only anomaly audit of
  the live permission grants: a customer seeing another org's processes or another
  tenant's pages, profile/org mismatches, customers holding `admin.*`, no-op user
  overrides, dead codes and empty profiles. Reads effective permissions through
  `spGetUserPermissions`, so it works on both the legacy catalogue (PROD) and the
  per-process shape from #238 (INT).
- **The tenant Dashboard and Workitems pages are the tenant's** (migrations
  `0097`, `0098`). The Dashboard and Workitems entries inside a tenant's
  sidebar group now open `/dashboard?tenant=<code>` and
  `/workitems?tenant=<code>`: the pages narrow your process grants to the
  processes whose organization belongs to that tenant, title themselves
  "`<Tenant>` Dashboard" / "`<Tenant>` Workitems", and light up only that
  tenant's entry. A user inside a tenant lands there by default. The scope
  sticks for the session until the global entry clears it, so a page that
  rewrites its own URL (Workitems does) keeps the tenant. Staff who
  see several groups get the unscoped views under their real names,
  **Global Dashboard** and **Global Workitems** — every process you may
  see, across tenants — from the global entries, which are relabelled
  accordingly. One helper (`process_helpers.granted_processes`) now feeds
  every process allow-list on both pages, replacing thirteen copies of the
  grant-parsing block. A custom page's `LayoutJSON` may carry a `query`
  object of string pairs that becomes the link's query string; mounting
  `dashboard` or `workitems_overview` from the tenant management page adds
  it automatically. Prepared Documents is MS02's own register with no
  process filter and stays as it is. A user inside exactly one tenant sees
  its pages flat under a plain label instead of a one-item collapsible
  group; staff and multi-tenant users keep the groups.
- **`AccessProfile.Rank` governs which profiles an admin may hand out** (#238,
  migration `0086`): an actor may assign a profile whose rank is at most their
  own. Enterprise Admin 100, Global Admin 90, supervisors 50, everyone else 10.
- **One `process.<client>.<name>.view` scope code per process** (migration
  `0087`) replaces the three per-process families (`workitems.filter.process.*`,
  `dashboard.filter.process.*`, `reporting.scope.process.*`); every process
  allow-list reads it through `process_grants()`.
- **Migrations `0091`, `0092`, `0094`, `0095` run on a post-#238 database.** They
  were written before `0086` dropped `AccessProfilePermission.Effect` and `0088`
  renamed the catalogue, and INT applied them first; PROD applies them after, where
  the old text would not compile. The Effect-dependent statements now sit in
  `sp_executesql` and the code lookups match both shapes (INT checksums
  re-blessed, the `0097` precedent). `0115` renames `admin.view/edit.tenants` to
  `admin.tenants.view/edit` so the two codes `0095` created follow the grammar.
- **`admin.permissions.edit`** gates catalogue edits (add, rename, delete a
  permission code) separately from profile grants.
- **`nx --doctor` Permissions section** warns about codes the code base
  references that are missing in `dbo.Permission`, and about profiles left at
  Rank 0.
- **Admin › Permissions grid** (`/admin/permissions`) replaces the per-profile
  permission drawer on Access Control and the read-only Permission Matrix page:
  every access profile against every permission, one checkbox per cell, saved
  as a diff. Children grey out until their object's `.view` is granted; click a
  code to see who holds it. Profile rank is edited on Access Control; user
  overrides on the user detail page use the same area › object grouping.
- **Enterprise Admin holds every permission** (migration `0106`) — granted
  today and kept that way by a trigger on `dbo.Permission`, so a code added
  later by migration or from the admin grid lands on the profile at once.
### Fixed

- **The `dbo.ActiveSessions` prune now has a way to be scheduled.** #227
  shipped `ops/cleanup/prune_active_sessions.py` and a docstring asking someone
  to register a task by hand; nothing in the repo executed it, so merging and
  deploying it deleted exactly zero rows.
  `ops/cleanup/prune-active-sessions-task.xml` is a ready-to-import Task
  Scheduler definition — daily 03:30, SYSTEM, `ENVIRONMENT=PROD`, output to
  `var/logs/system/prune_active_sessions.log` — following the pattern
  `ops/outage-monitor-task.xml` already established:

  ```
  schtasks /create /xml "D:\sydoc
exora\ops\cleanup\prune-active-sessions-task.xml" /tn "\sydoc
exora\Prune Sessions"
  ```

  Still one manual step on the host — the repo cannot register a task — but a
  one-command step with the definition under version control, rather than
  someone's memory of clicking through Task Scheduler. Four tests cover it,
  including that the file keeps its UTF-16 LE encoding: Task Scheduler refuses
  UTF-8, and an editor silently "fixing" it is invisible until an import fails.

### Changed

- **Advanced is back in the Reporting rail.** The **Advanced** nav entry (parked
  `hidden` on 2026-08-26) sits last in the Workspace group again, so the
  three-panel builder and its Live SQL tab are discoverable instead of only
  reachable via `?tab=advanced` or *Open in Advanced*.
- **A rejected Live SQL query is a 400, not a 500.** A statement the sandbox
  passes but the target server refuses (unknown table/column, ambiguous alias)
  is bad user input: `POST /api/reporting/sql/run` now answers **400** and logs
  it at WARNING, so a typo in the SQL editor no longer registers as an
  application error. Connection and timeout failures stay 500.

- **Dashboard cards are pieces of saved reports.** Add a card now opens the
  picked report in full (rendered by the same code as the Whole report
  card) with an **Add to dashboard** button on every KPI tile, the chart and
  the table, plus **Add whole report**. A card stores `{reportId, type,
  kpiIndex}` and fetches the report's live definition when the dashboard
  opens, so editing the report updates every card built from it. The
  dashboard-authored KPI / line / bar / donut / table renderers, the type
  pills, the size sliders, the blank-card picker and the KPI trend re-run are
  gone; cards saved by the old version show a remove-and-re-add notice.
  Cards use the Results tab's Console surfaces: a KPI card is the flat KPI
  tile (each of Total / Buckets / Avg / Peak is its own pickable tile), chart
  and table sit flush in the card with a title row and row count. The
  dashboard view is full-bleed — the workspace rail and every width cap step
  aside — and a **Present** button shows it fullscreen (Esc leaves). The
  **global filter bar shows the reports' own filters** — one chip per field
  (and Processes), the value the reports use, "mixed" when they disagree;
  clicking a chip edits it with date presets, a checkbox picker or a text
  field and the value replaces the reports' own on every card, with a reset
  per chip. Filter layering is now per field, most specific wins (override
  > dashboard > report), so a dashboard "last month" no longer ANDs with a
  report's "this month" into an empty result.
- **Simple wizard breakdown step curated.** Date chips read as their field
  (“Import date”, “Export date”) instead of “Over time (…)”. Document
  processing shows Process, Page Count, Document Type, Document Source and
  Creditor Name; a **Show advanced fields** chip unfolds the rest. Table
  sources flag theirs with `"advanced":true` in `ColumnsJSON`. The Field
  extraction quality source drops Stream and Workitem from its catalog,
  labels Customer as **Client**, prefixes Process with its client
  (`elektromaterial.02_Invoice`) and folds the raw/diagnostic dimensions
  (migration `0116`). The result table is shown by default under every
  chart; **Hide table** collapses it.

- **A tenant's own users never see the tenant named** (#255). For a user who
  belongs to exactly one tenant and holds no grant on another, the tenant *is*
  the portal, so naming it only exposes an internal concept: the sidebar's
  plain tenant label is gone and the mounted pages title themselves
  "Dashboard" / "Workitems" instead of "`<Tenant>` Dashboard" / "`<Tenant>`
  Workitems". Their view is byte-for-byte what it was before the tenant
  kernel landed. Staff and members with cross-tenant grants keep the names --
  they have several tenants to tell apart. Driven by one `tenant_solo` flag
  from `_inject_tenant_nav()`.
- **Permission codes follow one grammar, `<area>.<object>.<action>[.<scope>]`**
  (#238, migration `0088`). Every code was renamed; the full old → new mapping
  is Appendix A of `docs/superpowers/specs/2026-09-01-permission-structure-design.md`,
  the grammar and the rules around it are `docs/design/permissions.md`. Generali
  codes live under `tenant.generali.*`. Grants rode along on `PermissionID`, so
  nobody lost or gained access.
  **Deploy note:** migrations run before the app pool stops, so the old build
  serves renamed codes for the deploy window and answers 403 — deploy off-hours.

### Removed

- **`/admin/permission_matrix`** and the Permissions tab on Access Control (both folded into the grid).
- **Profile-level DENY** (446 semantically empty rows), **the ten
  `admin.assign.user.accessprofile.*` codes** (rank replaces them), **12 orphan
  codes** (`invoices.*`, `kundenmagazin.*`, two dead admin codes) and **the
  three per-process permission families** (#238).
- **Extraction quality is now reportable (#254).** The Octo runtime has been
  writing per-field extraction telemetry into the statistics DB for years —
  one row per document field, with what the machine read, what the validator
  ended up with, and the extractor's confidence — and nothing looked at it.
  A new Reporting source, **Field extraction quality**, puts it on the
  page: break down by Field and rank by "Extraction correct %", "User
  corrected %" or "Avg. confidence %" to see which fields extraction handles
  well and which cost validators the most time. Nine measures, gated by
  `reporting.source.field_quality`. It unions **all seven customer telemetry
  streams** — Bucherer, Compass, ElektroMaterial, Geberit and Privera's three —
  into one source with a Customer breakdown rather than seven separate ones,
  which is what lets you rank the *same* field across customers: field names are
  normalised to a shared vocabulary first, so whatever each customer calls its
  invoice number lands on the same row. A Stream dimension splits a customer
  running more than one document flow. Only **onboarded processes** are
  reportable — the picker no longer offers Octo's internal process names, and
  the filter reads `dbo.ProcessSources` matched on organization *and* process,
  so onboarding a process is all it takes to bring it in (and `02_Invoice` being
  onboarded for ElektroMaterial does not admit Privera's).
  Raw field values and the validating user are deliberately not exposed — the
  source answers "which fields extract well", not "what did this invoice say"
  or "who fixed it". Octo's ~630 raw field names are translated through the
  existing `FieldAliases` / `FieldLabels` registries, and "Mapped in nexora %"
  filters a report down to the fields nexora actually knows about — widened by
  adding alias rows, not by editing SQL. The measure descriptions spell out two
  traps the raw numbers hide: "Deviation %" is not the complement of "Extraction
  correct %" (a field the machine never attempted still deviates when a
  validator fills it in), and the headline rate understates the extractor —
  EM reads 51% correct overall but 94.6% on the instances it actually attempts.
  The breakdown labels put the useful dimension first and call it plainly
  "Field": it was named "Field key (nexora)" while a near-useless wide variant
  held the name "Field", so the obvious pick charted 631 series of which 230 sit
  permanently at 100%.

### Fixed

- **Eddard couldn't see an activated forecast.** "Ask Eddard about this report" attached the
  definition and fact sheet but never the forecast toggle, so a question about the projection
  got answered as if it weren't there. `report_context_text` now states when forecast is on
  (with its horizon) and, when the result is shared, that the trailing buckets are the forecast
  rather than more actuals; `reporting_simple.js` passes the run's forecast block along.
- **Eddard always announced which report he was reading.** The "Reading: I used the ..."
  preamble is meant for genuinely ambiguous questions (issue #132); it fired even when a
  specific report was already attached, where the report is given, not guessed. The
  report-context grounding now tells the model to skip that preamble for this flow.
- **Chat starter chips didn't fit the attached report.** The four fixed suggestions
  ("imported vs exported, last 30 days", etc.) are tuned to the docprocessing source and kept
  showing next to whatever report "Ask Eddard about this report" attached, even when they made
  no sense for it. They now hide once a report is attached.
- **Live SQL said why a query failed.** A failed run showed only "Could not run
  query" — the API had been sending the driver message in `detail` all along and
  `NX.api` threw it away. It now rides on the thrown `Error` as `err.detail` and
  the builder prints it under the message ("Invalid object name 'Workitem'.").
  An error raised while the Chart or Pivot view was open is also visible now
  instead of landing in a hidden container.
- **Switching Table <-> SQL in Advanced cleared the result area.** The two modes
  share one result pane, so SQL mode used to inherit the builder's grid, pivot
  shelf, KPI band, AI caption and timing badge — and showed the *builder's*
  generated SQL in "Query sent to the database" while the editor above held a
  different statement entirely. Each mode now starts from its own empty state.
- **The Advanced filter row fitted its column.** Three `flex: 1` controls in the
  240px wells panel left the field name clipped to "Worki" and the value box
  ~60px wide; the field select takes its own row and operator + value share the
  next one.

- `POST /api/reporting/run` answered 500 instead of 400 when a `columns` entry
  was a bare string rather than `{field}` (the error message itself crashed).

- **The reporting KPI tiles said what they compute.** On a report with a date
  dimension *and* a second breakdown ("Extraction correct % by month / Field":
  4 periods x 28 fields), three of the four tiles misdescribed themselves.
  **Buckets** counted result rows, so 112 appeared under "periods in the
  range" where there were 3 — the row count is now reported as the average's
  denominator and Buckets counts the leading dimension's distinct values.
  **Avg per bucket** claimed "total / buckets" while computing the mean of the
  cells (34.501 / 112 is 0.31, not 54.029); with a breakdown it now reads
  "Avg per row / mean of N values". The **headline figure** captioned itself
  "Total ... sum over the period" when it was the server's authoritative
  `AVG()` over every underlying row — a rate, not a total — and now reads
  "Overall ... over every matching row". Finally, rows whose leading dimension
  is NULL are excluded from the band, matching what the chart draws and what
  `caption_facts` already stated, so Peak no longer labels itself `null` and
  the tiles agree with the AI caption instead of contradicting it. Both
  implementations fixed (Simple's `reporting_simple_result.js` and the
  Advanced grid's mirror); pinned by `tests/unit/test_reporting_kpi_band.py`.
- **A migration that would have failed on a fresh database.** The permission
  grant in `0107` referenced `dbo.AccessProfilePermission.Effect`, a column
  retired by `0086` — a *lower* number, so on any rebuild or PROD deploy the drop
  runs first and the grant dies with it. It passed on INT only because the column
  still existed the hour it was applied. Both variants now sit in `sp_executesql`
  behind a `COL_LENGTH` check: an `IF` alone is not enough, because SQL Server
  binds every column in a batch before executing any of it, so even the untaken
  branch takes the whole batch down. `docs/howto/db-migrations.md` writes the
  trap up, including why this is the one case where editing an applied migration
  is correct — nothing added later can rescue a file that fails inside itself.

### Changed

- **The Simple wizard's measure list is grouped by source.** With more than one
  source the chips used to be one flat list with a `· Source Name` suffix on
  every label; they are now clustered under a caption per source, the same
  pattern the breakdown step already used. Reads far better now that picking a
  measure greys out every chip from the other sources — that constraint has
  always been there, but with a second source it went from two greyed chips to
  most of the list.
- **"Document count" is retired in favour of "Documents imported" /
  "Documents exported".** The measure list now says which date a document is
  counted on instead of leaving it unanchored. Five saved reports built on
  `doc_count` are repointed automatically, moving the date column, filter and
  sort onto the shared `activity_date` axis along with the measure — the numbers
  are unchanged. Only unambiguous definitions are rewritten; anything else keeps
  `doc_count` and is left for its owner. "Pages processed" goes the same way —
  `pages_imported` / `pages_exported` give the same numbers with a stated date —
  which leaves every Document Processing measure date-anchored, so they now all
  combine with one another instead of one odd chip greying out the rest. "Field
  instances" and "Workitems (distinct)" also come off the field-quality source:
  they measure how much data is in scope, not how well extraction works.

- **Migrations can reach another database on the same server.**
  `scripts/db-migrate.py` now passes the configured database names to sqlcmd as
  `-v` variables, so a migration writes `[$(StatisticsDb)]` instead of a
  hardcoded name that would be wrong on PROD. `$(NexoraDb)`, `$(StatisticsDb)`,
  `$(GeneraliDb)` and `$(OctoDb)` are available; an unset one is not passed, so
  sqlcmd fails loudly rather than substituting an empty name.

- **Repository moved to the `Sydoc-Org` GitHub organization** (from the
  personal `Sydoc-Code` account, 2026-09-03). GitHub redirects the old URL,
  but update your remote:
  `git remote set-url origin https://github.com/Sydoc-Org/nexora.git`.
  The org is still on GitHub Free, so branch protection remains the local
  pre-push guard until the org moves to GitHub Team (see CONTRIBUTING.md).
- **Branching model: short-lived topic branches instead of version branches**
  (#253). Nothing is pushed to `main` directly any more — everything lands via
  PR, review optional so either developer can merge their own once CI is green
  (the pre-push hook refuses a push from `main`, since branch protection needs
  a plan this private repo does not have). A
  branch is `<type>/<slug>` (`fix/253-collab-rules`), cut from `main` and gone
  within a day or two; `v<x.y.z.n>` branches are legacy and still accepted only
  so in-flight work can push. Releases become a **tag on `main`** rather than a
  branch. `scripts/git-hooks/branch-name-guard.ps1` enforces the new names, and
  `CONTRIBUTING.md` gains "Working in parallel" (the migration-number claim
  rule and the generated-file conflict hotspots) and "Releases".

### Fixed

- **The last eight hardcoded-English strings are out of
  `static/js/reporting_schema.js`** (#246). Each was the fallback half of
  `I18N.key || '<English default>'`, kept for the case the shim was missing.
  They were unreachable -- `templates/js/_reporting_schema_js.html` defines
  the shim and loads the script back to back, and supplies every key the
  script reads -- but they were real hardcoded English by the letter of the
  i18n lint, and were allowlisted rather than fixed when that lint was
  widened. The literals are now `''`: the `||` guard stays, so a missing
  shim degrades to a blank label rather than the text "undefined", and the
  eight `ALLOWED` entries are gone.

  A new test asserts the script and its shim supply exactly the same key
  set. Without the fallbacks an unsupplied key renders blank -- quieter than
  a stale English word, but silent -- and nothing previously checked that
  the two files agreed.
- **Expired `dbo.ActiveSessions` rows are deleted** (#227). Session expiry was
  implemented on one half only: the session *files* were pruned on a schedule,
  the database rows never were, so PROD had accumulated 1,558 rows of which
  ~93% were expired and the oldest was four months old. An orphaned row cannot
  authenticate -- its file is gone -- but it still claims to be a session.
  `ops/cleanup/prune_active_sessions.py` now removes them, with retention
  derived as `SESSION_LIFETIME + SESSION_ROW_RETENTION_GRACE` (24 h + 7 days)
  from `nx_lib/config.py` rather than restated, so it cannot drift below the
  lifetime of a live session and sign someone out. Straight delete, no archive:
  every reader of the table filters to the last 30 minutes, login history
  already lives in `dbo.Logs` and `Users.LastLoginAt`, and the one field not
  duplicated elsewhere is `IPAddress` -- personal data with no retention
  purpose. `--dry-run` reports without writing.
- **The 2FA screen works in dark mode** (#243). It never set Tailwind's
  `darkMode: 'class'`, so every `dark:` utility followed the OS
  `prefers-color-scheme` instead of the page's own `.dark` class -- the
  shared footer's `dark:brightness-0 dark:invert` fired on a light page
  whenever the OS was dark, rendering a white logo on a white background.
  Its surfaces were also hardcoded (`bg-white`, `text-gray-800`), so the
  page stayed white even once the pre-paint had set `.dark`; they now read
  the `--nx-*` tokens, which flip with the theme and need no new CSS.
  `init_2FA`, `forgot_password` and `reset_password` have the same problem
  and are tracked in #266.

- **The 2FA screen follows your accent colour** (#243). The shield gradient,
  the submit button, the focus rings and the page backdrop all read
  `--nx-accent*`, but `verify_2fa.html` never set `data-accent`, so they sat
  on the indigo defaults whatever you had chosen. The server cannot help
  there -- mid-2FA the session holds `pre_2fa_userid`, not `userid`, so prefs
  are deliberately not loaded -- so the page now reuses the same pre-paint
  block, which falls through to its `localStorage` mirror from the last
  signed-in page load. No database read on the login path, nothing about the
  account rendered into the page, and no stored prefs still means the amber
  default. The block moved to `templates/_ui_prefs_prepaint.html`, included
  verbatim by `_header.html`, so two copies of the accent derivation cannot
  drift apart.

## [3.2.4] - 2026-09-03

### Added

- **Answer-depth picker in the Eddard chat composer.** Click into the
  input and a Quick / Balanced / Deep control slides in above it, mapping
  to effort `low` / `medium` / `high` on the `/api/reporting/ai/agent`
  call. Quick trades deliberation for speed on straightforward counts;
  Deep gives the agent more room on hard, multi-source questions.
  Each segment carries a three-bar level meter (one, two or three bars lit)
  rather than three unrelated glyphs, since the thing being chosen is a
  scale; the bars rise in sequence when you pick a level.
  The control is capability-gated — it is absent, not greyed out, when the
  configured model cannot honour an effort level (`supports_effort()`),
  because Claude Haiku 4.5 and the non-reasoning Azure models reject the
  parameter outright. The choice lasts for the life of the panel.

- **Eddard's starter chips now lead with what the stack does best.** The empty
  chat panel offered generic prompts (one of them, "invoices by process",
  named a source that does not exist). It now offers four questions built on
  the `docprocessing` source's anchored imported / exported / Backlog metrics
  and its Process dimension: imported per month this year, imported vs
  exported over 30 days, documents by process this quarter, and imported but
  not yet exported. Each was run against the live agent and returns a real
  report definition.

- **The Eddard composer is now one surface.** The textarea, the depth
  picker and send used to be three stacked widgets; they are now a single
  rounded container that owns the focus ring, with the depth control as a
  trigger pill at bottom-left and send at bottom-right — the shape a model
  picker takes. Choosing a depth opens a popover listing each level with
  its meter and a one-line description.

- **Eddard's send button is an arrow, not a paper plane**, and circular like
  every other current chat composer. It lifts on hover and launches on send,
  which gives a 7-55s agent run a visible starting gun; while the request is
  in flight the button breathes rather than sitting dead. Styles are scoped to
  a local `.rp-chat-send` skin so the shared `.nx-btn--primary` is untouched.

### Performance

- **The reporting source/metric registry is cached for 60 seconds.**
  `_load_db_sources()`/`_load_db_metrics()` in `nx_lib/views/reporting/_shared.py`
  hit `dbo.ReportingSources`/`dbo.ReportingMetrics` on every call — up to
  ~8x per report run. Both now use the house TTL-cache pattern (mirrors
  `nx_lib/mapping_config.py`: success-only caching, a load error re-queries
  next call rather than caching the failure). Every admin CRUD route that
  writes those tables invalidates the cache immediately, so an admin edit is
  still visible without waiting out the TTL.
- **Static assets (CSS/JS/images) now cache for a year in the browser.**
  Every template asset tag was swept from raw `url_for('static', ...)` to
  `static_v(...)` (#191's mtime-busted `?v=` helper), so
  `SEND_FILE_MAX_AGE_DEFAULT` can safely go from Flask's no-cache default to
  365 days — a changed file gets a new URL, so a stale cache is never
  served past the next deploy. A new lint test bans raw
  `url_for('static'` in `templates/**` to keep it that way.
- **The Generali dashboard's aggregate/filter-option endpoints are cached for
  120 seconds.** `api_generali_stats` (7 aggregate scans) and
  `api_generali_filter_options` (7 `DISTINCT` scans) re-scanned
  `v_ReportJobJoinDefinitions` on every dashboard load. Both now use
  `dashboard.py`'s existing `@cache.cached` house pattern — a per-user (and,
  for stats, per-date-range-filter) cache key, and a `response_filter` that
  never pins an error or validation-failure response for the full TTL.
  Measured on real INT Generali data: cold 1.780s median → warm (cached)
  0.064s median, ~28x faster within the 120s window.
- **`fetch_merged_page`'s per-row source-routing cache write is now one
  batched `MERGE`, not up to 1000 sequential ones.** The warm loop used to
  call `get_source_for_workitem` per uncached row, each doing its own
  MERGE + commit round-trip; a new `_cache_store_many` collects a page's
  resolved `(WorkItemID, ClientCode)` pairs and writes them in a single
  multi-row `MERGE ... USING (VALUES ...)` statement (chunked at 1000
  rows/2000 params). Isolated benchmark against the real NexoraDB, 300
  uncached ids: 300x sequential `_cache_store` calls, 19.436s median →
  1x `_cache_store_many` call, 0.088s median — **~221x faster** for the
  store step. (A real end-to-end page timing wasn't a usable instrument on
  this INT dataset: MS02's id range sits almost entirely inside the
  default source's, so nearly every previously-uncached row resolves
  ambiguous and was never cached in either version — see the isolated
  number above for the mechanism this actually fixes.)
- **Prepared Documents' per-page Octo stage lookup is now one query, not
  one per row.** `prepared_documents()` called
  `_resolve_prepared_doc_wid_stage` once per pid on the page (up to
  200/page) against the MS02 Postgres runtime. A new
  `_resolve_octo_wid_stage_pg_batch` resolves the whole page's wids in one
  `WHERE twi."ID" = ANY(%s)` query; a missing wid still degrades to the
  same empty stage sentinel as before. Measured against a real MS02
  Postgres instance, 200 wids: 200x per-wid queries, 9.021s median → 1x
  batched query, 0.047s median — **~193x faster**.
- **`engineNexoraDB`'s connection pool is sized for a full waitress thread
  complement, and NexoraDB connects fail fast.** `pool_size` 10→32,
  `max_overflow` 20→16 (every request touches NexoraDB via the
  session/permission hooks, so the pool used to be smaller than PROD's 32
  waitress threads); a new `LoginTimeout=5` on the NexoraDB connection
  string makes a downed DB fail in ~5s instead of the ODBC driver's ~15s
  default. No single before/after number here — this is headroom, not a
  hot-path speedup — but verified with 60 concurrent authenticated
  `/dashboard` requests against the new pool sizing: all 60 returned 200,
  zero pool-exhaustion warnings in `app.log`/`app_stderr.log`. The
  `/api/reporting/sources/health` probe was also parallelized (bounded
  0.8s deadline instead of sequential unbounded per-engine probes), so N
  down data sources cost ~0.8s total instead of N sequential timeouts.
- **The permissions/UI-prefs session hooks skip the write when nothing
  changed.** `_reload_user_permissions`/`_load_user_ui_prefs` still read
  fresh from the TTL cache every request (unchanged), but now only assign
  into `session[...]` when the freshly-read value differs from what's
  already there — Flask marks a session dirty on every assignment
  regardless of whether the value changed, which meant a filesystem write
  + `Set-Cookie` on every single request on PROD's Flask-Session
  filesystem backend. Verified locally via `session.modified` staying
  `False` on an unchanged-value request and `True` on a real change
  (permission grant/revoke, pref edit still propagate on the next
  request); the actual disk-I/O/header-count reduction is PROD-only
  (Flask-Session's filesystem backend is deliberately off in local dev)
  and wasn't independently measurable in this environment.

### Changed

- **Access profiles are named `<Organization> <Role>`** (migration `0105`): `Enterprise Admin`,
  `Global Admin`, `Sydoc User`/`Sydoc Supervisor` (formerly `nexoraUser`/`nexoraSupervisor`),
  `ISS User`/`ISS Supervisor`, `PDBS User`, `Privera User`, `Compass User`, `ElektroMaterial User`,
  `Generali User`. The same migration creates `Generali User` (GNRL, every Generali portal code)
  and moves Generali users off the ISS profiles, folds the duplicate Basel-Stadt org `BSPD` into
  `PDBS`, moves sydoc staff off customer profiles onto the Sydoc ones (which gain the PDBS
  process and prepared-audit so nothing is lost), and renames the two assign codes whose slug
  changed. `nx_lib/security.py::assign_profile_code` builds that slug (spaces dropped).
- `api/dashboard/kpi_stats` also returns the previous day's value and a
  seven-point daily series per KPI; `api/dashboard/avg_processing_time` the
  same in minutes. `api/dashboard/processed_over_time` accepts `range`.
- **ISS and sydoc AG sit inside their tenants** (migration `0104`). ISS
  (`SSIX`) joins `generali`, the portal it works in; sydoc AG (`SYDC`) joins
  `sydoc`. Membership alone opens a tenant since `0096`, so ISS's existing
  `tenant.generali.view` grants stay as harmless leftovers. Members land on
  their tenant's Dashboard and Workitems by default; sydoc staff keep every
  tenant group and the Global entries through their grants. Only `demo`
  (`DMEO`) stays outside a tenant.
- **A tenant is a portal, not a data connection** (migration `0096`). Three
  tenants in, every `ClientCode` pointer — on `Tenants`, on `Organizations`,
  on `ProcessSources` — agreed in every row, and "tenant" meant a partner
  (Mobscn), a customer (Generali) or an operator (Sydoc) depending on the
  row. Decision: a tenant is the set of organizations that share one
  navigation group (`Organizations.TenantCode`), nothing more. Where data
  lives belongs to the thing that reads it — a process configuration already
  carried its connection; a generated entity now does too
  (`TenantEntities.ClientCode`, backfilled from its tenant). Dropped:
  `Tenants.ClientCode`, `Tenants.OrganizationCode`, `Organizations.ClientCode`.
  The Organizations overview derives an organization's connections from its
  process configurations; the tenant and organization edit modals lost their
  connection pickers. **Visibility is membership or grant:** a user whose
  organization belongs to a tenant sees its group and pages by right (a
  member without `tenant.<code>.view` no longer gets an empty sidebar);
  `tenant.<code>.view` remains the grant for non-members — sydoc staff working
  Generali — and `tenant.<code>.edit` stays an explicit grant.
- **Tenant management page** at `/admin/tenants/manage` (#256 phase 2,
  migration `0095`). Create and edit tenants (display name, active flag),
  decide which organizations belong to them (ticking an
  organization owned by another tenant moves it), mount existing pages into
  a tenant's sidebar group (endpoint picked from the app's argument-less GET
  routes, with label, icon, active marker and sort order), set pages to
  draft or active, remove them, and delete a tenant once no organization
  belongs to it. Creating a tenant provisions its `tenant.<code>.view/.edit`
  permissions (granted to nobody). Entities, fields and the generated
  list/crud pages stay migration-only and are shown read-only. New
  permissions `admin.view.tenants` / `admin.edit.tenants`, seeded like
  `0080` to every profile holding `admin.view.organizations`.
- **The Sydoc tenant** (#257, migration `0094`): ElektroMaterial, Privera
  and Compass — the customers sydoc hosts on the shared `default` runtime —
  form the tenant `sydoc`, with the same three mounted pages as Mobscn.
  Compass finally gets an organization row (`CMPS`) and its
  `compass.01_Invoice_SAP` source. `Tenants.OrganizationCode`, the pre-0090
  single-organization pointer, is nullable now — a tenant with several
  organizations has no single answer; `Organizations.TenantCode` is the
  relation that counts. `tenant.sydoc.view` goes to the profiles bound to
  the member organizations and to `globalAdmin`. Left alone on purpose:
  `compassUser` stays global (a `demo` user holds it), and sydoc AG, ISS
  and demo stay outside any tenant (`0104` later seats the first two).
- **Tenant-scoped navigation** (#257, migration `0093`). A user whose
  organization belongs to a tenant sees that tenant's group instead of the
  global Dashboard / Reporting / Workitems links — the same pages reached
  through the tenant's mounted pages, not twice. Users of organizations
  outside any tenant keep the global navigation. Mobscn's
  group is now Dashboard, Workitems and Prepared Documents with proper
  labels and icons; the generated "PDBS Dossiers" list page is set to
  `draft` (kept, not served). `nx_lib/tenant/registry.py::organization_tenant`
  answers "which tenant is this organization in", cached 60 s and failing
  closed to *not scoped*.
- **Generali is a tenant** (#257, migrations `0091`/`0092`). A `generali`
  data connection (`engine_generali_db`, no Octo), a `GNRL` organization, the
  `generali` tenant and one `custom` page per existing Generali page — so the
  Generali sidebar group now comes from the tenant registry like Mobscn's,
  and the hardcoded block in `_header.html` is gone. `tenant.generali.view`
  goes to every profile or user that already reaches a Generali page. The
  pages, their CRUD code and the 46 `generali.*` permissions are untouched;
  folding those into `tenant.generali.*` is #238's job. To make this
  possible, `nx_lib/clients.py` now loads a connection **without an Octo
  domain** as a data-only connection (only `default` still requires one),
  and the workitem paths (`api_external`, client-hint routing) consult
  `workitem_clients()` so a data-only connection never takes part in
  workitem routing. Custom tenant pages can carry `label`, `icon` and
  `active` in `LayoutJSON` for the sidebar.
- **Organization-centric tenancy** (#257, migration `0090`). The organization
  is the hub now: it belongs to a tenant (`Organizations.TenantCode`), owns
  its process configurations (`ProcessSources.OrganizationCode`) and its
  access profiles (`AccessProfile.OrganizationCode`, NULL = global). The
  columns are
  nullable FKs backfilled from the conventions the data already followed —
  the tenant pointer, the `<customer>.<process>` name prefix, the
  `priveraUser`-style profile names — so nothing changed meaning.
  **Rule:** a profile bound to an organization can only be held by that
  organization's users; the user add/edit endpoints refuse a mismatch (400),
  binding a profile that users elsewhere already hold is refused (409), and
  the profile pickers on Access Control and the user page only offer
  global profiles plus the chosen organization's own. Organizations' edit modal
  gained Tenant, Process Configurations gained
  Organization, the Access Control profile drawer gained Organization, and
  `/admin/tenants` now reads tenant → organizations → users / access
  profiles / data connection / process configurations, with the unassigned
  leftovers (e.g. `compass.*`, `compassUser`) called out.
  `Tenants.OrganizationCode` stays until the tenant registry stops reading
  it; a later migration drops it.
- **Tenants overview page** at `/admin/tenants` (#256, read-only phase).
  One card per tenant, joining what the other admin pages show in
  isolation: the customer organization and the users in it, the data
  connection and whether the running process loaded it, its process
  configurations (sources + document-field mappings), and the tenant's generated pages. A trailing "Not in a
  tenant" section lists the organizations and connections no tenant points at
  — with a *named-after* hint tying `<customer>.<process>` sources to the
  organization they are named for. Gated like Organizations (`admin.view.organizations`);
  the connection and process-configuration columns additionally respect
  `admin.view.clients` / `admin.view.processes`. Organizations gained a
  **Tenant** column linking back to it.
- **Admin nav renamed after what the pages do, not the tables behind them**
  (#255). `Clients` is now **Data Connections** (engine, dialect and Octo
  domain per client code), `Processes` is **Process Configurations** (its
  `dbo.ProcessSources` / `dbo.ProcessFieldMappings` mappings); `Organizations`
  keeps its name. The three sit together in a new
  collapsible **Tenants** group inside the admin sidebar, since together
  they are what describes a tenant. Routes, `data-testid`s, permission
  codes and DB columns are unchanged — labels only, plus de/fr/it.
  Reporting keeps its own `Processes` label (a report scope, different
  thing).
- **The `ms02` runtime source and tenant are labelled "Mobscn"** (migration
  `0089`). Display names only: the code stays `ms02` because it is the PK
  referenced by `dbo.ProcessSources`, `dbo.ProcessFieldMappings`,
  `dbo.WorkitemSourceCache` and `dbo.Tenants`, names the `MS02_*` env keys,
  and is baked into the `tenant.ms02.*` permission codes.

- **The deploy pipeline stopped testing everything twice.** Every commit
  reaching `main` arrives through a PR whose CI run already executed the full
  suite; the post-merge run on `main` then executed it again before deploying,
  so a merge cost ~42 min of CI for a `deploy` job that itself takes 31 s. The
  e2e suite (14m51s of the 21-minute test job, plus its Playwright chromium
  install) is now PR-only. The merge commit — the one artifact the PR run never
  saw — is still gated by lint, mypy and the unit/integration tier, cutting the
  path from merge to PROD to roughly 6 minutes.
- **Beautification Phase 3: tighter mypy and ruff configuration, plus a
  per-module typing ratchet.** `check_untyped_defs` was enabled repo-wide
  first (annotation fallout only, no bugs found), then `strict_optional`
  (found and fixed two real production bugs — see Fixed: admin
  add/edit-user's unknown accessprofile/org 500, and dashboard
  `set_filter`'s empty-body 500/415). Ruff gained the `PL` cherry-picks
  (`PLW1510`, `PLR1714`, `PLR1730`, `PLR0124`) and the full `PERF` rule
  set; the sole `PLR0124` hit (`field_locations.py`'s `f != f` NaN check)
  was confirmed a deliberate idiom and rewritten as `math.isnan`/
  `math.isinf` for clarity, no behavior change. `disallow_untyped_defs`
  (full annotation required) now applies per-module via
  `[[tool.mypy.overrides]]` — 10 modules covered so far (`nx_lib/branding.py`,
  `config.py`, `db.py`, `clients.py`, `mapping_config.py`, `ui_prefs.py`,
  `version.py`, `reporting/__init__.py`, `views/__init__.py`,
  `workitems/__init__.py`); the rule (a module never leaves the list, new
  modules ship typed) is documented in `CONTRIBUTING.md`. CI's mypy step
  still targets `nx_lib nx_main.py` — no file under `scripts/` was
  type-annotated as part of this plan, so the CI target was left
  unchanged.
- **`/api/workitems` paging's `total` count is now read off the page query
  itself (`COUNT(*) OVER()`) instead of a second, separate `COUNT(*)`
  query — PostgreSQL (MS02) only.** `PostgresSource.list_workitems` reads
  `total` from the paged query's own `COUNT(*) OVER()` column (falling back
  to the old separate-COUNT query only on an empty page, to keep the exact
  same reported total when the requested offset lands past the end of the
  results); the real round-trip saved here is plausible and has no measured
  regression. `SqlServerSource.list_workitems` was converted the same way
  and then **reverted back to the original two-query form** after isolated
  raw-SQL A/B measurement on a real SQL Server instance showed the
  single-query form is ~12% *slower*, not faster (118.2ms → 132.4ms
  median) — `COUNT(*) OVER()` with no `PARTITION BY` makes the engine build
  a window spool over the whole matching set before it can apply
  `OFFSET`/`FETCH`, pricier than two independent scans on this instance's
  plan. Net effect: SQL Server paging is unchanged from before this plan;
  PostgreSQL paging is one query per page request instead of two.

- **Generali list exports (`?all=true`) are now capped at 100,000 rows.**
  The five generated Generali list endpoints (Attendance, Base Services,
  Project Management, PDQM, Reporting — `nx_lib/views/generali/_crud.py`'s
  shared `_make_list` factory) took `?all=true` literally with no upper
  bound. Below the cap nothing changes (identical rows, identical SQL); only
  a request whose filters match more than 100,000 rows is now truncated to
  the export ceiling instead of returning every matching row. No scheduled
  export script in `ops/`/`scripts/` calls these endpoints — every caller is
  the "Export to Excel" button in the Generali admin UI. The truncation is
  now surfaced instead of silent: a capped response carries `truncated: true`
  and `capped_at: 100000` alongside the (still-uncapped) aggregate/total, and
  `exportToExcel()` in `static/js/generali_crud.js` /
  `static/js/generali_reporting.js` shows an `NX.toast` warning naming the
  row limit when it fires.
- **Eddard now sets `reasoning_effort` per surface on Azure GPT-5
  deployments.** Nothing set it, so gpt-5-mini deliberated at the API default
  (`medium`) on every call — including one-line chart captions. Measured on
  INT (`dbo.ReportingAiAudit`, 235 calls): captions took 8.0 s against
  gpt-4o-mini's 0.9 s, and agent runs 54.8 s against 7.7 s, with the slowest
  run at 210 s brushing the 180 s `AI_AGENT_BUDGET_S` ceiling. Single-shot
  surfaces (caption, definition, sql) now ask for `low`; the agentic chat loop
  keeps `medium`. The parameter is sent only for deployments named `gpt-5*` /
  `o1*` / `o3*` / `o4*` — every other Azure model 400s on it.
- **`nx_lib/views/generali.py` and `admin.py` are now packages.** Each
  ~1.5k–3.4k line module became `nx_lib/views/generali/` and
  `nx_lib/views/admin/` (8 submodules apiece — e.g. `generali/reporting.py`,
  `generali/baseservices.py`, `admin/processes.py`, `admin/organizations.py`,
  `admin/system.py`, `admin/overview.py`); each package's `__init__.py`
  re-exports every public name (including everything the test suite
  monkeypatches) so URLs, endpoint names, and `gv.<fn>`/`av.<fn>` call sites
  are unchanged — no Blueprints, no renames, no behavior change.
- **`nx_lib/views/reporting.py` is now a package.** The ~4k-line module became
  `nx_lib/views/reporting/`, split by feature cluster (`ai.py`, `pages.py`,
  `run.py`, `export.py`, `reports.py`, `schedules.py`, `admin_registry.py`,
  `health.py`, `catalog.py`) plus a shared core (`_shared.py`) for helpers
  used across clusters (e.g. `_load_db_sources()`/`_load_db_metrics()`).
  `__init__.py` re-exports every public name so URLs, endpoint names, and
  monkeypatch targets are unchanged — no Blueprints, no renames, no
  behavior change.
- **`nx_lib/views/workitems.py`'s non-route logic extracted into a new,
  Flask-free package `nx_lib/workitems/`.** Field/table value helpers
  (`fields.py`, incl. `DOCFIELD_OPS`), sensitive-field redaction
  (`sensitivity.py`, incl. `strip_sensitive_fields`), media loading/cache-key
  helpers (`media.py`), and the DB-query helpers behind `_get_workitems_data`
  including the MS02 prepared-docs/pid-spec helpers (`query.py`) now live
  outside the view module. `nx_lib/views/workitems.py` keeps only route
  handlers plus Flask-aware wrapper functions; `nx_lib/views/api_external.py`
  and `nx_lib/views/dashboard.py` are rewired to import the Flask-free
  symbols directly from `nx_lib/workitems/*` instead of through the view
  module. No Blueprints, no renames, no behavior change.
- **Generali's 8 duplicated CRUD endpoint families collapsed into one shared
  factory.** BaseServices, Attendance, ProjectManagement, PDQM, and Reporting
  each carried near-identical copies of monthreport/org-users/organizations/
  filter-users/list/add/edit/delete. `nx_lib/views/generali/_crud.py` now
  generates all eight from a `CrudTable` descriptor (table, permission
  prefix, columns, filters, writable-field validators, and each table's
  historical log-label text, preserved verbatim even where siblings
  disagreed). Every generated view is bound under its original function name
  and re-exported unchanged. **Known gap:** a 175-case parity harness proved
  the migrated BaseServices/Attendance/ProjectManagement tables out before
  this branch, but that harness was not committed — porting it into
  `tests/integration/test_generali_crud_factory.py` is a recommended
  follow-up, since those three tables currently have no automated coverage
  of their own.
- **New `static/js/nx_core.js` shared helper surface (`window.NX`).**
  `esc`/`el`/`api`/`apiSafe`/`toast`/`formatDate`/`formatDateTime`/
  `formatHours`/`csrfToken`, loaded once in `_header.html` before any
  consumer. Landed additively, then the reporting, generali, admin, and
  workitems-overview JS families were migrated onto it one file at a time,
  each verified against its real call sites (the throwing `NX.api` vs.
  non-throwing `NX.apiSafe` flavour was checked per file, not assumed from
  the filename). Net effect: 37 duplicated `API_PREFIX` copies removed, plus
  the `esc`/`el`/`api`/`toast` copies across the reporting JS family and the
  `formatDate`/`formatDateTime`/`formatHours`/`showNotification`/
  `escapeHtml` copies across generali/admin JS. Two deliberate behavior
  changes came out of the dedup, both confirmed with the coordinator before
  landing: `_reporting_drill_js.html`'s local `esc()` under-escaped `"`/`'`
  (unsafe inside a double-quoted HTML attribute) and now uses `NX.esc`'s
  full attribute-safe escaping; and `showNotification`'s top-slide banner is
  replaced everywhere by `NX.toast`'s bottom-center pill (a UI
  consolidation onto one shared notification component, not a
  preserve-exact-behavior swap).
- **New `static/js/generali_crud.js` shared module for the CRUD-clone
  partials.** The `loadRecords`/`canEditRecord`/`canDeleteRecord`/
  `exportToExcel`/`getAddMinDate`/pagination mechanics duplicated across
  BaseServices, AdditionalServices, ProjectManagement, and PDQM partials are
  now one module driven by a per-page descriptor; each of the four partials
  is a thin shim that supplies only its genuinely per-page bits
  (`renderRow`, `buildParams`, modal wiring).
- **Ruff now lints `RET`/`C4`/`PIE` too, and mypy checks for `Any` leaking
  through a typed return.** `[tool.ruff.lint].select` gained the
  flake8-return, flake8-comprehensions, and flake8-pie rulesets; the
  resulting sweep (redundant `else` after `return`, `dict()`/dict-literal
  cleanups, `str.startswith` tuple-arg merges, a couple of missing explicit
  `return None`s) touched ~20 files with no behavior change. `mypy`'s
  `warn_return_any` caught three call sites
  (`nx_lib/mapping_config.py`, `nx_lib/branding.py`, `nx_lib/octo.py`)
  returning an untyped cache/`requests.json()` value through a typed
  signature; each now narrows or casts explicitly. CI's `deploy.yml` now
  also lints `scripts/` and runs `mypy nx_lib nx_main.py` as its own step,
  matching the pre-commit hook that already covered both.
- **The default accent color is now Amber, not Indigo.** Anyone who never
  touched the accent picker on `/appearance`, or who had explicitly picked
  indigo, moves to amber (migration `0083`); explicit dark-mode preferences
  are left alone. The old indigo swatch stays available, now labeled
  "Classic".
- **The pre-push gate no longer runs the e2e suite.** Every push ran all
  ~228 Playwright tests locally even though CI's `test` job runs the full
  suite anyway on the PR and again on `main` before deploy — three runs of
  the same ~12 minutes. Pushes now run unit + integration only (~5 min);
  e2e coverage is unchanged where it gates: nothing merges or deploys
  without the full suite green in CI.
- **6 more JS-heavy partials converted to #191 shims.**
  `templates/js/_workitems_overview_js.html`, `_reporting_js.html`
  (the Advanced tab), `_workitem_detail_panel_js.html` (the panel shared by
  Workitems, Reporting's drill-through drawer, and Prepared Documents),
  `_reporting_viz_js.html`, `_generali_reporting_js.html`, and
  `admin/_access_control_js.html` now hold only a small inline
  `<script nonce>` with Jinja-rendered data/i18n, loaded via `static_v()`;
  their behaviour moved to `static/js/workitems_overview.js`,
  `reporting_advanced.js`, `workitem_detail_panel.js`, `reporting_viz.js`,
  `generali_reporting.js`, and `admin_access_control.js` respectively. No
  behavior change — verified per file against integration tests, a
  Playwright pass on a `--no-conflict` dev instance, and (for
  `admin_access_control.js`, which gates real permission grants) a live
  grant/revoke round-trip on a throwaway test user. Two genuine bugs
  surfaced and were fixed alongside the moves: the workitems overview
  doc-field filter's hardcoded English "No results" string (moved into the
  shim's `I18N` map and translated for de/fr/it), and both `_js.html`
  survivors missing the classic-script IIFE wrap the other four already
  had, a latent global-scope collision risk.
- **`static/js/reporting_simple.js` (~4k lines) split into five files
  behind a new `window.RS` shared namespace.** The monolith's
  `state`/`el`/`api`/`esc`/`I18N` closures became `RS.state`/`RS.el`/
  `RS.api`/`RS.esc`/`RS.I18N` (pure rename, no logic change), then the
  chart/Chart.js layer, the report/dashboard library grid, the KPI/
  anomalies/drill/result-table layer, and the AI-chip + 4-step wizard each
  moved out to their own file (`reporting_simple_chart.js`,
  `_library.js`, `_result.js`, `_wizard.js`), calling back into each other
  through `window.RS` and into the now much smaller
  `reporting_simple.js` core (state, `runCurrent`, `save`, `init`, the
  `window.ReportingSimple` export). `templates/js/_reporting_simple_js.html`
  loads them in dependency order (chart, library, result, wizard, then
  core) after its i18n shim, which stays the first script on the page.

### Removed

- **Recent Validations** and `GET api/dashboard/recent_activity`. The feed
  showed three workitems' extracted fields on a page nobody used it from; the
  workitems page is the place to look at workitems.
- **The dormant `tools/autopilot` orchestrator and its `nx.ps1` CLI
  plumbing.** Unused since 2026-06-15 (owner-approved deletion, recoverable
  from git history); `bin/nx.ps1` loses `--invoke-workflow`, `--kill-workflow`,
  `--workflow-logs`, `--queue`, `--body`, and the in-flight-build line in
  `status`. Everything else in `nx.ps1` is unchanged. This does **not**
  revoke the GitHub PAT exposed in the June transcript — that is a separate
  owner-only action.
- Migration `0082` drops the four synonyms (`SearchConfig`, `StatConfig`,
  `IndexFieldMappings`, `Search_Field_Labels`) hand-added on PROD during the
  2026-08-28 half-deploy rescue (#228). The deployed app reads the new
  mapping tables only; INT never had the synonyms, so the migration is a
  no-op there.

### Fixed

- **Process grants are read in both code shapes.** Migration `0087` (#238)
  replaces the three per-page process families with one
  `process.<client>.<name>.view` code per process. The dashboard, the
  workitems pages and reporting now accept that shape alongside the legacy
  `*.filter.process.*` / `reporting.scope.process.*` codes, so a database on
  either side of the migration shows the right processes. One parser,
  `process_helpers.process_grants`, feeds all of them.
- **Organization brand accents now actually show.** The header let any stored
  accent preference beat the organization's `BrandAccentHex`, and the default
  amber ends up stored for practically everyone (the effective prefs are
  mirrored and re-read), so Privera's teal never appeared. A brand accent now
  wins for every user of that organization; personal picks keep working where
  there is no branding, and the Appearance page shows the brand swatch with a
  note instead of the picker.
- **Tenant groups no longer all light up on the Dashboard.** A mounted custom
  page reuses a global endpoint (every tenant mounts `dashboard`), so a staffer
  who sees several tenant groups by grant saw every group expand and highlight
  its Dashboard entry. A group's mounted pages now count as active only for the
  user's own tenant (`tenant_scoped`); staff get the global link highlighted and
  the groups collapsed, tenant users still get exactly their group.
- **Checkboxes and radio buttons that did not size themselves rendered as a
  2px speck.** The shared chrome in `nexora-ui.css` draws its own box with
  `appearance: none`, which also drops the widget's *intrinsic* size -- so
  every checkbox and radio without an explicit `h-4 w-4` (or equivalent)
  collapsed to little more than its own border: 15 of them, across
  reporting's forecast and share controls, the admin clients / tenants /
  maintenance modals and `user_detail`'s permission-override radios. The base
  rule now sets a 16px `min-width`/`min-height` floor, so callers that size
  themselves still win (the scope picker keeps its 18px boxes, Tailwind's
  `h-4`/`w-4` stay honoured) while unsized ones stop vanishing. The share
  modal's local 15px workaround in `reporting-console.css` is gone with it;
  `.ml-toggle`'s deliberately collapsed switch input opts out.

- **Reporting wizard showed "no measures configured" on PROD for users with an
  ad blocker.** The Simple wizard's metric catalog was served at
  `/api/reporting/metrics`, and EasyPrivacy ships the generic URL filter
  `/reporting/metrics`; uBlock Origin, AdBlock Plus and Brave Shields therefore
  aborted that one fetch (Firefox: "NetworkError when attempting to fetch
  resource") while `/api/reporting/sources` loaded fine, so the Sources rail was
  populated but step 1 of the wizard was empty. Never reproduced on dev or
  staging because blockers leave `localhost` alone, and opening the URL directly
  worked because filter lists only apply to sub-resource requests. The route is
  now `/api/reporting/measures` (the admin CRUD under
  `/api/reporting/admin/metrics` is not matched and is unchanged); a unit test
  keeps every registered rule clear of the `/reporting/metrics` substring. The
  beautification campaign's reporting-package split (below) had already moved
  this route registration into `nx_lib/views/reporting/catalog.py`; the rename
  was reapplied there during the merge.
- **Admin add/edit-user crashed with a 500 on an unknown accessprofile or
  organization** instead of rejecting the request cleanly. Beautification
  Phase 3's `strict_optional` mypy flag (enabled repo-wide) surfaced the
  missing `None` guard around the lookup; the routes now return a 400 for
  an unrecognized accessprofile/org id.
- **`/api/dashboard`'s `set_filter` crashed (500/415) when called with an
  empty JSON body**, because it assumed `request.get_json()` always
  returns a dict. Also surfaced by `strict_optional`; the endpoint now
  falls back to "all" instead of raising.
- **The Simple reporting tab threw on every load.** Beautification Phase 2b's
  wizard extraction (`reporting_simple_wizard.js`) moved a bottom-of-file
  event-listener wiring block that calls `RS.el(...)` at top level
  (module-load time), but `RS.el` is normally set by `reporting_simple.js`,
  which loads *last* (`_reporting_simple_js.html`'s script order is chart,
  library, result, wizard, then core) — so `RS.el` was still undefined when
  wizard.js ran, throwing `TypeError: RS.el is not a function` on every
  `/reporting` page load. Found during the deferred e2e/browser catch-up for
  Tasks 7-8 once INT's SQL Server came back up. Fixed the same way the file
  already handled the analogous `RS.I18N` load-order gap: a same-file
  fallback, `RS.el = RS.el || window.NX.el`. Regression test:
  `tests/e2e/test_reporting_simple.py::test_simple_tab_load_has_no_console_errors`.
- **The Generali dashboard's daily average no longer rewards missing data.**
  `api_generali_stats` built the trend x-axis -- and the average's
  denominator -- from the rows the trend query returned, so days with no
  rows did not exist. July 2026 is missing 11 days (04.07.-14.07.), so its
  119'670 documents were divided by 20 instead of 31: 5'983.5/day, *higher*
  than complete June's 5'715.9 despite 30% fewer documents, with the arrow
  contradicting the total right beside it. The worse a month's coverage, the
  better it scored. Both now run over every calendar day in the selected
  range (`days_in_range()`), so the average reads 3'860.3 and falls with the
  total, and the chart plots empty days as zero instead of drawing 03.07
  adjacent to 15.07 and hiding the outage. The response also carries
  `days_in_range` / `days_with_data` so the UI can qualify the figure
  (#249).

- **A flaky auth test no longer reddens CI at random.**
  `_without_csrf_token()` in `tests/integration/test_auth_routes.py` blanked
  the CSRF token in the `<meta>` tag but not the one in the form's hidden
  input, so the two "a registered and an unregistered address must look
  identical" comparisons failed whenever their two requests straddled a
  1-second boundary — the token is re-signed with an itsdangerous timestamp
  of that granularity. Both spots are blanked now.

- **`scripts/test_db_reset.py` no longer hardcodes ODBC Driver 17.** It now
  picks the best installed SQL Server ODBC driver (18, then 17, then Native
  Client 11.0, then the legacy `SQL Server` driver), so resetting
  `NEXORA_TEST` works on machines that ship Driver 18 only. Previously the
  hardcoded driver made the reset impossible there, failing with `IM002`
  (#230).

- **An aborted deploy can no longer leave PROD's schema ahead of its code**
  (#228). The IIS preflight in `.github/workflows/deploy.yml` ran *after*
  "Apply DB migrations to PROD", so a failure there committed migrations to the
  production database and then skipped the code sync. That is exactly what
  happened on 2026-08-27: two merges applied `0070`–`0081`, aborted at the
  preflight, and left the deployed app querying `SearchConfig` / `StatConfig` /
  `IndexFieldMappings` / `Search_Field_Labels` after `0075` had renamed them —
  taking Workitems "Erweitert", the dashboard KPIs and the reporting catalog
  down until four SQL synonyms were added by hand. The preflight now runs
  before the migration step, so anything that can abort a deploy leaves PROD
  wholly untouched.

  The preflight probe that did the aborting (`waitress.__version__`, an
  attribute waitress does not ship) is fixed separately in #226.

- **The dashboard activity feed no longer dies on a null Octo document.**
  `items_of()` assumed the thin-document JSON was always a dict, so an Octo
  reply of HTTP 200 with a `null` body — or a container whose
  `ChildDocuments` carried a null entry — raised `'NoneType' object has no
  attribute 'get'` from outside the caller's `try`, blanking the whole feed
  instead of skipping the one bad workitem. Non-dict input now yields no
  leaves. The handler also logs a traceback, since the bare message named
  neither the file nor the workitem (#228 follow-up).

- **Test runs no longer corrupt each other's shared database.** One
  `NEXORA_TEST` is shared by CI and every local run, and both the pre-push gate
  and CI's `test` job reset it — so two overlapping runs re-seeded `dbo.Users`
  under one another and a random login fixture died with `KeyError: 'userid'`
  or a stray 401. A different test each time, always passing in isolation,
  never pointing at the cause; it cost five failed CI runs in one day and
  blocked two PRs that were entirely correct. Both the reset script and the
  pytest session now take an exclusive `sp_getapplock` on `nexora_test_suite`
  (`scripts/db_lock.py`), so the second run waits instead of trampling.
  `NEXORA_TEST_LOCK_SKIP=1` bypasses it, `NEXORA_TEST_LOCK_TIMEOUT_MS`
  overrides the 20-minute wait, and a run that cannot reach the database
  doesn't lock at all. See CONTRIBUTING.md and #235.

### Known gaps carried out of this campaign (not fixed here)

- An unauthorized target-user booking in generali's add endpoints returns a
  generic 500 instead of a 403, because `PermissionDenied` is raised inside a
  bare `except Exception` block. Pre-existing, left alone per scope
  discipline — now fixable in one place (`_crud.py`) instead of five,
  worth its own issue.
- `templates/js/admin/_user_management_js.html` appears to be genuinely
  dead/unreferenced code — a candidate for a future cleanup pass.

## [3.2.3] - 2026-08-27

### Added

- **Reporting: click a source to see inside its database.** The Console's
  Sources rail cards are now buttons that open a source visualizer — a
  filterable list of every table (row count, columns, types, primary and
  foreign keys) and an ER diagram drawing the foreign keys as arrows between
  table boxes, with pan, zoom and Fit. Clicking a box, or a column's 🔗,
  jumps to that table in the list. Structure only — no data rows are read.
  Served by `GET /api/reporting/sources/<id>/schema`
  (`nx_lib/reporting/db_schema.py`), on the same engine the source already
  uses, behind the new `reporting.sources.schema` permission
  (migration `0079`, seeded to profiles that hold `admin.view`) *and* the
  source's own permission — so it never widens which databases a user reaches.
  The panel shows **only the tables the source actually reads** — the ones its
  registry names (`BaseObject` / `dbo.ProcessSources.TableName`), plus whatever
  a used view reads and one foreign-key hop off them; the header says how many
  tables were hidden. A source whose SQL is hand-written falls back to hiding
  empty tables. View→table dependencies are drawn as dashed edges, so a
  view-backed source shows what it is built on.

- **Reporting dashboards: one-dialog "Add a card".** The add-card tile's type
  pills are replaced by a single mask (`rdb-add-mask`) that asks for everything
  at once — which saved report to show, how to draw it (KPI / chart / donut /
  table / whole report), the card title, and the card size as a width in grid
  columns plus a height in rows, sketched live as the sliders move. The card
  lands fully configured instead of as a placeholder that had to be clicked to
  reach the saved-report picker. Submitting with no report selected still adds
  the blank "configure this card" placeholder, so an empty report library is
  not a dead end.

- **Reporting dashboards: resizable cards.** Cards now carry a `rows` height
  alongside their `span` width, both drag-resizable from a card's bottom-right
  corner grip (Pointer Events, no library): width snaps to the 12 grid columns,
  height to whole grid rows (max 6). Charts re-fit themselves as the container
  changes. Saved dashboards without `rows` fall back to a per-type default
  sized to the heights those cards already had, so existing dashboards reopen
  unchanged.

- **Self-service client/process onboarding admin UI** (#98 phase 4). A new
  `dbo.Clients` runtime-source registry (migration `0079`) replaces the
  hardcoded `CLIENTS` dict in `nx_lib/clients.py`, seeded from today's two
  values (`default`, `ms02`); a new client still needs an app-pool recycle
  to take effect. New pages `/admin/clients` (CRUD over the registry, with
  delete refused when a `ClientCode` is still referenced by
  `dbo.ProcessSources`) and `/admin/processes` (view/edit `ProcessSources`
  and their field mappings per client through the cached
  `nx_lib/mapping_config.py` registry, with strict identifier validation on
  every value interpolated into SQL). `ProcessName` must be exactly
  `<customer>.<process>` — the permission that grants access to a process is
  derived from those two dot-segments, so any other shape could never be
  granted (and a three-segment name could piggyback on another customer's
  grant); a name whose two-segment reduction already belongs to another
  process is refused with 409. `ClientCode` is picked from `dbo.Clients`
  and checked server-side, so a typo can no longer create config that never
  resolves. `/admin/clients` shows resolved state next to configured state —
  a row the running registry did not load reads "Configured, not loaded" —
  and a boot-time `dbo.Clients` failure (which silently drops every
  non-`default` runtime for the process lifetime) now raises a banner on
  `/admin/clients` and `/admin/status` instead of only a stderr line written
  before logging was configured. Adding a process source
  auto-provisions its `workitems.filter.process.<name>` permission,
  granted to nobody until deliberately assigned at `/admin/access-control`;
  every write invalidates the mapping-config cache. New permissions
  `admin.view.clients`, `admin.edit.clients`, `admin.view.processes`,
  `admin.edit.processes` (migration `0080`), granted to `enterpriseAdmin`
  and `globalAdmin`; the same migration also seeds
  `admin.edit.organization.branding`, now in use by the branding panel below.
  Onboarding a customer riding the shared `default`
  runtime is now fully self-service — no migration, no deploy. See
  `docs/howto/white-label.md`.

- **Per-organization branding panel** (#98 phase 4). `/admin/organizations`
  gained a branding panel — brand name, accent colour and logo — behind the
  `admin.edit.organization.branding` permission (the panel and its per-row
  button are hidden entirely from a viewer who only holds
  `admin.view.organizations`). Branding attaches to the customer
  organization, never to a runtime `ClientCode`. Uploads are MIME-sniffed
  with libmagic through `nx_lib/files.py::is_file_allowed` (never the
  client-declared content type), capped at 512 KB, restricted to SVG/PNG/JPEG
  and stored as `var/branding/<orgcode>.<ext>`; `deploy.yml` already excludes
  `var/` from the robocopy mirror. Every successful save invalidates the
  60-second branding cache so the edit shows up immediately.

- **Per-organization white-label branding applied in the app** (#98 phase 4).
  Migration `0081` adds nullable `BrandName` / `BrandAccentHex` /
  `BrandLogoFile` to `dbo.Organizations`; `nx_lib/branding.py` reads them into
  a 60-second, success-only cached registry (`brand_for_org()`,
  `invalidate_branding()`) whose load errors return `None`, are never cached,
  and degrade the caller to Nexora branding. A context processor injects the
  viewer's organization brand fresh per render — never cached in `session`
  (#155) — so the header/sidebar shows the org's logo and wordmark when set and
  today's exact markup when not. **The organization accent is a default, not an
  override:** a user's own `/appearance` accent still wins, and the org accent
  only replaces the built-in `indigo` / `#4f46e5`. Logos are served from
  `GET /branding/<orgcode>/logo` with `Content-Security-Policy: sandbox` and
  `X-Content-Type-Options: nosniff`, because SVG is allowed and is
  script-capable. It is served with a one-hour `max-age` and skipped by the
  per-request hooks the same way `/avatar/<id>` is — the header fetches it on
  every page load of a branded org, which would otherwise double the request
  log and skew `/admin/logs`. The login page, the error pages and scheduled-report emails
  stay Nexora-branded by design — login is pre-session, so there is no user and
  therefore no organization; the context processor is gated on a logged-in
  session, because `logout()` leaves `organizationcode` behind and keying on it
  alone kept branding the landing page (with a broken logo `<img>`) after
  logout. See `docs/howto/white-label.md`.

- **Sidebar restyled toward a minimal, GitHub-inspired look** (#213). Same
  icons and labels, different treatment: the active page is marked by a thin
  accent-coloured bar on the left edge instead of a filled accent-tinted
  pill, and icons/text stay neutral gray (idle) / near-black (hover,
  active) in every state — the user's configurable accent colour now shows
  up in exactly one restrained place instead of painting the whole row.

- **Clear button on the document-value filter's first row** (#185). Added
  filter rows already had an "x" to remove them; the fixed first row (it
  always exists, so it can't be removed the same way) had no way to reset
  itself once filled. It now gets the same "x", shown only once the row
  actually has a field or value to clear, and clears field/operator/value
  back to defaults instead of removing the row.

- **Keyboard shortcut cheatsheet overlay** (#173). Pressing `?` outside an
  input field (or picking "Keyboard shortcuts" from the profile dropdown)
  shows every shortcut the app actually has: the `Ctrl`/`⌘`+`K` command
  palette, `Esc` to close a dialog, `?` itself, and — on the pages that embed
  the document viewer (Workitems, Reporting drill-through, Prepared
  documents) — `←`/`→` to page through a document's images. Content is
  static markup in `_header.html`, not scanned from the JS: adding a
  shortcut later means adding a row, on purpose, so the list can't silently
  drift from what's actually wired up.

- **Admin permission matrix** (#172). Read-only `/admin/permission_matrix`
  page answering "who can see reporting?" / "what can this user open?"
  without SQL against `spGetUserPermissions`'s tables directly: toggle
  between picking a permission code (every holder, override vs. profile) or a
  user (their effective permissions, grouped by family). Reuses the existing
  `effective_permissions` resolution logic and links each row through to
  Access Control / the user's overrides tab — granting and revoking stays
  there.


- **Responses are gzipped.** Nexora ships each page's JavaScript inline (the
  `templates/js/*.html` partials), so an HTML response is the whole client for
  that page — `/reporting` is ~620 KB — and none of it was compressed. Flask
  does nothing by default, and IIS could not cover for it: `web.config` maps
  `path="*"` to HttpPlatformHandler, so *every* request, `/static` included, is
  proxied to waitress rather than served (and compressed) by IIS.
  `nx_lib/compression.py` is one `after_request` hook over the stdlib's `gzip`,
  registered first so it runs last. Measured on INT: `/reporting` **172 KB
  instead of 625 KB** (‑73%, ~24 ms of CPU) and `reporting.css` **30 KB instead
  of 124 KB**. Only text types, only bodies over 1 KB, only a bounded
  (< 2 MB) `send_file` body, never a genuinely streamed one; `Vary:
  Accept-Encoding` is set whether or not the body ends up compressed, and the
  `ETag` is left alone so `If-None-Match` still answers 304.

- **Dashboard cards in the reporting library preview their real layout.** A
  dashboard's library card used to show a generic 2×2 placeholder; it now draws
  a miniature of the dashboard itself — the actual cards packed into their
  12-column rows, each tile carrying a small glyph for its chart type (KPI,
  line, bar, donut, table, whole report) — plus a card-count fact, so
  dashboards can be told apart before opening one. The list endpoint's
  server-computed summary now carries the compact card layout for
  dashboard-kind reports; an empty dashboard keeps the old placeholder.
- **Eddard, the reporting mascot** (#212). The AI assistant now has a face and a
  name: an animated version of the Nexora black-hole logo — black core, accent
  accretion ring, two dot eyes — who floats, blinks, looks around, winks and
  hops through the reporting AI surfaces (top-bar toggle, chat header, empty
  thread, the Simple tab's insight card). While a question is running he builds
  a placeholder report piece by piece — title, KPI, bars, trend line, a green
  *Ready* badge — above the real agent steps. The visible AI wording is rebranded
  with him ("AI chat" → **Eddard**, "AI insight" → **Eddard insight**), and his
  accent follows the user's accent picker while the core stays black in both
  themes. Decorative and `aria-hidden`; `prefers-reduced-motion` holds every loop
  on its resting frame. New `templates/_eddard.html`,
  `templates/js/_eddard_js.html`, `static/css/eddard.css`; design source is
  `docs/design/design_handoff_eddard_mascot/`. He since gained the rest of the
  handoff's personality — drifting ambient sparks and pointer-following eyes on
  the big chat mascot, a hover perk-up on the small marks, and per-piece
  build choreography (a fling as each report piece lands, a card settle, an
  orbiting spark while working, the celebrate pose on *Ready*) — and his mock
  report is no longer mock: the agent stream distills each tool result into a
  compact preview (`stage_preview`), so the title, total, bars and trend he
  animates while you wait are the real numbers of the answer being built.
- **Response-time sparklines on the admin status page.** Each component row now
  carries a 24-hour latency graph beside its uptime strip, drawn from the new
  `dbo.StatusSamples` table (migration `0071`) that the outage monitor fills
  from the durations it already measured and previously discarded. Inline SVG,
  no chart library: zero-based axis scaled per component, one bucket per hour
  keeping its slowest sample, gaps left as gaps, and failed probes marked with a
  square as well as a colour — and *named* in the tooltip and `aria-label`, so
  the anomaly survives a screen reader and a greyscale print. The HTTP, API,
  Graph and Octo probes now append their own `(204 ms)` timing so they are
  graphed too.
- **The outage monitor watches `WARNING` storms.** Previously only
  `ERROR`/`CRITICAL` signatures could open an incident, so a fault that merely
  warns was invisible — the reporting catalog warned on every request for months
  with nothing watching. Warnings get their own much higher bar (60 in 15 min vs
  10) and are labelled `warn storm @ <site>`.

- **Reporting "Console" redesign.** The `/reporting` page is now a workbench
  shell (design handoff `docs/design/design_handoff_reporting_console/`):
  compact top bar, persistent left rail with a Workspace nav (Library /
  Results / Dashboards / Scheduled / Advanced) and a live sources rail
  (status dot + latency via the new `GET /api/reporting/sources/health`),
  replacing the Simple/Advanced tab strip and the landing hero + global
  Ask-AI bar (AI lives in the chat panel). Library gains search + sort + a
  2-or-4-cards-per-row toggle and compact cards with an owner `…` menu
  (Share / Delete); the result view gains a breadcrumb + Saved chip, a Run
  again button, a flat KPI card row, and a side column with the AI-insight
  and always-visible syntax-coloured Query cards; the wizard gains
  horizontal step chips + a "So far" summary; **Results** restores the last
  rendered result from cache without re-querying. New **Scheduled** screen
  lists every owned schedule across reports (new
  `GET /api/reporting/schedules`) with on/off toggles and a New-schedule
  modal. Styling in the new `static/css/reporting-console.css`, riding the
  design-system tokens (accent picker + dark mode included), typeface
  Schibsted Grotesk.
- **The AI chat agent can execute a report definition, not just validate it.**
  A new `run_definition` tool (bound alongside `run_sql`, behind
  `reporting.ai.explain_data` + `reporting.sql.run`) runs a `build_definition`-
  shaped definition for real — the same query the report builder would run —
  and hands the rows back to the model, capped to 500. Previously a
  `build_definition` call only validated the shape, so a question needing
  concrete numbers (imported/exported/backlog, or any other business-metric
  question) ended with "definition built, numbers not run" instead of an
  answer.
- **PROD diagnostics workflow.** `.github/workflows/prod-diagnostics.yml` is a
  manual, read-only sweep of SYAPP01 — `app.log` tail, IIS app-pool/site state,
  PROD env key names (never values), disk/uptime, outage-monitor state — run on
  the `self-hosted` runner that already executes on the box. It exists because
  WinRM to PROD is blocked by the VPN/network ACL; it takes no command input.
- **WinRM access to PROD documented.** `docs/howto/winrm-prod-access.md`
  covers the one-time `Enable-PSRemoting` setup on SYAPP01 plus the firewall
  scoping, so log tails, app-pool checks and env-key audits can run remotely
  instead of needing an RDP session. Only 445 (SMB) and 3389 (RDP) were open
  before.
- **Cloudflare Tunnel runbook, prepared for the ngrok replacement.**
  `docs/howto/cloudflare-tunnel.md` documents the remotely-managed tunnel
  (token-only install on SYAPP01, hostname `nexora.sydoc.ch` -> local IIS,
  Bot-Fight-Mode caveat for `/api/v1` clients, verify/cutover/rollback), and
  the deploy workflow now stops/starts whichever of the `ngrok`/`cloudflared`
  Windows services exists, so deploys behave identically before, during and
  after the cutover. ngrok remains the live entry until then
  (`docs/howto/ngrok.md` carries the deprecation banner).
- **Colours & axes on Simple-tab charts.** A palette button in the chart
  toolbar opens a popover with one colour picker per series, one for the
  report title + legend, and a *Right axis* toggle per series so a level-type
  measure (backlog in the hundreds) no longer flat-lines beside imports in
  the tens of thousands — *Backlog* defaults to the right axis when it shares
  a chart with other measures. Picks are saved with the report
  (`definition.style`, validated hex-only in `nx_lib/reporting/schema.py`).
  Scheduled-mail PNGs and the Advanced tab keep the default palette.
- **Delete reports from the Simple tab.** Owned cards under *My reports* get a
  hover trash button, and an open saved report has *⋯ → Delete report*; both
  confirm first and call the existing owner-scoped
  `DELETE /api/reporting/reports/<id>`. Until now deleting was Advanced-only.

### Changed

- **Reporting dashboards: drag-to-rearrange previews the real layout.** The
  dragged card is spliced into its landing position as you hover, so the grid
  itself is the preview and its dashed outline sits where the card will end up;
  the whole card is now grabbable, with a `grab` cursor, rather than looking
  static. Drop only clears the drag state.


- **Dev-structure leftovers from the 2026-05 dev-env upgrade closed out**
  (#108). The camelCase template render kwargs the PR 6 handoff deferred are
  now snake_case (`pageV` -> `page_visibility`, `startDate`/`endDate` ->
  `start_date`/`end_date`), and the five endpoint names PR 5 deliberately kept
  camelCase as a compat surface were renamed too (`init_2FA` -> `init_2fa`,
  `generali_baseServices` -> `generali_base_services`, and the additional
  services / project management / import status siblings). Public URL paths are
  unchanged - the rules are declared explicitly, so only `url_for()` keys moved.
- **mypy is a blocking pre-commit hook** (#108). It was wired in as advisory
  (`stages: [manual]`) and never enforced. The 13 outstanding errors are fixed,
  `types-requests` joins the dev dependencies, `strict_optional = false` is
  recorded in `pyproject.toml` instead of being passed as a hook flag, and the
  hook now runs from the project environment so a local `mypy nx_lib nx_main.py`
  and the hook agree.
- **Doc-field suggestion endpoints read the mapping_config registry; `col_`
  prefix retired** (#98). `/api/docfield_values` (both the field-specific and
  value-first "any field" paths) no longer query `SearchConfig` directly —
  they resolve through `nx_lib.mapping_config`, like the search-filter
  resolution paths already did. With every `SearchConfig` read gone from
  `nx_lib/views/workitems.py`, `get_valid_search_columns()` and
  `get_search_columns_for_processes()` now return bare lowercase field keys
  instead of `col_`-prefixed ones — the last step of the two-phase migration
  off the legacy naming convention; `nx_lib/views/api_external.py` updated to
  match. The 600s suggestion caches and their key shapes (which encode the
  sensitive-permission column set) are unchanged.
- **Schema hygiene: `StatConfig` gets a primary key, `Logs` gets a timestamp
  index** (#98, migration `0073`). `StatConfig` was a PK-less heap with a
  nullable key column — now `ProcessName` is `NOT NULL` with a composite PK on
  `(ProcessName, ClientCode)`. `dbo.Logs` gains `IX_Logs_Timestamp` so the
  admin log pages stop table-scanning as the log grows.

- **`CLAUDE.md` is now a map, not a manual.** It is injected into every Claude
  Code session and re-sent after every compact, so its 28 KB of prose was a
  fixed per-session token cost. The architectural-conventions block moved
  verbatim to `docs/design/architecture-conventions.md`, the Databases section
  dropped the ~5 KB it duplicated from `docs/howto/db-migrations.md`, and the
  translations and GitNexus blocks became pointers. 28,069 -> 14,361 bytes with
  no content lost, only relocated; the Git branch policy is kept verbatim.
- **Normalized mapping schema live, legacy tables decapitated** (#98,
  migrations `0074`/`0075`). Every Python consumer of the doc-field/process
  mapping config now reads the single cached registry in
  `nx_lib/mapping_config.py`, backed by the normalized `dbo.ProcessSources` /
  `ProcessFieldMappings` / `FieldLabels` / `FieldAliases` tables (`0074`).
  With the cutover verified clean across the whole tree, migration `0075`
  renames the four legacy tables (`SearchConfig`, `StatConfig`,
  `IndexFieldMappings`, `Search_Field_Labels`) to `decapitated_*` — data is
  preserved, not dropped, following the same reversible pattern `0042` used
  for the chat/collaboration tables (later dropped for good by `0072`).

- **Doc-field search performance: sargable predicates, seeded column types,
  a short-lived allow-set cache, and a batched source-routing cache** (#98,
  migrations `0076`–`0078`). `ProcessSource.id_column_type` is now seeded
  from the live target DBs (`0076`, refined by fixup `0077`) so
  `_ms02_columnar_sql` can emit a sargable comparison instead of an
  unconditional `::text` cast on every row. Resolved doc-field allow-sets are
  now cached for 60s per (client, field-spec, value) — repeat identical
  searches skip re-querying MS02 entirely; the trade-off is that a workitem
  imported in the last 60s can be briefly missing from a repeat of the exact
  same search (accepted). `WorkitemSourceCache`'s primary key widens from
  `(WorkItemID)` to `(WorkItemID, ClientCode)` (migration `0078`) since ids
  collide across clients (1216 on INT) and a single-column PK could only ever
  pin one client per id; `fetch_merged_page`'s cache-warm loop replaces up to
  1000 sequential per-row lookups with one batched `_cache_lookup_many` call
  per page, falling back to `get_source_for_workitem` only for ids missing
  from the batch. Both `_cache_lookup` and `_cache_lookup_many` mirror
  `get_source_for_workitem`'s existing collision fail-safe: more than one
  row for an id is ambiguous and is never guessed — it's omitted (forcing a
  re-probe) with an error logged.


- **The three biggest JS partials now ship as cacheable static files** (#191).
  Nexora's per-page JavaScript lived inside Jinja partials only because that
  was the way to get Babel to translate its strings — which turned every
  navigation into a re-download and a re-parse of the whole client, since a
  script inside the document can never be cached. It didn't have to: the
  partials already funnel every translated string through one `I18N` object
  literal at the top, so the literal can stay in Jinja and the behaviour can
  leave. `_reporting_simple_js.html`, `_reporting_dashboard_js.html` and
  `_header_js.html` now keep a small inline `<script nonce>` holding only the
  Jinja-rendered data — the strings, `url_for()` endpoints and the
  permission-filtered Ctrl+K command list — and load their body from
  `static/js/reporting_simple.js`, `static/js/reporting_dashboard.js` and
  `static/js/header.js`. **290 KB of JavaScript left the document**:
  `/reporting` now renders 333 KB of HTML with 260 KB of inline script,
  against ~620 KB / 549 KB before, and what moved is cached across
  navigations and across pages. Babel is untouched — `babel.cfg` still
  extracts from `templates/**.html`, so `messages.pot` and the three `.po`
  files are byte-identical. New Jinja global `static_v()` appends an mtime
  `?v=` so a deploy busts the cache; `tests/unit/test_template_url_prefix.py`
  now also lints `static/js/` (a `.js` file has no `url_for()` to fall back
  on) and fails on any Jinja syntax left in a static file. As a side effect
  `_header_js.html` no longer injects a stray `<!DOCTYPE html><html><head>`
  block into the middle of every page.

- **Dashboard "Whole report" tile.** The Report tile on a reporting dashboard
  now renders the saved report as the Simple tab does — the KPI band with one
  labelled total per measure and prior-period chips, the chart with its saved
  axis and forecast, and the full table behind *Show table* with row
  drill-through — instead of a single total and one line. It draws through
  the Simple pane's own builders (`window.ReportingSimple`), so the two
  surfaces can no longer drift apart. Existing dashboards upgrade in place.
- **Every reporting total says what it is a total of.** The Simple and Advanced
  KPI bands showed a bare *Total* — on a multi-metric report that number was
  whichever metric happened to come first, with nothing on screen saying which,
  so an imported+exported report read as though one of the two were the
  report's grand total. The band now renders **one labelled total card per
  metric** (`Total · Documents imported`, `Total · Documents exported`, …), with
  Buckets / Avg per bucket / Peak grouped under a heading naming the measure
  they describe. Metric result columns are headered from the metrics registry
  server-side (`metric_result_columns`), so the table, the KPI band, exports and
  scheduled mails all read *Documents imported* instead of `docs_imported`.
  Three related fixes came with it: totals now come from the authoritative
  zero-column grand-total run rather than a client-side sum of the grouped rows
  (which was only ever right for additive metrics), each metric honours its
  **own** total mode so a levelled backlog reports its latest snapshot beside a
  summed count, and a *just the total* report no longer prints "Buckets 1, Avg
  per bucket N, Peak N" — the same number three more times. The separate
  `rsStatCard` that repeated the grand totals above the band is retired.
- **Permissions and UI prefs come from a 30-second per-process cache instead
  of two DB round-trips per request.** Every non-static request used to run
  `spGetUserPermissions` and `SELECT ui_prefs` for the user — at ~500 users
  that was the biggest DB-load multiplier (each click, each 5 s heartbeat).
  `nx_lib/user_cache.py` caches both per user (`NEXORA_USER_CACHE_TTL`,
  default 30, `0` disables); a user's own pref save and any admin write drop
  the affected entries immediately, so changes still show on the next
  request. Safe because PROD is a single waitress process — it is a process
  dict, deliberately not a session cache (the heartbeat/cookie race, #155).
- **The per-request `ActiveSessions` UPDATE is throttled through the same
  cache.** Profiling showed it was the hottest per-request cost (~70 ms of a
  75 ms heartbeat: UPDATE + commit every request). The alive-check is now
  cached per session id for the TTL; admin force-logout still takes effect on
  the revoked user's next request (any `/admin` write clears the cache), and
  `LastSeenAt` in the admin sessions view lags activity by at most the TTL.
- **The session-liveness heartbeat polls every 30 s instead of every 5 s.**
  Its only job is noticing an admin force-logout, and the server now answers
  that from the 30 s cache anyway — polling faster could not detect it
  sooner. At ~500 users the 5 s poll alone was ~100 requests/s of overhead.
- **Colours & axes popover polish.** The per-series *Right axis* checkbox is a
  **Left | Right** switch; each Y axis is titled with the series it carries and
  takes that series' colour when it carries exactly one; colour-picker drags
  re-render at most once per frame. The forecast is drawn as translucent bars
  on bar charts (dashed tails only on line charts), its toggle is tinted while
  on and greyed out on pie/doughnut, and switching it **off** repaints from the
  last result instead of re-running the query.
- **PROD now runs on waitress behind IIS HttpPlatformHandler, not wfastcgi.**
  `web.config` starts one `python -m waitress` process (32 threads, loopback
  port picked by IIS) and reverse-proxies to it; `wfastcgi` — archived
  upstream, one blocking request per process — is gone. Motivation: the
  expected jump to ~500 users, where a handful of slow reporting queries
  would have starved the FastCGI pool. `waitress` joins the runtime
  dependencies; the deploy workflow gains a preflight that refuses to stop
  the app pool unless the HttpPlatformHandler IIS module and `waitress` are
  present on SYAPP01 (one-time host setup in `docs/howto/iis.md`). Rollback
  is reverting the commit — `wfastcgi` stays installed on the box.
- **Rate limits are keyed on the client IP behind the proxy chain.** The
  limiter now reads the leftmost `X-Forwarded-For` hop (the same rule the CSV
  request log uses) instead of the socket peer, which behind ngrok → IIS →
  waitress is always `127.0.0.1` — i.e. one shared *10 logins per minute*
  bucket for everybody. `web.config` tells waitress to trust
  `X-Forwarded-For` from IIS so the header survives (waitress ≥ 2 strips
  proxy headers from untrusted peers).
- **The branch-name guard accepts a fourth version segment.** Cycle branches
  are still `v<x.y[.z]>`, but a per-developer branch off a cycle
  (`v3.2.3.1` beside `v3.2.3`) now passes `scripts/git-hooks/branch-name-guard.ps1`
  instead of needing `git push --no-verify`. `CONTRIBUTING.md`'s branch list was
  stale — it still advertised `fix/…`, `chore/…` and `hotfix/…` prefixes the
  guard has always refused — and now describes what actually pushes.

### Removed

- **Dead `decapitated_*` tables dropped for good** (#98). Migrations 0042 and
  0056 had renamed the ten dead chat/collaboration/notification/invoice tables
  with a `decapitated_` prefix as a reversible safety net; nothing has read
  them since, so migration `0072` deletes them (data included). The archived,
  never-registered `nx_lib/views/invoices.py` and the `templates/archive/`
  invoices/chat templates went with them.

### Fixed

- **`scripts/test_db_reset.py` wipes NEXORA_TEST before applying the schema.**
  The reset relied on a hand-maintained FK-safe `DROP TABLE` order inside
  `sql/test/schema.sql`, which cannot know about tables it has never heard of:
  a table another branch had applied its own migration for (`dbo.Clients`,
  `dbo.KundenmagazinIssue*`) held a foreign key into `dbo.Organizations` and
  wedged every reset with *"Could not drop object 'dbo.Organizations' because
  it is referenced by a FOREIGN KEY constraint"* — leaving the test database
  half-applied and the integration suite failing on missing permissions. The
  script now drops every user object (foreign keys first, then views, tables,
  procedures and functions) before applying `schema.sql`, re-checking
  `DB_NAME() = 'NEXORA_TEST'` on the live connection first. Third time this
  drop list has broken; it no longer needs maintaining.

- **`ActivityInstancesToIgnore` rules were applied globally instead of
  per-process.** The table has a `ProcessName` column precisely so an admin
  can hide a `Deletion Marker`-style activity on one process without
  affecting another, but the loader read `ActivityInstanceName` only and
  discarded `ProcessName` — every configured rule was silently OR'd across
  every process's workitem list and Recent Validations feed. The predicate is
  now built per `(client, process)` (`_activity_ignore_predicate` in
  `nx_lib/workitem_sources.py`), and is fully parameterized instead of
  string-spliced into the SQL (no more manual quote-escaping).

- **Reporting library: dashboard cards said "Delete report"** (#214). A
  library card's `…` menu now reads "Delete dashboard" when the card is a
  dashboard (`r.kind === 'dashboard'`), matching the "DASHBOARD" tag already
  on the card.

- **Workitem detail panel: line-item tables are tables again** (#199). Each
  extracted table (`TabVat`, `TabOrder`, …) was rendered as a stack of
  label-over-value rows inside the narrow Document Details column, so line-item
  rows could not be compared at a glance. They now render as a real `<table>`
  — one row per line item, collapsible per table — in their own full-width card
  below the two-column detail grid, with horizontal scroll for wide SAP-style
  grids. In the document lightbox they get their own box under the page image,
  spanning the page pane instead of being squeezed into the 480px values
  sidebar. Click-to-locate on a cell is unchanged; empty cells show an em dash
  instead of a "no source location" badge per cell.

- **Workitems loading state: cramped spinner row → accent-tinted skeleton rows**
  (#189). The loader was a single Font Awesome dot-spinner in a row squashed to
  12px padding (the unlayered `.nx-table tbody td` rule beats Tailwind's
  layered `py-20`), and until v3.2.3 it was hardcoded indigo. The table now
  shows six shimmering skeleton rows shaped like real workitem rows, tinted by
  the user's accent color and frozen under reduced motion; both the initial
  page load and every filter refetch share one server-rendered template
  (`#workitemsSkeletonTpl`).

- **The reporting page fetched the same catalogs eight times per load.** Its
  five modules (tabs rail, Simple, Advanced, dashboard builder, drill drawer)
  are separate IIFEs that can't read each other's state, so each fetched its
  own copy: `GET /api/reporting/sources` **three** times and
  `/api/reporting/metrics` **three** times on a single visit, serialised one
  behind another — and one of those `/metrics` calls, in the dashboard
  builder's `ensureCatalog`, was never read at all (its own comment said so).
  Both read-only registries now come from one shared in-flight promise
  (`window.ReportingCatalog`, `templates/js/_reporting_catalog_js.html`), so a
  page load makes one request each. Measured on INT: 8 API requests → 6, and
  the catalogs stop queueing behind one another. `/api/reporting/reports` is
  deliberately left alone — it changes on every save/rename/delete.

- **Saving a report in the Console duplicated it instead of updating it.** Save
  in the results view always `POST`ed a new row, so pressing it on a report you
  had opened from the library left two identical entries under My reports — and
  the rename pencil was the same code path, so renaming forked a *second* copy
  under the new name while the original kept the old one. Save now writes back
  (`PUT`) whenever the open result is a stored report you may edit — owner or
  CanEdit share — and the pencil renames that same report in place. Making a
  new one is now the explicit path: ⋯ → **Save as copy**, which pre-fills
  `"<name> (copy)"` and then leaves the copy open, so the next Save can't reach
  back to the original. A result that isn't a saved report yet (wizard run, an
  answer from Eddard) still asks for a name and creates one.


- **Fireflies now tint with the chosen accent color.** The `fireflies`
  background option used a hardcoded teal/amber dot color instead of
  following the user's accent choice (preset or custom). The dots and
  their glow now derive from `--nx-accent`, so they match whatever accent
  is active, light or dark mode included (#210).

- **Feedback page header didn't line up with the feedback card.** The
  header markup was copied from the Appearance page but never linked
  `appearance.css`, so the "Back to profile" link had no margin below it
  and the title/lede weren't width-constrained to match the card below.
  Gave the header its own scoped styles instead (#211).

- **A report shared with named colleagues now looks shared to its owner.**
  Only `Visibility='shared'` was ever surfaced, so a report shared by explicit
  per-user grant (which deliberately leaves `Visibility='private'`) was
  indistinguishable from a private one in the Simple library and the Advanced
  dropdown — the share was saved, it just never showed. `GET
  /api/reporting/reports` now returns an owner-only `sharedCount` and both
  panes tag the report `· shared`. Named shares stay on the **My reports**
  shelf; the **Library** shelf remains org-wide visibility only.

- **Reporting catalog stopped flooding `app.log`.** `fetch_docprocessing_catalog`
  logged `reporting catalog: FieldMetadata unavailable` at WARNING on *every*
  reporting request. The table has never existed in any environment — the
  customizable-widget engine that owned it was removed in 2.5.65 — so the miss is
  permanent and the warning was pure noise, thousands of identical lines a day on
  PROD. It now reports each missing optional table once per process, and includes
  the driver's message so a *new* cause (permission revoked, column dropped) is
  distinguishable from the expected "table does not exist".

- **The AI caption ("KI" box) narrates the whole result, not its first 50
  rows.** The caption route used to send the model `rows[:50]` off the top of
  the grid — for a time series sorted ascending that is the NULL-date bucket
  plus the oldest weeks, hence captions such as "a clear outlier of 74,182
  pages" (the rows with no date) and "at most 3,712 pages in the latest
  weeks" (it never saw them). The server now reduces the complete grid to an
  exact fact sheet — total or latest level, buckets with vs. without a value,
  peak/low, latest vs. previous, half-vs-half trend, recent tail, top
  categories, rows without a date named as such, the running bucket flagged
  and kept out of the comparisons — and the model writes at most two
  sentences from those numbers only (`nx_lib/reporting/caption_facts.py`).
- **Time charts no longer invent the future or read a half month as a
  collapse.** The Simple tab's bucket fill stops at today (*This year* = Jan
  to the current month, not Jan–Dec zeros), the bucket containing today is
  drawn faded/dashed with a "still running" note, the forecast fits on
  finished buckets only and projects from the next one, and a bucketed date
  axis may carry up to 400 points (53 weeks charted, not "too many points").
- **Backlog is treated as a level.** `dbo.ReportingMetrics.TotalMode` for the
  anchored `backlog` measure is `latest` (migration `0070`), so the Total card
  shows the newest snapshot instead of summing every month; buckets without a
  snapshot come back `NULL` from the query (gap in the chart, skipped by the
  KPI cards, carried forward by the forecast) instead of a fake `0`.
- **AI grounding for imported / exported / backlog.** The agent prompt no
  longer claims the builder can't put differently-dated measures side by side;
  anchored metrics are marked `anchor=<date>` in the catalog and the model is
  told to answer such questions with `build_definition` on `activity_date`
  (the business definition) instead of hand-rolled SQL that disagreed with the
  reports (681k vs 1,574 backlog). *Show it as a chart* on an answer that
  carries a definition opens it in the builder instead of asking the model to
  draw. The auto-caption receives notes about the partial bucket and NULL
  buckets and is told empty cells are missing measurements, not zero.
- Wizard "So far" summary updates on breakdown, grain and time-range picks
  (it lagged one pick behind); weekly/daily peak labels drop the `00:00:00`.
- **Backlog stays a gap when broken down by a second dimension.** The
  Simple-tab chart pivot (e.g. backlog by process) coerced an unmeasured
  bucket's `NULL` to `0` while collapsing rows into series; it now stays a
  gap for latest-mode metrics, matching the single-dimension chart.

## [3.2.2] - 2026-08-25

### Added

- **Imports, exports and backlog on one chart.** New date-anchored measures
  on the Document Processing source — *Documents imported* / *Pages imported*
  (counted on the import date), *Documents exported* / *Pages exported*
  (export date) and *Backlog* (point-in-time from `dbo.BacklogHistory`,
  newest snapshot per bucket, process names unified to `client.process`) —
  all plotted on one shared **activity_date** time axis. Pick them together
  in the wizard ("Over time (Date)") to get the import line, the export line
  and the backlog line in a single report; tiles, exports, saving and
  scheduling work unchanged (single SQL on the Statistics engine).
  `ReportingMetrics` gains a `DateAnchor` column (migration `0067`); anchored
  and unanchored measures cannot be mixed, and the wizard greys the
  incompatible pills. Known v1 limits: drill-through is not available on
  anchored results, and months without any backlog snapshot chart as 0.

### Removed

- **The standalone "Backlog History" reporting source is retired**
  (migration `0069`): the anchored *Backlog* measure on Document Processing
  supersedes it (combinable, process-scoped, latest-per-bucket). The
  migration deletes the source, its `backlog_total` metric, the
  `reporting.source.backlog_history` permission (incl. grants), and the
  saved reports/dashboards that referenced them. The `dbo.BacklogHistory`
  table and its collector are untouched — the anchored measure reads them
  directly.

### Fixed

- **Charts with a second breakdown silently dropped every measure but the
  first.** "Imported + exported + backlog per month / process" rendered only
  the first measure's lines. The two-dimension pivot (Simple pane and the
  scheduled-mail PNG renderer) now emits one series per (breakdown ×
  measure) pair ("privera.03_Invoice_New · Documents exported"), with the
  12-series cap applied fairly per measure so a small-valued measure
  (backlog) is never crowded out by large ones; single-breakdown PNGs also
  gained per-measure series. The old "Backlog" measure on the Backlog
  History source is relabeled "Backlog (detail analysis)" (migration `0068`)
  to distinguish it from the combinable anchored one.
- **Backlog history charts showed summed snapshots instead of point-in-time
  values.** Two stacked bugs: the generic table builder never truncated a
  `day`-grained `datetime` dimension (grouping per 30-minute snapshot, not per
  day), and the chart then added every snapshot landing on the same date — a
  day showing 9 000+ for a backlog that never exceeded 1 300. Day grain now
  buckets via `CAST(... AS date)`, and `TotalMode='latest'` metrics
  (`backlog_total`) aggregate only the **newest snapshot per bucket** (per-day
  closing value) instead of the whole day — also applied to category-only
  breakdowns ("Backlog by process" = latest snapshot), previously
  zero-dimension totals only. The KPI stat band (groups / avg per group /
  peak) becomes consistent with the chart as a side effect.
- **A `1900-01-01` bucket could appear on reporting time axes.** SQL Server's
  zero-date sentinel (empty-string/zero date casts) bucketed as a real date;
  both query builders now exclude it from grained date dimensions (NULL "no
  date yet" buckets stay).
- **Drill-through chips rendered relative date ranges as `[object Object]`.**
  Token values ({"token": "this_month"}) and value lists are now formatted.
- **The result view showed "Processes: all" next to an active process
  filter.** For sources without a process registry (`backlog_history`) the
  process restriction lives in a plain `in`-filter; the process chip now
  renders (and edits) that filter instead of always reading `scope.processes`
  — the same chip was previously also dead on click for those sources.
- **`in`/`not_in` filter chips no longer demand comma-separated typing.**
  Editing opens a checkbox picker of the field's distinct values (process
  registry or `POST /api/reporting/field_values`), falling back to the text
  editor when no values are available.

### Changed

- **Chip editors got a visual overhaul.** The inline editors that open when
  clicking a result chip (date preset, process/value checkbox pickers, grain)
  now render as small popover-style cards — checkbox options as selectable
  pills with accent highlighting — instead of raw unstyled controls.
- **The wizard's process picker for the backlog source now shows
  client-prefixed names** (`privera.03_Invoice_New` style, matching the rest
  of the app) via a new optional `labelWith` key in `ReportingSources.
  ColumnsJSON` (migration `0065`, which also renames the "Snapshot at" column
  label to "Stand").
- **…and only offers granted processes.** The snapshot collector records
  every Octo process, so the picker listed processes nobody has configured.
  A second ColumnsJSON flag `grantScoped` (migration `0066`) restricts the
  offered values to the caller's `reporting.scope.process.*` grants — the
  same list the rest of the app shows. UI curation only; the run path stays
  gated by the source-level permission.

### Fixed

- **Uploaded profile avatars were silently deleted on every production
  deploy.** The upload handler saved `{userid}-icon.png` directly under
  `static/images/`, but that whole tree is `robocopy /MIR`'d from git on
  every deploy — anything present on the server but absent from the git
  source gets purged, and an uploaded avatar (never committed to git) was
  exactly that. Avatars now save to `var/uploads/avatars/` (already
  excluded from the deploy mirror, same as sessions/logs/screenshots) and
  are served through a new `/avatar/<user_id>` route instead of a static
  file path.

- **Checkboxes/radios stayed plain white regardless of theme.** Native
  checkbox rendering wasn't reliable enough on its own: `accent-color`
  only tints the checked-state fill, and on a real Windows/Chrome setup
  even that wasn't enough — the *unchecked* box painted solid opaque
  white regardless of `color-scheme`/`accent-color`, standing out
  against every other bit of chrome that does follow dark mode/accent
  (Workitems' row-select/select-all checkboxes, the export-options
  checkboxes, the process-filter dropdown's checkboxes, admin/reporting
  radios, ...). Replaced native rendering with a fully custom checkbox/
  radio (`appearance: none` + our own border/background/checkmark, via
  `body.nx-app input[type="checkbox"|"radio"]` in `nexora-ui.css`) so
  every state — unchecked, checked, indeterminate (the process-filter
  dropdown's "some but not all selected" rows) — is explicitly
  theme-and-accent-aware instead of trusting the browser.

### Changed

- **Workitems search results now rank by relevance.** With a workitem-id
  search active, the closest match sorts first — shortest id (fewest extra
  digits beyond the searched prefix) on top, longer ids further down;
  searching `11` puts `11` above `110` above `1199`. Applies in both
  per-source queries (`ORDER BY LEN(id) ASC, ModifiedAt DESC`) and the
  cross-source merge for multi-client setups, which previously
  re-sorted everything back to plain recency after each source's own
  query. No search term active: unchanged plain-recency ordering.

### Fixed

- **Segmented picker buttons (Feedback's category, Appearance's Theme/
  Background/Density/... pickers) had an invisible "selected" indicator in
  dark mode.** `.profile-seg-btn.is-active`'s box-shadow was a near-black
  drop shadow tuned for a white card — on a dark card it was essentially
  imperceptible, so which option was selected read almost entirely off
  color alone. Added a `.dark`-scoped shadow (a visible border ring plus a
  soft accent-colored glow) so the selected state is unambiguous in dark
  mode too.

### Changed

- **Workitems search: prefix match instead of exact match.** Typing `11`
  now returns every workitem whose id *starts with* `11` (`11`, `110`,
  `1199`, ...), not just the literal `11`. Still not a full substring
  match — searching `371` still won't pull in `1371`/`3716`/`16371`, the
  original reason it was exact-only. Applies everywhere the Workitems
  overview's search box does, including the external API's `workitem_id`
  param (`docs/howto/external-api.md`).

### Added

- **Feedback page** (`/feedback`, profile dropdown → "Feedback") — an
  in-app way to report a bug, ask a question, or suggest an idea, so
  problems don't rely on someone happening to mention them. Category
  (Bug/Idea/Question) + message + an optional screenshot mail
  `SUPPORT_MAIL` (the outage-monitor env var, issue #166) via the existing
  Graph sender, auto-enriched with the submitter, the page they came from,
  and the app version/environment. No ticket tracking in-app — the mailbox
  is the queue. Rate-limited (`10 per hour`); screenshots are sniffed with
  the same `is_file_allowed` MIME check as every other upload, capped at
  5 MB, and never touch disk.
- **The nexora logo now follows your accent color** — the wordmark
  gradient and the black-hole icon's glow/ring/spark colors re-tint with
  whichever accent you pick in Appearance (preset or custom hex), on every
  page including pre-login (login, password reset, 2FA setup — read from
  the same `nexora-ui-prefs` localStorage mirror `_header.html` already
  writes, so it's picked up the moment you've logged in once on that
  browser). Previously fixed indigo everywhere; the black core and the
  wordmark's near-black leading stops stay fixed brand ink in every theme
  — only the actual accent-colored pieces change.

### Fixed

- **Logged-in pages: light-theme flash on reload/navigation in dark mode.**
  `_header.html`'s own UI-prefs script (issue #155) never actually ran
  pre-paint despite the comment claiming otherwise: it's `{% include %}`'d
  inside every page's `<body>`, but its markup opens with a *second*
  `<!DOCTYPE html><html><head>...</head><body>` of its own — the HTML
  parser drops that nested `<head>` start tag but still processes the
  script/link tags meant to live inside it, just relocated as `<body>`
  children. So dark mode (and `nexora-ui.css`'s `--nx-*` design tokens)
  only ever applied after the page's real `<head>` — and its first paint —
  had already happened. Added `templates/_theme_prepaint.html`, included
  first in the real `<head>` of all 28 logged-in page templates: it
  applies `html.dark`/`.sidebar-pinned` and an inline `background-color`
  synchronously from the server-rendered prefs, and an early
  `nexora-ui.css` `<link>` so `--nx-*` tokens exist before any dependent
  CSS (Reporting's `--rl-canvas`, Workitems' table colors) can paint.
  `reporting.css`'s token block also gained explicit fallback values as a
  second line of defense.
- **Page-entrance animation felt rushed.** `.nx-rise`/`.nx-rise-2`/
  `.nx-rise-3` (`nexora-ui.css`) went from 0.32s to 0.6s, stagger delays
  scaled to match.

### Added

- **Dark mode toggle on every pre-login page** — landing, login, the
  forgot/reset/set/init password pages, and 2FA setup all get the same
  sun/moon toggle and share the logged-in pages' prefs storage, so a
  choice made before logging in carries over automatically afterward.
  Along the way, fixed several pages' hardcoded light-only colors that
  had no dark counterpart at all (an invisible gradient-clipped logo
  wordmark, background glow blobs anchored off-viewport, a JS reset
  loop that kept clobbering the process-animation icon back to light
  mode) and brightened the login page's black-hole icon glow, which
  was a near-black drop shadow invisible against the dark background.
- **"Fireflies" background option in Appearance** (alongside Plain/
  Aurora/Grid) — started as a dashboard-only decorative effect,
  promoted to a real per-user preference available on every page.
  Fixed two real bugs surfaced while wiring it up: the server-side
  prefs allowlist rejected the new value outright (a 400 with no
  visible error, so the pick silently never saved), and the prefs-save
  request had no `keepalive`, so picking any appearance setting and
  immediately navigating away (e.g. clicking a sidebar link) could let
  the browser abort the save mid-flight — affecting every appearance
  preference, not just background.
- **Reporting's AI chat panel is now a draggable, non-modal floating
  window** (#205), replacing the fixed right-edge modal slide-over —
  the report underneath is no longer dimmed or click-blocked while the
  chat is open, restyled to match the app's theme (gradient header,
  accent-colored user messages, dark-mode-aware scrollbars). The drill-
  through drawer intentionally stays modal.

### Changed

- **Workitems now loads large result sets in two phases.** A `perPage`
  of up to 1000 previously left the table on a spinner for the whole
  round trip; a small 40-row chunk now renders almost immediately,
  with the full-size request following in the background (guarded
  against a stale response overwriting a newer one).

### Fixed

- **`bin/nx.ps1` hardcoded a previous owner's personal Python path** —
  every `nx` command failed outright on a fresh clone. Now points at
  the project's own `.venv`; `bootstrap.ps1`'s `uv` install also no
  longer depends on `python`/`pip` resolving correctly first (the
  Windows Store app-execution alias can silently break that).
- **`matplotlib` and `pypdfium2` were used by the reporting chart-
  render/export pipeline but missing from `requirements.txt`** — a
  clean install could break reporting exports depending on install
  order. Both declared as explicit dependencies.
- **Dashboard dark-mode toggle recolored** to match the login page's
  teal/orange pair; the "Recent Validations" card was missing `dark:`
  variants entirely and stayed light-gray against the dark sidebar.
- **Dashboard: sidebar hover no longer pushes/reflows the page**
  (reverted an earlier push-on-hover change that felt like too much
  motion), and `html` was forced to an always-visible scrollbar
  (`overflow-y: scroll`) even when content fit — switched to `auto`.
- **Account dropdown menu (profile menu) had zero `dark:` variants** —
  stayed white-background/gray-text regardless of theme.
- **Profile's active nav pill and avatar ring were hardcoded indigo**
  instead of following the accent picker (`admin-tokens.css`'s
  `--a-b-indigo` pair, `profile.css`'s avatar-ring gradient).
- **App-wide accent-color sweep, ~30 files** — the same hardcoded-
  indigo bug class as the profile fix above, found across sidebar
  nav/hover states, buttons, focus rings, dashboard charts, workitems
  chrome, reporting wizard/dashboard-builder UI, all 7 Generali pages,
  and admin. Deliberately left alone: the logo (confirmed deliberate
  brand artwork), a couple of "locked spec palette" colors, and chart
  "primary series" colors used to visually anchor a multi-series
  legend. Also fixed two bugs surfaced along the way: the active
  sidebar item's text losing a CSS-specificity fight to the dark-mode
  idle-text rule, and a missing gap between the sidebar's "Admin"
  group header and its subitems that fused them into one pill.
- **Dashboard trend chart hover required the cursor to land exactly
  on the 3px line** — switched to index-based hover so any x-position
  in that column shows the tooltip. The line color was also hardcoded
  indigo in uppercase hex (which is why it slipped past the sweep
  above's case-sensitive grep), and the default plain-black Chart.js
  tooltip was reskinned to match the app's card styling.
- **Workitems table/list stayed white in dark mode** — an ID selector
  and an `!important` in `workitems_overview.css` were beating the
  otherwise dark-aware `.nx-table` styles regardless of theme.
- **Reporting hero card's rounded corners were invisible** — an
  accent-tinted border was blending into the equally accent-tinted
  glow rendered behind it.
- **Reporting's "Ask AI" bar's inner corners didn't nest with its
  outer gradient-border ring** except at the default corner-style
  setting; the inner radius now scales with the same preference.
- **A pinned sidebar flashed collapsed, then snapped open, on every
  page navigation** — its open state was only ever set by JS on
  `DOMContentLoaded`, well after the pre-paint script had already
  reserved the layout space for it.
- **Remaining white-flash-on-load cases in dark mode** — the pre-paint
  script now also sets the body background color directly (deferring
  to `DOMContentLoaded` if the body isn't ready yet), on top of the
  `<html>`-level pre-paint fix above.
- **Reporting AI chat panel: answers and generated SQL could not be
  selected or copied** — `user-select: none` was scoped to the whole
  panel instead of just its drag handle.
- **Process selector (Reporting scope picker) checkboxes rendered as
  barely-visible tiny dots** — missing explicit width/height and
  `flex-shrink: 0` let them shrink to almost nothing (#206).
- **An unpinned sidebar overlaid page content on hover** instead of
  pushing it aside — content now gets matching padding while the
  sidebar is hovered open.
- **Workitems search bar: icon and input text overlapped.** Root cause
  turned out to be the compact-density padding shorthand clobbering
  the input's left clearance in `nexora-ui.css`; fixed there instead
  of a per-page padding tweak that was tried first and then reverted,
  keeping this input's markup consistent with the other seven search/
  icon inputs across the app.
- **Dashboard trend chart: a second tooltip dead zone, at the bottom
  edge of the chart's plotting area.** Chart.js's hover only hit-tests
  inside its internal `chartArea`, and this dataset's often-zero
  values put the line right at that boundary — a cursor a couple
  pixels below where the line visually sits (still "on" it to the eye)
  fell outside `chartArea` and got no tooltip, while hovering higher
  up always worked. The pointer is now clamped into `chartArea` before
  hit-testing, so the whole canvas height is a reliable hover target.

### Added

- **The external API is now watched by the outage monitor and shows on
  `/admin/status`** (#201). `http:site` only proves IIS served a *page* — the
  `/api/v1/*` surface is a second entry point with its own auth module and can
  break on its own. Two new probes, both in the Application group: `api:v1`
  calls `/api/v1/stats/today` with no credentials and treats **401 as the pass**
  (zero setup, proves routing reached `require_api_key`), and `api:key` calls
  the `/api/test/v1` twin with a Bearer key from the new optional
  `OUTAGE_API_KEY` env var, covering the `dbo.ApiKeys` lookup and process
  scoping. `api:key` skips itself when the var is unset, the same way the Graph
  probe does. See `docs/howto/outage-monitor.md`. Migration `0064` seeds the
  monitor-only key row in `dbo.ApiKeys`; the raw key still has to be pasted
  into each server's `env/<ENV>.env` as `OUTAGE_API_KEY` by hand.

## [3.1.2] - 2026-08-18

### Fixed

- **Generali edit/delete row buttons were dead on PROD since v3.1** (base
  services, additional services, PDQM, project management). The #193
  finding-10 CSP hardening removed `'unsafe-inline'` from `script-src`, and
  these four partials still built their row buttons with inline
  `onclick="openEditModal(...)"` handlers — which the browser refuses under
  that CSP ("Refused to execute inline event handler"), so clicking did
  nothing and the PUT/DELETE never left the browser. Invisible on dev/INT,
  where Talisman (and thus the CSP) is deliberately off. The buttons now use
  `data-id` + one delegated tbody listener per page (the same pattern the
  reporting page already had, which is why reporting survived). A new
  template lint (`tests/unit/test_no_inline_event_handlers.py`) fails on any
  inline `on<event>=` handler so the PROD-only breakage can't ship again.

## [3.1.1] - 2026-08-18

### Added

- **External API: `GET /api/v1/stages`** — count of workitems per
  stage (Import, Extraction, Validation, Delivery) for the key's process
  scope, computed via the same path as a stage-filtered `/workitems` query.
  Ships with its `/api/test/v1/stages` sandbox twin, the
  `docs/howto/external-api.md` section and the in-app API-docs page entry.

### Changed

- **Generali user filter is searchable** — the user dropdown on the base
  services, additional services, reporting, PDQM and project-management
  filter bars is now a type-to-search box (native datalist): typing filters
  the user list, picking a name applies the filter instantly, clearing the
  box returns to all users. Duplicate display names are disambiguated with
  the user id. Shared implementation in
  `templates/js/_generali_user_filter_js.html`.
- **Generali filters apply instantly** — the Apply button is gone from all
  Generali filter bars (base services, additional services, reporting, PDQM,
  project management, import status, dashboard). Changing any filter select
  or date now reloads the list directly (debounced; the dashboard's datetime
  pickers refresh on picker close, import-status text search as you type).
  Reset is unchanged.
- **Dev setup is now bare `uv sync`** — dev dependencies moved from
  `[project.optional-dependencies]` to a PEP 735 `[dependency-groups]` group,
  which uv installs by default. `--extra dev` no longer exists (and now
  errors); `bootstrap.ps1`, `nx --doctor`'s hint and the docs are updated.
  `requirements-dev.txt` is likewise exported without flags now.

### Fixed

- **Compact density broke every icon'd search input** — with Appearance →
  Density set to Compact, the `html.nx-compact` input-padding shorthand
  outranked the `.nx-input.pl-10`/`.pr-10` icon-padding re-asserts (extra
  `html` type selector), so placeholders rendered underneath the magnifying
  glass on the Workitems, Generali documents, prepared-documents and admin
  search fields. The re-asserts now also exist at compact specificity.
- **Env switching was a silent no-op for TUI-started dev servers** — the `nx`
  REPL imports `nx_lib.config` at startup, which loads the current env file's
  keys into the TUI's own process env; servers it spawned inherited them, and
  with `override=False` those inherited creds beat the target env file, so a
  server restarted with `env:staging` claimed STAGING while still running INT
  DB connections. Contamination was hereditary: such a server's `DOTENV_KEYS`
  is empty, so even the in-app restart's #187 strip couldn't recover. The TUI
  now spawns `nx.ps1` and python subcommands with the dotenv-injected keys
  stripped (same idiom as the in-app restart).
- **Generali user-search filter was invisible on all five Generali pages**
  (base services, additional services, reporting, PDQM, project management;
  client-reported on base services). The #142 inline-style cleanup replaced
  `style="display:none"` on `#filterUserWrapper` with the Tailwind class
  `[display:none]!` (= `display:none !important`), which the reveal code's
  `wrapper.style.display = ''` can never override — so the filter stayed
  hidden regardless of permissions. The reveal now removes the class instead.
  Same fix for the workitems export spinner and export-images helper info,
  which could likewise never show. A template lint test now guards the
  pattern (`tests/unit/test_display_none_important.py`).
- **A fresh clone could not run the app or the `nx` CLI** — `ModuleNotFoundError`
  even after installing every `requirements*.txt`. Three causes, all fixed:
  - `matplotlib`, `pypdfium2` and `markdown-it-py` are imported at module scope
    by `nx_lib/` but were never declared in `pyproject.toml` (they had been
    hand-added to `requirements.txt`, which `uv lock`/`uv sync` ignore, so only
    machines with ad-hoc global installs worked). `tabulate` was likewise
    undeclared for `scripts/new-process.py`. All are now real dependencies,
    with `matplotlib`/`pypdfium2` pinned to the versions already in production
    rather than the latest resolve (`pypdfium2` 5.x is an unexercised major).
  - `bin/nx.ps1` hardcoded one developer's absolute interpreter path. It now
    resolves the repo's `.venv`, then `$env:NEXORA_PYTHON`, then `python` from
    `PATH`, and prints an actionable error instead of failing obscurely.
  - `requirements-dev.txt` was a stale export missing `openpyxl`,
    `psycopg2-binary`, `sqlglot` and `et-xmlfile`. Both requirements files are
    regenerated from the refreshed lock.
- `tests/unit/test_dependencies.py` (new) fails when `nx_lib/`, `scripts/` or
  `ops/` imports a package `pyproject.toml` does not declare, so this class of
  drift cannot silently return.

## [3.1] - 2026-08-17

### Added

- `GET /api/v1/workitems/fields` (and its `/api/test/v1` twin): discovery
  endpoint listing the field keys `/api/v1/workitems` accepts in `?field=`,
  scoped to the key's `ProcessList` (only fields mapped for at least one of
  the key's processes, minus sensitive fields). Docs and the in-app API
  docs page now state the key-naming rule (lowercase, no separators) and
  point at it.

- **External API: `GET /api/v1/undelivered`** (#196) — the number of
  workitems imported in the last `?days=7|10` calendar days that have no
  export date yet, scoped to the API key's processes (not echoed in the
  response, same idiom as `/backlog`); ships with its
  `/api/test/v1/undelivered` sandbox twin and is documented in
  `docs/howto/external-api.md` and on the in-app `/api-docs` page, whose
  Base URLs table now lists the test-sandbox base instead of the INT
  localhost URL.
- **External API: Avg Processing Time** (#194) — `GET
  /api/v1/avg_processing_time` (with its `/api/test/v1/...` sandbox
  twin) returns the same "Avg Processing Time" number shown on the dashboard,
  scoped to the key's `ProcessList`. The calculation itself (mean of
  per-source `AVG(export - import)` seconds among rows exported today, not
  weighted by row count) is unchanged — only extracted into a shared
  `compute_avg_processing_time` helper (`nx_lib/views/dashboard.py`) so the
  dashboard and the API can never drift apart. Documented in
  `docs/howto/external-api.md` and the in-app `/api-docs` page.
- **External API: workitem query + detail** (#197) — `GET /api/v1/workitems`
  filters workitems with the Workitems overview page's filter set (workitem
  id, status, stage, modified-date range, process, repeated doc-field pairs
  incl. invoice number) scoped to the key's `ProcessList`, returning
  id/client/status/stage/modified_at/import_datetime rows;
  `GET /api/v1/workitems/<id>?client=` returns the row-expand document
  details (extracted fields + table values, sensitive fields stripped, no
  media/confidence/locations) with a uniform 404 for unknown and
  out-of-scope ids. Both endpoints fail **closed** (500) when the
  sensitive-field list can't be loaded (the in-app fail-open stays in-app;
  `get_sensitive_field_keys/tokens` now cache only on success and signal
  failure as `None`), and doc-field pairs are capped at 10 per request. Both ship with `/api/test/v1/...` sandbox twins and are
  documented in `docs/howto/external-api.md` and on `/api-docs`. Internally
  the overview's `_get_workitems_data` gained a session-less `scope`
  parameter and the detail panel's fetch core moved to a shared
  `_load_media_info` — one code path for UI and API. Supersedes the
  unreleased single-purpose `GET /api/v1/invoice/import_datetime` (#195):
  the same lookup is now `?field=invoicenr&value=<nr>&op=eq`, with the
  import datetime on the result row
  (`resolve_import_datetimes`, `nx_lib/views/dashboard.py`).
- **What's New page** (#169) — `/whats_new` (profile dropdown and Ctrl+K),
  showing curated, translated per-release feature notes authored in
  `nx_lib/whats_new.py` at release time (the raw `CHANGELOG.md` stays
  dev-facing; curation step documented in `docs/howto/whats-new.md`). Entries
  are permission-filtered — users only see features their account can actually
  use — and can link to their feature page. A red dot on the header avatar and
  the dropdown item appears when a curated release is newer than the user's
  seen-marker (`dbo.Users.whats_new_seen_version`, migration `0061`); opening
  the page clears it. No modal, badge only.
- Admin overview page (dev-only) now shows the currently-running `ENVIRONMENT`
  next to the "Restart nexora" button and a dropdown to restart into a
  different one (INT/STAGING). `POST /api/admin/restart` accepts an optional
  `{"env": "INT"|"STAGING"}` body and passes it through to `nx.ps1 -r
  --env:<value>`; after the restart the page logs itself back in via the
  dev-only login (which now honours a relative `?next=` path) and returns
  to where it was. `nx.ps1` gained `--port:<n>` (with `-u`/`-r`/`-d`) and the
  restart API passes its own port, so a `--no-conflict` instance restarts
  itself instead of the port-8000 one (#187).
- In-app Reporting help — a **Help** button in the Reporting page header opens
  a "Get the best results" panel (coverage badges, drill-through, delta chip
  semantics, chart caps, AI prompting tips), and its **Full guide** link opens
  the complete user guide as an app page at `/reporting/guide`
  (`docs/howto/reporting-guide.md` rendered server-side with markdown-it-py;
  the deploy workflow now ships that one docs file and deploys on guide-only
  pushes). The panel (`templates/_reporting_help.html`) mirrors the guide's
  new "Tips — getting the best results" section; a non-blocking
  `reporting-help-sync` pre-commit hook
  (`scripts/check-reporting-help-sync.py`) reminds when reporting behaviour
  changes without touching either.
- "Restart nexora" button on the admin overview page (#184) — dev-only
  (404s on PROD), lets admins with the new `admin.restart` permission
  (migration `0059`) kill and respawn the local dev server (`POST
  /api/admin/restart`, fires `bin/nx.ps1 -r` detached) so template/code
  changes show up without dropping to a terminal; the button polls until the
  server answers again and reloads the page.
- Saved-view folders (#186) — a saved workitems view can optionally live in a
  folder ("Search Specific"): the save/edit editor gains a folder field whose
  dropdown lists the existing folders, and same-folder views render as one folder
  chip (name + count) whose dropdown lists them. Un-foldered views stay plain
  chips; editing with a different folder moves the view. Nullable `Folder`
  column via migration `0060`; `GET`/`POST /api/workitem_filter_views` carry
  the optional `folder` field.
- Workitems saved filter views (#170) — the whole filter state (process, search,
  stage, status, dates, doc-value rows, per-page) can be saved as a named
  per-user view via the new "Save view" button; views render as chips in the
  filter card's toolbar row, left of the action buttons. Click applies the view
  (Advanced opens/closes to
  match), the active chip is highlighted until a filter is hand-edited, and
  clicking it (or its ×) again deselects — resetting the filters. The pencil
  opens an inline editor for rename/move, and deletion lives there behind an
  explicit trash button (an always-visible × deleted views when users meant to
  unselect them). Saving under an existing name
  overwrites it. Stored in `dbo.WorkitemFilterViews` (migration `0057`, private
  per user, capped at 50); new endpoints `GET`/`POST
  /api/workitem_filter_views` and `DELETE /api/workitem_filter_views/<id>`, all
  gated by `workitems.view`. Fields the user has since lost permission for are
  dropped on apply (client resolves them to "All fields"; server-side gates
  unchanged).

- `docs/howto/reporting-guide.md` (#179) — a plain-language end-user guide to
  the Reporting page: the four-question guided builder, Ask AI, the Advanced
  builder, reading the stat band / delta chips / forecast, drill-through,
  saving and sharing, exporting, scheduled and alert-only mails, dashboards,
  plus a "why does my number look wrong?" table and a glossary. Admin-only
  surfaces (source registry, metrics registry, SQL sandbox) are fenced into one
  final section so the guide can be handed to clients as-is. `reporting.md`
  stays the developer reference and now cross-links it.

- Reporting: live "building your report" step list in the AI chat while the
  agent works (#178) — a title line plus a growing per-tool-call step list
  (Building the report… / Checking the query… / Running the query… /
  Crunching the numbers…) replaces the old generic rotating status line.
- Reporting: granularity chip on Simple results, and the wizard's grain
  select is now always visible (disabled with a tooltip until a time
  breakdown is picked) rather than only appearing once one is chosen (#178).
- Reporting: wizard process step for table sources via new
  `POST /api/reporting/field_values` — a table source with no process
  registry but a process-like filterable field now gets a field-scope step
  in the wizard, sourced from the field's own distinct values (#178).
- Reporting: `TotalMode` on the metrics registry (migration `0056`) —
  snapshot metrics (backlog) total the latest bucket instead of summing
  snapshots, both server-side (zero-dim grand total) and on the Simple KPI
  band's "last bucket" caption (#178).
- Reporting: dashboard card type "Report" that adopts a saved report 1:1,
  including its own chart type (#178).

- **Admin status page** (#167) — `/admin/status`, gated by the new
  `admin.status.view` permission (migration `0055`, granted to every profile that
  already has `admin.view`). Shows each component's state
  (operational / degraded / outage, with an active maintenance window taking over
  the headline), a 30-day uptime strip, any open incidents with their evidence,
  and the incident history with durations. It renders only what the #166 outage
  monitor persisted rather than probing on page load — the question it answers is
  "what has been true since yesterday evening", which a request-scoped ping
  cannot. When the monitor has not reported for more than 15 minutes the page
  says so instead of rendering a reassuring all-green grid from stale rows.
  `ops/outage_monitor.py` now also probes Microsoft Graph (token only — a probe
  that sent mail would spam the mailbox every 5 minutes) and the Bexio API, and
  mirrors every run into the new `dbo.StatusComponents` / `dbo.StatusIncidents`
  tables. The mirror write is best-effort and wrapped: NexoraDB being down is one
  of the things the monitor exists to report, so a failed write must never cost
  the alert mail. Log-storm components stay out of the component grid (their keys
  are content hashes) and surface as incidents only. The two tables are the data
  model the eventual public status page — which has to live outside the app to
  survive a full outage — will consume.
- **Pull-request template** (`.github/pull_request_template.md`) — checklist for
  the things nothing else catches when merging to `main`, chiefly: env keys
  added to `env/*.env.example` never reach SYAPP01 on their own, because
  `deploy.yml` excludes `*.env` from the mirror. Migrations deploy themselves;
  env keys do not.
- Reporting: forecast toggle on time-series results (#168) — single-date-dim
  reports gain a Forecast toggle + horizon control (Auto/+7/+14/+30) in Simple
  and Advanced; the chart extends with a dashed prediction line and a 95 %
  confidence band (stdlib trend + seasonality, `nx_lib/reporting/forecast.py`),
  the table appends marked prediction rows, exports carry a Forecast marker
  column, and scheduled mails include the forecast when the saved definition
  has the toggle on. Drill-through is excluded on predicted points.
- **`scripts/env-sync.py`** — compares the gitignored env files in a checkout
  against the SYAPP01 copies (`\\syapp01\d$\sydoc\nexora\env`). Because
  `deploy.yml` excludes `*.env` from the robocopy mirror, a key added to the
  committed `env/PROD.env.example` never reaches the server on its own, and
  forgetting is silent — `SUPPORT_MAIL` is the reference case. The check is
  three-way (example vs local vs server), so a key the repo declares with a real
  default but the server lacks is reported as the deploy-forgot bug — printed as
  copy-pasteable `KEY=value` lines — while opt-in keys left blank in the example
  are collapsed to a count. Meant to be run by hand once per deploy that touched
  an env key. Only a missing key sets the exit code; a key present on both sides
  with a different value is informational, since dev and PROD hold different
  credentials and PROD legitimately lags dev until its deploy lands. Values are
  masked to fingerprints unless `--show-values`; `--push`/`--pull` copy a whole
  file after backing the destination up.
- **PROD outage detection with support-ticket mail** (#166) — a new
  `ops/outage_monitor.py`, run by Task Scheduler on SYAPP01 outside the Flask
  process (an in-app scheduler cannot report the app being dead), probes every
  DB engine, the public site over HTTP, the Octo token endpoint, and
  `var/logs/system/app.log` for repeating `ERROR` signatures. On breach it mails
  a ticket to `SUPPORT_MAIL` (new env var, alongside `OUTAGE_SITE_URL`) via the
  existing Graph sender. The log-storm probe is the one that would have caught
  the 2026-08-05 `0042` incident, where every connectivity check stayed green
  while the workitems list was broken for half a day. Alert hygiene —
  fail-threshold, dedupe and a 30 minute min-hold in `nx_lib/outage.py` — means
  a flapping component sends one outage mail and one recovery mail rather than
  the ~200 the old `ping_prdsrv` monitor once produced; incident state persists
  in `var/outage-state.json` so restarts do not re-alert. Ships with an
  importable Task Scheduler definition (`ops/outage-monitor-task.xml`). See
  `docs/howto/outage-monitor.md`.
- **Multi-select process filter** (#150) — the process filter on Dashboard
  and Workitems is no longer one-process-or-all: it is now the same
  checkbox dropdown the Reporting page uses (All / per-client / per-process
  rows), so two or three processes can be filtered at once. The filter value
  on the wire is `all` or a comma-joined `client.process` list (`prcfD` /
  `prcfW`, and `process` on `/api/docfield_values`); every entry is
  permission-checked individually, and a selection that ends up empty falls
  back to `all`. The picker lives in the shared partial
  `templates/js/_process_multiselect_js.html`, its styling moved from
  `reporting.css` into `nexora-ui.css` as the app-wide `.nx-scope*`
  component.
- **Backlog History in Reporting** (#162) — the #161 collector's
  `StatisticsDB.dbo.BacklogHistory` is now a registered reporting source
  (`sql/_migrations/NexoraDB/0053`, `0054`) with a canonical `backlog_total`
  metric, so it appears as a "Backlog" measure in the Simple wizard (with
  "over time" grouped by month/week/etc. and breakdown by client/process) and
  is grounded for the AI assistant. Fixed two provider-level gaps this
  exposed in the generic `table` source provider: the `grainable` column flag
  was silently dropped from the catalog, and date-grain requests either
  400'd (missing `grainable_fields` in validation) or silently grouped by
  the raw timestamp instead of the requested bucket (no grain SQL applied).
- **External API test sandbox** (#163) — every `/api/v1/...` route now has a
  `/api/test/v1/...` twin (same path, auth, and response shape) that returns
  random data instead of real KPI values, so clients can integrate without
  touching production data. Convention going forward: new v1 routes ship
  with their test twin.
- **"Development" sidebar group** (#157) — the API Docs page moved from a
  flat top-level sidebar item into a collapsible "Development" group
  (matching the Admin/Generali group pattern), so future dev-facing pages
  have a home without crowding the main nav.
- **Backlog-history collector** (#161) — new standalone
  `ops/backlog_history/` folder (script + own `.env` + requirements; no
  nexora imports, copyable to any prod server) for a 30-minute Task
  Scheduler task that snapshots the current C+A backlog per (source,
  client, process) from the Octo runtime DB + MS02 Postgres into a new
  `dbo.BacklogHistory` table on the Statistics DB (created idempotently
  by the script — the Statistics DB is not under `sql/_migrations/`), so
  backlog-over-time trends exist. `SnapshotAt` is server-local time;
  reporting-only/template processes are excluded via the `EXCLUDED` set;
  `--dry-run` prints the rows without writing. Runs log to a rotating
  `backlog_history.log` next to the script; on failure the run exits
  non-zero and opens one consolidated helpdesk ticket (Graph mail to
  `TICKET_TO`, throttled by `TICKET_COOLDOWN_HOURS`).
- **In-app API documentation page** (#157) — new `/api-docs` page (sidebar
  entry "API Docs") documenting the external `/api/v1/*` machine-to-machine
  API: getting-started guide, authentication, errors & rate limits, and a
  per-endpoint reference (`GET /stats/today`, `GET /backlog`) with copyable
  curl/JSON examples. Gated by the new grantable `api.docs.view` permission
  (migration `0051`, seeded to admins), intended for both internal staff and
  external API clients' portal accounts; an account holding only
  `api.docs.view` lands on the docs page after login.
- Workitems: **date-range presets** (#159) — a "Date Range" dropdown (Today,
  Yesterday, This week, Last 7 days, This month) in the Advanced filter panel
  that fills From/To Date and refetches; hand-editing a date flips it back to
  Custom. The Document Value Search block moved **inside** the Advanced toggle
  (hidden by default; the panel auto-opens when a URL restores any advanced
  filter so an active filter can't silently narrow the list).
- Appearance: **standalone `/appearance` page** (#155) replacing the in-profile
  controls (the profile keeps a teaser card linking to it; also reachable from
  the profile dropdown and the Ctrl/Cmd+K palette). Adds a **live preview
  canvas** — a miniature nexora page (header, KPI cards, table, form) built
  from the real `--nx-*` tokens so every change repaints it instantly — with a
  **Replay** button for comparing entrance animations, plus a mono spec
  readout of the active tokens. New preferences on top of the #155 set:
  **custom accent** (any hex via a native color picker; hover/soft/tint/
  gradient shades derived client-side, dark-aware), **font size**
  (small/default/large, zoom-based), **corner style** (sharp/default/round via
  the radius tokens), **high contrast** (stronger borders + darker secondary
  text), **table stripes**, **page background** (plain/aurora/grid), and a
  one-click **Reset to defaults**. Corner style drives one `--nx-radius-scale`
  factor: the radius tokens plus ~100 previously hardcoded `border-radius`
  values across the CSS files are wrapped in `calc(scale × Npx)`, so
  sharp/round reshapes the whole app while the default stays pixel-identical.
  Page entrance gained three more styles — **slide**, **pop** and **blur** —
  and a new **animation speed** pref (relaxed/default/snappy) scales the
  entrance keyframes and every `--nx-dur` transition through one
  `--nx-anim-speed` factor; motion-related clicks auto-replay the preview.
- Profile: **Appearance settings** (#155) — a new profile section with per-user
  UI preferences: theme (light/dark/**system**, the latter following
  `prefers-color-scheme`), **accent color** (indigo/violet/emerald/amber/rose/sky,
  re-tinting the `--nx-*`/`--a-*` brand tokens via `html[data-accent]`),
  **animations** (full/reduced — an in-app reduced-motion switch that also
  hard-guards legacy unguarded keyframes), **page entrance** style
  (rise/fade/off), **density** (comfortable/compact for `.nx-*`/`.admin-*`
  tables and cards), and the sidebar pin. Preferences persist cross-device in
  `dbo.Users.ui_prefs` (JSON, migration `0050`) via the new
  `POST /profile/ui_prefs` endpoint (`nx_lib/ui_prefs.py`, allowlist-validated),
  hydrate into `session['ui_prefs']` once per session (same idiom as locale),
  and apply pre-paint from a `_header.html` head script. The sidebar dark-mode
  and pin toggles now write through to the server; localStorage keeps working
  as the logged-out/legacy fallback.
- Reporting AI chat: **Continue** button (#153) when the agent loop dead-ends
  on `max_turns`/`budget` without a final answer -- re-runs the same question
  with a raised turn/budget cap (double the default), capped at 2 attempts
  per question.
- Sidebar: **pin toggle** (#151) in the bottom actions -- keeps the nav rail
  expanded (220px) instead of collapsing when the mouse leaves. State persists
  per-browser via `localStorage`, same idiom as the dark-mode toggle.
- Reporting AI: **committed the 22-prompt statistical eval suite** (#131) as
  a repeatable harness under `tools/reporting_ai_eval/` (dev-side, excluded
  from the deploy mirror) - `prompts.json` (22 hard stakeholder questions
  grouped by trap, each with a pass criterion), `run_eval.py` (logs into a
  running INT instance and collects full agent responses per prompt,
  resumable), and `baseline_2026-07-28.md` (the original 6.1/10-average
  scored run that surfaced issues #127-#130). Scoring stays manual/Claude-
  assisted against the criteria; the runner only collects.

- Workitems: **Stage filter** in the top filter row (#147), between Workitem
  and Status, gated on the new `workitems.filter.stage` permission (migration
  `0048`, seeded to holders of `workitems.filter.status`). Filters on the
  workitem's LATEST derived stage (Import/Extraction/Validation/Delivery,
  same values as the detail-panel stepper) -- both source adapters (SQL
  Server + MS02 Postgres) now dedup activity rows to the latest one before
  applying the stage clause, reusing the existing rn=1 CTE for both the count
  and the list query.

- Header: **switch user** button (dev-only, #118), GitHub-style. The profile
  dropdown gains a "Switch user" item that opens a searchable list of INT
  usernames (new `/dev/users` JSON endpoint) and switches the session via the
  existing `/dev/login/<username>` bypass on click — no more dropping to the
  terminal to `nx --loginas:` mid-session. Hidden in PROD (`is_prod` template
  global, same guard as `/dev/login`).

- Workitems: **see deleted workitems** with the new internal-only permission
  `workitems.filter.status.deleted` (#125, migration `0044`). Soft-deleted
  workitems (Octo/MS02 `Status = 2`) were hard-excluded from every list with no
  way to reach them; holders now get a "Deleted" option in the status filter,
  which drops that exclusion for that one query and badges the rows red. Both
  sources honour it (default Octo + MS02 Postgres) and the CSV export follows
  the filter. Opt-in only: "All statuses" still hides deleted rows, and without
  the permission the value is not mapped at all, so the query keeps its
  `Status <> 2`. The dashboard's recent-workitems tiles stay filtered.

- Header: the **version and build stamp in the profile dropdown** (#113). The
  footer partial is the only place either was rendered, and 12 page templates
  never include it — reporting (3), all 7 admin pages, `prepared_documents`,
  `maintenance` and `jd/jdvance` — so the newest and most-used surfaces showed
  no version at all. `templates/_header.html` now closes the profile menu with
  it, covering every page that has a sidebar. `_header.css` opts the stamp out
  of the dark-mode gray ramp: `text-gray-400` remaps to `#475569`, which is
  1.95:1 on the `#1e293b` menu, so 12px text was effectively invisible. Now
  4.83:1 in light and 5.71:1 in dark, both above the 4.5:1 AA floor.

- Footer: a **deploy build stamp** next to the version (#113) — the footer read
  `nexora 2.5.65` whether or not a deploy had actually landed, so a mirror that
  silently failed looked identical to a successful one. `.github/workflows/deploy.yml`
  now writes `nx_lib/_build.py` (`BUILD_STAMP = "<short-sha>, <UTC date>"`) right
  after the robocopy mirror, `nx_lib/version.py` imports it with an `ImportError`
  fallback to `""`, and the `nexora_build` context variable renders as
  `nexora 2.5.65 · a1b2c3d, 2026-07-28`. The file is gitignored and absent in
  dev/INT, which keeps those footers version-only and unchanged.

- Admin: **email invite for new users** (#117). The Add User modal has a
  "Email the user a link to set their own password" checkbox, ticked by
  default, which hides the password field: `POST /admin/users/add` then
  generates a strong random placeholder password (`secrets.token_urlsafe`,
  never shown to anyone), stores it hashed, pre-sets `InitReset` and mails the
  user a set-password link. The link reuses the existing `/reset_password/…`
  flow under its own `user-invite-salt`, valid for 7 days rather than the
  15 minutes a self-service reset link gets. The invited user lands on a
  dedicated welcome page (`templates/set_password.html`) rather than the reset
  page, whose copy ("your new password must be different from your previously
  used password") is nonsense to someone who never had one — same form, same
  validation, different wording. Untick the box and the old
  admin-types-a-password behaviour is unchanged.

- Reporting: a multi-turn **AI chat panel** (`#rpChatToggle`, both Simple and
  Advanced tabs) replaces the old single-shot "Ask AI" surface — a docked
  slide-over with a conversation thread, a per-turn collapsible tool-step
  trace, and follow-up suggestion chips. `POST /api/reporting/ai/agent` gains
  a `history` param (last 8 turns / 4000 chars, text-only) so follow-ups carry
  real conversational context instead of starting over each time.
- Reporting AI: **live progress in the chat panel**. `POST /api/reporting/ai/agent`
  accepts `"stream": true` and answers NDJSON — a `{"phase": ...}` line for each
  real step of the agent loop (`thinking` / the model's own `note` / the `tool`
  about to run), closed by exactly one `{"done": true, ...}` line carrying the
  usual payload. The panel's ticker now shows what the agent is actually doing
  ("Running the query…", "Checking the query…") instead of cycling three
  hardcoded strings on a timer. Callers that don't ask for the stream still get
  plain JSON unchanged, so a mid-stream failure rides the final line instead of
  an HTTP status.
- Reporting: an opt-in **comparison** — `compare: true` on
  `POST /api/reporting/run` reruns a definition with its single relative-date
  token filter shifted back by the window's own length and returns a
  `comparison` block (`columns`, `rows`, `priorStart`, `priorEnd`); the Simple
  tab's KPI band renders **delta chips** (↑/↓/flat + percentage) and an inline
  sparkline off it.
- Reporting: `POST /api/reporting/ai/caption` and **auto captions** — a
  `reporting.ai.explain_data`-gated 1–2 sentence AI narration that appears
  under a result's chart/KPI band after every successful run, silently
  no-opping on any failure.
- Reporting: chart/table formatting polish — integer axis ticks, rounded bars,
  a redesigned tooltip and categorical palette, data bars in the grid, KPI
  count-up animation, loading skeletons, entrance animation, and a sticky
  result toolbar.
- Prepared Documents: **filters, group-by, and a per-page selector** (#149).
  The register gained Collected/Prepared boolean filters, group-by (Collected
  by / Prepared by, an ORDER BY so same-valued rows cluster together), and a
  25/40/100/200 rows-per-page choice — all carried through the Previous/Next
  pagination links so paging never drops the active filters.

### Changed

- External API: source/client codes no longer appear anywhere on the
  surface — the `client` field is gone from `/api/v1/workitems` rows and
  the `/workitems/<id>` response, and the `?client=` query parameter is
  removed (now ignored). Detail lookups resolve the workitem's source from
  the key's process scope instead (registered sources tried in order,
  first in-scope match wins). Docs and the in-app API docs page updated.
- `GET /api/v1/avg_processing_time` (and its `/api/test/v1` twin) no longer
  echoes the key's `processes` list — like `/backlog` and `/undelivered`,
  scoping happens at key issuance, not in the payload. Docs updated.

- Reporting AI chat: the "Open in builder" chip on an agent answer is now
  "Open report" and lands the definition in the Simple result view instead
  of the Advanced builder (#178). A new `window.ReportingSimple.openDefinition()`
  seam (modeled on `openReport`) drives it; Advanced stays reachable via the
  result bar's escape hatch. Chat follow-ups now also carry the prior
  answer's produced SQL/definition forward as context in `history` (a
  `[sql from this answer]` / `[report definition from this answer]`
  convention, capped at 1500/1200 chars — raised the overall history cap
  from 4000 to 12000 chars to fit it), so a presentation-only follow-up
  ("show it as a chart") stays on the same query/data instead of the model
  re-deriving — or silently switching source for — one from its own prose.
- Reporting: forecasts fit on a widened history window (grain-dependent
  lookback — 56/182/730/1460/2190 days for day/week/month/quarter/year — for
  reports with a relative-date filter), so day-grain forecasts learn weekday
  seasonality instead of fitting on however little history the visible
  result happened to show (#178).
- Branch naming convention: release-cycle branches are now `v<x.y[.z]>` (e.g.
  `v3.1`); the pre-push branch-name guard accepts both the new form and the
  legacy `feature/<x.y.z>` for in-flight branches.
- Reporting page chrome now matches the rest of the app (#175) — the masthead
  ran outside any page container, so it was full-bleed against a white band
  while Dashboard and Workitems inset their titles in `.nx-main`. Header, view
  switch and both panes now share one container with the same 1600px/40px
  metrics, and the band + its hairline are gone. The Simple/Advanced switch
  moved out of the header's action row (where it sat as a pill between
  *Sources* and *AI chat*, reading as a third button) into a page-level tab rail
  under the title, using the app's standard `.nx-tabs` underline bar — so
  primary navigation no longer looks like the segmented toggles inside the pane
  it navigates to. *Sources* is admin plumbing rather than a daily action and is
  now a quiet ghost link at the right end of that rail.

- Workitems: the doc-field filter is now **Document Value Search** (#148) — its
  own always-visible section below the base filters instead of a row buried in
  the Advanced toggle, and it searches **value-first**: with no field selected
  the value is OR-matched across every permitted, non-sensitive field (default
  SQL Server + MS02 columnar paths, fail-closed contract unchanged), and
  `/api/docfield_values` returns labeled `{value, field}` suggestions whose
  pick locks the pair field-precise. Every row carries an **operator**
  (contains, `=`, `≠`, starts with, ends with, does not contain) and each
  added row an **AND/OR** combinator — rows fold left-to-right, so
  `A AND B OR C` reads `(A AND B) OR C`. Also fixes the bug where suggestions
  fell back to `doctype`/the first field while the field box showed "no field
  selected" (the issue's screenshot).

- Dashboard: the page title is now plain **"Dashboard"** instead of
  `Welcome back, <name>! 👋` (#146). The emoji greeting repeated on every visit
  and read as unprofessional; the personal touch moves to a quiet
  `Signed in as <name> — <date, time>` meta line that renders **once**, on the
  first dashboard load after login (session flag `show_login_note`, stamped in
  `_record_active_session`), and disappears on any later visit or refresh. The
  note also carries `Last sign-in: <date, time>` — the previous login stamp,
  kept on `dbo.Users.LastLoginAt` (migration `0049`) because `ActiveSessions`
  rows are deleted on logout and cannot answer it. Absent on a first-ever login.

- Footer: `_small_footer.html` is now scoped to the **logged-out surfaces** and
  removed from the 13 app pages that carry the sidebar (`dashboard`, `invoices`,
  `profile`, `workitems_overview`, all nine `generali_*`). It is a marketing
  footer — a 96px sydoc logo and six links to sydoc.ch public pages — and once
  the version moved into the profile dropdown it had no functional content left
  on an app page, while the sidebar already carried navigation. It stays on
  `index`, `hero`, `forgot_password`, `reset_password`, `set_password`,
  `init_reset`, `init_2FA`, `verify_2fa` and the error pages, which have no
  sidebar. The support mailto (`support.helpdesk@sydoc.ch`) moves into the
  profile dropdown so a logged-in user can still reach it. `Help` is an existing
  msgid, so no new translations. The rule is enforced by
  `tests/unit/test_template_layout.py`: no template may render both the shell
  and the footer, and the footer must still reach login and the error pages —
  it had already drifted once, present on 22 templates and missing from the 12
  newest. This also retires the last dark-mode contrast failure in the footer
  (the copyright line sat at 3.75:1); none of the remaining pages implement dark
  mode, so the fix is the removal rather than a CSS override.

- Reporting: the Simple tab's "Ask AI" bar/chips and the Advanced tab's
  "Ask AI" mode now both route into the shared AI chat panel above, instead of
  each running its own one-shot ask/refine flow.
- Reporting: the page's dark-mode support is repaired end to end (design
  tokens instead of hard-coded light-mode hex, dark-mode-aware chart
  segment borders).
- Reporting AI: the Azure request body now sends `max_completion_tokens`
  instead of the deprecated `max_tokens`, so GPT-5-family deployments
  (e.g. `gpt-5-mini`) work; older chat models keep working unchanged.
  Set `AZURE_OPENAI_API_VERSION` to a GPT-5-capable version (e.g.
  `2025-01-01-preview`) when pointing `AZURE_OPENAI_DEPLOYMENT` at one.
  The SQL and report-builder prompts also stop the model AND-merging
  multi-count questions ("imported today and exported today").

### Removed

- `GET /api/v1/stats/today` removed from the external API documentation
  (#181) — both `docs/howto/external-api.md` and the in-app `/api-docs` page
  now start from `/backlog`. It was scaffolding built to prove out the
  auth/routing structure before `/backlog` shipped as the actual first
  client-facing endpoint (#158) and was never meant for clients to call. The
  route itself (and its `/api/test/v1/...` twin) stays live in code —
  undocumented, not deleted.
- Bexio dropped from health monitoring (#177), following the archived invoices
  page it was the only consumer of. `nx --doctor` no longer runs the Bexio
  check or requires `BEXIO_PAT` in its env-key list, `ops/outage_monitor.py`
  no longer emits the `bexio:api` probe, and migration `0058` deletes that
  component's `dbo.StatusComponents` row so it stops rendering on the admin
  status page (open incidents are closed, history kept). `BEXIO_PAT` stays in
  `nx_lib/config.py` and the `env/*.env.example` templates — the archived
  `nx_lib/views/invoices.py` still imports it.
- Invoices page archived (#177). The Bexio-backed `/invoices` page is retired:
  its three routes (`/invoices`, `/api/invoices`, `/invoice/<id>/pdf`) are no
  longer registered and now 404, the sidebar entry and Ctrl+K command are gone,
  and `page_visibility()` no longer returns `invoicesPagePerm`. Nothing is
  deleted — `nx_lib/views/invoices.py` stays in tree (marked ARCHIVED in its
  docstring, helper tests kept) and its templates moved to
  `templates/archive/invoices.html` + `templates/js/archive/_invoices_js.html`,
  matching the `archive/` convention used for the retired chat page. Migration
  `0056` renames `dbo.ClientInvoices` to `dbo.decapitated_ClientInvoices`
  (data preserved, one `sp_rename` to undo). The `invoices.*` permission rows
  are deliberately left in `dbo.Permission`. Reviving the page means all three:
  re-register the routes, restore `invoicesPagePerm` + the nav entries, and
  rename the table back.

- `db-standard/` — the standardised statistics-DB schema proposal (shipped
  dev-side in 2.5.64) is withdrawn; its deploy-exclude and `.gitignore`
  entries go with it.
- Chat: the 1-on-1 chat page and all `/api/chat/*` routes (conversations,
  messages, send, upload). `chat.html` / `_chat_js.html` are moved to
  `templates/archive/` / `templates/js/archive/` rather than deleted.
- Workitem collaboration: tags, priority, assignment, and comments with
  `@mention` autocomplete, including the API routes
  `/api/workitem/<id>/comment`, `/api/workitem/<id>/assign`,
  `/api/workitem/<id>/priority`, `/api/workitem/<id>/tags`, `/api/tags`,
  `/api/users` and `/api/workitem/<id>/interactions`, and the tag /
  priority / assigned-to filters (and their header cells) on the workitems
  overview.
- The notification bell end to end: both routes (`/api/notifications`,
  `/api/notifications/mark_as_read`) and the header bell UI (icon, panel,
  60s poll).
- Eight now-dead permission codes, deleted by migration `0043`:
  `chat.view`, `workitems.details.add.tag`,
  `workitems.details.set.priority`, `workitems.details.assign.users`,
  `workitems.details.add.comment`, `workitems.filter.tag`,
  `workitems.filter.priority`, `workitems.filter.assignedUser`.
- The nine now-dead chat/collaboration/notification tables — renamed with a
  `decapitated_` prefix by migration `0042`, data preserved and reversible:
  `Chat_Conversations`, `Chat_Messages`, `Chat_Participants`, `Tags`,
  `Workitem_Tags`, `Workitem_Comments`, `Comment_Mentions`,
  `Workitem_Metadata`, `Notifications`.
- Reporting: the inline "Ask AI" panel (`rpAiPanel`, its Build/Write SQL/Agent
  sub-modes) and the Simple tab's dedicated AI **Refine** bar are removed,
  superseded by the AI chat panel above.
- Dashboard: the customizable-widget engine — six routes
  (`/api/dashboard/field_metadata`, `GET`/`PUT` `/api/dashboard/layout`,
  `/api/dashboard/layout/reset`, `/api/dashboard/widget_data`,
  `/api/dashboard/widget_compare`), the layout validator + default layout, and
  the whole widget query builder (~970 lines of `nx_lib/views/dashboard.py`).
  Backend-only since the 2026-04-27 customizable-dashboard plan: no template
  ever called it, and its `dbo.FieldMetadata` / `dbo.DashboardLayouts` tables
  were left as a manual SSMS step nobody ran, so every one of those endpoints
  500'd on every environment. Nothing to drop in SQL — the tables exist on
  neither INT, PROD nor TEST. The dashboard page, its four KPI/chart endpoints,
  `set_filter` and the recent-activity feed are untouched.

### Fixed

- `GET /api/v1/workitems` now answers
  `400 Field '...' is not available for your process scope` when a doc-field
  filter names a real field that is mapped for none of the key's processes —
  previously the pair silently resolved to an empty allow-set and the call
  returned `count=0` with no hint.

- Admin: the dev-server env switch works in both directions (#198). Restarting
  into STAGING made the "Restart nexora" control disappear, stranding the
  instance there: STAGING resolves *every* database — NexoraDB included — via
  `DB_SERVER_PRD`, i.e. the prod server, where the `admin.restart` permission
  row from migration `0059` does not exist. The control and `POST
  /api/admin/restart` now also accept a loopback caller (the trust rule the
  `/dev/*` routes already use), so a missing permission row in whichever
  NexoraDB the current environment points at can no longer strand the dev
  server. The template's guard also stopped depending on an `is_prod` variable
  the route never passed (always undefined, so always truthy) and uses the
  route-computed `can_restart` instead.
- Reporting user guide corrected against verified page behaviour: coverage-badge
  denominators (measures count all accessible processes, categories the current
  selection), per-pane chart caps, the drill-drawer export's 100-row cap, the
  Simple tab's greyed-out (not hidden) Forecast toggle, per-tab Save semantics,
  decorative library-card previews, and the retired AI "transparency line"
  (checking an AI result now goes through "Open report").
- Reporting: the Simple hero no longer overlays open reports (#178).
- Reporting: clearer self-repair hints for AI SQL errors 156/205/209 (#178).
- Reporting: `Open in Advanced` now actually runs the report — it used to
  only pre-fill the builder's wells, leaving Advanced showing no results and
  "Show query" hidden/stale until the user pressed Run themselves (#178).
- The two login e2e smokes clicked the 2FA submit button that the auto-submit
  challenge (since `a749bda`) removes from under them — they now fill the code
  and wait for the redirect. The e2e server port is overridable via the new
  `NEXORA_E2E_PORT` env var (default `8765`) so parallel checkouts and gate
  runs stop colliding on one hardcoded port.
- Reporting: date and datetime cells in results rendered as HTTP dates
  (`Thu, 26 Mar 2026 08:56:28 GMT`) (#175). `_json_safe` passed them to Flask's
  `DefaultJSONProvider`, whose date format that is; it now formats them as
  `yyyy-MM-dd HH:mm:ss` / `yyyy-MM-dd` — sortable and locale-free. Exports are
  unaffected: xlsx/csv serialize the raw rows, not the JSON payload.
- Hero page's step-connector line (Import → Extraction → Validation →
  Delivery) rendered invisible (#192). `hero.html` loads Tailwind via the v3
  Play CDN, which uses a `!`-prefix for important (`!left-[2rem]`), not the
  v4 `!`-suffix form (`[left:2rem]!`) the markup used — the CDN's JIT never
  generated those rules, so the connector's positioning container collapsed
  to zero width. Converted all 8 affected utilities to the v3 prefix form.

- Admin: every `page_header` action button was dead — the #193 CSP work
  (finding 10) removed the macro's inline `onclick` attribute but never added
  a replacement binding, so "Add banner", "Add organization", "Export CSV"
  and "Refresh" did nothing. The macro now emits `data-nx-click` and
  `_header.html` binds it through one delegated listener.
- Workitems: `media_raw_pdfpage_`/`media_raw_tif_` page-image cache keys
  omitted the client domain, so colliding workitem ids across clients served
  each other's rendered page images for up to an hour. Routed through the
  same `_wi_cache_key` idiom as the sibling media/audit caches.
- Process/Dashboard: `prepare_process_selection_sql`/`_lists` and the
  activity/backlog readers (`recent_rows`/`backlog_count`) built independent
  client and process IN-lists that, ANDed together, authorized the full
  client × process cross product instead of only the granted pairs — a
  caller granted `(A, P1)` and `(B, P2)` could also read `(A, P2)` and
  `(B, P1)`. Both source dialects now build an OR-joined `(client = ? AND
  process = ?)` predicate from the granted pairs directly.
- Reporting: the scheduled runner fell back to every allowed process across
  all clients whenever a schedule's requested/allowed scope intersection
  was empty, silently widening a client-scoped schedule instead of failing
  it. Reuses the interactive run's `_effective_scope` (never-widen, fails
  the run via `QueryBuildError` on a genuinely empty scope).
- Dashboard: the recent-activity feed leaked sensitive-configured doc-fields
  (missing the `strip_sensitive_fields` gate every other doc-field surface
  applies) and omitted `client` on each row, so a colliding id's
  click-through could deep-link into the wrong client's workitem.
- Generali: `api_generali_reporting_list` built its filter from request
  params only, so a `generali.reporting.view`-only caller saw every
  organization's rows. Applies the same `restrict_to_self` gate as the
  sibling Attendance/BaseServices/ProjectManagement/PDQM endpoints.
- Reporting: the AI agent's `run_sql_bound` tool called `_run_sql` directly,
  skipping the per-target permission check and sandbox-ack gate the HTTP
  run view enforces. Now mirrors the HTTP gate order exactly and audits
  refusals with a distinct status.
- Workitems: `api_docfield_values` was gated only by the blanket
  `workitems.filter.documentfields` permission, letting an unvalidated
  `process` argument pull value suggestions from any process — including
  ones the caller holds no `workitems.filter.process.<p>` grant for. Now
  restricted to the caller's allowed processes, failing closed to `[]`.
- Admin: the user-detail access-profile `<select>` only listed the editing
  admin's own assignable profiles, so an edited user whose current profile
  fell outside that set had no option selected and an untouched form
  silently reassigned them to whatever option render first on any
  unrelated save. The current profile is now always shown (labelled
  "current, not assignable" when outside the admin's set) and the server
  only enforces the assign-permission check when the value actually
  changes. Round-2 (browser-verified): a `<select>` option that is both
  `selected` and `disabled` is dropped from `FormData` on submit in real
  Chromium/Firefox, so that same option meant `accessprofile` was missing
  from the request entirely — 403ing saves of unrelated fields too;
  dropped `disabled` from the template and treat a still-missing
  `accessprofile` server-side as "unchanged".
- Workitems: CSV export's ≤10-row cap for heavy includes
  (fields/history/images, each a per-row Octo fetch) lived only in the JS
  control — a direct API call with an unbounded `include=` could walk up
  to `EXPORT_MAX_ROWS` rows of per-row Octo fetches. Now enforced
  server-side (D-CSVLIM).
- Workitems/MS02: a cluster of compound-identity (client + id) bugs in the
  Prepared Documents register — wid→stage resolution used the default
  client's Octo engine instead of MS02's Postgres runtime; the register
  preview omitted `?client=`, so a colliding id could preview the wrong
  client's document; `resolve_ms02_wids_to_pids` compared a varchar column
  against an int list with no cast, raising a PG operator-type error and
  silently killing the reverse "In register" chip; the in-register map was
  keyed on the bare id instead of `${client}-${id}`, so a colliding
  default-client row inherited MS02's chip; and the page-list cache-warm
  loop wrote through `_cache_store` directly, bypassing the collision
  probe and pinning an ambiguous id to whichever client's page listed it
  first. Follow-up: the warm loop's own already-built `active_sources()`
  list is now threaded into the probe instead of rebuilding it per row,
  closing an N+1 the initial fail-safe fix introduced.
- DB health: `ping_dbs_parallel` awaited each future's timeout serially, so
  N down engines took N × timeout wall time instead of the documented
  ~timeout. Replaced with one shared `concurrent.futures.wait(...,
  timeout=...)` deadline.
- Octo: `get_media` returned response bytes with no status check, so a
  502/HTML error page from Octo was cached as valid page bytes for an hour
  by every caching caller. Added `raise_for_status()` so a non-2xx response
  is treated as a cache miss.
- Reporting: `wrap_with_cap()` wrapped `WITH`-rooted queries in
  `SELECT TOP (n) * FROM ( WITH ... ) AS _q` — invalid T-SQL — and the same
  bug resurfaced for the idiomatic `;WITH` (leading-semicolon) form after
  the first fix only widened the bare-`WITH` case. CTE queries now pass
  through unwrapped (either form) with the cap enforced fetch-side via
  `fetchmany(cap + 1)`. Follow-up: a CSV export whose 120s Octo-fetch
  budget elapsed before any row completed derived its include columns from
  zero completed rows, producing an empty-looking export indistinguishable
  from a legitimate zero-result one; now surfaced via the same
  trailer-line + `X-Export-Timeout` header pattern used for row truncation.
- Dashboard: categorical widgets whose dimension resolves to the `?`
  bound-param sentinel (a constant label, not a real column) emitted
  `GROUP BY 1`, which T-SQL groups by the literal constant rather than
  ordinal position, 500ing the widget. `GROUP BY` is now omitted for that
  case.
- Workitems: `as_completed()` itself (not just `future.result()`) can raise
  `TimeoutError` at the CSV export loop's 120s boundary, 500ing large
  exports instead of returning the rows that did complete.
- Reporting: KPI cards sent their definition's `columns`/breakdown
  verbatim, so a breakdown-carrying definition made the card show the
  first bucket instead of the true total (both the headline number and its
  trend clone). Cleared for the KPI run payload so the backend returns a
  single zero-dimension row.
- Reporting: the global-filter popover's cached-catalog promise resolved in
  a microtask that ran before the outside-click closer attached, so every
  open after the first self-closed instantly. Deferred with `setTimeout`
  so popover creation happens after the triggering click finishes.
- Reporting: an unparseable drill-through grain-bucket label silently
  dropped that field's filter while the drawer still opened unfiltered,
  showing every row — now falls back to an equality filter on the raw
  value or aborts with a toast when even that isn't constructible. A
  follow-up fix separated the genuinely-`NULL` bucket case (a grained
  chart's own "(empty)" bucket) from the parse-failure case, which had
  been wrongly routed into the same abort-with-toast path instead of the
  `is_null` filter the non-grained branch already used correctly.
- Config: env-specific dotenv (`env/{ENVIRONMENT}.env`) now loads before
  the root `.env` fallback, matching the documented OS env > env-specific
  file > root `.env` precedence (the load order had it backwards).
- Auth: the password-reset flow got three rounds of hardening. First, a
  registered email visibly took longer to answer than an unregistered one
  (the Graph mail send blocked the response) — dispatched to a daemon
  thread to close the timing oracle. Second, reset tokens are now
  single-use (a hashed, TTL-matched cache marker) and the session
  capability is dropped on every exit path, not just success; the two
  bare `except Exception: return` branches (handing Flask `None` → 500)
  now log, flash a neutral message, and redirect to login. Third, a
  UX/security follow-up: token consumption moved from GET-render (a
  refresh, tab-restore, or mail-gateway link scanner burned it before the
  user clicked) to a successful write, and the write itself now re-checks
  the single-use marker immediately before writing — closing a
  cross-session replay window the consume-on-write change had briefly
  left open — while a mistyped confirmation keeps its retry path instead
  of losing the session capability on every exit.
- Admin: log search returned raw datetime rows straight to `jsonify`
  (Flask renders as RFC-1123/GMT, shifting displayed times by the server's
  UTC offset) — both the search and recent-logs routes now emit
  `.isoformat()`. `HttpResponseCode` is `NVARCHAR`, so the recent-logs
  int-range comparison `TypeError`'d (guaranteed 500) — now coerced first.
  Seven live admin templates linked a `output.css` that was never built or
  shipped, 404ing on every load. The access-control drawer defaulted every
  permission radio to Deny, so saving an untouched drawer wrote an
  explicit Deny row for every permission instead of only the ones actually
  set — now defaults to the neutral/inherit state, and a follow-up fix
  restored that neutral option's visibility in profile mode (it had been
  hidden entirely, recreating the same noise-row problem). The "Last hour"
  log preset truncated through a date-only formatter and actually filtered
  the whole current day; sub-day presets now carry a datetime-precision
  override. A race-condition follow-up: the first manual date edit right
  after clicking a preset was discarded by handler registration order —
  the override-clearing now happens in the same change handler that
  triggers the refetch.
- Octo: a transient DB read failure in `get_index_field_mappings` cached an
  empty `{}` for the full 1h timeout instead of leaving it a miss; and
  `get_workitemdata_param` raised `KeyError` past its
  `RequestException`-only except clause on a missing `DocumentID`,
  crashing the activity feed and other callers expecting a falsy sentinel.
- Workitems: `_count_image_media` counted every image-extension media item
  while the source-overlay renderer skips URL-less ones, misaligning page
  offsets between the overlay boxes and the pages Octo actually renders.
- Process: an activity-ignore name containing an embedded single quote
  (e.g. "O'Brien Review") broke the raw quote-concatenated `NOT IN (...)`
  SQL fragment; quotes are now doubled before splicing (full
  parameterization of this list is a follow-up, not done here).
- Reporting: the docprocessing catalog read `SearchConfig` with no
  `ClientCode` filter, letting MS02's columnar rows leak phantom field
  availability into the default catalog. Scoped to `ClientCode =
  'default'`, mirroring the workitems doc-field path.
- Reporting: XLSX/CSV export cells containing raw bytes or openpyxl's
  illegal control characters raised instead of exporting; cells are now
  decoded/stripped (and other non-primitive types stringified) before the
  formula-injection guard.
- Reporting: `MIN`/`MAX` aggregates on varchar stat columns compared
  lexicographically ("9" > "10"), so the numeric `TRY_CAST(... AS float)`
  wrap already applied to `SUM`/`AVG` bases is now applied to `MIN`/`MAX`
  too. A follow-up scoped that wrap to require the field actually be a
  stat column, so it no longer incorrectly wraps synthetic date/workitem-id
  fields (a `TRY_CAST` of a date to float is a hard error).
- Reporting: the SQL sandbox's keyword-blocklist scanner went through
  three hardening rounds. Round 1 stripped string-literal contents so a
  blocked keyword inside a quoted literal no longer false-positived.
  Round 2 closed a bypass the round-1 stripper introduced: its
  apostrophe-pairing was blind to T-SQL bracket- and double-quoted
  identifiers (which legally contain a bare apostrophe), so a crafted
  alias like `` AS [a'b] `` shifted the pairing and could hide a blocked
  keyword — plus two related gaps letting `OPENROWSET` slip past the
  blocklist while still parsing as a harmless `SELECT`. Round 3 closed
  what the first two missed: a `--` comment could hide a keyword behind a
  bare carriage return with no following newline, and the bracket-matching
  regex introduced in round 2 was vulnerable to catastrophic backtracking
  (ReDoS) on crafted input.
- Reporting: `validate_schedule` guarded `int(hour)`/`int(minute)` against
  non-numeric input but not `int(weekday)`/`int(dayOfMonth)`, so a bad
  value raised an uncaught `ValueError` (500) instead of a validation
  error.
- Reporting: stat group-key sorting compared `""` against numeric keys
  (`TypeError` on mixed int/`None` group keys); now sorts on
  `(v is None, str(v))` so NULLs always sort last without a cross-type
  comparison.
- Reporting: a single corrupt report definition (unexpected shape in
  `_preview_kind` or per-row serialization) 500'd the entire report
  library listing for every user; both paths are now type-guarded with a
  safe fallback so only the one row is skipped.
- External API: `_default_stat_rows`/`_ms02_stat_rows` swallowed any
  failure into an all-zeros result, so a Statistics-DB outage was
  indistinguishable from a quiet day and `/api/v1/stats/today` returned
  200 zeros instead of the documented 500. The external API now opts into
  strict failure surfacing; the dashboard's graceful degrade is unchanged.
- Generali: `api_generali_stats` called `.replace("T", " ")` directly on a
  possibly-absent query param, raising `AttributeError` (500) instead of a
  clean 400 when `startDate`/`endDate` were missing.
- Workitems: CSV export's field-fetch helper cached a reduced
  `{fields, media_count}` shape under the same `media_info` cache key the
  detail-panel API serves, silently emptying the source overlay on the
  next request for that workitem.
- Reporting: the dashboard's client-side filter merge keyed by field with
  last-write-wins, so two distinct filters on the same field (e.g. a range
  split across `gte`/`lte`) silently collapsed to just the last one,
  widening the card's query. Now concatenates and dedupes only exact
  duplicates.
- Reporting: switching sources in the Advanced builder reset
  columns/scope/metrics but left old filters in place, so the prior
  source's chips (referencing fields that might not exist on the new
  source) survived and 400'd every Run until cleared by hand.
- Reporting: pivot row/column bucket keys joined dimension tuples into a
  single string, colliding distinct tuples (e.g. `['ab','c']` vs
  `['a','bc']`); keyed with `JSON.stringify` instead.
- Workitems: the last-movement column's client-side sort expected a
  `"d. m. yyyy - HH:MM"` date format but the table renders ISO
  `"YYYY-MM-DD HH:MM:SS"`, so every comparison was `NaN` and clicking the
  header was a silent no-op.
- Profile: the change-password GET handler fell through with no return,
  handing Flask `None` and a 500; now redirects to the profile page.

- **Reporting: dashboard cards render two-dimension reports** (#174) — the card
  renderers were single-series v1 and read a fixed column 1 as the value, so a
  saved report with a second dimension ("per month / process") put the
  breakdown column into the value lookup: every chart card drew one flat
  zero line and KPI/donut/table cards showed the breakdown text where a number
  belonged. Line and bar cards now pivot the second dimension into named,
  colored series (the same pivot the Simple result view has always done, with
  a legend and an 8-series cap that reports its overflow instead of truncating
  silently); donut and table cards join the dimensions into one label
  ("Jan · Invoice") rather than mis-reading one of them; and drill-through
  carries one chip per dimension, so clicking a series point drills into that
  series, not into every series for that bucket.
- Reporting: scheduled table-source reports with a date grain no longer fail
  validation in the runner (missing `grainable_fields`).
- **Reporting: export date and import date can be broken down together**
  (#164) — the Simple wizard's two "Over time" chips were mutually exclusive
  (picking one silently dropped the other), even though the query builder has
  always applied grain per column and the Advanced tab allowed both. Selecting
  a second date is now a normal 2-dimension group-by (first date = chart X
  axis, second = series), within the same 3-breakdown cap. Both dates share
  the single grain select. Follow-ups this exposed: the chart legend printed
  the second date as a raw ISO datetime, and chart drill-through filtered
  non-leading dimensions on an equality instead of the bucket range.
- **Mobile nav toggle / modal backdrop z-index collision** (#144, follow-up
  from #142) — `--z-nav-toggle` and `--z-modal-backdrop` both resolved to
  `60`, so an open reporting modal wasn't guaranteed to paint above the
  floating mobile nav toggle. `--z-nav-toggle` now sits at `59`. The
  remaining ~105 one-off inline styles in `templates/admin/*` and ~46 in
  `templates/js/*` partials are triaged as accepted/permanent (single-use
  compound declarations, no dedup value as CSS classes) — see #144 for the
  decision record.
- Prepared Documents: the **"Load more" button in the workitem preview modal
  did nothing** (#149) — the shared detail panel creates a `.load-more-btn`
  dynamically, but the click delegation for it only existed in the Workitems
  overview page's JS, which `prepared_documents.html` never includes. Wired
  the same handler into `_prepared_documents_js.html`. Also restyled **Clear
  list** as a destructive (red) action and gave the previously-unstyled
  pagination footer proper spacing/border.

- Workitem details: the **MWST amount showed the wrong value** (reported on
  PROD; INT had the same data). Two `dbo.IndexFieldMappings` rows carried
  swapped TargetKeys — `RptCompCode → VatAmount` rendered the SAP company code
  as "MWST. Betrag", and a duplicate `VatAmount → Client` row overrode the
  correct `VatAmount → VatAmount` mapping (the mapping dict is keyed by
  SourceFieldName, last row wins) so the real VAT amount surfaced as "Mandant".
  Migration `0052` re-points `RptCompCode` to `Client` and deletes the
  duplicate row.

- Reporting AI: the schema grounding for the per-process partial Statconfig
  tables (`dbo.Compass_Invoice`, `dbo.EM_Invoice`, …) only named each table's
  import/export date columns, so the agent guessed every other column (page
  count, document type, user, barcode) when drafting a raw-SQL UNION across
  them and hit `Invalid column name` in ~1 of 5 eval cases (#154). The block
  now also lists each table's SearchConfig `col_*` columns, sourced from the
  same per-process field map the `docprocessing` curated source already
  builds from.

- Reporting: Advanced tab overflowed horizontally at phone widths (375px,
  #143) — `document.documentElement.scrollWidth` measured 591-714px against a
  375px `innerWidth`. Two independent causes: (1) the 3-column builder grid
  (`.reporting-main`) already collapsed to a single `1fr` track below 1100px,
  but grid items default to `min-width: auto`, so the track still grew to
  each child's max-content width instead of shrinking — fixed with
  `min-width: 0` on `.reporting-fields`/`.reporting-results`/
  `.reporting-wells`; (2) the saved-report cluster (select + rename/share/
  delete links) and the Run/Save/Export action cluster are both
  `flex-shrink: 0`, so `flex-wrap` on the parent toolbar couldn't help —
  each now gets `flex-basis: 100%` + its own internal `flex-wrap: wrap`
  below 480px so it drops to its own row and wraps instead of overflowing.

- Shared logo partial (`templates/nexora_logo/_nexora_logo.html`) was a full
  standalone HTML document (`<!DOCTYPE html><html><head>...`) `{% include %}`'d
  as a fragment into `_header.html` (every logged-in page) plus the standalone
  auth/hero pages (#140). Every logged-in page loaded Tailwind **twice**, at
  two different major versions and from two different CDNs (`_header.html`'s
  v4 `@tailwindcss/browser` plus the logo partial's own v3
  `cdn.tailwindcss.com`), alongside invalid nested `<html>/<head>/<body>`
  markup. The partial is now a plain fragment (just the logo `<a>` + its
  scoped stylesheet link) — no DOCTYPE/html/head/body, no CDN script of its
  own.

- Admin: System Audit Logs search (`GET /api/admin/logs/search`) and the
  recent-activity feed 500'd whenever `dbo.Logs.Timestamp` came back as a
  `str` instead of a driver-native `datetime` (#134) — some rows are written
  by the external `ops/cleanup/csvLogs_toDB.ps1` CSV-ingestion path, which
  doesn't guarantee the same column type pyodbc returns for native writes.
  Both call sites in `nx_lib/views/admin.py` now guard with
  `hasattr(ts, "isoformat")` instead of assuming the type, matching the
  pattern already used by the CSV-export and dashboard-widget log readers in
  the same file.
- Reporting AI: **four answer-quality gaps the #131 eval exposed** (#132),
  all closed in the agent's grounding rather than in code. (1) Asked how many
  unique workitems were processed, the agent drafted
  `COUNT(DISTINCT WorkitemID)` across several per-process statistics tables
  and reported the result as a company total — wrong twice over, since one row
  in those tables already *is* one workitem (which is why the
  `workitem_count` metric is disabled, migration `0021`) and the ids collide
  across processes; the PARTIAL-tables block now states both facts. (2) Vague
  questions ("show me the numbers for the last quarter") got a silently-picked
  reading presented as the answer — the agent must now open with one sentence
  naming the reading it used and the main alternative. (3) Answers omitted the
  caveats a stakeholder needs: a still-running current period, percentages off
  a near-zero baseline, silently excluded/assumed-NULL rows, "yes it's
  seasonal" from a single row — a four-item checklist is now part of the
  prompt. (4) The agent quit with turns left, telling the user to run the
  comparison themselves, and presented unexecuted SQL as if it had produced
  numbers — both now explicitly forbidden.

- Reporting: the page masthead (Simple/Advanced tabs, Sources, AI chat) and
  the Simple tab's "Ask AI" bar overflowed horizontally on phone widths
  (#136) — the header didn't wrap, and the AI input had no `min-width: 0`
  so it couldn't shrink below its default intrinsic width, pushing the Ask
  AI button off-screen. The masthead now wraps onto a second row below
  640px (matching the AI-chat button's icon-only collapse Sources already
  had), and the input shrinks properly in its flex row.

- Admin (Access Control, Maintenance, Organizations, User Detail): these pages
  load `admin.css` only, but their templates use Tailwind-style utility
  classes (`hidden`, `fixed`, `top-4`, `z-[...]`, `w-full`, `max-w-xs`,
  `space-y-3`) with no matching rules on the page — the classes were silent
  no-ops (#137). Worst case: Access Control's tab-hiding, which uses
  `class="hidden"`, didn't hide anything — the off-tab panel just got pushed
  offscreen by layout while its inputs stayed focusable and screen-reader
  visible. Added the handful of real rules actually used to `admin.css`.

- Invoices/Generali Documents: the filter forms on both pages submit as GET
  but shipped a hidden `csrf_token` field anyway (#139). Flask-WTF doesn't
  validate CSRF on GET requests, so the field was dead weight that leaked
  the session-bound token into the URL/browser history on submit — most
  visibly on Invoices, whose JS builds the query string from the full
  `FormData` (including hidden fields) and pushes it into
  `window.history`. Dropped the hidden field from both forms; both already
  send the real CSRF token via the `X-CSRFToken` header on their AJAX
  calls.

- Admin: the "Active Sessions" page and the overview's active-sessions count
  now actually reflect recent activity (#109). Both previously filtered on
  `ActiveSessions.CreatedAt` — set once at login and never updated — so a
  session logged in 23 hours ago and never touched again still counted as
  "active". Added `ActiveSessions.LastSeenAt` (migration `0045`), bumped on
  every request by the existing per-request session-enforcement hook, and
  changed both queries to a 30-minute `LastSeenAt` window, matching what the
  page's subtitle already claimed.

- Dashboard: the "Documents Processed by Hour (Today)" chart rendered an empty
  grid with no explanation when there was nothing to show yet (#142). It now
  hides the chart and shows a "No documents processed yet today." empty state,
  matching the pattern already used on the Generali Month Report page.

- Generali: Import Status no longer prefixes every filename with its raw
  dedup GUID (#142) — e.g. `b76b9747-...-NewDocsOverall_Final_Mail.csv` now
  displays as `NewDocsOverall_Final_Mail.csv`, with the original full name
  still available via a tooltip.

- Accessibility: added missing `alt` text to the document-preview `<img>`
  used in the Workitems, Reporting, and Prepared Documents image lightboxes
  (#142).

- Auth: **nobody could stay logged in** — migration `0045` made
  `ActiveSessions.LastSeenAt` `NOT NULL` without a default, but neither INSERT
  in `_record_active_session` supplies it, so every login failed to record its
  session; the next request then hit `_enforce_active_session`, found no row,
  and cleared the session. Migration `0047` gives `LastSeenAt` the same
  `DEFAULT (getdate())` that `CreatedAt` already had, fixing every INSERT site
  at once. Found while verifying #128 against a running INT instance.

- Reporting AI: the agent answered **company-wide questions from a single
  process table** and presented the result as the whole company (#128). The SQL
  grounding is a flat `INFORMATION_SCHEMA` dump, so `dbo.Compass_Invoice` looked
  exactly like a company-wide fact table; the agent picked whichever one its
  schema inspection surfaced first. Worst case was a confident **zero** for "the
  numbers for the last quarter" — correct SQL, correct dates, wrong universe.
  The schema block now opens with the `Statconfig` table→process map marked as
  per-process **partial** tables (`serialize_partial_tables`) — with each table's
  import/export date columns, which differ per table — naming the curated source
  that unions them and declaring itself complete, so the unregistered tables the
  agent liked most (`dbo.BFH_Statistic`, `dbo.DPSLicenseCounter`) are marked as
  outside the reporting universe. `_AGENT_SYSTEM` turns the old advisory
  "name which table(s)" line into a hard rule: totals questions naming no
  process are company-wide, raw SQL must UNION the partial tables, every SQL
  answer states its coverage, and a zero from one partial table is reported as
  zero *for that process*. The explain-data suffix no longer reads as licence to
  narrow the universe to reach `run_sql`.

- Auth: the 2FA challenge (`/verify_2fa`) now auto-submits once the code field
  holds 6 digits, instead of requiring a manual click on "Verify Identity"
  (#107). Non-digit input is stripped client-side as it's typed.

- Version: `uv.lock` had silently rotted to `2.5.63` while `nx_lib/version.py`
  and `pyproject.toml` were on `2.5.65` — a third copy of the version that no
  test covered. Refreshed via `uv lock`, and `tests/unit/test_version.py` now
  asserts all three agree. The `pyproject.toml` duplicate itself stays: uv
  rejects a `[project]` table whose version is neither static nor supplied by a
  build backend, and nexora is a virtual project that is never built, so the
  only way to remove it would be to add a build backend. Both copies now carry
  a comment saying so.

- Reporting SQL sandbox: a query with a top-level `ORDER BY` passed
  `validate_select` but then failed at run time with SQL Server error 1033 —
  `wrap_with_cap`'s `SELECT TOP (n) * FROM (…) AS _q` wrap made the trailing
  `ORDER BY` illegal inside the derived table (#129). Such queries now pass
  through unwrapped, exactly like the WITH-rooted path, with `fetch_capped`
  enforcing the row cap fetch-side. Hit both the human sandbox and the AI
  agent's `run_sql` tool, where the validate-ok/run-fail disagreement burned
  self-repair turns (one eval case spent all 10 turns on it).
- Reporting AI: the chat agent could return a completely **empty answer** —
  either a silent model turn with no tool calls, or the turn cap exhausting
  with no prose written (#127). The loop now nudges the model exactly once to
  write the answer it owes (`ask_agentic_iter`), and if the answer is still
  empty the response substitutes a localized, artifact-aware fallback (points
  at the produced report draft / SQL, or admits the request failed) instead of
  an empty string. The audit row keeps the raw empty answer.
- Workitems: the line-item table grids in the detail panel's "Show sources"
  view (e.g. Octo `TABVAT`/`TABORDER`) overflowed the panel on wide tables
  and showed raw Octo field codes (`TabNetAmount`, `OrdPk`) as headers.
  `renderTableGrids` no longer renders an HTML `<table>` at all — each grid
  is now a collapsed-by-default `<details>` ("TABVAT (2 rows)") that opens
  into the same `dt`/`dd` field-row list already used for scalar fields,
  one group per row, with labels routed through the same `fieldConfig.labels`
  lookup (falling back to a camelCase-split version of the raw code, e.g.
  "Tab Net Amount", when no `Search_Field_Labels` row exists).
- Profile: `GET /update_profile` returned 500 — the view only returned inside
  its `POST` branch, so a GET fell through to `None`. It now redirects to
  `/profile`, matching the same fix applied to `change_password`.
- Reporting AI: hard questions failed with *"The AI assistant could not answer
  right now"* on reasoning deployments (GPT-5 family). The per-call HTTP read
  timeout was hard-coded to 30 s while such a model routinely spends 30–60 s on
  one turn, so the request died mid-loop. The timeout is now `AI_TIMEOUT_S`
  (default **120 s**), and a whole agentic run is bounded by `AI_AGENT_BUDGET_S`
  (default **180 s**, checked between turns) so the longer per-call timeout
  cannot pin a worker for `max_turns × AI_TIMEOUT_S`.
- Reporting AI: the chat agent gave up on questions needing two
  differently-filtered measures side by side (e.g. *"month, imported documents,
  exported documents"*), splitting them into two separate reports — a
  definition's filters apply to the whole report, and the prompt also told the
  agent to stop as soon as *any* tool returned `ok:true`. It now falls back to
  one live-SQL draft with conditional aggregation for that shape, stops only on
  the artifact that answers the whole question, and names the per-process
  table(s) its numbers come from.

The following are the 57-finding 2026-07-23 bug-hunt's Part B fixes (Tasks
13-64), landed alongside the Part A removal above.

- Workitems: PDF/TIF page-image caches were keyed without the client domain,
  so colliding workitem ids across the Octo and MS02 clients could serve
  each other's **rendered page images** for up to an hour. Both cache keys
  now route through the existing `_wi_cache_key` helper, like the sibling
  media/audit caches.
- Process authorization: the "all" branch of `prepare_process_selection_sql`/
  `_lists` built independent client and process IN-lists that, ANDed
  together downstream, authorized the full client × process **cross
  product** — a caller granted only (A, P1) and (B, P2) could also read
  (A, P2) and (B, P1). Both twins, `WorkitemFilter`, and both workitem
  sources now build an OR-joined `(client = ? AND process = ?)` predicate.
  A follow-up found the dashboard's `recent_rows()`/`backlog_count()` had
  the identical bug independently (two separately-uniqued IN-lists) and
  applied the same fix.
- Reporting: the scheduled runner read only `scope.processes` and fell back
  to every allowed process whenever the requested/allowed intersection was
  empty, so a client-scoped schedule could silently **widen** to every
  client on that mail. It now reuses the interactive run's effective-scope
  logic (never widens) and fails the run instead of leaking data.
- Dashboard: the recent-activity feed skipped the canonical
  sensitive-doc-field gate every other doc-field surface applies, and
  omitted `client` on each row so its workitems deep-link couldn't
  disambiguate colliding ids across clients. Both fixed together.
- Generali: `api_generali_reporting_list` built its WHERE clause only from
  request filters, so a `generali.reporting.view`-only caller saw **every
  organization's rows**; it now applies the same self-scope gate as the
  sibling Attendance/BaseServices/ProjectManagement/PDQM endpoints.
- Reporting AI: the agent's internal `run_sql_bound` tool skipped the
  per-target permission check and the sandbox-ack gate the HTTP
  `/api/sql/run` view enforces; it now mirrors the exact gate order (ack,
  then target auth) and returns a tool-result error instead of a 500.
- Workitems: `api_docfield_values` let a caller pull value suggestions from
  **any process**, gated only by the blanket
  `workitems.filter.documentfields` permission; restricted to the caller's
  granted `workitems.filter.process.<p>` set, failing closed to an empty
  list.
- Admin: the user-detail form only listed the editing admin's own
  assignable access profiles, so editing a user whose current profile fell
  outside that set silently **reassigned them** to the first listed option
  on any unrelated save. The template now always shows and round-trips the
  current profile; the server enforces the assign-permission check only
  when the value actually changes. A browser-verified round-2 fix followed:
  a `<select>` option that is both `selected` and `disabled` is dropped
  from `FormData` by real browsers (Playwright-verified, not jsdom), so the
  round-1 fix's own unassignable-profile option vanished from the submit
  entirely — dropped `disabled`, kept `selected`, and treated a still-
  missing field server-side as "unchanged".
- Workitems: CSV export's ≤10-row cap on heavy includes (fields/history/
  images, all per-row Octo fetches) lived only in the JS control; a direct
  API call could send unbounded ids and walk up to `EXPORT_MAX_ROWS` rows
  of per-row Octo fetches. Enforced server-side.
- Workitems (MS02 compound identity, Prepared Documents register): a
  cluster of colliding-id bugs — wids resolved their Octo stage against the
  default client's engine instead of MS02's (added a Postgres-dialect twin
  of `resolve_octo_wid_stage`, later relocated next to its T-SQL sibling in
  `workitem_sources.py`); the preview button omitted `?client=`, risking
  previewing the wrong client's document; `resolve_ms02_wids_to_pids`
  compared a varchar column against an int list, raising a Postgres
  operator-type mismatch on every call; the "In register" chip map was
  keyed by bare id instead of `client-id`; and the page's cache-warm loop
  bypassed the collision fail-safe, letting a colliding id get pinned to
  whichever client's page listed it first. A follow-up removed the
  fail-safe's own N+1 cost — it rebuilt a fresh source list per
  non-default row instead of reusing the warm loop's own list.
- `ping_dbs_parallel` awaited each future's result **serially**, so N down
  engines took N × timeout wall time instead of the documented ~timeout;
  replaced with one shared `concurrent.futures.wait(..., timeout=...)`
  call.
- Octo: `get_media` cached a non-2xx response (e.g. a 502/HTML error page)
  as valid page bytes for an hour; added `raise_for_status()` so a bad
  response is treated as a cache miss instead of poisoning the slot.
- Reporting: `wrap_with_cap()` wrapped `WITH`-rooted queries into an
  **invalid** `SELECT TOP (n) * FROM ( WITH ... ) AS _q`; CTE-rooted queries
  now pass through unwrapped, with the row cap enforced fetch-side via a
  new `fetch_capped()` helper. Two follow-ups: the leading-`WITH` detector
  didn't recognize the idiomatic `;WITH` (leading-semicolon) form; and a
  CSV export whose 120s budget elapsed before any per-row fetch completed
  derived its include columns from zero completed rows, producing a
  marker-free export indistinguishable from a legitimate empty result —
  now flagged via the same `X-Export-Timeout` header/trailer pattern.
- Dashboard: a categorical widget whose dimension resolved to the `?`
  bound-param sentinel emitted `GROUP BY 1`, which in T-SQL groups by the
  literal constant rather than ordinal position and 500s; the clause is
  now omitted for that case.
- Workitems: `as_completed()` itself (not just `future.result()`) can raise
  `TimeoutError` at its own iteration boundary in large CSV exports; the
  loop now cancels pending futures and marks unfinished rows instead of
  500ing.
- Reporting: KPI cards sent their own `definition.columns` verbatim, so a
  breakdown-carrying definition showed the first bucket instead of the true
  total; columns/sort are now cleared in the KPI run payload and its trend
  clone so the backend returns a single zero-dim row.
- Reporting: the global-filter popover's cached-catalog promise resolved in
  a microtask that ran before the triggering click finished bubbling to the
  outside-click closer, so every open after the first **self-closed
  instantly**; popover creation is now deferred a tick.
- Reporting: an unparseable drill grain-bucket label made the drawer
  silently drop that field's filter while still opening — showing every
  row unfiltered; it now falls back to an equality filter or aborts with a
  toast. A follow-up fixed the opposite case: a genuinely NULL date bucket
  (a valid "(empty)" grain bucket, not a parse failure) was being treated
  the same as an unparseable one and aborted instead of drilling in with
  the correct `is_null` filter.
- Config: `env/{ENVIRONMENT}.env` loaded **after** the root `.env` instead
  of before it, inverting the documented `OS env > env-specific file > root
  .env` precedence.
- Auth: the password-reset mail send ran synchronously, so a registered
  email measurably answered slower than an unregistered one (a timing
  oracle); dispatched to a daemon thread. Reset tokens are now marked
  consumed (hashed, TTL-matched) so a token can't be replayed across
  sessions. Two bare `except Exception: return` blocks handed Flask a
  `None` response (a 500) instead of a neutral flash + redirect. Round-1
  follow-up: the token was being consumed on GET render — burning it before
  the user ever clicked — and the error branches rendered on a template
  that never shows flashed messages; moved consumption to a successful
  write and matched `login()`'s render idiom. Round-2 follow-up: round 1's
  retry-friendliness re-opened a cross-session replay window, since the
  write only checked the consumed-marker *after* writing — now checked
  before.
- Profile: `change_password`'s GET branch fell through with no return,
  handing Flask `None` (a 500); now redirects to the profile page.
- Admin: log-search and recent-logs timestamps were serialized as raw
  datetimes — Flask renders those RFC-1123/GMT, shifting displayed times by
  the server's UTC offset — both now emit `.isoformat()`. `HttpResponseCode`
  is `NVARCHAR`, so the recent-logs int-range compare `TypeError`'d on every
  row (a guaranteed 500); coerced before comparison. Seven admin templates
  linked an `output.css` that was never built or shipped, 404ing on every
  load. The permission drawer defaulted every radio to Deny, so an
  untouched drawer wrote an explicit Deny row for every permission instead
  of only the ones actually set — and, separately, the neutral/inherit
  column was hidden entirely in profile mode, so an admin could set
  Allow/Deny but never click back to unset. The "Last hour" log preset
  truncated through a date-only formatter and actually filtered the whole
  current day. A follow-up closed a registration-order race where the
  first manual date edit right after clicking a preset was discarded.
- Octo: `get_index_field_mappings` cached an empty `{}` result for the full
  1h timeout on a transient DB failure, disabling index-field lookups
  app-wide until the cache expired; only successful reads are cached now.
  `get_workitemdata_param` raised `KeyError` instead of returning falsy on
  a malformed payload, crashing the activity feed and other callers
  expecting a falsy "not found" sentinel.
- Workitems: `_count_image_media` counted every image-type media item, but
  the page renderer skips URL-less media — source-overlay boxes landed on
  the wrong page whenever a workitem had gaps in its media.
- Process: the activity-ignore CSV's raw quote-concatenated fragment didn't
  double embedded single-quotes, so a name like "O'Brien Review" broke the
  spliced `NOT IN (...)` SQL.
- Reporting: the docprocessing catalog read `SearchConfig` with no
  `ClientCode` filter, letting MS02's columnar rows leak phantom field
  availability into the default catalog.
- Reporting: `_safe_cell` didn't decode `bytes`/`bytearray`/`memoryview` or
  strip openpyxl's own illegal-character regex before the
  formula-injection guard, and other non-primitive types (e.g. UUID)
  weren't stringified; one fix covers both `export.py` and the view's own
  export path.
- Reporting: MIN/MAX over varchar stat columns compared **lexicographically**
  ("9" > "10"); extended the existing `TRY_CAST(... AS float)` wrap (already
  used for sum/avg) to min/max. A follow-up scoped the wrap to only genuine
  varchar stat columns — it was also being applied to synthetic date/
  workitem-id fields, where `date -> float` is a hard `TRY_CAST` error.
- Reporting: the SQL sandbox's keyword-blocklist scan was hardened across
  **three rounds**. Round 1 blanked string-literal contents before the
  blocklist regex ran (a keyword inside a literal was false-positively
  flagged as blocked DML/DDL). Round 2 closed a full sandbox-escape: the
  round-1 stripper was apostrophe-blind to bracket/double-quoted
  identifiers, so a crafted alias like `AS [a'b]` shifted the quote-pairing
  and blanked real SQL — including `OPENROWSET`, which sqlglot's AST gate
  does not independently catch — out of the scan. Round 3 closed two more
  gaps: the bracket regex didn't honor T-SQL's `]]` escape for an embedded
  `]`, and comment-stripping ran before any quote-awareness so a `--`/
  `/* */` marker inside a literal was blindly deleted, corrupting
  downstream stripping (unified into one left-to-right tokenizer pass); a
  final pass in the same round fixed a bare-CR (not just LF) comment
  terminator bypass and replaced the bracket regex with an atomic-group
  form after it was found to backtrack catastrophically (~16-29s of CPU on
  a ~20KB adversarial payload) — a DoS reachable by any authenticated user
  with `reporting.sql.run` + a target grant + the ack.
- Reporting: `validate_schedule` guarded `hour`/`minute` against
  non-numeric input but not `weekday`/`dayOfMonth`, so a bad value raised
  an uncaught `ValueError` (a 500) instead of a validation error.
- Reporting: grouped stat keys mixing `int` and `None` raised `TypeError`
  on comparison; now sorts NULLs last via a type-safe `(v is None, str(v))`
  tuple key.
- Reporting: a single malformed saved report definition 500'd the entire
  report listing for every user; type-guarded the preview-kind resolver
  and wrapped per-row serialization so only the offending row is skipped.
- API: the stats helpers swallowed any Statistics-DB failure into an empty
  result, so an outage was indistinguishable from a quiet day and the
  documented external-API 500 never fired; both legs now take a `strict=`
  flag, opted into by the external API only (the dashboard's graceful
  degrade is unchanged).
- Generali: `api_generali_stats` called `.replace("T", " ")` directly on a
  possibly-missing query arg, raising an uncaught `AttributeError` (a 500)
  instead of a 400 when `startDate`/`endDate` was absent.
- Workitems: CSV export's internal fetch helper cached a reduced
  `{fields, media_count}` shape under the same key the media-info API
  serves, silently emptying the source overlay on the next detail-panel
  request.
- Reporting: the dashboard's filter merge keyed by field with
  last-write-wins, so two different filters on the same field (e.g. a
  range split across `gte`/`lte`) silently collapsed to just the last one,
  widening the card's query.
- Reporting: switching sources in the report builder reset columns/scope/
  metrics but left the prior source's filter chips intact, referencing
  fields that might not exist on the new source and 400ing every run until
  cleared by hand.
- Reporting: pivot row/column bucket keys joined dimension tuples into a
  single string, colliding distinct tuples (e.g. `['ab','c']` vs
  `['a','bc']`); now keyed with `JSON.stringify`.
- Workitems: the last-movement column sorter expected a
  `"d. m. yyyy - HH:MM"` date format while the table actually renders ISO
  `YYYY-MM-DD HH:MM:SS`, so every comparison was `NaN` and clicking the
  header was a silent no-op.
- Workitems: detail-panel audit history (#156) — `get_activity_type_name`'s
  memoize timeout was the app's 5-minute default, so process-config data
  (the same for every workitem through a given step) kept re-fetching from
  Octo all day; bumped to 24h. `get_audithistory` also fetches any cold
  misses concurrently instead of one Octo call at a time (prod logs showed
  p90 ~5.6s, worst-case ~34s for this endpoint).

### Security

- Hardened access control and input handling after an internal
  unauthorized-access audit (#193). The by-id workitem detail/media/audit
  endpoints now verify the caller is entitled to the workitem's
  `(client, process)` pair (were reachable cross-tenant via a caller-supplied
  `?client=`); the five Generali list routes derive org/self visibility from
  grants instead of a client-supplied `organizationcode`; `/dev/login` and
  `/dev/users` are now loopback-only (not merely non-PROD); login runs a
  constant-time bcrypt comparison for unknown usernames; `SESSION_COOKIE_*`
  (HttpOnly/SameSite) and `X-Frame-Options`/`X-Content-Type-Options` apply in
  every environment; `MAX_CONTENT_LENGTH` caps upload bodies and the xlsx MIME
  allowlist drops `application/octet-stream`; the dashboard sign-in name is
  HTML-escaped; and JSON error handlers no longer return raw exception text.
  Findings + remediation status: `docs/security/2026-08-audit-193.md`.
- **#193 remaining findings (4, 6, 7, 10, 16) closed out.** Reporting SQL
  sandbox `validate_select()` now rejects cross-DB/linked-server and
  `sys`/`INFORMATION_SCHEMA`/system-DB table references (finding 4). Login
  mints a fresh server-side session id at every point a session becomes
  authenticated, closing the session-fixation gap (finding 6). A durable,
  cross-worker `dbo.LoginLockout` counter (migration `0062`) locks an account
  for 15 minutes after 5 failed logins, independent of the still-per-worker
  IP rate limit (finding 7 — the shared rate-limit-storage half needs Redis
  provisioned, tracked separately). CSP `script-src` no longer carries
  `'unsafe-inline'`; every inline `<script>` is nonce-gated
  (`content_security_policy_nonce_in`) and all inline
  `onclick`/`onchange`/`onerror`/`oninput` attribute handlers across the
  admin, Generali, profile and prepared-documents pages were converted to
  `addEventListener` bindings (finding 10). `DB_ODBC_DRIVER` /
  `DB_ODBC_ENCRYPT` env knobs let a box opt into the modern encrypted ODBC
  driver once it's confirmed installed; the legacy driver stays the default
  until then (finding 16). Updated disposition table:
  `docs/security/2026-08-audit-193.md`.

## [2.5.64] - 2026-07-22

### Added

- `db-standard/` — design proposal for a standardised statistics-DB schema
  (README + DDL) replacing the grown per-client `sydoc_stat` tables. Dev-side
  only: excluded from the prod deploy mirror; the sample Crystal Report binary
  stays untracked.
- Reporting: the Simple-tab wizard measure step is now **multi-select** — pick
  several metrics from one source (e.g. Document count + Pages processed) and
  the result carries one column/series per metric; the stat card shows one
  total per metric. The first pick pins the source; other sources' chips
  disable until the selection is cleared.
- Reporting: process selection is now its **own wizard step** ("Which
  processes?", between measure and breakdown, skipped for sources without
  processes) instead of a collapsed picker inside the breakdown step — the
  breakdown chips render pre-filtered by the chosen processes. Step headings
  auto-number via CSS counters so the skipped step leaves no gap.
- Reporting: breakdown chips sort by **process coverage** (full-coverage
  fields first, `1/x` fields at the bottom, recomputed live as the process
  selection changes) and the `n/m` coverage badge is now tiered by colour —
  amber for partial, muted for low (≤ ⅓ of the selected scope).

- `nx --no-conflict` — start an extra instance on the first free port from 8001 up,
  with separate log/state files, so any number of nexora instances can run alongside
  one already on 8000 (e.g. one a Claude session is testing against).
- `nx --down-all` — stop all nexora instances on any port; `-d` / `--down` keeps
  targeting only the default port-8000 instance.
- Reporting: drill-through — click a chart element or aggregate row to see the underlying
  document rows in a slide-over panel, with workitem links and CSV/XLSX export.
- Reporting: `is_null` filters now match rows from processes that don't expose the field
  (consistent with how those rows are projected into "(null)" groups).
- **Validation User** doc-field and a permission-gated doc-field mechanism:
  fields flagged `IsSensitive` in `dbo.Search_Field_Labels` are hidden (name and
  value) from users without `workitems.filter.documentfields.sensitive` across
  the search dropdown, the values autocomplete API, search filtering, the detail
  panel, and CSV export (migration `0035`).
- `scripts/new-process.py` — interactive dev-side helper that assembles a new
  `dbo.Statconfig` row (process name, stat table, export/import/workitem columns,
  client code) when onboarding a new Octo process. Prints the INSERT for review;
  the actual DB write is still commented out (WIP). Dev-only: `scripts/` is
  excluded from the prod deploy mirror.
- Reporting: the Simple-tab wizard's "Break it down by…" step now offers a
  **Process** dimension — one value per Octo process (per client in this
  deployment), placed first in the curated list. Previously the dimension was
  hidden as noise; the label is DB-localized via `dbo.Search_Field_Labels`
  (migration `0037`). The wizard's category-chip cap rises from 12 to 16 for
  every source (the docprocessing list was exactly saturated at 12; table
  sources with 13–16 string columns now show chips that were previously
  truncated).
- External API v1 for machine-to-machine clients: `GET /api/v1/stats/today`
  returns the dashboard's "imported today" / "processed today" KPI numbers
  as JSON, scoped per API key. Auth is `Authorization: Bearer <key>` against
  `dbo.ApiKeys` (migration `0038`; only the SHA-256 hash is stored; disabled
  keys answer like unknown ones), new decorator `require_api_key`
  (`nx_lib/api_auth.py`), 60/min rate limit checked before auth, JSON error
  handlers for `/api/v1` paths, key issuance via dev-side
  `scripts/new-api-key.py`. See `docs/howto/external-api.md`.
- Reporting: smarter UX — group-specific call-to-action empty states in the Simple
  library, an explanatory notice (instead of silent removal) when the AI assistant
  is unavailable, in-page toasts replacing every `window.alert` on the Advanced tab,
  a designed "No rows matched" empty state, a real loading indicator in the
  drill-through drawer, a full-scan hint while the wizard's "All time" range is
  selected, and copy feedback on the AI SQL draft.
- Reporting: **Pages processed** (`page_count`) metric — `SUM` over the
  `pagecount` doc field (migration `0039`); the query builder now `TRY_CAST`s
  `sum`/`avg` metric bases to float so varchar stat columns aggregate safely.
- Reporting: metric labels are localized — `dbo.ReportingMetrics` gains
  German/French/Italian label columns (migration `0039`, admin form updated);
  `/api/reporting/metrics` serves the session locale's label with English
  fallback.
- Reporting: the Simple wizard marks **process coverage** — measures and
  breakdown chips whose field only some processes provide show an "n/m" badge
  with a tooltip naming the providers; the chip list follows the process-scope
  picker (zero-coverage chips hide, stranded selections prune), and metrics
  whose base field no allowed process provides are not offered.
- Reporting: a **KPI stat band** above the results (both tabs) — total, bucket
  count, and average per bucket, computed client-side from the rows already
  returned (no extra query); hidden for zero-row or non-numeric results, with
  no "vs prior period" delta in v1 (deferred — needs a second query).
- Reporting: a **timing badge** in the masthead — "N rows · M ms" — showing
  the run response's row count and the elapsed time measured client-side
  around the fetch; appears after the first successful run.
- Reporting: a **persistent query footer** — a one-line peek of the inlined
  `sqlDisplay` SQL under the results, click to expand into the existing
  Show-query panel; hidden whenever `sqlDisplay` is absent (the WS1
  inliner-degrade fallback keeps working).
- Reporting: the drill-through drawer's workitem ids are links — clicking one
  opens the shared workitem detail panel (the same read-only view used by the
  Prepared Documents register preview) in a modal over the drawer, permission-
  gated the same way; Ctrl/middle-click still opens `/workitems` in a new tab.
- Reporting AI: a **Try again** button on a failed agent run (turn cap hit, or
  no artifacts produced) resends the same question instead of forcing a
  retype.
- Reporting AI/SQL: tool and sandbox errors strip ODBC driver noise before
  reaching the model or the trace UI, and SQL Server error 1033 (`ORDER BY`
  inside a derived table without `TOP`/`OFFSET`) gets a teaching hint instead
  of the raw message; the agent prompt now forbids resubmitting SQL that just
  failed unchanged. The SQL editor's generic 500 also carries a humanized
  detail.
- Reporting: multi-card dashboards — a new `kind:'dashboard'` saved-report type
  built in the Simple pane: KPI / line / bar / donut / table cards over the
  existing run endpoint, global filters with per-card overrides, drag-to-
  rearrange, add/duplicate/remove, Edit/Done with autosave, per-card export
  and drill-through. No schema change.

### Changed

- Generali Base Services: the combined "POE / PPR" category is split into
  separate "POE" and "PPR" categories for new entries and edits. Existing
  rows keep their stored "POE / PPR" label and stay filterable via a legacy
  filter option; editing such a row requires picking one of the new
  categories.
- Reporting: the Simple-tab wizard's 16-chip category cap is **removed** —
  every filterable string field the Advanced tab offers is now available as a
  breakdown chip (the docprocessing noise hide-list stays).
- AI-workflow slimming (token cost): the MS02 multi-source detail moved from
  `CLAUDE.md` into `docs/design/ms02-multisource.md` (short summary + pointer
  remains); the GitNexus guidance in `CLAUDE.md` is now advisory instead of
  mandatory-per-edit; `/write-plan` plans single-session by default (the
  7-agent workflow is behind a `--deep` flag); `/execute-plan` batches
  spec/quality reviews per plan phase instead of two reviews per task.
- CI/deploy pipeline speedups (`deploy.yml`, `.pre-commit-config.yaml`):
  docs-only pushes (`docs/**`, `**.md`, `.claude/**`) no longer trigger the
  pipeline at all (those paths are excluded from the prod mirror anyway); a
  newer push cancels a superseded in-progress **test** job (deploys still
  queue and are never cancelled); and the suite now runs in two tiers — unit +
  integration first, e2e browsers second — in both CI and the local pre-push
  gate, so a cheap failure surfaces in ~2 minutes instead of after the
  10-minute browser tier (default alphabetical collection ran e2e *first*).
- Reporting: the Show-query panels (Simple and Advanced) now display the executed
  SQL with parameter values inlined as literals and **Copy** copies that runnable
  statement; the separate "Parameters: 1 = …" footer is gone. Execution is
  unchanged and stays fully parameterized. Visual polish across the page: unified
  24px gutters, dark-mode SQL syntax colors, tokenised hint/warning colors,
  Show-query panel chrome.
- Reporting: the page carries its own **"Editorial Ledger" visual identity** —
  a serif masthead title and section headings on a cool-neutral canvas, mono
  (tabular) numerals for KPI figures, table cells and metadata, uppercase
  letter-spaced captions on the KPI band, and a single 2px ink rule topping
  the chart block — restyled in place across the masthead, Simple library/
  wizard/ask-AI, Advanced builder, drill drawer and AI surfaces, light and
  dark. Every `.reporting-*` class, `id`, `name` and `data-testid` is
  unchanged, so existing e2e selectors keep working; the process-coverage
  "n/m" badge on wizard chips and measures picks up the same mono ink-navy
  treatment. Single-series bar/line charts now render in ink-navy with a
  brand-indigo accent on the peak value; multi-series palettes are unchanged.
  Design spec: `docs/superpowers/specs/2026-07-15-reporting-editorial-ledger-design.md`.
  **Superseded below by the "Indigo Studio" redesign** (retired before this
  cycle shipped; kept here for the historical record).
- Reporting: full "Indigo Studio" redesign — landing hero with AI command bar
  and live-preview report cards, progress-rail wizard, refined result view
  with overflow menu, restyled drill drawer and Advanced builder, dark mode.
  The Editorial Ledger serif/mono skin is retired; all ids and testids kept.
  The only backend change the redesign needed: `api_reports_list`
  (`GET /api/reporting/reports`) now computes a `previewKind` per report
  server-side (new `_preview_kind()` helper in `nx_lib/views/reporting.py`)
  so library card badges/thumbnails match the report's real definition
  instead of guessing client-side.

### Security

- Workitems: seven `/api/workitem/<id>*` endpoints (`GET` detail, `GET`
  interactions, `POST` comment / assign / priority / tags, `DELETE` tag)
  checked only that a session existed — **any** logged-in user could read and
  mutate any workitem's metadata, including users who get a 403 on the
  workitems page itself (verified live on INT). They now enforce
  `workitems.details.view` / `.add.comment` / `.assign.users` / `.set.priority`
  / `.add.tag`.
- Workitems: the `status` filter is now gated on `workitems.filter.status` like
  every other filter (it was applied for anyone with `workitems.view`, in both
  the list and the CSV export).
- Workitems: `/api/users` (comment mentions) cached its result under a key that
  omitted the mention permission, so a permitted user's list could be served to
  users without `workitems.details.add.comment`.
- Workitems: the MS02 personal-number (PID) stamped onto list rows now respects
  the sensitive doc-field gate instead of being attached unconditionally.

### Fixed

- Table headers: `text-center`/`text-right` utilities on `.nx-table` header
  cells were silently overridden by the unlayered `.nx-table thead th`
  rule (Tailwind v4 `@layer` precedence), so headers rendered left-aligned
  over centered column content on every nx-table page (issue #121).
  `nexora-ui.css` now re-asserts those utilities at higher specificity.
- Workitems: workitem ids are **not unique across clients** (1216 ids exist in
  both the Octo and MS02 runtimes on INT, 96 of them visible in one list), and
  the detail/media/audit endpoints resolved a bare id by probing only the
  non-default sources — so a colliding id always resolved to MS02, was cached
  permanently, and served the **wrong client's document, fields and images**.
  The list row's client is now carried through to every detail request
  (`?client=`), the probe includes the default source and refuses to cache an
  ambiguous id, and the per-workitem caches are keyed per client. In the UI,
  row element ids are keyed by client+id (two rows previously shared one DOM
  id, so both toggles opened the same panel).
- Workitems: tag / priority / assigned-user filters silently dropped **all**
  MS02 rows — NexoraDB stores `WorkitemId` as `NVARCHAR`, and binding those
  string ids against Postgres' integer `"ID"` column errored, degrading the
  whole MS02 source. Ids are normalized before use.
- Workitems: tags and priority set on an MS02 workitem never appeared in the
  list (same `NVARCHAR`-vs-int mismatch in the row-enrichment lookup).
- Workitems: the "In Progress" status filter matched only status code `1`,
  while the list renders every non-Ready/Done code as "In Progress" — 96 rows
  displayed as In Progress could not be found by filtering for it, and the
  per-status counts did not add up to the total. Both sources now filter the
  whole bucket (`NOT IN (0, 5)`).
- Workitems: the workitem search box now matches the id **exactly** — searching
  `371` returned 1371, 2371, 3716, 16371 and more.
- Workitems: CSV export silently capped at 5000 rows (PROD has ~39k visible
  workitems, so a full export dropped ~34k of them without any indication). The
  cap is now 100k, and a truncated export is reported in the response headers,
  a trailing CSV marker, and the application log.
- Workitems: a user with zero process permissions produced an invalid `IN ()`
  query in both sources, showing a degraded-source banner instead of an empty
  list.
- Workitems: the per-source row counts now count distinct workitems, matching
  the deduplicated rows the page actually renders.
- Workitems: a transient DB error while reading the doc-field column whitelist
  was cached for an hour, disabling doc-field search, autocomplete and the
  PID/register lookups app-wide for that period. Only successful reads are
  cached now.
- Workitems: deleted MS02/PDBS workitems parked on the `Deletion Marker PDBS
  Dokument Statistik` / `Dossier Statistik` activity instances were still
  visible in the workitems list — those two instance names were missing from
  `dbo.ActivityInstancesToIgnore` (migration `0041`; the other two PDBS
  markers were already ignored).
- Workitems: an active doc-field search could return a source's **entire
  corpus** instead of only matching rows when that source's allow-set could
  not be resolved — observed on STAGING (MS02 runtime configured but
  `MS02_DOCFIELDS_DB_NAME` unset), where a barcode search flooded the list
  with all ~2.4k MS02 workitems. Every unresolved path (absent MS02
  doc-field engine, resolver/DB error, unusable SearchConfig mapping,
  unknown field key) now **fails closed**: the affected source contributes
  zero rows to the filtered result. Sensitive-blocked fields keep their
  designed "silently ignored" semantics.
- Reporting/Prepared documents: the workitem-preview **lightbox was broken**
  outside the Workitems page (image and values panel stacked unpositioned,
  reported via the drill-through preview) — the split-pane CSS in
  `source-highlight.css` was scoped to the Workitems shell ids
  (`#imageModal`/`#srcHlLayer`); de-scoped to the shared `.modal` class plus
  a `src-hl-layer-full` class on all three overlay layers.
- Reporting AI: the Agent surface completes instead of dying at the turn cap
  on nearly every ask. The `build_definition` tool now carries the full v1
  definition JSON schema (the model used to guess the shape — filters as a
  map, grain on non-date fields — and burn every turn on validation errors),
  tolerates a stringified or top-level definition argument, and the
  validator/sandbox errors teach the correct shape (filter-list example,
  grainable field list, literal-ISO-dates hint). A `LIMIT` in drafted SQL is
  rejected at the gate with "use TOP (n)" instead of passing sqlglot and
  failing on the real server. The selected builder source is grounding, not
  a gate: the data tools stay bound with `reporting.ai.explain_data` even
  while the builder sits on a builder-only curated source, and the model is
  told the selection is a UI default, not the question's subject. Turn cap
  raised 6 → 10 to fit the full build → validate → run → answer loop.

- Reporting: the drill-through drawer closes when a new run starts — after a
  Refine it kept showing the rows behind the previous result on top of the
  new one.

- Reporting: Simple-pane charts zero-fill empty date-grain buckets —
  "documents per month in Q1" with data only in February now renders three
  buckets (0 / 2 / 0) instead of a single point (single dimension + metric +
  bounded `between` filter; literal dates and resolved relative tokens).

- Reporting: charts now carry **all** breakdowns, not just two — the first
  breakdown stays the axis and every remaining breakdown joins into composite
  colored series ("Process · Source"), client chart and scheduled-mail PNG
  alike. Nothing collapses in the pivot anymore, so this is exact for every
  aggregation (the old third-dim collapse only held for count/sum, and the
  server renderer refused three breakdowns outright); the existing top-12
  series cap bounds the cross-product. Chart clicks drill through with one
  filter per breakdown, and whenever no chart renders the table shows
  immediately instead of hiding behind the "Show table" toggle.

- Workitems: a doc-field search on a field with no `SearchConfig` mapping for one
  of the two workitem sources let that source run **unconstrained** instead of
  contributing zero rows — e.g. searching the (default-only) Validation User field
  on a mixed-process view flooded the results with every MS02 workitem, and a
  field mapped only for ms02 would mirror-bleed all SQL Server workitems. A source
  with no mapping for a searched field now gets an empty allow-set (zero rows);
  broken-config and DB-error cases keep the tolerant no-constraint behavior.
- Dashboard statistics: the two PDBS deletion-marker activity instances
  (`Deletion Marker PDBS Parent Batch Deletion`, `Deletion Marker PDBS Deckblatt`
  on `sydoc.05_PDBS`) no longer pollute the stats — they are seeded into
  `dbo.ActivityInstancesToIgnore` by migration `0032` (idempotent `NOT EXISTS`
  inserts, so environments where the rows were already added by hand are safe).
- Admin: camelCase-named access profiles (e.g. `pdbsUser`) were unassignable
  in the admin UI even for holders of the grant permission, because the
  hand-inserted permission code (`admin.assign.user.accessprofile.pdbsUser`)
  didn't match the lowercased code the app checks — the profile was silently
  filtered out of every assignable-profiles dropdown. `has_permission()`
  (`nx_lib/security.py`) is now case-insensitive, and migration `0034`
  normalizes the stray row to lowercase.
- Admin: the permission add/edit APIs and the user-all-permissions API
  returned 500 on every environment — they referenced `dbo.Permission.SortingCode`,
  a column that never existed until migration `0034` added it.
- **Security:** `admin_add_user` now enforces the
  `admin.assign.user.accessprofile.<profile>` permission the same way user
  editing already did. Previously any `admin.create.user` holder could create
  a user with any access profile (including `enterpriseAdmin`) via a direct
  API request, bypassing the add-user dropdown's filtered list.
- Testing: the flaky-E2E retry net never actually retried anything — the
  pre-push and CI gates passed `--only-rerun flaky_e2e`, but that flag is an
  error-text regex (no traceback contains "flaky_e2e"), so a single browser
  race failed the whole gate. Retries are now armed in `tests/e2e/conftest.py`
  for every E2E test by directory (40+ tests had also drifted out of the net
  by missing the marker); the broken CLI flags are removed from
  `.pre-commit-config.yaml`, `deploy.yml`, `README.md`, and
  `scripts/git-hooks/pre-push`. Unit/integration tests still get zero retries.
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
- Dashboard: the actual root cause of the "chart blanks except for PDBS" symptom was a
  `TypeError` in `dashboard_processed_over_time`, not just the leg 500s above — the default
  T-SQL leg's legacy `DRIVER={SQL Server}` pyodbc driver returns date columns as `str`, while
  the MS02/Postgres leg and the zero-fill loop use real `datetime.date`; merging both into one
  `counts` dict and calling `sorted(counts.keys())` raised `TypeError: '<' not supported
  between instances of 'datetime.date' and 'str'` on every request touching a non-MS02
  process (83 confirmed PROD `app.log` occurrences over two weeks). `sydoc.05_PDBS` is
  MS02-only, so it never hit the mixed-type path — the only process that ever rendered. Fixed
  by normalizing the default leg's date to `datetime.date` at the merge point.
- Reporting: no more English fragments in localized UIs — reporting API errors are
  translated at the boundary (raw engine text demoted to a debug-only `detail`
  field), filter chips and the Advanced op dropdown show localized operator labels
  and catalog field names instead of raw codes, fallback report titles ("Report",
  "Untitled report", "SQL report", "AI report", drill exports) and the Beta badge
  are localized, and result numbers format with the app locale.
- Reporting Simple pane: a failed `/api/reporting/run` (400) now shows the
  server's own error + detail (e.g. "unknown metric: 'workitem_count'")
  instead of a canned message, keeps the report title visible, and offers an
  inline Open-in-Advanced escape hatch; Save/Export stay disabled until a run
  actually succeeds.
- Reporting Simple pane: a zero-row result always renders the designed
  no-data empty state with a "widen the range" hint — previously a
  header-only grid could show instead when the zero stat card happened to be
  visible.
- Reporting Simple pane: Back returns to wherever the report was opened from
  (library, wizard, or an AI ask) instead of always preferring the wizard.
- Reporting Simple wizard: restoring a saved report with a literal (non-token)
  custom date range now prefills the Custom picker with that range, so the
  picker's display always matches what actually runs.
- Reporting: the masthead timing badge (`#reportingTiming`) now hides
  whenever the Simple pane leaves the result view or shows a run error,
  instead of showing a stale "N rows · M ms" from a previous successful run.
- Security: JS partials for Generali documents, the dashboard activity feed, and the
  notification bell built `innerHTML`/`insertAdjacentHTML` from server-derived text
  (scanned-document fields, OCR'd activity content, notification messages) without
  escaping, allowing stored XSS. All three now escape at the render sink.
- Invoices: `/invoice/<id>/pdf` was gated only by a blanket `invoices.download`
  permission with no per-client check, letting a user scoped to one client download
  any client's invoice PDF (IDOR). It now resolves the invoice's Bexio contact and
  rejects the download if it isn't in the caller's allowed client set.
- Generali: PDQM's three read endpoints (list, organizations, month report) never
  applied the own-records restriction every sibling module already enforces, so a
  `generali.pdqm.view`-only user saw every org's entries. They now restrict to the
  caller's own records unless they hold an organizational/transorganizational edit
  permission.
- Dashboard: four legacy KPI endpoints checked only for a logged-in session, missing
  the `dashboard.view` gate present on every sibling route.
- Auth: 2FA verification had no rate limit, allowing unlimited brute-force attempts
  against the 6-digit TOTP code; `/init_2fa` and `/verify_2fa` are now limited to 30
  attempts per hour.
- Auth: only the 2FA-enabled login branch cleared the session before starting a new
  pre-auth flow, so a prior user's session keys could survive into another user's
  pending login on a shared browser. Every credential-accepted branch now clears the
  session first.
- Auth: `/request-password-reset` returned a different message for a registered vs.
  an unregistered email, letting a caller enumerate accounts. Both branches now
  return the same neutral message.
- Workitems: `api_recent_activity` discarded the row's own client when resolving its
  domain, so a colliding id (present in both the default Octo client and MS02) could
  resolve to the wrong client's fields on the dashboard activity feed.
- Workitems: CSV export cached each workitem's domain/details/media/audit-history by
  bare id, so exporting a set containing both clients' copies of a colliding id let
  one row silently carry the other client's fields, images, or audit history.
  Caches — and "export selected" filtering — are now keyed by client+id end to end.
- Admin: deleting a user committed each of eight child-table deletes individually
  before the final `DELETE FROM users`, so any later failure left a half-deleted,
  undeletable user — and the cascade omitted the reporting tables entirely, so
  deleting a report-owning user failed outright. Deletion is now one atomic
  transaction that also cascades the user's owned reports, schedules, and shares.
- Workitems: the "Recent Validations" query appended an unconditional
  `NOT IN (...)` clause that became `NOT IN ()` — a SQL syntax error — whenever the
  ignore list was empty (the normal state for the default client), silently emptying
  the feed.
- Dashboard: the "Current backlog" KPI read a `status` filter but never applied it
  as a predicate, so the widget counted every row ever recorded instead of documents
  actually outstanding. "Current backlog" is the count of workitems currently on
  activity type `C+A` (a live Octo-runtime fact), so a `status:"Ready"` count KPI now
  routes to the already-correct `total_backlog_count()` C+A activity-type count; the
  Statistics-DB stat tables have no activity-type column, so any other `status:"Ready"`
  shape (an average/sum metric, or a doc-field filter) returns an honest no-data state
  rather than a wrong number. A date range also no longer gets silently dropped when
  combined with a non-backlog status.
- Invoices: a Bexio search spanning multiple clients discarded every result already
  gathered as soon as one client's request failed, returning an empty list instead
  of the other clients' real data. A failing client is now logged and skipped,
  keeping whatever succeeded.
- Workitems: the prepared-documents register showed Preview / "Open in Workitems"
  buttons for any PID with a wid mapping, even when Octo had no matching record for
  it, producing dead buttons; the flag now reflects whether Octo actually resolved
  the wid.
- Invoices: two helper functions could raise `UnboundLocalError` or implicitly
  return `None` on a database failure instead of degrading gracefully, the latter
  causing a downstream `TypeError`.
- Generali: the "own record" fast-path in the org-scope check compared an integer id
  to the session's string user id, so it never matched — an admin re-organizing a
  still-logged-in user locked that user out of editing their own records until they
  logged back in.
- Core: `/` always redirected to `/dashboard`, which requires `dashboard.view` — a
  user without it hit a 403 instead of their actual permitted landing page.
- Invoices: an invoice's status label showed "Open" for any non-Paid status, but the
  Open filter only matched one specific status id, so some "Open"-labeled invoices
  vanished when filtered by Open.

## [2.5.63] - 2026-06-24

Version bumped from 2.5.60; now single-sourced in `nx_lib/version.py`.

### Changed

- **MS02 doc-field search reworked from EAV to columnar.** The MS02 doc-field
  source is not an EAV table (`t_DocumentIndexes` `"Name"`/`"StringValue"`, the
  `0027` assumption) — it is a wide per-process *statistik* table
  (`public."DossierStatistik"`) with one column per field plus a `WorkItemID`
  column. `resolve_ms02_docfield_ids` / `resolve_ms02_pid_ids` and the
  `api_docfield_values` autocomplete now run a **columnar** query
  (`SELECT DISTINCT "WorkItemID" FROM <TableName> WHERE "<col>"::text ILIKE %s`,
  AND-intersected across fields), reading `TableName`/`TableAlias`/`JoinCondition`
  from SearchConfig exactly like the default StatisticsDB path. Value matching is
  case-insensitive (`ILIKE`, parity with SQL Server's collation); `'ms02'`
  SearchConfig rows carry Postgres-syntax `TimeFilter`s. Migration `0030`
  configures `sydoc.05_PDBS` (`ClientCode='ms02'`, the column mappings, the PG
  time filters, the `IndexFieldMappings` + `search_field_labels` seeds). Without
  it the row stayed `ClientCode='default'` and was (wrongly) sent to SQL Server.
- Workitems list: the MS02 "Prepared documents" link to the register is now shown only when an MS02 prepared-docs target process is selected (e.g. `sydoc.05_PDBS`); it is hidden on "All Processes" and on any non-PDBS process. Previously the link was shown for any process as long as the user held `workitems.import.preparedaudit` AND MS02 was active.
- The MS02 prepared-documents upload on the workitems page now links to the new
  Prepared Documents register page instead of running a transient
  `?pidImport=<token>` overlay over the list.
- MS02 doc-field (document-field) search now resolves through nexora's `dbo.SearchConfig` mapping (made source/dialect-aware via the new `ClientCode` column, migration `0027`) instead of an in-query `EXISTS` against MS02's own `t_DocumentIndexes` runtime table. The matched field VALUE is resolved against a dedicated MS02 Azure-Postgres doc-field database via the new `engine_ms02_docfields_pg` engine + `MS02_DOCFIELDS_DB_*` env vars (graceful-degrade to `None` until configured); matches are pre-resolved to a workitem-id allow-set and applied as `twi."ID" = ANY(...)`, mirroring the default source. No ETL/ingestion. Default-client doc-field search is unchanged.

### Fixed

- **MS02 dashboard stats were always zero.** The dashboard's MS02 branch hardcoded its source as `public.batchtracking` (cols `datuminexport`/`datumimportiert`) — a table that does not exist in the MS02 stats DB (`Praesidialdepartement_BS`). Every MS02 query raised `UndefinedTable`, was swallowed by the per-source `try/except`, and MS02 contributed 0 to the processed/imported KPIs and the "processed over time" chart. The MS02 branch now reads `TableName`/`ExportColumn`/`ImportColumn` from its `Statconfig` row (like the default branch already does) instead of hardcoding them, quoting the PascalCase Postgres identifiers. The real source is the same columnar table doc-field search uses: `public."DossierStatistik"` with `DatumInTempExport` (processed) / `ImportDate`. Migration `0031` corrects the `Statconfig` row seeded by `0025` so fresh STAGING/PROD environments get the right source.
- Workitems doc-field filter: the field dropdown's lower entries (e.g. **Person ID** on MS02 `sydoc.05_PDBS`) were unreachable. Two causes: (1) the dropdown closed on input `blur`, so grabbing its native scrollbar hid the list mid-scroll — it now closes on outside-click / Tab / Escape / selection, never on plain blur; (2) more fundamentally, the entries that overflowed the filter card were **painted underneath the results table**. The `.nx-rise*` entrance animations used `animation-fill-mode: both`, which holds the final `transform: none` as a resolved identity matrix — and an identity transform still creates a stacking context, trapping the dropdown's `z-index` inside the filter card so the following `.nx-rise` card rendered on top. Switching those animations to `backwards` reverts to a true `transform: none` at rest (visually identical, no-flash preserved), so the dropdown — and any popover overflowing any `.nx-rise` card across the app — paints correctly above following content.
- Workitems document images returned 500 / showed "Failed to load image" whenever the Octo document service advertised a media-stream URL on a **bare internal host** (e.g. `https://mobscn02/...`) instead of its gateway FQDN — that host doesn't resolve off the Octo network. `nx_lib/octo.py` now rewrites a media URL whose host has no dot to the configured gateway domain (which serves the same `/api/documentservice/` path), so the stream is fetchable from anywhere the gateway resolves. URLs that already carry an FQDN are left untouched. The proper long-term fix is Octo-side (configure that instance to emit its FQDN), but nexora no longer depends on the internal hostname resolving.
- Workitems list failed to load for everyone: a temporal-dead-zone `ReferenceError` ("can't access lexical declaration 'activePidToken' before initialization"). The prepared-documents PID-filter token was declared (`let activePidToken`) below the initial `fetchAndUpdateWorkitems()` call, but that function reads it on the first load — so the list (and its document thumbnails) never rendered. The declaration is now hoisted to the top of the page's init scope.
- Prepared Documents register: the COLLECTED / PREPARED / OCTO STATUS check-column header cells were left-aligned while their body cells were centred. The three `<th>` elements now use `.nx-table .align-center` (matching the `<td>` alignment) so headers and cells align consistently.
- Prepared Documents register preview modal: the Import → Extraction → Validation → Delivery timeline rendered all-grey (no stage highlighted). The preview route now resolves the document's current Octo stage and status via a new `resolve_octo_wid_stage` helper and forwards them as `data-status`/`data-current-stage` into the shared panel renderer, so the correct stage lights up based on the document's live Octo state.
- Workitems detail viewer: a parent/batch workitem now surfaces **all** of its child documents' page images, field values, and source-highlight overlays, flattening the document tree **recursively** to its leaf documents at any depth. Previously only a single, literal `DocumentType == "Batch"` level was flattened, so multi-level client document trees — e.g. the MS02 `MobScnBatch → MobScnDossier → MobScnDocument` hierarchy — rendered an **empty** detail panel on the container workitem (images and fields live on the leaf documents). The flatten is now keyed on the presence of `ChildDocuments` rather than the literal type name, shared by `nx_lib/octo.py`, `nx_lib/field_locations.py`, and `nx_lib/table_locations.py` so page-index/overlay alignment is preserved. Plain single-document and one-level-batch workitems are unaffected (same leaves, same order).

### Removed
- The MS02 prepared-documents session-overlay model: the `pid_import:<token>`
  session stash, the `?pidImport=` read-back path (`pid_import_active` /
  `_pid_import_meta`), the row-merge + page-1-only synthetic-row append in
  `_get_workitems_data`, the CSV synthetic guard, and the
  `WorkitemFilter.pid_import_active` field with the `SqlServerSource`
  short-circuit. Superseded by the persistent `dbo.PreparedDocuments` register.

### Added
- **Prepared Documents ⇄ Workitem detail cross-linking (MS02).** The register's
  Octo-Status cell gains a read-only **Preview** modal mirroring the full Workitems
  detail panel (page images + source highlighting + extracted fields + audit + tags +
  comments) beside the renamed "Open in Workitems" link; write controls are hidden in
  the preview. A reverse **"In register"** chip on the Workitems detail panel links to
  `prepared_documents?pid=<pid>`, and the register accepts an exact `?pid=` filter (with
  a "Show all" reset). Internally the detail panel was extracted into a shared partial
  `templates/js/_workitem_detail_panel_js.html`
  (`window.NexoraWorkitemDetail.render(wid, container, {readOnly, perms, inRegisterPid})`
  + `attachLightbox(idMap)`) consumed by both the Workitems row-expand and the register
  modal; the Workitems page behaviour is unchanged. New helpers `pids_in_register()` and
  `resolve_ms02_wids_to_pids()`. MS02-only; read-only; no new permission, no new migration.
- **MS02 on the remaining two dashboard charts.** The "documents per hour" and "average processing time" charts now include MS02 alongside the default client (the processed/imported KPIs and "processed over time" already did). Both read the MS02 table + date columns from the `'ms02'` `Statconfig` row (`public."DossierStatistik"`): hourly buckets by `EXTRACT(HOUR FROM DatumInTempExport)`; avg-processing-time by `EXTRACT(EPOCH FROM (DatumInTempExport - ImportDate))`, contributing one client-level average weighted equally with the default bucket (the same mean-of-means the default path already applies across its processes). All four MS02 stat branches now share one `_ms02_stat_rows` helper for connection handling + error swallowing, and read their source from `Statconfig` rather than hardcoding a table name.
- **PDF page rendering in the workitem viewer.** Document media delivered as PDF
  (e.g. MS02 `MobScn` pages) now renders as page thumbnails + lightbox images
  like JPEG/PNG/TIFF media. `get_extensions_urls_fields` expands one PDF media
  into one slot per page (page carried in the URL fragment, `#page=N`), and
  `api_get_media_raw` rasterises the requested page to JPEG on demand (cached per
  page) via `pypdfium2` — a single binary wheel, no system Poppler/Ghostscript.
  New `requirements.txt` entry `pypdfium2`; must be installed on the prod
  interpreter separately (see `docs/howto/iis.md`). Degrades gracefully when the
  wheel is absent (PDF pages just don't appear; image/TIFF pages unaffected).
  Source-highlight overlay alignment for PDF pages is not yet wired (image-media
  overlays are unchanged).
- **MS02 "Prepared Documents" standalone register.** The MS02 prepared-documents
  Excel intake now persists in its own DB-backed register on a dedicated page
  (`GET /prepared_documents`) instead of a transient session filter over the
  workitems list. Accumulating, upsert-by-PID (one row per personal number;
  re-uploading a PID updates its row), shared across all MS02 users (`UploadedBy`
  is an audit stamp, not a visibility scope), read-only with a clear-whole-list
  action for v1. Columns: PID, Collected, Collected by, Prepared, Prepared by,
  plus a live (non-stored) Octo cross-reference status ("In Octo" + open-workitem
  link when the PID resolves through the MS02 doc-field index, dash otherwise).
  Real DB pagination (OFFSET/FETCH). Backed by new table `dbo.PreparedDocuments`
  (migration `0033`). Gated by the existing `workitems.import.preparedaudit`
  permission AND `ms02_active` (no new permission).
- `engine_ms02_docfields_pg` (+ `MS02_DOCFIELDS_DB_*` env vars) — a dedicated SQLAlchemy engine for the MS02 doc-field index database, and a source/dialect-aware `dbo.SearchConfig.ClientCode` column (migration `0027`).
- **Multi-source dashboard statistics (MS02).** The dashboard's "processed over time" chart and the
  processed/imported KPIs now include MS02, whose processing events live in `public."DossierStatistik"` in
  a separate Azure Postgres DB (`Praesidialdepartement_BS`). New `engine_ms02_stats_pg` engine and
  `MS02_STATS_DB_*` env vars; `dbo.Statconfig` gained a `ClientCode` column (migration `0024`) to route
  each stats group to its serving engine. MS02 stats are activated by seeding `ms02`-tagged Statconfig
  rows (one per exposed ProcessName).
- **Multi-source workitems (MS02 client).** The workitems list, detail page, CSV export, and
  dashboard (activity feed + C+A backlog KPI) now merge a second client, "MS02", whose runtime
  data lives in Azure Postgres and whose Octo API is at a separate domain. New
  `nx_lib/workitem_sources.py` (source adapters + probe-then-cache routing) and
  `nx_lib/clients.py` (client registry). New `engine_ms02_pg` engine (graceful-degrade) plus
  `MS02_*` env vars; the Postgres driver is `psycopg2-binary`. Routing cache table
  `dbo.WorkitemSourceCache` (migration `0023`). Octo access-token requests are now signed with
  per-client credentials. The list `/api/workitems` response gained a `degradedSources` array
  and the UI shows a non-blocking banner when a source is temporarily unavailable.
- Autopilot/nx: `nx status` (alias `nx -s`) now also shows the issue an autopilot run is currently building as `#<n> <title>  -- building <elapsed> (<phase>)`, read from `var/autopilot/run-state.json` and suppressed when stale by the same liveness rule as the run lock. The four per-item n8n Telegram notifications (built, recovered, skipped, needs-input) now name the issue title alongside its number, and the execute-phase node now forwards the issue number (run.log header reads `execute #<n>` instead of `#0`).
- Autopilot: **concurrent multi-lane processing** — up to 3 GitHub issues now build simultaneously in isolated git worktrees (`<repo>-lanes\lane-K`) on `auto/issue-NN` branches. A 3-slot atomic semaphore (`semaphore.ps1`) replaces the single global lock. Per-issue lane lifecycle (`lane.ps1`), DB serialization (`db-lock.ps1`), serialized merge-back under `merge.lock` (`merge-back.ps1`), and a conflict-resolver agent (`merge-resolve.ps1`) are added. The n8n canvas is rewired to dispatch per-item (`dispatch-acquire → got-slot?`), wrap the DB-touching build step in `db-acquire/db-release`, and merge each lane's work back individually (`merge-back → merge-route → merge-resolve`). A failed lane frees its slot and the other lanes continue — no pipeline STOP. `run-phase.ps1` gains `-LogPath`, `-StatePath`, `-Lane` params; `write-plan` skips nested worktree creation when `AUTOPILOT_LANE=1`. `nx status` enumerates per-lane states. `start-n8n.ps1` ancestor-checks and prunes stale lane worktrees on startup.
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
- Workitems list: a runtime-DB outage now renders an empty list with a "temporarily unavailable"
  banner instead of a 500 error (graceful degradation for the multi-source design).
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
- **Reporting page reskinned to the shared nexora-ui design system.** The `/reporting` page (Simple + Advanced tabs, wizard, result views, AI bars and the share/schedule/name/SQL-ack modals) now uses the same `--nx-*` design tokens, cards and buttons as the admin and other pages, and renders correctly in dark mode (the residual hardcoded-hex Simple-pane styling was tokenized). No behavior or feature change.

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
