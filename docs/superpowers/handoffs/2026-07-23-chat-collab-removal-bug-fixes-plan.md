# Handoff — Bug hunt (57 findings) + chat/collab/notification removal plan WRITTEN, ready to execute

**Date:** 2026-07-23 · **Branch:** `feature/2.5.65` (no worktree — clean tree, planned directly on
the branch) · **4 commits ahead of `origin/main`, unpushed** · **commit-only — owner reviews and pushes**
**Prior handoff:** `2026-07-22-reporting-redesign-dashboard-builder-execution-complete.md`

## TL;DR

- **A full multi-agent bug hunt ran this session** across every route (193), view module, JS partial,
  and test file, plus a live browser sweep and the full test suite. Result: **57 adversarially-verified
  code bugs (3 critical), 21 broken/meaningless tests, 25 test gaps, 15 untested surfaces.** Findings
  with per-bug failure scenarios are in **`var/bug-hunt-report.md`** (gitignored — on disk only, also
  delivered to the owner in-chat).
- **The owner then asked for a plan** to (A) remove chat + ALL workitem collaboration (tags, priority,
  assignments, comments incl. @mentions) + the notification bell — "nobody uses it" — and (B) fix the
  surviving bugs. That plan is **written, red-teamed, anchor-verified, and committed**:
  `docs/superpowers/plans/2026-07-23-chat-collab-removal-bug-fixes.md` (11 phases, 65 tasks).
- **Nothing is implemented yet.** This session ended at "plan committed." The next step is
  `/execute-plan` (with Sonnet) against that plan file.
- **Only `9680933` is this session's commit.** The other 3 unpushed commits (`c2a6fbf`, `66c8c5a`,
  `1c08a96`) are the owner's own pre-existing work — do not touch/rebase them.

## This session's commits (oldest → newest)

- `9680933` docs(plans): add chat-collab-removal-bug-fixes implementation plan

(The bug-hunt report `var/bug-hunt-report.md` is gitignored and intentionally NOT committed.)

## What shipped (the plan's shape)

**PART A — removal (Phases 1–6, Tasks 1–12), sequenced frontend → backend → bell → migrations → docs:**

| Phase | Removes | Key anchors |
|-------|---------|-------------|
| 1 | Chat page + all 6 routes + nav wiring | `nx_lib/views/chat.py` (deleted), `chat.view` perm, `chat.html`/`_chat_js.html` → `archive/` |
| 2 | Collaboration UI (shared detail panel + overview) | `buildCollaborationMarkup`, `buildReadonlyCommentsMarkup`, `renderTagsInDetails`, `handleSetPriority` |
| 3 | Collaboration backend | tag/priority/assignee/comment routes in `workitems.py`, the `Workitem_Metadata` joins + `TagsJSON` in `workitem_sources.py` |
| 4 | Notification bell | `nx_lib/views/notifications.py`, `nx_lib/notifications.py`, header bell UI |
| 5 | DB migrations `0042` (decapitate 9 tables via `sp_rename` + drop Users FKs) + `0043` (delete 8 dead permission rows child-first) | `sql/_migrations/NexoraDB/` |
| 6 | Docs closeout | CLAUDE.md, README, CHANGELOG Removed |

**PART B — surviving bug fixes (Phases 7–11, Tasks 13–65):** critical cross-tenant PDF cache leak →
access-control gaps → compound-identity → high correctness (reporting studio, ping pool, media) →
medium (compressed) → i18n cycle + CHANGELOG Fixed + full-suite gate. **The 9 bugs living inside
removed code are VOIDED** by their removal task — no fix task exists for them, by design.

## Next steps (concrete, ordered)

1. **Owner: review the plan** `docs/superpowers/plans/2026-07-23-chat-collab-removal-bug-fixes.md` —
   especially the "Decisions locked in" table and "Owner actions" (dev_login guard D-DEVLOGIN is GATED
   on Owner action 2; CSV heavy-include rule D-CSVLIM on Owner action 5).
2. **Execute:** `/execute-plan` (Sonnet) — resume point is Task 1, PHASE 1. The plan is
   subagent-driven-development ready (checkbox steps, TDD, paste-ready commit messages).
3. **Do NOT reorder phases** — the pre-commit hook auto-applies migrations to INT at commit time, so
   every code reference to a dead table/permission must be gone (Phases 1–4) before the `0042`/`0043`
   commits (Phase 5). This is D-SEQ.
4. After execution: owner reviews + pushes (pre-push gate runs the FULL suite incl. e2e —
   `scripts/test_db_reset.py` first).

## Gotchas & notes

- **`var/bug-hunt-report.md` is gitignored** (var/ is ignored) — it exists on disk for the executor,
  but a `var/` cleanup would break the plan's "see the report for per-bug detail" references. Each
  task carries its own defect description, so the plan is self-sufficient without it.
- **Two "comment tables":** `Workitem_Comments` AND `Comment_Mentions`. Nine tables total get
  decapitated. `Workitem_Metadata` is 100% collaboration (whole-table rename is safe — verified).
- **No `notifications.*` permission code exists** — the bell routes are session-gated only (`if
  "userid" not in session`). The 8 dead permission codes are the chat + tag/priority/assign/comment
  ones (incl. the real camelCase `workitems.filter.assignedUser`).
- **The shared detail panel has THREE consumers** (workitems row-expand, prepared-docs preview,
  reporting drill drawer) — collaboration must be pruned from all three, in both the editable and
  readOnly branches. Keep fields/images/source-highlighting/Octo audit-history (`get_audithistory` is
  the Octo processing trail, NOT a user-action log).
- **Already fixed in 2.5.64 (PR #124) — the plan explicitly excludes these** so nothing is re-done:
  invoice-PDF IDOR, PDQM scope, dashboard KPI guards, 2FA rate-limit, password-reset uniform message
  (today's residual is the timing oracle only), delete-user atomicity, recent-activity client_hint,
  CSV compound-id keys, notification-bell XSS.
- **Test suite state right now:** e2e = 180 passed (green). unit+integration = 1337 passed, but 5
  integration tests "fail" in a full run and pass in isolation — an order-dependent flask-cache state
  leak (the limiter is reset between tests, the cache is not). That flake is itself in the report as a
  test-infra finding; it is NOT introduced by this session (docs-only commit).
- **The coverage ratchet is decorative** — all 24 thresholds in `test_coverage_thresholds.py`
  unconditionally `pytest.skip`; the enforcement step was never built (report finding).

## Untracked / left for owner

- `var/bug-hunt-report.md` — gitignored deliverable; already sent to the owner. Not committed.
- The 3 pre-existing unpushed owner commits (`c2a6fbf`, `66c8c5a`, `1c08a96`) — the owner's own; left
  untouched.
- No migration files created yet — `0042`/`0043` are authored by the executor in Phase 5, each in its
  own commit (the pre-commit hook applies them to INT then).

## How to verify

- **The plan commit is docs-only:** `git show --stat 9680933` → one file.
- **Suite (optional sanity):** `.venv\Scripts\python scripts\test_db_reset.py` then
  `.venv\Scripts\python -m pytest tests/unit tests/integration -q` (expect the 5 order-dependent
  integration "failures" noted above — they pass with `-p no:cacheprovider` or run in isolation) and
  `.venv\Scripts\python -m pytest tests/e2e -q` (green).

## Resuming in a fresh session

Start here, then open `docs/superpowers/plans/2026-07-23-chat-collab-removal-bug-fixes.md` and run
`/execute-plan`. `/reset-session <path>` targets a specific handoff if `/reset-session` picks the
wrong one. Read `var/bug-hunt-report.md` for per-bug failure scenarios if a fix task needs more detail.
