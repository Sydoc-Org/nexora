# Maintenance Announcement Feature — Design Spec

**Date:** 2026-05-05  
**Branch:** 2.5.56  
**Author:** benstreich  

## Problem

Users are locked out without warning when a maintenance window activates. The system should let admins schedule a pre-announcement banner that appears N minutes before the lockdown starts.

---

## Design

### 1. Database

Add one column to `MaintenanceBanner`:

```sql
ALTER TABLE MaintenanceBanner
    ADD AnnounceMinutesBefore INT NULL DEFAULT 0;
```

- `NULL` or `0` → no pre-announcement (backwards compatible with existing rows).
- Any positive integer (1–1440) → banner becomes visible that many minutes before `StartAt`.
- SQL goes into `environment_transfer_queries.tmp.sql` and the reference DDL under `sql/`.

---

### 2. Backend

**`_maintenance_parse_payload(body)`**  
Add extraction of `announceMinutesBefore`:
- Read `body.get('announceMinutesBefore', 0)`, cast to `int`, clamp to `[0, 1440]`.
- Include in the returned dict as `announce_minutes_before`.

**`INSERT` / `UPDATE` in `api_admin_maintenance_add` and `api_admin_maintenance_edit`**  
Pass `announce_minutes_before` as a new bind parameter for the `AnnounceMinutesBefore` column.

**`api_admin_maintenance_list` (`GET /api/admin/maintenance`)**  
Include `AnnounceMinutesBefore` in the `SELECT` so the admin table can show it.

**`api_maintenance_active` (`GET /api/maintenance/active`)**  
Extend with a two-priority query:

```
Priority 1 (unchanged):
  Active = 1 AND StartAt <= GETDATE() AND EndAt >= GETDATE()
  → returns the live blocking/info banner
  → response: {"success": true, "banner": {..., "upcoming": false}}

Priority 2 (new — only runs if priority 1 returns nothing):
  Active = 1
  AND StartAt > GETDATE()
  AND AnnounceMinutesBefore > 0
  AND DATEADD(minute, -AnnounceMinutesBefore, StartAt) <= GETDATE()
  ORDER BY StartAt ASC, ID ASC
  → returns the nearest upcoming banner within its announcement window
  → response: {"success": true, "banner": {..., "upcoming": true}}
```

If neither query finds a row: `{"success": true, "banner": null}` (unchanged).

**Important:** the `_MAINTENANCE_BLOCK_CACHE` TTL cache is **not** involved here. That cache is only for the lockout path (`enforce_maintenance_lockout`). Upcoming announcements must not influence lockout decisions.

---

### 3. Admin UI — `templates/admin/maintenance.html` & `templates/js/admin/_maintenanceJS.html`

**Modal form** — add below the Start/End date row:

```
[ Announce ]  [____] minutes before start
              (number input, min=0, max=1440, step=1, default=0)
```

Label: "Announce users X min before start". When `0`, the field means "no announcement".

**Table** — add a new column header "Announce" with values like "30 min prior" or "—". Column width ~110 px.

**`makeRow(b)`** — render the new column from `b.AnnounceMinutesBefore`.

**`openEditMaintModal(b)`** — populate the new field from `b.AnnounceMinutesBefore`.

**Payload** — include `announceMinutesBefore: parseInt(...)` in POST/PUT JSON.

---

### 4. Front-end Banner — `templates/_maintenance_banner.html`

**Polling interval**  
Replace the one-shot `fetch` on load with a polling function that fires immediately on page load and then repeats every 60 seconds via `setInterval`. The interval is set up unconditionally; when no banner is active/upcoming the fetch returns `null` and the banner stays hidden. This also handles the automatic upgrade from "upcoming" to "live" without a page reload.

**`render(b)` — two modes**

| Field | `upcoming: false` (live) | `upcoming: true` (pre-announcement) |
|---|---|---|
| Dismiss key | `mb-dismissed-{id}` | `mb-announced-{id}` |
| CSS class | `mb-{severity}` (unchanged) | `mb-{severity}` (same) |
| Icon | severity icon (unchanged) | clock icon (`fa-clock`) |
| Message prefix | none (unchanged) | "Maintenance in X min: " |
| Countdown timer | — | `setInterval` every 60 s updates the minute count in-place; clears when `startAt` is past |

Using separate dismiss keys means dismissing the pre-announcement does **not** suppress the live banner when the window opens.

**Countdown format**  
`Math.max(0, Math.ceil((new Date(b.startAt) - Date.now()) / 60000))` minutes. When the countdown reaches 0, the interval self-clears and the next poll cycle will return the live banner.

---

### 5. Out of scope

- Push notifications / email alerts.
- Per-user opt-out of announcements.
- Announcement for banners with `BlockAccess = 0` behaves identically to `BlockAccess = 1` — the feature is announcement-only, lockout logic is untouched.

---

### 6. File changes summary

| File | Change |
|---|---|
| `environment_transfer_queries.tmp.sql` | `ALTER TABLE MaintenanceBanner ADD AnnounceMinutesBefore` |
| `sql/…` (reference DDL) | Same DDL for reference |
| `app.py` | `_maintenance_parse_payload`, `api_admin_maintenance_add/edit/list`, `api_maintenance_active` |
| `templates/admin/maintenance.html` | New "Announce" column header |
| `templates/js/admin/_maintenanceJS.html` | New field in modal + table row + payload |
| `templates/_maintenance_banner.html` | Polling loop, countdown, two-mode `render()` |
