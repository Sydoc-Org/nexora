# pdbsUser Access-Profile Assignment Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. This plan was adversarially reviewed by three agents (anchor-verification, executor red-team, security) on 2026-07-13; their findings are folded in — trust the anchors.

**Goal:** Make the `pdbsUser` access profile assignable in the admin UI (add-user AND edit-user flows) for holders of its assign permission, and fix the three confirmed defects around it: (1) a **case-mismatch** between the hand-inserted permission code `admin.assign.user.accessprofile.pdbsUser` and the lowercased code the app checks; (2) the admin **permission add/edit/all-permissions APIs 500 on every environment** because they reference a `Permission.SortingCode` column that was never migrated — which is why the permission row was hand-typed in SSMS in the first place; (3) an **authz gap**: `admin_add_user` never checks the assign permission (the add-user dropdown is the only gate; a direct POST can assign ANY profile, including `enterpriseAdmin`, with only `admin.create.user`). The gate fix closes the **add-user** escalation specifically; the user-override editor and profile editor are separately-gated trust boundaries and stay as they are.

**Confirmed root cause (do not re-investigate):**
- `nx_lib/security.py` `has_permission` is an exact, case-sensitive set-membership check: `return code in perms`.
- `nx_lib/views/admin.py` builds assign codes lowercased at three sites (anchor snippet, appears 3×): `f"admin.assign.user.accessprofile.{str(accessprofile).lower()}"` / `f'admin.assign.user.accessprofile.{str(ap["profile"]).lower()}'` — in `admin_edit_user` (403 gate), `admin_user_detail` (assignable list), `admin_access_control` (assignable list).
- Live INT `dbo.Permission` (verified 2026-07-13): all nine older assign rows are lowercase (`...issuser`, `...nexorauser`, …); **only** PermissionID 179 is mixed-case: `admin.assign.user.accessprofile.pdbsUser`. PROD has the same hand-inserted row. So the app checks `...pdbsuser`, the grant says `...pdbsUser`, and the profile is silently filtered out of every assignable-profiles dropdown; direct edit 403s.
- Live INT `dbo.Permission` columns are ONLY `PermissionID, Code, Description` (verified via INFORMATION_SCHEMA). `api_admin_permission_add`, `api_admin_permission_edit`, and `api_admin_user_all_permissions` all reference `SortingCode` → those routes throw and return 500 today on INT and PROD. `sql/test/schema.sql` also lacks the column, and the integration tests tolerate it via `assert resp.status_code in (200, 500)` — which is why CI never caught it.
- Live INT collation is `SQL_Latin1_General_CP1_CI_AS` (case-insensitive; verified via `DATABASEPROPERTYEX`) and `Permission.Code` carries a UNIQUE constraint — so two codes differing only by case cannot coexist, which makes case-insensitive matching in `has_permission` unambiguous. The per-object dump only proves the UNIQUE constraint, not the collation; the migration below is written collation-proof anyway.

**Architecture of the fix (defense in depth, all layers small):**
1. Migration `0034`: add `SortingCode nvarchar(50) NULL` to `dbo.Permission` + lowercase the stray `pdbsUser` code row. Data + schema repair for INT (auto-applied by the pre-commit hook) and PROD (auto-applied by the next deploy).
2. `has_permission` becomes case-insensitive (lowercase both sides) — kills the trap for every `has_permission` / `require_permission` call site, including future hand-inserted rows.
3. The maintenance-bypass check in `nx_lib/hooks.py` does raw `in session['permissions']` — route it through `has_permission` so it benefits too. (Two other raw-membership holdouts exist in `nx_lib/reporting/sources.py` `accessible()` and `nx_lib/reporting/runner.py`; they are **deliberately out of scope** — reporting source grants are their own machinery. Noted as follow-up.)
4. `admin_add_user` gets the same assign-permission gate `admin_edit_user` already has.
5. The over-tolerant integration tests are tightened and a strict add→edit→delete round-trip is added, so a broken permission API can never ride green again.

**Explicitly NOT done (decided against, don't add back):** lowercasing permission codes at creation/edit time. Live INT holds **case-significant** codes — `dashboard.filter.process.sydoc.05_PDBS` (ID 176) and `workitems.filter.process.sydoc.05_PDBS` (ID 177) — whose last segments are extracted **verbatim** by `nx_lib/process_helpers.py` and compared case-sensitively against Postgres process names. Normalizing on save would corrupt any such code re-saved through the UI. Case-insensitive **matching** (layer 2) fixes the assign trap without touching stored case.

**Tech stack:** Python 3.13 / Flask, pyodbc raw cursors in `nx_lib/views/admin.py`, pytest (`tests/unit`, `tests/integration` against NEXORA_TEST), SQL Server migrations under `sql/_migrations/NexoraDB/`.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.64` (already exists, tracks origin). This plan file is already committed. Commit per task. **Do NOT push and do NOT open a PR** — the owner reviews and pushes (the pre-push hook runs the full suite incl. Playwright e2e, owner runs it).
- **TDD is the house rule:** each task writes the failing test first, sees it fail, then implements. Use `superpowers:test-driven-development`.
- **Anchor on snippets, never line numbers** — quote-match the exact code shown in each task; line numbers drift.
- **Monkeypatching `has_permission` — two different targets (this bit the plan's first draft):** `nx_lib/views/admin.py` does `from ..security import ... has_permission ...` at module load, so **inline** calls inside route bodies resolve `nx_lib.views.admin.has_permission`. Patching `nx_lib.security.has_permission` reaches **only** the `@require_permission` decorator closures. The existing `admin_all_perms` fixture patches the security module — it does NOT reach inline gates. The repo's established pattern for inline gates patches the view module (see `tests/integration/test_workitems_routes.py`, `monkeypatch.setattr(wv, "has_permission", ...)`). Also note: the header comment in `test_admin_routes.py` claiming admin@test.local has only 3 permissions is stale — `sql/test/seed.sql` grants the TestAdmin profile **every seeded permission** (but NO `admin.assign.user.accessprofile.*` rows exist in the seed at all).
- **Test cleanup goes through the app, not `db_conn`:** the `db_conn` fixture is transaction-scoped and **rolls back** at test end, while routes commit through the app's own connection — rows created via routes survive. There is no add-then-cleanup precedent in `test_admin_routes.py`. Clean up by calling the app's delete APIs in `try/finally` (`/api/admin/permissions/delete/<id>`, and the admin user-delete route — read its registration in `admin.py` for the exact path).
- **Migration numbering:** next free number was `0034` on 2026-07-13 (`sql/_migrations/NexoraDB/` tops out at `0033_create_prepared_documents.sql`). **Re-list the directory at execution time** and bump if taken. Migrations MUST be idempotent — the pre-commit hook auto-applies them to INT and may re-run them.
- **`*.sql` is pinned to LF** by `.gitattributes` — write the migration with the Write tool (LF), not shell heredocs.
- **Pre-commit hook** runs `scripts/db-migrate.py --env INT` + `sql/sync-from-db.py --check` on every commit. The new column changes `dbo.Permission` DDL, so the sync step will regenerate `sql/NexoraDB/Tables/dbo.Permission.sql` — **`git add` the regenerated file into the same commit** when the hook reports drift. Never hand-edit files under `sql/NexoraDB/`. `SQL_SYNC_SKIP=1` is only for INT-unreachable flakes, never to silence a real failure.
- **gitlint:** conventional-commit title, no "WIP" in title, body required.
- **Test commands:** unit `.venv\Scripts\python -m pytest tests/unit/test_security.py -q`; integration `.venv\Scripts\python -m pytest tests/integration/test_admin_routes.py -q`. Integration tests hit the NEXORA_TEST DB on INTSQL01. **`scripts/test_db_reset.py` applies `sql/test/schema.sql` + `seed.sql`** — run it after Task 1 edits schema.sql so NEXORA_TEST actually has the new column.
- **i18n:** reuse the existing translated string `_("Permission Denied for this action.")` for the new 403 — introduce **no new user-facing strings**, then no pybabel cycle is needed. If you do add a string, you must run the full `/nx-i18n` cycle or the gate fails.
- **No template changes are required** (dropdowns are server-populated from `assignable_profiles`). For the live browser verification, restart the dev server first — templates and code are cached for the process lifetime.
- **No new top-level files/dirs** → no `deploy.yml` exclude changes.

---

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| 1 | Keep the `.lower()` convention at the three assign-check sites; do NOT switch them to verbatim profile names | Nine existing lowercase rows depend on it; verbatim would need renaming all of them |
| 2 | `has_permission` lowercases both sides | CI-unique `Permission.Code` (live INT collation `SQL_Latin1_General_CP1_CI_AS`) means case variants can't coexist → widening is unambiguous; protects against future SSMS hand-inserts |
| 3 | Migration also lowercases the stray row (belt + braces with #2), with a collation-proof WHERE | DB stays convention-consistent; works even if a future environment were CS-collated |
| 4 | `SortingCode` is `nvarchar(50) NULL` | UI placeholder is "e.g. A1"; NULLs sort first under `ORDER BY p.SortingCode, p.Code`, acceptable |
| 5 | `admin_add_user` reuses the gate shape from `admin_edit_user` (403 + logger), but with parameterized logging | Consistency; the f-string variant would let request-controlled values inject newlines into `var/logs/system/app.log` |
| 6 | NO lowercase-on-save in the permission CRUD routes | Would corrupt case-significant `*.filter.process.<client>.<Process>` codes matched verbatim against Postgres (see "Explicitly NOT done") |
| 7 | Only the pdbsUser row is data-fixed; no blanket `LOWER(Code)` sweep | Same reason as #6 |

---

## Task 1 — Migration 0034: SortingCode column + pdbsUser code case

- [ ] Create `sql/_migrations/NexoraDB/0034_permission_sortingcode_and_pdbsuser_case.sql` (re-verify the number is free):

```sql
-- 0034_permission_sortingcode_and_pdbsuser_case.sql
-- 1) dbo.Permission.SortingCode: referenced by the admin permission APIs
--    (api_admin_permission_add/edit, api_admin_user_all_permissions) since the
--    April admin redesign, but the column was never migrated -> those routes 500.
-- 2) Normalize the one hand-inserted mixed-case assign code to the lowercase
--    convention the app checks (admin.py builds codes with .lower()).
-- Idempotent: guarded / naturally re-runnable. LOWER() makes the match
-- collation-proof (CI or CS).

IF COL_LENGTH('dbo.Permission', 'SortingCode') IS NULL
    ALTER TABLE dbo.Permission ADD SortingCode nvarchar(50) NULL;
GO

UPDATE dbo.Permission
SET Code = 'admin.assign.user.accessprofile.pdbsuser'
WHERE LOWER(Code) = 'admin.assign.user.accessprofile.pdbsuser';
GO
```

- [ ] Add the column to the test schema: in `sql/test/schema.sql`, find the `CREATE TABLE` for `Permission` (anchor: the `Code` + `Description` column pair) and add `SortingCode nvarchar(50) NULL` after `Description`. Do NOT touch `sql/test/seed.sql` (its inserts name their columns).
- [ ] Run `.venv\Scripts\python scripts/test_db_reset.py` so NEXORA_TEST picks up the column.
- [ ] Commit (`fix(db): add Permission.SortingCode + normalize pdbsUser assign code (0034)`). The hook applies 0034 to INT and regenerates `sql/NexoraDB/Tables/dbo.Permission.sql` — add the regenerated dump to the same commit when the sync step flags it.

**Verify:** query INT INFORMATION_SCHEMA → the column exists; `SELECT Code FROM Permission WHERE Code LIKE '%pdbs%'` returns the all-lowercase code.

## Task 2 — has_permission becomes case-insensitive (unit-first)

- [ ] In `tests/unit/test_security.py`, add failing tests following the file's existing session-mocking pattern: with `session['permissions'] = ['admin.assign.user.accessprofile.pdbsUser']`, `has_permission('admin.assign.user.accessprofile.pdbsuser')` is True; the reverse direction too; a genuinely-absent code stays False.
- [ ] Implement in `nx_lib/security.py` — anchor:

```python
def has_permission(code: str) -> bool:
    perms = set(session.get("permissions", []))
    return code in perms
```

becomes lowercase-both-sides (e.g. `return code.lower() in {p.lower() for p in perms}`). Keep the signature and style.
- [ ] Run the unit file AND grep `tests/` for any test asserting case-SENSITIVE permission behavior (none known, but confirm) — all green. Commit (`fix(security): case-insensitive permission code matching`), body citing the CI-unique-index safety argument.

## Task 3 — Route the maintenance-bypass check through has_permission

- [ ] In `nx_lib/hooks.py`, find the raw membership check (anchor: `"admin.maintenance.bypass" in (session.get("permissions") or [])`) and replace it with `has_permission("admin.maintenance.bypass")` (import it the way the module already imports from `nx_lib.security`, or add the import).
- [ ] If a unit test covers the maintenance hook, extend it with a mixed-case session entry proving the bypass now matches case-insensitively; if none exists, add a minimal one only if the file's structure makes it cheap — otherwise the Task 2 unit tests already cover the function itself.
- [ ] Commit (`refactor(hooks): use has_permission for maintenance bypass`). Body notes the remaining raw-membership holdouts (`nx_lib/reporting/sources.py` `accessible()`, `nx_lib/reporting/runner.py`) are deliberate follow-ups, not oversights.

## Task 4 — Tighten the permission-API tests + strict round-trip

- [ ] In `tests/integration/test_admin_routes.py` (all use `admin_all_perms` — fine here, these routes gate via decorators only):
  - `test_api_admin_user_all_permissions` → `assert resp.status_code == 200`
  - `test_api_admin_permission_add_missing_body` → `assert resp.status_code == 400`
  - `test_api_admin_permission_edit_unknown` → `assert resp.status_code == 404` (route checks `cursor.rowcount == 0` → 404)
  - `test_api_admin_permission_delete_unknown` → `assert resp.status_code == 404` (same pattern)
  - `test_api_admin_permissions_list` already asserts 200 — no change.
- [ ] Add `test_api_admin_permission_crud_roundtrip`: POST `/api/admin/permissions/add` with `{"code": "test.roundtrip.perm", "description": "d", "sortingCode": "Z9"}` → 200 + `permissionId`; edit it via `/api/admin/permissions/edit/<id>` (change description) → 200; verify via `db_conn` SELECT that Code and SortingCode round-tripped **with case preserved**; finally DELETE `/api/admin/permissions/delete/<id>` → 200 — the delete is the cleanup, wrap add→…→delete in `try/finally` so a mid-test failure still deletes.
- [ ] Run the integration file against the reset NEXORA_TEST; all green (these now exercise the SortingCode paths for real).
- [ ] Commit (`test(admin): permission APIs must not 500 — strict statuses + CRUD round-trip`).

## Task 5 — Close the add-user authz gap

- [ ] Failing tests first, in `tests/integration/test_admin_routes.py`. **Patch the view-module binding** (see Context):
  - **Deny path:** `monkeypatch.setattr("nx_lib.views.admin.has_permission", lambda code: not code.startswith("admin.assign.user.accessprofile."))` — the `@require_permission("admin.create.user")` decorator still passes because it resolves the REAL `nx_lib.security.has_permission` and TestAdmin is seeded with every permission. POST the add-user route (find the exact path from `admin_add_user`'s registration in `admin.py`; the existing `test_admin_add_user_duplicate_returns_409_or_500` shows a working request body) with `"accessprofile": "TestUser"` → **assert 403** and via `db_conn` that no user row was created.
  - **Allow path:** `monkeypatch.setattr("nx_lib.views.admin.has_permission", lambda code: True)` (do NOT rely on `admin_all_perms` — it cannot reach the inline gate), same POST with a unique username → 200; clean up via the app's admin user-delete route in `try/finally`.
- [ ] **Update the existing test** `test_admin_add_user_duplicate_returns_409_or_500`: add the same `monkeypatch.setattr("nx_lib.views.admin.has_permission", lambda code: True)` so it keeps exercising the duplicate-409 path instead of dying on the new 403 (no `admin.assign.*` rows exist in the seed).
- [ ] Implement in `admin_add_user`: insert the gate **immediately after the `if not all([...])` guard** — before the bcrypt hash and before any DB connection is opened (unlike `admin_edit_user`, no cursor is needed for the check):

```python
if not has_permission(f"admin.assign.user.accessprofile.{str(accessprofile).lower()}"):
    current_app.logger.error(
        "assign-permission denied: profile=%r username=%r",
        str(accessprofile)[:100],
        str(username)[:100],
    )
    return jsonify({"success": False, "message": _("Permission Denied for this action.")}), 403
```

(Parameterized `%r` logging on purpose — the values are request-controlled; do not switch to an f-string.)
- [ ] Run the integration file; green. Commit (`fix(admin): enforce assign-profile permission on user creation`) — body notes this closes the **add-user** escalation path for `admin.create.user` holders (user-override and profile editors remain separately-gated trust boundaries).

## Task 6 — Changelog + docs

- [ ] `CHANGELOG.md` under `[Unreleased]`: **Fixed** — camelCase-named access profiles (e.g. `pdbsUser`) were unassignable even when granted (case-mismatch vs the lowercased check; permission matching is now case-insensitive and the stray row is normalized by migration `0034`); **Fixed** — admin permission add/edit and the user all-permissions API returned 500 everywhere (missing `Permission.SortingCode`, added by `0034`); **Fixed/Security** — user creation now enforces `admin.assign.user.accessprofile.<profile>` like user edit already did.
- [ ] Grep `docs/` for `accessprofile` / permission-admin howtos; if any page documents permission-code conventions or the admin UI, add the "codes are lowercase by convention; matching is case-insensitive; `*.filter.process.*` tails are case-significant" note. If none exists, skip — do not author a new doc.
- [ ] Commit (`docs(changelog): pdbsUser assign fix + permission API repairs`) — or fold into Task 5's commit.

## Task 7 — Live verification on INT (browser, self-driven)

- [ ] Restart the dev server: `nx -u -b --loginas:ben.streich` (INT). Playwright: open Admin → Access Control (and the user-detail page of any user).
- [ ] Assert `pdbsUser` now appears in the access-profile dropdown of the **add-user** modal and the **edit-user** panel (it was absent before the fix).
- [ ] Create a throwaway user with profile `pdbsUser` end-to-end → success; then delete the user via the admin UI.
- [ ] In Access Control's permission manager, add a throwaway permission (any code) → verify the API no longer 500s and the row appears; delete it.
- [ ] Screenshots of the dropdown + created user to `var/screenshots/pdbsuser-assign-*.png`; SendUserFile them if the session is remote.

## Owner actions (not for the executor)

1. **PROD fix timing:** migration `0034` reaches PROD automatically on the next deploy (merge to main). To fix PROD immediately instead: `python scripts/db-migrate.py --env PROD` from a SQL-reachable box (idempotent; it will also record `0032`, which is safe — its rows already exist by hand). Optional sanity: `SELECT DATABASEPROPERTYEX(DB_NAME(),'Collation')` on PROD should report a `_CI_` collation like INT's `SQL_Latin1_General_CP1_CI_AS`.
2. After deploy, spot-check on PROD: assign `pdbsUser` to one user via the UI.
3. Review + push `feature/2.5.64` (full pre-push gate).

## Follow-ups deliberately NOT in this plan

- Case-insensitive matching for the reporting raw-membership sites (`nx_lib/reporting/sources.py` `accessible()`, `nx_lib/reporting/runner.py`) — reporting source grants are their own machinery; touch only with reporting tests in hand.
- `admin_edit_user` currently lets an assign-permission holder change the password of ANY existing user, including ones whose current profile they could not assign — consider requiring the assign permission for the target's CURRENT profile too. Separate spec-worthy discussion.
- The stale header comment in `tests/integration/test_admin_routes.py` ("admin@test.local: admin.view + admin.users.manage + dashboard.view" — TestAdmin actually holds every seeded permission); fix opportunistically when editing that file.
