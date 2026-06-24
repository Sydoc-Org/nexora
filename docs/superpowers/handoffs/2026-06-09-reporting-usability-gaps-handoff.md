> ➡️ **NEWER HANDOFF (read this instead for current state):**
> `docs/superpowers/handoffs/2026-06-09-reporting-date-dimension-session-handoff.md`
> — the process picker, field-scoping, and the date dimension (Tasks 1–7) all landed after this doc.

# Handoff — Reporting page: usability gaps & "nothing really works" triage

- **Date:** 2026-06-09
- **Branch:** `feature/2.5.63`. 30 commits ahead of `origin/feature/2.5.63` (unpushed). Merge from
  `feat/workitem-table-highlight` is **resolved** (no merge in progress).
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-09-reporting-semantic-slice1-complete-handoff.md`
- **Status of the feature:** the reporting backend is broad and well-tested (806 backend tests
  green, Phases 1–4 + semantic Slice 1 all landed). But from the **user's seat the page is not
  usable yet** — too much surface area, key everyday capabilities missing, AI unreliable. This
  handoff captures *exactly what is broken/missing* with root causes already traced, so next
  session goes straight to fixing instead of re-diagnosing.

## User's verdict (verbatim intent)

> "There is a good ground basis now with the report but nothing is really working right now.
> Everything is way too complicated. The AI doesn't really work, no processes available to choose
> from, Import / Export Date is completely left out, Counting Workitem IDs in Document Processing
> is nowhere to be found (work on that later). Write the handoff."

Five issues. Four to fix; one (#5) explicitly deferred.

---

## Issue 1 — "No processes available to choose from" — UI GAP (root cause confirmed)

**It is NOT a permissions problem.** Verified live on INT: the test user `ben.streich` (uid 1019)
holds all 5 `reporting.scope.process.*` grants (compass.01_Invoice_SAP, elektromaterial.02_Invoice,
privera.02_InitialScan, privera.02_Posteingang, privera.03_Invoice_New), and the perms exist and
were correctly mirrored from `dashboard.filter.process.*` (5 ↔ 5). `_allowed_processes()`
(`nx_lib/views/reporting.py:570`) returns those 5 correctly.

**Root cause:** the reporting builder UI has **no process-picker control at all.**
- `templates/reporting.html` mentions "process" only inside an AI placeholder string — there is no
  process dropdown / multiselect / scope widget anywhere.
- In `templates/js/_reporting_js.html`, `state.processes` is only ever: initialised to `[]`
  (line 5), sent as `scope.processes` in the run payload (line 43), or hydrated from a saved report
  (line 366) / source default (line 664). Nothing in the UI ever lets the user *set* it.
- Server side, `_effective_scope()` (reporting.py:642) treats empty `scope.processes` as "all
  allowed processes," so docprocessing reports silently UNION across all 5 — the user can't narrow
  to one process, and can't even *see* which processes are in scope.
- The only current escape hatch is to hand-add a `processname` filter in the Filters well
  (`processname` is a synthetic field the query builder special-cases — see
  `query.py:_scope_by_processname`). Not discoverable.

**Compare:** the dashboard (`nx_lib/views/dashboard.py`) has a proper process filter. Reporting
needs the same affordance.

**Fix (next session):** add a process scope picker to the builder (a "Processes" well or a
multiselect in the toolbar) populated from a new lightweight endpoint that returns
`_allowed_processes()` (label + value). Wire it to `state.processes`. Default = all allowed
(current behaviour) with a clear "All processes" chip. Only applies to the `docprocessing` source
(table sources carry their own `processes`). i18n the new strings.

---

## Issue 2 — "Import / Export Date is completely left out" — REAL GAP (root cause confirmed)

**Root cause:** the docprocessing field catalog is built **only** from `SearchConfig.col_*`
columns (`nx_lib/reporting/catalog.py: fetch_docprocessing_catalog`). The date columns live in a
*different* table, `Statconfig` (`ExportColumn`, `ImportColumn`), and although `_load_process_configs`
(reporting.py:585) loads `export_col`/`import_col` into `process_configs`, the query builder
`build_table_query` (`nx_lib/reporting/query.py:108`) **never references them** — they're dead
inputs. So in a report you cannot select, filter-by, or group-by import/export date.

This is the single biggest functional hole: **no time dimension at all.** You can't do "volume by
day/week/month," "documents this month," or any date-range filter — the bread-and-butter of a BI
page. By contrast the dashboard uses these exact columns everywhere (throughput-over-time,
processing-time/duration, date-range WHERE — see dashboard.py lines 286–306, 489–504, 575–590,
963–984, 1060–1143).

**Fix (next session), design-first:** expose the per-process export/import date as first-class
catalog fields so they flow through the existing column/filter/sort/metric machinery. Sketch:
- In `fetch_docprocessing_catalog`, synthesise two virtual fields (e.g. `export_date`,
  `import_date`) with `type:"date"`, `filterable:true`, `sortable:true`, available for every
  process that has the corresponding Statconfig column.
- In `build_table_query`, when a projected/filtered/sorted field is `export_date`/`import_date`,
  resolve it to that process's `cfg["export_col"]`/`cfg["import_col"]` (names come from the
  injected config, never the client — keep the SQL-injection boundary intact). Beware per-process
  column-name differences and the `CONVERT(...)` cases the dashboard handles (dashboard.py:300).
- Add date bucket support (day/week/month) — either as a sort/group transform or, cleaner, as
  conformed time dimensions (this is essentially **semantic-layer Slice 2** territory; consider
  folding it in). A `documents per month` view needs a `DATE`-truncation group-by.
- This unlocks date-range filtering and time-series charts, and is a prerequisite for most
  "real" reports.

---

## Issue 3 — "The AI doesn't really work" — NEEDS REPRODUCTION (not yet root-caused)

AI is enabled on INT via Azure (`AI_PROVIDER=azure_openai`, `AI_MODEL`/deployment `gpt-4o-mini`,
keys in gitignored `env/INT.env` — see memory `project_reporting_ai_enabled_int`). Three surfaces,
all in `nx_lib/views/reporting.py` + `nx_lib/reporting/ai.py`:
- `POST /api/reporting/ai/ask` (Surface B — NL→T-SQL, gated `reporting.ai.sql`)
- `POST /api/reporting/ai/build` (Surface A — NL→report definition, gated `reporting.ai.use`)
- `POST /api/reporting/ai/agent` (Surface C — agentic loop)

**Not yet diagnosed** (didn't reproduce this session — user reported it). Next session, reproduce
in the browser and pull the truth from two places **before** changing code:
1. `dbo.ReportingAiAudit` — every call audits `Surface`, `Status` (`ok`/`blocked`/`error`),
   `Error`, and the model output. `SELECT TOP 20 * FROM dbo.ReportingAiAudit ORDER BY CreatedAt DESC`.
2. `var/logs/system/app.log` — provider errors, schema-truncation info lines, throttle (`429`).

**Leading hypotheses to check, cheapest first:**
- **Thin grounding:** the catalog the model sees (`_ai_catalog_text` / `_ai_schema_text`) is
  weakened by the same gaps above — docprocessing fields are all `type:"string"`,
  `aggregable:false` (because `FieldMetadata` doesn't exist on INT — that's the benign
  "FieldMetadata unavailable" warning), and there's **no date field and no process list** in the
  grounding. A small model can't draft good reports from a vague schema. Fixing #1 and #2
  *directly* improves AI grounding.
- **Small model:** `gpt-4o-mini` is weak for self-validating definition drafting; Surface A does
  one retry then gives up. Consider a stronger deployment or better prompt/repair.
- **Daily cap:** `AI_DAILY_LIMIT` returns 429 (audited `Status='blocked'`) before any provider
  call — confirm it isn't tripping.
- **explain_data path:** RO SQL logins must be provisioned for `run_sql`/`compute_stats` to work
  (memory `project_reporting_phase3` says provisioned on INT — re-verify).

Decide direction *after* reading the audit rows. Don't guess-patch the prompt.

---

## Issue 4 — "Everything is way too complicated" — UX / information architecture

The builder currently surfaces, all at once: source picker, **Table / SQL / Ask-AI** mode toggle,
**Grid / Chart / Pivot** view toggle, AI **Build / Write-SQL / Agent** sub-mode toggle, five wells
(Metrics, Columns, Filters, Sort, Format), and Save / Save-as / Share / Schedule / Export. For a
user who wants "count of invoices by process this month," that is overwhelming.

This session already did a visual redesign pass (segmented controls, single primary Run, empty
state — committed `b47fcf7`); it looks better but the **conceptual** load is still high.

**Direction (brainstorm next session — use `superpowers:brainstorming` + `ui-ux-pro-max`):**
- Lead with a **guided/simple path**: source → "what do you want to count/measure" (metric) →
  "broken down by" (a dimension, incl. the new date/process) → Run. Push SQL sandbox, pivot
  drag-drop, schedule, share behind an "Advanced" disclosure.
- Progressive disclosure (UX rule `progressive-disclosure`): don't show all five wells + three
  toggles to a first-time user.
- The AI "Build" surface is arguably the *right* simple entry point — but only once grounding
  (#1/#2) makes it reliable.
- Don't rebuild; restructure the existing controls' prominence.

---

## Issue 5 — "Counting Workitem IDs in Document Processing" — DEFERRED (user said later)

Captured for completeness. Today docprocessing's only metric is `doc_count` (a `COUNT(*)` from
`dbo.ReportingMetrics`, seeded by migration `0017`). A "distinct workitem-ID count" needs:
1. a workitem-id field exposed in the docprocessing catalog (check `SearchConfig.col_*` for the
   right column — it may already be there under a non-obvious key), and
2. a `COUNT(DISTINCT ...)` metric in `dbo.ReportingMetrics` (the semantic layer's `Aggregation`
   currently supports the blessed aggs in `nx_lib/reporting/semantic.py` — verify `COUNT DISTINCT`
   is allowed; may need a small extension). **Do this AFTER #1/#2 — explicitly parked by the user.**

---

## Recommended order next session

1. **Issue 2 (date dimension)** — highest leverage: unblocks time reporting *and* improves AI
   grounding. Design-first (touches catalog + query builder + maybe semantic Slice 2).
2. **Issue 1 (process picker)** — small, self-contained UI + tiny endpoint. Also improves AI
   grounding (process list).
3. **Issue 3 (AI)** — reproduce + read `ReportingAiAudit`/`app.log` first; much of it likely
   resolves once #1/#2 enrich the grounding.
4. **Issue 4 (simplify UX)** — brainstorm IA, then progressive-disclosure pass.
5. **Issue 5 (distinct workitem-ID metric)** — last, as the user directed.

## Key files (already traced — start here)

| Concern | File:line |
|---|---|
| Allowed processes (perm-derived) | `nx_lib/views/reporting.py:570` `_allowed_processes` |
| Scope intersection | `nx_lib/views/reporting.py:642` `_effective_scope` |
| Statconfig date cols loaded but unused | `nx_lib/views/reporting.py:585` `_load_process_configs` |
| docprocessing catalog (no dates) | `nx_lib/reporting/catalog.py: fetch_docprocessing_catalog` |
| Query builder (ignores export/import cols) | `nx_lib/reporting/query.py:108` `build_table_query` |
| AI grounding text | `nx_lib/views/reporting.py:319` `_ai_schema_text`, `:369` `_ai_catalog_text` |
| Builder JS state / scope | `templates/js/_reporting_js.html` (state @5, run payload @43) |
| Page template (no process UI) | `templates/reporting.html` |
| Dashboard date/process patterns to mirror | `nx_lib/views/dashboard.py:286–306, 575–590, 963–984` |

## Loose ends from prior work (still true)

- `sql/_migrations/NexoraDB/0019_fix_workitems_source_label_octo.sql` — **untracked, applied to
  INT, not committed.** Commit it on its own (idempotent no-op against INT):
  `git add sql/_migrations/NexoraDB/0019_*.sql && git commit -m "fix(reporting): rename Workitems source label 'Octopus' -> 'Octo'"`
- Branch is **unpushed** (30 commits ahead). Pre-push gate runs full e2e — run
  `.venv\Scripts\python.exe scripts\test_db_reset.py` first (memory `project_prepush_gate_e2e`).
- Owner ship items from earlier handoffs still pending (PROD migrations `0015`/`0016`/`0017`, RO
  login provisioning, Task Scheduler). See the semantic-Slice1 handoff §"Owner actions."
- The "FieldMetadata unavailable" WARNING is **benign by design** (optional table absent on INT;
  catalog falls back to string/sortable/non-aggregable). User chose "leave it." Note: it *does*
  weaken AI grounding (see Issue 3) — fixing the date/process gaps matters more than this.

## Verification done this session

- INT perm counts + `ben.streich` perms queried live (Issue 1 → confirmed UI gap, not perms).
- Traced `export_col`/`import_col` from Statconfig → `_load_process_configs` → `build_table_query`
  and confirmed they're never used (Issue 2 → confirmed real gap).
- Grepped templates/JS for any process picker → none exists (Issue 1 confirmed).
- No code changed this session — investigation + this handoff only.
