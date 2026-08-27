# Handoff — white-label + admin onboarding UI (#98 phase 4) executed and merged

**Date:** 2026-08-27 · **Branch:** `v3.2.3.1` · **merge commit `057a2ebd`** · commit-only, unpushed —
the owner pushes.

> **`var/handoff-pending` was NOT touched by this session** — it points at a peer session's
> reporting-dashboard handoff. Resume this work with the explicit path to this file.

## TL;DR

The plan `docs/superpowers/plans/2026-08-27-white-label-admin-ui.md` was executed end to end:
12 tasks, 3 phases, 17 commits on `feat/white-label`, merged into `v3.2.3.1` as `057a2ebd`.
The worktree and the branch are gone. Onboarding a customer that rides the shared `default`
runtime is now a no-deploy, no-migration admin task, and each customer's users see their own
brand in the app.

- **PHASE A** — migration `0079` creates + seeds `dbo.Clients`; `nx_lib/clients.py::_build_clients()`
  reads it. Public surface unchanged; a DB error degrades to a `default`-only registry.
- **PHASE B** — migration `0080` seeds five admin permissions; `/admin/clients` and `/admin/processes`.
  Creating a process source auto-provisions `workitems.filter.process.<name>`, granted to nobody;
  every mapping write calls `invalidate_mapping_config()`.
- **PHASE C** — migration `0081` adds nullable brand columns to `dbo.Organizations`; `nx_lib/branding.py`
  is a 60 s cached registry; a context processor injects the brand; `/admin/organizations` gained a
  branding panel with logo upload; `branding_logo` serves `var/branding/<orgcode>.<ext>`.

Docs: `docs/howto/white-label.md` (new). Every phase got a combined spec+quality review; four fix
waves in total; the final whole-branch review's blocker and five cross-cutting findings were fixed
and re-verified before the merge.

## What the reviews caught that the implementers did not

1. **`_PROCESS_NAME_RE` vs. the two-segment permission invariant (blocker).** Seven call sites
   (`nx_lib/views/workitems.py`, `nx_lib/process_helpers.py`) reconstruct a process name from
   `workitems.filter.process.<name>` as *exactly the last two dot-segments*. The admin UI would have
   accepted any dot count, so `Invoice` and `acme.eu.01_Invoice` would silently never match a grant —
   and `x.acme.01_Invoice` reduces to `acme.01_Invoice`, a **cross-tenant** collision any holder of
   `admin.edit.processes` could mint. Now pinned to exactly one dot, server-side and in the HTML
   `pattern`, with a reduction-collision check before the INSERT.
2. **Talisman overwrote the logo route's `Content-Security-Policy: sandbox` on PROD.** The one control
   that justifies allowing script-capable SVG existed on INT (no CSP at all) and was absent on PROD.
   Now applied via Talisman's per-view override, with a test that runs with Talisman actually installed.
3. **The client edit form silently NULLed four columns.** Editing the `ms02` row's display name wiped
   its stats and doc-field engine bindings — MS02 statistics and doc-field search would have broken
   after the next app-pool recycle.
4. **`logout()` leaves `organizationcode` in the session**, so the login page kept the ex-user's brand.
   Worked around by gating `_inject_brand` on `"userid" in session`; the root cause is untouched.

## Owner actions

1. **Push** — `v3.2.3.1` is unpushed.
2. **Two migrations are numbered `0079`.** A peer landed `0079_add_reporting_source_schema_permission.sql`
   while this ran; ours is `0079_clients_registry.sql`. `db-migrate.py` keys on filename, both are applied
   on INT, `--dry-run` is `up-to-date`, and they are independent (a permission insert vs. a new table), so
   ordering does not matter. Nothing to fix — just know it before reading the migration list.
3. **Check who holds `admin.view.organizations` on PROD.** Migration `0080` grants the two *edit*
   permissions to every profile that already holds it (on INT: `enterpriseAdmin`, `globalAdmin`).
   `admin.edit.processes` is high-trust — a holder can repoint a granted process's `TableName` at another
   customer's table, with no new grant and no audit trail. Documented in `docs/howto/white-label.md`.
4. **`0079` seeds the `ms02` row on PROD unconditionally.** Behaviour is unchanged (the row is skipped at
   build if PROD's `env/PROD.env` lacks the `MS02_*` keys), and `/admin/clients` now shows
   "Configured, not loaded" for exactly that case.
5. **File follow-up issues:** `logout()` should `session.clear()`; the clients-page toast/reload race,
   dead `MutationObserver` and speculative `#add-client` deep-link; field-length and `OctoDomain`
   validation on the client payload; `WorkitemSourceCache` orphans on client delete.
6. Optional: file the phase-4 GitHub issue linking the spec, the plan and `057a2ebd`.

## Test state at merge

- `tests/unit`: **1384 passed, 22 skipped.**
- `tests/integration`: 690 passed, **7 failed** — six `test_dashboard_routes.py::test_recent_activity_*` /
  `test_processed_over_time_*` plus one flaky `test_auth_routes.py` login-fixture test. **All pre-existing:**
  reproduced identically on the pre-merge `v3.2.3.1` HEAD (`e72baff0`) in a scratch worktree. They pass in
  isolation and fail only after `test_reporting_routes.py` runs first — cross-file monkeypatch leakage,
  not this work. Worth its own issue.
- Migrations: `--dry-run` reports `up-to-date` for NexoraDB and GeneraliDB on INT.

## Gotchas

1. **The `sql/NexoraDB/Tables/*.sql` files that show as modified with an empty `git diff` are CRLF drift**,
   not content. Do not stage them. Two untracked peer dumps
   (`dbo.KundenmagazinIssue{s,Organizations}.sql`) belong to another session — leave them.
   Several commits used the sanctioned `SQL_SYNC_SKIP=1` for exactly this; no schema of ours escaped
   the per-object dumps (verified in the final review).
2. **The merge had two semantic conflicts git resolved cleanly but wrongly.** `CHANGELOG.md` needed a
   union plus dropping a block the peer's release promotion had already relocated, and
   `tests/unit/test_security.py::test_page_visibility_returns_all_18_keys` had to become `_20_keys` —
   the peer's count assertion versus our two new keys. Both fixed in the merge commit.
3. **The `.po`/`.mo` conflict was resolved by regenerating**, not by picking a side: extract → update →
   fill each locale from both sides' catalogs → compile. `test_translations.py` is green, 0 fuzzy,
   0 untranslated in de/fr/it.
4. **PRVR is left branded on INT** (deliberate, from Task 12's browser verification); SYDC was reverted.
   `var/branding/PRVR.png` exists on the dev box.
5. Screenshots from the browser verification are in `var/screenshots/wl-01..wl-10` (gitignored).

## How to verify

```powershell
git log --oneline -1                                 # 057a2ebd merge commit
git worktree list                                    # only C:/dev/nexora
git branch --list feat/white-label                   # empty
python scripts/db-migrate.py --env INT --dry-run     # up-to-date
.venv\Scripts\python.exe -m pytest tests/unit -q --no-cov
```
