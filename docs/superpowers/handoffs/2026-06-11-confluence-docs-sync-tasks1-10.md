# Handoff — Git → Confluence docs sync: Tasks 1–10 complete, live

- **Date:** 2026-06-11
- **Branch:** `feat/confluence-docs-sync` (worktree `.claude/worktrees/confluence-docs-sync`)
- **Ahead of `feature/2.5.63`:** 13 commits (11 implementation + 2 fixes)
- **Remote:** commit-only (no push yet — owner pushes)
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-confluence-docs-sync-plan.md`

---

## TL;DR

- All 10 tasks implemented and committed. The Confluence space is live: 14 pages
  published from git via `scripts/confluence-publish.py`.
- Bootstrap ran on 2026-06-11 using `benjamin.streich@sydoc.ch` (personal account —
  should migrate to service account later).
- Two owner tasks remain before the feature is fully operational: provision runner
  secrets on SYAPP01, then flip the Confluence space to read-only.
- One bug fixed post-bootstrap: Standard plan doesn't support bulk archiving; script
  now archives one page at a time.

---

## This session's commits (oldest → newest)

| Hash | Subject |
|---|---|
| `9b8c337` | build(deps): add requirements-confluence.txt for Confluence sync |
| `116f886` | docs(changelog): merge duplicate Fixed sections under Unreleased |
| `781c125` | feat(docs-sync): staging, title preflight and index generation |
| `1485e8a` | test(docs-sync): local-conversion smoke and golden invariants |
| `dabc837` | feat(docs-sync): credentials loader and REST client with retry |
| `01c3749` | feat(docs-sync): space lookup, labels, bulk archive and reconcile |
| `a952a56` | feat(docs-sync): wire main() — dry-run, bootstrap, reconcile |
| `3675be1` | ci(docs-sync): Confluence publish workflow and credential template |
| `6ddae0d` | docs(docs-sync): runbook and doc updates for the Confluence mirror |
| `0653147` | fix(docs-sync): archive pages one at a time (Standard plan) |
| `0fb18a9` | docs(docs-sync): go-live notes and credential account runbook |

---

## What shipped

**Core script** — `scripts/confluence-publish.py`
- Stages publish set: `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/howto/*`,
  `docs/design/*` into `var/confluence-stage/`
- Generates alphabetical index pages for `howto/` and `design/` subtrees
- Converts locally with md2conf for pre-flight validation
- Publishes via md2conf (content-hash skip for unchanged pages, "do not edit" banner)
- Labels all published pages `git-managed`; orphan reconcile archives labeled pages no
  longer in git; stray pages (unlabeled, not in publish set) are warned but left alone
- Modes: `--dry-run` (zero writes), `--yes` (CI mode), `--bootstrap` (archive all
  existing non-homepage pages, then publish fresh)
- Credentials loaded from `env/CONFLUENCE.env` (gitignored)
- Archive: one page at a time (Standard plan rejects batch archive with 400)

**Tests** — `tests/test_confluence_publish.py` (30 tests, all pass)

**CI** — `.github/workflows/confluence-docs.yml`
- Path-filtered push to `main` + `workflow_dispatch`
- `concurrency: cancel-in-progress: false` (queue, don't cancel)
- Copies `C:\sydoc\runner-secrets\CONFLUENCE.env` from runner → workspace → cleanup

**Credentials template** — `env/CONFLUENCE.env.example`

**Documentation** — `docs/howto/confluence-sync.md` (runbook, troubleshooting,
token rotation, bootstrap reference, pending owner steps)

**Cross-references** — `CLAUDE.md`, `docs/howto/claude-workflow.md` updated

**Deps** — `requirements-confluence.txt` (`markdown-to-confluence==0.6.1`);
kept separate from uv lockfile to avoid `requests` version conflict with main app

---

## Credential state

- `env/CONFLUENCE.env` (gitignored, local only):
  - `CONFLUENCE_USER_NAME="benjamin.streich@sydoc.ch"` ← personal account
  - API token created 2026-06-11; expires 2027-06-11 at latest
- `C:\sydoc\runner-secrets\CONFLUENCE.env` on SYAPP01: **not yet provisioned**

---

## Next steps (owner, ordered)

1. **Provision SYAPP01 runner secrets.** Copy `env/CONFLUENCE.env` to
   `C:\sydoc\runner-secrets\CONFLUENCE.env` on SYAPP01. Then manually trigger the
   workflow (*Actions → Confluence docs sync → Run workflow*) to confirm end-to-end CI.

2. **Flip Confluence space read-only.** Space settings → Permissions → remove page
   add/edit/archive from user groups, keep full write for `benjamin.streich@sydoc.ch`
   only. (Documented in `docs/howto/confluence-sync.md` "Bootstrap" section.)

3. **Push branch + open PR.** `git push origin feat/confluence-docs-sync`, open
   PR → `feature/2.5.63` (or `main` depending on branching strategy).

4. **Migrate to service account (non-urgent).** When `noreply.sy@sydoc.ch` gets a
   Confluence seat, create a token on that account, update both credential files,
   update `CONFLUENCE_USER_NAME` in the runbook, revoke the personal token.

5. **Set token expiry reminder.** Current token expires ~2027-06-11. Calendar entry
   to rotate per `docs/howto/confluence-sync.md` "Token rotation" section.

---

## Gotchas & notes

- **Standard plan bulk archive is not supported.** `POST /wiki/rest/api/content/archive`
  returns 400 "not entitled to bulk archiving" when more than 1 page ID is in the body.
  Fixed in `0653147` — now archives one at a time. This means bootstrap is slightly
  slower for large page counts but works fine.
- **md2conf requires `--domain` even in `--local` mode.** Passing `--domain dummy.atlassian.net`
  is intentional; the value is ignored for local conversion.
- **`--skip-update` is required.** Without it, md2conf writes page IDs back into staged
  files; since `var/confluence-stage/` is wiped every run, those IDs would be lost and
  all pages would be re-created on the next sync.
- **`requirements-confluence.txt` is intentionally outside the uv lockfile.** md2conf
  requires `requests>=2.33`; the main app pins `requests==2.32.4`. CI installs it in a
  separate step after the main deps; the venv ends up with 2.34.2 but that's fine.
- **Run tests with `--noconftest`.** `pytest tests/test_confluence_publish.py -v
  --no-cov --noconftest` — skips `tests/conftest.py` which imports the Flask app and
  requires `env/TEST.env`.
- **Confluence v1 vs v2 API split.** Space lookup + page list use v2; labels and
  archive use v1 (no v2 equivalents).

---

## How to verify

```powershell
# Tests (no credentials needed)
C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests\test_confluence_publish.py -v --no-cov --noconftest
# Expected: 30 passed

# Dry-run (credentials needed — env/CONFLUENCE.env must exist)
C:\dev\nexora\.venv\Scripts\python.exe scripts\confluence-publish.py --dry-run --env-file env\CONFLUENCE.env
# Expected: staged=14, would-archive=0, done

# Live space
# https://sydocteam.atlassian.net/wiki/spaces/nexora/overview
```

---

## Resuming in a fresh session

This feature is complete from a code perspective. Remaining work is owner operations
(SYAPP01 provisioning, read-only flip, PR). No code changes expected unless the owner
finds issues after wiring CI.

If resuming here: `git log --oneline -5` on `feat/confluence-docs-sync` should show
`0fb18a9` as HEAD. Run tests to confirm green, then proceed with owner steps above.

To target this specific handoff: `/reset-session docs/superpowers/handoffs/2026-06-11-confluence-docs-sync-tasks1-10.md`
