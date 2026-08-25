# SQLAlchemy pool sizing for the 32-thread waitress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `v3.2.3.2` HEAD (`833355f4`) on 2026-08-25** — anchor on quoted snippets + symbol names, never line numbers; re-Grep before editing. Plan file: `docs/superpowers/plans/2026-08-25-db-pool-sizing-waitress-threads.md`.

**Goal:** PROD now runs as ONE waitress process with `--threads=32` (`web.config`, since `feat(hosting)` `83316e1d`), but each SQL Server engine's connection pool holds at most `pool_size=10 + max_overflow=20 = 30` connections. Under full concurrency, 2 of 32 threads can block up to `pool_timeout=30` seconds waiting for a checkout — a 2026-08-25 local load test at 100 concurrent showed exactly such multi-second p95/max tails (max 14 s) while waitress's own queue was empty. Raise the four SQL Server pools to `16 + 24 = 40 ≥ 32` via shared module constants, and add a unit test that permanently ties pool capacity to the thread count declared in `web.config`, so the two can never silently drift apart again.

**Architecture:** Two named constants in `nx_lib/db.py` (`POOL_SIZE = 16`, `MAX_OVERFLOW = 24`) replace the four repeated literal pairs on the SQL Server engines (`engine_octo_db`, `engine_nexora_db`, `engine_statistics_db`, `engine_generali_db`). The MS02 Postgres engines and the read-only sandbox logins keep their current, smaller sizing (light, bursty use — deliberately untouched). A new unit test parses the `--threads=` value out of `web.config`'s `httpPlatform` `arguments` attribute and asserts `POOL_SIZE + MAX_OVERFLOW >= threads` plus that the live engines actually use the constants.

**Tech Stack:** SQLAlchemy `create_engine` QueuePool args (existing), `xml.etree.ElementTree` for the web.config parse (stdlib, same approach as `tests/unit/test_iis_hosting.py`), pytest.

---

## Context an engineer needs (read first)

- **Branch:** execute on `v3.2.3.2` (or the cycle branch it has been merged into by the time you run — check `git log --oneline -3 v3.2.3.2` first). **Parallel sessions are normal on this repo**: do the work in your own worktree (`git worktree add .claude/worktrees/db-pool-sizing v3.2.3.2` or a branch off it), never in the main checkout, and stage by pathspec only. Commit per task. **Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes.
- **Copy the gitignored env files into the worktree before committing or running tests**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — the pre-commit hook runs `scripts/db-migrate.py --env INT` (needs `env/INT.env`) and the test suite needs `env/TEST.env`.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python.exe -m pytest …`. No new dependencies.
- **`nx_lib/db.py` executes at import time** (creates real engines from `env/TEST.env` creds under pytest). The existing suite already imports it (`tests/unit/test_db.py`), so the new test can too — no mocking needed for pool attributes; `engine.pool.size()` is public API and does not open a DB connection.
- **Migrations needed: NO.** No permission, no i18n, no route, no template, no deploy-exclude change.
- **Pre-commit hooks** run the INT migration apply + SQL sync check on every commit; if INT is unreachable prefix with `SQL_SYNC_SKIP=1 git commit …` — **never** `--no-verify`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period, non-empty body wrapped ≤100 chars/line; commit via `git commit -F - <<'EOF' … EOF` (Bash tool). End the body with the executing model's `Co-Authored-By:` trailer.
- **This plan touches `web.config` only in a comment** — the hosting contract test `tests/unit/test_iis_hosting.py` must stay green (it asserts handler/args/env, not comments).

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | `POOL_SIZE = 16`, `MAX_OVERFLOW = 24` (capacity 40) for the four SQL Server engines only. | 40 ≥ 32 threads with headroom for the scheduler/outage probes; SQL Server idle connections are cheap; overflow connections close when returned, so the steady-state footprint stays ≈ `POOL_SIZE`. |
| D2 | MS02 Postgres engines (`pool_size=5, max_overflow=10`) and the RO sandbox engines stay as they are. | Reporting-sandbox / MS02 traffic is a small slice of requests; Azure PG connection slots are the scarcer resource. Revisit only if a load test shows PG checkout waits. |
| D3 | The invariant `POOL_SIZE + MAX_OVERFLOW >= web.config threads` becomes a unit test, parsing `--threads=` from `web.config`. | The two numbers live in different files edited by different kinds of change; the 30-vs-32 gap this plan fixes was introduced exactly that way. |
| D4 | `pool_timeout` stays 30, `pool_recycle` stays 1800, `pool_pre_ping` stays True. | Out of scope; no evidence against them once capacity ≥ threads. |

## Owner actions (not for the executor)

1. Review + merge the worktree branch into the cycle branch, push. PROD picks the change up on the next deploy (new waitress process = new pools); no env keys involved, no `env-sync` needed.
2. Optional after deploy: re-run a load test against PROD-like hardware to confirm the p95 tails are gone (recipe in the appendix).

---

# PHASE 1 — the invariant test (RED), then the fix (GREEN)

### Task 1: Failing unit test tying pool capacity to web.config threads

- [ ] In the worktree, create `tests/unit/test_db_pool_sizing.py` with exactly this content:

```python
"""Pool capacity must cover waitress's thread count (web.config), else threads
block up to pool_timeout waiting for a connection — the 10+20=30 vs 32 gap
fixed on 2026-08-25 produced multi-second p95 tails under load."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from nx_lib import db

ROOT = Path(__file__).resolve().parents[2]


def _waitress_threads():
    ws = ET.parse(ROOT / "web.config").getroot().find("system.webServer")
    args = ws.find("httpPlatform").get("arguments")
    m = re.search(r"--threads=(\d+)", args)
    assert m, f"no --threads= in web.config arguments: {args}"
    return int(m.group(1))


def test_sqlserver_pool_capacity_covers_waitress_threads():
    threads = _waitress_threads()
    assert threads >= 1
    assert db.POOL_SIZE + db.MAX_OVERFLOW >= threads, (
        f"pool capacity {db.POOL_SIZE}+{db.MAX_OVERFLOW} < {threads} waitress threads"
    )


def test_all_four_sqlserver_engines_use_the_shared_constants():
    engines = [
        db.engine_octo_db,
        db.engine_nexora_db,
        db.engine_statistics_db,
        db.engine_generali_db,
    ]
    for e in engines:
        assert e.pool.size() == db.POOL_SIZE, e
        # _max_overflow is the QueuePool attribute backing max_overflow; there
        # is no public accessor, and pinning it here is the point of the test.
        assert e.pool._max_overflow == db.MAX_OVERFLOW, e
```

- [ ] Run it — **must be RED** with `AttributeError: module 'nx_lib.db' has no attribute 'POOL_SIZE'`:

```
C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_db_pool_sizing.py -q --no-cov
```

### Task 2: Constants in `nx_lib/db.py` (GREEN)

- [ ] In `nx_lib/db.py`, directly above the line `engine_octo_db = create_engine(` insert:

```python
# One waitress process serves PROD with --threads=32 (web.config). Every thread
# may need a connection from the SAME engine at once, so each SQL Server pool
# must cover the thread count or requests stall in pool_timeout (30 s) checkout
# waits — observed as multi-second p95 tails in the 2026-08-25 load test when
# capacity was 10+20=30 against 32 threads. Guarded by
# tests/unit/test_db_pool_sizing.py, which parses --threads out of web.config.
POOL_SIZE = 16
MAX_OVERFLOW = 24
```

- [ ] In each of the **four** SQL Server `create_engine(...)` calls — the ones assigned to `engine_octo_db`, `engine_nexora_db`, `engine_statistics_db`, `engine_generali_db`, each currently reading:

```python
    pool_size=10,
    max_overflow=20,
```

  replace those two lines with:

```python
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
```

  **Leave every other engine alone** — the MS02 Postgres engines (`pool_size=5, max_overflow=10`) and any `_ro` engines keep their literals.

- [ ] Run the new test plus the existing db tests — all green:

```
C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_db_pool_sizing.py tests/unit/test_db.py tests/unit/test_iis_hosting.py -q --no-cov
```

- [ ] `C:\dev\nexora\.venv\Scripts\ruff.exe check nx_lib/db.py tests/unit/test_db_pool_sizing.py` and `...\ruff.exe format` the same two files.

### Task 3: Keep the three prose references honest + changelog, then commit

- [ ] `web.config` — the comment line currently reading:

```
          - threads=32 matches the SQLAlchemy pools (10 + 20 overflow per engine).
```

  becomes:

```
          - threads=32 is covered by the SQLAlchemy pools (POOL_SIZE 16 + 24
            overflow per SQL Server engine = 40; tests/unit/test_db_pool_sizing.py
            ties the two together).
```

- [ ] `docs/howto/iis.md` — in the "What `web.config` sets, and why" table, the row:

```
| `--threads=32` | Matches the SQLAlchemy pools (10 + 20 overflow per engine). |
```

  becomes:

```
| `--threads=32` | Covered by the SQLAlchemy pools (16 + 24 overflow per SQL Server engine; `tests/unit/test_db_pool_sizing.py` enforces capacity ≥ threads). |
```

  (Grep for `Matches the SQLAlchemy pools` — if the wording differs slightly, update whatever that row says; the point is it must not claim 10+20.)

- [ ] `CHANGELOG.md` — add under `## [Unreleased]` → `### Fixed`:

```markdown
- **DB pools now cover the 32 waitress threads.** Each SQL Server engine held
  at most 10+20=30 connections against 32 worker threads, so under full load
  two threads per engine could stall up to 30 s in a pool-checkout wait
  (observed as multi-second p95 tails). Pools are 16+24=40 via shared
  `nx_lib/db.py` constants, and a unit test parses `--threads` out of
  `web.config` so pool capacity and thread count can never drift apart
  silently again.
```

- [ ] Run the fast suite to be safe: `C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests --ignore=tests/e2e -q` (the known flake `tests/integration/test_auth_routes.py::test_request_password_reset_returns_before_send_completes` may be deselected).
- [ ] Commit (paste-ready; swap the trailer for the executing model):

```
git add nx_lib/db.py tests/unit/test_db_pool_sizing.py web.config docs/howto/iis.md CHANGELOG.md
git commit -F - <<'EOF'
fix(db): size SQL Server pools to cover the 32 waitress threads

Each engine held pool_size=10 + max_overflow=20 = 30 connections against
32 worker threads (web.config --threads), so two threads per engine could
stall up to pool_timeout=30 s in a checkout wait under full concurrency -
observed as multi-second p95 tails in the 2026-08-25 load test. Shared
POOL_SIZE=16 / MAX_OVERFLOW=24 constants now feed the four SQL Server
engines (MS02 Postgres and RO sandbox engines deliberately unchanged),
and tests/unit/test_db_pool_sizing.py parses --threads out of web.config
so capacity >= threads is enforced from now on.

Co-Authored-By: <executing model> <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- The test parses `web.config` with stdlib `xml.etree` **on purpose** — it is the repo's own trusted file and `tests/unit/test_iis_hosting.py` already does the same; do not add a `defusedxml` dependency for this.
- `engine.pool._max_overflow` is private SQLAlchemy API (`QueuePool`). It is stable across the pinned `SQLAlchemy==2.0.45` and using it is deliberate (there is no public accessor); if a future SQLAlchemy bump renames it, fix the *test*, not the constants.
- Do **not** "fix" the Postgres engines to the same constants — Azure PG connection slots are the scarce side there (see `docs/design/ms02-multisource.md`).
- The load-test tails also had a GIL component (CPU-bound rendering); this plan only removes the pool-wait component. If tails persist after deploy, the next knob is 2–4 waitress processes behind IIS ARR — that requires sessions off the filesystem backend and a limiter `storage_uri` first (see "Scaling beyond one process" in `docs/howto/iis.md`), and is explicitly **out of scope** here.
- Appendix — quick load-test recipe used to find this (adapt paths): start the app under waitress with the exact `web.config` args on a spare port (`$env:ENVIRONMENT='INT'; python -m waitress --listen=127.0.0.1:8123 --threads=32 --connection-limit=1000 nx_main:app`), then hammer it from **two or more separate client processes** (a single Python client process saturates its own GIL near ~46 req/s and becomes the bottleneck): each client logs in via `/dev/login/<user>` (loopback-only) and loops GETs over `/api/session/heartbeat`, `/profile`, `/appearance` across ~25–50 threads, reporting p50/p95/max. Compare before/after; watch the server's stderr for `waitress.queue` depth warnings (queue empty + slow responses ⇒ the wait is inside the request, e.g. pool checkout).
