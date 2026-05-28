**Dev-env upgrade — handoff (PRs 1-6 shipped, PRs 7-10 remaining)**

Date: 2026-05-28 (later morning, post-PR 6 merge to `main`)
Branch at handoff: `feature/2.5.61` — fresh off `main` at `64da121` (the merge commit of PR #85), zero commits ahead. `feature/2.5.60` is **deleted** locally and on origin.
Topic keyword: **dev-structure** / dev-env-upgrade
Supersedes: `2026-05-27-pr5-complete-handoff.md`. The earlier post-PR-4 and post-PR-5 handoffs stay as backstory.

To resume: "read the dev-structure handoff" → land here → it points you at PR 7.

---

**Reading order for the resuming agent**

1. This file (you are here).
2. `docs/superpowers/plans/2026-05-27-dev-env-upgrade.md` — implementation plan. PRs 1-6 are done; start reading at **§PR 7**.
3. `docs/superpowers/specs/2026-05-26-dev-env-upgrade-design.md` — design spec (source of truth for *why*).
4. Older handoffs (2026-05-26 → 2026-05-27 evening → 2026-05-27 post-PR5) — backstory only.
5. `CLAUDE.md` at the repo root — now tracked (was previously gitignored). Note the **2026-05-27 git rule change** allowing stage + commit on feature branches by default, the **2026-05-28 deploy-artifacts rule** about adding new top-level files/dirs to robocopy `/XF` `/XD`, and the **2026-05-28 gitnexus first-time setup** note.
6. `C:\Users\bes\.claude\projects\C--dev-nexora\memory\MEMORY.md` — user memory. Especially `[[auto-commit-allowed-on-feature-branches]]`, `[[chunked-refactor-workflow]]`, and `[[feedback-deploy-excludes]]`.

---

**Status — what landed in 2.5.60 (PRs 1-6, shipped to `main` via PR #85)**

PR #85 merged at 2026-05-28T08:20:23Z. Merge commit on `main`: `64da121`. Deploy ran clean once a sqlcmd-PATH issue on SYAPP01 was resolved (see "things learned" below). nexora is live on 2.5.60.

The 30 commits broke down as:

| group | range | what |
|---|---|---|
| PRs 1-4 (one batch) | `deb1173..858a547` (~5 commits) | Standard repo files, `pyproject.toml` source-of-truth for ruff, uv migration with `uv.lock`, pre-commit framework + gitlint, `nx --doctor` preflight. |
| PR 5 | `1a612c6..9f0532f` (11 commits) | Python identifier snake_case rename. `pageVisability` → `page_visibility` (typo fixed); the four DB engines + `getDBUrl`; `get_activityinstancesToIgnore`; four Generali handlers + `init_2FA` renamed Python-only with camelCase `endpoint=` preserved on `add_url_rule`. Ruff lint + format-check flipped from advisory to blocking. |
| PR 6 | `153e063..f2859b1` (9 commits) | Template snake_case rename. All 30 camelCase Jinja templates + their `{% include %}` / `render_template` callers. Highlights: admin pages, `nexoraLogo/` folder + file, `_errorBase.html`, all `_<page>JS.html` partials, hyphen-normalisation on `_generali-dashboardJS.html`. `messages.pot` + `.po` files re-extracted. |
| AI tooling team-share | `99759a7..8627582` (5 commits) | Publish project-level Claude Code config (`CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `.claude/settings.json`, `.claude/helpers/`, ruflo agents/commands/skills). Personal/runtime state stays gitignored. Deploy excludes added defensively. |
| CI ruff/CRLF fixes | `4518158..5a3b105` (3 commits) | See "things learned" below. |

---

**Things learned the hard way during PR 6 + the merge (don't relearn these)**

**1. Pre-commit hooks corrupt files on the *first* chunk after a `git mv` rename.**
Symptom: `git mv old.html new.html` + a paired `Edit` to a caller, then `git commit` → pre-commit's stash/restore cycle around the `mixed-line-ending` and `end-of-file-fixer` hooks lost the content of the renamed file, committing it as 0 bytes. Recovery: `git reset --soft HEAD~1`, restore content via the `Write` tool, re-stage, re-commit. The reliable workflow is: stage a chunk, `git commit -F .git/COMMIT_MSG_*.txt`, then **immediately re-run the same `git add -A && git commit -F ...` once** to absorb whatever the hooks rewrote on the first pass. Verify with `wc -c <file>` on each renamed file before pushing.

**2. The self-hosted runner had `.py` files cached with CRLF endings that predated `.gitattributes`.**
Five files (`nx_lib/i18n.py`, `tests/e2e/test_login_smoke.py`, `tests/integration/test_auth_flow.py`, `tests/integration/test_permission_guard.py`, `tests/unit/test_security.py`) were added 2026-05-12/13, just before commit `26011a3` introduced `* text=auto` + `*.py text eol=lf`. They got cached with Windows CRLF on the SYAPP01 runner's persistent workspace and `actions/checkout` never re-normalised them. ruff 0.7.4 + `format.line-ending = "lf"` then flagged them as needing reformat in CI while dev (LF) said `already formatted`. Fix: a `Normalize Python line endings to LF` PowerShell step in `deploy.yml` that walks `nx_lib`, `nx_main.py`, `tests` and rewrites CRLF→LF before ruff lint. The step is a no-op on a fresh clone; only matters for the stale runner workspace. Look at it in `.github/workflows/deploy.yml` (added in `5a3b105`). Don't remove it without re-checking the runner's working tree.

**3. The Windows runner had a `Show tool versions` step intentionally added.**
Lives between `Install Python deps` and `Ruff lint`. Prints `python --version` and `ruff --version`. Keep it — it would have saved an hour of "is CI using a different ruff?" guesswork.

**4. `pip install --quiet -r requirements-dev.txt` can silently no-op on the self-hosted runner.**
When a globally-installed ruff is already present at a different version, `--quiet -r` doesn't downgrade audibly. The deploy.yml install step now ends with `pip install --quiet --force-reinstall ruff==0.7.4` to guarantee the pinned dev ruff is what the runner uses. Pattern is worth applying for other tooling that the dev/CI parity depends on (mypy, gitlint, playwright).

**5. The deploy's PROD migration step needs `sqlcmd` on the *runner service*'s PATH, not your interactive PATH.**
On SYAPP01, `sqlcmd.exe` is at `C:\Program Files\SqlCmd\` and that dir IS on the System PATH. But when the GitHub Actions runner service was started, the System PATH didn't have it yet, so the service inherited a stale PATH and `shutil.which("sqlcmd")` in `scripts/db-migrate.py` returned `None` → `RuntimeError: sqlcmd not found on PATH`. Fix: **restart the runner service** on SYAPP01 (`Get-Service | ? Name -Match '^actions\.runner' | Restart-Service`). Same pattern applies any time something is added to System PATH on the runner host. If this keeps biting, the durable fix is to either (a) prepend the dir to `$env:PATH` in `deploy.yml`'s migration step, or (b) make `scripts/db-migrate.py`'s `find_sqlcmd()` fall back to common install dirs — see plan ideas at the bottom.

---

**Decisions still in force (don't re-ask)**

| Decision | Value |
|---|---|
| Scope | Inside-project only (no machine-wide, no multi-project) |
| Runtime dir target | `var/` (lands in PR 7) |
| Tooling stack | uv + ruff + mypy + pre-commit + gitlint |
| Naming scope | Python + templates + branch/commit (NOT SQL identifiers) |
| Approach | Detailed up-front plan, sequential PRs, dual-stage subagent review when scale warrants |
| Execution model | Chunked refactor workflow (memory `[[chunked-refactor-workflow]]`): per-file or per-logical-group chunks, verify (ruff + format + pytest), commit, repeat. Stage + commit on feature branches is allowed since 2026-05-27. |
| Doc tone | Internal Sydoc team only — never frame for outside contributors. AI configs are team-shared (`CLAUDE.md`, `.claude/settings.json`, `.claude/helpers/`); personal state stays local. |
| Deploy excludes | Any new top-level file/dir that isn't needed by the running Flask app must be added to `/XF` or `/XD` in `.github/workflows/deploy.yml`. Memory: `[[feedback-deploy-excludes]]`. |
| Landing structure | 2.5.60 bundled PRs 1-6 + AI tooling team-share + CI fixes into one PR (#85, 30 commits) — same release-branch pattern as 2.5.59. Default for 2.5.61 unless asked otherwise. |
| PR 7 ops follow-up | Before/at PR 7 merge: on SYAPP01, move existing runtime data into `D:\sydoc\nexora\var\...` or accept that new writes go to `var/` while old data stays at the root. |
| PR 8 hard pre-flight | Before PR 8 ships: `D:\sydoc\nexora\{INT,PROD}.env` must be moved to `D:\sydoc\nexora\env\`. The fallback in the config loader covers a missed move but emits a `DeprecationWarning`. |
| Endpoint preservation | The camelCase `endpoint=` strings on `add_url_rule` from PR 5 (`init_2FA`, `generali_additionalServices`, `generali_baseServices`, `generali_projectManagement`, `generali_importStatus`) remain a compat surface. PR 6 already left the template-side `url_for("init_2FA")` calls alone for the same reason. Don't touch these without a separate decision. |

---

**What the next session should do**

Pick up at **PR 7 — Consolidate runtime dirs under `var/`** (plan §PR 7).

**Pre-flight before starting PR 7:**

1. Confirm you're on `feature/2.5.61` and it's fresh: `git status --short && git log --oneline -3`.
2. `git pull --ff-only origin main` if `main` has moved since this handoff.
3. `npx gitnexus analyze` to refresh the index.
4. `.venv\Scripts\python.exe -m pytest tests -v --reruns 2 --only-rerun flaky_e2e` — expect 22 pass.
5. `.venv\Scripts\python.exe -m ruff check nx_lib nx_main.py tests scripts ops` — expect clean.

**Critical PR 7 specifics:**

- **Plan §PR 7 step 2 has an investigation gate:** `static/uploads/` vs root `uploads/` — figure out which is real before defining the `PATHS` constants. Don't skip this.
- **Touches `nx_lib/config.py` to introduce `PATHS` constants** for `session/`, `logs/`, `uploads/`, etc. Every place in the code that does `./session` / `./logs` / `./uploads` literally needs to go through `PATHS`.
- **CI artifact paths** (`test-results/`, screenshots) and the `ops/cleanup/` scripts (`csvLogs_toDB.ps1`, `cleanup_expired_sessionFiles.ps1`) reference these dirs. Update in lockstep.
- **`web.config` + `.gitignore`** also reference some of these. Search broadly with `Grep` (`logs/|session/|uploads/`) before chunk 1.
- **SYAPP01 ops follow-up needed before merge:** on the runner host, either move `D:\sydoc\nexora\{session,logs,uploads}` → `D:\sydoc\nexora\var\{session,logs,uploads}`, or accept the data-split. Ask the user which.

**PRs 7-10 — quick map (unchanged from previous handoff):**

- **PR 7** — Consolidate runtime dirs under `var/`. Touches `nx_lib/config.py` (new `PATHS` constants), ops scripts, CI artifact paths, pytest output paths. Investigate `static/uploads/` vs root `uploads/` first (plan §PR 7 step 2). **SYAPP01 ops follow-up needed before merge.**
- **PR 8** — Consolidate env files under `env/`. **Hard pre-flight on SYAPP01 first** (see decisions table). Commits `env/*.env.example` templates with sanitised placeholders.
- **PR 9** — Move `nx.ps1` → `bin/nx.ps1`. Delete `scripts/install-git-hooks.ps1` (the deprecation shim from PR 4). Ask user whether they have a PowerShell profile binding that pins `nx` at the repo root.
- **PR 10** — `bootstrap.ps1` one-shot setup. Idempotent. Closes the dev-env upgrade.

**Worth doing alongside PR 7 (small, decoupled, defer if no bandwidth):**

- **`scripts/db-migrate.py` sqlcmd fallback.** Right now `find_sqlcmd()` only checks `PATH`. Add a fallback list with `C:\Program Files\SqlCmd`, `C:\Program Files\Microsoft SQL Server\*\Tools\Binn`, `C:\Program Files (x86)\Microsoft SQL Server\*\Tools\Binn`. Prevents future runner-restart fire drills.
- **Same for `deploy.yml`**, prepend `C:\Program Files\SqlCmd` to `$env:PATH` in the migration step. Belt-and-suspenders.

---

**Pre-flight checks (re-run after a multi-day gap)**

```powershell
git status --short
git branch --show-current
git log --oneline -5
.venv\Scripts\python.exe -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
.venv\Scripts\python.exe -m ruff check nx_lib nx_main.py tests scripts ops
.venv\Scripts\python.exe -m ruff format --check nx_lib nx_main.py tests scripts ops
```

If pytest fails or ruff returns violations, something drifted between sessions — investigate before starting PR 7.

---

**Critical constraints to re-read**

- **Stage + commit + push on feature branches is allowed by default** (CLAUDE.md, 2026-05-27). Reset, force-push, branch-delete still require explicit per-turn auth. Memory: `[[auto-commit-allowed-on-feature-branches]]`.
- **Chunked refactor workflow** is the default rhythm: per-file or per-logical-group chunks, verify, commit, repeat. Use `.git/COMMIT_MSG_*.txt` + `git commit -F` for long messages; multi-`-m` flags for short ones. Memory: `[[chunked-refactor-workflow]]`.
- **First commit after `git mv` may need a re-stage + re-commit** (pre-commit hook line-ending normalisation lands in the working tree but not the index on the first try). Verify `wc -c` on each renamed file after the commit, before pushing.
- **AskUserQuestion for yes/no & multiple-choice.** No A/B/C plaintext lists in chat. Memory: `[[feedback-use-askuserquestion]]`, `[[feedback-yes-no-prompt]]`.
- **No markdown headers in chat** — use **bold text** instead of `#`/`##`/`###`. Plans + handoffs (this file) use headers because they're docs.
- **Browser-test changes yourself** when reachable. `nx -u -b --loginas:<user>` + Playwright. Screenshots → `screenshots/` (not repo root). Memory: `[[browser-test-changes-yourself]]`, `[[screenshots-folder]]`, `[[project-nx-playwright]]`.
- **Flask template cache** — restart `nx` after template edits or stale HTML lingers in tests. Memory: `[[project-flask-template-cache]]`.
- **PowerShell tool, not Bash**, for parens/pipelines on Windows. Bash misparses `if (Test-Path ...)` and mangles `%VAR%`-style env-var references.
- **Docs are for the internal Sydoc team** — never frame for outside contributors. Memory: `[[feedback-docs-internal-team]]`.
- **gh CLI is installed** at `C:\Program Files\GitHub CLI\gh.exe` (not on PATH in already-running shells). Authenticated as `benstreich`. Use the full path or open a fresh shell. Lets you fetch CI logs directly (`gh run view <id> --log`) instead of having the user paste them.
- **New top-level files/dirs not needed at runtime must be added to `/XF` or `/XD` in `deploy.yml`.** Memory: `[[feedback-deploy-excludes]]`.

---

**Working-tree state at handoff**

After the merge of PR #85 and the deploy, the working tree is clean. The only files that *might* still be modified are:
- `.git/COMMIT_MSG_PR6_chunk*.txt`, `.git/COMMIT_MSG_ci_*.txt` — temporary commit-message files. Should be gone; if any linger, just `rm` them.
- `.claude/helpers/notify-toast.log` — runtime log from the Stop-event toast hook. Gitignored, no impact.

`git status --short` should be empty (modulo the always-modified `.claude/` files via auto-memory).

---

**TL;DR for the resuming agent**

PRs 1-6 + AI tooling team-share shipped as **2.5.60** (PR #85, 30 commits, merged 2026-05-28). nexora is live with the new dev-env baseline + snake_case Python and templates. Resume at **PR 7 (consolidate runtime dirs under `var/`)** — plan `docs/superpowers/plans/2026-05-27-dev-env-upgrade.md` §PR 7 has step-by-step commands. Pre-flight: confirm you're on `feature/2.5.61` and it's fresh off `main`.

**Defaults you can rely on:**
- Stage + commit + push on feature branches without asking.
- Use `.git/COMMIT_MSG_*.txt` + `git commit -F` for long messages.
- Chunk per file / per logical group; verify ruff + tests at each boundary; commit; re-add + re-commit once if pre-commit fixed line endings on the first pass.
- Keep camelCase endpoint preservation from PR 5 intact in templates.
- Use `gh` (full path) to fetch CI logs directly when CI fails — saves a round-trip with the user.
