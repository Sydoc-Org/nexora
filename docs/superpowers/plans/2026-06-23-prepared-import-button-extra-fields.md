# Prepared-Import Button Fix + 5-Column Excel + Extra Display Columns — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three tightly-coupled fixes to the MS02 "prepared documents" Excel import on the workitems page: (1) restore the vanished upload button by removing the per-process JS gate, (2) extend the Excel parser from 2 columns (PID, Prepared) to 5 columns (PID, Collected, CollectedBy, Prepared, PreparedBy — with a duplicate-header typo), and (3) display the four imported values as extra table columns during an active import, with unmatched PIDs rendered as synthetic rows in the same list.

**Architecture:** All changes are additive extensions of the existing token/session seam. The session payload under `pid_import:<token>` grows from a flat sorted-int-list to a dict `{ids, payloads, pid_to_wids}`. A new `resolve_ms02_pid_to_wids(engine, specs, pid_values)` sibling returns `{pid_str: [wid_int, ...]}` for matched PIDs only (unmatched absent); the flat-union `resolve_ms02_pid_ids` is kept for existing callers and its import removed from workitems.py when no longer used. `_get_workitems_data` merges import values onto matched rows and appends synthetic rows for unmatched PIDs **on page 1 only** (`offset == 0`). The JS `renderTable` branches on `workitem.synthetic` for synthetic rows and renders 4 extra `<td class="import-col">` cells for real rows; column visibility is driven by toggling the `no-import-cols` CSS class on `#workitemsTable`. The default (no pidImport) path remains **byte-identical**.

**Tech Stack:** Python 3, Flask, psycopg2-binary, openpyxl (existing dependency), Flask-Session, Flask-Babel i18n, pytest. No new dependencies, no migration.

**Predecessor plan:** `docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md` (original feature; format reference).

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63`. Execute on the worktree for this plan (`plan/prepared-import-button-extra-fields`, off HEAD `1fa8437`). Create a new feature branch for the actual implementation work, e.g. `feat/prepared-import-5col`, or commit directly onto `feature/2.5.63` from a fresh worktree.
- **Remote session = commit only.** Stage + commit freely on any feature branch. Do **not** push, do not open a PR.
- **Anchor on snippets, never line numbers.** Every code reference below quotes the exact snippet to locate. Line numbers are reading aids and will drift.
- **Columnar rewrite already landed.** Commit `1fa8437` and migration `0030` are already on `feature/2.5.63`. `resolve_ms02_pid_ids` is now columnar. `col_pid` IS seeded in `SearchConfig` for `sydoc.05_PDBS`. The button-gone bug is NOT a missing config — it is a JS visibility gate (`syncPreparedBtn` in `_workitems_overview_js.html`).
- **No migration needed.** Next free migration number is `0031`. This feature requires zero schema changes.
- **Template-cache restart REQUIRED** after any edit to `workitems_overview.html` or `_workitems_overview_js.html`. Jinja templates are cached process-lifetime; restart with `nx -u`.
- **TWO Jinja guards must be fixed.** There are two `{% if prepared_import_perm and ms02_active and pid_processes %}` guards in `workitems_overview.html`: one at line ~321 (the `#preparedAuditWrap` div) and one at line ~335 (the `#preparedAuditBanner` div). Both must be updated. If only the first is fixed, the banner `<div>` is absent from the DOM and the post-import `document.getElementById('preparedAuditBanner')` call silently returns null, breaking the success banner.
- **i18n needed.** Four new column header strings plus two banner strings. Wrap with `{{ _('...') }}` / `_('...')`, then run full pybabel cycle (`/nx-i18n`). `test_translations.py` must stay green.
- **CI/TEST has no MS02 engines.** `engine_ms02_docfields_pg` is `None`, `'ms02'` not in `CLIENTS`. All integration tests for `/import_prepared_audit` must continue to expect `400` with `"MS02"` in the error body (MS02 gate fires first). Parser unit tests need no Flask context.
- **Test fixtures:** `app`/`client`/`user_client`/`noperm_client` from `tests/conftest.py`. `workitems_all_perms` is LOCAL to `tests/integration/test_workitems_routes.py`.
- **Session stash breaking change:** old tokens carry a flat `[int, ...]` list. After this deploy, `_get_workitems_data` reads `isinstance(stored, dict)` — old flat-list tokens fall into the legacy branch and produce `pid_import_active=True` with `pid_ids=set()` (empty import, zero rows). Sessions are short-lived so no user impact.
- **`parse_prepared_xlsx` return type change:** from `list[tuple[str, bool]]` to `list[dict]`. The ONLY production caller is `import_prepared_audit` in `nx_lib/views/workitems.py`. Both the parser change and the caller update MUST be in the same commit (Task 2) to prevent a broken intermediate state that would fail the pre-commit test hook.
- **`resolve_ms02_pid_to_wids` contract:** returns `{pid_str: [wid_int, ...]}` for matched PIDs only (unmatched PIDs are absent from the dict). Returns `{}` (not `None`) on zero matches. Returns `None` on engine-absent / empty-specs / empty-pids / error. Unmatched PIDs are detected in `_get_workitems_data` by `pid not in pid_to_wids`. This is a clean two-level contract: `None` = no constraint, `{}` or populated dict = active constraint.
- **Synthetic rows and pagination:** Synthetic rows are appended only when `offset == 0` (page 1 of any fetch). On page 2+ the synthetic rows are absent and `total_items` is not bumped. This is documented as a known limitation in Gotchas. `total_items` is incremented by `len(synthetic_rows)` on page 1 only so the paginator shows the correct total.
- **CSV export guard:** `export_workitems_csv` iterates all workitems and calls `get_domain_for_workitem(wid)` — passing `None` (from a synthetic row) would fail. Filter synthetic rows out in the export path.
- **CSS approach for import-column visibility:** Toggle class `no-import-cols` on `#workitemsTable`. CSS rule `#workitemsTable.no-import-cols .import-col { display: none !important; }` hides all import cells. The CSP in `nx_lib/config.py` already permits `'unsafe-inline'` for `style-src`, so an inline `<style>` block is safe. Add the rule to `workitems_overview.html` (not the JS partial).
- **Pre-commit SQL hook / CRLF:** no SQL changes, so `sql-migrate-int` is a no-op. If CRLF drift blocks a commit, use `SQL_SYNC_SKIP=1 git commit ...` (never `--no-verify`).
- **Deploy.yml:** no new top-level files or directories; no `/XF`/`/XD` changes needed.
- **`resolve_ms02_pid_ids` import:** once `import_prepared_audit` is updated to call `resolve_ms02_pid_to_wids`, the old `resolve_ms02_pid_ids` import in `workitems.py` becomes unused. ruff will flag it (F401). Remove it from the import list in the same commit.
- **Design spec file confirmed:** `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` exists at that exact path.

---

## Decisions locked in

| # | Decision | Detail |
|---|---|---|
| 1 | **Button shows whenever `prepared_import_perm AND ms02_active`.** Decouple from `pid_processes` / selected process filter. | Drop `and pid_processes` from BOTH Jinja guards (`#preparedAuditWrap` and `#preparedAuditBanner`). Delete the `syncPreparedBtn` JS block entirely. Replace with `preparedWrap.classList.remove('hidden')` so the button is visible immediately on page load. Remove `data-pid-processes` attribute. |
| 2 | **Excel is five columns (typo-tolerant).** PID, Collected (0/1 flag), CollectedBy (name), Prepared (0/1 flag — the real-world 4th header `PreparedBy` is a user typo), PreparedBy (name). Parser is case-insensitive, order-agnostic, first-wins for duplicate header occurrences. | Ordered slot scanner: each normalized header key maps to an ordered list of slots it can fill; first unfilled slot wins. `"preparedby"` fills `prepared_flag` first, then `prepared_by`. Return type changes from `list[tuple[str, bool]]` to `list[dict]` with keys `pid/collected/collected_by/prepared/prepared_by`. Route caller updated in the same commit. |
| 3 | **New `resolve_ms02_pid_to_wids` sibling function; old `resolve_ms02_pid_ids` kept.** | `resolve_ms02_pid_to_wids(engine, specs, pid_values) -> dict[str, list[int]] \| None`. Reuses `_ms02_columnar_sql` / `_MS02_IDENT` / `_as_workitem_ids` — does NOT duplicate identifier-safety logic. Projects `SELECT DISTINCT "pid_col"::text, "id_col"` and groups by pid. Returns matched PIDs only (unmatched absent). The old flat-union `resolve_ms02_pid_ids` stays in place. Its import is removed from `workitems.py` once the route no longer calls it. |
| 4 | **Unmatched PIDs become synthetic rows; matched PIDs merge.** | Synthetic rows have `workitemid: None`, `synthetic: True`, the four import values, minimal stub fields. They are appended by `_get_workitems_data` **only on page 1** (`offset == 0`) and counted in `total_items`. Matched PIDs have `pid_import: {collected, collected_by, prepared, prepared_by}` merged onto their real row dicts. Column visibility toggled by `no-import-cols` CSS class on `#workitemsTable`. Synthetic rows suppressed in the CSV export. |

---

## Owner actions

No blocking actions required before execution. Once deployed, the owner should confirm that the `Collected`, `CollectedBy`, `PreparedBy` column values in the real Excel match the parser's expectations (flag vs. name by position) — the parser uses positional first-wins and the example row confirms the mapping.

---

# PHASE 1 — Button fix (smallest change, zero backend impact)

### Task 1: Remove per-process JS gate; fix both Jinja guards

**Files:**
- `templates/workitems_overview.html` — fix TWO `{% if ... and pid_processes %}` guards; remove `data-pid-processes` attribute; keep `class="inline-block hidden"` (JS immediately removes `hidden` on load)
- `templates/js/_workitems_overview_js.html` — replace `syncPreparedBtn` block with `preparedWrap.classList.remove('hidden')`

**Interfaces:**
- Consumes: `prepared_import_perm: bool`, `ms02_active: bool` from the view context (already passed, no view change needed)
- Produces: `#preparedAuditWrap` visible; `#preparedAuditBanner` present in DOM

**Steps:**

- [ ] **Step 1a: Write a failing integration test**

Add to `tests/integration/test_workitems_routes.py` (after the existing `test_import_prepared_audit_*` group):

```python
def test_prepared_audit_wrap_renders_without_pid_processes(user_client, workitems_all_perms, monkeypatch):
    """Button wrapper renders when perm+ms02_active even if pid_processes is empty."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS
    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    resp = user_client.get("/workitems")
    assert resp.status_code == 200
    assert b"preparedAuditWrap" in resp.data
    assert b"preparedAuditBanner" in resp.data
```

- [ ] **Step 1b: Run it red**

```
python -m pytest tests/integration/test_workitems_routes.py::test_prepared_audit_wrap_renders_without_pid_processes -v
```

Expected: `AssertionError` — neither `preparedAuditWrap` nor `preparedAuditBanner` is rendered because `pid_processes` is `[]` in CI.

- [ ] **Step 1c: Fix the first Jinja guard in `workitems_overview.html`**

Find:
```
{% if prepared_import_perm and ms02_active and pid_processes %}
          <div class="inline-block hidden" id="preparedAuditWrap"
            data-pid-processes='{{ pid_processes | tojson }}'>
```

Replace with:
```
{% if prepared_import_perm and ms02_active %}
          <div class="inline-block hidden" id="preparedAuditWrap">
```

- [ ] **Step 1d: Fix the second Jinja guard in `workitems_overview.html`**

Find:
```
      {% if prepared_import_perm and ms02_active and pid_processes %}
      <div id="preparedAuditBanner"
```

Replace with:
```
      {% if prepared_import_perm and ms02_active %}
      <div id="preparedAuditBanner"
```

- [ ] **Step 1e: Fix the JS in `_workitems_overview_js.html`**

Find this exact block:
```javascript
            const preparedWrap = document.getElementById('preparedAuditWrap');
            if (preparedWrap) {
                const pidProcesses = JSON.parse(preparedWrap.dataset.pidProcesses || '[]');
                const procSelEl = document.getElementById('prcfW');
                const syncPreparedBtn = () => preparedWrap.classList.toggle(
                    'hidden', !pidProcesses.includes(procSelEl?.value || 'all'));
                procSelEl?.addEventListener('change', syncPreparedBtn);
                syncPreparedBtn();
            }
```

Replace with:
```javascript
            const preparedWrap = document.getElementById('preparedAuditWrap');
            if (preparedWrap) {
                preparedWrap.classList.remove('hidden');
            }
```

- [ ] **Step 1f: Run the test green**

```
python -m pytest tests/integration/test_workitems_routes.py::test_prepared_audit_wrap_renders_without_pid_processes -v
```

- [ ] **Step 1g: Run full integration suite to confirm no regressions**

```
python -m pytest tests/integration/test_workitems_routes.py -v 2>&1 | tail -30
```

- [ ] **Step 1h: Commit**

```
git add templates/workitems_overview.html templates/js/_workitems_overview_js.html tests/integration/test_workitems_routes.py
git commit -m "$(cat <<'EOF'
fix(workitems): show prepared-import button whenever ms02_active, not per-process

Drop the per-process JS gate (syncPreparedBtn) that kept #preparedAuditWrap
hidden unless the selected process filter matched pid_processes. Fix BOTH
Jinja guards (one for #preparedAuditWrap, one for #preparedAuditBanner) from
`prepared_import_perm and ms02_active and pid_processes` to just
`prepared_import_perm and ms02_active`. Remove data-pid-processes attribute.
The button is now visible on page load whenever perms+ms02_active pass.
Unmatched PIDs will become synthetic rows (next task), making the button
useful regardless of the selected process filter (Decision #3).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 2 — Parser + route: 5-column Excel + richer session payload

### Task 2: Extend `parse_prepared_xlsx` to 5 columns AND update `import_prepared_audit` in the same commit

**Files:**
- `nx_lib/workitem_sources.py` — replace `parse_prepared_xlsx` entirely; add `resolve_ms02_pid_to_wids` after `resolve_ms02_pid_ids`
- `nx_lib/views/workitems.py` — update `import_prepared_audit` to use dict output + call `resolve_ms02_pid_to_wids`; remove unused `resolve_ms02_pid_ids` import
- `tests/unit/test_prepared_xlsx_parser.py` — update existing tuple-access tests to dict access; add new 5-column tests
- `tests/unit/test_workitem_sources.py` — add `resolve_ms02_pid_to_wids` unit tests

**Rationale for combining into one commit:** `parse_prepared_xlsx` changes its return type from `list[tuple]` to `list[dict]`. The ONLY production caller is `import_prepared_audit`. If parser and caller are committed separately, the pre-commit hook runs the test suite between commits, which would fail because `pids = [pid for pid, _prep in pairs]` breaks on `list[dict]`. Both changes must land together.

**Interfaces:**

`parse_prepared_xlsx(data) -> (list[dict], str | None)` — each dict: `{pid: str, collected: bool, collected_by: str, prepared: bool, prepared_by: str}`. Backward-compatible: 2-column files return dicts with `collected=False`, `collected_by=""`, `prepared_by=""`.

`resolve_ms02_pid_to_wids(engine, specs, pid_values) -> dict[str, list[int]] | None` — three-way contract: `None` = no constraint (engine absent / no specs / no pids / error), `{}` = zero matches, `{pid: [wid, ...]}` = matched PIDs only (unmatched absent from dict).

`import_prepared_audit` session stash changes from `[int, ...]` to `{ids: [int,...], pid_to_wids: {pid: [wid,...]}, payloads: {pid: {collected, collected_by, prepared, prepared_by}}}`. JSON response key `"prepared"` renamed to `"payloads"`.

**Steps:**

- [ ] **Step 2a: Update existing parser tests to dict access (run BEFORE changing the implementation)**

In `tests/unit/test_prepared_xlsx_parser.py`, update every test that uses tuple unpacking. The existing `_xlsx` fixture helper stays unchanged (it builds a 2-column workbook). Update the assertions:

```python
def test_parses_pid_and_prepared():
    rows, err = ws.parse_prepared_xlsx(_xlsx([("100", True), ("200", False)]))
    assert err is None
    assert [(r["pid"], r["prepared"]) for r in rows] == [("100", True), ("200", False)]


def test_header_detection_is_case_insensitive_and_order_agnostic():
    data = _xlsx([(True, "  300 ")], headers=("prepared", "pid"))
    rows, err = ws.parse_prepared_xlsx(data)
    assert err is None
    assert rows[0]["pid"] == "300"
    assert rows[0]["prepared"] is True


def test_integer_pid_does_not_get_trailing_dot_zero():
    rows, err = ws.parse_prepared_xlsx(_xlsx([(12345, "yes")]))
    assert err is None
    assert rows[0]["pid"] == "12345"
    assert rows[0]["prepared"] is True


def test_blank_rows_and_blank_pids_skipped():
    rows, err = ws.parse_prepared_xlsx(_xlsx([(None, True), ("", False), ("400", "")]))
    assert err is None
    assert len(rows) == 1
    assert rows[0]["pid"] == "400"
    assert rows[0]["prepared"] is False


def test_duplicate_pid_first_wins():
    rows, err = ws.parse_prepared_xlsx(_xlsx([("500", True), ("500", False)]))
    assert rows[0]["pid"] == "500"
    assert rows[0]["prepared"] is True
    assert len(rows) == 1


def test_row_cap_is_enforced():
    data_rows = [(str(i), True) for i in range(ws._PREPARED_MAX_ROWS + 50)]
    rows, err = ws.parse_prepared_xlsx(_xlsx(data_rows))
    assert err is None
    assert len(rows) == ws._PREPARED_MAX_ROWS


def test_missing_pid_column_returns_error():
    rows, err = ws.parse_prepared_xlsx(_xlsx([("x",)], headers=("Foo", "Prepared")))
    assert rows == []
    assert err is not None


def test_garbage_bytes_returns_error_not_raise():
    rows, err = ws.parse_prepared_xlsx(b"not a workbook")
    assert rows == []
    assert err is not None
```

- [ ] **Step 2b: Add new 5-column tests (still in `test_prepared_xlsx_parser.py`)**

Add a new helper and new tests after the updated existing tests:

```python
def _xlsx5(rows, headers=("PID", "Collected", "CollectedBy", "PreparedBy", "PreparedBy")):
    """Build a 5-column xlsx with the user's real (typo'd) header row."""
    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(list(headers))
    for r in rows:
        sh.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_five_column_full_row():
    rows, err = ws.parse_prepared_xlsx(
        _xlsx5([(30111679, 1, "Guy1", 1, "Girl2")])
    )
    assert err is None
    assert len(rows) == 1
    r = rows[0]
    assert r["pid"] == "30111679"
    assert r["collected"] is True
    assert r["collected_by"] == "Guy1"
    assert r["prepared"] is True
    assert r["prepared_by"] == "Girl2"


def test_duplicate_preparedby_header_first_is_flag_second_is_name():
    """4th col 'PreparedBy' (user typo for flag), 5th col 'PreparedBy' (name)."""
    data = _xlsx5([(99, 0, "Alice", 1, "Bob")])
    rows, err = ws.parse_prepared_xlsx(data)
    assert err is None
    r = rows[0]
    assert r["collected"] is False
    assert r["collected_by"] == "Alice"
    assert r["prepared"] is True
    assert r["prepared_by"] == "Bob"


def test_five_col_case_insensitive_headers():
    data = _xlsx5(
        [("PID1", 0, "Alice", 1, "Bob")],
        headers=("pid", "COLLECTED", "collectedby", "PREPARED", "preparedby"),
    )
    rows, err = ws.parse_prepared_xlsx(data)
    assert err is None
    r = rows[0]
    assert r["collected"] is False
    assert r["collected_by"] == "Alice"
    assert r["prepared"] is True
    assert r["prepared_by"] == "Bob"


def test_five_col_backward_compat_two_column():
    """Two-column file (PID + Prepared only) still parses; extra fields default."""
    rows, err = ws.parse_prepared_xlsx(_xlsx([("777", True), ("888", False)]))
    assert err is None
    assert rows[0]["collected"] is False
    assert rows[0]["collected_by"] == ""
    assert rows[0]["prepared_by"] == ""


def test_five_col_name_columns_stripped():
    data = _xlsx5([(10, 1, "  SpaceGuy  ", 0, "  ")],)
    rows, err = ws.parse_prepared_xlsx(data)
    r = rows[0]
    assert r["collected_by"] == "SpaceGuy"
    assert r["prepared_by"] == ""


def test_five_col_row_cap_enforced():
    data_rows = [(str(i), 1, "a", 0, "b") for i in range(ws._PREPARED_MAX_ROWS + 50)]
    data = _xlsx5(data_rows, headers=("PID", "Collected", "CollectedBy", "Prepared", "PreparedBy"))
    result, err = ws.parse_prepared_xlsx(data)
    assert err is None
    assert len(result) == ws._PREPARED_MAX_ROWS
```

- [ ] **Step 2c: Add `resolve_ms02_pid_to_wids` unit tests (in `tests/unit/test_workitem_sources.py`)**

```python
def test_resolve_ms02_pid_to_wids_returns_none_on_no_engine(app):
    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids
    with app.app_context():
        assert resolve_ms02_pid_to_wids(None, [("t", "id", "pid", None)], ["123"]) is None


def test_resolve_ms02_pid_to_wids_returns_none_on_no_specs(app):
    from unittest.mock import MagicMock
    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids
    with app.app_context():
        assert resolve_ms02_pid_to_wids(MagicMock(), [], ["123"]) is None


def test_resolve_ms02_pid_to_wids_returns_none_on_no_pids(app):
    from unittest.mock import MagicMock
    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids
    with app.app_context():
        assert resolve_ms02_pid_to_wids(MagicMock(), [("t", "id", "pid", None)], []) is None


def test_resolve_ms02_pid_to_wids_groups_by_pid(app):
    from unittest.mock import MagicMock
    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [("30111679", "100"), ("30111679", "200"), ("99999", "300")]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_engine = MagicMock()
    mock_engine.raw_connection.return_value = mock_conn

    with app.app_context():
        result = resolve_ms02_pid_to_wids(
            mock_engine,
            [("DossierStatistik", "WorkItemID", "DossierNummer", None)],
            ["30111679", "99999"],
        )
    assert result is not None
    assert set(result["30111679"]) == {100, 200}
    assert result["99999"] == [300]


def test_resolve_ms02_pid_to_wids_empty_dict_on_no_match(app):
    """Zero DB rows -> empty dict (not None)."""
    from unittest.mock import MagicMock
    from nx_lib.workitem_sources import resolve_ms02_pid_to_wids

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_engine = MagicMock()
    mock_engine.raw_connection.return_value = mock_conn

    with app.app_context():
        result = resolve_ms02_pid_to_wids(
            mock_engine,
            [("DossierStatistik", "WorkItemID", "DossierNummer", None)],
            ["NOTFOUND"],
        )
    assert result == {}
```

- [ ] **Step 2d: Run all new tests red**

```
python -m pytest tests/unit/test_prepared_xlsx_parser.py tests/unit/test_workitem_sources.py -v 2>&1 | tail -40
```

Expected: existing dict-access tests pass (they match the current tuple format via `[(r["pid"], r["prepared"]) for r in rows]` — actually these FAIL against the current tuple output, which is correct: they should all be red now since we updated the assertions before the implementation).

- [ ] **Step 2e: Implement the new `parse_prepared_xlsx` in `nx_lib/workitem_sources.py`**

Replace the entire `parse_prepared_xlsx` function body. Find by its docstring opening:
```python
def parse_prepared_xlsx(data):
    """Parse the MS02 'prepared documents' xlsx into [(pid, prepared_bool), ...].
```

Replace the entire function with:

```python
def parse_prepared_xlsx(data):
    """Parse the MS02 'prepared documents' xlsx into a list of row dicts.

    Columns (case-insensitive, order-agnostic): PID, Collected (bool),
    CollectedBy (name), Prepared (bool), PreparedBy (name). The real-world
    header has a DUPLICATE 'PreparedBy' — the 4th column is the Prepared flag
    (user typo). The parser resolves duplicates by positional first-wins:
    first 'PreparedBy' fills the Prepared flag slot; second fills PreparedBy.

    Backward-compatible: a 2-column file (PID + Prepared) returns dicts with
    collected=False, collected_by='', prepared_by=''.

    Slot assignment: each normalized header key maps to an ordered list of
    slots it can fill (first unfilled slot wins):
      'pid'         -> [pid]
      'collected'   -> [collected_flag]
      'collectedby' -> [collected_by]
      'prepared'    -> [prepared_flag]
      'preparedby'  -> [prepared_flag, prepared_by]   # handles the typo

    Returns (rows, error):
      rows: list[dict] with keys pid/collected/collected_by/prepared/prepared_by;
            deduped on pid (first wins); blanks/blank-pid rows skipped;
            at most _PREPARED_MAX_ROWS rows.
      error: None on success or a short human message on failure. NEVER raises.
    """
    import openpyxl  # local import: openpyxl is heavyish and only used here

    _KEY_TO_SLOTS = {
        "pid":         ["pid"],
        "collected":   ["collected_flag"],
        "collectedby": ["collected_by"],
        "prepared":    ["prepared_flag"],
        "preparedby":  ["prepared_flag", "prepared_by"],
    }

    def _norm_header(cell):
        return str(cell).strip().lower().replace(" ", "").replace("_", "") if cell is not None else ""

    def _to_bool(raw):
        if isinstance(raw, bool):
            return raw
        if raw is None:
            return False
        return str(raw).strip().lower() in _PREPARED_TRUE

    def _to_str(raw):
        if raw is None:
            return ""
        if isinstance(raw, float) and raw.is_integer():
            return str(int(raw))
        return str(raw).strip()

    def _log(msg):
        with contextlib.suppress(RuntimeError):  # no app context in unit tests
            current_app.logger.error(msg)

    wb = None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        _log(f"parse_prepared_xlsx load: {e}")
        return [], "Could not read the Excel file."
    try:
        sh = wb.active
        rows_iter = sh.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            return [], "The Excel file is empty."

        # Build slot -> column_index map (first-wins per slot).
        assigned = {}  # slot -> column index
        for i, cell in enumerate(header or []):
            key = _norm_header(cell)
            for slot in _KEY_TO_SLOTS.get(key, []):
                if slot not in assigned:
                    assigned[slot] = i
                    break

        if "pid" not in assigned:
            return [], "Missing required 'PID' column."

        pid_i = assigned["pid"]
        col_i = assigned.get("collected_flag")
        cby_i = assigned.get("collected_by")
        prep_i = assigned.get("prepared_flag")
        pby_i = assigned.get("prepared_by")

        out = []
        seen = set()
        for row in rows_iter:
            if len(out) >= _PREPARED_MAX_ROWS:
                break
            if row is None:
                continue
            pid = _norm_pid(row[pid_i] if pid_i < len(row) else None)
            if not pid or pid in seen:
                continue
            seen.add(pid)

            def _cell(idx, row=row):
                return row[idx] if idx is not None and idx < len(row) else None

            out.append({
                "pid":          pid,
                "collected":    _to_bool(_cell(col_i)),
                "collected_by": _to_str(_cell(cby_i)),
                "prepared":     _to_bool(_cell(prep_i)),
                "prepared_by":  _to_str(_cell(pby_i)),
            })
        return out, None
    except Exception as e:
        _log(f"parse_prepared_xlsx: {e}")
        return [], "Could not parse the Excel file."
    finally:
        if wb is not None:
            with contextlib.suppress(Exception):
                wb.close()
```

- [ ] **Step 2f: Add `resolve_ms02_pid_to_wids` to `nx_lib/workitem_sources.py`**

Insert this function immediately after the closing `finally` of `resolve_ms02_pid_ids` (find anchor: `if conn is not None:\n            conn.close()` followed by a blank line before `def _pgmarks`):

```python
def resolve_ms02_pid_to_wids(engine, specs, pid_values):
    """Resolve a list of personal-number PIDs to a per-PID workitem-id map
    (columnar). Sibling of resolve_ms02_pid_ids; returns the per-PID mapping
    needed to merge import values onto matched rows and detect unmatched PIDs
    (for synthetic-row generation).

    Reuses _ms02_columnar_sql / _MS02_IDENT / _as_workitem_ids to avoid
    duplicating identifier-safety logic. Projects both the pid and id columns
    by wrapping the columnar SQL: SELECT DISTINCT "pid_col"::text, "id_col".

    Three-way contract (mirrors resolve_ms02_pid_ids):
      * None        -> no constraint (engine absent, no specs, no PIDs, error).
      * {}          -> no PID matched any workitem (zero rows from DB).
      * {pid: [...]}-> matched PIDs only; unmatched PIDs are ABSENT from dict.
    Never raises: on error it logs and returns None.
    """
    if engine is None or not specs or not pid_values:
        return None
    pid_list = [str(p) for p in pid_values]
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        result: dict[str, list[int]] = {}
        for table, id_col, pid_col, time_filter in specs:
            # Validate identifiers using the same _MS02_IDENT guard as
            # _ms02_columnar_sql — keeps security logic in one place.
            if not (table and id_col and pid_col):
                continue
            if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(pid_col)):
                current_app.logger.error(
                    f"resolve_ms02_pid_to_wids: unsafe identifier {(id_col, pid_col)}"
                )
                continue
            sql = (
                f'SELECT DISTINCT "{pid_col}"::text, "{id_col}"'
                f" FROM {table}"
                f' WHERE "{pid_col}"::text = ANY(%s)'
            )
            if time_filter:
                sql += f" AND {time_filter}"
            cur.execute(sql, [pid_list])
            for pid_raw, wid_raw in cur.fetchall():
                pid_str = str(pid_raw) if pid_raw is not None else None
                if not pid_str:
                    continue
                wids = _as_workitem_ids([(wid_raw,)])
                if not wids:
                    continue
                wid = next(iter(wids))
                if pid_str not in result:
                    result[pid_str] = []
                if wid not in result[pid_str]:
                    result[pid_str].append(wid)
        return result
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_pid_to_wids: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step 2g: Update `import_prepared_audit` in `nx_lib/views/workitems.py`**

First, add `resolve_ms02_pid_to_wids` to the import block. Find:
```python
    resolve_ms02_pid_ids,
```
Replace with:
```python
    resolve_ms02_pid_to_wids,
```
(Remove `resolve_ms02_pid_ids` — it is no longer called anywhere in workitems.py.)

Then find the block starting with:
```python
    pids = [pid for pid, _prep in pairs]
    prepared = {pid: prep for pid, prep in pairs}
```
and ending with the closing `), 200` of `return jsonify({"token": token, "prepared": prepared, ...})`.

Replace it with:
```python
    pids = [row["pid"] for row in pairs]
    payloads = {
        row["pid"]: {
            "collected":    row["collected"],
            "collected_by": row["collected_by"],
            "prepared":     row["prepared"],
            "prepared_by":  row["prepared_by"],
        }
        for row in pairs
    }

    pid_specs = _ms02_pid_specs(_ms02_target_processes())
    if not pid_specs:
        return jsonify(
            {
                "token":   None,
                "payloads": {},
                "matched": 0,
                "total":   len(pids),
                "warning": _("The personal-number field is not configured for MS02."),
            }
        ), 200

    pid_to_wids = resolve_ms02_pid_to_wids(engine_ms02_docfields_pg, pid_specs, pids)
    if pid_to_wids is None:
        return jsonify(
            {"error": _("Could not resolve personal numbers against the MS02 index.")}
        ), 500

    # Flat union id-set for the WorkitemFilter.ms02_docfield_ids allow-set seam.
    id_set = {wid for wids in pid_to_wids.values() for wid in wids}
    matched_pids = {pid for pid, wids in pid_to_wids.items() if wids}
    ids = sorted(id_set)

    token = secrets.token_urlsafe(16)
    session[f"pid_import:{token}"] = {
        "ids":         ids,
        "pid_to_wids": {pid: list(wids) for pid, wids in pid_to_wids.items()},
        "payloads":    payloads,
    }
    return jsonify(
        {
            "token":    token,
            "payloads": payloads,
            "matched":  len(matched_pids),
            "total":    len(pids),
        }
    ), 200
```

Also update the docstring at the top of `import_prepared_audit`: change "two-column Excel (PID = personal number, Prepared = informational)" to "five-column Excel (PID, Collected, CollectedBy, Prepared, PreparedBy)".

- [ ] **Step 2h: Run parser and resolver tests green**

```
python -m pytest tests/unit/test_prepared_xlsx_parser.py tests/unit/test_workitem_sources.py -v 2>&1 | tail -40
```

- [ ] **Step 2i: Run full unit + integration suite**

```
python -m pytest tests/unit/ tests/integration/test_workitems_routes.py -v --tb=short 2>&1 | tail -50
```

The existing `test_import_prepared_audit_*` integration tests still pass because the MS02 gate fires at `400` before any payload parsing. The existing `test_pid_ids_intersected_into_ms02_docfield_ids` and `test_pid_ids_intersected_with_existing_ms02_docfield_ids` tests use flat-list session stash (`session["pid_import:tok123"] = [10, 20, 30]`) — these will now hit the legacy `isinstance(stored, dict)` branch producing empty `pid_ids`, causing them to fail. Update those two tests now (see next step).

- [ ] **Step 2j: Update the two flat-list session stash tests in `test_workitems_pid_filter.py`**

Find:
```python
        session["pid_import:tok123"] = [10, 20, 30]
```
Replace with:
```python
        session["pid_import:tok123"] = {"ids": [10, 20, 30], "pid_to_wids": {}, "payloads": {}}
```

Find:
```python
        session["pid_import:tok_intersect"] = [10, 20, 30]
```
Replace with:
```python
        session["pid_import:tok_intersect"] = {"ids": [10, 20, 30], "pid_to_wids": {}, "payloads": {}}
```

- [ ] **Step 2k: Run unit suite again — all green**

```
python -m pytest tests/unit/ -v --tb=short 2>&1 | tail -40
```

- [ ] **Step 2l: ruff**

```
ruff check nx_lib/workitem_sources.py nx_lib/views/workitems.py && ruff format nx_lib/workitem_sources.py nx_lib/views/workitems.py
```

- [ ] **Step 2m: Commit (parser + resolver + route caller all in one commit)**

```
git add nx_lib/workitem_sources.py nx_lib/views/workitems.py tests/unit/test_prepared_xlsx_parser.py tests/unit/test_workitem_sources.py tests/unit/test_workitems_pid_filter.py
git commit -m "$(cat <<'EOF'
feat(workitems): 5-col xlsx parser + per-PID resolver + richer session payload

parse_prepared_xlsx now accepts PID, Collected (flag), CollectedBy (name),
Prepared (flag), PreparedBy (name). Tolerates the real-world duplicate
'PreparedBy' header (4th col = Prepared flag; 5th = PreparedBy name) via
ordered first-wins slot assignment. Return type changes from list[tuple] to
list[dict] (pid/collected/collected_by/prepared/prepared_by). Backward-
compatible: 2-col files default extra fields to False/''.

New resolve_ms02_pid_to_wids returns {pid: [wid,...]} for matched PIDs
(unmatched absent). Reuses _ms02_columnar_sql/_MS02_IDENT/_as_workitem_ids.

import_prepared_audit updated: uses dict parser output, calls
resolve_ms02_pid_to_wids, stashes {ids, pid_to_wids, payloads} in session
(was flat int list), returns payloads key (was prepared). resolve_ms02_pid_ids
import removed from workitems.py (unused after this change).

Session tests updated to new dict stash format.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 3 — `_get_workitems_data`: merge + synthetic rows

### Task 3: Update `_get_workitems_data` to merge import values and append synthetic rows

**Files:**
- `nx_lib/views/workitems.py` — `_get_workitems_data`
- `tests/unit/test_workitems_pid_filter.py` — new tests for merge + synthetic row logic

**Interfaces:**

`_get_workitems_data` return dict gains no new top-level keys visible to the template; the extra fields (`pid_import`, `synthetic`, `pid`) are grafted onto individual row dicts. The existing `"workitems"` list now may contain synthetic rows (when `offset == 0` and unmatched PIDs exist).

Row dict shape for synthetic rows:
```python
{
    "workitemid": None, "synthetic": True, "pid": "<pid_str>",
    "pid_import": {"collected": bool, "collected_by": str, "prepared": bool, "prepared_by": str},
    "modifiedat": None, "status": None, "current_stage": None,
    "priority": None, "tags": [], "client": None,
}
```

Matched real rows gain: `"pid_import": {"collected": bool, "collected_by": str, "prepared": bool, "prepared_by": str}`.

**Steps:**

- [ ] **Step 3a: Write failing unit tests**

Add to `tests/unit/test_workitems_pid_filter.py`:

```python
def test_richer_stash_pid_ids_loaded_correctly(app):
    """New dict stash: ids key drives the allow-set."""
    captured = {}

    def fake_fetch(filt, offset, limit):
        captured["filt"] = filt
        return [], 0, []

    with app.test_request_context():
        from flask import session
        session["pid_import:tok_rich"] = {
            "ids": [10, 20, 30],
            "pid_to_wids": {"p1": [10]},
            "payloads": {"p1": {"collected": True, "collected_by": "A", "prepared": False, "prepared_by": ""}},
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            wv._get_workitems_data(MultiDict([("pidImport", "tok_rich")]))
    assert captured["filt"].ms02_docfield_ids == {10, 20, 30}
    assert captured["filt"].pid_import_active is True


def test_import_payload_merged_onto_matched_row(app):
    """Rows whose workitemid appears in pid_to_wids get pid_import grafted in."""
    matched_row = {
        "workitemid": 10, "status": "Done", "modifiedat": None,
        "priority": 0, "tags": [], "current_stage": "", "client": "ms02",
    }

    def fake_fetch(filt, offset, limit):
        return [matched_row], 1, []

    with app.test_request_context():
        from flask import session
        session["pid_import:tok_merge"] = {
            "ids": [10],
            "pid_to_wids": {"999": [10]},
            "payloads": {"999": {"collected": True, "collected_by": "Guy1", "prepared": True, "prepared_by": "Girl2"}},
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_merge")]))

    workitems = result["workitems"]
    assert len(workitems) == 1
    imp = workitems[0].get("pid_import")
    assert imp is not None
    assert imp["collected"] is True
    assert imp["collected_by"] == "Guy1"
    assert imp["prepared"] is True
    assert imp["prepared_by"] == "Girl2"


def test_unmatched_pid_becomes_synthetic_row_on_page_1(app):
    """PIDs with no wids -> synthetic row appended (offset=0 = page 1)."""
    def fake_fetch(filt, offset, limit):
        return [], 0, []

    with app.test_request_context():
        from flask import session
        session["pid_import:tok_synthetic"] = {
            "ids": [],
            "pid_to_wids": {},  # empty: no PID resolved to any workitem
            "payloads": {"77777": {"collected": False, "collected_by": "", "prepared": True, "prepared_by": "Bob"}},
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_synthetic")]))

    workitems = result["workitems"]
    assert len(workitems) == 1
    syn = workitems[0]
    assert syn.get("synthetic") is True
    assert syn["pid"] == "77777"
    assert syn["pid_import"]["prepared_by"] == "Bob"
    assert result["pagination"]["totalItems"] == 1


def test_synthetic_rows_not_appended_on_page_2(app):
    """offset > 0 (page 2+): no synthetic rows appended."""
    def fake_fetch(filt, offset, limit):
        return [], 0, []

    with app.test_request_context():
        from flask import session
        session["pid_import:tok_p2"] = {
            "ids": [],
            "pid_to_wids": {},
            "payloads": {"55555": {"collected": False, "collected_by": "", "prepared": False, "prepared_by": ""}},
        }
        with (
            patch.object(wv, "fetch_merged_page", side_effect=fake_fetch),
            patch.object(wv, "has_permission", return_value=True),
        ):
            # page=2 -> offset = (2-1)*40 = 40
            result = wv._get_workitems_data(MultiDict([("pidImport", "tok_p2"), ("page", "2")]))

    assert result["workitems"] == []
    assert result["pagination"]["totalItems"] == 0
```

- [ ] **Step 3b: Run failing**

```
python -m pytest tests/unit/test_workitems_pid_filter.py -v -k "richer_stash or merged_onto or synthetic" 2>&1 | tail -30
```

- [ ] **Step 3c: Implement the changes in `_get_workitems_data`**

Find the pid_token block:
```python
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
        ms02_docfield_ids = pid_ids if ms02_docfield_ids is None else ms02_docfield_ids & pid_ids
```

Replace with:
```python
    pid_import_active = False
    _pid_import_meta = None  # {pid_to_wids, payloads} for row enrichment
    pid_token = args.get("pidImport", "").strip()
    if pid_token:
        pid_import_active = True
        stored = session.get(f"pid_import:{pid_token}")
        pid_ids = set()
        if isinstance(stored, dict):
            # New richer payload: {ids, pid_to_wids, payloads}
            for raw in stored.get("ids") or []:
                try:
                    pid_ids.add(int(raw))
                except (TypeError, ValueError):
                    continue
            _pid_import_meta = {
                "pid_to_wids": stored.get("pid_to_wids") or {},
                "payloads":    stored.get("payloads") or {},
            }
        elif isinstance(stored, list):
            # Legacy flat list (pre-deploy session token): degrade gracefully.
            for raw in stored:
                try:
                    pid_ids.add(int(raw))
                except (TypeError, ValueError):
                    continue
        ms02_docfield_ids = pid_ids if ms02_docfield_ids is None else ms02_docfield_ids & pid_ids
```

Then find:
```python
    rows, total_items, degraded = fetch_merged_page(filt, offset, per_page)
    workitems_list = rows
```

Replace with:
```python
    rows, total_items, degraded = fetch_merged_page(filt, offset, per_page)
    workitems_list = list(rows)

    if pid_import_active and _pid_import_meta:
        pid_to_wids = _pid_import_meta["pid_to_wids"]
        payloads = _pid_import_meta["payloads"]
        # Reverse map: wid_int -> pid_str for O(1) row merge lookup.
        wid_to_pid = {
            wid: pid
            for pid, wids in pid_to_wids.items()
            for wid in wids
        }
        # Merge import values onto matched real rows.
        for row in workitems_list:
            wid = row.get("workitemid")
            if wid is not None and wid in wid_to_pid:
                pid = wid_to_pid[wid]
                row["pid_import"] = payloads.get(pid)

        # Append synthetic rows for unmatched PIDs — PAGE 1 ONLY (offset == 0).
        # On page 2+ the paginator already accounts for them in total_items;
        # re-appending would inflate the count and duplicate the rows.
        if offset == 0:
            matched_pids = set(pid_to_wids.keys())  # all PIDs that have ANY wid match
            for pid, pid_payld in payloads.items():
                if pid not in matched_pids:
                    workitems_list.append({
                        "workitemid":    None,
                        "synthetic":     True,
                        "pid":           pid,
                        "pid_import":    pid_payld,
                        "modifiedat":    None,
                        "status":        None,
                        "current_stage": None,
                        "priority":      None,
                        "tags":          [],
                        "client":        None,
                    })
            n_synthetic = sum(1 for pid in payloads if pid not in matched_pids)
            total_items += n_synthetic
```

Also guard synthetic rows from the CSV export. Find the block in `export_workitems_csv`:
```python
    if specific_ids:
        workitems = [w for w in workitems if w["workitemid"] in specific_ids]
```

Replace with:
```python
    workitems = [w for w in workitems if not w.get("synthetic")]
    if specific_ids:
        workitems = [w for w in workitems if w["workitemid"] in specific_ids]
```

- [ ] **Step 3d: Run tests green**

```
python -m pytest tests/unit/test_workitems_pid_filter.py -v 2>&1 | tail -30
```

- [ ] **Step 3e: Run full unit + integration suite**

```
python -m pytest tests/unit/ tests/integration/test_workitems_routes.py -v --tb=short 2>&1 | tail -50
```

- [ ] **Step 3f: ruff**

```
ruff check nx_lib/views/workitems.py && ruff format nx_lib/views/workitems.py
```

- [ ] **Step 3g: Commit**

```
git add nx_lib/views/workitems.py tests/unit/test_workitems_pid_filter.py
git commit -m "$(cat <<'EOF'
feat(workitems): merge pid-import values onto rows + synthetic rows for unmatched PIDs

_get_workitems_data reads the richer {ids, pid_to_wids, payloads} session
stash. Matched real rows get row['pid_import'] = {collected, collected_by,
prepared, prepared_by}. Unmatched PIDs (absent from pid_to_wids) become
synthetic rows appended on page 1 only (offset==0) to avoid pagination
inflation on subsequent fetches. total_items bumped by synthetic count.
Legacy flat-list tokens degrade gracefully (empty pid_ids, no synthetic rows).
CSV export filters synthetic rows out before iterating workitem ids.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 4 — Template + JS: extra columns + synthetic rows display

### Task 4: Add import column headers to the table; add CSS toggle

**Files:**
- `templates/workitems_overview.html` — add 4 hidden `<th class="import-col">` elements; add `no-import-cols` initial class to `<table>`; add `<style>` block for the CSS toggle rule; keep spinner colspan at 7

**Steps:**

- [ ] **Step 4a: Add CSS rule and initial `no-import-cols` class**

Find:
```html
          <table class="nx-table" id="workitemsTable">
```
Replace with:
```html
          <table class="nx-table no-import-cols" id="workitemsTable">
```

Add a `<style>` block immediately above the `<table>` line (the CSP in `nx_lib/config.py` already allows `'unsafe-inline'` for `style-src`):
```html
          <style>
            #workitemsTable.no-import-cols .import-col { display: none !important; }
          </style>
          <table class="nx-table no-import-cols" id="workitemsTable">
```

- [ ] **Step 4b: Add 4 hidden `<th>` elements before the Details column**

Find:
```html
                <th scope="col" class="relative px-6 py-3">
                  <span class="sr-only">Details</span>
                </th>
              </tr>
            </thead>
```
Replace with:
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
                <th scope="col" class="relative px-6 py-3">
                  <span class="sr-only">Details</span>
                </th>
              </tr>
            </thead>
```

Note: leave the spinner `<td colspan="7">` as-is — it is replaced immediately by JS `renderTable` and the visual artifact is imperceptible. The dynamic colspan is handled in the JS.

- [ ] **Step 4c: No test for pure template markup** — covered by the integration test added in Task 1 and by the JS rendering in Task 5.

- [ ] **Step 4d: Commit**

```
git add templates/workitems_overview.html
git commit -m "$(cat <<'EOF'
feat(workitems): add hidden import column headers (Collected/Prepared/by/by)

Four extra <th class="import-col"> cells before the Details column.
Visibility controlled by CSS class 'no-import-cols' on #workitemsTable
(initially set; removed by JS when a prepared-import is active).
The CSP already permits 'unsafe-inline' style-src. i18n strings extracted
and translated in the next i18n commit.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

### Task 5: JS — column visibility toggle, extra cells, synthetic rows

**Files:**
- `templates/js/_workitems_overview_js.html` — add `setImportColsVisible` helper; update `uploadPreparedAudit` and banner-clear handler; extend `renderTable` with import `<td>` cells and synthetic row branch; update `activePidToken` set/clear paths; fix `details-row` colspan

**Steps:**

- [ ] **Step 5a: Add `setImportColsVisible` helper after `activePidToken` declaration**

Find:
```javascript
            let activePidToken = null;  // null = no PID filter; set = filter active
```
After that line, add:
```javascript
            // Toggle the 4 import columns by toggling 'no-import-cols' on the table.
            function setImportColsVisible(visible) {
                const tbl = document.getElementById('workitemsTable');
                if (tbl) tbl.classList.toggle('no-import-cols', !visible);
            }
```

- [ ] **Step 5b: Update `uploadPreparedAudit` — show columns on success, use `data.payloads`**

Find:
```javascript
                    activePidToken = data.token || null;
                    const banner = document.getElementById('preparedAuditBanner');
                    const text = document.getElementById('preparedAuditBannerText');
                    if (banner && text) {
                        let msg = `{{ _("Matched") }} ${data.matched} / ${data.total} {{ _("PIDs") }}.`;
                        if (data.warning) msg += ' ' + data.warning;
```
Replace with:
```javascript
                    activePidToken = data.token || null;
                    if (activePidToken) setImportColsVisible(true);
                    const banner = document.getElementById('preparedAuditBanner');
                    const text = document.getElementById('preparedAuditBannerText');
                    if (banner && text) {
                        const unmatched = data.total - data.matched;
                        let msg = `{{ _("Matched") }} ${data.matched} / ${data.total} {{ _("PIDs") }}.`;
                        if (unmatched > 0) msg += ` ${unmatched} {{ _("unmatched — shown as synthetic rows.") }}`;
                        if (data.warning) msg += ' ' + data.warning;
```

- [ ] **Step 5c: Update banner-clear handler — hide columns**

Find:
```javascript
                bannerClear.addEventListener('click', () => {
                    activePidToken = null;
                    const b = document.getElementById('preparedAuditBanner');
                    if (b) b.classList.add('hidden');
                    fetchAndUpdateWorkitems(1);  // reload unfiltered
                });
```
Replace with:
```javascript
                bannerClear.addEventListener('click', () => {
                    activePidToken = null;
                    setImportColsVisible(false);
                    const b = document.getElementById('preparedAuditBanner');
                    if (b) b.classList.add('hidden');
                    fetchAndUpdateWorkitems(1);  // reload unfiltered
                });
```

- [ ] **Step 5d: Update `renderTable` — sync column state + import cells + synthetic rows + colspan**

At the very start of `renderTable`, sync the column visibility. Find:
```javascript
            function renderTable(workitems) {
                const tbody = document.getElementById('workitemsTbody');
                tbody.innerHTML = '';
```
Replace with:
```javascript
            function renderTable(workitems) {
                setImportColsVisible(activePidToken !== null);
                const tbody = document.getElementById('workitemsTbody');
                tbody.innerHTML = '';
```

Update the empty-state colspan. Find:
```javascript
                    tbody.innerHTML = `
                        <tr><td colspan="7">
```
Replace with:
```javascript
                    const emptyColspan = activePidToken ? 11 : 7;
                    tbody.innerHTML = `
                        <tr><td colspan="${emptyColspan}">
```

Update the `workitems.forEach` to branch on `workitem.synthetic` and add import `<td>` cells. Find the opening of the forEach:
```javascript
                workitems.forEach(workitem => {
                    const statusBadge = {
```
Replace with:
```javascript
                workitems.forEach(workitem => {
                    // --- SYNTHETIC ROW (unmatched PID from import) ---
                    if (workitem.synthetic) {
                        const imp = workitem.pid_import || {};
                        const bool2icon = v => v ? '<i class="fas fa-check text-green-600"></i>' : '<span class="text-gray-400">—</span>';
                        const str2cell = v => (v && v.trim()) ? v : '<span class="text-gray-400">—</span>';
                        const syntheticRow = `
                         <tr class="workitem-row workitem-row--synthetic bg-amber-50 italic" data-status="">
                            <td class="px-4 py-4 text-center w-10"></td>
                            <td class="px-6 py-4 whitespace-nowrap text-center text-amber-700 nx-mono font-medium">${workitem.pid || '—'}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center">
                                <span class="text-xs text-gray-400">{{ _("No match") }}</span>
                            </td>
                            <td class="px-6 py-4"></td>
                            <td class="px-6 py-4"></td>
                            <td class="px-6 py-4"></td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${bool2icon(imp.collected)}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${str2cell(imp.collected_by)}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${bool2icon(imp.prepared)}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${str2cell(imp.prepared_by)}</td>
                            <td class="px-6 py-4"></td>
                         </tr>
                        `;
                        tbody.insertAdjacentHTML('beforeend', syntheticRow);
                        return;
                    }

                    const statusBadge = {
```

Now add import `<td>` cells to the normal row. Find the block ending the normal rowHtml (the details-toggle button and the details-row):
```javascript
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-right">
                            <button class="details-toggle-button text-indigo-600 hover:text-indigo-900"
                                data-workitemid="${workitem.workitemid}" data-testid="workitems-details-toggle-${workitem.workitemid}">
                                <i class="indicator fas fa-chevron-down"></i>
                            </button>
                        </td>
                    </tr>
                    <tr id="details-row-${workitem.workitemid}" class="details-row" hidden
                        data-status="${workitem.status}"
                        data-current-stage="${workitem.current_stage || ''}"><td colspan="7"></td></tr>
```
Replace with:
```javascript
                        ${(() => {
                            const imp = workitem.pid_import || null;
                            const bool2icon = v => v ? '<i class="fas fa-check text-green-600"></i>' : '<span class="text-gray-400">—</span>';
                            const str2cell = v => (v && v.trim()) ? v : '<span class="text-gray-400">—</span>';
                            return imp ? `
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${bool2icon(imp.collected)}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${str2cell(imp.collected_by)}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${bool2icon(imp.prepared)}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center import-col">${str2cell(imp.prepared_by)}</td>
                            ` : `
                            <td class="import-col"></td>
                            <td class="import-col"></td>
                            <td class="import-col"></td>
                            <td class="import-col"></td>
                            `;
                        })()}
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-right">
                            <button class="details-toggle-button text-indigo-600 hover:text-indigo-900"
                                data-workitemid="${workitem.workitemid}" data-testid="workitems-details-toggle-${workitem.workitemid}">
                                <i class="indicator fas fa-chevron-down"></i>
                            </button>
                        </td>
                    </tr>
                    <tr id="details-row-${workitem.workitemid}" class="details-row" hidden
                        data-status="${workitem.status}"
                        data-current-stage="${workitem.current_stage || ''}"><td colspan="${activePidToken ? 11 : 7}"></td></tr>
```

- [ ] **Step 5e: Run full Python test suite**

```
python -m pytest tests/unit/ tests/integration/ --ignore=tests/e2e -v --tb=short 2>&1 | tail -50
```

Expected: all PASS. (JS changes are not unit-tested in Python; the Python layer tests cover the data shape.)

- [ ] **Step 5f: Restart dev server and spot-check** (remote session: capture a screenshot and send it)

```
nx -u
```

Open `/workitems` as a user with `workitems.import.preparedaudit`. The "Import" button (prepared audit) should now be visible immediately without selecting a process. Upload a test 5-column xlsx and verify the four extra columns appear with check/dash icons and the matched PID values. Save screenshot to `var/screenshots/prepared-import-5col.png` and send it.

- [ ] **Step 5g: Commit**

```
git add templates/js/_workitems_overview_js.html
git commit -m "$(cat <<'EOF'
feat(workitems): JS render 4 import columns + synthetic rows during pid import

setImportColsVisible toggles 'no-import-cols' on #workitemsTable (CSS approach,
no per-cell class toggling). renderTable branches on workitem.synthetic for
unmatched-PID synthetic rows (amber italic, no checkbox/details). Real rows
get 4 import-col <td> cells with check/dash icons and name values when
pid_import is present. details-row colspan updated to 11 during active import.
uploadPreparedAudit adds unmatched-count to banner text; banner-clear hides
columns. renderTable syncs column state at the top of every call.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 5 — i18n, docs, CHANGELOG

### Task 6: i18n — extract, translate, compile

**Files:**
- `translations/de/LC_MESSAGES/messages.po`
- `translations/fr/LC_MESSAGES/messages.po`
- `translations/it/LC_MESSAGES/messages.po`

New msgids from Phase 4 templates:

| msgid | de | fr | it |
|-------|----|----|-----|
| `Collected` | `Eingegangen` | `Collecté` | `Raccolto` |
| `Collected by` | `Eingegangen durch` | `Collecté par` | `Raccolto da` |
| `Prepared` | `Vorbereitet` | `Préparé` | `Preparato` |
| `Prepared by` | `Vorbereitet durch` | `Préparé par` | `Preparato da` |
| `No match` | `Kein Treffer` | `Aucune correspondance` | `Nessuna corrispondenza` |
| `unmatched — shown as synthetic rows.` | `ohne Treffer — als synthetische Zeilen dargestellt.` | `sans correspondance — affichés comme lignes synthétiques.` | `senza corrispondenza — mostrati come righe sintetiche.` |

Note: German `Prepared → Vorbereitet` (not `Bereit`, which means "Ready" and is already used for workitem status). Using `Bereit` would create a meaning collision.

**Steps:**

- [ ] **Step 6a: Run pybabel extract and update**

```
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 6b: Add translations in de/fr/it .po files** — edit the three `.po` files to add the 6 new msgids from the table above. Remove any `#, fuzzy` markers from the new entries before compiling.

- [ ] **Step 6c: Compile**

```
pybabel compile -d translations
```

- [ ] **Step 6d: Verify translations test**

```
python -m pytest tests/unit/test_translations.py -v 2>&1 | tail -20
```

- [ ] **Step 6e: Commit**

```
git add messages.pot translations/
git commit -m "$(cat <<'EOF'
feat(i18n): add prepared-import column header translations (de/fr/it)

New msgids: Collected, Collected by, Prepared (→ Vorbereitet/Préparé/Preparato,
not Bereit which is used for workitem status), Prepared by, No match, unmatched
synthetic-rows banner fragment. Full de/fr/it coverage.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

### Task 7: CHANGELOG + CLAUDE.md + design spec

**Files:**
- `CHANGELOG.md`
- `CLAUDE.md` (repo-level, in `C:\dev\nexora`)
- `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md`

**Steps:**

- [ ] **Step 7a: Update `CHANGELOG.md`**

Under `## [Unreleased]`, in `### Changed`, find the existing button-visibility entry:
```
- Workitems list: the MS02 "Prepared documents" upload button (and its banner) now appear **only when the selected process filter is one the PID import actually applies to**
```
Replace it with:
```
- Workitems list: the MS02 "Prepared documents" upload button is now visible whenever the user holds `workitems.import.preparedaudit` AND MS02 is active — decoupled from the selected process filter. Previously the per-process JS gate (`syncPreparedBtn`) kept the button hidden on "All Processes" (the default filter), so it was effectively never visible. The gate is removed; both Jinja guards updated.
```

Under `### Added`, find the existing prepared-documents bullet (beginning `- **MS02 'prepared documents' Excel import (workitems).**`). Append to it (or replace it):
```
- **MS02 'prepared documents' Excel import — extended to 5-column format.** The Excel now accepts PID, Collected (0/1 flag), CollectedBy (name), Prepared (0/1 flag), PreparedBy (name) — tolerates the duplicate 'PreparedBy' header typo (4th col = Prepared flag; 5th = PreparedBy name) via positional first-wins slot assignment. Four extra columns (Collected / Collected by / Prepared / Prepared by) appear in the workitems table during an active import. Matched PIDs merge imported values onto existing rows; unmatched PIDs appear as synthetic rows (amber italic, no audit link). Session payload changed from a flat id-list to `{ids, pid_to_wids, payloads}`. New `resolve_ms02_pid_to_wids` per-PID map resolver. Gated by `workitems.import.preparedaudit` (migration `0029`).
```

- [ ] **Step 7b: Update `CLAUDE.md` (repo-level)**

Find the sentence:
```
personal-number (PID) import**: `resolve_ms02_pid_ids` (sibling to `resolve_ms02_docfield_ids`, the personal-number `"Name"`(s) matched against MANY exact PIDs via `= ANY`) and the `/import_prepared_audit` route turn an uploaded two-column Excel (PID/Prepared) into the same `ms02_docfield_ids` allow-set (handed to the list via a session token, not the URL), listing the matched workitems so their full Octo audit can be reviewed.
```
Replace with:
```
personal-number (PID) import**: `resolve_ms02_pid_to_wids` (per-PID map resolver; sibling to `resolve_ms02_pid_ids`) and the `/import_prepared_audit` route turn an uploaded five-column Excel (PID/Collected/CollectedBy/Prepared/PreparedBy — duplicate 'PreparedBy' header tolerated via positional first-wins slot assignment) into a per-PID workitem-id map stashed in the session. Matched PIDs merge imported values (Collected/CollectedBy/Prepared/PreparedBy) onto their existing rows; unmatched PIDs appear as synthetic rows in the list. The upload button is visible whenever the user holds `workitems.import.preparedaudit` AND `ms02_active` — independent of the process filter. Gated by `workitems.import.preparedaudit` (migration `0029`).
```

- [ ] **Step 7c: Update design spec**

In `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md`, find the sentence:
```
The same EAV index and `engine_ms02_docfields_pg` connection also back the PID-list import (`resolve_ms02_pid_ids` / `/import_prepared_audit`), which resolves personal-number PIDs to workitem ids via exact `= ANY` matching against the `col_pid` `SearchConfig` field (migration `0029`, perm `workitems.import.preparedaudit`).
```
Replace with:
```
The same columnar index and `engine_ms02_docfields_pg` connection also back the PID-list import (`resolve_ms02_pid_to_wids` / `/import_prepared_audit`), which resolves personal-number PIDs to a per-PID workitem-id map via exact `= ANY` matching against the `col_pid` `SearchConfig` field (migration `0029`, perm `workitems.import.preparedaudit`). The import accepts a five-column Excel (PID/Collected/CollectedBy/Prepared/PreparedBy; duplicate 'PreparedBy' header tolerated). Matched PIDs merge the imported values onto the workitem list rows; unmatched PIDs appear as synthetic rows. The upload button is visible whenever `workitems.import.preparedaudit` AND `ms02_active` — no process-filter gate.
```

- [ ] **Step 7d: Commit**

```
git add CHANGELOG.md CLAUDE.md "docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md"
git commit -m "$(cat <<'EOF'
docs: update CHANGELOG, CLAUDE.md, design spec for 5-col prepared-import

Button visibility fix (process-decoupled), 5-col Excel, per-PID map resolver,
synthetic rows, and extra display columns reflected in the unreleased changelog,
the CLAUDE.md MS02 prepared-import paragraph, and the design spec §4.6.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

# PHASE 6 — Final green gate

### Task 8: Full suite + visual verification

**Steps:**

- [ ] **Step 8a: Run full unit + integration suite**

```
python -m pytest tests/unit/ tests/integration/ --ignore=tests/e2e -v --tb=short 2>&1 | tail -60
```

Expected: all PASS.

- [ ] **Step 8b: ruff clean across all touched Python files**

```
ruff check nx_lib/workitem_sources.py nx_lib/views/workitems.py && ruff format --check nx_lib/workitem_sources.py nx_lib/views/workitems.py
```

- [ ] **Step 8c: Restart dev server (template cache flush)**

```
nx -u
```

---

## Gotchas & notes

**TWO Jinja guards, not one.** Both `#preparedAuditWrap` (the button container) and `#preparedAuditBanner` (the post-import banner) are individually guarded by `{% if prepared_import_perm and ms02_active and pid_processes %}`. If only the first is fixed, `document.getElementById('preparedAuditBanner')` returns null in `uploadPreparedAudit` and the success banner never appears. The integration test in Task 1 asserts both `b"preparedAuditWrap"` and `b"preparedAuditBanner"` are present.

**Parser and route caller in the same commit (Task 2).** `parse_prepared_xlsx` changes its return type from `list[tuple]` to `list[dict]`. The pre-commit hook runs the test suite on every commit. Splitting these into two commits would break the test suite between them. All changes — parser, resolver, route, test updates — land in one commit.

**`resolve_ms02_pid_to_wids` reuses `_MS02_IDENT` and `_as_workitem_ids`.** No inline `re.match` or duplicated identifier-safety logic. Security checks stay in one place. The function builds its own SQL (`SELECT DISTINCT "pid_col"::text, "id_col"`) rather than calling `_ms02_columnar_sql` (which projects only the id column), but uses the same `_MS02_IDENT.match` guard and `_as_workitem_ids` coercion helper.

**`resolve_ms02_pid_ids` import removed from `workitems.py`.** After Task 2, `import_prepared_audit` calls `resolve_ms02_pid_to_wids` instead. The old function is still in `workitem_sources.py` (kept for completeness / other potential callers), but removing the unused import from `workitems.py` prevents an ruff F401 error.

**Resolver contract: matched PIDs only, unmatched absent.** `resolve_ms02_pid_to_wids` returns `{pid: [wid,...]}` for matched PIDs only — unmatched PIDs are simply absent from the dict. The synthetic-row logic in `_get_workitems_data` detects unmatched PIDs as `pid not in pid_to_wids` (where `pid_to_wids` is read from the session stash, which mirrors the resolver output). This is consistent throughout.

**Synthetic rows on page 1 only.** The `if offset == 0:` guard prevents synthetic rows from being re-appended on page 2+. The `total_items` bump also only happens on page 1. The paginator will show the correct total (including synthetic rows) after page 1 is fetched. On subsequent pages, the synthetic rows are absent from the row list but the total count is already correct in the paginator state. This is documented as a known limitation: a full solution would stash synthetic rows in the session and page through them; for the initial release this is acceptable since imports are typically hundreds of PIDs.

**CSV export guard.** `export_workitems_csv` iterates all workitems and calls `get_domain_for_workitem(wid)` — passing `None` would fail. The guard `workitems = [w for w in workitems if not w.get("synthetic")]` is added before the `specific_ids` filter.

**Duplicate-header parsing.** The slot scanner processes header cells left-to-right. The 4th header `"PreparedBy"` normalizes to `"preparedby"` — matches the `prepared_flag` slot first (first unfilled in `_KEY_TO_SLOTS["preparedby"]`). The 5th header `"PreparedBy"` also normalizes to `"preparedby"` — `prepared_flag` is now assigned, so it falls through to `prepared_by`. Result: 4th col → Prepared flag; 5th col → PreparedBy name. Exactly as Decision #2 requires.

**CSS column toggle.** `setImportColsVisible(visible)` toggles `no-import-cols` on `#workitemsTable`. The CSS rule `#workitemsTable.no-import-cols .import-col { display: none !important; }` hides both `<th>` and `<td>` elements with `class="import-col"`. `renderTable` calls `setImportColsVisible(activePidToken !== null)` at the top of every call so newly-rendered `<td class="import-col">` cells are correctly hidden/shown without needing `hidden` class per-cell.

**Session stash backward compatibility.** `_get_workitems_data` checks `isinstance(stored, dict)`. Old flat-list tokens (`[10, 20, 30]`) hit the `elif isinstance(stored, list)` path and produce a populated `pid_ids` set but `_pid_import_meta = None` — no synthetic rows, no merge, but the filter still applies. Sessions are short-lived (seconds to minutes) so the in-flight transition is harmless.

**German translation: `Prepared → Vorbereitet`.** Draft A proposed `Bereit` (= "Ready"), which is already used for workitem status `Ready`. The correct domain-specific German for "prepared/processed" is `Vorbereitet`. Using `Bereit` would create a semantic collision with the existing status badge translations.

**`allRenderedWorkitems` and bulk-action checkboxes.** The JS stores rendered rows in the workitems array. Synthetic rows have `workitemid: null`. The synthetic-row template renders an empty `<td>` (no checkbox), so `tbody.querySelectorAll('.row-checkbox')` never finds a synthetic checkbox. Bulk-action logic that checks `data-id` attributes is safe.

**`_cell` closure in `parse_prepared_xlsx`.** The inner `_cell` function captures `row` via a default argument `def _cell(idx, row=row)` — this is necessary inside the `for row in rows_iter` loop to avoid late-binding the loop variable. ruff will not flag it.

**No migration.** Confirmed: 0030 is the last migration file. 0031 is free. This feature requires zero schema changes.
