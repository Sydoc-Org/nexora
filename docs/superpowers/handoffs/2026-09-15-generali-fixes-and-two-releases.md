# Handoff — two Generali dashboard fixes, the #332 audit checks, and two releases

**Date:** 2026-09-15 · **Branch:** `docs/handoff-2026-09-15`, cut from `main`
@ `3e1d9361` · everything below is **merged, released and verified on PROD** ·
commit-only, the owner pushes.

**Prior handoffs:**
[`2026-09-14-billing-sources-and-reporting-ui.md`](2026-09-14-billing-sources-and-reporting-ui.md)
(this session's own earlier half) and, for the environments,
[`2026-09-14-dev-staging-envs-shipped.md`](2026-09-14-dev-staging-envs-shipped.md)
(benstreich).

## TL;DR

1. **The deploy contract changed under us mid-session** (#338, benstreich).
   `main` no longer deploys PROD — it deploys **staging**. Only a `v*` tag
   deploys PROD. Everything below about "merged" vs "live" follows from that,
   and it is the single most important thing to carry forward.
2. Two Generali dashboard fixes shipped: a blank page when a date box was
   empty (#346), and chart hover / tooltips (#350).
3. #332's two audit checks are written (#343). Its other two items are not,
   and an earlier handoff wrongly implied otherwise — corrected.
4. PROD is on **v3.2.7** (`3e1d936`). Two releases were cut this session.

## What shipped (oldest → newest)

| Merge commit | What | Issue | Released in |
|---|---|---|---|
| `52f70c11` | Fireflies over the wizard, rail label alignment, hint spacing | #336 | v3.2.5 |
| `300f8d97` | Perm-audit: dormant + cross-customer source grants | #332 | v3.2.5 |
| `41029108` | Generali dashboard: default the date window instead of a 400 | #346 | v3.2.6 |
| `ff4a81c4` | Generali dashboard: chart hover + themed tooltips | #350 | v3.2.7 |

Releases: `341e25d` = **v3.2.6**, `3e1d936` = **v3.2.7** (PROD, verified by
build stamp and a 200, not by the green badge).

## The environment change — read this first

Three hosts now, and **the URL prefix differs**:

| env | URL | tracks |
|---|---|---|
| dev | `https://dev-nexora.sydoc.ch/login` | last push to any branch **except** `main` |
| staging | `https://staging-nexora.sydoc.ch/**nexora**/login` | `main`, plus a 01:30 nightly rerun |
| prod | `https://nexora.sydoc.ch/**nexora**/login` | the newest `v*` tag |

dev runs as `INT` so it has **no** `/nexora` prefix; staging and prod both do.
`staging-nexora.sydoc.ch/login` returns **404**, which looks exactly like the
site being down. It is not — I made that call once and was wrong.

Three consequences that bit during this session:

- **A push to `main` deploys staging, not dev.** dev often holds a stale topic
  branch rather than the newest code.
- **The footer version is not enough to answer "is my fix live".** Staging and
  PROD both read `v3.2.6` while running different commits. Only the build stamp
  is honest.
- **One self-hosted runner serves everything.** The v3.2.7 PROD deploy sat
  queued ~10 minutes behind a colleague's branch push. Do not promise a time.

## Traps worth carrying forward

- **A release conflicts every open branch.** Folding `[Unreleased]` into a dated
  section put PR #348 into CONFLICTING, and git's auto-merge silently filed my
  changelog entry **inside the new release block** — claiming a fix shipped in a
  tag it was not in. After merging `main` in post-release, check *where* the
  entry landed.
- **Generated files are never hand-merged.** `translations/*.po|mo` and
  `messages.pot` conflicted; took `main`'s side and re-ran
  `pybabel extract` → `update` → `compile`.
- **Removing a translated string desyncs babel.** `test_translations.py` fails
  until the catalogues are regenerated.
- **The preview pane scales the page**, so a scaled screenshot made a dark
  tooltip look white. Sample painted canvas pixels (`getImageData`) or use
  layout values, never judge colour from a screenshot.
- **A local full-suite run can show red when the code is fine.** Two rate-limit
  tests (`test_rate_limit_429_for_unauthenticated_requests`,
  `test_verify_2fa_rate_limit_eventually_429`) fail in a long single-process run
  and pass both in isolation and on CI. Limiter state leaks across the run.
- **`uv` is not in `.venv`** — it is at `C:\Users\GRR\.local\bin\uv.exe`.
- Commit hooks shell out to bare `python`, which is the Store stub. Prefix with
  `PATH="/c/Users/GRR/dev/nexora/.venv/Scripts:$PATH"`.

## Open issues, as they actually stand

1. **#329 — billing sources.** All six live and matching the workbooks. Waiting
   only on the owner walking the numbers through with whoever invoices. A check
   sheet was produced (settings per report + expected figures); it was sent as a
   file, **not** attached to the issue — worth posting there if it is wanted.
   Two sources will silently give the wrong answer if the time range is used:
   **Neuzugänge** (its only date is `Abfragedatum`, the query date) and
   **Posteingang** (its dates are rescan/deletion; the month is a `contains`
   filter on the text `ExportDatetime`).
2. **#332 — reporting source grants.** Item 2 done (#343). Item 1 needs whoever
   granted `Sydoc User` the MediaMarkt source; item 3 (the rule for granting a
   `table` source to a customer profile) is unwritten. **Do not assume more has
   shipped than has** — grep `scripts/perm-audit.py`.
3. **#330 — Privera Mailbestellungen.** Owner is asking Privera whether they
   want the per-branch split. No code until they answer.
4. **#341 — external API N+1** (benstreich, new). He wrote the proposal
   himself; reads as his to build.
5. **#323 — Eddard bug** (benstreich). Diagnosed but **deliberately left for
   him** at the owner's request. Cause: `fireCaption()` at
   `static/js/reporting_simple.js:538` sits after the saved-layout branch's
   `return` at `:518`, so it never runs; `setAskEddard()` at `:489` is before
   it, which is exactly why "Ask Eddard" is the one module that works.
6. **#260 — legal pages.** Owner has set this aside twice.

**#267 (three environments) was closed** — superseded by benstreich's #338.

## Gotchas and notes

- **Release timing is not urgent here.** v3.2.7 went out mid-morning rather
  than off-peak at the owner's instruction, and the owner was explicit that
  nothing depends on a fix landing today rather than next week. The off-peak
  preference exists because a restart interrupts people, not because anything
  is waiting on it. Do not manufacture urgency around shipping.
- `https://nexora.sydoc.ch/` (no path) redirects to **`http://`**`…/nexora` —
  an insecure downgrade on a public host. Untouched, probably ngrok
  terminating TLS. Worth a look; no issue filed.
- `TenantPages.PageType` is constrained to `list | crud | custom`, with a
  schema comment saying "dashboard/report arrive later". The owner says the
  admin control panel covers this; **do not file an issue for it** (asked
  explicitly).
- Three copies of the themed-Chart.js-tooltip block now exist
  (`reporting_viz.js`, `reporting_simple_chart.js`, the generali dashboard
  partial). A shared helper in `nx_core.js` is the obvious home; deliberately
  not done inside a "fix the hover" request.
- A background task chip is pending: **reporting page loads three stylesheets
  twice** (`nexora-ui.css`, `all.min.css`, Google Fonts), with the second
  `nexora-ui.css` landing *after* `reporting.css` in the cascade.

## How to verify

```bash
# what each environment is really running (no login needed)
curl -s https://nexora.sydoc.ch/nexora/login        | grep -oiE "nexora v[0-9.]+|[0-9a-f]{7}, 2026-[0-9-]+"
curl -s https://staging-nexora.sydoc.ch/nexora/login | grep -oiE "[0-9a-f]{7} \([^)]*\)"
curl -s https://dev-nexora.sydoc.ch/login            | grep -oiE "[0-9a-f]{7} \([^)]*\)"

# locally
.venv\Scripts\python.exe -m pytest tests --ignore=tests/e2e -q   # see the rate-limit caveat above
```

PROD should read `nexora v3.2.7 · 3e1d936, 2026-09-15`.

## Untracked / left for the owner

Nothing. The working tree is clean apart from this handoff. Scratch scripts
stayed in the session scratchpad; the #329 check sheet was delivered as a file
and is not in the repo.

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-15-generali-fixes-and-two-releases.md`
— several handoffs share the 2026-09-14/15 dates, so name the file. Start from
"Open issues, as they actually stand".
