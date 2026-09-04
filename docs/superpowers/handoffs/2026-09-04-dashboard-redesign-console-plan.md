# Handoff — Dashboard console redesign (option 1a): plan written, ready for /execute-plan

**Date:** 2026-09-04 · **Branch:** `plan/dashboard-redesign-console` in worktree
`.claude/worktrees/plan-dashboard-redesign-console` (cut from
`refactor/255-admin-nav-tenancy-labels` @ `ebbcdf07`) · **1 commit ahead, nothing pushed** ·
commit-only (remote session) · plan-only, **no implementation done**.

**Prior handoff:** [`2026-09-03-tenancy-restructure-admin-pages.md`](2026-09-03-tenancy-restructure-admin-pages.md).

## This session's commits

| Commit | Branch | What |
|---|---|---|
| `286ca2af` | `plan/dashboard-redesign-console` | `docs(plans)`: the implementation plan **plus** the design handoff bundle, which was untracked until now |
| this file | `plan/dashboard-redesign-console` | handoff |

## TL;DR

- The user asked whether Sonnet could take on the dashboard UI/UX rework. Answer: yes — the design
  handoff sitting untracked in `docs/design/Dashboard_redesign/` is an unusually complete spec
  (exact measurements, endpoint contracts, token mapping, file list). No GitHub issue exists for it.
- The user chose "write plan first". Ran the single-session planning workflow (code recon → precedent
  → chore sweep → draft → self-red-team against the live repo), no subagents.
- **Deliverable:** `docs/superpowers/plans/2026-09-04-dashboard-redesign-console.md` — 4 phases,
  15 tasks, 12 locked decisions, every path/symbol/test anchor Grep-verified. **No SQL migrations.**
- The design bundle (`ISSUE.md`, `README.md`, the `.dc.html` prototype, `support.js`, the
  `design_system/` kit) was **untracked** in the main checkout and is now committed alongside the
  plan, so `/execute-plan` can read the spec it argues from.

## What shipped

| File | Commit | Notes |
|---|---|---|
| `docs/superpowers/plans/2026-09-04-dashboard-redesign-console.md` | `286ca2af` | the plan; Phase 1 backend endpoints, Phase 2 tokens + console kit CSS, Phase 3 markup/CSS/JS rebuild, Phase 4 removal + chores |
| `docs/design/Dashboard_redesign/design_handoff_dashboard_console/**` (120 files) | `286ca2af` | the design handoff = the spec. `README.md` holds every measurement; option **1a** in the `.dc.html` is the approved layout |

## The five decisions that shape the work

Full table (D1–D12) is in the plan's "Decisions locked in" section. The ones that will surprise a
reader who only skims the design README:

1. **The prototype's amber is `var(--nx-accent)`, not a fixed hue.** The app ships indigo
   (`#4f46e5`) and amber is one of seven user-selectable accents (`html[data-accent="amber"]`); the
   designer's demo simply had amber on. `static/css/reporting-console.css` already sets this
   precedent verbatim. Only the **chart series** keep fixed colours, as new `--nx-series-1..5`
   tokens with dark twins.
2. **English is the source locale.** The README's German copy ("Aktualisieren", "Rückstand", …) goes
   into `translations/de/…/messages.po`; the code gets English msgids. Task 13 has the full mapping
   table.
3. **`api/dashboard/recent_activity` is deleted outright** — route, view, `recent_activity_rows()`
   in `nx_lib/workitem_sources.py`, its 7 integration tests, 2 unit tests, and the
   `test_create_app.py` endpoint inventory entry. Grep proved nothing else calls it.
4. **The 14/30/90 range rides the session** (`session['dashboard_range']`, set through the existing
   `POST api/dashboard/set_filter`), not `nx_lib/ui_prefs.py` — that module is the pre-paint
   appearance allowlist, and the process filter already persists exactly this way.
5. **Sparklines are hand-built inline SVG polylines**, not four extra Chart.js canvases.

## Next steps

1. **Resume in the worktree**, not the main checkout: `.claude/worktrees/plan-dashboard-redesign-console`
   on `plan/dashboard-redesign-console`. First copy the secrets in (gitignored, absent in worktrees):
   `cp ../../../env/INT.env ../../../env/TEST.env env/`; prepend `C:\dev\nexora\.venv\Scripts` to
   `PATH`.
2. `/execute-plan` on `docs/superpowers/plans/2026-09-04-dashboard-redesign-console.md`, starting at
   **Task 1** (`_kpi_daily_counts`, in `nx_lib/views/dashboard.py`). Phase 1 is pure backend and
   fully unit-testable — no browser needed until Task 14.
3. After Phase 3, run the Task 14 browser sweep and `SendUserFile` the six screenshots (remote
   owner can't see the screen): `var/screenshots/dashboard_console_{1a,range90,hourly,narrow,dark,violet}.png`.
4. Consider filing a GitHub issue from `ISSUE.md` (`/write-issue`) if the work should be tracked —
   the plan does not assume one exists, and no issue number is referenced anywhere in it.
5. Merge the worktree back into `refactor/255-admin-nav-tenancy-labels` when the plan is executed
   (`/execute-plan --merge-worktree` does this).

## Gotchas & notes

- **Nothing is red.** No source file was touched this session; the only change is documentation.
- **The design bundle is now tracked**, so it no longer shows as untracked noise in the main
  checkout. `docs/` is already inside the `deploy.yml` exclusions, so no `/XF`/`/XD` change is
  needed for the 120 new files.
- **Two in-flight plans touch the same code and are sequenced in the plan header:**
  - `docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md` renames
    `dashboard.filter.process.*` → `process.<client>.<name>.view` and replaces `_allowed_processes()`'s
    parser. The dashboard plan deliberately **never touches `_allowed_processes()` or
    `_PROCESS_PERM_PREFIX`**, so whichever lands second only re-runs its own tests.
  - The #255 tenancy work **on this very branch** (migration `0097`) owns the two-title
    `dashboard_tenant` block and `session['dashboard_tenant']`. Both are kept; only the marketing
    subtitle is dropped.
- **`test_dashboard_signin_escape.py` reads `templates/dashboard.html` as text** and asserts
  `"fullname|e" in src` (security audit #193, finding 9). The new head line must keep the expression
  `name="<strong>"|safe ~ fullname|e ~ "</strong>"|safe` character-for-character.
- **`test_kpi_stats_authed_returns_zeros`** in `tests/integration/test_dashboard_routes.py` asserts
  the early-return dict **exactly**, so widening `kpi_stats` breaks it by design — Task 5 Step 3 has
  the replacement assertion.
- **Four anchors were wrong in the first draft and corrected during verification** (kept here so
  nobody "fixes" them back): the refresh button is `.nx-btn--secondary`, not `--ghost`; the new CSS
  test must read through the file's existing `REPO_ROOT`, not a relative `Path`; a token test must
  split on `"\nhtml.dark {"` because the bare string `html.dark` first appears in the sheet's
  table-of-contents comment; and `"processed_week"` is a live assertion in a test, not just dead code.
- **`dbo.BacklogHistory` lives on the Statistics DB, which nexora does not track under `sql/`** — the
  standalone collector `ops/backlog_history/backlog_history.py` creates it. Hence **no migration**.
  Schema: `SnapshotAt DATETIME2(0)`, `SourceCode`, `ClientName`, `ProcessName`, `BacklogCount`.
- **Commits from this worktree need `SQL_SYNC_SKIP=1`** — the worktree has no `env/*.env`, so the
  `sql-migrate-int` and `sql-sync-check` hooks abort with `Missing DB_SERVER_PRD / DB_UID / DB_PWD in
  env`. Copying the env files in (step 1 above) also fixes this. Never `--no-verify`.
- **`static/css/dashboard.css` is ~70 % dead code** (`.progress-*`, `.timeline-*`, two unused
  keyframe animations). Task 9 Step 1 re-proves it with a grep before deleting.

## Untracked / left for owner

- Nothing. The main checkout still has its own pre-existing uncommitted work in
  `nx_lib/tenant/registry.py` and `nx_lib/views/tenant.py` — **not this session's**, deliberately
  untouched, do not bundle it.
- Not pushed, no PR opened (remote/commit-only rule). The owner pushes.

## How to verify

Nothing to run — the change is documentation only. To sanity-check the plan's anchors yourself:

```bash
# every file the plan names as "Modify" must exist
ls nx_lib/views/dashboard.py static/css/dashboard.css static/css/nexora-ui.css \
   templates/dashboard.html templates/js/_dashboard_js.html \
   tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py \
   tests/e2e/test_dashboard.py tests/unit/test_ui_chrome_regressions.py

# the baseline suites the plan will extend are green today
python scripts/test_db_reset.py && pytest tests/unit tests/integration -q
```

## Resuming in a fresh session

Run `/reset-session` — the pending flag points here. To target this file explicitly:
`/reset-session docs/superpowers/handoffs/2026-09-04-dashboard-redesign-console-plan.md`.
Then read the plan (`docs/superpowers/plans/2026-09-04-dashboard-redesign-console.md`) and its spec
(`docs/design/Dashboard_redesign/design_handoff_dashboard_console/README.md`) before touching code,
and work **inside the worktree**.
