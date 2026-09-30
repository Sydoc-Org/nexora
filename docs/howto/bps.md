# Sydoc BPS — every hour booked in the BPS timetool

`/bps` shows all hours Sydoc books in the BPS timetool for a period, broken down
by task, customer and person, down to the single booking and its comment. It is
the in-depth companion of the Finance page, which lists only the **billable**
bookings of a month (`docs/howto/finance.md`). Issue #415; permission `bps.view`;
migration `0140`.

## Where the data comes from

The registered `bps_projects` reporting source (`0124`, repointed by `0142`)
over the view `SYDOC_Statistik.dbo.BPS_ProjectReportAll`: one row per booking
with `Kunde` (customer), `Projektpaket` (package), `Aufgabe` (task), `Benutzer`
(person), `Datum`, `Stunden` and `Beschreibung` (the comment). The queries are
built with the reporting `table` provider (`build_generic_query`), like Finance
and Reporting.

- The view is the live feed plus a history table (#424):
  - `dbo.BPS_ProjectReport` — the bpsuite Projektbericht export, **reloaded
    every morning** (04:00, truncate and reload), starting **3 August 2026**.
    Never insert into it by hand: the next load wipes it.
  - `dbo.BPS_ProjectReportHistory` — a one-off load of an older Projektbericht
    `.xlsx` export: **3 January 2025 – 31 July 2026**, 72,080 bookings,
    62,616.03 h (subtotal lines and rows with an empty customer or package
    dropped, as the feed does). Same columns as the feed.
  - The view takes history rows only **before the feed's first date**, so if
    the export is ever widened the overlap comes from the feed and nothing is
    counted twice. History `ID`s are negated to stay unique.
  - Both tables and the view exist on PRDSQL01 and INTSQL01. They sit on the
    vendor-side Statistics DB, which is not tracked under `sql/`; to reload the
    history, empty `BPS_ProjectReportHistory` and insert the rows again (one
    transaction), keeping the cutoff at the feed's first date.
- Closing a Finance month freezes that month's billable bookings in its
  snapshot — months closed before the history was loaded keep their snapshot.
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

Redesigned in #427 as the mirror of Sydoc Finance (design 1a in
`docs/design/design_handoff_sydoc_finance_bps/`): the ink header band, the
period headline and the period picker are shared with `/finance`.

- **Period**: two dates in the URL (`/bps?from=2026-08-01&to=2026-08-31`),
  default the previous month, at most a year. The headline names it ("August
  2026", "Week 39", "Jun – Aug", "4 – 19 Aug"); the arrows beside it go to the
  previous / next month (or the same number of days before / after) and stop
  when the next period would start after today. Clicking the headline opens the
  **picker**: presets (last month, this month, last week, last three months),
  the months of a year with their hours (a month without hours reads "No data";
  loaded lazily from `/api/bps/months`), and a free from/to range.
- **Band totals**: total hours, service hours, bookings, people with service
  hours, and a composition bar billable / other service / absence.
- **Hours per day**: stacked columns billable / other service / absence,
  weekends shaded. The three hues are the page's `--bps-*` tokens in
  `static/css/bps.css`, checked with the dataviz palette validator against the
  chart surface in both themes; every category is also named in the legends.
- **Drill-down**: one level at a time in one of three orders — task › customer ›
  person (default), customer › task › person, person › customer › task. Click a
  row (or tile) to zoom in; the breadcrumb, the back button, Backspace or
  Alt+← go up. Two views: **Table** (default; hours, billable hours, bookings,
  the change against the previous period, and the split of each row) and
  **Treemap** (squarified, tile size = hours). The view choice is kept per
  browser (`localStorage` `nx.bps.view`). The third level lists the single
  bookings per day with package, hours and comment (five per day, then "Show
  n more"). Filters: billable only, hide absences, a text filter over task /
  customer / package / person; they apply at every level, and changing the
  order or the text filter goes back to the top.
- **Previous period** ("vs. July"): the previous calendar month when the
  period is exactly one month, otherwise as many days just before it
  (`bps.previous_range`).
- **CSV**: every booking of the period with its category.

One summary request (`/api/bps/summary`) returns hours per task / customer /
package / person plus per day, and the same rows for the previous period
(`prev`); the drill-down is built in the browser from it, so changing the
order, the view or a filter never goes back to the server. A leaf loads its
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
| Routes: page, summary, entries, months, CSV | `nx_lib/views/bps.py` |
| Page, JS shim, behaviour, styles | `templates/bps.html`, `templates/js/_bps_js.html`, `static/js/bps.js`, `static/css/bps.css` |
| Drill-down logic (levels, deltas, treemap, per-day) | `static/js/bps_view.js` (`window.BpsView`) |
| Band, headline, picker shared with Finance | `templates/_sydoc.html`, `static/js/nx_sydoc.js`, `nx-sydoc-*` in `static/css/nexora-ui.css` |
| Permission | `sql/_migrations/NexoraDB/0140_bps_page.sql`, `sql/test/seed.sql` |
| Tests | `tests/unit/test_bps.py`, `tests/unit/test_bps_view_js.py`, `tests/unit/test_nx_sydoc_js.py`, `tests/integration/test_bps_routes.py` |
