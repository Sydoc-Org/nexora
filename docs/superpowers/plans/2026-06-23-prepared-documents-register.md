# Prepared Documents Register (MS02) — Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the MS02 "prepared documents" *transient session-overlay* import (`?pidImport=<token>` filter over the workitems list, with row-merge + page-1-only synthetic rows) with a **persistent, accumulating, upsert-by-PID register** that lives on its own page (`GET /prepared_documents`). The register is shared across all MS02 users, read-only with a clear-whole-list action, real DB-paginated (OFFSET/FETCH), and carries a live (non-stored) Octo cross-reference status column. The old overlay is torn down so the default workitems path returns byte-identical.

**Architecture:** A new tiny data-access module `nx_lib/prepared_documents.py` owns all I/O against the new table `dbo.PreparedDocuments` (upsert-by-PID, paginated read, count, clear). The upload route `import_prepared_audit` keeps its front half (auth + MS02 gate + MIME sniff + `parse_prepared_xlsx`) and swaps its back half from resolve-to-ids + session stash to a per-PID upsert returning `{inserted, updated, total}`. A new page route `prepared_documents` reads a paginated slice, resolves live Octo status for the visible PIDs via the retained `resolve_ms02_pid_to_wids`, and renders `prepared_documents.html` + `templates/js/_prepared_documents_js.html`. The retired overlay machinery in `_get_workitems_data`, `WorkitemFilter.pid_import_active`, `SqlServerSource.list_workitems`, the CSV synthetic guard, and the workitems-page `pid_processes`/`_ms02_pid_processes` plumbing is deleted (verified to exist solely for this feature).

**Tech Stack:** Python 3, Flask, SQLAlchemy 2.0 + pyodbc (SQL Server / NexoraDB via `engine_nexora_db`), psycopg2-binary (MS02 Postgres via `engine_ms02_docfields_pg`, already present), openpyxl (already present), Flask-WTF CSRF, Flask-Session, Flask-Babel i18n, pytest (unit + integration). No new dependency. One new migration (`0031`). No new permission.

**Design spec:** `docs/superpowers/specs/2026-06-23-prepared-documents-register-design.md` — READ it for any detail not covered here.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63` (NOT `main`). Commit directly onto this branch. **Remote session policy = commit only:** stage + commit freely; do **not** push, do **not** open a PR.
- **Anchor on snippets, never line numbers.** Every "find" step quotes the exact code; line numbers drift.
- **This is mostly a TEARDOWN.** The transient overlay was merged onto `feature/2.5.63` by the two predecessor plans (`docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md` and `docs/superpowers/plans/2026-06-23-prepared-import-button-extra-fields.md`). Those plans are the **inverse map** of the deletion work — read their Phase 3/4 to see exactly the code this plan removes.
- **`resolve_ms02_pid_to_wids` STAYS.** It is retained and repurposed for the live Octo soft-status column. It already exists in `nx_lib/workitem_sources.py` and is already imported in `nx_lib/views/workitems.py` (in the `from ..workitem_sources import (...)` block). Contract: `None` on engine-absent / empty-specs / empty-pids / error (never raises); `{}` on zero matches; `{pid_str: [wid_int, ...]}` for matched PIDs. `_ms02_pid_specs` and `_ms02_target_processes` also STAY (the new page uses them). `_ms02_pid_processes` becomes dead (its only caller is `workitems_overview`) and is removed.
- **`parse_prepared_xlsx` is UNCHANGED.** It already returns `(list[dict], error)`, each dict `{pid, collected, collected_by, prepared, prepared_by}`. Its tests are untouched.
- **`import_prepared_audit` currently has a `if not pid_specs:` early-return** that returns `200` with `{"token": None, ..., "warning": "The personal-number field is not configured for MS02."}`. **This plan intentionally REMOVES that branch** (Task 3): the register must persist rows regardless of whether the PID column is seeded — Octo status is computed later on the page and degrades to a dash. A test asserts upload still succeeds (counts returned) when `_ms02_pid_specs` is empty (the default CI path, since `SearchConfig` has no `'ms02'` `col_pid` in TEST).
- **Migration `0031` is free** (dir tops at `0030_ms02_pdbs_docfield_columnar_config.sql`). NexoraDB, not GeneraliDB. Make it idempotent (`IF NOT EXISTS`) so the `sql-migrate-int` pre-commit hook can re-apply it safely.
- **No new permission.** Reuse `workitems.import.preparedaudit` (seeded by migration `0029`). Guard the new routes with `@require_permission("workitems.import.preparedaudit")` PLUS the runtime `ms02_active` check in the body.
- **`ms02_active` gate (copy verbatim):** `ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None` (as in `workitems_overview`).
- **No-MS02 behaviour:** the page raises `PermissionDenied` (403) when MS02 is absent; the mutating clear route returns `400` with `"MS02"` in the body (matching `import_prepared_audit`). This asymmetry is intentional and is asserted in the route tests.
- **`PermissionDenied` is NOT yet imported in `workitems.py`.** It lives in `nx_lib/security.py` (`class PermissionDenied(HTTPException)`). Add it to the existing `from ..security import (...)` line (Task 4).
- **CI/TEST has NO MS02 engine and NO Statistics/Nexora DB guaranteed.** `engine_ms02_docfields_pg is None`, `"ms02" not in CLIENTS`. The MS02 gate fires: `import_prepared_audit` returns `400` with `"MS02"` in the body (existing tests assert this). DB access in unit tests is **mocked** (`MagicMock` `raw_connection`/cursor) — never assume a live NexoraDB.
- **Test fixtures:** `app`/`client`/`user_client`/`noperm_client` from `tests/conftest.py`. `workitems_all_perms` (monkeypatches `nx_lib.security.has_permission` to always-True) is **local** to `tests/integration/test_workitems_routes.py`. **Route bodies use the `wv`-module-local `has_permission` binding** (imported into `workitems.py`), which `workitems_all_perms` does NOT reach. So any test that needs the in-body `prepared_import_perm` to be True (e.g. to render the gated upload/clear controls) MUST also `monkeypatch.setattr(wv, "has_permission", lambda code: True)` — this is the trap the existing `test_prepared_audit_wrap_renders_without_pid_processes` documents. The `@require_permission` GATE itself uses the security-module binding, so `workitems_all_perms` alone gets you past the decorator.
- **Template cache:** Jinja templates are cached process-lifetime. After ANY edit to a template / JS partial, **restart the dev server** (`nx -u`) before browser/e2e verification.
- **Route registration** is via `app.add_url_rule(...)` in `register_routes(app)` at the bottom of `nx_lib/views/workitems.py`, NOT Flask decorators.
- **DB write pattern (the proven repo exemplar is `_cache_store` in `nx_lib/workitem_sources.py`):** `engine_nexora_db.raw_connection()` + `cursor` + `cursor.execute(MERGE …)` + `conn.commit()` + `except: logger.error` + `finally: conn.close()`. **Critically, `_cache_store`'s MERGE does NOT use `OUTPUT $action` and does NOT `fetchone()` after the MERGE** — that is the verified-against-driver pattern. This plan classifies insert-vs-update with a cheap pre-`SELECT EXISTS` per PID (one extra read per row) rather than relying on `OUTPUT $action`, which is unverified against this repo's pyodbc/SQL-Server setup. The counts are accurate and the path is driver-safe.
- **DB read + pagination pattern:** COUNT then `ORDER BY ID DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY`, returning a `pagination` dict `{currentPage, totalPages, totalItems, perPage}`.
- **Pre-commit / CRLF:** the `sql-migrate-int` hook auto-applies `0031` to INT and `sql-sync-check` regenerates `sql/NexoraDB/Tables/dbo.PreparedDocuments.sql` (do NOT hand-write that dump). On known INT CRLF checksum drift (migrations `0001`–`0003`) use `SQL_SYNC_SKIP=1 git commit ...`. **NEVER `--no-verify`.**
- **Deploy:** no `deploy.yml` change. Route lives in the existing `workitems.py`; the new templates are under `templates/` / `templates/js/` (already mirrored); `0031` is auto-applied by the deploy workflow before mirroring. The new module `nx_lib/prepared_documents.py` is under `nx_lib/` (a runtime dir already mirrored). No new top-level file/dir.
- **i18n:** new strings in the new template + JS partial + route flashes. Wrap with `{{ _('...') }}` / `_('...')`, then run the full pybabel cycle (`/nx-i18n`). `test_translations.py` enforces `messages.pot` in sync + every msgid non-fuzzy in de/fr/it. Use a SINGLE parameterized msgid for the upload summary (not concatenated word fragments).
- **Pre-push gate runs the FULL suite incl. Playwright e2e.** Run `python scripts/test_db_reset.py` first to avoid stale `NEXORA_TEST` state. Prefer integration tests with the monkeypatch pattern over a hard e2e needing a live MS02 engine.

---

## Decisions locked in

| # | Decision | Detail |
|---|---|---|
| 1 | **Persistent table, upsert-by-PID.** | New `dbo.PreparedDocuments` (migration `0031`). One row per `PID` (UNIQUE). Re-uploading a PID updates its row (`MERGE` on `PID`). No history of distinct batches. |
| 2 | **Shared register, global.** | One table for all MS02 users. `UploadedBy` is an audit stamp (bare nullable `INT`, no FK), not a visibility scope. No `ClientCode` column (MS02-only, YAGNI). |
| 3 | **Read-only + clear-whole-list (v1).** | No per-row edit / done-tracking. A single `Clear list` action `DELETE`s all rows (confirm dialog client-side). |
| 4 | **Octo status = live, not stored.** | The route resolves the visible page's PIDs via `resolve_ms02_pid_to_wids(engine_ms02_docfields_pg, _ms02_pid_specs(_ms02_target_processes()), pids)` each load and passes a per-row status to the template. Degrades to "—" on `None`/empty/error (resolver never raises). Nothing about Octo is persisted. |
| 5 | **No new permission.** | Reuse `workitems.import.preparedaudit` (migration `0029`). Add ONE `page_visibility()` key reusing that code. |
| 6 | **New data-access module.** | `nx_lib/prepared_documents.py` owns `upsert_prepared_documents`, `count_prepared_documents`, `fetch_prepared_documents_page`, `clear_prepared_documents`. Keeps the 2000+-line view thin and the DB I/O unit-testable. |
| 7 | **Tear down the overlay.** | Remove the `pid_import:<token>` stash, the `?pidImport=` read-back, the row-merge + synthetic-row block, the CSV synthetic guard, `WorkitemFilter.pid_import_active`, the `SqlServerSource.list_workitems` short-circuit, and the workitems-page `pid_processes`/`_ms02_pid_processes` plumbing (all verified to exist solely for this feature). |
| 8 | **Workitems button → link.** | The `#preparedAuditWrap` upload control on the workitems page becomes a link to `/prepared_documents` (same `{% if prepared_import_perm and ms02_active %}` guard). The `#preparedAuditBanner` + import-column machinery is deleted; the table reverts to its pre-overlay 7-column shape. |
| 9 | **Clear route = `POST /prepared_documents/clear`.** | POST (not DELETE) for CSRF-form simplicity and consistency with the existing import route; JS sends `X-CSRFToken`. |
| 10 | **Insert/update classification via pre-SELECT, not `OUTPUT $action`.** | The repo's proven MERGE exemplar (`_cache_store`) uses no `OUTPUT`/`fetch`; relying on `OUTPUT $action` + `fetchone()` is unverified against this pyodbc setup. A cheap `SELECT 1 … WHERE PID = ?` before each MERGE classifies insert vs update deterministically. |

---

## Owner actions

No blocking actions. Operational confirmations after merge/deploy:

1. **PROD migration:** `0031` auto-applies via the deploy workflow before the app pool stops. Verify `dbo.PreparedDocuments` exists on PROD after deploy (or run `python scripts/db-migrate.py --env PROD`).
2. **Permission grant:** `workitems.import.preparedaudit` already seeded by `0029`. Grant it to any additional MS02 operator profile that should see the register.
3. **PID format alignment (standing MS02 obligation, unchanged):** the Excel `PID` values must match the indexed `DossierStatistik` PID column for the live Octo status to resolve. A mismatch only degrades the soft-status column to "—"; the register still persists and renders. Additionally, the MS02 `SearchConfig` `col_pid` row for the user's `target_processes` (e.g. `ProcessName='sydoc.05_PDBS'`, migration `0030`) must be seeded on PROD for the column to resolve at all.
4. **Decision confirmation:** the register is **read-only** in v1 — no per-row "done" tracking. Confirm this is acceptable for the first release (it is the locked decision).

---

# PHASE 1 — Migration + data-access module (no view wiring yet)

### Task 1: Create migration `0031` for `dbo.PreparedDocuments`

**Files:**
- Create: `sql/_migrations/NexoraDB/0031_create_prepared_documents.sql`

**Interfaces:**
- Produces: table `dbo.PreparedDocuments(ID, PID, Collected, CollectedBy, Prepared, PreparedBy, UploadedBy, UploadedAt, UpdatedAt)` with `PID` UNIQUE.
- Consumes: nothing (pure DDL).

- [ ] **Step:** Re-list the migrations dir to confirm `0031` is still free:
```
ls sql/_migrations/NexoraDB/
```
Expected: highest number is `0030_ms02_pdbs_docfield_columnar_config.sql`. If a newer migration appeared, bump the number everywhere in this task.

- [ ] **Step:** Create `sql/_migrations/NexoraDB/0031_create_prepared_documents.sql` with exactly:
```sql
-- 0031_create_prepared_documents.sql
-- MS02-only standalone 'prepared documents' intake register. Accumulating,
-- upsert-by-PID; shared across MS02 users; read-only + clear-whole-list (v1).
-- Gated by workitems.import.preparedaudit + ms02_active at runtime. Replaces the
-- transient session-overlay pidImport model. No ClientCode column (MS02-only,
-- YAGNI). No new permission (workitems.import.preparedaudit reused from 0029).
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'PreparedDocuments' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.PreparedDocuments (
        ID          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PreparedDocuments PRIMARY KEY,
        PID         NVARCHAR(100) NOT NULL,
        Collected   BIT NOT NULL CONSTRAINT DF_PreparedDocuments_Collected DEFAULT (0),
        CollectedBy NVARCHAR(255) NULL,
        Prepared    BIT NOT NULL CONSTRAINT DF_PreparedDocuments_Prepared DEFAULT (0),
        PreparedBy  NVARCHAR(255) NULL,
        UploadedBy  INT NULL,
        UploadedAt  DATETIME2 NOT NULL CONSTRAINT DF_PreparedDocuments_UploadedAt DEFAULT (SYSUTCDATETIME()),
        UpdatedAt   DATETIME2 NULL,
        CONSTRAINT UQ_PreparedDocuments_PID UNIQUE (PID)
    );
END
GO
```

- [ ] **Step:** Commit (the `sql-migrate-int` hook applies `0031` to INT and `sql-sync-check` regenerates the per-object dump). If the hook fails on known CRLF checksum drift (not a real SQL error), use `SQL_SYNC_SKIP=1 git commit`. Stage the migration AND the auto-generated dump if the hook created it:
```
git add sql/_migrations/NexoraDB/0031_create_prepared_documents.sql sql/NexoraDB/Tables/dbo.PreparedDocuments.sql 2>/dev/null; git add sql/_migrations/NexoraDB/0031_create_prepared_documents.sql
git commit -m "$(cat <<'EOF'
feat(db): add dbo.PreparedDocuments register table (migration 0031)

Create the MS02-only persistent 'prepared documents' intake register: ID
IDENTITY PK, PID NVARCHAR(100) UNIQUE (upsert key), Collected/Prepared BIT
flags, CollectedBy/PreparedBy names, UploadedBy audit stamp, UploadedAt and
UpdatedAt timestamps. No ClientCode column (MS02-only, YAGNI) and no new
permission row (reuses workitems.import.preparedaudit from 0029). Idempotent
IF NOT EXISTS guard so the sql-migrate-int hook can re-apply safely. Replaces
the transient session-overlay pidImport model with a persistent table.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add the `prepared_documents` data-access module (TDD)

**Files:**
- Create: `nx_lib/prepared_documents.py`
- Test: `tests/unit/test_prepared_documents.py`

**Interfaces:**
- `upsert_prepared_documents(rows, uploaded_by) -> dict` — `rows: list[dict]` each `{pid, collected, collected_by, prepared, prepared_by}`; `uploaded_by: int | None`. Returns `{"inserted": int, "updated": int, "total": int}`. Raises `RuntimeError` on DB failure (after rollback).
- `count_prepared_documents() -> int`.
- `fetch_prepared_documents_page(offset, limit) -> list[dict]` — each row dict `{id, pid, collected, collected_by, prepared, prepared_by, uploaded_by, uploaded_at, updated_at}`.
- `clear_prepared_documents() -> int` — rows deleted.
- Consumes: `engine_nexora_db.raw_connection()`.

- [ ] **Step:** Write the failing unit test. Create `tests/unit/test_prepared_documents.py`:
```python
"""Unit tests for the dbo.PreparedDocuments data-access helpers.

CI/TEST has no live NexoraDB, so the cursor/connection is mocked (mirroring
tests/unit/test_workitem_sources.py). Insert vs update is classified by a
pre-SELECT existence check per PID, NOT by MERGE OUTPUT (the repo's proven
MERGE exemplar _cache_store uses neither OUTPUT nor a post-fetch).
"""

from unittest.mock import MagicMock

import nx_lib.prepared_documents as pd


def _mock_engine(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    return engine, conn


def test_upsert_inserts_then_updates_same_pid_no_dup(monkeypatch):
    """Re-uploading the same PID issues a MERGE per row and reports counts; the
    pre-SELECT existence check classifies row 1 as insert, row 2 as update."""
    cur = MagicMock()
    # Per row: one SELECT (existence) then one MERGE. fetchone() answers the
    # SELECT: None -> not present (insert); (1,) -> present (update).
    cur.fetchone.side_effect = [None, (1,)]
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)

    rows = [
        {"pid": "100", "collected": True, "collected_by": "A",
         "prepared": False, "prepared_by": ""},
        {"pid": "100", "collected": False, "collected_by": "",
         "prepared": True, "prepared_by": "B"},
    ]
    result = pd.upsert_prepared_documents(rows, uploaded_by=7)

    assert result == {"inserted": 1, "updated": 1, "total": 2}
    # Two executes per row (SELECT + MERGE) -> 4 total.
    assert cur.execute.call_count == 4
    # The MERGE keys on PID and targets the register.
    merge_calls = [c for c in cur.execute.call_args_list if "MERGE" in c.args[0].upper()]
    assert len(merge_calls) == 2
    assert "PreparedDocuments" in merge_calls[0].args[0]
    assert 7 in merge_calls[0].args[1]  # UploadedBy stamped
    conn.commit.assert_called_once()


def test_upsert_mixed_batch_counts(monkeypatch):
    """A batch with one new and one existing PID -> inserted=1, updated=1."""
    cur = MagicMock()
    cur.fetchone.side_effect = [None, (1,)]
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = [
        {"pid": "111", "collected": True, "collected_by": "A",
         "prepared": False, "prepared_by": ""},
        {"pid": "222", "collected": False, "collected_by": "",
         "prepared": True, "prepared_by": "B"},
    ]
    result = pd.upsert_prepared_documents(rows, uploaded_by=3)
    assert result == {"inserted": 1, "updated": 1, "total": 2}


def test_upsert_raises_runtimeerror_on_db_failure(monkeypatch):
    cur = MagicMock()
    cur.execute.side_effect = Exception("boom")
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = [{"pid": "1", "collected": False, "collected_by": "",
             "prepared": False, "prepared_by": ""}]
    try:
        pd.upsert_prepared_documents(rows, uploaded_by=None)
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
    conn.rollback.assert_called_once()


def test_fetch_page_maps_columns(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [
        (1, "100", True, "A", False, "", 7, "2026-06-23T10:00:00", None),
    ]
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    rows = pd.fetch_prepared_documents_page(offset=0, limit=40)
    assert rows[0]["pid"] == "100"
    assert rows[0]["collected"] is True
    assert rows[0]["collected_by"] == "A"
    assert rows[0]["prepared_by"] == ""
    sql_used = cur.execute.call_args.args[0]
    assert "OFFSET" in sql_used.upper()
    assert "FETCH NEXT" in sql_used.upper()


def test_count_returns_int(monkeypatch):
    cur = MagicMock()
    cur.fetchone.return_value = (12,)
    engine, _conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    assert pd.count_prepared_documents() == 12


def test_clear_deletes_all(monkeypatch):
    cur = MagicMock()
    cur.rowcount = 5
    engine, conn = _mock_engine(cur)
    monkeypatch.setattr(pd, "engine_nexora_db", engine)
    assert pd.clear_prepared_documents() == 5
    sql_used = cur.execute.call_args.args[0]
    assert "DELETE" in sql_used.upper()
    conn.commit.assert_called_once()
```

- [ ] **Step:** Run it red:
```
python -m pytest tests/unit/test_prepared_documents.py -v
```
Expected: `ModuleNotFoundError: No module named 'nx_lib.prepared_documents'`.

- [ ] **Step:** Implement `nx_lib/prepared_documents.py`:
```python
"""Data access for the MS02 'prepared documents' register (dbo.PreparedDocuments).

A thin, unit-testable seam over NexoraDB so the persistent register's I/O does
not live inside the multi-thousand-line workitems view. MS02-only at the call
sites (the routes gate on ms02_active); this module is purely about the table.

Insert vs update is classified by a pre-SELECT existence check per PID, then a
MERGE keyed on PID. This mirrors the repo's proven MERGE exemplar
(workitem_sources._cache_store), which uses neither OUTPUT $action nor a
post-fetch -- relying on OUTPUT $action + fetchone() is unverified against this
repo's pyodbc / SQL Server setup, whereas a SELECT + MERGE is driver-safe.
"""

from flask import current_app

from .db import engine_nexora_db


def upsert_prepared_documents(rows, uploaded_by):
    """Upsert each parsed row into dbo.PreparedDocuments, keyed on PID.

    rows: list[dict] with keys pid/collected/collected_by/prepared/prepared_by.
    uploaded_by: int | None (the acting user's id, an audit stamp).

    Per row: a SELECT classifies insert vs update, then a MERGE on PID applies
    the values (UPDATE sets UpdatedAt; INSERT sets UploadedBy/UploadedAt via the
    column default). Returns {"inserted": int, "updated": int, "total": int}.
    Raises RuntimeError on any DB failure (after rollback) so the caller can
    return a clear error without partially corrupting the register (a single
    failed row aborts the whole batch before commit).
    """
    merge_sql = (
        "MERGE dbo.PreparedDocuments AS tgt "
        "USING (SELECT ? AS PID) AS src ON tgt.PID = src.PID "
        "WHEN MATCHED THEN UPDATE SET "
        "  Collected = ?, CollectedBy = ?, Prepared = ?, PreparedBy = ?, "
        "  UploadedBy = ?, UpdatedAt = SYSUTCDATETIME() "
        "WHEN NOT MATCHED THEN INSERT "
        "  (PID, Collected, CollectedBy, Prepared, PreparedBy, UploadedBy) "
        "  VALUES (?, ?, ?, ?, ?, ?);"
    )
    inserted = 0
    updated = 0
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        for row in rows:
            pid = str(row.get("pid") or "").strip()
            if not pid:
                continue
            collected = 1 if row.get("collected") else 0
            collected_by = (row.get("collected_by") or "") or None
            prepared = 1 if row.get("prepared") else 0
            prepared_by = (row.get("prepared_by") or "") or None
            cur.execute(
                "SELECT 1 FROM dbo.PreparedDocuments WHERE PID = ?", [pid]
            )
            exists = cur.fetchone() is not None
            cur.execute(
                merge_sql,
                [
                    pid,
                    collected, collected_by, prepared, prepared_by, uploaded_by,
                    pid, collected, collected_by, prepared, prepared_by, uploaded_by,
                ],
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        conn.commit()
        return {"inserted": inserted, "updated": updated, "total": inserted + updated}
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        current_app.logger.error(f"upsert_prepared_documents: {e}")
        raise RuntimeError("prepared documents upsert failed") from e
    finally:
        if conn is not None:
            conn.close()


def count_prepared_documents():
    """Total row count of the register (for pagination)."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.PreparedDocuments")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        if conn is not None:
            conn.close()


def fetch_prepared_documents_page(offset, limit):
    """Return one OFFSET/FETCH page of the register, newest id first.

    Returns list[dict] with keys id/pid/collected/collected_by/prepared/
    prepared_by/uploaded_by/uploaded_at/updated_at.
    """
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT ID, PID, Collected, CollectedBy, Prepared, PreparedBy, "
            "       UploadedBy, UploadedAt, UpdatedAt "
            "FROM dbo.PreparedDocuments "
            "ORDER BY ID DESC "
            "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            [int(offset), int(limit)],
        )
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


def clear_prepared_documents():
    """Delete every row in the register. Returns the number of rows removed."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.PreparedDocuments")
        deleted = cur.rowcount
        conn.commit()
        return int(deleted) if deleted is not None and deleted >= 0 else 0
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step:** Run green:
```
python -m pytest tests/unit/test_prepared_documents.py -v
```

- [ ] **Step:** ruff:
```
ruff check nx_lib/prepared_documents.py tests/unit/test_prepared_documents.py && ruff format nx_lib/prepared_documents.py tests/unit/test_prepared_documents.py
```

- [ ] **Step:** Commit:
```
git add nx_lib/prepared_documents.py tests/unit/test_prepared_documents.py
git commit -m "$(cat <<'EOF'
feat(prepared-docs): add PreparedDocuments data-access module

Add nx_lib/prepared_documents.py owning all I/O against dbo.PreparedDocuments:
upsert_prepared_documents (pre-SELECT existence check to classify insert vs
update, then a MERGE per row keyed on PID; rollback + RuntimeError on failure),
count, OFFSET/FETCH paginated read (newest id first), and clear. Classifying via
a SELECT + MERGE mirrors the proven _cache_store exemplar rather than relying on
unverified MERGE OUTPUT $action. Keeps the register's DB access in one
unit-testable seam instead of the workitems view. Unit tests cover
insert-then-update-same-PID (no duplicate), mixed batch counts, DB-failure
rollback, column mapping, count, and clear, all with a mocked raw_connection.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 2 — Rewrite the upload route to upsert

### Task 3: Rewrite `import_prepared_audit` to upsert into the register

**Files:**
- Modify: `nx_lib/views/workitems.py` (`import_prepared_audit`, imports)
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes (unchanged front half): auth gate, MS02 gate, `is_file_allowed`, `parse_prepared_xlsx(data) -> (list[dict], err)`.
- Produces (new back half): JSON `{"inserted", "updated", "total"}` (200) on success; `{"error": ...}` (400/500) on failure. The MS02 gate (400) and parse/empty gates are unchanged.
- **Intentionally removed:** the `if not pid_specs:` warning early-return — the register persists rows regardless of PID-column seeding; Octo status is computed later on the page and degrades to a dash.

- [ ] **Step:** Import the data-access helpers. In `nx_lib/views/workitems.py`, find the existing `from ..workitem_sources import (` block (it already imports `parse_prepared_xlsx` and `resolve_ms02_pid_to_wids`). Immediately AFTER the `from ..security import has_permission, page_visibility, require_permission` line, add a new import line:
```python
from ..prepared_documents import (
    clear_prepared_documents,
    count_prepared_documents,
    fetch_prepared_documents_page,
    upsert_prepared_documents,
)
```

- [ ] **Step:** Confirm the existing gate tests still describe the unchanged front half. They stay valid (CI fires the MS02 gate first): `test_import_prepared_audit_gated` (403), `test_import_prepared_audit_no_file` (400 + "MS02"), `test_import_prepared_audit_rejects_non_xlsx` (400 + "MS02"). No change needed there.

- [ ] **Step:** Add new integration tests for the upsert path (incl. the no-PID-specs persistence path that the removed warning branch used to short-circuit). Append to the `/import_prepared_audit` test group in `tests/integration/test_workitems_routes.py`:
```python
def test_import_prepared_audit_upserts_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    """Past the MS02 gate, a valid xlsx upserts into the register and returns
    {inserted, updated, total} (no token, no synthetic-row machinery)."""
    import io

    import openpyxl

    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    # Bypass the MIME sniff for the synthetic xlsx bytes.
    monkeypatch.setattr(wv, "is_file_allowed", lambda name, stream: True)

    captured = {}

    def fake_upsert(rows, uploaded_by):
        captured["rows"] = rows
        captured["uploaded_by"] = uploaded_by
        return {"inserted": len(rows), "updated": 0, "total": len(rows)}

    monkeypatch.setattr(wv, "upsert_prepared_documents", fake_upsert)

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(["PID", "Collected", "CollectedBy", "Prepared", "PreparedBy"])
    sh.append(["100", 1, "Alice", 1, "Bob"])
    buf = io.BytesIO()
    wb.save(buf)

    resp = user_client.post(
        "/import_prepared_audit",
        data={"preparedAuditFile": (io.BytesIO(buf.getvalue()), "p.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["inserted"] == 1
    assert captured["rows"][0]["pid"] == "100"


def test_import_prepared_audit_persists_even_without_pid_specs(
    user_client, workitems_all_perms, monkeypatch
):
    """The register must persist rows even when no MS02 PID specs are configured
    (the default CI/TEST path: SearchConfig has no 'ms02' col_pid). The old
    warning early-return is intentionally gone -- Octo status degrades on the
    page, the upload still upserts."""
    import io

    import openpyxl

    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "is_file_allowed", lambda name, stream: True)
    # No PID specs configured.
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [])
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: [])
    monkeypatch.setattr(
        wv, "upsert_prepared_documents",
        lambda rows, uploaded_by: {"inserted": len(rows), "updated": 0, "total": len(rows)},
    )

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(["PID", "Prepared"])
    sh.append(["100", 1])
    buf = io.BytesIO()
    wb.save(buf)

    resp = user_client.post(
        "/import_prepared_audit",
        data={"preparedAuditFile": (io.BytesIO(buf.getvalue()), "p.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert "token" not in body
    assert "warning" not in body


def test_import_prepared_audit_db_failure_returns_500(
    user_client, workitems_all_perms, monkeypatch
):
    import io

    import openpyxl

    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "is_file_allowed", lambda name, stream: True)

    def boom(rows, uploaded_by):
        raise RuntimeError("db down")

    monkeypatch.setattr(wv, "upsert_prepared_documents", boom)

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(["PID", "Prepared"])
    sh.append(["100", 1])
    buf = io.BytesIO()
    wb.save(buf)

    resp = user_client.post(
        "/import_prepared_audit",
        data={"preparedAuditFile": (io.BytesIO(buf.getvalue()), "p.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 500
    assert "error" in (resp.get_json() or {})
```

- [ ] **Step:** Run them red:
```
python -m pytest tests/integration/test_workitems_routes.py -k "upserts_when_ms02_active or persists_even_without_pid_specs or db_failure_returns_500" -v
```
Expected red: the current route returns the old `{token, payloads, matched, total}` / warning payload, not `{inserted, updated, total}`.

- [ ] **Step:** Replace the back half of `import_prepared_audit`. Find the span that begins:
```python
    pids = [row["pid"] for row in pairs]
    payloads = {
```
and runs through the route's final:
```python
    return jsonify(
        {
            "token": token,
            "payloads": payloads,
            "matched": len(matched_pids),
            "total": len(pids),
        }
    ), 200
```
Replace that **entire span** (including the `pids = ...`, the `payloads = {...}` dict, the `pid_specs = _ms02_pid_specs(...)` line, the `if not pid_specs:` warning early-return, the `resolve_ms02_pid_to_wids` call + `id_set`/`matched_pids`/`ids` lines, the `token = secrets.token_urlsafe(16)` + `session[f"pid_import:{token}"] = {...}` stash, and the final `return jsonify({"token": ...}), 200`) with:
```python
    rows = [
        {
            "pid": row["pid"],
            "collected": row["collected"],
            "collected_by": row["collected_by"],
            "prepared": row["prepared"],
            "prepared_by": row["prepared_by"],
        }
        for row in pairs
    ]

    try:
        result = upsert_prepared_documents(rows, session.get("userid"))
    except RuntimeError:
        return jsonify(
            {"error": _("Could not save the prepared documents. Please try again.")}
        ), 500
    return jsonify(result), 200
```

- [ ] **Step:** Update the `import_prepared_audit` docstring. Find:
```python
    """MS02-only: upload a five-column Excel (PID, Collected, CollectedBy,
```
Replace the whole docstring body with:
```python
    """MS02-only: upload a five-column Excel (PID, Collected, CollectedBy,
    Prepared, PreparedBy) and UPSERT each row by PID into the persistent
    dbo.PreparedDocuments register (one row per PID; re-uploading a PID updates
    its row). Returns {inserted, updated, total}. The register is shared across
    MS02 users and viewed on the /prepared_documents page (this route no longer
    resolves PIDs to workitem ids or stashes anything in the session). Rows
    persist regardless of whether the PID column is configured -- the live Octo
    status on the page degrades to a dash when it cannot resolve."""
```

- [ ] **Step:** Run green + the full `/import_prepared_audit` group:
```
python -m pytest tests/integration/test_workitems_routes.py -k import_prepared_audit -v
```

- [ ] **Step:** ruff. Note: `resolve_ms02_pid_to_wids`, `_ms02_pid_specs`, `_ms02_target_processes`, `secrets` are no longer called inside `import_prepared_audit`, but `resolve_ms02_pid_to_wids` / `_ms02_pid_specs` / `_ms02_target_processes` gain a new caller in Task 4 (the page route) — keep their imports. `secrets` may now be unused; if ruff flags it as unused, check for other callers first (`grep -n "secrets\." nx_lib/views/workitems.py`) and only remove the import if there are none.
```
ruff check nx_lib/views/workitems.py
```
(Defer the commit to the end of Phase 3 Task 4 so `resolve_ms02_pid_to_wids`/`_ms02_pid_specs` have their new caller and ruff is clean. If you must commit now, only do so after confirming `resolve_ms02_pid_to_wids` is still imported and ruff passes — but the recommended order is to land Task 4 first.)

---

# PHASE 3 — New page route + templates

### Task 4: Add `GET /prepared_documents` (paginated + live Octo status) and `POST /prepared_documents/clear`

**Files:**
- Modify: `nx_lib/views/workitems.py` (two new view functions + `register_routes`, add `PermissionDenied` import)
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- `GET /prepared_documents` — gated by `@require_permission("workitems.import.preparedaudit")` + in-body `ms02_active`. Renders `prepared_documents.html` with `rows`, `pagination` dict, `octo_status` (`{pid: {"in_octo": bool, "wid": int | None}}`), `prepared_import_perm`, `ms02_active`, plus `pageV=page_visibility()`.
- `POST /prepared_documents/clear` — same perm gate; in-body `ms02_active` returns `400` with `"MS02"` when absent; deletes all rows; returns JSON `{"deleted": int}`.
- Consumes: `count_prepared_documents`, `fetch_prepared_documents_page`, `clear_prepared_documents`, `resolve_ms02_pid_to_wids(engine_ms02_docfields_pg, _ms02_pid_specs(_ms02_target_processes()), pids)`, `page_visibility()`, `PermissionDenied`.

- [ ] **Step:** Add the `PermissionDenied` import. In `nx_lib/views/workitems.py`, find:
```python
from ..security import has_permission, page_visibility, require_permission
```
Replace with:
```python
from ..security import (
    PermissionDenied,
    has_permission,
    page_visibility,
    require_permission,
)
```

- [ ] **Step:** Write failing integration tests. In `tests/integration/test_workitems_routes.py`, add a new section:
```python
# ====================== /prepared_documents (register page) =================


def test_prepared_documents_page_gated(noperm_client):
    """No permission -> 403 (or login redirect)."""
    resp = noperm_client.get("/prepared_documents")
    assert resp.status_code in (403, 302)


def test_prepared_documents_page_denies_without_ms02(user_client, workitems_all_perms):
    """Perm present but no MS02 engine in CI -> ms02_active gate denies (403)."""
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 403


def test_prepared_documents_page_renders_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    """Perm + ms02_active -> 200; table renders. DB read + Octo resolve mocked.
    The in-body prepared_import_perm uses the wv-local has_permission binding,
    so patch that too (the documented fixture trap)."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "count_prepared_documents", lambda: 1)
    monkeypatch.setattr(
        wv, "fetch_prepared_documents_page",
        lambda offset, limit: [
            {"id": 1, "pid": "100", "collected": True, "collected_by": "A",
             "prepared": False, "prepared_by": "", "uploaded_by": 7,
             "uploaded_at": None, "updated_at": None}
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})

    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert b"100" in resp.data


def test_prepared_documents_page_octo_resolve_failure_degrades(
    user_client, workitems_all_perms, monkeypatch
):
    """resolve returning None must NOT break the page (status degrades to dash)."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "count_prepared_documents", lambda: 1)
    monkeypatch.setattr(
        wv, "fetch_prepared_documents_page",
        lambda offset, limit: [
            {"id": 1, "pid": "100", "collected": False, "collected_by": "",
             "prepared": False, "prepared_by": "", "uploaded_by": None,
             "uploaded_at": None, "updated_at": None}
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: None)

    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200


def test_prepared_documents_clear_gated(noperm_client):
    resp = noperm_client.post("/prepared_documents/clear")
    assert resp.status_code in (403, 302)


def test_prepared_documents_clear_400_without_ms02(user_client, workitems_all_perms):
    resp = user_client.post("/prepared_documents/clear")
    assert resp.status_code == 400
    assert b"MS02" in resp.data


def test_prepared_documents_clear_deletes_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "clear_prepared_documents", lambda: 3)
    resp = user_client.post("/prepared_documents/clear")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 3
```

- [ ] **Step:** Run red:
```
python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -v
```
Expected: 404 (routes not registered yet).

- [ ] **Step:** Implement the two view functions. In `nx_lib/views/workitems.py`, add them immediately **before** `def register_routes(app):`:
```python
@require_permission("workitems.import.preparedaudit")
def prepared_documents():
    """MS02-only standalone 'prepared documents' register page. Reads a real
    OFFSET/FETCH page of dbo.PreparedDocuments and resolves a live (non-stored)
    Octo cross-reference status for the visible PIDs via resolve_ms02_pid_to_wids.
    Read-only + clear-whole-list for v1."""
    ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
    if not ms02_active:
        raise PermissionDenied(_("This page is only available for the MS02 client."))

    per_page = 40
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * per_page

    try:
        total_items = count_prepared_documents()
        rows = fetch_prepared_documents_page(offset, per_page)
    except Exception as e:
        current_app.logger.error(f"prepared_documents read: {e}")
        total_items, rows = 0, []

    # Live Octo soft-status for the visible page's PIDs (never stored; degrade to
    # a dash on None/empty/error -- resolve_ms02_pid_to_wids never raises).
    octo_status = {}
    pids = [r["pid"] for r in rows if r["pid"]]
    if pids:
        pid_specs = _ms02_pid_specs(_ms02_target_processes())
        pid_to_wids = (
            resolve_ms02_pid_to_wids(engine_ms02_docfields_pg, pid_specs, pids)
            if pid_specs
            else None
        )
        if pid_to_wids:
            for pid, wids in pid_to_wids.items():
                if wids:
                    octo_status[pid] = {"in_octo": True, "wid": wids[0]}

    total_pages = math.ceil(total_items / per_page) if per_page else 0
    pagination = {
        "currentPage": page,
        "totalPages": total_pages,
        "totalItems": total_items,
        "perPage": per_page,
    }
    return render_template(
        "prepared_documents.html",
        rows=rows,
        pagination=pagination,
        octo_status=octo_status,
        prepared_import_perm=has_permission("workitems.import.preparedaudit"),
        ms02_active=ms02_active,
        pageV=page_visibility(),
    )


@require_permission("workitems.import.preparedaudit")
def clear_prepared_documents_route():
    """MS02-only: delete every row in the prepared-documents register."""
    ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
    if not ms02_active:
        return jsonify(
            {"error": _("This import is only available for the MS02 client.")}
        ), 400
    try:
        deleted = clear_prepared_documents()
    except Exception as e:
        current_app.logger.error(f"clear_prepared_documents_route: {e}")
        return jsonify(
            {"error": _("Could not clear the prepared documents. Please try again.")}
        ), 500
    return jsonify({"deleted": deleted}), 200
```
Note: `math`, `request`, `render_template`, `current_app`, `jsonify`, `has_permission`, `page_visibility`, `_` are already imported in this module; `PermissionDenied` was added in the first step of this task.

- [ ] **Step:** Register the two routes. In `register_routes(app)`, find the existing block:
```python
    app.add_url_rule(
        "/import_prepared_audit",
        endpoint="import_prepared_audit",
        view_func=import_prepared_audit,
        methods=["POST"],
    )
```
Insert immediately after it:
```python
    app.add_url_rule(
        "/prepared_documents",
        endpoint="prepared_documents",
        view_func=prepared_documents,
        methods=["GET"],
    )
    app.add_url_rule(
        "/prepared_documents/clear",
        endpoint="clear_prepared_documents_route",
        view_func=clear_prepared_documents_route,
        methods=["POST"],
    )
```

- [ ] **Step:** Run the gate/clear tests green now (the two `200`-render tests will 500 on `TemplateNotFound` until Task 5 creates the template — that is expected; they go green at the end of Task 5):
```
python -m pytest tests/integration/test_workitems_routes.py -k "prepared_documents_page_gated or denies_without_ms02 or prepared_documents_clear" -v
```

- [ ] **Step:** ruff + commit Phase 2 + this task together (route rewrite + page/clear routes keep `resolve_ms02_pid_to_wids` and `_ms02_pid_specs` in use, so ruff is clean):
```
ruff check nx_lib/views/workitems.py tests/integration/test_workitems_routes.py && ruff format nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -m "$(cat <<'EOF'
feat(workitems): persist prepared-docs upload + add register page routes

import_prepared_audit keeps its auth + MS02 gate + MIME sniff + parse front half
but replaces the back half: instead of resolving PIDs to workitem ids and
stashing {ids, pid_to_wids, payloads} in the session under a token, it upserts
each parsed row by PID into dbo.PreparedDocuments via the new data-access module
and returns {inserted, updated, total}. The 'PID field not configured' warning
early-return is intentionally dropped -- the register persists rows regardless
of PID-column seeding; Octo status degrades on the page. A failed upsert returns
a 500 with a clear error. New GET /prepared_documents renders the standalone
register with real OFFSET/FETCH pagination and a live (non-stored) Octo
soft-status column resolved per page via resolve_ms02_pid_to_wids (dash on
None/error). New POST /prepared_documents/clear empties the register. Both
routes reuse workitems.import.preparedaudit plus the runtime ms02_active gate
(403 on the page, 400 with 'MS02' on clear when MS02 is absent). Template lands
in the next commit.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Create the page template + paired JS partial

**Files:**
- Create: `templates/prepared_documents.html`
- Create: `templates/js/_prepared_documents_js.html`
- Test: covered by `test_prepared_documents_page_renders_when_ms02_active` + `..._octo_resolve_failure_degrades` from Task 4 — flip them green here.

**Interfaces:**
- Consumes (template context from Task 4): `rows` (each with `octo_status` looked up by `pid`), `pagination`, `octo_status`, `prepared_import_perm`, `ms02_active`, `pageV`, `csrf_token()`, the global `API_PREFIX`/`csrfToken`.
- Produces: rendered register page (`id="preparedDocsTable"`); the JS partial wires upload (`POST import_prepared_audit`), clear (`POST prepared_documents/clear` with confirm), and pagination reload.

- [ ] **Step:** Before authoring, read the head/body skeleton of a sibling page so the asset links + `nx-*` classes match this repo exactly (do NOT guess the stylesheet href):
```
sed -n '1,40p' templates/workitems_overview.html
```
Copy the exact `<head>` asset block, `_header.html` include, and `nx-*` class set from there. The skeleton below is illustrative — reconcile its `<head>`/CSS hrefs against the sibling page.

- [ ] **Step:** Create `templates/prepared_documents.html`:
```html
<!DOCTYPE html>
<html lang="{{ get_locale }}">

<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ _("Prepared Documents") }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />
  <link rel="stylesheet" href="{{ url_for('static', filename='css/workitems_overview.css') }}" />
  <link rel="icon" type="image/x-icon" href="{{ url_for('static', filename='images/favicon.ico') }}" />
</head>

<body class="nx-app">
  {% set active_page = 'prepared_documents' %}
  {% include '_header.html' %}

  <main class="nx-main">
    <div class="nx-page-head nx-rise">
      <div class="nx-page-head__main">
        <div class="nx-page-head__title">
          <span class="nx-page-icon"><i class="fas fa-file-excel"></i></span>
          <div>
            <h1 class="nx-title">{{ _("Prepared Documents") }}</h1>
            <p class="nx-subtitle">{{ _("Intake register of collected and prepared documents") }}</p>
          </div>
        </div>
      </div>
      <div class="nx-page-head__actions">
        <div class="nx-count-pill">
          <span class="nx-count-pill__label">{{ _("Total") }}</span>
          <span class="nx-count-pill__value">{{ pagination.totalItems }}</span>
        </div>
        <input type="hidden" id="csrfToken" value="{{ csrf_token() }}" />
        {% if prepared_import_perm and ms02_active %}
        <input type="file" id="preparedDocsFile" name="preparedAuditFile"
          class="hidden" accept=".xlsx" data-testid="prepared-docs-file" />
        <button type="button" id="preparedDocsUploadBtn"
          class="nx-btn nx-btn--primary" data-testid="prepared-docs-upload">
          <i class="fas fa-upload mr-2"></i>{{ _("Upload Excel") }}
        </button>
        <button type="button" id="preparedDocsClearBtn"
          class="nx-btn nx-btn--secondary" data-testid="prepared-docs-clear">
          <i class="fas fa-trash mr-2"></i>{{ _("Clear list") }}
        </button>
        {% endif %}
      </div>
    </div>

    <div id="preparedDocsNotice"
      class="hidden mt-3 rounded-lg border px-4 py-3 text-sm" data-testid="prepared-docs-notice">
      <span id="preparedDocsNoticeText"></span>
    </div>

    <div class="nx-table-wrap nx-rise-3 relative mt-6">
      <div class="overflow-x-auto">
        <table class="nx-table" id="preparedDocsTable">
          <thead>
            <tr>
              <th scope="col" class="px-6 py-3 text-left">
                <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("PID") }}</span>
              </th>
              <th scope="col" class="px-6 py-3 text-center">
                <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Collected") }}</span>
              </th>
              <th scope="col" class="px-6 py-3 text-left">
                <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Collected by") }}</span>
              </th>
              <th scope="col" class="px-6 py-3 text-center">
                <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Prepared") }}</span>
              </th>
              <th scope="col" class="px-6 py-3 text-left">
                <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Prepared by") }}</span>
              </th>
              <th scope="col" class="px-6 py-3 text-center">
                <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Octo status") }}</span>
              </th>
            </tr>
          </thead>
          <tbody id="preparedDocsTbody">
            {% for r in rows %}
            <tr data-testid="prepared-docs-row">
              <td class="px-6 py-4 whitespace-nowrap text-sm">{{ r.pid }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-center">
                {% if r.collected %}<i class="fas fa-check text-emerald-600"></i>{% else %}<span class="text-gray-300">—</span>{% endif %}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">{{ r.collected_by }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-center">
                {% if r.prepared %}<i class="fas fa-check text-emerald-600"></i>{% else %}<span class="text-gray-300">—</span>{% endif %}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">{{ r.prepared_by }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-center text-sm">
                {% set st = octo_status.get(r.pid) %}
                {% if st and st.in_octo %}
                  <a href="{{ url_for('workitems_overview') }}?search={{ st.wid }}"
                     class="text-indigo-600 underline" data-testid="prepared-docs-octo-link">
                    <i class="fas fa-up-right-from-square mr-1"></i>{{ _("In Octo") }}
                  </a>
                {% else %}
                  <span class="text-gray-300">—</span>
                {% endif %}
              </td>
            </tr>
            {% else %}
            <tr>
              <td colspan="6" class="text-center py-20 text-gray-400">
                {{ _("No prepared documents yet. Upload an Excel to get started.") }}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      <div class="nx-pagination" id="preparedDocsPagination"
        data-current-page="{{ pagination.currentPage }}"
        data-total-pages="{{ pagination.totalPages }}"
        data-per-page="{{ pagination.perPage }}">
        <a class="nx-btn nx-btn--secondary {% if pagination.currentPage <= 1 %}opacity-40 pointer-events-none{% endif %}"
           href="?page={{ pagination.currentPage - 1 }}"
           data-testid="prepared-docs-prev">{{ _("Previous") }}</a>
        <span class="px-3 text-sm text-gray-600">
          {{ pagination.currentPage }} / {{ pagination.totalPages if pagination.totalPages else 1 }}
        </span>
        <a class="nx-btn nx-btn--secondary {% if pagination.currentPage >= pagination.totalPages %}opacity-40 pointer-events-none{% endif %}"
           href="?page={{ pagination.currentPage + 1 }}"
           data-testid="prepared-docs-next">{{ _("Next") }}</a>
      </div>
    </div>
  </main>

  {% include 'js/_prepared_documents_js.html' %}
</body>

</html>
```

- [ ] **Step:** Create `templates/js/_prepared_documents_js.html`. Model the uploader on the existing `uploadPreparedAudit` in `_workitems_overview_js.html` (same `FormData('preparedAuditFile')`, `X-CSRFToken` header). Note the upload summary uses a SINGLE parameterized msgid:
```html
<script>
  (function () {
    const API_PREFIX = window.API_PREFIX || "/";
    const csrfToken = document.getElementById("csrfToken")?.value || "";

    const fileInput = document.getElementById("preparedDocsFile");
    const uploadBtn = document.getElementById("preparedDocsUploadBtn");
    const clearBtn = document.getElementById("preparedDocsClearBtn");
    const notice = document.getElementById("preparedDocsNotice");
    const noticeText = document.getElementById("preparedDocsNoticeText");

    function showNotice(message, ok) {
      if (!notice || !noticeText) return;
      noticeText.textContent = message;
      notice.classList.remove("hidden");
      notice.classList.toggle("border-emerald-200", ok);
      notice.classList.toggle("bg-emerald-50", ok);
      notice.classList.toggle("text-emerald-800", ok);
      notice.classList.toggle("border-rose-200", !ok);
      notice.classList.toggle("bg-rose-50", !ok);
      notice.classList.toggle("text-rose-800", !ok);
    }

    uploadBtn?.addEventListener("click", () => fileInput?.click());

    fileInput?.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("preparedAuditFile", file);
      try {
        const resp = await fetch(`${API_PREFIX}import_prepared_audit`, {
          headers: { "X-CSRFToken": csrfToken },
          method: "POST",
          body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) {
          showNotice(data.error || "{{ _('Upload failed.') }}", false);
          return;
        }
        const tmpl = "{{ _('Imported %(total)s rows (%(new)s new, %(updated)s updated).') }}";
        const msg = tmpl
          .replace("%(total)s", data.total)
          .replace("%(new)s", data.inserted)
          .replace("%(updated)s", data.updated);
        showNotice(msg, true);
        setTimeout(() => window.location.reload(), 700);
      } catch (e) {
        showNotice("{{ _('Upload failed.') }}", false);
      } finally {
        fileInput.value = "";
      }
    });

    clearBtn?.addEventListener("click", async () => {
      if (!window.confirm("{{ _('Clear the entire prepared-documents list? This cannot be undone.') }}")) {
        return;
      }
      try {
        const resp = await fetch(`${API_PREFIX}prepared_documents/clear`, {
          headers: { "X-CSRFToken": csrfToken },
          method: "POST",
        });
        const data = await resp.json();
        if (!resp.ok) {
          showNotice(data.error || "{{ _('Could not clear the list.') }}", false);
          return;
        }
        showNotice("{{ _('Prepared-documents list cleared.') }}", true);
        setTimeout(() => window.location.reload(), 500);
      } catch (e) {
        showNotice("{{ _('Could not clear the list.') }}", false);
      }
    });
  })();
</script>
```

- [ ] **Step:** Restart the dev server so the new templates are picked up (Jinja cache), then run the full `/prepared_documents` route group green:
```
nx -u
python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -v
```
All route tests pass (incl. the two `200`-render tests now that the template + partial exist).

- [ ] **Step:** Browser-verify (remote session → screenshot). Start + login as an MS02 user, drive Playwright to `/prepared_documents`, screenshot the empty-state and a populated table to `var/screenshots/`, and SendUserFile them:
```
nx -u -b --loginas:<ms02_user>
```

- [ ] **Step:** Commit:
```
git add templates/prepared_documents.html templates/js/_prepared_documents_js.html
git commit -m "$(cat <<'EOF'
feat(prepared-docs): add register page template + paired JS partial

templates/prepared_documents.html renders the standalone register: PID,
Collected, Collected by, Prepared, Prepared by, and a live Octo status column
(In Octo + open-workitem link when matched, dash otherwise). Real OFFSET/FETCH
pagination via the route-provided pagination dict. Paired
templates/js/_prepared_documents_js.html wires the Excel upload (multipart POST
to import_prepared_audit with a single parameterized summary msgid) and the
Clear-list confirm (POST to prepared_documents/clear), each reloading the table.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 4 — Tear down the old overlay

### Task 6: Verify `pid_import_active` is feature-only, then remove the overlay from `_get_workitems_data`, the filter, and the source

**Files:**
- Modify: `nx_lib/views/workitems.py` (`_get_workitems_data`, `export_workitems_csv`)
- Modify: `nx_lib/workitem_sources.py` (`WorkitemFilter.pid_import_active`, `SqlServerSource.list_workitems`)
- Test: `tests/unit/test_workitems_pid_filter.py`, `tests/unit/test_workitem_sources.py`

**Interfaces:**
- Removed: `?pidImport=` read-back, `pid_import_active`/`_pid_import_meta`, row-merge + synthetic-row append, CSV synthetic guard, `WorkitemFilter.pid_import_active`, `SqlServerSource.list_workitems` short-circuit.
- The default workitems path becomes byte-identical to its pre-overlay state.

- [ ] **Step:** VERIFY `pid_import_active`/`synthetic`/`pidImport` are referenced only by the overlay before deleting:
```
grep -rn "pid_import_active\|pid_import:\|_pid_import_meta\|\.synthetic\|pidImport\|_ms02_pid_processes\|pid_processes" nx_lib/ templates/ tests/
```
Expect references only in: `nx_lib/views/workitems.py` (`_get_workitems_data` overlay block, `workitems_overview` pid_processes, the `_ms02_pid_processes` def), `nx_lib/workitem_sources.py` (`WorkitemFilter.pid_import_active`, `SqlServerSource.list_workitems` short-circuit), `templates/js/_workitems_overview_js.html` + `templates/workitems_overview.html` (Task 7), and the tests being retired. If any OTHER consumer appears, STOP and re-scope.

- [ ] **Step:** Delete the overlay read-back block in `_get_workitems_data`. Find the block starting at the header comment (anchor on this EXACT first line so the whole comment header is removed):
```python
    # --- MS02 'prepared documents' PID import allow-set ---
```
through the final line of that block:
```python
        ms02_docfield_ids = pid_ids if ms02_docfield_ids is None else ms02_docfield_ids & pid_ids
```
Delete the entire span (the `# --- MS02 ... ---` header, the multi-line explanatory comment, `pid_import_active = False`, `_pid_import_meta = None`, the `pid_token = args.get("pidImport", "").strip()` read, the `if pid_token:` body, and the final `ms02_docfield_ids = pid_ids if ...` line).

- [ ] **Step:** Drop the `pid_import_active` kwarg from the `WorkitemFilter(...)` construction. Find:
```python
        ms02_docfield_ids=ms02_docfield_ids,  # MS02 doc-field DB-resolved -> PostgresSource
        pid_import_active=pid_import_active,
    )
```
Replace with:
```python
        ms02_docfield_ids=ms02_docfield_ids,  # MS02 doc-field DB-resolved -> PostgresSource
    )
```

- [ ] **Step:** Remove the merge + synthetic-row block and revert `workitems_list`. Find:
```python
    rows, total_items, degraded = fetch_merged_page(filt, offset, per_page)
    workitems_list = list(rows)

    if pid_import_active and _pid_import_meta:
```
through the end of that `if` block:
```python
            n_synthetic = sum(1 for pid in payloads if pid not in matched_pids)
            total_items += n_synthetic
```
Replace the **whole span** (from `workitems_list = list(rows)` through `total_items += n_synthetic`) with:
```python
    workitems_list = rows
```
So the result reads:
```python
    rows, total_items, degraded = fetch_merged_page(filt, offset, per_page)
    workitems_list = rows

    total_pages = math.ceil(total_items / per_page) if per_page else 0
```

- [ ] **Step:** Delete the CSV synthetic guard in `export_workitems_csv`. Find:
```python
    workitems = [w for w in workitems if not w.get("synthetic")]
    if specific_ids:
```
Replace with:
```python
    if specific_ids:
```

- [ ] **Step:** Remove `WorkitemFilter.pid_import_active`. In `nx_lib/workitem_sources.py`, find (including the preceding comment):
```python
    # True when the request is an MS02 'prepared documents' PID import. The
    # default SQL Server source has no PID concept, so it contributes nothing
    # during a PID import -- the list shows only the matched MS02 workitems.
    pid_import_active: bool = False
```
Delete those 4 lines. (`pid_import_active` is the LAST defaulted field, so removing it does not break positional `WorkitemFilter(...)` construction elsewhere — verify by re-reading the dataclass field order if unsure.)

- [ ] **Step:** Remove the `SqlServerSource.list_workitems` short-circuit. Find:
```python
        if filt.pid_import_active:
            return [], 0  # MS02-only PID import: default source contributes nothing
```
Delete those 2 lines.

- [ ] **Step:** Retire the dead overlay tests. In `tests/unit/test_workitems_pid_filter.py`, delete every test that exercises removed code (anchor by these names/snippets): the `session["pid_import:tok..."] = {...}`/`= [...]` stash tests, `test_richer_stash_*`, `test_import_payload_merged_onto_matched_row`, `test_unmatched_pid_becomes_synthetic_row_on_page_1`, `test_synthetic_rows_not_appended_on_page_2`, and any test asserting `pid_import_active` or `.get("synthetic")`. KEEP any test asserting the byte-identical default (`ms02_docfield_ids`/`docfield_ids`) path; if a kept test references `pid_import_active`, drop that assertion. If the file ends up empty, `git rm tests/unit/test_workitems_pid_filter.py`. In `tests/unit/test_workitem_sources.py`, delete `test_sqlserver_source_suppressed_during_pid_import` (it constructs `WorkitemFilter(pid_import_active=True)`). KEEP all `resolve_ms02_pid_to_wids` and `resolve_ms02_pid_ids` tests.

- [ ] **Step:** ruff:
```
ruff check nx_lib/views/workitems.py nx_lib/workitem_sources.py && ruff format nx_lib/views/workitems.py nx_lib/workitem_sources.py
```

- [ ] **Step:** Run the unit + workitems integration suites:
```
python -m pytest tests/unit/ tests/integration/test_workitems_routes.py --tb=short 2>&1 | tail -50
```

- [ ] **Step:** Commit:
```
git add nx_lib/views/workitems.py nx_lib/workitem_sources.py tests/unit/test_workitems_pid_filter.py tests/unit/test_workitem_sources.py
git commit -m "$(cat <<'EOF'
refactor(workitems): remove the transient pidImport overlay machinery

Tear down the session-overlay model now superseded by the persistent register:
delete the ?pidImport= read-back block, pid_import_active / _pid_import_meta, the
row-merge-onto-real-rows + page-1-only synthetic-row append in
_get_workitems_data, the export_workitems_csv synthetic guard, the
WorkitemFilter.pid_import_active field (last defaulted field, so positional
construction is unaffected), and the SqlServerSource.list_workitems
short-circuit (all verified to exist solely for this feature). The default
single-source workitems path is byte-identical to its pre-overlay state. Dead
overlay unit tests removed; resolve_ms02_pid_to_wids / resolve_ms02_pid_ids
tests retained (the register page uses the former for live Octo status).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Relink the workitems-page button; remove banner, import columns, and `pid_processes`/`_ms02_pid_processes`

**Files:**
- Modify: `templates/workitems_overview.html`
- Modify: `templates/js/_workitems_overview_js.html`
- Modify: `nx_lib/views/workitems.py` (`workitems_overview`, delete `_ms02_pid_processes`)
- Test: `tests/integration/test_workitems_routes.py` (update `test_prepared_audit_wrap_renders_without_pid_processes`)

**Interfaces:**
- The workitems toolbar shows a **link** to `/prepared_documents` (guarded by `prepared_import_perm AND ms02_active`). All import-column / banner / synthetic-row client machinery removed; the table reverts to its pre-overlay 7-column shape.

- [ ] **Step:** Update the integration test. Find `def test_prepared_audit_wrap_renders_without_pid_processes(` and replace the whole function with one that asserts the relinked control renders and the retired banner/upload widget do not:
```python
def test_prepared_audit_link_renders_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    """The workitems toolbar shows a link to the register page when
    perm + ms02_active (independent of any process filter); the old upload/banner
    machinery is gone. The in-body perm uses the wv-local has_permission."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    resp = user_client.get("/workitems")
    assert resp.status_code == 200
    assert b"prepared-docs-link" in resp.data
    assert b"/prepared_documents" in resp.data
    assert b"bg-emerald-50" not in resp.data
```

- [ ] **Step:** Run it red:
```
python -m pytest tests/integration/test_workitems_routes.py -k prepared_audit_link -v
```

- [ ] **Step:** Relink the button. In `templates/workitems_overview.html`, find:
```html
          {% if prepared_import_perm and ms02_active %}
          <div class="inline-block hidden" id="preparedAuditWrap">
            <input type="file" id="preparedAuditFile" name="preparedAuditFile"
              class="hidden" accept=".xlsx" data-testid="workitems-prepared-audit-file">
            <button type="button" id="preparedAuditBtn"
              class="nx-btn nx-btn--secondary" data-testid="workitems-prepared-audit">
              <i class="fas fa-file-excel mr-2"></i>{{ _("Prepared documents") }}
            </button>
          </div>
          {% endif %}
```
Replace with:
```html
          {% if prepared_import_perm and ms02_active %}
          <a href="{{ url_for('prepared_documents') }}"
            class="nx-btn nx-btn--secondary" data-testid="prepared-docs-link">
            <i class="fas fa-file-excel mr-2"></i>{{ _("Prepared documents") }}
          </a>
          {% endif %}
```

- [ ] **Step:** Delete the synthetic-row banner block. Find and remove entirely:
```html
      {% if prepared_import_perm and ms02_active %}
      <div id="preparedAuditBanner"
        class="hidden mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        <span id="preparedAuditBannerText"></span>
        <button type="button" id="preparedAuditBannerClear"
          class="ml-3 underline">{{ _("Clear") }}</button>
      </div>
      {% endif %}
```

- [ ] **Step:** Remove the import-col CSS toggle and revert the table class. Find:
```html
          <style>
            #workitemsTable.no-import-cols .import-col { display: none !important; }
          </style>
          <table class="nx-table no-import-cols" id="workitemsTable">
```
Replace with:
```html
          <table class="nx-table" id="workitemsTable">
```

- [ ] **Step:** Delete the four `import-col` header cells. Find and remove the four consecutive `<th>` blocks:
```html
                <th scope="col" class="import-col px-6 py-3 text-center whitespace-nowrap">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Collected") }}</span>
                </th>
                <th scope="col" class="import-col px-6 py-3 text-center whitespace-nowrap">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Collected by") }}</span>
                </th>
                <th scope="col" class="import-col px-6 py-3 text-center whitespace-nowrap">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Prepared") }}</span>
                </th>
                <th scope="col" class="import-col px-6 py-3 text-center whitespace-nowrap">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Prepared by") }}</span>
                </th>
```
(The spinner-row `colspan="7"` stays — the baseline table has 7 visible columns: checkbox, Workitem, Status, Last movement at, Priority, Tag, Details. The import-col `<th>`s were extras that did not change the spinner colspan.)

- [ ] **Step:** Remove the retired client machinery in `templates/js/_workitems_overview_js.html`. To avoid undercounting the cells, the rule is **grep `import-col` and remove EVERY occurrence**. Confirm first:
```
grep -n "import-col\|activePidToken\|setImportColsVisible\|uploadPreparedAudit\|preparedAuditWrap\|preparedAuditBanner\|bool2icon\|str2cell\|pidImport\|workitem.synthetic" templates/js/_workitems_overview_js.html
```
Then make these edits:
  - Delete the `const preparedWrap = document.getElementById('preparedAuditWrap'); if (preparedWrap) { preparedWrap.classList.remove('hidden'); }` block.
  - Delete the `preparedAuditBtn`/`preparedAuditFile` change→`uploadPreparedAudit(...)` wiring and the `preparedAuditBannerClear` handler (the whole listener blocks).
  - Delete the entire `async function uploadPreparedAudit(file) { ... }` function (through its closing brace).
  - Delete `let activePidToken = null;` and the `function setImportColsVisible(visible) { ... }` function.
  - In `renderTable`: delete the `setImportColsVisible(activePidToken !== null);` call; the `if (workitem.synthetic) { ... }` synthetic-row branch (through its closing brace, including its FOUR `import-col` `<td>` cells); ALL `import-col` `<td>` cells in the real-row template (there are EIGHT: four content cells `${bool2icon(...)}` / `${str2cell(...)}` AND four trailing empty `<td class="import-col"></td>` — remove all eight); and revert both `colspan="${activePidToken ? 11 : 7}"` and `const emptyColspan = activePidToken ? 11 : 7;` to the fixed `7`.
  - In `fetchAndUpdateWorkitems`: delete `if (activePidToken) fetchParams.set('pidImport', activePidToken);`.
  - If `bool2icon`/`str2cell` (declared inside `renderTable`) now have no remaining caller, remove their declarations too. Re-grep to confirm zero `import-col`, `activePidToken`, `setImportColsVisible`, `uploadPreparedAudit`, `pidImport`, `workitem.synthetic` remain.

- [ ] **Step:** Remove the `pid_processes` plumbing in `workitems_overview`. Find and delete:
```python
        pid_processes = (
            _ms02_pid_processes(allowed_processes) if prepared_import_perm and ms02_active else []
        )
```
(plus its preceding comment lines if present). Then find and remove the render kwarg `pid_processes=pid_processes,` so the `render_template(..., ms02_active=ms02_active, ...)` call no longer passes it.

- [ ] **Step:** Delete the now-dead `_ms02_pid_processes` function. Confirm no other reference first:
```
grep -rn "_ms02_pid_processes" nx_lib/ tests/
```
Then find `def _ms02_pid_processes(target_processes):` and delete the whole function (through its `finally:` / `conn.close()` block).

- [ ] **Step:** Restart the dev server (template cache), run the test green, and browser-verify (remote → screenshot the workitems toolbar link + unchanged 7-column table, SendUserFile):
```
nx -u
python -m pytest tests/integration/test_workitems_routes.py -k "prepared_audit_link or import_prepared_audit" -v
```

- [ ] **Step:** ruff + commit:
```
ruff check nx_lib/views/workitems.py && ruff format nx_lib/views/workitems.py
git add templates/workitems_overview.html templates/js/_workitems_overview_js.html nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -m "$(cat <<'EOF'
refactor(workitems): replace prepared-import button with register page link

The workitems toolbar 'Prepared documents' control becomes a link to
/prepared_documents (same prepared_import_perm AND ms02_active guard). Remove the
retired client machinery: the #preparedAuditBanner block, ALL import-column
<th>/<td> cells (8 in the real-row template incl. the 4 trailing empties, plus
the 4 in the synthetic-row branch) and the no-import-cols CSS toggle, the
uploadPreparedAudit / setImportColsVisible / activePidToken / synthetic-row JS
(colspan reverts to 7), and the pidImport query-param injection. Drop the
server-side pid_processes plumbing and delete the now-dead _ms02_pid_processes
helper (its only caller was workitems_overview).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 5 — Page registration, i18n, docs

### Task 8: Register the page in `page_visibility()`

**Files:**
- Modify: `nx_lib/security.py` (`page_visibility`)

**Interfaces:**
- Produces: `pageV["preparedDocsPagePerm"]` boolean (consumed by `_header.html` via the route's `pageV=page_visibility()`).

- [ ] **Step:** In `nx_lib/security.py`, find inside `page_visibility()`:
```python
        "workitemsPagePerm": has_permission("workitems.view"),
        "invoicesPagePerm": has_permission("invoices.view"),
```
Insert after the `workitemsPagePerm` line:
```python
        "preparedDocsPagePerm": has_permission("workitems.import.preparedaudit"),
```

- [ ] **Step:** Do NOT add `preparedDocsPagePerm` to `startpage_redirect_to` (the page is reached from the workitems toolbar link, not a landing page; and it is MS02-only). Run ruff + the full suite:
```
ruff check nx_lib/security.py && ruff format nx_lib/security.py
python -m pytest tests/ --tb=short 2>&1 | tail -30
```

- [ ] **Step:** Commit:
```
git add nx_lib/security.py
git commit -m "$(cat <<'EOF'
feat(security): register prepared-documents page in page_visibility()

Add preparedDocsPagePerm (reusing the existing workitems.import.preparedaudit
permission, no new permission) so the page's _header.html include has the perm
in pageV. Not added to startpage_redirect_to (MS02-only; reached from the
workitems toolbar link, not a landing page).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: i18n — extract, translate de/fr/it, compile

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

**Interfaces:**
- Produces: all new msgids non-fuzzy translated in de/fr/it; `messages.pot` in sync.

- [ ] **Step:** Run the extract→update cycle (or invoke `/nx-i18n`):
```
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step:** Translate every NEW msgid **non-fuzzy** in `translations/de/`, `translations/fr/`, `translations/it/` `messages.po` (reuse the already-translated `Prepared documents`, `Clear`, `Total`, `Previous`, `Next` where they already exist — do not create near-duplicates). New strings introduced by this feature:
  - `Prepared Documents`, `Intake register of collected and prepared documents`
  - `PID`, `Collected`, `Collected by`, `Prepared`, `Prepared by`, `Octo status`
  - `In Octo`, `Upload Excel`, `Clear list`
  - `No prepared documents yet. Upload an Excel to get started.`
  - `Imported %(total)s rows (%(new)s new, %(updated)s updated).` (single parameterized msgid — do NOT split into word fragments)
  - `Upload failed.`, `Clear the entire prepared-documents list? This cannot be undone.`
  - `Prepared-documents list cleared.`, `Could not clear the list.`
  - Route flashes: `Could not save the prepared documents. Please try again.`, `Could not clear the prepared documents. Please try again.`, `This import is only available for the MS02 client.` (the last already exists from `import_prepared_audit` — reuse), `This page is only available for the MS02 client.`
  - Remove the `fuzzy` flag the updater may have added to any of these.

- [ ] **Step:** Compile + verify the translation test passes:
```
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v 2>&1 | tail -20
```

- [ ] **Step:** Commit:
```
git add messages.pot translations/
git commit -m "$(cat <<'EOF'
i18n(prepared-docs): translate register page strings for de/fr/it

Extract + translate the new register page strings (title, subtitle, column
headers, Octo status, upload/clear controls, confirm dialog, the single
parameterized import-summary msgid, empty-state, and route error/flash
messages) non-fuzzy for de, fr, it. messages.pot regenerated; catalogs
recompiled; test_translations stays green.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Update CHANGELOG and CLAUDE.md

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

**Interfaces:** docs only.

- [ ] **Step:** First locate the existing overlay bullets so you edit in place rather than adding contradictory entries. Read the `[Unreleased]` section:
```
grep -n "prepared\|pidImport\|synthetic\|5-col\|five-column" CHANGELOG.md
```
Read the matching lines under `## [Unreleased]`, then in the same section: (1) rewrite/fold any existing bullet that claims the workitems-list overlay / 5-column / synthetic-row behaviour so it no longer describes shipped reality; (2) update any "Changed: Prepared documents upload button" bullet to describe the toolbar link. Then add (merging into the existing `### Added`/`### Changed`/`### Removed` subsections, not duplicating headers):
```markdown
### Added
- **MS02 "Prepared Documents" standalone register.** The MS02 prepared-documents
  Excel intake now persists in its own DB-backed register on a dedicated page
  (`GET /prepared_documents`) instead of a transient session filter over the
  workitems list. Accumulating, upsert-by-PID (one row per personal number;
  re-uploading a PID updates its row), shared across all MS02 users (`UploadedBy`
  is an audit stamp, not a visibility scope), read-only with a clear-whole-list
  action for v1. Columns: PID, Collected, Collected by, Prepared, Prepared by,
  plus a live (non-stored) Octo cross-reference status ("In Octo" + open-workitem
  link when the PID resolves through the MS02 doc-field index, dash otherwise).
  Real DB pagination (OFFSET/FETCH). Backed by new table `dbo.PreparedDocuments`
  (migration `0031`). Gated by the existing `workitems.import.preparedaudit`
  permission AND `ms02_active` (no new permission).

### Changed
- The MS02 prepared-documents upload on the workitems page now links to the new
  Prepared Documents register page instead of running a transient
  `?pidImport=<token>` overlay over the list.

### Removed
- The MS02 prepared-documents session-overlay model: the `pid_import:<token>`
  session stash, the `?pidImport=` read-back path (`pid_import_active` /
  `_pid_import_meta`), the row-merge + page-1-only synthetic-row append in
  `_get_workitems_data`, the CSV synthetic guard, and the
  `WorkitemFilter.pid_import_active` field with the `SqlServerSource`
  short-circuit. Superseded by the persistent `dbo.PreparedDocuments` register.
```

- [ ] **Step:** Update the MS02 paragraph in `CLAUDE.md`. Find the sentence span beginning:
```
the `/import_prepared_audit` route turn an uploaded five-column Excel
```
and ending at:
```
Gated by `workitems.import.preparedaudit` (migration `0029`).
```
Replace that whole span with:
```
the `/import_prepared_audit` route upserts an uploaded five-column Excel (PID/Collected/CollectedBy/Prepared/PreparedBy — duplicate 'PreparedBy' header tolerated via positional first-wins) by PID into the persistent register `dbo.PreparedDocuments` (migration `0031`): one row per personal number, accumulating, shared across MS02 users, read-only + clear-whole-list (v1). The register is viewed on the standalone `/prepared_documents` page (route in `nx_lib/views/workitems.py`; data access in `nx_lib/prepared_documents.py`; templates `prepared_documents.html` + paired `templates/js/_prepared_documents_js.html`) with real OFFSET/FETCH pagination and a live (non-stored) Octo cross-reference status column computed per page via `resolve_ms02_pid_to_wids`. The workitems-page button is now a link to that page. Gated by `workitems.import.preparedaudit` (migration `0029`, reused) AND `ms02_active`; registered in `page_visibility()` as `preparedDocsPagePerm`. The earlier transient session-overlay (`?pidImport=<token>` filter with row-merge + synthetic rows) has been removed.
```

- [ ] **Step:** Commit:
```
git add CHANGELOG.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(prepared-docs): document the standalone register; retire overlay notes

Update CHANGELOG [Unreleased] (Added: standalone register page + dbo.Prepared
Documents migration 0031; Changed: workitems button now links to the page;
Removed: the pidImport session-overlay) and revise the predecessor overlay
bullets so the changelog reflects shipped reality. Rewrite the CLAUDE.md MS02
paragraph to describe the persistent upsert-by-PID register, the
/prepared_documents page, the live Octo status column, OFFSET/FETCH pagination,
and the page_visibility registration (was: session stash + synthetic rows).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 6 — Full-suite verification

### Task 11: Run the full suite and confirm the pre-push gate prerequisites

**Files:** none (verification only).

- [ ] **Step:** Reset test DB state to avoid stale `NEXORA_TEST` order-dependent failures:
```
python scripts/test_db_reset.py
```

- [ ] **Step:** Run the full unit + integration suite:
```
python -m pytest tests/unit/ tests/integration/ --tb=short 2>&1 | tail -60
```

- [ ] **Step:** ruff the whole changed surface:
```
ruff check nx_lib/ tests/ && ruff format --check nx_lib/ tests/
```

- [ ] **Step:** Restart the dev server and do a final browser pass as an MS02 user (remote: screenshot upload → summary → rows persist → reload → re-upload same PID updates not duplicates → clear → confirm → empty, and the relinked workitems button). Save to `var/screenshots/` and SendUserFile:
```
nx -u -b --loginas:<ms02_user>
```

- [ ] **Step:** Confirm `git status` is clean and all work is committed. Remote session: do NOT push, do NOT open a PR — stop here for the owner to review locally. If verification surfaced a fix, commit it with a focused `fix(...)` message.

---

## Gotchas & notes

- **Insert/update classification is via pre-SELECT + MERGE, NOT `OUTPUT $action`.** The repo's only proven MERGE (`_cache_store` in `workitem_sources.py`) uses neither `OUTPUT` nor a post-`fetchone()`; relying on `OUTPUT $action` + `fetchone()` against this pyodbc/SQL-Server setup is unverified and can raise "No results. Previous SQL was not a query." The `SELECT 1 … WHERE PID = ?` before each MERGE is one cheap extra read per row (imports are small) and is driver-safe. The `UQ_PreparedDocuments_PID` constraint still makes any concurrent double-insert fail loudly rather than duplicate.
- **The `if not pid_specs:` warning early-return is GONE on purpose.** Previously an unseeded PID column short-circuited the upload with a `warning`. The register must persist rows regardless; the Octo status column degrades to a dash on the page. `test_import_prepared_audit_persists_even_without_pid_specs` locks this in.
- **No live DB in CI:** every DB-touching helper is unit-tested with a mocked cursor; integration route tests monkeypatch `count_prepared_documents` / `fetch_prepared_documents_page` / `clear_prepared_documents` / `upsert_prepared_documents` on the `wv` module so they never touch a live DB. Do NOT write a test that requires a real `engineNexoraDB` round-trip in the push gate.
- **The `wv`-local `has_permission` trap:** route bodies call the `has_permission` imported INTO `workitems.py`, which `workitems_all_perms` (patches `nx_lib.security.has_permission`) does NOT reach. Any test asserting that a gated (`prepared_import_perm`) control renders MUST also `monkeypatch.setattr(wv, "has_permission", lambda code: True)`. The `@require_permission` decorator gate itself is satisfied by `workitems_all_perms` alone.
- **`ms02_active` gate placement is asymmetric on purpose:** the page raises `PermissionDenied` (403) when MS02 is absent; the clear route returns `400` with `"MS02"` (matching `import_prepared_audit`). Asserted in the route tests.
- **Octo link target caveat:** the "In Octo" link points at `workitems_overview?search=<wid>`. The list maps `?search=` to `search_id` only if the user holds `workitems.filter.workitemid`, and the match is a `twi.id LIKE %wid%` SUBSTRING match (so wid=42 also matches 423, 1142, …). This is acceptable for a soft cross-reference: the link silently no-ops without the filter perm and is fuzzy when it works; the dash path covers resolver `None`/`{}`/missing PIDs. Do not treat it as an exact deep-link.
- **`resolve_ms02_pid_to_wids` import must stay** in `workitems.py` — it loses its old caller in Task 3 but gains the page-route caller in Task 4; commit Phase 2+3 only after Task 4 so ruff is clean.
- **`secrets` import** in `workitems.py` may go unused after Task 3 (it backed the session token). Grep `secrets\.` before removing the import; only drop it if there are no other callers.
- **Template cache:** restart `nx -u` after EVERY template/JS-partial edit (Tasks 5, 7) before any browser/e2e check, or you will see stale HTML.
- **Template skeleton must match a sibling page.** Reconcile the `<head>` asset hrefs and `nx-*` class names in `prepared_documents.html` against `workitems_overview.html` (read its first ~40 lines) rather than the illustrative skeleton — the exact stylesheet href / class set in this repo may differ.
- **Baseline workitems colspan is 7.** The spinner/empty rows in both `workitems_overview.html` and the renderTable JS revert to `colspan="7"` (checkbox, Workitem, Status, Last movement at, Priority, Tag, Details). The 4 import-col `<th>`/`<td>` were extras hidden by `no-import-cols`; removing them does not change the 7.
- **Delete import-col cells by grep, not by counting.** `renderTable` has EIGHT real-row `import-col` `<td>` (four content + four trailing empty) plus FOUR in the synthetic branch, and `workitems_overview.html` has FOUR `import-col` `<th>`. Re-grep `import-col` after editing each file to confirm zero remain.
- **CRLF / SQL hook:** the only SQL change is migration `0031` (Task 1). If `sql-migrate-int` fails on known INT CRLF checksum drift (0001–0003), commit with `SQL_SYNC_SKIP=1`. Never `--no-verify`; never skip a real SQL error. Do NOT hand-edit the auto-generated `sql/NexoraDB/Tables/dbo.PreparedDocuments.sql` dump.
- **`pageV=page_visibility()` (not `**page_visibility()`).** Pass the visibility map as a single `pageV` kwarg (matching `workitems_overview`) to avoid kwarg-collision surprises with the explicit `prepared_import_perm`/`ms02_active` kwargs.
- **Commit order matters for the per-commit test hook.** Each task's edits are self-consistent (tests green) at commit time. Task 3 (route upsert) + Task 4 (page route) land together so the route never references both old and new paths and ruff stays clean; the overlay teardown (Task 6) follows. The overlay read-back in `_get_workitems_data` is independent of `import_prepared_audit` and is safe to leave in place until Task 6.
- **Deploy:** no `deploy.yml` change — route in an existing file, two templates under `templates/` (mirrored), the new module under `nx_lib/` (mirrored), migration auto-applied by the deploy pipeline.
