# Prepared Documents register (MS02) — design

**Date:** 2026-06-23
**Status:** Approved, ready for plan
**Scope:** MS02 client only

## Problem

The MS02 "prepared documents" Excel import (`import_prepared_audit`) currently
treats the upload as a *transient filter* over the workitems list: it resolves
each personal-number PID to its Octo workitem id(s), stashes the result in the
**Flask session** under a token, and the workitems list re-queries with
`?pidImport=<token>`. Matched PIDs merge their imported values onto real rows;
unmatched PIDs show as **synthetic rows** (page 1 only). Clicking **Clear** — or
logging out, or session expiry — discards it.

That model is wrong for what the data actually is. The prepared-documents Excel
is **not** a check of "is this PID already in Octo." It is its **own intake
register** — a preprocess list of documents that have been collected/prepared,
which may or may not have reached Octo yet. "No match" is the normal case, not a
miss. The register should **persist** and live on its **own page**, independent
of the workitems list.

## Decisions (from brainstorming)

- **List model:** accumulating, **upsert by PID** — one ongoing list, one row
  per PID; re-uploading a PID updates its row.
- **Octo cross-reference:** keep as a **soft status column** (computed live), not
  the purpose. List stands on its own.
- **Visibility:** **shared across MS02 users** — one global register; any MS02
  user with the permission sees all rows.
- **Behavior:** **read-only + clear-whole-list** for the first version. No
  per-row edit / done-tracking yet.

## Architecture

### 1. Data model — migration `0031`, NexoraDB, table `dbo.PreparedDocuments`

| Column | Type | Notes |
|---|---|---|
| `ID` | INT IDENTITY PK | |
| `PID` | NVARCHAR(100) NOT NULL, **UNIQUE** | upsert key |
| `Collected` | BIT NOT NULL DEFAULT 0 | the ✓ flag |
| `CollectedBy` | NVARCHAR(255) NULL | name |
| `Prepared` | BIT NOT NULL DEFAULT 0 | the ✓ flag |
| `PreparedBy` | NVARCHAR(255) NULL | name |
| `UploadedBy` | INT NULL | userid — audit stamp |
| `UploadedAt` | DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME() | first insert |
| `UpdatedAt` | DATETIME2 NULL | set on each upsert |

`ponytail:` no `ClientCode` column — the feature is MS02-only and gated by
`ms02_active`; add the column (mirroring `Statconfig.ClientCode` /
`SearchConfig.ClientCode`) only when a second client needs prepared-docs. The
shared register is one global table; `UploadedBy` is an audit stamp, not a
visibility scope.

Field types match `parse_prepared_xlsx`: `collected`/`prepared` are booleans,
`collected_by`/`prepared_by` are strings, `pid` is a normalized string.

### 2. New page

- **Route:** `GET /prepared_documents` → `prepared_documents.html` +
  paired `templates/js/_prepared_documents_js.html`.
- **Pagination:** real DB pagination (`OFFSET/FETCH`). This removes the
  page-1-only synthetic-row limitation entirely.
- **Columns:** PID · Collected ✓ · Collected By · Prepared ✓ · Prepared By ·
  **Octo status**.
- **Controls:** the Excel upload control and a **Clear list** button (with a
  confirm dialog) live on this page.
- **Gating:** existing `workitems.import.preparedaudit` permission **AND**
  `ms02_active`. **No new permission / no perm migration.** Registered in
  `page_visibility()` under that permission and linked from the workitems page
  (where the import button is today).

### 3. Octo soft-status column — live, not stored

For the PIDs on the currently visible page, call the existing
`resolve_ms02_pid_to_wids(engine_ms02_docfields_pg, pid_specs, pids)` to get a
`PID -> [workitem ids]` map. Render **"In Octo"** + an open-workitem link when
matched, **"—"** when not. Computed each load so it is always current; nothing
about Octo state is persisted.

### 4. Upload flow change — `import_prepared_audit`

- Parsing is unchanged (`parse_prepared_xlsx`).
- Instead of resolving to ids and stashing in the session, **upsert each parsed
  row by PID** into `dbo.PreparedDocuments` (`MERGE` on `PID`, or `UPDATE … IF
  @@ROWCOUNT = 0 INSERT`), stamping `UploadedBy`/`UpdatedAt`.
- Return `{inserted, updated, total}` for a summary flash.

### 5. Deletion of the old overlay model

Remove, in `nx_lib/views/workitems.py` and friends:
- the `pid_import:<token>` session stash,
- the `?pidImport=` read-back block (the `pid_import_active` / `_pid_import_meta`
  path),
- the row-merge onto real rows and the synthetic-row append block,
- the `pid_import_active` plumbing in `WorkitemFilter` / `fetch_merged_page`
  **if** it exists solely for this feature (verify during planning before
  removing).

The prepared-import button on the workitems page becomes a **link to the new
page** (or is removed in favor of the page's own upload control).

## Data flow

1. MS02 user (with `workitems.import.preparedaudit`) opens `/prepared_documents`.
2. Page reads a paginated slice of `dbo.PreparedDocuments`.
3. For that slice's PIDs, the route resolves live Octo status and renders it.
4. Upload xlsx → parse → upsert by PID → summary → refresh.
5. Clear list → delete all rows (confirm) → empty register.

## Error handling

- Upload reuses the existing parse/validation errors (`is_file_allowed`, parse
  error messages) and the MS02-only gate (`engine_ms02_docfields_pg is None` /
  `"ms02" not in CLIENTS`).
- Octo status resolution failures degrade to "—" (the resolver already returns
  `None` on error and never raises); the register still renders.
- DB upsert wrapped so a failed import returns a clear error and does not
  partially corrupt the register.

## Testing

- **Unit:** upsert helper — insert path then update path (same PID re-uploaded
  changes the row, does not duplicate). Parser is already covered.
- **Integration:** route test — upload persists rows; second upload upserts;
  `Clear` empties; page is gated by perm + `ms02_active`.

## Cross-cutting (per CLAUDE.md "Keeping docs in sync")

- i18n: new strings extracted + translated for de/fr/it.
- CHANGELOG `[Unreleased]` entry.
- Update the MS02 paragraph in `CLAUDE.md` (the prepared-audit description now
  points at the standalone register, not the session overlay).
- No `deploy.yml` change — the new template + route are runtime artifacts that
  ship normally; no new top-level dev-only file.

## Out of scope (YAGNI — add when needed)

- Per-row editing / "processed" tracking (read-only for now).
- History of distinct import batches (upsert keeps one row per PID).
- A second client (`ClientCode` column).
- A separate view-only permission distinct from the import permission.
