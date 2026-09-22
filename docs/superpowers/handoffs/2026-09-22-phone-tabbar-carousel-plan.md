> **SUPERSEDED — a newer handoff shares this date.** Start at
> [`2026-09-22-two-prod-releases-and-a-staging-error.md`](2026-09-22-two-prod-releases-and-a-staging-error.md).
> The plan this file points at has since been executed in full, and two releases have
> been merged to `main`. Kept for history.

# Handoff — phone bugs measured and fixed, carousel planned

**Date:** 2026-09-22 · **Branch:** `feat/354-phone-tabbar` · **55 commits ahead of `main`**,
**7 unpushed** · **commit-only (remote)** — nothing pushed, no PR touched, no tag.

**Prior handoff:**
[`2026-09-22-phone-view-fixes-resume-here.md`](2026-09-22-phone-view-fixes-resume-here.md) — the
session that ran before this one, same date. Read it for the phone effort's history.

## TL;DR

- **The phone blind spot is closed.** `env(safe-area-inset-*)` cannot be overridden, so every
  emulator reported 0 and a whole class of bug was invisible here. The insets now read through
  `--nx-sa-*` tokens, which *can* be set — so a real iPhone's geometry is reproducible on a desktop.
- **WebKit is installed and it mattered.** The reporting page overflowed **53px in Safari's engine
  at every width and 0px in Chromium**. That is why three reported symptoms went undiagnosed.
- **`scripts/phone-sweep.py` is the new tool**: 13+ pages × 7 iPhones × 2 engines, reporting
  overflow, clipping, sideways-sliding boxes and sub-44px targets.
- **Six phone/Generali bugs fixed**, all measured before and after. **252 sweep runs come back
  clean.**
- **A plan is written and committed** for the tab-bar carousel + tenant picker. **Nothing of that
  feature is built yet** — the next session executes it.

## This session's commits (oldest → newest)

| hash | what |
|---|---|
| `cddb0ef5` | safe-area tokens + `scripts/phone-sweep.py` + `tests/unit/test_safe_area_tokens.py` |
| `b532cacb` | the three confirmed bugs: reporting 53px, `/appearance` + `/profile`, workitems tap targets |
| `bec26cb3` | the reporting app icon back in the phone topbar (the owner asked) |
| `4cd48d8c` | Generali: 80 unnamed controls, month-report overflow, tiny row buttons |
| `ab1b7132` | Generali: stat-card grids single-column on a phone |
| `4cdb496f` | **the plan** — `docs/superpowers/plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md` |

## What shipped

**The measuring problem, and why it was structural.** `env(safe-area-inset-*)` cannot be
overridden — setting it from a stylesheet or the console does nothing, and every emulator reports
0 while a real iPhone reports ~59px top / ~34px bottom. Sixteen use sites across four sheets read
it directly, so every layout bug in that band was invisible outside the physical phone. They now
read `--nx-sa-*` tokens defined once in `nexora-ui.css`. **Rendering is unchanged** — measured
identical at real values in both engines. The `0px` fallbacks are load-bearing: a bare `env()` is
invalid where unsupported, and an invalid custom property makes every `var()` reading it collapse
and drop the declaration, losing the *padding* rather than the inset.

**The second blind spot was the engine.** Playwright's WebKit was never installed. It is now
(`webkit-2104`). `/reporting` overflowed 53px there on all seven devices and 0 in Chromium.

**Six bugs fixed:**

| where | what it was | cause |
|---|---|---|
| `/reporting` | draggable 53px sideways, **Safari only** | `select#rsSort` is 48px with a ~132px longest `<option>`; a `<select>` reports that intrinsic width as scroll overflow even at `opacity: 0`, and WebKit propagates it to the document. `overflow: hidden` on `.rs-sort-wrap`. |
| `/appearance`, `/profile` | 37px / 13px sideways at 375 | `grid-template-columns: 1fr` takes min-content as its automatic minimum. Now `minmax(0, 1fr)` + `min-width: 0`. |
| `/workitems` | 40 checkboxes at 24px, 40 toggles at 32px, "Advanced" at 43 wide | all 44px now; **row height 289→321px, ~11% fewer rows** — the trade is named in the CSS. |
| reporting topbar | app icon missing on a phone | it had been hidden deliberately; the owner wanted it back and it fits with 16px to spare. |
| Generali ×9 pages | **80 controls with no accessible name** | labels are `<span class="hidden sm:inline">` and Tailwind's `sm:` starts at 640px, so every phone gets an icon-only button with nothing to announce it. Row edit/delete were unnamed at *every* width. |
| Generali month report | draggable 11–45px on every iPhone | **not a grid bug.** German compounds "On-Time Rate" into "Pünktlichkeitsquote", one unbreakable 19-char word. Stat grids are single-column on a phone now. |

**The aria fix paid twice.** `nexora-ui.css` already grants `min-width: 44px` to
`.nx-btn[aria-label]` — "an aria-label is a reliable signal for icon-only, so nothing gives it
width". Naming the controls fixed their tap targets for free. All the strings reused existing
msgids, so there was **no translation work**.

## Next steps

1. **Execute the plan** —
   [`docs/superpowers/plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md`](../plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md).
   Start at **PHASE 1, Task 1** (a failing test that the bar shows the first three pages).
   The design is deliberately small: because the owner chose "active page in the middle", the three
   rendered slots *are* `[prev, active, next]`, so the carousel is a **Jinja slice** — no clipped
   track, no transform, no CSP work, **no JavaScript**, and `swipe_nav.js` is not modified at all.
   The tenant picker needs no route and no new session key: `apply_tenant_scope` already turns
   `?tenant=<code>` into `session['tenant_scope']`.
   **Open a GitHub issue first** and put its number in the commits (house rule: never a bare
   `#NNN` — always `#NNN — short description`).
2. **Push.** Seven commits are waiting. A branch push deploys **dev** only. In this session the push
   was blocked by the desktop app's own permission classifier (not git, not the repo), so the owner
   runs it. **A green workflow is not a live deploy** — dev is last-push-wins; confirm with
   `curl -s https://dev-nexora.sydoc.ch/static/css/reporting-console.css | grep -c "native picker it opens"`
   (`1` = live).
3. **Two symptoms still unreproduced** — "dashboards gets cut off half way" and "every page has a
   bit of swipe where the middle content flies around but the page doesn't". The sweep finds
   neither. Best guess for the first: Safari's collapsing URL bar changes viewport height as you
   scroll, and the installed app has no such bar — the one gap the tokens do **not** close. **Ask
   for a screenshot and whether they are in Safari or the installed app.**
4. **Two Generali judgement calls left open** — the dashboard's own stat cards stay two columns (it
   uses a bare `grid-cols-2`, so the new `:has(> .nx-stat)` exception does not reach it) and German
   filter-select text clips by a character or two on the documents page. Neither overflows.
5. **`v3.2.10` is still prepared and waiting** on the owner: merge PR
   [#361 — Phone layout: bottom tab bar and installable app](https://github.com/Sydoc-Org/nexora/pull/361)
   (staging only), then tag (PROD). Ten issues could auto-close if `Closes #362 …` were added to the
   PR body — offered twice, never answered.

## Gotchas & notes

- **`MSYS_NO_PATHCONV=1` in Git Bash** or MSYS rewrites `--pages /reporting` into
  `C:/Users/.../Git/reporting` and every sweep load fails with "Cannot navigate to invalid URL".
  PowerShell needs no prefix.
- **`nx` is not on PATH** — `./bin/nx.ps1` from PowerShell. From Bash it fails on a BOM/parse error;
  use the PowerShell tool. `nx -r` after every template edit (Jinja caches); `.css`/`.js` need only
  a reload.
- **The dev server runs on port 8000**, not 5000.
- **`/dev/login/<username>` works from loopback only** and is how the sweep authenticates.
  `ben.streich` can reach every Generali page.
- **Pre-commit will rewrite your files.** `mixed-line-ending` normalises anything written with LF
  by a Python script and **fails the commit**; `git add` again and re-commit. `ruff-format` does the
  same for `.py`. Both are normal, not errors.
- **`SQL_SYNC_SKIP=1 git commit`** is required here: `sql-migrate-int` cannot import `dotenv` and
  `sql-sync-check` cannot find `mssql-scripter` in the hook's own environment. Unrelated to any
  change in these commits. Never `--no-verify`.
- **gitlint caps the subject at 72 characters** — one commit was rejected for 77.
- **`overflow-wrap: anywhere` beats hyphenation.** It shrinks the intrinsic width, so the browser
  breaks the word anywhere rather than hyphenating; adding `-webkit-hyphens` (which Safari does
  require) changed nothing while `anywhere` stayed. It is `break-word` now.
- **I got the month report wrong first.** Changing `grid-cols-2` → `grid-cols-1 sm:grid-cols-2`
  did nothing, because **#367 deliberately forces that exact utility pair back to two columns on a
  phone** — the change opted the grid into a rule written for filter rows. Check that rule before
  touching any `grid-cols-1 sm:grid-cols-2` in a template.
- **A sub-pixel trap in the sweep, now fixed:** `getBoundingClientRect()` returns fractional widths,
  so a control laid out at exactly 44px measured 43.99 and was reported as too small forever.
  Rounded before comparing.
- **Nothing is red.** No failing suite, no half-finished edit.

## Untracked / left for owner

- **`static/js/header.js` is modified, uncommitted, and is the owner's** — their step-1a swipe
  handler (superseded by `swipe_nav.js`) plus a whole-file reformat their editor did on save, 727
  insertions / 575 deletions for ~30 lines of feature. Nothing formats JS in this repo, so there is
  no agreed style it is conforming to. **Do not commit or discard it.** They must choose: turn off
  format-on-save and keep the diff to their own lines, or land the reformat as its own commit.
  Asked three times, still unanswered.
- **A stray file named `t -L 3`** in the repo root — captured `less` pager help text from a mangled
  command. Junk; delete on their word.
- **No worktree was cut** for the plan, though `/write-plan` normally would: the only uncommitted
  file is that `header.js`, and worktree creation needs per-turn authorisation under the nexora git
  policy. Nothing to clean up.
- No migration, no env key, no generated catalog touched.

## How to verify

```bash
export PATH=".venv/Scripts:$PATH"
./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m pytest tests/integration -q -p no:randomly --no-cov -k generali
```

Last run: unit **1913 passed / 35 skipped**, `test_mobile_nav.py` **52 passed / 2 skipped**,
Generali integration **34 passed**, reporting e2e **107 passed**, translations **11 passed**.

The sweep needs the dev server up (`./bin/nx.ps1 -u` from PowerShell, port 8000):

```bash
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe scripts/phone-sweep.py
```

Pass condition: `side=-`, `slide=0`, `clip=0` on every row. `#fireflyField` losing 5–7px is the
decorative background layer and is expected everywhere.

## Resuming in a fresh session

Read this file, then the plan it points at. **Two handoffs share the date 2026-09-22** — this is
the newer one; `/reset-session docs/superpowers/handoffs/2026-09-22-phone-tabbar-carousel-plan.md`
targets it explicitly.

Also read [[feedback_owner_wants_to_write_the_code]] in memory: as of 2026-09-21 the owner wants to
write nexora code and be taught it. They have since asked for things to be implemented directly
(this whole session was requested that way), so follow what they ask for now rather than either
extreme — but when it is a learning task, explain and review instead of patching.
