# Handoff — `include=tables` on `/api/v1/workitems` shipped (#398)

**Date:** 2026-09-29 · **Branch:** `feat/admin-tenants-redesign` (this file only — the
feature itself is on `main` via PR #401, merged 06:28 UTC) · 0 ahead of origin ·
commit-only (remote) · #398 **closed by the merge** · worktree
`.claude/worktrees/feat-398-api-include-tables` and local branch
`feat/398-api-include-tables` **removed** (the remote branch still exists on GitHub).

**Prior handoff:** [`2026-09-14-dev-staging-envs-shipped.md`](2026-09-14-dev-staging-envs-shipped.md)
(the admin tenancy redesign in flight on this branch has its own bundle under
`docs/design/`, commit `59b7dce1`; nothing here touches it).

## This session's commits (all on `main` now)

- `f626abac` feat(api): add include=tables to /api/v1/workitems (#398)
- `218431d6` docs(api): document include=tables on the in-app API docs page (#398)
- `2ffeaf1f` Merge pull request #401 — deployed **staging** (green), Confluence synced.

## TL;DR

- `GET /api/v1/workitems?include=tables` (and `fields,tables`) returns each row's extracted
  table values in the detail endpoint's `tables` shape, resolved **once per page** — no per-row
  Octo call, no page-size cap, whole page 500s on any failure, sensitive columns stripped.
- The trick: Octo keeps each client's documents in a **separate database named after its
  `t_DocumentStorages` row on the runtime server** (`EM_Storage`, `Compass_Storage`, …;
  `<Default>` = the runtime DB), and the table values sit there as one plain-XML
  `SystemTableList` media item per document. The app's runtime login already reads them all on
  INT and PROD. Convention, no config, nothing renamed (owner decision this session).
- Verified equal to the document service on 12/12 INT workitems; PROD worst case (EM, 1000 rows,
  ~115 MB XML) is 10–25 s and accepted as a heavy opt-in call.
- Live on **dev** and **staging**. PROD moves with the next `v*` tag.

## What shipped

| area | files | commit |
|---|---|---|
| Pure parser + per-page fetch | `nx_lib/workitems/tables.py` | `f626abac` |
| Storage-name → engine resolver (cached, `<Default>` → runtime engine, unsafe names refused) | `nx_lib/document_storage.py` | `f626abac` |
| Include token, projection, shared `_strip_sensitive_table_columns`, sandbox twin | `nx_lib/views/api_external.py` | `f626abac` |
| `nx --doctor` "Document storages" section (gated on the OctoDB ping) | `nx_lib/cli_doctor.py` | `f626abac` |
| Tests | `tests/unit/test_workitem_tables.py`, `tests/unit/test_document_storage.py`, `tests/unit/test_cli_doctor.py`, `tests/integration/test_api_external_routes.py` | `f626abac` |
| Docs | `docs/howto/external-api.md`, `docs/howto/nx.md`, `CLAUDE.md` (Databases), `CHANGELOG.md` | `f626abac` |
| In-app `/api-docs` page + de/fr/it catalogs | `templates/api_docs.html`, `messages.pot`, `translations/*` | `218431d6` |

## Next steps

1. **Release when convenient** — `CONTRIBUTING.md` → Releases (bump `nx_lib/version.py` +
   `pyproject.toml`, `uv lock`, fold `[Unreleased]`, merge, tag). Merge = staging, tag = PROD.
2. **After the PROD deploy, once:** run `nx --doctor` against PROD or hit
   `include=tables` once per client, to confirm every storage the PROD runtime lists opens under
   the app pool's identity. Today's read-only checks used the INT/PROD `NXR_SERVICE` login from a
   dev box and saw all of them (`Compass_Storage`, `Default_Storage`, `EM_Storage`,
   `Geberit_Storage`, `Privera_Invoice_Storage`, `Privera_Neuzugaenge_Storage`,
   `Privera_Posteingang_Storage`, `Privera_Zeus_Storage`, `<Default>`).
3. Optional: delete the remote branch `origin/feat/398-api-include-tables` (merged).
4. Optional: `tests/unit/test_coverage_thresholds.py` has no entries for the two new modules;
   `/nx-cover` can ratchet them (unit coverage of `workitems/tables.py` is ~93%).

## Gotchas & notes

- **Local integration tests cannot run on this box**: `env/TEST.env` is the placeholder template
  (`DB_SERVER_PRD=replace-me…`), so every DB-backed test fails with ODBC 08001. CI (`pytest tests
  --ignore=tests/e2e` on the runner with the real TEST.env) is the verification path; both runs
  were green (2819 passed).
- **Pre-commit in a fresh worktree**: hooks shell out to `python`, `sqlcmd`, `mssql-scripter`,
  none on this shell's PATH → prefix `PATH="$PWD/.venv/Scripts:$PATH" SQL_SYNC_SKIP=1` (no SQL
  changes here).
- Container documents: the runtime's `RootDocumentID` is the batch; its own table stream must be
  **ignored** and the leaf documents' read instead (`leaf_documents`), or two INT workitems
  disagree with the document service. Same rule as `field_locations.items_of`.
- Server-side XML shredding (`.nodes()`) on SQL Server was tried and is **slower** than raw fetch +
  `ElementTree` (parse of 115 MB is ~3.4 s).
- `t_DocumentStorages.Connection` is Octo's **encrypted** connection string — irrelevant to nexora,
  which opens the storage by name with its own login.
- MS02 (Postgres): same schema in `Documentstorage` on the same server; only 38 table streams
  exist there, so MS02 rows practically always get `[]`.
- The VPN flapped repeatedly during the session; INT/PROD probes that fail with 08001 and
  "SQL Server existiert nicht" are the link, not the code.

## Untracked / left for owner

- Nothing uncommitted. The remote topic branch is the only leftover (see Next steps 3).

## How to verify

```powershell
# dev/staging already run the merged code
curl -H "Authorization: Bearer <key>" "https://staging-nexora.sydoc.ch/nexora/api/v1/workitems?include=tables&per_page=40"
curl -H "Authorization: Bearer <key>" "https://staging-nexora.sydoc.ch/nexora/api/test/v1/workitems?include=fields,tables"
# locally (unit only — integration needs a real env/TEST.env)
.venv\Scripts\python.exe -m pytest tests/unit/test_workitem_tables.py tests/unit/test_document_storage.py tests/unit/test_cli_doctor.py tests/unit/test_translations.py -q --no-cov
nx --doctor --fast      # new "Document storages" section, one line per storage
```

## Resuming in a fresh session

Nothing is in flight for #398. `/reset-session docs/superpowers/handoffs/2026-09-29-api-include-tables-shipped.md`
if you want the context; otherwise carry on with the admin tenancy redesign on this branch
(`docs/design/` bundle, commit `59b7dce1`). Decision record: issue #398 and PR #401.
