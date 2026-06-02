**Test expansion — handoff (Phase 3 complete, Phase 4 / PR next)**

Date: 2026-06-02
Branch: `feature/2.5.62`
Topic keyword: **test-expansion**
Plan: `docs/superpowers/plans/2026-06-01-test-expansion.md`
Tests: **532 → 602** (+70 E2E across Phase 3, all passing locally)

To resume: "read the phase 3 complete handoff" → land here → next move is **push the Phase-3 commits** (if not already pushed) and then choose: open the bundled PR (Phase 0/1/2/3) OR draft the Generali Phase-2 plan.

---

**Reading order for the resuming agent**

1. This file.
2. `docs/superpowers/handoffs/2026-06-01-phase2-complete-handoff.md` — Phase 2 background/lessons still apply.
3. `docs/superpowers/plans/2026-06-01-test-expansion.md` — Phase 3 tasks at lines ~3156-3861; Phase 4 close-out at ~3865+.
4. `tests/e2e/conftest.py` — the E2E fixtures. **Phase 3 made three load-bearing changes here (see lessons #1-#3).**
5. `tests/README.md` — fixtures, patterns, run commands.

---

**Status — Phase 3 commits on feature/2.5.62 (14 commits)**

| commit | what |
|---|---|
| `24b508e` | fix(auth): TOTP `valid_window=1` on verify (clock-skew + E2E de-flake) |
| `70ef3bb` | test(e2e): wire flaky_e2e reruns + disable rate limit for the browser subprocess |
| `cbd4eb4` | test(e2e): seed TestAdmin with ALL non-generali permissions |
| `5d8ef73` | docs(gitnexus): refresh auto-generated index metadata (incidental) |
| `6a5f4a6` | test(e2e): fix server pipe deadlock + add `_e2e_page_setup` / `seed_user_ids` |
| `e022c1e` | test(e2e): auth pages (10) |
| `b5c5494` | test(e2e): header (8) |
| `7d3710f` | test(e2e): dashboard (3) |
| `9754511` | test(e2e): workitems (5) |
| `22ef7b4` | test(e2e): invoices (4) |
| `fc3f46c` | test(e2e): chat (4) |
| `8a73c58` | test(e2e): profile (6) |
| `f486ea7` | test(e2e): admin pages (21) |
| `d651ec2` | test(e2e): misc pages — hero/jdvance/maintenance/404 (7) |
| `b20d871` | test(e2e): cross-browser login smoke (2) |

**70 new E2E tests** + the 1 pre-existing smoke = **71 E2E tests, all passing** (~200s, one server boot). Full suite (unit+integration+e2e) = **602 passing**.

---

**Things learned in Phase 3 (don't relearn)**

**1. The E2E server deadlocked on an undrained stdout PIPE.** `nexora_server` spawned `nx_main.py` with `stdout=PIPE, stderr=STDOUT` but never read the pipe. The app logs an ERROR on **every** request (the `MaintenanceBanner` table is absent in TEST → the maintenance before_request check logs and continues). After ~a handful of requests the ~64KB OS pipe buffer fills, the server **blocks on its next log write, and hangs** — every subsequent request times out. The single-test `test_login_smoke` never hit it; any multi-test run always did. **Fix (commit `6a5f4a6`):** stream the subprocess output to `var/test-results/e2e-server.log` instead of an unread PIPE. This was the single biggest blocker — symptoms looked like flaky selectors but were a fixture bug.

**2. CDN-loaded assets make `load`/`networkidle` waits unusable.** Every page pulls tailwind (`cdn.tailwindcss.com`), font-awesome (cdnjs) and Inter (google-fonts) from external CDNs. `page.goto` defaults to `wait_until="load"`, which blocks on those fetches → intermittent 15-30s timeouts (e.g. `/login` passed but `/forgot_password` timed out — pure CDN timing). **Fix:** `_e2e_page_setup` autouse fixture monkeypatches `page.goto` to default `wait_until="domcontentloaded"` and sets an 8s default timeout. Element assertions (`expect(...).to_be_visible()`) then auto-wait for tailwind to apply. **Never wait for `networkidle` on these pages** — the session-heartbeat poller means it never settles.

**3. The plan's `data-testid` names were aspirational — the real ones differ.** ~50 selectors in the plan don't exist. Reality (examples): dashboard has only `dashboard-process-filter` (no `dashboard-filter-button`/`-modal`/`-root`); there is no `header-chat-link` or `header-language-switch` (chat is a `header-nav-item-N`, language lives on the profile page as `profile-lang-{en,de,fr,it}`); the org "add" button is `admin-helpers-page-action-1` (not `admin-org-add`); user detail's force-logout is `admin-userdetail-sign-out-all`; profile submits are `profile-save-changes` / `profile-update-password`. **Always extract real testids from the rendered DOM** (a logged-in probe dumping `data-testid` values), not from the plan.

**4. Seed users couldn't reach most pages — E2E can't monkeypatch.** The in-process suite uses an `admin_all_perms` fixture that monkeypatches `has_permission`. The E2E subprocess can't be monkeypatched, and the seed `TestAdmin` only had `admin.view` + `admin.users.manage` + `dashboard.view` → 403 on workitems/invoices/chat/jdvance and every `/admin` sub-page. **Fix (commit `cbd4eb4`):** seed the full non-generali permission set and grant all of it to `TestAdmin`. `TestUser` (dashboard.view only) and `TestNoPerm` (none) are unchanged so the Phase-2 403 guards still hold. **Anyone running E2E after pulling must re-run `python scripts/test_db_reset.py`** to pick up the expanded seed.

**5. Use the real route paths, not the discovery agents' guesses.** Admin overview is `/admin` (not `/admin/dashboard`); access control is `/admin/access_control` (underscore, not `/admin/access-control`); user detail is `/admin/users/<int:id>` (there is no `/admin/user_detail_search`). User ids come from an IDENTITY reseed, so the `seed_user_ids` fixture queries them rather than hard-coding.

**6. `flaky_e2e` was a decorative marker.** There was no `--reruns` in addopts, so it did nothing for local runs. A `pytest_collection_modifyitems` hook in the e2e conftest now applies `pytest.mark.flaky(reruns=2)` to flaky_e2e items (scoped to E2E so unit/integration still fail fast). The pre-push gate independently passes `--reruns 2 --only-rerun flaky_e2e`.

**7. Modals are hidden forms revealed by JS.** `admin-maintenance-form`, `admin-org-modal-form`, `chat`'s new-conversation modal, the workitems export modal, etc. are present-but-hidden until their trigger fires (`classList.remove('hidden')`). Render tests assert an always-visible landmark (e.g. a toolbar input); modal tests click the trigger then assert the revealed element is visible, and close it again.

**8. Commit hygiene cost real time.** Three independent snags stacked up: (a) the `mixed-line-ending` hook kept rewriting `seed.sql` (CRLF from the Edit tool) — the **staged** copy must be LF, so normalize and re-`git add`; (b) gitlint enforces body lines ≤100 chars — `-m "<long line>"` fails, use a wrapped here-doc body; (c) a concurrent GitNexus re-index dirtied `AGENTS.md`/`CLAUDE.md` mid-commit, conflicting with pre-commit's stash/restore. Keep the tree clean (commit or normalize stray/auto-generated files first), normalize LF, wrap commit bodies.

---

**Decisions in force (Phase 3)**

| Decision | Value |
|---|---|
| Default E2E user | `admin@test.local` (omnipotent after the seed change); `user@test.local` only for permission-differentiation (e.g. admin-nav-hidden); `noperm@test.local` unused in E2E |
| Navigation | `domcontentloaded` + element assertions; never `load`/`networkidle` |
| Timeouts | 8s default, 15s navigation (in `_e2e_page_setup`) |
| Data-absent pages | tolerant assertions — page renders / no 500 / landmark present, not data rows |
| Selectors | `data-testid`, extracted from the rendered DOM |
| Destructive controls | open the confirm modal then **cancel** — never confirm against seed data |
| Commit convention | `test(e2e): cover <flow> (...)`, one task = one commit, gitlint-conformant wrapped body |

---

**Open caveats carrying forward**

1. **Pre-push gate now runs 71 E2E tests via SYSTEM python** (`python -m pytest tests --reruns 2 --only-rerun flaky_e2e`). System python has playwright + pytest-playwright and the browsers live in the user profile, so it works — but the gate is now ~5-6 min longer (server boot + browser runs). Budget for it.
2. **E2E needs the TEST DB reseeded.** After pulling, `python scripts/test_db_reset.py` must run so `TestAdmin` has the full permission set. Without it, admin-driven E2E tests 403.
3. **CDN dependency.** Visibility assertions rely on tailwind loading within 8s. Fully offline runs may flake on the few tests that assert on tailwind-applied `hidden` state.
4. **Cross-browser is opt-in.** `test_cross_browser.py` runs chromium only by default; pass `--browser firefox --browser webkit` for the matrix.
5. **Coverage thresholds unchanged.** E2E exercises a subprocess, so it does not move `coverage.xml` / `test_coverage_thresholds.py`. The view modules' coverage figures are still from the integration tests.
6. **SAWarning still present** (1 warning), unchanged from Phase 2.

---

**What the next session should do (opening move)**

1. Read this handoff.
2. `git push origin feature/2.5.62` if not already pushed — the pre-push gate runs the full suite incl. E2E (~8-10 min total). Confirm 602 pass.
3. **Decide direction (AskUserQuestion):**
   - Open the bundled PR now (Phase 0/1/2/3 — ~65 commits of test expansion).
   - Draft the Generali Phase-2 test plan (separate, ~25 tasks).
   - Phase 4 close-out: verify the deploy test-gate (plan Task 4.1) and final coverage table (Task 4.2).

---

**File index (Phase 3 deliverables)**

```
tests/e2e/test_auth_pages.py        10 tests
tests/e2e/test_header.py             8 tests
tests/e2e/test_dashboard.py          3 tests
tests/e2e/test_workitems.py          5 tests
tests/e2e/test_invoices.py           4 tests
tests/e2e/test_chat.py               4 tests
tests/e2e/test_profile.py            6 tests
tests/e2e/test_admin.py             21 tests
tests/e2e/test_misc_pages.py         7 tests
tests/e2e/test_cross_browser.py      2 tests
tests/e2e/test_login_smoke.py        1 test  (pre-existing)

tests/e2e/conftest.py               +pipe-deadlock fix, _e2e_page_setup, seed_user_ids
nx_lib/views/auth.py                 TOTP valid_window=1 (both verify paths)
nx_lib/extensions.py                 NEXORA_DISABLE_RATELIMIT honoured in init_app
sql/test/seed.sql                    full permission set + TestAdmin grants all
```

70 new E2E tests landing. Phase 3 complete.
