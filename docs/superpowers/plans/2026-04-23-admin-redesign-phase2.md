# Admin Redesign — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `docs/superpowers/specs/2026-04-23-admin-redesign-phase2-design.md`

**Goal:** Add system-health visibility on the admin overview, a real audit trail on the user detail page, admin-driven session revocation, and a permission-impact preview in the access-profile drawer.

**Architecture:** All four features are additive to Phase 1. No new templates; CSS classes from the logs page move into shared tokens. One new DB table (`ActiveSessions`) underpins force-logout. Three new endpoints (activity fetch, revoke one session, revoke all for a user). Backend work mirrors the existing pyodbc + `engineNexoraDB` pattern.

**Tech Stack:** Flask + Jinja2 + Tailwind (CDN) + vanilla JS. Manual verification per task (no test framework). SQL Server via pyodbc / SQLAlchemy engines.

**Conventions:**
- Repo root: `C:\Users\bes\OneDrive - TCG Informatik AG\Dokumente\nexora`
- Branch: `2.5.53`
- Commit style: short imperative, no trailing period
- Do not touch the unstaged `.gitignore` change

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `sql/accessManagement/tables/ActiveSessions.sql` | DDL for the session-tracking table (manual apply per env) |

### Modified files

| Path | Why |
|---|---|
| `app.py` | Health queries + `ping_db` helper in `admin_dashboard`; activity endpoint; login-flow session-tracking insert; 2 revoke endpoints |
| `static/css/admin-tokens.css` | Shared `.log-method--*` / `.log-status--*`; `.health-strip` styles |
| `templates/admin/logs.html` | Drop now-shared inline CSS |
| `templates/admin/adminOverview.html` | Render health strip above launcher grid |
| `templates/admin/userDetail.html` | Real activity table; "Sign out everywhere" in Danger zone |
| `templates/js/admin/_userDetailJS.html` | Activity fetcher/pager; sign-out-everywhere handler |
| `templates/admin/sessions.html` | Actions column |
| `templates/js/admin/_sessionsJS.html` | Revoke button rendering + click handler |
| `templates/admin/accessControl.html` | Drawer footer impact span |
| `templates/js/admin/_accessControlJS.html` | Set impact count when drawer opens |

---

## Task 1: Share log method/status styles + add health-strip tokens

**Files:**
- Modify: `static/css/admin-tokens.css`
- Modify: `templates/admin/logs.html`

- [ ] **Step 1: Append to `static/css/admin-tokens.css`:**

```css
/* Shared method / status cells (Logs + user-detail Activity) */
.log-method { font-weight:700; font-family:"SF Mono",Consolas,"Roboto Mono",monospace; font-size:11px; margin-right:6px; }
.log-method--GET    { color:#2563eb; }
.log-method--POST   { color:#15803d; }
.log-method--PUT    { color:#b54708; }
.log-method--DELETE { color:#b42318; }
.log-status { display:inline-flex; align-items:center; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:500; font-family:"SF Mono",Consolas,"Roboto Mono",monospace; }
.log-status--ok    { background:#d1fae5; color:#065f46; }
.log-status--warn  { background:#fef3c7; color:#92400e; }
.log-status--error { background:#fee2e2; color:#991b1b; }

/* Health strip on admin overview */
.health-strip { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:16px; margin-bottom:20px; }
.health-card { padding:16px 18px; }
.health-card-label { font-size:11px; font-weight:600; letter-spacing:0.6px; text-transform:uppercase; color:var(--a-text-meta); margin-bottom:6px; }
.health-card-value { font-size:24px; font-weight:600; letter-spacing:-0.4px; color:var(--a-text); line-height:1.2; }
.health-card-value.is-danger { color:var(--a-danger); }
.health-card-sub { font-size:12px; color:var(--a-text-sec); margin-top:4px; }
.health-db-list { display:flex; flex-wrap:wrap; gap:6px; }
.health-db-pill { display:inline-flex; align-items:center; gap:6px; padding:3px 8px; border-radius:999px; font-size:11px; font-weight:500; background:var(--a-b-gray); color:var(--a-b-gray-fg); }
.health-db-pill--ok  { background:var(--a-b-green); color:var(--a-b-green-fg); }
.health-db-pill--err { background:var(--a-b-red);   color:var(--a-b-red-fg);   }
.health-db-pill .dot { width:6px; height:6px; border-radius:50%; background:currentColor; opacity:0.7; }
```

- [ ] **Step 2:** In `templates/admin/logs.html`, remove the 9 `.log-method*` / `.log-status*` lines inside the inline `<style>` block (keep `.log-preset*` and `.code-scroll*`).

- [ ] **Step 3: Verify** — start `python app.py`, open `/admin/logs`, confirm method color + status badge still render.

- [ ] **Step 4: Commit**
```
git add static/css/admin-tokens.css templates/admin/logs.html
git commit -m "Share log method/status styles and add health-strip tokens"
```

---

## Task 2: Health strip backend (queries + ping helper)

**Files:** `app.py`

- [ ] **Step 1:** Add `ping_db(engine, label, timeout_s=2.0)` helper below the engine definitions. Signature returns `{label, ok, error, latency_ms}`. Uses `engine.raw_connection()` + cursor + `SELECT 1` + close. Never raises: catches all exceptions and returns `ok=False` with a truncated error message and measured latency. Track latency with `time.monotonic()`.

- [ ] **Step 2:** Replace body of `admin_dashboard` (line 792). Inside a single try/except over `engineNexoraDB`, compute four counts:

```
SELECT COUNT(*) FROM Users
SELECT COUNT(*) FROM organizations
SELECT COUNT(DISTINCT Username) FROM Logs WHERE Timestamp > DATEADD(minute, -5, GETDATE()) AND Username IS NOT NULL
SELECT COUNT(*) FROM Logs WHERE Path='/login' AND HttpRequestMethod='POST' AND HttpResponseCode >= 400 AND Timestamp >= CAST(GETDATE() AS DATE)
```

Then call `ping_db` for each of `engineNexoraDB`, `engineOctoDB`, `engineStatisticsDB`, `engineStatisticsDBMobscan`, `engineGeneraliDB`. Pass `active_users_5m`, `failed_logins_today`, `db_health` (list) to `render_template` alongside the existing kwargs.

Failed queries leave the count as `None` (not 0) so the template can render `—`.

- [ ] **Step 3: Verify** — `/admin` renders; no template change yet so values are unused. No errors in server log.

- [ ] **Step 4: Commit**
```
git add app.py
git commit -m "Add admin overview health queries and ping_db helper"
```

---

## Task 3: ActiveSessions DDL

**Files:** `sql/accessManagement/tables/ActiveSessions.sql`

- [ ] **Step 1:** Create with `IF NOT EXISTS` guarded `CREATE TABLE dbo.ActiveSessions`. Columns: `SessionID NVARCHAR(64) PRIMARY KEY`, `UserID INT NOT NULL`, `CreatedAt DATETIME NOT NULL` with `DEFAULT GETDATE()`. Create index `IX_ActiveSessions_UserID` on `(UserID)` inside the same guard.

- [ ] **Step 2: Manually apply** to the INT DB via your usual tool. Verify:
```
SELECT * FROM sys.tables WHERE name = 'ActiveSessions';
```

- [ ] **Step 3: Commit**
```
git add sql/accessManagement/tables/ActiveSessions.sql
git commit -m "Add ActiveSessions table DDL"
```

---

## Task 4: Login-flow session-tracking hook

**Files:** `app.py`

- [ ] **Step 1:** Add `_record_active_session(user_id)` directly above `def login():`. Read `session.sid` (prod filesystem backend exposes this); fall back to `session['_dev_sid']` or generate a UUID hex and store it there (dev). INSERT `(sid, user_id)` into `ActiveSessions` via `engineNexoraDB.raw_connection()` + `conn.commit()`. Wrap whole body in try/except that logs warning only — never break login.

- [ ] **Step 2:** Inside `login()`, call `_record_active_session(userid)` immediately after every `session['permissions'] = load_permissions_for_user(...)` line. There are 3 demo-login branches (userids "1019", demo.user, demo.user2) and the real-login branch. Grep for `load_permissions_for_user` inside the function — each success-path match gets one new helper call after it, before the redirect.

- [ ] **Step 3: Verify** — log in; `SELECT TOP 5 * FROM ActiveSessions ORDER BY CreatedAt DESC` shows a new row.

- [ ] **Step 4: Commit**
```
git add app.py
git commit -m "Record active sessions in ActiveSessions on login"
```

---

## Task 5: Health strip UI on overview

**Files:** `templates/admin/adminOverview.html`

- [ ] **Step 1:** Insert `<div class="health-strip">` directly after the `{{ a.page_header(...) }}` call, before the existing launcher grid. Three `admin-card health-card` children:

```jinja
<div class="health-strip">
    <div class="admin-card health-card">
        <div class="health-card-label">{{ _('Active users (5 min)') }}</div>
        <div class="health-card-value">
            {% if active_users_5m is not none %}{{ active_users_5m }}{% else %}—{% endif %}
        </div>
        <div class="health-card-sub">{{ _('Users active in the last 5 minutes') }}</div>
    </div>
    <div class="admin-card health-card">
        <div class="health-card-label">{{ _('Failed logins today') }}</div>
        <div class="health-card-value {% if failed_logins_today and failed_logins_today > 0 %}is-danger{% endif %}">
            {% if failed_logins_today is not none %}{{ failed_logins_today }}{% else %}—{% endif %}
        </div>
        <div class="health-card-sub">{{ _('Since midnight') }}</div>
    </div>
    <div class="admin-card health-card">
        <div class="health-card-label">{{ _('Database health') }}</div>
        <div class="health-db-list" style="margin-top:8px">
            {% for db in db_health %}
            <span class="health-db-pill {% if db.ok %}health-db-pill--ok{% else %}health-db-pill--err{% endif %}"
                  title="{% if db.ok %}{{ db.latency_ms }} ms{% else %}{{ db.error }}{% endif %}">
                <span class="dot"></span>{{ db.label }}
            </span>
            {% endfor %}
        </div>
    </div>
</div>
```

- [ ] **Step 2: Verify** — `/admin` shows the strip; 5 DB pills; narrow viewport stacks.

- [ ] **Step 3: Commit**
```
git add templates/admin/adminOverview.html
git commit -m "Render system health strip on admin overview"
```

---

## Task 6: Per-user activity endpoint

**Files:** `app.py`

- [ ] **Step 1:** Add new route right after `admin_user_detail` (line ~1232) and before `admin_delete_user`:

`GET /api/admin/users/<int:user_id>/activity`, guard `admin.view.accessprofiles.useroverrides`.

Read `page` query param (default 1), per_page 25, offset `max(0, (page-1)*25)`. Resolve username with `SELECT username FROM Users WHERE userID = ?`. If no user, return empty JSON.

COUNT query:
```
SELECT COUNT(*) FROM Logs
WHERE Username = ? AND Timestamp >= DATEADD(day, -7, GETDATE())
```

Paginated select:
```
SELECT Timestamp, HttpRequestMethod, Path, HttpResponseCode
FROM Logs
WHERE Username = ? AND Timestamp >= DATEADD(day, -7, GETDATE())
ORDER BY Timestamp DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
```

Build entries list as `[{Timestamp, HttpRequestMethod, Path, HttpResponseCode}]`. Compute `pages = max(1, math.ceil(total/25))` or 0 when total is 0. Return `{entries, total, page, pages}`. Wrap in try/except; on failure return 500 with `{error, entries: [], total: 0, page, pages: 0}`.

- [ ] **Step 2: Verify** — curl endpoint; valid user returns entries; invalid user returns empty; `?page=2` works.

- [ ] **Step 3: Commit**
```
git add app.py
git commit -m "Add per-user activity endpoint"
```

---

## Task 7: Activity UI on user detail

**Files:** `templates/admin/userDetail.html`, `templates/js/admin/_userDetailJS.html`

- [ ] **Step 1:** In `userDetail.html`, replace the placeholder Activity card with:

```jinja
{# Activity — last 7 days #}
<div class="admin-card" style="margin-bottom:20px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:12px;flex-wrap:wrap">
        <div>
            <div class="admin-section">{{ _('Activity') }}</div>
            <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">{{ _('Recent actions by this user — last 7 days.') }}</p>
        </div>
        <a href="{{ url_for('admin_logs_view') }}?username={{ user.username|urlencode }}"
           class="admin-btn admin-btn-ghost" style="font-size:12px">
            {{ _('View all in logs') }} <i class="fas fa-arrow-right" style="font-size:10px;margin-left:4px"></i>
        </a>
    </div>
    <div class="admin-table-wrap">
        <table class="admin-table">
            <thead>
                <tr>
                    <th style="width:170px">{{ _('Time') }}</th>
                    <th>{{ _('Action') }}</th>
                    <th class="align-right" style="width:130px">{{ _('Status') }}</th>
                </tr>
            </thead>
            <tbody id="activityTbody" data-user-id="{{ user.userID }}">
                <tr><td colspan="3" class="admin-empty"><i class="fas fa-circle-notch fa-spin"></i> &nbsp; {{ _('Loading...') }}</td></tr>
            </tbody>
        </table>
        <div style="padding:10px 16px;border-top:1px solid var(--a-border);display:flex;align-items:center;justify-content:space-between">
            <span style="font-size:12px;color:var(--a-text-sec)" id="activityPageInfo"></span>
            <div style="display:flex;gap:8px">
                <button id="activityPrevBtn" class="admin-btn admin-btn-secondary" type="button" disabled>{{ _('Previous') }}</button>
                <button id="activityNextBtn" class="admin-btn admin-btn-secondary" type="button" disabled>{{ _('Next') }}</button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 2:** Append to `_userDetailJS.html` a self-invoking function that:
  - grabs `#activityTbody`, reads `data-user-id`
  - declares `esc`, `statusBadge(code)` (returns `<span class="log-status log-status--ok|warn|error">CODE</span>` based on HTTP code), `relativeTime(iso)` ("just now" / "N min ago" / "N h ago" / "N d ago")
  - `load(page)` fetches `/api/admin/users/${userId}/activity?page=${page}` with `X-CSRFToken`, sets tbody rows like:

```
<tr>
  <td title="ISO">relative time</td>
  <td>
    <span class="log-method log-method--METHOD">METHOD</span>
    <span class="admin-mono" style="font-size:11px">short path</span>
  </td>
  <td class="align-right">[status badge]</td>
</tr>
```

  - updates `#activityPageInfo` text and prev/next disabled flags
  - wires click handlers and initial load on `DOMContentLoaded`

- [ ] **Step 3: Verify** — user with activity: table populates, pagination works. User without: empty-state message. "View all in logs" link navigates with username pre-filled.

- [ ] **Step 4: Commit**
```
git add templates/admin/userDetail.html templates/js/admin/_userDetailJS.html
git commit -m "Add real activity table with pagination to user detail"
```

---

## Task 8: Force-logout endpoints

**Files:** `app.py`

- [ ] **Step 1:** Add helper `_revoke_session_by_id(session_id)`: DELETE from `ActiveSessions WHERE SessionID = ?`, capture rowcount, commit. Then try to unlink `os.path.join(app.config.get('SESSION_FILE_DIR') or os.path.join(app.root_path,'session'), session_id)` inside its own try/except (log warning on failure; missing file is fine). Return bool (did row exist?).

- [ ] **Step 2:** Add route `POST /admin/sessions/<string:session_id>/revoke` guarded by `admin.edit.user.override`. Calls helper; returns `{success: true}` or 500 JSON on exception.

- [ ] **Step 3:** Add route `POST /admin/users/<int:user_id>/revoke_all` guarded by `admin.edit.user.override`. SELECT all SessionIDs for the user, iterate and call helper for each, count successes. `app.logger.info` the admin username + count. Return `{success: true, revoked: N}`.

- [ ] **Step 4:** Ensure `import os` exists near top of `app.py` (usually already there).

- [ ] **Step 5: Verify** — log in from two browsers; SELECT SessionIDs; POST revoke for one; row disappears; POST revoke_all; all rows for user gone.

- [ ] **Step 6: Commit**
```
git add app.py
git commit -m "Add session revoke endpoints"
```

---

## Task 9: Sessions page — Actions column

**Files:** `app.py`, `templates/admin/sessions.html`, `templates/js/admin/_sessionsJS.html`

- [ ] **Step 1:** In `admin_active_sessions` (line ~1283), update the SELECT list to include `MIN(SessionID) AS SessionID` as the first column (grouping already includes SessionID).

- [ ] **Step 2:** In `sessions.html`, add `Actions` column (align-right, width 130px) to the `a.table_header(...)` macro call. Update loading-state colspan from 4 to 5.

- [ ] **Step 3:** In `_sessionsJS.html`, update rows in `fetchActiveSessions` to include an Actions cell with a red ghost button:

```
<button type="button"
        class="admin-btn admin-btn-ghost revoke-session-btn"
        style="color:var(--a-danger);font-size:12px"
        data-session-id="ESCAPED_SID"
        data-username="ESCAPED_USERNAME"
        title="Revoke this session">
  <i class="fas fa-sign-out-alt"></i> Revoke
</button>
```

Change all existing loading/empty/error placeholders from `colspan="4"` to `colspan="5"`.

- [ ] **Step 4:** Append a delegated click listener for `.revoke-session-btn`: `confirm(...)` → POST `/admin/sessions/${sid}/revoke` with CSRF header → call `fetchActiveSessions()` on success.

- [ ] **Step 5: Verify** — column renders; revoke confirms + refreshes.

- [ ] **Step 6: Commit**
```
git add app.py templates/admin/sessions.html templates/js/admin/_sessionsJS.html
git commit -m "Add revoke session action to active sessions page"
```

---

## Task 10: "Sign out everywhere" on user detail

**Files:** `templates/admin/userDetail.html`, `templates/js/admin/_userDetailJS.html`

- [ ] **Step 1:** In the Danger zone card, wrap the existing `#deleteUserBtn` in `<div style="display:flex;gap:8px;flex-wrap:wrap">` and add a sibling secondary button `#signOutAllBtn` BEFORE it with `data-user-id`, `data-username` attributes, icon `fa-sign-out-alt`, label "Sign out everywhere".

- [ ] **Step 2:** Append handler in `_userDetailJS.html` on `DOMContentLoaded`: confirm dialog ("Sign out ALL active sessions for {username}? They will be forced to log in again.") → POST `/admin/users/${userId}/revoke_all` with CSRF → toast via existing `userDetailToast`.

- [ ] **Step 3: Verify** — click → confirm → toast reports N; `SELECT COUNT(*) FROM ActiveSessions WHERE UserID=<id>` = 0.

- [ ] **Step 4: Commit**
```
git add templates/admin/userDetail.html templates/js/admin/_userDetailJS.html
git commit -m "Add sign out everywhere action to user detail"
```

---

## Task 11: Permission impact preview in drawer

**Files:** `templates/admin/accessControl.html`, `templates/js/admin/_accessControlJS.html`

- [ ] **Step 1:** Wrap `#drawerSelectedCount` span with a parent span that includes a sibling `#drawerImpactCount` separated by a middot:
```
<span style="font-size:12px;color:var(--a-text-meta)">
    <span id="drawerSelectedCount"></span>
    <span id="drawerImpactSep" style="margin:0 6px;opacity:0.6">·</span>
    <span id="drawerImpactCount"></span>
</span>
```

- [ ] **Step 2:** In `_accessControlJS.html`, add `setDrawerImpact(text)` helper that sets `#drawerImpactCount` textContent.

- [ ] **Step 3:** In `openProfileDrawer()` (new profile), after `openDrawer(...)` call `setDrawerImpact("will affect 0 users (new profile)")`.

- [ ] **Step 4:** In `editProfile(id)`, read `profilesMap[id].userCount` and call `setDrawerImpact("will affect N user(s)")` based on the count.

- [ ] **Step 5:** In `openUserOverrideModal(userId)` (if still reachable after Phase 1 Task 14 removed the Overrides action from rows), read `usersMap[userId].username` and call `setDrawerImpact("will affect 1 user: USERNAME")`.

- [ ] **Step 6: Verify** — Access Profiles tab → Edit → drawer footer shows impact.

- [ ] **Step 7: Commit**
```
git add templates/admin/accessControl.html templates/js/admin/_accessControlJS.html
git commit -m "Show permission impact count in drawer footer"
```

---

## Task 12: i18n — DE translations

- [ ] **Step 1:** Extract + update:
```
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2:** Identify new empty msgids:
```
awk '/^msgid/{m=$0} /^msgstr ""$/{if(m!="msgid \"\"") print m}' translations/de/LC_MESSAGES/messages.po
```

- [ ] **Step 3:** Fill in German msgstr values for the Phase 2 additions. Suggested:

| msgid | German |
|---|---|
| Active users (5 min) | Aktive Benutzer (5 Min) |
| Users active in the last 5 minutes | In den letzten 5 Minuten aktive Benutzer |
| Failed logins today | Fehlgeschlagene Anmeldungen heute |
| Since midnight | Seit Mitternacht |
| Database health | Datenbankstatus |
| Recent actions by this user — last 7 days. | Letzte Aktionen dieses Benutzers — 7 Tage. |
| View all in logs | Alle in Protokollen anzeigen |
| No recorded activity in the last 7 days. | Keine Aktivität in den letzten 7 Tagen. |
| Could not load activity. | Aktivität konnte nicht geladen werden. |
| Page | Seite |
| of | von |
| entries | Einträge |
| just now | gerade eben |
| Revoke | Beenden |
| Revoke this session | Diese Sitzung beenden |
| Revoke the active session for | Aktive Sitzung beenden für |
| Could not revoke session. | Sitzung konnte nicht beendet werden. |
| Network error. | Netzwerkfehler. |
| Sign out everywhere | Überall abmelden |
| Sign out ALL active sessions for | ALLE aktiven Sitzungen beenden für |
| They will be forced to log in again. | Die Person muss sich neu anmelden. |
| Revoked | Beendet |
| session(s). | Sitzung(en). |
| Revoke failed. | Beenden fehlgeschlagen. |
| will affect | betrifft |
| user | Benutzer |
| users | Benutzer |
| will affect 1 user: | betrifft 1 Benutzer: |
| will affect 0 users (new profile) | betrifft 0 Benutzer (neues Profil) |

Remove any `#, fuzzy` markers on entries you've filled in.

- [ ] **Step 4:** Compile:
```
pybabel compile -d translations
```

- [ ] **Step 5: Verify** — switch locale to DE; new labels localize.

- [ ] **Step 6: Commit**
```
git add translations/
git commit -m "Translate Phase 2 admin strings into German"
```

---

## Task 13: Final smoke test

- [ ] Run end-to-end as admin:
  1. `/admin` → health strip + launcher render; numbers populate; DB pills green
  2. `/admin/users/<id>` → Activity populates; pagination works; Sign out everywhere works
  3. `/admin/sessions` → Actions column; Revoke works
  4. `/admin/access_control` → Edit profile → drawer footer shows impact
  5. Permission check: user with only `admin.view` cannot call revoke endpoints (403)
  6. DE locale: labels localize

- [ ] Fix any failures as new commits referencing the failing task number.

---

## Self-review

**Spec coverage:**
- §1 Health strip → Tasks 1 (CSS), 2 (backend), 5 (UI)
- §2 Audit trail → Tasks 6 (endpoint), 7 (UI)
- §3 Force-logout → Tasks 3 (DDL), 4 (login hook), 8 (endpoints), 9 (sessions UI), 10 (detail UI)
- §4 Impact preview → Task 11
- §7 i18n → Task 12
- §8/§9 Testing/rollout → Task 13

**Placeholder scan:** No TBD/TODO placeholders. Task 4 explicitly asks the engineer to grep inside `login()` for insertion points — intentional, reads the current code.

**Type consistency:**
- `ActiveSessions(SessionID, UserID, CreatedAt)` used consistently (Tasks 3, 4, 8, 9)
- `_revoke_session_by_id(sid)` returns bool (Tasks 8, 10)
- `ping_db` return shape `{label, ok, error, latency_ms}` matches Task 5 template
- Activity endpoint shape `{entries, total, page, pages}` matches Task 7 JS
- CSS classes `.log-method--*` / `.log-status--*` consistent across Tasks 1 and 7
