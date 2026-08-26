> **Superseded same-day:** see
> [`2026-08-25-reporting-audit-followups.md`](2026-08-25-reporting-audit-followups.md)
> for the next session, which closed this handoff's three "Next steps" items.

# Handoff — Reporting audit wounds fixed (delete reports, popover polish, stop-at-today, backlog-as-level, AI grounding)

**Date:** 2026-08-25 · **Branch:** `v3.2.3.1` (owner's per-developer branch off `v3.2.3`) ·
**5 commits ahead of `e007ff25`, unpushed** · commit-only (owner pushes) · **clean tree**.

**Prior handoff:**
[`2026-08-25-reporting-audit-colours-axes-delete.md`](2026-08-25-reporting-audit-colours-axes-delete.md)
(same day, earlier session — audit + colours/axes popover; its "Next steps" 1–4 are all done here).

## TL;DR

- Tested and committed the previous session's two uncommitted layers: **delete saved reports**
  (`3bbab717`) and the **popover/forecast polish** (`33b42f4c`, one extra bug found: forecast bars
  ignored the series' palette colour).
- Fixed **all seven open audit wounds** in one commit (`48a08364`) and verified each on STAGING via
  Playwright: buckets stop at today, partial bucket faded/dashed + note, backlog is a level
  (`NULL` gaps, Total = newest snapshot, migration `0070`), forecast fits finished buckets only and
  carries levels forward, AI agent builds a `build_definition` for imported/exported/backlog
  instead of raw SQL, "Show it as a chart" opens the builder, 400-bucket date-axis cap, wizard rail
  lag, `00:00:00` peak labels.
- A **peer Claude session (`nexora-c0`, branch `v3.2.3.2`)** is rewriting the AI caption body as a
  server-side fact sheet (`nx_lib/reporting/caption_facts.py`) on top of `48a08364` — it was told the
  caption files are free now. Don't touch `ai.py caption()` / `api_ai_caption` / `fireCaption` without
  checking `ListAgents` first.

## This session's commits

| Hash | What |
|---|---|
| `3bbab717` | feat(reporting): delete saved reports from the Simple tab — card trash button + ⋯ → *Bericht löschen*; carries the Babel cycle (de/fr/it) for this and the next commit |
| `33b42f4c` | fix(reporting): axis ownership, L\|R switch, forecast bars on bar charts — axis titles/tinted ticks, segmented Left\|Right, rAF-coalesced colour drags, translucent forecast bars (now in the series' own colour), toggle tint, instant forecast-off |
| `48a08364` | fix(reporting): stop at today, treat backlog as a level, ground the AI — the seven audit wounds, see below |

## What shipped in `48a08364` (by wound)

| # | Wound | Fix | Where |
|---|---|---|---|
| 1 | No-snapshot backlog buckets render 0 | `counter_exprs` emits `NULL AS [backlog]` on non-backlog legs → `SUM` is `NULL` for unmeasured buckets; JS null-fills latest-mode metrics, KPI band/sparkline/latest-total skip nulls, single-dim datasets keep `null` (+`spanGaps`), PNG renderer maps `None`→NaN | `query.py`, `_reporting_simple_js.html`, `chart_render.py` |
| 2 | Backlog level gets SUMmed | migration `0070` sets `ReportingMetrics.TotalMode='latest'` for `backlog` (0067 forgot it); front end's existing `applyLatestTotal` then does the rest | `sql/_migrations/NexoraDB/0070_*.sql` |
| 3 | Partial current bucket treated as complete | bucket containing today: bar faded (`fadeColor`), line segment dashed + rectRot point, note *"The current period is still running…"*; `compute_forecast` fits on finished buckets (`partial_last`) and projects from the next one; caption gets a note | `_reporting_simple_js.html`, `forecast.py`, `ai.py` |
| 4 | Future buckets zero-filled | `zeroFillDateBuckets` clamps the range end to `localTodayIso()` | `_reporting_simple_js.html` |
| 5 | Ask-AI bypasses definitions | `_AGENT_SYSTEM`'s stale "builder CANNOT put imported and exported side by side → write SQL" rule replaced with an anchored-metrics rule; `serialize_sources_catalog` marks metrics `anchor=<date>`; `_accessible_curated_sources` passes `anchor`; "Show it as a chart" follow-up opens the builder when the answer has a definition; caption `notes` param + system rule | `ai.py`, `ai_schema.py`, `views/reporting.py`, `_reporting_ai_js.html` |
| 6 | Wizard "Bisher:" lags one pick | `renderWizardRail()` on breakdown add/remove, `#rsGrain` change, time-preset pick | `_reporting_simple_js.html` |
| 7 | 53 weeks > 50-point cap → no chart | `xCap = isDate ? 400 : 50` (both single-dim and pivot paths); `MAX_X_DATE = 400` in `chart_render.py` | both |

Plus: `_forecast_for` passes `carry_forward=_level_metric_indexes(rd)` (latest-mode metrics carry
their last value across gaps); `appendChartNote()` so forecast/partial/gap notes stack instead of
clobbering; peak label strips `00:00:00`; 6 new unit tests (forecast ×2, ai, ai_schema, chart ×2);
guide section *"Today, unfinished periods and gaps"*, help tip, CHANGELOG *Fixed* block, de/fr/it.

## Verified on STAGING (Playwright, `ben.streich`, locale de)

- *Dieses Jahr* / Monat: 8 buckets Jan–Aug (was 12 with Sep–Dez zeros), Gruppen 8, Aug faded/dashed,
  note shown, caption request carried `notes` (partial bucket + "Backlog is a level").
- Forecast on bar: starts 2026-09, Aug kept as actual; importiert projection 67.7k (fit without Aug).
- *Dieses Jahr* / Woche: 35 weeks charted (was "Zu viele Datenpunkte").
- Backlog / Tag / *Dieser Monat*: 25 buckets, 8 weekend gaps (`null`, `spanGaps`), Gesamt = 794
  "Letzte Gruppe 2026-08-25", Gruppen 17 (non-null only), both notes in German.
- AI agent (`/api/reporting/ai/agent`, "Wie viele Dokumente wurden dieses Jahr pro Monat importiert und
  exportiert, und wie hoch war der Backlog?"): 2 turns, 21 s, `build_definition` ok with
  `docs_imported/docs_exported/backlog` on `activity_date`/month/`this_year`, **no SQL**.
- Wizard rail updates on breakdown, grain and time picks.

## Next steps (ordered)

1. Owner: review + push `v3.2.3.1`; PR → `v3.2.3`/`main` when the cycle is ready. `0070` is applied on
   INT (pre-commit) and STAGING (by hand this session); PROD gets it on deploy.
2. Coordinate with `nexora-c0`'s caption fact-sheet work (`v3.2.3.2`) — it will replace the raw-rows
   caption body; the `notes` param and `captionNotes()` client facts should survive (or become
   server-computed facts).
3. Open follow-ups from the audit (not started, none blocking):
   - AI for explain-data users still ends with "Definition gebaut, Zahlen nicht ausgeführt" — a
     `run_definition` tool (server runs the validated definition and returns rows) would let it quote
     numbers from the business definition instead of SQL.
   - Multi-dim pivot (`cell[x][s] || 0`, `_reporting_simple_js.html` ~L1417/1460) still turns a
     backlog `NULL` into 0 when broken down by process.
   - Advanced tab has none of the partial/gap/stop-at-today treatment.
   - Delta chips compare a partial current period against a full prior one (pre-existing).
4. `/nx-ui-verify`-style dark-mode pass over the new faded/dashed partial styling (only light checked).

## Gotchas & notes

- **Parallel sessions:** `ListAgents` at start; `nexora-c0` is live on `v3.2.3.2` (IIS hosting swap
  landed as `83316e1d` there; caption fact sheet in progress). Message it before touching
  `ai.py`/`views/reporting.py` caption code.
- STAGING server: `& C:\dev\nexora\bin\nx.ps1 -u --env:staging --no-conflict` → port 8001;
  `-d --port:8001` stops it. Restart after template edits (Jinja cache). Login
  `http://localhost:8001/dev/login/ben.streich`. Wizard labels are German; the German result view
  testids are in the prior handoff.
- `pybabel update` fuzzy-matched "Left"→"Violett", "Right"→"Hell", "Left axis"→"Rechte Achse" — the
  fill script overwrote them and dropped the `#, fuzzy` flags; `grep -c fuzzy` on the `.po`s is 0.
  Always diff-sweep `.po` after an update.
- `git commit` heredocs with `SQL_SYNC_SKIP=1` weren't needed this time — the INT hook passed; keep
  the prefix handy if `SchemaMigrations` CRLF drift returns.
- `compute_forecast` uses `datetime.date.today()` for `partial_last`; tests monkeypatch
  `datetime.date` inside the module (`test_compute_forecast_fits_on_finished_buckets_when_last_contains_today`).
- Zero-fill "today" is the **browser's** local date (`localTodayIso()`), the forecast's is the
  server's — same machine on INT/STAGING, one-day skew possible around midnight in PROD.

## Untracked / left for owner

- Nothing uncommitted. Screenshots in `var/screenshots/` (`l2-*`, `audit-*`) are gitignored evidence.
- Push of the five commits is the owner's call.

## How to verify

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_query.py tests/unit/test_reporting_forecast.py tests/unit/test_reporting_chart_render.py tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_schema.py tests/unit/test_reporting_schema.py tests/unit/test_translations.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py -q
.\.venv\Scripts\ruff.exe check nx_lib/reporting/ nx_lib/views/reporting.py tests/unit/
```
All green at `48a08364` (135 passed for the reporting subset).

## Resuming in a fresh session

Two handoffs share this date — run `/reset-session docs/superpowers/handoffs/2026-08-25-reporting-audit-wounds-fixed.md`
explicitly (the older one carries a forward-pointer banner). Start with "Next steps" 2–3.
