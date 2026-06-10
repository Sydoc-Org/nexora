# Reporting AI Grounding Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the reporting Ask-AI surfaces answer questions like *"Show me the different docsources from last month from the process Privera Invoice"* correctly, and make wrong AI guesses visible to the user instead of silently rendering an empty/garbage table.

**Architecture:** Four small, independent fixes: (1) inject today's date into the Surface A and Surface C prompts so relative dates resolve correctly; (2) teach the prompts the distinct-values pattern (column + count metric = GROUP BY) and process-id matching rules; (3) humanize process ids in the catalog grounding so "Privera Invoice" can match `privera.03_Invoice_New`; (4) surface the AI's explanation and the filters it chose in the Simple-tab result view. No schema/DB changes; all backend changes live in `nx_lib/reporting/ai.py`, `nx_lib/reporting/ai_schema.py`, and `nx_lib/views/reporting.py`; the UX change lives in the Simple-tab JS partial.

**Tech Stack:** Flask, pytest (unit + integration, network-isolated via injected `transport`), Jinja2 JS partials, Flask-Babel for the new UI strings.

---

## Root cause (evidence)

Audit row `dbo.ReportingAiAudit` ID 23 (INT, 2026-06-10, prompt = the user's exact question, Surface = definition, GateVerdict = **valid**): the model produced a definition that *validated and ran*, but was wrong three ways:

| Symptom | Artifact value | Root cause | Evidence |
|---|---|---|---|
| "last month" → Sept **2023** | `import_date between 2023-09-01..2023-09-30` | No current date anywhere in `_SYSTEM_DEF`, `_definition_user_prompt`, `_AGENT_SYSTEM`, or the agent grounding; gpt-4o-mini falls back to training-data dates | `nx_lib/reporting/ai.py:195-222`, `252-263`, `385-396`; `nx_lib/views/reporting.py:1369-1381` |
| "different docsources" → duplicate rows | `columns=[docsource]`, no `metrics` | Columns-only definitions compile to a plain projection with no GROUP BY (`query.py:300-314`); the distinct workaround (column + count metric → GROUP BY, `query.py:290-298`) is never taught in the prompt | `nx_lib/reporting/query.py`, `nx_lib/reporting/ai.py:195-222` |
| "Privera Invoice" → `privera.02_InitialScan` | wrong process picked | Catalog emits raw ids only (`ai_schema.py:113`); no human labels exist anywhere in the system, so the model guesses | `nx_lib/reporting/ai_schema.py:111-113`, `nx_lib/reporting/catalog.py:196` |
| User saw nothing wrong, only "Open in Advanced" | — | Simple tab discards `explanation` on the valid path (`rsMsg` is set hidden and never filled), shows no filter summary; zero rows → bare "No data for this report" | `templates/js/_reporting_simple_js.html:245-304`, `634-657`; `templates/_reporting_simple.html:83` |

## Out of scope (follow-ups, not this plan)

- **Relative-date tokens in definitions** (`{"op": "last_month"}`-style): saved/scheduled reports with absolute dates go stale (`ops/run_scheduled_reports.py` re-runs the saved JSON verbatim). Bigger feature: schema + validator + query + wizard + scheduler. With date grounding, ad-hoc AI asks emit correct absolutes at ask-time, which fixes this user journey.
- **DB-backed process display labels** (new table + admin UI). Task 4's derived labels are code-only and good enough for NL matching.
- **Conversational refine UX** (edit/retry the AI question from the result view).
- **e2e AI stub** (no automated e2e covers the ask-AI path; Task 5 is verified live on INT where Azure AI is enabled).

## Repo conventions that apply to every task

- Run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` before editing each named function, and `gitnexus_detect_changes()` before each commit (project CLAUDE.md rules).
- The `sql-migrate-int` pre-commit hook currently always fails on Windows (INT CRLF checksum drift). Commit with `SQL_SYNC_SKIP=1 git commit ...`.
- Test runner: `.venv\Scripts\python.exe -m pytest <path> -v` from `C:\dev\nexora`.
- Jinja templates are cached for the process lifetime — restart the dev server after template edits before browser-verifying.

---

### Task 1: Today's date in Surface A (definition drafting)

**Files:**
- Modify: `nx_lib/reporting/ai.py:252-263` (`_definition_user_prompt`), `nx_lib/reporting/ai.py:266-316` (`ask_definition`)
- Modify: `nx_lib/views/reporting.py:1179-1190` (call site in `api_ai_build`)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/unit/test_reporting_ai_definition.py` (the `_transport` / `_anthropic_body` helpers already exist at the top of the file):

```python
def test_ask_definition_includes_today_in_prompt():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "docs last month",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        today="2026-06-10",
        transport=transport,
    )
    assert "Today's date is 2026-06-10" in captured["user"]
    # The date line precedes the catalog so the model reads it first.
    assert captured["user"].index("Today's date") < captured["user"].index("CATALOG")


def test_ask_definition_omits_date_line_without_today():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=transport,
    )
    assert "Today's date" not in captured["user"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py -v -k today`
Expected: FAIL — `TypeError: ask_definition() got an unexpected keyword argument 'today'` for the first test (the second passes trivially; that's fine — it pins current behavior).

- [ ] **Step 3: Implement the date line in `ai.py`**

Replace `_definition_user_prompt` (ai.py:252-263) with:

```python
def _definition_user_prompt(question, catalog_text, prior_error, today=None):
    base = ""
    if today:
        base += (
            f"Today's date is {today}. Resolve relative time expressions "
            '("last month", "this year", "yesterday") against this date, '
            "never against your training data.\n\n"
        )
    base += (
        f"Available sources and fields:\n{catalog_text}\n\n"
        f"Question: {question}\n\n"
        'Return STRICT JSON {"definition": {...}, "explanation": ...}.'
    )
    if prior_error:
        base += (
            f"\n\nYour previous attempt was REJECTED by the validator with: "
            f"{prior_error}\nFix it and return corrected STRICT JSON."
        )
    return base
```

In `ask_definition`, add the keyword-only parameter and thread it through. The signature block (ai.py:266-281) becomes:

```python
def ask_definition(
    question,
    catalog_text,
    *,
    provider,
    model,
    api_key,
    endpoint=None,
    deployment=None,
    api_version="2024-10-21",
    url=None,
    prior_error=None,
    today=None,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
```

and the `_dispatch` call inside it changes its second argument from
`_definition_user_prompt(question, catalog_text, prior_error)` to
`_definition_user_prompt(question, catalog_text, prior_error, today)`.

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py -v`
Expected: ALL PASS (including the pre-existing tests — `today` defaults to `None`, so untouched callers see no date line).

- [ ] **Step 5: Write the failing integration test for the route call site**

Append to `tests/integration/test_reporting_ai_routes.py` (the file already imports `patch`; add `import datetime` and `from nx_lib.reporting.ai import AiDefinitionResult` to its imports if not present):

```python
def test_ai_build_passes_today_to_drafter(user_client):
    stub = AiDefinitionResult(
        definition=None, explanation="", model="m", provider="anthropic",
        tokens_in=1, tokens_out=1,
    )
    with (
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="CATALOG"),
        patch(
            "nx_lib.views.reporting._validate_definition_for_user",
            return_value=(False, "no def"),
        ),
        patch("nx_lib.views.reporting._audit_ai"),
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=stub) as drafter,
    ):
        resp = user_client.post(
            "/api/reporting/ai/build", json={"question": "docs last month"}
        )
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["today"] == datetime.date.today().isoformat()
```

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v -k passes_today`
Expected: FAIL — `KeyError: 'today'` (the route does not pass it yet).

- [ ] **Step 6: Pass `today` at the call site**

In `nx_lib/views/reporting.py` `api_ai_build` (the `ai_ask_definition(...)` call at ~line 1179), add one keyword argument after `prior_error=prior_error`:

```python
                prior_error=prior_error,
                today=datetime.date.today().isoformat(),
```

(`import datetime` already exists at `nx_lib/views/reporting.py:24` — no new import.)

- [ ] **Step 7: Run both test files to verify everything passes**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\integration\test_reporting_ai_routes.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add nx_lib/reporting/ai.py nx_lib/views/reporting.py tests/unit/test_reporting_ai_definition.py tests/integration/test_reporting_ai_routes.py
SQL_SYNC_SKIP=1 git commit -m "fix(reporting): ground AI definition drafting in today's date"
```

---

### Task 2: Today's date in Surface C (agent loop)

**Files:**
- Modify: `nx_lib/views/reporting.py:1369` (grounding in `api_ai_agent`)
- Modify: `nx_lib/reporting/ai.py:385-396` (`_AGENT_SYSTEM`)
- Test: `tests/integration/test_reporting_ai_routes.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/integration/test_reporting_ai_routes.py` (reuses the existing `_agent_patches()` / `_agentic_result()` helpers visible around line 390; `ExitStack` is already imported there):

```python
def test_ai_agent_grounding_states_todays_date(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        loop = es.enter_context(
            patch("nx_lib.views.reporting.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting._validate_definition_for_user",
                return_value=(True, None),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        user_client.post("/api/reporting/ai/agent", json={"question": "docs last month"})
    initial = loop.call_args.args[0]
    assert initial.startswith(f"Today's date is {datetime.date.today().isoformat()}")
```

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v -k todays_date`
Expected: FAIL — `initial` starts with `"Available report sources and fields:"`.

- [ ] **Step 2: Prepend the date to the agent grounding**

In `nx_lib/views/reporting.py` `api_ai_agent`, replace line 1369:

```python
    grounding = f"Available report sources and fields:\n{_ai_catalog_text()}"
```

with:

```python
    grounding = (
        f"Today's date is {datetime.date.today().isoformat()}.\n\n"
        f"Available report sources and fields:\n{_ai_catalog_text()}"
    )
```

- [ ] **Step 3: Write the failing prompt-content unit test**

Append to `tests/unit/test_reporting_ai_agentic.py` (it already imports the `ai` module; mirror the existing `test_agent_system_prompt_*` assertions style):

```python
def test_agent_system_prompt_grounds_relative_dates():
    assert "today's date" in ai._AGENT_SYSTEM.lower()
```

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_agentic.py -v -k relative_dates`
Expected: FAIL

- [ ] **Step 4: Extend `_AGENT_SYSTEM`**

In `nx_lib/reporting/ai.py`, append one sentence to the `_AGENT_SYSTEM` string (after "Do not ask the user questions."):

```python
    " The grounding states today's date; resolve relative time expressions"
    ' ("last month", "this year") against it, never against your training data.'
```

- [ ] **Step 5: Run both test files to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_agentic.py tests\integration\test_reporting_ai_routes.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add nx_lib/reporting/ai.py nx_lib/views/reporting.py tests/unit/test_reporting_ai_agentic.py tests/integration/test_reporting_ai_routes.py
SQL_SYNC_SKIP=1 git commit -m "fix(reporting): ground agent surface in today's date"
```

---

### Task 3: Distinct-values and process-matching guidance in the prompts

**Files:**
- Modify: `nx_lib/reporting/ai.py:195-222` (`_SYSTEM_DEF`), `nx_lib/reporting/ai.py:385-396` (`_AGENT_SYSTEM`)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing prompt-content tests**

Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_teaches_distinct_via_metrics():
    s = ai._SYSTEM_DEF
    assert "distinct" in s.lower()
    assert "GROUP BY" in s
    assert "duplicate rows" in s


def test_system_def_teaches_process_matching():
    s = ai._SYSTEM_DEF
    assert "scope.processes" in s
    assert "include ALL of them" in s
```

Append to `tests/unit/test_reporting_ai_agentic.py`:

```python
def test_agent_system_prompt_teaches_distinct_and_processes():
    s = ai._AGENT_SYSTEM
    assert "distinct" in s.lower()
    assert "GROUP BY" in s
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v -k "distinct or process_matching"`
Expected: FAIL (×3)

- [ ] **Step 3: Extend `_SYSTEM_DEF`**

In `nx_lib/reporting/ai.py`, append to the `_SYSTEM_DEF` string (after the existing `chartHint` sentence, keeping the implicit-concatenation style):

```python
    " When the question asks for the DISTINCT/different/unique values of a"
    ' field, put that field in "columns" AND add a count metric in "metrics" —'
    " with metrics present the selected columns become GROUP BY dimensions, so"
    " each value appears once (with its count). Never answer a distinct-values"
    " question with bare columns and no metrics: that returns duplicate rows."
    ' Process ids in "allowed scope.processes" follow <client>.<NN_Name>; a'
    " humanized label is shown in parentheses next to each id. Match the"
    " user's process words case-insensitively against the whole id and its"
    ' label (e.g. "Privera Invoice" matches privera.03_Invoice_New). If'
    " several ids match, include ALL of them in scope.processes; if none"
    " clearly match, leave scope.processes empty (= all allowed) rather than"
    " guessing one."
```

- [ ] **Step 4: Extend `_AGENT_SYSTEM`**

Append to the `_AGENT_SYSTEM` string (after the Task 2 date sentence):

```python
    " For distinct/unique-values questions, build a definition with that field"
    ' in "columns" plus a count metric — metrics make the columns GROUP BY'
    " dimensions. Match process words against whole process ids and their"
    " humanized labels; include all matches, or none rather than a guess."
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py
SQL_SYNC_SKIP=1 git commit -m "fix(reporting): teach AI prompts distinct-values and process matching"
```

---

### Task 4: Humanized process ids in the catalog grounding

**Files:**
- Modify: `nx_lib/reporting/ai_schema.py:111-113` (process line in `serialize_sources_catalog`) + new module-level helper
- Test: `tests/unit/test_reporting_ai_schema.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_reporting_ai_schema.py` (it already imports `serialize_sources_catalog`):

```python
def test_catalog_humanizes_process_ids():
    sources = [
        {
            "id": "docprocessing",
            "label": "Doc processing",
            "fields": [
                {
                    "field": "docsource",
                    "label": "Document Source",
                    "type": "string",
                    "filterable": True,
                }
            ],
            "processes": ["privera.03_Invoice_New", "compass.01_Invoice_SAP"],
        }
    ]
    text, truncated = serialize_sources_catalog(sources)
    assert 'privera.03_Invoice_New ("privera Invoice New")' in text
    assert 'compass.01_Invoice_SAP ("compass Invoice SAP")' in text
    assert truncated is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_schema.py -v -k humanizes`
Expected: FAIL — the line contains only raw ids.

- [ ] **Step 3: Implement the helper and rendering**

In `nx_lib/reporting/ai_schema.py`, add `import re` to the module imports if not already present, then add above `serialize_sources_catalog`:

```python
_PROC_NUM_PREFIX = re.compile(r"^\d+_")


def _humanize_process_id(pid):
    """'privera.03_Invoice_New' -> 'privera Invoice New', so the model can
    match natural-language process names against otherwise-opaque ids."""
    client, _, rest = str(pid).partition(".")
    rest = _PROC_NUM_PREFIX.sub("", rest).replace("_", " ").strip()
    return f"{client} {rest}".strip() if rest else str(pid)
```

Replace the process line (ai_schema.py:111-113):

```python
        procs = s.get("processes") or []
        if procs:
            parts = [f'{p} ("{_humanize_process_id(p)}")' for p in procs]
            lines.append(f"  allowed scope.processes: {', '.join(parts)}")
```

- [ ] **Step 4: Run the full ai_schema test file**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_schema.py -v`
Expected: ALL PASS. If a pre-existing test asserts the exact old `allowed scope.processes:` line, update its expected string to the new `id ("label")` form — the new form is the spec.

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai_schema.py tests/unit/test_reporting_ai_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): humanize process ids in AI catalog grounding"
```

---

### Task 5: Simple-tab transparency — show the AI's explanation and chosen filters

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (I18N block ~line 11-43, `runCurrent` ~line 245, `askAi` ~line 634)
- (No change to `templates/_reporting_simple.html` — the hidden `#rsMsg` element at line 83 already exists.)

There is no automated e2e for the AI path (no provider stub); this task is verified live on INT (Azure AI is enabled there) in Step 5.

- [ ] **Step 1: Add the new I18N strings**

In the `I18N` object in `templates/js/_reporting_simple_js.html` (after `aiLimit:` at line 42, adding a trailing comma to it):

```js
    aiLimit: {{ _("The AI daily limit is reached — try again tomorrow.")|tojson }},
    aiFilters: {{ _("Filters")|tojson }},
    aiProcesses: {{ _("Processes")|tojson }},
    aiNoFilters: {{ _("no filters")|tojson }}
```

- [ ] **Step 2: Stash the explanation on the AI path**

In `askAi()` (~line 654), extend the `state.current` assignment:

```js
    state.current = { def: res.data.definition, name: res.data.definition.title,
                      reportId: null, owned: true, canEdit: true, fromWizard: true,
                      aiExplanation: res.data.explanation || '' };
```

- [ ] **Step 3: Render the transparency line in `runCurrent()`**

Add this helper above `runCurrent` (~line 240):

```js
  // One-line transparency note under the title of AI-built reports: the
  // model's own explanation plus the filters/scope it chose, so a wrong guess
  // (bad date range, wrong process) is visible instead of silently rendering
  // an empty table.
  function aiSummaryLine(cur) {
    var def = cur.def || {};
    var bits = [];
    if (cur.aiExplanation) bits.push(cur.aiExplanation);
    var fs = (def.filters || []).map(function (f) {
      var v = Array.isArray(f.value) ? f.value.join(' → ')
            : (f.value === null || f.value === undefined ? '' : String(f.value));
      return f.field + ' ' + f.op + (v !== '' ? ' ' + v : '');
    });
    bits.push(I18N.aiFilters + ': ' + (fs.length ? fs.join(' · ') : I18N.aiNoFilters));
    var procs = (def.scope && def.scope.processes) || [];
    if (procs.length) bits.push(I18N.aiProcesses + ': ' + procs.join(', '));
    return bits.join(' — ');
  }
```

In `runCurrent()`, directly after `el('rsResultTitle').textContent = ...` (line 251), insert:

```js
    if (cur.aiExplanation !== undefined) {
      el('rsMsg').textContent = aiSummaryLine(cur);
      el('rsMsg').hidden = false;
    }
```

`textContent` (never `innerHTML`) keeps model-controlled text XSS-safe. Because the zero-row early-return at ~line 293 runs *after* this block, the filter summary stays visible exactly when the user most needs it — over an empty result.

- [ ] **Step 4: Restart the dev server (template cache) and verify in the browser**

```powershell
.\bin\nx.ps1 -u -b --loginas:ben.streich
```

In the Playwright browser: open `/reporting`, Simple tab, type the original question — *Show me the Different docsources from last month from the process Privera Invoice* — into the Ask-AI bar and submit. Verify:
- the result view shows the `rsMsg` line with the explanation, a `Filters: import_date between 2026-05-01 → 2026-05-31`-style chip (correct month now), and the chosen processes;
- the table lists each docsource once with a count column (distinct via GROUP BY), not duplicate rows.

Save a screenshot to `var/screenshots/2026-06-10-ai-distinct-docsources.png`. **If this is a remote session, send it via SendUserFile.** If the model still picks a wrong process despite Tasks 3-4, note it in the commit body — prompt-level matching is best-effort by design (see Out of scope).

- [ ] **Step 5: Run the e2e simple-tab suite to catch regressions**

```powershell
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v
```

Expected: ALL PASS (the new code only activates when `aiExplanation` is set, so wizard/library paths are untouched).

- [ ] **Step 6: Commit**

```bash
git add templates/js/_reporting_simple_js.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): show AI explanation and applied filters on Simple results"
```

---

### Task 6: i18n, changelog, docs

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`

- [ ] **Step 1: Run the Babel extract/update cycle** (or invoke the `/nx-i18n` skill, which does the same)

```powershell
.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

- [ ] **Step 2: Translate the three new msgids in each `.po`**

| msgid | de | fr | it |
|---|---|---|---|
| `Filters` | `Filter` | `Filtres` | `Filtri` |
| `Processes` | `Prozesse` | `Processus` | `Processi` |
| `no filters` | `keine Filter` | `aucun filtre` | `nessun filtro` |

(If `Filters`/`Processes` already exist as msgids from other pages, `pybabel update` reuses them — only fill in whatever is new or fuzzy, and remove the fuzzy markers.)

- [ ] **Step 3: Compile and verify translations are green**

```powershell
.venv\Scripts\pybabel.exe compile -d translations
.venv\Scripts\python.exe -m pytest tests -v -k translations
```

Expected: PASS (the suite enforces pot-sync and non-fuzzy de/fr/it coverage).

- [ ] **Step 4: Changelog**

Under `[Unreleased]` in `CHANGELOG.md`:

```markdown
### Fixed
- Reporting AI now knows today's date: relative ranges like "last month" resolve correctly on the build and agent surfaces instead of falling back to training-data dates.
- Reporting AI answers "distinct/different values" questions with a grouped definition (column + count metric) instead of duplicate raw rows.

### Added
- Reporting AI grounding shows a humanized label next to each process id (e.g. `privera.03_Invoice_New ("privera Invoice New")`) so natural-language process names match the right process.
- Simple tab shows the AI's explanation and the filters/processes it applied above AI-built results, so wrong guesses are visible instead of silently rendering an empty table.
```

- [ ] **Step 5: Docs**

- `docs/howto/reporting.md`: in the AI assistant section, document that prompts are grounded with the current date, the distinct-values pattern, and the humanized process labels; mention the Simple-tab transparency line.
- `docs/design/reporting-ai-assistant.md`: same three points in the Surface A/C grounding description (the "egress is schema-only" guarantee is unchanged — the date is not user data).

- [ ] **Step 6: Full verification run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit tests\integration -q
```

Expected: ALL PASS.

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md docs/design/reporting-ai-assistant.md
SQL_SYNC_SKIP=1 git commit -m "docs(reporting): i18n + docs for AI grounding fixes"
```
