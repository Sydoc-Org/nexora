# Handoff — Bug-hunt remediation: ALL 26 TASKS EXECUTED, reviewed, ready for owner push

**Date:** 2026-07-21 · **Branch:** `feature/2.5.64` (no worktree — plan ran directly on the branch)
**51 commits ahead of origin, unpushed** · **commit-only — owner reviews and pushes**
**Prior handoff:** `2026-07-20-reporting-redesign-dashboard-builder-plan.md` (a DIFFERENT plan, still
mid-execution in a concurrent session — see "Concurrent session" below; not this handoff's subject)

## TL;DR

- **All 26 tasks of `docs/superpowers/plans/2026-07-20-bug-hunt-remediation.md` are implemented,
  committed, and reviewed** — 6 phases, each closed out with a batched spec-compliance + code-quality
  review (per `/execute-plan`'s phase-review override), plus a final whole-branch review on the full
  plan diff. Every review came back **Approved, no Critical/Important findings**.
- **Two extra fixes landed beyond the 26-task list**, both dispatched by the controller after
  independent verification, not blindly on an implementer's word: a controller-dispatched follow-up
  (call it "Task 24b") closing a gap Task 24's own implementer flagged (`api_recent_activity` never
  had the `if returndata:` guard the defect assumed), and two small fixes closing a *second* instance
  of a bug class this plan already remediated once (Task 18's `conn=None`/`cursor=None` pattern), found
  by the final whole-branch reviewer in `nx_lib/views/auth.py`'s `init_2fa()` and `login()`.
- **Zero regressions.** The full non-e2e suite showed up to 8 failures at various points during
  execution; every single one was independently triaged (not trusted from an implementer's report) and
  confirmed either order-dependent test-isolation pollution (passes when re-run in a smaller batch —
  a pre-existing `Limiter.enabled` singleton issue), caused by the *concurrent* reporting-redesign
  session's uncommitted work (a missing i18n string, later committed by that session), or a
  pre-existing TEST-DB schema-drift issue (`Invalid object name 'MaintenanceBanner'`) in files this
  plan never touched.
- **Owner action required next:** review the diff, run the pre-push suite (incl. e2e —
  `scripts/test_db_reset.py` first per house convention), and push. The plan explicitly reserved
  push/PR for the owner throughout; nothing in this range was pushed.

## Concurrent-session note (read before touching the tree)

A **different, unrelated session was actively committing to this same branch/clone the entire time**
this plan executed — a UI "reporting redesign" overhaul (Indigo Studio), tracked by
`docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md` and its own handoff
(`2026-07-20-reporting-redesign-dashboard-builder-plan.md`). Of the 51 commits ahead of origin, roughly
half are that session's (touching `static/css/reporting.css`, `templates/_reporting_simple.html`,
`templates/js/_reporting_simple_js.html`, `nx_lib/views/reporting.py`, `tests/e2e/test_reporting_simple.py`
— never any file this plan touched). Every task in this session verified `git status`/`git diff --stat`
before staging and used explicit file paths — confirmed zero cross-contamination in every commit's
`git show --stat`. That other plan is **not finished** (its own handoff shows Tasks 1-3 of 17 done,
Task 4 in flight) — it is a separate, still-open piece of work, not something this handoff covers.

## This session's commits (oldest → newest, 30 total)

Phase 1 (XSS escaping):
- `dcdddd8` fix(generali): escape document free-text fields against stored XSS
- `a56c99d` fix(dashboard): escape recent-activity feed values against stored XSS
- `4230d06` fix(header): escape notification bell content against stored XSS

Phase 2 (access-control gaps):
- `68926b2` fix(invoices): scope PDF download to the caller's allowed clients
- `0bf2820` fix(generali): restrict PDQM reads to own records w/o edit perm
- `c77ede3` fix(dashboard): require dashboard.view on the four legacy KPI endpoints
- `d812dc5` fix(auth): rate-limit TOTP 2FA verification against brute force
- `c67d943` fix(auth): clear stale session in all login pre-auth branches
- `f496f10` fix(auth): use a uniform password-reset message to stop user enumeration
- `4cfbd6b` chore(changelog): defer bug-hunt entries to the consolidated task (controller correction —
  Task 9's commit had mistakenly added a per-task CHANGELOG entry, against the plan's explicit
  "one consolidated block at Task 23" constraint)

Phase 3 (compound-identity client+id fixes):
- `0aa4ae5` fix(dashboard): pass client hint resolving recent-activity workitems
- `c96d8dd` fix(workitems): key CSV export caches by client+id, not bare id
- `feaa3cc` fix(workitems): make "export selected" client-aware for colliding ids

Phase 4 (data-correctness/robustness — includes the plan's own flagged "highest blast radius" task):
- `7b55657` fix(admin): make user deletion atomic and cascade reporting artifacts
- `04bcc5b` fix(workitems): guard empty activity-ignore list in recent-activity
- `7b79d1d` fix(dashboard): compute backlog KPI with a real predicate, not all-rows
- `e9d6bbf` fix(invoices): keep partial results when one Bexio client search fails
- `0b16f05` fix(workitems): set prepared-docs in_octo from actual Octo resolution
- `f5f2150` fix(invoices): initialize conn/cursor so DB failure degrades gracefully
- `15b96c0` fix(invoices): log and return empty list on client-id lookup failure
- `ae45a16` fix(security): coerce ids so own-record generali edit/delete is allowed

Phase 5 (small functional fixes + the one consolidated i18n/changelog cycle):
- `d68b70c` fix(core): route "/" to permitted landing page, not dashboard
- `73181b9` fix(invoices): reconcile invoice status label with the status filter
- `1305ca6` chore(i18n): translations + changelog for bug-hunt remediation

Phase 6 (OPTIONAL backend plumbing — hunter-flagged, not second-verified per the plan, executed anyway
per explicit instruction to run the whole plan):
- `b65078f` fix(octo): return falsy instead of raising on fetch failure
- `e36afee` fix(dashboard): skip a failed Octo lookup instead of blanking the feed (controller-dispatched
  follow-up, "Task 24b" — Task 24's own implementer flagged that `api_recent_activity` never had the
  guard the defect text assumed, so Task 24 alone gave that caller zero improvement)
- `b0f84f5` fix(workitems): count PDF pages in media offset for source highlighting
- `ed742d0` chore(logging): route backend exception handlers through the app logger

Post-plan, from the final whole-branch review:
- `4d52045` fix(auth): init conn/cursor in init_2fa for graceful DB failure
- `d7f4f39` fix(auth): init conn/cursor in login for graceful DB failure

## What shipped (by category)

| Category | Tasks | Key files |
|---|---|---|
| Stored-XSS escaping | 1-3 | `_generali_documents_js.html`, `_dashboard_js.html`, `_header_js.html` |
| Access-control/permission gaps | 4-9 | `invoices.py`, `generali.py`, `dashboard.py`, `auth.py` |
| Compound-identity (client+id) | 10-12 | `dashboard.py`, `workitems.py`, `_workitems_overview_js.html` |
| Data-correctness/robustness | 13-20 | `admin.py`, `workitem_sources.py`, `dashboard.py`, `invoices.py`, `security.py` |
| Small functional fixes + i18n | 21-23 | `core.py`, `invoices.py`, `translations/*`, `CHANGELOG.md` |
| Backend plumbing (optional) | 24-26 | `octo.py`, `field_locations.py`, `table_locations.py`, `process_helpers.py` |
| Post-plan (final review) | — | `auth.py` (`init_2fa`, `login`) |

Consolidated CHANGELOG entry (all 22 bug-hunt fixes) is in `CHANGELOG.md` under `[Unreleased]/### Fixed`,
committed in `1305ca6`. Translations (de/fr/it, 21 new msgids) synced in the same commit — malformed-
msgstr trap checked programmatically (parsed both `.po` endpoints, diffed common-msgid content) and
confirmed clean, twice more during this session.

## Next steps (ordered)

1. **Owner reviews the diff.** Full range for this plan alone (excluding the concurrent session's
   interleaved reporting commits): every commit listed above under "This session's commits."
2. **Run the pre-push suite.** `.venv\Scripts\python scripts\test_db_reset.py` first (per house
   convention — stale `NEXORA_TEST` state breaks order-dependent tests), then the pre-push gate (full
   suite incl. Playwright e2e).
3. **Push `feature/2.5.64`.** Nothing in this range has been pushed.
4. **Nothing else queued from this plan** — all 26 tasks + the two follow-ups are done. The
  bug-hunt source triage doc (`var/bug-hunt-2026-07-20.md`, gitignored/local) can be archived/deleted
  once the owner confirms the fixes land.

## Gotchas & notes

- **Owner action items called out in the plan itself** (`docs/superpowers/plans/2026-07-20-bug-hunt-remediation.md`, "Owner actions" section) still apply:
  1. Review + push (this handoff's main ask).
  2. Delete-user report handling (D4 default: atomic delete-cascade, already implemented) — confirm
     this is the wanted behavior vs. reassigning reports to another admin.
  3. Backlog KPI semantics (D5) — implemented as "entered this process, not yet exported" (an honest
     structural approximation, NOT a literal match of the legacy C+A activity-type count, since the
     widget engine's `Statconfig` table has no activity-type column at all — this is disclosed in a
     code comment and the commit body). Confirm this approximation is acceptable, or say so if a
     different semantics is wanted.
  4. Two admin privilege-escalation endpoints (`save_user_overrides`, `save_access_profile`) are
     **explicitly out of scope** for this plan, pending an owner decision on who holds those permission
     codes.
- **Known, disclosed, NOT fixed (different bug shapes, correctly left as follow-ups rather than chased
  beyond this plan's scope):**
  - `nx_lib/views/auth.py`'s `verify_2fa()` POST branch has NO try/except/finally at all around its DB
    call — an unhandled 500 on DB failure (not the masking bug the two just-fixed instances had, just a
    plain missing guard).
  - `nx_lib/views/auth.py`'s `init_reset_password()` silently swallows errors with a bare `return` and
    leaks the DB connection on failure (no `finally`, so no `UnboundLocalError` — just silent + leaky).
  - `nx_lib/views/auth.py`'s `request_password_reset()` still has one `print(e)` at the account-lookup
    level (Task 26 was scoped to `octo.py`/`process_helpers.py` only); `scripts/news/sendReleaseNotice.py`
    has one too.
  - `escapeHtml` now exists as 4 verbatim copies across JS partials (`_generali_documents_js.html`,
    `_dashboard_js.html`, `_header_js.html`, plus the original in `_generali_project_management_js.html`)
    + 1 differently-shaped variant in `_reporting_ai_js.html` — all correctly escape `&<>"` but NOT `'`
    (safe today since every sink lands in a text node or a double-quoted attribute, never single-quoted
    — checked). Worth a future consolidation task if a 5th/6th copy appears.
  - Task 15's backlog-KPI "still outstanding" predicate guards `import_col` before referencing it but
    not `export_col` symmetrically (pre-existing pattern elsewhere in the same function, latent not
    introduced); combining `status:"Ready"` with an explicit date range on the export-date column
    yields 0 rows (self-disclosed, doesn't affect the default no-date widget).
  - 2FA's `@limiter.limit("10 per hour")` (D6, as specified) also counts GET page-loads and is keyed
    per remote address, so users behind a shared NAT/office IP share one pool — spec-compliant, not a
    defect, but worth the owner knowing.
- **Test suite state:** full non-e2e suite showed up to 8 failures at various points, ALL independently
  triaged as non-regressions (see TL;DR). If the owner sees these same failures on a fresh run, that's
  expected — re-run in isolation (e.g. `pytest tests/integration/test_dashboard_routes.py` alone) to
  confirm they clear.
- **`.superpowers/sdd/` ledger:** this plan's execution ledger lives at
  `.superpowers/sdd/progress.md` (gitignored) with full task-by-task detail, every controller
  investigation, and every phase review's findings — read it if you need more detail than this handoff
  gives. The *other* plan's ledger was archived to
  `.superpowers/sdd/reporting-redesign-dashboard-builder/` at the start of this session so the two
  didn't collide.

## Untracked / left for owner

- Nothing from this plan was left uncommitted — `git status` is clean for this session's work.
- The concurrent session's own uncommitted files (if any remain when you read this) belong to the
  reporting-redesign plan, not this one — don't stage/revert them as part of reviewing this work.

## How to verify

```powershell
git log --oneline feaa3cc..d7f4f39   # this plan's commits (minus interleaved reporting commits)
.\.venv\Scripts\python scripts\test_db_reset.py
.\.venv\Scripts\python -m pytest tests/unit tests/integration -q   # expect ~1331 passed, up to 8
                                                                     # known-unrelated failures (see above)
```

## Resuming in a fresh session

Nothing to resume — this plan is **complete**. `/reset-session` would land here via
`var/handoff-pending` only if no newer handoff exists; if the concurrent reporting-redesign session
also wrote a handoff around the same time, `/reset-session docs/superpowers/handoffs/2026-07-21-bug-hunt-remediation-execution-complete.md`
targets this file explicitly. The next piece of work is either: the owner reviewing/pushing this
branch, or resuming the *other* (reporting-redesign) plan at its own last checkpoint — see that plan's
own handoff for where it left off.
