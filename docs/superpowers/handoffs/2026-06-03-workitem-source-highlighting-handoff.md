# Handoff — Workitems source highlighting ("Show sources")

- **Date:** 2026-06-03
- **Branch:** `feat/workitem-source-highlight` — an **isolated git worktree** at
  `C:\dev\nexora.wt\source-highlight`, branched off `feature/2.5.63.1`@`7139d7a`.
  Committed locally, **NOT pushed** — remote session, commit-only.
- **HEAD:** `da5f165` — **7 feature commits** on top of the base (`4a44c08` → `da5f165`).
  This handoff commit will be the new latest.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-reporting-phase4-backlog-complete-handoff.md`
  (different workstream — reporting BI).
- **Spec:** `docs/superpowers/specs/2026-06-03-workitem-source-highlighting-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-03-workitem-source-highlighting.md`

## TL;DR

- Built **"Show sources"** on the workitems document viewer: a toggle overlays
  boxes showing exactly where each extracted index-field value was found on the
  page — in the full-page lightbox **and** on thumbnails. Click a field value to
  jump to its page and pulse its box; values with no coordinates get a
  **"no source location"** badge. **Strictly read-only** — extracted data is never
  changed. Reuses `workitems.details.view.images` + `.fields`; **no new permission,
  no migration.**
- The coordinates were already fetched from Octopus and **thrown away**. A live INT
  spike (WID 18299) pinned the real shape: `IndexField.Location.Rectangle/Rectangles`
  (image pixels, top-left, page = `PageIndex`; `{0,0,0,0}` = derived/un-locatable).
  Backend ships **raw pixel rects** in `api_get_media_info` `field_sources`; the
  browser normalizes against each page image's `naturalWidth/Height` (drops the
  page-dimension dependency and the rotation risk).
- Verified: **32 new unit tests** + full unit suite **477 passed**, **7** translation
  tests, **2** e2e, all green. Octopus shape confirmed live on INT; overlay rendering
  confirmed in a browser (screenshots `var/screenshots/source-highlight-*.png`).
- Built on a **worktree** because a concurrent Claude session was `git add -A`-sweeping
  a UI reskin onto `feature/2.5.63.1` and editing the same workitems files. **Nothing
  is pushed — you merge + push + open the PR.**

## What shipped — task → commit

| Task | Item | Commit |
|---|---|---|
| 1 | Live INT spike: verified Octopus coordinate shape (recorded in spec) | `4a44c08` |
| 2–3 | Pure `nx_lib/field_locations.py` (`_rect_from_octo`, `extract_field_locations`) + 14 unit tests | `f61936c` |
| 4–5 | `get_extensions_urls_fields` → 4-tuple; `api_get_media_info` returns `field_sources` (perm-suppressed) + tests | `3e9963c` |
| 6–9 | Frontend overlay UI: lightbox + thumbnails, click-to-locate, badge, localStorage toggle | `8ce1aca` |
| 10 | i18n: 5 strings translated de/fr/it (minimal-append) | `0aeab3d` |
| 11 | e2e scaffolding test | `0a79b60` |
| 12 | CHANGELOG + CLAUDE.md docs | `da5f165` |

### Files

**Backend (new):**
- `nx_lib/field_locations.py` — pure parser: Octopus `IndexField.Location` →
  `[{key,label,value,locations:[{page,rect:{left,top,width,height}}]}]`. Pixel rects;
  drops degenerate `{0,0,0,0}`; mapped+valued fields only (mirrors the existing
  `fields` dict, first-occurrence wins); per-child-document page offset for Batch docs;
  `CapturedLocation` fallback.

**Backend (changed):**
- `nx_lib/octo.py` — `get_extensions_urls_fields` now returns a **4-tuple**
  (`…, field_sources`) from the doc JSON it already fetches.
- `nx_lib/views/workitems.py` — `api_get_media_info` includes `field_sources` with a
  DRY `_suppress()`: no `fields` perm → empty; no `images` perm → values kept, boxes
  stripped. Three other unpack sites updated (`dashboard.py` activity, csv export,
  `api_get_media_raw`).

**Frontend:**
- `static/css/source-highlight.css` — **new**, isolated from the reskin's `nexora-ui.css`.
- `templates/workitems_overview.html` — CSS link + `#srcHlToggle` + `#srcHlLayer` in `#imageModal`.
- `templates/js/_workitems_overview_js.html` — overlay render (lightbox via
  `getBoundingClientRect` + `naturalWidth`; thumbnails `object-contain` + letterbox-aware),
  click-to-locate, un-locatable badge, `localStorage` toggle.

**Tests / i18n / docs:**
- `tests/unit/test_field_locations.py` (14), `tests/unit/test_media_info_field_sources.py` (3),
  `tests/unit/test_octo.py` (updated to 4-tuple), `tests/e2e/test_workitem_source_highlight.py` (2).
- `messages.pot` + `translations/{de,fr,it}/…` (5 strings).
- `CHANGELOG.md` (`[Unreleased] → Added`), `CLAUDE.md` (workitems doc-viewer note).

## Owner actions / next steps

1. **Merge `feat/workitem-source-highlight` into `feature/2.5.63.1`.** It advanced
   further (more reskin commits) since this branched off `7139d7a`. **Expect conflicts
   in `templates/js/_workitems_overview_js.html` and `templates/workitems_overview.html`**
   — the reskin and this feature both touch them. The new CSS is in a separate file,
   so no conflict there.
2. **Push** and open the PR yourself (remote session left this to you).
3. Before pushing, the pre-push gate runs the **full e2e suite** — run
   `python scripts/test_db_reset.py` first to avoid stale `NEXORA_TEST` state.

## Gotchas & notes

- **Worktree env files:** gitignored `env/*.env` were copied in from the main checkout
  (needed by tests + the dev server). They stay gitignored; not committed.
- **SQL line endings (worktree-local):** `sql/_migrations/**/*.sql` are LF-normalized in
  the working tree (uncommitted) so the `sql-migrate-int` hook's byte-checksums match
  INT's `SchemaMigrations` records. Root cause: `.gitattributes` does **not** pin
  `*.sql` to LF, so the fresh worktree checkout gave them CRLF. **Worth fixing centrally**
  (`*.sql text eol=lf` + renormalize). See the line-endings memory note.
- **Can't screenshot *real* boxes via the dev UI:** the only workitems carrying real
  coordinates belong to process `DigitalMailroom_sydoc`/`ELSY`, which **no account with
  detail perms can see**. The screenshots use injected representative coords on a real
  page; data correctness is proven by the spike + unit tests. The "no source location"
  badge in the thumbnail screenshot **is** real (the genuine `Document Source: SCAN` field).
- **Restart the dev server after template edits** (Jinja caches the JS partial for the
  process lifetime).

## How to verify

```bash
# from the worktree: C:\dev\nexora.wt\source-highlight
python -m pytest tests/unit/test_field_locations.py tests/unit/test_media_info_field_sources.py tests/unit/test_octo.py -q
python -m pytest tests/unit/test_translations.py -q
python -m pytest tests/e2e/test_workitem_source_highlight.py -q   # ~80s (browser + TEST subprocess)
# live UI:
FLASK_RUN_PORT=8050 ENVIRONMENT=INT python nx_main.py    # then /dev/login/<user> -> /workitems
```

## Resuming in a fresh session

Start from **this file**. The feature is complete and committed on the worktree branch
`feat/workitem-source-highlight`; the only remaining work is the **owner merge into
`feature/2.5.63.1` (with template conflict resolution) + push + PR**. Memory pointer:
`project_workitem_source_highlight`.
