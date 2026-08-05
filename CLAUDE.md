# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Documentation is authored in git (`docs/`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`) and auto-published to Confluence (read-only mirror): https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774 — see `docs/howto/confluence-sync.md`.

## Project overview

Nexora is a Flask web application (Python 3, WSGI) deployed on Windows/IIS via `wfastcgi`. It serves as an internal portal for Sydoc (workitems, invoices, admin, plus tenant-specific "generali" pages). It talks to multiple SQL Server databases, integrates with Microsoft Graph and Octopus-based runtime services, and uses Bexio for billing.

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
- `engine_ms02_pg` — the MS02 client's Azure Postgres runtime DB (same Octo schema, PG dialect); stays `None` until its `MS02_*` env vars are set (graceful degrade).
- `engine_ms02_stats_pg` — the MS02 client's dashboard-statistics DB (Azure Postgres); stays `None` until `MS02_STATS_DB_*` are set.
- `engine_ms02_docfields_pg` — the MS02 client's doc-field source DB (Azure Postgres); stays `None` until `MS02_DOCFIELDS_DB_*` are set. While `None`, doc-field searches **fail closed** for MS02 (zero MS02 rows in the filtered result), never unconstrained.

**Workitem identity is compound (client + id)** — ids are unique only *within* a client (1216 collide between the Octo and MS02 runtimes on INT). Detail routes take `?client=<code>` from the list row, per-workitem caches and front-end element ids include the client, and the source probe covers the default client too. Details + the NVARCHAR-vs-int seam on NexoraDB metadata: `docs/design/ms02-multisource.md`.

**Multi-source workitems (MS02 client):** MS02 is integrated via `nx_lib/workitem_sources.py` (per-source adapters `SqlServerSource`/`PostgresSource` + probe-then-cache routing, `dbo.WorkitemSourceCache`) and `nx_lib/clients.py` (client registry: runtime engine + per-client Octo creds). Dashboard statistics route per-client via `dbo.Statconfig.ClientCode`; doc-field search via `dbo.SearchConfig.ClientCode` — for MS02 both read wide **columnar** per-process statistik tables (e.g. `public."DossierStatistik"`, *not* an EAV index), and doc-field matches are pre-resolved into a workitem-id allow-set (never joined in-query to the runtime DB). Sensitive doc-fields are gated by `workitems.filter.documentfields.sensitive`, enforced server-side at every surface. The MS02-only prepared-documents register (`dbo.PreparedDocuments`, PID Excel import via `/import_prepared_audit`, standalone `/prepared_documents` page) lives in `nx_lib/prepared_documents.py` + `nx_lib/views/workitems.py`. **Full detail — engines, migrations `0023`–`0033`, resolvers, permission gates, gotchas: `docs/design/ms02-multisource.md`.**

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
  db-migrate.py    applies pending migrations on INT, STAGING or PROD
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
- **Confluence:** `docs/howto/*`, `docs/design/*`, `README.md`, `CONTRIBUTING.md` and `CHANGELOG.md` are auto-published to the Confluence space on push to `main` (`.github/workflows/confluence-docs.yml`). Never edit those pages in Confluence — the sync overwrites them. Details: `docs/howto/confluence-sync.md`.

## Architectural conventions

- **Auth & sessions:** Flask-Session with filesystem backend in `var/session/`. The filesystem session backend is active in production; it is intentionally commented out in local dev (the in-memory default is used instead). Do not re-enable it locally. CSRF via Flask-WTF (`CSRFProtect`). `Talisman` enforces a CSP defined inline in `nx_lib/config.py`. Password hashing uses `bcrypt`. 2FA is TOTP via `pyotp` with QR codes rendered to base64 PNG in `init_2FA.html`.
- **Permissions:** Permissions are string codes (e.g. `admin.view`, `generali.pdqm.view`) loaded via the `dbo.spGetUserPermissions` stored procedure into `session['permissions']`. A `@app.before_request` hook (`reload_user_permissions`) refreshes them on every non-static request. Guard routes with `@require_permission('some.code')`; check in templates/code with `has_permission(code)`. `page_visibility()` is the canonical map of page-level perms; `startpage_redirect_to` picks the landing route based on which perms the user has. The external machine-to-machine API (`/api/v1/*`, `nx_lib/views/api_external.py`) bypasses sessions and permission codes entirely — it authenticates per-client API keys from `dbo.ApiKeys` (migration `0038`) via `require_api_key` in `nx_lib/api_auth.py` (`Authorization: Bearer`, SHA-256-hashed keys, per-key process scope, uniform 401 for unknown/disabled keys, rate limit checked before auth); see `docs/howto/external-api.md`. The `reporting.*` permission family (page access, per-source grants, the SQL sandbox, the AI assistant, scheduling, semantic-metrics admin, and row scope) and the full reporting architecture — Simple/Advanced tabs, the report builder, the provider-agnostic AI assistant (Surfaces A/B/C), cross-user sharing, the DB-backed source registry, and scheduled email delivery — are documented in `docs/howto/reporting.md` and `docs/design/reporting-ai-assistant.md`.
- **UI preferences:** per-user appearance settings (theme incl. system, accent color incl. custom hex, motion, entrance style, animation speed, density, font scale, corner radius, contrast, table stripes, page background, sidebar pin) live in `dbo.Users.ui_prefs` (JSON, allowlisted in `nx_lib/ui_prefs.py`), reload into `session['ui_prefs']` on every request (permissions idiom — a load-once cache goes stale via the heartbeat/cookie race), and are applied pre-paint by the script in `templates/_header.html` `<head>` (`window.nxSetUiPref` persists changes via `POST /profile/ui_prefs`, writes serialized through a coalescing queue). The `/appearance` page (linked from profile, profile dropdown, Ctrl+K) is the UI, with a live preview canvas; CSS knobs live in `static/css/nexora-ui.css` (`html[data-accent]`, `html[data-entrance]`, `html[data-animspeed]`, `html[data-fontscale]`, `html[data-radius]`, `html[data-bg]`, `html.nx-compact`, `html.nx-motion-reduced`, `html.nx-contrast`, `html.nx-stripes`; corner style scales ~100 swept `border-radius` values via `--nx-radius-scale`).
- **Locale:** i18n via Flask-Babel. Supported locales are `en`, `de`, `fr`, `it`. `get_locale()` prefers `session['locale']`, then the user's DB-stored `locale`, then `Accept-Language`. When the user logs in, `load_user_locale` hydrates the session locale from the `Users` table once.
- **Logging:** Every non-static request is written as a CSV row to `var/logs/user/YYYYMMDDHH/nexora_logs.csv` via an `@app.after_request` hook. The `ops/cleanup/csvLogs_toDB.ps1` script ingests these into the stats DB. `ops/cleanup/cleanup_expired_sessionFiles.ps1` prunes the `var/session/` directory. The Flask app logger also writes to `var/logs/system/app.log`.
- **Outage detection:** `ops/outage_monitor.py` (Task Scheduler on SYAPP01, every 5 min, deliberately outside the app process) probes all DB engines, the public site, the Octo token endpoint, and `app.log` for repeating `ERROR` signatures, then mails `SUPPORT_MAIL` on breach via the Graph sender. Hysteresis/dedupe/min-hold and state persistence (`var/outage-state.json`) live in the pure-logic module `nx_lib/outage.py`. Details: `docs/howto/outage-monitor.md`.
- **Routing:** Routes live in `nx_lib/views/` (`auth`, `admin`, `dashboard`, `workitems`, `invoices`, `core`, `generali`, `profile`, `reporting`, `api_external`). Templates are flat under `templates/` with a few subfolders: `admin/` (admin pages + `modals/`), `handlers/` (403/404/500), `js/` (per-page JS as Jinja partials, included by the matching page template), `jd/`, `nexora_logo/`. Page template `foo.html` typically pairs with `templates/js/_foo_js.html`.
- **Error pages:** Custom 403/404/500 handlers render `templates/handlers/*.html`. Raise `PermissionDenied` (a subclass of `HTTPException`) to trigger the 403 page from inside a route.
- **Rate limiting:** `flask_limiter` is configured globally (`limiter = Limiter(...)`); apply `@limiter.limit(...)` per route when needed.
- **File uploads:** Use `werkzeug.utils.secure_filename` plus `python-magic-bin` (`magic`) for MIME sniffing — existing upload handlers follow that pattern; don't trust the client-reported content type.
- **Prefix middleware / PROD URL prefix:** PROD serves the app under `/nexora` — `nx_lib/__init__.py` wires `PrefixMiddleware(app.wsgi_app, prefix="/nexora")` whenever `ENVIRONMENT=PROD`. Server-side `url_for()` is prefix-correct (the middleware sets `SCRIPT_NAME`), but hand-built URLs in JS partials must use the `API_PREFIX` idiom (`const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";`); root-relative literals escape the prefix and 404 on the IIS root site. Dev/INT/tests run unprefixed. Enforced by `tests/unit/test_template_url_prefix.py` (note: it does not match `api('/api/...')` call sites — a new partial's `api()` helper must normalize through `API_PREFIX` itself).
- **Workitems document viewer / source highlighting:** the workitems page renders document pages as images and overlays where each extracted **field** and **table-cell** value was found (the "Show sources" overlay: click-to-locate, confidence colouring, split-pane lightbox). Backed by `nx_lib/octo.py` (`get_extensions_urls_fields`) and the pure helpers `nx_lib/field_locations.py` / `nx_lib/table_locations.py`; front-end in `static/css/source-highlight.css`. Panel rendering lives in the shared partial `templates/js/_workitem_detail_panel_js.html` (exposes `window.NexoraWorkitemDetail.render(wid, container, {readOnly, perms, inRegisterPid})` + `attachLightbox(idMap)`), consumed by both the Workitems row-expand and the Prepared Documents register preview modal. `templates/js/_workitems_overview_js.html` retains the list/filter/export code, the `tbody` write delegation, and calls the shared renderer. Container documents (Octo `Batch`, MS02 `MobScnBatch`/`MobScnDossier`, …) are flattened **recursively** to their leaf documents — keyed on the presence of `ChildDocuments`, not a literal type name — via the shared `field_locations._items`/`items_of` helper, so a parent/batch workitem surfaces all its children's pages + fields at any nesting depth (single docs and one-level batches are unchanged). Gated by `workitems.details.view.*` (incl. the grantable `.confidence` / `.source_location`, migration `0018`). Full design: `docs/superpowers/specs/2026-06-09-workitem-table-highlighting-design.md`.

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

Because they are gitignored, `deploy.yml` never copies them (`/XF *.env`) — **adding a key to `env/PROD.env.example` does nothing on the server until someone edits `\\syapp01\d$\sydoc\nexora\env\PROD.env` by hand**, and forgetting is silent. `scripts/env-sync.py` catches that. Run it **by hand once per deploy that touched an env key** — right before or right after; it is deliberately not automated. It compares the committed `.example` (the authoritative key list) against both the local and the SYAPP01 copy and prints copy-pasteable `KEY=value` lines for anything the server lacks. Only a *missing key* is actionable and sets the exit code; a key set on both sides with **different values** is informational only, since dev and PROD hold different credentials and PROD legitimately lags dev until its deploy lands. Values are masked to fingerprints unless `--show-values`. `--push`/`--pull` copy a whole file (backing the destination up first), but pasting single keys is safer — a push also overwrites server-only values.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **nexora** (9855 symbols, 14192 relationships, 213 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
