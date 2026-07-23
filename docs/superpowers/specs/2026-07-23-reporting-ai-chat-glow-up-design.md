# Reporting AI chat + result glow-up — design

**Date:** 2026-07-23 · **Branch:** feature/2.5.65 · **Status:** draft, awaiting owner review

## Goal

Take the reporting page from "clean but generic" to visibly premium, in four phases:

1. **AI chat** (flagship) — replace the one-shot Ask-AI textbox with a real conversational surface.
2. **Comparison deltas** — "↑ 12% vs previous period" chips backed by a real shifted-window query.
3. **Auto AI captions** — one-line generated insight under charts after every run.
4. **Formatting + polish** — chart/table formatting, skeletons, motion, sticky toolbar, dark-mode repair.

No DB migration and no new permission codes; everything rides on existing gates
(`reporting.ai.*`, `reporting.ai.explain_data`, daily AI limit, audit log).

## Phase 1 — AI chat

### Problem

Today the Ask-AI surface is a textbox: text stays in the box after submit, no history,
no feedback while the agent works. Feels unresponsive and impersonal. The user wants an
integrated chat — explicitly **not** a floating website-chatbot blob.

### UI

- **Docked right-side chat panel**, same slide-over pattern as the existing drill panel
  (`reporting-drill-panel`). Toggleable from both Simple and Advanced tabs via a
  persistent "AI" button in the page header area. Replaces both current Ask-AI surfaces
  (Simple ask card routes into the panel; Advanced "Ask AI" mode tab is removed).
- **Message list:** user bubbles right-aligned, assistant turns left. Assistant turns render:
  - answer text (the agent's narration),
  - a **result card** when the agent ran data (mini table; mini chart when shape suits),
  - an **action row**: Open in builder · Run · Show SQL · Save as report — wired to the
    existing `applyDefinition` / `applyDefinitionAndChart` / SQL-mode plumbing,
  - **follow-up chips** (heuristic, no extra AI call): e.g. "only this quarter",
    "break down by process", "show as chart".
- **Input behaviour:** clears on send, disabled while a request is in flight,
  Enter submits / Shift+Enter newline.
- **Progress:** animated status ticker while waiting ("reading schema…", "building
  query…", "running…"). Driven by elapsed-time stages; when the response arrives the
  ticker is replaced by the real turn. No SSE/streaming this round
  (`ponytail:` staged ticker, upgrade to SSE if the fake stages ever feel wrong).
- **Conversation lifetime:** JS state for the page visit only. No DB persistence,
  no cross-session history this round.
- Empty state: short intro + 3 starter question chips (reuse the Simple tab's examples).

### Backend

`POST /api/reporting/ai/agent` gains an optional `history` field:

```json
{ "question": "and only for Q2?",
  "history": [ {"role": "user", "content": "documents per month"},
               {"role": "assistant", "content": "Here are the monthly counts…"} ],
  "source": "…" }
```

- `history` is text-only prior turns (no tool traces), capped server-side to the last
  **8 turns** and ~4k chars total — older turns dropped silently.
- `ask_agentic()` gets an optional `history=None` param and seeds its message list with
  those turns before the grounded question. Grounding (catalog/schema/date) stays on the
  final user message only, so history stays cheap.
- Validation: reject non-list / malformed entries with 400. Roles other than
  user/assistant are dropped.
- Daily limit, audit row, permission-based tool binding: unchanged — one chat turn
  costs one "ask" exactly like today.

## Phase 2 — Comparison deltas

### Backend

`POST /api/reporting/run` gains an optional `compare: true` flag:

- Server resolves the definition's date tokens (existing `resolve_definition_tokens`),
  finds the resolved date window, shifts it back by its own length, and runs the same
  query once against the shifted window.
- Response gains a `comparison` block: per-metric totals for the prior window plus the
  resolved prior range (for the chip tooltip/label).
- **No resolvable date filter → no `comparison` block, no error.**
- Window-shift logic is a pure function (in `nx_lib/reporting/tokens.py`) with unit tests
  (month, quarter, year, explicit range, half-open ranges).
- Cost: second query only when the client asks (`compare` defaults off; frontend sends it
  for Simple-tab runs).

### Frontend

- Simple-tab KPI/total tiles get a delta chip: `↑ 12% vs 1 Mar – 31 Mar`. Green up,
  red down, grey when |Δ| < 0.5% or prior total is 0. Direction colouring is neutral
  grey when "up is good" is unknowable — counts get green-up by default, that's it.
- Tile numbers count up on run (respect `prefers-reduced-motion`).
- Sparkline in a tile **only** when the result already contains a time series — never an
  extra query.
- Advanced tab: no delta chips this round (grid/pivot/chart don't have a canonical
  "single number" to delta).

## Phase 3 — Auto AI captions

- New `POST /api/reporting/ai/caption`, gated `reporting.ai.explain_data` (the existing
  data-egress grant — exactly its purpose) + `@limiter.limit`.
- Request: columns, capped rows (≤ 50), report title, resolved date label. Response: 1–2
  sentence caption in the user's locale.
- Frontend fires it **automatically after every run** (Simple result view + Advanced chart
  view), async: chart renders instantly, caption shimmers in under it with a small "AI"
  chip. Any error → silently no caption.
- Users without `reporting.ai.explain_data` never see the surface (template already
  exposes `ai_explain_enabled`).
- Counts against the daily AI limit and writes an audit row (`surface: "caption"`).
- In the chat panel, no captions — the agent's own narration covers it.

## Phase 4 — Formatting + polish

**Chart formatting** (`templates/js/_reporting_viz_js.html`, Chart.js options only):

- Integer/unit tick formatting — kill the 0.0–1.0 float axis on count data.
- Rounded bar corners, softer gridlines, richer tooltips (formatted values + series label).
- Consistent palette shared between chart, tiles, and pivot heat.

**Table conditional formatting** (render-time, frontend only):

- Numeric columns get CSS data bars (linear-gradient background scaled to column max).

**Polish layer:**

- Skeleton loaders replace the spinner in the results area.
- Staged card entrance via `.nx-rise` — fill-mode `backwards`, never `both`
  (stacking-context trap).
- Sticky results toolbar on scroll.
- Dark-mode repair: replace hardcoded `#fff` / `#eef` etc. in `static/css/reporting.css`
  with nx tokens so the moon toggle stops half-working on this page.

## Testing

- Unit: window-shift pure function; `history` validation/capping; caption endpoint
  permission gate (403 without explain_data) and row cap.
- Integration: `/api/reporting/run` with `compare` (with and without date filter);
  agent endpoint threads history.
- E2E: chat panel smoke (send → answer renders → input cleared → follow-up uses history);
  existing reporting e2e stays green (`_stub_run_ok` pattern for AI stubs; reset test DB
  before pre-push).
- Screenshots to `var/screenshots/` per UI phase.

## Chores

- i18n de/fr/it for all new strings (`/nx-i18n`), changelog under `[Unreleased]`,
  `docs/howto/reporting.md` + `docs/design/reporting-ai-assistant.md` updated
  (Ask-AI textbox → chat panel; new endpoints/flags documented).
- No DB migration. No new permission codes. No new dependencies.

## Build order

Phases land independently in this order: **1 (chat) → 4 (formatting/polish) → 2 (deltas)
→ 3 (captions)** — chat is the flagship, polish is cheap and de-risks the CSS surface
before deltas/captions add chrome on top of it.
