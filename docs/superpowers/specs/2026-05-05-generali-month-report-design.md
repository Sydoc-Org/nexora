# Generali Month Report — Design Spec

**Date:** 2026-05-05

## Overview

Add a "Month Report" button to five generali data-entry pages. Each button links to a dedicated per-section month report page showing an aggregated summary of that section's data for the selected month. Users can navigate to previous and future months via prev/next controls.

## Scope

**Pages that get the button (and their own month report route):**
- Generali Reporting
- Generali Base Services
- Generali Additional Services
- Generali Project Management
- Generali PDQM

**Excluded:** generali-dashboard, generali_documents (the list page), generali_importstatus.

## Routes

Five new Flask routes, each placed near their parent route in `app.py`:

| Route | Function name | Permission |
|---|---|---|
| `GET /generali/reporting/monthreport` | `generali_reporting_monthreport` | `generali.reporting.view` |
| `GET /generali/baseservices/monthreport` | `generali_baseservices_monthreport` | `generali.baseservices.view` |
| `GET /generali/additionalservices/monthreport` | `generali_additionalservices_monthreport` | `generali.additionalservices.view` |
| `GET /generali/projectmanagement/monthreport` | `generali_projectmanagement_monthreport` | `generali.projectmanagement.view` |
| `GET /generali/pdqm/monthreport` | `generali_pdqm_monthreport` | `generali.pdqm.view` |

Each route:
1. Reads `?year=YYYY&month=M` query params (defaults to `date.today().year` / `date.today().month`)
2. Clamps `month` to 1–12, adjusts year accordingly
3. Computes first/last day of the month as date range
4. Queries the DB with a `GROUP BY` for that month's data
5. Computes `prev_year`/`prev_month` and `next_year`/`next_month` for nav links
6. Renders `generali_monthreport.html` with a `section` variable and aggregated data

The same org/user permission scoping used in the existing list routes applies here (admin sees all, regular user sees only their own records).

## Data aggregation per section

### Reporting
- Source table: `[Generali].[dbo].[Reporting]`
- `GROUP BY Category`
- Per row: `category`, `total` (count), `on_time_count`, `late_count`, `pct_on_time`
- Summary cards: total entries, overall on-time count, overall late count, overall % on-time

### Base Services
- Source table: `[Generali].[dbo].[BaseServices]`
- `GROUP BY Category`
- Per row: `category`, `entries` (count), `total_hours` (sum of EffortInHours)
- Summary cards: total entries, total hours

### Additional Services
- Source table: `[Generali].[dbo].[Attendance]`
- `GROUP BY ParentCategory`
- Per row: `category`, `entries`, `total_hours`
- Summary cards: total entries, total hours

### Project Management
- Source table: `[Generali].[dbo].[ProjectManagement]`
- No GROUP BY (no category column)
- Summary cards only: total entries, total hours
- No breakdown table rendered

### PDQM
- Source table: `[Generali].[dbo].[PDQMReport]`
- `GROUP BY ParentCategory`
- Per row: `category`, `entries`, `total_quantity` (sum of Quantity)
- Summary cards: total entries, total quantity

## Template

**File:** `templates/generali_monthreport.html`
**JS partial:** `templates/js/_generaliMonthReportJS.html` (minimal — only for any interactive elements)

Template variables passed from every route:
- `section` — one of `reporting`, `baseservices`, `additionalservices`, `projectmanagement`, `pdqm`
- `section_title` — human-readable section name (e.g. "Generali Reporting")
- `back_url` — url_for() of the parent page
- `year`, `month` — integers for the displayed month
- `prev_year`, `prev_month`, `next_year`, `next_month` — for nav links
- `is_current_month` — bool, used to disable the "next" arrow when on current month
- `summary` — dict of top-level stats (keys vary by section)
- `rows` — list of dicts for the breakdown table (empty list for Project Management)

### Layout

```
[Back button]  "Month Report — May 2026"
               ← April 2026 | May 2026 | June 2026 →  (next disabled if current month)

[Stat card 1] [Stat card 2] [Stat card 3] [Stat card 4]

Breakdown table (hidden for projectmanagement)
```

Styling follows existing generali page conventions: Tailwind CSS, Inter font, indigo accent colour, `rounded-2xl` cards, `bg-white` table with `border-gray-100` border.

## Button placement

In each of the 5 source page templates, add one `<a>` element to the existing header button row. The `url_for` target per template:

| Template | `url_for` target |
|---|---|
| `generali_reporting.html` | `generali_reporting_monthreport` |
| `generali_baseservices.html` | `generali_baseservices_monthreport` |
| `generali_additionalservices.html` | `generali_additionalservices_monthreport` |
| `generali_projectmanagement.html` | `generali_projectmanagement_monthreport` |
| `generali_pdqm.html` | `generali_pdqm_monthreport` |

```html
<a href="{{ url_for('generali_<section>_monthreport') }}"
   class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
  <i class="fas fa-calendar-alt"></i><span class="hidden sm:inline">{{ _("Month Report") }}</span>
</a>
```

No `year`/`month` params in the link — the route defaults to the current month.

## Permissions & security

- Month report routes reuse the same `@require_permission` code as their parent list route.
- The same org-scoping logic applies: users without `edit.organizational` or `edit.transorganizational` permission see only their own records.
- No new permission codes are needed.

## Out of scope

- Export (Excel) on the month report page
- Edit/delete actions from the month report
- Import Status month report
