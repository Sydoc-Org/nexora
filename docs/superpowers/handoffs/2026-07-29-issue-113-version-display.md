# Handoff — Issue #113: version display, end to end

**Date:** 2026-07-29 · **Branch:** `feature/2.5.65` (136 commits ahead of `origin/main`) ·
**commit-only — owner pushes**
**Prior handoff:** `2026-07-28-reporting-ai-chat-glow-up-execution-complete.md`

## TL;DR

- **GitHub issue #113 ("Better Version Display then the html file") is closed.** Four commits: a
  deploy build stamp, the version moved into the profile dropdown, a stale `uv.lock` caught by a new
  drift test, and the marketing footer scoped to logged-out pages only.
- **All four verified in the running app**, not just green in tests — Playwright against
  `127.0.0.1:8000`, screenshots in `var/screenshots/issue113_*.png`.
- **One suite is red and it is NOT from this work:** `tests/unit/test_template_url_prefix.py` fails
  on `templates/js/_header_js.html` (owner's #118 switch-user). **This blocks `git push`** — the
  pre-push gate runs the full suite.
- **The owner was committing in parallel all session.** Two commits are mislabelled as a result
  (see "Gotchas"). Nothing was lost either way.

## This session's commits (oldest → newest)

Owner commits are interleaved on the same branch and are **not** listed here except where they
absorbed this session's work.

- `22c811d` feat(deploy): stamp the deployed commit into the footer
- `9cc5f39` chore(i18n): translation cycle for the switch-user and workitem strings
- `337498a` fix(version): cover the stale uv.lock copy with the drift test
- `c013e71` feat(header): show the version and build stamp in the profile menu
- `f384d3e` refactor(templates): scope the site footer to the logged-out pages

**Absorbed by an owner commit:** the `nexora_build` line in `nx_lib/hooks.py` and the #113 CHANGELOG
entry landed inside `2365f81 feat(header): add dev-only switch user button (#118)`, not in `22c811d`.
Functionally correct, just attributed to the wrong commit.

## What shipped

| # | Change | Key files |
|---|---|---|
| 1 | **Deploy build stamp.** `deploy.yml` writes `nx_lib/_build.py` (`BUILD_STAMP = "<sha7>, <UTC date>"`) immediately **after** the robocopy mirror (`/MIR` purges anything not in git). `version.py` imports it behind an `ImportError` fallback to `""`, so dev/INT stay version-only. Footer renders `nexora 2.5.65 · a1b2c3d, 2026-07-29`. | `.github/workflows/deploy.yml`, `nx_lib/version.py`, `nx_lib/hooks.py`, `templates/_nexora_version.html`, `.gitignore` |
| 2 | **Version in the profile dropdown.** 12 page templates never included the footer (reporting ×3, all 7 admin, `prepared_documents`, `maintenance`, `jd/jdvance`), so the newest surfaces showed no version at all. `_header.html` now closes the profile menu with version + build stamp. | `templates/_header.html`, `static/css/_header.css` |
| 3 | **uv.lock drift.** `uv.lock` sat at `2.5.63` while `version.py` and `pyproject.toml` were on `2.5.65` — a third copy nothing checked. `uv lock` refreshed it; `test_version_matches_uv_lock` now covers it. | `uv.lock`, `pyproject.toml`, `tests/unit/test_version.py` |
| 4 | **Footer scoped to logged-out pages.** Removed from the 13 templates that carry the sidebar; kept on `index`, `hero`, the password flows, 2FA and the error pages. Support mailto moved into the profile menu. New invariant test in both directions. | 13 page templates, `templates/_header.html`, `tests/unit/test_template_layout.py`, `CHANGELOG.md` |

Also: one pybabel cycle (`9cc5f39`) — de/fr/it come back **0 untranslated, 0 fuzzy, 0 altered**.
`messages.pot` was out of sync with the owner's #118/#125 strings and would have bounced the push.

## Next steps (ordered)

1. **Fix the red suite — blocks push.** `templates/js/_header_js.html:346` and `:357` build
   root-relative URLs (`'/dev/login/' + …`, `fetch('/dev/users')`). Route both through the
   `API_PREFIX` idiom. They are `{% if not is_prod %}`-gated so they cannot actually fire on PROD,
   but `test_template_url_prefix.py` scans statically and fails regardless.
2. **Decide on the `9cc5f39` mix-up** (see Gotchas). Leave it or split it; nothing is broken either way.
3. **Push** once (1) is green. Nothing has been pushed this session.
4. **Backlog agreed but not started**, in the order recommended: **(a)** app-wide dark-mode gray ramp
   (see Gotchas — real accessibility bug, live today); **(b)** remove the browser-runtime Tailwind CDN;
   **(c)** rename `_header.html` → `_base.html` across 23 includes + split the 701-line `_header.css`.
   No spec or plan file exists for any of them.

## Gotchas & notes

- **Two commits are mislabelled from parallel work.** `9cc5f39` (`chore(i18n)`) also contains the
  owner's `static/css/source-highlight.css`, `templates/js/_workitem_detail_panel_js.html` and
  `.claude/commands/issue.md` — they were staged between this session's `git add` and `git commit`.
  Symmetrically, `2365f81` swallowed this session's `hooks.py` change. Later commits used
  `git commit --only <paths>` specifically to stop this recurring.
- **The `pyproject.toml` version duplicate cannot be removed.** Both escapes were probed and both
  fail `uv lock --check`: deleting `version` → *"required `project.version` field is neither set nor
  present in `project.dynamic`"*; `dynamic = ["version"]` → needs a build backend, and nexora is
  `source = { virtual = "." }`, never built or installed. Comments in `pyproject.toml` and
  `nx_lib/version.py` record this. **Bumping a release = edit both files, then run `uv lock`.**
- **The dark-mode gray ramp is broken app-wide and is NOT fixed.** `static/css/_header.css:349-354`
  remaps the ramp; `text-gray-400 → #475569` measures **1.95:1** against the `#1e293b` menu surface —
  below even the 3:1 large-text floor. `text-gray-400` appears in 10+ templates (`hero`, `index`,
  `forgot_password`, six `generali_*`). Only the profile-menu element was fixed, via a
  higher-specificity override so it beats the `!important` blanket rule regardless of source order.
- **`f384d3e` was committed with `SQL_SYNC_SKIP=1`** — the VPN was down and the two SQL hooks could
  not reach INT. That change touches no SQL. `--no-verify` was **not** used; every other hook ran.
- **`nx --doctor` reports pending INT migrations** (`0044`, from #125). Will self-apply on the next
  commit now the VPN is back.
- **`nexora_build` is empty in dev/INT by design.** `nx_lib/_build.py` is gitignored and only exists
  on PROD. `test_build_stamp_is_empty_without_generated_module` asserts it is absent from a checkout,
  so **do not commit that file** — creating it locally to eyeball the stamp will fail the suite until
  it is deleted.
- **Jinja templates cache for the process lifetime.** One contrast measurement in this session was
  taken against pre-edit markup for exactly this reason. Always `nx -r` before measuring.

## Untracked / left for owner

- Nothing uncommitted — working tree is clean.
- `var/screenshots/issue113_*.png` (9 files) are gitignored session artifacts; delete freely.
- No spec or plan file was written for the footer change — the owner explicitly chose "just do it"
  over the spec→plan ceremony for a 13-line deletion.

## How to verify

```powershell
# Green — this session's work
.venv\Scripts\python.exe -m pytest tests/unit/test_version.py tests/unit/test_template_layout.py `
    tests/unit/test_translations.py -q --no-cov      # 16 passed

# RED — owner's #118, blocks the pre-push gate
.venv\Scripts\python.exe -m pytest tests/unit/test_template_url_prefix.py -q --no-cov

# In the browser
.\bin\nx.ps1 -r
.\bin\nx.ps1 -u -b --loginas:ben.streich
#   /dashboard, /workitems  -> zero <footer> elements
#   profile dropdown        -> Help + "nexora 2.5.65"
#   /  (login)              -> footer still present
```

## Resuming in a fresh session

Run `/reset-session` — it reads `var/handoff-pending` and lands here. If another handoff shares
today's date, target this one explicitly:
`/reset-session docs/superpowers/handoffs/2026-07-29-issue-113-version-display.md`.

Start at **Next steps #1** (the red `test_template_url_prefix.py`) — it is the only thing standing
between this branch and a push. There is no plan or spec file to resume; #113 is closed and the
backlog items in #4 have not been specced.
