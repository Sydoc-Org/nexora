# Changelog

All notable changes to nexora are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work toward 2.5.65.

### Added

- Reporting: a multi-turn **AI chat panel** (`#rpChatToggle`, both Simple and
  Advanced tabs) replaces the old single-shot "Ask AI" surface — a docked
  slide-over with a conversation thread, a per-turn collapsible tool-step
  trace, and follow-up suggestion chips. `POST /api/reporting/ai/agent` gains
  a `history` param (last 8 turns / 4000 chars, text-only) so follow-ups carry
  real conversational context instead of starting over each time.
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

### Changed

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

### Fixed

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
