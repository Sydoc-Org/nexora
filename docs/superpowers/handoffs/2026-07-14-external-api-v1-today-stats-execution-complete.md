# Handoff — External API v1 ("today" stats) execution complete

**Date:** 2026-07-14 (evening) · **Branch:** `plan/external-api-v1-today-stats` (worktree
`.claude/worktrees/plan-external-api-v1-today-stats`, based on `feature/2.5.64` @ `97678a0`) ·
**commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-14-external-api-v1-today-stats-plan.md`

## TL;DR

- **All 8 tasks of the External API v1 plan are implemented, tested, and live-verified on INT.**
  `docs/superpowers/plans/2026-07-14-external-api-v1-today-stats.md` executed end-to-end via
  `superpowers:subagent-driven-development` — fresh implementer + reviewer per task (6 code-producing
  tasks), all six spec-compliance/quality reviews came back Approved with zero unresolved findings.
- **Full local test gate is green:** 1277 non-e2e passed / 0 failed / 25 expected skips, translations
  7 passed (zero new `_()` msgids), 6-commit history confirmed in order.
- **Live INT verification confirms the feature end-to-end** via a throwaway scratchpad admin script
  (never committed) driving the worktree's own dev server on port 8000: success path returns
  `200` with today's date, correct `processes` scope, non-negative ints; no-header → `401` +
  `WWW-Authenticate: Bearer`; garbage token → `401 {"error":"Invalid API key"}`; wrong path →
  `404 {"error":"Not found"}` (JSON); `LastUsedAt` stamped after the successful call; disabling the
  key then re-calling gives the byte-identical `401` (uniform — no existence oracle). Temp key
  deleted and dev server stopped afterward; `git status --porcelain` clean.
- **Final whole-branch review (opus, `97678a0..8b3753b`): Approved.** No Critical or Important
  findings. One optional Minor nit (a stale "mirror exactly" comment in
  `tests/unit/test_create_app.py` — the endpoint-set check is intentionally one-directional so this
  isn't a defect, just slightly stale wording). All six security properties (decorator order, uniform
  401, fail-closed auth / fail-open-per-leg stats, no dashboard behavior change, no i18n leakage, no
  deploy-config gap) independently re-verified at the whole-branch level.
- **One process incident this session, fully resolved:** Task 5's first implementer subagent
  committed to the wrong git checkout (the main clone `C:\dev\nexora` on `feature/2.5.64`, not this
  worktree) and truncated `tests/integration/test_api_external_routes.py` down to only its own 2 new
  tests in the process. Caught immediately (before any push), confirmed unpushed, fixed with
  `git revert` (not `git reset --hard`, which nexora's CLAUDE.md blocks outright for unpushed commits
  — no permission override possible) in the main clone, then correctly redone in this worktree with
  hardened directory-check instructions. See Gotchas for full detail.

## This session's commits

Worktree branch `plan/external-api-v1-today-stats`, oldest → newest (on top of the plan-writing
session's `d53c317`):

- `a6c96f7` feat(db): ApiKeys table for external API v1 (0038) — Task 1
- `ffdc007` refactor(dashboard): extract session-free compute_today_stats seam — Task 2
- `765408f` feat(api): require_api_key Bearer auth over dbo.ApiKeys — Task 3
- `01bd42d` feat(api): external v1 endpoint GET /api/v1/stats/today — Task 4
- `8c54709` feat(api): JSON error handlers for /api/v1 paths — Task 5 (the corrected retry; see
  Gotchas for the wrong-checkout incident)
- `8b3753b` docs(api): external API howto, key-gen script, changelog — Task 6

Tasks 7 (full local test gate) and 8 (live INT verification) were verification-only — no commits.

(Plus this handoff commit.)

## What shipped

| Area | Files | Commit(s) |
|---|---|---|
| DB migration + TEST mirror | `sql/_migrations/NexoraDB/0038_create_api_keys.sql`, `sql/test/schema.sql`, `sql/NexoraDB/Tables/dbo.ApiKeys.sql` | `a6c96f7` |
| KPI extraction seam | `nx_lib/views/dashboard.py` (`compute_today_stats`), `tests/unit/test_dashboard_stats.py` | `ffdc007` |
| Bearer auth | `nx_lib/api_auth.py` (new), `tests/unit/test_api_auth.py` (new) | `765408f` |
| Endpoint + wiring | `nx_lib/views/api_external.py` (new), `nx_lib/__init__.py`, `tests/integration/test_api_external_routes.py` (new) | `01bd42d` |
| JSON error handlers | `nx_lib/hooks.py`, `tests/unit/test_hooks.py`, `tests/integration/test_api_external_routes.py` | `8c54709` |
| Docs + tooling | `scripts/new-api-key.py` (new), `docs/howto/external-api.md` (new), `CHANGELOG.md`, `CLAUDE.md` | `8b3753b` |

Feature shape (full rationale in the plan's D1–D16 table): `GET /api/v1/stats/today` returns
`{"date", "imported_today", "exported_today", "processes"}` for one external client's own dashboard,
authenticated with `Authorization: Bearer <key>` against `dbo.ApiKeys` (SHA-256 hash stored,
`hmac.compare_digest` matching, uniform 401 for unknown/disabled keys, 503 fail-closed on DB error).
`@limiter.limit("60 per minute")` sits OUTERMOST above `@require_api_key` (opposite of
`reporting.py`'s stack) so unauthenticated brute-force requests are throttled too — pinned by a 429
test and independently re-verified at the whole-branch review. Key issuance is manual v1
(`scripts/new-api-key.py`, dev-side, prints the raw token once + INSERT) — no OAuth, no key UI, no
OpenAPI, deliberately.

## Next steps (ordered)

1. **This `/execute-plan` session's own next step is the worktree merge** (handled by this handoff
   command itself, `--merge-worktree` flag): merges `plan/external-api-v1-today-stats` into
   `feature/2.5.64` in the **main clone** `C:\dev\nexora`, then removes this worktree and deletes this
   branch. If you're reading this after that step ran, the worktree is already gone — resume from
   `feature/2.5.64` directly in the main clone.
2. **Owner: review and push `feature/2.5.64`** (commit-only session — nothing was pushed).
3. **PROD rollout is automatic** on the next deploy after `feature/2.5.64` reaches `main` — the
   deploy workflow applies pending migrations (incl. `0038`) before mirroring code, so the endpoint
   can never ship without its table.
4. **Owner actions from the plan (not done, not this executor's job — see the plan's "Owner actions"
   section for full detail):**
   - Issue the real client's key after PROD deploy (`python scripts/new-api-key.py --client-code
     <code> --label "<client>" --processes "<ProcessName>,…"`, run the printed INSERT against PROD).
   - Client comms: base URL `https://nexora.sydoc.ch/nexora/api/v1/stats/today`, Bearer header,
     response shape, 60/min limit, maintenance-window 503 behavior, revoked-key-looks-like-invalid.
   - Sanity-check the 60/min rate limit once real traffic exists.
   - `exported_today`'s inherited dashboard leg-asymmetry is a "someday/maybe" semantics decision,
     not a v1 bug — see the plan's Owner action 4 if it ever needs to change.
5. **Migration numbering heads-up (from the final review):** this branch claimed `0038`. Session
   memory notes a separately-planned PROD `col_validationuser` re-map that was earmarked "→0038" in
   an earlier session — that follow-up must now be authored as `0039` (or whatever is next-free at
   that time).

## Gotchas & notes

- **Wrong-checkout incident (Task 5), full detail:** the first Task 5 implementer subagent's
  `git commit` landed on `feature/2.5.64` in the main clone (`C:\dev\nexora`) as `ebd4741`
  ("feat(api): JSON error handlers for /api/v1 paths"), not on this worktree branch — despite
  explicit instructions to work from the worktree path. Because the integration test file didn't
  exist yet on that branch (Task 4's work lives only on our plan branch), the subagent's "append 2
  tests" instruction silently became "create a 2-test file", truncating what should have been an
  11-test file. Caught immediately via `git log`/`git worktree list` cross-checking (this worktree's
  own HEAD had stayed at Task 4's commit the whole time — the mismatch was the tell). Confirmed
  `ebd4741` was never pushed (`origin/feature/2.5.64` still at `d2d7205`) and the main clone had no
  other at-risk uncommitted work. **Fix used `git revert ebd4741 --no-edit` in the main clone**
  (commit `7654401`) rather than `git reset --hard` — nexora's CLAUDE.md places `reset --hard` on a
  branch with unpushed commits in the "Never authorized, even with explicit permission" list, so no
  permission prompt could have unblocked it; `git revert` is a plain commit on a feature branch,
  already blanket-authorized. Task 5 was then correctly redone in this worktree with hardened
  dispatch instructions (mandatory `git rev-parse --show-toplevel` check as literally the first
  action, plus an explicit pre-check that the integration test file already had 9 tests before
  appending). The redo (`8c54709`) was independently verified by the controller (not just the
  subagent's own report) to contain all 11 tests via direct `grep -c "^def test_"` before review.
  **Net effect on `feature/2.5.64` in the main clone:** two extra commits now sit in its history,
  `ebd4741` immediately followed by its own revert `7654401` — a harmless no-op pair (zero net diff)
  that will be visible in `git log` once this branch merges. Optional for the owner to squash away
  before pushing; not required, since they cancel out exactly.
- **A stray dev-server process was also found during Task 8** (live INT verification): a leftover
  `python nx_main.py` process bound to port 8000 was running against the **main clone's** code (PID
  30900, no feature) from earlier in the session, interfering with the first curl call (spurious HTML
  404 from nondeterministic dual-listener routing). Diagnosed via `netstat`, confirmed by cmdline, and
  stopped (process only — no files touched). Root cause likely a much earlier `nx -u` invocation left
  running; not something this plan's tasks started. Worth a `Get-Process python` sanity check if a
  future session sees odd port-8000 behavior.
- **Pre-existing CRLF/EOL noise under `sql/**`** (~65–68 files, `git status` shows them as modified
  with zero actual diff content — an `i/lf w/crlf` working-tree artifact). Seen repeatedly across
  every task in this session; cleaned with `git restore sql/` before each commit, never staged. If you
  see this in `git status` next session, it predates this work — don't chase it.
- **`env/INT.env` and `env/TEST.env` were already present in this worktree** (gitignored, copied in
  the plan-writing session) — used throughout for the SQL pre-commit hooks, `test_db_reset.py`, and
  Task 8's live verification. They're gone once the worktree is removed (step 5 of this handoff) —
  not a loss, just don't look for them post-merge.
- **Two interpreters, as documented in the plan:** `C:\dev\nexora\.venv\Scripts\python` for
  pytest/`test_db_reset.py`; plain global `python` for `db-migrate.py`/`sync-from-db.py`/
  `new-api-key.py`/the dev server. Both used correctly throughout — no interpreter-mismatch issues
  this session.

## Untracked / left for owner

- Nothing left uncommitted in this worktree — `git status --porcelain` is clean apart from the
  pre-existing CRLF noise described above (zero real diff, safe to ignore).
- Main clone `C:\dev\nexora` has the two pre-existing untracked junk files (`package.json`,
  `package-lock.json`, noted in the prior handoff as "not this session's work") plus the harmless
  revert pair described above — nothing else.

## How to verify (this handoff's claims)

```powershell
# From the worktree root (or feature/2.5.64 in the main clone, post-merge):
git log --oneline -8          # a6c96f7, ffdc007, 765408f, 01bd42d, 8c54709, 8b3753b present, in order
git status --porcelain        # clean (real changes) -- CRLF noise under sql/** is pre-existing

# Full local gate:
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q          # 1277 passed
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_translations.py -q   # 7 passed

# Live endpoint check (needs a real API key -- see scripts/new-api-key.py):
#   $env:ENVIRONMENT='INT'; python nx_main.py     (from the worktree/main-clone root, port 8000)
#   curl.exe -s -i -H "Authorization: Bearer <key>" http://127.0.0.1:8000/api/v1/stats/today
```

## Resuming in a fresh session

`/reset-session` (this file is the newest `2026-07-14` handoff once `var/handoff-pending` is updated
below). By the time a fresh session reads this, the worktree merge (this handoff's own step 5) should
already have run — check `git worktree list` first; if
`.claude/worktrees/plan-external-api-v1-today-stats` is gone, you're resuming on `feature/2.5.64` in
the main clone, not in a worktree. Next steps are Owner actions only (see above) — no more
implementation work is queued for this plan.
