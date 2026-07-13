# Handoff — PR #115 shipped to PROD + CI/gate speedups + Confluence cred hunt (parked)

**Date:** 2026-07-13 (afternoon) · **Branch:** `feature/2.5.64` · **0 ahead of origin at handoff-write time (handoff commit will be +1, unpushed)** · session was local (push + PR were explicitly authorized and done)
**Prior handoff:** `2026-07-13-pdbsuser-assign-permission-fix-execution-complete.md` (same day, morning — the pdbsUser fix execution)

## TL;DR

- **PR #115 (pdbsUser fix set) merged to main and deployed to PROD — green.** Migrations `0032`+`0034`
  applied before the app-pool stop. Owner spot-checked pdbsUser assignment on PROD: works.
- **Found + fixed: the flaky-E2E retry net NEVER worked** (`--only-rerun flaky_e2e` is an error-text
  regex in pytest-rerunfailures — matched nothing, so no test was ever retried; a single browser race
  failed the whole gate). Retries now armed directory-wide in `tests/e2e/conftest.py`.
- **CI/gate speedups implemented and pushed** (`604e6c9`, on origin/feature/2.5.64 but **NOT on main
  yet**): docs-path skip, test-job concurrency cancel, two-tier suite ordering. Take effect on the
  next PR merge.
- **Confluence sync still broken, root cause narrowed but PARKED by owner.** The runner env file is
  fine now; every API token fails with 403 "caller cannot access Confluence" while browser access
  works. Owner checked admin console and says the account has access — contradiction unresolved,
  deliberately deferred.

## This session's commits (oldest → newest, all pushed)

```
3dc75c1  test(e2e): mark test_simple_export_csv as flaky_e2e            (per-test mark, pre-discovery)
81a0c1e  fix(tests): actually arm the flaky-E2E retry net               (the real fix)
604e6c9  ci(deploy): skip docs-only pushes, cancel stale tests, two-tier suite
```
(The pdbsUser fix commits themselves are in the prior handoff; this session verified them, opened
PR #115, and the owner merged it. The handoff commit for THIS doc lands on top of `604e6c9`.)

## What shipped

| Area | Change | Files | Commit |
|---|---|---|---|
| **PROD deploy** | PR #115 merged → deploy run 29245541052 green: migrations `0032`+`0034` applied, robocopy mirror, app pool restarted. Owner verified pdbsUser assignable on PROD. | — | merge commit on main |
| **Retry net** | `tests/e2e/conftest.py` `pytest_collection_modifyitems` now adds `pytest.mark.flaky(reruns=2)` to **every** item under `tests/e2e` (directory-scoped, marker-independent — 40+ tests had drifted out of the net by missing the `flaky_e2e` decorator; 29/30 in `test_reporting_simple.py`). Dead `--reruns 2 --only-rerun flaky_e2e` flags removed from `.pre-commit-config.yaml`, `deploy.yml`, `README.md`, `scripts/git-hooks/pre-push`. Marker stays registered as documentation only. | `tests/e2e/conftest.py`, 4 config/doc files, `CHANGELOG.md` | `81a0c1e` (+`3dc75c1` now-redundant per-test mark, harmless) |
| **CI speedups** | (1) `paths-ignore` on push+PR: `docs/**`, `**.md`, `.claude/**`, `.claudeignore` skip the Deploy workflow entirely (all excluded from the robocopy mirror anyway). (2) test job `concurrency` group with `cancel-in-progress: true` (keyed per PR/ref); deploy job gets `prod-deploy` group with `cancel-in-progress: false` — **deploys queue, never cancel**. (3) Two-tier suite: fast tier `pytest tests --ignore=tests/e2e` (1247 tests, catches root-level `tests/test_confluence_publish.py`) gates the e2e tier `pytest tests/e2e` (123 tests) — pytest's alphabetical collection had run e2e FIRST, so unit failures surfaced after ~10 min of browsers. Same split in the local pre-push gate with per-hook `fail_fast: true` on the fast hook. | `.github/workflows/deploy.yml`, `.pre-commit-config.yaml`, `README.md`, `CHANGELOG.md` | `604e6c9` |

## Next steps (ordered)

1. **Next PR → main** (whenever the next batch of 2.5.64 work is ready) activates and live-tests the
   CI speedups: expect the Deploy run to show two test steps (fast, then e2e), and docs-only pushes
   to main to trigger no Deploy run at all. The README/CHANGELOG changes in `604e6c9` will also
   re-trigger the Confluence sync workflow on merge (which will fail until #2 is resolved — expected,
   harmless).
2. **Confluence cred (owner, parked — resume when wanted).** State of the hunt, so nobody re-treads:
   - Runner env file is PRESENT and loaded (owner copied it 2026-07-13; the June 24 missing-file
     failure is gone). Failure moved to the Confluence API call.
   - **Every token fails** with 403 `"Request rejected because caller cannot access Confluence"` on
     `/wiki/rest/api/user/current` (and 404 on v2 endpoints): the old June classic token (ATATT), a
     new all-scopes token, and a supposedly-classic new token that **still came out with the scoped
     `ATCTT` prefix**. Jira API 401s too. The `ATCTT` token also 404s via the
     `api.atlassian.com/ex/confluence/<cloudId>` gateway (cloudId `61333521-5b29-4903-a470-fd0b2d07ce1d`).
   - Browser access to the space **works** for benjamin.streich@sydoc.ch, and the owner checked the
     admin console and reports the account HAS product access. Working theories remaining, in order:
     (a) the "classic" token creation actually produced a scoped token (prefix says so) — try again
     making sure it's the plain "Create API token" button and the result starts with `ATATT`;
     (b) an org-level API-token access policy (admin.atlassian.com → Security → API tokens) blocks
     token auth; (c) admin-bypass browser access masking a missing *license* (owner says no).
   - Once a token probes green: copy the file to `C:\sydoc\runner-secrets\CONFLUENCE.env` on SYAPP01
     and `gh run rerun 29245541092` (workflow has NO workflow_dispatch). Probe one-liner is in "How
     to verify" below.
3. **Optional carryover** from the prior handoff: tighten `test_api_admin_permission_users_seeded`
   (`tests/integration/test_admin_routes.py:468`) from `in (200, 500)` to `== 200` when next touching
   that file.

## Gotchas & notes (READ)

- **`--only-rerun <x>` in pytest-rerunfailures filters by ERROR-TEXT REGEX, not marker.** It also
  blocks marker-driven reruns when the pattern doesn't match the traceback. This is why the gate's
  retry net was dead since it was built (May 2026). Don't reintroduce the flag.
- **pytest collects alphabetically** → `pytest tests` runs `tests/e2e` before `tests/unit`. The
  two-tier split exists precisely for this; keep new test dirs inside the fast tier unless they're
  browser-driven.
- **`tests/test_confluence_publish.py` lives at tests/ ROOT** (30 tests) — any tier split must use
  `--ignore=tests/e2e`, not an explicit `tests/unit tests/integration` list, or those 30 vanish
  silently. Tier counts at commit time: 1247 fast + 123 e2e = 1370 total.
- **deploy.yml concurrency:** the never-cancel group on the deploy job is load-bearing — cancelling
  mid-robocopy/mid-migration would leave PROD half-mirrored with the app pool stopped. Don't "unify"
  the two concurrency groups.
- **Atlassian token prefixes:** `ATATT` = classic/unscoped, `ATCTT` = scoped. Scoped tokens do NOT
  authenticate against `sydocteam.atlassian.net` site-domain REST (the publish script's URL style) —
  classic only. If the org ever bans classic tokens, `scripts/confluence-publish.py` needs a ~20-line
  rewrite to the `api.atlassian.com/ex/confluence/<cloudId>` gateway style.
- **PR #115 review artifacts:** the whole-branch opus review and live INT verification records are in
  the prior handoff; nothing was re-reviewed this session beyond fresh full-suite runs.
- **Memory files updated this session** (`~/.claude/projects/C--dev-nexora/memory/`):
  `project_2_5_64_cycle.md`, `project_confluence_docs_sync.md` — the Confluence one now carries the
  cred-hunt state (update it again when resolved).

## Untracked / left for owner

- Working tree clean; everything pushed except the handoff commit itself (owner pushes when
  convenient — or it rides along with the next feature push).
- `env/CONFLUENCE.env` (gitignored) currently holds the non-working `ATCTT` token — replace during
  Next-steps #2.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
git log --oneline 33a009f..HEAD      # this session's 3 commits + this handoff
git status --porcelain               # empty

# Retry net actually retries (fail-once probe pattern, ~6s):
# drop a test with a module-global fail-once counter into tests/e2e, run:
.venv\Scripts\python -m pytest tests/e2e/<probe>.py -q   # expect "1 passed, 1 rerun"

# Tier collection sanity (1247 + 123 = 1370):
.venv\Scripts\python -m pytest tests --ignore=tests/e2e --collect-only -q | Select-String collected
.venv\Scripts\python -m pytest tests/e2e --collect-only -q | Select-String collected

# Confluence cred probe (statuses only, prints no secrets):
.venv\Scripts\python -c "import requests; env={k.strip():v.strip().strip('\"') for k,v in (l.split('=',1) for l in open(r'env\CONFLUENCE.env') if '=' in l)}; r=requests.get('https://sydocteam.atlassian.net/wiki/rest/api/user/current', auth=(env['CONFLUENCE_USER_NAME'],env['CONFLUENCE_API_KEY']), timeout=15); print(r.status_code, r.text[:120])"
# 200 = cred good → copy env to runner + gh run rerun 29245541092
```

## Resuming in a fresh session

Run `/reset-session` (the `var/handoff-pending` flag points here). Note: another handoff shares
today's date — if the flag is gone, target this file explicitly:
`/reset-session docs/superpowers/handoffs/2026-07-13-pr115-ship-ci-speedups.md`.
No plan file is open; next work is either the Confluence cred (Next steps #2) or whatever the next
2.5.64 feature is.
