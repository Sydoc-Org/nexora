**Test expansion — handoff (Phase 0 + Phase 1 complete, Phase 2 next)**

Date: 2026-06-01 (afternoon, post-Phase-1 push)
Branch at handoff: `feature/2.5.62` — 41 commits ahead of `main`. **Not yet merged.** Pushed to `origin` at `cdfdbb8`.
Topic keyword: **test-expansion**
Plan: `docs/superpowers/plans/2026-06-01-test-expansion.md`
Tests: **22 → 332** (+310, all passing)

To resume: "read the phase 1 complete handoff" → land here → next move is **Phase 2: integration tests for every route** (10 tasks, ~80 new tests).

---

**Reading order for the resuming agent**

1. This file (you are here).
2. `docs/superpowers/plans/2026-06-01-test-expansion.md` — the 47-task plan. Phase 2 tasks live at lines ~1530-2200 (Task 2.1 through Task 2.10).
3. `tests/README.md` — fixtures, patterns, run commands. Already documents `admin_client` / `user_client` / `noperm_client` / `db_conn` / `fake_session` / `seeded_org`. Phase 2 should follow the same patterns.
4. `tests/unit/test_coverage_thresholds.py` — the per-module ratchet. Phase 2 will raise the `views/*` entries.
5. `tests/integration/test_auth_flow.py` + `tests/integration/test_permission_guard.py` — the two existing integration files. Phase 2 extends `test_auth_flow.py` (Task 2.2) and adds 8 new `test_<module>_routes.py` files.
6. `CLAUDE.md` at the repo root — covers branch policy, the SQL-migration workflow, the `nx` CLI tool, and the `bypassPermissions` git rules. Per CLAUDE.md, `feature/2.5.62` allows stage + commit + push without per-turn auth.

---

**Status — what's on feature/2.5.62 (41 commits, pushed to origin, not yet PR'd)**

| group | range | what |
|---|---|---|
| Plan | `a97c965` | The 47-task plan document |
| Phase 0 (foundation) | `5167e5e..ed85697` (8 commits incl interstitial fix) | coverage.py 7.6.10 + defusedxml 0.7.1 + pytest-cov 6.0.0 dev deps; coverage flags in pytest addopts; `fail_under=0` (per-module ratchet is the real gate); data-testid on all 51 templates (~506 testids); conftest fixtures (admin/user/noperm_client + fake_session + auth_app_ctx + seeded_org); `test_coverage_thresholds.py`; `tests/README.md` |
| Phase 1 (unit tests) | `cfd92e8..cdfdbb8` (16 commits) | One module per task, all nx_lib helper modules excluding views: security (extended), files (verified), users, db, i18n, maintenance, middleware, notifications, octo, process_helpers, hooks, extensions, app_logging, cli, cli_doctor, create_app smoke |

**Coverage achieved (per-module, `views/*` and `generali.py` excluded — Phase 2 / Generali plan):**

| Module | Coverage | Tests added |
|---|---|---|
| `app_logging.py` | 100% | 6 |
| `db.py` | 87% | 10 |
| `extensions.py` | 100% | 10 |
| `files.py` | 100% | (pre-existing 5) |
| `hooks.py` | 100% | 41 |
| `i18n.py` | 100% | 8 |
| `maintenance.py` | 100% | 26 |
| `middleware.py` | 100% | 6 |
| `notifications.py` | 100% | 6 |
| `octo.py` | 99% | 15 |
| `process_helpers.py` | 100% | 12 |
| `security.py` | 82% | 29 |
| `users.py` | 100% | 9 |
| `cli.py` | 71% | 63 |
| `cli_doctor.py` | 65% | 30 |
| `create_app` smoke | n/a | 15 |
| thresholds test | n/a | 24 |

Per-push gate: ruff + ruff-format + gitlint + sql-migrate-INT + sql-sync-check + pre-push pytest — all surviving. 41 pushes' worth of pre-commit cycles confirmed it.

---

**Things learned the hard way in Phase 0 + 1 (don't relearn these)**

**1. `fail_under` in `[tool.coverage.report]` blocks every pytest run until met.**
The plan as written set `fail_under = 90` in Task 0.1 — coverage.py enforces that floor on *every* invocation, so until phase-1/2/3 tests landed, every local `pytest` exited with code 1 (current was 1.82%). Fixed in commit `0fd1c19`: `fail_under = 0` + a comment pointing at `tests/unit/test_coverage_thresholds.py` as the real per-module ratchet. Plan doc patched in the same commit. **Don't raise this back to >0 globally** — use the threshold test instead.

**2. coverage.xml uses paths relative to `[tool.coverage.run] source`, NOT project-root paths.**
My first `MIN_COVERAGE` dict used keys like `"nx_lib/security.py"`. Every lookup missed because coverage.xml emits `"security.py"` when `source = ["nx_lib"]`. Threshold test silently treated everything as 0%. Watch for this when adding new entries to `MIN_COVERAGE`: keys are bare `module.py` for nx_lib helpers and `views/<name>.py` for view modules — NO leading `nx_lib/`.

**3. Modules absent from coverage.xml must be treated as 0%, not "no data → fail".**
Running `pytest tests/unit/test_coverage_thresholds.py` in isolation produces a coverage.xml that only contains files exercised by *that* test — so every other `nx_lib/*` is missing. First version of the threshold test failed `actual is not None`. Final version uses `pcts.get(module, 0.0)` so subset runs pass when their thresholds are 0; thresholds above 0 fail loudly with a hint to run the full suite.

**4. NEXORA_TEST is the auth/permissions subset of the prod schema — many tables are missing.**
`sql/test/schema.sql` only includes: `Organizations`, `AccessProfile`, `AccessProfilePermission`, `Permission`, `Users`, `ActiveSessions`, `UserPermissionOverride`. Tables missing from TEST: `Notifications`, `MaintenanceBanner`, `ActivityInstancesToIgnore`, `Statconfig`, `IndexFieldMappings`, `Chat_Messages`, every workitem/dashboard/invoice table. Affected tests use mocked DB (mock `engine_nexora_db.raw_connection`); the test file docstring documents this and points at a future schema extension as the migration path. **Phase 2 will hit this hard** — many routes query tables that aren't in TEST. Plan: either extend `sql/test/schema.sql` (preferred) or mock at the connection level (current Phase 1 pattern).

**5. Flask-Babel's gettext() needs a request context, not just an app context.**
Tests for `nx_lib.octo.get_activity_type_name`'s error branch (which returns `_("Error fetching activity instance")`) failed with "Working outside of request context" because `get_locale()` reads `session`. Use `app.test_request_context("/")` for any path that touches `_("…")`. `app_context()` alone is not enough.

**6. Functions with lazy `import requests` inside need `patch("requests.post")`, NOT `patch.object(mod, "requests.post")`.**
`nx_lib/cli_doctor.py` lazy-imports `requests` inside each `_check_graph` / `_check_octo` / `_check_bexio`. `patch.object(cli_doctor, "requests")` doesn't work because the attribute doesn't exist until the function runs. Use `patch("requests.post")` (global) instead.

**7. ruff auto-fixes mean re-staging after EVERY commit attempt.**
ruff and ruff-format hooks auto-fix the file then mark the hook failed so the commit must be retried. About one in three commits needed a second `git add <file>` + `git commit` pass. Common ones:
- `UP038 isinstance(x, (a, b))` → switch to `isinstance(x, a | b)`
- `SIM117` nested `with` → combine into parenthesised single-context manager
- `SIM105` `try`/`except`/`pass` → `contextlib.suppress(Exception)`
- `N817 CamelCase imported as acronym` → add `# noqa: N817` for `ET = ElementTree`-style aliases (canonical idiom)
- `B007` unused loop variable → rename to `_`
- `F841` unused local → delete
- `RUF003` Unicode ambiguous char (×, –, …) in comments → swap for ASCII equivalent or move to docstring

**8. The pre-commit `mixed-line-ending` hook auto-fixes silently.**
`Out-File -Encoding utf8` produces CRLF endings; the hook converts to LF and stages the fix. On rare runs this propagates a "Stashed changes conflicted with hook auto-fixes" warning if you have untracked files in the same directory — the auto-fix gets rolled back. Fix: `git reset HEAD <spurious files>` + retry the commit. Phase 0.4 hit this once; harmless once unwound.

**9. The pre-push pytest gate uses SYSTEM python, not the venv.**
`.pre-commit-config.yaml:77-83`'s `pytest-pre-push` hook runs `python -m pytest tests …` with `language: system`. That means it picks up whatever's on PATH (`C:\Users\bes\AppData\Local\Programs\Python\Python313\python.exe` for me), NOT `.venv\Scripts\python.exe`. Phase 0.2 added `--cov=…` to `addopts`, which made the gate immediately fail because system Python didn't have pytest-cov. Fix at the end of Phase 1: `python -m pip install pytest-cov==6.0.0 defusedxml==0.7.1` into system Python. **Phase 2 onwards, the system Python needs to stay in sync with the dev deps** — easy footgun if anyone re-builds the dev box.

**10. Pre-commit hook may stash + restore your unstaged work IF you have untracked files in the repo.**
The session left a handful of stray untracked files around the repo (`note`, `errDiv.remove()`, `app_logging.init_app`, `0`, `1,-`, `scripts/generali-import/*.xml` from prior work). Pre-commit stashes those, runs hooks, and on rollback re-stages them. Phase 0.4 commit auto-pulled `scripts/generali-import/*.xml` into staging. Clean up untracked clutter before starting Phase 2: `git status` first, then either commit or remove anything that shouldn't be there.

**11. SQL Server connectivity is transient.**
At one point during Phase 0 the `db-migrate.py` pre-commit hook couldn't reach `INTSQL01,1433` — connection failed, second commit attempt 30s later succeeded. The CLAUDE.md-documented `$env:SQL_SYNC_SKIP="1"` escape hatch worked once when the issue persisted. Don't panic on transient SQL failures; retry.

---

**Decisions still in force (from session-1 questioning of the planner)**

| Decision | Value |
|---|---|
| Coverage bar | Strict 100% goal per module, enforced via per-module ratchet test |
| DB strategy | Real DB everywhere where the test-schema permits; mocked at connection level when tables aren't in `sql/test/schema.sql` (documented per-test) |
| E2E selectors | `data-testid` added to all 51 templates up front (Task 0.3 / commit `b679852`); ~506 testids in tree; Phase 3 will use them |
| Generali scope | Separate Phase-2 plan (stub committed at the end of Phase 1; will be drafted after Phase 1 ratification) |
| Plan execution model | Subagent-driven for the early infrastructure tasks (0.1–0.3); direct implementation + thorough self-review for the rest. The previous subagent for Phase 0.4 hit a session limit mid-task; budget made that a one-time event. |
| Commit messages | gitlint-conformant: short title + body, no markdown emphasis; commits routinely include a "why" paragraph |
| Branch policy | feature/2.5.62 allows stage + commit + push pre-auth per CLAUDE.md; never touch main |
| Pre-push gate | Runs ruff + format + gitlint + sql-migrate-INT + sql-sync-check + full pytest (with cov flags) before any push lands; takes ~30-60s |

---

**What Phase 2 needs to do — 10 tasks, ~80 integration tests**

Every route registered by every non-Generali view module gets at least one integration test per accepted method, per permission case, per success/failure branch. All tests use the Flask test client (`client`, `admin_client`, `user_client`, `noperm_client`).

The plan lists the exact tests for each module in `docs/superpowers/plans/2026-06-01-test-expansion.md` Tasks 2.1 through 2.10. Quick map:

| Task | File | Routes | Notes |
|---|---|---|---|
| 2.1 | `tests/integration/test_core_routes.py` | 5 (`/`, `/jdvance`, `/maintenance`, `/api/maintenance_active`, `/session_heartbeat`) | Smallest; warm-up |
| 2.2 | extend `tests/integration/test_auth_flow.py` + new `tests/integration/test_auth_routes.py` | 11 (login family + dev_login + reset flow + rate-limits) | Existing file has 4 tests; add ~10 more. **Rate-limit tests are tricky: Flask-Limiter uses in-memory storage per worker — assert `429 or other` so test isn't brittle.** |
| 2.3 | `tests/integration/test_profile_routes.py` | 4 (`/profile`, `/update_profile`, `/change_password`, `/language/<lang>`) | Password-change happy path + bad current password |
| 2.4 | `tests/integration/test_dashboard_routes.py` | 13 (page + 11 widget APIs + activity) | Widget endpoints expect process-specific payloads — many will be `200 or 400 or 404` because TEST DB has no widget data |
| 2.5 | `tests/integration/test_admin_routes.py` | **38** — the biggest task | Sections per area (orgs / banners / logs / sessions / users / access control / permissions). Plan has anchor tests for each section. |
| 2.6 | `tests/integration/test_workitems_routes.py` | 19 | Includes mention-users, audit history, comment, tag, media. Most will be `(200, 404, 403, 400)` matches since TEST DB has no workitems. |
| 2.7 | `tests/integration/test_invoices_routes.py` + `tests/unit/test_invoices_helpers.py` | 3 + helper unit tests | Mock Bexio requests heavily (the route hits prod Bexio). |
| 2.8 | `tests/integration/test_notifications_routes.py` | 2 | GET + mark_read. **Notifications table absent in TEST schema — mock the DB or extend schema.sql first.** |
| 2.9 | `tests/integration/test_chat_routes.py` | 6 | Conversations + messages + upload. **Chat_Messages table absent in TEST — mock or extend schema.** |
| 2.10 | extend `tests/unit/test_create_app.py` | exact-set endpoint assertion | Adds a single test that the full expected endpoint set is registered. Catches future register_routes() removals. |

**After Phase 2: 22 → ~330 tests in unit/, +80 in integration/ = ~410 total.** Coverage thresholds in `MIN_COVERAGE` for `views/*` should ratchet from current 0 (or 20 for auth) up to 60–80% per module.

---

**Open caveats / known issues carrying into Phase 2**

1. **Test-schema gaps (recurring theme).** Phase 2 routes will frequently 500 on real DB because tables don't exist. Decision needed at the start of Phase 2: extend `sql/test/schema.sql` with the minimum tables each route needs (preferred, but more upfront work), or mock `engine_*_db.raw_connection()` per test (faster but lower fidelity). Phase 1 pattern was per-test mocks; Phase 2 may justify investing in a `schema-extended` seed if too many tests need mocking.

2. **Duplicate testids in `_generali_reporting_js.html` row constructors** (Code-quality review of Task 0.3). Generali-only, so doesn't affect Phase 1/2/3 tests but the Generali Phase-2 plan should suffix those testids with row index OR scope-by-parent in the E2E tests.

3. **`header-nav-item-{{ loop.index }}` testids in `_header.html`** (also flagged in Task 0.3 review). Stable today because the `nav_items` list is a fixed literal, but order-dependent. Phase 3 admin/header E2E should target by parent + index OR refactor to explicit testids. Not blocking Phase 2.

4. **`admin-helpers-page-action-{{ loop.index|default }}` macro testids** in `_admin_helpers.html`. Each calling page only has one such action so no within-page collision, but the testid isn't descriptive. Phase 3 admin tests will need careful selector scoping (use the page-prefix locator).

5. **`admin-logs-view-${index}` uses array index, not log id.** Flaky if log table reorders. Phase 3 admin/logs E2E should sort or pick first row.

6. **`scripts/generali-import/*.xml`** untracked files exist at the repo. They appear to be intentional (XML scripts for the Generali import pipeline) but aren't yet committed. Decide whether to commit or remove before Phase 2 starts — pre-commit hook intermittently auto-stages them.

7. **System Python ≠ venv Python.** The pre-push gate uses system Python via PATH. After this session, system Python has `pytest-cov` and `defusedxml` installed manually. Any rebuild of the dev box or any future dev-dep addition needs to be mirrored into system Python OR the pre-commit hook needs updating to point at `.venv\Scripts\python.exe`. Phase 2 might be a good time to fix the hook: `entry: .\.venv\Scripts\python.exe -m pytest tests …` — but watch for the WSL/Linux subagent that might not have the venv structure.

---

**Conventions Phase 2 should follow (matches Phase 1)**

1. **One task = one commit.** Don't pile multiple module tests into one commit; each ratchet of `MIN_COVERAGE` belongs with its module's tests.
2. **Commit title is `test(routes): cover <module>.py N routes (...)`.** Body lists the sections covered. gitlint requires a body; one-line titles get rejected.
3. **Each test file starts with a module docstring** noting any deviations from the "real DB" rule (which Phase 1 docstrings did consistently — Phase 2 is even more likely to need this).
4. **Use `admin_client` for routes with `admin.*` perms; `user_client` for routes that just need authentication; `noperm_client` for the 403 path.** Don't write fresh login flows per file.
5. **For routes hitting OctoDB / StatisticsDB / GeneraliDB**, use mocks. Those DBs aren't part of the TEST environment.
6. **Use `(200, 404, 403, 400)` tuple-matches** for routes that may or may not have data in TEST. Strict equality assertions on routes with unseeded data will be flaky.
7. **Ratchet `MIN_COVERAGE` in the SAME commit** as the test file landing. Round measured value down to the nearest 5.
8. **Run `.\.venv\Scripts\python.exe -m pytest tests/ -q --no-header 2>&1 | tail -2`** as the verification command (the full suite, no `-x`, so coverage.xml regenerates with cumulative data).

---

**What the next session should do (opening move)**

1. **Read this handoff** (you're here).
2. **`git status`** — clean up untracked clutter (`note`, `errDiv.remove()`, anything 0-byte at the root) before starting. Phase 1 commit hook hit a stash-and-restore issue with this once.
3. **Decide test-schema strategy:**
   - Option A (recommended): extend `sql/test/schema.sql` with Notifications + MaintenanceBanner + Chat_Messages + WorkitemTags + DashboardLayouts + IndexFieldMappings + ActivityInstancesToIgnore + Statconfig + ActivityInstanceToIgnore_Test (~150 lines of CREATE TABLE statements mirroring the prod schema), then re-run `scripts/test-db-reset.ps1`. About 30 minutes of work that unlocks ~30 currently-mocked tests in Phase 2.
   - Option B: keep mocking at the engine level. Faster per-test but lower fidelity.
   - The plan was written assuming Real-DB-everywhere but Phase 1 already had to back off. A pragmatic Phase 2 picks A for the most-touched tables and B for niche ones.
4. **Start Task 2.1 (`core.py`, 5 routes)** as the warm-up. Plan has all the anchor tests written out. Should take ~15 minutes for a careful pass.
5. **Continue through 2.2–2.9 in order**, then close with 2.10 (the endpoint-set assertion).

Total Phase 2 effort estimate: ~3-4 hours focused, depending on the test-schema decision. ~80 new tests landing.

---

**File index (Phase 1 deliverables)**

```
tests/unit/test_app_logging.py             6 tests   100%
tests/unit/test_cli.py                    63 tests    71%
tests/unit/test_cli_doctor.py             30 tests    65%
tests/unit/test_coverage_thresholds.py    24 tests   (the ratchet)
tests/unit/test_create_app.py             15 tests   (smoke)
tests/unit/test_db.py                     10 tests    87%
tests/unit/test_extensions.py             10 tests   100%
tests/unit/test_files.py                   5 tests   100%  (pre-existing)
tests/unit/test_hooks.py                  41 tests   100%
tests/unit/test_i18n.py                    8 tests   100%
tests/unit/test_maintenance.py            26 tests   100%
tests/unit/test_middleware.py              6 tests   100%
tests/unit/test_notifications.py           6 tests   100%
tests/unit/test_octo.py                   15 tests    99%
tests/unit/test_process_helpers.py        12 tests   100%
tests/unit/test_security.py               32 tests    82%  (3 pre-existing, 29 added)
tests/unit/test_translations.py            7 tests   (pre-existing)
tests/unit/test_users.py                   9 tests   100%

tests/integration/test_auth_flow.py        4 tests   (pre-existing — Phase 2 extends)
tests/integration/test_permission_guard.py 2 tests   (pre-existing)

tests/e2e/test_login_smoke.py              1 test    (pre-existing; Phase 3 extends)

tests/conftest.py                          (+53 lines — fixtures from Task 0.4)
tests/e2e/conftest.py                      (pre-existing — Playwright subprocess)
tests/README.md                            (new — Task 0.6)
```

Plan, threshold, fixtures, data-testid infrastructure all in place. Phase 2 is plug-and-chug from here.
