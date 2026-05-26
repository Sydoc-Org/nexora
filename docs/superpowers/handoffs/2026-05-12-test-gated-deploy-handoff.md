**Test-gated deploy — handoff for Batch B and beyond**

Date: 2026-05-12
Branch: `2.5.58`
Previous session: completed Batch A + Checkpoint A.

This file lets a fresh Claude Code session (or you) resume cleanly.

---

**Reading order for the resuming agent**

1. This file (you are here)
2. `docs/superpowers/specs/2026-05-12-test-gated-deploy-design.md` — what we're building and why
3. `docs/superpowers/plans/2026-05-12-test-gated-deploy.md` — the full 19-task plan
4. `CLAUDE.md` (project root) — git rules (never auto-commit), SQL workflow, response style

You don't need to re-read everything if context is tight. The plan + this handoff are sufficient; the spec is background.

---

**Status — what's done**

Batch A (Tasks 1-7) — committed by user, ready in working tree:

- `requirements-dev.txt` — pytest, pytest-html, pytest-playwright, pytest-rerunfailures, playwright
- `pyproject.toml` — pytest config (testpaths, JUnit + HTML reports to `test-results/`, `flaky_e2e` marker)
- `TEST.env.example` — committed; `TEST.env` is on the user's machine, gitignored
- `sql/test/schema.sql` — full mirror of nexora auth subset
- `sql/test/seed.sql` — 3 test users with real bcrypt hashes, pinned TOTP secrets
- `environment_transfer_queries.tmp.sql` — NEXORA_TEST + scoped login block (gitignored; the user ran it manually)
- `scripts/test-db-reset.ps1` — applies schema + seed via sqlcmd
- `tests/__init__.py`, `tests/conftest.py` — fixtures: `app`, `client`, `db_conn`, `totp_for`, `login`

Checkpoint A — done by user:

- NEXORA_TEST database exists with `nexora_test_user` login (scoped to NEXORA_TEST only)
- `TEST.env` exists at repo root with real connection values
- `requirements-dev.txt` installed
- Playwright chromium installed
- `scripts\test-db-reset.ps1` ran successfully
- `python -m pytest --collect-only` exits cleanly

---

**Reality-check deltas from the plan (already applied to the code that exists, but the PLAN doc has not been updated)**

When following the plan for Batch B/C, be aware of these things the plan got slightly wrong because they were discovered during execution:

- Auth flow endpoint is `/verify_2fa` (UNDERSCORE, not hyphen). Login template is `index.html` not `login.html`.
- Bcrypt hash column type is `NVARCHAR(255)` (string), not `VARBINARY`.
- Real `nexora` schema uses `AccessProfile` + `AccessProfilePermission` + `UserPermissionOverride` + `fnUserHasPermission`. Permissions are resolved through `dbo.spGetUserPermissions(@UserID)` which calls the function. Seed grants permissions via `AccessProfilePermission` (Effect='A'), not via a flat `UserPermissions` table.
- `.gitignore` already excludes `*.env`, `htmlcov/`, `test-results/`, `docs/`, and `environment_transfer_queries.tmp.sql`. No edits needed.
- Login uses these form fields: `username`, `password`. 2FA form uses field name `code`.
- The login flow has gates: if `InitReset=0` → redirect to `/init_reset`; if `twoFA=0` → redirect to `/init_2FA`; else → `/verify_2fa`. Seed users all have `InitReset=1` and `twoFA=1`, so they go straight to `/verify_2fa`.
- Login is rate-limited via `@limiter.limit("10 per minute")`. If tests do many login attempts, the limiter may trigger. The `conftest.py` `login` fixture is OK for round-1 volume.
- `python` is at `C:\Users\bes\AppData\Local\Programs\Python\Python313\python.exe`. There is no `./venv` in this checkout currently. If pre-push hook references `./venv/Scripts/python`, fall back to `python` (PATH) and update the hook installer accordingly OR ask the user whether to create a venv.

---

**Next batch — Batch B (Tasks 8-14): unit + integration tests**

Plan file: `docs/superpowers/plans/2026-05-12-test-gated-deploy.md`, search for the headings "Task 8" through "Task 14".

Goal: 5 unit tests (security, files) + 4 integration tests (auth flow, permission guard) all passing locally.

Order:

1. **Task 8** — `tests/unit/__init__.py` + `tests/unit/test_security.py` with `test_has_permission_returns_true_when_present`. Patch `nx_lib.security.session`.
2. **Task 9** — append two more security tests: `_returns_false_when_missing`, `_returns_false_when_no_permissions_in_session`. Run `pytest tests/unit -v`, expect 3 passed.
3. **Task 10** — `tests/unit/test_files.py` with 5 tests for `is_file_allowed`. Use the inline PDF/PNG byte sequences from the plan. Run `pytest tests/unit -v`, expect 8 passed.
4. **Task 11** — `tests/integration/__init__.py` + `tests/integration/test_auth_flow.py`. First test: `test_login_page_renders` — `client.get("/login")` returns 200 and body contains a form.
5. **Task 12** — append `test_login_valid_creds_and_2fa`. Use the `client` and `totp_for` fixtures from conftest. Confirm session is set after `/verify_2fa`.
6. **Task 13** — append `test_login_bad_password_rejected` and `test_login_unknown_user_rejected`. Run full integration: 4 tests passed.
7. **Task 14** — `tests/integration/test_permission_guard.py`. `ADMIN_ROUTE = "/admin"`. Two tests: `noperm@test.local` GET returns 403; `admin@test.local` GET returns 200 or 302.

End of Batch B: full run `python -m pytest tests -v` should report 12 passed (8 unit + 4 integration). NO E2E yet.

Verification commands at end of Batch B:

```powershell
python -m pytest tests -v
```

Expected: 12 passed in test-results/junit.xml.

---

**Checkpoint B — what the user does after Batch B**

- Review the diff and commit Batch B's files.
- Confirm tests pass on their machine (the resuming agent will have already verified via pytest run, but the user reviews the final state).

---

**Batch C (Tasks 15-18): E2E + hooks + CI**

1. **Task 15** — `tests/e2e/__init__.py`, `tests/e2e/conftest.py` (subprocess fixture starting `nx_main.py` on port 8765), `tests/e2e/test_login_smoke.py`. Marker: `@pytest.mark.flaky_e2e`.

   Subprocess fixture starts `python nx_main.py` with `FLASK_RUN_PORT=8765`. `nx_main.py` currently hardcodes port 8000 — the fixture needs `nx_main.py` to read `FLASK_RUN_PORT` env var, OR the fixture invokes `flask --app nx_main run --port 8765`, OR (last resort) the fixture starts on port 8000 and the test expects that. Check `nx_main.py` and pick the least-invasive path.

   Selectors: `templates/index.html` login form has fields `username`, `password`. `templates/verify_2fa.html` has field `code`. Inspect both before writing selectors.

2. **Task 16** — `scripts/install-hooks.ps1`. Installs `.git/hooks/pre-push` that runs `pytest tests -q --reruns 2 --only-rerun flaky_e2e`. The plan's hook script references `./venv/Scripts/python` — if no venv exists, change to `python` (relies on PATH). Confirm with user before changing.

3. **Task 17** — `.github/workflows/deploy.yml`. Split into `test` + `deploy` jobs:
   - `on:` includes `push.branches: [main]` AND `pull_request.branches: [main]`
   - `test` job: checkout, pip install, playwright install, verify TEST.env, run `test-db-reset.ps1`, pytest with `--reruns 2 --only-rerun flaky_e2e`, upload `test-results/` artifact
   - `deploy` job: `needs: test`, `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`, original deploy steps
   - `robocopy` exclusions add `tests test-results` to `/XD` and `requirements-dev.txt pyproject.toml` to `/XF`

   Runner-side one-time setup needed: `TEST.env` provisioned at `C:\sydoc\runner-secrets\TEST.env` (or wherever) with a step that copies it into the workspace. Plan describes this in Task 17.2.1.

4. **Task 18** — Append "Running tests" section to `README.md`. Plan has the exact markdown.

End of Batch C: full local run passes (13 tests: 8 unit + 4 integration + 1 e2e). `deploy.yml` parses (`python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`).

---

**Task 19: CI gate verification (user-driven, on a PR)**

After Batch C is committed and merged via PR:

1. PR opens → `test` job runs → confirm green → confirm `deploy` is skipped (correct; deploy only on push to main).
2. Push an intentionally failing test to the same PR (no-verify the local hook to let it through). Watch `test` fail, deploy skipped, PR check red.
3. Remove the failing test, push, watch green.
4. Merge PR → push to main triggers `test` + `deploy`. Deploy succeeds.

The plan has the exact commands in Task 19, steps 19.1 through 19.6.

---

**Operating rules for the resuming agent**

- NEVER auto-commit. After each task, surface the diff (`git status --short` + `git diff`) and stop. The user runs all git operations.
- Use `AskUserQuestion` for yes/no and multi-choice prompts.
- Use bold text for section breaks, not `#`/`##`/`###` markdown headers.
- New SQL that needs to be applied to a real environment goes into `environment_transfer_queries.tmp.sql` with `--claudes new sql statement:` header. The user runs it.
- If a UI-reachable change is being tested, drive Playwright yourself rather than asking the user to verify in a browser.
- Don't leave `$env:X = "Y"` set without restoring.
- Screenshots → `screenshots/`, never repo root.
- Restart the Flask dev server after template edits (Jinja template cache is process-lifetime).

---

**Quick-start command for the resuming agent**

When the user says "continue Batch B" (or similar), do this:

1. Read this handoff file and the plan.
2. Invoke the `superpowers:executing-plans` skill.
3. Set up tracking with `TaskCreate` for Batch B, Batch C, Task 19 (matching the structure of this handoff).
4. Mark Batch B in_progress.
5. Start Task 8 — write `tests/unit/__init__.py` and the first security test.
6. Work through to Task 14, then stop and surface diffs for Checkpoint B.

If anything in the plan contradicts the deltas listed in this handoff, the handoff wins (it's based on the actual code state).
