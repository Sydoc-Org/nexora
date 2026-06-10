# Reporting AI Conversational Refine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the Simple tab, an AI-built result can be fixed in place: edit/retry the question with the prior definition as context (refine bar), correct the AI's filter/process choices directly (editable chips, no AI round trip), and see a thinking indicator while the model works.

**Architecture:** `ask_definition` gains `prior_question`/`prior_definition` prompt context; `api_ai_build` accepts the same as optional, size-capped JSON fields (no new endpoint — limit/audit/validation loop reused; the priors are prompt context only, never executed, so the existing validator remains the security boundary). The Simple pane gets a refine bar + chips row in the result view and a CSS pulsing-dots loading state driven by a shared `aiBusy` flag.

**Tech Stack:** Flask, pytest (unit + integration + Playwright e2e — the AI endpoint is stubbed in e2e via `page.route`), Jinja2 JS partials, Flask-Babel, CSS keyframes.

**Spec:** `docs/superpowers/specs/2026-06-10-reporting-ai-refine-design.md`

---

## Repo conventions that apply to every task

- Run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` before editing each named function, and `gitnexus_detect_changes()` before each commit (project CLAUDE.md rules).
- The `sql-migrate-int` pre-commit hook currently always fails on Windows (INT CRLF checksum drift). Commit with `SQL_SYNC_SKIP=1 git commit ...`.
- Test runner: `.venv\Scripts\python.exe -m pytest <path> -v` from `C:\dev\nexora`.
- Jinja templates are cached for the process lifetime — restart the dev server after template edits before browser-verifying.
- e2e prep: `python scripts/test_db_reset.py` before running e2e files.
- Independent of the relative-date-tokens plan; the chip code checks for a token-shaped value defensively so the two plans can land in either order.

---

### Task 1: Refine context in `ask_definition`

**Files:**
- Modify: `nx_lib/reporting/ai.py:264-282` (`_definition_user_prompt`), `:285-321` (`ask_definition`)
- Test: `tests/unit/test_reporting_ai_definition.py`

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/unit/test_reporting_ai_definition.py` (the `_transport`/`_anthropic_body` helpers exist at the top of the file):

```python
def test_ask_definition_includes_refine_context():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "only the Privera invoice process",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        prior_question="docs last month",
        prior_definition={"schemaVersion": 1, "title": "t"},
        transport=transport,
    )
    assert 'The user previously asked: "docs last month"' in captured["user"]
    # Compact JSON (no spaces) keeps the prompt small.
    assert '{"schemaVersion":1,"title":"t"}' in captured["user"]
    # The refine block precedes the catalog so the model reads it first.
    assert captured["user"].index("previously asked") < captured["user"].index("CATALOG")


def test_ask_definition_omits_refine_context_by_default():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q", "CATALOG", provider="anthropic", model="m", api_key="k",
        transport=transport,
    )
    assert "previously asked" not in captured["user"]


def test_ask_definition_refine_context_requires_both_priors():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q", "CATALOG", provider="anthropic", model="m", api_key="k",
        prior_question="docs last month",  # definition missing -> no refine block
        transport=transport,
    )
    assert "previously asked" not in captured["user"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py -v -k refine`
Expected: FAIL — `TypeError: ask_definition() got an unexpected keyword argument 'prior_question'` (×2; the omit-by-default test passes trivially, pinning current behavior).

- [ ] **Step 3: Implement**

In `nx_lib/reporting/ai.py`, replace `_definition_user_prompt` (lines 264-282) with:

```python
def _definition_user_prompt(
    question, catalog_text, prior_error, today=None,
    prior_question=None, prior_definition=None,
):
    base = ""
    if today:
        base += (
            f"Today's date is {today}. Resolve relative time expressions "
            '("last month", "this year", "yesterday") against this date, '
            "never against your training data.\n\n"
        )
    if prior_question and prior_definition:
        compact = json.dumps(prior_definition, separators=(",", ":"))
        base += (
            f'The user previously asked: "{prior_question}". You answered with '
            f"this definition: {compact}\n"
            "Modify the previous definition to satisfy the new request; keep "
            "everything the user did not ask to change.\n\n"
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

(If the relative-date-tokens plan landed first, the `today` sentence already reads "emit a relative-date token as instructed; resolve explicit dates…" — keep that wording; only add the refine block.)

In `ask_definition`, add the two keyword-only parameters after `today=None` (line 297):

```python
    today=None,
    prior_question=None,
    prior_definition=None,
```

and change the `_dispatch` call's second argument (line 310) to:

```python
        _definition_user_prompt(
            question, catalog_text, prior_error, today,
            prior_question=prior_question, prior_definition=prior_definition,
        ),
```

- [ ] **Step 4: Run the test file**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): refine context in AI definition drafting"
```

---

### Task 2: `api_ai_build` accepts the refine fields

**Files:**
- Modify: `nx_lib/views/reporting.py:1133-1191` (`api_ai_build`)
- Test: `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/integration/test_reporting_ai_routes.py` (mirror the patch set of the file's existing `test_ai_build_passes_today_to_drafter`; `AiDefinitionResult` and `patch` are already imported there):

```python
def _build_patches():
    stub = AiDefinitionResult(
        definition=None, explanation="", model="m", provider="anthropic",
        tokens_in=1, tokens_out=1,
    )
    return stub, [
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
    ]


def test_ai_build_passes_refine_context_to_drafter(user_client):
    stub, patches = _build_patches()
    with (
        patches[0], patches[1], patches[2], patches[3], patches[4],
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=stub) as drafter,
    ):
        resp = user_client.post(
            "/api/reporting/ai/build",
            json={
                "question": "only May",
                "priorQuestion": "docs last month",
                "priorDefinition": {"schemaVersion": 1, "title": "t"},
            },
        )
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["prior_question"] == "docs last month"
    assert drafter.call_args.kwargs["prior_definition"] == {"schemaVersion": 1, "title": "t"}


def test_ai_build_without_refine_context_passes_none(user_client):
    stub, patches = _build_patches()
    with (
        patches[0], patches[1], patches[2], patches[3], patches[4],
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=stub) as drafter,
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "q"})
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["prior_question"] is None
    assert drafter.call_args.kwargs["prior_definition"] is None


def test_ai_build_rejects_malformed_refine_context(user_client):
    stub, patches = _build_patches()
    bad_bodies = [
        {"question": "q", "priorQuestion": 7},
        {"question": "q", "priorDefinition": "not-an-object"},
        {"question": "q", "priorQuestion": "x" * 2001},
        {"question": "q", "priorDefinition": {"big": "y" * 20001}},
    ]
    with (
        patches[0], patches[1], patches[2], patches[3], patches[4],
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=stub),
    ):
        for body in bad_bodies:
            resp = user_client.post("/api/reporting/ai/build", json=body)
            assert resp.status_code == 400, body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v -k refine_context`
Expected: FAIL — `KeyError: 'prior_question'` for the first two; the malformed bodies currently return 200.

- [ ] **Step 3: Implement the request handling**

In `api_ai_build` (`nx_lib/views/reporting.py`), after the `question` check (line 1138-1139), insert:

```python
    # Refine context (optional): prompt grounding ONLY — never executed, never
    # trusted. The model's output still passes _validate_definition_for_user,
    # so a crafted prior definition cannot widen access; its risk class equals
    # free text in `question`. Size caps keep the prompt bounded.
    prior_question = body.get("priorQuestion")
    prior_definition = body.get("priorDefinition")
    if prior_question is not None and (
        not isinstance(prior_question, str) or len(prior_question) > 2000
    ):
        return jsonify({"error": _("Invalid refine context")}), 400
    if prior_definition is not None and (
        not isinstance(prior_definition, dict)
        or len(json.dumps(prior_definition)) > 20000
    ):
        return jsonify({"error": _("Invalid refine context")}), 400
```

In the `ai_ask_definition(...)` call (line 1179-1191), add after `today=...`:

```python
                today=datetime.date.today().isoformat(),
                prior_question=prior_question or None,
                prior_definition=prior_definition or None,
```

- [ ] **Step 4: Run the integration file**

Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): /ai/build accepts refine context"
```

---

### Task 3: AI thinking indicator on the Simple tab

**Files:**
- Modify: `templates/_reporting_simple.html` (result section, ~line 82), `templates/js/_reporting_simple_js.html` (I18N block 11-46, `showResultError` 162-173, `askAi` 660-684), `static/css/reporting.css` (append)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Template — indicator element**

In `templates/_reporting_simple.html`, after the `.reporting-simple-resultbar` closing `</div>` (line 82) and before `<p id="rsMsg" ...>`, insert (inside the existing markup, gated like the AI bar):

```html
    {% if ai_enabled %}
    <div id="rsAiLoading" class="reporting-ai-loading" hidden data-testid="rs-ai-loading">
      <span class="reporting-ai-dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span id="rsAiLoadingText" role="status"></span>
    </div>
    {% endif %}
```

- [ ] **Step 2: CSS**

Append to `static/css/reporting.css`:

```css
/* AI thinking indicator (Simple pane) */
.reporting-ai-loading {
  display: flex; align-items: center; justify-content: center; gap: .6rem;
  padding: 2.5rem 0; color: var(--nx-text-muted, #6b7280);
}
.reporting-ai-dots i {
  display: inline-block; width: 8px; height: 8px; margin: 0 2px;
  border-radius: 50%; background: currentColor;
  animation: rs-ai-pulse 1.2s infinite ease-in-out;
}
.reporting-ai-dots i:nth-child(2) { animation-delay: .2s; }
.reporting-ai-dots i:nth-child(3) { animation-delay: .4s; }
@keyframes rs-ai-pulse {
  0%, 80%, 100% { opacity: .25; transform: scale(.8); }
  40% { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .reporting-ai-dots i { animation: none; }
}
```

- [ ] **Step 3: JS — busy flag, rotating status line, askAi wiring**

In the `I18N` object of `templates/js/_reporting_simple_js.html`, append (trailing comma on the previous last entry):

```js
    aiThinking: {{ _("Asking the AI…")|tojson }},
    aiDrafting: {{ _("Drafting your report…")|tojson }},
    aiChecking: {{ _("Checking the result…")|tojson }}
```

Below `var runSeq = 0;` (~line 265), add:

```js
  // AI in-flight state: shared by ask + refine. The indicator owns the result
  // area while waiting; the rotating line is purely cosmetic.
  var aiBusy = false;
  var aiLoadingTimer = null;
  function showAiLoading() {
    setView('result');
    el('rsResultTitle').textContent = '';
    el('rsError').hidden = true;
    el('rsMsg').hidden = true;
    el('rsSaveName').hidden = true;
    el('rsStatCard').hidden = true;
    el('rsChartCard').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
    var lines = [I18N.aiThinking, I18N.aiDrafting, I18N.aiChecking];
    var i = 0;
    el('rsAiLoadingText').textContent = lines[0];
    el('rsAiLoading').hidden = false;
    aiLoadingTimer = setInterval(function () {
      i = (i + 1) % lines.length;
      el('rsAiLoadingText').textContent = lines[i];
    }, 3000);
  }
  function hideAiLoading() {
    var box = el('rsAiLoading');
    if (box) box.hidden = true;
    if (aiLoadingTimer) { clearInterval(aiLoadingTimer); aiLoadingTimer = null; }
  }
```

In `showResultError` (line 162), add as the first line of the body:

```js
    hideAiLoading();
```

Rework `askAi` (lines 660-684) to:

```js
  async function askAi() {
    var q = el('rsAiPrompt').value.trim();
    if (!q || aiBusy) return;
    aiBusy = true;
    el('rsAiAsk').disabled = true;
    showAiLoading();
    var res = await api('/api/reporting/ai/build', {
      method: 'POST', body: JSON.stringify({ question: q })
    });
    aiBusy = false;
    el('rsAiAsk').disabled = false;
    hideAiLoading();
    if (res.status === 503) {            // AI unconfigured: hide the helper
      aiBar.hidden = true;
      aiBar.dataset.gone = '1';
      setView('library');
      return;
    }
    if (res.status === 429) { showResultError(I18N.aiLimit); return; }
    // Check data.valid, not res.ok: the route returns 200 for invalid drafts.
    if (!res.ok || !res.data || !res.data.valid || !res.data.definition) {
      var why = (res.data && (res.data.explanation || res.data.error)) || '';
      showResultError(I18N.aiInvalid + (why ? ' (' + why + ')' : ''));
      return;
    }
    state.current = { def: res.data.definition, name: res.data.definition.title,
                      reportId: null, owned: true, canEdit: true, fromWizard: true,
                      aiExplanation: res.data.explanation || '',
                      aiQuestion: q };
    runCurrent();
  }
```

(`aiQuestion` is groundwork Task 4 consumes; harmless on its own.)

- [ ] **Step 4: e2e — stubbed AI endpoint shows the indicator, then the result**

Append to `tests/e2e/test_reporting_simple.py` (add `import json` and `import time` to the file's imports if missing). `page.route` stubs the provider-free endpoint — this also establishes the file's AI-stubbing pattern for Tasks 4-5:

```python
STUB_AI_DEFINITION = {
    "schemaVersion": 1, "source": "docprocessing", "visualization": "table",
    "title": "stub ai report", "subtitle": None,
    "columns": [{"field": "processname"}],
    "filters": [{"field": "processname", "op": "eq", "value": "acme.inv"}],
    "sort": [], "scope": {"clients": [], "processes": []}, "rowLimit": 100,
    "groupBy": [], "sql": None, "sqlTarget": None,
}


def _stub_ai_build(page, definition=None, delay_s=0.0):
    body = json.dumps({
        "definition": definition or STUB_AI_DEFINITION,
        "explanation": "stubbed explanation", "valid": True, "error": None,
    })

    def handler(route):
        if delay_s:
            time.sleep(delay_s)
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)


def test_ai_ask_shows_loading_then_result(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    _stub_ai_build(page, delay_s=0.8)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-ai-loading")).to_be_visible()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-ai-loading")).to_be_hidden(timeout=5000)
    expect(page.get_by_test_id("rs-msg")).to_contain_text("stubbed explanation")
```

(If the in-handler `time.sleep` proves flaky under sync Playwright, drop `delay_s` and keep only the post-conditions — the indicator's appearance is then covered by browser verification in Step 5.)

Run:

```powershell
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Browser-verify on INT** (restart server first): `.\bin\nx.ps1 -u -b --loginas:ben.streich`, ask the AI bar a real question, watch the pulsing dots + rotating line, result replaces it. Screenshot `var/screenshots/2026-06-10-ai-loading.png`; **send via SendUserFile if remote.**

- [ ] **Step 6: Commit**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): AI thinking indicator on Simple tab"
```

---

### Task 4: Refine bar on AI-built results

**Files:**
- Modify: `templates/_reporting_simple.html` (result section), `templates/js/_reporting_simple_js.html` (`runCurrent`, `showResultError`, `askAi`, listeners), `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Template — refine bar**

In `templates/_reporting_simple.html`, directly after the `rsAiLoading` block from Task 3 (still inside the `{% if ai_enabled %}` guard — merge into the same guard), add:

```html
    <div id="rsRefineBar" class="reporting-simple-refine" hidden data-testid="rs-refine-bar">
      <input id="rsRefineInput" class="reporting-input" data-testid="rs-refine-input"
             placeholder="{{ _('Refine your question…') }}"
             aria-label="{{ _('Refine your question…') }}">
      <button id="rsRefine" class="nx-btn nx-btn--secondary" data-testid="rs-refine">
        <i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>{{ _("Refine") }}</button>
    </div>
```

Append to `static/css/reporting.css`:

```css
.reporting-simple-refine { display: flex; gap: .5rem; margin: .4rem 0 .6rem; }
.reporting-simple-refine .reporting-input { flex: 1; }
```

- [ ] **Step 2: JS — generalize askAi for refine, show the bar on AI results**

Rework `askAi` (the Task 3 version) into the refine-aware version — the signature and the payload block change, failure restores the prior result:

```js
  async function askAi(refineQuestion) {
    var fromRefine = refineQuestion !== undefined;
    var q = fromRefine ? refineQuestion : el('rsAiPrompt').value.trim();
    if (!q || aiBusy) return;
    var payload = { question: q };
    var prior = state.current;
    if (fromRefine && prior && prior.aiQuestion && prior.def) {
      payload.priorQuestion = prior.aiQuestion;
      payload.priorDefinition = prior.def;
    }
    aiBusy = true;
    el('rsAiAsk').disabled = true;
    var refineBtn = el('rsRefine');
    if (refineBtn) refineBtn.disabled = true;
    showAiLoading();
    var res = await api('/api/reporting/ai/build', {
      method: 'POST', body: JSON.stringify(payload)
    });
    aiBusy = false;
    el('rsAiAsk').disabled = false;
    if (refineBtn) refineBtn.disabled = false;
    hideAiLoading();
    if (res.status === 503) {            // AI unconfigured: hide the helper
      aiBar.hidden = true;
      aiBar.dataset.gone = '1';
      setView('library');
      return;
    }
    if (res.status === 429) { showResultError(I18N.aiLimit); return; }
    // Check data.valid, not res.ok: the route returns 200 for invalid drafts.
    if (!res.ok || !res.data || !res.data.valid || !res.data.definition) {
      var why = (res.data && (res.data.explanation || res.data.error)) || '';
      if (fromRefine && prior) {
        // Failed refine: re-render the previous result and surface the error
        // above it instead of discarding the user's working report.
        state.current = prior;
        await runCurrent();
        el('rsError').textContent = I18N.aiInvalid + (why ? ' (' + why + ')' : '');
        el('rsError').hidden = false;
      } else {
        showResultError(I18N.aiInvalid + (why ? ' (' + why + ')' : ''));
      }
      return;
    }
    state.current = { def: res.data.definition, name: res.data.definition.title,
                      reportId: null, owned: true, canEdit: true, fromWizard: true,
                      aiExplanation: res.data.explanation || '',
                      aiQuestion: q };
    runCurrent();
  }
```

In `runCurrent`, directly after the `aiExplanation` block (lines 274-277), add:

```js
    var refineBar = el('rsRefineBar');
    if (refineBar) {
      var aiBuilt = cur.aiExplanation !== undefined;
      refineBar.hidden = !aiBuilt;
      if (aiBuilt) el('rsRefineInput').value = cur.aiQuestion || '';
    }
```

In `showResultError`, after the `hideAiLoading();` line from Task 3, add:

```js
    if (el('rsRefineBar')) el('rsRefineBar').hidden = true;
```

Next to the existing `rsAiAsk` listeners (lines 653-658), add inside the same `if (aiBar)` block:

```js
    el('rsRefine').addEventListener('click', function () {
      var q = el('rsRefineInput').value.trim();
      if (q) askAi(q);
    });
    el('rsRefineInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var q = el('rsRefineInput').value.trim();
        if (q) askAi(q);
      }
    });
```

- [ ] **Step 3: e2e — refine sends priors and replaces the result**

Append to `tests/e2e/test_reporting_simple.py` (reuses `_stub_ai_build`/`STUB_AI_DEFINITION` from Task 3):

```python
def test_refine_sends_prior_context_and_replaces_result(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    seen = []

    def handler(route):
        seen.append(route.request.post_data_json)
        refined = dict(STUB_AI_DEFINITION, title="refined report")
        body = json.dumps({"definition": refined, "explanation": "refined expl",
                           "valid": True, "error": None})
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-refine-bar")).to_be_visible()
    # The bar is pre-filled with the asked question.
    expect(page.get_by_test_id("rs-refine-input")).to_have_value("docs by process")

    page.get_by_test_id("rs-refine-input").fill("only acme please")
    page.get_by_test_id("rs-refine").click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("refined report")
    assert seen[0].get("priorQuestion") is None
    assert seen[1]["priorQuestion"] == "docs by process"
    assert seen[1]["priorDefinition"]["title"] == "stub ai report"
    assert seen[1]["question"] == "only acme please"
```

(`rsResultTitle` has no test id yet — add `data-testid="rs-result-title"` to the `<h3 id="rsResultTitle" ...>` in `templates/_reporting_simple.html:72` as part of this step.)

Run:

```powershell
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v
```

Expected: ALL PASS

- [ ] **Step 4: Browser-verify on INT** (restart first): ask a real question, refine it ("only last month"), watch the loading state and the replaced result; verify a nonsense refine ("asdfgh") keeps the old result + shows the error. Screenshot `var/screenshots/2026-06-10-ai-refine.png`; **send via SendUserFile if remote.**

- [ ] **Step 5: Commit**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): conversational refine on Simple results"
```

---

### Task 5: Editable filter/process chips

**Files:**
- Modify: `templates/_reporting_simple.html` (chips container), `templates/js/_reporting_simple_js.html` (chips renderer + editors, `runCurrent`), `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Template + CSS**

In `templates/_reporting_simple.html`, directly after `<p id="rsMsg" ...>` (line 83), add:

```html
    <div id="rsChips" class="reporting-simple-chips" hidden data-testid="rs-chips"></div>
```

Append to `static/css/reporting.css`:

```css
.reporting-simple-chips { display: flex; flex-wrap: wrap; gap: .4rem; margin: .2rem 0 .6rem; }
.rs-chip {
  display: inline-flex; align-items: center; gap: .35rem;
  padding: .15rem .6rem; border-radius: 999px; font-size: .85em;
  background: var(--nx-surface-2, #eef2ff); border: 1px solid var(--nx-border, #c7d2fe);
  cursor: pointer;
}
.rs-chip--empty { cursor: default; opacity: .7; }
.rs-chip .rs-chip-x { font-weight: 700; padding: 0 .15rem; }
.rs-chip-editor { display: inline-flex; align-items: center; gap: .35rem; }
.rs-chip-editor input, .rs-chip-editor select { max-width: 11rem; }
```

- [ ] **Step 2: JS — chip renderer and inline editors**

Add below the `tokenLabel`/`isTokenValue` helpers if the tokens plan landed, otherwise below `aiSummaryLine` (`templates/js/_reporting_simple_js.html` ~line 260). If the tokens plan has NOT landed yet, also include these two helpers verbatim (they are self-contained):

```js
  function isTokenValue(v) {
    return !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.token === 'string';
  }
  function tokenLabel(v) { return String(v.token).replace(/_/g, ' '); }
```

Then add the chips code:

```js
  // ----- Editable AI chips: correct the model's filter/process choices in
  // place, client-side only — mutate state.current.def and re-run. All nodes
  // are built via createElement/textContent (model text never hits innerHTML).
  function fieldMetaFor(def, fieldKey) {
    var src = (state.sources || []).find(function (s) { return s.id === def.source; });
    return ((src && src.fields) || []).find(function (f) { return f.field === fieldKey; });
  }

  function chipValueLabel(v) {
    if (isTokenValue(v)) return tokenLabel(v);
    if (Array.isArray(v)) return v.join(' → ');
    return v === null || v === undefined ? '' : String(v);
  }

  function chip(text, onEdit, onRemove) {
    var c = document.createElement('span');
    c.className = 'rs-chip';
    c.setAttribute('data-testid', 'rs-chip');
    var t = document.createElement('span');
    t.textContent = text;
    c.appendChild(t);
    if (onRemove) {
      var x = document.createElement('span');
      x.className = 'rs-chip-x';
      x.setAttribute('data-testid', 'rs-chip-remove');
      x.textContent = '×';
      x.addEventListener('click', function (e) { e.stopPropagation(); onRemove(); });
      c.appendChild(x);
    }
    if (onEdit) c.addEventListener('click', function () { onEdit(c); });
    return c;
  }

  function filterChipEditor(cur, f, chipEl) {
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    var meta = fieldMetaFor(cur.def, f.field);
    var isDateField = !!(meta && (meta.grainable || /date/i.test(meta.type || '')));
    // Token preset dropdown for date chips — only when the relative-date
    // tokens feature is present (TOKEN_LABELS is defined by that feature).
    // Lets a "Last month" chip become "This year" or a custom absolute range.
    var preset = null;
    if (isDateField && typeof TOKEN_LABELS !== 'undefined') {
      preset = document.createElement('select');
      preset.setAttribute('data-testid', 'rs-chip-preset');
      var co = document.createElement('option');
      co.value = '';
      co.textContent = I18N.custom;
      preset.appendChild(co);
      Object.keys(TOKEN_LABELS).forEach(function (k) {
        if (k === 'last_n_days') return;  // needs an n input; Advanced covers it
        var o = document.createElement('option');
        o.value = k;
        o.textContent = TOKEN_LABELS[k];
        preset.appendChild(o);
      });
      if (isTokenValue(f.value)) preset.value = f.value.token;
      box.appendChild(preset);
    }
    var input = document.createElement('input');
    input.className = 'reporting-input';
    input.setAttribute('data-testid', 'rs-chip-input');
    input.value = Array.isArray(f.value) ? f.value.join(' → ')
      : isTokenValue(f.value) ? '' : chipValueLabel(f.value);
    input.hidden = !!(preset && preset.value);
    if (preset) {
      preset.onchange = function () { input.hidden = !!preset.value; };
    }
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-apply');
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      if (preset && preset.value) {
        f.op = 'between';
        f.value = { token: preset.value };
        runCurrent();
        return;
      }
      var v = input.value.trim();
      if (isTokenValue(f.value) || Array.isArray(f.value) || f.op === 'between') {
        var parts = v.split('→').map(function (s) { return s.trim(); }).filter(Boolean);
        if (parts.length === 2) { f.op = 'between'; f.value = parts; }
      } else {
        f.value = v;
      }
      runCurrent();
    });
    box.appendChild(input);
    box.appendChild(ok);
    chipEl.replaceWith(box);
    if (!input.hidden) input.focus();
  }

  async function processChipEditor(cur, chipEl) {
    await loadSourcesCatalog();
    var src = (state.sources || []).find(function (s) { return s.id === cur.def.source; });
    var all = (src && src.processes) || [];
    if (!all.length) return;
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    box.setAttribute('data-testid', 'rs-chip-procs');
    var selected = ((cur.def.scope || {}).processes || []);
    var inputs = all.map(function (p) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = p;
      cb.checked = !selected.length || selected.indexOf(p) !== -1;
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + p));
      box.appendChild(lbl);
      return cb;
    });
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-apply');
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      var picked = inputs.filter(function (c) { return c.checked; })
                         .map(function (c) { return c.value; });
      cur.def.scope = cur.def.scope || { clients: [], processes: [] };
      // Everything selected = empty scope (server default "all allowed").
      cur.def.scope.processes = picked.length === all.length ? [] : picked;
      runCurrent();
    });
    box.appendChild(ok);
    chipEl.replaceWith(box);
  }

  function renderAiChips(cur) {
    var wrap = el('rsChips');
    if (!wrap) return;
    wrap.innerHTML = '';
    var aiBuilt = cur.aiExplanation !== undefined;
    wrap.hidden = !aiBuilt;
    if (!aiBuilt) return;
    var def = cur.def || {};
    (def.filters || []).forEach(function (f) {
      var label = f.field + ' ' + f.op + ' ' + chipValueLabel(f.value);
      wrap.appendChild(chip(
        label,
        function (chipEl) { filterChipEditor(cur, f, chipEl); },
        function () {
          def.filters.splice(def.filters.indexOf(f), 1);
          runCurrent();
        }
      ));
    });
    if (!(def.filters || []).length) {
      var none = document.createElement('span');
      none.className = 'rs-chip rs-chip--empty';
      none.textContent = I18N.aiNoFilters;
      wrap.appendChild(none);
    }
    var procs = (def.scope && def.scope.processes) || [];
    wrap.appendChild(chip(
      I18N.aiProcesses + ': ' + (procs.length ? procs.join(', ') : I18N.allProcesses),
      function (chipEl) { processChipEditor(cur, chipEl); },
      null
    ));
  }
```

Add the two new I18N strings (same block as before, trailing-comma rules apply):

```js
    chipApply: {{ _("Apply")|tojson }},
    allProcesses: {{ _("All processes")|tojson }}
```

In `runCurrent`, replace the `aiExplanation` block (lines 274-277) so the chips render alongside (the rsMsg line keeps the explanation only — filters/processes now live in the chips):

```js
    if (cur.aiExplanation !== undefined) {
      el('rsMsg').textContent = cur.aiExplanation || '';
      el('rsMsg').hidden = !cur.aiExplanation;
    }
    renderAiChips(cur);
```

Then **delete `aiSummaryLine`** (lines 247-260) — the chips row replaced its filter/process portion and `rsMsg` keeps the explanation. (Keep the Task-6/F1 `resolvedDates` append logic in `runCurrent` if the tokens plan landed — it composes with the explanation-only `rsMsg`.) In `setView`/`showResultError`, hide the chips too — add to `showResultError` after the refine-bar line:

```js
    if (el('rsChips')) el('rsChips').hidden = true;
```

- [ ] **Step 3: e2e — edit and remove chips without any AI call**

Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_chips_edit_and_remove_rerun_without_ai(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    _stub_ai_build(page)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    chips = page.get_by_test_id("rs-chips")
    expect(chips).to_be_visible()
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("processname eq acme.inv")

    # Edit the filter value in place; the run payload must carry the new value.
    run_payloads = []
    page.route("**/api/reporting/run", lambda route: (
        run_payloads.append(route.request.post_data_json), route.continue_())[1])
    chips.get_by_test_id("rs-chip").first.click()
    page.get_by_test_id("rs-chip-input").fill("acme.other")
    page.get_by_test_id("rs-chip-apply").click()
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("acme.other")
    assert any(
        p.get("filters") and p["filters"][0].get("value") == "acme.other"
        for p in run_payloads
    )

    # Remove the filter chip entirely -> "no filters" placeholder renders.
    chips.get_by_test_id("rs-chip-remove").first.click()
    expect(chips).to_contain_text("no filters")
```

(`route.continue_()` lets the real `/run` through — the route exists in the TEST app; a 400/empty result is fine, the assertions are on the chips and the captured payload. If the lambda tuple trick reads poorly, use a named handler function.)

Run:

```powershell
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v
```

Expected: ALL PASS

- [ ] **Step 4: Browser-verify on INT** (restart first): real AI ask → click a date-filter chip, change the value, Apply → result re-runs instantly (no AI cost); untick a process in the process chip → re-run; remove a chip. Screenshot `var/screenshots/2026-06-10-ai-chips.png`; **send via SendUserFile if remote.**

- [ ] **Step 5: Commit**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): editable AI filter/process chips"
```

---

### Task 6: i18n, changelog, docs

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`

- [ ] **Step 1: Babel cycle** (or `/nx-i18n`)

```powershell
.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

- [ ] **Step 2: Translate the new msgids**

| msgid | de | fr | it |
|---|---|---|---|
| `Refine` | `Verfeinern` | `Affiner` | `Affina` |
| `Refine your question…` | `Frage verfeinern…` | `Affinez votre question…` | `Affina la tua domanda…` |
| `Asking the AI…` | `KI wird gefragt…` | `Interrogation de l'IA…` | `Interrogazione dell'IA…` |
| `Drafting your report…` | `Bericht wird entworfen…` | `Préparation du rapport…` | `Preparazione del report…` |
| `Checking the result…` | `Ergebnis wird geprüft…` | `Vérification du résultat…` | `Verifica del risultato…` |
| `Invalid refine context` | `Ungültiger Verfeinerungskontext` | `Contexte d'affinage invalide` | `Contesto di affinamento non valido` |
| `Apply` | `Übernehmen` | `Appliquer` | `Applica` |
| `All processes` | `Alle Prozesse` | `Tous les processus` | `Tutti i processi` |

- [ ] **Step 3: Compile + verify**

```powershell
.venv\Scripts\pybabel.exe compile -d translations
.venv\Scripts\python.exe -m pytest tests -v -k translations
```

Expected: PASS

- [ ] **Step 4: Changelog** — under `[Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- Simple tab: AI-built results can be refined in place — the asked question stays editable above the result and re-asks the AI with the prior definition as context; the AI's filter/process choices render as chips that can be edited or removed directly (instant re-run, no AI cost); a thinking indicator shows while the model works.
```

- [ ] **Step 5: Docs**

- `docs/howto/reporting.md`: in the AI assistant section, document the refine bar (single-turn, chained priors, counts against the daily limit), the editable chips (client-side, free), and the loading indicator.
- `docs/design/reporting-ai-assistant.md`: document the `priorQuestion`/`priorDefinition` fields on `/api/reporting/ai/build` — prompt-context-only, size caps, output still fully validated (no new trust boundary); audit captures them via the composed prompt.

- [ ] **Step 6: Full verification run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit tests\integration -q
```

Expected: ALL PASS.

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md docs/design/reporting-ai-assistant.md
SQL_SYNC_SKIP=1 git commit -m "docs(reporting): i18n + docs for AI refine and chips"
```
