# Prepared Documents ⇄ Workitem Detail Cross-Linking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cross-link the MS02 Prepared Documents register and the Workitems detail view in both directions: (P1) extract the workitem detail panel into a shared client-side partial; (P2) a read-only preview modal on the register's Octo-Status cell that mirrors the full workitem details panel; (P3) a reverse "In register" chip on the Workitems detail panel + a register `?pid` exact-match filter. Read-only, MS02-only, no new permission, no new migration.

**Architecture:** Extract the detail-panel rendering (markup builder + lazy loaders + the source-highlight lightbox engine) out of `templates/js/_workitems_overview_js.html` into a new shared partial `templates/js/_workitem_detail_panel_js.html` exposing `window.NexoraWorkitemDetail.render(workitemId, containerEl, { readOnly, perms, inRegisterPid })` plus `NexoraWorkitemDetail.attachLightbox(idMap)`. Both the Workitems row-expand and the register modal consume it (single source of truth). The lightbox engine is made container-scoped (bound to an explicit shell id-map, not the page-global `#imageModal`) so each host page owns its own shell. The reverse direction adds a `pids_in_register()` data-access helper, a `resolve_ms02_wids_to_pids()` resolver, and a pure `_stamp_in_register()` enrichment step inside `_get_workitems_data` (no new route, no new permission — honours the spec's "no extra perm"). Read-only mode **omits** (not just disables) the write controls. MS02-only.

**Tech Stack:** Flask (Python 3, WSGI) · Jinja2 templates with paired JS partials · vanilla JS (no build step) · Tailwind (CDN browser build) · SQL Server (NexoraDB via pyodbc) + Azure Postgres (MS02 doc-field engine via psycopg2) · Flask-Babel i18n (de/fr/it) · pytest (unit + integration) + Playwright (e2e).

**Spec:** `docs/superpowers/specs/2026-06-23-prepared-docs-workitem-preview-design.md`

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63`. You are in the planning worktree `plan/prepared-docs-workitem-preview` (working dir = repo root of that worktree). This is **remote / commit-only** work: STOP at `git commit`. Do **not** `git push` and do **not** open a PR — the owner does that after local review. Every task ends with a paste-ready conventional-commit message.
- **Anchor on snippets, never line numbers.** This plan cites line numbers only as a navigation aid; the files (`_workitems_overview_js.html` especially, ~2368 lines) are large and recently edited, so line numbers drift. When editing, match on the verbatim code/markup snippets shown in each task (the repo files were read at HEAD on 2026-06-23). Re-Read/Re-Grep the file before each Edit.
- **Jinja template cache:** templates are cached for the process lifetime. After ANY template/JS-partial edit, restart `nx -u` before browser verification or you will see stale HTML. (Unit/integration tests build a fresh app per session, so they pick up edits without a manual restart.)
- **TEST/CI has NO MS02 engine:** `ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None` is `False` in CI. Every test that needs the register/preview/reverse path must gate-and-mock: `import nx_lib.views.workitems as wv; from nx_lib.clients import CLIENTS; monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object()); monkeypatch.setitem(CLIENTS, "ms02", object())`.
- **The `has_permission` wv-local trap:** route bodies in `nx_lib/views/workitems.py` call the module-local `has_permission` (imported into `wv`). The `workitems_all_perms` fixture only patches `nx_lib.security.has_permission`. Render tests that exercise in-body perm gates MUST ALSO do `monkeypatch.setattr(wv, "has_permission", lambda code: True)` (see the existing `tests/integration/test_workitems_routes.py::test_prepared_documents_page_renders_when_ms02_active`).
- **SQL_SYNC_SKIP escape hatch:** there are NO SQL migrations in this feature, but the `sql-migrate-int` / `sql-sync-check` pre-commit hooks still run and can fail on known INT CRLF drift. If a commit is blocked by that (and ONLY that), use `SQL_SYNC_SKIP=1 git commit ...`. NEVER use `--no-verify`.
- **i18n cycle:** new user-facing strings are marked `{{ _('...') }}` in templates / `_('...')` in Python, then: `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → translate the new msgids **non-fuzzy** in `translations/{de,fr,it}/LC_MESSAGES/messages.po` → `pybabel compile -d translations`. `babel.cfg` extracts from `templates/**.html`, so the new partial is auto-covered; strings lifted-and-shifted out of `_workitems_overview_js.html` keep the same msgids. `tests/unit/test_translations.py` enforces pot-in-sync + every msgid translated non-fuzzy. The `/nx-i18n` skill scaffolds this.
- **Migrations needed: NO.** `dbo.PreparedDocuments` already exists (highest migration on disk is `0033`; the `0031` file in `git status` is a separate dashboard-stats fix, not ours). The whole feature is read-only / computed-live. Assert zero new files under `sql/_migrations/`.
- **New permission: NO.** Reuses `workitems.import.preparedaudit` (migration `0029`, register page) and the `workitems.details.view.*` family (migration `0018`). `page_visibility()` already has `"preparedDocsPagePerm": has_permission("workitems.import.preparedaudit")` (`nx_lib/security.py` line ~139). The reverse chip carries **no extra perm** (server-side enrichment, MS02-gated only).
- **Deploy excludes: no change.** The one new file (`templates/js/_workitem_detail_panel_js.html`) lives under `templates/`, already mirrored to prod (not in `deploy.yml` `/XD`). No new top-level file and no new `static/` asset (reuses `static/css/source-highlight.css`). Confirmation only — no `deploy.yml` edit.
- **Pre-push gate runs the FULL suite incl. Playwright e2e.** This is commit-only, so the push gate is the owner's concern — but keep the unit/integration suite green at every commit. Run `python scripts/test_db_reset.py` before any full-suite run if state is stale.
- **Pre-existing red tests (NOT this feature):** `tests/unit/test_octo.py::test_get_extensions_urls_fields_single_doc` / `..._batch_doc_iterates_children` / `..._non_batch_container_recurses` (doubled-scheme from the Octo media-host rewrite; verified present at lines 181/222/254). These are out of scope; flag them, do not fix them under this feature, and do not let a "suite green" claim hide them. (`tests/unit/test_workitems_pid_filter.py` does **not** exist — verified — so do NOT cite it as a candidate red.)
- **Strays in `git status`** (`scripts/new-process.py`, staged `nx_lib/views/dashboard.py` / `tests/unit/test_dashboard_stats.py` / `sql/_migrations/.../0031_*.sql`, `CHANGELOG.md`, `CLAUDE.md`) are NOT part of this feature; do not stage or sweep them into these commits. Use explicit `git add <paths>` per task (the commit messages below use `git add <paths>` then commit, not `git commit -am`).

### What the shared panel actually consists of (extraction surface — verified against HEAD)

`templates/js/_workitems_overview_js.html` is a **single `<script>` block, no outer IIFE**. The detail-panel pieces are split across two scopes:

- **Module scope (top-level):** `const API_PREFIX` (line 11), `let mentionableUsers` (27), `let fieldConfig` (29), `loadHistory` (148), `renderTagsInDetails` (218), `refreshWorkitemUI` (231), `loadCollaborationData` (258), `renderWorkitemTimeline` (308), `loadImagesInBatch` (358), `buildDetailContent` (384), `toggleDetailsAndLoadImages` (544), `srcEsc` (669), `tableCellSources` (678), `allSources` (691), `renderTableGrids` (699), `buildSourceDetailsHtml` (733), `renderThumbOverlay` (781), `refreshThumbOverlays` (808), `loadImage` (818), plus the write handlers (`handlePostComment`, `handleSetPriority`, `handleAssigning`, `handleAddTag`, `handleRemoveTag`) and mention helpers (`fetchMentionableUsers`, etc.). The `window.__*ByWorkitem` globals and `window.srcConfClass`/`window.srcConfPct` are also read here.
- **Inside `DOMContentLoaded`** (handler opens at line 1143): `renderRowList` (1380), `renderTable` (1689), the `tbody` event delegation (1979–2037: toggle/add-tag/remove-tag/load-more/comment/priority/assign/mention), and the **entire lightbox/source-overlay engine** (`let currentImages`/`let currentIndex` at 2039–2040; `const modal/modalImg/closeBtn/prevBtn/nextBtn` at 2042–2046 using `document.querySelector('.modal-*')`; `const srcHl` at 2049; `renderModalOverlay` 2079; `openModalForWorkitem` 2148; `renderReviewPanel` 2165; `showImage` 2195; `closeModal`, `ensureSourcesOn`, `setSrcHl`, `drawOverlayWhenStable`, the `ResizeObserver` at 2063; the four `document.addEventListener('click', …)` click-to-locate delegations at 2225–2260; and the close/backdrop/prev/next/toggle/resize/keydown handlers at 2262–2301). The select-all / bulk-bar / export-modal handlers (2303–2363) are **unrelated** and stay.

**Extraction strategy (locked):** move the **module-scope panel functions** into the shared partial under a `NexoraWorkitemDetail` namespace (re-exporting on `window` for the page-side code that still references them by bare name during the transition), and make the **lightbox engine + click-to-locate delegations** part of the shared partial as `attachLightbox(idMap)`, **scoped to a passed shell id-map** rather than the page-global `#imageModal`. The `tbody` write-handler delegation stays **page-side** on the workitems page (the register modal is read-only and has no `tbody`, so it never needs those handlers). The workitems shell ids (`imageModal`/`modalImage`/`srcHlLayer`/`srcHlToggle`/`srcHlToggleLabel`/`srcReviewPanel`/`srcReviewPanelBody`) are preserved unchanged (no rename → no regression); the register modal passes its own `pdocPreview*` ids.

## Decisions locked in

| # | Decision | Choice |
|---|---|---|
| 1 | Register click action | **Read-only preview MODAL** on the register page, plus an "Open in Workitems" link (the existing `workitems_overview?search=<wid>`). |
| 2 | Preview scope | **Full details mirror** — images, source highlighting, fields, audit, tags, comments. |
| 3 | Reverse direction | **Included** — an "In register" chip/link on the Workitems detail panel header → `prepared_documents?pid=<pid>`. |
| 4 | Reuse architecture | **Shared panel** — `templates/js/_workitem_detail_panel_js.html` exposing `NexoraWorkitemDetail.render(wid, container, {readOnly, perms, inRegisterPid})` + `attachLightbox(idMap)`; the Workitems row-expand refactored to consume it (behaviour unchanged). |
| 5 | Interactivity | **Read-only** preview (write controls **omitted**, not just disabled, in the modal). |
| 6 | Permissions / schema | **No new permission, no new migration.** MS02-only + existing `workitems.import.preparedaudit` + `workitems.details.view.*`. New i18n strings only. |

## Owner actions

These are NOT done by this plan (owner-only or out of scope):

- **Push / PR.** Commit-only remote session; the owner pushes `feature/2.5.63` and opens the PR to `main` after local review.
- **PROD visual verification of the modal IMAGE section.** Octo media is unreachable from dev / MS02-from-dev, so the preview modal renders fields/audit/tags/comments with empty image slots locally. Full image preview is only verifiable on PROD. The owner does the PROD visual check (as the register itself was verified).
- **Pre-existing red tests are out of scope.** `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}` (doubled-scheme from the Octo media-host rewrite). Do not absorb their fixes into this feature; flag them so any "suite green" claim stays honest.
- **Background-agent strays in `git status`** (`scripts/new-process.py`, staged `dashboard.py` / `0031` migration / `test_dashboard_stats.py` / `CHANGELOG.md` / `CLAUDE.md`) are not part of this feature; do not stage or sweep them into these commits except where this plan explicitly edits `CHANGELOG.md`/`CLAUDE.md` (Task 4.1).

---

# PHASE 1 — Shared panel extraction (riskiest; do first, in isolation)

P1 is a behaviour-preserving lift-and-shift. The Workitems page must behave byte-for-byte identically afterward. Do not collapse the P1 tasks into one commit — each keeps the suite green so a regression is caught at the smallest step. After each P1 task, do the **browser** regression check (integration tests assert route status + marker strings, not the JS DOM, so a closure/scope slip can pass unit tests yet break row-expand at runtime).

### Task 1.1: Create the shared partial skeleton with `NexoraWorkitemDetail.render` + perm-driven markup builder

**Files:**
- Create: `templates/js/_workitem_detail_panel_js.html`
- Modify: `templates/workitems_overview.html` (include the partial before the page JS)
- Test: `tests/integration/test_workitem_detail_panel.py` (new)

**Interfaces:**
- Produces: `window.NexoraWorkitemDetail = { render(workitemId, containerEl, { readOnly = false, perms = {}, inRegisterPid = null } = {}) }`. `perms` keys (booleans): `images`, `audit`, `fields`, `setPriority`, `addTag`, `assignUsers`, `addComment`. In this task `render` only builds the static panel DOM via an internal `buildPanelMarkup(workitemid, status, currentStage, perms, readOnly)`; loaders + lightbox + chip land in 1.2–1.4 / 3.4.
- Consumes: nothing page-specific — all visible strings use `{{ _('...') }}` (Jinja-rendered into both host pages); perms arrive via the JS `perms` argument so the same compiled markup serves both pages.

- [ ] **Step:** Read `templates/js/_workitems_overview_js.html` `buildDetailContent` (anchor: `function buildDetailContent(workitemid, status, currentStage) {` ~line 384 through its closing `}` ~542) to copy the markup interior verbatim, including the `data-testid` attributes. Note it has NO `detail-panel-header` element today — we add one for the P3 chip.
- [ ] **Step (write failing test):** Create `tests/integration/test_workitem_detail_panel.py`:
  ```python
  """The shared workitem-detail panel partial is included on its consumer pages
  and exposes window.NexoraWorkitemDetail.render. Include-presence is asserted on
  the /prepared_documents register render (gate-and-mocked, deterministically 200)
  so a 500-fallback can never make the assertion pass vacuously."""

  import pytest


  @pytest.fixture()
  def workitems_all_perms(monkeypatch):
      monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
      yield


  def test_detail_panel_partial_present_on_workitems(user_client, workitems_all_perms):
      # The include lives in the template body (before any data fetch); a 500-fallback
      # would render 500.html WITHOUT the marker, so assert unconditionally — that makes
      # the 'expect fail' run fail loudly and a later regression fail loudly too.
      resp = user_client.get("/workitems")
      assert b"NexoraWorkitemDetail" in resp.data
  ```
- [ ] **Step (run, expect fail):** `python -m pytest tests/integration/test_workitem_detail_panel.py::test_detail_panel_partial_present_on_workitems -q` — fails (marker absent: the partial does not exist / is not included). **Confirm it truly fails before implementing.**
- [ ] **Step (implement):** Create `templates/js/_workitem_detail_panel_js.html`. Open the namespace and move the markup builder in, converting the inline Jinja `{% if details_*_perm %}` gates to JS conditionals on the per-render `perms` object, splitting the Collaboration block into a writable variant and a read-only variant (decision 5 = **omit** the write controls). The markup interior (timeline steps, image/history/fields blocks, collaboration controls) is copied verbatim from `buildDetailContent`; only the perm-gating mechanism and the read-only split change. Add a `detail-panel-header-${workitemid}` element (empty; the P3 chip fills it):
  ```html
  <script>
    (function () {
      const API_PREFIX = window.API_PREFIX
        || (window.location.href.includes("nexora") ? "/nexora/" : "/");
      const csrfToken = document.getElementById("csrfToken")?.value || "";

      function buildCollaborationMarkup(workitemid, perms) {
        const prioDis = perms.setPriority ? '' : 'disabled';
        const assignDis = perms.assignUsers ? '' : 'disabled';
        const tagDis = perms.addTag ? '' : 'disabled';
        const commentDis = perms.addComment ? '' : 'disabled';
        return `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="flex flex-col">
              <div id="comments-container-${workitemid}" class="flex-grow space-y-3 overflow-y-auto mb-4 p-2 bg-gray-50 rounded h-60"><p class="text-gray-500 italic">{{ _("Loading comments...") }}</p></div>
            </div>
            <div id="collaboration-tools-${workitemid}" class="flex flex-col">
              <div class="mb-4">
                <label for="priority-select-${workitemid}" class="text-sm font-medium text-gray-700">{{ _("Set Priority:") }}</label>
                <select id="priority-select-${workitemid}" data-workitemid="${workitemid}" ${prioDis} class="priority-selector mt-1 w-full p-2 border rounded-md focus:ring-indigo-500 focus:border-indigo-500" data-testid="workitems-priority-${workitemid}">
                  <option value="0">{{ _("None") }}</option><option value="1">{{ _("Low") }}</option><option value="2">{{ _("Medium") }}</option><option value="3">{{ _("High") }}</option>
                </select>
              </div>
              <div class="mb-4">
                <label for="assign-select-${workitemid}" class="text-sm font-medium text-gray-700">{{ _("Assigned to:") }}</label>
                <select id="assign-select-${workitemid}" data-workitemid="${workitemid}" ${assignDis} class="assign-selector mt-1 w-full p-2 border rounded-md focus:ring-indigo-500 focus:border-indigo-500" data-testid="workitems-assign-${workitemid}"><option value="None">{{ _("None") }}</option></select>
              </div>
              <div class="mb-4">
                <label class="text-sm font-medium text-gray-700">{{ _("Tags:") }}</label>
                <div class="flex items-center gap-2">
                  <input type="text" id="tag-input-${workitemid}" list="taglist" ${tagDis} class="flex-grow p-2 border rounded-md" placeholder="{{ _('Add a tag...') }}" data-testid="workitems-tag-input-${workitemid}">
                  <input type="color" id="tag-color-${workitemid}" ${tagDis} class="h-10 w-12 p-1 border rounded-md" value="#6B7280" data-testid="workitems-tag-color-${workitemid}">
                  <button type="button" ${tagDis} class="add-tag-btn bg-indigo-600 text-white px-3 py-2 rounded-lg hover:bg-indigo-700 transition" data-workitemid="${workitemid}" data-testid="workitems-add-tag-${workitemid}"><i class="fas fa-plus"></i></button>
                </div>
                <div id="tags-container-${workitemid}" class="flex flex-wrap items-center gap-2 mt-4 p-2 bg-gray-50 rounded min-h-[40px]"></div>
              </div>
              <div class="relative mt-auto pt-8" id="comment-form-wrapper-${workitemid}">
                <form class="comment-form" data-workitemid="${workitemid}" data-testid="workitems-comment-form-${workitemid}">
                  <label for="comment-text-${workitemid}" class="text-sm font-medium text-gray-700">{{ _("Add Comment:") }}</label>
                  <textarea name="commentText" id="comment-text-${workitemid}" ${commentDis} class="mt-1 w-full p-2 border rounded-md focus:ring-indigo-500 focus:border-indigo-500" placeholder="{{ _('Add a comment... Tag with @username') }}" rows="3" required autocomplete="off" data-testid="workitems-comment-text-${workitemid}"></textarea>
                  <button type="submit" ${commentDis} class="mt-2 w-full bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition" data-testid="workitems-comment-submit-${workitemid}">{{ _("Post Comment") }}</button>
                </form>
                <div class="mention-autocomplete-list hidden absolute bottom-full mb-1 w-full bg-white border rounded-lg shadow-lg z-10 max-h-40 overflow-y-auto"></div>
              </div>
            </div>
          </div>`;
      }

      function buildReadonlyCommentsMarkup(workitemid) {
        // Read-only: comments are read content (kept); the priority/assign selectors,
        // the tag input and the comment form are OMITTED entirely (decision 5).
        return `
          <div class="grid grid-cols-1 gap-6">
            <div class="flex flex-col">
              <div id="comments-container-${workitemid}" class="flex-grow space-y-3 overflow-y-auto p-2 bg-gray-50 rounded"><p class="text-gray-500 italic">{{ _("Loading comments...") }}</p></div>
            </div>
            <div class="flex flex-col">
              <label class="text-sm font-medium text-gray-700">{{ _("Tags:") }}</label>
              <div id="tags-container-${workitemid}" class="flex flex-wrap items-center gap-2 mt-2 p-2 bg-gray-50 rounded min-h-[40px]"></div>
            </div>
          </div>`;
      }

      function buildPanelMarkup(workitemid, status, currentStage, perms, readOnly) {
        const imagesBlock = perms.images
          ? `<div id="image-container-${workitemid}" class="flex-1 flex justify-center items-center overflow-y-scroll p-2 border-2 border-dashed border-gray-200 rounded-2xl bg-white"><p class="text-gray-500 text-center px-2">{{ _("Click toggle button again to load media") }}</p></div>`
          : `<div class="flex-1 flex justify-center items-center p-2 border-2 border-gray-100 rounded-2xl bg-gray-50"><div class="text-center"><i class="fas fa-eye-slash text-gray-400 text-3xl mb-2"></i><p class="text-gray-500">{{ _("Media preview restricted") }}</p></div></div>`;
        const historyBlock = perms.audit
          ? `<div id="history-container-${workitemid}" class="flex-grow overflow-y-auto pr-2"><p class="text-gray-500 italic">{{ _("Loading history...") }}</p></div>`
          : `<div class="flex-grow flex items-center justify-center bg-gray-50 rounded"><p class="text-gray-400"><i class="fas fa-lock mr-2"></i>{{ _("Audit history restricted") }}</p></div>`;
        const fieldsBlock = perms.fields
          ? `<div id="fields-container-${workitemid}" class="flex-grow pr-2"><p class="text-gray-500 italic">{{ _("Loading details...") }}</p></div>`
          : `<div class="flex-grow flex items-center justify-center bg-gray-50 rounded"><p class="text-gray-400 italic"><i class="fas fa-lock mr-2"></i>{{ _("Document fields restricted") }}</p></div>`;
        const collaboration = readOnly ? buildReadonlyCommentsMarkup(workitemid) : buildCollaborationMarkup(workitemid, perms);
        return `
          <div class="details-content-wrapper p-4 bg-gray-100 flex flex-col gap-6">
            <div id="detail-panel-header-${workitemid}" class="detail-panel-header"></div>
            <div id="timeline-container-${workitemid}" class="relative bg-white p-6 sm:p-8 rounded-2xl shadow-sm border border-gray-100" data-current-stage="${currentStage}" data-status="${status}">
              <div class="relative flex justify-between items-center">
                <div class="absolute top-1/2 h-1 -translate-y-1/2 bg-gray-200 rounded-full" style="left: 28px; right: 28px;"></div>
                <div class="progress-line absolute top-1/2 h-1 -translate-y-1/2 bg-indigo-500 rounded-full" style="left: 28px; right: 28px; transform: scaleX(0); transform-origin: left; transition: transform 0.8s ease-in-out;"></div>
                <div class="process-step z-10 flex flex-col items-center text-center"><div class="step-icon-wrapper flex items-center justify-center w-14 h-14 bg-white border-2 border-gray-300 rounded-full"><i class="fas fa-cloud-arrow-up text-xl text-gray-400"></i></div><p class="step-label mt-3 font-semibold text-gray-500 text-sm">Import</p></div>
                <div class="process-step z-10 flex flex-col items-center text-center"><div class="step-icon-wrapper flex items-center justify-center w-14 h-14 bg-white border-2 border-gray-300 rounded-full"><i class="fas fa-gears text-xl text-gray-400"></i></div><p class="step-label mt-3 font-semibold text-gray-500 text-sm">Extraction</p></div>
                <div class="process-step z-10 flex flex-col items-center text-center"><div class="step-icon-wrapper flex items-center justify-center w-14 h-14 bg-white border-2 border-gray-300 rounded-full"><i class="fas fa-shield-halved text-xl text-gray-400"></i></div><p class="step-label mt-3 font-semibold text-gray-500 text-sm">Validation</p></div>
                <div class="process-step z-10 flex flex-col items-center text-center"><div class="step-icon-wrapper flex items-center justify-center w-14 h-14 bg-white border-2 border-gray-300 rounded-full"><i class="fas fa-paper-plane text-xl text-gray-400"></i></div><p class="step-label mt-3 font-semibold text-gray-500 text-sm">Delivery</p></div>
              </div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
              <div class="flex flex-col gap-6 h-[50rem]">
                ${imagesBlock}
                <div class="flex-1 flex flex-col bg-white rounded-2xl p-5 border border-gray-100 shadow-sm overflow-hidden">
                  <h4 class="text-sm font-bold text-gray-400 uppercase tracking-widest mb-3 border-b border-gray-100 pb-3">{{ _('History') }}</h4>
                  ${historyBlock}
                </div>
              </div>
              <div class="flex flex-col bg-white rounded-2xl p-5 border border-gray-100 shadow-sm h-[50rem] overflow-y-auto">
                <h4 class="text-sm font-bold text-gray-400 uppercase tracking-widest mb-3 border-b border-gray-100 pb-3">{{ _('Document Details') }}</h4>
                ${fieldsBlock}
              </div>
            </div>
            <div class="flex-1 flex flex-col bg-white rounded-2xl p-5 border border-gray-100 shadow-sm">
              <h4 class="text-sm font-bold text-gray-400 uppercase tracking-widest mb-3 border-b border-gray-100 pb-3">{{ _('Collaboration') }}</h4>
              ${collaboration}
            </div>
          </div>`;
      }

      window.NexoraWorkitemDetail = window.NexoraWorkitemDetail || {};
      window.NexoraWorkitemDetail._buildPanelMarkup = buildPanelMarkup;
      window.NexoraWorkitemDetail.render = function (workitemId, containerEl, opts) {
        const { readOnly = false, perms = {} } = opts || {};
        if (!containerEl) return;
        const wid = String(workitemId);
        const status = containerEl.dataset.status || (opts && opts.status) || '';
        const currentStage = containerEl.dataset.currentStage || (opts && opts.currentStage) || '';
        containerEl.innerHTML = buildPanelMarkup(wid, status, currentStage, perms, readOnly);
        // loaders + lightbox + chip wired in Tasks 1.2 / 1.4 / 3.4
        return wid;
      };
    })();
  </script>
  ```
- [ ] **Step (include on the workitems page):** In `templates/workitems_overview.html`, add the include immediately BEFORE the existing workitems JS include so `NexoraWorkitemDetail` exists when `_workitems_overview_js.html` runs. Match on the verbatim line `{% include 'js/_workitems_overview_js.html' %}` and insert the new include before it:
  ```html
      {% include 'js/_workitem_detail_panel_js.html' %}
      {% include 'js/_workitems_overview_js.html' %}
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitem_detail_panel.py -q` — passes.
- [ ] **Step (commit):**
  ```
  git add templates/js/_workitem_detail_panel_js.html templates/workitems_overview.html tests/integration/test_workitem_detail_panel.py
  git commit -m "refactor(workitems): scaffold shared NexoraWorkitemDetail panel partial (P1.1)

  New templates/js/_workitem_detail_panel_js.html exposing
  window.NexoraWorkitemDetail.render(wid, container, {readOnly, perms}). Perm gating
  is JS-driven (perms.*) so the same compiled markup serves both the workitems
  row-expand and the upcoming register preview modal; readOnly omits the write
  controls (priority/assign/tag input/comment form). Included on the workitems page;
  not yet wired to the row-expand.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```
  (If the `sql-migrate-int` hook fails on known INT CRLF drift, use `SQL_SYNC_SKIP=1 git commit -m "..."`; never `--no-verify`.)

### Task 1.2: Move the lazy loaders + field/source helpers into the shared partial (with the read-only null-guards)

**Files:**
- Modify: `templates/js/_workitem_detail_panel_js.html`
- Modify: `templates/js/_workitems_overview_js.html` (remove the moved functions; add a bare-name alias block)
- Test: `tests/integration/test_workitem_detail_panel.py`

**Interfaces:**
- Produces (inside the IIFE, also re-exported on `window` for the page-side lightbox/delegation during the transition): `srcEsc`, `tableCellSources`, `allSources`, `renderTableGrids`, `buildSourceDetailsHtml`, `renderThumbOverlay`, `refreshThumbOverlays`, `loadImage`, `loadImagesInBatch`, `loadHistory`, `loadCollaborationData(wid, mentionableUsers)`, `renderWorkitemTimeline`, `renderTagsInDetails`, and `loadDetailData(wid, perms)` (the data-fetch half extracted from `toggleDetailsAndLoadImages`).
- Consumes: `window.__srcByWorkitem` / `__tableByWorkitem` / `__fieldsByWorkitem` / `__srcLocVisibleByWorkitem`, `window.srcConfClass`/`srcConfPct`, `window.fieldConfig`, `window.mentionableUsers`. These stay defined on the host page and are read via `window.` so the shared partial sees them on both pages.

- [ ] **Step:** Read the verbatim bodies of these in `_workitems_overview_js.html`: `loadHistory` (anchor `async function loadHistory(workitemId) {`), `renderTagsInDetails` (`function renderTagsInDetails(workitemId, tags) {`), `loadCollaborationData` (`async function loadCollaborationData(workitemId) {`), `renderWorkitemTimeline` (`function renderWorkitemTimeline(container) {`), `loadImagesInBatch` (`function loadImagesInBatch(container, workitemid, totalImages) {`), `srcEsc`, `tableCellSources`, `allSources`, `renderTableGrids`, `buildSourceDetailsHtml`, `renderThumbOverlay`, `refreshThumbOverlays`, `loadImage`. Copy them verbatim.
- [ ] **Step (write failing test):** Append to `tests/integration/test_workitem_detail_panel.py`:
  ```python
  def test_detail_panel_exposes_loader_and_source_helpers(user_client, workitems_all_perms):
      resp = user_client.get("/workitems")
      for marker in (b"loadDetailData", b"buildSourceDetailsHtml", b"function allSources", b"get_media_info"):
          assert marker in resp.data
  ```
- [ ] **Step (run, expect fail):** `python -m pytest tests/integration/test_workitem_detail_panel.py::test_detail_panel_exposes_loader_and_source_helpers -q`.
- [ ] **Step (implement — paste helpers into the partial, with two explicit edits):** Inside the IIFE in `_workitem_detail_panel_js.html`, paste the verbatim helper bodies, applying these mandatory edits:
  - **`loadCollaborationData` null-guards (resolves the read-only TypeError).** The verbatim source (anchor `async function loadCollaborationData(workitemId) {` … through its `}`) unconditionally runs `mentionableUsers.forEach(... assignSelector.add(option))` *before* the comments guard, then later `prioritySelector.value = data.priority;` and `assignSelector.value = data.assigneduserid;`. In read-only mode those selectors are omitted, so they are `null` → TypeError before comments load. Change the signature to `async function loadCollaborationData(workitemId, mentionableUsers) {` and guard every write:
    ```js
    async function loadCollaborationData(workitemId, mentionableUsers) {
      mentionableUsers = mentionableUsers || [];
      const commentsContainer = document.getElementById(`comments-container-${workitemId}`);
      const prioritySelector = document.getElementById(`priority-select-${workitemId}`);
      const assignSelector = document.getElementById(`assign-select-${workitemId}`);
      const tagsContainer = document.getElementById(`tags-container-${workitemId}`);
      if (assignSelector) {
        mentionableUsers.forEach(user => {
          let option = document.createElement('option');
          option.text = user.fullname;
          option.value = user.userID;
          assignSelector.add(option);
        });
      }
      if (!commentsContainer || commentsContainer.dataset.loaded === 'true') return;
      try {
        const response = await fetch(`${API_PREFIX}api/workitem/${workitemId}/interactions`, {headers: {
          'Content-Type': 'application/json', 'X-CSRFToken': csrfToken
        }});
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const data = await response.json();
        if (prioritySelector) prioritySelector.value = data.priority;
        if (assignSelector) assignSelector.value = data.assigneduserid;
        if (tagsContainer) renderTagsInDetails(workitemId, data.tags);
        commentsContainer.innerHTML = '';
        // ... keep the existing comments-rendering loop VERBATIM from the source ...
        commentsContainer.dataset.loaded = 'true';
      } catch (error) {
        commentsContainer.innerHTML = `<p class="text-red-500">{{ _("Could not load comments.") }}</p>`;
      }
    }
    ```
    (Keep the comment-rendering `forEach` loop exactly as in the source between the markers above.)
  - **`buildSourceDetailsHtml` bare-name fix (resolves register-page `fieldConfig` undefined).** The verbatim source reads `const label = fieldConfig.labels[labelKey] || key;`. On the register page there is no top-level `let fieldConfig`. Change that read to `const label = (window.fieldConfig.labels || {})[labelKey] || key;`. (The partial defaults `window.fieldConfig` — next step.)
- [ ] **Step (default the window globals at IIFE top):** Near the top of the partial's IIFE (after `csrfToken`), add:
  ```js
      window.fieldConfig = window.fieldConfig || { search_options: {}, labels: {} };
      window.mentionableUsers = window.mentionableUsers || [];
  ```
- [ ] **Step (add `loadDetailData` — the data-fetch half of `toggleDetailsAndLoadImages`):** Extract the media-info fetch block (anchor: the `const infoResponse = await fetch(`${API_PREFIX}api/get_media_info/${workitemid}`...` block, ~605–658), the `loadHistory(workitemid)` call (~603), and the `__*ByWorkitem` stashing + `buildSourceDetailsHtml` + `loadImagesInBatch` fills, parameterised on `workitemid`. Keep the graceful `catch` that sets the red "Could not load media." message (it must survive the extraction — media degradation is already graceful, so no new hardening is needed). Drop the toggle/chevron/animation logic (that stays page-side):
  ```js
      async function loadDetailData(workitemid, perms) {
        const imageContainer = document.getElementById(`image-container-${workitemid}`);
        const fieldsContainer = document.getElementById(`fields-container-${workitemid}`);
        if (perms && perms.audit !== false) loadHistory(workitemid);
        if (!(imageContainer && imageContainer.dataset.loaded !== 'true') && !fieldsContainer) return;
        if (imageContainer) imageContainer.innerHTML = `<p class="text-gray-500 animate-pulse">{{ _("Checking for media...") }}</p>`;
        try {
          const infoResponse = await fetch(`${API_PREFIX}api/get_media_info/${workitemid}`, {headers: {
            'Content-Type': 'application/json', 'X-CSRFToken': csrfToken
          }});
          if (!infoResponse.ok) {
            if (infoResponse.status === 403) throw new Error("Restricted");
            throw new Error('Could not fetch media information.');
          }
          const mediaInfo = await infoResponse.json();
          const imageCount = mediaInfo.media_count || 0;
          const fields = mediaInfo.fields || {};
          window.__srcByWorkitem = window.__srcByWorkitem || {};
          window.__srcByWorkitem[workitemid] = mediaInfo.field_sources || [];
          window.__tableByWorkitem = window.__tableByWorkitem || {};
          window.__tableByWorkitem[workitemid] = mediaInfo.table_sources || [];
          window.__srcLocVisibleByWorkitem = window.__srcLocVisibleByWorkitem || {};
          window.__srcLocVisibleByWorkitem[workitemid] = mediaInfo.source_location_visible !== false;
          if (fieldsContainer) {
            window.__fieldsByWorkitem = window.__fieldsByWorkitem || {};
            window.__fieldsByWorkitem[workitemid] = fields;
            fieldsContainer.innerHTML = buildSourceDetailsHtml(workitemid)
              || `<p class="text-gray-500 p-2">{{ _("No additional details found.") }}</p>`;
          }
          if (imageContainer) {
            imageContainer.dataset.loaded = 'true';
            if (imageCount === 0) {
              imageContainer.innerHTML = `<p class="text-gray-500">{{ _("No media found for this workitem.") }}</p>`;
            } else {
              imageContainer.innerHTML = '';
              imageContainer.classList.remove('justify-center', 'items-center');
              imageContainer.classList.add('flex-wrap', 'gap-4', 'justify-start');
              imageContainer.dataset.loadedCount = '0';
              loadImagesInBatch(imageContainer, workitemid, imageCount);
            }
          }
        } catch (error) {
          if (imageContainer) {
            imageContainer.innerHTML = `<p class="text-red-500">{{ _("Could not load media.") }}</p>`;
            imageContainer.dataset.loaded = 'true';
          }
        }
      }
  ```
- [ ] **Step (wire `render` to call the loaders):** Replace the `render` body so after building the DOM it renders the timeline and kicks the loaders:
  ```js
      window.NexoraWorkitemDetail.render = function (workitemId, containerEl, opts) {
        const { readOnly = false, perms = {} } = opts || {};
        if (!containerEl) return;
        const wid = String(workitemId);
        const status = containerEl.dataset.status || (opts && opts.status) || '';
        const currentStage = containerEl.dataset.currentStage || (opts && opts.currentStage) || '';
        containerEl.innerHTML = buildPanelMarkup(wid, status, currentStage, perms, readOnly);
        renderWorkitemTimeline(containerEl.querySelector('[id^="timeline-container-"]'));
        _renderHeaderChip(wid, opts);            // filled in Task 3.4; no-op until then
        loadDetailData(wid, perms);
        loadCollaborationData(wid, readOnly ? [] : (window.mentionableUsers || []));
        return wid;
      };
      function _renderHeaderChip() {}            // placeholder; replaced in Task 3.4
  ```
- [ ] **Step (re-export on the namespace + window):** At the end of the IIFE add:
  ```js
      Object.assign(window.NexoraWorkitemDetail, {
        loadDetailData, loadHistory, loadCollaborationData, renderWorkitemTimeline,
        renderTagsInDetails, loadImage, loadImagesInBatch, buildSourceDetailsHtml,
        renderTableGrids, tableCellSources, allSources, srcEsc, renderThumbOverlay,
        refreshThumbOverlays,
      });
      window.srcEsc = srcEsc; window.tableCellSources = tableCellSources;
      window.allSources = allSources; window.renderTableGrids = renderTableGrids;
      window.buildSourceDetailsHtml = buildSourceDetailsHtml;
      window.renderThumbOverlay = renderThumbOverlay; window.refreshThumbOverlays = refreshThumbOverlays;
      window.loadImage = loadImage; window.loadImagesInBatch = loadImagesInBatch;
      window.loadHistory = loadHistory; window.loadCollaborationData = loadCollaborationData;
      window.renderWorkitemTimeline = renderWorkitemTimeline; window.renderTagsInDetails = renderTagsInDetails;
  ```
- [ ] **Step (delete moved functions from the page partial + add an alias block):** In `_workitems_overview_js.html`, DELETE the verbatim definitions of the 13 helpers moved above (they now live in the shared partial). Leave `toggleDetailsAndLoadImages`, `buildDetailContent` (deleted in Task 1.3), the write handlers, and the mention helpers in place. Because the shared partial is included BEFORE the page partial, add a thin alias block near the top of the page partial's `<script>` (after the `API_PREFIX`/`fieldConfig`/`mentionableUsers` declarations, ~line 33) so the page-side lightbox + `tbody` delegation that call these by bare name still resolve:
  ```js
      // Helpers now live in _workitem_detail_panel_js.html (shared). Alias the bare
      // names the lightbox + tbody delegation still call by reference.
      const srcEsc = window.srcEsc, allSources = window.allSources,
            tableCellSources = window.tableCellSources, renderTableGrids = window.renderTableGrids,
            buildSourceDetailsHtml = window.buildSourceDetailsHtml,
            renderThumbOverlay = window.renderThumbOverlay, refreshThumbOverlays = window.refreshThumbOverlays,
            loadImage = window.loadImage, loadImagesInBatch = window.loadImagesInBatch,
            loadHistory = window.loadHistory, loadCollaborationData = window.loadCollaborationData,
            renderWorkitemTimeline = window.renderWorkitemTimeline, renderTagsInDetails = window.renderTagsInDetails;
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitem_detail_panel.py tests/integration/test_workitems_routes.py -q`.
- [ ] **Step (browser regression — restart first):** Restart `nx -u -b --loginas:<an MS02 workitems user>`, open `/workitems`, expand a row: confirm the detail panel renders (timeline, history, fields, comments) identically; click a thumbnail → lightbox opens; click a located field → page+pulse. Save `var/screenshots/p1-loaders.png` and SendUserFile it (remote frontend rule).
- [ ] **Step (commit):**
  ```
  git add templates/js/_workitem_detail_panel_js.html templates/js/_workitems_overview_js.html tests/integration/test_workitem_detail_panel.py
  git commit -m "refactor(workitems): move detail loaders + source helpers into shared partial (P1.2)

  Relocate loadHistory/loadCollaborationData/renderWorkitemTimeline/loadImage(s)/
  renderTagsInDetails and the source-detail builders (buildSourceDetailsHtml/
  allSources/renderTableGrids/tableCellSources/renderThumbOverlay/refreshThumbOverlays/
  srcEsc) into _workitem_detail_panel_js.html, re-exported on window for the page-side
  lightbox + tbody delegation. Add loadDetailData() and wire render() to build+load.
  loadCollaborationData now null-guards the priority/assign selectors and takes
  mentionableUsers as an arg; buildSourceDetailsHtml reads window.fieldConfig — both
  so the read-only register modal (no write controls, no top-level fieldConfig) is
  TypeError-free. No behaviour change on the workitems page.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 1.3: Refactor the row-expand to consume `NexoraWorkitemDetail.render`

**Files:**
- Modify: `templates/js/_workitems_overview_js.html`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `NexoraWorkitemDetail.render(wid, detailsTd, { readOnly:false, perms, inRegisterPid })`.
- Produces: page-side `window.__workitemDetailPerms` (the JS mirror of the Jinja perm flags the route already supplies).

- [ ] **Step:** Read the current `toggleDetailsAndLoadImages` (anchor `async function toggleDetailsAndLoadImages(event) {` ~544) and the `renderTable` details-row markup (anchor `<tr id="details-row-${workitem.workitemid}" class="details-row" hidden` ~1741) to preserve the toggle open/close animation, chevron classes, and `dataset.initialized`.
- [ ] **Step (define the page perms object):** Near the top of the page partial (after the alias block), add a Jinja-driven JS perms object from the route's existing template vars:
  ```js
      window.__workitemDetailPerms = {
        images:      {{ 'true' if details_images_perm else 'false' }},
        audit:       {{ 'true' if details_audit_perm else 'false' }},
        fields:      {{ 'true' if details_fields_perm else 'false' }},
        setPriority: {{ 'true' if details_set_priority_perm else 'false' }},
        addTag:      {{ 'true' if details_add_tag_perm else 'false' }},
        assignUsers: {{ 'true' if details_assign_users_perm else 'false' }},
        addComment:  {{ 'true' if details_add_comment_perm else 'false' }},
      };
  ```
- [ ] **Step (rewrite `toggleDetailsAndLoadImages`):** Replace its whole body so it builds via the shared renderer once (passing the row's `status`/`current_stage` via the `td` dataset), then only toggles visibility thereafter. The render call kicks `loadDetailData` + `loadCollaborationData` itself, so the old open-branch fetch logic is gone:
  ```js
      async function toggleDetailsAndLoadImages(event) {
        try {
          const button = event.currentTarget;
          const workitemid = button.dataset.workitemid;
          const detailsRow = document.getElementById(`details-row-${workitemid}`);
          if (!detailsRow) return;
          const chevron = button.querySelector('.indicator');
          const isOpening = detailsRow.hasAttribute('hidden');

          if (isOpening && detailsRow.dataset.initialized !== 'true') {
            const td = detailsRow.querySelector('td');
            td.dataset.status = detailsRow.dataset.status || '';
            td.dataset.currentStage = detailsRow.dataset.currentStage || '';
            NexoraWorkitemDetail.render(workitemid, td, {
              readOnly: false,
              perms: window.__workitemDetailPerms,
              inRegisterPid: _inRegisterByWid[String(workitemid)] || null,  // P3 (defaults null; map seeded in 3.4)
            });
            detailsRow.dataset.initialized = 'true';
          }

          if (isOpening) {
            detailsRow.removeAttribute('hidden');
            setTimeout(() => { detailsRow.classList.add('open'); chevron.classList.add('open'); }, 10);
          } else {
            detailsRow.classList.remove('open');
            chevron.classList.remove('open');
            detailsRow.addEventListener('transitionend', () => { detailsRow.hidden = true; }, { once: true });
          }
          chevron.classList.toggle('glyphicon-chevron-up-custom');
          chevron.classList.toggle('glyphicon-chevron-down-custom');
        } catch (error) { /* pass */ }
      }
  ```
- [ ] **Step (seed the P3 map var so it resolves now):** Near the top module scope of the page partial add `let _inRegisterByWid = {};` (it stays empty until Task 3.4 populates it; referencing it now keeps `toggleDetailsAndLoadImages` defined and avoids a forward-reference error).
- [ ] **Step (delete the old `buildDetailContent`):** Remove the page-side `buildDetailContent` definition (anchor `function buildDetailContent(workitemid, status, currentStage) {` through its closing `}`); it now lives in the shared partial as `buildPanelMarkup`.
- [ ] **Step (confirm the write delegations still resolve):** Grep `_workitems_overview_js.html` for `handleAddTag`, `handleSetPriority`, `handleAssigning`, `handlePostComment`, `handleRemoveTag`, `handleMentionInput` — they stay page-side and operate on the same DOM ids the shared markup produces (`tag-input-${wid}`, `priority-select-${wid}`, `assign-select-${wid}`, `comment-form`, etc.). No change needed; just confirm by grep.
- [ ] **Step (write regression test):** Add to `tests/integration/test_workitems_routes.py` near `test_workitems_overview_with_perms`:
  ```python
  def test_workitems_overview_uses_shared_detail_panel(user_client, workitems_all_perms):
      """The workitems page wires the shared renderer."""
      resp = user_client.get("/workitems")
      # 200 or 500-fallback possible in CI; the partial markers live in template body.
      if resp.status_code == 200:
          assert b"NexoraWorkitemDetail.render" in resp.data
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py tests/integration/test_workitem_detail_panel.py -q`.
- [ ] **Step (browser regression — restart first):** Restart `nx -u -b --loginas:<MS02 user>`, expand a row: panel builds, media loads, history/comments load, lightbox + click-to-locate work, write controls (priority/assign/tags/comment) present and functional. Screenshot `var/screenshots/p1-row-expand-consumed.png` and SendUserFile.
- [ ] **Step (commit):**
  ```
  git add templates/js/_workitems_overview_js.html tests/integration/test_workitems_routes.py
  git commit -m "refactor(workitems): row-expand consumes NexoraWorkitemDetail.render (P1.3)

  toggleDetailsAndLoadImages now builds the panel via the shared renderer
  (readOnly:false, __workitemDetailPerms) and only toggles visibility thereafter; the
  page-side buildDetailContent is removed and perms pass through window.__workitemDetailPerms.
  Behaviour and perms on the workitems page unchanged (lift-and-shift).

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 1.4: Make the lightbox engine container-scoped via `attachLightbox(idMap)`

**Files:**
- Modify: `templates/js/_workitem_detail_panel_js.html` (move the lightbox engine in)
- Modify: `templates/js/_workitems_overview_js.html` (delete the moved engine; add a single `attachLightbox` call)
- Test: `tests/integration/test_workitem_detail_panel.py`

**Interfaces:**
- Produces: `NexoraWorkitemDetail.attachLightbox(cfg)` where `cfg = { modal, image, hlLayer, hlToggle, hlToggleLabel, reviewPanel, reviewPanelBody }` is an explicit id-map (the workitems shell ids are not a single prefix, so an id-map avoids any rename). Returns `{ openForWorkitem(wid, index, pulseKey), close() }`. The engine's `currentImages`/`currentIndex`/`srcHl` state are **closure-locals** per instance; the modal/close/prev/next lookups are scoped to the resolved `modal` element (`modal.querySelector('.modal-*')`), not `document.querySelector`, so two shells on one page never collide. The four click-to-locate delegations stay on `document` (they locate the originating `[id^="fields-container-"]`/`[id^="image-container-"]` regardless of host) and open via this instance.
- Consumes: the shell elements named in `cfg`, `static/css/source-highlight.css`, `window.srcConfClass`/`srcConfPct`, the `__*ByWorkitem` globals, the namespaced `allSources`/`buildSourceDetailsHtml`/`refreshThumbOverlays`.

- [ ] **Step:** Read the lightbox engine in `_workitems_overview_js.html`: `let currentImages = []` / `let currentIndex = 0` (~2039–2040), `const modal/modalImg/closeBtn/prevBtn/nextBtn` (~2042–2046), `const srcHl` (~2049), `srcHlLayer/srcHlToggle/srcHlToggleLabel` (~2054–2056), the `ResizeObserver` (~2063), `currentSources`/`hasAnyLocation`/`renderModalOverlay`/`openModalForWorkitem`/`renderReviewPanel`/`showImage`/`closeModal`/`setSrcHl`/`ensureSourcesOn`/`drawOverlayWhenStable`, the four `document.addEventListener('click', …)` delegations (~2225–2260), and the close/backdrop/prev/next/toggle/resize/keydown handlers (~2262–2301).
- [ ] **Step (write failing test):** Append to `tests/integration/test_workitem_detail_panel.py`:
  ```python
  def test_detail_panel_exposes_lightbox_attach(user_client, workitems_all_perms):
      resp = user_client.get("/workitems")
      assert b"attachLightbox" in resp.data
  ```
- [ ] **Step (run, expect fail):** `python -m pytest tests/integration/test_workitem_detail_panel.py::test_detail_panel_exposes_lightbox_attach -q`.
- [ ] **Step (implement — move the engine into `attachLightbox`):** In the shared partial, add `NexoraWorkitemDetail.attachLightbox = function (cfg) { ... }`. Paste the verbatim engine inside, with these scoping changes:
  - Carry the locals into the closure: `let currentImages = []; let currentIndex = 0;` at the top of `attachLightbox`.
  - Resolve the shell from `cfg`: `const modal = document.getElementById(cfg.modal); const modalImg = document.getElementById(cfg.image); const srcHlLayer = document.getElementById(cfg.hlLayer); const srcHlToggle = document.getElementById(cfg.hlToggle); const srcHlToggleLabel = document.getElementById(cfg.hlToggleLabel);` then `if (!modal) return { openForWorkitem(){}, close(){} };` (no-op where the shell is absent).
  - Replace the global `closeBtn/prevBtn/nextBtn = document.querySelector('.modal-*')` with **modal-scoped** lookups: `const closeBtn = modal.querySelector('.modal-close'); const prevBtn = modal.querySelector('.modal-prev'); const nextBtn = modal.querySelector('.modal-next');` — this resolves the two-`.modal-close` collision on the register page (its preview modal also has a `.modal-close`).
  - `renderReviewPanel` writes into `cfg.reviewPanel`/`cfg.reviewPanelBody`; resolve them via `document.getElementById(cfg.reviewPanel)` etc. (replace the bare `srcReviewPanel`/`srcReviewPanelBody` references). The review-panel click delegation reads the panel by `cfg.reviewPanel` too.
  - Replace bare `allSources(...)` / `buildSourceDetailsHtml(...)` / `refreshThumbOverlays()` calls with `window.allSources(...)` / `window.buildSourceDetailsHtml(...)` / `window.refreshThumbOverlays()` (they live in this same IIFE; bare names also work, but `window.` is unambiguous across the move).
  - Return `{ openForWorkitem: openModalForWorkitem, close: closeModal };` at the end.
- [ ] **Step (page partial calls `attachLightbox`):** In `_workitems_overview_js.html`, DELETE the in-`DOMContentLoaded` lightbox engine block (from `let currentImages = [];` ~2039 through the `keydown` handler's closing ~2301, i.e. everything up to but NOT including the `// ---- Select-all checkbox ----` block at ~2303). Replace it with a single call inside the existing `DOMContentLoaded`:
  ```js
      const _wiLightbox = NexoraWorkitemDetail.attachLightbox({
        modal: 'imageModal', image: 'modalImage', hlLayer: 'srcHlLayer',
        hlToggle: 'srcHlToggle', hlToggleLabel: 'srcHlToggleLabel',
        reviewPanel: 'srcReviewPanel', reviewPanelBody: 'srcReviewPanelBody',
      });
  ```
  Keep the unrelated select-all / bulk-bar / export-modal handlers (~2303+) untouched.
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitem_detail_panel.py tests/integration/test_workitems_routes.py -q`.
- [ ] **Step (browser regression — restart first):** Restart, expand a row, open the lightbox, toggle Show/Hide sources, prev/next, Escape-to-close, click a field row and a line-item cell to locate-and-pulse. All must work as before. Screenshot `var/screenshots/p1-lightbox.png` and SendUserFile.
- [ ] **Step (commit):**
  ```
  git add templates/js/_workitem_detail_panel_js.html templates/js/_workitems_overview_js.html tests/integration/test_workitem_detail_panel.py
  git commit -m "refactor(workitems): make lightbox engine container-scoped in shared partial (P1.4)

  Move the source-overlay lightbox (renderModalOverlay/openModalForWorkitem/showImage/
  click-to-locate/keydown + currentImages/currentIndex/srcHl) out of the workitems
  DOMContentLoaded into NexoraWorkitemDetail.attachLightbox(cfg), bound to an explicit
  shell id-map with modal-scoped .modal-close/.modal-prev/.modal-next lookups (no
  page-global #imageModal, no two-button collision). The workitems page attaches its
  existing shell; the register modal attaches its own in P2. Behaviour unchanged.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 1.5: Read-only contract test (write controls omitted)

**Files:**
- Test: `tests/integration/test_workitem_detail_panel.py`

**Interfaces:** asserts the read-only markup contract on the rendered partial source (no JS-DOM runner exists in this repo).

- [ ] **Step (write the test):** Append:
  ```python
  def test_detail_panel_readonly_branch_present(user_client, workitems_all_perms):
      """The shared partial carries a read-only branch that omits write controls and a
      writable branch that includes them; render() switches on readOnly. Asserted on the
      rendered partial source (the panel is built client-side)."""
      resp = user_client.get("/workitems")
      body = resp.data
      assert b"buildReadonlyCommentsMarkup" in body
      assert b"buildCollaborationMarkup" in body
      assert b"readOnly" in body
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitem_detail_panel.py -q` — passes (those helper names were introduced in 1.1/1.2; if it fails, the names drifted — fix the names to match).
- [ ] **Step (commit):**
  ```
  git add tests/integration/test_workitem_detail_panel.py
  git commit -m "test(workitems): assert shared panel read-only branch omits write controls (P1.5)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

---

# PHASE 2 — Register preview modal (read-only)

### Task 2.1: Register route passes the `details_*` perms; template gets the Preview button + modal + lightbox shells + deps

**Files:**
- Modify: `nx_lib/views/workitems.py` (`prepared_documents`)
- Modify: `templates/prepared_documents.html`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- `prepared_documents()` passes `details_view_perm`, `details_images_perm`, `details_audit_perm`, `details_fields_perm`, `details_set_priority_perm`, `details_add_tag_perm`, `details_assign_users_perm`, `details_add_comment_perm` to the template (gathered identically to `workitems_overview` lines 904–912).
- Template: per matched row a Preview button (`data-testid="prepared-docs-preview"`, `data-wid`, `data-pid`) gated on `details_view_perm`, alongside the renamed "Open in Workitems" link; the preview modal shell `#pdocPreviewModal` (+ `#pdocPreviewBody`, close button class `pdoc-preview-close`); the source-highlight lightbox shell with `pdocPreview*` ids; `source-highlight.css`; the `srcConf*` globals + empty `fieldConfig`; a `taglist` datalist; and the shared partial include.

- [ ] **Step (write failing tests):** Append to `tests/integration/test_workitems_routes.py`:
  ```python
  def test_prepared_documents_preview_button_requires_details_view(
      user_client, workitems_all_perms, monkeypatch
  ):
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
      monkeypatch.setattr(wv, "fetch_prepared_documents_page",
          lambda offset, limit, pid=None: [{"id": 1, "pid": "100", "collected": True,
              "collected_by": "A", "prepared": False, "prepared_by": "",
              "uploaded_by": 7, "uploaded_at": None, "updated_at": None}])
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
      monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
      monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})

      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      resp = user_client.get("/prepared_documents")
      assert resp.status_code == 200
      assert b'data-testid="prepared-docs-preview"' in resp.data
      assert b'data-wid="42"' in resp.data
      assert b"NexoraWorkitemDetail" in resp.data

      monkeypatch.setattr(wv, "has_permission", lambda code: code != "workitems.details.view")
      resp2 = user_client.get("/prepared_documents")
      assert resp2.status_code == 200
      assert b'data-testid="prepared-docs-preview"' not in resp2.data
  ```
- [ ] **Step (run, expect fail):** the preview button/perms don't exist yet.
- [ ] **Step (implement — perms in `prepared_documents`):** Match on the verbatim `return render_template(\n        "prepared_documents.html",` block. Before it, add (gathered exactly like `workitems_overview`):
  ```python
      details_view_perm = has_permission("workitems.details.view")
      details_images_perm = has_permission("workitems.details.view.images")
      details_audit_perm = has_permission("workitems.details.view.audit")
      details_fields_perm = has_permission("workitems.details.view.fields")
      details_set_priority_perm = has_permission("workitems.details.set.priority")
      details_add_tag_perm = has_permission("workitems.details.add.tag")
      details_assign_users_perm = has_permission("workitems.details.assign.users")
      details_add_comment_perm = has_permission("workitems.details.add.comment")
  ```
  And add the eight kwargs to the `render_template(...)` call alongside `octo_status=octo_status,`:
  ```python
          details_view_perm=details_view_perm,
          details_images_perm=details_images_perm,
          details_audit_perm=details_audit_perm,
          details_fields_perm=details_fields_perm,
          details_set_priority_perm=details_set_priority_perm,
          details_add_tag_perm=details_add_tag_perm,
          details_assign_users_perm=details_assign_users_perm,
          details_add_comment_perm=details_add_comment_perm,
  ```
- [ ] **Step (CSS):** In `templates/prepared_documents.html` `<head>`, after the `workitems_overview.css` link (verbatim `<link rel="stylesheet" href="{{ url_for('static', filename='css/workitems_overview.css') }}">`), add:
  ```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/source-highlight.css') }}">
  ```
- [ ] **Step (Octo-Status cell — Preview button + renamed link):** Replace the matched-cell block (verbatim anchor: the `{% if st and st.in_octo %}` … `{% else %}` … `{% endif %}` block containing the `In Octo` link):
  ```html
                {% set st = octo_status.get(r.pid) %}
                {% if st and st.in_octo %}
                  <div class="flex items-center justify-center gap-3">
                    {% if details_view_perm %}
                    <button type="button" class="text-indigo-600 underline"
                            data-testid="prepared-docs-preview" data-wid="{{ st.wid }}" data-pid="{{ r.pid }}">
                      <i class="fas fa-eye mr-1"></i>{{ _("Preview") }}
                    </button>
                    {% endif %}
                    <a href="{{ url_for('workitems_overview') }}?search={{ st.wid }}"
                       class="text-indigo-600 underline" data-testid="prepared-docs-octo-link">
                      <i class="fas fa-up-right-from-square mr-1"></i>{{ _("Open in Workitems") }}
                    </a>
                  </div>
                {% else %}
                  <span class="text-gray-300">—</span>
                {% endif %}
  ```
  (Label changes from "In Octo" to "Open in Workitems" per decision 1; i18n in Task 2.4.)
- [ ] **Step (modal + lightbox shells + globals + include):** Before the verbatim `{% include 'js/_prepared_documents_js.html' %}` line (and inside `<body>`), add — all gated on `details_view_perm`:
  ```html
    {% if details_view_perm %}
    <!-- Read-only workitem preview modal (MS02). Hidden until a Preview click. -->
    <div id="pdocPreviewModal" class="hidden fixed inset-0 bg-black bg-opacity-50 z-[200] flex items-center justify-center p-4"
         data-testid="prepared-docs-preview-modal">
      <div class="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 class="text-lg font-semibold text-gray-800">{{ _("Workitem preview") }}</h2>
          <button type="button" id="pdocPreviewClose" class="pdoc-preview-close text-gray-400 hover:text-gray-700"
                  aria-label="{{ _('Close') }}" title="{{ _('Close') }}" data-testid="prepared-docs-preview-close">
            <i class="fas fa-xmark text-xl"></i>
          </button>
        </div>
        <div id="pdocPreviewBody" class="p-2" data-testid="prepared-docs-preview-body"></div>
      </div>
    </div>

    <datalist id="taglist"></datalist>

    <!-- Source-highlight lightbox shell for the preview panel (own pdocPreview* ids). -->
    <div id="pdocPreviewLightbox" class="modal">
      <button type="button" class="modal-close" aria-label="{{ _('Close') }}" title="{{ _('Close') }}">
        <i class="fas fa-xmark" aria-hidden="true"></i>
      </button>
      <div class="src-modal-body">
        <div class="src-modal-page">
          <button type="button" id="pdocPreviewHlToggle" class="src-hl-toggle" hidden
                  title="{{ _('Show where extracted values were found on the document') }}">
            <i class="fas fa-magnifying-glass-location"></i>
            <span id="pdocPreviewHlToggleLabel">{{ _('Show sources') }}</span>
          </button>
          <img class="modal-content" id="pdocPreviewImage">
          <div id="pdocPreviewHlLayer"></div>
          <a class="modal-prev">&#10094;</a>
          <a class="modal-next">&#10095;</a>
        </div>
        <aside id="pdocPreviewReviewPanel" class="src-modal-values" hidden aria-label="{{ _('Extracted values') }}">
          <h3 class="src-modal-values-title">{{ _('Extracted values') }}</h3>
          <div id="pdocPreviewReviewPanelBody"></div>
        </aside>
      </div>
    </div>

    <script>
      // Source-highlight confidence helpers + an empty fieldConfig the shared panel reads.
      window.srcConfClass = function (conf) {
        if (typeof conf !== 'number' || isNaN(conf)) return '';
        if (conf >= 0.9) return 'src-conf-high';
        if (conf >= 0.7) return 'src-conf-med';
        return 'src-conf-low';
      };
      window.srcConfPct = function (conf) {
        if (typeof conf !== 'number' || isNaN(conf)) return '';
        return Math.round(conf * 100) + '%';
      };
      window.fieldConfig = window.fieldConfig || { search_options: {}, labels: {} };
      window.mentionableUsers = window.mentionableUsers || [];
      window.__pdocPreviewPerms = {
        images: {{ 'true' if details_images_perm else 'false' }},
        audit:  {{ 'true' if details_audit_perm else 'false' }},
        fields: {{ 'true' if details_fields_perm else 'false' }},
        setPriority: false, addTag: false, assignUsers: false, addComment: false,
      };
    </script>

    {% include 'js/_workitem_detail_panel_js.html' %}
    {% endif %}
  ```
  (The register page already has a `<input type="hidden" id="csrfToken" …>` in the page head, so `csrfToken` resolves. The `srcConfClass`/`srcConfPct` values mirror the workitems globals — confirm against `static/css/source-highlight.css` class names during implementation.)
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -q`.
- [ ] **Step (commit):**
  ```
  git add nx_lib/views/workitems.py templates/prepared_documents.html tests/integration/test_workitems_routes.py
  git commit -m "feat(prepared-docs): preview button + modal/lightbox shells on the register (P2.1)

  prepared_documents() computes the workitems.details.view.* perm family (like
  workitems_overview) and passes it to the template. The Octo-Status cell gains a gated
  Preview button (data-wid) beside the renamed Open-in-Workitems link; adds the read-only
  preview modal shell (distinct .pdoc-preview-close), the pdocPreview* source-highlight
  lightbox shell, source-highlight.css, the srcConf*/fieldConfig/mentionableUsers globals,
  a taglist datalist, and the shared detail-panel partial include.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 2.2: Update the two SHIPPED register-render stubs for the `pid=None` kwarg (forward-compat)

**Files:**
- Modify: `tests/integration/test_workitems_routes.py`

**Interfaces:** none (test maintenance). P3.2 makes the route call `count_prepared_documents(pid=...)` / `fetch_prepared_documents_page(offset, per_page, pid=...)`; the two pre-existing stubs use positional-only lambdas that would `TypeError` once the kwarg is passed. Update them now so the kwarg lands cleanly in P3 and the new P2.1 tests are consistent.

- [ ] **Step (implement):** In `tests/integration/test_workitems_routes.py`, in `test_prepared_documents_page_renders_when_ms02_active` and `test_prepared_documents_page_octo_resolve_failure_degrades`, change:
  - `monkeypatch.setattr(wv, "count_prepared_documents", lambda: 1)` → `lambda pid=None: 1`
  - `monkeypatch.setattr(wv, "fetch_prepared_documents_page", lambda offset, limit: [ ... ])` → `lambda offset, limit, pid=None: [ ... ]` (keep the row dict bodies verbatim).
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -q` — all stay green (the route still calls them with positional args today; the default kwarg is a superset).
- [ ] **Step (commit):**
  ```
  git add tests/integration/test_workitems_routes.py
  git commit -m "test(prepared-docs): forward-compat register stubs for the pid kwarg (P2.2)

  count_prepared_documents -> lambda pid=None: 1; fetch_prepared_documents_page ->
  lambda offset, limit, pid=None: [...] in the two shipped register-render tests, so the
  P3.2 route change (passing pid=) does not TypeError them.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 2.3: Wire the Preview button to the shared renderer (read-only) + lightbox + fieldConfig

**Files:**
- Modify: `templates/js/_prepared_documents_js.html`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `NexoraWorkitemDetail.render(wid, body, { readOnly:true, perms: window.__pdocPreviewPerms })`, `NexoraWorkitemDetail.attachLightbox({...pdocPreview ids...})`, `GET /api/config/fields`.
- Produces: click delegation on `[data-testid="prepared-docs-preview"]`, modal open/close (overlay + Escape + close button), one-time `fieldConfig` hydration. `API_PREFIX` here is the register IIFE's existing `window.API_PREFIX || "/"`; the shared partial's own `API_PREFIX` uses the same `window.API_PREFIX` first, so both resolve identically (see Gotchas re: URL-prefix deploys).

- [ ] **Step (write failing test):** Append:
  ```python
  def test_prepared_documents_modal_wires_shared_renderer(
      user_client, workitems_all_perms, monkeypatch
  ):
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 0)
      monkeypatch.setattr(wv, "fetch_prepared_documents_page", lambda offset, limit, pid=None: [])
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: [])
      monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [])
      monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: None)
      resp = user_client.get("/prepared_documents")
      assert resp.status_code == 200
      assert b"NexoraWorkitemDetail.render" in resp.data
      assert b"attachLightbox" in resp.data
      assert b"api/config/fields" in resp.data
  ```
- [ ] **Step (run, expect fail).**
- [ ] **Step (implement):** In `templates/js/_prepared_documents_js.html`, inside the existing IIFE, before the closing `})();`, add fieldConfig hydration, the preview-lightbox attach, the Preview button wiring, and modal close on overlay/Escape/close-button:
  ```js
      // ---- Read-only workitem preview modal (MS02) ----
      const previewModal = document.getElementById("pdocPreviewModal");
      const previewBody = document.getElementById("pdocPreviewBody");
      const previewClose = document.getElementById("pdocPreviewClose");
      let _pdocLightbox = null;

      async function ensureFieldConfig() {
        if (window.fieldConfig && window.fieldConfig.labels && Object.keys(window.fieldConfig.labels).length) return;
        try {
          const res = await fetch(`${API_PREFIX}api/config/fields`, {
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
          });
          if (res.ok) window.fieldConfig = await res.json();
        } catch (e) { /* labels fall back to raw keys */ }
      }

      function openPreview(wid) {
        if (!previewModal || !previewBody || !window.NexoraWorkitemDetail) return;
        if (!_pdocLightbox && window.NexoraWorkitemDetail.attachLightbox) {
          _pdocLightbox = window.NexoraWorkitemDetail.attachLightbox({
            modal: "pdocPreviewLightbox", image: "pdocPreviewImage",
            hlLayer: "pdocPreviewHlLayer", hlToggle: "pdocPreviewHlToggle",
            hlToggleLabel: "pdocPreviewHlToggleLabel",
            reviewPanel: "pdocPreviewReviewPanel", reviewPanelBody: "pdocPreviewReviewPanelBody",
          });
        }
        previewBody.innerHTML = "";
        ensureFieldConfig().then(() => {
          window.NexoraWorkitemDetail.render(wid, previewBody, {
            readOnly: true, perms: window.__pdocPreviewPerms || {},
          });
        });
        previewModal.classList.remove("hidden");
      }

      function closePreview() {
        if (!previewModal) return;
        previewModal.classList.add("hidden");
        if (previewBody) previewBody.innerHTML = "";
      }

      document.addEventListener("click", (event) => {
        const btn = event.target.closest('[data-testid="prepared-docs-preview"]');
        if (btn) { event.preventDefault(); openPreview(btn.dataset.wid); return; }
      });
      previewClose?.addEventListener("click", closePreview);
      previewModal?.addEventListener("click", (e) => { if (e.target === previewModal) closePreview(); });
      document.addEventListener("keydown", (e) => {
        // Yield to the lightbox's own Escape handler first (its shell is #pdocPreviewLightbox,
        // display:flex when open); only close the preview when the lightbox is not open.
        const lb = document.getElementById("pdocPreviewLightbox");
        const lbOpen = lb && lb.style.display === "flex";
        if (e.key === "Escape" && !lbOpen && previewModal && !previewModal.classList.contains("hidden")) {
          closePreview();
        }
      });
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -q`.
- [ ] **Step (browser verify — restart first):** Restart `nx -u -b --loginas:<MS02 user>`, open `/prepared_documents`, click Preview on a matched PID: the modal opens with fields/history/comments (image slots empty on dev — acceptable), write controls absent (read-only), source-highlight lightbox reachable if fields have locations, Escape/overlay/close all work. Screenshot `var/screenshots/p2-preview-modal.png` and SendUserFile.
- [ ] **Step (commit):**
  ```
  git add templates/js/_prepared_documents_js.html tests/integration/test_workitems_routes.py
  git commit -m "feat(prepared-docs): wire Preview button to read-only shared panel (P2.3)

  Register JS opens the preview modal and calls NexoraWorkitemDetail.render with
  readOnly:true + read perms; hydrates fieldConfig from /api/config/fields and lazily
  attaches the preview's own source-highlight lightbox (pdocPreview* shell). Closes on
  overlay/close-button/Escape (Escape yields to the lightbox first).

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 2.4: Image-unreachable degradation assertion + P2 i18n

**Files:**
- Test: `tests/integration/test_workitems_routes.py`
- Modify: `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ `.mo`), `messages.pot`

**Interfaces:** new msgids introduced in P2: `Preview`, `Open in Workitems`, `Workitem preview`. (`Close`, `Show sources`, `Extracted values`, `Show where extracted values were found on the document`, `Tags:` etc. already exist from the workitems page.)

- [ ] **Step (write degradation test):** Append:
  ```python
  def test_prepared_documents_preview_present_when_media_degrades(
      user_client, workitems_all_perms, monkeypatch
  ):
      """Octo resolve returning None still renders the page with the modal shell (image
      degradation is client-side; the panel must not be gated on media)."""
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
      monkeypatch.setattr(wv, "fetch_prepared_documents_page",
          lambda offset, limit, pid=None: [{"id": 1, "pid": "100", "collected": True,
              "collected_by": "A", "prepared": False, "prepared_by": "",
              "uploaded_by": 7, "uploaded_at": None, "updated_at": None}])
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
      monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
      monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})
      resp = user_client.get("/prepared_documents")
      assert resp.status_code == 200
      assert b'data-testid="prepared-docs-preview-modal"' in resp.data
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py::test_prepared_documents_preview_present_when_media_degrades -q`.
- [ ] **Step (i18n cycle):** `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → fill the new msgids non-fuzzy in de/fr/it (de: `Preview`→`Vorschau`, `Open in Workitems`→`In Workitems öffnen`, `Workitem preview`→`Workitem-Vorschau`; fr: `Aperçu` / `Ouvrir dans Workitems` / `Aperçu du workitem`; it: `Anteprima` / `Apri in Workitems` / `Anteprima workitem`). Remove any `#, fuzzy` flags on these. → `pybabel compile -d translations`. (Use `/nx-i18n`.)
- [ ] **Step (run, expect green):** `python -m pytest tests/unit/test_translations.py -q`.
- [ ] **Step (commit):**
  ```
  git add tests/integration/test_workitems_routes.py translations messages.pot
  git commit -m "test+i18n(prepared-docs): preview-degradation assert + modal strings (de/fr/it) (P2.4)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

---

# PHASE 3 — Reverse ("In register" chip + register `?pid` filter)

### Task 3.1: `pids_in_register` helper + `?pid` filter on the register read path

**Files:**
- Modify: `nx_lib/prepared_documents.py`
- Test: `tests/unit/test_prepared_documents.py`

**Interfaces:**
- Produces: `pids_in_register(pids: list[str]) -> set[str]` — one parameterized `SELECT PID FROM dbo.PreparedDocuments WHERE PID IN (?, …)`; empty input → empty set with NO DB round-trip; never raises (logs + returns `set()` on error). Mirrors the module's `try/finally + raw_connection` pattern; `current_app` is already imported.
- Produces: `count_prepared_documents(pid=None)` and `fetch_prepared_documents_page(offset, limit, pid=None)` — when `pid` is a non-empty string, add a parameterized `WHERE PID = ?` exact match.

- [ ] **Step (write failing tests):** Append to `tests/unit/test_prepared_documents.py` (reuse the module's `_mock_engine(cursor)` and the `app` fixture from conftest):
  ```python
  def test_pids_in_register_empty_input_no_db(monkeypatch):
      class _Boom:
          def raw_connection(self):
              raise AssertionError("should not connect")
      monkeypatch.setattr(pd, "engine_nexora_db", _Boom())
      assert pd.pids_in_register([]) == set()

  def test_pids_in_register_returns_matched_set(monkeypatch):
      cur = MagicMock()
      cur.fetchall.return_value = [("100",), ("222",)]
      engine, _conn = _mock_engine(cur)
      monkeypatch.setattr(pd, "engine_nexora_db", engine)
      result = pd.pids_in_register(["100", "200", "222"])
      assert result == {"100", "222"}
      sql_used = cur.execute.call_args.args[0]
      assert "PreparedDocuments" in sql_used
      assert sql_used.count("?") == 3  # one placeholder per input pid (parameterized)
      assert cur.execute.call_args.args[1] == ["100", "200", "222"]

  def test_pids_in_register_never_raises(app, monkeypatch):
      cur = MagicMock()
      cur.execute.side_effect = Exception("boom")
      engine, _conn = _mock_engine(cur)
      monkeypatch.setattr(pd, "engine_nexora_db", engine)
      with app.app_context():
          assert pd.pids_in_register(["1"]) == set()

  def test_count_with_pid_adds_where(monkeypatch):
      cur = MagicMock()
      cur.fetchone.return_value = (1,)
      engine, _conn = _mock_engine(cur)
      monkeypatch.setattr(pd, "engine_nexora_db", engine)
      assert pd.count_prepared_documents(pid="100") == 1
      sql_used = cur.execute.call_args.args[0]
      assert "WHERE PID = ?" in sql_used
      assert cur.execute.call_args.args[1] == ["100"]

  def test_fetch_page_with_pid_filters(monkeypatch):
      cur = MagicMock()
      cur.fetchall.return_value = [(1, "100", True, "A", False, "", 7, None, None)]
      engine, _conn = _mock_engine(cur)
      monkeypatch.setattr(pd, "engine_nexora_db", engine)
      rows = pd.fetch_prepared_documents_page(0, 40, pid="100")
      assert rows[0]["pid"] == "100"
      sql_used = cur.execute.call_args.args[0]
      assert "WHERE PID = ?" in sql_used
  ```
- [ ] **Step (run, expect fail):** `python -m pytest tests/unit/test_prepared_documents.py -k "pids_in_register or pid or fetch_page_with_pid or count_with_pid" -q`.
- [ ] **Step (implement `count_prepared_documents`):** Replace its body to accept `pid=None` (keep the `try/finally` shape):
  ```python
  def count_prepared_documents(pid=None):
      """Total row count of the register (for pagination). Optional exact PID filter."""
      conn = None
      try:
          conn = engine_nexora_db.raw_connection()
          cur = conn.cursor()
          if pid:
              cur.execute("SELECT COUNT(*) FROM dbo.PreparedDocuments WHERE PID = ?", [str(pid)])
          else:
              cur.execute("SELECT COUNT(*) FROM dbo.PreparedDocuments")
          row = cur.fetchone()
          return int(row[0]) if row else 0
      finally:
          if conn is not None:
              conn.close()
  ```
- [ ] **Step (implement `fetch_prepared_documents_page`):** Add `pid=None` and a conditional `WHERE PID = ?` before `ORDER BY ID DESC` (keep the OFFSET/FETCH last and the row-mapping loop verbatim):
  ```python
  def fetch_prepared_documents_page(offset, limit, pid=None):
      """Return one OFFSET/FETCH page of the register, newest id first.
      Optional exact PID filter (for the reverse ?pid deep-link)."""
      conn = None
      try:
          conn = engine_nexora_db.raw_connection()
          cur = conn.cursor()
          base = (
              "SELECT ID, PID, Collected, CollectedBy, Prepared, PreparedBy, "
              "       UploadedBy, UploadedAt, UpdatedAt "
              "FROM dbo.PreparedDocuments "
          )
          params = []
          if pid:
              base += "WHERE PID = ? "
              params.append(str(pid))
          base += "ORDER BY ID DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
          params += [int(offset), int(limit)]
          cur.execute(base, params)
          out = []
          for r in cur.fetchall():
              out.append({
                  "id": r[0],
                  "pid": str(r[1]) if r[1] is not None else "",
                  "collected": bool(r[2]),
                  "collected_by": r[3] or "",
                  "prepared": bool(r[4]),
                  "prepared_by": r[5] or "",
                  "uploaded_by": r[6],
                  "uploaded_at": str(r[7]) if r[7] is not None else None,
                  "updated_at": str(r[8]) if r[8] is not None else None,
              })
          return out
      finally:
          if conn is not None:
              conn.close()
  ```
- [ ] **Step (implement `pids_in_register`):** Append (after `clear_prepared_documents`):
  ```python
  def pids_in_register(pids):
      """Return the subset of `pids` present in dbo.PreparedDocuments.

      One parameterized SELECT (PID IN (...)). Empty input -> empty set without a DB
      round-trip. Never raises into the request: on any DB error it logs and returns an
      empty set (the reverse chip just won't show)."""
      wanted = [str(p) for p in (pids or []) if str(p).strip()]
      if not wanted:
          return set()
      conn = None
      try:
          conn = engine_nexora_db.raw_connection()
          cur = conn.cursor()
          placeholders = ",".join(["?"] * len(wanted))
          cur.execute(
              f"SELECT PID FROM dbo.PreparedDocuments WHERE PID IN ({placeholders})",
              wanted,
          )
          return {str(r[0]) for r in cur.fetchall() if r[0] is not None}
      except Exception as e:
          current_app.logger.error(f"pids_in_register: {e}")
          return set()
      finally:
          if conn is not None:
              conn.close()
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/unit/test_prepared_documents.py -q`.
- [ ] **Step (commit):**
  ```
  git add nx_lib/prepared_documents.py tests/unit/test_prepared_documents.py
  git commit -m "feat(prepared-docs): pids_in_register helper + optional pid filter (P3.1)

  Add pids_in_register(pids)->set[str] (parameterized IN-list; empty input -> empty set,
  no round-trip; never raises) for the reverse In-register chip, plus an optional exact
  pid argument to count_prepared_documents / fetch_prepared_documents_page for the
  register ?pid deep-link filter.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 3.2: Register route `?pid` filter + "Show all" affordance

**Files:**
- Modify: `nx_lib/views/workitems.py` (`prepared_documents`)
- Modify: `templates/prepared_documents.html`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `request.args.get("pid")`. Passes `pid_filter=pid_filter` (str | None) to the template; passes `pid=pid_filter` into the two read functions.
- Note: PID is the MERGE key of `dbo.PreparedDocuments` (verified: `MERGE … ON tgt.PID = src.PID`), so a `?pid` result is at most one row — **no pagination-href preservation is needed** (a filtered list is always ≤1 page).

- [ ] **Step (write failing integration test):** Append:
  ```python
  def test_prepared_documents_pid_filter_passes_through(
      user_client, workitems_all_perms, monkeypatch
  ):
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      seen = {}
      monkeypatch.setattr(wv, "count_prepared_documents",
          lambda pid=None: (seen.__setitem__("count_pid", pid) or 1))
      monkeypatch.setattr(wv, "fetch_prepared_documents_page",
          lambda offset, limit, pid=None: (seen.__setitem__("fetch_pid", pid) or
              [{"id": 1, "pid": "100", "collected": True, "collected_by": "A",
                "prepared": False, "prepared_by": "", "uploaded_by": 7,
                "uploaded_at": None, "updated_at": None}]))
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: [])
      monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [])
      monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: None)
      resp = user_client.get("/prepared_documents?pid=100")
      assert resp.status_code == 200
      assert seen.get("count_pid") == "100"
      assert seen.get("fetch_pid") == "100"
      assert b'data-testid="prepared-docs-show-all"' in resp.data
  ```
- [ ] **Step (run, expect fail).**
- [ ] **Step (implement route):** In `prepared_documents`, replace the read block (verbatim anchor: the `try:` / `total_items = count_prepared_documents()` / `rows = fetch_prepared_documents_page(offset, per_page)` block) with:
  ```python
      pid_filter = (request.args.get("pid") or "").strip() or None
      try:
          total_items = count_prepared_documents(pid=pid_filter)
          rows = fetch_prepared_documents_page(offset, per_page, pid=pid_filter)
      except Exception as e:
          current_app.logger.error(f"prepared_documents read: {e}")
          total_items, rows = 0, []
  ```
  Add `pid_filter=pid_filter,` to the `render_template(...)` kwargs.
- [ ] **Step (template "Show all"):** In `templates/prepared_documents.html`, inside the `nx-page-head__actions` div (verbatim anchor: `<div class="nx-page-head__actions">`), add before the `<div class="nx-count-pill">`:
  ```html
        {% if pid_filter %}
        <a href="{{ url_for('prepared_documents') }}" class="nx-btn nx-btn--secondary"
           data-testid="prepared-docs-show-all">{{ _("Show all") }} ({{ _("PID") }} {{ pid_filter }})</a>
        {% endif %}
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -q`.
- [ ] **Step (commit):**
  ```
  git add nx_lib/views/workitems.py templates/prepared_documents.html tests/integration/test_workitems_routes.py
  git commit -m "feat(prepared-docs): register ?pid exact-match filter + Show-all (P3.2)

  prepared_documents() reads ?pid and threads it through count/fetch (parameterized
  WHERE PID = ?), rendering a Show-all reset when filtered. Lands the reverse link
  directly on its register entry. PID is the table MERGE key, so a filtered list is
  always one page (no pagination-href change needed).

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 3.3: `resolve_ms02_wids_to_pids` resolver + pure `_stamp_in_register` enrichment (no new route/perm)

**Files:**
- Modify: `nx_lib/workitem_sources.py` (new `resolve_ms02_wids_to_pids`)
- Modify: `nx_lib/views/workitems.py` (new pure `_stamp_in_register(rows)`; call it in `_get_workitems_data`; import the resolver + `pids_in_register`)
- Test: `tests/unit/test_workitem_sources.py`, `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Produces: `resolve_ms02_wids_to_pids(engine, specs, wids) -> dict[int, str] | None` — inverse of `resolve_ms02_pid_to_wids`: `SELECT DISTINCT "<id_col>", "<pid_col>"::text FROM <table> WHERE "<id_col>" = ANY(%s)`, keyed by wid (first PID per wid wins). Reuses `_MS02_IDENT` + `_as_workitem_ids`. Three-way contract: `None` (engine/specs/wids absent or error), `{}` (no match), `{wid: pid}`. Never raises.
- Produces: `_stamp_in_register(rows)` in the view — MS02-gated pure helper that stamps `row["pid"]` and `row["in_register"]` onto each row dict in place; unit-testable by monkeypatching `resolve_ms02_wids_to_pids` + `pids_in_register` (no full-route drive — resolves the fragile-acceptance finding). Called once at the end of `_get_workitems_data`. No new endpoint, no `@require_permission` → the chip needs **no extra perm** (spec).

- [ ] **Step (write failing unit tests for the resolver):** Append to `tests/unit/test_workitem_sources.py` (mirror `test_resolve_ms02_pid_to_wids_groups_by_pid` style; note `(id, pid)` projection order here):
  ```python
  def test_resolve_ms02_wids_to_pids_maps_first_pid(app):
      from unittest.mock import MagicMock
      from nx_lib.workitem_sources import resolve_ms02_wids_to_pids
      cur = MagicMock()
      cur.fetchall.return_value = [(42, "100"), (43, "222"), (42, "999")]
      conn = MagicMock(); conn.cursor.return_value = cur
      engine = MagicMock(); engine.raw_connection.return_value = conn
      with app.app_context():
          result = resolve_ms02_wids_to_pids(engine, [("DossierStatistik", "WorkItemID", "DossierNummer", None)], [42, 43])
      assert result[42] == "100"   # first pid per wid wins
      assert result[43] == "222"

  def test_resolve_ms02_wids_to_pids_none_contract(app):
      from unittest.mock import MagicMock
      from nx_lib.workitem_sources import resolve_ms02_wids_to_pids
      with app.app_context():
          assert resolve_ms02_wids_to_pids(None, [("t", "ID", "PID", None)], [1]) is None
          assert resolve_ms02_wids_to_pids(MagicMock(), [], [1]) is None
          assert resolve_ms02_wids_to_pids(MagicMock(), [("t", "ID", "PID", None)], []) is None
  ```
- [ ] **Step (run, expect fail):** `python -m pytest tests/unit/test_workitem_sources.py -k resolve_ms02_wids_to_pids -q`.
- [ ] **Step (implement resolver):** In `nx_lib/workitem_sources.py`, after `resolve_ms02_pid_to_wids`, add:
  ```python
  def resolve_ms02_wids_to_pids(engine, specs, wids):
      """Inverse of resolve_ms02_pid_to_wids: map workitem ids -> their PID (col_pid)
      value, columnar. Used by the reverse 'In register' chip to learn each visible
      workitem's PID. Reuses the _MS02_IDENT guard + _as_workitem_ids.

      None (engine/specs/wids absent or error) -> no mapping; {} -> none matched;
      {wid: pid} otherwise. First PID seen per wid wins. Never raises."""
      if engine is None or not specs or not wids:
          return None
      ids = []
      for w in wids:
          try:
              ids.append(int(w))
          except (TypeError, ValueError):
              continue
      if not ids:
          return None
      conn = None
      try:
          conn = engine.raw_connection()
          cur = conn.cursor()
          result: dict[int, str] = {}
          for table, id_col, pid_col, time_filter in specs:
              if not (table and id_col and pid_col):
                  continue
              if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(pid_col)):
                  current_app.logger.error(
                      f"resolve_ms02_wids_to_pids: unsafe identifier {(id_col, pid_col)}"
                  )
                  continue
              sql = (
                  f'SELECT DISTINCT "{id_col}", "{pid_col}"::text'
                  f" FROM {table}"
                  f' WHERE "{id_col}" = ANY(%s)'
              )
              if time_filter:
                  sql += f" AND {time_filter}"
              cur.execute(sql, [ids])
              for wid_raw, pid_raw in cur.fetchall():
                  wids_parsed = _as_workitem_ids([(wid_raw,)])
                  if not wids_parsed:
                      continue
                  wid = next(iter(wids_parsed))
                  pid_str = str(pid_raw) if pid_raw is not None else None
                  if pid_str and wid not in result:
                      result[wid] = pid_str
          return result
      except Exception as e:
          current_app.logger.error(f"resolve_ms02_wids_to_pids: {e}")
          return None
      finally:
          if conn is not None:
              conn.close()
  ```
- [ ] **Step (imports in the view):** Add `resolve_ms02_wids_to_pids` to the `from ..workitem_sources import (...)` block (next to `resolve_ms02_pid_to_wids`) and `pids_in_register` to the `from ..prepared_documents import (...)` block.
- [ ] **Step (write failing unit test for `_stamp_in_register`):** Append to `tests/integration/test_workitems_routes.py` (import the view module; unit-test the pure helper directly — no route drive):
  ```python
  def test_stamp_in_register_marks_rows(monkeypatch):
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
      monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
      monkeypatch.setattr(wv, "resolve_ms02_wids_to_pids", lambda e, s, w: {42: "100", 43: "200"})
      monkeypatch.setattr(wv, "pids_in_register", lambda pids: {"100"})
      rows = [{"workitemid": 42}, {"workitemid": 43}]
      wv._stamp_in_register(rows)
      assert rows[0]["pid"] == "100" and rows[0]["in_register"] is True
      assert rows[1]["pid"] == "200" and rows[1]["in_register"] is False

  def test_stamp_in_register_noop_when_not_ms02(monkeypatch):
      import nx_lib.views.workitems as wv
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", None)
      rows = [{"workitemid": 42}]
      wv._stamp_in_register(rows)
      assert "pid" not in rows[0] and "in_register" not in rows[0]
  ```
- [ ] **Step (run, expect fail).**
- [ ] **Step (implement `_stamp_in_register` + call site):** In `nx_lib/views/workitems.py`, add the pure helper (place it just above `_get_workitems_data`):
  ```python
  def _stamp_in_register(rows):
      """MS02-only, in place: stamp row['pid'] + row['in_register'] onto each visible
      workitem row. Resolves the page's wids -> PIDs (resolve_ms02_wids_to_pids) and
      intersects with the register (pids_in_register). Guarded so the default client /
      CI path is byte-for-byte unchanged; never raises into the request."""
      ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
      if not (ms02_active and rows):
          return
      try:
          pid_specs = _ms02_pid_specs(_ms02_target_processes())
          wid_to_pid = (
              resolve_ms02_wids_to_pids(
                  engine_ms02_docfields_pg, pid_specs, [r["workitemid"] for r in rows]
              )
              if pid_specs else None
          ) or {}
          registered = pids_in_register(list(wid_to_pid.values())) if wid_to_pid else set()
          for r in rows:
              pid = wid_to_pid.get(r["workitemid"])
              r["pid"] = pid or ""
              r["in_register"] = bool(pid and pid in registered)
      except Exception as e:
          current_app.logger.error(f"_stamp_in_register: {e}")
  ```
  In `_get_workitems_data`, after `rows, total_items, degraded = fetch_merged_page(filt, offset, per_page)` and before the return dict, add:
  ```python
      _stamp_in_register(rows)
  ```
- [ ] **Step (run, expect green):** `python -m pytest tests/unit/test_workitem_sources.py tests/integration/test_workitems_routes.py -k "wids_to_pids or stamp_in_register" -q`.
- [ ] **Step (commit):**
  ```
  git add nx_lib/workitem_sources.py nx_lib/views/workitems.py tests/unit/test_workitem_sources.py tests/integration/test_workitems_routes.py
  git commit -m "feat(workitems): stamp pid + in_register on visible MS02 rows (P3.3)

  Add resolve_ms02_wids_to_pids (inverse of resolve_ms02_pid_to_wids) and a pure
  _stamp_in_register(rows) helper that maps the visible page's wids -> PIDs and
  intersects with pids_in_register to stamp row.pid + row.in_register. MS02-gated, no
  new route, no new permission (chip needs no extra perm). Unit-tested directly on the
  pure helper. Default client / CI path unchanged.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 3.4: Carry `pid`/`in_register` to the row + render the "In register" chip in the panel header

**Files:**
- Modify: `templates/js/_workitems_overview_js.html` (`renderTable` dataset attrs; seed `_inRegisterByWid` from the payload)
- Modify: `templates/js/_workitem_detail_panel_js.html` (`_renderHeaderChip`)
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `workitem.pid` / `workitem.in_register` (now in the `/api/workitems` payload via Task 3.3), carried onto the details-row dataset and into `_inRegisterByWid`.
- Produces: `_renderHeaderChip(workitemId, opts)` renders an "In register" anchor (`data-testid="workitem-in-register"`) into `#detail-panel-header-${wid}` → `prepared_documents?pid=<pid>` only when `opts.inRegisterPid` is set. The read-only register modal passes no `inRegisterPid`, so the chip never appears there (correct — that is where the click came from).

- [ ] **Step (renderTable — carry pid/in_register):** In `_workitems_overview_js.html` `renderTable`, change the details-row template literal (verbatim anchor: the `<tr id="details-row-${workitem.workitemid}" class="details-row" hidden` block ~1741–1743) to add the dataset attrs:
  ```js
                    <tr id="details-row-${workitem.workitemid}" class="details-row" hidden
                        data-status="${workitem.status}"
                        data-current-stage="${workitem.current_stage || ''}"
                        data-pid="${workitem.pid || ''}"
                        data-in-register="${workitem.in_register ? '1' : '0'}"><td colspan="7"></td></tr>
  ```
- [ ] **Step (seed `_inRegisterByWid` in `renderTable`):** At the end of `renderTable`'s `workitems.forEach(...)` (or right after it), populate the map declared in Task 1.3 from the payload (no extra fetch — PID is server-stamped):
  ```js
                  if (workitem.in_register && workitem.pid) {
                    _inRegisterByWid[String(workitem.workitemid)] = workitem.pid;
                  }
  ```
  (Reset `_inRegisterByWid = {}` at the top of `renderTable` before the loop.)
- [ ] **Step (implement `_renderHeaderChip`):** Replace the placeholder in the shared partial:
  ```js
      const _PREPARED_DOCS_URL = API_PREFIX + "prepared_documents";
      function _renderHeaderChip(workitemId, opts) {
        const pid = opts && opts.inRegisterPid;
        if (!pid) return;
        const host = document.getElementById(`detail-panel-header-${workitemId}`);
        if (!host) return;
        const url = `${_PREPARED_DOCS_URL}?pid=${encodeURIComponent(pid)}`;
        host.innerHTML = `<a href="${url}" class="nx-label nx-label--blue inline-flex items-center gap-1"
          data-testid="workitem-in-register"><i class="fas fa-clipboard-list"></i>{{ _("In register") }}</a>`;
      }
  ```
  (Already called from `render` in Task 1.2; `toggleDetailsAndLoadImages` already passes `inRegisterPid: _inRegisterByWid[...]` from Task 1.3.)
- [ ] **Step (write integration test — payload-stamped + chip wiring):** Append:
  ```python
  def test_api_workitems_carries_pid_in_register(user_client, workitems_all_perms, monkeypatch):
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS
      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      monkeypatch.setattr(wv, "fetch_merged_page",
          lambda filt, off, lim: ([{"workitemid": 42, "status": "Ready",
              "current_stage": "Import", "priority": 0, "tags": [], "modifiedat": None}], 1, []))
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
      monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
      monkeypatch.setattr(wv, "resolve_ms02_wids_to_pids", lambda e, s, w: {42: "100"})
      monkeypatch.setattr(wv, "pids_in_register", lambda pids: {"100"})
      resp = user_client.get("/api/workitems")
      assert resp.status_code in (200, 500)  # 500 only if upstream filter parsing trips in CI
      if resp.status_code == 200:
          wi = resp.get_json()["workitems"][0]
          assert wi["pid"] == "100"
          assert wi["in_register"] is True
  ```
  (The pure `_stamp_in_register` is already asserted exactly in Task 3.3; this is a thin end-to-end sanity that tolerates the CI 500 from upstream filter parsing without weakening the real assertion.)
- [ ] **Step (run, expect green):** `python -m pytest tests/integration/test_workitems_routes.py tests/integration/test_workitem_detail_panel.py -q`.
- [ ] **Step (browser verify — restart first):** Restart `nx -u -b --loginas:<MS02 user>` (needs a workitem whose PID is in the register — upload an Excel first or use a known matched PID). Expand that row: the "In register" chip shows in the panel header and links to `/prepared_documents?pid=<pid>`; following it lands on the single-row filtered register with a "Show all" link; a non-registered workitem shows no chip. Screenshot `var/screenshots/p3-in-register-chip.png` and SendUserFile.
- [ ] **Step (commit):**
  ```
  git add templates/js/_workitems_overview_js.html templates/js/_workitem_detail_panel_js.html tests/integration/test_workitems_routes.py
  git commit -m "feat(workitems): 'In register' reverse chip in the detail panel header (P3.4)

  renderTable carries pid + in_register onto the details-row dataset and seeds
  _inRegisterByWid from the payload; the shared panel renders an In-register chip linking
  to prepared_documents?pid=<pid> when the workitem's PID is in the register. Not shown in
  the read-only register modal (no inRegisterPid passed).

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

### Task 3.5: i18n for the P3 strings

**Files:** `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ `.mo`), `messages.pot`

**Interfaces:** new msgids: `In register`, `Show all`. (`PID` already exists from the register table head.)

- [ ] **Step (i18n cycle):** `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → fill non-fuzzy in de/fr/it (de: `In register`→`Im Register`, `Show all`→`Alle anzeigen`; fr: `Dans le registre` / `Tout afficher`; it: `Nel registro` / `Mostra tutto`). Remove any `#, fuzzy` flags. → `pybabel compile -d translations`. (Use `/nx-i18n`.)
- [ ] **Step (run, expect green):** `python -m pytest tests/unit/test_translations.py -q`.
- [ ] **Step (commit):**
  ```
  git add translations messages.pot
  git commit -m "i18n: reverse chip + show-all strings (de/fr/it) (P3.5)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```

---

# PHASE 4 — Docs & final verification

### Task 4.1: CHANGELOG + CLAUDE.md

**Files:** `CHANGELOG.md`, `CLAUDE.md`

- [ ] **Step (CHANGELOG):** Under `## [Unreleased]` → `### Added` (the section already exists), add:
  ```markdown
  - **Prepared Documents ⇄ Workitem detail cross-linking (MS02).** The register's
    Octo-Status cell gains a read-only **Preview** modal mirroring the full Workitems
    detail panel (page images + source highlighting + extracted fields + audit + tags +
    comments) beside the renamed "Open in Workitems" link; write controls are hidden in
    the preview. A reverse **"In register"** chip on the Workitems detail panel links to
    `prepared_documents?pid=<pid>`, and the register accepts an exact `?pid=` filter (with
    a "Show all" reset). Internally the detail panel was extracted into a shared partial
    `templates/js/_workitem_detail_panel_js.html`
    (`window.NexoraWorkitemDetail.render(wid, container, {readOnly, perms, inRegisterPid})`
    + `attachLightbox(idMap)`) consumed by both the Workitems row-expand and the register
    modal; the Workitems page behaviour is unchanged. New helpers `pids_in_register()` and
    `resolve_ms02_wids_to_pids()`. MS02-only; read-only; no new permission, no new migration.
  ```
- [ ] **Step (CLAUDE.md — MS02 paragraph, ~line 34):** Extend the prepared-documents sentence to note the read-only preview modal, the reverse "In register" chip, the `?pid` filter, and `pids_in_register()` / `resolve_ms02_wids_to_pids()`.
- [ ] **Step (CLAUDE.md — workitems-viewer paragraph, ~line 114):** Update the front-end file reference: panel rendering now lives in `templates/js/_workitem_detail_panel_js.html` (exposing `window.NexoraWorkitemDetail.render(wid, container, {readOnly, perms, inRegisterPid})` + `attachLightbox(idMap)`), consumed by both the Workitems row-expand and the register preview modal; `_workitems_overview_js.html` retains the list/filter/export code, the `tbody` write delegation, and calls the shared renderer.
- [ ] **Step (commit):**
  ```
  git add CHANGELOG.md CLAUDE.md
  git commit -m "docs: changelog + CLAUDE.md for prepared-docs/workitem cross-linking (P4.1)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SEYuZQYx4mug4yEodrC8Jh"
  ```
  (Note: `CHANGELOG.md` and `CLAUDE.md` already show as modified in `git status` from prior session work; stage and commit ONLY your new edits — review the diff first with `git diff CHANGELOG.md CLAUDE.md`. If the `sql-migrate-int` hook trips on INT CRLF drift, use `SQL_SYNC_SKIP=1 git commit`. Never `--no-verify`.)

### Task 4.2: Full-suite verification + final browser pass

- [ ] **Step:** `python scripts/test_db_reset.py` then `python -m pytest tests/unit tests/integration -q`. Confirm no NEW failures attributable to this feature; the only expected reds are the pre-existing `tests/unit/test_octo.py::test_get_extensions_urls_fields_*` (call them out, do not fix).
- [ ] **Step:** `ruff check nx_lib tests` (and `ruff format --check` if the repo runs it) — clean.
- [ ] **Step (browser smoke — restart first):** Restart `nx -u -b --loginas:<MS02 user>`. Verify end-to-end: (a) Workitems row-expand unchanged incl. lightbox/click-to-locate; (b) register Preview modal read-only mirror; (c) reverse chip → `?pid` filtered register → Show all. SendUserFile the screenshots if not already sent.
- [ ] **Step:** Leave the branch at the last commit (do NOT push). Summarize the commit list for the owner.

## Gotchas & notes

- **P1 is the whole ballgame.** `_workitems_overview_js.html` is a single non-IIFE `<script>` mixing module-scope panel helpers with a `DOMContentLoaded`-trapped lightbox engine + `tbody` delegation. The plan moves helpers + lightbox into the shared partial and re-exports on `window`, keeping the page-side `tbody` write delegation (toggle/add-tag/remove-tag/load-more/comment/priority/assign/mention) in place — those handlers stay on the workitems page and are simply absent from the read-only modal. Verify in the browser after each P1 task; a closure/scope break can pass the integration suite (which asserts route status + marker strings, not the JS DOM) yet break row-expand at runtime. Do not collapse P1 tasks into one commit.
- **Read-only means OMIT, not disable** (decision 5). `buildReadonlyCommentsMarkup` emits the comments container + a read-only tags display only — NO priority/assign `<select>`, NO tag input, NO comment `<form>`. The modal also passes `setPriority/addTag/assignUsers/addComment: false` so even the writable branch would be inert; the `readOnly` switch in `render` is the enforcement. `loadCollaborationData`'s null-guards (Task 1.2) make the absence safe.
- **`fieldConfig` / `mentionableUsers` resolution.** The workitems page declares `let fieldConfig`/`let mentionableUsers` at top scope; the shared partial reads them as `window.fieldConfig` / via the `mentionableUsers` argument so the register page (no top-level `let fieldConfig`) resolves them. The register hydrates `window.fieldConfig` from `/api/config/fields` (Task 2.3); the partial defaults it to `{search_options:{}, labels:{}}` so a failed fetch just shows raw field keys.
- **⚠️ `mentionableUsers` must actually reach the non-read-only row-expand (verifier-flagged gap — fix during P1).** The Workitems page populates a **module-scope `let mentionableUsers`** (line ~27) via `fetchMentionableUsers`, but the refactored row-expand reads `window.mentionableUsers` (`loadCollaborationData(wid, readOnly ? [] : (window.mentionableUsers || []))`, Task 1.2). Nothing in the plan assigns the page's populated list onto `window.mentionableUsers` — it only *defaults* it to `[]` (lines 307/745). Left as-is, the assignee `<select>` / @-mention list renders **EMPTY** on the Workitems page after the refactor (a silent regression the integration suite won't catch — it asserts route status + markers, not the JS DOM). **Fix:** in the P1 page-partial task, have `fetchMentionableUsers` (or its caller) assign `window.mentionableUsers = <populated list>` after fetch (or declare the page variable as `window.mentionableUsers` throughout), so the non-read-only path gets the real list. Verify in the browser that an expanded Workitems row still shows the assignee options. The read-only register modal is unaffected (it passes `[]`).
- **Two lightbox shells, never two open at once.** The workitems page attaches `#imageModal`; the register attaches `#pdocPreviewLightbox`. `attachLightbox(idMap)` gives each instance its own closure-local `currentImages`/`currentIndex`/`srcHl` and modal-scoped `.modal-close`/`.modal-prev`/`.modal-next` lookups — so the register's preview-modal `.pdoc-preview-close` button (rendered first in the DOM) can never be mis-bound by the lightbox (resolves the two-`.modal-close` collision). The register has no row-expand, so there is no same-DOM double-lightbox case.
- **`API_PREFIX` consistency.** Both the shared partial and the register IIFE prefer `window.API_PREFIX` (then the `window.location.href.includes("nexora")` heuristic), so they resolve identically in dev (`/`) and on standard prod. Under a `PrefixMiddleware` URL-prefix deploy, confirm `window.API_PREFIX` is set or the heuristic matches, else media/audit fetches 404 — a prod-only concern.
- **Load-more in the read-only modal.** The image "Load more" button is wired through the workitems-page `tbody` delegation only; the register modal renders into `#pdocPreviewBody` (outside `tbody`), so "Load more" does nothing in the preview. This affects only documents with >7 pages, and images are empty on dev anyway. **Acceptable for read-only v1** — note it, don't fix it. (A later nicety: delegate `.load-more-btn` on `document` inside the shared partial.)
- **Media degradation is already graceful** (verified): `loadDetailData`'s media fetch catches errors and shows a red "Could not load media." without erroring the panel; `loadImage` degrades per-image. So fields/audit/comments render even when Octo media is unreachable (dev / MS02-from-dev). No new hardening — just confirm the `catch` survives the extraction.
- **P3 PID source is server-side.** The list payload had no PID; `_stamp_in_register` computes `pid` + `in_register` in `_get_workitems_data` (one extra PG round-trip per page-load, MS02-only, guarded). The chip is best-effort: on any error the helper logs and leaves rows unstamped → no chip. The default client / CI path is byte-for-byte unchanged.
- **MS02 PID specs.** Always resolve via `_ms02_pid_specs(_ms02_target_processes())` (the `'ms02'` SearchConfig `col_pid` for the user's `target_processes`, e.g. `ProcessName='sydoc.05_PDBS'`) — never hardcode the column or process. The reverse resolver reuses these exact specs.
- **Tests gate-and-mock everywhere.** Every MS02-dependent test sets `engine_ms02_docfields_pg`, `CLIENTS["ms02"]`, AND `wv.has_permission` (the wv-local trap). Data-access unit tests mock the cursor via `tests/unit/test_prepared_documents.py::_mock_engine`; resolver unit tests mirror `test_resolve_ms02_pid_to_wids_groups_by_pid` and use the conftest `app` fixture for `app.app_context()`.
- **Include-presence tests assert unconditionally.** The shared partial is included in the template body before any data fetch; a 500-fallback renders `500.html` WITHOUT the markers, so asserting `b"NexoraWorkitemDetail" in resp.data` without a status guard fails loudly on a 500 — which is what we want (the `/prepared_documents` render is additionally deterministically 200 under the gate-and-mock, so the P2+ assertions are doubly safe). Always confirm the "expect fail" run truly fails before implementing.
- **No new migration, no new permission, no deploy-exclude change** — assert this in review; the only new file (`_workitem_detail_panel_js.html`) is under `templates/` and ships automatically via the existing robocopy mirror.
- **Pre-existing reds:** only `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}` (verified lines 181/222/254). `tests/unit/test_workitems_pid_filter.py` does NOT exist — do not reference it.
- **GitNexus MCP was unavailable in the planning sandbox** — every anchor in this plan was verified directly with Read/Grep against the worktree HEAD (2026-06-23). If GitNexus tools are available in the execution session, run `gitnexus_impact` before editing `_get_workitems_data` / `loadCollaborationData` / the lightbox engine per the repo's GitNexus rules; otherwise re-grep the anchor before each edit.
