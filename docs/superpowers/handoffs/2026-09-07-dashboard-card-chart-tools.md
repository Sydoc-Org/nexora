# Handoff — dashboard cards carry the Results tab's chart tools, FLIP drag

**Date:** 2026-09-07 · **Branch:** `refactor/255-admin-nav-tenancy-labels` · nothing pushed ·
commit-only (remote). **Three other sessions commit on this same branch and share the index —
read Gotchas first.**

**Prior handoff:** [`2026-09-07-dashboard-style-fullbleed-filters.md`](2026-09-07-dashboard-style-fullbleed-filters.md)
(same date — pass this file's path to `/reset-session` explicitly).

## This session's commits

| Commit | What |
|---|---|
| `228e6951` | per-card chart toolbar (type / PNG / forecast + horizon / colours & axes) saved as `card.viz`; FLIP drag reorder; docs, tips, changelog, pybabel cycle |

Between the prior handoff and this commit the parallel sessions landed `7d8f4632`, `49a400c5`,
`f1ecd04a` (Eddard report context, report-layouts spec, Advanced back in the rail). `f1ecd04a`
swept my first CSS block (`.rdb-card-tools`) into their commit — harmless, it is in HEAD.

## TL;DR

1. **Owner's ask built and verified against INT:** a dashboard card now has everything the
   Results tab's chart has — chart type, forecast, which series sits on which axis, colours, PNG —
   as an edit-mode toolbar on every chart-bearing card. Tweaks live on the card (`card.viz`),
   never on the saved report; view/Present mode shows no toolbar.
2. **Drag is smoother:** `reorderGridDom` plays a FLIP transform so neighbours slide into place
   (`.rdb-grid--dragging .rdb-card { transition: transform .22s }`). Still HTML5 drag.
3. **Dashboard e2e is 21/21 green** (`tests/e2e/test_reporting_dashboard.py`, new test
   `test_card_chart_tools_tweak_type_forecast_colours_and_persist_on_card`). Translation tests
   11/11.
4. Screenshots in `var/screenshots/`: `cardtools_edit.png`, `cardtools_style.png`,
   `cardtools_forecast.png`, `cardtools_view.png` (sent to the owner).

## What shipped (`228e6951`)

- `static/js/reporting_dashboard.js` — `cardRunDef` layers `card.viz` (`chartType`,
  `forecast` block or `false`, `style`) over the report definition; `cardToolsHtml`,
  `mountCardChart` (re-mount from the card's last result, no re-run), `syncCardTools`,
  `renderCardStyleRows`, delegated `handleCardToolClick/Input/Change` on `#rdbGrid`; toolbar
  skipped for the `__pick` overlay card; toolbar clicks never start a reorder drag; FLIP in
  `reorderGridDom`.
- `static/js/reporting_simple.js` — `window.ReportingSimple` also exports `forecastEligible`,
  `seriesKey`, `rightAxisKeys`, `defaultSeriesColor`.
- `static/css/reporting.css` — `.rdb-card .rdb-style-pop` scrolls (max-height 260px).
- `templates/js/_reporting_dashboard_js.html` — I18N keys reuse the Simple pane's msgids
  (Bar chart, Forecast, Colours & axes, Left/Right …) so nothing new needed translating.
- `templates/_reporting_help.html`, `docs/howto/reporting-guide.md` (new bullet "The Results
  tab's chart tools, per card"), `docs/howto/reporting.md` (`viz` shape + FLIP note),
  `CHANGELOG.md`.
- `messages.pot` + de/fr/it `.po`/`.mo` — full pybabel cycle; also translated the peer's
  "Need exact control the wizard can't give?" tip from `f1ecd04a`, which had no pot entry.

## Addendum (same session, later)

| Commit | What |
|---|---|
| `d3e1f060` | Present margins (rule moved into `reporting.css`, out-ranks the full-bleed padding); forecast toggle is `aria-disabled` + toast instead of a dead `disabled` button; whole-report card = KPI strip + full-width chart, `height: auto` |
| `e0bdda2c` | grid row spans: `grid-auto-rows: minmax(--rdb-row, auto)`, `grid-auto-flow: row dense`, `.rdb-card { grid-row: span --rdb-cardrows }` — short cards stack beside a tall one |

Parked, unstaged in the shared tree because a peer has its own staged hunk in the same file:
a 4-line CHANGELOG bullet for `e0bdda2c` (patch also in this session's scratchpad). The two
guide bullets for `d3e1f060` were swept into the peer's staged `reporting-guide.md` — they
land with the peer's commit. The shared tree does **not import** right now
(`nx_lib.db` lacks `engine_generali_ro` while a peer is mid-change); `e0bdda2c` was verified
from a `git archive HEAD` snapshot + the CSS on port 8011.

## Next steps (ordered)

1. (done in `d3e1f060`/`e0bdda2c`: Present margins, forecast affordance, report-card layout, stacking.) Optional polish: when a forecast legend appears, the floating toolbar overlaps its right
   end on narrow chart cards (`cardtools_edit.png`). A `margin-top` on `.rdb-report-chart` when
   `.rdb-card-tools` is present would fix it, but the chart-piece card's `height: calc(100% - 4px)`
   must then subtract it.
2. Pre-existing, not touched: adding a report from a **different source** to a dashboard whose
   filter bar already carries another source's field (e.g. *Scan date*) makes the pick overlay
   POST that foreign filter → `/api/reporting/run` 400 → "Could not load this card". Filters
   should be dropped per card when the field is not in the card's source catalog
   (`effectiveFilters` / `cardRunDef`).
3. Then the unchanged path from the prior handoff: merge GRuoss's PRs, fresh TEST seed, push,
   one PR.

## Gotchas & notes

- **Shared index, three peers (Angela Merkel / Nelson Mandela / Margaret Thatcher sessions).**
  Peers `git add` whole files, and pre-commit's stash makes your edits vanish for ~60 s. Rule
  that worked: `git add <paths> && SQL_SYNC_SKIP=1 git commit <paths>` in ONE invocation, then
  `git show --stat HEAD`. The sql-sync-check fails on drift from a peer's untracked migration
  (`0121_reporting_sql_generali_target.sql`) — hence `SQL_SYNC_SKIP=1`.
- The Playwright **MCP** browser wedged on its profile lock (`Browser is already in use …
  mcp-chrome-3a4f3d4`) and did not recover even after killing chrome + deleting `lockfile`.
  Verification was done with **Python Playwright from `.venv`** instead (scripts were in the
  session scratchpad, not the repo) — that path is reliable.
- Port 8000 is a STAGING server; use `bin\nx.ps1 -u --port:8010`. Server was stopped at the end.
- INT test artefacts (report 52 "e2e forecast weekly imports", dashboard 53 "e2e card tools")
  were deleted again via the API.
- `stacked` chart type is only offered for pivoted multi-breakdown series (`multiSeries`), not
  for two measures on one breakdown — same rule as the Results tab; the e2e test asserts it.

## Untracked / left for owner

- Working tree still holds the peers' staged `nx_lib/reporting/ai.py` and
  `templates/js/_reporting_ai_js.html` — not mine, not committed.
- Owner's drawio files and `docs/architecture/` remain untracked.

## How to verify

```powershell
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
python -m pytest tests/e2e/test_reporting_dashboard.py -q --no-cov        # 21 passed
python -m pytest tests/unit/test_translations.py -q --no-cov              # 11 passed
```

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-07-dashboard-card-chart-tools.md`
