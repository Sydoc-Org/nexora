# Bug-Hunt Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team). Anchors are **function names + quoted snippets**, never line numbers — re-`Grep` before editing. Source triage: `var/bug-hunt-2026-07-20.md` (this session), every finding independently second-agent-verified.

**Goal:** Fix the 22 verified, in-scope bugs from the 2026-07-20 bug hunt across invoices, generali, dashboard, workitems-export, auth, and shared plumbing — grouped into commit-sized phases — plus an optional backend-plumbing phase.

**Architecture:** Mostly small, surgical server-side and JS-partial changes following patterns already present in sibling code (an `escapeHtml` helper already exists in `_generali_project_management_js.html`; row-scope gating already exists in the Attendance/BaseServices/ProjectManagement generali endpoints; `@require_permission` is the established route guard; `_wi_cache_key()` is the established client-qualified cache key). No schema migration. No new permission codes. A few new i18n msgids (one late pybabel cycle).

**Tech Stack:** Flask/pyodbc/SQLAlchemy, vanilla-JS Jinja partials, pytest unit/integration, Playwright e2e, Flask-Babel de/fr/it, flask_limiter.

## Global constraints

- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python; `.venv` is test-only. Reset TEST DB before any e2e tier: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`.
- **Jinja template cache is process-lifetime** — `nx -r` (restart) before any manual browser check.
- **PROD URL prefix:** hand-built URLs in JS partials go through the `API_PREFIX` idiom. None of these fixes add new URLs, but don't regress existing ones.
- **i18n:** new user-facing strings use `_()` / `gettext`; JS-partial strings use the `{{ _("…")|tojson }}` idiom already in each file. Run ONE late pybabel cycle (final task of each phase that added msgids, or a single cycle before hand-back) — `tests/unit/test_translations.py` is expected RED until then.
- **CHANGELOG:** add a single consolidated `[Unreleased] / Fixed` block (Task 23) rather than per-task churn.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via `git commit -F - <<'EOF' … EOF`. If `ruff-format` rewrites a file the first attempt fails — `git add -u` and recommit. If INT unreachable at commit: `SQL_SYNC_SKIP=1`, never `--no-verify`.
- **Commit trailer names the EXECUTING model.** Blocks below say `Claude Sonnet 5` (planned executor); substitute the real executor if different.
- **Branch:** work directly on `feature/2.5.64`. Commit per task. **Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes.
- **Stray working-tree file:** `static/css/reporting.css` is modified by unrelated in-flight reporting work — never `git add` it; stage only each task's named files.

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **XSS fix = HTML-escape at the sink**, reusing/copying the existing `escapeHtml()` from `_generali_project_management_js.html`, not server-side sanitization. | Keeps stored data intact; matches the pattern the codebase already uses. Escape at render is the correct layer. |
| D2 | **Invoice PDF scoping** reuses `get_bexio_client_ids()` (the allow-list `api_invoices` already uses) — resolve the invoice's `contact_id` and reject if not in the caller's allowed set. | Same trust boundary as the list endpoint; no new permission surface. |
| D3 | **PDQM read endpoints copy the Attendance pattern verbatim** — `restrict_to_self = not edit.organizational and not edit.transorganizational`, then add `UserID = ?` / `session["userid"]`. | Sibling modules already do exactly this; PDQM is a copy-paste omission. |
| D4 | **delete-user becomes one all-or-nothing transaction** (drop the per-statement `cursor.commit()`; single commit at end; rollback on error) **and adds the missing `ReportShares`/`ReportSchedules`/`Reports` deletes** (owned rows deleted in the same transaction). | Half-deleted users are the worst outcome; deleting a user should delete their owned reporting artifacts atomically. See Owner action 2 if reports should instead be reassigned. |
| D5 | **Backlog KPI:** translate `status:"Ready"` into a real predicate matching the legacy `backlog_count()` semantics where the stat table supports it; if a given stat table can't express backlog, the widget returns an explicit `no_data` warning rather than a wrong count. Do **not** leave `WHERE 1=1`. | A silently-wrong headline number is worse than an honest empty. Legacy `total_backlog_count()` is the reference definition. |
| D6 | **2FA rate limit:** `@limiter.limit("10 per hour")` on both `init_2fa` and `verify_2fa` POST paths, keyed by remote address (the limiter default). | Caps the 6-digit brute-force (1e6 space) far below feasibility without hurting real users who fat-finger a code a few times. |
| D7 | **Login: `session.clear()` at the top of every credential-accepted branch**, not just the 2FA-enabled one. | Prevents a prior user's keys surviving into a new pre-auth on a shared browser. |
| D8 | **Password-reset returns the SAME neutral message** whether or not the email exists (mirror the login uniform-message pattern); still only sends mail on a hit. | Closes the enumeration oracle; matches the app's own login behavior. |
| D9 | **Compound-identity fixes pass the client the row already carries** — never re-probe. Cache keys become client-qualified via the existing `_wi_cache_key()` helper. | The row dicts already include `client`; discarding it is the bug. |

## Owner actions (not for the executor)

1. **Review + push `feature/2.5.64`** when the plan completes (pre-push gate runs the FULL suite incl. e2e; run `scripts/test_db_reset.py` first).
2. **Decide delete-user report handling (D4):** default is "delete the user's owned reports/schedules/shares atomically." If owned reports should instead be **reassigned** to an admin or blocked with a message, say so — Task 13 changes accordingly.
3. **Backlog KPI semantics (D5):** confirm "Current backlog" should mean the legacy `C+A` activity-type count. If the widget engine's stat tables can't express that, the fallback is to drop the default "Current backlog" widget until wired — confirm that's acceptable.
4. The two deferred admin privilege-escalation endpoints (`save_user_overrides`, `save_access_profile`) are **out of scope** here pending your "who holds `admin.edit.user.override` / `admin.edit.accessprofile`" decision.

---

# PHASE 1 — Stored-XSS escaping pass (frontend)

Shared root cause: JS partials build `innerHTML` from server data without escaping. Fix = escape at the sink using the existing helper.

### Task 1: Generali documents — escape free-text fields

**Files:**
- Modify: `templates/js/_generali_documents_js.html`
- Reference (copy helper from): `templates/js/_generali_project_management_js.html` (`escapeHtml`)
- Verify: `tests/e2e/` (add or extend a generali-documents e2e) OR browser check

**Defect:** `renderTable` and `renderDetailCard` (and the `channelBadge`/`nkBadge` fallback branches) interpolate free-text `DOC_*` fields from `v_ReportJobJoinDefinitions` into template literals assigned to `.innerHTML` with no escaping. A scanned document whose `DOC_KONTAKTPERSON` (etc.) contains `<img src=x onerror=…>` executes for any `generali.documentlist.view` user. Verified conf 100.

- [ ] **Step 1 — Add the helper.** Copy the `escapeHtml(s)` function from `_generali_project_management_js.html` (the `String(s).replace(/[&<>"']/g, …)` form) into `_generali_documents_js.html` near the top of its script block (skip if the file already has one — `Grep` first).
- [ ] **Step 2 — Wrap every server-string sink.** In `renderTable`, `renderDetailCard`, `channelBadge`, and `nkBadge`, wrap each interpolated document value in `escapeHtml(...)`: e.g. `${escapeHtml(doc.doc_dokumententyp || '—')}`, `${escapeHtml(doc.doc_empfaenger || '—')}`, `channelBadge`'s `${escapeHtml(val)}`, and the detail-card `val = \`<span …>${escapeHtml(val)}</span>\``. Do NOT escape values you build yourself (class names, tone tokens) — only server-derived strings.
- [ ] **Step 3 — Verify.** Restart (`nx -r`), open Generali → Documents with a row whose text field contains `<b>x</b>`; confirm it renders as literal text, not bold/executed. If adding an e2e: stub `/api/generali/documents` to return a row with `DOC_KONTAKTPERSON: "<img src=x onerror=window.__x=1>"`, assert `page.evaluate("window.__x")` is undefined and the cell text contains the literal tag.
- [ ] **Step 4 — Commit:**

```bash
git add templates/js/_generali_documents_js.html
git commit -F - <<'EOF'
fix(generali): escape document free-text fields against stored XSS

renderTable/renderDetailCard/channelBadge/nkBadge interpolated DOC_*
values from v_ReportJobJoinDefinitions into innerHTML unescaped. Route
them through escapeHtml (same helper the project-management partial uses)
so scanned-document content can no longer execute in a viewer's session.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 2: Dashboard activity feed — escape extracted fields + id

**Files:**
- Modify: `templates/js/_dashboard_js.html` (`updateActivityFeed`)
- Verify: browser check or e2e stub

**Defect:** `updateActivityFeed` builds `container.innerHTML` interpolating `act.id`, `act.time`, `act.process`, and `act.fields` key/value pairs (OCR/parsed document content) unescaped; `act.id` is also spliced into an inline `onclick="…${act.id}…"`. Verified conf 75 (needs crafted document content).

- [ ] **Step 1 — Add/confirm an `escapeHtml` helper** in `_dashboard_js.html` (copy the same helper; `Grep` first — the file may already use `escapeHtml`/`textContent` elsewhere).
- [ ] **Step 2 — Escape every server value** in the `fieldBadges`/row template: `${escapeHtml(key)}`, `${escapeHtml(val)}`, `${escapeHtml(act.process)}`, `${escapeHtml(act.time)}`. For the `onclick`/href carrying `act.id`, prefer moving off inline `onclick` to a `data-wid`/`data-client` attribute + delegated listener; minimally, `encodeURIComponent(act.id)` in the URL and `escapeHtml` in any text position.
- [ ] **Step 3 — Verify.** Restart; with a stubbed `/api/recent_activity` (or a document field containing `<b>x</b>`), confirm literal rendering and a working row click.
- [ ] **Step 4 — Commit** (`fix(dashboard): escape recent-activity feed values against stored XSS`).

### Task 3: Notification bell — escape message/icon/link

**Files:**
- Modify: `templates/js/_header_js.html` (`updateNotificationUI`)
- Verify: browser check

**Defect:** `updateNotificationUI` interpolates `n.Message`, `n.Icon`, and the built `link` into an HTML string inserted via `insertAdjacentHTML` with no escaping. Notification `Message` embeds the raw acting `username`, and `admin_add_user` doesn't validate username characters. Verified conf 75. (Chat/comment/assignment feeders are being removed, but the sink stays — escape it defensively.)

- [ ] **Step 1 — Add/confirm `escapeHtml`** in `_header_js.html` (`Grep` first).
- [ ] **Step 2 — Escape** `${escapeHtml(n.Message)}` and, if `n.Icon` is server-provided and used as a class/markup, validate it against a known set or escape it; run the `link` value through the existing `API_PREFIX` idiom + `encodeURIComponent` on any id segment.
- [ ] **Step 3 — Verify.** Restart; create a notification whose message contains `<b>x</b>` (e.g. via any surviving notification path) and confirm literal rendering in the bell.
- [ ] **Step 4 — Commit** (`fix(header): escape notification bell content against stored XSS`).

---

# PHASE 2 — Access-control / permission gaps (backend)

### Task 4: Invoice PDF download — client scoping (IDOR)

**Files:**
- Modify: `nx_lib/views/invoices.py` (`download_invoice_pdf`)
- Test: `tests/integration/test_invoices_routes.py`

**Defect:** `download_invoice_pdf(invoice_id)` is gated only by blanket `invoices.download` and calls `get_bexio_invoice_pdf(invoice_id)` with no client check, unlike `api_invoices` which filters via `get_bexio_client_ids()`. A user scoped to ClientX can enumerate `/invoice/<id>/pdf` and pull any client's invoice. Verified conf 92.

- [ ] **Step 1 — Write the failing test.** In `tests/integration/test_invoices_routes.py`, add a test: user whose perms grant `invoices.download` + `invoices.view.ClientX` only; request an `invoice_id` belonging to ClientY (mock Bexio metadata `contact_id = ClientY`); assert 403/404, not a PDF. (Follow the file's existing mock idiom for Bexio + `get_bexio_client_ids`.)
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In `download_invoice_pdf`, before returning the PDF: fetch the invoice's `contact_id` (a Bexio `kb_invoice/<id>` metadata lookup, or reuse whatever `get_bexio_invoice_pdf` already retrieves) and check it against `set(get_bexio_client_ids())`; if not a member, `raise PermissionDenied` (403) or return 404. Keep the existing `invoices.download` gate.
- [ ] **Step 4 — GREEN run** + the invoices test module.
- [ ] **Step 5 — Commit** (`fix(invoices): scope PDF download to the caller's allowed clients`).

### Task 5: PDQM read endpoints — own-records row scope

**Files:**
- Modify: `nx_lib/views/generali.py` (`generali_pdqm_monthreport`, `api_generali_pdqm_organizations`, `api_generali_pdqm_list`)
- Reference: the Attendance equivalents in the same file (`restrict_to_self` pattern)
- Test: `tests/integration/` generali tests (extend existing generali test module)

**Defect:** the three PDQM read endpoints never add the `UserID = session["userid"]` restriction that every sibling module applies for callers lacking `*.edit.organizational`/`*.edit.transorganizational`. A `generali.pdqm.view`-only user sees every org's entries. PDQM's own edit/delete DO call `_check_generali_record_org`, proving intent. Verified conf 100.

- [ ] **Step 1 — Write the failing test.** User with `generali.pdqm.view` and NO pdqm edit perms; seed PDQM rows for two different users/orgs; hit `/api/generali/pdqm` (list), `/api/generali/pdqm/organizations`, and the month report; assert only the caller's own rows/orgs come back.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In each of the three endpoints, copy the Attendance pattern verbatim: compute `restrict_to_self = not has_permission("generali.pdqm.edit.organizational") and not has_permission("generali.pdqm.edit.transorganizational")` (confirm the exact PDQM edit permission codes via `Grep` around `can_add_for_org`/`can_add_transorg` in the PDQM section), then when `restrict_to_self` add `WHERE … UserID = ?` with `session.get("userid")` to the list + month-report queries and gate the organizations scan the same way Attendance does.
- [ ] **Step 4 — GREEN run** + generali test module.
- [ ] **Step 5 — Commit** (`fix(generali): restrict PDQM read endpoints to own records without edit perms`).

### Task 6: Dashboard KPI endpoints — add permission guard

**Files:**
- Modify: `nx_lib/views/dashboard.py` (`dashboard_processed_over_time`, `dashboard_kpi_stats`, `dashboard_hourly_stats`, `dashboard_avg_processing_time`)
- Test: `tests/integration/` dashboard tests

**Defect:** these four legacy KPI endpoints check only `"username" not in session`, missing `@require_permission("dashboard.view")` present on every sibling route. A user holding only a grantable `dashboard.filter.process.*` (but not `dashboard.view`) can curl real KPI data. Verified conf 100.

- [ ] **Step 1 — Write the failing test.** Authenticated user WITHOUT `dashboard.view`; GET each of the four endpoints; assert 403.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Add `@require_permission("dashboard.view")` to each of the four routes (it's already imported in the module). Keep the existing per-process filter logic.
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(dashboard): require dashboard.view on the four legacy KPI endpoints`).

### Task 7: 2FA endpoints — rate limit

**Files:**
- Modify: `nx_lib/views/auth.py` (`init_2fa`, `verify_2fa`)
- Test: `tests/integration/` auth tests (assert the limit decorator is applied, or that the Nth rapid POST returns 429)

**Defect:** neither 2FA verification route has `@limiter.limit`, and the `Limiter` has no `default_limits`; a holder of a valid `pre_2fa_userid` session can brute-force the 6-digit TOTP unlimited. Verified conf 75.

- [ ] **Step 1 — Implement (D6).** Add `@limiter.limit("10 per hour")` to both `init_2fa` and `verify_2fa` (confirm `limiter` is importable in the module the way `login`/`request_password_reset` reference it; `Grep` those two for the exact import/usage).
- [ ] **Step 2 — Verify.** Add a test that fires 11 rapid POSTs to `/verify_2fa` with a bad code and asserts the last returns 429; or, if the test harness disables the limiter, assert the route carries the limit in `app.url_map`/decorator metadata following the pattern used for `login`'s limit test if one exists.
- [ ] **Step 3 — Commit** (`fix(auth): rate-limit TOTP 2FA verification against brute force`).

### Task 8: Login — clear session on every credential-accepted branch

**Files:**
- Modify: `nx_lib/views/auth.py` (`login`)
- Test: `tests/integration/` auth tests

**Defect:** only the 2FA-enabled branch calls `session.clear()`; the first-time-reset and 2FA-setup branches set pre-auth keys without clearing a prior session. On a shared browser, user A's `userid`/`username`/`permissions` survive under B's pending pre-auth. Verified conf 75.

- [ ] **Step 1 — Write the failing test.** Seed a session with user A fully authed; POST valid credentials for user B (who needs first-time reset or 2FA setup); assert the resulting session contains none of A's keys (`userid`/`username`/`permissions`) — only B's pre-auth key.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement (D7).** Add `session.clear()` at the top of the `not stored_init_reset` and `not stored_2fa` branches (mirroring the 2FA-enabled `else` branch), before setting `pre_auth_userid`/`pre_2fa_userid`.
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(auth): clear stale session in all login pre-auth branches`).

### Task 9: Password reset — uniform message (user enumeration)

**Files:**
- Modify: `nx_lib/views/auth.py` (`request_password_reset`)
- Test: `tests/integration/` auth tests

**Defect:** returns `_("Invalid Email Address")` for unknown emails vs a success message for known ones, and only sends mail on a hit — leaking account existence. Verified conf 75.

- [ ] **Step 1 — Write the failing test.** POST a known email and an unknown email; assert both responses are byte-identical (same flash/JSON message, same status).
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement (D8).** Return the same neutral message (e.g. `_("If that email is registered, a reset link has been sent.")`) on both branches; keep `send_reset_email()` gated on the row existing. Add the new msgid.
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(auth): use a uniform password-reset message to stop user enumeration`).

---

# PHASE 3 — Compound-identity (client+id) fixes

### Task 10: Dashboard recent-activity — pass the client hint

**Files:**
- Modify: `nx_lib/views/dashboard.py` (`api_recent_activity`)
- Reference: `nx_lib/workitem_sources.py` (`recent_activity_rows` returns `client`; `get_domain_for_workitem(wid, client_hint=…)`)
- Test: `tests/unit/` or `tests/integration/` dashboard test

**Defect:** `api_recent_activity` calls `get_domain_for_workitem(row["id"])` and discards `row["client"]` the row already carries; a colliding-id MS02 workitem shows the default client's fields. Verified conf 95.

- [ ] **Step 1 — Write the failing test.** Mock `recent_activity_rows` to return a row `{id: 1216, client: "ms02", …}`; assert `get_domain_for_workitem` is called with `client_hint="ms02"` (or that the resolved domain matches ms02, not default).
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement (D9).** Change the call to `get_domain_for_workitem(row["id"], client_hint=row.get("client"))` (confirm the parameter name via `Grep` of the def in `workitem_sources.py`).
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(dashboard): pass client hint when resolving recent-activity workitems`).

### Task 11: CSV export — client-qualified keys

**Files:**
- Modify: `nx_lib/views/workitems.py` (`export_workitems_csv`)
- Reference: same file — `_wi_cache_key(prefix, workitem_id, domain)` (already used by the detail/media code, e.g. `_wi_cache_key("media_info", workitem_id, domain)`), and `get_domain_for_workitem(workitem_id, client_hint=None)` in `nx_lib/workitem_sources.py`
- Test: `tests/integration/` workitems export test

**Defect:** `export_workitems_csv` keys `domains[wid]`, `details_map[wid]`, and the `media_*`/`audithistory_*` caches by bare id (no client), unlike `_wi_cache_key(prefix, wid, domain)` used by the detail/media code elsewhere in the same file. Exporting both clients' copies of a colliding id makes one row carry the other client's fields/images/audit. Verified conf 85.

- [ ] **Step 1 — Write the failing test.** Build an export set containing two rows with the same `workitemid` but different `client` (e.g. `1216`/default and `1216`/ms02, each with distinct field values); run the export; assert each CSV row carries its OWN client's values (no cross-contamination).
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement (D9).** Resolve the domain with `get_domain_for_workitem(wid, client_hint=w["client"])`, then key `domains` and `details_map` on `(w["client"], wid)` and replace each per-fetch cache literal with `_wi_cache_key(prefix, wid, domain)` — matching how the detail/media code already keys them. Re-`Grep` each bare literal (`f"media_info_{wid}"`, `f"media_data_{wid}"`, `f"audithistory_{wid}"`) in `export_workitems_csv` and convert it.
- [ ] **Step 4 — GREEN run** + the workitems export module.
- [ ] **Step 5 — Commit** (`fix(workitems): key CSV-export caches by client+id to stop cross-client mixups`).

### Task 12: Export selected — compound id end to end

**Files:**
- Modify: `nx_lib/views/workitems.py` (`export_workitems_csv` `specific_ids` filter) and `templates/js/_workitems_overview_js.html` (checkbox `data-id` + `selectedWorkitemIds`)
- Reference: `renderTable`'s `rowKey = \`${client}-${workitemid}\`` in the same JS file
- Test: `tests/e2e/` workitems test or integration test

**Defect:** "Export selected" filters by bare `workitemid`; checkboxes carry bare id. Selecting only the default-client row of a colliding id also exports the MS02 row. Verified conf 85.

- [ ] **Step 1 — Write the failing test.** (Integration) POST the export with `ids=["default-1216"]`-shaped selection; assert only the default row is exported when an ms02 `1216` also matches the base filter. (Or e2e: check one of two colliding rows, export, assert one row.)
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In the JS: change the checkbox to carry the compound key (`data-id="${rowKey}"`, matching `renderTable`'s `rowKey`), and `selectedWorkitemIds.add(cb.dataset.id)` now stores compound keys. In `export_workitems_csv`: parse `specific_ids` as compound `client-id` pairs and filter on `(w["client"], w["workitemid"])` membership (keep back-compat: if a bare numeric id arrives, match any client — or bump a request version; simplest is to accept the compound form the UI now sends).
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(workitems): make "export selected" client-aware for colliding ids`).

---

# PHASE 4 — Data-correctness / robustness

### Task 13: Delete-user — atomic cascade + missing report FKs

**Files:**
- Modify: `nx_lib/views/admin.py` (`admin_delete_user`)
- Reference DDL: `sql/NexoraDB/Tables/dbo.Reports.sql`, `dbo.ReportSchedules.sql`, `dbo.ReportShares.sql`
- Test: `tests/integration/` admin test

**Defect:** eight child deletes each `cursor.commit()` before the final `DELETE FROM users`; the cascade omits `Reports.OwnerUserID`/`ReportSchedules.OwnerUserID`/`ReportShares.SharedWithUserID` (all FK NO ACTION). Deleting a report-owning user wipes their other rows, then the users-delete throws (swallowed) → half-deleted, undeletable user. Verified conf 100.

- [ ] **Step 1 — Write the failing test.** Seed a user who OWNS a report (+ a schedule, + a share); call the delete route; assert either the user AND their report artifacts are all gone, OR (if D4-reassign chosen) the user is gone and reports reassigned — but never a half-state where child rows are gone and the user row survives.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement (D4).** Remove the per-statement `cursor.commit()` calls; run all deletes on one connection/transaction; add `DELETE FROM ReportShares WHERE SharedWithUserID = ?`, `DELETE FROM ReportSchedules WHERE OwnerUserID = ?`, `DELETE FROM Reports WHERE OwnerUserID = ?` (in FK-safe order: shares/schedules before reports before users); `commit()` once at the end; on exception `conn.rollback()` and surface a real error. Confirm the exact child-table list and FK order by `Grep`ping the three DDL files for `REFERENCES … Users`.
- [ ] **Step 4 — GREEN run** + admin test module.
- [ ] **Step 5 — Commit** (`fix(admin): make user deletion atomic and cascade reporting artifacts`).

### Task 14: Recent-activity — guard empty ignore-list

**Files:**
- Modify: `nx_lib/workitem_sources.py` (`SqlServerSource.recent_rows`)
- Reference: `PostgresSource.recent_rows` (the `if activity_ignore_csv:` guard) and `nx_lib/process_helpers.py` (`get_activity_instances_to_ignore`)
- Test: `tests/unit/` workitem_sources test

**Defect:** `SqlServerSource.recent_rows` appends `AND … NOT IN ({csv})` unconditionally; PG guards with `if csv:`. `get_activity_instances_to_ignore()` returns `""` on an empty table (normal) → `NOT IN ()` syntax error → swallowed → Recent Validations silently empty for the default client. Verified conf 90.

- [ ] **Step 1 — Write the failing test.** Call `SqlServerSource.recent_rows` with `activity_ignore_csv=""`; assert the generated SQL omits the `NOT IN` clause entirely (or that the method returns rows rather than `[]` against a fake cursor). Also cover `None`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Wrap the clause: `if activity_ignore_csv: clauses.append(f"AND tai.ActivityInstanceName NOT IN ({activity_ignore_csv})")` — mirroring the PG path. Separately, give `get_activity_instances_to_ignore`'s `except` an explicit `return ""` (Task 25 also touches its logging).
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(workitems): guard empty activity-ignore list in recent-activity query`).

### Task 15: Backlog KPI — real predicate

**Files:**
- Modify: `nx_lib/views/dashboard.py` (`_build_kpi_sql`)
- Reference: `nx_lib/workitem_sources.py` (`total_backlog_count`/`backlog_count`, `ActivityTypes.Name = 'C+A'`)
- Test: `tests/unit/` dashboard test

**Defect:** `_build_kpi_sql` reads `status = filters.get("status")` but only uses it to gate the date clause; it's never a predicate. The default "Current backlog" widget (`status:"Ready"`, no date) becomes `COUNT(*) … WHERE 1=1` = all history, and any `status:"Ready"`+date widget silently drops the date filter. Verified conf 85.

- [ ] **Step 1 — Decide (D5 / Owner action 3).** Confirm backlog = legacy `C+A` semantics. If the widget's stat table can't express it, the fallback is an explicit `no_data` warning / dropping the default widget.
- [ ] **Step 2 — Write the failing test.** For a `status:"Ready"` KPI config, assert the built SQL contains a real backlog predicate (not `WHERE 1=1`) and that a `status:"Ready"` + explicit date range keeps the date clause.
- [ ] **Step 3 — RED run.**
- [ ] **Step 4 — Implement.** Turn `status` into an actual predicate matching the reference definition; decouple the date-clause gating from the status value (a date range should always apply when present). If unsupported for a table, return the `no_data` warning path.
- [ ] **Step 5 — GREEN run.**
- [ ] **Step 6 — Commit** (`fix(dashboard): compute backlog KPI with a real predicate, not all-rows`).

### Task 16: Bexio search — keep partial results

**Files:**
- Modify: `nx_lib/views/invoices.py` (`search_bexio_invoices`)
- Test: `tests/unit/` invoices test

**Defect:** the `except requests.exceptions.RequestException` inside the per-client loop does `return []`, discarding invoices already gathered from earlier clients. A timeout on client 2 of 3 yields an empty list. Verified conf 100.

- [ ] **Step 1 — Write the failing test.** Mock 3 client calls where the 2nd raises `RequestException`; assert the result contains clients 1 and 3's invoices (partial), not `[]`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In the `except RequestException` (and `json.JSONDecodeError`) branches, `current_app.logger.error(...)` then `continue` instead of `return []`; return `all_invoices` after the loop. (Optionally surface a partial-failure flag to the caller — YAGNI unless the UI needs it.)
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(invoices): keep partial results when one Bexio client search fails`).

### Task 17: Prepared-docs — honest in_octo flag

**Files:**
- Modify: `nx_lib/views/workitems.py` (`prepared_documents`)
- Test: `tests/integration/` prepared-documents test

**Defect:** `in_octo` is set `True` whenever a wid mapping exists, not when `resolve_octo_wid_stage` actually found a row (`stage["status"]` can be `None`). The template then shows Preview / "Open in Workitems" buttons for PIDs whose wid isn't in Octo → broken buttons. Verified conf 80.

- [ ] **Step 1 — Write the failing test.** Mock `resolve_octo_wid_stage` to return `{"status": None, "current_stage": None}` for a mapped wid; assert `octo_status[pid]["in_octo"]` is `False`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Derive `in_octo` from the resolution result — e.g. `in_octo = bool(stage and stage.get("status"))` — instead of the presence of a wid.
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(workitems): set prepared-docs in_octo from actual Octo resolution`).

### Task 18: get_allowed_client_details — init conn/cursor

**Files:**
- Modify: `nx_lib/views/invoices.py` (`get_allowed_client_details`)
- Test: `tests/unit/` invoices test

**Defect:** `conn`/`cursor` are referenced in `finally` (`if cursor: … if conn:`) but assigned inside `try`; if `raw_connection()` throws, the `finally` raises `UnboundLocalError`, masking the intended `return []`. Sibling `get_bexio_client_ids` initializes `conn = None; cursor = None`. Verified conf 80.

- [ ] **Step 1 — Write the failing test.** Patch `engine_nexora_db.raw_connection` to raise; assert the function returns `[]` (not raises).
- [ ] **Step 2 — RED run** (expect `UnboundLocalError`).
- [ ] **Step 3 — Implement.** Add `conn = None` and `cursor = None` before the `try` (mirroring `get_bexio_client_ids`).
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(invoices): initialize conn/cursor so DB failure degrades gracefully`).

### Task 19: get_bexio_client_ids — log + typed return

**Files:**
- Modify: `nx_lib/views/invoices.py` (`get_bexio_client_ids`)
- Test: `tests/unit/` invoices test

**Defect:** on exception it `print(e)` (invisible under IIS) and implicitly returns `None`; downstream `sel_id in allowed_ids` raises `TypeError` on `None`. Verified conf 75.

- [ ] **Step 1 — Write the failing test.** Force an exception inside `get_bexio_client_ids`; assert it returns `[]` (a list), not `None`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Replace `print(e)` with `current_app.logger.error(...)` and add `return []` in the `except` branch.
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(invoices): log and return empty list on client-id lookup failure`).

### Task 20: _check_generali_record_org — fix own-record comparison

**Files:**
- Modify: `nx_lib/security.py` (`_check_generali_record_org`)
- Test: `tests/unit/test_security.py` (or nearest)

**Defect:** `record_uid` (int, from a SQL int column) is compared `== session.get("userid")` (a str set on every login path); `int == str` is always `False`, so the "own record always allowed" fast-path never fires. If an admin re-orgs a still-logged-in user, they can't edit/delete their own entries until re-login. Verified conf 85.

- [ ] **Step 1 — Write the failing test.** Session `userid="42"` (str); `rec = (42, someOrg)`; call `_check_generali_record_org`; assert it returns (allowed) without raising, even when the session org differs from the record's org.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Coerce both sides: `if str(record_uid) == str(session.get("userid")): return` (matches the `str(...) != str(...)` idiom used elsewhere in the generali add paths).
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(security): coerce ids so own-record generali edit/delete is always allowed`).

---

# PHASE 5 — Small functional fixes

### Task 21: index() — permission-aware landing

**Files:**
- Modify: `nx_lib/views/core.py` (`index`)
- Reference: `nx_lib/security.py` (`startpage_redirect_to`, `page_visibility`); `nx_lib/views/auth.py` call sites
- Test: `tests/integration/` core/routing test

**Defect:** `index()` hardcodes `redirect(url_for("dashboard"))`; `dashboard` requires `dashboard.view`. A user without it who hits `/` gets a 403 instead of a usable landing page — every other post-auth path uses `startpage_redirect_to(page_visibility())`. Verified conf 75.

- [ ] **Step 1 — Write the failing test.** Authed user without `dashboard.view` but with (say) `workitems` access; GET `/`; assert redirect to their permitted landing route, not a 403 to `/dashboard`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Replace the hardcoded redirect with `return redirect(url_for(startpage_redirect_to(page_visibility())))` (match the exact call signature used at the `auth.py` sites; `Grep` them).
- [ ] **Step 4 — GREEN run.**
- [ ] **Step 5 — Commit** (`fix(core): route "/" to a permitted landing page instead of hardcoded dashboard`).

### Task 22: Invoice status label/filter reconcile

**Files:**
- Modify: `nx_lib/views/invoices.py` (`map_invoice_status` and the `status_map` in `search_bexio_invoices`)
- Test: `tests/unit/` invoices test

**Defect:** `map_invoice_status` labels any non-9 status as "Open", but the Open filter matches only `kb_item_status_id == 8`. An invoice with status 3 shows "Open" yet vanishes when filtered by Open. Verified conf 75.

- [ ] **Step 1 — Decide the intended mapping.** Simplest consistent rule: define "Open" as "not Paid" in BOTH places, or enumerate the real Bexio status ids. Recommended: make the filter match "everything that maps to Open" (i.e. `!= 9`) so label and filter agree.
- [ ] **Step 2 — Write the failing test.** An invoice with `kb_item_status_id = 3`: assert it labels "Open" AND passes the `status="Open"` filter.
- [ ] **Step 3 — RED run.**
- [ ] **Step 4 — Implement.** Align `status_map["Open"]` with the label rule (e.g. filter Open = all non-9, Paid = 9), or centralize the mapping in one helper both call.
- [ ] **Step 5 — GREEN run.**
- [ ] **Step 6 — Commit** (`fix(invoices): reconcile invoice status label with the status filter`).

### Task 23: i18n cycle + changelog

**Files:**
- Modify: `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ `.mo`), `messages.pot`, `CHANGELOG.md`

- [ ] **Step 1 — Extract/update/compile.** `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → translate the new msgids (Task 9 reset message, any XSS-phase strings) in de/fr/it (non-fuzzy) → `pybabel compile -d translations`. **Diff-sweep** each `.po` for the malformed-msgstr trap (pybabel can drop characters from existing lines).
- [ ] **Step 2 — Run** `tests/unit/test_translations.py` GREEN.
- [ ] **Step 3 — Changelog.** Add one `[Unreleased] / Fixed` block summarizing the security + correctness fixes (XSS escaping, invoice PDF scoping, PDQM scope, dashboard KPI guard, 2FA rate limit, atomic user delete, compound-identity export/activity fixes, etc.).
- [ ] **Step 4 — Commit** (`chore(i18n): translations + changelog for bug-hunt remediation`).

---

# PHASE 6 — Backend plumbing (OPTIONAL — lower priority, hunter-flagged, not second-verified)

### Task 24: octo.get_workitemdata_param — real error handling

**Files:** Modify `nx_lib/octo.py` (`get_workitemdata_param`). **Defect:** no `raise_for_status`/try-except; indexes `response.json()["DocumentID"]` unconditionally, yet callers guard `if returndata:` expecting a falsy "not found" — an Octo hiccup raises instead, and in `api_recent_activity` blanks (and 2-min-caches) the whole feed. **Change:** wrap in try/except like its sibling `get_access_token`; return `None`/falsy on failure so the existing caller guards work. **Verify:** unit test — patch requests to raise, assert falsy return. **Commit:** `fix(octo): return falsy on workitem-data fetch failure instead of raising`.

### Task 25: field/table_locations media_offset — count PDF pages

**Files:** Modify `nx_lib/field_locations.py` (`_count_image_media`/`count_image_media`) and `nx_lib/table_locations.py` (`count_image_media`). **Defect:** they count only `IMG_EXTS`, not PDF-expanded pages, so in a mixed PDF+image container the "Show sources" overlay highlights the wrong page for later leaves. **Change:** account for PDF page expansion consistent with `octo.get_extensions_urls_fields` (count a PDF as its `n_pages` slots). **Verify:** unit test with a mixed PDF+image container asserting the correct offset. **Commit:** `fix(workitems): count PDF pages in media offset for source highlighting`.

### Task 26: print → logger sweep

**Files:** Modify `nx_lib/octo.py`, `nx_lib/process_helpers.py`. **Defect:** several `except` handlers `print()` instead of `current_app.logger` — invisible under IIS/wfastcgi. **Change:** replace `print(e)` with `current_app.logger.error(...)`; ensure each `except` returns a typed value (ties into Task 14's `get_activity_instances_to_ignore` return). **Verify:** grep shows no `print(` left in these handlers. **Commit:** `chore(logging): route backend exception handlers through the app logger`.

---

## Gotchas & notes

- **Test infra:** e2e requires `scripts/test_db_reset.py` first and has NO Statistics DB (reporting/stats can't run for real — stub). Integration tests for permission gates follow the existing `tests/integration/` fixtures that seed `session["permissions"]`.
- **Compound identity:** the `client` value lives on every row dict already; the fix is always "pass it through," never "re-probe." `_wi_cache_key(prefix, workitem_id, domain)` (in `nx_lib/views/workitems.py`) is the canonical per-workitem cache key, where `domain` comes from `get_domain_for_workitem(wid, client_hint=client)`.
- **Don't fix descoped code:** all chat (`_chat_js.html`, `chat.py`), workitem tags/comments/mentions, the stale-tag-badge bug, and the two admin priv-esc endpoints are intentionally OUT of scope.
- **Delete-user (Task 13)** is the highest-blast-radius change — do it on its own commit, run the full admin test module, and confirm FK order against the live DDL before trusting the child-table list.
- **pybabel malformed-msgstr trap:** after `pybabel update`, diff each `.po` — it silently mangles existing lines (e.g. dropped letters). Sweep before compile.
- **One late i18n cycle** (Task 23), not per-task — `test_translations.py` stays RED until then; `--deselect` it in fast tiers meanwhile.
