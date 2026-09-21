# Handoff — the twelve phone issues, and the owner taking over the keyboard

**Date:** 2026-09-21 · **Branch:** `feat/354-phone-tabbar` · **27 commits ahead of `main`**,
0 unpushed · **commit-only (remote)** — nothing merged, no PR touched, no tag.

**Prior handoff:**
[`2026-09-16-phone-ui-and-installable-app.md`](2026-09-16-phone-ui-and-installable-app.md)

**Issues:** [#362](https://github.com/Sydoc-Org/nexora/issues/362) ·
[#363](https://github.com/Sydoc-Org/nexora/issues/363) ·
[#364](https://github.com/Sydoc-Org/nexora/issues/364) ·
[#365](https://github.com/Sydoc-Org/nexora/issues/365) ·
[#366](https://github.com/Sydoc-Org/nexora/issues/366) ·
[#367](https://github.com/Sydoc-Org/nexora/issues/367) ·
[#369](https://github.com/Sydoc-Org/nexora/issues/369) ·
[#370](https://github.com/Sydoc-Org/nexora/issues/370) ·
[#371](https://github.com/Sydoc-Org/nexora/issues/371) ·
[#372](https://github.com/Sydoc-Org/nexora/issues/372) ·
[#373](https://github.com/Sydoc-Org/nexora/issues/373) — all fixed.
[#368 — swipe](https://github.com/Sydoc-Org/nexora/issues/368) — **in progress, owner is writing it.**

## TL;DR

- **Eleven of the twelve phone issues the owner filed on 2026-09-18 are fixed and on dev.**
  Only #368 (swipe navigation) is open, and it is deliberately the owner's to write.
- **The way of working changed on 2026-09-21.** The owner now writes the code and wants to be
  taught the codebase — see [[feedback_owner_wants_to_write_the_code]] in memory. Do not hand over
  finished patches. Point at files, explain the why, review honestly.
- **`static/js/header.js` is uncommitted and not mine.** It holds the owner's working swipe
  handler *and* a whole-file reformat their editor did on save. Read "Untracked / left for owner"
  before touching it.
- The owner is **stressed this week: a carve-out lands Friday 2026-09-25.** They asked to resume
  the learning next week. Do not start anything that needs their attention before then.

## This session's commits (oldest → newest)

| hash | what |
|---|---|
| `e6fb8652` | #372 profile menu reachable, #369 no zoom on focus, #370 themed top strip |
| `a9cc6c58` | #362/#363/#364 workitems phone layout + stage indicator; fixed a false CI failure |
| `30d23333` | #366/#367 card separation + Generali filter grids; #371 Eddard; #373 tab bar recovery |
| `73b00470` | #365 Generali donut legends below the chart |

## What shipped

**#372 — the profile menu was off the side of the screen.** Profile, Appearance, Feedback, Help
and **Sign out** were all rendered and clickable at `left: -176px`. The user row opens an
`<el-menu anchor="right end" popover>`; in the 240px desktop sidebar the card lands beside the row,
but in the full-width bottom sheet there is no "beside". Fixed in `static/css/_header.css`. The two
inset properties need `!important` — the elements library writes the anchor result as an **inline**
style, which no stylesheet rule can outrank.

**#369 — fields zoomed the page in.** Safari zooms when a focused field's font is under 16px and
does not zoom back out. Offenders measured: workitems search 12.5px, `.nx-input` 13px on
`/appearance` and the Generali date pickers, `.profile-input` 14px. Raised at the shared component
in `nexora-ui.css`; the workitems search needed its own rule at matching specificity because the
filter row sets `font-size` at (0,2,0).

**#370 — the strip above the page was stuck dark.** The root cause was not the `theme-color` meta
but the inline `background-color`/`color-scheme` the pre-paint scripts put on `<html>`: written
once before paint, never updated, and with `viewport-fit=cover` the html canvas is what shows
through the safe areas. An inline style beats any stylesheet rule, so this was not fixable in CSS.
Now synced off `html.dark` by a small script in `templates/_app_manifest.html`.

**#362/#364 — workitems chrome.** First row started 809px down an 844px screen. Filter 399→179px,
actions 106→48px, first row 809→532px.

**#363 — the stage indicator** shared one line with the label and the id; now has its own line.

**#366/#367 — card separation.** In dark mode the card border and the dividers *between cells* were
both `#334155`, so a nine-cell Generali document drew nine identical lines. Tokens now, one source
for both themes. Also: twelve templates use `grid-cols-1 sm:grid-cols-2`, and Tailwind's `sm:`
starts at 640px, so phones got one column — 352px of stacked filters on Generali Documents, now
167px. Every affected page re-measured: zero clipped controls.

**#371 — Eddard.** Starter chips were 28px; now 44px full-width rows. Close button and the
answer-depth picker also raised. Nothing in the panel is under 44px.

**#373 — tab bar recovery.** The hidden state is now derived from `document.activeElement` rather
than toggled per event, plus re-checks on `pageshow` and on becoming visible.
**This is not a reproduction** — Chromium fires `focusout` when the focused field is removed,
hidden, or left behind by a navigation (all three checked), so the real trigger is still unknown.

**#365 — donut legends.** Chart.js draws the legend inside the canvas, so a right-hand legend left
~150px for labels and chopped them mid-word. Now below the chart on a phone, boxes grown to 21rem.

**Also, not from an issue:** `#bulk-action-bar` cleared `56px` when the tab bar has been 64px for a
while (now `--nx-tabbar-h`), and error pages scrolled 7px sideways on a phone (axis clipped at the
root in `_errorPages.css`).

**One test changed:** `tests/unit/test_datepicker_styles.py` decided what was a comment by checking
whether a line *starts* with `/*`, `*` or `//`. This codebase indents comment continuations as
plain prose, so a sentence of mine mentioning flatpickr that ended in a comma read as a selector
list and **failed the build**. Comments are stripped as blocks now. Verified still strict: an
unprefixed `.flatpickr-day.selected` rule still fails it.

## Next steps

1. **Do not start work before next week.** The owner asked to resume then (carve-out Friday).
2. **When they return: #368, and they write it.** State of play:
   - **Step 1a is done and correct** — detect a horizontal swipe and log left/right, with a
     `Math.abs(dy) > Math.abs(dx)` guard so a thumb-arc scroll does not fire it.
   - **Step 1b is half-done.** `startedInSideScroller(el)` exists in their working copy but is
     **never called** — it climbs `.parentElement` looking for `scrollWidth > clientWidth`,
     stopping at `document.body` (climbing past body makes every swipe look like it started in a
     scroller, so nothing ever navigates). Remaining: a variable outside both listeners, set it
     from `e.target` at touchstart, bail on it in `handleGesture`.
   - **Step 2** is navigation: the bar's slots are already an ordered, permission-filtered list of
     `<a href>` in `templates/_header.html:403`, so it is "follow the neighbouring link". The
     **More** slot is a `<button>` and must be excluded. Driving it off the bar gives the
     per-organisation behaviour in the issue for free.
   - **Open question they are deciding:** cross-document view transitions
     (`@view-transition { navigation: auto; }`) to hide the reload flash. Measured: TTFB 16–68ms,
     3–9KB over the wire, so the cost is the browser rebuilding the page, not fetching it.
     Supported iOS Safari 18.2+, degrades silently. Two things they were asked to decide: which
     stylesheet / whether to scope to phones, and how to respect `html.nx-motion-reduced`.
3. **Teach, do not patch.** Lessons covered so far: the `nx` CLI (`--routes` gives URL → endpoint →
   file:line), paired filenames, `add_url_rule` instead of route decorators so you grep the URL,
   the template cache (`.html` needs `nx -r`, `.css`/`.js` do not), permissions (route decorator is
   the only real gate; ask whether an empty permission list means nothing or everything), and
   reading CI with `gh run list` / `gh run view --log-failed` instead of the whole log.

## Gotchas & notes

- **The owner's PowerShell has no `grep` and no `rg`** — only `findstr` and `git`. Give them
  `git grep`, which works in both shells and skips `.venv`. See
  [[reference_nexora_shell_environment_traps]].
- **`gh` pages long output into `less`** and the owner got stuck in it, typing shell commands at
  the pager. `gh config set pager cat` if it recurs.
- **Restart after a template edit.** Jinja caches; this cost me two false "the fix didn't work"
  diagnoses this session, both times on `.html`.
- **Rect vs computed px.** Under mobile emulation `getBoundingClientRect` returns scaled pixels
  (~1.09×) while `getComputedStyle` returns CSS px. Compare rect to rect. A 44px min-height reads
  as 48 in a rect.
- **`.rdb-head` is shared** between the dashboard builder and the Report definitions list. My first
  cut of the builder fix changed both; scoped with `:not(.rl-head)`. Caught only because a test
  locator matched two elements.
- **I backed something out this session.** A Chart.js `generateLabels` hook meant to shorten
  over-long donut labels returned items with no text and the legend rendered "undefined". Reverted;
  two long German document types still truncate, and the tooltip carries the full name. Do not
  retry it the same way.

## Untracked / left for owner

- **`static/js/header.js` is modified and not committed.** Two different things are in that diff:
  1. the owner's swipe handler (step 1a complete, `startedInSideScroller` defined but unwired);
  2. **a whole-file reformat their editor did on save** — 727 insertions / 575 deletions for a
     ~30-line feature. Quotes single→double, the historical 4-space wrapper indent removed, lines
     reflowed. The repo's pre-commit hooks format Python (ruff) but **nothing formats JS**, so
     there is no agreed JS style for this to conform to.
  **Do not commit this as-is and do not discard it.** The owner needs to decide: turn off
  format-on-save for this repo and keep the diff to their own lines, or accept the reformat as its
  own separate commit. Ask them.
- **A stray file named `t -L 3`** sits untracked in the repo root — debris from a mangled shell
  command. Junk; delete it once the owner confirms.
- No migration, no env key, no generated catalog touched this session.

## How to verify

```bash
export PATH=".venv/Scripts:$PATH"
./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly
./.venv/Scripts/python.exe -m pytest tests/integration -q -p no:randomly
./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly
```

Last run: unit **1910 passed**, integration **830 passed**, `test_mobile_nav.py` **44 passed,
1 skipped** (the stage-indicator test skips where the seeded workitems carry no stage). Nothing is
red. CI on `73b00470` is green.

For the phone work specifically, measure rather than eyeball — that is what made this whole effort
work. Scratch probes from this session are gone with the session; rebuild them from the numbers
quoted above, which are all reproducible at a 390×844 viewport with `has_touch=True,
is_mobile=True`.

## Resuming in a fresh session

Read this file. Then read [[feedback_owner_wants_to_write_the_code]] — the working arrangement
changed and it is the most important thing on this page. The owner is learning nexora deliberately
so they are not blocked without Claude; your job is to explain and review, not to deliver patches.

`/reset-session` picks the newest handoff automatically; `/reset-session docs/superpowers/handoffs/2026-09-21-phone-issues-swept-and-owner-learning.md`
targets this one specifically.
