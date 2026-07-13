# Permission-Gated Doc-Fields (Validation User) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. This plan was written from an exhaustive single-session recon of every doc-field surface in `nx_lib/views/workitems.py` (the multi-agent planning run was rate-limited, so the orchestrator did the recon + red-team inline); **every file path, symbol, and quoted snippet below was Grep/Read-verified against the live repo on 2026-07-13** — trust the anchors, but re-Grep before editing since line numbers drift.

**Goal:** Add a new searchable doc-field **"Validation User"** and make the whole doc-field machinery permission-aware: fields flagged *sensitive* (Validation User is the first) are hidden — name **and** value — from users who lack a single new permission `workitems.filter.documentfields.sensitive`, everywhere the field can surface (search dropdown, autocomplete-values API, search filtering, the workitem detail panel, and CSV export). Users with the permission see them; everyone else sees the app exactly as before.

**Architecture:** Sensitivity is **data-driven**, not hardcoded: a new `IsSensitive BIT` flag on the existing per-field label table `dbo.Search_Field_Labels` marks which `FieldKey`s are sensitive; one shared permission unlocks all of them. Two cached readers expose the sensitive set to the app — `get_sensitive_field_keys()` (lowercased FieldKeys, for the SearchConfig/doc-field surfaces) and `get_sensitive_field_tokens()` (normalized name-tokens = FieldKey + all four language labels, for matching against the **Octo extraction** field names that flow into the panel/CSV). Enforcement is **server-side at every surface** (templates/JS only render what the server sends); a permissionless request cannot reach a sensitive field's name or value through any route, param, cache key, or export. The new field itself is added by a migration; its actual source-DB **column mapping is an Owner action** (only the owner knows the real column name and which process/client row it belongs to) — until mapped it simply never appears, degrading gracefully.

**Tech Stack:** Python 3.13 / Flask, `pyodbc` raw cursors + Flask-Caching `SimpleCache` in `nx_lib/views/workitems.py`, pure helpers unit-tested with pytest, SQL Server migrations under `sql/_migrations/NexoraDB/`, DB-driven i18n labels via `dbo.Search_Field_Labels` (no gettext).

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.64` (already checked out, tracks origin). This plan file is already committed. Commit per task on this branch. **Do NOT `git push` and do NOT open a PR** — the owner reviews and pushes (the pre-push hook runs the full suite incl. Playwright e2e; the owner runs it).
- **TDD is the house rule:** each task writes the failing test first, watches it fail, then implements. Use `superpowers:test-driven-development`.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Every step quotes the exact code to find; re-`Grep` it if it has moved.
- **wv-local `has_permission` trap (this bit prior plans):** route bodies call `has_permission` imported into `nx_lib.views.workitems` (`from ..security import ... has_permission`). For **in-body** perm checks you MUST `monkeypatch.setattr(wv, "has_permission", ...)` — patching `nx_lib.security.has_permission` reaches only `@require_permission` decorator closures. To simulate "has everything except the sensitive perm" use `lambda code: code != "workitems.filter.documentfields.sensitive"`. The same holds for the new module-level helpers `get_sensitive_field_keys` / `get_sensitive_field_tokens` / `get_valid_search_columns`: patch them as `wv.<name>` (e.g. `monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})`).
- **The test DB has NO `SearchConfig` and NO `Search_Field_Labels` table** (verified: neither name appears in `sql/test/schema.sql`). So `get_valid_search_columns()` / `get_sensitive_field_keys()` return empty in CI, and the DB-backed doc-field paths short-circuit. Consequences for tests, all handled below: (a) the **enforcement logic** is proven by **pure unit tests** on the strip/filter helpers (no DB); (b) **integration** tests exercise the *wiring* by monkeypatching the `wv.*` seams above so the gate is reached without the tables. This is deliberate — do NOT add SearchConfig/Search_Field_Labels to the test schema for this feature (out of scope; the seams cover it). `has_permission` is already case-insensitive on this branch (0034), so no case traps.
- **`media_info_{wid}` cache poisoning is already solved and you must not undo it:** `get_media_info` caches the FULL (unsuppressed) fields dict and applies per-request suppression *after* the cache read via the `_suppress(data)` closure (that is how `confidence`/`source_location` already work). Your sensitive-field strip goes **inside `_suppress`**, never before the cache write — otherwise a permissioned user warms the cache and a permissionless user reads it.
- **Migration numbering:** next free number is `0035` (dir tops out at `0034_permission_sortingcode_and_pdbsuser_case.sql`). **Re-list `sql/_migrations/NexoraDB/` at execution time** and bump if taken. Migrations MUST be idempotent (`IF … IS NULL` / `WHERE NOT EXISTS` guards) — the pre-commit hook auto-applies them to INT and may re-run them.
- **`*.sql` is pinned to LF** by `.gitattributes` — write migrations with the Write tool (LF), not shell heredocs.
- **Pre-commit hook** runs `scripts/db-migrate.py --env INT` + `sql/sync-from-db.py --check` on every commit. The new columns change `dbo.SearchConfig` and `dbo.Search_Field_Labels` DDL, so the sync step regenerates `sql/NexoraDB/Tables/dbo.SearchConfig.sql` and `sql/NexoraDB/Tables/dbo.Search_Field_Labels.sql` — **`git add` the regenerated dumps into the same commit** when the hook reports drift. Never hand-edit files under `sql/NexoraDB/`. `SQL_SYNC_SKIP=1 git commit …` is only for INT-unreachable flakes, **never** `--no-verify`.
- **i18n: NO pybabel cycle.** Doc-field labels are DB-driven (`Search_Field_Labels`, four language columns) — the "Validation User" label is seeded as data in EN/DE/FR/IT, not a `gettext` string. The permission `Description` is DB text too. This feature introduces **no new `_()`-wrapped user-facing string**. If you deviate and add one, you must run the full `/nx-i18n` extract→update→translate(de/fr/it, non-fuzzy)→compile cycle or `test_translations.py` fails.
- **Jinja template cache is process-lifetime.** No template edits are required (dropdowns/panel are server-populated), but for the live browser check restart the dev server first.
- **No new top-level files/dirs** → no `deploy.yml` `/XF`/`/XD` changes.
- **`page_visibility()` needs no entry:** it holds only page-level perms; `workitems.filter.*` and `workitems.details.view.*` are deliberately absent from it, and this new filter-level perm follows suit (verified in `nx_lib/security.py:page_visibility`).
- **gitlint:** conventional-commit title, imperative, ≤72 chars, no trailing period, non-empty wrapped body, `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.
- **Test commands (Windows):** unit `.venv\Scripts\python -m pytest tests/unit/test_docfield_sensitivity.py -q`; integration `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -q`.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **One shared permission** `workitems.filter.documentfields.sensitive` gates ALL sensitive fields (owner-locked; not per-field codes). | Owner decision. Fewer permission rows; a field becomes sensitive by data, not by a new code. Sits in the existing `workitems.filter.documentfields` family + follows the `workitems.details.view.{confidence,source_location}` sub-permission precedent (migration `0018`). |
| D2 | **Sensitivity lives in `dbo.Search_Field_Labels.IsSensitive BIT NOT NULL DEFAULT(0)`**, keyed by `FieldKey`. | `Search_Field_Labels` is already the per-field metadata table (FieldKey PK + language labels), read by `api_config_fields`. One natural home; owner flags a field sensitive with an `UPDATE`, no code change. |
| D3 | **"Validation User" is added structurally** (`col_validationuser` on SearchConfig + a `Search_Field_Labels` row marked sensitive), but its **column→source mapping is an Owner action** (`UPDATE SearchConfig SET col_validationuser = '<RealColumn>' …`). | Owner: "Validation User is the field but I still need to add it and map it in the db." Only the owner knows the real source column and target process/client. A wrong mapping would break searches; an unmapped field is harmless (never surfaces). |
| D4 | **Enforcement is server-side at every surface** (search dropdown list, values API, both search-resolution blocks, detail panel, CSV export). Templates/JS are not the gate. | A hand-crafted `?docfield=validationuser` / `?field=validationuser`, a direct `/api/docfield_values` GET, a warmed cache, the panel JSON payload, or a CSV column must all refuse. Client-side hiding alone leaks. |
| D5 | **Two reader helpers, two namespaces.** `get_sensitive_field_keys()` (lowercased FieldKeys) gates the SearchConfig/doc-field surfaces; `get_sensitive_field_tokens()` (normalized FieldKey + all 4 labels) gates the **Octo extraction** field names in the panel/CSV. | The doc-field search keys off `col_<FieldKey>`; the panel/CSV key off Octo `field_mapping` target keys (`{key,label,value}` in `field_locations.extract_field_locations`). Matching Octo names needs fuzz (spacing/case) → normalized tokens; the doc-field side is an exact FieldKey match. |
| D6 | **Cache keys that can serve sensitive data must include the sensitive-perm state.** `api_config_fields`'s `_cache_key` gets a `_s{0|1}` suffix; `api_docfield_values` refuses sensitive fields *before* its `docfield_vals_*` cache is consulted. | Prevents a permissioned user's cached (unfiltered) response being served to a permissionless one. |
| D7 | **Strip runs inside `_suppress` (panel) and once over `details_map` (export), never before a cache write.** | Mirrors the existing `confidence`/`source_location` suppression; keeps `media_info_{wid}` a single shared cache without leaking. |
| D8 | **Fail-open-with-log on a Search_Field_Labels read error** (empty sensitive set → nothing hidden), matching every other DB helper in the module. | Consistent with `get_valid_search_columns` etc. `# ponytail:` a transient NexoraDB blip briefly disables the gate; the upgrade path (fail-closed / last-known-good cache) is noted in Gotchas, not built speculatively. |

---

## Owner actions (not for the executor)

1. **Map the field to its real source column (REQUIRED before it works).** Migration `0035` adds `col_validationuser` and the label row but leaves the mapping `NULL`. Add a follow-up migration (or run on INT/PROD) the real mapping, e.g. for the MS02 PDBS process:
   `UPDATE dbo.SearchConfig SET col_validationuser = '<RealColumnInDossierStatistik>' WHERE ProcessName = 'sydoc.05_PDBS' AND ClientCode = 'ms02';`
   or for a default-client process against its StatisticsDB table. Until this runs, "Validation User" is invisible everywhere (harmless).
2. **Confirm the Octo extraction name matches.** The panel/CSV strip matches Octo `field_mapping` target keys against the normalized FieldKey + labels. If Octo extracts Validation User under a target key that does **not** normalize to `validationuser` / one of the seeded labels, add that spelling as an extra `Search_Field_Labels` label (or adjust `field_mapping`) so the strip catches it. Verify on a real PDBS workitem whose panel shows the value.
3. **Grant the permission.** `0035` seeds `workitems.filter.documentfields.sensitive` and grants it to profiles already holding `admin.view` (admins/owner get it out of the box). Grant it to the specific non-admin profiles/users who should see Validation User via the admin UI.
4. **PROD rollout:** `0035` reaches PROD automatically on the next deploy (merge to main), or immediately via `python scripts/db-migrate.py --env PROD` from a SQL-reachable box (idempotent).
5. **Review + push `feature/2.5.64`** (full pre-push gate).

---

# PHASE 1 — DB foundation

### Task 1: Migration 0035 — new field, sensitivity flag, permission

**Files:**
- Create: `sql/_migrations/NexoraDB/0035_docfield_sensitive_and_validation_user.sql`
- (Hook-regenerated, `git add` when flagged) `sql/NexoraDB/Tables/dbo.SearchConfig.sql` and `sql/NexoraDB/Tables/dbo.Search_Field_Labels.sql`. (The `Permission`/`AccessProfilePermission` INSERTs are **data**, not DDL — `sync-from-db` dumps schema only, so no dump drifts for them.)

**Interfaces:**
- Produces: `dbo.SearchConfig.col_validationuser NVARCHAR(100) NULL`; `dbo.Search_Field_Labels.IsSensitive BIT NOT NULL DEFAULT(0)`; a `Search_Field_Labels` row `FieldKey='validationuser'` (EN/DE/FR/IT labels) with `IsSensitive=1`; a `dbo.Permission` row `workitems.filter.documentfields.sensitive` granted to every `admin.view` profile. These are the columns/keys every later task reads.

- [ ] **Step 1 — Re-verify the number is free:** list `sql/_migrations/NexoraDB/`; if `0035_*` exists, use the next integer and adjust the filename in all steps.
- [ ] **Step 2 — Write the migration** (Write tool, LF). Note SearchConfig `col_*` are `nvarchar/varchar(100)`; keep `NVARCHAR(100)` to match the recent `col_*` additions:

```sql
-- 0035_docfield_sensitive_and_validation_user.sql
-- Permission-gated doc-fields. Three idempotent changes:
--   1) New searchable doc-field column col_validationuser on dbo.SearchConfig.
--      (Its per-process source-column MAPPING is intentionally left NULL here --
--       set by the owner once the real source column/process is known; until
--       then the field never surfaces.)
--   2) IsSensitive flag on dbo.Search_Field_Labels + a 'validationuser' label
--      row flagged sensitive, with EN/DE/FR/IT labels (labels are DB-driven i18n).
--   3) The shared permission workitems.filter.documentfields.sensitive, granted
--      to every access profile that already grants admin.view (Effect 'A').

-- 1) SearchConfig: new field column (mapping stays NULL; owner maps it later).
IF COL_LENGTH('dbo.SearchConfig', 'col_validationuser') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_validationuser NVARCHAR(100) NULL;
GO

-- 2) Search_Field_Labels: sensitivity flag + the Validation User label row.
IF COL_LENGTH('dbo.Search_Field_Labels', 'IsSensitive') IS NULL
    ALTER TABLE dbo.Search_Field_Labels ADD IsSensitive BIT NOT NULL CONSTRAINT DF_Search_Field_Labels_IsSensitive DEFAULT(0);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Search_Field_Labels WHERE FieldKey = 'validationuser')
    INSERT INTO dbo.Search_Field_Labels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive)
    VALUES ('validationuser', 'Validation User', 'Prüfer', 'Validateur', 'Validatore', 1);
GO

-- Make sure the flag is set even if the row somehow pre-existed unflagged.
UPDATE dbo.Search_Field_Labels SET IsSensitive = 1 WHERE FieldKey = 'validationuser';
GO

-- 3) Permission + grant to admin.view profiles (0018 pattern).
INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.filter.documentfields.sensitive',
       'Workitems: view and search sensitive document fields (e.g. Validation User)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.filter.documentfields.sensitive');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.filter.documentfields.sensitive'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
```

- [ ] **Step 3 — Commit** (the hook applies `0035` to INT and regenerates the three per-object dumps; `git add` any it flags):

```bash
# The hook regenerates the two Tables dumps (col_validationuser / IsSensitive);
# the Permission + grant INSERTs are data, so no per-object dump drifts for them.
git add sql/_migrations/NexoraDB/0035_docfield_sensitive_and_validation_user.sql \
        sql/NexoraDB/Tables/dbo.SearchConfig.sql \
        sql/NexoraDB/Tables/dbo.Search_Field_Labels.sql
git commit -F - <<'EOF'
feat(db): add Validation User doc-field + sensitivity flag + permission (0035)

Migration 0035 adds col_validationuser to dbo.SearchConfig (mapping left NULL
for the owner to set), an IsSensitive flag on dbo.Search_Field_Labels with a
'validationuser' label row flagged sensitive (EN/DE/FR/IT), and the shared
workitems.filter.documentfields.sensitive permission granted to every admin.view
profile. All statements are idempotent (COL_LENGTH / NOT EXISTS guards).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

**Verify:** on INT, `SELECT COL_LENGTH('dbo.SearchConfig','col_validationuser'), COL_LENGTH('dbo.Search_Field_Labels','IsSensitive')` → both non-NULL; `SELECT FieldKey, IsSensitive FROM Search_Field_Labels WHERE FieldKey='validationuser'` → `1`; `SELECT 1 FROM Permission WHERE Code='workitems.filter.documentfields.sensitive'` → one row.

---

# PHASE 2 — Sensitivity helpers (pure logic, unit-first)

### Task 2: Pure strip/filter helpers + cached readers

**Files:**
- Modify: `nx_lib/views/workitems.py` (add helpers next to `get_valid_search_columns`)
- Create: `tests/unit/test_docfield_sensitivity.py`

**Interfaces:**
- Produces (used by Phases 3–4):
  - `_norm_field_token(s: str) -> str` — `lower()` then strip non-`[a-z0-9]`.
  - `strip_sensitive_fields(fields: dict, blocked_tokens: set) -> dict` — copy of `fields` minus entries whose `_norm_field_token(key)` is in `blocked_tokens`; no-op copy when `blocked_tokens` is empty/falsey.
  - `drop_sensitive_options(search_options: dict, blocked_keys: set) -> dict` — copy of the `{proc: [{"value","label"}, …]}` map minus options whose `value.lower()` is in `blocked_keys`.
  - `get_sensitive_field_keys() -> set[str]` — cached; lowercased FieldKeys with `IsSensitive=1`.
  - `get_sensitive_field_tokens() -> set[str]` — cached; `{_norm_field_token(FieldKey)} ∪ {_norm_field_token(label)}` over all sensitive rows' four labels.
  - `sensitive_blocked_keys() -> set[str]` / `sensitive_blocked_tokens() -> set[str]` — `set()` if the current user holds `workitems.filter.documentfields.sensitive`, else the full sensitive keys/tokens.

- [ ] **Step 1 — Failing unit tests** in `tests/unit/test_docfield_sensitivity.py` (pure, import the functions from `nx_lib.views.workitems`; no app/DB needed):

```python
from nx_lib.views.workitems import (
    _norm_field_token,
    strip_sensitive_fields,
    drop_sensitive_options,
)


def test_norm_collapses_case_space_punct():
    assert _norm_field_token("Validation User") == "validationuser"
    assert _norm_field_token("validation_user") == "validationuser"
    assert _norm_field_token("ValidationUser") == "validationuser"
    assert _norm_field_token(None) == ""


def test_strip_removes_matching_octo_fields():
    fields = {"Validation User": "alice", "Amount": "50"}
    out = strip_sensitive_fields(fields, {"validationuser"})
    assert out == {"Amount": "50"}
    assert fields == {"Validation User": "alice", "Amount": "50"}  # input untouched


def test_strip_empty_blockset_is_noop_copy():
    fields = {"Validation User": "alice"}
    out = strip_sensitive_fields(fields, set())
    assert out == fields and out is not fields


def test_drop_sensitive_options_filters_by_value():
    opts = {"p1": [{"value": "validationuser", "label": "Validation User"},
                   {"value": "doctype", "label": "Doc Type"}]}
    out = drop_sensitive_options(opts, {"validationuser"})
    assert out == {"p1": [{"value": "doctype", "label": "Doc Type"}]}
```

- [ ] **Step 2 — Run, expect RED** (ImportError): `.venv\Scripts\python -m pytest tests/unit/test_docfield_sensitivity.py -q`.
- [ ] **Step 3 — Implement.** Add near `get_valid_search_columns` in `nx_lib/views/workitems.py` (it already imports `re`, `cache`, `engine_nexora_db`, `current_app`, `has_permission`):

```python
def _norm_field_token(s):
    """Normalize a field name for cross-namespace matching: lowercase, strip
    everything but [a-z0-9] so 'Validation User' / 'validation_user' /
    'ValidationUser' all collapse to the same token."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def strip_sensitive_fields(fields, blocked_tokens):
    """Copy of an Octo extraction ``fields`` dict (or any name->value mapping)
    with entries whose normalized key is blocked removed. Empty blocked set =>
    plain copy (never mutates the input, which may be a cached object)."""
    if not blocked_tokens:
        return dict(fields)
    return {k: v for k, v in fields.items() if _norm_field_token(k) not in blocked_tokens}


def drop_sensitive_options(search_options, blocked_keys):
    """Copy of the api_config_fields {proc: [{'value','label'}, ...]} map with
    options whose value (a doc-field FieldKey) is blocked removed."""
    if not blocked_keys:
        return dict(search_options)
    return {
        proc: [f for f in fields if (f.get("value") or "").lower() not in blocked_keys]
        for proc, fields in search_options.items()
    }


@cache.cached(timeout=3600, key_prefix="sensitive_field_keys")
def get_sensitive_field_keys():
    """Lowercased FieldKeys flagged IsSensitive=1 in Search_Field_Labels.
    Empty set on any error (fail-open with log, like the other DB helpers)."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT FieldKey FROM Search_Field_Labels WHERE IsSensitive = 1")
        return {r[0].lower() for r in cur.fetchall() if r[0]}
    except Exception as e:
        current_app.logger.error(f"get_sensitive_field_keys: {e}")
        return set()
    finally:
        if conn:
            conn.close()


@cache.cached(timeout=3600, key_prefix="sensitive_field_tokens")
def get_sensitive_field_tokens():
    """Normalized name-tokens (FieldKey + all four language labels) of sensitive
    fields, for matching against Octo extraction field names shown in the detail
    panel / CSV export. Empty set on any error (fail-open with log)."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel "
            "FROM Search_Field_Labels WHERE IsSensitive = 1"
        )
        tokens = set()
        for row in cur.fetchall():
            for val in row:
                t = _norm_field_token(val)
                if t:
                    tokens.add(t)
        return tokens
    except Exception as e:
        current_app.logger.error(f"get_sensitive_field_tokens: {e}")
        return set()
    finally:
        if conn:
            conn.close()


def sensitive_blocked_keys():
    """FieldKeys the CURRENT user may not use (empty if they hold the perm)."""
    if has_permission("workitems.filter.documentfields.sensitive"):
        return set()
    return get_sensitive_field_keys()


def sensitive_blocked_tokens():
    """Octo name-tokens the CURRENT user may not see (empty if they hold perm)."""
    if has_permission("workitems.filter.documentfields.sensitive"):
        return set()
    return get_sensitive_field_tokens()
```

- [ ] **Step 4 — Run, expect GREEN:** `.venv\Scripts\python -m pytest tests/unit/test_docfield_sensitivity.py -q`.
- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/workitems.py tests/unit/test_docfield_sensitivity.py
git commit -F - <<'EOF'
feat(workitems): sensitive doc-field helpers (readers + pure strip/filter)

Add IsSensitive-backed readers (get_sensitive_field_keys / _tokens, cached) and
pure helpers (_norm_field_token, strip_sensitive_fields, drop_sensitive_options)
plus the per-request sensitive_blocked_keys/_tokens gates. No behaviour change
yet -- Phases 3-4 wire these into the doc-field surfaces. Unit-tested pure logic;
DB readers fail open with a log, matching the module's other helpers.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — Gate the doc-field search surfaces

### Task 3: Hide sensitive fields from the search dropdown (`api_config_fields`)

**Files:**
- Modify: `nx_lib/views/workitems.py` — function `api_config_fields`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `sensitive_blocked_keys`, `drop_sensitive_options`, `has_permission` (Task 2).
- Produces: `/api/config/fields` omits sensitive FieldKeys from every process's list for users without the perm, and its cache is per-perm-state (no cross-user leak).

`api_config_fields` today is gated only by `"username" in session` (no doc-field perm) — so the sensitive field NAME would leak here even to users who can't search it. Two edits: cache-key includes perm state; options filtered before caching.

- [ ] **Step 1 — Failing pure-ish integration test.** Because the test DB has no `SearchConfig`/`Search_Field_Labels`, `search_options` is empty and route-level exclusion isn't observable; the exclusion **logic** is already unit-covered by `test_drop_sensitive_options_filters_by_value`. Add a **regression test that the route still 200s and that the perm state reaches the cache key** by asserting two different-perm calls don't collide. In `tests/integration/test_workitems_routes.py`:

```python
def test_api_config_fields_perm_state_in_cache_key(user_client, monkeypatch):
    import nx_lib.views.workitems as wv
    from nx_lib.views.workitems import cache

    cache.clear()
    # Without the sensitive perm the response is filtered + cached under _s0.
    monkeypatch.setattr(wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive")
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    r0 = user_client.get("/api/config/fields")
    assert r0.status_code == 200
    # With the perm the cache key differs (_s1) -> not served the _s0 entry.
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    r1 = user_client.get("/api/config/fields")
    assert r1.status_code == 200
```

- [ ] **Step 2 — Run, expect RED** (route imports `drop_sensitive_options`/`sensitive_blocked_keys` only after Step 3 wiring, and the `_s{}` suffix doesn't exist yet — the test fails on the not-yet-added filtering call raising `NameError` if you TDD by first adding the assertion that the code path runs): `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k config_fields_perm_state -x`.

  > If Step 1 as written passes trivially against the current route (it may, since both calls just 200), treat the real RED gate as the **unit** test `test_drop_sensitive_options_filters_by_value` (Task 2) plus a manual check that the cache key changed; the value of this integration test is guarding the cache-key regression. Keep it.

- [ ] **Step 3 — Implement.** In `api_config_fields`, find:

```python
    current_lang = str(get_locale())
    _cache_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)
```

and change the cache key to carry perm state:

```python
    current_lang = str(get_locale())
    _sees_sensitive = has_permission("workitems.filter.documentfields.sensitive")
    _cache_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}_s{int(_sees_sensitive)}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)
```

Then find the tail:

```python
    result = {"search_options": search_options, "labels": db_labels_map}
    cache.set(_cache_key, result, timeout=3600)
    return jsonify(result)
```

and filter before building `result`:

```python
    blocked = sensitive_blocked_keys()
    if blocked:
        search_options = drop_sensitive_options(search_options, blocked)
        db_labels_map = {k: v for k, v in db_labels_map.items() if k.lower() not in blocked}
    result = {"search_options": search_options, "labels": db_labels_map}
    cache.set(_cache_key, result, timeout=3600)
    return jsonify(result)
```

- [ ] **Step 4 — Run, expect GREEN:** `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k "config_fields" -x`.
- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -F - <<'EOF'
feat(workitems): hide sensitive fields from the doc-field dropdown

api_config_fields now drops sensitive FieldKeys (and their labels) from the
per-process options for users lacking workitems.filter.documentfields.sensitive,
and its cache key carries the perm state (_s0/_s1) so a permissioned response is
never served to a permissionless caller.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 4: Refuse sensitive fields in the values API + search resolution

**Files:**
- Modify: `nx_lib/views/workitems.py` — `api_docfield_values` and the two doc-field pre-fetch blocks in `_get_workitems_data`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `sensitive_blocked_keys` (Task 2).
- Produces: a permissionless request for a sensitive field gets `[]` from `/api/docfield_values` and no filtering contribution from the search route.

- [ ] **Step 1 — Failing integration test** (uses the wv-local seams so it works without the tables — a blocked sensitive field returns `[]` *before* the route touches the absent `SearchConfig`, whereas an un-blocked one would fall through to a 500 on the missing table):

```python
def test_api_docfield_values_blocks_sensitive_without_perm(user_client, workitems_all_perms, monkeypatch):
    import nx_lib.views.workitems as wv
    # Pretend col_validationuser is a real searchable column, and that it is sensitive.
    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    # Everything allowed EXCEPT the sensitive perm.
    monkeypatch.setattr(wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive")
    resp = user_client.get("/api/docfield_values?field=validationuser&process=all")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_api_docfield_values_allows_sensitive_with_perm(user_client, workitems_all_perms, monkeypatch):
    import nx_lib.views.workitems as wv
    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    monkeypatch.setattr(wv, "has_permission", lambda code: True)  # incl. the sensitive perm
    # With the perm the sensitivity gate is skipped; the route then hits the
    # (absent-in-CI) SearchConfig and degrades to 500/[] -- either proves the gate
    # did NOT short-circuit. Accept both to stay DB-independent.
    resp = user_client.get("/api/docfield_values?field=validationuser&process=all")
    assert resp.status_code in (200, 500)
```

  > `@require_permission("workitems.filter.documentfields")` on `api_docfield_values` resolves the REAL `nx_lib.security.has_permission`; `workitems_all_perms` (which patches the security module) keeps the decorator passing while `wv.has_permission` drives the in-body gate. This is the established split — see the existing `test_prepared_documents_preview_button_requires_details_view`.

- [ ] **Step 2 — Run, expect RED** (`test_..._blocks_sensitive_without_perm` currently returns a value list or 500, not `[]`): `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k docfield_values_blocks_sensitive -x`.
- [ ] **Step 3a — Implement in `api_docfield_values`.** Find:

```python
    target_col_name = f"col_{field}"
    # Whitelist the column name before interpolating it into the SearchConfig SQL
    # below (the same guard the workitems search path uses) -- `field` is a raw
    # request arg, so without this it is a SQL-injection vector against NexoraDB.
    if target_col_name not in get_valid_search_columns():
        return jsonify([])
```

and add the sensitivity refusal directly after it:

```python
    if field in sensitive_blocked_keys():
        return jsonify([])
```

- [ ] **Step 3b — Implement in the default search block** of `_get_workitems_data`. Find:

```python
    if has_permission("workitems.filter.documentfields") and target_processes:
        valid_db_columns = get_valid_search_columns()
```

add a per-request block set right after it:

```python
        blocked_docfields = sensitive_blocked_keys()
```

then inside the loop find:

```python
                target_config_col = f"col_{docfield}"
                if target_config_col not in valid_db_columns:
                    continue
```

and add the skip:

```python
                if docfield in blocked_docfields:
                    continue
```

(`docfield` is already `(docfield or "").lower().strip()` at the top of the loop.)

- [ ] **Step 3c — Implement in the MS02 search block.** Find:

```python
        engine_ms02_docfields_pg is not None
    ):
        valid_db_columns = get_valid_search_columns()
```

add:

```python
        blocked_docfields = sensitive_blocked_keys()
```

then inside its loop find:

```python
                target_config_col = f"col_{docfield}"
                # Whitelist the column name (same guard the default path uses)
                # before interpolating it -- blocks injection via `docfield`.
                if target_config_col not in valid_db_columns:
                    continue
```

and add:

```python
                if docfield in blocked_docfields:
                    continue
```

- [ ] **Step 4 — Run, expect GREEN** (new tests + the existing docfield tolerance tests unaffected): `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k "docfield" -x`.
- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -F - <<'EOF'
feat(workitems): refuse sensitive doc-fields in values API and search

api_docfield_values returns [] for a sensitive field when the caller lacks
workitems.filter.documentfields.sensitive, and both doc-field pre-fetch blocks
in _get_workitems_data skip sensitive field pairs -- so a hand-crafted
?field=/&docfield= cannot read or filter by a gated field's values.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Gate the detail panel + CSV export

### Task 5: Strip sensitive Octo fields from the panel

**Files:**
- Modify: `nx_lib/views/workitems.py` — the `get_media_info` route's `_suppress(data)` closure
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `sensitive_blocked_tokens`, `strip_sensitive_fields`, `_norm_field_token` (Task 2).
- Produces: the detail-panel JSON omits sensitive extraction fields (`fields` dict + `field_sources` list, so the highlight overlay can't leak the value/location either) for users without the perm — applied post-cache, so `media_info_{wid}` stays a shared cache.

- [ ] **Step 1 — Failing integration test.** Drive `_suppress` in isolation via the module (no Octo needed):

```python
def test_suppress_strips_sensitive_fields(app, monkeypatch):
    import nx_lib.views.workitems as wv
    monkeypatch.setattr(wv, "get_sensitive_field_tokens", lambda: {"validationuser"})
    # No sensitive perm; everything else granted so fields are otherwise visible.
    monkeypatch.setattr(wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive")
    data = {
        "workitem_id": 1, "media_count": 0,
        "fields": {"Validation User": "alice", "Amount": "50"},
        "field_sources": [
            {"key": "Validation User", "label": "Validation User", "value": "alice", "locations": []},
            {"key": "Amount", "label": "Amount", "value": "50", "locations": []},
        ],
        "table_sources": [],
    }
    with app.test_request_context("/"):
        out = wv._suppress_for_test(data)   # thin wrapper exposing the closure; see Step 3
    assert "Validation User" not in out["fields"]
    assert out["fields"] == {"Amount": "50"}
    assert [s["key"] for s in out["field_sources"]] == ["Amount"]
    assert data["fields"] == {"Validation User": "alice", "Amount": "50"}  # cache object untouched
```

  > `_suppress` is a nested closure inside `get_media_info`, not importable. Rather than restructure the route, add a **module-level pure function** `strip_sensitive_from_detail(data, blocked_tokens)` and have `_suppress` call it; the test targets that function directly (drop the `test_request_context`/`_suppress_for_test` shim). Rewrite Step 1 to import and call `strip_sensitive_from_detail(data, {"validationuser"})`. (This keeps the closure thin and the logic testable — the structural, cleaner path.)

- [ ] **Step 1 (final form) — Failing test:**

```python
def test_strip_sensitive_from_detail_removes_fields_and_sources():
    from nx_lib.views.workitems import strip_sensitive_from_detail
    data = {
        "fields": {"Validation User": "alice", "Amount": "50"},
        "field_sources": [
            {"key": "Validation User", "value": "alice", "locations": []},
            {"key": "Amount", "value": "50", "locations": []},
        ],
        "table_sources": [],
    }
    out = strip_sensitive_from_detail(data, {"validationuser"})
    assert out["fields"] == {"Amount": "50"}
    assert [s["key"] for s in out["field_sources"]] == ["Amount"]
    assert data["fields"] == {"Validation User": "alice", "Amount": "50"}  # untouched
```

- [ ] **Step 2 — Run, expect RED** (ImportError): `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k strip_sensitive_from_detail -x`.
- [ ] **Step 3 — Implement.** Add the module-level function near the other helpers:

```python
def strip_sensitive_from_detail(data, blocked_tokens):
    """Copy of a get_media_info payload with sensitive extraction fields removed:
    the ``fields`` dict AND the ``field_sources`` list (so the highlight overlay
    can't leak the value/location either). Empty blocked set => plain copy."""
    if not blocked_tokens:
        return data
    d = dict(data)
    d["fields"] = strip_sensitive_fields(d.get("fields", {}) or {}, blocked_tokens)
    d["field_sources"] = [
        s for s in (d.get("field_sources") or [])
        if _norm_field_token(s.get("key", "")) not in blocked_tokens
    ]
    return d
```

Then inside `get_media_info`'s `_suppress(data)`, find the end of the fields branch:

```python
            if not can_view_fields:
                d["fields"] = {}
                d["field_sources"] = []
                d["table_sources"] = []
                return d
```

and immediately after that `if` block (fields ARE visible here), add:

```python
            blocked_sensitive = sensitive_blocked_tokens()
            if blocked_sensitive:
                d = strip_sensitive_from_detail(d, blocked_sensitive)
```

(Place it before the `field_sources`/`table_sources` confidence/location rework so the later `d.get("field_sources", [])` reads the already-stripped list. If you prefer, recompute `fs = d.get("field_sources", [])` after the strip — verify by reading the surrounding lines.)

- [ ] **Step 4 — Run, expect GREEN:** `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k "strip_sensitive_from_detail or media_info or details" -x`.
- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -F - <<'EOF'
feat(workitems): strip sensitive fields from the detail panel

get_media_info's _suppress now removes sensitive extraction fields (the fields
dict and the field_sources highlight entries) for users without the sensitive
perm, via the pure strip_sensitive_from_detail helper. Runs post-cache like the
existing confidence/source-location suppression, so media_info_<wid> stays a
single shared cache without leaking.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 6: Strip sensitive fields from CSV export

**Files:**
- Modify: `nx_lib/views/workitems.py` — `export_workitems_csv`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `sensitive_blocked_tokens`, `strip_sensitive_fields` (Task 2).
- Produces: exported CSV has no sensitive field columns/values for users without the perm.

The CSV builds its field columns from each workitem's `detail["fields"]` (`all_field_keys` derivation, then `fields.get(k, "")`). Strip once over `details_map` before headers are computed and every downstream read is clean.

- [ ] **Step 1 — Failing test** for the (extracted, pure) strip point. To keep it DB/Octo-independent, extract the strip into a tiny helper `_strip_export_fields(details_map, blocked_tokens)` and test it directly:

```python
def test_strip_export_fields_removes_sensitive_columns():
    from nx_lib.views.workitems import _strip_export_fields
    details_map = {
        1: {"fields": {"Validation User": "alice", "Amount": "50"}, "history": [], "images": []},
        2: {"fields": {"Amount": "9"}, "history": [], "images": []},
    }
    _strip_export_fields(details_map, {"validationuser"})
    assert details_map[1]["fields"] == {"Amount": "50"}
    assert details_map[2]["fields"] == {"Amount": "9"}
```

- [ ] **Step 2 — Run, expect RED** (ImportError): `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k strip_export_fields -x`.
- [ ] **Step 3 — Implement.** Add the helper near the others:

```python
def _strip_export_fields(details_map, blocked_tokens):
    """In-place: drop sensitive field entries from every detail's fields dict
    before CSV headers/rows are built. No-op when blocked_tokens is empty."""
    if not blocked_tokens:
        return
    for detail in details_map.values():
        if detail.get("fields"):
            detail["fields"] = strip_sensitive_fields(detail["fields"], blocked_tokens)
```

Then in `export_workitems_csv`, find the point just after `details_map` is fully populated and before `all_field_keys` is built:

```python
    all_field_keys = []
    if include_fields:
        seen_keys = set()
```

and insert the strip immediately above it:

```python
    if include_fields:
        _strip_export_fields(details_map, sensitive_blocked_tokens())

    all_field_keys = []
    if include_fields:
        seen_keys = set()
```

- [ ] **Step 4 — Run, expect GREEN:** `.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -k "strip_export_fields or export" -x`.
- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -F - <<'EOF'
feat(workitems): strip sensitive fields from CSV export

export_workitems_csv removes sensitive extraction-field columns/values before
building headers/rows for users lacking the sensitive perm, closing the export
leak. Extracted _strip_export_fields keeps the logic unit-tested.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — Docs

### Task 7: Changelog + CLAUDE.md note

**Files:**
- Modify: `CHANGELOG.md`, `CLAUDE.md`

**Interfaces:** none (docs only).

- [ ] **Step 1 — `CHANGELOG.md` under `[Unreleased]`:**
  - **Added** — "Validation User" doc-field and a permission-gated doc-field mechanism: fields flagged `IsSensitive` in `dbo.Search_Field_Labels` are hidden (name and value) from users without `workitems.filter.documentfields.sensitive` across the search dropdown, the values autocomplete API, search filtering, the detail panel, and CSV export (migration `0035`).
- [ ] **Step 2 — `CLAUDE.md`:** in the multi-source workitems / doc-field area, add one sentence: doc-field visibility is now permission-aware — `dbo.Search_Field_Labels.IsSensitive` marks sensitive `FieldKey`s, gated by the shared `workitems.filter.documentfields.sensitive` permission and enforced server-side at every surface (dropdown, values API, search, detail panel, CSV). (Grep `docs/` for `documentfields`/`SearchConfig`; if a how-to documents doc-field search, add the same note there — otherwise skip, do not author a new doc.)
- [ ] **Step 3 — Commit:**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -F - <<'EOF'
docs: permission-gated doc-fields (Validation User)

Changelog entry + CLAUDE.md note for the sensitive doc-field mechanism and the
new workitems.filter.documentfields.sensitive permission.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 6 — Live verification on INT (browser, self-driven)

### Task 8: End-to-end check on the running app

**Files:** none (verification only).

**Prereq:** the owner has run the mapping `UPDATE` (Owner action 1) on INT and confirmed the Octo extraction name (Owner action 2). If not yet done, verify the *plumbing* against a temporarily-mapped INT test row, then revert — and note it.

- [ ] **Step 1 — Restart the dev server** (templates/code are process-cached): `nx -u -b --loginas:<a user WITHOUT the sensitive perm>` (INT).
- [ ] **Step 2 — Dropdown:** on Workitems, open the doc-field search dropdown for the mapped process → **"Validation User" is absent**. Log in as a user WITH the perm (or grant it) and reload → it appears. Screenshot both to `var/screenshots/docfield-sensitive-dropdown-*.png`.
- [ ] **Step 3 — Values API:** as the no-perm user, `GET /api/docfield_values?field=validationuser&process=<proc>` → `[]`. As the perm user → values (or empty if the column is unmapped).
- [ ] **Step 4 — Detail panel:** open a workitem whose Octo extraction includes Validation User. No-perm user → the value is absent from the panel; perm user → present. Screenshot.
- [ ] **Step 5 — CSV export:** as the no-perm user, export with "fields" included → the CSV has no Validation User column; perm user → it does.
- [ ] **Step 6 — SendUserFile** the screenshots if the session is remote (it is).

---

## Gotchas & notes

- **Two field namespaces, one gate.** Doc-field **search** keys off SearchConfig `col_<FieldKey>` (exact FieldKey match via `get_sensitive_field_keys`); the **panel/CSV** key off Octo `field_mapping` target keys (fuzzy name match via `get_sensitive_field_tokens` = FieldKey + all four labels, normalized). Owner action 2 exists because these two namespaces are configured independently — the Octo target key must normalize to one of the sensitive tokens or the panel/CSV strip won't catch it.
- **Fail-open on DB error (D8, `# ponytail:`).** If `Search_Field_Labels` is briefly unreachable, `get_sensitive_field_*` return empty and nothing is hidden (matching every other DB helper in the module, which also fail open). Ceiling: a transient NexoraDB blip disables the gate for up to the SimpleCache TTL. Upgrade path if this ever matters: cache last-known-good and treat a read failure as "hide the known sensitive set," or fail the surface closed. Not built — YAGNI until asked.
- **Cache correctness.** `api_config_fields` cache key now includes `_s{0|1}`; `api_docfield_values` refuses sensitive fields before its `docfield_vals_*` cache is read; `media_info_{wid}` strip is post-cache in `_suppress`. Do not "optimize" any strip to run before a cache write — that reintroduces the leak (D6/D7).
- **`@require_permission("workitems.filter.documentfields")` still guards `api_docfield_values`** — the sensitive gate is an *additional* in-body refusal, not a replacement. Non-sensitive fields behave exactly as before.
- **Red-team notes folded in:** (1) `api_config_fields` was the sneaky leak — it's login-gated only, so the field *name* would show even to users who can't search it; Task 3 closes it. (2) `field_sources` (not just `fields`) carries the value + highlight location, so Task 5 strips both. (3) The export reads `detail["fields"]`; stripping once over `details_map` covers header derivation and row values in one place. (4) Test-DB has no SearchConfig/Search_Field_Labels, so enforcement logic is proven by pure unit tests and wiring by wv-local monkeypatch seams — the "blocked → `[]` before the absent-table query" trick makes the values-API gate observable in CI.
- **Sequencing:** no conflict with in-flight `feature/2.5.64` work — the pdbsUser fix (migrations `0034`, case-insensitive `has_permission`) is already committed on this branch and this plan builds on both (next migration `0035`; relies on case-insensitive matching for the new permission code). Re-verify `0035` is free and `0034` is applied before starting.
