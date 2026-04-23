# Admin Redesign — Phase 2 Design

**Date:** 2026-04-23
**Status:** Design approved, pending implementation plan
**Depends on:** Phase 1 (shipped on branch `2.5.53`, commits `52c2759..086dc91`)

## Context

Phase 1 delivered a consistent visual language, nested sidebar navigation, a new user detail page, and better filters. Four capabilities deferred from Phase 1 land here:

1. System health strip on the admin overview
2. Real audit trail on the user detail page (replacing the "Coming in a future release" placeholder)
3. Force-logout — revoking a user's active sessions from the admin section
4. Permission impact preview in the access-profile drawer

These features share the existing Phase 1 design system; this phase introduces no new visual tokens, macros, or layouts.

## Goals

- Give admins at-a-glance operational visibility on the overview page
- Let admins answer "what did this user do recently" without leaving the user detail page
- Let admins revoke sessions without shell access to the prod server
- Let admins see the blast radius of a permission-profile change before saving

## Non-goals

- Historical retention beyond what the existing `Logs` table already keeps
- Real-time streaming dashboards / websockets — all health data is fetched at page-load
- Self-service session management for the end user (no "sign me out everywhere" on the profile page)
- Permission impact for user overrides beyond counting affected users (no simulation of effective permissions)

## Target audience

Same as Phase 1 — small technical team. Design biases toward density and signal over decoration.

---

## 1. System health strip on Overview

### UI

A horizontal strip placed **above** the existing 2×2 launcher cards on the admin overview (`templates/admin/adminOverview.html`). Three equal cells in a CSS grid, responsive (stack on narrow screens).

| Cell | Primary value | Secondary | Source |
|---|---|---|---|
| Active users (5 min) | count | "users active in the last 5 minutes" | Logs table |
| Failed logins today | count | "since midnight" — red accent if > 0 | Logs table |
| Database health | 5 pills, one per engine | Ping result / error | 5 SQLAlchemy engines |

Each cell uses the existing `.admin-card` as its container for visual consistency with the cards below.

### Data sources

Three queries added to the `admin_dashboard` route (`app.py` line 792). All queries run in a single try/except so any individual failure shows "—" in that cell without taking down the page.

**Active users (5 min):**
```sql
SELECT COUNT(DISTINCT Username)
FROM Logs
WHERE Timestamp > DATEADD(minute, -5, GETDATE())
  AND Username IS NOT NULL
```

**Failed logins today:**
```sql
SELECT COUNT(*)
FROM Logs
WHERE Path = '/login'
  AND HttpRequestMethod = 'POST'
  AND HttpResponseCode >= 400
  AND Timestamp >= CAST(GETDATE() AS DATE)
```

**Database health:** A Python helper `ping_db(engine, label, timeout_s=2.0)` attempts `SELECT 1` on each of the five engines (`engineNexoraDB`, `engineOctoDB`, `engineStatisticsDB`, `engineStatisticsDBMobscan`, `engineGeneraliDB`). Returns a dict `{label, ok, error}`. Timeouts or connection errors return `ok=False` with the truncated error message.

### Error handling

Health queries must not block the page. Each cell is wrapped in its own try/except. If the Logs-based counts fail, they render as "—". If a DB ping fails, its pill turns red with a tooltip showing the error message. The overview page always renders.

### Out of scope

No auto-refresh. No historical trends ("errors up 20% from yesterday"). No alerting.

---

## 2. Audit trail on user detail page

### UI

The Activity card on `templates/admin/userDetail.html` (currently a placeholder that reads "Coming in a future release") becomes a paginated table of the user's recent actions.

- **Default range:** last 7 days
- **Page size:** 25 rows
- **Columns:** Time (relative + tooltip absolute) · Action (method + truncated path) · Status (pill)
- **Footer:** pagination controls ("Page 1 of 3 (62 entries)") + "View all in logs →" link to `/admin/logs?username=<u>`
- **Empty state:** "No recorded activity in the last 7 days."

Reuses the method-color CSS classes (`.log-method--GET|POST|PUT|DELETE`) and status badges (`.log-status--ok|warn|error`) defined on the Logs page; these styles are moved into `admin-tokens.css` to be shared.

### API

New endpoint `GET /api/admin/users/<int:user_id>/activity`.

**Query params:** `page` (default 1), fixed page size 25.

**Permission:** `admin.view.accessprofiles.useroverrides` (same as other user-detail reads).

**Response:**
```json
{
  "entries": [
    {"Timestamp": "...", "HttpRequestMethod": "POST", "Path": "/api/...", "HttpResponseCode": 200}
  ],
  "page": 1,
  "pages": 3,
  "total": 62
}
```

**SQL:** look up the user's username first, then:
```sql
SELECT Timestamp, HttpRequestMethod, Path, HttpResponseCode
FROM Logs
WHERE Username = ?
  AND Timestamp >= DATEADD(day, -7, GETDATE())
ORDER BY Timestamp DESC
OFFSET ? ROWS FETCH NEXT 25 ROWS ONLY
```
A corresponding COUNT query for pagination total.

### Template changes

`templates/admin/userDetail.html`: replace the Activity placeholder card body with a table container plus an inline pagination block. The card heading ("Activity") stays.

`templates/js/admin/_userDetailJS.html`: append an activity loader that fires on `DOMContentLoaded`, fetches the endpoint, renders rows, wires prev/next pagination.

### Error handling

Fetch failure renders an inline empty-state message ("Could not load activity — try refreshing."). The rest of the detail page stays functional.

---

## 3. Force-logout (active session revocation)

### Session backend

**Production:** Flask-Session filesystem backend is active. Session data persists as one file per session in `./session/`, filename = session ID (the Flask `sid`).

**Dev:** `Session(app)` is commented out locally (author's preference). Falls back to signed-cookie sessions with no server files.

The design works in both environments: on prod, force-logout deletes the session file; on dev, the file doesn't exist so unlink is a no-op (warning logged, HTTP response still OK).

### New DB table

```sql
CREATE TABLE ActiveSessions (
    SessionID NVARCHAR(64) NOT NULL PRIMARY KEY,
    UserID    INT NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT GETDATE()
);
CREATE INDEX IX_ActiveSessions_UserID ON ActiveSessions(UserID);
```

DDL file added at `sql/accessManagement/tables/ActiveSessions.sql` (manual apply per environment, matching the existing convention).

### Login hook

In `app.py` login flow, **after** each `session.clear()` + session dict assignment succeeds, record the session:

```python
conn = engineNexoraDB.raw_connection()
cursor = conn.cursor()
cursor.execute(
    "INSERT INTO ActiveSessions (SessionID, UserID) VALUES (?, ?)",
    (_get_current_sid(), session['userid'])
)
conn.commit()
cursor.close(); conn.close()
```

`_get_current_sid()` is a small helper that reads Flask-Session's current session ID from `session.sid` (prod) or falls back to a generated UUID stored in `session['_dev_sid']` (dev). Dev rows still record for testability.

This is inserted in three spots (for the three existing login branches: demo user 123, demo 321, demo 456, and the real login flow). Don't duplicate the helper — DRY.

### Revoke endpoints

**Revoke one session:**
```python
@app.route("/admin/sessions/<string:session_id>/revoke", methods=['POST'])
@require_permission('admin.edit.user.override')
def admin_revoke_session(session_id): ...
```
Steps: delete the row from `ActiveSessions`; attempt to unlink `<SESSION_FILE_DIR>/<session_id>` (silently OK if not found); return `{success: true}`.

**Revoke all sessions for a user:**
```python
@app.route("/admin/users/<int:user_id>/revoke_all", methods=['POST'])
@require_permission('admin.edit.user.override')
def admin_revoke_all_sessions(user_id): ...
```
Steps: `SELECT SessionID FROM ActiveSessions WHERE UserID = ?`; for each, unlink the file and delete the row; return `{success: true, revoked: N}`.

Both endpoints log the admin who performed the revocation.

### UI integration

**On the Sessions page (`templates/admin/sessions.html`):**
- Table gains an Actions column (align-right, width 120px).
- Each row renders a small "Sign out" icon button (danger-ghost style). Click → POST revoke endpoint → row flashes and disappears after refresh.
- Table re-fetch via `fetchActiveSessions()` after successful revoke.

**On the user detail page:**
- Danger zone card gains a secondary button next to the "Delete user" button: **"Sign out everywhere"**.
- Clicking it confirms in a small dialog, then POSTs `/admin/users/<id>/revoke_all`.
- Toast on success, page stays on detail view.

### Out of scope

- Server-side session retention policies (deleting stale rows): not in this spec. The table grows monotonically; a simple cron-cleanup job can be a follow-up. A Stale Row cleanup trigger: not needed for V1.
- Forcing re-2FA: force-logout alone ends sessions; next login goes through the normal flow.

---

## 4. Permission impact preview in the drawer

### UI

The existing permission-drawer footer already shows "N allowed, N denied" (`drawerSelectedCount`). A third piece of text is added after it:

```
3 allowed · 1 denied  ·  will affect 42 users
```

Rendered as an additional `<span>` inside the existing footer's flex container, muted-text color, same font size.

### Data

For `profile` drawer mode (editing an access profile):
- On drawer open for an existing profile, use the server-provided `profile.UserCount` (already passed to `profilesMap` in `accessControl.html`).
- The count does NOT change as radios are flipped — changing a profile's permissions doesn't change *who* has the profile, only what they can do. So "will affect X" stays static during the session.
- For new profiles (`accessId=0`), show "will affect 0 users (new profile)".

For `user` drawer mode (overrides for one user):
- Shows "will affect 1 user (<username>)". No endpoint call — the user is already known from `usersMap`.

### No new endpoint

Both counts are already present on the client; we surface them in the existing footer without any extra network calls.

### Template changes

`templates/admin/accessControl.html`: drawer footer gains a span with id `drawerImpactCount`.

`templates/js/admin/_accessControlJS.html`: `openProfileDrawer()`, `editProfile(id)`, and `openUserOverrideModal(userId)` each set the text on `drawerImpactCount` based on the relevant data.

### Out of scope

- A diff preview ("this change will add/remove N permissions from N users"). Requires simulating effective permissions across all users — too heavy for V1.
- Export of affected users list.

---

## 5. File structure

### New files

| Path | Purpose |
|---|---|
| `sql/accessManagement/tables/ActiveSessions.sql` | DDL for the session tracking table |

### Modified files

| Path | Why |
|---|---|
| `app.py` | 3 health queries + `ping_db` helper in `admin_dashboard`; activity endpoint; 2 revoke endpoints; session-tracking insert in login flow |
| `static/css/admin-tokens.css` | Move `.log-method--*` and `.log-status--*` classes from `logs.html` inline styles to shared tokens; add health-strip styles |
| `templates/admin/adminOverview.html` | Add health strip above launcher cards |
| `templates/admin/userDetail.html` | Replace Activity placeholder with real table + "Sign out everywhere" button in Danger zone |
| `templates/js/admin/_userDetailJS.html` | Activity loader + pagination + "sign out everywhere" handler |
| `templates/admin/sessions.html` | Add Actions column |
| `templates/js/admin/_sessionsJS.html` | Render Actions column + revoke handler |
| `templates/admin/accessControl.html` | Drawer footer span for impact count |
| `templates/js/admin/_accessControlJS.html` | Set impact count when drawer opens |
| `templates/admin/logs.html` | Remove now-shared `.log-method--*`/`.log-status--*` inline CSS (moved to tokens) |

---

## 6. Permissions

All existing admin permission codes already cover these features:

| Feature | Required permission |
|---|---|
| Health strip | `admin.view` (already gates overview) |
| Activity endpoint | `admin.view.accessprofiles.useroverrides` |
| Revoke session / revoke all | `admin.edit.user.override` |
| Impact preview data | none beyond existing `admin.view.accessprofiles.useroverrides` — data is already served |

No new permission codes.

---

## 7. i18n

Estimated ~15 new translatable strings across the four features. Added in a single translation pass at the end, following the Phase 1 approach: extract, update, translate DE only, compile. French and Italian continue to fall back to English.

## 8. Testing

Manual verification per task, consistent with Phase 1. Each task's verification step covers the happy path plus the most important failure case (DB error, missing session file, zero activity, etc.).

## 9. Rollout

Single deploy behind no flag — audience is small and the features are additive. Backward-compatible: existing routes, sessions and permissions remain valid. The one DDL migration (`ActiveSessions` table) must be applied manually per environment before the login hook can insert.

## Open questions (resolve during implementation)

- Should the "Sign out" icon button on Sessions require a confirm dialog, or is a single click enough for this power-user audience?
- Retention of `ActiveSessions` rows: deferred to a future cleanup job or handled by periodic `cleanup/*.ps1` — not in this spec.

## Out of scope — deferred to Phase 3

- Command palette (Ctrl+K)
- Dark-mode parity for admin pages
- Saved filter presets
- CSV export of logs / activity
