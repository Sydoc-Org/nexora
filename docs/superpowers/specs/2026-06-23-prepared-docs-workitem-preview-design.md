# Prepared Documents ⇄ Workitem Detail Cross-Linking — Design

**Date:** 2026-06-23 · **Branch:** `feature/2.5.63` (commit-only / remote) · **Status:** approved design, pre-plan
**Builds on:** the MS02 Prepared Documents register (`docs/superpowers/specs/2026-06-23-prepared-documents-register-design.md`, shipped — see `docs/superpowers/handoffs/2026-06-23-prepared-documents-register-execution-complete.md`).

## Goal

Cross-link the prepared-documents register and the Workitems detail view, in both directions:

1. **Register → workitem preview.** In the register's `Octo-Status` column, when a personal number (PID) resolves to an Octo workitem, the user can open a **read-only modal** that mirrors the full Workitems "details" panel for that workitem (document page images + source highlighting + extracted fields + audit history + tags + comments), without leaving the register.
2. **Workitem → register reverse.** On the Workitems page, a workitem whose PID is present in the register shows an **"In register" chip/link** that opens the register filtered to that PID.

Both are MS02-only and reuse existing permissions; no new permission and no new migration.

## Why this is needed

Today the register's `Octo-Status` cell (`templates/prepared_documents.html`, the `octo_status.get(r.pid)` block) renders, for a matched PID, a single soft link: `workitems_overview?search=<wid>` — a fuzzy `LIKE`-substring jump to the filtered Workitems list. It does not let the user *see* the matched workitem in place, and there is no link back from a workitem to its register entry. The register and the workitems list are the two halves of the MS02 intake workflow; an operator preparing documents wants to glance at the matched workitem (its scanned pages, extracted fields, status) and jump between the two views.

## Current state (verified against HEAD)

- **Register:** route `prepared_documents` + `clear_prepared_documents_route` in `nx_lib/views/workitems.py`; data access `nx_lib/prepared_documents.py`; templates `templates/prepared_documents.html` + `templates/js/_prepared_documents_js.html`. The route already resolves live Octo status via `resolve_ms02_pid_to_wids(...)` into `octo_status[pid] = {"in_octo": bool, "wid": int}`.
- **Workitems detail panel:** built entirely **client-side** in `templates/js/_workitems_overview_js.html` — the per-row `details-row-<wid>` markup (a template literal with Jinja perm gates: `details_images_perm`, `details_audit_perm`, `details_fields_perm`, `details_set_priority_perm`, `details_assign_users_perm`, `details_add_tag_perm`, `details_add_comment_perm`), expanded by `toggleDetailsAndLoadImages(...)`, which lazy-loads via the existing single-workitem endpoints (`api/workitem/<wid>`, `api/get_audithistory/<wid>`, `api/workitem/<wid>/interactions`) and the fields/images path (`get_extensions_urls_fields`, `nx_lib/field_locations.py`, `nx_lib/table_locations.py`), with source-highlighting from `static/css/source-highlight.css`.
- **`ms02_active`** = `"ms02" in CLIENTS and engine_ms02_docfields_pg is not None`. The MS02 PID is the `col_pid` doc-field (`SearchConfig`, migration `0030`, `ProcessName='sydoc.05_PDBS'`), already surfaced as a workitem field on the Workitems page.

## Decisions locked in (from brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | Register click action | **Preview popup** (read-only modal) on the register page, plus an "Open in Workitems" link. |
| 2 | Preview scope | **Full details mirror** — images, source highlighting, fields, audit, tags, comments. |
| 3 | Reverse direction | **Included** — an "In register" chip/link on the Workitems page → register filtered to that PID. |
| 4 | Reuse architecture | **Shared panel** — one component renders the detail panel for the Workitems row-expand AND the register modal (single source of truth). |
| 5 | Interactivity | **Read-only** preview (write controls hidden; "Open full workitem" for edits). |
| 6 | Permissions / schema | **No new permission, no new migration.** MS02-only + existing `workitems.import.preparedaudit` and `workitems.details.view.*` gates. |

## Architecture

### Component 1 — Shared workitem detail panel (the core refactor)

Extract the detail-panel rendering out of `_workitems_overview_js.html` into a new shared partial **`templates/js/_workitem_detail_panel_js.html`** that exposes a single entry point:

```js
window.NexoraWorkitemDetail = {
  render(workitemId, containerEl, { readOnly = false, perms } = {}) { ... }
}
```

It owns: (a) building the panel DOM (the markup currently inline in `renderTable`'s `details-row`); (b) the lazy loaders against the existing endpoints (`api/workitem/<wid>`, `api/get_audithistory/<wid>`, `api/workitem/<wid>/interactions`, fields/images); (c) source-highlight wiring + the page-image lightbox. The `perms` object carries the same `details_*` flags the Workitems route already computes; `readOnly:true` hides/omits the write controls (add tag, set priority, assign user, add comment) for the preview.

- `_workitems_overview_js.html` is refactored so its row-expand calls `NexoraWorkitemDetail.render(wid, detailsTd, { readOnly:false, perms })`. **Behaviour and perms on the Workitems page are unchanged** — this is a lift-and-shift guarded by the existing workitems integration/e2e tests plus new targeted tests.
- Both host pages load `static/css/source-highlight.css`.
- **Interface clarity:** a consumer needs only `render(wid, container, opts)`; it does not need to know the panel's internals. The Workitems page and the register modal are the two consumers; the reverse chip is a link, not a consumer.

### Component 2 — Register preview modal (read-only)

- **Octo-Status cell** (`templates/prepared_documents.html`): for a matched PID, render a **"Preview" button** (`data-testid="prepared-docs-preview"`, carrying `data-wid`) and keep an **"Open in Workitems"** link (the existing `workitems_overview?search=<wid>`). Unmatched stays "—".
- **Modal shell** in the register template (hidden by default); `templates/js/_prepared_documents_js.html` wires the Preview button to open the modal and call `NexoraWorkitemDetail.render(wid, modalBody, { readOnly:true, perms })`. Closes on overlay/Escape.
- **Route:** `prepared_documents` computes the same `details_*` perm flags as `workitems_overview` (gathered identically) and passes them to the template; the partial reads them. The Preview button renders only when the user holds the base `workitems.details.view` perm; per-section content follows the same per-section perms as the Workitems page.
- **Media degradation:** where the Octo media host is unreachable (dev, MS02-from-dev), the image section degrades to empty/placeholder while fields/audit/etc. still render — the loaders must not error the whole panel. (Confirm the existing loader already degrades; harden if not.)

### Component 3 — Workitem → register reverse

- **Data access:** new helper in `nx_lib/prepared_documents.py` — `pids_in_register(pids: list[str]) -> set[str]` (one parameterized `SELECT PID FROM dbo.PreparedDocuments WHERE PID IN (...)`; empty input → empty set; never raises into the request).
- **Workitems page (MS02 only):** for the visible workitems, intersect their PIDs (the `col_pid` doc-field already surfaced per row) with `pids_in_register(...)`. A workitem whose PID is in the register shows a small **"In register" chip/link** in its detail panel header (`data-testid="workitem-in-register"`) → `prepared_documents?pid=<pid>`.
- **Register `?pid` filter:** the `prepared_documents` route accepts an optional exact `?pid=<pid>` query param; when present it **filters the list to that single PID** so the reverse link lands directly on that entry (a "show all" link clears the filter). Implemented as a parameterized exact-match filter in the existing read path (`fetch_prepared_documents_page` + `count_prepared_documents` gain an optional `pid` argument).

## Permissions & scope

- Register page + preview button: `workitems.import.preparedaudit` + `ms02_active` (unchanged for the page; preview button additionally needs `workitems.details.view`).
- Preview content sections: the existing `workitems.details.view.*` family (same per-section gating as the Workitems page).
- Reverse chip: MS02-only; visible only for workitems whose PID is in the register; no extra perm.
- **No new permission, no new migration.** New i18n strings for the modal title, the "Preview" / "Open in Workitems" / "In register" labels, and any modal chrome.

## Phasing (for the implementation plan)

- **P1 — Shared panel extraction.** Move the detail panel + loaders into `_workitem_detail_panel_js.html`; refactor the Workitems page to consume it; add `readOnly` support; regression-test the Workitems detail expansion. *(Riskiest — do first, in isolation.)*
- **P2 — Register preview modal.** Octo-Status "Preview" button + modal shell + wire to the shared panel (read-only); register route passes `details_*` perms; image degradation hardened.
- **P3 — Reverse.** `pids_in_register` helper; Workitems "In register" chip; register `?pid` filter; intersect on the visible page.

## Dependencies to confirm during planning

1. The single-workitem endpoints (`api/workitem/<wid>`, `api/get_audithistory/<wid>`, `api/workitem/<wid>/interactions`) and `get_extensions_urls_fields` work for **MS02-sourced** workitems (the multi-source routing should already cover this).
2. Each visible workitem's **PID is available client-side** for the reverse intersect (the `col_pid` doc-field surfaced per row). If it is not in the list payload, P3 needs a small resolve step.
3. The detail-panel image loader **degrades gracefully** on unreachable Octo media rather than erroring the panel.

## Risks & trade-offs

- **P1 refactors the large, just-shipped `_workitems_overview_js.html`** — the principal risk. Mitigated by doing it isolated first and leaning on the existing workitems integration + e2e coverage plus new targeted tests; behaviour on the Workitems page must be byte-for-byte unchanged.
- **Full *image* preview only renders where Octo media is reachable (PROD).** On dev / MS02-from-dev the modal shows fields/audit/etc. with empty image slots. Acceptable and documented.
- **"Open in Workitems" stays the soft `?search=<wid>` `LIKE` match** (no exact single-workitem page exists). Optional later nicety: a deep-link `&expand=<wid>` that auto-expands the row.

## Out of scope (v1)

- Editing a workitem from the preview (read-only by decision).
- An exact single-workitem deep-link / auto-expand (optional follow-up).
- Persisting any Octo cross-reference (the register stays the source of truth; Octo status remains live/non-stored).
- Storing the reverse mapping (computed live per page).

## Testing approach

- **P1:** unit/DOM-level coverage that `NexoraWorkitemDetail.render` builds the panel and honours `readOnly`; the existing Workitems integration + e2e suites must stay green (no behavioural change on the Workitems page).
- **P2:** integration test that the register route exposes the `details_*` perms and the Preview button renders only with `workitems.details.view`; the modal opens and calls the shared renderer (DOM/e2e). Image-unreachable degradation asserted.
- **P3:** unit test for `pids_in_register` (mocked cursor, parameterized, empty-input, no-raise); integration test that an in-register PID shows the chip and the register `?pid` filter returns the single entry.
- CI/TEST has no MS02 engine; gate-and-mock as the register tests already do.
