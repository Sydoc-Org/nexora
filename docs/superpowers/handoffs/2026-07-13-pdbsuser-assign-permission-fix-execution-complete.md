> **Superseded same-day:** the newer handoff is
> `2026-07-13-pr115-ship-ci-speedups.md` (PR #115 merged + deployed, CI speedups, Confluence cred
> hunt). Resume from that one.

# Handoff — pdbsUser Access-Profile Assignment Fix (EXECUTED — ready to merge)

**Date:** 2026-07-13 · **Branch:** `feature/2.5.64` · **9 commits ahead of origin** · **commit-only (remote)** · no plan worktree
**Prior handoff:** none this cycle — first work on `feature/2.5.64` (opened 2026-07-13, prior handoff was the June 24 `prepared-docs-preview-fixes` cycle on `feature/2.5.63`, already merged to main)
**Plan executed:** `docs/superpowers/plans/2026-07-13-pdbsuser-assign-permission-fix.md`
**SDD ledger:** `.superpowers/sdd/progress.md` (full per-task review record; gitignored scratch)

## TL;DR

- **All 7 plan tasks executed, reviewed, and committed.** 8 commits on `feature/2.5.64`
  (`673a552..f84a14a`, where `673a552` is the plan-doc commit itself). Nothing left to implement.
- Fixed three confirmed defects: (1) `pdbsUser` access profile was silently unassignable in the admin
  UI due to a case-mismatch between a hand-inserted permission code and the lowercased code the app
  checks; (2) admin permission add/edit + user-all-permissions APIs 500'd on every environment
  (missing `Permission.SortingCode` column); (3) a **privilege-escalation gap** — `admin_add_user`
  never checked the assign-permission, so any `admin.create.user` holder could create a user with
  ANY profile (including `enterpriseAdmin`) via a direct POST.
- **Final whole-branch review (opus): READY TO MERGE.** No Critical, no Important, across the full
  `main`-merge-base range (12 commits, incl. 4 pre-plan commits already on the branch). 3 Minors, all
  cosmetic or explicitly out-of-plan-scope.
- **Live INT browser verification: all 4 checklist items PASS** on a freshly-restarted server (see
  Gotchas for the tooling substitution).
- **Owner still owes:** `git push` + PR→main (remote/commit-only — never done here), plus the
  optional immediate PROD migration apply (see Owner actions below).

## This session's commits (oldest → newest)

```
673a552  docs(plan): pdbsUser assign-permission fix plan                        (pre-existing, plan doc)
903668e  fix(db): add Permission.SortingCode; normalize pdbsUser code (0034)    (Task 1)
e313b4c  fix(security): case-insensitive permission code matching              (Task 2)
7b59a3a  refactor(hooks): use has_permission for maintenance bypass            (Task 3)
b4e99ab  test(admin): tighten permission API statuses + CRUD round-trip        (Task 4)
1554a2b  test(admin): use mixed-case code in permission round-trip test        (Task 4 fix)
6bb97e3  fix(admin): enforce assign-profile permission on user creation        (Task 5, SECURITY)
5ae3589  test(admin): fix allow-path cleanup to actually delete the test user  (Task 5 fix)
f84a14a  docs(changelog): pdbsUser assign fix + permission API repairs         (Task 6)
```
(Task 7 was live-verification only, no commits. The handoff commit for THIS doc lands on top of `f84a14a`.)

## What shipped (7 files touched by the plan, across 8 commits)

| Task | Fix | Files | Commit(s) |
|---|---|---|---|
| **1** Migration 0034 | Added `SortingCode nvarchar(50) NULL` to `dbo.Permission`; normalized the one hand-inserted mixed-case row (`...pdbsUser` → `...pdbsuser`), collation-proof `WHERE LOWER(Code)=...`. Mirrored in test schema. | `sql/_migrations/NexoraDB/0034_permission_sortingcode_and_pdbsuser_case.sql`, `sql/NexoraDB/Tables/dbo.Permission.sql` (regenerated), `sql/test/schema.sql` | `903668e` |
| **2** Case-insensitive matching | `has_permission()` now lowercases both sides — the fix that makes Task 1's data repair actually take effect everywhere. | `nx_lib/security.py`, `tests/unit/test_security.py` | `e313b4c` |
| **3** Hooks reroute | Maintenance-lockout bypass check routed through `has_permission()` instead of raw list membership, so it benefits from Task 2 too. | `nx_lib/hooks.py`, `tests/unit/test_hooks.py` | `7b59a3a` |
| **4** Test tightening + round-trip | 4 tolerant `in (200, 500)` assertions → strict; new CRUD round-trip test proving `Code`/`SortingCode` survive add→edit with case preserved (mixed-case value, after a review round caught an all-lowercase value that couldn't prove it). | `tests/integration/test_admin_routes.py` | `b4e99ab`, `1554a2b` |
| **5** Add-user authz gap (SECURITY) | `admin_add_user` gated with the same `admin.assign.user.accessprofile.<profile>` check `admin_edit_user` already had; `%r`-parameterized logging (not f-string) to prevent log injection from request-controlled values. Deny-path test proves both 403 AND zero rows persisted. | `nx_lib/views/admin.py`, `tests/integration/test_admin_routes.py` | `6bb97e3`, `5ae3589` |
| **6** Changelog | 3 `### Fixed` bullets under `[Unreleased]`, verified against actual shipped code, no overclaiming. No docs page existed to add a permission-code-convention note to — correctly skipped rather than inventing one. | `CHANGELOG.md` | `f84a14a` |
| **7** Live verification | Browser-driven: `pdbsUser` confirmed present in both add-user and edit-user dropdowns; throwaway user create+delete end-to-end; throwaway permission add+delete (no 500s). All 4 PASS. No commits (verification only). | — | — |

**No new top-level files/dirs** (no `deploy.yml` exclude changes needed). **No new i18n strings** (reused the existing `_("Permission Denied for this action.")`, no pybabel cycle needed).

## How it was executed (subagent-driven development)

Fresh implementer subagent per task → task review (spec + quality) → fix loop → next; then one opus
whole-branch review. Models: sonnet implementers/reviewers throughout, opus for the Task 5 review
(security-critical) and the final whole-branch review. Two review cycles found real, fixed issues:

- **Task 4:** the round-trip test's `code` value was all-lowercase (`test.roundtrip.perm`), so its
  "case preserved" assertion couldn't have caught a hypothetical lowercase-on-save regression — only
  `SortingCode` was meaningfully tested. Fixed by switching to a mixed-case code value; independently
  re-verified the route does no case normalization (`.strip()` only).
- **Task 5:** the allow-path test's cleanup called the app's own `/admin/users/delete/<id>` route,
  but that route's cascading delete hits `tags`/`workitem_metadata` tables NEXORA_TEST doesn't have,
  so it 500s on the first statement and never actually deletes — every run was orphaning a
  `task5-allow-*` row in the shared test DB. Fixed with a direct SQL delete + verified-gone assertion;
  6 pre-existing leaked rows were found and purged during the fix.

Full review trail (all per-task ✅/❌ verdicts, evidence, file:line citations) in
`.superpowers/sdd/progress.md`.

## Next steps (ordered)

1. **Owner: `git push`** `feature/2.5.64` and **open the PR → main** (remote/commit-only — the agent
   never pushes). Pre-push runs the full suite incl. Playwright e2e.
2. **Owner: PROD fix timing.** Migration `0034` auto-applies on the next deploy to `main`. To fix PROD
   immediately instead: `python scripts/db-migrate.py --env PROD` (idempotent; will also record
   `0032`, which is safe — its rows already exist by hand per the prior release-open commit).
3. **Owner: post-deploy PROD spot-check** — assign `pdbsUser` to one user via the UI.
4. Optional cosmetic cleanup (non-blocking Minor from final review): `test_api_admin_permission_users_seeded`
   (`tests/integration/test_admin_routes.py:468`) still asserts `in (200, 500)` — its route never
   referenced `SortingCode` so it was correctly out of Task 4's scope, but NEXORA_TEST now supports it
   reliably returning 200; tighten to `== 200` for symmetry with its sibling test if touching that file again.

## Owner actions baked into the plan (not the agent's job)

- **PROD migration timing / manual apply** — see Next steps #2 above.
- **Post-deploy PROD spot-check** — see Next steps #3 above.
- **Review + push `feature/2.5.64`** — full pre-push gate (Playwright e2e).

## Follow-ups deliberately NOT done (per the plan — don't pick these up without a fresh spec)

- Case-insensitive matching for the reporting raw-membership sites (`nx_lib/reporting/sources.py
  accessible()`, `nx_lib/reporting/runner.py`) — reporting source grants are separate machinery.
- `admin_edit_user` currently lets an assign-permission holder change the password of ANY existing
  user, including ones whose CURRENT profile they couldn't assign — a separate, pre-existing gap,
  noted but not fixed (needs its own spec discussion).
- The stale header comment in `test_admin_routes.py` claiming `admin@test.local` has only 3
  permissions (it actually has every seeded permission) — fix opportunistically if touching that file
  again for another reason.

## Gotchas & notes (READ)

- **Live browser verification used a tooling substitution.** The `claude-in-chrome` extension was
  unreachable this session — the OS default browser is Firefox, and the installed Chrome had no
  extension in its profile. Per the plan's own fallback guidance, Task 7 drove a standalone Playwright
  script (same Chromium/tooling the project's own `tests/e2e/` suite already depends on) against the
  live INT server instead. Same rigor: real clicks, real network requests, screenshots at each step.
  No application code was touched during verification.
- **Screenshots** at `var/screenshots/pdbsuser-assign-*.png` (9 files, gitignored — not committed,
  not attached to this handoff).
- **`%r` logging is deliberate, not a style choice.** The new gate in `admin_add_user`
  (`nx_lib/views/admin.py`) logs `profile=%r username=%r` with values as separate positional args,
  NOT an f-string — `accessprofile`/`username` are request-controlled, and an f-string would let a
  request inject newlines/control characters into `var/logs/system/app.log`. Do not "clean this up"
  into an f-string.
- **Two-target monkeypatch trap (bit a prior plan draft, avoided here).** `nx_lib/views/admin.py`
  imports `has_permission` at module load, so inline gate calls in route bodies resolve
  `nx_lib.views.admin.has_permission` — patching `nx_lib.security.has_permission` only reaches the
  `@require_permission` decorator's closure. All Task 5 tests correctly patch the view-module binding.
- **`*.filter.process.<client>.<Process>` codes are safe from Task 2's lowercasing** (verified at the
  final review, not just asserted): they're consumed via prefix-split iteration over
  `session['permissions']` (case-preserving reconstruction), never through `has_permission()` — so
  Task 2 cannot corrupt IDs 176/177 or any future case-significant code of that shape.
- **`SQL_SYNC_SKIP=1`** was used where needed for the migration commit (known INT `SchemaMigrations`
  CRLF drift on Windows). Never `--no-verify`. All commits landed clean.
- **Migration numbering note (pre-existing, not introduced this session):** `0032` (added by the
  release-open commit just before this session) sorts before the already-existing `0033` — benign,
  `db-migrate.py` tracks applied files individually, not sequentially; flagged by the final reviewer
  as informational only.
- **Pre-existing unrelated stray in a non-plan commit:** `scripts/new-process.py:52` (WIP helper, not
  part of this plan) has a commented-out latent SQL f-string bug — dead code, harmless, noted by the
  final reviewer for completeness only.

## Untracked / left for owner

Working tree is clean — nothing untracked or uncommitted at handoff time. No strays this session.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
git log --oneline 673a552..HEAD                 # the 8 plan-execution commits + this handoff
git status --porcelain                          # should be empty

# Feature test slices (all green at handoff):
.venv\Scripts\python -m pytest tests/unit/test_security.py tests/unit/test_hooks.py -q
.venv\Scripts\python -m pytest tests/integration/test_admin_routes.py -q   # hits live NEXORA_TEST
```

## Resuming in a fresh session

This feature is **done and ready to merge** — the remaining items are owner-only (push + PR + PROD
migration timing + spot-check). If resuming: `/reset-session` (the `var/handoff-pending` flag points
here).
