# Reporting: relative-date tokens in report definitions — design

- **Date:** 2026-06-10
- **Status:** approved design, NOT implemented (plan: `docs/superpowers/plans/2026-06-10-reporting-relative-date-tokens.md`)
- **Problem:** report definitions store date filters as absolute ISO strings (`{"op": "between", "value": ["2026-05-01", "2026-05-31"]}`). The wizard's "Last month" preset and AI-drafted definitions compute absolutes at *creation* time, so saved and scheduled reports go stale: a "last month" report scheduled monthly mails May data forever. `ops/run_scheduled_reports.py` re-runs `DefinitionJSON` verbatim with no resolution step.

## Goal

A date filter can carry a **relative-date token** that resolves to absolute dates **at every run**, so saved/scheduled/AI-built reports stay fresh. Absolute dates remain first-class and untouched.

## Token vocabulary (closed set, frozen)

| Token | Resolves to (inclusive day range) |
|---|---|
| `today` | current day |
| `yesterday` | previous day |
| `this_week` | ISO Monday → Sunday of the current week |
| `last_week` | ISO Monday → Sunday of the previous week |
| `this_month` | full current calendar month |
| `last_month` | full previous calendar month |
| `this_year` | full current calendar year |
| `last_year` | full previous calendar year |
| `last_3_months` | 1st of the month two months back → last day of the current month |
| `last_n_days` | rolling window: today − (n−1) → today; requires integer `n`, 1 ≤ n ≤ 366 |

"This"-period tokens cover the **full** calendar period (future days included — they simply match no data), mirroring the wizard's existing `presetRange()` semantics exactly (`_reporting_simple_js.html:532-540`: `this_month` = `[1st, last day of month]`, `this_year` = `[Jan 1, Dec 31]`, `last_3_months` = `[1st of m−2, last day of m]`), so switching the wizard presets to tokens changes no result. `last_3_months` is a fixed token because the wizard already offers that preset; dropping it would regress the wizard. No other tokens. The vocabulary is a frozen enum in code — extension requires a deliberate code change, not config.

**Reference date:** `datetime.date.today()` (server-local), consistently in interactive, export, and scheduler paths. This matches the AI grounding (`today=date.today().isoformat()`, `views/reporting.py:1190`). The scheduler currently computes `NextRunAt` with naive UTC (`schedule.py:62-95`) — token resolution deliberately does NOT reuse `utcnow()`: Swiss users mean Swiss calendar days. Users have no timezone column (`dbo.Users` has only `locale`); per-user timezones are out of scope. Week starts Monday (ISO).

## Definition shape (schema v1, additive)

A date filter's `value` may be a **token object** instead of a literal/list:

```json
{"field": "import_date", "op": "between", "value": {"token": "last_month"}}
{"field": "import_date", "op": "between", "value": {"token": "last_n_days", "n": 30}}
```

- Only `op: "between"` accepts a token value (a token *is* a range). All other ops keep literal-only values.
- Only **date-typed fields** accept tokens. The validator gains a `date_fields` parameter (set of field keys whose catalog `type` is `date`/`datetime`), mirroring the existing `grainable_fields` pattern (`schema.py:54`).
- `schemaVersion` stays `1` — the change is additive; every existing definition remains valid and untouched.

**Why value-level token objects, not new ops** (`{"op": "last_month"}`) or string sentinels (`"@last_month"`): new ops would pollute `FILTER_OPS` (`schema.py:19-33`), break the op/value-presence validation matrix, and mix presets into the Advanced op dropdown; string sentinels collide with literal data and are typo-fragile. A dict value is unambiguous (no literal value is a dict today), survives JSON round-trips, and leaves all op semantics alone.

## Resolution (one module, two choke points)

New module `nx_lib/reporting/tokens.py` — **standalone** (imports only stdlib `datetime`/`calendar`, no `schema` import, so no import cycle; the validator imports *from* it one-way):

- `RELATIVE_DATE_TOKENS` — frozen registry `{name: resolver(today) -> (start_date, end_date)}` (inclusive day range).
- `validate_token_value(value) -> error_message | None` — shape + vocabulary + `n` bounds check; returns a message string (the schema validator raises `ReportDefinitionError(message)`).
- `resolve_token(value, today) -> (start_date, end_date)` — inclusive range for one token value (also used by `api_run` for display metadata).
- `resolve_definition_tokens(definition, today=None) -> definition` — deep-copies when tokens are present; each token-valued filter is replaced by an **internal half-open pair**: `{field, op: "gte", value: start_iso}` + `{field, op: "lt", value: end_plus_one_day_iso}`. Returns the input unchanged (same object identity) when no tokens are present. Raises `ValueError` on a bad token (callers wrap into `ReportDefinitionError`).
- `date_fields_from_catalog(catalog) -> set` — fields whose catalog entry is `grainable` or has `type` `date`/`datetime` (the fields allowed to carry tokens).

**Why half-open instead of resolved `between`:** generic table sources can have `datetime` columns; `BETWEEN '2026-05-01' AND '2026-05-31'` silently drops May 31 intraday rows. `>= start AND < end+1day` is correct for both `date` and `datetime` columns. The docprocessing path normalizes via `_date_base()` (`query.py:67-75`) but the generic path (`table_query.py`) does not — half-open is the one shape that is safe everywhere. The expansion is internal only; the stored definition keeps the token.

**Call sites (validation first — the validator accepts and checks tokens — then resolution, then SQL build).** `runner.execute_definition` does NOT share `_prepare_run` (verified), so both need it:

1. `nx_lib/views/reporting.py:_prepare_run` (713-800), once per provider branch right after `validate_report_definition` — covers interactive runs (`api_run`:913) and `api_export` (1474). (`api_export_grid` takes client-rendered rows, no definition — unaffected.)
2. `nx_lib/reporting/runner.py:execute_definition` (50-150), once per provider branch after its `validate_report_definition` — covers the scheduler (`ops/run_scheduled_reports.py:_process`, 58-93) with zero scheduler changes.

**Defense in depth:** `query.py:_filter_clause` (123-153) raises `QueryBuildError` and `table_query.py:_build_conditions` (63-101) raises `TableQueryError` if a dict value ever reaches them — tokens must never bind as SQL parameters.

**Run response metadata:** `api_run` additionally returns `resolvedDates: [{field, token, n?, start, end}]` (inclusive display range from `resolve_token`) when the definition contains tokens, so the UI shows what actually ran (see Transparency below).

## UI

**Simple wizard (time-range step, `_reporting_simple.html:56-66`, `presetRange()` at `_reporting_simple_js.html:532-540`):** preset chips stop computing client-side absolutes and instead emit token values (`this_month`, `last_month`, `last_3_months`, `this_year`, `last_year`; `all_time` keeps emitting no filter). The custom flatpickr range keeps emitting absolutes. Net UI change: invisible; net behavior change: wizard-built saved reports stay fresh.

**Advanced Filters well (`renderFilters`, `_reporting_js.html:623-681`):** for date-typed fields the value control gains a preset `<select>`: "Custom dates…" (default → the existing single-value flatpickr + op dropdown, unchanged) plus the token list, plus "Last N days…" (reveals a small number input). Choosing a token sets `f.op = 'between'`, `f.value = {token: ...}` and **hides the op select** (the visible op dropdown deliberately has no `between` entry today — `_reporting_js.html:644-645` — and a token *is* the operator semantics). Choosing "Custom dates…" restores the op select and an empty value. Since `renderFilters` re-renders the well from `state.filters` on every change, hydration of a saved token filter falls out for free: it reads `f.value`, recognizes the token object, and pre-selects the matching preset. Token values render as humanized labels ("Last month"), never raw JSON.

**Transparency:** the Simple result `rsMsg` line (`aiSummaryLine`, `_reporting_simple_js.html:247-260`) humanizes token values, and after the run completes the resolved range from `resolvedDates` is appended: `Last month (2026-05-01 → 2026-05-31)`. For wizard-built (non-AI) reports with token filters, `rsMsg` shows just the resolved-range part. A user always sees both the intent and the dates that actually ran.

## AI surfaces

- `_SYSTEM_DEF` (`ai.py:195-234`): document the token syntax with one exact JSON example; instruct — relative phrasing ("last month", "this year", "letzte Woche") → emit the matching token; explicit dates ("May 2026", "since 2026-01-01") → emit absolutes. The existing `today` grounding stays (needed for explicit-date math).
- `_AGENT_SYSTEM` (`ai.py:405-441`): same instruction, one sentence.
- `coerce_definition` (`schema.py:172-275`): normalize token case (`{"token": "Last_Month"}` → `last_month`) and coerce a string `n` to int, mirroring the existing grain/op normalization.
- The agent's `build_definition` tool (`ai_tools.py:44-54`) needs no schema change — its `definition` parameter is unconstrained; validation flows through the same validator.
- No per-field catalog marking: the vocabulary is global, so it lives once in the prompts ("grainable/date-typed fields accept relative tokens"), not on every catalog line — the serialized catalog (`ai_schema.py:88-141`) stays unchanged.

## Out of scope

- Per-user timezones (no `Users.timezone` column; server-local is the contract).
- Fiscal periods, quarters, `last_n_months`, custom anchors — vocabulary is frozen.
- Migrating existing saved reports' absolute dates to tokens (opt-in only, by re-editing).
- Metric-value-relative filters ("count > last month's average").

## Error handling

- Unknown token / bad shape / `n` out of bounds → validator error with the allowed vocabulary listed (so the AI self-repair loop can fix it; generic errors are unrecoverable for the model).
- Token on a non-date field or with an op other than `between` → validator error naming the field/op.
- Dict value reaching a query builder → `ValueError` (programming error, not user error).

## Testing

- **Unit (`tests/unit/test_reporting_tokens.py`, new):** every token's resolution against fixed `today` values — month-length edges (Jan 31 → "last_month" = January…, Mar 1, leap-year Feb), ISO week boundaries (Monday/Sunday), `last_n_days` bounds, year boundaries (Jan 1).
- **Unit (schema):** token accept/reject matrix — wrong op, non-date field, unknown token, bad `n`, case coercion.
- **Unit (query/table_query):** resolved definitions build correct half-open SQL; dict value raises.
- **Unit (runner/views):** resolution called at each choke point with frozen `today` (monkeypatched).
- **Unit (ai prompt-content):** `_SYSTEM_DEF`/`_AGENT_SYSTEM` mention tokens, in the style of `test_system_def_teaches_distinct_via_metrics`.
- **e2e (`tests/e2e/test_reporting_simple.py` + advanced):** wizard preset → saved definition contains the token (not absolutes); Advanced preset select round-trips through save/load; result line shows humanized label + resolved range. No AI involvement → fully e2e-able.
- **i18n:** token labels + new UI strings translated de/fr/it; pot-sync suite stays green.

## Rejected alternatives

1. **New filter ops per token** — pollutes the op enum, breaks value-presence validation, ugly op dropdown (see above).
2. **Resolve at save time, store absolutes + token "recipe" side-band** — two sources of truth; export/share paths would leak stale absolutes.
3. **SQL-side resolution (`DATEADD(...)` expressions)** — duplicates calendar logic per builder/dialect, unparameterizable, harder to test; Python resolution is one function with frozen-date tests.
