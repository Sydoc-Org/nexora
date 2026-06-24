# Prepared Documents — Preview & Register Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three presentation defects on the MS02 "Prepared Documents" register and its read-only Octo Workitem-preview modal: (1) the register table's centered header columns (COLLECTED / PREPARED / OCTO STATUS) render left-aligned while their body cells render centered — ragged columns; (2) the "Prepared documents" entry button on the Workitems overview shows regardless of the selected Process — it must show only when an MS02 prepared-docs target process is selected; (3) the preview modal's Import→Extraction→Validation→Delivery timeline renders all-grey because the preview never supplies the document's `status`/`current_stage`.

**Architecture:** All three are template / paired-JS / route-presentation fixes — no DB schema, no route signature change. Bug 1 swaps a Tailwind `text-center` utility for the existing `.nx-table .align-center` helper on three `<th>` in `templates/prepared_documents.html` (the body `<td>` already render centered, so they are left untouched). Bug 2 computes a process-match boolean in `workitems_overview()` and tightens an existing Jinja `{% if %}` in `templates/workitems_overview.html`. Bug 3 adds ONE small parameterized helper `resolve_octo_wid_stage(engine, wid)` in `nx_lib/workitem_sources.py` (mirroring the canonical `t_WorkItems` Status/CurrentStage CASE-over-join), which `prepared_documents()` calls with `CLIENTS["default"].runtime_engine` for the already-resolved Octo wid, attaches `status`+`current_stage` to `octo_status[pid]`, emits them as `data-*` on the Preview button, and forwards them through `openPreview` into `NexoraWorkitemDetail.render`'s already-existing `opts.status`/`opts.currentStage` fallback — so the shared panel partial is NOT edited.

**Tech Stack:** Flask + Jinja2 templates (cached process-lifetime), vanilla-JS template partials (`templates/js/_*.html`), Tailwind via CDN + shared `static/css/nexora-ui.css`, raw-cursor SQL reads in `nx_lib/` (SQL Server `engine_octo_db` via `CLIENTS["default"].runtime_engine`; MS02 Postgres `engine_ms02_docfields_pg` only for PID→wid resolution), pytest (unit + integration route-render).

## Context an engineer needs (read first)

- **Branch:** work on `feature/2.5.63` (NOT `main`). **Remote / commit-only session:** every task STOPS at `git commit` — do **not** `git push` and do **not** open a PR.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Every step below quotes the exact code to find. Re-`Grep` the snippet if it has moved.
- **Jinja template cache is process-lifetime.** After ANY edit to a `.html` template or a `templates/js/*.html` partial you MUST restart the dev server (`nx -u …`) before a browser check, or you will verify stale HTML.
- **e2e / CI has NO MS02 engine** (`ms02_active` is `False`: `engine_ms02_docfields_pg is None` and `"ms02" not in CLIENTS`). Route-render tests must **gate-and-mock**:
  ```python
  import nx_lib.views.workitems as wv
  from nx_lib.clients import CLIENTS
  monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
  monkeypatch.setitem(CLIENTS, "ms02", object())
  monkeypatch.setattr(wv, "has_permission", lambda code: True)   # wv-local, see trap
  ```
- **wv-local `has_permission` trap:** the route bodies call `has_permission` imported into `nx_lib.views.workitems` (verified: `from ..security import has_permission`). Patching `nx_lib.security.has_permission` (what `workitems_all_perms` does) is NOT enough for the in-body perm checks — also `monkeypatch.setattr(wv, "has_permission", lambda code: True)`. To test perm-absence use the `code != "…"` form (e.g. `lambda code: code != "workitems.details.view"`).
- **`user@test.local` (the `user_client` fixture) has only `dashboard.view`** — its session `permissions` list has NO `workitems.filter.process.*` perm, so `allowed_processes` is empty and the route resets `process_name` to `'all'` (`if process_name != "all" and process_name not in allowed_processes: process_name = "all"`). A bare `?prcfW=sydoc.05_PDBS` would be reset before the Bug-2 gate runs. Drive the gate by monkeypatching `wv._ms02_target_processes` AND (for the present-case) seeding the session perm so `process_name` survives (see Task 2; verified sound — login precedes the seed and the GET does not re-authenticate, so the seed persists).
- **SQL pre-commit hooks may fail on known INT CRLF drift.** Escape hatch is `SQL_SYNC_SKIP=1 git commit …` — **NEVER `--no-verify`**. (No SQL is touched here, but the hook runs on every commit.)
- **i18n cycle:** only if a NEW user-facing string is introduced. This plan introduces **no new user-facing strings** — `_("Collected")`, `_("Prepared")`, `_("Octo status")`, `_("Preview")`, `_("Prepared documents")` and the timeline step labels (`Import`/`Extraction`/`Validation`/`Delivery`, literal/untranslated in the JS) all already exist and are wrapped. The two new `data-*` attribute VALUES come from the DB, not `_()`-literals. So **no pybabel cycle** is needed. (If you deviate and add a tooltip/label, run the nexora extract→update→translate de/fr/it non-fuzzy→compile cycle; `test_translations.py` enforces it.)
- **Migrations needed: no.** All three bugs are template/JS/route presentation. No DB schema, no data migration.
- **New permission: no.** Reuse `workitems.import.preparedaudit` (the `@require_permission` decorator on `prepared_documents()` + the button) and the existing `workitems.details.view` (the in-body preview gate). `page_visibility()` already exposes `preparedDocsPagePerm`.
- **Stray uncommitted files** (`helpers/notify-toast.ps1`, `.claudeignore`, `scripts/new-process.py`, the `0032_*` migration) are NOT part of this feature — never stage them. Use explicit `git add <paths>` per commit, never `git add -A`/`.`.

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Button gating (LOCKED, owner-confirmed):** the `prepared-docs-link` button on the Workitems overview is visible **only when `process_name` is one of the MS02 prepared-docs target processes** (`process_name in _ms02_target_processes()`, e.g. `sydoc.05_PDBS`). Hidden on `all`/"All Processes" and every non-PDBS process. | The register is MS02-PDBS-specific; surfacing it under unrelated processes is noise. |
| D2 | Compute the Bug-2 gate **in Python** (`workitems_overview()`) as a plain boolean kwarg `prepared_docs_process_match` and AND it into the existing Jinja gate (`{% if prepared_import_perm and ms02_active and prepared_docs_process_match %}`). No Jinja `{% if x in set %}` (no such precedent; `prepared_import_perm`/`ms02_active` are the dominant compute-bool-in-Python idiom). | Matches existing idiom; keeps Jinja dumb; trivially testable by monkeypatching `_ms02_target_processes`. |
| D3 | Gate against the **full `_ms02_target_processes()` list** (not a hardcoded `sydoc.05_PDBS`). It is the single locked-decision source already used by `prepared_documents()` / `_ms02_pid_specs`; a hardcoded subset would drift. | Single source of truth; future PDBS-family processes inherit the behaviour. |
| D4 | Bug 1 fix = swap the three centered HEADER `<th>` from Tailwind `text-center` to the existing `.nx-table .align-center` helper. The body `<td>` are **left untouched** (the Collected/Prepared bodies use `text-center` and the Octo-status body uses `flex items-center justify-center` — both already render centered; the only `text-align` competitor is the `thead`-scoped rule, which does not reach `tbody`). Do **not** edit the global `.nx-table thead th { text-align:left }` rule, and do **not** add `table-fixed`/`<colgroup>` (see Owner action O3). | Smallest safe diff; root cause is header-only. `.nx-table .align-center` has specificity (0,2,0) — two classes — which **beats** `.nx-table thead th` (0,1,2) outright, so the header centers (this is higher specificity, NOT "equal specificity, defined later"). |
| D5 | Bug 3 status source = a **new parameterized helper** `resolve_octo_wid_stage(engine, wid)` in `nx_lib/workitem_sources.py` mirroring the canonical default-source `t_WorkItems` Status/CurrentStage **CASE-over-join** query, scoped to one wid via `ROW_NUMBER() … WHERE rn = 1`. `prepared_documents()` calls it with `CLIENTS["default"].runtime_engine` and attaches `status`+`current_stage` to `octo_status[pid]`. The shared `render()` already has an `opts.status`/`opts.currentStage` fallback, so `_workitem_detail_panel_js.html` is **not** edited. | The resolved wid is a default-client Octo workitem (the register's "Open in Workitems" link points at the default overview). A parameterized helper gives the route a monkeypatchable seam (CI has no Octo engine) and reuses the canonical CASE so the preview never disagrees with the list. |
| D6 | The new helper must **never raise** — return `{"status": None, "current_stage": None}` on absent engine / bad wid / unreachable Octo / DB error, logging via the same `current_app.logger.error(...)` pattern `resolve_ms02_pid_to_wids` uses. The route maps `None → ""`. | The register must still render (timeline simply stays grey) if Octo is momentarily unreachable. |

## Owner actions (out of scope for the agent)

- **O1 — PROD/INT live timeline verification.** Dev/CI has no reachable Octo engine, so `resolve_octo_wid_stage` returns `{None, None}` locally and the live timeline stays grey. The agent verifies the *data plumbing* (route emits `data-status`/`data-current-stage`; JS forwards them into `render`'s `opts`) via tests, and the *DOM lighting* via a **synthetic** browser check (inject a fake stage). The owner does the real-data confirmation (right step lit for a real PDBS document's stage) on INT/PROD after deploy.
- **O2 — `git push` + PR→main.** Remote session: the agent stops at `git commit`. Owner pushes `feature/2.5.63` and opens the PR.
- **O3 — Confirm Bug-1 scope from Image #1.** The verified root cause is header *text alignment*. If, after this fix, the screenshot still shows ragged *column widths* (not just alignment), the owner decides whether to also pin widths (`table-fixed` + `<colgroup>`); the agent flags it in the Bug-1 screenshot but does not add width-pinning speculatively (D4).

---

# PHASE 1 — Bug 1: register column alignment

### Task 1: Center the three check/status header cells to match their body cells

**Files:**
- Modify: `templates/prepared_documents.html`
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: the existing `.nx-table .align-center` helper in `static/css/nexora-ui.css` (`.nx-table .align-center { text-align: center; }`).
- Produces: no API change — pure markup. COLLECTED / PREPARED / OCTO STATUS headers render centered over their already-centered body cells.

Root cause (verified): in `templates/prepared_documents.html` the three centered headers use a bare Tailwind utility:
```html
<th scope="col" class="px-6 py-3 text-center">
  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Collected") }}</span>
</th>
```
but `static/css/nexora-ui.css` ships `.nx-table thead th { … text-align: left; … }` (specificity (0,1,2)), which **out-specificities** the single-class `.text-center` utility (0,1,0). So the HEADER renders left while its body `<td>` (`class="px-6 py-4 whitespace-nowrap text-center"`, and the Octo-status body `<div class="flex items-center justify-center">`) renders centered → the ragged mismatch in Image #1. The body cells have NO `thead`-scoped competitor (the only `tbody` rule `.nx-table tbody td` sets no `text-align`), so they are fine and must stay untouched. PID / Collected by / Prepared by are intentionally `text-left` and stay as-is. The `.nx-table .align-center` helper has specificity (0,2,0) — two classes — which beats `.nx-table thead th` (0,1,2) on the second component, so swapping `text-center → align-center` on the `<th>` makes the header center.

- [ ] **Write a failing route-render test** in `tests/integration/test_workitems_routes.py`. Copy the gate-and-mock + stubs from `test_prepared_documents_preview_button_requires_details_view` (`engine_ms02_docfields_pg=object()`, `CLIENTS["ms02"]=object()`, `count_prepared_documents`/`fetch_prepared_documents_page`/`_ms02_target_processes`/`_ms02_pid_specs`/`resolve_ms02_pid_to_wids` stubs, `wv.has_permission=lambda code: True`). New test `test_prepared_documents_centered_headers_use_align_center`:
  ```python
  resp = user_client.get("/prepared_documents")
  assert resp.status_code == 200
  # The three centered columns now carry the .nx-table align helper on the <th>,
  # so headers no longer render left while bodies render center.
  assert resp.data.count(b'class="px-6 py-3 align-center"') == 3
  ```
- [ ] **Run it, expect RED** (the current `<th>` use `text-center`): `python -m pytest tests/integration/test_workitems_routes.py -k centered_headers -x`.
- [ ] **Implement.** In `templates/prepared_documents.html`, change ONLY the three centered HEADER `<th>` (Collected, Prepared, Octo status) from `class="px-6 py-3 text-center"` to `class="px-6 py-3 align-center"`. The three are byte-identical, so apply the swap to all three occurrences of `<th scope="col" class="px-6 py-3 text-center">` (use `replace_all` or supply the surrounding `{{ _("…") }}` span as unique context per occurrence). Example (Collected):
  ```html
  <th scope="col" class="px-6 py-3 align-center">
    <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Collected") }}</span>
  </th>
  ```
  Leave the three left-aligned headers (`text-left`: PID / Collected by / Prepared by) and ALL body `<td>` unchanged.
- [ ] **Run it, expect GREEN.** Re-run the test above.
- [ ] **Browser-verify + screenshot.** Restart `nx -u -b --loginas:<ms02 user>` (Jinja cache is process-lifetime). Open `/prepared_documents`; confirm COLLECTED / PREPARED / OCTO STATUS headers sit centered over their centered body cells; PID / COLLECTED BY / PREPARED BY stay left. Save `var/screenshots/pdoc-bug1-alignment.png` and `SendUserFile` it (remote session). If column *widths* still look ragged after alignment, note it for Owner action O3.
- [ ] **Commit** (explicit paths only):
  ```
  git add templates/prepared_documents.html tests/integration/test_workitems_routes.py
  SQL_SYNC_SKIP=1 git commit -m "$(cat <<'EOF'
  fix(prepared-docs): center register check-column headers

  The COLLECTED/PREPARED/OCTO STATUS header cells used a bare Tailwind
  text-center utility, which loses to the shared .nx-table thead th
  text-align:left rule, so headers rendered left while their body cells
  rendered centered -> ragged columns. Swap those three th to the
  table-scoped .nx-table .align-center helper (specificity (0,2,0) beats
  the (0,1,2) thead th rule) so headers align with their centered body
  cells. Body cells already centered; no shared CSS change.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

# PHASE 2 — Bug 2: gate the entry button to MS02 target processes

### Task 2: Show "Prepared documents" only when a PDBS target process is selected

**Files:**
- Modify: `nx_lib/views/workitems.py` (`workitems_overview()`)
- Modify: `templates/workitems_overview.html`
- Test: `tests/integration/test_workitems_routes.py` (rewrite `test_prepared_audit_link_renders_when_ms02_active`; add hidden-on-all sibling)

**Interfaces:**
- Consumes: `_ms02_target_processes()` (existing; reads `workitems.filter.process.*` perms via `f"{parts[-2]}.{parts[-1]}"`), `process_name` (already computed in `workitems_overview()` from `request.args.get("prcfW", "all")` and reset to `"all"` if not in `allowed_processes`).
- Produces: a new `render_template` kwarg `prepared_docs_process_match` (bool); the template gate tightens to AND it in.

Caveat (verified): `allowed_processes` is built per-request from the session `permissions` list (`{(perm.split(".")[-2] + "." + perm.split(".")[-1]) for perm in perms if perm.startswith("workitems.filter.process.")}`), NOT from `has_permission`. Patching `has_permission` True does NOT populate it. So the present-case test must seed `workitems.filter.process.sydoc.05_PDBS` into the session (→ `allowed_processes` contains `sydoc.05_PDBS`, the reset is a no-op) AND patch `_ms02_target_processes` to return `["sydoc.05_PDBS"]`. The seeding is sound: the login fixture runs `/login` + `/verify_2fa` (which does `session.clear()`) BEFORE the test body, the test mutates session via `session_transaction()` AFTER login, and the GET does not re-authenticate — so the seed persists into the request.

- [ ] **Rewrite the now-false test** `test_prepared_audit_link_renders_when_ms02_active` (its docstring says "independent of any process filter" and asserts `b"prepared-docs-link" in resp.data` unconditionally — now FALSE under D1). Replace with present-on-PDBS + absent-on-all:
  ```python
  def test_prepared_docs_link_renders_only_for_target_process(
      user_client, workitems_all_perms, monkeypatch
  ):
      """The Workitems toolbar shows the register link ONLY when the selected
      process is an MS02 prepared-docs target process (locked decision)."""
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS

      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])

      # Seed a process perm so allowed_processes contains the target and the
      # route's "reset to all if unknown" guard is a no-op for it. (Login runs
      # before this seed; the GET does not re-auth, so the seed persists.)
      with user_client.session_transaction() as sess:
          sess["permissions"] = sess.get("permissions", []) + [
              "workitems.filter.process.sydoc.05_PDBS",
          ]

      # Selected = the target process -> link present.
      resp = user_client.get("/workitems?prcfW=sydoc.05_PDBS")
      assert resp.status_code == 200
      assert b"prepared-docs-link" in resp.data
      assert b"/prepared_documents" in resp.data

  def test_prepared_docs_link_hidden_on_all_processes(
      user_client, workitems_all_perms, monkeypatch
  ):
      """'All Processes' (and any non-PDBS process) hide the register link."""
      import nx_lib.views.workitems as wv
      from nx_lib.clients import CLIENTS

      monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
      monkeypatch.setitem(CLIENTS, "ms02", object())
      monkeypatch.setattr(wv, "has_permission", lambda code: True)
      monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])

      resp = user_client.get("/workitems")  # defaults to prcfW=all
      assert resp.status_code == 200
      assert b"prepared-docs-link" not in resp.data
  ```
- [ ] **Run it, expect RED** — the current gate ignores the process, so the hidden-on-all assertion fails (and the old test name is gone): `python -m pytest tests/integration/test_workitems_routes.py -k "prepared_docs_link" -x`.
- [ ] **Implement the server flag.** In `workitems_overview()`, just after `ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None` (and after `process_name` is finalized by the `if process_name != "all" and process_name not in allowed_processes: process_name = "all"` block), add:
  ```python
  prepared_docs_process_match = (
      ms02_active
      and prepared_import_perm
      and process_name in _ms02_target_processes()
  )
  ```
  Then add it to the `render_template("workitems_overview.html", …)` kwargs, right after `ms02_active=ms02_active,`:
  ```python
              prepared_import_perm=prepared_import_perm,
              ms02_active=ms02_active,
              prepared_docs_process_match=prepared_docs_process_match,
  ```
  (Defensive: the whole route is wrapped in `try/except → 500.html`; `_ms02_target_processes()` reads `session.get("permissions", [])` and never raises, so this is safe inside the try.)
- [ ] **Implement the template gate.** In `templates/workitems_overview.html`, tighten the existing gate (anchor: `{% if prepared_import_perm and ms02_active %}` wrapping the `data-testid="prepared-docs-link"` anchor):
  ```html
  {% if prepared_docs_process_match %}
  <a href="{{ url_for('prepared_documents') }}"
    class="nx-btn nx-btn--secondary" data-testid="prepared-docs-link">
    <i class="fas fa-file-excel mr-2"></i>{{ _("Prepared documents") }}
  </a>
  {% endif %}
  ```
  (`prepared_docs_process_match` already folds in `prepared_import_perm` and `ms02_active`, so the gate is a single bool. Keep the inner anchor markup byte-identical.)
- [ ] **Run it, expect GREEN.** Re-run; also run the nearby register tests to confirm no regression: `python -m pytest tests/integration/test_workitems_routes.py -k "prepared" -x`.
- [ ] **Browser-verify + screenshots.** Restart `nx -u -b --loginas:<ms02 user>`. On `/workitems`: (a) with "All Processes" selected → button absent; (b) select the PDBS target process from `#prcfW` (the page reloads — the gate is server-side) → button appears. Save `var/screenshots/pdoc-bug2-button-all.png` and `var/screenshots/pdoc-bug2-button-pdbs.png` and `SendUserFile` both.
- [ ] **Commit:**
  ```
  git add nx_lib/views/workitems.py templates/workitems_overview.html tests/integration/test_workitems_routes.py
  SQL_SYNC_SKIP=1 git commit -m "$(cat <<'EOF'
  fix(workitems): gate prepared-docs link to MS02 target processes

  The "Prepared documents" toolbar link showed for every process (and for
  "All Processes"), regardless of relevance. Per the locked decision it must
  appear only when an MS02 prepared-docs target process is selected. Compute
  a server-side prepared_docs_process_match (perm + ms02_active + process_name
  in _ms02_target_processes()) in workitems_overview() and tighten the template
  gate. Rewrite the now-inverted process-independent link test and add the
  hidden-on-all-processes sibling.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

# PHASE 3 — Bug 3: light the preview timeline with the wid's real stage

### Task 3.1: Add a never-raising per-wid Octo status/stage resolver

**Files:**
- Modify: `nx_lib/workitem_sources.py`
- Test: `tests/unit/test_workitem_sources.py`

**Interfaces:**
- Consumes: an Octo engine (passed as a parameter — the module does NOT import `engine_octo_db`, only `engine_nexora_db`) + a single Octo workitem id.
- Produces: `resolve_octo_wid_stage(engine, wid) -> {"status": str|None, "current_stage": str|None}`. Returns `{"status": None, "current_stage": None}` on absent engine / bad wid / not-found / unreachable engine / DB error (D6). `status` ∈ {`Ready`,`In Progress`,`Done`}; `current_stage` ∈ {`Import`,`Extraction`,`Validation`,`Delivery`} — the SAME vocabularies the timeline expects (`stages = ['Import','Extraction','Validation','Delivery']`; `status === 'Done'` lights all steps).

The canonical query to mirror (verified in `nx_lib/workitem_sources.py`, the `SqlServerSource` `WorkitemCTE`): both values are computed via CASE, **not** read as raw columns, and the `CurrentStage` CASE **requires** `INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID`. Reproduce the two CASE blocks verbatim (including `LIKE '%C+A%'`, `'%Imp%'`, `'%Pause%'`/`'%Deletion%'`/`'%Lieferung%'`, and `ELSE 'Extraction'`). The source dedups with `ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC)` then `WHERE rn = 1`; keep that slice scoped to one wid. Row access is pyodbc attribute style (`r.Status`, `r.CurrentStage`), matching the existing `r.Status`/`r.CurrentStage` usage.

- [ ] **Write a failing unit test** in `tests/unit/test_workitem_sources.py` (module imported as `ws`; `app` fixture provides `current_app`). Model the MagicMock stub on `test_sqlserver_source_normalizes_rows` (`fake_cur.fetchone.return_value`, `fake_conn.cursor.return_value = fake_cur`, `eng.raw_connection.return_value = fake_conn`):
  ```python
  def test_resolve_octo_wid_stage_returns_none_without_engine(app):
      with app.app_context():
          assert ws.resolve_octo_wid_stage(None, 42) == {
              "status": None, "current_stage": None,
          }

  def test_resolve_octo_wid_stage_degrades_to_none_on_error(app):
      class Boom:
          def raw_connection(self):
              raise RuntimeError("octo down")
      with app.app_context():
          assert ws.resolve_octo_wid_stage(Boom(), 42) == {
              "status": None, "current_stage": None,
          }

  def test_resolve_octo_wid_stage_maps_status_and_stage(app):
      from unittest.mock import MagicMock
      row = MagicMock(Status="In Progress", CurrentStage="Validation")
      fake_cur = MagicMock()
      fake_cur.fetchone.return_value = row
      fake_conn = MagicMock()
      fake_conn.cursor.return_value = fake_cur
      eng = MagicMock()
      eng.raw_connection.return_value = fake_conn
      with app.app_context():
          assert ws.resolve_octo_wid_stage(eng, 42) == {
              "status": "In Progress", "current_stage": "Validation",
          }
  ```
- [ ] **Run it, expect RED** (function doesn't exist): `python -m pytest tests/unit/test_workitem_sources.py -k resolve_octo_wid_stage -x`.
- [ ] **Implement** in `nx_lib/workitem_sources.py` (near `resolve_ms02_pid_to_wids`; `current_app` and `DB_NEXORA` are already imported at the top of the module):
  ```python
  def resolve_octo_wid_stage(engine, wid):
      """Latest (status, current_stage) for a single default-client Octo
      workitem, using the same CASE-over-join vocabulary the list query emits
      so the preview timeline lights correctly. Returns
      {"status": str|None, "current_stage": str|None}. Never raises: on absent
      engine / bad wid / not-found / DB error -> {"status": None,
      "current_stage": None} (mirrors resolve_ms02_pid_to_wids' degrade
      contract)."""
      empty = {"status": None, "current_stage": None}
      if engine is None or wid in (None, ""):
          return empty
      try:
          wid_int = int(wid)
      except (TypeError, ValueError):
          return empty
      conn = None
      try:
          conn = engine.raw_connection()
          cur = conn.cursor()
          cur.execute(
              """
              WITH WorkitemCTE AS (
                  SELECT
                      CASE
                          WHEN twi.Status = 0 THEN 'Ready' WHEN twi.Status = 5 THEN 'Done' ELSE 'In Progress'
                      END AS Status,
                      CASE
                          WHEN twi.Status = 5 THEN 'Delivery'
                          WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'Validation'
                          WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'Delivery'
                          WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'Import'
                          WHEN tai.ActivityInstanceName LIKE '%Extract%' OR tai.ActivityInstanceName LIKE '%OCR%' THEN 'Extraction'
                          WHEN tai.ActivityInstanceName LIKE '%Pause%' or tai.ActivityInstanceName like '%Deletion%' or tai.ActivityInstanceName like '%Lieferung%' THEN 'Delivery'
                          ELSE 'Extraction'
                      END AS CurrentStage,
                      ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                  FROM t_WorkItems twi
                  INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                  WHERE twi.ID = ?
              )
              SELECT Status, CurrentStage FROM WorkitemCTE WHERE rn = 1
              """,
              [wid_int],
          )
          row = cur.fetchone()
          if not row:
              return empty
          return {"status": row.Status, "current_stage": row.CurrentStage}
      except Exception as e:
          current_app.logger.error(f"resolve_octo_wid_stage({wid}): {e}")
          return empty
      finally:
          if conn is not None:
              conn.close()
  ```
  Keep the two CASE blocks byte-aligned with the list query's CASE so the preview never disagrees with the list for the same wid. Do NOT "simplify" the `LIKE` patterns.
- [ ] **Run it, expect GREEN.**
- [ ] **Commit:**
  ```
  git add nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
  SQL_SYNC_SKIP=1 git commit -m "$(cat <<'EOF'
  feat(workitems): add never-raising per-wid Octo stage resolver

  resolve_octo_wid_stage(engine, wid) returns {status, current_stage} for a
  single default-client Octo workitem using the same CASE-over-join
  vocabulary as the list query (joining t_ActivityInstances, ROW_NUMBER
  latest-row slice), degrading to {None, None} on absent engine / bad wid /
  DB error so callers can render regardless of Octo health. Used next to
  light the prepared-docs preview timeline.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

### Task 3.2: Resolve the stage in the route and emit it on the Preview button

**Files:**
- Modify: `nx_lib/views/workitems.py` (`prepared_documents()` + the `workitem_sources` import block)
- Modify: `templates/prepared_documents.html` (Preview button)
- Test: `tests/integration/test_workitems_routes.py`

**Interfaces:**
- Consumes: `resolve_octo_wid_stage` (Task 3.1); `CLIENTS["default"].runtime_engine` (verified == `engine_octo_db`; `CLIENTS` is already imported in `views/workitems.py`). Do **NOT** pass `engine_ms02_docfields_pg` — that is the PDBS Postgres docfields engine (wrong id-space; would silently return no rows under the never-raise contract → grey timeline forever).
- Produces: `octo_status[pid]` gains `"status"` and `"current_stage"`; the Preview `<button>` gains `data-status` / `data-current-stage`.

- [ ] **Write a failing route-render test.** Extend the gate-and-mock recipe; patch `resolve_octo_wid_stage` so no Octo engine is needed. New test `test_prepared_docs_preview_button_carries_stage`:
  ```python
  monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
  monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
  monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})
  monkeypatch.setattr(
      wv, "resolve_octo_wid_stage",
      lambda e, w: {"status": "In Progress", "current_stage": "Validation"},
  )
  monkeypatch.setattr(wv, "has_permission", lambda code: True)
  resp = user_client.get("/prepared_documents")
  assert resp.status_code == 200
  assert b'data-wid="42"' in resp.data
  assert b'data-status="In Progress"' in resp.data
  assert b'data-current-stage="Validation"' in resp.data
  ```
  (Use the full `count_prepared_documents`/`fetch_prepared_documents_page` stubs from `test_prepared_documents_preview_button_requires_details_view`. `resolve_octo_wid_stage` must be importable as `wv.resolve_octo_wid_stage` — added in the implementation step.)
- [ ] **Run it, expect RED.**
- [ ] **Implement the import + resolution.** In `nx_lib/views/workitems.py`, add `resolve_octo_wid_stage` to the existing alphabetically-sorted `from ..workitem_sources import (… resolve_ms02_pid_to_wids …)` block. Then in `prepared_documents()`, extend the octo_status loop (anchor: `octo_status[pid] = {"in_octo": True, "wid": wids[0]}`):
  ```python
          if pid_to_wids:
              for pid, wids in pid_to_wids.items():
                  if wids:
                      wid = wids[0]
                      stage = resolve_octo_wid_stage(
                          CLIENTS["default"].runtime_engine, wid
                      )
                      octo_status[pid] = {
                          "in_octo": True,
                          "wid": wid,
                          "status": stage["status"] or "",
                          "current_stage": stage["current_stage"] or "",
                      }
  ```
  (`resolve_octo_wid_stage` never raises, so no extra guard; on a dead/unreachable Octo the values are `""` and the timeline simply stays grey — same as today, no regression.)
- [ ] **Implement the button markup.** In `templates/prepared_documents.html`, add the two `data-*` to the Preview button (anchor: `data-testid="prepared-docs-preview" data-wid="{{ st.wid }}" data-pid="{{ r.pid }}"`):
  ```html
  <button type="button" class="text-indigo-600 underline"
          data-testid="prepared-docs-preview"
          data-wid="{{ st.wid }}" data-pid="{{ r.pid }}"
          data-status="{{ st.status }}" data-current-stage="{{ st.current_stage }}">
    <i class="fas fa-eye mr-1"></i>{{ _("Preview") }}
  </button>
  ```
  (`st = octo_status.get(r.pid)`; `st.status`/`st.current_stage` are `""` when unresolved — harmless.)
- [ ] **Run it, expect GREEN.** Also re-run `-k "prepared"` to confirm the existing preview-button test still passes (it only asserts `data-wid="42"`, unaffected).
- [ ] **Commit:**
  ```
  git add nx_lib/views/workitems.py templates/prepared_documents.html tests/integration/test_workitems_routes.py
  SQL_SYNC_SKIP=1 git commit -m "$(cat <<'EOF'
  feat(prepared-docs): carry Octo status/stage to the preview button

  prepared_documents() now resolves the cross-referenced Octo wid's live
  status + current_stage via resolve_octo_wid_stage (passing the default
  client's runtime engine, NOT the MS02 docfields PG engine) and emits them
  as data-status / data-current-stage on the Preview button, so the preview
  modal can light the timeline. Degrades to empty (grey timeline) when Octo
  is unreachable.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

### Task 3.3: Forward status/current_stage from the button into render() opts

**Files:**
- Modify: `templates/js/_prepared_documents_js.html` (`openPreview` + the Preview click handler)
- Test: `tests/integration/test_workitems_routes.py` (markup-presence assertion)

**Interfaces:**
- Consumes: `btn.dataset.status` / `btn.dataset.currentStage` (Task 3.2); the existing `opts.status` / `opts.currentStage` fallback in `NexoraWorkitemDetail.render` (verified: `const status = containerEl.dataset.status || (opts && opts.status) || '';` and `const currentStage = containerEl.dataset.currentStage || (opts && opts.currentStage) || '';`). **No edit to `templates/js/_workitem_detail_panel_js.html`** (D5).
- Produces: the preview modal renders the timeline lit to the wid's stage.

- [ ] **Write a failing route-render test.** Assert the server-emitted `data-*` reach the markup (robust to JS formatting; preferred over brittle JS-token matching). This can be the same `test_prepared_docs_preview_button_carries_stage` from Task 3.2 — if you already added the three `data-*` assertions there, no new route test is needed for 3.3; the JS forwarding is verified by the manual browser step below. (If you want a JS-presence anchor, assert a single stable token, e.g. `assert b"openPreview(btn.dataset.wid, btn.dataset.status, btn.dataset.currentStage)" in resp.data`, matching the exact call you write.)
- [ ] **Run it, expect RED** (the click handler currently calls `openPreview(btn.dataset.wid)` only).
- [ ] **Implement.** In `templates/js/_prepared_documents_js.html`, change the click handler to forward the two datasets, and `openPreview` to accept + pass them. Click handler (anchor: `if (btn) { event.preventDefault(); openPreview(btn.dataset.wid); return; }`):
  ```js
  if (btn) {
    event.preventDefault();
    openPreview(btn.dataset.wid, btn.dataset.status, btn.dataset.currentStage);
    return;
  }
  ```
  `openPreview` signature + render call (anchors: `function openPreview(wid) {` and the `window.NexoraWorkitemDetail.render(wid, previewBody, { readOnly: true, perms: window.__pdocPreviewPerms || {}, });` block):
  ```js
  function openPreview(wid, status, currentStage) {
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
        readOnly: true,
        perms: window.__pdocPreviewPerms || {},
        status: status || "",
        currentStage: currentStage || "",
      });
    });
    previewModal.classList.remove("hidden");
  }
  ```
  (`previewBody` has no `data-status`/`data-current-stage`, so the shared `render`'s `containerEl.dataset.* || opts.*` falls through to `opts.status`/`opts.currentStage` — exactly the existing fallback. No panel-partial change.)
- [ ] **Run it, expect GREEN.**
- [ ] **Browser-verify (the load-bearing manual check) + screenshot.** Restart `nx -u -b --loginas:<ms02 user>`. On `/prepared_documents`, click a Preview link. Because dev has no reachable Octo, `resolve_octo_wid_stage` returns `{None, None}` locally → the timeline stays grey (expected). To prove the JS plumbing lights the timeline, do a **synthetic** check: in DevTools set a Preview button's `data-status="In Progress" data-current-stage="Validation"`, click it, and confirm the timeline lights to Validation (completed steps filled, current step active, progress line scaled). Save `var/screenshots/pdoc-bug3-timeline.png` and `SendUserFile` it. State plainly in the caption: the DOM lighting is browser-verified with a mocked stage; live-Octo correctness is Owner action O1.
- [ ] **Commit:**
  ```
  git add templates/js/_prepared_documents_js.html tests/integration/test_workitems_routes.py
  SQL_SYNC_SKIP=1 git commit -m "$(cat <<'EOF'
  fix(prepared-docs): light preview timeline from the wid's stage

  openPreview now forwards the Preview button's data-status/data-current-stage
  into NexoraWorkitemDetail.render via opts, which the shared panel already
  falls back to (containerEl.dataset.* || opts.*). The
  Import->Extraction->Validation->Delivery timeline in the read-only preview
  modal now reflects the document's current Octo stage instead of rendering
  all-grey. No change to the shared panel renderer.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

# PHASE 4 — Docs & changelog sync

### Task 4: Update CHANGELOG + CLAUDE.md to match the shipped behaviour

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

**Interfaces:** docs only; no code, no test.

- [ ] **CHANGELOG.md.** Under `## [Unreleased]`: rewrite the line that currently says the prepared-docs button "is now visible whenever the user holds `workitems.import.preparedaudit` AND MS02 is active — decoupled from the selected process filter" (anchor: the `decoupled from the selected process filter` wording). New wording: the prepared-docs **link** is now shown only when an MS02 prepared-docs target process is selected (was: perm + ms02_active, any process). Add two `### Fixed` bullets — register check-column header alignment, and the preview-modal timeline now reflecting the document's current Octo stage. Keep house style (match surrounding bullet format).
- [ ] **CLAUDE.md.** Update the prepared-docs paragraph: the sentence "The workitems-page button is now a link to that page." → note it is shown only for MS02 target processes; and the "read-only **Preview** modal" sentence → note the preview timeline now reflects the resolved wid's live `current_stage`/`status`.
- [ ] **Verify no i18n / no migration drift.** Confirm `git diff --stat` across all phases shows ONLY the intended files and no `messages.pot` / `sql/_migrations/**` changes (this plan adds no strings, no SQL). Run the full slice once more: `python -m pytest tests/integration/test_workitems_routes.py -k "prepared or workitems_overview" tests/unit/test_workitem_sources.py -x`.
- [ ] **Commit:**
  ```
  git add CHANGELOG.md CLAUDE.md
  SQL_SYNC_SKIP=1 git commit -m "$(cat <<'EOF'
  docs(prepared-docs): changelog + CLAUDE.md for preview/register polish

  Record the three fixes: PDBS-target-process gating of the register link
  (correcting the stale "decoupled from the process filter" line), centered
  register check-column headers, and the preview timeline now reflecting the
  document's live current Octo stage.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Gotchas & notes

- **Bug-3 engine handle is make-or-break.** Pass `CLIENTS["default"].runtime_engine` (verified == `engine_octo_db`) into `resolve_octo_wid_stage`. `views/workitems.py` imports `CLIENTS` but NOT `engine_octo_db`, and `workitem_sources.py` imports only `engine_nexora_db` — that is exactly why the helper takes the engine as a parameter. Passing `engine_ms02_docfields_pg` (the PDBS Postgres docfields engine) would silently return no rows under the never-raise contract → permanently grey timeline.
- **Keep the two CASE blocks byte-aligned.** `resolve_octo_wid_stage`'s Status/CurrentStage CASE must match the list query's CASE verbatim (including `'%C+A%'`, `'%Imp%'`, `'%Pause%'`/`'%Deletion%'`/`'%Lieferung%'`, lowercase `or`/`like` as in the source, and `ELSE 'Extraction'`). The CASE produces the string vocabulary the timeline needs (`Ready`/`In Progress`/`Done`; `Import`/`Extraction`/`Validation`/`Delivery`) — it is NOT raw `twi.Status` ints or a (nonexistent) `twi.CurrentStage` column.
- **Never raise from status resolution (D6).** A down/unreachable Octo must yield `{None, None}` and a still-rendering register with a grey timeline — not a 500. Mirror `resolve_ms02_pid_to_wids`' `current_app.logger.error(...)` + return-None pattern.
- **The `render` fallback already exists** — do NOT edit `templates/js/_workitem_detail_panel_js.html`. Confirmed: `const status = containerEl.dataset.status || (opts && opts.status) || '';` (and the matching `currentStage` line); `buildPanelMarkup` writes them into `data-current-stage`/`data-status` on `#timeline-container-${workitemid}`; `renderWorkitemTimeline` reads those and lights all steps on `status === 'Done'`. Changing the shared signature would risk the working `/workitems` row-expand path.
- **wv-local `has_permission` trap.** The `workitems_all_perms` fixture patches `nx_lib.security.has_permission`, but the route bodies call the name imported into `nx_lib.views.workitems`. Always also `monkeypatch.setattr(wv, "has_permission", lambda code: True)` (and use the `code != "…"` form to test perm-absence — see `test_prepared_documents_preview_button_requires_details_view`).
- **`allowed_processes` ≠ `has_permission` (Bug-2 test).** `allowed_processes` is built from the session `permissions` list via the `workitems.filter.process.` prefix (`{parts[-2]}.{parts[-1]}`), NOT from `has_permission`. The present-case test seeds `workitems.filter.process.sydoc.05_PDBS` via `session_transaction()` so `allowed_processes` contains `sydoc.05_PDBS` and the `process_name → 'all'` reset is a no-op. This is sound (verified): login (`/login` + `/verify_2fa`, which `session.clear()`s) runs before the seed, and the GET does not re-authenticate, so the seed persists into the request.
- **Bug-1 specificity (verified).** `.nx-table .align-center` is (0,2,0) — two classes — and beats `.nx-table thead th` (0,1,2) on the second component, so the header centers. Body `<td>` `text-center` (0,1,0) has no `thead`-scoped competitor on `tbody`, so body cells already center — leave them untouched.
- **JS DOM lighting is browser-verified, not unit-verified.** Bug 3's actual timeline lighting happens in `renderWorkitemTimeline` in the browser; pytest only asserts the server-emitted `data-*` attributes (robust) and (optionally) a single stable JS call-token. The lit timeline is confirmed by the manual synthetic screenshot, and real-Octo-data correctness is Owner action O1. Do NOT claim the timeline is "verified working" from a green pytest run alone.
- **N+1 note (future optimization).** `resolve_octo_wid_stage` adds one Octo round-trip per resolved PID on the register page (up to 40 rows/page; `per_page = 40`). It mirrors existing per-row patterns and degrades safely, but on a Defender-scanned PROD path it adds latency. A future optimization could batch the status lookup into one query (`WHERE twi.ID IN (...)` + ROW_NUMBER) — left out of this minimal-diff v1.
- **Template cache:** restart `nx -u` after EVERY template/JS edit before browser-checking, or you'll screenshot stale HTML.
- **Explicit `git add <paths>` only.** Never sweep the strays (`helpers/notify-toast.ps1`, `.claudeignore`, `scripts/new-process.py`, the `0032_*` migration). Use `SQL_SYNC_SKIP=1 git commit` if the SQL hook trips on INT CRLF drift — never `--no-verify`. Remote session: stop at commit (no push, no PR).
- **No new strings → no pybabel cycle.** All labels are already `_()`-wrapped; the new `data-*` values are DB-sourced. If you find yourself adding a `{{ _('…') }}`, stop and run the i18n cycle + `test_translations.py`.
