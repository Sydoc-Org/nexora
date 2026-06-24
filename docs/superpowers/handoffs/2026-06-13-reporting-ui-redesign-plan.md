# Handoff — reporting UI redesign: plan written (ready for /execute-plan)

- **Date:** 2026-06-13
- **Branch:** `feature/2.5.63`. **157 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-13-reporting-two-breakdown-chart-cap-execution.md`
- **This session's commit:**
  - `fff24ad` docs(plans): add reporting-ui-redesign implementation plan
- **No worktree** was created (clean tree, not in a linked worktree) — `/execute-plan` runs in the
  main checkout `C:\dev\nexora`.

---

## TL;DR

1. **Plan written and committed** for the GitHub issue *"Reporting: Upgrade the UI — the UI still
   doesn't really look like the other pages and is messy."* Resume at
   `docs/superpowers/plans/2026-06-13-reporting-ui-redesign.md`.
2. **Scope (decided autonomously):** reskin the whole `/reporting` page onto the existing **nexora-ui
   design system** (`--nx-*` tokens, `.nx-btn/.nx-card/...`) plus light layout tidying — **zero
   feature/behavior/IA change. CSS + markup only. No SQL, no migration, no new strings, no backend.**
3. **Key finding (verified):** the page is already ~70% migrated. `static/css/reporting.css` ends with
   two appended override blocks that **win the cascade** and already tokenize most `.reporting-*`
   rules — so the early hex rules near the top are **dead** (editing them is a no-op). The genuine
   residual defect is the **Simple-pane block** (`.reporting-simple-*`, `.reporting-chartbtn`,
   `.reporting-sqlview pre`, `.rs-chip`, `.reporting-ai-loading`) which sits *after* the appended
   blocks, still on literal hex, and renders wrong in dark mode.
4. **Next:** `/execute-plan` against the plan above — 11 tasks across 5 phases (P0 baseline → P1
   Simple-pane token fix (CSS-only, the real win) → P2 nx-btn/nx-card co-apply (markup) → P3
   conditional layout tidy → P4 verify + CHANGELOG).

---

## What shipped this session

### Planning run (`fff24ad`)

| File | Change |
|------|--------|
| `docs/superpowers/plans/2026-06-13-reporting-ui-redesign.md` | New. Full implementation plan: explore ×3 → dual drafts → adversarial red-team → merge. 11 tasks, 5 phases (P0–P4). |

The plan was produced by the `/write-plan` 7-agent Workflow. **Fable 5 was unavailable** in this
account (the same US-only restriction the autopilot work hit on 2026-06-13). The first run failed all
7 agents with "Claude Fable 5 is currently unavailable"; I edited the workflow script to drop the
`model: 'fable'` overrides so agents **inherit Opus 4.8** (the top available tier) and re-ran — it
completed (~31 min, 781k subagent tokens, 127 tool uses). Every file/CSS-rule/snippet/token/markup
and e2e-selector anchor in the plan was re-verified against the live repo before commit.

**Owner scope question was declined** (the `AskUserQuestion` was dismissed), so per the autonomous
mandate I locked defaults into the plan: *reskin-to-nexora-ui + light tidy*, *whole page in scope*
(phased delivery). These are recorded in the plan's "Decisions locked in" table and "Owner actions".

---

## Next steps

**Primary:** execute the plan — `docs/superpowers/plans/2026-06-13-reporting-ui-redesign.md`

| Phase | Tasks | Files |
|---|------|-------|
| P0 | Task 0 — baseline: green e2e + before-screenshots (light+dark) | read-only + `var/screenshots/` |
| P1 | Tasks 1–3 — token-ize residual Simple-pane hex (the real dark-mode fix; CSS-only) | `static/css/reporting.css` |
| P2 | Tasks 4–7 — co-apply `nx-btn`/`nx-card` on toolbar / AI+SQL panels / 4 modals / Simple result-bar | `templates/reporting.html`, `templates/_reporting_simple.html` |
| P3 | Tasks 8–9 — **conditional** layout tidy (skip if region already clean after reskin) | `static/css/reporting.css` |
| P4 | Task 10 — full verify, shared-admin-page regression guard, CHANGELOG, hand off | `CHANGELOG.md` + verify |

**After this reskin:** push `feature/2.5.63` + open PR → `main` (owner).

---

## Gotchas & notes

- **The cascade is the whole game.** `reporting.css` loads *after* `nexora-ui.css`; both unlayered;
  many `.reporting-*` selectors are defined **twice** (early hex + appended tokenized). **The appended
  (later) one wins** — always search the whole file for a selector and edit its LAST definition.
  Editing a dead early rule is a no-op that wastes a task.
- **Never rename a `.reporting-*` class.** Nine JS partials inject/query them and `_reporting_anim_js`
  selects `.reporting-modal`/`.reporting-modal-box`/`.reporting-btn` for the entrance animation (keep
  hook classes FIRST in the class list). Strategy is **restyle-in-place** or **co-apply** both classes
  on one element — never drop a class.
- **`.reporting-admin*` is a SHARED surface** with `reporting_metrics.html` / `reporting_sources.html`.
  Never edit a `.reporting-admin*` CSS rule; Task 10 screenshots both admin pages to prove no regression.
- **Preserve every `data-testid`/`id`/`name`** — the e2e suite selects on those, so class co-applies
  are safe *because* the testids survive. Don't change the chart-note text `"Too many data points to
  chart"`; don't touch the `.sql-*` syntax-highlight colors (e2e asserts on both).
- **Bogus tokens** confirmed absent in `nexora-ui.css`: `--nx-surface-2`, `--nx-text-muted` (so their
  literal `#fallback` was firing — wrong in dark mode). P1 replaces them with `--nx-accent-tint` /
  `--nx-text-sec`. If you hit `var(--rp-border, ...)`, replace with `var(--nx-border)`.
- **Restart the dev server after markup edits** (P2/P3 markup) — Jinja is process-cached; CSS-only
  edits (P1, 8, 9) only need a hard browser reload.
- **Remote session:** drive Playwright yourself, capture **light AND dark** screenshots (1440 + 375)
  to `var/screenshots/`, and `SendUserFile` before/after pairs. **Stop at `git commit`** — no push, no PR.
- **`SQL_SYNC_SKIP=1`** before commits (INT `SchemaMigrations` CRLF drift) — though this session's
  hooks actually **passed** (INT reachable). Each plan task uses `git commit -m '<subject>' -m '<body>'`
  (the harness pipes nothing to stdin, so `-F -` hangs).
- **Sequencing:** drill-through (Tasks 2–8), show-query-multidim-export Phase 2,
  page-improvement-options, and the **unverified** loading-states plan are queued on the same files.
  Every plan edit is anchored on a unique quoted snippet — whichever lands second re-bases cleanly.
  This reskin never touches `reporting.py`, keeping the conflict surface minimal.

---

## Untracked / left for owner

- Working tree is **clean** — only the plan file was committed. Nothing else staged or stashed.
- **Owner scope confirmation:** the `AskUserQuestion` (redesign intensity / surface scope) was
  declined; defaults locked in (reskin + tidy, whole page, phased). If the owner wants bigger layout
  changes than "tidy + reskin", that's a separate scope — see the plan's "Owner actions".
- **Push + PR:** 157 commits ahead of `origin/feature/2.5.63`. Owner pushes and opens the PR.

---

## How to verify

```powershell
cd C:\dev\nexora

# Plan exists; spot-check anchors that were verified this session:
Get-Content docs\superpowers\plans\2026-06-13-reporting-ui-redesign.md -TotalCount 3
git log -1 --stat fff24ad

# The residual Simple-pane hex (the real P1 target) still on literal hex:
Select-String -Path static\css\reporting.css -Pattern '\.reporting-simple-choice\.is-selected'
# nexora-ui tokens exist; bogus ones do not:
Select-String -Path static\css\nexora-ui.css -Pattern '--nx-accent-tint\s*:'
Select-String -Path static\css\nexora-ui.css -Pattern '--nx-surface-2\s*:'   # expect NO match

# After executing P0/P4, the selector-preservation gate is the full reporting e2e suite:
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -q
```

---

## Resuming in a fresh session

`/reset-session` picks the newest handoff. If another handoff shares today's date, target this file
explicitly:

```
/reset-session docs/superpowers/handoffs/2026-06-13-reporting-ui-redesign-plan.md
```

Then execute the plan:

```
/execute-plan
```

Read the plan before touching code:
`docs/superpowers/plans/2026-06-13-reporting-ui-redesign.md`

Start with **Task 0** (baseline: confirm green e2e + capture before-screenshots in light AND dark) —
the dark-mode Simple-pane shots are the "before" that proves the P1 token fix. Do **not** start a
reskin on a red baseline.
