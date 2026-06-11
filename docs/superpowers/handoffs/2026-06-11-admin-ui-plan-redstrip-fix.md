> ⏩ **Superseded** — a newer handoff exists for the same date:
> `docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-plan.md`
> Use `/reset-session docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-plan.md` to resume.

# Handoff — Admin nexora-ui migration plan + Generali red-strip fix

- **Date:** 2026-06-11
- **Branch:** `feat/admin-ui-integration` — a **git worktree** at
  `.claude/worktrees/admin-ui-integration`, branched off `feature/2.5.63` @ `427f179`.
  **Entire branch unpushed** (no upstream; 2 commits on top of the base). Commit-only — the
  owner reviews, merges into `feature/2.5.63`, and pushes.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-ai-fixes-plan-staging-migrations.md`
  (same date — that one covers the reporting AI-fixes plan on `feature/2.5.63`).
- **This session's commits (oldest → newest):**
  - `874814a` fix(ui): hide empty modal error flash beaten by Tailwind v4 layers
  - `4556579` docs(plans): admin section nexora-ui integration plan

---

## TL;DR

1. **Generali "red strip" bug fixed (`874814a`).** The empty pink banner in the add/edit
   modals (user's screenshot, "Eintrag hinzufügen") was the Tailwind-v4 cascade-layer trap:
   the CDN emits `.hidden` inside `@layer utilities`, which always loses to the unlayered
   `.nx-flash { display:flex }` — so the empty error banner rendered permanently. Affected
   **pdqm, baseservices, projectmanagement, generali-reporting** (and additionalservices,
   which showed an icon-only strip). Fixed in CSS + 4 templates + 4 JS partials.
2. **Admin → nexora-ui migration plan written (`4556579`), NOT executed:**
   `docs/superpowers/plans/2026-06-11-admin-nexora-ui-integration.md` — 11 tasks converting
   all 7 admin pages off the legacy `admin-tokens.css` precursor (`--a-*`/`.admin-*`) onto
   `.nx-*`, per the user's "should all be in unison".
3. **Verification was harness-based, not live e2e** — this worktree has no `env/INT.env`
   (gitignored secret; the session sandbox can't copy it in), so the dev server can't run
   here. The CSS mechanism was proven both ways in a real browser against the real CDN +
   real stylesheet (see "How to verify"). **e2e from the main checkout is still owed before
   push.**

## What shipped (by file)

| Area | Files | Change |
|---|---|---|
| **Design system** | `static/css/nexora-ui.css` | `.nx-flash.hidden { display:none }` re-assertion (same pattern as the `pl-10` fix `0627674`). |
| **Generali modals** | `templates/generali_{pdqm,baseservices,projectmanagement,reporting}.html` | Empty `#addModalError`/`#modalError` divs normalised to the additionalservices pattern: `role="alert"` + `<i>` icon + `<span id="addModalErrorText">` (reporting: `modalErrorText`). All ids/`data-testid`s preserved. |
| **Paired JS** | `templates/js/_generali_{pdqm,base_services,project_management,reporting}_js.html` | Error text now written to the inner span (`errTextEl.textContent = …`); `hidden` still toggled on the banner div. Edit-modal `errEl` (= `#editError`) deliberately untouched — plain `<p>`, no display-class conflict. |
| **Docs** | `CHANGELOG.md` | `[Unreleased] → Fixed` entry for the strip. |
| **Plan (new)** | `docs/superpowers/plans/2026-06-11-admin-nexora-ui-integration.md` | 11-task migration plan (details below). |

### The admin plan in one paragraph

Recon (4-agent workflow) established: admin pages are **not** on nexora-ui — they ride the
phase-1 precursor `admin-tokens.css` whose `--a-*` token *values* are identical to `--nx-*`,
so migration is mostly mechanical. Plan: (T1) new slim `static/css/admin.css` keeping
admin-only classes (`admin-empty`, `log-method/status`, `health-*`, overview launcher cards,
toggles, log presets) re-based on `--nx-*` so ~40 JS injection sites stay untouched; (T2)
rewrite `_admin_helpers.html` macros to emit `.nx-*`; (T3–T9) per-page conversion
(overview → orgs → sessions → logs → maintenance → user-detail → access-control) incl.
nx-card modals and `.nx-tabs`; (T10) admin pages stop loading `admin-tokens.css` (file
survives **only** for `profile.html`); (T11) changelog + full-suite verify. Hard invariants
documented: 40+ `data-testid` e2e selectors, element ids, `perm_*` radio names,
`.modal-content` JS queries, `hidden/opacity-0/scale-95` toggle mechanics. Bonus: fixes the
permission drawer + user-detail confirm dialog rendering white in dark mode today.

## Next steps (ordered)

1. **Verify live + run e2e from the main checkout** (`C:\dev\nexora`, has venv + env):
   `python scripts/test_db_reset.py` → `python -m pytest tests/e2e -q`; open a Generali
   add-modal as a generali user and confirm no strip + error message still appears on empty
   submit.
2. **Merge `feat/admin-ui-integration` → `feature/2.5.63`** (fast-forward-ish; base is
   `427f179`, files disjoint from the AI-fixes work) and push. Then prune the worktree.
3. **Execute the admin plan** — start at
   `docs/superpowers/plans/2026-06-11-admin-nexora-ui-integration.md` **Task 0 (baseline)**.
   Use superpowers:subagent-driven-development or executing-plans; per-page commits as
   listed in the plan.
4. Long-tail follow-ups recorded in the plan: migrate `profile.html` then delete
   `admin-tokens.css`; delete `templates/admin/archive/` + `modals/_user_modals.html`
   (dead code) in a cleanup PR.

## Gotchas & notes

- **Tailwind v4 cascade-layer trap (now bitten twice — `0627674`, `874814a`):** unlayered
  custom CSS always beats the CDN's layered utilities at equal specificity. Never let a
  utility fight an unlayered `.nx-*`/custom class for the same property; re-assert at
  `.custom.utility` specificity in the stylesheet owning the custom class. A blanket
  unlayered `.hidden { display:none !important }` was considered and **rejected** — it
  would break responsive `hidden md:flex` patterns.
- **`generali_reporting` uses different ids** (`modalError`/`modalErrorText`,
  `showModalError()` helper) than the other three (`addModalError`/`addModalErrorText`) —
  mind this if touching those modals again.
- **Worktree has no secrets:** `env/*.env` are gitignored and the session sandbox blocks
  reading outside the worktree, so `nx -u` / pytest-e2e can't run here. Workaround used: a
  static harness (`var/ui-harness/red-strip.html`) loading the **same** Tailwind CDN tag +
  `static/css/nexora-ui.css` + the real modal markup, served via `python -m http.server
  8765`, driven with Playwright MCP (`file://` is blocked; background `http.server` gets
  reaped after idle — just restart it).
- **Line-ending pre-commit hook** normalised CRLF and aborted the first commit attempt —
  re-`git add` + re-commit passes (known behaviour).
- `SQL_SYNC_SKIP=1` used on commits (INT migration hooks; standard on this machine).
- Recon details (full admin route/template/JS inventory, risks) live in the plan's Context
  section; the 2026-06-03 nexora-ui handoff
  (`2026-06-03-app-wide-ui-redesign-nexora-ui-handoff.md`) documents the original redesign
  series this builds on.

## Untracked / left for owner

- `var/ui-harness/red-strip.html` + `var/screenshots/red-strip-fixed-{clean,error-state}.png`
  — gitignored verification artifacts, kept in the worktree for review.
- Auto-memory updated: `project_admin_ui_worktree.md` (worktree state + the layer-trap rule).
- Nothing else uncommitted; `git status` is clean.

## How to verify

```powershell
# Mechanism proof (works inside the worktree, no env needed):
python -m http.server 8765 --bind 127.0.0.1   # from the worktree root
# browse http://127.0.0.1:8765/var/ui-harness/red-strip.html
#   → no pink strip; getComputedStyle(addModalError).display === 'none'

# Real-app proof (main checkout only):
.\bin\nx.ps1 -r ; nx -u -b --loginas:ben.streich
# /generali/pdqm → "Eintrag hinzufügen" → no strip; submit empty → red banner with icon+text
python scripts/test_db_reset.py
python -m pytest tests/e2e -q            # owed — not run this session (no env in worktree)
```

## Resuming in a fresh session

Read this handoff, then pick up at **Next steps 1–2** (verify + merge/push), or jump straight
into the admin migration via the plan at
`docs/superpowers/plans/2026-06-11-admin-nexora-ui-integration.md` (start: Task 0).
⚠️ Two handoffs share 2026-06-11 — if `/reset-session` picks the AI-fixes one, target this
file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-11-admin-ui-plan-redstrip-fix.md`.
