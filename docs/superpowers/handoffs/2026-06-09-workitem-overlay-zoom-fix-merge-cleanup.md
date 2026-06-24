# Handoff — Workitems source-overlay open-zoom fix + table-highlight merge & worktree cleanup

- **Date:** 2026-06-09
- **Branch:** `feature/2.5.63` (in the **main checkout** `C:\dev\nexora`).
  Committed locally, **NOT pushed** — remote session, commit-only.
- **HEAD / feature commits this session:**
  - `bf23f10` — `fix(workitems): defer source overlay until open-zoom settles`
    (the actual bug fix; made on the now-deleted `feat/workitem-table-highlight` branch).
  - `cb3c9a3` — `Merge feat/workitem-table-highlight into feature/2.5.63` (the `--no-ff` merge).
  - This handoff is the latest `docs(handoff)` commit on top of `cb3c9a3`.
- **Prior handoff / builds on:** `docs/superpowers/handoffs/2026-06-09-workitem-table-highlighting-handoff.md`
  (the table / line-item highlighting feature — now merged into `feature/2.5.63`).
- **Memory pointer:** `project_workitem_table_highlight`.

## TL;DR

- **Fixed the remaining "Show sources" lightbox bug:** highlight boxes appeared the
  instant the lightbox opened, **mispositioned**, and only snapped into place after a
  manual hide/show toggle. Root cause (confirmed with live measurement): the boxes are
  drawn at the page's *final layout* coordinates, but `#srcHlLayer` is a **sibling** of
  the `<img>`, so it does **not** inherit the `.modal-content` open-zoom
  `transform: scale(0.5→1)`. With the image cached, the single render fired *during* the
  zoom, so the boxes floated off the still-scaling page. The earlier `getBoundingClientRect→offset`
  fix corrected the *coordinates* but not the *timing*. (`bf23f10`)
- **Fix:** the overlay's first render now waits until the page is geometrically settled —
  image bitmap decoded **and** every running animation on the image has `finished` — via a
  new `drawOverlayWhenStable()` (reopen / prev-next, with no animation running, render
  immediately). A `ResizeObserver` on the modal image re-renders on any later box-size
  change (values-panel reflow, late decode, viewport resize). Verified live on INT (WID
  18322): cold open draws all 12 boxes within the page bounds, **no toggle needed**.
- **Merged** `feat/workitem-table-highlight` → `feature/2.5.63` (`cb3c9a3`, `--no-ff`).
- **Cleaned up:** removed the `hero-ui` + `table-highlight` worktrees and **deleted** the
  two now-fully-merged branches (`feat/workitem-table-highlight`, `feature/2.5.63-hero-ui`).

## What shipped — the fix (`bf23f10`)

| File | Change |
|---|---|
| `templates/js/_workitems_overview_js.html` | New `drawOverlayWhenStable(pulse)` (waits for image decode + `Promise.allSettled(getAnimations().map(a=>a.finished))` before `renderModalOverlay`); `showImage` calls it instead of the bare 1-rAF defer; a `ResizeObserver` on `#modalImage` re-renders the overlay on later box-size changes (gated to skip while a zoom animation is mid-flight). |
| `CHANGELOG.md` | Fixed-section entry under `[Unreleased]`. |
| `CLAUDE.md` | Extended the workitems source-highlight note (sibling-vs-transform + `drawOverlayWhenStable` + ResizeObserver). |

## What shipped — the merge (`cb3c9a3`)

Brought the entire **table / line-item highlighting** feature + the two new
sub-permissions + the overlay fix onto `feature/2.5.63` (27 files, +2366/−396).
Conflicts resolved:

- **`CHANGELOG.md`** — hand-merged the `[Unreleased]` union; dropped the table-highlight
  side's *older* duplicate of the reporting-semantic Slice-1 entry (same migration `0017`;
  HEAD's "canonical metrics" text is the newer version). `CLAUDE.md` auto-merged.
- **i18n catalogs** (`messages.pot`, de/fr/it `.po`/`.mo`) — conflicts were only cosmetic
  (POT timestamp + source line-refs); the translation content auto-merged. Resolved by
  stripping the markers then **regenerating** via `pybabel extract` / `update` / `compile`.
  `tests/unit/test_translations.py` → 7 passed.

## Owner actions / next steps

1. **Delete the leftover orphaned folder.** `git worktree remove --force` *unregistered*
   the table-highlight worktree (gone from `git worktree list`) but could not delete the
   directory — this session was running inside it (Windows locks the CWD). After closing
   the session, from the main repo:
   `Remove-Item -Recurse -Force C:\dev\nexora.wt\table-highlight`
2. **Push `feature/2.5.63` + open the PR → `main`** (remote session left this to you).
   The pre-push gate runs the full e2e suite — run `python scripts/test_db_reset.py` first
   to avoid stale `NEXORA_TEST` state.
3. **Migration `0018`** (workitems `…view.confidence` / `…view.source_location` perms) was
   applied directly to INT in the prior session (idempotent) but **not recorded** in
   `dbo.SchemaMigrations` (INT CRLF drift). Formally record/apply on INT, and PROD picks it
   up automatically on deploy (auto-applies pending migrations).
4. **Stray untracked file:** `sql/_migrations/NexoraDB/0019_fix_workitems_source_label_octo.sql`
   sits **uncommitted** in the main-repo working tree — looks like someone else's in-progress
   work. I left it untouched and it is **not** in any commit. Decide if it's wanted before
   your next commit/migrate.

## Gotchas & notes

- **Why the fix targets timing, not coordinates:** the overlay can never inherit the
  image's `transform` (it's a sibling div, and an `<img>` can't contain children). So the
  correct fix is to render only once the image is at its final scale. `getAnimations()` is
  used because the headless test env throttles the 0.4s CSS animation to ~3s — `.finished`
  is robust to that; a fixed timeout would not be. `Promise.allSettled` (not `all`) so a
  cancelled animation (modal closed mid-open) can't hang the render.
- **Branch deletion used `-d` (not `-D`)** — git confirmed both branches were fully merged,
  so nothing was lost. Branch refs were the only remaining copy of `feature/2.5.63-hero-ui`
  (it had no upstream); it is now fully contained in `feature/2.5.63`.
- **Restart the dev server after template edits** (Jinja caches the JS partial).
- Verification screenshots from this session were saved under the (now-orphaned) worktree's
  `var/screenshots/` — they go away with the folder; regenerate from the live UI if needed.

## How to verify

```bash
# from the main repo: C:\dev\nexora  (system python; no venv on this box)
python -m pytest tests/e2e/test_workitem_source_highlight.py tests/e2e/test_workitem_table_highlight.py -o addopts="" -q
python -m pytest tests/unit/test_translations.py -o addopts="" -q
# live UI: ENVIRONMENT=INT FLASK_RUN_PORT=8050 python nx_main.py
#   -> /dev/login/ben.streich -> /workitems?search=18322 -> expand -> click the page thumbnail
#   -> boxes appear aligned over the document on open, no hide/show toggle needed
```

## Resuming in a fresh session

The workitems source-highlighting feature (scalar + table/line-item + the two
sub-permissions + the open-zoom fix) is **complete and merged into `feature/2.5.63`**.
The only remaining work is **owner-side**: delete the leftover worktree folder, push
`feature/2.5.63`, open the PR → `main`, and record migration `0018` on INT (PROD
auto-applies on deploy). Memory pointer: `project_workitem_table_highlight`.
