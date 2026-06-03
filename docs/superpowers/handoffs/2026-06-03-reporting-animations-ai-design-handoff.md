# Handoff — Reporting animations (Motion) + AI-assistant design doc

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63` (committed locally, **NOT pushed** — remote
  session, commit-only)
- **Feature commits:** `e58a9a7` (animations) · `1546b79` (AI design doc) ·
  this handoff
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-reporting-phase4-backlog-complete-handoff.md`

## TL;DR

Two independent pieces of work, both committed on `feature/2.5.63`, **unpushed**:

1. **Reporting UI animations** (`e58a9a7`) — a purely additive animation layer
   built on **Motion** ([motion.dev](https://motion.dev), the vanilla-JS sibling
   of Framer Motion). Framer Motion itself is React-only and nexora is
   server-rendered Jinja/vanilla-JS, so Motion was loaded via a pinned + SRI'd
   jsdelivr `<script>` (matching the B10 CDN convention). It changes **no
   reporting logic** — it only observes the DOM the builder already renders — so
   the `data-testid`-keyed tests are unaffected, and it fully respects
   `prefers-reduced-motion` and degrades to a static page if the CDN is blocked.
2. **AI-assistant design doc** (`1546b79`) — `docs/design/reporting-ai-assistant.md`,
   a design (not a plan) for an in-page NL→report / NL→SQL / NL→stats assistant
   that routes every model output through the **existing** sqlglot gate + RO
   logins + audit. Ends with 5 open decisions that gate any implementation plan.

Verified the animations **live on INT** (logged in as `ben.streich` via
`/dev/login`): Motion loaded, **0 console errors**, a report runs against real
PDQM data, modals spring in. Screenshots in `var/screenshots/reporting_anim_*`
(gitignored).

## What shipped

### 1. Animations (`e58a9a7`)

| File | Change |
|---|---|
| `templates/js/_reporting_anim_js.html` | **NEW** — the Motion animation layer (entrance, row-reveal, view fade, modal spring, button hover/press, field-list stagger) |
| `templates/reporting.html` | Pinned `motion@12.40.0` `dist/motion.js` `<script>` with SRI `sha384-pEZauOIyg+epFndlKew0sgl5yX3MHgf+30BAvpAlckfutfh4WwijcDbz6xua1VjD`; a no-FOUC head init script that adds `.rp-anim` unless `prefers-reduced-motion`; the `_reporting_anim_js.html` include |
| `static/css/reporting.css` | `.rp-anim` entrance pre-hide (3 columns) + a reduced-motion override |
| `CHANGELOG.md` | `[Unreleased] → Added` entry |
| `docs/howto/reporting.md` | "Motion" note under *What the page does* |

Behaviour: the three columns rise + fade in (staggered); after **Run** the first
~40 result rows stream in; chart/pivot containers fade on switch; the SQL-ack /
Share / Schedule modals spring in (backdrop fade + dialog scale-up); buttons and
toggles lift on hover and settle on press; field-list items stagger on
(re)population but stay instant while a search filter is typed.

Design notes:
- The BI logic (`_reporting_js.html`, `_reporting_viz_js.html`) is an IIFE with
  no exposed hooks. Rather than edit it, the animation layer uses
  **MutationObservers** on `#rpResults`, `#rpChart`/`#rpPivot` (`hidden` attr),
  the `.reporting-modal`s (`hidden` attr), and `#rpFieldList`, plus Motion
  `hover`/`press` on buttons. Removing the file restores the old behaviour 1:1.
- No-FOUC: a head inline script pre-hides the 3 columns via `.rp-anim` only when
  motion is allowed; Motion's inline opacity overrides the CSS, and the class is
  dropped on entrance-finish (plus a 2.5s failsafe).
- **No deploy.yml change** needed: the new partial is under `templates/`
  (runtime), Motion is CDN-loaded (no local file).

### 2. AI design doc (`1546b79`)

`docs/design/reporting-ai-assistant.md` — `docs/` is `/XD`-excluded from deploy,
so it's dev-side only. Highlights:
- **Two safe surfaces:** A) NL → report-definition (SQL-free, whitelist-validated,
  keeps `reporting.scope.process.*` row-scoping); B) NL → T-SQL (always shown
  first → copy / insert-into-editor / gated run).
- **Four tiers:** single-shot → **agentic tool-loop with self-repair** (the
  recommended core) → RAG/glossary grounding → semantic/metrics layer.
- **Providers:** Azure OpenAI (tenant-resident, likely compliance default) vs
  Claude API (quality); server-side key (no CSP change); explicit egress table
  (schema-only by default; result rows gated behind `reporting.ai.explain_data`).
- **nexora wiring:** `nx_lib/reporting/ai.py` + `ai_tools.py`,
  `POST /api/reporting/ai/ask`, `reporting.ai.use|sql|explain_data` perms,
  `dbo.ReportingAiAudit` — with the **execution** path 100% reused
  (`sandbox.validate_select`/`wrap_with_cap`, RO engines, audit).
- A deterministic `compute_stats` (pandas/scipy) tool for exact analytics.
- A 4-phase roadmap (Phase 1 = NL→SQL into the editor only, no auto-run).

## Owner actions

1. **Push `feature/2.5.63` and open the PR `→ main`** (this session is
   commit-only). HEAD is ~57 commits ahead of `origin/main`.
2. **Decide the 5 open questions** in the design doc §13 before any AI plan:
   provider (Azure vs Claude), whether result rows may be sent to the model,
   primary audience, starting source scope, glossary ownership.
3. The dev server started this session (`nx -u`, PID was 27288, port 8000) may
   still be running — stop with `nx -d` if you don't want it up.
4. **(Still carried from Phase 4, unrelated to this work)** provision the two RO
   SQL logins (`DB_REPORTING_RO_*`, `DB_REPORTING_OCTO_RO_*`) and wire the
   scheduled-reports Task Scheduler task. See the Phase-4 handoff.

## Gotchas & notes

1. **New CDN dependency:** Motion `12.40.0` from jsdelivr, pinned + SRI. CSP
   already allows `https://cdn.jsdelivr.net` in `script-src` (and `'unsafe-inline'`
   for the inline layer). If a future jsdelivr/Motion change is wanted, re-pin and
   recompute the SRI hash.
2. **e2e not run this session.** The change is additive (no testid/behaviour
   change) and was manually verified live, but the reporting e2e suite
   (`tests/e2e/test_reporting_*`) was not run — worth running before merge.
3. **GitNexus MCP was not connected**, so CLAUDE.md's "impact analysis before
   editing" was by hand; edits were confined to the reporting templates/CSS + one
   new partial + docs (no Python symbols touched).
4. The `â€"` mojibake in the **"Generali — PDQM Report"** source label seen in
   the screenshots is **pre-existing seed data**, not from this change.
5. Screenshots are under `var/screenshots/reporting_anim_*` (gitignored, not
   committed): `entrance_frame`, `settled`, `results`, `modal`.

## How to verify

```powershell
# start INT + log in for browser testing
& C:\dev\nexora\bin\nx.ps1 -u
# then drive a browser to /dev/login/<intuser> -> /reporting (Motion loads,
# entrance staggers, Run streams rows, modals spring). Reduced-motion users and
# a blocked CDN both get a static, fully-functional page.
```

```bash
# (recommended before merge) reporting e2e
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_viz.py tests/e2e/test_reporting_save.py \
  -o addopts="" -p no:cacheprovider -q
```

## Resuming in a fresh session

Point the new session at this handoff. The branch is the source of truth (local,
unpushed). Two natural next steps: (a) the **owner actions** above (push + PR),
and (b) if pursuing the AI assistant, answer the design-doc §13 decisions and ask
for a **Phase-1 implementation plan** (NL→SQL into the editor, reusing the gate +
audit). `CHANGELOG.md` keeps the animation entry under `[Unreleased]`.
