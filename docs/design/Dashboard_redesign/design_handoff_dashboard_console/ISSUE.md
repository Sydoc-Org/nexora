# Dashboard redesign: console layout

## What
Rebuild the Dashboard page to the approved design (option **1a** in the attached prototype):
a console-style page with a top bar, a borderless KPI strip, a full-width tabbed chart, and a
borderless 14-day per-process backlog trend. No card frames anywhere on the page.

## Why
The Dashboard still looks like a card grid while Reporting has moved to a denser console
layout. The redesign brings the two into the same visual family without making them look
identical, and puts the information operators actually watch (today's throughput and the
backlog trend) in the top two screens' worth of page.

## Scope
1. **Page head** — icon + "Dashboard" + one muted line with user and last sign-in; live
   indicator and "Aktualisieren" button on the right. Drop the marketing subtitle.
2. **Filter row** — existing process scope picker, restyled; new 14 T / 30 T / 90 T range
   control on the right that drives both charts.
3. **KPI strip** — four KPIs in one borderless row separated by hairlines: label, 32px mono
   value, day-over-day delta ("vs. gestern"), and a 120×36 sparkline. No cards, no icon chips.
4. **Main chart** — full content width, no card frame, underline tabs "Zeitverlauf" /
   "Heute nach Stunde". The standalone hourly card is removed and becomes the second tab.
5. **Backlog trend** — borderless, separated by a top rule: header with total and legend, plus a 14-day
   multi-series line chart per process (amber solid / violet dashed / cyan dotted / pink),
   fed from `dbo.BacklogHistory`.
6. **Removals** — "Recent Validations" column and `#activity-feed`, the hourly chart card,
   the `nx-stat` KPI cards, and every `nx-card` frame on the page.

## API work
- `kpi_stats`: add previous-day value and a 7-point daily series per KPI (deltas, sparklines).
- `processed_over_time`: accept a `range` parameter (14/30/90 days).
- New `GET api/dashboard/backlog_trend?range=14` → `{labels, series:[{name, values}]}` from
  `dbo.BacklogHistory`, scoped by the active client/process filter; single total series when
  only one process is selected.

## Implementation notes
The attachment is an HTML **design reference**, not code to copy. Implement it in the existing
stack (Jinja template + `static/css/dashboard.css` + Chart.js 4.5.1) and express every color
through the `--nx-*` tokens so theming and tenant branding still work. Exact measurements,
colors, type sizes, and copy are in `README.md` in the attachment.

## Definition of done
- Dashboard matches option 1a at ≥1180px width, and degrades to 2×2 KPIs below ~1024px.
- Both chart tabs, the range control, and the scope filter refresh the right data.
- Backlog trend renders per-process series with the legend line styles matching the chart.
- No hardcoded hex values in `dashboard.css`; light and dark themes both correct.
- New strings added to de/fr/it; e2e tests updated for the removed feed and hourly card.

## Design system
The attachment also carries `design_system/` — the nexora "slim" UI kit. The new classes
for this page should be built from its component sources and added to `nexora-ui.css` so
they are reusable when the next page is migrated (see README "How to implement against
the kit").

## Attachment
`design_handoff_dashboard_console.zip` — open `Dashboard Redesign.dc.html` (keep
`support.js` beside it) and look at option **1a**; `README.md` has the full spec.
