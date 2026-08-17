# Chat, Collaboration & Notification-Bell Removal + 2026-07-23 Bug-Hunt Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchors are **function names + quoted snippets**, never line numbers — re-`Grep` before editing (Part A reshapes `nx_lib/views/workitems.py`, `nx_lib/workitem_sources.py` and `templates/js/_workitems_overview_js.html` before Part B touches them). Source triage: `var/bug-hunt-report.md` (2026-07-23 hunt, 57 findings, adversarially verified) — read it for per-bug failure scenarios instead of this plan restating them. Every surviving fix anchor below was re-verified present in current code on `feature/2.5.65` during planning; every voided bug was confirmed to live entirely inside code Part A removes.

**Goal:** PART A — deprecate (archive, never hard-delete) three unused features: the chat page + backend, ALL workitem collaboration (tags, priority, assignments, comments incl. @mentions), and the notification bell (its only three producers — chat messages, comment @mentions, assignments — all die with Part A). Data is preserved by renaming the nine dead tables `dbo.decapitated_*`; the eight dead permission rows are deleted by migration. PART B — fix the surviving, re-verified bugs from the 2026-07-23 hunt (1 critical, 18 high, ~28 medium after voiding). The nine bugs living inside removed code are VOIDED by their removal task and must never be fixed in place.

**Architecture:** Part A is a structural excision consolidated by surface: view modules deleted outright (git history is the archive for Python), whole template files moved to the existing `archive/` convention, shared files (detail panel, overview JS, header) surgically pruned. Removal is sequenced frontend-first, then backend, then bell, then migrations — so INT never serves a page calling a missing endpoint, and no code references a renamed table when the migration auto-applies. The DB change is two migrations: `0042` (drop the `dbo.Users` FKs on the dead tables + `sp_rename` all nine to `decapitated_*`) and `0043` (delete the eight dead permission rows child-first). Part B follows the 2026-07-20 remediation plan's style: small surgical fixes reusing established sibling patterns (`_wi_cache_key` client-qualified caching, the `restrict_to_self` scoping pattern, the `_authorize_sql_target`/`_has_acked` gates, the `API_PREFIX` idiom) — no new abstractions.

**Tech Stack:** Flask/pyodbc/SQLAlchemy (+psycopg2 for MS02 PG), vanilla-JS Jinja partials, pytest unit/integration, Playwright e2e, Flask-Babel de/fr/it, T-SQL migrations via `scripts/db-migrate.py` + pre-commit hooks.

## Context an engineer needs (read first)

- **Removal inventory (Part A):** 9 tables (`Chat_Conversations`, `Chat_Messages`, `Chat_Participants`, `Tags`, `Workitem_Tags`, `Workitem_Comments`, `Comment_Mentions`, `Workitem_Metadata`, `Notifications` — note "the comments table" is TWO tables); 8 permission codes (`chat.view`, `workitems.details.add.tag`, `workitems.details.set.priority`, `workitems.details.assign.users`, `workitems.details.add.comment`, `workitems.filter.tag`, `workitems.filter.priority`, `workitems.filter.assignedUser` — the camelCase is real; **no `notifications.*` codes exist anywhere** — the bell routes are gated only by `if "userid" not in session`); 3 Python modules deleted (`nx_lib/views/chat.py`, `nx_lib/views/notifications.py`, `nx_lib/notifications.py`); 2 templates archived (`chat.html`, `_chat_js.html`).
- **`create_notification` has exactly three call sites** — `chat.py` (message), `workitems.py` `add_workitem_comment` (@mention), `workitems.py` `assign_workitem` — all removed, which is why the bell goes too (D-NOTIF). `scripts/news/sendReleaseNotice.py` sends Graph email, not Notifications rows.
- **`dbo.Workitem_Metadata` is 100% collaboration** (columns: `MetadataID`, `WorkitemId`, `Priority`, `LastUpdatedByUserID`, `LastUpdatedAt`, `AssignedUserID` — nothing else; the MS02 PID register lives in `dbo.PreparedDocuments` + `dbo.WorkitemSourceCache`, untouched). Whole-table rename is correct for all nine tables — none is shared with a surviving feature. "Last movement at" in the list is Octo `twi.ModifiedAt`, not this table — its sort bug survives.
- **The shared detail panel (`templates/js/_workitem_detail_panel_js.html`, `window.NexoraWorkitemDetail`) has THREE consumers:** the workitems row-expand (`window.__workitemDetailPerms`), the prepared-docs register preview (`window.__pdocPreviewPerms`), and the reporting drill drawer (`window.__rpDrillPerms`, shipped 2.5.64). All three keep fields/images/source-highlighting/timeline/audit and lose collaboration — in BOTH the editable and the readOnly branch (the readOnly branch renders comments+tags today via `buildReadonlyCommentsMarkup`; per D-PANEL it goes). **`get_audithistory` is the Octo processing trail** (Octo `processService/WorkItemAudits` REST API, `ActivityInstanceID` → activity names, zero NexoraDB user actions) — KEEP it, its route, its `workitems.details.view.audit` perm, and the panel's `loadHistory`.
- **The collaboration tables are embedded in SURVIVING list queries:** `nx_lib/workitem_sources.py` has the `LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata` joins, the `TagsJSON` subquery over `Workitem_Tags`/`Tags`, the tag/priority/assigned allow-set resolver, and the priority+tags attach helper. If these survive to the migration commit, the whole workitems overview dies on INT. Phase 3 strips them; Phase 5's preflight Grep is the guard.
- **Migration ordering is load-bearing:** the pre-commit `sql-migrate-int` hook auto-applies migrations to INT **at commit time**, and `sql-sync-check` regenerates the per-object dumps (old `dbo.X.sql` files disappear, `dbo.decapitated_X.sql` appear — stage them, never hand-edit). All code references to the old table names must be gone (Phases 1–4) before the `0042` commit lands (Phase 5). **Do not reorder phases.**
- **Next free migration number: `0042`** (`sql/_migrations/NexoraDB/` ends at `0041_ignore_pdbs_statistik_deletion_markers.sql` — re-verified during planning).
- **Archive convention:** archived files are completely unreferenced dead weight kept for resurrection (precedents: `templates/js/archive/_tour_js.html`, `templates/admin/archive/user_management.html`, `static/css/archive/`). Stale references *inside* archived files are accepted as-is — do not "fix" them. `templates/archive/` does not exist yet — Task 1 creates it. Archive dirs ship to PROD today (`deploy.yml` `/XD` has no `archive` entry) and that is harmless precedent — no deploy change (Owner action 3 may opt in). `tests/unit/test_template_url_prefix.py` scans archive dirs — the chat files already pass the `API_PREFIX` rule; don't strip it from anything you archive.
- **i18n:** `babel.cfg` extracts `templates/**.html` *including archives*, so archived template msgids stay in the pot; deleted **Python** msgids (chat/notification flash strings, collaboration messages) and collab markup excised from *surviving* templates drop out → `tests/unit/test_translations.py::test_pot_is_in_sync` is RED from Task 1 until the single late pybabel cycle (final task). `--deselect` it in every intermediate run.
- **Workitem identity is compound (client, id)** — ids collide across clients (1216 on INT). Several Part B fixes are "pass the client the row already carries; key caches via `_wi_cache_key(prefix, wid, domain)`" — never re-probe.
- **Already fixed in 2.5.64 (PR #124) — do NOT re-plan or re-fix:** invoice-PDF IDOR, PDQM row-scope, dashboard KPI guards, 2FA rate-limit, login `session.clear()` in all branches, password-reset UNIFORM MESSAGE (today's residual is the timing oracle only), delete-user atomicity + report FKs (the atomic block in `admin_delete_user` stays byte-for-byte), recent-activity `client_hint` pass-through (residuals: missing `client` in the response + the sensitive doc-field gate), CSV-export compound-id cache keys, the `/api/users` cache-key suffix `_c{int(_can_mention)}` (that endpoint is now removed anyway), Bexio partial results, backlog KPI predicate, the notification-bell XSS hardening (removed wholesale with the bell).
- **Voided by Part A (9 — handled by their removal task, no fix task exists anywhere in this plan, on purpose):** chat-message stored XSS (`_chat_js.html`), workitem-comment stored XSS (panel `loadCollaborationData`, sink `${comment.CommentText.replace(…)}` into innerHTML), tag name/color XSS (overview `renderTable`), `upload_chat_file` IDOR, `start_conversation` any-target, delete-user tag/metadata wipe lines, comment-id race (`SELECT TOP 1 CommentID … ORDER BY CommentID DESC`), stale priority-flag/tag-preview (`refreshWorkitemUI`/`handleSetPriority`), and the page-init user-list cache key (`_users_key = f"users_mentions_{'all' if _all_users else _org}"` — the whole users block is removed; **the endpoint itself SURVIVES for `field_config`**, it is pruned, not deleted).
- **NOT voided (previously flagged "partial"):** the CSV-export heavy-include limit fully SURVIVES — the heavy includes are `fields`/`history`/`images` (all surviving features, zero collaboration). Full fix task in Part B.
- **Trap:** `showNotification(...)` in several JS partials is the client-side **toast** helper — unrelated to the bell. Never remove it.
- **GitNexus:** the MCP tools were unavailable during recon; every anchor here is Grep/Read-verified instead. If they're available to the executor, impact checks are advisory — do not block on them.

## Global constraints

- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved. If a Part-B snippet is gone, check whether Part A already removed the surrounding block — then flag it, don't guess.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python; `.venv` is test-only. Reset TEST DB before any e2e tier: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`. The TEST env has **no Statistics DB** — reporting/stats integration tests mock the engines; e2e stubs the network (the `_stub_run_ok` pattern; always stub `/api/reporting/run` before clicking in reporting e2e).
- **Jinja template cache is process-lifetime** — `nx -r` (restart) before any manual browser check; `nx -u -b --loginas:<user>` for Playwright; screenshots to `var/screenshots/` and send them for frontend-visible changes (remote-session rule).
- **PROD URL prefix:** hand-built URLs in JS partials go through the `API_PREFIX` idiom. No task adds new URL literals; don't regress existing ones (incl. inside archived files).
- **Migrations:** the pre-commit hook auto-applies to INT at commit and re-dumps per-object DDL — stage the regenerated `sql/NexoraDB/**` dumps, never hand-edit them. Offline escape hatch: `SQL_SYNC_SKIP=1 git commit …` — **never `--no-verify`**. PROD receives migrations automatically pre-app-stop via `deploy.yml`.
- **i18n:** ONE late pybabel cycle (final task) covering both the Part-A msgid removals and any new Part-B msgids. `test_translations.py` expected RED until then — `--deselect tests/unit/test_translations.py` in intermediate runs. After `pybabel update`, **diff-sweep every `.po`** (malformed-msgstr trap: pybabel has silently mangled existing lines before, e.g. the dropped "T" from "T-SQL").
- **CHANGELOG:** one consolidated `[Unreleased] / ### Removed` addition (Task 12) and one `### Fixed` block (final task) — no per-task churn.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via `git commit -F - <<'EOF' … EOF`. Compressed tasks show the subject only — the executor writes a 1–2 line body. If `ruff-format` or the SQL hooks rewrite files, the first attempt fails — `git add -u` (plus regenerated dumps) and recommit.
- **Commit trailer names the EXECUTING model.** Blocks below say `Claude Sonnet 5` (planned executor); substitute the real executor if different.
- **Branch:** work directly on `feature/2.5.65`. Commit per task. **Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes (remote-session rule). The branch carries 3 unpushed owner commits — never rebase/reset it.
- **Stage only each task's named files.** If stray 0-byte junk files appear (ruflo background-agent artifact), `rm` them, never stage them.

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D-DATA | **No table drops.** Rename all nine collaboration tables `dbo.X` → `dbo.decapitated_X` via guarded `sp_rename` in migration `0042`. Recon confirmed `Workitem_Metadata` holds ONLY collaboration columns — whole-table rename, no column surgery; no dead table is shared with a surviving feature. | Data preserved and reversible (a mirror-image migration resurrects), yet obviously dead. `sp_rename` keeps constraints/indexes under their old auto-names — acceptable. |
| D-FK | `0042` **also drops the FK constraints referencing `dbo.Users`** on the seven dead tables that carry them, looked up dynamically via `sys.foreign_keys` (auto-generated names differ per environment — never hardcode). Intra-group FKs (Chat_Messages→Chat_Conversations, Workitem_Tags→Tags) stay — both sides die together. | Part A removes `admin_delete_user`'s collaboration child-deletes; the NO-ACTION FKs would otherwise make any user with legacy collab rows undeletable. Re-add FKs on resurrection. |
| D-NOTIF | Remove the bell entirely: `nx_lib/views/notifications.py` (routes `get_notifications`, `mark_notifications_as_read`), `nx_lib/notifications.py` (`create_notification`), the `_header.html`/`_header_js.html` bell UI, decapitate `dbo.Notifications`. No permission rows to delete — none exist. | Its only three producers are all removed; a consumer with no producers is dead weight. |
| D-PERMS | Remove the 8 dead codes from `page_visibility()`/route guards/templates AND delete their DB rows in migration `0043`, children first: `AccessProfilePermission` → `UserPermissionOverride` → `Permission` (both child tables FK `Permission.PermissionID` with NO CASCADE; rows for the dead codes WILL exist — the access-control drawer's Deny-default bug wrote them). Mirror in `sql/test/seed.sql`. | Row deletion is trivially reversible; mirrors the app's own `api_admin_permission_delete` child-first order. |
| D-PANEL | The shared panel keeps fields/images/source-highlighting/timeline/**Octo audit history** and `attachLightbox`; it loses `buildCollaborationMarkup`, `buildReadonlyCommentsMarkup` (the readOnly comments/tags card goes too), `renderTagsInDetails`, `loadCollaborationData`, `window.mentionableUsers`, and the `perms.setPriority/addTag/assignUsers/addComment` contract keys — across all THREE consumers. | Owner decision; audit history confirmed processing trail, not a user-action log. |
| D-ARCHIVE | Archive **whole template files only**: `templates/chat.html` → new `templates/archive/`; `templates/js/_chat_js.html` → existing `templates/js/archive/`. Excisions from shared files rely on git history (partial snapshots drift). Python modules are deleted, not archived. No `deploy.yml` change — archives ship today, precedent accepts it. | Matches the `_tour_js.html`/`user_management.html` precedent; `git log --follow` preserves history. |
| D-SEQ | Every code reference to a dead table or permission is removed in commits **before** the migration commits; `0042`/`0043` are the LAST code-touching Part-A commits, followed only by docs. Frontend strips land before their backend counterparts so INT never serves a page calling missing endpoints. | The pre-commit hook applies migrations to INT at commit time; a surviving reference (e.g. the `Workitem_Metadata` join in the list query, or `admin_delete_user`'s `"delete from tags …"`) breaks INT instantly. |
| D-CSVLIM | The heavy-include export rule becomes **server-enforced**: `include=` (any of `fields`/`history`/`images`) requires an explicit `ids` selection of ≤10 compound `client-id` pairs, else 400 with a translated message. | The ≤10 gate exists only client-side (`isSelection = selectedIds.size > 0 && selectedIds.size <= 10`); an `include=` request without ids walks up to `EXPORT_MAX_ROWS` doing per-row Octo fetches. Owner action 5 may adjust. |
| D-DEVLOGIN | Default guard for `dev_login`: keep the `IS_PROD` 404 **and** additionally require a loopback `request.remote_addr` (`127.0.0.1`/`::1`). Owner-gated (Owner action 2) — may be overridden to an env-flag variant or accept-as-designed. | Preserves the `nx -u -b --loginas:` Playwright workflow (local browser → localhost) with zero CLI changes, while closing the remote INT/STAGING password+2FA bypass. |
| D-RUNSQL | The AI agent's `run_sql_bound` enforces the exact gates the HTTP run route uses — `_authorize_sql_target(target)` (backed by the `_SQL_TARGET_PERMS` map) + `_has_acked` — before `_run_sql`; failures return a tool-visible error string, never a 500. | One trust boundary for sandbox SQL regardless of which surface submits it. |
| D-CTE | Sandbox row cap: plain SELECTs keep the existing `SELECT TOP (n) * FROM (…) AS _q` wrap; **WITH-rooted queries pass through unwrapped** and the executor enforces the cap fetch-side via `fetchmany(cap + 1)` (truncation flagged), applied to every path. | `SELECT TOP … FROM ( WITH … )` is invalid T-SQL; a CTE rewrite is fragile; fetch-side capping is parser-free and covers both branches identically. |
| D-KPI | KPI cards request **undimensioned totals** — the card's run payload omits breakdown dims — instead of client-side aggregation. | Summing rows client-side is wrong for avg/min/max metrics; the run backend already supports zero-dim totals (shipped with the Simple tabs). |
| D-RESET | Close the password-reset timing oracle by dispatching `send_reset_email` on a daemon thread (both branches return immediately); make the token single-use via a consumed-token cache mark; `session.pop("email_for_password_reset", None)` on every `set_new_password` exit. | Uniform message shipped in 2.5.64 (D8); response time and replayability are the residuals. Per-process cache under wfastcgi makes single-use best-effort across workers — accepted, noted in code. |
| D-DOTENV | Fix `nx_lib/config.py` precedence by loading `env/{ENVIRONMENT}.env` (and the deprecated root fallback) FIRST and the bare `load_dotenv()` SECOND, all `override=False`, yielding OS env > env-specific file > root `.env`. | Matches the documented contract without `override=True`'s side effect of files clobbering real OS environment variables. |
| D-I18N | ONE pybabel cycle at the very end covering Part A removals + Part B additions. Archived templates keep their msgids (babel scans archive dirs); removed msgids become obsolete `#~` entries in the `.po` files — harmless. | Matches the prior plan's single-late-cycle convention; `test_pot_is_in_sync` diffs both directions so it stays RED in between. |
| D-VOID | Bugs inside removed code are voided by their removal task and never fixed in place (list in Context). | Fixing code that is deleted in the same plan is waste. |

## Owner actions (not for the executor)

1. **Review + push `feature/2.5.65`** when the plan completes. The pre-push gate runs the FULL suite incl. Playwright e2e — run `scripts/test_db_reset.py` first and `uv pip install -r requirements.txt` if the venv drifted. PROD receives migrations `0042`/`0043` automatically via the deploy workflow (pre-app-stop).
2. **`dev_login` (D-DEVLOGIN):** confirm the loopback guard, pick the env-flag variant (`NEXORA_DEV_LOGIN=1`, set by the `nx` CLI), or say "accept as designed" (then the task is skipped). Task 22 is gated on this answer.
3. **`deploy.yml` `/XD archive`:** default is NO change (archives ship, as the three existing archive dirs do today). Opting in also purges those existing dirs from PROD via `/MIR` on the next deploy — say so explicitly if wanted (note: robocopy `/XD` matches the bare dir name at ANY depth).
4. **PROD/INT `static/uploads/chat/` files:** recommendation is keep on disk (data preservation; `uploads` is already `/XD`-excluded so deploys never touch them). Say if you want server-side cleanup scheduled instead.
5. **CSV heavy-include rule (D-CSVLIM):** confirm "400 without ids / with >10 ids" vs silently capping.
6. **After ship:** the MEMORY.md note "tags/priority still shared between colliding ids — open" becomes moot; Confluence republishes the doc edits on your push; resurrection path for any decapitated table is a mirror-image migration (rename back + re-add Users FKs + reseed the 8 permission rows + `git mv` the archived templates back).

---

# PART A — REMOVAL

# PHASE 1 — Remove chat

### Task 1: Chat backend, nav wiring, permission plumbing; templates → archive

**Files:**
- Delete: `nx_lib/views/chat.py`, `tests/e2e/test_chat.py`, `tests/integration/test_chat_routes.py`
- Archive (git mv): `templates/chat.html` → `templates/archive/chat.html` (create the dir), `templates/js/_chat_js.html` → `templates/js/archive/_chat_js.html`
- Modify: `nx_lib/__init__.py`, `nx_lib/security.py`, `templates/_header.html`, `templates/js/_header_js.html`, `tests/unit/test_create_app.py`, `tests/unit/test_security.py`, `tests/unit/test_coverage_thresholds.py`

**Scope/defect:** all six chat routes (`chat_page`, `get_conversations`, `start_conversation`, `get_chat_messages`, `send_chat_message`, `upload_chat_file`) live in `nx_lib/views/chat.py`'s `register_routes`; the module goes whole. `url_for('chat_page')` appears in the `_header.html` nav_items entry and the `_header_js.html` command-palette entry — a leftover is a hard Jinja `BuildError` on every page, so header + route removal are ONE commit. Voids the chat stored-XSS, the `upload_chat_file` IDOR and the `start_conversation` any-target findings. `chat.view` is the only chat permission code.

- [ ] **Step 1 — Write the failing tests.** In `tests/unit/test_create_app.py`: delete `test_create_app_registers_chat_endpoint`; remove `chat_page` and every chat endpoint name from the endpoint-census lists (`Grep` the exact names); remove `"chat.view"` from any seeded `fake_session["permissions"]` and every `chatPagePerm` assertion. In `tests/unit/test_security.py`: drop the `chatPagePerm` expectations from the `page_visibility`/`startpage_redirect_to` tests. In `tests/unit/test_coverage_thresholds.py`: drop the `"views/chat.py"` entry.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_create_app.py tests/unit/test_security.py -q` — the census fails against unmodified code (chat endpoints still registered).
- [ ] **Step 3 — Implement (backend).** `git rm nx_lib/views/chat.py`. In `nx_lib/__init__.py` remove `chat` from the `from .views import (…)` block and delete `chat.register_routes(app)`. In `nx_lib/security.py` delete `"chatPagePerm": has_permission("chat.view")` from `page_visibility()` and `"chatPagePerm": "chat_page"` from `startpage_redirect_to`'s `perm_to_function` map.
- [ ] **Step 4 — Implement (UI + archive).** In `templates/_header.html` delete the nav item `{'perm': pageV.chatPagePerm, 'url': url_for('chat_page'), 'icon': 'fa-comments', 'label': _('Chat'), …}`. In `templates/js/_header_js.html` delete the command-palette entry `{ section: "Workspace", label: "Chat", … }` with its `{% if pageV.chatPagePerm %}` guard. `mkdir templates/archive`, then `git mv templates/chat.html templates/archive/chat.html` and `git mv templates/js/_chat_js.html templates/js/archive/_chat_js.html` — do NOT edit their contents (stale includes inside archived files are the accepted convention).
- [ ] **Step 5 — GREEN run.** `.venv\Scripts\python -m pytest tests/unit -q --deselect tests/unit/test_translations.py` (translations RED expected from here until the final task) — incl. `test_template_url_prefix.py`, which scans the archived partial. `git rm` the two chat test files. Then `nx -r` and confirm any page renders without BuildError.
- [ ] **Step 6 — Commit:**

```bash
git add -A nx_lib/views/chat.py nx_lib/__init__.py nx_lib/security.py templates/_header.html templates/js/_header_js.html templates/chat.html templates/archive/ templates/js/_chat_js.html templates/js/archive/ tests/e2e/test_chat.py tests/integration/test_chat_routes.py tests/unit/test_create_app.py tests/unit/test_security.py tests/unit/test_coverage_thresholds.py
git commit -F - <<'EOF'
refactor(chat): remove chat page, API and nav wiring

Nobody uses chat. Delete nx_lib/views/chat.py (all six /chat and
/api/chat/* routes), de-register it, drop chatPagePerm from
page_visibility()/startpage_redirect_to, and remove the nav +
command-palette entries (url_for('chat_page') would otherwise
BuildError on every page). chat.html and _chat_js.html move to the
archive/ folders for resurrection; git history archives the Python.
Chat_* tables are decapitated later by migration 0042; files under
static/uploads/chat/ stay on disk. Voids the chat stored-XSS, upload
IDOR and start-conversation findings from the 2026-07-23 hunt.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — Remove collaboration frontend (panel + overview)

Frontend first (D-SEQ): after this phase the UI no longer calls any collaboration endpoint, so Phase 3's backend removal cannot break a rendered page on INT.

### Task 2: Prune collaboration from the shared detail panel (all three consumers)

**Files:**
- Modify: `templates/js/_workitem_detail_panel_js.html`, `templates/js/_workitems_overview_js.html` (perm object + aliases only), `templates/js/_prepared_documents_js.html`, `templates/js/_reporting_drill_js.html`, `templates/prepared_documents.html`, `templates/workitems_overview.html` (only if it feeds the perm objects — `Grep "__workitemDetailPerms|__pdocPreviewPerms|__rpDrillPerms"`), `tests/integration/test_workitem_detail_panel.py`

**Scope/defect (D-PANEL):** REMOVE from the panel partial: `buildCollaborationMarkup`, `buildReadonlyCommentsMarkup` (the readOnly branch renders comments+tags today — it goes too), the `collaboration` const + Collaboration card slot inside `buildPanelMarkup`, `renderTagsInDetails`, `loadCollaborationData` (contains the voided comment-XSS sink `${comment.CommentText.replace(…)}` and the `api/workitem/${id}/interactions` fetch), the `window.mentionableUsers` seed, the `loadCollaborationData(wid, …)` call inside `render`, and the `renderTagsInDetails`/`loadCollaborationData` entries in `Object.assign(window.NexoraWorkitemDetail, {…})` + their `window.*` re-exports. KEEP untouched: `buildPanelMarkup`'s timeline/images/History/Document-Details cards, `loadHistory`, `renderWorkitemTimeline` (process-stage progress — NOT collaboration), `loadImagesInBatch`/`loadImage`, all source-highlight helpers (`srcEsc`, `tableCellSources`, `allSources`, `renderTableGrids`, `buildSourceDetailsHtml`, `renderThumbOverlay`, `refreshThumbOverlays`), `loadDetailData`, `_clientByWid`/`_clientQS`, `render()`, `_renderHeaderChip`, `attachLightbox` — entirely. Strip the `setPriority/addTag/assignUsers/addComment` keys from all three perm objects (the drill object may not carry them — `Grep` first) and the `loadCollaborationData`/`renderTagsInDetails` aliases near the top of the overview partial.

- [ ] **Step 1 — Write the failing test.** In `tests/integration/test_workitem_detail_panel.py`, flip the assertions: `b"buildCollaborationMarkup" not in body`, `b"buildReadonlyCommentsMarkup" not in body`; keep/add asserts that `attachLightbox` and `loadHistory` are present.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/integration/test_workitem_detail_panel.py -q`.
- [ ] **Step 3 — Implement** the excisions in the panel partial, then the perm-object/alias strips in the three consumers. (The view-side `details_*_perm` template vars are removed in Task 6 — passing unused vars meanwhile is harmless.)
- [ ] **Step 4 — GREEN run + browser.** Panel test GREEN; `nx -r`, then `nx -u -b --loginas:<user>`: expand a workitem row, open a prepared-docs preview, open a reporting drill drawer — fields, images, timeline, audit history and the lightbox all render, no console errors referencing removed functions. Screenshot to `var/screenshots/` and send it.
- [ ] **Step 5 — Commit** (`refactor(workitems): prune collaboration from shared detail panel` — body: names the removed builders, notes BOTH branches stripped incl. the readOnly comments/tags card, all three consumers updated, and the voided comment-XSS sink; trailer as usual).

### Task 3: Strip collaboration UI from the workitems overview (template + JS)

**Files:**
- Modify: `templates/workitems_overview.html`, `templates/js/_workitems_overview_js.html`
- Verify: `tests/e2e/test_workitems.py`, `tests/e2e/test_workitem_source_highlight.py`, `tests/e2e/test_workitem_table_highlight.py` (grep-verified clean of collaboration deps — must still pass)

**Scope/defect:** Template — remove the tag filter (`#tagFilterInput` + `<datalist id="taglist">`, gated by `tag_filter_perm`), `#priorityFilter` (gated by `priority_perm`), `#assignedUserFilter` (gated by `assigned_user_perm`), the priority-flag header cell (`<i class="fas fa-flag">`) and the tags header cell; reword the export-modal subtitle `"Workitem ID, Status, Stage, Last Movement, Priority, Tags"` to drop the last two. JS — remove the `${API_PREFIX}api/users` fetch, `fetchMentionableUsers` and `fetchAllTags` (both already-dead), `handleSetPriority`, `refreshWorkitemUI`, `handlePostComment`, `insertMention`, `renderAutocompleteList`, `handleMentionInput`, the tbody `submit`/`input`/`focusout` mention/comment delegations, the tags-preview + `priority-indicator-${rowKey}` cells in `renderTable` (voids the tag-XSS and the stale-flag findings), the tag/priority/assigned filter listeners, and the `data.users`/`data.tags` handling in the page-init fetch (the backend keys vanish in Task 6 — stripping the consumer first prevents an undefined-deref window on INT). Re-derive the column arithmetic from the FINAL header row — `emptyColspan`, the loader `colspan`, the details-row `colspan`, and `sortTable`'s column indices all shift when the Priority + Tags columns disappear; never pattern-copy old numbers. KEEP: `showNotification` (toast), `_inRegisterByWid`, selection/export code, doc-field search UI, the `NexoraWorkitemDetail.render` call.

- [ ] **Step 1 — Implement the template strip**, then **Step 2 — the JS strip** (order within the commit is free; it's one commit).
- [ ] **Step 3 — Verify.** `.venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py -q`; `nx -r` and load the workitems page as a full-perm user: table renders, remaining filters are process/status/id/date/doc-fields, row-expand works, no console errors (the still-registered backend routes simply go uncalled). Screenshot + send.
- [ ] **Step 4 — e2e tier.** `.venv\Scripts\python scripts/test_db_reset.py` then the three workitems e2e modules — GREEN.
- [ ] **Step 5 — Commit** (`refactor(workitems): remove collaboration UI from the overview` — body: filters, columns, mention/comment handlers gone; colspans and sort indices re-derived; voids the tag-XSS and stale priority-flag findings).

---

# PHASE 3 — Remove collaboration backend

### Task 4: Collaboration API routes out of `nx_lib/views/workitems.py`

**Files:**
- Modify: `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py`, `tests/unit/test_create_app.py`

**Scope/defect:** remove nine view functions and their `add_url_rule` registrations: `get_workitem_interactions`, `add_workitem_comment`, `assign_workitem`, `set_workitem_priority`, `get_all_tags`, `add_tag_to_workitem`, `remove_tag_from_workitem`, `get_single_workitem` (the `/api/workitem/<int:workitemid>` route — returns only tags, collaboration-only), and `get_users_for_mentions` (`/api/users` — sole consumers were the @mention autocomplete and the assign dropdown, both gone in Phase 2; its 2.5.64 cache-key fix dies with it, correctly). Also remove the `create_notification` import, the `@(\w+\.\w+)` mention-parsing block and the `interactions_{wid}` cache writes. **KEEP** `get_audithistory` and its route untouched. Voids the comment-id race (`SELECT TOP 1 CommentID … ORDER BY CommentID DESC`) and removes two of the three notification producers.

- [ ] **Step 1 — Write the failing tests.** In `tests/integration/test_workitems_routes.py` delete: `test_get_users_for_mentions_authed`, `test_get_workitem_interactions_authed`, `test_add_workitem_comment_anonymous_returns_unauth`, `test_add_workitem_comment_authed_unknown`, `test_assign_workitem_authed_unknown`, `test_set_workitem_priority_authed_unknown`, `test_get_all_tags_authed`, `test_add_tag_to_workitem_authed_unknown`, `test_remove_tag_from_workitem_authed_unknown`; strip the four collaboration codes from the `workitems_all_perms`-style fixture. In `tests/unit/test_create_app.py` remove the nine endpoint names from the census.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_create_app.py -q`.
- [ ] **Step 3 — Implement.** Delete the nine functions + registrations + the import + mention block. `Grep "add_url_rule"` in the file afterwards for dangling registrations; `Grep "create_notification"` in the file → zero.
- [ ] **Step 4 — GREEN run.** `.venv\Scripts\python -m pytest tests/unit/test_create_app.py tests/integration/test_workitems_routes.py -q`.
- [ ] **Step 5 — Commit** (`refactor(workitems): remove collaboration API routes` — body: lists the nine routes, notes get_audithistory (Octo processing trail) stays, and the voided comment-id race).

### Task 5: Strip tag/priority/assignee plumbing from `nx_lib/workitem_sources.py`

**Files:**
- Modify: `nx_lib/workitem_sources.py`, `nx_lib/views/workitems.py` (`_get_workitems_data`), `tests/unit/test_workitem_sources.py`

**Scope/defect:** the collaboration tables are embedded in the SURVIVING list queries — this is the blocker-grade strip. `WorkitemFilter` loses its `priority`, `assigned_user`, `tag` fields. `SqlServerSource.list_workitems` loses the tag `EXISTS` clause against `[DB_NEXORA].dbo.Workitem_Tags`/`Tags`, the priority and assigned-user clauses, the `TagsJSON` subquery, the `wim.Priority` projection and the `LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata` joins (BOTH query variants), and `"tags": json.loads(r.TagsJSON)` in row building. `PostgresSource` loses its hardcoded `"tags": []` / `"priority": 0` row keys. Delete `resolve_nexora_filter_ids`, `enrich_rows_from_nexora` (and its call sites — `Grep` callers), and `single_workitem_tags`. In `_get_workitems_data` remove the `args.get("tag")`/priority/assigned reads, their `has_permission("workitems.filter.priority")`-style gates (incl. the camelCase `has_permission("workitems.filter.assignedUser")`), and the removed `WorkitemFilter(...)` kwargs — a leftover kwarg is a `TypeError`.

- [ ] **Step 1 — Write the failing tests.** In `tests/unit/test_workitem_sources.py`: delete the `resolve_nexora_filter_ids` tests, `test_enrich_rows_from_nexora_attaches_priority_and_tags`, `test_single_workitem_tags_uses_nexora`, and every `resolve_nexora_filter_ids` patch; update row-shape assertions so rows no longer carry `tags`/`priority`.
- [ ] **Step 2 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_workitem_sources.py -q`.
- [ ] **Step 3 — Implement**, then `Grep "Workitem_Metadata|Workitem_Tags|TagsJSON|resolve_nexora_filter_ids|enrich_rows_from_nexora"` over `nx_lib/` — zero hits must remain.
- [ ] **Step 4 — GREEN run.** `.venv\Scripts\python -m pytest tests/unit/test_workitem_sources.py tests/integration/test_workitems_routes.py -q`; `nx -r`, confirm the list loads for both the default and the MS02 client.
- [ ] **Step 5 — Commit** (`refactor(workitems): drop collaboration joins and filters from sources` — body: WorkitemFilter fields, both adapters' joins/projections and the three Nexora-metadata helpers removed; prerequisite for migration 0042).

### Task 6: Trim `api_workitems_page_init`, CSV columns and view perm plumbing

**Files:**
- Modify: `nx_lib/views/workitems.py` (`api_workitems_page_init`, `export_workitems_csv`, `workitems_overview`, `prepared_documents`), `tests/integration/test_workitems_routes.py`

**Scope/defect:** `api_workitems_page_init` **survives** but returns only `{"field_config": …}` — delete its tags block and its users block (incl. the buggy `_users_key = f"users_mentions_{'all' if _all_users else _org}"` cache key, voiding that finding; `field_config` is doc-field search config, a surviving feature). In `export_workitems_csv`, drop the `"Priority", "Tags"` headers, the `priority_label` map and the per-row values (the fields/history/images includes stay — Task 21 caps them). In `workitems_overview` remove `details_set_priority_perm`/`details_add_tag_perm`/`details_assign_users_perm`/`details_add_comment_perm`, `tag_filter_perm`/`priority_perm`/`assigned_user_perm`, and `portal_assigned_users_filter = get_all_portal_users("workitems", "filter.assignedUser")` (+ all their `render_template` kwargs); in `prepared_documents` remove the same four `details_*` vars/kwargs.

- [ ] **Step 1 — Write the failing test.** Update `test_api_workitems_page_init_authed` to assert the response contains `field_config` and NOT `tags`/`users`; update any CSV test asserting the Priority/Tags headers.
- [ ] **Step 2 — RED run.** **Step 3 — Implement** all trims. **Step 4 — GREEN run** (`tests/integration/test_workitems_routes.py`) + `nx -r` page reload.
- [ ] **Step 5 — Commit** (`refactor(workitems): trim page-init payload, CSV columns and perm vars` — body: page_init now serves doc-field config only, voiding its user-cache-key finding; CSV loses the collaboration columns; both views stop passing dead perm vars).

### Task 7: Remove the orphaned portal-user helper

**Files:** Modify `nx_lib/users.py`, `tests/unit/test_users.py`, `tests/unit/test_coverage_thresholds.py` (only if the `users.py` threshold now misfits). **Scope:** after Tasks 1 and 6, `get_all_portal_users` has zero callers (only `chat.py` and the assigned-user filter used it). **KEEP `resolve_user_icon_url`** — `nx_lib/hooks.py`'s context processor (header avatar) uses it. **Steps:** delete the function + its tests (keep the icon-resolver tests); `Grep "get_all_portal_users"` repo-wide → zero; run `tests/unit/test_users.py` + thresholds. **Commit:** `refactor(users): remove get_all_portal_users, keep icon resolver`.

### Task 8: Drop collaboration child-deletes from `admin_delete_user`

**Files:**
- Modify: `nx_lib/views/admin.py` (`admin_delete_user`), `tests/integration/test_admin_routes.py`

**Scope/defect:** inside the atomic block, remove exactly the seven collaboration deletes — the run starting at `"delete from tags where createdbyuserid = ?"` through the `workitem_metadata`, `notifications`, `comment_mentions`, `workitem_comments`, `Chat_Messages` (senderid) and `Chat_Participants` statements. **Keep the 2.5.64 atomic structure** (single transaction, rollback, `ReportShares`/`ReportSchedules`/`Reports` ordering) byte-for-byte. Voids the "delete-user wipes global tags + workitem_metadata" finding. Must land BEFORE the migration (D-SEQ) — the hook-applied rename would otherwise make delete-user 500 on INT; D-FK guarantees deletes still succeed post-rename.

- [ ] **Step 1 — Edit the test.** Remove the Notifications-row seed and its post-delete assertions from the delete-user test (`Grep "Notifications"` in the file); the test now asserts user + report artifacts vanish atomically. (If the edited test passes against unmodified code, treat Step 2's Grep as the RED gate instead.)
- [ ] **Step 2 — Implement.** Delete the seven lines; touch nothing else. `Grep "tags|workitem_metadata|notifications|comment_mentions|workitem_comments|Chat_"` over `nx_lib/views/admin.py` → zero collaboration-table hits.
- [ ] **Step 3 — GREEN run.** `.venv\Scripts\python -m pytest tests/integration/test_admin_routes.py -q`.
- [ ] **Step 4 — Commit** (`refactor(admin): drop collaboration child-deletes from user deletion` — body: the seven tables are decapitated by 0042, which also drops their Users FKs; the 2.5.64 atomic report-cascade is unchanged. Note: until 0042 lands, deleting a user with legacy collab rows on INT FK-fails — transient, don't delete users on INT in that window).

---

# PHASE 4 — Remove the notification bell

### Task 9: Bell modules, routes, header UI, tests

**Files:**
- Delete: `nx_lib/views/notifications.py`, `nx_lib/notifications.py`, `tests/unit/test_notifications.py`, `tests/integration/test_notifications_routes.py`
- Modify: `nx_lib/__init__.py`, `templates/_header.html`, `templates/js/_header_js.html`, `tests/e2e/test_header.py`, `tests/unit/test_create_app.py`, `tests/unit/test_coverage_thresholds.py`

**Scope/defect (D-NOTIF):** with chat (Task 1) and the workitems producers (Task 4) gone, `create_notification` has zero callers. Remove both routes (`get_notifications`, `mark_notifications_as_read` — session-gated only, no permission codes), the producer module, the `_header.html` bell block (`#notification-dropdown-container`, `#bell-button`, `#notification-count`, `#notification-panel`, `#notification-list`, `data-testid="header-notifications-toggle"`), and the whole `_header_js.html` bell script section (`fetchNotifications`, `updateNotificationUI`, `ALLOWED_NOTIFICATION_ICONS`, `safeNotificationHref`, `markNotificationsAsRead`, the click/outside-click handlers, `setInterval(fetchNotifications, 60000)`). `url_for('get_notifications')` in that block makes header + route removal one commit. **Do not touch** any `showNotification` toast helper.

- [ ] **Step 1 — Grep precondition.** `Grep "create_notification"` repo-wide → only `nx_lib/notifications.py` itself. If any caller remains, STOP — a prior task was incomplete.
- [ ] **Step 2 — Write the failing tests.** `test_create_app.py`: remove both endpoints from the census. `tests/e2e/test_header.py`: delete `test_header_notifications_toggle_opens_panel`. `test_coverage_thresholds.py`: drop `"notifications.py": 100` and `"views/notifications.py": 100`. `git rm` the two notification test files.
- [ ] **Step 3 — RED run.** `.venv\Scripts\python -m pytest tests/unit/test_create_app.py -q`.
- [ ] **Step 4 — Implement.** `git rm` the two modules; remove the `notifications` import + `notifications.register_routes(app)` from `nx_lib/__init__.py`; excise both header blocks. `Grep "get_notifications|notification-panel"` over `nx_lib/ templates/` (excluding archives) → zero.
- [ ] **Step 5 — GREEN run.** `.venv\Scripts\python -m pytest tests/unit tests/integration -q --deselect tests/unit/test_translations.py`; `nx -r`, header renders bell-free, no console errors.
- [ ] **Step 6 — Commit:**

```bash
git add -A nx_lib/views/notifications.py nx_lib/notifications.py nx_lib/__init__.py templates/_header.html templates/js/_header_js.html tests/unit/test_notifications.py tests/integration/test_notifications_routes.py tests/e2e/test_header.py tests/unit/test_create_app.py tests/unit/test_coverage_thresholds.py
git commit -F - <<'EOF'
refactor(notifications): remove the notification bell end to end

All three producers (chat messages, comment @mentions, assignments)
were removed with their features, so the bell goes too: both routes,
create_notification, and the header bell UI incl. its 60s poll. The
2.5.64 XSS hardening (ALLOWED_NOTIFICATION_ICONS/safeNotificationHref)
is removed wholesale with the sink. No notifications.* permission codes
ever existed. dbo.Notifications is decapitated by migration 0042. Toast
helpers (showNotification) are unrelated and stay.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — DB migrations + TEST fixtures

### Task 10: Migration `0042` — decapitate the nine tables (D-DATA + D-FK)

**Files:**
- Create: `sql/_migrations/NexoraDB/0042_decapitate_collaboration_tables.sql`
- Staged as regenerated by the hook (never hand-edited): `sql/NexoraDB/Tables/*` dumps

**Content sketch** (idempotent — survives hook re-apply; `sp_rename`'s second argument must be the bare new name, never schema-qualified; FK names are auto-generated and differ per environment, hence the dynamic lookup):

```sql
-- 0042: chat/collaboration/notification removal (feature/2.5.65).
-- Renames the nine dead tables with a decapitated_ prefix (data preserved,
-- reversible) and drops their FKs to dbo.Users so user deletion keeps
-- working after admin_delete_user lost its collaboration child-deletes.
DECLARE @sql nvarchar(max) = N'';
SELECT @sql = @sql + N'ALTER TABLE dbo.' + QUOTENAME(OBJECT_NAME(fk.parent_object_id))
             + N' DROP CONSTRAINT ' + QUOTENAME(fk.name) + N';'
FROM sys.foreign_keys fk
WHERE fk.referenced_object_id = OBJECT_ID(N'dbo.Users')
  AND OBJECT_NAME(fk.parent_object_id) IN
      (N'Chat_Messages', N'Chat_Participants', N'Tags', N'Workitem_Comments',
       N'Comment_Mentions', N'Notifications', N'Workitem_Metadata');
EXEC sp_executesql @sql;
GO
IF OBJECT_ID(N'dbo.Chat_Conversations', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Chat_Conversations', N'U') IS NULL
    EXEC sp_rename N'dbo.Chat_Conversations', N'decapitated_Chat_Conversations';
GO
-- …repeat the guarded sp_rename block for: Chat_Messages, Chat_Participants,
-- Tags, Workitem_Tags, Workitem_Comments, Comment_Mentions, Notifications,
-- Workitem_Metadata.
```

- [ ] **Step 1 — Preflight (take it seriously).** `Grep "Workitem_Metadata|Workitem_Tags|Workitem_Comments|Comment_Mentions|Chat_Conversations|Chat_Messages|Chat_Participants|dbo\.Tags|Notifications"` over `nx_lib/` → MUST be zero live hits (Phases 1–4 complete). Confirm `0042` is still the next free number (`ls sql/_migrations/NexoraDB/`).
- [ ] **Step 2 — Write the migration** per the sketch (all nine tables; FK-drops first; intra-group FKs untouched).
- [ ] **Step 3 — Apply to INT manually first:** `python scripts/db-migrate.py --env INT`. Then `nx -r` and smoke the workitems list, a row-expand, prepared docs and an admin page against INT — nothing may miss the renamed tables.
- [ ] **Step 4 — Commit.** The hook re-applies (no-op thanks to the guards) and `sql-sync-check` regenerates the per-object dumps — `git add sql/_migrations/NexoraDB/0042_decapitate_collaboration_tables.sql sql/NexoraDB` (old `dbo.X.sql` deleted, `dbo.decapitated_X.sql` added) and commit (`chore(sql): decapitate collaboration tables in migration 0042` — body: nine tables renamed via guarded sp_rename, data preserved and reversible; Users FKs dropped via dynamic sys.foreign_keys lookup; dumps regenerated by the sync hook). Offline: `SQL_SYNC_SKIP=1`, never `--no-verify`.

### Task 11: Migration `0043` — delete dead permission rows + TEST fixture prune (D-PERMS)

**Files:**
- Create: `sql/_migrations/NexoraDB/0043_delete_collaboration_permissions.sql`
- Modify: `sql/test/seed.sql`, `sql/test/schema.sql`

**Content:** naturally idempotent deletes, children first (both `dbo.AccessProfilePermission` and `dbo.UserPermissionOverride` FK `Permission.PermissionID` with NO CASCADE — rows for the dead codes exist in practice because the access-control drawer wrote explicit Deny rows for every permission), copying the comment-header style of `0018_seed_workitems_details_view_permissions.sql`:

```sql
DELETE app FROM dbo.AccessProfilePermission app
  JOIN dbo.Permission p ON p.PermissionID = app.PermissionID
 WHERE p.Code IN (N'chat.view', N'workitems.details.add.tag',
                  N'workitems.details.set.priority', N'workitems.details.assign.users',
                  N'workitems.details.add.comment', N'workitems.filter.tag',
                  N'workitems.filter.priority', N'workitems.filter.assignedUser');
GO
DELETE upo FROM dbo.UserPermissionOverride upo
  JOIN dbo.Permission p ON p.PermissionID = upo.PermissionID
 WHERE p.Code IN (/* same eight codes */);
GO
DELETE FROM dbo.Permission WHERE Code IN (/* same eight codes */);
GO
```

- [ ] **Step 1 — Write the migration** with the eight codes (no `notifications.*` — none exist).
- [ ] **Step 2 — Prune TEST fixtures.** `sql/test/seed.sql`: remove the `dbo.Permission` INSERT rows for the eight codes (`Grep` each). `sql/test/schema.sql`: remove whichever collaboration `CREATE TABLE` blocks exist (`Grep` each of the nine names — the file holds a subset) plus their entries in the DROP list at the top; no surviving test references them after Phases 1–4.
- [ ] **Step 3 — Apply + verify.** `python scripts/db-migrate.py --env INT`; then `.venv\Scripts\python scripts/test_db_reset.py` and `.venv\Scripts\python -m pytest tests/integration -q --deselect tests/unit/test_translations.py` GREEN.
- [ ] **Step 4 — Commit** (`chore(sql): delete dead collaboration permission rows in 0043` — body: eight codes deleted child-first (AccessProfilePermission → UserPermissionOverride → Permission), trivially reversible by reseeding; TEST schema/seed pruned to match).

---

# PHASE 6 — Part A docs closeout

### Task 12: CLAUDE.md / README / design docs / CHANGELOG Removed

**Files:** Modify `CLAUDE.md`, `README.md`, `docs/design/ms02-multisource.md`, `CHANGELOG.md`.

- [ ] **Step 1 — CLAUDE.md.** Project-overview line: drop "chat" from "(workitems, invoices, chat, admin…". Routing bullet: drop `chat` and `notifications` from the views list. Databases section: remove the "(tags/priority still shared between colliding ids — open)" caveat from the compound-identity paragraph — now moot.
- [ ] **Step 2 — README.md.** Drop "chat" from the feature list near the top.
- [ ] **Step 3 — ms02-multisource.md.** Rewrite the "NexoraDB metadata (tags, priority, assignment, PID register)…" paragraph to PreparedDocuments/PID-register-only; keep the NVARCHAR-seam point (it survives for PreparedDocuments).
- [ ] **Step 4 — CHANGELOG.** Append to the existing `[Unreleased] / ### Removed` section: chat page + `/api/chat/*`; workitem collaboration (tags, priority, assignment, comments + @mentions; routes `/api/workitem/<id>/comment|assign|priority|tags`, `/api/tags`, `/api/users`, `/api/workitem/<id>/interactions`; tag/priority/assigned-to filters); the notification bell (both routes + header UI); the eight permission codes (listed, migration 0043); nine tables renamed `dbo.decapitated_*` (migration 0042, data preserved); templates archived under `archive/`. Do not touch `docs/howto/*` (grep-verified clean) or historical plans/handoffs.
- [ ] **Step 5 — Verify + commit.** Re-grep the edited files for leftover chat/notification references. Commit (`docs: update overview, routing and ms02 design for feature removal` — body: notes Confluence republishes on the owner's push).

---

# PART B — BUG FIXES (all anchors re-verified 2026-07-23; per-bug scenarios in `var/bug-hunt-report.md`)

# PHASE 7 — Critical cross-tenant leak + access control

### Task 13: PDF/TIF page caches keyed without client domain (CRITICAL)

**Files:**
- Modify: `nx_lib/views/workitems.py` (`api_get_media_raw`)
- Reference: same file — `_wi_cache_key(prefix, workitem_id, domain)` (the established client-qualified key; `get_audithistory` and `api_get_media_info` already use it)
- Test: `tests/integration/test_workitems_routes.py`

**Defect:** `_pdf_cache_key = f"media_raw_pdfpage_{workitem_id}_{media_index}"` and `_tif_cache_key = f"media_raw_tif_{workitem_id}_{media_index}"` omit the domain even though `api_get_media_raw` resolves `domain` immediately above and `media_data` is domain-keyed — colliding ids (1216 exists in both runtimes on INT) serve one client's rendered page image to the other client's user for up to an hour.

- [ ] **Step 1 — Write the failing test.** Request the same `workitem_id`/`media_index` twice with different `?client=` (mock `get_domain_for_workitem` to return two domains and the media fetch to return distinguishable bytes per domain); assert the second response is its OWN bytes, not the first client's cached ones.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Rebuild both keys through the established helper with the already-resolved domain, e.g. `_wi_cache_key(f"media_raw_pdfpage_{media_index}", workitem_id, domain)` (match `_wi_cache_key`'s exact signature by Grep) and the `tif` twin. Sweep the function for any other bare `media_raw_` literal.
- [ ] **Step 4 — GREEN run** + the full workitems integration module.
- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -F - <<'EOF'
fix(workitems): key PDF/TIF page caches by client domain

media_raw_pdfpage_/media_raw_tif_ cache keys omitted the domain the
route had already resolved, so colliding workitem ids across clients
served each other's rendered page images for up to an hour. Route both
keys through _wi_cache_key like the sibling media/audit caches.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 14: "all" process selection authorizes ungranted client×process pairs

**Files:** Modify `nx_lib/process_helpers.py` (BOTH twins carrying the pattern — `Grep "unique_clients"`: `prepare_process_selection_sql` and its list-building sibling). Test: `tests/unit/test_process_helpers.py`.

**Defect:** the "all" branch builds `unique_clients` and `unique_processes` as two independent IN-lists, authorizing the full cross-product — a user granted (A, P1) and (B, P2) can read (A, P2).

- [ ] **Step 1 — Write the failing test.** Grants {(A,P1),(B,P2)}: assert the built SQL/params do NOT authorize (A,P2) or (B,P1).
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Replace the two IN-lists with an OR-joined parameterized pair predicate — `((client = ? AND process = ?) OR …)` — built from the granted pairs, in BOTH functions; update the consumers' splicing accordingly (`Grep` both functions' callers).
- [ ] **Step 4 — GREEN run** + a dashboard/workitems integration smoke.
- [ ] **Step 5 — Commit** (`fix(process): authorize granted client-process pairs, not cross-product`).

### Task 15: Scheduled runner ignores `scope.clients` and widens on empty

**Files:** Modify `nx_lib/reporting/runner.py`. Reference: the interactive path's scope handling in `nx_lib/views/reporting.py` (`Grep "scope"` around the run view — it does this right). Test: `tests/unit/test_reporting_runner.py`.

**Defect:** `requested = (definition.get("scope") or {}).get("processes")` never reads `scope.clients`, and an all-filtered `requested` falls back to `list(allowed)` — a narrowly-scoped schedule silently emails ALL allowed processes.

- [ ] **Step 1 — Write the failing tests.** (a) Definition scoped to client X → only X's processes queried. (b) requested ∩ allowed = ∅ → explicit empty/error result surfaced in the run status, never `list(allowed)`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Read `scope.get("clients")` and intersect with the owner's allowed (client, process) pairs (reuse Task 14's pair semantics or extract the interactive path's helper into `nx_lib/reporting/`); replace the widening fallback with an empty selection + logged warning.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(reporting): honor scope clients in the scheduled runner, never widen`).

### Task 16: Recent activity bypasses the sensitive doc-field gate + drops `client`

**Files:** Modify `nx_lib/views/dashboard.py` (`api_recent_activity`), `templates/js/_dashboard_js.html` (activity row click-through). Test: `tests/integration/` dashboard tests.

**Defect (residuals only — the 2.5.64 `client_hint` pass-through at `get_domain_for_workitem(row["id"], client_hint=row.get("client"))` IS present, keep it):** the rows emit raw `fields` with no sensitive-doc-field strip (`workitems.filter.documentfields.sensitive` is enforced at every other surface), and rows carry no `client` key so colliding-id click-throughs open the wrong client's workitem.

- [ ] **Step 1 — Write the failing tests.** (a) Caller WITHOUT the sensitive perm: a row whose fields include a sensitive-configured field → absent from the JSON. (b) Every row carries `"client"`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Apply the established server-side sensitive-field strip (`Grep "documentfields.sensitive"` in `nx_lib/` for the canonical helper + config lookup; fail-closed per the doc-field contract) before emitting `fields`; add `"client": row.get("client")` to each row. In `_dashboard_js.html`, carry the client into the workitems deep-link (`?client=` via the existing `data-*` + `API_PREFIX` idiom from the 2.5.64 escaping pass).
- [ ] **Step 4 — GREEN run** + `nx -r` browser spot-check.
- [ ] **Step 5 — Commit** (`fix(dashboard): gate sensitive doc-fields and carry client in activity`).

### Task 17: Generali reporting list missing self-scoping

**Files:** Modify `nx_lib/views/generali.py` (`api_generali_reporting_list`). Reference: the transorg/org gate in the sibling users endpoint and the `restrict_to_self` pattern (2.5.64). Test: `tests/integration/` generali tests.

**Defect:** WHERE is built only from request filters; a caller holding only `generali.reporting.view` sees every org's rows.

- [ ] **Step 1 — Write the failing test.** View-only user + rows for two users/orgs → only own rows return.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** Copy the sibling pattern: `restrict_to_self = not <org edit> and not <transorg edit>` (confirm the exact codes via `Grep` around the endpoint) → append `UserID = ?` bound to `session["userid"]`.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(generali): self-scope the reporting list without edit perms`).

### Task 18: AI agent `run_sql` bypasses per-target auth + ack gate (D-RUNSQL)

**Files:** Modify `nx_lib/views/reporting.py` (`run_sql_bound` in the agent tool wiring). Reference: `_authorize_sql_target`, `_has_acked`, the `_SQL_TARGET_PERMS` map, and how the HTTP run view composes them. Test: `tests/integration/test_reporting_ai_routes.py` (or nearest).

**Defect:** `run_sql_bound` calls `_run_sql(target, sql, …)` directly; `_run_sql` contains neither gate — an agent user without the target's `reporting.sql.target.*` permission or the ack can execute sandbox SQL.

- [ ] **Step 1 — Write the failing tests.** (a) User lacking the target's SQL perm invokes the tool → authorization error in the tool result, no SQL executed. (b) User without ack → ack-required error.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In `run_sql_bound`, mirror the run view's gate order (`_authorize_sql_target(target)`, then the `_has_acked` check), converting failures into tool-result error strings the agent relays — never a raise-through 500. Audit the refusal via the existing SQL audit write with a distinct status.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(reporting): enforce SQL target auth and ack in the AI agent`).

### Task 19: `api_docfield_values` ignores per-process permissions

**Files:** Modify `nx_lib/views/workitems.py` (`api_docfield_values`). Reference: the allowed-process computation in `_get_workitems_data` (`Grep "workitems.filter.process"`). Test: `tests/integration/test_workitems_routes.py`.

**Defect:** gated only by `workitems.filter.documentfields`; the `process` argument is used unvalidated — value suggestions leak from processes the caller can't list.

- [ ] **Step 1 — Write the failing test.** Caller with the doc-field perm but WITHOUT `workitems.filter.process.<p>` requests values for `<p>` → 403/empty, fail-closed.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** Compute the caller's allowed processes the same way the list path does; return empty (not an error leak) when the requested process isn't allowed, matching the doc-field fail-closed contract.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(workitems): require process permission for doc-field values`).

### Task 20: User-detail save silently reassigns an unassignable access profile

**Files:** Modify `templates/admin/user_detail.html` (the `<select name="accessprofile">`) and the POST handler saving it in `nx_lib/views/admin.py` (`Grep "accessprofile"`). Test: `tests/integration/test_admin_routes.py`.

**Defect:** options come only from `assignable_profiles`; when the user's current profile isn't in the admin's assignable list, no option is `selected`, the browser submits the first option, and saving unrelated fields silently reassigns the profile.

- [ ] **Step 1 — Write the failing tests.** POST the form for a user whose current profile is outside the assignable set: (a) echoing the current (unassignable) value → profile unchanged; (b) a DIFFERENT unassignable value → rejected (403/validation error).
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** Template: always render the user's current profile as a selected option (labelled via `_()` as current/not-assignable) so an untouched form round-trips it. Server: accept the unchanged value always; if the value changed, require membership in the assignable set.
- [ ] **Step 4 — GREEN run** + `nx -r` browser check. **Step 5 — Commit** (`fix(admin): stop silent access-profile reassignment on user save`).

### Task 21: CSV export — enforce the heavy-include selection cap server-side (D-CSVLIM)

**Files:** Modify `nx_lib/views/workitems.py` (`export_workitems_csv`). Test: `tests/integration/test_workitems_routes.py`.

**Defect:** the ≤10-selection rule for heavy includes (`include_fields = "fields" in include_set and has_permission("workitems.details.view.fields")` etc. — fields/history/images, all per-row Octo fetches, all SURVIVING features) exists only client-side; the server honors `include=` for arbitrary or absent ids up to `EXPORT_MAX_ROWS`.

- [ ] **Step 1 — Write the failing tests.** (a) `include=fields` with no `ids` → 400. (b) With 11 compound ids → 400. (c) With 3 ids → 200, includes honored. (d) No `include`, no ids → 200 (light export unchanged).
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** After `include_set` and `specific_ids` are parsed: reject with 400 + a `_()` message when `include_set` is non-empty and `specific_ids` is absent or longer than 10 (constant next to `EXPORT_MAX_ROWS`).
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(workitems): enforce the heavy-include selection cap server-side`).

### Task 22: `dev_login` guard (D-DEVLOGIN — GATED on Owner action 2)

**Files:** Modify `nx_lib/views/auth.py` (`dev_login`). Test: `tests/integration/` auth tests.

**Defect (design-risk):** `/dev/login/<username>` is a full password+2FA bypass gated only by `if IS_PROD: abort(404)` — reachable by anyone on the INT/STAGING network. **Execute only after the owner confirms; skip entirely on "accept as designed."**

- [ ] **Step 1 — Write the failing test.** Non-loopback `REMOTE_ADDR` on non-PROD → 404; loopback → current behavior.
- [ ] **Step 2 — RED run.** **Step 3 — Implement (default proposal).** Keep the `IS_PROD` 404; add `if request.remote_addr not in ("127.0.0.1", "::1"): abort(404)`. (Env-flag variant if the owner picks it: additionally require `NEXORA_DEV_LOGIN=1`, set by the `nx` CLI's `--loginas` launch path — never left set globally.)
- [ ] **Step 4 — GREEN run** + a real `nx -u -b --loginas:<user>` smoke to prove the Playwright workflow still works. **Step 5 — Commit** (`fix(auth): restrict dev_login to loopback callers`).

---

# PHASE 8 — Compound identity (client + id)

### Task 23: `prepared_documents` resolves MS02 wids against the default Octo engine

**Files:** Modify `nx_lib/views/workitems.py` (`prepared_documents`). Reference: `nx_lib/clients.py` (`CLIENTS` registry, per-client `runtime_engine`), `resolve_octo_wid_stage`. Test: `tests/integration/test_workitems_routes.py`.

**Defect:** the register resolves MS02-derived wids via `resolve_octo_wid_stage(CLIENTS["default"].runtime_engine, wid)` — the wrong runtime; a colliding id yields the wrong status/stage.

- [ ] **Step 1 — Write the failing test.** Mock two runtime engines; a register wid must be resolved against the OWNING client's engine (assert which engine received the call), with different stages per engine → the MS02 stage wins.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** The register is MS02-scoped (`dbo.PreparedDocuments`) — resolve against the owning client's `runtime_engine` from `CLIENTS` (`Grep` how the wid→pid mapping rows attribute their client). **Check dialect-safety first:** `resolve_octo_wid_stage` was written for the SQL Server engine — read it; if the MS02 engine is Postgres, route through the source adapter's PG-side equivalent instead. Fail closed (`in_octo=False`) on resolution errors.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(workitems): resolve prepared-doc wids on the owning client engine`).

### Task 24: Prepared-docs preview drops the MS02 client

**Files:** Modify `templates/js/_prepared_documents_js.html` (`openPreview`) and, if needed, `templates/prepared_documents.html` / the `prepared_documents` view (to surface the client on the row). Test: e2e stub or browser check.

**Defect:** `NexoraWorkitemDetail.render(wid, previewBody, {readOnly:true, …})` passes no `client` and the container has no `data-client` → the panel's `_clientQS` returns `''` → media/audit fetched without `?client=ms02` — a colliding id previews the wrong client's document.

- [ ] **Step 1 — Implement.** Pass `client` in the render options, matching the overview's calling convention (`toggleDetailsAndLoadImages` passes `client`); surface it as a `data-client` attribute or template constant if the rows don't carry it yet.
- [ ] **Step 2 — Verify.** `nx -r`; open a preview on INT and confirm the media/audit requests carry `?client=` in the network tab (e2e: assert the stubbed request URL contains the client). Screenshot + send.
- [ ] **Step 3 — Commit** (`fix(workitems): pass the client into the prepared-docs preview`).

### Task 25 (compressed): `fetch_merged_page` warm loop bypasses the collision fail-safe

**Files:** Modify `nx_lib/workitem_sources.py` (`fetch_merged_page`); Test `tests/unit/test_workitem_sources.py`. **Defect:** the cache-warm loop calls `_cache_store(r["workitemid"], r["client"])` directly, bypassing `get_source_for_workitem`'s collision fail-safe — a colliding id gets pinned to whichever client the page listed first. **Change:** route the warm-store through the fail-safe (or replicate its collision check: skip ids known to exist in more than one source — read `get_source_for_workitem` first, smallest diff wins). **Verify:** unit test — a wid present in both sources is NOT blind-cached by the warm loop. **Commit:** `fix(workitems): route warm-loop caching through the collision fail-safe`.

### Task 26 (compressed): `resolve_ms02_wids_to_pids` varchar/int PG cast error (VERIFIED LIVE)

**Files:** Modify `nx_lib/workitem_sources.py` (`resolve_ms02_wids_to_pids`); Test `tests/unit/test_workitem_sources.py`. **Defect:** `WHERE "{id_col}" = ANY(%s)` binds an int list against the varchar `WorkItemID` column — PG operator error on every call; the MS02 "In register" reverse stamping is dead. The forward twin casts `::text` in its SELECT; the reverse forgot the WHERE-side cast. **Change:** mirror the forward twin — make the comparison type-consistent (`"{id_col}"` compared against a `str()`-mapped list, or cast the column) — Grep the forward twin and copy its convention exactly. **Verify:** unit test with a fake PG cursor asserting the emitted SQL/param types; then live INT spot-check that reverse chips appear. **Commit:** `fix(workitems): cast MS02 id column for wid-to-pid resolution`.

### Task 27 (compressed): `_inRegisterByWid` keyed on bare wid leaks the chip to colliding clients

**Files:** Modify `templates/js/_workitems_overview_js.html`. **Defect:** the map is seeded on bare wid and read as `inRegisterPid: _inRegisterByWid[String(workitemid)]` — the colliding default-client row inherits the MS02 "In register" chip. **Change:** key seed + lookup on the existing compound `rowKey` (`${client}-${workitemid}`) idiom. Anchors moved by Task 3 — re-`Grep "_inRegisterByWid"`. **Verify:** e2e or browser with the colliding INT id 1216 — only the MS02 row shows the chip. **Commit:** `fix(workitems): key the in-register map by client and id`.

---

# PHASE 9 — High-severity correctness (backend + reporting studio)

### Task 28: `ping_dbs_parallel` serial timeouts starve the ping pool

**Files:** Modify `nx_lib/db.py` (`ping_dbs_parallel`). Test: `tests/unit/test_db.py`.

**Defect:** the loop waits `fut.result(timeout=timeout_s)` **serially per future** → N×timeout wall time when several DBs are down, contradicting its own docstring ("bounded by ~timeout_s").

- [ ] **Step 1 — Write the failing test.** Patch the per-engine ping to block > timeout; with 3 engines assert total elapsed ≈ one timeout (+slack), all three reporting timed-out status.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** One `concurrent.futures.wait(futures, timeout=timeout_s)`; harvest `done`, mark `not_done` as timed-out and `cancel()` them.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(db): bound parallel DB pings by a single shared deadline`).

### Task 29: `get_media` never checks HTTP status; errors cached 1h

**Files:** Modify `nx_lib/octo.py` (`get_media`) and its caching callers (`Grep "get_media("` — the `pdf_src_bytes` path in `api_get_media_raw`). Test: `tests/unit/test_octo_media.py` (or `test_octo.py`).

**Defect:** `get_media` returns `response.content` with no `raise_for_status()` — a 502/HTML error body gets cached 3600s as page bytes.

- [ ] **Step 1 — Write the failing test.** Mock a 502; assert `get_media` raises (or returns a falsy sentinel) and the caching caller does NOT cache and degrades to an error status, not a poisoned cache.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** Add `response.raise_for_status()` before returning; confirm each caching caller catches `requests.HTTPError`/`RequestException` and treats it as a miss (add the except where missing).
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(octo): stop caching non-2xx media responses`).

### Task 30: `wrap_with_cap` emits invalid T-SQL for CTE queries (D-CTE)

**Files:** Modify `nx_lib/reporting/sandbox.py` (`wrap_with_cap`) + the executor consuming it (`Grep "wrap_with_cap("` callers). Test: `tests/unit/test_reporting_sandbox.py`.

**Defect:** `wrap_with_cap` emits `SELECT TOP (n) * FROM ( WITH … ) AS _q` — invalid T-SQL for every `WITH` query, which `validate_select` explicitly allows (`_QUERY_ROOTS` includes WITH).

- [ ] **Step 1 — Write the failing tests.** (a) `WITH q AS (SELECT 1 AS a) SELECT * FROM q` must produce executable SQL (assert no `FROM ( WITH` substring). (b) Plain SELECT keeps the TOP wrap. (c) Executor-level: a WITH query returns at most `cap` rows with truncation flagged.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** Detect a leading `WITH` on the comment-stripped SQL: return it unwrapped; in the executor, enforce the cap fetch-side via `cursor.fetchmany(cap + 1)` (flag truncation) on every path so both branches truncate identically.
- [ ] **Step 4 — GREEN run** + an INT smoke of a CTE query through the SQL tab. **Step 5 — Commit** (`fix(reporting): cap CTE queries without emitting invalid T-SQL`).

### Task 31: Categorical widget emits `GROUP BY 1`

**Files:** Modify `nx_lib/views/dashboard.py` (anchor: `group_by = dim_sql if dim_sql != "?" else "1"`). Test: `tests/unit/` dashboard tests.

**Defect:** when the dimension is bound as a parameter, the code emits `GROUP BY 1` — grouping by a constant is a T-SQL error, so the affected categorical widgets 500.

- [ ] **Step 1 — Write the failing test.** A widget whose dim resolves to the `"?"` parameter → the generated SQL must contain NO `GROUP BY` (a bound constant label + aggregate needs none) and must still bind the label param; a real-column dim keeps its `GROUP BY {dim_sql}`.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** When `dim_sql == "?"`, omit the `GROUP BY` clause entirely (`SELECT ? AS dim, {metric} …` with only aggregates otherwise selected is legal). No injection surface — dims come from the fixed whitelist map, never user text (assert that in the test).
- [ ] **Step 4 — GREEN run** + browser-check a categorical widget on INT. **Step 5 — Commit** (`fix(dashboard): drop GROUP BY for constant-dim categorical widgets`).

### Task 32: Uncaught `TimeoutError` from `as_completed` kills large CSV exports

**Files:** Modify `nx_lib/views/workitems.py` (`export_workitems_csv`, anchor: `for future in as_completed(futures, timeout=120):`). Test: `tests/integration/test_workitems_routes.py`.

**Defect:** the `try` wraps only `future.result()`; `as_completed` itself raising `TimeoutError` at iteration is uncaught → the whole export 500s instead of degrading.

- [ ] **Step 1 — Write the failing test.** Patch `as_completed` to raise `concurrent.futures.TimeoutError` mid-iteration; assert the export returns 200 with the rows fetched so far (unfinished rows carry an explicit timed-out marker), not a 500.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** Wrap the loop in `try/except concurrent.futures.TimeoutError`: log, cancel pending futures, fill their rows with the marker, continue writing the CSV.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(workitems): survive as_completed timeout in large CSV exports`).

### Task 33: KPI card shows the first breakdown row, not the metric total (D-KPI)

**Files:** Modify `templates/js/_reporting_dashboard_js.html` (`renderKpi` + the card run-payload builder). Test: e2e (`tests/e2e/test_reporting_dashboard.py`, stub-network pattern).

**Defect:** `var v = rows.length ? rows[0][idx.val] : null` — with a breakdown dimension the card shows an arbitrary first bucket instead of the total.

- [ ] **Step 1 — Write the failing e2e.** Stub the run endpoint; assert the KPI card's run request contains NO breakdown dims (and the displayed value is the stubbed zero-dim total).
- [ ] **Step 2 — RED run** (after `scripts/test_db_reset.py`).
- [ ] **Step 3 — Implement.** When the card type is KPI, omit breakdown dims from the run payload so the backend returns the single total row (zero-dim totals are supported since the Simple tabs); `renderKpi` keeps reading `rows[0]`. Client-side summing is NOT acceptable — wrong for avg/min/max metrics.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(reporting): request undimensioned totals for KPI cards`).

### Task 34: Global-filter popover self-closes on every open after the catalog is cached

**Files:** Modify `templates/js/_reporting_dashboard_js.html` (`openFilterPopover` + the document-level click closer). Test: e2e.

**Defect:** once `ensureCatalog()`'s promise is cached, the `await` resolves in a microtask and the popover opens BEFORE the same click bubbles to the document closer → `filterPop.open` is true, target is outside → instant self-close. First open (real fetch) escapes.

- [ ] **Step 1 — Write the failing e2e.** Open the popover, close it, open again (catalog cached) → assert it stays open.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** Make the closer ignore the opening click: record the triggering event on open and have the document listener return early for it, OR defer the open past the bubble with `setTimeout(…, 0)`. Pick ONE, comment why.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(reporting): keep the global-filter popover open on cached opens`).

### Task 35: Drill drops date filters for unparseable grain buckets

**Files:** Modify `templates/js/_reporting_drill_js.html` (anchor: `var upper = addGrainUpper(…); if (!upper) return;` inside the `clicked.forEach`). Test: e2e (new drill test, stub-network style).

**Defect:** an unparseable grain bucket silently skips pushing the date filters yet still opens the drill → the drawer shows ALL rows.

- [ ] **Step 1 — Write the failing e2e.** Stub a run whose grain bucket label is unparseable; click it; assert the drill request still carries a date/equality constraint on the raw bucket — or the drawer refuses to open with a toast — never an unfiltered query.
- [ ] **Step 2 — RED run.** **Step 3 — Implement.** On unparseable `upper`, fall back to an equality filter on the raw bucket value for the grain field; if even that is impossible, abort opening with a toast. Never proceed unfiltered.
- [ ] **Step 4 — GREEN run.** **Step 5 — Commit** (`fix(reporting): never drop date filters on unparseable drill buckets`).

---

# PHASE 10 — Medium fixes (compressed; per-bug scenarios in `var/bug-hunt-report.md`)

### Task 36: dotenv precedence inverted vs documented (D-DOTENV)

**Files:** Modify `nx_lib/config.py`; new `tests/unit/test_config_dotenv.py` (tmp-file based). **Defect:** the bare `load_dotenv()` (root `.env`) runs FIRST; the `load_dotenv(dotenv_path=…)` env-specific load runs second with default `override=False` — root `.env` wins, inverting the module docstring's contract. **Change:** swap the order — `env/{ENVIRONMENT}.env` (and the deprecated root fallback) first, bare `load_dotenv()` second, all `override=False` (OS env > env-file > root). Update the docstring. **Verify:** unit test — both files define a key → env-specific wins; a process-env value wins over both. **Commit:** `fix(config): load env-specific dotenv before the root fallback`.

### Task 37: `sendReleaseNotice.py` ImportErrors on `nx_main` re-exports

**Files:** Modify `scripts/news/sendReleaseNotice.py` (its `from nx_main import (GRAPH_CLIENT_ID, … engine_nexora_db)` block) + the stale re-export docstring in `nx_main.py`. **Defect:** `nx_main.py` imports only `create_app`, so the script ImportErrors on every run; its docstring still promises the re-exports. **Change:** point the script at the canonical homes — `from nx_lib.config import GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_PASSWORD, GRAPH_TENANT_ID, GRAPH_USERNAME` and `from nx_lib.db import engine_nexora_db` — and rewrite the `nx_main` docstring to stop promising re-exports. Do NOT reshape `nx_main`'s surface: `ops/run_scheduled_reports.py` and `nx_lib/cli.py` import `app` from it (verified) and must keep working. **Verify:** an import smoke of the script's module (read its `__main__` guard first — importing must not send mail). **Commit:** `fix(scripts): import release-notice deps from their real modules`.

### Task 38: `change_password` GET returns None → 500 (VERIFIED LIVE)

**Files:** Modify `nx_lib/views/profile.py` (`change_password`). **Defect:** the function only returns inside the POST branch; GET falls through → None → 500. **Change:** add the final GET-path `return` (render the proper template if one exists, else redirect to the profile page — `Grep` how the page is reached from `profile.html`). **Verify:** integration test — GET → 200/302, not 500. **Commit:** `fix(profile): return a response on change-password GET`.

### Task 39: Password-reset timing oracle (D-RESET)

**Files:** Modify `nx_lib/views/auth.py` (the branch `if rows: send_reset_email(request_email)`). **Defect:** the synchronous Graph mail call runs only for registered addresses — response latency leaks account existence despite the 2.5.64 uniform message (which stays untouched). **Change:** dispatch `send_reset_email` on a daemon `threading.Thread` (thread body catches/logs its own exceptions — no unhandled thread errors under IIS; capture needed config values before spawning) so both branches return immediately with the same D8 neutral message. **Verify:** integration test — patch `send_reset_email` with a blocking mock; the route returns without waiting; both branches return identical bodies (existing 2.5.64 test stays green). **Commit:** `fix(auth): send reset mail asynchronously to close the timing oracle`.

### Task 40: Reset token not single-use + session capability persists (D-RESET)

**Files:** Modify `nx_lib/views/auth.py` (`reset_password`, `set_new_password`). **Defect:** the signed token is replayable for its full 15-min `max_age`, and `set_new_password` never pops `session["email_for_password_reset"]` — the capability persists for the whole session. **Change:** (a) on every `set_new_password` exit (success AND failure), `session.pop("email_for_password_reset", None)`; (b) single-use: mark consumed tokens in the app `cache` keyed by token hash with TTL = max_age, and have `reset_password` reject already-consumed tokens. Code comment: per-process cache under wfastcgi makes single-use best-effort across workers — accepted (D-RESET). **Verify:** integration test — complete a reset, replay the same token URL → rejected; session key gone. **Commit:** `fix(auth): make reset tokens single-use and drop the session capability`.

### Task 41: Auth `except Exception: return` → None → 500 sweep (VERIFIED LIVE)

**Files:** Modify `nx_lib/views/auth.py` (`set_new_password`'s and `init_reset_password`'s bare `except Exception: return` branches). **Defect:** both end in a bare `return` → None → 500; `set_new_password` also swallows the GET-with-no-session KeyError this way. **Change:** log via `current_app.logger`, flash a neutral `_()` message, `return redirect(url_for("login"))` (match the surrounding idiom); handle the missing-session-key case explicitly. **Verify:** integration tests — each branch → 302, not 500. **Commit:** `fix(auth): return real responses from reset error branches`.

### Task 42: Admin log search emits raw datetimes (TZ shift)

**Files:** Modify `nx_lib/views/admin.py` (the log-search rows, anchor: `"Timestamp": row.Timestamp`). **Defect:** raw datetimes serialize RFC-1123/GMT → UI times shift by the server's UTC offset; `admin_active_sessions` already does it right (explicit ISO comment). **Change:** emit `.isoformat()` exactly like `admin_active_sessions`; check the log-export sibling for the same raw pass-through while there. **Verify:** integration test asserts an ISO-shaped string. **Commit:** `fix(admin): serialize log-search timestamps as ISO strings`.

### Task 43: `admin_recent_logs` always 500s (NVARCHAR vs int)

**Files:** Modify `nx_lib/views/admin.py` (`admin_recent_logs`, anchor: `200 <= row.HttpResponseCode < 300`). **Defect:** `HttpResponseCode` is NVARCHAR → TypeError → guaranteed 500. **Change:** coerce defensively (guarded `int(row.HttpResponseCode)` with a fallback bucket for non-numeric). **Verify:** integration test with string status codes → 200. **Commit:** `fix(admin): coerce log status codes before range comparison`.

### Task 44: 7 live admin templates link nonexistent `static/css/output.css` (VERIFIED LIVE)

**Files:** Modify `templates/admin/{access_control,admin_overview,logs,maintenance,organizations,sessions,user_detail}.html` — leave `templates/admin/archive/user_management.html` alone (archived files are frozen). **Defect:** `output.css` does not exist in `static/css/` (never did — no git history, no Tailwind build in the repo) → a 404 on every admin page load. **Change:** delete the dead `<link … output.css>` line from the seven live templates; the fix is deleting the link, NOT adding a build pipeline (the admin UI's real styles shipped with the 2.5.63 nx CSS migration). **Verify:** `Grep "output.css"` → only the archived template remains; `nx -r` + browser network tab clean on an admin page. **Commit:** `fix(admin): drop dead output.css links from admin templates`.

### Task 45: Access-control drawer saves explicit Deny for every permission

**Files:** Modify `templates/js/admin/_access_control_js.html` (anchor: the radio default `value="D"`). **Defect:** the profile drawer pre-checks Deny for every permission → saving writes explicit Deny rows for ALL — which also blocks permission-row deletion (the app refuses to delete a referenced Permission; this is why 0043's child-first deletes matter). **Change:** default each radio to the neutral/inherit state (no row); serialize only rows the admin explicitly set to Allow/Deny; map absent rows back to unset on load (read the save-payload builder + backend to confirm the unset representation). **Verify:** e2e/integration — save an untouched drawer → zero new `AccessProfilePermission` rows. **Commit:** `fix(admin): stop the profile drawer writing implicit Deny rows`.

### Task 46: "Last hour" log preset filters by whole days

**Files:** Modify `templates/js/admin/_logs_js.html` (anchor: the `'1h'` preset + `toDateInput`), possibly the log-search backend (`Grep` the filter params in `nx_lib/views/admin.py` — extend parsing only if it accepts dates only). **Defect:** the `1h` preset computes now−1h then truncates through the date-only `toDateInput` → whole-day filter. **Change:** send datetime-precision bounds for sub-day presets; keep day-granularity presets as-is. Coordinates with Task 42's ISO output. **Verify:** browser/e2e — the preset's request spans ~1h. **Commit:** `fix(admin): make the last-hour log preset filter by time, not day`.

### Task 47: `get_index_field_mappings` caches an empty mapping 1h on DB failure

**Files:** Modify `nx_lib/octo.py` (the function under `@cache.cached(timeout=3600, key_prefix="index_field_mappings")`). **Defect:** a DB read failure returns `{}`, which gets cached for an hour → all fields vanish app-wide. **Change:** add `response_filter=lambda v: bool(v)` to the decorator (flask-caching skips caching falsy results) — or, if the installed flask-caching version lacks it, switch to explicit `cache.get`/`cache.set` storing only non-empty results. Keep returning `{}` to callers. **Verify:** unit test — first call fails (empty, uncached), second call re-queries. **Commit:** `fix(octo): stop caching empty index-field mappings on DB failure`.

### Task 48: `get_workitemdata_param` catches only RequestException

**Files:** Modify `nx_lib/octo.py` (`get_workitemdata_param`). **Defect:** a response missing `DocumentID` raises KeyError past the `except requests.exceptions.RequestException` → kills the activity feed (and any caller expecting a falsy "not found"). **Change:** use `.get("DocumentID")` + broaden the except to `(RequestException, KeyError, ValueError)` returning the falsy sentinel callers already guard on. **Verify:** unit test — `{}` JSON body → falsy return, no raise. **Commit:** `fix(octo): return falsy on malformed workitem-data payloads`.

### Task 49: Page-offset counts image media that `get_extensions_urls_fields` skipped

**Files:** Modify `nx_lib/field_locations.py` (`_count_image_media` + callers). **Defect:** the offset counter counts every `IMG_EXTS` media, but `octo.get_extensions_urls_fields` skips media via `if not raw_url: continue` → offsets overcount → source-overlay boxes land on wrong pages in multi-item docs with URL-less media. **Change:** apply the same skip predicate (no raw URL → not counted) so both walks agree; check `nx_lib/table_locations.py` for a twin counter. **Verify:** unit test — a container with one URL-less image between two real pages → offsets match the rendered pages. **Commit:** `fix(workitems): align page offsets with actually rendered media`.

### Task 50: Activity-ignore CSV spliced raw into SQL without quote escaping

**Files:** Modify `nx_lib/process_helpers.py` (anchor: `", ".join("'" + row.ActivityInstanceName + "'")`). **Defect:** raw quote-concatenated names spliced unparameterized into SQL (`… not in ({csv})`) — a name containing `'` breaks (or injects into) every consumer. **Change:** double embedded quotes when building each element (`name.replace("'", "''")`); full parameterization would touch every consumer — out of minimal-diff scope, note as follow-up in the commit body. **Verify:** unit test with an `O'Brien`-style value → valid SQL fragment. **Commit:** `fix(process): escape quotes in the activity-ignore CSV`.

### Task 51: Reporting catalog reads SearchConfig without a ClientCode filter

**Files:** Modify `nx_lib/reporting/catalog.py` (`fetch_docprocessing_catalog`). **Defect:** `SELECT ProcessName, {cols} FROM SearchConfig` with no `ClientCode` filter — MS02 columnar rows contribute phantom field availability to the default docprocessing source. **Change:** scope to the source's client, mirroring how the workitems doc-field path routes on `dbo.SearchConfig.ClientCode` (`Grep "ClientCode"` in `nx_lib/` and copy its NULL-as-default semantics). **Verify:** unit test — an ms02-coded row does not appear in the default catalog. **Commit:** `fix(reporting): scope the docprocessing catalog by client code`.

### Task 52: Exports crash on bytes/control-char cells (merges the export.py + view-path findings)

**Files:** Modify `nx_lib/reporting/export.py` (`_safe_cell`) and `nx_lib/views/reporting.py` (the export path feeding raw DB cells). **Defect:** `_safe_cell` passes bytes/control chars through — openpyxl raises (500, incl. the view export path which does no coercion at all) and the CSV path writes `b'…'` reprs. **Change:** in `_safe_cell`: bytes → `.decode("utf-8", "replace")`, strip openpyxl's `ILLEGAL_CHARACTERS_RE`, non-primitive → `str()`; route the view export path's cells through `_safe_cell` — one fix covers both findings. **Verify:** unit tests with bytes + `\x07` cells for xlsx and csv; integration export → 200. **Commit:** `fix(reporting): coerce bytes and control chars in export cells`.

### Task 53: MIN/MAX aggregates varchar stat columns lexicographically

**Files:** Modify `nx_lib/reporting/query.py` (the `numeric_bases` construct). **Defect:** `numeric_bases` covers only `("sum", "avg")` — MIN/MAX on varchar stat columns compares lexicographically (`"9" > "10"`). **Change:** extend the numeric-conversion wrap to `min`/`max` via the same mechanism. **Verify:** unit test — generated SQL wraps MIN/MAX in the numeric cast. **Commit:** `fix(reporting): aggregate MIN/MAX numerically on varchar stat columns`.

### Task 54: Sandbox blocklist scans string literals

**Files:** Modify `nx_lib/reporting/sandbox.py` (the `_BLOCKED_RE.search(scan)` input). **Defect:** the scan strips comments but not string literals — `… WHERE note = 'update log'` is rejected. **Change:** add a literal-stripper alongside the comment strip (walk `'…'` sequences honoring doubled quotes, replace with `''`) and run the blocklist on the stripped text; root validation of the raw text unchanged. **Verify:** unit tests — a literal containing `update` passes; a real `UPDATE` statement still blocks. **Commit:** `fix(reporting): ignore string literals in the sandbox keyword scan`.

### Task 55: `validate_schedule` raises instead of returning the error

**Files:** Modify `nx_lib/reporting/schedule.py` (`validate_schedule`). **Defect:** `int(wd)` / `int(dom)` raise uncaught ValueError on non-numeric input → 500 not 400 (`hour`/`minute` are already try-guarded). **Change:** guard weekday/dayOfMonth exactly like hour/minute — return the error string, keeping `validate_schedule`'s return contract (do NOT wrap the route in try/except instead). **Verify:** unit test — `weekday="mon"` → error string, no raise. **Commit:** `fix(reporting): return validation errors for weekday and day-of-month`.

### Task 56: `compute_stats` group-by TypeError on numeric keys with NULLs

**Files:** Modify `nx_lib/reporting/stats.py` (anchor: `sorted(buckets, key=lambda k: tuple("" if v is None else v for v in k))`). **Defect:** mixed int/`""` tuples raise TypeError when a numeric group key has NULLs. **Change:** type-stable key — `tuple((v is None, str(v)) for v in k)` (NULLs last, no cross-type compares). **Verify:** unit test with `[None, 3, 1]` group keys. **Commit:** `fix(reporting): sort stat group keys type-safely with NULLs`.

### Task 57: One malformed saved definition 500s the whole report library

**Files:** Modify `nx_lib/views/reporting.py` (`_preview_kind` + its per-row caller in the library listing). **Defect:** a non-dict `cols[0]` raises AttributeError, caught only by the route-level except → the library 500s for everyone. **Change:** type-guard inside `_preview_kind` (fallback kind on malformed shape) AND wrap the per-row serialization so one bad row is skipped/logged, never the whole listing. **Verify:** integration test — one corrupt + one good definition → 200 with the good one listed. **Commit:** `fix(reporting): keep the report library up when one definition is corrupt`.

### Task 58: External API returns 200 zeros on a Statistics-DB outage

**Files:** Modify `nx_lib/views/api_external.py` (+ the `compute_today_stats` legs `_default_stat_rows`/`_ms02_stat_rows` where they live). **Defect:** the stat-row legs swallow failures into `[]`, so an outage yields 200 + zeros; the documented 500 can only fire for a NexoraDB failure. **Change:** let the external-API path distinguish outage from genuinely-empty — thread a `strict=` flag or a sentinel the API call site maps to the documented 500, while the dashboard keeps its graceful degrade. Update `docs/howto/external-api.md` only if the final behavior drifts from its wording. **Verify:** integration test — patched stats-engine failure → external API 500; empty-but-healthy → 200 zeros; dashboard still 200. **Commit:** `fix(api): surface statistics outages as errors on the external API`.

### Task 59: `api_generali_stats` 500 when startDate/endDate absent

**Files:** Modify `nx_lib/views/generali.py` (`api_generali_stats`, anchor: `(request.args.get("startDate")).replace("T", " ")`). **Defect:** absent params → AttributeError on None → 500. **Change:** validate both params up front → 400 JSON with a `_()` message. **Verify:** integration test — GET without params → 400. **Commit:** `fix(generali): return 400 when stats dates are missing`.

### Task 60: CSV export poisons the `media_info` cache with a reduced shape

**Files:** Modify `nx_lib/views/workitems.py` (the export `_fetch` helper caching `{"fields": fields, "media_count": len(urls)}`). **Defect:** the CSV path writes a partial shape (no `field_sources`/`table_sources`, built without `with_tables=True`) under the same `media_info` key `api_get_media_info` serves → the source overlay goes silently empty after an export. **Change:** either build the full payload the detail path caches (mirror `api_get_media_info`'s cache-set incl. `with_tables=True`) or stop the CSV path writing that key entirely (read-through only) — read both sites, smallest diff wins. **Verify:** integration test — after an export, `api_get_media_info` for the same wid still returns `field_sources`. **Commit:** `fix(workitems): stop CSV export poisoning the media-info cache`.

### Task 61: Dashboard `effectiveFilters` keeps only the last filter per field

**Files:** Modify `templates/js/_reporting_dashboard_js.html` (anchor: `byField[f.field] = f`). **Defect:** last-wins keying collapses multiple filters on one field (e.g. two range bounds) → widened card queries. **Change:** accumulate per-field lists (concatenate global + card filters; dedupe exact duplicates only — read the merge consumer first). **Verify:** e2e stub — two filters on one field both appear in the card's run payload. **Commit:** `fix(reporting): keep all dashboard filters per field`.

### Task 62: Switching source keeps the previous source's filters

**Files:** Modify `templates/js/_reporting_js.html` (`pick()`). **Defect:** `pick()` resets `state.columns`/scope/metrics but never `state.filters` → the previous source's filters 400 every Run until cleared by hand. **Change:** `state.filters = []` in the same reset block + re-render the filter chips. **Verify:** e2e — switch source, Run succeeds with no stale chips. **Commit:** `fix(reporting): clear filters when switching sources`.

### Task 63: Pivot bucket keys collide

**Files:** Modify `templates/js/_reporting_viz_js.html` (anchor: `tup(r, dims).join('')`). **Defect:** joining dim values with `''` collides distinct tuples (`['ab','c']` vs `['a','bc']`). **Change:** key with `JSON.stringify(tup(r, dims))` at every keying site (`Grep ".join('')"` in the file for twins — build AND parse sites must match). **Verify:** e2e stub with the colliding tuples → two distinct pivot cells. **Commit:** `fix(reporting): key pivot buckets with unambiguous tuple encoding`.

### Task 64: "Last movement at" sort is a silent no-op

**Files:** Modify `templates/js/_workitems_overview_js.html` (`sortTable`). **Defect:** the date comparator's `parseDate` expects `"d. m. yyyy - HH:MM"` but `renderTable` writes ISO `"YYYY-MM-DD HH:MM:SS"` → Invalid Date → NaN comparator → silent no-op. **Change:** parse ISO (`new Date(text.replace(' ', 'T'))`, NaN fallback to string compare). **Anchor on the rendered date format, not a column index** — the Priority/Tags columns are gone since Task 3, so re-derive the date column's index from the FINAL header row (or a data-attribute); never trust pre-removal indices. Deliberately sequenced after the Part-A column removal. **Verify:** e2e/browser — click the header, row order flips both directions. **Commit:** `fix(workitems): sort the last-movement column with ISO dates`.

---

# PHASE 11 — i18n cycle, changelog Fixed, final verification

### Task 65: pybabel cycle + CHANGELOG Fixed + full-suite gate (D-I18N)

**Files:** Modify `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`), `CHANGELOG.md`.

- [ ] **Step 1 — Extract/update.** `pybabel extract -F babel.cfg -o messages.pot .` then `pybabel update -i messages.pot -d translations`. Removed Python msgids become obsolete `#~` entries (harmless — `test_all_strings_translated` excludes them); archived templates keep their msgids in the pot (babel scans archive dirs). Translate every NEW Part-B msgid (Task 20's current-profile label, Task 21's 400 message, Task 41's neutral flash, Task 59's 400 message — `Grep` the Part-B diffs for `_(` additions) in de/fr/it, non-fuzzy.
- [ ] **Step 2 — Diff-sweep the trap.** `git diff translations/` and inspect every CHANGED existing msgstr line — pybabel has silently mangled lines before (the dropped-"T"-from-T-SQL incident). Repair before compiling.
- [ ] **Step 3 — Compile + test.** `pybabel compile -d translations`; `.venv\Scripts\python -m pytest tests/unit/test_translations.py -q` GREEN (first time since Task 1).
- [ ] **Step 4 — CHANGELOG.** Add the consolidated `[Unreleased] / ### Fixed` block, grouped by subsystem: cross-tenant page-image cache; client-process pair authorization; scheduled-runner scope; recent-activity sensitive gate + client; generali reporting self-scope; AI-agent SQL gates; doc-field value permissions; admin profile reassignment; CSV heavy-include cap; dev_login guard (if shipped); MS02 register fixes (engine, preview client, wid↔pid cast, in-register keying, warm-loop fail-safe); DB-ping deadline; media status caching; CTE cap; categorical GROUP BY; export timeout; KPI totals; filter popover; drill date filters; plus the medium sweep — reference `var/bug-hunt-report.md` for detail. Verify the Task-12 Removed entries still read correctly alongside.
- [ ] **Step 5 — Full gate.** `.venv\Scripts\python scripts/test_db_reset.py` then `.venv\Scripts\python -m pytest tests -q` (all tiers incl. e2e, dev server via `nx -u -b --loginas:` where needed). Fix stragglers before committing.
- [ ] **Step 6 — Commit** (`chore(i18n): translation cycle and changelog for removal and fixes` — body: pot regenerated after the Part-A msgid removals; new Part-B msgids translated de/fr/it; consolidated Fixed changelog; full suite green).
- [ ] **Step 7 — STOP.** Do not push, do not open a PR (Owner action 1).

---

## Gotchas & notes

- **Phase order is a hard constraint, not a preference.** Phases 1–4 strip every code reference to the collaboration tables (incl. the list-query joins in `workitem_sources.py` and `admin_delete_user`'s child-deletes); Phase 5's commits auto-apply the renames to INT via the pre-commit hook. Landing `0042` early breaks the INT workitems list and delete-user instantly. Task 10's Step-1 Grep preflight is the guard — take it seriously. Equally: `url_for('chat_page')` / `url_for('get_notifications')` in the header make Tasks 1 and 9 single-commit removals (template + route together, or every page BuildErrors).
- **Between Task 8 and Task 10,** deleting a user with legacy collaboration rows on INT will FK-fail (transient; 0042 drops those FKs). Don't delete users on INT in that window.
- **Never hand-edit `sql/NexoraDB/**` dumps** — the sync hook regenerates them from INT; in Task 10 just `git add` what appears/disappears. Offline at commit time: `SQL_SYNC_SKIP=1`, never `--no-verify`.
- **Part B anchors live in post-Part-A files.** `workitems.py`, `workitem_sources.py` and `_workitems_overview_js.html` are reshaped by Phases 2–3 — always re-`Grep` the quoted snippet; if it's gone, check whether Part A removed the surrounding block (then the task may be moot — flag it, don't guess).
- **Reporting fix targets are post-redesign "studio" code** (`_reporting_dashboard_js.html`, `_reporting_drill_js.html`, `_reporting_js.html`, `_reporting_viz_js.html` — 2.5.64 state). Anchor on the current function names (`renderKpi`, `openFilterPopover`, `effectiveFilters`, `pick`), not pre-redesign snippets from older notes.
- **VOIDED bugs have no fix task anywhere, on purpose:** chat XSS/IDOR/any-target, comment XSS, tag XSS, comment-id race, stale priority-flag/tag-preview, delete-user tag/metadata wipe (the 2.5.64 atomicity fix survives), and the page-init user-list cache key. They die in Phases 1–4. **ALREADY-FIXED 2.5.64 items must not be re-fixed** — when in doubt, Grep the shipped pattern (`_wi_cache_key`, `client_hint=`, the D8 neutral message, `_c{int(_can_mention)}`) before writing a fix.
- **Archived files are frozen:** don't "fix" stale includes, `url_for`s, or the `output.css` link inside `templates/*/archive/**` — precedent accepts them as-is, and `test_template_url_prefix.py` still scans them (they pass today; keep the `API_PREFIX` idiom in anything you archive).
- **`showNotification` is a toast, not the bell.** Repeated because it is the likeliest accidental deletion in Phase 4.
- **`test_translations.py` stays RED from Task 1 to Task 65** — `--deselect tests/unit/test_translations.py` in every intermediate run. After `pybabel update`, diff-sweep every `.po` for silently mangled msgstrs before compiling.
- **e2e discipline:** `scripts/test_db_reset.py` before every e2e tier; TEST has no Statistics DB; reporting e2e stubs `/api/reporting/run` (the `_stub_run_ok` house pattern) before clicking, or the Simple-AI race makes chips flaky.
- **Compound identity everywhere:** `_wi_cache_key(prefix, wid, domain)` server-side, `${client}-${workitemid}` rowKey client-side; fixes pass through the client the row already carries, never re-probe.
- **Dev server runs global Python** (`nx -u`), `.venv` is tests-only — if a Part-B fix ever needs a new runtime dep (none planned), install into BOTH plus PROD's `D:\sydoc\tools\py`.
- **Data resurrection path:** a future migration renaming `decapitated_*` back + re-adding the Users FKs + reseeding the 8 permission rows + `git mv` the archived templates back + reverting the removal commits restores everything. Nothing in this plan forecloses it.
- **Remote-session rule:** commit only — no push, no PR; capture and send `var/screenshots/` shots for the frontend-visible changes (Tasks 2, 3, 24, 44, and any reporting-JS fix you browser-verify).
