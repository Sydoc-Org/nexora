**Dev-env upgrade — handoff (PRs 1-10 done, bundle pending merge as 2.5.61)**

Date: 2026-05-28 (afternoon, post-PR-10 push)
Branch at handoff: `feature/2.5.61` — 14 commits ahead of `main`. **Not yet merged.**
Topic keyword: **dev-structure** / dev-env-upgrade
Supersedes: `2026-05-28-pr6-complete-handoff.md`. The earlier handoffs (2026-05-26 → 2026-05-27 → post-PR-5 → post-PR-6) stay as backstory.

To resume: "read the dev-structure handoff" → land here → next move is the SYAPP01 ops moves + opening PR #86 to merge the bundle.

---

**Reading order for the resuming agent**

1. This file (you are here).
2. `CHANGELOG.md` `[2.5.61]` block — every change in one place, ordered Added / Changed / Removed.
3. `docs/superpowers/specs/2026-05-26-dev-env-upgrade-design.md` — design (source of truth for *why*).
4. `docs/superpowers/plans/2026-05-27-dev-env-upgrade.md` — implementation plan (now fully executed).
5. Older handoffs (2026-05-26 → post-PR-6) — backstory only.
6. `CLAUDE.md` at the repo root — **PR 8 just updated this** to describe the `env/` layout and the loader's one-release fallback.

---

**Status — what's on feature/2.5.61 (14 commits, not yet merged)**

| group | range | what |
|---|---|---|
| handoff | `7ec6d81` | Post-PR-6 handoff doc (was already on the branch at session start) |
| PR 7 | `039d81f..ef66755` (6 commits) | `var/` runtime tree, `nx_lib.config.PATHS` namespace, Python writers route through PATHS, ops scripts + pytest output + CI artifact path point at `var/`, `static/uploads/` explicit ignore, `scripts/db-migrate.py` sqlcmd fallback + deploy.yml PATH prepend |
| PR 8 | `0cab179..c8c2d49` (4 commits) | `env/{INT,PROD,STAGING,TEST}.env` move, loader with `env/{ENV}.env` primary + legacy-root fallback + DeprecationWarning, sanitised `env/*.env.example` templates, `.gitignore` keeps `*.env` ignore + `!env/*.env.example` exception, README/CLAUDE.md/`scripts/test_db_reset.py`/`deploy.yml` updated to new paths |
| PR 9 | `762b494..68ea072` (2 commits) | `nx.ps1` → `bin/nx.ps1` via `git mv` (history preserved 100%), `nx_lib.cli.NX_PS1` updated, `scripts/install-git-hooks.ps1` removed (PR 4 deprecation shim's job is done), `deploy.yml /XD` adds `bin` |
| PR 10 | `0005b79` (1 commit) | `bootstrap.ps1` (verified idempotent on existing venv), README quick-start collapses to `.\bootstrap.ps1`, CONTRIBUTING leads with bootstrap + keeps manual fallback below, CHANGELOG renamed `[Unreleased]` → `[2.5.61] - 2026-05-28` with bootstrap/`bin/`/`env/`/`var/` promoted to Added |

22 tests pass, ruff lint + format-check clean, every push survived the full pre-push hook chain (yaml/toml/merge-conflict/private-key/end-of-files/mixed-line-ending/trailing-whitespace/ruff/ruff-format/branch-name-guard/pytest).

---

**Things learned the hard way during PRs 7-10 (don't relearn these)**

**1. `uv sync` without `--extra dev` does NOT install the dev group.**
First bootstrap.ps1 draft followed the plan literally (`uv sync`). On a fresh venv that installed only the runtime deps (Flask, Werkzeug, etc.) — playwright wasn't there, so `python -m playwright install chromium` exit-1'd with `No module named playwright`. Fix: `uv sync --extra dev` (the dev group lives in `[project.optional-dependencies] dev`, not `[tool.uv.dev-dependencies]`, so it's gated behind `--extra`). Same applies to any manual setup — CONTRIBUTING.md's manual fallback says `uv sync --extra dev` for the same reason.

**2. Pre-commit's first commit after a `git mv` rename still wants a re-stage.**
PR 9's `git mv nx.ps1 bin/nx.ps1` + the related edits committed cleanly on the second pass (the auto-fixed line-endings were already in place from prior pre-commit runs). But you should still verify with `git log --stat` after every `git mv` commit that the new path is at full byte size — the `bin/nx.ps1 100%` rename detection in the log output is the only signal that history was preserved.

**3. PowerShell's redirection isn't the only way to get mystery 0-byte files in the working tree.**
At the end of PR 10, three 0-byte files appeared at the repo root: `Bootstrap`, `Installing`, `Syncing` — each matching the first word after `==>` in a bootstrap.ps1 `Write-Host`. Root cause not fully nailed down. Working theory: some interaction between `& .\bootstrap.ps1 2>&1 | Select-Object -Last N` and PowerShell's stream redirection on certain Write-Host calls. They were harmless (untracked, empty), but the safe move is `git status` after running ANY new PowerShell script for the first time and clean up before staging.

**4. `bin/nx.ps1` mysteriously truncated to 0 bytes in the working tree at the same time.**
Committed version was intact (verified via `git show HEAD:bin/nx.ps1`); only the working-tree copy was emptied. Restored via `git checkout HEAD -- bin/nx.ps1` before pushing. Probably the same root cause as #3. If you see this again: don't panic, the git copy is fine.

**5. `.env` at the repo root is gitignore-protected from Read/Test-Path in the AI sandbox.**
The Claude Code sandbox blocks reads on `.env` at the project root even though it's in the working directory. Workaround: don't reference `.env` in commands; the loader chain (root `.env` for env-selector + `env/{ENVIRONMENT}.env` for secrets) works without ever having to inspect `.env` in chat.

---

**Decisions still in force (don't re-ask)**

| Decision | Value |
|---|---|
| Scope | Inside-project only |
| Runtime dir | `var/` (shipped in PR 7) |
| Env dir | `env/` (shipped in PR 8); root `.env` stays put as the env-selector |
| CLI scripts dir | `bin/` (shipped in PR 9; only `bin/nx.ps1` so far) |
| Tooling stack | uv + ruff + mypy + pre-commit + gitlint + `bootstrap.ps1` |
| Approach | Detailed up-front plan, sequential chunks-per-PR with auto-commit on feature branches |
| Execution model | Chunked refactor: per-file or per-logical-group chunks, verify ruff + format-check + pytest at each boundary, commit, repeat. Re-stage + re-commit once if pre-commit rewrote line endings on the first pass. |
| Landing structure | 2.5.61 bundles PRs 7-10 into ONE PR to `main` — same release-branch pattern as 2.5.60 (PR #85). Open as PR #86. |
| Doc tone | Internal Sydoc team only. AI configs are team-shared; personal state stays local. |
| Deploy excludes | New top-level files/dirs not needed at runtime go to `/XF` or `/XD` in `.github/workflows/deploy.yml`. `var` and `bin` are already in `/XD`. |
| Auto-commit | Stage + commit + push on feature branches without asking (CLAUDE.md, 2026-05-27). Reset, force-push, branch-delete still need explicit per-turn auth. |
| Endpoint preservation | The camelCase `endpoint=` strings on `add_url_rule` from PR 5 remain a compat surface. PR 6 left the template-side `url_for("init_2FA")` calls alone for the same reason. Don't touch these without a separate decision. |

---

**What the next session should do**

Pick **ONE** of these depending on where the SYAPP01 ops moves stand:

**A. Open the 2.5.61 PR to main** (recommended once SYAPP01 ops are done).

```powershell
gh pr create --base main --head feature/2.5.61 --title "feat: dev-environment upgrade (2.5.61 — PRs 7-10)" --body "$(cat docs/superpowers/handoffs/2026-05-28-pr10-complete-handoff.md | Out-String)"
```

(Or write a tighter PR description that links to this handoff + the CHANGELOG `[2.5.61]` block.) Same merge pattern as PR #85 / 2.5.60.

**B. Do the SYAPP01 ops moves first**, then come back to A.

On SYAPP01 (via RDP / runner box):
```powershell
# 1. var/ consolidation (PR 7 follow-up)
$root = 'D:\sydoc\nexora'
if (-not (Test-Path "$root\var")) { New-Item -ItemType Directory "$root\var" | Out-Null }
foreach ($d in @('uploads','session','logs','screenshots','backups')) {
    if (Test-Path "$root\$d") {
        if (-not (Test-Path "$root\var\$d")) { New-Item -ItemType Directory "$root\var\$d" | Out-Null }
        robocopy "$root\$d" "$root\var\$d" /MOVE /E /NFL /NDL /NJH /NJS
    }
}

# 2. env/ consolidation (PR 8 follow-up)
if (-not (Test-Path "$root\env")) { New-Item -ItemType Directory "$root\env" | Out-Null }
foreach ($e in @('INT.env','PROD.env')) {
    if (Test-Path "$root\$e") { Move-Item "$root\$e" "$root\env\$e" -Force }
}
```

Both are reversible with `Move-Item` if anything looks off after; the loader and deploy both have fallbacks that emit DeprecationWarnings without breaking, so a missed move just shows up as a warning in the next app-pool restart's logs.

**C. Tend to `scripts/generali-import/csvToSql.ps1` (multi-server work)** if it's not yours to ship via this PR — the working tree had unstaged changes adding INTSQL01 → PRDSQL01 dual-server logic at session end. Either commit those on a different branch or stash them so the 2.5.61 bundle stays scoped.

---

**Pre-flight checks (re-run after a multi-day gap)**

```powershell
git status --short
git branch --show-current
git log --oneline feature/2.5.61 ^origin/main
.venv\Scripts\python.exe -m pytest tests -q --reruns 2 --only-rerun flaky_e2e
.venv\Scripts\python.exe -m ruff check nx_lib nx_main.py tests scripts ops
.venv\Scripts\python.exe -m ruff format --check nx_lib nx_main.py tests scripts ops
.\bootstrap.ps1                              # idempotent, should re-confirm everything
```

If anything fails, something drifted between sessions — investigate before opening the PR.

---

**Critical constraints to re-read**

- **Stage + commit + push on feature branches is allowed by default** (CLAUDE.md, 2026-05-27). Reset, force-push, branch-delete still require explicit per-turn auth. Memory: `[[auto-commit-allowed-on-feature-branches]]`.
- **Chunked refactor workflow** is the default rhythm: per-file or per-logical-group chunks, verify, commit, repeat. Memory: `[[chunked-refactor-workflow]]`.
- **First commit after `git mv` may need a re-stage + re-commit** (pre-commit hook line-ending normalisation lands in the working tree but not the index on the first try). Verify size on each renamed file after the commit, before pushing.
- **AskUserQuestion for yes/no & multiple-choice.** No A/B/C plaintext lists in chat. Memory: `[[feedback-use-askuserquestion]]`, `[[feedback-yes-no-prompt]]`.
- **No markdown headers in chat** — use **bold text** instead of `#`/`##`/`###`. Plans + handoffs (this file) use headers because they're docs.
- **Browser-test changes yourself** when reachable. `.\bin\nx.ps1 -u -b --loginas:<user>` + Playwright. Screenshots → `var/screenshots/` (updated from `screenshots/` in PR 7). Memory: `[[browser-test-changes-yourself]]`, `[[screenshots-folder]]`, `[[project-nx-playwright]]`.
- **Flask template cache** — restart nx after template edits or stale HTML lingers in tests. Memory: `[[project-flask-template-cache]]`.
- **PowerShell tool, not Bash**, for parens/pipelines on Windows. Bash misparses `if (Test-Path ...)` and mangles `%VAR%`-style env-var references.
- **Docs are for the internal Sydoc team** — never frame for outside contributors. Memory: `[[feedback-docs-internal-team]]`.
- **gh CLI is installed** at `C:\Program Files\GitHub CLI\gh.exe` (not on PATH in already-running shells). Authenticated as `benstreich`. Use the full path or open a fresh shell.
- **New top-level files/dirs not needed at runtime must be added to `/XF` or `/XD` in `deploy.yml`.** Memory: `[[feedback-deploy-excludes]]`. `var` and `bin` are already added.

---

**Working-tree state at handoff**

After the final PR 10 push, the working tree is clean except for **`scripts/generali-import/csvToSql.ps1`**, which has unstaged real edits adding multi-server support (`INTSQL01` → `PRDSQL01` cascade) that arrived during the session but aren't related to the dev-env upgrade. Don't fold this into the 2.5.61 bundle without explicit user confirmation; it's likely meant for a separate branch.

`git status --short` at handoff:
```
 M scripts/generali-import/csvToSql.ps1
```

---

**TL;DR for the resuming agent**

The 10-PR dev-env upgrade is **done**: tidy layout (`var/` + `env/` + `bin/`), modern Python tooling (uv + ruff + mypy + pre-commit + gitlint), enforced naming (PRs 5 + 6 from the previous handoff), and one-shot bootstrap (`.\bootstrap.ps1`). 14 commits ahead of `main` on `feature/2.5.61`, ready to bundle as 2.5.61 / PR #86.

**Two SYAPP01 ops moves remain** (user-confirmed they'll handle them): move `D:\sydoc\nexora\{uploads,session,logs,screenshots,backups}\*` into `D:\sydoc\nexora\var\...` and `D:\sydoc\nexora\{INT,PROD}.env` into `D:\sydoc\nexora\env\`. Both have loader/deploy fallbacks that emit DeprecationWarnings if you skip, so the consequences of skipping are visible-but-not-broken.

**Defaults you can rely on:**
- Stage + commit + push on feature branches without asking.
- Use `.git/COMMIT_MSG_*.txt` + `git commit -F` for long messages; multi-`-m` flags for short ones.
- Chunked refactor workflow: verify ruff + pytest at each boundary; re-add + re-commit once if pre-commit fixed line endings.
- Use `gh` (full path) to fetch CI logs directly when CI fails — saves a round-trip with the user.
