# Permission structure — rename, rank, process scope, grid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** Turn the 144-code permission catalogue into 112 codes under one grammar, make profile grants allow-only, replace the ten per-profile assign codes with a rank, collapse three per-process families into one, and replace the 144-row drawer plus the read-only matrix with a permissions × profiles grid.

**Architecture:** Three data-driven NexoraDB migrations (cleanup+rank, process scope, rename) keep every grant by `PermissionID`. A one-off sweep script rewrites string literals across `nx_lib/`, `templates/`, `tests/`, `sql/test/seed.sql` and `docs/`, emits the rename migration, and is deleted in the same commit. A shared `group_permissions()` helper feeds the new `/admin/permissions` grid and the user-detail overrides. A convention unit test holds the grammar.

**Tech Stack:** Flask + Jinja2, pyodbc raw cursors (house style in `nx_lib/views/admin/`), SQL Server T-SQL migrations via `scripts/db-migrate.py`, vanilla JS (#191 shim pattern, `window.NX`), pytest (unit/integration against NEXORA_TEST), Playwright e2e (CI-only).

**Spec:** `docs/superpowers/specs/2026-09-01-permission-structure-design.md` — decisions D1–D6 and Appendix A (the full code mapping) are authoritative. Issue: #238.

## Global Constraints

- Code grammar: `<area>[.<object>[.<sub>]].<action>[.<scope>]`; actions `view add edit delete use run export schedule manage bypass import restart`; scopes `org all pastdeadline`. Regex in Task 11.
- Grants preserved by `PermissionID`; migrations key on codes that exist (PROD's catalogue may differ from INT).
- Migrations are immutable once applied; new files only. Numbers **0086–0088** (0083–0085 belong to the tenant-kernel worktree and are already applied on INT). Run `python scripts/db-migrate.py --env INT --dry-run` before creating each file and renumber if taken.
- Hand-built URLs in JS go through `API_PREFIX`; no inline `onclick=` (CSP on PROD; `tests/unit/test_no_inline_event_handlers.py` fails the build).
- Templates are cached for the process lifetime: `nx -r` after every template edit before browser checks.
- Never `--no-verify`. If the SQL pre-commit hooks block on unrelated INT drift (the tenant tables), use `SQL_SYNC_SKIP=1 git commit ...`.
- Remote session policy: commit, never push, never open a PR.

---

## Context an engineer needs (read first)

- **Branch / worktree:** plan authored in worktree `.claude/worktrees/plan-permission-structure-rename-grid` on `plan/permission-structure-rename-grid` (from `v3.2.4.1` @ `630cb99d`). Execute there. The main checkout has unrelated INT-drift dumps under `sql/NexoraDB/Tables/` — never stage them.
- **Worktree has no secrets or venv:** `env/*.env` are gitignored, so the worktree only has the `.example` files and every DB call fails with `TypeError: 'NoneType' object is not iterable` from `URLSafeTimedSerializer`. Before Task 1: `cp ../../../env/INT.env ../../../env/TEST.env env/` (never commit them). The venv lives in the main checkout: prepend `C:\dev\nexora\.venv\Scripts` to `PATH` for `pytest`/`python`.
- **In-flight work:** `feat/tenant-kernel` (worktree `plan-tenant-kernel-ms02-pilot`) owns migrations 0083–0085 and seeds `tenant.ms02.*`; we keep those two codes untouched. `plan/beautify-phase-2-3` touches views broadly — rebase conflicts are possible in `nx_lib/views/reporting.py` and `nx_lib/views/workitems.py`; keep our edits to the process-scope helpers small.
- **How permissions flow:** `dbo.spGetUserPermissions` → `session['permissions']` (list of codes), refreshed per request through `nx_lib/user_cache.py` (30 s TTL); `_invalidate_user_cache` in `nx_lib/hooks.py` clears the cache on writes whose path starts with `/admin` — **`/api/admin/*` writes are not covered**, so the new grants API clears it explicitly.
- **Test DB:** `sql/test/schema.sql` + `sql/test/seed.sql`, reset with `python scripts/test_db_reset.py` (prepend `.venv\Scripts` to PATH). `admin@test.local` (profile TestAdmin) holds every seeded code; `user@test.local` (TestUser) has `dashboard.view`; `noperm@test.local` none. The `admin_all_perms` fixture in `tests/integration/test_admin_routes.py` monkeypatches `nx_lib.security.has_permission` to `True`.
- **Process codes carry no client in the DB key**: `ProcessName` is already `<client>.<name>`; `_permission_reduction()` in `nx_lib/views/admin/processes.py` takes its last two segments.
- **Hidden code stores:** `dbo.ReportingSources.Permission` (registry column), `nx_lib/reporting/sources.py` (static sources), `nx_lib/whats_new.py` (`perm` and `endpoint` per entry; `tests/unit/test_whats_new.py` requires `perm` to match `[a-z0-9_.]+`).
- **Migrations needed: YES** (0086, 0087, 0088). **i18n needed: YES** (Phase 4 adds UI strings — run the `nx-i18n` skill). **Deploy excludes: none** (no new top-level paths). **Env keys: none.**
- **Deploy blip (D6):** migrations run before the app pool stops; the old build 403s for the deploy window. Deploy off-hours; say so in the release notes.

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | Full rename to one grammar via `UPDATE dbo.Permission SET Code=...` joined on old code. | Grants ride on `PermissionID`; no re-granting. |
| D2 | Grid editor `permissions × profiles` replaces the drawer **and** `/admin/permission_matrix`. | One page shows every profile; the matrix's "who holds it" folds in as a row panel. |
| D3 | `generali.*` → `tenant.generali.*` now. | Owner decision 2026-09-01; the tenant platform finds the codes in place. |
| D4 | One release, four commits (one per phase). | Owner decision. |
| D5 | Assign rule: `target.Rank <= actor.Rank`. | Admins can create peers; globalAdmin gains globalAdmin + pdbsUser. |
| D6 | Accept the deploy blip; no additive double catalogue. | Simplest migration; off-hours deploy. |
| D7 | `prepare_process_selection_*` lose their `prefix` parameter; one shared `granted_processes(perms)`. | One family means one parser; the parameter would be vestigial. |
| D8 | `_allowed_processes()` in `views/reporting.py` stays as a one-line wrapper. | Five tests patch `nx_lib.views.reporting._allowed_processes`. |
| D9 | The sweep script is committed-then-deleted in Phase 3; the mapping survives in migration 0088 and the spec. | No second source of truth in the tree. |

## Owner actions

- Deploy off-hours (D6). Before deploying, run `scripts/env-sync.py` as usual (no new keys expected).
- After PROD deploy, open `/admin/permissions` once and eyeball the grid against the pre-deploy profile screenshots in `var/screenshots/238_*.png`.

---

# PHASE 1 — Profile grants allow-only, profile rank (migration 0086)

### Task 1: Test schema + seed for the new grant model

**Files:**
- Modify: `sql/test/schema.sql`
- Modify: `sql/test/seed.sql`

**Interfaces:**
- Produces: `dbo.AccessProfilePermission(AccessID, PermissionID)` without `Effect`; `dbo.AccessProfile.Rank int`; `dbo.fnUserHasPermission` and `dbo.spGetUserPermissions` with the new resolution order. Every later task's integration tests run on this.

- [ ] **Step 1: Edit `sql/test/schema.sql`** — in the block starting `CREATE TABLE dbo.AccessProfile (` add `Rank INT NOT NULL DEFAULT 0,` after `Description`. In `CREATE TABLE dbo.AccessProfilePermission (` delete the line `Effect CHAR(1) NOT NULL CHECK (Effect IN ('A', 'D')),`. Replace the body of `CREATE FUNCTION dbo.fnUserHasPermission` (after `IF @PermID IS NULL RETURN 0;`) with:

```sql
    IF EXISTS (SELECT 1 FROM dbo.UserPermissionOverride
               WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'D') RETURN 0;
    IF EXISTS (SELECT 1 FROM dbo.UserPermissionOverride
               WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'A') RETURN 1;
    IF EXISTS (SELECT 1 FROM dbo.Users u
               JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessid
               WHERE u.userID = @UserID AND ap.PermissionID = @PermID) RETURN 1;
    RETURN 0;
```

and replace the body of `spGetUserPermissions` with the set-based query:

```sql
    SELECT p.Code
    FROM dbo.Permission p
    WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                      WHERE o.UserID = @UserID AND o.PermissionID = p.PermissionID AND o.Effect = 'D')
      AND ( EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                    WHERE o.UserID = @UserID AND o.PermissionID = p.PermissionID AND o.Effect = 'A')
         OR EXISTS (SELECT 1 FROM dbo.Users u
                    JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessid
                    WHERE u.userID = @UserID AND ap.PermissionID = p.PermissionID) );
```

- [ ] **Step 2: Edit `sql/test/seed.sql`** — `INSERT INTO dbo.AccessProfile (Name, Description) VALUES` becomes `(Name, Description, Rank)` with `('TestAdmin', ..., 100)`, `('TestUser', ..., 10)`, `('TestNoPerm', ..., 0)`. Both `INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)` statements become `(AccessID, PermissionID)` and drop the `, 'A'` from their SELECT lists. Delete the seed row `('admin.interact.users.all', 'Interact with all users'),`. The `UserPermissionOverride` insert for `noai@test.local` stays as is.

- [ ] **Step 3: Reset and run the guard tests**

Run: `python scripts/test_db_reset.py && pytest tests/integration/test_permission_guard.py tests/integration/test_auth_flow.py -q`
Expected: PASS (admin 200, noperm 403, noai override still denies).

- [ ] **Step 4: Commit**

```bash
git add sql/test/schema.sql sql/test/seed.sql
git commit -m "test(db): allow-only profile grants and AccessProfile.Rank in the test schema"
```

### Task 2: Migration 0086 — cleanup, rank, orphans, resolver rewrite

**Files:**
- Create: `sql/_migrations/NexoraDB/0086_permission_cleanup_and_rank.sql`

- [ ] **Step 1: Check the number is free**

Run: `python scripts/db-migrate.py --env INT --dry-run`
Expected: nothing pending; highest applied `0085_seed_ms02_tenant.sql`. If 0086 exists anywhere (`ls sql/_migrations/NexoraDB ../*/sql/_migrations/NexoraDB`), take the next free number and update the two later migration names in this plan.

- [ ] **Step 2: Write the migration** (`GO`-separated, idempotent):

```sql
-- 0086_permission_cleanup_and_rank.sql  (#238 phase 1)
-- Profile grants become allow-only: a profile-level DENY was identical to "no
-- row" (one profile per user, default deny). Adds AccessProfile.Rank, which
-- replaces the ten admin.assign.user.accessprofile.* codes (rule: an actor may
-- assign a profile whose Rank <= their own). Deletes orphan codes. Rewrites
-- the resolver function and the set-based permission proc.

DELETE FROM dbo.AccessProfilePermission WHERE Effect = 'D';
GO
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_AccessProfilePermission_Effect')
    ALTER TABLE dbo.AccessProfilePermission DROP CONSTRAINT CK_AccessProfilePermission_Effect;
GO
IF COL_LENGTH('dbo.AccessProfilePermission', 'Effect') IS NOT NULL
    ALTER TABLE dbo.AccessProfilePermission DROP COLUMN Effect;
GO
IF COL_LENGTH('dbo.AccessProfile', 'Rank') IS NULL
    ALTER TABLE dbo.AccessProfile ADD Rank INT NOT NULL CONSTRAINT DF_AccessProfile_Rank DEFAULT 0;
GO
UPDATE dbo.AccessProfile SET Rank = CASE
    WHEN Name = 'enterpriseAdmin' THEN 100
    WHEN Name = 'globalAdmin' THEN 90
    WHEN Name LIKE '%Supervisor' THEN 50
    ELSE 10 END
WHERE Rank = 0;
GO
-- Orphans (retired invoices page #177, Kundenmagazin, two dead admin codes)
-- and the ten assign meta-codes. Grant rows first (FKs), then the codes.
DECLARE @dead TABLE (PermissionID INT PRIMARY KEY);
INSERT INTO @dead SELECT PermissionID FROM dbo.Permission
WHERE Code LIKE 'invoices.%' OR Code LIKE 'kundenmagazin.%'
   OR Code IN ('admin.interact.users.all', 'admin.view.mobscn.processmanagement')
   OR Code LIKE 'admin.assign.user.accessprofile.%';
DELETE FROM dbo.AccessProfilePermission WHERE PermissionID IN (SELECT PermissionID FROM @dead);
DELETE FROM dbo.UserPermissionOverride  WHERE PermissionID IN (SELECT PermissionID FROM @dead);
DELETE FROM dbo.Permission              WHERE PermissionID IN (SELECT PermissionID FROM @dead);
GO
CREATE OR ALTER FUNCTION dbo.fnUserHasPermission (@UserID INT, @PermCode SYSNAME)
RETURNS BIT AS
BEGIN
    DECLARE @PermID INT = (SELECT PermissionID FROM dbo.Permission WHERE Code = @PermCode);
    IF @PermID IS NULL RETURN 0;
    IF EXISTS (SELECT 1 FROM dbo.UserPermissionOverride
               WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'D') RETURN 0;
    IF EXISTS (SELECT 1 FROM dbo.UserPermissionOverride
               WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'A') RETURN 1;
    IF EXISTS (SELECT 1 FROM dbo.Users u
               JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessid
               WHERE u.userID = @UserID AND ap.PermissionID = @PermID) RETURN 1;
    RETURN 0;
END;
GO
CREATE OR ALTER PROCEDURE dbo.spGetUserPermissions @UserID INT AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.Code
    FROM dbo.Permission p
    WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                      WHERE o.UserID = @UserID AND o.PermissionID = p.PermissionID AND o.Effect = 'D')
      AND ( EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                    WHERE o.UserID = @UserID AND o.PermissionID = p.PermissionID AND o.Effect = 'A')
         OR EXISTS (SELECT 1 FROM dbo.Users u
                    JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessid
                    WHERE u.userID = @UserID AND ap.PermissionID = p.PermissionID) );
END;
GO
```

- [ ] **Step 3: Apply to INT and prove the counts**

Run: `python scripts/db-migrate.py --env INT` then
```
ENVIRONMENT=INT python -c "from nx_lib.db import engine_nexora_db as e; from sqlalchemy import text; c=e.connect(); print(c.execute(text('select count(*) from dbo.Permission')).scalar(), c.execute(text('select count(*) from dbo.AccessProfilePermission')).scalar(), [tuple(r) for r in c.execute(text('select Name, Rank from dbo.AccessProfile order by Rank desc'))])"
```
Expected: `122 340 [...]` (144 − 22 codes; 855 − 446 deny rows − 69 grants that sat on deleted codes; measured on INT 2026-09-01), enterpriseAdmin 100, globalAdmin 90, two supervisors 50, rest 10. Commit-time hooks will also re-apply (idempotent guards make that a no-op).

- [ ] **Step 4: Commit**

```bash
git add sql/_migrations/NexoraDB/0086_permission_cleanup_and_rank.sql
git commit -m "feat(db): drop profile-level deny, add AccessProfile.Rank, delete orphan permission codes"
```

### Task 3: Rank replaces the assign meta-codes

**Files:**
- Modify: `nx_lib/security.py`
- Modify: `nx_lib/views/admin/users.py`
- Modify: `nx_lib/views/admin/permissions.py`
- Test: `tests/unit/test_security.py`, `tests/integration/test_admin_routes.py`

**Interfaces:**
- Produces: `nx_lib.security.assignable_profile_ids() -> set[int]` — AccessIDs the current session's user may assign (`Rank <= own rank`; empty set when the user has no profile).

- [ ] **Step 1: Write the failing unit test** in `tests/unit/test_security.py` — replace the two tests that reference `admin.assign.user.accessprofile.pdbsuser` (Grep `admin.assign` in the file) with:

```python
def test_assignable_profile_ids_queries_rank_ceiling(monkeypatch):
    from nx_lib import security

    cur = MagicMock()
    cur.fetchall.return_value = [(3,), (4,)]
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(security.engine_nexora_db, "raw_connection", lambda: conn)
    with patch("nx_lib.security.session", {"userid": 1019}):
        assert security.assignable_profile_ids() == {3, 4}
    sql = cur.execute.call_args[0][0]
    assert "Rank <=" in sql and cur.execute.call_args[0][1] == (1019,)


def test_assignable_profile_ids_empty_without_login():
    from nx_lib import security

    with patch("nx_lib.security.session", {}):
        assert security.assignable_profile_ids() == set()
```

- [ ] **Step 2: Run it** — `pytest tests/unit/test_security.py -q -k assignable` — Expected: FAIL `AttributeError: ... has no attribute 'assignable_profile_ids'`.

- [ ] **Step 3: Implement** in `nx_lib/security.py`, directly below `def load_permissions_for_user(user_id):`:

```python
def assignable_profile_ids() -> set[int]:
    """AccessIDs the current user may assign: every profile whose Rank is at or
    below the rank of the user's own profile (spec #238 D5). No login or no
    profile -> nothing. Replaces the admin.assign.user.accessprofile.* codes."""
    uid = session.get("userid")
    if not uid:
        return set()
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ap.AccessID FROM dbo.AccessProfile ap
            WHERE ap.Rank <= (SELECT ISNULL(MAX(me.Rank), -1)
                              FROM dbo.Users u JOIN dbo.AccessProfile me ON me.AccessID = u.accessid
                              WHERE u.userID = ?)
            """,
            (uid,),
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
```

- [ ] **Step 4: Replace the checks in `nx_lib/views/admin/users.py`** — in `admin_add_user` the block `if not has_permission(f"admin.assign.user.accessprofile.{str(accessprofile).lower()}"):` and in `admin_edit_user` the block `if accessprofile != current_profile and not has_permission(f"admin.assign.user.accessprofile....")`: resolve the profile id first (the existing `cursor.execute("select accessid from accessprofile where name = ?", accessprofile)` line moves above the check) and test `if accessid not in assignable_profile_ids():` → same 403 JSON as today. In `admin_user_detail` the comprehension `if has_permission(f'admin.assign.user.accessprofile.{str(ap["profile"]).lower()}')` becomes `if ap["accessid"] in assignable`, with `assignable = assignable_profile_ids()` computed once above the loop. Same edit in `nx_lib/views/admin/permissions.py::admin_access_control` (`for ap in all_ap: if has_permission(f'admin.assign...')`). Import `assignable_profile_ids` from `...security` (keep the re-export list in `nx_lib/views/admin/__init__.py` in sync if it names the imported symbols).

- [ ] **Step 5: Integration test** in `tests/integration/test_admin_routes.py`, section `/admin/sessions + /admin/users/*`:

```python
def test_add_user_refuses_a_higher_ranked_profile(user_client, admin_all_perms):
    # TestUser has Rank 10; TestAdmin is Rank 100 -> not assignable even with every code.
    resp = user_client.post(
        "/admin/users/add",
        json={"username": f"r{uuid.uuid4().hex[:6]}", "password": "Test1234!", "fullname": "Rank Test",
              "email": f"r{uuid.uuid4().hex[:6]}@test.local", "organization": "Test Organization",
              "accessprofile": "TestAdmin"},
    )
    assert resp.status_code == 403
```

(`admin_add_user` reads JSON and 400s when any of username/password/fullname/email/organization/accessprofile is missing, so the password must be present for the rank check to be reached. `Test Organization` is the seeded org display name.)

- [ ] **Step 6: Run** — `pytest tests/unit/test_security.py tests/integration/test_admin_routes.py -q -k "assignable or refuses_a_higher"` — Expected: PASS. Then `grep -rn "admin.assign" nx_lib templates tests` → only the migration and this plan/spec.

- [ ] **Step 7: Commit**

```bash
git add nx_lib/security.py nx_lib/views/admin/users.py nx_lib/views/admin/permissions.py tests/unit/test_security.py tests/integration/test_admin_routes.py
git commit -m "refactor(permissions): profile rank replaces the admin.assign.* meta-permissions"
```

### Task 4: Admin SQL without `Effect` on profile rows

**Files:**
- Modify: `nx_lib/views/admin/permissions.py`
- Modify: `templates/js/admin/_access_control_js.html` (minimal: send only Allow rows; the drawer dies in Phase 4)
- Test: `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Grep every profile-row `Effect`** — `grep -n "Effect" nx_lib/views/admin/permissions.py`. Expected hits by function: `api_admin_permission_holders` and `api_admin_user_effective_permissions` (`ap_perm.Effect AS ProfileEffect`), `get_profile_details` (the multi-line `SELECT PermissionID, Effect` / `FROM AccessProfilePermission` query), `save_access_profile` (`INSERT INTO AccessProfilePermission (AccessID, PermissionID, Effect)`), `get_user_overrides` (`SELECT PermissionID, Effect FROM AccessProfilePermission WHERE AccessID = ?`), `api_admin_permission_users` and `api_admin_user_all_permissions` (`app.Effect AS ProfileEffect`). `UserPermissionOverride.Effect` reads stay.

- [ ] **Step 2: Write the failing test** — in `test_admin_routes.py`:

```python
def test_save_access_profile_stores_only_allow_rows(admin_client, admin_all_perms, db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestNoPerm'")
    access_id = cur.fetchone()[0]
    cur.execute("SELECT PermissionID FROM dbo.Permission WHERE Code IN ('jd.view', 'api.docs.view') ORDER BY Code")
    api_docs, jd = [r[0] for r in cur.fetchall()]
    resp = admin_client.post("/api/admin/access_profile/save", json={
        "accessId": access_id, "name": "TestNoPerm", "description": "Test no-permission profile",
        "permissions": [{"PermissionID": jd, "Effect": "A"}, {"PermissionID": api_docs, "Effect": "D"}],
    })
    assert resp.status_code == 200
    cur.execute("SELECT PermissionID FROM dbo.AccessProfilePermission WHERE AccessID = ?", (access_id,))
    assert [r[0] for r in cur.fetchall()] == [jd]
    cur.execute("DELETE FROM dbo.AccessProfilePermission WHERE AccessID = ?", (access_id,)); db_conn.commit()
```

(`db_conn` fixture exists — see `test_admin_edit_organization_existing`. Add `jd.view`/`api.docs.view` to `sql/test/seed.sql` if missing.)

- [ ] **Step 3: Run** — Expected: FAIL (`Invalid column name 'Effect'`).

- [ ] **Step 4: Implement** — `save_access_profile`: `params = [(access_id, p["PermissionID"]) for p in permissions if p.get("Effect") == "A"]` and `INSERT INTO AccessProfilePermission (AccessID, PermissionID) VALUES (?, ?)`. `get_profile_details` and `get_user_overrides`: `SELECT PermissionID, 'A' AS Effect FROM AccessProfilePermission ...` (keeps the JSON shape the drawer and user detail read). The four `ap_perm.Effect` / `app.Effect` selects: `CASE WHEN ap_perm.PermissionID IS NULL THEN NULL ELSE 'A' END AS ProfileEffect` (same alias). In `_access_control_js.html` nothing changes functionally (Deny radios now save as none) — leave it; Phase 4 deletes the drawer.

- [ ] **Step 5: Run** — `pytest tests/integration/test_admin_routes.py -q` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/admin/permissions.py sql/test/seed.sql tests/integration/test_admin_routes.py
git commit -m "refactor(admin): profile grants are allow-only rows"
```

---

# PHASE 2 — One process scope code (migration 0087)

### Task 5: Migration 0087 — `process.<client>.<name>.view`

**Files:**
- Create: `sql/_migrations/NexoraDB/0087_process_scope.sql`

- [ ] **Step 1: Write the migration** (data-driven; derives pairs from whatever codes exist):

```sql
-- 0087_process_scope.sql (#238 phase 2)
-- One process.<client>.<name>.view code per (client, process) replaces the
-- three families workitems.filter.process.*, dashboard.filter.process.* and
-- reporting.scope.process.*. Every profile granted the three identically on
-- INT/PROD; the union is taken anyway. User overrides: D wins over A.
DECLARE @old TABLE (PermissionID INT PRIMARY KEY, Pair NVARCHAR(200));
INSERT INTO @old
SELECT PermissionID,
       CASE WHEN Code LIKE 'workitems.filter.process.%' THEN SUBSTRING(Code, LEN('workitems.filter.process.') + 1, 200)
            WHEN Code LIKE 'dashboard.filter.process.%' THEN SUBSTRING(Code, LEN('dashboard.filter.process.') + 1, 200)
            ELSE SUBSTRING(Code, LEN('reporting.scope.process.') + 1, 200) END
FROM dbo.Permission
WHERE Code LIKE 'workitems.filter.process.%' OR Code LIKE 'dashboard.filter.process.%'
   OR Code LIKE 'reporting.scope.process.%';

INSERT INTO dbo.Permission (Code, Description)
SELECT DISTINCT 'process.' + o.Pair + '.view', 'Process ' + o.Pair + ': workitems, dashboard and reports'
FROM @old o
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'process.' + o.Pair + '.view');

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT DISTINCT ap.AccessID, np.PermissionID
FROM dbo.AccessProfilePermission ap
JOIN @old o ON o.PermissionID = ap.PermissionID
JOIN dbo.Permission np ON np.Code = 'process.' + o.Pair + '.view'
WHERE NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x
                  WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID);

INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT uo.UserID, np.PermissionID, MAX(uo.Effect)   -- 'D' > 'A': a deny on any of the three wins
FROM dbo.UserPermissionOverride uo
JOIN @old o ON o.PermissionID = uo.PermissionID
JOIN dbo.Permission np ON np.Code = 'process.' + o.Pair + '.view'
WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride x
                  WHERE x.UserID = uo.UserID AND x.PermissionID = np.PermissionID)
GROUP BY uo.UserID, np.PermissionID;

DELETE FROM dbo.AccessProfilePermission WHERE PermissionID IN (SELECT PermissionID FROM @old);
DELETE FROM dbo.UserPermissionOverride  WHERE PermissionID IN (SELECT PermissionID FROM @old);
DELETE FROM dbo.Permission              WHERE PermissionID IN (SELECT PermissionID FROM @old);
GO
```

One `GO` at the end only: the table variable must live across the statements. Re-running is a no-op (the `@old` set is empty once the old codes are gone).

- [ ] **Step 2: Apply and prove** — `python scripts/db-migrate.py --env INT`; then query `select Code from dbo.Permission where Code like 'process.%' order by Code` → six codes; `select count(*) from dbo.Permission where Code like '%.filter.process.%' or Code like 'reporting.scope.process.%'` → 0; `select count(*) from dbo.Permission` → **111**; `select count(*) from dbo.AccessProfilePermission` → **289** (340 − 77 old-family grants + 26 new); `select ap.Name, count(*) from dbo.AccessProfilePermission x join dbo.Permission p on p.PermissionID=x.PermissionID join dbo.AccessProfile ap on ap.AccessID=x.AccessID where p.Code like 'process.%' group by ap.Name` → enterpriseAdmin 6, globalAdmin 5, nexoraSupervisor 5, nexoraUser 5, priveraUser 3, compassUser 1, elektromaterialUser 1. (INT held no user overrides on the old families, so the override step inserts nothing there.)

- [ ] **Step 3: Commit**

```bash
git add sql/_migrations/NexoraDB/0087_process_scope.sql
git commit -m "feat(db): one process.<client>.<name>.view scope code replaces three per-process families"
```

### Task 6: Shared `granted_processes()` and the consumers

**Files:**
- Modify: `nx_lib/process_helpers.py`
- Modify: `nx_lib/views/workitems.py`, `nx_lib/views/dashboard.py`, `nx_lib/views/reporting.py`, `nx_lib/reporting/runner.py`
- Modify: `nx_lib/views/admin/processes.py`
- Modify: `sql/test/seed.sql`
- Test: `tests/unit/test_process_helpers.py`, `tests/unit/test_reporting_runner.py`, `tests/unit/test_dashboard_stats.py`, `tests/integration/test_workitems_routes.py`, `tests/integration/test_dashboard_routes.py`, `tests/integration/test_reporting_routes.py`, `tests/integration/test_admin_routes.py`

**Interfaces:**
- Produces: `nx_lib.process_helpers.PROCESS_SCOPE_PREFIX = "process."`, `PROCESS_SCOPE_SUFFIX = ".view"`, `granted_processes(perms) -> list[str]` (sorted `"<client>.<name>"`), `process_scope_code(pair) -> str`; `prepare_process_selection_sql(process_name)` and `prepare_process_selection_lists(process_name)` **without** the `prefix` parameter (D7).

- [ ] **Step 1: Failing unit tests** — add to `tests/unit/test_process_helpers.py`:

```python
from nx_lib.process_helpers import granted_processes, process_scope_code


def test_granted_processes_parses_the_single_family():
    perms = ["process.privera.03_Invoice_New.view", "dashboard.view", "process.compass.01_Invoice_SAP.view",
             "processes.view", "process.privera.03_Invoice_New.edit"]
    assert granted_processes(perms) == ["compass.01_Invoice_SAP", "privera.03_Invoice_New"]


def test_process_scope_code_round_trips():
    assert process_scope_code("privera.03_Invoice_New") == "process.privera.03_Invoice_New.view"
```

Then rewrite the existing tests: every `prepare_process_selection_sql("stat.", ...)` / `prepare_process_selection_lists("workitems.filter.process.", ...)` call drops its first argument, and the session permission fixtures use `process.<client>.<name>.view` codes (e.g. `"stat.A.P1"` → `"process.A.P1.view"`).

- [ ] **Step 2: Run** — `pytest tests/unit/test_process_helpers.py -q` — Expected: FAIL (import error).

- [ ] **Step 3: Implement** in `nx_lib/process_helpers.py`:

```python
PROCESS_SCOPE_PREFIX = "process."
PROCESS_SCOPE_SUFFIX = ".view"


def process_scope_code(pair):
    """'<client>.<name>' -> 'process.<client>.<name>.view' (spec #238)."""
    return f"{PROCESS_SCOPE_PREFIX}{pair}{PROCESS_SCOPE_SUFFIX}"


def granted_processes(perms):
    """Sorted '<client>.<name>' pairs the permission list grants. Only the
    process.<client>.<name>.view family counts; anything else is ignored."""
    out = set()
    for perm in perms:
        if perm.startswith(PROCESS_SCOPE_PREFIX) and perm.endswith(PROCESS_SCOPE_SUFFIX):
            pair = perm[len(PROCESS_SCOPE_PREFIX) : -len(PROCESS_SCOPE_SUFFIX)]
            if pair.count(".") == 1:
                out.add(pair)
    return sorted(out)
```

`_selected_pairs(process_name)`: `if len(parts) == 2 and has_permission(process_scope_code(name))`. In `prepare_process_selection_sql(process_name)` and `prepare_process_selection_lists(process_name)` the `"all"` branch becomes `pairs = [tuple(p.split(".", 1)) for p in granted_processes(perms)]`. Update the module docstring (`Most permissions are scoped by ...`).

- [ ] **Step 4: Consumers** — Grep-driven, each a one-line change:
  - `nx_lib/views/workitems.py`: `prefix = "workitems.filter.process."` + the set comprehension → `allowed_processes = set(granted_processes(perms))`; `_ms02_target_processes()` body → `return granted_processes(session.get("permissions", []))`; `prepare_process_selection_lists("workitems.filter.process.", "all")` → `prepare_process_selection_lists("all")`. Import `granted_processes` next to `prepare_process_selection_lists`.
  - `nx_lib/views/dashboard.py`: every `prefix = "dashboard.filter.process."` block (7, Grep) → `granted_processes(perms)` / drop the first argument of `prepare_process_selection_*`.
  - `nx_lib/views/reporting.py`: delete `_SCOPE_PREFIX = "reporting.scope.process."`; `_allowed_processes()` body → `return granted_processes(session.get("permissions", []))` (D8 wrapper stays).
  - `nx_lib/reporting/runner.py`: delete `_SCOPE_PREFIX`; `_allowed_processes_from_perms(perms)` body → `return granted_processes(perms)`.
  - `nx_lib/views/admin/processes.py`: `_PROCESS_PERMISSION_PREFIX = "workitems.filter.process."` → delete; in `api_admin_process_source_add` the two `f"{_PROCESS_PERMISSION_PREFIX}..."` sites → `process_scope_code(_permission_reduction(process_name))`; description → `f"Process {reduction}: workitems, dashboard and reports"[:200]`. Fix the `_permission_reduction` docstring (`workitems.filter.process.<ProcessName>` → `process.<client>.<name>.view`) and the docstring on `api_admin_process_source_delete` (`The ``workitems.filter.process.<name>`` permission row is deliberately left`).
  - `sql/test/seed.sql`: replace any seeded `workitems.filter.process.*` / `dashboard.filter.process.*` / `reporting.scope.process.*` rows with `process.<pair>.view` (Grep; keep one row per pair).
  - Tests: `grep -rln "filter\.process\|scope\.process" tests` → replace codes with `process.<pair>.view` and drop the prefix argument where `prepare_process_selection_*` is called; `monkeypatch.setattr(wv, "_ms02_target_processes", ...)` sites in `test_workitems_routes.py` are unaffected (they patch the wrapper).

- [ ] **Step 5: Run** — `python scripts/test_db_reset.py && pytest tests/unit/test_process_helpers.py tests/unit/test_reporting_runner.py tests/unit/test_dashboard_stats.py tests/integration/test_workitems_routes.py tests/integration/test_dashboard_routes.py tests/integration/test_reporting_routes.py tests/integration/test_admin_routes.py -q` — Expected: PASS. Then `grep -rn "filter\.process\|scope\.process" nx_lib templates tests sql/test` → empty.

- [ ] **Step 6: Browser check** — `nx -r`, log in as `ben.streich`, open `/workitems`, `/dashboard`, `/reporting`: the process filter lists the same processes as before (ben.streich is enterpriseAdmin → 6). Screenshot `var/screenshots/238_phase2_workitems_filter.png`.

- [ ] **Step 7: Commit**

```bash
git add nx_lib/process_helpers.py nx_lib/views/workitems.py nx_lib/views/dashboard.py nx_lib/views/reporting.py nx_lib/reporting/runner.py nx_lib/views/admin/processes.py sql/test/seed.sql tests
git commit -m "refactor(permissions): read process scope from one process.<client>.<name>.view family"
```

---

# PHASE 3 — Rename the catalogue (migration 0088)

### Task 7: The sweep script (mapping = Appendix A)

**Files:**
- Create: `scripts/rename_permissions.py` (deleted again in Task 9)

**Interfaces:**
- Produces: `MAPPING: dict[str, tuple[str, str]]` old → (new, description); `python scripts/rename_permissions.py --emit-sql` prints migration 0088; `python scripts/rename_permissions.py --apply` rewrites literals in place and prints per-file counts.

- [ ] **Step 1: Write the script**

```python
"""One-off: rename permission codes per docs/superpowers/specs/2026-09-01-permission-structure-design.md
Appendix A. --emit-sql prints migration 0088; --apply rewrites literals in the tree. Deleted after use (#238)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWEEP_DIRS = ["nx_lib", "templates", "static/js", "tests", "sql/test", "docs/howto", "docs/design",
              "CLAUDE.md", "README.md", "CONTRIBUTING.md"]
SKIP_PARTS = {"__pycache__", "superpowers"}

# old -> (new, description). "=" as new keeps the code and rewrites the description.
MAPPING: dict[str, tuple[str, str]] = {
    # admin
    "admin.view": ("=", "View the admin area"),
    "admin.view.users": ("admin.users.view", "View users"),
    "admin.create.user": ("admin.users.add", "Add users"),
    "admin.edit.user": ("admin.users.edit", "Edit users"),
    "admin.delete.user": ("admin.users.delete", "Delete users"),
    "admin.edit.user.override": ("admin.users.overrides.edit", "Edit per-user permission overrides"),
    "admin.view.accessprofiles.useroverrides": ("admin.profiles.view", "View access profiles and the permissions grid"),
    "admin.edit.accessprofile": ("admin.profiles.edit", "Edit access profiles and their grants"),
    "admin.view.organizations": ("admin.organizations.view", "View organizations"),
    "admin.add.organization": ("admin.organizations.add", "Add organizations"),
    "admin.edit.organization": ("admin.organizations.edit", "Edit organizations"),
    "admin.delete.organization": ("admin.organizations.delete", "Delete organizations"),
    "admin.edit.organization.branding": ("admin.organizations.branding.edit", "Edit organization branding"),
    "admin.view.clients": ("admin.clients.view", "View the client registry"),
    "admin.edit.clients": ("admin.clients.edit", "Edit the client registry"),
    "admin.view.processes": ("admin.processes.view", "View process source mappings"),
    "admin.edit.processes": ("admin.processes.edit", "Edit process source mappings (high trust)"),
    "admin.view.active.sessions": ("admin.sessions.view", "View active sessions"),
    "admin.view.system.logs": ("admin.logs.view", "View system logs"),
    "admin.status.view": ("=", "View the system status page"),
    "admin.maintenance.view": ("=", "View the maintenance page"),
    "admin.maintenance.edit": ("=", "Edit and release maintenance periods"),
    "admin.maintenance.bypass": ("=", "Bypass the maintenance lockout"),
    "admin.restart": ("admin.server.restart", "Restart the local dev server (dev only)"),
    # workitems
    "workitems.view": ("=", "View the workitems page"),
    "workitems.details.view": ("=", "View workitem details"),
    "workitems.details.view.audit": ("workitems.details.audit.view", "View the workitem audit trail"),
    "workitems.details.view.fields": ("workitems.details.fields.view", "View extracted fields"),
    "workitems.details.view.images": ("workitems.details.images.view", "View document images"),
    "workitems.details.view.confidence": ("workitems.details.confidence.view", "View extraction confidence scores"),
    "workitems.details.view.source_location": ("workitems.details.sources.view", "View where values were found on the page (needs images.view)"),
    "workitems.filter.datetime": ("workitems.filter.date.view", "Filter by date"),
    "workitems.filter.status": ("workitems.filter.status.view", "Filter by status"),
    "workitems.filter.status.deleted": ("workitems.filter.deleted.view", "Filter for deleted workitems (internal; needs status.view)"),
    "workitems.filter.stage": ("workitems.filter.stage.view", "Filter by process stage"),
    "workitems.filter.workitemid": ("workitems.filter.id.view", "Search by workitem id"),
    "workitems.filter.documentfields": ("workitems.filter.docfields.view", "Filter by document fields"),
    "workitems.filter.documentfields.sensitive": ("workitems.filter.docfields.sensitive.view", "Filter by sensitive document fields (needs docfields.view)"),
    "workitems.import.workitem": ("workitems.import.run", "Import a workitem"),
    "workitems.import.preparedaudit": ("workitems.prepared.view", "View the prepared-documents import and audit page"),
    # dashboard, api, jd
    "dashboard.view": ("=", "View the dashboard"),
    "api.docs.view": ("=", "View the in-app API documentation"),
    "jd.view": ("=", "View the JD page"),
    # reporting
    "reporting.view": ("=", "View the reporting page"),
    "reporting.export": ("=", "Export reports to Excel"),
    "reporting.schedule": ("=", "Schedule reports for email delivery"),
    "reporting.sql.run": ("=", "Run live read-only SQL in the sandbox"),
    "reporting.sql.target.octopus": ("reporting.sql.target.octopus.use", "Target the Octo runtime DB in the sandbox"),
    "reporting.ai.use": ("=", "Use the AI assistant"),
    "reporting.ai.sql": ("reporting.ai.sql.use", "Receive AI-drafted SQL (needs sql.run)"),
    "reporting.ai.explain_data": ("reporting.ai.explain.use", "Let the AI run queries and explain results (data egress; needs sql.run)"),
    "reporting.admin.sources": ("reporting.sources.manage", "Manage the data-source registry"),
    "reporting.sources.schema": ("reporting.sources.schema.view", "Browse tables and columns of a source"),
    "reporting.semantic.admin": ("reporting.metrics.manage", "Manage the canonical metrics registry"),
    "reporting.source.docprocessing": ("reporting.source.docprocessing.use", "Use the Document Processing source"),
    "reporting.source.workitems": ("reporting.source.workitems.use", "Use the Workitems (Octo) source"),
    "reporting.source.generali.pdqm": ("reporting.source.generali_pdqm.use", "Use the Generali PDQM source"),
    # tenant.ms02 (already in grammar; description only)
    "tenant.ms02.view": ("=", "View the MS02 pilot tenant pages"),
    "tenant.ms02.edit": ("=", "Edit the MS02 pilot tenant data"),
    # generali -> tenant.generali
    "generali.dashboard.view": ("tenant.generali.view", "View the Generali dashboard"),
    "generali.documentlist.view": ("tenant.generali.documents.view", "View the Generali document list"),
    "generali.importstatus.view": ("tenant.generali.importstatus.view", "View the Generali import status"),
    "generali.additionalservices.view": ("tenant.generali.attendance.view", "View the attendance page (Zusätzliche Leistungen)"),
}

_SCOPE_TXT = {".org": " for the own organization", ".all": " for every organization", ".pastdeadline": " past the deadline"}
_GENERALI = {
    "attendance": ("attendance records", ("add", "edit", "delete"), True),
    "baseservices": ("base service records", ("add", "edit", "delete"), True),
    "pdqm": ("PDQM records", ("add", "edit", "delete"), True),
    "projectmanagement": ("project management records", ("add", "edit", "delete"), True),
    "reporting": ("reporting records", ("add", "edit", "delete"), False),
}
for _obj, (_noun, _actions, _add_scoped) in _GENERALI.items():
    if _obj != "attendance":  # attendance.view comes from additionalservices.view above
        MAPPING[f"generali.{_obj}.view"] = (f"tenant.generali.{_obj}.view", f"View the Generali {_noun} page")
    MAPPING[f"generali.{_obj}.add"] = (f"tenant.generali.{_obj}.add", f"Add own {_noun}")
    MAPPING[f"generali.{_obj}.add.bypass.deadline"] = (f"tenant.generali.{_obj}.add.pastdeadline", f"Add {_noun} past the deadline")
    for _action in _actions:
        for _old, _new in ((".organizational", ".org"), (".transorganizational", ".all")):
            if _action == "add" and not _add_scoped:
                continue
            MAPPING[f"generali.{_obj}.{_action}{_old}"] = (
                f"tenant.generali.{_obj}.{_action}{_new}", f"{_action.capitalize()} {_noun}{_SCOPE_TXT[_new]}")


def resolved() -> list[tuple[str, str, str]]:
    return [(old, old if new == "=" else new, desc) for old, (new, desc) in MAPPING.items()]


def emit_sql() -> str:
    rows = ",\n".join(f"    (N'{o}', N'{n}', N'{d.replace(chr(39), chr(39) * 2)}')" for o, n, d in resolved())
    return f"""-- 0088_permission_rename.sql (#238 phase 3) -- generated by scripts/rename_permissions.py --emit-sql
-- Renames codes to <area>.<object>.<action>[.<scope>] and rewrites descriptions.
-- Grants ride on PermissionID. Data-driven: codes absent on this server are skipped.
DECLARE @map TABLE (OldCode SYSNAME PRIMARY KEY, NewCode SYSNAME, NewDescription NVARCHAR(200));
INSERT INTO @map VALUES
{rows};
IF EXISTS (SELECT 1 FROM @map m JOIN dbo.Permission p ON p.Code = m.NewCode
           JOIN dbo.Permission o ON o.Code = m.OldCode WHERE m.OldCode <> m.NewCode AND o.PermissionID <> p.PermissionID)
    THROW 50088, 'permission rename target already exists with a different PermissionID', 1;
UPDATE p SET p.Code = m.NewCode, p.Description = m.NewDescription
FROM dbo.Permission p JOIN @map m ON m.OldCode = p.Code;
UPDATE r SET r.Permission = m.NewCode
FROM dbo.ReportingSources r JOIN @map m ON m.OldCode = r.Permission;
INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.permissions.edit', 'Edit the permission catalogue (descriptions, add, delete)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'admin.permissions.edit');
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, np.PermissionID
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission hp ON hp.PermissionID = ap.PermissionID AND hp.Code = 'admin.profiles.edit'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'admin.permissions.edit'
  AND NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID);
GO
"""


def apply() -> None:
    pairs = sorted(((o, n) for o, n, _ in resolved() if o != n), key=lambda p: -len(p[0]))
    patterns = [(re.compile(rf"(?<![A-Za-z0-9_.]){re.escape(o)}(?![A-Za-z0-9_.])"), n) for o, n in pairs]
    for entry in SWEEP_DIRS:
        base = ROOT / entry
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file() and not (SKIP_PARTS & set(p.parts))]
        for f in files:
            if f.suffix not in {".py", ".html", ".js", ".sql", ".md"}:
                continue
            text = f.read_text(encoding="utf-8")
            new, hits = text, 0
            for rx, n in patterns:
                new, k = rx.subn(n, new)
                hits += k
            if hits:
                f.write_bytes(new.encode("utf-8"))  # binary write keeps LF/CRLF as-is
                print(f"{hits:4d}  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    if "--emit-sql" in sys.argv:
        sys.stdout.write(emit_sql())
    elif "--apply" in sys.argv:
        apply()
    else:
        sys.exit("usage: rename_permissions.py --emit-sql | --apply")
```

- [ ] **Step 2: Sanity-check the mapping** — run:

```
python - <<'EOF'
import collections, importlib.util as u
s = u.spec_from_file_location("r", "scripts/rename_permissions.py"); m = u.module_from_spec(s); s.loader.exec_module(m)
r = m.resolved()
print(len(r))                                                          # 105
print([k for k, v in collections.Counter(n for _, n, _ in r).items() if v > 1])   # []  (no two old codes share a new one)
changing_old = {o for o, n, _ in r if o != n}
print(sorted({n for o, n, _ in r} & changing_old))                     # []  (no new code equals another old code -> no rename cycles)
EOF
```

Expected `105` = the 111 codes INT holds after Phase 2 minus the 6 `process.*` codes (which 0087 already wrote in the new grammar). Then prove coverage against INT: `ENVIRONMENT=INT python -c "from nx_lib.db import engine_nexora_db as e; from sqlalchemy import text; import importlib.util as u; s=u.spec_from_file_location('r','scripts/rename_permissions.py'); m=u.module_from_spec(s); s.loader.exec_module(m); c=e.connect(); db={r[0] for r in c.execute(text(\"select Code from dbo.Permission where Code not like 'process.%'\"))}; print(sorted(db - set(m.MAPPING)), sorted(set(m.MAPPING) - db))"` → `[] []` (every live code is mapped; nothing mapped is missing).

- [ ] **Step 3: Emit the migration** — `python scripts/rename_permissions.py --emit-sql > sql/_migrations/NexoraDB/0088_permission_rename.sql` (ensure LF endings; `git diff --stat` shows one file). Do **not** apply yet — Task 8 applies it together with the code sweep so the running INT server and the code base flip in the same commit.

- [ ] **Step 4: Commit the script and migration**

```bash
git add scripts/rename_permissions.py sql/_migrations/NexoraDB/0088_permission_rename.sql
SQL_SYNC_SKIP=1 git commit -m "feat(db): rename the permission catalogue to <area>.<object>.<action> (migration 0088)"
```

(`SQL_SYNC_SKIP=1` here because the hook would apply 0088 to INT while the code still reads old codes; Task 8 applies it explicitly.)

### Task 8: Sweep literals, fix the structural sites, apply 0088

**Files:**
- Modify: everything `--apply` touches (expect ~60 files), plus by hand: `nx_lib/views/generali/_crud.py`, `nx_lib/views/generali/_scope.py`, `nx_lib/views/generali/attendance.py`, `nx_lib/views/generali/baseservices.py`, `nx_lib/views/generali/pdqm.py`, `nx_lib/views/generali/projectmanagement.py`, `nx_lib/views/generali/reporting.py`, `nx_lib/security.py`, `templates/js/admin/_access_control_js.html`, `templates/admin/user_detail.html`

- [ ] **Step 1: Apply the sweep** — `python scripts/rename_permissions.py --apply | sort -k2` and skim the file list. `git diff --stat | tail -1`.

- [ ] **Step 2: Structural sites the regex cannot see** (f-strings and prefixes):
  - `nx_lib/views/generali/*.py` descriptors: `perm_prefix="generali.<slug>"` → `perm_prefix="tenant.generali.<slug>"` (five files). Delete the `view_perm=` line in each and the field `view_perm: str  # view permission (differs from perm_prefix for attendance)` in `CrudTable`; every use of `d.view_perm` in `_crud.py` becomes `f"{d.perm_prefix}.view"` (Grep `view_perm`).
  - `nx_lib/views/generali/_crud.py` and `_scope.py`: `sed -i 's/\.transorganizational"/.all"/g; s/\.organizational"/.org"/g; s/\.add\.bypass\.deadline"/.add.pastdeadline"/g'` on both files; then Grep `organizational\|bypass.deadline` in `nx_lib/views/generali` → only comments/log labels may remain; fix those by hand.
  - `nx_lib/views/generali/reporting.py` (hand-written views): Grep `"generali\.` → any literal the sweep missed (there should be none; f-strings get the same sed).
  - `nx_lib/security.py::page_visibility()`: values were swept; re-read once — `generaliAdditionalServicesPerm` now reads `tenant.generali.attendance.view` (correct: same page).
  - `nx_lib/whats_new.py`: swept `perm` values; verify `tests/unit/test_whats_new.py` regex `[a-z0-9_.]+` still holds (it does — no capitals in `reporting.*`).
  - `templates/js/admin/_access_control_js.html::groupOf` (`p[0] === 'generali' ? p.slice(0,2).join('.') : p[0]`) → `(p[0] === 'tenant' || p[0] === 'process') ? p.slice(0,2).join('.') : p[0]`. Same rule wherever `templates/admin/user_detail.html` groups (`{% set group = parts[0] %}` → `{% set group = parts[0] ~ ('.' ~ parts[1] if parts[0] in ('tenant', 'process') else '') %}`). Both die/shrink in Phase 4; this keeps them coherent meanwhile.
  - `tests/unit/test_generali_scope.py`: `gv._generali_scope_where("generali.reporting", ...)` → `"tenant.generali.reporting"`; codes in `perms` sets follow the mapping (`.edit.transorganizational` → `.edit.all`).

- [ ] **Step 3: Apply 0088 to INT and reset TEST** — `python scripts/db-migrate.py --env INT && python scripts/test_db_reset.py`. Prove: `select count(*) from dbo.Permission` → **112**; `select Code from dbo.Permission where Code like 'generali.%' or Code like '%.organizational' or Code like 'admin.view.%'` → empty; `select Permission from dbo.ReportingSources` → all end in `.use`.

- [ ] **Step 4: Full fast-tier suite** — `pytest tests/unit tests/integration -q -x` — Expected: PASS. Typical stragglers: a code built from an f-string prefix (Step 2 covers the known ones), a test that asserts an old code in a rendered page, a `monkeypatch.setattr(..., lambda code: code in {...})` set with old codes. The sweep regex is quote-agnostic, so the 12 Jinja `has_permission('...')` sites in `templates/` are already renamed.

- [ ] **Step 5: Zero-leftover proof** — `grep -rn "\.transorganizational\|\.organizational\|bypass\.deadline\|admin\.view\.\|admin\.edit\.\|admin\.create\.\|admin\.delete\.\|admin\.add\.\|details\.view\.\|filter\.documentfields\|filter\.datetime\|filter\.workitemid\|reporting\.admin\.\|reporting\.semantic\|explain_data\|\"generali\." nx_lib templates static/js tests sql/test docs/howto docs/design` → only lines that quote the *old* name for history (CHANGELOG-style prose). Fix the rest.

- [ ] **Step 6: Commit**

```bash
git add -A nx_lib templates static/js tests sql/test docs/howto docs/design CLAUDE.md README.md CONTRIBUTING.md
git commit -m "refactor(permissions): rename every code to <area>.<object>.<action>[.<scope>]"
```

### Task 9: Convention test, doctor check, delete the script

**Files:**
- Create: `tests/unit/test_permission_codes.py`
- Modify: `nx_lib/cli_doctor.py`
- Delete: `scripts/rename_permissions.py`

**Interfaces:**
- Produces: `PERMISSION_CODE_RE` (module constant in `nx_lib/security.py`) used by the test and the doctor.

- [ ] **Step 1: Write the failing test**

```python
"""Permission codes follow <area>[.<object>[.<sub>]].<action>[.<scope>] (spec #238)."""
import re
from pathlib import Path

from nx_lib.security import PERMISSION_CODE_RE

ROOT = Path(__file__).resolve().parents[2]
_LITERAL = re.compile(r"""(?:require_permission|has_permission|require_any_permission)\(\s*['"]([^'"]+)['"]""")
_SEED = re.compile(r"^\s*\('([a-zA-Z0-9_.]+)',\s*'", re.M)
_MIGRATION = re.compile(r"\(N'[^']+',\s*N'([^']+)',", re.M)


def _referenced_codes():
    out = set()
    for folder, suffix in (("nx_lib", "*.py"), ("templates", "*.html")):
        for f in (ROOT / folder).rglob(suffix):
            out.update(_LITERAL.findall(f.read_text(encoding="utf-8", errors="ignore")))
    return out


def test_referenced_codes_match_the_grammar():
    bad = sorted(c for c in _referenced_codes() if not PERMISSION_CODE_RE.fullmatch(c))
    assert bad == [], bad


def test_seed_and_rename_migration_match_the_grammar():
    seed = _SEED.findall((ROOT / "sql/test/seed.sql").read_text(encoding="utf-8"))
    mig = _MIGRATION.findall((ROOT / "sql/_migrations/NexoraDB/0088_permission_rename.sql").read_text(encoding="utf-8"))
    assert seed and mig
    bad = sorted(c for c in set(seed) | set(mig) if not PERMISSION_CODE_RE.fullmatch(c))
    assert bad == [], bad
```

- [ ] **Step 2: Run** — Expected: FAIL (`ImportError: PERMISSION_CODE_RE`).

- [ ] **Step 3: Implement** in `nx_lib/security.py` (module level, above `load_permissions_for_user`):

```python
# <area>[.<object>[.<sub>]].<action>[.<scope>] -- spec #238. External identifiers
# (process names, reporting source codes) may carry capitals and underscores.
PERMISSION_CODE_RE = re.compile(
    r"^[a-z]+(\.[a-z]+)?(\.[A-Za-z0-9_]+)*"
    r"\.(view|add|edit|delete|use|run|export|schedule|manage|bypass|import|restart)"
    r"(\.(org|all|pastdeadline))?$"
)
```

(`import re` at the top.) The seed regex in the test tolerates the test-only `admin.users.manage`, which matches the grammar.

- [ ] **Step 4: Doctor check** — in `nx_lib/cli_doctor.py` add `_check_permissions() -> list[CheckResult]` next to `_check_migrations`: load the referenced literal set (same regex as the test, import-free copy), query `SELECT Code FROM dbo.Permission` and `SELECT Name FROM dbo.AccessProfile WHERE Rank = 0` on `engine_nexora_db`; `warn` "N referenced codes missing in DB: a, b, c" (dynamic families `process.*` and `reporting.source.*` excluded from the comparison) and `warn` "profiles with Rank 0: ..." ; `ok` otherwise; `fail` only when the DB is unreachable is *not* wanted — return a single `warn` "skipped (DB down)". Register it in the `sections` list in the runner (`("Migrations", _check_migrations()),` → add `("Permissions", _check_permissions()),` after it). Run `nx --doctor` once; expect `ok`.

- [ ] **Step 5: Delete the script** — `git rm scripts/rename_permissions.py` (D9; the mapping lives in 0088 and the spec).

- [ ] **Step 6: Run** — `pytest tests/unit/test_permission_codes.py tests/unit/test_security.py -q` — Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_permission_codes.py nx_lib/security.py nx_lib/cli_doctor.py
git commit -m "test(permissions): enforce the code grammar; doctor reports codes missing in the DB"
```

### Task 10: Docs for Phase 1–3

**Files:**
- Create: `docs/design/permissions.md`
- Modify: `CLAUDE.md`, `docs/design/architecture-conventions.md`, `docs/howto/white-label.md`, `docs/howto/reporting.md`, `docs/design/ms02-multisource.md` (only if it names codes), `CHANGELOG.md`

- [ ] **Step 1: Write `docs/design/permissions.md`** with these sections, prose from the spec: *Grammar* (regex + action/scope vocabulary + the `<area>.view` rule), *Resolution order* (user D, user A, profile row, deny), *Rank* (D5, the seed table), *Dynamic families* (process, reporting.source, tenant), *Adding a code* (migration `WHERE NOT EXISTS`, granted to nobody, grant at `/admin/permissions`), *Where codes are stored* (Permission, ReportingSources.Permission, whats_new.py, sql/test/seed.sql), *Tests* (`test_permission_codes.py`, doctor), and a pointer to the spec's Appendix A for the 2026-09 rename.
- [ ] **Step 2: Pointers** — `CLAUDE.md` "Permissions" bullet: add "Grammar, rank, dynamic families: `docs/design/permissions.md`". `docs/design/architecture-conventions.md` Permissions bullet: replace the `admin.view`, `generali.pdqm.view` examples with `admin.users.edit`, `tenant.generali.pdqm.view`, mention Rank and the allow-only profile table, link the new doc. `docs/howto/white-label.md`: `workitems.filter.process.<ProcessName>` → `process.<client>.<name>.view` (three mentions, Grep), `/admin/access-control` → `/admin/access_control`. `docs/howto/reporting.md`: the sweep renamed the codes; re-read the permission table once for prose that describes old shapes. `docs/superpowers/specs/2026-08-31-tenant-platform-design.md`, section "Permissions & navigation": add one line that `tenant.generali.*` codes already exist since #238 (the sweep skips `docs/superpowers/`, so this is by hand).
- [ ] **Step 3: CHANGELOG `[Unreleased]`** — *Changed*: "Permission codes follow one grammar `<area>.<object>.<action>[.<scope>]`; every code renamed (mapping in `docs/superpowers/specs/2026-09-01-permission-structure-design.md`, Appendix A); Generali codes live under `tenant.generali.*`." *Removed*: "Profile-level DENY (446 empty rows), the ten `admin.assign.user.accessprofile.*` codes, 12 orphan codes (`invoices.*`, `kundenmagazin.*`, …), the three per-process families." *Added*: "`AccessProfile.Rank` governs which profiles an admin may assign; one `process.<client>.<name>.view` scope code per process; `admin.permissions.edit`; `nx --doctor` Permissions section." Note the deploy blip (D6) under a **Deploy notes** line.
- [ ] **Step 4: Commit**

```bash
git add docs/design/permissions.md CLAUDE.md docs/design/architecture-conventions.md docs/howto/white-label.md docs/howto/reporting.md CHANGELOG.md
git commit -m "docs(permissions): grammar, rank and dynamic families; changelog for the #238 rename"
```

---

# PHASE 4 — The permissions grid

### Task 11: `group_permissions()` helper

**Files:**
- Modify: `nx_lib/security.py`
- Test: `tests/unit/test_security.py`

**Interfaces:**
- Produces: `group_permissions(rows: Iterable[Mapping]) -> list[dict]` where each row has `PermissionID`, `Code`, `Description`. Returns `[{"area": "admin", "objects": [{"key": "admin", "label": "", "perms": [row, ...]}, {"key": "admin.users", "label": "users", "perms": [...]}]}]`. Area = first segment (`tenant.<code>` is a two-segment area); object = the first segment after the area (`filter`, `users`, `pdqm`, a process's client); deeper segments stay in the row. Areas sorted alpha, the area-level object first, then objects alpha; perms sorted by action order `view add edit delete use run import export schedule manage bypass restart`, then scope order `"" org all pastdeadline`, then code. Every returned perm dict is a **copy** of the input row plus `"gate"`: the `.view` code the UI greys it behind — the object's `.view` if present, else the area's `.view`, else `None`. Consumed by Task 12 (grid) and Task 14 (user detail).

- [ ] **Step 1: Failing test**

```python
def test_group_permissions_builds_area_object_tree_with_gates():
    from nx_lib.security import group_permissions

    rows = [
        {"PermissionID": 1, "Code": "admin.users.edit", "Description": ""},
        {"PermissionID": 2, "Code": "admin.view", "Description": ""},
        {"PermissionID": 3, "Code": "admin.users.view", "Description": ""},
        {"PermissionID": 4, "Code": "tenant.generali.pdqm.edit.all", "Description": ""},
        {"PermissionID": 5, "Code": "tenant.generali.pdqm.edit.org", "Description": ""},
        {"PermissionID": 6, "Code": "process.privera.03_Invoice_New.view", "Description": ""},
        {"PermissionID": 7, "Code": "tenant.generali.view", "Description": ""},
    ]
    tree = group_permissions(rows)
    assert [a["area"] for a in tree] == ["admin", "process", "tenant.generali"]
    admin = tree[0]["objects"]
    assert [o["key"] for o in admin] == ["admin", "admin.users"]
    assert [p["Code"] for p in admin[1]["perms"]] == ["admin.users.view", "admin.users.edit"]
    assert [p["gate"] for p in admin[1]["perms"]] == ["admin.view", "admin.users.view"]
    assert admin[0]["perms"][0]["gate"] is None
    proc = tree[1]["objects"][0]
    assert proc["label"] == "privera" and proc["perms"][0]["gate"] is None
    pdqm = tree[2]["objects"][1]
    assert pdqm["label"] == "pdqm"
    assert [p["Code"] for p in pdqm["perms"]] == ["tenant.generali.pdqm.edit.org", "tenant.generali.pdqm.edit.all"]
    assert pdqm["perms"][0]["gate"] == "tenant.generali.view"
    assert "gate" not in rows[0]  # input rows untouched
```

- [ ] **Step 2: Run** — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** in `nx_lib/security.py` below `PERMISSION_CODE_RE`:

```python
_ACTIONS = ("view", "add", "edit", "delete", "use", "run", "import", "export", "schedule", "manage", "bypass", "restart")
_SCOPES = ("", "org", "all", "pastdeadline")
_TWO_SEGMENT_AREAS = ("tenant",)


def _split_code(code):
    """-> (area, object_key, action, scope) per the #238 grammar. The object is
    the first segment after the area; area-level codes (admin.view,
    reporting.export) have object == area."""
    parts = code.split(".")
    n_area = 2 if parts[0] in _TWO_SEGMENT_AREAS and len(parts) > 2 else 1
    area = ".".join(parts[:n_area])
    tail = parts[n_area:]
    scope = tail.pop() if tail and tail[-1] in _SCOPES[1:] else ""
    action = tail.pop() if tail and tail[-1] in _ACTIONS else ""
    obj = f"{area}.{tail[0]}" if tail else area
    return area, obj, action, scope


def group_permissions(rows):
    """Area -> object -> permissions tree for the grid and the user-detail page.
    Each returned permission is a copy of its row plus ``gate``: the .view code
    (the object's, else the area's) the UI greys it behind, or None."""
    codes = {row["Code"] for row in rows}
    areas = {}
    for row in rows:
        area, obj, action, scope = _split_code(row["Code"])
        gate = next((c for c in (f"{obj}.view", f"{area}.view") if c != row["Code"] and c in codes), None)
        areas.setdefault(area, {}).setdefault(obj, []).append(({**row, "gate": gate}, action, scope))
    tree = []
    for area in sorted(areas):
        objects = []
        for obj in sorted(areas[area], key=lambda k: (k != area, k)):
            perms = sorted(
                areas[area][obj],
                key=lambda t: (_ACTIONS.index(t[1]) if t[1] in _ACTIONS else 99, _SCOPES.index(t[2]), t[0]["Code"]),
            )
            objects.append({"key": obj, "label": obj[len(area) + 1 :], "perms": [t[0] for t in perms]})
        tree.append({"area": area, "objects": objects})
    return tree
```

- [ ] **Step 4: Run** — `pytest tests/unit/test_security.py -q -k group_permissions` — Expected: PASS.
- [ ] **Step 5: Commit** — `git add nx_lib/security.py tests/unit/test_security.py && git commit -m "feat(permissions): group_permissions() builds the area/object tree"`

### Task 12: `/admin/permissions` page + grants API

**Files:**
- Modify: `nx_lib/views/admin/permissions.py`, `nx_lib/views/admin/__init__.py`
- Create: `templates/admin/permissions.html`, `templates/js/admin/_permissions_js.html`, `static/js/admin_permissions.js`
- Modify: `templates/_header.html`, `templates/admin/admin_overview.html`, `nx_lib/whats_new.py`
- Delete: `templates/admin/permission_matrix.html`, `templates/js/admin/_permission_matrix_js.html`
- Test: `tests/integration/test_admin_routes.py`

**Interfaces:**
- Produces: route `GET /admin/permissions` (endpoint `admin_permissions`, perm `admin.profiles.view`); `POST /api/admin/profiles/grants` (endpoint `api_admin_profile_grants_save`, perm `admin.profiles.edit`) with body `{"changes": [{"accessId": int, "permissionId": int, "granted": bool}]}` → `{"success": true, "applied": int}`.
- Consumes: `group_permissions` (Task 11), existing `api_admin_permission_holders` (`/api/admin/permissions/<id>/holders`), existing catalogue APIs `/api/admin/permissions/add|edit/<id>|delete/<id>`.

- [ ] **Step 1: Failing integration tests**

```python
def test_admin_permissions_page_gated(noperm_client):
    assert noperm_client.get("/admin/permissions").status_code == 403


def test_admin_permissions_page_renders_grid(admin_client, admin_all_perms):
    resp = admin_client.get("/admin/permissions")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-testid="admin-perms-grid"' in html and "TestNoPerm" in html and "jd.view" in html


def test_profile_grants_save_round_trip(admin_client, admin_all_perms, db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestNoPerm'"); access_id = cur.fetchone()[0]
    cur.execute("SELECT PermissionID FROM dbo.Permission WHERE Code = 'jd.view'"); perm_id = cur.fetchone()[0]
    body = {"changes": [{"accessId": access_id, "permissionId": perm_id, "granted": True}]}
    assert admin_client.post("/api/admin/profiles/grants", json=body).get_json() == {"success": True, "applied": 1}
    cur.execute("SELECT COUNT(*) FROM dbo.AccessProfilePermission WHERE AccessID=? AND PermissionID=?", (access_id, perm_id))
    assert cur.fetchone()[0] == 1
    body["changes"][0]["granted"] = False
    assert admin_client.post("/api/admin/profiles/grants", json=body).get_json()["applied"] == 1
    cur.execute("SELECT COUNT(*) FROM dbo.AccessProfilePermission WHERE AccessID=? AND PermissionID=?", (access_id, perm_id))
    assert cur.fetchone()[0] == 0


def test_profile_grants_save_rejects_bad_body(admin_client, admin_all_perms):
    assert admin_client.post("/api/admin/profiles/grants", json={"changes": "nope"}).status_code == 400
```

Delete `test_admin_permission_matrix_view_gated` and `test_admin_permission_matrix_view_with_perms`.

- [ ] **Step 2: Run** — Expected: FAIL (404).

- [ ] **Step 3: Routes** in `nx_lib/views/admin/permissions.py` — replace `admin_permission_matrix` with:

```python
@require_permission("admin.profiles.view")
def admin_permissions_page():
    """Permissions x profiles grid (#238): rows grouped area -> object, one
    checkbox per (profile, permission). Saving posts only changed cells."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT PermissionID, Code, Description FROM dbo.Permission ORDER BY Code")
        perms = [dict(zip([c[0] for c in cur.description], r, strict=False)) for r in cur.fetchall()]
        cur.execute(
            """SELECT ap.AccessID, ap.Name, ap.Rank, COUNT(u.userID) AS UserCount
               FROM dbo.AccessProfile ap LEFT JOIN dbo.Users u ON u.accessid = ap.AccessID
               GROUP BY ap.AccessID, ap.Name, ap.Rank ORDER BY ap.Rank DESC, ap.Name"""
        )
        profiles = [dict(zip([c[0] for c in cur.description], r, strict=False)) for r in cur.fetchall()]
        cur.execute("SELECT AccessID, PermissionID FROM dbo.AccessProfilePermission")
        grants = [[r[0], r[1]] for r in cur.fetchall()]
    finally:
        conn.close()
    return render_template(
        "admin/permissions.html",
        groups=group_permissions(perms),
        profiles=profiles,
        grants=grants,
        can_edit=has_permission("admin.profiles.edit"),
        can_edit_catalog=has_permission("admin.permissions.edit"),
        page_visibility=page_visibility(),
    )


@require_permission("admin.profiles.edit")
def api_admin_profile_grants_save():
    data = request.get_json(silent=True) or {}
    changes = data.get("changes")
    if not isinstance(changes, list) or not all(
        isinstance(c, dict) and isinstance(c.get("accessId"), int) and isinstance(c.get("permissionId"), int)
        and isinstance(c.get("granted"), bool) for c in changes
    ):
        return jsonify({"success": False, "message": _("Invalid payload")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        for c in changes:
            if c["granted"]:
                cur.execute(
                    "INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID) SELECT ?, ? "
                    "WHERE NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission WHERE AccessID = ? AND PermissionID = ?)",
                    (c["accessId"], c["permissionId"], c["accessId"], c["permissionId"]),
                )
            else:
                cur.execute(
                    "DELETE FROM dbo.AccessProfilePermission WHERE AccessID = ? AND PermissionID = ?",
                    (c["accessId"], c["permissionId"]),
                )
        conn.commit()
    finally:
        conn.close()
    user_cache.clear()  # /api/admin/* is outside the hooks' /admin prefix
    session["permissions"] = load_permissions_for_user(session["userid"])
    return jsonify({"success": True, "applied": len(changes)})
```

Imports: `from ... import user_cache`, `from ...security import group_permissions` (extend the existing `from ...security import (...)` block). In `register_routes`: replace the `/admin/permission_matrix` rule with `app.add_url_rule("/admin/permissions", endpoint="admin_permissions", view_func=admin_permissions_page)` and add `app.add_url_rule("/api/admin/profiles/grants", endpoint="api_admin_profile_grants_save", view_func=api_admin_profile_grants_save, methods=["POST"])`. Re-gate `api_admin_permission_add`, `api_admin_permission_edit`, `api_admin_permission_delete` to `@require_permission("admin.permissions.edit")`. Update the import + `__all__` entries in `nx_lib/views/admin/__init__.py` (`admin_permission_matrix` → `admin_permissions_page`, add `api_admin_profile_grants_save`).

- [ ] **Step 4: Template** `templates/admin/permissions.html` — copy the full-page shell of `templates/admin/permission_matrix.html` (it is a standalone page, not an `extends`: `<head>` with `_theme_prepaint.html`, `nexora-ui.css`, `admin.css`; `{% set active_page = 'admin_permissions' %}`; `{% include '_header.html' %}`; `{% import 'admin/_admin_helpers.html' as a %}`; `{{ a.page_header(title=_('Permissions'), subtitle=_('Which access profile holds which permission. Tick, save, done.'), back_url=url_for('admin_access_control'), icon='fa-table-cells') }}`) and this body inside `<main class="nx-main">`:

```html
<div class="nx-card" style="padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
  <input id="permsFilter" class="nx-input" style="max-width:360px" placeholder="{{ _('Filter by code or description…') }}" data-testid="admin-perms-filter">
  <span class="nx-meta" id="permsDirty" data-testid="admin-perms-dirty"></span>
  {% if can_edit %}<button id="permsSave" class="nx-btn nx-btn--primary" disabled data-testid="admin-perms-save">{{ _('Save changes') }}</button>{% endif %}
  {% if can_edit_catalog %}<button id="permsAdd" class="nx-btn nx-btn--secondary" data-testid="admin-perms-add">{{ _('Add permission') }}</button>{% endif %}
</div>
<div class="nx-table-wrap" style="overflow:auto;max-height:calc(100vh - 220px)">
  <table class="nx-table" id="permsGrid" data-testid="admin-perms-grid">
    <thead style="position:sticky;top:0;z-index:2">
      <tr><th>{{ _('Permission') }}</th>
      {% for p in profiles %}<th class="align-center" title="{{ p.UserCount }} {{ _('user(s)') }}"><div class="nx-mono">{{ p.Name }}</div><div class="nx-meta">{{ _('rank') }} {{ p.Rank }} · {{ p.UserCount }}</div></th>{% endfor %}</tr>
    </thead>
    <tbody>
    {% for g in groups %}
      <tr class="perm-area" data-area="{{ g.area }}"><td colspan="{{ profiles|length + 1 }}"><span class="perm-chevron">▾</span> {{ g.area }}</td></tr>
      {% for o in g.objects %}
        {% if o.label %}<tr class="perm-object" data-area="{{ g.area }}"><td colspan="{{ profiles|length + 1 }}" style="padding-left:24px">{{ o.label }}</td></tr>{% endif %}
        {% for perm in o.perms %}
        <tr class="perm-row" data-area="{{ g.area }}" data-code="{{ perm.Code }}" data-perm-id="{{ perm.PermissionID }}"
            data-search="{{ ((perm.Code ~ ' ' ~ (perm.Description or ''))|lower) }}"
            data-gate="{{ perm.gate or '' }}">
          <td style="padding-left:{{ 48 if o.label else 24 }}px"><div class="nx-mono">{{ perm.Code }}</div><div class="nx-meta">{{ perm.Description }}</div></td>
          {% for p in profiles %}
          <td class="align-center" data-profile="{{ p.Name }}" data-code="{{ perm.Code }}">
            <input type="checkbox" data-access-id="{{ p.AccessID }}" data-perm-id="{{ perm.PermissionID }}"
                   {% if not can_edit %}disabled{% endif %} data-testid="admin-perms-cell-{{ p.AccessID }}-{{ perm.PermissionID }}">
          </td>
          {% endfor %}
        </tr>
        {% endfor %}
      {% endfor %}
    {% endfor %}
    </tbody>
  </table>
</div>
<aside id="permsHolders" class="nx-card" hidden data-testid="admin-perms-holders"></aside>
{% include 'js/admin/_permissions_js.html' %}
```

Move the `permissionMetaModal` block (Add/Edit permission modal) from `templates/admin/access_control.html` into this template unchanged.

- [ ] **Step 5: Shim + JS** — `templates/js/admin/_permissions_js.html`:

```html
<script nonce="{{ csp_nonce() }}">
  window.NX_PERMS = {
    grants: {{ grants|tojson }},
    canEdit: {{ can_edit|tojson }},
    i18n: {
      changes: {{ _("{n} unsaved change(s)")|tojson }},
      saved: {{ _("Grants saved")|tojson }},
      failed: {{ _("Could not save grants")|tojson }},
      needsView: {{ _("Requires the .view permission of this object")|tojson }},
      holders: {{ _("Held by")|tojson }},
      nobody: {{ _("Nobody holds this permission")|tojson }}
    }
  };
</script>
<script src="{{ static_v('js/admin_permissions.js') }}"></script>
```

`static/js/admin_permissions.js` (all handlers via `addEventListener`; URLs through `API_PREFIX`):

```js
(function () {
  const S = window.NX_PERMS, grid = document.getElementById('permsGrid');
  if (!grid) return;
  const granted = new Set(S.grants.map(([a, p]) => `${a}:${p}`));
  const dirty = new Map();  // "a:p" -> bool
  const boxes = [...grid.querySelectorAll('input[type=checkbox]')];
  boxes.forEach(b => { b.checked = granted.has(`${b.dataset.accessId}:${b.dataset.permId}`); });

  function applyGates() {   // grey a child cell while its object's .view is unchecked in that column
    const state = {};
    grid.querySelectorAll('tr.perm-row').forEach(tr => {
      if (!tr.dataset.code.endsWith('.view')) return;
      tr.querySelectorAll('input').forEach(b => { state[`${tr.dataset.code}|${b.dataset.accessId}`] = b.checked; });
    });
    grid.querySelectorAll('tr.perm-row[data-gate]').forEach(tr => {
      const gate = tr.dataset.gate; if (!gate) return;
      tr.querySelectorAll('input').forEach(b => {
        const ok = state[`${gate}|${b.dataset.accessId}`];
        if (ok === undefined) return;
        b.closest('td').style.opacity = ok ? '' : '0.35';
        b.closest('td').title = ok ? '' : S.i18n.needsView;
      });
    });
  }
  function refreshDirty() {
    const n = [...dirty.entries()].filter(([k, v]) => v !== granted.has(k)).length;
    document.getElementById('permsDirty').textContent = n ? S.i18n.changes.replace('{n}', n) : '';
    const save = document.getElementById('permsSave'); if (save) save.disabled = !n;
  }
  grid.addEventListener('change', e => {
    const b = e.target; if (b.type !== 'checkbox') return;
    b.closest('td').classList.toggle('perm-dirty', b.checked !== granted.has(`${b.dataset.accessId}:${b.dataset.permId}`));
    dirty.set(`${b.dataset.accessId}:${b.dataset.permId}`, b.checked);
    applyGates(); refreshDirty();
  });
  document.getElementById('permsSave')?.addEventListener('click', async () => {
    const changes = [...dirty.entries()].filter(([k, v]) => v !== granted.has(k))
      .map(([k, v]) => { const [a, p] = k.split(':').map(Number); return { accessId: a, permissionId: p, granted: v }; });
    // NX.apiSafe resolves a leading "/" through API_PREFIX itself and adds the JSON + CSRF headers.
    const res = await NX.apiSafe('/api/admin/profiles/grants', { method: 'POST', body: JSON.stringify({ changes }) });
    if (!res.ok || !res.data || !res.data.success) { NX.toast(S.i18n.failed, 'error'); return; }
    changes.forEach(c => { const k = `${c.accessId}:${c.permissionId}`; c.granted ? granted.add(k) : granted.delete(k); });
    dirty.clear(); grid.querySelectorAll('.perm-dirty').forEach(td => td.classList.remove('perm-dirty'));
    refreshDirty(); NX.toast(S.i18n.saved, 'success');
  });
  document.getElementById('permsFilter').addEventListener('input', e => {
    const q = e.target.value.trim().toLowerCase();
    grid.querySelectorAll('tr.perm-row').forEach(tr => { tr.hidden = q && !tr.dataset.search.includes(q); });
    grid.querySelectorAll('tr.perm-area, tr.perm-object').forEach(tr => {
      const rows = [...grid.querySelectorAll(`tr.perm-row[data-area="${tr.dataset.area}"]`)];
      tr.hidden = q && rows.every(r => r.hidden);
    });
  });
  grid.addEventListener('click', async e => {
    const head = e.target.closest('tr.perm-area'); if (head) {
      const collapsed = head.classList.toggle('collapsed');
      grid.querySelectorAll(`tr[data-area="${head.dataset.area}"]:not(.perm-area)`).forEach(r => { r.hidden = collapsed; });
      return;
    }
    const cell = e.target.closest('tr.perm-row > td:first-child'); if (!cell) return;
    const tr = cell.parentElement, aside = document.getElementById('permsHolders');
    // api_admin_permission_holders -> {success, permission:{...}, holders:[{userID, username, fullname, organizationCode, organization, source}]}
    const r = await NX.apiSafe(`/api/admin/permissions/${tr.dataset.permId}/holders`);
    const holders = (r.data && r.data.holders) || [];
    aside.hidden = false;
    aside.innerHTML = `<h3 class="nx-section">${NX.esc(tr.dataset.code)}</h3>` +
      (holders.length ? `<div class="nx-meta">${S.i18n.holders}</div><ul>${holders.map(u => `<li>${NX.esc(u.fullname || u.username)} <span class="nx-meta">${NX.esc(u.organization || '')} · ${NX.esc(u.source || '')}</span></li>`).join('')}</ul>`
                      : `<div class="nx-meta">${S.i18n.nobody}</div>`);
  });
  applyGates();
})();
```

Add `.perm-dirty { outline: 2px solid var(--nx-accent); outline-offset: -2px }` and `.perm-area.collapsed .perm-chevron { transform: rotate(-90deg) }` to `static/css/nexora-ui.css` (Grep an existing `.perm-chevron` rule first; reuse it if present).

- [ ] **Step 6: Nav + overview + What's New** — `templates/_header.html`: the anchor `href="{{ url_for('admin_permission_matrix') }}"` → `url_for('admin_permissions')`, active check `'admin_permissions'`, testid `header-nav-admin-permissions`, label `{{ _('Permissions') }}`, icon `fa-table-cells`. `templates/admin/admin_overview.html`: the card `url_for('admin_permission_matrix')` → `url_for('admin_permissions')`, label `{{ _('Permissions') }}`. `nx_lib/whats_new.py`: the entry with `"endpoint": "admin_permission_matrix"` → `"admin_permissions"` (and its `perm` is already `admin.view`). Delete `templates/admin/permission_matrix.html` and `templates/js/admin/_permission_matrix_js.html`.

- [ ] **Step 7: Run** — `nx -r`; `pytest tests/integration/test_admin_routes.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py tests/unit/test_whats_new.py -q` — Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add nx_lib/views/admin/permissions.py nx_lib/views/admin/__init__.py templates/admin/permissions.html templates/js/admin/_permissions_js.html static/js/admin_permissions.js static/css/nexora-ui.css templates/_header.html templates/admin/admin_overview.html nx_lib/whats_new.py tests/integration/test_admin_routes.py
git rm templates/admin/permission_matrix.html templates/js/admin/_permission_matrix_js.html
git commit -m "feat(admin): permissions x profiles grid replaces the read-only matrix"
```

### Task 13: Slim `/admin/access_control` — profiles get rank, the drawer goes

**Files:**
- Modify: `templates/admin/access_control.html`, `templates/js/admin/_access_control_js.html`, `nx_lib/views/admin/permissions.py`
- Test: `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Failing test**

```python
def test_save_access_profile_updates_rank(admin_client, admin_all_perms, db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestNoPerm'"); access_id = cur.fetchone()[0]
    resp = admin_client.post("/api/admin/access_profile/save",
                             json={"accessId": access_id, "name": "TestNoPerm", "description": "Test no-permission profile", "rank": 5})
    assert resp.status_code == 200
    cur.execute("SELECT Rank FROM dbo.AccessProfile WHERE AccessID = ?", (access_id,))
    assert cur.fetchone()[0] == 5
    cur.execute("UPDATE dbo.AccessProfile SET Rank = 0 WHERE AccessID = ?", (access_id,)); db_conn.commit()
```

Replace `test_save_access_profile_stores_only_allow_rows` (Task 4) — the save API no longer takes `permissions`.

- [ ] **Step 2: Implement** — `save_access_profile`: read `rank = int(data.get("rank") or 0)`; `UPDATE AccessProfile SET Name=?, Description=?, Rank=? WHERE AccessID=?` / `INSERT INTO AccessProfile (Name, Description, Rank) OUTPUT INSERTED.AccessID VALUES (?, ?, ?)`; delete the `DELETE FROM AccessProfilePermission` + `INSERT INTO AccessProfilePermission` block. `admin_access_control`: add `ap.Rank` to the profiles query (`SELECT ap.AccessID, ap.Name, ap.Description, ap.Rank, COUNT(u.userID) AS UserCount ... GROUP BY ap.AccessID, ap.Name, ap.Description, ap.Rank`); drop the `all_permissions` query and template variable. Delete `get_profile_details` and its `/api/admin/access_profile/<int:access_id>/details` rule (only the drawer used it; Grep `access_profile/` in templates to confirm).
- [ ] **Step 3: Template** — in `templates/admin/access_control.html` delete the `<div id="permissionDrawer" ...>` block through its closing tag, the `tab-permissions-btn` button and its panel (`permissionsTableBody` table), and the `permissionMetaModal` (moved in Task 12). The profile card (`admin-ac-edit-profile-<id>` button) opens a small modal with Name, Description, Rank (`<input type="number" min="0" max="1000">`); card shows `{{ _('rank') }} {{ p.Rank }}`. In `_access_control_js.html` delete `setupViewGating`, `setupAutoPermissionLogic`, `permGroupToggle`, the drawer open/close/save code and the fetch of `/api/admin/access_profile/${id}/details`; the profile modal posts `{accessId, name, description, rank}` to `/api/admin/access_profile/save`. Keep the Users tab untouched.
- [ ] **Step 4: Run** — `nx -r`; `pytest tests/integration/test_admin_routes.py tests/unit/test_no_inline_event_handlers.py -q` — PASS. Browser: `/admin/access_control` → Profiles tab → edit nexoraUser → rank field shows 10; no drawer anywhere.
- [ ] **Step 5: Commit** — `git add templates/admin/access_control.html templates/js/admin/_access_control_js.html nx_lib/views/admin/permissions.py tests/integration/test_admin_routes.py && git commit -m "refactor(admin): access control keeps users and profiles; rank editable; drawer removed"`

### Task 14: User detail overrides use the shared grouping

**Files:**
- Modify: `nx_lib/views/admin/users.py` (`admin_user_detail`), `templates/admin/user_detail.html`

- [ ] **Step 1:** In `admin_user_detail` pass `groups=group_permissions(all_permissions)` alongside `all_permissions` (import `group_permissions` from `...security`).
- [ ] **Step 2:** In `templates/admin/user_detail.html` replace the `{% set ns = namespace(prev_group='', prev_sub='') %} ... {% endfor %}` block inside `<tbody id="overridesTbody">` with nested loops over `groups` → `objects` → `perms`, emitting the same three row kinds (`data-perm-group="{{ g.area }}"`, `data-perm-sub-group="{{ o.key }}"` only when `o.label`, and the unchanged `<tr data-perm-id=... data-perm-code=...>` radio row). Keep every `data-testid` exactly (`admin-userdetail-override-<id>-none|deny|allow`).
- [ ] **Step 3:** `nx -r`; `pytest tests/integration/test_admin_routes.py -q -k user_detail`; open `/admin/users/1047` (massimo.zuffi, 3 overrides) — groups read `tenant.generali › attendance`, overrides still Allow.
- [ ] **Step 4: Commit** — `git add nx_lib/views/admin/users.py templates/admin/user_detail.html && git commit -m "refactor(admin): user detail overrides grouped by area and object"`

### Task 15: e2e smoke, i18n, What's New, screenshots, docs

**Files:**
- Create: `tests/e2e/test_admin_permissions.py`
- Modify: `nx_lib/whats_new.py`, `docs/design/permissions.md`, `CHANGELOG.md`, `translations/*/LC_MESSAGES/messages.po` (via the `nx-i18n` skill)

- [ ] **Step 1: e2e smoke** (CI-only; runnable locally with `NEXORA_E2E_PORT` free):

```python
"""E2E: the permissions grid toggles a grant and persists it (#238)."""

CELL = '[data-profile="TestNoPerm"][data-code="jd.view"] input'


def _login_admin(page, base):
    page.goto(f"{base}/dev/login/admin@test.local")
    page.wait_for_load_state("networkidle")


def test_grid_toggle_persists_and_reverts(nexora_server, page):
    _login_admin(page, nexora_server)
    page.goto(f"{nexora_server}/admin/permissions")
    page.wait_for_selector('[data-testid="admin-perms-grid"]')
    box = page.locator(CELL)
    before = box.is_checked()
    box.click()
    page.get_by_test_id("admin-perms-save").click()
    page.wait_for_selector('[data-testid="admin-perms-save"][disabled]')
    page.reload()
    page.wait_for_selector('[data-testid="admin-perms-grid"]')
    assert page.locator(CELL).is_checked() != before
    page.locator(CELL).click()
    page.get_by_test_id("admin-perms-save").click()
    page.wait_for_selector('[data-testid="admin-perms-save"][disabled]')
```

- [ ] **Step 2: i18n** — invoke the `nx-i18n` skill (extract → update → compile; fill de/fr/it for the new strings from Tasks 12–13; the deleted matrix strings become obsolete and are pruned). `pytest tests/unit/test_translations.py -q` → PASS.
- [ ] **Step 3: What's New** — in `nx_lib/whats_new.py` add to the newest release block an entry `{"title": _("One grid for every permission"), "body": _("Admin › Permissions shows every access profile against every permission; tick a cell, save, done. Profiles now carry a rank that decides which profiles an admin may hand out."), "perm": "admin.profiles.view", "endpoint": "admin_permissions", "icon": "table-cells"}`.
- [ ] **Step 4: Docs** — `docs/design/permissions.md`: add *The grid* (`/admin/permissions`, save semantics, cache clear, catalogue actions) and *User overrides*; `CHANGELOG.md` `[Unreleased]` *Added*: "Admin › Permissions grid replaces the per-profile drawer and the Permission Matrix page; profile rank editable on Access Control." *Removed*: "`/admin/permission_matrix`."
- [ ] **Step 5: Screenshots for the owner** — `nx -r`, `nx -u -b --loginas:ben.streich` (or Playwright MCP against `127.0.0.1:8000` after `/dev/login/ben.streich`); capture `var/screenshots/238_permissions_grid.png` (top), `238_permissions_grid_tenant.png` (scrolled to `tenant.generali`), `238_access_control_profiles.png`, `238_user_detail_overrides.png`; send with `SendUserFile`.
- [ ] **Step 6: Gate** — `python scripts/test_db_reset.py && pytest tests/unit tests/integration -q` → PASS; `nx --doctor` → Permissions `ok`.
- [ ] **Step 7: Commit**

```bash
git add tests/e2e/test_admin_permissions.py nx_lib/whats_new.py docs/design/permissions.md CHANGELOG.md translations messages.pot
git commit -m "feat(admin): permissions grid e2e smoke, translations, What's New card and docs"
```

- [ ] **Step 8: Close the loop** — `gh issue comment 238 --body "Shipped on <branch>: see docs/design/permissions.md and the #238 spec Appendix A for the mapping."`; leave the issue open until the PROD deploy (owner closes after the off-hours deploy, D6).

## Gotchas & notes

- **Worktree ≠ checkout:** no `env/*.env`, no `.venv` (see Context). The dev server on `:8000` runs the *main* checkout — for browser checks of worktree code start a second instance from the worktree with `nx -u --no-conflict` (next free port from 8001) or merge first.
- **`NX.api` / `NX.apiSafe` prefix leading-slash URLs themselves** (`resolveUrl`): pass `'/api/admin/…'`, never `${API_PREFIX}api/…`, or PROD gets `/nexora/nexora/…`.
- **`/api/admin/*` writes do not clear the user cache** (`_invalidate_user_cache` checks the `/admin` prefix only). The grants API calls `user_cache.clear()` itself; keep that line.
- **Migration numbering race:** `feat/tenant-kernel` owns 0083–0085 and they are applied on INT. Run `db-migrate.py --env INT --dry-run` before creating 0086/0087/0088; renumber the plan if a peer took a number meanwhile.
- **Hook order in Task 7:** commit 0088 with `SQL_SYNC_SKIP=1` so INT is not renamed before the code sweep (Task 8) lands; apply it explicitly in Task 8 Step 3. If the hook already applied it, the running INT server 403s until `nx -r` on the swept code — expected, not a bug.
- **The sweep regex** matches whole codes only (`(?<![A-Za-z0-9_.])code(?![A-Za-z0-9_.])`), longest first, so `admin.view` never eats `admin.view.users`. F-strings and prefixes (`perm_prefix="generali.…"`, `.edit.transorganizational`) are the hand-edited sites in Task 8 Step 2.
- **`admin.users.manage`** exists only in `sql/test/seed.sql` (test-only, matches the grammar) — leave it.
- **`tests/unit/test_whats_new.py`** requires `perm` values to match `[a-z0-9_.]+` and `endpoint` names to resolve — the matrix endpoint rename in Task 12 Step 6 is mandatory or every page 500s in What's New.
- **CSP:** no `onclick=` in templates; `tests/unit/test_no_inline_event_handlers.py` scans `templates/**/*.html`. All grid behaviour lives in `static/js/admin_permissions.js`.
- **Jinja cache:** `nx -r` after every template change before a browser check; the e2e server is a fresh subprocess so it never has the problem.
- **Deploy blip (D6):** the old build serves renamed codes for the deploy window. Off-hours deploy; note in the release.
- **Generali descriptors:** after Task 8, `CrudTable` has no `view_perm`; the attendance page's permission is `tenant.generali.attendance.view`, so `page_visibility()['generaliAdditionalServicesPerm']` and the `/generali/additionalServices/*` routes gate on the same code — intended (spec Why §5).
- **Rank edge:** `assignable_profile_ids()` returns `set()` for a user without a profile (`ISNULL(MAX(...), -1)`), so such an admin can create no users. Ceiling noted in the spec; per-rank *edit* protection is a one-line extension if ever wanted.
