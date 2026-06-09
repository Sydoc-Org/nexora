# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Full product documentation lives in Confluence: https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774

## Project overview

Nexora is a Flask web application (Python 3, WSGI) deployed on Windows/IIS via `wfastcgi`. It serves as an internal portal for Sydoc (workitems, invoices, chat, admin, plus tenant-specific "generali" pages). It talks to multiple SQL Server databases, integrates with Microsoft Graph and Octopus-based runtime services, and uses Bexio for billing.

The entire backend is a single file: `nx_main.py` (a 119-line WSGI shim); routes live under `nx_lib/views/`. Templates live under `templates/` (Jinja2, split into page templates and paired JS partials under `templates/js/`). Static assets are in `static/`.

## Environment & running

- Environment is selected via the `ENVIRONMENT` env var (`INT` or `PROD`). `nx_lib/config.py` loads `env/{ENVIRONMENT}.env` on startup (with a one-release fallback to the legacy root-level `{ENVIRONMENT}.env`, emitting a `DeprecationWarning`). `env/INT.env`, `env/PROD.env`, `env/STAGING.env`, `env/TEST.env` hold secrets and DB/Graph/Octo/Bexio credentials. Sanitised templates live at `env/*.env.example`.
- Local dev: create a venv at `./venv`, `pip install -r requirements.txt`, set `ENVIRONMENT=INT`, run `python nx_main.py` (or `flask run`). The WSGI handler is `nx_main.app`.
- Production: IIS with URL Rewrite + FastCGI. See `docs/howto/iis.md`. `web.config` rewrites all non-`/static/` URLs to `nx_main.py` and points FastCGI at `D:\sydoc\tools\py\python.exe`. `PYTHONPATH` is `D:\sydoc\nexora`.
- Public tunnel (SYAPP01 only): see `docs/howto/ngrok.md` — `ngrok start --config="D:\sydoc\nexora\ngrok.yaml" --all`, or run as a Windows service.

## Databases

The app connects to four SQL Server databases via SQLAlchemy engines with pyodbc (see `nx_lib/db.py`). Credentials come from env vars, not code.

- `engineNexoraDB` — the app's own DB (users, permissions, sessions metadata, config).
- `engineOctoDB` — Octopus runtime DB on `DB_SERVER_PRD`.
- `engineStatisticsDB` — stats DB on `DB_SERVER_PRD`.
- `engineGeneraliDB` — tenant-specific DB for Generali-branded pages.
- `engine_statistics_ro` — read-only `db_datareader` login over the Statistics DB used by the reporting SQL sandbox (`DB_REPORTING_RO_USER` / `DB_REPORTING_RO_PWD` env vars; until set, the SQL source returns 503).
- `engine_octo_ro` — read-only `db_datareader` login over the Octopus runtime DB, used by the reporting SQL sandbox's Octopus target (`DB_REPORTING_OCTO_RO_USER` / `DB_REPORTING_OCTO_RO_PWD` env vars; until set, the Octopus target returns 503).

DDL source lives under `sql/`, organized to mirror SSMS Object Explorer. The **live INT database is the source of truth** for committed-state DDL — the per-object files are auto-generated and must not be hand-edited.

```
sql/
  NexoraDB/        Tables/  Views/  Programmability/{StoredProcedures,Functions,Triggers,Types}  Security/{Users,Roles,Schemas}
  GeneraliDB/      same layout
  _migrations/
    NexoraDB/      0001_init_schema_migrations.sql, 0002_..., 0003_...
    GeneraliDB/    0001_init_schema_migrations.sql, ...
  sync-from-db.py  regenerates the per-object dumps from INT via mssql-scripter
  requirements.txt mssql-scripter
scripts/
  db-migrate.py    applies pending migrations on INT or PROD
```

Only the two app-owned databases are tracked. `StatisticsDB` (sydoc_stat) and `OctoDB` are deliberately excluded — they're treated as runtime/vendor surfaces, not schema we own.

**Two scripts, two roles:**

- `scripts/db-migrate.py` — moves schema forward by running ordered migration files. Records each applied file in `dbo.SchemaMigrations` (per database) and refuses to re-run a file whose checksum changed.
- `sql/sync-from-db.py` — read-only dump of the current INT schema into per-object files for review and code search.

Install once per clone (handled by `.\bootstrap.ps1`, or manually):

```
pip install -r sql/requirements.txt   # mssql-scripter, used by sync-from-db.py
pre-commit install --install-hooks     # wire the git hooks (pre-commit framework)
```

Detailed walkthrough: `docs/howto/db-migrations.md`.

The pre-commit hook (the `sql-migrate-int` and `sql-sync-check` hooks in `.pre-commit-config.yaml`) runs:

1. `scripts/db-migrate.py --env INT` — **auto-applies** any pending migrations to INT.
2. `sql/sync-from-db.py --check` — verifies the per-object dumps still match INT.

**Blocks the commit** if either step fails (SQL error during apply, or drift between INT and the per-object dumps).

Escape hatch when offline: `SQL_SYNC_SKIP=1 git commit ...` or `git commit --no-verify`.

**Workflow for any DB change** (new table, column, index, stored proc, permission row, data backfill, etc.):

1. Create a new migration file `sql/_migrations/<Db>/NNNN_short_description.sql`. Use the next number; one or more SQL batches separated by `GO`.
2. Commit. The pre-commit hook auto-applies it to INT and re-dumps per-object DDL.
   - If you already ran the statements in SSMS while prototyping, record them first so the hook doesn't try to re-apply: `python scripts/db-migrate.py --env INT --mark-applied`
   - Idempotent migrations (using `IF NOT EXISTS` / `IF EXISTS` guards) survive being re-applied by the hook without needing `--mark-applied`.
3. Push to `main`. The GitHub Actions deploy workflow (`.github/workflows/deploy.yml`) auto-applies pending migrations to PROD **before** the app pool is stopped, then mirrors the code. Failed migration → deploy aborts and the running app stays untouched. For ad-hoc PROD migration from your dev box: `python scripts/db-migrate.py --env PROD`.

Never hand-edit files under `sql/<Database>/<TableOrView>/...` — those are auto-generated from INT. Always go through a migration. Migrations are immutable once applied: to undo or alter a previous migration, add a new one.

The previous `environment_transfer_queries.tmp.sql` workflow is deprecated and replaced by `sql/_migrations/`.

## Deploy artifacts

The deploy workflow at `.github/workflows/deploy.yml` mirrors the repo to `D:\sydoc\nexora` via `robocopy /MIR` after stopping the IIS app pool. The Flask app only needs `nx_main.py`, `nx_lib/`, `templates/`, `static/`, `translations/`, and `web.config` at runtime — everything else (tests, scripts, docs, dev tooling, AI configs, build artifacts) is dev-side.

**Rule:** when committing a new top-level file or directory that is **not** needed by the running app, also add it to the robocopy exclude list in `deploy.yml` — `/XF` for files, `/XD` for directories. `/MIR` would otherwise sync it into prod on the next deploy.

## Keeping docs in sync

Documentation is part of the change, not a follow-up. Whenever you add, rename, or remove a CLI flag, route, env var, directory, stored proc, or workflow:

- **Changelog:** add an entry under `[Unreleased]` in `CHANGELOG.md` (Keep-a-Changelog categories — Added / Changed / Fixed / Removed). When a version ships, promote `[Unreleased]` to a dated `[x.y.z]` section.
- **Touched docs:** update whatever the change affects — this file, `README.md`, `CONTRIBUTING.md`, and `docs/howto/*`. Keep the path / flag / symbol references in this file accurate (they drift fast).
- **Stale docs:** if you notice an existing doc that has drifted (wrong path, renamed symbol, removed flag, superseded workflow), fix it in the same commit rather than leaving it. Prefer correcting or deleting a superseded doc over adding a parallel one.

## Architectural conventions

- **Auth & sessions:** Flask-Session with filesystem backend in `var/session/`. The filesystem session backend is active in production; it is intentionally commented out in local dev (the in-memory default is used instead). Do not re-enable it locally. CSRF via Flask-WTF (`CSRFProtect`). `Talisman` enforces a CSP defined inline in `nx_lib/config.py`. Password hashing uses `bcrypt`. 2FA is TOTP via `pyotp` with QR codes rendered to base64 PNG in `init_2FA.html`.
- **Permissions:** Permissions are string codes (e.g. `admin.view`, `generali.pdqm.view`) loaded via the `dbo.spGetUserPermissions` stored procedure into `session['permissions']`. A `@app.before_request` hook (`reload_user_permissions`) refreshes them on every non-static request. Guard routes with `@require_permission('some.code')`; check in templates/code with `has_permission(code)`. `page_visibility()` is the canonical map of page-level perms; `startpage_redirect_to` picks the landing route based on which perms the user has. The `reporting.*` family covers the reporting page: `reporting.view` (page access), `reporting.source.docprocessing` (Document Processing source), `reporting.export` (Excel export via `openpyxl`), `reporting.scope.process.<client>.<process>` (row scope, mirrored from `dashboard.filter.process.*`; surfaced as the builder's left-panel **Processes** multi-select picker grouped by client — fully-ticked clients serialise to `scope.clients`, partial to `scope.processes`, and `_effective_scope` composes them by union with the grant set as the boundary), `reporting.sql.run` (run live read-only SQL in the sandbox against the Statistics DB, sandboxed via `sqlglot` AST gate + dedicated `db_datareader` login; grantable; admins seeded; every run audited to `dbo.ReportingSqlAudit`; first-use acknowledgment recorded in `dbo.ReportingSqlAck`), `reporting.sql.target.octopus` (additionally target the Octopus runtime DB in the SQL sandbox via its own `db_datareader` login; gated independently from `reporting.sql.run`; grantable; admins seeded), `reporting.admin.sources` (manage the DB-backed source registry at `/reporting/sources`), `reporting.semantic.admin` (manage the canonical-metrics registry `dbo.ReportingMetrics` at `/reporting/metrics` — **semantic layer Slice 1**: a definition's optional `metrics` list turns the selected `columns` into the GROUP BY and adds blessed `AGG(col)` columns resolved via `nx_lib/reporting/semantic.py`; migration `0017`; admins seeded), `reporting.schedule` (schedule a report to run + be emailed), the per-source perms `reporting.source.generali.pdqm` / `reporting.source.workitems` (the two seeded `table`-provider curated sources over Generali / Octopus), `reporting.ai.use` (use the AI assistant — NL questions), `reporting.ai.sql` (receive AI-drafted read-only T-SQL into the editor; grant alongside `reporting.sql.run`) and `reporting.ai.explain_data` (**Phase 3e**, opt-in, admins seeded via migration `0015`; lets the agentic loop bind the data-returning tools `run_sql` + `compute_stats` so the model can run validated read-only SELECTs and narrate the **actual result numbers** — a deliberate **data-egress** grant, only effective together with `reporting.sql.run`; off by default keeps the loop schema-only). The assistant exposes three routes: `POST /api/reporting/ai/ask` (Surface B — NL → T-SQL; gated `reporting.ai.sql`; sqlglot-validated; audited `Surface='sql'`), `POST /api/reporting/ai/build` (Surface A — NL → report **definition**; gated `reporting.ai.use` only, no SQL perm required; self-validates via `validate_report_definition` + one retry; auto-fills the builder via `applyDefinition()`; optional `chartHint`; audited `Surface='definition'`), and `POST /api/reporting/ai/agent` (Surface C — **Phase 3** agentic self-repairing drafter over a Tier-2 tool-loop `nx_lib/reporting/ai.py: ask_agentic`; gated `reporting.ai.use`; binds **data-free** tools by default — `build_definition` always, `validate_sql` with `reporting.ai.sql` — so egress stays schema-only, and additionally binds `run_sql` + `compute_stats` when the caller holds `reporting.ai.explain_data`; returns a validated definition/SQL + a tool trace and an `explainData` flag; audited `Surface='agent'`). The **"Agent" sub-mode** in the Ask-AI panel (`templates/js/_reporting_ai_js.html`) drives Surface C with a visible tool-step trace + follow-up conversation. The tool layer (`nx_lib/reporting/ai_tools.py`) and a stdlib **deterministic stats engine** (`nx_lib/reporting/stats.py`) back it. All three routes are server-side and provider-agnostic (`AI_PROVIDER`), and audit to `dbo.ReportingAiAudit`; they send only the question + schema metadata (never result rows) **except** the explain-data agent path, where rows the loop fetches flow back to the model for narration. See `docs/design/reporting-ai-assistant.md`. The builder also offers chart + drag-and-drop pivot views (with nested column headers), Excel **and CSV** export (view-aware: grid rows, pivot matrix, or chart PNG), Save-vs-Save-as, **cross-user sharing** (`dbo.Reports.Visibility` + `dbo.ReportShares`, "My reports" / "Shared with me"), a **DB-backed source registry** (`dbo.ReportingSources`, code defaults overlaid with DB rows; generic whitelist-safe `table` provider in `nx_lib/reporting/table_query.py`), **scheduled email delivery** (`dbo.ReportSchedules`; `ops/run_scheduled_reports.py` runs each due report as its owner via `nx_lib/reporting/runner.py` and mails it through `nx_lib/mail.py`/Graph, wired by Windows Task Scheduler), and the **AI assistant** (provider-agnostic; configured via `AI_PROVIDER` / `AI_MODEL` / `ANTHROPIC_API_KEY` / `ANTHROPIC_API_URL` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_VERSION` env vars; disabled until `AI_PROVIDER` is set; `AI_DAILY_LIMIT` caps asks per user/day — `0`=unlimited — returning 429 before any provider call and auditing the throttle as `Status='blocked'`). The two `db_datareader` RO logins are provisioned with `scripts/provision-reporting-ro-logins.sql`. docprocessing also exposes synthetic date fields `import_date`/`export_date` (from `Statconfig`, CONVERT/CAST-normalized) with an optional per-column `grain` (day/week/month/quarter/year) resolved in `query.py` for both the row and aggregate paths; date filters always use the raw date. See `docs/howto/reporting.md`.
- **Locale:** i18n via Flask-Babel. Supported locales are `en`, `de`, `fr`, `it`. `get_locale()` prefers `session['locale']`, then the user's DB-stored `locale`, then `Accept-Language`. When the user logs in, `load_user_locale` hydrates the session locale from the `Users` table once.
- **Logging:** Every non-static request is written as a CSV row to `var/logs/user/YYYYMMDDHH/nexora_logs.csv` via an `@app.after_request` hook. The `ops/cleanup/csvLogs_toDB.ps1` script ingests these into the stats DB. `ops/cleanup/cleanup_expired_sessionFiles.ps1` prunes the `var/session/` directory. The Flask app logger also writes to `var/logs/system/app.log`.
- **Routing:** Routes live in `nx_lib/views/` (`auth`, `admin`, `dashboard`, `workitems`, `chat`, `invoices`, `notifications`, `core`, `generali`, `profile`, `reporting`). Templates are flat under `templates/` with a few subfolders: `admin/` (admin pages + `modals/`), `handlers/` (403/404/500), `js/` (per-page JS as Jinja partials, included by the matching page template), `jd/`, `nexora_logo/`. Page template `foo.html` typically pairs with `templates/js/_foo_js.html`.
- **Error pages:** Custom 403/404/500 handlers render `templates/handlers/*.html`. Raise `PermissionDenied` (a subclass of `HTTPException`) to trigger the 403 page from inside a route.
- **Rate limiting:** `flask_limiter` is configured globally (`limiter = Limiter(...)`); apply `@limiter.limit(...)` per route when needed.
- **File uploads:** Use `werkzeug.utils.secure_filename` plus `python-magic-bin` (`magic`) for MIME sniffing — existing upload handlers follow that pattern; don't trust the client-reported content type.
- **Prefix middleware:** `PrefixMiddleware` exists for deploying under a URL prefix; it's defined but only wired up when needed.
- **Workitems document viewer / source highlighting:** the workitems page renders document pages as images (`api_get_media_raw`) and extracted index-field values via `api_get_media_info`, both backed by the Octopus document service in `nx_lib/octo.py` (`get_extensions_urls_fields`). `api_get_media_info` also returns `field_sources` — where each value was found on the page — parsed from `IndexField.Location` by the pure helper `nx_lib/field_locations.py` (raw image-pixel rects; the browser normalizes against the page image's `naturalWidth/Height`). Each entry also carries an optional 0–1 `confidence` (from the IndexField's `Confidence`, normalized in `field_locations.py`) used to colour the boxes + a per-field chip (green ≥ 0.9 / amber ≥ 0.7 / red < 0.7; neutral orange when absent). The "Show sources" overlay (full-page split review + thumbnails, click-to-locate, un-locatable badge, confidence colouring) lives in `templates/js/_workitems_overview_js.html` with styles in `static/css/source-highlight.css`; it reuses `workitems.details.view.images` + `.fields`, and adds two grantable sub-permissions (migration `0018`, admin-seeded): `workitems.details.view.confidence` (the confidence % chips + box colour) and `workitems.details.view.source_location` (the highlight boxes + click-to-locate; only effective with `.images` since boxes draw over the page). `api_get_media_info` strips `confidence`/`locations` from `field_sources`+`table_sources` per permission and returns a `source_location_visible` flag (the front-end hides the "no source location" badge when the perm is absent). The lightbox (`#imageModal`) is a two-pane split: the document page + highlight overlay on the left (`.src-modal-page`), the extracted values on the right (`#srcReviewPanel`, the same scalar `<dl>` + line-item grid as the inline panel, built by the shared `buildSourceDetailsHtml`). The overlay layer (`#srcHlLayer`) is sized from the image's transform-immune **layout box** (`offsetLeft/Top/Width/Height`, not `getBoundingClientRect`, which the open-zoom `transform` corrupts). Because `#srcHlLayer` is a *sibling* of the image (so it never inherits the `.modal-content` open-zoom `scale(0.5)→1`), the overlay's first render is deferred by `drawOverlayWhenStable()` until the page is geometrically settled — the image bitmap is decoded **and** every running animation on it has `finished` (reopen / prev-next, with no animation running, renders immediately) — otherwise boxes drawn mid-zoom float off the still-scaling page until a manual hide/show re-renders them; a `ResizeObserver` on the modal image re-renders on any later box-size change (panel reflow, late decode, resize). The same overlay also covers **table / line-item extractions**: when `with_tables=True` (only the `api_get_media_info` path opts in, so the three scalar-only callers keep the smaller `WithTables=false` payload) `get_extensions_urls_fields` returns a 5-tuple with a `table_sources` array, parsed from the Octopus `Tables[].Rows[].Cells[]` shape by the pure helper `nx_lib/table_locations.py` (cell value = `CellValue.Text`/`CapturedValue`, column = `ColumnName`, table title = `Name`; same `Location` rect shape, reusing `field_locations.py`'s rect/confidence/page-offset helpers, which are imported via the public aliases `rect_from_octo`/`confidence_of`/`count_image_media`/`items_of`/`num`). A table cell is rendered as "just another source" (`kind:'cell'`): cell boxes draw via the same loop with a **dashed** border (distinct from the solid scalar boxes; confidence colour preserved), and a compact **line-item grid** renders below the scalar `<dl>` with click-to-locate cells. `table_sources` is permission-suppressed identically to `field_sources`. All extracted document content (field + cell values, labels, column names, table title) is HTML-escaped (`srcEsc`) before innerHTML interpolation. Nested `DPSI_Document`s whose located data lives in `ChildDocuments` are a pre-existing viewer limitation (the parser reuses the same root-vs-children iteration so table page-indices always align with the served images). See `docs/superpowers/specs/2026-06-09-workitem-table-highlighting-design.md`.

## Testing & browser automation

The `nx` CLI tool starts and inspects the nexora dev server. Full reference: `docs/howto/nx.md`.

- `nx -u` — start nexora (INT environment)
- `nx -u -b --loginas:<username>` — start nexora and auto-login as the given user for Playwright browser tests
- `nx --doctor` — preflight health check (env, DBs, migrations, services)
- `nx` (no args) — interactive TUI (REPL with tab-completion and live status)

Playwright screenshot artifacts go in `screenshots/` (never the repo root).

## Working with Claude Code

Token-efficiency and AI-workflow conventions — subagent/GitNexus exploration, targeted tests, plan-mode for multi-file changes, the verification loop, the session-start budget — live in `docs/howto/claude-workflow.md`. When adding a page/route/permission, use the `nexora-feature` skill; `/nx-i18n` and `/nx-migrate` scaffold the translation and migration chores.

**Session handoff loop:** when a batch of work is done (committed, tests green, nothing queued) or the conversation is getting heavy (nearing auto-compact), run `/handoff-session-state` **unprompted** — it writes a zero-context handoff, commits it, drops the gitignored `var/handoff-pending` flag, and prompts the user to `/clear`. On the next session start, a SessionStart hook reads the flag and instructs the fresh session to resume via `/reset-session`, which consumes the flag. Details: `docs/howto/claude-workflow.md` ("Session handoff loop").

## Git — Branch-based policy

**On a feature branch** (any branch that isn't `main`): allowed to stage (`git add`), commit (`git commit`), and push (`git push`) without further authorization. Other modifying operations (branch delete, reset, rebase, worktree prune, etc.) still require explicit per-turn opt-in.

**On `main`**: never run any modifying git command — no staging, no commit, no push, no operation that changes refs, the index, or history. This stands even with explicit per-turn authorization in the user's message. If a change needs to land on `main`, switch to a feature branch first and open a PR.

**Per-turn opt-in (feature branches only):** if the current user message explicitly authorizes a specific non-default operation (e.g. "go ahead and delete branch X", "run the worktree prune"), that one operation may be executed. Authorization is scoped to what was named in that message and expires at the end of the turn. Standing blanket permissions ("you have git access for this session") do **not** satisfy this rule.

Read-only git commands are always allowed without authorization on any branch: `git log`, `git diff`, `git status`, `git show`, `git branch`, `git stash list`, `git worktree list`, `git ls-remote`, etc.

**Never authorized, even with explicit permission:** force-push to `main`, `git push --force` without `--force-with-lease`, `git reset --hard` on a branch with unpushed commits, `git branch -D` of the currently checked-out branch, deleting `main`, or skipping hooks (`--no-verify`, `--no-gpg-sign`). For these, refuse and explain even if asked.

## Response style

- Use **bold text** for section breaks, not `#`/`##`/`###` markdown headers.
- Use `AskUserQuestion` for yes/no and multiple-choice prompts so the user can click instead of type.

## Translations (Flask-Babel)

Workflow from `docs/howto/babel.md`:

```
pybabel extract -F babel.cfg -o messages.pot .
# first time per locale:
pybabel init -i messages.pot -d translations -l de    # (or fr, it)
# updates:
pybabel update -i messages.pot -d translations
# after editing translations/<lang>/LC_MESSAGES/messages.po:
pybabel compile -d translations
```

`babel.cfg` extracts from `nx_lib/**.py` (recursive — so route/flash messages are translated), root-level `*.py`, and `templates/**.html`. Mark strings with `{{ _('...') }}` in templates and `_('...')` / `gettext(...)` in Python. English is the source locale and has no `.po` file. The `test_translations.py` suite enforces that `messages.pot` is in sync and every msgid is translated (non-fuzzy) in de/fr/it.

## Secrets

`env/INT.env`, `env/PROD.env`, `env/STAGING.env`, `env/TEST.env` contain live credentials (DB, Microsoft Graph, Octopus, Bexio PAT, Flask secret key). They are **gitignored** (`*.env` in `.gitignore` with `!env/*.env.example` exception) and live only on dev and prod machines — never committed. The sanitised `env/*.env.example` templates are committed for onboarding. Treat the real files as sensitive: do not paste their contents into chats, issues, or external tools, and never add new secret values to code or commit messages.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **nexora** (3437 symbols, 4819 relationships, 106 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/nexora/context` | Codebase overview, check index freshness |
| `gitnexus://repo/nexora/clusters` | All functional areas |
| `gitnexus://repo/nexora/processes` | All execution flows |
| `gitnexus://repo/nexora/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
