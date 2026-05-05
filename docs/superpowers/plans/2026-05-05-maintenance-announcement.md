# Maintenance Announcement Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins configure a per-banner "announce X minutes before" lead time so users see a dismissible countdown banner before a maintenance window locks them out.

**Architecture:** Add `AnnounceMinutesBefore INT` to the `MaintenanceBanner` table. Extend `GET /api/maintenance/active` to return upcoming-window banners (priority 2 after live banners). The existing `_maintenance_banner.html` partial becomes polling-based and renders two modes: live (unchanged) and upcoming (clock icon + countdown).

**Tech Stack:** SQL Server (pyodbc/SQLAlchemy raw_connection), Flask/Python, Jinja2, vanilla JS (no framework), Flatpickr (already in use for date inputs).

---

## File Map

| File | Change |
|---|---|
| `environment_transfer_queries.tmp.sql` | Append `ALTER TABLE` for new column |
| `sql/nexora/config/tables/MaintenanceBanner_asCreate.sql` | Add column to reference DDL |
| `app.py:1308–1331` | `_maintenance_parse_payload` — add `announceMinutesBefore` |
| `app.py:1292–1295` | `api_admin_maintenance_list` SELECT — add column |
| `app.py:1346–1351` | `api_admin_maintenance_add` INSERT — add column |
| `app.py:1376–1381` | `api_admin_maintenance_edit` UPDATE — add column |
| `app.py:1422–1456` | `api_maintenance_active` — two-priority query |
| `templates/admin/maintenance.html:52–59` | Table header — add Announce column |
| `templates/admin/maintenance.html:86–96` | Modal form — add number input |
| `templates/js/admin/_maintenanceJS.html` | `makeRow`, colSpan, modal init, payload |
| `templates/_maintenance_banner.html` | Full replacement: polling, countdown, two-mode render |

---

### Task 1: DB migration

**Files:**
- Modify: `environment_transfer_queries.tmp.sql` (append at end)
- Modify: `sql/nexora/config/tables/MaintenanceBanner_asCreate.sql`

- [ ] **Step 1: Append the ALTER TABLE to the transfer queries file**

Open `environment_transfer_queries.tmp.sql` and add at the very end:

```sql

--claudes new sql statement: maintenance announcement lead time column
ALTER TABLE [dbo].[MaintenanceBanner]
    ADD [AnnounceMinutesBefore] INT NULL CONSTRAINT DF_MaintenanceBanner_AnnounceMinutesBefore DEFAULT (0);
GO
```

- [ ] **Step 2: Add column to reference DDL**

In `sql/nexora/config/tables/MaintenanceBanner_asCreate.sql`, add the column inside the `CREATE TABLE` block, after the `[BlockAccess]` line:

```sql
	[AnnounceMinutesBefore] [int] NULL,
```

Then add a DEFAULT constraint after the existing `ALTER TABLE … BlockAccess` line:

```sql
ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ((0)) FOR [AnnounceMinutesBefore]
GO
```

And add a migration comment at the bottom of the file:

```sql
-- If the table already exists, run this instead of recreating:
-- ALTER TABLE [dbo].[MaintenanceBanner] ADD [AnnounceMinutesBefore] [int] NULL CONSTRAINT DF_MaintenanceBanner_AnnounceMinutesBefore DEFAULT (0)
-- GO
```

- [ ] **Step 3: Verify the SQL looks right**

Read both files back and confirm the column appears in the correct place and that the file is syntactically valid.

- [ ] **Step 4: Commit**

```
git add environment_transfer_queries.tmp.sql "sql/nexora/config/tables/MaintenanceBanner_asCreate.sql"
git commit -m "feat: add AnnounceMinutesBefore column to MaintenanceBanner"
```

> Note: run the `ALTER TABLE` from `environment_transfer_queries.tmp.sql` on INT and PROD databases before testing Task 2 onwards.

---

### Task 2: Backend — parse helper + list endpoint

**Files:**
- Modify: `app.py:1308–1331` (`_maintenance_parse_payload`)
- Modify: `app.py:1292–1295` (`api_admin_maintenance_list` SELECT)

- [ ] **Step 1: Update `_maintenance_parse_payload` (app.py ~line 1308)**

Replace the existing function body:

```python
def _maintenance_parse_payload(body):
    title        = (body.get('title') or '').strip()
    message      = (body.get('message') or '').strip()
    start_at     = (body.get('startAt') or '').strip().replace('T', ' ')
    end_at       = (body.get('endAt') or '').strip().replace('T', ' ')
    severity     = (body.get('severity') or 'info').strip().lower()
    active       = bool(body.get('active', True))
    block_access = bool(body.get('blockAccess', False))
    try:
        announce_minutes = max(0, min(1440, int(body.get('announceMinutesBefore') or 0)))
    except (TypeError, ValueError):
        announce_minutes = 0

    if not message:
        return None, ("message is required", 400)
    if not start_at or not end_at:
        return None, ("startAt and endAt are required", 400)
    if severity not in MAINTENANCE_SEVERITIES:
        return None, ("invalid severity", 400)
    return {
        'title': title or None,
        'message': message,
        'start_at': start_at,
        'end_at': end_at,
        'severity': severity,
        'active': 1 if active else 0,
        'block_access': 1 if block_access else 0,
        'announce_minutes': announce_minutes,
    }, None
```

- [ ] **Step 2: Update the SELECT in `api_admin_maintenance_list` (app.py ~line 1292)**

Replace:
```python
        cursor.execute("""
            SELECT ID, Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, CreatedBy, CreatedAt
            FROM MaintenanceBanner
            ORDER BY StartAt DESC, ID DESC
        """)
```
With:
```python
        cursor.execute("""
            SELECT ID, Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, AnnounceMinutesBefore, CreatedBy, CreatedAt
            FROM MaintenanceBanner
            ORDER BY StartAt DESC, ID DESC
        """)
```

- [ ] **Step 3: Verify — call the admin list API**

Start the app (`nx -u`), log in as an admin, then run:

```
curl -s -b cookies.txt http://localhost:5000/api/admin/maintenance | python -m json.tool
```

Confirm each record in `records` now contains `"AnnounceMinutesBefore": 0` (or null for old rows).

- [ ] **Step 4: Commit**

```
git add app.py
git commit -m "feat: parse announceMinutesBefore in maintenance payload, expose in list API"
```

---

### Task 3: Backend — write endpoints (INSERT + UPDATE)

**Files:**
- Modify: `app.py:1346–1351` (`api_admin_maintenance_add` INSERT)
- Modify: `app.py:1376–1381` (`api_admin_maintenance_edit` UPDATE)

- [ ] **Step 1: Update INSERT in `api_admin_maintenance_add` (app.py ~line 1346)**

Replace:
```python
        cursor.execute("""
            INSERT INTO MaintenanceBanner (Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, CreatedBy, CreatedAt)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, [parsed['title'], parsed['message'], parsed['start_at'], parsed['end_at'],
              parsed['severity'], parsed['active'], parsed['block_access'], session.get('userid')])
```
With:
```python
        cursor.execute("""
            INSERT INTO MaintenanceBanner (Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, AnnounceMinutesBefore, CreatedBy, CreatedAt)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, [parsed['title'], parsed['message'], parsed['start_at'], parsed['end_at'],
              parsed['severity'], parsed['active'], parsed['block_access'],
              parsed['announce_minutes'], session.get('userid')])
```

- [ ] **Step 2: Update UPDATE in `api_admin_maintenance_edit` (app.py ~line 1376)**

Replace:
```python
        cursor.execute("""
            UPDATE MaintenanceBanner
               SET Title = ?, Message = ?, StartAt = ?, EndAt = ?, Severity = ?, Active = ?, BlockAccess = ?
             WHERE ID = ?
        """, [parsed['title'], parsed['message'], parsed['start_at'], parsed['end_at'],
              parsed['severity'], parsed['active'], parsed['block_access'], banner_id])
```
With:
```python
        cursor.execute("""
            UPDATE MaintenanceBanner
               SET Title = ?, Message = ?, StartAt = ?, EndAt = ?, Severity = ?,
                   Active = ?, BlockAccess = ?, AnnounceMinutesBefore = ?
             WHERE ID = ?
        """, [parsed['title'], parsed['message'], parsed['start_at'], parsed['end_at'],
              parsed['severity'], parsed['active'], parsed['block_access'],
              parsed['announce_minutes'], banner_id])
```

- [ ] **Step 3: Verify — create a test banner via API**

```
curl -s -X POST http://localhost:5000/api/admin/maintenance \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"message":"Test","startAt":"2026-05-05 22:00","endAt":"2026-05-05 23:00","severity":"info","active":true,"blockAccess":false,"announceMinutesBefore":30}'
```

Expected: `{"success": true, "id": <N>}`

Then fetch the list and confirm `AnnounceMinutesBefore` is `30` for that record.

- [ ] **Step 4: Commit**

```
git add app.py
git commit -m "feat: persist AnnounceMinutesBefore in maintenance INSERT and UPDATE"
```

---

### Task 4: Backend — extend `api_maintenance_active` with two-priority query

**Files:**
- Modify: `app.py:1422–1456` (`api_maintenance_active`)

- [ ] **Step 1: Replace the function body**

Replace the entire `api_maintenance_active` function body (keep the route decorator):

```python
@app.route("/api/maintenance/active", methods=['GET'])
def api_maintenance_active():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        # Priority 1: currently active banner (window has started)
        cursor.execute("""
            SELECT TOP 1 ID, Title, Message, StartAt, EndAt, Severity
            FROM MaintenanceBanner
            WHERE Active = 1
              AND StartAt <= GETDATE()
              AND EndAt   >= GETDATE()
            ORDER BY StartAt DESC, ID DESC
        """)
        row = cursor.fetchone()
        if row:
            rec_id, title, message, start_at, end_at, severity = row
            return jsonify({
                "success": True,
                "banner": {
                    "id":       int(rec_id),
                    "title":    title,
                    "message":  message,
                    "startAt":  _maintenance_iso(start_at),
                    "endAt":    _maintenance_iso(end_at),
                    "severity": severity,
                    "upcoming": False,
                }
            })
        # Priority 2: upcoming banner within its announcement window
        cursor.execute("""
            SELECT TOP 1 ID, Title, Message, StartAt, EndAt, Severity
            FROM MaintenanceBanner
            WHERE Active = 1
              AND StartAt > GETDATE()
              AND AnnounceMinutesBefore > 0
              AND DATEADD(minute, -AnnounceMinutesBefore, StartAt) <= GETDATE()
            ORDER BY StartAt ASC, ID ASC
        """)
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": True, "banner": None})
        rec_id, title, message, start_at, end_at, severity = row
        return jsonify({
            "success": True,
            "banner": {
                "id":       int(rec_id),
                "title":    title,
                "message":  message,
                "startAt":  _maintenance_iso(start_at),
                "endAt":    _maintenance_iso(end_at),
                "severity": severity,
                "upcoming": True,
            }
        })
    except Exception as e:
        app.logger.error(f"Maintenance active error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()
```

- [ ] **Step 2: Verify priority 1 (no regression) — no active window**

```
curl -s http://localhost:5000/api/maintenance/active | python -m json.tool
```

Expected when no banner is active: `{"success": true, "banner": null}`

- [ ] **Step 3: Verify priority 1 (no regression) — live window**

Temporarily update the test banner from Task 3 to have `StartAt` in the past and `EndAt` in the future (via the admin UI or SQL), then:

```
curl -s http://localhost:5000/api/maintenance/active | python -m json.tool
```

Expected: `{"success": true, "banner": {"upcoming": false, ...}}`

- [ ] **Step 4: Verify priority 2 — upcoming window**

Update the test banner to have `StartAt` 25 minutes in the future, `AnnounceMinutesBefore = 30`, then:

```
curl -s http://localhost:5000/api/maintenance/active | python -m json.tool
```

Expected: `{"success": true, "banner": {"upcoming": true, "startAt": "...", ...}}`

- [ ] **Step 5: Verify priority 1 beats priority 2**

Ensure that when a live banner exists, priority 2 is never returned even if another upcoming banner is also in its window. (Have two banners: one live, one upcoming with announcement window active.) Check that `upcoming: false` is returned.

- [ ] **Step 6: Commit**

```
git add app.py
git commit -m "feat: return upcoming announcement banners from /api/maintenance/active"
```

---

### Task 5: Admin HTML — new table column + modal field

**Files:**
- Modify: `templates/admin/maintenance.html:52–59` (table header)
- Modify: `templates/admin/maintenance.html:85–96` (modal form)

- [ ] **Step 1: Add "Announce" column to the table header (line ~52)**

Replace:
```html
                {{ a.table_header([
                    {'label': _('Title')},
                    {'label': _('Window')},
                    {'label': _('Severity'), 'width': '120px'},
                    {'label': _('Block'), 'width': '90px', 'align': 'center'},
                    {'label': _('Active'), 'width': '100px', 'align': 'center'},
                    {'label': _('Actions'), 'align': 'right', 'width': '180px'}
                ]) }}
```
With:
```html
                {{ a.table_header([
                    {'label': _('Title')},
                    {'label': _('Window')},
                    {'label': _('Severity'), 'width': '120px'},
                    {'label': _('Block'), 'width': '90px', 'align': 'center'},
                    {'label': _('Announce'), 'width': '110px', 'align': 'center'},
                    {'label': _('Active'), 'width': '100px', 'align': 'center'},
                    {'label': _('Actions'), 'align': 'right', 'width': '180px'}
                ]) }}
```

- [ ] **Step 2: Add number input to the modal form (line ~85, between Start/End row and Severity/Active row)**

Replace:
```html
                    <div class="grid grid-cols-2 gap-3 items-end">
                        <div>
                            <label for="maintSeverity" class="block mb-1 text-sm font-medium">{{ _("Severity") }}</label>
```
With:
```html
                    <div>
                        <label for="maintAnnounce" class="block mb-1 text-sm font-medium">{{ _("Announce users") }}</label>
                        <div class="flex items-center gap-2">
                            <input type="number" id="maintAnnounce" min="0" max="1440" step="1" value="0"
                                   class="bg-gray-50 border border-gray-300 text-sm rounded-lg p-2.5 w-24 focus:ring-indigo-500 focus:border-indigo-500" />
                            <span class="text-sm text-gray-500">{{ _("minutes before start (0 = no announcement)") }}</span>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-3 items-end">
                        <div>
                            <label for="maintSeverity" class="block mb-1 text-sm font-medium">{{ _("Severity") }}</label>
```

- [ ] **Step 3: Verify the form renders**

Open the admin maintenance page in a browser. Click "Add banner". Confirm the "Announce users … minutes" field appears between the date range and the Severity row. Also confirm the table header has 7 columns.

- [ ] **Step 4: Commit**

```
git add templates/admin/maintenance.html
git commit -m "feat: add Announce column header and modal input to maintenance admin page"
```

---

### Task 6: Admin JS — table row, modal init, payload

**Files:**
- Modify: `templates/js/admin/_maintenanceJS.html`

- [ ] **Step 1: Add the Announce cell to `makeRow`**

Inside `makeRow`, after the `const tdActions = document.createElement('td');` block and before the first `tr.appendChild` call, insert the `tdAnnounce` element declaration:

```javascript
        const tdAnnounce = document.createElement('td');
        tdAnnounce.style.textAlign = 'center';
        const amin = b.AnnounceMinutesBefore;
        if (amin && amin > 0) {
            const pill = document.createElement('span');
            pill.style.cssText = 'font-size:12px;color:#4338ca;font-weight:600;';
            pill.textContent = amin + ' min';
            tdAnnounce.appendChild(pill);
        } else {
            const dash = document.createElement('span');
            dash.style.color = '#94a3b8';
            dash.textContent = '—';
            tdAnnounce.appendChild(dash);
        }
```

Then replace the existing `tr.appendChild` sequence with:
```javascript
        tr.appendChild(tdTitle);
        tr.appendChild(tdWindow);
        tr.appendChild(tdSev);
        tr.appendChild(tdBlock);
        tr.appendChild(tdAnnounce);
        tr.appendChild(tdActive);
        tr.appendChild(tdActions);
```

- [ ] **Step 2: Fix colSpan from 6 to 7**

In `renderTable` (the "No banners found" empty row):
```javascript
            td.colSpan = 7;
```

In `loadBanners` (the spinner row):
```javascript
        td.colSpan = 7;
```

- [ ] **Step 3: Initialise the announce field in `openMaintModal`**

Inside `openMaintModal()`, after the existing resets, add:
```javascript
        document.getElementById('maintAnnounce').value = 0;
```

- [ ] **Step 4: Populate the field in `openEditMaintModal`**

Inside `openEditMaintModal(b)`, after populating `maintBlockAccess`, add:
```javascript
        document.getElementById('maintAnnounce').value = b.AnnounceMinutesBefore || 0;
```

- [ ] **Step 5: Add `announceMinutesBefore` to the POST/PUT payload**

In the `document.getElementById('maintForm').addEventListener('submit', ...)` handler, inside the `payload` object, add:
```javascript
            announceMinutesBefore: Math.max(0, parseInt(document.getElementById('maintAnnounce').value) || 0),
```

Full corrected `payload` object:
```javascript
        const payload = {
            title:                document.getElementById('maintTitle').value.trim(),
            message:              document.getElementById('maintMessage').value.trim(),
            startAt:              document.getElementById('maintStartAt').value.trim(),
            endAt:                document.getElementById('maintEndAt').value.trim(),
            severity:             document.getElementById('maintSeverity').value,
            active:               document.getElementById('maintActive').checked,
            blockAccess:          document.getElementById('maintBlockAccess').checked,
            announceMinutesBefore: Math.max(0, parseInt(document.getElementById('maintAnnounce').value) || 0),
        };
```

- [ ] **Step 6: Verify end-to-end admin flow**

1. Open the admin maintenance page.
2. Click "Add banner", fill in all fields, set Announce = 30, save. Confirm no JS error and the table row shows "30 min" in the Announce column.
3. Click Edit on that row. Confirm the Announce field is pre-filled with 30.
4. Change it to 0, save. Confirm the table shows "—" in the Announce column.

- [ ] **Step 7: Commit**

```
git add "templates/js/admin/_maintenanceJS.html"
git commit -m "feat: announce field in maintenance admin JS — table, modal, payload"
```

---

### Task 7: Front-end announcement banner

**Files:**
- Modify: `templates/_maintenance_banner.html` (full replacement of `<script>` block)

- [ ] **Step 1: Replace the entire `<script>` block**

Keep the `<style>` block and `<div id="maintenance-banner">` unchanged. Replace only the `<script>…</script>` section with:

```html
<script>
(function() {
    const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";
    const SEVERITY_ICON = { info: 'fa-circle-info', warning: 'fa-triangle-exclamation', critical: 'fa-circle-exclamation' };
    const banner = document.getElementById('maintenance-banner');
    if (!banner) return;

    let _countdownInterval = null;
    let _activeBannerKey = null;

    function fmt(iso) {
        if (!iso) return '';
        return iso.replace('T', ' ').substring(0, 16);
    }

    function minutesUntil(isoStr) {
        return Math.max(0, Math.ceil((new Date(isoStr) - Date.now()) / 60000));
    }

    function hide() {
        _activeBannerKey = null;
        if (_countdownInterval) { clearInterval(_countdownInterval); _countdownInterval = null; }
        banner.classList.remove('mb-show');
        document.body.classList.remove('has-maintenance-banner');
        banner.replaceChildren();
    }

    function render(b) {
        const upcoming = !!b.upcoming;
        const dismissKey = upcoming ? ('mb-announced-' + b.id) : ('mb-dismissed-' + b.id);

        if (sessionStorage.getItem(dismissKey) === '1') {
            if (banner.classList.contains('mb-show')) hide();
            return;
        }

        const bannerKey = b.id + ':' + (upcoming ? 'up' : 'live');
        if (_activeBannerKey === bannerKey) return;
        _activeBannerKey = bannerKey;

        if (_countdownInterval) { clearInterval(_countdownInterval); _countdownInterval = null; }

        banner.replaceChildren();
        const hasSidebar = !!document.getElementById('nexora-sidebar');
        banner.className = 'mb-show mb-' + (b.severity || 'info') + (hasSidebar ? ' mb-with-sidebar' : '');

        const ico = document.createElement('i');
        ico.className = 'fas mb-icon ' + (upcoming ? 'fa-clock' : (SEVERITY_ICON[b.severity] || SEVERITY_ICON.info));
        banner.appendChild(ico);

        const body = document.createElement('div');
        body.className = 'mb-body';

        if (upcoming) {
            const prefix = document.createElement('span');
            prefix.className = 'mb-title';
            prefix.appendChild(document.createTextNode('Maintenance in '));
            const countSpan = document.createElement('span');
            countSpan.id = 'mb-countdown';
            countSpan.textContent = String(minutesUntil(b.startAt));
            prefix.appendChild(countSpan);
            prefix.appendChild(document.createTextNode(' min: '));
            body.appendChild(prefix);

            _countdownInterval = setInterval(function() {
                const el = document.getElementById('mb-countdown');
                if (el) el.textContent = String(minutesUntil(b.startAt));
                if (minutesUntil(b.startAt) === 0) {
                    clearInterval(_countdownInterval);
                    _countdownInterval = null;
                }
            }, 60000);
        } else if (b.title) {
            const t = document.createElement('span');
            t.className = 'mb-title';
            t.textContent = b.title;
            body.appendChild(t);
        }

        body.appendChild(document.createTextNode(b.message || ''));
        if (b.startAt && b.endAt) {
            const win = document.createElement('span');
            win.className = 'mb-window';
            win.textContent = '(' + fmt(b.startAt) + ' – ' + fmt(b.endAt) + ')';
            body.appendChild(win);
        }
        banner.appendChild(body);

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'mb-dismiss';
        btn.setAttribute('aria-label', 'Dismiss');
        const x = document.createElement('i');
        x.className = 'fas fa-xmark';
        btn.appendChild(x);
        btn.addEventListener('click', function() {
            sessionStorage.setItem(dismissKey, '1');
            hide();
        });
        banner.appendChild(btn);

        document.body.classList.add('has-maintenance-banner');
    }

    function poll() {
        fetch(API_PREFIX + 'api/maintenance/active')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data && data.success && data.banner) render(data.banner);
                else hide();
            })
            .catch(function() {});
    }

    poll();
    setInterval(poll, 60000);
})();
</script>
```

- [ ] **Step 2: Verify — upcoming banner appears**

1. Create a banner with `StartAt` = 20 minutes from now, `AnnounceMinutesBefore` = 30, `Active` = true.
2. Navigate to any page that includes `_maintenance_banner.html` (any in-app page).
3. Confirm the banner shows with a clock icon and "Maintenance in ~20 min: [message]".
4. Confirm the window time range appears in the banner.

- [ ] **Step 3: Verify — countdown updates (accelerated test)**

Open the browser console and run:
```javascript
// Override minutesUntil to fast-forward
```
Or simply wait ~60 s and check that the countdown number decrements by 1. (Alternatively, set `StartAt` to 2 minutes from now and verify the counter shows 2 then 1 then 0 at 60 s intervals.)

- [ ] **Step 4: Verify — dismiss behaviour**

1. With the upcoming banner showing, click ✕.
2. Confirm the banner disappears and `sessionStorage.getItem('mb-announced-<id>')` = `'1'`.
3. Wait for the next poll (≤ 60 s) — banner should NOT reappear.
4. Once `StartAt` passes, refresh the page. The live banner should appear (different dismiss key `mb-dismissed-<id>`).

- [ ] **Step 5: Verify — no regression on live banner**

1. Update the test banner so `StartAt` is in the past and `EndAt` is in the future.
2. Confirm the banner shows with the severity icon (not clock), shows title + message, and is dismissible with key `mb-dismissed-<id>`.

- [ ] **Step 6: Verify — no banner when outside any window**

Set both `StartAt` and `EndAt` in the future but with `AnnounceMinutesBefore = 0`. Confirm no banner appears.

- [ ] **Step 7: Commit**

```
git add templates/_maintenance_banner.html
git commit -m "feat: maintenance announcement banner with countdown and polling"
```

---

## Done

All tasks complete. The feature delivers:
- Per-banner `AnnounceMinutesBefore` field, managed in the admin UI.
- `/api/maintenance/active` returns upcoming announcements with `"upcoming": true` when within the configured window.
- The in-app banner automatically transitions from upcoming (clock + countdown) to live (severity icon) without a page reload, via 60-second polling.
- Dismissing the pre-announcement uses a separate session key so the live banner still shows when the window opens.
