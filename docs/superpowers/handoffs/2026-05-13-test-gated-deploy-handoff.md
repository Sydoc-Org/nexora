**Test-gated deploy — handoff after Batch B + C + iteration**

Date: 2026-05-13
Branch: `2.5.58`
Previous handoff: `docs/superpowers/handoffs/2026-05-12-test-gated-deploy-handoff.md`

This continues the plan in `docs/superpowers/plans/2026-05-12-test-gated-deploy.md`. Reading just this file is enough; the previous handoff is historical.

---

**Reading order for the resuming agent**

1. This file (you are here)
2. `CLAUDE.md` — git rules (never auto-commit), SQL workflow, response style
3. `docs/superpowers/plans/2026-05-12-test-gated-deploy.md` — full plan, but most tasks are done; reference only

---

**Status — what's done**

Batch A (Tasks 1-7), B (Tasks 8-14), C (Tasks 15-18) are all committed on `2.5.58`. The user opened a PR; CI has been iterating through real-environment issues, all of which have been fixed.

Tests passing locally: **22** (8 unit + 6 integration + 1 e2e + 7 translation hygiene). Full suite runs in ~13s, ~30s including a fresh DB reset.

Recent commits on the branch:
- `4abd558` add test-gated deploy: e2e suite, pre-push hook, CI test job
- `c663401` add babel translation hygiene tests, unit test, nx cli improvements
- `9b520c4` fill all fuzzy/empty msgstr in de/fr/it, drop obsolete entries
- `358291d` silence pytest warnings: fix flask_caching cache type, ignore flask_limiter memory backend
- `bb334da` replace sqlcmd with pyodbc in test-db-reset (no client tools needed)

Plus uncommitted in working tree (waiting on user commit):
- `.gitignore` — added `!messages.pot` exception so messages.pot tracks
- `messages.pot` — newly trackable (was gitignored before)
- `.gitattributes` — new, silences LF/CRLF git warnings

---

**Important deltas from the original plan (already in code)**

These are choices that diverged from the plan during execution:

- **No `venv` in this checkout.** Pre-push hook uses `python` from PATH, not `./venv/Scripts/python`. Same for `scripts/test-db-reset.ps1` which prefers `D:\sydoc\tools\py\python.exe` (runner) but falls back to `python` on PATH.
- **`sqlcmd` is NOT a dependency.** `scripts/test-db-reset.ps1` is now a thin wrapper around `scripts/test_db_reset.py`, which uses pyodbc directly (pyodbc is already in requirements.txt → already installed in CI).
- **`messages.pot` IS committed.** The plan didn't address this; the translation hygiene test (`tests/unit/test_translations.py::test_pot_is_in_sync`) needs the committed `.pot` to compare against. The `.gitignore` has `!messages.pot` exception.
- **Translation hygiene tests added** beyond the original plan — `tests/unit/test_translations.py` has 7 tests: pot-in-sync + 3 locales × (all-translated + mo-up-to-date).
- **Auth flow endpoint is `/verify_2fa`** (UNDERSCORE), login template is `index.html` not `login.html`. Form fields: `username`, `password`, `code`. Seed users have `InitReset=1` + `twoFA=1` so login → `/verify_2fa` directly.
- **Bcrypt hash column** in NEXORA_TEST is `NVARCHAR(255)` (string), not `VARBINARY`.
- **flask_caching deprecation warning fixed** in `nx_lib/extensions.py:20` (changed `"simple"` → `"SimpleCache"`).
- **flask_limiter UserWarning suppressed** in `pyproject.toml`. Real production fix is documented as a TODO comment in `nx_lib/extensions.py:18-20` — under IIS FastCGI multi-worker, the in-memory rate-limit counter is per-worker, not global. Wire `storage_uri` to NexoraDB or Redis when ready.

---

**Known quirks / non-issues**

- **OneDrive evicts files in `sql/NexoraDB/`** periodically (the repo lives in OneDrive). The `pre-commit` hook regenerates them from INT every commit via `sql/sync-from-db.py`'s atomic swap. Looks alarming in `git status` but is self-healing. Fix at the OS level: right-click `sql/` → "Always keep on this device" in OneDrive settings.
- **LF/CRLF warnings on Windows** — silenced via the new `.gitattributes` (`* text=auto`). After committing `.gitattributes`, the user may want to run `git add --renormalize .` once to normalize existing files.

---

**What's left — Task 19: CI gate verification (user-driven)**

Plan reference: `docs/superpowers/plans/2026-05-12-test-gated-deploy.md` Task 19.

The user has been iterating on this. Latest known state: PR open, `test` job has hit and resolved:
- ✅ Playwright chromium missing — installed via `python -m playwright install chromium`
- ✅ sqlcmd not on runner — replaced with pyodbc
- ✅ messages.pot missing in CI workspace — un-gitignored
- ⏳ Whatever else surfaces on the next run

Once `test` is green on the PR:
1. Open a second PR (or push to same one) with an intentionally failing test to confirm the gate blocks.
2. Remove the failing test, confirm green.
3. Merge the original PR. The push-to-main triggers `test` + `deploy`. Deploy succeeds → IIS pool restarts with new code.

Runner provisioning that's required before this works (user is on the hook for this):
- `C:\sydoc\runner-secrets\TEST.env` on SYAPP01 (the self-hosted runner). The workflow copies it into `${{ github.workspace }}` each run.
- `D:\sydoc\tools\py\python.exe -m pip install -r requirements-dev.txt` (once)
- `D:\sydoc\tools\py\python.exe -m playwright install chromium` (once)
- NEXORA_TEST DDL on the shared SQL Server (already done — same server as user's local TEST.env).

---

**Operating rules for the resuming agent**

Standard project rules apply (from `CLAUDE.md` and user memory):

- NEVER auto-commit. After edits, surface the diff and **always include a suggested commit message** (user prefers short, lowercase, no scope prefix). The user runs all git operations.
- Use `AskUserQuestion` for yes/no and multi-choice prompts.
- Bold text for section breaks in chat, not `#`/`##`/`###` markdown headers.
- New SQL → `environment_transfer_queries.tmp.sql` with `--claudes new sql statement:` header; user runs manually.
- Browser-reachable changes → drive Playwright yourself rather than asking the user to verify.
- Restart Flask after template edits (Jinja template cache is process-lifetime).
- The repo is in OneDrive — never leave the user with a file in a state where OneDrive could lock it (e.g., open handles, half-written content).

---

**Quick-start if the user says "the PR test failed because of X"**

1. Look at the actual error if they pasted it; if not, ask for the log line.
2. Common failure classes you might see next:
   - **`No module named 'X'`** — missing dep on runner. Check it's in `requirements.txt` or `requirements-dev.txt`; if so the runner needs `pip install` re-run.
   - **`Login failed for user 'nexora_test_user'`** — runner's `TEST.env` has wrong `DB_PWD`, or the runner SQL Server isn't the one the user thinks.
   - **`No such column 'X'` in seed.sql** — `sql/test/schema.sql` and `sql/test/seed.sql` are committed; CI ran them. If schema doesn't match what tests expect, fix schema.sql + seed.sql + push.
   - **`/verify_2fa` failed** — TOTP secret in `seed.sql` doesn't match the one in `tests/conftest.py` `TOTP_SECRETS` map. They MUST match byte-for-byte.
   - **`pybabel extract` says new strings** — user added `_("foo")` to source without running `pybabel extract -F babel.cfg -o messages.pot . && pybabel update -i messages.pot -d translations && pybabel compile -d translations`. Translation hygiene gate working as intended.
3. Fix in code, run `python -m pytest tests -q --reruns 2 --only-rerun flaky_e2e` locally, surface diff + commit message.

---

**Files inventory (for orientation)**

```
tests/
  __init__.py
  conftest.py              # app, client, db_conn, totp_for, login fixtures
  unit/
    __init__.py
    test_security.py       # 3 tests for has_permission
    test_files.py          # 5 tests for is_file_allowed
    test_translations.py   # 7 tests: pot sync + per-locale translate/compile
  integration/
    __init__.py
    test_auth_flow.py      # 4 tests: login flow + bad creds
    test_permission_guard.py  # 2 tests: @require_permission allow/deny
  e2e/
    __init__.py
    conftest.py            # nexora_server subprocess fixture on port 8765
    test_login_smoke.py    # @flaky_e2e Playwright smoke

scripts/
  test_db_reset.py         # pyodbc-based DB reset (real logic)
  test-db-reset.ps1        # thin wrapper, picks python path
  install-hooks.ps1        # installs .git/hooks/pre-push

sql/test/
  schema.sql               # NEXORA_TEST DDL (mirrors real nexora)
  seed.sql                 # 3 test users with bcrypt hashes + pinned TOTP

.github/workflows/deploy.yml  # split into test + deploy jobs
pyproject.toml                # pytest config
requirements-dev.txt          # pytest, playwright, pytest-rerunfailures
TEST.env.example              # template for local TEST.env
.gitattributes                # line-ending normalization
messages.pot                  # NOW TRACKED (was gitignored before)
```
