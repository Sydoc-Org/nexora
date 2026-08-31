# Handoff — #228 outage ended, PROD deployed, preflight-ordering fix still unmerged

**Date:** 2026-08-28 · **Branch:** `v3.2.3.9` (main checkout, no worktree) · **1 commit, already
pushed to `origin/v3.2.3.9`** · **PROD was deployed today at 17:01 and is healthy.**

**Prior handoff:**
[`2026-08-27-v323-release-prep-gate-red.md`](2026-08-27-v323-release-prep-gate-red.md) — its core
diagnosis was **wrong**, see "Corrections" below. Do not act on it.

## TL;DR

1. **The outage cause was never the tests.** `main`'s `test` job has been passing all along. The
   blocker was the `deploy` job dying at `Preflight IIS host` on a broken `waitress.__version__`
   probe — and that step ran *after* migrations, which is how PROD's schema got ahead of its code.
2. **PROD is deployed and healthy.** benstreich's #226 fixed the probe; the deploy ran green in
   **61 seconds**. PROD moved `78592ce8` (25 Aug) → `9da68cfb`, 161 commits.
3. **The four SQL synonyms are still in place. Leave them until the media question below is
   settled.** They cost nothing and are the rollback to a known-good state.
4. **#231 must merge before anything carrying a `sql/_migrations/` file** — Kundenmagazin included.

---

## Corrections to the prior handoff

| Prior claim | Reality |
|---|---|
| "main's test gate is red, 6 dashboard tests block the deploy" | `test` job **succeeds** on `main`. Both failed runs (`33099091339`, `33111295008`) show `test: success`, `deploy: failure`. |
| "`0079_clients_registry.sql` missing from `sql/test/schema.sql` breaks 6 dashboard tests" | The table **is** missing (confirmed — `clients registry load: Invalid object name 'Clients'`), but the dashboard tests monkeypatch past it. Full suite runs **2103 passed / 0 failed** locally. |
| "migrations applied but code never deployed because the gate is red" | Right effect, wrong cause. The `deploy` job applied `0070`–`0081` at step 5, then aborted at step 6. |

**Root cause, verified from the CI log:**

```
import waitress; print('waitress', waitress.__version__)
                                   ^^^^^^^^^^^^^^^^^^^^
AttributeError: module 'waitress' has no attribute '__version__'
```

The import succeeded. waitress was always installed. The probe checked an attribute waitress does
not ship, and the step reported it as *"waitress is not importable"*.

---

## What happened this session

| Action | Result |
|---|---|
| Combined #230 into #229 (`v3.2.3.8` → `v3.2.3.6`) | Merge `18bf9d0b`, no conflicts, authorship preserved. #230 closed as superseded. |
| Wrote `fc90cee8` — move preflight ahead of migrations | Pushed. **PR #231**, open, unmerged. |
| **Merged #226** (benstreich's probe fix) — *by the owner* | `main` → `9da68cfb`. Triggered the deploy. |
| Deploy run `33180014881` | **All steps green.** 15:00:36–15:01:37 UTC. Downtime < 60 s. |
| Deleted 3 spent local branches | `v3.2.1`, `v3.2.3.1`, `v3.2.3.4`. Content verified present elsewhere first. |

### `fc90cee8` scope

Pure relocation of the `Preflight IIS host` block above `Apply DB migrations to PROD`, plus 7 comment
lines. Verified order-insensitively: 385 → 392 lines, **only added comments differ**. The
`waitress` probe line is byte-identical to `main`'s — deliberately, so #226 stays separable.

---

## PROD state right now

- Running `9da68cfb`. Outage monitor: **12/12 probes green**, 0 incidents — site, all DBs, Graph,
  and the `prd-dps.sydoc.ch` Octo token endpoint (HTTP 200).
- `Invalid object name` errors: **393 before 11:43, zero since.** Note the synonyms stopped those at
  **11:43**, not the deploy — don't credit the deploy with it.
- **One** post-deploy error: `dashboard:846 Activity feed error: 'NoneType' object has no attribute
  'get'`. New-code bug, low severity, likely an unguarded Octo `None`.
- **Request logging repaired as a side effect.** `var/logs/user/` has only one folder today —
  hour 17. The `Errno 13` failures stopped at the pool restart. Audit data before 17:00 is lost.

### OPEN QUESTION — unresolved at session end

Owner reported `get_media_info` returning **500** with "Medien konnten nicht geladen werden" in the
workitem detail panel. **We could not confirm which environment that was.** Evidence it was *not*
PROD:

- Zero `get_media_info` / workitem requests in PROD's hour-17 request log (owner's own heartbeats
  *are* logged, so the session was being captured).
- No traceback in `app.log`; `waitress-stdout` is 0 bytes.

**First thing next session:** ask which URL the owner was on. If `nexora.sydoc.ch/nexora/...`,
investigate seriously and consider rolling back to `78592ce8`. If localhost/INT, it is unrelated to
the deploy.

Separately, **Octo has been returning intermittent 401/400** on document fetches with
`LoadMediaStreams=true` since at least 11:43 — *before* the deploy. That is a real, pre-existing
problem and the likely cause of missing media regardless.

---

## Next steps, in order

1. **Resolve the media 500 environment question** (above).
2. **Merge #231** — preflight reorder. Blocks nothing, protects everything after.
3. **Merge #229** — test gate + ODBC fix. Puts the working `test_db_reset.py` on `main`.
4. **Chase the Octo 401s** from `prd-dps.sydoc.ch`.
5. **Drop the four synonyms** once media is understood:
   `SearchConfig`, `StatConfig`, `IndexFieldMappings`, `Search_Field_Labels`.
6. Fix `dashboard:846` `NoneType`.
7. Then Kundenmagazin (#207) — **not before step 2.**

---

## Gotchas & notes

- **`ENVIRONMENT` must be UNSET for pytest.** `tests/conftest.py:11` uses
  `os.environ.setdefault("ENVIRONMENT", "TEST")`. Setting `ENVIRONMENT=INT` (as the prior handoff
  suggests for the app) makes the whole suite run against INT → **491 errors**, all
  `/login failed ... status=401`. Cost ~20 minutes this session.
- **Never assign `TMP` in a shell here.** It is an exported Windows variable; overwriting it
  redirects every child process's temp dir. Pytest wrote its scratch tree into `scripts/` and broke
  `test_script_imports_are_declared`. Use any other name.
- **`git show "rev:path"` needs `MSYS_NO_PATHCONV=1`** in Git Bash, or the argument is mangled to
  `rev\path` and the command *silently* produces nothing — easy to misread as a passing check.
- **Locale leak → every local push needs a DB reset first.** A test leaves `user@test.local` on
  `locale='de'` (seeded `'en'` at `sql/test/seed.sql:147`), so a later CSV-export test asserts
  `EXPORT TIMED OUT` and gets `EXPORT ZEITÜBERSCHREITUNG`. Passes on a fresh DB, fails on a reused
  one. CI is immune — it resets at step 11. A task chip was spawned for this.
- `scripts/test_db_reset.py` on `main` still hardcodes **ODBC Driver 17**, which this machine lacks
  (`IM002`). Until #229 merges, reset from a branch that has the fix:
  `git show "origin/v3.2.3.6:scripts/test_db_reset.py" > scripts/_helper.py`, run, delete.
- `0072_drop_decapitated_tables.sql` already exists and drops the tables the synonyms point at. It
  runs before `0075` so it is harmless today — but do not let a future migration drop them while
  the synonyms are live.
- Kundenmagazin's `0070_kundenmagazin_issues.sql` **collides** with `0070_backlog_metric_...` on
  `main`. Renumber to `0082`/`0083` before that branch can merge at all.
- **Never delete `v3.2.3.3`** (benstreich's) — he may hold unpushed local commits. `v3.2.3` is the
  active release-cycle branch, not spent, despite being 0 ahead.

## Untracked / left for owner

- Nothing uncommitted. Tree is clean.
- `v3.2.3.8` (local + remote) is spent once #229 merges, but the local one is checked out in the
  worktree at `C:\Users\GRR\dev\nexora-wt-223` — remove that worktree first.
- A full-history bundle of all local refs from before today's branch surgery:
  `…\scratchpad\nexora-all-refs-pre-fixture-work.bundle` (46 MB, verified). Session-scoped temp —
  copy it somewhere durable if it still matters.

## How to verify

```
python scripts/test_db_reset.py          # MUST run first — see the locale-leak note
python -m pytest tests --ignore=tests/e2e
```

Expect **2103 passed / 30 skipped / 0 failed**. Do **not** set `ENVIRONMENT`.

PROD health:

```
Get-Content "\\syapp01\d$\sydoc\nexora\var\logs\system\app.log" -Tail 40
Get-Content "\\syapp01\d$\sydoc\nexora\var\logs\system\outage_monitor.log" -Tail 12
```

## Resuming in a fresh session

Start here. `/reset-session docs/superpowers/handoffs/2026-08-28-outage-228-deployed-preflight-fix.md`
targets this file specifically. Open with the media-500 environment question — it is the only thing
that could still warrant a rollback.
