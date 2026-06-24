# Reporting: conversational refine on Simple-tab AI results — design

- **Date:** 2026-06-10
- **Status:** approved design, NOT implemented (plan: `docs/superpowers/plans/2026-06-10-reporting-ai-refine.md`)
- **Problem:** after Ask-AI builds a report on the Simple tab, the only recovery from a wrong guess is to start over (re-type a fuller question) or "Open in Advanced". The transparency line (added 2026-06-10) makes wrong guesses *visible*; this feature makes them *fixable* in place. Additionally, the ask flow has no visible progress state while the model thinks (several seconds on Azure `gpt-4o-mini`).

## Goal

Three additions to the Simple-tab result view for AI-built reports:

1. **Refine bar** — the asked question stays visible and editable above the result; submitting it re-asks the AI *with the prior question + prior definition as context*, single-turn, replacing the result.
2. **Editable chips** — the transparency line's filters/processes become chips the user can edit or remove directly (no AI round trip), re-running the report immediately.
3. **AI loading animation** — a visible thinking indicator for every Simple-tab AI call (ask + refine).

## 1. Refine bar

**UX:** for AI-built results (`state.current.aiExplanation !== undefined`), a bar renders between the result title and the transparency line: a text input pre-filled with the question that produced the result, plus a "Refine" button. The user edits the question ("…I meant the Privera invoice process, only May") and submits. The new result replaces the old; the bar now shows the new question. Iterating naturally chains — each refine uses the *latest* question/definition as prior context. No thread UI, no history state.

**API:** extend `POST /api/reporting/ai/build` (`api_ai_build`, `views/reporting.py:1133-1255`) with two optional fields:

```json
{"question": "...edited question...", "priorQuestion": "...", "priorDefinition": {...}}
```

No new endpoint — refine reuses the daily limit, audit, and the 2-attempt validation/self-repair loop unchanged. A refine call counts against the daily AI limit like any other call (it is a provider call).

**Prompt plumbing:** `ask_definition` (`ai.py:285-336`) gains keyword-only `prior_question=None, prior_definition=None`; `_definition_user_prompt` (`ai.py:264-282`) prepends, when both are present:

> The user previously asked: "{prior_question}". You answered with this definition: {compact JSON}. The user now wants: "{question}". Modify the previous definition to satisfy the new request; keep everything the user did not ask to change.

The prior definition is serialized compactly (`json.dumps(..., separators=(",", ":"))`); definitions are small (well under 1 KB) so token budget is not a concern.

**Security:** `priorQuestion`/`priorDefinition` are client-supplied and used **only as prompt context — never executed and never trusted**. The model's *output* definition passes through `_validate_definition_for_user` (catalog whitelists, process scope intersection) exactly as today, so a crafted prior definition cannot reach data the caller's permissions don't allow; its risk class is identical to free text in `question`. Validation of the request body: `priorDefinition` must be a JSON object and `priorQuestion` a string, both size-capped (reject > 20 KB), else 400.

**Audit:** no schema change. The audited `Prompt` for a refine call is the composed user prompt, which embeds the prior question and definition — full traceability without new `ReportingAiAudit` columns.

**State:** `state.current` (`_reporting_simple_js.html:48-57`) gains `aiQuestion` (the question that produced the current result). On every successful ask/refine: `aiQuestion = submitted question`. Refine submits `{question: edited, priorQuestion: cur.aiQuestion, priorDefinition: cur.def}`. State is per-page-load JS only; navigating away loses refine context by design (the report itself can be saved as usual).

## 2. Editable chips (manual correction, no AI)

The transparency line (`aiSummaryLine`, `_reporting_simple_js.html:247-260`) is upgraded from a text line to a chip row (still under the title, XSS-safe DOM construction — `createElement`/`textContent`, never `innerHTML` with model text):

- **One chip per filter** — label `field op value` (humanized; relative-date tokens render as "Last month" per the tokens design). Clicking swaps the chip for a small inline editor: values edit as text (a `between` range as `start → end`); when the relative-date tokens feature is present, date-field chips additionally offer the token preset dropdown (so a "Last month" chip can become "This year" or a custom absolute range). flatpickr-in-popover is deliberately skipped in v1. Each chip has an × to remove the filter.
- **One process chip** — shows chosen processes; clicking opens a checkbox list of the allowed processes, which the page already has client-side: `/api/reporting/sources` returns `processes` per docprocessing source (`api_sources`, `views/reporting.py:884-908`) and the Simple pane caches it in `state.sources` (`loadSourcesCatalog`). No new endpoint.
- **Apply** mutates `state.current.def` (filters / `scope.processes`) directly and calls `runCurrent()` — pure client-side, instant, no AI call, no daily-limit cost.
- Adding *new* filters stays out of scope — that's "Open in Advanced" territory. Chips edit or remove what the AI chose.

Edited definitions remain valid by construction where possible (field/op unchanged, only value/processes change); the server still re-validates on run, and a validation error surfaces in the existing error area.

Chips render for AI-built results. (Wizard-built results keep the plain summary for now — the wizard's own steps are the edit path; revisit later if users ask.)

## 3. AI loading animation

While a Simple-tab AI call is in flight (ask or refine): the result area shows a centered indicator — three pulsing dots (CSS keyframes in `static/css/reporting.css`, `prefers-reduced-motion` honored: dots become a static "…") plus a rotating status line cycling i18n strings ("Asking the AI…", "Drafting your report…", "Checking the result…" on a ~3 s timer, purely cosmetic). The Ask/Refine buttons disable for the duration via a new shared `aiBusy` flag (today `askAi` only disables the Ask button — `_reporting_simple_js.html:663-667`). On response, the indicator is replaced by the result or the error message. Pure CSS + template strings; no new dependencies.

## Out of scope

- Multi-turn thread UI / conversation history.
- Persisting refine context server-side (DB or session) across page loads.
- New `ReportingAiAudit` columns (`IsRefinement` etc.) — composed prompt suffices.
- Refine on the Advanced tab's AI surfaces (Surface B SQL, Surface C agent — the agent already carries follow-up context via `agentContext()`, `_reporting_ai_js.html:187-196`).
- Editing chips on wizard-built (non-AI) results.

## Error handling

- Refine validation failure after the 2-attempt loop → same error path as ask today (message in result area, prior result left in place — the old `state.current` is only replaced on success).
- Daily limit hit on refine → existing `aiLimit` message.
- Chip edit producing a server-side validation error on run → error in the existing run-error area; definition stays as edited so the user can fix it.
- Empty refine question → ignore submit (same as ask).

## Testing

- **Unit (`tests/unit/test_reporting_ai_definition.py`):** prompt-content tests — refine block present when both priors given, absent otherwise, compact JSON serialization, ordering (refine block before catalog).
- **Integration (`tests/integration/test_reporting_ai_routes.py`):** `api_ai_build` threads `priorQuestion`/`priorDefinition` to `ask_definition` (patched drafter, kwargs assertion — mirror `test_ai_build_passes_today_to_drafter`); size-cap / wrong-type rejection → 400; refine counts toward the daily limit.
- **e2e (`tests/e2e/test_reporting_simple.py`):** chips path is AI-free and fully e2e-able — build a report via the wizard-free path (inject a definition), render chips, edit a filter value, assert re-run payload; remove chip; process chip toggling. Loading indicator: assert element appears with `aiBusy` (can be tested by stubbing fetch latency) — keep shallow.
- **Live INT verification:** refine round trip with Azure (no e2e AI stub exists — known gap, unchanged by this design).
- **i18n:** new strings ("Refine", "Refine your question…", "Asking the AI…", "Drafting your report…", "Checking the result…", chip editor labels, "Remove filter") translated de/fr/it.

## Rejected alternatives

1. **Chat-thread UX** — richer but needs thread state, more audit, more UI surface; single-turn refine with chained priors covers the demonstrated journey ("wrong process / wrong month → correct it") at a fraction of the complexity.
2. **New `/api/reporting/ai/refine` endpoint** — would duplicate the limit/audit/validation-loop plumbing for zero behavioral difference; optional fields on the existing endpoint are strictly simpler.
3. **Server-persisted refine sessions** — page-load-scoped JS state matches how the Simple tab already works (`state.current` is ephemeral); persistence adds schema + cleanup for a marginal case.
