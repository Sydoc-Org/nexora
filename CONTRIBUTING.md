# Contributing to nexora

Internal Sydoc project. Read this once before opening your first PR.

## Prerequisites

- Windows 10/11 with PowerShell 7+
- Python 3.13.9 (see `.python-version`)
- SQL Server access to `NEXORA_TEST` (test DB) and credentials for INT/PROD DBs
- A clone of the repo at a short path (e.g. `C:\dev\nexora`, **not** under OneDrive)

## One-time setup

Run the bootstrap script — idempotent, re-runnable, handles every step below:

```powershell
.\bootstrap.ps1                # default: INT environment
.\bootstrap.ps1 -Env STAGING   # if you target staging instead
```

Then follow the checklist it prints: edit your `env\*.env` files with real credentials, reset `NEXORA_TEST` via `.\scripts\test-db-reset.ps1`, and start the dev server with `.\bin\nx.ps1 -u`. The `nx` CLI does a lot more than start the server (status, logs, route listing, browser auto-login, `--doctor` preflight, an interactive TUI) — see `docs/howto/nx.md` for the full reference.

### Manual fallback

If bootstrap fails (or you want to know what it does), the manual steps are:

```powershell
# pip install uv   # only if `python`/pip already work reliably on your PATH.
# Windows' Microsoft Store "app execution alias" often shadows `python` with
# a stub that errors instead of running (even when a real install exists) --
# if `python --version` doesn't cleanly print a version, use the standalone
# installer instead, which needs neither python nor pip:
#   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
uv venv
uv sync
.venv\Scripts\python.exe -m playwright install chromium

copy env\INT.env.example env\INT.env       # then fill in real values
copy env\TEST.env.example env\TEST.env

.venv\Scripts\pre-commit.exe install --install-hooks
.venv\Scripts\pre-commit.exe install --hook-type commit-msg
.venv\Scripts\pre-commit.exe install --hook-type pre-push
```

The repo still ships `requirements.txt` and `requirements-dev.txt` (generated from `uv.lock`); they exist for the IIS deploy path on SYAPP01 (the deploy workflow runs `pip install -r requirements.txt` on the prod interpreter). Locally, bare `uv sync` is the whole setup — dev deps are a PEP 735 `[dependency-groups]` group that uv installs by default, so no `--extra` flag exists anymore.

**Adding a dependency.** `pyproject.toml` is the only source of truth. Never
hand-edit `requirements*.txt` — they are regenerated from `uv.lock` and your
edit is both silently discarded on the next export and invisible to `uv sync`,
so every other checkout gets `ModuleNotFoundError` while your machine keeps
working off an ad-hoc install. The correct sequence:

```
# 1. add to [project.dependencies] (runtime) or [dependency-groups].dev
uv lock
uv sync
uv export --format requirements-txt --no-hashes --no-dev -o requirements.txt
uv export --format requirements-txt --no-hashes          -o requirements-dev.txt
```

`tests/unit/test_dependencies.py` fails if `nx_lib/`, `scripts/` or `ops/`
imports a package that `pyproject.toml` does not declare.

## Type checking

`[tool.mypy]` in `pyproject.toml` applies `check_untyped_defs` + `strict_optional`
repo-wide; `disallow_untyped_defs` (every function fully annotated) arrives
per-module via `[[tool.mypy.overrides]]`, never as a single repo-wide flip. **A
module added to that overrides list never leaves it; new modules ship typed.**
Grow the list by picking an already-clean or small, contract-heavy module,
annotating it fully, adding its dotted path to the overrides `module` list, and
confirming `python -m mypy nx_lib nx_main.py` is still green.
## The shared test database

There is exactly one `NEXORA_TEST`, on `INTSQL01`, and CI and every developer's
local run share it. Both `scripts/test_db_reset.py` and CI's `test` job reset it, so two
overlapping runs used to corrupt each other: whichever started second re-seeded
`dbo.Users` under the one already going, and a random login fixture died with
`KeyError: 'userid'` or a stray 401 — a different test every time, always
passing in isolation, never pointing at the real cause (issue #235).

Runs now serialise on a SQL Server application lock (`scripts/db_lock.py`).
Both the reset script and the pytest session take `nexora_test_suite`
exclusively, so a second run **waits** instead of trampling:

```
[db-lock] another test run holds nexora_test_suite; waiting up to 20 min (pytest).
[db-lock] acquired after 47s
```

That wait is the feature — do not kill it. The lock is `@LockOwner='Session'`,
so a killed run releases it when SQL Server reaps the session; there is never a
stale lock to clear by hand.

| Variable | Effect |
|---|---|
| `NEXORA_TEST_LOCK_SKIP=1` | Don't lock at all. For when the lock itself is the problem. |
| `NEXORA_TEST_LOCK_TIMEOUT_MS` | Override the 20-minute wait before giving up. |

Skipping means you can corrupt someone else's in-flight run, and they cannot
tell it was you — so prefer waiting. A run that cannot reach the database
doesn't lock at all (it can't corrupt anything either), which keeps pure-unit
runs working offline.

Do not use elapsed time to judge whether a run was contended. A brief collision
reddens a suite without slowing it — the deploy that exposed this failed in
3m54s, inside the normal ~5m.

## Naming conventions

**Python:**
- Functions, methods, variables, module names: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE`
- Enforced via `ruff check --select N` (after PR 2)

**Templates (Jinja2):**
- Page templates: `snake_case.html` (e.g. `workitem_detail.html`)
- Paired JS partials: `templates/js/_<page>_js.html`
- Includes/partials: `_underscore_prefixed.html`

**SQL (documentation-only, not lint-enforced):**
- Tables: `PascalCase` (e.g. `Users`)
- Stored procs: `sp` + `PascalCase` (e.g. `spGetUserPermissions`)
- Functions: `fn` + `PascalCase`
- Migration files: `NNNN_short_snake_case.sql`

**Branches:** one short-lived topic branch per issue, cut from `main`. The
pre-push guard (`scripts/git-hooks/branch-name-guard.ps1`) only lets these
names push:
- `<type>/<slug>` — the topic branch. `<type>` is one of the Conventional-Commit
  types below; `<slug>` is lowercase-with-hyphens and should start with the
  issue number: `fix/253-collab-rules`, `feat/241-dashboard-overwork`,
  `docs/nx-cli-reference`.
- `v<x.y[.z[.n]]>` — **legacy** release-cycle and per-developer branches, still
  accepted so work already in flight can push. Do not cut new ones.
- `feature/<x.y.z>` — the pre-3.1 naming, same story.

Anything else is refused at push time.

**Commits — Conventional Commits:**
- `feat: <subject>` — new user-facing feature
- `fix: <subject>` — bug fix
- `chore: <subject>` — tooling, deps, no behaviour change
- `refactor: <subject>` — code restructure, no behaviour change
- `docs: <subject>` — documentation only
- `test: <subject>` — test-only changes
- `ci: <subject>` — CI/CD changes
- Optional scope: `feat(dashboard): …`
- Subject in imperative ("add X", not "added X")
- Body explains why

## Pull requests

- Target `main`. **Never push to `main` directly** — everything lands via PR.
  The pre-push hook refuses it (`git push --no-verify` bypasses, as always).
  That local guard is the enforcement, because GitHub's is not for sale here:
  the repo is private under the `Sydoc-Org` organization, which is on GitHub
  Free for organizations, where branch protection and rulesets are both
  unavailable (the API answers `403 Upgrade to GitHub Pro or make this
  repository public`). Upgrading the org to GitHub Team unlocks them; the day
  that happens, make the rule real server-side too (PR required, zero
  approvals, CI job `test` green, no force-push, no deletion, admins included):

  ```
  gh api -X PUT repos/Sydoc-Org/nexora/branches/main/protection --input - <<'JSON'
  {
    "required_pull_request_reviews": {"required_approving_review_count": 0},
    "required_status_checks": {"strict": false, "contexts": ["test"]},
    "enforce_admins": true,
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false
  }
  JSON
  ```

- **Review is optional, not required.** Once CI is green you may merge your own
  PR. Ask for a look when the change is risky or crosses someone else's area;
  do not sit blocked waiting for one.
- No tests run on push. CI runs the fast tier (unit + integration) on the **PR**
  and again on the merge commit that gates `deploy`. The e2e browser suite runs
  nightly on `main` and on demand (Actions → Deploy → Run workflow); a red
  nightly means revert or fix forward the next morning
- Keep PRs small and focused. The repo prefers many small PRs over one large one.
- Squash or merge, your call — but delete the branch after merging.

## Working in parallel

Two people, one auto-deploying `main`. The rules that keep merges cheap:

**One issue, one branch, one to two days.** Cut it from an up-to-date `main`,
merge it back, delete it. A branch that lives a week is not a branch, it is a
fork — split the work instead. Merge `main` into your branch daily (or rebase
if it is unpushed); the cost of a conflict grows with the square of how long
you let it sit.

**Claim before you collide.** These files are edited by everybody, so say what
you are taking in the issue before you write it:

| Hotspot | Rule |
|---|---|
| `sql/_migrations/<Db>/NNNN_*.sql` | Run `python scripts/db-migrate.py --dry-run` and post the number you are claiming in the issue **before** creating the file. Two people picking `0080` is the classic nexora conflict — and migrations are immutable once applied, so the loser renumbers by writing a new one. |
| `sql/<Database>/**` | Auto-generated dumps of INT. **Never hand-edit, never hand-merge.** On conflict take either side, then re-run `python sql/sync-from-db.py`. |
| `translations/*.po`, `messages.pot` | Same — regenerate with `/nx-i18n` rather than resolving hunks by hand. `pybabel` silently mangles malformed lines. |
| `CHANGELOG.md` `[Unreleased]` | Append at the **end** of your category, never in the middle. Conflicts here are always "keep both". |
| `docs/superpowers/handoffs/` | Date-prefixed filenames; two sessions never write the same one. |

**Stay out of each other's process.** Long refactors get their own git worktree
(`git worktree add`) so a `git stash` or a branch switch on one side cannot
sweep the other's uncommitted files. INT is shared: the pre-commit hook applies
your migrations to the live INT database the moment you commit, and `NEXORA_TEST`
serialises on an application lock (see above) — a waiting test run is correct
behaviour, not a hang.

## Releases

The version lives in exactly two places, `nx_lib/version.py` and
`pyproject.toml`, and `tests/unit/test_version.py` fails if they disagree.

A release is a **tag on `main`, not a branch**:

```powershell
# on a topic branch
#   1. bump __version__ in nx_lib/version.py and version in pyproject.toml
#   2. uv lock
#   3. promote CHANGELOG.md's [Unreleased] to "## [3.2.5] - YYYY-MM-DD"
# then PR it, merge, and tag the merge commit:
git switch main
git pull
git tag v3.2.5
git push origin v3.2.5
```

Deploy is not tied to the tag — **every** push to `main` deploys (see
`README.md`). The tag is a label on what shipped, so you can say "PROD is
running v3.2.5" and `git diff v3.2.4..v3.2.5` means something.
