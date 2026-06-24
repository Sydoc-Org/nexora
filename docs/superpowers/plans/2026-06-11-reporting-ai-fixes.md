# Reporting AI Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five AI bugs found in the 2026-06-10 stakeholder browser tour — missing quarter tokens, AI never emitting date grain, the distinct-count-per-group trap, the agent's unknown-SQL-target dead end, metric-less-source misdrafts with confusing error messages — consolidate the redundant `workitem_count` metric (owner-verified 2026-06-11: all count variants identical on PROD), and make **every** Simple result tweakable (refine bar + editable chips on wizard/library results, wizard re-entry with preserved choices).

**Architecture:** All fixes are prompt-engineering + small deterministic guards along the existing Surface A/C pipeline: token vocabulary lives in `nx_lib/reporting/tokens.py`, both system prompts live in `nx_lib/reporting/ai.py` (`_SYSTEM_DEF`, `_AGENT_SYSTEM`), the gate is `_validate_definition_for_user` in `nx_lib/views/reporting.py`, grounding text comes from `nx_lib/reporting/ai_schema.py`, and the Simple-tab UI strings live in `templates/js/_reporting_simple_js.html`. No new tables, no migrations.

**Tech Stack:** Flask, pytest (unit + integration with stubbed AI transport), Flask-Babel i18n (de/fr/it), Jinja JS partials.

**Background — the five bugs (from the 2026-06-10 stakeholder tour, audit-verified):**

1. **No quarter tokens.** `RELATIVE_DATE_TOKENS` has no `this_quarter`/`last_quarter`. Asked "last quarter", the model picked `last_3_months` (resolves 2026-04-01 → 2026-06-30 — includes the *current* month; the user meant Q1). Silent wrong-date reports.
2. **AI never emits `grain`.** "Documents per month this year" → definition had `columns: [{"field": "export_date"}]` with **no grain**; the result bucketed per raw day (`2026-02-02`) while the explanation claimed monthly. The wizard emits grain correctly — only the prompts lack a worked example.
3. **Distinct-per-group trap.** "How many distinct workitems per process" → model emitted `columns: [processname, workitem_id]` + `metrics: [workitem_count]` (a `count_distinct` of `workitem_id`). Grouping by the counted field forces every count to 1; the gate said *valid*. The current DISTINCT prompt rule actively teaches this mistake for "count distinct X per Y" questions.
4. **Agent dies on `run_sql`.** Live trace: 3× `build_definition` invalid → SQL fallback → `run_sql` failed `"unknown SQL target"` → turn cap → "(no answer)". The grounding never names the valid `target` values and the error message doesn't list them, so the model can't self-repair. Audit history: nearly every agent run ends `max_turns` with an empty answer.
5. **Metric-less source misdrafts + confusing error.** The first "distinct workitems" ask picked the `workitems` source (which has **no** registered metrics), invented `workitem_count` there, and hard-failed. The Simple tab then showed *"The AI could not draft that report — try rephrasing. (…model explanation…)"* — the JS prefers `explanation` over the actual gate `error`.
6. **Wrong date field for time questions** (owner-reported 2026-06-11). Asked about *"April 2026"*, the model filtered on **Document Date** (the date printed on the document) instead of the processing dates. Time-period questions must default to `export_date` (or `import_date` when the question says imported/received); content-date fields are only correct when the user names them explicitly.

**Measurement finding (2026-06-11, owner-verified on PROD):** `COUNT(*)`, `COUNT(WorkitemID)`, `COUNT(DISTINCT WorkItemID)` and `COUNT(Barcode)` all return the same number on the PROD Statistics tables — one row per workitem, no NULL ids, no duplicates. The earlier staging gap (Posteingang +799 rows in May) does not reproduce on PROD, so `workitem_count` (count_distinct) always equals `doc_count` there. Consequence: **Task 12** disables `workitem_count` so the picker offers one count metric; the `count_distinct` machinery (and Task 5/6's guard) stays — it is metric-registry-generic and unit-covered.

**Out of scope (deliberately):** registering metrics for `gen_pdqm`/`workitems` (zero-code admin action at `/reporting/metrics`); Advanced-builder save-as UX; raw-code column headers.

**Anchors note:** all line numbers below are the pre-plan state of `feature/2.5.63` (HEAD `554cfc3`). Earlier tasks shift later anchors by a few lines — match on the quoted code, not the absolute number.

**Commit note:** every commit in this repo currently needs `SQL_SYNC_SKIP=1` (INT `SchemaMigrations` CRLF drift — see memory `project_int_migration_crlf_drift`). All commit steps below include it.

---

## File structure

| File | Role in this plan |
|---|---|
| `nx_lib/reporting/tokens.py` | Add `_quarter_start` helper + `this_quarter`/`last_quarter` resolvers (Task 1) |
| `nx_lib/reporting/ai.py` | `_SYSTEM_DEF` (195–243) + `_AGENT_SYSTEM` (437–459): quarter tokens, grain worked example, two-case DISTINCT rule, metrics-required-for-aggregation rule (Tasks 2, 4, 5, 8) |
| `nx_lib/reporting/semantic.py` | New pure helper `drop_columns_shadowing_distinct_metrics` (Task 6) |
| `nx_lib/views/reporting.py` | Call the new guard in `_validate_definition_for_user` (395–451); name allowed targets in `_run_sql` error (549–550) and in agent grounding (1442–1457) (Tasks 6, 7) |
| `nx_lib/reporting/ai_schema.py` | Mark metric-less curated sources "cannot aggregate" in `serialize_sources_catalog` (88–141) (Task 8) |
| `templates/js/_reporting_simple_js.html` | `TOKEN_LABELS` (262–268) + `I18N` keys + wizard presets (784–787); error-precedence fix (916) (Tasks 3, 9) |
| `templates/js/_reporting_js.html` | `DATE_TOKEN_PRESETS` (20–31) (Task 3) |
| `tests/unit/test_reporting_tokens.py` | Quarter-token resolution tests (Task 1) |
| `tests/unit/test_reporting_ai_definition.py` | Prompt-content tests for `_SYSTEM_DEF` (Tasks 2, 4, 5, 8) |
| `tests/unit/test_reporting_ai_agentic.py` | Prompt-content tests for `_AGENT_SYSTEM` (Tasks 2, 4, 5) |
| `tests/unit/test_reporting_semantic.py` | Guard helper tests (Task 6) |
| `tests/unit/test_reporting_ai_schema.py` | Grounding marker test (Task 8) |
| `tests/integration/test_reporting_ai_routes.py` | Agent grounding + guard integration tests (Tasks 6, 7) |
| `translations/{de,fr,it}/LC_MESSAGES/messages.po` | "This quarter" / "Last quarter" (Task 10) |
| `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md` | Token vocabulary + behavior docs (Tasks 11, 12) |
| `sql/_migrations/NexoraDB/0021_disable_workitem_count_metric.sql` | Create — consolidate to one count metric (Task 12) |
| `templates/_reporting_simple.html` | "Adjust in wizard" button in the result actions (Task 15) |
| `templates/js/_reporting_simple_js.html` | Un-gate chips/refine from AI-only (Task 14); wizard re-entry with preserved state (Task 15) |

---

### Task 1: Quarter tokens in the vocabulary

**Files:**
- Modify: `nx_lib/reporting/tokens.py` (helpers ~line 25–37, `RELATIVE_DATE_TOKENS` 41–52)
- Test: `tests/unit/test_reporting_tokens.py`

- [ ] **Step 1: Write the failing tests**

Append to the `test_fixed_token_resolution` parametrize list in `tests/unit/test_reporting_tokens.py` (after the `last_3_months` row, line 35; `TODAY` is 2026-06-10, a Wednesday in Q2):

```python
        ("this_quarter", "2026-04-01", "2026-06-30"),
        ("last_quarter", "2026-01-01", "2026-03-31"),
```

And append a year-boundary test after `test_month_edges_resolve_correctly` (line 70):

```python
def test_quarter_edges_resolve_correctly():
    # January: last_quarter crosses the year boundary into Q4.
    assert resolve_token({"token": "last_quarter"}, _d("2026-01-15")) == (
        _d("2025-10-01"),
        _d("2025-12-31"),
    )
    # Last day of a quarter still resolves to its own quarter.
    assert resolve_token({"token": "this_quarter"}, _d("2026-03-31")) == (
        _d("2026-01-01"),
        _d("2026-03-31"),
    )
    # First day of a quarter.
    assert resolve_token({"token": "this_quarter"}, _d("2026-10-01")) == (
        _d("2026-10-01"),
        _d("2026-12-31"),
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py -v -k quarter`
Expected: FAIL — `unknown relative-date token: 'this_quarter'` (from `validate_token_value` inside `resolve_token`).

- [ ] **Step 3: Implement the resolvers**

In `nx_lib/reporting/tokens.py`, add below `_week_of` (after line 36):

```python
def _quarter_start(d, delta=0):
    """First day of d's calendar quarter, shifted by `delta` quarters."""
    q_index = d.year * 4 + (d.month - 1) // 3 + delta
    year, q = divmod(q_index, 4)
    return datetime.date(year, q * 3 + 1, 1)
```

And add two entries to `RELATIVE_DATE_TOKENS` after the `"last_month"` entry (line 47):

```python
    "this_quarter": lambda t: (
        _quarter_start(t),
        _quarter_start(t, 1) - datetime.timedelta(days=1),
    ),
    "last_quarter": lambda t: (
        _quarter_start(t, -1),
        _quarter_start(t) - datetime.timedelta(days=1),
    ),
```

(`validate_token_value` and `resolve_token` key off the dict — no other change needed. The error message listing allowed tokens updates itself via `", ".join(sorted(RELATIVE_DATE_TOKENS))`.)

- [ ] **Step 4: Run the token suite**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py -v`
Expected: all PASS (existing + 2 new parametrize rows + `test_quarter_edges_resolve_correctly`).

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/tokens.py tests/unit/test_reporting_tokens.py
git commit -m "feat(reporting): this_quarter and last_quarter relative-date tokens"
```

---

### Task 2: Teach both prompts the quarter tokens (and warn off last_3_months)

**Files:**
- Modify: `nx_lib/reporting/ai.py` — `_SYSTEM_DEF` token sentence (lines 237–239), `_AGENT_SYSTEM` token list (lines 455–457)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_ai_definition.py` (near `test_system_def_teaches_distinct_via_metrics`, line 116):

```python
def test_system_def_teaches_quarter_tokens():
    s = ai._SYSTEM_DEF
    assert "this_quarter" in s and "last_quarter" in s
    # The disambiguation that prevents the last_3_months mispick:
    assert "calendar quarter" in s.lower()
```

Append to `tests/unit/test_reporting_ai_agentic.py` (near `test_agent_system_prompt_teaches_distinct_and_processes`, line 219; module imports `_AGENT_SYSTEM` already for that test — follow its import style):

```python
def test_agent_system_prompt_teaches_quarter_tokens():
    s = _AGENT_SYSTEM
    assert "this_quarter" in s and "last_quarter" in s
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py::test_system_def_teaches_quarter_tokens tests\unit\test_reporting_ai_agentic.py::test_agent_system_prompt_teaches_quarter_tokens -v`
Expected: both FAIL on the `this_quarter` assertion.

- [ ] **Step 3: Edit `_SYSTEM_DEF`**

In `nx_lib/reporting/ai.py`, replace (lines 237–239):

```python
    ' {"token": "last_month"}}. Valid tokens: today, yesterday, this_week,'
    " last_week, this_month, last_month, this_year, last_year, last_3_months,"
    ' and {"token": "last_n_days", "n": <1-366>}. Token values are resolved'
```

with:

```python
    ' {"token": "last_month"}}. Valid tokens: today, yesterday, this_week,'
    " last_week, this_month, last_month, this_quarter, last_quarter,"
    " this_year, last_year, last_3_months,"
    ' and {"token": "last_n_days", "n": <1-366>}. "Last quarter" means the'
    " previous CALENDAR quarter — use last_quarter, never last_3_months (a"
    " rolling window that includes the current month). Token values are resolved"
```

- [ ] **Step 4: Edit `_AGENT_SYSTEM`**

In `nx_lib/reporting/ai.py`, replace (lines 455–457):

```python
    ' e.g. {"field": "<date field>", "op": "between", "value": {"token": "last_month"}} (tokens: today,'
    " yesterday, this_week, last_week, this_month, last_month, this_year,"
    ' last_year, last_3_months, last_n_days with "n") — these resolve at run'
```

with:

```python
    ' e.g. {"field": "<date field>", "op": "between", "value": {"token": "last_month"}} (tokens: today,'
    " yesterday, this_week, last_week, this_month, last_month, this_quarter,"
    ' last_quarter, this_year, last_year, last_3_months, last_n_days with "n";'
    ' "last quarter" = the previous calendar quarter, i.e. last_quarter, not'
    " last_3_months) — these resolve at run"
```

- [ ] **Step 5: Run the two AI prompt suites**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v`
Expected: all PASS (new tests green, existing token/DISTINCT/today tests untouched).

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py
git commit -m "feat(reporting): teach AI prompts quarter tokens with last_3_months disambiguation"
```

---

### Task 3: Quarter tokens in the UI (chip labels, Advanced presets, wizard presets)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` — `I18N` block (~line 38–48), `TOKEN_LABELS` (262–268), wizard time presets (784–787)
- Modify: `templates/js/_reporting_js.html` — `DATE_TOKEN_PRESETS` (20–31)

No unit test covers these Jinja JS partials; the e2e + browser pass in Task 12 verifies them. Keep the new msgids exactly `"This quarter"` / `"Last quarter"` — Task 10 translates them.

- [ ] **Step 1: Add the two I18N keys in `_reporting_simple_js.html`**

After the `lastYear:` line (line 38), add:

```javascript
    thisQuarter: {{ _("This quarter")|tojson }},
    lastQuarter: {{ _("Last quarter")|tojson }},
```

- [ ] **Step 2: Extend `TOKEN_LABELS` (line 262–268)**

Replace:

```javascript
  var TOKEN_LABELS = {
    today: I18N.tokenToday, yesterday: I18N.tokenYesterday,
    this_week: I18N.thisWeek, last_week: I18N.lastWeek,
    this_month: I18N.thisMonth, last_month: I18N.lastMonth,
    last_3_months: I18N.last3Months, this_year: I18N.thisYear,
    last_year: I18N.lastYear, last_n_days: I18N.lastNDays
  };
```

with:

```javascript
  var TOKEN_LABELS = {
    today: I18N.tokenToday, yesterday: I18N.tokenYesterday,
    this_week: I18N.thisWeek, last_week: I18N.lastWeek,
    this_month: I18N.thisMonth, last_month: I18N.lastMonth,
    this_quarter: I18N.thisQuarter, last_quarter: I18N.lastQuarter,
    last_3_months: I18N.last3Months, this_year: I18N.thisYear,
    last_year: I18N.lastYear, last_n_days: I18N.lastNDays
  };
```

(The Simple-tab chip preset `<select>` at lines 315–330 iterates `Object.keys(TOKEN_LABELS)` — it picks the new tokens up automatically.)

- [ ] **Step 3: Extend the wizard time presets (lines 784–787)**

Replace:

```javascript
    [['this_month', I18N.thisMonth], ['last_month', I18N.lastMonth],
     ['last_3_months', I18N.last3Months], ['this_year', I18N.thisYear],
     ['last_year', I18N.lastYear], ['all_time', I18N.allTime],
     ['custom', I18N.custom]].forEach(function (p) {
```

with:

```javascript
    [['this_month', I18N.thisMonth], ['last_month', I18N.lastMonth],
     ['last_quarter', I18N.lastQuarter], ['last_3_months', I18N.last3Months],
     ['this_year', I18N.thisYear], ['last_year', I18N.lastYear],
     ['all_time', I18N.allTime], ['custom', I18N.custom]].forEach(function (p) {
```

(`this_quarter` is deliberately left off the wizard button row to keep it one line — it remains reachable via the AI, the chip editor, and the Advanced preset select.)

- [ ] **Step 4: Extend `DATE_TOKEN_PRESETS` in `_reporting_js.html` (lines 20–31)**

After the `['last_month', …]` entry (line 26), add:

```javascript
    ['this_quarter', {{ _("This quarter")|tojson }}],
    ['last_quarter', {{ _("Last quarter")|tojson }}],
```

- [ ] **Step 5: Sanity-run the template**

Run: `.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -k wizard --collect-only -q`
Expected: collection succeeds (no Jinja syntax error). Full e2e runs in the final verification task (Task 16).

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add templates/js/_reporting_simple_js.html templates/js/_reporting_js.html
git commit -m "feat(reporting): quarter token presets and labels in Simple and Advanced UI"
```

---

### Task 4: Grain worked example in the prompts

**Files:**
- Modify: `nx_lib/reporting/ai.py` — `_SYSTEM_DEF` grain sentence (lines 217–220), `_AGENT_SYSTEM` (after line 453)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_teaches_grain_with_worked_example():
    s = ai._SYSTEM_DEF
    # The hard rule:
    assert "MUST carry the matching" in s
    # The worked example (verbatim JSON fragment the model can copy):
    assert '"grain": "month"' in s
    assert '"metric": "doc_count"' not in s  # example must stay generic, no real codes
```

Append to `tests/unit/test_reporting_ai_agentic.py`:

```python
def test_agent_system_prompt_requires_grain_for_per_period():
    assert '"grain"' in _AGENT_SYSTEM
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py::test_system_def_teaches_grain_with_worked_example tests\unit\test_reporting_ai_agentic.py::test_agent_system_prompt_requires_grain_for_per_period -v`
Expected: both FAIL (`MUST carry the matching` / `"grain"` not found).

- [ ] **Step 3: Extend `_SYSTEM_DEF`**

In `nx_lib/reporting/ai.py`, the grain sentence currently reads (lines 216–220):

```python
    'total, use "metrics" with "columns": []. Only metric codes from the'
    "source's metrics line are valid. Fields flagged (grainable) are date "
    'fields: a column for one may carry "grain": '
    '"day"|"week"|"month"|"quarter"|"year" to bucket it; filters always use '
    "the raw date."
```

Replace it with:

```python
    'total, use "metrics" with "columns": []. Only metric codes from the'
    "source's metrics line are valid. Fields flagged (grainable) are date "
    'fields: a column for one may carry "grain": '
    '"day"|"week"|"month"|"quarter"|"year" to bucket it; filters always use '
    "the raw date."
    ' When the question groups by a time period ("per month", "monthly",'
    ' "per week", "by quarter", "over the years"), the date column MUST carry'
    ' the matching "grain" — e.g. for "<things> per month this year":'
    ' "columns": [{"field": "<date key>", "header": "Month", "grain": "month"}],'
    ' "metrics": [{"metric": "<count code>"}], "filters": [{"field":'
    ' "<date key>", "op": "between", "value": {"token": "this_year"}}].'
    " A date column WITHOUT grain buckets per raw day, which contradicts any"
    " per-month/per-week/per-quarter/per-year question."
```

- [ ] **Step 4: Extend `_AGENT_SYSTEM`**

In `nx_lib/reporting/ai.py`, after the DISTINCT sentence block ending `"…or none rather than a guess."` (line 453), insert:

```python
    ' When a question groups by a time period (per day/week/month/quarter/'
    'year), the date column in the definition MUST carry the matching'
    ' "grain" (e.g. {"field": "<date key>", "grain": "month"}).'
```

- [ ] **Step 5: Run the suites**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py
git commit -m "fix(reporting): AI prompts require date grain for per-period questions"
```

---

### Task 5: Two-case DISTINCT rule (kill the count-by-the-counted-field trap)

**Files:**
- Modify: `nx_lib/reporting/ai.py` — `_SYSTEM_DEF` DISTINCT paragraph (lines 222–226), `_AGENT_SYSTEM` DISTINCT sentence (lines 450–453)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai_agentic.py`

The existing tests `test_system_def_teaches_distinct_via_metrics` (asserts `"GROUP BY" in s` and `"duplicate rows" in s`) and `test_agent_system_prompt_teaches_distinct_and_processes` (asserts `"GROUP BY" in s`) must stay green — the replacement text below keeps both phrases.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_forbids_grouping_by_the_counted_field():
    s = ai._SYSTEM_DEF
    assert "NEVER also add" in s
    assert "forces every count to 1" in s
```

Append to `tests/unit/test_reporting_ai_agentic.py`:

```python
def test_agent_system_prompt_forbids_grouping_by_the_counted_field():
    assert "forces every count to 1" in _AGENT_SYSTEM
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py::test_system_def_forbids_grouping_by_the_counted_field tests\unit\test_reporting_ai_agentic.py::test_agent_system_prompt_forbids_grouping_by_the_counted_field -v`
Expected: both FAIL.

- [ ] **Step 3: Replace the `_SYSTEM_DEF` paragraph (lines 222–226)**

Replace:

```python
    " When the question asks for the DISTINCT/different/unique values of a"
    ' field, put that field in "columns" AND add a count metric in "metrics" —'
    " with metrics present the selected columns become GROUP BY dimensions, so"
    " each value appears once (with its count). Never answer a distinct-values"
    " question with bare columns and no metrics: that returns duplicate rows."
```

with:

```python
    " Distinct/unique questions come in two shapes — pick the right one."
    ' (1) "List the distinct values of X": put X in "columns" and add a plain'
    " count metric — with metrics present the columns become GROUP BY"
    " dimensions, so each value appears once with its row count (bare columns"
    " with no metrics would return duplicate rows)."
    ' (2) "How many distinct X per Y": put ONLY Y in "columns" and use a'
    " distinct-count metric of X — NEVER also add X to \"columns\": grouping by"
    " the very field being counted forces every count to 1. With no Y at all"
    ' ("how many distinct X in total"), use the distinct-count metric with'
    ' "columns": [].'
```

- [ ] **Step 4: Replace the `_AGENT_SYSTEM` sentence (lines 450–453)**

Replace:

```python
    " For distinct/unique-values questions, build a definition with that field"
    ' in "columns" plus a count metric — metrics make the columns GROUP BY'
    " dimensions. Match process words against whole process ids and their"
    " humanized labels; include all matches, or none rather than a guess."
```

with:

```python
    ' For "list the distinct values of X" build a definition with X in'
    ' "columns" plus a plain count metric — metrics make the columns GROUP BY'
    ' dimensions. For "how many distinct X per Y" put ONLY Y in "columns" and'
    " use a distinct-count metric of X; never group by the counted field"
    " itself — that forces every count to 1."
    " Match process words against whole process ids and their"
    " humanized labels; include all matches, or none rather than a guess."
```

- [ ] **Step 5: Run the suites (old + new tests)**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v`
Expected: all PASS, including the pre-existing `test_system_def_teaches_distinct_via_metrics` and `test_agent_system_prompt_teaches_distinct_and_processes`.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py
git commit -m "fix(reporting): two-case DISTINCT prompt rule stops count-by-counted-field drafts"
```

---

### Task 6: Deterministic guard — drop columns that shadow a distinct-count metric

Prompts reduce the mistake; this guard makes it *impossible*. If a definition carries a `count_distinct` metric AND lists that metric's `base_field` as a grouping column, silently drop the column (the gate already mutates definitions via `coerce_definition`, so in-place repair is the established pattern — see the comment at `nx_lib/views/reporting.py:423-427`). Both Surface A and the agent's `build_definition` tool route through `_validate_definition_for_user`, so one call site fixes both.

**Files:**
- Modify: `nx_lib/reporting/semantic.py` (new helper, after `resolve_metrics`, ~line 60)
- Modify: `nx_lib/views/reporting.py` — `_validate_definition_for_user`, after the `coerce_definition(...)` call (line 434)
- Test: `tests/unit/test_reporting_semantic.py` (append; if the file does not exist, create it with the import block shown)
- Test: `tests/integration/test_reporting_ai_routes.py` (append)

- [ ] **Step 1: Write the failing unit tests**

In `tests/unit/test_reporting_semantic.py` (create with this exact content if absent; otherwise append the import + tests):

```python
from nx_lib.reporting.semantic import drop_columns_shadowing_distinct_metrics

REGISTRY = {
    "doc_count": {"aggregation": "count", "base_field": None},
    "workitem_count": {"aggregation": "count_distinct", "base_field": "workitem_id"},
}


def test_drops_column_matching_distinct_metric_base_field():
    rd = {
        "columns": [{"field": "processname"}, {"field": "workitem_id"}],
        "metrics": [{"metric": "workitem_count"}],
    }
    dropped = drop_columns_shadowing_distinct_metrics(rd, REGISTRY)
    assert dropped == ["workitem_id"]
    assert [c["field"] for c in rd["columns"]] == ["processname"]


def test_drop_can_empty_columns_for_grand_total():
    rd = {
        "columns": [{"field": "workitem_id"}],
        "metrics": [{"metric": "workitem_count"}],
    }
    assert drop_columns_shadowing_distinct_metrics(rd, REGISTRY) == ["workitem_id"]
    assert rd["columns"] == []


def test_plain_count_metric_never_drops_columns():
    # "List distinct workitem ids with their row counts" stays intact.
    rd = {
        "columns": [{"field": "workitem_id"}],
        "metrics": [{"metric": "doc_count"}],
    }
    assert drop_columns_shadowing_distinct_metrics(rd, REGISTRY) == []
    assert [c["field"] for c in rd["columns"]] == ["workitem_id"]


def test_no_metrics_is_a_no_op():
    rd = {"columns": [{"field": "workitem_id"}], "metrics": []}
    assert drop_columns_shadowing_distinct_metrics(rd, REGISTRY) == []
    assert rd["columns"] == [{"field": "workitem_id"}]


def test_unknown_metric_code_is_ignored():
    rd = {
        "columns": [{"field": "workitem_id"}],
        "metrics": [{"metric": "nope"}],
    }
    assert drop_columns_shadowing_distinct_metrics(rd, REGISTRY) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_semantic.py -v -k shadow or drop`
Expected: FAIL — `ImportError: cannot import name 'drop_columns_shadowing_distinct_metrics'`.

- [ ] **Step 3: Implement the helper**

In `nx_lib/reporting/semantic.py`, after `resolve_metrics` (ends ~line 59):

```python
def drop_columns_shadowing_distinct_metrics(rd, metric_registry):
    """Remove grouping columns that name the very field a count_distinct
    metric aggregates — GROUP BY the counted field forces every count to 1,
    so such a draft is always wrong. Mutates `rd` in place (same contract as
    coerce_definition); returns the list of dropped field keys."""
    distinct_bases = set()
    for ref in rd.get("metrics") or []:
        spec = metric_registry.get((ref or {}).get("metric")) or {}
        if spec.get("aggregation") == "count_distinct" and spec.get("base_field"):
            distinct_bases.add(spec["base_field"])
    if not distinct_bases:
        return []
    cols = rd.get("columns") or []
    dropped = [c.get("field") for c in cols if c.get("field") in distinct_bases]
    if dropped:
        rd["columns"] = [c for c in cols if c.get("field") not in distinct_bases]
    return dropped
```

- [ ] **Step 4: Run the unit tests**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_semantic.py -v`
Expected: all PASS.

- [ ] **Step 5: Wire it into the gate**

In `nx_lib/views/reporting.py`, import it next to the existing semantic import (grep `from ..reporting.semantic import` near the top and extend that line), then in `_validate_definition_for_user` insert between the `coerce_definition(...)` call (ends line 434) and the `to_validate = ...` line (line 435):

```python
        # A count_distinct metric grouped by its own base field always yields
        # 1 per row — drop the shadowing column instead of bouncing the draft.
        drop_columns_shadowing_distinct_metrics(definition, source_metrics)
```

**Ordering note:** `source_metrics = _metrics_for_source(source["id"])` is assigned at line 422, *before* `coerce_definition` — no reordering needed. `coerce_definition` must run first so label-typed column fields (`"Workitem ID"`) are resolved to keys (`workitem_id`) before the comparison.

- [ ] **Step 6: Write the failing integration test**

Append to `tests/integration/test_reporting_ai_routes.py`, following the patch pattern of `test_ai_build_does_not_require_sql_permission` (lines 187–220) but **without** patching `_validate_definition_for_user` (the point is to exercise the real gate). Patch the catalog + metrics seams instead:

```python
def test_ai_build_drops_column_shadowing_distinct_metric(user_client):
    drafted = {
        "schemaVersion": 1,
        "visualization": "table",
        "source": "docprocessing",
        "title": "Distinct workitems per process",
        "columns": [{"field": "processname"}, {"field": "workitem_id"}],
        "metrics": [{"metric": "workitem_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 5000,
    }
    catalog = [
        {"field": "processname", "label": "Processname", "type": "string",
         "filterable": True, "sortable": True},
        {"field": "workitem_id", "label": "Workitem ID", "type": "string",
         "filterable": True, "sortable": True},
    ]
    metrics = {"workitem_count": {"aggregation": "count_distinct", "base_field": "workitem_id"}}
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="SOURCE docprocessing ..."),
        patch(
            "nx_lib.views.reporting.ai_ask_definition",
            return_value=_def_result(definition=drafted, explanation="x"),
        ),
        patch("nx_lib.views.reporting._allowed_processes", return_value=["compass.01_Invoice_SAP"]),
        patch("nx_lib.views.reporting.fetch_docprocessing_catalog", return_value=catalog),
        patch("nx_lib.views.reporting._metrics_for_source", return_value=metrics),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "distinct per process"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert [c["field"] for c in data["definition"]["columns"]] == ["processname"]
```

**Stub-factory change this test needs:** `_def_result` (line 166 of this test file) currently has signature `def _def_result(source="gen_pdqm"):` with a canned definition. Extend it backward-compatibly:

```python
def _def_result(source="gen_pdqm", definition=None, explanation="by outcome"):
    return AiDefinitionResult(
        definition=definition
        or {
            "schemaVersion": 1,
            "visualization": "table",
            "source": source,
            "title": "T",
            "columns": [{"field": "Outcome"}],
            "filters": [],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 5000,
        },
        explanation=explanation,
        model="m",
        # keep the remaining kwargs exactly as they are today (provider/tokens)
    )
```

Existing call sites pass no kwargs and keep their behavior. `source: "docprocessing"` resolves through the real `_get_effective_source` (the neighbouring build tests already post curated sources through it).

- [ ] **Step 7: Run the integration test**

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v -k shadow`
Expected: PASS (and FAIL if Step 5's wiring is reverted — verify once by commenting the call out, then restore).

- [ ] **Step 8: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/semantic.py nx_lib/views/reporting.py tests/unit/test_reporting_semantic.py tests/integration/test_reporting_ai_routes.py
git commit -m "fix(reporting): gate drops grouping columns that shadow a distinct-count metric"
```

---

### Task 7: Agent knows the run_sql targets

Two changes: (a) the grounding names the valid `target` values when the data tools are bound; (b) the `"unknown SQL target"` error enumerates them so the model self-repairs on its bounded retry.

**Files:**
- Modify: `nx_lib/views/reporting.py` — `_run_sql` (lines 549–550), agent grounding (lines 1446–1447)
- Test: `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_reporting_ai_routes.py`:

```python
def test_run_sql_unknown_target_error_lists_allowed_targets():
    from nx_lib.reporting.schema import ReportDefinitionError
    from nx_lib.views.reporting import _run_sql

    with pytest.raises(ReportDefinitionError) as e:
        _run_sql("nope", "SELECT 1", userid="1", username="t")
    msg = str(e.value)
    assert "octopus" in msg and "statistics" in msg
```

(If this file does not already `import pytest`, add it to the imports.)

For the grounding, capture the `initial` prompt the route hands to `ask_agentic` — mirror the route-test patch pattern and force the explain-data branch:

```python
def test_agent_grounding_names_run_sql_targets(user_client):
    captured = {}

    def _fake_agentic(initial, *, registry, agent_step):
        captured["initial"] = initial
        return SimpleNamespace(
            answer="ok", stopped_reason="final", tool_trace=[],
            turns=1, tokens_in=1, tokens_out=1,
        )

    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="SOURCE docprocessing ..."),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.make_agent_step", return_value=lambda m: None),
        patch("nx_lib.views.reporting.ask_agentic", side_effect=_fake_agentic),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    assert "statistics" in captured["initial"] and "octopus" in captured["initial"]
    assert "target" in captured["initial"]
```

(Add `from types import SimpleNamespace` to the imports. If the agent route in this file already has a stub-result helper, reuse it instead of `SimpleNamespace` — match the existing agent-route test if one exists. The route path is the one the existing agent tests use; confirm with `grep -n "ai/agent" tests/integration/test_reporting_ai_routes.py` and reuse it verbatim.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v -k "unknown_target or names_run_sql"`
Expected: `test_run_sql_unknown_target_error_lists_allowed_targets` FAILS (message is bare `unknown SQL target`); `test_agent_grounding_names_run_sql_targets` FAILS (`statistics`/`octopus` not in grounding).

- [ ] **Step 3: Fix the error message**

In `nx_lib/views/reporting.py` replace (lines 549–550):

```python
    if target not in _SQL_TARGETS:
        raise ReportDefinitionError("unknown SQL target")
```

with:

```python
    if target not in _SQL_TARGETS:
        raise ReportDefinitionError(
            f"unknown SQL target {target!r} — allowed targets: "
            + ", ".join(sorted(_SQL_TARGETS))
        )
```

- [ ] **Step 4: Name the targets in the grounding**

In `nx_lib/views/reporting.py`, the grounding currently reads (lines 1446–1447):

```python
    if has_sql or explain:
        grounding += f"\n\nSQL schema (for validate_sql / run_sql):\n{_ai_schema_text()}"
```

Replace with:

```python
    if has_sql or explain:
        grounding += f"\n\nSQL schema (for validate_sql / run_sql):\n{_ai_schema_text()}"
        grounding += (
            '\nrun_sql "target" argument MUST be one of: '
            + ", ".join(sorted(_SQL_TARGETS))
            + ". Any other value is rejected."
        )
```

- [ ] **Step 5: Run the integration suite**

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v`
Expected: all PASS (the new two plus the pre-existing route tests).

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
git commit -m "fix(reporting): agent grounding and run_sql error name the valid SQL targets"
```

---

### Task 8: Metric-less sources marked "cannot aggregate"

The grounding renders a `metrics:` line only for sources that have registered metrics; metric-less sources show nothing, so the model invents codes there. Make the absence explicit and add the matching prompt rule.

**Files:**
- Modify: `nx_lib/reporting/ai_schema.py` — `serialize_sources_catalog` (lines 88–141)
- Modify: `nx_lib/reporting/ai.py` — `_SYSTEM_DEF` metrics sentence (line 216–217)
- Test: `tests/unit/test_reporting_ai_schema.py` (exists — append), `tests/unit/test_reporting_ai_definition.py`

`serialize_sources_catalog(sources, *, char_budget=DEFAULT_CHAR_BUDGET)` takes a list of `{id, label, fields: […], processes: […], metrics: […]}` dicts and returns a **`(text, truncated_bool)` tuple** (`nx_lib/reporting/ai_schema.py:88-141`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_ai_schema.py` (it already imports `serialize_sources_catalog`; if not, add the import):

```python
def test_metricless_source_is_marked_no_aggregation():
    sources = [
        {
            "id": "workitems",
            "label": "Workitems (Octo)",
            "fields": [
                {"field": "wid", "label": "Workitem ID", "type": "string",
                 "filterable": True, "sortable": True}
            ],
            "processes": [],
            "metrics": [],
        }
    ]
    text, truncated = serialize_sources_catalog(sources)
    assert truncated is False
    assert "metrics: none" in text
    assert "cannot aggregate" in text


def test_source_with_metrics_keeps_its_metrics_line():
    sources = [
        {
            "id": "docprocessing",
            "label": "Document Processing",
            "fields": [
                {"field": "workitem_id", "label": "Workitem ID", "type": "string",
                 "filterable": True, "sortable": True}
            ],
            "processes": [],
            "metrics": [
                {"code": "workitem_count", "label": "Workitem count (distinct)",
                 "aggregation": "count_distinct", "base_field": "workitem_id"}
            ],
        }
    ]
    text, _ = serialize_sources_catalog(sources)
    assert "workitem_count" in text
    assert "metrics: none" not in text
```

Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_requires_metrics_source_for_counting():
    s = ai._SYSTEM_DEF
    assert "metrics: none" in s
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_schema.py tests\unit\test_reporting_ai_definition.py::test_system_def_requires_metrics_source_for_counting -v`
Expected: FAIL.

- [ ] **Step 3: Mark metric-less sources in the serializer**

In `nx_lib/reporting/ai_schema.py` `serialize_sources_catalog`, the metrics branch currently reads (lines 127–134):

```python
        mets = s.get("metrics") or []
        if mets:
            parts = []
            for m in mets:
                col = m.get("base_field") or "*"
                label = f' "{m.get("label")}"' if m.get("label") else ""
                parts.append(f"{m.get('code')}{label} = {m.get('aggregation')}({col})")
            lines.append(f"  metrics: {'; '.join(parts)}")
```

Add an `else` branch:

```python
        mets = s.get("metrics") or []
        if mets:
            parts = []
            for m in mets:
                col = m.get("base_field") or "*"
                label = f' "{m.get("label")}"' if m.get("label") else ""
                parts.append(f"{m.get('code')}{label} = {m.get('aggregation')}({col})")
            lines.append(f"  metrics: {'; '.join(parts)}")
        else:
            lines.append(
                "  metrics: none — this source cannot aggregate; for"
                " counting/summing questions pick a source that lists metrics"
            )
```

Also update the docstring line `A source's canonical metrics render as one … line.` to mention the explicit `metrics: none` marker for metric-less sources.

- [ ] **Step 4: Add the prompt rule**

In `nx_lib/reporting/ai.py` `_SYSTEM_DEF`, the metrics sentence ends with `"Only metric codes from the source's metrics line are valid."` (lines 216–217). Append directly after it:

```python
    ' A source marked "metrics: none" cannot aggregate at all — for any'
    " counting/summing/averaging question prefer a source that lists metrics"
    " instead of inventing a code."
```

- [ ] **Step 5: Run the suites**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_schema.py tests\unit\test_reporting_ai_definition.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/ai_schema.py nx_lib/reporting/ai.py tests/unit/test_reporting_ai_schema.py tests/unit/test_reporting_ai_definition.py
git commit -m "fix(reporting): grounding marks metric-less sources as cannot-aggregate"
```

---

### Task 9: Error message shows the gate reason, not the model's explanation

`askAi()` builds the failure line as `aiInvalid + ' (' + why + ')'` with `why = explanation || error` — so the user sees the model happily describing the report it failed to draft. Prefer the gate error.

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (line 916)

- [ ] **Step 1: Flip the precedence**

Replace (line 916):

```javascript
      var why = (res.data && (res.data.explanation || res.data.error)) || '';
```

with:

```javascript
      var why = (res.data && (res.data.error || res.data.explanation)) || '';
```

- [ ] **Step 2: Verify no other call site composes the invalid message**

Run: `Grep pattern "aiInvalid" in templates/js/_reporting_simple_js.html`
Expected: exactly the I18N definition (line 41) and the two render sites (lines 922, 925) — both feed off the same `why`.

- [ ] **Step 3: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add templates/js/_reporting_simple_js.html
git commit -m "fix(reporting): AI failure line surfaces the gate error before the model explanation"
```

---

### Task 10: i18n for the two new strings

New msgids from Task 3: `This quarter`, `Last quarter` (used in both JS partials via `{{ _("…") }}`).

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

- [ ] **Step 1: Extract + update**

```powershell
.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

- [ ] **Step 2: Translate**

In each `translations/<lang>/LC_MESSAGES/messages.po`, fill the two new (or fuzzy) entries — and **remove any `#, fuzzy` flag** pybabel added to them:

| msgid | de | fr | it |
|---|---|---|---|
| `This quarter` | `Dieses Quartal` | `Ce trimestre` | `Questo trimestre` |
| `Last quarter` | `Letztes Quartal` | `Trimestre dernier` | `Trimestre scorso` |

- [ ] **Step 3: Compile + verify**

```powershell
.venv\Scripts\pybabel.exe compile -d translations
.venv\Scripts\python.exe -m pytest tests\unit\test_translations.py -v
```

Expected: PASS (`test_pot_is_in_sync` and the per-locale completeness checks).

- [ ] **Step 4: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add messages.pot translations
git commit -m "feat(reporting): i18n for quarter token labels (de/fr/it)"
```

---

### Task 11: Docs + changelog (and fix the stale vocabulary claims)

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`

- [ ] **Step 1: Find every vocabulary enumeration**

Run: `Grep pattern "last_3_months" in docs/ (output_mode files_with_matches)`
Expected hits include `docs/howto/reporting.md` and `docs/design/reporting-ai-assistant.md`. In **each** hit, extend the token list with `this_quarter`, `last_quarter` (insert after `last_month`, mirroring the order in `RELATIVE_DATE_TOKENS`).

- [ ] **Step 2: CHANGELOG entries**

Under `[Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- Reporting: `this_quarter` / `last_quarter` relative-date tokens — in the AI prompts, the Simple wizard ("Last quarter" preset), the Advanced filter presets, and the chip editor.

### Fixed
- Reporting AI: prompts now require a date `grain` for per-month/week/quarter/year questions (drafts no longer bucket by raw day while claiming "monthly").
- Reporting AI: "how many distinct X per Y" no longer groups by the counted field (prompt rule + a gate guard that drops the shadowing column).
- Reporting AI agent: the grounding and the `run_sql` error now name the valid SQL targets, so the agent can self-repair instead of dying at the turn cap.
- Reporting AI: sources without registered metrics are marked "cannot aggregate" in the grounding; failure messages surface the gate error instead of the model's explanation.
```

- [ ] **Step 3: Behavior notes in the design doc**

In `docs/design/reporting-ai-assistant.md`, where Surface A validation is described, add one paragraph: the gate now (a) drops grouping columns that shadow a `count_distinct` metric's base field (mutating repair, same contract as `coerce_definition`), and (b) `/api/reporting/ai/build` errors surface the validator message verbatim in the Simple tab.

- [ ] **Step 4: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add CHANGELOG.md docs/howto/reporting.md docs/design/reporting-ai-assistant.md
git commit -m "docs(reporting): quarter tokens, grain rule, distinct guard, agent targets"
```

---

### Task 12: Consolidate the count metrics (disable `workitem_count`)

Owner verified on PROD (2026-06-11): `COUNT(*)`, `COUNT(WorkitemID)`, `COUNT(DISTINCT WorkItemID)`, `COUNT(Barcode)` are identical on the docprocessing Statistics tables. Two metrics that can never differ just clutter the wizard and give the AI a second code to misuse — keep `doc_count` as the single count metric. **Disable, don't delete**: reversible, and the `workitem_id` dimension field (column/filter) stays available.

No app code changes: the wizard (`/api/reporting/metrics`), the AI grounding (`_accessible_metrics`), and the gate (`_metrics_for_source`) are all driven by `WHERE Enabled = 1` in `_load_db_metrics` (`nx_lib/views/reporting.py:177-211`). The `count_distinct` machinery and Task 5/6's guard stay — they are registry-generic and covered by fixture-based unit tests (`tests/unit/test_reporting_query.py:457-466`, `tests/unit/test_reporting_runner.py:49-141`), which do not depend on the DB flag.

**Files:**
- Create: `sql/_migrations/NexoraDB/0021_disable_workitem_count_metric.sql`
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`

- [ ] **Step 1: Create the migration**

`sql/_migrations/NexoraDB/0021_disable_workitem_count_metric.sql`:

```sql
-- 0021: consolidate count metrics - disable workitem_count.
-- Owner verified 2026-06-11 on PROD: COUNT(*), COUNT(WorkitemID),
-- COUNT(DISTINCT WorkItemID) and COUNT(Barcode) all return the same number
-- on the docprocessing Statistics tables (one row per workitem, no NULL ids),
-- so this metric always equals doc_count. Disabled rather than deleted:
-- reversible, and the workitem_id dimension field stays available.
UPDATE dbo.ReportingMetrics SET Enabled = 0 WHERE Code = 'workitem_count';
GO
```

(Idempotent — re-running is a no-op, so the pre-commit auto-apply can safely re-run it.)

- [ ] **Step 2: Docs + changelog**

In `CHANGELOG.md` under `[Unreleased]`:

```markdown
### Changed
- Reporting: `workitem_count` metric disabled (migration `0021`) — verified on PROD that the Statistics tables hold one row per workitem, so it always equaled `doc_count`. `workitem_id` remains available as a column/filter; re-enable the metric row if a multi-row-per-workitem source ever appears.
```

In `docs/howto/reporting.md`, find the metric examples (grep `workitem_count`) and update them to reflect the single `doc_count` metric (mention the disabled row + the rationale in one sentence).

- [ ] **Step 3: Commit — let the hook apply the migration to INT**

Commit **without** `SQL_SYNC_SKIP` so the `sql-migrate-int` hook auto-applies `0021` to INT:

```powershell
git add sql/_migrations/NexoraDB/0021_disable_workitem_count_metric.sql CHANGELOG.md docs/howto/reporting.md
git commit -m "feat(reporting): consolidate count metrics - disable workitem_count (0021)"
```

If the hook fails on the historical CRLF-checksum drift (memory `project_int_migration_crlf_drift`), apply manually then commit with the skip:

```powershell
python scripts\db-migrate.py --env INT
$env:SQL_SYNC_SKIP='1'; git commit -m "feat(reporting): consolidate count metrics - disable workitem_count (0021)"
```

- [ ] **Step 4: Verify on INT**

```powershell
# Flag really flipped:
# (any SQL client / python one-liner against NexoraDB)
# SELECT Code, Enabled FROM dbo.ReportingMetrics ORDER BY Code;
# Expected: doc_count = 1, workitem_count = 0
```

Then restart the dev server (`& bin\nx.ps1 -d; & bin\nx.ps1 -u`) and confirm in the browser: the Simple wizard's "What do you want to measure?" step shows **only** "Document count"; the Advanced builder's metric dropdown likewise.

- [ ] **Step 5: Run the metric-adjacent suites (nothing may depend on the flag)**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_query.py tests\unit\test_reporting_runner.py tests\unit\test_reporting_semantic.py tests\integration\test_reporting_ai_routes.py -q
```

Expected: all green (these test the count_distinct *mechanism* via fixture registries, not the DB row).

**PROD note:** the deploy workflow auto-applies `0021` before the app pool restart — no manual PROD step.

---

### Task 13: Time questions default to the processing dates, never Document Date

Owner-reported: asking about *"April 2026"* produced a filter on **Document Date** (`DokDatum` — the date printed on the document) instead of a processing date. The prompts already teach grain and tokens but never say WHICH date field a time-period question should filter on. The catalog grounding already flags exactly the right fields: only the synthetic `export_date`/`import_date` carry the `(grainable)` flag (`_DATE_FIELD_COL`, `nx_lib/reporting/query.py:33`), so the rule can anchor on it.

**Files:**
- Modify: `nx_lib/reporting/ai.py` — `_SYSTEM_DEF` (append after the token paragraph that Task 2 edited), `_AGENT_SYSTEM` (append after the grain sentence that Task 4 added)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_defaults_time_filters_to_processing_dates():
    s = ai._SYSTEM_DEF
    assert "export_date" in s and "import_date" in s
    assert "printed on the document" in s  # the Document Date counter-example
    assert "processing-date" in s
```

Append to `tests/unit/test_reporting_ai_agentic.py`:

```python
def test_agent_system_prompt_defaults_time_filters_to_processing_dates():
    assert "processing-date" in _AGENT_SYSTEM
    assert "Document Date" in _AGENT_SYSTEM
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py::test_system_def_defaults_time_filters_to_processing_dates tests\unit\test_reporting_ai_agentic.py::test_agent_system_prompt_defaults_time_filters_to_processing_dates -v`
Expected: both FAIL (`processing-date` not found).

- [ ] **Step 3: Extend `_SYSTEM_DEF`**

In `nx_lib/reporting/ai.py`, directly after the relative-token paragraph's closing sentence (`…keep literal ISO dates.` — Task 2's edited text), append:

```python
    " When a question constrains a TIME PERIOD without naming a specific date"
    " field, put the filter on a (grainable) processing-date field — default"
    " to the export date (export_date); use the import date (import_date)"
    " when the question says imported/received/arrived. Content dates such as"
    ' "Document Date" (the date printed on the document) are correct ONLY'
    " when the user names that field explicitly."
```

- [ ] **Step 4: Extend `_AGENT_SYSTEM`**

In `nx_lib/reporting/ai.py`, directly after the grain sentence Task 4 added to `_AGENT_SYSTEM`, append:

```python
    " Time-period filters go on a (grainable) processing-date field — export"
    " date by default, import date when the question says imported/received —"
    " never on content dates like Document Date unless the user names that"
    " field."
```

- [ ] **Step 5: Run the suites**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py
git commit -m "fix(reporting): AI time filters default to export/import date, not Document Date"
```

---

### Task 14: Tweak any Simple result — refine bar + editable chips everywhere

Today the refine bar and the editable filter/process chips render only for AI-built results: one boolean gates both — `var aiBuilt = cur.aiExplanation !== undefined;` (`templates/js/_reporting_simple_js.html:409` in `renderAiChips`, `:486` in `runCurrent`). Wizard-built (`:860`) and library-opened (`:161`) results never set `aiExplanation`, so they are dead ends. Chips are purely definition-driven and the refine API already accepts a prior definition — only the prompt builder insists on having a prior *question* too (`nx_lib/reporting/ai.py:289` `if prior_question and prior_definition:`). `api_ai_build` already validates `priorQuestion` and `priorDefinition` independently (`nx_lib/views/reporting.py:1226-1240`) — no route change needed.

**Files:**
- Modify: `nx_lib/reporting/ai.py` — `_definition_user_prompt` (273–305)
- Modify: `templates/js/_reporting_simple_js.html` — `renderAiChips` (405–411), `runCurrent` (484–488), refine payload (892–893)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/integration/test_reporting_ai_routes.py`, `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing unit test**

Append to `tests/unit/test_reporting_ai_definition.py` (reuse the file's `_transport`/`_anthropic_body` stubs and the captured-body pattern of `test_ask_definition_includes_today_in_prompt`, lines 129–147):

```python
def test_ask_definition_accepts_prior_definition_without_question():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["body"] = body
        return _anthropic_body(
            {"definition": {"schemaVersion": 1, "visualization": "table",
                            "source": "docprocessing", "title": "T", "columns": [],
                            "filters": [], "sort": [],
                            "scope": {"clients": [], "processes": []},
                            "rowLimit": 5000},
             "explanation": "x"}
        )

    ai.ask_definition(
        "add a breakdown by process",
        "SOURCE docprocessing ...",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=transport,
        prior_definition={"schemaVersion": 1, "source": "docprocessing",
                          "columns": [], "filters": []},
    )
    user_msg = json.dumps(captured["body"])
    assert "built from this definition" in user_msg
    assert "previously asked" not in user_msg
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py::test_ask_definition_accepts_prior_definition_without_question -v`
Expected: FAIL — without `prior_question` the current code skips the prior-context block entirely, so `built from this definition` is absent.

- [ ] **Step 3: Relax `_definition_user_prompt`**

In `nx_lib/reporting/ai.py`, replace (lines 289–294):

```python
    if prior_question and prior_definition:
        compact = json.dumps(prior_definition, separators=(",", ":"))
        base += (
            f'The user previously asked: "{prior_question}". You answered with this definition: {compact}\n'
            "Modify the previous definition to satisfy the new request; keep everything the user did not ask to change.\n\n"
        )
```

with:

```python
    if prior_definition:
        compact = json.dumps(prior_definition, separators=(",", ":"))
        if prior_question:
            base += (
                f'The user previously asked: "{prior_question}". You answered with this definition: {compact}\n'
            )
        else:
            base += (
                f"The user is viewing a report built from this definition: {compact}\n"
            )
        base += (
            "Modify the previous definition to satisfy the new request; keep everything the user did not ask to change.\n\n"
        )
```

- [ ] **Step 4: Run the unit suite**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py -v`
Expected: all PASS (the existing both-fields refine tests keep their wording).

- [ ] **Step 5: Un-gate the chips and the refine bar in the JS**

In `templates/js/_reporting_simple_js.html`:

(a) `renderAiChips` — replace (lines 409–411):

```javascript
    var aiBuilt = cur.aiExplanation !== undefined;
    wrap.hidden = !aiBuilt;
    if (!aiBuilt) return;
```

with:

```javascript
    // Chips are definition-driven — every Simple result (AI, wizard, library)
    // gets them; edits mutate the in-memory copy only (Save creates a new row).
    var hasDef = !!(cur && cur.def);
    wrap.hidden = !hasDef;
    if (!hasDef) return;
```

(b) `runCurrent` — replace (lines 484–488):

```javascript
    var refineBar = el('rsRefineBar');
    if (refineBar) {
      var aiBuilt = cur.aiExplanation !== undefined;
      refineBar.hidden = !aiBuilt;
      if (aiBuilt) el('rsRefineInput').value = cur.aiQuestion || '';
    }
```

with:

```javascript
    var refineBar = el('rsRefineBar');
    if (refineBar) {
      refineBar.hidden = false;
      el('rsRefineInput').value = cur.aiQuestion || '';
    }
```

(c) Refine payload — replace (lines 892–893):

```javascript
    if (fromRefine && prior && prior.aiQuestion && prior.def) {
      payload.priorQuestion = prior.aiQuestion;
```

with (keep the following `payload.priorDefinition = …` line as-is):

```javascript
    if (fromRefine && prior && prior.def) {
      if (prior.aiQuestion) payload.priorQuestion = prior.aiQuestion;
```

(After a successful refine the result becomes AI-built — `aiExplanation`/`aiQuestion` get set by the existing assignment at lines 929–932; nothing more to wire.)

- [ ] **Step 6: Write the failing integration test**

Append to `tests/integration/test_reporting_ai_routes.py` (same patch set as `test_ai_build_does_not_require_sql_permission`, lines 187–220):

```python
def test_ai_build_accepts_prior_definition_without_question(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="SOURCE gen_pdqm ..."),
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=_def_result()) as draft,
        patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None)),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post(
            "/api/reporting/ai/build",
            json={
                "question": "add a breakdown by process",
                "priorDefinition": {"schemaVersion": 1, "source": "gen_pdqm",
                                    "columns": [], "filters": []},
            },
        )
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True
    assert draft.call_args.kwargs.get("prior_definition") is not None
    assert draft.call_args.kwargs.get("prior_question") in (None, "")
```

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v -k without_question`
Expected: PASS already if the route forwards the kwargs unconditionally — if it only forwards them when BOTH are set, fix the forwarding in `api_ai_build` so each is passed independently.

- [ ] **Step 7: e2e — wizard result shows chips + refine bar**

In `tests/e2e/test_reporting_simple.py` there are two tests to crib from: the existing wizard-run e2e (drives measure → breakdown → time preset → `rs-wizard-run`) and `test_refine_sends_prior_context_and_replaces_result` (stubs the AI build endpoint and drives `rs-refine-input`/`rs-refine`). Add a test that runs the **wizard** arrange steps, then asserts the tweak affordances exist on the result:

```python
    # after the wizard result rendered:
    expect(page.get_by_test_id("rs-refine-input")).to_be_visible()
    chips = page.locator("#rsChips")
    expect(chips).to_be_visible()
    # the filter chip from the wizard's time preset is editable:
    chips.locator(".rs-chip").first.click()
    expect(page.get_by_test_id("rs-chip-apply")).to_be_visible()
```

Then (optional but preferred) extend it with the refine stub from `test_refine_sends_prior_context_and_replaces_result` and assert the stub received `priorDefinition` and **no** `priorQuestion`.

Run: `python scripts\test_db_reset.py` then `.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v -k "wizard and (chips or refine)"`
Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add nx_lib/reporting/ai.py templates/js/_reporting_simple_js.html tests/unit/test_reporting_ai_definition.py tests/integration/test_reporting_ai_routes.py tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): refine bar and editable chips on every Simple result"
```

---

### Task 15: "Adjust in wizard" — re-enter the walkthrough with your choices kept

`startWizard()` (`templates/js/_reporting_simple_js.html:649-659`) always resets `state.wiz` and hides steps 2/3. A wizard-built result should offer a way back into the walkthrough with the previous choices pre-selected. Note one quirk: the AI result assignment at line 930 also sets `fromWizard: true` (it means "ephemeral/unsaved" there), so the new button must NOT key off `fromWizard` — introduce an explicit `builtBy: 'wizard'` marker instead.

**Files:**
- Modify: `templates/_reporting_simple.html` — result actions block (lines 73–81)
- Modify: `templates/js/_reporting_simple_js.html` — `choiceBtn` (624–636), `renderMeasureStep` (661–685), `renderBreakdownStep` (687–746), `renderTimeStep` (754–805+), wizard-run result assignment (~860), `runCurrent`, new `reopenWizard()`
- Modify: `messages.pot` + 3× `.po/.mo` (one new string)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Add the button to the result actions**

In `templates/_reporting_simple.html`, before the `rsSave` button (line 76), add:

```html
        <button id="rsAdjustWizard" class="reporting-btn" hidden
                data-testid="rs-adjust-wizard">{{ _("Adjust in wizard") }}</button>
```

- [ ] **Step 2: Let `choiceBtn` render pre-selected**

Replace the head of `choiceBtn` (lines 624–629):

```javascript
  function choiceBtn(label, onpick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'reporting-simple-choice';
    b.setAttribute('aria-pressed', 'false');
    b.textContent = label;
```

with:

```javascript
  function choiceBtn(label, onpick, selected) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'reporting-simple-choice';
    if (selected) b.classList.add('is-selected');
    b.setAttribute('aria-pressed', selected ? 'true' : 'false');
    b.textContent = label;
```

- [ ] **Step 3: Make the step renderers honor existing `state.wiz`**

In `renderMeasureStep` (line 675), pass the selected flag:

```javascript
        list.appendChild(choiceBtn(label, function () {
          state.wiz.measure = m;
          state.wiz.source = src;   // picking a measure pins the source
          renderBreakdownStep();
        }, !!(state.wiz.measure && state.wiz.measure.code === m.code
              && state.wiz.source && state.wiz.source.id === src.id)));
```

In `renderBreakdownStep`:
- date buttons (line 701): third arg `!!(state.wiz.breakdown && state.wiz.breakdown.kind === 'date' && state.wiz.breakdown.field.field === f.field)`
- category buttons (line 711): third arg `!!(state.wiz.breakdown && state.wiz.breakdown.kind === 'category' && state.wiz.breakdown.field.field === f.field)`
- "just the total" (line 717): third arg `!!(state.wiz.breakdown && state.wiz.breakdown.kind === 'none')`
- grain wrap (line 693): replace `el('rsGrainWrap').hidden = true;` with `el('rsGrainWrap').hidden = !(state.wiz.breakdown && state.wiz.breakdown.kind === 'date');` (the grain `<select>` itself lives in the template, so its value survives re-render untouched)
- process checkboxes (lines 735 + 744): preserve a prior selection instead of resetting —

```javascript
      var prior = state.wiz.scopeProcs || [];
      // inside the loop (line 735):
        cb.checked = !prior.length || prior.indexOf(p) !== -1;
      // and replace the unconditional reset (line 744):
      if (!prior.length) state.wiz.scopeProcs = procs.slice();
```

In `renderTimeStep`:
- date-field select (lines 776–780): honor a kept choice —

```javascript
    if (state.wiz.dateField
        && dateFields.some(function (f) { return f.field === state.wiz.dateField; })) {
      sel.value = state.wiz.dateField;
    } else if (dateFields.some(function (f) { return f.field === 'import_date'; })) {
      sel.value = 'import_date';
    }
```

- preset buttons (the `[['this_month', …]].forEach` list): third arg `state.wiz.range === p[0] || (p[0] === 'custom' && Array.isArray(state.wiz.range))` (presets store the token name in `state.wiz.range`; Custom stores a `[start, end]` array — verify against the click handler right below and match its actual storage), and keep `el('rsTimeCustom').hidden = true;` (line 757) only when the kept range is not an array:

```javascript
    el('rsTimeCustom').hidden = !Array.isArray(state.wiz.range);
```

- [ ] **Step 4: `reopenWizard()` + the marker + wiring**

Add next to `startWizard`:

```javascript
  async function reopenWizard() {
    if (!state.wiz || !state.wiz.measure) { startWizard(); return; }
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    setView('wizard');
    renderMeasureStep();
    renderBreakdownStep();
    renderTimeStep();
  }
```

In the wizard-run result assignment (~line 860) add the marker:

```javascript
                      owned: true, canEdit: true, fromWizard: true,
                      builtBy: 'wizard' };
```

In `runCurrent`, next to the refine-bar block, toggle the button:

```javascript
    var adjustBtn = el('rsAdjustWizard');
    if (adjustBtn) adjustBtn.hidden = cur.builtBy !== 'wizard';
```

And bind the click once, next to the existing `rsOpenAdvanced` click binding (grep `rsOpenAdvanced` in this file's wiring section):

```javascript
    el('rsAdjustWizard').addEventListener('click', reopenWizard);
```

- [ ] **Step 5: i18n for the new string**

```powershell
.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

| msgid | de | fr | it |
|---|---|---|---|
| `Adjust in wizard` | `Im Assistenten anpassen` | `Ajuster dans l'assistant` | `Modifica nella procedura guidata` |

Remove any `#, fuzzy` flags, then:

```powershell
.venv\Scripts\pybabel.exe compile -d translations
.venv\Scripts\python.exe -m pytest tests\unit\test_translations.py -v
```

- [ ] **Step 6: e2e — round trip**

Append to `tests/e2e/test_reporting_simple.py` (crib the wizard arrange steps from the existing wizard e2e test):

```python
    # run the wizard once, then re-enter it:
    page.get_by_test_id("rs-adjust-wizard").click()
    expect(page.get_by_test_id("rs-wizard-run")).to_be_visible()
    # previous choices survive: the measure button is still pressed
    expect(page.locator(".reporting-simple-choice.is-selected").first).to_be_visible()
    # change the time preset, run again, result re-renders
    page.get_by_test_id("rs-wizard-run").click()
```

Run: `python scripts\test_db_reset.py` then `.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v -k adjust`
Expected: PASS.

- [ ] **Step 7: Changelog + docs**

`CHANGELOG.md` `[Unreleased]` → `### Added`:

```markdown
- Reporting Simple: every result is now tweakable — the AI refine bar and the editable filter/process chips show on wizard-built and library-opened reports too (refine works without a prior AI question), and wizard-built results get an "Adjust in wizard" button that re-opens the walkthrough with the previous choices pre-selected.
```

Update the Simple-tab section of `docs/howto/reporting.md` accordingly.

- [ ] **Step 8: Commit**

```powershell
$env:SQL_SYNC_SKIP='1'; git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html messages.pot translations tests/e2e/test_reporting_simple.py CHANGELOG.md docs/howto/reporting.md
git commit -m "feat(reporting): adjust-in-wizard re-entry with preserved choices"
```

---

### Task 16: Full verification — suites + live browser pass

**Files:** none (verification only)

- [ ] **Step 1: Full unit + integration run**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\ tests\integration\ -q
```

Expected: all green.

- [ ] **Step 2: e2e (reset test DB first — stale `NEXORA_TEST` state breaks order-dependent tests)**

```powershell
python scripts\test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py tests\e2e\test_reporting.py -v
```

Expected: all green.

- [ ] **Step 3: Live INT re-run of the failing stakeholder questions**

Restart the server first (Jinja templates cache for the process lifetime), then drive Playwright as `ben.streich`:

```powershell
& bin\nx.ps1 -d; & bin\nx.ps1 -u
# then in Playwright: http://127.0.0.1:8000/dev/login/ben.streich → /reporting?tab=simple
```

Re-ask, screenshot each to `var/screenshots/` (send to the user):
1. *"How many documents did we process per month this year?"* → table buckets must be month starts (`2026-02-01`), not raw days; chip `import/export_date between This year`.
2. *"How many documents did each process handle last quarter?"* → chip must read **Last quarter** (resolved `2026-01-01 → 2026-03-31`, NOT the `last_3_months` window); table = one row per process with `doc_count`.
3. *"How many distinct workitems did each process handle last quarter?"* → with `workitem_count` disabled (Task 12) there is no valid distinct metric on docprocessing anymore: expect either a doc_count draft (acceptable — counts are 1:1 on PROD) or a clean failure whose red line shows the **gate reason** (Task 9). What must NOT happen: an invented metric code or an all-1s table.
4. Advanced → Ask AI → Agent: *"Which process handled the most documents this year, and how many was it?"* → expect a concrete answer (audit `GateVerdict = 'final'`), or at minimum a `run_sql` step that no longer fails on `unknown SQL target`. Check with:
   `SELECT TOP 3 Surface, Status, GateVerdict, CreatedAt FROM dbo.ReportingAiAudit ORDER BY CreatedAt DESC`
5. Force an invalid draft (ask for a metric on the metric-less `workitems` source, e.g. *"average number of workitems per day in the workitems source"*) → the red line must show the **gate reason**, not the model explanation.
6. *"How many documents did we process in April 2026?"* → the filter chip must be on **export_date** (literal `2026-04-01 → 2026-04-30`), NOT on Document Date; rephrase with *"imported in April 2026"* → **import_date**.
7. Build a report via the **wizard**, then on the result: chips are visible and editable, the refine bar is visible — type *"only compass"* and Refine → the AI narrows the scope without a prior question (audit row Surface `definition`, verdict `valid`).
8. On the same wizard result click **Adjust in wizard** → the walkthrough re-opens with measure/breakdown/time still selected; change only the time preset, run, and the result updates.

- [ ] **Step 4: Update the usability-gaps memory + handoff**

Record the outcome (esp. whether the agent now reaches `final`) in memory `project_reporting_usability_gaps`, then run `/handoff-session-state` if the session is ending.

---

## Self-review notes

- **Spec coverage:** bug 1 → Tasks 1–3, 10, 11; bug 2 → Task 4; bug 3 → Tasks 5–6; bug 4 → Task 7; bug 5 → Tasks 8–9; metric consolidation (PROD parity finding) → Task 12; bug 6 (Document Date mispick) → Task 13; tweak-any-result + wizard re-entry (owner request 2026-06-11) → Tasks 14–15. Verification → Task 16.
- **Signatures verified against the live tree (2026-06-11):** `_def_result(source="gen_pdqm")` at `tests/integration/test_reporting_ai_routes.py:166` (Task 6 extends it backward-compatibly); `serialize_sources_catalog(sources, *, char_budget=…) -> (text, truncated)` at `nx_lib/reporting/ai_schema.py:88`; `_run_sql(target, sql, *, userid, username)` at `nx_lib/views/reporting.py:543` (the unknown-target branch raises before any engine/app-context use, so it is directly callable in tests); the agent route is `/api/reporting/ai/agent` and calls `ask_agentic(initial, registry=…, agent_step=…)` at line 1473; the agentic result exposes `answer, stopped_reason, tool_trace, turns, tokens_in, tokens_out` (see `tests/unit/test_reporting_ai_agentic.py` usage).
- **Type consistency:** `drop_columns_shadowing_distinct_metrics(rd, metric_registry)` consumes the exact `{code: {aggregation, base_field}}` shape `_metrics_for_source` returns (`nx_lib/views/reporting.py:214-220`); Tasks 6 unit + integration both use that shape.
- **Existing-test compatibility:** Task 5's replacement text deliberately keeps the literal phrases `GROUP BY` and `duplicate rows` asserted by the pre-existing prompt tests.
