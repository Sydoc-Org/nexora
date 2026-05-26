# Generali Month Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Month Report" button to five generali data-entry pages; each button links to a dedicated server-rendered summary page for the selected month with month navigation.

**Architecture:** Five new Flask routes (one per section) perform a GROUP BY SQL query for the given month and render a single shared Jinja template (`generali_monthreport.html`). Month navigation is implemented via `?year=YYYY&month=M` query params. A "Month Report" `<a>` button is added to the header of each source page.

**Tech Stack:** Flask, Jinja2, Tailwind CSS (browser CDN), Font Awesome, SQL Server via pyodbc (`engineGeneraliDB`), Playwright via `nx` CLI for browser testing.

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Create | `templates/generali_monthreport.html` | Shared template for all 5 month report pages |
| Create | `templates/js/_generaliMonthReportJS.html` | Minimal JS partial (required by convention) |
| Modify | `app.py:7244` | Insert Reporting month report route after parent route |
| Modify | `app.py:7575` | Insert Additional Services month report route |
| Modify | `app.py:7989` | Insert Base Services month report route |
| Modify | `app.py:8357` | Insert Project Management month report route |
| Modify | `app.py:8717` | Insert PDQM month report route |
| Modify | `templates/generali_reporting.html` | Add Month Report button |
| Modify | `templates/generali_additionalservices.html` | Add Month Report button |
| Modify | `templates/generali_baseservices.html` | Add Month Report button |
| Modify | `templates/generali_projectmanagement.html` | Add Month Report button |
| Modify | `templates/generali_pdqm.html` | Add Month Report button |

---

## Task 1: Create the shared template

**Files:**
- Create: `templates/generali_monthreport.html`
- Create: `templates/js/_generaliMonthReportJS.html`

- [ ] **Step 1: Create `templates/js/_generaliMonthReportJS.html`**

```html
{# No dynamic JS needed — page is fully server-rendered #}
```

- [ ] **Step 2: Create `templates/generali_monthreport.html`**

```html
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ _("Month Report") }} — {{ section_title }} - nexora</title>
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
  <link rel="stylesheet" href="{{ url_for('static',filename='css/workitems_overview.css') }}">
  <link rel="icon" type="image/x-icon" href="{{ url_for('static',filename='images/favicon.ico') }}">
</head>
<body class="bg-gray-50 text-gray-800">
  {% set active_page = 'generali_' ~ section %}
  {% include '_header.html' %}

  <main class="container mx-auto px-3 py-4 sm:p-6">

    <!-- Page Header -->
    <div class="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h2 class="text-2xl sm:text-3xl font-bold text-gray-900 mb-1">{{ _("Month Report") }} — {{ section_title }}</h2>
        <p class="text-gray-500 font-medium">{{ month_label }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        <a href="{{ back_url }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-arrow-left"></i><span class="hidden sm:inline">{{ _("Back") }}</span>
        </a>
      </div>
    </div>

    <!-- Month Navigation -->
    <div class="flex items-center justify-center gap-4 mb-6">
      <a href="?year={{ prev_year }}&month={{ prev_month }}"
         class="inline-flex items-center bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
        <i class="fas fa-chevron-left"></i>
      </a>
      <span class="text-lg font-bold text-gray-900 min-w-36 text-center">{{ month_label }}</span>
      {% if is_current_month %}
      <span class="inline-flex items-center bg-gray-50 text-gray-300 px-4 py-2.5 rounded-xl text-sm font-semibold border border-gray-100 cursor-not-allowed select-none">
        <i class="fas fa-chevron-right"></i>
      </span>
      {% else %}
      <a href="?year={{ next_year }}&month={{ next_month }}"
         class="inline-flex items-center bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
        <i class="fas fa-chevron-right"></i>
      </a>
      {% endif %}
    </div>

    <!-- Stat Cards -->
    <div class="grid grid-cols-2 {% if section == 'reporting' %}lg:grid-cols-4{% else %}lg:grid-cols-2{% endif %} gap-4 mb-6">

      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{{ _("Total Entries") }}</p>
        <p class="text-3xl font-bold text-gray-900">{{ summary.total_entries }}</p>
      </div>

      {% if section == 'reporting' %}
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{{ _("On Time") }}</p>
        <p class="text-3xl font-bold text-emerald-600">{{ summary.on_time }}</p>
      </div>
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{{ _("Late") }}</p>
        <p class="text-3xl font-bold text-red-500">{{ summary.late }}</p>
      </div>
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{{ _("On-Time Rate") }}</p>
        <p class="text-3xl font-bold text-indigo-600">{{ summary.pct_on_time }}%</p>
      </div>

      {% elif section == 'pdqm' %}
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{{ _("Total Quantity") }}</p>
        <p class="text-3xl font-bold text-indigo-600">{{ summary.total_quantity }}</p>
      </div>

      {% else %}
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{{ _("Total Hours") }}</p>
        <p class="text-3xl font-bold text-indigo-600">{{ summary.total_hours }}</p>
      </div>
      {% endif %}

    </div>

    <!-- Breakdown Table (not shown for Project Management) -->
    {% if section != 'projectmanagement' %}
      {% if rows %}
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-gray-50 border-b border-gray-200">
              <tr>
                <th class="px-6 py-4 text-left">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Category") }}</span>
                </th>
                <th class="px-6 py-4 text-center">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Entries") }}</span>
                </th>
                {% if section == 'reporting' %}
                <th class="px-6 py-4 text-center">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("On Time") }}</span>
                </th>
                <th class="px-6 py-4 text-center">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Late") }}</span>
                </th>
                <th class="px-6 py-4 text-center">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("% On Time") }}</span>
                </th>
                {% elif section == 'pdqm' %}
                <th class="px-6 py-4 text-center">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Total Quantity") }}</span>
                </th>
                {% else %}
                <th class="px-6 py-4 text-center">
                  <span class="text-xs font-semibold text-gray-600 uppercase tracking-wider">{{ _("Total Hours") }}</span>
                </th>
                {% endif %}
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-100">
              {% for row in rows %}
              <tr class="hover:bg-gray-50 transition">
                <td class="px-6 py-4 text-sm font-medium text-gray-900">{{ row.category }}</td>
                {% if section == 'reporting' %}
                <td class="px-6 py-4 text-center text-sm text-gray-700">{{ row.total }}</td>
                <td class="px-6 py-4 text-center text-sm font-semibold text-emerald-600">{{ row.on_time }}</td>
                <td class="px-6 py-4 text-center text-sm font-semibold text-red-500">{{ row.late }}</td>
                <td class="px-6 py-4 text-center text-sm font-bold text-indigo-600">{{ row.pct }}%</td>
                {% elif section == 'pdqm' %}
                <td class="px-6 py-4 text-center text-sm text-gray-700">{{ row.entries }}</td>
                <td class="px-6 py-4 text-center text-sm font-bold text-indigo-600">{{ row.total_quantity }}</td>
                {% else %}
                <td class="px-6 py-4 text-center text-sm text-gray-700">{{ row.entries }}</td>
                <td class="px-6 py-4 text-center text-sm font-bold text-indigo-600">{{ row.total_hours }}</td>
                {% endif %}
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
      {% else %}
      <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-12 text-center">
        <i class="fas fa-calendar-xmark text-4xl text-gray-300 mb-3"></i>
        <p class="text-gray-400 font-medium">{{ _("No data for this month.") }}</p>
      </div>
      {% endif %}
    {% endif %}

  </main>

  {% include '_small_footer.html' %}
  {% include 'js/_generaliMonthReportJS.html' %}
</body>
</html>
```

- [ ] **Step 3: Commit**

```
git add templates/generali_monthreport.html templates/js/_generaliMonthReportJS.html
git commit -m "feat: add shared generali month report template"
```

---

## Task 2: Reporting month report route + button

**Files:**
- Modify: `app.py` — insert after line 7244 (after the `generali_reporting` function)
- Modify: `templates/generali_reporting.html`

- [ ] **Step 1: Insert route into `app.py` after the blank line at 7245**

Find this block in `app.py` (around line 7244–7246):
```python
    except Exception as e:
        app.logger.error(f"Error loading Generali Reporting: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/reporting/organizations", methods=["GET"])
```

Insert the new route in the blank lines between (after the `500` return, before `@app.route("/api/generali/reporting/organizations"`):

```python
@app.route("/generali/reporting/monthreport")
@require_permission('generali.reporting.view')
def generali_reporting_monthreport():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        today = date.today()
        year  = int(request.args.get('year',  today.year))
        month = int(request.args.get('month', today.month))
        month = max(1, min(12, month))

        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year  = year if month < 12 else year + 1
        is_current_month = (year == today.year and month == today.month)
        month_label = first_day.strftime('%B %Y')

        CATEGORY_LABELS = {
            'export_post':            'KPI 1: Delivery physical post',
            'export_post_scan':       'KPI 2: Delivery physical post with scanning',
            'provision_archive':      'KPI 3: Provision of Archival Records',
            'stray_document_digital': 'KPI 12: Stray document (digital)',
            'stray_document_physical':'KPI 13: Stray document (physical)',
        }

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category,
                   COUNT(*) AS total,
                   SUM(CAST(ontime AS INT)) AS on_time_count
            FROM [dbo].[reportingiss]
            WHERE ReportForDate >= ? AND ReportForDate <= ?
            GROUP BY category
            ORDER BY category
        """, [str(first_day), str(last_day)])
        rows_raw = cursor.fetchall()
        cursor.close()
        conn.close()

        rows = [{
            'category': CATEGORY_LABELS.get(r[0], r[0]),
            'total':    r[1],
            'on_time':  r[2] or 0,
            'late':     r[1] - (r[2] or 0),
            'pct':      round((r[2] or 0) / r[1] * 100, 1) if r[1] else 0.0,
        } for r in rows_raw]

        total_on_time = sum(r['on_time'] for r in rows)
        total_entries = sum(r['total']   for r in rows)
        summary = {
            'total_entries': total_entries,
            'on_time':       total_on_time,
            'late':          total_entries - total_on_time,
            'pct_on_time':   round(total_on_time / total_entries * 100, 1) if total_entries else 0.0,
        }

        return render_template('generali_monthreport.html',
            logged_in_user=session.get('username'),
            pageV=pageVisability(),
            section='reporting',
            section_title='Generali Reporting',
            back_url=url_for('generali_reporting'),
            year=year, month=month, month_label=month_label,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            is_current_month=is_current_month,
            summary=summary, rows=rows)
    except Exception as e:
        app.logger.error(f"Error loading Generali Reporting Month Report: {e}")
        return render_template('handlers/500.html'), 500

```

- [ ] **Step 2: Add "Month Report" button to `templates/generali_reporting.html`**

Find this block in `generali_reporting.html` (the existing "Dashboard" anchor around line 43):
```html
        <a href="{{ url_for('generali_evaluation') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-chart-line"></i><span class="hidden sm:inline">{{ _("Dashboard") }}</span>
        </a>
```

Add the Month Report button **before** that anchor:
```html
        <a href="{{ url_for('generali_reporting_monthreport') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-calendar-alt"></i><span class="hidden sm:inline">{{ _("Month Report") }}</span>
        </a>
        <a href="{{ url_for('generali_evaluation') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-chart-line"></i><span class="hidden sm:inline">{{ _("Dashboard") }}</span>
        </a>
```

- [ ] **Step 3: Commit**

```
git add app.py templates/generali_reporting.html
git commit -m "feat: add month report for generali reporting"
```

---

## Task 3: Additional Services month report route + button

**Files:**
- Modify: `app.py` — insert after line 7575 (after `generali_additionalServices`)
- Modify: `templates/generali_additionalservices.html`

- [ ] **Step 1: Insert route into `app.py` after line 7575**

Find this block (around line 7573–7577):
```python
    except Exception as e:
        app.logger.error(f"Error loading Generali Attendance: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/attendance/categories", methods=["GET"])
```

Insert in the blank lines:

```python
@app.route("/generali/additionalServices/monthreport")
@require_permission('generali.additionalservices.view')
def generali_additionalservices_monthreport():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        today = date.today()
        year  = int(request.args.get('year',  today.year))
        month = int(request.args.get('month', today.month))
        month = max(1, min(12, month))

        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year  = year if month < 12 else year + 1
        is_current_month = (year == today.year and month == today.month)
        month_label = first_day.strftime('%B %Y')

        where_clauses = ["ForDate >= ?", "ForDate <= ?"]
        params = [str(first_day), str(last_day)]
        if not has_permission('generali.attendance.edit.organizational') and \
           not has_permission('generali.attendance.edit.transorganizational'):
            where_clauses.append("UserID = ?")
            params.append(session.get('userid'))
        where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT ParentCategory,
                   COUNT(*) AS entries,
                   ISNULL(SUM(EffortInHours), 0) AS total_hours
            FROM [Generali].[dbo].[Attendance]
            {where_sql}
            GROUP BY ParentCategory
            ORDER BY ParentCategory
        """, params)
        rows_raw = cursor.fetchall()
        cursor.close()
        conn.close()

        rows = [{
            'category':    r[0] or '—',
            'entries':     r[1],
            'total_hours': round(float(r[2] or 0), 2),
        } for r in rows_raw]

        summary = {
            'total_entries': sum(r['entries']     for r in rows),
            'total_hours':   round(sum(r['total_hours'] for r in rows), 2),
        }

        return render_template('generali_monthreport.html',
            logged_in_user=session.get('username'),
            pageV=pageVisability(),
            section='additionalservices',
            section_title='Generali Additional Services',
            back_url=url_for('generali_additionalServices'),
            year=year, month=month, month_label=month_label,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            is_current_month=is_current_month,
            summary=summary, rows=rows)
    except Exception as e:
        app.logger.error(f"Error loading Generali Additional Services Month Report: {e}")
        return render_template('handlers/500.html'), 500

```

- [ ] **Step 2: Add button to `templates/generali_additionalservices.html`**

Find the existing "Reporting" anchor button:
```html
        <a href="{{ url_for('generali_reporting') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-clipboard-list"></i><span class="hidden sm:inline">{{ _("Reporting") }}</span>
        </a>
```

Add the Month Report button **before** it:
```html
        <a href="{{ url_for('generali_additionalservices_monthreport') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-calendar-alt"></i><span class="hidden sm:inline">{{ _("Month Report") }}</span>
        </a>
        <a href="{{ url_for('generali_reporting') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-clipboard-list"></i><span class="hidden sm:inline">{{ _("Reporting") }}</span>
        </a>
```

- [ ] **Step 3: Commit**

```
git add app.py templates/generali_additionalservices.html
git commit -m "feat: add month report for generali additional services"
```

---

## Task 4: Base Services month report route + button

**Files:**
- Modify: `app.py` — insert after line 7989 (after `generali_baseServices`)
- Modify: `templates/generali_baseservices.html`

- [ ] **Step 1: Insert route into `app.py` after line 7989**

Find this block (around line 7987–7991):
```python
    except Exception as e:
        app.logger.error(f"Error loading Generali Base Services: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/baseservices/orgUsers", methods=["GET"])
```

Insert in the blank lines:

```python
@app.route("/generali/baseServices/monthreport")
@require_permission('generali.baseservices.view')
def generali_baseservices_monthreport():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        today = date.today()
        year  = int(request.args.get('year',  today.year))
        month = int(request.args.get('month', today.month))
        month = max(1, min(12, month))

        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year  = year if month < 12 else year + 1
        is_current_month = (year == today.year and month == today.month)
        month_label = first_day.strftime('%B %Y')

        where_clauses = ["ForDate >= ?", "ForDate <= ?"]
        params = [str(first_day), str(last_day)]
        if not has_permission('generali.baseservices.edit.organizational') and \
           not has_permission('generali.baseservices.edit.transorganizational'):
            where_clauses.append("UserID = ?")
            params.append(session.get('userid'))
        where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT Category,
                   COUNT(*) AS entries,
                   ISNULL(SUM(EffortInHours), 0) AS total_hours
            FROM [Generali].[dbo].[BaseServices]
            {where_sql}
            GROUP BY Category
            ORDER BY Category
        """, params)
        rows_raw = cursor.fetchall()
        cursor.close()
        conn.close()

        rows = [{
            'category':    r[0] or '—',
            'entries':     r[1],
            'total_hours': round(float(r[2] or 0), 2),
        } for r in rows_raw]

        summary = {
            'total_entries': sum(r['entries']     for r in rows),
            'total_hours':   round(sum(r['total_hours'] for r in rows), 2),
        }

        return render_template('generali_monthreport.html',
            logged_in_user=session.get('username'),
            pageV=pageVisability(),
            section='baseservices',
            section_title='Generali Base Services',
            back_url=url_for('generali_baseServices'),
            year=year, month=month, month_label=month_label,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            is_current_month=is_current_month,
            summary=summary, rows=rows)
    except Exception as e:
        app.logger.error(f"Error loading Generali Base Services Month Report: {e}")
        return render_template('handlers/500.html'), 500

```

- [ ] **Step 2: Add button to `templates/generali_baseservices.html`**

Find the existing "Reporting" anchor:
```html
        <a href="{{ url_for('generali_reporting') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-clipboard-list"></i><span class="hidden sm:inline">{{ _("Reporting") }}</span>
        </a>
```

Add the Month Report button **before** it:
```html
        <a href="{{ url_for('generali_baseservices_monthreport') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-calendar-alt"></i><span class="hidden sm:inline">{{ _("Month Report") }}</span>
        </a>
        <a href="{{ url_for('generali_reporting') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-clipboard-list"></i><span class="hidden sm:inline">{{ _("Reporting") }}</span>
        </a>
```

- [ ] **Step 3: Commit**

```
git add app.py templates/generali_baseservices.html
git commit -m "feat: add month report for generali base services"
```

---

## Task 5: Project Management month report route + button

**Files:**
- Modify: `app.py` — insert after line 8357 (after `generali_projectManagement`)
- Modify: `templates/generali_projectmanagement.html`

- [ ] **Step 1: Insert route into `app.py` after line 8357**

Find this block (around line 8355–8359):
```python
    except Exception as e:
        app.logger.error(f"Error loading Generali Project Management: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/projectmanagement/orgUsers", methods=["GET"])
```

Insert in the blank lines:

```python
@app.route("/generali/projectManagement/monthreport")
@require_permission('generali.projectmanagement.view')
def generali_projectmanagement_monthreport():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        today = date.today()
        year  = int(request.args.get('year',  today.year))
        month = int(request.args.get('month', today.month))
        month = max(1, min(12, month))

        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year  = year if month < 12 else year + 1
        is_current_month = (year == today.year and month == today.month)
        month_label = first_day.strftime('%B %Y')

        where_clauses = ["ForDate >= ?", "ForDate <= ?"]
        params = [str(first_day), str(last_day)]
        if not has_permission('generali.projectmanagement.edit.organizational') and \
           not has_permission('generali.projectmanagement.edit.transorganizational'):
            where_clauses.append("UserID = ?")
            params.append(session.get('userid'))
        where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT COUNT(*) AS entries,
                   ISNULL(SUM(EffortInHours), 0) AS total_hours
            FROM [Generali].[dbo].[ProjectManagement]
            {where_sql}
        """, params)
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        summary = {
            'total_entries': row[0] or 0,
            'total_hours':   round(float(row[1] or 0), 2),
        }

        return render_template('generali_monthreport.html',
            logged_in_user=session.get('username'),
            pageV=pageVisability(),
            section='projectmanagement',
            section_title='Generali Project Management',
            back_url=url_for('generali_projectManagement'),
            year=year, month=month, month_label=month_label,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            is_current_month=is_current_month,
            summary=summary, rows=[])
    except Exception as e:
        app.logger.error(f"Error loading Generali Project Management Month Report: {e}")
        return render_template('handlers/500.html'), 500

```

- [ ] **Step 2: Add button to `templates/generali_projectmanagement.html`**

Find the existing "Reporting" anchor:
```html
        <a href="{{ url_for('generali_reporting') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-clipboard-list"></i><span class="hidden sm:inline">{{ _("Reporting") }}</span>
        </a>
```

Add the Month Report button **before** it:
```html
        <a href="{{ url_for('generali_projectmanagement_monthreport') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-calendar-alt"></i><span class="hidden sm:inline">{{ _("Month Report") }}</span>
        </a>
        <a href="{{ url_for('generali_reporting') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-clipboard-list"></i><span class="hidden sm:inline">{{ _("Reporting") }}</span>
        </a>
```

- [ ] **Step 3: Commit**

```
git add app.py templates/generali_projectmanagement.html
git commit -m "feat: add month report for generali project management"
```

---

## Task 6: PDQM month report route + button

**Files:**
- Modify: `app.py` — insert after line 8717 (after `generali_pdqm`)
- Modify: `templates/generali_pdqm.html`

- [ ] **Step 1: Insert route into `app.py` after line 8717**

Find this block (around line 8715–8719):
```python
    except Exception as e:
        app.logger.error(f"Error loading Generali PDQM: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/pdqm/orgUsers", methods=["GET"])
```

Insert in the blank lines:

```python
@app.route("/generali/pdqm/monthreport")
@require_permission('generali.pdqm.view')
def generali_pdqm_monthreport():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        today = date.today()
        year  = int(request.args.get('year',  today.year))
        month = int(request.args.get('month', today.month))
        month = max(1, min(12, month))

        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year  = year if month < 12 else year + 1
        is_current_month = (year == today.year and month == today.month)
        month_label = first_day.strftime('%B %Y')

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ParentCategory,
                   COUNT(*) AS entries,
                   ISNULL(SUM(Quantity), 0) AS total_quantity
            FROM [Generali].[dbo].[PDQMReport]
            WHERE ForDate >= ? AND ForDate <= ?
            GROUP BY ParentCategory
            ORDER BY ParentCategory
        """, [str(first_day), str(last_day)])
        rows_raw = cursor.fetchall()
        cursor.close()
        conn.close()

        rows = [{
            'category':       r[0] or '—',
            'entries':        r[1],
            'total_quantity': int(r[2] or 0),
        } for r in rows_raw]

        summary = {
            'total_entries':  sum(r['entries']        for r in rows),
            'total_quantity': sum(r['total_quantity']  for r in rows),
        }

        return render_template('generali_monthreport.html',
            logged_in_user=session.get('username'),
            pageV=pageVisability(),
            section='pdqm',
            section_title='Generali PDQM',
            back_url=url_for('generali_pdqm'),
            year=year, month=month, month_label=month_label,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            is_current_month=is_current_month,
            summary=summary, rows=rows)
    except Exception as e:
        app.logger.error(f"Error loading Generali PDQM Month Report: {e}")
        return render_template('handlers/500.html'), 500

```

- [ ] **Step 2: Add button to `templates/generali_pdqm.html`**

Find the Export Excel button area in `generali_pdqm.html` (the button row has only Export Excel and no nav links):
```html
        <button id="exportExcelBtn" onclick="exportToExcel()"
          class="inline-flex items-center gap-2 bg-white text-green-700 px-4 py-2.5 rounded-xl hover:bg-green-50 transition text-sm font-semibold border border-green-200">
          <i class="fas fa-file-excel"></i><span class="hidden sm:inline">{{ _("Export Excel") }}</span>
        </button>
      </div>
    </div>
```

Add the Month Report button **after** the Export Excel button (before the closing `</div>`):
```html
        <button id="exportExcelBtn" onclick="exportToExcel()"
          class="inline-flex items-center gap-2 bg-white text-green-700 px-4 py-2.5 rounded-xl hover:bg-green-50 transition text-sm font-semibold border border-green-200">
          <i class="fas fa-file-excel"></i><span class="hidden sm:inline">{{ _("Export Excel") }}</span>
        </button>
        <a href="{{ url_for('generali_pdqm_monthreport') }}"
           class="inline-flex items-center gap-2 bg-white text-gray-600 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition text-sm font-semibold border border-gray-200">
          <i class="fas fa-calendar-alt"></i><span class="hidden sm:inline">{{ _("Month Report") }}</span>
        </a>
      </div>
    </div>
```

- [ ] **Step 3: Commit**

```
git add app.py templates/generali_pdqm.html
git commit -m "feat: add month report for generali pdqm"
```

---

## Task 7: Browser test with Playwright via nx

**Goal:** Verify all 5 month report buttons appear, all 5 month report pages load with correct data, and month navigation works.

- [ ] **Step 1: Start the dev server**

```
nx -u -b --loginas:<generali-user>
```

Use a login that has access to generali pages (has at least `generali.reporting.view`, `generali.baseservices.view`, `generali.additionalservices.view`, `generali.projectmanagement.view`, `generali.pdqm.view` permissions).

- [ ] **Step 2: Verify each source page shows the Month Report button**

Using Playwright, navigate to each page and take a screenshot to confirm the button is present:

```javascript
const { chromium } = require('playwright');
const fs = require('fs');
if (!fs.existsSync('screenshots')) fs.mkdirSync('screenshots');

const browser = await chromium.connectOverCDP('http://localhost:9222');
const context = browser.contexts()[0];
const page = context.pages()[0];

const pages = [
  { url: '/generali/reporting',          label: 'reporting' },
  { url: '/generali/additionalServices', label: 'additionalservices' },
  { url: '/generali/baseServices',       label: 'baseservices' },
  { url: '/generali/projectManagement',  label: 'projectmanagement' },
  { url: '/generali/pdqm',               label: 'pdqm' },
];

for (const p of pages) {
  await page.goto(`http://localhost:5000${p.url}`);
  await page.waitForSelector('a[href*="monthreport"]');
  await page.screenshot({ path: `screenshots/monthreport-btn-${p.label}.png` });
  console.log(`✓ ${p.label}: Month Report button found`);
}
```

Expected: 5 screenshots showing the Month Report button in the header, no errors in console.

- [ ] **Step 3: Verify each month report page loads with correct month label**

```javascript
const today = new Date();
const monthName = today.toLocaleString('en', { month: 'long' });
const year = today.getFullYear();
const expectedLabel = `${monthName} ${year}`;

const reportRoutes = [
  { url: '/generali/reporting/monthreport',           label: 'reporting' },
  { url: '/generali/additionalServices/monthreport',  label: 'additionalservices' },
  { url: '/generali/baseServices/monthreport',        label: 'baseservices' },
  { url: '/generali/projectManagement/monthreport',   label: 'projectmanagement' },
  { url: '/generali/pdqm/monthreport',                label: 'pdqm' },
];

for (const r of reportRoutes) {
  await page.goto(`http://localhost:5000${r.url}`);
  await page.waitForSelector('main');
  const monthText = await page.textContent('.min-w-36');
  if (!monthText.includes(monthName) || !monthText.includes(String(year))) {
    throw new Error(`${r.label}: expected "${expectedLabel}" but got "${monthText}"`);
  }
  await page.screenshot({ path: `screenshots/monthreport-page-${r.label}.png` });
  console.log(`✓ ${r.label}: shows "${monthText}"`);
}
```

Expected: 5 screenshots of month report pages showing the current month/year in the navigator.

- [ ] **Step 4: Verify month navigation (prev arrow goes to previous month)**

```javascript
await page.goto('http://localhost:5000/generali/reporting/monthreport');
await page.waitForSelector('.min-w-36');

const prevMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
const prevLabel = prevMonth.toLocaleString('en', { month: 'long' }) + ' ' + prevMonth.getFullYear();

// Click prev arrow
await page.click('a[href*="month="]');
await page.waitForSelector('.min-w-36');

const monthText = await page.textContent('.min-w-36');
if (!monthText.includes(prevLabel.split(' ')[0])) {
  throw new Error(`Navigation failed: expected "${prevLabel}", got "${monthText}"`);
}
await page.screenshot({ path: 'screenshots/monthreport-nav-prev.png' });
console.log(`✓ Navigation: shows "${monthText}"`);

// Click next (should return to current month)
await page.click('a[href*="month="]');
await page.waitForSelector('.min-w-36');
const monthTextBack = await page.textContent('.min-w-36');
if (!monthTextBack.includes(monthName)) {
  throw new Error(`Forward nav failed: expected "${expectedLabel}", got "${monthTextBack}"`);
}
console.log(`✓ Forward nav: shows "${monthTextBack}"`);
```

Expected: screenshots showing prev-month page then back to current month. Next arrow is greyed out on current month.

- [ ] **Step 5: Verify next arrow is disabled on current month**

```javascript
await page.goto('http://localhost:5000/generali/reporting/monthreport');
await page.waitForSelector('main');

// On the current month there should be exactly ONE month nav anchor (prev only);
// next is rendered as a <span class="cursor-not-allowed"> not an <a>
const monthNavLinks = await page.$$('a[href*="month="]');
const disabledSpan  = await page.$('span.cursor-not-allowed');

if (monthNavLinks.length !== 1) throw new Error(`Expected 1 month nav link (prev only) but found ${monthNavLinks.length}`);
if (!disabledSpan)               throw new Error('Expected disabled next-arrow <span> on current month');

await page.screenshot({ path: 'screenshots/monthreport-next-disabled.png' });
console.log('✓ Next arrow correctly disabled on current month');
```

Expected: screenshot shows the greyed-out next arrow, no errors.

- [ ] **Step 6: Verify "Back" button returns to parent page**

```javascript
await page.goto('http://localhost:5000/generali/baseServices/monthreport');
await page.waitForSelector('a[href*="/generali/baseServices"]');
await page.click('a:has-text("Back")');
await page.waitForSelector('main');

if (!page.url().includes('/generali/baseServices')) {
  throw new Error(`Back button went to wrong page: ${page.url()}`);
}
console.log('✓ Back button returns to Base Services');
```

Expected: lands on `/generali/baseServices`.

- [ ] **Step 7: Commit screenshots as test evidence (optional)**

Screenshots land in `screenshots/` — do not commit them to git. Review them visually to confirm layout is correct, then discard:
```
# Review screenshots, then:
Remove-Item screenshots\monthreport-*.png
```
