# Sydoc BPS — every hour booked in the BPS timetool

`/bps` shows all hours Sydoc books in the BPS timetool for a period, broken down
by task, customer and person, down to the single booking and its comment. It is
the in-depth companion of the Finance page, which lists only the **billable**
bookings of a month (`docs/howto/finance.md`). Issue #415; permission `bps.view`;
migration `0140`.

## Where the data comes from

The registered `bps_projects` reporting source (`0124`) over
`SYDOC_Statistik.dbo.BPS_ProjectReport`: one row per booking with `Kunde`
(customer), `Projektpaket` (package), `Aufgabe` (task), `Benutzer` (person),
`Datum`, `Stunden` and `Beschreibung` (the comment). The queries are built with
the reporting `table` provider (`build_generic_query`), like Finance and
Reporting.

- The export is **reloaded every morning** (04:00, truncate and reload) and
  starts on **3 August 2026**; earlier periods are empty. Closing a Finance
  month freezes that month's billable bookings in its snapshot.
- BPS has **no billing flag**. What is billable is a property of the task name,
  defined once in `nx_lib/bps.py` (`BILLABLE_RULES` for SQL, `is_billable()` for
  rows in memory; `tests/unit/test_bps.py` keeps them in step): the tasks
  `Support-verrechenbar`, `Support extern verrechenbar`, `Change`,
  `Change Request`, `Professional Services`, `Projektmanagement` on customers
  other than `sydoc` / `sydoc intern`, plus `Vorbereitung Akten` on `Privera` ·
  `Tagesgeschäft Neuzugänge`. Change the rule there and both pages follow.
- Every booking falls in one of three categories: **billable**, **other
  service** (all other work, breaks included) and **absence** (the `Absences`
  pseudo-customer: vacation, sickness, compensation, military).
- Text is cleaned for display: HTML entities in comments (`&amp;`), stray
  leading/trailing blanks, doubled blanks inside names (`Astrid  Schicker`). The
  drill-down therefore matches a person on the cleaned name.

## The page

- **Period**: two dates in the URL (`/bps?from=2026-08-01&to=2026-08-31`),
  default the previous month, at most a year. Presets: last month, this month,
  last week, last three months.
- **KPIs**: total, service, billable and absence hours, bookings, people with
  service hours.
- **Hours per day**: stacked columns billable / other service / absence. The
  three hues are the page's `--bps-*` tokens in `static/css/bps.css`, checked
  with the dataviz palette validator against the chart surface in both themes;
  every category is also named in the legend, the KPIs and the tree.
- **Drill-down**: a tree in one of three orders — task › customer › person
  (default), customer › task › person, person › customer › task — with hours,
  billable hours, bookings and share of the parent. The third level opens the
  single bookings with date, package, hours and comment. Filters: billable only,
  hide absences, a text filter over task / customer / package / person.
- **CSV**: every booking of the period with its category.

One summary request (`/api/bps/summary`) returns hours per task / customer /
package / person plus per day; the tree is built in the browser from it, so
changing the order or a filter never goes back to the server. A leaf loads its
bookings from `/api/bps/entries` (5,000 at most; the CSV has all).

## Permission

`bps.view` is its own area. The page names every employee's hours and reads the
`table` provider without row scoping: internal only, **never** a customer
profile. `0140` grants it to `Global Admin`; `Enterprise Admin` holds it through
the `0106` trigger.

## Files

| What | Where |
|---|---|
| Billable rule, period, queries, payloads | `nx_lib/bps.py` (pure, DB-free) |
| Routes: page, summary, entries, CSV | `nx_lib/views/bps.py` |
| Page, JS shim, behaviour, styles | `templates/bps.html`, `templates/js/_bps_js.html`, `static/js/bps.js`, `static/css/bps.css` |
| Permission | `sql/_migrations/NexoraDB/0140_bps_page.sql`, `sql/test/seed.sql` |
| Tests | `tests/unit/test_bps.py`, `tests/integration/test_bps_routes.py` |
