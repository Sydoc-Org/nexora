> **Superseded next-day:** Task 8 is now done too — see
> `2026-07-14-docfield-permission-gating-task8-verified.md` (DB/VPN access came back, owner
> mapped the field, dropdown gate proven live with a screenshot). This plan is fully complete.

# Handoff — Permission-gated doc-fields (Validation User) — EXECUTED, 7/8 tasks (Task 8 blocked, owner-only)

**Date:** 2026-07-13 (evening) · **Branch:** `feature/2.5.64` · **commit-only (remote session — owner pushes)** · no plan worktree
**Prior handoff:** `2026-07-13-docfield-permission-gating-plan.md` (same day — plan written, ready to execute)
**Plan executed:** `docs/superpowers/plans/2026-07-13-docfield-permission-gating.md`
**SDD ledger:** `.superpowers/sdd/progress.md` (full per-task review record; gitignored scratch)

## TL;DR

- **All 7 code/doc tasks executed, reviewed, and committed** (9 commits total incl. one
  mid-plan test-strengthening fix and one final-review fix). Feature: a new searchable
  doc-field "Validation User" plus a full permission-gating mechanism — fields flagged
  `IsSensitive` in `dbo.Search_Field_Labels` are hidden (name AND value) from users without
  `workitems.filter.documentfields.sensitive`, across six surfaces.
- **Final whole-branch review (opus) caught a real Critical the per-task reviews missed:**
  Task 3 gated `api_config_fields`, but the Workitems page's doc-field dropdown is actually
  fed by a *different*, duplicate-logic route (`api_workitems_page_init`) that was left
  completely unfiltered. Fixed by mirroring the same gating pattern into it; re-review clean.
- **Task 8 (live INT browser verification) is BLOCKED, not done.** `nx --doctor` this
  session shows every project database + Octopus unreachable (VPN/network-level block on
  this remote environment) — a hard external blocker, not something resolvable here. Also
  structurally gated on an owner action regardless of connectivity (see below).
- **Two independent concurrent-session discoveries this session, both benign, already
  resolved — see Gotchas.**

## This session's commits (oldest → newest)

```
a32c7c7  feat(db): add Validation User doc-field + sensitivity flag (0035)         (Task 1)
9b54052  feat(workitems): sensitive doc-field strip/filter + cached readers        (Task 2)
bdfbb11  feat(workitems): hide sensitive fields from doc-field dropdown            (Task 3)
ceae954  test(workitems): assert distinct cache entries in perm test              (Task 3 fix)
ae83bcb  feat(workitems): refuse sensitive doc-fields in values API and search     (Task 4)
0dbceeb  feat(workitems): strip sensitive fields from the detail panel             (Task 5)
0c7935e  feat(workitems): strip sensitive fields from CSV export                   (Task 6)
97a5de2  docs: permission-gated doc-fields (Validation User)                       (Task 7)
a11c68e  fix(workitems): gate page_init field config, add search-skip test         (final review fix)
```
(Task 8 has no commits — verification-only, and blocked. Base was `674207d`, the prior
handoff commit. Two unrelated commits from a concurrent session — `b7531ba`, `84fa104`,
`e0602cf`, `dbe78b9` — landed interleaved in the branch history during this session; see
Gotchas, not part of this plan.)

## What shipped

| Task | What | Files | Commit(s) |
|---|---|---|---|
| **1** Migration 0035 | `col_validationuser` on `SearchConfig`; `IsSensitive BIT` + seeded `validationuser` label row (EN/DE/FR/IT) on `Search_Field_Labels`; new permission `workitems.filter.documentfields.sensitive` granted to all `admin.view` profiles. Mapping column left NULL (owner action). | `sql/_migrations/NexoraDB/0035_*.sql` + 2 regenerated dumps | `a32c7c7` |
| **2** Sensitivity helpers | Pure `_norm_field_token`/`strip_sensitive_fields`/`drop_sensitive_options`; cached readers `get_sensitive_field_keys`/`_tokens`; per-request gates `sensitive_blocked_keys`/`_tokens`. Unused by design at this point. | `nx_lib/views/workitems.py`, `tests/unit/test_docfield_sensitivity.py` | `9b54052` |
| **3** Search dropdown | `api_config_fields`: perm-state `_s{0\|1}` cache-key suffix + pre-cache filtering of both `search_options` and `db_labels_map`. | `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py` | `bdfbb11`, `ceae954` |
| **4** Values API + search | `api_docfield_values` refuses sensitive fields (`[]`); both `_get_workitems_data` blocks (default + MS02) skip sensitive field pairs. SQL-injection whitelist guard ordering preserved. | `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py` | `ae83bcb` |
| **5** Detail panel | `strip_sensitive_from_detail` strips both `fields` and `field_sources` (highlight overlay data too), wired into `get_media_info`'s `_suppress`, post-cache. | `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py` | `0dbceeb` |
| **6** CSV export | `_strip_export_fields` strips `details_map` before headers/rows are built; correctly reassigns rather than mutates a potentially cache-shared `fields` dict. | `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py` | `0c7935e` |
| **7** Docs | CHANGELOG entry + one-sentence CLAUDE.md note. No new how-to warranted (Grepped `docs/`, nothing relevant found). | `CHANGELOG.md`, `CLAUDE.md` | `97a5de2` |
| **Final-review fix** | `api_workitems_page_init` (the *actual* dropdown-feeding route) mirrored with the same gating as Task 3; 2 new committed regression tests for `_get_workitems_data`'s sensitive-skip. | `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py` | `a11c68e` |

**No new top-level files/dirs** (no `deploy.yml` exclude changes needed). **No new i18n
strings** (doc-field labels are DB-driven, not `gettext` — no pybabel cycle needed).

## How it was executed (subagent-driven development)

Fresh implementer subagent per task → task review (spec + quality) → fix loop → next; then
one opus whole-branch review → one fix round → opus re-review. Models: haiku for mechanical
tasks (1, 2, 7), sonnet for tasks touching route wiring/security-relevant ordering (3, 4, 5,
6, the final fix), opus for the final whole-branch review and its re-review. Full trail
(all per-task ✅/❌ verdicts, evidence, file:line citations) in `.superpowers/sdd/progress.md`.

**Review cycles that found and fixed real issues:**
- **Task 3:** the brief's own integration test asserted only `status_code == 200` on both
  calls (plan-mandated, since the test DB lacks the `SearchConfig` table) — it would have
  passed even with the fix reverted. Strengthened to assert on `nx_lib.views.workitems.cache`
  directly for two distinct, non-colliding entries; verified the strengthened assertion would
  genuinely fail if the cache-key suffix were reverted.
- **Final whole-branch review (the big one):** independently confirmed by the controller via
  direct Read/Grep before accepting — `api_workitems_page_init` builds an *identical*
  `field_config` to `api_config_fields` but with **no filtering and the old un-suffixed cache
  key**, and it is what `templates/js/_workitems_overview_js.html` actually fetches to
  populate the Workitems page's doc-field dropdown. `api_config_fields`'s only frontend
  caller, `fetchFieldConfig()`, has **zero call sites** anywhere in templates — Task 3 gated
  a dead code path. Once the owner maps `col_validationuser`, this would have leaked the
  field's NAME (not value — the other 5 gates were correct) to unpermissioned users on the
  main UI. Fixed by mirroring the identical Task-3 pattern into the real route; re-review
  (fresh-eyes, independently checked for a THIRD ungated field-config builder — found none)
  came back clean, zero Critical/Important.

## Next steps (ordered)

1. **Owner: perform Owner actions 1-2 from the plan** (required before the feature does
   anything visible):
   - Map the field: `UPDATE dbo.SearchConfig SET col_validationuser = '<RealColumn>' WHERE
     ProcessName = '...' AND ClientCode = '...'` — until this runs, "Validation User" is
     invisible everywhere (harmless, by design).
   - Confirm the Octo extraction target-key normalizes to `validationuser`/a seeded label
     (or add the spelling as an extra `Search_Field_Labels` label) so the detail-panel/CSV
     token-match actually catches it.
2. **Owner: run Task 8 (live INT browser verification) locally**, with VPN access — this
   environment cannot reach `DB_SERVER_PRD` at all (see Gotchas). Checklist is in the plan's
   Phase 6 / Task 8: dropdown absent/present, values API `[]`/values, detail panel
   absent/present, CSV column absent/present, each for a no-perm vs. perm user. Restart the
   dev server first (`nx -u -b --loginas:<user>`) since templates/JS are process-cached
   (though this feature added no template changes — server-populated dropdowns).
3. **Owner: grant the permission** to the right non-admin profiles via the admin UI (`0035`
   only auto-grants to `admin.view` profiles).
4. **Owner: PROD rollout** — `0035` reaches PROD automatically on the next deploy to `main`,
   or immediately via `python scripts/db-migrate.py --env PROD` (idempotent).
5. **Owner: review + push `feature/2.5.64`** (full pre-push gate incl. Playwright e2e — the
   owner has DB/VPN access this session did not).

## Gotchas & notes (READ)

- **TEST/INT SQL Server (and every other project DB) was unreachable this entire session.**
  Confirmed repeatedly, and definitively via `nx --doctor`: NexoraDB, OctoDB, StatisticsDB,
  GeneraliDB, all 3 MS02 Postgres targets timeout ("Check DB_SERVER_PRD reachability + VPN"),
  plus Octopus DNS resolution fails (`int-dps.sydoc.ch`). This blocked every DB-backed
  integration test (`user_client`/login-dependent) from getting a genuine pytest GREEN —
  each such task instead relied on (a) DB-independent pure/unit tests where possible
  (genuinely RED→GREEN: Tasks 2, 5, 6), and (b) for DB-dependent tests (Tasks 3, 4, final
  fix): careful code-reading against exact quoted brief snippets, plus uncommitted manual
  verification scripts exercising the real, unmodified code with only the DB connection
  layer substituted (session/cache mocking, SQL-text-capturing fake cursors). **Re-run the
  full `tests/integration/test_workitems_routes.py -k docfield` sweep once DB access is
  available** to convert "logically verified" into an actual pytest pass — the final
  reviewer flagged this as the one non-blocking outstanding item.
- **Migration `0035` DID apply to INT successfully early in the session** (Task 1's
  pre-commit hook passed genuinely) — the DB outage above set in partway through, and
  briefly recovered again for the final-fix commit's migration-check hook. It is
  intermittent, not a permanent condition; INT itself may be reachable again by the time you
  read this, even though the remote *execution* environment's VPN access is not the same
  thing as INT's own health.
- **Concurrent session #1 (docs-only, no conflict):** another Claude Code session ran
  directly in this same working directory (`C:\dev\nexora`, no worktree) planning an
  unrelated "dashboard-chart-recent-validations-404" bugfix. Its commits (`b7531ba`,
  `84fa104`) are docs-only (a new plan file + a coordination banner added to *this* plan's
  earlier handoff) and don't touch anything this plan touched.
- **Concurrent session #2 (code, no conflict):** the same or a related session later
  committed and then immediately reverted a real code fix on this branch (`e0602cf` /
  `dbe78b9`, `templates/handlers/_error_base.html` + `templates/js/_dashboard_js.html` +
  `tests/unit/test_template_url_prefix.py`) — net-zero, and it later created its own worktree
  at `.claude/worktrees/plan-dashboard-chart-recent-validations-404` (branch
  `plan/dashboard-chart-recent-validations-404`) for its actual execution, properly isolated.
  No file overlap with this plan at any point.
- **User's own unrelated work, left untouched:** an untracked `package.json`/
  `package-lock.json`/`node_modules` (npm package `headroom-ai`) sat in the repo root all
  session. Flagged to the user mid-session out of an abundance of caution (peer-deps on
  AI-provider SDKs, no code in this repo references it) — the user confirmed it's their own
  intentional download, unrelated to this plan. Left alone, not part of any commit here.
- **Cache-safety patterns, don't undo:** `media_info_{wid}` strip runs *post-cache* inside
  `_suppress` (never before a cache write); `api_config_fields`/`api_workitems_page_init`
  cache keys both carry `_s{0|1}`; `_strip_export_fields` reassigns `detail["fields"]` to a
  fresh dict rather than mutating in place (it can alias the shared `media_info_{wid}` cache
  object on a cache-hit path in `export_workitems_csv`'s `_fetch` — verified safe by the
  final reviewer precisely because of the reassignment-not-mutation pattern).
- **Two field namespaces, verified not swapped anywhere:** `sensitive_blocked_keys()`
  (exact FieldKey match) gates doc-field SEARCH surfaces (Tasks 3, 4, final fix);
  `sensitive_blocked_tokens()` (normalized FieldKey + 4 labels, fuzzy) gates Octo EXTRACTION
  surfaces (Tasks 5, 6). Independently re-checked at the final review.
- **`SQL_SYNC_SKIP=1`** was used repeatedly for commits, always for the documented
  DB-unreachable reason, never `--no-verify`. All commits landed with ruff/ruff-format/
  gitlint genuinely passing.
- **Commit title gitlint note:** Task 7's title ("docs: permission-gated doc-fields
  (Validation User)") is a noun phrase, not an imperative verb — a reviewer flagged this as
  a violation, but independently verified false: this repo's actual `.gitlint` has no
  imperative-mood rule (only title-length/body-length/conventional-commit-type), the commit
  already passed the real hook, and there's repo precedent for this exact style (e.g.
  `3c9d117`). No action needed if you see this pattern again.

## Owner actions baked into the plan (not the agent's job)

See "Next steps" above (1, 3, 4) — column mapping, permission grants, PROD rollout timing.

## Untracked / left for owner

- Working tree clean at handoff time except the user's own unrelated `package.json`/
  `package-lock.json`/`node_modules` (confirmed intentional, not this plan's concern).
- No worktree was created for this plan (recorded as such in the prior handoff) — nothing to
  merge or clean up.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
git log --oneline 674207d..a11c68e     # this plan's 9 commits (interleaved with 4 non-plan
                                         # commits from a concurrent session — see Gotchas)
git status --porcelain                  # clean except the user's own unrelated npm files

# DB-independent tests (should be green in any environment):
.venv\Scripts\python -m pytest tests/unit/test_docfield_sensitivity.py -q

# DB-dependent tests (need VPN/DB access this session didn't have — re-run once available):
.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k "docfield or config_fields or strip_sensitive or strip_export" -q
```

## Resuming in a fresh session

Task 8 (live INT browser verification) is the only remaining item, and it's owner-only (VPN
access + the two owner actions above are prerequisites this session cannot satisfy). If
resuming to do that work: `/reset-session` (the `var/handoff-pending` flag points here), then
open the plan's Phase 6 / Task 8 checklist directly — no further planning needed.
