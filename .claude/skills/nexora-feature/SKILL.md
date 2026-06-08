---
name: nexora-feature
description: Use when adding or changing a nexora page, route, permission, or DB-backed feature. Enumerates the full file constellation (route, page template + paired JS partial, permission wiring, SQL migration, i18n, changelog, docs, deploy excludes) so nothing is missed.
---

# Adding or changing a nexora feature

A nexora change touches a predictable constellation of files. Walk every item below; skip what genuinely doesn't apply, but check each one — the common failure is shipping the route and forgetting the migration, i18n, or changelog.

## Before editing

- **Impact first.** Before modifying any existing function/route/class, run `gitnexus_impact({target: "symbol", direction: "upstream"})` and report the blast radius. Warn on HIGH/CRITICAL. (Mandatory per CLAUDE.md.)
- **Plan multi-file changes.** If the change spans more than one file (it usually does here), use plan mode first: Explore → Plan → Code → Commit.

## The constellation

1. **Route** — add/modify the view in `nx_lib/views/<area>.py` (`auth`, `admin`, `dashboard`, `workitems`, `chat`, `invoices`, `notifications`, `core`, `generali`, `profile`, …). All routes live under `nx_lib/views/`; `nx_main.py` is only the WSGI shim — don't add routes there.
2. **Templates** — page `templates/<name>.html` **plus** its paired JS partial `templates/js/_<name>_js.html` (the page `{% include %}`s the partial). Follow the existing pairing convention; subfolders: `admin/`, `handlers/`, `js/`, `jd/`, `nexora_logo/`.
3. **Permission** — guard the route with `@require_permission('area.code')`. Register the code in `page_visibility()` for page-level visibility; update `startpage_redirect_to` if it can be a landing page; check in templates/code with `has_permission('area.code')`. Codes resolve through `dbo.spGetUserPermissions`, so a **new** code needs a seed/grant row → a SQL migration (next item).
4. **SQL migration** (schema, permission seed, or data change) — new file `sql/_migrations/<NexoraDB|GeneraliDB>/NNNN_short_desc.sql`, next number, batches separated by `GO`. Prefer idempotent guards (`IF NOT EXISTS …`). Committing auto-applies it to INT via the pre-commit hook and re-dumps per-object DDL. **Never** hand-edit `sql/<Db>/<Object>/…` (auto-generated). Use the `/nx-migrate` command to scaffold.
5. **i18n** — wrap user-facing strings: `{{ _('…') }}` in templates, `_('…')` / `gettext(…)` in Python. Then run the extract→update→compile cycle so `de`/`fr`/`it` are fully, non-fuzzily translated. Use the `/nx-i18n` command.
6. **Changelog** — add an entry under `[Unreleased]` in `CHANGELOG.md` (Added / Changed / Fixed / Removed).
7. **Docs** — update whatever the change affects: the relevant `docs/howto/*`, this `CLAUDE.md` (keep path/flag/symbol refs accurate — they drift fast), `README`/`CONTRIBUTING`. Fix any stale doc you touch in the same commit.
8. **Deploy excludes** — if you add a **new top-level** file/dir that the running app doesn't need (it needs only `nx_main.py`, `nx_lib/`, `templates/`, `static/`, `translations/`, `web.config`), add it to the robocopy `/XF` (files) / `/XD` (dirs) list in `.github/workflows/deploy.yml`, or `/MIR` will sync it to prod.

## Verify before claiming done

- `ruff check .` (and `ruff format` if formatting changed).
- **Targeted** tests for what you changed: `pytest <path>::<test> -q` — not the whole suite (that's the pre-push gate; run `python scripts/test_db_reset.py` first if you do run e2e).
- **UI changes:** restart the dev server first (Jinja templates are cached for the process lifetime, so tests/screenshots see stale HTML otherwise), then drive Playwright via `nx -u -b --loginas:<user>` and save screenshots to `var/screenshots/`.
- Run `gitnexus_detect_changes()` before committing to confirm only the expected symbols/flows changed.

## Commit

- Conventional-commit message (gitlint-enforced). Feature branches allow stage/commit/push; `main` allows **no** modifying git ops — PR instead. Never `--no-verify`. If the SQL pre-commit hook can't reach INT (e.g. a fresh worktree with no `env/INT.env`), use `SQL_SYNC_SKIP=1 git commit`.
