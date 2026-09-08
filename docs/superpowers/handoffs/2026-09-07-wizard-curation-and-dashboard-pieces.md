> **Newer handoff (same date):** [`2026-09-07-report-layouts-definitions-plan.md`](2026-09-07-report-layouts-definitions-plan.md) — report-layouts spec + plan, execute in worktree `plan-report-layouts`.

# Handoff — the wizard's breakdown step is curated, and dashboard cards became pieces of saved reports

**Date:** 2026-09-07 · **Branch:** `refactor/255-admin-nav-tenancy-labels` (main checkout
`C:\dev\nexora`, no worktrees) · **97 commits ahead of `origin/main`, nothing pushed** ·
commit-only — the owner pushes and opens the PR.

**Prior handoff:** [`2026-09-07-tenant-solo-and-reporting-kpi-honesty.md`](2026-09-07-tenant-solo-and-reporting-kpi-honesty.md)
(same date — pass this file's path to `/reset-session` explicitly; that one and
`2026-09-07-one-branch-238-254-merged.md` carry forward-pointer banners).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `430695a6` | wizard: breakdown step curated (Advanced fold, plain date chips, field_quality catalog via migration `0116`), result table shown by default |
| `d6863edb` | dashboards: a card is `{reportId, type, kpiIndex}` — pick pieces off the fully rendered report; old card types deleted |

## TL;DR

1. **Owner's pre-PR wizard list is done.** Field extraction quality: Stream and Workitem gone from
   the catalog, Customer → **Client**, Process reads `elektromaterial.02_Invoice`, the raw/diagnostic
   dimensions sit behind **Show advanced fields (n)**. Docprocessing keeps Process, Page Count,
   Document Type, Document Source, Creditor Name in front; everything else folds. Date chips read
   "Import date" / "Export date" (no "Over time (…)" wrapper). The Simple result table is shown by
   default; the toggle now only hides it.
2. **Dashboards were rebuilt around the owner's model** ("take the original thing, not a recreated
   one"): Add card → pick a report → it renders whole in an overlay (same `renderReportCard` as the
   Whole-report card) → hover-`Add to dashboard` on each KPI tile, the chart, the table, plus `Add
   whole report`. Cards reference the report; its definition is fetched live on open and never
   persisted. The five dashboard-authored renderers, pivot, type pills, sliders, blank-card picker,
   KPI trend re-run and their CSS are deleted (~500 JS lines net).
3. **e2e is green where it can be.** `test_reporting_dashboard.py`: 18/18 (14 old-type tests
   removed, 2 added). Three `test_reporting_simple.py` drill/two-breakdown tests fail **only** because
   the shared `NEXORA_TEST` currently holds an older seed (pre-`0088` permission code
   `reporting.admin.sources`; the route wants `reporting.sources.manage` → 403 in test setup). A
   `test_db_reset.py` fixes it, but another run held the applock for the full 20 min this session.
4. **No backend change in either commit.** One data-only migration (`0116`, applied to INT).

## What shipped

### `430695a6` — wizard curation + table by default

| File | Change |
|---|---|
| `sql/_migrations/NexoraDB/0116_field_quality_wizard_curation.sql` | `field_quality` ColumnsJSON: drop Stream/Workitem, Customer → "Client", Process `labelWith: Customer`, `"advanced": true` on FieldLabel/Field/FieldType/ValueOrigin/HistorySource/StatusBefore/AfterValidation |
| `nx_lib/reporting/table_query.py` | `table_source_catalog` passes `advanced` through |
| `static/js/reporting_simple_wizard.js` | `DOCPROC_DIM_MAIN` (five keys), `DOCPROC_DIM_ORDER` reordered; breakdown step splits main vs advanced (`isAdv`), one `Show advanced fields (n)` chip (`data-testid="rs-breakdown-advanced"`) → `w.advOpen`; a selected advanced field keeps the fold open; date chips = `f.label` |
| `static/js/reporting_simple.js` | `runCurrent`: table always visible, toggle text `hideTable`, toggle shown only when a chart/stat card exists |
| `templates/js/_reporting_simple_js.html` | `overTime` removed; `groupAdvanced`, `showAdvanced` added |
| `templates/_reporting_help.html`, `docs/howto/reporting-guide.md`, `docs/howto/reporting.md`, `CHANGELOG.md` | advanced fold, plain date chips, table-by-default, Client wording |
| `tests/unit/test_reporting_table_query.py` | `advanced` passthrough test |
| `tests/e2e/test_reporting_simple.py` | docprocessing chip test asserts 4 main + fold → 13; table-toggle clicks removed (table already visible) |
| `messages.pot`, `translations/*` | 2 new + 2 re-worded msgids, all locales non-fuzzy |

### `d6863edb` — dashboard pieces

| File | Change |
|---|---|
| `static/js/reporting_dashboard.js` | card model `{id, reportId, type: report\|chart\|table\|kpi, kpiIndex, span, rows, title, filterOverrides}`; `hydrateCards` (GET each distinct report on `open()`), `persistedDef` (strip `definition` on save); `runCard` → `renderReportCard` for every type; `applyPiece` hides the rest, `kpiTiles` indexes `.rs-kpi-total-card, .rs-kpi-stats-card`; add flow = `openAddMask` (report list) → `openPickReport` (renders via `renderReportCard` into `rdb-pick-report-body`, chart keyed `__pick`, kept alive across grid re-renders) → `pickPiece`; `isLegacyCard` (no `reportId`) → notice body, never runs; `DEFAULT_SPAN {kpi 3, chart 8, table 6, report 12}`, `DEFAULT_ROWS {kpi 2, chart 3, table 2, report 4}` |
| `templates/js/_reporting_dashboard_js.html` | −16 strings (pills, mask steps/sizes, trend, donut) / +7 (`reportGone`, `legacyCard`, `pickHint`, `pickAdd`, `pickAdded`, `pickWhole`, new `addTileHint`) |
| `static/css/reporting.css` | +`.rdb-modal--pick`, `.rdb-pick-host`, `.rdb-pick-btn`, `.rdb-report--kpi/--chart/--table`; −40 dead rules (mask pills/sliders, donut, k/v table, kpi trend, configure) |
| `tests/e2e/test_reporting_dashboard.py` | `_add_card_via_mask(page, type, name)` drives the new overlay; `_stub_dashboard_report(..., reports=)` + `_as_reference_cards` convert old-shape fixtures to reference cards and answer `reports/<id>` per report; `rdb-kpi-value` → `rdb-rs-kpi-total .reporting-ledger-kpi-value`; new `test_add_card_overlay_takes_pieces_of_the_opened_report`, `test_legacy_card_shows_notice_and_never_runs` |
| `docs/howto/reporting.md` §Dashboards, `docs/howto/reporting-guide.md` §Dashboards, `templates/_reporting_help.html`, `CHANGELOG.md` | rewritten for the reference model |
| `messages.pot`, `translations/*` | 9 new msgids translated de/fr/it |

## Next steps (ordered)

1. **Unchanged from the prior handoff:** merge GRuoss's #262, #276 (clean) and #261
   (`templates/_header.html` conflict, positional) into `main`, merge `main` into this branch, push,
   one PR linking #238 #254 #255 #256 #257.
2. **Before trusting CI's e2e:** the three `test_reporting_simple.py` failures need a fresh
   `NEXORA_TEST` seed — run `scripts/test_db_reset.py` when nobody holds the applock, then
   `-k "test_wizard_two_breakdowns or test_drill_row_opens_panel"`.
3. **Owner eyeball** (screenshots, gitignored): `var/screenshots/wiz_fq_breakdown_folded.png`,
   `wiz_fq_breakdown_unfolded.png`, `wiz_docproc_breakdown_folded.png`, `wiz_fq_result_table_default.png`,
   `dash_pick_overlay.png`, `dash_cards_pieces_v2.png`, `dash_reopened.png`.
4. Dashboard follow-ups the owner may want (not built, not asked): a card title editor (titles default
   to `Report · tile caption`), whole-workbook export, and a "Page Count" chip whose catalog type
   is `string` on INT — it shows as a category today, which is what was asked.
5. Carried over untouched: `compassUser` → CMPS, #256 entity/field editors, tenant delete leaving
   `tenant.<code>.*` rows, INT Privera logo 404 / ISS brand, What's New card for #238.

## Gotchas & notes

- **`open()` is async now** (hydrates before rendering). Callers in `reporting_simple.js` /
  `reporting_simple_library.js` don't await it — fine, but a second `open()` mid-hydrate is guarded
  by `state.def !== report.definition`.
- **`effectiveFilters`, `cardSourceIds`, `openCardDrill`, `exportCard` still read `card.definition`** —
  that is the hydrated live definition, so nothing else had to change. Export skips cards whose report
  is gone (`!isLegacyCard(c) && c.definition`).
- **KPI tile identity is positional** (`kpiIndex` into the band's DOM order: one total card per
  measure, then the Buckets/Avg/Peak stats card). Adding a measure to the report shifts indexes —
  accepted for v1 (`ponytail`).
- **The overlay's chart id is `__pick`**; `renderGrid`'s `destroyChartsExcept` keeps it while
  `addMask.open`. Forgetting that made the overlay chart vanish on the first pick.
- **e2e fixture converter**: a fixture card with a `reportId` key (even `None`) is left alone — that's
  how the legacy test keeps its shape. Cards without the key are converted to `src-<id>` references.
- **Two runs per pick-then-card**: the overlay renders the report (1 run + totals clone) and the card
  runs again. `test_report_card_zero_dim_totals_without_second_run` now asserts 2 posts, both
  `columns: []` — the "no totals clone for zero dims" property still holds.
- **Corner-drag e2e** needed `handle.scroll_into_view_if_needed()` — a 2-row KPI card pushes the
  handle below the 720-px fold after the first resize.
- **`test_db_reset.py` lost the applock race** (waited 20 min, gave up, pytest then ran on the
  stale seed). Don't kill the other run; retry later.
- **`pybabel extract` has no `-q`** — first cycle this session silently skipped extraction.
- **KPI cards at 1 row clip the tile**, chart at 2 rows loses the plot under the legend — hence the
  new `DEFAULT_ROWS`.
- `docs/superpowers/plans/2026-08-25-dashboard-whole-report-card.md` and
  `2026-08-06-reporting-ai-owner-feedback.md` still reference `rdb-card-configure` / `rdb-report-picker`
  — historical plans, left as is.

## Untracked / left for owner

- Same as before: `docs/nexora-architecture.drawio` modified, `docs/nx-architecture.drawio`,
  `docs/architecture/`, two `.$*.bkp` files — the owner's diagram work, **not committed**.
  `docs/architecture/` may need a `/XD` in `deploy.yml`.
- Two throwaway "Untitled dashboard" reports created on INT during verification were deleted again
  (ids 38, 39).

## How to verify

```powershell
# unit (no DB)
$env:NEXORA_TEST_LOCK_SKIP = "1"
.venv\Scripts\python -m pytest tests/unit/test_reporting_table_query.py tests/unit/test_translations.py `
  tests/unit/test_reporting_i18n_lint.py tests/unit/test_template_url_prefix.py -q -p no:cacheprovider --no-cov
Remove-Item Env:NEXORA_TEST_LOCK_SKIP

# e2e (needs a FRESH NEXORA_TEST seed -- see Gotchas)
$env:ENVIRONMENT = "TEST"; .venv\Scripts\python scripts\test_db_reset.py
$env:NEXORA_E2E_PORT = "8123"
.venv\Scripts\python -m pytest tests/e2e/test_reporting_dashboard.py -q -p no:cacheprovider --no-cov   # 18 passed
.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q -p no:cacheprovider --no-cov `
  -k "docprocessing_offers_process_breakdown or two_date or test_wizard_two_breakdowns or test_drill_row_opens_panel"

# migrations (0116 applied to INT; next free number is 0117)
.venv\Scripts\python scripts\db-migrate.py --env INT --db NexoraDB --dry-run

# live (restart first -- Jinja templates and .mo files are cached for the process lifetime)
bin\nx.ps1 -r --port:8000
#   /reporting?tab=simple -> New report -> "Extraction correct %" -> Continue:
#     scope lists compass.01_Invoice_SAP … ; breakdown shows Import date / Export date,
#     Field / Client / Process, "Show advanced fields (7)"; result opens with the table visible.
#   Dashboards -> New dashboard -> Add a card -> pick a report -> hover a KPI / the chart -> Add.
```

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-09-07-wizard-curation-and-dashboard-pieces.md`
— pass the path explicitly: three handoffs share today's date.

Nothing is red in the code. The branch still waits on GRuoss's three PRs, a fresh TEST seed for the
three environmental e2e failures, then the owner's push and one PR.
