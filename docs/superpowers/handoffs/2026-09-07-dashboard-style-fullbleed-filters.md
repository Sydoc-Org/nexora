> **Superseded the same day** — continue from [`2026-09-07-dashboard-card-chart-tools.md`](2026-09-07-dashboard-card-chart-tools.md).

# Handoff — dashboard restyle, full-bleed + Present, report-derived filter bar

**Date:** 2026-09-07 · **Branch:** `refactor/255-admin-nav-tenancy-labels` · nothing pushed ·
commit-only. **A parallel session commits on this same branch — read Gotchas first.**

**Prior handoff:** [`2026-09-07-wizard-curation-and-dashboard-pieces.md`](2026-09-07-wizard-curation-and-dashboard-pieces.md)
(same date — pass this file's path to `/reset-session` explicitly).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `cb7d4376` | dashboard cards wear the Results tab's Console look (flat KPI tile, chart/table flush, each of Total/Buckets/Avg/Peak its own pickable tile) |
| `cf9d933a` | full-bleed dashboard view (`body.rdb-fullbleed`) + **Present** fullscreen button |
| `4c100176` | Present-mode margins |
| `d4ad3eee` | **parallel session** — Generali sources; swept in small edits of mine to `reporting-guide.md` and `reporting.css` |
| `17968c12` | **parallel session's** conditional measures (`FilterJson` → CASE WHEN, migration `0120`), split back out of my mixed commit |
| `7c8c11d2` | filter bar shows the reports' own filters (chips per field, editors, replace-by-field, reset) |

## TL;DR

1. **Owner's asks all built and verified in the browser:** dashboard styled like the Results tab,
   full width + Present, and the global filter bar now shows the **reports' own filters** as chips
   (date presets / checkbox picker / text editors, replace-by-field, reset per chip, "+" for other
   fields). Screenshots in `var/screenshots/`: `style3_dashboard_view.png`, `fullbleed_dashboard_v2.png`,
   `filters_bar_active.png`, `filters_editor.png`, `filters_processes.png`.
2. **A shared-index collision happened and is resolved.** My first filter-bar commit (`93094deb`)
   had swept in the other session's staged files; with the owner's OK it was soft-reset and split
   into `17968c12` (theirs) and `7c8c11d2` (mine). `CHANGELOG.md` carries both entries and lives in
   `7c8c11d2`. Rule for this branch: **commit by pathspec and check `git show --stat HEAD` right
   after** — the other session stages into the same index.
3. **Working tree:** the other session's in-progress edits (`nx_lib/reporting/ai.py`,
   `nx_lib/views/reporting/ai.py`, `static/js/reporting_simple.js`, `templates/_reporting_simple.html`,
   `templates/js/_reporting_ai_js.html`, `tests/integration/test_reporting_ai_routes.py`) plus the
   owner's drawio files are **not mine and not committed**.
4. **Dashboard e2e is 20/20 green** on `7c8c11d2` (run after the split). The earlier two
   whole-report failures came from the chart-fill CSS of `cf9d933a`; that block is removed in
   `7c8c11d2`.

## What the filter-bar commit (`7c8c11d2`) does

- `effectiveFilters`: per-field layering, most specific wins (override > dashboard > report);
  within a layer every filter survives, exact duplicates collapse.
- `cardRunDef` copies `state.def.globalProcesses` onto every card's `scope.processes`; export and
  the change-detection snapshot use `cardRunDef` too.
- `facets()` / `facetLabel()` / `openFacetEditor()` / `applyFacet()` / `applyProcesses()` /
  `renderFilterBar()` — chips derived from the cards' report filters (+ Processes from the sources'
  registries), value editors, reset. Old field/op/value popover kept behind the round "+".
- I18N shim: `filterHint`, `processes`, `allProcesses`, `mixed`, `resetFilter`, `custom`, the
  relative-date token labels (same msgids as the Simple shim → already translated).
- CSS: `.rdb-gfilter--derived/--active/--mixed`, `.rdb-facet-*`, round `.rdb-add-filter`.

## Next steps (ordered)

1. Optional: re-add a whole-report chart-fill that does not overlay the toggle (the removed block is
   in `cf9d933a`'s diff; the bug was the absolute canvas inside a flex-grown `.rdb-report-chart`).
2. Then the unchanged path: merge GRuoss's PRs, fresh TEST seed for the three environmental
   `test_reporting_simple.py` failures, push, one PR.

## Gotchas & notes

- **Never `git add -A` / `git commit -a` on this branch; commit by pathspec and check
  `git show --stat HEAD` right after** — the other session stages into the same index.
- Port **8000 is someone else's STAGING server** since 14:54; use `bin\nx.ps1 -u --port:8010`.
- The Playwright MCP browser caches JS hard: `Network.setCacheDisabled` via CDP before checks.
- "Test dashboard" (report 41) on INT currently has zero cards — not touched by me.
- Untracked `sql/_migrations/NexoraDB/0118_seed_generali_measures.sql` belongs to the other session.

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-07-dashboard-style-fullbleed-filters.md`
