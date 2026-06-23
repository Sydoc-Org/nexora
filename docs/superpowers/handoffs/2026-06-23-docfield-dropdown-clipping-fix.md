# Handoff — Workitems doc-field dropdown: hidden under results table + scrollbar-close fix

**Date:** 2026-06-23 (afternoon) · **Branch:** `feature/2.5.63` · **97 commits ahead of origin (98 after this handoff)** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-23-prepared-import-button-extra-fields-plan.md` (same-date; a `/write-plan`-only session — its plan worktree is still OPEN and unrelated to this fix, see "Untracked / left for owner").
**Durable context in auto-memory:** `reference_nx_rise_stacking_trap` (NEW — the headline fix), `project_ms02_docfield_columnar`, `project_flask_template_cache`, `reference_dev_server_global_python`, `feedback_caveman_speak`, `feedback_remote_commit_only`.

## TL;DR

- **User report:** on the MS02 workitems page they could not find/search the "Person ID" (PID) doc-field, and the field dropdown "could not scroll further down."
- **Two findings, neither was the seeding.** (1) PID **was** correctly seeded and searchable all along — the field just sat far down the list and the running server was serving a **stale in-memory `SimpleCache`** of the field list (cleared by restarting `nx`). (2) The real bug: the field dropdown's lower entries (incl. "Person ID") were **painted underneath the results table** — a CSS stacking-context trap, not a scroll/clip problem.
- **Root cause of the dropdown bug:** `.nx-rise*` card entrance animations used `animation-fill-mode: both`, which holds the final `transform: none` as a resolved **identity matrix** → still a stacking context → the dropdown's `z-index` was trapped inside the filter card and the next `.nx-rise` card (the results table) painted over its overflow. Fixed by switching to `fill-mode: backwards` (visually identical; rests at a true `transform: none`). **App-wide fix** — every `.nx-rise` card had this latent trap for any popover that overflowed it.
- **Also fixed:** the field combobox closed on plain `blur`, so grabbing its native scrollbar (on the long "All processes" 35-field list) hid the list mid-scroll. Now it closes on outside-click / Tab / Escape / selection.
- **Verified live on INT** by driving Playwright (dev-login `ben.streich`, process `sydoc.05_PDBS`): all 6 PDBS fields incl. "Person ID" render and the dropdown paints **over** the results table. **Not pushed** (remote / commit-only).

## This session's commits

```
29bdc15  fix(workitems): doc-field dropdown items hidden under results table
```
Plus the `docs(handoff)` commit this step creates.

## What shipped

| Area | File | Change |
|---|---|---|
| **Stacking-context fix (headline)** | `static/css/nexora-ui.css` | `.nx-rise` / `.nx-rise-2` / `.nx-rise-3`: `animation-fill-mode: both` → `backwards` (+ comment). Removes the lingering identity-matrix transform so overflowing popovers paint above the next card. |
| **Combobox close behaviour** | `templates/js/_workitems_overview_js.html` (`initDocFieldCombobox`) | Stop closing on `blur`; close on document `mousedown` outside the wrapper + `keydown` Tab/Escape; item-select still closes. Lets the user drag the dropdown's scrollbar without it vanishing. |
| **Changelog** | `CHANGELOG.md` | `[Unreleased] → Fixed` entry covering both root causes. |

## Next steps (ordered)

1. **Owner: push** `feature/2.5.63` (98 commits unpushed after this handoff). Not done here (remote / commit-only).
2. **PROD:** nothing special — pure front-end (CSS + a Jinja JS partial). No migration, no dep, no env. The CSS change ships in the normal robocopy mirror.
3. **Unrelated, still open:** the prior handoff's `/write-plan` worktree (`.claude/worktrees/plan-prepared-import-button-extra-fields`, branch `plan/prepared-import-button-extra-fields`, plan commit `7c5b5d4`) is the **execution vessel** for the prepared-docs import button + 5-column Excel feature. Resume that with **`/execute-plan`** — it is NOT part of this fix.

## Gotchas & notes (READ)

- **`.nx-rise*` MUST stay `fill-mode: backwards`, never `both`** (`reference_nx_rise_stacking_trap`). `both` holds `transform: none` as `matrix(1,0,0,1,0,0)` (identity) which still creates a stacking context, burying any absolutely-positioned popover that overflows the card under the next `.nx-rise` card. Verify a "clipped dropdown" with `document.elementsFromPoint(x,y)` (the covering element shows on top) and `getComputedStyle(card).transform` (`matrix(...)` vs `none`). Don't add new card-entrance animations whose **resting** state is a transform.
- **The "PID not searchable" half was a red herring** — `SearchConfig` for `sydoc.05_PDBS` has `ClientCode='ms02'`, `col_pid='DossierNummer'`, and the `pid → "Person ID"` label all seeded; the columnar resolver returns the right workitem. The dropdown just caches its field list in **`SimpleCache` (per-process, 1 h TTL)**, so after a `SearchConfig` change you must **restart `nx`** (or wait out the TTL) — same class as the Jinja template cache (`project_flask_template_cache`). Migrations run out-of-process so they can't bust the running server's cache.
- **Search label vs detail label differ on purpose:** the search dropdown shows **"Person ID"** (`dbo.search_field_labels`, FieldKey `pid`) while the detail view shows **"PID"** (`dbo.IndexFieldMappings`, TargetKey `PID`). Not a bug; offered to align but left as-is.
- **Headless Chromium uses 0-width overlay scrollbars**, so a real classic Windows scrollbar can't be clicked in Playwright. The scrollbar-close bug was verified by reproducing its *mechanism* (focus-loss with no mousedown) rather than a literal scrollbar drag.
- **Restart `nx` after editing the JS partial** (`project_flask_template_cache`) — it's a server-rendered Jinja include. The CSS is a static file (no template cache) but the **browser** caches it: a real user needs a **hard reload (Ctrl+F5)** to pick up the `nexora-ui.css` change.

## Untracked / left for owner

- **`scripts/new-process.py`** — still-untracked `StatConfig`-insert helper, a known background-agent stray; harmless (dev-side, excluded from the deploy mirror). User chose to **keep** it this session. Not committed.
- The `.claude/worktrees/plan-prepared-import-button-extra-fields` worktree (+ its `plan/…` branch) from the prior handoff is intentionally still open as the `/execute-plan` vessel.
- `var/handoff-pending` points at this file (gitignored — not committed).

## How to verify

```powershell
# Restart first (server-rendered JS partial; clears the field-list SimpleCache):
& C:\dev\nexora\bin\nx.ps1 -r

# Browser (dev-login ben.streich), process = sydoc.05_PDBS, open the Document Fields dropdown:
#   all 6 fields show incl. "Person ID", and the dropdown paints OVER the results table.

# CSS fix is in place:
Select-String static/css/nexora-ui.css -Pattern 'nx-rise .* backwards' -Quiet   # True (3 rules)

# Combobox no longer closes on blur:
Select-String templates/js/_workitems_overview_js.html -Pattern "addEventListener\('blur'" -Quiet  # False
```
(No unit/e2e suite added — this is a CSS + DOM-interaction fix verified via Playwright by hand. Existing suites untouched.)

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). This fix is **done and committed** (`29bdc15`); the only open thread is the **separate** prepared-docs import plan — resume that with **`/execute-plan`**.

**Same-date tie-break:** several handoffs share `2026-06-23`. If `/reset-session` auto-picks the wrong one, target this file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-23-docfield-dropdown-clipping-fix.md`.
