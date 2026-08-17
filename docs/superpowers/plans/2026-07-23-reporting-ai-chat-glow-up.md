# Reporting AI Chat + Result Glow-Up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchors are **function names + quoted snippets**, never line numbers — re-`Grep` before editing (the in-flight chat-collab-removal plan reshapes `nx_lib/views/reporting.py` before this plan touches it — see sequencing below). Spec: `docs/superpowers/specs/2026-07-23-reporting-ai-chat-glow-up-design.md`.

**Goal:** Four-phase reporting upgrade: (1) replace the one-shot Ask-AI textbox with a real conversational chat panel (docked, both tabs, multi-turn via a backend `history` param); (2) chart/table formatting + motion/skeleton/dark-mode polish; (3) "vs previous period" delta chips backed by a real shifted-window comparison query; (4) automatic AI insight captions under charts.

**Architecture:** The chat rides the existing Surface-C agentic loop — `ask_agentic` gains an optional `history` seed and `/api/reporting/ai/agent` accepts capped prior turns, replacing the client-side `agentContext()` string-prepend hack. The panel is a new docked slide-over (drill-panel pattern) whose JS supersedes `_reporting_ai_js.html`'s three-surface form; the Advanced "Ask AI" mode and the Simple ask-result/refine path both route into it. Comparison runs reuse `_prepare_run` verbatim on a token-shifted definition produced by a pure helper in `tokens.py`. Captions are a new small endpoint gated by the existing `reporting.ai.explain_data` data-egress grant. Polish is CSS/Chart.js-options only.

**Tech Stack:** Flask + existing provider-agnostic AI client (`nx_lib/reporting/ai.py`), Chart.js (already vendored), vanilla-JS Jinja partials, `--nx-*` design tokens (`html.dark`), pytest unit/integration, Playwright e2e, Flask-Babel de/fr/it.

## Context an engineer needs (read first)

- **SEQUENCING — read this or break INT:** the `2026-07-23-chat-collab-removal-bug-fixes` plan is EXECUTING on `feature/2.5.65` concurrently with this plan's authoring. Its Part B modifies `nx_lib/views/reporting.py` (`run_sql_bound` gains `_authorize_sql_target` + `_has_acked` gates inside `api_ai_agent` — the very function Task 1 edits) and `nx_lib/reporting/sandbox.py` (fetch-side row cap). **Do not start this plan until that plan's final commit lands.** Then bring this branch current: `git merge feature/2.5.65` into `plan/reporting-ai-chat-glow-up` (or execute directly on `feature/2.5.65` and delete the plan worktree). Re-`Grep` every anchor after the merge.
- **Worktree:** this plan was authored in `.claude/worktrees/plan-reporting-ai-chat-glow-up` (branch `plan/reporting-ai-chat-glow-up`, based mid-way through the removal plan's execution). See sequencing point above before executing in it.
- **No DB migration, no new permission codes, no new dependencies** anywhere in this plan.
- **AI surface map today:** `templates/js/_reporting_ai_js.html` implements three sub-surfaces (build / sql / agent) sharing one `#rpAiPrompt` input inside the inline `#rpAiPanel` in `templates/reporting.html` (Advanced pane). Only the agent surface threads turns (`agentThread`) and clears the input; build/sql do neither — that is the UX complaint driving Phase 1. The Simple hero bar (`#rsAiPrompt`/`#rsAiAsk` + `.rs-suggestion` chips in `templates/_reporting_simple.html`) posts to `/api/reporting/ai/build` then `/api/reporting/run` (`_reporting_simple_js.html`, anchor `var res = await api('/api/reporting/ai/build', {`).
- **Template flags already passed** by the `reporting` view: `ai_enabled`, `ai_sql_enabled`, `ai_explain_enabled` (anchor in `nx_lib/views/reporting.py`: `ai_explain_enabled=has_permission("reporting.ai.explain_data")`). Reuse them; add none.
- **`ask_agentic` seeds `messages = [{"role": "user", "content": question}]`** (`nx_lib/reporting/ai.py`) — the history param slots in immediately before that seed. Providers already translate the neutral messages list (`_to_azure_messages` / `_to_anthropic_messages`).
- **Date tokens:** `nx_lib/reporting/tokens.py` — `resolve_token(value, today)` → inclusive `(start, end)`; `resolve_definition_tokens(rd, today)` rewrites each token filter into `gte start` + `lt end+1day` literal clauses. `_resolved_dates_meta(rd)` in the views module already extracts `{field, token, start, end}` per token filter for the run response. Comparison (Phase 3) supports **token-filtered definitions only** — the Simple wizard's time step always emits tokens; explicit literal ranges get no delta (documented ceiling).
- **KPI band:** `_reporting_simple_js.html` — `computeKpiBand(dims, rows)` computes total/buckets/avg/peak client-side; `kpiBlock(...)` renders `.reporting-ledger-kpi` blocks into `#rsKpiBand`. Delta chips and sparklines hang off this exact spot.
- **Dark mode:** `html.dark` class + `--nx-*` token overrides in `static/css/nexora-ui.css` (`:root` then `html.dark` blocks). `static/css/reporting.css` (2258 lines) hardcodes `#fff`/`#eef`/`#ddd` — that's why the moon toggle half-breaks the page.
- **Charts:** Chart.js via `templates/js/_reporting_viz_js.html` (`ReportingViz.mountChart(container, columns, rows, opts)`, `applyChartHint`, `chartPngDataUrl`). No new chart lib.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. Dev server (`nx -u`) runs global Python — new runtime deps would need both, but this plan adds none. TEST env has **no Statistics DB**: integration tests mock engines; e2e stubs the network — copy the `_stub_run_ok` pattern (`tests/e2e/test_reporting_simple.py`) and the agent-stub pattern (`tests/e2e/test_reporting_agent.py`). Reset before e2e: `.venv\Scripts\python scripts\test_db_reset.py`.
- **Jinja template cache is process-lifetime** — `nx -r` before any manual browser check; `nx -u -b --loginas:<user>` for Playwright; screenshots to `var/screenshots/` and send them (remote-session rule).
- **PROD URL prefix:** new fetches in JS partials go through the existing `API_PREFIX` / `api()` helpers — never a bare root-relative literal.
- **i18n:** ONE pybabel cycle at the end (final task). `tests/unit/test_translations.py` is RED from the first template edit until then — `--deselect tests/unit/test_translations.py` in intermediate runs. After `pybabel update`, **diff-sweep every `.po`** (pybabel has silently mangled existing msgstr lines before).
- **Pre-commit hooks:** SQL hooks run on every commit even with zero SQL changes (migrate no-op + sync check, can take minutes). Offline/slow escape hatch: `SQL_SYNC_SKIP=1 git commit …` — **never `--no-verify`**.
- **gitlint:** conventional-commit subject ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via `git commit -F - <<'EOF' … EOF`.
- **GitNexus:** advisory if available (`gitnexus_impact` on `api_ai_agent`, `ask_agentic`, `api_run` before editing); it has been unavailable in recent sessions — every anchor here is Grep/Read-verified instead.
- **Daily AI limit + audit:** every AI endpoint checks `_ai_asks_today(userid)` against `_ai_daily_limit()` and writes `_audit_ai(...)`. Chat turns and captions each count as one ask — no separate budget.

## Global constraints

- Anchor on quoted snippets + function names, NEVER line numbers. Re-`Grep` any snippet that moved (especially in `nx_lib/views/reporting.py` after the removal plan lands).
- Motion respects `prefers-reduced-motion` (count-up, shimmer, entrance animations all no-op under it).
- `.nx-rise` entrance animations use fill-mode `backwards`, never `both` (stacking-context trap — `both` buries overflowing popovers).
- All new user-facing strings wrapped `{{ _("…") }}` / `_( "…" )` at introduction time; the pot/po cycle runs once at the end.
- New CSS goes in `static/css/reporting.css` using `--nx-*` tokens only — no new hardcoded colors.
- Stage only each task's named files. Commit per task. **No `git push`, no PR** — the owner reviews and pushes.
- Commit trailer names the EXECUTING model, e.g. `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D-CHAT-ENDPOINT | The chat panel speaks ONLY to `/api/reporting/ai/agent`. `/api/reporting/ai/build` and `/api/reporting/ai/ask` stay registered (schedule/AI-build internals may reuse them later) but lose their UI callers. | One conversational brain; the agent's tool loop subsumes build & SQL drafting. Removing the endpoints is a separate YAGNI decision for another day. |
| D-HISTORY | `history` = prior `{role, content}` TEXT turns only (no tool traces), validated server-side: list of dicts, roles ∈ {user, assistant}, capped to the last 8 turns AND ~4000 chars (drop oldest first, silently). Grounding stays on the final user message only. | Bounded token cost; replaces the client-side `agentContext()` prepend hack with a real conversation the providers already understand. |
| D-PANEL-UI | Docked right-side slide-over reusing the drill-panel pattern (`reporting-drill-panel` CSS as the style precedent, new `reporting-chat-*` classes), opened by one persistent "AI chat" header button next to the Sources button, available on BOTH tabs. The inline `#rpAiPanel` + `#rpModeAi` mode button are removed. | Integrated, not a floating website-chatbot blob; one home for AI on the whole page. |
| D-SIMPLE-ROUTE | The Simple hero bar and suggestion chips stay visually, but submitting **opens the chat panel and sends the text as a chat message**. The Simple AI-ask result path (`showAiLoading` + refine bar branches in `_reporting_simple_js.html`) is excised; the shared result view stays for library/wizard runs. | Spec decision: one conversation. Refine = chat follow-up now. |
| D-PROGRESS | Progress ticker = elapsed-time staged lines (reuse the `showAiLoading` rotating-lines mechanism as precedent), replaced by the real turn on arrival. No SSE/streaming this round. | ponytail: staged ticker; upgrade to SSE only if fake stages ever feel wrong. |
| D-CHAT-LIFETIME | Conversation lives in JS module state for the page visit. No DB persistence, no sessionStorage. | YAGNI; a refresh starts fresh, matching today's agent thread. |
| D-COMPARE | `compare: true` in the `/api/reporting/run` body triggers ONE extra run of the same definition with its single token filter shifted back by the window's own length (helper `shifted_definition_for_comparison` in `tokens.py`). Response gains `comparison: {rows, columns, priorStart, priorEnd}`; the client computes prior totals with the same `computeKpiBand`. No token filter (or >1) → no `comparison` key, never an error. | Server owns token resolution; client owns aggregation exactly as it does for the main run. Literal-range support is a documented ceiling. |
| D-DELTA-UI | Delta chips render on the Simple KPI band only (total/avg/peak get chips; buckets doesn't). Green up / red down for counts, grey when prior total is 0 or |Δ| < 0.5%. Sparkline only when the main result already contains a time series (dims include a grained date field) — never an extra query. Advanced tab: no chips this round. | Simple is where single-number KPIs live; Advanced's grid/pivot has no canonical number to delta. |
| D-CAPTION | New `POST /api/reporting/ai/caption` gated `@require_permission("reporting.ai.explain_data")` + `@limiter.limit("10 per minute")` + daily AI limit + audit (`surface="caption"`). Body: columns, ≤50 rows, title, resolved-dates label. New `caption()` helper in `ai.py` with its own system prompt, answers in the user's locale, 1–2 sentences. Fired automatically after every Simple result render and Advanced chart mount; silent on any error; absent entirely without the perm (`ai_explain_enabled` flag). NOT fired inside the chat panel. | The data-egress grant exists for exactly this; automatic-per-run is the owner's explicit choice. |
| D-DARK | Dark-mode repair = mechanical sweep of `reporting.css` hardcoded colors to `--nx-*` tokens (`#fff`→`var(--nx-card)`, `#eef`/`#ddd`→`var(--nx-border)`, fixed dark text→`var(--nx-text)` etc.). No new tokens; where no token fits, nearest existing token wins. | The tokens + `html.dark` overrides already exist; reporting.css just ignores them. |
| D-CHARTFMT | Chart formatting via Chart.js options in `mountChart` only: integer tick `callback` (skip non-integers on count axes), `maxTicksLimit`, `borderRadius` on bars, softer grid color from a `--nx-border` read, tooltip callbacks with `fmtNumber`-style formatting. Palette: one shared JS array of nx-indigo-family colors used by chart datasets and (Phase 2) table data bars. | No new lib; kills the 0.0–1.0 float axis. |
| D-E2E | Every e2e that exercises AI or run flows stubs the network: `/api/reporting/ai/agent` (new chat stubs), `/api/reporting/run` (`_stub_run_ok`), `/api/reporting/ai/caption` (stub or absent-perm). Never let a Playwright test hit Azure. | TEST env has no Statistics DB and no AI config; live calls = flaky + cost. |

## Owner actions (not for the executor)

1. **Gate:** confirm the chat-collab-removal plan has fully landed on `feature/2.5.65` before letting this plan execute; then merge `feature/2.5.65` into `plan/reporting-ai-chat-glow-up` (or execute on the feature branch directly and remove the worktree).
2. **Review + push** when done — pre-push gate runs the FULL suite incl. e2e (`scripts/test_db_reset.py` first; `uv pip install -r requirements.txt` if the venv drifted).
3. **Azure cost check** after a week of auto-captions on INT: each run by an `explain_data` holder = one small completion. If noisy, flip the frontend call to on-demand (the endpoint doesn't care).
4. **Decide later** whether `/api/reporting/ai/build` + `/ask` (now UI-orphaned) get removed — deliberately out of scope here.

---

# PHASE 1 — AI CHAT

### Task 1: `history` param — `ask_agentic` + `/api/reporting/ai/agent`

**Files:**
- Modify: `nx_lib/reporting/ai.py` (`ask_agentic`), `nx_lib/views/reporting.py` (`api_ai_agent`)
- Test: `tests/unit/test_reporting_ai_agentic.py`, `tests/integration/test_reporting_ai_routes.py`

**Interfaces:**
- Produces: `ask_agentic(question, *, registry, agent_step, max_turns=DEFAULT_MAX_TURNS, history=None)` — `history` is a pre-validated list of `{"role": "user"|"assistant", "content": str}`. Endpoint accepts optional `history` in the JSON body; response shape unchanged.

- [ ] **Step 1 — Write the failing unit tests** in `tests/unit/test_reporting_ai_agentic.py` (copy the module's existing scripted-`agent_step` style):

```python
def test_ask_agentic_seeds_history_before_question():
    seen = {}
    def step(messages):
        seen["messages"] = list(messages)
        return AssistantTurn(text="done", tool_calls=[])
    result = ask_agentic(
        "follow-up?", registry=ToolRegistry(), agent_step=step,
        history=[{"role": "user", "content": "first"},
                 {"role": "assistant", "content": "answer"}])
    assert seen["messages"][0] == {"role": "user", "content": "first"}
    assert seen["messages"][1] == {"role": "assistant", "content": "answer"}
    assert seen["messages"][2] == {"role": "user", "content": "follow-up?"}
    assert result.answer == "done"

def test_ask_agentic_no_history_unchanged():
    def step(messages):
        assert messages == [{"role": "user", "content": "q"}]
        return AssistantTurn(text="ok", tool_calls=[])
    assert ask_agentic("q", registry=ToolRegistry(), agent_step=step).answer == "ok"
```

- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_reporting_ai_agentic.py -q` — fails: unexpected keyword `history`.
- [ ] **Step 3 — Implement in `ai.py`.** Change the signature to `def ask_agentic(question, *, registry, agent_step, max_turns=DEFAULT_MAX_TURNS, history=None):` and the seed line `messages = [{"role": "user", "content": question}]` to:

```python
    messages = list(history or []) + [{"role": "user", "content": question}]
```

- [ ] **Step 4 — Write the failing integration tests** in `tests/integration/test_reporting_ai_routes.py` (copy its existing agent-endpoint test fixtures/mocks): (a) POST with `history` = list of 10 user/assistant turns each 600 chars → assert the `ask_agentic` call (patch it) received ≤8 turns and total content ≤ ~4000 chars, oldest dropped; (b) `history` = `"not-a-list"` → 400; (c) history entries with `role: "tool"` or non-string content are dropped, request still succeeds.
- [ ] **Step 5 — Implement in `api_ai_agent`.** After the `question` extraction (anchor: `question = (body.get("question") or "").strip()`), add sanitation + cap, then thread into the call (anchor: `result = ask_agentic(initial, registry=registry, agent_step=step)`):

```python
    raw_history = body.get("history")
    if raw_history is not None and not isinstance(raw_history, list):
        return jsonify({"error": _("Invalid history")}), 400
    history = []
    for h in raw_history or []:
        if (isinstance(h, dict) and h.get("role") in ("user", "assistant")
                and isinstance(h.get("content"), str) and h["content"].strip()):
            history.append({"role": h["role"], "content": h["content"]})
    history = history[-8:]
    while history and sum(len(h["content"]) for h in history) > 4000:
        history.pop(0)
```

```python
        result = ask_agentic(initial, registry=registry, agent_step=step, history=history)
```

- [ ] **Step 6 — GREEN run.** `.venv\Scripts\python -m pytest tests/unit/test_reporting_ai_agentic.py tests/integration/test_reporting_ai_routes.py -q`.
- [ ] **Step 7 — Commit:**

```bash
git add nx_lib/reporting/ai.py nx_lib/views/reporting.py tests/unit/test_reporting_ai_agentic.py tests/integration/test_reporting_ai_routes.py
git commit -F - <<'EOF'
feat(reporting): thread conversation history into the AI agent

ask_agentic gains an optional history seed and /api/reporting/ai/agent
accepts prior user/assistant text turns, validated and capped to the
last 8 turns / ~4k chars server-side. Grounding stays on the final user
message only. Replaces the client-side answer-prepend hack and enables
the chat panel.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 2: Chat panel markup + CSS

**Files:**
- Modify: `templates/reporting.html`, `static/css/reporting.css`

**Interfaces:**
- Produces DOM ids Task 3 wires: `#rpChatToggle` (header button), `#rpChatPanel`, `#rpChatBackdrop`, `#rpChatThread`, `#rpChatEmpty` (with three `.rp-chat-starter` buttons), `#rpChatForm`, `#rpChatInput` (`<textarea rows="1">`), `#rpChatSend`, `#rpChatClose`. All inside `{% if ai_enabled %}`.

- [ ] **Step 1 — Header button.** In `templates/reporting.html`, next to the Sources button (anchor: the `nx-btn` whose label is `{{ _("Sources") }}` in the `nx-page-head` block), add inside `{% if ai_enabled %}`:

```html
<button id="rpChatToggle" class="nx-btn nx-btn--secondary" data-testid="reporting-chat-toggle"
        aria-controls="rpChatPanel" aria-expanded="false">
  <i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>{{ _("AI chat") }}</button>
```

- [ ] **Step 2 — Panel skeleton.** Alongside the existing drill panel markup (anchor: `class="reporting-drill-panel"`), add the chat slide-over (same backdrop/panel structure; new classes, `role="dialog"`, `aria-label="{{ _('AI chat') }}"`):

```html
{% if ai_enabled %}
<div id="rpChatBackdrop" class="reporting-chat-backdrop" hidden></div>
<aside id="rpChatPanel" class="reporting-chat-panel" hidden role="dialog"
       aria-label="{{ _('AI chat') }}" data-testid="reporting-chat-panel">
  <div class="reporting-chat-head">
    <span class="reporting-chat-title"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>{{ _("AI chat") }}</span>
    <button id="rpChatClose" class="nx-btn nx-btn--ghost nx-btn--sm" data-testid="reporting-chat-close"
            aria-label="{{ _('Close') }}">&times;</button>
  </div>
  <div id="rpChatThread" class="reporting-chat-thread" data-testid="reporting-chat-thread">
    <div id="rpChatEmpty" class="reporting-chat-empty">
      <p>{{ _("Ask about your data in plain language. I can build reports, draft SQL, and — with the right permission — run read-only queries and report real numbers.") }}</p>
      <button type="button" class="rp-chat-starter" data-testid="rp-chat-starter">{{ _("documents per month this year") }}</button>
      <button type="button" class="rp-chat-starter" data-testid="rp-chat-starter">{{ _("invoices by process, last 3 months") }}</button>
      <button type="button" class="rp-chat-starter" data-testid="rp-chat-starter">{{ _("pages processed per week") }}</button>
    </div>
  </div>
  <form id="rpChatForm" class="reporting-chat-form">
    <textarea id="rpChatInput" class="reporting-chat-input" rows="1"
              placeholder="{{ _('Ask about your data…') }}" data-testid="reporting-chat-input"></textarea>
    <button id="rpChatSend" type="submit" class="nx-btn nx-btn--primary" data-testid="reporting-chat-send"
            aria-label="{{ _('Send') }}"><i class="fas fa-paper-plane" aria-hidden="true"></i></button>
  </form>
</aside>
{% endif %}
```

- [ ] **Step 3 — CSS.** In `static/css/reporting.css`, add a `/* ---- AI chat panel ---- */` section modeled on the `.reporting-drill-panel` rules: fixed right slide-over (~420px, `100dvh`, `translateX` transition honoring `prefers-reduced-motion`), tokens only (`var(--nx-card)`, `var(--nx-border)`, `var(--nx-text)`). Message bubbles: `.rp-chat-msg--user` (right-aligned, `var(--nx-accent-soft)` bg) / `.rp-chat-msg--ai` (left, `var(--nx-card)` + border); `.rp-chat-actions` chip row; `.rp-chat-result` mini-table card (max-height + `overflow:auto`); `.rp-chat-ticker` with the three-dot pulse copied from `.reporting-ai-dots`; `.rp-chat-starter` chips reusing `.rs-suggestion`'s look. (Grep `reporting-ai-dots` and `rs-suggestion` in this file and mirror their rules rather than inventing new visuals.)
- [ ] **Step 4 — Verify + commit.** `nx -r`, load `/reporting` — button renders on both tabs, panel opens nothing yet (JS comes next; `hidden` attrs keep it inert). `.venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py -q` GREEN. Commit:

```bash
git add templates/reporting.html static/css/reporting.css
git commit -F - <<'EOF'
feat(reporting): add AI chat panel markup and styles

Docked right-side slide-over (drill-panel pattern) with thread, empty
state, starter chips and a send form, plus a header toggle next to
Sources. Token-based CSS only; JS wiring lands separately.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 3: Chat JS — rewrite `_reporting_ai_js.html`, retire the Ask-AI mode

**Files:**
- Modify: `templates/js/_reporting_ai_js.html` (full rewrite), `templates/reporting.html` (remove `#rpModeAi` + `#rpAiPanel`), `templates/js/_reporting_js.html` (drop AI-mode references if any — `Grep "rpModeAi|rpAiPanel"` first)
- Test: `tests/integration/test_reporting_routes.py` (template-render assertions)

**Interfaces:**
- Consumes: Task 1's `history` param; Task 2's DOM ids; existing `window.Reporting.applyDefinition` / `applyDefinitionAndChart`; existing `#rpSqlEditor` insert mechanics; `/api/reporting/ai/agent` response `{answer, definition, sql, toolTrace, turns, stoppedReason, explainData}`.
- Produces: `window.ReportingChat.open(prefillText?)` and `window.ReportingChat.send(text)` — Task 4's Simple-side hooks.

- [ ] **Step 1 — Write the failing render test.** In `tests/integration/test_reporting_routes.py`, in the reporting-page render test with AI enabled, assert `b"rpChatPanel" in body` and `b"rpAiPanel" not in body` and `b"rpModeAi" not in body`.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -q`.
- [ ] **Step 3 — Remove the old surface.** In `templates/reporting.html`: delete the `#rpModeAi` button (anchor: `data-testid="reporting-mode-ai"`) and the whole `#rpAiPanel` block (anchor: `data-testid="reporting-ai-panel"` through its closing `</div>` before `rpAiError`'s parent closes — the block is fully inside one `{% if ai_enabled %}`). In `_reporting_js.html`, `Grep "rpModeAi|rpAiPanel"` — remove any references (recon found none; verify).
- [ ] **Step 4 — Rewrite `templates/js/_reporting_ai_js.html`** as the chat module (keep filename → no include changes; keep `API_PREFIX` + `csrfToken()` + `escapeHtml` helpers from the old file). Structure:

```js
var chat = { history: [], busy: false };          // history: [{role, content}]
function openPanel(prefill) { /* unhide panel+backdrop, aria-expanded, focus input, optional prefill */ }
function closePanel() { /* hide, restore focus to #rpChatToggle */ }
function pushMsg(role, html) { /* append .rp-chat-msg--{role}, hide #rpChatEmpty, scroll to bottom */ }
function startTicker() { /* .rp-chat-ticker bubble cycling AGENT_LINES every 3s (reuse old AI_LINES strings) */ }
function send(text) {
  if (chat.busy || !text.trim()) return;
  pushMsg("user", escapeHtml(text));
  input.value = ""; input.style.height = "";      // THE fix: clear on send
  chat.busy = true; sendBtn.disabled = true; startTicker();
  fetch(API_PREFIX + "api/reporting/ai/agent", { method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
    body: JSON.stringify({ question: text, history: chat.history,
      source: (document.getElementById("rpSource") || {}).value || null })
  }).then(...).then(function (res) {
    stopTicker(); chat.busy = false; sendBtn.disabled = false;
    if (!res.ok) { pushMsg("ai", errorBubble((res.data && res.data.error) || netErrText)); return; }
    chat.history.push({ role: "user", content: text });
    chat.history.push({ role: "assistant", content: res.data.answer || "" });
    pushMsg("ai", aiTurnHtml(res.data));
    wireTurnActions(res.data);                    // event listeners on the just-inserted node
  }).catch(function () { stopTicker(); chat.busy = false; sendBtn.disabled = false;
    pushMsg("ai", errorBubble(netErrText)); });
}
```

  `aiTurnHtml(d)` renders: answer text (escaped, newlines→`<br>`); a collapsed `<details>` tool-trace (port `renderAgentTrace`'s chip/step markup verbatim); action chips — Open in builder (when `d.definition`), Insert SQL (when `d.sql` and `#rpSqlEditor` exists — port the old `agentInsertSqlBtn` logic incl. disabled-`modeSql` fallback), Show SQL (toggles an inline `<pre>` via `ReportingSqlFormat.render`); and three static follow-up chips (`{{ _("Only this quarter") }}`, `{{ _("Break down by process") }}`, `{{ _("Show it as a chart") }}`) that call `send(chipText)`. Form submit + Enter (Shift+Enter = newline) call `send(input.value)`; starter chips send their own text; `#rpChatToggle`/`#rpChatClose`/backdrop toggle the panel; textarea autosizes (set `style.height` from `scrollHeight`, cap ~5 rows). Expose `window.ReportingChat = { open: openPanel, send: send }`.
- [ ] **Step 5 — GREEN run + browser.** Integration test GREEN. `nx -r`, then `nx -u -b --loginas:<user>`: open panel, ask a question against the real INT agent (AI is live on INT), watch ticker → answer bubble with actions, input cleared, follow-up chip works (history threading visible in the answer). Screenshot `var/screenshots/reporting_chat_panel.png` + send it.
- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_ai_js.html templates/reporting.html templates/js/_reporting_js.html tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): replace the Ask-AI mode with the chat panel

_reporting_ai_js.html becomes the chat module: message thread, cleared
input on send, staged progress ticker, per-turn tool trace, action
chips (open in builder, insert/show SQL) and follow-up chips, with
multi-turn context via the new history param. The inline rpAiPanel and
the Ask AI mode button are removed.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 4: Simple tab routes into the chat; excise the ask-result/refine path

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`, `templates/_reporting_simple.html` (only if refine-bar markup lives there — `Grep "refine"` both files first)
- Test: `tests/e2e/test_reporting_simple.py`

**Scope:** the hero bar (`#rsAiPrompt`, `#rsAiAsk`, `.rs-suggestion` chips) stays; its submit handler becomes `window.ReportingChat.open()` + `ReportingChat.send(text)` (and clears `#rsAiPrompt`). The AI-ask result branch — the `showAiLoading()` call chain around the anchor `var res = await api('/api/reporting/ai/build', {`, the subsequent auto-run, and the refine bar (`Grep "refine" -i` — includes the `Refine` button and `showResultError` refine-bar interplay) — is removed. The shared result view, wizard, library and their run paths are UNTOUCHED (`Grep` shows which branches are ask-only by following the callers of the `ai/build` fetch; trace before deleting — if a helper is shared with the wizard, keep it).

- [ ] **Step 1 — Rewire the hero.** Replace the `#rsAiAsk` click / hero submit handler body with:

```js
if (window.ReportingChat) {
  window.ReportingChat.open();
  window.ReportingChat.send(q);
  promptEl.value = "";
}
```

  Suggestion chips route through the same path. The `ai_enabled`-off fallback (`#rsAiGone` hint) keeps its current behavior.
- [ ] **Step 2 — Excise the dead branch.** Remove the ask-only code path (the `ai/build` fetch + its loading/refine/error rendering). After the excision `Grep "ai/build"` in the file → zero hits; `Grep "refine" -i` → zero live hits.
- [ ] **Step 3 — Rework e2e.** In `tests/e2e/test_reporting_simple.py`: the AI-ask flow tests now stub `/api/reporting/ai/agent` (copy the stub pattern from `tests/e2e/test_reporting_agent.py`) and assert: hero submit opens `[data-testid="reporting-chat-panel"]`, a user bubble + an AI bubble render, and `[data-testid="reporting-chat-input"]` is empty after send. Delete/adapt refine-bar assertions. Keep wizard/library e2e untouched.
- [ ] **Step 4 — Run.** `.venv\Scripts\python scripts\test_db_reset.py`, then `.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q` GREEN. `nx -r` + browser: hero ask opens chat and answers; wizard + library still run reports. Screenshot `var/screenshots/reporting_chat_from_simple.png` + send.
- [ ] **Step 5 — Commit** (`feat(reporting): route Simple ask into the chat panel` — body: hero + chips now open the shared chat; ask-result/refine path removed; wizard, library and shared result view untouched; e2e reworked to the chat flow).

### Task 5: Chat e2e smoke

**Files:**
- Modify: `tests/e2e/test_reporting_agent.py` (extend — it already stubs the agent endpoint)

- [ ] **Step 1 — Write the smoke** (stubbed agent endpoint returning a definition + answer): open chat from Advanced via `[data-testid="reporting-chat-toggle"]`; send "documents per month"; assert user bubble, AI bubble with answer text, cleared input, "Open in builder" chip visible; click a follow-up chip → assert the SECOND stub call's request body `history` contains the first two turns (assert via the route-stub's captured request JSON); click "Open in builder" → builder shows the definition title (existing `applyDefinition` behavior).
- [ ] **Step 2 — Run.** `.venv\Scripts\python scripts\test_db_reset.py`, then `.venv\Scripts\python -m pytest tests/e2e/test_reporting_agent.py -q` GREEN.
- [ ] **Step 3 — Commit** (`test(reporting): e2e smoke for the AI chat panel` — body: covers open/send/clear/follow-up-history/open-in-builder against a stubbed agent endpoint).

---

# PHASE 2 — FORMATTING + POLISH

### Task 6: Chart formatting (ticks, bars, tooltips, palette)

**Files:**
- Modify: `templates/js/_reporting_viz_js.html`
- Test: `tests/e2e/test_reporting_viz.py` (existing suite must stay green — it asserts chart mounting, not pixel values)

- [ ] **Step 1 — Palette + option helpers.** Near the top of the module add the shared palette and read the border token once:

```js
var NX_PALETTE = ['#4f46e5', '#7c3aed', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#64748b'];
function gridColor() {
  var v = getComputedStyle(document.documentElement).getPropertyValue('--nx-border').trim();
  return v || 'rgba(100,116,139,.18)';
}
```

- [ ] **Step 2 — Apply in `mountChart`.** In the Chart.js config it builds (anchor: `function mountChart(container, columns, rows, opts)` — Read the function first; it already builds `datasets`/`options`): datasets take `backgroundColor` from `NX_PALETTE` (cycled) and `borderRadius: 6` + `maxBarThickness: 48` for bar type; `options.scales.y.ticks.callback` skips non-integers when every plotted value is an integer (`Number.isInteger` sweep once over the values), `maxTicksLimit: 6`, `grid.color: gridColor()`; `options.plugins.tooltip.callbacks.label` formats via the module's existing number formatter (`Grep "fmtNumber|toLocaleString"` in the file and reuse — don't add a second formatter).
- [ ] **Step 3 — Run + verify.** `.venv\Scripts\python scripts\test_db_reset.py`, `.venv\Scripts\python -m pytest tests/e2e/test_reporting_viz.py -q` GREEN. `nx -r`, run a count-by-month report → integer axis, rounded bars, formatted tooltip. Screenshot `var/screenshots/reporting_chart_formatting.png` + send.
- [ ] **Step 4 — Commit** (`feat(reporting): chart formatting — integer ticks, rounded bars, tooltips` — body: shared NX palette, token-derived grid color, no new library).

### Task 7: Table data bars, count-up, skeletons, entrance, sticky toolbar

**Files:**
- Modify: `templates/js/_reporting_js.html` (grid render), `templates/js/_reporting_simple_js.html` (KPI count-up + result skeleton), `static/css/reporting.css`

- [ ] **Step 1 — Data bars.** In the Advanced grid renderer (`Grep "renderResults"` in `_reporting_js.html`, find the row/cell building loop): for each numeric column compute the column max once; numeric `<td>`s get `class="rp-cell-num" style="--bar: {pct}%"`. CSS:

```css
.rp-cell-num { position: relative; font-variant-numeric: tabular-nums; }
.rp-cell-num::before { content: ""; position: absolute; inset: 4px auto 4px 0;
  width: var(--bar, 0%); background: var(--nx-accent-soft, #eef2ff);
  border-radius: 3px; z-index: -1; }
```

  Apply the same treatment in the Simple result grid if it has its own cell loop (`Grep "tabular|<td"` in `_reporting_simple_js.html`; reuse the same class).
- [ ] **Step 2 — Count-up.** In `_reporting_simple_js.html`, where `kpiBlock`/`renderKpiBand` writes `.reporting-ledger-kpi-value`, animate 0→value over ~500ms with `requestAnimationFrame`, skipped entirely when `matchMedia('(prefers-reduced-motion: reduce)').matches` (write the final value directly). ~10 lines, one helper `animateValue(el, target, fmt)`.
- [ ] **Step 3 — Skeletons.** Replace the results-area spinner/loading state (`Grep "loading" -i` in both partials for the current mechanism) with skeleton blocks: CSS `.rp-skeleton` (token-based shimmer via `background: linear-gradient(90deg, var(--nx-border) …)` + `@keyframes`, static under reduced-motion) and a small JS helper injecting a KPI-band-shaped + table-shaped skeleton while a run is in flight.
- [ ] **Step 4 — Entrance + sticky.** Add `.nx-rise` (fill-mode `backwards` — never `both`) to the Simple result cards and chat bubbles' entrance; make `.reporting-toolbar` sticky: `position: sticky; top: 0; z-index: 5; background: var(--nx-card);`.
- [ ] **Step 5 — Verify + commit.** `nx -r`; run reports on both tabs; toggle OS reduced-motion (or DevTools emulation) and confirm no animation. e2e reporting suite spot-run: `.venv\Scripts\python -m pytest tests/e2e/test_reporting.py tests/e2e/test_reporting_simple.py -q` GREEN. Screenshot `var/screenshots/reporting_polish_pass.png` + send. Commit (`feat(reporting): data bars, KPI count-up, skeletons, sticky toolbar` — body: all motion honors prefers-reduced-motion; token-based CSS only).

### Task 8: Dark-mode repair of `reporting.css`

**Files:**
- Modify: `static/css/reporting.css`

- [ ] **Step 1 — Sweep.** Mechanical replace throughout the file: `background: #fff` → `var(--nx-card)`; `#eef`/`#e5e7eb`/`#ddd` borders → `var(--nx-border)`; near-black text colors → `var(--nx-text)`; grey secondary text → `var(--nx-text-sec)`, faint meta text → `var(--nx-text-meta)` (those are the real token names — there is no `--nx-text-muted`). Keep brand indigos (`#4338ca` etc.) — they work on both themes. Do NOT touch `.reporting-drill-*` rules already using tokens.
- [ ] **Step 2 — Verify.** `nx -r`, toggle the moon: both tabs, chat panel, SQL editor, result grid, pivot readable in dark. Screenshots `var/screenshots/reporting_dark_light.png` (both themes side by side or two files) + send.
- [ ] **Step 3 — Commit** (`fix(reporting): use nx design tokens so dark mode works` — body: hardcoded whites/greys swept to --nx-* tokens; brand accents kept).

---

# PHASE 3 — COMPARISON DELTAS

### Task 9: `shifted_definition_for_comparison` (pure helper)

**Files:**
- Modify: `nx_lib/reporting/tokens.py`
- Test: `tests/unit/test_reporting_tokens.py`

**Interfaces:**
- Produces: `shifted_definition_for_comparison(rd, today=None)` → `(shifted_rd, prior_start, prior_end)` or `None`. Only acts when `rd["filters"]` contains EXACTLY ONE token-valued filter; the shifted rd carries literal `gte`/`lt` clauses for the prior window; `prior_start`/`prior_end` are inclusive `datetime.date`s for display.

- [ ] **Step 1 — Write the failing tests** in `tests/unit/test_reporting_tokens.py` (module already tests `resolve_definition_tokens` — copy its fixture style). Cases: `this_month` on 2026-07-23 → prior window `[2026-06-01, 2026-07-01)` i.e. `prior_start=2026-06-01`, `prior_end=2026-06-30`; `last_n_days` n=7 → the 7 days before those; `this_quarter` → full prior quarter-length window ending at the quarter start; no token filter → `None`; two token filters → `None`; non-token filters pass through unchanged in the shifted rd.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_reporting_tokens.py -q`.
- [ ] **Step 3 — Implement** in `tokens.py` (below `resolve_definition_tokens`):

```python
def shifted_definition_for_comparison(rd, today=None):
    """Same definition with its single relative-date window shifted back by
    the window's own length: [start - len, start). Returns (shifted_rd,
    prior_start, prior_end) with inclusive display dates, or None when the
    definition has no token filter or more than one (ambiguous).

    # ponytail: token filters only — literal date ranges get no comparison;
    # extend via date_fields_from_catalog if that ceiling ever hurts.
    """
    filters = (rd or {}).get("filters") or []
    token_filters = [
        f for f in filters
        if isinstance(f, dict) and isinstance(f.get("value"), dict) and "token" in f["value"]
    ]
    if len(token_filters) != 1:
        return None
    f = token_filters[0]
    start, end = resolve_token(f["value"], today)
    end_excl = end + datetime.timedelta(days=1)
    length = end_excl - start
    prior_start, prior_end_excl = start - length, start
    new_filters = [x for x in filters if x is not f]
    new_filters.append({"field": f["field"], "op": "gte", "value": prior_start.isoformat()})
    new_filters.append({"field": f["field"], "op": "lt", "value": prior_end_excl.isoformat()})
    out = dict(rd)
    out["filters"] = new_filters
    return out, prior_start, prior_end_excl - datetime.timedelta(days=1)
```

- [ ] **Step 4 — GREEN run**, then **commit** (`feat(reporting): pure helper shifting a token window for comparison` — body: [start−len, start) semantics, single-token-filter contract, None otherwise).

### Task 10: `compare` flag on `/api/reporting/run`

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_run`)
- Test: `tests/integration/test_reporting_routes.py`

**Interfaces:**
- Produces: request body key `compare: true` → response gains `comparison: {columns, rows, priorStart, priorEnd}` (same column shape as the main payload) when the definition qualifies; key absent otherwise. Never fails the main run: a comparison-run error logs a warning and omits the key.

- [ ] **Step 1 — Write the failing integration tests** (copy the module's existing `api_run` test mocks for `_prepare_run`/`_execute`): (a) `compare: true` + one token filter → response has `comparison` with `priorStart`/`priorEnd` strings and rows from the second (mocked) execute; (b) `compare: true`, no token filter → no `comparison` key, 200; (c) comparison execute raises → main payload intact, no `comparison` key, 200; (d) no `compare` key → `_execute` called exactly once.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -q`.
- [ ] **Step 3 — Implement.** In `api_run`, after the payload dict is built (anchor: `payload = {` … `"params": [_json_safe(p) for p in params],`), insert before the `resolvedDates` block:

```python
    if rd.get("compare"):
        shifted = shifted_definition_for_comparison(rd)
        if shifted is not None:
            shifted_rd, prior_start, prior_end = shifted
            try:
                c_columns, c_sql, c_params, c_engine = _prepare_run(shifted_rd)
                c_rows = _execute(c_engine, c_sql, c_params)
                payload["comparison"] = {
                    "columns": [
                        {"field": c["field"], "header": c.get("header") or c["field"]}
                        for c in c_columns
                    ],
                    "rows": _rows_json_safe(c_rows),
                    "priorStart": prior_start.isoformat(),
                    "priorEnd": prior_end.isoformat(),
                }
            except Exception as e:
                current_app.logger.warning(f"/api/reporting/run comparison skipped: {e}")
```

  Import the helper next to the existing `from .. tokens import` site (`Grep "resolve_token" nx_lib/views/reporting.py` for the import line and extend it).
- [ ] **Step 4 — GREEN run**, then **commit** (`feat(reporting): optional shifted-window comparison on run` — body: compare flag runs the same definition once more over the prior window via the pure shift helper; comparison failures degrade to no key, never a failed run; double query only when requested).

### Task 11: Delta chips + sparkline on the Simple KPI band

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`, `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py`

**Scope:** Simple's run call sites (anchor: `var t = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(totalDef) });` and the breakdown run below it) add `compare: true` to the posted definition. When the response carries `comparison`, compute prior KPIs with the SAME `computeKpiBand(dims, comparison.rows)` and render chips next to total/avg/peak values; `title`/`aria-label` = `{{ _("vs") }} priorStart – priorEnd`. Chip element carries `data-testid="rp-delta"`: `↑ 12%` / `↓ 8%` / `— 0%`; classes `.rp-delta--up` (green), `.rp-delta--down` (red), `.rp-delta--flat` (muted); flat when prior total is 0 or |Δ| < 0.5%. Sparkline: when the main result's dims include a grained date field (the definition's columns carry a `grain` — `Grep "grain"` in the file for how the wizard marks it), render an inline SVG `<polyline>` of the metric series into the total tile (~15 lines, no Chart.js instance); skip otherwise.

- [ ] **Step 1 — Write the failing e2e** (extend the `_stub_run_ok` stub to include a `comparison` block): run a wizard report with a time preset → assert a `[data-testid="rp-delta"]` chip renders with the up class and the vs-range tooltip; stub without `comparison` → no chip.
- [ ] **Step 2 — RED run**, **Step 3 — implement** (delta chip render inside `kpiBlock` callers, sparkline helper, `compare: true` on both run posts, CSS for the three chip states + `.rp-sparkline`), **Step 4 — GREEN run** (`test_reporting_simple.py`) + browser check on INT with a real time-filtered report; screenshot `var/screenshots/reporting_delta_chips.png` + send.
- [ ] **Step 5 — Commit** (`feat(reporting): delta chips and sparklines on the Simple KPI band` — body: compare:true on Simple runs; prior KPIs via the same computeKpiBand; chips green/red/flat with vs-range tooltip; sparkline only when the result already carries a time series).

---

# PHASE 4 — AUTO AI CAPTIONS

### Task 12: `caption()` helper + `/api/reporting/ai/caption`

**Files:**
- Modify: `nx_lib/reporting/ai.py` (new `caption()`), `nx_lib/views/reporting.py` (new `api_ai_caption` + route registration)
- Test: `tests/unit/test_reporting_ai.py`, `tests/integration/test_reporting_ai_routes.py`

**Interfaces:**
- Produces: `POST /api/reporting/ai/caption` body `{columns: [{field, header}], rows: [...], title?: str, dateLabel?: str}` → `{caption: str}`. Gated `@require_permission("reporting.ai.explain_data")`, `@limiter.limit("10 per minute")`, daily AI limit, audit `surface="caption"`. Rows capped server-side to 50 (silently truncated). `caption(columns, rows, title, date_label, *, locale, cfg)` in `ai.py` dispatches via the module's existing provider plumbing (`Grep "def ask("` and copy its `_dispatch`/`_call_*` usage) with system prompt: concise data-analyst, 1–2 sentences, no preamble, answer in `{locale}`.

- [ ] **Step 1 — Write the failing unit test** for `caption()` (mock the provider call like `test_reporting_ai.py`'s existing `ask` tests): returns stripped text; truncates rows to 50 before building the prompt.
- [ ] **Step 2 — Write the failing integration tests**: (a) without `reporting.ai.explain_data` → 403; (b) with perm + mocked `caption()` → 200 `{caption}`; (c) provider raises → 502 with translated error; (d) daily limit reached → 429 (copy the agent endpoint's limit-test pattern).
- [ ] **Step 3 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_reporting_ai.py tests/integration/test_reporting_ai_routes.py -q`.
- [ ] **Step 4 — Implement** `caption()` in `ai.py`; `api_ai_caption` in the views module following `api_ai_agent`'s skeleton (config check → 503, daily limit → 429 + audit `blocked`, try/except → 502 + audit `error`, success → audit `ok` with tokens/duration); register after the agent rule (anchor: `endpoint="reporting_ai_agent"`):

```python
    app.add_url_rule(
        "/api/reporting/ai/caption",
        endpoint="reporting_ai_caption",
        view_func=api_ai_caption,
        methods=["POST"],
    )
```

- [ ] **Step 5 — GREEN run**, then **commit** (`feat(reporting): AI caption endpoint over result rows` — body: gated by reporting.ai.explain_data (the data-egress grant), rate-limited, counts toward the daily AI limit, rows capped at 50; provider errors degrade to 502, frontend treats any error as no caption).

### Task 13: Fire captions after runs (shimmer-in, silent-fail)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`, `templates/js/_reporting_js.html`, `templates/reporting.html` (caption slot divs), `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py` (stub caption), `tests/e2e/test_reporting.py` (spot-check unaffected without perm)

**Scope:** template gets `{% if ai_explain_enabled %}<div id="rsCaption" class="rp-caption" hidden></div>{% endif %}` under the Simple result chart area and `#rpCaption` under `#rpChart` in Advanced (find both mount points by `Grep "rpChart"` / the Simple chart container id). Shared JS helper (put it in `_reporting_simple_js.html` if no shared util partial exists — duplicate the ~20 lines in `_reporting_js.html` rather than inventing a new shared file): after a successful run render (Simple) / chart mount (Advanced), when the caption div exists, show `.rp-caption--loading` shimmer, POST columns + first 50 rows + title + resolved-dates label to `api/reporting/ai/caption`, then fill `<span class="rp-caption-chip">AI</span> {caption}` or hide on any error. Abort/ignore stale responses when a newer run lands (simple monotonically-increasing run counter). NOT called anywhere in the chat panel.

- [ ] **Step 1 — Failing e2e:** stub caption endpoint → run → caption text appears with the AI chip; error-stub variant → caption div stays hidden, no console error.
- [ ] **Step 2 — RED**, **Step 3 — implement**, **Step 4 — GREEN** (`test_reporting_simple.py`, `test_reporting.py`) + INT browser check (real caption from Azure); screenshot `var/screenshots/reporting_caption.png` + send.
- [ ] **Step 5 — Commit** (`feat(reporting): auto AI captions under result charts` — body: fires after each run for explain_data holders, shimmer-in, silent on error, stale responses discarded, never inside the chat panel).

---

# PHASE 5 — CLOSEOUT

### Task 14: i18n cycle, changelog, docs, final screenshots

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`), `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`

- [ ] **Step 1 — pybabel cycle.** `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → translate every new msgid in de/fr/it (chat panel strings, chips, caption/delta strings, error lines) → `pybabel compile -d translations`. **Diff-sweep all three `.po` files for mangled EXISTING msgstr lines** (known pybabel trap) before committing.
- [ ] **Step 2 — Run translations test.** `.venv\Scripts\python -m pytest tests/unit/test_translations.py -q` GREEN (first time since Phase 1 started).
- [ ] **Step 3 — CHANGELOG.** Under `[Unreleased]`: **Added** — AI chat panel (multi-turn, both tabs); `history` on `/api/reporting/ai/agent`; `compare` on `/api/reporting/run` + delta chips/sparklines; `/api/reporting/ai/caption` + auto captions; chart/table formatting, skeletons, sticky toolbar. **Changed** — Simple ask + Advanced Ask-AI mode replaced by the chat panel; reporting page dark-mode support. **Removed** — inline Ask-AI panel and its refine bar.
- [ ] **Step 4 — Docs.** `docs/howto/reporting.md`: replace the Ask-AI textbox description with the chat panel (open/toggle, actions, follow-ups, history cap), document `compare` + `comparison` response, the caption endpoint + its permission, and the delta-chip semantics. `docs/design/reporting-ai-assistant.md`: Surface C section gains the history contract (8 turns / 4k chars, text-only); note captions as the shipped Phase-3e narration surface, gated `reporting.ai.explain_data`. Fix any now-stale references to `rpAiPanel`/refine flow in either doc (`Grep "refine|rpAi" docs/`).
- [ ] **Step 5 — Full local verify.** `.venv\Scripts\python -m pytest tests/unit tests/integration -q` GREEN; `.venv\Scripts\python scripts\test_db_reset.py` + full reporting e2e set GREEN. Fresh screenshot set (light + dark, chat open, deltas, caption) to `var/screenshots/` + send.
- [ ] **Step 6 — Commit** (`docs(reporting): chat panel, comparison and caption docs + i18n cycle` — body: one pybabel cycle for all four phases; changelog updated; howto + AI design doc reflect the chat surface, compare flag and caption endpoint).

---

## Gotchas & notes

- **`api_ai_agent` will have moved** by execution time (removal plan's D-RUNSQL adds gates inside it). The Task 1 anchors (`question = (body.get("question") or "").strip()`, `result = ask_agentic(initial, …)`) are stable either way — re-Grep, don't assume offsets.
- **Don't break the agent's grounding contract:** `initial` (grounding + question) stays the FINAL user message; history goes strictly before it. Putting grounding into history would multiply schema text per turn.
- **`_reporting_ai_js.html` is included once** from `reporting.html` inside `{% if ai_enabled %}` (`Grep "_reporting_ai_js"` to confirm at execution) — the chat module inherits that gate; guard every `getElementById` for the `ai_enabled`-off render anyway (the old file's early-return pattern).
- **Simple excision risk:** the ask-result view shares helpers with wizard/library runs. Trace callers before deleting anything; the ONLY dead code is what exclusively serves the `ai/build` ask path + refine bar.
- **`compare` on SQL-mode runs:** `api_sql_run` is a different endpoint — untouched. Only definition runs compare.
- **Caption data egress:** rows leave the building — that's precisely what `reporting.ai.explain_data` authorizes. Never soften the gate to `reporting.ai.ask`.
- **Sparkline ≠ chart:** inline SVG polyline, no Chart.js instance per tile (tiles re-render often; chart instances leak).
- **Chip color semantics:** more documents/invoices = green-up is fine, but never invert (down=green) heuristically — flat/unknown stays grey.
- **e2e AI race:** the Simple AI-ask e2e race trap (stub `/api/reporting/run` BEFORE clicking) applies to every new chat/caption test — stub first, then interact.
- **Screenshots are part of done** for every UI task (remote-session rule): `var/screenshots/`, sent via SendUserFile.
