> **Superseded the same day** → [`2026-08-25-reporting-audit-wounds-fixed.md`](2026-08-25-reporting-audit-wounds-fixed.md) (layers 1+2 committed, all seven audit wounds fixed). Resume from that file.

# Handoff — Reporting audit → colours/right-axis popover → delete reports (WIP fixes uncommitted)

**Date:** 2026-08-25 · **Branch:** `v3.2.3.1` (owner's per-developer branch off `v3.2.3`) ·
**1 commit ahead of `e007ff25`, unpushed** · commit-only (owner pushes) · **dirty tree on purpose**
— see "Untracked / left for owner".

**Prior handoff:**
[`2026-08-19-logged-in-dark-mode-and-accent-audit.md`](2026-08-19-logged-in-dark-mode-and-accent-audit.md)
(v3.2.1 dark-mode/accent sweep; unrelated to this session).

## TL;DR

- Audited the Reporting page's core job on **STAGING** (owner: "not INT"): *imported + exported +
  backlog over time, with forecast*. Guided builder delivers it; **Ask-AI does not** (writes raw
  SQL, invents its own backlog = 681k vs 1,574, never charts). Full wound list in memory
  `project_reporting_state_audit_2026_08_25.md` and below.
- Shipped **`9ee87b84`** — Simple-tab *Farben & Achsen* popover: per-series colour, title+legend
  colour, per-series right-axis, backlog defaults to `y2`; persisted as `definition.style`.
- Built + browser-verified **delete reports** (card trash button + ⋯ → *Bericht löschen*) — **not
  yet committed** (my commit command hung on a stdin-blocked `cat`; nothing was staged).
- Started the owner's five feedback fixes on the popover/forecast — **edited but NOT tested, NOT
  committed**. Owner left with no internet; resume by testing those edits first.

## This session's commits

| Hash | What |
|---|---|
| `9ee87b84` | feat(reporting): colours & right axis for Simple-tab charts — `schema.py` (+tests), `_reporting_simple.html`, `_reporting_simple_js.html`, `reporting.css`, guide + tips + changelog, de/fr/it |

## Uncommitted work in the tree (two layers, same files)

**Layer 1 — delete reports (tested on STAGING, ready to commit):**
- `_reporting_simple_js.html`: `card()` wraps owned cards in `.rs-card-wrap` + `.rs-card-del`
  trash button; `deleteReport(id, name)` (window.confirm → `DELETE /api/reporting/reports/<id>`
  → `loadLibrary()`, drops to library if the open report was deleted); `rsDeleteReport` menu row
  wired; hidden-sync next to `applyTitleStyle()`.
- `_reporting_simple.html`: `#rsDeleteReport` row in `#rsMoreMenu`.
- `reporting.css`: `.rs-card-wrap/.rs-card-del/.rs-more-row--danger`.
- `_reporting_help.html` + `docs/howto/reporting-guide.md` + `CHANGELOG.md` entries; de/fr/it
  `.po/.mo` filled (msgids "Delete report", "Delete “{name}”? This cannot be undone.", help tip).
- Verified: Farbtest report deleted via card; "Importierte Dokumente dieses Jahr" deleted via ⋯
  menu; DB confirmed; shares/schedules `ON DELETE CASCADE` confirmed in `sql/NexoraDB/Tables`.

**Layer 2 — owner feedback fixes (edited, UNTESTED — server never restarted after these edits):**
1. Axis ownership unclear → `y`/`y2` get `title` = joined series labels, ticks tinted with the
   series colour when an axis carries one series (`leftSeries/rightSeries/axisTint/axisTitle` in
   `renderChart`).
2. Popover "Rechte Achse" ×3 confusing → checkbox replaced by a **Left | Right segmented switch**
   per row (`.rs-axis-seg/.rs-axis-btn`, `data-testid="rs-style-axis-left|right"`); click handler
   delegated on `#rsStyleRows` (`click`), colour handler now only `input[type=color]`.
3. Slow rebuild while dragging the colour picker → `rerenderStyled()` coalesced via rAF.
4. Forecast dashed lines bleeding into the bar chart → on `bar` the forecast is drawn as
   translucent bars (`hexAlpha(c,.35)`), band only on `line`, `fcActive` excludes `stacked`;
   pie/doughnut disable the forecast toggle with `I18N.forecastNeedsLineBar`.
5. Forecast toggle looked un-toggleable → `#rsForecastToggle.is-selected, #rsStyleToggle.is-selected`
   get an accent tint; turning forecast **off** now re-renders from `state.lastRun` (set in
   `runCurrent` after the anchor trim) without a server run (on still re-runs — the lookback-widened
   refit is server-side and is what makes "on" take 10–30 s on STAGING).
- **New msgids not yet extracted/translated:** "Left axis", "Left", "Right", "Forecast is only
  drawn on line and bar charts." → run the Babel cycle + fill de/fr/it (scratchpad scripts
  `fill_po*.py` show the pattern; wrapped msgids need the line-scanner variant), then
  `pybabel compile`.

## Audit findings still open (from the STAGING run; none fixed)

1. Buckets with **no `BacklogHistory` snapshot render as 0** (weekends, future days) — chart, avg,
   forecast, AI summary all treat them as real. Needs null-not-zero.
2. Backlog is a *level* but Gesamt/Ø/Spitze cards **sum it** across buckets.
3. Partial current bucket treated as complete (AI: "35% drop in August").
4. Future buckets inside a preset zero-filled and charted (AI: "Sep–Dez Aktivitätsstopp").
5. Ask-AI bypasses report definitions (no deleted-filters, own backlog def, first `run_sql` timed
   out, numbers drift between runs, "Als Diagramm anzeigen" yields text).
6. Wizard "Bisher:" summary lags one pick behind (cosmetic).
7. *Dieses Jahr* + *Woche* = 53 buckets > 50 chart cap → no chart though only 35 weeks have data.

## Next steps (ordered)

1. `& C:\dev\nexora\bin\nx.ps1 -u --env:staging --no-conflict` → Playwright login
   `http://localhost:8001/dev/login/ben.streich` → `/reporting` → wizard (German labels:
   *Dokumente importiert / Dokumente exportiert / Backlog → Im Zeitverlauf (Datum) → Dieses Jahr →
   Ergebnis anzeigen*). Test layer 2: popover L|R switch moves a series and the axis titles/tick
   colours follow; colour drag is smooth; forecast on bar = translucent bars; forecast off is
   instant; toggle shows tinted when on; pie disables it.
2. Babel cycle for the four new msgids, fill de/fr/it, compile; `pytest tests/unit/test_translations.py
   tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py`.
3. Commit — either one commit "feat(reporting): delete saved reports + popover/forecast polish" or
   split by `git add -p` (layer 1 vs 2). Prefix `SQL_SYNC_SKIP=1` if the INT hook stalls.
4. Then pick from the open audit list — #1 + #2 (null-not-zero, level-not-sum) are the biggest wins
   for the owner's north-star view; #7 is a one-liner (raise/skip the cap for pure time axes).

## Gotchas & notes

- Owner's dev-login user is **`ben.streich`**; staging locale is **de** → selectors need German
  labels. Stable testids: `rs-new-report`, `rs-measure-next`, `rs-scope-next`, `rs-breakdown-next`,
  `rs-forecast-toggle`, `rs-table-toggle`, `rs-style-toggle`, `rs-style-pop`, `rs-card-delete`,
  `rs-delete-report`, `rs-save`, `rs-save-name`.
- `nx` is not on PATH in the Claude shell — call `& C:\dev\nexora\bin\nx.ps1 …`; `-d --port:8001`
  stops a `--no-conflict` instance.
- `window.confirm` dialogs block Playwright — use `browser_handle_dialog` right after the click.
- Save on Simple is two-step: first *Speichern* reveals the name box, second commits.
- Saved-report column is `dbo.Reports.DefinitionJSON` (capital JSON).
- Someone else created two "DEMO" reports on STAGING mid-session — parallel activity is normal.
- Pre-commit `mixed-line-ending` rewrites `.po` files on the first attempt → `git add translations/`
  and commit again.
- Owner backfilled STAGING `BacklogHistory` from a legacy table on 2026-08-25 → daily snapshots
  since 2026-01-01; INT still has exactly one snapshot.

## Untracked / left for owner

- All of "Uncommitted work in the tree" above — deliberately left uncommitted (layer 2 untested).
- Screenshots in `var/screenshots/` (`staging-*`, `style-*`, `delete-*`) — gitignored evidence.
- Push of `9ee87b84` (+ whatever lands next) is the owner's call.

## How to verify

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_schema.py tests/unit/test_translations.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py -q
.\.venv\Scripts\ruff.exe check nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
```
`test_translations.py` **will fail** until the four new msgids are extracted + translated (step 2).

## Resuming in a fresh session

`/reset-session` picks this file (only handoff dated 2026-08-25). Start with "Next steps" 1–3.
