# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

This file is injected into **every** session and re-sent after every compact — keep it a map, not a manual. Detail belongs in `docs/`; add a one-line pointer here instead of a paragraph.

Docs are authored in git (`docs/`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`) and auto-published to Confluence (read-only mirror): https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774 — see `docs/howto/confluence-sync.md`.

## Project overview

Nexora is a Flask web application (Python 3, WSGI) deployed on Windows/IIS, which runs it as a single `waitress` process via HttpPlatformHandler. It is Sydoc's internal portal (workitems, reporting, admin, plus tenant-specific "generali" pages). It talks to multiple SQL Server databases and integrates with Microsoft Graph and Octo-based runtime services. (The Bexio billing integration was retired with the invoices page — archived in #177, deleted along with its `decapitated_ClientInvoices` table in #98.)

`nx_main.py` is a 119-line WSGI shim; routes live under `nx_lib/views/`, templates under `templates/` (Jinja2, page templates paired with JS partials under `templates/js/`), assets under `static/`.

## Environment & running

- `ENVIRONMENT` (`INT` or `PROD`) selects the env file; `nx_lib/config.py` loads `env/{ENVIRONMENT}.env`. Sanitised templates: `env/*.env.example`.
- **Local dev:** venv at `./venv`, `pip install -r requirements.txt`, `ENVIRONMENT=INT`, `python nx_main.py`. WSGI handler is `nx_main.app`.
- **Production:** IIS + HttpPlatformHandler → `waitress` (32 threads). `web.config` is the whole hosting contract — it starts waitress, sets `ENVIRONMENT=PROD` / `PYTHONPATH`, trusts `X-Forwarded-For`, logs stdout to `var/logs/system/waitress-stdout*`. Note `path="*"`: **waitress serves `/static`, not IIS**. See `docs/howto/iis.md`. (`wfastcgi` retired in v3.2.3.)
- **Public tunnel** (SYAPP01 only): ngrok today (`docs/howto/ngrok.md`), Cloudflare Tunnel prepared, cutover pending (`docs/howto/cloudflare-tunnel.md`).

## Databases

SQLAlchemy engines with pyodbc, defined in `nx_lib/db.py`. Credentials come from env vars, never code. An engine whose env vars are unset stays `None` and the feature degrades gracefully.

| engine | what |
|---|---|
| `engineNexoraDB` | the app's own DB — users, permissions, session metadata, config |
| `engineOctoDB` | Octo runtime DB on `DB_SERVER_PRD` |
| `engineStatisticsDB` | stats DB on `DB_SERVER_PRD` |
| `engineGeneraliDB` | tenant DB for Generali-branded pages |
| `engine_statistics_ro` | read-only login for the reporting SQL sandbox (`DB_REPORTING_RO_*`; 503 until set) |
| `engine_octo_ro` | read-only login for the sandbox's Octo target (`DB_REPORTING_OCTO_RO_*`; 503 until set) |
| `engine_ms02_pg` | MS02 client's Azure Postgres runtime DB (same Octo schema, PG dialect) — `MS02_*` |
| `engine_ms02_stats_pg` | MS02 dashboard-statistics DB — `MS02_STATS_DB_*` |
| `engine_ms02_docfields_pg` | MS02 doc-field source DB — `MS02_DOCFIELDS_DB_*`. While `None`, doc-field search **fails closed** for MS02 (zero rows), never unconstrained |

**Workitem identity is compound (client + id)** — ids are unique only *within* a client (1216 collides between the Octo and MS02 runtimes on INT). Detail routes take `?client=<code>`; per-workitem caches and front-end element ids include the client.

**Multi-source workitems (MS02)** live in `nx_lib/workitem_sources.py` (adapters + probe-then-cache routing) and `nx_lib/clients.py` (client registry). Statistics and doc-field search route per-client through `nx_lib/mapping_config.py`'s cached registry over `dbo.ProcessSources`/`ProcessFieldMappings`/`FieldLabels`/`FieldAliases` (migration `0074`; the legacy `SearchConfig`/`StatConfig`/`IndexFieldMappings`/`Search_Field_Labels` tables were decapitated by `0075`); for MS02 both read wide **columnar** statistik tables (e.g. `public."DossierStatistik"`), *not* an EAV index. **Engines, migrations `0023`–`0033`, `0074`–`0075`, resolvers, permission gates, gotchas: `docs/design/ms02-multisource.md`.**

**Onboarding a new client/customer** (the `ClientCode` runtime-source vs. `Organizations` customer split, `dbo.Clients` registry, `/admin/clients` + `/admin/processes` admin pages): `docs/howto/white-label.md`.

**Schema changes always go through a migration.** DDL under `sql/` mirrors SSMS Object Explorer; the **live INT database is the source of truth** and the per-object files under `sql/<Database>/` are auto-generated — **never hand-edit them**. Only the two app-owned DBs are tracked (`StatisticsDB` and `OctoDB` are vendor/runtime surfaces).

- New change → new file `sql/_migrations/<Db>/NNNN_short_description.sql`, `GO`-separated, ideally idempotent.
- `scripts/db-migrate.py` applies pending migrations and records them in `dbo.SchemaMigrations`; `sql/sync-from-db.py` re-dumps INT read-only.
- The `sql-migrate-int` + `sql-sync-check` pre-commit hooks auto-apply to INT and block the commit on drift. Escape hatch: `SQL_SYNC_SKIP=1 git commit`.
- Pushing to `main` makes `deploy.yml` apply pending migrations to PROD **before** the app pool stops.
- Migrations are immutable once applied — to undo one, add another.

**Full walkthrough, flag reference, recipes, troubleshooting: `docs/howto/db-migrations.md`.**

## Deploy artifacts

`deploy.yml` mirrors the repo to `D:\sydoc\nexora` with `robocopy /MIR` after stopping the app pool. Runtime needs only `nx_main.py`, `nx_lib/`, `templates/`, `static/`, `translations/`, `web.config`.

**Rule:** committing a new top-level file or directory the running app does **not** need? Add it to the robocopy exclude list in `deploy.yml` — `/XF` for files, `/XD` for directories. `/MIR` would otherwise sync it into prod.

## Keeping docs in sync

Documentation is part of the change, not a follow-up. Add, rename, or remove a CLI flag, route, env var, directory, stored proc, or workflow and you also:

- **Changelog:** add an entry under `[Unreleased]` in `CHANGELOG.md` (Keep-a-Changelog categories). On release, promote it to a dated section.
- **Touched docs:** update this file, `README.md`, `CONTRIBUTING.md`, `docs/howto/*` — whatever the change affects. Path/flag/symbol references here drift fast.
- **Stale docs:** fix drift you notice in the same commit. Prefer correcting or deleting a superseded doc over adding a parallel one.
- **Confluence:** `docs/howto/*`, `docs/design/*`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` auto-publish on push to `main`. Never edit those pages in Confluence — the sync overwrites them.

## Architectural conventions

One line each; **the full detail lives in `docs/design/architecture-conventions.md`** — read it before changing any of these subsystems.

- **Auth & sessions** — Flask-Session (filesystem in prod, deliberately off locally), CSRF via Flask-WTF, Talisman CSP, bcrypt, TOTP 2FA.
- **Permissions** — string codes from `dbo.spGetUserPermissions` into `session['permissions']`, refreshed per request via a TTL cache (`nx_lib/user_cache.py`). Guard with `@require_permission('code')`, check with `has_permission(code)`. The external API (`/api/v1/*`) bypasses sessions entirely — per-client keys from `dbo.ApiKeys`, see `docs/howto/external-api.md`.
- **UI preferences** — allowlisted JSON in `dbo.Users.ui_prefs` (`nx_lib/ui_prefs.py`), applied pre-paint in `templates/_header.html`, edited on `/appearance`. Never cache them in the session (#155).
- **Locale** — Flask-Babel, `en`/`de`/`fr`/`it`; session → user DB row → `Accept-Language`.
- **Response compression** — `nx_lib/compression.py` gzips text responses > 1 KB (stdlib, no `flask-compress`). Covers `/static`. Do **not** suffix the `ETag` — it breaks `If-None-Match`.
- **Logging** — every non-static request appended as a CSV row under `var/logs/user/`; app logger writes `var/logs/system/app.log`.
- **Outage detection** — `ops/outage_monitor.py` on Task Scheduler, pure logic in `nx_lib/outage.py`. See `docs/howto/outage-monitor.md`.
- **Routing** — routes in `nx_lib/views/`, either a single module or a package (`generali/`, `admin/`) of submodules re-exported from `__init__.py`; templates flat under `templates/` plus `admin/`, `handlers/`, `js/`, `jd/`, `nexora_logo/`. Page `foo.html` pairs with `templates/js/_foo_js.html`.
- **Static JS partials (#191)** — the three biggest partials are shims: inline `<script nonce>` holds only Jinja-rendered data, behaviour lives in `static/js/<name>.js` loaded via `static_v()`. Translated strings must stay in the shim and be read off `window`; a `.js` file has no `url_for()` — build URLs with the `API_PREFIX` idiom. `static/js/nx_core.js` loads first, before any other script, on every page (`templates/_header.html`) and defines `window.NX` (`esc`/`api`/`apiSafe`/`toast`/`formatDate`/`formatDateTime`/`formatHours`) plus the canonical `window.API_PREFIX` — new JS should use these instead of reimplementing them.
- **Error pages** — `templates/handlers/*.html`; raise `PermissionDenied` for a 403 from inside a route.
- **Rate limiting** — `flask_limiter` configured globally; apply `@limiter.limit(...)` per route.
- **File uploads** — `secure_filename` + `magic` MIME sniffing; never trust the client content type.
- **PROD URL prefix** — PROD serves under `/nexora` via `PrefixMiddleware`. `url_for()` is prefix-correct; hand-built URLs in JS **must** normalize through `API_PREFIX` or they 404 on PROD. Enforced by `tests/unit/test_template_url_prefix.py`.
- **Workitems document viewer** — page images plus field/table-cell source overlays; `nx_lib/octo.py` + pure helpers `nx_lib/field_locations.py` / `nx_lib/table_locations.py`; shared renderer `templates/js/_workitem_detail_panel_js.html`. Container documents flatten **recursively** to leaf documents.
- **Workitems logic package** — Flask-free helpers (field/table value ops, sensitivity redaction, media/cache-key helpers, DB query) live in `nx_lib/workitems/` (`fields.py`/`sensitivity.py`/`media.py`/`query.py`); `nx_lib/views/workitems.py` keeps route handlers plus Flask-aware wrappers, and `api_external.py`/`dashboard.py` import the Flask-free symbols directly.

**Reporting** is the largest subsystem — Simple/Advanced tabs, report builder, provider-agnostic AI assistant, sharing, DB-backed source registry, scheduled email delivery. Architecture: `docs/howto/reporting.md` + `docs/design/reporting-ai-assistant.md`. `docs/howto/reporting-guide.md` is the **end-user** guide: any user-visible reporting change must update it **and** the in-app tips panel (`templates/_reporting_help.html`) in the same commit — the `reporting-help-sync` pre-commit hook reminds you.


## Testing & browser automation

The `nx` CLI starts and inspects the dev server. Full reference: `docs/howto/nx.md`.

- `nx -u` — start nexora (INT)
- `nx -u -b --loginas:<username>` — start and auto-login for Playwright tests
- `nx --doctor` — preflight health check (env, DBs, migrations, services)
- `nx` — interactive TUI

Playwright screenshot artifacts go in `var/screenshots/`, never the repo root.

## Translations (Flask-Babel)

Mark strings `{{ _('...') }}` in templates, `_('...')` / `gettext(...)` in Python. English is the source locale and has no `.po`. `babel.cfg` extracts from `nx_lib/**.py`, root `*.py`, and `templates/**.html`.

`test_translations.py` enforces that `messages.pot` is in sync and every msgid is translated (non-fuzzy) in de/fr/it. Details: `docs/howto/babel.md`.

## Secrets

`env/{INT,PROD,STAGING,TEST}.env` hold live credentials (DB, Graph, Octo, Flask secret key). They are **gitignored** and live only on dev and prod machines. Never paste their contents into chats, issues, or external tools; never add secret values to code or commit messages.

Because they are gitignored, `deploy.yml` never copies them — **adding a key to `env/PROD.env.example` does nothing on the server until someone hand-edits `\\syapp01\d$\sydoc\nexora\env\PROD.env`**, and forgetting is silent. Run `scripts/env-sync.py` by hand once per deploy that touched an env key; it diffs the committed `.example` against the local and SYAPP01 copies and prints copy-pasteable lines for anything missing. Only a *missing* key is actionable — differing values are expected (dev ≠ PROD).

## Working with Claude Code

Token-efficiency and AI-workflow conventions — subagent/GitNexus exploration, targeted tests, plan-mode for multi-file changes, the verification loop, the session-start budget — live in `docs/howto/claude-workflow.md`. When adding a page/route/permission use the `nexora-feature` skill; `/nx-i18n` and `/nx-migrate` scaffold the translation and migration chores.

**Session handoff loop:** when a batch of work is done (committed, tests green, nothing queued) or the conversation nears auto-compact, run `/handoff-session-state` **unprompted** — it writes a zero-context handoff, commits it, drops the gitignored `var/handoff-pending` flag, and prompts `/clear`. A SessionStart hook then routes the next session through `/reset-session`.

**GitNexus** indexes this repo as `nexora`. Prefer `gitnexus_query({query: "concept"})` over grep when exploring unfamiliar code, and `gitnexus_context({name: "symbolName"})` for a symbol's callers/callees. Run `gitnexus_impact({target, direction: "upstream"})` before editing a widely-used symbol and surface HIGH/CRITICAL risk to the user. Use `gitnexus_rename` rather than find-and-replace. Stale-index warning → `npx gitnexus analyze`. Skill files for each workflow live under `.claude/skills/gitnexus/`.

## Git — Branch-based policy

**On a feature branch** (any branch that isn't `main`): allowed to stage (`git add`), commit (`git commit`), and push (`git push`) without further authorization. Other modifying operations (branch delete, reset, rebase, worktree prune, etc.) still require explicit per-turn opt-in.

**On `main`**: never run any modifying git command — no staging, no commit, no push, no operation that changes refs, the index, or history. This stands even with explicit per-turn authorization in the user's message. If a change needs to land on `main`, switch to a feature branch first and open a PR.

**Per-turn opt-in (feature branches only):** if the current user message explicitly authorizes a specific non-default operation (e.g. "go ahead and delete branch X", "run the worktree prune"), that one operation may be executed. Authorization is scoped to what was named in that message and expires at the end of the turn. Standing blanket permissions ("you have git access for this session") do **not** satisfy this rule.

Read-only git commands are always allowed without authorization on any branch: `git log`, `git diff`, `git status`, `git show`, `git branch`, `git stash list`, `git worktree list`, `git ls-remote`, etc.

**Never authorized, even with explicit permission:** force-push to `main`, `git push --force` without `--force-with-lease`, `git reset --hard` on a branch with unpushed commits, `git branch -D` of the currently checked-out branch, deleting `main`, or skipping hooks (`--no-verify`, `--no-gpg-sign`). For these, refuse and explain even if asked.

## Response style

- Use **bold text** for section breaks, not `#`/`##`/`###` markdown headers.
- **Close with a one-line recap** prefixed `※ recap:` — `Goal:` what was being attempted, then what actually landed (including anything deliberately not done, and why), then `Next:` the next step. Prose, not bullets; no header, no emoji.
- Use `AskUserQuestion` for yes/no and multiple-choice prompts so the user can click instead of type.
