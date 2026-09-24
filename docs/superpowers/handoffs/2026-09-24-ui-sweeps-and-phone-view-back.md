# Handoff — UI sweeps, v3.2.14 ready, phone view back on dev

**Date:** 2026-09-24 · **Branch:** `feat/354-phone-tabbar` · **0 unpushed** (pushed; dev runs
it) · commit-only (remote) for this handoff.

**Prior handoff:**
[`2026-09-23-prod-caught-up-on-3-2-13.md`](2026-09-23-prod-caught-up-on-3-2-13.md) — every open
item in it is resolved except the eye-toggle question (see Next steps).

## TL;DR

- **v3.2.14 is merged but NOT tagged — PROD is still v3.2.13.** The owner chose "tonight, after
  hours" and did not push the tag. `main` has since moved past the release, so the tag must name the
  release commit: `git tag v3.2.14 912e88ef` then `git push origin v3.2.14`. Friday 2026-09-25 is
  the carve-out — waiting until the week of 2026-09-28 is fine and arguably better.
- **Two WebKit UI sweeps → 13 issues filed and fixed.** Desktop/narrow-layout fixes are on `main`
  (#381–#384 via #385/#386, plus my own regression #387). Phone-view fixes (#388–#394) and an
  "icons all-or-none per row" change live only on the phone branch.
- **The phone view is back.** The owner "dropped" it in the morning (closed #361/#354/#362–#373),
  then asked for it back hours later. Nothing was ever deleted. `main` was merged into the branch,
  #361 and #354 were reopened (the 12 old bug issues stay closed, their choice), and dev runs it.
  **Never merge #361** — that deploys staging; PROD waits for an explicit decision.

## What shipped

**On `main` (all merged on green, staging deployed):**

| PR | merge | what |
|---|---|---|
| #378 | `2b6fcada` | password reset clears the login lockout + checks its write (rowcount); `nx_core.js` wraps `fetch` so a fetch bounced to `/login` navigates there |
| #379 | `b8e9bb60` | 2FA form sends once; "Failed logins today" counts only 401/429 (all 5 PROD "failures" on 09-23 were double-submits hitting a stale CSRF token) |
| #360 | `da85069b` | docs: table-source granting rule (#332 item 3) |
| #359 | `0b40d350` | docs: 30-key include cap; translations regenerated, never hand-merged |
| #380 | `912e88ef` | **release 3.2.14** (version + `uv.lock` + changelog fold) — the commit to tag |
| #385 | `a5bc43c0` | reporting pages fit a phone (bare `1fr` → `minmax(0,1fr)`, wraps); admin page-head wraps (#381, #382) |
| #386 | `c592eae4` | row actions one line on desktop (#383, #384) |
| #387 | `836c5bc7` | **my regression fix**: #382 used `flex: 1 1 18rem`; in column headers (<768px, `workitems_overview.css`) a basis is a HEIGHT → ~300px gap. Now `flex: 1 1 0; min-width: min(100%, 18rem)` |

**On `feat/354-phone-tabbar` only (dev):**

| commit | what |
|---|---|
| `c81b6534` | merge `main` in (3.2.14 + all of the above). Generated files taken from main and regenerated; 8 phone-only strings refilled; changelog = main's, with the branch's phone entries re-filed under `[Unreleased]` as "… — phone view" |
| `5859d4a7` | merge of the #387 fix branch |
| `761d7deb` | #388–#394: page-head actions wrap; `.nx-stat` wrap with a min-content floor; card tables `overflow-wrap: anywhere` + `td:empty` hidden; Access Control user cell stacked; appearance preview `minmax(0,1fr)`; phone filter dropdowns ellipsis; touch-gated 44px targets (guide TOC, card kebab) |
| `dee257ae` | owner request: stat-card icons **all-or-none per group** — `nx_core.js` adds `.nx-stats--no-chips` when any chip in a group would wrap |
| `c849f7e7` | owner request: Generali Documents had cards inside a same-looking box -- in card mode `.nx-table-wrap` drops its frame (`_header.css`) |
| `071358b9` | owner request: Generali From/To looked "weird" on a phone — flatpickr swapped them for iOS native date fields. `nx_core.js` sets `flatpickr.setDefaults({ disableMobile: true })` once; same input + calendar as desktop (fits 320px) |

**Test branch `feat/phone-post-focus` (dev runs it, `d953175e`)** — cut from the phone branch
after the owner said Generali/ISS users have no phone access yet and asked for a reversible
test: Generali Reporting opens with a "Today" board (per KPI on time / late / both / not
reported yet, "Report now" opens the form with the KPI preset, month on-time rate) and
every `.nx-filter` page folds its filters behind one button on a touch phone. **Undo on dev:**
`gh run rerun 35968313374` (replays the last phone-branch deploy, `42635bf`). **Keep:** merge
it into `feat/354-phone-tabbar`. Ideas 3-5 (one-tap with time, start page, "not delivered")
wait on the owner's survey + the boss — see the memory note on Generali post reporting.
Follow-ups on the same branch: `56555bc3` + `1a35c849` — readable boxes (Today rows two-line, card
labels brighter, form KPI dropdown full-width) and dashboard charts (recipient chart grows per bar,
doughnut legends ellipsised via `Chart.overrides.doughnut`). **Open:** the owner says "Report now"
does nothing on their phone; not reproducible in WebKit/Chromium by tap (form opens, submit saves) —
asked for device/browser and what exactly happens. Dev runs `1a35c84`.

**GitHub housekeeping:** closed #329 (six billing sources live), trimmed #332 to its MediaMarkt
question, closed #388–#394 by hand (the branch never merges, so "Closes" lines don't fire).
Deleted merged branches locally and on origin. New long-lived branch `docs/issue-screenshots`
(images for issues, never merged — see Gotchas).

**Also produced (not in the repo):** a one-page German question sheet for the privacy policy
(`nexora-Datenschutz-Fragen.docx`, sent to the owner for their boss; source in the session scratchpad
only). The long English version is `docs/design/legal-pages-open-questions.md` on
`feat/260-legal-pages`.

## Next steps

1. **Tag PROD when the owner says** — `git tag v3.2.14 912e88ef` + `git push origin v3.2.14`, off
   peak, after the carve-out is safest. Verify by the footer on `nexora.sydoc.ch/nexora/` (v3.2.14,
   build `912e88e`), not by a green workflow.
2. **Rate limiter keys on ngrok's local port** — a spawned task chip ("Fix rate limiter keying on
   ngrok's local port") explains it: PROD `Logs` show every IP as `[::1]:<port>`, so
   `extensions.client_ip` / `hooks.get_ip` (rightmost XFF hop) give each TCP connection its own
   bucket. Account lockout still protects. Not urgent; after the carve-out.
3. **Privacy policy (#260)** — waits on the boss's answers to the question sheet.
4. **#332 item 1** — someone must say whether `Sydoc User` should see the MediaMarkt source.
5. **Eye toggle on reset-password (from the prior handoff)** — never answered; ask them to try a
   private window (password-manager extension theory).
6. **Phone view** — the release decision is still the owner's. Keep merging `main` into the branch
   when main moves.

## Gotchas & notes

- **Owner's own account uses `data-fontscale="sm"` → `body { zoom: 0.9 }`.** In WebKit,
  `getBoundingClientRect` then reports ~1/0.9 sizes (body 433px on a 390px phone). Remove the
  attribute before measuring, or you chase phantom overflow.
- **"Desktop unchanged" claims were checked by pixel-diffing every desktop page** (1440×900)
  before/after. That caught a real desktop change once (`/appearance` chip wrap) — keep doing it.
- **A flex-basis on something that can become a column is a height.** See #387.
- **Git Bash mangles `/reporting` args to Playwright scripts** — prefix `MSYS_NO_PATHCONV=1`.
- **Python rewrites of `CHANGELOG.md` must keep LF** (`newline="\n"`); CRLF trips the
  `mixed-line-ending` hook and a merge commit silently didn't happen once (fixed).
- **`gh pr checks --watch` waits on the dev deploy too**, which queues behind staging. Poll the
  `test` check instead; dev deploy is not a merge gate.
- **`docs/issue-screenshots` must never be merged, orphaned or deleted** while issues link to it
  (#381–#394). It only touches `docs/`, so pushing it deploys nothing.
- **Dev is last-push-wins** — any other branch push takes the phone view off dev.
- Nothing is red.

## Untracked / left for owner

- **`.claude/worktrees/`** — appeared mid-session, not created by this session; left alone.
- Old stash `stash@{0}` (from `fix/259-generali-date-picker`) and the local-only branch
  `docs/handoff-2026-09-15` — owner chose to keep both.
- `t -L 3` was deleted on the owner's word.

## How to verify

```bash
./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m pytest tests/integration -q -p no:randomly --no-cov
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe scripts/phone-sweep.py --engine webkit --pages /dashboard,/reporting
```

Last run on this branch: unit **1944**, integration **857** (after the main merge), sweep 0
sideways/clipped/sliding runs.

Which host runs what:

```bash
for u in https://nexora.sydoc.ch/nexora/ https://staging-nexora.sydoc.ch/nexora/ https://dev-nexora.sydoc.ch/; do
  echo "$u $(curl -s -L --max-time 20 "$u" | grep -oE 'nexora v[0-9.]+[^<]{0,60}' | head -1)"
done
```

Expected: PROD `v3.2.13 · 1b949f9`; staging current `main`; dev `071358b (feat/354-phone-tabbar)` or later.

## Resuming in a fresh session

Read this file first. Memory notes worth re-reading: the phone-view note (reopened, never merge
#361), `reference_issue_screenshots_branch`, `feedback_deploy_only_off_peak`,
`feedback_merge_on_green_without_asking`. The owner likes UI bugs filed as `Phoneview: …` /
`Desktop: …` with just a screenshot and "needs fixing", label `brushup`.
