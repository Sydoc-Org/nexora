# Reporting — user guide

This is the **how do I actually use it** guide for the Reporting page. No
technical knowledge assumed. If you want to know how the thing is *built*
instead, read [`reporting.md`](reporting.md) — that one is for developers.

> Keep this guide current. If you change how Reporting *behaves* for a user —
> a renamed button, a new step in the wizard, a different default — update this
> file in the same commit. See the "Keeping docs in sync" rule in `CLAUDE.md`.

---

## The 60-second version

1. Open **Reporting** from the left navigation.
2. Click **New report — guided builder**.
3. Answer four questions: *what to measure* → *which processes* → *how to break
   it down* → *what time range*.
4. Click **Show result**.

You now have a number, a chart and a table. Everything else in this guide is
detail on top of those four steps.

---

## Three ways to build a report

The page has two tabs — **Simple** and **Advanced** — and three ways in. They
all produce the same kind of report; pick whichever suits you.

| Way in | Where | Best for |
|---|---|---|
| **Guided builder** (wizard) | Simple tab | Almost everyone, almost always. Four questions, no jargon. |
| **Ask AI** | Simple tab (the bar at the top) | You know the question in words but not which fields to pick. |
| **Advanced builder** | Advanced tab | You want exact control: pick individual columns, several filters, custom sort, custom headers. |

You can start in one and move to another: any result has an **Open in Advanced**
button, and the AI's answers have an **Open in builder** chip.

### Way 1 — the guided builder

**New report — guided builder** walks you through four steps. **Back** returns a
step without losing your picks; **✕** leaves without deleting anything you saved.

1. **What do you want to measure?**
   Pick one or more measures (e.g. *documents*). The first pick decides which
   data source you are in, so measures from other sources grey out until you
   clear the selection. Each measure you add becomes its own column, series and
   total in the result.

2. **Which processes?**
   A checklist, everything ticked by default. Untick to narrow. This step is
   skipped for data sources that have no processes.

3. **Break it down by…**
   - *Over time* — pick a **Granularity** (Week / Month / Quarter / Year).
   - *A category* — e.g. **Process**, Document Source, Document Type, Owner no.
   - *None — just the total* — one big number, no chart.

   You can pick up to **three** breakdowns. The first one becomes the chart's
   horizontal axis; the rest become the coloured series (e.g. "Process ·
   Document Source").

4. **Time range**
   A preset (Today, This week, This month, Last month, Last 3 months, This
   quarter, Last quarter, This year, Last year, Last N days) or **Custom** with a
   date picker. Also choose the **Date field** — usually *import date* (when the
   document came in) or *export date* (when it left).

   **Presets are relative, and stay relative.** A report saved with "This month"
   shows *this* month every time it is opened or emailed — it does not freeze on
   the month you built it in.

Then **Show result**. To change something afterwards, hit **Adjust** — the
wizard reopens with all your answers still selected.

#### About those "2/5" badges

Some measures and categories carry a small **coverage badge** like `2/5`, with a
progress bar. It means: *only 2 of the 5 processes you selected actually provide
this field.*

- Amber = partial coverage. Muted = low coverage (a third or less).
- Hover it to see which processes do provide it.
- Documents from the other processes land in the empty bucket — a partial
  measure only counts the documents of the processes that have it.

Chips that no selected process provides at all are hidden, and the rest sort
best-coverage-first. **If a number looks too low, check the badge first.**

### Way 2 — Ask AI

Type a question into the bar at the top of the Simple tab — *"documents per
month this year"*, *"invoices by process, last 3 months"* — and press Enter, or
click one of the suggestion chips. This opens the **AI chat** panel on the right
and answers there.

- Every answer has a **How the agent worked** section you can unfold to see what
  it actually did.
- If it built a report, an **Open in builder** chip drops it into the Advanced
  builder so you can check and adjust it.
- It remembers the conversation, so "…now only this quarter" works as a
  follow-up. Three follow-up chips are offered for you.
- Results the AI built show a **transparency line** under the title: the filters
  and processes it chose. **Read it.** A wrong guess (wrong date range, wrong
  process) is visible right there.

The AI does not get to bypass anything: it can only build a report you were
already allowed to run, and the report still runs through the normal path with
your own permissions.

If you do not see the AI bar or the **AI chat** button, the assistant is either
not switched on in your environment or not granted to your account.

### Way 3 — the Advanced builder

Three panels:

- **Left** — the data source, the process picker, and a searchable list of
  fields. Double-click or drag a field to add it as a column.
- **Middle** — your result, plus the report title, **Save** and **Export**.
- **Right** — **Columns** (order, and custom display headers), **Filters**,
  **Sort**, **Format** (title/subtitle).

Then **Run**.

Filters support: equals, not equals, is one of, is not one of, greater/less
than (and or-equal), between, contains, starts with, is empty, is not empty.
Date filters offer the same relative presets as the wizard.

Narrowing the process selection also **removes** any column, filter or sort on a
field none of the remaining processes provide — that is deliberate, the report
could not run otherwise.

---

## Reading the result

**The stat band** at the top: total, number of buckets, average per bucket, and
peak. Computed from the rows on screen, so it costs no extra query time.

**Delta chips (↑ 12%)** appear on those tiles when your report uses exactly one
relative date preset. They compare against the period *immediately before* the
one you are looking at.

Two things to know, because they surprise people:

- **It is not "last calendar month".** It shifts back by however many days your
  current window is long. A 31-day month shifted back 31 days does not land
  neatly on the 1st of a 30-day month. Hover the chip — the tooltip always shows
  the exact dates it compared against.
- **The arrow colour is direction only, never judgement.** Up is up. The chip
  does not know whether up is good news for your metric.

The **average** chip disappears when the two periods do not have the same number
of buckets — averaging across two different-length periods would invent a
percentage, so it is dropped rather than shown wrong.

**The chart** is a line for time breakdowns and bars for categories, with a
bar / line / pie / doughnut switcher (your choice is saved with the report).
There is a button to download the chart as a **PNG**. Charts show at most 50
values along the axis and 12 series; beyond that the top 50 are charted with a
note.

**Show table** reveals the data rows. **Show query** reveals the actual database
query behind the number, formatted and copyable — useful when you want to prove
where a figure came from.

### Forecast

If your report is *one time breakdown plus a measure*, a **Forecast** toggle
appears. It extends the chart with a dashed projection line and a shaded 95%
confidence band, and appends the predicted rows to the table with a *Forecast*
badge.

- It fits a trend and, when there is enough history, a repeating seasonal
  pattern on top.
- It needs at least 5 periods of history. Below that you get *"Not enough
  history to forecast this series."*
- The setting is saved with the report — including for scheduled emails.
- Exports get an extra **Forecast** column so you can tell predicted rows from
  real ones. Predicted points are not clickable — there are no real documents
  behind a number the system invented.

### Click a bar to see the documents behind it

On any report that has a measure *and* a breakdown, **clicking a chart bar/point
or a table row** opens a drawer listing the actual documents that make up that
number. A hint line tells you when this is available.

- Shows up to **100 rows**; export from the drawer (CSV / Excel) for the full
  set.
- Workitem numbers are links — click to open the document detail panel over the
  drawer, or Ctrl-click to open it in a new Workitems tab.
- Not available on: plain row lists with no measure, the single big-number card,
  pivot cells, and hand-written SQL results.
- On a distinct-count measure, the drawer says so: you may see more rows than
  the number, because the same value can appear on several rows.

---

## Saving, sharing, finding again

**Save** stores the report under **My reports**. With a report open, Save
overwrites it; **Save as** always makes a copy. Editing the title and hitting
Save also renames it.

The library on the Simple tab groups everything into three shelves:

- **Library** — reports shared with the whole organisation.
- **My reports** — yours.
- **Shared with me** — reports someone shared with you by name.

Cards show a small preview of the report's last result. Nothing runs until you
click a card.

**Share** (on a report you own) does two independent things:

- **Visibility** — *private* (only you) or *shared* (readable by everyone who
  can open the Reporting page).
- **Named shares** — share with specific colleagues, optionally with **Can
  edit**.

Only the owner can change visibility, manage shares, rename or delete. Someone
with a read-only share who edits and saves gets their own copy instead.

> **Two people can open the same shared report and see different numbers.** That
> is correct, not a bug: a report always runs with the *viewer's* own data
> access. Someone who cannot see a process simply does not get its rows.

---

## Exporting

Pick **Excel** or **CSV** next to the **Export** button. What you get depends on
what you are looking at:

- **Table/grid view** → the data rows. Excel includes a title block (report
  title, source, timestamp), a frozen header row, and — if a chart is on screen
  — the chart image above the table. CSV is data rows only.
- **Pivot view** → the pivot matrix as displayed.
- **Chart view** → a PNG image of the chart.

---

## Getting it by email

On a report you own, **Schedule** sets up automatic delivery: **frequency**
(daily / weekly / monthly), **time** (UTC — mind the offset), **format**
(Excel / CSV) and **recipients**. Reports with a breakdown get the chart drawn
into the mail body and into the attached file.

Schedules can be switched on and off individually from the list.

**Alert-only schedules.** The **Send** dropdown can turn a schedule into an
alert: *only when the total is above / at least / below / at most N*. If the
condition is not met, no mail goes out that run. For reports without a measure,
the threshold compares against the number of rows.

The schedule runs the report **as its owner**, with the owner's data access —
not the recipients'.

---

## Dashboards

**New dashboard** builds a page of live tiles instead of a single report. Each
tile is its own small report: **KPI** (one number), **line**, **bar**, **donut**
or **table**.

- **Edit / Done** toggles edit mode: drag tiles to rearrange, add, duplicate or
  remove them, and set the **global filters**.
- Global filters apply to every tile *except* tiles that override that field —
  those are marked "This card overrides the global filters".
- A KPI tile shows a "vs previous period" change when its filters contain
  exactly one date range that can be shifted back (this month → last month, and
  so on). Anything more ambiguous shows no trend rather than guessing.
- Tiles drill through exactly like a normal report — click one and the document
  drawer opens. (Donut tiles are the exception: their "Other" grouping breaks
  the mapping.)
- **Export** is per tile: the header menu lists the tiles, pick one.

A dashboard saves, shares and deletes exactly like any other report.

---

## Why does my number look wrong?

| Symptom | Likely cause |
|---|---|
| Number lower than expected | A measure or category with a partial coverage badge (`2/5`) — the other processes contribute nothing to it. |
| A colleague sees a different total | Correct behaviour. Reports run with the viewer's own data access. |
| "Showing the first N rows…" | The result hit the row cap. Narrow the filters or the time range. |
| The comparison chip looks off by a few days | The comparison shifts by day count, not calendar period. Hover it for the exact dates compared. |
| The average delta chip vanished | The two periods have different bucket counts, so the percentage would be fabricated. Total and peak are still valid. |
| Everything lands in one empty bucket | The breakdown field is not filled in for the processes you selected. |
| The saved report shows a different month than when I built it | Working as intended — relative presets re-resolve on every run. |
| Scheduled mail arrives at an odd hour | Schedule times are **UTC**. |
| Chart says it is showing the top 50 | Charts cap at 50 axis values and 12 series. Filter down, or use the table/export. |
| A button is missing entirely | It is permission-gated. See below. |

---

## Words used on the page

| Word | Means |
|---|---|
| **Measure** | The thing being counted or summed — e.g. documents. |
| **Breakdown / dimension** | What splits the number up — per month, per process, per document type. |
| **Granularity / grain** | How wide a time bucket is: week, month, quarter, year. |
| **Process** | One configured document workflow. In this deployment each one corresponds to a client, so "per process" reads as "per client". |
| **Source** | Which body of data the report reads from. Most reports use *Document Processing*. |
| **Scope** | The processes a report is allowed to include. |
| **Bucket** | One bar/point of the chart — one month, one category, … |
| **Drill-through** | Clicking a number to see the individual documents behind it. |

---

## If something is greyed out or missing

Reporting is permission-gated feature by feature, so two people can see two
different pages. Ask an administrator to grant what you need:

| You cannot… | Ask for |
|---|---|
| Open the page at all | Reporting page access |
| See a particular data source | Access to that source |
| Export to Excel/CSV | Export permission |
| See a client or process in the picker | Row scope for that process |
| Use the AI assistant | AI assistant access |
| Set up email delivery | Scheduling permission |
| Write your own SQL | SQL sandbox access (below) |

---

## For administrators (internal)

Everything above is for anyone using the page. The rest is for people who
administer it.

**Data sources** (`/reporting/sources`) — the registry of what the source
selector offers. Add or retire a source here; no code change needed for a
table-shaped source.

**Measures** (`/reporting/metrics`) — the list the wizard's first step offers.
Adding a row here widens the guided builder for everyone, without a release.

**Live SQL sandbox** — the **SQL** tab in the Advanced builder, for when the
builder cannot express the query. It runs a single read-only `SELECT` against a
chosen target (Statistics, and the Octo runtime database with the extra
permission). Guard rails: the statement is parsed and rejected unless it is a
single `SELECT`, it runs on a read-only login, results cap at 50,000 rows,
statements time out at ~30 seconds, and every run is audited. First use requires
a one-time acknowledgement.

Setup, permission codes, endpoints, database schema and everything else
technical: [`reporting.md`](reporting.md).

---

## See also

- [`reporting.md`](reporting.md) — the developer/architecture reference.
- [`../design/reporting-ai-assistant.md`](../design/reporting-ai-assistant.md) —
  how the AI assistant is designed.
