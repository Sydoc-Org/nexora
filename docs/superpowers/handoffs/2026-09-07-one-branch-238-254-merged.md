# Handoff — one branch: #238 permission grid and #254 field quality merged into the tenancy branch

**Date:** 2026-09-07 · **Branch:** `refactor/255-admin-nav-tenancy-labels` (main checkout `C:\dev\nexora`,
the only worktree left) · **90 commits ahead of `origin/main`, nothing pushed** · commit-only — the owner
tests on INT (port 8000 runs this branch), then pushes and opens **one PR** to `main` for the PROD deploy.

**Prior handoff:** [`2026-09-05-tenant-is-a-portal-memberships.md`](2026-09-05-tenant-is-a-portal-memberships.md).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `dac4063b` | #238 Task 9: grammar convention test, `nx --doctor` Permissions section, sweep script deleted; **migration `0106`** Enterprise Admin holds every permission (trigger keeps it so) |
| `84ecb932` | #238 Task 10: `docs/design/permissions.md`, pointers, changelog |
| `6dfaab1d` | #238 Task 11: `group_permissions()` |
| `3946b35b` | #238 Task 12: `/admin/permissions` grid + `POST /api/admin/profiles/grants`; Permission Matrix deleted |
| `cd177903` | #238 Task 13: Access Control keeps Users + Profiles; drawer gone; rank editable |
| `e72615a6` | #238 Task 14: user-detail overrides grouped by area/object |
| `8b0e56ce` | rank capped at the actor's own on **update** too (security review finding) |
| `df1efa7a` | #254 migrations renumbered `0097/0098/0099–0104` → **`0107`–`0114`** (INT `SchemaMigrations` rows repointed) |
| `45753f3c`, `4876e402` | #238 Task 15: e2e smoke, translations, What's New card, endpoint baseline |
| `ea4cb338` | **merge** `origin/main` + #238 into 255 (see Gotchas: four migrations rewritten, `0115`) |
| `6e66bb63` | header: staff keep Global Dashboard/Workitems; Reporting always renders |
| `b1b2b438` | header: tenant-marked pages match their marker only; backlog chart all solid lines |
| `b086692e` | **merge** #254 into 255; nav label **Global Reporting**; plural-aware translation tests |

## TL;DR

1. **Everything is on one branch.** `refactor/255-admin-nav-tenancy-labels` = `origin/main` (v3.2.4) + tenancy
   work + #238 (Tasks 1–15 complete) + #254. The #238 worktree and `C:\dev\nexora-254` were merged, then
   removed with their branches (owner asked). INT is up to date through **`0115`**; next free number is **`0116`**.
2. **#238 is finished**: one code grammar, allow-only profile grants, `AccessProfile.Rank`, one
   `process.<client>.<name>.view` per process, the permissions × profiles grid, Enterprise Admin holds all.
   Issue #238 has a comment; stays open until the PROD deploy.
3. **The 255 code was swept to the new grammar** (0088 mapping + `admin.tenants.view/.edit` via `0115`).
   Process allow-lists keep the tenant scope and read both code shapes (`process_grants(perms, prefix=None)`,
   one-dot pairs only).
4. **Full gate green** at `b086692e`: `2391 passed, 29 skipped, 2 failed` — the two are the known order-dependent
   rate-limit tests (`test_rate_limit_429_for_unauthenticated_requests`, `test_verify_2fa_rate_limit_eventually_429`),
   green in isolation.

## Next steps (ordered)

1. **Owner tests on INT** (port 8000 serves this branch; `bin\nx.ps1 -r --port:8000` after template edits), then
   **pushes the branch and opens the PR** to `main`. Link #238, #254, #255, #256, #257.
2. **PROD deploy, off-hours** (D6): migrations `0086`–`0115` apply before the app pool stops; the old build 403s
   during the window. `scripts/env-sync.py` by habit — no new env keys.
3. After deploy: close #238 and #254; eyeball `/admin/permissions` on PROD against `var/screenshots/238_*.png`.
4. Carried over, untouched: `compassUser` → CMPS, #256 entity/field editors, tenant delete leaving
   `tenant.<code>.*` rows, INT oddities (Privera logo 404, PDBS accent `#000000`), the What's New card for the grid
   sits in the 3.2.4 block — move it to the next release block when cutting one.

## Gotchas & notes

- **Four applied migrations were edited** (`0091`, `0092`, `0094`, `0095`): written before `0086` dropped
  `AccessProfilePermission.Effect` and `0088` renamed the catalogue; INT ran them first, PROD runs them after.
  Effect-dependent statements now sit in `sp_executesql`, code lookups match both shapes; INT checksums
  re-blessed (`db-migrate.py --rebless`). Same precedent as #254's `0097`. Changelog records it.
- **`0107`–`0111` checksums were re-blessed too** — CRLF drift only (byte-identical to the 254 branch content).
- **Sidebar rules** (`templates/_header.html`): Global Dashboard/Workitems hide only for a user inside exactly
  one tenant (flat sidebar); Global Reporting always renders (`'always': true`); a mounted page with a
  tenant-specific marker (`tenant_<code>_workitems`) matches only that marker, the endpoint fallback is for
  pages whose marker is the endpoint (Prepared Documents).
- **Access profile modal** carries name, description, **organization binding (0090)** and **rank**; save
  caps rank at the actor's own on create and update. Grants live only on `/admin/permissions`.
- **`process_grants` drops pairs that are not exactly `<client>.<name>`** — `/admin/processes` relies on it.
- **Test-suite DB lock:** `NEXORA_TEST` is shared (sp_getapplock); a colleague's run on another machine held it
  for ~15 min today. Runs wait, don't kill.
- **Bash-tool heredocs mangle backslashes** — write Python with regexes to the scratchpad and run the file.
- `docs/nx-architecture.drawio` (+ `.bkp`) is the **owner's** diagram in progress — untracked on purpose.
- Architecture facts confirmed for the diagram: tenant = portal (nav group + pages + `tenant.<code>.*`), an
  organization belongs to **at most one** tenant (`demo` is outside), a user has exactly one organization and
  one profile, profiles bound to an organization are holdable only by its users (server 400), global profiles by
  anyone, **branding (logo, accent) is on the Organization**, not the tenant.

## Untracked / left for owner

- `docs/nx-architecture.drawio`, `docs/.$nx-architecture.drawio.bkp` — not committed.
- `var/screenshots/238_*.png` — gitignored evidence.

## How to verify

```powershell
# full tier (green at b086692e apart from the two flaky rate-limit tests; ~15 min)
$env:ENVIRONMENT = "TEST"; .venv\Scripts\python scripts\test_db_reset.py
.venv\Scripts\python -m pytest tests/unit tests/integration -q -p no:cacheprovider

# migrations up to date on INT (0086-0115)
.venv\Scripts\python scripts\db-migrate.py --env INT --db NexoraDB --dry-run

# live: /dev/login/ben.streich → /admin/permissions, /admin/access_control (Profiles tab), sidebar Global entries
bin\nx.ps1 -r --port:8000
```

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-09-07-one-branch-238-254-merged.md`. Nothing is red;
the branch waits for the owner's INT test, push and PR.
