> **SUPERSEDED — a newer handoff shares this date.** Start at
> [`2026-09-22-phone-tabbar-carousel-plan.md`](2026-09-22-phone-tabbar-carousel-plan.md).
> The three phone symptoms below were worked after this was written: one was
> reproduced and fixed, two are still unreproduced. This file is kept for history.

# Handoff — START WITH THE PHONE-VIEW FIXES

**Date:** 2026-09-22 · **Branch:** `feat/354-phone-tabbar` · **42 commits ahead of `main`**,
0 unpushed · **commit-only (remote)** — this handoff is committed, not pushed.

**Prior handoff:**
[`2026-09-21-phone-issues-swept-and-owner-learning.md`](2026-09-21-phone-issues-swept-and-owner-learning.md)
— read it too. It carries the working arrangement and the lessons already taught.

## Start here

The owner's instruction for this session, verbatim: **start with the phone-view fixes.**

There are **three symptoms they reported from their own iPhone that were never diagnosed.** Their
words:

> "for the reporting the page is to big some css is off also dashboards gets cut off hlaf way and
> idk every page has a bit of swipe towards it where the middle content flys around but the page
> doesent"

**I could not reproduce any of them**, and the reason matters — do not start by re-measuring in
Chromium and concluding it is fine, which is what I did:

- `env(safe-area-inset-*)` is **0** in Chromium device emulation and real on an iPhone (~59px top,
  ~34px bottom). The tab bar, the wizard footer, the profile menu and the body padding all use
  those values. A layout error there is **structurally invisible** from here.
- Safari is not Chromium. Text metrics differ, so something that fits by a few pixels for me can
  overflow for them.
- The installed home-screen app and a Safari tab differ, especially around viewport height.

**What I asked for and never received: screenshots.** Ask again, and ask *which* they are using —
Safari or the installed app — because that decides the safe-area values. Every previous diagnosis
this whole effort came from a screenshot in a fraction of the time measuring took.

One measurement gap I did close, which is the pattern to copy: every number in this effort had been
taken at **390×844 only**. Re-testing at six real iPhone widths (375–430) found the workitems
toolbar draggable by 13px at 375 while fitting at 390. **Test more than one width.**

## This session's commits (oldest → newest)

| hash | what |
|---|---|
| `db376f0f` | reporting topbar + profile menu panel |
| `b506e0fe` | put "Reporting BETA" back — hiding it was my call and wrong |
| `84264f31` | drop the keyboard-shortcuts row; thumb-size the 4 pages behind it |
| `b95fbecc` | **chore(release): 3.2.10** — version bump, relock, changelog folded |
| `3aa83f91` | nothing scrolls sideways; rail becomes a 3×2 grid |
| `3724d524` | workitems toolbar → grid; found by testing six widths |
| `d9df5e03` | **swipe between views + view transitions** |
| `d16b8f01` | the changelog entry that should have been in `d9df5e03` |

## What shipped

**Swipe between views (#368) — functionally complete.** [static/js/swipe_nav.js](../../../static/js/swipe_nav.js),
its own file rather than a block in `header.js`. Reads the tab bar's own `<a>` slots, so there is no
second page list to drift; a tenant-scoped user gets their tenant's pages free. No wrap at the ends.
**The outer 30px are left to the platform's back/forward gesture on purpose** — in an installed app
that is the only way back out of a page, Safari ignores attempts to suppress it, and native iOS
works the same way. Nothing calls `preventDefault`, so both listeners stay passive.

**View transitions.** `@view-transition { navigation: auto; }` in `nexora-ui.css`, phone-gated.
The flash between loads was never slowness — 16–68ms TTFB, 3–9KB over the wire, everything else
cached. Reduced motion cancels the *animation*, not the opt-in, from both `nx-motion-reduced` and
the OS setting.

**Nothing scrolls sideways on a phone.** Only two things ever did: the reporting rail (756px in a
358px box) and the status tabs (over by six). The rail is a 3×2 grid — no scrolling *and* no ragged
wrap; what made the original wrap look broken was buttons at four different heights with dangling
connectors, not the wrapping. A parametrised test pins the rule across five pages.

**The profile menu section.** Shortcuts row hidden on touch (no keyboard to press). The four pages
behind it held **101 controls under 44px** — What's New's "Try it" at 20px, both primary actions at
40px — now 5, two of which are deliberate and documented in the CSS.

## Next steps

1. **The three undiagnosed symptoms above.** Get screenshots first.
2. **The release is ready and waiting on the owner.** `v3.2.10` is prepared: both version
   declarations bumped, `uv lock` done, changelog folded to a dated section, `test_version.py`
   green. Two steps, **both theirs, neither available to me** (`main` is off-limits):
   - merge PR [#361](https://github.com/Sydoc-Org/nexora/pull/361) → deploys **staging** only
   - `git switch main && git pull && git tag v3.2.10 && git push origin v3.2.10` → **deploys PROD**

   They said "get that on prod". I flagged that the carve-out was Friday 2026-09-25 and they chose
   to proceed, so this is their decision, not a pending question. Mention off-peak timing once; do
   not re-litigate.
3. **Ten issues can auto-close.** PR #361 predates them so it references none. I offered to add
   `Closes #362 …` to the PR body and got no answer — offer once more. Leave **#368** (theirs to
   finish learning) and **#373** (never reproduced) open.
4. **#373 is a defensive fix, not a reproduction.** Chromium fires the `focusout` it relies on in
   all three cases I tried. If the owner sees the tab bar stick again, what would help is what they
   were doing in the seconds before.

## Gotchas & notes

- **PowerShell has no `grep` and no `rg`** — give the owner `git grep`. See
  [[reference_nexora_shell_environment_traps]].
- **`nx` is the tool, not raw python.** `./bin/nx.ps1 --routes:<regex>` gives URL → endpoint →
  file:line, which beats grepping. `-u` / `-r` / `-s` / `-d` / `--doctor`. It is not on PATH.
- **Restart after a template edit** (`nx -r`); `.css`/`.js` need only a reload. This produced two
  false "the fix didn't work" diagnoses.
- **Rect vs computed px**: under mobile emulation `getBoundingClientRect` returns scaled pixels
  (~1.09×). Compare rect to rect.
- **A green workflow is not a live deploy.** A run was cancelled mid-flight by a newer push
  (dev is last-push-wins) and left older code serving. Check dev's footer build stamp, or better,
  `curl` the actual asset — that is how the swipe was confirmed.
- **Waits**: `/reporting` takes ~3s to boot. A 1.4s wait made a working swipe look broken and cost
  real time. Same class of error as reading a stale build: the tooling looked like the code.
- **Two things I got wrong and corrected**: hiding the BETA chip (an unfinished-feature signal is
  not decoration — the owner was right to push back), and a Chart.js `generateLabels` hook that
  rendered "undefined" and was reverted. Two long German donut labels still truncate; the tooltip
  carries the full name. Do not retry that hook the same way.
- **`.rdb-head` is shared** between the dashboard builder and the Report definitions list; scope
  with `:not(.rl-head)`.

## Untracked / left for owner

- **`static/js/header.js` is modified and uncommitted, and is not mine.** It holds (a) the owner's
  own step-1a swipe handler, which still only `console.log`s and is now **superseded** by
  `swipe_nav.js`, and (b) **a whole-file reformat their editor did on save** — 727 insertions /
  575 deletions for ~30 lines of feature. The repo formats Python with ruff but **nothing formats
  JS**, so there is no agreed style this is conforming to. **Do not commit or discard it.** They
  must choose: turn off format-on-save and keep the diff to their own lines, or land the reformat
  as its own commit. Ask.
- **A stray file named `t -L 3`** in the repo root, debris from a mangled shell command. Junk;
  delete on their word.
- No migration, no env key, no generated catalog touched.

## How to verify

```bash
export PATH=".venv/Scripts:$PATH"
./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly
./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly
```

Last run: **1962 passed, 37 skipped** across unit + `test_mobile_nav.py`. Integration was 830
passed earlier in the effort. Nothing is red; CI on `d9df5e03` is green.

For phone work, measure rather than eyeball — at **more than one width** — and remember the
emulator cannot see safe-area insets.

## Resuming in a fresh session

Read this file, then the prior handoff, then
[[feedback_owner_wants_to_write_the_code]] in memory — **the working arrangement changed on
2026-09-21: the owner writes the code and wants to be taught.** They have since asked me to
implement things directly (this session's work was requested that way), so follow what they ask
for now rather than either extreme; when it is a learning task, explain and review instead of
patching.

`/reset-session` picks the newest handoff; `/reset-session docs/superpowers/handoffs/2026-09-22-phone-view-fixes-resume-here.md`
targets this one.
