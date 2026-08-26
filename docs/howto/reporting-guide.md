# Reporting — user guide

This is the **how do I actually use it** guide for the Reporting page. No
technical knowledge assumed. If you want to know how the thing is *built*
instead, read [`reporting.md`](reporting.md) — that one is for developers.

<!-- Maintainers: this file is END-USER-FACING at runtime — the app renders it
  at /reporting/guide (nx_lib/views/reporting.py), and the deploy workflow
  copies it to the server. Keep it current: if you change how Reporting
  *behaves* for a user, update this file AND the in-app tips panel
  (templates/_reporting_help.html, the Help button) in the same commit. See
  "Keeping docs in sync" in CLAUDE.md; the reporting-help-sync pre-commit hook
  reminds you. Keep the H1 unique (Confluence page title). -->

---

## The 60-second version

1. Open **Reporting** from the left navigation.
2. In the **Library**, click **New report** (top right).
3. Answer four questions: *what to measure* → *which processes* → *how to break
   it down* → *what time range*.
4. Click **Show result**.

You now have a number, a chart and a table. Everything else in this guide is
detail on top of those four steps.

---

## Tips — getting the best results

The same tips live inside the app: the **Help** button in the Reporting page
header opens them in a panel, and its **Full guide** link opens this whole
guide as an app page.

**Building a report**

- Watch the **coverage badge** (e.g. `2/5`) on measures and categories: only
  part of the processes provide that field, and documents from the others land
  in the empty bucket. Hover it to see which. If a number looks too low, check
  the badge first.
- Everything in one empty bucket? The breakdown field is not filled in for the
  processes you selected.
- Relative presets stay relative: a report saved with "This month" shows the
  current month on every run and in every scheduled mail. Schedule times are
  UTC.
- The palette button in the chart toolbar recolours each series and the
  title, and puts a series on its own right-hand axis — Backlog starts there
  by default so a few hundred stays readable next to tens of thousands. Picks
  are saved with the report.

**Checking a number**

- Click a chart bar or a table row to open the documents behind that number;
  the **Query** card beside the chart shows exactly how it was computed.
- The ↑/↓ comparison chips compare a window shifted back by your range's
  length in days — not the previous calendar period. Hover a chip for the
  exact dates.
- Two people can see different totals on the same report: it always runs with
  the viewer's own data access.
- Charts cap at 50 axis values and 12 series — past the cap you get a partial
  chart or none at all; the table and exports always carry the full data.

**Saving and sharing**

- Save works differently per builder: from the guided view, Save always creates a new report
  under My reports; on Advanced, Save overwrites the open report — including a
  shared one you can edit. Use **Save as** for a copy.
- A scheduled email runs with the report owner's data access — recipients see
  the owner's numbers, not their own.
- Delete a report you own: open its card's **…** menu under My reports and
  pick Delete, or open the report and use ⋯ → Delete report. Shared copies and
  schedules go with it.

**Asking the AI**

- Name the measure, the time range and the processes: *"invoices by process,
  last 3 months"* beats *"show me invoices"*.
- Check what the AI built with **Open report** — the filters and process
  scope it chose are visible there before you trust the number.
- Follow-ups work: the chat remembers the conversation, so *"now only this
  quarter"* refines the last answer.
- When the AI used tools, unfold **How the agent worked** to see the steps; if
  a **Continue** button appears, click it before rephrasing your question.

> This section and the in-app panel (`templates/_reporting_help.html`) mirror
> each other — change both together.

---

## Finding your way around

The page is a small workspace with a fixed navigation on the left:

- **Library** — every report you can see, as cards: search, sort, and switch
  between 2 or 4 cards per row. This is the start screen.
- **Results** — brings back the **last result you rendered**, exactly as you
  left it, without running the report again.
- **Dashboards** — opens your most recent dashboard.
- **Scheduled** — every automatic delivery you own, in one table.
- **Advanced** — the full builder for exact control.

Under the navigation, the **Sources** list shows each data source you can
report on, with a green dot and its current response time.

## Three ways to build a report

There are three ways in. They all produce the same kind of report; pick
whichever suits you.

| Way in | Where | Best for |
|---|---|---|
| **Guided builder** (wizard) | **New report** in the Library | Almost everyone, almost always. Four questions, no jargon. |
| **Ask Eddard** | **Eddard** button, top right | You know the question in words but not which fields to pick. |
| **Advanced builder** | **Advanced** in the left navigation | You want exact control: pick individual columns, several filters, custom sort, custom headers. |

You can start in one and move to another: any result has an **Open in Advanced**
entry in its **…** menu, and Eddard's answers have an **Open report** chip.

### Way 1 — the guided builder

**New report** walks you through four steps — the step chips across the top
show where you are, and the **So far** panel on the right collects your picks.
**Back** returns a step without losing your picks; **✕** leaves without
deleting anything you saved.

1. **What do you want to measure?**
   Pick one or more measures (e.g. *documents*). The first pick decides which
   data source you are in, so measures from other sources grey out until you
   clear the selection. Each measure you add becomes its own column, series and
   total in the result.

   **The imports / exports / backlog view:** pick *Documents imported*,
   *Documents exported* and *Backlog* together (or the *Pages …* variants),
   break down *Over time (Date)*, and you get one line per measure on a
   shared time axis — imports counted on their import date, exports on their
   export date, backlog as the point-in-time level. These "anchored" measures
   can't be mixed with the plain ones (the incompatible pills grey out).

2. **Which processes?**
   A checklist, everything ticked by default. Untick to narrow. This step is
   skipped for data sources that have no processes. Entries read
   `client.process` (e.g. `privera.03_Invoice_New`) — the same naming, and
   the same set of processes, you see everywhere else in the app (only
   processes you have access to are offered).

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
wizard reopens with all your answers still selected. The chips above the
result are editable too: clicking the **Processes** chip or any *is one of*
filter chip opens a checkbox picker of the known values — no typing needed.
Ticking everything simply removes the restriction.

#### About those "2/5" badges

Some measures and categories carry a small **coverage badge** like `2/5`, with a
progress bar. It means: *only 2 of the 5 processes actually provide this field.*
The two chip types count against different denominators: a **measure** badge
counts all processes you may access (you pick the measure before the process
step, and the badge does not recompute when you narrow the selection later); a
**category** badge counts the processes currently selected.

- Amber = partial coverage. Muted = low coverage (a third or less).
- Hover it to see which processes do provide it.
- Documents from the other processes land in the empty bucket — a partial
  measure only counts the documents of the processes that have it.

Chips that no selected process provides at all are hidden, and the rest sort
best-coverage-first. **If a number looks too low, check the badge first.**

### Way 2 — Ask Eddard

**Eddard** is the reporting assistant — the little black hole in the top bar,
who blinks at you while he waits and throws a report together while he works.
Click **Eddard** in the top-right and ask in plain words — *"documents per
month this year"*, *"invoices by process, last 3 months"* — or click one of
the starter chips in the empty panel. The answer arrives in the same panel.

- Answers where the agent used tools include a **How the agent worked** section
  you can unfold to see each step it took. If a **Continue** button appears
  under an answer, the agent ran out of budget mid-way — one click resumes it
  with more room; try that before rephrasing.
- If it built a report, an **Open report** chip opens it in the results view.
  **Use it.** The filters and process scope Eddard chose are visible there —
  a wrong guess (wrong date range, wrong process) shows up immediately, and
  you can adjust before trusting the number. From there, **Open in Advanced**
  reaches the builder if you need it.
- It remembers the conversation, so "…now only this quarter" works as a
  follow-up. Three follow-up chips are offered for you.

Eddard does not get to bypass anything: he can only build a report you were
already allowed to run, and the report still runs through the normal path with
your own permissions.

If you do not see the **Eddard** button, the assistant is either not switched
on in your environment or not granted to your account.

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

**The stat band** at the top. Every figure says what it is a figure *of*:

- One **total card per measure** — `Total · Documents imported`, then
  `Total · Documents exported`, and so on, one per measure you picked. There is
  no single number combining them: a document that was imported and later
  exported would be counted twice, so adding the two together would not be a
  count of anything real.
- Below them, **number of buckets, average per bucket and peak** for the first
  measure — the card says which one it is describing. A report with no
  breakdown (*just the total*) has no buckets, so these are not shown.

**Delta chips (↑ 12%)** appear on those cards when your report uses exactly one
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
values along the axis and 12 series (the 12 largest are kept). Past 50 axis
values the two builders differ: Advanced charts the top 50 by value with a note;
the guided view charts the first 50 for a category axis, and for a date axis (or a
result with several breakdowns) shows no chart at all with a hint to pick a
coarser granularity or a shorter range. The table and exports always carry the
full data.

**Show table** reveals the data rows. The **Query** card beside the chart
always shows the actual database query behind the number, formatted and
copyable — useful when you want to prove where a figure came from.

### Today, unfinished periods and gaps

- A time chart **stops at today**. *This year* draws January up to the current
  month — the months that haven't happened yet are not drawn as zero, and the
  *Groups* / *Ø per group* cards only count the periods that exist.
- The period that contains today is **still filling up**: its bar is faded (its
  line segment dashed) and the note *"The current period is still running"*
  appears under the chart. Don't read it as a drop.
- **Backlog is a level, not a count.** Its *Total* is the newest snapshot, never
  the sum of all snapshots. A period nobody measured shows as a **gap** in the
  line (not zero) with the note *"Gaps are periods without a backlog snapshot"*.
- A weekly or daily breakdown of a whole year charts fine — the 50-point cut
  only applies to category axes.

### Forecast

If your report is *one time breakdown plus a measure*, the **Forecast** toggle
becomes available. (In the guided view the toggle is always visible in the chart
toolbar but greyed out until the report qualifies; Advanced hides it instead.)
On a line chart it extends the chart with a dashed projection line and a shaded
95% confidence band; on a bar chart the predicted periods are drawn as
translucent bars in the series' colour. Pie and doughnut charts have no
forecast. The predicted rows are appended to the table with a *Forecast* badge,
and switching the forecast off again is instant — nothing is re-queried.

- It fits a trend and, when there is enough history, a repeating seasonal
  pattern on top. The unfinished current period is left out of the fit (it
  stays on the chart as-is) and the projection starts right after it; a
  backlog's unmeasured periods are carried forward, not counted as empty.
- It needs at least 5 periods of history. Below that you get *"Not enough
  history to forecast this series."*
- The setting is saved with the report — including for scheduled emails.
- Exports get an extra **Forecast** column so you can tell predicted rows from
  real ones. Predicted points are not clickable — there are no real documents
  behind a number the system invented.

### Colours & axes

The palette button in the chart toolbar opens a small panel with a colour
picker for every series and one for the **report title and legend**. Each
series also has a **Left | Right** switch: put it on *Right* to plot that line
against its own scale on the right-hand side — the way to keep a *Backlog* of a
few hundred readable next to imports in the tens of thousands (when *Backlog*
shares a chart with other measures it starts on the right axis by default).
Each axis is titled with the series it carries, and when it carries exactly one
series its numbers take that series' colour. **Reset colours** returns to the
standard palette.

- Your picks are saved with the report and come back when you open it.
- Emailed reports and the Advanced builder use the standard colours.

### Click a bar to see the documents behind it

On any report that has a measure *and* a breakdown, **clicking a chart bar/point
or a table row** opens a drawer listing the actual documents that make up that
number. A hint line tells you when this is available.

- Shows up to **100 rows**. The drawer's CSV / Excel export is currently capped
  at the same 100 rows — for the full set, narrow the bucket or run the
  underlying rows as their own report.
- Workitem numbers are links — click to open the document detail panel over the
  drawer, or Ctrl-click to open it in a new Workitems tab.
- Not available on: plain row lists with no measure, the single big-number card,
  pivot cells, and hand-written SQL results.
- On a distinct-count measure, the drawer says so: you may see more rows than
  the number, because the same value can appear on several rows.

---

## Saving, sharing, finding again

**Save** stores the report under **My reports** — but the two builders treat
it differently. From the guided view, Save always creates a *new* report, even
when you opened one from the library. In the **Advanced** builder, Save
overwrites the loaded report — including a shared report you have edit rights
on, for everyone — and **Save as** makes a copy. Editing the title and hitting
Save also renames it.

The **Library** groups everything into three shelves:

- **Library** — reports shared with the whole organisation.
- **My reports** — yours.
- **Shared with me** — reports someone shared with you by name.

Above the shelves: a **search box**, a **sort** dropdown (recently updated /
name), and a layout toggle for **2 or 4 cards per row**. Every card you own has
a **…** menu with **Share** and **Delete**; clicking anywhere else on the card
opens the report.

Cards show a small preview chart. It only reflects your real numbers after you
have opened and run that report in this browser — before that it is a
decorative placeholder, so don't read trends off a card you haven't opened.
Nothing runs until you click a card.

**Share** (on a report you own) does two independent things:

- **Visibility** — *private* (only you) or *shared* (readable by everyone who
  can open the Reporting page).
- **Named shares** — share with specific colleagues, optionally with **Can
  edit**.

Once a report of yours is shared either way, its card and its entry in the
Advanced dropdown are tagged **· shared**. A named share does not move the card
to the **Library** shelf — that shelf is only for reports shared with the whole
organisation.

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

The **Scheduled** page (left navigation) lists every automatic delivery you
own, across all your reports: what runs, how often, who gets it, in which
format, when it last ran and when it runs next. From there:

- The **toggle** at the start of each row switches a schedule on or off —
  switched-off rows stay in the list, dimmed.
- **New schedule** opens a small form: pick one of your saved reports, a
  **frequency** (daily / weekly / monthly), a **time** (UTC — mind the
  offset), a **format** (Excel / CSV) and the **recipients**.
- The bin icon at the end of a row deletes that schedule.

Reports with a breakdown get the chart drawn into the mail body and into the
attached file.

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
or **table** — or a **Whole report** tile.

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
- **Whole report** imports a saved report exactly as the Simple tab shows it:
  the KPI band with one labelled total per measure, the chart with its colours,
  right axis and forecast, and the full table behind **Show table** (rows drill
  through like everywhere else). Global filters still apply. The tile is
  read-only — change colours, chart type or forecast in the report itself.

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
| The line chart shows no empty months | Zero-months only appear for a single date breakdown with a bounded time range. With a second breakdown or "All time", empty periods drop off the axis entirely. |
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
| Ask Eddard | AI assistant access |
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
