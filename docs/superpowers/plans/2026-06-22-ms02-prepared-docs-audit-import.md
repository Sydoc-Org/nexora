# MS02 Prepared-Documents Excel Import + Audit Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an **MS02-only** Excel-upload control to the workitems list. The spreadsheet has exactly two columns — `PID` (a *personal number*, a person identifier) and `Prepared` (boolean-ish, informational only). For each PID we resolve to its MS02 workitem(s) **through the existing MS02 doc-field EAV index** (`engine_ms02_docfields_pg`) — because a PID is an extracted/indexed document field, NOT a workitem id and NOT a process id — and we display those workitems in the merged list so the user can open each row and read **the full Octo audit the document went through**. The `Prepared` column is surfaced for information only: there is **no** reconcile/verify logic against the audit.

**Architecture:** This stacks directly on the just-shipped MS02 doc-field machinery. The MS02 multi-source seam (`WorkitemFilter.ms02_docfield_ids` → `PostgresSource._build_where` → `twi."ID" = ANY(%s)`) is **already built and untouched** by this feature. We add: (1) a **sibling resolver** `resolve_ms02_pid_ids(engine, eav_names, pid_values)` in `nx_lib/workitem_sources.py` that does `"Name" IN (...) AND "StringValue" = ANY(%s)` — the personal-number EAV field(s), MANY exact PIDs, OR-ed (the *opposite* shape to `resolve_ms02_docfield_ids`, which ANDs across fields with ONE `LIKE` value each, so we do **not** overload it); (2) a pure Excel parser `parse_prepared_xlsx(data) -> (pairs, error)` (openpyxl, already a dependency) with a row cap; (3) a new `@require_permission`-guarded POST route `import_prepared_audit()` that validates the upload (`secure_filename` + libmagic MIME sniff + CSRF), parses it, resolves PIDs → MS02 workitem ids, stashes the resolved id-set in the server session under a short token, and returns `{token, prepared, matched, total}` JSON; (4) the orchestrator `_get_workitems_data` accepts a new optional `pidImport` token param, reads the resolved id-set back out of the session, and **intersects** it into `ms02_docfield_ids` before building `WorkitemFilter` (PostgresSource-only — never touches `SqlServerSource`); (5) an MS02-gated upload control on `workitems_overview.html` + its handler in `_workitems_overview_js.html` that POSTs the file then re-queries `api/workitems?pidImport=<token>`. The default single-source path stays **byte-identical**. The audit is **already rendered** today (`loadHistory` → `/api/get_audithistory/<id>`, gated `workitems.details.view.audit`, client-routed via `get_domain_for_workitem`) — so "show the full audit" is REUSE, not new audit UI.

**Tech Stack:** Python 3, Flask, SQLAlchemy 2.0 + pyodbc (SQL Server) + psycopg2-binary (Postgres, already a dependency), openpyxl 3.1.5 (already in `requirements.txt`), python-magic-bin (`magic`, already used by `nx_lib/files.py`), Flask-WTF CSRF, Flask-Session (server-side filesystem session, already active), Flask-Babel i18n, pytest (unit + integration).

**Design spec:** No spec exists for THIS feature — do not author one. It stacks on `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` (the MS02 multi-source + doc-field architecture); §4.6 (doc-field search) gets a one-sentence touch noting the same EAV index now also backs PID-list import.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63` (NOT `main`). This work STACKS on ~25 unpushed MS02 multi-source commits + the `0027`/`0028` doc-field work already on this branch. Do NOT branch off `main`; commit onto `feature/2.5.63`.
- **Remote session = commit only.** Commits are allowed on this feature branch, but **do not push and do not open a PR** — the owner does that after local review. The last step of every task stops at `git commit`.
- **Anchor on snippets, never line numbers.** Every "find X" step quotes the exact code to locate; line numbers are reading aids and will drift (the MS02 branch keeps moving).
- **Migrations needed: YES.** One new file `sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql` (new file) — verified next free number: the directory currently tops out at `0028_rename_ms02_process_to_05_pdbs.sql`. **Re-list `sql/_migrations/NexoraDB/` at execution to confirm `0029` is still free** and bump if the underlying MS02 branch added more. It seeds ONE permission row (no table/column DDL).
- **Pre-commit hook escape hatch:** the `sql-migrate-int` hook auto-applies the migration to INT. On Windows it can flake on stale CRLF checksums for migrations `0001`–`0003` (known INT drift). If it fails on checksum drift (not a real SQL error), commit with `SQL_SYNC_SKIP=1 git commit ...`. **NEVER `--no-verify`.** Make the migration idempotent (`NOT EXISTS` guards) so the hook can re-apply safely.
- **Template-cache restart REQUIRED.** Jinja templates are cached process-lifetime. After editing `workitems_overview.html` / `_workitems_overview_js.html`, **restart the dev server** (`nx -u`) or browser/e2e tests see stale HTML.
- **i18n needed: YES.** New user-facing strings (button label, flash/error messages, result banner). Wrap with `{{ _('...') }}` in templates / `_('...')` in Python, then run the full pybabel cycle (the `/nx-i18n` skill). `test_translations.py` enforces `messages.pot` is in sync and every msgid is non-fuzzy in de/fr/it — the cycle is mandatory or the pre-push gate fails.
- **TEST / CI has NO MS02 engines and NO Statistics DB.** `engine_ms02_docfields_pg` and `engine_ms02_pg` are `None`; `CLIENTS` has no `'ms02'` entry. Every new test must tolerate `engine is None` / empty allow-set: the PID resolver returns `None` (no constraint) on `engine is None` and never raises; the route degrades gracefully (control not offered / 403 / MS02-only 400) without 500-ing the page. The integration harness already tolerates `(200, 500)` for workitems API routes because engines can legitimately be absent — follow that pattern.
- **Test fixtures (verified live in `tests/conftest.py`):** the `app` fixture (line 30) is available to **unit** tests (existing `tests/unit/test_workitem_sources.py` uses `app.app_context()` throughout); `client` (anonymous, line 64), `user_client` (logged-in, line 144) and `noperm_client` (logged-in, dashboard-only, line 150) are the integration fixtures. The `workitems_all_perms` fixture is **local to `tests/integration/test_workitems_routes.py`** (line 39) and is **`monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)`** — it grants ALL permissions unconditionally and does **NOT** read `sql/test/seed.sql`. Do **NOT** claim a seed.sql edit is what makes the integration test pass; the monkeypatch is. (See Finding F1.)
- **The default single-source path must stay byte-identical.** `docfield_ids` (StatisticsDB-resolved, SQL-Server-only), the `SqlServerSource` branch, and existing SearchConfig rows must not change. The PID allow-set funnels ONLY into `ms02_docfield_ids` (PostgresSource).
- **No new dependency** (openpyxl + magic + psycopg2-binary already present). **No new top-level file/dir** — everything lives in already-tracked/mirrored dirs (`nx_lib/`, `templates/`, `sql/`, `tests/`, `docs/`, `translations/`), so `deploy.yml` `/XF`/`/XD` needs **no change**. The uploaded `.xlsx` (which contains personal numbers) is parsed in-request and **never written to disk**; only the resolved integer id-set is kept, in the server session under a short token.
- **Sequencing / in-flight MS02 work:** migration `0027` (`SearchConfig.ClientCode`) is applied to INT and in place. Migration `0028` renamed the MS02 Octo process from `praesidialdepartement_bs` to `05_PDBS` — so the live process key is **`sydoc.05_PDBS`** and the process permission is **`workitems.filter.process.sydoc.05_PDBS`**. **Do NOT copy the stale `sydoc.praesidialdepartement_bs` key** that appears in older `0025`/`0026`/`0027` text. The personal-number EAV `"Name"` is **owner-seeded** in a `'ms02'` `SearchConfig` row (`col_<field>` = the EAV Name) — see Owner actions; until it is seeded, PID resolution finds nothing and the import lists nothing (graceful, not an error). The route reads the process key **the same dynamic way the orchestrator does** — from `target_processes` derived from `workitems.filter.process.*` perms, bound as `ProcessName IN (...)` — NOT a hardcoded literal (Finding F5).

---

## Decisions locked in

| # | Decision | Detail |
|---|---|---|
| 1 | **New SIBLING resolver, do NOT overload `resolve_ms02_docfield_ids`.** | A PID import is the personal-number EAV `"Name"`(s) matched against MANY exact PID values, OR-ed. The existing resolver ANDs across fields with ONE `LIKE` value each — forcing PIDs through it returns the empty set. Add `resolve_ms02_pid_ids(engine, eav_names, pid_values) -> set \| None` doing `"Name" IN (...) AND "StringValue" = ANY(%s)`, reusing the `_MS02_DOCFIELD_*` constants and the same three-way `None`/`set()`/populated contract + never-raises style. The existing search resolver stays byte-identical. |
| 2 | **EXACT match (`= ANY(%s)`), not `LIKE`.** | PIDs are precise identifiers, not substrings (the search box uses `LIKE %value%`; PID import does not). Owner confirms there is no zero-padding/format mismatch between the Excel `PID` column and the indexed `"StringValue"` (Owner action). |
| 3 | **Reuse the existing `ms02_docfield_ids` → `ANY(%s)` seam.** | `PostgresSource._build_where` already consumes `filt.ms02_docfield_ids`. The orchestrator intersects the PID allow-set into `ms02_docfield_ids` before building `WorkitemFilter`. No change to `PostgresSource` or to `WorkitemFilter.ms02_docfield_ids`. |
| 4 | **The PID allow-set is stashed in the server session under a token, NOT serialized into the URL.** | The upload route resolves PIDs in-request, stores the resolved integer id-set in `session` under a short random token, and returns `{token, ...}` JSON; the JS re-queries `api/workitems?pidImport=<token>`. `_get_workitems_data` reads the token, pulls the id-set from the session, and intersects it into `ms02_docfield_ids`. This avoids a multi-kilobyte `?pidWorkitemId=...&pidWorkitemId=...` query string (one PID → many workitems → potentially hundreds of ids) blowing past URL limits and polluting the address bar (Findings F2, F7). The spreadsheet (personal numbers, sensitive) is never written to disk. |
| 5 | **MS02-only gate everywhere.** | Control shown only when `'ms02' in CLIENTS and engine_ms02_docfields_pg is not None` AND the user holds the new permission. Route returns a 400 JSON `{"error": ...}` when `engine_ms02_docfields_pg is None` OR `'ms02' not in CLIENTS`. In CI (no MS02 engine) the control simply isn't offered and the route hits the MS02-only gate. |
| 6 | **"Show the full audit" = REUSE.** | The audit is already fetched AND rendered today: `loadHistory(workitemId)` (JS) → `/api/get_audithistory/<id>` (gated `workitems.details.view.audit`), client-routed via `get_domain_for_workitem` (so MS02 audits load through the per-client Octo domain). The feature does ZERO audit-rendering work — it only surfaces the matched MS02 workitems in the list. |
| 7 | **`Prepared` column is informational only.** | The route returns a `{pid: prepared_bool}` map and a matched/total count; there is NO reconcile against the audit. The JS surfaces a matched/total banner (and an unresolved-PID note). |
| 8 | **New permission `workitems.import.preparedaudit`.** | Grantable per-user, modelled on migration `0018`; seeded Effect `'A'` to every profile that already has `admin.view`. Guard the route with `@require_permission`; pass `prepared_import_perm = has_permission(...)` to the template (a per-control perm — NOT a `page_visibility()` entry, mirroring `workitems.import.workitem` which is also enforced via `@require_permission` only — Finding F8). |
| 9 | **Default source suppressed during a PID import.** | A PID import should show ONLY the matched MS02 workitems. Add a `pid_import_active: bool = False` flag to `WorkitemFilter` (after `ms02_docfield_ids`) that `SqlServerSource.list_workitems` honours by returning `([], 0)` as its literal first statement (before any `where_clauses` build or `raw_connection()`). Confirmed `list_workitems` returns a `(rows, total)` 2-tuple that callers unpack (Finding F4). |

---

## Owner actions (build-time confirmations — do NOT fabricate)

These are owner-provided and must be supplied before the import resolves anything. Until they are, the engine stays `None` / the mapping is absent and the import lists nothing (the page still renders).

1. **The personal-number EAV `"Name"`** in the MS02 doc-field index (`engine_ms02_docfields_pg`, table `t_DocumentIndexes`, column `"Name"`). What string is the PID/personal-number indexed under? (e.g. is it literally `"PersonalNumber"` / `"PID"` / something else?) This MUST be seeded as a `'ms02'` `SearchConfig` row's `col_<field>` value (same mechanism `0027` uses, e.g. `col_docbarcode='Barcode'`), with `ClientCode='ms02'` and `ProcessName='sydoc.05_PDBS'`. The plan reads this `col_<field>` value from `SearchConfig` at runtime (whitelisted column, never user input) — it is **never hard-coded**. **Decision:** the field key is `col_pid` (i.e. the owner seeds `col_pid = '<EAV Name>'`); the route whitelists `col_pid` via the existing `get_valid_search_columns()` guard. *(If the owner prefers a different `col_<field>` name, change the single `_MS02_PID_SEARCH_FIELD` constant — Task 6 — to match.)*
2. **`MS02_DOCFIELDS_DB_NAME`** set in `env/INT.env` + `env/PROD.env` (existing standing MS02 obligation — the engine is `None` until set).
3. **PID format alignment.** Confirm the Excel `PID` column values match the indexed `"StringValue"` byte-for-byte (no zero-padding loss, no leading apostrophes, no float coercion of integer-looking PIDs by Excel). If Excel stores them as numbers, the parser must stringify without a trailing `.0` (the parser handles this; owner confirms expected format). If PIDs are zero-padded strings, the Excel column must be text-formatted.
4. **One PID → MANY workitems is expected and desired.** A person's documents accumulate over time; the import shows ALL workitems for every PID (the list already de-dups to the latest activity *per workitem id*, not per person). Confirm this is the intended UX (vs. latest-per-PID).
5. **MS02-only result during a PID import.** When a PID import is active the plan suppresses the default (SQL Server) source so the list shows ONLY the matched MS02 workitems (Decision #9). Confirm acceptable (vs. also showing default-client rows).
6. **PROD ops:** `psycopg2-binary` already on the prod interpreter; `MS02_DOCFIELDS_DB_*` in `env/PROD.env`; migration `0029` auto-applies via deploy; grant `workitems.import.preparedaudit` to the relevant MS02 operator profile(s) (the `0018`-style seed gives it to `admin.view` profiles out of the box).
7. **PROD libmagic MIME for `.xlsx`.** Confirm the value the SYAPP01 prod libmagic emits for a real `.xlsx` (the plan whitelists `office-openxml` + `application/zip` + `application/octet-stream`; widen if prod emits something else).

---

# PHASE 1 — Excel parser (pure, no engine)

### Task 1: `parse_prepared_xlsx` pure helper

**Files:**
- Modify: `nx_lib/workitem_sources.py` (add the parser near the other pure helpers, after `resolve_ms02_docfield_ids`)
- Test: `tests/unit/test_prepared_xlsx_parser.py` (new file)

**Interfaces:**
- Produces: `parse_prepared_xlsx(data: bytes) -> tuple[list[tuple[str, bool]], str | None]` — returns `(pairs, error)` where `pairs` is `[(pid_str, prepared_bool), ...]` deduped on PID (first wins), blanks skipped, capped at `_PREPARED_MAX_ROWS`; `error` is `None` on success or a short message on a malformed/empty/missing-column workbook. **Never raises** into the request.
- Header detection: case-insensitive match of a `PID` column and a `Prepared` column in row 1; tolerates extra columns and surrounding whitespace.
- `Prepared` truthiness: `True`/`true`/`1`/`yes`/`y`/`ja`/`x`/`wahr` → `True`; everything else (incl. blank) → `False`.
- Row cap: stop after `_PREPARED_MAX_ROWS` (10000) data rows — bounds memory/URL for a malicious or oversized workbook (Finding F7).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_prepared_xlsx_parser.py
"""Pure parser for the MS02 'prepared documents' Excel (PID + Prepared)."""

import io

import openpyxl

import nx_lib.workitem_sources as ws


def _xlsx(rows, headers=("PID", "Prepared")):
    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(list(headers))
    for r in rows:
        sh.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parses_pid_and_prepared():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([("100", True), ("200", False)]))
    assert err is None
    assert pairs == [("100", True), ("200", False)]


def test_header_detection_is_case_insensitive_and_order_agnostic():
    data = _xlsx([(True, "  300 ")], headers=("prepared", "pid"))
    pairs, err = ws.parse_prepared_xlsx(data)
    assert err is None
    assert pairs == [("300", True)]  # trimmed; column order swapped


def test_integer_pid_does_not_get_trailing_dot_zero():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([(12345, "yes")]))
    assert err is None
    assert pairs == [("12345", True)]


def test_blank_rows_and_blank_pids_skipped():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([(None, True), ("", False), ("400", "")]))
    assert err is None
    assert pairs == [("400", False)]


def test_duplicate_pid_first_wins():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([("500", True), ("500", False)]))
    assert pairs == [("500", True)]


def test_row_cap_is_enforced():
    rows = [(str(i), True) for i in range(ws._PREPARED_MAX_ROWS + 50)]
    pairs, err = ws.parse_prepared_xlsx(_xlsx(rows))
    assert err is None
    assert len(pairs) == ws._PREPARED_MAX_ROWS


def test_missing_pid_column_returns_error():
    pairs, err = ws.parse_prepared_xlsx(_xlsx([("x",)], headers=("Foo", "Prepared")))
    assert pairs == []
    assert err is not None


def test_garbage_bytes_returns_error_not_raise():
    pairs, err = ws.parse_prepared_xlsx(b"not a workbook")
    assert pairs == []
    assert err is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_prepared_xlsx_parser.py -v`
Expected: FAIL — `AttributeError: module 'nx_lib.workitem_sources' has no attribute 'parse_prepared_xlsx'`.

- [ ] **Step 3: Implement the parser**

In `nx_lib/workitem_sources.py`, add `import io` next to the existing `import json` (top of file), and add this helper right after `resolve_ms02_docfield_ids` (find `def resolve_ms02_docfield_ids(engine, pairs):` and place it after that function's closing `finally`):

```python
_PREPARED_TRUE = {"true", "1", "yes", "y", "ja", "x", "wahr"}
_PREPARED_MAX_ROWS = 10000  # bound a malicious/oversized workbook


def _norm_pid(value):
    """Stringify a cell value as a PID without Excel's float trailing '.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_prepared_xlsx(data):
    """Parse the MS02 'prepared documents' xlsx into [(pid, prepared_bool), ...].

    Two columns by header (case-insensitive, order-agnostic): "PID" and
    "Prepared". Blanks/blank-PID rows are skipped; PIDs are deduped (first wins);
    integer-looking PIDs never gain a trailing '.0'; at most _PREPARED_MAX_ROWS
    data rows are kept. Returns (pairs, error): error is None on success or a
    short message on a malformed/empty workbook or a missing PID column. NEVER
    raises -- the route surfaces ``error`` as a flash.
    """
    import openpyxl  # local import: openpyxl is heavyish and only used here

    wb = None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        current_app.logger.error(f"parse_prepared_xlsx load: {e}")
        return [], "Could not read the Excel file."
    try:
        sh = wb.active
        rows = sh.iter_rows(values_only=True)
        try:
            header = next(rows)
        except StopIteration:
            return [], "The Excel file is empty."
        idx = {}
        for i, cell in enumerate(header or []):
            key = str(cell).strip().lower() if cell is not None else ""
            if key in ("pid", "prepared"):
                idx[key] = i
        if "pid" not in idx:
            return [], "Missing required 'PID' column."
        pid_i = idx["pid"]
        prep_i = idx.get("prepared")
        out = []
        seen = set()
        for row in rows:
            if len(out) >= _PREPARED_MAX_ROWS:
                break
            if row is None:
                continue
            pid = _norm_pid(row[pid_i] if pid_i < len(row) else None)
            if not pid or pid in seen:
                continue
            seen.add(pid)
            prepared = False
            if prep_i is not None and prep_i < len(row):
                raw = row[prep_i]
                if isinstance(raw, bool):
                    prepared = raw
                elif raw is not None:
                    prepared = str(raw).strip().lower() in _PREPARED_TRUE
            out.append((pid, prepared))
        return out, None
    except Exception as e:
        current_app.logger.error(f"parse_prepared_xlsx: {e}")
        return [], "Could not parse the Excel file."
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass
```

- [ ] **Step 4: Run the test green**

Run: `python -m pytest tests/unit/test_prepared_xlsx_parser.py -v`
Expected: PASS (all 8).

- [ ] **Step 5: ruff + commit**

```bash
ruff check nx_lib/workitem_sources.py tests/unit/test_prepared_xlsx_parser.py
ruff format nx_lib/workitem_sources.py tests/unit/test_prepared_xlsx_parser.py
git add nx_lib/workitem_sources.py tests/unit/test_prepared_xlsx_parser.py
git commit -F- <<'EOF'
feat(workitems): add pure parse_prepared_xlsx PID/Prepared Excel parser

Add a pure, engine-free helper that reads the MS02 'prepared documents' xlsx
(two columns: PID = personal number, Prepared = informational) into a deduped
[(pid, prepared)] list, capped at 10000 data rows. Header detection is
case-insensitive and order-agnostic; integer PIDs never gain Excel's trailing
'.0'; malformed/empty/missing-column workbooks return an error string instead of
raising into the request. Unit-tested on in-memory openpyxl workbooks (no
engine, CI-safe).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — PID → workitem-id resolver (sibling seam)

### Task 2: `resolve_ms02_pid_ids` (personal-number field(s), MANY exact PIDs, OR-ed)

**Files:**
- Modify: `nx_lib/workitem_sources.py` (add `build_ms02_pid_sql` + `resolve_ms02_pid_ids` right after `parse_prepared_xlsx`, reusing the `_MS02_DOCFIELD_*` constants)
- Test: `tests/unit/test_workitem_sources.py` (extend)

**Interfaces:**
- Produces: `build_ms02_pid_sql(eav_names) -> str` — pure; `SELECT DISTINCT "WorkItemID" FROM "t_DocumentIndexes" WHERE "Name" IN (%s,...) AND "StringValue" = ANY(%s)` using the module identifier constants (quoted, never user input) and one `%s` placeholder per EAV name. This mirrors `build_ms02_docfield_sql`'s `"Name" IN (...)` shape but pairs it with an exact `= ANY(%s)` PID list instead of a single `LIKE`.
- Produces: `resolve_ms02_pid_ids(engine, eav_names, pid_values) -> set | None`. Three-way contract (mirrors `resolve_ms02_docfield_ids`): `None` when `engine is None`, `eav_names` falsy, `pid_values` empty, or any query errors (no constraint, page still renders); `set()` when nothing matched (force zero rows); else the union id-set. **Never raises.**
- Consumed by the upload route (Task 6); flows through the existing `WorkitemFilter.ms02_docfield_ids` → `twi."ID" = ANY(%s)` seam — no `PostgresSource` change.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_workitem_sources.py` (the file already imports `MagicMock`/`patch`, `nx_lib.workitem_sources as ws`, and uses the `app` fixture from the root `tests/conftest.py`):

```python
def test_build_ms02_pid_sql_uses_quoted_identifiers_and_any():
    sql = ws.build_ms02_pid_sql(["PID"])
    assert '"WorkItemID"' in sql
    assert '"Name" IN (%s)' in sql
    assert '"StringValue" = ANY(%s)' in sql
    assert "?" not in sql           # psycopg2 markers, not pyodbc
    assert "LIKE" not in sql        # exact match, not substring


def test_resolve_ms02_pid_ids_engine_none_returns_none():
    assert ws.resolve_ms02_pid_ids(None, ["PID"], ["1", "2"]) is None


def test_resolve_ms02_pid_ids_no_names_returns_none(app):
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(MagicMock(), [], ["1"]) is None


def test_resolve_ms02_pid_ids_empty_values_returns_none(app):
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(MagicMock(), ["PID"], []) is None


def test_resolve_ms02_pid_ids_unions_matches(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.return_value = [(10,), (20,), (30,)]
    with app.app_context():
        result = ws.resolve_ms02_pid_ids(engine, ["PID"], ["100", "200"])
    assert result == {10, 20, 30}
    # params: the name(s) first, then the list of PIDs bound to ANY(%s)
    args = cur.execute.call_args[0]
    assert args[1][0] == "PID"
    assert sorted(args[1][1]) == ["100", "200"]


def test_resolve_ms02_pid_ids_no_match_returns_empty_set(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.return_value = []
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(engine, ["PID"], ["nope"]) == set()


def test_resolve_ms02_pid_ids_query_error_returns_none(app):
    engine = MagicMock()
    engine.raw_connection.side_effect = Exception("boom")
    with app.app_context():
        assert ws.resolve_ms02_pid_ids(engine, ["PID"], ["1"]) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/unit/test_workitem_sources.py -v -k "ms02_pid or build_ms02_pid"`
Expected: FAIL — the helpers do not exist.

- [ ] **Step 3: Implement the resolver**

In `nx_lib/workitem_sources.py`, add right after `parse_prepared_xlsx`. Reuse the existing `_pgmarks` helper if present (the file defines `_pgmarks(seq)` immediately after `resolve_ms02_docfield_ids`); the snippet below builds the `IN (...)` placeholders inline so it does not depend on a particular helper name — **verify `_pgmarks` exists and prefer it; otherwise keep the inline `", ".join(["%s"] * ...)`**:

```python
def build_ms02_pid_sql(eav_names):
    """SQL for resolving a personal-number (PID) list against the MS02 doc-field
    index. The personal-number EAV "Name"(s) matched against MANY exact
    "StringValue" PIDs (OR via = ANY). Identifiers are config constants (quoted,
    never user input); the Name(s) + the PID list are bound %s params -> no
    injection. This is the INVERSE shape of build_ms02_docfield_sql (the Name
    IN-set is paired with an exact = ANY PID list, not a single LIKE) -- a
    sibling, not a reuse of the AND/LIKE doc-field search resolver."""
    name_ph = ", ".join(["%s"] * len(eav_names))
    return (
        f'SELECT DISTINCT "{_MS02_DOCFIELD_ID_COL}" FROM "{_MS02_DOCFIELD_TABLE}" '
        f'WHERE "{_MS02_DOCFIELD_NAME_COL}" IN ({name_ph}) '
        f'AND "{_MS02_DOCFIELD_VALUE_COL}" = ANY(%s)'
    )


def resolve_ms02_pid_ids(engine, eav_names, pid_values):
    """Resolve a list of personal-number PIDs to an MS02 workitem-id allow-set.

    ``eav_names`` is the list of doc-field index "Name" values the PID is stored
    under (from 'ms02' SearchConfig col_pid rows -- never hard-coded; usually one
    Name). ``pid_values`` is the deduped PID list from the uploaded Excel.
    Matching is EXACT (= ANY), not LIKE, since PIDs are precise identifiers. One
    PID can map to many workitems; the result is the UNION of all matching
    workitem ids.

    Three-way contract (mirrors resolve_ms02_docfield_ids):
      * None      -> no constraint (engine absent, no names, no PIDs, or error).
      * set()     -> no PID matched a workitem -> force zero MS02 rows.
      * {ids...}  -> union allow-set -> twi."ID" = ANY(%s).
    Never raises: on error it logs and returns None (no constraint).
    """
    if engine is None or not eav_names or not pid_values:
        return None
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute(build_ms02_pid_sql(eav_names), [*eav_names, list(pid_values)])
        return {row[0] for row in cur.fetchall()}
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_pid_ids: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step 4: Run the tests green**

Run: `python -m pytest tests/unit/test_workitem_sources.py -v`
Expected: all green (existing tests unaffected — no signature changes).

- [ ] **Step 5: ruff + commit**

```bash
ruff check nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
ruff format nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
git add nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
git commit -F- <<'EOF'
feat(workitems): add resolve_ms02_pid_ids sibling resolver (PID->id allow-set)

A PID import is the personal-number EAV "Name"(s) matched against MANY exact
PID values OR-ed together -- the inverse shape of resolve_ms02_docfield_ids
(which ANDs across fields with one LIKE value each). Add a SIBLING resolver
rather than overload the search resolver: build_ms02_pid_sql does "Name" IN (..)
AND "StringValue" = ANY(%s); resolve_ms02_pid_ids returns the union workitem-id
allow-set under the same None/empty/populated three-way contract and reuses the
_MS02_DOCFIELD_* identifier constants. Feeds the existing
WorkitemFilter.ms02_docfield_ids -> twi."ID" = ANY(%s) seam unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — xlsx upload validation

### Task 3: Allow `.xlsx` in the MIME whitelist

**Files:**
- Modify: `nx_lib/files.py` (`ALLOWED_MIME_TYPES`)
- Test: `tests/unit/test_files_xlsx.py` (new file)

**Interfaces:**
- `is_file_allowed(filename, file_stream)` accepts `.xlsx` whose sniffed MIME is the office-openxml type OR a zip container (`.xlsx` is a zip; libmagic commonly reports `application/zip` and sometimes `application/octet-stream`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_files_xlsx.py
"""xlsx upload validation: real .xlsx passes, a renamed non-xlsx is rejected."""

import io

import openpyxl

from nx_lib.files import is_file_allowed


def _xlsx_bytes():
    wb = openpyxl.Workbook()
    wb.active.append(["PID", "Prepared"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_real_xlsx_is_allowed():
    assert is_file_allowed("prepared.xlsx", _xlsx_bytes()) is True


def test_pdf_bytes_renamed_to_xlsx_is_rejected():
    fake = io.BytesIO(b"%PDF-1.4 not really a spreadsheet")
    assert is_file_allowed("prepared.xlsx", fake) is False


def test_xlsx_extension_required():
    assert is_file_allowed("prepared.txt", _xlsx_bytes()) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_files_xlsx.py -v`
Expected: FAIL — `xlsx` is not in `ALLOWED_MIME_TYPES`, so `test_real_xlsx_is_allowed` returns `False`.

- [ ] **Step 3: Add the xlsx entry**

In `nx_lib/files.py`, extend `ALLOWED_MIME_TYPES` (currently `{"pdf": [...], "png": [...], "jpg": [...], "jpeg": [...]}`):

```python
ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "png": ["image/png"],
    "jpg": ["image/jpeg"],
    "jpeg": ["image/jpeg"],
    # .xlsx is an OOXML zip container. libmagic reports it as the office-openxml
    # type on newer builds, but falls back to a generic zip/octet-stream on
    # others -- accept all three for the .xlsx extension. (The extension is still
    # required, and the parser (parse_prepared_xlsx) is the real structural gate:
    # a renamed .pdf/.zip without a valid workbook returns a parse error.)
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    ],
}
```

> Note: a `.zip` renamed to `.xlsx` would pass the MIME gate (it *is* a zip) but fail `parse_prepared_xlsx` (not a valid workbook → error flash). The two-layer gate (MIME sniff + workbook parse) is intentional.

- [ ] **Step 4: Run the test green**

Run: `python -m pytest tests/unit/test_files_xlsx.py -v`
Expected: PASS. If the local libmagic build reports something other than the three accepted MIMEs, log it and widen the list (note the actual value the SYAPP01 prod libmagic emits in the commit body as an Owner/ops caveat — Owner action #7).

- [ ] **Step 5: ruff + commit**

```bash
ruff check nx_lib/files.py tests/unit/test_files_xlsx.py
ruff format nx_lib/files.py tests/unit/test_files_xlsx.py
git add nx_lib/files.py tests/unit/test_files_xlsx.py
git commit -F- <<'EOF'
feat(files): allow .xlsx uploads in the libmagic MIME whitelist

Extend ALLOWED_MIME_TYPES with an xlsx entry for the MS02 prepared-documents
import. .xlsx is an OOXML zip container, so libmagic may report the office-
openxml MIME, a generic application/zip, or application/octet-stream depending
on the build -- accept all three for the .xlsx extension. The workbook parser
(parse_prepared_xlsx) is the real structural gate, so a renamed zip without a
valid sheet still fails downstream with a parse error.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Orchestrator: thread the PID allow-set into the list

### Task 4: `_get_workitems_data` consumes `pidImport` token (PostgresSource-only)

**Files:**
- Modify: `nx_lib/workitem_sources.py` (add `WorkitemFilter.pid_import_active` + the `SqlServerSource.list_workitems` early-return)
- Modify: `nx_lib/views/workitems.py` (add the `CLIENTS` import + the `resolve_ms02_pid_ids`/`parse_prepared_xlsx` imports for later tasks; parse the new `pidImport` token, read the id-set from the session, intersect into `ms02_docfield_ids`, flag the default source off)
- Test: `tests/unit/test_workitems_pid_filter.py` (new file); extend `tests/unit/test_workitem_sources.py`

**Interfaces:**
- New optional request param `pidImport` (a short token the upload route returned). When present, `_get_workitems_data` reads `session["pid_import:<token>"]` (a list of MS02 workitem ids), intersects it into `ms02_docfield_ids` (so the existing `WorkitemFilter.ms02_docfield_ids` → `ANY(%s)` seam applies it to `PostgresSource` only), and sets `pid_import_active=True` to force MS02-only results (default source suppressed — Decision #9).
- Back-compat: when `pidImport` is absent (or unknown), behaviour is byte-identical to today. `api_workitems` and `export_workitems_csv` (both call `_get_workitems_data(request.args, ...)`) inherit the param transparently.

> **Why a session token, not a URL id-list:** one PID → many workitems, so a raw `?pidWorkitemId=...` list could be hundreds of ids — past sane URL limits and polluting the address bar that `fetchAndUpdateWorkitems` rewrites via `pushState`. The upload route stashes the resolved id-set in the server session under a random token and hands the token back; the orchestrator reads it back out (Findings F2, F7).

> **Default-source suppression mechanism:** `fetch_merged_page` builds sources and unpacks `rows, total = source.list_workitems(...)`. Add a `pid_import_active: bool = False` field on `WorkitemFilter` (AFTER `ms02_docfield_ids`, the current last field, so positional construction elsewhere is unaffected) that `SqlServerSource.list_workitems` honours by returning `([], 0)` as its **literal first statement** (before the `where_clauses = [...]` build and well before `self.engine.raw_connection()`). This keeps gating in the source layer (testable) rather than branching `fetch_merged_page`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_workitems_pid_filter.py
"""_get_workitems_data threads a pidImport session token into ms02_docfield_ids
and suppresses the default source during a PID import."""

from unittest.mock import patch

from werkzeug.datastructures import MultiDict

import nx_lib.views.workitems as wv


def test_pid_ids_intersected_into_ms02_docfield_ids(app):
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        from flask import session

        session["pid_import:tok123"] = [10, 20, 30]
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            wv._get_workitems_data(MultiDict([("pidImport", "tok123")]))
    filt = captured["filt"]
    assert filt.ms02_docfield_ids == {10, 20, 30}
    assert filt.pid_import_active is True


def test_no_pid_param_leaves_filter_unconstrained(app):
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            wv._get_workitems_data(MultiDict())
    assert captured["filt"].pid_import_active is False


def test_unknown_pid_token_is_ignored(app):
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            wv._get_workitems_data(MultiDict([("pidImport", "nope")]))
    # Unknown token -> treated as an empty import (MS02-only, zero MS02 rows).
    assert captured["filt"].pid_import_active is True
    assert captured["filt"].ms02_docfield_ids == set()
```

Add to `tests/unit/test_workitem_sources.py`:

```python
def test_sqlserver_source_suppressed_during_pid_import(app):
    src = ws.SqlServerSource.__new__(ws.SqlServerSource)
    src.engine = None  # would explode if it tried to query
    filt = ws.WorkitemFilter(
        process_names=["p"],
        client_names=["c"],
        activity_ignore_csv="",
        pid_import_active=True,
    )
    with app.app_context():
        rows, total = src.list_workitems(filt, 0, 40)
    assert rows == []
    assert total == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/unit/test_workitems_pid_filter.py tests/unit/test_workitem_sources.py -v -k "pid"`
Expected: FAIL — `pid_import_active` is not a `WorkitemFilter` field; `_get_workitems_data` ignores `pidImport`; `SqlServerSource` does not short-circuit.

- [ ] **Step 3a: Add `WorkitemFilter.pid_import_active` + SqlServerSource early-return**

In `nx_lib/workitem_sources.py`, add to `WorkitemFilter` immediately after the `ms02_docfield_ids: set | None = None` field (the current last field):

```python
    # True when the request is an MS02 'prepared documents' PID import. The
    # default SQL Server source has no PID concept, so it contributes nothing
    # during a PID import -- the list shows only the matched MS02 workitems.
    pid_import_active: bool = False
```

At the TOP of `SqlServerSource.list_workitems` (the method begins `def list_workitems(self, filt, offset, limit):` then a docstring; insert as the first statement after the docstring, before `where_clauses = [`):

```python
        if filt.pid_import_active:
            return [], 0  # MS02-only PID import: default source contributes nothing
```

- [ ] **Step 3b: Thread `pidImport` in `_get_workitems_data`**

In `nx_lib/views/workitems.py`:

1. Add `from ..clients import CLIENTS` to the `from ..` import block (verified NOT currently imported — Finding F3). Place it near the other `from ..` imports (e.g. right after `from ..files import is_file_allowed`).
2. Extend the existing `from ..workitem_sources import (...)` block (which already imports `resolve_ms02_docfield_ids`, `WorkitemFilter`, `fetch_merged_page`, etc.) with `parse_prepared_xlsx` and `resolve_ms02_pid_ids` (keep the block sorted).
3. In `_get_workitems_data`, find the end of the MS02 doc-field pre-fetch block — the `finally:` that closes `cursor_nex2`/`conn_nex2`, immediately before `status_map = {"Ready": 0, "In Progress": 1, "Done": 5}`. Insert between them:

```python
    # --- MS02 'prepared documents' PID import allow-set ---
    # The upload route (import_prepared_audit) resolved the uploaded personal-
    # number PIDs to MS02 workitem ids and stashed them in the session under a
    # token; the JS re-queries the list with ?pidImport=<token>. Read the id-set
    # back out and intersect into ms02_docfield_ids so the SAME PostgresSource
    # twi."ID" = ANY(%s) seam applies it; force MS02-only by flagging the
    # default source off. An unknown/expired token resolves to an empty set
    # (zero MS02 rows) rather than silently dropping the MS02-only gate.
    pid_import_active = False
    pid_token = args.get("pidImport", "").strip()
    if pid_token:
        pid_import_active = True
        stored = session.get(f"pid_import:{pid_token}") or []
        pid_ids = set()
        for raw in stored:
            try:
                pid_ids.add(int(raw))
            except (TypeError, ValueError):
                continue
        if ms02_docfield_ids is None:
            ms02_docfield_ids = pid_ids
        else:
            ms02_docfield_ids = ms02_docfield_ids & pid_ids
```

4. Add `pid_import_active=pid_import_active,` to the `WorkitemFilter(...)` constructor call (alongside the existing `ms02_docfield_ids=ms02_docfield_ids,` line).

> The upload route (Task 6) is what actually *resolves* PIDs via `resolve_ms02_pid_ids` and writes the session entry; `_get_workitems_data` only consumes it. `parse_prepared_xlsx`/`resolve_ms02_pid_ids` are imported here so the route (same module) can use them.

- [ ] **Step 4: Run the tests green**

Run: `python -m pytest tests/unit/test_workitems_pid_filter.py tests/unit/test_workitem_sources.py -v`
Expected: all green. Existing `_get_workitems_data` / source tests unaffected (param is additive, default `pid_import_active=False`).

- [ ] **Step 5: ruff + commit**

```bash
ruff check nx_lib/views/workitems.py nx_lib/workitem_sources.py tests/unit/test_workitems_pid_filter.py tests/unit/test_workitem_sources.py
ruff format nx_lib/views/workitems.py nx_lib/workitem_sources.py tests/unit/test_workitems_pid_filter.py tests/unit/test_workitem_sources.py
git add nx_lib/views/workitems.py nx_lib/workitem_sources.py tests/unit/test_workitems_pid_filter.py tests/unit/test_workitem_sources.py
git commit -F- <<'EOF'
feat(workitems): thread pidImport token into the list (MS02-only PID import)

_get_workitems_data accepts an optional pidImport token (the key the prepared-
documents upload route used to stash the resolved MS02 workitem ids in the
session), reads the id-set back out, and intersects it into ms02_docfield_ids --
reusing the existing PostgresSource twi."ID" = ANY(%s) seam. A new
WorkitemFilter.pid_import_active flag forces MS02-only results during a PID
import by short-circuiting SqlServerSource.list_workitems to ([], 0). A session
token (not a URL id-list) avoids multi-kilobyte query strings when one PID maps
to many workitems. Also imports CLIENTS (not previously imported) for the route
gate. Absent the param the path is byte-identical; api_workitems and export
inherit it for free.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — Permission migration

### Task 5: Migration `0029` — seed `workitems.import.preparedaudit`

**Files:**
- Create: `sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql` (new file)
- Modify (optional, realism only): `sql/test/seed.sql`

**Interfaces:**
- Produces: `dbo.Permission` row `workitems.import.preparedaudit`, granted Effect `'A'` to every profile that already has `admin.view` (modelled on `0018`).

> **Note (Finding F1):** the integration test for the new route passes via the `workitems_all_perms` fixture, which **monkeypatches `nx_lib.security.has_permission` to always-True** — it does NOT read `sql/test/seed.sql`. So the seed.sql edit below is **NOT** required for the test to pass; it is included only for parity/realism so a seeded user *could* hold the perm. Do it if `seed.sql` already enumerates `workitems.*` perms in a way that's cheap to extend; skip it otherwise. Either way, do not justify it as a test-passing step.

- [ ] **Step 0: Confirm `0029` is still the next free number**

Run (Glob tool): list `sql/_migrations/NexoraDB/*.sql`. Verified the dir currently tops at `0028_rename_ms02_process_to_05_pdbs.sql`. If a higher number now exists, bump the new filename.

- [ ] **Step 1: Write the migration**

Create `sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql`:

```sql
-- 0029_seed_workitems_prepared_audit_permission.sql
-- New grantable permission for the MS02-only 'prepared documents' Excel import
-- on the workitems list:
--   workitems.import.preparedaudit -- upload a two-column Excel (PID = personal
--     number, Prepared = informational) and display the matched MS02 workitems
--     so their full Octo audit can be reviewed. MS02-only at runtime (the route
--     also gates on engine_ms02_docfields_pg being present); this perm only
--     controls whether the upload control is offered + the route is reachable.
-- Seeded Effect 'A' to every access profile that already grants admin.view, so
-- admins/owner have it out of the box; grantable per-user. Idempotent. Mirrors
-- migration 0018.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.import.preparedaudit',
       'Workitems: import an MS02 prepared-documents Excel (PID/Prepared) and display the matched workitems'' audit'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.import.preparedaudit');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.import.preparedaudit'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
```

- [ ] **Step 2: Apply to INT**

Run: `python scripts/db-migrate.py --env INT`
Expected: applies `0029`, records it in `dbo.SchemaMigrations`. If it errors on CRLF checksum drift for an *earlier* migration (not `0029` SQL), that is the known INT drift — proceed and use the `SQL_SYNC_SKIP=1` hatch at commit.

- [ ] **Step 3: Verify the row exists**

```sql
SELECT Code FROM dbo.Permission WHERE Code = 'workitems.import.preparedaudit';
```
Expected: one row.

- [ ] **Step 4 (optional realism): grant it in the test seed**

If `sql/test/seed.sql` enumerates `workitems.*` codes in a way that's cheap to extend, add `workitems.import.preparedaudit` the same way. This is NOT what makes the integration test pass (the fixture monkeypatches `has_permission`); skip if `seed.sql`'s structure makes it awkward.

- [ ] **Step 5: Commit (SQL hatch only if the hook flakes on CRLF drift)**

```bash
git add sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql
# (also: git add sql/test/seed.sql -- only if Step 4 was done)
git commit -F- <<'EOF'
feat(db): seed workitems.import.preparedaudit permission (0029)

Add the grantable workitems.import.preparedaudit permission for the MS02-only
prepared-documents Excel import, modelled on migration 0018: idempotent INSERT
into dbo.Permission, then Effect 'A' to every profile that already has
admin.view. The route additionally gates on engine_ms02_docfields_pg at runtime
(MS02-only). The integration test exercises the route via the workitems_all_perms
fixture (which monkeypatches has_permission), so this seed is for INT/PROD parity.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```
If the `sql-migrate-int` hook fails on stale CRLF checksums for `0001`–`0003`, prefix with `SQL_SYNC_SKIP=1`.

---

# PHASE 6 — The upload route

### Task 6: `import_prepared_audit` POST route

**Files:**
- Modify: `nx_lib/views/workitems.py` (new route fn + a `_ms02_pid_eav_names` helper + register the rule)
- Test: `tests/integration/test_workitems_routes.py` (extend)

**Interfaces:**
- `POST /import_prepared_audit` — `@require_permission("workitems.import.preparedaudit")`. Body: multipart with `preparedAuditFile` (xlsx). Behaviour:
  1. `engine_ms02_docfields_pg is None` OR `"ms02" not in CLIENTS` → 400 JSON `{"error": "..."}` (MS02-only).
  2. Missing/empty file → 400 JSON.
  3. `is_file_allowed(..., xlsx)` fails → 400 JSON (invalid type).
  4. `parse_prepared_xlsx` error / no rows → 400 JSON.
  5. Read the personal-number EAV `"Name"`(s) from the `'ms02'` `SearchConfig` rows for the user's `target_processes` (the SAME query the orchestrator's MS02 block runs — `col_pid`, `ClientCode='ms02'`, `ProcessName IN (target_processes)`). If unmapped → 200 JSON `{ids: [], matched: 0, total: <n>, prepared: {}, warning: "..."}` (graceful).
  6. `resolve_ms02_pid_ids(engine_ms02_docfields_pg, eav_names, pids)` → id set; stash the sorted int id-list in the session under a fresh `secrets.token_urlsafe` token (`session["pid_import:<token>"] = ids`); return JSON `{token, prepared: {pid: bool}, matched: <#resolved ids>, total: <#pids>}`.
- CSRF: the global Flask-WTF `CSRFProtect` applies; the JS sends `X-CSRFToken` (same as `uploadBatchFiles`/`fetchAndUpdateWorkitems`).

> **Deriving the EAV `"Name"` and the process key (Finding F5):** the route must NOT hardcode `sydoc.05_PDBS`. The orchestrator's MS02 doc-field block derives `target_processes` from the user's `workitems.filter.process.*` perms and binds `SELECT col_<field> FROM SearchConfig WHERE col_<field> IS NOT NULL AND ClientCode='ms02' AND ProcessName IN (placeholders)`. The route reuses that exact pattern with `col_pid`. A small module constant `_MS02_PID_SEARCH_FIELD = "pid"` names the SearchConfig field; the owner seeds `col_pid = '<EAV Name>'`. If `col_pid` is unseeded/NULL the route degrades to the "unmapped" warning branch. `get_valid_search_columns()` is already a module-level function in this file — reuse it to whitelist `col_pid` before interpolation.

- [ ] **Step 1: Write the failing integration tests**

Add to `tests/integration/test_workitems_routes.py` (mirror the existing `test_import_workitems_gated` style at the established `(noperm_client → 403)` pattern):

```python
def test_import_prepared_audit_gated(noperm_client):
    resp = noperm_client.post("/import_prepared_audit")
    assert resp.status_code == 403


def test_import_prepared_audit_no_file(user_client, workitems_all_perms):
    resp = user_client.post("/import_prepared_audit")
    # No MS02 engine in CI -> MS02-only gate fires first -> 400 (never 500).
    assert resp.status_code in (400, 403)


def test_import_prepared_audit_rejects_non_xlsx(user_client, workitems_all_perms):
    import io

    data = {"preparedAuditFile": (io.BytesIO(b"%PDF-1.4 nope"), "x.xlsx")}
    resp = user_client.post(
        "/import_prepared_audit", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code in (400, 403)  # rejected, not a 500
```

(In CI `engine_ms02_docfields_pg is None`, so the MS02-only gate fires first and returns 400 before any parsing — the assertions tolerate that. The `noperm_client` case proves the `@require_permission` gate returns 403 — `noperm_client` is authenticated, so it is a 403, not the unauthenticated redirect.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/integration/test_workitems_routes.py -v -k prepared_audit`
Expected: FAIL — the route is not registered (404, not 400/403).

- [ ] **Step 3: Implement the route**

In `nx_lib/views/workitems.py` (imports for `CLIENTS`, `parse_prepared_xlsx`, `resolve_ms02_pid_ids` were added in Task 4). Add `import secrets` to the stdlib imports if not present. Add a module constant near the other field/config helpers:

```python
# The 'ms02' SearchConfig col_<field> whose value is the personal-number (PID)
# EAV "Name" in the MS02 doc-field index. Owner-seeded (col_pid='<EAV Name>').
_MS02_PID_SEARCH_FIELD = "pid"
```

Add the helper (place it near `get_valid_search_columns`):

```python
def _ms02_pid_eav_names(target_processes):
    """Read the personal-number EAV "Name"(s) from the 'ms02' SearchConfig rows
    (col_pid) for the given processes. Mirrors the orchestrator's MS02 doc-field
    SearchConfig read: whitelisted column, ClientCode='ms02', ProcessName IN
    (target_processes) -- NEVER a hardcoded process key. Returns the list of
    Names (usually one) or [] when unseeded."""
    col = f"col_{_MS02_PID_SEARCH_FIELD}"
    if col not in get_valid_search_columns() or not target_processes:
        return []
    conn = None
    cur = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(target_processes))
        cur.execute(
            f"SELECT {col} FROM SearchConfig "
            f"WHERE {col} IS NOT NULL AND ClientCode = 'ms02' "
            f"AND ProcessName IN ({placeholders})",
            target_processes,
        )
        return [r[0] for r in cur.fetchall() if r[0]]
    except Exception as e:
        current_app.logger.error(f"_ms02_pid_eav_names: {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _ms02_target_processes():
    """The user's MS02-eligible process allow-list, derived the same way
    _get_workitems_data does (from workitems.filter.process.* perms)."""
    prefix = "workitems.filter.process."
    out = []
    for perm in session.get("permissions", []):
        if perm.startswith(prefix):
            parts = perm.split(".")
            if len(parts) >= 2:
                out.append(f"{parts[-2]}.{parts[-1]}")
    return out
```

Add the route function (place it right after `import_workitems`):

```python
@require_permission("workitems.import.preparedaudit")
def import_prepared_audit():
    """MS02-only: upload a two-column Excel (PID = personal number, Prepared =
    informational), resolve each PID through the MS02 doc-field index to its
    workitem id(s), stash the id-set in the session under a token, and return
    the token so the list can re-query and display the matched workitems (the
    user opens each to read the full Octo audit). Display only -- the Prepared
    column is never reconciled against the audit."""
    # Defensive parity with import_workitems (require_permission already gates
    # auth, redirecting unauthenticated users to login; this never 401s a gated
    # caller -- it is dead-code parity, not a tested path).
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    # MS02-only gate: no MS02 doc-field engine / no ms02 client -> not available.
    if engine_ms02_docfields_pg is None or "ms02" not in CLIENTS:
        return jsonify({"error": _("This import is only available for the MS02 client.")}), 400

    if "preparedAuditFile" not in request.files:
        return jsonify({"error": _("No file part in the request.")}), 400
    file = request.files["preparedAuditFile"]
    if not file or file.filename == "":
        return jsonify({"error": _("No file selected for uploading.")}), 400

    if not is_file_allowed(file.filename, file.stream):
        return jsonify(
            {"error": _("Invalid file type. Please upload a valid Excel (.xlsx) file.")}
        ), 400

    data = file.stream.read()
    pairs, parse_err = parse_prepared_xlsx(data)
    if parse_err:
        return jsonify({"error": parse_err}), 400
    if not pairs:
        return jsonify({"error": _("The Excel file has no usable rows.")}), 400

    pids = [pid for pid, _prep in pairs]
    prepared = {pid: prep for pid, prep in pairs}

    eav_names = _ms02_pid_eav_names(_ms02_target_processes())
    if not eav_names:
        return jsonify(
            {
                "token": None,
                "prepared": prepared,
                "matched": 0,
                "total": len(pids),
                "warning": _("The personal-number field is not configured for MS02."),
            }
        ), 200

    id_set = resolve_ms02_pid_ids(engine_ms02_docfields_pg, eav_names, pids)
    ids = sorted(id_set) if id_set else []
    token = secrets.token_urlsafe(16)
    session[f"pid_import:{token}"] = ids
    return jsonify(
        {
            "token": token,
            "prepared": prepared,
            "matched": len(ids),
            "total": len(pids),
        }
    ), 200
```

Register the route in `register_routes(app)` (after the `import_workitems` rule, which uses `methods=["POST"]`):

```python
    app.add_url_rule(
        "/import_prepared_audit",
        endpoint="import_prepared_audit",
        view_func=import_prepared_audit,
        methods=["POST"],
    )
```

> `get_valid_search_columns` is a module-level function in this file (verified), so `_ms02_pid_eav_names` can call it directly — no hoist needed.

- [ ] **Step 4: Run the integration tests green**

Run: `python -m pytest tests/integration/test_workitems_routes.py -v -k prepared_audit`
Expected: PASS (CI hits the MS02-only gate → 400; `noperm_client` → 403).

- [ ] **Step 5: Full route-module sanity**

Run: `python -c "import nx_lib.views.workitems; print('ok')"` → `ok`.
Run: `python -m pytest tests/unit/test_workitem_sources.py tests/unit/test_prepared_xlsx_parser.py tests/unit/test_workitems_pid_filter.py tests/unit/test_files_xlsx.py -v` → all green.

- [ ] **Step 6: ruff + commit**

```bash
ruff check nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
ruff format nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -F- <<'EOF'
feat(workitems): add MS02-only import_prepared_audit upload route

POST /import_prepared_audit accepts a two-column Excel (PID = personal number,
Prepared = informational), validates it (libmagic MIME sniff + workbook parse),
reads the personal-number EAV "Name"(s) from the 'ms02' SearchConfig col_pid
rows for the user's target processes (same dynamic ProcessName IN (...) query the
orchestrator runs -- never a hardcoded process key), resolves the PIDs to MS02
workitem ids via resolve_ms02_pid_ids, stashes them in the session under a token,
and returns {token, prepared, matched, total}. MS02-only (gated on
engine_ms02_docfields_pg + CLIENTS['ms02']) and guarded by
workitems.import.preparedaudit. Degrades gracefully when unmapped or the engine
is absent (CI). Display only -- the Prepared flag is not reconciled.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 7 — Frontend (MS02-only control + handler)

### Task 7: Template control + render flags

**Files:**
- Modify: `nx_lib/views/workitems.py` (`workitems_overview()` render vars)
- Modify: `templates/workitems_overview.html` (the upload control + a result banner)

**Interfaces:**
- New render vars: `prepared_import_perm = has_permission("workitems.import.preparedaudit")` and `ms02_active = ("ms02" in CLIENTS and engine_ms02_docfields_pg is not None)`. The control renders only when both are truthy. (`CLIENTS` import added in Task 4.)

- [ ] **Step 1: Add the render vars**

In `workitems_overview()`, near the other `*_perm = has_permission(...)` lines, add:

```python
        prepared_import_perm = has_permission("workitems.import.preparedaudit")
        ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
```

and pass them into the `render_template("workitems_overview.html", ...)` call: `prepared_import_perm=prepared_import_perm, ms02_active=ms02_active`.

- [ ] **Step 2: Add the control to the template**

In `templates/workitems_overview.html`, next to the existing Import control (find the `importFile` `<input>` + `importBtn` `<button>` block), add a sibling inside the same toolbar:

```html
          {% if prepared_import_perm and ms02_active %}
          <div class="inline-block">
            <input type="file" id="preparedAuditFile" name="preparedAuditFile"
              class="hidden" accept=".xlsx" data-testid="workitems-prepared-audit-file">
            <button type="button" id="preparedAuditBtn"
              class="nx-btn nx-btn--secondary" data-testid="workitems-prepared-audit">
              <i class="fas fa-file-excel mr-2"></i>{{ _("Prepared documents") }}
            </button>
          </div>
          {% endif %}
```

> The `id="preparedAuditFile"` input is intentionally OUTSIDE (or, if inside, it is `type="file"` which `fetchAndUpdateWorkitems` already skips) the `filterForm` so it never leaks into the list query string. Confirm placement does not add it to `filterForm.elements` as a non-file field.

Add a dismissible result banner above the table (near where the degraded-source banner is inserted, or just under the toolbar), hidden by default:

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

- [ ] **Step 3: Restart dev server + verify it renders (no JS yet)**

Run: `nx -u` (restart — Jinja cache). Confirm the page still renders and, for a non-MS02 user, the control is absent. Manual/visual check; the wiring test comes next.

- [ ] **Step 4: ruff + commit**

```bash
ruff check nx_lib/views/workitems.py
ruff format nx_lib/views/workitems.py
git add nx_lib/views/workitems.py templates/workitems_overview.html
git commit -F- <<'EOF'
feat(workitems): add MS02-only Prepared-documents upload control + banner

Render an MS02-only 'Prepared documents' Excel-upload control next to the
existing Import button, gated in Jinja on prepared_import_perm AND ms02_active
(engine_ms02_docfields_pg present + CLIENTS['ms02']). Adds a dismissible result
banner for the matched/total summary. Wiring (POST + re-query) lands in the JS
partial next.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 8: JS handler — upload, re-query, banner

**Files:**
- Modify: `templates/js/_workitems_overview_js.html`

**Interfaces:**
- `uploadPreparedAudit(file)` — POSTs `preparedAuditFile` to `import_prepared_audit` (FormData, `X-CSRFToken`), then re-queries the list via the EXISTING `fetchAndUpdateWorkitems()` path with the returned `token` appended as `pidImport`, and shows the banner (`matched`/`total`, plus a warning when `matched < total` or `warning` present).

> **List re-query mechanism (Finding F2 — verified):** `fetchAndUpdateWorkitems(page)` builds `params` by iterating `filterForm.elements` (skipping `file`/`hidden`/unchecked), then `params.set('page', page)`, fetches `api/workitems?${params}`, and `pushState`s `?${params}` onto the visible URL. There is no module-level URL-builder to wrap and the file/hidden skip means a wrapper approach won't engage. **The correct hook is to modify `fetchAndUpdateWorkitems` directly:** keep a module-level `activePidToken`; inside the function, after the form loop and `params.set('page', page)`, append `pidImport` to the FETCH params only, and build the `pushState` URL from a SEPARATE params object that omits `pidImport` so the address bar isn't polluted. Locate the exact lines in `_workitems_overview_js.html`:
> ```js
> const url = `${API_PREFIX}api/workitems?${params.toString()}`;
> const newUrl = `${window.location.pathname}?${params.toString()}`;
> window.history.pushState({ path: newUrl }, '', newUrl);
> ```
> Replace with:
> ```js
> const fetchParams = new URLSearchParams(params);
> if (activePidToken) fetchParams.set('pidImport', activePidToken);
> const url = `${API_PREFIX}api/workitems?${fetchParams.toString()}`;
> const newUrl = `${window.location.pathname}?${params.toString()}`;
> window.history.pushState({ path: newUrl }, '', newUrl);
> ```

- [ ] **Step 1: Add the upload handler + token state**

Near `uploadBatchFiles` in `_workitems_overview_js.html`, add:

```javascript
let activePidToken = null;  // null = no PID filter; set = filter active

async function uploadPreparedAudit(file) {
    if (!file) return;
    const btn = document.getElementById('preparedAuditBtn');
    if (btn) { btn.disabled = true; btn.innerHTML =
        `<i class="fas fa-spinner fa-spin mr-2"></i>{{ _("Prepared documents") }}`; }
    try {
        const formData = new FormData();
        formData.append('preparedAuditFile', file);
        const resp = await fetch(`${API_PREFIX}import_prepared_audit`, {
            headers: {'X-CSRFToken': csrfToken},
            method: 'POST',
            body: formData,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            showNotification(data.error || '{{ _("Import failed.") }}', 'error');
            return;
        }
        activePidToken = data.token || null;
        const banner = document.getElementById('preparedAuditBanner');
        const text = document.getElementById('preparedAuditBannerText');
        if (banner && text) {
            let msg = `{{ _("Matched") }} ${data.matched} / ${data.total} {{ _("PIDs") }}.`;
            if (data.warning) msg += ' ' + data.warning;
            else if (data.matched < data.total)
                msg += ' {{ _("Some PIDs matched no workitem.") }}';
            text.textContent = msg;
            banner.classList.remove('hidden');
        }
        // Re-query page 1 with the token applied via fetchAndUpdateWorkitems.
        await fetchAndUpdateWorkitems(1);
    } catch (e) {
        console.error('uploadPreparedAudit', e);
        showNotification('{{ _("Import failed.") }}', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML =
            `<i class="fas fa-file-excel mr-2"></i>{{ _("Prepared documents") }}`; }
    }
}
```

- [ ] **Step 2: Inject the token into `fetchAndUpdateWorkitems`**

Apply the exact replacement quoted in the Interfaces note above (split `fetchParams` for the fetch URL, keep `params` for the `pushState` URL). This is the ONLY change to the existing fetch function and it is no-op when `activePidToken` is `null`.

- [ ] **Step 3: Register the control's event listeners**

In the existing block that wires `importBtn`/`importFile` (search `importBtn`), add the parallel wiring:

```javascript
            const preparedBtn = document.getElementById('preparedAuditBtn');
            const preparedInput = document.getElementById('preparedAuditFile');
            if (preparedBtn && preparedInput) {
                preparedBtn.addEventListener('click', () => {
                    preparedInput.value = '';
                    preparedInput.click();
                });
                preparedInput.addEventListener('change', () => {
                    if (preparedInput.files && preparedInput.files.length > 0) {
                        uploadPreparedAudit(preparedInput.files[0]);
                    }
                });
            }
            const bannerClear = document.getElementById('preparedAuditBannerClear');
            if (bannerClear) {
                bannerClear.addEventListener('click', () => {
                    activePidToken = null;
                    const b = document.getElementById('preparedAuditBanner');
                    if (b) b.classList.add('hidden');
                    fetchAndUpdateWorkitems(1);  // reload unfiltered
                });
            }
```

- [ ] **Step 4: Restart + browser-verify with Playwright (drive it yourself; remote = send screenshots)**

Run: `nx -u -b --loginas:<an MS02 operator user holding workitems.import.preparedaudit>`. Note: in local dev `engine_ms02_docfields_pg` may be `None` → the control is absent; if so, screenshot the toolbar WITHOUT the control (confirming the gate) and verify the full flow on INT where the engine is configured. Using Playwright: load `/workitems`, screenshot the toolbar; if MS02 is live, upload a tiny test `.xlsx` and screenshot the banner + the filtered list. Save shots to `var/screenshots/` and **send them to the user** (SendUserFile) without being asked.

- [ ] **Step 5: commit**

```bash
git add templates/js/_workitems_overview_js.html
git commit -F- <<'EOF'
feat(workitems): wire Prepared-documents upload -> PID filter + banner

uploadPreparedAudit POSTs the xlsx to import_prepared_audit (CSRF header), takes
the returned session token, and re-queries the list via the existing
fetchAndUpdateWorkitems path with ?pidImport=<token> appended to the FETCH URL
only (the pushState address bar stays clean), so the table shows exactly the
matched MS02 workitems (open a row -> the existing loadHistory audit panel
renders the full Octo audit). Surfaces a matched/total banner with an
unresolved-PID note; a Clear control drops the filter. Reuses the existing
import-button event-listener block + showNotification.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 8 — i18n + docs + changelog

### Task 9: i18n cycle

**Files:**
- Modify: `messages.pot`, `translations/de/LC_MESSAGES/messages.po`, `translations/fr/...`, `translations/it/...` (+ compiled `.mo`)

- [ ] **Step 1: Extract + update**

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2: Translate the new msgids (non-fuzzy) in de/fr/it**

Translate every new string: "Prepared documents", "Matched", "PIDs", "Some PIDs matched no workitem.", "Clear", "This import is only available for the MS02 client.", "Invalid file type. Please upload a valid Excel (.xlsx) file.", "The Excel file has no usable rows.", "The personal-number field is not configured for MS02.", "Import failed.", "Could not read the Excel file.", "The Excel file is empty.", "Missing required 'PID' column.", "Could not parse the Excel file.", "No file part in the request.", "No file selected for uploading." (some may already exist from `import_workitems` — pybabel will reuse them). Use the `/nx-i18n` skill to drive extract→update→compile.

- [ ] **Step 3: Compile + test**

```bash
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: PASS (pot in sync; all msgids non-fuzzy in de/fr/it).

- [ ] **Step 4: commit**

```bash
git add messages.pot translations/
git commit -F- <<'EOF'
i18n: translate MS02 prepared-documents import strings (de/fr/it)

Extract + translate the new user-facing strings for the MS02 prepared-documents
Excel import (control label, banner, flash/error messages, parser errors) into
de/fr/it, non-fuzzy. Keeps test_translations.py green.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 10: Docs + changelog

**Files:**
- Modify: `CHANGELOG.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` (one-line §4.6 touch)

- [ ] **Step 1: Changelog**

Under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- **MS02 'prepared documents' Excel import (workitems).** An MS02-only upload
  control on the workitems list accepts a two-column Excel (`PID` = personal
  number, `Prepared` = informational) and resolves each PID through the MS02
  doc-field index (`engine_ms02_docfields_pg`) to its workitem(s), listing them
  so the full Octo audit can be reviewed. Gated by the new permission
  `workitems.import.preparedaudit` (migration `0029`). Excel parsing via openpyxl
  (already a dependency); no reconcile logic — the `Prepared` column is
  display-only. New `resolve_ms02_pid_ids` resolver + `/import_prepared_audit`
  route reuse the existing `ms02_docfield_ids` → `twi."ID" = ANY(%s)` seam; the
  resolved id-set is passed via a session token, never serialized into the URL.
```

- [ ] **Step 2: CLAUDE.md**

In the `Databases` section's MS02 doc-field paragraph (find `resolve_ms02_docfield_ids` in `nx_lib/workitem_sources.py`), append:

```
The same EAV index also backs an MS02-only **personal-number (PID) import**:
`resolve_ms02_pid_ids` (sibling to `resolve_ms02_docfield_ids`, the
personal-number `"Name"`(s) matched against MANY exact PIDs via `= ANY`) and the
`/import_prepared_audit` route turn an uploaded two-column Excel (PID/Prepared)
into the same `ms02_docfield_ids` allow-set (handed to the list via a session
token, not the URL), listing the matched workitems so their full Octo audit can
be reviewed. Gated by `workitems.import.preparedaudit` (migration `0029`). The
personal-number EAV `"Name"` is owner-seeded as the `'ms02'` `SearchConfig`
`col_pid` value (read dynamically per the user's `target_processes`, e.g.
`ProcessName='sydoc.05_PDBS'` after migration `0028`).
```

- [ ] **Step 3: Spec §4.6 one-liner**

In `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` §4.6, add one sentence noting the same EAV doc-field index now also backs the PID-list import (`resolve_ms02_pid_ids` / `/import_prepared_audit`). No new spec.

- [ ] **Step 4: commit**

```bash
git add CHANGELOG.md CLAUDE.md docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md
git commit -F- <<'EOF'
docs: record MS02 prepared-documents import + resolve_ms02_pid_ids

Add the [Unreleased] changelog entry, extend the CLAUDE.md MS02 doc-field
paragraph with the PID import (resolve_ms02_pid_ids + /import_prepared_audit, the
workitems.import.preparedaudit perm, migration 0029, the col_pid owner seed, the
session-token id passing), and note the new use in the 2026-06-16 MS02 design
spec section 4.6. No new spec authored.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

# PHASE 9 — Full-suite verification

### Task 11: Run the full suite

- [ ] **Step 1: Reset order-dependent e2e state**

Run: `python scripts/test_db_reset.py`

- [ ] **Step 2: Full unit + integration**

Run: `python -m pytest tests/unit tests/integration -q`
Expected: green. If matplotlib/collection errors appear, `uv pip install -r requirements.txt` and prepend `.venv\Scripts` to PATH (known venv-drift remedy).

- [ ] **Step 3: ruff over the whole change**

Run: `ruff check nx_lib/ tests/ && ruff format --check nx_lib/ tests/`

- [ ] **Step 4: STOP — remote session**

Do **not** push and do **not** open a PR. All commits stay local on `feature/2.5.63` for the owner to review. If a `/handoff-session-state` is appropriate (work complete, nothing queued), run it unprompted.

---

## Gotchas & notes

- **PID is NOT a workitem id and NOT a process id.** It is a personal number, indexed as a document field in the MS02 EAV doc-field DB. Resolution is ALWAYS through `engine_ms02_docfields_pg` via the seeded `"Name"`. Never try to join a PID to `t_WorkItems` directly.
- **Resolver shape is the inverse of the search resolver.** `resolve_ms02_docfield_ids` = AND across fields, ONE `LIKE` value each. `resolve_ms02_pid_ids` = the personal-number `"Name"`(s), MANY exact values OR-ed. Do NOT reuse the search resolver for PIDs — it would intersect single-value LIKE calls and return ~nothing.
- **Stale process key trap.** Migration `0028` renamed the MS02 process to `05_PDBS`. The live SearchConfig key is `sydoc.05_PDBS` and the process perm is `workitems.filter.process.sydoc.05_PDBS`. Older `0025`/`0026`/`0027` text still says `praesidialdepartement_bs` — do NOT copy it. The route reads the process key **dynamically from `target_processes`** (never hardcoded), exactly like the orchestrator's MS02 doc-field block, so a future rename Just Works.
- **The id-set travels by session token, not the URL.** One PID → many workitems, so a raw `?pidWorkitemId=...` list would be huge. The route stashes the resolved ids in `session["pid_import:<token>"]` and returns the token; `_get_workitems_data` reads it back. An unknown/expired token resolves to an empty set (zero MS02 rows) while still forcing MS02-only — it never silently drops the filter. (The session is the active server-side Flask-Session filesystem backend in prod; in CI the in-memory default still works for the unit test via `test_request_context`.)
- **Owner seed gate.** Until the owner seeds `col_pid = '<EAV Name>'` in the `'ms02'` SearchConfig row AND sets `MS02_DOCFIELDS_DB_NAME`, the import resolves nothing — the route returns a `warning` and the list is empty. Graceful, not a bug. Confirm the exact EAV `"Name"` (Owner action #1) before claiming the feature works on INT.
- **Excel float coercion.** Excel stores integer-looking PIDs as floats; `_norm_pid` strips the `.0`. If the indexed `"StringValue"` has leading zeros the float path would drop them — confirm PID format with the owner (Owner action #3). If PIDs are zero-padded strings, ensure the Excel column is text-formatted (the parser preserves string cells verbatim).
- **Row cap.** `parse_prepared_xlsx` stops after `_PREPARED_MAX_ROWS` (10000) data rows to bound memory on a malicious/oversized workbook. `is_file_allowed` only sniffs the first 2048 bytes for MIME — the row cap is the real size guard.
- **Two-layer upload gate.** `is_file_allowed` (MIME sniff) + `parse_prepared_xlsx` (workbook structure). A renamed `.zip`/`.pdf` is caught by one or the other. libmagic reports `.xlsx` variably (office-openxml / zip / octet-stream) — the whitelist accepts all three; if the **prod** libmagic emits something else, widen `ALLOWED_MIME_TYPES["xlsx"]` (Owner action #7).
- **Audit is REUSE.** No new audit UI. Matched MS02 workitems open into the existing detail panel; `loadHistory` → `/api/get_audithistory/<id>` is client-routed via `get_domain_for_workitem` to the MS02 Octo domain. (Separately, `octo.py`'s `&WithDocumentAudits=true` is the per-document-extension audit for source-highlight — a DIFFERENT surface; do not conflate.)
- **Permission is per-control, not page-level.** `workitems.import.preparedaudit` is enforced via `@require_permission` + the Jinja `prepared_import_perm` gate and is intentionally NOT added to `page_visibility()` — mirroring `workitems.import.workitem`, which is likewise `@require_permission`-only. A reviewer should not flag its absence from `page_visibility()`.
- **Redundant unauthenticated check.** The route keeps the `if "username" not in session: return ..., 401` line for parity with `import_workitems`, but `@require_permission` already redirects unauthenticated callers to login (302) before the body runs — so the 401 branch is dead code for the gated path. Do NOT write a test asserting 401 for the anonymous case (it is a 302 redirect).
- **MS02 media/DNS caveat (not a blocker).** MS02 Octo returns media URLs on bare host `mobscn02`, unresolvable from dev, so MS02 page images never render locally (placeholders). The audit is a separate Octo API call and should render; verify on INT, not dev, if page images are needed.
- **Default path byte-identical.** The PID set funnels only into `ms02_docfield_ids` (PostgresSource). `pid_import_active` short-circuits `SqlServerSource.list_workitems` to `([], 0)` so a PID import shows MS02 rows only (Owner action #5). Absent the param, nothing changes for the default client.
- **WorkItemID type.** `resolve_ms02_pid_ids` returns whatever type `t_DocumentIndexes."WorkItemID"` is; the orchestrator `int()`-casts the stored token ids. The MS02 multi-source design treats workitem ids as integer-coercible — if MS02 ids turn out non-integer, the `int()` cast in `_get_workitems_data` would drop them; confirm during INT verification.
- **Template cache + remote screenshots.** Restart `nx -u` after every template/JS edit. On a remote session, drive Playwright yourself and SendUserFile the screenshots (toolbar with/without the control; banner; filtered list) — save to `var/screenshots/`.
- **SQL hook hatch.** `SQL_SYNC_SKIP=1 git commit` only for the known `0001`–`0003` CRLF checksum drift. Never `--no-verify`.
- **Migration number drift.** Re-list `sql/_migrations/NexoraDB/` at execution; the MS02 branch may have added past `0028`. Bump `0029` if needed.
