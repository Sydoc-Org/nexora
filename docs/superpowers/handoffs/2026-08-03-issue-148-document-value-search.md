# Handoff — Issue #148: Document Value Search, end to end

**Date:** 2026-08-03 · **Branch:** `feature/2.5.65` (188 commits ahead of `origin/main`) ·
**commit-only — owner pushes**
**Prior handoff:** `2026-07-29-issue-113-version-display.md`

## TL;DR

- **GitHub issue #148 ("Document Field Search") is closed.** The doc-field filter became
  **Document Value Search**: its own always-visible section, value-first (no field = match any
  permitted field), per-row **operators** (contains, `=`, `≠`, starts with, ends with, does not
  contain), **AND/OR** combinators between rows, and a query-builder UI iterated four times with
  the owner until approved.
- A **smart-search hero** was built, shipped, then **removed on owner decision** mid-session
  (commits `b719629` → `314a08d`); its stale-response fetch guard survived as a real bugfix.
- **Everything verified live on INT** (Playwright + direct API assertions, e.g. `=040 OR =041`
  = 71 = 29+42 exact union), 159 targeted tests green, i18n de/fr/it complete.
- **A concurrent session (autopilot) was committing on this branch all day** — it swept
  uncommitted work twice, absorbed one i18n batch into its own commit, and its missing test-schema
  update broke 67 integration tests (fixed here, `aea3998`).

## This session's commits (oldest → newest)

Owner/concurrent-session commits are interleaved and not listed except where relevant.

- `85ba34d` feat(workitems): value-first Document Value Search (#148)
- `78fde0e` docs(workitems): changelog, docs and i18n for value search (#148)
- `b85c4c5` test(workitems): cover value-first any-field doc search (#148)
- `a68b890` fix(workitems): drop stale list responses on rapid re-filter (#148)
- `b719629` feat(workitems): smart search hero with AND-chips (#148) — later removed
- `1a64598` style(workitems): align smart-search icon/input padding (#148) — later removed
- `314a08d` revert(workitems): drop the smart search hero (#148)
- `aea3998` test(sql): add Users.LastLoginAt + MaintenanceBanner to the test schema
- `00dc43f` feat(workitems): operators + AND/OR rows in Document Value Search (#148)
- `b6f5da0` docs(workitems): changelog, docs and i18n for search operators (#148)
- `d349cfa` style(workitems): query-builder layout for Document Value Search (#148)
- `d188a32` style(workitems): collapse boolean rail for a lone filter row (#148) — superseded
- `d7420d6` style(workitems): full-width filter rows, AND/OR between rows (#148)
- `8f177f9` style(workitems): tuck the row remove-x inside the value input (#148)

**Absorbed by a concurrent-session commit:** the smart-search-hero i18n batch (pot + de/fr/it po/mo)
landed inside `6899df2 feat(dashboard): add last sign-in to the sign-in note (#146)` — the two
sessions share the git index. Functionally fine, just attributed oddly; those strings were removed
again with the hero anyway.

## What shipped

| # | Change | Key files |
|---|---|---|
| 1 | **Value-first any-field search.** Empty `docfield` + value = OR across every permitted, non-sensitive column: widened UNION on the default SQL Server leg; multi-column specs into `resolve_ms02_docfield_ids` on the MS02 Postgres leg. `/api/docfield_values` with empty `field` returns labeled `{value, field}` suggestions (`_docfield_values_all_fields`); picking one locks the pair. Fail-closed contract extended: field-less pairs count as active. Root bugs killed: `\|\| 'doctype'` fallback in `fetchRowSuggestions` AND silent `fields[0]` auto-select in `fillDocFieldSelect`. | `nx_lib/views/workitems.py`, `templates/js/_workitems_overview_js.html`, `templates/workitems_overview.html` |
| 2 | **Operators + AND/OR.** `docop` (contains/eq/neq/startswith/endswith/ncontains) + `doccomb` (and/or) ride as index-aligned lists next to docfield/docvalue (row 1 carries a hidden `and`). Whitelisted maps `DOCFIELD_OPS` / `_MS02_DOCFIELD_OPS` — never interpolated. Both legs now FOLD pairs left-to-right (`(A AND B) OR C`); AND-only early-breaks removed; MS02 eq/neq escape LIKE metachars and run via ILIKE for CI parity. | `nx_lib/views/workitems.py`, `nx_lib/workitem_sources.py` |
| 3 | **Query-builder UI** (4 iterations with owner): every row a full-width fused segmented control (field \| op \| value, collapsed inner borders, rounded ends); AND/OR as a pill on a hairline connector line BETWEEN rows; remove-× inline inside the value input's right padding so all rows share identical geometry. Operator/combinator change auto-refetches. | `templates/workitems_overview.html`, `templates/js/_workitems_overview_js.html` |
| 4 | **Stale-response guard.** Rapid re-submits of the workitems list could resolve out of order and the older response overwrote the newer render. Sequence counter in `fetchAndUpdateWorkitems`; pre-existing page-wide bug. | `templates/js/_workitems_overview_js.html` |
| 5 | **Test-schema catch-up** (not #148): concurrent session's `LastLoginAt` (migration 0049) + `MaintenanceBanner` table were missing from hand-maintained `sql/test/schema.sql`; the maintenance lockout fails closed on the missing table and 302s every test login — 67 integration tests were red branch-wide. | `sql/test/schema.sql` |
| 6 | Tests (`b85c4c5`, in `00dc43f`): value-first widening, sensitive-column exclusion, labeled endpoint mode, op/comb whitelisting, OR-fold no-early-break, resolver OR/forced-empty/eq-escaping. Changelog + `docs/design/ms02-multisource.md` doc-field section updated. i18n de/fr/it for all new strings (pybabel fuzzy guesses hand-corrected each cycle). | `tests/integration/test_workitems_routes.py`, `tests/unit/test_workitem_sources.py`, `CHANGELOG.md`, docs |

## Next steps (ordered)

1. **Owner: review + push** `feature/2.5.65` (188 ahead). Pre-push gate runs the FULL suite incl.
   e2e — run `python scripts/test_db_reset.py` first (memory: stale NEXORA_TEST state) and check the
   concurrent session has committed its in-flight work (`CHANGELOG.md` staged, `dbo.Users.sql` dump
   drift, `static/css/reporting.css` were uncommitted at handoff time — all theirs).
2. Optional follow-ups parked deliberately: chips/URL persistence for extra filter rows beyond
   row 1 across full page reloads (pre-existing ceiling, unchanged); "matched in <field>" badge on
   result rows (owner declined — labeled suggestions cover it).

## Gotchas & notes

- **Concurrent autopilot session on the same checkout/branch all day.** It hard-reverted
  uncommitted edits twice mid-session (recovered by re-applying via idempotent python scripts +
  committing in the same shell invocation), shares the git index (staged files get absorbed into
  its commits — commit immediately after staging), merged `worktree-issue-147-stage-filter`
  mid-flight, and held the Playwright MCP browser profile (this session drove its own chromium via
  `.venv` Playwright instead). The `.pixel-agents` PostToolUse hook (deferred cleanup item)
  forwards every tool event to a live local server — still suspected in the revert loop; consider
  finally unplugging it.
- **`SQL_SYNC_SKIP=1`** was needed on most commits: the concurrent session's migration `0049` was
  applied to INT but its per-object dump wasn't committed yet, so `sql-sync-check` failed on drift
  that wasn't ours. Each commit message records the reason.
- The two removed hero commits (`b719629`, `1a64598`) are still in history; the revert commit
  `314a08d` documents why. History is append-only per repo policy — no rebase.
- pybabel `update` fuzzy-matching invents WRONG translations for new msgids every cycle
  ("Dokumentenliste" for "Document Value Search", "Ende" for "AND") — always sweep `#, fuzzy`
  entries after update.
- Tailwind v4 layer trap hit again: `pl-11`/`rounded-*` utilities lose to unlayered `.nx-input`;
  the fused-control corners use trailing-bang utilities (`rounded-r-none!` etc.).

## Untracked / left for owner

- `CHANGELOG.md` (staged), `sql/NexoraDB/Tables/dbo.Users.sql` (INT-sync drift for migration
  0049), `static/css/reporting.css` (+28), `.claude/commands/write-issue.md` (untracked) — all
  belong to the concurrent session / owner; deliberately not committed here.
- Screenshots from live verification: `var/screenshots/issue148_*.png`, `ops148_*.png`,
  `chrome148_*.png`, `hero148_*.png` (gitignored).

## How to verify

```powershell
# targeted suites (all green at handoff)
.venv\Scripts\python.exe -m pytest tests/integration/test_workitems_routes.py tests/unit/test_workitem_sources.py -q   # 159 passed
.venv\Scripts\python.exe -m pytest tests/unit/test_translations.py tests/unit/test_template_url_prefix.py -q          # 8 passed

# live (INT), server on 127.0.0.1:8000 via bin\nx.ps1 -u
# =040 OR =041 across all fields -> 71; =040 AND =041 -> 0; eq narrows vs contains (29 vs 50)
```

## Resuming in a fresh session

Read this file. Issue #148 is closed and fully shipped; there is no open plan for it. If the owner
reports UI feedback post-push, the whole surface lives in `templates/workitems_overview.html`
(rows + template) and `templates/js/_workitems_overview_js.html` (delegated handlers in
`initMultiDocFilters`). Note `/reset-session <path>` can target this file explicitly.
